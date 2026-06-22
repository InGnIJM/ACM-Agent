# ACM-Agent RAG 检索系统升级设计

> 状态：设计完成，待审批
> 日期：2026-06-21
> 方案：A（最小改动升级）

---

## 1. 问题陈述

### 1.1 现状

当前 RAG 检索链路：

```
用户 query → Ollama embedText(query) → pgvector ANN (vector_embedding) → 返回结果
```

**核心问题**：`vector_embedding` 由完整的 `solution_summary` 生成。而 `solution_summary` 是展示版文本，混合了高价值语义、展示型细节、模板化内容、变量名、泛化易错点，不适合作为主向量文本。

### 1.2 当前数据库状态（2026-06-21）

| 指标 | 数值 |
|---|---|
| problems 总数 | 7,293 |
| solution_summary 覆盖率 | 6,666 / 7,293 (91.4%) |
| vector_embedding 覆盖率 | 6,570 / 7,293 (90.1%) |
| full_content 覆盖率 | 100% |
| problem_solutions 总数 | 64,309 |
| 新字段（retrieval_summary 等） | 全部未建 |
| 向量索引 | 无（旧 IVFFlat 已删除） |
| 平台分布 | Luogu 7,197 / LeetCode 64 / CF 21 / NowCoder 8 / AT 3 |

### 1.3 目标

构建混合检索系统，支持题意、算法、题型、易错点、相似题等多维度准确检索。

---

## 2. 架构总览

```
用户 query
  ↓
QueryAnalysisService（规则引擎, ~1ms）
  ├── 词典匹配 → algorithm_terms, problem_patterns
  ├── query_type 判断 → 权重分配
  └── query expansion → expanded_query, query_tags
  ↓
并行 3 路召回（PGVector, 同一查询，各路独立 timeout 3s）
  ├── content_vector   → cosine ANN, topK=80
  ├── vector_embedding → cosine ANN, topK=80
  └── sparse_text      → tsvector GIN (OR), topK=50
  ↓ (任何一路超时/失败 → 跳过该路，不阻塞整体)
应用层合并去重（ProblemSearchService）
  ├── Map<problem_id, CandidateRecord>
  ├── 分数归一化（各路独立 min-max 归一化后加权）
  ↓
粗排（动态权重加权求和）
  ↓ (若 Rerank 不可用 → 直接返回粗排结果)
Rerank（top 20 → llama-server /v1/rerank）
  ↓ (rerank 分数方差 < 0.01 → 回退到粗排结果)
返回 top 10/20
```

### 2.1 核心原则

- **solution_summary** = 展示版题解总结，保留不动
- **retrieval_summary** = 检索版摘要（150-350 字），用于 `vector_embedding`
- **sparse_text** = 关键词文本，用于 BM25/全文检索
- **summary_struct** = 结构化题解信息（JSON，本次存储备用，后续版本用于 rerank 特征）
- **主表负责找题目，题解表负责找证据**
- **标签不进入检索路径**（当前 `tags_normalized` 存平台原始数字 ID，与 taxonomy 标准名体系不兼容。tag boost 延后到 v2，待标签归一化后再启用）
- **检索时不强过滤 tags，先召回再加权**

---

## 3. 数据库变更

### 3.1 problems 表新增字段

```sql
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS retrieval_summary text;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS sparse_text text;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS summary_struct jsonb;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS primary_algo varchar(50);
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS sub_algos text[];
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS problem_patterns text[];
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS retrieval_summary_generated_at timestamptz;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS embedding_generated_at timestamptz;
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS embedding_version varchar(100);
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS retrieval_version varchar(100);
ALTER TABLE public.problems ADD COLUMN IF NOT EXISTS content_vector vector(1024);
```

### 3.2 problem_solutions 表新增字段

```sql
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary text;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary_vector vector(1024);
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS quality_score double precision;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS solution_type varchar(50);
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS extracted_algos text[];
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary_generated_at timestamptz;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS embedding_generated_at timestamptz;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS embedding_version varchar(100);
```

### 3.3 迁移日志表

```sql
CREATE TABLE IF NOT EXISTS public.rag_migration_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    problem_id uuid REFERENCES public.problems(id),
    solution_id uuid REFERENCES public.problem_solutions(id),
    stage varchar(100) NOT NULL,
    status varchar(50) NOT NULL,
    message text,
    old_version varchar(100),
    new_version varchar(100),
    duration_ms integer,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (problem_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_rag_migration_logs_stage_status
ON public.rag_migration_logs (stage, status);

CREATE INDEX IF NOT EXISTS idx_rag_migration_logs_problem_id
ON public.rag_migration_logs (problem_id);
```

### 3.4 向量索引（HNSW 替代 IVFFlat）

