# ACM Agent 语法范式参考

> 版本: v1.0 | 日期: 2026-06-13 | 基于行业最佳实践 + 相关项目调研
>
> 参考项目: ACManager (SDUST)、ICPC-Training-Summary、nestjs-boilerplate、NestJS 官方 Starter、MUI TypeScript Convention

---
---

## 目录

- [一、通用规则](#一通用规则)
- [二、TypeScript / NestJS](#二typescript--nestjs)
- [三、React / 前端](#三react--前端)
- [四、Python](#四python)
- [五、配置文件速查](#五配置文件速查)
- [六、Git 提交规范](#六git-提交规范)
- [七、禁止事项](#七禁止事项)

---
---

## 一、通用规则

### 1.1 命名约定速查

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名（TS/JS） | `kebab-case` | `user.controller.ts`, `auth.service.ts` |
| 文件名（Python） | `snake_case` | `profile_agent.py`, `rate_limiter.py` |
| 类名 | `PascalCase` | `UserController`, `AuthService` |
| 接口/类型 | `PascalCase` (无 `I` 前缀) | `UserProfile`, `CrawlResult` |
| 变量/函数 | `camelCase` | `getUserById()`, `accessToken` |
| 常量 | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT`, `DEFAULT_QPS` |
| 测试文件 | `*.spec.ts` / `test_*.py` | `auth.service.spec.ts`, `test_profile_agent.py` |
| 目录 | `kebab-case` (TS) / `snake_case` (Python) | `problem-pipeline/`, `llm/` |

### 1.2 缩进与空白

```
- 缩进: 2 空格 (TypeScript), 4 空格 (Python)
- 行宽: 120 字符 (TS), 100 字符 (Python)
- 行尾: LF (`\n`), 文件末尾保留一个空行
- 尾部空格: 全部清除
```

### 1.3 引号

```
- TypeScript: 单引号 `'`
- Python: 双引号 `"` (PEP 8 标准)
- JSON: 双引号 `"`
```

### 1.4 分号

```
- TypeScript: 必须 `;`
- Python: 禁止
```

---
---

## 二、TypeScript / NestJS

### 2.1 严格模式 (tsconfig.json)

```json
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  }
}
```

### 2.2 模块文件组织

```
src/
├── main.ts                            # 应用入口
├── app.module.ts                      # 根模块
├── common/                            # 全局通用层
│   ├── decorators/
│   │   ├── current-user.decorator.ts  # @CurrentUser()
│   │   └── roles.decorator.ts         # @Roles('admin')
│   ├── filters/
│   │   └── all-exceptions.filter.ts
│   ├── guards/
│   │   ├── jwt-auth.guard.ts
│   │   └── roles.guard.ts
│   ├── interceptors/
│   └── pipes/
├── config/                            # 配置模块
│   └── config.module.ts
├── prisma/                            # 数据库层 (全局)
│   ├── prisma.module.ts
│   └── prisma.service.ts
├── <module>/                           # 业务模块 (按 feature 组织)
│   ├── <module>.module.ts
│   ├── <module>.controller.ts
│   ├── <module>.service.ts
│   └── dto/
│       ├── create-<entity>.dto.ts
│       ├── update-<entity>.dto.ts
│       └── <entity>-query.dto.ts
└── test/
```

### 2.3 PrismaService (单例 + 全局)

```typescript
// src/common/prisma/prisma.service.ts
import { Injectable, OnModuleInit, OnModuleDestroy } from "@nestjs/common";
import { PrismaClient } from "@prisma/client";

@Injectable()
export class PrismaService
  extends PrismaClient
  implements OnModuleInit, OnModuleDestroy
{
  async onModuleInit() {
    await this.$connect();

    // 软删除中间件
    this.$use(async (params, next) => {
      const softDeleteModels = ["User", "Problem", "TrainingPlan", "Team"];

      if (softDeleteModels.includes(params.model ?? "")) {
        if (params.action === "findUnique" || params.action === "findFirst") {
          params.action = "findFirst";
          params.args.where = { ...params.args.where, deletedAt: null };
        }
        if (params.action === "findMany") {
          params.args.where = { ...params.args.where, deletedAt: null };
        }
      }
      return next(params);
    });
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
```

### 2.4 Controller 范式

```typescript
// src/user/user.controller.ts
import { Controller, Get, Post, Patch, Delete, Param, Body, Query, UseGuards } from "@nestjs/common";
import { ApiTags, ApiBearerAuth, ApiOperation } from "@nestjs/swagger";
import { JwtAuthGuard } from "../common/guards/jwt-auth.guard";
import { RolesGuard } from "../common/guards/roles.guard";
import { Roles } from "../common/decorators/roles.decorator";
import { CurrentUser } from "../common/decorators/current-user.decorator";
import { UserService } from "./user.service";
import { UserQueryDto, UpdateUserDto, BindPlatformDto } from "./dto";

@ApiTags("Users")
@Controller("api/users")
export class UserController {
  constructor(private readonly userService: UserService) {}

  @Get()
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles("admin")
  @ApiBearerAuth()
  @ApiOperation({ summary: "获取用户列表" })
  async findAll(@Query() query: UserQueryDto) {
    return this.userService.findAll(query);
  }

  @Get(":id")
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  async findById(@Param("id") id: string) {
    return this.userService.findById(id);
  }

  @Patch(":id")
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  async update(
    @Param("id") id: string,
    @Body() dto: UpdateUserDto,
    @CurrentUser() user: JwtPayload,
  ) {
    return this.userService.update(id, dto, user);
  }

  @Post(":id/platforms")
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  async bindPlatform(
    @Param("id") id: string,
    @Body() dto: BindPlatformDto,
  ) {
    return this.userService.bindPlatform(id, dto);
  }
}
```

### 2.5 Service 范式

```typescript
// src/user/user.service.ts
import { Injectable, NotFoundException, ConflictException } from "@nestjs/common";
import { PrismaService } from "../common/prisma/prisma.service";
import { UserQueryDto, UpdateUserDto, BindPlatformDto } from "./dto";

@Injectable()
export class UserService {
  constructor(private readonly prisma: PrismaService) {}

  async findAll(query: UserQueryDto) {
    // 构建 where 条件
    const where: Record<string, unknown> = {};
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
        where,
        skip: (query.page - 1) * query.limit,
        take: query.limit,
        select: USER_SAFE_SELECT,   // 排除 passwordHash
        orderBy: { createdAt: "desc" },
      }),
      this.prisma.user.count({ where }),
    ]);

    return { data, total, page: query.page, limit: query.limit };
  }

  async findById(id: string) {
    const user = await this.prisma.user.findUnique({
      where: { id },
      select: USER_SAFE_SELECT,
    });
    if (!user) {
      throw new NotFoundException("用户不存在");
    }
    return user;
  }

  async update(id: string, dto: UpdateUserDto, actor: JwtPayload) {
    const user = await this.prisma.user.findUnique({ where: { id } });
    if (!user) throw new NotFoundException("用户不存在");

    // 安全: 禁止通过此接口修改密码
    const { passwordHash, role, ...safeDto } = dto as Record<string, unknown>;

    // 非管理员不能修改其他人的信息
    if (actor.role !== "admin" && id !== actor.sub) {
      throw new ForbiddenException("权限不足");
    }

    return this.prisma.user.update({
      where: { id },
      data: { ...safeDto, updatedBy: actor.sub },
      select: USER_SAFE_SELECT,
    });
  }
}

// 安全 SELECT: 排除密码和软删除时间
const USER_SAFE_SELECT = {
  id: true, username: true, role: true, nickname: true, email: true,
  realName: true, studentId: true, department: true, major: true,
  grade: true, enrollmentYear: true, feishuOpenId: true, qqNumber: true,
  pushChannels: true, createdAt: true, updatedAt: true,
};
```

### 2.6 DTO 范式

```typescript
// src/user/dto/create-user.dto.ts
import { ApiProperty, ApiPropertyOptional } from "@nestjs/swagger";
import { IsString, IsEmail, IsOptional, MinLength, MaxLength, IsEnum } from "class-validator";
import { UserRole } from "@prisma/client";

export class CreateUserDto {
  @ApiProperty({ description: "用户名", minLength: 3, maxLength: 50, example: "zhangsan" })
  @IsString()
  @MinLength(3)
  @MaxLength(50)
  username: string;

  @ApiProperty({ description: "密码", minLength: 6, example: "password123" })
  @IsString()
  @MinLength(6)
  password: string;

  @ApiPropertyOptional({ description: "用户角色", enum: UserRole })
  @IsOptional()
  @IsEnum(UserRole)
  role?: UserRole;

  @ApiPropertyOptional({ description: "显示昵称" })
  @IsOptional()
  @IsString()
  @MaxLength(100)
  nickname?: string;

  @ApiPropertyOptional({ description: "邮箱" })
  @IsOptional()
  @IsEmail()
  email?: string;

  @ApiPropertyOptional({ description: "学号" })
  @IsOptional()
  @IsString()
  @MaxLength(30)
  studentId?: string;
}
```

```typescript
// src/user/dto/user-query.dto.ts
import { ApiPropertyOptional } from "@nestjs/swagger";
import { IsOptional, IsInt, IsString, IsEnum, Min, Max } from "class-validator";
import { Type } from "class-transformer";
import { UserRole } from "@prisma/client";

export class UserQueryDto {
  @ApiPropertyOptional({ default: 1 })
  @IsOptional()
  @IsInt()
  @Min(1)
  @Type(() => Number)
  page?: number = 1;

  @ApiPropertyOptional({ default: 20 })
  @IsOptional()
  @IsInt()
  @Min(1)
  @Max(100)
  @Type(() => Number)
  limit?: number = 20;

  @ApiPropertyOptional({ description: "搜索关键词" })
  @IsOptional()
  @IsString()
  search?: string;

  @ApiPropertyOptional({ enum: UserRole })
  @IsOptional()
  @IsEnum(UserRole)
  role?: UserRole;
}
```

### 2.7 异常处理范式

```typescript
// 推荐: 使用 NestJS 内置异常类
throw new NotFoundException("用户不存在");
throw new ConflictException("用户名已被注册");
throw new UnauthorizedException("用户名或密码错误");
throw new ForbiddenException("权限不足");
throw new BadRequestException("输入参数不合法");

// 不推荐: 自定义 HTTP 状态码
throw new HttpException("自定义错误", 418);  // 只在标准异常不够用时使用
```

### 2.8 依赖注入

```typescript
// ✅ 正确: readonly + 构造函数注入
@Injectable()
export class UserService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly logger: Logger,
  ) {}
}

// ❌ 错误: 属性注入
@Injectable()
export class UserService {
  @Inject(PrismaService)
  private prisma: PrismaService;    // 不要用属性注入
}
```

### 2.9 返回类型

```typescript
// ✅ Controller 方法显式声明返回类型
@Get()
async findAll(@Query() query: UserQueryDto): Promise<PaginatedResponse<UserDto>> {
  return this.userService.findAll(query);
}

// ✅ Service 方法显式声明返回类型
async findById(id: string): Promise<UserDto | null> {
  return this.prisma.user.findUnique({ where: { id } });
}

// ❌ 避免 any
function process(data: any): any { ... }   // 禁止
function process(data: unknown): Result { ... }  // 正确
```

---
---

## 三、React / 前端

### 3.1 项目结构 (Feature-Based)

```
src/
├── main.tsx                    # 入口
├── App.tsx                     # 根组件 (Router + Theme + Auth)
├── theme.ts                    # MUI MD3 主题配置
├── routes.tsx                  # 路由配置 (懒加载)
├── components/
│   ├── layout/                 # 布局组件
│   │   ├── AppLayout.tsx
│   │   ├── Sidebar.tsx
│   │   └── TopBar.tsx
│   ├── common/                 # 通用组件
│   │   ├── DataTable.tsx
│   │   ├── SearchInput.tsx
│   │   ├── FilterPanel.tsx
│   │   ├── TagBadge.tsx
│   │   ├── DifficultyBadge.tsx
│   │   ├── VerdictBadge.tsx
│   │   ├── LoadingSpinner.tsx
│   │   ├── EmptyState.tsx
│   │   └── ConfirmDialog.tsx
│   ├── charts/                 # 图表组件
│   │   ├── SkillRadar.tsx
│   │   ├── DailyTrend.tsx
│   │   ├── DifficultyPie.tsx
│   │   ├── TagBar.tsx
│   │   └── Heatmap.tsx
│   └── business/               # 业务组件
│       ├── ProblemCard.tsx
│       ├── ProfileOverview.tsx
│       ├── TrainingWeekView.tsx
│       ├── MatchRecommendation.tsx
│       └── RankingTable.tsx
├── pages/                      # 页面组件
│   ├── Login.tsx
│   ├── Register.tsx
│   ├── Dashboard.tsx
│   ├── Problems.tsx
│   ├── ProblemDetail.tsx
│   ├── Records.tsx
│   ├── Profile.tsx
│   ├── Training.tsx
│   ├── Matching.tsx
│   ├── Teams.tsx
│   ├── Ranking.tsx
│   ├── Settings.tsx
│   └── admin/
│       ├── UserManagement.tsx
│       ├── CrawlerManagement.tsx
│       └── BotConfig.tsx
├── hooks/                      # 自定义 Hooks
│   ├── useAuth.ts
│   ├── useApi.ts
│   ├── usePagination.ts
│   └── useDebounce.ts
├── services/                   # API 调用层
│   ├── api.ts                  # axios 实例 + 拦截器
│   ├── auth.ts
│   ├── users.ts
│   ├── problems.ts
│   └── records.ts
├── types/                      # TypeScript 类型定义
│   ├── user.ts
│   ├── problem.ts
│   ├── record.ts
│   └── api.ts                  # 通用 API 响应类型
└── test/                       # 测试
    ├── setup.ts
    ├── components/
    └── pages/
```

### 3.2 组件定义范式

```typescript
// ✅ 推荐: 命名函数组件 + Props 接口
import { type FC } from "react";

interface SkillRadarProps {
  data: { tag: string; score: number }[];
  maxValue?: number;
  size?: number;
  color?: string;
}

export function SkillRadar({
  data,
  maxValue = 1,
  size = 300,
  color,
}: SkillRadarProps) {
  return (
    <RadarChart width={size} height={size} data={data}>
      {/* ... */}
    </RadarChart>
  );
}

// ✅ 也接受: 带 children 时用 FC
interface AppLayoutProps {
  children: React.ReactNode;
}

export const AppLayout: FC<AppLayoutProps> = ({ children }) => {
  return (
    <Box sx={{ display: "flex" }}>
      <Sidebar />
      <Box component="main">{children}</Box>
    </Box>
  );
};

// ❌ 避免: React.FC 类型问题 (隐式 children)
// 只在明确需要 children 时使用 FC
```

### 3.3 Hook 范式

```typescript
// ✅ 自定义 hook: use 前缀 + 返回对象
export function useAuth() {
  const [user, setUser] = useState<UserDto | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.post("/api/auth/login", { username, password });
    localStorage.setItem("access_token", res.data.access_token);
    localStorage.setItem("refresh_token", res.data.refresh_token);
    setUser(res.data.user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
  }, []);

  return { user, loading, login, logout, isAuthenticated: !!user };
}

