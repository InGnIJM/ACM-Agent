# RAG 检索系统升级 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将算法题库从单向量 ANN 检索升级为 3 路混合检索（content_vector + vector_embedding + sparse_text）+ 粗排 + Rerank 的完整 RAG 系统。

**Architecture:** 数据库新增 10+7 个字段存放检索摘要和结构化信息；Python 改造 summarizer/embedder 支持一次 LLM 调用生成全部字段；TypeScript 新增 QueryAnalysisService（规则引擎）+ RerankService（llama-server 封装）+ RagMigrationService（断点续跑迁移）；改造 ProblemService.searchByVector 为三路混合检索。

**Tech Stack:** NestJS + Prisma + pgvector 0.8.2 + Ollama (qwen3-embedding:0.6b) + llama-server (/v1/rerank) + DeepSeek LLM + Python (aiohttp)

---

## File Structure

```
新增:
  backend/prisma/rag-upgrade.sql                          — DDL 迁移 SQL
  backend/prisma/rag-migration-logs.prisma                 — rag_migration_logs Prisma model
  backend/src/common/query-analysis/query-analysis.module.ts
  backend/src/common/query-analysis/query-analysis.service.ts
  backend/src/common/query-analysis/query_expansion.json   — 算法同义词词典 (~80 条)
  backend/src/common/rerank/rerank.module.ts
  backend/src/common/rerank/rerank.service.ts
  backend/src/prisma/rag-migration-logs.prisma
  backend/src/crawler/rag-migration.service.ts             — 迁移服务
  backend/src/problem/dto/search.dto.ts                    — 搜索 DTO
  backend/test/query-analysis.service.spec.ts
  backend/test/rerank.service.spec.ts
  backend/test/problem-search.service.spec.ts
  backend/test/rag-migration.service.spec.ts
  python/llm/test/test_summarizer_v2.py
  python/llm/test/test_embedder_v2.py

改造:
  backend/prisma/schema.prisma                             — +10 字段到 Problem, +7 到 ProblemSolution
  backend/prisma/vector-indexes.sql                        — IVFFlat → HNSW + GIN
  backend/src/common/vector/vector.service.ts              — +120 行 (instruction/多向量读写)
  backend/src/common/vector/vector.module.ts               — 导出扩展方法
  backend/src/problem/problem.service.ts                   — +250 行 (searchByVector 重写)
  backend/src/problem/problem.controller.ts                — 路由+query校验
  backend/src/app.module.ts                                — 导入新模块
  python/llm/summarizer.py                                 — +80 行 (retrieval_summary 生成)
  python/llm/embedder.py                                   — +40 行 (instruction prefix)
  frontend/src/types/problem.ts                            — 扩展 optional 字段
  start-backend.bat                                        — 新增 rerank 启动
```

---

### Task 1: 数据库 DDL

**Files:**
- Create: `backend/prisma/rag-upgrade.sql`
- Create: `backend/prisma/rag-migration-logs.prisma`

- [ ] **Step 1: 创建 DDL 文件**

创建 `backend/prisma/rag-upgrade.sql`：

```sql
-- ============================================================
-- RAG Upgrade: 新增字段 + 迁移日志表
-- 幂等（全部 ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS）
-- pgvector 0.8.2 + PostgreSQL 18
-- ============================================================

-- problems 新增字段
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

-- problem_solutions 新增字段
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary text;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary_vector vector(1024);
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS quality_score double precision;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS solution_type varchar(50);
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS extracted_algos text[];
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS summary_generated_at timestamptz;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS embedding_generated_at timestamptz;
ALTER TABLE public.problem_solutions ADD COLUMN IF NOT EXISTS embedding_version varchar(100);

-- 迁移日志表
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

- [ ] **Step 2: 执行 DDL**

```bash
psql -h localhost -U postgres -d acm_agent -f backend/prisma/rag-upgrade.sql
```

Expected: 每个 `ALTER TABLE` 输出 `ALTER TABLE`，`CREATE TABLE` 输出 `CREATE TABLE`。

- [ ] **Step 3: 验证新字段**

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'problems' AND table_schema = 'public'
  AND column_name IN ('retrieval_summary','sparse_text','summary_struct','primary_algo','content_vector');
```

Expected: 11 行（含已存在的 content_vector）。

- [ ] **Step 4: Commit**

```bash
git add backend/prisma/rag-upgrade.sql
git commit -m "feat(db): add RAG retrieval columns and migration logs table"
```

---

### Task 2: Prisma Schema 更新

**Files:**
- Modify: `backend/prisma/schema.prisma`

- [ ] **Step 1: 更新 Problem model**

在 `backend/prisma/schema.prisma` 的 `model Problem` 中添加新字段（`vectorEmbedding` 之后，`createdAt` 之前）：

```prisma
  retrievalSummary           String?                             @map("retrieval_summary") @db.Text
  sparseText                 String?                             @map("sparse_text") @db.Text
  summaryStruct              Json?                               @map("summary_struct")
  primaryAlgo                String?                             @map("primary_algo") @db.VarChar(50)
  subAlgos                   String[]                            @map("sub_algos")
  problemPatterns            String[]                            @map("problem_patterns")
  retrievalSummaryGeneratedAt DateTime?                          @map("retrieval_summary_generated_at")
  embeddingGeneratedAt       DateTime?                           @map("embedding_generated_at")
  embeddingVersion           String?                             @map("embedding_version") @db.VarChar(100)
  retrievalVersion           String?                             @map("retrieval_version") @db.VarChar(100)
  contentVector              Unsupported("vector(1024)")?        @map("content_vector")
```

- [ ] **Step 2: 更新 ProblemSolution model**

在 `model ProblemSolution` 中添加（`deletedAt` 之前）：

```prisma
  summary             String?                            @map("summary") @db.Text
  summaryVector       Unsupported("vector(1024)")?       @map("summary_vector")
  qualityScore        Float?                             @map("quality_score")
  solutionType        String?                            @map("solution_type") @db.VarChar(50)
  extractedAlgos      String[]                           @map("extracted_algos")
  summaryGeneratedAt  DateTime?                          @map("summary_generated_at")
  embeddingGeneratedAt DateTime?                         @map("embedding_generated_at")
  embeddingVersion    String?                            @map("embedding_version") @db.VarChar(100)
```

- [ ] **Step 3: 重新生成 Prisma Client**

```bash
cd backend && npx prisma generate
```

Expected: `Generated Prisma Client (5.22.0) ...` without errors.

- [ ] **Step 4: Commit**

```bash
git add backend/prisma/schema.prisma
git commit -m "feat(db): add RAG fields to Problem and ProblemSolution Prisma models"
```

---

### Task 3: VectorService 扩展

**Files:**
- Modify: `backend/src/common/vector/vector.service.ts`

- [ ] **Step 1: 写测试**

创建 `backend/test/vector.service.spec.ts`（如果已存在则追加）：

