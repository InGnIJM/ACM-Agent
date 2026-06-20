import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

export interface VectorSearchFilters {
  platform?: string;
  tags?: string[];
  difficultyMin?: number;
  difficultyMax?: number;
}

export interface ProblemSearchResult {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  difficultyNormalized: number;
  tagsNormalized: string[];
  solutionSummary: string | null;
  similarity: number;
}

@Injectable()
export class VectorService {
  private readonly logger = new Logger(VectorService.name);
  private readonly ollamaUrl: string;
  private readonly model: string;

  constructor(private readonly prisma: PrismaService) {
    this.ollamaUrl =
      (process.env.OLLAMA_URL || 'http://localhost:11434').replace(/\/$/, '');
    this.model = process.env.EMBED_MODEL || 'qwen3-embedding:0.6b';
  }

  // ------------------------------------------------------------------
  // Embedding
  // ------------------------------------------------------------------

  /** Embed a single text and return a 1024-dim float vector. */
  async embedText(text: string): Promise<number[]> {
    const results = await this.embedTexts([text]);
    return results[0];
  }

  /** Embed multiple texts in one call. Returns one vector per input text. */
  async embedTexts(texts: string[]): Promise<number[][]> {
    if (!texts.length) return [];

    const url = `${this.ollamaUrl}/api/embed`;
    const payload = { model: this.model, input: texts };

    let lastErr: Error | null = null;
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          const body = await response.text().catch(() => '');
          throw new Error(
            `Ollama returned ${response.status}: ${body.slice(0, 500)}`,
          );
        }

        const data: any = await response.json();
        if (!data.embeddings || !Array.isArray(data.embeddings)) {
          throw new Error(
            `Unexpected Ollama response shape: ${JSON.stringify(data).slice(0, 300)}`,
          );
        }

        return data.embeddings as number[][];
      } catch (err) {
        lastErr = err instanceof Error ? err : new Error(String(err));
        if (attempt < 3) {
          const delay = 2 ** (attempt + 1) * 1000;
          this.logger.warn(
            `Ollama embedding attempt ${attempt + 1} failed, retrying in ${delay}ms: ${lastErr.message}`,
          );
          await new Promise((r) => setTimeout(r, delay));
        }
      }
    }

    throw new Error(
      `Ollama embedding failed after 4 attempts: ${lastErr?.message}`,
    );
  }

  // ------------------------------------------------------------------
  // Vector writes (raw SQL — Prisma Unsupported type)
  // ------------------------------------------------------------------

  /** Write the solution_summary embedding vector for a problem. */
  async setProblemVector(
    problemId: string,
    vec: number[],
  ): Promise<void> {
    if (!vec.length) return;

    await this.prisma.$executeRaw`
      UPDATE problems
      SET vector_embedding = ${this._toVec(vec)}::vector,
          updated_at       = NOW()
      WHERE id = ${problemId}::uuid
    `;
    this.logger.debug(`Vector written for problem ${problemId}`);
  }

  // ------------------------------------------------------------------
  // Vector search (raw SQL — pgvector ANN)
  // ------------------------------------------------------------------

  /**
   * ANN search on problems.vector_embedding (solution_summary vector).
   * Returns problems ranked by cosine similarity.
   */
  async searchProblems(
    queryVec: number[],
    topK: number = 20,
    filters?: VectorSearchFilters,
  ): Promise<ProblemSearchResult[]> {
    const conditions: string[] = [
      'p.deleted_at IS NULL',
      'p.vector_embedding IS NOT NULL',
    ];
    const params: string[] = [this._toVec(queryVec)];

    let paramIdx = 2;

    if (filters?.platform) {
      conditions.push(`p.source_platform::text = $${paramIdx++}::text`);
      params.push(filters.platform);
    }
    if (filters?.difficultyMin != null) {
      conditions.push(
        `p.difficulty_normalized >= $${paramIdx++}::float`,
      );
      params.push(String(filters.difficultyMin));
    }
    if (filters?.difficultyMax != null) {
      conditions.push(
        `p.difficulty_normalized <= $${paramIdx++}::float`,
      );
      params.push(String(filters.difficultyMax));
    }
    if (filters?.tags && filters.tags.length > 0) {
      conditions.push(`p.tags_normalized && $${paramIdx++}::text[]`);
      params.push(`{${filters.tags.join(',')}}`);
    }

    const where = conditions.map((c) => `  AND ${c}`).join('\n');

    const sql = `
      SELECT p.id,
             p.title,
             p.source_platform::text  AS "sourcePlatform",
             p.source_id              AS "sourceId",
             p.difficulty_normalized  AS "difficultyNormalized",
             p.tags_normalized        AS "tagsNormalized",
             p.solution_summary       AS "solutionSummary",
             1 - (p.vector_embedding <=> $1::vector) AS similarity
      FROM problems p
      WHERE 1=1
      ${where}
      ORDER BY p.vector_embedding <=> $1::vector
      LIMIT $${paramIdx++}::bigint
    `;
    params.push(String(topK));

    // Wrap SET + SELECT in a transaction so they share the same connection
    const rows: any[] = await this.prisma.$transaction([
      this.prisma.$executeRawUnsafe('SET LOCAL ivfflat.probes = 10'),
      this.prisma.$queryRawUnsafe(sql, ...params),
    ]).then(([, selectResult]) => selectResult as any[]);
    return rows.map(this._mapProblemRow);
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  /** Convert a number[] to pgvector literal `'[0.1,0.2,...]'`. */
  private _toVec(v: number[]): string {
    return `[${v.join(',')}]`;
  }

  private _mapProblemRow(r: any): ProblemSearchResult {
    return {
      id: r.id,
      title: r.title,
      sourcePlatform: r.sourcePlatform,
      sourceId: r.sourceId,
      difficultyNormalized: Number(r.difficultyNormalized),
      tagsNormalized: r.tagsNormalized || [],
      solutionSummary: r.solutionSummary,
      similarity: Number(r.similarity),
    };
  }
}
