/**
 * RAG 数据迁移脚本 — 测试批（5题）
 *
 * 用法: npx ts-node scripts/rag-migrate-test.ts
 * 环境变量: DEEPSEEK_API_KEY, OLLAMA_URL
 */

import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// ── DeepSeek config ──────────────────────────────────────────
const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY || '';
const PROVIDER = (process.env.DEEPSEEK_PROVIDER || 'deepseek').toLowerCase();
const MODEL = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash';
const BASE_URL = process.env.DEEPSEEK_BASE_URL
  || (PROVIDER === 'aliyun'
    ? 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    : 'https://api.deepseek.com/v1');

// ── Ollama config ────────────────────────────────────────────
const OLLAMA_URL = (process.env.OLLAMA_URL || 'http://localhost:11434').replace(/\/$/, '');
const EMBED_MODEL = process.env.EMBED_MODEL || 'qwen3-embedding:0.6b';
const EMBED_VERSION = 'qwen3-embedding:0.6b@ollama';
const RETRIEVAL_VERSION = 'algo-rag-summary-v1';

// ── Helpers ──────────────────────────────────────────────────
function toVec(v: number[]): string {
  return `[${v.join(',')}]`;
}

async function embedOllama(texts: string[]): Promise<number[][]> {
  const resp = await fetch(`${OLLAMA_URL}/api/embed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: EMBED_MODEL, input: texts }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Ollama ${resp.status}: ${body.slice(0, 300)}`);
  }
  const data: any = await resp.json();
  return data.embeddings;
}

async function callDeepSeek(prompt: string): Promise<any> {
  const resp = await fetch(`${BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${DEEPSEEK_API_KEY}`,
    },
    body: JSON.stringify({
      model: MODEL,
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.3,
      max_tokens: 4096,
      response_format: { type: 'json_object' },
    }),
  });
  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`DeepSeek ${resp.status}: ${errText.slice(0, 300)}`);
  }
  const data: any = await resp.json();
  const content = data?.choices?.[0]?.message?.content || '{}';
  return JSON.parse(content);
}

// ── Main ─────────────────────────────────────────────────────
async function main() {
  if (!DEEPSEEK_API_KEY || DEEPSEEK_API_KEY === 'sk-placeholder') {
    console.error('❌ DEEPSEEK_API_KEY not set. Set it in .env or environment.');
    process.exit(1);
  }

  // Fetch test batch
  const problems = await prisma.$queryRawUnsafe(`
    SELECT id, title, source_platform, source_id, difficulty_raw, tags_normalized,
           solution_summary, full_content
    FROM problems
    WHERE deleted_at IS NULL
      AND solution_summary IS NOT NULL
      AND retrieval_summary IS NULL
    ORDER BY created_at DESC
    LIMIT 5
  `) as any[];

  console.log(`📦 Processing ${problems.length} problems (test batch)\n`);

  let success = 0, fail = 0;

  for (const p of problems) {
    const label = `${p.source_platform}/${p.source_id}: ${p.title.substring(0, 50)}`;
    try {
      // ── Step 1: Generate retrieval_summary via DeepSeek ──
      const prompt = `You are an expert competitive programming analyst. Based on the existing solution summary, generate retrieval-oriented fields.

Title: ${p.title}
Difficulty: ${p.difficulty_raw || 'unknown'}
Tags: ${JSON.stringify(p.tags_normalized || [])}

Existing solution summary:
${p.solution_summary}

Return a JSON object with these keys:
- retrieval_summary: A 150-350 character Chinese summary for vector search. Must include: (1) problem type and algorithm subtype, (2) problem pattern, (3) why this algorithm fits, (4) core state semantics or invariants, (5) 1-3 distinctive pitfalls. Must NOT include: full code, long formulas, variable names, boilerplate advice.
- sparse_text: Space-separated keywords (Chinese + English), including algorithm names, aliases, data structure names
- primary_algo: The main algorithm category
- sub_algos: Array of algorithm subtypes
- problem_patterns: Array of problem patterns

Return ONLY the JSON object, no markdown fences.`;

      const result = await callDeepSeek(prompt);
      const retrievalSummary = result.retrieval_summary || '';
      const sparseText = result.sparse_text || '';
      const primaryAlgo = result.primary_algo || '';
      const subAlgos = result.sub_algos || [];
      const problemPatterns = result.problem_patterns || [];

      console.log(`  📝 ${label}`);
      console.log(`     retrieval_summary: ${retrievalSummary.substring(0, 80)}...`);
      console.log(`     sparse_text: ${sparseText.substring(0, 60)}...`);

      // ── Step 2: Generate vectors via Ollama ──
      const instContent = '为算法题题面生成用于题意相似检索的向量，重点关注输入输出、目标、约束条件、问题结构和场景描述。';
      const instSolution = '为算法题解法摘要生成用于相似题检索的向量，重点关注算法类型、题目模式、触发条件、核心思想、状态语义、不变量和高区分度易错点。';

      const contentText = `${instContent}\n\n${(p.full_content || '').slice(0, 4000)}`;
      const summaryText = `${instSolution}\n\n${retrievalSummary || p.solution_summary}`;

      const [contentVec, summaryVec] = await embedOllama([contentText, summaryText]);

      // ── Step 3: Update DB ──
      const vecStr = toVec(summaryVec);
      const cntStr = toVec(contentVec);
      await prisma.$executeRawUnsafe(`
        UPDATE problems
        SET retrieval_summary = $1,
            sparse_text = $2,
            primary_algo = $3,
            sub_algos = $4::text[],
            problem_patterns = $5::text[],
            retrieval_version = $6,
            retrieval_summary_generated_at = NOW(),
            vector_embedding = $7::vector,
            content_vector = $8::vector,
            embedding_version = $9,
            embedding_generated_at = NOW(),
            updated_at = NOW()
        WHERE id = $10::uuid
      `, retrievalSummary, sparseText, primaryAlgo, subAlgos, problemPatterns,
         RETRIEVAL_VERSION, vecStr, cntStr, EMBED_VERSION, p.id);

      console.log(`     ✅ migrated (${summaryVec.length}d vec, ${contentVec.length}d content)\n`);
      success++;
    } catch (err: any) {
      console.error(`     ❌ ${err.message?.slice(0, 200)}\n`);
      fail++;
    }
  }

  console.log(`\n🎯 Done: ${success} OK, ${fail} FAIL`);
  await prisma.$disconnect();
}

main().catch((err) => {
  console.error('Fatal:', err);
  process.exit(1);
});
