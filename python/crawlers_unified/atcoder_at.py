"""AtCoder problem crawler — HTML page parsing."""
import json
import re
import requests
from bs4 import BeautifulSoup
from typing import Optional


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en,ja;q=0.9",
}


def _source_id_from_url(url: str) -> str:
    """Extract task ID from AtCoder URL.
    URL format: https://atcoder.jp/contests/{contest}/tasks/{task_id}
    """
    m = re.search(r"/tasks/([^/?]+)", url)
    if not m:
        raise ValueError(f"Cannot extract task ID from: {url}")
    return m.group(1)


def _fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _extract_time_memory(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract time limit and memory limit."""
    time_limit = ""
    memory_limit = ""

    # AtCoder puts limits in the task statement, e.g., "Time Limit: 2 sec / Memory Limit: 1024 MB"
    text = soup.get_text()
    tm = re.search(r"Time\s*Limit\s*:\s*(\d+)\s*sec", text, re.IGNORECASE)
    if tm:
        time_limit = f"{tm.group(1)}s"
    mm = re.search(r"Memory\s*Limit\s*:\s*(\d+)\s*MB", text, re.IGNORECASE)
    if mm:
        memory_limit = f"{mm.group(1)}MB"

    return time_limit, memory_limit


def _extract_samples(soup: BeautifulSoup) -> list[dict]:
    """Extract sample I/O from AtCoder task statement."""
    samples = []

    # AtCoder wraps samples in <div class="part"> with <h3>Sample X</h3>
    # English version uses <span class="lang-en">
    en_spans = soup.find_all("span", class_="lang-en")
    if en_spans:
        # Use the English version
        content = en_spans[0] if en_spans else soup
    else:
        content = soup

    # Find all <h3> with "Sample"
    sample_sections = content.find_all("h3", string=re.compile(r"Sample\s*(Input|Output)", re.IGNORECASE))
    if not sample_sections:
        sample_sections = content.find_all("h3", string=re.compile(r"(入力例|出力例)"))

    i = 0
    while i + 1 < len(sample_sections):
        h3_in = sample_sections[i]
        h3_out = sample_sections[i + 1]

        # Check they're a pair
        in_text = h3_in.get_text().strip()
        out_text = h3_out.get_text().strip()

        if ("Input" in in_text or "入力" in in_text) and ("Output" in out_text or "出力" in out_text):
            pre_in = h3_in.find_next("pre")
            pre_out = h3_out.find_next("pre")

            if pre_in and pre_out:
                samples.append({
                    "input": pre_in.get_text().strip(),
                    "output": pre_out.get_text().strip(),
                    "note": "",
                })
            i += 2
        else:
            i += 1

    return samples


def _build_full_content(soup: BeautifulSoup) -> str:
    """Build Markdown content from AtCoder task statement."""
    parts = []

    # Title
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip()
        title = re.sub(r"\s*[-–—]\s*AtCoder.*$", "", title)
        parts.append(f"# {title}")

    # Use English version — find lang-en span and get its content
    en_span = soup.find("span", class_="lang-en")
    if not en_span:
        # Fallback: try to find the task statement area
        task_div = soup.find("div", id="task-statement")
        if task_div:
            content_elements = task_div
        else:
            content_elements = soup
    else:
        content_elements = en_span

    # Walk through direct children, grouping by <h3> sections
    current_key = ""
    current_texts: dict[str, list[str]] = {}

    container = content_elements
    # If en_span is inside another span, its children include div.part > section > h3 + p
    def walk_children(el):
        for child in (el.children if hasattr(el, "children") else []):
            if not hasattr(child, "name") or child.name is None:
                continue

            if child.name == "h3":
                h3_text = child.get_text().strip()
                return h3_text
            elif child.name == "div" and "part" in (child.get("class") or []):
                section = child.find("section")
                if section:
                    h3 = section.find("h3")
                    p_tags = section.find_all("p")
                    pre_tags = section.find_all("pre")
                    ul_tags = section.find_all("ul")

                    if h3:
                        h3_text = h3.get_text().strip()
                        content_parts = []
                        for p in p_tags:
                            content_parts.append(p.get_text().strip())
                        for pre in pre_tags:
                            content_parts.append(f"```\n{pre.get_text().strip()}\n```")
                        for ul in ul_tags:
                            for li in ul.find_all("li"):
                                content_parts.append(f"- {li.get_text().strip()}")

                        if content_parts:
                            parts.append(f"## {h3_text}")
                            parts.extend(content_parts)
            elif child.name in ("p", "pre", "ul", "ol"):
                # Direct child content (without h3 wrapper)
                if child.name == "pre":
                    parts.append(f"```\n{child.get_text().strip()}\n```")
                elif child.name in ("ul", "ol"):
                    for li in child.find_all("li"):
                        parts.append(f"- {li.get_text().strip()}")
                else:
                    text = child.get_text().strip()
                    if text:
                        parts.append(text)

    # Walk through all elements in the container
    for child in container.children if hasattr(container, "children") else []:
        if not hasattr(child, "name") or child.name is None:
            continue

        if child.name == "div" and "part" in (child.get("class") or []):
            section = child.find("section")
            if not section:
                continue
            h3 = section.find("h3")
            if not h3:
                continue
            h3_text = h3.get_text().strip()

            # Collect all paragraph, pre, list content
            content_parts = []
            for el in section.children:
                if not hasattr(el, "name") or el.name is None:
                    continue
                if el.name in ("p",):
                    text = el.get_text().strip()
                    if text:
                        content_parts.append(text)
                elif el.name == "pre":
                    content_parts.append(f"```\n{el.get_text().strip()}\n```")
                elif el.name in ("ul", "ol"):
                    for li in el.find_all("li"):
                        content_parts.append(f"- {li.get_text().strip()}")

            if content_parts:
                parts.append(f"## {h3_text}")
                parts.extend(content_parts)

    return "\n\n".join(parts)


def fetch_problem(url: str) -> dict:
    """Fetch an AtCoder problem and return unified JSON."""
    source_id = _source_id_from_url(url)
    html = _fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_tag = soup.find("title")
    title = ""
    if title_tag:
        title = title_tag.get_text().strip()
        title = re.sub(r"\s*[-–—]\s*AtCoder.*$", "", title)

    # Also try <h2> for title
    if not title:
        h2 = soup.find("h2")
        if h2:
            title = h2.get_text().strip()

    time_limit, memory_limit = _extract_time_memory(soup)
    samples = _extract_samples(soup)

    # Parse from English content for description
    en_span = soup.find("span", class_="lang-en")
    description_html = ""
    if en_span:
        parent = en_span.parent
        if parent:
            description_html = str(parent)

    # Get difficulty from task statement or default
    difficulty = ""
    score_tag = soup.find(string=re.compile(r"(\d+)\s*点"))
    if score_tag:
        difficulty = score_tag.strip()

    raw_detail = {
        "description": description_html,
        "inputFormat": "",
        "outputFormat": "",
        "samples": samples,
        "note": "",
        "timeLimit": time_limit,
        "memoryLimit": memory_limit,
        "platformMeta": {
            "taskId": source_id,
        },
    }

    return {
        "title": title,
        "sourcePlatform": "atcoder",
        "sourceId": source_id,
        "sourceUrl": url,
        "difficultyRaw": difficulty,
        "difficultyNormalized": 5.0,
        "tagsNormalized": [],
        "tagsPlatform": {},
        "fullContent": _build_full_content(soup),
        "rawDetail": raw_detail,
    }


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://atcoder.jp/contests/DEGwer2023/tasks/1202Contest_j"
    result = fetch_problem(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