```sql
DROP INDEX IF EXISTS idx_problems_vector_embedding_ivfflat;

CREATE INDEX IF NOT EXISTS idx_problems_solution_vector_hnsw
ON public.problems USING hnsw (vector_embedding vector_cosine_ops)
WHERE deleted_at IS NULL AND vector_embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_problems_content_vector_hnsw
ON public.problems USING hnsw (content_vector vector_cosine_ops)
WHERE deleted_at IS NULL AND content_vector IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_problem_solutions_summary_vector_hnsw
ON public.problem_solutions USING hnsw (summary_vector vector_cosine_ops)
WHERE deleted_at IS NULL AND summary_vector IS NOT NULL;
```

### 3.5 关键词检索索引

```sql
CREATE INDEX IF NOT EXISTS idx_problems_sparse_text_gin
ON public.problems USING gin (to_tsvector('simple', coalesce(sparse_text, '')))
WHERE deleted_at IS NULL;
```

---

## 4. Summary 生成

### 4.1 生成流程

改造 `python/llm/summarizer.py`，`ProblemSummarizer` 新增方法：

```
输入: full_content (截取 2000 字) + solution_summary + tags_normalized
  ↓ DeepSeek LLM (temperature=0.3, response_format=json_object)
输出:
  - solution_summary (展示版，不变)
  - retrieval_summary (检索版，150-350 字)
  - sparse_text (空格分隔关键词)
  - primary_algo / sub_algos / problem_patterns
  - summary_struct (JSON)
```

### 4.2 retrieval_summary 格式要求

**必须包含**：
- 题目题型/算法子类型
- 题目模式
- 为什么适合该算法
- 核心状态/不变量/数据结构
- 高区分度易错点

**禁止包含**：
- 完整代码、大段公式、低区分度变量名
- 模板废话（"注意边界""注意初始化"）
- 泛化易错点、过多标签罗列

### 4.3 示例

```json
{
  "retrieval_summary": "本题是数独求解的约束搜索/回溯问题，问题模式是在固定9x9网格中为空格填入数字，并同时满足每行、每列和每个3x3宫内数字唯一。核心思想是按空格递归尝试候选数字，利用行、列、宫的占用状态快速判断合法性，并在失败时撤销选择继续搜索。适合使用DFS回溯、剪枝、候选数优化或位掩码加速。易错点是九宫格索引、状态恢复和找到解后的递归返回。",
  "sparse_text": "数独 Sudoku 回溯 DFS 约束搜索 剪枝 行约束 列约束 3x3宫 九宫格 位掩码 候选数 状态恢复",
  "primary_algo": "回溯",
  "sub_algos": ["DFS", "剪枝", "约束搜索"],
  "problem_patterns": ["填数约束", "组合搜索", "唯一性约束"]
}
```

---

## 5. Embedding 服务

### 5.1 模型配置

| 项目 | 值 |
|---|---|
| 模型 | `qwen3-embedding:0.6b` |
| 部署 | Ollama `/api/embed` |
| 维度 | 1024 |
| 距离 | Cosine (`<=>`) |
| 重试 | 4 次，指数退避 |

### 5.2 向量化策略

| 向量字段 | 输入文本 | instruction prefix |
|---|---|---|
| `content_vector` | `full_content` (截取前 4000 字符) | "为算法题题面生成用于题意相似检索的向量，重点关注输入输出、目标、约束条件、问题结构和场景描述。" |
| `vector_embedding` | `retrieval_summary` | "为算法题解法摘要生成用于相似题检索的向量，重点关注算法类型、题目模式、触发条件、核心思想、状态语义、不变量和高区分度易错点。" |
| `summary_vector` | `problem_solutions.summary` | 同上 |
| query embedding | 用户 query | "为用户的算法题检索请求生成向量，重点识别题意、算法意图、题型模式、数据结构、约束条件和学习目标。" |

**Instruction 实现方式**：Ollama `/api/embed` 不支持原生 instruction 参数。instruction 通过**文本拼接**实现：

```typescript
// 实测验证：有 instruction 时区分度从 0.290 → 0.308（+6%）
const text = `${instruction}\n\n${content}`;
const vec = await ollamaEmbed({ model, input: [text] });
```

Qwen3-Embedding 对指令前缀敏感——指令改变 embedding 空间但不破坏语义关系。

### 5.3 VectorService 扩展

改造 `backend/src/common/vector/vector.service.ts`，新增方法：

```typescript
embedContent(text: string): Promise<number[]>   // content_vector
embedSummary(text: string): Promise<number[]>   // vector_embedding
embedQuery(text: string): Promise<number[]>     // query search
searchByContentVector(vec: number[], topK: number): Promise<SearchHit[]>
searchBySolutionVector(vec: number[], topK: number): Promise<SearchHit[]>
setContentVector(problemId: string, vec: number[]): Promise<void>
setSolutionSummaryVector(solutionId: string, vec: number[]): Promise<void>
```

写入时记录 `embedding_version = "qwen3-embedding:0.6b@ollama"` 和 `embedding_generated_at`。

