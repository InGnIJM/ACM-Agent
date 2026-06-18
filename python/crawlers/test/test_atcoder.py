"""
Tests for crawlers/atcoder.py – AtCoderCrawler.

All HTTP is mocked via _http_request so no real network calls are made.
Focuses on fetch_problem and fetch_problems_by_tag methods.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import CrawlResult, RateLimiter
from crawlers.atcoder import AtCoderCrawler


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><title>Task_a - AtCoder Beginner Contest 400</title></head>
<body>
<div id="task-statement">
<span class="lang-en">
<h3>Problem Statement</h3>
<p>Given an integer N, print N+1.</p>
<h3>Constraints</h3>
<ul><li>1 ≤ N ≤ 100</li></ul>
<h3>Input</h3>
<p>N</p>
<h3>Output</h3>
<p>Print N+1.</p>
<h3>Sample Input 1</h3>
<pre>5</pre>
<h3>Sample Output 1</h3>
<pre>6</pre>
</span>
</div>
</body>
</html>"""

_HTML_NO_CONSTRAINTS_H3 = """\
<!DOCTYPE html>
<html>
<head><title>Task_b - AtCoder Beginner Contest 400</title></head>
<body>
<div id="task-statement">
<span class="lang-en">
<h3>Problem</h3>
<p>Do something.</p>
<h3>Input</h3>
<p>x</p>
<h3>Output</h3>
<p>y</p>
</span>
</div>
</body>
</html>"""


def _mock_crawler() -> AtCoderCrawler:
    """Return an AtCoderCrawler with internal deps mocked."""
    crawler = AtCoderCrawler.__new__(AtCoderCrawler)
    crawler.PLATFORM = "atcoder"
    crawler.BASE_URL = "https://atcoder.jp"
    crawler.KENKOO_API = "https://kenkoooo.com/atcoder"
    crawler.data_dir = MagicMock()
    crawler.headless = True
    crawler._session = MagicMock()
    crawler._browser = None
    crawler._rate_limiter = RateLimiter(qps=100, jitter=0)
    crawler._cookie_manager = MagicMock()
    crawler._cookie_manager.load.return_value = None

    crawler._http_request = MagicMock()
    crawler.fetch_with_fallback = MagicMock()
    return crawler


def _crawl_ok(data: object) -> CrawlResult:
    return CrawlResult(success=True, data=data, source="http")


def _crawl_fail(msg: str = "fail") -> CrawlResult:
    return CrawlResult(success=False, error=msg, source="http")


# ──────────────────────────────────────────────
# fetch_problem
# ──────────────────────────────────────────────


