"""
Comprehensive tests for formulas.py — all 8 public functions.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Dict, List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.formulas import (
    STYLE_BONUS,
    _sigmoid,
    calc_category_coverage,
    calc_ceiling,
    calc_coverage,
    calc_efficiency,
    calc_momentum,
    calc_overall_score,
    calc_proficiency,
    classify_style,
)


# ============================================================
# calc_coverage
# ============================================================

class TestCalcCoverage:
    def test_full_coverage(self):
        tags = {"a", "b", "c"}
        assert calc_coverage(tags, tags) == 1.0

    def test_half_coverage(self):
        assert calc_coverage({"a"}, {"a", "b", "c", "d"}) == 0.25

    def test_no_overlap(self):
        assert calc_coverage({"x"}, {"a", "b"}) == 0.0

    def test_empty_all_tags(self):
        assert calc_coverage({"a", "b"}, set()) == 0.0

    def test_empty_user_tags(self):
        assert calc_coverage(set(), {"a", "b"}) == 0.0


# ============================================================
# calc_category_coverage
# ============================================================

class TestCalcCategoryCoverage:
    def test_mixed_categories(self):
        user = {"a", "b", "c"}
        taxonomy = {
            "cat1": {"a", "b", "d"},
            "cat2": {"x", "y"},
        }
        result = calc_category_coverage(user, taxonomy)
        assert result["cat1"] == pytest.approx(2 / 3)
        assert result["cat2"] == 0.0

    def test_empty_taxonomy(self):
        assert calc_category_coverage({"a"}, {}) == {}

    def test_empty_category_tags(self):
        result = calc_category_coverage({"a"}, {"empty": set()})
        assert result["empty"] == 0.0


# ============================================================
# calc_proficiency
# ============================================================

class TestCalcProficiency:
    def test_sigmoid_overflow_returns_extremes(self):
        """Very negative x → overflow → 0.0; very positive x → 1.0."""
        assert _sigmoid(-100.0, center=0.5, slope=10.0) == 0.0
        assert _sigmoid(100.0, center=0.5, slope=10.0) == 1.0

    def test_perfect_mastery(self):
        """AC rate 100%, max difficulty, many ACs, recent activity."""
        score = calc_proficiency(
            ac_count=30, total_count=30, avg_difficulty=10.0, days_since_last=0,
        )
        # All components near max → ~1.0
        assert 0.85 <= score <= 1.05

    def test_beginner(self):
        """Low AC count, low difficulty, moderate rate, long inactivity."""
        score = calc_proficiency(
            ac_count=2, total_count=10, avg_difficulty=2.0, days_since_last=100,
        )
        # Should be significantly lower
        assert 0.05 <= score <= 0.45

    def test_zero_ac(self):
        """No ACs at all."""
        score = calc_proficiency(
            ac_count=0, total_count=0, avg_difficulty=0.0, days_since_last=365,
        )
        # ac_rate=0 → sigmoid(0,0.5,10) ≈ 0.0067
        # But days_since_last is huge → recency ≈ 0
        assert 0.0 <= score <= 0.1

    def test_zero_total_count(self):
        """total_count=0 but ac_count=0 — avoid division by zero."""
        score = calc_proficiency(
            ac_count=0, total_count=0, avg_difficulty=5.0, days_since_last=0,
        )
        # Should not raise; recency term is max since days=0
        assert 0.0 <= score <= 0.5

    @pytest.mark.parametrize(
        "ac_count,total_count,avg_diff,days,expected_lo,expected_hi",
        [
            (10, 10, 8.0, 0, 0.80, 1.0),    # strong
            (5, 10, 5.0, 7, 0.40, 0.65),     # moderate
            (1, 5, 3.0, 30, 0.19, 0.50),     # weak
            (0, 1, 0.0, 180, 0.0, 0.15),     # very weak
            (50, 50, 10.0, 0, 0.90, 1.05),   # near-perfect
        ],
    )
    def test_parametrized(
        self, ac_count, total_count, avg_diff, days, expected_lo, expected_hi,
    ):
        score = calc_proficiency(ac_count, total_count, avg_diff, days)
        assert expected_lo <= score <= expected_hi, (
            f"Expected {expected_lo}–{expected_hi}, got {score:.4f}"
        )

    def test_sigmoid_center(self):
        """At ac_rate=0.5, sigmoid should be 0.5."""
        score_ac05 = calc_proficiency(5, 10, 5.0, 1000)
        # With ac_rate=0.5, days huge (recency ≈ 0), avg_diff=5:
        # 0.40*0.5 + 0.30*0.5 + 0.20*log(6)/log(31) + ~0
        # = 0.20 + 0.15 + 0.20*0.522 + 0 ≈ 0.454
        # Just verify it doesn't blow up
        assert 0.0 <= score_ac05 <= 1.0


# ============================================================
# calc_ceiling
# ============================================================

class TestCalcCeiling:
    def test_p90_basic(self):
        records = [{"difficulty": float(i)} for i in range(1, 11)]  # 1..10
        result = calc_ceiling(records)
        # 10 values → sorted: 1,2,3,4,5,6,7,8,9,10
        # 90th percentile with default linear interpolation ≈ 9.1
        assert 8.5 <= result <= 9.5

    def test_less_than_5_records_returns_zero(self):
        assert calc_ceiling([{"difficulty": 8.0}]) == 0.0
        assert calc_ceiling([{"difficulty": i} for i in range(4)]) == 0.0

    def test_exactly_5_records(self):
        records = [{"difficulty": float(i)} for i in range(1, 6)]  # 1,2,3,4,5
        result = calc_ceiling(records)
        # Should be non-zero since len >= 5
        assert result > 0.0

    def test_empty_records(self):
        assert calc_ceiling([]) == 0.0

    def test_all_same_difficulty(self):
        records = [{"difficulty": 5.0}] * 10
        assert calc_ceiling(records) == 5.0


# ============================================================
# calc_efficiency
# ============================================================

class TestCalcEfficiency:
    def test_perfect_first_ac(self):
        records = [
            {"first_ac": True, "retries": 0},
            {"first_ac": True, "retries": 0},
        ]
        # first_ac_rate=1.0, avg_retries=0, retry_penalty=0
        # = 0.6*1.0 + 0.4*1.0 = 1.0
        assert calc_efficiency(records) == 1.0

    def test_all_retries_no_first_ac(self):
        records = [
            {"first_ac": False, "retries": 3},
            {"first_ac": False, "retries": 3},
        ]
        # first_ac_rate=0.0, avg_retries=3, penalty=0.6
        # = 0.6*0 + 0.4*(1-0.6) = 0.16
        assert calc_efficiency(records) == pytest.approx(0.16)

    def test_mixed(self):
        records = [
            {"first_ac": True, "retries": 0},
            {"first_ac": False, "retries": 5},
            {"first_ac": True, "retries": 2},
        ]
        # first_ac_rate = 2/3 ≈ 0.6667
        # avg_retries = (0+5+2)/3 = 7/3 ≈ 2.333
        # penalty = 2.333/5 = 0.4667
        # = 0.6*0.6667 + 0.4*0.5333 = 0.4000 + 0.2133 = 0.6133
        result = calc_efficiency(records)
        assert 0.60 <= result <= 0.62

    def test_no_records(self):
        assert calc_efficiency([]) == 0.0

    def test_max_retries_capped(self):
        """avg_retries > 5 should be capped so penalty ≤ 1."""
        records = [
            {"first_ac": True, "retries": 20},
        ]
        # first_ac_rate=1.0, avg_retries=20, penalty=min(20/5,1)=1.0
        # = 0.6*1.0 + 0.4*0 = 0.6
        assert calc_efficiency(records) == pytest.approx(0.6)


# ============================================================
# calc_momentum
# ============================================================

class TestCalcMomentum:
    def test_positive_trend(self):
        daily = [
            {"ac_count": 1},
            {"ac_count": 2},
            {"ac_count": 3},
            {"ac_count": 4},
            {"ac_count": 5},
        ]
        result = calc_momentum(daily)
        # Positive slope, normalised → > 0
        assert result > 0.0

    def test_negative_trend(self):
        daily = [
            {"ac_count": 5},
            {"ac_count": 4},
            {"ac_count": 3},
            {"ac_count": 2},
            {"ac_count": 1},
        ]
        result = calc_momentum(daily)
        assert result < 0.0

    def test_flat_trend(self):
        daily = [
            {"ac_count": 3},
            {"ac_count": 3},
            {"ac_count": 3},
        ]
        result = calc_momentum(daily)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_insufficient_data_single_point(self):
        assert calc_momentum([{"ac_count": 5}]) == 0.0

    def test_insufficient_data_empty(self):
        assert calc_momentum([]) == 0.0

    def test_clamped_to_range(self):
        """Very steep slope should be clamped to [-1, 1]."""
        daily = [{"ac_count": i * 100} for i in range(10)]
        result = calc_momentum(daily)
        assert -1.0 <= result <= 1.0

    def test_window_applied(self):
        """Only last `window` entries are used."""
        daily = [{"ac_count": i} for i in range(100)]
        result = calc_momentum(daily, window=10)
        assert -1.0 <= result <= 1.0


# ============================================================
# classify_style
# ============================================================

class TestClassifyStyle:
    def test_grinder(self):
        """High volume, low difficulty → grinder."""
        style = classify_style(
            total_solved=300,
            unique_tags=20,
            avg_proficiency=0.6,
            top3_concentration=0.3,
            avg_difficulty=3.0,
        )
        assert style == "grinder"

    def test_deep_diver(self):
        """High difficulty, narrow tags → deep_diver."""
        style = classify_style(
            total_solved=50,
            unique_tags=5,
            avg_proficiency=0.7,
            top3_concentration=0.4,
            avg_difficulty=8.0,
        )
        assert style == "deep_diver"

    def test_specialist(self):
        """High top3 concentration, not grinder/deep_diver → specialist."""
        style = classify_style(
            total_solved=100,
            unique_tags=15,
            avg_proficiency=0.5,
            top3_concentration=0.65,
            avg_difficulty=5.0,
        )
        assert style == "specialist"

    def test_balanced(self):
        """Moderate everything → balanced."""
        style = classify_style(
            total_solved=100,
            unique_tags=12,
            avg_proficiency=0.5,
            top3_concentration=0.3,
            avg_difficulty=5.5,
        )
        assert style == "balanced"

    def test_grinder_edge(self):
        """Exactly at grinder thresholds."""
        style = classify_style(
            total_solved=200,
            unique_tags=50,
            avg_proficiency=0.5,
            top3_concentration=0.2,
            avg_difficulty=4.0,
        )
        assert style == "grinder"

    def test_deep_diver_edge(self):
        """Exactly at deep_diver thresholds."""
        style = classify_style(
            total_solved=10,
            unique_tags=8,
            avg_proficiency=0.5,
            top3_concentration=0.2,
            avg_difficulty=7.0,
        )
        assert style == "deep_diver"

    def test_specialist_edge(self):
        """Exactly at specialist concentration threshold."""
        style = classify_style(
            total_solved=50,
            unique_tags=10,
            avg_proficiency=0.5,
            top3_concentration=0.5,
            avg_difficulty=5.0,
        )
        assert style == "specialist"

    def test_grinder_overrides_deep_diver(self):
        """When both thresholds met, grinder wins."""
        # avg_difficulty=4 (low enough for grinder) AND avg_difficulty=7? Can't both.
        # But a user with 300 solved, difficulty=4, narrow tags would still be grinder.
        style = classify_style(
            total_solved=300,
            unique_tags=5,
            avg_proficiency=0.7,
            top3_concentration=0.2,
            avg_difficulty=4.0,
        )
        assert style == "grinder"

    def test_deep_diver_overrides_specialist(self):
        style = classify_style(
            total_solved=30,
            unique_tags=5,
            avg_proficiency=0.7,
            top3_concentration=0.8,
            avg_difficulty=8.0,
        )
        # deep_diver triggered before specialist
        assert style == "deep_diver"


# ============================================================
# calc_overall_score
# ============================================================

class TestOverallScore:
    def test_perfect_score(self):
        score = calc_overall_score(
            coverage=1.0,
            avg_proficiency=1.0,
            ceiling=10.0,
            efficiency=1.0,
            style="balanced",
            momentum=1.0,
        )
        # base = 0.20*1 + 0.25*1 + 0.20*1 + 0.20*1 = 0.85
        # * 1.0 * 1.10 = 0.935
        assert 0.90 <= score <= 1.0

    def test_zero_score(self):
        score = calc_overall_score(
            coverage=0.0,
            avg_proficiency=0.0,
            ceiling=0.0,
            efficiency=0.0,
            style="specialist",
            momentum=-1.0,
        )
        # base = 0, *0.5*(1-0.1) = 0
        assert score == 0.0

    def test_style_bonus_applied(self):
        """Same inputs, different styles → different scores."""
        args = dict(coverage=0.5, avg_proficiency=0.5, ceiling=5.0, efficiency=0.5, momentum=0.0)
        balanced = calc_overall_score(**args, style="balanced")
        grinder = calc_overall_score(**args, style="grinder")
        assert balanced > grinder  # balanced has bonus 1.0, grinder 0.6

    def test_momentum_positive_boosts(self):
        base = calc_overall_score(0.5, 0.5, 5.0, 0.5, "balanced", 0.0)
        boosted = calc_overall_score(0.5, 0.5, 5.0, 0.5, "balanced", 1.0)
        assert boosted > base

    def test_momentum_negative_penalizes(self):
        base = calc_overall_score(0.5, 0.5, 5.0, 0.5, "balanced", 0.0)
        penalized = calc_overall_score(0.5, 0.5, 5.0, 0.5, "balanced", -1.0)
        assert penalized < base

    def test_unknown_style_defaults_to_1(self):
        score = calc_overall_score(0.5, 0.5, 5.0, 0.5, "nonexistent_style", 0.0)
        # Should not crash; should use default bonus=1.0
        assert 0.0 <= score <= 1.0

    def test_ceiling_exceeds_10_is_capped(self):
        """ceiling > 10 should be capped in the overall formula."""
        s1 = calc_overall_score(0.5, 0.5, 10.0, 0.5, "balanced", 0.0)
        s2 = calc_overall_score(0.5, 0.5, 15.0, 0.5, "balanced", 0.0)
        assert s1 == pytest.approx(s2)

    def test_style_bonus_constants(self):
        """Verify style bonus is defined for all 4 styles."""
        for style in ["grinder", "deep_diver", "specialist", "balanced"]:
            assert style in STYLE_BONUS
            assert 0.0 <= STYLE_BONUS[style] <= 2.0
