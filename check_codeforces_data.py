import psycopg2
from psycopg2.extras import RealDictCursor

# 数据库连接信息
DB_URL = "postgresql://postgres:jm050711@localhost:5432/acm_agent"

def check_codeforces_data():
    try:
        # 连接数据库
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        print("=== 检查Codeforces平台数据 ===\n")

        # 1. 查询总问题数
        cur.execute("""
            SELECT COUNT(*) as total_problems
            FROM problems
            WHERE source_platform = 'codeforces' AND deleted_at IS NULL
        """)
        total = cur.fetchone()['total_problems']
        print(f"1. Codeforces平台总问题数: {total}")

        # 2. 查询有题解但没有题解总结的问题
        cur.execute("""
            SELECT p.id, p.source_id, p.title,
                   EXISTS(SELECT 1 FROM problem_solutions ps WHERE ps.problem_id = p.id AND ps.deleted_at IS NULL) as has_solutions,
                   p.solution_summary IS NOT NULL as has_solution_summary
            FROM problems p
            WHERE p.source_platform = 'codeforces'
            AND p.deleted_at IS NULL
            AND EXISTS(SELECT 1 FROM problem_solutions ps WHERE ps.problem_id = p.id AND ps.deleted_at IS NULL)
            AND p.solution_summary IS NULL
            LIMIT 20
        """)
        has_solutions_no_summary = cur.fetchall()

        print(f"\n2. 有题解但没有题解总结的问题 (前20条):")
        if has_solutions_no_summary:
            for row in has_solutions_no_summary:
                print(f"   - {row['source_id']}: {row['title']}")
        else:
            print("   无")

        # 3. 查询有题解总结但没有题解的问题
        cur.execute("""
            SELECT p.id, p.source_id, p.title,
                   EXISTS(SELECT 1 FROM problem_solutions ps WHERE ps.problem_id = p.id AND ps.deleted_at IS NULL) as has_solutions,
                   p.solution_summary IS NOT NULL as has_solution_summary
            FROM problems p
            WHERE p.source_platform = 'codeforces'
            AND p.deleted_at IS NULL
            AND p.solution_summary IS NOT NULL
            AND NOT EXISTS(SELECT 1 FROM problem_solutions ps WHERE ps.problem_id = p.id AND ps.deleted_at IS NULL)
            LIMIT 20
        """)
        has_summary_no_solutions = cur.fetchall()

        print(f"\n3. 有题解总结但没有题解的问题 (前20条):")
        if has_summary_no_solutions:
            for row in has_summary_no_solutions:
                print(f"   - {row['source_id']}: {row['title']}")
        else:
            print("   无")

        # 4. 统计各类情况的数量
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN solution_summary IS NOT NULL THEN 1 END) as has_summary,
                COUNT(CASE WHEN EXISTS(SELECT 1 FROM problem_solutions ps WHERE ps.problem_id = problems.id AND ps.deleted_at IS NULL) THEN 1 END) as has_solutions,
                COUNT(CASE WHEN solution_summary IS NOT NULL AND EXISTS(SELECT 1 FROM problem_solutions ps WHERE ps.problem_id = problems.id AND ps.deleted_at IS NULL) THEN 1 END) as has_both,
                COUNT(CASE WHEN solution_summary IS NULL AND NOT EXISTS(SELECT 1 FROM problem_solutions ps WHERE ps.problem_id = problems.id AND ps.deleted_at IS NULL) THEN 1 END) as has_neither
            FROM problems
            WHERE source_platform = 'codeforces' AND deleted_at IS NULL
        """)
        stats = cur.fetchone()

        print(f"\n4. 统计汇总:")
        print(f"   - 总问题数: {stats['total']}")
        print(f"   - 有题解总结: {stats['has_summary']}")
        print(f"   - 有题解: {stats['has_solutions']}")
        print(f"   - 同时有题解和题解总结: {stats['has_both']}")
        print(f"   - 都没有: {stats['has_neither']}")

        # 5. 检查题解表的数据
        cur.execute("""
            SELECT
                p.source_id,
                COUNT(ps.id) as solution_count,
                COUNT(CASE WHEN ps.summary IS NOT NULL THEN 1 END) as solutions_with_summary
            FROM problems p
            LEFT JOIN problem_solutions ps ON p.id = ps.problem_id AND ps.deleted_at IS NULL
            WHERE p.source_platform = 'codeforces' AND p.deleted_at IS NULL
            GROUP BY p.id, p.source_id
            HAVING COUNT(ps.id) > 0
            ORDER BY solution_count DESC
            LIMIT 10
        """)
        solution_stats = cur.fetchall()

        print(f"\n5. 题解数量最多的题目 (前10):")
        for row in solution_stats:
            print(f"   - {row['source_id']}: {row['solution_count']}个题解, {row['solutions_with_summary']}个有摘要")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    check_codeforces_data()