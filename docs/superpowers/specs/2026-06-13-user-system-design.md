# §5 用户管理系统详细设计

> 版本: v1.0 | 日期: 2026-06-13 | 状态: 已批准
> 基于: `2026-06-13-acm-agent-design.md` §5 用户部分细化

---

## 1. 设计决策总览

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 认证方式 | JWT 无状态 | 适合单机部署，无 Redis 依赖 |
| 密码加密 | bcrypt (10 rounds) | 行业标准，抗彩虹表 |
| Token 过期 | Access 2h + Refresh 7d | 平衡安全性和用户体验 |
| 角色体系 | 3 级: user / observed / admin | 满足当前需求，可扩展 |
| 平台绑定 | 用户自主绑定 + 管理员代绑 | 灵活，支持批量导入 |

---

## 2. AuthModule

### 2.1 API 端点

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/auth/register` | 注册 | 无 |
| POST | `/api/auth/login` | 登录，返回 JWT | 无 |
| GET | `/api/auth/me` | 获取当前用户信息 | 需要 |
| POST | `/api/auth/refresh` | 刷新 Access Token | 需要 Refresh Token |

### 2.2 DTO 定义

```typescript
// 注册
class RegisterDto {
  @IsString() @MinLength(3) @MaxLength(50)
  username: string;

  @IsString() @MinLength(6)
  password: string;

  @IsOptional() @IsString()
  nickname?: string;

  @IsOptional() @IsEmail()
  email?: string;

  @IsOptional() @IsString()
  studentId?: string;
}

// 登录
class LoginDto {
  @IsString()
  username: string;

  @IsString()
  password: string;
}

// JWT Payload
interface JwtPayload {
  sub: string;      // user id
  username: string;
  role: UserRole;
  iat: number;
  exp: number;
}

// Token 响应
interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;  // 秒
  token_type: "Bearer";
}
```

### 2.3 认证流程

```
注册: POST /register → bcrypt(password) → 创建用户 → 返回 TokenResponse
登录: POST /login → 验证密码 → 生成 JWT → 返回 TokenResponse
认证: GET /me → Authorization: Bearer {token} → JwtStrategy 验证 → 返回用户信息
刷新: POST /refresh → 验证 Refresh Token → 生成新 Access Token → 返回 TokenResponse
```

### 2.4 守卫与装饰器

```typescript
// 角色守卫
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}
  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.get<UserRole[]>('roles', context.getHandler());
    if (!requiredRoles) return true;
    const { user } = context.switchToHttp().getRequest();
    return requiredRoles.includes(user.role);
  }
}

// 角色装饰器
@Roles(UserRole.ADMIN)
@UseGuards(JwtAuthGuard, RolesGuard)
```

---

## 3. UserModule

### 3.1 API 端点

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/users` | 用户列表（分页+搜索） | admin |
| GET | `/api/users/:id` | 用户详情 | self / admin |
| PATCH | `/api/users/:id` | 更新用户信息 | self / admin |
| DELETE | `/api/users/:id` | 软删除用户 | admin |
| POST | `/api/users/:id/platforms` | 绑定平台账号 | self / admin |
| DELETE | `/api/users/:id/platforms/:platform` | 解绑平台 | self / admin |

### 3.2 查询参数

```typescript
// GET /api/users
class UserQueryDto {
  @IsOptional() @IsInt() @Type(() => Number)
  page?: number = 1;

  @IsOptional() @IsInt() @Type(() => Number)
  limit?: number = 20;

  @IsOptional() @IsString()
  search?: string;  // 搜索 username / nickname / studentId

  @IsOptional() @IsEnum(UserRole)
  role?: UserRole;

  @IsOptional() @IsEnum(Platform)
  platform?: Platform;  // 筛选绑定了某平台的用户
}
```

### 3.3 平台绑定流程

```
POST /users/:id/platforms
Body: { platform: "luogu", platform_uid: "12345" }
     ↓
1. 验证用户存在
2. 调用对应爬虫 fetch_user_profile(platform_uid)
3. 提取 platform_username, raw_profile
4. 计算 normalized_rating
5. 创建/更新 PlatformAccount 记录
6. 返回绑定结果
```

### 3.4 normalized_rating 映射

```python
def normalize_rating(platform: str, raw_rating: int) -> int:
    """跨平台归一化到 0~3000 区间"""
    if platform == "codeforces":
        return raw_rating  # CF rating 本身就是 ~0~3500
    elif platform == "luogu":
        return int(raw_rating * 1.5)  # 咕值 0~2000 → 0~3000
    elif platform == "leetcode":
        # 力扣分 1400~2600 → 0~3000
        return int((raw_rating - 1400) * 2.5)
    elif platform == "nowcoder":
        return int(raw_rating * 0.6)  # 牛客分 0~5000 → 0~3000
    elif platform == "atcoder":
        return int(raw_rating * 1.2)  # AT rating 0~2800 → 0~3000
    return raw_rating
```

---

## 4. 错误处理

| 场景 | HTTP 状态码 | 错误消息 |
|------|-----------|---------|
| 用户名已存在 | 409 Conflict | "用户名已被注册" |
| 密码错误 | 401 Unauthorized | "用户名或密码错误" |
| 用户不存在 | 404 Not Found | "用户不存在" |
| Token 过期 | 401 Unauthorized | "Token 已过期，请重新登录" |
| 权限不足 | 403 Forbidden | "权限不足" |
| 平台账号已绑定 | 409 Conflict | "该平台账号已被其他用户绑定" |
| 平台账号验证失败 | 400 Bad Request | "无法验证平台账号，请检查 UID" |

---

## 5. 测试策略

| 测试类型 | 覆盖范围 |
|----------|---------|
| 单元测试 | AuthService (密码验证/JWT生成), UserService (CRUD), normalize_rating |
| 集成测试 | 完整注册→登录→认证流程, 平台绑定流程 |
| E2E 测试 | 角色权限验证, 分页查询 |
