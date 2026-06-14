"""
Comprehensive tests for TrainingAgent — phase classification, target selection,
difficulty curve, problem scoring, LLM arrangement, graph compilation, plan_data output.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.training_agent import (
    DEFAULT_TRAINING_DB,
    TrainingAgent,
    TrainingState,
    _TrainingDatabase,
    _generate_mock_problems,
    _get_user_known_tags,
    _mock_target_vector,
    compute_problem_score,
    _gaussian_diff_match,
)
from agents.taxonomy import ALL_TAGS, BASIC_TAGS


# ============================================================
# Helpers
# ============================================================

def _make_profile(
    *,
    coverage: float = 0.5,
    proficiency: float = 0.5,
    ceiling: float = 5.0,
    efficiency: float = 0.5,
    momentum: float = 0.0,
    overall: float = 0.5,
    strengths: List[Dict[str, Any]] | None = None,
    weaknesses: List[Dict[str, Any]] | None = None,
    weak_tags_ranked: List[str] | None = None,
) -> Dict[str, Any]:
    """Build a minimal test profile dict."""
    return {
        "profile_id": "test_profile",
        "dimensions": {
            "coverage": coverage,
            "proficiency": proficiency,
            "ceiling": ceiling,
            "efficiency": efficiency,
            "momentum": momentum,
            "overall": overall,
        },
        "strengths": strengths or [],
        "weaknesses": weaknesses or [],
        "weak_tags_ranked": weak_tags_ranked or [],
        "skill_radar": {},
    }


def _make_state(
    user_id: str = "u1",
    profile: Dict[str, Any] | None = None,
    plan_days: int = 7,
    daily_target: int = 5,
) -> TrainingState:
    """Build a minimal TrainingState for testing."""
    p = profile or _make_profile()
    return {
        "user_id": user_id,
        "profile_id": p.get("profile_id", "unknown"),
        "plan_days": plan_days,
        "daily_target": daily_target,
        "profile": p,
        "weak_tags_ranked": p.get("weak_tags_ranked", []),
        "candidate_problems": [],
        "weekly_plan": {},
        "difficulty_curve": [],
        "targets": {},
        "plan_data": {},
        "errors": [],
    }


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def empty_db() -> _TrainingDatabase:
    return _TrainingDatabase()


@pytest.fixture
def db_with_profile() -> _TrainingDatabase:
    db = _TrainingDatabase()
    db.set_profile("u1", _make_profile(
        coverage=0.5,
        ceiling=5.0,
        efficiency=0.6,
        overall=0.55,
        weak_tags_ranked=["prefix_sum", "two_pointers", "binary_search"],
    ))
    db.add_problems(_generate_mock_problems(50))
    return db


@pytest.fixture
def agent(db_with_profile: _TrainingDatabase) -> TrainingAgent:
    return TrainingAgent(db=db_with_profile, llm=None)


# ============================================================
# 1. Phase Classification Tests (all 4 phases)
# ============================================================

class TestDeterminePhase:
    """Test determine_phase node for each of the 4 phases."""

    def test_template_consolidation_by_low_coverage(self, agent: TrainingAgent):
        """Phase = template_consolidation when coverage < 0.3."""
        profile = _make_profile(coverage=0.2, ceiling=5.0, efficiency=0.5, overall=0.3)
        state = _make_state(profile=profile)
        result = agent._determine_phase(state)
        assert result["profile"]["phase"] == "template_consolidation"

    def test_template_consolidation_by_weak_basics(self, agent: TrainingAgent):
        """Phase = template_consolidation when >= 3 weak basic tags."""
        profile = _make_profile(
            coverage=0.5,
            ceiling=5.0,
            efficiency=0.5,
            overall=0.5,
            weak_tags_ranked=["prefix_sum", "two_pointers", "binary_search", "sliding_window"],
        )
        state = _make_state(profile=profile)
        result = agent._determine_phase(state)
        # 4 of these are in BASIC_TAGS → >= 3 → template_consolidation
        assert result["profile"]["phase"] == "template_consolidation"

    def test_topic_breakthrough_default(self, agent: TrainingAgent):
        """Phase = topic_breakthrough by default when no other rules match."""
        profile = _make_profile(
            coverage=0.5,
            ceiling=4.0,  # < 6 → not integrated; < 8 → not contest
            efficiency=0.5,
            overall=0.5,
            strengths=[{"category": "math", "coverage": 0.9}],
            weaknesses=[{"category": "dp", "coverage": 0.1}],  # gap=0.8 > 0.5
            weak_tags_ranked=["dp"],
        )
        state = _make_state(profile=profile)
        result = agent._determine_phase(state)
        assert result["profile"]["phase"] == "topic_breakthrough"

    def test_topic_breakthrough_clear_weakness(self, agent: TrainingAgent):
        """Phase = topic_breakthrough when has clear weakness (gap > 0.5) and ceiling < 7."""
        profile = _make_profile(
            coverage=0.4,
            ceiling=5.0,
            efficiency=0.4,  # < 0.5 → not integrated
            overall=0.4,
            strengths=[{"category": "data_struct", "coverage": 0.95}],
            weaknesses=[{"category": "dp", "coverage": 0.10}],  # gap=0.85 > 0.5
            weak_tags_ranked=["linear_dp"],
        )
        state = _make_state(profile=profile)
        result = agent._determine_phase(state)
        assert result["profile"]["phase"] == "topic_breakthrough"

    def test_integrated_practice(self, agent: TrainingAgent):
        """Phase = integrated_practice when ceiling >= 6 and efficiency >= 0.5."""
        profile = _make_profile(
            coverage=0.5,
            ceiling=6.5,
            efficiency=0.6,
            overall=0.6,
        )
        state = _make_state(profile=profile)
        result = agent._determine_phase(state)
        assert result["profile"]["phase"] == "integrated_practice"

    def test_contest_simulation(self, agent: TrainingAgent):
        """Phase = contest_simulation when ceiling >= 8 and overall >= 0.7."""
        profile = _make_profile(
            coverage=0.7,
            ceiling=8.5,
            efficiency=0.7,
            overall=0.75,
        )
        state = _make_state(profile=profile)
        result = agent._determine_phase(state)
        assert result["profile"]["phase"] == "contest_simulation"

    def test_contest_simulation_takes_priority_over_integrated(self, agent: TrainingAgent):
        """contest_simulation checked before integrated_practice."""
        profile = _make_profile(
            coverage=0.8,
            ceiling=9.0,
            efficiency=0.8,
            overall=0.85,
        )
        state = _make_state(profile=profile)
        result = agent._determine_phase(state)
        assert result["profile"]["phase"] == "contest_simulation"

    def test_topic_breakthrough_fallback_else(self, agent: TrainingAgent):
        """Phase defaults to topic_breakthrough when no other rules match (high ceiling, no clear weakness, low efficiency)."""
        profile = _make_profile(
            coverage=0.5,
            ceiling=7.5,    # >= 6 but efficiency < 0.5 → not integrated; < 8 → not contest
            efficiency=0.3,
            overall=0.5,
            strengths=[],
            weaknesses=[],  # no clear weakness gap
            weak_tags_ranked=[],
        )
        state = _make_state(profile=profile)
        result = agent._determine_phase(state)
        assert result["profile"]["phase"] == "topic_breakthrough"


# ============================================================
# 2. select_targets Structure Tests
# ============================================================

class TestSelectTargets:
    """Test select_targets returns correct structure."""

    def test_returns_correct_keys(self, agent: TrainingAgent):
        """targets dict must contain phase, primary, secondary, explore."""
        state = _make_state()
        state["profile"]["phase"] = "topic_breakthrough"
        state["weak_tags_ranked"] = ["dp", "graph", "string"]
        result = agent._select_targets(state)
        targets = result["targets"]
        assert "phase" in targets
        assert "primary" in targets
        assert "secondary" in targets
        assert "explore" in targets

    def test_primary_is_list(self, agent: TrainingAgent):
        state = _make_state()
        state["profile"]["phase"] = "topic_breakthrough"
        state["weak_tags_ranked"] = ["dp", "graph"]
        result = agent._select_targets(state)
        assert isinstance(result["targets"]["primary"], list)

    def test_secondary_is_list(self, agent: TrainingAgent):
        state = _make_state()
        state["profile"]["phase"] = "topic_breakthrough"
        state["weak_tags_ranked"] = ["dp", "graph"]
        result = agent._select_targets(state)
        assert isinstance(result["targets"]["secondary"], list)

    def test_explore_is_list(self, agent: TrainingAgent):
        state = _make_state()
        state["profile"]["phase"] = "topic_breakthrough"
        state["weak_tags_ranked"] = ["dp", "graph"]
        result = agent._select_targets(state)
        assert isinstance(result["targets"]["explore"], list)

    def test_template_consolidation_primary_basics(self, agent: TrainingAgent):
        """template_consolidation primary tags should be from BASIC_TAGS."""
        state = _make_state()
        state["profile"]["phase"] = "template_consolidation"
        state["weak_tags_ranked"] = ["prefix_sum", "two_pointers", "binary_search"]
        result = agent._select_targets(state)
        primary = result["targets"]["primary"]
        for tag in primary:
            assert tag in BASIC_TAGS, f"primary tag '{tag}' not in BASIC_TAGS"

    def test_topic_breakthrough_primary_weak_tags(self, agent: TrainingAgent):
        """topic_breakthrough primary should be weak tags."""
        state = _make_state()
        state["profile"]["phase"] = "topic_breakthrough"
        state["weak_tags_ranked"] = ["suffix_array", "max_flow", "convex_hull"]
        result = agent._select_targets(state)
        primary = result["targets"]["primary"]
        assert primary == ["suffix_array", "max_flow", "convex_hull"]

    def test_integrated_practice_uses_weaknesses(self, agent: TrainingAgent):
        state = _make_state(profile=_make_profile(
            coverage=0.5, ceiling=6.0, efficiency=0.6,
            weaknesses=[{"category": "dp", "coverage": 0.1}],
            weak_tags_ranked=["dp"],
        ))
        state["profile"]["phase"] = "integrated_practice"
        result = agent._select_targets(state)
        assert len(result["targets"]["primary"]) >= 1

    def test_contest_simulation_primary_from_all_tags(self, agent: TrainingAgent):
        state = _make_state()
        state["profile"]["phase"] = "contest_simulation"
        result = agent._select_targets(state)
        primary = result["targets"]["primary"]
        assert len(primary) == 3
        for tag in primary:
            assert tag in ALL_TAGS

    def test_unknown_phase_fallback(self, agent: TrainingAgent):
        """When phase is an unrecognized value, select_targets should fallback gracefully."""
        state = _make_state()
        state["profile"]["phase"] = "nonexistent_phase"
        state["weak_tags_ranked"] = ["dp", "graph", "string"]
        result = agent._select_targets(state)
        targets = result["targets"]
        assert "primary" in targets
        assert "secondary" in targets
        assert len(targets["primary"]) > 0


# ============================================================
# 3. calc_curve Tests (valid difficulty values 1~10)
# ============================================================

class TestCalcCurve:
    """Test calc_curve returns valid difficulty values in [1, 10]."""

    @pytest.mark.parametrize("phase", [
        "template_consolidation",
        "topic_breakthrough",
        "integrated_practice",
        "contest_simulation",
    ])
    def test_curve_values_in_range(self, agent: TrainingAgent, phase: str):
        state = _make_state(plan_days=7)
        state["profile"]["phase"] = phase
        result = agent._calc_curve(state)
        curve = result["difficulty_curve"]
        assert len(curve) == 7
        for d in curve:
            assert 1.0 <= d <= 10.0, f"difficulty {d} out of [1,10] in phase {phase}"

    def test_curve_length_matches_plan_days(self, agent: TrainingAgent):
        for days in [5, 7, 10, 14]:
            state = _make_state(plan_days=days)
            state["profile"]["phase"] = "topic_breakthrough"
            result = agent._calc_curve(state)
            assert len(result["difficulty_curve"]) == days

    def test_template_consolidation_values_low(self, agent: TrainingAgent):
        """template_consolidation curve should be mostly low (<= 4.5)."""
        state = _make_state(plan_days=14)
        state["profile"]["phase"] = "template_consolidation"
        result = agent._calc_curve(state)
        curve = result["difficulty_curve"]
        for d in curve:
            assert d <= 4.0, f"template_consolidation difficulty {d} should be low (<= 4.0)"

    def test_topic_breakthrough_is_monotonic_ramp(self, agent: TrainingAgent):
        """topic_breakthrough should be a non-decreasing ramp."""
        state = _make_state(plan_days=10)
        state["profile"]["phase"] = "topic_breakthrough"
        result = agent._calc_curve(state)
        curve = result["difficulty_curve"]
        for i in range(1, len(curve)):
            assert curve[i] >= curve[i - 1] - 0.01, \
                f"curve not monotonic at index {i}: {curve[i-1]} > {curve[i]}"

    def test_contest_simulation_reaches_high(self, agent: TrainingAgent):
        """contest_simulation should have values >= 7 in latter half."""
        state = _make_state(plan_days=10)
        state["profile"]["phase"] = "contest_simulation"
        result = agent._calc_curve(state)
        curve = result["difficulty_curve"]
        second_half = curve[len(curve) // 2 :]
        assert any(d >= 7.0 for d in second_half), \
            "contest_simulation should reach high difficulty in second half"

    def test_unknown_phase_default_curve(self, agent: TrainingAgent):
        """Unknown phase should produce a default linear ramp curve."""
        state = _make_state(plan_days=5)
        state["profile"]["phase"] = "bogus_phase"
        result = agent._calc_curve(state)
        curve = result["difficulty_curve"]
        assert len(curve) == 5
        for d in curve:
            assert 1.0 <= d <= 10.0


# ============================================================
# 4. Problem Scoring Function Tests
# ============================================================

class TestProblemScoring:
    """Test the 5-dimension compute_problem_score function."""

    def test_perfect_match_score(self):
        """Full overlap in tags, exactly on target diff → high score."""
        scores = compute_problem_score(
            problem_tags=["dp", "graph"],
            target_tags=["dp", "graph"],
            problem_diff=5.0,
            target_diff=5.0,
            problem_vector=[0.5] * 10,
            target_vector=[0.5] * 10,
            previously_solved=False,
            dep_satisfied=True,
        )
        # tag_match=1.0 diff_match=1.0 vec_sim=1.0 novelty=1.0 dep=1.0
        # total = 0.30*1 + 0.25*1 + 0.15*1 + 0.15*1 + 0.15*1 = 1.0
        assert scores["tag_match"] == 1.0
        assert scores["diff_match"] == 1.0
        assert scores["vector_similarity"] == 1.0
        assert scores["novelty"] == 1.0
        assert scores["dependency_satisfied"] == 1.0
        assert scores["total"] == 1.0

    def test_zero_overlap_score(self):
        """No tag overlap, far from target diff, previously solved, deps unmet."""
        scores = compute_problem_score(
            problem_tags=["dfs"],
            target_tags=["dp"],
            problem_diff=1.0,
            target_diff=10.0,
            problem_vector=[1.0] + [0.0] * 9,
            target_vector=[0.0] * 9 + [1.0],
            previously_solved=True,
            dep_satisfied=False,
        )
        assert scores["tag_match"] == 0.0
        assert scores["novelty"] == 0.0
        assert scores["dependency_satisfied"] == 0.2
        assert scores["total"] < 0.3  # should be very low

    def test_novelty_effect(self):
        """Previously solved should knock novelty to 0."""
        scores_new = compute_problem_score(
            problem_tags=["dp"], target_tags=["dp"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[0.5] * 10, target_vector=[0.5] * 10,
            previously_solved=False, dep_satisfied=True,
        )
        scores_old = compute_problem_score(
            problem_tags=["dp"], target_tags=["dp"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[0.5] * 10, target_vector=[0.5] * 10,
            previously_solved=True, dep_satisfied=True,
        )
        assert scores_new["novelty"] == 1.0
        assert scores_old["novelty"] == 0.0
        assert scores_new["total"] > scores_old["total"]

    def test_dependency_score(self):
        """Dependencies met → 1.0, unmet → 0.2."""
        met = compute_problem_score(
            problem_tags=["dp"], target_tags=["dp"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[0.5] * 10, target_vector=[0.5] * 10,
            previously_solved=False, dep_satisfied=True,
        )
        unmet = compute_problem_score(
            problem_tags=["dp"], target_tags=["dp"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[0.5] * 10, target_vector=[0.5] * 10,
            previously_solved=False, dep_satisfied=False,
        )
        assert met["dependency_satisfied"] == 1.0
        assert unmet["dependency_satisfied"] == 0.2
        assert met["total"] > unmet["total"]

    def test_gaussian_diff_match_peak(self):
        """At delta=0, gaussian diff match = 1.0."""
        assert _gaussian_diff_match(5.0, 5.0) == 1.0

    def test_gaussian_diff_match_decay(self):
        """As delta increases, gaussian score decays."""
        s1 = _gaussian_diff_match(5.0, 6.0)  # delta=1
        s2 = _gaussian_diff_match(5.0, 8.0)  # delta=3
        assert 0.5 < s1 < 1.0
        assert s2 < s1

    def test_empty_target_tags(self):
        """When target_tags is empty, tag_match should be 0."""
        scores = compute_problem_score(
            problem_tags=["dp"], target_tags=[],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[0.5] * 10, target_vector=[0.5] * 10,
            previously_solved=False, dep_satisfied=True,
        )
        assert scores["tag_match"] == 0.0

    def test_partial_tag_overlap(self):
        """Partial tag overlap should give Jaccard between 0 and 1."""
        scores = compute_problem_score(
            problem_tags=["dp", "graph"],
            target_tags=["dp", "string"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[0.5] * 10, target_vector=[0.5] * 10,
            previously_solved=False, dep_satisfied=True,
        )
        # intersection=1 (dp), union=3 (dp, graph, string) → 0.333
        assert 0.3 < scores["tag_match"] < 0.4

    def test_total_is_weighted_sum(self):
        """Total = 0.30*tag + 0.25*diff + 0.15*vec + 0.15*novelty + 0.15*dep."""
        scores = compute_problem_score(
            problem_tags=["a"], target_tags=["a"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[1.0] + [0.0] * 9,
            target_vector=[0.0] * 9 + [1.0],
            previously_solved=False, dep_satisfied=False,
        )
        expected = (
            0.30 * scores["tag_match"]
            + 0.25 * scores["diff_match"]
            + 0.15 * scores["vector_similarity"]
            + 0.15 * scores["novelty"]
            + 0.15 * scores["dependency_satisfied"]
        )
        assert abs(scores["total"] - expected) < 1e-9

    def test_empty_vectors(self):
        """Empty or mismatched-length vectors should yield vec_sim=0."""
        scores = compute_problem_score(
            problem_tags=["dp"], target_tags=["dp"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[],
            target_vector=[0.5] * 10,
            previously_solved=False, dep_satisfied=True,
        )
        assert scores["vector_similarity"] == 0.0

    def test_mismatched_vector_lengths(self):
        """Vectors of different lengths should yield vec_sim=0."""
        scores = compute_problem_score(
            problem_tags=["dp"], target_tags=["dp"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[0.5] * 5,
            target_vector=[0.5] * 10,
            previously_solved=False, dep_satisfied=True,
        )
        assert scores["vector_similarity"] == 0.0

    def test_zero_norm_vectors(self):
        """Zero-norm vectors should yield vec_sim=0."""
        scores = compute_problem_score(
            problem_tags=["dp"], target_tags=["dp"],
            problem_diff=5.0, target_diff=5.0,
            problem_vector=[0.0] * 5,
            target_vector=[0.0] * 5,
            previously_solved=False, dep_satisfied=True,
        )
        assert scores["vector_similarity"] == 0.0


# ============================================================
# 5. llm_arrange with mocked LLM
# ============================================================

class TestLLMArrange:
    """Test llm_arrange with and without mocked LLM."""

    @pytest.fixture
    def agent_with_mock_llm(self, db_with_profile: _TrainingDatabase) -> TrainingAgent:
        """Create agent with a mocked LLM that returns a valid plan JSON."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "days": [
                {"day": 1, "primary": ["prob_0001", "prob_0002"],
                 "secondary": ["prob_0003", "prob_0004"],
                 "explore": ["prob_0005"], "target_difficulty": 3.0},
                {"day": 2, "primary": ["prob_0006", "prob_0007"],
                 "secondary": ["prob_0008", "prob_0009"],
                 "explore": ["prob_0010"], "target_difficulty": 4.0},
                {"day": 3, "primary": ["prob_0011", "prob_0012"],
                 "secondary": ["prob_0013", "prob_0014"],
                 "explore": ["prob_0015"], "target_difficulty": 5.0},
            ],
            "phase": "topic_breakthrough",
            "total_problems": 15,
        })
        mock_llm.invoke.return_value = mock_response
        agent = TrainingAgent(db=db_with_profile, llm=mock_llm)
        # Populate candidates
        agent.db.add_problems(_generate_mock_problems(50))
        return agent

    def test_rule_based_arrange_structure(self, agent: TrainingAgent):
        """Rule-based arrange produces correct weekly_plan structure."""
        state = _make_state(plan_days=7, daily_target=5)
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp", "graph"],
            "secondary": ["greedy", "math"],
            "explore": ["string"],
        }
        state["difficulty_curve"] = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 8.0]
        state["candidate_problems"] = _generate_mock_problems(100)

        result = agent._rule_based_arrange(state)
        plan = result["weekly_plan"]

        assert "days" in plan
        assert "phase" in plan
        assert "total_problems" in plan
        assert len(plan["days"]) == 7

    def test_rule_based_arrange_day_structure(self, agent: TrainingAgent):
        """Each day has primary, secondary, explore, target_difficulty."""
        state = _make_state(plan_days=3)
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"],
            "secondary": ["greedy"],
            "explore": ["string"],
        }
        state["difficulty_curve"] = [4.0, 5.0, 6.0]
        state["candidate_problems"] = _generate_mock_problems(80)

        result = agent._rule_based_arrange(state)
        days = result["weekly_plan"]["days"]

        for i, day in enumerate(days):
            assert "day" in day
            assert "primary" in day
            assert "secondary" in day
            assert "explore" in day
            assert "target_difficulty" in day
            assert day["day"] == i + 1
            assert isinstance(day["primary"], list)
            assert isinstance(day["secondary"], list)
            assert isinstance(day["explore"], list)

    def test_mocked_llm_arrange_produces_valid_plan(self, agent_with_mock_llm: TrainingAgent):
        """Mocked LLM should produce a plan that matches the mocked response."""
        state = _make_state(plan_days=3)
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"], "secondary": ["greedy"], "explore": ["string"],
        }
        state["difficulty_curve"] = [3.0, 4.0, 5.0]
        state["candidate_problems"] = _generate_mock_problems(20)

        result = agent_with_mock_llm._llm_arrange(state)
        plan = result["weekly_plan"]
        assert plan["phase"] == "topic_breakthrough"
        assert plan["total_problems"] == 15
        assert len(plan["days"]) == 3

    def test_llm_arrange_falls_back_on_exception(self, agent: TrainingAgent):
        """When LLM raises, it should fall back to rule-based arrange."""
        state = _make_state(plan_days=3)
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"], "secondary": ["greedy"], "explore": ["string"],
        }
        state["difficulty_curve"] = [3.0, 4.0, 5.0]
        state["candidate_problems"] = _generate_mock_problems(50)

        # agent was created with llm=None → _llm_arrange goes straight to rule-based
        result = agent._llm_arrange(state)
        assert "days" in result["weekly_plan"]
        assert len(result["weekly_plan"]["days"]) == 3

    def test_llm_arrange_error_triggers_fallback(self, db_with_profile: _TrainingDatabase):
        """When LLM.invoke raises, the error is recorded and fallback used."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM down")
        agent_broken = TrainingAgent(db=db_with_profile, llm=mock_llm)
        agent_broken.db.add_problems(_generate_mock_problems(50))

        state = _make_state(plan_days=3)
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"], "secondary": ["greedy"], "explore": ["string"],
        }
        state["difficulty_curve"] = [3.0, 4.0, 5.0]
        state["candidate_problems"] = _generate_mock_problems(50)

        result = agent_broken._llm_arrange(state)
        assert "days" in result["weekly_plan"]
        assert len(result["errors"]) > 0
        assert "LLM arrange failed" in result["errors"][0]

    def test_llm_arrange_markdown_code_fence(self, db_with_profile: _TrainingDatabase):
        """When LLM returns JSON wrapped in markdown code fences, strip them."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "```json\n" + json.dumps({
            "days": [
                {"day": 1, "primary": ["p1"], "secondary": ["s1", "s2"],
                 "explore": ["e1"], "target_difficulty": 3.0},
            ],
            "phase": "topic_breakthrough",
            "total_problems": 4,
        }) + "\n```"
        mock_llm.invoke.return_value = mock_response
        agent_fenced = TrainingAgent(db=db_with_profile, llm=mock_llm)
        agent_fenced.db.add_problems(_generate_mock_problems(30))

        state = _make_state(plan_days=1)
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"], "secondary": ["greedy"], "explore": ["string"],
        }
        state["difficulty_curve"] = [3.0]
        state["candidate_problems"] = _generate_mock_problems(20)

        result = agent_fenced._llm_arrange(state)
        assert result["weekly_plan"]["total_problems"] == 4
        assert result["weekly_plan"]["phase"] == "topic_breakthrough"

    def test_llm_arrange_json_extraction_fallback(self, db_with_profile: _TrainingDatabase):
        """When LLM returns text with embedded JSON, extract it via regex."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            "Here is the plan you requested:\n\n"
            + json.dumps({
                "days": [
                    {"day": 1, "primary": ["p1"], "secondary": ["s1", "s2"],
                     "explore": ["e1"], "target_difficulty": 3.0},
                ],
                "phase": "integrated_practice",
                "total_problems": 4,
            })
            + "\n\nLet me know if you need adjustments."
        )
        mock_llm.invoke.return_value = mock_response
        agent_json = TrainingAgent(db=db_with_profile, llm=mock_llm)
        agent_json.db.add_problems(_generate_mock_problems(30))

        state = _make_state(plan_days=1)
        state["profile"]["phase"] = "integrated_practice"
        state["targets"] = {
            "phase": "integrated_practice",
            "primary": ["dp"], "secondary": ["greedy"], "explore": [],
        }
        state["difficulty_curve"] = [3.0]
        state["candidate_problems"] = _generate_mock_problems(20)

        result = agent_json._llm_arrange(state)
        assert result["weekly_plan"]["total_problems"] == 4

    def test_llm_arrange_both_json_parse_and_regex_fail(self, db_with_profile: _TrainingDatabase):
        """When LLM returns completely unparseable text, error falls back to rule-based."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        # Text that is not valid JSON and contains no {...} block
        mock_response.content = "Sorry, I cannot generate a plan right now."
        mock_llm.invoke.return_value = mock_response
        agent_bad = TrainingAgent(db=db_with_profile, llm=mock_llm)
        agent_bad.db.add_problems(_generate_mock_problems(30))

        state = _make_state(plan_days=1)
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"], "secondary": ["greedy"], "explore": ["string"],
        }
        state["difficulty_curve"] = [3.0]
        state["candidate_problems"] = _generate_mock_problems(20)

        result = agent_bad._llm_arrange(state)
        # Should fall back to rule-based arrange
        assert "days" in result["weekly_plan"]
        assert len(result["errors"]) > 0


