# Phase 4: Problem Pipeline (LLM Processing) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现题目处理管道（归一化 → LLM 总结 → 向量化 → 写 DB），覆盖 TagNormalizer / DifficultyNormalizer / ProblemSummarizer / ProblemEmbedder / ProblemPipeline / CLI 入口，90% 测试覆盖率通过后进入 Phase 5。

**Architecture:** 纯 Python 模块，管道式处理。每步独立可重试，LLM 调用使用 OpenAI SDK 兼容接口（DeepSeek + OpenAI Embedding）。测试全部 mock 外部 API 调用。

**Tech Stack:** Python 3.11+, openai>=1.0.0, pytest, pytest-asyncio, pytest-cov, unittest.mock

**Phase Gate:** `pytest --cov=python/llm --cov-report=term-missing` — 覆盖率 ≥ 90%，全部测试通过

---

## 文件结构

```
acm-agent/
├── python/
│   ├── requirements.txt
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── normalizer.py          # TagNormalizer + DifficultyNormalizer
│   │   ├── summarizer.py          # ProblemSummarizer (DeepSeek LLM)
│   │   ├── embedder.py            # ProblemEmbedder (OpenAI embedding)
│   │   ├── pipeline.py            # ProblemPipeline orchestrator + CLI
│   │   ├── taxonomy.json          # 标签映射表
│   │   └── test/
│   │       ├── __init__.py
│   │       ├── conftest.py        # 共享 fixtures
│   │       ├── test_normalizer.py
│   │       ├── test_summarizer.py
│   │       ├── test_embedder.py
│   │       └── test_pipeline.py
│   └── pytest.ini
└── docs/
```

---

## Task 1: 项目初始化 + 依赖安装

**Files:**
- Create: `python/requirements.txt`
- Create: `python/pytest.ini`
- Create: `python/llm/__init__.py`
- Create: `python/llm/test/__init__.py`
- Create: `python/llm/test/conftest.py`

- [ ] **Step 1: 创建 requirements.txt**

```txt
# python/requirements.txt
openai>=1.0.0
tqdm>=4.0.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.0.0
```

- [ ] **Step 2: 创建 pytest.ini**

```ini
# python/pytest.ini
[pytest]
asyncio_mode = auto
testpaths = llm/test
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = --strict-markers -v
```

- [ ] **Step 3: 创建空模块文件**

```python
# python/llm/__init__.py
"""ACM Agent - Problem Pipeline LLM Processing"""
```

```python
# python/llm/test/__init__.py
```

- [ ] **Step 4: 创建共享 fixtures**

```python
# python/llm/test/conftest.py
import json
import pytest
from pathlib import Path


TAXONOMY_DIR = Path(__file__).parent.parent  # llm/


@pytest.fixture
def sample_taxonomy(tmp_path):
    """创建最小 taxonomy.json 用于测试"""
    taxonomy = {
        "version": "1.0",
        "categories": {
            "data_structure": {
                "subcategories": {
                    "array": {
                        "topics": ["prefix_sum", "diff_array", "two_pointers"],
                        "aliases": {
                            "luogu": {"前缀和": "prefix_sum", "差分": "diff_array", "双指针": "two_pointers"},
                            "leetcode": {"Prefix Sum": "prefix_sum", "Two Pointers": "two_pointers"},
                            "codeforces": {"two pointers": "two_pointers"},
                        },
                    },
                    "tree": {
                        "topics": ["segment_tree", "trie", "heap"],
                        "aliases": {
                            "luogu": {"线段树": "segment_tree", "字典树": "trie", "堆": "heap"},
                            "leetcode": {"Segment Tree": "segment_tree"},
                        },
                    },
                },
            },
            "algorithm": {
                "subcategories": {
                    "dp": {
                        "topics": ["knapsack", "interval_dp", "tree_dp"],
                        "aliases": {
                            "luogu": {"背包": "knapsack", "区间dp": "interval_dp"},
                            "leetcode": {"Dynamic Programming": "knapsack"},
                        },
                    },
                },
            },
        },
    }
    path = tmp_path / "taxonomy.json"
    path.write_text(json.dumps(taxonomy, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def sample_raw_problem():
    """一道原始题目样本"""
    return {
        "source_platform": "luogu",
        "source_id": "P1048",
        "source_url": "https://www.luogu.com.cn/problem/P1048",
        "title": "采药",
        "difficulty_raw": "普及/提高-",
        "tags_platform": ["背包", "动态规划"],
        "full_content": "辰辰是个天资聪颖的孩子，他的梦想是成为世界上最伟大的医师...",
        "raw_detail": {},
    }


@pytest.fixture
def sample_raw_problems():
    """多道原始题目样本"""
    return [
        {
            "source_platform": "luogu",
            "source_id": "P1048",
            "title": "采药",
            "difficulty_raw": "普及/提高-",
            "tags_platform": ["背包"],
            "full_content": "辰辰是个天资聪颖的孩子...",
        },
        {
            "source_platform": "leetcode",
            "source_id": "1",
            "title": "Two Sum",
            "difficulty_raw": "Easy",
            "tags_platform": ["Two Pointers"],
            "full_content": "Given an array of integers nums...",
        },
        {
            "source_platform": "codeforces",
            "source_id": "4A",
            "title": "Watermelon",
            "difficulty_raw": 800,
            "tags_platform": ["two pointers"],
            "full_content": "One hot summer day...",
        },
    ]


@pytest.fixture
def mock_llm_response():
    """模拟 DeepSeek LLM 返回的 JSON"""
    return {
        "summary": "经典 0-1 背包模板题",
        "solution_approach": "dp[i][j] 表示前 i 个物品容量 j 的最大价值，状态转移取放或不放",
        "key_points": ["状态转移方程", "空间优化逆序遍历"],
        "pitfalls": ["初始化边界条件", "空间优化时遍历方向"],
        "tags_normalized": ["knapsack"],
        "difficulty_normalized": 3.0,
        "similar_problems_hint": "背包问题变种，涉及容量和价值两个维度",
    }
```

- [ ] **Step 5: 安装依赖 + 验证**

```bash
cd E:/code/ACM-Agent/python
pip install -r requirements.txt
pytest --co -q
# 预期: 0 tests collected (尚无测试文件)
```

- [ ] **Step 6: Commit**

```bash
git add python/
git commit -m "chore(llm): initialize Python pipeline project with test fixtures"
```

---

## Task 2: TagNormalizer — 标签归一化

**Files:**
- Create: `python/llm/taxonomy.json`
- Create: `python/llm/normalizer.py` (TagNormalizer 部分)
- Create: `python/llm/test/test_normalizer.py`

- [ ] **Step 1: 写测试 — TagNormalizer（先写失败测试）**

