"""
Rebuild all fullContent with separate input/output code blocks.

Each sample pair gets two independent code blocks:
  输入 #1
  ```
  {input}
  ```
  输出 #1
  ```
  {output}
  ```
Frontend renders 输入 #N / 输出 #N as ### h3 with InputOutlinedIcon / OutputOutlinedIcon.
"""
import psycopg2, json, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed

DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"


def clean_mathjax(text):
    if not text:
        return text
    return re.sub(
        r"\n\n([a-zA-Z0-9]{1,3})\n\n\1\n\n\1(\n|$)", r"\n\1\2", text
    ).replace("\n\n\n", "\n\n")


def html_to_text(html_str):
    if not html_str or not html_str.strip().startswith("<"):
        return html_str or ""
    s = html_str
    for e, r in [
        ("&#39;", "'"), ("&#x27;", "'"), ("&apos;", "'"), ("&quot;", '"'),
        ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&nbsp;", " "),
        ("&#8217;", "'"), ("&#8216;", "'"), ("&#8220;", '"'), ("&#8221;", '"'),
        ("&#8230;", "..."), ("&#xA0;", " "),
    ]:
        s = s.replace(e, r)
    s = re.sub(r"</?(?:p|div|li|h[1-6]|pre|blockquote)\b[^>]*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<(?:br|hr)\b[^>]*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def build_fullcontent(record, platform="luogu"):
    """Build fullContent with unified sample format."""
    parts = []

    if record.get("background"):
        parts.append(f"[背景]\n{clean_mathjax(record['background'])}")

    desc = record.get("description", "") or record.get("content", "")
    if desc and desc.strip().startswith("<"):
        desc = html_to_text(desc)
    if desc:
        parts.append(f"[描述]\n{clean_mathjax(desc)}")

    if record.get("input_format"):
        parts.append(f"[输入]\n{clean_mathjax(record['input_format'])}")
    if record.get("output_format"):
        parts.append(f"[输出]\n{clean_mathjax(record['output_format'])}")

    # Samples — separate input/output code blocks (standard OJ order: before hints)
    samples = record.get("samples")
    if samples and isinstance(samples, list) and len(samples) > 0:
        slines = []
        for i, s in enumerate(samples):
            if isinstance(s, list) and len(s) >= 2:
                inp = (s[0] or "").rstrip()
                out = (s[1] or "").rstrip()
                slines.append(
                    f"输入 #{i + 1}\n```\n{inp}\n```\n\n"
                    f"输出 #{i + 1}\n```\n{out}\n```"
                )
        if slines:
            parts.append(f"[样例]\n" + "\n\n".join(slines))
    elif isinstance(samples, str) and samples.strip():
        parts.append(f"[样例]\n{samples}")

    # LeetCode-style samples: separate input/output blocks
    if platform == "leetcode" and not record.get("samples"):
        st = record.get("sampleTestCase", "")
        et = record.get("exampleTestcases", "")
        if st or et:
            lines = []
            if st:
                lines.append(f"输入 #1\n```\n{st}\n```")
            if et:
                lines.append(f"输出 #1\n```\n{et}\n```")
            parts.append(f"[样例]\n" + "\n\n".join(lines))

    if record.get("hint"):
        parts.append(f"[提示]\n{clean_mathjax(record['hint'])}")
    if record.get("note"):
        parts.append(f"[注]\n{record['note']}")

    return "\n\n".join(parts) if parts else ""


def fix_one(problem):
    pid = problem["id"]
    rd = problem["raw_detail"]
    platform = problem["source_platform"]
    record = rd if isinstance(rd, dict) else {}

    new_fc = build_fullcontent(record, platform)

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "UPDATE problems SET full_content = %s, updated_at = NOW() WHERE id = %s",
        (new_fc if new_fc else None, pid),
    )
    cur.close()
    conn.close()

    return {
        "sid": problem["source_id"],
        "plat": platform,
        "old_len": len(problem.get("full_content") or ""),
        "new_len": len(new_fc),
        "has_samples": "[样例]" in new_fc,
    }


def main():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute(
        """SELECT id, source_id, source_platform, title, raw_detail, full_content
           FROM problems WHERE source_platform != 'atcoder'
           ORDER BY source_platform, source_id"""
    )
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()

    problems = [dict(zip(cols, row)) for row in rows]
    total = len(problems)
    print(f"Total problems to rebuild: {total}")
    print()

    # Count by platform
    plats = {}
    for p in problems:
        plats[p["source_platform"]] = plats.get(p["source_platform"], 0) + 1
    for plat, count in sorted(plats.items()):
        print(f"  {plat:12s}: {count:5d}")
    print()

    t_start = time.monotonic()
    ok = 0
    total_samples = 0

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fix_one, p): p for p in problems}
        for future in as_completed(futures):
            r = future.result()
            ok += 1
            if r["has_samples"]:
                total_samples += 1
            if ok % 1000 == 0:
                elapsed = time.monotonic() - t_start
                rate = ok / elapsed
                eta = (total - ok) / rate
                print(f"  [{ok}/{total}] rate={rate:.0f}/s eta={eta:.0f}s ...")

    elapsed = time.monotonic() - t_start
    print(f"\nDone: {ok}/{total} rebuilt in {elapsed:.0f}s ({ok/elapsed:.0f}/s)")
    print(f"Problems with samples: {total_samples}/{total}")


if __name__ == "__main__":
    main()
