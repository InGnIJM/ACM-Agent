"""Re-embed 30 problems across 3 platforms using Ollama qwen3-embedding:0.6b (1024-dim).
Writes parent vectors (solution_summary), content vectors (full_content), and
child solution vectors (content[:2000]) directly to PostgreSQL."""

import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2

OLLAMA_URL = "http://localhost:11434/api/embed"
MODEL = "qwen3-embedding:0.6b"
DB_URL = "postgresql://postgres:jm050711@localhost:5432/acm_agent"


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Call Ollama /api/embed, return list of 1024-dim vectors."""
    if not texts:
        return []
    payload = json.dumps({"model": MODEL, "input": texts}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["embeddings"]


def process_batch(problem_ids: list[str], platform: str):
    """For a batch of problem IDs, generate and store all vectors."""
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # 1. Fetch problems
    placeholders = ','.join(['%s'] * len(problem_ids))
    cur.execute(
        f"SELECT id, solution_summary, full_content, title, difficulty_raw, source_id "
        f"FROM problems WHERE id::text IN ({placeholders}) AND source_platform = %s",
        (*problem_ids, platform),
    )
    problems = cur.fetchall()
    if not problems:
        conn.close()
        return {"platform": platform, "problems": 0, "solutions": 0, "errors": ["no problems found"]}

    # 2. Generate summaries for problems lacking them
    texts_to_embed_parent = []
    texts_to_embed_content = []
    prob_map = []  # (id, parent_text, content_text)

    for pid, summary, content, title, diff, sid in problems:
        parent_text = summary or f"{title}. Difficulty: {diff}. Platform: {platform}."
        content_text = content or title
        texts_to_embed_parent.append(parent_text[:3000])
        texts_to_embed_content.append(content_text[:3000])
        prob_map.append((pid, parent_text, content_text))

    print(f"  [{platform}] Embedding {len(prob_map)} problems...", flush=True)

    # 3. Batch embed (split into chunks if needed)
    all_parent_vecs = []
    all_content_vecs = []
    chunk = 20
    for i in range(0, len(texts_to_embed_parent), chunk):
        all_parent_vecs.extend(embed_batch(texts_to_embed_parent[i:i + chunk]))
        all_content_vecs.extend(embed_batch(texts_to_embed_content[i:i + chunk]))

    # 4. Write problem vectors
    for (pid, _, _), pvec, cvec in zip(prob_map, all_parent_vecs, all_content_vecs):
        cur.execute(
            "UPDATE problems SET vector_embedding = %s::vector, content_vector = %s::vector, updated_at = NOW() WHERE id = %s",
            (f"[{','.join(map(str, pvec))}]", f"[{','.join(map(str, cvec))}]", pid),
        )

    # 5. Embed solutions
    placeholders = ','.join(['%s'] * len(problem_ids))
    cur.execute(
        f"SELECT id, content FROM problem_solutions WHERE problem_id::text IN ({placeholders})",
        (*problem_ids,),
    )
    solutions = cur.fetchall()
    sol_embeds = 0
    if solutions:
        sol_ids = [s[0] for s in solutions]
        sol_contents = [(s[1] or "")[:2000] for s in solutions]
        sol_vecs = embed_batch(sol_contents)
        for sid, svec in zip(sol_ids, sol_vecs):
            cur.execute(
                "UPDATE problem_solutions SET vector_embedding = %s::vector, updated_at = NOW() WHERE id = %s",
                (f"[{','.join(map(str, svec))}]", sid),
            )
        sol_embeds = len(solutions)

    conn.close()
    return {"platform": platform, "problems": len(prob_map), "solutions": sol_embeds, "errors": []}


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Get 10 problems per platform
    platforms = ["luogu", "leetcode", "codeforces"]
    batches = {}
    for plat in platforms:
        cur.execute(
            "SELECT id FROM problems WHERE source_platform = %s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 10",
            (plat,),
        )
        ids = [r[0] for r in cur.fetchall()]
        if ids:
            batches[plat] = ids
        print(f"[{plat}] {len(ids)} problems to embed")

    conn.close()

    # Parallel process
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(process_batch, ids, plat): plat for plat, ids in batches.items()}
        for f in as_completed(futures):
            result = f.result()
            status = "OK" if not result["errors"] else f"ERROR: {result['errors']}"
            print(f"[{result['platform']}] {result['problems']} problems, {result['solutions']} solutions — {status}")

    # Verify
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "SELECT source_platform, count(*) as total, count(vector_embedding) as with_vec "
        "FROM problems WHERE vector_embedding IS NOT NULL GROUP BY source_platform"
    )
    print("\n=== VERIFICATION ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}/{row[2]} problems have vectors")
    cur.execute("SELECT count(*) FROM problem_solutions WHERE vector_embedding IS NOT NULL")
    print(f"  solutions with vectors: {cur.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
