"""
ACM Agent 训练计划 Agent —— LangGraph StateGraph with MemorySaver.

Nodes: load_profile → determine_phase → select_targets → calc_curve
    → retrieve_problems → llm_arrange → save_plan → END

Produces a weekly training plan with ZPD difficulty curve and 5-dimension problem scoring.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.taxonomy import ALL_TAGS, BASIC_TAGS, DEPENDENCY_GRAPH


# ============================================================
# State
# ============================================================

class TrainingState(TypedDict):
    user_id: str
    profile_id: str
    plan_days: int
    daily_target: int
    profile: Dict[str, Any]
    weak_tags_ranked: List[str]
    candidate_problems: List[Dict[str, Any]]
    weekly_plan: Dict[str, Any]
    difficulty_curve: List[float]
    targets: Dict[str, Any]
    plan_data: Dict[str, Any]
    errors: List[str]


# ============================================================
# DB mock (in-memory for construction)
# ============================================================

class _TrainingDatabase:
    """In-memory database for user profiles and training plans."""

    def __init__(self) -> None:
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._plans: Dict[str, Dict[str, Any]] = {}
        self._problems: List[Dict[str, Any]] = []

    def set_profile(self, user_id: str, profile: Dict[str, Any]) -> None:
        self._profiles[user_id] = profile

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._profiles.get(user_id)

    def add_problems(self, problems: List[Dict[str, Any]]) -> None:
        self._problems.extend(problems)

    def get_all_problems(self) -> List[Dict[str, Any]]:
        return list(self._problems)

    def save_plan(self, user_id: str, plan: Dict[str, Any]) -> None:
        if user_id not in self._plans:
            self._plans[user_id] = {}
        plan_key = plan.get("profile_id", "unknown")
        self._plans[user_id][plan_key] = plan

    def get_plan(self, user_id: str, profile_id: str) -> Optional[Dict[str, Any]]:
        return self._plans.get(user_id, {}).get(profile_id)


DEFAULT_TRAINING_DB = _TrainingDatabase()


# ============================================================
# 5-dimension Problem Scoring Function
# ============================================================

def _gaussian_diff_match(problem_diff: float, target_diff: float, sigma: float = 1.5) -> float:
    """Gaussian difficulty match score: exp(-(diff_delta)^2 / (2*sigma^2))."""
    delta = problem_diff - target_diff
    return math.exp(-(delta ** 2) / (2.0 * sigma ** 2))


def _normalize_vector(v1: List[float], v2: List[float]) -> float:
    """Cosine similarity approximation via dot product (assumes pre-normalized)."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def compute_problem_score(
    *,
    problem_tags: List[str],
    target_tags: List[str],
    problem_diff: float,
    target_diff: float,
    problem_vector: List[float],
    target_vector: List[float],
    previously_solved: bool,
    dep_satisfied: bool,
) -> Dict[str, float]:
    """Compute 5-dimension score for a candidate problem.

    Dimensions:
        1. tag_match           (weight 0.30) — Jaccard overlap with target tags
        2. diff_match          (weight 0.25) — Gaussian centred at target difficulty
        3. vector_similarity   (weight 0.15) — cosine similarity of embeddings
        4. novelty             (weight 0.15) — 1.0 if not previously solved, else 0.0
        5. dependency_satisfied(weight 0.15) — 1.0 if deps met, else 0.2

    Returns dict with per-dimension scores and total.
    """
    # 1. Tag match — Jaccard
    p_set = set(problem_tags)
    t_set = set(target_tags)
    if not t_set:
        tag_match = 0.0
    else:
        intersection = len(p_set & t_set)
        union = len(p_set | t_set)
        tag_match = intersection / union if union > 0 else 0.0

    # 2. Difficulty match — Gaussian
    diff_match = _gaussian_diff_match(problem_diff, target_diff)

    # 3. Vector similarity
    vec_sim = _normalize_vector(problem_vector, target_vector)

    # 4. Novelty
    novelty = 0.0 if previously_solved else 1.0

    # 5. Dependency satisfied
    dep_score = 1.0 if dep_satisfied else 0.2

    total = (
        0.30 * tag_match
        + 0.25 * diff_match
        + 0.15 * vec_sim
        + 0.15 * novelty
        + 0.15 * dep_score
    )

    return {
        "tag_match": round(tag_match, 4),
        "diff_match": round(diff_match, 4),
        "vector_similarity": round(vec_sim, 4),
        "novelty": round(novelty, 4),
        "dependency_satisfied": round(dep_score, 4),
        "total": round(total, 4),
    }


