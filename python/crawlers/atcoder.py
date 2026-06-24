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

    @staticmethod
    def _default_qps() -> float:
        return 3.0

    # ── contest_id cache ────────────────────────────────────────
    # kenkoooo's merged-problems.json has unreliable problem IDs
    # (e.g. "1202Contest_a" where contest slug is actually "DEGwer2023").
    # We load contest-problem.json to get the real contest_id for each
    # problem_id so URLs like /contests/{real_contest}/tasks/{pid} work.

    _contest_map: Optional[dict] = None  # problem_id -> contest_id

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

            # Walk up to find the .katex wrapper
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
                if "katex" in classes:
                    katex_wrapper = el
                    break
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

        # Wrap <code> content in backticks before unwrapping
        for code_el in root_el.find_all("code"):
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
        SECTION_MAP: Dict[str, str] = {
            "problem statement": "description",
            "problem": "description",
            "story": "description",
            "constraints": "constraints",
            "constraint": "constraints",
            "input": "input_format",
            "output": "output_format",
            "input format": "input_format",
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
                existing = result.get(section_key, "")
                if isinstance(existing, str) and existing:
                    result[section_key] = existing + "\n\n" + text
                else:
                    result[section_key] = text

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

        # ── Fetch kenkoooo merged-problems.json for metadata ────────
        try:
            merged_url = (
                f"{self.KENKOO_API}/resources/merged-problems.json"
            )
            merged_result = self._http_request(merged_url)
            if merged_result.success and isinstance(
                merged_result.data, list
            ):
                for p in merged_result.data:
                    if isinstance(p, dict) and p.get("id") == source_id:
                        if "point" in p and p["point"] is not None:
                            data_dict["point"] = p["point"]
                        if "solver_count" in p:
                            data_dict["solver_count"] = p["solver_count"]
                        break
        except Exception:
            pass

        # ── Fetch difficulty from problem-models.json ───────────────
        try:
            models_url = (
                f"{self.KENKOO_API}/resources/problem-models.json"
            )
            models_result = self._http_request(models_url)
            if models_result.success and isinstance(
                models_result.data, dict
            ):
                model = models_result.data.get(source_id)
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
        # Group English editorial links under their preceding
        # problem heading.
        prob_editorials: dict[str, str] = {}  # letter → english_url
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
                    # "Editorial" = English; "解説" = Japanese
                    if link_text.lower() in ("editorial", "english"):
                        full_url = (
                            f"{self.BASE_URL}{href}"
                            if href.startswith("/") else href
                        )
                        prob_editorials[current_letter] = full_url

        logger.debug(
            "Found editorials for problems: %s",
            ", ".join(sorted(prob_editorials.keys())),
        )

        target_links: list[str] = []
        if index_upper in prob_editorials:
            target_links.append(prob_editorials[index_upper])
        # Fallback: also try Japanese link if no English found
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if _re.search(
                rf"/contests/{_re.escape(contest_id)}/editorial/\d+", href,
            ):
                full_url = (
                    f"{self.BASE_URL}{href}"
                    if href.startswith("/") else href
                )
                if full_url not in target_links:
                    target_links.append(full_url)

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
            ):
                for el in content_area.select(sel):
                    el.decompose()

            # Clean KaTeX and images
            self._process_katex(content_area)
            self._process_images(content_area)

            # Try to extract problem-specific section by heading
            prob_heading_re = _re.compile(
                rf"^(?:Task\s*)?{_re.escape(index_upper)}[\.\s\-:：]",
                _re.IGNORECASE,
            )
            found_text = ""
            for tag in content_area.find_all(["h2", "h3", "h4"]):
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
                    parts.append(
                        sibling.get_text("\n", strip=True)
                        if hasattr(sibling, "get_text")
                        else str(sibling)
                    )
                    sibling = sibling.next_sibling
                found_text = "\n".join(p for p in parts if p.strip())
                break

            # If no problem-specific heading, use the full content area
            if not found_text:
                found_text = content_area.get_text("\n", strip=True)
                # Strip common header noise
                found_text = _re.sub(
                    r'^.*?Contest Duration:.*?(\n[A-Z][a-z].*?Editorial)',
                    r'\1', found_text, count=1, flags=_re.DOTALL,
                )

            found_text = _html.unescape(found_text)
            found_text = self._normalize_text(found_text)

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
                text = section_soup.get_text("\n", strip=True)
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

        Fetches ``merged-problems.json`` from kenkoooo.com and
        filters problems whose ``id`` starts with *tag*.

        Args:
            tag: Contest prefix to filter by
                 (e.g. ``"abc"``, ``"arc"``, ``"agc"``).
            count: Maximum problems to return.

        Returns:
            CrawlResult with a list of matching problem dicts.
        """
        merged_url = (
            "https://kenkoooo.com/atcoder/resources/merged-problems.json"
        )
        logger.debug("AtCoder fetching merged-problems.json")

        result = self._http_request(merged_url)
        if not result.success:
            return result

        problems = result.data
        if not isinstance(problems, list):
            return CrawlResult(
                success=False,
                error="Unexpected merged-problems response format",
                source="http",
            )

        matching: List[dict] = []
        for p in problems:
            if not isinstance(p, dict):
                continue
            pid = p.get("id", "")
            if isinstance(pid, str) and pid.lower().startswith(
                tag.lower()
            ):
                # Attach source_url if missing
                if "source_url" not in p:
                    cid = p.get("contest_id", "")
                    p["source_url"] = (
                        f"{self.BASE_URL}/contests/{cid}/tasks/{pid}"
                    )
                matching.append(p)
                if len(matching) >= count:
                    break

        # ── Fetch difficulty from problem-models.json ───────────────
        try:
            models_url = (
                f"{self.KENKOO_API}/resources/problem-models.json"
            )
            models_result = self._http_request(models_url)
            if models_result.success and isinstance(
                models_result.data, dict
            ):
                models_data = models_result.data
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
            fetch_count = max(count + len(skip_ids), count * 3)
            result = executor.execute(
                "fetch_problems_by_tag", str(tag), fetch_count
            )
            if result.success and result.data:
                new_items = []
                for p in result.data:
                    pid = p.get("id", "")
                    if pid not in skip_ids:
                        new_items.append(p)
                new_items = new_items[:count]
                # Enrich with full detail
                enriched = []
                for prob in new_items:
                    sid = prob.get("id", "")
                    if sid:
                        detail = executor.execute(
                            "fetch_problem", str(sid)
                        )
                        if detail and detail.success and detail.data:
                            enriched.append(dict(detail.data))
                        else:
                            enriched.append(prob)
                    else:
                        enriched.append(prob)
                result = CrawlResult(
                    success=True,
                    data=enriched,
                    source=result.source,
                )
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