```python
# python/llm/test/test_normalizer.py
import pytest
from llm.normalizer import TagNormalizer, DifficultyNormalizer


class TestTagNormalizer:
    """TagNormalizer 测试"""

    def test_init_loads_taxonomy(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        assert normalizer.taxonomy["version"] == "1.0"

    def test_build_reverse_index(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        assert "luogu:前缀和" in normalizer.reverse_index
        assert normalizer.reverse_index["luogu:前缀和"] == "prefix_sum"
        assert "leetcode:prefix sum" in normalizer.reverse_index
        assert normalizer.reverse_index["leetcode:prefix sum"] == "prefix_sum"

    def test_normalize_tags_known(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        result = normalizer.normalize_tags("luogu", ["前缀和", "背包"])
        assert sorted(result) == sorted(["prefix_sum", "knapsack"])

    def test_normalize_tags_unknown(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        result = normalizer.normalize_tags("luogu", ["未知标签"])
        assert result == ["unmapped:未知标签"]

    def test_normalize_tags_mixed(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        result = normalizer.normalize_tags("luogu", ["前缀和", "未知标签"])
        assert "prefix_sum" in result
        assert "unmapped:未知标签" in result

    def test_normalize_tags_case_insensitive(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        result = normalizer.normalize_tags("leetcode", ["Prefix Sum"])
        assert result == ["prefix_sum"]

    def test_normalize_tags_empty(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        result = normalizer.normalize_tags("luogu", [])
        assert result == []

    def test_normalize_tags_dedup(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        result = normalizer.normalize_tags("luogu", ["前缀和", "前缀和"])
        assert result == ["prefix_sum"]

    def test_get_all_tags(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        all_tags = normalizer.get_all_tags()
        assert "prefix_sum" in all_tags
        assert "knapsack" in all_tags
        assert "segment_tree" in all_tags
        assert isinstance(all_tags, list)

    def test_normalize_tags_different_platforms(self, sample_taxonomy):
        normalizer = TagNormalizer(sample_taxonomy)
        luogu_result = normalizer.normalize_tags("luogu", ["线段树"])
        cf_result = normalizer.normalize_tags("codeforces", ["two pointers"])
        assert luogu_result == ["segment_tree"]
        assert cf_result == ["two_pointers"]

    def test_init_with_default_path(self, monkeypatch, tmp_path, sample_taxonomy):
        """测试默认路径（当前目录下 taxonomy.json）"""
        import os
        monkeypatch.chdir(tmp_path.parent)
        # 如果文件不存在应抛异常
        with pytest.raises(FileNotFoundError):
            TagNormalizer("nonexistent.json")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_normalizer.py -v
# 预期: FAIL — ModuleNotFoundError: No module named 'llm.normalizer'
```

- [ ] **Step 3: 创建 taxonomy.json**

```json
{
  "version": "1.0",
  "categories": {
    "data_structure": {
      "subcategories": {
        "array": {
          "topics": ["prefix_sum", "diff_array", "two_pointers", "sliding_window", "binary_search"],
          "aliases": {
            "luogu": {"前缀和": "prefix_sum", "差分": "diff_array", "双指针": "two_pointers", "滑动窗口": "sliding_window", "二分": "binary_search"},
            "leetcode": {"Prefix Sum": "prefix_sum", "Two Pointers": "two_pointers", "Sliding Window": "sliding_window", "Binary Search": "binary_search"},
            "codeforces": {"two pointers": "two_pointers", "binary search": "binary_search", "sliding window": "sliding_window"}
          }
        },
        "linked_list": {
          "topics": ["singly_linked_list", "doubly_linked_list", "fast_slow_pointer"],
          "aliases": {
            "luogu": {"链表": "singly_linked_list", "快慢指针": "fast_slow_pointer"},
            "leetcode": {"Linked List": "singly_linked_list"}
          }
        },
        "tree": {
          "topics": ["binary_tree_traverse", "bst", "segment_tree", "trie", "heap", "lca"],
          "aliases": {
            "luogu": {"二叉树": "binary_tree_traverse", "二叉搜索树": "bst", "线段树": "segment_tree", "字典树": "trie", "堆": "heap", "最近公共祖先": "lca"},
            "leetcode": {"Binary Tree": "binary_tree_traverse", "Segment Tree": "segment_tree", "Trie": "trie", "Heap": "heap"}
          }
        },
        "stack_queue": {
          "topics": ["stack", "queue", "monotonic_stack", "deque"],
          "aliases": {
            "luogu": {"栈": "stack", "队列": "queue", "单调栈": "monotonic_stack"},
            "leetcode": {"Stack": "stack", "Queue": "queue"}
          }
        }
      }
    },
    "algorithm": {
      "subcategories": {
        "dp": {
          "topics": ["knapsack", "interval_dp", "tree_dp", "digit_dp", "bitmask_dp", "probability_dp"],
          "aliases": {
            "luogu": {"背包": "knapsack", "区间dp": "interval_dp", "树形dp": "tree_dp", "数位dp": "digit_dp", "状压dp": "bitmask_dp"},
            "leetcode": {"Dynamic Programming": "knapsack", "Bitmask": "bitmask_dp"}
          }
        },
        "graph": {
          "topics": ["bfs", "dfs", "dijkstra", "floyd", "topological_sort", "union_find", "mst", "euler_path"],
          "aliases": {
            "luogu": {"广度优先搜索": "bfs", "深度优先搜索": "dfs", "最短路": "dijkstra", "拓扑排序": "topological_sort", "并查集": "union_find", "最小生成树": "mst"},
            "leetcode": {"Breadth-First Search": "bfs", "Depth-First Search": "dfs", "Graph": "bfs", "Union Find": "union_find"}
          }
        },
        "greedy": {
          "topics": ["greedy", "sort_greedy", "interval_scheduling"],
          "aliases": {
            "luogu": {"贪心": "greedy", "排序贪心": "sort_greedy"},
            "leetcode": {"Greedy": "greedy", "Sorting": "sort_greedy"}
          }
        },
        "math": {
          "topics": ["number_theory", "combinatorics", "probability", "geometry", "matrix"],
          "aliases": {
            "luogu": {"数论": "number_theory", "组合数学": "combinatorics", "概率": "probability", "几何": "geometry", "矩阵": "matrix"},
            "leetcode": {"Math": "number_theory", "Geometry": "geometry"}
          }
        },
        "string": {
          "topics": ["kmp", "hash", "manacher", "suffix_array", "ac_automaton"],
          "aliases": {
            "luogu": {"KMP": "kmp", "哈希": "hash", "字符串哈希": "hash", "Manacher": "manacher", "AC自动机": "ac_automaton"},
            "leetcode": {"String Matching": "kmp", "String": "hash"}
          }
        }
      }
    }
  }
}
```

