# Phase 2: 用户管理系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans

**Goal:** 实现 NestJS 用户认证（JWT + bcrypt）和用户管理（CRUD + 平台绑定），90% 测试覆盖率通过后进入 Phase 3

**Architecture:** AuthModule (JWT 无状态认证) + UserModule (CRUD + 平台绑定) + RolesGuard (admin/user/observed 三级权限)

**Tech Stack:** NestJS 10, Prisma 5, bcrypt, @nestjs/jwt, @nestjs/passport, class-validator, Jest

---

## 文件结构

```
backend/src/
├── auth/
│   ├── auth.module.ts
│   ├── auth.service.ts
│   ├── auth.controller.ts
│   ├── jwt.strategy.ts
│   └── dto/
│       ├── login.dto.ts
│       ├── register.dto.ts
│       └── token-response.dto.ts
├── user/
│   ├── user.module.ts
│   ├── user.service.ts
│   ├── user.controller.ts
│   └── dto/
│       ├── user-query.dto.ts
│       ├── update-user.dto.ts
│       └── bind-platform.dto.ts
└── common/
    ├── guards/
    │   ├── jwt-auth.guard.ts
    │   ├── roles.guard.ts
    │   └── optional-auth.guard.ts
    └── decorators/
        ├── roles.decorator.ts
        └── current-user.decorator.ts

backend/test/
├── auth.service.spec.ts
├── auth.e2e.spec.ts
├── user.service.spec.ts
└── guards.spec.ts
```

---

## Task 1: AuthModule — Service

**Files:** Create `backend/src/auth/auth.module.ts`, `auth.service.ts`, `dto/`

- [ ] **Step 1: 写测试 — AuthService**

```typescript
// backend/test/auth.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { AuthService } from '../src/auth/auth.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { UnauthorizedException, ConflictException } from '@nestjs/common';

const mockPrisma = {
  user: { findUnique: jest.fn(), create: jest.fn() },
};

const mockJwt = { sign: jest.fn() };

describe('AuthService', () => {
  let service: AuthService;

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        AuthService,
        { provide: PrismaService, useValue: mockPrisma },
        { provide: JwtService, useValue: mockJwt },
      ],
    }).compile();
    service = module.get(AuthService);
    jest.clearAllMocks();
  });

  describe('register', () => {
    it('should create user with hashed password', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);
      mockPrisma.user.create.mockResolvedValue({
        id: 'u1', username: 'test', role: 'user', passwordHash: 'hashed',
      });
      mockJwt.sign.mockReturnValue('token');
      const result = await service.register({ username: 'test', password: 'password123' });
      expect(mockPrisma.user.create).toHaveBeenCalled();
      const call = mockPrisma.user.create.mock.calls[0][0];
      expect(call.data.username).toBe('test');
      expect(call.data.passwordHash).not.toBe('password123'); // hashed
      expect(result.access_token).toBe('token');
    });

    it('should reject duplicate username', async () => {
      mockPrisma.user.findUnique.mockResolvedValue({ id: 'u1' });
      await expect(service.register({ username: 'test', password: 'pass' }))
        .rejects.toThrow(ConflictException);
    });

    it('should reject short password', async () => {
      await expect(service.register({ username: 'test', password: '12345' }))
        .rejects.toThrow('密码至少6位');
    });
  });

  describe('login', () => {
    it('should return token on success', async () => {
      const hash = await bcrypt.hash('password123', 10);
      mockPrisma.user.findUnique.mockResolvedValue({
        id: 'u1', username: 'test', role: 'user', passwordHash: hash,
      });
      mockJwt.sign.mockReturnValue('access').mockReturnValueOnce('refresh');
      const result = await service.login({ username: 'test', password: 'password123' });
      expect(result.access_token).toBeDefined();
      expect(result.token_type).toBe('Bearer');
    });

    it('should reject wrong password', async () => {
      const hash = await bcrypt.hash('right', 10);
      mockPrisma.user.findUnique.mockResolvedValue({
        id: 'u1', username: 'test', passwordHash: hash,
      });
      await expect(service.login({ username: 'test', password: 'wrong' }))
        .rejects.toThrow(UnauthorizedException);
    });

    it('should reject non-existent user', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);
      await expect(service.login({ username: 'ghost', password: 'pass' }))
        .rejects.toThrow(UnauthorizedException);
    });
  });

  describe('getProfile', () => {
    it('should return user without passwordHash', async () => {
      mockPrisma.user.findUnique.mockResolvedValue({
        id: 'u1', username: 'test', role: 'user', createdAt: new Date(),
      });
      const result = await service.getProfile('u1');
      expect(result).not.toHaveProperty('passwordHash');
      expect(result).not.toHaveProperty('password_hash');
    });

    it('should return null for non-existent user', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);
      expect(await service.getProfile('ghost')).toBeNull();
    });
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
npx jest test/auth.service.spec.ts --no-cache
# 预期: FAIL — AuthService not defined
```

