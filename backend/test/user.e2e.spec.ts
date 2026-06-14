import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import request from 'supertest';
import * as jwt from 'jsonwebtoken';
import { AppModule } from '../src/app.module';
import { PrismaService } from '../src/common/prisma/prisma.service';

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret';

function signToken(payload: { sub: string; username: string; role: string }): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: '1h' });
}

// Deterministic fixture IDs
const ADMIN_ID = 'admin-001';
const NORMAL_ID = 'user-001';
const OTHER_ID = 'user-002';

const adminFixture = {
  id: ADMIN_ID,
  username: 'admin1',
  passwordHash: 'hashed',
  role: 'admin',
  nickname: 'Admin',
  email: 'admin@example.com',
  realName: 'Admin',
  studentId: null,
  department: null,
  major: null,
  className: null,
  grade: null,
  enrollmentYear: null,
  feishuOpenId: null,
  qqNumber: null,
  pushChannels: {},
  createdAt: new Date('2024-01-01'),
  updatedAt: new Date('2024-01-01'),
  deletedAt: null,
  createdBy: null,
  updatedBy: null,
};

const normalFixture = {
  ...adminFixture,
  id: NORMAL_ID,
  username: 'normal1',
  role: 'user',
  nickname: 'Normal',
  email: 'normal@example.com',
  realName: 'Normal User',
};

const otherFixture = {
  ...adminFixture,
  id: OTHER_ID,
  username: 'other1',
  role: 'user',
  nickname: 'Other',
  email: 'other@example.com',
  realName: 'Other User',
};

describe('User (e2e)', () => {
  let app: INestApplication;
  let adminToken: string;
  let userToken: string;

  // In-memory store for mock Prisma
  const store = new Map<string, any>();

  beforeAll(async () => {
    // Seed store
    store.set(ADMIN_ID, { ...adminFixture });
    store.set(NORMAL_ID, { ...normalFixture });
    store.set(OTHER_ID, { ...otherFixture });

    // Generate JWT tokens
    adminToken = signToken({ sub: ADMIN_ID, username: adminFixture.username, role: 'admin' });
    userToken = signToken({ sub: NORMAL_ID, username: normalFixture.username, role: 'user' });

    const mockPrisma = {
      user: {
        findMany: jest.fn((args: any) => {
          let users = [...store.values()].filter((u: any) => u.deletedAt === null);
          if (args?.where?.role) {
            users = users.filter((u: any) => u.role === args.where.role);
          }
          const skip = args?.skip ?? 0;
          const take = args?.take ?? 20;
          const sliced = users.slice(skip, skip + take);
          if (args?.select) {
            return Promise.resolve(sliced.map(({ passwordHash, deletedAt, ...rest }: any) => rest));
          }
          return Promise.resolve(sliced);
        }),
        findUnique: jest.fn((args: any) => {
          const user = store.get(args.where.id);
          if (!user || user.deletedAt !== null) return Promise.resolve(null);
          return Promise.resolve({ ...user });
        }),
        update: jest.fn((args: any) => {
          const existing = store.get(args.where.id);
          if (!existing) return Promise.resolve(null);
          const updated = { ...existing, ...args.data, updatedAt: new Date() };
          store.set(args.where.id, updated);
          return Promise.resolve({ ...updated });
        }),
        count: jest.fn((args: any) => {
          let users = [...store.values()].filter((u: any) => u.deletedAt === null);
          if (args?.where?.role) {
            users = users.filter((u: any) => u.role === args.where.role);
          }
          return Promise.resolve(users.length);
        }),
      },
      platformAccount: {
        findFirst: jest.fn().mockResolvedValue(null),
        create: jest.fn((args: any) =>
          Promise.resolve({ id: 'pa-1', ...args.data, createdAt: new Date() }),
        ),
        deleteMany: jest.fn().mockResolvedValue({ count: 1 }),
      },
    };

    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(PrismaService)
      .useValue(mockPrisma)
      .compile();

    app = moduleFixture.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        transform: true,
        forbidNonWhitelisted: true,
      }),
    );
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  beforeEach(() => {
    store.clear();
    store.set(ADMIN_ID, { ...adminFixture });
    store.set(NORMAL_ID, { ...normalFixture });
    store.set(OTHER_ID, { ...otherFixture });
  });

  // ─── GET /api/users as admin → 200 + paginated ─────────────────────

  describe('GET /api/users', () => {
    it('returns 200 + paginated users for admin', async () => {
      const res = await request(app.getHttpServer())
        .get('/api/users')
        .set('Authorization', `Bearer ${adminToken}`)
        .expect(200);

      expect(res.body).toHaveProperty('data');
      expect(res.body).toHaveProperty('total');
      expect(res.body).toHaveProperty('page', 1);
      expect(res.body).toHaveProperty('limit', 20);
      expect(Array.isArray(res.body.data)).toBe(true);
      for (const user of res.body.data) {
        expect(user).not.toHaveProperty('passwordHash');
      }
    });

    it('returns 403 for regular user (non-admin)', async () => {
      const res = await request(app.getHttpServer())
        .get('/api/users')
        .set('Authorization', `Bearer ${userToken}`)
        .expect(403);

      expect(res.body).toHaveProperty('message');
      expect(res.body).toHaveProperty('statusCode', 403);
    });

    it('returns 401 without token', async () => {
      const res = await request(app.getHttpServer())
        .get('/api/users')
        .expect(401);

      expect(res.body).toHaveProperty('statusCode', 401);
    });
  });

  // ─── PATCH /api/users/:id ──────────────────────────────────────────

  describe('PATCH /api/users/:id', () => {
    it('returns 200 when updating own profile', async () => {
      const res = await request(app.getHttpServer())
        .patch(`/api/users/${NORMAL_ID}`)
        .set('Authorization', `Bearer ${userToken}`)
        .send({ nickname: 'UpdatedNick' })
        .expect(200);

      expect(res.body).not.toHaveProperty('passwordHash');
      expect(res.body).not.toHaveProperty('deletedAt');
      expect(res.body.nickname).toBe('UpdatedNick');
    });

    it('returns 403 when non-admin tries to update another user', async () => {
      const res = await request(app.getHttpServer())
        .patch(`/api/users/${OTHER_ID}`)
        .set('Authorization', `Bearer ${userToken}`)
        .send({ nickname: 'HackAttempt' })
        .expect(403);

      expect(res.body).toHaveProperty('statusCode', 403);
    });

    it('returns 200 when admin updates any user', async () => {
      const res = await request(app.getHttpServer())
        .patch(`/api/users/${NORMAL_ID}`)
        .set('Authorization', `Bearer ${adminToken}`)
        .send({ nickname: 'AdminSet' })
        .expect(200);

      expect(res.body.nickname).toBe('AdminSet');
    });
  });
});
