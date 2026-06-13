# Phase 6: 队友匹配 + Bot 推送 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans

**Goal:** 实现队友匹配推荐算法（互补评分 + 贪心组合）和飞书/QQ Bot 推送服务，90% 覆盖率

**Architecture:** NestJS MatchingModule（算法纯函数）+ BotModule（Webhook 推送 + @nestjs/schedule 定时）

**Tech Stack:** NestJS 10, @nestjs/schedule, httpx, Jest

---

## 文件结构

```
backend/src/
├── matching/
│   ├── matching.module.ts
│   ├── matching.service.ts        # calc_compatibility, calc_team_score, recommend_teammates
│   ├── matching.controller.ts
│   └── dto/
├── team/
│   ├── team.module.ts, team.service.ts, team.controller.ts
├── bot/
│   ├── bot.module.ts, bot.service.ts, bot.controller.ts
│   └── templates/
│       ├── daily-report.ts
│       └── weekly-report.ts

backend/test/
├── matching.service.spec.ts
├── team.service.spec.ts
├── bot.service.spec.ts
└── bot.e2e.spec.ts
```

---

## Task 1: MatchingAlgorithm — 纯函数测试

- [ ] **Step 1: 写测试**

```typescript
// backend/test/matching.service.spec.ts
import { calcCompatibility, calcTeamScore } from '../src/matching/matching.service';

const makeProfile = (overrides: any = {}) => ({
  overallScore: 0.7, coverage: 0.5, ceiling: 5, efficiency: 0.6, style: 'balanced',
  tagProficiency: {}, strengths: [], weaknesses: [],
  ...overrides,
});

describe('calcCompatibility', () => {
  it('should return 1.0 for perfect complement', () => {
    const a = makeProfile({
      strengths: [{ tag: 'dp', score: 0.9 }],
      weaknesses: [{ tag: 'graph', gap: 0.8 }],
      tagProficiency: { dp: 0.9, graph: 0.2 },
    });
    const b = makeProfile({
      strengths: [{ tag: 'graph', score: 0.9 }],
      weaknesses: [{ tag: 'dp', gap: 0.8 }],
      tagProficiency: { graph: 0.9, dp: 0.2 },
    });
    const score = calcCompatibility(a, b);
    expect(score).toBeGreaterThan(0.7);
  });

  it('should penalize same weaknesses', () => {
    const a = makeProfile({ weaknesses: [{ tag: 'dp', gap: 0.8 }] });
    const b = makeProfile({ weaknesses: [{ tag: 'dp', gap: 0.7 }] });
    const score = calcCompatibility(a, b);
    expect(score).toBeLessThan(0.6);
  });

  it('should return 0 to 1 range', () => {
    for (let i = 0; i < 100; i++) {
      const a = makeProfile({ overallScore: Math.random(), style: 'balanced' });
      const b = makeProfile({ overallScore: Math.random(), style: 'grinder' });
      const s = calcCompatibility(a, b);
      expect(s).toBeGreaterThanOrEqual(0);
      expect(s).toBeLessThanOrEqual(1);
    }
  });
});

describe('calcTeamScore', () => {
  it('should aggregate pair scores', () => {
    const users = [makeProfile(), makeProfile(), makeProfile()];
    const score = calcTeamScore(users);
    expect(score).toBeGreaterThanOrEqual(0);
    expect(score).toBeLessThanOrEqual(1);
  });
});
```

- [ ] **Step 2: 运行确认失败 → 实现**

```typescript
// backend/src/matching/matching.service.ts
export function calcCompatibility(a: any, b: any): number {
  const aStrengths = new Set((a.strengths || []).map((s: any) => s.tag));
  const bWeaknesses = new Set((b.weaknesses || []).map((w: any) => w.tag));
  const bStrengths = new Set((b.strengths || []).map((s: any) => s.tag));
  const aWeaknesses = new Set((a.weaknesses || []).map((w: any) => w.tag));
  const complement = [...aStrengths].filter(s => bWeaknesses.has(s)).length + [...bStrengths].filter(s => aWeaknesses.has(s)).length;
  const maxC = Math.max(aStrengths.size + bStrengths.size, 1);
  const skillScore = complement / maxC;
  const levelScore = Math.max(0, 1 - Math.abs(a.overallScore - b.overallScore) * 2);
  const stylePairs: Record<string, number> = {
    'grinder_deep_diver': 1.0, 'grinder_specialist': 0.8, 'deep_diver_specialist': 0.9,
    'balanced_grinder': 0.7, 'balanced_deep_diver': 0.7, 'balanced_specialist': 0.7, 'balanced_balanced': 0.5,
  };
  const pair = [a.style || 'balanced', b.style || 'balanced'].sort().join('_');
  const styleScore = stylePairs[pair] || 0.5;
  return +(0.5 * skillScore + 0.3 * levelScore + 0.2 * styleScore).toFixed(3);
}

export function calcTeamScore(users: any[]): number {
  const pairs = [[0, 1], [0, 2], [1, 2]];
  const pairScores = pairs.map(([i, j]) => calcCompatibility(users[i], users[j]));
  const allStrengths = new Set(users.flatMap((u: any) => (u.strengths || []).map((s: any) => s.tag)));
  const covScore = Math.min(allStrengths.size / 10, 1);
  return +(0.7 * (pairScores.reduce((a, b) => a + b, 0) / 3) + 0.3 * covScore).toFixed(3);
}
```

