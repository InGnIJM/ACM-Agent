# ACM Agent 存量问题修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 5 个阻塞性问题 + 完成前后端集成 + 补测试覆盖 + 完成部署配置，使系统达到可生产状态。

**Architecture:** 本计划覆盖 NestJS 后端（CronService DI 修复、数据关联修复、QQ Bot 实现）、React 前端（API 对接）、Python 爬虫（缺失脚本补齐）、Docker 部署（init.sql 补齐、路径修正）。

**Tech Stack:** NestJS + Prisma + Python 3 + React + MUI 5 + Docker Compose + PGVector

---

## 文件结构

```
acm-agent/
├── backend/
│   ├── src/
│   │   ├── task/
│   │   │   └── task.module.ts          # 修改：注册 DI provider
│   │   ├── crawler/
│   │   │   └── crawler.controller.ts   # 修改：修复 upsertRecord 占位 UUID
│   │   ├── bot/
│   │   │   └── bot.service.ts          # 修改：sendQQ HTTP 实现
│   │   └── training/
│   │       └── training.service.ts     # 修改：实现 getRecommend
│   ├── prisma/
│   │   └── init.sql                    # 创建：PGVector 扩展
│   └── test/
│       └── training.service.spec.ts    # 创建：TrainingService 单测
├── python/
│   └── crawlers/
│       └── user_crawler.py             # 创建：批量用户爬取入口
├── frontend/
│   └── src/
│       ├── pages/admin/BotConfig.tsx   # 修改：对接真实 API
│       └── services/bot.ts            # 创建：Bot API service
├── docker-compose.yml                  # 修改：init.sql 路径
└── .dockerignore                       # 创建
```

---

### Task 1: 修复 CronService — DI Token 注册

**背景**：`cron.service.ts` 通过 `@Optional() @Inject(CRAWLER_TRIGGER)` 等方式注入依赖，但 `TaskModule` 从未提供这些 token。四个定时任务（syncObservedUsers、generateProfiles、dailyPush、weeklyPush）虽然注册了 cron 表达式，但所有 `?.` 调用全部跳过，集群静默失效。

**Files:**
- Modify: `backend/src/task/task.module.ts`

- [ ] **Step 1: 在 TaskModule 中注册 CrawlerService 和 PushService 作为 provider**

```typescript
// backend/src/task/task.module.ts
import { Module } from '@nestjs/common';
import { ScheduleModule } from '@nestjs/schedule';
import { CronService } from './cron.service';
import { CrawlerModule } from '../crawler/crawler.module';
import { BotModule } from '../bot/bot.module';

@Module({
  imports: [ScheduleModule.forRoot(), CrawlerModule, BotModule],
  providers: [CronService],
})
export class TaskModule {}
```

- [ ] **Step 2: 修改 cron.service.ts — 直接注入具体服务，弃用 Symbol token**

```typescript
// backend/src/task/cron.service.ts
import { Injectable, Logger } from '@nestjs/common';
import { Cron } from '@nestjs/schedule';
import { PrismaService } from '../common/prisma/prisma.service';
import { CrawlerService } from '../crawler/crawler.service';
import { PushService } from '../bot/bot.service';

@Injectable()
export class CronService {
  private readonly logger = new Logger(CronService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly crawlerService: CrawlerService,
    private readonly pushService: PushService,
  ) {}

  @Cron('0 2 * * *')
  async syncObservedUsers(): Promise<void> {
    try {
      const observedUsers = await this.prisma.user.findMany({
        where: { role: 'observed', deletedAt: null },
        select: { id: true },
      });

      for (const user of observedUsers) {
        await this.crawlerService.triggerUserCrawl(user.id);
      }

      this.logger.log(
        `syncObservedUsers: triggered crawler for ${observedUsers.length} observed users`,
      );
    } catch (error) {
      this.logger.error('syncObservedUsers failed', error);
    }
  }

  @Cron('0 4 * * *')
  async generateProfiles(): Promise<void> {
    try {
      const usersWithProfile = await this.prisma.user.findMany({
        where: { role: 'observed', deletedAt: null },
        select: {
          id: true,
          profile: { select: { generatedAt: true } },
        },
      });

      let triggered = 0;

      for (const user of usersWithProfile) {
        const lastProfileAt =
          user.profile?.generatedAt ?? new Date(0);

        const newRecordCount = await this.prisma.practiceRecord.count({
          where: {
            userId: user.id,
            submitTime: { gt: lastProfileAt },
          },
        });

        if (newRecordCount > 0) {
          // 通过 crawler service 触发画像生成（内部调用 Python profile_agent）
          await this.crawlerService.triggerProfileGeneration(user.id);
          triggered++;
        }
      }

      this.logger.log(
        `generateProfiles: triggered profile generation for ${triggered} users`,
      );
    } catch (error) {
      this.logger.error('generateProfiles failed', error);
    }
  }

  @Cron('0 8 * * *')
  async dailyPush(): Promise<void> {
    try {
      const configs = await this.prisma.botConfig.findMany({
        where: { enabled: true, deletedAt: null },
        select: { channel: true, userId: true },
      });
      for (const cfg of configs) {
        const data = {
          date: new Date().toISOString().slice(0, 10),
          stats: { totalSubmits: 0, totalAc: 0, acRate: '0%' },
          ranking: [],
        };
        await this.pushService.sendDailyReport(cfg.channel, cfg.userId, data);
      }
      this.logger.log(`dailyPush: sent to ${configs.length} configs`);
    } catch (error) {
      this.logger.error('dailyPush failed', error);
    }
  }

  @Cron('0 8 * * 1')
  async weeklyPush(): Promise<void> {
    try {
      const configs = await this.prisma.botConfig.findMany({
        where: { enabled: true, deletedAt: null },
        select: { channel: true, userId: true },
      });
      for (const cfg of configs) {
        const data = {
          weekLabel: '本周',
          totalAc: 0,
          totalSubmits: 0,
          acRate: '0%',
          activeUsers: 0,
          strengths: [],
          weaknesses: [],
          topUsers: [],
        };
        await this.pushService.sendWeeklyReport(cfg.channel, cfg.userId, data);
      }
      this.logger.log(`weeklyPush: sent to ${configs.length} configs`);
    } catch (error) {
      this.logger.error('weeklyPush failed', error);
    }
  }
}
```

