"""
Multi-platform login helper
- Manual mode: opens browser, waits for Enter key
- Auto mode (--input): opens browser, auto-detects login, saves cookies
"""
import argparse
import json
import sys
import time
from pathlib import Path
from DrissionPage import ChromiumPage

COOKIE_DIR = Path("data/cookies")
COOKIE_DIR.mkdir(parents=True, exist_ok=True)

PLATFORM_CONFIG = {
    "luogu": {"name": "洛谷", "url": "https://www.luogu.com.cn/auth/login"},
    "leetcode": {"name": "力扣", "url": "https://leetcode.cn/accounts/login/"},
    "codeforces": {"name": "Codeforces", "url": "https://codeforces.com/enter"},
    "nowcoder": {"name": "牛客", "url": "https://ac.nowcoder.com/acm/login"},
    "atcoder": {"name": "AtCoder", "url": "https://atcoder.jp/login"},
}


def main():
    parser = argparse.ArgumentParser(description="Platform login helper")
    parser.add_argument("--platform", default="luogu", choices=list(PLATFORM_CONFIG.keys()))
    parser.add_argument("--input", default=None, help="JSON input (NestJS mode)")
    args = parser.parse_args()

    if args.input:
        params = json.loads(args.input)
        platform = params.get("platform", "luogu")
        auto = True
    else:
        platform = args.platform
        auto = False

    cfg = PLATFORM_CONFIG.get(platform, PLATFORM_CONFIG["luogu"])
    cookie_file = COOKIE_DIR / f"{platform}.json"

    print(f"Opening {cfg['name']} login page: {cfg['url']}", flush=True)

    page = ChromiumPage()
    page.get(cfg["url"])

    if auto:
        # Wait for user to login (detect URL change from login page)
        for _ in range(120):
            time.sleep(1)
            try:
                url = page.url
                if "login" not in url.lower():
                    break
            except Exception:
                pass
        cookies = page.cookies()
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(json.dumps({"success": True, "platform": platform, "cookies": len(cookies)}), flush=True)
        page.quit()
        return

    input("\nLogin complete? Press Enter to save cookies...")
    cookies = page.cookies()
    with open(cookie_file, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(cookies)} cookies to {cookie_file}")
    page.quit()


if __name__ == "__main__":
    main()
