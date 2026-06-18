import { Test, TestingModule } from '@nestjs/testing';
import { CrawlerController } from '../src/crawler/crawler.controller';
import { PythonService } from '../src/crawler/python.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { VectorService } from '../src/common/vector/vector.service';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------
const mockPythonService = {
  execute: jest.fn(),
  spawn: jest.fn(),
  cancelJob: jest.fn(),
} as any;

const mockPrisma = {
  problem: {
    findMany: jest.fn().mockResolvedValue([]),
    findUnique: jest.fn().mockResolvedValue(null),
    upsert: jest.fn(),
    update: jest.fn(),
    updateMany: jest.fn(),
    count: jest.fn().mockResolvedValue(0),
  },
  practiceRecord: { upsert: jest.fn() },
  problemSolution: { upsert: jest.fn() },
  crawlJob: {
    create: jest.fn().mockResolvedValue({ id: 'job-1' }),
    findUnique: jest.fn().mockResolvedValue(null),
    findFirst: jest.fn().mockResolvedValue(null),
    update: jest.fn(),
    findMany: jest.fn().mockResolvedValue([]),
  },
} as any;

const mockVectorService = {
  embedText: jest.fn().mockResolvedValue(new Array(768).fill(0.1)),
  setProblemVectors: jest.fn(),
  setSolutionVector: jest.fn(),
} as any;

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------
describe('CrawlerController.buildFullContent — samples handling', () => {
  let controller: CrawlerController;

  beforeAll(async () => {
    const moduleRef: TestingModule = await Test.createTestingModule({
      controllers: [CrawlerController],
      providers: [
        { provide: PythonService, useValue: mockPythonService },
        { provide: PrismaService, useValue: mockPrisma },
        { provide: VectorService, useValue: mockVectorService },
      ],
    }).compile();
    controller = moduleRef.get<CrawlerController>(CrawlerController);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // Helper to access private method
  const build = (platform: string, record: any) =>
    (controller as any).buildFullContent(platform, record);

  // ====================================================================
  // Dict-type samples (the audit issue)
  // ====================================================================
  it('should convert dict samples to array via Object.values', () => {
    const record = {
      title: 'Test',
      description: 'Sum two numbers',
      samples: {
        '0': ['1 2', '3'],
        '1': ['5 6', '11'],
      },
    };
    const result = build('luogu', record);
    expect(result).toContain('[样例]');
    expect(result).toContain('输入 #1');
    expect(result).toContain('1 2');
    expect(result).toContain('输出 #1');
    expect(result).toContain('3');
    expect(result).toContain('输入 #2');
    expect(result).toContain('5 6');
    expect(result).toContain('输出 #2');
    expect(result).toContain('11');
  });

  it('should handle dict with single sample', () => {
    const record = {
      title: 'Test',
      description: 'Simple',
      samples: { '0': ['hello', 'world'] },
    };
    const result = build('luogu', record);
    expect(result).toContain('[样例]');
    expect(result).toContain('输入 #1');
    expect(result).toContain('hello');
    expect(result).toContain('输出 #1');
    expect(result).toContain('world');
  });

  // ====================================================================
  // Array samples (existing behavior, must still work)
  // ====================================================================
  it('should render array-of-arrays samples correctly', () => {
    const record = {
      title: 'Test',
      description: 'Add',
      samples: [
        ['1 2', '3'],
        ['4 5', '9'],
      ],
    };
    const result = build('luogu', record);
    expect(result).toContain('[样例]');
    expect(result).toContain('输入 #1');
    expect(result).toContain('1 2');
    expect(result).toContain('输出 #1');
    expect(result).toContain('3');
    expect(result).toContain('输入 #2');
    expect(result).toContain('4 5');
    expect(result).toContain('输出 #2');
    expect(result).toContain('9');
  });

  it('should handle empty array samples gracefully', () => {
    const record = {
      title: 'Test',
      description: 'No samples',
      samples: [],
    };
    const result = build('luogu', record);
    expect(result).not.toContain('[样例]');
  });

  it('should handle array element that is not an array (String() fallback)', () => {
    const record = {
      title: 'Test',
      description: 'Weird samples',
      samples: ['just a string'],
    };
    const result = build('luogu', record);
    expect(result).toContain('[样例]');
    expect(result).toContain('just a string');
  });

  // ====================================================================
  // String samples (NowCoder)
  // ====================================================================
  it('should parse string samples into structured code blocks via parseSampleString', () => {
    const record = {
      title: 'Test',
      description: 'String sample',
      samples: '输入：1 2\n输出：3',
    };
    const result = build('luogu', record);
    expect(result).toContain('[样例]');
    expect(result).toContain('输入 #1');
    expect(result).toContain('1 2');
    expect(result).toContain('输出 #1');
    expect(result).toContain('3');
  });

  it('should handle empty string samples (no section added)', () => {
    const record = {
      title: 'Test',
      description: 'Empty',
      samples: '   ',
    };
    const result = build('luogu', record);
    expect(result).not.toContain('[样例]');
  });

  // ====================================================================
  // Null / undefined / missing samples
  // ====================================================================
  it('should not add [样例] when samples is null', () => {
    const record = { title: 'Test', description: 'Desc', samples: null };
    const result = build('luogu', record);
    expect(result).not.toContain('[样例]');
  });

  it('should not add [样例] when samples is undefined', () => {
    const record = { title: 'Test', description: 'Desc' };
    const result = build('luogu', record);
    expect(result).not.toContain('[样例]');
  });

  it('should not add [样例] when samples is 0 (falsy but not dict/array/string)', () => {
    const record = { title: 'Test', description: 'Desc', samples: 0 };
    const result = build('luogu', record);
    expect(result).not.toContain('[样例]');
  });

  // ====================================================================
  // Full integration: dict samples with other sections
  // ====================================================================
  it('should place samples between output_format and hints', () => {
    const record = {
      title: 'Full Problem',
      background: 'Some background',
      description: 'Problem description',
      input_format: 'Two integers',
      output_format: 'Their sum',
      samples: { '0': ['1 2', '3'] },
      hint: 'Watch for overflow',
    };
    const result = build('luogu', record);
    // Extract section headers in order (e.g. "[背景]", "[描述]", ...)
    const sectionHeaders = [...result.matchAll(/\[([^\]\n]+)\]/g)].map((m) => m[1]);
    expect(sectionHeaders).toContain('背景');
    expect(sectionHeaders).toContain('描述');
    expect(sectionHeaders).toContain('输入');
    expect(sectionHeaders).toContain('输出');
    expect(sectionHeaders).toContain('样例');
    expect(sectionHeaders).toContain('提示');
    // Ensure samples come after output and before hint
    const outputIdx = sectionHeaders.indexOf('输出');
    const sampleIdx = sectionHeaders.indexOf('样例');
    const hintIdx = sectionHeaders.indexOf('提示');
    expect(outputIdx).toBeLessThan(sampleIdx);
    expect(sampleIdx).toBeLessThan(hintIdx);
  });

  // ====================================================================
  // hint + note coexistence (hint-note-align fix)
  // ====================================================================
  it('should include both [提示] and [注] when hint and note both exist', () => {
    const record = {
      title: 'Problem with both',
      description: 'Main problem description',
      hint: 'A hint for solving the problem',
      note: 'An additional note about constraints',
    };
    const result = build('luogu', record);
    expect(result).toContain('[提示]');
    expect(result).toContain('A hint for solving the problem');
    expect(result).toContain('[注]');
    expect(result).toContain('An additional note about constraints');
    // [提示] should appear before [注]
    const hintIdx = result.indexOf('[提示]');
    const noteIdx = result.indexOf('[注]');
    expect(hintIdx).toBeLessThan(noteIdx);
  });
});
