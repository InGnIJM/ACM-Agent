"""
Rebuild fullContent for ALL Luogu problems from rawDetail.

Issue: buildFullContent during initial import failed to include the [样例]
section despite rawDetail having samples data.

This script rebuilds fullContent for every Luogu problem using the rawDetail
data and updates the database.  Runs in background with batch commits.
"""
import psycopg2
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"


def clean_mathjax(text):
    """Same triplication cleanup as backend buildFullContent."""
    if not text:
        return text
    return re.sub(
        r"\n\n([a-zA-Z0-9]{1,3})\n\n\1\n\n\1(\n|$)",
        r"\n\1\2",
        text,
    ).replace("\n\n\n", "\n\n")


def build_fullcontent(record):
    """Replicate NestJS buildFullContent for Luogu."""
    parts = []

    if record.get("background"):
        parts.append(f"[背景]\n{clean_mathjax(record['background'])}")
    if record.get("description"):
        parts.append(f"[描述]\n{clean_mathjax(record['description'])}")
    if record.get("input_format"):
        parts.append(f"[输入]\n{clean_mathjax(record['input_format'])}")
    if record.get("output_format"):
        parts.append(f"[输出]\n{clean_mathjax(record['output_format'])}")

    # Samples — standard OJ order: samples before hints
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
            parts.append(f"[样例]\n" + "\n\n".join(slines))
    elif isinstance(samples, str) and samples.strip():
        parts.append(f"[样例]\n{samples}")

    if record.get("hint"):
        parts.append(f"[提示]\n{clean_mathjax(record['hint'])}")
    if record.get("note"):
        parts.append(f"[注]\n{record['note']}")

    return "\n\n".join(parts) if parts else ""


def fix_one(problem):
    """Rebuild fullContent for one problem and update DB."""
    pid = problem["id"]
    sid = problem["source_id"]
    title = problem["title"]
    rd = problem["raw_detail"]

    record = rd if isinstance(rd, dict) else {}
    new_fc = build_fullcontent(record)

    old_has_samples = "[样例]" in (problem.get("full_content") or "")
    new_has_samples = "[样例]" in new_fc
    old_len = len(problem.get("full_content") or "")
    new_len = len(new_fc)

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "UPDATE problems SET full_content = %s, updated_at = NOW() WHERE id = %s",
        (new_fc, pid),
    )
    cur.close()
    conn.close()

    return {
        "sid": sid,
        "title": title[:40],
        "old_has": old_has_samples,
        "new_has": new_has_samples,
        "old_len": old_len,
        "new_len": new_len,
    }


def main():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source_id, title, raw_detail, full_content
        FROM problems
        WHERE source_platform = 'luogu'
        ORDER BY source_id
        """
    )
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()

    problems = [dict(zip(columns, row)) for row in rows]
    total = len(problems)
    print(f"Found {total} Luogu problems")

    # Count how many already have samples (should be 0 based on earlier query)
    already_ok = sum(1 for p in problems if "[样例]" in (p.get("full_content") or ""))
    print(f"Already have samples: {already_ok}")
    print(f"Need fix: {total - already_ok}")
    print()

    t_start = time.monotonic()
    ok = 0
    added = 0

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fix_one, p): p for p in problems}
        for i, future in enumerate(as_completed(futures)):
            r = future.result()
            ok += 1
            if r["new_has"]:
                added += 1
            if (i + 1) % 500 == 0 or i < 10:
                status = "+" if r["new_has"] and not r["old_has"] else "="
                print(
                    f"  [{i+1:5d}/{total}] {status} {r['sid']:8s}  "
                    f"len: {r['old_len']} -> {r['new_len']}  "
                    f"samples: {r['old_has']} -> {r['new_has']}  "
                    f"{r['title']}"
                )

    elapsed = time.monotonic() - t_start
    print()
    print(f"Done: {ok}/{total} rebuilt in {elapsed:.1f}s")
    print(f"Added samples to: {added} problems")
    print(f"Rate: {total/elapsed:.0f} problems/sec")


if __name__ == "__main__":
    main()