- [ ] **Step 3: 在 CrawlerService 中新增 triggerProfileGeneration 方法**

在 `backend/src/crawler/crawler.service.ts` 末尾追加：

```typescript
  async triggerProfileGeneration(userId: string): Promise<void> {
    this.logger.log(`Triggering profile generation for user=${userId}`);
    await this.pythonService.execute('agents/profile_agent_cli.py', { userId });
  }
```

- [ ] **Step 4: 删除 cron.service.ts 中不再需要的 Symbol token 导出**

原文件中 `CRAWLER_TRIGGER`、`PROFILE_AGENT_TRIGGER`、`BOT_SERVICE` 三个 Symbol 和对应的 interface 定义全部删除（已在 Step 2 的新代码中移除）。

- [ ] **Step 5: 运行现有 cron service 单测确认不退化**

```bash
cd backend
npx jest src/task/cron.service.spec.ts --no-cache
# 预期: PASS（如果测试存在；如果不存在则跳过此步）
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/task/task.module.ts backend/src/task/cron.service.ts backend/src/crawler/crawler.service.ts
git commit -m "fix(task): wire cron service DI with concrete services, replacing orphaned Symbol tokens"
```

---

### Task 2: 创建 crawlers/user_crawler.py — 批量用户爬取入口

**背景**：`CrawlerController.triggerUserCrawl()` 和 `triggerAllUsers()` 调用 `crawlers/user_crawler.py`，但该文件不存在。需要创建一个入口脚本，按参数分发到各平台爬虫。

**Files:**
- Create: `python/crawlers/user_crawler.py`

- [ ] **Step 1: 创建 user_crawler.py**

```python
"""Batch user crawl entry point — invoked by NestJS CrawlerController.

Usage:
    python crawlers/user_crawler.py --input '{"userId":"uuid","all":false}'
    python crawlers/user_crawler.py --input '{"all":true}'

The script queries the backend API for platform accounts, then invokes
each platform crawler in sequence.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Map platform to crawler module
PLATFORM_CRAWLER_MAP: Dict[str, str] = {
    "luogu": "crawlers.luogu",
    "leetcode": "crawlers.leetcode",
    "codeforces": "crawlers.codeforces",
    "atcoder": "crawlers.atcoder",
    "nowcoder": "crawlers.nowcoder",
}


def _fetch_accounts_from_api(
    api_url: str, user_id: Optional[str] = None
) -> List[Dict[str, str]]:
    """Fetch platform accounts from the NestJS backend API."""
    import urllib.request
    import urllib.error

    if user_id:
        url = f"{api_url}/api/users/{user_id}/accounts"
    else:
        url = f"{api_url}/api/users/observed/accounts"

    try:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        # Use internal service token if configured
        token = os.environ.get("ACM_SERVICE_TOKEN", "")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.error(f"API returned {e.code}: {e.reason}")
        return []
    except Exception as e:
        logger.error(f"Failed to fetch accounts: {e}")
        return []


def _run_crawler(platform: str, user_id: str, platform_uid: str) -> Dict[str, Any]:
    """Run a single platform crawler for a single user."""
    module_name = PLATFORM_CRAWLER_MAP.get(platform)
    if not module_name:
        return {"platform": platform, "success": False, "error": f"Unknown platform: {platform}"}

    try:
        import importlib
        mod = importlib.import_module(module_name)
        crawler_class = getattr(mod, f"{platform.capitalize()}Crawler", None)
        if crawler_class is None:
            # Fallback: try to find any class ending with Crawler
            crawler_class = next(
                (v for k, v in mod.__dict__.items() if k.endswith("Crawler") and isinstance(v, type)),
                None,
            )
        if crawler_class is None:
            return {"platform": platform, "success": False, "error": "No crawler class found"}

        crawler = crawler_class()
        result = crawler.fetch_user_records(user_id=user_id, platform_uid=platform_uid)
        return {
            "platform": platform,
            "success": True,
            "records_synced": len(result) if isinstance(result, list) else 0,
        }
    except Exception as e:
        logger.error(f"Crawler {platform} failed: {traceback.format_exc()}")
        return {"platform": platform, "success": False, "error": str(e)}


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Batch user crawl")
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help='JSON: {"userId":"uuid"} or {"all":true}',
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=os.environ.get("ACM_API_URL", "http://localhost:3000"),
        help="NestJS backend URL",
    )
    args = parser.parse_args(argv)
    input_data: Dict[str, Any] = json.loads(args.input or "{}")

    if input_data.get("all"):
        # Crawl all observed users
        accounts = _fetch_accounts_from_api(api_url=args.api_url)
    else:
        user_id = input_data.get("userId", "")
        if not user_id:
            print(json.dumps({"success": False, "error": "userId is required"}))
            return
        accounts = _fetch_accounts_from_api(api_url=args.api_url, user_id=user_id)

    if not accounts:
        print(json.dumps({"success": True, "total": 0, "results": [], "message": "No accounts found"}))
        return

    results: List[Dict[str, Any]] = []
    for acct in accounts:
        result = _run_crawler(
            platform=acct.get("platform", ""),
            user_id=acct.get("userId", ""),
            platform_uid=acct.get("platformUid", ""),
        )
        results.append(result)

    success_count = sum(1 for r in results if r.get("success"))
    output = {
        "success": True,
        "total": len(accounts),
        "success_count": success_count,
        "error_count": len(accounts) - success_count,
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main()
```

