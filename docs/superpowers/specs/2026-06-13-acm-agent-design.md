# ACM Agent 总体架构设计

> 版本: v1.0 | 日期: 2026-06-13 | 状态: 已批准

---

## 1. 项目概述

ACM Agent 是一个面向校级 ACM 竞赛团队的智能训练管理平台。核心能力：多平台练习数据聚合、AI 驱动的用户画像与训练规划、队友匹配推荐、飞书/QQ Bot 每日推送。

### 目标用户

- 校级/社团 ACM 团队，20~200 人，观测用户 10~50 人
- 角色：普通用户(user)、观测用户(observed)、管理员(admin)

### 技术栈

| 层 | 技术 |
|---|------|
| 前端 | React 18 + TypeScript + Vite 5 + MUI 5 (Material Design 3) |
| 后端 | NestJS (TypeScript) + Prisma ORM + Swagger |
| AI/Agent | LangChain + LangGraph (Python) |
| LLM | DeepSeek + Mimo |
| 脚本 | Python（爬虫 + LLM 处理 + Agent） |
| 数据库 | PostgreSQL 16 + PGVector |
| 缓存/队列 | 预留 Redis + BullMQ（后续扩展） |
| 部署 | Docker Compose · 单机 · 本地局域网 |

---

## 2. 系统架构

### 子系统划分（6 个，按构建顺序）

| # | 子系统 | 核心职责 | 依赖 |
|---|--------|---------|------|
| S1 | 多平台爬虫 | 爬取 5 大平台的题目、练习记录、题解 | 无 |
| S2 | 用户管理系统 | 注册、角色、权限、学籍信息、Bot 绑定 | 无 |
| S3 | 数据画像与训练规划 | 分析强弱项 → 生成画像 → 推荐训练计划 | S1 + S2 |
| S4 | 队友匹配推荐 | 基于画像数据做 3 人 ACM 队匹配 | S2 + S3 |
| S5 | 题库构建与向量化 | 爬题 → LLM 总结分类 → PGVector 存储 → 知识图谱 | S1 |
| S6 | 消息推送 | 飞书/QQ Bot 定时发榜单、日报、周报 | S2 + S3 |

**建议构建顺序**: S1 + S2（并行）→ S5 → S3 → S4 → S6

### 三层架构

```
展示层:    React SPA  |  飞书 Bot  |  QQ Bot
业务层:    NestJS (Auth/User/Problem/Record/Profile/Training/Matching/Crawler/Bot/Task)
数据AI层:  Python (爬虫/LLM/Agent)  |  PostgreSQL + PGVector
```

---

## 3. 项目目录结构

```
acm-agent/
├── docker-compose.yml
├── .env.example
├── backend/                   # NestJS 后端
│   └── src/
│       ├── main.ts
│       ├── app.module.ts
│       ├── common/            # 守卫、拦截器、DTO
│       ├── auth/              # JWT + 密码认证
│       ├── user/              # 用户 CRUD + 角色
│       ├── problem/           # 题库查询 + PGVector 检索
│       ├── record/            # 练习记录
│       ├── profile/           # 用户画像
│       ├── training/          # 训练规划
│       ├── matching/          # 队友匹配
│       ├── crawler/           # 爬虫调度
│       ├── bot/               # 飞书/QQ webhook
│       └── task/              # 定时任务（后续迁 BullMQ）
├── python/                    # Python 脚本 + Agent
│   ├── crawlers/              # 5 平台爬虫 (base/luogu/leetcode/nowcoder/codeforces/atcoder)
│   ├── llm/                   # LLM 处理 (summarizer/embedder/normalizer)
│   ├── agents/                # LangGraph Agent (profile_agent/training_agent)
│   └── scheduler/             # 定时任务触发器
├── frontend/                  # React SPA
│   └── src/
│       ├── pages/             # 17 个页面
│       ├── components/        # layout/common/charts/business 四层
│       ├── hooks/             # 自定义 hooks
│       ├── services/          # API 调用封装
│       └── types/             # TypeScript 类型
└── docs/
    └── superpowers/specs/     # 设计文档
```