class TestFetchProblem:
    """Tests for AtCoderCrawler.fetch_problem()."""

    def test_basic_success_with_all_enrichments(self) -> None:
        """Happy path: HTML parsed, kenkoooo metadata + difficulty + tags added."""
        crawler = _mock_crawler()

        # Mock the problem page fetch (HTML)
        crawler.fetch_with_fallback.return_value = _crawl_ok(
            {"text": _HTML_TEMPLATE}
        )

        # Mock kenkoooo merged-problems.json
        crawler._http_request.side_effect = [
            # 1st call: merged-problems.json
            _crawl_ok([
                {
                    "id": "abc400_a",
                    "contest_id": "abc400",
                    "title": "A. Print N+1",
                    "point": 100,
                    "solver_count": 5000,
                }
            ]),
            # 2nd call: problem-models.json
            _crawl_ok({
                "abc400_a": {"difficulty": 42, "is_experimental": False}
            }),
        ]

        result = crawler.fetch_problem("abc400_a")

        assert result.success
        data = result.data
        assert isinstance(data, dict)
        assert data["source_id"] == "abc400_a"
        assert data["contest_id"] == "abc400"
        assert data["index"] == "a"
        assert "AtCoder Beginner Contest 400" in str(data["title"])
        assert "Given an integer N" in str(data["description"])
        assert "1 ≤ N ≤ 100" in str(data["constraints"])
        assert data["source_url"] == (
            "https://atcoder.jp/contests/abc400/tasks/abc400_a"
        )
        assert data["point"] == 100
        assert data["solver_count"] == 5000
        assert data["difficulty"] == 42
        assert data["tags"] == ["abc"]

    def test_fetch_with_fallback_failure(self) -> None:
        """When the problem page cannot be fetched, return the error result."""
        crawler = _mock_crawler()
        crawler.fetch_with_fallback.return_value = _crawl_fail("HTTP 404")

        result = crawler.fetch_problem("abc400_a")
        assert not result.success
        assert "404" in str(result.error)

    def test_empty_html_response(self) -> None:
        """Empty HTML from problem page returns an error."""
        crawler = _mock_crawler()
        crawler.fetch_with_fallback.return_value = _crawl_ok({"text": ""})

        result = crawler.fetch_problem("abc400_a")
        assert not result.success
        assert "Empty response" in str(result.error)

    def test_unparseable_source_id(self) -> None:
        """Source ID that cannot be parsed returns error immediately."""
        crawler = _mock_crawler()
        # "nocontest" has no underscore, so _parse_problem_id returns ("", "nocontest")
        result = crawler.fetch_problem("nocontest")
        assert not result.success
        assert "Cannot parse problem ID" in str(result.error)

    def test_kenkoooo_api_failure_does_not_break_fetch(self) -> None:
        """If merged-problems.json returns error, fetch_problem still succeeds."""
        crawler = _mock_crawler()
        crawler.fetch_with_fallback.return_value = _crawl_ok(
            {"text": _HTML_TEMPLATE}
        )
        # Both kenkoooo calls fail
        crawler._http_request.side_effect = [
            _crawl_fail("HTTP 500"),
            _crawl_fail("HTTP 500"),
        ]

        result = crawler.fetch_problem("abc400_a")
        assert result.success
        data = result.data
        assert isinstance(data, dict)
        assert "point" not in data
        assert "difficulty" not in data
        assert "tags" in data  # tags come from contest_id, not API
        assert data["tags"] == ["abc"]

    def test_problem_models_not_a_dict(self) -> None:
        """If problem-models.json returns a list, difficulty is not added."""
        crawler = _mock_crawler()
        crawler.fetch_with_fallback.return_value = _crawl_ok(
            {"text": _HTML_TEMPLATE}
        )
        crawler._http_request.side_effect = [
            _crawl_ok([
                {
                    "id": "abc400_a",
                    "contest_id": "abc400",
                    "point": 100,
                    "solver_count": 5000,
                }
            ]),
            _crawl_ok([]),  # list instead of dict
        ]

        result = crawler.fetch_problem("abc400_a")
        assert result.success
        assert "difficulty" not in result.data

    def test_merged_problems_entry_not_found(self) -> None:
        """If merged-problems has no matching entry, point/solver_count omitted."""
        crawler = _mock_crawler()
        crawler.fetch_with_fallback.return_value = _crawl_ok(
            {"text": _HTML_TEMPLATE}
        )
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "abc400_b", "contest_id": "abc400", "point": 200}
            ]),
            _crawl_ok({}),
        ]

        result = crawler.fetch_problem("abc400_a")
        assert result.success
        assert "point" not in result.data

    def test_constraints_fallback_regex(self) -> None:
        """When _extract_sections misses constraints, dedicated regex extracts it."""
        crawler = _mock_crawler()
        html_with_constraints = """\
<!DOCTYPE html>
<html><head><title>T</title></head><body>
<div id="task-statement"><span class="lang-en">
<p>Some preamble.</p>
<h3>Problem Statement</h3>
<p>Do X.</p>
<h3>Constraints</h3>
<ul><li>1 ≤ X ≤ 10</li></ul>
<h3>Input</h3>
<p>x</p>
</span></div></body></html>"""
        crawler.fetch_with_fallback.return_value = _crawl_ok(
            {"text": html_with_constraints}
        )
        crawler._http_request.side_effect = [
            _crawl_fail("fail"),
            _crawl_fail("fail"),
        ]

        # Mock _extract_sections to simulate missing constraints
        with patch.object(
            AtCoderCrawler,
            "_extract_sections",
            return_value={
                "description": "Do X.",
                "constraints": "",
                "input_format": "x",
                "output_format": "",
                "samples": [],
            },
        ):
            result = crawler.fetch_problem("abc400_a")

        assert result.success
        data = result.data
        assert isinstance(data, dict)
        assert "1 ≤ X ≤ 10" in str(data["constraints"])

    def test_constraints_fallback_exception_handled(self) -> None:
        """When an exception occurs during fallback extraction, it is swallowed."""
        crawler = _mock_crawler()
        html = """\
<html><head><title>T</title></head><body>
<h3>Constraints</h3><p>1 ≤ X ≤ 10</p>
<h3>Something else</h3></body></html>"""
        crawler.fetch_with_fallback.return_value = _crawl_ok({"text": html})
        crawler._http_request.side_effect = [
            _crawl_fail("fail"),
            _crawl_fail("fail"),
        ]

        with patch.object(
            AtCoderCrawler,
            "_extract_sections",
            return_value={
                "description": "",
                "constraints": "",
                "input_format": "",
                "output_format": "",
                "samples": [],
            },
        ):
            # Force _process_katex to raise, triggering the except handler
            with patch.object(
                AtCoderCrawler, "_process_katex", side_effect=RuntimeError("boom")
            ):
                result = crawler.fetch_problem("abc400_a")

        assert result.success
        # constraints remains empty since fallback failed
        assert result.data["constraints"] == ""

    def test_tags_for_arc_contest(self) -> None:
        """Tags derive from contest_id prefix (arc → arc)."""
        crawler = _mock_crawler()
        crawler.fetch_with_fallback.return_value = _crawl_ok(
            {"text": _HTML_TEMPLATE}
        )
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "arc180_a", "contest_id": "arc180", "point": 300}
            ]),
            _crawl_ok({}),
        ]

        result = crawler.fetch_problem("arc180_a")
        assert result.success
        assert result.data["tags"] == ["arc"]

    def test_tags_for_agc_contest(self) -> None:
        """Tags derive from contest_id prefix (agc → agc)."""
        crawler = _mock_crawler()
        crawler.fetch_with_fallback.return_value = _crawl_ok(
            {"text": _HTML_TEMPLATE}
        )
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "agc070_a", "contest_id": "agc070", "point": 600}
            ]),
            _crawl_ok({}),
        ]

        result = crawler.fetch_problem("agc070_a")
        assert result.success
        assert result.data["tags"] == ["agc"]

    def test_exception_during_enrichment_is_swallowed(self) -> None:
        """If _http_request raises an exception, fetch still succeeds."""
        crawler = _mock_crawler()
        crawler.fetch_with_fallback.return_value = _crawl_ok(
            {"text": _HTML_TEMPLATE}
        )
        crawler._http_request.side_effect = Exception("network gone")

        result = crawler.fetch_problem("abc400_a")
        assert result.success
        # No kenkoooo enrichment but base data is present
        assert result.data["source_id"] == "abc400_a"


