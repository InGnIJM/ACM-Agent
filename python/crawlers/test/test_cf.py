"""
Tests for crawlers/codeforces.py – CodeforcesCrawler.

All HTTP is mocked via _http_request so no real network calls are made.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import CrawlResult, RateLimiter
from crawlers.codeforces import CodeforcesCrawler


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _mock_crawler() -> CodeforcesCrawler:
    """Return a CodeforcesCrawler with _rate_limiter set to no-op and _http_request mocked."""
    crawler = CodeforcesCrawler.__new__(CodeforcesCrawler)
    crawler.PLATFORM = "codeforces"
    crawler.API_URL = "https://codeforces.com/api"
    crawler.data_dir = MagicMock()
    crawler.headless = True
    crawler._session = MagicMock()
    crawler._browser = None
    crawler._rate_limiter = RateLimiter(qps=100, jitter=0)
    crawler._cookie_manager = MagicMock()
    crawler._cookie_manager.load.return_value = None

    # Attach a mock for _http_request; test methods will set return_value.
    crawler._http_request = MagicMock()
    return crawler


def _crawl_ok(data: object) -> CrawlResult:
    return CrawlResult(success=True, data=data, source="http")


# ──────────────────────────────────────────────
# _default_qps
# ──────────────────────────────────────────────

class TestCodeforcesDefaultQps:
    """Verify Codeforces default QPS is 5.0."""

    def test_default_qps_is_5(self) -> None:
        assert CodeforcesCrawler._default_qps() == 5.0

    def test_default_qps_type_is_float(self) -> None:
        assert isinstance(CodeforcesCrawler._default_qps(), float)


# ──────────────────────────────────────────────
# API_URL constant
# ──────────────────────────────────────────────

class TestCodeforcesApiUrl:
    def test_api_url_constant(self) -> None:
        assert CodeforcesCrawler.API_URL == "https://codeforces.com/api"


# ──────────────────────────────────────────────
# PLATFORM constant
# ──────────────────────────────────────────────

class TestCodeforcesPlatform:
    def test_platform_name(self) -> None:
        assert CodeforcesCrawler.PLATFORM == "codeforces"


# ──────────────────────────────────────────────
# _api helper – URL construction
# ──────────────────────────────────────────────

class TestCodeforcesApi:
    """Tests for CodeforcesCrawler._api method."""

    def test_url_construction_simple(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": [{"handle": "tourist"}]}
        )
        result = c._api("user.info", handles="tourist")
        call_arg = c._http_request.call_args[0][0]
        assert call_arg == "https://codeforces.com/api/user.info?handles=tourist"

    def test_url_construction_multiple_params(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": []}
        )
        c._api("user.status", handle="tourist", **{"from": "1", "count": "1000"})
        call_arg = c._http_request.call_args[0][0]
        assert "https://codeforces.com/api/user.status?" in call_arg
        assert "handle=tourist" in call_arg
        assert "from=1" in call_arg
        assert "count=1000" in call_arg

    def test_url_construction_skips_none_params(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": []}
        )
        c._api("problemset.problems", tags="dp", extra=None)
        call_arg = c._http_request.call_args[0][0]
        assert "extra" not in call_arg
        assert "None" not in call_arg

    def test_api_ok_unwraps_result(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": {"field": "value"}}
        )
        result = c._api("some.method")
        assert result.success
        assert result.data == {"field": "value"}

    def test_api_non_ok_status(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "FAILED", "comment": "Invalid params"}
        )
        result = c._api("bad.method")
        assert not result.success
        assert "Invalid params" in (result.error or "")

    def test_api_non_ok_status_no_comment(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "FAILED"}
        )
        result = c._api("bad.method")
        assert not result.success
        assert "non-ok" in (result.error or "").lower()

    def test_api_http_failure_passthrough(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="Connection error", source="http"
        )
        result = c._api("user.info", handles="tourist")
        assert not result.success
        assert "Connection error" in (result.error or "")

    def test_api_non_dict_response_forwarded(self) -> None:
        """When _http_request returns non-dict data, forward as-is."""
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok([1, 2, 3])
        result = c._api("some.method")
        assert result.success
        assert result.data == [1, 2, 3]

    def test_api_no_query_params(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": []}
        )
        c._api("problemset.problems")
        call_arg = c._http_request.call_args[0][0]
        assert call_arg == "https://codeforces.com/api/problemset.problems"


# ──────────────────────────────────────────────
# fetch_user_profile
# ──────────────────────────────────────────────

class TestCodeforcesFetchUserProfile:
    """Tests for CodeforcesCrawler.fetch_user_profile."""

    def test_returns_crawl_result_with_user_data(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "status": "OK",
                "result": [
                    {
                        "handle": "tourist",
                        "rating": 3800,
                        "maxRating": 4000,
                        "rank": "legendary grandmaster",
                    }
                ],
            }
        )
        result = c.fetch_user_profile("tourist")
        assert isinstance(result, CrawlResult)
        assert result.success
        assert result.data["handle"] == "tourist"
        assert result.data["rating"] == 3800
        assert result.source == "http"

    def test_constructs_correct_url(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": [{"handle": "user"}]}
        )
        c.fetch_user_profile("test_handle")
        call_arg = c._http_request.call_args[0][0]
        expected = "https://codeforces.com/api/user.info?handles=test_handle"
        assert call_arg == expected

    def test_user_not_found_empty_list(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": []}
        )
        result = c.fetch_user_profile("nonexistent_user_xyz")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    def test_user_not_found_non_list_result(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": None}
        )
        result = c.fetch_user_profile("nonexistent")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    def test_api_error_passthrough(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="HTTP 503", source="http"
        )
        result = c.fetch_user_profile("user")
        assert not result.success
        assert "503" in (result.error or "")

    def test_dict_result_not_list(self) -> None:
        """When CF returns a dict instead of list for user.info (unexpected but handled)."""
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": {"handle": "single"}}
        )
        result = c.fetch_user_profile("user")
        assert result.success
        assert result.data == {"handle": "single"}


# ──────────────────────────────────────────────
# fetch_user_records
# ──────────────────────────────────────────────

class TestCodeforcesFetchUserRecords:
    """Tests for CodeforcesCrawler.fetch_user_records."""

    def test_returns_submissions_list(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "status": "OK",
                "result": [
                    {"id": 1, "problem": {"name": "A+B"}, "verdict": "OK"},
                    {"id": 2, "problem": {"name": "Sort"}, "verdict": "WRONG_ANSWER"},
                ],
            }
        )
        result = c.fetch_user_records("tourist")
        assert result.success
        assert len(result.data) == 2
        assert result.data[0]["verdict"] == "OK"

    def test_url_includes_from_and_count(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": []}
        )
        c.fetch_user_records("user")
        call_arg = c._http_request.call_args[0][0]
        assert "handle=user" in call_arg
        assert "from=1" in call_arg
        assert "count=1000" in call_arg

    def test_since_param_ignored(self) -> None:
        """since is accepted but not used in the request."""
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": []}
        )
        c.fetch_user_records("user", since="2025-01-01")
        call_arg = c._http_request.call_args[0][0]
        assert "since" not in call_arg

    def test_api_error_passthrough(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="timeout", source="http"
        )
        result = c.fetch_user_records("user")
        assert not result.success


# ──────────────────────────────────────────────
# fetch_problem
# ──────────────────────────────────────────────

class TestCodeforcesFetchProblem:
    """Tests for CodeforcesCrawler.fetch_problem."""

    def test_finds_problem_in_problemset(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "status": "OK",
                "result": {
                    "problems": [
                        {"contestId": 1742, "index": "A", "name": "Sum"},
                        {"contestId": 1742, "index": "E", "name": "Binary Search"},
                    ]
                },
            }
        )
        result = c.fetch_problem("1742E")
        assert result.success
        assert result.data["name"] == "Binary Search"
        assert result.data["contestId"] == 1742
        assert result.data["index"] == "E"

    def test_problem_not_found(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "status": "OK",
                "result": {
                    "problems": [
                        {"contestId": 1000, "index": "A", "name": "Test"},
                    ]
                },
            }
        )
        result = c.fetch_problem("9999Z")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    def test_api_error_passthrough(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="Network error", source="http"
        )
        result = c.fetch_problem("1742E")
        assert not result.success

    def test_non_dict_response_is_error(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok([1, 2, 3])
        result = c.fetch_problem("1742E")
        assert not result.success
        assert "Unexpected problemset" in (result.error or "")

    def test_parse_problem_id_simple(self) -> None:
        result = CodeforcesCrawler._parse_problem_id("1742E")
        assert result == (1742, "E")

    def test_parse_problem_id_with_number_suffix(self) -> None:
        result = CodeforcesCrawler._parse_problem_id("1234A1")
        assert result == (1234, "A1")

    def test_parse_problem_id_fallback(self) -> None:
        """Malformed source_id returns (0, source_id)."""
        result = CodeforcesCrawler._parse_problem_id("ABC")
        assert result == (0, "ABC")

    def test_parse_problem_id_empty_string(self) -> None:
        result = CodeforcesCrawler._parse_problem_id("")
        assert result == (0, "")


# ──────────────────────────────────────────────
# fetch_problems_by_tag
# ──────────────────────────────────────────────

class TestCodeforcesFetchProblemsByTag:
    """Tests for CodeforcesCrawler.fetch_problems_by_tag."""

    def test_returns_problems_filtered_by_tag(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "status": "OK",
                "result": {
                    "problems": [
                        {"contestId": 1, "index": "A", "name": "DP 1"},
                        {"contestId": 2, "index": "B", "name": "DP 2"},
                        {"contestId": 3, "index": "C", "name": "DP 3"},
                    ]
                },
            }
        )
        result = c.fetch_problems_by_tag("dp", count=2)
        assert result.success
        assert len(result.data) == 2
        assert result.data[0]["name"] == "DP 1"
        assert result.data[1]["name"] == "DP 2"

    def test_url_includes_tag(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": {"problems": []}}
        )
        c.fetch_problems_by_tag("greedy")
        call_arg = c._http_request.call_args[0][0]
        assert "tags=greedy" in call_arg

    def test_api_error_passthrough(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="rate limit exceeded", source="http"
        )
        result = c.fetch_problems_by_tag("dp")
        assert not result.success

    def test_non_dict_response_is_error(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(["not", "a", "dict"])
        result = c.fetch_problems_by_tag("dp")
        assert not result.success
        assert "Unexpected problemset" in (result.error or "")

    def test_default_count_is_50(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "status": "OK",
                "result": {
                    "problems": [
                        {"contestId": i, "index": "A", "name": f"P{i}"}
                        for i in range(60)
                    ]
                },
            }
        )
        result = c.fetch_problems_by_tag("dp")
        assert len(result.data) == 50  # default count


# ──────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────

class TestCodeforcesEdgeCases:
    """Additional edge case tests for CodeforcesCrawler."""

    def test_fetch_user_profile_multiple_users_returns_first(self) -> None:
        """CF user.info can return multiple users; should return only first."""
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "status": "OK",
                "result": [
                    {"handle": "user1", "rating": 1500},
                    {"handle": "user2", "rating": 2000},
                ],
            }
        )
        result = c.fetch_user_profile("user1;user2")
        assert result.success
        assert isinstance(result.data, dict)
        assert result.data["handle"] == "user1"

    def test_fetch_problem_partial_match_avoided(self) -> None:
        """Ensure 1742E does not match 1742EA or 17422E."""
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "status": "OK",
                "result": {
                    "problems": [
                        {"contestId": 1742, "index": "E2", "name": "Different"},
                        {"contestId": 1742, "index": "E", "name": "Correct"},
                    ]
                },
            }
        )
        result = c.fetch_problem("1742E")
        assert result.success
        assert result.data["name"] == "Correct"

    def test_fetch_problem_empty_problemset(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"status": "OK", "result": {"problems": []}}
        )
        result = c.fetch_problem("1742E")
        assert not result.success
        assert "not found" in (result.error or "").lower()
