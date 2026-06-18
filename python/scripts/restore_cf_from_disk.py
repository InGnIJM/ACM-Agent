"""
Restore Codeforces problem data from disk JSON files.

Reads all CF JSON files from python/data/raw/codeforces/problems/,
updates raw_detail and rebuilds full_content in the database.
Handles both "good" files (with samples) and "partial" files (no samples).
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.rebuild_all_samples import build_fullcontent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

try:
    import psycopg2
except ImportError:
    logger.error("psycopg2 not available")
    sys.exit(1)

DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"
CF_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "codeforces" / "problems"


def load_records():
    """Read all CF JSON files and return list of (source_id, record_dict)."""
    records = []
    if not CF_DIR.exists():
        logger.error("CF data dir not found: %s", CF_DIR)
        return records

    for fpath in sorted(CF_DIR.glob("*.json")):
        if fpath.name.startswith("bulk_"):
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skip %s: %s", fpath.name, exc)
            continue

        items = data if isinstance(data, list) else [data]
        for r in items:
            sid = r.get("source_id") or f"{r.get('contestId', '')}{r.get('index', '')}"
            if sid:
                records.append((sid, r))

    return records


def main():
    records = load_records()
    logger.info("Loaded %d CF records from disk", len(records))
    if not records:
        return

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    # Get existing CF problems from DB
    cur.execute("SELECT source_id, id FROM problems WHERE source_platform = 'codeforces'")
    db_map = {r[0]: r[1] for r in cur.fetchall()}
    logger.info("Found %d CF problems in database", len(db_map))

    updated = 0
    not_in_db = 0
    has_samples = 0

    for sid, record in records:
        if sid not in db_map:
            logger.debug("  %s: not in DB, skipping", sid)
            not_in_db += 1
            continue

        pid = db_map[sid]
        fc = build_fullcontent(record, platform="codeforces")
        sample_count = len(record.get("samples", []) or [])

        cur.execute(
            "UPDATE problems SET raw_detail = %s, full_content = %s, "
            "updated_at = NOW() WHERE id = %s",
            (json.dumps(record, ensure_ascii=False),
             fc if fc else None,
             pid),
        )
        updated += 1
        if sample_count > 0:
            has_samples += 1

        if updated % 20 == 0:
            logger.info("  ... %d/%d updated", updated, len(records))

    cur.close()
    conn.close()

    logger.info(
        "Done: %d updated (%d with samples), %d not in DB",
        updated, has_samples, not_in_db,
    )


if __name__ == "__main__":
    main()