- [ ] **Step 3: 实现 AuthService**

```typescript
// backend/src/auth/auth.service.ts
import { Injectable, UnauthorizedException, ConflictException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { PrismaService } from '../common/prisma/prisma.service';
import { LoginDto, RegisterDto } from './dto';

@Injectable()
export class AuthService {
  constructor(private prisma: PrismaService, private jwt: JwtService) {}

  async register(dto: RegisterDto) {
    if (dto.password.length < 6) throw new ConflictException('密码至少6位');
    const existing = await this.prisma.user.findUnique({ where: { username: dto.username } });
    if (existing) throw new ConflictException('用户名已被注册');
    const passwordHash = await bcrypt.hash(dto.password, 10);
    const user = await this.prisma.user.create({
      data: { username: dto.username, passwordHash, role: 'user' },
    });
    const tokens = this.generateTokens(user.id, user.username, user.role as any);
    return { ...tokens, token_type: 'Bearer' };
  }

  async login(dto: LoginDto) {
    const user = await this.prisma.user.findUnique({ where: { username: dto.username } });
    if (!user) throw new UnauthorizedException('用户名或密码错误');
    const valid = await bcrypt.compare(dto.password, user.passwordHash);
    if (!valid) throw new UnauthorizedException('用户名或密码错误');
    const tokens = this.generateTokens(user.id, user.username, user.role as any);
    return { ...tokens, token_type: 'Bearer' };
  }

  async getProfile(userId: string) {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) return null;
    const { passwordHash, deletedAt, ...safe } = user;
    return safe;
  }

  async refreshToken(token: string) {
    try {
      const payload = this.jwt.verify(token, { secret: process.env.JWT_REFRESH_SECRET || process.env.JWT_SECRET });
      const access = this.jwt.sign({ sub: payload.sub, username: payload.username, role: payload.role }, { expiresIn: '2h' });
      return { access_token: access, token_type: 'Bearer', expires_in: 7200 };
    } catch {
      throw new UnauthorizedException('Refresh token 已过期');
    }
  }

  private generateTokens(sub: string, username: string, role: string) {
    const payload = { sub, username, role };
    return {
      access_token: this.jwt.sign(payload, { expiresIn: '2h' }),
      refresh_token: this.jwt.sign(payload, { secret: process.env.JWT_REFRESH_SECRET || process.env.JWT_SECRET, expiresIn: '7d' }),
      expires_in: 7200,
    };
  }
}
```

- [ ] **Step 4: 创建 DTOs**

```typescript
// backend/src/auth/dto/register.dto.ts
import { IsString, MinLength, MaxLength, IsOptional } from 'class-validator';
export class RegisterDto {
  @IsString() @MinLength(3) @MaxLength(50) username: string;
  @IsString() @MinLength(6) password: string;
  @IsOptional() @IsString() nickname?: string;
  @IsOptional() @IsString() @MaxLength(30) studentId?: string;
}
```

```typescript
// backend/src/auth/dto/login.dto.ts
import { IsString } from 'class-validator';
export class LoginDto {
  @IsString() username: string;
  @IsString() password: string;
}
```

- [ ] **Step 5: 实现 AuthModule**

```typescript
// backend/src/auth/auth.module.ts
import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { AuthService } from './auth.service';
import { AuthController } from './auth.controller';
import { JwtStrategy } from './jwt.strategy';

@Module({
  imports: [JwtModule.register({ secret: process.env.JWT_SECRET || 'dev-secret', signOptions: { expiresIn: '2h' } })],
  controllers: [AuthController],
  providers: [AuthService, JwtStrategy],
  exports: [AuthService],
})
export class AuthModule {}
```

