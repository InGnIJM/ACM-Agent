"""
Batch fix all Codeforces problem fullContent fields — optimized version.

Fetches the problemset API once (metadata cache), then scrapes each
problem page in parallel to rebuild clean fullContent.
"""
import sys
import os
import time
import html as html_mod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
from crawlers.codeforces import CodeforcesCrawler

# ── Config ──────────────────────────────────────────
DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"
WORKERS = 5  # parallel page scrapers
MIN_DELAY = 0.25  # seconds between pages from same worker


def build_fullcontent(record: dict) -> str:
    """Replicate NestJS buildFullContent logic."""
    parts = []
    if record.get("description"):
        parts.append(f"[描述]\n{record['description']}")
    if record.get("input_format"):
        parts.append(f"[输入]\n{record['input_format']}")
    if record.get("output_format"):
        parts.append(f"[输出]\n{record['output_format']}")
    samples = record.get("samples")
    if samples and isinstance(samples, list) and len(samples) > 0:
        slines = []
        for i, s in enumerate(samples):
            if isinstance(s, list) and len(s) >= 2:
                slines.append(
                    f"输入 #{i + 1}\n```\n{s[0] or ''}\n```\n\n"
                    f"输出 #{i + 1}\n```\n{s[1] or ''}\n```"
                )
        if slines:
            parts.append(f"[样例]\n{chr(10).join(slines)}")
    if record.get("note"):
        parts.append(f"[注]\n{record['note']}")
    return "\n\n".join(parts) if parts else ""


def count_blank_pairs(text: str) -> int:
    if not text:
        return 0
    return (len(text) - len(text.replace("\n\n", ""))) // 2


def scrape_and_fix(problem: dict) -> dict:
    """
    Scrape ONE problem page and rebuild fullContent.
    Each worker creates its own crawler & db connection.
    """
    sid = problem["source_id"]
    title = problem["title"]
    pid = problem["id"]
    old_blanks = problem.get("blank_line_pairs", 0)
    contest_id = problem["contest_id"]
    index = problem["index"]

    result = {"source_id": sid, "title": title, "ok": False,
              "old_blanks": old_blanks, "new_blanks": 0, "error": None}

    crawler = None
    try:
        crawler = CodeforcesCrawler()
        url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        page_result = crawler.fetch_with_fallback(url)

        if not page_result.success:
            result["error"] = f"page fetch failed: {page_result.error}"
            return result

        html_text = CodeforcesCrawler._extract_html_text(page_result)
        if not html_text:
            result["error"] = "empty page HTML"
            return result

        # Decode HTML entities (same as in fetch_problem)
        html_text = html_mod.unescape(html_text)

        # Extract sections using the (now fixed) static methods
        desc = CodeforcesCrawler._cf_extract(html_text, "problem-statement", skip_header=True)
        inp = CodeforcesCrawler._cf_extract(html_text, "input-specification")
        out = CodeforcesCrawler._cf_extract(html_text, "output-specification")
        note = CodeforcesCrawler._cf_extract(html_text, "note")
        samples = CodeforcesCrawler._cf_extract_samples(html_text)

        record = {
            "description": desc,
            "input_format": inp,
            "output_format": out,
            "note": note,
            "samples": samples,
        }

        full_content = build_fullcontent(record)
        new_blanks = count_blank_pairs(full_content)

        # Update DB
        conn = psycopg2.connect(DSN)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "UPDATE problems SET full_content = %s, updated_at = NOW() WHERE id = %s",
            (full_content, pid),
        )
        cur.close()
        conn.close()

        result["ok"] = True
        result["new_blanks"] = new_blanks
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        if crawler:
            try:
                crawler.close()
            except Exception:
                pass

    time.sleep(MIN_DELAY)
    return result


def main():
    # ── Step 1: load all CF problems from DB ──────────
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, source_id, title,
               COALESCE(
                   (LENGTH(full_content) - LENGTH(REPLACE(full_content, E'\n\n', ''))) / 2,
                   0
               ) as blank_line_pairs
        FROM problems
        WHERE source_platform = 'codeforces'
        ORDER BY source_id
    """)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()

    problems = [dict(zip(columns, row)) for row in rows]
    print(f"Found {len(problems)} CF problems in DB")

    # ── Step 2: enrich with contestId/index ───────────
    # Parse sourceId like "2236B" → contestId=2236, index="B"
    for p in problems:
        sid = p["source_id"]
        match = __import__("re").match(r"^(\d+)([A-Z]\d*)$", sid)
        if match:
            p["contest_id"] = int(match.group(1))
            p["index"] = match.group(2)
        else:
            p["contest_id"] = 0
            p["index"] = ""

    valid = [p for p in problems if p["contest_id"] > 0]
    invalid = [p for p in problems if p["contest_id"] == 0]
    if invalid:
        print(f"⚠ {len(invalid)} problems with unparseable sourceId: "
              f"{[p['source_id'] for p in invalid]}")
    print(f"Proceeding with {len(valid)} fixable problems")

    # ── Step 3: parallel scrape & fix ─────────────────
    ok_count = 0
    fail_count = 0
    total_old = 0
    total_new = 0

    print(f"\nScraping with {WORKERS} workers...\n")
    t_start = time.monotonic()

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(scrape_and_fix, p): p for p in valid}
        for future in as_completed(futures):
            p = futures[future]
            try:
                r = future.result()
                if r["ok"]:
                    ok_count += 1
                    total_old += r["old_blanks"]
                    total_new += r["new_blanks"]
                    delta = r["old_blanks"] - r["new_blanks"]
                    print(f"  ✓ {r['source_id']:12s}  blanks: {r['old_blanks']:3d} → {r['new_blanks']:3d}  "
                          f"({delta:+d})  {r['title']}")
                else:
                    fail_count += 1
                    print(f"  ✗ {r['source_id']:12s}  ERROR: {r['error']}  {r['title']}")
            except Exception as e:
                fail_count += 1
                print(f"  ✗ {p['source_id']:12s}  EXCEPTION: {e}  {p['title']}")

    elapsed = time.monotonic() - t_start

    # ── Step 4: summary ───────────────────────────────
    print()
    print("=" * 60)
    print(f"SUMMARY: {ok_count} ok, {fail_count} failed (out of {len(valid)})")
    print(f"Time: {elapsed:.1f}s")
    if ok_count > 0:
        removed = total_old - total_new
        pct = removed * 100 // max(1, total_old)
        print(f"Blank-line pairs: {total_old} → {total_new}  (removed {removed}, {pct}%)")
    if fail_count > 0:
        print(f"\nFailed problems — may need manual fix:")
        # re-check which ones failed
        conn = psycopg2.connect(DSN)
        cur = conn.cursor()
        cur.execute("""
            SELECT source_id, title,
                   (LENGTH(full_content) - LENGTH(REPLACE(full_content, E'\n\n', ''))) / 2 as blanks
            FROM problems
            WHERE source_platform = 'codeforces'
              AND (LENGTH(full_content) - LENGTH(REPLACE(full_content, E'\n\n', ''))) / 2 > 20
            ORDER BY blanks DESC
        """)
        remaining = cur.fetchall()
        cur.close()
        conn.close()
        if remaining:
            print(f"  {len(remaining)} still have >20 blank-line pairs:")
            for sid, title, blanks in remaining[:10]:
                print(f"    {sid:12s}  blanks={blanks:3d}  {title}")
            if len(remaining) > 10:
                print(f"    ... and {len(remaining) - 10} more")


if __name__ == "__main__":
    main()