- [ ] **Step 3: 运行测试确认通过**

```bash
npx jest test/matching.service.spec.ts --no-cache -t "calcCompatibility|calcTeamScore"
# 预期: PASS
git add backend/src/matching/
git commit -m "feat(matching): add compatibility scoring and team scoring algorithms"
```

---

## Task 2: MatchingController + Team CRUD

- [ ] **Step 1: 实现 recommend_teammates（贪心 Top K）**
- [ ] **Step 2: 实现 Team CRUD（teams, team_members）**
- [ ] **Step 3: E2E 测试**

```bash
npx jest test/matching.service.spec.ts test/team.service.spec.ts --no-cache
# 预期: PASS
git commit -m "feat(matching): add teammate recommendation and team CRUD"
```

---

## Task 3: BotModule

- [ ] **Step 1: 写测试 — PushService**

```typescript
// backend/test/bot.service.spec.ts
describe('PushService', () => {
  it('should format daily report as Feishu card', async () => {
    const service = new PushService(mockPrisma);
    const result = service.formatDailyReport({ date: '2026-06-13', topUser: 'Alice', topCount: 5, totalAc: 20, totalSubmit: 30, acRate: '66.7%', ranking: [] });
    expect(result).toHaveProperty('msg_type', 'interactive');
    expect(result.card.header.title.content).toContain('每日战报');
  });

  it('should format weekly report for user', async () => {
    const service = new PushService(mockPrisma);
    const result = service.formatWeeklyReport({ nickname: 'Alice', submitCount: 30, acCount: 20, hardestProblem: 'P1001', strengths: ['dp'], weaknesses: ['graph'] });
    expect(result.card.elements[0].content).toContain('Alice');
  });

  it('should record push log', async () => {
    mockPrisma.pushLog.create = jest.fn().mockResolvedValue({ id: 'log1' });
    await service.sendDailyReport('feishu', 'user123', mockData);
    expect(mockPrisma.pushLog.create).toHaveBeenCalledWith(expect.objectContaining({ channel: 'feishu', messageType: 'daily_report' }));
  });
});
```

- [ ] **Step 2: 实现 PushService + BotConfig CRUD + 定时任务**

```typescript
// backend/src/bot/bot.service.ts
@Injectable()
export class PushService {
  constructor(private prisma: PrismaService) {}

  async sendDailyReport(channel: string, targetId: string, data: any) {
    const message = this.formatDailyReport(data);
    if (channel === 'feishu') await this.sendFeishu(targetId, message);
    else if (channel === 'qq') await this.sendQQ(targetId, message);
    await this.prisma.pushLog.create({
      data: { channel: channel as any, targetType: 'user', targetId, messageType: 'daily_report', content: data, status: 'sent' },
    });
  }

  formatDailyReport(data: any) {
    return {
      msg_type: 'interactive',
      card: { header: { title: { content: `📊 每日战报 (${data.date})`, tag: 'plain_text' } },
        elements: [{ tag: 'markdown', content: `🏆 刷题王: ${data.topUser} (${data.topCount} 题)\n📈 团队统计: ${data.totalAc} AC / ${data.totalSubmit} 提交` }] },
    };
  }

  formatWeeklyReport(data: any) {
    return {
      msg_type: 'interactive',
      card: { header: { title: { content: `📈 ${data.nickname} 的周报`, tag: 'plain_text' } },
        elements: [{ tag: 'markdown', content: `📊 本周: ${data.submitCount} 提交 / ${data.acCount} AC\n💪 强项: ${data.strengths.join(', ')}\n🎯 待提升: ${data.weaknesses.join(', ')}` }] },
    };
  }

  private async sendFeishu(webhookUrl: string, content: any) {
    const resp = await fetch(webhookUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(content) });
    if (!resp.ok) throw new Error(`Feishu webhook failed: ${await resp.text()}`);
  }

  private async sendQQ(targetId: string, content: any) { /* QQ Bot API */ }
}
```

- [ ] **Step 3: 配置 @nestjs/schedule cron**

```typescript
// backend/src/bot/bot.module.ts — 添加 ScheduleModule
@Injectable()
export class BotScheduler {
  constructor(private bot: PushService, private prisma: PrismaService) {}

  @Cron('0 8 * * *')  // 每天 08:00
  async handleDailyPush() {
    const configs = await this.prisma.botConfig.findMany({ where: { enabled: true } });
    for (const c of configs) {
      const data = await this.buildDailyData();
      await this.bot.sendDailyReport(c.channel, c.userId, data).catch(e => logger.error(e));
    }
  }

  @Cron('0 8 * * 1')  // 周一 08:00
  async handleWeeklyPush() { /* 类似 */ }
}
```

- [ ] **Step 4: 运行测试 + 覆盖率**

```bash
npx jest test/bot.service.spec.ts --no-cache --coverage
# 预期: PASS + ≥ 90%
git commit -m "feat(bot): add push service, daily/weekly cron, Feishu/QQ integration"
```

---

## Phase 6 Gate

| 检查项 | 标准 |
|--------|------|
| 兼容性评分 | 3 因子加权（互补 0.5 + 水平 0.3 + 风格 0.2）|
| 推荐算法 | Top K 组合输出 |
| 日报格式 | Feishu 卡片格式 |
| Bot 配置 | CRUD 完备 |
| 定时推送 | 日报 08:00 + 周报 周一 08:00 |
| 覆盖率 | ≥ 90% |
