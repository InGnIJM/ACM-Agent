"""
Self-contained script: embed Luogu problems + solutions and write vectors to PostgreSQL.

Usage:
    cd E:/code/ACM-Agent/python
    python scripts/seed_vectors_luogu.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import textwrap
from typing import Optional

import uuid as _uuid

import aiohttp
import psycopg2
import psycopg2.extras

# ── config ──────────────────────────────────────────────────────────────
OLLAMA_URL: str = "http://localhost:11434/api/embed"
OLLAMA_MODEL: str = "qwen3-embedding:0.6b"
OLLAMA_DIMS: int = 1024  # qwen3-embedding:0.6b outputs 1024-dim vectors
PGVECTOR_DIMS: int = 1536  # pgvector column expects 1536-dim
DB_DSN: str = "postgresql://postgres:jm050711@localhost:5432/acm_agent"
PLATFORM: str = "luogu"
LIMIT: int = 10
SOLUTIONS_PER_PROBLEM: int = 2  # 1-2 per problem

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_vectors")

# ── tag name mapping (Luogu tag ID → Chinese name) ─────────────────────
TAG_NAMES: dict[int, str] = {
    1: "模拟",
    2: "字符串",
    3: "动态规划",
    4: "搜索",
    5: "数学",
    6: "图论",
    7: "贪心",
    8: "计算几何",
    11: "数据结构",
    14: "数论",
    19: "排序",
    21: "位运算",
    22: "分治",
    23: "递归",
    24: "暴力",
    25: "枚举",
    26: "高精度",
    27: "组合数学",
    28: "概率论",
    29: "博弈论",
    31: "线性代数",
    32: "矩阵",
    33: "FFT/NTT",
    36: "拓扑排序",
    37: "最短路",
    38: "最小生成树",
    39: "网络流",
    40: "二分图",
    41: "强连通分量",
    42: "LCA",
    43: "树形结构",
    44: "线段树",
    45: "树状数组",
    46: "动态规划/DP优化",
    47: "倍增",
    48: "RMQ",
    49: "并查集",
    53: "二分",
    54: "离散化",
    59: "USACO",
    107: "构造",
    111: "哈希",
    113: "前缀和",
    144: "区间DP",
    146: "单调队列",
    159: "基环树",
    166: "内向基环树",
    175: "树形DP",
    179: "连通性",
    254: "随机化",
    318: "Ad Hoc",
    320: "DAG",
    365: "双指针",
    477: "博弈论",
}


def tag_id_to_name(tag_id: int | str) -> str:
    tid = int(tag_id)
    return TAG_NAMES.get(tid, f"标签{tid}")


def pad_vector(vec: list[float], target_dim: int) -> list[float]:
    """Pad or truncate a vector to target_dim dimensions."""
    if len(vec) >= target_dim:
        return vec[:target_dim]
    return vec + [0.0] * (target_dim - len(vec))


# ── database helpers ──────────────────────────────────────────────────


def fetch_problems() -> list[dict]:
    """Fetch the 10 most recent Luogu problems with null vectors."""
    conn = psycopg2.connect(DB_DSN)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, title, full_content, solution_summary,
                       difficulty_normalized, tags_normalized, raw_detail
                FROM problems
                WHERE source_platform = %s
                  AND deleted_at IS NULL
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (PLATFORM, LIMIT),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_problem_vectors(problem_id: str, parent_vec: list[float], content_vec: list[float]) -> None:
    """UPDATE problems SET vector_embedding and content_vector."""
    conn = psycopg2.connect(DB_DSN)
    try:
        parent_padded = pad_vector(parent_vec, PGVECTOR_DIMS)
        content_padded = pad_vector(content_vec, PGVECTOR_DIMS)
        parent_json = json.dumps(parent_padded)
        content_json = json.dumps(content_padded)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE problems
                SET vector_embedding = %s::vector,
                    content_vector = %s::vector,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (parent_json, content_json, problem_id),
            )
        conn.commit()
    finally:
        conn.close()


def create_solution(problem_id: str, solution_index: int, content: str, author: str) -> str:
    """INSERT a mock solution and return its id."""
    conn = psycopg2.connect(DB_DSN)
    try:
        new_id = str(_uuid.uuid4())
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO problem_solutions (id, problem_id, solution_index, content, author, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                RETURNING id
                """,
                (new_id, problem_id, solution_index, content, author),
            )
            result_id = cur.fetchone()[0]
        conn.commit()
        return str(result_id)
    finally:
        conn.close()