---

## 4. 数据库设计

### 4.1 表总览（12 张，4 个业务域）

**用户域 (3 张)**: `users`, `platform_accounts`, `user_daily_stats`
**题库域 (2 张)**: `problems`, `problem_solutions`
**记录画像域 (3 张)**: `practice_records`, `user_profiles`, `training_plans`
**匹配推送域 (4 张)**: `teams`, `team_members`, `bot_configs`, `push_logs`

### 4.2 核心表

**users** — 系统用户
| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| username | VARCHAR(50) UNIQUE | 登录账号 |
| password_hash | VARCHAR(255) | |
| role | ENUM('user','observed','admin') | |
| nickname | VARCHAR(100) | 显示昵称 |
| email | VARCHAR(200) | 邮箱 |
| real_name | VARCHAR(50) | 真实姓名 |
| student_id | VARCHAR(30) | 学号 |
| department | VARCHAR(100) | 院系 |
| major | VARCHAR(100) | 专业 |
| class_name | VARCHAR(50) | 班级 |
| grade | VARCHAR(10) | 年级 |
| enrollment_year | INTEGER | 入学年份 |
| feishu_open_id | VARCHAR(100) | 飞书推送 |
| qq_number | VARCHAR(20) | QQ 推送 |
| push_channels | JSONB | 推送偏好 {daily_report:{feishu,qq},...} |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**platform_accounts** — 多平台身份绑定
- `user_id` FK → users, `platform` ENUM(luogu/leetcode/nowcoder/codeforces/atcoder)
- `platform_uid`, `platform_username`, `raw_profile` JSONB, `normalized_rating` INTEGER
- `last_synced_at`, `is_active`
- UNIQUE(user_id, platform)

**problems** — 归一化题库
- `source_platform`, `source_id`, `source_url`, `title`
- `difficulty_raw` VARCHAR(50) — 平台原始难度
- `difficulty_normalized` INTEGER 1~10 — 跨平台可比
- `tags_normalized` TEXT[], `tags_platform` JSONB
- `raw_detail` JSONB — 平台原始字段完整保留
- `full_content` TEXT — 完整题面
- `solution_summary` TEXT — LLM 统一总结（含做法/分类/题意/关键点/易错点/原题链接）
- `vector_embedding` vector(1536) — PGVector 父向量
- UNIQUE(source_platform, source_id)

**problem_solutions** — 官方题解（子分段）
- `problem_id` FK, `solution_index` SMALLINT(1~3)
- `content` TEXT, `author`, `source_url`
- `vector_embedding` vector(1536) — 子向量

**practice_records** — 归一化提交记录
- `platform`, `user_id` FK, `problem_id` FK
- `platform_submission_id`, `submit_time`
- `verdict` VARCHAR(30) — 归一化: OK|WA|TLE|MLE|RE|CE|OLE|SE|OTHER
- `verdict_raw` VARCHAR(100) — 平台原始结果
- `language`, `runtime_ms`, `memory_kb`, `code`, `raw_detail` JSONB
- UNIQUE(platform, platform_submission_id)

**user_daily_stats** — 每日统计
- `user_id` FK, `platform`, `stat_date` DATE
- `submit_count`, `ac_count`, `wa_count`, `tle_count`, `other_count`
- `new_problems_solved`, `hardest_difficulty`, `avg_difficulty`
- `active_duration_min`, `primary_language`
- `detail` JSONB — by_tag/by_difficulty/by_language 分组
- UNIQUE(user_id, platform, stat_date)

**user_profiles** — 用户画像
- `user_id` FK UNIQUE, `generated_at`
- `overall_stats` JSONB, `difficulty_distribution` JSONB
- `platform_breakdown` JSONB, `tag_proficiency` JSONB
- `strengths` JSONB, `weaknesses` JSONB, `skill_radar` JSONB
- `summary_text` TEXT, `version` INTEGER