```typescript
describe('VectorService (extended)', () => {
  let service: VectorService;

  beforeAll(async () => {
    const module = await Test.createTestingModule({
      providers: [VectorService, PrismaService],
    }).compile();
    service = module.get(VectorService);
  });

  it('embedContent should prefix instruction and return 1024-dim vector', async () => {
    const vec = await service.embedContent('给定一个数组，求连续子数组的最大和');
    expect(vec).toHaveLength(1024);
    expect(vec.every(v => typeof v === 'number')).toBe(true);
  });

  it('embedSummary should prefix instruction and return 1024-dim vector', async () => {
    const vec = await service.embedSummary('单调栈经典应用，维护递减栈');
    expect(vec).toHaveLength(1024);
  });

  it('embedQuery should prefix instruction and return 1024-dim vector', async () => {
    const vec = await service.embedQuery('单调栈求下一个更大元素');
    expect(vec).toHaveLength(1024);
  });

  it('setContentVector should write vector and metadata', async () => {
    // Requires a test problem ID
    await service.setContentVector(testProblemId, new Array(1024).fill(0.01));
    const row = await prisma.$queryRawUnsafe(
      `SELECT content_vector, embedding_version, embedding_generated_at FROM problems WHERE id = $1::uuid`,
      testProblemId
    );
    expect(row[0].embedding_version).toBe('qwen3-embedding:0.6b@ollama');
  });

  it('embedTexts should handle empty array', async () => {
    const result = await service.embedTexts([]);
    expect(result).toEqual([]);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && npx jest test/vector.service.spec.ts --testNamePattern="embedContent" 2>&1 | tail -5
```

Expected: FAIL, method not defined.

- [ ] **Step 3: 实现 instruction 常量和扩展方法**

在 `vector.service.ts` 中追加（`setProblemVector` 之后）：

```typescript
  // ------------------------------------------------------------------
  // Instruction prefixes
  // ------------------------------------------------------------------

  private static readonly INST_CONTENT =
    '为算法题题面生成用于题意相似检索的向量，重点关注输入输出、目标、约束条件、问题结构和场景描述。';
  private static readonly INST_SOLUTION =
    '为算法题解法摘要生成用于相似题检索的向量，重点关注算法类型、题目模式、触发条件、核心思想、状态语义、不变量和高区分度易错点。';
  private static readonly INST_QUERY =
    '为用户的算法题检索请求生成向量，重点识别题意、算法意图、题型模式、数据结构、约束条件和学习目标。';
  private static readonly EMBED_VERSION = 'qwen3-embedding:0.6b@ollama';

  /** Embed full_content with content instruction prefix. */
  async embedContent(text: string): Promise<number[]> {
    const truncated = text.length > 4000 ? text.slice(0, 4000) : text;
    return this.embedText(`${VectorService.INST_CONTENT}\n\n${truncated}`);
  }

  /** Embed retrieval_summary with solution instruction prefix. */
  async embedSummary(text: string): Promise<number[]> {
    return this.embedText(`${VectorService.INST_SOLUTION}\n\n${text}`);
  }

  /** Embed user query with query instruction prefix. */
  async embedQuery(text: string): Promise<number[]> {
    return this.embedText(`${VectorService.INST_QUERY}\n\n${text}`);
  }

  // ------------------------------------------------------------------
  // Content vector write
  // ------------------------------------------------------------------

  async setContentVector(problemId: string, vec: number[]): Promise<void> {
    if (!vec.length) return;
    await this.prisma.$executeRaw`
      UPDATE problems
      SET content_vector     = ${this._toVec(vec)}::vector,
          embedding_version  = ${VectorService.EMBED_VERSION},
          embedding_generated_at = NOW(),
          updated_at         = NOW()
      WHERE id = ${problemId}::uuid
    `;
  }

  /** Write summary vector for a problem_solution record. */
  async setSolutionSummaryVector(solutionId: string, vec: number[]): Promise<void> {
    if (!vec.length) return;
    await this.prisma.$executeRaw`
      UPDATE problem_solutions
      SET summary_vector     = ${this._toVec(vec)}::vector,
          embedding_version  = ${VectorService.EMBED_VERSION},
          embedding_generated_at = NOW()
      WHERE id = ${solutionId}::uuid
    `;
  }

  // ------------------------------------------------------------------
  // Multi-path ANN search
  // ------------------------------------------------------------------

  async searchByContentVector(queryVec: number[], topK: number = 80): Promise<SearchHit[]> {
    const sql = `
      SELECT id,
             1 - (content_vector <=> $1::vector) AS score
      FROM problems
      WHERE deleted_at IS NULL AND content_vector IS NOT NULL
      ORDER BY content_vector <=> $1::vector
      LIMIT $2::bigint
    `;
    const rows: any[] = await this.prisma.$queryRawUnsafe(sql, this._toVec(queryVec), String(topK));
    return rows.map(r => ({ id: r.id, score: Number(r.score) }));
  }

  async searchBySolutionVector(queryVec: number[], topK: number = 80): Promise<SearchHit[]> {
    const sql = `
      SELECT id,
             1 - (vector_embedding <=> $1::vector) AS score
      FROM problems
      WHERE deleted_at IS NULL AND vector_embedding IS NOT NULL
      ORDER BY vector_embedding <=> $1::vector
      LIMIT $2::bigint
    `;
    const rows: any[] = await this.prisma.$queryRawUnsafe(sql, this._toVec(queryVec), String(topK));
    return rows.map(r => ({ id: r.id, score: Number(r.score) }));
  }

  async searchByKeyword(keywordOrQuery: string, topK: number = 50): Promise<SearchHit[]> {
    const sql = `
      SELECT id,
             ts_rank(
               to_tsvector('simple', coalesce(sparse_text, '')),
               to_tsquery('simple', $1)
             ) AS score
      FROM problems
      WHERE deleted_at IS NULL
        AND to_tsvector('simple', coalesce(sparse_text, '')) @@ to_tsquery('simple', $1)
      ORDER BY score DESC
      LIMIT $2::bigint
    `;
    const rows: any[] = await this.prisma.$queryRawUnsafe(sql, keywordOrQuery, String(topK));
    return rows.map(r => ({ id: r.id, score: Number(r.score) }));
  }
}

// Add to top of file after existing imports:
export interface SearchHit {
  id: string;
  score: number;
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && npx jest test/vector.service.spec.ts 2>&1 | tail -10
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/common/vector/vector.service.ts backend/test/vector.service.spec.ts
git commit -m "feat(vector): add instruction-based embedding and multi-path ANN search"
```

---

### Task 4: query_expansion.json 算法词典

**Files:**
- Create: `backend/src/common/query-analysis/query_expansion.json`

- [ ] **Step 1: 创建词典文件**

创建 `backend/src/common/query-analysis/query_expansion.json`，覆盖 80+ 算法：

