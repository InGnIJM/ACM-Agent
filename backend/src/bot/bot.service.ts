import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { BotConfigDto } from './dto/bot-config.dto';
import {
  BotChannel,
  BotConfig,
  Platform,
  Prisma,
  PushMessageType,
  PushStatus,
} from '@prisma/client';

interface DailyReportData {
  date: string;
  topUser?: { nickname: string; acCount: number; platform: Platform };
  stats: { totalSubmits: number; totalAc: number; acRate: string };
  ranking: { rank: number; nickname: string; acCount: number; platform: Platform }[];
  platform?: Platform;
}

interface WeeklyReportData {
  weekLabel: string;
  totalAc: number;
  totalSubmits: number;
  acRate: string;
  activeUsers: number;
  strengths: string[];
  weaknesses: string[];
  topUsers: { nickname: string; acCount: number; platform: Platform }[];
  platform?: Platform;
}

@Injectable()
export class PushService {
  private readonly logger = new Logger(PushService.name);

  constructor(private readonly prisma: PrismaService) {}

  // ─── Send daily report ─────────────────────────────────────────────────────

  async sendDailyReport(
    channel: BotChannel,
    targetId: string,
    data: DailyReportData,
  ): Promise<void> {
    this.logger.log(`sendDailyReport channel=${channel} target=${targetId}`);
    const content = this.formatDailyReport(data);
    await this.sendAndLog(channel, targetId, PushMessageType.daily_report, { content, data });
  }

  // ─── Send weekly report ────────────────────────────────────────────────────

  async sendWeeklyReport(
    channel: BotChannel,
    targetId: string,
    data: WeeklyReportData,
  ): Promise<void> {
    this.logger.log(`sendWeeklyReport channel=${channel} target=${targetId}`);
    const content = this.formatWeeklyReport(data);
    await this.sendAndLog(channel, targetId, PushMessageType.weekly_report, { content, data });
  }

  // ─── Format daily report ───────────────────────────────────────────────────

  formatDailyReport(data: DailyReportData): Record<string, unknown> {
    const dateLabel = data.date ?? new Date().toISOString().slice(0, 10);

    // Feishu interactive card JSON
    const feishuCard = {
      header: {
        title: { tag: 'plain_text', content: `ACM 每日刷题日报 (${dateLabel})` },
        template: 'blue' as const,
      },
      elements: [
        {
          tag: 'markdown',
          content: [
            `**日期**：${dateLabel}`,
            data.topUser
              ? `**今日之星**：${data.topUser.nickname}（${data.topUser.acCount} AC，${data.topUser.platform}）`
              : `**今日之星**：--`,
            '',
            `**统计概览**：`,
            `- 总提交：${data.stats.totalSubmits}`,
            `- 总 AC：${data.stats.totalAc}`,
            `- AC 率：${data.stats.acRate}`,
            '',
            `**排行榜**：`,
            ...data.ranking.slice(0, 10).map(
              (r, i) =>
                `- ${i + 1}. ${r.nickname}（${r.acCount} AC，${r.platform}）`,
            ),
          ].join('\n'),
        },
      ],
    };

    // QQ Markdown (plain text with markdown notation)
    const qqMarkdown = [
      `## ACM 每日刷题日报 (${dateLabel})`,
      '',
      data.topUser
        ? `**今日之星**：${data.topUser.nickname}（${data.topUser.acCount} AC，${data.topUser.platform}）`
        : `**今日之星**：--`,
      '',
      `### 统计概览`,
      `- 总提交：${data.stats.totalSubmits}`,
      `- 总 AC：${data.stats.totalAc}`,
      `- AC 率：${data.stats.acRate}`,
      '',
      `### 排行榜`,
      ...data.ranking.slice(0, 10).map(
        (r, i) =>
          `- ${i + 1}. ${r.nickname}（${r.acCount} AC，${r.platform}）`,
      ),
    ].join('\n');

    return { feishu: feishuCard, qq: qqMarkdown };
  }

  // ─── Format weekly report ──────────────────────────────────────────────────

