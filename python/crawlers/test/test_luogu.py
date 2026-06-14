"""
Tests for crawlers/luogu.py – LuoguCrawler.

All HTTP is mocked via _http_request so no real network calls are made.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import CrawlResult, RateLimiter
from crawlers.luogu import LuoguCrawler


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _mock_crawler() -> LuoguCrawler:
    """Return a LuoguCrawler with _rate_limiter set to no-op jitter=0."""
    crawler = LuoguCrawler.__new__(LuoguCrawler)
    crawler.PLATFORM = "luogu"
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
# URL construction
# ──────────────────────────────────────────────

class TestLuoguUrlConstruction:
    """Verify that each method constructs the correct URL via _http_request."""

    def test_fetch_user_profile_url(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 200, "currentData": {"user": {"uid": 1001, "name": "test"}}}
        )
        result = c.fetch_user_profile("1001")
        call_arg = c._http_request.call_args[0][0]
        assert call_arg == "https://www.luogu.com.cn/user/1001?_contentOnly=1"
        assert result.success
        assert result.data == {"uid": 1001, "name": "test"}

    def test_fetch_problem_url(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 200, "currentData": {"problem": {"pid": "P1001", "title": "A+B"}}}
        )
        result = c.fetch_problem("P1001")
        call_arg = c._http_request.call_args[0][0]
        assert call_arg == "https://www.luogu.com.cn/problem/P1001?_contentOnly=1"
        assert result.success
        assert result.data == {"pid": "P1001", "title": "A+B"}

    def test_fetch_user_records_first_page_url(self) -> None:
        c = _mock_crawler()
        # Return empty records to stop pagination after first page.
        c._http_request.return_value = _crawl_ok(
            {
                "code": 200,
                "currentData": {
                    "records": {"result": [], "count": 0}
                },
            }
        )
        result = c.fetch_user_records("1001")
        call_arg = c._http_request.call_args[0][0]
        assert "https://www.luogu.com.cn/record/list" in call_arg
        assert "_contentOnly=1" in call_arg
        assert "user=1001" in call_arg
        assert "page=1" in call_arg
        assert result.success
        assert result.data == []

    def test_fetch_problems_by_tag_url(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "code": 200,
                "currentData": {
                    "problems": {"result": [], "count": 0}
                },
            }
        )
        result = c.fetch_problems_by_tag("P", count=10)
        call_arg = c._http_request.call_args[0][0]
        assert "https://www.luogu.com.cn/problem/list" in call_arg
        assert "type=P" in call_arg
        assert "page=1" in call_arg
        assert result.success
        assert result.data == []


# ──────────────────────────────────────────────
# fetch_user_profile
# ──────────────────────────────────────────────

class TestLuoguFetchUserProfile:
    """Tests for LuoguCrawler.fetch_user_profile."""

    def test_success_with_user_key(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "code": 200,
                "currentData": {
                    "user": {"uid": 1001, "name": "Alice", "rating": 1500}
                },
            }
        )
        result = c.fetch_user_profile("1001")
        assert result.success
        assert result.data == {"uid": 1001, "name": "Alice", "rating": 1500}

    def test_success_no_user_key_returns_raw(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 200, "currentData": {"someOther": "value"}}
        )
        result = c.fetch_user_profile("1001")
        assert result.success
        assert result.data == {"someOther": "value"}

    def test_http_failure_passthrough(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="Connection refused", source="http"
        )
        result = c.fetch_user_profile("1001")
        assert not result.success
        assert "Connection refused" in (result.error or "")

    def test_api_error_code(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 404, "currentTemplate": "User not found"}
        )
        result = c.fetch_user_profile("nonexistent")
        assert not result.success
        assert "User not found" in (result.error or "")


# ──────────────────────────────────────────────
# fetch_problem
# ──────────────────────────────────────────────

class TestLuoguFetchProblem:
    """Tests for LuoguCrawler.fetch_problem."""

    def test_success_with_problem_key(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "code": 200,
                "currentData": {
                    "problem": {"pid": "P1001", "title": "A+B Problem", "difficulty": 1}
                },
            }
        )
        result = c.fetch_problem("P1001")
        assert result.success
        assert result.data == {"pid": "P1001", "title": "A+B Problem", "difficulty": 1}

    def test_success_no_problem_key_returns_raw(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 200, "currentData": {"rawProblem": "..."}}
        )
        result = c.fetch_problem("P1001")
        assert result.success
        assert result.data == {"rawProblem": "..."}

    def test_http_error_passthrough(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="HTTP 500", source="http"
        )
        result = c.fetch_problem("P9999")
        assert not result.success
        assert "HTTP 500" in (result.error or "")

    def test_non_dict_data_passthrough(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok([1, 2, 3])
        result = c.fetch_problem("P1001")
        # Non-dict data is forwarded as-is
        assert result.success
        assert result.data == [1, 2, 3]


# ──────────────────────────────────────────────
# fetch_user_records
# ──────────────────────────────────────────────

class TestLuoguFetchUserRecords:
    """Tests for LuoguCrawler.fetch_user_records."""

    def test_single_page_records(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "code": 200,
                "currentData": {
                    "records": {
                        "result": [
                            {"id": 1, "problem": "P1001", "verdict": "AC"},
                            {"id": 2, "problem": "P1002", "verdict": "WA"},
                        ],
                        "count": 1,
                    }
                },
            }
        )
        result = c.fetch_user_records("1001")
        assert result.success
        assert len(result.data) == 2
        assert result.data[0]["verdict"] == "AC"
        assert result.data[1]["verdict"] == "WA"

    def test_multi_page_records(self) -> None:
        c = _mock_crawler()
        call_count = [0]

        def side_effect(url: str) -> CrawlResult:
            call_count[0] += 1
            page = call_count[0]
            if page == 1:
                return _crawl_ok(
                    {
                        "code": 200,
                        "currentData": {
                            "records": {
                                "result": [{"id": 1, "verdict": "AC"}],
                                "count": 2,
                            }
                        },
                    }
                )
            elif page == 2:
                return _crawl_ok(
                    {
                        "code": 200,
                        "currentData": {
                            "records": {
                                "result": [{"id": 2, "verdict": "WA"}],
                                "count": 2,
                            }
                        },
                    }
                )
            return _crawl_ok(
                {"code": 200, "currentData": {"records": {"result": [], "count": 2}}}
            )

        c._http_request.side_effect = side_effect
        result = c.fetch_user_records("1001")
        assert result.success
        assert len(result.data) == 2
        assert call_count[0] == 2

    def test_first_page_fails(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="timeout", source="http"
        )
        result = c.fetch_user_records("1001")
        assert not result.success
        assert "timeout" in (result.error or "")

    def test_later_page_failure_non_fatal(self) -> None:
        c = _mock_crawler()
        call_count = [0]

        def side_effect(url: str) -> CrawlResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return _crawl_ok(
                    {
                        "code": 200,
                        "currentData": {
                            "records": {
                                "result": [{"id": 1, "verdict": "AC"}],
                                "count": 5,
                            }
                        },
                    }
                )
            return CrawlResult(success=False, error="timeout on page", source="http")

        c._http_request.side_effect = side_effect
        result = c.fetch_user_records("1001")
        assert result.success
        assert len(result.data) == 1  # only first page data

    def test_empty_records_stops_pagination(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "code": 200,
                "currentData": {
                    "records": {
                        "result": [{"id": 1, "verdict": "AC"}],
                        "count": 1,
                    }
                },
            }
        )
        result = c.fetch_user_records("1001")
        assert result.success
        assert len(result.data) == 1

    def test_dict_data_without_records_key(self) -> None:
        """When currentData has no 'records' key, break out of loop."""
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 200, "currentData": {"unexpected": "structure"}}
        )
        result = c.fetch_user_records("1001")
        assert result.success
        assert result.data == []

    def test_with_since_param_accepted(self) -> None:
        """since param is accepted but not used in URL construction."""
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "code": 200,
                "currentData": {
                    "records": {"result": [{"id": 1, "verdict": "AC"}], "count": 1}
                },
            }
        )
        result = c.fetch_user_records("1001", since="2025-01-01")
        assert result.success
        assert len(result.data) == 1


# ──────────────────────────────────────────────
# fetch_problems_by_tag
# ──────────────────────────────────────────────

class TestLuoguFetchProblemsByTag:
    """Tests for LuoguCrawler.fetch_problems_by_tag."""

    def test_single_page_problems(self) -> None:
        c = _mock_crawler()
        # Use side_effect: first call returns data, second call returns empty
        # to stop pagination (max_pages = count//20 + 2 = 2 for count=10).
        call_count = [0]

        def side_effect(url: str) -> CrawlResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return _crawl_ok(
                    {
                        "code": 200,
                        "currentData": {
                            "problems": {
                                "result": [
                                    {"pid": "P1001", "title": "A+B"},
                                    {"pid": "P1002", "title": "Sum"},
                                ]
                            }
                        },
                    }
                )
            return _crawl_ok(
                {"code": 200, "currentData": {"problems": {"result": []}}}
            )

        c._http_request.side_effect = side_effect
        result = c.fetch_problems_by_tag("P", count=10)
        assert result.success
        assert len(result.data) == 2
        assert result.data[0]["pid"] == "P1001"

    def test_multi_page_problems(self) -> None:
        c = _mock_crawler()
        call_count = [0]

        def side_effect(url: str) -> CrawlResult:
            call_count[0] += 1
            page = call_count[0]
            if page == 1:
                return _crawl_ok(
                    {
                        "code": 200,
                        "currentData": {
                            "problems": {
                                "result": [{"pid": f"P{1000 + i}"} for i in range(20)]
                            }
                        },
                    }
                )
            elif page == 2:
                return _crawl_ok(
                    {
                        "code": 200,
                        "currentData": {
                            "problems": {
                                "result": [{"pid": f"P{2000 + i}"} for i in range(10)]
                            }
                        },
                    }
                )
            return _crawl_ok(
                {"code": 200, "currentData": {"problems": {"result": []}}}
            )

        c._http_request.side_effect = side_effect
        result = c.fetch_problems_by_tag("P", count=30)
        assert result.success
        assert len(result.data) == 30
        assert call_count[0] == 2

    def test_respects_count_limit(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {
                "code": 200,
                "currentData": {
                    "problems": {
                        "result": [{"pid": f"P{i}"} for i in range(50)]
                    }
                },
            }
        )
        result = c.fetch_problems_by_tag("P", count=5)
        assert result.success
        assert len(result.data) == 5

    def test_first_page_fails(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = CrawlResult(
            success=False, error="Server error", source="http"
        )
        result = c.fetch_problems_by_tag("P")
        assert not result.success
        assert "Server error" in (result.error or "")

    def test_later_page_failure_non_fatal(self) -> None:
        c = _mock_crawler()
        call_count = [0]

        def side_effect(url: str) -> CrawlResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return _crawl_ok(
                    {
                        "code": 200,
                        "currentData": {
                            "problems": {
                                "result": [{"pid": "P1001"}]
                            }
                        },
                    }
                )
            return CrawlResult(success=False, error="timeout", source="http")

        c._http_request.side_effect = side_effect
        result = c.fetch_problems_by_tag("P", count=50)
        assert result.success
        assert len(result.data) == 1  # only first page

    def test_non_dict_data_stops_pagination(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok([1, 2, 3])  # list, not dict
        result = c.fetch_problems_by_tag("P")
        assert result.success
        assert result.data == []  # loop breaks on non-dict, returns empty slice


# ──────────────────────────────────────────────
# _get_json envelope handling
# ──────────────────────────────────────────────

class TestLuoguGetJson:
    """Tests for the _get_json helper covering envelope edge cases."""

    def test_code_none_treated_as_success(self) -> None:
        """When 'code' key is missing (None), treat as success."""
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"currentData": {"user": {"uid": 1}}}
        )
        # Call fetch_user_profile which internally calls _get_json.
        result = c.fetch_user_profile("1")
        assert result.success
        assert result.data == {"uid": 1}

    def test_code_non_200_is_error(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 403, "currentTemplate": "Forbidden"}
        )
        result = c.fetch_user_profile("1")
        assert not result.success
        assert "Forbidden" in (result.error or "")

    def test_code_non_200_without_template(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 500}
        )
        result = c.fetch_user_profile("1")
        assert not result.success
        assert "code 500" in (result.error or "")

    def test_no_current_data_returns_whole_envelope(self) -> None:
        c = _mock_crawler()
        c._http_request.return_value = _crawl_ok(
            {"code": 200, "message": "OK but no currentData"}
        )
        result = c.fetch_user_profile("1")
        assert result.success
        assert result.data == {"code": 200, "message": "OK but no currentData"}


# ──────────────────────────────────────────────
# _default_qps
# ──────────────────────────────────────────────

class TestLuoguDefaultQps:
    """Tests for LuoguCrawler._default_qps."""

    def test_default_qps_is_2(self) -> None:
        assert LuoguCrawler._default_qps() == 2.0
