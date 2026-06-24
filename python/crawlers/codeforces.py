"""
Codeforces platform crawler.

Uses the official Codeforces API (https://codeforces.com/api).
No browser fallback needed — CF has a stable, well-documented REST API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Optional

from crawlers.base import BaseCrawler, CrawlResult, CrawlerExecutor, DataImporter

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# CodeforcesCrawler
# ──────────────────────────────────────────────


class CodeforcesCrawler(BaseCrawler):
    """Crawler for Codeforces (https://codeforces.com).

    All methods use ``_http_request`` exclusively — the official API
    is reliable and does not require browser-based fallback.
    """

    PLATFORM: str = "codeforces"

    # ── Problemset metadata cache ────────────────────────────────
    # _api("problemset.problems") returns all ~10 000 problems in a
    # single ~5 MB JSON blob.  fetch_problem() used to call it for
    # EVERY problem, re-downloading the same data N times.  This
    # cache holds the parsed list keyed by "contestId+index" so only
    # the first call hits the API; subsequent lookups are O(1) dict
    # reads.  TTL defaults to 1 hour — the problemset rarely changes
    # outside of contest times.
    _problemset_cache: dict[str, dict] | None = None
    _problemset_cache_ts: float = 0.0
    _problemset_cache_ttl: float = 3600.0  # seconds

    # ── Editorial caches ─────────────────────────────────────────
    # When using a headless browser to load editorial pages (so that
    # AJAX-loaded Tutorial text becomes available), the rendered HTML
    # is cached here so all problems in the same contest reuse the
    # same page load.  The URL → editorial-URL mapping is also cached
    # so _discover_editorial_url only runs once per contest.
    _editorial_cache: dict[str, str] = {}       # URL → rendered HTML
    _editorial_url_cache: dict[int, str | None] = {}  # contest_id → editorial_url
    _editorial_cache_lock: object = __import__('threading').Lock()
    _editorial_url_lock: object = __import__('threading').Lock()

    @classmethod
    def _clear_editorial_cache(cls) -> None:
        """Clear the editorial caches (for testing)."""
        with cls._editorial_cache_lock:
            cls._editorial_cache.clear()
        with cls._editorial_url_lock:
            cls._editorial_url_cache.clear()

    @classmethod
    def _clear_problemset_cache(cls) -> None:
        """Clear the problemset cache (for testing)."""
        cls._problemset_cache = None
        cls._problemset_cache_ts = 0.0

    def _get_cached_problemset_meta(
        self, contest_id: int, index: str
    ) -> dict | None:
        """Return metadata for a single problem from the local problemset
        cache, downloading and populating the cache on first use or after
        the TTL expires.
        """
        import time as _time
        now = _time.monotonic()

        # ── Populate cache if needed ──────────────────────────────
        cls = type(self)
        if (
            cls._problemset_cache is None
            or (now - cls._problemset_cache_ts) > cls._problemset_cache_ttl
        ):
            logger.info("Downloading full problemset for local cache…")
            api_result = self._api("problemset.problems")
            if not api_result.success:
                logger.warning(
                    "Failed to populate problemset cache: %s",
                    api_result.error,
                )
                return None

            raw = api_result.data
            if not isinstance(raw, dict):
                logger.warning("Unexpected problemset response format")
                return None

            problems: list[dict] = raw.get("problems", [])
            cache: dict[str, dict] = {}
            for p in problems:
                cid = p.get("contestId")
                idx = p.get("index")
                if cid is not None and idx is not None:
                    cache[f"{cid}{idx}"] = p
            cls._problemset_cache = cache
            cls._problemset_cache_ts = now
            logger.info(
                "Problemset cache loaded: %d problems",
                len(cache),
            )

        return cls._problemset_cache.get(f"{contest_id}{index}")

    # ── class constants ─────────────────────────────────────────

    API_URL: str = "https://codeforces.com/api"

    @staticmethod
    def _default_qps() -> float:
        """Codeforces allows ~5 requests per second in practice."""
        return 5.0

    @staticmethod
    def _curl_request(url: str, retry_count: int = 0) -> CrawlResult:
        """Fetch a URL via system curl (subprocess).

        Python HTTP libraries (requests, urllib3, DrissionPage) are
        blocked by Cloudflare on codeforces.com, but system curl (which
        uses Schannel TLS on Windows) bypasses the block.

        Returns a CrawlResult with ``data={"text": html}`` on success.
        """
        import subprocess

        try:
            proc = subprocess.run(
                [
                    "curl", "-sL",
                    "--max-time", "15",   # 15 s is enough for a CF page
                    "--connect-timeout", "10",
                    "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "-H", "Accept: text/html,application/xhtml+xml",
                    "-H", "Accept-Language: en-US,en;q=0.9",
                    url,
                ],
                capture_output=True,
                timeout=20,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return CrawlResult(
                success=False,
                error=f"curl failed: {exc}",
                source="http",
                retry_count=retry_count,
            )
            return CrawlResult(
                success=False,
                error=f"curl failed: {exc}",
                source="http",
                retry_count=retry_count,
            )

        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[:200]
            return CrawlResult(
                success=False,
                error=f"curl exit {proc.returncode}: {err}",
                source="http",
                retry_count=retry_count,
            )

        stdout = proc.stdout or b""
        html = stdout.decode("utf-8", errors="replace")
        if not html or len(html) < 500:
            return CrawlResult(
                success=False,
                error=f"curl returned only {len(html)} bytes",
                source="http",
                retry_count=retry_count,
            )

        return CrawlResult(
            success=True,
            data={"text": html},
            source="http",
            retry_count=retry_count,
        )

    # ── helpers ─────────────────────────────────────────────────

    def _api(self, method: str, **params: str) -> CrawlResult:
        """Call a Codeforces API method with query parameters.

        Args:
            method: API method path (e.g. ``"user.info"``).
            **params: Query-string parameters.

        Returns:
            CrawlResult with the API ``result`` field as data, or an
            error payload when ``status != "OK"``.
        """
        url = f"{self.API_URL}/{method}"
        # Build query string from non-None params.
        query_parts = [f"{k}={v}" for k, v in params.items() if v is not None]
        if query_parts:
            url += "?" + "&".join(query_parts)

        logger.debug("CF API call: %s", url)
        result = self._http_request(url)
        if not result.success:
            return result

        # Codeforces wraps every response in {"status": "...", "result": ...}.
        raw = result.data
        if isinstance(raw, dict):
            if raw.get("status") != "OK":
                return CrawlResult(
                    success=False,
                    error=raw.get("comment", "CF API returned non-OK status"),
                    source="http",
                    retry_count=result.retry_count,
                )
            return CrawlResult(
                success=True,
                data=raw.get("result"),
                source="http",
                retry_count=result.retry_count,
            )
        return result  # non-dict response is unexpected but forwarded

    # ── abstract method implementations ─────────────────────────

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch a Codeforces user's public profile.

        GET /api/user.info?handles={uid}

        Args:
            uid: Codeforces handle (case-sensitive).

        Returns:
            CrawlResult whose ``data`` is the user info dict (or None on failure).
        """
        result = self._api("user.info", handles=uid)
        if result.success and isinstance(result.data, list) and len(result.data) > 0:
            # CF returns a list of users; extract the first one.
            return CrawlResult(
                success=True,
                data=result.data[0],
                source="http",
                retry_count=result.retry_count,
            )
        if result.success and isinstance(result.data, dict):
            return result
        if result.success:
            return CrawlResult(
                success=False,
                error=f"User '{uid}' not found or empty response",
                source="http",
                retry_count=result.retry_count,
            )
        return result

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch submissions for a Codeforces user.

        GET /api/user.status?handle={uid}&from=1&count=1000

        CF does not expose a server-side ``since`` filter so the
        parameter is accepted but ignored; callers should filter
        client-side if needed.

        Args:
            uid: Codeforces handle.
            since: *Ignored* — kept for interface compatibility.

        Returns:
            CrawlResult whose ``data`` is a list of submission dicts.
        """
        result = self._api(
            "user.status",
            handle=uid,
            **{"from": "1", "count": "1000"},
        )
        return result

    def fetch_problem(
        self, source_id: str, meta: dict | None = None
    ) -> CrawlResult:
        """Fetch problem metadata + full statement.

        1. Get metadata (rating, tags, etc.) from the CF API.
        2. Scrape the problem statement from the HTML page.

        *source_id* is expected in the form ``"<contestId><index>"``
        (e.g. ``"1742E"``).

        Args:
            source_id: Problem identifier (e.g. ``"1742E"``).
            meta: Optional pre-fetched metadata from the problemset API.
                  When provided (e.g. from ``fetch_problems_by_tag``),
                  the API call is skipped entirely.

        Returns:
            CrawlResult with problem dict including ``description``,
            ``input_format``, ``output_format``, ``note`` fields.
        """
        contest_id, index = self._parse_problem_id(source_id)
        if contest_id == 0:
            return CrawlResult(
                success=False,
                error=f"Cannot parse problem ID: {source_id}",
                source="http",
            )

        # ── Step 1: get API metadata (cached, or passed in) ─────
        if meta is None:
            meta = self._get_cached_problemset_meta(contest_id, index)
        if meta is None:
            return CrawlResult(
                success=False,
                error=f"Problem '{source_id}' not found in problemset",
                source="http",
            )

        # ── Step 2: scrape HTML for problem statement ──────────
        # Use curl (subprocess) because Python HTTP libraries
        # (requests, urllib3, DrissionPage) are blocked by CF's
        # Cloudflare while system curl bypasses it via Schannel TLS.
        problem_url = (
            f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        )
        logger.debug("CF scraping problem page: %s", problem_url)

        page_result = self._curl_request(problem_url)
        if not page_result.success:
            logger.warning(
                "CF problem page curl failed for %s: %s",
                source_id, page_result.error,
            )
            return CrawlResult(
                success=False,
                error=page_result.error,
                source="http",
                retry_count=page_result.retry_count,
            )

        html = self._extract_html_text(page_result)
        if not html:
            logger.warning(
                "CF _extract_html_text returned empty for %s (source: %s)",
                source_id, page_result.source,
            )
            return CrawlResult(
                success=False,
                error="Empty HTML content — page fetch succeeded but yielded no text",
                source=page_result.source,
                retry_count=page_result.retry_count,
            )

        # ── Decode HTML entities in raw HTML before extraction ────
        # Codeforces pages contain entities like &amp; &lt; &gt; &quot;
        # that are not always decoded by BeautifulSoup's get_text().
        import html as _html
        html = _html.unescape(html)

        # ── Step 3: extract sections ───────────────────────────
        limits = self._cf_extract_limits(html)
        description = self._cf_extract(html, "problem-statement",
                                        skip_header=True)
        input_fmt = self._cf_extract(html, "input-specification")
        output_fmt = self._cf_extract(html, "output-specification")
        note = self._cf_extract(html, "note")
        samples = self._cf_extract_samples(html)

        return CrawlResult(
            success=True,
            data={
                **meta,
                "limits": limits,
                "description": description,
                "input_format": input_fmt,
                "output_format": output_fmt,
                "note": note,
                "samples": samples,
                "source_url": f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
            },
            source=page_result.source,
            retry_count=page_result.retry_count,
        )


    # ── HTML scraping helpers ──────────────────────────────────

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
    def _cf_extract(html: str, class_name: str,
                    skip_header: bool = False) -> str:
        """Extract text from a CF problem page section by CSS class.

        Uses BeautifulSoup to parse the div, strip unwanted children
        (header, scripts), and return the cleaned inner text.
        """
        import re as _re

        try:
            from bs4 import BeautifulSoup as _BS, NavigableString as _NS
        except ImportError:
            return ""

        soup = _BS(html, "html.parser")

        # ── Shared helper: extract math text, remove math wrappers ──
        def _extract_math(root_el):
            """Replace MathJax wrappers with their <nobr> text, then
            decompose all remaining math-related elements so each
            math expression appears exactly once in the final text.

            CF pages have up to 3 representations of the same math:
              1) <span class="MathJax_Preview">…</span>     (preview)
              2) <script type="math/tex">…</script>         (LaTeX src)
              3) <span class="MathJax">…<nobr>…</nobr>…</span> (rendered)
            Only the <nobr> text is kept; everything else is discarded.
            """
            # Preprocess ^{\text{…}} / _{\text{…}} BEFORE $…$ wrapping,
            # otherwise the $ delimiters prevent the replace from matching.
            _TEX_BEFORE = {
                r'^{\text{∗}}': r'^{\ast}',
                r'^{\text{*}}': r'^{\ast}',
                r'^{\text{†}}': r'^{\dagger}',
                r'^{\text{T}}': r'^{\mathsf{T}}',
            }
            def _preprocess_tex(t):
                for old, new in _TEX_BEFORE.items():
                    t = t.replace(old, new)
                t = _re.sub(r'\^\{?\\text\{([^}]*)\}\}?', r'^{\1}', t)
                t = _re.sub(r'_\{?\\text\{([^}]*)\}\}?', r'_{\1}', t)
                return t

            # Replace each .MathJax wrapper with its <nobr> text.
            # Using get_text("", strip=True) preserves subscripts
            # like "p_i" instead of splitting into "p i".
            # LaTeX expressions (containing \) get $…$ wrapping.
            for math_el in root_el.select(".MathJax"):
                nobr = math_el.find("nobr")
                if nobr:
                    t = nobr.get_text("", strip=True)
                    if t:
                        t = _preprocess_tex(t)
                        if _re.search(r'\\[a-zA-Z]', t):
                            math_el.replace_with(f" ${t}$ ")
                        else:
                            math_el.replace_with(f" {t} ")
                        continue
                # No <nobr> — try extracting LaTeX source from
                # <script type="math/tex"> or <annotation>
                tex = None
                script_tex = math_el.select_one(
                    "script[type='math/tex']")
                if script_tex:
                    tex = script_tex.get_text("", strip=True)
                if not tex:
                    annotation = math_el.select_one("annotation")
                    if annotation:
                        tex = annotation.get_text("", strip=True)
                if tex:
                    tex = _preprocess_tex(tex)
                    math_el.replace_with(f" ${tex}$ ")
                else:
                    math_el.decompose()

            # Decompose remaining math artifacts (preview spans,
            # LaTeX sources, assistive MathML).
            for sel in (".MathJax_Preview",
                         "script[type='math/tex']",
                         ".MJX_Assistive_MathML"):
                for el in root_el.select(sel):
                    el.decompose()

        # ── Shared helper: unwind inline formatting elements ──────
        def _unwind_inline(root_el):
            """Replace inline formatting elements (tex-font-style-*,
            <b>, <i>, <tt>, <em>, <strong>) with their text content
            so they don't cause spurious line breaks in get_text().
            Also unwrap <a> links (keep text, drop href).
            Convert <li> to markdown-style list items.
            """
            inline_selectors = (
                ".tex-font-style-tt",
                ".tex-font-style-bf",
                ".tex-font-style-it",
                "b", "i", "tt", "em", "strong", "u", "s",
            )
            for sel in inline_selectors:
                for el in root_el.select(sel):
                    el.unwrap()
            # Unwrap <a> tags (keep link text, drop URL)
            for a in root_el.find_all("a"):
                a.unwrap()
            # Convert <li> → markdown list item
            for li in root_el.find_all("li"):
                li.insert_before(soup.new_string("\n- "))
                li.unwrap()
            # Remove <ol>/<ul> wrappers (keep their children)
            for list_tag in root_el.find_all(["ol", "ul"]):
                list_tag.unwrap()

        def _merge_adjacent_strings(root_el):
            """Merge adjacent NavigableString nodes into one.
            unwrap() leaves sibling NavigableStrings separate;
            get_text('\\n') then splits them into individual lines,
            and the orphan merge (with space) would insert unwanted
            spaces between subscript fragments (e.g. p + i = 'p i'
            instead of 'pi' from a <i> wrapper).

            Only iterate over tag elements (skip NavigableString and
            other leaf nodes) to avoid quadratic-traversal MemoryError
            on large MathJax-heavy CF pages.
            """
            from bs4 import NavigableString as _NS, Tag as _Tag
            for el in root_el.descendants:
                # Skip non-tag nodes — only tags can have children to merge.
                if not isinstance(el, _Tag):
                    continue
                if not el.contents:
                    continue
                i = 0
                while i < len(el.contents) - 1:
                    a, b = el.contents[i], el.contents[i + 1]
                    if isinstance(a, _NS) and isinstance(b, _NS):
                        a.replace_with(_NS(str(a) + str(b)))
                        b.extract()
                        # don't increment i; re-check merged string against next sibling
                    else:
                        i += 1

        if class_name == "problem-statement" and skip_header:
            # ── description-only extraction ──────────────────────
            root = soup.find("div", class_="problem-statement")
            if not root:
                return ""

            # Step 1: remove header BEFORE MathJax processing.
            # This ensures math inside the header is discarded
            # cleanly instead of leaking into the description.
            for sel in (".header", ".problem-header",
                         ".problem-statement-header"):
                for el in root.select(sel):
                    el.decompose()

            # Step 2: extract math from remaining content
            _unwind_inline(root)
            _extract_math(root)

            # Step 3: remove sub-sections we extract separately
            for sel in (".input-specification", ".output-specification",
                         ".note", ".sample-tests",
                         "script", "style"):
                for el in root.select(sel):
                    el.decompose()

            # Step 4: remove sidebars / tag-boxes
            for el in root.select(
                ".tag-box, .roundbox, .sidebar-menu, .second-level-menu"):
                el.decompose()

            _merge_adjacent_strings(root)
            text = root.get_text("\n", strip=True)
        else:
            # ── single-section extraction ─────────────────────────
            root = soup.find("div", class_=class_name)
            if not root:
                return ""

            _unwind_inline(root)
            _extract_math(root)

            for s in root.select("script, style"):
                s.decompose()

            _merge_adjacent_strings(root)
            text = root.get_text("\n", strip=True)

        # ── HTML entity decoding ────────────────────────────────────
        import html as _html
        text = _html.unescape(text)

        # ── whitespace cleanup ──────────────────────────────────────
        # Normalize Windows-style line endings
        text = _re.sub(r'\r\n|\r', '\n', text)
        # Convert CF MathJax delimiter $$$ → $ for KaTeX compatibility.
        # CF uses $$$ as its math delimiter.  Split on $$$ and rebuild:
        # odd-indexed segments are math.  Two cases:
        #   $$$x$$$           → $x$     (inline; odd seg = "x" non-empty)
        #   $$$$$$c$$$$$$     → $$c$$   (display; the empty odd segments
        #                                 on each side of c become the $$
        #                                 display fences)
        #   $$$A$$$$$$B$$$    → $A$$B$  (two adjacent inline blocks, merged
        #                                 to $AB$ by the step below so that
        #                                 orphaned superscripts like $^{\ast}$
        #                                 reattach to their base)
        # Regression: 2236G's ``a_{v_{l}} \oplus ... \geq (...)`` was wrapped
        # in $$$$$$...$$$$$$; the old $$$→$ + $$-merge approach treated the
        # display $$ fence as an adjacent-inline merge point and stripped it,
        # leaving bare LaTeX with no $ wrapping.
        _parts = text.split("$$$")
        _FENCE = "\x00MATHFENCE\x00"  # placeholder so display fences survive the merge regex
        _rebuilt = _parts[0]
        for _pi in range(1, len(_parts)):
            if _pi % 2 == 1:  # math segment
                _seg = _parts[_pi]
                if _seg.strip() == "":
                    _rebuilt += _FENCE  # empty math → display fence
                else:
                    _rebuilt += "$" + _seg + "$"
            else:  # text segment
                _rebuilt += _parts[_pi]
        text = _rebuilt
        # Merge adjacent inline blocks ($A$$B$ → $AB$).  The display-fence
        # placeholders contain no '$', so they never participate in this
        # pattern and stay intact.
        for _ in range(10):  # bounded; realistic max depth is ~5
            new_text = _re.sub(r'\$([^$]+?)\$\$([^$]+?)\$', r'$\1\2$', text)
            if new_text == text:
                break
            text = new_text
        # Restore display fences → $$ (KaTeX display math)
        text = text.replace(_FENCE, "$$")
        # Collapse 2+ consecutive newlines → max 1
        text = _re.sub(r'\n{2,}', '\n', text)
        # Collapse whitespace-only lines into the surrounding newline
        text = _re.sub(r'\n[ \t]+\n', '\n', text)
        # Strip leading/trailing whitespace
        text = text.strip()
        # Normalize horizontal whitespace but preserve newlines
        text = _re.sub(r'[ \t]{2,}', ' ', text)

        # ── Merge orphaned inline fragments ──────────────────────
        # BS4's unwrap() doesn't merge adjacent NavigableStrings,
        # so get_text("\n") puts each former inline element on its
        # own line.  Merge short / lowercase-starting / punctuation
        # lines with the previous line to reconstruct sentences.
        _lines = text.split('\n')
        _merged = []
        for _l in _lines:
            _s = _l.strip()
            # Don't merge new paragraphs (start with capital or section marker).
            # Also exclude standalone list-item markers ("-") produced by
            # _unwind_inline from <li> conversion — merging them into the
            # previous line destroys the list structure and causes missing
            # newlines before bullet items (regression: CF 2233B).
            if (_merged and _s
                and not _re.match(r'^[A-Z\[【]', _s)
                and not _s.startswith('**')
                and _s != '-'
                and _merged[-1].strip()):
                _merged[-1] = _merged[-1] + _s
            else:
                _merged.append(_l)
        text = '\n'.join(_merged)

        # ── Collapse single-char spacing (e.g. "H e l p" → "Help") ──
        # When HTML wraps individual characters in tex-font-style-* tags,
        # unwrap() leaves spaces between them.  Compress runs of
        # space-separated single letters on the same line.
        text = _re.sub(
            r'\b([a-zA-Z]) (?=[a-zA-Z](?:\s|$))',
            r'\1',
            text,
        )
        # Also collapse space-separated digits (CF superscript artifacts)
        text = _re.sub(
            r'\b([0-9]) (?=[0-9](?:\s|$))',
            r'\1',
            text,
        )

        # ── MathJax triplication dedup ─────────────────────────────
        # Browser-rendered MathJax produces 3 copies of each math symbol
        # separated by blank lines (e.g. \n1\n\n≤\n\nx\n\n1 \le x\n).
        # Collect math-fragment "islands" (skipping blank lines between
        # them), keep only the best (LaTeX-rich) variant.
        MATH_SPECIAL = _re.compile(
            r'[\\_{}^|×∙∣≤≥±∞∑∏∫∂∇√≈≠←→⇒⇔⋅⋯⋮⋱'
            r'α-ωΓ-Ω​]'
        )
        def _is_math_fragment(s: str) -> bool:
            if not s or len(s) > 120:
                return False
            if s[0] in '[【#':
                return False
            if _re.search(r'[一-鿿]', s):
                return False
            if len(s) <= 3:
                return bool(_re.match(
                    r'^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&\'\"'
                    r'×∙∣≤≥±∞∑∏∫∂∇√∞≈≠←→⇒⇔⋅⋯⋮⋱'
                    r'α-ωΓ-Ω​]+$', s))
            if not MATH_SPECIAL.search(s):
                return False
            return bool(_re.match(
                r'^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&\'\"'
                r'×∙∣≤≥±∞∑∏∫∂∇√∞≈≠←→⇒⇔⋅⋯⋮⋱'
                r'α-ωΓ-Ω​]+$', s))

        lines = text.split('\n')
        merged = []
        i = 0
        while i < len(lines):
            t = lines[i].strip()
            if t == '' or not _is_math_fragment(t):
                merged.append(lines[i])
                i += 1
                continue

            # Collect a math island — skip blank lines between fragments
            island = [lines[i]]
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                if s == '':
                    peek = i + 1
                    while peek < len(lines) and lines[peek].strip() == '':
                        peek += 1
                    if peek < len(lines) and _is_math_fragment(
                        lines[peek].strip()
                    ):
                        i += 1  # skip blank between math fragments
                        continue
                    break  # blank not between math → end island
                if _is_math_fragment(s):
                    island.append(lines[i])
                    i += 1
                else:
                    break

            if len(island) >= 3:
                latex_variants = [
                    l.strip() for l in island
                    if _re.search(r'\\[a-zA-Z]', l)
                ]
                if latex_variants:
                    best = max(latex_variants, key=len)
                    merged.append(best)
                else:
                    unique = list(dict.fromkeys(
                        l.strip() for l in island
                    ))
                    merged.append(max(unique, key=len))
            else:
                merged.extend(l.strip() for l in island)

        text = '\n'.join(merged)

        # ── Preprocess ^{\text{…}} / _{\text{…}} ────────────────────
        # The bare LaTeX wrapper below can't handle nested braces in
        # ^{\text{…}} — the inner } would terminate the outer {…} group
        # prematurely.  Coerce these to plain ^{…} / _{…} before
        # wrapping them.  Also handle single-char text bodies like
        # ^{\text{∗}} → \mul (Unicode), and ^{\text{†}} → \dagger.
        _TEXT_REPLACE = {
            r'^{\text{∗}}': r'^{\ast}',
            r'^{\text{*}}': r'^{\ast}',
            r'^{\text{†}}': r'^{\dagger}',
            r'^{\text{T}}': r'^{\mathsf{T}}',
        }
        for _old, _new in _TEXT_REPLACE.items():
            text = text.replace(_old, _new)
        text = _re.sub(
            r'\^\{?\\text\{([^}]*)\}\}?',
            r'^{\1}',
            text,
        )
        text = _re.sub(
            r'_\{?\\text\{([^}]*)\}\}?',
            r'_{\1}',
            text,
        )

        # ── Wrap bare LaTeX expressions in $…$ for KaTeX ───────────
        # Browser-rendered pages have bare LaTeX from <nobr> text
        # (e.g. ^{\text{∗}}, \le, p_{i}) without $ delimiters.
        # Desktop pages already have $$ from the $$$ → $ conversion
        # above, so this is skipped.
        if '$' not in text:
            text = _re.sub(
                r'(\\[a-zA-Z]+(?:\{[^}]*\})*)',
                r'$\1$',
                text,
            )
            text = text.replace("$$", "$")

        # ── Final whitespace normalisation ────────────────────────
        text = _re.sub(r'\n{3,}', '\n\n', text).strip()
        return text

    @staticmethod
    def _cf_extract_samples(html: str) -> list:
        """Extract sample test cases from CF problem page.

        Handles two possible layouts:

        Layout A (classic):
          <div class="sample-test">
            <div class="input"><div class="title">...</div><pre>...</pre></div>
            <div class="output"><div class="title">...</div><pre>...</pre></div>
          </div>

        Layout B (newer):
          <div class="sample-test">
            <div class="sample-test"><pre>input1</pre><pre>output1</pre>...</div>
          </div>

        Returns a list of ``[input_str, output_str]`` pairs.
        """
        try:
            from bs4 import BeautifulSoup as _BS
        except ImportError:
            return []

        soup = _BS(html, "html.parser")
        samples_div = soup.find("div", class_="sample-test")
        if not samples_div:
            return []

        samples = []

        # Layout A: input/output div pairs
        inputs = samples_div.find_all("div", class_="input")
        outputs = samples_div.find_all("div", class_="output")
        if inputs and outputs:
            for inp, out in zip(inputs, outputs):
                inp_pre = inp.find("pre")
                out_pre = out.find("pre")
                inp_text = inp_pre.get_text("\n", strip=True) if inp_pre else ""
                out_text = out_pre.get_text("\n", strip=True) if out_pre else ""
                if inp_text or out_text:
                    samples.append([inp_text, out_text])
            return samples

        # Layout B: nested .sample-test with bare <pre> tags (input/output interleaved)
        inner = samples_div.find("div", class_="sample-test")
        if inner:
            pres = inner.find_all("pre", recursive=False)
            for i in range(0, len(pres) - 1, 2):
                inp_text = pres[i].get_text("\n", strip=True) if i < len(pres) else ""
                out_text = pres[i + 1].get_text("\n", strip=True) if i + 1 < len(pres) else ""
                if inp_text or out_text:
                    samples.append([inp_text, out_text])
            if samples:
                return samples

        # Fallback: any <pre> tags at top level, paired
        pres = samples_div.find_all("pre", recursive=False)
        for i in range(0, len(pres) - 1, 2):
            inp_text = pres[i].get_text("\n", strip=True)
            out_text = pres[i + 1].get_text("\n", strip=True)
            if inp_text or out_text:
                samples.append([inp_text, out_text])

        # ── HTML entity decoding for all sample texts ────────────
        import html as _html
        samples = [[_html.unescape(s[0]), _html.unescape(s[1])] for s in samples]

        return samples

    @staticmethod
    def _cf_extract_limits(html: str) -> dict | None:
        """Extract time and memory limits from CF problem page header.

        CF pages have structured header divs:
          <div class="time-limit">...2 seconds</div>
          <div class="memory-limit">...256 megabytes</div>

        Returns a dict ``{time: <ms>, memory: <MB>}`` or None if
        extraction fails.
        """
        import re as _re

        try:
            from bs4 import BeautifulSoup as _BS
        except ImportError:
            return None

        soup = _BS(html, "html.parser")
        header = soup.find("div", class_="header")
        if not header:
            return None

        def _parse_time(text: str) -> int | None:
            """Parse "2 seconds" → 2000 (ms)."""
            m = _re.search(r'(\d+(?:\.\d+)?)\s*seconds?', text, _re.IGNORECASE)
            if m:
                return int(float(m.group(1)) * 1000)
            return None

        def _parse_memory(text: str) -> int | None:
            """Parse "256 megabytes" → 256 (MB)."""
            m = _re.search(r'(\d+(?:\.\d+)?)\s*megabytes?', text, _re.IGNORECASE)
            if m:
                return int(float(m.group(1)))
            # Also handle "gigabytes"
            m = _re.search(r'(\d+(?:\.\d+)?)\s*gigabytes?', text, _re.IGNORECASE)
            if m:
                return int(float(m.group(1)) * 1024)
            return None

        time_limit = None
        memory_limit = None

        time_div = header.find("div", class_="time-limit")
        if time_div:
            time_limit = _parse_time(time_div.get_text("", strip=True))

        mem_div = header.find("div", class_="memory-limit")
        if mem_div:
            memory_limit = _parse_memory(mem_div.get_text("", strip=True))

        if time_limit is not None or memory_limit is not None:
            return {"time": time_limit, "memory": memory_limit}
        return None

    @staticmethod
    def _editorial_html_to_markdown(html: str) -> str:
        """Convert CF editorial HTML to Markdown suitable for frontend rendering.

        Handles $$$ → $ math delimiters, <pre> → ``` fences, inline formatting,
        and list structures — the same transformations that _cf_extract applies
        to problem statements, adapted for editorial/blog pages.
        """
        import re as _re

        try:
            from bs4 import BeautifulSoup as _BS, NavigableString as _NS
        except ImportError:
            return html

        soup = _BS(html, "html.parser")

        # ── MathJax: extract <nobr> text from .MathJax spans ──────
        for math_el in soup.select(".MathJax"):
            nobr = math_el.find("nobr")
            if nobr:
                t = nobr.get_text("", strip=True)
                if t:
                    if _re.search(r'\\[a-zA-Z]', t):
                        math_el.replace_with(f" ${t}$ ")
                    else:
                        math_el.replace_with(f" {t} ")
                    continue
            math_el.decompose()
        for sel in (".MathJax_Preview", "script[type='math/tex']",
                     ".MJX_Assistive_MathML"):
            for el in soup.select(sel):
                el.decompose()

        # ── Code blocks: <pre> → ``` fences ──────────────────────
        for pre in soup.find_all("pre"):
            lang = ""
            code_el = pre.find("code")
            if code_el:
                cls = code_el.get("class", [])
                if isinstance(cls, str):
                    cls = [cls]
                for c in cls:
                    if c.startswith("language-") or c.startswith("lang-"):
                        lang = c.split("-", 1)[1]
                        break
            text = pre.get_text()
            # Strip CF "Copy" button text
            text = _re.sub(r'\bCopy\b', '', text)
            fence = f"```{lang}" if lang else "```"
            pre.replace_with(f"\n{fence}\n{text.strip()}\n```\n")

        # ── Inline code: <code> → backticks ──────────────────────
        for code in soup.find_all("code"):
            if code.find_parent("pre"):
                continue  # already handled
            code.replace_with(f"`{code.get_text()}`")

        # ── Inline formatting ─────────────────────────────────────
        for b in soup.find_all(["b", "strong"]):
            b.replace_with(f"**{b.get_text()}**")
        for i in soup.find_all(["i", "em"]):
            i.replace_with(f"*{i.get_text()}*")

        # ── Lists ─────────────────────────────────────────────────
        for li in soup.find_all("li"):
            li.insert_before(_BS("", "html.parser").new_string("\n- "))
            li.unwrap()
        for tag in soup.find_all(["ul", "ol"]):
            tag.unwrap()

        # ── Headers ───────────────────────────────────────────────
        for h_level in range(1, 7):
            for h in soup.find_all(f"h{h_level}"):
                prefix = "#" * h_level
                h.insert_before(_BS("", "html.parser").new_string(
                    f"\n\n{prefix} "))
                h.insert_after("\n")
                h.unwrap()

        # ── Block elements → paragraph breaks ─────────────────────
        for p in soup.find_all(["p", "div"]):
            p.insert_after("\n\n")

        # ── Sub/sup → LaTeX ──────────────────────────────────────
        for sub in soup.find_all("sub"):
            sub.replace_with(f"_{{{sub.get_text()}}}")
        for sup in soup.find_all("sup"):
            sup.replace_with(f"^{{{sup.get_text()}}}")

        # ── Line breaks ──────────────────────────────────────────
        for br in soup.find_all("br"):
            br.replace_with("\n")

        # ── CF spoilers: remove "Tutorial is loading…" placeholders ──
        # The actual tutorial text is AJAX-loaded from /data/problemTutorial
        # (Cloudflare-protected, inaccessible to curl).  The placeholder div
        # contains no useful content; remove it.  The .spoiler-content wrapper
        # is unwrapped so its children (e.g. <pre> code blocks) are preserved.
        for spoiler_content in soup.select(".spoiler-content"):
            # Remove "Tutorial is loading..." placeholder divs
            for placeholder in spoiler_content.select(".problemTutorial"):
                placeholder.decompose()
            spoiler_content.unwrap()
        for spoiler_title in soup.select(".spoiler-title"):
            spoiler_title.unwrap()

        # ── Links: keep text, drop href ──────────────────────────
        for a in soup.find_all("a"):
            a.unwrap()

        # ── Strip remaining tags ──────────────────────────────────
        text = soup.get_text()

        # ── $$$ delimiter conversion (same as _cf_extract) ───────
        parts = text.split("$$$")
        FENCE = "\x00MATHFENCE\x00"
        rebuilt = parts[0]
        for pi in range(1, len(parts)):
            if pi % 2 == 1:
                seg = parts[pi]
                if seg.strip() == "":
                    rebuilt += FENCE
                else:
                    rebuilt += "$" + seg + "$"
            else:
                rebuilt += parts[pi]
        text = rebuilt
        # Merge adjacent inline blocks $A$$B$ → $AB$
        for _ in range(10):
            new_text = _re.sub(r'\$([^$]+?)\$\$([^$]+?)\$', r'$\1\2$', text)
            if new_text == text:
                break
            text = new_text
        text = text.replace(FENCE, "$$")

        # ── Whitespace normalisation ──────────────────────────────
        import html as _html
        text = _html.unescape(text)
        text = _re.sub(r"\r\n|\r", "\n", text)
        text = _re.sub(r"\n{3,}", "\n\n", text)
        text = _re.sub(r"[ \t]+\n", "\n", text)
        text = _re.sub(r"\n[ \t]+", "\n", text)
        text = _re.sub(r"[ \t]{2,}", " ", text)
        text = _re.sub(r"CopyCopyCopied!", "", text)
        return text.strip()

    @staticmethod
    def _discover_editorial_url(
        problem_url: str, contest_id: int
    ) -> str | None:
        """Find the editorial blog URL for a contest.

        Scrapes the problem page for blog entry links and checks the most
        recent ones for an editorial title matching the contest.

        The editorial is almost always in the "Recent Actions" sidebar,
        which shows ~10 most recent blog posts.  By scanning the first
        N unique entries (newest first), we reliably find it without
        fetching every blog link on the page.
        """
        import re as _re

        page = CodeforcesCrawler._curl_request(problem_url)
        if not page.success:
            return None
        html = CodeforcesCrawler._extract_html_text(page)
        if not html:
            return None

        # Collect unique blog entry IDs, preserving order (newest first).
        # Entries typically appear in the sidebar's "Recent Actions" list
        # before any other sections.
        blog_ids_deduped: list[int] = []
        seen: set[int] = set()
        for m in _re.finditer(r'/blog/entry/(\d+)', html):
            bid = int(m.group(1))
            if bid not in seen:
                seen.add(bid)
                blog_ids_deduped.append(bid)

        if not blog_ids_deduped:
            return None

        # Sort by entry ID descending (newest first) and limit to 20.
        # The editorial is always among the most recent blog posts; older
        # entries (2+ pages down in the sidebar) are noise.
        candidates = sorted(blog_ids_deduped, reverse=True)[:20]

        logger.info(
            "Scanning up to %d blog entries for editorial (contest %d)…",
            len(candidates), contest_id,
        )

        for bid in candidates:
            blog_url = f"https://codeforces.com/blog/entry/{bid}"
            result = CodeforcesCrawler._curl_request(blog_url)
            if not result.success:
                continue
            blog_html = CodeforcesCrawler._extract_html_text(result)
            if not blog_html:
                continue
            # Extract <title> from the first 8 KB
            head = blog_html[:8192]
            title_m = _re.search(
                r'<title>([^<]*)</title>', head, _re.IGNORECASE,
            )
            if not title_m:
                continue
            title = title_m.group(1)
            if "editorial" not in title.lower():
                continue

            # Verify contest ID appears in the page content.
            # CF editorial pages link to each problem via
            # /contest/{contest_id}/problem/{idx}, so this is a
            # reliable signal even for older editorials.
            if _re.search(
                rf'/contest/{contest_id}\b', blog_html
            ) or _re.search(
                rf'contestId[=:]\s*{contest_id}', blog_html
            ):
                logger.info("Found editorial: %s → %s", blog_url, title)
                return blog_url

        return None

    # ── Browser-based editorial fetching ─────────────────────────

    @classmethod
    def _fetch_editorial_rendered(cls, editorial_url: str) -> str | None:
        """Load an editorial page with a headless browser so that
        AJAX-loaded Tutorial text becomes available.

        Uses Scrapling's ``StealthyFetcher`` with Playwright Chromium.
        The rendered HTML is cached at class level so all problems in
        the same contest reuse the same page load.

        The cache lock is held during the (potentially slow) browser
        load.  This is deliberate: without it, every solver worker
        thread opens its own browser instance simultaneously, causing
        resource exhaustion and timeouts.  The wait is bounded to ~8 s
        and only happens once per editorial URL per process lifetime.

        Returns the fully-rendered HTML string, or None on failure.
        """
        import threading as _threading

        # ── Double-check cache under lock ────────────────────────
        with cls._editorial_cache_lock:
            if editorial_url in cls._editorial_cache:
                logger.debug(
                    "Editorial cache hit: %s", editorial_url,
                )
                return cls._editorial_cache[editorial_url]

        # ── Only one thread per URL reaches the loading section ──
        # The lock is re-acquired and HELD for the entire browser
        # load.  Other threads requesting the same URL will block at
        # the top of this method until the load completes and the
        # result is cached.
        with cls._editorial_cache_lock:
            # Re-check: another thread may have loaded while we
            # were waiting for the lock.
            if editorial_url in cls._editorial_cache:
                return cls._editorial_cache[editorial_url]

            try:
                from scrapling.fetchers import StealthyFetcher
            except ImportError:
                logger.warning(
                    "Scrapling not installed — falling back to static HTML"
                )
                cls._editorial_cache[editorial_url] = ""  # sentinel
                return None

            logger.info(
                "Loading editorial with headless browser: %s",
                editorial_url,
            )
            import time as _time
            t0 = _time.monotonic()

            try:
                proxy = getattr(cls, '_scrapling_proxy', None)
                if proxy:
                    StealthyFetcher.proxy = proxy

                page = StealthyFetcher.fetch(
                    f"{editorial_url}?locale=en",
                    headless=True,
                    network_idle=True,
                    timeout=30_000,
                )
                html = page.html_content if hasattr(page, 'html_content') else \
                       page.body.decode('utf-8', errors='replace')
            except Exception as exc:
                elapsed = _time.monotonic() - t0
                logger.warning(
                    "Headless browser fetch failed after %.1fs: %s",
                    elapsed, exc,
                )
                # Don't cache failures — next caller may succeed
                return None

            elapsed = _time.monotonic() - t0
            logger.info(
                "Editorial rendered in %.1fs (%d bytes)",
                elapsed, len(html),
            )
            cls._editorial_cache[editorial_url] = html
            return html

    @staticmethod
    def _parse_editorial_html(html: str, contest_id: int) -> dict:
        """Parse CF editorial HTML and extract per-problem solutions.

        Each problem in an editorial is structured as:
          <p><a href="/contest/{cid}/problem/{idx}">{cid}{idx} - Title</a></p>
          <p>Idea: ... Preparation: ...</p>
          <div class="spoiler">
            <b class="spoiler-title">Tutorial</b>
            <div class="spoiler-content">
              <div class="problemTutorial">Tutorial is loading...</div>
              <!-- tutorial text is AJAX-loaded, not in static HTML -->
            </div>
          </div>
          <div class="spoiler">
            <b class="spoiler-title">Implementation</b>
            <div class="spoiler-content">
              <pre><code>// actual solution code</code></pre>
            </div>
          </div>

        Returns a dict mapping problem index (e.g. ``"A"``, ``"E1"``) to
        a solution dict with ``author``, ``title``, ``content``, ``vote_count``.
        """
        import re as _re
        try:
            from bs4 import BeautifulSoup as _BS, Tag as _Tag
        except ImportError:
            return {}

        import html as _html

        soup = _BS(html, "html.parser")
        # Only the FIRST .ttypography is the main editorial content;
        # subsequent .ttypography divs are blog comments.
        ttypography = soup.select_one(".ttypography")
        if not ttypography:
            # Fallback: try .content container directly
            content_div = soup.select_one(".content")
            if content_div:
                ttypography = content_div.find("div", class_="ttypography")
        if not ttypography:
            return {}

        # Collect top-level Tag children — these are <p>, <div>, etc.
        # Skip NavigableStrings (whitespace between elements).
        children: list = [
            c for c in ttypography.children if isinstance(c, _Tag)
        ]

        # Find problem boundaries:
        # <p><a href="/contest/{cid}/problem/{idx}">...</a></p>
        # Some editorials use absolute URLs:
        # <p><a href="https://codeforces.com/contest/{cid}/problem/{idx}">...</a></p>
        problem_link_re = _re.compile(
            rf"(?:^|codeforces\.com)/contest/{contest_id}/problem/([A-Z]\d*)$"
        )
        boundaries: list = []  # (child_index, problem_index, header_text)
        for i, child in enumerate(children):
            if child.name != "p":
                continue
            # Some <p> contain multiple problem links (e.g. "C1, C2").
            # Collect ALL matching <a> tags, not just the first one.
            links = child.find_all(
                "a", href=_re.compile(
                    rf"(?:^|codeforces\.com)/contest/{contest_id}/problem/[A-Z]\d*$"
                )
            )
            for link in links:
                href = link.get("href", "")
                m = problem_link_re.search(href)
                if m:
                    boundaries.append((
                        i, m.group(1), link.get_text(strip=True),
                    ))

        if not boundaries:
            logger.debug(
                "No problem <a> links found in editorial for contest %d",
                contest_id,
            )
            return {}

        # ── Handle combined same-letter problems ──────────────────
        # C1 and C2 may share a <p> (same child index) or E1/E2 may
        # be adjacent <p> elements.  In both cases the second problem
        # gets no spoilers of its own → inherit from the first that
        # DOES get content.
        sibling_map: dict[str, str] = {}  # skipped_idx → source_idx
        for k in range(len(boundaries)):
            if k + 1 < len(boundaries):
                curr_i, curr_idx, _ = boundaries[k]
                next_i, next_idx, _ = boundaries[k + 1]
                curr_letter = _re.sub(r'\d+$', '', curr_idx)
                next_letter = _re.sub(r'\d+$', '', next_idx)
                if curr_letter == next_letter:
                    if curr_i == next_i or curr_i + 1 == next_i:
                        sibling_map[curr_idx] = next_idx

        # ── Extract solution for each problem ─────────────────────
        solutions: dict = {}
        for j, (start_i, idx, header) in enumerate(boundaries):
            end_i = (
                boundaries[j + 1][0]
                if j + 1 < len(boundaries)
                else len(children)
            )

            # Walk children between this problem's <p><a> and the next
            # one's, collecting explanation text + solution code.
            #
            # CF editorials use several spoiler-title naming conventions:
            #   Code:   "Implementation" / "Code" / "Solution (…)"
            #   Text:   "Tutorial" / "Solution" / "Hint N"
            # Skip:   "Rate the problem" / "Alternate …" (user polls,
            #          alternative solutions — not official editorial)
            tutorial_text = ""
            code = ""
            _tutorial_parts: list[str] = []  # collect from Hint+Solution
            for child in children[start_i + 1 : end_i]:
                if child.name != "div":
                    continue
                classes = child.get("class") or []
                if "spoiler" not in classes:
                    continue
                title_el = child.select_one(".spoiler-title")
                if not title_el:
                    continue
                title_text = title_el.get_text(strip=True)
                title_lower = title_text.lower()

                # Skip user-poll spoilers ("Rate the problem", "Rate The Problem! (C1)")
                if title_lower.startswith("rate"):
                    continue

                # ── Code spoilers: title implies code + has <pre> ──
                # "Implementation" | "Code" | "Code (C1)" |
                # "Solution (FelixArg)" | "Solution 1 (FelixArg)" |
                # "Solution E1 (FairyWinx)"
                is_code_title = (
                    title_lower == "implementation"
                    or title_lower.startswith("code")
                )
                is_solution_title = (
                    title_lower == "solution"
                    or title_lower.startswith("solution ")
                    or title_lower.startswith("solution(")
                )
                has_pre = child.find("pre") is not None

                if is_code_title or (is_solution_title and has_pre):
                    pre_el = child.find("pre")
                    if pre_el and not code:
                        raw = str(pre_el)
                        raw = _re.sub(r'<[^>]+>', '', raw)
                        code = _html.unescape(raw).strip()
                        lines = code.split('\n')
                        while lines and not lines[-1].strip():
                            lines.pop()
                        code = '\n'.join(lines)
                    continue

                # ── Tutorial / Hint / Solution (text-only) spoilers ─
                elif (title_lower == "tutorial"
                      or title_lower == "solution"
                      or title_lower.startswith("solution ")
                      or title_lower.startswith("solution(")
                      or title_lower.startswith("hint")):
                    sc = child.select_one(".spoiler-content")
                    if not sc:
                        continue
                    _soup = _BS(str(sc), "html.parser")
                    # MathJax cleanup
                    for math_el in _soup.select(".MathJax"):
                        nobr = math_el.find("nobr")
                        if nobr:
                            t = nobr.get_text("", strip=True)
                            if t:
                                if _re.search(r'\\[a-zA-Z]', t):
                                    math_el.replace_with(f" ${t}$ ")
                                else:
                                    math_el.replace_with(f" {t} ")
                                continue
                        math_el.decompose()
                    for sel in (".MathJax_Preview",
                                 "script[type='math/tex']",
                                 ".MJX_Assistive_MathML"):
                        for el in _soup.select(sel):
                            el.decompose()
                    # Collect paragraphs
                    paragraphs: list[str] = []
                    for p in _soup.select("p"):
                        text = " ".join(p.stripped_strings)
                        if text:
                            paragraphs.append(text)
                    if not paragraphs:
                        text = " ".join(_soup.stripped_strings)
                        if text:
                            paragraphs = [text]
                    para_text = "\n\n".join(paragraphs)
                    if para_text:
                        _tutorial_parts.append(para_text)

            # ── Combine tutorial parts ─────────────────────────────
            if _tutorial_parts:
                tutorial_text = "\n\n".join(_tutorial_parts)
                # Strip Russian/localised title prefix
                tutorial_text = _re.sub(
                    rf'^{_re.escape(str(contest_id))}'
                    rf'{_re.escape(idx)}\s*[-–—]\s*\S[^a-zA-Z]*',
                    '', tutorial_text,
                ).strip()

            if not code:
                # No code spoiler for this problem — try to inherit
                # from a sibling (C2 reuses C1's code, E1 reuses E2's).
                _sibling_idx = _re.sub(r'\d+$', '', idx)  # "C2" → "C"
                for _sib_idx, _sib_sol in solutions.items():
                    if _re.sub(r'\d+$', '', _sib_idx) == _sibling_idx and _sib_idx != idx:
                        _sib_content = _sib_sol.get("content", "")
                        _m = _re.search(r'```(?:\w+)?\n(.*?)\n```', _sib_content, _re.DOTALL)
                        if _m:
                            code = _m.group(1)
                            logger.debug(
                                "Inherited code from sibling %s for %s",
                                _sib_idx, idx,
                            )
                            break

            if not code and not tutorial_text:
                # Neither code nor explanation — nothing useful.
                logger.debug(
                    "No content for problem %s in editorial", idx,
                )
                continue

            # ── Build solution markdown content ──────────────────
            parts: list = [f"## {header}"]
            # Include tutorial explanation if available
            if tutorial_text:
                parts.append(f"\n### 题解\n{tutorial_text}")
            # Detect programming language from code heuristics
            lang = "cpp"  # CF default
            if code.strip().startswith("def ") or code.strip().startswith("import "):
                lang = "python"
            elif code.strip().startswith("import java"):
                lang = "java"
            parts.append(f"\n### 代码\n```{lang}\n{code}\n```")
            if not tutorial_text:
                # Only show the AJAX warning when tutorial is missing
                parts.append(
                    "\n> **注意**：题解解释（Tutorial）部分由 Codeforces "
                    "通过 JavaScript 动态加载，静态爬取仅能获取代码实现。"
                    "请访问原页面查看完整题解。"
                )

            solutions[idx] = {
                "author": "Codeforces Editorial",
                "title": header,
                "content": "\n".join(parts),
                "vote_count": 0,
                "solution_index": 0,  # CF 每題只有 1 篇 editorial
            }

        # ── Inherit solutions for adjacent same-letter problems ────
        # When E1 and E2 links are adjacent with shared spoilers,
        # E1 gets no content of its own → clone E2's solution.
        for skipped_idx, source_idx in sibling_map.items():
            if skipped_idx not in solutions and source_idx in solutions:
                src = dict(solutions[source_idx])
                # Update the title to reflect this problem's header
                for _bi, _b_idx, _b_header in boundaries:
                    if _b_idx == skipped_idx:
                        # Replace the ## header line
                        src["content"] = _re.sub(
                            r'^## .*', f'## {_b_header}',
                            src["content"], count=1,
                        )
                        src["title"] = _b_header
                        break
                solutions[skipped_idx] = src
                logger.debug(
                    "Cloned solution from %s for adjacent problem %s",
                    source_idx, skipped_idx,
                )

        return solutions

    def fetch_solutions(
        self, source_id: str, max_editorials: int = 5
    ) -> CrawlResult:
        """Fetch solution content for a Codeforces problem.

        Fetches the contest editorial blog post and extracts the
        per-problem solution (code from the Implementation spoiler).

        The Tutorial explanation text is AJAX-loaded by CF JavaScript
        and is NOT available in static HTML; only the code is extracted.

        Args:
            source_id: Problem identifier (e.g. ``"1742E"``).
            max_editorials: Maximum number of editorial/blog pages to try.

        Returns:
            CrawlResult whose ``data`` is a list of solution dicts with
            ``author``, ``content``, ``title``, ``vote_count`` fields.
        """
        contest_id, index = self._parse_problem_id(source_id)
        if contest_id == 0:
            return CrawlResult(
                success=False,
                error=f"Cannot parse problem ID: {source_id}",
                source="http",
            )

        problem_url = (
            f"https://codeforces.com/problemset/problem/"
            f"{contest_id}/{index}"
        )

        # ── Step 1: find the editorial blog URL ──────────────────
        cls = type(self)
        should_discover = False
        with cls._editorial_url_lock:
            if contest_id in cls._editorial_url_cache:
                editorial_url = cls._editorial_url_cache[contest_id]
            else:
                editorial_url = None
                should_discover = True

        if should_discover:
            editorial_url = self._discover_editorial_url(
                problem_url, contest_id,
            )
            with cls._editorial_url_lock:
                cls._editorial_url_cache[contest_id] = editorial_url

        if not editorial_url:
            return CrawlResult(
                success=False,
                error=(
                    f"No editorial found for contest {contest_id} "
                    f"(problem {source_id})"
                ),
                source="http",
            )

        # ── Step 2: fetch editorial HTML ─────────────────────────
        # Try headless browser first → gets AJAX-loaded Tutorial text.
        # Fall back to curl if browser is unavailable or fails.
        html = self._fetch_editorial_rendered(editorial_url)

        if not html:
            # Fallback: static curl (fast but no Tutorial text)
            logger.debug(
                "Browser unavailable, falling back to curl: %s",
                editorial_url,
            )
            ed_result = self._curl_request(editorial_url)
            if not ed_result.success:
                return CrawlResult(
                    success=False,
                    error=ed_result.error,
                    source="http",
                )
            html = self._extract_html_text(ed_result)

        if not html:
            return CrawlResult(
                success=False,
                error="Empty editorial HTML",
                source="http",
            )

        # Parse ALL solutions from the editorial HTML
        all_solutions = self._parse_editorial_html(html, contest_id)

        # Return only the solution matching this problem's index
        if index in all_solutions:
            return CrawlResult(
                success=True,
                data=[all_solutions[index]],
                source="http",
            )

        # ── Fallback: try the old markdown-based extraction ──────
        # for editorials that don't use the standard spoiler format
        try:
            from bs4 import BeautifulSoup as _BS
        except ImportError:
            return CrawlResult(
                success=False,
                error=(
                    f"Problem '{index}' not found in editorial "
                    f"and no fallback available"
                ),
                source="http",
            )

        soup = _BS(html, "html.parser")
        title_tag = soup.find("title")
        page_title = (
            title_tag.get_text(strip=True)
            if title_tag else "Codeforces Editorial"
        )

        ttypography = soup.select_one(
            ".ttypography, .content"
        )
        if ttypography:
            import re as _re
            md_text = self._editorial_html_to_markdown(str(ttypography))
            lines = md_text.split("\n")

            prob_header_re = _re.compile(
                rf"^\s*(?:\*\*)?(?:#+\s*)?"
                rf"(?:{_re.escape(str(contest_id))}\s*)?"
                rf"{_re.escape(index)}[\s\.\-:：]",
                _re.IGNORECASE,
            )
            next_header_re = _re.compile(
                r"^\s*(?:\*\*)?(?:#+\s*)?(?:\d+)?[A-Z]\d*[\s\.\-:：]",
            )

            in_section = False
            section_lines = []
            for line in lines:
                if prob_header_re.match(line):
                    in_section = True
                    section_lines = [line]
                elif in_section:
                    if next_header_re.match(line) and not prob_header_re.match(line):
                        break
                    section_lines.append(line)

            if section_lines:
                content = "\n".join(section_lines).strip()
                if len(content) > 50:
                    return CrawlResult(
                        success=True,
                        data=[{
                            "author": "Codeforces Editorial",
                            "title": f"{source_id} Solution",
                            "content": content,
                            "vote_count": 0,
                        }],
                        source="http",
                    )

        return CrawlResult(
            success=False,
            error=f"No solution found for problem '{source_id}' "
                  f"in editorial",
            source="http",
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch problems matching a given tag.

        GET /api/problemset.problems?tags={tag}

        Args:
            tag: CF tag (e.g. ``"dp"``, ``"greedy"``).
            count: Maximum number to return (default 50).

        Returns:
            CrawlResult with a list of up to *count* problem dicts.
        """
        result = self._api("problemset.problems", tags=tag)
        if not result.success:
            return result

        raw = result.data
        if not isinstance(raw, dict):
            return CrawlResult(
                success=False,
                error="Unexpected problemset response format",
                source="http",
            )

        problems = raw.get("problems", [])[:count]
        return CrawlResult(
            success=True,
            data=problems,
            source="http",
        )

    # ── internal helpers ────────────────────────────────────────

    @staticmethod
    def _parse_problem_id(source_id: str) -> tuple:
        """Split ``"1742E"`` → ``(1742, "E")``.

        Returns ``(0, source_id)`` if parsing fails.
        """
        import re

        m = re.match(r"^(\d+)([A-Z]\d*)$", source_id)
        if m:
            return int(m.group(1)), m.group(2)
        return 0, source_id


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


def _save_result(crawler: CodeforcesCrawler, data, sub_dir: str, label: str) -> None:
    """Save fetched data to a timestamped JSON file under data/raw/{platform}/{sub_dir}/."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_label = str(label).replace("/", "_").replace("\\", "_")
    filename = f"{today}_{safe_label}.json"
    crawler.save_json(data, filename=filename, sub_dir=f"{crawler.PLATFORM}/{sub_dir}")


def main(argv: Optional[list] = None) -> None:
    """CLI entry point for the Codeforces crawler.

    Two modes are supported:

    * **NestJS mode** – ``--input`` receives a JSON string with all
      parameters (``action``, ``uid``, ``tags``, ``count``).
    * **CLI mode** – each parameter is supplied via its own argparse flag.

    Output is always a single JSON object printed to stdout.
    """
    parser = argparse.ArgumentParser(description="Codeforces crawler CLI")
    parser.add_argument(
        "--action",
        choices=["fetch_problems", "fetch_user", "fetch_records", "fetch_solutions", "fetch_detail", "import"],
        default=None,
        help="Crawl action to execute",
    )
    parser.add_argument("--uid", default=None, help="User ID / handle")
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
                platform="codeforces",
            )
            sys.exit(1)
    else:
        if not args.action:
            _emit(
                success=False,
                error="Either --action or --input is required",
                platform="codeforces",
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
        _emit(success=False, error="Missing 'action' in parameters", platform="codeforces")
        sys.exit(1)

    # ── execute ────────────────────────────────────────────────
    crawler = CodeforcesCrawler()
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
            result = executor.execute("fetch_problems_by_tag", str(tag), fetch_count)
            if result.success and result.data:
                # Build problem key: "contestId+index"
                skip_keys = set()
                for sid in skip_ids:
                    cid, idx = CodeforcesCrawler._parse_problem_id(sid)
                    if cid:
                        skip_keys.add(f"{cid}{idx}")
                    else:
                        skip_keys.add(sid)
                new_items = []
                for p in result.data:
                    key1 = f"{p.get('contestId','')}{p.get('index','')}"
                    key2 = p.get('id') or p.get('pid') or ''
                    if key1 not in skip_keys and key2 not in skip_ids:
                        new_items.append(p)
                new_items = new_items[:count]
                # Enrich with full detail (scrape problem page) — parallel
                # _curl_request is a static method using subprocess, so it's
                # I/O-bound and thread-safe.  6 workers saturate typical
                # bandwidth without tripping CF rate limits.
                import concurrent.futures as _futures
                MAX_WORKERS = 6
                enriched: list[dict] = [{}] * len(new_items)

                def _fetch_one(i: int, prob: dict) -> tuple[int, dict]:
                    cid = prob.get("contestId", "")
                    idx = prob.get("index", "")
                    sid = f"{cid}{idx}" if cid and idx else ""
                    if not sid:
                        return (i, prob)
                    # Pass meta=prob so the worker skips the API call
                    # entirely — only curl + HTML extraction runs.
                    worker = CodeforcesCrawler()
                    detail = worker.fetch_problem(sid, meta=prob)
                    if detail and detail.success and detail.data:
                        return (i, dict(detail.data))
                    return (i, prob)

                with _futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                    futures = [
                        pool.submit(_fetch_one, i, p)
                        for i, p in enumerate(new_items)
                    ]
                    for fut in _futures.as_completed(futures):
                        i, data = fut.result()
                        enriched[i] = data

                result = CrawlResult(success=True, data=enriched, source=result.source)
                _save_result(crawler, result.data, "problems", str(tag) or "all")
                # Fetch solutions for each problem — parallel (I/O-bound)
                import threading as _threading
                _save_lock = _threading.Lock()

                def _fetch_sol_worker(prob: dict) -> tuple[str, list | None]:
                    cid = prob.get("contestId", "")
                    idx = prob.get("index", "")
                    sid = f"{cid}{idx}" if cid and idx else ""
                    if not sid:
                        return ("", None)
                    worker = CodeforcesCrawler()
                    sol = worker.fetch_solutions(sid, 5)
                    if sol and sol.success and sol.data:
                        with _save_lock:
                            _save_result(crawler, sol.data, "solutions", str(sid))
                        return (sid, sol.data)
                    return (sid, None)

                SOL_WORKERS = 5  # _curl_request is not rate-limited, safe to parallelize
                with _futures.ThreadPoolExecutor(max_workers=SOL_WORKERS) as pool:
                    list(pool.map(_fetch_sol_worker, enriched))

        elif action == "fetch_records":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_records")
            result = executor.execute("fetch_user_records", str(uid))
            if result.success and result.data:
                _save_result(crawler, result.data, "records", str(uid))

        elif action == "fetch_solutions":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_solutions")
            count = int(params.get("count", 5))
            result = executor.execute("fetch_solutions", str(uid), count)
            if result.success and result.data:
                _save_result(crawler, result.data, "solutions", str(uid))

        elif action == "fetch_detail":
            # Fetch a single problem's full detail (used by backfill)
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_detail")
            result = executor.execute("fetch_problem", str(uid))
            if result.success and result.data:
                _save_result(crawler, result.data, "problems", str(uid))

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
    platform: str = "codeforces",
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
