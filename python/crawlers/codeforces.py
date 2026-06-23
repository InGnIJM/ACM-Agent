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

    def fetch_solutions(
        self, source_id: str, max_editorials: int = 5
    ) -> CrawlResult:
        """Fetch solution content for a Codeforces problem.

        Scrapes editorial blog posts and extracts solution text for the
        specific problem (matching by problem index letter). Falls back
        to returning the full editorial content as a single solution.

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

        problem_url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        contest_url = f"https://codeforces.com/contest/{contest_id}"

        # ── Step 1: find editorial / tutorial URLs ────────────────
        tutorial_links: List[str] = []

        try:
            from bs4 import BeautifulSoup as _BS
        except ImportError:
            return CrawlResult(success=True, data=[], source="http")

        editorial_keywords = ("editorial", "tutorial", "solution", "analysis")

        # Check contest page
        contest_result = self.fetch_with_fallback(contest_url)
        if contest_result.success:
            html = self._extract_html_text(contest_result)
            soup = _BS(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True).lower()
                if any(kw in text for kw in editorial_keywords):
                    full = f"https://codeforces.com{href}" if href.startswith("/") else href
                    if full not in tutorial_links:
                        tutorial_links.append(full)

        # Check problem page sidebar
        problem_result = self.fetch_with_fallback(problem_url)
        if problem_result.success:
            html = self._extract_html_text(problem_result)
            soup = _BS(html, "html.parser")
            for a in soup.select(".sidebar-menu a, .roundbox a, .second-level-menu a"):
                href = a.get("href", "")
                if href and "blog/entry" in href:
                    full = f"https://codeforces.com{href}" if href.startswith("/") else href
                    if full not in tutorial_links:
                        tutorial_links.append(full)

        # Always try the standard blog/entry/<contest_id> editorial URL
        blog_url = f"https://codeforces.com/blog/entry/{contest_id}"
        if blog_url not in tutorial_links:
            tutorial_links.append(blog_url)

        # ── Step 2: fetch editorial content ───────────────────────
        solutions: list = []

        for link in tutorial_links[:max_editorials]:
            logger.debug("CF fetching editorial: %s", link)
            ed_result = self.fetch_with_fallback(link)
            if not ed_result.success:
                continue

            html = self._extract_html_text(ed_result)
            if not html:
                continue

            soup = _BS(html, "html.parser")

            # Extract page title
            title_tag = soup.find("title")
            page_title = title_tag.get_text(strip=True) if title_tag else "Codeforces Editorial"

            # Try to find content specific to this problem's index
            # Editorial format: usually has headers like "1742A - Some Name" or "A. Some Name"
            import re as _re
            problem_pattern = _re.compile(
                rf"(?:^|\n|<(?:p|div|h\d)[^>]*?>)\s*"
                rf"(?:{_re.escape(str(contest_id))})?\s*"
                rf"{_re.escape(index)}[\.\s\-:：]",
                _re.IGNORECASE,
            )

            # Strategy A: find the problem-specific section in the editorial
            ttypography = soup.select_one(".ttypography, .content, .blog-content, .post-content, .entry-content")
            if ttypography:
                # Convert editorial HTML to Markdown first so that
                # code fences, math delimiters, and formatting survive.
                md_text = self._editorial_html_to_markdown(str(ttypography))
                lines = md_text.split("\n")

                # Look for the section that mentions this problem index
                prob_header_re = _re.compile(
                    rf"^\s*(?:#+\s*)?(?:{_re.escape(str(contest_id))}\s*)?"
                    rf"{_re.escape(index)}[\s\.\-:：]",
                    _re.IGNORECASE,
                )
                next_header_re = _re.compile(
                    r"^\s*(?:#+\s*)?(?:\d+)?[A-Z]\d*[\s\.\-:：]",
                )

                in_section = False
                section_lines: List[str] = []
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
                        solutions.append({
                            "author": "Codeforces Editorial",
                            "title": f"{source_id} Solution",
                            "content": content,
                            "vote_count": 0,
                        })
                        continue

                # Strategy B: return the whole editorial as Markdown
                clean = md_text.strip()
                if len(clean) > 100:
                    solutions.append({
                        "author": "Codeforces Editorial",
                        "title": page_title or f"Contest {contest_id} Editorial",
                        "content": clean,
                        "vote_count": 0,
                    })
                    break  # Got the full editorial, no need to try more links

        if not solutions:
            return CrawlResult(
                success=False,
                error=f"No solution content found for problem '{source_id}'",
                source="http",
            )

        return CrawlResult(
            success=True,
            data=solutions,
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

                SOL_WORKERS = 3  # fewer workers: fetch_solutions uses _http_request
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
