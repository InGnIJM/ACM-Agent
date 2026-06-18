"""Fix CF content: dedup MathJax triplication in rawDetail fields, then rebuild."""
import json, re
import psycopg2

def dedup_mathjax(text):
    """Collapse MathJax triplication: repeated identical short tokens -> keep only LaTeX variant."""
    if not text:
        return text

    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        # Collect a run of consecutive short ASCII-only non-empty lines
        run = []
        while i < len(lines):
            t = lines[i].strip()
            if not t:
                break
            # Short, ASCII, not a section header
            if len(t) <= 60 and all(ord(c) < 128 for c in t) and not t.startswith("[") and not t.startswith("##"):
                run.append(t)
                i += 1
                if len(run) > 30:
                    break
            else:
                break

        if len(run) >= 3:
            # Within this run, look for triplication patterns
            # Group by similarity: identical or near-identical tokens
            groups = []
            for token in run:
                found = False
                for g in groups:
                    # Match if one token contains the other (e.g. "p" is in "p_i")
                    if token in g[0] or g[0] in token:
                        g.append(token)
                        found = True
                        break
                if not found:
                    groups.append([token])

            # For each group, keep only the most LaTeX-like variant (longest, with _, ^, {, })
            deduped = []
            for g in groups:
                best = max(g, key=lambda x: (
                    any(c in x for c in "_{}^|\\"),
                    len(x),
                    x.count("_") + x.count("^") + x.count("{"),
                ))
                deduped.append(best)

            out.extend(deduped)
        elif run:
            out.extend(run)

        # Add the non-run line that stopped us
        if i < len(lines):
            out.append(lines[i])
            i += 1

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


conn = psycopg2.connect("postgresql://postgres:jm050711@localhost:5432/acm_agent")
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT id, raw_detail FROM problems WHERE source_platform='codeforces'")
fixed = 0
for pid, raw in cur.fetchall():
    if not raw:
        continue
    detail = raw if isinstance(raw, dict) else json.loads(str(raw))

    # Extract and dedup each section
    description = dedup_mathjax((detail.get("description") or "").strip())
    input_spec = dedup_mathjax((detail.get("input_format") or detail.get("inputSpec") or "").strip())
    output_spec = dedup_mathjax((detail.get("output_format") or detail.get("outputSpec") or "").strip())
    note = dedup_mathjax((detail.get("note") or "").strip())

    # Strip CF metadata header from description (time limit, memory, input/output labels)
    # Pattern: "X seconds\n\nmemory limit per test\nX megabytes\n\ninput\nstandard input\n\noutput\nstandard output\n\n"
    description = re.sub(
        r'^\d+\s*seconds?\s*\n+\s*memory limit per test\s*\n+\d+\s*megabytes\s*\n+\s*input\s*\n+\s*standard input\s*\n+\s*output\s*\n+\s*standard output\s*\n+',
        '', description, flags=re.IGNORECASE
    ).strip()

    parts = []
    if description:
        parts.append(f"[描述]\n{description}")
    if input_spec:
        parts.append(f"[输入]\n{input_spec}")
    if output_spec:
        parts.append(f"[输出]\n{output_spec}")
    if note:
        parts.append(f"[注]\n{note}")

    new_content = "\n\n".join(parts).strip()
    cur.execute("UPDATE problems SET full_content=%s WHERE id=%s", (new_content, pid))
    fixed += 1

print(f"CF rebuilt: {fixed}")

# Verify
cur.execute("SELECT full_content FROM problems WHERE source_platform='codeforces' AND source_id='2230E'")
c = cur.fetchone()[0]
print(f"CF 2230E: {len(c)} chars, {len(c.splitlines())} lines")
# Show first 25 lines
for i, line in enumerate(c.split("\n")[:25]):
    print(f"  [{i}]: {line[:120]}")

conn.close()
print("Done")