- [ ] **Step 2: 验证脚本至少能解析参数**

```bash
cd python
python crawlers/user_crawler.py --input '{"userId":"test","all":false}'
# 预期: 输出 JSON（即使 API 不可达也会优雅失败）; 不应报 ImportError
```

- [ ] **Step 3: Commit**

```bash
git add python/crawlers/user_crawler.py
git commit -m "feat(crawler): add batch user crawl entry script"
```

---

### Task 3: 修复 PracticeRecord upsert — userId / problemId 映射

**背景**：`crawler.controller.ts` 在 upsert 练习记录时使用硬编码的占位 UUID `00000000-0000-0000-0000-000000000000`，导致所有记录无法关联到真实用户和题目。

**Files:**
- Modify: `backend/src/crawler/crawler.controller.ts`

- [ ] **Step 1: 在 CrawlerController 类中添加 lookup 方法**

在 `crawler.controller.ts` 中 `upsertRecord` 方法的**前面**添加：

```typescript
  /**
   * Resolve userId from platform account (platform + platformUid).
   * Returns null if no PlatformAccount exists for this combination.
   */
  private async resolveUserId(platform: string, platformUid: string): Promise<string | null> {
    const account = await this.prisma.platformAccount.findFirst({
      where: { platform: platform as any, platformUid },
      select: { userId: true },
    });
    return account?.userId ?? null;
  }

  /**
   * Resolve problemId from platform + platformProblemId.
   * Returns null if the problem doesn't exist in our DB yet.
   */
  private async resolveProblemId(platform: string, platformProblemId: string): Promise<string | null> {
    const problem = await this.prisma.problem.findFirst({
      where: {
        platform: platform as any,
        platformProblemId,
      },
      select: { id: true },
    });
    return problem?.id ?? null;
  }
```

- [ ] **Step 2: 修改 upsertRecord，调用 resolveUserId / resolveProblemId**

将 `upsertRecord` 方法替换为异步实现（如果是同步的则改为 async）：

```typescript
  private async upsertRecord(platform: string, record: any, platformUid: string): Promise<void> {
    const submissionId = record.id || record.record_id || record.platform_submission_id || `${record.uid}_${record.timestamp}`;
    if (!submissionId) return;

    // Resolve real UUIDs
    const userId = await this.resolveUserId(platform, platformUid);
    const platformProblemId = record.problem_id || record.problemId || record.title_slug || null;
    const problemId = platformProblemId
      ? await this.resolveProblemId(platform, String(platformProblemId))
      : null;

    if (!userId) {
      this.logger.warn(`Cannot upsert record: no PlatformAccount for ${platform}/${platformUid}`);
      return;
    }

    await this.prisma.practiceRecord.upsert({
      where: {
        platform_platformSubmissionId: { platform: platform as any, platformSubmissionId: String(submissionId) },
      },
      create: {
        platform: platform as any,
        userId,
        problemId,
        platformSubmissionId: String(submissionId),
        submitTime: record.timestamp || record.submit_time || new Date(),
        verdict: 'OTHER' as any,
        verdictRaw: record.verdict || null,
        language: record.language || null,
        rawDetail: record,
      },
      update: {
        verdictRaw: record.verdict || null,
        language: record.language || null,
        rawDetail: record,
      },
    });
  }
```

- [ ] **Step 3: 找到所有调用 upsertRecord 的地方，确保传入 platformUid**

搜索 `this.upsertRecord` 的调用点，确保第三个参数 `platformUid` 已传入。如果调用方没有 platformUid，需要在调用方解析。

```bash
cd backend
npx jest src/crawler/crawler.controller.spec.ts --no-cache 2>&1 | head -5
# 预期: 测试文件存在则运行，否则跳过
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/crawler/crawler.controller.ts
git commit -m "fix(crawler): resolve real userId and problemId in PracticeRecord upsert"
```

---

### Task 4: QQ Bot sendQQ — HTTP API 实现

