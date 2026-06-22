import { Injectable, BadRequestException } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { VectorService, SearchHit } from '../common/vector/vector.service';
import { QueryAnalysisService } from '../common/query-analysis/query-analysis.service';
import { RerankService, RerankCandidate } from '../common/rerank/rerank.service';

@Injectable()
export class ProblemService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly vectorService: VectorService,
    private readonly queryAnalysis: QueryAnalysisService,
    private readonly rerankService: RerankService,
  ) {}

  async findAll(query: any) {
    const where: any = {};
    if (query.platform) where.sourcePlatform = query.platform;
    if (query.difficultyMin || query.difficultyMax) {
      where.difficultyNormalized = {};
      if (query.difficultyMin) where.difficultyNormalized.gte = Number(query.difficultyMin);
      if (query.difficultyMax) where.difficultyNormalized.lte = Number(query.difficultyMax);
    }
    if (query.search) {
      where.title = { contains: query.search };
    }
    if (query.tags) {
      where.tagsNormalized = { hasSome: Array.isArray(query.tags) ? query.tags : [query.tags] };
    }

    const page = Number(query.page) || 1;
    const limit = Number(query.limit) || 20;

    const [data, total] = await Promise.all([
      this.prisma.problem.findMany({
        where,
        skip: (page - 1) * limit,
        take: limit,
        orderBy: { createdAt: 'desc' },
      }),
      this.prisma.problem.count({ where }),
    ]);

    return { data, total, page, limit };
  }

  async findOne(id: string) {
    const problem = await this.prisma.problem.findUnique({
      where: { id },
      include: { solutions: true },
    });
    return problem;
  }

  async searchProblems(q: string) {
    if (!q) return [];
    const problems = await this.prisma.problem.findMany({
      where: { title: { contains: q } },
      take: 20,
      orderBy: { createdAt: 'desc' },
    });
    return problems.map((p) => ({ problem: p, score: 0 }));
  }

  async getSimilarProblems(id: string) {
    const problem = await this.prisma.problem.findUnique({ where: { id } });
    if (!problem || !problem.tagsNormalized?.length) return [];
    const similar = await this.prisma.problem.findMany({
      where: {
        id: { not: id },
        tagsNormalized: { hasSome: problem.tagsNormalized },
      },
      take: 10,
      orderBy: { createdAt: 'desc' },
    });
    return similar;
  }

  /** Semantic vector search — embeds query, ANN searches problems by solution_summary vector. */
  async searchByVector(dto: {
    query: string;
    topK?: number;
    platform?: string;
    tags?: string;
    difficultyMin?: number;
    difficultyMax?: number;
  }) {
    const { query, topK = 20, platform, tags, difficultyMin, difficultyMax } = dto;

    // Validate
    if (!query || query.trim().length < 2) {
      throw new BadRequestException('查询内容过短，至少输入 2 个字符');
    }

    // 1. Query analysis
    let analysis;
    try {
      analysis = this.queryAnalysis.analyze(query);
    } catch (err: any) {
      throw new BadRequestException(err.message);
    }

    // 2. Generate query embedding
    const queryVec = await this.vectorService.embedQuery(query);

    // 3. Three-path parallel recall (with individual 3s timeout)
    const [contentHits, solutionHits, keywordHits] = await Promise.allSettled([
      this.withTimeout(this.vectorService.searchByContentVector(queryVec, 80), 3000),
      this.withTimeout(this.vectorService.searchBySolutionVector(queryVec, 80), 3000),
      this.withTimeout(
        this.vectorService.searchByKeyword(this.buildOrTsQuery(analysis.keywords), 50),
        3000,
      ),
    ]);

    // 4. Merge candidates (per-path min-max normalization)
    const candidates = this.mergeCandidates(
      this.unwrapHits(contentHits),
      this.unwrapHits(solutionHits),
      this.unwrapHits(keywordHits),
    );

    if (candidates.length === 0) {
      return { query, queryAnalysis: analysis, results: [], total: 0 };
    }

    // 5. Fetch full problem data for candidates
    const candidateIds = candidates.map(c => c.id);
    const problems = await this.prisma.problem.findMany({
      where: { id: { in: candidateIds }, deletedAt: null },
      select: {
        id: true, title: true, sourcePlatform: true, sourceId: true,
        difficultyNormalized: true, tagsNormalized: true,
        solutionSummary: true, retrievalSummary: true, fullContent: true,
      },
    });
    const problemMap = new Map(problems.map(p => [p.id, p]));

    // Hydrate candidates with DB data
    for (const c of candidates) {
      const p = problemMap.get(c.id);
      if (p) {
        c.title = p.title;
        c.sourcePlatform = p.sourcePlatform;
        c.sourceId = p.sourceId;
        c.difficultyNormalized = p.difficultyNormalized;
        c.tagsNormalized = p.tagsNormalized;
        c.solutionSummary = p.solutionSummary;
        c.retrievalSummary = p.retrievalSummary;
        c.fullContent = p.fullContent;
      }
    }

    // 6. Rough ranking with dynamic weights
    const roughRanked = this.roughRank(candidates, analysis.weights);

    // 7. Rerank top 20
    const top20 = roughRanked.slice(0, 20);
    let reranked = top20;
    if (top20.length > 0) {
      const rerankCandidates: RerankCandidate[] = top20.map(c => ({
        problemId: c.id,
        title: c.title,
        retrievalSummary: c.retrievalSummary,
        solutionSummary: c.solutionSummary,
        fullContent: c.fullContent,
        tagsNormalized: c.tagsNormalized,
        roughScore: c.roughScore,
      }));
      const rerankResults = await this.rerankService.rerank(query, rerankCandidates);
      reranked = top20
        .map(c => ({
          ...c,
          rerankScore: rerankResults.find(r => r.problemId === c.id)?.rerankScore ?? c.roughScore,
        }))
        .sort((a, b) => b.rerankScore - a.rerankScore);
    }

    // 8. Apply optional filters (platform, difficulty, tags) on final results
    let filtered = reranked;
    if (platform) {
      filtered = filtered.filter(r => r.sourcePlatform === platform);
    }
    if (difficultyMin != null) {
      filtered = filtered.filter(r => r.difficultyNormalized >= Number(difficultyMin));
    }
    if (difficultyMax != null) {
      filtered = filtered.filter(r => r.difficultyNormalized <= Number(difficultyMax));
    }
    if (tags) {
      const tagList = tags.split(',').map(t => t.trim()).filter(Boolean);
      if (tagList.length > 0) {
        filtered = filtered.filter(r =>
          tagList.some(t => (r.tagsNormalized || []).includes(t))
        );
      }
    }

    // 9. Format response (backward compatible)
    const results = filtered.slice(0, topK).map(r => ({
      id: r.id,
      title: r.title,
      sourcePlatform: r.sourcePlatform,
      sourceId: r.sourceId,
      difficultyNormalized: r.difficultyNormalized,
      tagsNormalized: r.tagsNormalized,
      solutionSummary: r.solutionSummary,
      retrievalSummary: r.retrievalSummary,
      similarity: r.rerankScore ?? r.roughScore,
      scores: {
        contentScore: r.contentScore,
        solutionScore: r.solutionScore,
        keywordScore: r.keywordScore,
        roughScore: r.roughScore,
        rerankScore: r.rerankScore,
      },
      matched: {
        keywords: r.matchedKeywords,
        sources: r.sources,
      },
    }));

    return {
      query,
      queryAnalysis: {
        queryType: analysis.queryType,
        expandedQuery: analysis.expandedQuery,
        algorithmTerms: analysis.algorithmTerms,
        weights: analysis.weights,
      },
      results,
      total: results.length,
    };
  }

  // ── Private helpers for hybrid search ──

  private buildOrTsQuery(keywords: string[]): string {
    return keywords
      .filter(k => k)
      .map(k => `'${k.replace(/'/g, "''")}'`)
      .join(' | ') || "'placeholder'";
  }

  private unwrapHits(result: PromiseSettledResult<SearchHit[]>): SearchHit[] {
    return result.status === 'fulfilled' ? result.value : [];
  }

  private async withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
    return Promise.race([
      promise,
      new Promise<T>((_, reject) => setTimeout(() => reject(new Error('timeout')), ms)),
    ]);
  }

  private mergeCandidates(
    contentHits: SearchHit[],
    solutionHits: SearchHit[],
    keywordHits: SearchHit[],
  ): CandidateRecord[] {
    const map = new Map<string, CandidateRecord>();

    const normContent = this.normalizePath(contentHits.map(h => h.score));
    const normSol = this.normalizePath(solutionHits.map(h => h.score));
    const normKW = this.normalizePath(keywordHits.map(h => h.score));

    contentHits.forEach((h, i) => {
      const c = this.getOrCreate(map, h.id);
      c.contentScore = normContent[i];
      c.sources.push('content_vector');
    });
    solutionHits.forEach((h, i) => {
      const c = this.getOrCreate(map, h.id);
      c.solutionScore = normSol[i];
      c.sources.push('solution_vector');
    });
    keywordHits.forEach((h, i) => {
      const c = this.getOrCreate(map, h.id);
      c.keywordScore = normKW[i];
      c.sources.push('keyword');
    });

    return Array.from(map.values());
  }

  private normalizePath(scores: number[]): number[] {
    if (scores.length < 2) return scores.map(() => 1.0);
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    if (max === min) return scores.map(() => 1.0);
    return scores.map(x => (x - min) / (max - min));
  }

  private getOrCreate(map: Map<string, CandidateRecord>, id: string): CandidateRecord {
    if (!map.has(id)) {
      map.set(id, {
        id,
        title: '',
        sourcePlatform: '',
        sourceId: '',
        difficultyNormalized: 0,
        tagsNormalized: [],
        solutionSummary: null,
        retrievalSummary: null,
        fullContent: null,
        contentScore: 0,
        solutionScore: 0,
        keywordScore: 0,
        roughScore: 0,
        rerankScore: 0,
        matchedKeywords: [],
        sources: [],
      });
    }
    return map.get(id)!;
  }

  private roughRank(candidates: CandidateRecord[], weights: { content: number; solution: number; keyword: number }): CandidateRecord[] {
    candidates.forEach(c => {
      c.roughScore = c.contentScore * weights.content
                   + c.solutionScore * weights.solution
                   + c.keywordScore * weights.keyword;
    });
    return candidates.sort((a, b) => b.roughScore - a.roughScore);
  }

  /** Soft-delete a single problem. */
  async deleteOne(id: string) {
    await this.prisma.problem.update({
      where: { id },
      data: { deletedAt: new Date() },
    });
    return { deleted: true };
  }

  /** Soft-delete multiple problems. */
  async deleteMany(ids: string[]) {
    await this.prisma.problem.updateMany({
      where: { id: { in: ids } },
      data: { deletedAt: new Date() },
    });
    return { deleted: true, count: ids.length };
  }
}

interface CandidateRecord {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  difficultyNormalized: number;
  tagsNormalized: string[];
  solutionSummary: string | null;
  retrievalSummary?: string | null;
  fullContent?: string | null;
  contentScore: number;
  solutionScore: number;
  keywordScore: number;
  roughScore: number;
  rerankScore: number;
  matchedKeywords: string[];
  sources: string[];
}