// ✅ 数据获取 hook: useApi 封装
export function useApi<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<T>(url);
      setData(res.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => { refetch(); }, [refetch]);

  return { data, loading, error, refetch };
}
```

### 3.4 API 调用范式

```typescript
// src/services/api.ts  — axios 实例
import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 10_000,
  headers: { "Content-Type": "application/json" },
});

// 请求拦截器: 注入 JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器: 自动刷新 token
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        try {
          const { data } = await axios.post("/api/auth/refresh", { refresh_token: refresh });
          localStorage.setItem("access_token", data.access_token);
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return api(error.config);
        } catch {
          localStorage.clear();
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  },
);

export default api;
```

### 3.5 TypeScript 类型文件

```typescript
// src/types/api.ts  — 通用 API 响应类型
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
}

export interface ApiError {
  statusCode: number;
  message: string;
  timestamp: string;
}

// src/types/user.ts
import type { UserRole } from "@prisma/client";

export interface UserDto {
  id: string;
  username: string;
  role: UserRole;
  nickname?: string;
  email?: string;
  realName?: string;
  studentId?: string;
  createdAt: string;
  updatedAt: string;
}
```

### 3.6 组件导出规范

```typescript
// ✅ 推荐: 命名导出
export function DataTable<T>({ columns, data, loading }: DataTableProps<T>) { ... }

