"""
ACM Agent 用户能力画像 Agent —— LangGraph StateGraph with MemorySaver.

Nodes: load_user_data → aggregate_stats → calc_6_dims → [llm_summarize | fallback] → END
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.formulas import (
    BASIC_TAGS,
    calc_category_coverage,
    calc_ceiling,
    calc_coverage,
    calc_efficiency,
    calc_momentum,
    calc_overall_score,
    calc_proficiency,
    classify_style,
)
from agents.taxonomy import ALL_TAGS, CATEGORY_MAP


# ============================================================
# State
# ============================================================

class ProfileState(TypedDict):
    user_id: str
    platforms: List[str]
    raw_records: List[Dict[str, Any]]
    daily_stats: List[Dict[str, Any]]
    platform_profiles: Dict[str, Dict[str, Any]]
    aggregated_stats: Dict[str, Any]
    analysis: Dict[str, Any]
    profile_data: Dict[str, Any]
    errors: List[str]


# ============================================================
# DB mock (in-memory for construction)
# ============================================================

class _Database:
    """In-memory database for user problem-solving records and daily stats."""

    def __init__(self) -> None:
        # ---- records: each entry is a problem-solving record ----
        self._records: List[Dict[str, Any]] = []
        # ---- daily_stats: aggregated per-day AC counts ----
        self._daily_stats: List[Dict[str, Any]] = []
        # ---- platform_profiles: per-platform metadata ----
        self._platform_profiles: Dict[str, Dict[str, Any]] = {}

    def add_records(self, records: List[Dict[str, Any]]) -> None:
        self._records.extend(records)

    def add_daily_stats(self, stats: List[Dict[str, Any]]) -> None:
        self._daily_stats.extend(stats)

    def set_platform_profile(self, platform: str, profile: Dict[str, Any]) -> None:
        self._platform_profiles[platform] = profile

    def get_records(self, user_id: str) -> List[Dict[str, Any]]:
        return [r for r in self._records if r.get("user_id") == user_id]

    def get_daily_stats(self, user_id: str) -> List[Dict[str, Any]]:
        return [s for s in self._daily_stats if s.get("user_id") == user_id]

    def get_platform_profiles(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        return dict(self._platform_profiles)


# Default DB instance used when none is provided
DEFAULT_DB = _Database()


# ============================================================
# Agent
# ============================================================

class ProfileAgent:
    """LangGraph agent that builds a 6-dimension user ability profile."""

    def __init__(self, db: Optional[_Database] = None, llm: Any = None) -> None:
        self.db = db or DEFAULT_DB
        if llm is None:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(model="deepseek-chat")
        else:
            self.llm = llm
        self.graph = self._build()

    # ----- node: load_user_data ----------------------------------------

    def _load_user_data(self, state: ProfileState) -> ProfileState:
        """Query records, daily_stats, and platform_profiles from DB mock."""
        user_id = state["user_id"]
        state["raw_records"] = self.db.get_records(user_id)
        state["daily_stats"] = self.db.get_daily_stats(user_id)
        state["platform_profiles"] = self.db.get_platform_profiles(user_id)
        state["platforms"] = sorted(state["platform_profiles"].keys())
        state["errors"] = state.get("errors", [])
        return state

    # ----- node: aggregate_stats ---------------------------------------

    @staticmethod
    def _aggregate_stats(state: ProfileState) -> ProfileState:
        """Compute by_tag, by_difficulty, and by_platform aggregations."""
        records = state["raw_records"]

        if not records:
            state["aggregated_stats"] = {
                "total_records": 0,
                "ac_count": 0,
                "unique_tags": 0,
                "avg_difficulty": 0.0,
                "by_tag": {},
                "by_difficulty": {},
                "by_platform": {},
                "daily_ac_count": 0,
                "first_ac_rate": 0.0,
                "avg_retries": 0.0,
                "top_tags": {},
            }
            return state

        # Basic counts
        ac = [r for r in records if r.get("status") == "AC"]
        ac_count = len(ac)
        total = len(records)

        # Unique tags across all records
        user_tags: Set[str] = set()
        for r in records:
            for t in r.get("tags", []):
                user_tags.add(t)

        # by_tag aggregation
        by_tag: Dict[str, int] = {}
        for r in records:
            for t in r.get("tags", []):
                by_tag[t] = by_tag.get(t, 0) + 1

        # by_difficulty
        by_difficulty: Dict[str, int] = {}
        for r in records:
            d = str(r.get("difficulty", 0))
            by_difficulty[d] = by_difficulty.get(d, 0) + 1

        # by_platform
        by_platform: Dict[str, int] = {}
        for r in records:
            p = r.get("platform", "unknown")
            by_platform[p] = by_platform.get(p, 0) + 1

        # avg difficulty
        diffs = [r.get("difficulty", 0) for r in records]
        avg_diff = sum(diffs) / len(diffs) if diffs else 0.0

        # first_ac_rate & avg_retries
        first_ac_count = sum(1 for r in records if r.get("first_ac", False))
        first_ac_rate = first_ac_count / total if total else 0.0
        avg_retries = sum(r.get("retries", 0) for r in records) / total if total else 0.0

        # daily AC total from daily_stats
        daily_ac = sum(s.get("ac_count", 0) for s in state.get("daily_stats", []))

        # top_tags (top 5 by frequency)
        top_tags = dict(sorted(by_tag.items(), key=lambda x: -x[1])[:5])

        state["aggregated_stats"] = {
            "total_records": total,
            "ac_count": ac_count,
            "unique_tags": len(user_tags),
            "avg_difficulty": avg_diff,
            "by_tag": by_tag,
            "by_difficulty": by_difficulty,
            "by_platform": by_platform,
            "daily_ac_count": daily_ac,
            "first_ac_rate": first_ac_rate,
            "avg_retries": avg_retries,
            "top_tags": top_tags,
        }
        state["errors"] = state.get("errors", [])
        return state

    # ----- node: calc_6_dims -------------------------------------------

    @staticmethod
    def _calc_6_dims(state: ProfileState) -> ProfileState:
        """Compute all 6 dimensions using formulas.py functions.

        Populates profile_data with:
          - dimensions: {coverage, proficiency, ceiling, efficiency, momentum, overall}
          - style, strengths, weaknesses, skill_radar
        """
        records = state["raw_records"]
        daily_stats = state.get("daily_stats", [])
        stats = state.get("aggregated_stats", {})

        # Gather user's actual tags from records
        user_tags: Set[str] = set()
        for r in records:
            for t in r.get("tags", []):
                user_tags.add(t)

        all_tags_set = set(ALL_TAGS)

        # Dimension 1: Coverage
        coverage = calc_coverage(user_tags, all_tags_set)

        # Dimension 2: Proficiency (aggregated)
        ac_count = stats.get("ac_count", 0)
        total = stats.get("total_records", 0)
        avg_diff = stats.get("avg_difficulty", 0.0)
        # days_since_last: compute from newest record's timestamp
        days_since_last = 0.0
        if records:
            timestamps = [r.get("timestamp", 0) for r in records]
            latest = max(timestamps)
            if latest > 0:
                days_since_last = (86400 * 30) / 86400  # placeholder ~30 days
                # More realistic: derive from actual recency
                try:
                    import time
                    now = time.time()
                    days_since_last = max(0.0, (now - latest) / 86400.0)
                except Exception:
                    days_since_last = 7.0

        proficiency = calc_proficiency(ac_count, total, avg_diff, days_since_last)

        # Dimension 3: Ceiling
        ceiling = calc_ceiling(records)

        # Dimension 4: Efficiency
        efficiency = calc_efficiency(records)

        # Dimension 5: Momentum
        momentum = calc_momentum(daily_stats)

        # Style classification
        unique_tags = stats.get("unique_tags", 0)
        top_tags = stats.get("top_tags", {})
        total_solved = ac_count
        top3_total = sum(list(top_tags.values())[:3]) if top_tags else 0
        top3_concentration = top3_total / total_solved if total_solved > 0 else 0.0

        style = classify_style(
            total_solved=total_solved,
            unique_tags=unique_tags,
            avg_proficiency=proficiency,
            top3_concentration=top3_concentration,
            avg_difficulty=avg_diff,
        )

        # Dimension 6: Overall score
        overall = calc_overall_score(coverage, proficiency, ceiling, efficiency, style, momentum)

        # Strengths & Weaknesses (top 5 each)
        # Strength: highest-coverage categories; Weakness: lowest-coverage categories
        # calc_category_coverage expects Dict[str, Set[str]], but CATEGORY_MAP is Dict[str, List[str]]
        taxonomy_sets = {k: set(v) for k, v in CATEGORY_MAP.items()} if CATEGORY_MAP else {}
        cat_cov = calc_category_coverage(user_tags, taxonomy_sets) if taxonomy_sets else {}
        sorted_cats = sorted(cat_cov.items(), key=lambda x: x[1], reverse=True)
        strengths: List[Dict[str, Any]] = []
        weaknesses: List[Dict[str, Any]] = []
        if sorted_cats:
            strengths = [
                {"category": c, "coverage": v}
                for c, v in sorted_cats[:5]
                if v > 0
            ]
            weaknesses = [
                {"category": c, "coverage": v}
                for c, v in sorted_cats[-5:]
                if v < 1.0
            ]
            # Reverse so weakest is first
            weaknesses = list(reversed(weaknesses))

        # Skill radar data: per-category coverage ratio
        skill_radar = {c: v for c, v in cat_cov.items()}

        state["profile_data"] = {
            "dimensions": {
                "coverage": round(coverage, 4),
                "proficiency": round(proficiency, 4),
                "ceiling": round(ceiling, 4),
                "efficiency": round(efficiency, 4),
                "momentum": round(momentum, 4),
                "overall": round(overall, 4),
            },
            "style": style,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "skill_radar": skill_radar,
        }
        state["errors"] = state.get("errors", [])
        return state

    # ----- node: llm_summarize -----------------------------------------

    def _llm_summarize(self, state: ProfileState) -> ProfileState:
        """Generate a natural-language summary of the user profile via LLM."""
        profile = state.get("profile_data", {})
        dims = profile.get("dimensions", {})
        records = state["raw_records"]
        stats = state.get("aggregated_stats", {})

        prompt = (
            "你是一位 ACM 算法竞赛教练。请根据以下用户画像数据，生成一段 150 字以内的中文总结，"
            "描述该用户的算法能力概况，包含优势和待提升方向。\n\n"
            f"用户 ID: {state['user_id']}\n"
            f"总提交次数: {stats.get('total_records', 0)}\n"
            f"AC 次数: {stats.get('ac_count', 0)}\n"
            f"六维能力值: {dims}\n"
            f"解题风格: {profile.get('style', 'unknown')}\n"
            f"优势领域: {[s['category'] for s in profile.get('strengths', [])]}\n"
            f"薄弱领域: {[w['category'] for w in profile.get('weaknesses', [])]}\n"
            "\n请直接输出总结段落，不要加前缀或后缀。"
        )

        try:
            response = self.llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            state["analysis"] = {"summary_text": text.strip()}
        except Exception as exc:
            state["errors"] = list(state.get("errors", [])) + [
                f"LLM summarization failed: {exc}"
            ]
            state["analysis"] = {"summary_text": "（LLM 总结生成失败，请检查日志）"}

        return state

    # ----- node: fallback ----------------------------------------------

    @staticmethod
    def _fallback(state: ProfileState) -> ProfileState:
        """Set a fallback summary when there are too few records."""
        state["analysis"] = {
            "summary_text": (
                f"用户 {state['user_id']} 的答题记录不足（仅 {len(state['raw_records'])} 条），"
                "暂无法生成完整的六维能力画像。请继续刷题以积累足够的数据。"
            ),
        }
        state["errors"] = state.get("errors", [])
        return state

    # ----- routing -----------------------------------------------------

    @staticmethod
    def _route_after_calc(state: ProfileState) -> str:
        """If fewer than 10 raw_records, route to fallback; else llm_summarize."""
        if len(state.get("raw_records", [])) < 10:
            return "fallback"
        return "llm_summarize"

    # ----- build -------------------------------------------------------

    def _build(self) -> StateGraph:
        """Compile the LangGraph StateGraph with MemorySaver checkpointer."""
        builder = StateGraph(ProfileState)

        builder.add_node("load_user_data", self._load_user_data)
        builder.add_node("aggregate_stats", self._aggregate_stats)
        builder.add_node("calc_6_dims", self._calc_6_dims)
        builder.add_node("llm_summarize", self._llm_summarize)
        builder.add_node("fallback", self._fallback)

        builder.set_entry_point("load_user_data")
        builder.add_edge("load_user_data", "aggregate_stats")
        builder.add_edge("aggregate_stats", "calc_6_dims")

        builder.add_conditional_edges(
            "calc_6_dims",
            self._route_after_calc,
            {
                "llm_summarize": "llm_summarize",
                "fallback": "fallback",
            },
        )

        builder.add_edge("llm_summarize", END)
        builder.add_edge("fallback", END)

        return builder.compile(checkpointer=MemorySaver())
