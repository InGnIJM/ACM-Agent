import { Test, TestingModule } from '@nestjs/testing';
import * as fs from 'fs';
import { CrawlerController } from '../src/crawler/crawler.controller';
import { PythonService } from '../src/crawler/python.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { VectorService } from '../src/common/vector/vector.service';

// ---------------------------------------------------------------------------
// Mock the entire fs module so we can control existsSync/readdirSync etc.
// ---------------------------------------------------------------------------
jest.mock('fs');

const mockedFs = fs as jest.Mocked<typeof fs>;

// ---------------------------------------------------------------------------
// Mocks (follow existing patterns from test/crawler.controller.spec.ts)
// ---------------------------------------------------------------------------
const mockPythonService = {
  execute: jest.fn(),
  spawn: jest.fn(),
  cancelJob: jest.fn(),
} as any;

const mockPrisma = {
  $executeRaw: jest.fn().mockResolvedValue(1),
  $queryRaw: jest.fn().mockResolvedValue([]),
  problem: {
    findMany: jest.fn().mockResolvedValue([]),
    findUnique: jest.fn().mockResolvedValue({ id: 'mock-problem-id' }),
    upsert: jest.fn().mockResolvedValue({}),
    update: jest.fn().mockResolvedValue({}),
    updateMany: jest.fn().mockResolvedValue({ count: 0 }),
    count: jest.fn().mockResolvedValue(0),
  },
  practiceRecord: { upsert: jest.fn().mockResolvedValue({}) },
  problemSolution: { upsert: jest.fn().mockResolvedValue({ id: 'sol-1' }) },
  crawlJob: {
    create: jest.fn().mockResolvedValue({ id: 'job-1' }),
    findUnique: jest.fn().mockResolvedValue(null),
    findFirst: jest.fn().mockResolvedValue(null),
    update: jest.fn().mockResolvedValue({}),
    findMany: jest.fn().mockResolvedValue([]),
  },
} as any;

const mockVectorService = {
  embedText: jest.fn().mockResolvedValue(new Array(1024).fill(0.1)),
  setProblemVector: jest.fn(),
} as any;

// Prevent real HTTP calls from summarizeUnprocessed (fire-and-forget in triggerProblemCrawl)
// ---------------------------------------------------------------------------
// FS mock helpers (use the jest-mocked fs module)
// ---------------------------------------------------------------------------

/**
 * Configure the mocked fs for importPlatformData tests.
 */
function configFsForImport(opts: {
  platformDirExists?: boolean;
  problemCount?: number;
  recordCount?: number;
  solutionCount?: number;
} = {}) {
  const {
    platformDirExists = true,
    problemCount = 0,
    recordCount = 0,
    solutionCount = 0,
  } = opts;

  mockedFs.existsSync.mockImplementation((p: fs.PathLike) => {
    const s = String(p).replace(/\\/g, '/');
    if (!platformDirExists) return false;
    if (s.endsWith('/test-platform')) return true;
    if (s.endsWith('/test-platform/problems') && problemCount > 0) return true;
    if (s.endsWith('/test-platform/records') && recordCount > 0) return true;
    if (s.endsWith('/test-platform/solutions') && solutionCount > 0) return true;
    return false;
  });

  mockedFs.readdirSync.mockImplementation((p: any) => {
    const s = String(p).replace(/\\/g, '/');
    if (s.endsWith('/test-platform/problems')) {
      return Array.from({ length: problemCount }, (_, i) => `2024-01-0${i + 1}_P00${i + 1}.json`) as any;
    }
    if (s.endsWith('/test-platform/records')) {
      return Array.from({ length: recordCount }, (_, i) => `2024-01-0${i + 1}_R00${i + 1}.json`) as any;
    }
    if (s.endsWith('/test-platform/solutions')) {
      return Array.from({ length: solutionCount }, (_, i) => `2024-01-0${i + 1}_S00${i + 1}.json`) as any;
    }
    return [] as any;
  });

  mockedFs.readFileSync.mockImplementation((p: any) => {
    const s = String(p);
    if (s.includes('P00')) return JSON.stringify({ title: 'Test Problem', source_id: 'P001', difficulty: 'easy' });
    if (s.includes('R00')) return JSON.stringify({ id: 'R1', uid: 'u1', timestamp: '2024-01-01' });
    if (s.includes('S00')) return JSON.stringify([{ problem_id: 'P001', author: 'Author', content: 'Solution content' }]);
    return '{}';
  });

  mockedFs.unlinkSync.mockImplementation(() => {});
}

/**
 * Configure mocked fs for triggerProblemCrawl using 'luogu'.
 */
