import { Test, TestingModule } from '@nestjs/testing';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { PrismaModule } from '../src/common/prisma/prisma.module';

describe('PrismaService', () => {
  let service: PrismaService;
  let moduleRef: TestingModule;

  beforeAll(async () => {
    moduleRef = await Test.createTestingModule({
      imports: [PrismaModule],
    }).compile();
    service = moduleRef.get<PrismaService>(PrismaService);
  });

  afterAll(async () => {
    await service.$disconnect();
    await moduleRef.close();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('should execute SELECT 1', async () => {
    const result = await service.$queryRaw`SELECT 1`;
    expect(result).toBeDefined();
  });

  it('should have all 12 tables', async () => {
    const rows = await service.$queryRaw<
      Array<{ table_name: string }>
    >`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
      ORDER BY table_name
    `;
    const names = rows.map((r) => r.table_name).sort();
    expect(names).toEqual([
      'bot_configs',
      'platform_accounts',
      'practice_records',
      'problem_solutions',
      'problems',
      'push_logs',
      'team_members',
      'teams',
      'training_plans',
      'user_daily_stats',
      'user_profiles',
      'users',
    ]);
  });

  it('should have all 8 enum types', async () => {
    const rows = await service.$queryRaw<
      Array<{ typname: string }>
    >`
      SELECT typname FROM pg_type
      WHERE typtype = 'e'
      ORDER BY typname
    `;
    const names = rows.map((r) => r.typname).sort();
    expect(names).toEqual([
      'BotChannel',
      'Platform',
      'PushMessageType',
      'PushStatus',
      'TeamStatus',
      'TrainingPlanStatus',
      'UserRole',
      'Verdict',
    ]);
  });

  describe('soft delete', () => {
    const testUserId = '00000000-0000-0000-0000-00000000feed';

    afterAll(async () => {
      await service.$executeRaw`DELETE FROM users WHERE id = ${testUserId}::uuid`;
    });

    it('should return null for soft-deleted record via findUnique', async () => {
      // Upsert-style: ensure a clean test row
      await service.$executeRaw`
        INSERT INTO users (id, username, password_hash, role, created_at, updated_at)
        VALUES (${testUserId}::uuid, 'sd-test', 'hash', 'user', NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET deleted_at = NULL, username = 'sd-test'
      `;

      // Soft-delete it
      await service.$executeRaw`
        UPDATE users SET deleted_at = NOW() WHERE id = ${testUserId}::uuid
      `;

      // findUnique should return null (middleware adds deletedAt: null)
      const user = await service.user.findUnique({
        where: { id: testUserId },
      });
      expect(user).toBeNull();

      // Raw SQL without soft-delete filter should still find the row
      const raw = await service.$queryRaw<
        Array<{ id: string; deleted_at: Date | null }>
      >`
        SELECT id, deleted_at FROM users
        WHERE id = ${testUserId}::uuid AND deleted_at IS NOT NULL
      `;
      expect(raw).toHaveLength(1);
      expect(raw[0].deleted_at).not.toBeNull();
    });
  });

  describe('PGVector', () => {
    it('should have vector extension installed', async () => {
      const rows = await service.$queryRaw<
        Array<{ extname: string }>
      >`
        SELECT extname FROM pg_extension WHERE extname = 'vector'
      `;
      expect(rows).toHaveLength(1);
      expect(rows[0].extname).toBe('vector');
    });

    it('should have vector_embedding and content_vector columns on problems table', async () => {
      const rows = await service.$queryRaw<
        Array<{ column_name: string; udt_name: string }>
      >`
        SELECT column_name, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'problems'
          AND column_name IN ('vector_embedding', 'content_vector')
        ORDER BY column_name
      `;
      expect(rows).toHaveLength(2);
      expect(rows[0]).toEqual({ column_name: 'content_vector', udt_name: 'vector' });
      expect(rows[1]).toEqual({ column_name: 'vector_embedding', udt_name: 'vector' });
    });

    it('should have vector_embedding column on problem_solutions table', async () => {
      const rows = await service.$queryRaw<
        Array<{ column_name: string; udt_name: string }>
      >`
        SELECT column_name, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'problem_solutions'
          AND column_name = 'vector_embedding'
      `;
      expect(rows).toHaveLength(1);
      expect(rows[0]).toEqual({ column_name: 'vector_embedding', udt_name: 'vector' });
    });

    it('should have vector indexes on problems and problem_solutions', async () => {
      const rows = await service.$queryRaw<
        Array<{ indexname: string }>
      >`
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname LIKE 'idx\\_%\\_vector%'
        ORDER BY indexname
      `;
      const names = rows.map((r) => r.indexname).sort();
      expect(names).toEqual([
        'idx_problem_solutions_vector',
        'idx_problems_content_vector',
        'idx_problems_vector_embedding',
      ]);
    });
  });
});
