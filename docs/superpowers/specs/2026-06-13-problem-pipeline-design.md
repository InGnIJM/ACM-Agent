# §6.3 题库构建与 LLM 处理详细设计

> 版本: v1.0 | 日期: 2026-06-13 | 状态: 已批准
> 基于: `2026-06-13-acm-agent-design.md` §6.3 细化

---

## 1. 设计决策总览

| 决策项 | 选择 | 原因 |
|--------|------|------|
| LLM 模型 | DeepSeek (总结) + text-embedding-3-small (向量) | DeepSeek 性价比高，OpenAI embedding 质量好 |
| 处理流程 | 爬取 → 归一化 → LLM 总结 → 向量化 → 写 DB | 管道式，每步独立可重试 |
| 标签体系 | 三级分类（手动维护 + LLM 辅助） | 手动保证质量，LLM 辅助扩展 |
| 向量维度 | 1536 (text-embedding-3-small) | 性价比最优 |
| 批量处理 | 每批 500 条 embedding，失败重试 3 次 | 平衡效率和稳定性 |

---

## 2. 管道架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  normalizer  │────>│  summarizer  │────>│   embedder   │────>│   DB 写入    │
│  标签/难度归一│     │  LLM 总结题解│     │  文本→向量    │     │  problems    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       ↑                    ↑                    ↑
       │                    │                    │
  taxonomy.json      DeepSeek API        OpenAI/Mimo API
  (标签映射表)         (题目总结)          (向量生成)
```

**管道状态**: `raw` → `normalized` → `summarized` → `embedded` → `imported`

---

## 3. normalizer.py — 标签与难度归一化

### 3.1 标签映射表（taxonomy.json）

```json
{
  "version": "1.0",
  "categories": {
    "data_structure": {
      "subcategories": {
        "array": {
          "topics": ["prefix_sum", "diff_array", "two_pointers", "sliding_window", "binary_search"],
          "aliases": {
            "luogu": {"前缀和": "prefix_sum", "差分": "diff_array", "双指针": "two_pointers"},
            "leetcode": {"Prefix Sum": "prefix_sum", "Two Pointers": "two_pointers"},
            "codeforces": {"two pointers": "two_pointers", "binary search": "binary_search"}
          }
        },
        "tree": {
          "topics": ["binary_tree_traverse", "bst", "segment_tree", "trie", "heap", "lca"],
          "aliases": {
            "luogu": {"线段树": "segment_tree", "字典树": "trie", "堆": "heap"},
            "leetcode": {"Binary Tree": "binary_tree_traverse", "Segment Tree": "segment_tree"}
          }
        }
      }
    }
  }
}
```

### 3.2 归一化函数

```python
class TagNormalizer:
    def __init__(self, taxonomy_path: str = "taxonomy.json"):
        self.taxonomy = json.load(open(taxonomy_path))
        self._build_reverse_index()

    def _build_reverse_index(self):
        """构建 platform_tag → normalized_tag 的反向索引"""
        self.reverse_index = {}
        for cat, subcats in self.taxonomy["categories"].items():
            for sub, data in subcats["subcategories"].items():
                for platform, aliases in data.get("aliases", {}).items():
                    for raw_tag, norm_tag in aliases.items():
                        key = f"{platform}:{raw_tag.lower()}"
                        self.reverse_index[key] = norm_tag

    def normalize_tags(self, platform: str, raw_tags: list[str]) -> list[str]:
        """平台原始标签 → 归一化标签"""
        normalized = set()
        for tag in raw_tags:
            key = f"{platform}:{tag.lower()}"
            if key in self.reverse_index:
                normalized.add(self.reverse_index[key])
            else:
                # 未知标签，标记为待人工审核
                normalized.add(f"unmapped:{tag}")
        return list(normalized)