**training_plans** — 训练规划
- `user_id` FK, `profile_id` FK
- `weak_tags` TEXT[], `weekly_problems` JSONB, `difficulty_curve` JSONB
- `status` ENUM('active','completed','abandoned')
- `completed_count`, `total_count`

**teams** — 队伍
- `id` UUID PK, `name`, `created_by` FK → users
- `status` ENUM('active','archived'), `created_at`

**team_members** — 队员
- `team_id` FK, `user_id` FK, `joined_at`
- UNIQUE(team_id, user_id)

**bot_configs** — Bot 配置
- `channel` ENUM(feishu/qq), `user_id` FK
- `webhook_url`, `enabled` BOOLEAN, `schedule_cron`

**push_logs** — 推送日志
- `channel`, `target_type` (user/group/channel), `target_id`
- `message_type` ENUM(daily_report/ranking/weekly_report/alert)
- `content` JSONB, `sent_at`, `status` ENUM(sent/failed), `error_message`

### 4.3 向量存储策略（父子分段）

| 分段 | 存储位置 | 内容 |
|------|---------|------|
| 父 | `problems.vector_embedding` | LLM 总结全文 |
| 子1 | `problems.full_content`（不单独向量化） | 完整题面 |
| 子2 | `problem_solutions.vector_embedding` | 2~3 条官方题解 |
| 子3 | `problems.vector_embedding`（同上） | LLM 总结 |

检索：父向量 ANN → 关联子分段返回。建图：`category_tags` 和 `type_tags` 共现关系。

### 4.4 关键设计决策

- **raw_* JSONB 保留平台原始数据**，不丢失信息
- **normalized_rating / normalized_difficulty** 跨平台可比
- **tags_normalized + tags_platform 双字段**：检索用归一化，回溯用原始
- **verdict_raw + verdict 双字段**：保留原始 + 归一化枚举
- **UNIQUE(platform, platform_submission_id)** 防重复爬取

---

## 5. NestJS 后端设计

### 5.1 模块总览（10 个）

| 模块 | 职责 | 依赖 |
|------|------|------|
| AppModule | 根模块，注册所有子模块 | 全部 |
| AuthModule | JWT + 密码登录/注册/me | 无 |
| UserModule | 用户 CRUD + 角色 + 平台绑定 | Auth |
| ProblemModule | 题库查询 + 向量检索 + 标签 | 无 |
| RecordModule | 练习记录查询 + 每日统计 | User |
| ProfileModule | 画像查询 + 触发生成 | User, Record |
| TrainingModule | 训练计划 + 题目推荐 | Profile, Problem |
| MatchingModule | 队友匹配 + 队伍管理 | Profile, User |
| CrawlerModule | 爬虫触发 + 日志 | Python脚本 |
| BotModule | 飞书/QQ webhook + 推送 | User, Record |
| TaskModule | 定时任务调度 (@nestjs/schedule) | Crawler, Profile, Bot |

### 5.2 核心 API 端点

```
POST /api/auth/login              # 登录返回 JWT
POST /api/auth/register           # 注册
GET  /api/auth/me                 # 当前用户

GET  /api/users                   # 用户列表（分页+搜索+筛选）
GET  /api/users/:id               # 用户详情
PATCH /api/users/:id              # 更新用户
POST /api/users/:id/platforms     # 绑定平台账号

GET  /api/problems                # 题目列表（按平台/难度/标签筛选）
GET  /api/problems/:id            # 题目详情（题面+总结+题解）
POST /api/problems/search/vector  # 语义检索（PGVector ANN）
GET  /api/problems/similar/:id    # 相似题目推荐

GET  /api/records                 # 练习记录列表
GET  /api/records/stats/daily     # 每日统计
GET  /api/records/stats/summary   # 个人总览

GET  /api/profiles/:userId        # 获取画像
POST /api/profiles/:userId/generate # 触发画像生成（调 Python Agent）

GET  /api/training/plans/:userId  # 当前训练计划
POST /api/training/plans/:userId/generate # 生成训练计划
GET  /api/training/recommend      # 快速推荐题目

POST /api/matching/recommend/:userId # 推荐最佳队友组合
POST /api/teams                   # 创建队伍

POST /api/crawler/trigger/user/:userId   # 手动爬取单用户
POST /api/crawler/trigger/all            # 批量爬取全部观测用户
POST /api/crawler/trigger/problems       # 触发题库爬取

POST /api/bot/push/daily     # 手动触发每日推送
POST /api/bot/push/weekly    # 手动触发周报推送
```

