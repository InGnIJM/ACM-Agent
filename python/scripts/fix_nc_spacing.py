"""
Fix bare LaTeX spacing commands (\\, \\! \\; \\:) in NowCoder problem content.

Run: python python/scripts/fix_nc_spacing.py
"""

import psycopg2, re, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BS = chr(92)  # backslash

FIXES = [
    (BS + ',', ''),    # thin space
    (BS + '!', ''),    # negative thin space
    (BS + ';', ''),    # thick space
    (BS + ':', ''),    # medium space
]

def fix_text(s):
    if not s:
        return s
    for pat, repl in FIXES:
        s = s.replace(pat, repl)
    return s

def main():
    conn = psycopg2.connect(host='localhost', user='postgres', password='jm050711', dbname='acm_agent')
    cur = conn.cursor()

    cur.execute(
        "SELECT id, source_id, full_content, raw_detail FROM problems WHERE source_platform = %s AND full_content LIKE %s",
        ('nowcoder', '%' + BS + ',%')
    )
    rows = cur.fetchall()
    print("Found %d problems with bare \\, in full_content" % len(rows))

    fixed = 0
    for pid, sid, fc, rd in rows:
        new_fc = fix_text(fc) if fc else None
        new_rd = None

        if rd and isinstance(rd, dict):
            rd2 = dict(rd)
            rd_changed = False
            for key in ('description', 'input_format', 'output_format'):
                if key in rd2 and rd2[key]:
                    new_val = fix_text(rd2[key])
                    if new_val != rd2[key]:
                        rd2[key] = new_val
                        rd_changed = True
            if rd_changed:
                new_rd = json.dumps(rd2, ensure_ascii=False)

        if new_fc != fc or new_rd:
            if new_rd:
                cur.execute(
                    'UPDATE problems SET full_content = %s, raw_detail = %s WHERE id = %s',
                    (new_fc, new_rd, pid)
                )
            else:
                cur.execute(
                    'UPDATE problems SET full_content = %s WHERE id = %s',
                    (new_fc, pid)
                )
            fixed += 1
            print("  [%s] fixed" % sid)

    conn.commit()
    print("\nFixed %d problems." % fixed)

    # Verify
    cur.execute(
        "SELECT COUNT(*) FROM problems WHERE source_platform = %s AND full_content LIKE %s",
        ('nowcoder', '%' + BS + ',%')
    )
    remain = cur.fetchone()[0]
    print("Remaining with bare \\, in full_content: %d" % remain)

    # Also check for other spacing artifacts
    for cmd in ['!', ';', ':']:
        cur.execute(
            "SELECT COUNT(*) FROM problems WHERE source_platform = %s AND full_content LIKE %s",
            ('nowcoder', '%' + BS + cmd + '%')
        )
        c = cur.fetchone()[0]
        if c:
            print("  Also found %d with bare \\%s" % (c, cmd))

    conn.close()

if __name__ == '__main__':
    main()
