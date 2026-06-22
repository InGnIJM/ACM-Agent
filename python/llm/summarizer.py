"""LLM-based problem summarization using DeepSeek."""

import json
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI

from .normalizer import TagNormalizer


class ProblemSummarizer:
    """Summarize an ACM problem via DeepSeek LLM and normalize its tags."""

    def __init__(self, deepseek_client: ChatOpenAI, normalizer: TagNormalizer):
        self._client = deepseek_client
        self._normalizer = normalizer
        self._valid_tags = set(normalizer.get_all_tags())

    async def summarize(self, problem: Dict[str, Any]) -> Dict[str, Any]:
        """Build a prompt, call DeepSeek, filter tags, and return structured results."""

        platform = problem.get("platform", "unknown")
        source_id = problem.get("source_id", "")
        title = problem.get("title", "")
        difficulty_raw = problem.get("difficulty_raw", "")
        tags_platform = problem.get("tags_platform", [])
        full_content = problem.get("full_content", "")

        content_truncated = (
            full_content[:3000] if len(full_content) > 3000 else full_content
        )

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

        response = await self._client.ainvoke(
            prompt,
            temperature=0.3,
            response_format="json_object",
        )

        parsed = json.loads(response.content)

        raw_tags: List[str] = parsed.get("tags_normalized", [])
        filtered_tags = [t for t in raw_tags if t in self._valid_tags]
        parsed["tags_normalized"] = filtered_tags

        return {
            "summary": parsed.get("summary", ""),
            "solution_approach": parsed.get("solution_approach", ""),
            "key_points": parsed.get("key_points", []),
            "pitfalls": parsed.get("pitfalls", []),
            "tags_normalized": filtered_tags,
            "difficulty_normalized": parsed.get("difficulty_normalized", 5.0),
            "similar_problems_hint": parsed.get("similar_problems_hint", ""),
            # New fields for RAG v1
            "retrieval_summary": parsed.get("retrieval_summary", ""),
            "sparse_text": parsed.get("sparse_text", ""),
            "primary_algo": parsed.get("primary_algo", ""),
            "sub_algos": parsed.get("sub_algos", []),
            "problem_patterns": parsed.get("problem_patterns", []),
        }

    def _format_summary(self, result: Dict[str, Any]) -> str:
        """Format the structured result into a single text column value."""
        parts: List[str] = []

        if result.get("summary"):
            parts.append(f"Summary: {result['summary']}")

        if result.get("solution_approach"):
            parts.append(f"Approach: {result['solution_approach']}")

        key_points = result.get("key_points", [])
        if key_points:
            parts.append("Key Points:\n" + "\n".join(f"  - {p}" for p in key_points))

        pitfalls = result.get("pitfalls", [])
        if pitfalls:
            parts.append("Pitfalls:\n" + "\n".join(f"  - {p}" for p in pitfalls))

        tags = result.get("tags_normalized", [])
        if tags:
            parts.append(f"Tags: {', '.join(tags)}")

        difficulty = result.get("difficulty_normalized")
        if difficulty is not None:
            parts.append(f"Difficulty: {difficulty}/10")

        hint = result.get("similar_problems_hint")
        if hint:
            parts.append(f"Similar: {hint}")

        return "\n\n".join(parts)
