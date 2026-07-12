/**
 * 修复 embedding 失败的题目：有 summary 但无 vector。
 * 直接调本地 embedding 服务重嵌，不走 summarize。
 *
 * 用法：npx ts-node scripts/reembed-missing.ts
 */
import { PrismaClient } from '@prisma/client';

const EMBED_URL = 'http://127.0.0.1:8089/v1/embeddings';
const EMBED_VERSION = 'qwen3-embedding:0.6b@llama-cpp';
const INST_SOLUTION =
  '为算法题解法摘要生成用于相似题检索的向量，重点关注算法类型、题目模式、触发条件、核心思想、状态语义、不变量和高区分度易错点。';

async function embedTexts(texts: string[]): Promise<number[][]> {
  const resp = await fetch(EMBED_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: texts }),
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => '');
    throw new Error(`Embedding server returned ${resp.status}: ${body.slice(0, 500)}`);
  }
  const data: any = await resp.json();
  const items: Array<{ index: number; embedding: number[] }> = data.data || [];
  return items.sort((a, b) => a.index - b.index).map((i) => i.embedding);
}

async function embedOne(text: string): Promise<number[]> {
  const vecs = await embedTexts([`${INST_SOLUTION}\n\n${text}`]);
  return vecs[0];
}

const p = new PrismaClient();

async function main() {
  // 找到有完整摘要但无向量的题目
  const rows: any[] = await p.$queryRaw`
    SELECT id, source_id::text, title, solution_summary
    FROM problems
    WHERE deleted_at IS NULL
      AND solution_summary IS NOT NULL
      AND solution_summary != ''
      AND solution_summary ~ '【核心考点】'
      AND solution_summary ~ '【推荐解法】'
      AND solution_summary ~ '【易错点】'
      AND vector_embedding IS NULL
    ORDER BY created_at ASC
  `;

  console.log(`找到 ${rows.length} 条有摘要但缺向量的题目`);

  if (rows.length === 0) {
    await p.$disconnect();
    return;
  }

  let ok = 0;
  let fail = 0;

  for (const r of rows) {
    try {
      process.stdout.write(`[${ok + fail + 1}/${rows.length}] ${r.source_id}: ${r.title.slice(0, 50)} ... `);
      const vec = await embedOne(r.solution_summary);
      const vecStr = `[${vec.join(',')}]`;
      await p.$executeRaw`
        UPDATE problems
        SET vector_embedding = ${vecStr}::vector,
            embedding_version = ${EMBED_VERSION},
            embedding_generated_at = NOW(),
            updated_at = NOW()
        WHERE id = ${r.id}::uuid
      `;
      console.log('OK');
      ok++;
    } catch (err: any) {
      console.log(`FAIL: ${err?.message || err}`);
      fail++;
    }
  }

  console.log(`\n完成: 成功 ${ok}, 失败 ${fail}`);
  await p.$disconnect();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
