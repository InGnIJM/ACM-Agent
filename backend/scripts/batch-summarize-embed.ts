/**
 * batch-summarize-embed.ts
 *
 * 批量题解总结 + 向量嵌入脚本（线程池并发，poolSize=40）
 *
 * 流程：
 *   1. 清空所有 problems.vector_embedding
 *   2. 拉取全量题目
 *   3. 对每道题：
 *      a. 无 solution_summary → 调 DeepSeek 生成 → 写回 DB
 *      b. 有 solution_summary → 调 Ollama 生成向量 → 写回 DB
 *   4. 并发数 = 40（基于 Promise 信号量）
 *
 * 运行：
 *   cd backend
 *   npx ts-node scripts/batch-summarize-embed.ts
 *
 * 依赖环境变量（.env）：
 *   DATABASE_URL, DEEPSEEK_API_KEY, OLLAMA_URL（可选）
 */

import { PrismaClient } from '@prisma/client';
import * as dotenv from 'dotenv';
import * as path from 'path';

// 加载 .env
dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

// ── 配置 ──────────────────────────────────────────────────────────────────
const POOL_SIZE = 200;
const OLLAMA_URL = (process.env.OLLAMA_URL || 'http://localhost:11434').replace(/\/$/, '');
const EMBED_MODEL = process.env.EMBED_MODEL || 'qwen3-embedding:0.6b';

// DeepSeek 配置解析（DEEPSEEK_PROVIDER=aliyun → 阿里云百炼，留空/其他 → 官方）
function resolveDeepSeekConfig(): { apiKey: string; baseUrl: string; model: string } | null {
  const apiKey = (process.env.DEEPSEEK_API_KEY || '').trim();
  if (!apiKey || apiKey === 'sk-placeholder') return null;

  const provider = (process.env.DEEPSEEK_PROVIDER || 'deepseek').trim().toLowerCase();
  const model = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash';

  let baseUrl = process.env.DEEPSEEK_BASE_URL || '';
  if (!baseUrl) {
    baseUrl = provider === 'aliyun'
      ? 'https://dashscope.aliyuncs.com/compatible-mode/v1'
      : 'https://api.deepseek.com/v1';
  }
  // 向后兼容：旧配置无 /v1 后缀的自动追加
  if (!baseUrl.endsWith('/v1') && !baseUrl.endsWith('/v2') && !baseUrl.includes('/compatible-mode/')) {
    baseUrl = baseUrl.replace(/\/$/, '') + '/v1';
  }

  return { apiKey, baseUrl, model };
}

const deepseekConfig = resolveDeepSeekConfig();
const DEEPSEEK_KEY = deepseekConfig?.apiKey || '';
const DEEPSEEK_BASE = deepseekConfig?.baseUrl || '';
const DEEPSEEK_MODEL = deepseekConfig?.model || 'deepseek-v4-flash';

// ── 信号量（控制并发数）───────────────────────────────────────────────
class Semaphore {
  private permits: number;
  private queue: Array<() => void> = [];

  constructor(count: number) {
    this.permits = count;
  }

  async acquire(): Promise<void> {
    if (this.permits > 0) {
      this.permits--;
      return;
    }
    return new Promise<void>((resolve) => {
      this.queue.push(resolve);
    });
  }

  release(): void {
    const next = this.queue.shift();
    if (next) {
      next();
    } else {
      this.permits++;
    }
  }

  /** 包装一个 async 函数，自动 acquire/release */
  async run<T>(fn: () => Promise<T>): Promise<T> {
    await this.acquire();
    try {
      return await fn();
    } finally {
      this.release();
    }
  }
}

// ── 简单进度条 ───────────────────────────────────────────────────────────
function progress(done: number, total: number, label: string): void {
  const pct = ((done / total) * 100).toFixed(1);
  const barLen = 30;
  const filled = Math.floor((done / total) * barLen);
  const bar = '█'.repeat(filled) + '░'.repeat(barLen - filled);
  process.stdout.write(`\r  ${label} [${bar}] ${done}/${total} (${pct}%)`);
}

// ── DeepSeek 总结 ─────────────────────────────────────────────────────────
async function summarizeWithDeepSeek(
  title: string,
  fullContent: string,
  difficultyRaw: string,
): Promise<string | null> {
  if (!DEEPSEEK_KEY || DEEPSEEK_KEY === 'sk-placeholder') {
    return null;
  }

  const truncated = fullContent.length > 3000 ? fullContent.slice(0, 3000) : fullContent;
  const prompt = `You are an expert competitive programming analyst. Summarize the following problem concisely.

Title: ${title}
Difficulty: ${difficultyRaw}
Content: ${truncated}

Return a Chinese summary with these sections (2-3 sentences each):
【核心考点】...
【推荐解法】...
【易错点】...`;

  const resp = await fetch(`${DEEPSEEK_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${DEEPSEEK_KEY}`,
    },
    body: JSON.stringify({
      model: DEEPSEEK_MODEL,
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.3,
      max_tokens: 4096,
      thinking: { type: 'disabled' },
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`DeepSeek API error ${resp.status}: ${errText.slice(0, 200)}`);
  }

  const data: any = await resp.json();
  return data?.choices?.[0]?.message?.content || null;
}

