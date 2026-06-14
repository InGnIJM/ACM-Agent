import { Injectable, Logger, Inject, Optional } from '@nestjs/common';
import { Cron } from '@nestjs/schedule';
import { PrismaService } from '../common/prisma/prisma.service';

/** Injection token for the crawler trigger service (to be implemented). */
export const CRAWLER_TRIGGER = Symbol('CRAWLER_TRIGGER');

/** Injection token for the profile agent trigger service (to be implemented). */
export const PROFILE_AGENT_TRIGGER = Symbol('PROFILE_AGENT_TRIGGER');

/** Injection token for the bot push service (to be implemented). */
export const BOT_SERVICE = Symbol('BOT_SERVICE');

export interface CrawlerTrigger {
  crawlUser(userId: string): Promise<void>;
}

export interface ProfileAgentTrigger {
  generateProfile(userId: string): Promise<void>;
}

export interface BotService {
  sendDailyReport(): Promise<void>;
  sendWeeklyReport(): Promise<void>;
}

@Injectable()
export class CronService {
  private readonly logger = new Logger(CronService.name);

  constructor(
    private readonly prisma: PrismaService,
    @Optional()
    @Inject(CRAWLER_TRIGGER)
    private readonly crawlerTrigger?: CrawlerTrigger,
    @Optional()
    @Inject(PROFILE_AGENT_TRIGGER)
    private readonly profileAgentTrigger?: ProfileAgentTrigger,
    @Optional()
    @Inject(BOT_SERVICE)
    private readonly botService?: BotService,
  ) {}

  @Cron('0 2 * * *')
  async syncObservedUsers(): Promise<void> {
    try {
      const observedUsers = await this.prisma.user.findMany({
        where: { role: 'observed', deletedAt: null },
        select: { id: true },
      });

      for (const user of observedUsers) {
        await this.crawlerTrigger?.crawlUser(user.id);
      }

      this.logger.log(
        `syncObservedUsers: triggered crawler for ${observedUsers.length} observed users`,
      );
    } catch (error) {
      this.logger.error('syncObservedUsers failed', error);
    }
  }

  @Cron('0 4 * * *')
  async generateProfiles(): Promise<void> {
    try {
      // Find observed users who have a profile
      const usersWithProfile = await this.prisma.user.findMany({
        where: { role: 'observed', deletedAt: null },
        select: {
          id: true,
          profile: { select: { generatedAt: true } },
        },
      });

      let triggered = 0;

      for (const user of usersWithProfile) {
        // Check if any practice record exists newer than the last profile
        const lastProfileAt =
          user.profile?.generatedAt ?? new Date(0);

        const newRecordCount = await this.prisma.practiceRecord.count({
          where: {
            userId: user.id,
            submitTime: { gt: lastProfileAt },
          },
        });

        if (newRecordCount > 0) {
          await this.profileAgentTrigger?.generateProfile(user.id);
          triggered++;
        }
      }

      this.logger.log(
        `generateProfiles: triggered profile generation for ${triggered} users`,
      );
    } catch (error) {
      this.logger.error('generateProfiles failed', error);
    }
  }

  @Cron('0 8 * * *')
  async dailyPush(): Promise<void> {
    try {
      await this.botService?.sendDailyReport();
      this.logger.log('dailyPush: daily report sent');
    } catch (error) {
      this.logger.error('dailyPush failed', error);
    }
  }

  @Cron('0 8 * * 1')
  async weeklyPush(): Promise<void> {
    try {
      await this.botService?.sendWeeklyReport();
      this.logger.log('weeklyPush: weekly report sent');
    } catch (error) {
      this.logger.error('weeklyPush failed', error);
    }
  }
}
