import { Injectable, Logger } from '@nestjs/common';
import { Cron } from '@nestjs/schedule';
import { PrismaService } from '../common/prisma/prisma.service';
import { PushService } from './bot.service';

@Injectable()
export class BotScheduler {
  private readonly logger = new Logger(BotScheduler.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly pushService: PushService,
  ) {}

  /** Daily push at 8:00 AM — aggregate yesterday's stats across all users, send to each active config. */
  @Cron('0 8 * * *', { name: 'daily-push' })
  async handleDailyPush(): Promise<void> {
    this.logger.log('Triggered daily push cron');
    const configs = await this.prisma.botConfig.findMany({
      where: { enabled: true, deletedAt: null },
    });

    if (configs.length === 0) {
      this.logger.log('No active bot configs, skipping daily push');
      return;
    }

    const data = await this.buildDailyData();

    for (const cfg of configs) {
      try {
        await this.pushService.sendDailyReport(cfg.channel, cfg.userId, data);
      } catch (error) {
        this.logger.error(
          `Daily push failed for user ${cfg.userId}: ${(error as Error).message}`,
        );
      }
    }
  }

  /** Weekly push every Monday at 8:00 AM — per-user weekly stats with profile strengths/weaknesses. */
  @Cron('0 8 * * 1', { name: 'weekly-push' })
  async handleWeeklyPush(): Promise<void> {
    this.logger.log('Triggered weekly push cron');
    const configs = await this.prisma.botConfig.findMany({
      where: { enabled: true, deletedAt: null },
    });

    if (configs.length === 0) {
      this.logger.log('No active bot configs, skipping weekly push');
      return;
    }

    for (const cfg of configs) {
      try {
        const data = await this.buildWeeklyData(cfg.userId);
        await this.pushService.sendWeeklyReport(cfg.channel, cfg.userId, data);
      } catch (error) {
        this.logger.error(
          `Weekly push failed for user ${cfg.userId}: ${(error as Error).message}`,
        );
      }
    }
  }

  // ─── Daily data builder ─────────────────────────────────────────────────────

  /**
   * Aggregate yesterday's stats from user_daily_stats across all users.
   * Returns a global daily report (top users, total submits, AC rate).
   */
  async buildDailyData() {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    yesterday.setHours(0, 0, 0, 0);
    const yesterdayEnd = new Date(yesterday);
    yesterdayEnd.setHours(23, 59, 59, 999);

    const stats = await this.prisma.userDailyStat.findMany({
      where: { statDate: { gte: yesterday, lte: yesterdayEnd } },
      include: { user: { select: { nickname: true } } },
      orderBy: { acCount: 'desc' },
    });

    const totalSubmits = stats.reduce((sum, s) => sum + s.submitCount, 0);
    const totalAc = stats.reduce((sum, s) => sum + s.acCount, 0);
    const acRate = totalSubmits > 0 ? `${((totalAc / totalSubmits) * 100).toFixed(1)}%` : '0%';

    const ranking = stats.slice(0, 10).map((s, i) => ({
      rank: i + 1,
      nickname: s.user.nickname ?? `user_${s.userId.slice(0, 8)}`,
      acCount: s.acCount,
      platform: s.platform,
    }));

    return {
      date: yesterday.toISOString().slice(0, 10),
      topUser: ranking[0],
      stats: { totalSubmits, totalAc, acRate },
      ranking,
    };
  }

  // ─── Weekly data builder ────────────────────────────────────────────────────

  /**
   * Aggregate the given user's last 7-day stats and fetch their current profile
   * for personalized strengths / weaknesses.
   */
  async buildWeeklyData(userId: string) {
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    weekAgo.setHours(0, 0, 0, 0);

    // User's own weekly stats
    const userStats = await this.prisma.userDailyStat.findMany({
      where: { userId, statDate: { gte: weekAgo } },
    });

    const totalAc = userStats.reduce((sum, s) => sum + s.acCount, 0);
    const totalSubmits = userStats.reduce((sum, s) => sum + s.submitCount, 0);
    const acRate = totalSubmits > 0 ? `${((totalAc / totalSubmits) * 100).toFixed(1)}%` : '0%';
    const activeUsers = new Set(userStats.map((s) => s.userId)).size;

    // Fetch current profile for strengths / weaknesses
    const profile = await this.prisma.userProfile.findUnique({
      where: { userId, deletedAt: null },
      select: { strengths: true, weaknesses: true },
    });

    const strengths: string[] = (profile?.strengths as string[]) ?? [];
    const weaknesses: string[] = (profile?.weaknesses as string[]) ?? [];

    // Global top users this week
    const allWeeklyStats = await this.prisma.userDailyStat.findMany({
      where: { statDate: { gte: weekAgo } },
      include: { user: { select: { nickname: true } } },
      orderBy: { acCount: 'desc' },
      take: 5,
    });

    const topUsers = allWeeklyStats.map((s) => ({
      nickname: s.user.nickname ?? `user_${s.userId.slice(0, 8)}`,
      acCount: s.acCount,
      platform: s.platform,
    }));

    return {
      weekLabel: `${weekAgo.toISOString().slice(0, 10)} ~ ${new Date().toISOString().slice(0, 10)}`,
      totalAc,
      totalSubmits,
      acRate,
      activeUsers,
      strengths,
      weaknesses,
      topUsers,
    };
  }
}