### 5.3 NestJS ↔ Python 调用机制

使用 `PythonService` 统一管理子进程调用：
- NestJS 通过 `child_process.execFile()` 调用 Python 脚本
- 参数通过 argv[1] 传 JSON，结果从 stdout 读 JSON
- Python 脚本同时支持 CLI 手动运行（argparse 模式）
- 保留 `task/` 模块扩展点，后续迁 BullMQ Worker

### 5.4 定时任务（TaskModule）

| 任务 | Cron | 说明 |
|------|------|------|
| sync-observed-users | 可配置，默认 02:00 | 爬取全部观测用户记录 |
| generate-profiles | 04:00 | 为新数据用户重新生成画像 |
| daily-push | 08:00 | 飞书/QQ 推送昨日榜单+日报 |
| weekly-push | 周一 08:00 | 推送周报 |

---

## 6. Python 爬虫与 Agent 设计

### 6.1 爬虫模块（crawlers/）

**base.py** — 抽象基类，定义三个核心抽象方法：
- `fetch_user_profile(platform_uid)` → dict
- `fetch_user_records(platform_uid, since)` → list[dict]
- `fetch_problem(source_id)` → dict

**5 个平台实现**:
| 平台 | 类 | API 方式 | 难度体系 |
|------|---|---------|---------|
| 洛谷 | LuoguCrawler | HTML + 部分 JSON (_contentOnly=1) | 颜色 0-9 |
| 力扣 | LeetcodeCrawler | GraphQL (leetcode.cn/graphql) | Easy/Medium/Hard |
| 牛客 | NowcoderCrawler | 内部 API + HTML | 整数难度 |
| Codeforces | CodeforcesCrawler | REST API (codeforces.com/api) | 整数 rating |
| AtCoder | AtcoderCrawler | HTML + kenkoooo API | 整数难度 |

**爬虫策略**: HTTP API 优先，失败降级 Playwright 浏览器

### 6.2 统一入口约定

所有 Python 脚本支持双模式：
```python
# 模式 1: NestJS 调用 → argv[1] = JSON
# 模式 2: 手动运行 → argparse CLI
# 示例: python crawlers/codeforces.py --action fetch_problems --tags dp --count 50
```

### 6.3 LLM 处理模块（llm/）

- **summarizer.py**: DeepSeek 总结题目 → 生成 summary + tags_normalized + key_points + pitfalls + difficulty_normalized
- **embedder.py**: 文本 → 1536 维向量，批量模式 + tqdm
- **normalizer.py**: 标签/难度归一化映射表（手动维护 + LLM 辅助）

### 6.4 LangGraph Agent 精细化设计（agents/）

两个 Agent 均使用 LangGraph StateGraph 构建，MemorySaver 做内存检查点。LLM 只做语义分析和编排，不做数值计算。

#### 6.4.1 profile_agent — 用户画像生成

**State Schema**: `{user_id, platforms, raw_records, daily_stats, platform_profiles, aggregated_stats, analysis, profile_data, errors}`

**Node Flow (5 节点 + 条件路由)**:

1. **Node 1: load_user_data** — 数据加载
   - 查询 `practice_records` + `user_daily_stats` (近 90 天) + `platform_accounts`
   - 如果 records < 10 → 标记数据不足

