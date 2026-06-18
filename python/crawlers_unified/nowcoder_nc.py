"""NowCoder problem crawler — HTML page parsing."""
import json
import re
import requests
from bs4 import BeautifulSoup
from typing import Optional


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}


def _source_id_from_url(url: str) -> str:
    m = re.search(r"/problem/(\d+)", url)
    if not m:
        raise ValueError(f"Cannot extract source ID from: {url}")
    return m.group(1)


def _clean_text(text: str) -> str:
    """Remove U+200B zero-width spaces and other invisible characters."""
    text = text.replace("​", "").replace("‌", "").replace("‍", "")
    text = text.replace("﻿", "").replace("\xa0", " ")
    return text.strip()


def _extract_samples(soup: BeautifulSoup) -> list[dict]:
    """Extract sample I/O from NowCoder problem page using question-oi divs."""
    samples = []

    # NowCoder wraps samples in <div class="question-oi">
    oi_divs = soup.find_all("div", class_="question-oi")
    for oi in oi_divs:
        inp = ""
        out = ""

        # Find input and output <pre> blocks within question-oi-cont
        mods = oi.find_all("div", class_="question-oi-mod")
        for mod in mods:
            h2 = mod.find("h2")
            if not h2:
                continue
            label = h2.get_text().strip()
            pre = mod.find("pre")
            if not pre:
                continue
            text = _clean_text(pre.get_text())
            if "输入" in label:
                inp = text
            elif "输出" in label:
                out = text

        if inp or out:
            samples.append({
                "input": inp,
                "output": out,
                "note": "",
            })

    return samples


def fetch_problem(url: str) -> dict:
    """Fetch a NowCoder problem and return unified JSON."""
    source_id = _source_id_from_url(url)

    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    # Force UTF-8 encoding
    resp.encoding = "utf-8"
    html = resp.text

    # Clean zero-width spaces
    html = _clean_text(html)

    soup = BeautifulSoup(html, "html.parser")

    # Title: from <title> or page heading
    title_tag = soup.find("title")
    title = ""
    if title_tag:
        title_text = title_tag.get_text().strip()
        # Remove " - 牛客网" suffix
        title = re.sub(r"\s*[-–—]\s*牛客网.*$", "", title_text)

    # Also try to find title in the page content
    if not title:
        title_h = soup.find("span", class_="terminal-topic-title")
        if title_h:
            title = title_h.get_text().strip()

    # Content area
    content_area = soup.find("div", class_="terminal-topic")
    content_html = str(content_area) if content_area else ""

    # Extract description, input/output format, etc.
    description = ""
    input_format = ""
    output_format = ""
    note = ""

    if content_area:
        # NowCoder uses headers like "题目描述", "输入描述", "输出描述", "备注"
        sections = {}
        current_key = "description"

        for child in content_area.children:
            if not hasattr(child, "name") or child.name is None:
                continue

            text = child.get_text().strip()
            if not text:
                continue

            if "题目描述" in text or "题描述" in text:
                current_key = "description"
                continue
            elif "输入描述" in text:
                current_key = "inputFormat"
                continue
            elif "输出描述" in text:
                current_key = "outputFormat"
                continue
            elif "示例" in text and "输入" in text:
                current_key = "samples"
                continue
            elif "备注" in text or "说明" in text:
                current_key = "note"
                continue

            sections.setdefault(current_key, []).append(str(child))

        description = "\n".join(sections.get("description", []))
        input_format = "\n".join(sections.get("inputFormat", []))
        output_format = "\n".join(sections.get("outputFormat", []))
        note = "\n".join(sections.get("note", []))

    # Extract time/memory limits
    time_limit = ""
    memory_limit = ""
    limit_text = soup.get_text()
    tm = re.search(r"时间限制[：:]\s*([\d.]+)\s*秒?", limit_text)
    if tm:
        time_limit = f"{tm.group(1)}s"
    mm = re.search(r"空间限制[：:]\s*(\d+)\s*[MB]", limit_text)
    if mm:
        memory_limit = f"{mm.group(1)}MB"

    samples = _extract_samples(soup)

    # Build full content markdown
    parts = [f"# {title}"]
    if description:
        parts.append(description)
    if input_format:
        parts.append(f"## 输入描述\n{input_format}")
    if output_format:
        parts.append(f"## 输出描述\n{output_format}")

    # Parse tags from page
    tags = []
    tag_links = soup.find_all("a", href=re.compile(r"/search\?tag=|/problems/.*tag"))
    for tl in tag_links:
        tag_text = tl.get_text().strip()
        if tag_text and tag_text not in tags:
            tags.append(tag_text)

    raw_detail = {
        "description": content_html,
        "inputFormat": input_format,
        "outputFormat": output_format,
        "samples": samples,
        "note": note,
        "timeLimit": time_limit,
        "memoryLimit": memory_limit,
        "platformMeta": {
            "sourceId": source_id,
        },
    }

    return {
        "title": title,
        "sourcePlatform": "nowcoder",
        "sourceId": source_id,
        "sourceUrl": url,
        "difficultyRaw": "",
        "difficultyNormalized": 5.0,
        "tagsNormalized": [t.lower().replace(" ", "-") for t in tags],
        "tagsPlatform": {
            "tags": tags,
        },
        "fullContent": "\n\n".join(parts),
        "rawDetail": raw_detail,
    }


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://ac.nowcoder.com/acm/problem/317391"
    result = fetch_problem(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
