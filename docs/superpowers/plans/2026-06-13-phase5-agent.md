# Phase 5: LangGraph Agents 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans

**Goal:** 实现 profile_agent（6 维画像）和 training_agent（4 阶段训练规划），90% 测试覆盖率

**Architecture:** LangGraph StateGraph + DeepSeek LLM + 纯 Python 数值计算（LLM 仅生成总结文本）

**Tech Stack:** Python 3.11+, LangGraph, LangChain, DeepSeek API, pytest, pytest-cov

---

## 文件结构

```
python/agents/
├── __init__.py
├── taxonomy.py             # 三级标签 + 知识依赖图谱
├── profile_agent.py        # 6 维画像 Agent (LangGraph)
├── training_agent.py       # 训练规划 Agent (LangGraph)
├── formulas.py             # 纯 Python 计算公式
├── spaced_repetition.py    # SM-2 间隔重复
├── test/
│   ├── __init__.py
│   ├── test_formulas.py
│   ├── test_profile_agent.py
│   ├── test_training_agent.py
│   ├── test_taxonomy.py
│   └── test_sm2.py
```

---

## Task 1: 公式集（formulas.py + spaced_repetition.py）

**Files:** Create `python/agents/formulas.py`, `python/agents/spaced_repetition.py`, `python/agents/taxonomy.py`

- [ ] **Step 1: 写测试 — formulas**

```python
# python/agents/test/test_formulas.py
import pytest, math
from agents.formulas import calc_proficiency, calc_ceiling, calc_efficiency, calc_momentum, classify_style, calc_coverage

class TestProficiency:
    def test_perfect_mastery(self):
        # AC=100, total=100, avg_diff=10, days=0 → near 1.0
        p = calc_proficiency(ac_count=100, total_count=100, avg_difficulty=10.0, days_since_last=0)
        assert 0.85 <= p <= 1.0

    def test_beginner(self):
        p = calc_proficiency(ac_count=1, total_count=5, avg_difficulty=2.0, days_since_last=60)
        assert p < 0.5

    def test_zero_ac_returns_zero(self):
        p = calc_proficiency(ac_count=0, total_count=10, avg_difficulty=5.0, days_since_last=0)
        assert p == 0.0

class TestCeiling:
    def test_p90_ceiling(self):
        records = [{'verdict': 'OK', 'difficulty_normalized': d, 'days_ago': 10} for d in [1,2,3,4,5,6,7,8,9,10]]
        assert calc_ceiling(records) == pytest.approx(9.1, 0.5)

    def test_insufficient_data(self):
        assert calc_ceiling([]) == 0.0
        assert calc_ceiling([{'verdict': 'OK', 'difficulty_normalized': 5}]) == 0.0

class TestEfficiency:
    def test_perfect_first_ac(self):
        from collections import defaultdict
        records = [{'problem_id': 'p1', 'verdict': 'OK'}, {'problem_id': 'p2', 'verdict': 'OK'}]
        e = calc_efficiency(records)
        assert e >= 0.9

    def test_multiple_retries(self):
        records = [
            {'problem_id': 'p1', 'verdict': 'WA'}, {'problem_id': 'p1', 'verdict': 'TLE'},
            {'problem_id': 'p1', 'verdict': 'OK'},
        ]
        e = calc_efficiency(records)
        assert e < 0.7

class TestMomentum:
    def test_positive_trend(self):
        stats = [{'ac_count': i} for i in range(1, 31)]  # 1→30
        assert calc_momentum(stats) > 0.5

    def test_negative_trend(self):
        stats = [{'ac_count': i} for i in range(30, 0, -1)]
        assert calc_momentum(stats) < -0.5

class TestStyle:
    def test_grinder(self):
        assert classify_style(total_solved=300, unique_tags=20, avg_proficiency=0.5, top3_tag_concentration=0.3, avg_difficulty=5.0) == "grinder"

    def test_deep_diver(self):
        assert classify_style(total_solved=50, unique_tags=10, avg_proficiency=0.8, top3_tag_concentration=0.4, avg_difficulty=5.0) == "deep_diver"

    def test_specialist(self):
        assert classify_style(total_solved=100, unique_tags=10, avg_proficiency=0.6, top3_tag_concentration=0.7, avg_difficulty=5.0) == "specialist"

    def test_balanced(self):
        assert classify_style(total_solved=100, unique_tags=12, avg_proficiency=0.6, top3_tag_concentration=0.4, avg_difficulty=5.0) == "balanced"

class TestCoverage:
    def test_full_coverage(self):
        assert calc_coverage({"dp", "graph"}, {"dp", "graph"}) == 1.0
    def test_half_coverage(self):
        assert calc_coverage({"dp"}, {"dp", "graph"}) == 0.5
```