// ❌ 避免: 默认导出 (影响 tree-shaking 和 IDE 自动导入)
export default function DataTable() { ... }
```

---
---

## 四、Python

### 4.1 文件结构

```
python/
├── crawlers/
│   ├── __init__.py
│   ├── base.py            # 抽象基类
│   ├── luogu.py
│   ├── leetcode.py
│   ├── nowcoder.py
│   ├── codeforces.py
│   ├── atcoder.py
│   ├── importer.py
│   └── test/
│       ├── __init__.py
│       └── test_base.py
├── llm/
│   ├── __init__.py
│   ├── normalizer.py
│   ├── summarizer.py
│   ├── embedder.py
│   ├── pipeline.py
│   └── test/
├── agents/
│   ├── __init__.py
│   ├── formulas.py
│   ├── taxonomy.py
│   ├── profile_agent.py
│   ├── training_agent.py
│   ├── spaced_repetition.py
│   └── test/
└── scheduler/
    └── jobs.py
```

### 4.2 类定义范式

```python
"""Base crawler module for ACM platform data fetching."""

import json
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from DrissionPage import ChromiumPage, SessionPage

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """Result container for crawl operations.

    Attributes:
        success: Whether the crawl succeeded.
        data: Parsed response data (dict or list).
        error: Error message if success is False.
        source: Data source — "http" or "browser".
        retry_count: Number of retries attempted.
    """
    success: bool
    data: dict | list | None = None
    error: str | None = None
    source: str = "http"
    retry_count: int = 0


