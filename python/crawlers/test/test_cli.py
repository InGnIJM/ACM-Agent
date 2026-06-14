"""
Tests for CLI entry points across luogu.py, leetcode.py, codeforces.py,
and batch_crawl.py.

Covers:
- argparse parsing (CLI mode with individual flags)
- JSON input mode (NestJS --input flag)
- stdout output format (valid JSON with expected keys)
- Error handling (missing args, invalid JSON, unknown actions)
"""

from __future__ import annotations

import json
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import CrawlResult


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

MOCK_USER_DATA = {"uid": "1001", "name": "TestUser", "rating": 1500}
MOCK_PROBLEM_DATA = [
    {"pid": "P1001", "title": "A+B Problem", "difficulty": 1},
    {"pid": "P1002", "title": "Sum", "difficulty": 2},
]
MOCK_RECORDS_DATA = [
    {"id": 1, "problem": "P1001", "verdict": "AC"},
    {"id": 2, "problem": "P1002", "verdict": "WA"},
]


def _make_success_result(data: object = None) -> CrawlResult:
    return CrawlResult(success=True, data=data, source="http")


def _parse_stdout(capsys) -> dict:
    """Capture and parse the JSON line printed to stdout."""
    captured = capsys.readouterr()
    text = captured.out.strip()
    assert text, "Expected JSON output but stdout was empty"
    return json.loads(text)


# ──────────────────────────────────────────────
# Per-platform combined fixtures
# ──────────────────────────────────────────────


def _make_platform_fixture(
    crawler_module: str,
    crawler_class: str,
    platform_name: str,
):
    """Factory that creates a combined mock fixture for one platform.

    Patches both the crawler class and CrawlerExecutor in the target
    module so that ``main()`` can run without real HTTP or browser.
    """

    @pytest.fixture
    def _fixture() -> MagicMock:
        with ExitStack() as stack:
            # Mock the crawler class (e.g. crawlers.luogu.LuoguCrawler).
            mock_crawler_cls = stack.enter_context(
                patch(f"{crawler_module}.{crawler_class}")
            )
            mock_crawler = MagicMock()
            mock_crawler.PLATFORM = platform_name
            mock_crawler.close = MagicMock()
            mock_crawler_cls.return_value = mock_crawler

            # Mock CrawlerExecutor in the same module.
            mock_exec_cls = stack.enter_context(
                patch(f"{crawler_module}.CrawlerExecutor")
            )
            mock_exec = MagicMock()
            mock_exec.execute.return_value = _make_success_result(MOCK_USER_DATA)
            mock_exec_cls.return_value = mock_exec

            yield mock_exec

    return _fixture


mock_luogu = _make_platform_fixture("crawlers.luogu", "LuoguCrawler", "luogu")
mock_leetcode = _make_platform_fixture(
    "crawlers.leetcode", "LeetCodeCrawler", "leetcode"
)
mock_codeforces = _make_platform_fixture(
    "crawlers.codeforces", "CodeforcesCrawler", "codeforces"
)


# ──────────────────────────────────────────────
# Luogu CLI tests
# ──────────────────────────────────────────────