# ============================================================
# Agent
# ============================================================

class TrainingAgent:
    """LangGraph agent that generates a weekly training plan.

    Produces a ZPD-aligned difficulty curve, retrieves candidate problems
    with 5-dimension scoring, and arranges a 2+2+1 daily pattern via LLM.
    """

    def __init__(
        self,
        db: Optional[_TrainingDatabase] = None,
        llm: Any = None,
    ) -> None:
        self.db = db or DEFAULT_TRAINING_DB
        if llm is None:
            try:
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(model="deepseek-chat")
            except Exception:
                self.llm = None
        else:
            self.llm = llm
        self.graph = self._build()

    # ================================================================
    # Node: load_profile
    # ================================================================

    def _load_profile(self, state: TrainingState) -> TrainingState:
        """Load user profile from DB mock into state."""
        user_id = state["user_id"]
        profile = self.db.get_profile(user_id)

        if profile is None:
            state["errors"] = list(state.get("errors", [])) + [
                f"Profile not found for user_id={user_id}"
            ]
            state["profile"] = {}
            state["weak_tags_ranked"] = []
            return state

        state["profile"] = profile
        state["weak_tags_ranked"] = profile.get("weak_tags_ranked", [])
        state["profile_id"] = profile.get("profile_id", state.get("profile_id", "unknown"))
        state["errors"] = state.get("errors", [])
        return state

    # ================================================================
    # Node: determine_phase
    # ================================================================

    @staticmethod
    def _determine_phase(state: TrainingState) -> TrainingState:
        """Rule-based phase classifier per spec §3.2.

        Priorities (top-down, first match wins):
          1. template_consolidation : coverage < 0.3 OR >= 3 weak basics
          2. contest_simulation     : ceiling >= 8 AND overall_score >= 0.7
          3. integrated_practice    : ceiling >= 6 AND efficiency >= 0.5
          4. topic_breakthrough     : has clear weakness (gap > 0.5) AND ceiling < 7
          5. default                : topic_breakthrough

        The phase is stored in state["profile"]["phase"].
        """
        profile = state.get("profile", {})
        dims = profile.get("dimensions", {})

        coverage = dims.get("coverage", 0.0)
        ceiling = dims.get("ceiling", 0.0)
        efficiency = dims.get("efficiency", 0.0)
        overall_score = dims.get("overall", 0.0)
        weak_basics = [
            w for w in profile.get("weaknesses", [])
            if any(b in BASIC_TAGS for b in str(w.get("category", "")).lower().split())
        ]
        # Also check weak_tags_ranked for basic tag presence
        weak_tags = state.get("weak_tags_ranked", [])
        weak_basic_count = (
            len(set(basic for basic in weak_tags if basic in BASIC_TAGS))
            + len(weak_basics)
        )

        # Determine if there's a clear weakness gap
        strengths = profile.get("strengths", [])
        weaknesses = profile.get("weaknesses", [])
        has_clear_weakness = False
        if strengths and weaknesses:
            best_strength = max((s.get("coverage", 0.0) for s in strengths), default=0.0)
            worst_weakness = min((w.get("coverage", 0.0) for w in weaknesses), default=1.0)
            gap = best_strength - worst_weakness
            has_clear_weakness = gap > 0.5

        # ---- classify ----
        if coverage < 0.3 or weak_basic_count >= 3:
            phase = "template_consolidation"
        elif ceiling >= 8.0 and overall_score >= 0.7:
            phase = "contest_simulation"
        elif ceiling >= 6.0 and efficiency >= 0.5:
            phase = "integrated_practice"
        elif has_clear_weakness and ceiling < 7.0:
            phase = "topic_breakthrough"
        else:
            phase = "topic_breakthrough"

        # Store phase inside profile so it travels through the graph
        profile["phase"] = phase
        state["profile"] = profile
        state["errors"] = state.get("errors", [])
        return state

    # ================================================================
    # Node: select_targets
    # ================================================================

    @staticmethod
    def _select_targets(state: TrainingState) -> TrainingState:
        """Determine primary(2-3), secondary(1-2), explore(0-1) tags based on phase.

        Phase strategy:
          - template_consolidation: primary=2 basics, secondary=1 medium, explore=0
          - topic_breakthrough:    primary=3 weak, secondary=2 adjacent, explore=1
          - integrated_practice:   primary=2 mixed, secondary=2, explore=0
          - contest_simulation:    primary=3 random, secondary=1, explore=1
        """
        phase = state["profile"].get("phase", "topic_breakthrough")
        weak_tags = state.get("weak_tags_ranked", [])
        profile = state.get("profile", {})

        if phase == "template_consolidation":
            primary = [t for t in weak_tags if t in BASIC_TAGS][:2]
            if len(primary) < 2:
                extras = [t for t in BASIC_TAGS if t not in primary]
                primary.extend(extras[: 2 - len(primary)])
            secondary = [t for t in weak_tags if t not in primary and t not in BASIC_TAGS][:1]
            explore: List[str] = []

        elif phase == "topic_breakthrough":
            primary = weak_tags[:3] if len(weak_tags) >= 3 else list(weak_tags)
            secondary = []
            for tag in primary:
                deps = DEPENDENCY_GRAPH.get(tag, [])
                for d in deps:
                    if d not in primary and d not in secondary:
                        secondary.append(d)
            secondary = secondary[:2]
            explore = [t for t in ALL_TAGS if t not in primary and t not in secondary][:1]

        elif phase == "integrated_practice":
            strengths_list = [s.get("category", "") for s in profile.get("strengths", [])]
            weaknesses_list = [w.get("category", "") for w in profile.get("weaknesses", [])]
            primary = (weaknesses_list[:2] if weaknesses_list else weak_tags[:2])
            if len(primary) < 2:
                primary.extend(strengths_list[: 2 - len(primary)])
            secondary = strengths_list[:2] if strengths_list else ALL_TAGS[:2]
            explore = []

        elif phase == "contest_simulation":
            rng = random.Random(state["user_id"])
            primary = rng.sample(ALL_TAGS, min(3, len(ALL_TAGS)))
            remaining = [t for t in ALL_TAGS if t not in primary]
            secondary = rng.sample(remaining, min(1, len(remaining)))
            remaining_after = [t for t in remaining if t not in secondary]
            explore_sample = rng.sample(
                remaining_after,
                min(1, max(0, len(remaining_after))),
            )
            explore = explore_sample if explore_sample else []

        else:
            primary = weak_tags[:3] if weak_tags else ALL_TAGS[:3]
            secondary = ALL_TAGS[3:5]
            explore = []

        state["targets"] = {
            "phase": phase,
            "primary": primary,
            "secondary": secondary,
            "explore": explore,
        }
        state["errors"] = state.get("errors", [])
        return state

    # ================================================================
    # Node: calc_curve
    # ================================================================

    @staticmethod
    def _calc_curve(state: TrainingState) -> TrainingState:
        """Generate ZPD difficulty curve per phase (spec §3.4).

        Returns `difficulty_curve`: list of target difficulty per day.
        Shapes per phase:
          - template_consolidation : flat low, d ~ [2, 4]
          - topic_breakthrough     : ramp from low to mid, d ~ [2, 6]
          - integrated_practice    : gentle oscillating, d ~ [4, 8]
          - contest_simulation     : contest mimic with high plateau, d ~ [5, 10]
        """
        phase = state["profile"].get("phase", "topic_breakthrough")
        plan_days = state.get("plan_days", 7)
        daily_target = state.get("daily_target", 5)

        if phase == "template_consolidation":
            # Flat low: oscillate gently between 2.0 and 4.0
            curve = [2.5 + 0.8 * math.sin((i / plan_days) * 2 * math.pi) for i in range(plan_days)]

        elif phase == "topic_breakthrough":
            # Ramp from 2.0 up to 6.0
            curve = [2.0 + (i / max(plan_days - 1, 1)) * 4.0 for i in range(plan_days)]

        elif phase == "integrated_practice":
            # Gentle oscillating [4, 8]
            center = 6.0
            amplitude = 2.0
            curve = [center + amplitude * math.sin((i / max(plan_days - 1, 1)) * math.pi) for i in range(plan_days)]

        elif phase == "contest_simulation":
            # Contest mimic: ramp up then high plateau
            half = plan_days // 2
            curve = []
            for i in range(plan_days):
                if i < half:
                    val = 5.0 + (i / max(half - 1, 1)) * 3.0
                else:
                    val = 7.0 + 1.5 * math.sin((i - half) / max(plan_days - half - 1, 1) * math.pi)
                curve.append(val)

        else:
            # Default linear ramp
            curve = [3.0 + (i / max(plan_days - 1, 1)) * 4.0 for i in range(plan_days)]

        # Clamp to [1, 10]
        curve = [max(1.0, min(10.0, round(d, 2))) for d in curve]

        state["difficulty_curve"] = curve
        state["errors"] = state.get("errors", [])
        return state

    # ================================================================
    # Node: retrieve_problems
    # ================================================================

    def _retrieve_problems(self, state: TrainingState) -> TrainingState:
        """Mock vector+tag+similar retrieval with 5-dimension scoring.

        Produces a ranked list of candidate problems stored in
        state["candidate_problems"], each including a `_score` dict with
        per-dimension breakdown.
        """
        targets = state.get("targets", {})
        curve = state.get("difficulty_curve", [5.0] * 7)
        all_primary = targets.get("primary", [])
        all_secondary = targets.get("secondary", [])
        all_explore = targets.get("explore", [])
        all_target_tags = all_primary + all_secondary + all_explore

        problem_pool = self.db.get_all_problems()
        user_id = state["user_id"]

        # Generate mock problems if pool is empty
        if not problem_pool:
            problem_pool = _generate_mock_problems(200)

        scored: List[Dict[str, Any]] = []
        for prob in problem_pool:
            p_tags = prob.get("tags", [])
            p_diff = prob.get("difficulty", 5.0)
            p_vec = prob.get("vector", [0.0] * 10)
            solved_by_me = user_id in prob.get("solved_by", [])

            # For scoring, use average curve difficulty as target
            avg_target_diff = sum(curve) / len(curve) if curve else 5.0

            # Check dependencies
            deps = prob.get("dependencies", [])
            dep_satisfied = all(
                d in _get_user_known_tags(state)
                for d in deps
            )

            scores = compute_problem_score(
                problem_tags=p_tags,
                target_tags=all_target_tags,
                problem_diff=p_diff,
                target_diff=avg_target_diff,
                problem_vector=p_vec,
                target_vector=_mock_target_vector(all_target_tags),
                previously_solved=solved_by_me,
                dep_satisfied=dep_satisfied,
            )

            scored.append({
                **prob,
                "_score": scores,
            })

        # Sort by total score descending
        scored.sort(key=lambda p: p["_score"]["total"], reverse=True)

        state["candidate_problems"] = scored
        state["errors"] = state.get("errors", [])
        return state

    # ================================================================
    # Node: llm_arrange
    # ================================================================

    def _llm_arrange(self, state: TrainingState) -> TrainingState:
        """Use LLM to arrange a weekly plan with 2+2+1 daily pattern.

        2 primary + 2 secondary + 1 explore per day, fitted to the difficulty
        curve and candidate problem pool.
        """
        plan_days = state.get("plan_days", 7)
        daily_target = state.get("daily_target", 5)
        targets = state.get("targets", {})
        curve = state.get("difficulty_curve", [5.0] * plan_days)
        candidates = state.get("candidate_problems", [])

        # If LLM is unavailable, fall through to rule-based arrangement
        if self.llm is not None:
            try:
                return self._llm_arrange_with_llm(state)
            except Exception as exc:
                state["errors"] = list(state.get("errors", [])) + [
                    f"LLM arrange failed, falling back to rule-based: {exc}"
                ]

        return self._rule_based_arrange(state)

    def _llm_arrange_with_llm(self, state: TrainingState) -> TrainingState:
        """Arrange plan via LLM invocation."""
        plan_days = state.get("plan_days", 7)
        targets = state.get("targets", {})
        curve = state.get("difficulty_curve", [5.0] * plan_days)
        candidates = state.get("candidate_problems", [])

        # Prepare a concise candidate summary for the LLM
        top_n = min(len(candidates), 60)
        cand_summary_lines: List[str] = []
        for i, c in enumerate(candidates[:top_n]):
            score_total = c.get("_score", {}).get("total", 0.0)
            cand_summary_lines.append(
                f"  [{i}] id={c.get('id','?')}, tags={c.get('tags',[])}, "
                f"diff={c.get('difficulty',0):.1f}, score={score_total:.3f}"
            )
        cand_summary = "\n".join(cand_summary_lines)

        prompt = (
            "你是一位 ACM 算法竞赛教练。请根据以下信息，为学员制定一份为期 "
            f"{plan_days} 天的周训练计划。\n\n"
            f"训练阶段: {targets.get('phase', 'unknown')}\n"
            f"每日题目数: {state.get('daily_target', 5)}\n"
            f"每日模式: 2 道主线题(primary) + 2 道辅线题(secondary) + 1 道探索题(explore)\n"
            f"主线标签: {targets.get('primary', [])}\n"
            f"辅线标签: {targets.get('secondary', [])}\n"
            f"探索标签: {targets.get('explore', [])}\n"
            f"每日目标难度曲线: {curve}\n\n"
            f"候选题目池（前{top_n}道，按综合得分排序）:\n{cand_summary}\n\n"
            "请输出以下 JSON 格式（不要加代码块标记）:\n"
            '{"days": [{"day": 1, "primary": [id1, id2], "secondary": [id3, id4], '
            '"explore": [id5], "target_difficulty": 3.5}, ...], '
            '"phase": "topic_breakthrough", "total_problems": 35}'
        )

        response = self.llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        text = text.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[: text.rfind("```")].strip()

        import json as _json
        try:
            plan_json = _json.loads(text)
        except _json.JSONDecodeError:
            # Fallback: extract JSON from text
            import re as _re
            match = _re.search(r"\{.*\}", text, _re.DOTALL)
            if match:
                plan_json = _json.loads(match.group())
            else:
                raise

        state["weekly_plan"] = plan_json
        state["errors"] = state.get("errors", [])
        return state

    def _rule_based_arrange(self, state: TrainingState) -> TrainingState:
        """Arrange plan with rule-based fallback when LLM is unavailable."""
        plan_days = state.get("plan_days", 7)
        daily_target = state.get("daily_target", 5)
        targets = state.get("targets", {})
        curve = state.get("difficulty_curve", [5.0] * plan_days)
        candidates = state.get("candidate_problems", [])

        days: List[Dict[str, Any]] = []
        used_ids: set = set()
        primary_tags = targets.get("primary", [])
        secondary_tags = targets.get("secondary", [])
        explore_tags = targets.get("explore", [])

        def _pick_by_tag(tags: List[str], exclude: set, count: int, target_diff: float) -> List[str]:
            """Pick top-scoring candidates matching given tags, closest to target_diff."""
            if not tags:
                # Fallback: pick any candidate closest to target_diff
                matching = [
                    c for c in candidates
                    if c.get("id") not in exclude
                ]
                matching.sort(
                    key=lambda c: abs(c.get("difficulty", 5.0) - target_diff)
                )
            else:
                matching = [
                    c for c in candidates
                    if c.get("id") not in exclude
                    and any(t in c.get("tags", []) for t in tags)
                ]
                # Sort by composite: score (if available) + diff proximity
                def _sort_key(c: Dict[str, Any]) -> tuple:
                    score_total = c.get("_score", {}).get("total", 0.0)
                    diff_delta = abs(c.get("difficulty", 5.0) - target_diff)
                    return (-score_total, diff_delta)

                matching.sort(key=_sort_key)

            picked: List[str] = []
            for c in matching:
                if len(picked) >= count:
                    break
                picked.append(str(c.get("id", "")))
            return picked

        for day_i in range(plan_days):
            td = curve[day_i] if day_i < len(curve) else curve[-1]
            primary = _pick_by_tag(primary_tags, used_ids, 2, td)
            for pid in primary:
                used_ids.add(pid)
            secondary = _pick_by_tag(secondary_tags, used_ids, 2, td)
            for sid in secondary:
                used_ids.add(sid)
            explore = _pick_by_tag(explore_tags, used_ids, 1, td)
            for eid in explore:
                used_ids.add(eid)

            # Pad if we don't have enough candidates
            remaining_slots = daily_target - len(primary) - len(secondary) - len(explore)
            if remaining_slots > 0:
                fallback = _pick_by_tag(primary_tags + secondary_tags, used_ids, remaining_slots, td)
                secondary.extend(fallback)
                for fid in fallback:
                    used_ids.add(fid)

            days.append({
                "day": day_i + 1,
                "primary": primary,
                "secondary": secondary,
                "explore": explore,
                "target_difficulty": round(td, 2),
            })

        total_problems = sum(
            len(d["primary"]) + len(d["secondary"]) + len(d["explore"])
            for d in days
        )

        state["weekly_plan"] = {
            "days": days,
            "phase": targets.get("phase", "unknown"),
            "total_problems": total_problems,
        }
        state["errors"] = state.get("errors", [])
        return state

    # ================================================================
    # Node: save_plan
    # ================================================================

    def _save_plan(self, state: TrainingState) -> TrainingState:
        """Mock save the training plan to DB."""
        user_id = state["user_id"]
        profile_id = state.get("profile_id", state["user_id"])
        weekly_plan = state.get("weekly_plan", {})

        plan_data: Dict[str, Any] = {
            "profile_id": profile_id,
            "user_id": user_id,
            "plan": weekly_plan,
            "targets": state.get("targets", {}),
            "difficulty_curve": state.get("difficulty_curve", []),
            "candidate_count": len(state.get("candidate_problems", [])),
            "errors": state.get("errors", []),
        }

        self.db.save_plan(user_id, plan_data)
        state["plan_data"] = plan_data
        state["errors"] = state.get("errors", [])
        return state

    # ================================================================
    # Build
    # ================================================================

    def _build(self) -> StateGraph:
        """Compile the LangGraph StateGraph with MemorySaver checkpointer."""
        builder = StateGraph(TrainingState)

        builder.add_node("load_profile", self._load_profile)
        builder.add_node("determine_phase", self._determine_phase)
        builder.add_node("select_targets", self._select_targets)
        builder.add_node("calc_curve", self._calc_curve)
        builder.add_node("retrieve_problems", self._retrieve_problems)
        builder.add_node("llm_arrange", self._llm_arrange)
        builder.add_node("save_plan", self._save_plan)

        builder.set_entry_point("load_profile")
        builder.add_edge("load_profile", "determine_phase")
        builder.add_edge("determine_phase", "select_targets")
        builder.add_edge("select_targets", "calc_curve")
        builder.add_edge("calc_curve", "retrieve_problems")
        builder.add_edge("retrieve_problems", "llm_arrange")
        builder.add_edge("llm_arrange", "save_plan")
        builder.add_edge("save_plan", END)

        return builder.compile(checkpointer=MemorySaver())