2. **Node 2: aggregate_stats** — 多维统计聚合（纯 Python，不调 LLM）
   - 按标签聚合: 每标签 {total, ac, wa, tle, ac_rate, avg_difficulty, recent_trend}
   - 按难度聚合: 1~10 各档位 solved 计数
   - 按平台聚合: 各平台 {solved, avg_difficulty, primary_language}
   - 时间趋势: 近 30 天刷题量/AC 量斜率
   - 全局统计: total_solved, total_submissions, overall_ac_rate, streak_days

3. **Node 3: llm_analyze** — LLM 深度分析（调 DeepSeek + StructuredOutput）
   - 输入: `aggregated_stats` → 输出结构化 JSON:
   - `strengths`: [{tag, proficiency_score (0~1), evidence}] — proficiency >= 0.7 的前 5
   - `weaknesses`: [{tag, gap_score (0~1), suggested_focus, priority}] — gap >= 0.5 的前 5
   - `skill_radar`: {tag: score (0~1)} — 全部标签雷达图数据
   - `summary_text`: 自然语言总结 (100~200 字)
   - `learning_style`: ENUM("题海型","精研型","偏科型","均衡型")

4. **条件路由**:
   - 数据不足 → Node 4a fallback（纯规则兜底）
   - LLM 正常 → Node 4b validate（校验 proficiency/gap 范围、summary 长度）
   - LLM 异常 → Node 4c retry（降温度 0.3 重试，最多 2 次）

5. **Node 5: save_profile** — 写入 `user_profiles` 表

**LLM Prompt 核心要求**: 教练口吻，proficiency 综合考虑 AC 率(0.4) + 难度(0.3) + 题量(0.3)，summary 格式: "该同学整体处于[水平定位]，擅长[top3优势]，但在[top3弱势]方面需要加强..."

**容错策略**: 数据不足走纯规则画像（只用 aggregate_stats 结果不加 LLM）；LLM 2 次重试仍失败走规则兜底

#### 6.4.2 training_agent — 训练规划生成

**State Schema**: `{user_id, profile_id, plan_days=7, daily_target=5, profile, weak_tags_ranked, candidate_problems, weekly_plan, difficulty_curve, plan_data, errors}`

**Node Flow (6 节点 + 条件路由)**:

1. **Node 1: load_profile** — 读取最新画像（无画像则先调 profile_agent）

2. **Node 2: rank_weak_tags** — 确定训练靶向
   - 取 weaknesses 中 gap_score 最高 3 个标签作为主靶向
   - 取 skill_radar 边缘标签（0.5~0.65）2 个作为次要巩固
   - 关联子标签/细分方向

3. **Node 3: retrieve_problems** — 3 路并行召回 + 打分去重
   - **路 1 向量**: PGVector ANN 搜靶向标签对应的 summary，Top 30，排除已 AC
   - **路 2 标签**: SQL WHERE tags_normalized && ARRAY[靶向标签]，难度 ±2，Top 20
   - **路 3 相似**: 用用户最近 AC 的高难度题做种子，向量搜相似但更难的题，Top 10
   - 去重打分: 0.5×标签匹配 + 0.3×难度匹配 + 0.2×向量相似
   - 候选池不足 35 题时 → 补充节点扩大筛选范围

4. **Node 4: llm_arrange_plan** — LLM 编排周计划（调 DeepSeek + StructuredOutput）
   - 输入: `candidate_problems` (40~60 题) + `weak_tags_ranked` + `difficulty_curve`
   - 编排节奏: Day 1-2 低难度恢复 → Day 3-5 中高难度突破 → Day 6 次要标签巩固 → Day 7 综合限时模拟
   - 每天 5 题，每题附带 1 句推荐理由
   - 题型搭配: 2 模板经典 + 2 变种思维 + 1 综合
   - 平台多样性: 洛谷打基础 → 力扣练思维 → CF 上强度

