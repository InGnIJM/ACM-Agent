"""
Tests for crawlers/leetcode.py – LeetCodeCrawler.

All GraphQL calls are mocked via _graphql so no real network calls are made.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import CrawlResult, RateLimiter
from crawlers.leetcode import (
    LeetCodeCrawler,
    _USER_PROFILE_QUERY,
    _RECENT_AC_SUBMISSIONS_QUERY,
    _PROBLEM_QUERY,
    _PROBLEMSET_QUERY,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _mock_crawler() -> LeetCodeCrawler:
    """Return a LeetCodeCrawler with _rate_limiter set to no-op and _graphql mocked."""
    crawler = LeetCodeCrawler.__new__(LeetCodeCrawler)
    crawler.PLATFORM = "leetcode"
    crawler.data_dir = MagicMock()
    crawler.headless = True
    crawler._session = MagicMock()
    crawler._browser = None
    crawler._rate_limiter = RateLimiter(qps=100, jitter=0)
    crawler._cookie_manager = MagicMock()
    crawler._cookie_manager.load.return_value = None

    # Attach a mock for _graphql; test methods will set return_value.
    crawler._graphql = MagicMock()
    return crawler


def _crawl_ok(data: object) -> CrawlResult:
    return CrawlResult(success=True, data=data, source="http")


# ──────────────────────────────────────────────
# _default_qps
# ──────────────────────────────────────────────

class TestLeetCodeDefaultQps:
    def test_default_qps_is_1(self) -> None:
        assert LeetCodeCrawler._default_qps() == 1.0


# ──────────────────────────────────────────────
# GraphQL URL constant
# ──────────────────────────────────────────────

class TestLeetCodeGraphqlUrl:
    def test_graphql_url(self) -> None:
        assert LeetCodeCrawler.GRAPHQL_URL == "https://leetcode.cn/graphql"


# ──────────────────────────────────────────────
# fetch_user_profile
# ──────────────────────────────────────────────

class TestLeetCodeFetchUserProfile:
    """Tests for LeetCodeCrawler.fetch_user_profile."""

    def test_sends_correct_graphql_query(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "matchedUser": {
                    "username": "testuser",
                    "profile": {"realName": "Test User", "ranking": 12345},
                }
            }
        )
        result = c.fetch_user_profile("testuser")

        # Verify _graphql was called with correct query and variables.
        c._graphql.assert_called_once()
        call_args = c._graphql.call_args
        assert call_args[0][0] == _USER_PROFILE_QUERY
        assert call_args[1]["variables"] == {"username": "testuser"}

        assert result.success
        assert result.data["username"] == "testuser"
        assert result.data["profile"]["realName"] == "Test User"

    def test_user_not_found_returns_error(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({"matchedUser": None})
        result = c.fetch_user_profile("nonexistent")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    def test_graphql_failure_passthrough(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = CrawlResult(
            success=False, error="GraphQL errors: user not found", source="http"
        )
        result = c.fetch_user_profile("user")
        assert not result.success
        assert "GraphQL errors" in (result.error or "")

    def test_null_data_passthrough(self) -> None:
        """When _graphql returns success=True with data=None, the method
        returns the CrawlResult as-is (it passes the 'data is None' check)."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(None)
        result = c.fetch_user_profile("user")
        # The method returns the CrawlResult from _graphql unchanged because
        # success=True but data is None triggers the early return.
        assert result.success
        assert result.data is None

    def test_non_dict_data_with_no_matched_user(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok([1, 2, 3])
        result = c.fetch_user_profile("user")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    def test_verify_variables_format(self) -> None:
        """Verify variables dict is formatted as expected by GraphQL API."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {"matchedUser": {"username": "u", "profile": {}}}
        )
        c.fetch_user_profile("myUsername")
        variables = c._graphql.call_args[1]["variables"]
        assert variables == {"username": "myUsername"}
        assert isinstance(variables["username"], str)


# ──────────────────────────────────────────────
# fetch_user_records
# ──────────────────────────────────────────────

class TestLeetCodeFetchUserRecords:
    """Tests for LeetCodeCrawler.fetch_user_records."""

    def test_sends_correct_query_and_variables(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "recentAcSubmissionList": [
                    {
                        "id": "1",
                        "title": "Two Sum",
                        "titleSlug": "two-sum",
                        "timestamp": "1700000000",
                        "lang": "python3",
                        "statusDisplay": "Accepted",
                    }
                ]
            }
        )
        result = c.fetch_user_records("testuser")

        c._graphql.assert_called_once()
        call_args = c._graphql.call_args
        assert call_args[0][0] == _RECENT_AC_SUBMISSIONS_QUERY
        assert call_args[1]["variables"] == {"username": "testuser", "limit": 20}

        assert result.success
        assert len(result.data) == 1
        assert result.data[0]["title"] == "Two Sum"

    def test_empty_submissions_list(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({"recentAcSubmissionList": []})
        result = c.fetch_user_records("newuser")
        assert result.success
        assert result.data == []

    def test_graphql_failure_passthrough(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = CrawlResult(
            success=False, error="HTTP 429", source="http"
        )
        result = c.fetch_user_records("user")
        assert not result.success
        assert "429" in (result.error or "")

    def test_null_data_passthrough(self) -> None:
        """When _graphql returns success=True with data=None, the method
        returns the CrawlResult as-is."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(None)
        result = c.fetch_user_records("user")
        assert result.success
        assert result.data is None

    def test_non_dict_data_returns_empty_list(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(["not", "a", "dict"])
        result = c.fetch_user_records("user")
        assert result.success
        assert result.data == []

    def test_since_param_accepted_but_not_used(self) -> None:
        """since param is accepted for interface compatibility but ignored."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({"recentAcSubmissionList": []})
        result = c.fetch_user_records("user", since="2025-01-01")
        assert result.success
        # Verify the GraphQL call did not include since in variables.
        call_vars = c._graphql.call_args[1]["variables"]
        assert "since" not in call_vars
        assert call_vars == {"username": "user", "limit": 20}


# ──────────────────────────────────────────────
# fetch_problem
# ──────────────────────────────────────────────

class TestLeetCodeFetchProblem:
    """Tests for LeetCodeCrawler.fetch_problem."""

    def test_sends_correct_query_and_variables(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "1",
                    "title": "Two Sum",
                    "titleSlug": "two-sum",
                    "difficulty": "Easy",
                    "content": "<p>Find two numbers...</p>",
                }
            }
        )
        result = c.fetch_problem("two-sum")

        c._graphql.assert_called_once()
        call_args = c._graphql.call_args
        assert call_args[0][0] == _PROBLEM_QUERY
        assert call_args[1]["variables"] == {"titleSlug": "two-sum"}

        assert result.success
        assert result.data["title"] == "Two Sum"
        assert result.data["difficulty"] == "Easy"

    def test_problem_not_found(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({"question": None})
        result = c.fetch_problem("nonexistent-problem")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    def test_graphql_failure_passthrough(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = CrawlResult(
            success=False, error="timeout", source="http"
        )
        result = c.fetch_problem("two-sum")
        assert not result.success

    def test_null_data_passthrough(self) -> None:
        """When _graphql returns success=True with data=None, the method
        returns the CrawlResult as-is."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(None)
        result = c.fetch_problem("two-sum")
        assert result.success
        assert result.data is None

    def test_non_dict_data_no_question_key(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(["unexpected"])
        result = c.fetch_problem("two-sum")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    def test_prefers_translated_title_and_content(self) -> None:
        """When translatedTitle/translatedContent are present, they replace title/content."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "1",
                    "title": "Two Sum",
                    "translatedTitle": "两数之和",
                    "titleSlug": "two-sum",
                    "difficulty": "Easy",
                    "content": "<p>English description</p>",
                    "translatedContent": "<p>中文描述</p>",
                }
            }
        )
        result = c.fetch_problem("two-sum")
        assert result.success
        assert result.data["title"] == "两数之和"
        assert result.data["content"] == "<p>中文描述</p>"

    def test_keeps_english_when_no_translation(self) -> None:
        """When translatedTitle/translatedContent are absent or empty, keep original."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "1",
                    "title": "Two Sum",
                    "titleSlug": "two-sum",
                    "difficulty": "Easy",
                    "content": "<p>English description</p>",
                }
            }
        )
        result = c.fetch_problem("two-sum")
        assert result.success
        assert result.data["title"] == "Two Sum"
        assert result.data["content"] == "<p>English description</p>"

    def test_partial_translation_content_only(self) -> None:
        """When only translatedContent is present (not translatedTitle)."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "1",
                    "title": "Two Sum",
                    "translatedContent": "<p>中文描述</p>",
                    "titleSlug": "two-sum",
                    "difficulty": "Easy",
                    "content": "<p>English description</p>",
                }
            }
        )
        result = c.fetch_problem("two-sum")
        assert result.success
        assert result.data["title"] == "Two Sum"
        assert result.data["content"] == "<p>中文描述</p>"

    def test_null_translated_fields_not_used(self) -> None:
        """When translatedTitle/translatedContent are None, keep original."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "1",
                    "title": "Two Sum",
                    "translatedTitle": None,
                    "titleSlug": "two-sum",
                    "content": "<p>English</p>",
                    "translatedContent": None,
                }
            }
        )
        result = c.fetch_problem("two-sum")
        assert result.success
        assert result.data["title"] == "Two Sum"
        assert result.data["content"] == "<p>English</p>"

    def test_difficulty_normalized_easy(self) -> None:
        """Difficulty string 'Easy' → numeric 1."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "1",
                    "title": "Two Sum",
                    "titleSlug": "two-sum",
                    "difficulty": "Easy",
                    "content": "<p>test</p>",
                }
            }
        )
        result = c.fetch_problem("two-sum")
        assert result.success
        assert result.data["difficulty"] == "Easy"  # original preserved
        assert result.data["difficultyNormalized"] == 1

    def test_difficulty_normalized_medium(self) -> None:
        """Difficulty string 'Medium' → numeric 2."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "2",
                    "title": "Add Two Numbers",
                    "titleSlug": "add-two-numbers",
                    "difficulty": "Medium",
                    "content": "<p>test</p>",
                }
            }
        )
        result = c.fetch_problem("add-two-numbers")
        assert result.success
        assert result.data["difficultyNormalized"] == 2

    def test_difficulty_normalized_hard(self) -> None:
        """Difficulty string 'Hard' → numeric 3."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "3",
                    "title": "Median of Two Sorted Arrays",
                    "titleSlug": "median-of-two-sorted-arrays",
                    "difficulty": "Hard",
                    "content": "<p>test</p>",
                }
            }
        )
        result = c.fetch_problem("median-of-two-sorted-arrays")
        assert result.success
        assert result.data["difficultyNormalized"] == 3

    def test_difficulty_normalized_unknown_defaults_to_1(self) -> None:
        """Unknown/empty difficulty string defaults to 1."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "4",
                    "title": "Unknown Diff",
                    "titleSlug": "unknown-diff",
                    "difficulty": "",
                    "content": "<p>test</p>",
                }
            }
        )
        result = c.fetch_problem("unknown-diff")
        assert result.success
        assert result.data["difficultyNormalized"] == 1

    def test_difficulty_normalized_case_insensitive(self) -> None:
        """Difficulty mapping is case-insensitive."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "5",
                    "title": "Case Test",
                    "titleSlug": "case-test",
                    "difficulty": "EASY",
                    "content": "<p>test</p>",
                }
            }
        )
        result = c.fetch_problem("case-test")
        assert result.success
        assert result.data["difficultyNormalized"] == 1

    def test_input_output_format_extraction(self) -> None:
        """Extracts input/output format from HTML content with dedicated format sections."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "6",
                    "title": "Format Test",
                    "titleSlug": "format-test",
                    "difficulty": "Easy",
                    "content": (
                        "<p>Problem description here.</p>"
                        "<p><strong>输入格式：</strong>第一行包含一个整数 N。</p>"
                        "<p><strong>输出格式：</strong>输出一个整数表示结果。</p>"
                    ),
                }
            }
        )
        result = c.fetch_problem("format-test")
        assert result.success
        assert "第一行包含一个整数 N" in result.data["input_format"]
        assert "输出一个整数表示结果" in result.data["output_format"]

    def test_input_output_format_english_markers(self) -> None:
        """Extracts format using English 'Input Format:' / 'Output Format:' markers."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "7",
                    "title": "English Format",
                    "titleSlug": "english-format",
                    "difficulty": "Easy",
                    "content": (
                        "<p>Description.</p>"
                        "<p><strong>Input Format:</strong>The first line contains T.</p>"
                        "<p><strong>Output Format:</strong>Print the result.</p>"
                    ),
                }
            }
        )
        result = c.fetch_problem("english-format")
        assert result.success
        assert "first line contains T" in result.data["input_format"]
        assert "Print the result" in result.data["output_format"]

    def test_input_output_format_no_markers_returns_empty(self) -> None:
        """Returns empty strings when no format markers found."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "8",
                    "title": "No Format",
                    "titleSlug": "no-format",
                    "difficulty": "Easy",
                    "content": "<p>Just a simple problem with no format description.</p>",
                }
            }
        )
        result = c.fetch_problem("no-format")
        assert result.success
        assert result.data["input_format"] == ""
        assert result.data["output_format"] == ""

    def test_input_output_format_ignores_pre_blocks(self) -> None:
        """Ignores 'Input:' / 'Output:' markers inside <pre> (example) blocks."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "9",
                    "title": "Pre Block Test",
                    "titleSlug": "pre-block-test",
                    "difficulty": "Easy",
                    "content": (
                        "<p>Problem description.</p>"
                        "<pre><strong>Input:</strong>1 2 3\n<strong>Output:</strong>6</pre>"
                        "<p><strong>输入：</strong>输入包含两个整数。</p>"
                        "<p><strong>输出：</strong>输出它们的和。</p>"
                    ),
                }
            }
        )
        result = c.fetch_problem("pre-block-test")
        assert result.success
        # Should NOT have matched the example input/output inside <pre>
        assert "输入包含两个整数" in result.data["input_format"]
        assert "输出它们的和" in result.data["output_format"]

    def test_hints_included_as_array(self) -> None:
        """Hints array from GraphQL is preserved as-is in the returned data."""
        c = _mock_crawler()
        hints = ["Hint 1: Try sorting.", "Hint 2: Use two pointers."]
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "10",
                    "title": "Hint Test",
                    "titleSlug": "hint-test",
                    "difficulty": "Easy",
                    "content": "<p>test</p>",
                    "hints": hints,
                }
            }
        )
        result = c.fetch_problem("hint-test")
        assert result.success
        assert result.data["hints"] == hints
        assert len(result.data["hints"]) == 2

    def test_hints_defaults_to_empty_list(self) -> None:
        """When hints is not in the GraphQL response, defaults to empty list."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "11",
                    "title": "No Hints",
                    "titleSlug": "no-hints",
                    "difficulty": "Easy",
                    "content": "<p>test</p>",
                }
            }
        )
        result = c.fetch_problem("no-hints")
        assert result.success
        assert result.data["hints"] == []

    def test_hints_none_defaults_to_empty_list(self) -> None:
        """When hints is present but None, defaults to empty list."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "question": {
                    "questionId": "12",
                    "title": "Null Hints",
                    "titleSlug": "null-hints",
                    "difficulty": "Easy",
                    "content": "<p>test</p>",
                    "hints": None,
                }
            }
        )
        result = c.fetch_problem("null-hints")
        assert result.success
        assert result.data["hints"] == []

    # ── sample parsing (sampleTestCase / exampleTestcases → [[in,out],..]) ──

    def test_samples_single_param_multiple_examples(self) -> None:
        """metaData with 1 param → each input line is one test case."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "20",
                "title": "Single Param",
                "titleSlug": "single-param",
                "difficulty": "Easy",
                "content": "<p>test</p>",
                "sampleTestCase": "1\n2\n3",
                "exampleTestcases": "10\n20\n30",
                "metaData": '{"name":"solve","params":[{"name":"n","type":"integer"}],"return":{"type":"integer"}}',
            }
        })
        result = c.fetch_problem("single-param")
        assert result.success
        assert "samples" in result.data
        samples = result.data["samples"]
        assert len(samples) == 3
        assert samples[0] == ["1", "10"]
        assert samples[1] == ["2", "20"]
        assert samples[2] == ["3", "30"]

    def test_samples_two_param_problem(self) -> None:
        """metaData with 2 params → every 2 input lines = one test case."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "21",
                "title": "Two Param",
                "titleSlug": "two-param",
                "difficulty": "Medium",
                "content": "<p>test</p>",
                "sampleTestCase": "[2,7,11,15]\n9\n[3,2,4]\n6",
                "exampleTestcases": "[0,1]\n[1,2]",
                "metaData": '{"name":"twoSum","params":[{"name":"nums","type":"integer[]"},{"name":"target","type":"integer"}],"return":{"type":"integer[]"}}',
            }
        })
        result = c.fetch_problem("two-param")
        assert result.success
        samples = result.data["samples"]
        assert len(samples) == 2
        assert samples[0] == ["[2,7,11,15]\n9", "[0,1]"]
        assert samples[1] == ["[3,2,4]\n6", "[1,2]"]

    def test_samples_auto_detect_param_count_no_metadata(self) -> None:
        """Without metaData, auto-detect param count from line counts (2 params, 2 examples)."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "22",
                "title": "Auto Detect",
                "titleSlug": "auto-detect",
                "difficulty": "Easy",
                "content": "<p>test</p>",
                "sampleTestCase": "1 2\n3\n4 5\n6",
                "exampleTestcases": "3\n9",
                "metaData": None,
            }
        })
        result = c.fetch_problem("auto-detect")
        assert result.success
        samples = result.data["samples"]
        assert len(samples) == 2
        # Auto-detection: 4 input lines, 2 output lines → param_count=2
        assert samples[0] == ["1 2\n3", "3"]
        assert samples[1] == ["4 5\n6", "9"]

    def test_samples_no_sample_data_present(self) -> None:
        """When sampleTestCase/exampleTestcases missing, samples is not set."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "23",
                "title": "No Samples",
                "titleSlug": "no-samples",
                "difficulty": "Easy",
                "content": "<p>test</p>",
                "metaData": '{"name":"f","params":[{"name":"x","type":"integer"}]}',
            }
        })
        result = c.fetch_problem("no-samples")
        assert result.success
        assert "samples" in result.data
        assert result.data["samples"] == []
        # Original string fields may still be absent (None)
        assert result.data.get("sampleTestCase") is None

    def test_samples_empty_strings_no_samples_set(self) -> None:
        """Empty sampleTestCase/exampleTestcases should not produce samples."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "24",
                "title": "Empty Samples",
                "titleSlug": "empty-samples",
                "difficulty": "Easy",
                "content": "<p>test</p>",
                "sampleTestCase": "",
                "exampleTestcases": "   ",
                "metaData": '{"name":"f","params":[{"name":"x","type":"integer"}]}',
            }
        })
        result = c.fetch_problem("empty-samples")
        assert result.success
        assert "samples" in result.data
        assert result.data["samples"] == []

    def test_samples_metadata_parse_failure_auto_detects(self) -> None:
        """Invalid JSON metaData → fallback to auto-detection."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "25",
                "title": "Bad Metadata",
                "titleSlug": "bad-metadata",
                "difficulty": "Easy",
                "content": "<p>test</p>",
                "sampleTestCase": "a\nb\nc",
                "exampleTestcases": "x\ny\nz",
                "metaData": "not-valid-json",
            }
        })
        result = c.fetch_problem("bad-metadata")
        assert result.success
        samples = result.data["samples"]
        # Auto-detection: 3 input lines, 3 output lines → param_count=1
        assert len(samples) == 3
        assert samples[0] == ["a", "x"]
        assert samples[1] == ["b", "y"]
        assert samples[2] == ["c", "z"]

    def test_samples_partial_output_count_graceful(self) -> None:
        """When there are more input groups than output lines, output lines
        are paired as available."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "26",
                "title": "Partial Outputs",
                "titleSlug": "partial-outputs",
                "difficulty": "Easy",
                "content": "<p>test</p>",
                "sampleTestCase": "1\n2\n3",
                "exampleTestcases": "10",
                "metaData": '{"name":"f","params":[{"name":"x","type":"integer"}]}',
            }
        })
        result = c.fetch_problem("partial-outputs")
        assert result.success
        samples = result.data["samples"]
        # Only 1 output for 3 inputs — first group paired, rest get empty
        assert len(samples) == 3
        assert samples[0] == ["1", "10"]
        assert samples[1] == ["2", ""]
        assert samples[2] == ["3", ""]

    def test_samples_metadata_no_params_auto_detects(self) -> None:
        """metaData with empty params array → auto-detect."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "27",
                "title": "No Params",
                "titleSlug": "no-params",
                "difficulty": "Easy",
                "content": "<p>test</p>",
                "sampleTestCase": "X\nY",
                "exampleTestcases": "A\nB",
                "metaData": '{"name":"f","params":[]}',
            }
        })
        result = c.fetch_problem("no-params")
        assert result.success
        samples = result.data["samples"]
        # Auto-detection: 2 in, 2 out → param_count=1
        assert len(samples) == 2
        assert samples[0] == ["X", "A"]
        assert samples[1] == ["Y", "B"]

    def test_samples_preserves_raw_string_fields(self) -> None:
        """sampleTestCase and exampleTestcases are kept alongside samples."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({
            "question": {
                "questionId": "28",
                "title": "Raw Preserved",
                "titleSlug": "raw-preserved",
                "difficulty": "Easy",
                "content": "<p>test</p>",
                "sampleTestCase": "42",
                "exampleTestcases": "84",
                "metaData": '{"name":"f","params":[{"name":"x","type":"integer"}]}',
            }
        })
        result = c.fetch_problem("raw-preserved")
        assert result.success
        assert result.data["sampleTestCase"] == "42"
        assert result.data["exampleTestcases"] == "84"
        assert result.data["samples"] == [["42", "84"]]


