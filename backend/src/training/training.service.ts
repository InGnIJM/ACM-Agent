import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { PythonService } from '../crawler/python.service';

@Injectable()
export class TrainingService {
  private readonly logger = new Logger(TrainingService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly pythonService: PythonService,
  ) {}

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

    // Call the training agent via Python CLI
    let planData: any;
    try {
      planData = await this.pythonService.execute('agents/training_agent_cli.py', {
        userId,
        profileId: profile.id,
        planDays: 7,
        dailyTarget: 5,
      });
      this.logger.log(`Training plan generated via agent for user ${userId}`);
    } catch (err: any) {
      this.logger.warn(`Training agent failed, using stub plan: ${err?.message || err}`);
      planData = {
        plan: {},
        targets: {},
        difficulty_curve: [],
        errors: [String(err?.message || err)],
      };
    }

    const plan = await this.prisma.trainingPlan.create({
      data: {
        userId,
        profileId: profile.id,
        phase: planData?.targets?.phase || 'topic_breakthrough',
        weakTags: planData?.targets?.primary || [],
        weeklyProblems: planData?.plan || {},
        difficultyCurve: planData?.difficulty_curve || [],
        targets: planData?.targets || {},
        totalCount: planData?.plan?.total_problems || 35,
      },
    });
    return plan;
  }

  async getRecommend() {
    return { message: '推荐功能建设中' };
  }
}