# ============================================================
# Helpers
# ============================================================

def _get_user_known_tags(state: TrainingState) -> set:
    """Extract tags the user is known to have covered from profile."""
    profile = state.get("profile", {})
    skill_radar = profile.get("skill_radar", {})
    known = set()
    for cat, cov in skill_radar.items():
        if cov > 0.0:
            known.add(cat)
    # Also include tags from completed records
    for s in profile.get("strengths", []):
        known.add(s.get("category", ""))
    return known


def _mock_target_vector(tags: List[str]) -> List[float]:
    """Generate a mock 10-dim vector from tag set (deterministic hash)."""
    import hashlib
    vec = [0.0] * 10
    for tag in sorted(tags):
        h = int(hashlib.md5(tag.encode()).hexdigest()[:8], 16)
        rng = random.Random(h)
        for i in range(10):
            vec[i] += rng.uniform(0, 1)
    # Normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _generate_mock_problems(n: int = 200) -> List[Dict[str, Any]]:
    """Generate a mock problem pool for testing."""
    import hashlib
    problems: List[Dict[str, Any]] = []
    rng = random.Random(42)  # deterministic seed
    for i in range(n):
        h = int(hashlib.md5(f"prob_{i}".encode()).hexdigest()[:8], 16)
        tag_rng = random.Random(h)
        n_tags = tag_rng.randint(1, 5)
        tags = tag_rng.sample(ALL_TAGS, min(n_tags, len(ALL_TAGS)))
        vec = [rng.uniform(-1, 1) for _ in range(10)]
        norm = math.sqrt(sum(v * v for v in vec))
        vec = [v / norm for v in vec] if norm > 0 else [0.0] * 10
        deps_pool = [
            d for t in tags for d in DEPENDENCY_GRAPH.get(t, [])
        ][:2]
        problems.append({
            "id": f"prob_{i:04d}",
            "title": f"Mock Problem {i}",
            "tags": tags,
            "difficulty": round(rng.uniform(1.0, 10.0), 1),
            "vector": vec,
            "dependencies": deps_pool,
            "solved_by": [f"user_{j}" for j in rng.sample(range(50), min(20, 50))],
        })
    return problems
