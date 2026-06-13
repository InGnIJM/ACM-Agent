# Phase 1: 数据库基础设施 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 NestJS + Prisma + PostgreSQL + PGVector 基础设施，创建全部 12 张表，90% 测试覆盖率通过后进入 Phase 2。

**Architecture:** NestJS 项目脚手架 + Prisma Schema-first + Docker Compose 本地 PostgreSQL。测试用 Testcontainers 自动启动临时 PG 实例。

**Tech Stack:** NestJS 10, Prisma 5, PostgreSQL 16, PGVector, Jest, Testcontainers

**Phase Gate:** `npm run test:cov` — 语句覆盖率 ≥ 90%，分支覆盖率 ≥ 85%，全部测试通过

---

## 文件结构

```
acm-agent/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── nest-cli.json
│   ├── jest.config.ts
│   ├── src/
│   │   ├── main.ts
│   │   ├── app.module.ts
│   │   ├── common/
│   │   │   ├── prisma/
│   │   │   │   ├── prisma.module.ts
│   │   │   │   └── prisma.service.ts
│   │   │   └── filters/
│   │   │       └── all-exceptions.filter.ts
│   │   └── health/
│   │       ├── health.module.ts
│   │       ├── health.controller.ts
│   │       └── health.service.ts
│   ├── prisma/
│   │   ├── schema.prisma
│   │   ├── seed.ts
│   │   └── vector-indexes.sql
│   └── test/
│       ├── prisma.service.spec.ts
│       ├── seed.spec.ts
│       ├── health.service.spec.ts
│       └── jest-e2e.json
├── python/
│   └── requirements.txt
└── docs/
```

---

## Task 1: 项目脚手架

**Files:**
- Create: `backend/package.json`
- Create: `backend/tsconfig.json`
- Create: `backend/nest-cli.json`
- Create: `backend/jest.config.ts`
- Create: `backend/src/main.ts`
- Create: `backend/src/app.module.ts`
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: 初始化 NestJS 项目**

```bash
cd E:/code/ACM-Agent
npm init -y
npm i -D @nestjs/cli
npx @nestjs new backend --package-manager npm --skip-git
cd backend
```

- [ ] **Step 2: 安装核心依赖**

```bash
cd E:/code/ACM-Agent/backend
npm i @nestjs/config @nestjs/swagger @prisma/client class-validator class-transformer
npm i -D prisma @types/node @types/jest ts-jest
```

- [ ] **Step 3: 创建 Prisma schema**

```bash
cd E:/code/ACM-Agent/backend
npx prisma init
```

- [ ] **Step 4: 创建 docker-compose.yml**

```yaml
# E:/code/ACM-Agent/docker-compose.yml
version: "3.8"

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: acm-postgres
    environment:
      POSTGRES_DB: acm_agent
      POSTGRES_USER: acm
      POSTGRES_PASSWORD: ${DB_PASSWORD:-devpassword}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U acm"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

- [ ] **Step 5: 创建 .env.example**

```bash
# E:/code/ACM-Agent/.env.example
DATABASE_URL=postgresql://acm:devpassword@localhost:5432/acm_agent
JWT_SECRET=change-me-to-32-chars-minimum
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=sk-xxx
```

- [ ] **Step 6: 验证项目启动**

```bash
cd E:/code/ACM-Agent/backend
npm run start:dev
# 预期: NestJS 启动成功，监听 3000 端口
curl http://localhost:3000
# 预期: 返回 "Hello World!"
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: initialize NestJS project with Docker Compose"
```

---

## Task 2: Prisma Schema — 枚举与用户域

**Files:**
- Modify: `backend/prisma/schema.prisma`
- Test: `backend/test/prisma.service.spec.ts`

- [ ] **Step 1: 写测试 — Prisma 连接测试**

```typescript
// backend/test/prisma.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { PrismaService } from '../src/common/prisma/prisma.service';

