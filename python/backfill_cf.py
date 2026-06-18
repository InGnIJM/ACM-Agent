"""
Backfill script: re-fetch detail for ALL Codeforces problems and re-import them.

Reads existing problem JSONs from data/raw/codeforces/problems/ to collect
source IDs, then re-scrapes each problem page for fresh description,
input_format, output_format, note, and samples. Output is saved as
timestamped JSON files ready for DataImporter.

Usage:
    python backfill_cf.py              # backfill all problems, save JSON only
    python backfill_cf.py --import     # also run DataImporter after backfill
    python backfill_cf.py --ids 1742E,1840C  # backfill specific problems
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_cf")


# ──────────────────────────────────────────────
# Problem ID collection
# ──────────────────────────────────────────────


def collect_problem_ids() -> List[str]:
    """Collect all unique Codeforces problem IDs from saved JSON files.

    Returns a sorted list of problem source IDs (e.g. ``"1742E"``).
    """
    data_dir = Path("data/raw/codeforces/problems")
    if not data_dir.exists():
        logger.warning("No data directory: %s", data_dir)
        return []

    ids: set[str] = set()
    for fpath in sorted(data_dir.glob("*.json")):
        # Skip bulk list / progress / backfill files to avoid double-counting
        name = fpath.name
        if name.startswith(("bulk_list_", "bulk_detail_progress_", "backfill_")):
            continue
        try:
            payload = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping %s: %s", fpath, exc)
            continue

        items = payload if isinstance(payload, list) else [payload]
        for prob in items:
            cid = prob.get("contestId", "")
            idx = prob.get("index", "")
            if cid and idx:
                ids.add(f"{cid}{idx}")

    return sorted(ids)


# ──────────────────────────────────────────────
# Backfill logic
# ──────────────────────────────────────────────


async def backfill(
    problem_ids: List[str],
    do_import: bool = False,
) -> int:
    """Re-fetch detail for each problem and save updated JSONs.

    Args:
        problem_ids: List of CF problem source IDs (e.g. ``["1742E"]``).
        do_import: If True, also run DataImporter after saving.

    Returns:
        Number of problems successfully backfilled.
    """
    from crawlers.codeforces import CodeforcesCrawler
    from crawlers.base import CrawlerExecutor

    crawler = CodeforcesCrawler()
    executor = CrawlerExecutor(crawler)

    enriched: list = []
    failed: list = []

    for i, sid in enumerate(problem_ids):
        logger.info("[%d/%d] Fetching detail for %s ...", i + 1, len(problem_ids), sid)
        result = executor.execute("fetch_problem", str(sid))
        if result.success and result.data:
            enriched.append(dict(result.data))
            logger.info("  -> OK: %s", result.data.get("name", sid))
        else:
            failed.append(sid)
            logger.warning("  -> FAILED: %s", result.error)

    if not enriched:
        logger.error("No problems were successfully backfilled.")
        crawler.close()
        return 0

    # ── Save ──────────────────────────────────────────────────
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag = f"{today}_backfill"

    # Bulk file for bulk import
    crawler.save_json(enriched, filename=f"{tag}.json", sub_dir="codeforces/problems")
    logger.info(
        "Saved %d enriched problems to data/raw/codeforces/problems/%s.json",
        len(enriched), tag,
    )

    # Individual files (one per problem) for selective imports
    for prob in enriched:
        cid = prob.get("contestId", "")
        idx = prob.get("index", "")
        sid = f"{cid}{idx}" if cid and idx else ""
        if sid:
            crawler.save_json(prob, filename=f"{today}_backfill_{sid}.json",
                              sub_dir="codeforces/problems")

    # ── Import (optional) ─────────────────────────────────────
    if do_import:
        try:
            from prisma import Prisma  # type: ignore[import-untyped]
        except (ImportError, RuntimeError):
            logger.error(
                "Prisma client not available. Install with: "
                "pip install prisma, then run: prisma generate"
            )
            crawler.close()
            return len(enriched)

        from crawlers.base import DataImporter

        prisma = Prisma()
        await prisma.connect()
        try:
            importer = DataImporter(prisma)
            imported = await importer.import_problems("codeforces", today)
            logger.info("Imported %d problems into database.", imported)
        except Exception as exc:
            logger.error("Import failed: %s", exc)
        finally:
            await prisma.disconnect()

    crawler.close()

    if failed:
        logger.warning("Failed to backfill %d problems: %s", len(failed), failed)

    return len(enriched)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Backfill Codeforces problem details",
    )
    parser.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        help="Also run DataImporter to upsert into the database",
    )
    parser.add_argument(
        "--ids",
        default=None,
        help="Comma-separated list of problem IDs (e.g. '1742E,1840C'). "
             "If omitted, reads all IDs from existing JSON files.",
    )
    parser.add_argument(
        "--data-dir",
        default="data/raw",
        help="Root data directory (default: data/raw)",
    )
    args = parser.parse_args(argv)

    if args.ids:
        problem_ids = [s.strip() for s in args.ids.split(",") if s.strip()]
    else:
        problem_ids = collect_problem_ids()

    if not problem_ids:
        print("No problem IDs found. Use --ids to specify manually, "
              "or ensure data/raw/codeforces/problems/ contains JSON files.")
        sys.exit(1)

    logger.info("Backfilling %d problem(s)", len(problem_ids))
    count = asyncio.run(backfill(problem_ids, do_import=args.do_import))
    print(f"\nBackfill complete: {count} problem(s) enriched.")

    if not args.do_import:
        print("Run with --import to also upsert into the database.")
        print("Or run: python crawlers/codeforces.py --action import")


if __name__ == "__main__":
    main()