---

## 6. Query 分析与扩充

### 6.1 架构

纯规则引擎（TypeScript），不走 LLM（延迟敏感）。

新增 `backend/src/common/query-analysis/` 模块：

```
用户 query
  ↓
1. 词典匹配 → algorithm_terms, problem_patterns, keywords
2. 意图判断 → query_type (problem_semantic | algorithm_intent | error_reason)
3. 权重分配 → 按 query_type 查表
4. 扩充 → 匹配词的同义词/别名追加到 expanded_query
  ↓
QueryAnalysisResult
```

### 6.2 Query 类型判断

**词典匹配算法**（`matchAlgorithmTerms`）：

```typescript
// 从 query_expansion.json 加载词典，双向遍历匹配
// 匹配策略：中文用 includes（无边界，因中文无空格），英文用 \b 词边界
function matchAlgorithmTerms(query: string, dict: AlgoDict): MatchResult {
  const matched: string[] = [];

  for (const [algo, aliases] of Object.entries(dict)) {
    const allTerms = [algo, ...aliases];
    for (const term of allTerms) {
      let found = false;
      if (/[一-鿿]/.test(term)) {
        // 中文词：直接用 includes（无空格分词，边界正则对中文无效）
        //   实测：'(^|\\s)单调栈($|\\s)' 对 "单调栈求下一个更大" 匹配失败（53% 假阴性）
        //   风险："线段" 误匹配 "线段树"，但词典无 "线段" 条目，实际风险可控
        found = query.includes(term);
      } else {
        // 英文词：用 \b 词边界
        found = new RegExp(`\\b${escapeRegex(term)}\\b`, 'i').test(query);
      }
      if (found) {
        matched.push(algo);
        break;  // 一个算法只匹配一次
      }
    }
  }
  return { algorithmTerms: [...new Set(matched)] };
}
```

**Query 分析主逻辑**：

```typescript
function analyzeQuery(query: string): QueryAnalysisResult {
  const matched = matchAlgorithmTerms(query);

  // 易错点检测：正则词边界 + 窄化关键词，避免误匹配
  // 错误做法: query.includes('注意') — "注意数据范围" 不是易错查询
  const errorPatterns = [
    /为什么.*(错|不对|过不了|WA|TLE)/,
    /怎么(处理|避免|防止)/,
    /容易(错|出错)/,
    /(忘记|没注意|忽略了?)/,
    /(恢复|回溯).*(状态|现场)/,
    /边界.*(错|不对)/,
    /哪里(错了|不对|有问题)/,
  ];
  const hasErrorIntent = errorPatterns.some(p => p.test(query));

  if (matched.length === 0 && !hasErrorIntent) {
    return { queryType: 'problem_semantic', weights: WEIGHTS.problem_semantic };
  }
  if (hasErrorIntent) {
    return { queryType: 'error_reason', weights: WEIGHTS.error_reason };
  }
  return { queryType: 'algorithm_intent', weights: WEIGHTS.algorithm_intent };
}

// 空/null/短查询保护
function validateQuery(query: string): void {
  if (!query || query.trim().length < 2) {
    throw new BadRequestException('查询内容过短，至少输入 2 个字符');
  }
}
```

### 6.3 动态权重

```typescript
// 权重表：3 路（content / solution / keyword），tag 路延后到 v2
const WEIGHTS = {
  problem_semantic: { content: 0.60, solution: 0.30, keyword: 0.10 },
  algorithm_intent: { content: 0.20, solution: 0.55, keyword: 0.25 },
  error_reason:     { content: 0.20, solution: 0.60, keyword: 0.20 },
};
```

### 6.4 算法同义词词典

新增 `backend/src/common/query-analysis/query_expansion.json`（TypeScript 热路径直接引用，不跨语言），覆盖 80+ 算法，六大类：

| 大类 | 条目数 | 示例 |
|---|---|---|
| 动态规划 | 18 | 背包/区间DP/树形DP/状压DP/数位DP/DP优化 |
| 图论 | 16 | Dijkstra/Floyd/SPFA/拓扑排序/SCC/DSU/MST/网络流 |
| 数据结构 | 14 | 单调栈/线段树/BIT/主席树/Trie/并查集/ST表/莫队 |
| 搜索回溯 | 7 | DFS/BFS/回溯/剪枝/A*/IDA*/记忆化搜索 |
| 字符串 | 8 | KMP/Z函数/Manacher/AC自动机/后缀数组/字符串哈希 |
| 基础算法/数学 | 17 | 双指针/滑动窗口/二分/前缀和/位运算/贪心/分治/FFT |

