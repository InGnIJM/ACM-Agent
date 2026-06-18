"""Run all unified crawlers and save results as JSON files."""
import json
import os
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from leetcode_cn import fetch_problem as fetch_leetcode
from codeforces_cf import fetch_problem as fetch_codeforces
from nowcoder_nc import fetch_problem as fetch_nowcoder
from atcoder_at import fetch_problem as fetch_atcoder

# Reuse Luogu crawler
sys.path.insert(0, str(Path(__file__).parent.parent / "crawlers"))

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "unified"


def save_result(data: dict, platform: str):
    """Save a crawl result to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_id = data.get("sourceId", "unknown")
    filename = f"{platform}_{source_id.replace('/', '_')}.json"
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ Saved: {filepath}")
    return filepath


def crawl_all(urls: list[tuple[str, str]]) -> list[dict]:
    """Crawl all problems and return results."""
    results = []
    total = len(urls)

    for platform, url in urls:
        print(f"\n{'='*60}")
        print(f"[{platform}] {url}")
        print(f"{'='*60}")

        try:
            if platform == "leetcode":
                data = fetch_leetcode(url)
            elif platform == "codeforces":
                data = fetch_codeforces(url)
            elif platform == "nowcoder":
                data = fetch_nowcoder(url)
            elif platform == "atcoder":
                data = fetch_atcoder(url)
            elif platform == "luogu":
                data = fetch_luogu(url)
            else:
                print(f"  ❌ Unknown platform: {platform}")
                continue

            save_result(data, platform)
            results.append(data)
            print(f"  ✅ Title: {data.get('title', 'N/A')}")
            print(f"  ✅ Difficulty: {data.get('difficultyRaw', 'N/A')} → {data.get('difficultyNormalized', 'N/A')}")
            print(f"  ✅ Tags: {data.get('tagsNormalized', [])}")
            print(f"  ✅ Samples: {len(data.get('rawDetail', {}).get('samples', []))}")

        except Exception as e:
            print(f"  ❌ Failed: {type(e).__name__}: {e}")

    return results


def fetch_luogu(url: str) -> dict:
    """Fetch Luogu problem using existing crawler."""
    from luogu import LuoguCrawler
    source_id = url.rstrip("/").split("/")[-1]
    crawler = LuoguCrawler(data_dir=str(Path(__file__).parent.parent / "data" / "raw"))
    result = crawler.fetch_problem(source_id)

    if not result.success or not result.data:
        raise RuntimeError(f"Luogu crawl failed: {result.error}")

    data = result.data
    if isinstance(data, dict) and "problem" in data:
        prob = data["problem"]
    else:
        prob = data

    crawler.close()

    # Map Luogu fields to unified format
    title = prob.get("title") or prob.get("pid", source_id)
    difficulty_raw = str(prob.get("difficulty", ""))
    tags = prob.get("tags") or []
    tag_names = [str(t) for t in tags]

    # Luogu difficulty: 0=未评定, then 1-7
    diff_map = {0: 1.0, 1: 2.0, 2: 3.0, 3: 5.0, 4: 6.0, 5: 7.5, 6: 8.5, 7: 9.5}
    diff_normalized = diff_map.get(prob.get("difficulty", 0), 5.0) if isinstance(prob.get("difficulty"), int) else 5.0

    raw_detail = {
        "description": prob.get("background", "") + "\n\n" + prob.get("description", ""),
        "inputFormat": prob.get("inputFormat", ""),
        "outputFormat": prob.get("outputFormat", ""),
        "samples": prob.get("samples", []),
        "note": prob.get("hint", ""),
        "timeLimit": prob.get("limits", {}).get("time", "") if isinstance(prob.get("limits"), dict) else "",
        "memoryLimit": prob.get("limits", {}).get("memory", "") if isinstance(prob.get("limits"), dict) else "",
        "platformMeta": {
            "pid": prob.get("pid", source_id),
            "difficulty": prob.get("difficulty"),
            "totalSubmit": prob.get("totalSubmit"),
            "totalAccepted": prob.get("totalAccepted"),
        },
    }

    return {
        "title": title,
        "sourcePlatform": "luogu",
        "sourceId": source_id,
        "sourceUrl": url,
        "difficultyRaw": difficulty_raw,
        "difficultyNormalized": diff_normalized,
        "tagsNormalized": tag_names,
        "tagsPlatform": {"tags": tag_names},
        "fullContent": _build_luogu_full(prob),
        "rawDetail": raw_detail,
    }


def _build_luogu_full(prob: dict) -> str:
    parts = [f"# {prob.get('title', '')}"]
    if prob.get("background"):
        parts.append(f"## 题目背景\n{prob['background']}")
    if prob.get("description"):
        parts.append(f"## 题目描述\n{prob['description']}")
    if prob.get("inputFormat"):
        parts.append(f"## 输入格式\n{prob['inputFormat']}")
    if prob.get("outputFormat"):
        parts.append(f"## 输出格式\n{prob['outputFormat']}")
    samples = prob.get("samples", [])
    if samples:
        parts.append("## 样例")
        for i, s in enumerate(samples, 1):
            if isinstance(s, list) and len(s) >= 2:
                parts.append(f"### 样例 {i}\n**输入:**\n```\n{s[0]}\n```\n**输出:**\n```\n{s[1]}\n```")
            elif isinstance(s, dict):
                parts.append(f"### 样例 {i}\n**输入:**\n```\n{s.get('input', s.get(0, ''))}\n```\n**输出:**\n```\n{s.get('output', s.get(1, ''))}\n```")
    if prob.get("hint"):
        parts.append(f"## 说明/提示\n{prob['hint']}")
    return "\n\n".join(parts)


# ─── Target URLs ──────────────────────────────────────────────────────────

TARGET_URLS = [
    ("luogu", "https://www.luogu.com.cn/problem/P6412"),
    ("leetcode", "https://leetcode.cn/problems/regular-expression-matching/description/"),
    ("nowcoder", "https://ac.nowcoder.com/acm/problem/317391"),
    ("codeforces", "https://codeforces.com/problemset/problem/2234/G"),
    ("atcoder", "https://atcoder.jp/contests/DEGwer2023/tasks/1202Contest_j"),
]


if __name__ == "__main__":
    results = crawl_all(TARGET_URLS)
    print(f"\n{'='*60}")
    print(f"Done. {len(results)}/{len(TARGET_URLS)} successful.")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"{'='*60}")