// ── Ollama 嵌入 ───────────────────────────────────────────────────────────
async function embedWithOllama(text: string): Promise<number[]> {
  const url = `${OLLAMA_URL}/api/embed`;
  const payload = { model: EMBED_MODEL, input: [text] };

  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Ollama returned ${resp.status}: ${body.slice(0, 300)}`);
  }

  const data: any = await resp.json();
  if (!data.embeddings?.[0]) {
    throw new Error(`Unexpected Ollama response: ${JSON.stringify(data).slice(0, 300)}`);
  }

  return data.embeddings[0] as number[];
}

// ── 处理单道题目 ──────────────────────────────────────────────────────────
interface ProblemRow {
  id: string;
  sourceId: string;
  title: string;
  fullContent: string | null;
  solutionSummary: string | null;
  difficultyRaw: string | null;
}

async function processOneProblem(
  prisma: PrismaClient,
  p: ProblemRow,
  stats: { summarized: number; embedded: number; skipped: number; errors: number },
): Promise<void> {
  let summary = p.solutionSummary;

  // 检查三个必要段落是否都存在、末尾是否完整结束
  const hasAllSections = (s: string | null): boolean => {
    if (!s || s.trim().length === 0) return false;
    return /【核心考点】/.test(s) && /【推荐解法】/.test(s) && /【易错点】/.test(s)
      && /[。.！!？?）)]\s*$/.test(s.trim());
  };

  // Step 1: 无摘要或摘要不完整 → 重新生成摘要
  if (!hasAllSections(summary)) {
    try {
      summary = await summarizeWithDeepSeek(
        p.title,
        p.fullContent || '',
        p.difficultyRaw || '',
      );
      if (summary) {
        await prisma.$executeRaw`
          UPDATE problems
          SET solution_summary = ${summary},
              updated_at = NOW()
          WHERE id = ${p.id}::uuid
        `;
        stats.summarized++;
      }
    } catch (err: any) {
      stats.errors++;
      console.error(`\n  [ERR] summarize ${p.sourceId}: ${err.message}`);
      return;
    }
  }

  // Step 2: 有摘要 → 生成向量
  if (summary && summary.trim().length > 0) {
    try {
      const vec = await embedWithOllama(summary);
      const vecStr = `[${vec.join(',')}]`;
      await prisma.$executeRaw`
        UPDATE problems
        SET vector_embedding = ${vecStr}::vector,
            updated_at = NOW()
        WHERE id = ${p.id}::uuid
      `;
      stats.embedded++;
    } catch (err: any) {
      stats.errors++;
      console.error(`\n  [ERR] embed ${p.sourceId}: ${err.message}`);
      return;
    }
  } else {
    stats.skipped++;
  }
}

// ── 主流程 ────────────────────────────────────────────────────────────────
async function main() {
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║  批量题解总结 + 向量嵌入（并发 = 40）       ║');
  console.log('╚══════════════════════════════════════════════╝');
  console.log(`  DeepSeek: ${DEEPSEEK_KEY ? '已配置' : '❌ 未配置'}`);
  console.log(`  Ollama:   ${OLLAMA_URL}`);
  console.log(`  嵌入模型: ${EMBED_MODEL}`);
  console.log(`  并发数:   ${POOL_SIZE}`);
  console.log('');

  const prisma = new PrismaClient();
  const sem = new Semaphore(POOL_SIZE);
  const stats = { summarized: 0, embedded: 0, skipped: 0, errors: 0 };

  try {
    // ── Step 0: 清空所有向量存储 ──────────────────────────────────────
    console.log('[0] 清空现有向量存储...');
    const clearResult: any = await prisma.$executeRaw`
      UPDATE problems
      SET vector_embedding = NULL,
          updated_at = NOW()
      WHERE vector_embedding IS NOT NULL
    `;
    console.log(`    已清空 ${clearResult} 条向量记录\n`);

    // ── Step 1: 拉取全量题目 ─────────────────────────────────────────
    console.log('[1] 拉取全量题目...');
    const rows: any[] = await prisma.$queryRaw`
      SELECT id,
             source_id::text          AS "sourceId",
             title,
             full_content             AS "fullContent",
             solution_summary         AS "solutionSummary",
             difficulty_raw           AS "difficultyRaw"
      FROM problems
      WHERE deleted_at IS NULL
      ORDER BY created_at DESC
    `;
    const problems: ProblemRow[] = rows.map((r: any) => ({
      id: r.id,
      sourceId: r.sourceId,
      title: r.title,
      fullContent: r.fullContent,
      solutionSummary: r.solutionSummary,
      difficultyRaw: r.difficultyRaw,
    }));

    const needSummary = problems.filter(p => !p.solutionSummary || p.solutionSummary.trim().length === 0).length;
    const total = problems.length;
    console.log(`    共 ${total} 道题目（需生成摘要: ${needSummary}，仅需嵌入: ${total - needSummary}）\n`);

    if (total === 0) {
      console.log('没有待处理的题目，退出。');
      return;
    }

    // ── Step 2: 并发处理 ─────────────────────────────────────────────
    console.log('[2] 开始并发处理...');
    const startTime = Date.now();
    let completed = 0;

    const tasks = problems.map((p) =>
      sem.run(async () => {
        await processOneProblem(prisma, p, stats);
        completed++;
        if (completed % 10 === 0 || completed === total) {
          progress(completed, total, '处理进度');
        }
      }),
    );

    await Promise.all(tasks);
    console.log(''); // 换行

    // ── Step 3: 输出统计 ─────────────────────────────────────────────
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`\n[3] 完成！耗时 ${elapsed}s`);
    console.log(`    生成摘要: ${stats.summarized}`);
    console.log(`    生成向量: ${stats.embedded}`);
    console.log(`    跳过:     ${stats.skipped}（无摘要且 DeepSeek 未配置）`);
    console.log(`    错误:     ${stats.errors}`);
    console.log(`    总计:     ${total}`);

  } finally {
    await prisma.$disconnect();
  }
}

main().catch((err) => {
  console.error('脚本异常退出:', err);
  process.exit(1);
});