**背景**：`bot.service.ts` 的 `sendQQ()` 方法只有 `// TODO: Integrate QQ Bot SDK or HTTP API when available` 注释，实际不发送任何消息。QQ Bot 官方提供 HTTP API，可基于环境变量配置。

QQ Bot API 端点：`https://api.q.qq.com/v2/users/{openid}/messages`（群聊）或 `https://sandbox.api.q.qq.com/v2/groups/{group_openid}/messages`

**Files:**
- Modify: `backend/src/bot/bot.service.ts`

- [ ] **Step 1: 替换 sendQQ 方法为真实 HTTP 实现**

```typescript
  private async sendQQ(targetId: string, content: Record<string, unknown>): Promise<void> {
    const appId = process.env.QQ_BOT_APP_ID;
    const token = process.env.QQ_BOT_TOKEN;
    const groupOpenid = process.env.QQ_BOT_GROUP_OPENID;

    if (!appId || !token) {
      this.logger.warn('QQ Bot not configured (missing QQ_BOT_APP_ID or QQ_BOT_TOKEN), skipping send');
      return;
    }

    // QQ Bot group message API (sandbox or production based on NODE_ENV)
    const baseUrl = process.env.NODE_ENV === 'production'
      ? 'https://api.q.qq.com'
      : 'https://sandbox.api.q.qq.com';

    const url = groupOpenid
      ? `${baseUrl}/v2/groups/${groupOpenid}/messages`
      : `${baseUrl}/v2/users/${targetId}/messages`;

    // QQ Bot requires markdown or text message format
    const body = {
      msg_type: 2, // markdown message
      markdown: {
        content: typeof content.qq === 'string' ? content.qq : JSON.stringify(content),
      },
      msg_id: `acm_${Date.now()}`,
    };

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `QQBot ${token}`,
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errBody = await response.text();
        throw new Error(`QQ Bot API returned ${response.status}: ${errBody}`);
      }

      this.logger.log(`sendQQ: message sent to ${targetId || 'group'}`);
    } catch (error) {
      this.logger.error(`sendQQ failed: ${(error as Error).message}`);
      throw error;
    }
  }
```

- [ ] **Step 2: 更新 .env.example 加 QQ Bot 配置说明**

如果 `.env.example` 不存在则创建。追加以下内容（如果已有 QQ_BOT_APP_ID 则确认）：

```bash
# QQ Bot 配置（QQ Bot 官方 HTTP API）
# 申请地址: https://q.qq.com/bot
QQ_BOT_APP_ID=your_qq_bot_app_id
QQ_BOT_TOKEN=your_qq_bot_access_token
QQ_BOT_GROUP_OPENID=your_group_openid  # 可选；群聊机器人需填写
```

- [ ] **Step 3: 运行 bot service 现有单测**

```bash
cd backend
npx jest src/bot/bot.service.spec.ts --no-cache
# 预期: PASS（sendQQ 的 mock 应保持兼容）
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/bot/bot.service.ts .env.example
git commit -m "feat(bot): implement QQ Bot HTTP API integration"
```

---

### Task 5: 创建 init.sql + 修复 docker-compose 路径

**背景**：`docker-compose.yml` 引用 `./prisma/init.sql`，但文件在 `./backend/prisma/` 路径，且 `init.sql` 不存在。PGVector 扩展不会在首次启动时自动创建。

**Files:**
- Create: `backend/prisma/init.sql`
- Modify: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: 创建 backend/prisma/init.sql**

```sql
-- Auto-create PGVector extension on first database start
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify extension is available
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension failed to create';
    END IF;
END $$;
```

- [ ] **Step 2: 修正 docker-compose.yml 中 init.sql 路径**

将第 16 行：
```yaml
      - ./prisma/init.sql:/docker-entrypoint-initdb.d/init.sql
```
改为：
```yaml
      - ./backend/prisma/init.sql:/docker-entrypoint-initdb.d/init.sql
```

- [ ] **Step 3: 创建 .dockerignore**

```
node_modules
dist
coverage
.git
.env
.env.local
*.log
__pycache__
*.pyc
.pytest_cache
frontend/node_modules
frontend/dist
python/data/raw
python/data/tmp
data/
```

- [ ] **Step 4: 验证 docker compose 配置解析**

```bash
cd E:/code/ACM-Agent
docker compose config 2>&1 | head -20
# 预期: 解析成功，无报错
```

- [ ] **Step 5: Commit**

```bash
git add backend/prisma/init.sql docker-compose.yml .dockerignore
git commit -m "feat(deploy): add PGVector init.sql, fix compose path, add .dockerignore"
```

---

### Task 6: 前端 BotConfig 对接真实 API

**背景**：`BotConfig.tsx` 有两条 TODO — 加载配置和保存配置都使用 mock 数据，没有调用后端 API。后端 `BotController` 已经提供了 `GET /api/bot/configs` 和 `PATCH /api/bot/configs`。

**Files:**
- Create: `frontend/src/services/bot.ts`
- Modify: `frontend/src/pages/admin/BotConfig.tsx`

- [ ] **Step 1: 创建 frontend/src/services/bot.ts**