class RateLimiter:
    """Fixed-QPS rate limiter with random jitter.

    Args:
        qps: Maximum requests per second.
        jitter: Jitter ratio (0~1). 0 = no jitter.
    """

    def __init__(self, qps: float, jitter: float = 0.3) -> None:
        self.interval = 1.0 / max(qps, 0.1)
        self.jitter = jitter
        self._last_time = 0.0

    def wait(self) -> None:
        """Block until the next request slot."""
        now = time.monotonic()
        elapsed = now - self._last_time
        actual = self.interval * (1 + random.uniform(-self.jitter, self.jitter))
        if elapsed < actual:
            time.sleep(actual - elapsed)
        self._last_time = time.monotonic()


class BaseCrawler(ABC):
    """Abstract base for platform-specific crawlers.

    Subclasses must define:
        PLATFORM: Platform identifier string.
        _default_qps(): Default QPS limit override.
        fetch_user_profile(uid): Crawl user profile.
        fetch_user_records(uid, since): Crawl submission records.
        fetch_problem(source_id): Crawl problem details.
        fetch_problems_by_tag(tag, count): Batch fetch by tag.
    """

    PLATFORM: str

    def __init__(self, data_dir: str = "data/raw", headless: bool = True) -> None:
        self.data_dir = Path(data_dir) / self.PLATFORM
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.http = SessionPage()
        self._browser: Optional[ChromiumPage] = None
        self.headless = headless
        self.limiter = RateLimiter(qps=self._default_qps())

    def _default_qps(self) -> float:
        return 1.0

    def _get_browser(self) -> ChromiumPage:
        """Lazy-init browser instance."""
        if self._browser is None:
            self._browser = ChromiumPage(headless=self.headless)
        return self._browser

    def fetch_with_fallback(self, url: str, **kwargs: dict) -> CrawlResult:
        """Try HTTP first, fall back to browser on failure."""
        result = self._http_request(url, **kwargs)
        if result.success:
            return result
        logger.warning("HTTP failed for %s: %s, falling back to browser", url, result.error)
        return self._browser_request(url)

    @abstractmethod
    def fetch_user_profile(self, platform_uid: str) -> CrawlResult: ...
    @abstractmethod
    def fetch_user_records(self, platform_uid: str, since: str | None = None) -> CrawlResult: ...
    @abstractmethod
    def fetch_problem(self, source_id: str) -> CrawlResult: ...
    @abstractmethod
    def fetch_problems_by_tag(self, tag: str, count: int = 50) -> CrawlResult: ...
