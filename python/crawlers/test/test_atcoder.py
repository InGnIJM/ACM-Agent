"""
Tests for crawlers/atcoder.py – AtCoderCrawler.

All HTTP is mocked via _http_request so no real network calls are made.
Focuses on fetch_problem and fetch_problems_by_tag methods.
"""

from __future__ import annotations

import re
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
        assert len(sample) == 3  # [input, output, note]
        assert "5" in sample[0]
        assert "6" in sample[1]
        assert sample[2] == ""  # _HTML_TEMPLATE Sample Output has no explanation

    def test_sample_output_extracts_explanation_as_note(self) -> None:
        """Sample Output section's explanation (paragraphs / ASCII-art <pre>
        that come AFTER the answer <pre>) must be captured as the sample
        NOTE (third element) so the frontend renders it under '解释 #N',
        instead of being thrown away. (1202Contest_b Sample Output 2 lost
        its 'In this case...' text + dungeon diagram + interactive table.)
        """
        html = (
            """<!DOCTYPE html><html><head><title>T</title></head><body>
<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>Do X.</p>
<h3>Input</h3><p>x</p>
<h3>Output</h3><p>y</p>
<h3>Sample Input 1</h3>
<pre>2 1 First</pre>
<h3>Sample Output 1</h3>
<pre>Yes
...</pre>
<p>In this case, the dungeon is as below:</p>
<pre>| |
 -
| |</pre>
<p>You use the magic first.</p>
</span></div></body></html>"""
        )
        sections = AtCoderCrawler._extract_sections(html)
        samples = sections["samples"]
        assert len(samples) == 1
        sample = samples[0]
        assert len(sample) == 3, f"expected [input, output, note], got {sample!r}"
        # Output stays clean (only the answer)
        assert sample[1].strip() == "Yes\n..."
        note = sample[2]
        assert "In this case" in note, f"explanation paragraph missing: {note!r}"
        assert "You use the magic first" in note
        # ASCII-art <pre> preserved inside a code fence in the note
        assert "```" in note
        assert "| |" in note

    def test_preserves_multiline_dollar_constraints_verbatim(self) -> None:
        """Multi-line $...$ constraints (one per <li>) are preserved verbatim.

        Regression armour for root cause: AtCoder constraint lists use
        ``<var>`` elements rendered as ``$...$`` math; each ``<li>`` must
        remain on its own line and the LaTeX must NOT be mangled by
        ``_wrap_latex`` (which early-returns when ``$`` is already present).
        """
        html = (
            r"""<!DOCTYPE html><html><head><title>T</title></head><body>
<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>Do X.</p>
<h3>Constraints</h3>
<ul>
<li><var>1 \le N \le 10^5</var></li>
<li><var>1 \le M \le 10^5</var></li>
<li><var>N + M \le 2 \times 10^5</var></li>
</ul>
<h3>Input</h3><p>x</p>
</span></div></body></html>"""
        )
        sections = AtCoderCrawler._extract_sections(html)
        constraints = sections["constraints"]

        # Each constraint wrapped in $...$, LaTeX preserved verbatim
        assert r"$1 \le N \le 10^5$" in constraints
        assert r"$1 \le M \le 10^5$" in constraints
        assert r"$N + M \le 2 \times 10^5$" in constraints

        # Multi-line structure: each constraint on its own non-empty line
        lines = [ln for ln in constraints.split("\n") if ln.strip()]
        assert len(lines) == 3, (
            f"expected 3 constraint lines, got {lines!r}"
        )

    # ── Realistic AtCoder fixture mirroring 1202Contest_b (input/output ──
    # format <pre> with <var> math, <ul><li> constraints, inline <code>).
    _HTML_1202 = (
        r"""<!DOCTYPE html><html><head><title>B - vs. DEGwer</title></head><body>
<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>This is an interactive problem.</p>
<h3>Constraints</h3>
<ul>
<li><var>1 \leq H \leq 20</var></li>
<li><var>1 \leq W \leq 20</var></li>
<li><var>\textrm{move}</var> is either <code>First</code> or <code>Second</code>, where <code>First</code> means you use the magic first.</li>
</ul>
<h3>Input</h3>
<p>The input is given in the following format:</p>
<pre><var>H</var> <var>W</var> <var>\textrm{move}</var></pre>
<h3>Output</h3>
<p>Print <code>Yes</code> or <code>No</code>.</p>
<pre><var>t</var> <var>i</var> <var>j</var></pre>
<ul><li><var>t</var> is either <code>|</code> or <code>-</code>.</li></ul>
<h3>Sample Input 1</h3>
<pre>1 1 First</pre>
<h3>Sample Output 1</h3>
<pre>No</pre>
</span></div></body></html>"""
    )

    def test_input_format_pre_with_var_keeps_latex_unfenced(self) -> None:
        """Input-format ``<pre>`` that contains ``<var>`` math must NOT be
        wrapped in a fenced code block — otherwise the LaTeX (``$H$ $W$
        $\\textrm{move}$``) won't render (code fences don't run math).

        Root cause C: AtCoder I/O-format blocks are "format with math
        variables", not code. Keep them as a plain text block so KaTeX
        renders H / W / move.
        """
        html = (
            r"""<!DOCTYPE html><html><head><title>T</title></head><body>
<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>Do X.</p>
<h3>Input</h3>
<pre><var>H</var> <var>W</var> <var>\textrm{move}</var></pre>
<h3>Output</h3><p>y</p>
</span></div></body></html>"""
        )
        sections = AtCoderCrawler._extract_sections(html)
        input_fmt = sections["input_format"]

        # NOT wrapped in a code fence
        assert "```" not in input_fmt, (
            f"input-format pre must stay unfenced, got {input_fmt!r}"
        )
        # LaTeX tokens survive so KaTeX can render them
        assert r"$H$ $W$ $\textrm{move}$" in input_fmt

    def test_plain_pre_still_wrapped_in_fenced_code_block(self) -> None:
        """Plain-text ``<pre>`` (no math) — e.g. sample ASCII art / output
        preview — MUST still be wrapped in a fenced code block (regression
        guard for root cause C fix: only ``<var>``-bearing pre stays unfenced).
        """
        html = (
            """<!DOCTYPE html><html><head><title>T</title></head><body>
<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3>
<p>Do X.</p>
<pre>| |
 -
| |</pre>
</span></div></body></html>"""
        )
        sections = AtCoderCrawler._extract_sections(html)
        assert "```" in sections["description"]

    def test_inline_code_becomes_backticks(self) -> None:
        """``<code>x</code>`` → Markdown inline `` `x` ``.

        Root cause A: without backticks, get_text("\\n") isolates the
        inner text on its own line (e.g. ``First`` / ``Yes``), shattering
        the sentence and, for ``-`` / ``|`` tokens, triggering Setext
        headings on the frontend.
        """
        sections = AtCoderCrawler._extract_sections(self._HTML_1202)
        constraints = sections["constraints"]
        # Each inline <code> survives as a backtick-wrapped inline-code span
        assert "`First`" in constraints
        assert "`Second`" in constraints
        # And they must NOT be isolated on their own line — verify the
        # third <li> stays a single line containing both tokens
        third = [ln for ln in constraints.split("\n") if "is either" in ln]
        assert len(third) == 1, f"expected single line, got {third!r}"
        assert "`First`" in third[0] and "`Second`" in third[0]

    def test_unordered_list_becomes_markdown_list(self) -> None:
        """``<ul><li>`` → Markdown ``- item`` list.

        Root cause B: get_text("\\n") flattens list items into bare
        newline-separated lines, losing the list structure (no ``- ``
        markers) so the frontend renders them as one paragraph.
        """
        sections = AtCoderCrawler._extract_sections(self._HTML_1202)
        constraints = sections["constraints"]
        # Three constraint lines, each a markdown bullet
        bullets = [ln for ln in constraints.split("\n") if ln.startswith("- ")]
        assert len(bullets) == 3, (
            f"expected 3 markdown bullets, got {bullets!r}"
        )
        assert r"$1 \leq H \leq 20$" in bullets[0]
        assert r"$1 \leq W \leq 20$" in bullets[1]
        assert "move" in bullets[2] and "`First`" in bullets[2]

    def test_sample_output_excludes_explanatory_pre(self) -> None:
        """Sample Output section's FIRST ``<pre>`` is the answer; any
        subsequent ``<pre>`` (ASCII-art diagram / illustration inside the
        explanation paragraph) must NOT be merged into the sample output.

        Root cause: ``find_all("pre")`` + ``"\\n".join`` concatenated
        every ``<pre>`` in the section, so the dungeon diagram
        ``| |\\n -\\n| |`` leaked into Sample Output 2 of 1202Contest_b
        (rendered as part of the answer code block).
        """
        html = (
            """<!DOCTYPE html><html><head><title>T</title></head><body>
<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>Do X.</p>
<h3>Input</h3><p>x</p>
<h3>Output</h3><p>y</p>
<h3>Sample Input 1</h3>
<pre>2 1 First</pre>
<h3>Sample Output 1</h3>
<pre>Yes
...</pre>
<p>The dungeon looks like:</p>
<pre>| |
 -
| |</pre>
</span></div></body></html>"""
        )
        sections = AtCoderCrawler._extract_sections(html)
        samples = sections["samples"]
        assert len(samples) == 1, f"expected 1 sample, got {samples!r}"
        out = samples[0][1]
        # The answer (first pre) is preserved...
        assert "Yes" in out and "..." in out
        # ...but the ASCII-art diagram from the explanation paragraph is excluded
        assert "| |" not in out, f"diagram leaked into output: {out!r}"

    def test_sample_table_becomes_markdown_table(self) -> None:
        """A ``<table>`` inside a sample explanation becomes a Markdown
        pipe-table (header row + ``---`` separator + body rows), not a
        flattened content soup."""
        html = (
            """<!DOCTYPE html><html><head><title>T</title></head><body>
<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>Do X.</p>
<h3>Input</h3><p>x</p>
<h3>Output</h3><p>y</p>
<h3>Sample Input 1</h3><pre>2 1</pre>
<h3>Sample Output 1</h3>
<pre>Yes</pre>
<table class="table table-bordered"><thead><tr>
<th>Input</th><th>Output</th><th>Explanation</th>
</tr></thead><tbody>
<tr><td><code>2 1</code></td><td></td><td>An input is given.</td></tr>
<tr><td></td><td><code>Yes</code></td><td>You print Yes.</td></tr>
</tbody></table>
</span></div></body></html>"""
        )
        sections = AtCoderCrawler._extract_sections(html)
        note = sections["samples"][0][2]
        # Header row + separator (exact)
        assert "| Input | Output | Explanation |" in note
        assert re.search(r"\|\s*-{3,}\s*\|\s*-{3,}\s*\|\s*-{3,}\s*\|", note), note
        # Body cells survive with inline code + math, column order preserved
        # even with empty cells (don't assert exact spacing around pipes).
        assert "`2 1`" in note and "An input is given." in note
        assert "`Yes`" in note and "You print Yes." in note

    def test_ordered_list_becomes_markdown_ordered_list(self) -> None:
        """``<ol><li>`` → Markdown ``1.`` / ``2.`` numbered list."""
        html = (
            """<!DOCTYPE html><html><head><title>T</title></head><body>
<div id="task-statement"><span class="lang-en">
<h3>Problem Statement</h3><p>Steps:</p>
<ol><li>Do A.</li><li>Do B.</li><li>Do C.</li></ol>
</span></div></body></html>"""
        )
        sections = AtCoderCrawler._extract_sections(html)
        desc = sections["description"]
        assert "1. Do A." in desc
        assert "2. Do B." in desc
        assert "3. Do C." in desc

    def test_output_format_avoids_setext_heading_trap(self) -> None:
        """The ``-`` / ``|`` tokens inside output-format ``<code>`` must
        remain backtick-escaped so they never sit on their own line and
        trigger a Setext heading (frontend rendered stray ``<h5>``).
        """
        sections = AtCoderCrawler._extract_sections(self._HTML_1202)
        output_fmt = sections["output_format"]
        # Code tokens wrapped, never bare-on-their-own-line
        assert "`|`" in output_fmt
        assert "`-`" in output_fmt
        assert "`Yes`" in output_fmt
        # The input/output format <pre> with <var> stays unfenced
        assert r"$t$ $i$ $j$" in output_fmt
        # No Setext trap: no line that is a bare '-' or '|'
        for ln in output_fmt.split("\n"):
            assert ln.strip() not in ("-", "|", "=", "a", "w"), (
                f"bare token on its own line → Setext/fragmentation: {ln!r}"
            )


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