- [ ] **Step 6: 运行测试**

```bash
npx jest test/auth.service.spec.ts --no-cache
# 预期: 全部 PASS
```

- [ ] **Step 7: Commit**

```bash
git add backend/src/auth/ backend/test/auth.service.spec.ts
git commit -m "feat(auth): add AuthService with JWT+brypt register/login"
```

---

## Task 2: AuthController + JWT Guard

- [ ] **Step 1: 写测试 — AuthController (e2e)**

```typescript
// backend/test/auth.e2e.spec.ts
import { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';

describe('AuthController (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const module = await Test.createTestingModule({ imports: [AppModule] }).compile();
    app = module.createNestApplication();
    await app.init();
  });

  afterAll(() => app.close());

  const testUser = { username: `e2e_${Date.now()}`, password: 'test123' };
  let token: string;

  it('POST /api/auth/register → 201 + token', async () => {
    const res = await request(app.getHttpServer()).post('/api/auth/register').send(testUser);
    expect(res.status).toBe(201);
    expect(res.body.access_token).toBeDefined();
    expect(res.body.token_type).toBe('Bearer');
    token = res.body.access_token;
  });

  it('POST /api/auth/login → 201 + token', async () => {
    const res = await request(app.getHttpServer()).post('/api/auth/login').send(testUser);
    expect(res.status).toBe(201);
    expect(res.body.access_token).toBeDefined();
  });

  it('POST /api/auth/register duplicate → 409', async () => {
    const res = await request(app.getHttpServer()).post('/api/auth/register').send(testUser);
    expect(res.status).toBe(409);
  });

  it('POST /api/auth/login wrong password → 401', async () => {
    const res = await request(app.getHttpServer()).post('/api/auth/login')
      .send({ username: testUser.username, password: 'wrong' });
    expect(res.status).toBe(401);
  });

  it('GET /api/auth/me with token → 200', async () => {
    const res = await request(app.getHttpServer()).get('/api/auth/me')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
    expect(res.body.username).toBe(testUser.username);
  });

  it('GET /api/auth/me without token → 401', async () => {
    const res = await request(app.getHttpServer()).get('/api/auth/me');
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 2: 运行确认失败**

```bash
npx jest test/auth.e2e.spec.ts --no-cache
# 预期: FAIL — AuthController 不存在
```

- [ ] **Step 3: 实现 AuthController + JwtStrategy + Guards**

```typescript
// backend/src/auth/jwt.strategy.ts
import { Injectable } from '@nestjs/common';
import { PassportStrategy } from '@nestjs/passport';
import { ExtractJwt, Strategy } from 'passport-jwt';

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy) {
  constructor() {
    super({ jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(), secretOrKey: process.env.JWT_SECRET || 'dev-secret' });
  }
  async validate(payload: any) { return { userId: payload.sub, username: payload.username, role: payload.role }; }
}
```

```typescript
// backend/src/auth/auth.controller.ts
import { Controller, Post, Get, Body, UseGuards, HttpCode } from '@nestjs/common';
import { AuthService } from './auth.service';
import { LoginDto, RegisterDto } from './dto';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { RefreshTokenDto } from './dto/refresh-token.dto';

@Controller('api/auth')
export class AuthController {
  constructor(private auth: AuthService) {}

  @Post('register') @HttpCode(201)
  register(@Body() dto: RegisterDto) { return this.auth.register(dto); }

  @Post('login') @HttpCode(201)
  login(@Body() dto: LoginDto) { return this.auth.login(dto); }

  @Post('refresh') @HttpCode(201)
  refresh(@Body() dto: RefreshTokenDto) { return this.auth.refreshToken(dto.refresh_token); }

