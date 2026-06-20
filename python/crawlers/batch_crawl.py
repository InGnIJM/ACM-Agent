"""
Batch crawler: crawl all observed users across platforms.

Fetches observed users from the database (Prisma) or a JSON fallback file,
iterates over configured platforms, executes platform-specific crawlers
for each user, persists results as JSON files, and optionally triggers
the DataImporter to upsert records into the database.

Usage::

    import asyncio
    from crawlers.batch_crawl import crawl_all_observed_users

    summary = asyncio.run(crawl_all_observed_users())
    print(summary)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from crawlers.base import CrawlResult, CrawlerExecutor, DataImporter
from crawlers.luogu import LuoguCrawler
from crawlers.leetcode import LeetCodeCrawler
from crawlers.codeforces import CodeforcesCrawler

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Platform registry
# ──────────────────────────────────────────────

_PLATFORM_CRAWLERS: Dict[str, type] = {
    "luogu": LuoguCrawler,
    "leetcode": LeetCodeCrawler,
    "codeforces": CodeforcesCrawler,
}

# Default config file for observed users (fallback when DB is unavailable).
_DEFAULT_USERS_FILE: str = "data/observed_users.json"

# Default data directory for crawl outputs.
_DEFAULT_DATA_DIR: str = "data/raw"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _load_users_from_file(filepath: str) -> List[Dict[str, Any]]:
    """Load observed users from a JSON file.

    Expected format (array of objects)::

        [
          {"uid": "1001", "platforms": ["luogu"]},
          {"uid": "tourist", "platforms": ["codeforces", "leetcode"]}
        ]

    If ``platforms`` is omitted the user is crawled on all known platforms.
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning("Observed users file not found: %s", filepath)
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read observed users file %s: %s", filepath, exc)
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Support a top-level {"users": [...]} envelope.
        return data.get("users", [])
    logger.warning("Unexpected observed users file format in %s", filepath)
    return []


async def _load_users_from_db() -> List[Dict[str, Any]]:
    """Fetch observed users from the Prisma database.

    Queries the ``observed_user`` table.  Returns an empty list if Prisma
    is not installed or the table is unavailable.
    """
    try:
        from prisma import Prisma  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("Prisma not installed; cannot load users from DB")
        return []

    prisma = Prisma()
    try:
        await prisma.connect()
        # The observed_user table is expected to have at least uid +
        # platforms columns.
        records = await prisma.observed_user.find_many()  # type: ignore[attr-defined]
        return [
            {
                "uid": getattr(r, "uid", ""),
                "platforms": getattr(r, "platforms", None),
            }
            for r in records
        ]
    except Exception as exc:
        logger.warning("Failed to load observed users from DB: %s", exc)
        return []
    finally:
        await prisma.disconnect()


