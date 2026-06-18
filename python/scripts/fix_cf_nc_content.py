"""Fix Codeforces MathJax triplication and NowCoder LaTeX wrapping in DB content."""
import sys, re
import psycopg2

conn = psycopg2.connect("postgresql://postgres:jm050711@localhost:5432/acm_agent")
conn.autocommit = True
cur = conn.cursor()

BACKSLASH = chr(92)

# ── Fix Codeforces: collapse MathJax triplication ──
cur.execute("SELECT id, full_content FROM problems WHERE source_platform='codeforces'")
cf_fixed = 0
for pid, content in cur.fetchall():
    lines = content.split("\n")
    cleaned = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        # Collect consecutive short ASCII lines (1-5 chars, no CJK, no brackets)
        run = []
        while i < len(lines):
            s = lines[i].strip()
            is_short = 1 <= len(s) <= 5
            is_ascii = all(ord(c) < 128 for c in s)
            is_not_header = not s.startswith("[")
            if s and is_short and is_ascii and is_not_header:
                run.append(s)
                i += 1
                if len(run) > 12:
                    break
            else:
                break

        if len(run) >= 3:
            # Keep the longest / most LaTeX-like variant (with _, ^, {, })
            best = max(run, key=lambda x: (
                any(c in x for c in "_{}^|"),
                len(x),
            ), default=run[-1])
            cleaned.append(best)
        elif run:
            cleaned.extend(run)

        if i < len(lines):
            s = lines[i].strip()
            if s:
                cleaned.append(s)
            i += 1

    new_content = "\n".join(cleaned)
    new_content = re.sub(r"\n{3,}", "\n\n", new_content).strip()

    if len(new_content) < len(content) * 0.9:
        cur.execute("UPDATE problems SET full_content=%s WHERE id=%s", (new_content, pid))
        cf_fixed += 1

print(f"CF fixed: {cf_fixed}")

# ── Fix NowCoder: wrap standalone backslash lines in $$ ──
cur.execute("SELECT id, full_content FROM problems WHERE source_platform='nowcoder'")
nc_fixed = 0
for pid, content in cur.fetchall():
    lines = content.split("\n")
    changed = False
    new_lines = []
    for line in lines:
        s = line.strip()
        if s and s[0] == BACKSLASH and not s.startswith("$$"):
            new_lines.append("$$" + s + "$$")
            changed = True
        else:
            new_lines.append(line)
    if changed:
        new_content = "\n".join(new_lines)
        cur.execute("UPDATE problems SET full_content=%s WHERE id=%s", (new_content, pid))
        nc_fixed += 1

print(f"NC fixed: {nc_fixed}")

# ── Verify ──
cur.execute("SELECT full_content FROM problems WHERE source_platform='codeforces' AND source_id='2230E'")
c = cur.fetchone()[0]
print(f"CF 2230E: {len(c.splitlines())} lines")

cur.execute("SELECT full_content FROM problems WHERE source_platform='nowcoder' AND source_id='317502'")
c = cur.fetchone()[0]
print(f"NC 317502 $$ count: {c.count('$$')}")
for i, line in enumerate(c.split("\n")):
    if BACKSLASH in line:
        print(f"  [{i}]: {line[:120]}")

conn.close()
print("Done")
