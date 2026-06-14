import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../src/app.module';
import { PrismaService } from '../src/common/prisma/prisma.service';

jest.mock('bcrypt', () => ({
  hash: jest.fn().mockResolvedValue('mocked_hashed_password'),
  compare: jest.fn(),
}));

import * as bcrypt from 'bcrypt';

describe('Auth (e2e)', () => {
  let app: INestApplication;
  let mockPrisma: {
    user: {
      findUnique: jest.Mock;
      create: jest.Mock;
    };
  };
  const inMemoryUsers: Map<string, any> = new Map();

  beforeAll(async () => {
    mockPrisma = {
      user: {
        findUnique: jest.fn((args: { where: any }) => {
          if (args.where.id) {
            return Promise.resolve(inMemoryUsers.get(args.where.id) || null);
          }
          if (args.where.username) {
            return Promise.resolve(
              [...inMemoryUsers.values()].find(
                (u) => u.username === args.where.username,
              ) || null,
            );
          }
          return Promise.resolve(null);
        }),
        create: jest.fn((args: { data: any }) => {
          const user = {
            id: `user-${inMemoryUsers.size + 1}-${Date.now()}`,
            username: args.data.username,
            passwordHash: args.data.passwordHash || 'mocked_hashed_password',
            role: args.data.role || 'user',
            nickname: args.data.nickname || null,
            studentId: args.data.studentId || null,
            email: null,
            realName: null,
            department: null,
            major: null,
            className: null,
            grade: null,
            enrollmentYear: null,
            feishuOpenId: null,
            qqNumber: null,
            pushChannels: {},
            createdAt: new Date(),
            updatedAt: new Date(),
            deletedAt: null,
            createdBy: null,
            updatedBy: null,
          };
          inMemoryUsers.set(user.id, user);
          return Promise.resolve(user);
        }),
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
    inMemoryUsers.clear();
    jest.clearAllMocks();
  });

  // ─── POST /api/auth/register ─────────────────────────────────────────

  describe('POST /api/auth/register', () => {
    it('returns 201 + token on success', async () => {
      const res = await request(app.getHttpServer())
        .post('/api/auth/register')
        .send({ username: 'newuser', password: '123456' })
        .expect(201);

      expect(res.body).toHaveProperty('access_token');
      expect(res.body).toHaveProperty('refresh_token');
      expect(res.body.expires_in).toBe(7200);
      expect(res.body.token_type).toBe('Bearer');
    });

    it('returns 409 on duplicate username', async () => {
      await request(app.getHttpServer())
        .post('/api/auth/register')
        .send({ username: 'dup', password: '123456' })
        .expect(201);

      const res = await request(app.getHttpServer())
        .post('/api/auth/register')
        .send({ username: 'dup', password: '123456' })
        .expect(409);

      expect(res.body.message).toBe('Username already exists');
    });
  });

  // ─── POST /api/auth/login ────────────────────────────────────────────

  describe('POST /api/auth/login', () => {
    it('returns 201 + token on success', async () => {
      // register first
      await request(app.getHttpServer())
        .post('/api/auth/register')
        .send({ username: 'logintest', password: 'correct' })
        .expect(201);

      (bcrypt.compare as jest.Mock).mockResolvedValue(true);

      const res = await request(app.getHttpServer())
        .post('/api/auth/login')
        .send({ username: 'logintest', password: 'correct' })
        .expect(201);

      expect(res.body).toHaveProperty('access_token');
      expect(res.body).toHaveProperty('refresh_token');
      expect(res.body.token_type).toBe('Bearer');
    });

    it('returns 401 on wrong password', async () => {
      // register first
      await request(app.getHttpServer())
        .post('/api/auth/register')
        .send({ username: 'wptest', password: 'correct' })
        .expect(201);

      (bcrypt.compare as jest.Mock).mockResolvedValue(false);

      const res = await request(app.getHttpServer())
        .post('/api/auth/login')
        .send({ username: 'wptest', password: 'wrong' })
        .expect(401);

      expect(res.body.message).toBe('Invalid credentials');
    });
  });

  // ─── GET /api/auth/me ────────────────────────────────────────────────

  describe('GET /api/auth/me', () => {
    it('returns 200 + user with valid token', async () => {
      // register to get a token
      const regRes = await request(app.getHttpServer())
        .post('/api/auth/register')
        .send({ username: 'metest', password: '123456' })
        .expect(201);

      const token = regRes.body.access_token;

      const res = await request(app.getHttpServer())
        .get('/api/auth/me')
        .set('Authorization', `Bearer ${token}`)
        .expect(200);

      expect(res.body).toHaveProperty('id');
      expect(res.body).toHaveProperty('username', 'metest');
      expect(res.body).toHaveProperty('role', 'user');
      expect(res.body).not.toHaveProperty('passwordHash');
      expect(res.body).not.toHaveProperty('deletedAt');
    });

    it('returns 401 without token', async () => {
      const res = await request(app.getHttpServer())
        .get('/api/auth/me')
        .expect(401);

      expect(res.body).toHaveProperty('message');
      expect(res.body.statusCode).toBe(401);
    });
  });
});
