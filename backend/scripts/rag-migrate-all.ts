/**
 * RAG 全量数据迁移
 *
 * 用法:
 *   npx ts-node scripts/rag-migrate-all.ts
 *   npx ts-node scripts/rag-migrate-all.ts --stage=summary --limit=100
 *   npx ts-node scripts/rag-migrate-all.ts --stage=embedding --from-date=2026-06-20
 *
 * 环境变量: DEEPSEEK_API_KEY, OLLAMA_URL
 */

import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// ── Config ────────────────────────────────────────────────────
const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY || '';
const PROVIDER = (process.env.DEEPSEEK_PROVIDER || 'deepseek').toLowerCase();
const LLM_MODEL = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash';
const LLM_BASE = process.env.DEEPSEEK_BASE_URL
  || (PROVIDER === 'aliyun'
    ? 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    : 'https://api.deepseek.com/v1');

const OLLAMA_URL = (process.env.OLLAMA_URL || 'http://localhost:11434').replace(/\/$/, '');
const EMBED_MODEL = process.env.EMBED_MODEL || 'qwen3-embedding:0.6b';
const EMBED_VERSION = 'qwen3-embedding:0.6b@ollama';
const RETRIEVAL_VERSION = 'algo-rag-summary-v1';

const CONCURRENCY_LLM = 10;   // DeepSeek 并发
const CONCURRENCY_EMBED = 4;  // Ollama 并发（信号量）

// ── CLI ───────────────────────────────────────────────────────
const args = process.argv.slice(2);
function getArg(key: string): string | undefined {
  const idx = args.indexOf(`--${key}`);
  return idx >= 0 ? args[idx + 1] : undefined;
}

const STAGE = getArg('stage') || 'all';          // summary | embedding | all
const LIMIT = parseInt(getArg('limit') || '0');  // 0 = no limit
const FROM_DATE = getArg('from-date');           // YYYY-MM-DD for resuming
const DRY_RUN = args.includes('--dry-run');

// ── Helpers ──────────────────────────────────────────────────
function toVec(v: number[]): string { return `[${v.join(',')}]`; }

async function embedOllama(texts: string[]): Promise<number[][]> {
  let lastErr: Error | null = null;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
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
    } catch (err) {
      lastErr = err instanceof Error ? err : new Error(String(err));
      if (attempt < 3) await new Promise(r => setTimeout(r, 2000 * (attempt + 1)));
    }
  }
  throw lastErr;
}

async function callDeepSeek(prompt: string): Promise<any> {
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const resp = await fetch(`${LLM_BASE}/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${DEEPSEEK_API_KEY}` },
        body: JSON.stringify({
          model: LLM_MODEL,
          messages: [{ role: 'user', content: prompt }],
          temperature: 0.3, max_tokens: 4096,
          response_format: { type: 'json_object' },
        }),
      });
      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(`DeepSeek ${resp.status}: ${errText.slice(0, 300)}`);
      }
      const data: any = await resp.json();
      return JSON.parse(data?.choices?.[0]?.message?.content || '{}');
    } catch (err) {
      if (err instanceof SyntaxError) throw err; // JSON parse error, don't retry
      if (attempt < 3) await new Promise(r => setTimeout(r, 3000 * (attempt + 1)));
    }
  }
  throw new Error('DeepSeek failed after 4 attempts');
}

async function semaphore<T>(tasks: (() => Promise<T>)[], limit: number): Promise<T[]> {
  const results: T[] = new Array(tasks.length);
  let idx = 0;
  async function worker() {
    while (idx < tasks.length) {
      const i = idx++;
      try { results[i] = await tasks[i](); }
      catch (err: any) { results[i] = err; }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, tasks.length) }, () => worker()));
  return results;
}