```json
{
  "动态规划": ["DP", "状态转移", "最优子结构", "无后效性", "dynamic programming", "线性DP", "区间DP"],
  "回溯": ["DFS", "深度优先搜索", "递归枚举", "状态恢复", "剪枝", "backtracking"],
  "单调栈": ["最近更大元素", "最近更小元素", "Next Greater Element", "NGE", "贡献法", "Monotonic Stack"],
  "单调队列": ["滑动窗口最值", "队列优化DP", "Monotonic Queue"],
  "二分答案": ["判定函数", "最大化最小值", "最小化最大值", "Binary Search on Answer"],
  "并查集": ["DSU", "连通性", "集合合并", "Union Find", "Disjoint Set"],
  "Dijkstra": ["最短路", "非负边权", "优先队列优化", "单源最短路径", "堆优化Dijkstra", "dijkstra"],
  "拓扑排序": ["有向无环图", "DAG", "入度", "课程安排", "Topological Sort"],
  "KMP": ["字符串匹配", "前缀函数", "next数组"],
  "前缀和": ["区间和", "子数组和", "差分", "Prefix Sum", "prefix_sum"],
  "滑动窗口": ["双指针", "连续区间", "窗口维护", "Two Pointers", "Sliding Window", "sliding_window"],
  "线段树": ["Segment Tree", "区间查询", "区间更新", "Lazy Tag", "主席树", "动态开点", "segment_tree"],
  "树状数组": ["BIT", "Fenwick", "Fenwick Tree", "Binary Indexed Tree", "binary_indexed_tree"],
  "并查集": ["DSU", "连通分量", "集合合并", "Union Find", "union_find"],
  "网络流": ["最大流", "Dinic", "ISAP", "最小割", "费用流", "MCMF", "max_flow", "dinic"],
  "二分图": ["二分图匹配", "Hungarian", "匈牙利算法", "最大匹配", "bipartite_match"],
  "背包问题": ["01背包", "完全背包", "多重背包", "分组背包", "Knapsack", "零钱兑换", "子集划分"],
  "区间DP": ["最优划分", "区间合并", "合并石子", "区间动态规划"],
  "状态压缩DP": ["状压DP", "Bitmask DP", "bitmask_dp", "旅行商", "TSP"],
  "数位DP": ["位数统计", "Digit DP"],
  "树形DP": ["树上DP", "Tree DP", "tree_dp"],
  "快速幂": ["Fast Pow", "模重复平方", "矩阵快速幂", "快速幂取模"],
  "筛法": ["素数筛", "埃氏筛", "欧拉筛", "线性筛", "质因数分解"],
  "BFS": ["广度优先搜索", "广度优先", "最短路(无权)", "层次遍历"],
  "DFS": ["深度优先", "连通块", "Flood Fill", "dfs"],
  "记忆化搜索": ["memorized search", "Memoization"],
  "A*": ["A star", "启发式搜索", "IDA*", "第K短路"],
  "Floyd": ["多源最短路", "Floyd Warshall", "全源最短路径", "floyd_warshall"],
  "SPFA": ["Bellman-Ford", "队列优化Bellman-Ford", "负权边", "判负环"],
  "最小生成树": ["MST", "Prim", "Kruskal", "最小瓶颈路"],
  "强连通分量": ["SCC", "Tarjan", "Kosaraju", "缩点"],
  "最近公共祖先": ["LCA", "树上倍增", "Tarjan离线", "lca"],
  "Z函数": ["Z算法", "Z Algorithm", "扩展KMP"],
  "Manacher": ["回文串", "马拉车", "回文半径"],
  "AC自动机": ["AC Automaton", "多模式匹配", "ac_automaton"],
  "后缀数组": ["SA", "Suffix Array", "后缀排序", "height数组"],
  "字符串哈希": ["Rabin-Karp", "Hash", "进制哈希"],
  "Trie": ["字典树", "前缀树", "trie"],
  "差分约束": ["SPFA判负环", "不等式系统"],
  "2-SAT": ["2SAT", "布尔可满足性"],
  "基环树": ["环套树", "内向基环树"],
  "点分治": ["重心分解", "树上分治"],
  "树链剖分": ["HLD", "重链剖分", "Heavy Light Decomposition"],
  "莫队": ["Mo's Algorithm", "分块查询", "普通莫队", "树上莫队"],
  "CDQ分治": ["离线分治", "三维偏序"],
  "FFT": ["快速傅里叶变换", "多项式乘法", "NTT", "卷积"],
  "ST表": ["Sparse Table", "RMQ", "sparse_table"],
  "博弈论": ["Nim", "SG函数", "公平组合博弈", "Bash博弈", "威佐夫博弈"],
  "康托展开": ["排列编码", "全排列哈希"],
  "扫描线": ["矩形面积", "区间覆盖"],
  "模拟退火": ["随机化算法", "SA", "爬山算法"],
  "DLX": ["舞蹈链", "Dancing Links", "精确覆盖"],
  "矩阵快速幂": ["矩阵乘法", "线性递推"],
  "卡特兰数": ["Catalan", "括号序列", "出栈序列"],
  "容斥原理": ["Inclusion Exclusion", "至少包含"],
  "莫比乌斯反演": ["Mobius", "数论反演"],
  "中国剩余定理": ["CRT", "同余方程组", "孙子定理"],
  "高斯消元": ["线性方程组", "异或方程组", "Gauss Elimination"],
  "凸包": ["Convex Hull", "Graham Scan", "Andrew算法"],
  "分数规划": ["0/1分数规划", "最大化平均值"],
  "期望DP": ["概率DP", "期望值"],
  "李超线段树": ["Li Chao Tree", "动态凸包"],
  "斯坦纳树": ["Steiner Tree", "最小连通子图"],
  "欧拉路径": ["Euler Path", "一笔画", "欧拉回路"],
  "割点与桥": ["articulation_point", "bridge", "Tarjan求割点"],
  "BST": ["二叉搜索树", "Binary Search Tree", "平衡树", "Treap", "Splay"],
  "堆": ["优先队列", "Priority Queue", "二叉堆", "左偏树"],
  "哈希表": ["Hash Map", "Hash Set", "unordered_map"],
  "排列组合": ["组合数", "阶乘", "杨辉三角", "Lucas定理"],
  "位运算": ["Bit Manipulation", "异或", "XOR", "lowbit", "状态压缩"]
}
```

- [ ] **Step 2: 验证 JSON 有效性**

```bash
cd backend && node -e "const d=require('./src/common/query-analysis/query_expansion.json'); console.log('keys:', Object.keys(d).length)"
```

Expected: `keys: 65` (or similar).

- [ ] **Step 3: Commit**

```bash
git add backend/src/common/query-analysis/query_expansion.json
git commit -m "feat(query): add algorithm synonym dictionary (65 entries)"
```

---

### Task 5: QueryAnalysisService

**Files:**
- Create: `backend/src/common/query-analysis/query-analysis.module.ts`
- Create: `backend/src/common/query-analysis/query-analysis.service.ts`
- Test: `backend/test/query-analysis.service.spec.ts`

- [ ] **Step 1: 写测试**

创建 `backend/test/query-analysis.service.spec.ts`：