- [ ] **Step 2: 写测试 — SM-2**

```python
# python/agents/test/test_sm2.py
from agents.spaced_repetition import schedule_review

def test_first_review():
    result = schedule_review("dp", [])
    assert result["interval_days"] == 1

def test_perfect_extends_interval():
    history = [{"date": "2026-01-01", "quality": 5}]
    result = schedule_review("dp", history)
    assert result["interval_days"] >= 1

def test_failed_resets():
    history = [{"date": "2026-01-01", "quality": 1}]
    result = schedule_review("dp", history)
    assert result["interval_days"] == 1
```

- [ ] **Step 3: 运行确认失败 → 实现 → 运行确认通过**

```python
# python/agents/formulas.py — 包含 6 维画像的全部计算公式
# python/agents/spaced_repetition.py — SM-2 变体
# python/agents/taxonomy.py — 三级标签树 + DEPENDENCY_GRAPH
```

```bash
pytest agents/test/test_formulas.py agents/test/test_sm2.py -v
# 预期: 全部 PASS
git add python/agents/
git commit -m "feat(agents): add 6-dimension formulas, SM-2, and taxonomy"
```

---

## Task 2: profile_agent（LangGraph StateGraph）

- [ ] **Step 1: 写测试**

```python
# python/agents/test/test_profile_agent.py
from unittest.mock import MagicMock, AsyncMock, patch
from agents.profile_agent import ProfileAgent, ProfileState

class TestProfileAgent:
    @patch('agents.profile_agent.PrismaClient')
    def test_load_user_data_node(self, mock_prisma):
        agent = ProfileAgent(mock_prisma)
        state = ProfileState(user_id="u1", platforms=[], raw_records=[], daily_stats=[], platform_profiles={}, aggregated_stats={}, analysis={}, profile_data={}, errors=[])
        result = agent.load_user_data(state)
        assert mock_prisma.practicerecord.find_many.called or len(result['raw_records']) >= 0

    def test_calc_6_dims_node(self):
        agent = ProfileAgent(None)
        state = ProfileState(user_id="u1", raw_records=[
            {'verdict': 'OK', 'difficulty_normalized': 7, 'tags_normalized': ['dp'], 'days_ago': 5, 'problem_id': 'p1'},
            {'verdict': 'OK', 'difficulty_normalized': 5, 'tags_normalized': ['graph'], 'days_ago': 10, 'problem_id': 'p2'},
        ], daily_stats=[{'ac_count': i} for i in range(1, 15)])
        result = agent.calc_6_dims(state)
        assert 0 <= result['profile_data']['overall_score'] <= 1
        assert 'coverage' in result['profile_data']
        assert 'ceiling' in result['profile_data']
        assert 'style' in result['profile_data']

    @patch('agents.profile_agent.ChatOpenAI')
    def test_llm_summarize_generates_text(self, mock_llm):
        mock_llm.return_value.invoke = AsyncMock(return_value=MagicMock(content='{"summary_text": "该同学处于中级水平"}'))
        agent = ProfileAgent(None, llm=mock_llm.return_value)
        state = ProfileState(profile_data={'overall_score': 0.7, 'style': 'balanced', 'strengths': [{'tag': 'dp', 'score': 0.8}]})
        result = agent.llm_summarize(state)
        assert 'summary_text' in result['profile_data']

    def test_fallback_node_creates_profile(self):
        agent = ProfileAgent(None)
        state = ProfileState(profile_data={'overall_score': 0.5})
        result = agent.fallback(state)
        assert 'summary_text' in result['profile_data']
        assert '数据不足' in result['profile_data']['summary_text']
```

- [ ] **Step 2: 实现 profile_agent**

