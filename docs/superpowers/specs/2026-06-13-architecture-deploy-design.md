# §2+§9+§10+§11 架构总览 + 部署 + 非功能需求 + 版本规划

> 版本: v1.0 | 日期: 2026-06-13 | 状态: 已批准
> 基于: `2026-06-13-acm-agent-design.md` §2+§9+§10+§11 细化

---

## 1. 系统架构总览（§2 细化）

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│                        展示层                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ React SPA │  │ 飞书 Bot  │  │  QQ Bot  │                  │
│  │ :5173     │  │ Webhook  │  │  API     │                  │
│  └─────┬────┘  └─────┬────┘  └────┬─────┘                  │
├────────┼─────────────┼────────────┼─────────────────────────┤
│        │             │            │       业务层              │
│  ┌─────▼─────────────▼────────────▼─────────────────────┐   │
│  │                   NestJS :3000                        │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │   │
│  │  │ Auth │ │ User │ │Problem│ │Record│ │Profile│     │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘      │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐               │   │
│  │  │Train │ │Match │ │Crawl │ │ Bot  │               │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘               │   │
│  └──────┬──────────────────────────┬───────────────────┘   │
├─────────┼──────────────────────────┼───────────────────────┤
│         │         数据 AI 层       │                        │
│  ┌──────▼──────┐           ┌──────▼──────┐                 │
│  │   Python    │           │ PostgreSQL  │                 │
│  │  爬虫/LLM   │──────────>│  + PGVector │                 │
│  │  Agent      │           │   :5432     │                 │
│  └─────────────┘           └─────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 子系统依赖图

```
S1 爬虫 ──────┐
              ├──── S5 题库构建 ──── S3 画像/训练 ──── S4 队友匹配
S2 用户管理 ──┘                              │
                                             ├── S6 消息推送
                                             │
                                      前端 React SPA
```

**构建顺序**: S1 + S2（并行）→ S5 → S3 → S4 → S6

### 1.3 技术栈确认

| 层 | 技术 | 版本 | 用途 |
|---|------|------|------|
| 前端 | React + TypeScript + Vite | 18 / 5.x / 5 | SPA |
| 组件库 | MUI (Material UI) | 5 | MD3 组件 |
| 后端 | NestJS + Prisma | 10 / 5 | API + ORM |
| AI/Agent | LangChain + LangGraph | 0.2 / 0.1 | Agent 编排 |
| LLM | DeepSeek + text-embedding-3-small | — | 总结 + 向量 |
| 爬虫 | DrissionPage | 4.x | 浏览器自动化 |
| 数据库 | PostgreSQL + PGVector | 16 / 0.5 | 存储 + 向量 |
| 部署 | Docker Compose | v2 | 单机部署 |

---

## 2. Docker Compose 部署（§9 细化）

### 2.1 docker-compose.yml

```yaml
version: "3.8"

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: acm-postgres
    environment:
      POSTGRES_DB: acm_agent
      POSTGRES_USER: acm
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./prisma/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U acm"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: acm-backend
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://acm:${DB_PASSWORD}@postgres:5432/acm_agent
      JWT_SECRET: ${JWT_SECRET}
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
      DEEPSEEK_BASE_URL: ${DEEPSEEK_BASE_URL}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    volumes:
      - ./python:/app/python
      - ./data:/app/data
    depends_on:
      postgres:
        condition: service_healthy

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: acm-frontend
    ports:
      - "5173:80"
    depends_on:
      - backend

volumes:
  postgres_data:
```

### 2.2 Dockerfile.backend

```dockerfile
FROM node:20-slim

# 安装 Python
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv

WORKDIR /app

# Node 依赖
COPY backend/package*.json ./backend/
RUN cd backend && npm ci

# Python 依赖
COPY python/requirements.txt ./python/
RUN pip3 install -r python/requirements.txt

# 复制代码
COPY backend/ ./backend/
COPY python/ ./python/
COPY prisma/ ./prisma/

WORKDIR /app/backend
RUN npx prisma generate

EXPOSE 3000
CMD ["npm", "run", "start:prod"]
```

### 2.3 环境变量

```bash
# .env.example
DB_PASSWORD=your_db_password
JWT_SECRET=your_jwt_secret_32_chars_min
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=sk-xxx
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
QQ_BOT_APP_ID=xxx
QQ_BOT_TOKEN=xxx
CRAWLER_RATE_LIMIT=2
CRAWLER_USER_AGENT=ACMBot/1.0
```

### 2.4 启动流程