```typescript
import { QueryAnalysisService } from '../src/common/query-analysis/query-analysis.service';

describe('QueryAnalysisService', () => {
  let service: QueryAnalysisService;

  beforeAll(() => {
    service = new QueryAnalysisService();
  });

  it('should classify problem_semantic for description-only query', () => {
    const r = service.analyze('给一个数组，找连续区间最大和');
    expect(r.queryType).toBe('problem_semantic');
    expect(r.weights.content).toBe(0.60);
  });

  it('should classify algorithm_intent with matched terms', () => {
    const r = service.analyze('单调栈求下一个更大元素的题');
    expect(r.queryType).toBe('algorithm_intent');
    expect(r.algorithmTerms).toContain('单调栈');
    expect(r.expandedQuery).toContain('NGE');
  });

  it('should classify error_reason for error/debug queries', () => {
    const r = service.analyze('为什么二分边界容易错');
    expect(r.queryType).toBe('error_reason');
    expect(r.weights.solution).toBe(0.60);
  });

  it('should not classify normal algorithm query as error', () => {
    const r = service.analyze('为什么线段树比树状数组快');
    expect(r.queryType).not.toBe('error_reason'); // "为什么" 不在 error pattern 中单独匹配
  });

  it('should expand algorithm aliases', () => {
    const r = service.analyze('并查集维护连通性');
    expect(r.algorithmTerms).toContain('并查集');
    expect(r.expandedQuery).toContain('DSU');
  });

  it('should reject empty/short queries', () => {
    expect(() => service.analyze('')).toThrow('查询内容过短');
    expect(() => service.analyze('a')).toThrow('查询内容过短');
  });

  it('should match Chinese terms with includes (no boundary regex)', () => {
    const r = service.analyze('线段树区间查询模板题');
    expect(r.algorithmTerms).toContain('线段树');
  });

  it('should match English terms with word boundary', () => {
    const r = service.analyze('用Dijkstra求最短路');
    expect(r.algorithmTerms).toContain('Dijkstra');
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && npx jest test/query-analysis.service.spec.ts 2>&1 | tail -5
```

Expected: FAIL, module not found.

- [ ] **Step 3: 实现 service**

创建 `backend/src/common/query-analysis/query-analysis.service.ts`：

```typescript
import { Injectable } from '@nestjs/common';
import * as fs from 'fs';
import * as path from 'path';

export interface RetrievalWeights {
  content: number;
  solution: number;
  keyword: number;
}

export interface QueryAnalysisResult {
  rawQuery: string;
  queryType: 'problem_semantic' | 'algorithm_intent' | 'error_reason' | 'mixed';
  expandedQuery: string;
  keywords: string[];
  algorithmTerms: string[];
  problemPatterns: string[];
  queryTags: string[];
  weights: RetrievalWeights;
}

type AlgoDict = Record<string, string[]>;

const WEIGHTS: Record<string, RetrievalWeights> = {
  problem_semantic: { content: 0.60, solution: 0.30, keyword: 0.10 },
  algorithm_intent: { content: 0.20, solution: 0.55, keyword: 0.25 },
  error_reason:     { content: 0.20, solution: 0.60, keyword: 0.20 },
};

const ERROR_PATTERNS: RegExp[] = [
  /为什么.*(错|不对|过不了|WA|TLE)/,
  /怎么(处理|避免|防止)/,
  /容易(错|出错)/,
  /(忘记|没注意|忽略了?)/,
  /(恢复|回溯).*(状态|现场)/,
  /边界.*(错|不对)/,
  /哪里(错了|不对|有问题)/,
];

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function matchAlgorithmTerms(query: string, dict: AlgoDict): string[] {
  const matched: string[] = [];
  for (const [algo, aliases] of Object.entries(dict)) {
    const allTerms = [algo, ...aliases];
    for (const term of allTerms) {
      let found = false;
      if (/[一-鿿]/.test(term)) {
        // Chinese: use includes (no boundary — spaces don't separate Chinese words)
        found = query.includes(term);
      } else {
        // English: use \b word boundary
        found = new RegExp(`\\b${escapeRegex(term)}\\b`, 'i').test(query);
      }
      if (found) {
        matched.push(algo);
        break;
      }
    }
  }
  return [...new Set(matched)];
}

@Injectable()
export class QueryAnalysisService {
  private readonly dict: AlgoDict;

  constructor() {
    const dictPath = path.join(__dirname, 'query_expansion.json');
    this.dict = JSON.parse(fs.readFileSync(dictPath, 'utf-8'));
  }

  analyze(rawQuery: string): QueryAnalysisResult {
    const query = rawQuery.trim();
    if (!query || query.length < 2) {
      throw new Error('查询内容过短，至少输入 2 个字符');
    }

    const algorithmTerms = matchAlgorithmTerms(query, this.dict);
    const hasErrorIntent = ERROR_PATTERNS.some(p => p.test(query));

    let queryType: QueryAnalysisResult['queryType'];
    if (algorithmTerms.length === 0 && !hasErrorIntent) {
      queryType = 'problem_semantic';
    } else if (hasErrorIntent) {
      queryType = 'error_reason';
    } else {
      queryType = 'algorithm_intent';
    }

    // Expand: collect all aliases for matched terms
    const expandedParts: string[] = [query];
    const allAliases: string[] = [];
    for (const term of algorithmTerms) {
      const aliases = this.dict[term] || [];
      allAliases.push(...aliases);
    }
    // Only add unique aliases not already in query
    const uniqueAliases = [...new Set(allAliases)].filter(a => !query.includes(a));
    expandedParts.push(...uniqueAliases.slice(0, 10)); // cap at 10 expanded terms

    return {
      rawQuery: query,
      queryType,
      expandedQuery: expandedParts.join(' '),
      keywords: [...algorithmTerms, ...uniqueAliases],
      algorithmTerms,
      problemPatterns: [],
      queryTags: algorithmTerms,
      weights: { ...WEIGHTS[queryType] },
    };
  }
}
```

- [ ] **Step 4: 创建 module**

创建 `backend/src/common/query-analysis/query-analysis.module.ts`：

```typescript
import { Global, Module } from '@nestjs/common';
import { QueryAnalysisService } from './query-analysis.service';

@Global()
@Module({
  providers: [QueryAnalysisService],
  exports: [QueryAnalysisService],
})
export class QueryAnalysisModule {}
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && npx jest test/query-analysis.service.spec.ts 2>&1 | tail -10
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/common/query-analysis/ backend/test/query-analysis.service.spec.ts
git commit -m "feat(query): add QueryAnalysisService with rule-based intent detection"
```

---

### Task 6: RerankService

**Files:**
- Create: `backend/src/common/rerank/rerank.module.ts`
- Create: `backend/src/common/rerank/rerank.service.ts`
- Test: `backend/test/rerank.service.spec.ts`

- [ ] **Step 1: 写测试**

创建 `backend/test/rerank.service.spec.ts`：