```

### 4.3 函数定义范式

```python
"""Pure Python formula functions for user profile calculation."""

import math
import logging
from collections import defaultdict
from typing import TypedDict

import numpy as np

logger = logging.getLogger(__name__)


class ProfileRecord(TypedDict, total=False):
    """Single practice record for profile calculation."""
    verdict: str
    difficulty_normalized: float
    tags_normalized: list[str]
    days_ago: int
    problem_id: str


class DailyStat(TypedDict):
    """Daily aggregated statistics."""
    ac_count: int


# ---- Dimension 2: Tag Proficiency ----

def calc_proficiency(
    ac_count: int,
    total_count: int,
    avg_difficulty: float,
    days_since_last: int,
) -> float:
    """Calculate proficiency score for a single tag.

    Formula:
        proficiency = 0.40 * ac_factor + 0.30 * diff_factor
                    + 0.20 * vol_factor + 0.10 * recency_factor

    Args:
        ac_count: Number of AC submissions for this tag.
        total_count: Total submissions for this tag.
        avg_difficulty: Average difficulty of AC problems (1~10).
        days_since_last: Days since last AC on this tag.

    Returns:
        Proficiency score in [0, 1].
    """
    if ac_count == 0:
        return 0.0

    # AC rate factor: sigmoid centered at 0.5
    ac_rate = ac_count / max(total_count, 1)
    ac_factor = 1.0 / (1.0 + math.exp(-10 * (ac_rate - 0.5)))

    # Difficulty factor: linear normalization
    diff_factor = min(avg_difficulty / 10.0, 1.0)

    # Volume factor: log decay, saturates at ~30 problems
    vol_factor = min(math.log(1 + ac_count) / math.log(31), 1.0)

    # Recency factor: exponential decay, 30-day half-life
    recency_factor = math.exp(-0.023 * days_since_last)

    proficiency = (
        0.40 * ac_factor
        + 0.30 * diff_factor
        + 0.20 * vol_factor
        + 0.10 * recency_factor
    )
    return round(proficiency, 3)
