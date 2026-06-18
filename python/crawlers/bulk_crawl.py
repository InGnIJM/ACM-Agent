"""
Bulk crawler for large-scale problem fetching (10,000+ problems).

Runs three independent phases sequentially:
  1. LIST   — paginate through problem lists, save metadata
  2. DETAIL — fetch full problem content for each problem
  3. SOLUTIONS — fetch solution posts for each problem

Progress is persisted to ``data/raw/{platform}/_crawl_state.json`` after
every batch so the backend (and frontend via polling) can monitor live
progress.  The script also supports resume: if a state file already exists
and is in ``running`` status, the script will skip already-completed items.

Usage (CLI)::

    python bulk_crawl.py --platform luogu --tags P --count 10000

Usage (NestJS mode)::

    python bulk_crawl.py --input '{"platform":"luogu","tags":"P","count":10000,"job_id":"..."}'

Graceful shutdown:
    Sends SIGTERM → script writes final state and exits cleanly.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from crawlers.base import BaseCrawler, CrawlResult, CrawlerExecutor, RateLimiter
from crawlers.codeforces import CodeforcesCrawler
from crawlers.leetcode import LeetCodeCrawler
from crawlers.luogu import LuoguCrawler
from crawlers.nowcoder import NowCoderCrawler

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

BATCH_SIZE_DETAIL = 20       # update state file every N detail fetches
BATCH_SIZE_SOLUTIONS = 10    # update state file every N solution fetches

PLATFORM_CRAWLERS: Dict[str, type] = {
    "luogu": LuoguCrawler,
    "leetcode": LeetCodeCrawler,
    "codeforces": CodeforcesCrawler,
    "nowcoder": NowCoderCrawler,
}

PLATFORM_QPS: Dict[str, float] = {
    "luogu": 2.0,
    "leetcode": 2.0,
    "codeforces": 3.0,
    "nowcoder": 1.0,
}

# ──────────────────────────────────────────────
# State file helpers
# ──────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state(state_dir: Path) -> Optional[Dict[str, Any]]:
    """Read the crawl state file if it exists."""
    state_file = state_dir / "_crawl_state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read state file: %s", exc)
        return None


def _write_state(state_dir: Path, state: Dict[str, Any]) -> None:
    """Atomically write the crawl state file.

    Uses tmp + rename for atomicity.  On Windows, the rename may fail
    transiently (file locked by AV / filesystem), so we retry with backoff.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    tmp = state_dir / "_crawl_state.json.tmp"
    target = state_dir / "_crawl_state.json"

    tmp.write_text(
        json.dumps(state, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )

    # Retry loop – Windows may transiently lock the target file
    last_err = None
    for attempt in range(10):
        try:
            tmp.replace(target)
            return
        except PermissionError as exc:
            last_err = exc
            time.sleep(0.05 * (attempt + 1))  # 50ms, 100ms, ..., 500ms
        except OSError:
            # On Windows, fall back to delete-then-rename
            try:
                target.unlink(missing_ok=True)
                tmp.replace(target)
                return
            except OSError:
                time.sleep(0.05 * (attempt + 1))

    # Last resort: write directly
    logger.warning(
        "Could not atomically replace state file after 10 attempts (%s), writing directly",
        last_err,
    )
    target.write_text(
        json.dumps(state, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )


def _init_state(
    state_dir: Path,
    job_id: str,
    platform: str,
    config: Dict[str, Any],
    phases: List[str],
) -> Dict[str, Any]:
    """Create the initial state structure."""
    now = _now_iso()
    phase_statuses: Dict[str, Dict[str, Any]] = {}
    for p in phases:
        phase_statuses[p] = {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "total": None,
            "fetched": 0,
            "errors": 0,
            "avg_ms_per_item": 0,
            "last_pid": None,
        }

    return {
        "job_id": job_id,
        "platform": platform,
        "status": "running",
        "phase": None,
        "config": config,
        "started_at": now,
        "updated_at": now,
        "phases": phase_statuses,
        "errors": [],
    }


# ──────────────────────────────────────────────
# BulkCrawler
# ──────────────────────────────────────────────


class BulkCrawler:
    """Orchestrate bulk problem crawling across three phases."""

    def __init__(
        self,
        platform: str = "luogu",
        data_dir: str = "data/raw",
    ) -> None:
        if platform not in PLATFORM_CRAWLERS:
            raise ValueError(
                f"Unsupported platform: {platform}. "
                f"Supported: {', '.join(sorted(PLATFORM_CRAWLERS.keys()))}"
            )
        self.platform = platform
        self.data_dir = Path(data_dir)
        self.state_dir = self.data_dir / platform
        crawler_cls = PLATFORM_CRAWLERS[platform]
        qps = PLATFORM_QPS.get(platform)
        self.crawler = crawler_cls(data_dir=data_dir, qps=qps)
        self.executor = CrawlerExecutor(self.crawler)
        self._shutdown_requested = False
        self._failed_items_file = self.state_dir / "failed_items.jsonl"

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        logger.info("Received signal %d, requesting graceful shutdown...", signum)
        self._shutdown_requested = True

    def _append_failed_item(self, record: Dict[str, Any]) -> None:
        """Append a per-problem failure record to failed_items.jsonl."""
        try:
            with open(self._failed_items_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.warning("Failed to write failed_items.jsonl: %s", exc)

    def close(self) -> None:
        self.crawler.close()

    # ── Phase 1: LIST ──────────────────────────────────────────

    def run_list_phase(
        self,
        state: Dict[str, Any],
        tag: str,
        count: int,
        skip_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """Fetch problem list pages and return all problem summaries."""
        phase = "list"
        state["phase"] = phase
        state["phases"][phase]["status"] = "running"
        state["phases"][phase]["started_at"] = _now_iso()
        _write_state(self.state_dir, state)

        all_problems: List[Dict[str, Any]] = []
        # Account for skip_ids: need extra pages to compensate
        effective_count = count + len(skip_ids)
        max_pages = (effective_count // 20) + 3
        page_start_time = time.monotonic()
        total_page_ms = 0.0

        for page in range(1, max_pages + 1):
            if self._shutdown_requested:
                state["status"] = "cancelled"
                _write_state(self.state_dir, state)
                logger.info("List phase cancelled at page %d", page)
                return all_problems

            result = self._fetch_list_page(tag, page)

            if not result.success:
                if page == 1:
                    state["status"] = "failed"
                    state["phases"][phase]["status"] = "failed"
                    state["errors"].append({
                        "phase": phase,
                        "page": page,
                        "error": result.error,
                        "ts": _now_iso(),
                    })
                    _write_state(self.state_dir, state)
                    return []
                logger.warning("List page %d failed: %s", page, result.error)
                break

            data = result.data
            if not isinstance(data, dict):
                break

            problems = data.get("problems", {}).get("result", [])
            if not problems:
                break

            # Filter out already-imported problems
            for p in problems:
                pid = p.get("pid", "")
                if pid not in skip_ids:
                    all_problems.append(p)

            # Track page timing
            page_ms = (time.monotonic() - page_start_time) * 1000
            total_page_ms += page_ms
            state["phases"][phase]["fetched"] = len(all_problems)
            state["phases"][phase]["total"] = count
            state["phases"][phase]["avg_ms_per_item"] = (
                total_page_ms / max(page, 1) if page > 0 else 0
            )
            state["updated_at"] = _now_iso()
            _write_state(self.state_dir, state)

            if len(all_problems) >= count:
                break

            page_start_time = time.monotonic()

        # Mark phase complete
        state["phases"][phase]["status"] = "completed"
        state["phases"][phase]["completed_at"] = _now_iso()
        state["phases"][phase]["total"] = len(all_problems)
        state["updated_at"] = _now_iso()
        _write_state(self.state_dir, state)

        # Trim to exact count
        all_problems = all_problems[:count]

        # Save the list as JSON
        self.crawler.save_json(
            all_problems,
            filename=f"bulk_list_{(tag or 'all')}_{_now_iso()[:10]}.json",
            sub_dir=f"{self.platform}/problems",
        )

        logger.info("List phase complete: %d problems collected", len(all_problems))
        return all_problems

    def _fetch_list_page(self, tag: Optional[str], page: int) -> CrawlResult:
        """Fetch a single page of the problem list.

        Directly calls LuoguCrawler._get_json for paginated access.
        If *tag* is None/empty, fetches all problem types.
        """
        kwargs = {"page": str(page)}
        if tag:
            kwargs["type"] = tag
        return self.crawler._get_json("/problem/list", **kwargs)

    # ── Phase 2: DETAIL ────────────────────────────────────────

    def run_detail_phase(
        self,
        state: Dict[str, Any],
        problems: List[Dict[str, Any]],
        skip_existing: bool,
    ) -> List[Dict[str, Any]]:
        """Fetch full detail for each problem, merge with existing metadata."""
        phase = "detail"
        state["phase"] = phase
        state["phases"][phase]["status"] = "running"
        state["phases"][phase]["started_at"] = _now_iso()
        state["phases"][phase]["total"] = len(problems)
        _write_state(self.state_dir, state)

        enriched: List[Dict[str, Any]] = []
        batch_start_time = time.monotonic()
        total_ms = 0.0
        fetched = 0

        # Build set of already-fetched pids for resume
        already_fetched: Set[str] = set()
        if skip_existing:
            problems_dir = self.data_dir / self.platform / "problems"
            if problems_dir.exists():
                for f in problems_dir.glob("*.json"):
                    if f.name.startswith("bulk_list"):
                        continue
                    already_fetched.add(f.stem.split("_")[-1] if "_" in f.stem else f.stem)

        for i, prob in enumerate(problems):
            if self._shutdown_requested:
                state["status"] = "cancelled"
                _write_state(self.state_dir, state)
                logger.info("Detail phase cancelled at %d/%d", i, len(problems))
                return enriched

            pid = prob.get("pid", "")
            if not pid:
                state["phases"][phase]["errors"] += 1
                enriched.append(prob)
                continue

            # Resume: skip if already fetched
            if pid in already_fetched:
                enriched.append(prob)
                continue

            # Retry detail fetch up to 3 times for transient errors
            detail_result = None
            for retry in range(3):
                detail_result = self.executor.execute("fetch_problem", str(pid))
                if detail_result and detail_result.success and detail_result.data:
                    break
                if retry < 2:
                    time.sleep(1.0 * (retry + 1))  # backoff: 1s, 2s

            if detail_result and detail_result.success and detail_result.data:
                merged = dict(detail_result.data)
                # Merge list-level stats if missing in detail
                for k in ("totalSubmit", "totalAccepted", "total_submit", "total_ac"):
                    if merged.get(k) is None:
                        merged[k] = prob.get(k)
                enriched.append(merged)
            else:
                enriched.append(prob)
                state["phases"][phase]["errors"] += 1
                err_record = {
                    "phase": phase,
                    "pid": pid,
                    "error": detail_result.error if detail_result else "no result after 3 retries",
                    "ts": _now_iso(),
                }
                state["errors"].append(err_record)
                self._append_failed_item(err_record)

            fetched += 1
            state["phases"][phase]["fetched"] = fetched
            state["phases"][phase]["last_pid"] = pid

            # Periodic state update
            if fetched % BATCH_SIZE_DETAIL == 0:
                elapsed_ms = (time.monotonic() - batch_start_time) * 1000
                total_ms += elapsed_ms
                state["phases"][phase]["avg_ms_per_item"] = (
                    total_ms / fetched if fetched > 0 else 0
                )
                state["updated_at"] = _now_iso()
                _write_state(self.state_dir, state)
                batch_start_time = time.monotonic()

                # Also save the enriched data so far as backup
                if enriched:
                    self.crawler.save_json(
                        enriched,
                        filename=f"bulk_detail_progress_{pid}.json",
                        sub_dir=f"{self.platform}/problems",
                    )

        # Mark phase complete
        state["phases"][phase]["status"] = "completed"
        state["phases"][phase]["completed_at"] = _now_iso()
        state["phases"][phase]["fetched"] = fetched
        state["updated_at"] = _now_iso()
        _write_state(self.state_dir, state)

        # Save final enriched data (supersedes list files)
        if enriched:
            self.crawler.save_json(
                enriched,
                filename=f"bulk_detail_full_{_now_iso()[:10]}.json",
                sub_dir=f"{self.platform}/problems",
            )

        # Delete stale list files — detail file is now the authoritative source.
        # This prevents list-level data (no descriptions) from overwriting
        # full detail data during import.
        problems_dir = self.data_dir / self.platform / "problems"
        for list_file in problems_dir.glob("bulk_list_*"):
            try:
                list_file.unlink()
                logger.debug("Removed stale list file: %s", list_file.name)
            except OSError:
                pass

        logger.info("Detail phase complete: %d enriched", len(enriched))
        return enriched

    # ── Phase 3: SOLUTIONS ─────────────────────────────────────

    def run_solutions_phase(
        self,
        state: Dict[str, Any],
        problems: List[Dict[str, Any]],
        skip_existing: bool,
    ) -> None:
        """Fetch solutions for each problem, save as individual JSON files."""
        phase = "solutions"
        state["phase"] = phase
        state["phases"][phase]["status"] = "running"
        state["phases"][phase]["started_at"] = _now_iso()
        state["phases"][phase]["total"] = len(problems)
        _write_state(self.state_dir, state)

        # Build set of already-fetched pids for resume
        already_fetched: Set[str] = set()
        if skip_existing:
            solutions_dir = self.data_dir / self.platform / "solutions"
            if solutions_dir.exists():
                for f in solutions_dir.glob("*.json"):
                    already_fetched.add(f.stem.split("_")[-1] if "_" in f.stem else f.stem)

        batch_start_time = time.monotonic()
        total_ms = 0.0
        fetched = 0
        solutions_dir = self.data_dir / self.platform / "solutions"

        for i, prob in enumerate(problems):
            if self._shutdown_requested:
                state["status"] = "cancelled"
                _write_state(self.state_dir, state)
                logger.info("Solutions phase cancelled at %d/%d", i, len(problems))
                return

            pid = prob.get("pid", "")
            if not pid:
                state["phases"][phase]["errors"] += 1
                continue

            # Resume: skip if already fetched
            if pid in already_fetched:
                continue

            sol_result = self.executor.execute("fetch_solutions", str(pid))
            if sol_result and sol_result.success and sol_result.data:
                self.crawler.save_json(
                    sol_result.data,
                    filename=f"{_now_iso()[:10]}_{pid}.json",
                    sub_dir=f"{self.platform}/solutions",
                )
            else:
                state["phases"][phase]["errors"] += 1
                err_record = {
                    "phase": phase,
                    "pid": pid,
                    "error": sol_result.error if sol_result else "no result",
                    "ts": _now_iso(),
                }
                state["errors"].append(err_record)
                self._append_failed_item(err_record)

            fetched += 1
            state["phases"][phase]["fetched"] = fetched
            state["phases"][phase]["last_pid"] = pid

            # Periodic state update
            if fetched % BATCH_SIZE_SOLUTIONS == 0:
                elapsed_ms = (time.monotonic() - batch_start_time) * 1000
                total_ms += elapsed_ms
                state["phases"][phase]["avg_ms_per_item"] = (
                    total_ms / fetched if fetched > 0 else 0
                )
                state["updated_at"] = _now_iso()
                _write_state(self.state_dir, state)
                batch_start_time = time.monotonic()

        # Mark phase complete
        state["phases"][phase]["status"] = "completed"
        state["phases"][phase]["completed_at"] = _now_iso()
        state["phases"][phase]["fetched"] = fetched
        state["updated_at"] = _now_iso()
        _write_state(self.state_dir, state)

        logger.info("Solutions phase complete: %d processed", fetched)

    # ── Orchestration ──────────────────────────────────────────

    def run(
        self,
        job_id: str,
        tag: Optional[str] = None,
        count: int = 100,
        phases: Optional[List[str]] = None,
        skip_ids: Optional[List[str]] = None,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """Execute the bulk crawl.

        Args:
            job_id: Unique job identifier (used for state file).
            tag: Problem tag filter (e.g. "P", "B", "CF").
            count: Maximum number of problems to fetch.
            phases: Which phases to run. Default: all three.
            skip_ids: Problem IDs to skip (already imported).
            skip_existing: If True, skip problems with existing JSON files.

        Returns:
            The final state dict.
        """
        if phases is None:
            phases = ["list", "detail", "solutions"]

        skip_id_set = set(skip_ids or [])
        config = {
            "tag": tag,
            "count": count,
            "phases": phases,
            "skip_existing": skip_existing,
        }

        # Init or resume state
        state = _read_state(self.state_dir)
        if state and state.get("status") == "running":
            logger.info("Resuming from existing state file (job_id=%s)", state.get("job_id"))
            # Merge config to pick up any new settings
            state["config"] = config
            # Ensure all requested phases exist in the state (stale states
            # from previous runs may have been created with fewer phases).
            for p in phases:
                if p not in state.get("phases", {}):
                    state.setdefault("phases", {})[p] = {
                        "status": "pending",
                        "started_at": None,
                        "completed_at": None,
                        "total": None,
                        "fetched": 0,
                        "errors": 0,
                        "avg_ms_per_item": 0,
                        "last_pid": None,
                    }
                    logger.info("Added missing phase '%s' to resumed state", p)
        else:
            state = _init_state(self.state_dir, job_id, self.platform, config, phases)

        # Check if list phase needed
        problems: List[Dict[str, Any]] = []
        need_list = "list" in phases
        need_detail = "detail" in phases
        need_solutions = "solutions" in phases

        if need_list:
            list_status = state["phases"]["list"]["status"]
            if list_status == "completed":
                logger.info("List phase already completed, skipping")
                # Try to load existing list from saved file
                problems = self._load_list_from_disk(tag)
                if not problems:
                    logger.warning("Could not load saved list, re-running list phase")
                    need_list = True  # force re-run
                    list_status = "pending"

            if list_status != "completed":
                problems = self.run_list_phase(state, tag, count, skip_id_set)
                if self._shutdown_requested:
                    return state
        else:
            # Load problems from existing saved list
            problems = self._load_list_from_disk(tag)
            if not problems:
                logger.error("No saved problem list found and list phase not requested")
                state["status"] = "failed"
                state["errors"].append({
                    "phase": "init",
                    "error": "No problem list available",
                    "ts": _now_iso(),
                })
                _write_state(self.state_dir, state)
                return state
            # Ensure list phase entry exists even if we loaded from disk
            if "list" not in state["phases"]:
                state["phases"]["list"] = {
                    "status": "skipped",
                    "started_at": None,
                    "completed_at": None,
                    "total": len(problems),
                    "fetched": len(problems),
                    "errors": 0,
                    "avg_ms_per_item": 0,
                    "last_pid": None,
                }
            else:
                state["phases"]["list"]["total"] = len(problems)
                state["phases"]["list"]["fetched"] = len(problems)

        if not problems:
            logger.warning("No problems to process")
            state["status"] = "completed"
            state["updated_at"] = _now_iso()
            _write_state(self.state_dir, state)
            return state

        # Detail phase
        if need_detail and "detail" in state.get("phases", {}):
            detail_status = state["phases"]["detail"]["status"]
            if detail_status == "completed":
                logger.info("Detail phase already completed, skipping")
            else:
                problems = self.run_detail_phase(state, problems, skip_existing)
                if self._shutdown_requested:
                    return state

        # Solutions phase
        if need_solutions and "solutions" in state.get("phases", {}):
            sol_status = state["phases"]["solutions"]["status"]
            if sol_status == "completed":
                logger.info("Solutions phase already completed, skipping")
            else:
                self.run_solutions_phase(state, problems, skip_existing)
                if self._shutdown_requested:
                    return state

        # All done
        state["status"] = "completed"
        state["phase"] = None
        state["updated_at"] = _now_iso()
        state["summary"] = {
            "total_problems": len(problems),
            "total_solutions_fetched": state["phases"].get("solutions", {}).get("fetched", 0),
            "total_errors": sum(
                p.get("errors", 0) for p in state.get("phases", {}).values()
            ),
            "duration_seconds": None,
        }
        if state.get("started_at"):
            try:
                started = datetime.fromisoformat(state["started_at"])
                state["summary"]["duration_seconds"] = (
                    datetime.now(timezone.utc) - started
                ).total_seconds()
            except (ValueError, TypeError):
                pass
        _write_state(self.state_dir, state)

        logger.info(
            "Bulk crawl complete: %d problems, %d errors",
            len(problems),
            state["summary"]["total_errors"],
        )
        return state

    def _load_list_from_disk(self, tag: str) -> List[Dict[str, Any]]:
        """Try to load previously-saved problem list from disk."""
        problems_dir = self.data_dir / self.platform / "problems"
        if not problems_dir.exists():
            return []

        # Look for bulk_list files, newest first
        candidates = sorted(
            problems_dir.glob(f"bulk_list_{(tag or 'all')}_*.json"),
            reverse=True,
        )
        if not candidates:
            # Also try bulk_detail_full files
            candidates = sorted(
                problems_dir.glob("bulk_detail_full_*.json"),
                reverse=True,
            )

        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    logger.info("Loaded %d problems from %s", len(data), path.name)
                    return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load %s: %s", path, exc)

        return []


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point for bulk crawler.

    Accepts either ``--input`` (JSON) or individual flags.
    """
    parser = argparse.ArgumentParser(description="Bulk problem crawler")
    parser.add_argument("--platform", default="luogu", help="Platform to crawl")
    parser.add_argument("--tags", default="P", help="Problem tag filter")
    parser.add_argument("--count", type=int, default=100, help="Max problems to fetch")
    parser.add_argument("--job-id", default=None, help="Job ID for state tracking")
    parser.add_argument("--phases", default=None, help="Comma-separated phases (list,detail,solutions)")
    parser.add_argument("--skip-ids", default=None, help="Comma-separated IDs to skip")
    parser.add_argument("--no-skip-existing", action="store_true", help="Don't skip existing files")
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

    # Determine parameter source
    if args.input_file:
        try:
            params = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(json.dumps({
                "success": False,
                "error": f"Failed to read input file: {exc}",
                "platform": "luogu",
            }, ensure_ascii=False))
            sys.exit(1)
    elif args.input:
        try:
            params: Dict[str, Any] = json.loads(args.input)
        except json.JSONDecodeError as exc:
            print(json.dumps({
                "success": False,
                "error": f"Invalid JSON input: {exc}",
                "platform": "luogu",
            }, ensure_ascii=False))
            sys.exit(1)
    else:
        params = {
            "platform": args.platform,
            "tags": args.tags,
            "count": args.count,
            "job_id": args.job_id or f"bulk_{_now_iso()[:10]}_{args.tags}_{args.count}",
            "phases": args.phases.split(",") if args.phases else None,
            "skip_ids": args.skip_ids.split(",") if args.skip_ids else [],
            "skip_existing": not args.no_skip_existing,
        }

    platform = params.get("platform", "luogu")
    tag = params.get("tags") or None  # None = all types
    count = int(params.get("count", 100))
    job_id = str(params.get("job_id", f"bulk_{_now_iso()[:10]}_{tag}_{count}"))
    phases = params.get("phases")  # None = all three
    skip_ids = params.get("skip_ids", [])
    skip_existing = params.get("skip_existing", True)

    try:
        crawler = BulkCrawler(platform=platform)
        state = crawler.run(
            job_id=job_id,
            tag=tag,
            count=count,
            phases=phases,
            skip_ids=skip_ids,
            skip_existing=skip_existing,
        )

        success = state.get("status") == "completed"
        print(json.dumps({
            "success": success,
            "data": {
                "job_id": job_id,
                "status": state.get("status"),
                "summary": state.get("summary", {}),
            },
            "error": None if success else f"Crawl ended with status: {state.get('status')}",
            "platform": platform,
        }, ensure_ascii=False, default=str))
    except Exception as exc:
        logger.exception("Bulk crawl failed")
        print(json.dumps({
            "success": False,
            "error": str(exc),
            "platform": platform,
        }, ensure_ascii=False, default=str))
        sys.exit(1)
    finally:
        if "crawler" in locals():
            crawler.close()


if __name__ == "__main__":
    main()