每条格式：
```json
{
  "线段树": ["Segment Tree", "区间查询", "区间更新", "Lazy Tag", "主席树", "zkw线段树"],
  "单调栈": ["最近更大元素", "最近更小元素", "Next Greater Element", "NGE", "贡献法", "Monotonic Stack"],
  "背包问题": ["01背包", "完全背包", "多重背包", "Knapsack", "零钱兑换", "子集划分"],
  "Dijkstra": ["最短路", "非负边权", "优先队列优化", "单源最短路径", "堆优化Dijkstra"],
  "二分答案": ["最大化最小值", "最小化最大值", "判定函数", "Binary Search on Answer"],
  "网络流": ["最大流", "Dinic", "ISAP", "最小割", "费用流", "MCMF", "二分图匹配"]
}
```

**tag boost 说明**：tag boost 延后到 v2。原因是 `tags_normalized` 列当前存储的是平台原始数据（Luogu 数字 ID + LeetCode/CF 英文标签），与 taxonomy.json 的 125 个标准名体系不兼容。v2 将对 `tags_normalized` 进行全面归一化后再启用 tag 权重。v1 的 keyword 路（`sparse_text` 全文检索）已覆盖关键词匹配需求。

---

## 7. 混合检索

### 7.1 3 路并行召回

```sql
-- 路 1: vector_embedding (题解摘要向量)
SELECT id, 1 - (vector_embedding <=> :query_vec) AS solution_score
FROM problems
WHERE deleted_at IS NULL AND vector_embedding IS NOT NULL
ORDER BY vector_embedding <=> :query_vec
LIMIT 80;

-- 路 2: content_vector (题面向量)
SELECT id, 1 - (content_vector <=> :query_vec) AS content_score
FROM problems
WHERE deleted_at IS NULL AND content_vector IS NOT NULL
ORDER BY content_vector <=> :query_vec
LIMIT 80;

-- 路 3: sparse_text 关键词召回（OR 语义）
-- ⚠️ plainto_tsquery 和 websearch_to_tsquery 对 'simple' 字典均产生 AND 语义
--    实测: "单调栈 贡献法" → '单调栈' & '贡献法' (必须全部命中)
--    解决方案: 应用层构造 OR 查询串，用 to_tsquery() 代替
SELECT id,
  ts_rank(to_tsvector('simple', coalesce(sparse_text,'')), to_tsquery('simple', :keyword_or_query)) AS keyword_score
FROM problems
WHERE deleted_at IS NULL
  AND to_tsvector('simple', coalesce(sparse_text,'')) @@ to_tsquery('simple', :keyword_or_query)
ORDER BY keyword_score DESC
LIMIT 50;
```

**应用层构造 `:keyword_or_query`**：

```typescript
// keywords = ['单调栈', '贡献法', 'NGE']
// → "'单调栈' | '贡献法' | 'NGE'"  (OR 语义)
function buildOrTsQuery(keywords: string[]): string {
  return keywords.map(k => `'${k.replace(/'/g, "''")}'`).join(' | ');
}
```

**ts_rank 值范围说明**：实测 `simple` 字典对短中文文本的 ts_rank 值在 0-0.1 区间（非无界），可与 cosine 相似度 [0,1] 直接 min-max 归一化后加权。各路径独立归一化，避免跨路径数值量纲差异。

### 7.2 合并 & 粗排

```typescript
interface CandidateRecord {
  problemId: string;
  contentScore: number;    // 0-1
  solutionScore: number;   // 0-1
  keywordScore: number;    // 0-1
  matchedKeywords: string[];
  sources: string[];       // ['content_vector', 'solution_vector', 'keyword']
}

// 各路分数归一化（含单结果除零保护）
function normalizePath(scores: number[]): number[] {
  if (scores.length < 2) return scores.map(() => 1.0);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  if (max === min) return scores.map(() => 1.0);
  return scores.map(x => (x - min) / (max - min));
}

function computeRoughScore(c: CandidateRecord, w: RetrievalWeights): number {
  return c.contentScore * w.content
       + c.solutionScore * w.solution
       + c.keywordScore * w.keyword;
}
```

### 7.3 Rerank

```
粗排 top 20 → llama-server /v1/rerank → 按 relevance_score 降序 → 返回 top 10/20
```

**Rerank 输入构造**：每个 document 需控制在 ~200 token 以内，确保 20 个文档在 4096 token 窗口内。

```
Document 格式："{title} | {summary_for_rerank} | tags: {tags_normalized.join(' ')}"

summary_for_rerank 取值优先级（fallback 链）：
  1. retrieval_summary (截断至120字)
  2. solution_summary  (截断至120字)  ← retrieval_summary 未生成时
  3. full_content      (截断至120字)  ← 兜底
