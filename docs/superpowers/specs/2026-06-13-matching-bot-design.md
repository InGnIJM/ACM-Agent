# §5+§8 队友匹配与 Bot 推送详细设计

> 版本: v1.0 | 日期: 2026-06-13 | 状态: 已批准
> 基于: `2026-06-13-acm-agent-design.md` §5(匹配部分) + §8 细化

---

## Part A: 队友匹配推荐

### 1. 设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 匹配算法 | 互补性评分 + 贪心组合 | 简单有效，可解释 |
| 队伍规模 | 3 人（ACM 标准赛制） | 符合竞赛规则 |
| 匹配维度 | 技能互补 + 水平相近 + 风格多样 | 全面考虑团队协作 |
| 输出 | Top 5 推荐组合 | 给用户选择空间 |

### 2. 匹配算法

#### 2.1 互补性评分

```python
def calc_compatibility(user_a: UserProfile, user_b: UserProfile) -> float:
    """计算两个用户的兼容性得分 (0~1)"""

    # 1. 技能互补度 (权重 0.5)
    # 一方强的地方另一方弱 → 互补
    a_strengths = set(s["tag"] for s in user_a.strengths)
    b_weaknesses = set(w["tag"] for w in user_b.weaknesses)
    b_strengths = set(s["tag"] for s in user_b.strengths)
    a_weaknesses = set(w["tag"] for w in user_a.weaknesses)

    complement = len(a_strengths & b_weaknesses) + len(b_strengths & a_weaknesses)
    max_complement = max(len(a_strengths) + len(b_strengths), 1)
    skill_score = complement / max_complement

    # 2. 水平相近度 (权重 0.3)
    # 综合评分差距越小越好
    score_diff = abs(user_a.overall_score - user_b.overall_score)
    level_score = max(0, 1 - score_diff * 2)  # 差距 0.5 以上得 0

    # 3. 风格多样性 (权重 0.2)
    # 不同风格组合比相同风格好
    style_pairs = {
        ("grinder", "deep_diver"): 1.0,
        ("grinder", "specialist"): 0.8,
        ("deep_diver", "specialist"): 0.9,
        ("balanced", "grinder"): 0.7,
        ("balanced", "deep_diver"): 0.7,
        ("balanced", "specialist"): 0.7,
        ("balanced", "balanced"): 0.5,
    }
    pair = tuple(sorted([user_a.style, user_b.style]))
    style_score = style_pairs.get(pair, 0.5)

    return round(0.5 * skill_score + 0.3 * level_score + 0.2 * style_score, 3)
```

#### 2.2 三人组合评分

```python
def calc_team_score(users: list[UserProfile]) -> float:
    """三人队伍的综合评分"""
    # 两两兼容性
    pairs = [(0,1), (0,2), (1,2)]
    pair_scores = [calc_compatibility(users[i], users[j]) for i, j in pairs]

    # 技能覆盖度: 三人 strengths 合集越大越好
    all_strengths = set()
    for u in users:
        all_strengths.update(s["tag"] for s in u.strengths)
    coverage_score = min(len(all_strengths) / 10, 1.0)  # 最多 10 个不同优势

    # 综合
    avg_pair = sum(pair_scores) / len(pair_scores)
    return round(0.7 * avg_pair + 0.3 * coverage_score, 3)
```

#### 2.3 推荐算法（贪心）

```python
async def recommend_teammates(user_id: str, db, top_k: int = 5) -> list[dict]:
    """为用户推荐最佳队友组合"""
    # 获取当前用户画像
    user = await db.user_profile.find_unique(where={"userId": user_id})
    if not user:
        return []

    # 获取所有候选用户（排除自己和已组队的）
    candidates = await db.user_profile.find_many(
        where={"userId": {"not": user_id}},
        include={"user": True},
    )

    # 计算与每个候选人的兼容性
    pair_scores = []
    for c in candidates:
        score = calc_compatibility(user, c)
        pair_scores.append({"user": c, "pair_score": score})

    # 按兼容性排序，取 Top 10 候选
    pair_scores.sort(key=lambda x: x["pair_score"], reverse=True)
    top_candidates = pair_scores[:10]

    # 贪心组合: 从 Top 10 中选 2 人，使三人组合分最高
    combos = []
    for i in range(len(top_candidates)):
        for j in range(i + 1, len(top_candidates)):
            team = [user, top_candidates[i]["user"], top_candidates[j]["user"]]
            team_score = calc_team_score(team)
            combos.append({
                "teammates": [top_candidates[i]["user"], top_candidates[j]["user"]],
                "team_score": team_score,
                "pair_scores": [top_candidates[i]["pair_score"], top_candidates[j]["pair_score"]],
            })

    # 取 Top K
    combos.sort(key=lambda x: x["team_score"], reverse=True)
    return combos[:top_k]
```

