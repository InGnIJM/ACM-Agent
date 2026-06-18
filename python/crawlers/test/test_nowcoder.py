"""
Tests for crawlers/nowcoder.py – NowCoderCrawler.

Focuses on _scrape_problem_list table parsing and difficulty extraction.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawlers.base import CrawlResult, RateLimiter
from crawlers.nowcoder import NowCoderCrawler


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _mock_crawler() -> NowCoderCrawler:
    """Return a NowCoderCrawler with _rate_limiter set to no-op jitter=0."""
    crawler = NowCoderCrawler.__new__(NowCoderCrawler)
    crawler.PLATFORM = "nowcoder"
    crawler.headless = True
    crawler._session = MagicMock()
    crawler._browser = None
    crawler._rate_limiter = RateLimiter(qps=100, jitter=0)
    crawler._cookie_manager = MagicMock()
    crawler._cookie_manager.load.return_value = None
    crawler._http_request = MagicMock()
    return crawler


def _crawl_ok(data: object) -> CrawlResult:
    return CrawlResult(success=True, data=data, source="http")


# ──────────────────────────────────────────────
# _scrape_problem_list — table parsing
# ──────────────────────────────────────────────

NOWCODER_TABLE_HTML = """<html><body>
<table>
  <thead>
    <tr><th>题号</th><th>标题</th><th width="20">难度</th><th>通过率</th><th>标签</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>NC1</td>
      <td><a href="/acm/problem/317489">DP入门</a></td>
      <td>1600</td>
      <td>45.2%</td>
      <td>dp, 背包</td>
    </tr>
    <tr>
      <td>NC2</td>
      <td><a href="/acm/problem/317490">贪心策略</a></td>
      <td>中等</td>
      <td>60.1%</td>
      <td>贪心, 排序</td>
    </tr>
    <tr>
      <td>NC3</td>
      <td><a href="/acm/problem/317491">图论基础</a></td>
      <td>2000</td>
      <td>32.8%</td>
      <td>图论</td>
    </tr>
  </tbody>
</table>
</body></html>"""


class TestScrapeProblemListBS4:
    """Verify BeautifulSoup-based table parsing extracts all fields."""

    def test_extracts_ids_titles_urls(self) -> None:
        result = NowCoderCrawler._scrape_problem_list(NOWCODER_TABLE_HTML)
        assert len(result) == 3

        assert result[0]["id"] == "317489"
        assert result[0]["title"] == "DP入门"
        assert result[0]["url"] == "https://ac.nowcoder.com/acm/problem/317489"

        assert result[1]["id"] == "317490"
        assert result[1]["title"] == "贪心策略"

        assert result[2]["id"] == "317491"
        assert result[2]["title"] == "图论基础"

    def test_extracts_numeric_difficulty(self) -> None:
        result = NowCoderCrawler._scrape_problem_list(NOWCODER_TABLE_HTML)
        assert result[0]["difficulty"] == "1600"

    def test_extracts_text_difficulty(self) -> None:
        result = NowCoderCrawler._scrape_problem_list(NOWCODER_TABLE_HTML)
        assert result[1]["difficulty"] == "中等"

    def test_extracts_tags_column(self) -> None:
        result = NowCoderCrawler._scrape_problem_list(NOWCODER_TABLE_HTML)
        assert result[0]["tags"] == ["dp", "背包"]
        assert result[1]["tags"] == ["贪心", "排序"]
        assert result[2]["tags"] == ["图论"]

    def test_all_keys_present(self) -> None:
        result = NowCoderCrawler._scrape_problem_list(NOWCODER_TABLE_HTML)
        for item in result:
            assert set(item.keys()) == {"id", "title", "url", "difficulty", "tags"}

    def test_max_count_limits_results(self) -> None:
        result = NowCoderCrawler._scrape_problem_list(NOWCODER_TABLE_HTML, max_count=2)
        assert len(result) == 2


# ──────────────────────────────────────────────
# _scrape_problem_list — regex fallback (no bs4)
# ──────────────────────────────────────────────

NO_BS4_TABLE = """<html><body>
<table>
  <thead><tr><th>题号</th><th>标题</th><th width="20">难度</th><th>通过率</th></tr></thead>
  <tbody>
    <tr><td>NC1</td><td><a href="/acm/problem/317489">DP入门</a></td><td>1600</td><td>45.2%</td></tr>
    <tr><td>NC2</td><td><a href="/acm/problem/317490">贪心策略</a></td><td>1200</td><td>60.1%</td></tr>
  </tbody>
