"""Tests for ProblemSummarizer."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_openai import ChatOpenAI

from llm.normalizer import TagNormalizer
from llm.summarizer import ProblemSummarizer


SAMPLE_LLM_RESPONSE = {
    "summary": "Find the longest subarray with sum zero.",
    "solution_approach": "prefix_sum + hash map",
    "key_points": ["Zero-sum implies prefix sums equal.", "Use a hash map for O(n)."],
    "pitfalls": ["Empty subarray edge case.", "Large input may overflow int."],
    "tags_normalized": ["prefix_sum", "hash_map", "unknown_fake_tag", "two_pointers"],
    "difficulty_normalized": 4.5,
    "similar_problems_hint": "Similar to LeetCode 525 Contiguous Array.",
}


def _make_mock_client(response_json: dict) -> ChatOpenAI:
    """Build a mock ChatOpenAI whose ainvoke returns the given dict as JSON."""
    mock = MagicMock(spec=ChatOpenAI)
    mock_response = MagicMock()
    mock_response.content = json.dumps(response_json, ensure_ascii=False)
    mock.ainvoke = AsyncMock(return_value=mock_response)
    return mock


@pytest.fixture(scope="module")
def tag_normalizer():
    return TagNormalizer()


@pytest.fixture
def summarizer(tag_normalizer):
    client = _make_mock_client(SAMPLE_LLM_RESPONSE)
    return ProblemSummarizer(deepseek_client=client, normalizer=tag_normalizer)


@pytest.fixture
def sample_problem():
    return {
        "platform": "leetcode",
        "source_id": "525",
        "title": "Contiguous Array",
        "difficulty_raw": "Medium",
        "tags_platform": ["Prefix Sum", "Hash Map"],
        "full_content": "Given a binary array nums, return the maximum length of a contiguous subarray with an equal number of 0 and 1. "
        * 50,
    }


class TestProblemSummarizer:
    """Tests for ProblemSummarizer."""

    @pytest.mark.asyncio
    async def test_summarize_returns_expected_keys(self, summarizer, sample_problem):
        """Result dict should contain all expected keys."""
        result = await summarizer.summarize(sample_problem)

        assert isinstance(result, dict)
        for key in (
            "summary",
            "solution_approach",
            "key_points",
            "pitfalls",
            "tags_normalized",
            "difficulty_normalized",
            "similar_problems_hint",
        ):
            assert key in result

    @pytest.mark.asyncio
    async def test_tags_normalized_filtered_against_valid_tags(
        self, summarizer, sample_problem
    ):
        """Only tags that exist in normalizer.get_all_tags() should survive."""
        result = await summarizer.summarize(sample_problem)

        valid = set(summarizer._normalizer.get_all_tags())
        for tag in result["tags_normalized"]:
            assert tag in valid, f"Tag '{tag}' is not in the valid tag set"

    @pytest.mark.asyncio
    async def test_invalid_tags_are_removed(self, summarizer, sample_problem):
        """'unknown_fake_tag' from the mock response must be stripped out."""
        result = await summarizer.summarize(sample_problem)

        assert "unknown_fake_tag" not in result["tags_normalized"]
        assert "prefix_sum" in result["tags_normalized"]
        assert "hash_map" in result["tags_normalized"]
        assert "two_pointers" in result["tags_normalized"]

    def test_format_summary_produces_expected_sections(self, summarizer):
        """_format_summary should include all populated fields."""
        result = dict(SAMPLE_LLM_RESPONSE)
        result["tags_normalized"] = ["prefix_sum", "hash_map"]
        formatted = summarizer._format_summary(result)

        assert "Summary:" in formatted
        assert "Approach:" in formatted
        assert "Key Points:" in formatted
        assert "Pitfalls:" in formatted
        assert "Tags:" in formatted
        assert "Difficulty:" in formatted
        assert "Similar:" in formatted

    def test_format_summary_handles_empty_fields(self, summarizer):
        """Missing optional fields should be gracefully omitted."""
        result = {
            "summary": "Just a summary.",
            "solution_approach": "",
            "key_points": [],
            "pitfalls": [],
            "tags_normalized": [],
            "difficulty_normalized": None,
            "similar_problems_hint": "",
        }
        formatted = summarizer._format_summary(result)

        assert "Summary: Just a summary." in formatted
        assert "Approach:" not in formatted
        assert "Key Points:" not in formatted
        assert "Pitfalls:" not in formatted
        assert "Tags:" not in formatted
        assert "Difficulty:" not in formatted
        assert "Similar:" not in formatted

    @pytest.mark.asyncio
    async def test_content_truncated_at_3000_chars(self, tag_normalizer):
        """Content longer than 3000 chars must be truncated before sending to LLM."""
        captured_prompt = []

        mock = MagicMock(spec=ChatOpenAI)
        mock_response = MagicMock()
        mock_response.content = json.dumps(SAMPLE_LLM_RESPONSE, ensure_ascii=False)

        async def _capture(prompt, **kwargs):
            captured_prompt.append(prompt)
            return mock_response

        mock.ainvoke = _capture

        s = ProblemSummarizer(deepseek_client=mock, normalizer=tag_normalizer)

        long_content = "A" * 5000
        problem = {
            "platform": "cf",
            "source_id": "1A",
            "title": "Big Input",
            "difficulty_raw": "1500",
            "tags_platform": [],
            "full_content": long_content,
        }

        await s.summarize(problem)

        sent_prompt = captured_prompt[0]
        assert "AAAA" in sent_prompt
        assert sent_prompt.count("A") <= 3000 + 500