### 3. API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/matching/recommend/:userId` | 推荐队友组合 |
| GET | `/api/matching/compatibility/:userId/:targetId` | 查看两人兼容性 |
| POST | `/api/teams` | 创建队伍 |
| GET | `/api/teams` | 队伍列表 |
| GET | `/api/teams/:id` | 队伍详情 |
| POST | `/api/teams/:id/members` | 添加队员 |
| DELETE | `/api/teams/:id/members/:userId` | 移除队员 |

---

## Part B: Bot 推送

### 1. 设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| Phase 1 推送方式 | Webhook（飞书）+ Bot API（QQ） | 无需公网，简单可靠 |
| 推送内容 | Markdown 卡片 | 排版美观，跨平台兼容 |
| 推送频率 | 日报 08:00 + 周报周一 08:00 | 避免打扰 |
| 推送目标 | 个人 + 群组 | 灵活配置 |

### 2. 消息模板

#### 2.1 每日推送

```
📊 {team_name} 每日战报 ({date})

🏆 刷题王: {top_user} ({top_count} 题)
📈 团队统计: {total_ac} AC / {total_submit} 提交
🎯 整体 AC 率: {ac_rate}%

📋 Top 5:
1. {user1} - {ac1} AC ✅
2. {user2} - {ac2} AC ✅
3. {user3} - {ac3} AC ✅
4. {user4} - {ac4} AC ✅
5. {user5} - {ac5} AC ✅

💡 提示: {random_tip}
```

#### 2.2 每周推送（个人）

```
📈 {nickname} 的周报 ({week_range})

📊 本周统计
- 提交: {submit_count} 次
- AC: {ac_count} 题
- AC 率: {ac_rate}%
- 最难 AC: {hardest_problem} (难度 {difficulty})

📈 趋势: {trend_emoji} {trend_label}

💪 强项: {top3_strengths}
🎯 待提升: {top3_weaknesses}

📋 下周推荐训练:
{recommended_plan_summary}
```

### 3. 推送服务

```python
class PushService:
    """Bot 推送服务"""

    def __init__(self, db):
        self.db = db

    async def send_daily_report(self, channel: str, target_id: str, data: dict):
        """发送每日报告"""
        message = self._format_daily_report(data)

        if channel == "feishu":
            await self._send_feishu_webhook(target_id, message)
        elif channel == "qq":
            await self._send_qq_message(target_id, message)

        # 记录推送日志
        await self.db.push_log.create({
            "channel": channel,
            "targetType": "user",
            "targetId": target_id,
            "messageType": "daily_report",
            "content": data,
            "status": "sent",
        })

    async def _send_feishu_webhook(self, webhook_url: str, content: dict):
        """飞书 Webhook 推送"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=content)
            if resp.status_code != 200:
                raise Exception(f"Feishu webhook failed: {resp.text}")

    async def _send_qq_message(self, group_id: str, content: str):
        """QQ Bot API 推送"""
        # QQ 开放平台 Bot API
        ...

    def _format_daily_report(self, data: dict) -> dict:
        """格式化每日报告（飞书卡片格式）"""
        return {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"content": f"📊 每日战报 ({data['date']})", "tag": "plain_text"}},
                "elements": [
                    {"tag": "markdown", "content": self._build_daily_markdown(data)},
                ],
            },
        }
```

### 4. 定时任务

| 任务 | Cron | 说明 |
|------|------|------|
| daily-push | 08:00 每天 | 推送昨日战报 |
| weekly-push | 周一 08:00 | 推送个人周报 |
| alert-push | 实时 | 连续 3 天未刷题提醒（预留） |

### 5. Bot 配置管理

```typescript
// GET /api/bot/configs — 获取当前用户的 Bot 配置
// PATCH /api/bot/configs — 更新推送偏好
// POST /api/bot/test — 测试推送

interface BotConfigDto {
  channel: "feishu" | "qq";
  webhookUrl?: string;     // 飞书 Webhook URL
  enabled: boolean;
  scheduleCron?: string;   // 自定义推送时间
}
```

### 6. Phase 2 预留（指令交互）

```
用户发送: @Bot 查画像
Bot 处理: 解析指令 → 调用 /api/profiles/:userId → 格式化返回
Bot 回复: 画像卡片

用户发送: @Bot 推荐题
Bot 处理: 解析指令 → 调用 /api/training/recommend → 格式化返回
Bot 回复: 题目列表卡片
```
