# §4 数据库详细设计

> 版本: v1.0 | 日期: 2026-06-13 | 状态: 已批准
> 基于: `2026-06-13-acm-agent-design.md` §4 细化

---

## 1. 设计决策总览

| 决策项 | 选择 | 原因 |
|--------|------|------|
| ORM | Prisma Schema-first | 类型安全 + 自动生成 migration |
| 删除策略 | 全局软删除 (`deleted_at`) | 数据安全，用户/业务表可恢复 |
| 审计追踪 | 基础审计 (`created_by`/`updated_by`) | 记录操作人，适合多人管理 |
| 向量索引 | IVFFlat | 10 万级数据，查询快，构建简单 |
| 种子数据 | 最小化（仅 admin 账号） | 开发调试用，其他数据通过爬虫获取 |
| 复杂查询 | Raw SQL 扩展 | Prisma 不原生支持 PGVector 和数组查询 |

---

## 2. 通用规范

### 2.1 命名约定

| 类型 | 规范 | 示例 |
|------|------|------|
| 表名 | snake_case, 复数 | `users`, `practice_records` |
| 列名 | snake_case | `created_at`, `user_id` |
| 主键 | `id` UUID | `@id @default(uuid())` |
| 外键 | `{关联表单数}_id` | `user_id`, `problem_id` |
| 枚举 | UPPER_SNAKE_CASE | `UserRole.USER` |
| 索引 | `idx_{表}_{列}` | `idx_users_username` |
| 唯一约束 | `uq_{表}_{列}` | `uq_platform_accounts_user_platform` |

### 2.2 通用字段

每张表都有：

```prisma
id        String   @id @default(uuid()) @db.Uuid
createdAt DateTime @default(now()) @map("created_at")
updatedAt DateTime @updatedAt @map("updated_at")
deletedAt DateTime? @map("deleted_at")     // 软删除
```

核心业务表额外添加审计字段：

```prisma
createdBy String?  @map("created_by") @db.Uuid
updatedBy String?  @map("updated_by") @db.Uuid
```

### 2.3 枚举定义

```prisma
enum UserRole { user; observed; admin }
enum Platform { luogu; leetcode; nowcoder; codeforces; atcoder }
enum Verdict { OK; WA; TLE; MLE; RE; CE; OLE; SE; OTHER }
enum TrainingPlanStatus { active; completed; abandoned }
enum TeamStatus { active; archived }
enum BotChannel { feishu; qq }
enum PushMessageType { daily_report; ranking; weekly_report; alert }
enum PushStatus { sent; failed }
```

---

## 3. 用户域（3 张表）

### 3.1 users — 系统用户

```prisma
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
```

**字段说明**:
- `push_channels` JSONB: `{"daily_report": {"feishu": true, "qq": false}, ...}`
- `password_hash`: bcrypt 生成，不存明文
- `role`: `user`=普通用户, `observed`=观测用户(自动爬取), `admin`=管理员

### 3.2 platform_accounts — 多平台身份绑定

```prisma
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
```

**设计决策**:
- `normalized_rating`: CF rating / 洛谷咕值 / 力扣分 → 统一映射到 0~3000 区间
- `raw_profile`: JSONB 保留平台原始数据
- `onDelete: Cascade`: 用户删除时级联删除平台绑定

### 3.3 user_daily_stats — 每日统计

