import { Injectable, Logger } from '@nestjs/common';

export interface RerankCandidate {
  problemId: string;
  title: string;
  retrievalSummary?: string | null;
  solutionSummary?: string | null;
  fullContent?: string | null;
  tagsNormalized: string[];
  roughScore: number;
}

export interface RerankResult {
  problemId: string;
  rerankScore: number;
}

@Injectable()
export class RerankService {
  private readonly logger = new Logger(RerankService.name);
  private readonly rerankUrl: string;

  constructor() {
    this.rerankUrl = process.env.RERANK_URL || 'http://127.0.0.1:8088/v1/rerank';
  }

  async rerank(query: string, candidates: RerankCandidate[]): Promise<RerankResult[]> {
    if (!candidates.length) return [];

    const documents = this.formatDocuments(query, candidates);

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);

      const resp = await fetch(this.rerankUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, documents }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!resp.ok) {
        throw new Error(`Rerank server returned ${resp.status}`);
      }

      const data: any = await resp.json();
      const scores: Array<{ index: number; relevance_score: number }> = data.results || [];

      if (scores.length >= 2 && this.isDegraded(scores.map(s => s.relevance_score))) {
        this.logger.warn('Rerank scores degraded (variance < 0.01), falling back to rough scores');
        return candidates.map(c => ({ problemId: c.problemId, rerankScore: c.roughScore }));
      }

      return scores.map(s => ({
        problemId: candidates[s.index]?.problemId || '',
        rerankScore: s.relevance_score,
      }));
    } catch (err: any) {
      this.logger.warn(`Rerank failed (${err.message}), returning rough scores`);
      return candidates.map(c => ({ problemId: c.problemId, rerankScore: c.roughScore }));
    }
  }

  private formatDocuments(_query: string, candidates: RerankCandidate[]): string[] {
    return candidates.map(c => {
      const summary = (c.retrievalSummary || c.solutionSummary || c.fullContent || '');
      const truncated = summary.length > 120 ? summary.slice(0, 120) : summary;
      const tags = (c.tagsNormalized || []).join(' ');
      return `${c.title} | ${truncated} | tags: ${tags}`;
    });
  }

  private isDegraded(scores: number[]): boolean {
    if (scores.length < 2) return false;
    const max = Math.max(...scores);
    const min = Math.min(...scores);
    return (max - min) < 0.01;
  }
}
