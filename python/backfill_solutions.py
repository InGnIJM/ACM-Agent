"""
Backfill solutions for existing problems on Codeforces, LeetCode, Luogu, and NowCoder.

Usage:
    # Backfill a single platform
    python backfill_solutions.py --platform codeforces

    # Backfill all platforms
    python backfill_solutions.py --all

    # Backfill with custom count per problem
    python backfill_solutions.py --platform leetcode --count 30

    # Dry run (list what would be processed, no DB writes)
    python backfill_solutions.py --platform luogu --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# Ensure cwd is the python/ directory so imports work
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_solutions")

PLATFORM_SCRIPTS = {
    "codeforces": "crawlers.codeforces",
    "leetcode": "crawlers.leetcode",
    "luogu": "crawlers.luogu",
    "nowcoder": "crawlers.nowcoder",
}


def get_crawler(platform: str):
    """Import and instantiate the crawler for a given platform."""
    module_name = PLATFORM_SCRIPTS[platform]
    import importlib
    mod = importlib.import_module(module_name)
    # Each crawler module has a class named <Platform>Crawler
    class_name = f"{platform.capitalize()}Crawler"
    crawler_cls = getattr(mod, class_name)
    return crawler_cls()


def get_crawler_executor(platform: str):
    """Get a CrawlerExecutor wrapping the platform crawler."""
    from crawlers.base import CrawlerExecutor
    crawler = get_crawler(platform)
    return crawler, CrawlerExecutor(crawler)


async def get_problem_ids(platform: str) -> list[dict]:
    """Query the database for all problem sourceIds on a platform."""
    try:
        from prisma import Prisma
    except ImportError:
        logger.error("Prisma not installed. Install with: pip install prisma")
        return []

    prisma = Prisma()
    await prisma.connect()
    try:
        problems = await prisma.problem.find_many(
            where={"sourcePlatform": platform},
            select={"sourceId": True, "title": True},
        )
        return [{"sourceId": p.sourceId, "title": p.title} for p in problems]
    finally:
        await prisma.disconnect()


async def backfill_platform(
    platform: str,
    count: int = 20,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """Fetch solutions for all problems on a platform and save to data/raw/."""
    problems = await get_problem_ids(platform)

    if limit and limit > 0:
        problems = problems[:limit]

    if not problems:
        logger.info("No problems found for platform: %s", platform)
        return {"platform": platform, "fetched": 0, "errors": 0, "skipped": 0}

    logger.info(
        "Backfilling solutions for %d problems on %s (count=%d)",
        len(problems), platform, count,
    )

    crawler, executor = get_crawler_executor(platform)
    data_dir = Path("data/raw") / platform / "solutions"
    data_dir.mkdir(parents=True, exist_ok=True)

    fetched_total = 0
    errors_total = 0
    skipped_total = 0

    for i, p in enumerate(problems):
        source_id = p["sourceId"]
        title = p.get("title", "")
        logger.info(
            "[%d/%d] Fetching solutions for %s/%s: %s",
            i + 1, len(problems), platform, source_id, title,
        )

        try:
            if platform == "codeforces":
                # CF fetch_solutions accepts (source_id, max_editorials)
                result = executor.execute("fetch_solutions", source_id, count)
            elif platform == "nowcoder":
                # NC fetch_solutions accepts (source_id, max_pages)
                result = executor.execute("fetch_solutions", source_id, min(count // 10, 3))
            elif platform == "leetcode":
                result = executor.execute("fetch_solutions", source_id, count)
            else:
                result = executor.execute("fetch_solutions", source_id, min(count // 10, 3))

            if not result.success:
                logger.warning(
                    "  -> FAILED for %s: %s", source_id, result.error,
                )
                errors_total += 1
                continue

            data = result.data
            if not data or (isinstance(data, list) and len(data) == 0):
                logger.info("  -> No solutions found for %s", source_id)
                skipped_total += 1
                continue

            count_fetched = len(data) if isinstance(data, list) else 1
            fetched_total += count_fetched

            if not dry_run:
                safe_label = str(source_id).replace("/", "_").replace("\\", "_")
                from datetime import datetime, timezone
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                filename = f"{today}_{safe_label}.json"
                crawler.save_json(
                    data,
                    filename=filename,
                    sub_dir=f"{platform}/solutions",
                )
                logger.info(
                    "  -> Saved %d solutions to %s", count_fetched, filename,
                )
            else:
                logger.info(
                    "  -> [DRY RUN] Would save %d solutions for %s",
                    count_fetched, source_id,
                )

        except Exception as exc:
            logger.error("  -> ERROR for %s: %s", source_id, exc)
            errors_total += 1

    crawler.close()

    summary = {
        "platform": platform,
        "total_problems": len(problems),
        "fetched": fetched_total,
        "errors": errors_total,
        "skipped": skipped_total,
    }
    logger.info(
        "Backfill done for %s: %d solutions fetched, %d errors, %d skipped",
        platform, fetched_total, errors_total, skipped_total,
    )
    return summary


async def main_async(args: argparse.Namespace) -> None:
    platforms: list[str]
    if args.all:
        platforms = ["codeforces", "leetcode", "luogu", "nowcoder"]
    else:
        platforms = [args.platform]

    summaries = []
    for platform in platforms:
        summary = await backfill_platform(
            platform=platform,
            count=args.count,
            dry_run=args.dry_run,
            limit=args.limit,
        )
        summaries.append(summary)

    # Print summary
    print("\n" + "=" * 60)
    print("BACKFILL SUMMARY")
    print("=" * 60)
    total_fetched = sum(s["fetched"] for s in summaries)
    total_errors = sum(s["errors"] for s in summaries)
    total_skipped = sum(s["skipped"] for s in summaries)
    total_problems = sum(s["total_problems"] for s in summaries)
    for s in summaries:
        print(
            f"  {s['platform']:15s} | problems={s['total_problems']:4d} | "
            f"fetched={s['fetched']:4d} | errors={s['errors']:3d} | skipped={s['skipped']:3d}"
        )
    print("-" * 60)
    print(
        f"  {'TOTAL':15s} | problems={total_problems:4d} | "
        f"fetched={total_fetched:4d} | errors={total_errors:3d} | skipped={total_skipped:3d}"
    )
    print("=" * 60)


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Backfill solutions for existing problems",
    )
    parser.add_argument(
        "--platform",
        choices=["codeforces", "leetcode", "luogu", "nowcoder"],
        help="Target platform",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Backfill all platforms",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Max solutions to fetch per problem (default: 20)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of problems to process per platform",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without saving",
    )
    args = parser.parse_args(argv)

    if not args.platform and not args.all:
        parser.error("Either --platform or --all is required")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
