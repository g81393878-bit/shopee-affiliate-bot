import json
import pathlib
import sys
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

cookies = json.loads(open("tools/tiktok_cookies.json", encoding="utf-8").read())
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
    )
    ctx.add_cookies(cookies)
    page = ctx.new_page()
    page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=40000)
    page.wait_for_timeout(6000)
    print("Page URL:", page.url)
    print("Page Title:", page.title())
    file_inputs = page.locator('input[type="file"]').count()
    print("File Inputs Count:", file_inputs)
    buttons = [b.inner_text().strip() for b in page.locator("button").all() if b.inner_text().strip()]
    print("Buttons on page:", buttons[:10])
    browser.close()
