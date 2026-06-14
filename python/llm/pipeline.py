"""Problem processing pipeline: normalize -> summarize -> embed.

Provides ProblemPipeline, the main orchestrator that takes raw ACM problems
through the full enrichment flow: tag/difficulty normalization, LLM summarization,
and embedding generation.  Also includes a CLI for batch processing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .embedder import ProblemEmbedder
from .normalizer import DifficultyNormalizer, TagNormalizer
from .summarizer import ProblemSummarizer

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    """Return the repository root (two levels above this file)."""
    return Path(__file__).resolve().parent.parent.parent


class ProblemPipeline:
    """Orchestrates tag/difficulty normalization, LLM summarization and embedding.

    Parameters
    ----------
    db:
        Database handle / connection (placeholder -- used by ``_upsert_problem``).
    llm:
        A ``ChatOpenAI`` (or compatible) client pointed at DeepSeek for summarization.
    openai_client:
        An OpenAI / AsyncOpenAI client exposing ``client.embeddings.create`` for
        ``text-embedding-3-small`` embeddings.
    """

    def __init__(self, db: Any, llm: Any, openai_client: Any) -> None:
        self._db = db
        self._tag_normalizer = TagNormalizer()
        self._diff_normalizer = DifficultyNormalizer()
        self._summarizer = ProblemSummarizer(
            deepseek_client=llm, normalizer=self._tag_normalizer
        )
        self._embedder = ProblemEmbedder(openai_client)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_problem(self, raw_problem: Dict[str, Any]) -> Dict[str, Any]:
        """Run the full enrichment pipeline on a single raw problem.

        1. Normalize tags (deterministic, taxonomy-backed) and difficulty.
        2. Generate LLM summary (solution approach, key points, pitfalls ...).
        3. Generate embeddings (parent vector from summary, content vector from
           ``full_content``).

        Returns a *new* enriched dict -- the input dict is not mutated.
        """
        problem: Dict[str, Any] = dict(raw_problem)
        platform: str = problem.get("platform", "unknown")

        # ---- step 1: deterministic normalization ---------------------------
        raw_tags: List[str] = problem.get("tags_platform", [])
        problem["tags_normalized"] = self._tag_normalizer.normalize_tags(
            platform, raw_tags
        )
        problem["difficulty_normalized"] = self._diff_normalizer.normalize(
            platform, problem.get("difficulty_raw", "")
        )

        # ---- step 2: LLM summary -------------------------------------------
        # Save deterministic values so the LLM's own tags/difficulty do not
        # overwrite them.
        det_tags = problem["tags_normalized"]
        det_diff = problem["difficulty_normalized"]

        summary_result: Dict[str, Any] = await self._summarizer.summarize(problem)
        problem.update(summary_result)

        # Restore deterministic normalizer output (step 1 wins over LLM)
        problem["tags_normalized"] = det_tags
        problem["difficulty_normalized"] = det_diff

        # Build a single textual summary column for the parent embedding
        problem["solution_summary"] = self._summarizer._format_summary(summary_result)

        # ---- step 3: embeddings (parent + content) -------------------------
        enriched_list: List[Dict[str, Any]] = await self._embedder.embed_problems(
            [problem]
        )
        return enriched_list[0]

    async def process_batch(self, problems: List[Dict[str, Any]]) -> Dict[str, int]:
        """Process a batch of problems with per-problem error isolation.

        Each problem that succeeds is persisted via ``_upsert_problem``.
        Failures are logged but never abort the batch.

        Returns
        -------
        dict
            ``{"processed": N, "errors": M}``
        """
        processed = 0
        errors = 0

        for problem in problems:
            try:
                enriched = await self.process_problem(problem)
                await self._upsert_problem(enriched)
                processed += 1
            except Exception:
                logger.exception(
                    "Failed to process problem %s (platform=%s)",
                    problem.get("source_id", "?"),
                    problem.get("platform", "?"),
                )
                errors += 1

        return {"processed": processed, "errors": errors}

    async def _upsert_problem(self, problem: Dict[str, Any]) -> None:
        """Persist an enriched problem to the database.

        Placeholder -- in production this delegates to Prisma (or equivalent)
        for an upsert operation.
        """
        # TODO: wire up Prisma upsert
        pass


# ======================================================================
# CLI
# ======================================================================


def _read_problems(
    platform: str, date_str: str, base_dir: Path
) -> List[Dict[str, Any]]:
    """Read all ``*.json`` files from ``data/raw/{platform}/{date}/problems/``."""
    problems_dir = base_dir / "data" / "raw" / platform / date_str / "problems"
    if not problems_dir.is_dir():
        raise FileNotFoundError(
            f"Problems directory not found: {problems_dir}"
        )

    problems: List[Dict[str, Any]] = []
    for json_file in sorted(problems_dir.glob("*.json")):
        with open(json_file, "r", encoding="utf-8") as fh:
            problems.append(json.load(fh))
    return problems


def _write_problems(
    problems: List[Dict[str, Any]],
    platform: str,
    date_str: str,
    base_dir: Path,
) -> None:
    """Write enriched problems back to ``data/raw/{platform}/{date}/problems/``."""
    problems_dir = base_dir / "data" / "raw" / platform / date_str / "problems"
    problems_dir.mkdir(parents=True, exist_ok=True)

    for problem in problems:
        source_id = problem.get("source_id", "unknown")
        output_path = problems_dir / f"{source_id}.json"
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(problem, fh, ensure_ascii=False, indent=2)


async def _run_process(
    *,
    platform: str,
    count: int,
    date_str: str,
    db: Any,
    llm: Any,
    openai_client: Any,
    base_dir: Optional[Path] = None,
) -> Dict[str, int]:
    """Execute the ``process`` action."""
    if base_dir is None:
        base_dir = _project_root()

    problems = _read_problems(platform, date_str, base_dir)
    if count > 0:
        problems = problems[:count]

    logger.info(
        "Processing %d problems from %s/%s", len(problems), platform, date_str
    )

    pipeline = ProblemPipeline(db, llm, openai_client)
    stats = await pipeline.process_batch(problems)
    logger.info("Batch complete: %s", stats)
    return stats


async def _run_re_embed(
    *,
    platform: str,
    count: int,
    date_str: str,
    openai_client: Any,
    base_dir: Optional[Path] = None,
) -> Dict[str, int]:
    """Execute the ``re-embed`` action."""
    if base_dir is None:
        base_dir = _project_root()

    problems = _read_problems(platform, date_str, base_dir)
    if count > 0:
        problems = problems[:count]

    logger.info(
        "Re-embedding %d problems from %s/%s", len(problems), platform, date_str
    )

    embedder = ProblemEmbedder(openai_client)
    enriched = await embedder.embed_problems(problems)
    _write_problems(enriched, platform, date_str, base_dir)

    logger.info("Re-embed complete: %d problems", len(enriched))
    return {"re_embedded": len(enriched)}


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser (usable for testing)."""
    parser = argparse.ArgumentParser(
        description="ACM Problem Processing Pipeline",
    )
    parser.add_argument(
        "--platform",
        required=True,
        help="Platform name (luogu, leetcode, codeforces, atcoder, nowcoder)",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["process", "re-embed"],
        help="Action to perform",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Max problems to process (0 = unlimited)",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Date subdirectory in YYYY-MM-DD format (default: today)",
    )
    return parser


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments (injectable *argv* for testing)."""
    parser = build_parser()
    return parser.parse_args(argv)


async def main_async(argv: Optional[List[str]] = None) -> None:
    """Async CLI entry point."""
    args = parse_args(argv)

    # Lazy imports so the module can be imported without these deps present
    from langchain_openai import ChatOpenAI
    from openai import AsyncOpenAI

    base_dir = _project_root()

    if args.action == "process":
        # These clients must be configured via env vars:
        #   DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL   for ChatOpenAI
        #   OPENAI_API_KEY / OPENAI_BASE_URL        for AsyncOpenAI
        llm = ChatOpenAI(
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key="placeholder",  # resolved from env
        )
        openai_client = AsyncOpenAI()
        db = None  # not wired yet
        stats = await _run_process(
            platform=args.platform,
            count=args.count,
            date_str=args.date,
            db=db,
            llm=llm,
            openai_client=openai_client,
            base_dir=base_dir,
        )
        print(json.dumps(stats))
    elif args.action == "re-embed":
        openai_client = AsyncOpenAI()
        stats = await _run_re_embed(
            platform=args.platform,
            count=args.count,
            date_str=args.date,
            openai_client=openai_client,
            base_dir=base_dir,
        )
        print(json.dumps(stats))


def main(argv: Optional[List[str]] = None) -> None:
    """Synchronous CLI entry point."""
    asyncio.run(main_async(argv))


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main()
