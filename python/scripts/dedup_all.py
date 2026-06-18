"""Dedup MathJax triplication from NowCoder DB content."""
import re, psycopg2

def dedup(content):
    lines = content.split("\n")
    out = []
    i = 0
    while i < len(lines):
        t = lines[i].strip()
        if not t:
            out.append(lines[i]); i += 1; continue
        cluster = []
        while i < len(lines):
            s = lines[i].strip()
            if not s: break
            if len(s) <= 60 and all(ord(c) < 128 for c in s) and not s.startswith("[") and not s.startswith("##"):
                cluster.append(s); i += 1
            else: break
        if len(cluster) >= 3:
            latex_score = lambda x: sum(1 for c in "_^{}|" + chr(92) if c in x)
            best = max(cluster, key=lambda x: (len(x), latex_score(x)))
            out.append(best)
        elif cluster:
            out.extend(cluster)
        if i < len(lines):
            out.append(lines[i]); i += 1
    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result

conn = psycopg2.connect("postgresql://postgres:jm050711@localhost:5432/acm_agent")
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT id, full_content FROM problems WHERE source_platform='nowcoder'")
fixed = 0
for pid, content in cur.fetchall():
    new_c = dedup(content)
    if new_c != content:
        cur.execute("UPDATE problems SET full_content=%s WHERE id=%s", (new_c, pid))
        fixed += 1
print(f"NC dedup: {fixed}/51")

# Also re-run CF dedup with improved logic
cur.execute("SELECT id, full_content FROM problems WHERE source_platform='codeforces'")
cf_fixed = 0
for pid, content in cur.fetchall():
    new_c = dedup(content)
    # Also strip CF metadata header
    new_c = re.sub(
        r'^\d+\s*seconds?\s*\n+\s*memory limit per test\s*\n+\d+\s*megabytes\s*\n+\s*input\s*\n+\s*standard input\s*\n+\s*output\s*\n+\s*standard output\s*\n+',
        '', new_c, flags=re.IGNORECASE
    ).strip()
    if new_c != content:
        cur.execute("UPDATE problems SET full_content=%s WHERE id=%s", (new_c, pid))
        cf_fixed += 1
print(f"CF re-dedup: {cf_fixed}/50")

# Verify NC
cur.execute("SELECT full_content FROM problems WHERE source_platform='nowcoder' AND source_id='317502'")
c = cur.fetchone()[0]
for i, line in enumerate(c.split("\n")):
    if i < 25 and line.strip():
        print(f"[{i}]: {line[:120]}")
    if any(p in line for p in ["n n n", "S S S", "i i i", "P P P"]):
        print(f"  STILL TRIPLE [{i}]: {line[:100]}")
print(f"Done - lines: {len(c.split(chr(10)))}")

conn.close()
