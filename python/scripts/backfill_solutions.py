"""Backfill solutions for LeetCode and Codeforces.

LeetCode needs titleSlug from rawDetail (not numeric sourceId).
Codeforces sourceId is already the correct format (e.g. "2236B").
NowCoder skipped — requires login to view solutions.
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
from crawlers.leetcode import LeetCodeCrawler
from crawlers.codeforces import CodeforcesCrawler

DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"
MAX_PER_PROBLEM = 5  # max solutions to store per problem


def upsert_solutions(platform, problem_id, solutions, source_id_hint):
    """Replicate NestJS upsertSolutions logic with proper UUID generation."""
    if not solutions:
        return 0
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    count = 0
    for i, sol in enumerate(solutions):
        author = sol.get("author", "匿名")
        content = sol.get("content", "")
        min_len = 50 if platform == "codeforces" else 20
        if not content or len(content.strip()) < min_len:
            continue
        solution_index = sol.get("solution_index") or i + 1
        try:
            cur.execute(
                """INSERT INTO problem_solutions (id, problem_id, solution_index, content, author, updated_at)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, NOW())
                   ON CONFLICT (problem_id, solution_index) DO UPDATE
                   SET content = EXCLUDED.content, author = EXCLUDED.author, updated_at = NOW()""",
                (problem_id, solution_index, content[:10000], author),
            )
            count += 1
            if count >= MAX_PER_PROBLEM:
                break
        except Exception as e:
            print(f"    DB error (skipping): {str(e)[:100]}")
    cur.close()
    conn.close()
    return count


def backfill_leetcode():
    """Backfill LeetCode solutions using titleSlug from rawDetail."""
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source_id, raw_detail FROM problems WHERE source_platform = 'leetcode'"
    )
    problems = []
    for pid, sid, rd in cur.fetchall():
        record = rd if isinstance(rd, dict) else {}
        slug = record.get("titleSlug", "")
        if slug:
            problems.append({"id": pid, "source_id": sid, "slug": slug})
    cur.close()
    conn.close()

    print(f"LeetCode: {len(problems)} problems to backfill")
    crawler = LeetCodeCrawler()
    ok = fail = total_sols = 0

    for p in problems:
        try:
            result = crawler.fetch_solutions(p["slug"], first=5)
            if result.success and result.data:
                count = upsert_solutions("leetcode", p["id"], result.data, p["source_id"])
                total_sols += count
                ok += 1
                if count > 0:
                    print(f"  OK {p['source_id']:6s} slug={p['slug']:30s} -> {count} solutions")
            else:
                fail += 1
                print(f"  SKIP {p['source_id']:6s} slug={p['slug']:30s} (no solutions found)")
        except Exception as e:
            fail += 1
            print(f"  FAIL {p['source_id']:6s} {e}")
        time.sleep(1)

    crawler.close()
    print(f"LeetCode done: {ok} ok, {fail} failed, {total_sols} solutions imported\n")


def backfill_codeforces():
    """Backfill Codeforces solutions using sourceId directly."""
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source_id FROM problems WHERE source_platform = 'codeforces'"
    )
    problems = [{"id": pid, "source_id": sid} for pid, sid in cur.fetchall()]
    cur.close()
    conn.close()

    print(f"Codeforces: {len(problems)} problems to backfill")
    crawler = CodeforcesCrawler()
    ok = fail = total_sols = 0

    for p in problems:
        try:
            result = crawler.fetch_solutions(p["source_id"], max_editorials=5)
            if result.success and result.data:
                count = upsert_solutions("codeforces", p["id"], result.data, p["source_id"])
                total_sols += count
                ok += 1
                if count > 0:
                    print(f"  OK {p['source_id']:10s} -> {count} solutions")
                else:
                    print(f"  SKIP {p['source_id']:10s} (content too short)")
            else:
                fail += 1
                print(f"  SKIP {p['source_id']:10s} (no editorials found)")
        except Exception as e:
            fail += 1
            print(f"  FAIL {p['source_id']:10s} {e}")
        time.sleep(1.5)

    crawler.close()
    print(f"Codeforces done: {ok} ok, {fail} failed, {total_sols} solutions imported\n")


def main():
    t0 = time.monotonic()
    backfill_leetcode()
    backfill_codeforces()
    elapsed = time.monotonic() - t0

    # Summary
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    for plat in ["leetcode", "codeforces", "nowcoder"]:
        cur.execute(
            """SELECT COUNT(*) FROM problem_solutions s
               JOIN problems p ON s.problem_id = p.id
               WHERE p.source_platform = %s""",
            (plat,),
        )
        count = cur.fetchone()[0]
        print(f"  {plat:12s}: {count} solutions in DB")
    cur.close()
    conn.close()
    print(f"\nTotal time: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
