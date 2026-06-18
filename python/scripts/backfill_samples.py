"""
Sample backfill script — reads problems without samples from the database,
scrapes each problem's original page for sample test cases, and updates the DB.

Usage:
    python scripts/backfill_samples.py --platform luogu
    python scripts/backfill_samples.py --platform codeforces
    python scripts/backfill_samples.py --platform leetcode
    python scripts/backfill_samples.py --platform nowcoder
    python scripts/backfill_samples.py --all
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent dir to path for crawler imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawlers.base import CrawlResult
from crawlers.luogu import LuoguCrawler
from crawlers.codeforces import CodeforcesCrawler
from crawlers.leetcode import LeetCodeCrawler
from crawlers.nowcoder import NowCoderCrawler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Per-platform sample fetchers
# ──────────────────────────────────────────────


def _fetch_luogu_samples(crawler: LuoguCrawler, source_id: str) -> Optional[list]:
    """Fetch samples for a Luogu problem. Returns list of [input, output] pairs."""
    r = crawler.fetch_problem(source_id)
    if r.success and r.data:
        return r.data.get("samples")
    return None


def _fetch_cf_samples(crawler: CodeforcesCrawler, source_id: str) -> Optional[list]:
    """Fetch samples for a CF problem by scraping the problem page."""
    # The crawler's fetch_problem now includes samples from HTML
    r = crawler.fetch_problem(source_id)
    if r.success and r.data:
        return r.data.get("samples")
    return None


def _fetch_lc_samples(crawler: LeetCodeCrawler, source_id: str) -> Optional[str]:
    """Fetch sample test cases from LeetCode GraphQL."""
    r = crawler.fetch_problem(source_id)
    if r.success and r.data:
        return r.data.get("exampleTestcases") or r.data.get("sampleTestCase")
    return None


def _fetch_nc_samples(crawler: NowCoderCrawler, source_id: str) -> Optional[str]:
    """Fetch samples from a NowCoder problem page."""
    r = crawler.fetch_problem(source_id)
    if r.success and r.data:
        return r.data.get("samples")
    return None


# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────


def _get_db():
    """Return a connected Prisma client."""
    try:
        from prisma import Prisma
    except ImportError:
        logger.error("Prisma client not available. Install: pip install prisma")
        sys.exit(1)

    import asyncio

    async def _connect():
        client = Prisma()
        await client.connect()
        return client

    return asyncio.run(_connect())


async def _get_empty_problems(db, platform: str) -> List[Dict[str, Any]]:
    """Return problems on *platform* that lack sample data."""
    problems = await db.problem.find_many(
        where={
            "sourcePlatform": platform,
            "OR": [
                {"fullContent": None},
                {"fullContent": ""},
                {"fullContent": {"not": {"contains": "[样例]"}}},
            ],
        },
        select={"id": True, "sourceId": True, "sourceUrl": True, "fullContent": True},
        take=100,
    )
    return [{"id": p.id, "sourceId": p.sourceId, "sourceUrl": p.sourceUrl, "fullContent": p.fullContent} for p in problems]


async def _update_full_content(db, problem_id: str, full_content: str):
    """Update a problem's fullContent in the database."""
    await db.problem.update(
        where={"id": problem_id},
        data={"fullContent": full_content},
    )


# ──────────────────────────────────────────────
# Backfill logic
# ──────────────────────────────────────────────


