"""
Retry failed CF problems — sequential, one at a time to avoid connection conflicts.
"""
import sys
import os
import time
import html as html_mod

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
from crawlers.codeforces import CodeforcesCrawler

DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"


def build_fullcontent(record: dict) -> str:
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


def main():
    # Load failed (high-blank) problems from DB
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, source_id, title,
               (LENGTH(full_content) - LENGTH(REPLACE(full_content, E'\n\n', ''))) / 2 as blanks
        FROM problems
        WHERE source_platform = 'codeforces'
          AND (LENGTH(full_content) - LENGTH(REPLACE(full_content, E'\n\n', ''))) / 2 > 15
        ORDER BY blanks DESC
    """)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()

    problems = [dict(zip(columns, row)) for row in rows]
    print(f"Still needs fix: {len(problems)} problems")

    # Parse contestId/index
    import re
    for p in problems:
        m = re.match(r"^(\d+)([A-Z]\d*)$", p["source_id"])
        if m:
            p["contest_id"] = int(m.group(1))
            p["index"] = m.group(2)
        else:
            p["contest_id"] = 0
            p["index"] = ""

    ok = 0
    fail = 0
    crawler = None

    for p in problems:
        sid = p["source_id"]
        title = p["title"]
        pid = p["id"]
        cid = p.get("contest_id", 0)
        idx = p.get("index", "")
        old_blanks = p["blanks"]

        if cid == 0:
            print(f"  ✗ {sid:12s}  SKIP: unparseable sourceId")
            fail += 1
            continue

        try:
            if crawler is None:
                crawler = CodeforcesCrawler()
            url = f"https://codeforces.com/problemset/problem/{cid}/{idx}"

            # Retry up to 3 times
            for attempt in range(3):
                page = crawler.fetch_with_fallback(url)
                if page.success:
                    break
                print(f"    retry {attempt+1}/3 for {sid}...")
                time.sleep(2)

            if not page.success:
                print(f"  ✗ {sid:12s}  FAIL: page fetch error  ({old_blanks:3d})  {title}")
                fail += 1
                # Close and recreate crawler on failure
                try:
                    crawler.close()
                except Exception:
                    pass
                crawler = None
                continue

            html_text = CodeforcesCrawler._extract_html_text(page)
            if not html_text:
                print(f"  ✗ {sid:12s}  FAIL: empty HTML  ({old_blanks:3d})  {title}")
                fail += 1
                continue

            html_text = html_mod.unescape(html_text)
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

            conn = psycopg2.connect(DSN)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(
                "UPDATE problems SET full_content = %s, updated_at = NOW() WHERE id = %s",
                (full_content, pid),
            )
            cur.close()
            conn.close()

            delta = old_blanks - new_blanks
            print(f"  ✓ {sid:12s}  blanks: {old_blanks:3d} → {new_blanks:3d}  ({delta:+d})  {title}")
            ok += 1

        except Exception as e:
            print(f"  ✗ {sid:12s}  ERROR: {type(e).__name__}: {e}  ({old_blanks:3d})  {title}")
            fail += 1
            try:
                crawler.close()
            except Exception:
                pass
            crawler = None

        time.sleep(1)  # 1 second between problems

    if crawler:
        try:
            crawler.close()
        except Exception:
            pass

    print(f"\nRetry done: {ok} ok, {fail} failed (out of {len(problems)})")


if __name__ == "__main__":
    main()