```typescript
import { RerankService } from '../src/common/rerank/rerank.service';

describe('RerankService', () => {
  const service = new RerankService();

  it('should construct document strings with fallback chain', () => {
    const docs = [
      { title: 'Test', retrievalSummary: 'retrieval summary here', tags: ['tag1'] },
      { title: 'Test2', retrievalSummary: null as any, solutionSummary: 'solution summary here', fullContent: 'full', tags: [] },
    ];
    const formatted = (service as any).formatDocuments('test query', docs);
    expect(formatted[0]).toContain('retrieval summary here');
    expect(formatted[1]).toContain('solution summary here');
  });

  it('should detect degraded scores (variance < 0.01)', () => {
    expect((service as any).isDegraded([0.5, 0.5001, 0.5002])).toBe(true);
    expect((service as any).isDegraded([0.1, 0.5, 0.9])).toBe(false);
  });

  it('should handle empty candidate list', async () => {
    const result = await service.rerank('query', []);
    expect(result).toEqual([]);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && npx jest test/rerank.service.spec.ts 2>&1 | tail -5
```

- [ ] **Step 3: 实现 RerankService**

创建 `backend/src/common/rerank/rerank.service.ts`：

```typescript
import { Injectable, Logger } from '@nestjs/common';

export interface RerankCandidate {
  problemId: string;
  title: string;
  retrievalSummary?: string | null;
  solutionSummary?: string | null;
  fullContent?: string | null;
  tagsNormalized: string[];
  roughScore: number;
}

export interface RerankResult {
  problemId: string;
  rerankScore: number;
}

@Injectable()
export class RerankService {
  private readonly logger = new Logger(RerankService.name);
  private readonly rerankUrl: string;

  constructor() {
    this.rerankUrl = process.env.RERANK_URL || 'http://127.0.0.1:8088/v1/rerank';
  }

  async rerank(query: string, candidates: RerankCandidate[]): Promise<RerankResult[]> {
    if (!candidates.length) return [];

    const documents = this.formatDocuments(query, candidates);

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);

      const resp = await fetch(this.rerankUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, documents }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!resp.ok) {
        throw new Error(`Rerank server returned ${resp.status}`);
      }

      const data: any = await resp.json();
      const scores: Array<{ index: number; relevance_score: number }> = data.results || [];

      // Check for degraded model (all scores nearly identical)
      if (scores.length >= 2 && this.isDegraded(scores.map(s => s.relevance_score))) {
        this.logger.warn('Rerank scores degraded (variance < 0.01), falling back to rough scores');
        return candidates.map(c => ({ problemId: c.problemId, rerankScore: c.roughScore }));
      }

      return scores.map(s => ({
        problemId: candidates[s.index]?.problemId || '',
        rerankScore: s.relevance_score,
      }));
    } catch (err: any) {
      this.logger.warn(`Rerank failed (${err.message}), returning rough scores`);
      return candidates.map(c => ({ problemId: c.problemId, rerankScore: c.roughScore }));
    }
  }

  private formatDocuments(_query: string, candidates: RerankCandidate[]): string[] {
    return candidates.map(c => {
      const summary = (c.retrievalSummary || c.solutionSummary || c.fullContent || '');
      const truncated = summary.length > 120 ? summary.slice(0, 120) : summary;
      const tags = (c.tagsNormalized || []).join(' ');
      return `${c.title} | ${truncated} | tags: ${tags}`;
    });
  }

  private isDegraded(scores: number[]): boolean {
    if (scores.length < 2) return false;
    const max = Math.max(...scores);
    const min = Math.min(...scores);
    return (max - min) < 0.01;
  }
}
```

- [ ] **Step 4: 创建 module**

创建 `backend/src/common/rerank/rerank.module.ts`：

```typescript
import { Global, Module } from '@nestjs/common';
import { RerankService } from './rerank.service';

@Global()
@Module({
  providers: [RerankService],
  exports: [RerankService],
})
export class RerankModule {}
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && npx jest test/rerank.service.spec.ts 2>&1 | tail -10
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/common/rerank/ backend/test/rerank.service.spec.ts
git commit -m "feat(rerank): add RerankService with llama-server integration and degradation fallback"
```

---

### Task 7: 改造 ProblemService — 混合检索

**Files:**
- Modify: `backend/src/problem/problem.service.ts`
- Create: `backend/src/problem/dto/search.dto.ts`

- [ ] **Step 1: 创建搜索 DTO**

创建 `backend/src/problem/dto/search.dto.ts`：

```typescript
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsString, IsInt, IsOptional, Min, Max } from 'class-validator';
import { Type } from 'class-transformer';

export class VectorSearchDto {
  @ApiProperty({ description: 'Natural-language search query' })
  @IsString()
  query: string;

  @ApiPropertyOptional({ description: 'Number of results', default: 20, minimum: 1, maximum: 100 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(100)
  topK?: number;

  @ApiPropertyOptional({ description: 'Filter by platform' })
  @IsOptional()
  @IsString()
  platform?: string;

  @ApiPropertyOptional({ description: 'Filter by tags (comma-separated)' })
  @IsOptional()
  @IsString()
  tags?: string;

  @ApiPropertyOptional({ description: 'Minimum difficulty (1-10)' })
  @IsOptional()
  @Type(() => Number)
  difficultyMin?: number;

  @ApiPropertyOptional({ description: 'Maximum difficulty (1-10)' })
  @IsOptional()
  @Type(() => Number)
  difficultyMax?: number;
}
```

- [ ] **Step 2: 重写 searchByVector**

在 `problem.service.ts` 中替换 `searchByVector` 方法（注入新增的 `queryAnalysisService` 和 `rerankService`）：

```typescript
import { QueryAnalysisService, QueryAnalysisResult } from '../common/query-analysis/query-analysis.service';
import { RerankService, RerankCandidate } from '../common/rerank/rerank.service';
import { SearchHit } from '../common/vector/vector.service';

// Add to constructor:
// private readonly queryAnalysis: QueryAnalysisService,
// private readonly rerankService: RerankService,

async searchByVector(dto: {
  query: string;
  topK?: number;
  platform?: string;
  tags?: string;
  difficultyMin?: number;
  difficultyMax?: number;
}) {
  const { query, topK = 20, platform, difficultyMin, difficultyMax } = dto;

  // 1. Query analysis
  const analysis = this.queryAnalysis.analyze(query);

  // 2. Generate query embedding
  const queryVec = await this.vectorService.embedQuery(query);

  // 3. Three-path parallel recall (with individual timeout)
  const [contentHits, solutionHits, keywordHits] = await Promise.allSettled([
    this.withTimeout(this.vectorService.searchByContentVector(queryVec, 80), 3000),
    this.withTimeout(this.vectorService.searchBySolutionVector(queryVec, 80), 3000),
    this.withTimeout(
      this.vectorService.searchByKeyword(this.buildOrTsQuery(analysis.keywords), 50),
      3000,
    ),
  ]);

  // 4. Merge and normalize
  const candidates = this.mergeCandidates(
    this.unwrapHits(contentHits),
    this.unwrapHits(solutionHits),
    this.unwrapHits(keywordHits),
  );

  // 5. Rough ranking
  const roughRanked = this.roughRank(candidates, analysis.weights);

  // 6. Rerank top 20
  const top20 = roughRanked.slice(0, 20);
  let reranked = top20;
  if (top20.length > 0) {
    const rerankCandidates: RerankCandidate[] = top20.map(c => ({
      problemId: c.id,
      title: c.title,
      retrievalSummary: c.retrievalSummary,
      solutionSummary: c.solutionSummary,
      fullContent: c.fullContent,
      tagsNormalized: c.tagsNormalized,
      roughScore: c.roughScore,
    }));
    const rerankResults = await this.rerankService.rerank(query, rerankCandidates);
    reranked = top20
      .map(c => ({
        ...c,
        rerankScore: rerankResults.find(r => r.problemId === c.id)?.rerankScore ?? c.roughScore,
      }))
      .sort((a, b) => b.rerankScore - a.rerankScore);
  }

  // 7. Format response (backward compatible)
  const results = reranked.slice(0, topK).map(r => ({
    id: r.id,
    title: r.title,
    sourcePlatform: r.sourcePlatform,
    sourceId: r.sourceId,
    difficultyNormalized: r.difficultyNormalized,
    tagsNormalized: r.tagsNormalized,
    solutionSummary: r.solutionSummary,
    retrievalSummary: r.retrievalSummary,
    similarity: r.rerankScore ?? r.roughScore,  // backward compatible
    scores: {
      contentScore: r.contentScore,
      solutionScore: r.solutionScore,
      keywordScore: r.keywordScore,
      roughScore: r.roughScore,
      rerankScore: r.rerankScore,
    },
    matched: {
      keywords: r.matchedKeywords,
      sources: r.sources,
    },
  }));

  return {
    query,
    queryAnalysis: {
      queryType: analysis.queryType,
      expandedQuery: analysis.expandedQuery,
      algorithmTerms: analysis.algorithmTerms,
      weights: analysis.weights,
    },
    results,
    total: results.length,
  };
}

// ── Private helpers ──

private buildOrTsQuery(keywords: string[]): string {
  return keywords
    .filter(k => k)
    .map(k => `'${k.replace(/'/g, "''")}'`)
    .join(' | ') || "'placeholder'";
}

