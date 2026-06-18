"""Codeforces problem crawler — uses official API + HTML page scraping."""
import json
import re
import subprocess
import requests
from bs4 import BeautifulSoup
from typing import Optional


API_BASE = "https://codeforces.com/api"
PROBLEMS_URL = f"{API_BASE}/problemset.problems"
CONTEST_URL = f"{API_BASE}/contest.standings"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json",
}


def _parse_contest_index(url: str) -> tuple[int, str]:
    """Extract contestId and problem index from CF URL.
    URL format: https://codeforces.com/problemset/problem/{contestId}/{index}
    or https://codeforces.com/contest/{contestId}/problem/{index}
    """
    # /problemset/problem/2234/G
    m = re.search(r"/problemset/problem/(\d+)/([A-Z]\d*)", url)
    if m:
        return int(m.group(1)), m.group(2)
    # /contest/2234/problem/G
    m = re.search(r"/contest/(\d+)/problem/([A-Z]\d*)", url)
    if m:
        return int(m.group(1)), m.group(2)
    raise ValueError(f"Cannot parse contestId/index from: {url}")


def _api_get(endpoint: str, **params) -> dict:
    resp = requests.get(endpoint, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "OK":
        raise RuntimeError(f"CF API error: {data.get('comment', 'unknown')}")
    return data["result"]


def _fetch_problem_meta(contest_id: int, index: str) -> dict:
    """Get problem metadata from CF API."""
    all_problems = _api_get(PROBLEMS_URL)["problems"]
    for p in all_problems:
        if p.get("contestId") == contest_id and p.get("index") == index:
            return p
    raise RuntimeError(f"Problem {contest_id}/{index} not found")


def _curl_get(url: str) -> str:
    """Fetch a URL using system curl (CF blocks Python http clients)."""
    result = subprocess.run(
        ["curl", "-s", "-L", url, "-H", f"User-Agent: {HEADERS['User-Agent']}"],
        capture_output=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {result.stderr}")
    # CF pages are UTF-8 encoded
    return result.stdout.decode("utf-8", errors="replace")


def _fetch_problem_statement(contest_id: int, index: str) -> str:
    """Fetch problem statement HTML from the problemset page via curl."""
    url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    html = _curl_get(url)
    soup = BeautifulSoup(html, "html.parser")

    statement = soup.find("div", class_="problem-statement")
    if not statement:
        return ""

    # Remove header (title, time limit, memory limit are extracted separately)
    header = statement.find("div", class_="header")
    if header:
        header.decompose()

    # Remove MathJax processing markers
    html = str(statement)
    return html


def _extract_samples(statement_html: str) -> list[dict]:
    """Extract sample I/O from problem statement HTML."""
    soup = BeautifulSoup(statement_html, "html.parser")
    samples = []

    # CF samples are in <div class="sample-test">
    sample_div = soup.find("div", class_="sample-test")
    if not sample_div:
        return samples

    inputs = sample_div.find_all("div", class_="input")
    outputs = sample_div.find_all("div", class_="output")

    for inp, out in zip(inputs, outputs):
        inp_pre = inp.find("pre")
        out_pre = out.find("pre")
        inp_blocks = [br for br in inp.find_all("br")] if inp else []

        samples.append({
            "input": _clean_pre(inp_pre) if inp_pre else "",
            "output": _clean_pre(out_pre) if out_pre else "",
            "note": "",
        })

    # Check for note div outside sample-test
    note_div = soup.find("div", class_="note")
    if note_div and samples:
        note_pre = note_div.find("pre")
        if note_pre:
            samples[-1]["note"] = _clean_pre(note_pre)

    return samples


def _clean_pre(el) -> str:
    """Extract clean text from a <pre> element, handling <br> line breaks."""
    parts = []
    for child in el.children:
        if isinstance(child, str):
            parts.append(str(child))
        elif hasattr(child, "name"):
            if child.name == "br":
                parts.append("\n")
            else:
                text = child.get_text() if hasattr(child, "get_text") else str(child)
                parts.append(text)
    text = "".join(parts)
    # Clean excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _html_to_markdown(html: str) -> str:
    """Convert CF problem statement HTML to Markdown."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove MathJax spans (keep their text content)
    for mj in soup.find_all("span", class_="MathJax"):
        mj.unwrap()
    for mj in soup.find_all("span", class_="MathJax_Preview"):
        mj.decompose()

    # Convert common elements
    for p in soup.find_all("p"):
        p.insert_after("\n\n")

    for li in soup.find_all("li"):
        li.insert_before("- ")
        li.insert_after("\n")

    for center in soup.find_all("center"):
        center.unwrap()

    # Convert sub/sup to LaTeX
    for sub in soup.find_all("sub"):
        sub.replace_with(f"_{{{sub.get_text()}}}")
    for sup in soup.find_all("sup"):
        sup.replace_with(f"^{{{sup.get_text()}}}")

    text = soup.get_text()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _build_full_content(meta: dict, statement_html: str) -> str:
    """Build full Markdown content."""
    parts = []
    parts.append(f"# {meta.get('name', '')}")

    # Extract sections from statement HTML
    soup = BeautifulSoup(statement_html, "html.parser")

    # Process all children sections
    current_section = ""
    sections: dict[str, list[str]] = {}

    for child in soup.children:
        if not hasattr(child, "name") or child.name is None:
            continue
        if child.name in ("div",):
            title_div = child.find("div", class_="section-title")
            if title_div:
                current_section = title_div.get_text().strip()
                if current_section not in sections:
                    sections[current_section] = []
                continue
        if current_section:
            sections.setdefault(current_section, []).append(_html_to_markdown(str(child)))

    for title, content_parts in sections.items():
        parts.append(f"## {title}")
        for cp in content_parts:
            if cp.strip():
                parts.append(cp)

    parts.append("## 样例")
    return "\n\n".join(parts)


def fetch_problem(url: str) -> dict:
    """Fetch a Codeforces problem and return unified JSON."""
    contest_id, index = _parse_contest_index(url)
    meta = _fetch_problem_meta(contest_id, index)
    statement_html = _fetch_problem_statement(contest_id, index)
    samples = _extract_samples(statement_html)

    difficulty_raw = str(meta.get("rating", 0))
    rating = meta.get("rating", 0)
    difficulty_normalized = min(rating / 350.0 * 10.0, 10.0) if rating else 5.0

    raw_detail = {
        "description": statement_html,
        "inputFormat": "",
        "outputFormat": "",
        "samples": samples,
        "note": "",
        "timeLimit": "",
        "memoryLimit": "",
        "platformMeta": {
            "contestId": contest_id,
            "index": index,
            "rating": rating,
            "points": meta.get("points"),
        },
    }

    return {
        "title": meta.get("name", f"{contest_id}{index}"),
        "sourcePlatform": "codeforces",
        "sourceId": f"{contest_id}/{index}",
        "sourceUrl": f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
        "difficultyRaw": difficulty_raw,
        "difficultyNormalized": round(difficulty_normalized, 1),
        "tagsNormalized": [t.lower().replace(" ", "-") for t in meta.get("tags", [])],
        "tagsPlatform": {
            "tags": meta.get("tags", []),
            "rating": rating,
        },
        "fullContent": _build_full_content(meta, statement_html),
        "rawDetail": raw_detail,
    }


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://codeforces.com/problemset/problem/2234/G"
    result = fetch_problem(url)
    # Use ascii-safe JSON to avoid Windows GBK encoding issues
    print(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8", errors="replace").decode("utf-8"))