// ── Stage: Summary generation ─────────────────────────────────
async function migrateSummary() {
  const fromClause = FROM_DATE ? `AND p.created_at > '${FROM_DATE}'::timestamptz` : '';
  const limitClause = LIMIT > 0 ? `LIMIT ${LIMIT}` : '';

  const problems = await prisma.$queryRawUnsafe(`
    SELECT id, title, source_platform, source_id, difficulty_raw, tags_normalized,
           solution_summary, full_content
    FROM problems p
    WHERE p.deleted_at IS NULL
      AND p.solution_summary IS NOT NULL
      AND (p.retrieval_summary IS NULL OR p.retrieval_version != '${RETRIEVAL_VERSION}')
      AND p.id NOT IN (
        SELECT problem_id FROM rag_migration_logs
        WHERE stage = 'summary' AND status = 'success'
      )
      ${fromClause}
    ORDER BY p.created_at
    ${limitClause}
  `) as any[];

  console.log(`📝 Stage: summary — ${problems.length} problems\n`);

  if (DRY_RUN) {
    console.log(`[DRY RUN] Would process ${problems.length} problems`);
    return { total: problems.length, success: 0, fail: 0 };
  }

  let success = 0, fail = 0, done = 0;
  const startedAt = Date.now();

  const tasks = problems.map(p => async () => {
    try {
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

      await prisma.$executeRawUnsafe(`
        UPDATE problems
        SET retrieval_summary = $1, sparse_text = $2, primary_algo = $3,
            sub_algos = $4::text[], problem_patterns = $5::text[],
            retrieval_version = $6, retrieval_summary_generated_at = NOW(),
            updated_at = NOW()
        WHERE id = $7::uuid
      `, result.retrieval_summary || '', result.sparse_text || '',
         result.primary_algo || '', result.sub_algos || [], result.problem_patterns || [],
         RETRIEVAL_VERSION, p.id);

      await prisma.$executeRawUnsafe(`
        INSERT INTO rag_migration_logs (problem_id, stage, status, duration_ms, started_at, finished_at)
        VALUES ($1::uuid, 'summary', 'success', 0, NOW(), NOW())
        ON CONFLICT (problem_id, stage) DO UPDATE SET status = 'success', finished_at = NOW()
      `, p.id);

      success++;
    } catch (err: any) {
      fail++;
      const msg = err.message?.slice(0, 500) || String(err);
      await prisma.$executeRawUnsafe(`
        INSERT INTO rag_migration_logs (problem_id, stage, status, message, started_at, finished_at)
        VALUES ($1::uuid, 'summary', 'failed', $2, NOW(), NOW())
        ON CONFLICT (problem_id, stage) DO UPDATE SET status = 'failed', message = $2, finished_at = NOW()
      `, p.id, msg).catch(() => {});
    }
    done++;
    if (done % 50 === 0) {
      const elapsed = ((Date.now() - startedAt) / 1000).toFixed(0);
      console.log(`  ${done}/${problems.length} (${elapsed}s) — OK=${success} FAIL=${fail}`);
    }
  });

  await semaphore(tasks, CONCURRENCY_LLM);
  const elapsed = ((Date.now() - startedAt) / 1000).toFixed(0);
  console.log(`\n✅ Summary done: ${success} OK, ${fail} FAIL (${elapsed}s)\n`);
  return { total: problems.length, success, fail };
}

