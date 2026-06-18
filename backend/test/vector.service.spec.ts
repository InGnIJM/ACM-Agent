import { Test, TestingModule } from '@nestjs/testing';
import { VectorService } from '../src/common/vector/vector.service';
import { PrismaService } from '../src/common/prisma/prisma.service';

// ---------------------------------------------------------------------------
// Mock PrismaService
// ---------------------------------------------------------------------------
const mock$executeRaw = jest.fn();
const mock$executeRawUnsafe = jest.fn();
const mock$queryRawUnsafe = jest.fn();
const mock$transaction = jest.fn();

const mockPrisma: Partial<PrismaService> = {
  $executeRaw: mock$executeRaw,
  $executeRawUnsafe: mock$executeRawUnsafe,
  $queryRawUnsafe: mock$queryRawUnsafe,
  $transaction: mock$transaction as any,
};

// ---------------------------------------------------------------------------
// Mock global fetch so we don't hit Ollama
// ---------------------------------------------------------------------------
let fetchResponse: { ok: boolean; status: number; json: () => Promise<any>; text: () => Promise<string> };

global.fetch = jest.fn(() => Promise.resolve(fetchResponse)) as any;

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------
describe('VectorService', () => {
  let service: VectorService;
  let moduleRef: TestingModule;

  beforeAll(async () => {
    moduleRef = await Test.createTestingModule({
      providers: [
        VectorService,
        { provide: PrismaService, useValue: mockPrisma },
      ],
    }).compile();
    service = moduleRef.get<VectorService>(VectorService);
  });

  afterAll(async () => {
    await moduleRef.close();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mock$executeRawUnsafe.mockResolvedValue(undefined);
    // $transaction with array: return [SET_result, SELECT_result] directly
    mock$transaction.mockImplementation(async (ops: any[]) => {
      const resolved = await Promise.all(ops);
      return resolved;
    });
  });

  // ====================================================================
  // embedTexts
  // ====================================================================

  describe('embedTexts', () => {
    it('returns one vector per input text (1024-dim)', async () => {
      fetchResponse = {
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            embeddings: [
              Array(1024).fill(0.1),
              Array(1024).fill(0.2),
            ],
          }),
        text: () => Promise.resolve(''),
      };

      const vecs = await service.embedTexts(['hello', 'world']);
      expect(vecs).toHaveLength(2);
      expect(vecs[0]).toHaveLength(1024);
      expect(vecs[1]).toHaveLength(1024);
    });

    it('returns empty for empty input', async () => {
      const vecs = await service.embedTexts([]);
      expect(vecs).toEqual([]);
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('retries on failure', async () => {
      let callCount = 0;
      fetchResponse = {
        ok: true,
        status: 200,
        json: () => {
          callCount++;
          if (callCount < 3) {
            return Promise.reject(new Error('Network error'));
          }
          return Promise.resolve({ embeddings: [Array(1024).fill(0.5)] });
        },
        text: () => Promise.resolve(''),
      };

      const vecs = await service.embedTexts(['test']);
      expect(vecs).toHaveLength(1);
      expect(callCount).toBe(3);
    }, 20000);

    it('throws after 4 total attempts', async () => {
      fetchResponse = {
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error('Server error')),
        text: () => Promise.resolve('Internal Server Error'),
      };

      await expect(service.embedTexts(['test'])).rejects.toThrow(
        'Ollama embedding failed after 4 attempts',
      );
    }, 20000);

    it('throws on unexpected response shape', async () => {
      fetchResponse = {
        ok: true,
        status: 200,
        json: () => Promise.resolve({ wrongKey: [] }),
        text: () => Promise.resolve(''),
      };

      await expect(service.embedTexts(['test'])).rejects.toThrow(
        'Unexpected Ollama response shape',
      );
    }, 20000);  // timeout accounts for retry backoff
  });

  // ====================================================================
  // embedText (convenience)
  // ====================================================================

  describe('embedText', () => {
    it('delegates to embedTexts', async () => {
      const vec = Array(1024).fill(0.3);
      // Spy on embedTexts to avoid calling real fetch
      jest.spyOn(service, 'embedTexts').mockResolvedValueOnce([vec]);

      const result = await service.embedText('hello');
      expect(result).toEqual(vec);
      expect(service.embedTexts).toHaveBeenCalledWith(['hello']);
    });
  });

  // ====================================================================
  // setProblemVectors
  // ====================================================================

  describe('setProblemVectors', () => {
    it('calls $executeRaw with correct SQL', async () => {
      const id = '550e8400-e29b-41d4-a716-446655440000';
      const pVec = [0.1, 0.2, 0.3];
      const cVec = [0.4, 0.5, 0.6];

      mock$executeRaw.mockResolvedValueOnce(undefined);

      await service.setProblemVectors(id, pVec, cVec);

      expect(mock$executeRaw).toHaveBeenCalledTimes(1);
      // tagged template: first arg is string[] chunks
      const allSql = (mock$executeRaw.mock.calls[0][0] as string[]).join('');
      expect(allSql).toContain('UPDATE problems');
      expect(allSql).toContain('vector_embedding');
      expect(allSql).toContain('content_vector');
    });

    it('no-ops on empty vectors', async () => {
      await service.setProblemVectors('id', [], [0.1]);
      await service.setProblemVectors('id', [0.1], []);
      expect(mock$executeRaw).not.toHaveBeenCalled();
    });
  });

  // ====================================================================
  // setSolutionVector
  // ====================================================================

  describe('setSolutionVector', () => {
    it('calls $executeRaw with correct SQL', async () => {
      mock$executeRaw.mockResolvedValueOnce(undefined);
      await service.setSolutionVector('sid', [0.1, 0.2]);
      expect(mock$executeRaw).toHaveBeenCalledTimes(1);
      const allSql = (mock$executeRaw.mock.calls[0][0] as string[]).join('');
      expect(allSql).toContain('UPDATE problem_solutions');
    });

    it('no-ops on empty vector', async () => {
      await service.setSolutionVector('sid', []);
      expect(mock$executeRaw).not.toHaveBeenCalled();
    });
  });

  // ====================================================================
  // searchProblems
  // ====================================================================

  describe('searchProblems', () => {
    const mockRows = [
      {
        id: 'p1',
        title: 'Two Sum',
        sourcePlatform: 'leetcode',
        sourceId: 'two-sum',
        difficultyNormalized: 3,
        tagsNormalized: ['array', 'hash_map'],
        solutionSummary: 'Use hash map.',
        fullContent: 'Find two numbers...',
        similarity: 0.95,
      },
    ];

    it('executes ANN search and maps results', async () => {
      mock$queryRawUnsafe.mockResolvedValueOnce(mockRows);
      const res = await service.searchProblems(Array(1024).fill(0.1));
      expect(res).toHaveLength(1);
      expect(res[0].id).toBe('p1');
      expect(res[0].similarity).toBe(0.95);
      expect(res[0].tagsNormalized).toEqual(['array', 'hash_map']);
    });

    it('includes platform filter when specified', async () => {
      mock$queryRawUnsafe.mockResolvedValueOnce([]);
      await service.searchProblems(Array(1024).fill(0.1), 20, {
        platform: 'luogu',
      });
      const sql: string = mock$queryRawUnsafe.mock.calls[0][0];
      expect(sql).toContain('source_platform');
    });

    it('includes tag filter when specified', async () => {
      mock$queryRawUnsafe.mockResolvedValueOnce([]);
      await service.searchProblems(Array(1024).fill(0.1), 20, {
        tags: ['dp', 'tree'],
      });
      const sql: string = mock$queryRawUnsafe.mock.calls[0][0];
      expect(sql).toContain('tags_normalized');
    });

    it('includes difficulty range when specified', async () => {
      mock$queryRawUnsafe.mockResolvedValueOnce([]);
      await service.searchProblems(Array(1024).fill(0.1), 20, {
        difficultyMin: 3,
        difficultyMax: 7,
      });
      const sql: string = mock$queryRawUnsafe.mock.calls[0][0];
      expect(sql).toContain('difficulty_normalized');
    });
  });

  // ====================================================================
  // getSolutionsForProblems
  // ====================================================================

  describe('getSolutionsForProblems', () => {
    const mockRows = [
      {
        id: 's1',
        problemId: 'p1',
        content: 'Solution text...',
        author: 'coder',
        solutionIndex: 1,
        similarity: 0.88,
      },
    ];

    it('fetches solutions with similarity', async () => {
      mock$queryRawUnsafe.mockResolvedValueOnce(mockRows);
      const res = await service.getSolutionsForProblems(
        ['p1'],
        Array(1024).fill(0.1),
      );
      expect(res).toHaveLength(1);
      expect(res[0].problemId).toBe('p1');
      expect(res[0].similarity).toBe(0.88);
    });

    it('returns empty for empty problemIds', async () => {
      const res = await service.getSolutionsForProblems(
        [],
        Array(1024).fill(0.1),
      );
      expect(res).toEqual([]);
      expect(mock$queryRawUnsafe).not.toHaveBeenCalled();
    });
  });
});
