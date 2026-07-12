import { Test, TestingModule } from '@nestjs/testing';
import { CrawlerController } from '../src/crawler/crawler.controller';
import { cleanMathJaxTriplication } from '../src/crawler/fullcontent.util';
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
  embedText: jest.fn().mockResolvedValue(new Array(1024).fill(0.1)),
  setProblemVector: jest.fn(),
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

// ===========================================================================
// AtCoder data-loss regression (TDD — Red phase)
//
// buildFullContent() applied cleanMathJaxTriplication() to every platform,
// but AtCoder/Luogu data is already clean $...$ KaTeX, so short constraint
// lines ("$1 \leq H \leq 20$", "|", "or", "-", ".") were misclassified as a
// 3-copy math island and DELETED. These tests lock in the fix.
// ===========================================================================
describe('CrawlerController.buildFullContent — AtCoder data-loss regression', () => {
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

  const build = (platform: string, record: any) =>
    (controller as any).buildFullContent(platform, record);
  const cleanMath = (t: string) => cleanMathJaxTriplication(t);

  // (a) AtCoder constraints must NOT be truncated.
  it('preserves all AtCoder constraint lines (no cleanMathJax on atcoder)', () => {
    const constraints =
      '$1 \\leq H \\leq 20$\n' +
      '$1 \\leq W \\leq 20$\n' +
      '$\\textrm{move}$ is either\n' +
      'First\n' +
      'or\n' +
      'Second\n' +
      ', where\n' +
      'First means...\n' +
      'Second means...';
    const result = build('atcoder', {
      title: '1202Contest_b',
      description: 'Move on grid',
      constraints,
      input_format: 'H W',
      output_format: 'First or Second',
    });
    expect(result).toContain('$1 \\leq H \\leq 20$');
    expect(result).toContain('$1 \\leq W \\leq 20$');
    expect(result).toContain('First');
    expect(result).toContain('Second');
    expect(result).toContain('move');
    // The whole constraints block must be present (no truncation)
    expect(result).toContain('[数据范围]');
    expect(result).toContain('First means...');
    expect(result).toContain('Second means...');
  });

  // (b) cleanMathJaxTriplication must preserve fenced code blocks verbatim.
  it('cleanMathJaxTriplication preserves fenced code block contents verbatim', () => {
    const input =
      'Some intro line.\n' +
      '```\n' +
      '3\n' +
      '1 2\n' +
      '5 4\n' +
      '7 8\n' +
      '```\n' +
      'Trailing text.';
    const out = cleanMath(input);
    expect(out).toContain('```');
    expect(out).toContain('1 2');
    expect(out).toContain('5 4');
    expect(out).toContain('7 8');
    // Fence lines must survive (not collapsed into a math island)
    const fenceCount = (out.match(/```/g) || []).length;
    expect(fenceCount).toBe(2);
  });

  // (c) cleanMathJaxTriplication must NOT mangle adjacent inline math.
  it('cleanMathJaxTriplication does not mangle "$H$ $W$ $\\textrm{move}$"', () => {
    const input = '$H$ $W$ $\\textrm{move}$';
    const out = cleanMath(input);
    expect(out).toContain('$H$');
    expect(out).toContain('$W$');
    expect(out).toContain('$\\textrm{move}$');
  });

  // (d) camelCase alias support (atcoder 1202Contest_j schema)
  it('reads camelCase aliases (inputFormat/outputFormat/timeLimit/memoryLimit)', () => {
    const result = build('atcoder', {
      title: '1202Contest_j',
      description: 'CamelCase problem',
      inputFormat: 'N K',
      outputFormat: 'answer',
      limits: { timeLimit: 2000, memoryLimit: 1024 },
    });
    expect(result).toContain('[输入]');
    expect(result).toContain('N K');
    expect(result).toContain('[输出]');
    expect(result).toContain('answer');
    expect(result).toContain('2000ms');
    expect(result).toContain('1024MB');
  });

  // (e) Regression: codeforces-style triplication still collapses to p_i.
  it('regression: collapses codeforces triplication "p\\ni\\n\\np\\ni\\n\\np_i"', () => {
    const input = 'p\ni\n\np\ni\n\np_i';
    const out = cleanMath(input);
    expect(out).toContain('p_i');
  });

  // ── Extra coverage for camelCase limits + section wiring ─────────────
  it('uses top-level timeLimit/memoryLimit when no limits object exists', () => {
    const result = build('atcoder', {
      title: 'flatLimits',
      description: 'D',
      timeLimit: 1000,
      memoryLimit: 256,
    });
    expect(result).toContain('1000ms');
    expect(result).toContain('256MB');
  });

  it('emits background / constraints / input / output sections for atcoder', () => {
    const result = build('atcoder', {
      title: 'sections',
      background: 'bg',
      description: 'desc',
      constraints: 'C',
      input_format: 'IN',
      output_format: 'OUT',
    });
    expect(result).toContain('[背景]');
    expect(result).toContain('bg');
    expect(result).toContain('[数据范围]');
    expect(result).toContain('[输入]');
    expect(result).toContain('IN');
    expect(result).toContain('[输出]');
    expect(result).toContain('OUT');
  });

  // ── Coverage for explanation-block, hints array, fallback paths ──────
  it('renders 解释 block when array sample has a 3rd element', () => {
    const result = build('codeforces', {
      description: 'D',
      samples: [['1 2', '3', 'because 1+2=3']],
    });
    expect(result).toContain('解释 #1');
    expect(result).toContain('because 1+2=3');
  });

  it('parses 示例N markers in NowCoder string samples', () => {
    const result = build('nowcoder', {
      description: 'D',
      samples: '示例1：输入：1 2\n输出：3',
    });
    expect(result).toContain('1 2');
    expect(result).toContain('3');
  });

  it('falls back to raw samples string when parseSampleString yields nothing', () => {
    const result = build('nowcoder', {
      description: 'D',
      samples: 'no recognizable markers here',
    });
    expect(result).toContain('[样例]');
    expect(result).toContain('no recognizable markers here');
  });

  it('renders hints array as numbered list', () => {
    const result = build('luogu', {
      description: 'D',
      hints: ['first tip', 'second tip'],
    });
    expect(result).toContain('[提示]');
    expect(result).toContain('1. first tip');
    expect(result).toContain('2. second tip');
  });

  it('wraps HTML content (no description) in [描述] section', () => {
    const result = build('luogu', {
      content: '<p>Hello <b>world</b></p>',
    });
    expect(result).toContain('[描述]');
    expect(result).toContain('Hello');
    expect(result).toContain('world');
  });

  // ── Coverage for cleanMathJaxTriplication post-pass (LaTeX wrap) ─────
  it('cleanMathJaxTriplication wraps bare LaTeX lines in $...$ when no $ present', () => {
    // Text with LaTeX command but no existing $ → post-pass wraps it
    const out = cleanMath('value is \\leq 10 here');
    expect(out).toContain('$');
    expect(out).toContain('\\leq');
  });

  it('overrides pre-existing [样例] when leetcode HTML parse succeeds', () => {
    // Provide both record.samples AND parseable HTML so the override loop runs
    const result = build('leetcode', {
      content: '<pre><strong>输入：</strong>1 2\n<strong>输出：</strong>3</pre>',
      samples: [['stale', 'stale']],
    });
    // The HTML-parsed sample should win; stale Python sample overridden
    expect(result).toContain('1 2');
    expect(result).toContain('### 输入 #1');
  });

  it('leetcode falls back to sampleTestCase when HTML not parseable and no samples', () => {
    const result = build('leetcode', {
      content: 'plain text, no html tags',
      sampleTestCase: '5\n1 2 3',
    });
    expect(result).toContain('[样例]');
    expect(result).toContain('1 2 3');
  });

  // ── Coverage for island dedup latex-line path + leetcode div format ──
  it('cleanMathJaxTriplication keeps longest LaTeX line in a 3+ island', () => {
    // 3 math fragments, the LaTeX-source variant is the longest
    const out = cleanMath('f\n(\\n)\n\na\nb\n\n1 \\\\leq x \\\\leq 10');
    // The LaTeX-rich line should survive
    expect(out).toContain('1 \\\\leq x \\\\leq 10');
  });

  it('parses leetcode new-format <div class="example-block"> samples', () => {
    const html =
      '<div class="example-block">' +
      '<p><strong>输入：</strong><span class="example-io">2 7</span></p>' +
      '<p><strong>输出：</strong><span class="example-io">9</span></p>' +
      '</div>';
    const result = build('leetcode', { content: html });
    expect(result).toContain('2 7');
    expect(result).toContain('9');
  });

  // =========================================================================
  // Adversarial regression check — lock in BOTH the original PURPOSE (CF /
  // NowCoder MathJax triplication collapse) AND the new preserves-fence /
  // preserves-inline-math behavior. Any change to cleanMathJaxTriplication
  // that breaks these contracts is a regression.
  // =========================================================================
  describe('cleanMathJaxTriplication — adversarial regression contract', () => {
    // COLLAPSE contract #1: codeforces "p / i" triplication collapses to p_i.
    it('COLLAPSES "p\\ni\\n\\np\\ni\\n\\np_i" into a line containing p_i', () => {
      const input = 'p\ni\n\np\ni\n\np_i';
      const out = cleanMath(input);
      expect(out).toContain('p_i');
      // The triplicated single-char fragments must NOT survive as separate lines.
      const lines = out.split('\n').map(l => l.trim()).filter(l => l.length > 0);
      const standalonePIslands = lines.filter(l => l === 'p' || l === 'i');
      expect(standalonePIslands.length).toBe(0);
    });

    // COLLAPSE contract #2: CF symbol-by-line island collapses to the LaTeX line.
    it('COLLAPSES "1\\n\\n≤\\n\\nx\\n\\n1 \\le x\\n\\n." into a single line with \\le', () => {
      const input = '1\n\n≤\n\nx\n\n1 \\le x\n\n.';
      const out = cleanMath(input);
      expect(out).toContain('\\le');
      // Exactly ONE surviving line carries the LaTeX command (no duplication).
      const leLines = out.split('\n').filter(l => l.includes('\\le'));
      expect(leLines.length).toBe(1);
      // The bare symbol fragments must not survive as their own lines.
      const lines = out.split('\n').map(l => l.trim()).filter(l => l.length > 0);
      expect(lines).not.toContain('≤');
      expect(lines).not.toContain('.');
    });

    // PRESERVE contract #1: a fenced code block's contents stay verbatim.
    it('PRESERVES fenced code block with A_i / B_i / C_i intact (3 content lines)', () => {
      const input =
        'Intro.\n' +
        '```\n' +
        'A_i\n' +
        'B_i\n' +
        'C_i\n' +
        '```\n' +
        'Outro.';
      const out = cleanMath(input);
      // All three content lines must survive untouched.
      expect(out).toContain('A_i');
      expect(out).toContain('B_i');
      expect(out).toContain('C_i');
      // Both fence markers must survive (island must not swallow the fences).
      const fenceCount = (out.match(/```/g) || []).length;
      expect(fenceCount).toBe(2);
      // The three lines must NOT be collapsed into a single math island line.
      const collapsedCandidate = out.split('\n').filter(l =>
        l.includes('A_i') && l.includes('B_i') && l.includes('C_i'),
      );
      expect(collapsedCandidate.length).toBe(0);
    });

    // PRESERVE contract #2: adjacent inline math on one line is unchanged.
    it('PRESERVES "$H$ $W$ $\\textrm{move}$" unchanged (middle "$ $" NOT stripped)', () => {
      const input = '$H$ $W$ $\\textrm{move}$';
      const out = cleanMath(input);
      // All three inline math spans must be present.
      expect(out).toContain('$H$');
      expect(out).toContain('$W$');
      expect(out).toContain('$\\textrm{move}$');
      // The middle "$ $" gap must NOT have been collapsed to "$$".
      expect(out).not.toContain('$$');
      // Overall structure preserved on a single line.
      expect(out.trim()).toBe('$H$ $W$ $\\textrm{move}$');
    });
  });
});

// ===========================================================================
// callDeepSeekSummarize — timeout + retry (fetch failed / RPM guard)
// ===========================================================================
describe('CrawlerController.callDeepSeekSummarize — retry & timeout', () => {
  let controller: CrawlerController;
  const originalFetch = global.fetch;
  const originalEnv = { ...process.env };

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
    // Ensure API key is set so resolveDeepSeekConfig() returns a config
    process.env.DEEPSEEK_API_KEY = 'sk-test-key';
    process.env.DEEPSEEK_PROVIDER = 'deepseek';
    process.env.DEEPSEEK_BASE_URL = 'https://api.test.com/v1';
    process.env.DEEPSEEK_MAX_RETRIES = '2'; // keep tests fast
    process.env.DEEPSEEK_TIMEOUT_MS = '100';
    delete process.env.DEEPSEEK_CALL_DELAY_MS;
    delete process.env.DEEPSEEK_RPM;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  const callSummarize = (title = 'Test', content = 'content', diff = 'easy') =>
    (controller as any).callDeepSeekSummarize(title, content, diff);

  // ------------------------------------------------------------------
  // Happy path
  // ------------------------------------------------------------------
  it('returns summary on first attempt', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ choices: [{ message: { content: '好的总结' } }] }),
    } as any);

    const result = await callSummarize();
    expect(result).toBe('好的总结');
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('returns null when no API key configured', async () => {
    delete process.env.DEEPSEEK_API_KEY;
    global.fetch = jest.fn();

    const result = await callSummarize();
    expect(result).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  // ------------------------------------------------------------------
  // Network-error retry
  // ------------------------------------------------------------------
  it('retries on fetch failed (network error) and succeeds', async () => {
    global.fetch = jest.fn()
      .mockRejectedValueOnce(new TypeError('fetch failed'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'retry success' } }] }),
      } as any);

    const result = await callSummarize();
    expect(result).toBe('retry success');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('retries on ECONNRESET and succeeds', async () => {
    global.fetch = jest.fn()
      .mockRejectedValueOnce(new TypeError('ECONNRESET'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'ok' } }] }),
      } as any);

    const result = await callSummarize();
    expect(result).toBe('ok');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('retries on ECONNREFUSED and succeeds', async () => {
    global.fetch = jest.fn()
      .mockRejectedValueOnce(new TypeError('ECONNREFUSED'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'ok' } }] }),
      } as any);

    const result = await callSummarize();
    expect(result).toBe('ok');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('retries on ENOTFOUND (DNS failure) and succeeds', async () => {
    global.fetch = jest.fn()
      .mockRejectedValueOnce(new TypeError('ENOTFOUND'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'ok' } }] }),
      } as any);

    const result = await callSummarize();
    expect(result).toBe('ok');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  // ------------------------------------------------------------------
  // Timeout (AbortError) retry
  // ------------------------------------------------------------------
  it('retries on AbortError (timeout) and succeeds', async () => {
    const abortErr = new DOMException('The operation was aborted', 'AbortError');
    global.fetch = jest.fn()
      .mockRejectedValueOnce(abortErr)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'after timeout' } }] }),
      } as any);

    const result = await callSummarize();
    expect(result).toBe('after timeout');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  // ------------------------------------------------------------------
  // HTTP-error retry
  // ------------------------------------------------------------------
  it('retries on 429 rate limit and succeeds', async () => {
    const rateLimitResp = {
      ok: false,
      status: 429,
      headers: { get: () => null } as any,
      text: async () => 'rate limited',
    };
    global.fetch = jest.fn()
      .mockResolvedValueOnce(rateLimitResp as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'after 429' } }] }),
      } as any);

    const result = await callSummarize();
    expect(result).toBe('after 429');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('honors Retry-After header on 429', async () => {
    const rateLimitResp = {
      ok: false,
      status: 429,
      headers: { get: (_: string) => '1' } as any, // 1 second
      text: async () => 'rate limited',
    };
    global.fetch = jest.fn()
      .mockResolvedValueOnce(rateLimitResp as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'ok' } }] }),
      } as any);

    // Spy on setTimeout to verify Retry-After delay is used
    const setTimeoutSpy = jest.spyOn(global, 'setTimeout');
    const result = await callSummarize();
    expect(result).toBe('ok');
    // Verify setTimeout was called with ~1000ms (Retry-After value)
    const delayCall = setTimeoutSpy.mock.calls.find(
      ([, ms]: any) => typeof ms === 'number' && ms >= 900 && ms <= 1100,
    );
    expect(delayCall).toBeTruthy();
    setTimeoutSpy.mockRestore();
  });

  it('retries on 500 server error and succeeds', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: false, status: 500, text: async () => 'internal error',
      } as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'after 500' } }] }),
      } as any);

    const result = await callSummarize();
    expect(result).toBe('after 500');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('retries on 503 server error and succeeds', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: false, status: 503, text: async () => 'unavailable',
      } as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ choices: [{ message: { content: 'ok' } }] }),
      } as any);

    const result = await callSummarize();
    expect(result).toBe('ok');
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  // ------------------------------------------------------------------
  // Non-retryable errors (no retry)
  // ------------------------------------------------------------------
  it('does NOT retry on 400 bad request', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false, status: 400, text: async () => 'bad request',
    } as any);

    await expect(callSummarize()).rejects.toThrow('DeepSeek API error 400');
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('does NOT retry on 401 unauthorized', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false, status: 401, text: async () => 'unauthorized',
    } as any);

    await expect(callSummarize()).rejects.toThrow('DeepSeek API error 401');
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  // ------------------------------------------------------------------
  // Exhausted retries
  // ------------------------------------------------------------------
  it('throws after exhausting all retries on network error', async () => {
    global.fetch = jest.fn()
      .mockRejectedValueOnce(new TypeError('fetch failed'))
      .mockRejectedValueOnce(new TypeError('fetch failed'))
      .mockRejectedValueOnce(new TypeError('fetch failed')); // 3 attempts = maxRetries(2) + 1

    await expect(callSummarize()).rejects.toThrow(
      'DeepSeek summarize failed after 3 attempts: fetch failed',
    );
    expect(global.fetch).toHaveBeenCalledTimes(3);
  }, 20000);

  it('throws after exhausting all retries on 429', async () => {
    const rateLimitResp = {
      ok: false,
      status: 429,
      headers: { get: () => null } as any,
      text: async () => 'rate limited',
    };
    global.fetch = jest.fn()
      .mockResolvedValueOnce(rateLimitResp as any)
      .mockResolvedValueOnce(rateLimitResp as any)
      .mockResolvedValueOnce(rateLimitResp as any);

    await expect(callSummarize()).rejects.toThrow(
      'DeepSeek API error 429: rate limited',
    );
    expect(global.fetch).toHaveBeenCalledTimes(3);
  }, 20000);

  // ------------------------------------------------------------------
  // AbortController signal is passed to fetch
  // ------------------------------------------------------------------
  it('passes AbortController signal to fetch', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ choices: [{ message: { content: 'ok' } }] }),
    } as any);

    await callSummarize();

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[1].signal).toBeInstanceOf(AbortSignal);
  });

  // ------------------------------------------------------------------
  // thinking disabled (avoid reasoning_token waste)
  // ------------------------------------------------------------------
  it('includes thinking: {type: disabled} in request body', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ choices: [{ message: { content: 'ok' } }] }),
    } as any);

    await callSummarize();

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    const body = JSON.parse(fetchCall[1].body);
    expect(body.thinking).toEqual({ type: 'disabled' });
  });
});

// ===========================================================================
// _getSummarizeCallDelay — rate-limit guard
// ===========================================================================
describe('CrawlerController._getSummarizeCallDelay', () => {
  let controller: CrawlerController;
  const originalEnv = { ...process.env };

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
    delete process.env.DEEPSEEK_CALL_DELAY_MS;
    delete process.env.DEEPSEEK_RPM;
    delete process.env.DEEPSEEK_PROVIDER;
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  const getDelay = () => (controller as any)._getSummarizeCallDelay() as number;

  it('returns explicit DEEPSEEK_CALL_DELAY_MS when set', () => {
    process.env.DEEPSEEK_CALL_DELAY_MS = '5000';
    expect(getDelay()).toBe(5000);
  });

  it('returns 0 when DEEPSEEK_CALL_DELAY_MS is explicitly 0', () => {
    process.env.DEEPSEEK_CALL_DELAY_MS = '0';
    process.env.DEEPSEEK_PROVIDER = 'aliyun'; // would default to 3000, but explicit 0 wins
    expect(getDelay()).toBe(0);
  });

  it('computes delay from DEEPSEEK_RPM (rounds up)', () => {
    process.env.DEEPSEEK_RPM = '10';
    expect(getDelay()).toBe(6000); // 60000 / 10
  });

  it('computes delay from DEEPSEEK_RPM (ceiling division)', () => {
    process.env.DEEPSEEK_RPM = '9';
    expect(getDelay()).toBe(6667); // Math.ceil(60000 / 9)
  });

  it('DEEPSEEK_CALL_DELAY_MS takes priority over DEEPSEEK_RPM', () => {
    process.env.DEEPSEEK_CALL_DELAY_MS = '1000';
    process.env.DEEPSEEK_RPM = '10'; // would give 6000
    expect(getDelay()).toBe(1000);
  });

  it('defaults to 3000ms for aliyun provider', () => {
    process.env.DEEPSEEK_PROVIDER = 'aliyun';
    expect(getDelay()).toBe(3000);
  });

  it('defaults to 0ms for deepseek official', () => {
    process.env.DEEPSEEK_PROVIDER = 'deepseek';
    expect(getDelay()).toBe(0);
  });

  it('defaults to 0ms when provider is unset', () => {
    expect(getDelay()).toBe(0);
  });

  it('ignores invalid DEEPSEEK_RPM (NaN)', () => {
    process.env.DEEPSEEK_RPM = 'not-a-number';
    process.env.DEEPSEEK_PROVIDER = 'deepseek';
    expect(getDelay()).toBe(0); // falls through to default
  });

  it('ignores zero DEEPSEEK_RPM', () => {
    process.env.DEEPSEEK_RPM = '0';
    process.env.DEEPSEEK_PROVIDER = 'deepseek';
    expect(getDelay()).toBe(0);
  });
});