  @Get('me') @UseGuards(JwtAuthGuard)
  getProfile(@CurrentUser() user: any) { return this.auth.getProfile(user.userId); }
}
```

```typescript
// backend/src/common/guards/jwt-auth.guard.ts
import { Injectable } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {}
```

```typescript
// backend/src/common/guards/roles.guard.ts
import { Injectable, CanActivate, ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}
  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.get<string[]>('roles', context.getHandler());
    if (!requiredRoles) return true;
    const { user } = context.switchToHttp().getRequest();
    return requiredRoles.includes(user.role);
  }
}
```

```typescript
// backend/src/common/decorators/current-user.decorator.ts
import { createParamDecorator, ExecutionContext } from '@nestjs/common';
export const CurrentUser = createParamDecorator((data: unknown, ctx: ExecutionContext) => {
  return ctx.switchToHttp().getRequest().user;
});
```

```typescript
// backend/src/common/decorators/roles.decorator.ts
import { SetMetadata } from '@nestjs/common';
export const Roles = (...roles: string[]) => SetMetadata('roles', roles);
```

- [ ] **Step 4: 更新 AppModule**

```typescript
// 修改 backend/src/app.module.ts — 添加 AuthModule
imports: [ConfigModule.forRoot({ isGlobal: true }), PrismaModule, AuthModule, HealthModule],
```

- [ ] **Step 5: 运行 E2E 测试**

```bash
npx jest test/auth.e2e.spec.ts --no-cache
# 预期: 全部 PASS
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(auth): add AuthController, JWT strategy, guards, e2e tests"
```

---

## Task 3: UserModule

- [ ] **Step 1: 写测试 — UserService**

```typescript
// backend/test/user.service.spec.ts
describe('UserService', () => {
  let service: UserService;
  const mockPrisma = {
    user: { findMany: jest.fn(), findUnique: jest.fn(), update: jest.fn(), count: jest.fn(), delete: jest.fn() },
    platformAccount: { create: jest.fn(), findFirst: jest.fn(), delete: jest.fn() },
  };

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [UserService, { provide: PrismaService, useValue: mockPrisma }],
    }).compile();
    service = module.get(UserService);
  });

  it('findAll should return paginated users without passwordHash', async () => {
    mockPrisma.user.findMany.mockResolvedValue([{ id: '1', username: 'test', role: 'user' }]);
    mockPrisma.user.count.mockResolvedValue(1);
    const result = await service.findAll({ page: 1, limit: 20 });
    expect(result.data).toHaveLength(1);
    expect(result.data[0]).not.toHaveProperty('passwordHash');
    expect(result.total).toBe(1);
  });

  it('findAll should filter by role', async () => {
    mockPrisma.user.findMany.mockResolvedValue([]);
    mockPrisma.user.count.mockResolvedValue(0);
    const result = await service.findAll({ page: 1, limit: 20, role: 'observed' });
    expect(mockPrisma.user.findMany).toHaveBeenCalledWith(expect.objectContaining({ where: expect.objectContaining({ role: 'observed' }) }));
  });

  it('findAll should search across username/nickname/studentId', async () => {
    mockPrisma.user.findMany.mockResolvedValue([]);
    mockPrisma.user.count.mockResolvedValue(0);
    await service.findAll({ page: 1, limit: 20, search: 'zhang' });
    expect(mockPrisma.user.findMany).toHaveBeenCalledWith(expect.objectContaining({
      where: expect.objectContaining({ deletedAt: null }),
    }));
  });

  it('update should reject passwordHash from DTO', async () => {
    mockPrisma.user.findUnique.mockResolvedValue({ id: '1' });
    mockPrisma.user.update.mockResolvedValue({ id: '1', username: 'test' });
    await service.update('1', { nickname: 'new', passwordHash: 'hacked' } as any);
    expect(mockPrisma.user.update).toHaveBeenCalled();
    const updateData = mockPrisma.user.update.mock.calls[0][0].data;
    expect(updateData.passwordHash).toBeUndefined();
  });

  it('bindPlatform should create platform account', async () => {
    mockPrisma.user.findUnique.mockResolvedValue({ id: '1' });
    mockPrisma.platformAccount.findFirst.mockResolvedValue(null);
    mockPrisma.platformAccount.create.mockResolvedValue({ id: 'p1', platform: 'luogu' });
    const result = await service.bindPlatform('1', { platform: 'luogu', platformUid: '12345' });
    expect(result.platform).toBe('luogu');
  });

  it('bindPlatform should reject duplicate', async () => {
    mockPrisma.user.findUnique.mockResolvedValue({ id: '1' });
    mockPrisma.platformAccount.findFirst.mockResolvedValue({ id: 'p1' });
    await expect(service.bindPlatform('1', { platform: 'luogu', platformUid: '12345' }))
      .rejects.toThrow(ConflictException);
  });
});
```

- [ ] **Step 2: 运行确认失败 → 实现 UserService → 运行确认通过**

```typescript
// backend/src/user/user.service.ts
@Injectable()
export class UserService {
  constructor(private prisma: PrismaService) {}