5. **条件路由**: 候选不足→补题；编排异常→重试

6. **Node 6: save_plan** — 写入 `training_plans` 表

**难度曲线自动计算**（纯 Python，不走 LLM）:
```
start = max(1.0, weak_avg - 1.0)    # 从舒适区开始
peak  = min(10.0, weak_avg + 2.0)   # 峰值不超过 +2
curve = 缓升(day1→day6) → 回稳(day7)
```

**LLM Prompt 核心要求**: 难度递进、标签聚焦、平台多样、题型搭配(2+2+1)、避重原则(排除已 AC)

#### 6.4.3 关键设计决策

| 决策 | 做法 | 原因 |
|------|------|------|
| LLM 只做分析不做计算 | 统计聚合纯 Python，LLM 只接收聚合结果 | 避免幻觉算错数据，节省 token |
| 规则兜底 + 降级重试 | 数据<10 条走纯规则；LLM 异常降温度重试 2 次 | 系统不依赖 LLM 可用性 |
| 3 路并行召回 | 向量 + 标签 + 相似题，打分排序 | 单路容易偏，多路互补 |
| 难度曲线不走 LLM | 纯 Python 公式 | 确定性计算，稳定可复现 |
| StructuredOutput 强制校验 | LangChain `with_structured_output(JSON_SCHEMA)` | 防止 LLM 输出格式错误 |

---

## 7. React 前端设计

### 7.1 设计系统

| 维度 | 规格 |
|------|------|
| 设计语言 | Google Material Design 3 |
| 组件库 | MUI 5 (@mui/material) |
| 主题 | 亮色调 Analytics Blue |
| Primary | #1E40AF (信任蓝) |
| Secondary | #3B82F6 (亮蓝) |
| CTA / Warning | #F59E0B (琥珀) |
| Success / AC | #10B981 (翡翠绿) |
| Error / WA | #EF4444 (警示红) |
| Background | #F8FAFC (石板 50) |
| Surface | #FFFFFF (卡片白) |
| Text Primary | #1E3A8A (深蓝, contrast ~8:1) |
| Text Secondary | #475569 (石板 600, contrast ~5:1) |
| Heading 字体 | Fira Sans (600/700) |
| Body 字体 | Fira Sans (400/500) |
| Code/Data 字体 | Fira Code (400/500, tabular-nums) |
| 图标库 | Google Material Symbols (禁止 emoji 作为视觉元素) |
| 图表 | Recharts（配色跟随 MD3 主题 token） |
| 路由 | React Router v6 |
| 状态管理 | React Context + useReducer + 自定义 hooks |
| HTTP | axios + JWT 拦截器 |

### 7.2 页面路由（17 个）

```
/login                          → 登录
/register                       → 注册
/dashboard                      → 仪表盘
/problems                       → 题库浏览（筛选+语义搜索+列表）
/problems/:id                   → 题目详情（题面+总结+题解+相似题）
/records                        → 练习记录
/profile/:userId                → 用户画像（雷达图+强弱项+总结）
/training                       → 训练计划（周视图+进度）
/training/recommend             → 快速推荐题目
/matching                       → 队友匹配推荐
/teams                          → 队伍列表
/teams/:id                      → 队伍详情
/ranking                        → 排行榜（刷题/AC/连续天数, 日/周/总）
/settings                       → 个人设置（密码+平台绑定+Bot偏好）
/admin/users                    → [admin] 用户管理
/admin/users/:id                → [admin] 用户详情/编辑
/admin/crawler                  → [admin] 爬虫管理
/admin/bot                      → [admin] Bot 配置
```

### 7.3 组件树

