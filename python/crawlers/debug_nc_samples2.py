"""Debug: check raw HTML structure of NowCoder sample section."""
import sys, re
sys.path.insert(0, ".")
from crawlers.base import BaseCrawler
from bs4 import BeautifulSoup

# Quick fetch without full crawler
import requests
url = "https://ac.nowcoder.com/acm/problem/317391"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, timeout=30)
html = resp.text

soup = BeautifulSoup(html, "html.parser")
sample_el = soup.select_one(".question-oi")
if not sample_el:
    print("NO .question-oi found!")
    # Try other selectors
    for sel in [".sample", ".question-sample", "[class*=sample]", "[class*=oi]"][:4]:
        print(f"  {sel}: {bool(soup.select_one(sel))}")
else:
    print("=== .question-oi structure ===")
    # Check for question-oi-mod blocks
    mods = sample_el.select(".question-oi-mod")
    print(f".question-oi-mod count: {len(mods)}")
    for i, mod in enumerate(mods):
        h2 = mod.find("h2")
        pres = mod.find_all("pre")
        h2_text = h2.get_text(strip=True) if h2 else "NO H2"
        print(f"  Mod {i}: h2='{h2_text}' pres={len(pres)}")
        for j, pre in enumerate(pres):
            txt = pre.get_text("\n", strip=True)[:100]
            print(f"    pre {j}: {repr(txt)}")

    # Check all <pre> in question-oi
    all_pres = sample_el.find_all("pre")
    print(f"\nTotal <pre> in .question-oi: {len(all_pres)}")
    for i, pre in enumerate(all_pres):
        txt = pre.get_text("\n", strip=True)[:100]
        print(f"  pre {i}: {repr(txt)}")

    # Check for example markers in HTML
    raw_html = str(sample_el)
    markers = re.findall(r"(?:示例|样例)\s*\d", raw_html)
    print(f"\nExample markers found: {markers}")

    # Test Strategy 4 directly
    clean = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = clean.replace("复制", "")
    sections = re.split(r"(?:示例|样例)\s*\d*\s*[:：]?\s*", clean)
    print(f"\nStrategy 4 sections: {len(sections)}")
    for i, s in enumerate(sections[1:6]):
        print(f"  Section {i+1}: {repr(s[:200])}")