```typescript
import api from './api'; // existing axios instance with JWT interceptor

export interface BotConfigItem {
  id: string;
  channel: 'feishu' | 'qq';
  webhookUrl: string | null;
  enabled: boolean;
  scheduleCron: string | null;
  userId: string;
}

export interface BotConfigUpsertDto {
  channel: 'feishu' | 'qq';
  webhookUrl?: string;
  enabled?: boolean;
  scheduleCron?: string;
}

export const botApi = {
  getConfigs: () => api.get<BotConfigItem[]>('/bot/configs').then(r => r.data),
  upsertConfig: (dto: BotConfigUpsertDto) => api.patch<BotConfigItem>('/bot/configs', dto).then(r => r.data),
  testPush: (channel: 'feishu' | 'qq') => api.post<{ message: string }>('/bot/test', { channel }).then(r => r.data),
  triggerDaily: (channel: 'feishu' | 'qq', targetId: string) =>
    api.post<{ message: string }>('/bot/push/daily', { channel, targetId }).then(r => r.data),
  triggerWeekly: (channel: 'feishu' | 'qq', targetId: string) =>
    api.post<{ message: string }>('/bot/push/weekly', { channel, targetId }).then(r => r.data),
};
```

- [ ] **Step 2: 重写 BotConfig.tsx 对接 API**

```typescript
// frontend/src/pages/admin/BotConfig.tsx
import { useState, useEffect, useCallback, type FormEvent } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import { botApi, type BotConfigItem } from "../../services/bot";

interface BotConfigForm {
  feishu_webhook: string;
  feishu_enabled: boolean;
  qq_enabled: boolean;
  schedule_cron: string;
}

const DEFAULT_FORM: BotConfigForm = {
  feishu_webhook: "",
  feishu_enabled: false,
  qq_enabled: false,
  schedule_cron: "0 9 * * *",
};

export default function BotConfig() {
  const [form, setForm] = useState<BotConfigForm>(DEFAULT_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      const configs = await botApi.getConfigs();
      const feishu = configs.find(c => c.channel === 'feishu');
      const qq = configs.find(c => c.channel === 'qq');
      setForm({
        feishu_webhook: feishu?.webhookUrl ?? "",
        feishu_enabled: feishu?.enabled ?? false,
        qq_enabled: qq?.enabled ?? false,
        schedule_cron: feishu?.scheduleCron ?? qq?.scheduleCron ?? "0 9 * * *",
      });
    } catch {
      setMsg({ type: "error", text: "加载配置失败" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadConfig(); }, [loadConfig]);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSaving(true);
    try {
      // Upsert feishu config
      await botApi.upsertConfig({
        channel: 'feishu',
        webhookUrl: form.feishu_webhook || undefined,
        enabled: form.feishu_enabled,
        scheduleCron: form.schedule_cron,
      });
      // Upsert qq config (enabled only; token managed via env)
      await botApi.upsertConfig({
        channel: 'qq',
        enabled: form.qq_enabled,
        scheduleCron: form.schedule_cron,
      });
      setMsg({ type: "success", text: "机器人配置已更新" });
    } catch {
      setMsg({ type: "error", text: "配置保存失败" });
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <CircularProgress sx={{ m: 4 }} />;

  return (
    <Box sx={{ p: 3, maxWidth: 720 }}>
      <Typography variant="h4" gutterBottom>
        机器人配置 (管理员)
      </Typography>

      <Paper sx={{ p: 3 }}>
        {msg && (
          <Alert severity={msg.type} sx={{ mb: 2 }}>
            {msg.text}
          </Alert>
        )}

        <Box component="form" onSubmit={handleSave} noValidate>
          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle1" gutterBottom>
            飞书机器人
          </Typography>
          <FormControlLabel
            control={
              <Switch
                checked={form.feishu_enabled}
                onChange={(e) => setForm({ ...form, feishu_enabled: e.target.checked })}
              />
            }
            label="启用飞书推送"
          />
          <TextField
            fullWidth
            label="Webhook URL"
            margin="normal"
            value={form.feishu_webhook}
            onChange={(e) => setForm({ ...form, feishu_webhook: e.target.value })}
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
            helperText="飞书群机器人的 Webhook 地址"
          />

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle1" gutterBottom>
            QQ 机器人
          </Typography>
          <FormControlLabel
            control={
              <Switch
                checked={form.qq_enabled}
                onChange={(e) => setForm({ ...form, qq_enabled: e.target.checked })}
              />
            }
            label="启用 QQ 推送"
          />
          <Typography variant="body2" color="text.secondary">
            QQ Bot Token 通过环境变量 QQ_BOT_TOKEN 配置，无需在此填写。
          </Typography>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle1" gutterBottom>
            推送计划
          </Typography>
          <TextField
            fullWidth
            label="Cron 表达式"
            margin="normal"
            value={form.schedule_cron}
            onChange={(e) => setForm({ ...form, schedule_cron: e.target.value })}
            size="small"
            helperText='格式: "分 时 日 月 周" (如: 0 9 * * * 表示每天9点)'
          />

          <Box sx={{ mt: 3, display: "flex", gap: 2 }}>
            <Button type="submit" variant="contained" disabled={saving}>
              {saving ? <CircularProgress size={20} /> : "保存配置"}
            </Button>
            <Button variant="outlined" onClick={() => setForm(DEFAULT_FORM)}>
              重置
            </Button>
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend
npx tsc --noEmit --pretty 2>&1 | head -30
# 预期: 无新增 TS 错误
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/bot.ts frontend/src/pages/admin/BotConfig.tsx
git commit -m "feat(frontend): wire BotConfig page to real API endpoints"
```