class DifficultyNormalizer:
    """跨平台难度归一化到 1~10"""

    # 各平台难度映射表
    MAPPINGS = {
        "luogu": {
            "入门": 1, "普及-": 2, "普及/提高-": 3, "普及+/提高": 4,
            "提高+/省选-": 5, "省选/NOI-": 6, "NOI/NOI+": 7, "NOI+": 8
        },
        "leetcode": {
            "Easy": 3, "Medium": 5, "Hard": 8
        },
        "codeforces": lambda r: max(1, min(10, (r - 800) / 300 + 1)),
        "atcoder": lambda r: max(1, min(10, (r - 100) / 300 + 1)),
        "nowcoder": lambda d: max(1, min(10, d / 5)),
    }

    def normalize(self, platform: str, raw_difficulty) -> float:
        mapping = self.MAPPINGS.get(platform)
        if mapping is None:
            return 5.0  # 默认中间值
        if callable(mapping):
            return round(mapping(raw_difficulty), 1)
        return float(mapping.get(str(raw_difficulty), 5.0))
```

---

## 4. summarizer.py — LLM 题目总结

### 4.1 Prompt 设计

```python
SUMMARIZE_PROMPT = """
你是 ACM 竞赛教练。请对以下题目生成结构化总结。

## 题目信息
- 平台: {platform}
- 题号: {source_id}
- 标题: {title}
- 原始难度: {difficulty_raw}
- 原始标签: {tags_platform}
- 题面: {full_content}

## 输出要求（JSON 格式）
{{
  "summary": "一句话总结题目核心考点（50字以内）",
  "solution_approach": "推荐解法思路（100字以内）",
  "key_points": ["关键点1", "关键点2"],
  "pitfalls": ["易错点1", "易错点2"],
  "tags_normalized": ["从标准标签库中选择，最多5个"],
  "difficulty_normalized": 5.0,
  "similar_problems_hint": "类似题目的特征描述（50字）"
}}

## 标签库（必须从中选择）
{taxonomy_tags}
"""
```

### 4.2 调用逻辑

```python
class ProblemSummarizer:
    def __init__(self, deepseek_client, normalizer: TagNormalizer):
        self.llm = deepseek_client
        self.normalizer = normalizer

    async def summarize(self, problem: dict) -> dict:
        """生成题目总结"""
        taxonomy_tags = self.normalizer.get_all_tags()

        prompt = SUMMARIZE_PROMPT.format(
            platform=problem["source_platform"],
            source_id=problem["source_id"],
            title=problem["title"],
            difficulty_raw=problem.get("difficulty_raw", ""),
            tags_platform=json.dumps(problem.get("tags_platform", []), ensure_ascii=False),
            full_content=problem.get("full_content", "")[:3000],  # 截断过长题面
            taxonomy_tags=", ".join(taxonomy_tags),
        )

        response = await self.llm.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        # 校验 tags_normalized 是否在标准库内
        valid_tags = self.normalizer.get_all_tags()
        result["tags_normalized"] = [
            t for t in result["tags_normalized"] if t in valid_tags
        ]

        return result
