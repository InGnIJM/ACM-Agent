import { Test, TestingModule } from '@nestjs/testing';
import {
  NotFoundException,
  ConflictException,
  ForbiddenException,
} from '@nestjs/common';
import { UserService } from '../src/user/user.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { Platform, UserRole } from '@prisma/client';

describe('UserService', () => {
  let service: UserService;

  const mockPrisma = {
    user: {
      findMany: jest.fn(),
      findUnique: jest.fn(),
      update: jest.fn(),
      count: jest.fn(),
    },
    platformAccount: {
      findFirst: jest.fn(),
      create: jest.fn(),
      deleteMany: jest.fn(),
    },
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        UserService,
        { provide: PrismaService, useValue: mockPrisma },
      ],
    }).compile();

    service = module.get<UserService>(UserService);
    jest.clearAllMocks();
  });

  // ─── sample data ──────────────────────────────────────────────────────────

  const makeUser = (overrides: Record<string, unknown> = {}) => ({
    id: 'uuid-1',
    username: 'alice',
    passwordHash: '$2b$10$hashed',
    role: UserRole.user,
    nickname: 'Alice',
    email: 'alice@example.com',
    realName: 'Alice Wang',
    studentId: '2024001',
    department: 'CS',
    major: 'CS',
    className: 'CS2401',
    grade: '2024',
    enrollmentYear: 2024,
    feishuOpenId: null,
    qqNumber: null,
    pushChannels: {},
    createdAt: new Date('2024-01-01'),
    updatedAt: new Date('2024-01-02'),
    deletedAt: null,
    createdBy: null,
    updatedBy: null,
    ...overrides,
  });

  const safeUser = (u: Record<string, unknown>) => {
    const { passwordHash, deletedAt, ...rest } = u;
    return rest;
  };

  // ─── findAll ─────────────────────────────────────────────────────────────

  describe('findAll', () => {
    it('returns paginated users without passwordHash', async () => {
      // Real Prisma with select won't return passwordHash or deletedAt
      const users = [makeUser(), makeUser({ id: 'uuid-2', username: 'bob' })];
      const usersWithoutSensitive = users.map(safeUser);
      mockPrisma.user.findMany.mockResolvedValue(usersWithoutSensitive);
      mockPrisma.user.count.mockResolvedValue(2);

      const result = await service.findAll({});

      expect(result).toEqual({
        data: usersWithoutSensitive,
        total: 2,
        page: 1,
        limit: 20,
      });
      expect(mockPrisma.user.findMany).toHaveBeenCalledWith(
        expect.objectContaining({
          skip: 0,
          take: 20,
        }),
      );
    });

    it('filters by role', async () => {
      const users = [makeUser({ role: UserRole.admin })];
      mockPrisma.user.findMany.mockResolvedValue(users);
      mockPrisma.user.count.mockResolvedValue(1);

      const result = await service.findAll({ role: UserRole.admin });

      expect(result.data).toHaveLength(1);
      expect(mockPrisma.user.findMany).toHaveBeenCalledWith(
        expect.objectContaining({
          where: expect.objectContaining({ role: UserRole.admin }),
        }),
      );
    });

    it('filters by platform (users with platform account)', async () => {
      const users = [makeUser()];
      mockPrisma.user.findMany.mockResolvedValue(users);
      mockPrisma.user.count.mockResolvedValue(1);

      await service.findAll({ platform: Platform.luogu });

      expect(mockPrisma.user.findMany).toHaveBeenCalledWith(
        expect.objectContaining({
          where: expect.objectContaining({
            platformAccounts: {
              some: { platform: Platform.luogu },
            },
          }),
        }),
      );
    });

    it('searches across username/nickname/studentId', async () => {
      const users = [makeUser()];
      mockPrisma.user.findMany.mockResolvedValue(users);
      mockPrisma.user.count.mockResolvedValue(1);

      await service.findAll({ search: 'ali' });

      expect(mockPrisma.user.findMany).toHaveBeenCalledWith(
        expect.objectContaining({
          where: expect.objectContaining({
            OR: [
              { username: { contains: 'ali' } },
              { nickname: { contains: 'ali' } },
              { studentId: { contains: 'ali' } },
            ],
          }),
        }),
      );
    });

    it('trims search input', async () => {
      mockPrisma.user.findMany.mockResolvedValue([]);
      mockPrisma.user.count.mockResolvedValue(0);

      await service.findAll({ search: '  hello  ' });

      expect(mockPrisma.user.findMany).toHaveBeenCalledWith(
        expect.objectContaining({
          where: expect.objectContaining({
            OR: expect.arrayContaining([
              { username: { contains: 'hello' } },
            ]),
          }),
        }),
      );
    });

    it('applies custom page/limit with correct skip', async () => {
      mockPrisma.user.findMany.mockResolvedValue([]);
      mockPrisma.user.count.mockResolvedValue(0);

      const result = await service.findAll({ page: 3, limit: 10 });

      expect(result.page).toBe(3);
      expect(result.limit).toBe(10);
      expect(mockPrisma.user.findMany).toHaveBeenCalledWith(
        expect.objectContaining({ skip: 20, take: 10 }),
      );
    });

    it('combines role filter and search together', async () => {
      mockPrisma.user.findMany.mockResolvedValue([]);
      mockPrisma.user.count.mockResolvedValue(0);

      await service.findAll({ role: UserRole.user, search: 'bob' });

      const callArgs = mockPrisma.user.findMany.mock.calls[0][0];
      expect(callArgs.where.role).toBe(UserRole.user);
      expect(callArgs.where.OR).toBeDefined();
    });

    it('returns empty data when no users match', async () => {
      mockPrisma.user.findMany.mockResolvedValue([]);
      mockPrisma.user.count.mockResolvedValue(0);

      const result = await service.findAll({});

      expect(result).toEqual({ data: [], total: 0, page: 1, limit: 20 });
    });

    it('uses select to exclude passwordHash from findMany', async () => {
      mockPrisma.user.findMany.mockResolvedValue([]);
      mockPrisma.user.count.mockResolvedValue(0);

      await service.findAll({});

      const callArgs = mockPrisma.user.findMany.mock.calls[0][0];
      expect(callArgs.select).toBeDefined();
      expect(callArgs.select).not.toHaveProperty('passwordHash');
      expect(callArgs.select).toHaveProperty('id');
      expect(callArgs.select).toHaveProperty('username');
    });
  });

  // ─── findById ────────────────────────────────────────────────────────────

  describe('findById', () => {
    it('returns user without passwordHash', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);

      const result = await service.findById('uuid-1');

      expect(result).not.toHaveProperty('passwordHash');
      expect(result).not.toHaveProperty('deletedAt');
      expect(result.username).toBe('alice');
    });

    it('throws NotFoundException when user does not exist', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);

      await expect(service.findById('nonexistent')).rejects.toThrow(
        NotFoundException,
      );
    });

    it('soft-deleted users are not found (middleware adds deletedAt=null)', async () => {
      // The PrismaService middleware adds `deletedAt: null` automatically,
      // so findUnique will return null for soft-deleted users.
      mockPrisma.user.findUnique.mockResolvedValue(null);

      await expect(service.findById('deleted-user')).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  // ─── update ──────────────────────────────────────────────────────────────

  describe('update', () => {
    const admin = { userId: 'admin-id', role: 'admin' };
    const self = { userId: 'uuid-1', role: 'user' };
    const other = { userId: 'uuid-other', role: 'user' };

    it('updates own profile (self)', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);
      const updated = makeUser({ nickname: 'NewNick' });
      mockPrisma.user.update.mockResolvedValue(updated);

      const result = await service.update('uuid-1', { nickname: 'NewNick' }, self);

      expect(result).not.toHaveProperty('passwordHash');
      expect(result.nickname).toBe('NewNick');
      expect(mockPrisma.user.update).toHaveBeenCalledWith(
        expect.objectContaining({
          where: { id: 'uuid-1' },
          data: expect.objectContaining({ nickname: 'NewNick', updatedBy: 'uuid-1' }),
        }),
      );
    });

    it('admin can update any user', async () => {
      const user = makeUser({ id: 'uuid-2' });
      mockPrisma.user.findUnique.mockResolvedValue(user);
      const updated = makeUser({ id: 'uuid-2', nickname: 'AdminSet' });
      mockPrisma.user.update.mockResolvedValue(updated);

      const result = await service.update(
        'uuid-2',
        { nickname: 'AdminSet' },
        admin,
      );

      expect(result.nickname).toBe('AdminSet');
      expect(mockPrisma.user.update).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({ updatedBy: 'admin-id' }),
        }),
      );
    });

    it('rejects non-admin trying to update another user', async () => {
      const user = makeUser({ id: 'uuid-2' });
      mockPrisma.user.findUnique.mockResolvedValue(user);

      await expect(
        service.update('uuid-2', { nickname: 'Hack' }, other),
      ).rejects.toThrow(ForbiddenException);
    });

    it('throws NotFoundException when user does not exist', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);

      await expect(
        service.update('nonexistent', { nickname: 'X' }, admin),
      ).rejects.toThrow(NotFoundException);
    });

    it('strips passwordHash/username/role from update data', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);
      mockPrisma.user.update.mockResolvedValue(user);

      await service.update(
        'uuid-1',
        {
          nickname: 'Safe',
          passwordHash: 'should-be-stripped',
          username: 'should-be-stripped',
          role: 'should-be-stripped',
        } as any,
        self,
      );

      const updateCall = mockPrisma.user.update.mock.calls[0][0];
      expect(updateCall.data).not.toHaveProperty('passwordHash');
      expect(updateCall.data).not.toHaveProperty('username');
      expect(updateCall.data).not.toHaveProperty('role');
    });

    it('strips undefined fields from update data', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);
      mockPrisma.user.update.mockResolvedValue(user);

      await service.update('uuid-1', { nickname: 'Only' }, self);

      const updateCall = mockPrisma.user.update.mock.calls[0][0];
      // Only nickname and updatedBy should be present
      expect(Object.keys(updateCall.data).sort()).toEqual(
        ['nickname', 'updatedBy'].sort(),
      );
    });

    it('sets updatedBy to actor userId', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);
      mockPrisma.user.update.mockResolvedValue(user);

      await service.update('uuid-1', { nickname: 'X' }, self);

      expect(mockPrisma.user.update).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({ updatedBy: 'uuid-1' }),
        }),
      );
    });
  });

  // ─── softDelete ──────────────────────────────────────────────────────────

  describe('softDelete', () => {
    it('sets deletedAt to current date', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);
      mockPrisma.user.update.mockResolvedValue({ ...user, deletedAt: new Date() });

      await service.softDelete('uuid-1');

      expect(mockPrisma.user.update).toHaveBeenCalledWith(
        expect.objectContaining({
          where: { id: 'uuid-1' },
          data: { deletedAt: expect.any(Date) },
        }),
      );
    });

    it('throws NotFoundException when user does not exist', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);

      await expect(service.softDelete('nonexistent')).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  // ─── bindPlatform ────────────────────────────────────────────────────────

  describe('bindPlatform', () => {
    const bindDto = {
      platform: Platform.luogu,
      platformUid: '12345',
      platformUsername: 'luogu_user',
    };

    const bindDtoNoUsername = {
      platform: Platform.codeforces,
      platformUid: 'cf_user',
    };

    it('creates a platform account', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);
      mockPrisma.platformAccount.findFirst.mockResolvedValue(null);
      const account = {
        id: 'pa-1',
        userId: 'uuid-1',
        platform: Platform.luogu,
        platformUid: '12345',
        platformUsername: 'luogu_user',
        createdAt: new Date(),
      };
      mockPrisma.platformAccount.create.mockResolvedValue(account);

      const result = await service.bindPlatform('uuid-1', bindDto);

      expect(result).toEqual(account);
      expect(mockPrisma.platformAccount.create).toHaveBeenCalledWith({
        data: {
          userId: 'uuid-1',
          platform: Platform.luogu,
          platformUid: '12345',
          platformUsername: 'luogu_user',
        },
      });
    });

    it('falls back to platformUid when platformUsername is not provided', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);
      mockPrisma.platformAccount.findFirst.mockResolvedValue(null);
      mockPrisma.platformAccount.create.mockResolvedValue({});

      await service.bindPlatform('uuid-1', bindDtoNoUsername);

      expect(mockPrisma.platformAccount.create).toHaveBeenCalledWith({
        data: expect.objectContaining({
          platformUsername: 'cf_user', // falls back to platformUid
        }),
      });
    });

    it('rejects duplicate binding (same platform + platformUid)', async () => {
      const user = makeUser();
      mockPrisma.user.findUnique.mockResolvedValue(user);
      mockPrisma.platformAccount.findFirst.mockResolvedValue({
        id: 'existing-pa',
        platform: Platform.luogu,
        platformUid: '12345',
      });

      await expect(
        service.bindPlatform('uuid-1', bindDto),
      ).rejects.toThrow(ConflictException);
    });

    it('throws NotFoundException when user does not exist', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);

      await expect(
        service.bindPlatform('nonexistent', bindDto),
      ).rejects.toThrow(NotFoundException);
    });
  });

  // ─── unbindPlatform ──────────────────────────────────────────────────────

  describe('unbindPlatform', () => {
    it('deletes matching platform accounts for the user', async () => {
      mockPrisma.platformAccount.deleteMany.mockResolvedValue({ count: 1 });

      await service.unbindPlatform('uuid-1', Platform.luogu);

      expect(mockPrisma.platformAccount.deleteMany).toHaveBeenCalledWith({
        where: {
          userId: 'uuid-1',
          platform: Platform.luogu,
        },
      });
    });

    it('does not throw when no accounts match', async () => {
      mockPrisma.platformAccount.deleteMany.mockResolvedValue({ count: 0 });

      await expect(
        service.unbindPlatform('uuid-1', Platform.atcoder),
      ).resolves.toBeUndefined();
    });
  });
});
