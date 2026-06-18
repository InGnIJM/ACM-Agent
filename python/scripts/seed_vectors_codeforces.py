"""
Self-contained script: embed 10 most recent Codeforces problems + mock solutions.

Steps:
1. Fetch 10 problems from codeforces (latest created_at)
2. Generate embeddings via Ollama (qwen3-embedding:0.6b)
   - parent vector: embed solution_summary (or generated Chinese summary)
   - content vector: embed full_content (or title + tags)
3. UPDATE problems SET vector_embedding, content_vector
4. INSERT 1–2 mock solutions per problem + embed those
"""

import asyncio
import json
import sys
import textwrap
import uuid
from typing import Optional

import aiohttp
import psycopg2

# ── Config ────────────────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/embed"
MODEL = "qwen3-embedding:0.6b"
MODEL_DIM = 1024          # qwen3-embedding:0.6b outputs 1024-dim
TARGET_DIM = 1536          # DB vector columns are 1536-dim
PG_DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"
PLATFORM = "codeforces"
LIMIT = 10

# ── Pad vectors to target dimension ─────────────────────────────────────────

def pad_vector(vec: list[float], target_dim: int) -> list[float]:
    """Zero-pad a vector to target_dim."""
    if len(vec) == target_dim:
        return vec
    if len(vec) > target_dim:
        print(f"       WARNING: truncating vector from {len(vec)} to {target_dim}")
        return vec[:target_dim]
    return vec + [0.0] * (target_dim - len(vec))


# ── Helpers: generate Chinese text when source fields are empty ────────────

def build_content_text(title: str, tags: list[str]) -> str:
    """Build a short Chinese description from title + tags when full_content is empty."""
    tag_str = "、".join(tags[:8]) if tags else "算法与数据结构"
    # English title, Chinese tags context
    text = (
        f"Codeforces编程题：{title}。"
        f"涉及算法标签：{tag_str}。"
        f"该题目来自Codeforces竞赛平台，需要设计高效算法解决对应的计算问题。"
    )
    return text


def build_summary_text(title: str, tags: list[str], rating: Optional[int] = None) -> str:
    """Build a Chinese solution summary when solution_summary is empty."""
    tag_str = "、".join(tags[:5]) if tags else "基础算法"
    rating_hint = f"难度评级约{rating}，" if rating else ""
    text = (
        f"题目{title}的解题思路：{rating_hint}核心考察{tag_str}。"
        f"首先分析问题结构，根据标签选择合适的算法策略。"
        f"对于{tags[0] if tags else '算法'}类型问题，关键在于正确建模并优化时间复杂度。"
    )
    return text


# ── Ollama embedding via aiohttp ───────────────────────────────────────────

async def embed_text(session: aiohttp.ClientSession, text: str) -> list[float]:
    """Return embedding vector for a single text."""
    payload = {"model": MODEL, "input": [text]}
    try:
        async with session.post(OLLAMA_URL, json=payload, timeout=60) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Ollama embed failed (HTTP {resp.status}): {body[:300]}")
            data = await resp.json()
            embeddings = data.get("embeddings", [])
            if not embeddings:
                raise RuntimeError(f"No embeddings in response: {json.dumps(data, ensure_ascii=False)[:300]}")
            return embeddings[0]
    except asyncio.TimeoutError:
        raise RuntimeError(f"Ollama embed timed out for text: {text[:100]}...")


async def embed_batch(
    session: aiohttp.ClientSession,
    texts: list[str],
) -> list[list[float]]:
    """Embed multiple texts; Ollama supports batch input so send all at once when possible."""
    if not texts:
        return []
    # qwen3-embedding supports batch input via "input": [str, str, ...]
    payload = {"model": MODEL, "input": texts}
    try:
        async with session.post(OLLAMA_URL, json=payload, timeout=120) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Ollama batch embed failed (HTTP {resp.status}): {body[:300]}")
            data = await resp.json()
            embeddings = data.get("embeddings", [])
            if len(embeddings) != len(texts):
                raise RuntimeError(
                    f"Embedding count mismatch: got {len(embeddings)} for {len(texts)} inputs"
                )
            return embeddings
    except asyncio.TimeoutError:
        # Fall back to one-at-a-time
        results = []
        for text in texts:
            vec = await embed_text(session, text)
            results.append(vec)
        return results


