"""
Luogu (洛谷) platform crawler.

Uses Luogu's ``_contentOnly=1`` query parameter to obtain structured
JSON responses instead of full HTML pages.  No browser fallback is
required under normal circumstances.
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
# LuoguCrawler
# ──────────────────────────────────────────────


class LuoguCrawler(BaseCrawler):
    """Crawler for Luogu (https://www.luogu.com.cn).

    Appends ``?_contentOnly=1`` to every request so the server
    returns JSON instead of rendered HTML.
    """

    PLATFORM: str = "luogu"

    # ── class constants ─────────────────────────────────────────

    BASE_URL: str = "https://www.luogu.com.cn"

    @staticmethod
    def _default_qps() -> float:
        """Luogu rate-limits to roughly 2 requests/second."""
        return 2.0

    # ── helpers ─────────────────────────────────────────────────

    def _get_json(self, path: str, **params: str) -> CrawlResult:
        """GET *path* with ``_contentOnly=1`` appended.

        Returns the ``currentData`` field on success, or the raw
        response if the envelope is missing.
        """
        # Merge _contentOnly with any additional params.
        all_params = {"_contentOnly": "1", **params}
        qs = "&".join(f"{k}={v}" for k, v in all_params.items())
        url = f"{self.BASE_URL}{path}?{qs}"

        logger.debug("Luogu GET: %s", url)
        result = self._http_request(url)
        if not result.success:
            return result

        raw = result.data
        if isinstance(raw, dict):
            code = raw.get("code")
            if code is not None and code != 200:
                return CrawlResult(
                    success=False,
                    error=raw.get("currentTemplate", f"Luogu API returned code {code}"),
                    source="http",
                    retry_count=result.retry_count,
                )
            # Unwrap the payload.
            inner = raw.get("currentData")
            if inner is not None:
                return CrawlResult(
                    success=True,
                    data=inner,
                    source="http",
                    retry_count=result.retry_count,
                )
            # No currentData – return the whole envelope.
            return CrawlResult(
                success=True,
                data=raw,
                source="http",
                retry_count=result.retry_count,
            )

        # Fallback: Luogu CDN-rendered pages embed data in <script id="lentille-context">
        if isinstance(raw, str):
            import re as _re
            match = _re.search(
                r'<script\s+id="lentille-context"[^>]*type="application/json"[^>]*>(.*?)</script>',
                raw, _re.DOTALL,
            )
            if match:
                try:
                    envelope = json.loads(match.group(1))
                    # envelope.status === 200, envelope.data contains old currentData structure
                    if envelope.get("status") == 200:
                        inner = envelope.get("data", {})
                        return CrawlResult(
                            success=True,
                            data=inner,
                            source="http",
                            retry_count=result.retry_count,
                        )
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning("Failed to parse lentille-context JSON: %s", exc)

        return result

    # ── abstract method implementations ─────────────────────────

    def fetch_user_profile(self, uid: str) -> CrawlResult:
        """Fetch a Luogu user's public profile.

        GET /user/{uid}?_contentOnly=1

        Args:
            uid: Luogu user ID (numeric string, e.g. ``"1001"``).

        Returns:
            CrawlResult with user profile data.
        """
        result = self._get_json(f"/user/{uid}")
        if not result.success:
            return result

        data = result.data
        if isinstance(data, dict) and "user" in data:
            return CrawlResult(
                success=True,
                data=data["user"],
                source="http",
                retry_count=result.retry_count,
            )
        return result

    def fetch_user_records(
        self, uid: str, since: Optional[str] = None
    ) -> CrawlResult:
        """Fetch submission records for a Luogu user (paginated).

        GET /record/list?user={uid}&page=1&_contentOnly=1

        Pages through up to 5 pages (configurable via ``_max_pages``)
        to collect all recent records.  The ``since`` parameter is
        accepted for interface compatibility but client-side filtering
        is recommended.

        Args:
            uid: Luogu user ID.
            since: *Optional* timestamp for filtering (client-side).

        Returns:
            CrawlResult whose ``data`` is a list of record dicts.
        """
        all_records: list = []
        max_pages = 5

        for page in range(1, max_pages + 1):
            path = f"/record/list"
            result = self._get_json(path, user=uid, page=str(page))
            if not result.success:
                if page == 1:
                    return result
                # Later page failures are non-fatal.
                logger.warning(
                    "Luogu records page %d failed: %s", page, result.error
                )
                break

            data = result.data
            if not isinstance(data, dict):
                break

            records = data.get("records", {}).get("result", [])
            if not records:
                break  # No more records.

            all_records.extend(records)

            # If the server signals there are no more pages, stop.
            total_pages = (
                data.get("records", {}).get("count", 0)
                if isinstance(data.get("records"), dict)
                else 0
            )
            if page >= total_pages:
                break

        return CrawlResult(
            success=True,
            data=all_records,
            source="http",
        )

    def fetch_problem(self, source_id: str) -> CrawlResult:
        """Fetch a single problem's full metadata via HTTP + lentille-context.

        Args:
            source_id: Luogu problem ID (e.g. ``"P1001"``).

        Returns:
            CrawlResult with full problem data including description.
        """
        url = f"{self.BASE_URL}/problem/{source_id}?_contentOnly=1"
        logger.debug("Luogu HTTP GET: %s", url)

        result = self.fetch_with_fallback(url)
        if not result.success:
            return result

        raw = result.data
        # Try lentille-context extraction from HTML (same as _get_json fallback)
        if isinstance(raw, str):
            import re as _re
            match = _re.search(
                r'<script\s+id="lentille-context"[^>]*type="application/json"[^>]*>(.*?)</script>',
                raw, _re.DOTALL,
            )
            if match:
                try:
                    envelope = json.loads(match.group(1))
                    if envelope.get("status") == 200:
                        problem = envelope.get("data", {}).get("problem", {})
                        contenu = problem.get("contenu") or {}
                        pid_val = problem.get("pid") or source_id
                        return CrawlResult(success=True, data={
                            "pid": problem.get("pid") or source_id,
                            "title": problem.get("name") or contenu.get("name") or "",
                            "difficulty": problem.get("difficulty") or 0,
                            "tags": problem.get("tags") or [],
                            "total_submit": problem.get("totalSubmit") or 0,
                            "total_ac": problem.get("totalAccepted") or 0,
                            "background": contenu.get("background") or "",
                            "description": contenu.get("description") or "",
                            "input_format": contenu.get("formatI") or "",
                            "output_format": contenu.get("formatO") or "",
                            "hint": contenu.get("hint") or "",
                            "samples": problem.get("samples") or [],
                            "limits": problem.get("limits") or {},
                            "source_url": f"https://www.luogu.com.cn/problem/{pid_val}",
                        }, source="http")
                except (json.JSONDecodeError, KeyError):
                    pass
        elif isinstance(raw, dict):
            problem = raw.get("currentData", {}).get("problem", {})
            if problem:
                contenu = problem.get("contenu") or {}
                pid_val = problem.get("pid") or source_id
                return CrawlResult(success=True, data={
                    "pid": problem.get("pid") or source_id,
                    "title": problem.get("name") or contenu.get("name") or "",
                    "difficulty": problem.get("difficulty") or 0,
                    "tags": problem.get("tags") or [],
                    "total_submit": problem.get("totalSubmit") or 0,
                    "total_ac": problem.get("totalAccepted") or 0,
                    "background": contenu.get("background") or "",
                    "description": contenu.get("description") or "",
                    "input_format": contenu.get("formatI") or "",
                    "output_format": contenu.get("formatO") or "",
                    "hint": contenu.get("hint") or "",
                    "samples": problem.get("samples") or [],
                    "limits": problem.get("limits") or {},
                    "source_url": f"https://www.luogu.com.cn/problem/{pid_val}",
                }, source="http")

        return CrawlResult(success=False, error=f"Failed to extract problem data for {source_id}")

    def fetch_solutions(
        self, source_id: str, max_pages: int = 3
    ) -> CrawlResult:
        """Fetch solutions for a problem via HTTP + lentille-context.

        Requires login cookies to be present in the session.
        Uses HTTP instead of browser for speed.

        Args:
            source_id: Luogu problem ID (e.g. ``"P1001"``).
            max_pages: Max number of solution pages to fetch.

        Returns:
            CrawlResult with list of solution dicts.
        """
        all_solutions: list = []

        for page_num in range(1, max_pages + 1):
            url = f"{self.BASE_URL}/problem/solution/{source_id}?page={page_num}"
            logger.debug("Luogu solutions HTTP GET: %s", url)
            result = self.fetch_with_fallback(url)

            if not result.success:
                if page_num == 1:
                    return CrawlResult(
                        success=False,
                        error=result.error or "Solution fetch failed",
                    )
                break

            raw = result.data
            # Extract lentille-context from HTML
            if isinstance(raw, str):
                import re as _re
                match = _re.search(
                    r'<script\s+id="lentille-context"[^>]*type="application/json"[^>]*>(.*?)</script>',
                    raw, _re.DOTALL,
                )
                if match:
                    try:
                        envelope = json.loads(match.group(1))
                        if envelope.get("status") == 200:
                            data = envelope.get("data", {})
                            sols = data.get("solutions", {}).get("result", [])
                            if not sols:
                                break
                            for s in sols:
                                all_solutions.append({
                                    "author": (s.get("author") or {}).get("name", "匿名"),
                                    "title": s.get("title", ""),
                                    "content": s.get("content", ""),
                                    "vote_count": s.get("thumbUp", 0),
                                    "reply_count": s.get("replyCount", 0),
                                })
                            # Check total pages
                            total = data.get("solutions", {}).get("count", 0)
                            if page_num * 20 >= total:
                                break
                            continue
                        elif envelope.get("status") == 401:
                            if page_num == 1:
                                return CrawlResult(
                                    success=False,
                                    error="Login required — please log in to Luogu first",
                                )
                            break
                    except (json.JSONDecodeError, KeyError):
                        pass
            elif isinstance(raw, dict):
                # Direct JSON response
                data = raw.get("currentData", raw)
                sols = data.get("solutions", {}).get("result", [])
                if not sols:
                    break
                for s in sols:
                    all_solutions.append({
                        "author": (s.get("author") or {}).get("name", "匿名"),
                        "title": s.get("title", ""),
                        "content": s.get("content", ""),
                        "vote_count": s.get("thumbUp", 0),
                        "reply_count": s.get("replyCount", 0),
                    })
                total = data.get("solutions", {}).get("count", 0)
                if page_num * 20 >= total:
                    break
                continue

            break  # Unknown format, stop

        return CrawlResult(
            success=True,
            data=all_solutions,
            source="http",
        )

    def fetch_problems_by_tag(
        self, tag: str, count: int = 50
    ) -> CrawlResult:
        """Fetch problems filtered by type/tag.

        GET /problem/list?type={tag}&page=1&_contentOnly=1

        Args:
            tag: Luogu problem type (e.g. ``"P"``, ``"B"``, ``"CF"``).
            count: Maximum number to return.

        Returns:
            CrawlResult with a list of problem dicts.
        """
        all_problems: list = []
        max_pages = (count // 20) + 2  # Each page has ~20 problems.

        for page in range(1, max_pages + 1):
            path = "/problem/list"
            result = self._get_json(path, type=tag, page=str(page))
            if not result.success:
                if page == 1:
                    return result
                break

            data = result.data
            if not isinstance(data, dict):
                break

            problems = data.get("problems", {}).get("result", [])
            if not problems:
                break

            all_problems.extend(problems)
            if len(all_problems) >= count:
                break

        return CrawlResult(
            success=True,
            data=all_problems[:count],
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


def _save_result(crawler: LuoguCrawler, data, sub_dir: str, label: str) -> None:
    """Save fetched data to a timestamped JSON file under data/raw/{platform}/{sub_dir}/."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_label = str(label).replace("/", "_").replace("\\", "_")
    filename = f"{today}_{safe_label}.json"
    crawler.save_json(data, filename=filename, sub_dir=f"{crawler.PLATFORM}/{sub_dir}")


def main(argv: Optional[list] = None) -> None:
    """CLI entry point for the Luogu crawler.

    Two modes are supported:

    * **NestJS mode** – ``--input`` receives a JSON string with all
      parameters (``action``, ``uid``, ``tags``, ``count``).
    * **CLI mode** – each parameter is supplied via its own argparse flag.

    Output is always a single JSON object printed to stdout.
    """
    parser = argparse.ArgumentParser(description="Luogu crawler CLI")
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
    parser.add_argument(
        "--input-file",
        default=None,
        help="Path to a JSON file containing all parameters (for large payloads)",
    )
    args = parser.parse_args(argv)

    # ── determine parameter source ─────────────────────────────
    if args.input_file:
        from pathlib import Path as _Path
        try:
            params = json.loads(_Path(args.input_file).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _emit(
                success=False,
                error=f"Failed to read input file: {exc}",
                platform="luogu",
            )
            sys.exit(1)
    elif args.input:
        try:
            params: dict = json.loads(args.input)
        except json.JSONDecodeError as exc:
            _emit(
                success=False,
                error=f"Invalid JSON input: {exc}",
                platform="luogu",
            )
            sys.exit(1)
    else:
        if not args.action:
            _emit(
                success=False,
                error="Either --action or --input is required",
                platform="luogu",
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
        _emit(success=False, error="Missing 'action' in parameters", platform="luogu")
        sys.exit(1)

    # ── execute ────────────────────────────────────────────────
    crawler = LuoguCrawler()
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
            # Fetch extra to compensate for already-imported problems
            fetch_count = max(count + len(skip_ids), count * 3)
            result = executor.execute("fetch_problems_by_tag", str(tag), fetch_count)
            if result.success and result.data:
                new_items = [p for p in result.data if p.get('pid') not in skip_ids]
                new_items = new_items[:count]
                # Enrich with full content: fetch detail for each problem
                enriched = []
                for prob in new_items:
                    pid = prob.get('pid', '')
                    if pid:
                        # Retry up to 3 times for transient HTTP errors
                        detail = None
                        for retry in range(3):
                            detail = executor.execute("fetch_problem", str(pid))
                            if detail and detail.success and detail.data:
                                break
                            if retry < 2:
                                import time as _time
                                _time.sleep(1.0 * (retry + 1))
                        if detail and detail.success and detail.data:
                            merged = dict(detail.data)
                            for k in ('totalSubmit', 'totalAccepted', 'total_submit', 'total_ac'):
                                if merged.get(k) is None:
                                    merged[k] = prob.get(k)
                            enriched.append(merged)
                        else:
                            enriched.append(prob)
                    else:
                        enriched.append(prob)
                result = CrawlResult(success=True, data=enriched, source=result.source)
                _save_result(crawler, result.data, "problems", str(tag) or "all")
                # Also fetch solutions for each new problem
                for prob in enriched:
                    pid = prob.get('pid', '')
                    if pid:
                        sol_result = executor.execute("fetch_solutions", str(pid))
                        if sol_result and sol_result.success and sol_result.data:
                            _save_result(crawler, sol_result.data, "solutions", str(pid))

        elif action == "fetch_records":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_records")
            result = executor.execute("fetch_user_records", str(uid))
            if result.success and result.data:
                _save_result(crawler, result.data, "records", str(uid))

        elif action == "fetch_detail":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_detail")
            result = executor.execute("fetch_problem", str(uid))

        elif action == "fetch_solutions":
            uid = params.get("uid", "")
            if not uid:
                raise ValueError("--uid is required for fetch_solutions")
            result = executor.execute("fetch_solutions", str(uid))
            if result.success and result.data:
                _save_result(crawler, result.data, "solutions", str(uid))

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
    platform: str = "luogu",
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
