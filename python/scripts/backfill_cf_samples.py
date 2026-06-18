"""
Backfill Codeforces problem samples by re-scraping each problem page.

The old CF crawler only returned API metadata (contestId, index, name,
tags) without scraping the HTML statement.  This script re-fetches every
CF problem using the current crawler (which extracts description,
input_format, output_format, note, AND samples from the HTML page),
then updates raw_detail and rebuilds fullContent in the database.

Usage:
    python scripts/backfill_cf_samples.py           # all CF problems
    python scripts/backfill_cf_samples.py --dry-run  # preview only
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawlers.codeforces import CodeforcesCrawler
from scripts.rebuild_all_samples import build_fullcontent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

try:
    import psycopg2
except ImportError:
    logger.error("psycopg2 not available. Install: pip install psycopg2")
    sys.exit(1)

DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"


def get_cf_problems():
    """Return list of {id, source_id, raw_detail} for all CF problems."""
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source_id, raw_detail FROM problems "
        "WHERE source_platform = 'codeforces' ORDER BY source_id"
    )
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def update_problem(problem_id: str, raw_detail: dict, full_content: str):
    """Persist updated raw_detail and fullContent to the database."""
    import json as _json
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "UPDATE problems SET raw_detail = %s, full_content = %s, "
        "updated_at = NOW() WHERE id = %s",
        (_json.dumps(raw_detail, ensure_ascii=False),
         full_content if full_content else None,
         problem_id),
    )
    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill Codeforces problem samples"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write to DB")
    args = parser.parse_args()

    problems = get_cf_problems()
    total = len(problems)
    logger.info("Found %d CF problems in database", total)
    if total == 0:
        logger.info("Nothing to do.")
        return

    crawler = CodeforcesCrawler()
    updated = 0
    skipped = 0
    failed = 0
    t_start = time.monotonic()

    try:
        for i, prob in enumerate(problems):
            sid = prob["source_id"]
            pid = prob["id"]
            logger.info("[%d/%d] %s", i + 1, total, sid)

            # ── Re-scrape problem page with current crawler ──────
            try:
                result = crawler.fetch_problem(sid)
            except Exception as exc:
                logger.error("  fetch_problem crashed: %s", exc)
                failed += 1
                continue

            if not result.success or not result.data:
                logger.warning("  fetch failed: %s", result.error)
                failed += 1
                continue

            data = result.data
            samples = data.get("samples", [])
            sample_count = len(samples) if isinstance(samples, list) else (1 if samples else 0)

            old_rd = prob["raw_detail"]
            old_has_samples = bool(
                isinstance(old_rd, dict) and old_rd.get("samples")
            )

            if old_has_samples and sample_count <= len(old_rd.get("samples", [])):
                logger.info("  already has %d samples, skipping",
                            len(old_rd.get("samples", [])))
                skipped += 1
                continue

            # ── Build new fullContent ────────────────────────────
            new_fc = build_fullcontent(data, platform="codeforces")

            if args.dry_run:
                logger.info("  [DRY RUN] would update: +%d samples, "
                            "fc=%d chars", sample_count, len(new_fc))
            else:
                update_problem(pid, data, new_fc)
                logger.info("  updated: +%d samples, fc=%d chars",
                            sample_count, len(new_fc))

            updated += 1

            # Rate-limit: be gentle to CF servers
            time.sleep(1.5)

    finally:
        crawler.close()

    elapsed = time.monotonic() - t_start
    logger.info(
        "Done: %d updated, %d skipped, %d failed, %d total in %.0fs",
        updated, skipped, failed, total, elapsed,
    )


if __name__ == "__main__":
    main()