# ============================================================
# 6. Full Graph Compilation Tests
# ============================================================

class TestGraphCompilation:
    """Test that the graph compiles and executes end-to-end."""

    def test_graph_is_compiled(self, agent: TrainingAgent):
        """Graph should have a compile method result."""
        assert agent.graph is not None

    def test_graph_has_checkpointer(self, agent: TrainingAgent):
        """Compiled graph should include a checkpointer."""
        assert hasattr(agent.graph, "checkpointer")

    def test_graph_invoke_loads_profile(self, agent: TrainingAgent):
        """Invoking the graph should produce a result with loaded profile data."""
        config = {"configurable": {"thread_id": "test-load-profile"}}
        result = agent.graph.invoke({
            "user_id": "u1",
            "profile_id": "test_profile",
            "plan_days": 7,
            "daily_target": 5,
            "profile": {},
            "weak_tags_ranked": [],
            "candidate_problems": [],
            "weekly_plan": {},
            "difficulty_curve": [],
            "targets": {},
            "plan_data": {},
            "errors": [],
        }, config)
        assert result is not None
        assert isinstance(result, dict)

    def test_graph_invoke_error_on_missing_profile(self, empty_db: _TrainingDatabase):
        """Invoking with missing profile should record an error."""
        agent_no_profile = TrainingAgent(db=empty_db, llm=None)
        config = {"configurable": {"thread_id": "test-missing"}}
        result = agent_no_profile.graph.invoke({
            "user_id": "no_such_user",
            "profile_id": "unknown",
            "plan_days": 7,
            "daily_target": 5,
            "profile": {},
            "weak_tags_ranked": [],
            "candidate_problems": [],
            "weekly_plan": {},
            "difficulty_curve": [],
            "targets": {},
            "plan_data": {},
            "errors": [],
        }, config)
        assert len(result.get("errors", [])) > 0

    def test_full_pipeline_produces_plan_data(self, agent: TrainingAgent):
        """End-to-end invocation should produce complete plan_data."""
        config = {"configurable": {"thread_id": "test-full-pipeline"}}
        result = agent.graph.invoke({
            "user_id": "u1",
            "profile_id": "test_profile",
            "plan_days": 7,
            "daily_target": 5,
            "profile": {},
            "weak_tags_ranked": [],
            "candidate_problems": [],
            "weekly_plan": {},
            "difficulty_curve": [],
            "targets": {},
            "plan_data": {},
            "errors": [],
        }, config)
        assert "plan_data" in result
        assert "weekly_plan" in result
        assert "targets" in result
        assert "difficulty_curve" in result