```

### 4.4 测试范式

```python
"""Tests for formula functions."""

import math

import pytest

from agents.formulas import calc_ceiling, calc_efficiency, calc_proficiency, classify_style


class TestCalcProficiency:
    """Tests for tag proficiency calculation."""

    def test_perfect_mastery(self) -> None:
        """Perfect mastery: AC=100, total=100, diff=10, recency=0."""
        result = calc_proficiency(
            ac_count=100, total_count=100,
            avg_difficulty=10.0, days_since_last=0,
        )
        assert 0.85 <= result <= 1.0, f"Expected 0.85~1.0, got {result}"

    def test_beginner(self) -> None:
        """Beginner: few AC, low difficulty, stale."""
        result = calc_proficiency(
            ac_count=1, total_count=5,
            avg_difficulty=2.0, days_since_last=60,
        )
        assert result < 0.5, f"Expected <0.5, got {result}"

    def test_zero_ac_returns_zero(self) -> None:
        """Edge case: no AC at all."""
        result = calc_proficiency(
            ac_count=0, total_count=10,
            avg_difficulty=5.0, days_since_last=0,
        )
        assert result == 0.0

    @pytest.mark.parametrize("ac_count,total_count,avg_diff,days,expected_range", [
        (10, 10, 8.0, 0, (0.8, 1.0)),     # Perfect
        (5, 10, 5.0, 30, (0.3, 0.7)),      # Medium
        (1, 1, 1.0, 90, (0.0, 0.3)),        # Barely started
    ])
    def test_proficiency_range(
        self, ac_count: int, total_count: int,
        avg_diff: float, days: int, expected_range: tuple,
    ) -> None:
        """Parameterized: proficiency stays within expected bounds."""
        result = calc_proficiency(ac_count, total_count, avg_diff, days)
        assert expected_range[0] <= result <= expected_range[1]
```

### 4.5 Python CLI 入口范式

```python
#!/usr/bin/env python3
"""Luogu platform crawler CLI."""

import argparse
import json
import sys

from crawlers.base import CrawlerExecutor
from crawlers.luogu import LuoguCrawler


def main() -> None:
    """Dual-mode entry: CLI args or JSON from NestJS via --input."""
    parser = argparse.ArgumentParser(description="洛谷爬虫")
    parser.add_argument(
        "--action",
        choices=["fetch_problems", "fetch_user", "fetch_records", "import"],
        required=True,
    )
    parser.add_argument("--uid", help="用户 UID")
    parser.add_argument("--tags", help="题目标签（逗号分隔）")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--input", help="JSON 输入 (NestJS 调用模式)")

    args = parser.parse_args()

    # Mode 1: NestJS calls via --input JSON
    params: dict = json.loads(args.input) if args.input else vars(args)

    crawler = LuoguCrawler()
    executor = CrawlerExecutor(crawler)

    if params["action"] == "fetch_problems":
        result = executor.execute("fetch_problems_by_tag", params.get("tags", ""), params.get("count", 50))
    elif params["action"] == "fetch_user":
        result = executor.execute("fetch_user_profile", params["uid"])
    elif params["action"] == "fetch_records":
        result = executor.execute("fetch_user_records", params["uid"])
    else:
        result = None

    # Output JSON to stdout for NestJS to consume
    output = {"success": result.success, "data": result.data, "error": result.error} if result else {"success": False, "error": "unknown action"}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

