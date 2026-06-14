"""
Comprehensive tests for spaced_repetition.py — SM-2 variant scheduler.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.spaced_repetition import schedule_review


# ============================================================
# Helpers
# ============================================================

def _make_history(*qualities: int):
    """Build a history list from quality values."""
    return [{"quality": q} for q in qualities]


# ============================================================
# First review / no history
# ============================================================

class TestFirstReview:
    def test_no_history_returns_interval_1(self):
        result = schedule_review("binary_search", [])
        assert result["interval_days"] == 1
        assert result["ease_factor"] == pytest.approx(2.5)
        expected_date = date.today() + timedelta(days=1)
        assert result["next_review_date"] == expected_date.isoformat()

    def test_no_history_has_valid_date(self):
        result = schedule_review("dp", [])
        parsed = date.fromisoformat(result["next_review_date"])
        assert parsed > date.today()


# ============================================================
# Perfect quality extends interval
# ============================================================

class TestPerfectQualityExtendsInterval:
    def test_one_success_doubles_from_1_to_2(self):
        """After first success, interval doubles: 1 → 2."""
        result = schedule_review("tag", _make_history(5))
        assert result["interval_days"] == 2

    def test_two_successes_double_twice(self):
        """1 → 2 → 4."""
        result = schedule_review("tag", _make_history(5, 5))
        assert result["interval_days"] == 4

    def test_three_successes_double_thrice(self):
        """1 → 2 → 4 → 8."""
        result = schedule_review("tag", _make_history(5, 5, 5))
        assert result["interval_days"] == 8

    def test_five_successes(self):
        """1 → 2 → 4 → 8 → 16."""
        result = schedule_review("tag", _make_history(5, 5, 5, 5, 5))
        assert result["interval_days"] == 32

    def test_interval_capped_at_365(self):
        """Very long success streak caps at 365 days."""
        result = schedule_review("tag", _make_history(*([5] * 20)))
        assert result["interval_days"] <= 365


# ============================================================
# Failed quality resets interval
# ============================================================

class TestFailedQualityResetsInterval:
    def test_failure_after_successes_resets(self):
        """1→2→4 → failure → 1."""
        result = schedule_review("tag", _make_history(5, 5, 0))
        assert result["interval_days"] == 1

    def test_single_failure(self):
        """Single failure → interval stays 1."""
        result = schedule_review("tag", _make_history(2))
        assert result["interval_days"] == 1

    def test_success_after_failure(self):
        """Failure resets to 1, then success doubles to 2."""
        result = schedule_review("tag", _make_history(5, 5, 0, 5))
        # History: success(1→2), success(2→4), fail(→1), success(1→2)
        assert result["interval_days"] == 2

    def test_quality_3_is_success(self):
        """Quality 3 is still a success (≥ 3)."""
        result = schedule_review("tag", _make_history(5, 3))
        # 1→2→4
        assert result["interval_days"] == 4

    def test_quality_2_is_failure(self):
        """Quality 2 is a failure (< 3)."""
        result = schedule_review("tag", _make_history(5, 2))
        # 1→2, then reset to 1
        assert result["interval_days"] == 1


# ============================================================
# Ease factor adjustments
# ============================================================

class TestEaseFactorAdjustments:
    def test_starts_at_2_5(self):
        result = schedule_review("tag", [])
        assert result["ease_factor"] == pytest.approx(2.5)

    def test_perfect_quality_increases_ease(self):
        """Quality 5 should increase ease_factor above 2.5."""
        result = schedule_review("tag", _make_history(5))
        assert result["ease_factor"] > 2.5

    def test_multiple_perfects_increase_ease_further(self):
        r1 = schedule_review("tag", _make_history(5))
        r2 = schedule_review("tag", _make_history(5, 5))
        assert r2["ease_factor"] > r1["ease_factor"]

    def test_quality_4_smaller_increase(self):
        """Quality 4 gives smaller EF boost than quality 5."""
        r4 = schedule_review("tag", _make_history(4))
        r5 = schedule_review("tag", _make_history(5))
        assert r5["ease_factor"] > r4["ease_factor"]

    def test_quality_0_decreases_ease(self):
        result = schedule_review("tag", _make_history(5, 0))
        # After first success EF > 2.5, then failure drops it
        assert result["ease_factor"] < 2.6  # significantly reduced

    def test_ease_factor_floor_is_1_3(self):
        """EF should never drop below 1.3."""
        # Many failures in a row
        result = schedule_review("tag", _make_history(*([1] * 20)))
        assert result["ease_factor"] >= 1.3

    def test_ease_factor_rounded_to_2_decimals(self):
        result = schedule_review("tag", _make_history(5, 5, 5))
        ef_str = str(result["ease_factor"])
        # Should have at most 2 decimal places
        if "." in ef_str:
            decimals = len(ef_str.split(".")[1])
            assert decimals <= 2


# ============================================================
# Integration / edge cases
# ============================================================

class TestIntegration:
    def test_full_cycle(self):
        """Simulate a realistic review cycle."""
        # Day 1: first review, quality 4
        r1 = schedule_review("dp", _make_history(4))
        assert r1["interval_days"] == 2  # 1→2
        assert r1["ease_factor"] == pytest.approx(2.5)  # q4 net EF change is 0

        # Day 3: second review, quality 5
        r2 = schedule_review("dp", _make_history(4, 5))
        assert r2["interval_days"] == 4  # 2→4

        # Day 7: third review, quality 3 (barely passed)
        r3 = schedule_review("dp", _make_history(4, 5, 3))
        assert r3["interval_days"] == 8  # 4→8

        # Day 15: forgot, quality 1
        r4 = schedule_review("dp", _make_history(4, 5, 3, 1))
        assert r4["interval_days"] == 1  # reset

    def test_tag_is_preserved_but_not_functional(self):
        """tag parameter is accepted but doesn't affect calculation."""
        r1 = schedule_review("tag_a", _make_history(5))
        r2 = schedule_review("tag_b", _make_history(5))
        assert r1["interval_days"] == r2["interval_days"]
