"""
Fix problems polluted by CloudFront block pages.

Re-crawls problems whose title is "ERROR: The request could not be
satisfied" and saves clean data to data/raw/atcoder/problems/ so the
backend importer can pick them up.

Usage:
    python fix_polluted_problems.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawlers.atcoder import AtCoderCrawler

# Problems that were stored with CloudFront block-page data.
# stpc2025_1_a is excluded — it genuinely has no English statement.
POLLUTED_IDS = [
    "soundhound2018_summer_qual_c",
    "soundhound2018_summer_qual_d",
    "soundhound2018_summer_qual_e",
    "stage0_2021_a",
]

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "atcoder" / "problems"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    crawler = AtCoderCrawler()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    ok = 0
    fail = 0
    for sid in POLLUTED_IDS:
        print(f"Crawling {sid} ...", end=" ", flush=True)
        result = crawler.fetch_problem(sid)
        if not result.success:
            print(f"FAIL: {result.error}")
            fail += 1
            continue
        data = result.data
        if not isinstance(data, dict):
            print(f"FAIL: unexpected data type {type(data)}")
            fail += 1
            continue
        # Verify we got real content (not another block page)
        desc = str(data.get("description", ""))
        samples = data.get("samples", [])
        if len(desc) < 10 or not isinstance(samples, list) or len(samples) == 0:
            print(f"FAIL: content still empty after re-crawl (desc={len(desc)}, samples={len(samples)})")
            fail += 1
            continue

        out_path = OUT_DIR / f"{date_str}_{sid}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK → {out_path.name} (title={data.get('title','?')[:40]})")
        ok += 1

    print(f"\nDone: {ok} OK, {fail} failed")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