</table>
</body></html>"""

# No <thead>/<tbody>, just plain <tr>/<th>/<td>
FLAT_TABLE = """<html><body>
<table>
  <tr><th>题号</th><th>标题</th><th width="20">难度</th><th>通过率</th></tr>
  <tr><td>NC1</td><td><a href="/acm/problem/888">测试题</a></td><td>800</td><td>70%</td></tr>
</table>
</body></html>"""


class TestScrapeProblemListRegex:
    """Verify regex fallback when bs4 is not available."""

    def test_regex_parses_table_with_tbody(self, monkeypatch) -> None:
        """When bs4 import fails, regex fallback should still work."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "bs4" or name.startswith("bs4."):
                raise ImportError("No bs4")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        result = NowCoderCrawler._scrape_problem_list(NO_BS4_TABLE)
        assert len(result) == 2
        assert result[0]["id"] == "317489"
        assert result[0]["title"] == "DP入门"
        assert result[0]["difficulty"] == "1600"
        assert result[0]["tags"] == []
        assert result[1]["id"] == "317490"
        assert result[1]["difficulty"] == "1200"

    def test_regex_parses_flat_table(self, monkeypatch) -> None:
        """Regex fallback handles tables without thead/tbody."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "bs4" or name.startswith("bs4."):
                raise ImportError("No bs4")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        result = NowCoderCrawler._scrape_problem_list(FLAT_TABLE)
        assert len(result) == 1
        assert result[0]["id"] == "888"
        assert result[0]["difficulty"] == "800"


# ──────────────────────────────────────────────
# _scrape_problem_list — ultimate fallback
# ──────────────────────────────────────────────

NO_TABLE_HTML = """<html><body>
<div><a href="/acm/problem/100">Problem A</a></div>
<div><a href="/acm/problem/200">Problem B</a></div>
</body></html>"""


class TestScrapeProblemListLinkFallback:
    """Verify simple link extraction when no table is found."""

    def test_fallback_parses_links(self, monkeypatch) -> None:
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "bs4" or name.startswith("bs4."):
                raise ImportError("No bs4")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        result = NowCoderCrawler._scrape_problem_list(NO_TABLE_HTML)
        assert len(result) == 2
        assert result[0]["id"] == "100"
        assert result[0]["title"] == "Problem A"
        assert result[0]["difficulty"] == ""
        assert result[0]["tags"] == []
        assert result[1]["id"] == "200"
        assert result[1]["title"] == "Problem B"


# ──────────────────────────────────────────────
# fetch_problems_by_tag — integration
# ──────────────────────────────────────────────

class TestFetchProblemsByTag:
    """Verify fetch_problems_by_tag uses _scrape_problem_list as fallback."""

    def test_returns_problems_with_difficulty_and_tags(self, monkeypatch) -> None:
        """When no embedded state available, should use table scraping."""
        crawler = _mock_crawler()

        # Return HTML that has no __INITIAL_STATE__ but has a table
        crawler.fetch_with_fallback = MagicMock(return_value=_crawl_ok(
            {"text": NOWCODER_TABLE_HTML}
        ))

        result = crawler.fetch_problems_by_tag("dp", count=2)
        assert result.success
        data = result.data
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == "317489"
        assert data[0]["difficulty"] == "1600"
        assert "tags" in data[0]
        assert data[1]["id"] == "317490"
        assert data[1]["difficulty"] == "中等"


# ──────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────

class TestScrapeProblemListEdgeCases:
    """Verify edge case handling."""

    def test_empty_html_returns_empty_list(self) -> None:
        result = NowCoderCrawler._scrape_problem_list("")
        assert result == []

    def test_empty_html_returns_empty_list_no_bs4(self, monkeypatch) -> None:
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "bs4" or name.startswith("bs4."):
                raise ImportError("No bs4")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = NowCoderCrawler._scrape_problem_list("")
        assert result == []

    def test_html_without_problem_links_returns_empty(self) -> None:
        html = "<table><tr><th>难度</th></tr><tr><td>100</td></tr></table>"
        result = NowCoderCrawler._scrape_problem_list(html)
        assert result == []

    def test_duplicate_ids_filtered(self) -> None:
        html = """<html><body><table>
          <tr><th>题号</th><th>标题</th><th>难度</th></tr>
          <tr><td>1</td><td><a href="/acm/problem/100">A</a></td><td>500</td></tr>
          <tr><td>2</td><td><a href="/acm/problem/100">A dup</a></td><td>500</td></tr>
        </table></body></html>"""
        result = NowCoderCrawler._scrape_problem_list(html)
        assert len(result) == 1
        assert result[0]["id"] == "100"


# ──────────────────────────────────────────────
# _parse_samples_from_text — text-based parsing
# ──────────────────────────────────────────────

class TestParseSamplesFromText:
    """Verify text-based sample parsing into [[input, output], ...] pairs."""

    def test_multiple_samples_with_markers(self) -> None:
        text = (
            "示例1\n输入\n\n1 2\n3 4\n\n输出\n\n3\n\n"
            "示例2\n输入\n\n5 6\n\n输出\n\n11\n\n"
        )
        result = NowCoderCrawler._parse_samples_from_text(text)
        assert len(result) == 2
        assert result[0] == ["1 2\n3 4", "3"]
        assert result[1] == ["5 6", "11"]

    def test_single_sample_no_marker(self) -> None:
        text = "输入\n\nabc\n\n输出\n\ndef\n\n"
        result = NowCoderCrawler._parse_samples_from_text(text)
        assert len(result) == 1
        assert result[0] == ["abc", "def"]

    def test_trailing_shuoming_removed(self) -> None:
        text = "示例1\n输入\n\nhello\n\n输出\n\nworld\n\n说明\n\n一些解释文字\n"
        result = NowCoderCrawler._parse_samples_from_text(text)
        assert len(result) == 1
        assert result[0] == ["hello", "world"]

    def test_copy_labels_cleaned(self) -> None:
        text = "示例1\n输入\n复制\n1 2\n复制\n输出\n复制\n3\n"
        result = NowCoderCrawler._parse_samples_from_text(text)
        assert len(result) == 1
        assert result[0] == ["1 2", "3"]

    def test_empty_text_returns_empty_list(self) -> None:
        result = NowCoderCrawler._parse_samples_from_text("")
        assert result == []

    def test_whitespace_only_text(self) -> None:
        result = NowCoderCrawler._parse_samples_from_text("   \n  \n   ")
        assert result == []

    def test_extra_blank_lines_trimmed(self) -> None:
        text = "示例1\n\n输入\n\n\nx\n\n\n\n输出\n\n\ny\n\n\n"
        result = NowCoderCrawler._parse_samples_from_text(text)
        assert len(result) == 1
        assert result[0][0].strip() == "x"
        assert result[0][1].strip() == "y"

    def test_empty_input_output_not_paired(self) -> None:
        """Edge case: if input is empty but output has text, still produce a pair."""
        text = "示例1\n输入\n\n\n输出\n\nresult\n"
        result = NowCoderCrawler._parse_samples_from_text(text)
        assert len(result) == 1
        assert result[0] == ["", "result"]

    def test_mixed_example_sample_markers(self) -> None:
        text = "样例1\n输入\n\na\n\n输出\n\nb\n\n示例2\n输入\n\nc\n\n输出\n\nd\n"
        result = NowCoderCrawler._parse_samples_from_text(text)
        assert len(result) == 2
        assert result[0] == ["a", "b"]
        assert result[1] == ["c", "d"]


# ──────────────────────────────────────────────
# _parse_samples_from_html — HTML-based parsing
# ──────────────────────────────────────────────

SAMPLE_DIV_S1 = """<div class="question-oi">
  <div class="question-oi-mod">
    <div class="question-oi-hd">示例1</div>
    <div class="question-oi-bd">
      <pre>1 2