# ──────────────────────────────────────────────
# fetch_problems_by_tag
# ──────────────────────────────────────────────


class TestFetchProblemsByTag:
    """Tests for AtCoderCrawler.fetch_problems_by_tag()."""

    def test_basic_filter_by_tag(self) -> None:
        """Filters merged-problems by tag prefix and adds source_url."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            # merged-problems.json
            _crawl_ok([
                {"id": "abc400_a", "contest_id": "abc400", "title": "A"},
                {"id": "abc400_b", "contest_id": "abc400", "title": "B"},
                {"id": "arc180_a", "contest_id": "arc180", "title": "C"},
            ]),
            # problem-models.json (empty)
            _crawl_ok({}),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        data = result.data
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == "abc400_a"
        assert data[1]["id"] == "abc400_b"
        assert "source_url" in data[0]

    def test_respects_count_limit(self) -> None:
        """Returns at most `count` matching problems."""
        crawler = _mock_crawler()
        problems = [
            {"id": f"abc400_{chr(97+i)}", "contest_id": "abc400"}
            for i in range(20)
        ]
        crawler._http_request.side_effect = [
            _crawl_ok(problems),
            _crawl_ok({}),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=5)
        assert result.success
        assert len(result.data) == 5

    def test_difficulty_merged_from_problem_models(self) -> None:
        """Difficulty from problem-models.json is merged into each problem."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "abc400_a", "contest_id": "abc400", "title": "A"},
                {"id": "abc400_b", "contest_id": "abc400", "title": "B"},
            ]),
            _crawl_ok({
                "abc400_a": {"difficulty": 42},
                "abc400_b": {"difficulty": 87},
            }),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        assert result.data[0]["difficulty"] == 42
        assert result.data[1]["difficulty"] == 87

    def test_difficulty_missing_for_some_problems(self) -> None:
        """Problems not in problem-models.json simply lack difficulty field."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "abc400_c", "contest_id": "abc400", "title": "C"},
            ]),
            _crawl_ok({"abc400_a": {"difficulty": 42}}),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        assert "difficulty" not in result.data[0]

    def test_merged_problems_not_a_list(self) -> None:
        """Returns error when merged-problems response is not a list."""
        crawler = _mock_crawler()
        crawler._http_request.return_value = _crawl_ok({"not": "a list"})

        result = crawler.fetch_problems_by_tag("abc")
        assert not result.success
        assert "Unexpected" in str(result.error)

    def test_problem_models_fetch_failure(self) -> None:
        """If problem-models.json fails, matching is unaffected."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "abc400_a", "contest_id": "abc400", "title": "A"},
            ]),
            _crawl_fail("timeout"),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        assert len(result.data) == 1
        assert "difficulty" not in result.data[0]

    def test_problem_models_not_a_dict(self) -> None:
        """If problem-models.json returns a list, no difficulty merged."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "abc400_a", "contest_id": "abc400", "title": "A"},
            ]),
            _crawl_ok([]),  # list instead of dict
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        assert "difficulty" not in result.data[0]

    def test_exception_during_difficulty_fetch(self) -> None:
        """Exception in problem-models fetch is swallowed."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "abc400_a", "contest_id": "abc400", "title": "A"},
            ]),
            Exception("crash"),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        assert len(result.data) == 1

    def test_no_matching_problems(self) -> None:
        """Returns empty list when no problems match the tag."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            _crawl_ok([
                {"id": "arc180_a", "contest_id": "arc180", "title": "C"},
            ]),
            _crawl_ok({}),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        assert result.data == []

    def test_source_url_attached_when_missing(self) -> None:
        """source_url is auto-generated from contest_id and problem id."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            _crawl_ok([
                {
                    "id": "abc400_a",
                    "contest_id": "abc400",
                    "title": "A",
                    # No source_url
                },
            ]),
            _crawl_ok({}),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        assert result.data[0]["source_url"] == (
            "https://atcoder.jp/contests/abc400/tasks/abc400_a"
        )

    def test_existing_source_url_preserved(self) -> None:
        """If source_url already exists, it is not overwritten."""
        crawler = _mock_crawler()
        crawler._http_request.side_effect = [
            _crawl_ok([
                {
                    "id": "abc400_a",
                    "contest_id": "abc400",
                    "title": "A",
                    "source_url": "https://custom.url/problem",
                },
            ]),
            _crawl_ok({}),
        ]

        result = crawler.fetch_problems_by_tag("abc", count=10)
        assert result.success
        assert result.data[0]["source_url"] == "https://custom.url/problem"


