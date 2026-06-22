import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { VectorService } from '../common/vector/vector.service';

export interface MigrationOptions {
  dryRun: boolean;
  limit: number;
  fromCreatedAt?: Date;
  stage: 'summary' | 'embedding' | 'solution_summary' | 'solution_embedding' | 'all';
  concurrency: number;
  batchSize: number;
  maxRetries: number;
}

export interface MigrationReport {
  total: number;
  success: number;
  failed: number;
  skipped: number;
  durationMs: number;
}

@Injectable()
export class RagMigrationService {
  private readonly logger = new Logger(RagMigrationService.name);
  private readonly CURRENT_RETRIEVAL_VER = 'algo-rag-summary-v1';
  private readonly CURRENT_EMBED_VER = 'qwen3-embedding:0.6b@ollama';

  constructor(
    private readonly prisma: PrismaService,
    private readonly vectorService: VectorService,
  ) {}

  async migrate(options: MigrationOptions): Promise<MigrationReport> {
    const startedAt = Date.now();
    let success = 0, failed = 0, skipped = 0;

    const pending = await this.findPending(options);
    this.logger.log(`Found ${pending.length} problems to migrate (stage=${options.stage})`);

    if (options.dryRun) {
      this.logger.log(`[DRY RUN] Would process ${pending.length} problems`);
      return { total: pending.length, success: 0, failed: 0, skipped: pending.length, durationMs: Date.now() - startedAt };
    }

    for (let i = 0; i < pending.length; i += options.concurrency) {
      const batch = pending.slice(i, i + options.concurrency);
      const results = await Promise.allSettled(
        batch.map(p => this.processOne(p, options)),
      );
      results.forEach((r, j) => {
        if (r.status === 'fulfilled') success++;
        else { failed++; this.logger.error(`Problem ${batch[j].id}: ${r.reason}`); }
      });
      this.logger.log(`Progress: ${i + batch.length}/${pending.length} (success=${success} failed=${failed})`);
    }

    return { total: pending.length, success, failed, skipped, durationMs: Date.now() - startedAt };
  }

  async getStatus(): Promise<{ stage: string; status: string; count: number }[]> {
    const rows: any[] = await this.prisma.$queryRawUnsafe(
      `SELECT stage, status, COUNT(*) as count FROM rag_migration_logs GROUP BY stage, status ORDER BY stage, status`
    );
    return rows.map(r => ({ stage: r.stage, status: r.status, count: Number(r.count) }));
  }

  private async findPending(options: MigrationOptions) {
    const conditions: string[] = ['p.deleted_at IS NULL'];
    const params: string[] = [];

    if (options.fromCreatedAt) {
      params.push(options.fromCreatedAt.toISOString());
      conditions.push(`p.created_at > $${params.length}::timestamptz`);
    }

    if (options.stage === 'summary' || options.stage === 'all') {
      conditions.push(`(p.retrieval_summary IS NULL OR p.retrieval_version != '${this.CURRENT_RETRIEVAL_VER}')`);
    }
    if (options.stage === 'embedding' || options.stage === 'all') {
      conditions.push(`(p.vector_embedding IS NULL OR p.embedding_version != '${this.CURRENT_EMBED_VER}' OR p.content_vector IS NULL)`);
    }

    const where = conditions.map(c => `  AND ${c}`).join('\n');
    const limitClause = options.limit > 0 ? `LIMIT ${options.limit}` : '';
    const sql = `SELECT id, solution_summary, full_content, tags_normalized, retrieval_summary FROM problems p WHERE 1=1 ${where} ORDER BY created_at ${limitClause}`;

    const rows: any[] = params.length > 0
      ? await this.prisma.$queryRawUnsafe(sql, ...params)
      : await this.prisma.$queryRawUnsafe(sql);
    return rows;
  }

  private async processOne(problem: any, options: MigrationOptions): Promise<void> {
    const stage = options.stage === 'all' ? 'embedding' : options.stage;
    for (let attempt = 0; attempt < options.maxRetries; attempt++) {
      try {
        await this.prisma.$executeRawUnsafe(
          `INSERT INTO rag_migration_logs (problem_id, stage, status, started_at)
           VALUES ($1::uuid, $2, 'running', NOW())
           ON CONFLICT (problem_id, stage) DO UPDATE SET status = 'running', started_at = NOW()`,
          problem.id, stage,
        );

        if (options.stage === 'embedding' || options.stage === 'all') {
          const summaryText = problem.retrieval_summary || problem.solution_summary || '';
          if (summaryText) {
            const summaryVec = await this.vectorService.embedSummary(summaryText);
            await this.vectorService.setProblemVector(problem.id, summaryVec);
          }

          if (problem.full_content) {
            const contentVec = await this.vectorService.embedContent(problem.full_content);
            await this.vectorService.setContentVector(problem.id, contentVec);
          }
        }

        await this.prisma.$executeRawUnsafe(
          `UPDATE rag_migration_logs SET status = 'success', finished_at = NOW()
           WHERE problem_id = $1::uuid AND stage = $2`,
          problem.id, stage,
        );
        return;
      } catch (err: any) {
        if (attempt === options.maxRetries - 1) {
          await this.prisma.$executeRawUnsafe(
            `UPDATE rag_migration_logs SET status = 'failed', message = $3, finished_at = NOW()
             WHERE problem_id = $1::uuid AND stage = $2`,
            problem.id, stage, err.message?.slice(0, 500) || String(err),
          );
          throw err;
        }
        await new Promise(r => setTimeout(r, 2000 * (attempt + 1)));
      }
    }
  }
}