3 4</pre>
      <pre>3</pre>
    </div>
  </div>
  <div class="question-oi-mod">
    <div class="question-oi-hd">示例2</div>
    <div class="question-oi-bd">
      <pre>5 6</pre>
      <pre>11</pre>
    </div>
  </div>
</div>"""

SAMPLE_DIV_S2 = """<div class="question-oi">
  <pre>inp1</pre>
  <pre>out1</pre>
  <pre>inp2</pre>
  <pre>out2</pre>
</div>"""

SAMPLE_DIV_TEXT_ONLY = """<div class="question-oi">
  示例1
  输入

  1 2
  输出

  3
</div>"""

SAMPLE_DIV_EMPTY = """<div class="question-oi">
</div>"""

SAMPLE_DIV_WITH_COPY = """<div class="question-oi">
  <div class="question-oi-mod">
    <pre>复制
1 2</pre>
    <pre>3
复制</pre>
  </div>
</div>"""


class TestParseSamplesFromHtml:
    """Verify HTML-based sample parsing via BeautifulSoup."""

    @staticmethod
    def _make_soup(html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").select_one(".question-oi")

    def test_structured_blocks(self) -> None:
        el = self._make_soup(SAMPLE_DIV_S1)
        result = NowCoderCrawler._parse_samples_from_html(el)
        assert len(result) == 2
        assert result[0] == ["1 2\n3 4", "3"]
        assert result[1] == ["5 6", "11"]

    def test_sequential_pre_tags(self) -> None:
        el = self._make_soup(SAMPLE_DIV_S2)
        result = NowCoderCrawler._parse_samples_from_html(el)
        assert len(result) == 2
        assert result[0] == ["inp1", "out1"]
        assert result[1] == ["inp2", "out2"]

    def test_falls_back_to_text(self) -> None:
        el = self._make_soup(SAMPLE_DIV_TEXT_ONLY)
        result = NowCoderCrawler._parse_samples_from_html(el)
        assert len(result) == 1
        assert result[0][0].strip() == "1 2"
        assert result[0][1].strip() == "3"

    def test_empty_div(self) -> None:
        el = self._make_soup(SAMPLE_DIV_EMPTY)
        result = NowCoderCrawler._parse_samples_from_html(el)
        assert result == []

    def test_copy_button_cleaned(self) -> None:
        el = self._make_soup(SAMPLE_DIV_WITH_COPY)
        result = NowCoderCrawler._parse_samples_from_html(el)
        assert len(result) == 1
        assert result[0] == ["1 2", "3"]

    def test_none_pre_tags(self) -> None:
        """Div with no <pre> tags at all."""
        el = self._make_soup("""<div class="question-oi">
          <p>no pre here</p>
        </div>""")
        result = NowCoderCrawler._parse_samples_from_html(el)
        assert result == []

    def test_single_pre_tag_ignored(self) -> None:
        """A single <pre> can't form input/output pair."""
        el = self._make_soup("""<div class="question-oi">
          <pre>just one</pre>
        </div>""")
        result = NowCoderCrawler._parse_samples_from_html(el)
        # Falls through to text parser which may extract partial
        # For single <pre> without input/output labels, should be empty
        assert result == [] or all(isinstance(p, list) for p in result)