```

**降级策略**：llama-server 不可用时（连接拒绝/超时 2s），跳过 rerank 直接返回粗排结果。rerank 返回分数方差 < 0.01 时（GGUF 损坏特征），同样降级到粗排。

---

## 8. Rerank 服务

### 8.1 为什么不用 Ollama

Ollama 不支持 `/rerank` 端点。`qwen3-reranker:0.6b` 是序列分类模型（Sequence Classification），被 Ollama 视作 completion 模型，通过 `/api/chat` 模拟时：
- 模型强制输出 `思考` 链，消耗 token 配额
- 输出 `[0.5, 0.5, 0.5]` 无区分度
- 延迟 ~4s/次

### 8.2 解决方案

直接使用 Ollama 安装目录自带的 `llama-server.exe`，通过 `/v1/rerank` 端点。

**GGUF 文件**：不替换 Ollama blob（避免 hash 校验冲突），使用独立路径存放正确转换的 GGUF：

```bash
# GGUF 存放路径（独立于 Ollama blob）
set RERANK_GGUF=%PROJECT_ROOT%\ollama-models\qwen3-reranker\Qwen3-Reranker-0.6B.Q4_K_M.gguf
# 下载地址: https://huggingface.co/Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp

# Ollama 自带的 llama-server.exe
%LOCALAPPDATA%\Programs\Ollama\lib\ollama\llama-server.exe ^
  -m "%RERANK_GGUF%" ^
  --reranking --pooling rank ^
  --port 8088 --host 127.0.0.1 ^
  -c 4096 -ub 4096
```

**关键发现（2026-06-21 实测）**：
- Ollama 官方 blob 为错误转换的 GGUF——缺少 `cls.output.weight` 分类头，`/v1/rerank` 输出 e-17 量级随机分数
- 需从 HuggingFace 下载正确转换的 GGUF：`Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp`（Q4_K_M, ~370MB）
- **不**替换 Ollama blob（`sha256` 不匹配会导致 `ollama pull` 覆盖），使用独立文件路径
- Ollama 的 `/api/chat` 不受影响（它不需要分类头，用 chat template 兜底）

### 8.3 RerankService 接口

```typescript
// backend/src/common/rerank/rerank.service.ts
class RerankService {
  async rerank(query: string, documents: string[]): Promise<RerankResult[]>;
}
```

---

## 9. 后端服务清单

| 服务 | 路径 | 类型 | 职责 |
|---|---|---|---|
| `VectorService` | `common/vector/` | 改造 | 新增 instruction-based embedding + contentVector 读写 |
| `QueryAnalysisService` | `common/query-analysis/` | 新增 | 规则引擎 + 词典匹配 + 权重输出 |
| `ProblemSearchService` | `problem/` | 改造 | 3 路混合检索 → 合并去重 → 粗排 → 调用 rerank |
| `RerankService` | `common/rerank/` | 新增 | 封装 llama-server `/v1/rerank` |
| `RagMigrationService` | `crawler/rag-migration.service.ts` | 新增 | 断点续跑数据迁移 |
| `ProblemSummarizer` | `python/llm/summarizer.py` | 改造 | 新增 `retrieval_summary` 生成 |
| `ProblemEmbedder` | `python/llm/embedder.py` | 改造 | 支持多文本源（content/summary/solution） |

### 9.1 API 变更

| 端点 | 方法 | 说明 |
|---|---|---|
| `POST /api/problems/search/vector` | POST | **重构**：URL 不变，内部 handler 替换为混合检索逻辑，返回格式向后兼容 |
| `POST /api/crawler/rag-migrate` | POST | 触发 RAG 迁移，`?dryRun=true&limit=50&stage=all` |
| `GET /api/crawler/rag-migrate/status` | GET | 查看迁移进度 |

### 9.2 返回格式

```json
{
  "query": "单调栈求下一个更大元素的题",
  "query_analysis": {
    "query_type": "algorithm_intent",
    "expanded_query": "单调栈 下一个更大元素 Next Greater Element 贡献法",
    "algorithm_terms": ["单调栈"],
    "weights": { "content": 0.2, "solution": 0.55, "keyword": 0.25 }
  },
  "results": [{
    "problem_id": "...",
    "title": "...",
    "source_platform": "luogu",
    "difficulty_normalized": 0.6,
    "tags_normalized": ["37","42"],                     // 平台原始ID（v2归一化）
    "retrieval_summary": "...",
    "solution_summary": "...",
    "scores": {
      "content_score": 0.82,
      "solution_score": 0.91,
      "keyword_score": 0.75,
      "rough_score": 0.87,
      "rerank_score": 0.94
    },
    "matched": { "keywords": ["单调栈"], "sources": ["solution_vector", "keyword"] }
  }]
}
```

### 9.3 前端兼容方案

**原则**：新接口是旧接口的**超集**，旧前端零改动运行。

**旧接口**（当前）：
```
POST /api/problems/search/vector
Response: {
  query: string;
  results: [{ id, title, ..., similarity }];
  total: number;
}
```

**新接口**：
```
POST /api/problems/search          ← 替换旧端点
Response: {
  query: string;
  query_analysis?: { query_type, expanded_query, weights };  // 新增
  results: [{
    ...旧字段全部保留...,                                        // 向后兼容
    similarity: number;         // = roughScore，兼容旧前端
    retrieval_summary?: string;  // 新增
    scores: {                   // 新增：详细分数
      content_score, solution_score, keyword_score,
      tag_score, rough_score, rerank_score?
    };
    matched: {                  // 新增：匹配来源
      keywords: string[];
      tags: string[];
      sources: string[];        // ['content_vector','solution_vector','keyword']
    };
  }];
  total: number;
}
```

**前端 Typescript 类型兼容**：

```typescript
// 旧版（当前 frontend/src/types/problem.ts）
interface VectorSearchResultItem {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  difficultyNormalized: number;
  tagsNormalized: string[];
  solutionSummary: string | null;
  similarity: number;
}