# ── Database ───────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(PG_DSN)


def fetch_problems():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, source_id, title, full_content, solution_summary,
                   tags_normalized, raw_detail
            FROM problems
            WHERE source_platform = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (PLATFORM, LIMIT),
        )
        rows = cur.fetchall()
        problems = []
        for r in rows:
            raw = r[6]
            rating = None
            if raw:
                d = json.loads(raw) if isinstance(raw, str) else raw
                rating = d.get("rating")
            problems.append({
                "id": r[0],
                "source_id": r[1],
                "title": r[2],
                "full_content": r[3],
                "solution_summary": r[4],
                "tags": r[5] or [],
                "rating": rating,
            })
        return problems
    finally:
        conn.close()


def update_problem_vectors(problem_id: str, parent_vec: list[float], content_vec: list[float]):
    conn = get_db()
    try:
        cur = conn.cursor()
        parent_padded = pad_vector(parent_vec, TARGET_DIM)
        content_padded = pad_vector(content_vec, TARGET_DIM)
        parent_json = json.dumps(parent_padded)
        content_json = json.dumps(content_padded)
        cur.execute(
            """
            UPDATE problems
            SET vector_embedding = %s::vector,
                content_vector = %s::vector
            WHERE id = %s
            """,
            (parent_json, content_json, problem_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_solution(problem_id: str, solution_index: int, content: str, author: str) -> str:
    conn = get_db()
    try:
        cur = conn.cursor()
        sid = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO problem_solutions (id, problem_id, solution_index, content, author, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            RETURNING id
            """,
            (sid, problem_id, solution_index, content, author),
        )
        result = cur.fetchone()[0]
        conn.commit()
        return result
    finally:
        conn.close()


def update_solution_vector(solution_id: str, vec: list[float]):
    conn = get_db()
    try:
        cur = conn.cursor()
        vec_padded = pad_vector(vec, TARGET_DIM)
        vec_json = json.dumps(vec_padded)
        cur.execute(
            "UPDATE problem_solutions SET vector_embedding = %s::vector WHERE id = %s",
            (vec_json, solution_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── Mock solution content generators ───────────────────────────────────────

def mock_solution_cpp(title: str, tags: list[str]) -> str:
    """Generate a C++ mock solution."""
    t0 = tags[0] if tags else "implementation"
    return textwrap.dedent(f"""\
    /**
     * Solution for: {title}
     * Tags: {', '.join(tags[:5]) if tags else 'N/A'}
     * Approach: Use {t0} to compute the answer efficiently.
     */
    #include <bits/stdc++.h>
    using namespace std;

    int main() {{
        ios::sync_with_stdio(false);
        cin.tie(nullptr);

        // TODO: read input
        // TODO: apply {t0} algorithm
        // TODO: output result

        return 0;
    }}
    """).strip()


def mock_solution_python(title: str, tags: list[str]) -> str:
    """Generate a Python mock solution."""
    t0 = tags[0] if tags else "greedy"
    return textwrap.dedent(f"""\
    # Solution for: {title}
    # Tags: {', '.join(tags[:5]) if tags else 'N/A'}
    # Approach: Use {t0} to find the optimal result.

    def solve():
        import sys
        data = sys.stdin.read().split()
        if not data:
            return
        # TODO: parse input
        # TODO: compute result with {t0} strategy
        # TODO: print output
        pass

    if __name__ == '__main__':
        solve()
    """).strip()


# ── Main ───────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("Seed Vectors for Codeforces Problems")
    print("=" * 60)

    # ── Step 1: Fetch problems ─────────────────────────────────────────────
    print("\n[1/4] Fetching problems from PostgreSQL...")
    problems = fetch_problems()
    print(f"       Got {len(problems)} problems")
    if len(problems) == 0:
        print("       No problems found, exiting.")
        return

    # ── Step 2: Prepare texts + generate missing content ────────────────────
    print("\n[2/4] Preparing embedding texts...")
    parent_texts = []   # for vector_embedding
    content_texts = []  # for content_vector
    for p in problems:
        title = p["title"]
        tags = p["tags"]
        rating = p.get("rating")

        # parent vector text (solution_summary)
        if p["solution_summary"] and len(p["solution_summary"].strip()) > 10:
            parent_texts.append(p["solution_summary"])
        else:
            parent_texts.append(build_summary_text(title, tags, rating))

        # content vector text (full_content)
        fc = p.get("full_content")
        if fc and len(fc.strip()) > 200:
            content_texts.append(fc)
        else:
            content_texts.append(build_content_text(title, tags))

    for i, p in enumerate(problems):
        print(f"       [{i+1}] {p['source_id']} {p['title'][:45]}")
        print(f"           parent: {parent_texts[i][:80]}...")
        print(f"           content: {content_texts[i][:80]}...")

    # ── Step 3a: Embed problems ─────────────────────────────────────────────
    print("\n[3/4] Embedding via Ollama (qwen3-embedding:0.6b)...")
    async with aiohttp.ClientSession() as session:
        all_texts = parent_texts + content_texts
        print(f"       Sending {len(all_texts)} texts in one batch...")
        all_vecs = await embed_batch(session, all_texts)
        parent_vecs = all_vecs[: len(problems)]
        content_vecs = all_vecs[len(problems):]

    print(f"       Parent vectors: {len(parent_vecs)}  (dim={len(parent_vecs[0]) if parent_vecs else 'N/A'})")
    print(f"       Content vectors: {len(content_vecs)}  (dim={len(content_vecs[0]) if content_vecs else 'N/A'})")

    # ── Step 3b: UPDATE problems ────────────────────────────────────────────
    print("\n       Updating problems in PostgreSQL...")
    problem_ok = 0
    problem_errors = []
    for i, p in enumerate(problems):
        try:
            update_problem_vectors(p["id"], parent_vecs[i], content_vecs[i])
            problem_ok += 1
        except Exception as e:
            problem_errors.append(f"UPDATE problem {p['source_id']}: {e}")

    print(f"       Problems updated: {problem_ok}/{len(problems)}")
    for err in problem_errors:
        print(f"       ERROR: {err}")

    # ── Step 4: Mock solutions ──────────────────────────────────────────────
    print("\n[4/4] Creating mock solutions + embedding...")
    solution_texts = []
    solution_meta = []  # (problem_id, solution_index, content, author)

    for i, p in enumerate(problems):
        tags = p["tags"]

        # Solution 1: C++
        cpp = mock_solution_cpp(p["title"], tags)
        solution_texts.append(cpp)
        solution_meta.append((p["id"], 0, cpp, "mock-bot"))

        # Solution 2: Python (skip for every other to vary 1–2 per problem)
        if i % 3 != 0:
            py = mock_solution_python(p["title"], tags)
            solution_texts.append(py)
            solution_meta.append((p["id"], 1, py, "mock-bot"))

    print(f"       Total mock solutions to create: {len(solution_meta)}")

    # Embed all solution texts in one batch
    async with aiohttp.ClientSession() as session:
        print(f"       Embedding {len(solution_texts)} solution texts...")
        sol_vecs = await embed_batch(session, solution_texts)

    # Insert + update
    sol_ok = 0
    sol_errors = []
    for idx, (meta, vec) in enumerate(zip(solution_meta, sol_vecs)):
        pid, six, content, author = meta
        try:
            sid = insert_solution(pid, six, content, author)
            update_solution_vector(sid, vec)
            sol_ok += 1
        except Exception as e:
            sol_errors.append(f"Solution {idx} for problem {pid[:8]}: {e}")

    print(f"       Solutions created + embedded: {sol_ok}/{len(solution_meta)}")
    for err in sol_errors:
        print(f"       ERROR: {err}")

    # ── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Problems embedded:      {problem_ok}/{len(problems)}")
    print(f"  Solutions embedded:     {sol_ok}/{len(solution_meta)}")
    all_errors = problem_errors + sol_errors
    if all_errors:
        print(f"  Errors:                 {len(all_errors)}")
        for e in all_errors:
            print(f"    - {e}")
    else:
        print("  Errors:                 0")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