---

### Task 7: 实现 TrainingService.getRecommend() 基础逻辑

**背景**：`getRecommend()` 返回硬编码 `{ message: '推荐功能建设中' }`。需要实现基于用户弱项标签的题目推荐。

**Files:**
- Modify: `backend/src/training/training.service.ts`

- [ ] **Step 1: 替换 getRecommend 为真实查询**

```typescript
  async getRecommend(userId: string) {
    // 1. 获取用户最新的活跃训练计划
    const plan = await this.prisma.trainingPlan.findFirst({
      where: { userId, status: 'active', deletedAt: null },
      orderBy: { createdAt: 'desc' },
    });

    // 2. 如果没有任何计划，返回空推荐
    if (!plan || !plan.weakTags || plan.weakTags.length === 0) {
      return { message: '暂无推荐 — 请先生成训练计划', problems: [] };
    }

    // 3. 按弱项标签搜索题目（使用 vector search 如果可用）
    const problems = await this.prisma.problem.findMany({
      where: {
        deletedAt: null,
        tags: { hasSome: plan.weakTags as string[] },
      },
      orderBy: { difficulty: 'asc' },
      take: 10,
      select: {
        id: true,
        title: true,
        platform: true,
        platformProblemId: true,
        difficulty: true,
        tags: true,
      },
    });

    return {
      message: `基于你的弱项标签推荐 ${problems.length} 题`,
      weakTags: plan.weakTags,
      problems,
    };
  }
```

- [ ] **Step 2: 检查 getRecommend 的 controller 端点是否需要 userId 参数**

搜索 `getRecommend` 被调用的 controller：

```bash
cd backend
npx grep -r "getRecommend" src/ --include="*.ts" -l
# 确认调用链
```

如果 controller 不需要认证/没有 `@Req()` 获取 userId，需要修改 controller 传递 userId。

- [ ] **Step 3: Commit**

```bash
git add backend/src/training/training.service.ts
git commit -m "feat(training): implement getRecommend with weak-tag-based problem query"
```

---

### Task 8: 修复 BotController 端点路径不一致

**背景**：`BotController` 使用 `@Controller('api/bot')`，但 API 全局前缀已在 `main.ts` 中设为 `api`，导致实际路径变成 `/api/api/bot/...`。

**Files:**
- Modify: `backend/src/bot/bot.controller.ts`

- [ ] **Step 1: 修正 Controller 装饰器路径**

```typescript
// 将 @Controller('api/bot') 改为 @Controller('bot')
@ApiTags('Bot')
@ApiBearerAuth()
@Controller('bot')
export class BotController {
```

- [ ] **Step 2: 检查其他 Controller 是否有同样问题**

```bash
cd backend
npx grep -r "@Controller('api/" src/ --include="*.ts"
# 预期: 如果除了 BotController 还有别的，全部改为不含 api/ 前缀
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/bot/bot.controller.ts
git commit -m "fix(bot): remove duplicate api/ prefix in BotController route"
```

---

### Task 9: 补充 TrainingService 单元测试

**背景**：`TrainingService` 没有任何单元测试。

**Files:**
- Create: `backend/test/training.service.spec.ts`

- [ ] **Step 1: 创建测试文件**

