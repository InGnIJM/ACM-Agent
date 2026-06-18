import { Test, TestingModule } from '@nestjs/testing';
import * as fs from 'fs';
import * as path from 'path';
import { CrawlerController } from '../src/crawler/crawler.controller';
import { PythonService } from '../src/crawler/python.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { VectorService } from '../src/common/vector/vector.service';

// ---------------------------------------------------------------------------
// Mocks (lightweight — these methods are never exercised by the units under
// test, but CrawlerController's DI requires all three providers).
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

const FIXTURE_PATH = path.join(__dirname, 'fixtures', 'leetcode-two-sum-content.html');

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------
describe('CrawlerController — LeetCode rendering (sup/sub LaTeX + sample split)', () => {
  let controller: CrawlerController;
  let twoSumHtml: string;

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
    twoSumHtml = fs.readFileSync(FIXTURE_PATH, 'utf8');
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // Helpers: reach private methods on the instance
  const parse = (html: string) =>
    (controller as any).parseLeetCodeSamples(html);
  const build = (record: any) =>
    (controller as any).buildFullContent('leetcode', record);

  // ====================================================================
  // Fix ① — <sup>/<sub> → inline LaTeX math for KaTeX
  // ====================================================================
  describe('<sup>/<sub> → inline LaTeX math', () => {
    it('converts 10<sup>4</sup> → $10^{4}$ (no bare 10^4)', () => {
      const out = build({ content: '<p>10<sup>4</sup></p>' });
      expect(out).toContain('$10^{4}$');
      expect(out).not.toContain('10^4');
      expect(out).not.toContain('<sup>');
    });

    it('converts -10<sup>9</sup> → $-10^{9}$ (minus captured inside math)', () => {
      const out = build({ content: '<p>-10<sup>9</sup></p>' });
      expect(out).toContain('$-10^{9}$');
      expect(out).not.toContain('<sup>');
    });

    it('converts O(n<sup>2</sup>) → O($n^{2}$) (local wrap acceptable)', () => {
      const out = build({ content: '<p>O(n<sup>2</sup>)</p>' });
      expect(out).toMatch(/\$n\^\{2\}\$/);
      expect(out).toContain('O(');
      expect(out).not.toContain('<sup>');
    });

    it('converts <sub>x</sub> → _{x} inside LaTeX (defensive)', () => {
      const out = build({ content: '<p>a<sub>i</sub></p>' });
      // expect a math span containing a_{i}
      expect(out).toMatch(/\$a_\{i\}\$/);
      expect(out).not.toContain('<sub>');
    });

    it('keeps &lt;= as literal "<=" text (not \\le)', () => {
      const out = build({ content: '<p>3 &lt;= n</p>' });
      expect(out).toContain('3 <= n');
      expect(out).not.toContain('\\le');
    });

    it('two-sum fixture: constraints sup → LaTeX, no leftover <sup>/bare ^', () => {
      const out = build({ content: twoSumHtml });
      expect(out).toContain('$10^{4}$');
      expect(out).toContain('$-10^{9}$');
      expect(out).toMatch(/\$10\^\{9\}\$/); // upper bound 10^9
      expect(out).not.toContain('<sup>');
      expect(out).not.toContain('10^4'); // bare ^4 must be gone
    });
  });

  // ====================================================================
  // Fix ② — parseLeetCodeSamples separates the 3 <pre> examples
  // ====================================================================
  describe('parseLeetCodeSamples — separates 3 <pre> examples', () => {
    it('returns 3 pairs for the two-sum fixture', () => {
      const pairs = parse(twoSumHtml);
      expect(pairs).not.toBeNull();
      expect(pairs!.length).toBe(3);
    });

    it('example 1 carries a non-empty explanation as the 3rd element', () => {
      const pairs = parse(twoSumHtml)!;
      expect(pairs[0][0]).toContain('nums = [2,7,11,15]');
      expect(pairs[0][0]).toContain('target = 9');
      expect(pairs[0][1]).toContain('[0,1]');
      expect(pairs[0][2]).toBeTruthy();
      expect(pairs[0][2]).toContain('nums[0] + nums[1] == 9');
    });

    it('examples 2 & 3 have NO explanation (3rd element empty)', () => {
      const pairs = parse(twoSumHtml)!;
      expect(pairs[1][0]).toContain('nums = [3,2,4]');
      expect(pairs[1][1]).toContain('[1,2]');
      expect(pairs[1][2]).toBeFalsy();
      expect(pairs[2][0]).toContain('nums = [3,3]');
      expect(pairs[2][1]).toContain('[0,1]');
      expect(pairs[2][2]).toBeFalsy();
    });

    it('no input/output leaks the "示例 N：" header', () => {
      const pairs = parse(twoSumHtml)!;
      for (const [input, output] of pairs) {
        expect(input).not.toMatch(/示例\s*\d/);
        expect(output).not.toMatch(/示例\s*\d/);
      }
    });
  });

  // ====================================================================
  // Fix ③ — sample template: ### headers + explanation block
  // ====================================================================
  describe('sample template — ### headers + explanation block', () => {
    it('emits ### 输入/输出 headers for all 3 examples', () => {
      const out = build({ content: twoSumHtml });
      expect(out).toContain('### 输入 #1');
      expect(out).toContain('### 输出 #1');
      expect(out).toContain('### 输入 #2');
      expect(out).toContain('### 输出 #2');
      expect(out).toContain('### 输入 #3');
      expect(out).toContain('### 输出 #3');
    });

    it('emits ### 解释 #1 only (no 解释 #2 / #3)', () => {
      const out = build({ content: twoSumHtml });
      expect(out).toContain('### 解释 #1');
      expect(out).not.toContain('### 解释 #2');
      expect(out).not.toContain('### 解释 #3');
    });
  });
});
