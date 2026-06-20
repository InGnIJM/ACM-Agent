import { Injectable } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { VectorService } from '../common/vector/vector.service';

@Injectable()
export class ProblemService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly vectorService: VectorService,
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
    const queryVec = await this.vectorService.embedText(query);

    const filters: any = {};
    if (platform) filters.platform = platform;
    if (tags) filters.tags = tags.split(',').map((t) => t.trim()).filter(Boolean);
    if (difficultyMin != null) filters.difficultyMin = Number(difficultyMin);
    if (difficultyMax != null) filters.difficultyMax = Number(difficultyMax);

    const problems = await this.vectorService.searchProblems(queryVec, topK, filters);

    const results = problems.map((p) => ({
      id: p.id,
      title: p.title,
      sourcePlatform: p.sourcePlatform,
      sourceId: p.sourceId,
      difficultyNormalized: p.difficultyNormalized,
      tagsNormalized: p.tagsNormalized,
      solutionSummary: p.solutionSummary,
      similarity: p.similarity,
    }));

    return { query, results, total: results.length };
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