```typescript
// backend/test/training.service.spec.ts
import { Test, TestingModule } from '@nestjs/testing';
import { TrainingService } from '../src/training/training.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { PythonService } from '../src/crawler/python.service';
import { NotFoundException } from '@nestjs/common';

describe('TrainingService', () => {
  let service: TrainingService;
  let prisma: any;

  const mockPrisma = {
    trainingPlan: {
      findFirst: jest.fn(),
      create: jest.fn(),
    },
    userProfile: {
      findUnique: jest.fn(),
    },
    problem: {
      findMany: jest.fn(),
    },
  };

  const mockPython = {
    execute: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TrainingService,
        { provide: PrismaService, useValue: mockPrisma },
        { provide: PythonService, useValue: mockPython },
      ],
    }).compile();

    service = module.get<TrainingService>(TrainingService);
    prisma = mockPrisma;
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('getPlan', () => {
    it('should return active plan when exists', async () => {
      const plan = { id: 'p1', userId: 'u1', status: 'active', phase: 'topic_breakthrough' };
      mockPrisma.trainingPlan.findFirst.mockResolvedValue(plan);

      const result = await service.getPlan('u1');
      expect(result).toEqual(plan);
      expect(mockPrisma.trainingPlan.findFirst).toHaveBeenCalledWith({
        where: { userId: 'u1', status: 'active' },
        orderBy: { createdAt: 'desc' },
      });
    });

    it('should throw NotFoundException when no active plan', async () => {
      mockPrisma.trainingPlan.findFirst.mockResolvedValue(null);
      await expect(service.getPlan('u1')).rejects.toThrow(NotFoundException);
    });
  });

  describe('generatePlan', () => {
    it('should throw NotFoundException when profile missing', async () => {
      mockPrisma.userProfile.findUnique.mockResolvedValue(null);
      await expect(service.generatePlan('u1')).rejects.toThrow(NotFoundException);
    });

    it('should call PythonService and create plan on success', async () => {
      mockPrisma.userProfile.findUnique.mockResolvedValue({ id: 'pf1', userId: 'u1' });
      mockPython.execute.mockResolvedValue({
        plan: { total_problems: 7 },
        targets: { phase: 'dp', primary: ['dp', 'greedy'] },
        difficulty_curve: [1, 2, 3],
      });
      mockPrisma.trainingPlan.create.mockResolvedValue({ id: 'tp1' });

      const result = await service.generatePlan('u1');

      expect(mockPython.execute).toHaveBeenCalledWith('agents/training_agent_cli.py', {
        userId: 'u1',
        profileId: 'pf1',
        planDays: 7,
        dailyTarget: 5,
      });
      expect(mockPrisma.trainingPlan.create).toHaveBeenCalled();
      expect(result).toEqual({ id: 'tp1' });
    });

    it('should create stub plan when PythonService fails', async () => {
      mockPrisma.userProfile.findUnique.mockResolvedValue({ id: 'pf1', userId: 'u1' });
      mockPython.execute.mockRejectedValue(new Error('agent crash'));
      mockPrisma.trainingPlan.create.mockResolvedValue({ id: 'tp-fallback' });

      const result = await service.generatePlan('u1');

      expect(mockPrisma.trainingPlan.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            phase: 'topic_breakthrough',
            totalCount: 35,
          }),
        }),
      );
      expect(result).toEqual({ id: 'tp-fallback' });
    });
  });

  describe('getRecommend', () => {
    it('should return empty when no plan exists', async () => {
      mockPrisma.trainingPlan.findFirst.mockResolvedValue(null);
      const result = await service.getRecommend('u1');
      expect(result.problems).toEqual([]);
    });

    it('should return recommended problems based on weakTags', async () => {
      mockPrisma.trainingPlan.findFirst.mockResolvedValue({
        weakTags: ['dp', 'greedy'],
      });
      mockPrisma.problem.findMany.mockResolvedValue([
        { id: 'p1', title: 'Coin Change', platform: 'leetcode', difficulty: 3 },
      ]);
      const result = await service.getRecommend('u1');
      expect(result.problems.length).toBe(1);
      expect(mockPrisma.problem.findMany).toHaveBeenCalledWith(
        expect.objectContaining({
          where: expect.objectContaining({
            tags: { hasSome: ['dp', 'greedy'] },
          }),
        }),
      );
    });
  });
});
```

- [ ] **Step 2: 运行测试确认通过**

```bash
cd backend
npx jest test/training.service.spec.ts --no-cache
# 预期: 全部 PASS
```

- [ ] **Step 3: Commit**

```bash
git add backend/test/training.service.spec.ts
git commit -m "test(training): add TrainingService unit tests"
```

---

### Task 10: 检查并修复 CrawlerController.loginPlatform — 缺失的 login 脚本

**背景**：`loginScripts` 映射了 5 个平台的 login 脚本，但仅 `luogu_login.py` 存在。其余 4 个缺失会导致 fire-and-forget 调用静默失败。

**Files:**
- Modify: `backend/src/crawler/crawler.controller.ts`

- [ ] **Step 1: 在 loginPlatform 方法中检查脚本是否存在**

```typescript
  @Post('login/:platform')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Open browser login page for a platform' })
  async loginPlatform(@Param('platform') platform: string): Promise<{ accepted: boolean; platform: string; error?: string }> {
    this.logger.log(`Opening login page for platform: ${platform}`);

    const loginScript = this.loginScripts[platform];
    if (!loginScript) {
      this.logger.warn(`No login script configured for platform: ${platform}`);
      return { accepted: false, platform, error: `Unsupported platform: ${platform}` };
    }

    // Check script existence before spawning
    const scriptPath = path.resolve(__dirname, '../../../python', loginScript);
    if (!fs.existsSync(scriptPath)) {
      this.logger.warn(`Login script not found: ${scriptPath}`);
      return { accepted: false, platform, error: `Login script not available for ${platform}` };
    }

    // Fire-and-forget: spawn Python script that opens browser for manual login
    this.pythonService
      .execute(loginScript, { platform })
      .then((result) => this.logger.log(`Login script completed: ${JSON.stringify(result)}`))
      .catch((err) => this.logger.error(`Login script failed: ${err.message}`));

    return { accepted: true, platform };
  }
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/crawler/crawler.controller.ts
git commit -m "fix(crawler): add file existence check before spawning login scripts"
```

---

### Task 11: 前端 Markdown 组件测试持久化

**背景**：`Markdown.test.tsx` 是 untracked 新文件，需要提交。

**Files:**
- Track: `frontend/test/components/Markdown.test.tsx`

- [ ] **Step 1: 确认测试可运行**

```bash
cd frontend
npx vitest run test/components/Markdown.test.tsx 2>&1 | tail -20
# 预期: 全部 PASS
```

- [ ] **Step 2: Commit**

```bash
git add frontend/test/components/Markdown.test.tsx
git commit -m "test(frontend): add Markdown component tests"
```

---

### Task 12: 验证 Phase 8 已有资产 + 补充缺失

