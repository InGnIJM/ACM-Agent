"""Rebuild Codeforces full_content from rawDetail JSON."""
import json, re
import psycopg2

conn = psycopg2.connect("postgresql://postgres:jm050711@localhost:5432/acm_agent")
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT id, raw_detail FROM problems WHERE source_platform='codeforces'")
fixed = 0
for pid, raw in cur.fetchall():
    if not raw:
        continue
    detail = raw if isinstance(raw, dict) else json.loads(str(raw))

    # Skip if no structured data available
    if not detail.get("description") and not detail.get("title"):
        continue

    parts = []
    description = (detail.get("description") or "").strip()
    input_spec = (detail.get("input_format") or detail.get("inputSpec") or "").strip()
    output_spec = (detail.get("output_format") or detail.get("outputSpec") or "").strip()
    note = (detail.get("note") or "").strip()
    samples = detail.get("samples") or detail.get("sampleTests") or []

    # Simple text cleanup: normalize whitespace, remove excessive newlines
    def clean_text(t):
        # Collapse 3+ newlines
        t = re.sub(r"\n{3,}", "\n\n", t)
        # Remove lines that are single repeated chars (MathJax artifacts)
        lines = t.split("\n")
        cleaned = []
        prev_short = False
        for line in lines:
            s = line.strip()
            if len(s) <= 2 and s and all(c == s[0] for c in s if c != ' '):
                # Single repeated-char line like "n", "S" — skip
                continue
            if 1 <= len(s) <= 3 and not prev_short:
                prev_short = True
            elif len(s) > 3:
                prev_short = False
            cleaned.append(line)
        t = "\n".join(cleaned)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    if description:
        parts.append(f"[描述]\n{clean_text(description)}")
    if input_spec:
        parts.append(f"[输入]\n{clean_text(input_spec)}")
    if output_spec:
        parts.append(f"[输出]\n{clean_text(output_spec)}")

    # Samples
    if isinstance(samples, list) and len(samples) > 0:
        sample_lines = ["[样例]"]
        for i, s in enumerate(samples):
            if isinstance(s, dict):
                si = s.get("input", "")
                so = s.get("output", "")
                sample_lines.append(f"示例 {i+1}:")
                if si:
                    sample_lines.append(f"```\n{si}\n```")
                if so:
                    sample_lines.append(f"```\n{so}\n```")
        parts.append("\n".join(sample_lines))
    elif isinstance(samples, str) and samples.strip():
        parts.append(f"[样例]\n{samples.strip()}")

    if note:
        parts.append(f"[注]\n{clean_text(note)}")

    new_content = "\n\n".join(parts).strip()
    cur.execute("UPDATE problems SET full_content=%s WHERE id=%s", (new_content, pid))
    fixed += 1

print(f"CF rebuilt: {fixed}")

# Verify
cur.execute("SELECT full_content FROM problems WHERE source_platform='codeforces' AND source_id='2230E'")
c = cur.fetchone()[0]
print(f"CF 2230E: {len(c.splitlines())} lines")
# Show first 400 chars
for line in c.split("\n")[:15]:
    print(f"  {line[:100]}")
print(f"  ... (total {len(c)} chars)")

conn.close()
