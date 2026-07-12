"""Backfill solutions for LeetCode problems that have no solutions in the DB."""

import json
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

# Ensure parent dir is in path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawlers.leetcode import LeetCodeCrawler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def main():
    # Read problem sourceIds without solutions
    ids_file = Path("/tmp/leetcode_no_solutions.json")
    if not ids_file.exists():
        logger.error("Run the DB query first to generate %s", ids_file)
        sys.exit(1)

    source_ids = json.loads(ids_file.read_text(encoding="utf-8"))
    logger.info("Backfilling solutions for %d problems", len(source_ids))

    crawler = LeetCodeCrawler()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Resolve relative to python/ directory (where this script lives)
    base_dir = Path(__file__).resolve().parent.parent
    solutions_dir = base_dir / "data" / "raw" / "leetcode" / "solutions"
    solutions_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Saving solutions to %s", solutions_dir)

    success = 0
    failed = 0
    empty = 0

    for i, slug in enumerate(source_ids):
        out_file = solutions_dir / f"{today}_{slug}.json"
        if out_file.exists():
            logger.info("[%d/%d] %s already exists, skip", i+1, len(source_ids), slug)
            success += 1
            continue

        try:
            result = crawler.fetch_solutions(slug, first=10)
            if result.success and result.data:
                out_file.write_text(
                    json.dumps(result.data, ensure_ascii=False, default=str),
                    encoding="utf-8",
                )
                sol_count = len(result.data) if isinstance(result.data, list) else 0
                logger.info("[%d/%d] %s -> %d solutions", i+1, len(source_ids), slug, sol_count)
                if sol_count > 0:
                    success += 1
                else:
                    empty += 1
            else:
                logger.warning("[%d/%d] %s FAILED: %s", i+1, len(source_ids), slug, result.error)
                failed += 1
        except Exception as e:
            logger.error("[%d/%d] %s ERROR: %s", i+1, len(source_ids), slug, e)
            failed += 1

        # Rate limit: 1 QPS
        time.sleep(1.0)

    logger.info("Done: success=%d, empty=%d, failed=%d, total=%d", success, empty, failed, len(source_ids))
    crawler.close()

if __name__ == "__main__":
    main()
