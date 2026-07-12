"""
精准补齐 Codeforces 缺失题解。
只处理 problem_solutions 表中没有记录的题目，按 contest 分组复用 editorial 缓存。
"""
import os
import psycopg2
import psycopg2.extras
import subprocess
import json
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_URL = "postgresql://postgres:jm050711@localhost:5432/acm_agent"
PYTHON = sys.executable  # use current python
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PYTHON_DIR = os.path.join(_SCRIPT_DIR, "python")
CRAWLER = os.path.join(_PYTHON_DIR, "crawlers", "codeforces.py")


def get_missing_problems():
    """查询没有题解的 Codeforces 题目，按 contest_id 排序。"""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT p.source_id, p.title,
               (regexp_match(p.source_id, '^([0-9]+)'))[1]::int as contest_id
        FROM problems p
        WHERE p.source_platform = 'codeforces'
          AND p.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM problem_solutions ps
              WHERE ps.problem_id = p.id AND ps.deleted_at IS NULL
          )
        ORDER BY contest_id, p.source_id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def upsert_solution(problem_source_id: str, solution_data: dict):
    """将题解写入 problem_solutions 表。"""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    try:
        # 找到 problem id
        cur.execute("""
            SELECT id FROM problems
            WHERE source_platform = 'codeforces' AND source_id = %s AND deleted_at IS NULL
        """, (problem_source_id,))
        row = cur.fetchone()
        if not row:
            logger.warning(f"Problem {problem_source_id} not found in DB")
            return False
        problem_id = row[0]

        content = solution_data.get("content", "")
        if not content:
            return False

        author = solution_data.get("author", "Codeforces Editorial")
        solution_index = solution_data.get("solution_index", 0)

        # 清理旧的不同 solutionIndex 的行
        cur.execute("""
            DELETE FROM problem_solutions
            WHERE problem_id = %s::uuid AND solution_index != %s AND deleted_at IS NULL
        """, (problem_id, solution_index))

        # Upsert
        cur.execute("""
            INSERT INTO problem_solutions (id, problem_id, solution_index, content, author, created_at, updated_at)
            VALUES (gen_random_uuid(), %s::uuid, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (problem_id, solution_index)
            DO UPDATE SET content = EXCLUDED.content, author = EXCLUDED.author, updated_at = NOW(), deleted_at = NULL
        """, (problem_id, solution_index, content, author))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error for {problem_source_id}: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def fetch_solution_via_crawler(source_id: str) -> list:
    """调用 Python 爬虫获取题解。"""
    try:
        result = subprocess.run(
            [PYTHON, CRAWLER, "--action", "fetch_solutions", "--uid", source_id],
            capture_output=True, text=True, timeout=120,
            cwd=_PYTHON_DIR
        )
        if result.returncode != 0:
            logger.warning(f"Crawler failed for {source_id}: {result.stderr[:200]}")
            return []

        # 解析 stdout 最后一行 JSON
        for line in reversed(result.stdout.strip().split("\n")):
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                if data.get("success") and isinstance(data.get("data"), list):
                    return data["data"]
        return []
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout for {source_id}")
        return []
    except Exception as e:
        logger.error(f"Error fetching {source_id}: {e}")
        return []


def main():
    problems = get_missing_problems()
    logger.info(f"Found {len(problems)} Codeforces problems without solutions")

    if not problems:
        logger.info("Nothing to do")
        return

    # 按 contest 分组
    from collections import defaultdict
    by_contest = defaultdict(list)
    for p in problems:
        by_contest[p["contest_id"]].append(p)

    logger.info(f"Spread across {len(by_contest)} contests")

    fetched = 0
    errors = 0
    skipped = 0

    for i, (contest_id, contest_problems) in enumerate(by_contest.items()):
        logger.info(f"[{i+1}/{len(by_contest)}] Contest {contest_id}: {len(contest_problems)} problems")

        for p in contest_problems:
            sid = p["source_id"]
            # 从 sourceId 提取 index（如 "2206L" → "L"）
            import re
            m = re.match(r'^\d+(.+)$', sid)
            if not m:
                logger.warning(f"Cannot parse index from {sid}")
                skipped += 1
                continue

            solutions = fetch_solution_via_crawler(sid)
            if solutions:
                ok = upsert_solution(sid, solutions[0])
                if ok:
                    fetched += 1
                    logger.info(f"  ✓ {sid}: solution saved ({len(solutions[0].get('content', ''))} chars)")
                else:
                    errors += 1
            else:
                skipped += 1
                logger.info(f"  - {sid}: no editorial found")

            # Rate limit: 2s between requests (同一 contest 内的 editorial 是缓存的，所以主要瓶颈是首次)
            time.sleep(1)

    logger.info(f"\nDone! fetched={fetched}, skipped={skipped}, errors={errors}")


if __name__ == "__main__":
    main()