**背景**：Phase 8 的 10 个 Task 全部 unchecked，但实际上 Dockerfile.backend、frontend/Dockerfile、frontend/nginx.conf、docker-compose.yml 都已存在（可能是计划编写后按计划实现了）。需要确认哪些已完成，补上缺失的。

**Files:**
- 核查现有: `Dockerfile.backend`, `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.yml`
- 缺失: `backend/test/swagger.e2e-spec.ts`, `backend/test/docker-compose.e2e-spec.ts`, `scripts/wait-for-it.sh`, `docs/deployment-runbook.md`, `.env.example`

- [ ] **Step 1: 确认已存在的文件内容正确**

```bash
# 验证 Dockerfile.backend 可构建
docker build -f Dockerfile.backend -t acm-backend:check . 2>&1 | tail -5

# 验证前端 Dockerfile 可构建
docker build -f frontend/Dockerfile -t acm-frontend:check frontend/ 2>&1 | tail -5
```

如果构建失败，根据错误信息修复。

- [ ] **Step 2: 创建 .env.example（如不存在）**

```bash
# backend/.env.example (如果不存在)
cat > .env.example << 'EOF'
# ===== 数据库 =====
DB_PASSWORD=change_me_strong_password

# ===== 认证 =====
JWT_SECRET=change_me_to_32_chars_minimum_secret_key

# ===== LLM =====
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=sk-xxx

# ===== Bot =====
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
QQ_BOT_APP_ID=xxx
QQ_BOT_TOKEN=xxx
QQ_BOT_GROUP_OPENID=xxx

# ===== 爬虫 =====
CRAWLER_RATE_LIMIT=2
CRAWLER_USER_AGENT=ACMBot/1.0
ACM_SERVICE_TOKEN=internal_service_token
EOF
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "chore(deploy): add .env.example with all required variables"
```

---

### Task 13: 全栈启动冒烟验证

**背景**：所有修复完成后，需要验证 Docker Compose 全栈能否启动。

- [ ] **Step 1: 清理旧容器和卷**

```bash
cd E:/code/ACM-Agent
docker compose down -v 2>/dev/null || true
```

- [ ] **Step 2: 构建并启动**

```bash
docker compose up -d --build 2>&1 | tail -30
# 预期: 三个服务全部启动
```

- [ ] **Step 3: 等待就绪 + 健康检查**

```bash
sleep 30
docker compose ps
# 预期: 三个容器状态为 Up (healthy)
```

- [ ] **Step 4: 验证 API**

```bash
curl -s http://localhost:3000/api/health | head -1
# 预期: {"status":"ok",...}
```

- [ ] **Step 5: 验证前端**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/
# 预期: 200
```

- [ ] **Step 6: 初始化数据库（首次）**

```bash
docker compose exec backend npx prisma migrate deploy
docker compose exec backend npx prisma db seed
```

- [ ] **Step 7: 验证 PGVector 扩展**

```bash
docker compose exec postgres psql -U acm -d acm_agent -c "SELECT extname FROM pg_extension WHERE extname='vector';"
# 预期: 1 row (vector)
```

所有步骤通过后，记录结果。

---

## 依赖关系

```
Task 1 (CronService DI 修复)
    ↓
Task 2 (user_crawler.py)       ← 独立
    ↓
Task 3 (PracticeRecord UUID)   ← 独立
Task 4 (QQ Bot sendQQ)         ← 独立
Task 5 (init.sql + compose)    ← 独立
    ↓
Task 6 (BotConfig 前端对接)    ← 依赖 Task 8
Task 7 (getRecommend 实现)     ← 独立
Task 8 (BotController 路径)    ← 独立
Task 9 (TrainingService 单测)  ← 独立
Task 10 (loginScript 检查)     ← 独立
Task 11 (Markdown 测试提交)    ← 独立
Task 12 (Phase 8 资产核查)     ← 依赖 Task 5
    ↓
Task 13 (全栈冒烟验证)         ← 依赖全部以上
```

Task 2~5、Task 6~11 可在各自组内并行。

---

## 完成标准

| 检查项 | 标准 | 验证方式 |
|--------|------|---------|
| CronService | 四个定时任务正常调用依赖 | 启动后查看日志含 "syncObservedUsers" / "dailyPush" 等 |
| user_crawler.py | 脚本可解析参数，不报 ImportError | `python crawlers/user_crawler.py --input '{"userId":"test"}'` |
| PracticeRecord | userId / problemId 使用真实 UUID | 单元测试或日志确认不再出现 `00000000-...` |
| QQ Bot | sendQQ 发送 HTTP 请求 | 配置 QQ_BOT_TOKEN 后触发推送，查看 QQ API 日志 |
| init.sql | PGVector 扩展自动创建 | `docker compose exec postgres psql ... -c "SELECT extname..."` |
| BotConfig | 前端可加载/保存配置 | 浏览器打开 /admin/bot，修改并保存 |
| getRecommend | 返回基于弱项标签的题目 | API 调用返回实际题目数组 |
| BotController | 路径不含重复 `/api/api/` | `curl /api/bot/configs` 返回 200 |
| TrainingService 单测 | 全部 PASS | `npx jest test/training.service.spec.ts` |
| 全栈冒烟 | docker compose up 启动成功 | `curl localhost:3000/api/health` 返回 ok |
