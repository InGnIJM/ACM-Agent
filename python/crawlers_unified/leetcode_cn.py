"""LeetCode CN problem crawler — fetches via GraphQL API."""
import json
import re
import requests
from typing import Optional


GRAPHQL_URL = "https://leetcode.cn/graphql/"

QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    title
    translatedTitle
    titleSlug
    difficulty
    translatedContent
    topicTags { name translatedName slug }
    hints
    codeSnippets { lang langSlug code }
    metaData
    exampleTestcases
    questionFrontendId
    stats
    similarQuestions
    mysqlSchemas
    dataSchemas
  }
}
"""

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://leetcode.cn/",
}


def _slug_from_url(url: str) -> str:
    m = re.search(r"/problems/([^/]+)", url)
    if not m:
        raise ValueError(f"Cannot extract slug from URL: {url}")
    return m[1]


def _fetch_question(slug: str) -> dict:
    payload = {
        "operationName": "questionData",
        "variables": {"titleSlug": slug},
        "query": QUESTION_QUERY,
    }
    resp = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    q = data.get("data", {}).get("question")
    if not q:
        raise RuntimeError(f"No question data for slug: {slug}")
    return q


def _parse_samples(html_content: str) -> list[dict]:
    """Extract sample I/O pairs from LeetCode's HTML content."""
    samples = []
    # LeetCode wraps examples in <pre> blocks
    pre_blocks = re.findall(r"<pre>\s*(.*?)\s*</pre>", html_content, re.DOTALL)
    for block in pre_blocks:
        # Clean HTML tags
        clean = re.sub(r"<[^>]+>", "", block)
        lines = clean.strip().split("\n")
        input_lines = []
        output_lines = []
        note_lines = []
        current = None
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("输入") or stripped.startswith("Input"):
                current = "input"
                input_lines.append(stripped)
            elif stripped.startswith("输出") or stripped.startswith("Output"):
                current = "output"
                output_lines.append(stripped)
            elif stripped.startswith("解释") or stripped.startswith("Explanation"):
                current = "note"
                note_lines.append(stripped)
            elif current == "input":
                input_lines.append(stripped)
            elif current == "output":
                output_lines.append(stripped)
            elif current == "note":
                note_lines.append(stripped)
        if input_lines or output_lines:
            samples.append({
                "input": "\n".join(input_lines) if input_lines else clean,
                "output": "\n".join(output_lines) if output_lines else "",
                "note": "\n".join(note_lines) if note_lines else "",
            })
    return samples


def _build_full_content(q: dict) -> str:
    """Build a Markdown representation from question data."""
    parts = []

    title = q.get("translatedTitle") or q.get("title") or ""
    parts.append(f"# {title}")

    content = q.get("translatedContent") or ""
    if content:
        # Convert HTML to plain text (keep structure roughly)
        # Remove HTML tags, keep text
        clean = re.sub(r"<br\s*/?>", "\n", content)
        clean = re.sub(r"<p>", "\n\n", clean)
        clean = re.sub(r"</p>", "", clean)
        clean = re.sub(r"<strong>", "**", clean)
        clean = re.sub(r"</strong>", "**", clean)
        clean = re.sub(r"<em>", "*", clean)
        clean = re.sub(r"</em>", "*", clean)
        clean = re.sub(r"<code>", "`", clean)
        clean = re.sub(r"</code>", "`", clean)
        clean = re.sub(r"<pre>", "\n```\n", clean)
        clean = re.sub(r"</pre>", "\n```\n", clean)
        clean = re.sub(r"<ul>", "\n", clean)
        clean = re.sub(r"</ul>", "\n", clean)
        clean = re.sub(r"<li>", "- ", clean)
        clean = re.sub(r"</li>", "\n", clean)
        clean = re.sub(r"<[^>]+>", "", clean)
        clean = re.sub(r"\n{3,}", "\n\n", clean)
        parts.append(clean.strip())

    if q.get("hints"):
        parts.append("## 提示")
        for i, h in enumerate(q["hints"], 1):
            parts.append(f"{i}. {h}")

    return "\n\n".join(parts)


DIFFICULTY_MAP = {"Easy": 2.0, "Medium": 5.0, "Hard": 8.0}


def fetch_problem(url: str) -> dict:
    """Fetch a LeetCode CN problem and return unified JSON."""
    slug = _slug_from_url(url)
    q = _fetch_question(slug)

    difficulty = q.get("difficulty", "Medium")
    tags = q.get("topicTags") or []
    tag_names = [t.get("translatedName") or t.get("name", "") for t in tags]

    content_html = q.get("translatedContent") or ""
    samples = _parse_samples(content_html)

    raw_detail = {
        "description": content_html,
        "inputFormat": "",
        "outputFormat": "",
        "samples": samples,
        "note": "",
        "timeLimit": "",
        "memoryLimit": "",
        "platformMeta": {
            "questionId": q.get("questionId"),
            "questionFrontendId": q.get("questionFrontendId"),
            "acRate": q.get("stats"),
        },
    }

    return {
        "title": q.get("translatedTitle") or q.get("title") or slug,
        "sourcePlatform": "leetcode",
        "sourceId": slug,
        "sourceUrl": url,
        "difficultyRaw": difficulty,
        "difficultyNormalized": DIFFICULTY_MAP.get(difficulty, 5.0),
        "tagsNormalized": [_normalize_tag(t) for t in tag_names],
        "tagsPlatform": {
            "topicTags": [{"name": t.get("name"), "translatedName": t.get("translatedName")} for t in tags]
        },
        "fullContent": _build_full_content(q),
        "rawDetail": raw_detail,
    }


def _normalize_tag(tag: str) -> str:
    """Normalize a LeetCode tag to a common lowercase form."""
    m = {
        "字符串": "string", "动态规划": "dynamic-programming", "递归": "recursion",
        "数学": "math", "数组": "array", "哈希表": "hash-table",
        "二分查找": "binary-search", "贪心": "greedy", "树": "tree",
        "深度优先搜索": "dfs", "广度优先搜索": "bfs",
        "双指针": "two-pointers", "位运算": "bit-manipulation",
        "回溯": "backtracking", "栈": "stack", "堆（优先队列）": "heap",
        "排序": "sorting", "模拟": "simulation",
        "图": "graph", "链表": "linked-list",
        "分治": "divide-and-conquer", "滑动窗口": "sliding-window",
        "字典树": "trie", "并查集": "union-find", "前缀和": "prefix-sum",
    }
    return m.get(tag, tag.lower().replace(" ", "-"))


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        url = "https://leetcode.cn/problems/regular-expression-matching/description/"
    else:
        url = sys.argv[1]
    result = fetch_problem(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