```

### 4.3 LLM 总结存储格式

`problems.solution_summary` 字段内容：

```
【核心考点】背包 DP 的基础应用
【推荐解法】0-1 背包模板题，dp[i][j] 表示前 i 个物品容量 j 的最大价值
【关键点】状态转移方程 dp[i][j] = max(dp[i-1][j], dp[i-1][j-w]+v)
【易错点】空间优化时需逆序遍历
【相似特征】背包问题变种，涉及容量和价值两个维度
```

---

## 5. embedder.py — 向量生成

### 5.1 批量 Embedding

```python
class ProblemEmbedder:
    def __init__(self, openai_client, batch_size: int = 500):
        self.client = openai_client
        self.batch_size = batch_size

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量"""
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            for attempt in range(3):
                try:
                    response = await self.client.embeddings.create(
                        model="text-embedding-3-small",
                        input=batch,
                    )
                    all_embeddings.extend([e.embedding for e in response.data])
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)
        return all_embeddings

    async def embed_problems(self, problems: list[dict]) -> list[dict]:
        """为题目生成向量"""
        # 父向量: LLM 总结全文
        summaries = [p["solution_summary"] for p in problems]
        parent_vectors = await self.embed_batch(summaries)

        # 子向量: 完整题面
        contents = [p.get("full_content", "") for p in problems]
        content_vectors = await self.embed_batch(contents)

        for i, p in enumerate(problems):
            p["vector_embedding"] = parent_vectors[i]
            p["content_vector"] = content_vectors[i]

        return problems
```

### 5.2 题解向量化

```python
async def embed_solutions(self, solutions: list[dict]) -> list[dict]:
    """为题解生成向量"""
    texts = [s["content"][:2000] for s in solutions]  # 截断过长题解
    vectors = await self.embed_batch(texts)
    for i, s in enumerate(solutions):
        s["vector_embedding"] = vectors[i]
    return solutions
```

---

## 6. 完整处理管道

```python
class ProblemPipeline:
    """题目处理管道: 归一化 → LLM 总结 → 向量化 → 写 DB"""

    def __init__(self, db, llm, openai_client):
        self.normalizer = TagNormalizer()
        self.diff_normalizer = DifficultyNormalizer()
        self.summarizer = ProblemSummarizer(llm, self.normalizer)
        self.embedder = ProblemEmbedder(openai_client)
        self.db = db

    async def process_problem(self, raw_problem: dict) -> dict:
        """处理单道题目"""
        # Step 1: 归一化
        raw_problem["tags_normalized"] = self.normalizer.normalize_tags(
            raw_problem["source_platform"],
            raw_problem.get("tags_platform", [])
        )
        raw_problem["difficulty_normalized"] = self.diff_normalizer.normalize(
            raw_problem["source_platform"],
            raw_problem.get("difficulty_raw")
        )

        # Step 2: LLM 总结
        summary = await self.summarizer.summarize(raw_problem)
        raw_problem["solution_summary"] = self._format_summary(summary)
        raw_problem["tags_normalized"] = summary.get("tags_normalized", raw_problem["tags_normalized"])

        # Step 3: 向量化
        embedded = await self.embedder.embed_problems([raw_problem])

        # Step 4: 写 DB (upsert)
        await self._upsert_problem(embedded[0])

        return embedded[0]

    async def process_batch(self, problems: list[dict]) -> dict:
        """批量处理"""
        stats = {"processed": 0, "errors": 0}
        for p in problems:
            try:
                await self.process_problem(p)
                stats["processed"] += 1
            except Exception as e:
                logger.error(f"Error processing {p.get('source_id')}: {e}")
                stats["errors"] += 1
        return stats

    async def _upsert_problem(self, problem: dict):
        """写入数据库（upsert 语义）"""
        await self.db.problem.upsert(
            where={"sourcePlatform_sourceId": {
                "sourcePlatform": problem["source_platform"],
                "sourceId": problem["source_id"],
            }},
            create={...},
            update={...},
        )
```

---

## 7. 定时任务

| 任务 | Cron | 说明 |
|------|------|------|
| sync-problems | 03:00 每天 | 爬取新题目 → 处理管道 |
| re-embed | 周日 03:00 | 重新向量化（模型更新时触发） |
| update-taxonomy | 手动 | 更新标签映射表 |

---

## 8. CLI 入口

```bash
# 处理单个平台的题目
python python/llm/pipeline.py --platform luogu --action process --count 100

# 重新向量化所有题目
python python/llm/pipeline.py --action re-embed

# 更新标签映射
python python/llm/normalizer.py --update-taxonomy
```

---

## 9. 依赖项

```
# requirements.txt
openai>=1.0.0          # DeepSeek + Embedding API
tqdm>=4.0.0            # 进度条
```