# ============================================================
# 7. plan_data Output Structure Tests
# ============================================================

class TestPlanDataOutput:
    """Test that plan_data output structure is complete."""

    def test_plan_data_has_required_keys(self, agent: TrainingAgent):
        """plan_data must include profile_id, user_id, plan, targets, difficulty_curve, candidate_count."""
        state = _make_state()
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"], "secondary": ["greedy"], "explore": [],
        }
        state["weekly_plan"] = {
            "days": [
                {"day": 1, "primary": [], "secondary": [], "explore": [], "target_difficulty": 3.0},
            ],
            "phase": "topic_breakthrough",
            "total_problems": 0,
        }
        state["difficulty_curve"] = [3.0]
        state["candidate_problems"] = _generate_mock_problems(5)

        result = agent._save_plan(state)
        plan_data = result["plan_data"]

        assert "profile_id" in plan_data
        assert "user_id" in plan_data
        assert "plan" in plan_data
        assert "targets" in plan_data
        assert "difficulty_curve" in plan_data
        assert "candidate_count" in plan_data
        assert "errors" in plan_data

    def test_plan_data_is_saved_to_db(self, agent: TrainingAgent):
        """save_plan should persist to the database."""
        user_id = "u_save_test"
        profile_id = "p_save_test"
        db = agent.db
        db.set_profile(user_id, _make_profile())

        state = _make_state(user_id=user_id, profile=_make_profile())
        state["profile"]["phase"] = "topic_breakthrough"
        state["profile_id"] = profile_id
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"], "secondary": ["greedy"], "explore": [],
        }
        state["weekly_plan"] = {
            "days": [], "phase": "topic_breakthrough", "total_problems": 0,
        }
        state["difficulty_curve"] = [3.0, 4.0]
        state["candidate_problems"] = []

        agent._save_plan(state)

        saved = db.get_plan(user_id, profile_id)
        assert saved is not None
        assert saved["user_id"] == user_id
        assert saved["profile_id"] == profile_id
        assert "plan" in saved
        assert "targets" in saved
        assert "difficulty_curve" in saved

    def test_load_profile_node_fills_state(self, agent: TrainingAgent):
        """load_profile should populate profile and weak_tags_ranked."""
        state: TrainingState = {
            "user_id": "u1",
            "profile_id": "",
            "plan_days": 7,
            "daily_target": 5,
            "profile": {},
            "weak_tags_ranked": [],
            "candidate_problems": [],
            "weekly_plan": {},
            "difficulty_curve": [],
            "targets": {},
            "plan_data": {},
            "errors": [],
        }
        result = agent._load_profile(state)
        assert result["profile"] != {}
        assert "weak_tags_ranked" in result

    def test_retrieve_problems_produces_scored_candidates(self, agent: TrainingAgent):
        """retrieve_problems should produce scored candidate list."""
        state = _make_state()
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp", "graph"],
            "secondary": ["greedy"],
            "explore": ["string"],
        }
        state["difficulty_curve"] = [4.0] * 7

        result = agent._retrieve_problems(state)
        candidates = result["candidate_problems"]
        assert len(candidates) > 0
        for c in candidates:
            assert "_score" in c
            assert "total" in c["_score"]
            assert 0.0 <= c["_score"]["total"] <= 1.0

    def test_candidates_sorted_by_score_descending(self, agent: TrainingAgent):
        """Candidates should be sorted by total score descending."""
        state = _make_state()
        state["profile"]["phase"] = "topic_breakthrough"
        state["targets"] = {
            "phase": "topic_breakthrough",
            "primary": ["dp"],
            "secondary": ["greedy"],
            "explore": [],
        }
        state["difficulty_curve"] = [5.0] * 7

        result = agent._retrieve_problems(state)
        candidates = result["candidate_problems"]
        totals = [c["_score"]["total"] for c in candidates]
        assert totals == sorted(totals, reverse=True), "Candidates not sorted by score descending"


