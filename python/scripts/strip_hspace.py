"""Strip \\hspace / \\vspace lines from DB content (OJ formatting artifacts)."""
import re, psycopg2

conn = psycopg2.connect("postgresql://postgres:jm050711@localhost:5432/acm_agent")
conn.autocommit = True
cur = conn.cursor()

for plat in ("nowcoder", "codeforces"):
    cur.execute(
        "SELECT id, full_content FROM problems WHERE source_platform=%s",
        (plat,),
    )
    fixed = 0
    for pid, content in cur.fetchall():
        new_lines = []
        for line in content.split("\n"):
            s = line.strip()
            # Drop hspace/vspace lines (with or without $$ wrapping)
            if re.match(r'^\$?\$?\\[hv]space\{', s):
                continue
            new_lines.append(line)
        new_c = "\n".join(new_lines)
        new_c = re.sub(r"\n{3,}", "\n\n", new_c).strip()
        if new_c != content:
            cur.execute(
                "UPDATE problems SET full_content=%s WHERE id=%s",
                (new_c, pid),
            )
            fixed += 1
    print(f"{plat}: {fixed} cleaned")

# Verify NC 317502
cur.execute(
    "SELECT full_content FROM problems WHERE source_platform=%s AND source_id=%s",
    ("nowcoder", "317502"),
)
c = cur.fetchone()[0]
for i, line in enumerate(c.split("\n")):
    if i < 20 and line.strip():
        print(f"[{i}]: {line[:120]}")
print(f"Lines: {len(c.splitlines())}")

conn.close()