function configFsForTriggerCrawl() {
  mockedFs.existsSync.mockImplementation((p: fs.PathLike) => {
    const s = String(p).replace(/\\/g, '/');
    if (s.endsWith('/luogu')) return true;
    if (s.endsWith('/luogu/problems')) return true;
    return false;
  });

  mockedFs.readdirSync.mockImplementation((p: any) => {
    const s = String(p).replace(/\\/g, '/');
    if (s.endsWith('/luogu/problems')) return ['2024-06-01_P001.json'] as any;
    return [] as any;
  });

  mockedFs.readFileSync.mockImplementation(() => {
    return JSON.stringify({ title: 'Test', source_id: 'P001', difficulty: 'easy' });
  });
}

/**
 * Reset mocked fs to safe defaults (no files exist).
 */
function resetFsSpies() {
  mockedFs.existsSync.mockReturnValue(false);
  mockedFs.readdirSync.mockReturnValue([] as any);
  mockedFs.readFileSync.mockReturnValue('{}');
  mockedFs.unlinkSync.mockImplementation(() => {});
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------
describe('CrawlerController — import breakdown', () => {
  let importCtrl: CrawlerController;
  let triggerCtrl: CrawlerController;

  beforeAll(async () => {
    // Prevent real HTTP calls from summarizeUnprocessed (fire-and-forget in triggerProblemCrawl)
    (global as any).fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ choices: [{ message: { content: 'Summary' } }] }),
    });

    const importModule: TestingModule = await Test.createTestingModule({
      controllers: [CrawlerController],
      providers: [
        { provide: PythonService, useValue: mockPythonService },
        { provide: PrismaService, useValue: mockPrisma },
        { provide: VectorService, useValue: mockVectorService },
      ],
    }).compile();

    const triggerModule: TestingModule = await Test.createTestingModule({
      controllers: [CrawlerController],
      providers: [
        { provide: PythonService, useValue: mockPythonService },
        { provide: PrismaService, useValue: mockPrisma },
        { provide: VectorService, useValue: mockVectorService },
      ],
    }).compile();

    importCtrl = importModule.get<CrawlerController>(CrawlerController);
    triggerCtrl = triggerModule.get<CrawlerController>(CrawlerController);
  });

  beforeEach(() => {
    jest.clearAllMocks();
    resetFsSpies();
  });

  // =========================================================================
  // importPlatformData — breakdown return
  // =========================================================================
  describe('importPlatformData', () => {
    const importData = (platform: string) =>
      (importCtrl as any).importPlatformData(platform);

    it('returns breakdown { problems, solutions, records, total } with correct counts', async () => {
      configFsForImport({ problemCount: 2, recordCount: 1, solutionCount: 3 });

      const result = await importData('test-platform');

      expect(result).toEqual({
        problems: 2,
        solutions: 3,
        records: 1,
        total: 6,
      });
    });

    it('has exactly four keys in the expected order', async () => {
      configFsForImport({ problemCount: 1 });

      const result = await importData('test-platform');

      expect(Object.keys(result)).toEqual(['problems', 'solutions', 'records', 'total']);
    });

    it('returns all zeros when platform directory does not exist', async () => {
      configFsForImport({ platformDirExists: false });

      const result = await importData('test-platform');

      expect(result).toEqual({
        problems: 0,
        solutions: 0,
        records: 0,
        total: 0,
      });
    });

    it('counts only problems when only problems subdirectory exists', async () => {
      configFsForImport({ problemCount: 3, recordCount: 0, solutionCount: 0 });

      const result = await importData('test-platform');

      expect(result).toEqual({
        problems: 3,
        solutions: 0,
        records: 0,
        total: 3,
      });
    });

    it('counts only records when only records subdirectory exists', async () => {
      configFsForImport({ problemCount: 0, recordCount: 5, solutionCount: 0 });

      const result = await importData('test-platform');

      expect(result).toEqual({
        problems: 0,
        solutions: 0,
        records: 5,
        total: 5,
      });
    });

    it('counts only solutions when only solutions subdirectory exists', async () => {
      configFsForImport({ problemCount: 0, recordCount: 0, solutionCount: 4 });

      const result = await importData('test-platform');

      expect(result).toEqual({
        problems: 0,
        solutions: 4,
        records: 0,
        total: 4,
      });
    });

    it('total equals sum of problems + solutions + records', async () => {
      configFsForImport({ problemCount: 7, recordCount: 11, solutionCount: 13 });

      const result = await importData('test-platform');

      expect(result.total).toBe(result.problems + result.solutions + result.records);
    });

    it('handles JSON parse errors gracefully without crashing', async () => {
      configFsForImport({ problemCount: 1, recordCount: 0, solutionCount: 0 });
      mockedFs.readFileSync.mockImplementation(() => {
        return 'not valid json {';
      });

      const result = await importData('test-platform');

      // Should not throw; the broken file is skipped and counts are zero
      expect(result.problems).toBe(0);
      expect(result.solutions).toBe(0);
      expect(result.records).toBe(0);
      expect(result.total).toBe(0);
    });

    it('handles empty subdirectories (no files)', async () => {
      configFsForImport({ problemCount: 0, recordCount: 0, solutionCount: 0 });

      const result = await importData('test-platform');

      expect(result).toEqual({
        problems: 0,
        solutions: 0,
        records: 0,
        total: 0,
      });
    });

    it('handles multiple files in a single subdirectory', async () => {
      configFsForImport({ problemCount: 5, recordCount: 0, solutionCount: 0 });

      const result = await importData('test-platform');

      expect(result.problems).toBe(5);
      expect(result.total).toBe(5);
    });

    it('each count is a number', async () => {
      configFsForImport({ problemCount: 2, recordCount: 1, solutionCount: 3 });

      const result = await importData('test-platform');

      expect(typeof result.problems).toBe('number');
      expect(typeof result.solutions).toBe('number');
      expect(typeof result.records).toBe('number');
      expect(typeof result.total).toBe('number');
    });
  });

  // =========================================================================
  // triggerProblemCrawl — import breakdown in response
  // =========================================================================
  describe('triggerProblemCrawl', () => {
    const dto = {
      platform: 'luogu',
      action: 'fetch_problems',
      count: 10,
    };

    it('response includes import breakdown when import succeeds', async () => {
      configFsForTriggerCrawl();
      mockPythonService.execute.mockResolvedValue({
        success: true,
        data: [{ name: 'Problem 1', pid: 'P001' }],
      });

      const result = await triggerCtrl.triggerProblemCrawl(dto as any);

      expect(result.success).toBe(true);
      // Backward-compatible: imported is a number (total)
      expect(typeof result.imported).toBe('number');
      expect(result.imported).toBe(1);
      // Breakdown is in a separate field
      expect(result.importedDetail).toBeDefined();
      expect(result.importedDetail).toHaveProperty('problems');
      expect(result.importedDetail).toHaveProperty('solutions');
      expect(result.importedDetail).toHaveProperty('records');
      expect(result.importedDetail).toHaveProperty('total');
      expect(result.importedDetail!.problems).toBe(1);
      expect(result.importedDetail!.total).toBe(1);
    });

    it('response includes zeroed breakdown when import fails', async () => {
      mockPythonService.execute.mockResolvedValue({
        success: true,
        data: [{ name: 'Problem 1', pid: 'P001' }],
      });
      // Simulate import failure: fs.existsSync throws
      mockedFs.existsSync.mockImplementation(() => {
        throw new Error('Read error');
      });

      const result = await triggerCtrl.triggerProblemCrawl(dto as any);

      expect(result.success).toBe(true);
      // Backward-compatible: imported is 0
      expect(result.imported).toBe(0);
      expect(result.importedDetail).toEqual({
        problems: 0,
        solutions: 0,
        records: 0,
        total: 0,
      });
    });

    it('response has no imported when platform is unknown', async () => {
      const result = await triggerCtrl.triggerProblemCrawl({
        platform: 'unknown-platform',
        action: 'fetch_problems',
      } as any);

      expect(result.success).toBe(false);
      expect((result as any).imported).toBeUndefined();
    });

    it('creates crawlJob with correct imported count when embedding is triggered', async () => {
      const originalKey = process.env.DEEPSEEK_API_KEY;
      process.env.DEEPSEEK_API_KEY = 'sk-test-key';

      try {
        configFsForTriggerCrawl();
        mockPythonService.execute.mockResolvedValue({
          success: true,
          data: [{ name: 'P1', pid: 'P001' }],
        });

        const result = await triggerCtrl.triggerProblemCrawl(dto as any);

        // Backward-compatible: imported is a number
        expect(result.imported).toBe(1);
        expect(result.importedDetail!.problems).toBe(1);

        // Verify crawlJob.create was called with the imported total count
        expect(mockPrisma.crawlJob.create).toHaveBeenCalled();
        const createCall = mockPrisma.crawlJob.create.mock.calls[0][0];
        // config.imported stores the total count (a single number)
        expect(createCall.data.config.imported).toBe(1);
        expect(createCall.data.config.sourceAction).toBe('fetch_problems');
      } finally {
        process.env.DEEPSEEK_API_KEY = originalKey;
      }
    });

    it('does not create crawlJob when imported total is zero', async () => {
      const originalKey = process.env.DEEPSEEK_API_KEY;
      process.env.DEEPSEEK_API_KEY = 'sk-test-key';

      try {
        // Setup fs so no data directories exist → import returns all zeros
        resetFsSpies();
        mockPythonService.execute.mockResolvedValue({
          success: true,
          data: [{ name: 'P1', pid: 'P001' }],
        });

        await triggerCtrl.triggerProblemCrawl(dto as any);

        // crawlJob.create should NOT have been called because imported.total is 0
        expect(mockPrisma.crawlJob.create).not.toHaveBeenCalled();
      } finally {
        process.env.DEEPSEEK_API_KEY = originalKey;
      }
    });
  });
});