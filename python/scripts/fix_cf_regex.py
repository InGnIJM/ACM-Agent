"""Fix CF content: regex-based MathJax triplication dedup.
Pattern: X\n\nX\n\nX_latex -> X_latex (keep only LaTeX version)"""
import json, re
import psycopg2

def dedup(text):
    """Remove MathJax plain-text duplicates, keeping LaTeX variants."""
    if not text:
        return text

    # Pattern: single math letter/number repeated with blank lines, then LaTeX variant
    # "p\n\ni\n\np\n\ni\n\np_i" -> "p_i"
    # "n\n\nn\n\nn" -> "n"
    # "10\n\n5\n\n10\n\n5\n\n10^5" -> "10^5"

    # Strategy: merge every 3 lines where lines 1-2 are plain text, line 3 is LaTeX
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        # Look ahead: find pattern of short lines + blank lines
        # Collect a "triplet group": consecutive blocks separated by blank lines
        group = []
        current_block = []

        while i < len(lines):
            s = lines[i].strip()
            if s == "":
                if current_block:
                    group.append(current_block)
                    current_block = []
                i += 1
                continue

            # Line with content
            current_block.append(s)
            i += 1

            # If we've collected 3 blocks, check if they look like triplication
            if len(group) >= 2 and len(current_block) > 0:
                # Check if blocks 1,2,3 are triplication
                b1 = "".join(b for block in [group[-2]] for b in block)
                b2 = "".join(b for block in [group[-1]] for b in block)
                b3 = "".join(current_block)

                # Triplication: b1 and b2 are near-identical plain text, b3 is LaTeX
                if b1.replace(" ", "") == b2.replace(" ", "") and len(b3) >= len(b1):
                    # Confirm b3 has LaTeX markers or is longer
                    if any(c in b3 for c in "_{}^|\\") or len(b3) > len(b1) * 1.5:
                        # Replace: drop group[-2] and group[-1], keep group[-3..-3] + b3
                        # Pop last 2 groups, add b3 as a new block
                        group.pop()  # remove b2
                        group.pop()  # remove b1
                        current_block = [b3]
                        continue

            if len(current_block) > 50:  # safety limit
                break

        if current_block:
            group.append(current_block)

        # Flatten groups back to output
        for block in group:
            for line in block:
                out.append(line)
            out.append("")  # blank line between blocks

        # Skip trailing blank line
        if out and out[-1] == "":
            out.pop()

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# Simpler approach: just use regex to collapse known triplication patterns
def dedup_simple(text):
    """Regex-based: X\n\nX\n\nX_latex -> X_latex for math tokens."""
    if not text:
        return text

    # Pattern 1: "letter\n\nletter\n\nletter_latex" -> "letter_latex"
    # e.g., "p\n\ni\n\np\n\ni\n\np_i" -> "p_i"
    text = re.sub(
        r'([a-zA-Z])\n\n([a-zA-Z])\n\n([a-zA-Z][_{][a-zA-Z0-9}]+)',
        r'\3', text
    )

    # Pattern 2: "digit\n\ndigit\n\ndigit_latex" -> "digit_latex"
    # e.g., "10\n\n5\n\n10\n\n5\n\n10^5" -> "10^5"
    text = re.sub(
        r'(\d+)\n\n(\d+)\n\n(\d+[\^_{][^\n]+)',
        r'\3', text
    )

    # Pattern 3: single repeated letter on consecutive lines -> keep one
    # e.g., "n\n\nn\n\nn" -> "n"
    text = re.sub(r'([a-zA-Z0-9])\n\n\1\n\n\1', r'\1', text)

    return text


conn = psycopg2.connect("postgresql://postgres:jm050711@localhost:5432/acm_agent")
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT id, raw_detail FROM problems WHERE source_platform='codeforces'")
fixed = 0
for pid, raw in cur.fetchall():
    if not raw:
        continue
    detail = raw if isinstance(raw, dict) else json.loads(str(raw))

    description = dedup_simple((detail.get("description") or "").strip())
    input_spec = dedup_simple((detail.get("input_format") or detail.get("inputSpec") or "").strip())
    output_spec = dedup_simple((detail.get("output_format") or detail.get("outputSpec") or "").strip())
    note = dedup_simple((detail.get("note") or "").strip())

    # Strip CF metadata header
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

    new_content = "\n\n".join(parts)
    new_content = re.sub(r"\n{3,}", "\n\n", new_content).strip()
    cur.execute("UPDATE problems SET full_content=%s WHERE id=%s", (new_content, pid))
    fixed += 1

print(f"CF rebuilt: {fixed}")

# Verify
cur.execute("SELECT full_content FROM problems WHERE source_platform='codeforces' AND source_id='2230E'")
c = cur.fetchone()[0]
print(f"CF 2230E: {len(c)} chars, {len(c.splitlines())} lines")
for i, line in enumerate(c.split("\n")[:20]):
    print(f"  [{i}]: {line[:120]}")

# Show math symbol count reduction
count_single_repeats = len(re.findall(r'([a-zA-Z])\n\n\1', c))
print(f"\nRemaining single-char repeats: {count_single_repeats}")

conn.close()
print("Done")
