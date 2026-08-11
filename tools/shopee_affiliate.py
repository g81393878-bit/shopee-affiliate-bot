#!/usr/bin/env python3
"""
Shopee Affiliate phone automation via adb.

Automates the Shopee app on an Android phone (USB debugging) to convert
normal Shopee product URLs into YOUR affiliate short links using the
built-in "Convert Link" (แปลงลิงก์) feature, then optionally pushes the
links into the Shopee Affiliate LINE bot backend.

Why Convert Link instead of copy-link? Android 10+ blocks reading the
clipboard over adb (service call returns "No items"), but the Convert Link
popup shows the generated links as on-screen text, which uiautomator can
read reliably.

Usage:
  python tools/shopee_affiliate.py convert <url1> [<url2> ...] [--bot-api URL]
  python tools/shopee_affiliate.py search <keyword>          # opens app search (ASCII only)
  python tools/shopee_affiliate.py update-bot <product_id> <affiliate_url>
      [--name NAME] [--price PRICE] [--bot-api URL] [--product-url URL]

Examples:
  python tools/shopee_affiliate.py convert https://shopee.co.th/product/1/2 \
      https://shopee.co.th/m/world-milk-day/
  python tools/shopee_affiliate.py convert <url> --bot-api https://shopee-affiliate-bot-9e9n.onrender.com

Notes:
  - Requires: phone with USB debugging enabled + authorized (adb devices),
    Shopee app installed, logged into the Shopee Affiliate account.
  - Keywords for `search` are ASCII-only (adb input text cannot type Thai);
    for Thai searches, type on the phone keyboard manually.
  - On Git Bash (MSYS), run through `python` (never pipe args through a
    native binary directly) so path-like args are not mangled.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.parse

DEFAULT_BOT_API = os.environ.get(
    "BOT_API", "https://shopee-affiliate-bot-9e9n.onrender.com"
)

# ---------------------------------------------------------------------------
# adb helpers
# ---------------------------------------------------------------------------

ADB_CANDIDATES = [
    "adb",
    r"C:\Users\Lenovo\AppData\Local\Android\Sdk\platform-tools\adb.exe",
    r"C:\Android\platform-tools\adb.exe",
    r"C:\platform-tools\adb.exe",
]


def adb():
    for c in ADB_CANDIDATES:
        if os.path.exists(c):
            return c
    # PATH lookup
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(p, "adb.exe")
        if os.path.exists(cand):
            return cand
        cand = os.path.join(p, "adb")
        if os.path.exists(cand):
            return cand
    sys.exit("adb not found. Install Android platform-tools (winget install Google.PlatformTools)")


def adb_devices(adb_bin):
    r = subprocess.run([adb_bin, "devices"], capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.strip() and "device" in l and "devices" not in l]
    return lines


def shell(adb_bin, *args, timeout=60):
    """Run `adb shell ...` and return stdout (UTF-8, tolerant of mojibake)."""
    r = subprocess.run([adb_bin, "shell", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.stdout


def dump_ui(adb_bin, retries=6, wait=2):
    """Dump the current accessibility tree to an XML string.

    Shopee home screen has autoplay videos -> uiautomator never reaches
    idle -> dump fails with 'could not get idle state'. Retry; static
    screens (search results, product pages, dialogs) dump fine.
    """
    for i in range(retries):
        out = shell(adb_bin, "uiautomator", "dump", "/sdcard/ui.xml")
        if "dumped to" in out:
            xml = shell(adb_bin, "cat", "/sdcard/ui.xml")
            if xml.strip():
                return xml
        time.sleep(wait)
    return None


def parse_nodes(xml):
    """Return [(text, bounds, clickable)] for every leaf node with text."""
    nodes = []
    for m in re.finditer(r"<node[^>]*?/>", xml):
        node = m.group(0)
        t = re.search(r'text="([^"]*)"', node)
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        cl = re.search(r'clickable="([^"]*)"', node)
        if t and b:
            nodes.append({
                "text": t.group(1),
                "bounds": [int(b.group(1)), int(b.group(2)), int(b.group(3)), int(b.group(4))],
                "clickable": cl.group(1) == "true" if cl else False,
            })
    return nodes


def find_text(xml, text, exact=True):
    """Return center (x, y) of the first node whose text matches."""
    nodes = parse_nodes(xml)
    for n in nodes:
        if exact and n["text"] == text:
            return center(n)
        if not exact and text in n["text"]:
            return center(n)
    return None


def all_text(xml, text):
    nodes = parse_nodes(xml)
    return [center(n) for n in nodes if n["text"] == text]


def center(n):
    x1, y1, x2, y2 = n["bounds"]
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def tap(adb_bin, x, y):
    shell(adb_bin, "input", "tap", str(x), str(y))


def tap_text(adb_bin, xml, text, exact=True):
    """Tap the center of the first node matching text. Returns True if found."""
    c = find_text(xml, text, exact=exact)
    if c:
        tap(adb_bin, c[0], c[1])
        return True
    return False


def input_text(adb_bin, text):
    """Type ASCII text via adb. Non-ASCII (Thai) is NOT supported by `input text`."""
    # device shell quoting: single-quote everything (URLs contain no quotes)
    shell(adb_bin, "input", "text", "'%s'" % text.replace("'", "'\\''"))


def clear_field(adb_bin, chars=200):
    """Move cursor to end and delete `chars` characters (clears an EditText)."""
    shell(adb_bin, "input", "keyevent", "123")  # KEYCODE_MOVE_END
    for _ in range(chars):
        shell(adb_bin, "input", "keyevent", "67")  # KEYCODE_DEL


def scroll_until(adb_bin, text, max_scrolls=6, wait=2):
    """Swipe up until `text` appears in the UI dump, or return None."""
    for _ in range(max_scrolls):
        xml = dump_ui(adb_bin)
        if xml and find_text(xml, text):
            return xml
        shell(adb_bin, "input", "swipe", "540", "1700", "540", "600", "400")
        time.sleep(wait)
    return None


# ---------------------------------------------------------------------------
# navigation
# ---------------------------------------------------------------------------

def launch_shopee(adb_bin):
    shell(adb_bin, "monkey", "-p", "com.shopee.th", "-c",
          "android.intent.category.LAUNCHER", "1")
    time.sleep(5)


def open_convert_link(adb_bin):
    """Navigate: Shopee app -> Me tab -> โปรแกรม Affiliate -> Convert Link.

    Convert Link (แปลงลิงก์) lives on the affiliate Account page, reached via
    the โปรแกรม Affiliate menu on the main Me tab. Restart the app first so no
    stray screen interferes, dismiss any nudge popup (ตั้งรหัสผ่าน), then walk
    the menu. Returns True when the convert screen (แปลงลิงก์ + แปลง) is up.
    """
    def on_convert(xml):
        return bool(xml and find_text(xml, "แปลงลิงก์") and find_text(xml, "แปลง"))

    xml = dump_ui(adb_bin)
    # dismiss a leftover convert-result popup (shows a link + copy button)
    if xml and find_text(xml, "คัดลอกลิงก์") and LINK_RE.search(xml):
        shell(adb_bin, "input", "keyevent", "4")
        time.sleep(2)
        xml = dump_ui(adb_bin)
    if on_convert(xml):
        return True

    # fresh start so no stray screen interferes
    shell(adb_bin, "am", "force-stop", "com.shopee.th")
    time.sleep(2)
    launch_shopee(adb_bin)
    xml = dump_ui(adb_bin)

    # main app home -> Me tab (bottom-right of the 5-tab nav)
    tap(adb_bin, 972, 2330)
    time.sleep(3)
    xml = dump_ui(adb_bin)

    # dismiss the occasional "ตั้งรหัสผ่าน" nudge popup (ไว้ทีหลัง = later)
    c = find_text(xml, "ไว้ทีหลัง") if xml else None
    if c:
        tap(adb_bin, c[0], c[1])
        time.sleep(2)
        xml = dump_ui(adb_bin)

    # Me page -> โปรแกรม Affiliate (may need scrolling; the Me page is long)
    c = find_text(xml, "โปรแกรม Affiliate") if xml else None
    if not c:
        xml = scroll_until(adb_bin, "โปรแกรม Affiliate")
        c = find_text(xml, "โปรแกรม Affiliate") if xml else None
    if not c:
        return False
    tap(adb_bin, c[0], c[1])
    time.sleep(4)
    xml = dump_ui(adb_bin)

    # affiliate home -> "บัญชีผู้ใช้" (Account) bottom tab, then แปลงลิงก์
    c = find_text(xml, "บัญชีผู้ใช้") if xml else None
    if c and not find_text(xml, "แปลงลิงก์"):
        tap(adb_bin, c[0], c[1])
        time.sleep(3)
        xml = dump_ui(adb_bin)

    # Account page -> แปลงลิงก์
    c = find_text(xml, "แปลงลิงก์") if xml else None
    if not c:
        xml = scroll_until(adb_bin, "แปลงลิงก์")
        c = find_text(xml, "แปลงลิงก์") if xml else None
    if not c:
        return False
    tap(adb_bin, c[0], c[1])
    time.sleep(3)
    return on_convert(dump_ui(adb_bin))


# ---------------------------------------------------------------------------
# convert links
# ---------------------------------------------------------------------------

LINK_RE = re.compile(r"https?://[^\s\"']+")

def extract_links(xml):
    """Return unique links found in a UI dump, preferring s.shopee.co.th."""
    links = []
    for m in LINK_RE.finditer(xml):
        url = m.group(0).rstrip(".,;")
        if "shopee" in url:
            links.append(url)
    # de-dup preserving order
    seen = set()
    out = []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    out.sort(key=lambda u: (0 if "s.shopee.co.th" in u else 1))
    return out


CONVERT_TAP_KEYBOARD_OPEN = (540, 1340)  # "แปลง" button position while the IME is up


def convert_links(adb_bin, urls):
    """Convert URLs -> affiliate short links via the phone's Convert Link screen.

    Hard-won recipe (Shopee app, Realme RMX3612, Aug 2026):
    - The convert button only responds to a tap while the on-screen keyboard
      is OPEN, at its keyboard-open position (y ~1340). With the keyboard
      closed the button at the bottom (y ~2276) silently ignores taps.
    - Do NOT dump the UI right before tapping: uiautomator dump takes 1-2s
      and by then the IME may settle/close, shifting the layout and making
      the tap land on the "เพิ่ม Sub id" row instead.
    - Plain `input tap` works; keep the press quick after typing.
    - For batch runs, call this once per URL rather than passing several
      URLs: multiple lines + the ENTER keypress make the tap unreliable.
    """
    for attempt in range(1, 4):
        if not open_convert_link(adb_bin):
            return {"error": "could not reach Convert Link screen"}
        xml = dump_ui(adb_bin)

        # clear the field via the app's "ลบทั้งหมด" (clear all) button if a
        # previous run left links in it (top-right small clickable, no text)
        for m in re.finditer(r'<node[^>]*clickable="true"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml or ""):
            x1, y1, x2, y2 = (int(m.group(i)) for i in range(1, 5))
            if (x2 - x1) < 400 and y1 < 700 and (y2 - y1) < 200:
                tap(adb_bin, (x1 + x2) // 2, (y1 + y2) // 2)
                time.sleep(1.5)
                break

        # focus the big multiline field
        m = re.search(r'<node[^>]*class="android\.widget\.EditText"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml or "")
        if not m:
            return {"error": "Convert Link input field not found"}
        x1, y1, x2, y2 = (int(m.group(i)) for i in range(1, 5))
        tap(adb_bin, (x1 + x2) // 2, (y1 + y2) // 2)
        time.sleep(1.5)

        for i, url in enumerate(urls):
            input_text(adb_bin, url.strip())
            time.sleep(0.5)
            if i < len(urls) - 1:
                shell(adb_bin, "input", "keyevent", "66")  # ENTER -> next line
                time.sleep(0.5)

        # tap แปลง QUICKLY while the keyboard is still open. NEVER dump the
        # UI between typing and tapping: uiautomator dump takes 1-2s during
        # which the IME settles/closes, shifting the layout so the tap misses.
        tap(adb_bin, *CONVERT_TAP_KEYBOARD_OPEN)
        time.sleep(5)  # let the API generate links

        xml = dump_ui(adb_bin)
        if not xml:
            return {"error": "no UI dump after convert"}
        links = extract_links(xml)
        raw = " ".join(n["text"] for n in parse_nodes(xml) if n["text"])
        short = [u for u in links if "s.shopee.co.th" in u]
        if short:
            # dismiss the result popup so the screen is ready for the next run
            shell(adb_bin, "input", "keyevent", "4")
            time.sleep(1)
            return {"links": short, "raw_popup_text": raw}
        # failed (tap missed / wrong screen) — dismiss whatever is open, retry
        shell(adb_bin, "input", "keyevent", "4")
        time.sleep(1.5)
        print(f"[convert] attempt {attempt} missed, retrying...")

    return {"error": "convert failed after 3 attempts", "raw_popup_text": raw}


# ---------------------------------------------------------------------------
# bot backend helpers
# ---------------------------------------------------------------------------

def update_bot(product_id, affiliate_url, name=None, price=None,
               product_url=None, bot_api=DEFAULT_BOT_API):
    payload = {"affiliate_url": affiliate_url}
    if name:
        payload["name"] = name
    if price:
        payload["price"] = price
    if product_url:
        payload["url"] = product_url
    req = urllib.request.Request(
        f"{bot_api}/api/products/{product_id}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_conv = sub.add_parser("convert", help="Convert Shopee URLs to affiliate links via the phone")
    p_conv.add_argument("urls", nargs="+")
    p_conv.add_argument("--bot-api", default=DEFAULT_BOT_API)

    p_search = sub.add_parser("search", help="Open Shopee affiliate search with an ASCII keyword")
    p_search.add_argument("keyword")

    p_upd = sub.add_parser("update-bot", help="PUT an affiliate URL onto a product in the bot backend")
    p_upd.add_argument("product_id", type=int)
    p_upd.add_argument("affiliate_url")
    p_upd.add_argument("--name")
    p_upd.add_argument("--price", type=float)
    p_upd.add_argument("--product-url")
    p_upd.add_argument("--bot-api", default=DEFAULT_BOT_API)

    args = ap.parse_args()

    adb_bin = adb()
    devs = adb_devices(adb_bin)
    if not devs:
        sys.exit("No device attached. Connect the phone and enable USB debugging (adb devices).")

    if args.cmd == "convert":
        res = convert_links(adb_bin, args.urls)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if res.get("links"):
            print("\nConverted links:")
            for u in res["links"]:
                print(" ", u)

    elif args.cmd == "search":
        if not args.keyword.isascii():
            sys.exit("search keyword must be ASCII (adb cannot type Thai). "
                     "Type Thai on the phone keyboard instead.")
        if not open_convert_link(adb_bin):
            sys.exit("could not reach the affiliate search")
        xml = dump_ui(adb_bin)
        # tap the search box on the affiliate home
        c = find_text(xml, "ค้นหาสินค้าหรือร้านค้า")
        if c:
            tap(adb_bin, c[0], c[1])
            time.sleep(2)
            input_text(adb_bin, args.keyword)
            shell(adb_bin, "input", "keyevent", "66")
            print("search submitted on phone")

    elif args.cmd == "update-bot":
        status, body = update_bot(args.product_id, args.affiliate_url,
                                  name=args.name, price=args.price,
                                  product_url=args.product_url,
                                  bot_api=args.bot_api)
        print(f"HTTP {status}")
        print(json.dumps(body, ensure_ascii=False, indent=2) if isinstance(body, dict) else body)


if __name__ == "__main__":
    main()
