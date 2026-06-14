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
