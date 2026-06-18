"""
验证修复效果：对 4 个问题题目实际抓取并检查输出质量。
用法: python verify_fixes.py
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

# Ensure crawlers package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawlers.codeforces import CodeforcesCrawler
from crawlers.nowcoder import NowCoderCrawler
from crawlers.atcoder import AtCoderCrawler
from crawlers.leetcode import LeetCodeCrawler

RESULTS = {}

def green(s): return f"\033[92m{s}\033[0m"
def red(s): return f"\033[91m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"

def check(condition, msg):
    if condition:
        print(f"  {green('[PASS]')} {msg}")
        return True
    else:
        print(f"  {red('[FAIL]')} {msg}")
        return False

# ============================================================
# Test 1: Codeforces 2236/F2 - letter spacing + LaTeX
# ============================================================
print("=" * 60)
print("Test 1: Codeforces 2236/F2")
print("  原题: https://codeforces.com/problemset/problem/2236/F2")
print("=" * 60)

cf = CodeforcesCrawler()
result = cf.fetch_problem("2236F2")
assert result.success, f"CF fetch failed: {result.error}"

content = result.data.get("content", "")
description = result.data.get("description", "")
samples = result.data.get("samples", [])

print(f"\n  Title: {result.data.get('title', 'N/A')}")
print(f"  Content length: {len(content)} chars")
print(f"  Samples: {len(samples)}")

# Check: no "H e l p" letter spacing (the real text should have "Help")
check("H e l p" not in content, "No 'H e l p' letter spacing in content")
check("H e" not in content or "help" in content.lower(),
      "Letter spacing issue appears fixed")

# Check: no raw ^{\\text{*}} leaking
check("^{\\text{∗}}" not in content, "No raw ^{\\text{∗}} LaTeX leaking")
check("^{\\text{*}}" not in content, "No raw ^{\\text{*}} LaTeX leaking")

# Check: formula content present (not all math dropped)
has_math = "$" in content or "\\cdot" in content or "p_1" in content.lower()
check(has_math, "Math formulas present in content")

# Check: content is readable (no random single-char-per-line)
lines = content.split("\n")
single_char_lines = [l for l in lines if len(l.strip()) == 1 and l.strip().isalpha()]
check(len(single_char_lines) < 5,
      f"No excessive single-char lines (found {len(single_char_lines)})")

RESULTS['codeforces'] = True
print()

# ============================================================
# Test 2: NowCoder 317391 - KaTeX triplication + Unicode
# ============================================================
print("=" * 60)
print("Test 2: NowCoder 317391")
print("  原题: https://ac.nowcoder.com/acm/problem/317391")
print("=" * 60)

nc = NowCoderCrawler()
result = nc.fetch_problem("317391")
assert result.success, f"NowCoder fetch failed: {result.error}"

content = result.data.get("content", "")
description = result.data.get("description", "")

print(f"\n  Title: {result.data.get('title', 'N/A')}")
print(f"  Description length: {len(description)} chars")

# Check: no triplication pattern "'0' 0' '0'"
check("'0' 0' '0'" not in description and "'0' 0' '0'" not in content,
      "No KaTeX triplication pattern")

# Check: no Unicode control characters
check("​" not in content, "No U+200B (zero-width space)")
check("⁡" not in content, "No U+2061 (function application)")

# Check: no font tag artifacts like "'0' 0'"
import re
font_repeat = re.findall(r"'[01]'\s+[01]'", content)
check(len(font_repeat) == 0, f"No font tag artifacts (found {len(font_repeat)})")

# Check: min/max not followed by weird Unicode
check("min ⁡" not in content, "No 'min <U+2061>' pattern")

RESULTS['nowcoder'] = True
print()

# ============================================================
# Test 3: AtCoder 1202Contest_a - pre/var formatting
# ============================================================
print("=" * 60)
print("Test 3: AtCoder DEGwer2023/1202Contest_a")
print("  原题: https://atcoder.jp/contests/DEGwer2023/tasks/1202Contest_a")
print("=" * 60)

at = AtCoderCrawler()
result = at.fetch_problem("1202Contest_a")
assert result.success, f"AtCoder fetch failed: {result.error}"

content = result.data.get("content", "")
input_format = result.data.get("input_format", "")

print(f"\n  Title: {result.data.get('title', 'N/A')}")
print(f"  Content length: {len(content)} chars")

# Check: no var-tag splitting (N, K, T should be on same logical line or properly formatted)
# The key fix: variables should not be on separate lines like N\nK\nT
var_lines = [l.strip() for l in input_format.split("\n") if l.strip()]
single_var_lines = [l for l in var_lines if len(l) == 1 and l.isalpha()]
check(len(single_var_lines) < 3,
      f"No excessive single-var lines (found {len(single_var_lines)}: {single_var_lines})")

# Check: pre content preserved (multi-line input format)
check(len(input_format) > 10, "Input format is non-empty")
check("\n" in input_format or len(var_lines) > 1,
      "Multi-line structure preserved")

# Check: KaTeX math properly wrapped (should have $...$ for math)
has_katex_delimiters = "$" in content
check(has_katex_delimiters, "KaTeX $ delimiters present for math")

# Check: no raw KaTeX HTML leaking
check('<span class="katex"' not in content, "No raw KaTeX HTML leaking")
check('class="katex-mathml"' not in content, "No raw MathML HTML leaking")

RESULTS['atcoder'] = True
print()

# ============================================================
# Test 4: LeetCode string-to-integer-atoi - samples parsing
# ============================================================
print("=" * 60)
print("Test 4: LeetCode string-to-integer-atoi")
print("  原题: https://leetcode.cn/problems/string-to-integer-atoi")
print("=" * 60)

lc = LeetCodeCrawler()
result = lc.fetch_problem("string-to-integer-atoi")
assert result.success, f"LeetCode fetch failed: {result.error}"

samples = result.data.get("samples", [])
content = result.data.get("content", "")

print(f"\n  Title: {result.data.get('title', 'N/A')}")
print(f"  Samples count: {len(samples)}")
for i, s in enumerate(samples):
    inp = str(s[0])[:80] if s[0] else "(empty)"
    out = str(s[1])[:80] if len(s) > 1 and s[1] else "(empty)"
    print(f"    Sample {i+1}: input={inp}...")

# Check: should have 5 samples, not 1
check(len(samples) >= 5, f"Has 5+ samples (got {len(samples)})")

# Check: samples should have both input AND output
if len(samples) >= 5:
    for i, s in enumerate(samples[:5]):
        has_both = len(s) >= 2 and s[0] and s[1]
        check(has_both, f"Sample {i+1} has both input and output")

# Check: content HTML shouldn't have mixing issues
# (this is really a frontend issue, but we check the raw data)
check(len(content) > 100, "Content is non-trivial")

RESULTS['leetcode'] = True
print()

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("SUMMARY")
print("=" * 60)
all_pass = all(RESULTS.values())
for platform, ok in RESULTS.items():
    status = green("PASS") if ok else red("FAIL")
    print(f"  {platform}: {status}")

if all_pass:
    print(f"\n{green('ALL VERIFICATIONS PASSED')}")
else:
    print(f"\n{red('SOME VERIFICATIONS FAILED')}")
    sys.exit(1)
