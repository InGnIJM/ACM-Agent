"""
AtCoder platform crawler.

Fetches problem statements, solutions, user profiles, and submission
records from the official AtCoder site (https://atcoder.jp).
Uses the kenkoooo.com merged-problems.json for tag-based problem listing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from typing import Dict, List, Optional

from crawlers.base import BaseCrawler, CrawlResult, CrawlerExecutor, DataImporter

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# AtCoderCrawler
# ──────────────────────────────────────────────


class AtCoderCrawler(BaseCrawler):
    """Crawler for AtCoder (https://atcoder.jp).

    Problem statements are scraped from the official site using
    ``fetch_with_fallback`` (HTTP -> browser fallback).  Problem lists
    by tag use the kenkoooo merged-problems.json endpoint.  User
    profiles and submission records are browser-based.
    """

    PLATFORM: str = "atcoder"

    # ── class constants ─────────────────────────────────────────

    BASE_URL: str = "https://atcoder.jp"
    KENKOO_API: str = "https://kenkoooo.com/atcoder"

    # Japanese section heading patterns in <h3> tags.
    # Ordered longest-first so 入力例/出力例 match before 入力/出力.
    _JAPANESE_HEADINGS: tuple = (
        "問題文", "制約", "入力例", "出力例", "入力", "出力",
    )

    # Title patterns that indicate a CDN/WAF block page rather than
    # a real AtCoder problem.  The crawler treats these as fetch
    # failures so the browser fallback (or retry) is triggered.
    _BLOCK_PAGE_TITLE_PATTERNS: tuple = (
        "ERROR: The request could not be satisfied",
        "Access Denied",
        "403 ERROR",
        "404 Not Found",
    )

    @staticmethod
    def _default_qps() -> float:
        return 3.0

    # ── kenkoooo caches ────────────────────────────────────────
    # Caching avoids re-downloading large JSON files (~900 KB total)
    # for every single fetch_problem call — a 100-problem batch would
    # otherwise make 300 HTTP requests instead of ~100.

    _contest_map: Optional[dict] = None       # problem_id -> contest_id
    _merged_problems: Optional[list] = None   # merged-problems.json cache
    _problem_models: Optional[dict] = None    # problem-models.json cache

    def _load_contest_map(self) -> dict:
        """Lazily load contest-problem.json mapping problem_id -> contest_id."""
        if self._contest_map is not None:
            return self._contest_map
        try:
            result = self._http_request(
                f"{self.KENKOO_API}/resources/contest-problem.json"
            )
            if result.success and isinstance(result.data, list):
                self._contest_map = {}
                for entry in result.data:
                    if isinstance(entry, dict):
                        pid = entry.get("problem_id", "")
                        cid = entry.get("contest_id", "")
                        if pid and cid:
                            self._contest_map[pid] = cid
                logger.info("Loaded %d contest-problem mappings", len(self._contest_map))
            else:
                self._contest_map = {}
        except Exception as exc:
            logger.warning("Failed to load contest-problem.json: %s", exc)
            self._contest_map = {}
        return self._contest_map

    def _load_merged_problems(self) -> list:
        """Lazily load merged-problems.json (cached)."""
        if self._merged_problems is not None:
            return self._merged_problems
        try:
            result = self._http_request(
                f"{self.KENKOO_API}/resources/merged-problems.json"
            )
            if result.success and isinstance(result.data, list):
                self._merged_problems = result.data
                logger.info("Loaded %d merged problems", len(self._merged_problems))
            else:
                # Don't cache invalid responses — let caller see the
                # raw data and report "Unexpected format" rather than
                # "Empty cache".
                logger.warning(
                    "merged-problems.json: unexpected format (type=%s)",
                    type(result.data).__name__,
                )
                return result.data if result.success else []
        except Exception as exc:
            logger.warning("Failed to load merged-problems.json: %s", exc)
            self._merged_problems = []
        return self._merged_problems

    def _load_problem_models(self) -> dict:
        """Lazily load problem-models.json (cached)."""
        if self._problem_models is not None:
            return self._problem_models
        try:
            result = self._http_request(
                f"{self.KENKOO_API}/resources/problem-models.json"
            )
            if result.success and isinstance(result.data, dict):
                self._problem_models = result.data
                logger.info("Loaded %d problem models", len(self._problem_models))
            else:
                self._problem_models = {}
        except Exception as exc:
            logger.warning("Failed to load problem-models.json: %s", exc)
            self._problem_models = {}
        return self._problem_models

    # ── helpers ─────────────────────────────────────────────────

    @staticmethod
    def _extract_html_text(page_result: CrawlResult) -> str:
        """Extract HTML string from a CrawlResult (browser or HTTP)."""
        data = page_result.data
        if isinstance(data, dict):
            return data.get("text", data.get("html", ""))
        if isinstance(data, str):
            return data
        return ""

    @staticmethod
    def _parse_problem_id(source_id: str) -> tuple:
        """Split ``\"abc400_a\"`` -> ``(\"abc400\", \"a\")``."""
        m = re.match(r"^([a-zA-Z]+\d+)_([a-z]\d*)$", source_id)
        if m:
            return m.group(1), m.group(2)
        parts = source_id.rsplit("_", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
        return "", source_id

    def _get_contest_id(self, problem_id: str) -> str:
        """Get the real AtCoder contest slug for a problem_id.

        Uses the kenkoooo contest-problem.json cache loaded via
        ``_http_request``. Falls back to parsing the problem_id.
        """
        cmap = self._load_contest_map()
        cid = cmap.get(problem_id, "")
        if cid:
            return cid
        # Fallback: try to parse from problem_id
        parsed, _ = self._parse_problem_id(problem_id)
        return parsed

    # ── KaTeX handling ──────────────────────────────────────────

    @staticmethod
    def _process_katex(soup_element) -> None:
        """Replace KaTeX elements with ``$...$`` or ``$$...$$`` LaTeX markup.

        Finds ``<annotation encoding="application/x-tex">`` inside
        KaTeX elements, extracts the LaTeX source, and replaces the
        outermost ``.katex`` wrapper.  Display math (``.katex-display``)
        is wrapped with ``$$``; inline math with ``$``.
        """
        annotations = soup_element.select(
            'annotation[encoding="application/x-tex"]'
        )
        # Track already-processed wrappers to avoid double-replacement
        seen_wrappers = set()

        for annotation in annotations:
            tex = annotation.get_text(strip=False).strip()
            if not tex:
                continue

            # Walk up to find the .katex wrapper.
            # .katex-display wraps .katex as an ancestor — we must keep
            # walking past .katex to detect display mode.
            el = annotation.parent
            is_display = False
            katex_wrapper = None
            while el is not None and el is not soup_element:
                if not hasattr(el, "get"):
                    el = el.parent
                    continue
                cls_val = el.get("class", "")
                if isinstance(cls_val, list):
                    classes = cls_val
                else:
                    classes = str(cls_val).split()
                if "katex-display" in classes:
                    is_display = True
                    katex_wrapper = el
                    break
                if "katex" in classes and katex_wrapper is None:
                    # Save as fallback; keep walking — .katex-display may
                    # be further up the ancestor chain.
                    katex_wrapper = el
                el = el.parent

            if katex_wrapper is None:
                # No katex wrapper found; just replace the annotation itself
                try:
                    annotation.replace_with(f"${tex}$")
                except Exception:
                    pass
                continue

            wrapper_id = id(katex_wrapper)
            if wrapper_id in seen_wrappers:
                continue
            seen_wrappers.add(wrapper_id)

            try:
                if is_display:
                    katex_wrapper.replace_with(f"$$\n{tex}\n$$")
                else:
                    katex_wrapper.replace_with(f"${tex}$")
            except Exception:
                pass

    @staticmethod
    def _process_images(soup_element) -> None:
        """Replace ``<img>`` tags with Markdown image syntax ``![](url)``."""
        for img in soup_element.find_all("img"):
            src = img.get("src", "")
            alt = img.get("alt", "image")
            if src:
                img.replace_with(f"![{alt}]({src})")

    @staticmethod
    def _unwind_inline(root_el) -> None:
        """Replace inline formatting elements (<var>, <code>, <b>, <i>,
        <em>, <strong>, <span>) with their text content so they don't cause
        spurious line breaks in get_text().  Also unwrap <a> links
        (keep text, drop href).

        For ``<var>`` tags, the content is wrapped in ``$...$`` first
        so that LaTeX expressions (e.g. ``N \\ K \\ T``, ``\\ldots``)
        render as math even when the page uses no KaTeX markup.

        For ``<code>`` tags, the content is wrapped in backticks first
        so it survives the later get_text() flattening as Markdown inline
        code (`` `x` ``). Without this, get_text("\\n") isolates the inner
        text on its own line — e.g. ``Yes`` / ``First`` / a bare ``-`` —
        which shatters sentences and lets a lone ``-`` trigger a Setext
        heading on the frontend. (Root cause A.)
        """
        from bs4 import NavigableString as _NS

        # Wrap <var> content in $...$ before unwrapping
        for var_el in root_el.find_all("var"):
            inner = var_el.get_text("", strip=True)
            if inner and "$" not in inner:
                var_el.clear()
                var_el.append(_NS(f"${inner}$"))

        # Wrap <code> content in backticks before unwrapping.
        # BUT skip <code> inside <pre> — those are code blocks, not
        # inline code; backticks would break the later <pre> handling.
        for code_el in root_el.find_all("code"):
            if code_el.find_parent("pre") is not None:
                continue
            inner = code_el.get_text("", strip=True)
            if inner and "`" not in inner:
                code_el.clear()
                code_el.append(_NS(f"`{inner}`"))

        inline_selectors = ("var", "code", "b", "i", "em", "strong", "span", "font")
        for sel in inline_selectors:
            for el in root_el.find_all(sel):
                el.unwrap()
        # Unwrap <a> tags (keep link text, drop URL)
        for a in root_el.find_all("a"):
            a.unwrap()

    @staticmethod
    def _process_lists(root_el) -> None:
        """Convert ``<ul>`` / ``<ol>`` lists into Markdown list items.

        get_text("\\n") flattens ``<li>`` into bare newline-separated
        lines (losing the ``- `` markers), so the frontend renders a list
        as one paragraph. Replacing the list with Markdown bullet text
        preserves the structure. Runs AFTER ``_unwind_inline`` so each
        ``<li>``'s inline ``<var>`` / ``<code>`` are already ``$…$`` /
        backtick text nodes. (Root cause B.)
        """
        from bs4 import NavigableString as _NS

        def _serialize(list_el, marker_fn) -> str:
            items = list_el.find_all("li", recursive=False)
            lines: List[str] = []
            for li in items:
                # get_text(strip=True) would strip EACH NavigableString's
                # leading/trailing whitespace — collapsing the space
                # between "$move$" and "is either `First`". Use separator=""
                # (no inter-node delimiter) + strip=False (preserve inner
                # spaces), then strip the whole assembled line once.
                # (Root cause A regression — inline spaces around <code>.)
                txt = li.get_text("", strip=False).strip()
                if txt:
                    lines.append(f"{marker_fn(len(lines) + 1)} {txt}")
            return "\n".join(lines)

        # Snapshot with list() because we mutate the tree while iterating.
        # Ordered lists first so a nested <ol> inside <ul> isn't skipped.
        for ol in list(root_el.find_all("ol")):
            body = _serialize(ol, lambda i: f"{i}.")
            ol.replace_with(_NS(f"\n{body}\n"))
        for ul in list(root_el.find_all("ul")):
            body = _serialize(ul, lambda _: "-")
            ul.replace_with(_NS(f"\n{body}\n"))

    @staticmethod
    def _process_tables(root_el) -> None:
        """Convert ``<table>`` into a Markdown pipe-table so interactive
        example tables survive ``get_text`` instead of being flattened to
        a content soup. Runs AFTER ``_unwind_inline`` so cell ``<code>`` /
        ``<var>`` are already backtick / ``$…$`` text. Cell-internal
        newlines collapse to spaces (a Markdown table cell can't wrap),
        and literal ``|`` is escaped so it doesn't break column parsing.
        """
        from bs4 import NavigableString as _NS

        for table in list(root_el.find_all("table")):
            md_rows: List[List[str]] = []
            for tr in table.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                row: List[str] = []
                for c in cells:
                    AtCoderCrawler._merge_adjacent_strings(c)
                    txt = c.get_text("", strip=False).strip()
                    txt = re.sub(r"\s+", " ", txt).replace("|", "\\|")
                    row.append(txt)
                if row:
                    md_rows.append(row)
            if not md_rows:
                table.replace_with(_NS(""))
                continue
            ncol = max(len(r) for r in md_rows)
            for r in md_rows:
                while len(r) < ncol:
                    r.append("")
            lines = ["| " + " | ".join(md_rows[0]) + " |"]
            lines.append("| " + " | ".join("---" for _ in range(ncol)) + " |")
            for r in md_rows[1:]:
                lines.append("| " + " | ".join(r) + " |")
            table.replace_with(_NS("\n\n" + "\n".join(lines) + "\n\n"))

    @staticmethod
    def _process_paragraphs(root_el) -> None:
        """Insert newline boundaries around block-level ``<p>`` elements.

        BeautifulSoup's get_text("\\n") joins adjacent <p> tags with only a
        single newline, which Markdown treats as a soft wrap — collapsing
        distinct paragraphs into one blob. Padding each block element with
        newline text nodes lets a blank line form between paragraphs.
        """
        from bs4 import NavigableString as _NS

        for block in list(root_el.find_all(["p", "blockquote"])):
            block.insert_before(_NS("\n"))
            block.insert_after(_NS("\n"))

    @staticmethod
    def _merge_adjacent_strings(root_el) -> None:
        """Merge adjacent NavigableString nodes so get_text("\\n") won't
        split unwrapped inline content into separate lines."""
        from bs4 import NavigableString as _NS
        walked = set()
        for el in root_el.descendants:
            if el in walked or not hasattr(el, "contents"):
                continue
            i = 0
            while i < len(el.contents) - 1:
                a, b = el.contents[i], el.contents[i + 1]
                if isinstance(a, _NS) and isinstance(b, _NS):
                    walked.add(a)
                    walked.add(b)
                    a.replace_with(_NS(str(a) + str(b)))
                    b.extract()
                else:
                    i += 1

    # ── section extraction ──────────────────────────────────────

    @staticmethod
    def _extract_sections(html: str) -> dict:
        """Parse AtCoder problem page into structured sections.

        Finds ``#task-statement > span.lang-en``, then splits content
        by ``<h3>`` headings to classify into: description, constraints,
        input_format, output_format, and samples.

        Returns a dict with keys:
            description, constraints, input_format, output_format, samples
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {}

        soup = BeautifulSoup(html, "html.parser")

        # Find the English task statement
        task_statement = soup.select_one("#task-statement")
        if not task_statement:
            return {}

        lang_en = task_statement.select_one("span.lang-en")
        if not lang_en:
            # Fallback: use the whole task-statement
            lang_en = task_statement

        # Pre-process: replace KaTeX math and images with Markdown
        AtCoderCrawler._process_katex(lang_en)
        AtCoderCrawler._process_images(lang_en)

        # Remove script/style elements
        for tag in lang_en.find_all(["script", "style"]):
            tag.decompose()

        # ── Split by <h3> tags ───────────────────────────────────
        lang_en_html = str(lang_en)
        parts = re.split(r"<h3[^>]*>", lang_en_html, flags=re.IGNORECASE)

        result: Dict[str, object] = {
            "description": "",
            "constraints": "",
            "input_format": "",
            "output_format": "",
            "samples": [],
        }

        # Section labels -> result key mapping
        # Include both English and Japanese headings for bilingual pages
        SECTION_MAP: Dict[str, str] = {
            "problem statement": "description",
            "problem": "description",
            "story": "description",
            "問題文": "description",  # Japanese: problem statement
            "constraints": "constraints",
            "constraint": "constraints",
            "制約": "constraints",  # Japanese: constraints
            "入力": "input_format",  # Japanese: input
            "output": "output_format",
            "input": "input_format",
            "input format": "input_format",
            "出力": "output_format",  # Japanese: output
            "output format": "output_format",
        }

        SAMPLE_INPUT_RE = re.compile(r"^Sample\s+Input\s+\d+$", re.IGNORECASE)
        SAMPLE_OUTPUT_RE = re.compile(r"^Sample\s+Output\s+\d+$", re.IGNORECASE)
        SAMPLE_RE = re.compile(r"^Sample\s+\d+$", re.IGNORECASE)

        sample_inputs: List[str] = []
        sample_outputs: List[str] = []
        # Parallel to sample_outputs: the explanation that follows the
        # answer <pre> in a Sample Output section (paragraphs / ASCII-art
        # diagrams / tables). Rendered by the frontend under "解释 #N".
        sample_notes: List[str] = []

        # Reusable HTML→markdown pipeline for a section's EXPLANATION body
        # (everything after the answer <pre> has been removed). Mirrors the
        # regular-section pipeline: inline tags unwrapped, lists/paragraphs
        # structured, <pre> split by math-bearing vs plain.
        def _section_to_markdown(soup) -> str:
            AtCoderCrawler._unwind_inline(soup)
            AtCoderCrawler._process_lists(soup)
            AtCoderCrawler._process_tables(soup)
            AtCoderCrawler._process_paragraphs(soup)
            for pre in soup.find_all("pre"):
                AtCoderCrawler._merge_adjacent_strings(pre)
                pre_text = pre.get_text()
                if "$" in pre_text:
                    pre.replace_with(f"\n{pre_text.strip()}\n")
                else:
                    pre.replace_with(f"\n```\n{pre_text}\n```\n")
            AtCoderCrawler._merge_adjacent_strings(soup)
            return AtCoderCrawler._normalize_text(soup.get_text("\n", strip=True))

        # Track if we found an empty Problem Statement section
        # In some problems, the Problem Statement heading is followed
        # immediately by another heading with no content in between.
        # In that case, we should use the next non-empty section as description.
        _empty_problem_statement = False

        for idx, part in enumerate(parts):
            if idx == 0:
                # Content before the first <h3> — often empty or a lead-in
                continue

            # Split at the first </h3> to get heading text and body
            m = re.match(r"(.*?)</h3>(.*)", part, re.DOTALL | re.IGNORECASE)
            if not m:
                continue

            heading_text = BeautifulSoup(m.group(1), "html.parser").get_text(
                strip=True
            )
            section_html = m.group(2)

            if not heading_text:
                continue

            # ── Check if this is a sample heading ─────────────────
            if SAMPLE_INPUT_RE.match(heading_text):
                section_soup = BeautifulSoup(section_html, "html.parser")
                # Only the FIRST <pre> is the sample input; later <pre>
                # blocks belong to explanation paragraphs (e.g. ASCII-art
                # diagrams) and must NOT be merged into the answer.
                first_pre = section_soup.find("pre")
                if first_pre is not None:
                    sample_inputs.append(first_pre.get_text("\n", strip=False))
                else:
                    sample_inputs.append(section_soup.get_text("\n", strip=True))
                # notes come only from the Sample Output section (where the
                # explanation lives) and are index-aligned with outputs.
                continue

            if SAMPLE_OUTPUT_RE.match(heading_text):
                section_soup = BeautifulSoup(section_html, "html.parser")
                # See SAMPLE_INPUT_RE branch: only the first <pre>.
                first_pre = section_soup.find("pre")
                if first_pre is not None:
                    sample_outputs.append(first_pre.get_text("\n", strip=False))
                    # Root cause D: the explanation that follows the answer
                    # <pre> (paragraphs / ASCII-art <pre> / tables) was
                    # being thrown away. Extract it as the sample NOTE so
                    # the frontend can render it under "解释 #N". Remove
                    # the answer <pre> first, then run the same pipeline.
                    first_pre.extract()
                    note = _section_to_markdown(section_soup)
                else:
                    sample_outputs.append(section_soup.get_text("\n", strip=True))
                    note = ""
                sample_notes.append(note)
                continue

            if SAMPLE_RE.match(heading_text):
                # "Sample 1" style — may contain both input and output <pre> blocks
                section_soup = BeautifulSoup(section_html, "html.parser")
                pres = section_soup.find_all("pre")
                if len(pres) >= 2:
                    sample_inputs.append(
                        pres[0].get_text("\n", strip=False)
                    )
                    sample_outputs.append(
                        pres[1].get_text("\n", strip=False)
                    )
                    sample_notes.append("")
                continue

            # ── Classify regular section ──────────────────────────
            heading_lower = heading_text.lower().strip()
            section_key = None
            for label, key in SECTION_MAP.items():
                if heading_lower == label or heading_lower.startswith(
                    label + " "
                ):
                    section_key = key
                    break

            if section_key:
                section_soup = BeautifulSoup(section_html, "html.parser")
                AtCoderCrawler._process_katex(section_soup)
                AtCoderCrawler._process_images(section_soup)
                # Unwrap inline tags FIRST (wraps <var> in $…$ and <code>
                # in backticks) before <pre> replacement extracts text.
                AtCoderCrawler._unwind_inline(section_soup)
                # Lists → Markdown bullets, paragraphs → blank-line
                # separated, tables → pipe-tables, so get_text()
                # preserves structure.
                AtCoderCrawler._process_lists(section_soup)
                AtCoderCrawler._process_tables(section_soup)
                AtCoderCrawler._process_paragraphs(section_soup)
                # Preserve <pre> formatting: replace each <pre> with its
                # text. Root cause C — AtCoder input/output-format <pre>
                # blocks contain <var> math (already turned into $…$ by
                # _unwind_inline). A ``` fence would hide that LaTeX (code
                # blocks don't run math), so keep math-bearing <pre> as a
                # plain text block; only plain-text <pre> (sample preview /
                # ASCII art) stays fenced.
                for pre in section_soup.find_all("pre"):
                    AtCoderCrawler._merge_adjacent_strings(pre)
                    pre_text = pre.get_text()
                    if "$" in pre_text:
                        pre.replace_with(f"\n{pre_text.strip()}\n")
                    else:
                        pre.replace_with(f"\n```\n{pre_text}\n```\n")
                AtCoderCrawler._merge_adjacent_strings(section_soup)
                text = section_soup.get_text("\n", strip=True)
                text = AtCoderCrawler._normalize_text(text)
                # Only add non-empty sections
                if text:
                    existing = result.get(section_key, "")
                    if isinstance(existing, str) and existing:
                        result[section_key] = existing + "\n\n" + text
                    else:
                        result[section_key] = text
                    # Reset empty problem statement flag if we found content
                    if section_key == "description":
                        _empty_problem_statement = False
                elif section_key == "description":
                    # Mark that we found an empty Problem Statement section
                    _empty_problem_statement = True

        # ── Handle empty Problem Statement ─────────────────────────
        # If Problem Statement section was empty, try to find description
        # from the next non-empty section that looks like content
        if _empty_problem_statement and not result.get("description"):
            # Look for content in the next section after Problem Statement
            # This handles cases where Problem Statement heading is followed
            # immediately by another heading with the actual content
            for idx, part in enumerate(parts):
                if idx == 0:
                    continue
                m = re.match(r"(.*?)</h3>(.*)", part, re.DOTALL | re.IGNORECASE)
                if not m:
                    continue
                heading_text = BeautifulSoup(m.group(1), "html.parser").get_text(strip=True)
                section_html = m.group(2)
                # Skip sample sections
                if SAMPLE_INPUT_RE.match(heading_text) or SAMPLE_OUTPUT_RE.match(heading_text) or SAMPLE_RE.match(heading_text):
                    continue
                # Check if this section has content
                section_soup = BeautifulSoup(section_html, "html.parser")
                text = section_soup.get_text(strip=True)
                if text and len(text) > 20:
                    # This looks like it could be the problem description
                    AtCoderCrawler._process_katex(section_soup)
                    AtCoderCrawler._process_images(section_soup)
                    AtCoderCrawler._unwind_inline(section_soup)
                    AtCoderCrawler._process_lists(section_soup)
                    AtCoderCrawler._process_tables(section_soup)
                    AtCoderCrawler._process_paragraphs(section_soup)
                    for pre in section_soup.find_all("pre"):
                        AtCoderCrawler._merge_adjacent_strings(pre)
                        pre_text = pre.get_text()
                        if "$" in pre_text:
                            pre.replace_with(f"\n{pre_text.strip()}\n")
                        else:
                            pre.replace_with(f"\n```\n{pre_text}\n```\n")
                    AtCoderCrawler._merge_adjacent_strings(section_soup)
                    text = section_soup.get_text("\n", strip=True)
                    text = AtCoderCrawler._normalize_text(text)
                    if text:
                        result["description"] = text
                        break

        # ── Pair sample inputs / outputs / notes ────────────────
        # notes align with sample_outputs (explanations live in the
        # Sample Output section). If input/output counts diverge, the
        # shorter side gets an empty slot.
        samples: list = []
        max_len = max(
            len(sample_inputs), len(sample_outputs), len(sample_notes)
        )
        for i in range(max_len):
            inp = sample_inputs[i] if i < len(sample_inputs) else ""
            out = sample_outputs[i] if i < len(sample_outputs) else ""
            note = sample_notes[i] if i < len(sample_notes) else ""
            samples.append(
                [
                    AtCoderCrawler._normalize_text(inp),
                    AtCoderCrawler._normalize_text(out),
                    note,
                ]
            )

        result["samples"] = samples

        return result

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize whitespace in extracted text.

        Applies ``html.unescape``, collapses blank lines, normalizes
        horizontal whitespace while preserving newlines.
        """
        import html as _html

        text = _html.unescape(text)
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"\n[ \t]+\n", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = AtCoderCrawler._wrap_latex(text)
        return text.strip()

    @staticmethod
    def _wrap_latex(text: str) -> str:
        """Wrap bare LaTeX commands / subscripts that escaped <var> handling
        in ``$...$`` delimiters.  Most cases are handled by ``_unwind_inline``
        which wraps ``<var>`` content before unwrapping."""
        # Already has $ delimiters — skip
        if "$" in text:
            return text
        # Wrap \ldots, \dots, \  (backslash-space), and similar bare commands.
        # The \  (backslash + whitespace) is AtCoder's math spacing — wrap
        # any backslash followed by one letter or whitespace.
        text = re.sub(
            r"(\\[a-zA-Z\s](?:\{[^}]*\})*)",
            r"$\g<1>$",
            text,
        )
        # Wrap isolated subscripts/superscripts: A_i, x^{2}
        text = re.sub(
            r"([A-Za-z0-9]+[_^]\s*(?:\{[^}]*\}|[A-Za-z0-9]+))",
            r"$\g<1>$",
            text,
        )
        return text

    # ── abstract method implementations ─────────────────────────

    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Fetch problem metadata + full HTML statement.

        Parses *source_id* like ``"abc400_a"`` into contest_id + index,
        fetches ``/contests/{contest_id}/tasks/{source_id}``, and
        extracts structured content via :meth:`_extract_sections`.

        Args:
            source_id: AtCoder problem ID (e.g. ``"abc400_a"``).

        Returns:
            CrawlResult with problem dict including ``description``,
            ``constraints``, ``input_format``, ``output_format``,
            ``samples``, and ``source_url``.
        """
        # Use the kenkoooo cache to get the CORRECT contest slug
        # (e.g. "1202Contest_a" -> contest_id="DEGwer2023", not "1202Contest")
        contest_id = self._get_contest_id(source_id)
        if not contest_id:
            return CrawlResult(
                success=False,
                error=f"Cannot determine contest for problem ID: {source_id}",
                source="http",
            )
        # Also extract index for metadata
        _, index = self._parse_problem_id(source_id)

        problem_url = (
            f"{self.BASE_URL}/contests/{contest_id}/tasks/{source_id}"
        )
        logger.debug("AtCoder fetching problem page: %s", problem_url)

        page_result = self.fetch_with_fallback(problem_url)
        if not page_result.success:
            return page_result

        html = self._extract_html_text(page_result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response from AtCoder problem page",
                source=page_result.source,
                retry_count=page_result.retry_count,
            )

        # ── Japanese statement detection (BEFORE section extraction) ──
        # Check #task-statement: skip if only Japanese content.
        # Three cases (with h3 heading check as sub-case of case 1):
        #   1. No spans at all (old contests) → h3 headings → CJK fallback
        #   2. lang-ja exists but no lang-en → skip
        #   3. Both exist but lang-en is empty/short → skip
        #
        # Exception: dp/tdpc problems are always allowed — they are
        # well-known educational problems that users specifically seek
        # out, even though they are Japanese-only.
        # abc/arc problems are also allowed — older problems may be
        # Japanese-only but _extract_sections can still parse them.
        _is_dp_tdpc = source_id.startswith(("dp_", "tdpc_"))
        _skip_japanese = not _is_dp_tdpc
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return CrawlResult(
                success=False,
                error="BeautifulSoup not available",
                source="http",
            )
        _ts = BeautifulSoup(html, "html.parser").select_one("#task-statement")
        if _ts and _skip_japanese:
            _lang_en = _ts.select_one("span.lang-en")
            _lang_ja = _ts.select_one("span.lang-ja")
            if not _lang_en and not _lang_ja:
                # Old-style page: no language spans.
                # First check h3 headings for Japanese section text
                # (問題文/制約/入力/出力 etc.) — a content-level check
                # that catches Japanese pages regardless of missing spans.
                for _h3 in _ts.find_all("h3"):
                    _h3_text = _h3.get_text(strip=True)
                    if any(
                        _jp in _h3_text
                        for _jp in self._JAPANESE_HEADINGS
                    ):
                        return CrawlResult(
                            success=False,
                            error=(
                                f"Problem '{source_id}' has Japanese "
                                f"section headings "
                                f"(問題文/制約/入力/出力), skipping"
                            ),
                            source=page_result.source,
                        )
                # CJK fallback — check if the content is Japanese by
                # looking for CJK characters + Japanese-specific patterns.
                _ts_text = _ts.get_text()
                _has_cjk = bool(re.search(r'[぀-ヿ一-鿿]', _ts_text))
                _has_eng = bool(re.search(
                    r'\b(Problem|Constraints?|Input|Output|Sample)\b',
                    _ts_text, re.IGNORECASE,
                ))
                # Calculate CJK ratio to detect mixed content
                # where h3 tags are English but body is Japanese
                _cjk_chars = len(re.findall(r'[぀-呣一-鿿]', _ts_text))
                _total_chars = len(_ts_text.strip())
                _cjk_ratio = _cjk_chars / _total_chars if _total_chars > 0 else 0
                # Use 15% threshold to catch more Japanese content
                if _has_cjk and (not _has_eng or _cjk_ratio > 0.15):
                    return CrawlResult(
                        success=False,
                        error=(
                            f"Problem '{source_id}' has Japanese-only "
                            f"statement (old-style, no lang spans), skipping"
                        ),
                        source=page_result.source,
                    )
            elif not _lang_en and _lang_ja:
                return CrawlResult(
                    success=False,
                    error=(
                        f"Problem '{source_id}' has Japanese-only "
                        f"statement (no lang-en), skipping"
                    ),
                    source=page_result.source,
                )
            elif _lang_en and _lang_ja:
                _en_text = _lang_en.get_text(strip=True)
                if not _en_text or len(_en_text) < 20:
                    return CrawlResult(
                        success=False,
                        error=(
                            f"Problem '{source_id}' English section "
                            f"is empty/too short, skipping"
                        ),
                        source=page_result.source,
                    )

        # Extract sections
        sections = self._extract_sections(html)

        # Try to get a clean title from the page
        try:
            from bs4 import BeautifulSoup

            title_soup = BeautifulSoup(html, "html.parser")
            title_tag = title_soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else source_id
            # Strip "ContestName - " prefix if present
            if " - " in title:
                _, _, title = title.partition(" - ")
            import html as _html

            title = _html.unescape(title)
        except Exception:
            title = source_id

        # ── CDN / WAF block-page detection ──────────────────────────
        # CloudFront / AWS WAF sometimes returns a 200-block-page
        # whose <title> says "ERROR: The request could not be
        # satisfied".  The HTTP layer treats it as success, so
        # fetch_with_fallback never escalates to the browser.
        # Detect this here and force a browser-only retry.
        _is_block_title = any(
            pat in title for pat in self._BLOCK_PAGE_TITLE_PATTERNS
        )
        _has_content = bool(
            sections.get("description")
            or sections.get("constraints")
            or sections.get("input_format")
        )
        if _is_block_title and not _has_content:
            if page_result.source == "browser":
                # Already tried browser — give up.
                return CrawlResult(
                    success=False,
                    error=(
                        f"Block page detected (title='{title}') "
                        f"even after browser fallback"
                    ),
                    source="browser",
                )
            logger.warning(
                "Block-page title detected (title=%r), forcing browser retry for %s",
                title,
                problem_url,
            )
            browser_result = self._browser_request(problem_url)
            if not browser_result.success:
                return browser_result
            html2 = self._extract_html_text(browser_result)
            if not html2:
                return CrawlResult(
                    success=False,
                    error="Empty browser response after block-page retry",
                    source="browser",
                )
            sections = self._extract_sections(html2)
            # Re-extract title from browser page
            try:
                title_soup2 = BeautifulSoup(html2, "html.parser")
                title_tag2 = title_soup2.find("title")
                title = title_tag2.get_text(strip=True) if title_tag2 else source_id
                if " - " in title:
                    _, _, title = title.partition(" - ")
                import html as _html2
                title = _html2.unescape(title)
            except Exception:
                title = source_id
            page_result = browser_result  # update page_result for downstream metadata

            # Double-check: if browser also returned a block page, fail.
            _is_block_title2 = any(
                pat in title for pat in self._BLOCK_PAGE_TITLE_PATTERNS
            )
            _has_content2 = bool(
                sections.get("description")
                or sections.get("constraints")
                or sections.get("input_format")
            )
            if _is_block_title2 and not _has_content2:
                return CrawlResult(
                    success=False,
                    error=(
                        f"Block page detected (title='{title}') "
                        f"even after browser fallback"
                    ),
                    source="browser",
                )

        # ── Ensure constraints is extracted ──────────────────────────
        if not sections.get("constraints"):
            constraint_match = re.search(
                r'<h3[^>]*>\s*(?:Constraints|Constraint)\s*</h3>\s*(.*?)(?=<h3[^>]*>|$)',
                html,
                re.DOTALL | re.IGNORECASE,
            )
            if constraint_match:
                try:
                    from bs4 import BeautifulSoup

                    c_soup = BeautifulSoup(
                        constraint_match.group(1), "html.parser"
                    )
                    self._process_katex(c_soup)
                    self._process_images(c_soup)
                    self._unwind_inline(c_soup)
                    self._process_lists(c_soup)
                    self._process_paragraphs(c_soup)
                    c_text = c_soup.get_text("\n", strip=True)
                    sections["constraints"] = self._normalize_text(c_text)
                except Exception:
                    pass

        # ── Build base data dict ────────────────────────────────────
        data_dict: Dict[str, object] = {
            "source_id": source_id,
            "contest_id": contest_id,
            "index": index,
            "title": title,
            "description": sections.get("description", ""),
            "constraints": sections.get("constraints", ""),
            "input_format": sections.get("input_format", ""),
            "output_format": sections.get("output_format", ""),
            "samples": sections.get("samples", []),
            "source_url": problem_url,
        }

        # ── Attach kenkoooo metadata (cached) ──────────────────────
        try:
            for p in self._load_merged_problems():
                if isinstance(p, dict) and p.get("id") == source_id:
                    if "point" in p and p["point"] is not None:
                        data_dict["point"] = p["point"]
                    if "solver_count" in p:
                        data_dict["solver_count"] = p["solver_count"]
                    break
        except Exception:
            pass

        # ── Attach difficulty from problem-models (cached) ─────────
        try:
            model = self._load_problem_models().get(source_id)
            if isinstance(model, dict) and "difficulty" in model:
                data_dict["difficulty"] = model["difficulty"]
        except Exception:
            pass

        # ── Extract tags ────────────────────────────────────────────
        # NOTE: AtCoder does NOT provide algorithm tags (dp, graph,
        # greedy, etc.) on its official pages.  Only contest-type prefix
        # tags are available, derived from the contest_id (e.g.
        # "abc300" → "abc", "arc180" → "arc", "agc065" → "agc").
        #
        # The kenkoooo AtCoder Problems API (merged-problems.json /
        # problem-models.json) also does NOT expose algorithm tags
        # (difficulty ratings are available and consumed above).
        #
        # If algorithm tags are needed in the future, options include:
        #  1. LLM-based auto-tagging from problem description
        #  2. Community-curated tag lists (no stable public endpoint)
        #  3. Cross-referencing against other problem databases
        tags: List[str] = []
        if contest_id:
            prefix_match = re.match(r"^([a-zA-Z]+)\d", contest_id)
            if prefix_match:
                tag = prefix_match.group(1).lower()
                if tag not in tags:
                    tags.append(tag)
        if tags:
            data_dict["tags"] = tags

        return CrawlResult(
            success=True,
            data=data_dict,
            source=page_result.source,
            retry_count=page_result.retry_count,
        )

    def fetch_solutions(
        self, source_id: str, max_editorials: int = 5
    ) -> CrawlResult:
        """Fetch solution / editorial content for an AtCoder problem.

        AtCoder editorials have a 3-level structure:
          1. Problem page → link to editorial index
          2. Editorial index (/contests/{contest}/editorial) → links to
             per-problem editorial pages
          3. Per-problem editorial (/contests/{contest}/editorial/{id})
             → actual solution content

        Args:
            source_id: Problem identifier (e.g. ``"abc400_a"``).
            max_editorials: Maximum editorial pages to try.

        Returns:
            CrawlResult whose ``data`` is a list of solution dicts
            with ``author``, ``content``, ``title``, ``vote_count``.
        """
        contest_id = self._get_contest_id(source_id)
        if not contest_id:
            return CrawlResult(
                success=False,
                error=f"Cannot determine contest for problem ID: {source_id}",
                source="http",
            )

        # Parse problem index (e.g. "abc400_a" → "a")
        _, index = self._parse_problem_id(source_id)
        index_lower = index.lower()
        index_upper = index.upper()

        # ── Step 1: fetch the editorial index page ──────────────
        editorial_url = f"{self.BASE_URL}/contests/{contest_id}/editorial"
        logger.debug("AtCoder fetching editorial index: %s", editorial_url)

        page_result = self.fetch_with_fallback(editorial_url)
        if not page_result.success:
            return page_result

        html = self._extract_html_text(page_result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty editorial page",
                source="http",
            )

        try:
            from bs4 import BeautifulSoup, Tag
        except ImportError:
            return CrawlResult(success=True, data=[], source="http")

        import html as _html
        import re as _re

        soup = BeautifulSoup(html, "html.parser")
        solutions: list = []

        # ── Step 2: group editorial links per problem ───────────
        # The index page lists problems as:
        #   <h4>A - Problem Name</h4>
        #   <a href=".../editorial/123">解説</a> (Japanese)
        #   <a href=".../editorial/456">Editorial</a> (English)
        #
        # Group editorial links under their preceding problem heading.
        # prob_editorials: English only.  prob_all_editorials: any language.
        prob_editorials: dict[str, str] = {}  # letter → english_url
        prob_all_editorials: dict[str, str] = {}  # letter → any_url
        current_letter: str | None = None

        for tag in soup.find_all(["h2", "h3", "h4", "a"]):
            if tag.name in ("h2", "h3", "h4"):
                tag_text = tag.get_text(strip=True)
                m = _re.match(r"([A-Z])\d*\s*[-–—]", tag_text)
                if m:
                    current_letter = m.group(1).upper()
            elif tag.name == "a" and current_letter:
                href = tag.get("href", "")
                if _re.search(
                    rf"/contests/{_re.escape(contest_id)}/editorial/\d+",
                    href,
                ):
                    link_text = tag.get_text(strip=True)
                    full_url = (
                        f"{self.BASE_URL}{href}"
                        if href.startswith("/") else href
                    )
                    # Track first-seen link for this letter as fallback
                    if current_letter not in prob_all_editorials:
                        prob_all_editorials[current_letter] = full_url
                    # "Editorial" / "English" = English
                    if link_text.lower() in ("editorial", "english"):
                        prob_editorials[current_letter] = full_url

        logger.debug(
            "Found English editorials for problems: %s",
            ", ".join(sorted(prob_editorials.keys())),
        )

        # ── Step 3: pick links for the target problem ──────────
        # Prefer English; fall back to any-language for the SAME letter.
        # NEVER add editorial links from other problems — that was the
        # root cause of wrong-Japanese-content-for-wrong-problem bugs.
        target_links: list[str] = []
        if index_upper in prob_editorials:
            target_links.append(prob_editorials[index_upper])
        elif index_upper in prob_all_editorials:
            target_links.append(prob_all_editorials[index_upper])

        target_links = target_links[:max_editorials]

        # ── Step 4: fetch per-problem editorial content ─────────
        for link in target_links[:max_editorials]:
            # AtCoder editorial content is JavaScript-rendered (like CF).
            # Use Accept-Language header for English; do NOT append
            # ?lang=en (it can break the editorial page's language
            # detection and serve Japanese instead).
            logger.debug("AtCoder fetching per-problem editorial: %s", link)
            ed_html = None
            # Try browser rendering
            try:
                from scrapling.fetchers import StealthyFetcher
                proxy = getattr(type(self), '_scrapling_proxy', None)
                if proxy:
                    StealthyFetcher.proxy = proxy
                page = StealthyFetcher.fetch(
                    link, headless=True, network_idle=True,
                    timeout=15_000,
                    headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                ed_html = (
                    page.html_content if hasattr(page, 'html_content')
                    else page.body.decode('utf-8', errors='replace')
                )
            except Exception:
                pass
            # Fallback: plain HTTP
            if not ed_html:
                ed_result = self.fetch_with_fallback(link)
                if not ed_result.success:
                    continue
                ed_html = self._extract_html_text(ed_result)
            if not ed_html:
                continue

            ed_soup = BeautifulSoup(ed_html, "html.parser")

            # AtCoder editorial pages: the first .col-sm-12 is the nav
            # header; the second (or later) .col-sm-12 contains the
            # actual editorial body.  Browser-rendered pages may also
            # have .lang-en > .part wrappers.
            content_area = ed_soup.select_one(
                ".lang-en .part, .part, .editorial-content, "
                "article, main, #task-statement"
            )
            if not content_area:
                # Try the second .col-sm-12 (first is navigation)
                cols = ed_soup.select(".col-sm-12")
                if len(cols) >= 2:
                    content_area = cols[1]
                else:
                    content_area = cols[0] if cols else ed_soup

            # Remove navigation/header/sidebar
            for sel in (
                "script", "style", "nav", "footer", "header",
                "#contest-nav-tabs", ".contest-duration",
                ".pull-right", ".sidebox", ".col-sm-4",
                ".hidden-xs", ".a2a_kit",
                ".div-btn-copy", ".btn-copy",  # "Copy" button
                ".monaco-editor",  # Monaco editor (JS code viewer)
                ".prettyprint", ".prettyprinted",  # code blocks with line numbers (clean copy <pre> preferred)
            ):
                for el in content_area.select(sel):
                    el.decompose()

            # Clean KaTeX and images
            self._process_katex(content_area)
            self._process_images(content_area)

            # Apply HTML processing pipeline BEFORE text extraction so
            # <p> boundaries, lists, tables, and inline formatting survive.
            self._unwind_inline(content_area)
            self._process_lists(content_area)
            self._process_tables(content_area)
            self._process_paragraphs(content_area)
            # Handle <pre> code blocks (math-bearing → plain; else → ```fenced).
            # Skip hidden <pre> blocks (AtCoder has display:none fallback).
            for pre in content_area.find_all("pre"):
                style = pre.get("style", "")
                if "display:none" in style.replace(" ", "").lower():
                    pre.decompose()
                    continue
                self._merge_adjacent_strings(pre)
                pre_text = pre.get_text()
                if "$" in pre_text:
                    pre.replace_with(f"\n{pre_text.strip()}\n")
                else:
                    pre.replace_with(f"\n```\n{pre_text}\n```\n")
                self._merge_adjacent_strings(pre)
                pre_text = pre.get_text()
                if "$" in pre_text:
                    pre.replace_with(f"\n{pre_text.strip()}\n")
                else:
                    pre.replace_with(f"\n```\n{pre_text}\n```\n")

            # Try to extract problem-specific section by heading.
            # Per-problem editorial pages typically don't have per-letter
            # headings — the whole page IS the editorial for one problem.
            # This path is for multi-problem editorial index pages.
            prob_heading_re = _re.compile(
                rf"^(?:Task\s*)?{_re.escape(index_upper)}[\.\s\-:：]",
                _re.IGNORECASE,
            )
            found_text = ""
            _is_heading_path = False
            for tag in content_area.find_all(["h2", "h3", "h4"]):
                tag_text = tag.get_text(strip=True)
                if not prob_heading_re.match(tag_text):
                    continue
                # Collect sibling HTML up to the next heading, build a
                # mini-soup, and run the full HTML pipeline on it — so
                # paragraph breaks, lists, and code blocks survive.
                parts_html: list[str] = [str(tag)]  # include heading itself
                sibling = tag.next_sibling
                while sibling is not None:
                    if hasattr(sibling, "name") and sibling.name in (
                        "h2", "h3", "h4",
                    ):
                        break
                    parts_html.append(str(sibling))
                    sibling = sibling.next_sibling
                section_html = "".join(parts_html)
                section_soup = BeautifulSoup(section_html, "html.parser")
                self._process_katex(section_soup)
                self._process_images(section_soup)
                self._unwind_inline(section_soup)
                self._process_lists(section_soup)
                self._process_tables(section_soup)
                self._process_paragraphs(section_soup)
                for pre in section_soup.find_all("pre"):
                    self._merge_adjacent_strings(pre)
                    pre_text = pre.get_text()
                    if "$" in pre_text:
                        pre.replace_with(f"\n{pre_text.strip()}\n")
                    else:
                        pre.replace_with(f"\n```\n{pre_text}\n```\n")
                self._merge_adjacent_strings(section_soup)
                found_text = section_soup.get_text("\n", strip=False).strip()
                _is_heading_path = True
                break

            # If no problem-specific heading, use the full content area
            if not found_text:
                self._merge_adjacent_strings(content_area)
                # IMPORTANT: strip=False, then manual .strip() — strip=True
                # strips the \n NavigableString nodes inserted by
                # _process_paragraphs, collapsing all paragraph breaks.
                found_text = content_area.get_text("\n", strip=False).strip()
            else:
                # Heading-match path: rebuild from collected siblings so
                # the HTML pipeline (lists, paragraphs, <pre>) applies.
                # Sibling iteration with per-sibling get_text(strip=True)
                # silently loses paragraph breaks from _process_paragraphs.
                pass  # heading text is already in the first part; just unescape+normalize
                # Strip common header noise (author avatar, "Official" label, etc.)
                found_text = _re.sub(
                    r'^.*?Contest Duration:.*?(\n[A-Z][a-z].*?Editorial)',
                    r'\1', found_text, count=1, flags=_re.DOTALL,
                )
                # Also strip leading "Official\n\n" if present
                found_text = _re.sub(
                    r'^Official\s*\n+', '', found_text, count=1,
                )
                # Strip author line: "\n\nby ![image](...)username\n\n" → "\n\n"
                found_text = _re.sub(
                    r'\n\nby\s+!\[image\]\([^)]+\)\S*\s*\n\n',
                    '\n\n', found_text, count=1,
                )

            found_text = _html.unescape(found_text)
            found_text = self._normalize_text(found_text)

            # Strip header noise common to AtCoder editorial pages:
            #   Official:  "X - Problem Name\n\nby avatar username\n\n"
            #   User:      "B16 - Frog 1 Editorial\n\nby avatar iastm\n\n"
            found_text = _re.sub(
                r'^\s*(?:Official\s*\n+)?'
                r'(?:[A-Z]\d*\s*[-–—−–—]\s*.+?\n\n)?'
                r'\s*by\s+!\[image\]\([^)]+\)\S*\s*\n+',
                '', found_text, count=1,
            )
            # User-editorial variant: "B16 - Frog 1 Editorial\n\n by avatar iastm\n\n"
            found_text = _re.sub(
                r'^[A-Z]\d+\s*[-–—−–—]\s*.+?(?:Editorial|题解|解説)\s*\n+'
                r'\s*by\s+!\[image\]\([^)]+\)\S*\s*\n+',
                '', found_text, count=1,
            )

            if len(found_text) > 50:
                solutions.append({
                    "author": "AtCoder Editorial",
                    "title": f"{source_id} Solution",
                    "content": found_text,
                    "vote_count": 0,
                })
                break  # Found the solution for this problem

        # ── Step 5: fallback — Strategy A on index page ─────────
        if not solutions:
            main_content = soup.select_one(
                ".editorial-content, .part, #main-container .container, "
                ".col-sm-12, .row"
            ) or soup

            prob_heading_re = _re.compile(
                rf"^(?:Task\s*)?{_re.escape(index_upper)}[\.\s\-:：]",
                _re.IGNORECASE,
            )
            for tag in main_content.find_all(["h2", "h3", "h4"]):
                tag_text = tag.get_text(strip=True)
                if not prob_heading_re.match(tag_text):
                    continue
                parts: list[str] = []
                sibling = tag.next_sibling
                while sibling is not None:
                    if hasattr(sibling, "name") and sibling.name in (
                        "h2", "h3", "h4",
                    ):
                        break
                    parts.append(str(sibling))
                    sibling = sibling.next_sibling
                section_html = "".join(parts)
                section_soup = BeautifulSoup(section_html, "html.parser")
                self._process_katex(section_soup)
                self._process_images(section_soup)
                # Apply HTML pipeline so paragraph/lists survive
                self._unwind_inline(section_soup)
                self._process_lists(section_soup)
                self._process_tables(section_soup)
                self._process_paragraphs(section_soup)
                self._merge_adjacent_strings(section_soup)
                text = section_soup.get_text("\n", strip=False).strip()
                text = _html.unescape(text)
                text = self._normalize_text(text)
                if len(text) > 50:
                    solutions.append({
                        "author": "AtCoder Editorial",
                        "title": tag_text,
                        "content": text,
                        "vote_count": 0,
                    })
                break

        # ── Step 6: fallback — editorial link on problem page ──
        # Some contests (tessoku-book / dp / tdpc) have a nested
        # editorial structure:
        #   problem page → /tasks/{id}/editorial → User Editorial link
        # The problem page has a "题解" / "Editorial" button that
        # points to a task-level hub listing user editorials.
        if not solutions:
            problem_url = (
                f"{self.BASE_URL}/contests/{contest_id}/tasks/{source_id}"
            )
            logger.debug("AtCoder trying problem-page editorial: %s", problem_url)
            prob_result = self.fetch_with_fallback(problem_url)
            if prob_result.success:
                prob_html = self._extract_html_text(prob_result)
                prob_soup = BeautifulSoup(prob_html, "html.parser")
                # Find the editorial button on the problem page
                task_ed_url: str | None = None
                for a in prob_soup.find_all("a", href=True):
                    href = a.get("href", "")
                    txt = a.get_text(strip=True)
                    if txt in ("Editorial", "题解", "解説") and f"/tasks/{source_id}/editorial" in href:
                        task_ed_url = (
                            f"{self.BASE_URL}{href}"
                            if href.startswith("/") else href
                        )
                        break
                if task_ed_url:
                    logger.debug(
                        "Found task editorial hub: %s", task_ed_url,
                    )
                    hub_result = self.fetch_with_fallback(task_ed_url)
                    if hub_result.success:
                        hub_html = self._extract_html_text(hub_result)
                        hub_soup = BeautifulSoup(hub_html, "html.parser")
                        # Collect user editorial links
                        user_ed_urls: list[str] = []
                        for a in hub_soup.find_all("a", href=True):
                            href = a.get("href", "")
                            txt = a.get_text(strip=True)
                            if txt in ("User Editorial", "Editorial") and _re.search(
                                rf"/contests/{_re.escape(contest_id)}/editorial/\d+",
                                href,
                            ):
                                full_url = (
                                    f"{self.BASE_URL}{href}"
                                    if href.startswith("/") else href
                                )
                                if full_url not in user_ed_urls:
                                    user_ed_urls.append(full_url)
                        # Fetch each user editorial (reuse Step 4 logic)
                        for ed_url in user_ed_urls[:max_editorials]:
                            logger.debug(
                                "AtCoder fetching user editorial: %s", ed_url,
                            )
                            try:
                                from scrapling.fetchers import StealthyFetcher
                                proxy = getattr(type(self), '_scrapling_proxy', None)
                                if proxy:
                                    StealthyFetcher.proxy = proxy
                                page = StealthyFetcher.fetch(
                                    ed_url, headless=True, network_idle=True,
                                    timeout=15_000,
                                    headers={"Accept-Language": "en-US,en;q=0.9"},
                                )
                                ed_html = (
                                    page.html_content if hasattr(page, 'html_content')
                                    else page.body.decode('utf-8', errors='replace')
                                )
                            except Exception:
                                ed_html = None
                            if not ed_html:
                                ed_result = self.fetch_with_fallback(ed_url)
                                if ed_result.success:
                                    ed_html = self._extract_html_text(ed_result)
                            if not ed_html:
                                continue
                            ed_soup = BeautifulSoup(ed_html, "html.parser")
                            # Select content area (same as Step 4)
                            content_area = ed_soup.select_one(
                                ".lang-en .part, .part, .editorial-content, "
                                "article, main, #task-statement"
                            )
                            if not content_area:
                                cols = ed_soup.select(".col-sm-12")
                                if len(cols) >= 2:
                                    content_area = cols[1]
                                else:
                                    content_area = cols[0] if cols else ed_soup
                            # Remove nav/header
                            for sel in (
                                "script", "style", "nav", "footer", "header",
                                "#contest-nav-tabs", ".contest-duration",
                                ".pull-right", ".sidebox", ".col-sm-4",
                                ".hidden-xs", ".a2a_kit",
                                ".div-btn-copy", ".btn-copy",
                                ".monaco-editor",
                                ".prettyprint", ".prettyprinted",
                            ):
                                for el in content_area.select(sel):
                                    el.decompose()
                            # Run HTML pipeline
                            self._process_katex(content_area)
                            self._process_images(content_area)
                            self._unwind_inline(content_area)
                            self._process_lists(content_area)
                            self._process_tables(content_area)
                            self._process_paragraphs(content_area)
                            for pre in content_area.find_all("pre"):
                                style = pre.get("style", "")
                                if "display:none" in style.replace(" ", "").lower():
                                    pre.decompose()
                                    continue
                                self._merge_adjacent_strings(pre)
                                pre_text = pre.get_text()
                                if "$" in pre_text:
                                    pre.replace_with(f"\n{pre_text.strip()}\n")
                                else:
                                    pre.replace_with(f"\n```\n{pre_text}\n```\n")
                            self._merge_adjacent_strings(content_area)
                            found_text = content_area.get_text("\n", strip=False).strip()
                            found_text = _html.unescape(found_text)
                            found_text = self._normalize_text(found_text)
                            # Strip user-editorial header:
                            #   "B16 - Frog 1 Editorial\n\n by avatar iastm\n\n"
                            found_text = _re.sub(
                                r'^[A-Z]\d+\s*[-–—−–—]\s*.+?(?:Editorial|题解|解説)\s*\n+'
                                r'\s*by\s+!\[image\]\([^)]+\)\S*\s*\n+',
                                '', found_text, count=1,
                            )
                            if len(found_text) > 50:
                                solutions.append({
                                    "author": "AtCoder Editorial",
                                    "title": f"{source_id} Solution",
                                    "content": found_text,
                                    "vote_count": 0,
                                })
                                break

        if not solutions:
            return CrawlResult(
                success=False,
                error=f"No editorial content found for problem '{source_id}'",
                source="http",
            )

        return CrawlResult(
            success=True,
            data=solutions,
            source=page_result.source,
        )

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch an AtCoder user's profile (browser-based).

        Navigates to ``/users/{uid}`` and extracts structured profile
        data via regex scraping.

        Args:
            uid: AtCoder user ID (case-sensitive).

        Returns:
            CrawlResult with profile dict.
        """
        url = f"{self.BASE_URL}/users/{uid}"
        logger.debug("AtCoder fetching user profile: %s", url)

        result = self.fetch_with_fallback(url)
        if not result.success:
            return result

        html = self._extract_html_text(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty user profile page",
                source=result.source,
                retry_count=result.retry_count,
            )

        import html as _html

        profile: Dict[str, object] = {"user_id": uid}

        # Rating
        rating_match = re.search(
            r'<span[^>]*class="[^"]*user-red[^"]*"[^>]*>(\d+)</span>',
            html,
        ) or re.search(
            r'<span[^>]*class="[^"]*bold[^"]*"[^>]*>(\d+)</span>', html
        )
        if rating_match:
            profile["rating"] = int(rating_match.group(1))

        # Highest rating
        highest_match = re.search(r"Highest Rating[：:]\s*(\d+)", html)
        if highest_match:
            profile["highest_rating"] = int(highest_match.group(1))

        # Affiliation
        aff_match = re.search(
            r'<th[^>]*>Affiliation</th>\s*<td[^>]*>(.*?)</td>',
            html,
            re.DOTALL,
        )
        if aff_match:
            profile["affiliation"] = _html.unescape(
                aff_match.group(1).strip()
            )

        # Country / region
        country_match = re.search(
            r'<th[^>]*>Country/Region</th>\s*<td[^>]*>(.*?)</td>',
            html,
            re.DOTALL,
        )
        if country_match:
            profile["country"] = _html.unescape(
                country_match.group(1).strip()
            )

        # Rank (colour class)
        rank_match = re.search(
            r'<span[^>]*class="[^"]*user-(blue|orange|red|yellow|cyan|green|brown|gray|unrated)[^"]*"',
            html,
        )
        if rank_match:
            profile["rank"] = rank_match.group(1)

        # Number of contests participated
        contests_match = re.search(
            r'<td[^>]*>(\d+)</td>\s*<td[^>]*class="[^"]*text-center[^"]*"[^>]*>\s*Contests',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if contests_match:
            profile["contests_participated"] = int(contests_match.group(1))

        return CrawlResult(
            success=True,
            data=profile,
            source=result.source,
            retry_count=result.retry_count,
        )

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch submission history for an AtCoder user (browser-based).

        Navigates to ``/users/{uid}/submissions`` and extracts
        submission records from the results table.

        Args:
            uid: AtCoder user ID.
            since: *Ignored* — kept for interface compatibility.
                   AtCoder submissions are always newest-first.

        Returns:
            CrawlResult whose ``data`` is a list of submission dicts.
        """
        url = f"{self.BASE_URL}/users/{uid}/submissions"
        logger.debug("AtCoder fetching user submissions: %s", url)

        result = self.fetch_with_fallback(url)
        if not result.success:
            return result

        html = self._extract_html_text(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty submissions page",
                source=result.source,
                retry_count=result.retry_count,
            )

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return CrawlResult(
                success=False,
                error="BeautifulSoup not available",
                source="http",
            )

        soup = BeautifulSoup(html, "html.parser")
        records: list = []

        # AtCoder submissions table — class "table" is typical
        table = soup.find("table", class_="table")
        if table is None:
            table = soup.find("table")

        if table:
            rows = table.find_all("tr")[1:]  # skip header
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 7:
                    continue

                try:
                    time_text = cols[0].get_text(strip=True)
                    problem_link = cols[1].find("a")
                    problem_id = (
                        problem_link.get_text(strip=True)
                        if problem_link
                        else ""
                    )
                    verdict = (
                        cols[6].get_text(strip=True)
                        if len(cols) > 6
                        else ""
                    )

                    records.append(
                        {
                            "uid": uid,
                            "time": time_text,
                            "problem_id": problem_id,
                            "verdict": verdict,
                        }
                    )
                except Exception:
                    continue

        return CrawlResult(
            success=True,
            data=records,
            source=result.source,
            retry_count=result.retry_count,
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch problems filtered by contest tag via kenkoooo API.

        Only returns problems from competitive programming contests
        (ABC, ARC, AGC, AHC, custom contests with digits in ID)
        and DP / TDPC contests.  Tutorials, practice, past exams,
        and other non-contest problem sets are excluded.

        Args:
            tag: Contest prefix to filter by
                 (e.g. ``"abc"``, ``"arc"``, ``"agc"``).
            count: Maximum problems to return.

        Returns:
            CrawlResult with a list of matching problem dicts.
        """
        # ── Tutorial / non-contest prefixes to skip ──────────────
        _TUTORIAL_PREFIXES = (
            "apg4b",  # APG4b / APG4bPython — C++ / Python 入门教程
            "practice",  # practice contest
            "typical90",  # 競プロ典型 90 問
            "tessoku",  # 競技プログラミングの鉄則
            "past",  # アルゴリズム実技検定 (PAST)
            "math-and-algorithm",  # contest_id uses hyphens
            "math_and_algorithm",  # problem_id uses underscores
        )
        # ── Allowed contest patterns ─────────────────────────────
        # Only ABC and ARC contests are crawled.
        _CONTEST_RE = re.compile(
            r'^(abc|arc|agc)'
            r'(\d|[_-])'  # must be followed by digit or separator
        )
        # Lazy-load contest-problem.json for contest_id validation
        _contest_map = self._load_contest_map()
        problems = self._load_merged_problems()
        if not isinstance(problems, list):
            return CrawlResult(
                success=False,
                error="Unexpected merged-problems response format",
                source="http",
            )
        if not problems:
            return CrawlResult(
                success=False,
                error="Empty merged-problems cache",
                source="http",
            )

        # ── English-first priority ordering ──────────────────────
        # ABC/ARC/AGC/AHC and dp/tdpc are almost always English;
        # other contests (xmascon, wupc, yahoo_procon, etc.) are
        # often Japanese-only.  Two-pass collection ensures the
        # enrichment loop sees English problems first and doesn't
        # burn its max_rounds budget on Japanese-only contests.
        _ENGLISH_PREFIXES = ("abc", "arc", "agc")

        def _is_english_contest(pid_lower: str) -> bool:
            """Heuristic: problem ID starts with a known English prefix."""
            return any(pid_lower.startswith(p) for p in _ENGLISH_PREFIXES)

        def _passes_filter(pid: str, pid_lower: str) -> bool:
            """Return True if this problem passes the contest filter."""
            if any(pid_lower.startswith(pref)
                   for pref in _TUTORIAL_PREFIXES):
                return False
            cid = _contest_map.get(pid, "")
            cid_lower = cid.lower() if cid else ""
            pid_allowed = bool(_CONTEST_RE.match(pid_lower))
            cid_allowed = bool(
                cid_lower
                and not any(cid_lower.startswith(pref)
                           for pref in _TUTORIAL_PREFIXES)
                and re.search(r'\d', cid_lower)
            )
            return pid_allowed or cid_allowed

        # Collect all matching problems first (tag-filtered + contest-filtered)
        all_matching: List[dict] = []
        for p in reversed(problems):
            if not isinstance(p, dict):
                continue
            pid = p.get("id", "")
            if not isinstance(pid, str):
                continue
            pid_lower = pid.lower()

            # Must match the requested tag prefix
            if not pid_lower.startswith(tag.lower()):
                continue

            if not _passes_filter(pid, pid_lower):
                continue

            if "source_url" not in p:
                cid = p.get("contest_id", "")
                p["source_url"] = (
                    f"{self.BASE_URL}/contests/{cid}/tasks/{pid}"
                )
            all_matching.append(p)

        # Sort: English-prefix problems first (newest within each
        # group), then the rest.  This ensures the enrichment loop
        # hits English problems before exhausting its round budget.
        english = [p for p in all_matching
                   if _is_english_contest(p.get("id", "").lower())]
        others = [p for p in all_matching
                  if not _is_english_contest(p.get("id", "").lower())]
        matching = (english + others)[:count]

        # ── Attach difficulty from problem-models (cached) ─────────
        try:
            models_data = self._load_problem_models()
            for p in matching:
                pid = p.get("id", "")
                if pid and pid in models_data:
                    model = models_data[pid]
                    if isinstance(model, dict) and "difficulty" in model:
                        p["difficulty"] = model["difficulty"]
        except Exception:
            pass

        return CrawlResult(
            success=True,
            data=matching,
            source="http",
        )


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────


def _run_import(platform: str) -> CrawlResult:
    """Run DataImporter.import_all() for the given platform.

    Returns:
        CrawlResult wrapping the import results.
    """
    try:
        from prisma import Prisma  # type: ignore[import-untyped]
    except (ImportError, RuntimeError):
        return CrawlResult(
            success=False,
            error=(
                "Prisma client not available. "
                "Install with: pip install prisma, "
                "then run: prisma generate"
            ),
        )

    async def _import() -> CrawlResult:
        prisma = Prisma()
        await prisma.connect()
        try:
            importer = DataImporter(prisma)
            results = await importer.import_all()
            return CrawlResult(success=True, data=results)
        finally:
            await prisma.disconnect()

    try:
        return asyncio.run(_import())
    except Exception as exc:
        return CrawlResult(success=False, error=str(exc))


def _save_result(
    crawler: AtCoderCrawler, data, sub_dir: str, label: str
) -> None:
    """Save fetched data to a timestamped JSON file under
    ``data/raw/{platform}/{sub_dir}/``.
    """
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_label = str(label).replace("/", "_").replace("\\", "_")
    filename = f"{today}_{safe_label}.json"
    crawler.save_json(
        data,
        filename=filename,
        sub_dir=f"{crawler.PLATFORM}/{sub_dir}",
    )


def main(argv: Optional[list] = None) -> None:
    """CLI entry point for the AtCoder crawler.

    Two modes are supported:

    * **NestJS mode** — ``--input`` receives a JSON string with all
      parameters (``action``, ``uid``, ``tags``, ``count``).
    * **CLI mode** — each parameter is supplied via its own argparse flag.

    Output is always a single JSON object printed to stdout.
    """
    parser = argparse.ArgumentParser(description="AtCoder crawler CLI")
    parser.add_argument(
        "--action",
        choices=[
            "fetch_problems",
            "fetch_user",
            "fetch_records",
            "fetch_solutions",
            "fetch_detail",
            "import",
        ],
        default=None,
        help="Crawl action to execute",
    )
    parser.add_argument(
        "--uid", default=None, help="User ID / handle"
    )
    parser.add_argument(
        "--tags", default=None, help="Tag for filtering problems"
    )
    parser.add_argument(
        "--count", type=int, default=50, help="Max items to fetch"
    )
    parser.add_argument(
        "--input",
        default=None,
        help="JSON input string containing all parameters (NestJS mode)",
    )
    args = parser.parse_args(argv)

    # ── determine parameter source ─────────────────────────────
    if args.input:
        try:
            params: dict = json.loads(args.input)
        except json.JSONDecodeError as exc:
            _emit(
                success=False,
                error=f"Invalid JSON input: {exc}",
                platform="atcoder",
            )
            sys.exit(1)
    else:
        if not args.action:
            _emit(
                success=False,
                error="Either --action or --input is required",
                platform="atcoder",
            )
            sys.exit(1)
        params = {
            "action": args.action,
            "uid": args.uid,
            "tags": args.tags,
            "count": args.count,
        }

    action: str = params.get("action", "")
    if not action:
        _emit(
            success=False,
            error="Missing 'action' in parameters",
            platform="atcoder",
        )
        sys.exit(1)

    # ── execute ────────────────────────────────────────────────
    crawler = AtCoderCrawler()
    executor = CrawlerExecutor(crawler)

    try:
        if action == "fetch_user":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_user")
            result = executor.execute("fetch_user_profile", str(uid))
            if result.success and result.data:
                _save_result(
                    crawler, result.data, "profiles", str(uid)
                )

        elif action == "fetch_problems":
            tag = params.get("tags", "")
            count = int(params.get("count", 50))
            skip_ids = set(params.get("skip_ids", []))
            # Loop: keep fetching + enriching in batches until we have
            # `count` valid (non-Japanese) problems or kenkoooo runs dry.
            enriched: list = []
            batch_size = max(count * 3, 30)
            max_rounds = 5
            fetch_ok = False  # True if at least one API call succeeded
            for _round in range(max_rounds):
                fetch_count = batch_size + len(skip_ids)
                batch_result = executor.execute(
                    "fetch_problems_by_tag", str(tag), fetch_count
                )
                if not batch_result.success or not batch_result.data:
                    break  # API failure or no more problems
                fetch_ok = True
                new_items = [
                    p for p in batch_result.data
                    if p.get("id", "") not in skip_ids
                ]
                if not new_items:
                    break  # everything already imported
                for prob in new_items:
                    if len(enriched) >= count:
                        break
                    sid = prob.get("id", "")
                    if not sid:
                        enriched.append(prob)
                        continue
                    detail = executor.execute(
                        "fetch_problem", str(sid)
                    )
                    if detail is not None:
                        if detail.success and detail.data:
                            enriched.append(dict(detail.data))
                        else:
                            # Japanese-only / broken page — skip
                            logger.info(
                                "Skipping %s: %s", sid, detail.error
                            )
                    else:
                        enriched.append(prob)
                    # Track as "seen" so next round skips it
                    skip_ids.add(sid)
                if len(enriched) >= count:
                    break
            # ── Save & fetch solutions ──────────────────────────────
            result = CrawlResult(
                success=fetch_ok,
                data=enriched,
                error=(
                    None if fetch_ok
                    else "No problems fetched (API may be rate-limited "
                         "or all problems are Japanese-only)"
                ),
                source="http",
            )
            if enriched:
                _save_result(
                    crawler, result.data, "problems", str(tag) or "all"
                )
                # Fetch solutions for each problem
                for prob in enriched:
                    sid = prob.get("id", "")
                    if sid:
                        sol_result = executor.execute("fetch_solutions", str(sid), 5)
                        if sol_result and sol_result.success and sol_result.data:
                            _save_result(crawler, sol_result.data, "solutions", str(sid))

        elif action == "fetch_records":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError(
                    "--uid is required for fetch_records"
                )
            result = executor.execute("fetch_user_records", str(uid))
            if result.success and result.data:
                _save_result(
                    crawler, result.data, "records", str(uid)
                )

        elif action == "fetch_solutions":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError(
                    "--uid is required for fetch_solutions"
                )
            count = int(params.get("count", 5))
            result = executor.execute(
                "fetch_solutions", str(uid), count
            )
            if result.success and result.data:
                _save_result(
                    crawler, result.data, "solutions", str(uid)
                )

        elif action == "fetch_detail":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError(
                    "--uid is required for fetch_detail"
                )
            result = executor.execute("fetch_problem", str(uid))
            if result.success and result.data:
                _save_result(
                    crawler, result.data, "problems", str(uid)
                )

        elif action == "import":
            result = _run_import(crawler.PLATFORM)

        else:
            result = CrawlResult(
                success=False, error=f"Unknown action: {action}"
            )

        _emit(
            success=result.success,
            data=result.data,
            error=result.error,
            platform=crawler.PLATFORM,
        )
    except Exception as exc:
        _emit(
            success=False,
            error=str(exc),
            platform=crawler.PLATFORM,
        )
        sys.exit(1)
    finally:
        crawler.close()


def _emit(
    success: bool,
    platform: str = "atcoder",
    data: object = None,
    error: Optional[str] = None,
) -> None:
    """Print a JSON result line to stdout."""
    payload = {
        "success": success,
        "data": data,
        "error": error,
        "platform": platform,
    }
    json_str = json.dumps(payload, ensure_ascii=False, default=str)
    sys.stdout.buffer.write((json_str + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
