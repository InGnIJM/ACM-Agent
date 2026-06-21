"""
Tests for crawlers/bulk_crawl.py – BulkCrawler state management and phase logic.

All HTTP is mocked so no real network calls are made.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import CrawlResult, RateLimiter
from crawlers.bulk_crawl import (
    _read_state,
    _write_state,
    _init_state,
    _now_iso,
    BulkCrawler,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _crawl_ok(data: object) -> CrawlResult:
    return CrawlResult(success=True, data=data, source="http")


def _crawl_err(msg: str = "test error") -> CrawlResult:
    return CrawlResult(success=False, error=msg, source="http")


def _mock_problem_list_page(page: int, pids: list) -> dict:
    """Simulate a **normalized** problem list page response.

    After the platform-dispatch refactor, ``_fetch_list_page`` returns
    ``{"problems": [...]}`` for every platform.
    """
    return {
        "problems": [
            {
                "pid": pid,
                "title": f"Problem {pid}",
                "difficulty": (page % 7) + 1,
                "tags": [1, 2],
                "totalSubmit": 1000,
                "totalAccepted": 500,
            }
            for pid in pids
        ],
    }


def _mock_problem_detail(pid: str) -> dict:
    """Simulate a Luogu /problem/{pid} JSON response."""
    return {
        "pid": pid,
        "title": f"Problem {pid}",
        "difficulty": 3,
        "tags": [1, 2],
        "background": "This is a background.",
        "description": f"Description for {pid}.",
        "input_format": "Two integers a and b.",
        "output_format": "One integer.",
        "hint": "No hint.",
        "samples": [["1 2", "3"]],
        "limits": {"time": [1000, 2000], "memory": [128, 256]},
        "totalSubmit": 1000,
        "totalAccepted": 500,
    }


def _mock_solutions(pid: str) -> list:
    """Simulate Luogu solutions response."""
    return [
        {
            "author": f"user_{pid}",
            "title": f"Solution for {pid}",
            "content": f"Here is how to solve {pid}...",
            "vote_count": 10,
            "reply_count": 5,
        }
    ]


# ──────────────────────────────────────────────
# State file tests
# ──────────────────────────────────────────────


class TestStateFileIO:
    def test_write_and_read_state(self, tmp_path: Path):
        state_dir = tmp_path / "test_platform"
        state = {"status": "running", "phase": "list", "count": 42}
        _write_state(state_dir, state)

        # Verify file exists
        state_file = state_dir / "_crawl_state.json"
        assert state_file.exists()

        # Verify no tmp file left behind
        assert not (state_dir / "_crawl_state.json.tmp").exists()

        # Read back
        loaded = _read_state(state_dir)
        assert loaded is not None
        assert loaded["status"] == "running"
        assert loaded["count"] == 42

    def test_read_nonexistent_state(self, tmp_path: Path):
        assert _read_state(tmp_path / "nonexistent") is None

    def test_read_corrupt_state(self, tmp_path: Path):
        state_dir = tmp_path / "corrupt"
        state_dir.mkdir(parents=True)
        (state_dir / "_crawl_state.json").write_text("not valid json{{{", encoding="utf-8")
        assert _read_state(state_dir) is None

    def test_init_state_structure(self, tmp_path: Path):
        state = _init_state(
            tmp_path,
            job_id="test-job-123",
            platform="luogu",
            config={"tags": "P", "count": 100},
            phases=["list", "detail", "solutions"],
        )
        assert state["job_id"] == "test-job-123"
        assert state["status"] == "running"
        assert state["phase"] is None
        assert "list" in state["phases"]
        assert "detail" in state["phases"]
        assert "solutions" in state["phases"]
        for p in ["list", "detail", "solutions"]:
            assert state["phases"][p]["status"] == "pending"
            assert state["phases"][p]["fetched"] == 0
            assert state["phases"][p]["errors"] == 0

    def test_atomic_write_no_corruption(self, tmp_path: Path):
        """If crash happens during write, tmp file exists but target may be old/valid."""
        state_dir = tmp_path / "atomic_test"

        # First write
        _write_state(state_dir, {"v": 1})
        assert (state_dir / "_crawl_state.json").exists()

        # Simulate partial write by creating a tmp file
        (state_dir / "_crawl_state.json.tmp").write_text("partial", encoding="utf-8")
        # Target should still have v=1
        loaded = _read_state(state_dir)
        assert loaded == {"v": 1}


# ──────────────────────────────────────────────
# BulkCrawler phase tests
# ──────────────────────────────────────────────


class TestBulkCrawlerListPhase:
    def test_list_phase_single_page(self, tmp_path: Path):
        """Fetch 20 problems in a single page."""
        crawler = self._make_crawler(tmp_path)

        # Mock _fetch_list_page to return 20 problems
        pids = [f"P{i:04d}" for i in range(1, 21)]
        crawler._fetch_list_page = MagicMock(return_value=_crawl_ok(
            _mock_problem_list_page(1, pids)
        ))

        state = _init_state(
            tmp_path / "luogu",
            "test-job",
            "luogu",
            {"tags": "P", "count": 20},
            ["list"],
        )
        _write_state(tmp_path / "luogu", state)

        problems = crawler.run_list_phase(state, "P", 20, set())
        assert len(problems) == 20
        assert problems[0]["pid"] == "P0001"
        assert state["phases"]["list"]["status"] == "completed"

    def test_list_phase_skip_ids(self, tmp_path: Path):
        """Skip already-imported problem IDs."""
        crawler = self._make_crawler(tmp_path)

        pids = [f"P{i:04d}" for i in range(1, 11)]
        # Return 10 on page 1, empty on page 2 (so only 1 page of results)
        crawler._fetch_list_page = MagicMock(side_effect=[
            _crawl_ok(_mock_problem_list_page(1, pids)),
            _crawl_ok(_mock_problem_list_page(2, [])),  # empty page → stops
        ])

        state = _init_state(
            tmp_path / "luogu",
            "test-job",
            "luogu",
            {"tags": "P", "count": 10},
            ["list"],
        )
        _write_state(tmp_path / "luogu", state)

        # Skip P0001 and P0005
        skip = {"P0001", "P0005"}
        problems = crawler.run_list_phase(state, "P", 10, skip)
        assert len(problems) == 8
        returned_pids = {p["pid"] for p in problems}
        assert "P0001" not in returned_pids
        assert "P0005" not in returned_pids

    def test_list_phase_first_page_failure(self, tmp_path: Path):
        """First page failure should set phase as failed."""
        crawler = self._make_crawler(tmp_path)
        crawler._fetch_list_page = MagicMock(return_value=_crawl_err("HTTP 503"))

        state = _init_state(
            tmp_path / "luogu",
            "test-job",
            "luogu",
            {"tags": "P", "count": 20},
            ["list"],
        )
        _write_state(tmp_path / "luogu", state)

        problems = crawler.run_list_phase(state, "P", 20, set())
        assert len(problems) == 0
        assert state["phases"]["list"]["status"] == "failed"
        assert state["status"] == "failed"

    def _make_crawler(self, tmp_path: Path) -> BulkCrawler:
        """Create a BulkCrawler with mocked dependencies."""
        with patch("crawlers.bulk_crawl.LuoguCrawler") as mock_luogu_cls:
            mock_crawler = MagicMock()
            mock_crawler._get_json = MagicMock()
            mock_crawler.save_json = MagicMock()
            mock_crawler.close = MagicMock()

            # Also mock the executor
            mock_executor = MagicMock()

            mock_luogu_cls.return_value = mock_crawler

            crawler = BulkCrawler.__new__(BulkCrawler)
            crawler.platform = "luogu"
            crawler.data_dir = tmp_path
            crawler.state_dir = tmp_path / "luogu"
            crawler.state_dir.mkdir(parents=True, exist_ok=True)
            crawler.crawler = mock_crawler
            crawler.executor = mock_executor
            crawler._shutdown_requested = False

            return crawler


class TestBulkCrawlerDetailPhase:
    def test_detail_phase_enriches_problems(self, tmp_path: Path):
        """Each problem gets full detail fetched and merged."""
        crawler = BulkCrawler.__new__(BulkCrawler)
        crawler.platform = "luogu"
        crawler.data_dir = tmp_path
        crawler.state_dir = tmp_path / "luogu"
        crawler.state_dir.mkdir(parents=True, exist_ok=True)

        mock_crawler = MagicMock()
        mock_crawler.save_json = MagicMock()
        crawler.crawler = mock_crawler

        mock_executor = MagicMock()
        mock_executor.execute.return_value = _crawl_ok(_mock_problem_detail("P0001"))
        crawler.executor = mock_executor
        crawler._shutdown_requested = False

        state = _init_state(
            tmp_path / "luogu",
            "test-job",
            "luogu",
            {"tags": "P", "count": 5},
            ["detail"],
        )
        _write_state(tmp_path / "luogu", state)

        problems = [
            {"pid": "P0001", "title": "Old Title", "difficulty": 1},
            {"pid": "P0002", "title": "Old Title 2", "difficulty": 2},
        ]

        enriched = crawler.run_detail_phase(state, problems, skip_existing=True)
        assert len(enriched) == 2
        assert enriched[0]["description"] == "Description for P0001."
        assert enriched[0]["background"] == "This is a background."
        assert state["phases"]["detail"]["status"] == "completed"
        assert state["phases"]["detail"]["fetched"] == 2

    def test_detail_phase_handles_errors(self, tmp_path: Path):
        """Failed detail fetches keep original problem data."""
        crawler = BulkCrawler.__new__(BulkCrawler)
        crawler.platform = "luogu"
        crawler.data_dir = tmp_path
        crawler.state_dir = tmp_path / "luogu"
        crawler.state_dir.mkdir(parents=True, exist_ok=True)

        mock_crawler = MagicMock()
        mock_crawler.save_json = MagicMock()
        crawler.crawler = mock_crawler

        mock_executor = MagicMock()
        # First succeeds, second fails
        # P0001: success on first try; P0002: fails 3 times (retry exhausted)
        mock_executor.execute.side_effect = [
            _crawl_ok(_mock_problem_detail("P0001")),
            _crawl_err("timeout"),
            _crawl_err("timeout"),
            _crawl_err("timeout"),
        ]
        crawler.executor = mock_executor
        crawler._shutdown_requested = False

        state = _init_state(
            tmp_path / "luogu",
            "test-job",
            "luogu",
            {"tags": "P", "count": 2},
            ["detail"],
        )
        _write_state(tmp_path / "luogu", state)

        problems = [
            {"pid": "P0001", "title": "T1"},
            {"pid": "P0002", "title": "T2"},
        ]

        enriched = crawler.run_detail_phase(state, problems, skip_existing=True)
        assert len(enriched) == 2
        assert enriched[0].get("description") == "Description for P0001."  # enriched
        assert enriched[1].get("title") == "T2"  # kept original
        assert state["phases"]["detail"]["errors"] == 1


class TestOrchestration:
    def test_run_all_phases_minimal(self, tmp_path: Path):
        """End-to-end run with minimal count and mocked HTTP."""
        with patch("crawlers.bulk_crawl.LuoguCrawler") as mock_luogu_cls:
            mock_crawler = MagicMock()
            mock_crawler.save_json = MagicMock()
            mock_crawler.close = MagicMock()
            mock_luogu_cls.return_value = mock_crawler

            crawler = BulkCrawler.__new__(BulkCrawler)
            crawler.platform = "luogu"
            crawler.data_dir = tmp_path
            crawler.state_dir = tmp_path / "luogu"
            crawler.state_dir.mkdir(parents=True, exist_ok=True)
            crawler.crawler = mock_crawler
            crawler._shutdown_requested = False

            # Mock all three phase methods
            crawler.run_list_phase = MagicMock(return_value=[
                {"pid": "P0001", "title": "Test"},
            ])
            crawler.run_detail_phase = MagicMock(return_value=[
                {"pid": "P0001", "title": "Test", "description": "Desc"},
            ])
            crawler.run_solutions_phase = MagicMock()

            state = crawler.run(
                job_id="test-123",
                tag="P",
                count=1,
                phases=["list", "detail", "solutions"],
            )

            assert state["status"] == "completed"
            crawler.run_list_phase.assert_called_once()
            crawler.run_detail_phase.assert_called_once()
            crawler.run_solutions_phase.assert_called_once()

    def test_run_detail_only_loads_from_disk(self, tmp_path: Path):
        """When list phase is skipped, load problems from saved file."""
        with patch("crawlers.bulk_crawl.LuoguCrawler") as mock_luogu_cls:
            mock_crawler = MagicMock()
            mock_crawler.save_json = MagicMock()
            mock_crawler.close = MagicMock()
            mock_luogu_cls.return_value = mock_crawler

            # Save problems to disk so _load_list_from_disk can find them
            problems_dir = tmp_path / "luogu" / "problems"
            problems_dir.mkdir(parents=True)
            saved_problems = [
                {"pid": "P0001", "title": "Saved Problem"},
                {"pid": "P0002", "title": "Saved Problem 2"},
            ]
            (problems_dir / "bulk_list_P_2026-06-14.json").write_text(
                json.dumps(saved_problems), encoding="utf-8"
            )

            crawler = BulkCrawler.__new__(BulkCrawler)
            crawler.platform = "luogu"
            crawler.data_dir = tmp_path
            crawler.state_dir = tmp_path / "luogu"
            crawler.state_dir.mkdir(parents=True, exist_ok=True)
            crawler.crawler = mock_crawler
            crawler._shutdown_requested = False

            # Mock detail phase
            crawler.run_detail_phase = MagicMock(return_value=saved_problems)

            state = crawler.run(
                job_id="test-456",
                tag="P",
                count=2,
                phases=["detail"],  # skip list
            )

            assert state["status"] == "completed"
            crawler.run_detail_phase.assert_called_once()
            # List phase should NOT be called
            assert state["phases"]["list"]["total"] == 2


# ──────────────────────────────────────────────
# Signal handling
# ──────────────────────────────────────────────


class TestShutdownHandling:
    def test_shutdown_during_list_phase(self, tmp_path: Path):
        """When shutdown is requested, list phase returns partial results."""
        crawler = BulkCrawler.__new__(BulkCrawler)
        crawler.platform = "luogu"
        crawler.data_dir = tmp_path
        crawler.state_dir = tmp_path / "luogu"
        crawler.state_dir.mkdir(parents=True, exist_ok=True)

        mock_crawler = MagicMock()
        mock_crawler.save_json = MagicMock()
        crawler.crawler = mock_crawler
        crawler._shutdown_requested = False

        pids = [f"P{i:04d}" for i in range(1, 21)]
        page_data = _mock_problem_list_page(1, pids)

        call_count = [0]

        def fetch_side_effect(tag, page):
            call_count[0] += 1
            if call_count[0] >= 2:
                crawler._shutdown_requested = True  # simulate signal
            return _crawl_ok(page_data)

        crawler._fetch_list_page = MagicMock(side_effect=fetch_side_effect)

        state = _init_state(
            tmp_path / "luogu",
            "test-job",
            "luogu",
            {"tags": "P", "count": 100},
            ["list"],
        )
        _write_state(tmp_path / "luogu", state)

        problems = crawler.run_list_phase(state, "P", 100, set())
        # Should have fetched at least 1 page before shutdown
        assert len(problems) >= 20
        assert state["status"] == "cancelled"


class TestFetchListPagePlatformDispatch:
    """Tests for _fetch_list_page platform-dispatch and per-platform methods."""

    # ── helpers ────────────────────────────────────────────────

    @staticmethod
    def _make_crawler(
        tmp_path: Path, platform: str = "leetcode"
    ) -> BulkCrawler:
        crawler = BulkCrawler.__new__(BulkCrawler)
        crawler.platform = platform
        crawler.data_dir = tmp_path
        crawler.state_dir = tmp_path / platform
        crawler.state_dir.mkdir(parents=True, exist_ok=True)

        mock = MagicMock()
        mock._graphql = MagicMock()
        mock._get_json = MagicMock()
        mock._api = MagicMock()
        mock.fetch_problems_by_tag = MagicMock()
        mock.save_json = MagicMock()
        mock.close = MagicMock()
        crawler.crawler = mock
        return crawler

    # ── dispatch ───────────────────────────────────────────────

    def test_dispatch_calls_leetcode_for_leetcode(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "leetcode")
        crawler.crawler._graphql.return_value = _crawl_ok({
            "problemsetQuestionList": {
                "questions": [
                    {"titleSlug": "two-sum", "title": "Two Sum", "difficulty": "Easy"},
                ],
            },
        })
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        assert result.data is not None
        problems = result.data["problems"]
        assert len(problems) == 1
        assert problems[0]["pid"] == "two-sum"

    def test_dispatch_calls_luogu_for_luogu(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "luogu")
        crawler.crawler._get_json.return_value = _crawl_ok({
            "problems": {
                "result": [{"pid": "P1000", "title": "Test"}],
            },
        })
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        assert result.data is not None
        problems = result.data["problems"]
        assert len(problems) == 1
        assert problems[0]["pid"] == "P1000"

    def test_dispatch_calls_codeforces_for_codeforces(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "codeforces")
        crawler.crawler._api.return_value = _crawl_ok({
            "problems": [
                {"contestId": 1742, "index": "E", "name": "FTL"},
            ],
        })
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        assert result.data is not None
        problems = result.data["problems"]
        assert len(problems) == 1
        assert problems[0]["pid"] == "1742E"

    def test_dispatch_calls_nowcoder_for_nowcoder(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "nowcoder")
        crawler.crawler.fetch_problems_by_tag.return_value = _crawl_ok([
            {"problemId": "NC1", "title": "Test"},
        ])
        result = crawler._fetch_list_page("dp", 1)
        assert result.success
        assert result.data is not None
        problems = result.data["problems"]
        assert len(problems) == 1
        assert problems[0]["pid"] == "NC1"

    def test_unsupported_platform_returns_error(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "leetcode")
        crawler.platform = "unsupported"
        result = crawler._fetch_list_page(None, 1)
        assert not result.success
        assert "not implemented" in (result.error or "").lower()

    # ── LeetCode ────────────────────────────────────────────────

    def test_leetcode_fetch_with_tag(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "leetcode")
        crawler.crawler._graphql.return_value = _crawl_ok({
            "problemsetQuestionList": {
                "questions": [
                    {"titleSlug": "jump-game", "title": "Jump Game",
                     "difficulty": "Medium"},
                ],
            },
        })
        result = crawler._fetch_list_page("dynamic-programming", 2)
        assert result.success
        # Verify skip offset reflects page 2 → 20
        call_kwargs = crawler.crawler._graphql.call_args[1]
        assert call_kwargs["variables"]["skip"] == 20
        assert call_kwargs["variables"]["limit"] == 20
        assert call_kwargs["variables"]["filters"] == {"tags": ["dynamic-programming"]}

    def test_leetcode_fetch_without_tag(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "leetcode")
        crawler.crawler._graphql.return_value = _crawl_ok({
            "problemsetQuestionList": {"questions": []},
        })
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        call_kwargs = crawler.crawler._graphql.call_args[1]
        assert call_kwargs["variables"]["filters"] == {}

    def test_leetcode_fetch_graphql_error(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "leetcode")
        crawler.crawler._graphql.return_value = _crawl_err("HTTP 429")
        result = crawler._fetch_list_page(None, 1)
        assert not result.success
        assert "HTTP 429" in (result.error or "")

    def test_leetcode_fetch_non_dict_response(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "leetcode")
        crawler.crawler._graphql.return_value = _crawl_ok(["not a dict"])
        result = crawler._fetch_list_page(None, 1)
        assert not result.success

    def test_leetcode_normalizes_pid_from_title_slug(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "leetcode")
        crawler.crawler._graphql.return_value = _crawl_ok({
            "problemsetQuestionList": {
                "questions": [
                    {"titleSlug": "two-sum", "title": "Two Sum",
                     "frontendQuestionId": "1", "difficulty": "Easy",
                     "acRate": 52.3, "paidOnly": False,
                     "topicTags": [{"name": "Array"}],
                     "status": None},
                    {"titleSlug": "", "title": "No Slug"},
                ],
            },
        })
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        assert result.data is not None
        problems = result.data["problems"]
        assert len(problems) == 2
        # first problem: titleSlug → pid
        assert problems[0]["pid"] == "two-sum"
        assert problems[0]["titleSlug"] == "two-sum"
        assert problems[0]["frontendQuestionId"] == "1"
        assert problems[0]["difficulty"] == "Easy"
        assert problems[0]["acRate"] == 52.3
        assert problems[0]["paidOnly"] is False
        assert problems[0]["topicTags"] == [{"name": "Array"}]
        assert problems[0]["status"] is None
        # second problem: empty slug → empty pid
        assert problems[1]["pid"] == ""

    # ── Codeforces ───────────────────────────────────────────────

    def test_codeforces_page_1_fetches_all(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "codeforces")
        crawler.crawler._api.return_value = _crawl_ok({
            "problems": [
                {"contestId": 1, "index": "A", "name": "A+B"},
                {"contestId": 2, "index": "B", "name": "C*D"},
            ],
        })
        result = crawler._fetch_list_page("math", 1)
        assert result.success
        assert result.data is not None
        problems = result.data["problems"]
        assert len(problems) == 2
        assert problems[0]["pid"] == "1A"
        assert problems[1]["pid"] == "2B"
        # Verify tag was passed
        crawler.crawler._api.assert_called_once_with(
            "problemset.problems", tags="math",
        )

    def test_codeforces_page_greater_than_1_returns_empty(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "codeforces")
        # _api should NOT be called for page > 1
        result = crawler._fetch_list_page(None, 2)
        assert result.success
        assert result.data is not None
        assert result.data["problems"] == []
        crawler.crawler._api.assert_not_called()

    def test_codeforces_no_tag(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "codeforces")
        crawler.crawler._api.return_value = _crawl_ok({"problems": []})
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        # No tag → no tags kwarg
        crawler.crawler._api.assert_called_once_with("problemset.problems")

    def test_codeforces_api_error(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "codeforces")
        crawler.crawler._api.return_value = _crawl_err("server error")
        result = crawler._fetch_list_page("dp", 1)
        assert not result.success

    def test_codeforces_non_dict_response(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "codeforces")
        crawler.crawler._api.return_value = _crawl_ok([1, 2, 3])
        result = crawler._fetch_list_page(None, 1)
        assert not result.success

    def test_codeforces_empty_pid_for_missing_fields(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "codeforces")
        crawler.crawler._api.return_value = _crawl_ok({
            "problems": [
                {"contestId": 0, "index": "", "name": "bad"},
            ],
        })
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        assert result.data is not None
        assert result.data["problems"][0]["pid"] == ""

    # ── NowCoder ─────────────────────────────────────────────────

    def test_nowcoder_with_tag_and_page(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "nowcoder")
        crawler.crawler.fetch_problems_by_tag.return_value = _crawl_ok([
            {"problemId": "NC100", "title": "DP入门"},
        ])
        result = crawler._fetch_list_page("dp", 3)
        assert result.success
        assert result.data is not None
        problems = result.data["problems"]
        assert len(problems) == 1
        assert problems[0]["pid"] == "NC100"
        crawler.crawler.fetch_problems_by_tag.assert_called_once_with(
            "dp", count=50, page=3,
        )

    def test_nowcoder_empty_tag(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "nowcoder")
        crawler.crawler.fetch_problems_by_tag.return_value = _crawl_ok([])
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        crawler.crawler.fetch_problems_by_tag.assert_called_once_with(
            "", count=50, page=1,
        )

    def test_nowcoder_error_propagates(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "nowcoder")
        crawler.crawler.fetch_problems_by_tag.return_value = _crawl_err("timeout")
        result = crawler._fetch_list_page("dp", 1)
        assert not result.success
        assert "timeout" in (result.error or "")

    def test_nowcoder_non_list_data(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "nowcoder")
        crawler.crawler.fetch_problems_by_tag.return_value = _crawl_ok(
            {"not": "a list"},
        )
        result = crawler._fetch_list_page("dp", 1)
        assert result.success
        assert result.data is not None
        assert result.data["problems"] == []

    def test_nowcoder_fallback_pid_from_id(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "nowcoder")
        crawler.crawler.fetch_problems_by_tag.return_value = _crawl_ok([
            {"id": 42, "title": "无ID问题"},
        ])
        result = crawler._fetch_list_page("dp", 1)
        assert result.success
        assert result.data is not None
        assert result.data["problems"][0]["pid"] == "42"

    # ── Luogu ────────────────────────────────────────────────────

    def test_luogu_with_tag(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "luogu")
        crawler.crawler._get_json.return_value = _crawl_ok({
            "problems": {"result": [{"pid": "B2000", "title": "B"}]},
        })
        result = crawler._fetch_list_page("B", 3)
        assert result.success
        assert result.data is not None
        assert result.data["problems"][0]["pid"] == "B2000"
        crawler.crawler._get_json.assert_called_once_with(
            "/problem/list", page="3", type="B",
        )

    def test_luogu_no_tag(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "luogu")
        crawler.crawler._get_json.return_value = _crawl_ok({
            "problems": {"result": [{"pid": "P1001"}]},
        })
        result = crawler._fetch_list_page(None, 1)
        assert result.success
        # No type param when tag is None
        crawler.crawler._get_json.assert_called_once_with(
            "/problem/list", page="1",
        )

    def test_luogu_error_propagates(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "luogu")
        crawler.crawler._get_json.return_value = _crawl_err("not found")
        result = crawler._fetch_list_page("P", 1)
        assert not result.success

    def test_luogu_non_dict_response(self, tmp_path: Path):
        crawler = self._make_crawler(tmp_path, "luogu")
        crawler.crawler._get_json.return_value = _crawl_ok([1, 2])
        result = crawler._fetch_list_page("P", 1)
        assert not result.success


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────


class TestCLI:
    def test_cli_json_input(self, tmp_path: Path):
        """CLI accepts --input JSON and runs bulk crawl."""
        from crawlers.bulk_crawl import main

        with patch("crawlers.bulk_crawl.BulkCrawler") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {
                "status": "completed",
                "job_id": "test-cli",
                "summary": {"total_problems": 5, "total_errors": 0},
            }
            mock_cls.return_value = mock_instance

            # Capture stdout
            import io
            old_stdout = sys.stdout
            sys.stdout = captured = io.StringIO()

            try:
                main(["--input", json.dumps({
                    "platform": "luogu",
                    "tags": "P",
                    "count": 5,
                    "job_id": "test-cli",
                })])
            finally:
                sys.stdout = old_stdout

            output = json.loads(captured.getvalue())
            assert output["success"] is True
            assert output["platform"] == "luogu"

    def test_cli_invalid_json(self):
        """Invalid JSON input produces error output."""
        from crawlers.bulk_crawl import main

        import io
        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()

        # Invalid JSON should trigger sys.exit(1)
        with pytest.raises(SystemExit) as exc_info:
            main(["--input", "not valid json{{{{"])
        assert exc_info.value.code == 1

        sys.stdout = old_stdout