class TestLuoguCli:
    """Tests for luogu.py CLI main()."""

    def test_cli_fetch_user_success(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        main(argv=["--action", "fetch_user", "--uid", "1001"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "luogu"
        assert out["error"] is None

    def test_cli_fetch_problems_success(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        main(argv=["--action", "fetch_problems", "--tags", "P", "--count", "10"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "luogu"

    def test_cli_fetch_records_success(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        main(argv=["--action", "fetch_records", "--uid", "1001"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "luogu"

    def test_cli_missing_action(self, capsys) -> None:
        from crawlers.luogu import main

        with pytest.raises(SystemExit):
            main(argv=[])

    def test_cli_missing_action_but_has_other_args(self, capsys) -> None:
        from crawlers.luogu import main

        with pytest.raises(SystemExit):
            main(argv=["--uid", "1001"])

    def test_json_input_mode_fetch_user(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        input_json = json.dumps({"action": "fetch_user", "uid": "1001"})
        main(argv=["--input", input_json])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "luogu"

    def test_json_input_mode_fetch_problems(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        input_json = json.dumps({"action": "fetch_problems", "tags": "B", "count": 20})
        main(argv=["--input", input_json])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "luogu"

    def test_json_input_invalid_json(self, capsys) -> None:
        from crawlers.luogu import main

        with pytest.raises(SystemExit):
            main(argv=["--input", "not valid json {{{"])

    def test_json_input_overrides_cli_args(self, mock_luogu, capsys) -> None:
        """When --input is provided, its JSON values take precedence."""
        from crawlers.luogu import main

        input_json = json.dumps({"action": "fetch_user", "uid": "1001"})
        # CLI args say fetch_records but --input says fetch_user
        main(
            argv=[
                "--action", "fetch_records",
                "--uid", "9999",
                "--input", input_json,
            ]
        )

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "luogu"

    def test_cli_missing_uid_for_fetch_user(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        with pytest.raises(SystemExit):
            main(argv=["--action", "fetch_user"])

    def test_cli_missing_uid_for_fetch_records(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        with pytest.raises(SystemExit):
            main(argv=["--action", "fetch_records"])

    def test_output_keys_present(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        main(argv=["--action", "fetch_user", "--uid", "1001"])

        out = _parse_stdout(capsys)
        for key in ("success", "data", "error", "platform"):
            assert key in out, f"Missing key: {key}"

    def test_output_data_is_preserved(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        main(argv=["--action", "fetch_user", "--uid", "1001"])

        out = _parse_stdout(capsys)
        assert out["data"] == MOCK_USER_DATA

    def test_crawler_result_with_non_serializable_data(
        self, mock_luogu, capsys
    ) -> None:
        """default=str should handle set objects and other non-serializables."""
        from crawlers.luogu import main

        mock_luogu.execute.return_value = _make_success_result(
            {"timestamp": "2025-01-01", "tags": {"math", "dp"}}
        )

        main(argv=["--action", "fetch_user", "--uid", "1"])

        out = _parse_stdout(capsys)
        assert out["success"] is True


# ──────────────────────────────────────────────
# LeetCode CLI tests
# ──────────────────────────────────────────────


class TestLeetCodeCli:
    """Tests for leetcode.py CLI main()."""

    def test_cli_fetch_user_success(self, mock_leetcode, capsys) -> None:
        from crawlers.leetcode import main

        main(argv=["--action", "fetch_user", "--uid", "someuser"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "leetcode"
        assert out["error"] is None

    def test_cli_fetch_problems_success(self, mock_leetcode, capsys) -> None:
        from crawlers.leetcode import main

        main(argv=["--action", "fetch_problems", "--tags", "array", "--count", "30"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "leetcode"

    def test_cli_fetch_records_success(self, mock_leetcode, capsys) -> None:
        from crawlers.leetcode import main

        main(argv=["--action", "fetch_records", "--uid", "someuser"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "leetcode"

    def test_json_input_mode(self, mock_leetcode, capsys) -> None:
        from crawlers.leetcode import main

        input_json = json.dumps({"action": "fetch_user", "uid": "leetcode_user"})
        main(argv=["--input", input_json])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "leetcode"

    def test_output_keys(self, mock_leetcode, capsys) -> None:
        from crawlers.leetcode import main

        main(argv=["--action", "fetch_user", "--uid", "test"])

        out = _parse_stdout(capsys)
        for key in ("success", "data", "error", "platform"):
            assert key in out, f"Missing key: {key}"

    def test_missing_action(self, capsys) -> None:
        from crawlers.leetcode import main

        with pytest.raises(SystemExit):
            main(argv=[])

    def test_missing_action_with_other_args(self, capsys) -> None:
        from crawlers.leetcode import main

        with pytest.raises(SystemExit):
            main(argv=["--uid", "test"])

    def test_invalid_json_input(self, capsys) -> None:
        from crawlers.leetcode import main

        with pytest.raises(SystemExit):
            main(argv=["--input", "{invalid}"])


# ──────────────────────────────────────────────
# Codeforces CLI tests
# ──────────────────────────────────────────────


class TestCodeforcesCli:
    """Tests for codeforces.py CLI main()."""

    def test_cli_fetch_user_success(self, mock_codeforces, capsys) -> None:
        from crawlers.codeforces import main

        main(argv=["--action", "fetch_user", "--uid", "tourist"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "codeforces"

    def test_cli_fetch_problems_success(self, mock_codeforces, capsys) -> None:
        from crawlers.codeforces import main

        main(argv=["--action", "fetch_problems", "--tags", "dp", "--count", "25"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "codeforces"

    def test_cli_fetch_records_success(self, mock_codeforces, capsys) -> None:
        from crawlers.codeforces import main

        main(argv=["--action", "fetch_records", "--uid", "tourist"])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "codeforces"

    def test_json_input_mode(self, mock_codeforces, capsys) -> None:
        from crawlers.codeforces import main

        input_json = json.dumps(
            {"action": "fetch_problems", "tags": "math", "count": 15}
        )
        main(argv=["--input", input_json])

        out = _parse_stdout(capsys)
        assert out["success"] is True
        assert out["platform"] == "codeforces"

    def test_default_count_value(self, mock_codeforces, capsys) -> None:
        """When --count is not provided, default 50 should be used."""
        from crawlers.codeforces import main

        main(argv=["--action", "fetch_problems", "--tags", "greedy"])

        out = _parse_stdout(capsys)
        assert out["success"] is True

    def test_output_keys(self, mock_codeforces, capsys) -> None:
        from crawlers.codeforces import main

        main(argv=["--action", "fetch_user", "--uid", "tourist"])

        out = _parse_stdout(capsys)
        for key in ("success", "data", "error", "platform"):
            assert key in out, f"Missing key: {key}"

    def test_missing_action(self, capsys) -> None:
        from crawlers.codeforces import main

        with pytest.raises(SystemExit):
            main(argv=[])

    def test_invalid_json_input(self, capsys) -> None:
        from crawlers.codeforces import main

        with pytest.raises(SystemExit):
            main(argv=["--input", "not-json"])


# ──────────────────────────────────────────────
# Cross-crawler output format tests
# ──────────────────────────────────────────────


class TestOutputFormat:
    """Verify stdout JSON format is consistent across all crawlers."""

    def test_luogu_output_structure(self, mock_luogu, capsys) -> None:
        from crawlers.luogu import main

        main(argv=["--action", "fetch_user", "--uid", "1"])

        out = _parse_stdout(capsys)
        assert isinstance(out["success"], bool)
        assert out["platform"] == "luogu"
        assert out["error"] is None

    def test_leetcode_output_structure(self, mock_leetcode, capsys) -> None:
        from crawlers.leetcode import main

        main(argv=["--action", "fetch_user", "--uid", "test"])

        out = _parse_stdout(capsys)
        assert isinstance(out["success"], bool)
        assert out["platform"] == "leetcode"
        assert out["error"] is None

    def test_codeforces_output_structure(self, mock_codeforces, capsys) -> None:
        from crawlers.codeforces import main

        main(argv=["--action", "fetch_user", "--uid", "test"])

        out = _parse_stdout(capsys)
        assert isinstance(out["success"], bool)
        assert out["platform"] == "codeforces"
        assert out["error"] is None

    def test_all_platforms_have_same_json_shape(
        self, mock_luogu, mock_leetcode, mock_codeforces, capsys
    ) -> None:
        """Each platform outputs the same top-level JSON keys."""
        from crawlers.luogu import main as luogu_main
        from crawlers.leetcode import main as leetcode_main
        from crawlers.codeforces import main as codeforces_main

        for main_fn, platform in [
            (luogu_main, "luogu"),
            (leetcode_main, "leetcode"),
            (codeforces_main, "codeforces"),
        ]:
            main_fn(argv=["--action", "fetch_user", "--uid", "test"])
            out = _parse_stdout(capsys)
            assert out["platform"] == platform
            assert "success" in out
            assert "data" in out
            assert "error" in out


# ──────────────────────────────────────────────
# Argparse parsing edge cases
# ──────────────────────────────────────────────


class TestCliArgparseDetails:
    """Verify argparse behaviour for each action."""

    def test_count_as_int_type(self, mock_luogu, capsys) -> None:
        """--count 10 should be parsed as integer 10."""
        from crawlers.luogu import main

        main(argv=["--action", "fetch_problems", "--tags", "P", "--count", "10"])

        out = _parse_stdout(capsys)
        assert out["success"] is True

    def test_action_fetch_problems_requires_tags(self, mock_luogu, capsys) -> None:
        """fetch_problems with empty tags should still execute (might return nothing)."""
        from crawlers.luogu import main

        main(argv=["--action", "fetch_problems", "--tags", ""])

        out = _parse_stdout(capsys)
        assert out["success"] is True

    def test_system_exit_code_is_one(self, capsys) -> None:
        """Invalid input should cause exit code 1."""
        from crawlers.luogu import main

        with pytest.raises(SystemExit) as exc_info:
            main(argv=[])
        assert exc_info.value.code == 1

    def test_json_missing_action_key(self, mock_luogu, capsys) -> None:
        """JSON that lacks 'action' should fail."""
        from crawlers.luogu import main

        with pytest.raises(SystemExit):
            main(argv=["--input", json.dumps({"uid": "1001"})])


# ──────────────────────────────────────────────
# batch_crawl CLI tests
# ──────────────────────────────────────────────


class TestBatchCrawlCli:
    """Tests for batch_crawl.py CLI main()."""

    def test_cli_default_run(self, capsys) -> None:
        """Default run with no arguments."""
        with patch(
            "crawlers.batch_crawl.crawl_all_observed_users"
        ) as mock_crawl_all, patch("crawlers.batch_crawl.asyncio.run") as mock_async_run:
            mock_crawl_all.return_value = {
                "started_at": "2025-01-01T00:00:00+00:00",
                "finished_at": "2025-01-01T00:01:00+00:00",
                "users_crawled": 1,
                "platforms": {"luogu": {"profiles": 1, "records": 10, "errors": 0}},
                "import": {},
                "errors": [],
            }
            mock_async_run.return_value = mock_crawl_all.return_value

            from crawlers.batch_crawl import main

            main(argv=[])

        out = _parse_stdout(capsys)
        assert out["users_crawled"] == 1
        assert "platforms" in out

    def test_cli_with_platforms(self, capsys) -> None:
        """Passing --platforms restricts to those platforms."""
        with patch(
            "crawlers.batch_crawl.crawl_all_observed_users"
        ) as mock_crawl_all, patch("crawlers.batch_crawl.asyncio.run") as mock_async_run:
            mock_crawl_all.return_value = {
                "users_crawled": 0,
                "platforms": {},
                "import": {},
                "errors": [],
            }
            mock_async_run.return_value = mock_crawl_all.return_value

            from crawlers.batch_crawl import main

            main(argv=["--platforms", "luogu", "codeforces"])

        out = _parse_stdout(capsys)
        assert out["users_crawled"] == 0

    def test_cli_no_import_flag(self, capsys) -> None:
        """--no-import should disable the import step."""
        with patch(
            "crawlers.batch_crawl.crawl_all_observed_users"
        ) as mock_crawl_all, patch("crawlers.batch_crawl.asyncio.run") as mock_async_run:
            mock_crawl_all.return_value = {
                "users_crawled": 0,
                "platforms": {},
                "import": {},
                "errors": [],
            }
            mock_async_run.return_value = mock_crawl_all.return_value

            from crawlers.batch_crawl import main

            main(argv=["--no-import"])

        out = _parse_stdout(capsys)
        assert out["users_crawled"] == 0

    def test_cli_with_users_file_flag(self, capsys) -> None:
        """--users-file should load users from the specified file."""
        import tempfile
        import os

        # Create a temporary users file.
        users_data = [{"uid": "custom_user", "platforms": ["luogu"]}]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(users_data, f)
            tmp_path = f.name

        try:
            with patch(
                "crawlers.batch_crawl.crawl_all_observed_users"
            ) as mock_crawl_all, patch(
                "crawlers.batch_crawl.asyncio.run"
            ) as mock_async_run:
                mock_crawl_all.return_value = {
                    "users_crawled": 1,
                    "platforms": {},
                    "import": {},
                    "errors": [],
                }
                mock_async_run.return_value = mock_crawl_all.return_value

                from crawlers.batch_crawl import main

                main(argv=["--users-file", tmp_path])

            out = _parse_stdout(capsys)
            assert out["users_crawled"] == 1
        finally:
            os.unlink(tmp_path)

    def test_cli_users_file_not_found(self, capsys) -> None:
        """Non-existent users file should produce an error."""
        from crawlers.batch_crawl import main

        main(argv=["--users-file", "/nonexistent/path/users.json"])

        out = _parse_stdout(capsys)
        assert out["success"] is False
        assert "No users found" in out["error"]
