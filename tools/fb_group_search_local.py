# -*- coding: utf-8 -*-
"""Local Facebook Group Discovery — หาผู้สมัครกลุ่ม "buyer demand" ให้เรดาร์
========================================================================
ค้นกลุ่ม Facebook ที่สมาชิกโพสต์แนว "อยากได้ / งบ / ขอแนะนำ" ผ่าน session
ที่ล็อกอินอยู่ (fb_cookies.json) ด้วย undetected_chromedriver แล้วเสนอ
รายชื่อกลุ่มผู้สมัครให้เอาไปเพิ่มใน Social Demand Radar.

Read-only monitoring — ใช้ session ที่ได้รับอนุญาต ไม่รับประกัน 100%
ปลอดภัย/ไม่ต้องล็อกอิน (หลักเดียวกับ fb_group_monitor_local.py).

Usage:
  python tools/fb_group_search_local.py --keywords "อยากได้ของ,แนะนำของใช้"
  python tools/fb_group_search_local.py --keywords "หูฟัง" --limit 10 --inspect 3
  python tools/fb_group_search_local.py --inspect 5 --auto-add --api-url https://...
  python tools/fb_group_search_local.py --auto-add --loop --interval 21600
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("fb_group_search")

DEFAULT_SEARCH_URL = "https://www.facebook.com/search/groups/"
DEFAULT_COOKIE_PATH = Path(__file__).resolve().parent.parent / "fb_cookies.json"
DEFAULT_LOOP_INTERVAL = 21600  # 6 ชั่วโมง — ค้นหากลุ่มใหม่เป็นรอบ

# คีย์เวิร์ดเริ่มต้น (ถ้าไม่ส่ง --keywords) — เน้นโพสต์ "อยากได้/แนะนำ" + หมวดสินค้าร้านป้าเข็ม
DEFAULT_KEYWORDS = (
    "อยากได้ของ", "แนะนำของใช้", "หูฟังแนะนำ", "เครื่องนวด",
    "ของใช้แม่และเด็ก", "อุปกรณ์สัตว์เลี้ยง", "อาร์ตทอย", "สมาร์ทโฮม",
)

# คำที่บ่งบอกว่าโพสต์เป็น "คนอยากซื้อ" (demand) ไม่ใช่ "แม่ค้าขายของ"
BUYER_SIGNALS = (
    "อยากได้", "งบ", "แนะนำ", "หา", "ขอพิกัด", "ราคาไม่เกิน", "ช่วยเลือก",
    "ตัวไหนดี", "บอกต่อ", "ขอคำแนะนำ", "ราคาเท่าไหร่", "ซื้อที่ไหน",
)

# คำที่บ่งบอกว่าเป็นโพสต์ขายของ/โฆษณา (ใช้หักล้างคะแนน buyer)
SELLER_SIGNALS = (
    "ขาย", "รับสั่ง", "สนใจทัก", "ทักแชท", "ฝากร้าน", "พร้อมส่ง", "จัดส่ง",
)


# ===========================================================================
# Pure helpers (testable, no browser)
# ===========================================================================
def normalize_group_url(href: str) -> Optional[Dict[str, str]]:
    """แยก group_id + url สะอาดจาก href ของลิงก์ Facebook group.

    คืน dict {"group_id": ..., "url": ...} หรือ None ถ้าไม่ใช่ลิงก์กลุ่ม.
    """
    if not href:
        return None
    href = href.strip()
    if "/groups/" not in href:
        return None
    parsed = urlparse(href)
    segments = [s for s in parsed.path.split("/") if s]
    try:
        idx = segments.index("groups")
    except ValueError:
        return None
    if idx + 1 >= len(segments):
        return None
    # มี segment ต่อท้าย (เช่น /posts/xxx, /permalink/xxx) = ลิงก์ย่อย ไม่ใช่ลิงก์กลุ่มหลัก
    if idx + 2 < len(segments):
        return None
    group_id = segments[idx + 1]
    # กัน segment พิเศษที่อาจโผล่เป็นชื่อ (กันพลาด)
    if group_id.lower() in ("permalink", "posts", "members", "about", "photos", "videos", "media"):
        return None
    return {"group_id": group_id, "url": f"https://www.facebook.com/groups/{group_id}/"}


_THAI_UNITS = {
    "พัน": 1_000,
    "หมื่น": 10_000,
    "แสน": 100_000,
    "ล้าน": 1_000_000,
}


def _parse_member_count(joined: str) -> Optional[int]:
    """อ่านจำนวนสมาชิกจากข้อความการ์ด เช่น '12K members' / 'สมาชิก 5.2 หมื่น คน'."""
    # English: "12K members" / "3,400 members"
    m = re.search(r"([\d.,]+)\s*([kKmM]?)\s*(?:members|สมาชิก|คน)", joined)
    if m:
        try:
            num = float(m.group(1).replace(",", ""))
            suffix = m.group(2).lower()
            mult = 1_000 if suffix == "k" else (1_000_000 if suffix == "m" else 1)
            return int(num * mult)
        except ValueError:
            pass
    # Thai units: "5.2 หมื่น", "1.5 ล้าน"
    m = re.search(r"([\d.,]+)\s*(พัน|หมื่น|แสน|ล้าน)", joined)
    if m:
        try:
            num = float(m.group(1).replace(",", ""))
            return int(num * _THAI_UNITS[m.group(2)])
        except ValueError:
            pass
    return None


def parse_group_card(text: str) -> Dict[str, Any]:
    """ดึงชื่อ / จำนวนสมาชิก / ความเป็นสาธารณะจากข้อความของการ์ดกลุ่ม."""
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    info: Dict[str, Any] = {"name": "", "members": None, "public": None, "raw": lines}
    if not lines:
        return info
    info["name"] = lines[0]
    joined = " ".join(lines).lower()
    if "ส่วนตัว" in joined or "private" in joined:
        info["public"] = False
    elif "สาธารณะ" in joined or "public" in joined:
        info["public"] = True
    info["members"] = _parse_member_count(joined)
    return info


def count_buyer_signals(text: str) -> int:
    """นับจำนวนสัญญาณ buyer demand ในข้อความ."""
    t = (text or "").lower()
    return sum(1 for w in BUYER_SIGNALS if w.lower() in t)


def count_seller_signals(text: str) -> int:
    """นับจำนวนสัญญาณ seller/โฆษณาในข้อความ."""
    t = (text or "").lower()
    return sum(1 for w in SELLER_SIGNALS if w.lower() in t)


def rank_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """เรียงผู้สมัคร: buyer signals มากก่อน → สาธารณะก่อน → สมาชิกมากก่อน."""
    def key(c: Dict[str, Any]):
        public_rank = 0 if c.get("public") is True else 1
        return (-(c.get("buyer_signals", 0)), public_rank, -(c.get("members") or 0))
    return sorted(candidates, key=key)


def should_auto_add(candidate: Dict[str, Any], min_buyer: int = 1) -> bool:
    """ตัดสินว่าควรเพิ่มกลุ่มอัตโนมัติหรือไม่.

    เงื่อนไข: ยังไม่ถูกเพิ่ม + สแกนได้ (scannable) + ไม่ใช่ private
    + มี buyer signals ถึงเกณฑ์ + ไม่ใช่กลุ่มขายของล้วน (buyer >= seller).
    """
    if candidate.get("already_added"):
        return False
    if not candidate.get("scannable"):
        return False
    if candidate.get("public") is False:
        return False
    buyer = candidate.get("buyer_signals", 0)
    seller = candidate.get("seller_signals", 0)
    return buyer >= max(1, min_buyer) and buyer >= seller


# ===========================================================================
# Token resolution (เหมือน monitor — อ่านจาก CLI > env > backend/.env)
# ===========================================================================
def load_env_token(cli_token: Optional[str] = None, env_path: Optional[str] = None) -> str:
    """อ่าน admin token (CRON_TOKEN / ADMIN_DASHBOARD_PASSWORD)."""
    if cli_token and cli_token.strip():
        return cli_token.strip()
    env_val = os.getenv("CRON_TOKEN") or os.getenv("ADMIN_DASHBOARD_PASSWORD")
    if env_val and env_val.strip():
        return env_val.strip()
    target = Path(env_path) if env_path else Path(__file__).resolve().parent.parent / "backend" / ".env"
    if target.exists():
        try:
            for line in target.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("CRON_TOKEN=") or line.startswith("ADMIN_DASHBOARD_PASSWORD="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        except Exception as e:
            logger.debug(f"Failed to read .env at {target}: {e}")
    return ""


def add_group_to_radar(api_url: str, token: str, candidate: Dict[str, Any]) -> tuple:
    """POST กลุ่มเข้า backend radar (POST /api/admin/facebook-radar/groups).

    คืน (ok: bool, result: dict).
    """
    import urllib.error
    import urllib.request
    clean = api_url.rstrip("/")
    endpoint = f"{clean}/api/admin/facebook-radar/groups"
    payload = {
        "group_id": candidate["group_id"],
        "group_name": (candidate["name"] or candidate["group_id"])[:255],
        "group_url": candidate["url"],
        "is_active": True,
    }
    req = urllib.request.Request(
        f"{endpoint}?token={token}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "PKH-FacebookGroupSearch/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return False, {"error": f"HTTP {e.code}", "detail": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:
        return False, {"error": type(e).__name__, "detail": str(e)[:200]}


def log_group_to_sheet(sheet_url: str, candidate: Dict[str, Any]) -> tuple:
    """POST กลุ่มผู้สมัครไปยัง Google Sheet webhook (kind='group_candidate').

    คืน (ok: bool, detail: str).
    """
    import urllib.request
    payload = {
        "kind": "group_candidate",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "group_name": candidate.get("name") or candidate.get("group_id"),
        "group_url": candidate.get("url"),
        "want": candidate.get("keyword") or "",
        "buyer_signals": candidate.get("buyer_signals", 0),
        "seller_signals": candidate.get("seller_signals", 0),
        "scannable": bool(candidate.get("scannable")),
        "sample_post": (candidate.get("sample_posts") or [""])[0],
    }
    req = urllib.request.Request(
        sheet_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "PKH-FacebookGroupSearch/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, r.read().decode("utf-8", "replace")[:200]
    except Exception as e:
        return False, str(e)[:200]


def fetch_existing_group_ids(api_url: str, token: str) -> set:
    """ดึง group_id ที่มีอยู่แล้วจาก backend (สำหรับ dedup)."""
    import urllib.request
    clean = api_url.rstrip("/")
    endpoint = f"{clean}/api/admin/facebook-radar/groups"
    headers = {"User-Agent": "PKH-FacebookGroupSearch/1.0"}
    if token:
        headers["X-Admin-Token"] = token
    request_url = f"{endpoint}?token={token}" if token else endpoint
    req = urllib.request.Request(request_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else []
        return {g.get("group_id") for g in data if isinstance(g, dict) and g.get("group_id")}
    except Exception as e:
        print(f"   ↳ ⚠️ Failed to fetch existing groups (dedup off): {e}")
        return set()


# ===========================================================================
# Browser helpers (stealth Chrome + cookies)
# ===========================================================================
def _launch_driver():
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")
    driver = uc.Chrome(options=options, version_main=151)
    driver.set_script_timeout(10)
    driver.set_page_load_timeout(15)
    return driver


def inject_cookies(driver, cookie_path: Optional[Path] = None) -> bool:
    """โหลด fb_cookies.json ฉีดเข้า browser session."""
    cookie_path = cookie_path or DEFAULT_COOKIE_PATH
    if not os.path.exists(str(cookie_path)):
        print(f"   ↳ ⚠️ Cookie file not found: {cookie_path}")
        return False
    print("   ↳ 🌐 Accessing Facebook domain to inject session cookies...")
    try:
        driver.get("https://www.facebook.com/")
    except Exception:
        pass
    time.sleep(2)
    try:
        with open(str(cookie_path), "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for cookie in cookies:
            driver.add_cookie({
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie.get("domain", ".facebook.com"),
                "path": cookie.get("path", "/"),
            })
        print("   ↳ 🍪 Injected Facebook session cookies successfully.")
    except Exception as e:
        print(f"   ↳ ⚠️ Cookie Injection Error: {e}")
    try:
        driver.refresh()
    except Exception:
        pass
    time.sleep(3)
    return True


# ===========================================================================
# Search & inspect
# ===========================================================================
def _climb_for_card_text(anchor, max_levels: int = 5) -> str:
    """ไต่ขึ้นจาก anchor เพื่อหาข้อความการ์ดกลุ่ม (ชื่อ/สมาชิก/สาธารณะ)."""
    # ชอบ container ที่เป็น role="article" ก่อน (การ์ดจริง)
    try:
        card = anchor.find_element(By.XPATH, "./ancestor::*[@role='article'][1]")
        t = (card.text or "").strip()
        if t:
            return t
    except Exception:
        pass
    best = ""
    el = anchor
    for _ in range(max_levels):
        try:
            el = el.find_element(By.XPATH, "..")
        except Exception:
            break
        t = (el.text or "").strip()
        if len(t) > len(best):
            best = t
    return best


def search_groups(driver, keyword: str, limit: int = 15) -> List[Dict[str, Any]]:
    """ค้นกลุ่มตามคีย์เวิร์ด แล้วดึงผู้สมัคร (name/url/members/public)."""
    from selenium.webdriver.common.by import By
    url = f"{DEFAULT_SEARCH_URL}?q={quote(keyword)}"
    print(f"   ↳ 🔍 Searching: {url}")
    driver.get(url)
    time.sleep(5)
    for _ in range(3):
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(1.5)

    anchors = driver.find_elements(By.XPATH, '//a[contains(@href, "/groups/")]')
    print(f"   ↳ 📋 Found {len(anchors)} group links on page")

    # กลุ่มการ์ดเดียวมีหลายลิงก์ (รูป/ชื่อ) → รวมเป็น 1 ต่อ URL แล้วเลือก anchor ที่มีข้อความ
    groups_by_url: Dict[str, Dict[str, Any]] = {}
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            norm = normalize_group_url(href)
            if not norm:
                continue
            entry = groups_by_url.setdefault(
                norm["url"],
                {"norm": norm, "name": "", "card_text": ""},
            )
            text = (a.text or "").strip()
            if text and not entry["name"]:
                entry["name"] = text
            card_text = _climb_for_card_text(a)
            if len(card_text) > len(entry["card_text"]):
                entry["card_text"] = card_text
        except Exception:
            continue

    results: List[Dict[str, Any]] = []
    for entry in groups_by_url.values():
        norm = entry["norm"]
        info = parse_group_card(entry["card_text"] or entry["name"])
        name = entry["name"] or info["name"]
        if not name and entry["card_text"]:
            name = entry["card_text"].split("\n")[0].strip()
        results.append({
            "keyword": keyword,
            "group_id": norm["group_id"],
            "url": norm["url"],
            "name": name,
            "members": info["members"],
            "public": info["public"],
            "buyer_signals": 0,
            "seller_signals": 0,
            "sample_posts": [],
            "already_added": False,
        })
        if len(results) >= limit:
            break
    return results


def inspect_group_posts(driver, candidate: Dict[str, Any], limit: int = 5) -> Dict[str, Any]:
    """เข้าไปอ่านโพสต์ล่าสุดของกลุ่ม แล้วนับ buyer/seller signals."""
    from selenium.webdriver.common.by import By
    try:
        driver.get(candidate["url"])
        time.sleep(4)
        for _ in range(2):
            driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(1.5)
        articles = driver.find_elements(By.XPATH, '//div[@role="article"]')
        texts = []
        for el in articles[:limit]:
            t = (el.text or "").strip()
            if t:
                texts.append(t)
        candidate["buyer_signals"] = sum(count_buyer_signals(t) for t in texts)
        candidate["seller_signals"] = sum(count_seller_signals(t) for t in texts)
        candidate["sample_posts"] = [t[:80] for t in texts[:3]]
        # อ่านโพสต์เจอ = เป็นกลุ่มที่สแกนได้ (สาธารณะ/เข้าได้) — ถ้า private จะเจอหน้า join ว่าง ๆ
        candidate["scannable"] = len(texts) > 0
        if candidate["scannable"] and candidate.get("public") is None:
            candidate["public"] = True
    except Exception as e:
        logger.warning(f"Inspect failed for {candidate.get('url')}: {e}")
    return candidate


def _print_results(ranked: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 70)
    print(f"📋 Candidate buyer-demand groups ({len(ranked)}):")
    print("=" * 70)
    for i, c in enumerate(ranked, 1):
        flag = "PUBLIC " if c.get("public") is True else ("PRIVATE" if c.get("public") is False else "UNKNOWN")
        scannable = "" if c.get("scannable") is None else (" ✓scan" if c.get("scannable") else " ✗noscan")
        members = f"{c.get('members'):,}" if c.get("members") else "?"
        already = " [ALREADY ADDED]" if c.get("already_added") else ""
        print(f"{i:2}. [{flag}]{scannable} {c['name'][:45]:45} | members={members:>8} | buyer={c['buyer_signals']} seller={c['seller_signals']}{already}")
        print(f"    {c['url']}")
        for p in c.get("sample_posts", []):
            print(f"      · {p}")
    print("=" * 70)


# ===========================================================================
# CLI
# ===========================================================================
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ค้นกลุ่ม Facebook ที่เป็น buyer demand (อยากได้/งบ/แนะนำ) ผ่าน session ที่ล็อกอินอยู่",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python tools/fb_group_search_local.py --keywords "อยากได้ของ,แนะนำของใช้"
  python tools/fb_group_search_local.py --keywords "หูฟัง" --limit 10 --inspect 3
  python tools/fb_group_search_local.py --inspect 5 --auto-add --api-url https://...
  python tools/fb_group_search_local.py --auto-add --loop --interval 21600
        """,
    )
    parser.add_argument(
        "--keywords", "-k",
        type=str,
        default=None,
        help="คีย์เวิร์ดค้นหา คั่นด้วยจุลภาค (default: ใช้คีย์เวิร์ด buyer-demand มาตรฐาน)",
    )
    parser.add_argument(
        "--auto-add",
        action="store_true",
        help="เพิ่มกลุ่มที่ผ่านเกณฑ์ (public+scannable+buyer) เข้า radar อัตโนมัติผ่าน API",
    )
    parser.add_argument(
        "--min-buyer",
        type=int,
        default=1,
        help="จำนวน buyer signals ขั้นต่ำที่จะ auto-add (default 1)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="รันวนซ้ำเป็นรอบ (ใช้กับ --auto-add) เพื่อค้นหากลุ่มใหม่เรื่อย ๆ",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_LOOP_INTERVAL,
        help=f"วินาทีระหว่างรอบเมื่อใช้ --loop (default {DEFAULT_LOOP_INTERVAL} = 6 ชม.)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="จำนวนผลลัพธ์สูงสุดต่อคีย์เวิร์ด (default 15)",
    )
    parser.add_argument(
        "--inspect",
        type=int,
        default=0,
        metavar="N",
        help="เข้าไปอ่านโพสต์ล่าสุดของ N กลุ่มแรก เพื่อนับ buyer signals (default 0 = ไม่เข้า)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="ถ้าใส่ จะดึงกลุ่มที่มีอยู่แล้วจาก backend มาข้าม (dedup)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Admin token (อ่านจาก CRON_TOKEN / backend/.env ถ้าไม่ใส่)",
    )
    parser.add_argument(
        "--sheet-url",
        type=str,
        default=None,
        help="Google Sheet webhook URL บันทึกกลุ่มผู้สมัคร (default: อ่าน POSTS_SHEET_WEBHOOK_URL จาก env)",
    )
    parser.add_argument(
        "--out", "-o",
        type=str,
        default=None,
        help="บันทึกผลเป็น JSON file",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="เปิด debug logging",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else list(DEFAULT_KEYWORDS)
    if not keywords:
        print("❌ No keywords provided.", file=sys.stderr)
        return 1

    print("=" * 70)
    print("🔎 FACEBOOK GROUP DISCOVERY (buyer-demand candidates)")
    print("=" * 70)
    print(f"🏷️  Keywords   : {', '.join(keywords)}")
    print(f"🔎 Inspect     : {args.inspect} top groups")
    print(f"➕ Auto-add    : {'ON' if args.auto_add else 'off'} (min buyer {args.min_buyer})")
    print("=" * 70)

    token = load_env_token(args.token)
    if args.auto_add and not args.api_url:
        print("⚠️  --auto-add ต้องใช้คู่กับ --api-url (ปลายทางที่จะเพิ่มกลุ่ม)", file=sys.stderr)
        return 1

    driver = _launch_driver()
    try:
        inject_cookies(driver)
        while True:
            existing: set = set()
            if args.api_url:
                existing = fetch_existing_group_ids(args.api_url, token)

            collected: List[Dict[str, Any]] = []
            inspected_urls: set = set()
            for kw in keywords:
                print(f"\n🔍 Searching groups for '{kw}' ...")
                kw_results = search_groups(driver, kw, limit=args.limit)
                for c in kw_results:
                    c["already_added"] = c["group_id"] in existing
                # inspect แบบ per-keyword — เฉพาะกลุ่มใหม่ที่ยังไม่เคยดูในรอบนี้
                to_inspect = [c for c in kw_results
                              if not c["already_added"] and c["url"] not in inspected_urls][: args.inspect]
                if args.inspect and to_inspect:
                    print(f"   🔎 Inspecting {len(to_inspect)} new groups for '{kw}' ...")
                    for c in to_inspect:
                        inspect_group_posts(driver, c, limit=5)
                        inspected_urls.add(c["url"])
                        print(f"      - {c['name'][:40]}: buyer={c['buyer_signals']} seller={c['seller_signals']} scannable={c.get('scannable')}")
                collected.extend(kw_results)

            # dedup across keywords (by url) — เก็บตัวที่ถูก inspect แล้ว (buyer>0) ไว้ก่อน
            deduped: Dict[str, Dict[str, Any]] = {}
            for c in collected:
                prev = deduped.get(c["url"])
                if prev is None or c.get("buyer_signals", 0) > prev.get("buyer_signals", 0):
                    deduped[c["url"]] = c
            candidates = list(deduped.values())
            print(f"\n📦 Unique candidates: {len(candidates)}")

            ranked = rank_candidates(candidates)
            _print_results(ranked)

            sheet_url = args.sheet_url or os.getenv("POSTS_SHEET_WEBHOOK_URL") or ""
            if sheet_url:
                print(f"\n📤 Logging {len(ranked)} candidates to Google Sheet ...")
                ok_n = fail_n = 0
                for c in ranked:
                    ok, detail = log_group_to_sheet(sheet_url, c)
                    if ok:
                        ok_n += 1
                    else:
                        fail_n += 1
                        print(f"   ⚠️ sheet log fail: {(c.get('name') or '')[:30]} — {detail}")
                print(f"📤 Sheet: {ok_n} ok, {fail_n} fail")

            if args.auto_add:
                added, failed = [], []
                for c in ranked:
                    if not should_auto_add(c, min_buyer=args.min_buyer):
                        continue
                    ok, res = add_group_to_radar(args.api_url, token, c)
                    if ok:
                        added.append(c)
                        c["already_added"] = True
                        print(f"   ➕ ADDED: {c['name'][:40]} ({c['group_id']})")
                    else:
                        failed.append((c, res))
                        print(f"   ❌ FAILED: {c['name'][:40]} — {res}")
                print(f"\n✅ Auto-add: {len(added)} เพิ่มสำเร็จ, {len(failed)} ล้ม")

            if args.out:
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(ranked, f, ensure_ascii=False, indent=2)
                print(f"💾 Saved {len(ranked)} candidates to {args.out}")

            if not args.loop:
                break
            print(f"\n💤 Sleeping for {args.interval} seconds... (Ctrl+C to stop)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user (KeyboardInterrupt).")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
