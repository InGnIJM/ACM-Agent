"""
Backfill fullContent for LeetCode problems with Chinese content.

Re-fetches each LeetCode problem via GraphQL (with zh-CN Accept-Language),
rebuilds fullContent from the fresh data, and updates the database.

Usage:
    python backfill_leetcode_content.py              # backfill all LC problems
    python backfill_leetcode_content.py --limit 10   # backfill first 10
    python backfill_leetcode_content.py --dry-run    # preview without DB writes
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

# Ensure cwd is the python/ directory so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_lc_content")

# Load .env for DATABASE_URL
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key.strip() and not os.environ.get(key.strip()):
                    os.environ[key.strip()] = val.strip()


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:jm050711@localhost:5432/acm_agent",
)


def get_db_connection():
    """Create a PostgreSQL connection from DATABASE_URL."""
    # psycopg2 uses DSN string, replace postgresql:// with postgres:// for older libs
    dsn = DATABASE_URL
    return psycopg2.connect(dsn)


def get_leetcode_problems(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Query the database for all LeetCode problems."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, source_id, title, full_content, raw_detail
                FROM problems
                WHERE source_platform = 'leetcode'
                ORDER BY created_at ASC
                """
            )
            rows = cur.fetchall()
            result = [dict(r) for r in rows]
            if limit and limit > 0:
                result = result[:limit]
            return result
    finally:
        conn.close()