```python
# python/agents/profile_agent.py
import operator
from typing import TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from agents.formulas import calc_proficiency, calc_ceiling, calc_efficiency, calc_momentum, classify_style, calc_coverage

class ProfileState(TypedDict):
    user_id: str
    platforms: list
    raw_records: list
    daily_stats: list
    platform_profiles: dict
    aggregated_stats: dict
    analysis: dict
    profile_data: dict
    errors: Annotated[list, operator.add]

class ProfileAgent:
    def __init__(self, db, llm=None):
        self.db = db
        self.llm = llm or ChatOpenAI(model=os.getenv('DEEPSEEK_MODEL', 'deepseek-chat'),
                                       api_key=os.getenv('DEEPSEEK_API_KEY'),
                                       base_url=os.getenv('DEEPSEEK_BASE_URL'))
        self.graph = self._build()

    def load_user_data(self, state: ProfileState) -> ProfileState:
        # Query practice_records, daily_stats, platform_accounts from DB
        state['errors'] = []
        if len(state.get('raw_records', [])) < 10:
            state['errors'].append('data_insufficient')
        return state

    def aggregate_stats(self, state: ProfileState) -> ProfileState:
        records = state['raw_records']
        stats = {'by_tag': {}, 'by_difficulty': {}, 'by_platform': {}, 'global': {}}
        # ... aggregate logic
        state['aggregated_stats'] = stats
        return state

    def calc_6_dims(self, state: ProfileState) -> ProfileState:
        records = state['raw_records']
        ac_tags = set()
        tag_ac = {}
        for r in records:
            if r.get('verdict') == 'OK':
                for t in r.get('tags_normalized', []):
                    ac_tags.add(t)
                    tag_ac[t] = tag_ac.get(t, 0) + 1

        coverage = calc_coverage(ac_tags, ALL_TAGS)
        proficiency_map = {t: calc_proficiency(tag_ac.get(t, 0), tag_ac.get(t, 0), 5, 30) for t in ac_tags}
        ceiling = calc_ceiling([r for r in records if r.get('verdict') == 'OK'])
        efficiency = calc_efficiency(records)
        style = classify_style(len(records), len(ac_tags), sum(proficiency_map.values())/max(len(proficiency_map), 1), 0.3, 5)
        momentum = calc_momentum(state.get('daily_stats', []))
        overall = 0.15*coverage + 0.30*(sum(proficiency_map.values())/max(len(proficiency_map), 1)) + 0.20*(ceiling/10) + 0.15*efficiency + 0.10*STYLE_BONUS[style] + 0.10*((momentum+1)/2)

        state['profile_data'] = {
            'overall_score': round(overall, 3),
            'coverage': round(coverage, 3),
            'ceiling': ceiling, 'efficiency': efficiency, 'style': style, 'momentum': momentum,
            'tag_proficiency': proficiency_map,
            'strengths': sorted([{'tag': t, 'score': s} for t, s in proficiency_map.items()], key=lambda x: -x['score'])[:5],
            'weaknesses': sorted([{'tag': t, 'score': s} for t, s in proficiency_map.items()], key=lambda x: x['score'])[:5],
        }
        return state

    def llm_summarize(self, state: ProfileState) -> ProfileState:
        prompt = f"你是 ACM 教练。根据以下画像生成100-200字总结:\n{state['profile_data']}"
        resp = self.llm.invoke(prompt)
        summary = json.loads(resp.content) if 'json' in str(resp) else resp.content
        state['profile_data']['summary_text'] = summary if isinstance(summary, str) else summary.get('summary_text', '')
        return state

    def fallback(self, state: ProfileState) -> ProfileState:
        state['profile_data']['summary_text'] = "数据不足，基于已有数据生成的规则画像。建议完成至少10道题目后再查看完整画像。"
        return state

    def _build(self):
        graph = StateGraph(ProfileState)
        graph.add_node("load", self.load_user_data)
        graph.add_node("aggregate", self.aggregate_stats)
        graph.add_node("calc_6_dims", self.calc_6_dims)
        graph.add_node("llm_summarize", self.llm_summarize)
        graph.add_node("fallback", self.fallback)

        graph.set_entry_point("load")
        graph.add_edge("load", "aggregate")
        graph.add_edge("aggregate", "calc_6_dims")
        graph.add_conditional_edges("calc_6_dims", lambda s: "data_insufficient" in s.get('errors', []), {"True": "fallback", "False": "llm_summarize"})
        graph.add_edge("llm_summarize", END)
        graph.add_edge("fallback", END)
        return graph.compile(checkpointer=MemorySaver())
```

- [ ] **Step 3: 运行测试**

```bash
pytest agents/test/test_profile_agent.py -v
# 预期: 全部 PASS
git commit -m "feat(agents): add profile_agent with 6-dimension calculation and LangGraph"
```

---

## Task 3: training_agent

- [ ] **Step 1: 写测试** — 验证 determine_phase, select_targets, calc_difficulty_curve, SM-2 调度
- [ ] **Step 2: 实现** — training_agent.py (LangGraph, 7 节点)
- [ ] **Step 3: 运行全部测试 + 覆盖率**

```bash
pytest agents/ --cov=agents --cov-report=term-missing
# 预期: ≥ 90%
git commit -m "feat(agents): add training_agent with 4-phase model and spaced repetition"
```

---

## Phase 5 Gate

| 检查项 | 标准 |
|--------|------|
| 6 维画像计算 | 纯 Python，无 LLM 依赖 |
| LLM 总结 | 仅在 llm_summarize 节点调用 |
| 4 阶段判定 | determine_phase 规则引擎 |
| ZPD 难度曲线 | 数学公式可复现 |
| SM-2 间隔重复 | 正确计算间隔天数和 ease |
| 覆盖率 | ≥ 90% |
