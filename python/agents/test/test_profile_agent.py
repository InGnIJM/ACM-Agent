"""
Comprehensive tests for ProfileAgent — nodes, routing, compilation, profile_data structure.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.profile_agent import (
    DEFAULT_DB,
    ProfileAgent,
    ProfileState,
    _Database,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def empty_db() -> _Database:
    """Fresh empty DB."""
    return _Database()


@pytest.fixture
def db_with_few_records() -> _Database:
    """DB with only 3 records (insufficient for full analysis)."""
    db = _Database()
    db.add_records([
        {
            "user_id": "u1", "platform": "Codeforces", "status": "AC",
            "difficulty": 3.0, "tags": ["binary_search", "prefix_sum"],
            "first_ac": True, "retries": 0, "timestamp": time.time() - 86400,
        },
        {
            "user_id": "u1", "platform": "Codeforces", "status": "WA",
            "difficulty": 4.0, "tags": ["two_pointers"],
            "first_ac": False, "retries": 2, "timestamp": time.time() - 172800,
        },
        {
            "user_id": "u1", "platform": "Luogu", "status": "AC",
            "difficulty": 5.0, "tags": ["heap", "greedy"],
            "first_ac": True, "retries": 1, "timestamp": time.time() - 259200,
        },
    ])
    db.add_daily_stats([
        {"user_id": "u1", "ac_count": 1},
        {"user_id": "u1", "ac_count": 0},
        {"user_id": "u1", "ac_count": 2},
    ])
    db.set_platform_profile("Codeforces", {"handle": "test_user", "rating": 1500})
    db.set_platform_profile("Luogu", {"handle": "test_user_lg", "rating": 1200})
    return db


@pytest.fixture
def db_with_many_records() -> _Database:
    """DB with 15 records (sufficient for full analysis)."""
    db = _Database()
    tags_pool = [
        ["binary_search", "prefix_sum"],
        ["two_pointers", "sliding_window"],
        ["heap", "greedy"],
        ["dfs", "bfs", "graph"],
        ["binary_tree_traverse", "bst"],
        ["hash_map", "string"],
        ["dp", "knapsack"],
        ["math", "number_theory"],
        ["segment_tree", "fenwick_tree"],
        ["shortest_path", "dijkstra"],
        ["kmp", "string"],
        ["backtracking"],
        ["union_find", "mst"],
        ["binary_search", "two_pointers"],
        ["suffix_array", "sam"],
    ]
    statuses = ["AC", "AC", "AC", "AC", "AC", "AC", "WA", "TLE", "AC", "AC", "AC", "AC", "AC", "WA", "AC"]
    difficulties = [2.0, 3.0, 4.0, 5.0, 6.0, 3.5, 7.0, 8.0, 4.5, 5.5, 6.5, 7.5, 3.0, 4.0, 9.0]
    first_acs = [True, True, True, False, True, True, True, False, True, True, True, True, False, True, True]
    retries_vals = [0, 1, 0, 2, 0, 0, 1, 3, 0, 1, 0, 0, 2, 1, 0]

    for i in range(15):
        db.add_records([{
            "user_id": "u2",
            "platform": "Codeforces" if i % 2 == 0 else "Luogu",
            "status": statuses[i],
            "difficulty": difficulties[i],
            "tags": tags_pool[i],
            "first_ac": first_acs[i],
            "retries": retries_vals[i],
            "timestamp": time.time() - (15 - i) * 86400,
        }])

    db.add_daily_stats([
        {"user_id": "u2", "ac_count": 1},
        {"user_id": "u2", "ac_count": 2},
        {"user_id": "u2", "ac_count": 3},
        {"user_id": "u2", "ac_count": 4},
        {"user_id": "u2", "ac_count": 5},
    ])
    db.set_platform_profile("Codeforces", {"handle": "power_user", "rating": 2200})
    db.set_platform_profile("Luogu", {"handle": "power_user_lg", "rating": 2000})
    return db


@pytest.fixture
def mock_llm() -> MagicMock:
    """Mock LLM that returns a deterministic summary."""
    llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "该用户算法基础扎实，在数据结构和搜索领域表现突出，建议加强动态规划和数学方面的训练。"
    llm.invoke.return_value = mock_response
    return llm


def _make_state(user_id: str) -> ProfileState:
    """Create a fresh ProfileState for testing nodes."""
    return ProfileState(
        user_id=user_id,
        platforms=[],
        raw_records=[],
        daily_stats=[],
        platform_profiles={},
        aggregated_stats={},
        analysis={},
        profile_data={},
        errors=[],
    )


# ============================================================
# Test: load_user_data node
# ============================================================

class TestLoadUserData:
    """Node load_user_data queries DB and populates records/daily/platforms."""

    def test_populates_records(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        result = agent._load_user_data(state)
        assert len(result["raw_records"]) == 15
        assert len(result["daily_stats"]) == 5
        assert "Codeforces" in result["platform_profiles"]
        assert "Luogu" in result["platform_profiles"]

    def test_empty_user_no_records(self, empty_db, mock_llm):
        agent = ProfileAgent(db=empty_db, llm=mock_llm)
        state = _make_state("nonexistent")
        result = agent._load_user_data(state)
        assert result["raw_records"] == []
        assert result["daily_stats"] == []
        assert result["platform_profiles"] == {}

    def test_platforms_set_correctly(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        result = agent._load_user_data(state)
        assert set(result["platforms"]) == {"Codeforces", "Luogu"}

    def test_errors_list_initialized(self, empty_db, mock_llm):
        agent = ProfileAgent(db=empty_db, llm=mock_llm)
        state = _make_state("u1")
        result = agent._load_user_data(state)
        assert isinstance(result["errors"], list)
        assert result["errors"] == []


# ============================================================
# Test: aggregate_stats node
# ============================================================

class TestAggregateStats:
    """Node aggregate_stats computes correct statistics."""

    def test_non_empty_records(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        result = ProfileAgent._aggregate_stats(state)
        stats = result["aggregated_stats"]
        assert stats["total_records"] == 15
        assert stats["ac_count"] == 12  # 12 "AC" out of 15
        assert stats["unique_tags"] > 0
        assert 0.0 <= stats["avg_difficulty"] <= 10.0
        assert isinstance(stats["by_tag"], dict)
        assert isinstance(stats["by_difficulty"], dict)
        assert isinstance(stats["by_platform"], dict)
        assert len(stats["top_tags"]) <= 5

    def test_empty_records(self, empty_db, mock_llm):
        agent = ProfileAgent(db=empty_db, llm=mock_llm)
        state = _make_state("u1")
        state = agent._load_user_data(state)
        result = ProfileAgent._aggregate_stats(state)
        stats = result["aggregated_stats"]
        assert stats["total_records"] == 0
        assert stats["ac_count"] == 0
        assert stats["avg_difficulty"] == 0.0
        assert stats["by_tag"] == {}

    def test_first_ac_rate_calculation(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        result = ProfileAgent._aggregate_stats(state)
        stats = result["aggregated_stats"]
        # 12 first_ac True out of 15 records
        assert 0.7 <= stats["first_ac_rate"] <= 0.9
        assert stats["avg_retries"] >= 0.0

    def test_top_tags_is_top5(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        # Create records where binary_search appears 5 times, two_pointers 4, etc.
        db = _Database()
        for i in range(5):
            db.add_records([{
                "user_id": "u99", "platform": "CF", "status": "AC",
                "difficulty": 3.0, "tags": ["binary_search"],
                "first_ac": True, "retries": 0, "timestamp": time.time(),
            }])
        for i in range(4):
            db.add_records([{
                "user_id": "u99", "platform": "CF", "status": "AC",
                "difficulty": 3.0, "tags": ["two_pointers"],
                "first_ac": True, "retries": 0, "timestamp": time.time(),
            }])
        agent = ProfileAgent(db=db, llm=mock_llm)
        state = _make_state("u99")
        state = agent._load_user_data(state)
        result = ProfileAgent._aggregate_stats(state)
        top_tags = result["aggregated_stats"]["top_tags"]
        assert list(top_tags.keys())[0] == "binary_search"
        assert top_tags["binary_search"] == 5


# ============================================================
# Test: calc_6_dims node
# ============================================================

class TestCalc6Dims:
    """Node calc_6_dims produces valid profile_data with all 6 dimensions."""

    def test_all_six_dimensions_present(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        result = ProfileAgent._calc_6_dims(state)
        dims = result["profile_data"]["dimensions"]
        expected_keys = {"coverage", "proficiency", "ceiling", "efficiency", "momentum", "overall"}
        assert set(dims.keys()) == expected_keys

    def test_dimensions_in_valid_ranges(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        result = ProfileAgent._calc_6_dims(state)
        dims = result["profile_data"]["dimensions"]
        # All dimension values should be non-negative and finite
        for key, val in dims.items():
            assert isinstance(val, (int, float)), f"{key} is {type(val).__name__}"
            assert val >= 0.0, f"{key}={val} is negative"
            assert val == val, f"{key}={val} is NaN"  # NaN != NaN
            assert val != float("inf"), f"{key} is +inf"
            assert val != float("-inf"), f"{key} is -inf"

    def test_dimensions_with_few_records(self, db_with_few_records, mock_llm):
        agent = ProfileAgent(db=db_with_few_records, llm=mock_llm)
        state = _make_state("u1")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        result = ProfileAgent._calc_6_dims(state)
        dims = result["profile_data"]["dimensions"]
        # Ceiling should be 0 since fewer than 5 records
        assert dims["ceiling"] == 0.0
        # But other dims should still compute
        assert 0.0 <= dims["coverage"] <= 1.0
        assert 0.0 <= dims["proficiency"] <= 1.0
        assert -1.0 <= dims["momentum"] <= 1.0

    def test_style_is_valid(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        result = ProfileAgent._calc_6_dims(state)
        style = result["profile_data"]["style"]
        assert style in {"grinder", "deep_diver", "specialist", "balanced"}

    def test_strengths_and_weaknesses_present(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        result = ProfileAgent._calc_6_dims(state)
        assert isinstance(result["profile_data"]["strengths"], list)
        assert isinstance(result["profile_data"]["weaknesses"], list)

    def test_skill_radar_is_dict(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        result = ProfileAgent._calc_6_dims(state)
        radar = result["profile_data"]["skill_radar"]
        assert isinstance(radar, dict)
        assert len(radar) > 0
        for k, v in radar.items():
            assert isinstance(k, str)
            assert 0.0 <= v <= 1.0

    def test_empty_records_graceful(self, empty_db, mock_llm):
        agent = ProfileAgent(db=empty_db, llm=mock_llm)
        state = _make_state("u1")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        result = ProfileAgent._calc_6_dims(state)
        dims = result["profile_data"]["dimensions"]
        # All should be 0.0-ish for empty data
        for key in dims:
            assert dims[key] >= 0.0
        assert result["profile_data"]["style"] is not None


# ============================================================
# Test: profile_data output structure
# ============================================================

class TestProfileDataStructure:
    """Verify profile_data output structure is complete."""

    def test_top_level_keys(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        state = ProfileAgent._calc_6_dims(state)
        expected_keys = {"dimensions", "style", "strengths", "weaknesses", "skill_radar"}
        assert set(state["profile_data"].keys()) == expected_keys

    def test_dimensions_has_6_keys(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        state = ProfileAgent._calc_6_dims(state)
        assert len(state["profile_data"]["dimensions"]) == 6

    def test_strengths_items_have_category_and_coverage(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        state = ProfileAgent._calc_6_dims(state)
        for item in state["profile_data"]["strengths"]:
            assert "category" in item
            assert "coverage" in item
            assert isinstance(item["coverage"], float)

    def test_weaknesses_items_have_category_and_coverage(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        state = ProfileAgent._calc_6_dims(state)
        for item in state["profile_data"]["weaknesses"]:
            assert "category" in item
            assert "coverage" in item
            assert isinstance(item["coverage"], float)


# ============================================================
# Test: llm_summarize node
# ============================================================

class TestLLMSummarize:
    """Node llm_summarize calls LLM and populates analysis.summary_text."""

    def test_generates_summary_text(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        state = ProfileAgent._calc_6_dims(state)
        result = agent._llm_summarize(state)
        assert "summary_text" in result["analysis"]
        assert len(result["analysis"]["summary_text"]) > 0

    def test_llm_invoked_with_profile_data(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        state = ProfileAgent._calc_6_dims(state)
        agent._llm_summarize(state)
        # LLM should have been invoked once
        mock_llm.invoke.assert_called_once()
        call_arg = mock_llm.invoke.call_args[0][0]
        assert "u2" in call_arg
        assert "六维能力值" in call_arg

    def test_llm_failure_graceful(self, db_with_many_records):
        """When LLM raises, node still returns a valid state with error recorded."""
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("API down")
        agent = ProfileAgent(db=db_with_many_records, llm=llm)
        state = _make_state("u2")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        state = ProfileAgent._calc_6_dims(state)
        result = agent._llm_summarize(state)
        assert "summary_text" in result["analysis"]
        assert len(result["errors"]) > 0
        assert "LLM summarization failed" in result["errors"][0]


# ============================================================
# Test: fallback node
# ============================================================

class TestFallback:
    """Node fallback sets a static summary when data is insufficient."""

    def test_sets_summary_text(self, db_with_few_records, mock_llm):
        agent = ProfileAgent(db=db_with_few_records, llm=mock_llm)
        state = _make_state("u1")
        state = agent._load_user_data(state)
        state = ProfileAgent._aggregate_stats(state)
        state = ProfileAgent._calc_6_dims(state)
        result = ProfileAgent._fallback(state)
        assert "summary_text" in result["analysis"]
        assert "记录不足" in result["analysis"]["summary_text"]
        assert "u1" in result["analysis"]["summary_text"]

    def test_no_errors_added_by_fallback(self, db_with_few_records, mock_llm):
        agent = ProfileAgent(db=db_with_few_records, llm=mock_llm)
        state = _make_state("u1")
        state = agent._load_user_data(state)
        result = ProfileAgent._fallback(state)
        assert result["errors"] == []


# ============================================================
# Test: conditional routing
# ============================================================

class TestRouting:
    """Conditional edge after calc_6_dims routes correctly."""

    def test_few_records_routes_to_fallback(self, mock_llm):
        """records < 10 → 'fallback'."""
        agent = ProfileAgent(db=DEFAULT_DB, llm=mock_llm)
        state = _make_state("u1")
        state["raw_records"] = [{"status": "AC"}] * 5  # 5 records
        result = ProfileAgent._route_after_calc(state)
        assert result == "fallback"

    def test_exactly_9_records_routes_to_fallback(self, mock_llm):
        agent = ProfileAgent(db=DEFAULT_DB, llm=mock_llm)
        state = _make_state("u1")
        state["raw_records"] = [{"status": "AC"}] * 9
        assert ProfileAgent._route_after_calc(state) == "fallback"

    def test_exactly_10_records_routes_to_llm(self, mock_llm):
        agent = ProfileAgent(db=DEFAULT_DB, llm=mock_llm)
        state = _make_state("u1")
        state["raw_records"] = [{"status": "AC"}] * 10
        assert ProfileAgent._route_after_calc(state) == "llm_summarize"

    def test_many_records_routes_to_llm(self, mock_llm):
        agent = ProfileAgent(db=DEFAULT_DB, llm=mock_llm)
        state = _make_state("u1")
        state["raw_records"] = [{"status": "AC"}] * 50
        assert ProfileAgent._route_after_calc(state) == "llm_summarize"

    def test_no_records_routes_to_fallback(self, mock_llm):
        agent = ProfileAgent(db=DEFAULT_DB, llm=mock_llm)
        state = _make_state("u1")
        state["raw_records"] = []
        assert ProfileAgent._route_after_calc(state) == "fallback"


# ============================================================
# Test: full graph compilation
# ============================================================

class TestGraphCompilation:
    """Full graph compiles and runs successfully end-to-end."""

    def test_graph_compiles_successfully(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        assert agent.graph is not None

    def test_graph_invoke_llm_path(self, db_with_many_records, mock_llm):
        """With sufficient records → should route through llm_summarize."""
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        graph = agent.graph
        config = {"configurable": {"thread_id": "test-thread-1"}}
        result = graph.invoke({"user_id": "u2"}, config)
        assert result["raw_records"] is not None
        assert len(result["raw_records"]) == 15
        assert "dimensions" in result["profile_data"]
        assert "summary_text" in result["analysis"]
        assert len(result["analysis"]["summary_text"]) > 0

    def test_graph_invoke_fallback_path(self, db_with_few_records, mock_llm):
        """With fewer than 10 records → should route through fallback."""
        agent = ProfileAgent(db=db_with_few_records, llm=mock_llm)
        graph = agent.graph
        config = {"configurable": {"thread_id": "test-thread-2"}}
        result = graph.invoke({"user_id": "u1"}, config)
        assert len(result["raw_records"]) == 3
        assert "dimensions" in result["profile_data"]
        assert "summary_text" in result["analysis"]
        assert "记录不足" in result["analysis"]["summary_text"]

    def test_graph_invoke_empty_data(self, empty_db, mock_llm):
        """With no records at all → should still not crash."""
        agent = ProfileAgent(db=empty_db, llm=mock_llm)
        graph = agent.graph
        config = {"configurable": {"thread_id": "test-thread-3"}}
        result = graph.invoke({"user_id": "no_user"}, config)
        assert result["raw_records"] == []
        assert result["profile_data"]["dimensions"]["overall"] >= 0.0

    def test_graph_has_checkpointer(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        assert agent.graph.checkpointer is not None

    def test_default_llm_is_chatopenai(self, db_with_many_records):
        """When no LLM is passed, default is ChatOpenAI(deepseek-chat)."""
        # ChatOpenAI validates API keys at init time; mock to avoid real key check
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-testing")
            from langchain_openai import ChatOpenAI
            agent = ProfileAgent(db=db_with_many_records)
            assert isinstance(agent.llm, ChatOpenAI)


# ============================================================
# Test: integration — full graph with real formulas
# ============================================================

class TestIntegration:
    """End-to-end correctness of the graph output against formulas.py expectations."""

    def test_overall_score_falls_in_reasonable_range(self, db_with_many_records, mock_llm):
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        graph = agent.graph
        config = {"configurable": {"thread_id": "test-integration-1"}}
        result = graph.invoke({"user_id": "u2"}, config)
        overall = result["profile_data"]["dimensions"]["overall"]
        assert 0.0 <= overall <= 1.5  # overall can slightly exceed 1.0 with bonus

    def test_dimensions_consistent_across_runs(self, db_with_many_records, mock_llm):
        """Same input should produce same profile_data (deterministic formulas)."""
        agent = ProfileAgent(db=db_with_many_records, llm=mock_llm)
        graph = agent.graph
        config1 = {"configurable": {"thread_id": "t1"}}
        config2 = {"configurable": {"thread_id": "t2"}}
        r1 = graph.invoke({"user_id": "u2"}, config1)
        r2 = graph.invoke({"user_id": "u2"}, config2)
        assert r1["profile_data"]["dimensions"] == r2["profile_data"]["dimensions"]
        assert r1["profile_data"]["style"] == r2["profile_data"]["style"]