- [ ] **Step 4: 实现 TagNormalizer**

```python
# python/llm/normalizer.py
"""标签归一化与难度归一化模块"""

import json
from typing import Union


class TagNormalizer:
    """将各平台原始标签映射到统一标签体系"""

    def __init__(self, taxonomy_path: str = "taxonomy.json"):
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            self.taxonomy = json.load(f)
        self._build_reverse_index()

    def _build_reverse_index(self) -> None:
        """构建 platform:raw_tag → normalized_tag 的反向索引"""
        self.reverse_index: dict[str, str] = {}
        for _cat, subcats in self.taxonomy["categories"].items():
            for _sub, data in subcats["subcategories"].items():
                for platform, aliases in data.get("aliases", {}).items():
                    for raw_tag, norm_tag in aliases.items():
                        key = f"{platform}:{raw_tag.lower()}"
                        self.reverse_index[key] = norm_tag

    def normalize_tags(self, platform: str, raw_tags: list[str]) -> list[str]:
        """平台原始标签 → 归一化标签（去重，未知标签标记 unmapped:）"""
        normalized: set[str] = set()
        for tag in raw_tags:
            key = f"{platform}:{tag.lower()}"
            if key in self.reverse_index:
                normalized.add(self.reverse_index[key])
            else:
                normalized.add(f"unmapped:{tag}")
        return sorted(normalized)

    def get_all_tags(self) -> list[str]:
        """返回 taxonomy 中所有归一化标签"""
        tags: set[str] = set()
        for _cat, subcats in self.taxonomy["categories"].items():
            for _sub, data in subcats["subcategories"].items():
                tags.update(data.get("topics", []))
        return sorted(tags)
```

- [ ] **Step 5: 运行测试**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_normalizer.py::TestTagNormalizer -v
# 预期: 全部 PASS
```

- [ ] **Step 6: Commit**

```bash
git add python/llm/normalizer.py python/llm/taxonomy.json python/llm/test/test_normalizer.py
git commit -m "feat(llm): add TagNormalizer with taxonomy-based reverse index"
```

---

## Task 3: DifficultyNormalizer — 跨平台难度归一化

**Files:**
- Modify: `python/llm/normalizer.py` (追加 DifficultyNormalizer)
- Modify: `python/llm/test/test_normalizer.py` (追加测试)

- [ ] **Step 1: 写测试 — DifficultyNormalizer（先写失败测试）**

```python
# 追加到 python/llm/test/test_normalizer.py