# ──────────────────────────────────────────────
# fetch_problems_by_tag
# ──────────────────────────────────────────────

class TestLeetCodeFetchProblemsByTag:
    """Tests for LeetCodeCrawler.fetch_problems_by_tag."""

    def test_sends_correct_query_and_variables(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "problemsetQuestionList": {
                    "total": 100,
                    "questions": [
                        {
                            "title": "Two Sum",
                            "titleSlug": "two-sum",
                            "difficulty": "Easy",
                        },
                        {
                            "title": "Three Sum",
                            "titleSlug": "3sum",
                            "difficulty": "Medium",
                        },
                    ],
                }
            }
        )
        result = c.fetch_problems_by_tag("array", count=50)

        c._graphql.assert_called_once()
        call_args = c._graphql.call_args
        assert call_args[0][0] == _PROBLEMSET_QUERY
        variables = call_args[1]["variables"]
        assert variables["categorySlug"] == ""
        assert variables["limit"] == 50
        assert variables["skip"] == 0
        assert variables["filters"] == {"tags": ["array"]}

        assert result.success
        assert len(result.data) == 2

    def test_caps_limit_at_100(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "problemsetQuestionList": {
                    "total": 200,
                    "questions": [{"title": "Test", "titleSlug": "test"}] * 50,
                }
            }
        )
        result = c.fetch_problems_by_tag("dp", count=200)
        call_vars = c._graphql.call_args[1]["variables"]
        assert call_vars["limit"] == 100  # capped at 100
        assert result.success

    def test_respects_count_limit_in_output(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {
                "problemsetQuestionList": {
                    "total": 100,
                    "questions": [{"title": f"Problem {i}", "titleSlug": f"p{i}"} for i in range(50)],
                }
            }
        )
        result = c.fetch_problems_by_tag("array", count=10)
        assert len(result.data) == 10

    def test_empty_questions_list(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(
            {"problemsetQuestionList": {"total": 0, "questions": []}}
        )
        result = c.fetch_problems_by_tag("nonexistent-tag")
        assert result.success
        assert result.data == []

    def test_graphql_failure_passthrough(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = CrawlResult(
            success=False, error="rate limit", source="http"
        )
        result = c.fetch_problems_by_tag("array")
        assert not result.success

    def test_null_data_passthrough(self) -> None:
        """When _graphql returns success=True with data=None, the method
        returns the CrawlResult as-is."""
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(None)
        result = c.fetch_problems_by_tag("array")
        assert result.success
        assert result.data is None

    def test_non_dict_data_returns_error(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok(["unexpected", "format"])
        result = c.fetch_problems_by_tag("array")
        assert not result.success
        assert "Unexpected problemset" in (result.error or "")

    def test_missing_problemset_question_list_key(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({"otherKey": "value"})
        result = c.fetch_problems_by_tag("array")
        assert result.success
        assert result.data == []

    def test_problemset_question_list_is_not_dict(self) -> None:
        c = _mock_crawler()
        c._graphql.return_value = _crawl_ok({"problemsetQuestionList": ["bad", "type"]})
        result = c.fetch_problems_by_tag("array")
        assert result.success
        assert result.data == []


# ──────────────────────────────────────────────
# _graphql method (via mock on session.post)
# ──────────────────────────────────────────────

class TestLeetCodeGraphQLMethod:
    """Test the _graphql method directly by mocking the session post."""

    def _setup_crawler_with_real_graphql(self) -> LeetCodeCrawler:
        """Create a crawler with a real _graphql but mocked _session.post."""
        crawler = LeetCodeCrawler.__new__(LeetCodeCrawler)
        crawler.PLATFORM = "leetcode"
        crawler.data_dir = MagicMock()
        crawler.headless = True
        crawler._session = MagicMock()
        crawler._browser = None
        crawler._rate_limiter = RateLimiter(qps=100, jitter=0)
        crawler._cookie_manager = MagicMock()
        crawler._cookie_manager.load.return_value = None
        crawler.GRAPHQL_URL = "https://leetcode.cn/graphql"  # ensure set
        return crawler

    def test_graphql_success(self) -> None:
        c = self._setup_crawler_with_real_graphql()
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"data": {"matchedUser": {"username": "u"}}}
        c._session.post.return_value = fake_resp

        result = c._graphql("query { test }", variables={"x": 1})
        assert result.success
        assert result.data == {"matchedUser": {"username": "u"}}

        # Verify POST was made correctly.
        c._session.post.assert_called_once()
        call_kwargs = c._session.post.call_args
        assert call_kwargs[0][0] == "https://leetcode.cn/graphql"
        assert call_kwargs[1]["json"]["query"] == "query { test }"
        assert call_kwargs[1]["json"]["variables"] == {"x": 1}
        assert call_kwargs[1]["headers"]["Content-Type"] == "application/json"

    def test_graphql_429_error(self) -> None:
        c = self._setup_crawler_with_real_graphql()
        fake_resp = MagicMock()
        fake_resp.status_code = 429
        c._session.post.return_value = fake_resp

        result = c._graphql("query { test }")
        assert not result.success
        assert "429" in (result.error or "")

    def test_graphql_500_error(self) -> None:
        c = self._setup_crawler_with_real_graphql()
        fake_resp = MagicMock()
        fake_resp.status_code = 500
        c._session.post.return_value = fake_resp

        result = c._graphql("query { test }")
        assert not result.success
        assert "500" in (result.error or "")

    def test_graphql_invalid_json_response(self) -> None:
        c = self._setup_crawler_with_real_graphql()
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.side_effect = ValueError("not json")
        c._session.post.return_value = fake_resp

        result = c._graphql("query { test }")
        assert not result.success
        assert "not valid JSON" in (result.error or "")

    def test_graphql_errors_without_data(self) -> None:
        c = self._setup_crawler_with_real_graphql()
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "errors": [{"message": "Something went wrong"}],
            "data": None,
        }
        c._session.post.return_value = fake_resp

        result = c._graphql("query { bad }")
        assert not result.success
        assert "Something went wrong" in (result.error or "")

    def test_graphql_errors_with_data_still_succeeds(self) -> None:
        """GraphQL may return partial data alongside errors."""
        c = self._setup_crawler_with_real_graphql()
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "errors": [{"message": "Field x is deprecated"}],
            "data": {"matchedUser": {"username": "u"}},
        }
        c._session.post.return_value = fake_resp

        result = c._graphql("query { user }")
        assert result.success
        assert result.data == {"matchedUser": {"username": "u"}}

    def test_graphql_exception(self) -> None:
        c = self._setup_crawler_with_real_graphql()
        c._session.post.side_effect = ConnectionError("refused")

        result = c._graphql("query { test }")
        assert not result.success
        assert "refused" in (result.error or "")

    def test_graphql_multiple_errors(self) -> None:
        c = self._setup_crawler_with_real_graphql()
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "errors": [
                {"message": "Error 1"},
                {"message": "Error 2"},
            ],
            "data": None,
        }
        c._session.post.return_value = fake_resp

        result = c._graphql("query { test }")
        assert not result.success
        assert "Error 1" in (result.error or "")
        assert "Error 2" in (result.error or "")

    def test_graphql_default_variables(self) -> None:
        """_graphql should default variables to empty dict."""
        c = self._setup_crawler_with_real_graphql()
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"data": {"ok": True}}
        c._session.post.return_value = fake_resp

        result = c._graphql("query { test }")
        assert result.success
        call_json = c._session.post.call_args[1]["json"]
        assert call_json["variables"] == {}