// ── Stage: Embedding generation ───────────────────────────────
async function migrateEmbedding() {
  const fromClause = FROM_DATE ? `AND p.created_at > '${FROM_DATE}'::timestamptz` : '';
  const limitClause = LIMIT > 0 ? `LIMIT ${LIMIT}` : '';

  const problems = await prisma.$queryRawUnsafe(`
    SELECT id, source_id, source_platform,
           COALESCE(retrieval_summary, solution_summary, '') AS summary_text,
           COALESCE(full_content, '') AS content_text
    FROM problems p
    WHERE p.deleted_at IS NULL
      AND (p.vector_embedding IS NULL OR p.embedding_version != '${EMBED_VERSION}'
           OR p.content_vector IS NULL)
      AND p.id NOT IN (
        SELECT problem_id FROM rag_migration_logs
        WHERE stage = 'embedding' AND status = 'success'
      )
      ${fromClause}
    ORDER BY p.created_at
    ${limitClause}
  `) as any[];

  console.log(`🔢 Stage: embedding — ${problems.length} problems\n`);

  if (DRY_RUN) {
    console.log(`[DRY RUN] Would process ${problems.length} problems`);
    return { total: problems.length, success: 0, fail: 0 };
  }

  let success = 0, fail = 0, done = 0;
  const startedAt = Date.now();

  const instContent = '为算法题题面生成用于题意相似检索的向量，重点关注输入输出、目标、约束条件、问题结构和场景描述。';
  const instSolution = '为算法题解法摘要生成用于相似题检索的向量，重点关注算法类型、题目模式、触发条件、核心思想、状态语义、不变量和高区分度易错点。';

  const tasks = problems.map(p => async () => {
    try {
      const summaryText = `${instSolution}\n\n${(p.summary_text || '').slice(0, 3000)}`;
      const contentText = `${instContent}\n\n${(p.content_text || '').slice(0, 4000)}`;

      const [summaryVec, contentVec] = await embedOllama([summaryText, contentText]);

      await prisma.$executeRawUnsafe(`
        UPDATE problems
        SET vector_embedding = $1::vector, content_vector = $2::vector,
            embedding_version = $3, embedding_generated_at = NOW(), updated_at = NOW()
        WHERE id = $4::uuid
      `, toVec(summaryVec), toVec(contentVec), EMBED_VERSION, p.id);

      await prisma.$executeRawUnsafe(`
        INSERT INTO rag_migration_logs (problem_id, stage, status, duration_ms, started_at, finished_at)
        VALUES ($1::uuid, 'embedding', 'success', 0, NOW(), NOW())
        ON CONFLICT (problem_id, stage) DO UPDATE SET status = 'success', finished_at = NOW()
      `, p.id);

      success++;
    } catch (err: any) {
      fail++;
      const msg = err.message?.slice(0, 500) || String(err);
      await prisma.$executeRawUnsafe(`
        INSERT INTO rag_migration_logs (problem_id, stage, status, message, started_at, finished_at)
        VALUES ($1::uuid, 'embedding', 'failed', $2, NOW(), NOW())
        ON CONFLICT (problem_id, stage) DO UPDATE SET status = 'failed', message = $2, finished_at = NOW()
      `, p.id, msg).catch(() => {});
    }
    done++;
    if (done % 50 === 0) {
      const elapsed = ((Date.now() - startedAt) / 1000).toFixed(0);
      console.log(`  ${done}/${problems.length} (${elapsed}s) — OK=${success} FAIL=${fail}`);
    }
  });

  await semaphore(tasks, CONCURRENCY_EMBED);
  const elapsed = ((Date.now() - startedAt) / 1000).toFixed(0);
  console.log(`\n✅ Embedding done: ${success} OK, ${fail} FAIL (${elapsed}s)\n`);
  return { total: problems.length, success, fail };
}

// ── Main ─────────────────────────────────────────────────────
async function main() {
  if (!DEEPSEEK_API_KEY || DEEPSEEK_API_KEY === 'sk-placeholder') {
    console.error('❌ DEEPSEEK_API_KEY not set.');
    process.exit(1);
  }

  console.log(`🚀 RAG Migration — stage=${STAGE} limit=${LIMIT || '∞'} from=${FROM_DATE || 'start'} dry=${DRY_RUN}\n`);

  if (STAGE === 'summary' || STAGE === 'all') {
    await migrateSummary();
  }
  if (STAGE === 'embedding' || STAGE === 'all') {
    await migrateEmbedding();
  }

  await prisma.$disconnect();
  console.log('🎉 Migration complete.');
}

main().catch(err => { console.error('Fatal:', err); process.exit(1); });
