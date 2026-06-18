"""Rebuild fullContent for all LeetCode problems from rawDetail using fixed HTML-to-text."""
import psycopg2, json, re

DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"


def html_to_text(html_str):
    """Replicate the FIXED buildFullContent HTML-to-text conversion."""
    if not html_str or not html_str.strip().startswith("<"):
        return html_str or ""

    s = html_str
    # Step 1: decode entities
    s = s.replace("&#39;", "'").replace("&#x27;", "'").replace("&apos;", "'")
    s = s.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&amp;", "&").replace("&nbsp;", " ")
    s = s.replace("&#8217;", "'").replace("&#8216;", "'")
    s = s.replace("&#8220;", '"').replace("&#8221;", '"')
    s = s.replace("&#8230;", "...").replace("&#xA0;", " ")

    # Step 2: block-level tags -> paragraph breaks
    block_close = r"</(?:p|div|li|h[1-6]|pre|blockquote|section|article|main|aside|header|footer|nav|figure|figcaption|details|summary|fieldset|form|table|tr|ul|ol|dl)>"
    s = re.sub(block_close, "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<(?:br|hr)\b[^>]*/?>", "\n", s, flags=re.IGNORECASE)
    block_open = r"</?\s*(?:p|div|h[1-6]|pre|blockquote|li|tr|ul|ol|dl|table|section|article|main|aside|header|footer|nav)\b[^>]*>"
    s = re.sub(block_open, "\n", s, flags=re.IGNORECASE)

    # Step 3: remove remaining tags (inline elements like <code>, <strong>, <em>, <span>, <a>)
    s = re.sub(r"<[^>]+>", "", s)

    # Step 4: whitespace cleanup
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def build_fullcontent(record):
    """Replicate the FIXED NestJS buildFullContent logic."""
    parts = []

    # Description: for LeetCode, content is HTML
    desc = record.get("description", "") or record.get("content", "")
    if desc and desc.strip().startswith("<"):
        desc = html_to_text(desc)

    if desc:
        parts.append("[描述]\n" + desc)

    if record.get("input_format"):
        parts.append("[输入]\n" + record["input_format"])
    if record.get("output_format"):
        parts.append("[输出]\n" + record["output_format"])
    if record.get("hint"):
        parts.append("[提示]\n" + record["hint"])

    # Samples from sampleTestCase/exampleTestcases
    sample_test = record.get("sampleTestCase", "")
    example_test = record.get("exampleTestcases", "")
    if sample_test or example_test:
        slines = []
        if sample_test:
            slines.append("输入\n```\n" + sample_test + "\n```")
        if example_test:
            slines.append("输出\n```\n" + example_test + "\n```")
        if slines:
            parts.append("[样例]\n" + "\n".join(slines))

    if record.get("note"):
        parts.append("[注]\n" + record["note"])

    return "\n\n".join(parts) if parts else ""


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(
        "SELECT id, source_id, title, raw_detail FROM problems WHERE source_platform = %s",
        ("leetcode",),
    )
    problems = cur.fetchall()
    print(f"Found {len(problems)} LeetCode problems")

    ok = 0
    for pid, sid, title, rd in problems:
        record = rd if isinstance(rd, dict) else {}
        new_fc = build_fullcontent(record)
        blanks = (
            (len(new_fc) - len(new_fc.replace("\n\n", ""))) // 2 if new_fc else 0
        )

        cur.execute(
            "UPDATE problems SET full_content = %s, updated_at = NOW() WHERE id = %s",
            (new_fc, pid),
        )
        print(f"  OK {sid:6s} blanks={blanks:2d}  {title[:50]}")
        ok += 1

    cur.close()
    conn.close()
    print(f"\nDone: {ok} LeetCode problems fixed")


if __name__ == "__main__":
    main()
