import { Injectable } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';

@Injectable()
export class ProblemService {
  constructor(private readonly prisma: PrismaService) {}

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
}