// 新版（扩展，非破坏）
interface VectorSearchResultItem {
  // 旧字段原封不动
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  difficultyNormalized: number;
  tagsNormalized: string[];
  solutionSummary: string | null;
  similarity: number;              // 兼容 = scores.roughScore
  // 新增字段（optional，旧代码不读即可）
  retrievalSummary?: string;
  sparseText?: string;
  scores?: {
    contentScore: number;
    solutionScore: number;
    keywordScore: number;
    roughScore: number;
    rerankScore?: number;
  };
  matched?: {
    keywords: string[];
    sources: string[];
  };
}

interface VectorSearchResponse {
  query: string;
  queryAnalysis?: {
    queryType: string;
    expandedQuery: string;
    algorithmTerms: string[];
    weights: Record<string, number>;
  };
  results: VectorSearchResultItem[];
  total: number;
}
```

**前端渐进升级路径**：

| 阶段 | 改动 | 影响 |
|---|---|---|
| 1（立即） | 后端新接口上线，`similarity` = `roughScore` | 旧前端**零改动**，搜索正常 |
| 2（可选） | 侧边栏显示 `matched.keywords` / `matched.sources` | 用户可看到"为什么匹配" |
| 3（可选） | Hover 显示各路径详细分数 `scores` | 方便调试 |

**关键点**：
- `similarity` 字段保留映射到 `roughScore`（粗排加权分），旧前端 `(r.similarity * 100).toFixed(1)%` 正常显示
- `similarity > 0.7` 绿色高亮逻辑不失
- 后端保留 `POST /api/problems/search/vector` 端点 URL，内部 handler 替换为混合检索逻辑
- 前端**仅需改 1 行**：`frontend/src/services/problems.ts:35` 无需改 URL（端点不变），TypeScript 类型新增 optional 字段自动兼容

---

## 10. 数据迁移

### 10.1 迁移阶段

| 阶段 | 内容 | 处理量 | 并发 | 预估耗时 |
|---|---|---|---|---|
| 1. DDL | 新增列、建表 | 一次性 | — | < 1 min |
| 2. 生成摘要 | solution_summary → retrieval_summary + sparse_text + summary_struct | 6,666 | 10 (LLM) | ~1 hr |
| 3. 补充摘要 | 723 条无 solution_summary → LLM 一次调用同时生成 solution_summary + retrieval_summary | 723 | 10 (LLM) | ~10 min |
| 4. 生成向量 | retrieval_summary → vector_embedding; full_content → content_vector | 7,293 × 2 | 4×50 (信号量4,每批50条文本) | ~10 min |
| 5. 题解向量 | problem_solutions.summary → summary_vector | ≤ 64,309 | 4×50（按需） | ~5 min（按需） |
| 6. 建索引 | HNSW + GIN 索引 | 一次性 | — | 5-10 min |

### 10.2 断点续跑

```typescript
class RagMigrationService {
  async migrate(options: {
    dryRun: boolean;
    limit: number;         // 0 = 不限制
    fromCreatedAt?: Date;  // 断点续跑：从指定 created_at 之后继续（不用 UUID，因 UUID v4 无序）
    stage: 'summary' | 'embedding' | 'solution_summary' | 'solution_embedding' | 'all';
    concurrency: number;   // LLM=10, Embedding=4 (信号量)
    batchSize: number;     // Embedding 每批文本数=50 (Ollama batch API)
    maxRetries: number;    // 单条失败最大重试次数，默认 3
  }): Promise<MigrationReport>;
}
```

查询待处理数据（按 `created_at` 排序，保证断点续跑确定性）：
```sql
-- ⚠️ PostgreSQL 三值逻辑: created_at > NULL → NULL → WHERE 整体 false → 返回 0 行
--    因此 fromCreatedAt 为 NULL 时必须跳过 created_at 条件
SELECT * FROM problems
WHERE deleted_at IS NULL
  AND (:fromCreatedAt IS NULL OR created_at > :fromCreatedAt)
  AND (retrieval_summary IS NULL
       OR retrieval_version != :currentVer
       OR vector_embedding IS NULL
       OR embedding_version != :currentEmbVer)
  -- 跳过已成功的记录；版本升级时改 stage 名（如 'summary_v2'）自动跳过旧 UNIQUE
  AND id NOT IN (
    SELECT problem_id FROM rag_migration_logs
    WHERE stage = :currentStage AND status = 'success'
  )