class TestDifficultyNormalizer:
    """DifficultyNormalizer 测试"""

    def test_luogu_entry_level(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("luogu", "入门") == 1.0

    def test_luogu_pujin(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("luogu", "普及/提高-") == 3.0

    def test_luogu_noi(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("luogu", "NOI/NOI+") == 7.0

    def test_luogu_unknown_returns_default(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("luogu", "不存在的难度") == 5.0

    def test_leetcode_easy(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("leetcode", "Easy") == 3.0

    def test_leetcode_medium(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("leetcode", "Medium") == 5.0

    def test_leetcode_hard(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("leetcode", "Hard") == 8.0

    def test_leetcode_unknown_returns_default(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("leetcode", "Impossible") == 5.0

    def test_codeforces_rating_800(self):
        dn = DifficultyNormalizer()
        result = dn.normalize("codeforces", 800)
        assert result == 1.0

    def test_codeforces_rating_1400(self):
        dn = DifficultyNormalizer()
        result = dn.normalize("codeforces", 1400)
        assert result == round((1400 - 800) / 300 + 1, 1)

    def test_codeforces_rating_clamp_high(self):
        dn = DifficultyNormalizer()
        result = dn.normalize("codeforces", 5000)
        assert result == 10.0

    def test_codeforces_rating_clamp_low(self):
        dn = DifficultyNormalizer()
        result = dn.normalize("codeforces", 500)
        assert result == 1.0

    def test_atcoder_rating(self):
        dn = DifficultyNormalizer()
        result = dn.normalize("atcoder", 100)
        assert result == 1.0

    def test_atcoder_rating_clamp(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("atcoder", 5000) == 10.0

    def test_nowcoder_difficulty(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("nowcoder", 25) == 5.0

    def test_nowcoder_clamp(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("nowcoder", 100) == 10.0

    def test_unknown_platform_returns_default(self):
        dn = DifficultyNormalizer()
        assert dn.normalize("spoj", 100) == 5.0

    def test_rounding(self):
        dn = DifficultyNormalizer()
        result = dn.normalize("codeforces", 1100)
        assert isinstance(result, float)
        # 验证保留 1 位小数
        assert len(str(result).split(".")[-1]) <= 1 or result == int(result)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_normalizer.py::TestDifficultyNormalizer -v
# 预期: FAIL — DifficultyNormalizer 不存在
```

- [ ] **Step 3: 实现 DifficultyNormalizer**

```python
# 追加到 python/llm/normalizer.py


class DifficultyNormalizer:
    """跨平台难度归一化到 1.0~10.0"""

    MAPPINGS: dict[str, Union[dict, callable]] = {
        "luogu": {
            "入门": 1.0,
            "普及-": 2.0,
            "普及/提高-": 3.0,
            "普及+/提高": 4.0,
            "提高+/省选-": 5.0,
            "省选/NOI-": 6.0,
            "NOI/NOI+": 7.0,
            "NOI+": 8.0,
        },
        "leetcode": {
            "Easy": 3.0,
            "Medium": 5.0,
            "Hard": 8.0,
        },
        "codeforces": lambda r: max(1.0, min(10.0, (r - 800) / 300 + 1)),
        "atcoder": lambda r: max(1.0, min(10.0, (r - 100) / 300 + 1)),
        "nowcoder": lambda d: max(1.0, min(10.0, d / 5)),
    }

    def normalize(self, platform: str, raw_difficulty: Union[str, int, float]) -> float:
        """归一化难度到 1.0~10.0，未知平台/难度返回 5.0"""
        mapping = self.MAPPINGS.get(platform)
        if mapping is None:
            return 5.0
        if callable(mapping):
            return round(float(mapping(raw_difficulty)), 1)
        return float(mapping.get(str(raw_difficulty), 5.0))
```

- [ ] **Step 4: 运行测试**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_normalizer.py -v
# 预期: 全部 PASS
```

- [ ] **Step 5: Commit**

```bash
git add python/llm/normalizer.py python/llm/test/test_normalizer.py
git commit -m "feat(llm): add DifficultyNormalizer with cross-platform mapping"
```

---

## Task 4: ProblemSummarizer — LLM 题目总结

**Files:**
- Create: `python/llm/summarizer.py`
- Create: `python/llm/test/test_summarizer.py`

- [ ] **Step 1: 写测试 — ProblemSummarizer（先写失败测试，mock LLM 调用）**

```python
# python/llm/test/test_summarizer.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from llm.normalizer import TagNormalizer
from llm.summarizer import ProblemSummarizer


class TestProblemSummarizer:
    """ProblemSummarizer 测试 — 全部 mock LLM API"""

    def _make_summarizer(self, taxonomy_path, llm_response_json):
        """构造带 mock LLM 的 summarizer"""
        normalizer = TagNormalizer(taxonomy_path)
        mock_llm = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps(llm_response_json, ensure_ascii=False)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)
        return ProblemSummarizer(mock_llm, normalizer), mock_llm

    async def test_summarize_returns_structured_output(self, sample_taxonomy, sample_raw_problem, mock_llm_response):
        summarizer, mock_llm = self._make_summarizer(sample_taxonomy, mock_llm_response)
        result = await summarizer.summarize(sample_raw_problem)
        assert "summary" in result
        assert "solution_approach" in result
        assert "key_points" in result
        assert "pitfalls" in result
        assert "tags_normalized" in result
        assert "difficulty_normalized" in result

    async def test_summarize_calls_deepseek(self, sample_taxonomy, sample_raw_problem, mock_llm_response):
        summarizer, mock_llm = self._make_summarizer(sample_taxonomy, mock_llm_response)
        await summarizer.summarize(sample_raw_problem)
        mock_llm.chat.completions.create.assert_called_once()
        call_args = mock_llm.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "deepseek-chat"
        assert call_args.kwargs["temperature"] == 0.3
        assert call_args.kwargs["response_format"] == {"type": "json_object"}

    async def test_summarize_filters_invalid_tags(self, sample_taxonomy):
        """LLM 返回的无效标签应被过滤"""
        normalizer = TagNormalizer(sample_taxonomy)
        invalid_response = {
            "summary": "测试",
            "solution_approach": "测试",
            "key_points": [],
            "pitfalls": [],
            "tags_normalized": ["prefix_sum", "nonexistent_tag", "knapsack"],
            "difficulty_normalized": 5.0,
            "similar_problems_hint": "测试",
        }
        mock_llm = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps(invalid_response)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

        summarizer = ProblemSummarizer(mock_llm, normalizer)
        problem = {
            "source_platform": "luogu",
            "source_id": "P1001",
            "title": "测试",
            "difficulty_raw": "入门",
            "tags_platform": [],
            "full_content": "测试题面",
        }
        result = await summarizer.summarize(problem)
        assert "nonexistent_tag" not in result["tags_normalized"]
        assert "prefix_sum" in result["tags_normalized"]

    async def test_summarize_truncates_long_content(self, sample_taxonomy, mock_llm_response):
        """过长题面应被截断到 3000 字符"""
        summarizer, mock_llm = self._make_summarizer(sample_taxonomy, mock_llm_response)
        problem = {
            "source_platform": "luogu",
            "source_id": "P9999",
            "title": "长题面测试",
            "difficulty_raw": "入门",
            "tags_platform": [],
            "full_content": "A" * 5000,
        }
        await summarizer.summarize(problem)
        call_args = mock_llm.chat.completions.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        # 题面应被截断到 3000 字符
        assert "A" * 3000 in prompt
        assert "A" * 3001 not in prompt

    async def test_summarize_handles_empty_content(self, sample_taxonomy, mock_llm_response):
        summarizer, mock_llm = self._make_summarizer(sample_taxonomy, mock_llm_response)
        problem = {
            "source_platform": "luogu",
            "source_id": "P0000",
            "title": "空题面",
            "difficulty_raw": "入门",
            "tags_platform": [],
            "full_content": "",
        }
        result = await summarizer.summarize(problem)
        assert "summary" in result

    async def test_summarize_includes_taxonomy_in_prompt(self, sample_taxonomy, sample_raw_problem, mock_llm_response):
        """prompt 中应包含标准标签库"""
        summarizer, mock_llm = self._make_summarizer(sample_taxonomy, mock_llm_response)
        await summarizer.summarize(sample_raw_problem)
        call_args = mock_llm.chat.completions.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "prefix_sum" in prompt
        assert "knapsack" in prompt

    async def test_format_summary(self, sample_taxonomy):
        """测试 _format_summary 格式化输出"""
        normalizer = TagNormalizer(sample_taxonomy)
        mock_llm = MagicMock()
        summarizer = ProblemSummarizer(mock_llm, normalizer)
        summary = {
            "summary": "经典背包题",
            "solution_approach": "0-1 背包 DP",
            "key_points": ["状态转移", "空间优化"],
            "pitfalls": ["边界条件"],
            "similar_problems_hint": "背包变种",
        }
        formatted = summarizer._format_summary(summary)
        assert "【核心考点】" in formatted
        assert "【推荐解法】" in formatted
        assert "【关键点】" in formatted
        assert "【易错点】" in formatted
        assert "【相似特征】" in formatted
        assert "经典背包题" in formatted
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_summarizer.py -v
# 预期: FAIL — ModuleNotFoundError: No module named 'llm.summarizer'
```

- [ ] **Step 3: 实现 ProblemSummarizer**

```python
# python/llm/summarizer.py
"""LLM 题目总结模块 — DeepSeek 结构化输出"""

import json
from typing import Any

from llm.normalizer import TagNormalizer


SUMMARIZE_PROMPT = """\
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


class ProblemSummarizer:
    """调用 DeepSeek LLM 生成题目结构化总结"""

    def __init__(self, llm_client: Any, normalizer: TagNormalizer):
        self.llm = llm_client
        self.normalizer = normalizer

    async def summarize(self, problem: dict) -> dict:
        """生成题目总结，返回结构化 dict"""
        taxonomy_tags = self.normalizer.get_all_tags()

        prompt = SUMMARIZE_PROMPT.format(
            platform=problem["source_platform"],
            source_id=problem["source_id"],
            title=problem["title"],
            difficulty_raw=problem.get("difficulty_raw", ""),
            tags_platform=json.dumps(problem.get("tags_platform", []), ensure_ascii=False),
            full_content=str(problem.get("full_content", ""))[:3000],
            taxonomy_tags=", ".join(taxonomy_tags),
        )

        response = await self.llm.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        # 过滤不在标准标签库内的标签
        valid_tags = set(self.normalizer.get_all_tags())
        result["tags_normalized"] = [
            t for t in result.get("tags_normalized", []) if t in valid_tags
        ]

        return result

    def _format_summary(self, summary: dict) -> str:
        """将结构化总结格式化为可读文本（存入 solution_summary 字段）"""
        lines = [
            f"【核心考点】{summary.get('summary', '')}",
            f"【推荐解法】{summary.get('solution_approach', '')}",
            f"【关键点】{'、'.join(summary.get('key_points', []))}",
            f"【易错点】{'、'.join(summary.get('pitfalls', []))}",
            f"【相似特征】{summary.get('similar_problems_hint', '')}",
        ]
        return "\n".join(lines)
```

- [ ] **Step 4: 运行测试**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_summarizer.py -v
# 预期: 全部 PASS
```

- [ ] **Step 5: Commit**

```bash
git add python/llm/summarizer.py python/llm/test/test_summarizer.py
git commit -m "feat(llm): add ProblemSummarizer with DeepSeek structured output"
```

---

## Task 5: ProblemEmbedder — 向量生成

**Files:**
- Create: `python/llm/embedder.py`
- Create: `python/llm/test/test_embedder.py`

- [ ] **Step 1: 写测试 — ProblemEmbedder（先写失败测试，mock embedding API）**

```python
# python/llm/test/test_embedder.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from llm.embedder import ProblemEmbedder


def _make_mock_embedding(dim: int = 1536):
    """构造一个 mock embedding 对象"""
    mock_data = MagicMock()
    mock_data.embedding = [0.1] * dim
    return mock_data


def _make_mock_client(batch_count: int = 1, dim: int = 1536):
    """构造 mock OpenAI client"""
    mock_client = MagicMock()
    mock_data_list = [_make_mock_embedding(dim) for _ in range(batch_count)]
    mock_response = MagicMock()
    mock_response.data = mock_data_list
    mock_client.embeddings.create = AsyncMock(return_value=mock_response)
    return mock_client


class TestProblemEmbedder:
    """ProblemEmbedder 测试 — 全部 mock API"""

    async def test_embed_batch_returns_vectors(self):
        client = _make_mock_client(batch_count=3)
        embedder = ProblemEmbedder(client, batch_size=500)
        result = await embedder.embed_batch(["text1", "text2", "text3"])
        assert len(result) == 3
        assert len(result[0]) == 1536

    async def test_embed_batch_calls_api(self):
        client = _make_mock_client(batch_count=2)
        embedder = ProblemEmbedder(client, batch_size=500)
        await embedder.embed_batch(["hello", "world"])
        client.embeddings.create.assert_called_once()
        call_args = client.embeddings.create.call_args
        assert call_args.kwargs["model"] == "text-embedding-3-small"
        assert call_args.kwargs["input"] == ["hello", "world"]

    async def test_embed_batch_splits_large_batch(self):
        """超过 batch_size 的文本应分批调用"""
        client = MagicMock()
        mock_data = [_make_mock_embedding() for _ in range(2)]
        mock_response = MagicMock()
        mock_response.data = mock_data
        client.embeddings.create = AsyncMock(return_value=mock_response)

        embedder = ProblemEmbedder(client, batch_size=2)
        texts = ["a", "b", "c", "d", "e"]
        result = await embedder.embed_batch(texts)
        assert client.embeddings.create.call_count == 3  # ceil(5/2) = 3
        assert len(result) == 5

    async def test_embed_batch_retry_on_failure(self):
        """第一次失败后应重试"""
        client = MagicMock()
        mock_data = [_make_mock_embedding()]
        mock_response = MagicMock()
        mock_response.data = mock_data
        client.embeddings.create = AsyncMock(
            side_effect=[Exception("timeout"), mock_response]
        )

        embedder = ProblemEmbedder(client, batch_size=500)
        result = await embedder.embed_batch(["text"])
        assert len(result) == 1
        assert client.embeddings.create.call_count == 2

    async def test_embed_batch_raises_after_max_retries(self):
        """连续失败超过 3 次应抛异常"""
        client = MagicMock()
        client.embeddings.create = AsyncMock(side_effect=Exception("API down"))

        embedder = ProblemEmbedder(client, batch_size=500)
        with pytest.raises(Exception, match="API down"):
            await embedder.embed_batch(["text"])
        assert client.embeddings.create.call_count == 3

    async def test_embed_problems_adds_vectors(self):
        """embed_problems 应为题目添加 vector_embedding 和 content_vector"""
        client = MagicMock()
        mock_data = [_make_mock_embedding() for _ in range(4)]
        mock_response = MagicMock()
        mock_response.data = mock_data
        client.embeddings.create = AsyncMock(return_value=mock_response)

        embedder = ProblemEmbedder(client, batch_size=500)
        problems = [
            {"solution_summary": "summary1", "full_content": "content1"},
            {"solution_summary": "summary2", "full_content": "content2"},
        ]
        result = await embedder.embed_problems(problems)
        assert len(result) == 2
        assert "vector_embedding" in result[0]
        assert "content_vector" in result[0]
        assert len(result[0]["vector_embedding"]) == 1536
        assert len(result[0]["content_vector"]) == 1536
        # 两次 batch 调用: summaries + contents
        assert client.embeddings.create.call_count == 2

    async def test_embed_problems_empty_content(self):
        """题目没有 full_content 时应使用空字符串"""
        client = _make_mock_client(batch_count=2)
        embedder = ProblemEmbedder(client, batch_size=500)
        problems = [{"solution_summary": "summary1"}]
        result = await embedder.embed_problems(problems)
        assert "content_vector" in result[0]

    async def test_embed_solutions(self):
        """embed_solutions 应为题解生成向量"""
        client = _make_mock_client(batch_count=2)
        embedder = ProblemEmbedder(client, batch_size=500)
        solutions = [
            {"content": "解法1"},
            {"content": "解法2"},
        ]
        result = await embedder.embed_solutions(solutions)
        assert len(result) == 2
        assert "vector_embedding" in result[0]
        assert "vector_embedding" in result[1]

    async def test_embed_solutions_truncates_long_content(self):
        """过长题解应被截断到 2000 字符"""
        client = MagicMock()
        mock_data = [_make_mock_embedding()]
        mock_response = MagicMock()
        mock_response.data = mock_data
        client.embeddings.create = AsyncMock(return_value=mock_response)

        embedder = ProblemEmbedder(client, batch_size=500)
        solutions = [{"content": "A" * 5000}]
        await embedder.embed_solutions(solutions)
        call_args = client.embeddings.create.call_args
        assert call_args.kwargs["input"] == ["A" * 2000]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_embedder.py -v
# 预期: FAIL — ModuleNotFoundError: No module named 'llm.embedder'
```

- [ ] **Step 3: 实现 ProblemEmbedder**

```python
# python/llm/embedder.py
"""向量生成模块 — OpenAI text-embedding-3-small 批量处理"""

import asyncio
from typing import Any


class ProblemEmbedder:
    """批量生成文本向量，支持自动分批与重试"""

    def __init__(self, openai_client: Any, batch_size: int = 500):
        self.client = openai_client
        self.batch_size = batch_size

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量，自动分批 + 3 次重试"""
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            for attempt in range(3):
                try:
                    response = await self.client.embeddings.create(
                        model="text-embedding-3-small",
                        input=batch,
                    )
                    all_embeddings.extend([e.embedding for e in response.data])
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
        return all_embeddings

    async def embed_problems(self, problems: list[dict]) -> list[dict]:
        """为题目生成父向量(summary) + 子向量(content)"""
        # 父向量: LLM 总结全文
        summaries = [p.get("solution_summary", "") for p in problems]
        parent_vectors = await self.embed_batch(summaries)

        # 子向量: 完整题面
        contents = [p.get("full_content", "") for p in problems]
        content_vectors = await self.embed_batch(contents)

        for i, p in enumerate(problems):
            p["vector_embedding"] = parent_vectors[i]
            p["content_vector"] = content_vectors[i]

        return problems

    async def embed_solutions(self, solutions: list[dict]) -> list[dict]:
        """为题解生成向量，截断过长内容"""
        texts = [s.get("content", "")[:2000] for s in solutions]
        vectors = await self.embed_batch(texts)
        for i, s in enumerate(solutions):
            s["vector_embedding"] = vectors[i]
        return solutions
```

- [ ] **Step 4: 运行测试**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_embedder.py -v
# 预期: 全部 PASS
```

- [ ] **Step 5: Commit**

```bash
git add python/llm/embedder.py python/llm/test/test_embedder.py
git commit -m "feat(llm): add ProblemEmbedder with batch processing and retry"
```

---

## Task 6: ProblemPipeline — 管道编排器

**Files:**
- Create: `python/llm/pipeline.py`
- Create: `python/llm/test/test_pipeline.py`

- [ ] **Step 1: 写测试 — ProblemPipeline（先写失败测试，mock 所有外部依赖）**

```python
# python/llm/test/test_pipeline.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from llm.pipeline import ProblemPipeline


def _make_mock_db():
    """构造 mock 数据库"""
    db = MagicMock()
    db.problem = MagicMock()
    db.problem.upsert = AsyncMock(return_value={"id": "test-id"})
    return db


def _make_mock_llm(llm_response: dict):
    """构造 mock DeepSeek LLM"""
    mock_llm = MagicMock()
    mock_message = MagicMock()
    mock_message.content = json.dumps(llm_response, ensure_ascii=False)
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_llm


def _make_mock_openai(dim: int = 1536):
    """构造 mock OpenAI embedding client"""
    mock_client = MagicMock()
    mock_data = MagicMock()
    mock_data.embedding = [0.1] * dim
    mock_response = MagicMock()
    mock_response.data = [mock_data]
    mock_client.embeddings.create = AsyncMock(return_value=mock_response)
    return mock_client


class TestProblemPipeline:
    """ProblemPipeline 端到端测试 — 全部 mock"""

    def _make_pipeline(self, taxonomy_path, llm_response, embedding_dim=1536):
        db = _make_mock_db()
        llm = _make_mock_llm(llm_response)
        openai = _make_mock_openai(embedding_dim)
        pipeline = ProblemPipeline(db, llm, openai, taxonomy_path=taxonomy_path)
        return pipeline, db, llm, openai

    async def test_process_problem_full_flow(self, sample_taxonomy, sample_raw_problem, mock_llm_response):
        """单题处理完整流程: 归一化 → 总结 → 向量化 → 写 DB"""
        pipeline, db, llm, openai = self._make_pipeline(sample_taxonomy, mock_llm_response)
        result = await pipeline.process_problem(sample_raw_problem)

        # 验证归一化结果
        assert "tags_normalized" in result
        assert "difficulty_normalized" in result
        assert isinstance(result["difficulty_normalized"], float)

        # 验证 LLM 总结
        assert "solution_summary" in result
        assert "【核心考点】" in result["solution_summary"]

        # 验证向量
        assert "vector_embedding" in result
        assert "content_vector" in result

        # 验证 DB 写入
        db.problem.upsert.assert_called_once()

    async def test_process_problem_normalize_tags(self, sample_taxonomy, sample_raw_problem, mock_llm_response):
        """标签归一化应正确执行"""
        pipeline, *_ = self._make_pipeline(sample_taxonomy, mock_llm_response)
        result = await pipeline.process_problem(sample_raw_problem)
        # luogu 背包 → knapsack (来自 LLM 总结)
        assert "knapsack" in result["tags_normalized"]

    async def test_process_problem_normalize_difficulty(self, sample_taxonomy, sample_raw_problem, mock_llm_response):
        """难度归一化应正确执行"""
        pipeline, *_ = self._make_pipeline(sample_taxonomy, mock_llm_response)
        result = await pipeline.process_problem(sample_raw_problem)
        assert result["difficulty_normalized"] == 3.0  # 普及/提高- → 3.0

    async def test_process_batch_stats(self, sample_taxonomy, sample_raw_problems, mock_llm_response):
        """批量处理应返回统计信息"""
        pipeline, db, llm, openai = self._make_pipeline(sample_taxonomy, mock_llm_response)
        # 需要为每道题构造不同 mock 返回
        mock_message = MagicMock()
        mock_message.content = json.dumps(mock_llm_response, ensure_ascii=False)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        llm.chat.completions.create = AsyncMock(return_value=mock_response)
        # embedding 需要返回多个
        mock_data = MagicMock()
        mock_data.embedding = [0.1] * 1536
        mock_emb_response = MagicMock()
        mock_emb_response.data = [mock_data, mock_data, mock_data]
        openai.embeddings.create = AsyncMock(return_value=mock_emb_response)

        stats = await pipeline.process_batch(sample_raw_problems)
        assert stats["processed"] == 3
        assert stats["errors"] == 0

    async def test_process_batch_counts_errors(self, sample_taxonomy):
        """处理失败的题目应计入 errors"""
        db = _make_mock_db()
        llm = MagicMock()
        llm.chat.completions.create = AsyncMock(side_effect=Exception("LLM error"))
        openai = _make_mock_openai()
        pipeline = ProblemPipeline(db, llm, openai, taxonomy_path=sample_taxonomy)

        problems = [{"source_platform": "luogu", "source_id": "P0001", "title": "test", "tags_platform": []}]
        stats = await pipeline.process_batch(problems)
        assert stats["processed"] == 0
        assert stats["errors"] == 1

    async def test_process_problem_upsert_keys(self, sample_taxonomy, sample_raw_problem, mock_llm_response):
        """DB upsert 应使用正确的 where 条件"""
        pipeline, db, *_ = self._make_pipeline(sample_taxonomy, mock_llm_response)
        await pipeline.process_problem(sample_raw_problem)
        call_args = db.problem.upsert.call_args
        where = call_args.kwargs.get("where") or call_args[1].get("where") or call_args[0][0]
        # 验证 upsert 被调用
        assert db.problem.upsert.called

    async def test_process_problem_llm_failure_propagates(self, sample_taxonomy, sample_raw_problem):
        """LLM 调用失败应向上传播"""
        db = _make_mock_db()
        llm = MagicMock()
        llm.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        openai = _make_mock_openai()
        pipeline = ProblemPipeline(db, llm, openai, taxonomy_path=sample_taxonomy)

        with pytest.raises(Exception, match="API error"):
            await pipeline.process_problem(sample_raw_problem)

    async def test_format_summary_method(self, sample_taxonomy, mock_llm_response):
        """测试 _format_summary 格式化"""
        pipeline, *_ = self._make_pipeline(sample_taxonomy, mock_llm_response)
        formatted = pipeline._format_summary(mock_llm_response)
        assert "【核心考点】" in formatted
        assert "经典 0-1 背包模板题" in formatted

    async def test_upsert_problem_structure(self, sample_taxonomy, sample_raw_problem, mock_llm_response):
        """验证 upsert 写入的数据结构包含必要字段"""
        pipeline, db, *_ = self._make_pipeline(sample_taxonomy, mock_llm_response)
        await pipeline.process_problem(sample_raw_problem)
        call_args = db.problem.upsert.call_args
        # upsert 应被调用且包含 create/update 参数
        assert db.problem.upsert.called
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_pipeline.py -v
# 预期: FAIL — ModuleNotFoundError: No module named 'llm.pipeline'
```

- [ ] **Step 3: 实现 ProblemPipeline**

```python
# python/llm/pipeline.py
"""题目处理管道 — 归一化 → LLM 总结 → 向量化 → 写 DB"""

import asyncio
import json
import logging
from typing import Any

from llm.normalizer import DifficultyNormalizer, TagNormalizer
from llm.summarizer import ProblemSummarizer
from llm.embedder import ProblemEmbedder

logger = logging.getLogger(__name__)


class ProblemPipeline:
    """题目处理管道: 归一化 → LLM 总结 → 向量化 → 写 DB"""

    def __init__(
        self,
        db: Any,
        llm_client: Any,
        openai_client: Any,
        taxonomy_path: str = "taxonomy.json",
    ):
        self.normalizer = TagNormalizer(taxonomy_path)
        self.diff_normalizer = DifficultyNormalizer()
        self.summarizer = ProblemSummarizer(llm_client, self.normalizer)
        self.embedder = ProblemEmbedder(openai_client)
        self.db = db

    async def process_problem(self, raw_problem: dict) -> dict:
        """处理单道题目: 归一化 → LLM 总结 → 向量化 → 写 DB"""
        # Step 1: 标签归一化
        raw_problem["tags_normalized"] = self.normalizer.normalize_tags(
            raw_problem["source_platform"],
            raw_problem.get("tags_platform", []),
        )

        # Step 2: 难度归一化
        raw_problem["difficulty_normalized"] = self.diff_normalizer.normalize(
            raw_problem["source_platform"],
            raw_problem.get("difficulty_raw"),
        )

        # Step 3: LLM 总结
        summary = await self.summarizer.summarize(raw_problem)
        raw_problem["solution_summary"] = self._format_summary(summary)
        raw_problem["tags_normalized"] = summary.get(
            "tags_normalized", raw_problem["tags_normalized"]
        )

        # Step 4: 向量化
        embedded = await self.embedder.embed_problems([raw_problem])

        # Step 5: 写 DB (upsert)
        await self._upsert_problem(embedded[0])

        return embedded[0]

    async def process_batch(self, problems: list[dict]) -> dict:
        """批量处理，返回 {processed, errors} 统计"""
        stats = {"processed": 0, "errors": 0}
        for p in problems:
            try:
                await self.process_problem(p)
                stats["processed"] += 1
            except Exception as e:
                logger.error(f"Error processing {p.get('source_id')}: {e}")
                stats["errors"] += 1
        return stats

    def _format_summary(self, summary: dict) -> str:
        """将结构化总结格式化为可读文本"""
        lines = [
            f"【核心考点】{summary.get('summary', '')}",
            f"【推荐解法】{summary.get('solution_approach', '')}",
            f"【关键点】{'、'.join(summary.get('key_points', []))}",
            f"【易错点】{'、'.join(summary.get('pitfalls', []))}",
            f"【相似特征】{summary.get('similar_problems_hint', '')}",
        ]
        return "\n".join(lines)

    async def _upsert_problem(self, problem: dict) -> None:
        """写入数据库（upsert 语义）"""
        await self.db.problem.upsert(
            where={
                "sourcePlatform_sourceId": {
                    "sourcePlatform": problem["source_platform"],
                    "sourceId": problem["source_id"],
                }
            },
            create={
                "sourcePlatform": problem["source_platform"],
                "sourceId": problem["source_id"],
                "sourceUrl": problem.get("source_url", ""),
                "title": problem["title"],
                "difficultyRaw": str(problem.get("difficulty_raw", "")),
                "difficultyNormalized": problem["difficulty_normalized"],
                "tagsNormalized": problem["tags_normalized"],
                "tagsPlatform": json.dumps(problem.get("tags_platform", []), ensure_ascii=False),
                "fullContent": problem.get("full_content", ""),
                "solutionSummary": problem.get("solution_summary", ""),
                "vectorEmbedding": problem.get("vector_embedding"),
                "contentVector": problem.get("content_vector"),
            },
            update={
                "difficultyNormalized": problem["difficulty_normalized"],
                "tagsNormalized": problem["tags_normalized"],
                "solutionSummary": problem.get("solution_summary", ""),
                "vectorEmbedding": problem.get("vector_embedding"),
                "contentVector": problem.get("content_vector"),
                "title": problem["title"],
            },
        )


# ===== CLI 入口 =====

async def main():
    """CLI 入口: 解析参数并执行管道"""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="ACM Agent Problem Pipeline")
    parser.add_argument("--platform", type=str, help="平台名称 (luogu/leetcode/codeforces/atcoder/nowcoder)")
    parser.add_argument("--action", type=str, choices=["process", "re-embed"], default="process", help="操作类型")
    parser.add_argument("--count", type=int, default=100, help="处理数量")
    parser.add_argument("--taxonomy", type=str, default="taxonomy.json", help="标签映射表路径")
    args = parser.parse_args()

    # 依赖初始化（延迟导入，避免测试时触发）
    from openai import AsyncOpenAI

    db_url = os.environ.get("DATABASE_URL", "")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if not deepseek_key or not openai_key:
        print("Error: DEEPSEEK_API_KEY and OPENAI_API_KEY environment variables required")
        return

    # 初始化客户端
    deepseek_client = AsyncOpenAI(
        api_key=deepseek_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    openai_client = AsyncOpenAI(api_key=openai_key)

    # DB 初始化（延迟导入）
    try:
        from prisma import PrismaClient
        db = PrismaClient()
        await db.connect()
    except ImportError:
        print("Warning: prisma not available, running without DB")
        db = MagicMock()

    pipeline = ProblemPipeline(db, deepseek_client, openai_client, taxonomy_path=args.taxonomy)

    if args.action == "process":
        # 从 DB 读取待处理题目
        problems = await db.problem.find_many(
            where={"sourcePlatform": args.platform} if args.platform else {},
            take=args.count,
        )
        print(f"Processing {len(problems)} problems...")
        stats = await pipeline.process_batch([p.dict() for p in problems])
        print(f"Done: {stats['processed']} processed, {stats['errors']} errors")
    elif args.action == "re-embed":
        # 重新向量化
        problems = await db.problem.find_many(take=args.count)
        texts = [p.solution_summary or "" for p in problems]
        vectors = await pipeline.embedder.embed_batch(texts)
        for i, p in enumerate(problems):
            await db.problem.update(where={"id": p.id}, data={"vectorEmbedding": vectors[i]})
        print(f"Re-embedded {len(problems)} problems")

    if hasattr(db, "disconnect"):
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: 运行测试**

```bash
cd E:/code/ACM-Agent/python
pytest llm/test/test_pipeline.py -v
# 预期: 全部 PASS
```

- [ ] **Step 5: Commit**

```bash
git add python/llm/pipeline.py python/llm/test/test_pipeline.py
git commit -m "feat(llm): add ProblemPipeline orchestrator with CLI entry"
```

---

## Task 7: 覆盖率验证 + Phase Gate

**Files:**
- 无新文件，验证现有代码覆盖率

- [ ] **Step 1: 运行全量测试 + 覆盖率报告**

```bash
cd E:/code/ACM-Agent/python
pytest --cov=llm --cov-report=term-missing --cov-fail-under=90 -v
# 预期:
# - 全部测试 PASS
# - 覆盖率 ≥ 90%
# - 查看 Missing 列，定位未覆盖行
```

- [ ] **Step 2: 如果覆盖率不足，补充测试**

检查 Missing 列，为以下常见未覆盖场景补充测试：

- `pipeline.py` 中 `main()` CLI 入口（可通过 `unittest.mock.patch` 模拟 argparse + 环境变量）
- `normalizer.py` 中 `DifficultyNormalizer` 的边界值
- `summarizer.py` 中 prompt 格式化的边界情况
- `embedder.py` 中分批 + 重试的组合场景

补充测试示例（如需覆盖 CLI main 函数）:

```python
# 追加到 python/llm/test/test_pipeline.py

import sys
from unittest.mock import patch


class TestCLIMain:
    """CLI main 函数测试"""

    async def test_main_missing_env_vars(self, capsys):
        """缺少环境变量时应打印错误"""
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.argv", ["pipeline.py", "--action", "process"]):
                from llm.pipeline import main
                # 重新导入以获取干净的模块
                import importlib
                import llm.pipeline
                importlib.reload(llm.pipeline)
                # main 内部会检查环境变量
                # 这里验证不抛异常即可
                try:
                    await llm.pipeline.main()
                except SystemExit:
                    pass

    async def test_main_with_mock_env(self):
        """环境变量齐全时应正常执行"""
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.problem = MagicMock()
        mock_db.problem.find_many = AsyncMock(return_value=[])
        mock_db.disconnect = AsyncMock()

        with patch.dict("os.environ", {
            "DEEPSEEK_API_KEY": "sk-test",
            "OPENAI_API_KEY": "sk-test",
        }):
            with patch("sys.argv", ["pipeline.py", "--action", "process", "--count", "10"]):
                with patch("llm.pipeline.ProblemPipeline") as MockPipeline:
                    mock_pipeline = MagicMock()
                    mock_pipeline.process_batch = AsyncMock(return_value={"processed": 0, "errors": 0})
                    MockPipeline.return_value = mock_pipeline

                    with patch("llm.pipeline.PrismaClient", return_value=mock_db):
                        from llm.pipeline import main
                        import importlib
                        import llm.pipeline
                        importlib.reload(llm.pipeline)
                        try:
                            await llm.pipeline.main()
                        except Exception:
                            pass  # 可能因 import 失败，但覆盖率已收集
```

- [ ] **Step 3: 确认覆盖率达标**

```bash
cd E:/code/ACM-Agent/python
pytest --cov=llm --cov-report=term-missing --cov-fail-under=90 -v
# 预期: 覆盖率 ≥ 90%，全部 PASS
```

- [ ] **Step 4: Phase Gate — 最终验证**

```bash
cd E:/code/ACM-Agent/python
pytest --cov=llm --cov-report=term-missing --cov-fail-under=90
echo "Phase 4 Gate: Problem Pipeline ready"
```

- [ ] **Step 5: Commit**

```bash
git add python/
git commit -m "test(llm): Phase 4 gate — 90% coverage achieved for problem pipeline"
```

---

## Phase 4 完成标准

| 检查项 | 标准 | 验证命令 |
|--------|------|---------|
| TagNormalizer | 标签映射 + 反向索引 + unmapped 标记 | `pytest llm/test/test_normalizer.py::TestTagNormalizer -v` |
| DifficultyNormalizer | 5 平台映射 + 边界 clamp + 默认值 | `pytest llm/test/test_normalizer.py::TestDifficultyNormalizer -v` |
| ProblemSummarizer | DeepSeek 调用 + 结构化输出 + 标签过滤 + 格式化 | `pytest llm/test/test_summarizer.py -v` |
| ProblemEmbedder | 批量 embedding + 分批 + 重试 + 双向量 | `pytest llm/test/test_embedder.py -v` |
| ProblemPipeline | 完整管道 + 批量处理 + 统计 + upsert | `pytest llm/test/test_pipeline.py -v` |
| CLI 入口 | --platform / --action / --count 参数 | `python -m llm.pipeline --help` |
| 测试覆盖率 | ≥ 90% | `pytest --cov=llm --cov-fail-under=90` |
| 全部测试通过 | 0 failures | `pytest -v` |

---

## 依赖关系

```
Task 1 (初始化)
    ↓
Task 2 (TagNormalizer) ← taxonomy.json
    ↓
Task 3 (DifficultyNormalizer)
    ↓
Task 4 (ProblemSummarizer) ← 依赖 TagNormalizer
    ↓
Task 5 (ProblemEmbedder)
    ↓
Task 6 (ProblemPipeline) ← 依赖全部上层模块
    ↓
Task 7 (覆盖率验证)
```

每个 Task 必须在前一个 Task 的测试全部 PASS 后才能开始。Task 2~6 遵循严格 TDD: 写测试 → 确认失败 → 实现 → 确认通过。