# ============================================================
# 8. Helper Function Edge Cases
# ============================================================

class TestHelperFunctions:
    """Test module-level helper functions for full coverage."""

    def test_get_user_known_tags_empty_profile(self):
        """Empty profile should return empty set."""
        state: TrainingState = {
            "user_id": "u1", "profile_id": "", "plan_days": 7, "daily_target": 5,
            "profile": {}, "weak_tags_ranked": [], "candidate_problems": [],
            "weekly_plan": {}, "difficulty_curve": [], "targets": {},
            "plan_data": {}, "errors": [],
        }
        result = _get_user_known_tags(state)
        assert result == set()

    def test_get_user_known_tags_with_data(self):
        """Profile with skill_radar and strengths should return known tags."""
        state: TrainingState = {
            "user_id": "u1", "profile_id": "", "plan_days": 7, "daily_target": 5,
            "profile": {
                "skill_radar": {"dp": 0.8, "graph": 0.0, "math": 0.5},
                "strengths": [{"category": "greedy"}, {"category": "string"}],
            },
            "weak_tags_ranked": [], "candidate_problems": [],
            "weekly_plan": {}, "difficulty_curve": [], "targets": {},
            "plan_data": {}, "errors": [],
        }
        result = _get_user_known_tags(state)
        assert "dp" in result
        assert "math" in result
        assert "graph" not in result  # cov=0.0 excluded
        assert "greedy" in result
        assert "string" in result

    def test_mock_target_vector_output(self):
        """_mock_target_vector should return a normalized 10-dim vector."""
        vec = _mock_target_vector(["dp", "graph", "math"])
        assert len(vec) == 10
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-9

    def test_mock_target_vector_empty_tags(self):
        """Empty tags should return zero vector."""
        vec = _mock_target_vector([])
        assert len(vec) == 10
        assert all(v == 0.0 for v in vec)