async def _fetch_users(
    users: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Resolve the observed user list.

    Resolution order:
    1. Explicit *users* argument.
    2. Database (Prisma observed_user table).
    3. JSON fallback file (``data/observed_users.json``).
    """
    if users is not None:
        return users

    db_users = await _load_users_from_db()
    if db_users:
        logger.info("Loaded %d observed users from database", len(db_users))
        return db_users

    file_users = _load_users_from_file(_DEFAULT_USERS_FILE)
    if file_users:
        logger.info("Loaded %d observed users from %s", len(file_users), _DEFAULT_USERS_FILE)
        return file_users

    logger.warning("No observed users found (DB or file).")
    return []


def _resolve_platforms_for_user(
    user: Dict[str, Any],
    requested_platforms: Optional[List[str]],
) -> List[str]:
    """Determine which platforms to crawl for a given user.

    If the user dict has a ``platforms`` key it takes precedence over the
    global *requested_platforms* list.
    """
    user_platforms = user.get("platforms")
    if user_platforms and isinstance(user_platforms, list):
        return [p for p in user_platforms if p in _PLATFORM_CRAWLERS]
    if requested_platforms:
        return [p for p in requested_platforms if p in _PLATFORM_CRAWLERS]
    return list(_PLATFORM_CRAWLERS.keys())


def _make_filename(prefix: str, uid: str, extension: str = "json") -> str:
    """Generate a timestamped filename: ``{date}_{prefix}_{uid}.json``."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_uid = str(uid).replace("/", "_").replace("\\", "_")
    return f"{today}_{prefix}_{safe_uid}.{extension}"


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────


async def crawl_all_observed_users(
    users: Optional[List[Dict[str, Any]]] = None,
    platforms: Optional[List[str]] = None,
    data_dir: str = _DEFAULT_DATA_DIR,
    trigger_import: bool = True,
) -> Dict[str, Any]:
    """Fetch observed users, iterate platforms, crawl, save, and import.

    Args:
        users: Optional explicit list of user dicts.  Each dict must have
               ``uid`` (str) and optionally ``platforms`` (list of str).
               When omitted users are loaded from the database or fallback
               JSON file.
        platforms: Platforms to crawl (e.g. ``["luogu", "codeforces"]``).
                   Defaults to all registered platforms.
        data_dir: Base directory for saved JSON outputs.  Files are written
                  under ``{data_dir}/{platform}/profiles/`` and
                  ``{data_dir}/{platform}/records/``.
        trigger_import: If True, run ``DataImporter.import_all()`` after all
                        crawling is complete.

    Returns:
        A summary dict::

            {
              "started_at": "2025-06-13T12:00:00+00:00",
              "finished_at": "2025-06-13T12:05:00+00:00",
              "users_crawled": 3,
              "platforms": {
                "luogu":    {"profiles": 2, "records": 100, "errors": 0},
                "leetcode": {"profiles": 1, "records": 20, "errors": 0},
              },
              "import": {"luogu": {"problems": 0, "records": 2}, ...},
              "errors": []
            }
    """
    started_at = datetime.now(timezone.utc).isoformat()
    errors: List[Dict[str, Any]] = []
    platform_stats: Dict[str, Dict[str, int]] = {}

    # ── resolve users ─────────────────────────────────────────
    resolved_users = await _fetch_users(users)
    if not resolved_users:
        return {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "users_crawled": 0,
            "platforms": {},
            "import": {},
            "errors": [{"message": "No observed users found"}],
        }

    # ── crawl each user on each platform ──────────────────────
    for user in resolved_users:
        uid = user.get("uid", "")
        if not uid:
            errors.append({"uid": "", "error": "User entry missing 'uid'", "user": user})
            continue

        user_platforms = _resolve_platforms_for_user(user, platforms)

        for platform in user_platforms:
            crawler_cls = _PLATFORM_CRAWLERS.get(platform)
            if crawler_cls is None:
                errors.append({"uid": uid, "platform": platform, "error": "Unknown platform"})
                continue

            # Initialize per-platform counters.
            if platform not in platform_stats:
                platform_stats[platform] = {"profiles": 0, "records": 0, "errors": 0}

            crawler = crawler_cls(data_dir=data_dir)
            executor = CrawlerExecutor(crawler)

            try:
                # ── fetch profile ──────────────────────────
                profile_result = executor.execute("fetch_user_profile", str(uid))
                if profile_result.success and profile_result.data:
                    profile_file = _make_filename("profile", uid)
                    crawler.save_json(
                        profile_result.data,
                        filename=profile_file,
                        sub_dir=f"{platform}/profiles",
                    )
                    platform_stats[platform]["profiles"] += 1
                else:
                    err_msg = profile_result.error or "Unknown error fetching profile"
                    errors.append({"uid": uid, "platform": platform, "phase": "profile", "error": err_msg})
                    platform_stats[platform]["errors"] += 1
                    logger.warning("Profile fetch failed for %s on %s: %s", uid, platform, err_msg)

                # ── fetch records ──────────────────────────
                records_result = executor.execute("fetch_user_records", str(uid))
                if records_result.success and records_result.data:
                    records_file = _make_filename("records", uid)
                    crawler.save_json(
                        records_result.data,
                        filename=records_file,
                        sub_dir=f"{platform}/records",
                    )
                    record_count = (
                        len(records_result.data)
                        if isinstance(records_result.data, list)
                        else 1
                    )
                    platform_stats[platform]["records"] += record_count
                else:
                    err_msg = records_result.error or "Unknown error fetching records"
                    errors.append({"uid": uid, "platform": platform, "phase": "records", "error": err_msg})
                    platform_stats[platform]["errors"] += 1
                    logger.warning("Records fetch failed for %s on %s: %s", uid, platform, err_msg)

            except Exception as exc:
                errors.append({"uid": uid, "platform": platform, "error": str(exc)})
                platform_stats[platform]["errors"] += 1
                logger.exception("Unexpected error crawling %s on %s", uid, platform)
            finally:
                crawler.close()

    # ── trigger import ──────────────────────────────────────
    import_results: Dict[str, Any] = {}
    if trigger_import:
        try:
            from prisma import Prisma  # type: ignore[import-untyped]

            prisma = Prisma()
            await prisma.connect()
            try:
                importer = DataImporter(prisma)
                import_results = await importer.import_all()
            finally:
                await prisma.disconnect()
        except ImportError:
            logger.warning("Prisma not installed; skipping import step")
            import_results = {"error": "Prisma not installed"}
        except Exception as exc:
            logger.exception("Import failed")
            import_results = {"error": str(exc)}

    finished_at = datetime.now(timezone.utc).isoformat()

    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "users_crawled": len(resolved_users),
        "platforms": platform_stats,
        "import": import_results,
        "errors": errors,
    }


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────


def main(argv: Optional[list] = None) -> None:
    """CLI wrapper for ``crawl_all_observed_users``.

    Usage::

        python batch_crawl.py [--platforms luogu leetcode] [--no-import]
    """
    import argparse

    parser = argparse.ArgumentParser(description="Batch crawl all observed users")
    parser.add_argument(
        "--platforms",
        nargs="*",
        default=None,
        help="Platforms to crawl (default: all registered)",
    )
    parser.add_argument(
        "--no-import",
        action="store_true",
        help="Skip the final DB import step",
    )
    parser.add_argument(
        "--data-dir",
        default=_DEFAULT_DATA_DIR,
        help="Base directory for crawl output JSON files",
    )
    parser.add_argument(
        "--users-file",
        default=None,
        help="Path to observed users JSON file (overrides DB and default fallback)",
    )
    args = parser.parse_args(argv)

    # Resolve users (explicit file > DB > default fallback).
    explicit_users: Optional[List[Dict[str, Any]]] = None
    if args.users_file:
        explicit_users = _load_users_from_file(args.users_file)
        if not explicit_users:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": f"No users found in {args.users_file}",
                    },
                    ensure_ascii=False,
                )
            )
            return

    summary = asyncio.run(
        crawl_all_observed_users(
            users=explicit_users,
            platforms=args.platforms,
            data_dir=args.data_dir,
            trigger_import=not args.no_import,
        )
    )

    json_str = json.dumps(summary, ensure_ascii=False, default=str)
    sys.stdout.buffer.write((json_str + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