def update_solution_vector(solution_id: str, vec: list[float]) -> None:
    """UPDATE problem_solutions SET vector_embedding."""
    conn = psycopg2.connect(DB_DSN)
    try:
        padded = pad_vector(vec, PGVECTOR_DIMS)
        vec_json = json.dumps(padded)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE problem_solutions
                SET vector_embedding = %s::vector,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (vec_json, solution_id),
            )
        conn.commit()
    finally:
        conn.close()


def count_existing_solutions(problem_id: str) -> int:
    """Count existing solutions for a problem."""
    conn = psycopg2.connect(DB_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(solution_index) FROM problem_solutions WHERE problem_id = %s AND deleted_at IS NULL",
                (problem_id,),
            )
            row = cur.fetchone()
            return (row[0] or 0)
    finally:
        conn.close()


# ── embedding client ──────────────────────────────────────────────────


async def embed_text(session: aiohttp.ClientSession, text: str) -> Optional[list[float]]:
    """Call Ollama /api/embed and return the first embedding vector."""
    if not text or not text.strip():
        return None
    try:
        payload = {"model": OLLAMA_MODEL, "input": text}
        async with session.post(OLLAMA_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error("Ollama returned %d: %s", resp.status, body[:200])
                return None
            data = await resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
            logger.error("No embeddings in response: %s", json.dumps(data, ensure_ascii=False)[:200])
            return None
    except asyncio.TimeoutError:
        logger.error("Ollama timeout for text of length %d", len(text))
        return None
    except Exception as exc:
        logger.error("Ollama error: %s", exc)
        return None


# ── text preparation ──────────────────────────────────────────────────


def prepare_parent_text(prob: dict) -> str:
    """Prepare text for the parent (solution_summary) vector.

    If solution_summary is non-empty, use it directly.
    Otherwise, generate a basic Chinese summary from title + tags + content excerpt.
    """
    summary = (prob.get("solution_summary") or "").strip()
    if summary:
        return summary

    title = (prob.get("title") or "").strip()
    difficulty = prob.get("difficulty_normalized")
    tags = prob.get("tags_normalized") or []

    # Build a synthetic summary
    parts = [f"题目：{title}"]

    # Add difficulty
    if difficulty is not None:
        if difficulty <= 1500:
            diff_label = "入门"
        elif difficulty <= 2400:
            diff_label = "普及"
        elif difficulty <= 3000:
            diff_label = "提高"
        elif difficulty <= 4000:
            diff_label = "省选"
        else:
            diff_label = "NOI"
        parts.append(f"难度：{diff_label}（{int(difficulty)}）")

    # Add Chinese tag names
    if tags:
        tag_names = [tag_id_to_name(t) for t in tags]
        parts.append(f"算法标签：{', '.join(tag_names)}")

    # Add content excerpt
    content = (prob.get("full_content") or "").strip()
    if content:
        # Take first ~600 chars for summary context
        excerpt = content[:600]
        parts.append(f"题目描述摘要：{excerpt}")

    return "\n".join(parts)


def prepare_content_text(prob: dict) -> str:
    """Prepare text for the content vector.

    Uses full_content if non-empty; otherwise falls back to title + description from raw_detail.
    """
    content = (prob.get("full_content") or "").strip()
    if content:
        return content

    title = (prob.get("title") or "").strip()
    raw = prob.get("raw_detail") or {}
    description = (raw.get("description") or "").strip()

    parts = [f"题目：{title}"]
    if description:
        parts.append(f"题目描述：{description}")

    return "\n".join(parts)


def generate_mock_solution_content(prob: dict, index: int) -> str:
    """Generate a mock solution in Chinese for a problem."""
    title = (prob.get("title") or "").strip()
    tags = prob.get("tags_normalized") or []
    tag_names = [tag_id_to_name(t) for t in tags]
    difficulty = prob.get("difficulty_normalized")

    diff_label = "中等"
    if difficulty is not None:
        if difficulty <= 1500:
            diff_label = "入门"
        elif difficulty <= 2400:
            diff_label = "普及"
        elif difficulty <= 3000:
            diff_label = "提高"
        elif difficulty <= 4000:
            diff_label = "省选"
        else:
            diff_label = "NOI"

    if index == 1:
        return textwrap.dedent(f"""\
            ## 解题思路

            本题「{title}」属于{diff_label}难度，主要考察{', '.join(tag_names[:3]) if tag_names else '综合算法'}。

            ### 算法分析
            根据题目描述，我们需要仔细分析问题的约束条件。题目给出了明确的数据范围限制，我们可以据此选择合适的算法。

            ### 时间复杂度
            考虑到数据范围，我们设计的算法需要在规定的时间限制内运行完成。

            ### 关键步骤
            1. 仔细阅读理解题目要求，明确输入输出格式
            2. 分析样例数据，验证思路的正确性
            3. 根据数据范围选择合适的数据结构和算法
            4. 实现代码并进行充分的测试

            ### 注意事项
            - 注意边界条件的处理
            - 注意数据类型的范围，可能需要使用64位整数
            - 注意特殊情况的处理，如空输入或极值

            ### 参考代码思路
            本题的核心解法需要结合{', '.join(tag_names[:2]) if len(tag_names) >= 2 else tag_names[0] if tag_names else '基础算法'}来完成。
            建议先写出暴力解法验证思路，再逐步优化到最终解法。""")
    else:
        return textwrap.dedent(f"""\
            ## 题解：「{title}」详解

            ### 题目分析
            这道题是典型的{', '.join(tag_names[:2]) if len(tag_names) >= 2 else (tag_names[0] if tag_names else '算法')}类型题目，难度为{diff_label}级别。

            ### 核心思想
            解决本题的关键在于理解题目的本质。我们需要将实际问题转化为数学模型，然后利用已知的算法框架来求解。

            ### 具体解法
            1. **预处理阶段**：对输入数据进行必要的预处理，建立辅助数据结构
            2. **核心计算**：执行主要算法逻辑，这是解题的关键部分
            3. **输出结果**：按照题目要求的格式输出答案

            ### 代码结构建议
            ```
            - 读取输入数据
            - 初始化数据结构
            - 执行核心算法逻辑
            - 格式化输出结果
            ```

            ### 复杂度分析
            - 时间复杂度：需要根据具体算法确定
            - 空间复杂度：需要考虑辅助数据结构的开销

            ### 易错点提醒
            - 注意数据溢出问题
            - 注意循环边界条件
            - 注意空集和极值情况的处理""")

    # Alternative shorter version
    return textwrap.dedent(f"""\
        ## 简要题解

        「{title}」考查{', '.join(tag_names[:3]) if tag_names else '综合能力'}。

        核心思路：分析题目的约束条件，选择合适的数据结构和算法。注意数据范围和边界情况。

        推荐先写出朴素解法，验证通过后再优化时间复杂度。""")

# ── main ────────────────────────────────────────────────────────────────


async def main_async() -> dict:
    """Main async entry point. Returns a report dict."""
    report = {
        "problems_embedded": 0,
        "solutions_created": 0,
        "solutions_embedded": 0,
        "errors": [],
    }

    # 1. Fetch problems
    logger.info("Fetching %d most recent Luogu problems...", LIMIT)
    problems = fetch_problems()
    logger.info("Found %d problems", len(problems))

    if not problems:
        report["errors"].append("No Luogu problems found in database")
        return report

    # 2. Prepare all texts
    parent_texts: list[tuple[str, str]] = []  # (problem_id, text)
    content_texts: list[tuple[str, str]] = []  # (problem_id, text)
    all_texts: list[tuple[str, str, str]] = []  # (problem_id, kind, text) — for batch embedding

    for prob in problems:
        pid = str(prob["id"])

        p_text = prepare_parent_text(prob)
        if p_text:
            parent_texts.append((pid, p_text))
            all_texts.append((pid, "parent", p_text))

        c_text = prepare_content_text(prob)
        if c_text:
            content_texts.append((pid, c_text))
            all_texts.append((pid, "content", c_text))

    logger.info(
        "Prepared %d parent texts and %d content texts (%d total embeddings to request)",
        len(parent_texts), len(content_texts), len(all_texts),
    )

    # 3. Batch embed all texts concurrently
    embeddings: dict[str, dict[str, list[float]]] = {}  # problem_id -> {parent: vec, content: vec}

    async with aiohttp.ClientSession() as session:
        # Process in chunks to avoid overwhelming Ollama
        chunk_size = 5
        for i in range(0, len(all_texts), chunk_size):
            chunk = all_texts[i : i + chunk_size]
            tasks = []
            for pid, kind, text in chunk:
                tasks.append(embed_text(session, text))

            logger.info("Embedding chunk %d/%d (%d texts)...",
                        i // chunk_size + 1,
                        (len(all_texts) + chunk_size - 1) // chunk_size,
                        len(chunk))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(results):
                pid, kind, _ = chunk[j]
                if isinstance(result, Exception):
                    report["errors"].append(f"Embed failed for {pid}/{kind}: {result}")
                    continue
                if result is None:
                    report["errors"].append(f"Embed returned None for {pid}/{kind}")
                    continue
                if pid not in embeddings:
                    embeddings[pid] = {}
                embeddings[pid][kind] = result

    # 4. Write problem vectors to DB
    for prob in problems:
        pid = str(prob["id"])
        emb = embeddings.get(pid, {})
        parent_vec = emb.get("parent")
        content_vec = emb.get("content")

        if parent_vec is None and content_vec is None:
            report["errors"].append(f"No embeddings generated for problem {pid}")
            continue

        # Default empty vector if one is missing
        if parent_vec is None:
            parent_vec = content_vec or []
        if content_vec is None:
            content_vec = parent_vec or []

        try:
            update_problem_vectors(pid, parent_vec, content_vec)
            report["problems_embedded"] += 1
            logger.info("Updated vectors for problem %s: %s", pid, prob.get("title", ""))
        except Exception as exc:
            report["errors"].append(f"Failed to update vectors for {pid}: {exc}")
            logger.error("DB update failed for %s: %s", pid, exc)

    # 5. Create & embed mock solutions
    async with aiohttp.ClientSession() as session:
        for prob in problems:
            pid = str(prob["id"])

            # Determine starting solution_index
            existing_max = count_existing_solutions(pid)
            start_idx = existing_max + 1

            for si in range(SOLUTIONS_PER_PROBLEM):
                sol_idx = start_idx + si
                sol_content = generate_mock_solution_content(prob, si + 1)

                # Create solution record
                try:
                    sol_id = create_solution(pid, sol_idx, sol_content, "AI生成")
                    report["solutions_created"] += 1
                except Exception as exc:
                    report["errors"].append(f"Failed to create solution for {pid}: {exc}")
                    continue

                # Embed solution content
                sol_vec = await embed_text(session, sol_content)
                if sol_vec is None:
                    report["errors"].append(f"Failed to embed solution {sol_id}")
                    continue

                try:
                    update_solution_vector(sol_id, sol_vec)
                    report["solutions_embedded"] += 1
                    logger.info("Created solution %s for problem %s (idx=%d)", sol_id, pid, sol_idx)
                except Exception as exc:
                    report["errors"].append(f"Failed to update solution vector {sol_id}: {exc}")

    return report


def main() -> None:
    """Entry point."""
    logger.info("=" * 60)
    logger.info("Seed Vectors for Luogu Problems")
    logger.info("Ollama model: %s", OLLAMA_MODEL)
    logger.info("Database: %s", DB_DSN)
    logger.info("=" * 60)

    report = asyncio.run(main_async())

    print()
    print("=" * 60)
    print("REPORT")
    print("=" * 60)
    print(f"  Problems embedded:  {report['problems_embedded']}")
    print(f"  Solutions created:  {report['solutions_created']}")
    print(f"  Solutions embedded: {report['solutions_embedded']}")
    print(f"  Errors:             {len(report['errors'])}")
    if report["errors"]:
        print("  Error details:")
        for err in report["errors"]:
            print(f"    - {err}")
    print("=" * 60)

    # Exit with non-zero if nothing was done
    if report["problems_embedded"] == 0 and report["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
