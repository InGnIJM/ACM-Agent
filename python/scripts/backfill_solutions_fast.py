"""Fast parallel solution backfill — LeetCode 5w, CF 2w. Failed sequential retry."""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed
from crawlers.leetcode import LeetCodeCrawler
from crawlers.codeforces import CodeforcesCrawler

DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"


def upsert_solutions(platform, problem_id, solutions):
    if not solutions:
        return 0
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    count = 0
    for i, sol in enumerate(solutions):
        author = sol.get("author", "")
        content = sol.get("content", "")
        min_len = 50 if platform == "codeforces" else 20
        if not content or len(content.strip()) < min_len:
            continue
        try:
            cur.execute(
                """INSERT INTO problem_solutions (id, problem_id, solution_index, content, author, updated_at)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, NOW())
                   ON CONFLICT (problem_id, solution_index) DO UPDATE
                   SET content = EXCLUDED.content, author = EXCLUDED.author, updated_at = NOW()""",
                (problem_id, i + 1, content[:10000], author),
            )
            count += 1
            if count >= 5:
                break
        except Exception:
            pass
    cur.close()
    conn.close()
    return count


def do_leetcode(p):
    """Fetch solutions for one LeetCode problem (GraphQL — no DrissionPage)."""
    try:
        crawler = LeetCodeCrawler()
        result = crawler.fetch_solutions(p["slug"], first=5)
        if result.success and result.data:
            return {"sid": p["source_id"], "ok": True,
                    "count": upsert_solutions("leetcode", p["id"], result.data)}
        return {"sid": p["source_id"], "ok": False, "reason": "no solutions"}
    except Exception as e:
        return {"sid": p["source_id"], "ok": False, "reason": str(e)[:80]}
    finally:
        try: crawler.close()
        except: pass


def do_cf(p):
    """Fetch solutions for one CF problem (page scrape — DrissionPage)."""
    try:
        crawler = CodeforcesCrawler()
        result = crawler.fetch_solutions(p["source_id"], max_editorials=3)
        if result.success and result.data:
            return {"sid": p["source_id"], "ok": True,
                    "count": upsert_solutions("codeforces", p["id"], result.data)}
        return {"sid": p["source_id"], "ok": False, "reason": "no editorials"}
    except Exception as e:
        return {"sid": p["source_id"], "ok": False, "reason": str(e)[:80]}
    finally:
        try: crawler.close()
        except: pass


def parallel_backfill(label, problems, worker_fn, workers, retry_sequential=True):
    """Process problems in parallel, retry failures sequentially."""
    print(f"\n{label}: {len(problems)} problems, {workers} workers")
    ok = fail = total_sols = 0
    failed = []

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker_fn, p): p for p in problems}
        for f in as_completed(futures):
            r = f.result()
            if r["ok"]:
                ok += 1
                total_sols += r.get("count", 0)
                if r.get("count", 0) > 0:
                    print(f"  + {r['sid']:12s} {r['count']} solutions")
            else:
                fail += 1
                failed.append(futures[f])
                print(f"  - {r['sid']:12s} {r.get('reason', '')}")

    elapsed = time.monotonic() - t0
    print(f"  [{elapsed:.0f}s] {ok} ok, {fail} failed, {total_sols} solutions")

    # Sequential retry
    if failed and retry_sequential:
        print(f"  Retrying {len(failed)} failed sequentially...")
        retry_ok = 0
        for p in failed:
            r = worker_fn(p)
            if r["ok"]:
                retry_ok += 1
                total_sols += r.get("count", 0)
                if r.get("count", 0) > 0:
                    print(f"    + {r['sid']:12s} {r['count']} solutions (retry)")
            else:
                print(f"    - {r['sid']:12s} STILL FAILED: {r.get('reason', '')}")
            time.sleep(0.5)
        print(f"  Retry recovered: {retry_ok}/{len(failed)}")
        ok += retry_ok
        fail -= retry_ok

    return ok, fail, total_sols


def main():
    # Load LeetCode problems with slugs
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute("SELECT id, source_id, raw_detail FROM problems WHERE source_platform = 'leetcode'")
    lc_problems = []
    for pid, sid, rd in cur.fetchall():
        record = rd if isinstance(rd, dict) else {}
        slug = record.get("titleSlug", "")
        if slug:
            lc_problems.append({"id": pid, "source_id": sid, "slug": slug})

    cur.execute("SELECT id, source_id FROM problems WHERE source_platform = 'codeforces'")
    cf_problems = [{"id": pid, "source_id": sid} for pid, sid in cur.fetchall()]
    cur.close()
    conn.close()

    t_start = time.monotonic()

    # LeetCode: 5 workers (GraphQL, no DrissionPage issues)
    lc_ok, lc_fail, lc_sols = parallel_backfill(
        "LeetCode", lc_problems, do_leetcode, workers=5
    )

    # CF: 2 workers (DrissionPage, avoid connection conflicts)
    cf_ok, cf_fail, cf_sols = parallel_backfill(
        "Codeforces", cf_problems, do_cf, workers=2
    )

    elapsed = time.monotonic() - t_start

    # Summary
    print(f"\n{'='*50}")
    print(f"Total: {elapsed:.0f}s | LeetCode: {lc_ok}ok {lc_sols}sols | CF: {cf_ok}ok {cf_sols}sols")
    cur = conn.cursor()
    for plat in ["leetcode", "codeforces"]:
        cur.execute("SELECT COUNT(*) FROM problem_solutions s JOIN problems p ON s.problem_id=p.id WHERE p.source_platform=%s", (plat,))
        print(f"  {plat}: {cur.fetchone()[0]} solutions in DB")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