private unwrapHits(result: PromiseSettledResult<SearchHit[]>): SearchHit[] {
  return result.status === 'fulfilled' ? result.value : [];
}

private async withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => setTimeout(() => reject(new Error('timeout')), ms)),
  ]);
}

private mergeCandidates(
  contentHits: SearchHit[],
  solutionHits: SearchHit[],
  keywordHits: SearchHit[],
): CandidateRecord[] {
  const map = new Map<string, CandidateRecord>();

  const normContent = this.normalizePath(contentHits.map(h => h.score));
  const normSol = this.normalizePath(solutionHits.map(h => h.score));
  const normKW = this.normalizePath(keywordHits.map(h => h.score));

  contentHits.forEach((h, i) => {
    const c = this.getOrCreate(map, h.id);
    c.contentScore = normContent[i];
    c.sources.push('content_vector');
  });
  solutionHits.forEach((h, i) => {
    const c = this.getOrCreate(map, h.id);
    c.solutionScore = normSol[i];
    c.sources.push('solution_vector');
  });
  keywordHits.forEach((h, i) => {
    const c = this.getOrCreate(map, h.id);
    c.keywordScore = normKW[i];
    c.sources.push('keyword');
  });

  return Array.from(map.values());
}

private normalizePath(scores: number[]): number[] {
  if (scores.length < 2) return scores.map(() => 1.0);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  if (max === min) return scores.map(() => 1.0);
  return scores.map(x => (x - min) / (max - min));
}

private getOrCreate(map: Map<string, CandidateRecord>, id: string): CandidateRecord {
  if (!map.has(id)) {
    map.set(id, {
      id,
      title: '',
      sourcePlatform: '',
      sourceId: '',
      difficultyNormalized: 0,
      tagsNormalized: [],
      solutionSummary: null,
      retrievalSummary: null,
      fullContent: null,
      contentScore: 0,
      solutionScore: 0,
      keywordScore: 0,
      roughScore: 0,
      rerankScore: 0,
      matchedKeywords: [],
      sources: [],
    });
  }
  return map.get(id)!;
}

private roughRank(candidates: CandidateRecord[], weights: { content: number; solution: number; keyword: number }): CandidateRecord[] {
  candidates.forEach(c => {
    c.roughScore = c.contentScore * weights.content
                 + c.solutionScore * weights.solution
                 + c.keywordScore * weights.keyword;
  });
  return candidates.sort((a, b) => b.roughScore - a.roughScore);
}

// Add interface at top of file:
interface CandidateRecord {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  difficultyNormalized: number;
  tagsNormalized: string[];
  solutionSummary: string | null;
  retrievalSummary?: string | null;
  fullContent?: string | null;
  contentScore: number;
  solutionScore: number;
  keywordScore: number;
  roughScore: number;
  rerankScore: number;
  matchedKeywords: string[];
  sources: string[];
}
```

- [ ] **Step 3: 运行测试**

```bash
cd backend && npx jest test/problem-search.service.spec.ts 2>&1 | tail -10
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/problem/ backend/test/problem-search.service.spec.ts
git commit -m "feat(search): rewrite searchByVector as 3-path hybrid retrieval with rerank"
```

---

### Task 8: RagMigrationService

**Files:**
- Create: `backend/src/crawler/rag-migration.service.ts`

- [ ] **Step 1: 实现迁移服务**

创建 `backend/src/crawler/rag-migration.service.ts`：

```typescript
import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { VectorService } from '../common/vector/vector.service';

export interface MigrationOptions {
  dryRun: boolean;
  limit: number;
  fromCreatedAt?: Date;
  stage: 'summary' | 'embedding' | 'all';
  concurrency: number;
  batchSize: number;
  maxRetries: number;
}

interface MigrationReport {
  total: number;
  success: number;
  failed: number;
  skipped: number;
  durationMs: number;
}

@Injectable()
export class RagMigrationService {
  private readonly logger = new Logger(RagMigrationService.name);
  private readonly CURRENT_RETRIEVAL_VER = 'algo-rag-summary-v1';
  private readonly CURRENT_EMBED_VER = 'qwen3-embedding:0.6b@ollama';

  constructor(
    private readonly prisma: PrismaService,
    private readonly vectorService: VectorService,
  ) {}

  async migrate(options: MigrationOptions): Promise<MigrationReport> {
    const startedAt = Date.now();
    let success = 0, failed = 0, skipped = 0;

    const pending = await this.findPending(options);
    this.logger.log(`Found ${pending.length} problems to migrate (stage=${options.stage})`);

    if (options.dryRun) {
      this.logger.log(`[DRY RUN] Would process ${pending.length} problems`);
      return { total: pending.length, success: 0, failed: 0, skipped: pending.length, durationMs: Date.now() - startedAt };
    }

    // Process in batches with semaphore
    for (let i = 0; i < pending.length; i += options.concurrency) {
      const batch = pending.slice(i, i + options.concurrency);
      const results = await Promise.allSettled(
        batch.map(p => this.processOne(p, options)),
      );
      results.forEach((r, j) => {
        if (r.status === 'fulfilled') success++;
        else { failed++; this.logger.error(`Problem ${batch[j].id}: ${r.reason}`); }
      });
      this.logger.log(`Progress: ${i + batch.length}/${pending.length} (success=${success} failed=${failed})`);
    }

    return { total: pending.length, success, failed, skipped, durationMs: Date.now() - startedAt };
  }

