"""
SM-2 variant spaced-repetition scheduler.

Pure Python — no LLM, no DB.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List


def schedule_review(
    tag: str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute next review date, interval, and ease factor.

    SM-2 variant:
      - quality ∈ [0, 5]
      - ease_factor starts at 2.5, clamped to [1.3, ∞)
      - interval doubles on success (q >= 3), resets to 1 on failure (q < 3)
      - ease_factor adjusted per SM-2 formula on success; small penalty on failure

    Args:
        tag: The knowledge tag being reviewed.
        history: Chronological list of past reviews. Each entry is a dict with:
            - 'quality' (int): 0-5 rating of recall quality
            - 'date' (str, optional): ISO date string of the review

    Returns:
        {
            'next_review_date': str (ISO date),
            'interval_days': int,
            'ease_factor': float (rounded to 2 decimals),
        }
    """
    ease_factor: float = 2.5
    interval: int = 1

    if not history:
        next_date = date.today() + timedelta(days=interval)
        return {
            "next_review_date": next_date.isoformat(),
            "interval_days": interval,
            "ease_factor": round(ease_factor, 2),
        }

    # Replay history sequentially to compute current ease_factor and interval
    for review in history:
        q = int(review["quality"])
        if q >= 3:
            # Success — double the interval
            interval = max(interval * 2, 1)
            # SM-2 ease-factor update
            ease_factor += 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
            ease_factor = max(1.3, ease_factor)
        else:
            # Failure — reset interval, small ease-factor penalty
            interval = 1
            ease_factor = max(1.3, ease_factor - 0.15)

    # Cap interval to avoid multi-year gaps
    interval = min(interval, 365)

    next_date = date.today() + timedelta(days=interval)
    return {
        "next_review_date": next_date.isoformat(),
        "interval_days": interval,
        "ease_factor": round(ease_factor, 2),
    }