ORDER BY created_at
LIMIT :limit;
```

**版本升级策略**：prompt 版本号变更时（如 `retrieval_version` 从 `v1` 升到 `v2`），使用**新 stage 名**（如 `summary_v2`）触发重新迁移。`UNIQUE(problem_id, stage)` 约束仅防同版本重复，不同版本的 stage 名自然避开约束。如需清理旧版日志：`DELETE FROM rag_migration_logs WHERE stage = 'summary_v1'`。

每条处理记录写入 `rag_migration_logs`，含 `problem_id`、`stage`、`status`、`duration_ms`、`message`。

### 10.3 回滚

- 不删旧数据：`solution_summary` 保留，`vector_embedding` 可覆盖
- 版本标识：`retrieval_version` / `embedding_version` 区分新旧
- 回退步骤：关掉混合检索路径 → 重建 IVFFlat 索引（如有需要）→ 旧 API 正常工作

---

## 11. 启动脚本

`start-backend.bat` 新增 Rerank 服务启动步骤：

```batch
echo [3/5] Checking Reranker GGUF...
REM 独立路径，不替换 Ollama blob（避免 sha256 校验冲突）
set RERANK_GGUF=%~dp0ollama-models\qwen3-reranker\Qwen3-Reranker-0.6B.Q4_K_M.gguf
if not exist "%RERANK_GGUF%" (
    echo   Reranker GGUF not found. Download from:
    echo   https://huggingface.co/Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp
    echo   Save to: %RERANK_GGUF%
    pause
    exit /b 1
)

