"""Debug NowCoder sample parsing for problem 317391."""
import sys, re, json
sys.path.insert(0, ".")
from crawlers.nowcoder import NowCoderCrawler
from bs4 import BeautifulSoup

# Load the saved raw data
with open("data/raw/nowcoder/problems/2026-06-17_317391.json") as f:
    raw = json.load(f)

# Simulate what fetch_problem does
record = raw.get("data", raw)
html = record.get("_html", "")

# Need to re-fetch the HTML since it's not saved
# Instead, let's look at the raw sample data
print("=== Raw samples from JSON ===")
print(json.dumps(record.get("samples", []), indent=2, ensure_ascii=False))

# Check if we can get the HTML from the raw data
if "_html" in record:
    print("\n=== HTML available, parsing... ===")
else:
    print("\n=== No HTML saved in raw data ===")
    print("Keys:", list(record.keys()))

# Check description for sample markers
desc = record.get("description", "")
print("\n=== Description (first 1000 chars) ===")
print(desc[:1000])