```
layout/    AppLayout, Sidebar, TopBar
common/    DataTable, SearchInput, FilterPanel, TagBadge, DifficultyBadge, VerdictBadge,
           LoadingSpinner, EmptyState, ConfirmDialog
charts/    SkillRadar, DailyTrend, DifficultyPie, TagBar, Heatmap
business/  ProblemCard, ProblemDetail, CodeViewer, ProfileOverview,
           TrainingWeekView, TeamCard, MatchRecommendation, RankingTable
```

### 7.4 响应式断点（MD3 规范）

| 断点 | 宽度 | 列数 | 导航 |
|------|------|------|------|
| Compact | 0-599px | 4 | NavigationBar (底部) |
| Medium | 600-839px | 8 | NavigationRail |
| Expanded | 840-1199px | 12 | NavigationRail |
| Large | 1200-1599px | 12 | NavigationDrawer |
| Extra Large | 1600px+ | 12 | NavigationDrawer |

### 7.5 交互规范

- 按钮 hover: 背景色渐变 150ms ease
- 卡片 hover: elevation ↑ + border-color 200ms
- 加载态: MUI Skeleton 骨架屏
- 空状态: 大图标 + 说明文字 + 操作按钮
- 错误态: Alert severity="error" + 重试按钮
- 成功反馈: Snackbar 底部短暂提示
- Focus 态: 2px primary ring (keyboard a11y)

---

## 8. Bot 推送设计

### 8.1 飞书 Bot

| 阶段 | 功能 | 技术方式 |
|------|------|---------|
| Phase 1 | 定时推送（日报/周报/榜单） | Webhook 机器人 → 群消息（无需公网） |
| Phase 2 | 指令交互（查画像/推荐题） | 应用机器人 → 消息回调 → NestJS API（需公网/内网穿透） |

### 8.2 QQ Bot

| 阶段 | 功能 | 技术方式 |
|------|------|---------|
| Phase 1 | 定时推送 | QQ 开放平台 Bot API → 群聊消息 |
| Phase 2 | 指令交互 | WebSocket 连接 → 事件回调 → NestJS API |

### 8.3 推送消息类型

- **每日推送**: 团队统计卡片 + 刷题王 + 榜单 Top 5
- **每周推送**: 个人周报（提交数/AC率/趋势/强弱项/推荐训练）

---

## 9. 部署方案

### 9.1 Docker Compose（4 容器）

```yaml
services:
  postgres:   # pgvector/pgvector:pg16, port 5432
  backend:    # NestJS, port 3000, 挂载 python/ 目录
  frontend:   # React build → Nginx, port 5173
  # redis:    # 预留，BullMQ 扩展
```

### 9.2 启动命令

```bash
docker compose up -d                                          # 启动
docker compose exec backend npx prisma migrate deploy          # 初始化数据库
docker compose exec backend python /app/python/crawlers/luogu.py --action fetch_problems  # 手动爬题
```

### 9.3 关键环境变量

```
DB_PASSWORD, JWT_SECRET
DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MIMO_API_KEY, MIMO_BASE_URL
FEISHU_WEBHOOK_URL, QQ_BOT_APP_ID, QQ_BOT_TOKEN
CRAWLER_RATE_LIMIT, CRAWLER_USER_AGENT
```

---

## 10. 非功能需求

- **安全**: JWT 无状态认证、密码 bcrypt 哈希、.env 不入版本控制、API 输入校验
- **性能**: PGVector IVFFlat 索引、爬虫速率限制、前端代码分割
- **可维护性**: Swagger 自动文档、Python 脚本独立可测、NestJS 模块化边界清晰
- **可扩展性**: task/ 模块预留 BullMQ 迁移路径、Bot Phase 2 指令交互架构预留

---

## 11. 后续版本规划

| 版本 | 内容 |
|------|------|
| v1.0 | S1+S2+S5+S3+S4+S6 全部基础功能 |
| v1.1 | BullMQ 任务队列、Redis 缓存、爬虫重试机制 |
| v1.2 | Bot Phase 2 指令交互、内网穿透方案 |
| v1.3 | 知识图谱可视化、训练成效评估、多学期对比 |
