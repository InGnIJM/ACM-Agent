import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';

@Injectable()
export class ProfileService {
  constructor(private readonly prisma: PrismaService) {}

  async getProfile(userId: string) {
    const profile = await this.prisma.userProfile.findUnique({
      where: { userId },
      include: { user: { select: { username: true, nickname: true } } },
    });
    if (!profile) {
      throw new NotFoundException('画像不存在，请先生成画像');
    }
    return profile;
  }

  async generateProfile(userId: string) {
    // Check user exists
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) throw new NotFoundException('用户不存在');

    // Check if there are enough records to generate profile
    const recordCount = await this.prisma.practiceRecord.count({ where: { userId } });
    if (recordCount < 10) {
      throw new NotFoundException('练习记录不足（需要至少10条），无法生成画像');
    }

    // Create or update profile with basic stats
    // Full 6-dimension profile generation is handled by Python profile_agent
    const profile = await this.prisma.userProfile.upsert({
      where: { userId },
      create: {
        userId,
        generatedAt: new Date(),
        overallScore: 0,
        coverage: 0,
        ceiling: 0,
        efficiency: 0,
        momentum: 0,
        version: 1,
      },
      update: {
        generatedAt: new Date(),
        version: { increment: 1 },
      },
    });

    return { profile, message: '画像已生成，请稍后查看详细报告' };
  }
}
