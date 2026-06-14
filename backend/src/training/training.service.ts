import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';

@Injectable()
export class TrainingService {
  constructor(private readonly prisma: PrismaService) {}

  async getPlan(userId: string) {
    const plan = await this.prisma.trainingPlan.findFirst({
      where: { userId, status: 'active' },
      orderBy: { createdAt: 'desc' },
    });
    if (!plan) throw new NotFoundException('没有活跃的训练计划，请先生成');
    return plan;
  }

  async generatePlan(userId: string) {
    const profile = await this.prisma.userProfile.findUnique({ where: { userId } });
    if (!profile) throw new NotFoundException('请先生成用户画像');

    const plan = await this.prisma.trainingPlan.create({
      data: {
        userId,
        profileId: profile.id,
        phase: 'topic_breakthrough',
        weakTags: [],
        weeklyProblems: {},
        totalCount: 35,
      },
    });
    return plan;
  }

  async getRecommend() {
    return { message: '推荐功能建设中' };
  }
}