def update_full_content(problem_id: str, full_content: str) -> bool:
    """Update the fullContent field for a problem in the database."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE problems
                SET full_content = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (full_content, problem_id),
            )
            conn.commit()
            updated = cur.rowcount
            return updated > 0
    except Exception as exc:
        logger.error("DB update failed for %s: %s", problem_id, exc)
        conn.rollback()
        return False
    finally:
        conn.close()


def build_full_content(record: Dict[str, Any]) -> str:
    """Build fullContent from a LeetCode crawl record.

    Ported from crawler.controller.ts buildFullContent(), LeetCode-specific logic.
    """
    parts: List[str] = []

    # Chinese content (preferred by fetch_problem)
    content = record.get("content") or ""

    # HTML entity decoding (same as TS version)
    if content and content.strip().startswith("<"):
        content = content \
            .replace("&#39;", "'") \
            .replace("&#x27;", "'") \
            .replace("&apos;", "'") \
            .replace("&quot;", '"') \
            .replace("&lt;", "<") \
            .replace("&gt;", ">") \
            .replace("&amp;", "&") \
            .replace("&nbsp;", " ") \
            .replace("&#8217;", "'") \
            .replace("&#8216;", "'") \
            .replace("&#8220;", '"') \
            .replace("&#8221;", '"') \
            .replace("&#8230;", "...") \
            .replace("&#xA0;", " ")
        content = re.sub(r"<[^>]+>", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

    # Build sections
    if content:
        parts.append(f"[描述]\n{content}")

    # Sample test cases
    sample_lines: List[str] = []
    sample_testcase = record.get("sampleTestCase") or ""
    example_testcases = record.get("exampleTestcases") or ""

    if sample_testcase:
        sample_lines.append(f"输入\n```\n{sample_testcase}\n```")
    if example_testcases:
        sample_lines.append(f"输出\n```\n{example_testcases}\n```")

    if sample_lines:
        separator = "\n\n"
        parts.append(f"[样例]\n{separator.join(sample_lines)}")

    # Hints
    hints = record.get("hints") or []
    if hints:
        if isinstance(hints, list):
            hint_text = "\n".join(
                f"提示 {i + 1}: {h}" for i, h in enumerate(hints)
            )
        else:
            hint_text = str(hints)
        parts.append(f"[提示]\n{hint_text}")

    # Difficulty
    difficulty = record.get("difficulty") or ""
    if difficulty:
        parts.append(f"[难度]\n{difficulty}")

    # Topic Tags
    topic_tags = record.get("topicTags") or []
    if topic_tags:
        tags_text = ", ".join(
            t.get("name") or t.get("slug") or str(t)
            for t in topic_tags
            if isinstance(t, dict)
        )
        if tags_text:
            parts.append(f"[标签]\n{tags_text}")

    # Code snippets (first 3 languages)
    code_snippets = record.get("codeSnippets") or []
    if code_snippets:
        snippet_parts = []
    return "\n\n".join(parts) if parts else (content or "")


def backfill(
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Main backfill logic: re-fetch and update all LeetCode problems."""
    from crawlers.leetcode import LeetCodeCrawler
    from crawlers.base import CrawlerExecutor

    problems = get_leetcode_problems(limit)
    if not problems:
        logger.info("No LeetCode problems found in database")
        return {"total": 0, "backfilled": 0, "errors": 0, "skipped": 0}

    logger.info(
        "Found %d LeetCode problems in DB%s",
        len(problems),
        f" (limited to {limit})" if limit else "",
    )

    crawler = LeetCodeCrawler()
    executor = CrawlerExecutor(crawler)

    backfilled = 0
    errors = 0
    skipped = 0

    try:
        for i, p in enumerate(problems):
            source_id = p["source_id"]
            title = p.get("title", "")

            # Extract titleSlug from raw_detail for the GraphQL query
            raw_detail = p.get("raw_detail") or {}
            if isinstance(raw_detail, str):
                import json
                try:
                    raw_detail = json.loads(raw_detail)
                except (json.JSONDecodeError, TypeError):
                    raw_detail = {}
            title_slug = ""
            if isinstance(raw_detail, dict):
                title_slug = raw_detail.get("titleSlug") or raw_detail.get("slug") or ""

            if not title_slug:
                logger.warning(
                    "  -> No titleSlug found for %s, skipping", source_id,
                )
                skipped += 1
                continue

            logger.info(
                "[%d/%d] Re-fetching %s (slug=%s): %s",
                i + 1, len(problems), source_id, title_slug, title,
            )

            try:
                result = executor.execute("fetch_problem", str(title_slug))

                if not result.success or not result.data:
                    logger.warning(
                        "  -> FAILED for %s: %s", source_id, result.error or "no data",
                    )
                    errors += 1
                    continue

                data = result.data
                new_content = build_full_content(data)

                if not new_content:
                    logger.warning(
                        "  -> Empty content for %s, skipping", source_id,
                    )
                    skipped += 1
                    continue

                has_chinese = any(ord(ch) > 0x4e00 for ch in new_content)
                content_len = len(new_content)
                old_len = len(p.get("full_content") or "")

                logger.info(
                    "  -> content_len=%d, old_len=%d, has_chinese=%s",
                    content_len, old_len, has_chinese,
                )

                if not has_chinese:
                    logger.warning(
                        "  -> NO Chinese content for %s (may still be English)",
                        source_id,
                    )

                if dry_run:
                    logger.info("  -> [DRY RUN] Would update %s", source_id)
                    backfilled += 1
                else:
                    ok = update_full_content(p["id"], new_content)
                    if ok:
                        backfilled += 1
                        logger.info("  -> Updated fullContent for %s", source_id)
                    else:
                        errors += 1

            except Exception as exc:
                logger.error("  -> ERROR for %s: %s", source_id, exc)
                errors += 1
                import time
                time.sleep(2)  # rate limiting pause on errors

    finally:
        crawler.close()

    summary = {
        "total": len(problems),
        "backfilled": backfilled,
        "errors": errors,
        "skipped": skipped,
    }
    logger.info(
        "Backfill done: %d total, %d backfilled, %d errors, %d skipped",
        summary["total"], summary["backfilled"], summary["errors"], summary["skipped"],
    )
    return summary


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Backfill LeetCode fullContent with Chinese content",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of problems to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to DB",
    )
    args = parser.parse_args(argv)

    summary = backfill(
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 60)
    print("LEETCODE CONTENT BACKFILL SUMMARY")
    print("=" * 60)
    print(f"  Total problems:     {summary['total']:4d}")
    print(f"  Backfilled:         {summary['backfilled']:4d}")
    print(f"  Errors:             {summary['errors']:4d}")
    print(f"  Skipped:            {summary['skipped']:4d}")
    print("=" * 60)


if __name__ == "__main__":
    main()