---
---

## 五、配置文件速查

### 5.1 ESLint (backend/.eslintrc.js)

```javascript
module.exports = {
  parser: "@typescript-eslint/parser",
  parserOptions: { project: "tsconfig.json", tsconfigRootDir: __dirname },
  plugins: ["@typescript-eslint"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/strict-type-checked",
    "plugin:@typescript-eslint/stylistic-type-checked",
    "prettier",
  ],
  rules: {
    "@typescript-eslint/no-explicit-any": "error",
    "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    "@typescript-eslint/explicit-function-return-type": "error",
    "@typescript-eslint/naming-convention": [
      "error",
      { selector: "class", format: ["PascalCase"] },
      { selector: "interface", format: ["PascalCase"] },
      { selector: "variable", format: ["camelCase", "UPPER_CASE"] },
      { selector: "function", format: ["camelCase"] },
    ],
    "eqeqeq": "error",
    "curly": "error",
    "no-console": "warn",
    "prefer-const": "error",
  },
};
```

### 5.2 Prettier (.prettierrc)

```json
{
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 120,
  "tabWidth": 2,
  "semi": true,
  "bracketSpacing": true,
  "arrowParens": "always",
  "endOfLine": "lf"
}
```

### 5.3 Python (pyproject.toml)

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.pytest.ini_options]
testpaths = ["crawlers/test", "llm/test", "agents/test"]
pythonpath = ["."]

[tool.coverage.run]
source = ["crawlers", "llm", "agents"]
omit = ["*/test/*"]

[tool.coverage.report]
fail_under = 90
exclude_also = ["def __repr__", "if TYPE_CHECKING:", "raise NotImplementedError"]
```

---
---

## 六、Git 提交规范

### 6.1 Commit Message 格式

```
<type>(<scope>): <description>
```

| type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 bug |
| `refactor` | 重构（无功能变化） |
| `test` | 测试 |
| `docs` | 文档 |
| `chore` | 构建/工具链 |

### 6.2 示例

```
feat(db): add user domain tables and soft delete middleware
test(auth): add AuthService unit tests with 95% coverage
fix(crawler): handle CF API rate limit 429 with exponential backoff
refactor(agents): extract 6-dimension formulas to pure functions
```

### 6.3 提交粒度

- 每 commit 不超过 3 个文件
- 先 `npm run test:cov` / `pytest --cov` 确认通过再提交
- 禁止 `git add -A` 提交 (按文件精挑)

---
---

## 七、禁止事项

### 7.1 通用

```
❌ 硬编码密钥 / API Key
❌ console.log 提交到生产代码 (前端)
❌ print() 提交到生产代码 (Python, 用 logging)
❌ 注释掉的代码块 (删掉，git 历史可回溯)
❌ TODO/FIXME 无 issue 编号
❌ 裸 any 类型 (TypeScript)
❌ 静默吞异常 (至少 log.warning)
```

### 7.2 NestJS

```
❌ 在 Controller 里直接操作 Prisma (必须通过 Service)
❌ 在 DTO 里放业务逻辑
❌ 在 Service 里直接返回 Prisma 类型给 Controller
❌ 属性注入 (@Inject 在 property 上)
❌ 硬编码 HTTP 状态码 (用 HttpException 子类)
```

### 7.3 React

```
❌ React.FC 无 children 时 (隐式 children 类型问题)
❌ 在组件内定义组件 (每次渲染重建)
❌ 在 render 中调用 setState (无限循环)
❌ useEffect 缺少依赖数组
❌ 使用 index 作为 key (列表会变动时)
```

### 7.4 Python

```
❌ mutable defaults (def foo(x=[]): ...)
❌ 裸 except: (至少 except Exception:)
❌ from module import * (污染命名空间)
❌ 类属性 mutable (用 __init__ 初始化)
❌ f-string 中执行复杂表达式 (提前计算)
```

---
---

*参考: [NestJS Official](https://docs.nestjs.com/), [MUI TypeScript Convention](https://github.com/mui/material-ui/blob/master/TYPESCRIPT_CONVENTION.md), PEP 8, ACManager (SDUST)*