  formatWeeklyReport(data: WeeklyReportData): Record<string, unknown> {
    const weekLabel = data.weekLabel ?? '本周';

    const feishuCard = {
      header: {
        title: { tag: 'plain_text', content: `ACM 每周训练周报 (${weekLabel})` },
        template: 'wathet' as const,
      },
      elements: [
        {
          tag: 'markdown',
          content: [
            `**周期**：${weekLabel}`,
            '',
            `**统计概览**：`,
            `- 总提交：${data.totalSubmits}`,
            `- 总 AC：${data.totalAc}`,
            `- AC 率：${data.acRate}`,
            `- 活跃用户：${data.activeUsers}`,
            '',
            `**优势方向**：`,
            ...data.strengths.map((s) => `- ${s}`),
            '',
            `**薄弱方向**：`,
            ...data.weaknesses.map((w) => `- ${w}`),
            '',
            `**本周 TOP 5**：`,
            ...data.topUsers.slice(0, 5).map(
              (u, i) =>
                `- ${i + 1}. ${u.nickname}（${u.acCount} AC，${u.platform}）`,
            ),
          ].join('\n'),
        },
      ],
    };

    const qqMarkdown = [
      `## ACM 每周训练周报 (${weekLabel})`,
      '',
      `### 统计概览`,
      `- 总提交：${data.totalSubmits}`,
      `- 总 AC：${data.totalAc}`,
      `- AC 率：${data.acRate}`,
      `- 活跃用户：${data.activeUsers}`,
      '',
      `### 优势方向`,
      ...data.strengths.map((s) => `- ${s}`),
      '',
      `### 薄弱方向`,
      ...data.weaknesses.map((w) => `- ${w}`),
      '',
      `### 本周 TOP 5`,
      ...data.topUsers.slice(0, 5).map(
        (u, i) =>
          `- ${i + 1}. ${u.nickname}（${u.acCount} AC，${u.platform}）`,
      ),
    ].join('\n');

    return { feishu: feishuCard, qq: qqMarkdown };
  }

  // ─── Private: http send ────────────────────────────────────────────────────

  private async sendFeishu(webhookUrl: string, content: Record<string, unknown>): Promise<void> {
    try {
      const card = content.feishu ?? content;
      const response = await fetch(webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ msg_type: 'interactive', card }),
      });
      if (!response.ok) {
        throw new Error(`Feishu webhook returned ${response.status}`);
      }
    } catch (error) {
      this.logger.error(`sendFeishu failed: ${(error as Error).message}`);
      throw error;
    }
  }

  private async sendQQ(targetId: string, content: Record<string, unknown>): Promise<void> {
    // QQ Bot HTTP API — placeholder implementation
    this.logger.log(`sendQQ to=${targetId} content=${JSON.stringify(content).slice(0, 200)}`);
    // TODO: Integrate QQ Bot SDK or HTTP API when available
  }

  // ─── Send and log ──────────────────────────────────────────────────────────

  private async sendAndLog(
    channel: BotChannel,
    targetId: string,
    messageType: PushMessageType,
    content: Record<string, unknown>,
  ): Promise<void> {
    const sentAt = new Date();
    let status: PushStatus = PushStatus.sent;
    let errorMessage: string | null = null;

    try {
      if (channel === BotChannel.feishu) {
        // Look up webhook URL from user's config or use a default
        const config = await this.prisma.botConfig.findUnique({
          where: { channel_userId: { channel, userId: targetId } },
        });
        const webhookUrl = config?.webhookUrl;
        if (!webhookUrl) {
          throw new Error(`No feishu webhook URL configured for user ${targetId}`);
        }
        await this.sendFeishu(webhookUrl, content);
      } else if (channel === BotChannel.qq) {
        await this.sendQQ(targetId, content);
      }
    } catch (error) {
      status = PushStatus.failed;
      errorMessage = (error as Error).message;
      this.logger.error(`Push failed: ${errorMessage}`);
    }

    await this.prisma.pushLog.create({
      data: {
        channel,
        targetType: 'user',
        targetId,
        messageType,
        content: content as unknown as Prisma.JsonObject,
        sentAt,
        status,
        errorMessage,
      },
    });
  }

  // ─── BotConfig CRUD ────────────────────────────────────────────────────────

  async getConfigs(userId: string): Promise<BotConfig[]> {
    return this.prisma.botConfig.findMany({
      where: { userId, deletedAt: null },
      orderBy: { channel: 'asc' },
    });
  }

  async upsertConfig(userId: string, dto: BotConfigDto): Promise<BotConfig> {
    const create: Prisma.BotConfigCreateInput = {
      channel: dto.channel,
      webhookUrl: dto.webhookUrl ?? null,
      enabled: dto.enabled ?? true,
      scheduleCron: dto.scheduleCron ?? null,
      user: { connect: { id: userId } },
    };

    const update: Prisma.BotConfigUpdateInput = {
      webhookUrl: dto.webhookUrl ?? undefined,
      enabled: dto.enabled ?? undefined,
      scheduleCron: dto.scheduleCron ?? undefined,
    };

    return this.prisma.botConfig.upsert({
      where: { channel_userId: { channel: dto.channel, userId } },
      create,
      update,
    });
  }

  async deleteConfig(userId: string, channel: BotChannel): Promise<BotConfig> {
    const config = await this.prisma.botConfig.findUnique({
      where: { channel_userId: { channel, userId } },
    });
    if (!config) {
      throw new NotFoundException(`BotConfig ${channel} not found`);
    }
    return this.prisma.botConfig.delete({
      where: { id: config.id },
    });
  }
}