describe('PrismaService', () => {
  let service: PrismaService;

  beforeEach(async () => {
    service = new PrismaService();
  });

  afterEach(async () => {
    await service.$disconnect();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('should connect to database', async () => {
    const result = await service.$queryRaw`SELECT 1 as num`;
    expect(result).toEqual([{ num: 1 }]);
  });

  it('should have all enums defined', async () => {
    // 验证枚举类型存在
    const result = await service.$queryRaw`
      SELECT typname FROM pg_type
      WHERE typname IN ('UserRole','Platform','Verdict','TrainingPlanStatus','TeamStatus','BotChannel','PushMessageType','PushStatus')
    `;
    const names = (result as any[]).map(r => r.typname);
    expect(names).toHaveLength(8);
  });

  it('should have users table', async () => {
    const result = await service.$queryRaw`
      SELECT table_name FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'users'
    `;
    expect(result).toHaveLength(1);
  });

  it('should have platform_accounts table', async () => {
    const result = await service.$queryRaw`
      SELECT table_name FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'platform_accounts'
    `;
    expect(result).toHaveLength(1);
  });

  it('should have user_daily_stats table', async () => {
    const result = await service.$queryRaw`
      SELECT table_name FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'user_daily_stats'
    `;
    expect(result).toHaveLength(1);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/code/ACM-Agent/backend
npx jest test/prisma.service.spec.ts --no-cache
# 预期: FAIL — PrismaService 不存在，schema 未定义
```

- [ ] **Step 3: 写 Prisma schema — 枚举 + 用户域**

```prisma
// backend/prisma/schema.prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

enum UserRole { user; observed; admin }
enum Platform { luogu; leetcode; nowcoder; codeforces; atcoder }
enum Verdict { OK; WA; TLE; MLE; RE; CE; OLE; SE; OTHER }
enum TrainingPlanStatus { active; completed; abandoned }
enum TeamStatus { active; archived }
enum BotChannel { feishu; qq }
enum PushMessageType { daily_report; ranking; weekly_report; alert }
enum PushStatus { sent; failed }

model User {
  id             String     @id @default(uuid()) @db.Uuid
  username       String     @unique @db.VarChar(50)
  passwordHash   String     @map("password_hash") @db.VarChar(255)
  role           UserRole   @default(user)
  nickname       String?    @db.VarChar(100)
  email          String?    @unique @db.VarChar(200)
  realName       String?    @map("real_name") @db.VarChar(50)
  studentId      String?    @map("student_id") @db.VarChar(30)
  department     String?    @db.VarChar(100)
  major          String?    @db.VarChar(100)
  className      String?    @map("class_name") @db.VarChar(50)
  grade          String?    @db.VarChar(10)
  enrollmentYear Int?       @map("enrollment_year")
  feishuOpenId   String?    @map("feishu_open_id") @db.VarChar(100)
  qqNumber       String?    @map("qq_number") @db.VarChar(20)
  pushChannels   Json?      @default("{}") @map("push_channels")
  createdAt      DateTime   @default(now()) @map("created_at")
  updatedAt      DateTime   @updatedAt @map("updated_at")
  deletedAt      DateTime?  @map("deleted_at")
  createdBy      String?    @map("created_by") @db.Uuid
  updatedBy      String?    @map("updated_by") @db.Uuid

  platformAccounts PlatformAccount[]
  dailyStats       UserDailyStat[]
  practiceRecords  PracticeRecord[]
  profile          UserProfile?
  trainingPlans    TrainingPlan[]
  teamMembers      TeamMember[]
  botConfigs       BotConfig[]
  createdTeams     Team[]           @relation("TeamCreator")

  @@index([role], map: "idx_users_role")
  @@index([studentId], map: "idx_users_student_id")
  @@map("users")
}

model PlatformAccount {
  id                 String    @id @default(uuid()) @db.Uuid
  userId             String    @map("user_id") @db.Uuid
  platform           Platform
  platformUid        String    @map("platform_uid") @db.VarChar(100)
  platformUsername   String    @map("platform_username") @db.VarChar(100)
  rawProfile         Json?     @map("raw_profile")
  normalizedRating   Int?      @map("normalized_rating")
  lastSyncedAt       DateTime? @map("last_synced_at")
  isActive           Boolean   @default(true) @map("is_active")
  createdAt          DateTime  @default(now()) @map("created_at")
  updatedAt          DateTime  @updatedAt @map("updated_at")
  deletedAt          DateTime? @map("deleted_at")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([userId, platform], map: "uq_platform_accounts_user_platform")
  @@index([platform, platformUid], map: "idx_platform_accounts_lookup")
  @@map("platform_accounts")
}

model UserDailyStat {
  id                 String    @id @default(uuid()) @db.Uuid
  userId             String    @map("user_id") @db.Uuid
  platform           Platform
  statDate           DateTime  @map("stat_date") @db.Date
  submitCount        Int       @default(0) @map("submit_count")
  acCount            Int       @default(0) @map("ac_count")
  waCount            Int       @default(0) @map("wa_count")
  tleCount           Int       @default(0) @map("tle_count")
  otherCount         Int       @default(0) @map("other_count")
  newProblemsSolved  Int       @default(0) @map("new_problems_solved")
  hardestDifficulty  Float?    @map("hardest_difficulty")
  avgDifficulty      Float?    @map("avg_difficulty")
  activeDurationMin  Int?      @map("active_duration_min")
  primaryLanguage    String?   @map("primary_language") @db.VarChar(20)
  detail             Json?
  createdAt          DateTime  @default(now()) @map("created_at")
  updatedAt          DateTime  @updatedAt @map("updated_at")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([userId, platform, statDate], map: "uq_user_daily_stats_user_platform_date")
  @@index([statDate], map: "idx_user_daily_stats_date")
  @@map("user_daily_stats")
}
```

- [ ] **Step 4: 创建 PrismaService**

```typescript
// backend/src/common/prisma/prisma.service.ts
import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
```

```typescript
// backend/src/common/prisma/prisma.module.ts
import { Global, Module } from '@nestjs/common';
import { PrismaService } from './prisma.service';

@Global()
@Module({
  providers: [PrismaService],
  exports: [PrismaService],
})
export class PrismaModule {}
```

- [ ] **Step 5: 启动 PG + 执行迁移**

```bash
cd E:/code/ACM-Agent
docker compose up -d postgres
# 等待 PG 就绪
docker compose exec postgres pg_isready

cd backend
cp ../.env.example .env
npx prisma migrate dev --name init_user_domain
```

- [ ] **Step 6: 运行测试**

```bash
cd E:/code/ACM-Agent/backend
npx jest test/prisma.service.spec.ts --no-cache
# 预期: 全部 PASS
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(db): add enums and user domain tables (users, platform_accounts, user_daily_stats)"
```

---

## Task 3: Prisma Schema — 题库域 + 记录画像域 + 匹配推送域

**Files:**
- Modify: `backend/prisma/schema.prisma`
- Test: `backend/test/prisma.service.spec.ts` (扩展)

- [ ] **Step 1: 写测试 — 验证全部 12 张表存在**

```typescript
// 追加到 backend/test/prisma.service.spec.ts
const ALL_TABLES = [
  'users', 'platform_accounts', 'user_daily_stats',
  'problems', 'problem_solutions',
  'practice_records', 'user_profiles', 'training_plans',
  'teams', 'team_members', 'bot_configs', 'push_logs',
];

describe('All 12 tables exist', () => {
  ALL_TABLES.forEach(table => {
    it(`should have ${table} table`, async () => {
      const result = await service.$queryRawUnsafe(
        `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = $1`,
        table
      );
      expect(result).toHaveLength(1);
    });
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
npx jest test/prisma.service.spec.ts --no-cache -t "All 12 tables"
# 预期: FAIL — problems 等表不存在
```

- [ ] **Step 3: 追加题库域 + 记录画像域 + 匹配推送域到 schema.prisma**

```prisma
// 追加到 backend/prisma/schema.prisma

// ===== 题库域 =====
model Problem {
  id                   String   @id @default(uuid()) @db.Uuid
  sourcePlatform       Platform @map("source_platform")
  sourceId             String   @map("source_id") @db.VarChar(50)
  sourceUrl            String?  @map("source_url") @db.VarChar(500)
  title                String   @db.VarChar(300)
  difficultyRaw        String?  @map("difficulty_raw") @db.VarChar(50)
  difficultyNormalized Float    @map("difficulty_normalized")
  tagsNormalized       String[] @map("tags_normalized")
  tagsPlatform         Json?    @map("tags_platform")
  rawDetail            Json?    @map("raw_detail")
  fullContent          String?  @map("full_content") @db.Text
  solutionSummary      String?  @map("solution_summary") @db.Text
  vectorEmbedding      Unsupported("vector(1536)")? @map("vector_embedding")
  contentVector        Unsupported("vector(1536)")? @map("content_vector")
  createdAt            DateTime @default(now()) @map("created_at")
  updatedAt            DateTime @updatedAt @map("updated_at")
  deletedAt            DateTime? @map("deleted_at")

  solutions       ProblemSolution[]
  practiceRecords PracticeRecord[]

  @@unique([sourcePlatform, sourceId], map: "uq_problems_platform_source")
  @@index([difficultyNormalized], map: "idx_problems_difficulty")
  @@index([tagsNormalized], map: "idx_problems_tags", type: Gin)
  @@map("problems")
}

model ProblemSolution {
  id               String   @id @default(uuid()) @db.Uuid
  problemId        String   @map("problem_id") @db.Uuid
  solutionIndex    Int      @map("solution_index")
  content          String   @db.Text
  author           String?  @db.VarChar(100)
  sourceUrl        String?  @map("source_url") @db.VarChar(500)
  vectorEmbedding  Unsupported("vector(1536)")? @map("vector_embedding")
  createdAt        DateTime @default(now()) @map("created_at")
  updatedAt        DateTime @updatedAt @map("updated_at")
  deletedAt        DateTime? @map("deleted_at")

  problem Problem @relation(fields: [problemId], references: [id], onDelete: Cascade)

  @@unique([problemId, solutionIndex], map: "uq_problem_solutions_idx")
  @@map("problem_solutions")
}

// ===== 记录画像域 =====
model PracticeRecord {
  id                    String    @id @default(uuid()) @db.Uuid
  platform              Platform
  userId                String    @map("user_id") @db.Uuid
  problemId             String    @map("problem_id") @db.Uuid
  platformSubmissionId  String    @map("platform_submission_id") @db.VarChar(100)
  submitTime            DateTime  @map("submit_time")
  verdict               Verdict
  verdictRaw            String?   @map("verdict_raw") @db.VarChar(100)
  language              String?   @db.VarChar(30)
  runtimeMs             Int?      @map("runtime_ms")
  memoryKb              Int?      @map("memory_kb")
  code                  String?   @db.Text
  rawDetail             Json?     @map("raw_detail")
  createdAt             DateTime  @default(now()) @map("created_at")
  updatedAt             DateTime  @updatedAt @map("updated_at")

  user    User    @relation(fields: [userId], references: [id], onDelete: Cascade)
  problem Problem @relation(fields: [problemId], references: [id], onDelete: Cascade)

  @@unique([platform, platformSubmissionId], map: "uq_practice_records_platform_sub")
  @@index([userId, submitTime], map: "idx_practice_records_user_time")
  @@index([userId, verdict], map: "idx_practice_records_user_verdict")
  @@index([problemId], map: "idx_practice_records_problem")
  @@map("practice_records")
}

model UserProfile {
  id                      String   @id @default(uuid()) @db.Uuid
  userId                  String   @unique @map("user_id") @db.Uuid
  generatedAt             DateTime @map("generated_at")
  overallScore            Float    @map("overall_score")
  coverage                Float    @default(0)
  categoryCoverage        Json?    @map("category_coverage")
  ceiling                 Float    @default(0) @map("ceiling")
  ceilingLevel            String?  @map("ceiling_level") @db.VarChar(20)
  efficiency              Float    @default(0)
  firstAcRate             Float    @default(0) @map("first_ac_rate")
  avgRetries              Float    @default(0) @map("avg_retries")
  style                   String?  @db.VarChar(20)
  momentum                Float    @default(0)
  trendLabel              String?  @map("trend_label") @db.VarChar(20)
  overallStats            Json?    @map("overall_stats")
  difficultyDistribution  Json?    @map("difficulty_distribution")
  platformBreakdown       Json?    @map("platform_breakdown")
  tagProficiency          Json?    @map("tag_proficiency")
  strengths               Json?
  weaknesses              Json?
  skillRadar              Json?    @map("skill_radar")
  summaryText             String?  @map("summary_text") @db.Text
  version                 Int      @default(1)
  createdAt               DateTime @default(now()) @map("created_at")
  updatedAt               DateTime @updatedAt @map("updated_at")

  user          User          @relation(fields: [userId], references: [id], onDelete: Cascade)
  trainingPlans TrainingPlan[]

  @@map("user_profiles")
}

model TrainingPlan {
  id               String             @id @default(uuid()) @db.Uuid
  userId           String             @map("user_id") @db.Uuid
  profileId        String             @map("profile_id") @db.Uuid
  phase            String             @db.VarChar(30)
  weakTags         String[]           @map("weak_tags")
  weeklyProblems   Json               @map("weekly_problems")
  difficultyCurve  Json?              @map("difficulty_curve")
  targets          Json?
  status           TrainingPlanStatus @default(active)
  completedCount   Int                @default(0) @map("completed_count")
  totalCount       Int                @default(0) @map("total_count")
  createdAt        DateTime           @default(now()) @map("created_at")
  updatedAt        DateTime           @updatedAt @map("updated_at")
  deletedAt        DateTime?          @map("deleted_at")

  user    User        @relation(fields: [userId], references: [id], onDelete: Cascade)
  profile UserProfile @relation(fields: [profileId], references: [id], onDelete: Cascade)

  @@index([userId, status], map: "idx_training_plans_user_status")
  @@map("training_plans")
}

// ===== 匹配推送域 =====
model Team {
  id          String     @id @default(uuid()) @db.Uuid
  name        String     @db.VarChar(100)
  createdBy   String     @map("created_by") @db.Uuid
  status      TeamStatus @default(active)
  createdAt   DateTime   @default(now()) @map("created_at")
  updatedAt   DateTime   @updatedAt @map("updated_at")
  deletedAt   DateTime?  @map("deleted_at")

  creator User         @relation("TeamCreator", fields: [createdBy], references: [id])
  members TeamMember[]

  @@map("teams")
}

model TeamMember {
  id       String   @id @default(uuid()) @db.Uuid
  teamId   String   @map("team_id") @db.Uuid
  userId   String   @map("user_id") @db.Uuid
  joinedAt DateTime @default(now()) @map("joined_at")

  team Team @relation(fields: [teamId], references: [id], onDelete: Cascade)
  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([teamId, userId], map: "uq_team_members_team_user")
  @@map("team_members")
}

model BotConfig {
  id           String     @id @default(uuid()) @db.Uuid
  channel      BotChannel
  userId       String     @map("user_id") @db.Uuid
  webhookUrl   String?    @map("webhook_url") @db.VarChar(500)
  enabled      Boolean    @default(true)
  scheduleCron String?    @map("schedule_cron") @db.VarChar(50)
  createdAt    DateTime   @default(now()) @map("created_at")
  updatedAt    DateTime   @updatedAt @map("updated_at")
  deletedAt    DateTime?  @map("deleted_at")

  user User @relation(fields: [userId], references: [id], onDelete: Cascade)

  @@unique([channel, userId], map: "uq_bot_configs_channel_user")
  @@map("bot_configs")
}

model PushLog {
  id           String          @id @default(uuid()) @db.Uuid
  channel      BotChannel
  targetType   String          @map("target_type") @db.VarChar(20)
  targetId     String          @map("target_id") @db.VarChar(100)
  messageType  PushMessageType @map("message_type")
  content      Json?
  sentAt       DateTime        @default(now()) @map("sent_at")
  status       PushStatus      @default(sent)
  errorMessage String?         @map("error_message") @db.Text

  @@index([channel, sentAt], map: "idx_push_logs_channel_time")
  @@index([status], map: "idx_push_logs_status")
  @@map("push_logs")
}
```

- [ ] **Step 4: 执行迁移**

```bash
cd E:/code/ACM-Agent/backend
npx prisma migrate dev --name add_all_tables
```

- [ ] **Step 5: 运行测试**

```bash
npx jest test/prisma.service.spec.ts --no-cache
# 预期: 全部 PASS (含 12 张表存在性测试)
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(db): add problem, record, profile, matching, push domain tables"
```

---

## Task 4: PGVector 扩展 + 向量索引

**Files:**
- Create: `backend/prisma/vector-indexes.sql`
- Test: `backend/test/prisma.service.spec.ts` (扩展)

- [ ] **Step 1: 写测试 — PGVector 扩展和索引**

```typescript
// 追加到 backend/test/prisma.service.spec.ts
describe('PGVector', () => {
  it('should have vector extension', async () => {
    const result = await service.$queryRaw`
      SELECT extname FROM pg_extension WHERE extname = 'vector'
    `;
    expect(result).toHaveLength(1);
  });

  it('should have vector columns on problems table', async () => {
    const result = await service.$queryRaw`
      SELECT column_name FROM information_schema.columns
      WHERE table_name = 'problems' AND column_name IN ('vector_embedding', 'content_vector')
    `;
    const names = (result as any[]).map(r => r.column_name);
    expect(names).toContain('vector_embedding');
    expect(names).toContain('content_vector');
  });

  it('should have vector column on problem_solutions', async () => {
    const result = await service.$queryRaw`
      SELECT column_name FROM information_schema.columns
      WHERE table_name = 'problem_solutions' AND column_name = 'vector_embedding'
    `;
    expect(result).toHaveLength(1);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
npx jest test/prisma.service.spec.ts --no-cache -t "PGVector"
# 预期: FAIL — vector 扩展未安装
```

- [ ] **Step 3: 启用 PGVector 扩展**

```bash
cd E:/code/ACM-Agent/backend
npx prisma db execute --command "CREATE EXTENSION IF NOT EXISTS vector;" --schema prisma/schema.prisma
```

- [ ] **Step 4: 创建向量索引 SQL**

```sql
-- backend/prisma/vector-indexes.sql
CREATE INDEX IF NOT EXISTS idx_problems_vector_embedding
ON problems USING ivfflat (vector_embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_problems_content_vector
ON problems USING ivfflat (content_vector vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_problem_solutions_vector
ON problem_solutions USING ivfflat (vector_embedding vector_cosine_ops)
WITH (lists = 50);
```

- [ ] **Step 5: 执行索引创建**

```bash
cd E:/code/ACM-Agent/backend
npx prisma db execute --file prisma/vector-indexes.sql --schema prisma/schema.prisma
```

- [ ] **Step 6: 运行测试**

```bash
npx jest test/prisma.service.spec.ts --no-cache
# 预期: 全部 PASS
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(db): enable PGVector extension and create IVFFlat indexes"
```

---

## Task 5: PrismaModule + HealthCheck

**Files:**
- Create: `backend/src/common/prisma/prisma.module.ts`
- Create: `backend/src/common/prisma/prisma.service.ts`
- Create: `backend/src/health/health.module.ts`
- Create: `backend/src/health/health.controller.ts`
- Create: `backend/src/health/health.service.ts`
- Test: `backend/test/health.service.spec.ts`

- [ ] **Step 1: 写测试 — HealthService**

```typescript
// backend/test/health.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { HealthService } from '../src/health/health.service';
import { PrismaService } from '../src/common/prisma/prisma.service';

describe('HealthService', () => {
  let service: HealthService;
  let prisma: PrismaService;

  beforeEach(async () => {
    prisma = new PrismaService();
    service = new HealthService(prisma);
  });

  afterEach(async () => {
    await prisma.$disconnect();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('should return healthy status when DB is connected', async () => {
    const result = await service.check();
    expect(result.status).toBe('ok');
    expect(result.database).toBe('connected');
    expect(result.timestamp).toBeDefined();
  });

  it('should return version info', async () => {
    const result = await service.check();
    expect(result.version).toBeDefined();
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
npx jest test/health.service.spec.ts --no-cache
# 预期: FAIL — HealthService 不存在
```

- [ ] **Step 3: 实现 HealthService**

```typescript
// backend/src/health/health.service.ts
import { Injectable } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';

@Injectable()
export class HealthService {
  constructor(private prisma: PrismaService) {}

  async check() {
    try {
      await this.prisma.$queryRaw`SELECT 1`;
      return {
        status: 'ok',
        database: 'connected',
        timestamp: new Date().toISOString(),
        version: process.env.npm_package_version || '0.0.1',
      };
    } catch {
      return {
        status: 'error',
        database: 'disconnected',
        timestamp: new Date().toISOString(),
      };
    }
  }
}
```

```typescript
// backend/src/health/health.controller.ts
import { Controller, Get } from '@nestjs/common';
import { HealthService } from './health.service';

@Controller('health')
export class HealthController {
  constructor(private healthService: HealthService) {}

  @Get()
  async check() {
    return this.healthService.check();
  }
}
```

```typescript
// backend/src/health/health.module.ts
import { Module } from '@nestjs/common';
import { HealthController } from './health.controller';
import { HealthService } from './health.service';

@Module({
  controllers: [HealthController],
  providers: [HealthService],
})
export class HealthModule {}
```

- [ ] **Step 4: 更新 AppModule**

```typescript
// backend/src/app.module.ts
import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { PrismaModule } from './common/prisma/prisma.module';
import { HealthModule } from './health/health.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    PrismaModule,
    HealthModule,
  ],
})
export class AppModule {}
```

- [ ] **Step 5: 运行测试**

```bash
npx jest test/health.service.spec.ts --no-cache
# 预期: 全部 PASS
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add PrismaModule and HealthCheck endpoint"
```

---

## Task 6: 种子数据

**Files:**
- Create: `backend/prisma/seed.ts`
- Test: `backend/test/seed.spec.ts`

- [ ] **Step 1: 写测试 — 种子数据**

```typescript
// backend/test/seed.spec.ts
import { PrismaService } from '../src/common/prisma/prisma.service';

describe('Seed Data', () => {
  let prisma: PrismaService;

  beforeAll(async () => {
    prisma = new PrismaService();
    await prisma.$connect();

    // 执行种子
    const { execSync } = require('child_process');
    execSync('npx prisma db seed', { cwd: process.cwd() });
  });

  afterAll(async () => {
    await prisma.$disconnect();
  });

  it('should have admin user', async () => {
    const admin = await prisma.user.findUnique({ where: { username: 'admin' } });
    expect(admin).not.toBeNull();
    expect(admin!.role).toBe('admin');
    expect(admin!.nickname).toBe('系统管理员');
  });

  it('should have hashed password for admin', async () => {
    const admin = await prisma.user.findUnique({ where: { username: 'admin' } });
    expect(admin!.passwordHash).not.toBe('admin123');
    expect(admin!.passwordHash).toMatch(/^\$2[ab]\$/); // bcrypt 格式
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
npx jest test/seed.spec.ts --no-cache
# 预期: FAIL — admin 用户不存在
```

- [ ] **Step 3: 创建种子脚本**

```typescript
// backend/prisma/seed.ts
import { PrismaClient } from '@prisma/client';
import * as bcrypt from 'bcrypt';

const prisma = new PrismaClient();

async function main() {
  const passwordHash = await bcrypt.hash('admin123', 10);

  await prisma.user.upsert({
    where: { username: 'admin' },
    update: {},
    create: {
      username: 'admin',
      passwordHash,
      role: 'admin',
      nickname: '系统管理员',
    },
  });

  console.log('Seed completed: admin user created');
}

main()
  .catch(console.error)
  .finally(() => prisma.$disconnect());
```

- [ ] **Step 4: 配置 package.json seed 命令**

```json
// backend/package.json — 追加
{
  "prisma": {
    "seed": "ts-node prisma/seed.ts"
  }
}
```

安装 ts-node: `npm i -D ts-node`

- [ ] **Step 5: 运行测试**

```bash
npx jest test/seed.spec.ts --no-cache
# 预期: 全部 PASS
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(db): add seed script with admin user"
```

---

## Task 7: 软删除中间件 + 全局异常过滤器

**Files:**
- Modify: `backend/src/common/prisma/prisma.service.ts`
- Create: `backend/src/common/filters/all-exceptions.filter.ts`
- Test: `backend/test/prisma.service.spec.ts` (扩展)

- [ ] **Step 1: 写测试 — 软删除**

```typescript
// 追加到 backend/test/prisma.service.spec.ts
describe('Soft Delete', () => {
  it('should filter deleted records by default', async () => {
    // 创建用户
    const user = await service.user.create({
      data: { username: 'soft_del_test', passwordHash: 'hash', role: 'user' },
    });
    // 软删除
    await service.user.update({
      where: { id: user.id },
      data: { deletedAt: new Date() },
    });
    // 查询应该找不到
    const found = await service.user.findUnique({ where: { id: user.id } });
    expect(found).toBeNull();
  });

  it('should find deleted records with findMany when explicitly querying', async () => {
    const user = await service.user.create({
      data: { username: 'soft_del_test2', passwordHash: 'hash', role: 'user' },
    });
    await service.user.update({
      where: { id: user.id },
      data: { deletedAt: new Date() },
    });
    // 用原生 SQL 查询含 deleted_at 的记录
    const found = await service.$queryRaw`
      SELECT id FROM users WHERE id = ${user.id}::uuid AND deleted_at IS NOT NULL
    `;
    expect(found).toHaveLength(1);

    // 清理
    await service.$queryRaw`DELETE FROM users WHERE id = ${user.id}::uuid`;
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
npx jest test/prisma.service.spec.ts --no-cache -t "Soft Delete"
# 预期: FAIL — 软删除未实现，findUnique 仍返回已删除记录
```

- [ ] **Step 3: 实现软删除中间件**

```typescript
// backend/src/common/prisma/prisma.service.ts
import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  async onModuleInit() {
    await this.$connect();
    this.$use(async (params, next) => {
      // 软删除中间件: 自动过滤 deleted_at IS NOT NULL 的记录
      const softDeleteModels = ['User', 'PlatformAccount', 'Problem', 'ProblemSolution',
        'UserProfile', 'TrainingPlan', 'Team', 'BotConfig'];

      if (softDeleteModels.includes(params.model)) {
        if (params.action === 'findUnique' || params.action === 'findFirst') {
          params.action = 'findFirst';
          params.args.where = { ...params.args.where, deletedAt: null };
        }
        if (params.action === 'findMany') {
          if (!params.args.where) params.args.where = {};
          if (params.args.where.deletedAt === undefined) {
            params.args.where.deletedAt = null;
          }
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

- [ ] **Step 4: 创建全局异常过滤器**

```typescript
// backend/src/common/filters/all-exceptions.filter.ts
import { ExceptionFilter, Catch, ArgumentsHost, HttpException, HttpStatus } from '@nestjs/common';
import { Response } from 'express';

@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();

    let status = HttpStatus.INTERNAL_SERVER_ERROR;
    let message = 'Internal server error';

    if (exception instanceof HttpException) {
      status = exception.getStatus();
      const res = exception.getResponse();
      message = typeof res === 'string' ? res : (res as any).message || message;
    } else if (exception instanceof Error) {
      message = exception.message;
    }

    response.status(status).json({
      statusCode: status,
      message,
      timestamp: new Date().toISOString(),
    });
  }
}
```

- [ ] **Step 5: 更新 main.ts 注册过滤器**

```typescript
// backend/src/main.ts
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { AppModule } from './app.module';
import { AllExceptionsFilter } from './common/filters/all-exceptions.filter';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  app.useGlobalFilters(new AllExceptionsFilter());
  app.enableCors();

  const config = new DocumentBuilder()
    .setTitle('ACM Agent API')
    .setVersion('1.0')
    .addBearerAuth()
    .build();
  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('api/docs', app, document);

  await app.listen(3000);
}
bootstrap();
```

- [ ] **Step 6: 运行测试**

```bash
npx jest test/prisma.service.spec.ts --no-cache
# 预期: 全部 PASS
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(db): add soft delete middleware and global exception filter"
```

---

## Task 8: 覆盖率验证 + Phase Gate

**Files:**
- Modify: `backend/jest.config.ts`

- [ ] **Step 1: 配置覆盖率阈值**

```typescript
// backend/jest.config.ts
export default {
  moduleFileExtensions: ['js', 'json', 'ts'],
  rootDir: '.',
  testRegex: '.*\\.spec\\.ts$',
  transform: { '^.+\\.ts$': 'ts-jest' },
  collectCoverageFrom: ['src/**/*.ts', '!src/main.ts'],
  coverageDirectory: './coverage',
  coverageThreshold: {
    global: {
      statements: 90,
      branches: 85,
      functions: 90,
      lines: 90,
    },
  },
  testEnvironment: 'node',
};
```

- [ ] **Step 2: 运行全量测试 + 覆盖率**

```bash
cd E:/code/ACM-Agent/backend
npm run test:cov
# 预期:
# - 全部测试 PASS
# - 语句覆盖率 ≥ 90%
# - 分支覆盖率 ≥ 85%
# - 函数覆盖率 ≥ 90%
# - 行覆盖率 ≥ 90%
```

- [ ] **Step 3: 如果覆盖率不足，补充测试**

检查覆盖率报告，为未覆盖的分支/函数补充测试用例。

- [ ] **Step 4: Phase Gate — 确认通过**

```bash
# 最终验证
npm run test:cov -- --forceExit
echo "Phase 1 Gate: Database infrastructure ready"
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(db): Phase 1 gate — 90% coverage achieved"
```

---

## Phase 1 完成标准

| 检查项 | 标准 | 验证命令 |
|--------|------|---------|
| 12 张表全部创建 | 100% | `npx prisma db execute --command "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"` |
| 枚举类型 | 8 个 | 测试验证 |
| PGVector 扩展 | 已启用 | 测试验证 |
| 向量索引 | 3 个 | 测试验证 |
| 种子数据 | admin 用户 | 测试验证 |
| 软删除 | 中间件工作 | 测试验证 |
| 测试覆盖率 | ≥ 90% | `npm run test:cov` |
| 全部测试通过 | 0 failures | `npm test` |
