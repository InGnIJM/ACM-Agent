"""
NowCoder (牛客网) platform crawler.

NowCoder does not expose a public REST or GraphQL API.  All data is
obtained by fetching HTML pages and parsing them via ``fetch_with_fallback``
(HTTP first, then browser fallback).

HTML parsing is minimal and defensive: if the expected DOM structure
changes, methods return a failure ``CrawlResult`` instead of crashing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from typing import Any, Dict, List, Optional

from crawlers.base import BaseCrawler, CrawlResult, CrawlerExecutor, DataImporter

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# NowCoderCrawler
# ──────────────────────────────────────────────


class NowCoderCrawler(BaseCrawler):
    """Crawler for NowCoder (https://ac.nowcoder.com).

    Uses ``fetch_with_fallback`` for every endpoint; HTML responses are
    parsed with regex / ``json.loads``-in-script-tag extraction.

    If the HTML structure changes upstream these methods will degrade
    gracefully to failure rather than raising exceptions.
    """

    PLATFORM: str = "nowcoder"

    # ── class constants ─────────────────────────────────────────

    BASE_URL: str = "https://ac.nowcoder.com"

    @staticmethod
    def _default_qps() -> float:
        return 2.0

    # ── HTML extraction helpers ─────────────────────────────────

    @staticmethod
    def _extract_json_from_script(
        html: str, var_pattern: str
    ) -> Optional[Any]:
        """Extract a JSON value assigned to a JS variable in a ``<script>`` tag.

        Typical NowCoder pattern:

            <script>window.__INITIAL_STATE__ = {...};</script>

        Args:
            html: Full HTML page text.
            var_pattern: Regex pattern that captures the JSON payload in
                         group 1 (e.g. ``r'__INITIAL_STATE__\\s*=\\s*(\\{.*?\\});'``).

        Returns:
            Parsed Python object, or ``None`` on failure.
        """
        m = re.search(var_pattern, html, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse JSON from script tag: %s", exc)
            return None

    @staticmethod
    def _parse_samples_from_html(sample_el) -> list:
        """Parse sample input/output pairs from the .question-oi element.

        Returns a list of ``[input_str, output_str, note_str?]`` triples.
        The third element (note/explanation) is present only when the sample
        includes an "explanation" section.
        """
        pairs: list = []

        # Convert equation images to LaTeX first
        NowCoderCrawler._nowcoder_convert_equation_images(sample_el)
        # Convert ordinary <img> (screenshots etc.) to Markdown ![](url)
        NowCoderCrawler._nowcoder_convert_images_to_markdown(sample_el)

        # Strategy 1: .question-oi-bd blocks (modern layout)
        # Each sample has its own .question-oi-bd containing multiple
        # .question-oi-mod blocks (input/output/explanation).
        bd_blocks = sample_el.select('.question-oi-bd')
        if bd_blocks:
            for bd in bd_blocks:
                mods = bd.select('.question-oi-mod')
                inp = ''
                out = ''
                note = ''
                for mod in mods:
                    h2 = mod.select_one('h2')
                    label = h2.get_text(strip=True) if h2 else ''
                    pre = mod.select_one('pre')
                    textarea = mod.select_one('textarea')
                    if pre:
                        text = pre.get_text('\n', strip=True)
                    elif textarea:
                        text = textarea.get_text('\n', strip=True)
                    else:
                        text = ''
                    text = re.sub(r'\s*复制\s*', '', text).strip()
                    if '输入' in label and not inp:
                        inp = text
                    elif '输出' in label and not out:
                        out = text
                    elif ('说明' in label or '解释' in label) and text:
                        note = text
                if inp or out:
                    entry = [inp, out]
                    if note:
                        entry.append(note)
                    pairs.append(entry)
            if pairs:
                return pairs

        # Strategy 2: .question-oi-mod blocks (legacy flat layout)
        sample_blocks = sample_el.select('.question-oi-mod')
        if sample_blocks:
            inp = ''
            out = ''
            note = ''
            for block in sample_blocks:
                h2 = block.select_one('h2')
                label = h2.get_text(strip=True) if h2 else ''
                pre = block.select_one('pre')
                textarea = block.select_one('textarea')
                if pre:
                    text = pre.get_text('\n', strip=True)
                elif textarea:
                    text = textarea.get_text('\n', strip=True)
                else:
                    text = ''
                text = re.sub(r'\s*复制\s*', '', text).strip()
                if '输入' in label:
                    # Start new sample if we already have data
                    if inp or out:
                        entry = [inp, out]
                        if note:
                            entry.append(note)
                        pairs.append(entry)
                    inp = text
                    out = ''
                    note = ''
                elif '输出' in label:
                    out = text
                elif ('说明' in label or '解释' in label) and text:
                    note = text
            # Don't forget the last one
            if inp or out:
                entry = [inp, out]
                if note:
                    entry.append(note)
                pairs.append(entry)
            if pairs:
                return pairs

        # Strategy 3: sequential <pre> pairs
        all_pres = sample_el.select('pre')
        meaningful = [
            p for p in all_pres
            if p.get_text(strip=True).replace('复制', '').strip()
        ]
        if len(meaningful) >= 2:
            for i in range(0, len(meaningful) - 1, 2):
                inp = meaningful[i].get_text('\n', strip=True).replace('复制', '').strip()
                out = meaningful[i + 1].get_text('\n', strip=True).replace('复制', '').strip()
                if inp:
                    pairs.append([inp, out])
            if len(meaningful) % 2 == 1 and pairs:
                extra = meaningful[-1].get_text('\n', strip=True).replace('复制', '').strip()
                if extra:
                    pairs[-1].append(extra)
            if pairs:
                return pairs

        # Strategy 4: text fallback
        raw = sample_el.get_text('\n', strip=True)
        raw = raw.replace('复制', '')
        pairs = NowCoderCrawler._parse_samples_from_text(raw)
        if pairs:
            raw_html = str(sample_el)
            marker_count = len(re.findall(r'(?:示例|样例)\s*\d', raw_html))
            if len(pairs) >= marker_count:
                return pairs

        # Strategy 5: search raw HTML for markers
        raw_html = str(sample_el)
        clean = re.sub(r'<br\s*/?>', '\n', raw_html, flags=re.IGNORECASE)
        clean = re.sub(r'<[^>]+>', '', clean)
        clean = clean.replace('复制', '')
        sections = re.split(r'(?:示例|样例)\d*\s*', clean)
        if len(sections) > 1:
            for section in sections[1:]:
                section = section.strip()
                if not section:
                    continue
                inp_m = re.search(r'输入\s*\n(.*?)(?=\n\s*(?:输出|说明))', section, re.DOTALL)
                inp_text = inp_m.group(1).strip() if inp_m else ''
                out_m = re.search(r'输出\s*\n(.*?)(?=\n\s*说明|$)', section, re.DOTALL)
                out_text = out_m.group(1).strip() if out_m else ''
                note_m = re.search(r'说明\s*\n(.*)', section, re.DOTALL)
                note_text = note_m.group(1).strip() if note_m else ''
                if inp_text or out_text:
                    entry = [inp_text, out_text]
                    if note_text:
                        entry.append(note_text)
                    pairs.append(entry)
        return pairs

    @staticmethod
    def _parse_samples_from_text(raw_text: str) -> list:
        """Parse NowCoder sample text into ``[[input, output], ...]`` pairs.

        Handles patterns like::

            示例1
            输入
            <multi-line input>
            输出
            <multi-line output>
            说明      ← trailing note, discarded
        """
        pairs: list = []

        raw = raw_text.strip()
        # Remove trailing "说明" note section (appears after all samples)
        shuoming = raw.rfind("说明")
        if shuoming > 0:
            raw = raw[:shuoming].strip()

        # Split by example markers: 示例1, 样例2, 示例1：, etc.
        # The old regex \d+\s* failed on Chinese colons (：is not whitespace).
        sections = re.split(r"(?:示例|样例)\s*\d*\s*[:：]?\s*", raw)
        sections = [s.strip() for s in sections if s.strip()]

        if not sections:
            return pairs

        for section in sections:
            # Extract input: text between "输入" and "输出"
            inp_m = re.search(
                r"输入\s*\n(.*?)(?=\n\s*输出)", section, re.DOTALL
            )
            inp_text = inp_m.group(1).strip() if inp_m else ""

            # Extract output: text after "输出"
            out_m = re.search(r"输出\s*\n(.*)", section, re.DOTALL)
            out_text = out_m.group(1).strip() if out_m else ""

            # Strip ''' literal delimiters from NowCoder's HTML <pre> content
            inp_text = inp_text.replace("'''", "").strip()
            out_text = out_text.replace("'''", "").strip()
            # Clean copy-button labels
            inp_text = re.sub(r"\s*复制\s*", "", inp_text).strip()
            out_text = re.sub(r"\s*复制\s*", "", out_text).strip()

            if inp_text or out_text:
                pairs.append([inp_text, out_text])

        return pairs

    @staticmethod
    def _strip_katex_redundancy(soup) -> None:
        """Replace KaTeX math elements with their plain-text content.

        KaTeX renders math into a three-layer HTML structure with heavy
        nesting (MathML + visual spans + hidden duplicates).  Instead of
        trying to pick one layer, we extract the plain text from the
        semantic MathML layer and replace the entire ``.katex`` wrapper
        with that text node.  This avoids both triplication and the
        line-splitting that occurs when ``get_text("\\n")`` walks
        individual ``<mi>``/``<mo>``/``<mn>`` MathML elements.

        After replacing KaTeX wrappers, also strip any bare LaTeX source
        (``$...$``) that sits outside ``.katex`` — these are spill-over
        text nodes from the raw problem source and cause triplication.
        """
        for katex_el in soup.select(".katex"):
            mathml = katex_el.select_one(".katex-mathml")
            if mathml:
                # Prefer the <annotation> element which contains the raw
                # LaTeX source (e.g. "100^{100}").  Wrap in $...$ so the
                # downstream Markdown+KaTeX pipeline renders it correctly.
                ann = mathml.select_one("annotation")
                if ann:
                    plain = ann.get_text("", strip=True)
                    import re as _re_nck
                    # Strip leading \hspace{...} / \vspace{...} (layout noise)
                    # but KEEP any remaining LaTeX content (e.g. \bullet\,).
                    # The old logic discarded the entire annotation when it
                    # started with \hspace, which leaked raw annotation text
                    # into the output when the .katex element was left intact.
                    stripped = _re_nck.sub(r'^\\[hv]space\{[^}]*\}', '', plain).strip()
                    if stripped:
                        plain = f" ${stripped}$ "
                    else:
                        plain = ""  # purely spacing — decomposing
                else:
                    # Fallback: extract plain MathML text (Unicode math)
                    for ann in mathml.select("annotation"):
                        ann.decompose()
                    plain = mathml.get_text("", strip=True)
            else:
                plain = katex_el.get_text("", strip=True)
            if plain:
                katex_el.replace_with(plain)
            else:
                katex_el.decompose()  # pure spacing — remove entirely

    @staticmethod
    def _nowcoder_convert_equation_images(soup) -> None:
        """Convert NowCoder equation <img> tags to LaTeX $...$ text.

        NowCoder renders math via server-side equation images:
            <img alt="100^{100}" src=".../equation?tex=100%5E%7B100%7D"/>

        This method replaces each such <img> with a text node containing
        the LaTeX source wrapped in $...$, using the alt attribute as
        the LaTeX source (it's already unescaped).
        """
        import re as _re_nci
        for img in soup.select('img[src*="equation"]'):
            alt = (img.get('alt') or '').strip()
            if not alt:
                img.decompose()
                continue
            # Skip purely spacing commands — they're layout noise
            if _re_nci.match(r'^\\[hv]space', alt):
                img.decompose()
                continue
            img.replace_with(f' ${alt}$ ')

    @staticmethod
    def _nowcoder_convert_images_to_markdown(soup) -> None:
        """Convert non-equation <img> tags to Markdown ``![](url)`` syntax.

        Equation images (src contains "equation") are handled separately
        by :meth:`_nowcoder_convert_equation_images`.  This method only
        processes ordinary content images (e.g. screenshots in explanations)
        and replaces each with a Markdown image node so downstream rendering
        displays them correctly.

        Reference: AtCoder crawler ``_process_images``.
        """
        for img in soup.select('img'):
            src = (img.get('src') or '').strip()
            if not src:
                img.decompose()
                continue
            # Skip equation images — those are handled by
            # _nowcoder_convert_equation_images (called earlier).
            if 'equation' in src:
                continue
            alt = (img.get('alt') or '').strip() or 'image'
            img.replace_with(f'![{alt}]({src})')

    @staticmethod
    def _nowcoder_html_to_markdown(container) -> str:
        """Convert a BeautifulSoup HTML element to Markdown text.

        Preserves: <br>->newline, <u>-><u>text</u>, <strong>->**text**,
        <a>->[text](href), <div>->paragraph break, <img>->$...$.

        Call _nowcoder_convert_equation_images FIRST on the soup before
        passing the element to this method.
        """
        from bs4 import NavigableString, Tag
        import re as _re_nhm

        result = []

        def _walk(el):
            if isinstance(el, NavigableString):
                result.append(str(el))
                return
            if not isinstance(el, Tag):
                return

            tag = el.name.lower()

            if tag == 'br':
                result.append('\n')
                return

            if tag == 'img':
                alt = (el.get('alt') or '').strip()
                src = el.get('src', '')
                if 'equation' in src and alt:
                    if not _re_nhm.match(r'^\\[hv]space', alt):
                        result.append(f' ${alt}$ ')
                elif src:
                    # Ordinary image (screenshot, diagram, etc.) → Markdown
                    label = alt or 'image'
                    result.append(f'\n\n![{label}]({src})\n\n')
                return

            if tag == 'u':
                result.append('<u>')
                for child in el.children:
                    _walk(child)
                result.append('</u>')
                return

            if tag in ('strong', 'b'):
                result.append('**')
                for child in el.children:
                    _walk(child)
                result.append('**')
                return

            if tag in ('em', 'i'):
                result.append('*')
                for child in el.children:
                    _walk(child)
                result.append('*')
                return

            if tag == 'a':
                href = el.get('href', '')
                result.append('[')
                for child in el.children:
                    _walk(child)
                result.append(f']({href})')
                return

            if tag in ('div', 'p'):
                if result and not result[-1].endswith('\n\n'):
                    result.append('\n\n')
                for child in el.children:
                    _walk(child)
                if result and not result[-1].endswith('\n\n'):
                    result.append('\n\n')
                return

            if tag in ('pre', 'code'):
                text = el.get_text('', strip=False)
                result.append(f'\n```\n{text}\n```\n')
                return

            for child in el.children:
                _walk(child)

        _walk(container)

        text = ''.join(result)
        # Collapse 3+ consecutive blank lines to at most one
        import re as _re_nhm2
        text = _re_nhm2.sub('\n{3,}', '\n\n', text)
        text = text.replace('  ', ' ')
        text = text.strip()
        text = text.replace('$ ', '$').replace(' $', '$')

        return text

    @staticmethod
    def clean_mathjax(text: str) -> str:
        """Clean MathJax artifacts and NowCoder UI noise from extracted text.

        Removes: MathJax triplication (deduplicates consecutive identical
        lines), LaTeX formatting commands (``\\hspace``, ``\\texttt``,
        ``\\bullet``, ``\\leqq``, ``^\\texttt{[...]}``), and copy-button
        labels (``复制``).
        """
        if not text:
            return text

        # ── Unicode control characters (root cause of triplication + noise) ──
        for k, v in NowCoderCrawler._unicode_controls().items():
            text = text.replace(k, v)

        # Strip "复制" copy-button labels
        text = re.sub(r"\s*复制\s*", "", text)

        # Strip LaTeX formatting / MathJax artifacts
        text = re.sub(r"\\hspace\{[^}]*\}", "", text)
        text = re.sub(r"\\texttt\{([^}]*)\}", r"\1", text)
        text = re.sub(r"\^\{\\texttt\{[^}]*\}\}", "", text)
        text = re.sub(r"\\bullet", "", text)
        text = re.sub(r"\\leqq", "<=", text)
        # Strip LaTeX spacing commands that leak outside $…$ delimiters
        text = re.sub(r"\\,", "", text)   # thin space
        text = re.sub(r"\\!", "", text)   # negative thin space
        text = re.sub(r"\\;", "", text)   # thick space
        text = re.sub(r"\\:", "", text)   # medium space

        # Deduplicate consecutive repeated lines (MathJax triplication)
        lines = text.split("\n")
        deduped: list = []
        prev = ""
        for line in lines:
            s = line.strip()
            if s and s == prev:
                continue
            if s:
                prev = s
            deduped.append(line)

        text = "\n".join(deduped).strip()

        # Merge short orphaned lines back into paragraphs.
        # get_text("\\n") splits EVERY text node onto its own line
        # (e.g. "有一个" / "n" / "行" / "m" / "列" all separate).
        # Strategy: join consecutive non-blank short lines with spaces,
        # keep blank lines as paragraph breaks.
        lines2 = text.split("\n")
        merged2: list = []
        buf: list = []
        for line in lines2:
            s = line.strip()
            if not s:
                if buf:
                    merged2.append(" ".join(buf))
                    buf = []
                merged2.append("")  # preserve paragraph break
            elif len(s) <= 20 and not s.startswith(("输入", "输出", "样例", "示例", "提示", "说明", "注意")):
                buf.append(s)
            else:
                if buf:
                    merged2.append(" ".join(buf))
                    buf = []
                merged2.append(line)
        if buf:
            merged2.append(" ".join(buf))

        return "\n".join(merged2).strip()

    @staticmethod
    def clean_mathjax_sample(text: str) -> str:
        """Light version of :meth:`clean_mathjax` for sample I/O text.

        Strips Unicode controls, deduplicates, and removes copy-button
        labels, but does NOT perform aggressive line merging — sample
        text must preserve its multi-line structure (matrix rows, etc.).
        """
        if not text:
            return text
        # Unicode controls (same as clean_mathjax)
        for k, v in NowCoderCrawler._unicode_controls().items():
            text = text.replace(k, v)
        # Strip copy-button labels and LaTeX artifacts
        text = re.sub(r"\s*复制\s*", "", text)
        text = re.sub(r"\\hspace\{[^}]*\}", "", text)
        text = re.sub(r"\\texttt\{([^}]*)\}", r"\1", text)
        text = re.sub(r"\^\{\\texttt\{[^}]*\}\}", "", text)
        text = re.sub(r"\\bullet", "", text)
        text = re.sub(r"\\leqq", "<=", text)
        text = re.sub(r"\\,", "", text)
        text = re.sub(r"\\!", "", text)
        text = re.sub(r"\\;", "", text)
        text = re.sub(r"\\:", "", text)
        # Deduplicate consecutive identical lines only (no merging)
        lines = text.split("\n")
        deduped = []
        prev = ""
        for line in lines:
            s = line.strip()
            if s and s == prev:
                continue
            if s:
                prev = s
            deduped.append(line)
        return "\n".join(deduped).strip()

    @staticmethod
    def _unicode_controls() -> dict:
        """Shared Unicode control-character table."""
        return {
            "​": "",   # ZERO WIDTH SPACE (U+200B)
            "⁡": "",   # FUNCTION APPLICATION (U+2061)
            " ": " ",  # THIN SPACE (U+2009)
            " ": " ",  # HAIR SPACE (U+200A)
            " ": " ",  # EN SPACE (U+2002)
            " ": " ",  # EM SPACE (U+2003)
            " ": " ",  # THREE-PER-EM SPACE
            " ": " ",  # FOUR-PER-EM SPACE
            " ": " ",  # SIX-PER-EM SPACE
            " ": " ",  # FIGURE SPACE
            " ": " ",  # PUNCTUATION SPACE
            " ": " ",  # NO-BREAK SPACE
            "﻿": "",   # BYTE ORDER MARK
            "⁠": "",   # WORD JOINER
            "￼": "",   # OBJECT REPLACEMENT CHARACTER
            "‘": "'",  # LEFT SINGLE QUOTATION MARK
            "’": "'",  # RIGHT SINGLE QUOTATION MARK
            "`": "'",  # GRAVE ACCENT
            "′": "'",  # PRIME
        }

    @staticmethod
    def _get_text_from_result(result: CrawlResult) -> Optional[str]:
        """Extract a plain-text string from a ``CrawlResult`` payload.

        Handles both ``{"text": "<html>..."}`` (browser source) and
        dict/list data (stringified).
        """
        data = result.data
        if isinstance(data, dict):
            return data.get("text") if "text" in data else json.dumps(data)
        if isinstance(data, list):
            return json.dumps(data)
        return str(data) if data else None

    # ── abstract method implementations ─────────────────────────

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch a NowCoder user's public profile page.

        GET https://ac.nowcoder.com/acm/contest/profile/{uid}

        The profile data is embedded as ``window.__INITIAL_STATE__``
        in the HTML.

        Args:
            uid: NowCoder user ID (numeric, e.g. ``"123456"``).

        Returns:
            CrawlResult with profile dict, or error.
        """
        url = f"{self.BASE_URL}/acm/contest/profile/{uid}"
        result = self.fetch_with_fallback(url)

        if not result.success:
            return result

        html = self._get_text_from_result(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response body",
                source=result.source,
            )

        # Attempt to extract window.__INITIAL_STATE__.
        extracted = self._extract_json_from_script(
            html,
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        )
        if extracted is None:
            # Fallback: try other script patterns.
            extracted = self._extract_json_from_script(
                html,
                r'window\.__NUXT__\s*=\s*(\{.*?\});',
            )

        if extracted is None:
            return CrawlResult(
                success=False,
                error="Could not extract profile data from page HTML",
                source=result.source,
            )

        # The profile is usually nested; try common paths.
        profile = None
        if isinstance(extracted, dict):
            profile = (
                extracted.get("profile")
                or extracted.get("userData")
                or extracted.get("userInfo")
                or extracted.get("state", {}).get("profile")
                or extracted
            )

        return CrawlResult(
            success=True,
            data=profile,
            source=result.source,
            retry_count=result.retry_count,
        )

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch a user's AC submission list.

        GET https://ac.nowcoder.com/acm/contest/profile/{uid}/practice-coding

        The submission list is rendered server-side in the HTML table.

        Args:
            uid: NowCoder user ID.
            since: *Accepted but ignored* — the profile page includes
                   all submissions.

        Returns:
            CrawlResult with a list of parsed submission dicts.
        """
        url = f"{self.BASE_URL}/acm/contest/profile/{uid}/practice-coding"
        result = self.fetch_with_fallback(url)

        if not result.success:
            return result

        html = self._get_text_from_result(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response body",
                source=result.source,
            )

        # Try to extract records from embedded state.
        extracted = self._extract_json_from_script(
            html,
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        )
        if isinstance(extracted, dict):
            records = (
                extracted.get("records")
                or extracted.get("submissionList")
                or extracted.get("practiceList")
                or []
            )
            if records:
                return CrawlResult(
                    success=True,
                    data=records if isinstance(records, list) else [],
                    source=result.source,
                    retry_count=result.retry_count,
                )

        # Fallback: scrape the table rows.
        records = self._scrape_submission_table(html)
        return CrawlResult(
            success=True,
            data=records,
            source=result.source,
            retry_count=result.retry_count,
        )

    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Fetch a single problem by its NowCoder problem ID.

        GET https://ac.nowcoder.com/acm/problem/{source_id}

        Uses the browser directly because NowCoder requires browser-
        based cookies (SessionPage cookies are often rejected).

        Args:
            source_id: NowCoder problem ID (numeric, e.g. ``"12345"``).

        Returns:
            CrawlResult with problem data including ``description``,
            ``input_format``, ``output_format``, ``samples``.
        """
        url = f"{self.BASE_URL}/acm/problem/{source_id}"

        # Use browser first – NowCoder auth only works in browser context
        result = self._browser_request(url)
        if not result.success:
            # Fall back to HTTP
            result = self._http_request(url)
        if not result.success:
            return result

        html = self._get_text_from_result(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response body",
                source=result.source,
            )

        # Check for permission-denied page
        if "没有查看题目的权限" in html or "没有权限" in html:
            return CrawlResult(
                success=False,
                error="No permission to view this problem (可能需要登录或题目受限)",
                source=result.source,
            )

        # ── Extract from modern NowCoder HTML structure ──────────
        # The page uses CSS classes for layout:
        #   .question-title       → problem title
        #   .subject-describe     → container for all content
        #   .subject-question     → problem description text
        #   h2 + pre              → input/output format sections
        #   .question-oi          → sample test cases

        title = ""
        description = ""
        input_format = ""
        output_format = ""
        samples: list = []  # [[input_str, output_str], ...]

        try:
            from bs4 import BeautifulSoup as _BS
            # Fix malformed HTML: NowCoder uses </br> (invalid closing tags
            # for the void <br> element) which confuses html.parser into
            # wrapping all subsequent content inside a <br> container.
            html = html.replace('</br>', '')
            try:
                soup = _BS(html, "lxml")
            except Exception:
                soup = _BS(html, "html.parser")

            # Title
            title_el = soup.select_one(".question-title")
            if title_el:
                title = title_el.get_text(strip=True)

            # Description — convert equation images first, then HTML→Markdown
            desc_el = soup.select_one(".subject-question")
            if desc_el:
                NowCoderCrawler._strip_katex_redundancy(soup)
                NowCoderCrawler._nowcoder_convert_equation_images(soup)
                description = NowCoderCrawler.clean_mathjax(
                    NowCoderCrawler._nowcoder_html_to_markdown(desc_el)
                )

            # Input / Output format — find h2 elements and their following pre.
            # Only match the "描述" versions; the short "输入"/"输出" headers
            # in the sample section have no pre and would overwrite valid data.
            for h2 in soup.select(".subject-describe h2"):
                label = h2.get_text(strip=True).replace("：", "").replace(":", "")
                pre = h2.find_next_sibling("pre")
                text = pre.get_text("\n", strip=True) if pre else ""
                if "输入描述" in label:
                    input_format = NowCoderCrawler.clean_mathjax(text)
                elif "输出描述" in label:
                    output_format = NowCoderCrawler.clean_mathjax(text)

            # ── Sample extraction ──────────────────────────────
            sample_el = soup.select_one(".question-oi")
            if sample_el:
                samples = NowCoderCrawler._parse_samples_from_html(sample_el)
                # Clean MathJax artifacts lightly — preserve multi-line
                # structure (no aggressive line merging).
                samples = [
                    [NowCoderCrawler.clean_mathjax_sample(x) for x in s]
                    for s in samples
                ]

        except ImportError:
            # Fallback: regex-based extraction
            import re as _re
            t_m = _re.search(
                r'<div[^>]*class="[^"]*question-title[^"]*"[^>]*>(.*?)</div>',
                html, _re.DOTALL,
            )
            if t_m:
                title = _re.sub(r"<[^>]+>", "", t_m.group(1)).strip()

            d_m = _re.search(
                r'<div[^>]*class="[^"]*subject-question[^"]*"[^>]*>(.*?)<h2',
                html, _re.DOTALL,
            )
            if d_m:
                description = _re.sub(r"<[^>]+>", "", d_m.group(1)).strip()

        # ── Extract difficulty and tags from embedded state ──────
        difficulty = None
        tags: List[str] = []

        extracted_state = self._extract_json_from_script(
            html,
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        )
        if isinstance(extracted_state, dict):
            problem_data = (
                extracted_state.get("problemData")
                or extracted_state.get("problem")
                or extracted_state.get("detailData")
                or {}
            )
            if isinstance(problem_data, dict):
                difficulty = (
                    problem_data.get("difficulty")
                    or problem_data.get("difficultyStr")
                    or problem_data.get("level")
                    or problem_data.get("problemDifficulty")
                )
                raw_tags = (
                    problem_data.get("tags")
                    or problem_data.get("tagList")
                    or problem_data.get("labels")
                    or []
                )
                if isinstance(raw_tags, list):
                    tags = [str(t).strip() for t in raw_tags if t]
                elif isinstance(raw_tags, str):
                    tags = [raw_tags.strip()] if raw_tags.strip() else []

        # Fallback: regex for difficulty from page text (e.g. "难度：中等")
        if not difficulty:
            diff_match = re.search(r'难度\s*[：:]\s*(\S+)', html)
            if diff_match:
                difficulty = diff_match.group(1).strip()

        # Fallback: derive difficulty from pass rate if available
        if not difficulty:
            pass_rate = None
            if isinstance(extracted_state, dict):
                pd2 = extracted_state.get("problemData") or extracted_state.get("problem") or {}
                if isinstance(pd2, dict):
                    pass_rate = pd2.get("passRate") or pd2.get("acceptRate") or pd2.get("correctPercent")
            if pass_rate is not None:
                try:
                    pr = float(pass_rate)
                    if pr >= 0.8:
                        difficulty = "简单"
                    elif pr >= 0.5:
                        difficulty = "中等"
                    elif pr >= 0.2:
                        difficulty = "较难"
                    else:
                        difficulty = "困难"
                except (ValueError, TypeError):
                    pass

        # Fallback: scrape difficulty from page text (strip HTML first)
        if not difficulty:
            try:
                from bs4 import BeautifulSoup as _BS3
                _soup = _BS3(html, "html.parser") if "soup" not in dir() else soup
                plain = _soup.get_text(" ", strip=True)
            except Exception:
                import re as _re2
                plain = _re2.sub(r"<[^>]+>", " ", html)
            diff_match = re.search(r"难度\s*[：:]\s*(\S+)", plain)
            if diff_match:
                difficulty = diff_match.group(1).strip()

        # ── Content empty guard ───────────────────────────────────
        if not description and not input_format and not output_format and not samples:
            if title:
                logger.warning(
                    "Content extraction produced empty result for problem %s, using title as content",
                    source_id,
                )
                description = title
            else:
                return CrawlResult(
                    success=False,
                    error="Could not extract problem data from page HTML (empty content)",
                    source=result.source,
                )

        if not title and not description:
            return CrawlResult(
                success=False,
                error="Could not extract problem data from page HTML",
                source=result.source,
            )

        return CrawlResult(
            success=True,
            data={
                "source_id": source_id,
                "title": title,
                "description": description,
                "input_format": input_format,
                "output_format": output_format,
                "samples": samples,
                "difficulty": difficulty,
                "tags": tags,
                "source_url": f"https://ac.nowcoder.com/acm/problem/{source_id}",
            },
            source=result.source,
            retry_count=result.retry_count,
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50, page: int = 1
    ) -> CrawlResult:
        """Fetch problems from the problem set filtered by tag.

        GET https://ac.nowcoder.com/acm/problem/list?tag={tag}&page={page}

        Args:
            tag: NowCoder tag ID or tag name.
            count: Maximum problems to return.
            page: Page number (1-based, 50 per page).

        Returns:
            CrawlResult with a list of problem summary dicts.
        """
        url = f"{self.BASE_URL}/acm/problem/list?tag={tag}&page={page}"
        result = self.fetch_with_fallback(url)

        if not result.success:
            return result

        html = self._get_text_from_result(result)
        if not html:
            return CrawlResult(
                success=False,
                error="Empty response body",
                source=result.source,
            )

        # Try embedded state first.
        extracted = self._extract_json_from_script(
            html,
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
        )
        if isinstance(extracted, dict):
            problems = (
                extracted.get("problemList")
                or extracted.get("problems")
                or extracted.get("list")
                or []
            )
            if problems:
                return CrawlResult(
                    success=True,
                    data=problems[:count] if isinstance(problems, list) else [],
                    source=result.source,
                    retry_count=result.retry_count,
                )

        # Fallback: scrape problem links from the page.
        problems = self._scrape_problem_list(html, count)
        return CrawlResult(
            success=True,
            data=problems,
            source=result.source,
            retry_count=result.retry_count,
        )

    # ── HTML scraping fallback helpers ──────────────────────────

    @staticmethod
    def _scrape_submission_table(html: str) -> List[Dict[str, str]]:
        """Parse the practice-coding HTML table into a list of records.

        This is a best-effort scraper; if the table structure changes
        it will return an empty list (rather than crashing).
        """
        records: List[Dict[str, str]] = []

        # Look for a <table> with class containing "record" or "submission".
        table_match = re.search(
            r'<table[^>]*class="[^"]*(?:record|submission|table)[^"]*"[^>]*>(.*?)</table>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if not table_match:
            table_match = re.search(
                r"<table[^>]*>(.*?)</table>",
                html,
                re.DOTALL | re.IGNORECASE,
            )

        if not table_match:
            return records

        table_html = table_match.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)

        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE)
            # Clean HTML tags from cells.
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if len(clean) >= 3:
                records.append(
                    {
                        "problem": clean[0],
                        "verdict": clean[1] if len(clean) > 1 else "",
                        "time": clean[2] if len(clean) > 2 else "",
                    }
                )

        return records

    def fetch_solutions(
        self, source_id: str, max_pages: int = 3
    ) -> CrawlResult:
        """Fetch solutions for a problem from its solution discussion page.

        Navigates to ``https://ac.nowcoder.com/acm/problem/blogs/{source_id}``
        using the browser and extracts solution entries. Falls back to scraping
        solution-like blocks embedded in the problem page itself.

        Args:
            source_id: NowCoder problem ID (numeric, e.g. ``"317489"``).
            max_pages: Max number of solution pages to fetch (paginated).

        Returns:
            CrawlResult with a list of solution dicts containing
            ``author``, ``content``, ``vote_count``, ``reply_count``.
        """
        all_solutions: list = []

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                url = f"{self.BASE_URL}/acm/problem/blogs/{source_id}"
            else:
                url = f"{self.BASE_URL}/acm/problem/blogs/{source_id}?page={page_num}"

            result = self._browser_request(url)
            if not result.success:
                if page_num == 1:
                    # Primary URL failed; try alternative: /acm/problem/discuss/{id}
                    alt_url = f"{self.BASE_URL}/acm/problem/discuss/{source_id}"
                    result = self.fetch_with_fallback(alt_url)
                    if not result.success:
                        return CrawlResult(
                            success=False,
                            error=result.error or "Solution page fetch failed",
                            source=result.source,
                        )
                else:
                    break

            html = self._get_text_from_result(result)
            if not html:
                break

            # Check for empty / no-solution page
            if "暂无题解" in html or "没有找到相关内容" in html or "暂无内容" in html:
                break

            # ── Parse solution entries ─────────────────────────
            page_solutions: list = []

            try:
                from bs4 import BeautifulSoup as _BS
                soup = _BS(html, "html.parser")

                # Strategy 1: .nc-post-content containers (primary — blogs page)
                solution_items = (
                    soup.select(".nc-post-content")
                    or soup.select("[class*='post-content']")
                    or soup.select("[class*='blog-content']")
                )

                for item in solution_items:
                    # Find author: check parent for .name link
                    parent = item.parent
                    author_el = (
                        (parent.select_one("a.name") if parent else None)
                        or soup.select_one("a.name")
                        or soup.select_one("[class*='user-name']")
                        or soup.select_one(".author")
                    )
                    author = author_el.get_text(strip=True) if author_el else "匿名"

                    content = item.get_text("\n", strip=True)

                    # Filter out ad content
                    if len(content) < 20 or "扫描二维码" in content or "扫码加入" in content or "下载牛客APP" in content or "扫码添加" in content:
                        continue

                    page_solutions.append({
                        "author": author,
                        "title": content[:80].replace("\n", " "),
                        "content": content,
                        "vote_count": 0,
                        "reply_count": 0,
                    })

                # Strategy 1b: .solution-item or .discuss-item containers (fallback)
                if not page_solutions:
                    fb_items = (
                        soup.select(".solution-item")
                        or soup.select(".discuss-item")
                        or soup.select(".solution-list > div")
                        or soup.select(".discuss-list > div")
                        or soup.select("[class*='solution']")
                    )

                    for item in (fb_items or []):
                        author_el = (
                            item.select_one(".user-name")
                            or item.select_one(".author")
                            or item.select_one("[class*='user']")
                        )
                        author = author_el.get_text(strip=True) if author_el else "匿名"

                        content_el = (
                            item.select_one(".solution-content")
                            or item.select_one(".discuss-content")
                            or item.select_one(".content")
                            or item.select_one("[class*='content']")
                        )
                        content = content_el.get_text("\n", strip=True) if content_el else ""

                        if len(content) < 20 or "扫描二维码" in content or "扫码加入" in content:
                            continue

                        vote_el = (
                            item.select_one(".vote-count")
                            or item.select_one(".like-count")
                            or item.select_one("[class*='vote']")
                            or item.select_one("[class*='like']")
                        )
                        vote_count = 0
                        if vote_el:
                            try:
                                vote_count = int(re.sub(r"[^\d]", "", vote_el.get_text(strip=True)) or "0")
                            except ValueError:
                                vote_count = 0

                        reply_el = (
                            item.select_one(".reply-count")
                            or item.select_one(".comment-count")
                            or item.select_one("[class*='reply']")
                            or item.select_one("[class*='comment']")
                        )
                        reply_count = 0
                        if reply_el:
                            try:
                                reply_count = int(re.sub(r"[^\d]", "", reply_el.get_text(strip=True)) or "0")
                            except ValueError:
                                reply_count = 0

                        if content.strip() or author != "匿名":
                            page_solutions.append({
                                "author": author,
                                "title": (content or "")[:80].split("\n")[0].strip(),
                                "content": content,
                                "vote_count": vote_count,
                                "reply_count": reply_count,
                            })

                # Strategy 2: scrape any discussion-style list with user + content
                if not page_solutions:
                    # Look for any user-name + text-content pattern in lists
                    for container in soup.select("ul, ol, .discuss-container, .solution-container"):
                        for li in container.select("li, .item"):
                            author = ""
                            content = ""
                            a_el = li.select_one(".user-name, .name, a[href*='profile']")
                            if a_el:
                                author = a_el.get_text(strip=True)
                            c_el = li.select_one(".content, .text, p:not(.name):not(.user-name)")
                            if c_el:
                                content = c_el.get_text("\n", strip=True)
                            if content.strip():
                                page_solutions.append({
                                    "author": author or "匿名",
                                    "title": (content or "")[:80].split("\n")[0].strip(),
                                    "content": content,
                                    "vote_count": 0,
                                    "reply_count": 0,
                                })

            except ImportError:
                # Fallback: regex-based extraction
                import re as _re
                # Try to extract solution-like blocks
                blocks = _re.findall(
                    r'<div[^>]*class="[^"]*(?:solution|discuss)[^"]*"[^>]*>(.*?)</div>\s*</div>',
                    html, _re.DOTALL,
                )
                for block in blocks[:max_pages * 10]:
                    author_m = _re.search(
                        r'(?:user|author|name)[^>]*>([^<]+)<',
                        block, _re.IGNORECASE,
                    )
                    content_m = _re.search(
                        r'(?:content|text|detail)[^>]*>(.*?)(?:</div>|<div)',
                        block, _re.DOTALL,
                    )
                    author = _re.sub(r"<[^>]+>", "", author_m.group(1)).strip() if author_m else "匿名"
                    content = _re.sub(r"<[^>]+>", "", content_m.group(1)).strip() if content_m else ""
                    if content.strip():
                        page_solutions.append({
                            "author": author,
                            "title": content[:80].split("\n")[0].strip(),
                            "content": content,
                            "vote_count": 0,
                            "reply_count": 0,
                        })

            if not page_solutions:
                break

            all_solutions.extend(page_solutions)

            # If we got fewer solutions than a full page, assume last page
            if len(page_solutions) < 10:
                break

        return CrawlResult(
            success=True,
            data=all_solutions,
            source="browser",
        )

    @staticmethod
    def _scrape_problem_list(
        html: str, max_count: int = 50
    ) -> List[Dict[str, str]]:
        """Scrape problem rows from the problem-list page table.

        The table has columns: 题号, 标题, 难度, 通过率, etc.
        Returns a list of dicts with ``id``, ``title``, ``url``,
        ``difficulty``, and ``tags`` keys.
        """
        problems: List[Dict[str, str]] = []
        seen: set = set()

        # ── Strategy 1: BeautifulSoup table parsing ────────────
        try:
            from bs4 import BeautifulSoup as _BS  # noqa: F811
            soup = _BS(html, "html.parser")

            # Locate the problem table by header keywords
            table = None
            for tbl in soup.select("table"):
                headers = [th.get_text(strip=True) for th in tbl.select("th")]
                if any("难度" in h for h in headers) or any("题号" in h for h in headers):
                    table = tbl
                    break
            if table is None:
                tables = soup.select("table")
                if tables:
                    table = tables[0]

            if table is not None:
                # Column index detection from header row
                header_cells = (
                    table.select("thead th")
                    or table.select("tr:first-child th")
                )
                difficulty_idx: Optional[int] = None
                tags_idx: Optional[int] = None
                for i, th in enumerate(header_cells):
                    text = th.get_text(strip=True)
                    if "难度" in text and difficulty_idx is None:
                        difficulty_idx = i
                    if ("标签" in text or "tag" in text.lower()) and tags_idx is None:
                        tags_idx = i

                # Parse data rows
                rows = table.select("tbody tr")
                if not rows:
                    rows = [r for r in table.select("tr") if r.select("td")]

                for row in rows:
                    if len(problems) >= max_count:
                        break

                    cells = row.select("td")
                    if len(cells) < 2:
                        continue

                    # Locate problem link in any cell
                    problem_id: Optional[str] = None
                    title = ""
                    url = ""
                    for cell in cells:
                        link = cell.select_one("a[href*='/acm/problem/']")
                        if link:
                            href = link.get("href", "")
                            m = re.search(r"/acm/problem/(\d+)", href)
                            if m:
                                problem_id = m.group(1)
                                title = link.get_text(strip=True)
                                url = f"{NowCoderCrawler.BASE_URL}{href}"
                                break

                    if not problem_id or problem_id in seen:
                        continue
                    seen.add(problem_id)

                    # Extract difficulty by column index
                    difficulty = ""
                    if difficulty_idx is not None and difficulty_idx < len(cells):
                        difficulty = cells[difficulty_idx].get_text(strip=True)

                    # Extract tags by column index
                    tags: List[str] = []
                    if tags_idx is not None and tags_idx < len(cells):
                        tag_cell = cells[tags_idx]
                        tag_text = tag_cell.get_text(strip=True)
                        if tag_text:
                            tags = [
                                t.strip()
                                for t in re.split(r"[,，\s]+", tag_text)
                                if t.strip()
                            ]

                    problems.append({
                        "id": problem_id,
                        "title": title,
                        "url": url,
                        "difficulty": difficulty,
                        "tags": tags,
                    })

                if problems:
                    return problems

        except ImportError:
            pass

        # ── Strategy 2: Regex table parsing ────────────────────
        table_m = re.search(
            r"<table[^>]*>(.*?)</table>",
            html, re.DOTALL | re.IGNORECASE,
        )
        if table_m:
            table_html = table_m.group(1)

            # Determine difficulty column index from headers
            difficulty_idx: Optional[int] = None
            thead_m = re.search(
                r"<thead[^>]*>(.*?)</thead>",
                table_html, re.DOTALL | re.IGNORECASE,
            )
            header_section = thead_m.group(1) if thead_m else table_html
            headers = re.findall(
                r"<th[^>]*>(.*?)</th>",
                header_section, re.DOTALL | re.IGNORECASE,
            )
            for i, h in enumerate(headers):
                text = re.sub(r"<[^>]+>", "", h).strip()
                if "难度" in text:
                    difficulty_idx = i
                    break

            # Parse data rows (prefer tbody, fallback to all rows)
            tbody_m = re.search(
                r"<tbody[^>]*>(.*?)</tbody>",
                table_html, re.DOTALL | re.IGNORECASE,
            )
            rows_section = tbody_m.group(1) if tbody_m else table_html

            rows = re.findall(
                r"<tr[^>]*>(.*?)</tr>",
                rows_section, re.DOTALL | re.IGNORECASE,
            )

            for row_html in rows:
                if len(problems) >= max_count:
                    break

                tds = re.findall(
                    r"<td[^>]*>(.*?)</td>",
                    row_html, re.DOTALL | re.IGNORECASE,
                )
                if len(tds) < 2:
                    continue

                # Find problem link
                link_m = re.search(
                    r'<a[^>]*href="(/acm/problem/(\d+))"[^>]*>(.*?)</a>',
                    row_html, re.DOTALL | re.IGNORECASE,
                )
                if not link_m:
                    continue

                problem_id = link_m.group(2)
                if problem_id in seen:
                    continue
                seen.add(problem_id)

                title = re.sub(r"<[^>]+>", "", link_m.group(3)).strip()
                url = f"{NowCoderCrawler.BASE_URL}{link_m.group(1)}"

                # Extract difficulty by column index
                difficulty = ""
                if difficulty_idx is not None and difficulty_idx < len(tds):
                    difficulty = re.sub(r"<[^>]+>", "", tds[difficulty_idx]).strip()

                problems.append({
                    "id": problem_id,
                    "title": title,
                    "url": url,
                    "difficulty": difficulty,
                    "tags": [],
                })

            if problems:
                return problems

        # ── Strategy 3: Simple link extraction (ultimate fallback) ──
        link_pattern = re.compile(
            r'<a[^>]*href="(/acm/problem/(\d+))"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )

        for m in link_pattern.finditer(html):
            problem_id = m.group(2)
            if problem_id in seen:
                continue
            seen.add(problem_id)

            title = re.sub(r"<[^>]+>", "", m.group(3)).strip()
            problems.append({
                "id": problem_id,
                "title": title,
                "url": f"{NowCoderCrawler.BASE_URL}{m.group(1)}",
                "difficulty": "",
                "tags": [],
            })

            if len(problems) >= max_count:
                break

        return problems


# ──────────────────────────────────────────────
# Helper functions for CLI
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
            error="Prisma client not available. Install with: pip install prisma, then run: prisma generate",
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


def _save_result(crawler: NowCoderCrawler, data, sub_dir: str, label: str) -> None:
    """Save fetched data to a timestamped JSON file under data/raw/{platform}/{sub_dir}/."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_label = str(label).replace("/", "_").replace("\\", "_")
    filename = f"{today}_{safe_label}.json"
    crawler.save_json(data, filename=filename, sub_dir=f"{crawler.PLATFORM}/{sub_dir}")


def main(argv: Optional[list] = None) -> None:
    """CLI entry point for the NowCoder crawler.

    Two modes are supported:

    * **NestJS mode** – ``--input`` receives a JSON string with all
      parameters (``action``, ``uid``, ``tags``, ``count``).
    * **CLI mode** – each parameter is supplied via its own argparse flag.

    Output is always a single JSON object printed to stdout.
    """
    parser = argparse.ArgumentParser(description="NowCoder crawler CLI")
    parser.add_argument(
        "--action",
        choices=["fetch_problems", "fetch_user", "fetch_records", "fetch_detail", "fetch_solutions", "import"],
        default=None,
        help="Crawl action to execute",
    )
    parser.add_argument("--uid", default=None, help="User ID / handle for user actions")
    parser.add_argument("--sid", default=None, help="Source ID for fetch_detail / fetch_solutions (problem ID)")
    parser.add_argument("--tags", default=None, help="Tag for filtering problems")
    parser.add_argument("--count", type=int, default=50, help="Max items to fetch")
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
                platform="nowcoder",
            )
            sys.exit(1)
    else:
        if not args.action:
            _emit(
                success=False,
                error="Either --action or --input is required",
                platform="nowcoder",
            )
            sys.exit(1)
        params = {
            "action": args.action,
            "uid": args.uid,
            "sid": args.sid,
            "tags": args.tags,
            "count": args.count,
        }

    action: str = params.get("action", "")
    if not action:
        _emit(success=False, error="Missing 'action' in parameters", platform="nowcoder")
        sys.exit(1)

    # ── execute ────────────────────────────────────────────────
    crawler = NowCoderCrawler()
    executor = CrawlerExecutor(crawler)

    try:
        if action == "fetch_user":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_user")
            result = executor.execute("fetch_user_profile", str(uid))
            if result.success and result.data:
                _save_result(crawler, result.data, "profiles", str(uid))

        elif action == "fetch_problems":
            tag = params.get("tags", "")
            count = int(params.get("count", 50))
            skip_ids = set(params.get("skip_ids", []))
            fetch_count = max(count + len(skip_ids), count * 3)
            # Paginate to collect enough new (non-skipped) problems
            all_items = []
            page = 1
            max_pages = (fetch_count // 50) + 5
            while len(all_items) < fetch_count and page <= max_pages:
                result = executor.execute(
                    "fetch_problems_by_tag", str(tag), fetch_count, page
                )
                if not result.success or not result.data:
                    break
                for p in result.data:
                    pid = str(p.get("id") or p.get("pid") or "")
                    if pid not in skip_ids:
                        all_items.append(p)
                        if len(all_items) >= fetch_count:
                            break
                if len(result.data) < 50:
                    break  # last page
                page += 1
            new_items = all_items[:count]
            # Enrich with full detail (scrape each problem page)
            enriched = []
            list_tag = params.get("tags", "")
            for prob in new_items:
                # Preserve tags/difficulty from list page if already present
                list_tags = prob.get("tags") or []
                if isinstance(list_tags, str):
                    list_tags = [list_tags]
                list_difficulty = prob.get("difficulty")
                pid = str(prob.get("id") or prob.get("pid") or "")
                if pid:
                    detail = executor.execute("fetch_problem", pid)
                    if detail and detail.success and detail.data:
                        merged = dict(detail.data)
                        if not merged.get("tags"):
                            if list_tags:
                                merged["tags"] = list_tags
                            elif list_tag:
                                merged["tags"] = [list_tag]
                        if not merged.get("difficulty") and list_difficulty:
                            merged["difficulty"] = list_difficulty
                        if list_difficulty:
                            merged["difficulty_raw"] = list_difficulty
                        enriched.append(merged)
                    else:
                        prob_copy = dict(prob)
                        if not prob_copy.get("tags"):
                            if list_tags:
                                prob_copy["tags"] = list_tags
                            elif list_tag:
                                prob_copy["tags"] = [list_tag]
                        if list_difficulty:
                            prob_copy["difficulty_raw"] = list_difficulty
                        enriched.append(prob_copy)
                else:
                    prob_copy = dict(prob)
                    if not prob_copy.get("tags"):
                        if list_tags:
                            prob_copy["tags"] = list_tags
                        elif list_tag:
                            prob_copy["tags"] = [list_tag]
                    if list_difficulty:
                        prob_copy["difficulty_raw"] = list_difficulty
                    enriched.append(prob_copy)
            result = CrawlResult(success=True, data=enriched, source=result.source)
            _save_result(crawler, result.data, "problems", str(tag) or "all")

        elif action == "fetch_records":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_records")
            result = executor.execute("fetch_user_records", str(uid))
            if result.success and result.data:
                _save_result(crawler, result.data, "records", str(uid))

        elif action == "fetch_detail":
            sid = params.get("sid") or params.get("uid", "")
            if not sid:
                raise ValueError("--sid is required for fetch_detail")
            result = executor.execute("fetch_problem", str(sid))
            if result.success and result.data:
                _save_result(crawler, result.data, "problems", str(sid))

        elif action == "fetch_solutions":
            sid = params.get("sid") or params.get("uid", "")
            if not sid:
                raise ValueError("--sid is required for fetch_solutions")
            result = executor.execute("fetch_solutions", str(sid))
            if result.success and result.data:
                _save_result(crawler, result.data, "solutions", str(sid))

        elif action == "import":
            result = _run_import(crawler.PLATFORM)

        else:
            result = CrawlResult(success=False, error=f"Unknown action: {action}")

        _emit(
            success=result.success,
            data=result.data,
            error=result.error,
            platform=crawler.PLATFORM,
        )
    except Exception as exc:
        _emit(success=False, error=str(exc), platform=crawler.PLATFORM)
        sys.exit(1)
    finally:
        crawler.close()


def _emit(
    success: bool,
    platform: str = "nowcoder",
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
    print(json.dumps(payload, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