```prisma
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

**设计决策**:
- 无 `deletedAt` — 统计数据硬删除（历史数据不应被软删）
- `detail` JSONB: `{"by_tag": {...}, "by_difficulty": {...}, "by_language": {...}}`
- `@@unique` 防止重复统计

---

## 4. 题库域（2 张表）

### 4.1 problems — 归一化题库

```prisma
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
```

**设计决策**:
- `tags_normalized` 用 PostgreSQL 数组 + GIN 索引，支持 `&&`（交集查询）
- `vector_embedding` / `content_vector`: Prisma 不原生支持 PGVector，用 `Unsupported` 类型，通过 Raw SQL 操作
- `difficulty_normalized` 1~10 浮点，跨平台可比

### 4.2 problem_solutions — 官方题解

```prisma
model ProblemSolution {
  id               String   @id @default(uuid()) @db.Uuid
  problemId        String   @map("problem_id") @db.Uuid
  solutionIndex    Int      @map("solution_index")   // 1~2
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
```

### 4.3 向量存储策略

| 分段 | 存储位置 | 向量化 | 检索方式 |
|------|---------|--------|---------|
| 父 | `problems.vector_embedding` | ✅ LLM 总结全文 | ANN 主检索 |
| 子1 | `problems.content_vector` | ✅ 完整题面 | 关联返回 |
| 子2 | `problem_solutions.vector_embedding` | ✅ 1~2 条题解 | 关联返回 |

检索流程：父向量 ANN Top-K → 关联子分段返回。

---

## 5. 记录画像域（3 张表）

### 5.1 practice_records — 归一化提交记录

```prisma
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
```

**设计决策**:
- 无 `deletedAt` — 提交记录硬删除
- `@@unique(platform, platform_submission_id)` 防止重复爬取
- 双索引支持：按用户+时间查询 + 按用户+结果筛选

### 5.2 user_profiles — 用户画像

```prisma
model UserProfile {
  id                      String   @id @default(uuid()) @db.Uuid
  userId                  String   @unique @map("user_id") @db.Uuid
  generatedAt             DateTime @map("generated_at")

  // 6 维画像字段
  overallScore            Float    @map("overall_score")          // 0~1 综合评分
  coverage                Float    @default(0)                    // D1: 知识覆盖率
  categoryCoverage        Json?    @map("category_coverage")      // D1: {category: 0~1}
  ceiling                 Float    @default(0) @map("ceiling")    // D3: 难度天花板 1~10
  ceilingLevel            String?  @map("ceiling_level") @db.VarChar(20)
  efficiency              Float    @default(0)                     // D4: 解题效率
  firstAcRate             Float    @default(0) @map("first_ac_rate")
  avgRetries              Float    @default(0) @map("avg_retries")
  style                   String?  @db.VarChar(20)                 // D5: 学习风格
  momentum                Float    @default(0)                     // D6: 趋势动量
  trendLabel              String?  @map("trend_label") @db.VarChar(20)

  // 扩展字段
  overallStats            Json?    @map("overall_stats")
  difficultyDistribution  Json?    @map("difficulty_distribution")
  platformBreakdown       Json?    @map("platform_breakdown")
  tagProficiency          Json?    @map("tag_proficiency")         // D2: {tag: 0~1}
  strengths               Json?                               // [{tag, score, evidence}]
  weaknesses              Json?                               // [{tag, gap, priority}]
  skillRadar              Json?    @map("skill_radar")            // {category: score}
  summaryText             String?  @map("summary_text") @db.Text
  version                 Int      @default(1)

  createdAt               DateTime @default(now()) @map("created_at")
  updatedAt               DateTime @updatedAt @map("updated_at")

  user          User          @relation(fields: [userId], references: [id], onDelete: Cascade)
  trainingPlans TrainingPlan[]

  @@map("user_profiles")
}
```

**设计决策**:
- `userId` 唯一约束 — 每用户只有一个最新画像
- `version` 字段支持画像迭代（每次重新生成 version+1）
- 6 维数据直接存字段（非 JSON），便于查询
- `tag_proficiency` 等用 JSONB — 结构灵活

### 5.3 training_plans — 训练规划

```prisma
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
```

**JSONB 结构**:
- `weekly_problems`: `{"day1": [{problem_id, reason, is_review}], "day2": [...]}`
- `difficulty_curve`: `[5.0, 5.5, 6.0, 6.5, 7.0, 6.5, 6.0]`
- `targets`: `{"primary": [...], "secondary": [...], "explore": [...]}`
- `phase`: `template_consolidation` / `topic_breakthrough` / `integrated_practice` / `contest_simulation`

---

## 6. 匹配推送域（4 张表）

### 6.1 teams — 队伍

```prisma
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
```

### 6.2 team_members — 队员

```prisma
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
```

### 6.3 bot_configs — Bot 配置

```prisma
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
```

### 6.4 push_logs — 推送日志

```prisma
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

**设计决策**:
- `push_logs` 无 `deletedAt` — 日志表硬删除
- `target_type` + `target_id` 灵活支持用户/群组/频道推送
- `content` JSONB 快照推送内容

---

## 7. PGVector 配置与索引策略

### 7.1 向量扩展

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

向量维度: 1536 (text-embedding-3-small)

### 7.2 IVFFlat 索引

```sql
-- problems 表: 父向量索引
CREATE INDEX idx_problems_vector_embedding
ON problems USING ivfflat (vector_embedding vector_cosine_ops)
WITH (lists = 100);

-- problems 表: 题面子向量索引
CREATE INDEX idx_problems_content_vector
ON problems USING ivfflat (content_vector vector_cosine_ops)
WITH (lists = 100);

-- problem_solutions 表: 题解子向量索引
CREATE INDEX idx_problem_solutions_vector
ON problem_solutions USING ivfflat (vector_embedding vector_cosine_ops)
WITH (lists = 50);
```

**IVFFlat 参数**:
- `lists = sqrt(行数)`: 10 万题 → 100, 20 万题解 → 50
- `probes = sqrt(lists)`: 100 → 10（查询时设置）

### 7.3 向量检索查询模板

```sql
-- 父向量 ANN 检索
SET ivfflat.probes = 10;
SELECT p.id, p.title, p.difficulty_normalized, p.tags_normalized,
       1 - (p.vector_embedding <=> $1::vector) AS similarity
FROM problems p
WHERE p.deleted_at IS NULL AND p.vector_embedding IS NOT NULL
ORDER BY p.vector_embedding <=> $1::vector
LIMIT 20;

-- 子向量检索（题解）
SELECT ps.id, ps.content, ps.author,
       1 - (ps.vector_embedding <=> $1::vector) AS similarity
FROM problem_solutions ps
WHERE ps.deleted_at IS NULL AND ps.vector_embedding IS NOT NULL
ORDER BY ps.vector_embedding <=> $1::vector
LIMIT 10;
```

### 7.4 Embedding 模型

| 模型 | 维度 | 单价 | 适用场景 |
|------|------|------|---------|
| **text-embedding-3-small** | 1536 | $0.02/1M tokens | **当前选择** |
| text-embedding-3-large | 3072 | $0.13/1M tokens | 精度更高 |
| Mimo embedding | 待定 | 待定 | 国内模型 |

批量策略: 每批 500 条，失败重试 3 次指数退避。

---

## 8. 迁移与种子数据

### 8.1 Migration 工作流

```bash
# 开发: 修改 schema → 生成迁移 → 应用
npx prisma migrate dev --name <name>

# 生产: 应用迁移
npx prisma migrate deploy
```

### 8.2 种子数据

```typescript
// prisma/seed.ts — 仅创建 admin 账号
async function main() {
  await prisma.user.upsert({
    where: { username: 'admin' },
    update: {},
    create: {
      username: 'admin',
      passwordHash: await bcrypt.hash('admin123', 10),
      role: 'admin',
      nickname: '系统管理员',
    },
  });
}
```

### 8.3 数据库初始化完整流程

```bash
docker compose up -d postgres
docker compose exec postgres pg_isready
docker compose exec backend npx prisma migrate deploy
docker compose exec backend npx prisma db execute \
  --command "CREATE EXTENSION IF NOT EXISTS vector;"
docker compose exec backend npx prisma db execute \
  --file prisma/vector-indexes.sql
docker compose exec backend npx prisma db seed
docker compose up -d
```

---

## 9. 完整 Prisma Schema

见项目 `prisma/schema.prisma` 文件，包含全部 12 张表 + 8 个枚举定义。

---

## 10. ER 关系图

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│    users     │────<│ platform_accounts │     │   problems   │
│              │     └──────────────────┘     │              │
│              │────<┌──────────────────┐     │              │
│              │     │ user_daily_stats  │     │              │
│              │     └──────────────────┘     │              │
│              │                              │              │
│              │────<┌──────────────────┐     │              │
│              │     │ practice_records  │>────│              │
│              │     └──────────────────┘     │              │
│              │                              │              │
│              │─────┌──────────────────┐     │              │
│              │     │  user_profiles   │     │              │
│              │     └──────────────────┘     │              │
│              │                              │              │
│              │────<┌──────────────────┐     │              │
│              │     │ training_plans   │     │              │
│              │     └──────────────────┘     │              │
│              │                              │              │
│              │────<┌──────────────────┐     │              │
│              │     │  team_members    │     │              │
│              │     └──────────────────┘     │              │
│              │                              │              │
│              │────<┌──────────────────┐     │              │
│              │     │  bot_configs     │     │              │
└──────────────┘     └──────────────────┘     └──────────────┘
                                                    │
                                            ┌───────┴───────┐
                                            │problem_solutions│
                                            └───────────────┘

┌──────────────┐     ┌──────────────────┐
│    teams     │────<│  team_members    │
└──────────────┘     └──────────────────┘

┌──────────────────┐
│    push_logs     │  (独立，无 FK)
└──────────────────┘
```