echo [4/5] Starting Rerank service (llama-server)...
REM 检查端口占用，避免重复启动
netstat -ano | findstr ":8088.*LISTENING" >nul 2>&1
if %errorlevel% neq 0 (
    start "RerankService" /MIN ^
      "%LOCALAPPDATA%\Programs\Ollama\lib\ollama\llama-server.exe" ^
      -m "%RERANK_GGUF%" --reranking --pooling rank ^
      --port 8088 --host 127.0.0.1 -c 4096 -ub 4096
    REM 等待服务就绪
    timeout /t 3 /nobreak >nul
    curl -s http://127.0.0.1:8088/health >nul 2>&1
    if %errorlevel% neq 0 (
        echo   WARNING: Rerank service may not be ready yet
    )
    echo   Rerank service: http://127.0.0.1:8088
) else (
    echo   Rerank service already running on port 8088
)
```

---

## 12. 测试方案

### 12.1 测试集

| 类型 | query 示例 | 预期 behavior |
|---|---|---|
| 题意型 | "给一个数组，找连续区间最大和" | content_vector 权重最高 |
| 题意型 | "9x9 棋盘填数字，每行每列不能重复" | content_vector 权重最高 |
| 算法型 | "单调栈经典题" | solution_vector + keyword 权重高 |
| 算法型 | "Dijkstra最短路题" | solution_vector + keyword 权重高 |
| 易错型 | "为什么二分边界容易错" | solution_vector + keyword 权重高 |
| 易错型 | "回溯为什么要恢复状态" | solution_vector 权重最高 |
| 混合型 | "找几道用回溯解决的填数类题" | solution_vector + content_vector |
| 混合型 | "找类似解数独但是更简单的搜索题" | content_vector + solution_vector |

### 12.2 评估指标

| 指标 | 当前 (单路 ANN) | 目标 (混合检索) |
|---|---|---|
| Recall@10 | 待测量 | ≥ 0.85 |
| MRR@10 | 待测量 | ≥ 0.75 |
| NDCG@10 | 待测量 | ≥ 0.80 |
| 检索延迟（含 rerank） | ~500ms | < 3s |
| query_type 判断准确率 | N/A | ≥ 0.90 |

**评估方法**：
1. 人工标注 30-50 条 query 的 ground truth（relevant problem IDs），覆盖 4 种 query 类型
2. 升级前先跑 baseline 指标（当前单路 ANN），记录为对照
3. 升级后跑同样 query，对比 Recall/MRR/NDCG 变化
4. 同时记录延迟分布和 rerank 分数方差

### 12.3 降级/边界测试

| 场景 | 预期行为 |
|---|---|
| Ollama 不可用 | 路 1/路 2 跳过，路 3（关键词）独立返回结果 |
| llama-server 不可用 | 跳过 rerank，返回粗排 top 10 |
| GGUF 损坏（分数方差 < 0.01）| Rerank 降级到粗排 |
| `sparse_text` 全为 NULL | 路 3 返回空，路 1+路 2 正常 |
| query 为空/单字符 | 返回 400 Bad Request |
| topK 超过总问题数 | 返回全部可用结果 |
| 3 路召回均无结果 | 返回空数组 + "未找到相关题目" 提示 |

---

## 13. 文件清单

| # | 文件 | 类型 | 预计行数 |
|---|---|---|---|
| 1 | `backend/prisma/migrations/rag-upgrade.sql` | SQL | ~50 |
| 2 | `backend/src/common/vector/vector.service.ts` | 改造 | +120 |
| 3 | `backend/src/common/query-analysis/query-analysis.module.ts` | 新增 | ~15 |
| 4 | `backend/src/common/query-analysis/query-analysis.service.ts` | 新增 | ~200 |
| 5 | `backend/src/common/rerank/rerank.module.ts` | 新增 | ~15 |
| 6 | `backend/src/common/rerank/rerank.service.ts` | 新增 | ~80 |
| 7 | `backend/src/problem/problem.service.ts` | 改造 | +250 |
| 8 | `backend/src/problem/dto/search.dto.ts` | 新增 | ~60 |
| 9 | `backend/src/crawler/rag-migration.service.ts` | 新增 | ~300 |
| 10 | `python/llm/summarizer.py` | 改造 | +80 |
| 11 | `python/llm/embedder.py` | 改造 | +40 |
| 12 | `backend/src/common/query-analysis/query_expansion.json` | 新增 | ~500 |
| 13 | `backend/prisma/schema.prisma` | 改造 | +25 |
| 14 | `backend/prisma/vector-indexes.sql` | 改造 | +20 |
| 15 | `start-backend.bat` | 改造 | +25 |
| 16 | 测试文件（`test/rag-*.spec.ts`, `python/llm/test/test_*.py`） | 新增 | ~300 |
| 17 | 本设计文档 | — | — |

**总新增 ~2,000 行，改造 ~500 行。**

---

## 14. 风险与注意事项

1. **GGUF 模型转换**（🔴 高）：需从 [Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp](https://huggingface.co/Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp) 下载正确转换的 GGUF（Q4_K_M, ~370MB），存为独立文件（不替换 Ollama blob）。该仓库为个人维护，有删除风险，建议下载后纳入项目仓库。
2. **pgvector HNSW**：实测当前 pgvector 0.8.2 已支持 HNSW ✅
3. **LLM 限流**：DeepSeek API 并发设为 10，需实现重试+指数退避
4. **迁移中断**：所有 SQL 幂等，`rag_migration_logs` 有 UNIQUE 约束防重复，`fromCreatedAt` 游标保证断点续跑
5. **HNSW 建索引**：pgvector HNSW 不支持 `CONCURRENTLY`，7,293 行锁表 ~30s 可接受；64,309 行 problem_solutions 锁表 ~2min
6. **Rerank 降级**：llama-server 不可用 → 跳过 rerank 返回粗排结果；分数方差 < 0.01 → 判定 GGUF 损坏，降级到粗排
7. **Ollama 降级**：Ollama 不可用 → 仅关键词路（路 3）可独立返回结果，dense 路跳过
8. **content_vector 截断**：`full_content` 超长时截取前 4000 字符传入 embedding，避免超出模型上下文窗口
9. **`query_expansion.json` 维护**：与现有 `taxonomy.json` 功能重叠。`query_expansion.json` 聚焦搜索时的同义/中英/别名映射，`taxonomy.json` 聚焦标签归一化。两者需保持算法标准名一致。建议 `query_expansion.json` 的 key 从 `taxonomy.json` 的 `normalized_tags` 列表派生。

---

## 附录 A：Prisma Schema 变更

```prisma
model Problem {
  // ... 现有字段保留 ...
  retrievalSummary           String?    @map("retrieval_summary") @db.Text
  sparseText                 String?    @map("sparse_text") @db.Text
  summaryStruct              Json?      @map("summary_struct")
  primaryAlgo                String?    @map("primary_algo") @db.VarChar(50)
  subAlgos                   String[]   @map("sub_algos")
  problemPatterns            String[]   @map("problem_patterns")
  retrievalSummaryGeneratedAt DateTime? @map("retrieval_summary_generated_at")
  embeddingGeneratedAt       DateTime?  @map("embedding_generated_at")
  embeddingVersion           String?    @map("embedding_version") @db.VarChar(100)
  retrievalVersion           String?    @map("retrieval_version") @db.VarChar(100)
  contentVector              Unsupported("vector(1024)")? @map("content_vector")
}

model ProblemSolution {
  // ... 现有字段保留 ...
  summary             String?    @map("summary") @db.Text
  summaryVector       Unsupported("vector(1024)")? @map("summary_vector")
  qualityScore        Float?     @map("quality_score")
  solutionType        String?    @map("solution_type") @db.VarChar(50)
  extractedAlgos      String[]   @map("extracted_algos")
  summaryGeneratedAt  DateTime?  @map("summary_generated_at")
  embeddingGeneratedAt DateTime? @map("embedding_generated_at")
  embeddingVersion    String?    @map("embedding_version") @db.VarChar(100)
}
```