def _format_samples_as_markdown(samples, platform: str) -> str:
    """Format sample data as a Markdown [样例] section."""
    if not samples:
        return ""

    lines = ["[样例]"]

    if platform == "luogu" or platform == "codeforces":
        # Luogu/CF: list of [input_str, output_str] pairs
        if isinstance(samples, list):
            for i, pair in enumerate(samples):
                if isinstance(pair, list) and len(pair) >= 2:
                    lines.append(f"输入 #{i + 1}")
                    lines.append("```")
                    lines.append(str(pair[0]).strip())
                    lines.append("```")
                    lines.append("")
                    lines.append(f"输出 #{i + 1}")
                    lines.append("```")
                    lines.append(str(pair[1]).strip())
                    lines.append("```")
                elif isinstance(pair, str):
                    lines.append(pair)
        else:
            lines.append(str(samples))

    elif platform == "leetcode" or platform == "nowcoder":
        # LC/NC: string with raw test cases
        if isinstance(samples, str):
            lines.append("```")
            lines.append(samples.strip())
            lines.append("```")
        else:
            lines.append(str(samples))

    return "\n".join(lines)


def backfill_platform(platform: str, limit: int = 50, dry_run: bool = False):
    """Backfill samples for problems on *platform*."""
    import asyncio

    logger.info("=== Backfilling %s (limit=%d, dry_run=%s) ===", platform, limit, dry_run)

    # ── Set up crawler ──────────────────────────
    if platform == "luogu":
        crawler = LuoguCrawler()
        fetch_fn = _fetch_luogu_samples
    elif platform == "codeforces":
        crawler = CodeforcesCrawler()
        fetch_fn = _fetch_cf_samples
    elif platform == "leetcode":
        crawler = LeetCodeCrawler()
        fetch_fn = _fetch_lc_samples
    elif platform == "nowcoder":
        crawler = NowCoderCrawler()
        fetch_fn = _fetch_nc_samples
    else:
        logger.error("Unknown platform: %s", platform)
        return

    try:
        # ── Query DB ─────────────────────────────
        db = _get_db()
        problems = asyncio.run(_get_empty_problems(db, platform))
        problems = problems[:limit]
        logger.info("Found %d problems without samples on %s", len(problems), platform)

        if not problems:
            logger.info("No problems need samples. Done.")
            return

        updated = 0
        failed = 0
        skipped = 0

        for i, prob in enumerate(problems):
            pid = prob["sourceId"]
            logger.info("[%d/%d] %s %s", i + 1, len(problems), platform, pid)

            # Skip if we can't find a source URL
            if not prob.get("sourceUrl"):
                logger.warning("  No source URL, skipping")
                skipped += 1
                continue

            # Fetch samples from the original problem page
            try:
                samples = fetch_fn(crawler, pid)
            except Exception as exc:
                logger.error("  Fetch failed: %s", exc)
                failed += 1
                continue

            if not samples:
                logger.warning("  No samples found on page")
                skipped += 1
                continue

            # Format and update
            sample_section = _format_samples_as_markdown(samples, platform)
            current = prob.get("fullContent") or ""

            # Avoid duplicating existing samples
            if "[样例]" in (current or ""):
                # Replace existing sample section
                import re
                current = re.sub(r"\[样例\].*", sample_section, current, flags=re.DOTALL)
            else:
                current = current.rstrip() + "\n\n" + sample_section

            if dry_run:
                logger.info("  [DRY RUN] Would update: +%d chars", len(sample_section))
            else:
                asyncio.run(_update_full_content(db, prob["id"], current))
                logger.info("  Updated: +%d chars sample section", len(sample_section))

            updated += 1
            time.sleep(0.5)  # rate limit

        logger.info("Done: %d updated, %d failed, %d skipped", updated, failed, skipped)

    finally:
        crawler.close()
        try:
            import asyncio
            asyncio.run(db.disconnect())
        except Exception:
            pass


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Backfill problem samples from original pages")
    parser.add_argument("--platform", default=None, help="Single platform to process")
    parser.add_argument("--all", action="store_true", help="Process all platforms")
    parser.add_argument("--limit", type=int, default=50, help="Max problems per platform")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    args = parser.parse_args()

    if args.all:
        platforms = ["luogu", "codeforces", "leetcode", "nowcoder"]
    elif args.platform:
        platforms = [args.platform]
    else:
        parser.print_help()
        sys.exit(1)

    for plat in platforms:
        backfill_platform(plat, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
