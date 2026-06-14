"""
ACM Agent 六维能力公式 + 风格分类 + 综合评分。

Pure Python — no LLM, no DB.
"""

from __future__ import annotations

import math
from typing import Dict, List, Set

import numpy as np

# ============================================================
# Constants
# ============================================================

STYLE_BONUS: Dict[str, float] = {
    "grinder": 0.6,
    "deep_diver": 0.8,
    "specialist": 0.5,
    "balanced": 1.0,
}

BASIC_TAGS: List[str] = [
    "prefix_sum",
    "two_pointers",
    "binary_search",
    "sliding_window",
    "binary_tree_traverse",
    "bst",
    "hash_map",
    "heap",
]


# ============================================================
# Helpers
# ============================================================

def _sigmoid(x: float, center: float = 0.5, slope: float = 10.0) -> float:
    """Logistic sigmoid centred at `center` with steepness `slope`."""
    try:
        return 1.0 / (1.0 + math.exp(-slope * (x - center)))
    except OverflowError:
        return 0.0 if x < center else 1.0


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den != 0 else default


# ============================================================
# 1. Coverage — 标签覆盖度
# ============================================================

def calc_coverage(user_tags: Set[str], all_tags: Set[str]) -> float:
    """Jaccard-like coverage: |user_tags ∩ all_tags| / |all_tags|.

    Returns 0.0 when `all_tags` is empty.
    Range: [0, 1].
    """
    if not all_tags:
        return 0.0
    return len(user_tags & all_tags) / len(all_tags)


# ============================================================
# 2. Category Coverage
# ============================================================

def calc_category_coverage(
    user_tags: Set[str],
    taxonomy: Dict[str, Set[str]],
) -> Dict[str, float]:
    """Per-category coverage.

    taxonomy: {category_name → set_of_tags}
    Returns: {category_name → coverage_ratio}
    """
    result: Dict[str, float] = {}
    for category, tags in taxonomy.items():
        if not tags:
            result[category] = 0.0
        else:
            result[category] = len(user_tags & tags) / len(tags)
    return result


# ============================================================
# 3. Proficiency — 熟练度
# ============================================================

def calc_proficiency(
    ac_count: int,
    total_count: int,
    avg_difficulty: float,
    days_since_last: float,
) -> float:
    """Composite proficiency score.

    0.40 * sigmoid(ac_rate, 0.5, 10)
    + 0.30 * min(avg_difficulty / 10, 1)
    + 0.20 * min(ln(1+ac_count) / ln(31), 1)
    + 0.10 * exp(-0.023 * days_since_last)

    Range: roughly [0, 1].
    """
    ac_rate = _safe_div(ac_count, total_count)

    w_rate = 0.40 * _sigmoid(ac_rate, center=0.5, slope=10.0)
    w_diff = 0.30 * min(avg_difficulty / 10.0, 1.0)
    w_vol = 0.20 * min(math.log(1 + ac_count) / math.log(31), 1.0)
    w_recency = 0.10 * math.exp(-0.023 * max(days_since_last, 0))

    return w_rate + w_diff + w_vol + w_recency


# ============================================================
# 4. Ceiling — 能力天花板 (P90 难度)
# ============================================================

def calc_ceiling(records: List[Dict]) -> float:
    """90th percentile of problem difficulties solved.

    records: list of dicts, each must have a 'difficulty' key (numeric, 0-10).
    Returns 0.0 when fewer than 5 records.
    """
    if len(records) < 5:
        return 0.0
    diffs = [r["difficulty"] for r in records]
    return float(np.percentile(diffs, 90))


# ============================================================
# 5. Efficiency — 效率
# ============================================================

def calc_efficiency(records: List[Dict]) -> float:
    """Efficiency based on first-AC rate and average retries.

    0.6 * first_ac_rate + 0.4 * (1 - min(avg_retries / 5, 1))

    records: list of dicts, each with:
        - 'first_ac' (bool): whether solved on first attempt
        - 'retries' (int): number of retry attempts
    Returns 0.0 when no records.
    """
    if not records:
        return 0.0

    first_ac_count = sum(1 for r in records if r.get("first_ac", False))
    first_ac_rate = first_ac_count / len(records)

    avg_retries = sum(r.get("retries", 0) for r in records) / len(records)
    retry_penalty = min(avg_retries / 5.0, 1.0)

    return 0.6 * first_ac_rate + 0.4 * (1.0 - retry_penalty)


# ============================================================
# 6. Momentum — 动量（线性回归斜率）
# ============================================================

def calc_momentum(
    daily_stats: List[Dict],
    window: int = 30,
) -> float:
    """Linear-regression slope of daily AC count, normalised to [-1, 1].

    daily_stats: list of dicts with 'ac_count' (int).
        Ordered chronologically. At most `window` entries used (most recent).
    Returns 0.0 when fewer than 2 data points.
    """
    series = daily_stats[-window:] if len(daily_stats) > window else daily_stats
    if len(series) < 2:
        return 0.0

    xs = np.arange(len(series), dtype=np.float64)
    ys = np.array([d["ac_count"] for d in series], dtype=np.float64)

    # linear regression slope = cov(x,y) / var(x)
    x_mean = xs.mean()
    y_mean = ys.mean()
    cov = np.sum((xs - x_mean) * (ys - y_mean))
    var_x = np.sum((xs - x_mean) ** 2)
    if var_x == 0:
        return 0.0
    slope = cov / var_x

    # normalise: slope / 0.5, clip to [-1, 1]
    normalised = slope / 0.5
    return float(max(-1.0, min(1.0, normalised)))


# ============================================================
# 7. Style Classification
# ============================================================

def classify_style(
    total_solved: int,
    unique_tags: int,
    avg_proficiency: float,
    top3_concentration: float,
    avg_difficulty: float,
) -> str:
    """Classify user into one of four problem-solving styles.

    - grinder:     high volume, low difficulty — quantity over depth
    - deep_diver:  high difficulty, narrow tag range — depth over breadth
    - specialist:  concentrated in top tag areas
    - balanced:    none of the above extremes

    Priority order: grinder > deep_diver > specialist > balanced
    """
    if total_solved >= 200 and avg_difficulty <= 4.0:
        return "grinder"

    if avg_difficulty >= 7.0 and unique_tags <= 8:
        return "deep_diver"

    if top3_concentration >= 0.5:
        return "specialist"

    return "balanced"


# ============================================================
# 8. Overall Score
# ============================================================

def calc_overall_score(
    coverage: float,
    avg_proficiency: float,
    ceiling: float,
    efficiency: float,
    style: str,
    momentum: float,
) -> float:
    """Weighted composite score incorporating all six dimensions + style bonus.

    Base = 0.20*coverage + 0.25*proficiency + 0.20*(ceiling/10) + 0.20*efficiency
    Style multiplier: STYLE_BONUS[style]  (default 1.0 for unknown)
    Momentum adjustment: (1 + 0.10 * momentum)

    Returns roughly [0, 1.1] — can slightly exceed 1.0 with positive momentum.
    """
    base = (
        0.20 * coverage
        + 0.25 * avg_proficiency
        + 0.20 * min(ceiling / 10.0, 1.0)
        + 0.20 * efficiency
    )
    bonus = STYLE_BONUS.get(style, 1.0)
    momentum_factor = 1.0 + 0.10 * momentum

    return base * bonus * momentum_factor