```bash
# 1. 克隆代码
git clone <repo> && cd acm-agent

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值

# 3. 启动
docker compose up -d

# 4. 初始化数据库
docker compose exec backend npx prisma migrate deploy
docker compose exec backend npx prisma db execute \
  --command "CREATE EXTENSION IF NOT EXISTS vector;"
docker compose exec backend npx prisma db execute \
  --file prisma/vector-indexes.sql
docker compose exec backend npx prisma db seed

# 5. 访问
# 前端: http://localhost:5173
# API: http://localhost:3000/api
# Swagger: http://localhost:3000/api/docs
```

---

## 3. 非功能需求（§10 细化）

### 3.1 安全

| 需求 | 实现 |
|------|------|
| 认证 | JWT 无状态，Access 2h + Refresh 7d |
| 密码 | bcrypt 10 rounds |
| 输入校验 | class-validator + class-transformer (NestJS) |
| SQL 注入 | Prisma ORM 参数化查询 |
| XSS | React 自动转义 + DOMPurify (富文本) |
| CORS | 仅允许前端域名 |
| 环境变量 | .env 不入版本控制 |
| API Key | 仅在 Python 环境变量中，不暴露给前端 |

### 3.2 性能

| 需求 | 实现 |
|------|------|
| 向量检索 | PGVector IVFFlat 索引，probes=10 |
| 爬虫速率 | 每平台独立 QPS 限制 |
| 前端加载 | React.lazy 代码分割，首屏 < 2s |
| API 响应 | 简单查询 < 100ms，LLM 相关 < 5s |
| 数据库 | 关键查询走索引，N+1 问题用 include |

### 3.3 可维护性

| 需求 | 实现 |
|------|------|
| API 文档 | Swagger 自动文档 (`/api/docs`) |
| 日志 | NestJS Logger + Python logging |
| 错误追踪 | 全局异常过滤器 + 结构化错误响应 |
| 代码规范 | ESLint + Prettier (TS) / Ruff (Python) |
| 测试 | Jest (后端) + Vitest (前端) + pytest (Python) |

### 3.4 可扩展性

| 需求 | 实现 |
|------|------|
| 任务队列 | task/ 模块预留 BullMQ 迁移路径 |
| Bot Phase 2 | 指令交互架构预留 |
| 新平台爬虫 | 继承 BaseCrawler 即可扩展 |
| 新 Agent | LangGraph StateGraph 模块化 |

---

## 4. 版本规划（§11 细化）

### 4.1 v1.0 — MVP（目标: 4 周）

**范围**: S1 + S2 + S5 + S3 + S4 + S6 基础功能

| 周 | 任务 | 产出 |
|---|------|------|
| W1 | S1 爬虫 + S2 用户系统 | 5 平台爬虫可用 + 注册登录 |
| W2 | S5 题库构建 + 数据库 | 题库 1000+ 向量化完成 |
| W3 | S3 画像 + S4 匹配 | 画像生成 + 队友推荐 |
| W4 | S6 推送 + 前端 + 联调 | 日报推送 + 前端可用 |

### 4.2 v1.1 — 任务队列（目标: +1 周）

- BullMQ 替代 task/ 模块的 @nestjs/schedule
- Redis 缓存热门查询
- 爬虫重试机制增强

### 4.3 v1.2 — Bot 交互（目标: +2 周）

- 飞书应用机器人（消息回调）
- QQ Bot WebSocket 连接
- 指令交互: 查画像、推荐题、查排名

### 4.� v1.3 — 知识图谱（目标: +2 周）

- 知识图谱可视化（D3.js / Cytoscape.js）
- 训练成效评估（画像版本对比）
- 多学期数据对比

---

## 5. API 端点汇总

| 模块 | 端点数 | 主要端点 |
|------|--------|---------|
| Auth | 4 | login, register, me, refresh |
| User | 6 | CRUD + 平台绑定 |
| Problem | 4 | 列表, 详情, 语义搜索, 相似题 |
| Record | 3 | 列表, 每日统计, 总览 |
| Profile | 2 | 获取画像, 触发生成 |
| Training | 3 | 当前计划, 生成计划, 快速推荐 |
| Matching | 3 | 推荐队友, 创建队伍, 队伍管理 |
| Crawler | 3 | 触发爬取(单用户/全部/题库) |
| Bot | 4 | 推送(日报/周报), 配置, 测试 |
| Admin | 4 | 用户管理, 爬虫管理, Bot 配置 |
| **总计** | **36** | |