# ──────────────────────────────────────────────
# _parse_problem_id
# ──────────────────────────────────────────────


class TestParseProblemId:
    """Tests for AtCoderCrawler._parse_problem_id()."""

    @pytest.mark.parametrize(
        "source_id, expected",
        [
            ("abc400_a", ("abc400", "a")),
            ("arc180_f", ("arc180", "f")),
            ("agc070_a2", ("agc070", "a2")),
            ("abc001_ex", ("abc001", "ex")),
        ],
    )
    def test_standard_format(self, source_id, expected) -> None:
        assert AtCoderCrawler._parse_problem_id(source_id) == expected

    @pytest.mark.parametrize(
        "source_id",
        ["only_underscore_", "_leading"],
    )
    def test_unparseable_returns_empty_contest(self, source_id) -> None:
        contest, index = AtCoderCrawler._parse_problem_id(source_id)
        assert contest == ""


# ──────────────────────────────────────────────
# _extract_sections
# ──────────────────────────────────────────────


class TestExtractSections:
    """Tests for AtCoderCrawler._extract_sections()."""

    def test_extracts_all_sections(self) -> None:
        sections = AtCoderCrawler._extract_sections(_HTML_TEMPLATE)
        assert "Given an integer N" in sections["description"]
        assert "1 ≤ N ≤ 100" in sections["constraints"]
        assert sections["samples"]  # non-empty

    def test_empty_html_returns_empty_dict(self) -> None:
        sections = AtCoderCrawler._extract_sections("")
        assert sections == {}

    def test_no_task_statement_returns_empty(self) -> None:
        html = "<html><body><p>no task</p></body></html>"
        sections = AtCoderCrawler._extract_sections(html)
        assert sections == {}

    def test_samples_paired_correctly(self) -> None:
        sections = AtCoderCrawler._extract_sections(_HTML_TEMPLATE)
        assert len(sections["samples"]) >= 1
        sample = sections["samples"][0]
        assert isinstance(sample, list)
        assert len(sample) == 2  # [input, output]
        assert "5" in sample[0]
        assert "6" in sample[1]


# ──────────────────────────────────────────────
# _normalize_text
# ──────────────────────────────────────────────


class TestNormalizeText:
    """Tests for AtCoderCrawler._normalize_text()."""

    def test_collapses_multiple_newlines(self) -> None:
        text = "line1\n\n\n\nline2"
        result = AtCoderCrawler._normalize_text(text)
        assert result == "line1\n\nline2"

    def test_collapses_multiple_spaces(self) -> None:
        text = "a     b   c"
        result = AtCoderCrawler._normalize_text(text)
        assert result == "a b c"

    def test_strips_whitespace(self) -> None:
        text = "  hello  \n  world  "
        result = AtCoderCrawler._normalize_text(text)
        # Multiple spaces collapsed to single space; leading/trailing stripped
        assert result == "hello \n world"

    def test_handles_html_entities(self) -> None:
        text = "a &lt; b &amp;&amp; c &gt; d"
        result = AtCoderCrawler._normalize_text(text)
        assert result == "a < b && c > d"

    def test_crlf_converted_to_lf(self) -> None:
        text = "line1\r\nline2\r\nline3"
        result = AtCoderCrawler._normalize_text(text)
        assert "\r" not in result
        assert result == "line1\nline2\nline3"