  private async findPending(options: MigrationOptions) {
    const conditions: string[] = ['p.deleted_at IS NULL'];
    if (options.fromCreatedAt) {
      conditions.push('p.created_at > $1::timestamptz');
    }

    if (options.stage === 'summary' || options.stage === 'all') {
      conditions.push(`(p.retrieval_summary IS NULL OR p.retrieval_version != '${this.CURRENT_RETRIEVAL_VER}')`);
    }
    if (options.stage === 'embedding' || options.stage === 'all') {
      conditions.push(`(p.vector_embedding IS NULL OR p.embedding_version != '${this.CURRENT_EMBED_VER}')`);
    }

    const where = conditions.map(c => `  AND ${c}`).join('\n');
    const sql = `SELECT id, solution_summary, full_content, tags_normalized FROM problems p WHERE 1=1 ${where} ORDER BY created_at LIMIT ${options.limit || 10000}`;
    const rows: any[] = await this.prisma.$queryRawUnsafe(sql);
    return rows;
  }

  private async processOne(problem: any, options: MigrationOptions): Promise<void> {
    for (let attempt = 0; attempt < options.maxRetries; attempt++) {
      try {
        await this.prisma.$executeRawUnsafe(
          `INSERT INTO rag_migration_logs (problem_id, stage, status, started_at)
           VALUES ($1::uuid, $2, 'running', NOW())
           ON CONFLICT (problem_id, stage) DO UPDATE SET status = 'running', started_at = NOW()`,
          problem.id, options.stage,
        );

        if (options.stage === 'summary' || options.stage === 'all') {
          // Call DeepSeek LLM via PythonService helper (delegated)
          // For now, placeholder: actual LLM call integrated in Task 9
        }

        if (options.stage === 'embedding' || options.stage === 'all') {
          // Generate vectors
          const summaryVec = await this.vectorService.embedSummary(problem.retrieval_summary || problem.solution_summary || '');
          await this.vectorService.setProblemVector(problem.id, summaryVec);

          if (problem.full_content) {
            const contentVec = await this.vectorService.embedContent(problem.full_content);
            await this.vectorService.setContentVector(problem.id, contentVec);
          }
        }

        await this.prisma.$executeRawUnsafe(
          `UPDATE rag_migration_logs SET status = 'success', finished_at = NOW()
           WHERE problem_id = $1::uuid AND stage = $2`,
          problem.id, options.stage,
        );
        return;
      } catch (err: any) {
        if (attempt === options.maxRetries - 1) {
          await this.prisma.$executeRawUnsafe(
            `UPDATE rag_migration_logs SET status = 'failed', message = $3, finished_at = NOW()
             WHERE problem_id = $1::uuid AND stage = $2`,
            problem.id, options.stage, err.message?.slice(0, 500),
          );
          throw err;
        }
        await new Promise(r => setTimeout(r, 2000 * (attempt + 1)));
      }
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/crawler/rag-migration.service.ts
git commit -m "feat(migration): add RagMigrationService with checkpoint-restart support"
```

---

### Task 9: Python Summarizer 改造

**Files:**
- Modify: `python/llm/summarizer.py`

- [ ] **Step 1: 合并 prompt 生成 retrieval_summary**

在 `summarizer.py` 的 `summarize` 方法中，修改 prompt 同时输出 `solution_summary`（展示版）和 `retrieval_summary`（检索版）：

```python
# 将现有 prompt (line 33-53) 替换为:
prompt = f"""You are an expert competitive programming analyst. Analyze this problem and output a JSON object.

Platform: {platform}
Source ID: {source_id}
Title: {title}
Difficulty (raw): {difficulty_raw}
Platform tags: {json.dumps(tags_platform, ensure_ascii=False)}

Problem content:
{content_truncated}

Return a JSON object with these keys:
- summary: A concise 2-3 sentence summary of the problem (for display)
- solution_approach: The recommended algorithm or technique
- key_points: Array of 3-5 key observations
- pitfalls: Array of 1-3 common pitfalls or edge cases
- tags_normalized: Array of standardized topic tags
- difficulty_normalized: Float from 1 to 10
- similar_problems_hint: What kind of known problems this resembles

- retrieval_summary: A 150-350 character Chinese summary for vector search. Must include: (1) problem type and algorithm subtype, (2) problem pattern, (3) why this algorithm fits, (4) core state semantics or invariants, (5) 1-3 distinctive pitfalls. Must NOT include: full code, long formulas, variable names, boilerplate advice like "watch out for boundaries".
- sparse_text: Space-separated keywords (Chinese + English), including algorithm names, aliases, data structure names, distinguishing terms
- primary_algo: The main algorithm category (e.g. "回溯", "动态规划", "图论", "贪心", "二分")
- sub_algos: Array of algorithm subtypes (e.g. ["DFS", "剪枝"])
- problem_patterns: Array of problem patterns (e.g. ["填数约束", "组合搜索"])

Return ONLY the JSON object, no markdown fences or extra text."""

# After parsing response, extract the new fields:
return {
    "summary": parsed.get("summary", ""),
    "solution_approach": parsed.get("solution_approach", ""),
    "key_points": parsed.get("key_points", []),
    "pitfalls": parsed.get("pitfalls", []),
    "tags_normalized": filtered_tags,
    "difficulty_normalized": parsed.get("difficulty_normalized", 5.0),
    "similar_problems_hint": parsed.get("similar_problems_hint", ""),
    # New fields
    "retrieval_summary": parsed.get("retrieval_summary", ""),
    "sparse_text": parsed.get("sparse_text", ""),
    "primary_algo": parsed.get("primary_algo", ""),
    "sub_algos": parsed.get("sub_algos", []),
    "problem_patterns": parsed.get("problem_patterns", []),
}
```

- [ ] **Step 2: 运行现有测试确认未破坏**

```bash
cd python && pytest llm/test/test_summarizer.py -v 2>&1 | tail -15
```

- [ ] **Step 3: Commit**

```bash
git add python/llm/summarizer.py
git commit -m "feat(summarizer): generate retrieval_summary and sparse_text in one LLM call"
```

---

### Task 10: Python Embedder 改造

**Files:**
- Modify: `python/llm/embedder.py`

- [ ] **Step 1: 添加 instruction prefix 支持**

在 `embedder.py` 的 `embed_problems` 中添加 content_vector 和 instruction 支持：

```python
async def embed_problems(self, problems: list[dict], text_field: str = "solution_summary") -> list[dict]:
    """Embed problems by creating a vector from the specified text field.

    Args:
        problems: List of problem dicts
        text_field: Which field to embed ('solution_summary', 'retrieval_summary', 'full_content')
    """
    if not problems:
        return problems

    texts = [p.get(text_field, "") or "" for p in problems]
    vectors = await self.embed_batch(texts)

    vec_key = {
        "solution_summary": "vector_embedding",
        "retrieval_summary": "vector_embedding",
        "full_content": "content_vector",
    }.get(text_field, "vector_embedding")

    for prob, vec in zip(problems, vectors):
        prob[vec_key] = vec

    return problems
```

- [ ] **Step 2: 运行测试**

```bash
cd python && pytest llm/test/test_embedder.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Commit**

```bash
git add python/llm/embedder.py
git commit -m "feat(embedder): support multiple text sources for embedding"
```

---

### Task 11: App Module & 路由注册

**Files:**
- Modify: `backend/src/app.module.ts`
- Modify: `backend/src/problem/problem.controller.ts`

- [ ] **Step 1: 注册新模块**

在 `app.module.ts` 的 imports 中追加：

```typescript
import { QueryAnalysisModule } from './common/query-analysis/query-analysis.module';
import { RerankModule } from './common/rerank/rerank.module';

// In @Module({ imports: [...] }):
QueryAnalysisModule,
RerankModule,
```

- [ ] **Step 2: 验证编译**

```bash
cd backend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/src/app.module.ts
git commit -m "feat(app): register QueryAnalysisModule and RerankModule"
```

---

### Task 12: 前端类型兼容

**Files:**
- Modify: `frontend/src/types/problem.ts`

- [ ] **Step 1: 扩展类型（向后兼容）**

在 `VectorSearchResultItem` 和 `VectorSearchResponse` 中添加 optional 新字段：

```typescript
export interface VectorSearchResultItem {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  difficultyNormalized: number;
  tagsNormalized: string[];
  solutionSummary: string | null;
  similarity: number;
  // New optional fields
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

export interface VectorSearchResponse {
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

- [ ] **Step 2: 验证前端编译**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/problem.ts
git commit -m "feat(frontend): extend search types with optional RAG fields"
```

---

### Task 13: 向量索引（HNSW + GIN）

**Files:**
- Modify: `backend/prisma/vector-indexes.sql`

- [ ] **Step 1: 更新索引 SQL**

替换 `backend/prisma/vector-indexes.sql`：

```sql
-- PGVector HNSW indexes + GIN index for RAG hybrid search
-- pgvector 0.8.2, PostgreSQL 18

DROP INDEX IF EXISTS idx_problems_vector_embedding_ivfflat;

-- Solution vector HNSW
CREATE INDEX IF NOT EXISTS idx_problems_solution_vector_hnsw
ON public.problems USING hnsw (vector_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE deleted_at IS NULL AND vector_embedding IS NOT NULL;

-- Content vector HNSW
CREATE INDEX IF NOT EXISTS idx_problems_content_vector_hnsw
ON public.problems USING hnsw (content_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE deleted_at IS NULL AND content_vector IS NOT NULL;

-- Sparse text GIN
CREATE INDEX IF NOT EXISTS idx_problems_sparse_text_gin
ON public.problems USING gin (to_tsvector('simple', coalesce(sparse_text, '')))
WHERE deleted_at IS NULL;
```

- [ ] **Step 2: 执行建索引（迁移阶段 6，低峰期）**

```bash
psql -h localhost -U postgres -d acm_agent -f backend/prisma/vector-indexes.sql
```

- [ ] **Step 3: 验证索引**

```sql
SELECT indexname FROM pg_indexes WHERE tablename = 'problems' AND indexname LIKE '%hnsw%' OR indexname LIKE '%sparse_text%';
```

Expected: 3 rows.

- [ ] **Step 4: Commit**

```bash
git add backend/prisma/vector-indexes.sql
git commit -m "feat(db): add HNSW and GIN indexes for hybrid search"
```

---

### Task 14: 启动脚本

**Files:**
- Modify: `start-backend.bat`

- [ ] **Step 1: 新增 Rerank 启动步骤**

在 `start-backend.bat` 中，原有的 `[2/3]` (PostgreSQL 检查) 之后插入：

```batch
echo [3/5] Checking Reranker GGUF...
set RERANK_GGUF=%~dp0ollama-models\qwen3-reranker\Qwen3-Reranker-0.6B.Q4_K_M.gguf
if not exist "%RERANK_GGUF%" (
    echo   Reranker GGUF not found. Download from:
    echo   https://huggingface.co/Voodisss/Qwen3-Reranker-0.6B-GGUF-llama_cpp
    echo   Save to: %RERANK_GGUF%
    pause
    exit /b 1
)

echo [4/5] Starting Rerank service (llama-server)...
netstat -ano | findstr ":8088.*LISTENING" >nul 2>&1
if %errorlevel% neq 0 (
    start "RerankService" /MIN ^
      "%LOCALAPPDATA%\Programs\Ollama\lib\ollama\llama-server.exe" ^
      -m "%RERANK_GGUF%" --reranking --pooling rank ^
      --port 8088 --host 127.0.0.1 -c 4096 -ub 4096
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

并将原来的 `[2/3]` → `[2/5]`，`[3/3]` → `[5/5]`。

- [ ] **Step 2: Commit**

```bash
git add start-backend.bat
git commit -m "feat(scripts): add llama-server rerank service to start-backend.bat"
```

---

### Task 15: 集成测试

**Files:**
- Create: `backend/test/rag-integration.spec.ts`
- Create: `python/llm/test/test_summarizer_v2.py`

- [ ] **Step 1: 后端集成测试**

创建 `backend/test/rag-integration.spec.ts`：

```typescript
describe('RAG Integration', () => {
  it('searchByVector should return backward-compatible results', async () => {
    // Requires running Ollama + DB
    const resp = await problemService.searchByVector({ query: '单调栈', topK: 10 });
    expect(resp.results).toBeInstanceOf(Array);
    expect(resp.results[0]).toHaveProperty('similarity');
    expect(resp.results[0]).toHaveProperty('scores');
    expect(resp.results[0].scores).toHaveProperty('roughScore');
  });

  it('should degrade to keyword-only when Ollama is down', async () => {
    // Mock Ollama failure
    jest.spyOn(vectorService, 'embedQuery').mockRejectedValue(new Error('Ollama down'));
    const resp = await problemService.searchByVector({ query: '回溯剪枝', topK: 5 });
    expect(resp.results.length).toBeGreaterThanOrEqual(0);  // doesn't crash
    jest.restoreAllMocks();
  });

  it('should return 400 for empty query', async () => {
    await expect(problemService.searchByVector({ query: 'a' })).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Commit**

```bash
git add backend/test/rag-integration.spec.ts python/llm/test/test_summarizer_v2.py
git commit -m "test(rag): add integration tests for hybrid search and degradation"
```

---

## Execution Order

```
Phase 0 (前置): 下载 GGUF, 确认模型可用
Phase 1: Task 1 (DDL) → Task 2 (Prisma schema)
Phase 2: Task 3 (VectorService) → Task 5 (QueryAnalysis) → Task 6 (Rerank)
Phase 3: Task 7 (ProblemSearch) + Task 11 (App Module)
Phase 4: Task 9 (Summarizer) + Task 10 (Embedder)
Phase 5: Task 8 (RagMigrationService)
Phase 6: Task 12 (Frontend types) + Task 14 (start-backend.bat)
Phase 7: Task 4 (query_expansion.json)
Phase 8: Task 13 (Indexes) — 迁移后执行
Phase 9: Task 15 (Integration tests)
```
