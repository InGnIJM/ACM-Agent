"""CLI wrapper for TrainingAgent — invoked by NestJS PythonService.

Usage:
    python agents/training_agent_cli.py --input '{"userId":"...","profileId":"..."}'

Output (stdout, last line JSON):
    {"user_id": "...", "plan": {...}, "candidate_count": N, "errors": [...]}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _build_state(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build initial TrainingState from input JSON."""
    return {
        "user_id": input_data.get("userId", input_data.get("user_id", "")),
        "profile_id": input_data.get("profileId", input_data.get("profile_id", "")),
        "plan_days": int(input_data.get("planDays", 7)),
        "daily_target": int(input_data.get("dailyTarget", 5)),
        "profile": {},
        "weak_tags_ranked": [],
        "candidate_problems": [],
        "weekly_plan": {},
        "difficulty_curve": [],
        "targets": {},
        "plan_data": {},
        "errors": [],
    }


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Training Agent CLI")
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="JSON string with userId, profileId, planDays, dailyTarget",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=os.environ.get("TRAINING_API_URL", "http://localhost:3000"),
        help="NestJS backend URL for vector search API",
    )
    args = parser.parse_args(argv)
    input_data: Dict[str, Any] = json.loads(args.input or "{}")

    from agents.training_agent import TrainingAgent

    agent = TrainingAgent(api_url=args.api_url)

    state = _build_state(input_data)
    result = agent.graph.invoke(state)

    plan_data: Dict[str, Any] = result.get("plan_data", {})
    output = {
        "user_id": input_data.get("userId", input_data.get("user_id", "")),
        "profile_id": input_data.get("profileId", input_data.get("profile_id", "")),
        "plan": plan_data.get("plan", result.get("weekly_plan", {})),
        "candidate_count": plan_data.get("candidate_count", len(result.get("candidate_problems", []))),
        "targets": result.get("targets", {}),
        "difficulty_curve": result.get("difficulty_curve", []),
        "errors": result.get("errors", []),
    }

    # Print final JSON line (PythonService reads last non-empty line)
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main()
