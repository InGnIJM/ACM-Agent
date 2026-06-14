import { Test, TestingModule } from '@nestjs/testing';
import { AuthService } from '../src/auth/auth.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { JwtService } from '@nestjs/jwt';
import { ConflictException, UnauthorizedException, BadRequestException } from '@nestjs/common';
import * as bcrypt from 'bcrypt';

jest.mock('bcrypt');

describe('AuthService', () => {
  let service: AuthService;
  let prisma: {
    user: {
      findUnique: jest.Mock;
      create: jest.Mock;
    };
  };
  let jwt: {
    sign: jest.Mock;
    verify: jest.Mock;
  };

  beforeEach(async () => {
    prisma = {
      user: {
        findUnique: jest.fn(),
        create: jest.fn(),
      },
    };
    jwt = {
      sign: jest.fn(),
      verify: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AuthService,
        { provide: PrismaService, useValue: prisma },
        { provide: JwtService, useValue: jwt },
      ],
    }).compile();

    service = module.get<AuthService>(AuthService);

    jest.clearAllMocks();
  });

  // ─── register ────────────────────────────────────────────────────────

  describe('register', () => {
    const dto = { username: 'newuser', password: '123456' };

    it('creates user with hashed password and returns token', async () => {
      (bcrypt.hash as jest.Mock).mockResolvedValue('hashed_abc');
      prisma.user.findUnique.mockResolvedValue(null);
      prisma.user.create.mockResolvedValue({
        id: 'user-uuid-1',
        username: 'newuser',
        passwordHash: 'hashed_abc',
        role: 'user',
      });
      jwt.sign.mockReturnValueOnce('access-token-1').mockReturnValueOnce('refresh-token-1');

      const result = await service.register(dto);

      expect(bcrypt.hash).toHaveBeenCalledWith('123456', 10);
      expect(prisma.user.create).toHaveBeenCalledWith({
        data: {
          username: 'newuser',
          passwordHash: 'hashed_abc',
          nickname: undefined,
          studentId: undefined,
        },
      });
      expect(result).toEqual({
        access_token: 'access-token-1',
        refresh_token: 'refresh-token-1',
        expires_in: 7200,
        token_type: 'Bearer',
      });
    });

    it('rejects duplicate username with ConflictException', async () => {
      prisma.user.findUnique.mockResolvedValue({ id: 'existing-id', username: 'newuser' });

      await expect(service.register(dto)).rejects.toThrow(ConflictException);
      expect(prisma.user.create).not.toHaveBeenCalled();
    });

    it('rejects password shorter than 6 characters', async () => {
      const shortPw = { username: 'newuser', password: '12345' };

      await expect(service.register(shortPw)).rejects.toThrow(BadRequestException);
      expect(prisma.user.create).not.toHaveBeenCalled();
    });
  });

  // ─── login ───────────────────────────────────────────────────────────

  describe('login', () => {
    const dto = { username: 'testuser', password: 'correct' };

    it('returns token on successful login', async () => {
      prisma.user.findUnique.mockResolvedValue({
        id: 'user-uuid-1',
        username: 'testuser',
        passwordHash: 'hashed_abc',
        role: 'user',
      });
      (bcrypt.compare as jest.Mock).mockResolvedValue(true);
      jwt.sign.mockReturnValueOnce('access-token-1').mockReturnValueOnce('refresh-token-1');

      const result = await service.login(dto);

      expect(bcrypt.compare).toHaveBeenCalledWith('correct', 'hashed_abc');
      expect(result.access_token).toBe('access-token-1');
      expect(result.refresh_token).toBe('refresh-token-1');
    });

    it('rejects wrong password with UnauthorizedException', async () => {
      prisma.user.findUnique.mockResolvedValue({
        id: 'user-uuid-1',
        username: 'testuser',
        passwordHash: 'hashed_abc',
        role: 'user',
      });
      (bcrypt.compare as jest.Mock).mockResolvedValue(false);

      await expect(service.login({ ...dto, password: 'wrong' })).rejects.toThrow(
        UnauthorizedException,
      );
    });

    it('rejects non-existent user with UnauthorizedException', async () => {
      prisma.user.findUnique.mockResolvedValue(null);

      await expect(service.login({ username: 'ghost', password: 'whatever' })).rejects.toThrow(
        UnauthorizedException,
      );
    });
  });

  // ─── getProfile ──────────────────────────────────────────────────────

  describe('getProfile', () => {
    it('returns user without passwordHash and deletedAt', async () => {
      prisma.user.findUnique.mockResolvedValue({
        id: 'user-uuid-1',
        username: 'testuser',
        passwordHash: 'secret_hash',
        deletedAt: null,
        role: 'user',
        nickname: 'Test',
        studentId: 'S12345',
      });

      const result = await service.getProfile('user-uuid-1');

      expect(result).not.toHaveProperty('passwordHash');
      expect(result).not.toHaveProperty('deletedAt');
      expect(result).toMatchObject({
        id: 'user-uuid-1',
        username: 'testuser',
        role: 'user',
        nickname: 'Test',
        studentId: 'S12345',
      });
    });

    it('returns null for non-existent user', async () => {
      prisma.user.findUnique.mockResolvedValue(null);

      const result = await service.getProfile('ghost-id');

      expect(result).toBeNull();
    });
  });

  // ─── refreshToken ────────────────────────────────────────────────────

  describe('refreshToken', () => {
    it('returns new access_token on valid refresh token', async () => {
      jwt.verify.mockReturnValue({ sub: 'user-uuid-1', username: 'testuser', role: 'user' });
      jwt.sign.mockReturnValueOnce('new-access-token');

      const result = await service.refreshToken('valid-refresh-token');

      expect(jwt.verify).toHaveBeenCalledWith('valid-refresh-token', {
        secret: process.env.JWT_REFRESH_SECRET || 'dev-refresh-secret',
      });
      expect(result).toEqual({
        access_token: 'new-access-token',
        token_type: 'Bearer',
        expires_in: 7200,
      });
    });

    it('throws UnauthorizedException on invalid refresh token', async () => {
      jwt.verify.mockImplementation(() => {
        throw new Error('invalid token');
      });

      await expect(service.refreshToken('bad-token')).rejects.toThrow(UnauthorizedException);
    });
  });
});
