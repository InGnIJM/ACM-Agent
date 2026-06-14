import { Test, TestingModule } from '@nestjs/testing';
import {
  CronService,
  CRAWLER_TRIGGER,
  PROFILE_AGENT_TRIGGER,
  BOT_SERVICE,
  CrawlerTrigger,
  ProfileAgentTrigger,
  BotService,
} from '../src/task/cron.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { ScheduleModule } from '@nestjs/schedule';

/** Metadata key used internally by @nestjs/schedule's @Cron decorator. */
const SCHEDULE_CRON_OPTIONS = 'SCHEDULE_CRON_OPTIONS';

// ---------------------------------------------------------------------------
// Mock factories
// ---------------------------------------------------------------------------

type MockPrisma = {
  user: { findMany: jest.Mock };
  practiceRecord: { count: jest.Mock };
};

function mockPrisma(): MockPrisma {
  return {
    user: { findMany: jest.fn() },
    practiceRecord: { count: jest.fn() },
  };
}

function mockCrawlerTrigger(): jest.Mocked<CrawlerTrigger> {
  return { crawlUser: jest.fn() };
}

function mockProfileAgentTrigger(): jest.Mocked<ProfileAgentTrigger> {
  return { generateProfile: jest.fn() };
}

function mockBotService(): jest.Mocked<BotService> {
  return { sendDailyReport: jest.fn(), sendWeeklyReport: jest.fn() };
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

describe('CronService', () => {
  let service: CronService;
  let prisma: ReturnType<typeof mockPrisma>;
  let crawler: ReturnType<typeof mockCrawlerTrigger>;
  let profileAgent: ReturnType<typeof mockProfileAgentTrigger>;
  let bot: ReturnType<typeof mockBotService>;
  let moduleRef: TestingModule;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  beforeAll(async () => {
    moduleRef = await Test.createTestingModule({
      imports: [ScheduleModule.forRoot()],
      providers: [
        CronService,
        { provide: PrismaService, useFactory: mockPrisma },
        { provide: CRAWLER_TRIGGER, useFactory: mockCrawlerTrigger },
        { provide: PROFILE_AGENT_TRIGGER, useFactory: mockProfileAgentTrigger },
        { provide: BOT_SERVICE, useFactory: mockBotService },
      ],
    }).compile();

    service = moduleRef.get<CronService>(CronService);
    prisma = moduleRef.get<PrismaService>(PrismaService) as any;
    crawler = moduleRef.get<CrawlerTrigger>(CRAWLER_TRIGGER as any) as any;
    profileAgent = moduleRef.get<ProfileAgentTrigger>(
      PROFILE_AGENT_TRIGGER as any,
    ) as any;
    bot = moduleRef.get<BotService>(BOT_SERVICE as any) as any;
  });

  afterAll(async () => {
    await moduleRef.close();
  });

  // ------------------------------------------------------------------
  // Decorator presence
  // ------------------------------------------------------------------

  describe('@Cron decorators', () => {
    it('should decorate syncObservedUsers with cron "0 2 * * *"', () => {
      const meta = Reflect.getOwnMetadata(
        SCHEDULE_CRON_OPTIONS,
        CronService.prototype.syncObservedUsers,
      );
      expect(meta).toBeDefined();
      expect(meta).toMatchObject({ cronTime: '0 2 * * *' });
    });

    it('should decorate generateProfiles with cron "0 4 * * *"', () => {
      const meta = Reflect.getOwnMetadata(
        SCHEDULE_CRON_OPTIONS,
        CronService.prototype.generateProfiles,
      );
      expect(meta).toBeDefined();
      expect(meta).toMatchObject({ cronTime: '0 4 * * *' });
    });

    it('should decorate dailyPush with cron "0 8 * * *"', () => {
      const meta = Reflect.getOwnMetadata(
        SCHEDULE_CRON_OPTIONS,
        CronService.prototype.dailyPush,
      );
      expect(meta).toBeDefined();
      expect(meta).toMatchObject({ cronTime: '0 8 * * *' });
    });

    it('should decorate weeklyPush with cron "0 8 * * 1"', () => {
      const meta = Reflect.getOwnMetadata(
        SCHEDULE_CRON_OPTIONS,
        CronService.prototype.weeklyPush,
      );
      expect(meta).toBeDefined();
      expect(meta).toMatchObject({ cronTime: '0 8 * * 1' });
    });
  });

  // ------------------------------------------------------------------
  // syncObservedUsers
  // ------------------------------------------------------------------

  describe('syncObservedUsers', () => {
    it('should fetch observed users and call crawler for each', async () => {
      const users = [{ id: 'u1' }, { id: 'u2' }, { id: 'u3' }];
      (prisma.user.findMany as jest.Mock).mockResolvedValue(users);

      await service.syncObservedUsers();

      expect(prisma.user.findMany).toHaveBeenCalledWith({
        where: { role: 'observed', deletedAt: null },
        select: { id: true },
      });
      expect(crawler.crawlUser).toHaveBeenCalledTimes(3);
      expect(crawler.crawlUser).toHaveBeenCalledWith('u1');
      expect(crawler.crawlUser).toHaveBeenCalledWith('u2');
      expect(crawler.crawlUser).toHaveBeenCalledWith('u3');
    });

    it('should handle empty observed user list gracefully', async () => {
      (prisma.user.findMany as jest.Mock).mockResolvedValue([]);

      await service.syncObservedUsers();

      expect(crawler.crawlUser).not.toHaveBeenCalled();
    });

    it('should catch and log errors without throwing', async () => {
      const logSpy = jest.spyOn(
        (service as any).logger,
        'error',
      );
      (prisma.user.findMany as jest.Mock).mockRejectedValue(
        new Error('DB down'),
      );

      await expect(service.syncObservedUsers()).resolves.toBeUndefined();
      expect(logSpy).toHaveBeenCalledWith(
        'syncObservedUsers failed',
        expect.any(Error),
      );
      logSpy.mockRestore();
    });
  });

  // ------------------------------------------------------------------
  // generateProfiles
  // ------------------------------------------------------------------

  describe('generateProfiles', () => {
    it('should trigger profile generation for users with new records', async () => {
      const users = [
        { id: 'u1', profile: { generatedAt: new Date('2025-01-01') } },
        { id: 'u2', profile: null }, // no profile — treated as epoch 0
        { id: 'u3', profile: { generatedAt: new Date('2025-06-01') } },
      ];
      (prisma.user.findMany as jest.Mock).mockResolvedValue(users);

      // Only u1 and u2 have new records; u3 has none
      (prisma.practiceRecord.count as jest.Mock)
        .mockResolvedValueOnce(5) // u1 — trigger
        .mockResolvedValueOnce(3) // u2 — trigger (no profile)
        .mockResolvedValueOnce(0); // u3 — skip

      await service.generateProfiles();

      expect(prisma.user.findMany).toHaveBeenCalledWith({
        where: { role: 'observed', deletedAt: null },
        select: {
          id: true,
          profile: { select: { generatedAt: true } },
        },
      });

      expect(profileAgent.generateProfile).toHaveBeenCalledTimes(2);
      expect(profileAgent.generateProfile).toHaveBeenCalledWith('u1');
      expect(profileAgent.generateProfile).toHaveBeenCalledWith('u2');

      // u3 had count=0 so not called
      expect(profileAgent.generateProfile).not.toHaveBeenCalledWith('u3');
    });

    it('should handle empty user list', async () => {
      (prisma.user.findMany as jest.Mock).mockResolvedValue([]);

      await service.generateProfiles();

      expect(profileAgent.generateProfile).not.toHaveBeenCalled();
    });

    it('should catch and log errors without throwing', async () => {
      const logSpy = jest.spyOn(
        (service as any).logger,
        'error',
      );
      (prisma.user.findMany as jest.Mock).mockRejectedValue(
        new Error('DB down'),
      );

      await expect(service.generateProfiles()).resolves.toBeUndefined();
      expect(logSpy).toHaveBeenCalledWith(
        'generateProfiles failed',
        expect.any(Error),
      );
      logSpy.mockRestore();
    });
  });

  // ------------------------------------------------------------------
  // dailyPush
  // ------------------------------------------------------------------

  describe('dailyPush', () => {
    it('should call botService.sendDailyReport', async () => {
      await service.dailyPush();
      expect(bot.sendDailyReport).toHaveBeenCalled();
    });

    it('should catch and log errors without throwing', async () => {
      const logSpy = jest.spyOn(
        (service as any).logger,
        'error',
      );
      (bot.sendDailyReport as jest.Mock).mockRejectedValue(
        new Error('Bot offline'),
      );

      await expect(service.dailyPush()).resolves.toBeUndefined();
      expect(logSpy).toHaveBeenCalledWith(
        'dailyPush failed',
        expect.any(Error),
      );
      logSpy.mockRestore();
    });
  });

  // ------------------------------------------------------------------
  // weeklyPush
  // ------------------------------------------------------------------

  describe('weeklyPush', () => {
    it('should call botService.sendWeeklyReport', async () => {
      await service.weeklyPush();
      expect(bot.sendWeeklyReport).toHaveBeenCalled();
    });

    it('should catch and log errors without throwing', async () => {
      const logSpy = jest.spyOn(
        (service as any).logger,
        'error',
      );
      (bot.sendWeeklyReport as jest.Mock).mockRejectedValue(
        new Error('Bot offline'),
      );

      await expect(service.weeklyPush()).resolves.toBeUndefined();
      expect(logSpy).toHaveBeenCalledWith(
        'weeklyPush failed',
        expect.any(Error),
      );
      logSpy.mockRestore();
    });
  });

  // ------------------------------------------------------------------
  // Optional dependency resilience
  // ------------------------------------------------------------------

  describe('optional dependency absence', () => {
    it('should not crash when crawlerTrigger is not provided', async () => {
      const users = [{ id: 'u4' }];
      (prisma.user.findMany as jest.Mock).mockResolvedValue(users);

      const bareModule = await Test.createTestingModule({
        imports: [ScheduleModule.forRoot()],
        providers: [
          CronService,
          { provide: PrismaService, useFactory: mockPrisma },
          // No CRAWLER_TRIGGER, PROFILE_AGENT_TRIGGER, or BOT_SERVICE provided
        ],
      }).compile();

      const bareService = bareModule.get<CronService>(CronService);

      await expect(bareService.syncObservedUsers()).resolves.toBeUndefined();
      await expect(bareService.generateProfiles()).resolves.toBeUndefined();
      await expect(bareService.dailyPush()).resolves.toBeUndefined();
      await expect(bareService.weeklyPush()).resolves.toBeUndefined();

      await bareModule.close();
    });
  });
});
