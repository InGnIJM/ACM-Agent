import { Test, TestingModule } from '@nestjs/testing';
import * as fs from 'fs';
import * as path from 'path';
import { CrawlerController } from '../src/crawler/crawler.controller';
import { parseLeetCodeSamples } from '../src/crawler/fullcontent.util';
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
  embedText: jest.fn().mockResolvedValue(new Array(1024).fill(0.1)),
  setProblemVector: jest.fn(),
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

  // Helpers: buildFullContent stays on the controller instance; the sample
  // parser was extracted to the shared pure util (fullcontent.util.ts) and
  // is now imported directly.
  const parse = (html: string) => parseLeetCodeSamples(html);
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
  // Fix ④ — [描述] must not leak example/hint headers (new format without class="example")
  // ====================================================================
  describe('[描述] must not leak example/hint headers', () => {
    it('strips plain <strong>示例 N：</strong> (new format, full-width colon)', () => {
      const html = '<p><strong>示例 1：</strong></p><pre><strong>输入：</strong>a=1\n<strong>输出：</strong>2</pre>';
      const out = build({ content: html });
      expect(out).not.toMatch(/示例\s*1/);
      expect(out).toContain('[样例]');
      expect(out).toContain('a=1');
    });

    it('strips <strong>示例 N:</strong> with ASCII colon', () => {
      const html = '<p><strong>示例 2:</strong></p><pre><strong>输入：</strong>b=3\n<strong>输出：</strong>4</pre>';
      const out = build({ content: html });
      expect(out).not.toMatch(/示例\s*2/);
      expect(out).toContain('[样例]');
    });

    it('strips <strong>示例&nbsp;N：</strong> with &nbsp; entity', () => {
      const html = '<p><strong>示例&nbsp;3：</strong></p><pre><strong>输入：</strong>c=5\n<strong>输出：</strong>6</pre>';
      const out = build({ content: html });
      expect(out).not.toMatch(/示例\s*3/);
      expect(out).toContain('[样例]');
    });

    it('strips <strong>Example N:</strong> (English)', () => {
      const html = '<p><strong>Example 1:</strong></p><pre><strong>Input:</strong>d=7\n<strong>Output:</strong>8</pre>';
      const out = build({ content: html });
      expect(out).not.toMatch(/Example\s*1/);
      expect(out).toContain('[样例]');
    });

    it('strips <strong>提示：</strong> (full-width colon)', () => {
      const html = '<p><strong>提示：</strong></p><ul><li>1 &lt;= n &lt;= 100</li></ul>';
      const out = build({ content: html });
      // "提示：" label must be stripped; [提示] section header is fine
      expect(out).not.toMatch(/提示[：:]/);
      expect(out).toContain('1 <= n <= 100');
    });

    it('strips <strong>提示:</strong> (ASCII colon)', () => {
      const html = '<p><strong>提示:</strong></p><ul><li>n is positive</li></ul>';
      const out = build({ content: html });
      expect(out).not.toMatch(/提示[：:]/);
      expect(out).toContain('n is positive');
    });

    it('keeps <strong>进阶：</strong> (follow-up section, not example/hint)', () => {
      const html = '<p><strong>进阶：</strong>你可以想出一个时间复杂度小于 O(n) 的算法吗？</p>';
      const out = build({ content: html });
      expect(out).toContain('进阶');
      expect(out).toContain('时间复杂度');
    });

    it('old format <strong class="example"> still works', () => {
      const html = '<p><strong class="example">示例 1：</strong></p><pre><strong>输入：</strong>x=1\n<strong>输出：</strong>2</pre>';
      const out = build({ content: html });
      expect(out).not.toMatch(/示例\s*1/);
      expect(out).toContain('[样例]');
    });
  });
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

  // ====================================================================
  // Fix ⑤ — Extract hints from HTML when GraphQL hints array is empty
  // ====================================================================
  describe('hints extraction from HTML content', () => {
    it('extracts hints from <ul> after <strong>提示：</strong> into [提示]', () => {
      const html = '<p>描述文本</p><p><strong>提示：</strong></p><ul><li><code>-2<sup>31</sup> &lt;= x &lt;= 2<sup>31</sup> - 1</code></li></ul>';
      const out = build({ content: html, hints: [] });
      expect(out).toContain('[提示]');
      expect(out).toContain('$-2^{31}$');
      expect(out).not.toContain('提示：');
      // Description should contain the description text but NOT the hints
      expect(out).toContain('描述文本');
    });

    it('does NOT extract hints when record.hints is already populated', () => {
      const html = '<p>描述</p><p><strong>提示：</strong></p><ul><li>hint from html</li></ul>';
      const out = build({ content: html, hints: ['hint from graphql'] });
      expect(out).toContain('[提示]');
      expect(out).toContain('hint from graphql');
      expect(out).not.toContain('hint from html');
      // Description should NOT contain the HTML hints content
      expect(out).not.toMatch(/hint from html/);
    });

    it('handles reverse-integer: hints in HTML, GraphQL hints empty', () => {
      // Simulated reverse-integer HTML (hints in <ul>, GraphQL hints=[])
      // CRITICAL: LeetCode GraphQL returns literal <= (not &lt;=) inside <code> tags
      const html = '<p>给你一个 32 位的有符号整数 x</p><p><strong>示例 1：</strong></p><pre><strong>输入：</strong>x = 123\n<strong>输出：</strong>321</pre><p><strong>提示：</strong></p><ul><li><code>-2<sup>31</sup> <= x <= 2<sup>31</sup> - 1</code></li></ul>';
      const out = build({ content: html, hints: [] });
      // Must have [提示] section
      expect(out).toContain('[提示]');
      // Full hints content must be preserved (not truncated by greedy tag regex)
      expect(out).toContain('$-2^{31}$');
      expect(out).toContain('$2^{31}$');
      expect(out).toContain('<= x <=');
      expect(out).toContain('- 1');
      // Must NOT leak hints into description
      const descSection = out.split('[样例]')[0];
      expect(descSection).not.toContain('提示：');
      expect(descSection).not.toMatch(/-2\s*31/);
      // Must have [样例] section
      expect(out).toContain('[样例]');
      expect(out).toContain('x = 123');
    });

    it('strips hints <ul> from description even when record.hints is present', () => {
      // When record.hints is present, use it for [提示] but STILL strip hints from HTML
      const html = '<p>描述</p><p><strong>提示：</strong></p><ul><li>html hint</li></ul>';
      const out = build({ content: html, hints: ['graphql hint 1'] });
      // [提示] should come from graphql hints
      expect(out).toContain('graphql hint 1');
      // Description should NOT contain the HTML hints
      expect(out).not.toContain('html hint');
      expect(out).not.toContain('提示：');
    });

    it('handles English Hint: label', () => {
      const html = '<p>Description</p><p><strong>Hint:</strong></p><ul><li>n is positive</li></ul>';
      const out = build({ content: html, hints: [] });
      expect(out).toContain('[提示]');
      expect(out).toContain('n is positive');
      expect(out).not.toContain('Hint:');
    });

    it('no hints section in HTML → no extra [提示]', () => {
      const html = '<p>Just a description</p>';
      const out = build({ content: html, hints: [] });
      expect(out).not.toContain('[提示]');
      expect(out).toContain('Just a description');
    });
  });
});
