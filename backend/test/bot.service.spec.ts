import { Test, TestingModule } from '@nestjs/testing';
import { PushService } from '../src/bot/bot.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { BotChannel, PushMessageType, PushStatus } from '@prisma/client';

describe('PushService', () => {
  let service: PushService;
  let prisma: {
    botConfig: {
      findUnique: jest.Mock;
      findMany: jest.Mock;
      upsert: jest.Mock;
      delete: jest.Mock;
    };
    pushLog: { create: jest.Mock };
    userDailyStat: { findMany: jest.Mock };
    userProfile: { findUnique: jest.Mock };
  };

  const mockFetch = jest.fn();

  beforeAll(() => {
    global.fetch = mockFetch as unknown as typeof global.fetch;
  });

  beforeEach(async () => {
    prisma = {
      botConfig: {
        findUnique: jest.fn(),
        findMany: jest.fn(),
        upsert: jest.fn(),
        delete: jest.fn(),
      },
      pushLog: { create: jest.fn() },
      userDailyStat: { findMany: jest.fn() },
      userProfile: { findUnique: jest.fn() },
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        PushService,
        { provide: PrismaService, useValue: prisma },
      ],
    }).compile();

    service = module.get<PushService>(PushService);

    jest.clearAllMocks();
  });

  afterAll(() => {
    // Restore fetch after tests
    Object.defineProperty(global, 'fetch', {
      value: undefined,
      writable: true,
    });
  });

  // ─── formatDailyReport ─────────────────────────────────────────────────────

  describe('formatDailyReport', () => {
    const dailyData = {
      date: '2026-06-12',
      topUser: { nickname: 'Alice', acCount: 8, platform: 'leetcode' as const },
      stats: { totalSubmits: 42, totalAc: 30, acRate: '71.4%' },
      ranking: [
        { rank: 1, nickname: 'Alice', acCount: 8, platform: 'leetcode' as const },
        { rank: 2, nickname: 'Bob', acCount: 6, platform: 'nowcoder' as const },
        { rank: 3, nickname: 'Charlie', acCount: 5, platform: 'luogu' as const },
      ],
    };

    it('returns a record with feishu and qq keys', () => {
      const result = service.formatDailyReport(dailyData);

      expect(result).toHaveProperty('feishu');
      expect(result).toHaveProperty('qq');
    });

    it('sets the feishu card header with the correct date', () => {
      const result = service.formatDailyReport(dailyData);
      const card = result.feishu as Record<string, unknown>;
      const header = card.header as Record<string, unknown>;
      const title = header.title as Record<string, unknown>;

      expect(title.tag).toBe('plain_text');
      expect(title.content).toContain('2026-06-12');
      expect(header.template).toBe('blue');
    });

    it('includes the top user in the feishu markdown content', () => {
      const result = service.formatDailyReport(dailyData);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('Alice');
      expect(content).toContain('8 AC');
    });

    it('includes stats overview in the feishu markdown content', () => {
      const result = service.formatDailyReport(dailyData);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('42');
      expect(content).toContain('30');
      expect(content).toContain('71.4%');
    });

    it('includes ranking entries in the feishu markdown content', () => {
      const result = service.formatDailyReport(dailyData);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('Alice');
      expect(content).toContain('Bob');
      expect(content).toContain('Charlie');
    });

    it('produces qq markdown with the date label', () => {
      const result = service.formatDailyReport(dailyData);
      const qq = result.qq as string;

      expect(qq).toContain('2026-06-12');
      expect(qq).toContain('ACM 每日刷题日报');
    });

    it('handles missing topUser gracefully', () => {
      const noTop = { ...dailyData, topUser: undefined };
      const result = service.formatDailyReport(noTop);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('--');
    });

    it('uses current date when date field is missing', () => {
      const noDate = { ...dailyData, date: undefined as unknown as string };
      const result = service.formatDailyReport(noDate);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;
      const today = new Date().toISOString().slice(0, 10);

      expect(content).toContain(today);
    });
  });

  // ─── formatWeeklyReport ────────────────────────────────────────────────────

  describe('formatWeeklyReport', () => {
    const weeklyData = {
      weekLabel: '2026-06-06 ~ 2026-06-12',
      totalAc: 85,
      totalSubmits: 120,
      acRate: '70.8%',
      activeUsers: 12,
      strengths: ['动态规划', '贪心算法'],
      weaknesses: ['图论', '字符串处理'],
      topUsers: [
        { nickname: 'Alice', acCount: 20, platform: 'leetcode' as const },
        { nickname: 'Bob', acCount: 18, platform: 'nowcoder' as const },
        { nickname: 'Charlie', acCount: 15, platform: 'luogu' as const },
      ],
    };

    it('returns a record with feishu and qq keys', () => {
      const result = service.formatWeeklyReport(weeklyData);

      expect(result).toHaveProperty('feishu');
      expect(result).toHaveProperty('qq');
    });

    it('sets the feishu card header with wathet template', () => {
      const result = service.formatWeeklyReport(weeklyData);
      const card = result.feishu as Record<string, unknown>;
      const header = card.header as Record<string, unknown>;

      expect(header.template).toBe('wathet');
    });

    it('includes strengths in the feishu markdown content', () => {
      const result = service.formatWeeklyReport(weeklyData);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('动态规划');
      expect(content).toContain('贪心算法');
    });

    it('includes weaknesses in the feishu markdown content', () => {
      const result = service.formatWeeklyReport(weeklyData);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('图论');
      expect(content).toContain('字符串处理');
    });

    it('includes stats overview in the feishu markdown content', () => {
      const result = service.formatWeeklyReport(weeklyData);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('120');
      expect(content).toContain('85');
      expect(content).toContain('70.8%');
      expect(content).toContain('12');
    });

    it('includes top users in the feishu markdown content', () => {
      const result = service.formatWeeklyReport(weeklyData);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('Alice');
      expect(content).toContain('Bob');
      expect(content).toContain('Charlie');
    });

    it('produces qq markdown with week label', () => {
      const result = service.formatWeeklyReport(weeklyData);
      const qq = result.qq as string;

      expect(qq).toContain('2026-06-06 ~ 2026-06-12');
      expect(qq).toContain('ACM 每周训练周报');
    });

    it('includes strengths and weaknesses in qq markdown', () => {
      const result = service.formatWeeklyReport(weeklyData);
      const qq = result.qq as string;

      expect(qq).toContain('动态规划');
      expect(qq).toContain('图论');
    });

    it('handles empty strengths and weaknesses gracefully', () => {
      const emptyData = { ...weeklyData, strengths: [], weaknesses: [] };
      const result = service.formatWeeklyReport(emptyData);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      // Should still render the sections without crashing
      expect(content).toContain('优势方向');
      expect(content).toContain('薄弱方向');
    });

    it('limits top users to 5 in the report', () => {
      const manyUsers = {
        ...weeklyData,
        topUsers: Array.from({ length: 8 }, (_, i) => ({
          nickname: `User${i + 1}`,
          acCount: 20 - i,
          platform: 'leetcode' as const,
        })),
      };
      const result = service.formatWeeklyReport(manyUsers);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('User1');
      expect(content).toContain('User5');
      expect(content).not.toContain('User6');
    });

    it('falls back to default week label when weekLabel is missing', () => {
      const noLabel = { ...weeklyData, weekLabel: undefined as unknown as string };
      const result = service.formatWeeklyReport(noLabel);
      const card = result.feishu as Record<string, unknown>;
      const elements = card.elements as Array<Record<string, unknown>>;
      const content = elements[0].content as string;

      expect(content).toContain('本周');
    });
  });

  // ─── sendDailyReport ───────────────────────────────────────────────────────

  describe('sendDailyReport', () => {
    const dailyData = {
      date: '2026-06-12',
      topUser: { nickname: 'Alice', acCount: 8, platform: 'leetcode' as const },
      stats: { totalSubmits: 42, totalAc: 30, acRate: '71.4%' },
      ranking: [
        { rank: 1, nickname: 'Alice', acCount: 8, platform: 'leetcode' as const },
      ],
    };

    it('calls fetch with feishu webhook and creates PushLog on success', async () => {
      prisma.botConfig.findUnique.mockResolvedValue({
        id: 'cfg-1',
        channel: BotChannel.feishu,
        userId: 'user-1',
        webhookUrl: 'https://hooks.example.com/feishu/webhook',
        enabled: true,
      });
      mockFetch.mockResolvedValue({ ok: true });
      prisma.pushLog.create.mockResolvedValue({ id: 'log-1' });

      await service.sendDailyReport(BotChannel.feishu, 'user-1', dailyData);

      // Should have called fetch with the feishu webhook URL
      expect(mockFetch).toHaveBeenCalledTimes(1);
      const fetchUrl = mockFetch.mock.calls[0][0];
      expect(fetchUrl).toBe('https://hooks.example.com/feishu/webhook');

      // Should have created a PushLog
      expect(prisma.pushLog.create).toHaveBeenCalledTimes(1);
      const logCall = prisma.pushLog.create.mock.calls[0][0];
      expect(logCall.data.channel).toBe(BotChannel.feishu);
      expect(logCall.data.targetType).toBe('user');
      expect(logCall.data.targetId).toBe('user-1');
      expect(logCall.data.messageType).toBe(PushMessageType.daily_report);
      expect(logCall.data.status).toBe(PushStatus.sent);
      expect(logCall.data.errorMessage).toBeNull();
    });

    it('creates PushLog with failed status when webhook URL is missing', async () => {
      prisma.botConfig.findUnique.mockResolvedValue(null);
      prisma.pushLog.create.mockResolvedValue({ id: 'log-fail' });

      await service.sendDailyReport(BotChannel.feishu, 'user-no-config', dailyData);

      expect(mockFetch).not.toHaveBeenCalled();
      expect(prisma.pushLog.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            status: PushStatus.failed,
            errorMessage: expect.stringContaining('No feishu webhook URL'),
          }),
        }),
      );
    });

    it('creates PushLog with failed status when fetch throws', async () => {
      prisma.botConfig.findUnique.mockResolvedValue({
        id: 'cfg-2',
        channel: BotChannel.feishu,
        userId: 'user-2',
        webhookUrl: 'https://hooks.example.com/broken',
        enabled: true,
      });
      mockFetch.mockRejectedValue(new Error('Network error'));
      prisma.pushLog.create.mockResolvedValue({ id: 'log-err' });

      await service.sendDailyReport(BotChannel.feishu, 'user-2', dailyData);

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(prisma.pushLog.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            status: PushStatus.failed,
            errorMessage: 'Network error',
          }),
        }),
      );
    });

    it('creates PushLog with failed status when feishu returns non-ok', async () => {
      prisma.botConfig.findUnique.mockResolvedValue({
        id: 'cfg-3',
        channel: BotChannel.feishu,
        userId: 'user-3',
        webhookUrl: 'https://hooks.example.com/feishu/bad',
        enabled: true,
      });
      mockFetch.mockResolvedValue({ ok: false, status: 500 });
      prisma.pushLog.create.mockResolvedValue({ id: 'log-500' });

      await service.sendDailyReport(BotChannel.feishu, 'user-3', dailyData);

      expect(prisma.pushLog.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            status: PushStatus.failed,
            errorMessage: expect.stringContaining('500'),
          }),
        }),
      );
    });

    it('handles qq channel without calling fetch', async () => {
      prisma.pushLog.create.mockResolvedValue({ id: 'log-qq' });

      await service.sendDailyReport(BotChannel.qq, 'user-4', dailyData);

      // QQ channel should not call feishu fetch
      const fetchCalls = mockFetch.mock.calls.filter(
        (call: string[]) => call[0]?.includes('feishu'),
      );
      expect(fetchCalls.length).toBe(0);
      // Should still create a PushLog
      expect(prisma.pushLog.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            channel: BotChannel.qq,
            messageType: PushMessageType.daily_report,
            status: PushStatus.sent,
          }),
        }),
      );
    });
  });

  // ─── upsertConfig ──────────────────────────────────────────────────────────

  describe('upsertConfig', () => {
    const userId = 'user-uuid-1';
    const dto = {
      channel: BotChannel.feishu,
      webhookUrl: 'https://hooks.example.com/feishu/new',
      enabled: true,
    };

    it('calls prisma.botConfig.upsert with correct create input', async () => {
      const expectedConfig = {
        id: 'cfg-new',
        channel: BotChannel.feishu,
        userId,
        webhookUrl: dto.webhookUrl,
        enabled: true,
        scheduleCron: null,
        createdAt: new Date(),
        updatedAt: new Date(),
        deletedAt: null,
      };
      prisma.botConfig.upsert.mockResolvedValue(expectedConfig);

      const result = await service.upsertConfig(userId, dto);

      expect(prisma.botConfig.upsert).toHaveBeenCalledTimes(1);
      const upsertArgs = prisma.botConfig.upsert.mock.calls[0][0];

      // Verify the where clause
      expect(upsertArgs.where).toEqual({
        channel_userId: { channel: BotChannel.feishu, userId },
      });

      // Verify create input has the right shape
      expect(upsertArgs.create.channel).toBe(BotChannel.feishu);
      expect(upsertArgs.create.webhookUrl).toBe(dto.webhookUrl);
      expect(upsertArgs.create.enabled).toBe(true);
      expect(upsertArgs.create.user).toEqual({ connect: { id: userId } });

      // Verify update input
      expect(upsertArgs.update.webhookUrl).toBe(dto.webhookUrl);
      expect(upsertArgs.update.enabled).toBe(true);

      expect(result).toEqual(expectedConfig);
    });

    it('handles dto without optional fields', async () => {
      const minimalDto = { channel: BotChannel.qq };
      prisma.botConfig.upsert.mockResolvedValue({
        id: 'cfg-min',
        channel: BotChannel.qq,
        userId,
        webhookUrl: null,
        enabled: true,
        scheduleCron: null,
        createdAt: new Date(),
        updatedAt: new Date(),
        deletedAt: null,
      });

      const result = await service.upsertConfig(userId, minimalDto);

      expect(prisma.botConfig.upsert).toHaveBeenCalledTimes(1);
      const upsertArgs = prisma.botConfig.upsert.mock.calls[0][0];

      expect(upsertArgs.create.webhookUrl).toBeNull();
      expect(upsertArgs.create.enabled).toBe(true);
      expect(result.channel).toBe(BotChannel.qq);
    });

    it('returns the upserted config with correct shape', async () => {
      const saved = {
        id: 'cfg-42',
        channel: BotChannel.feishu,
        userId,
        webhookUrl: 'https://hooks.example.com/feishu/custom',
        enabled: false,
        scheduleCron: '0 9 * * *',
        createdAt: new Date('2026-01-01'),
        updatedAt: new Date('2026-06-13'),
        deletedAt: null,
      };
      prisma.botConfig.upsert.mockResolvedValue(saved);

      const result = await service.upsertConfig(userId, {
        channel: BotChannel.feishu,
        webhookUrl: 'https://hooks.example.com/feishu/custom',
        enabled: false,
        scheduleCron: '0 9 * * *',
      });

      expect(result).toEqual(saved);
      expect(result.id).toBe('cfg-42');
    });
  });

  // ─── getConfigs ────────────────────────────────────────────────────────────

  describe('getConfigs', () => {
    it('returns configs for the given userId ordered by channel', async () => {
      const configs = [
        { id: 'c1', channel: BotChannel.feishu, userId: 'user-1', webhookUrl: null, enabled: true, scheduleCron: null, createdAt: new Date(), updatedAt: new Date(), deletedAt: null },
        { id: 'c2', channel: BotChannel.qq, userId: 'user-1', webhookUrl: null, enabled: false, scheduleCron: null, createdAt: new Date(), updatedAt: new Date(), deletedAt: null },
      ];
      prisma.botConfig.findMany.mockResolvedValue(configs);

      const result = await service.getConfigs('user-1');

      expect(prisma.botConfig.findMany).toHaveBeenCalledWith({
        where: { userId: 'user-1', deletedAt: null },
        orderBy: { channel: 'asc' },
      });
      expect(result).toHaveLength(2);
      expect(result[0].channel).toBe(BotChannel.feishu);
    });

    it('returns empty array when user has no configs', async () => {
      prisma.botConfig.findMany.mockResolvedValue([]);

      const result = await service.getConfigs('user-none');

      expect(result).toEqual([]);
    });
  });

  // ─── deleteConfig ──────────────────────────────────────────────────────────

  describe('deleteConfig', () => {
    it('deletes an existing config and returns it', async () => {
      const config = {
        id: 'cfg-del',
        channel: BotChannel.feishu,
        userId: 'user-1',
        webhookUrl: null,
        enabled: true,
        scheduleCron: null,
        createdAt: new Date(),
        updatedAt: new Date(),
        deletedAt: null,
      };
      prisma.botConfig.findUnique.mockResolvedValue(config);
      prisma.botConfig.delete.mockResolvedValue({ ...config, deletedAt: new Date() });

      const result = await service.deleteConfig('user-1', BotChannel.feishu);

      expect(prisma.botConfig.delete).toHaveBeenCalledWith({ where: { id: 'cfg-del' } });
      expect(result.deletedAt).not.toBeNull();
    });

    it('throws NotFoundException when config does not exist', async () => {
      prisma.botConfig.findUnique.mockResolvedValue(null);

      await expect(
        service.deleteConfig('user-none', BotChannel.qq),
      ).rejects.toThrow('BotConfig qq not found');

      expect(prisma.botConfig.delete).not.toHaveBeenCalled();
    });
  });
});