  async findAll(query: UserQueryDto) {
    const where: any = { deletedAt: null };
    if (query.role) where.role = query.role;
    if (query.search) {
      where.OR = [
        { username: { contains: query.search } },
        { nickname: { contains: query.search } },
        { studentId: { contains: query.search } },
      ];
    }
    const [data, total] = await Promise.all([
      this.prisma.user.findMany({
        where, skip: (query.page - 1) * query.limit, take: query.limit,
        select: { id: true, username: true, role: true, nickname: true, email: true, realName: true, studentId: true, department: true, major: true, grade: true, createdAt: true, updatedAt: true },
        orderBy: { createdAt: 'desc' },
      }),
      this.prisma.user.count({ where }),
    ]);
    return { data, total, page: query.page, limit: query.limit };
  }

  async findById(id: string) {
    const user = await this.prisma.user.findUnique({ where: { id } });
    if (!user) throw new NotFoundException('用户不存在');
    const { passwordHash, ...safe } = user;
    return safe;
  }

  async update(id: string, dto: UpdateUserDto) {
    const user = await this.prisma.user.findUnique({ where: { id } });
    if (!user) throw new NotFoundException('用户不存在');
    const { passwordHash, ...safe } = dto as any; // 禁止通过此接口修改密码
    return this.prisma.user.update({ where: { id }, data: safe, select: { id: true, username: true, role: true, nickname: true, updatedAt: true } });
  }

  async softDelete(id: string) {
    return this.prisma.user.update({ where: { id }, data: { deletedAt: new Date() }, select: { id: true, deletedAt: true } });
  }

  async bindPlatform(userId: string, dto: BindPlatformDto) {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) throw new NotFoundException('用户不存在');
    const existing = await this.prisma.platformAccount.findFirst({ where: { platform: dto.platform, platformUid: dto.platformUid } });
    if (existing) throw new ConflictException('该平台账号已被其他用户绑定');
    return this.prisma.platformAccount.create({ data: { userId, platform: dto.platform, platformUid: dto.platformUid, platformUsername: dto.platformUsername } });
  }

  async unbindPlatform(userId: string, platform: string) {
    await this.prisma.platformAccount.deleteMany({ where: { userId, platform: platform as any } });
    return { success: true };
  }
}
```

```bash
npx jest test/user.service.spec.ts --no-cache
# 预期: 全部 PASS
git commit -m "feat(user): add UserService with CRUD and platform binding"
```

---

## Task 4: UserController + E2E

- [ ] **Step 1: 写 E2E 测试** (含角色权限验证)
- [ ] **Step 2: 实现 UserController** (GET/PATCH/DELETE /users, GET /users/:id, POST/DELETE platform binding)
- [ ] **Step 3: 实现 RolesGuard 集成** (`@Roles('admin')` 装饰器)
- [ ] **Step 4: 运行全部测试确认通过 + 覆盖率**

```bash
npx jest --no-cache --config jest.config.ts
npm run test:cov
# 预期: 全部 PASS + 覆盖率 ≥ 90%
git commit -m "feat(user): add UserController with role-based access control"
```

---

## Phase 2 Gate

| 检查项 | 标准 | 命令 |
|--------|------|------|
| 注册 | 201 + token | `POST /api/auth/register` |
| 登录 | 201 + token | `POST /api/auth/login` |
| 认证 | 200 + user | `GET /api/auth/me` |
| 用户列表 | 200 + paginated | `GET /api/users` |
| 角色守卫 | 403 for non-admin | `GET /api/users` as user |
| 测试覆盖率 | ≥ 90% | `npm run test:cov` |
