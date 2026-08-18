# -*- coding: utf-8 -*-
"""
บอทแชร์โพสต์เพจลงกลุ่ม Facebook (ปุ่มแชร์) — แยกส่วน: รับ post_url → แชร์ → บันทึกชีท
ไม่โพสต์เพจเอง (ใช้คู่กับ bot/post_page.py โดยเอา URL มาป้อน)

Flow: เปิดโพสต์ → กด "แชร์" → "แชร์ไปยังกลุ่ม" → เลือกกลุ่ม → "โพสต์" → บันทึกชีท

ใช้งาน:
  python bot/share_group.py --post-url "https://www.facebook.com/.../posts/..." --group-name "กลุ่มA"
  python bot/share_group.py --post-url "https://..." --group-name "กลุ่มA,กลุ่มB,กลุ่มC"
  python bot/share_group.py --post-url "$(cat post_url.txt)" --group-name "กลุ่มA"
  python bot/share_group.py --post-url "..." --group-name "..." --dry-run
  python bot/share_group.py --post-url "..." --group-url "https://www.facebook.com/groups/123/..." --dry-run

หมายเหตุ:
  - ใช้ Selenium + คุกกี้ (fb_cookies.json) เปิด Facebook จริง ต้องรันบนเครื่องบ้าน/IP จริง
  - ต้องตั้ง env POSTS_SHEET_WEBHOOK_URL (URL ของ Apps Script tools/sheet_posts_apps_script.gs)
    ไม่งั้นข้ามบันทึกชีท
"""
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    """โหลด backend/.env เข้า os.environ — ไม่ทับค่าที่ตั้งไว้แล้ว"""
    env_path = ROOT / "backend" / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _launch_driver():
    """เปิดเบราว์เซอร์ด้วย undetected_chromedriver (version_main=151 ตรง Chrome เครื่อง)"""
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")
    options.add_argument("--start-maximized")
    driver = uc.Chrome(options=options, version_main=151)
    driver.set_script_timeout(10)
    driver.set_page_load_timeout(20)
    return driver


def inject_cookies(driver, cookie_path: Path) -> bool:
    """โหลด fb_cookies.json ฉีดเข้า browser session"""
    if not cookie_path.exists():
        print(f"[ERROR] ไม่พบไฟล์คุกกี้ล็อกอิน: {cookie_path}")
        return False
    print("[INFO] เปิดหน้า Facebook เพื่อฉีดเซสชันคุกกี้...")
    try:
        driver.get("https://www.facebook.com/")
    except Exception as e:
        print(f"[WARNING] โหลดหน้าแรก: {e}")
    time.sleep(3)
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
        print("[SUCCESS] ฉีดเซสชันล็อกอิน Facebook เรียบร้อย")
        driver.refresh()
        time.sleep(4)
        return True
    except Exception as e:
        print(f"[ERROR] โหลดคุกกี้ผิดพลาด: {e}")
        return False


# ---------------------------------------------------------------------------
# Google ชีท (ที่เก็บผลลัพธ์เดียวของบอทนี้)
# ---------------------------------------------------------------------------
def _log_to_sheet(row: Dict[str, Any]) -> bool:
    url = os.getenv("POSTS_SHEET_WEBHOOK_URL", "").strip()
    if not url:
        print("[SHEET] POSTS_SHEET_WEBHOOK_URL ไม่ได้ตั้ง → ข้ามบันทึกชีท")
        return False
    try:
        r = requests.post(url, json=row, timeout=10, allow_redirects=True)
        print(f"[SHEET] บันทึกลงชีท ok (HTTP {r.status_code})")
        return r.status_code in (200, 302)
    except Exception as e:
        print(f"[SHEET] บันทึกลงชีทล้ม: {e}")
        return False


def _line_oa_url() -> str:
    return os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")


# แคปชั่นแชร์แบบ spintax — คู่ hook+benefit (5 คู่) × CTA (3 แบบ) = 15 แบบไม่ซ้ำ
_SHARE_CAPTION_PAIRS = [
    (
        "อยากใช้บอทช่วยขายของ Shopee (บอทป้าเข็ม) ป้าจัดการระบบให้พร้อมใช้ทันทีจ้า 😊",
        "🛠️ ปลอดภัยรันบนบัญชี/คีย์คุณเอง แอดมินดูแลหลังบ้านให้หมด ไม่ต้องเซ็ตค่าเองให้ปวดหัวจ้า",
    ),
    (
        "อยากมีบอทอัจฉริยะในแบรนด์ตัวเองไหมจ๊ะ? 🤖",
        "บอทป้าเข็มตัวนี้สามารถเปลี่ยนชื่อบอท เปลี่ยนสโลแกน และตั้งเป็นชื่อร้านของคุณเองได้ทันทีเลยนะจ๊ะ!",
    ),
    (
        "แม่ค้าออนไลน์ตอบแชทไม่ทันบ้างไหมจ๊ะ? 😅",
        "ป้าเข็มมีบอทช่วยตอบลูกค้าอัตโนมัติ + ช่วยหาคนอยากซื้อให้ถึงเพจ ตอบไวไม่ตกหล่น",
    ),
    (
        "ขายของออนไลน์อยากมีตัวช่วยสักคนไหมจ๊ะ? 🛒",
        "บอทป้าเข็มดูแลหลังบ้านให้หมด ทั้งตอบแชท หาคนซื้อ และตั้งชื่อแบรนด์ตัวเองได้",
    ),
    (
        "อยากให้ร้านมีบอทตอบลูกค้าเองอัตโนมัติ ไม่ต้องจ้างพนักงานไหมจ๊ะ? 💼",
        "ป้าเข็มเซ็ตระบบให้พร้อมใช้ รันบนบัญชี/คีย์คุณเอง ปลอดภัย ไม่ต้องนั่งเซ็ตเอง",
    ),
]

_SHARE_CAPTION_CTAS = [
    "💼 เริ่มต้น 490.- แอดไลน์คุยรายละเอียดแพ็กเกจกับป้าเลยจ้า 👉 @@LINE@@",
    "💬 ทักไลน์คุยรายละเอียดกับป้าเข็มได้เลยจ้า 👉 @@LINE@@",
    "เริ่มต้นเบา ๆ คุยกันก่อนได้ ทักไลน์หาป้าเข็มเลยจ้า 👉 @@LINE@@",
]


def _share_caption_variants() -> List[str]:
    """แคปชั่นแชร์หลายแบบ (spintax: hook/benefit × CTA สลับกัน) — หมุนเวียนกันแต่ละกลุ่ม
    ข้อความไม่ซ้ำกันทุกกลุ่ม กัน Facebook จับว่าเป็นสแปม."""
    line = _line_oa_url()
    variants = []
    for hook, benefit in _SHARE_CAPTION_PAIRS:
        for cta in _SHARE_CAPTION_CTAS:
            variants.append(f"{hook}\n{benefit}\n{cta}".replace("@@LINE@@", line))
    return variants


def _default_caption() -> str:
    """แคปชั่นแชร์แบบแรก (โปรโมทบอทป้าเข็ม — ไม่มีลิงก์สินค้า) — ใช้เมื่อต้องการข้อความเดียว."""
    return _share_caption_variants()[0]


def _sheet_row(post_url: str, group_name: str, caption: str, ok: bool) -> Dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": "group_local",
        "title": f"เพจป้าเข็ม → {group_name}",
        "message": f"[{'OK' if ok else 'FAIL'}] {caption}",
        "link": "",
        "post_id": post_url,
        "post_url": post_url,
    }


# ---------------------------------------------------------------------------
# ปุ่มแชร์ (Share)
# ---------------------------------------------------------------------------
def _type_like_human(element, text: str):
    clean = "".join(c for c in text if ord(c) <= 0xFFFF)
    try:
        element.click()
        time.sleep(1)
    except Exception:
        pass
    for ch in clean:
        element.send_keys(ch)
        time.sleep(random.uniform(0.03, 0.10))


def _click(driver, element):
    """กด element — ไม่ throw (FB re-render ทำให้ element stale ระหว่างหา/กด → ลอง JS แล้วยอมแพ้เงียบ ๆ)"""
    try:
        element.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


def _find_first(driver, locators):
    for by, selector in locators:
        try:
            return WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((by, selector))
            )
        except Exception:
            continue
    return None


def _share_dialog_closed(driver, timeout: int = 10) -> bool:
    """True = dialog แชร์ปิดแล้ว (สัญญาณว่า Facebook รับโพสต์ไปแล้ว)."""
    try:
        WebDriverWait(driver, timeout).until_not(
            EC.presence_of_element_located((By.XPATH, '//div[@role="dialog"]'))
        )
        return True
    except Exception:
        return False


def share_post_to_group(driver, post_url: str, group_name: str,
                        message: Optional[str] = None,
                        dry_run: bool = False) -> Tuple[bool, str]:
    """เปิดโพสต์ → ปุ่มแชร์ → แชร์ไปยังกลุ่ม → เลือกกลุ่ม → แคปชั่น → โพสต์"""
    print(f"[INFO] เปิดโพสต์ต้นทาง: {post_url}")
    try:
        driver.get(post_url)
    except Exception as e:
        print(f"[WARNING] โหลดโพสต์: {e}")
    time.sleep(5)

    # ปิด dialog ที่อาจค้างจากกลุ่มก่อนหน้า (กัน state สับสนระหว่างกลุ่ม)
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(1)
    except Exception:
        pass

    # 1. กดปุ่ม "แชร์" (Share) — Facebook 2026 เปลี่ยน aria-label เป็น
    #    "ส่งลิงก์นี้ให้เพื่อนหรือโพสต์ลงในโปรไฟล์ของคุณ" (EN: Send this ... post on your profile)
    share_btn = _find_first(driver, [
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "ส่งลิงก์") or contains(@aria-label, "โพสต์ลงในโปรไฟล์ของคุณ")]'),
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "Send this") or contains(@aria-label, "post on your profile") or contains(@aria-label, "post on your timeline")]'),
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "แชร์") or contains(@aria-label, "Share")]'),
        (By.XPATH, '//div[@aria-label="แชร์โพสต์นี้"] | //div[@aria-label="Share this"]'),
    ])
    if not share_btn:
        return False, "ไม่พบปุ่มแชร์"
    _click(driver, share_btn)
    time.sleep(2)

    # 2+3. เปิด panel แชร์ → กด "กลุ่ม" → รอช่องค้นหากลุ่ม
    #    FB 2026 UI ไม่เสถียร (เจอจริง 18/08): กด "กลุ่ม" แล้ว panel ไม่เปิดบางรอบ /
    #    บางรอบกดแชร์แล้วได้ panel variant ที่ไม่มีตัวเลือก "กลุ่ม" → วนสูงสุด 4 รอบ:
    #    หา search box → กด "กลุ่ม" → ถ้าไม่มีทั้งคู่ ปิด dialog แล้วกดปุ่มแชร์ใหม่
    search_locators = [
        (By.XPATH, '//input[contains(@placeholder, "ค้นหากลุ่ม")] | //input[contains(@aria-label, "ค้นหากลุ่ม")]'),
        (By.XPATH, '//input[contains(@placeholder, "Search for groups")] | //input[contains(@aria-label, "Search for groups")]'),
        (By.XPATH, '//div[@role="dialog"]//input[@role="combobox"][contains(@placeholder, "ค้นหา") or contains(@placeholder, "Search")]'),
        (By.XPATH, '//div[@role="dialog"]//input[contains(@placeholder, "ค้นหา") or contains(@placeholder, "Search")]'),
    ]
    group_locators = [
        # FB 2026: ปุ่มจริงคือ div[role=button] aria-label="แชร์ไปยังกลุ่ม" (ไม่ใช่ span ข้อความ "กลุ่ม")
        (By.XPATH, '//div[@role="dialog"]//div[@role="button"][contains(@aria-label, "แชร์ไปยังกลุ่ม") or contains(@aria-label, "Share to a group")]'),
        (By.XPATH, '//div[@role="dialog"]//*[contains(@aria-label, "แชร์ไปยังกลุ่ม") or contains(@aria-label, "Share to a group")]'),
        (By.XPATH, '//div[@role="dialog"]//span[normalize-space(text())="กลุ่ม"]'),
        (By.XPATH, '//div[@role="dialog"]//*[normalize-space(.)="กลุ่ม"]'),
        (By.XPATH, '//div[@role="dialog"]//*[normalize-space(text())="Groups"]'),
        (By.XPATH, '//*[normalize-space(text())="แชร์ไปยังกลุ่ม" or normalize-space(text())="แชร์ในกลุ่ม"]'),
        (By.XPATH, '//*[contains(text(), "Share to a group") or contains(text(), "Share in a group")]'),
    ]
    search = None
    last_err = "ไม่พบช่องค้นหากลุ่ม"
    for _attempt in range(4):
        # หา search box ก่อน (บาง variant เปิดมาให้เลย) — ตรวจสั้น ๆ 3 วิ/ตัว
        for by, sel in search_locators:
            try:
                search = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((by, sel)))
                break
            except Exception:
                continue
        if search:
            break
        # ยังไม่มี → หา "กลุ่ม" ใหม่ทุกรอบ (panel re-render ทำให้ element เก่า stale) แล้วกด
        group_opt = _find_first(driver, group_locators)
        if group_opt:
            _click(driver, group_opt)
            time.sleep(3)
            continue
        # ไม่มี "กลุ่ม" = panel เปิด variant ผิด/ไม่เปิด → ปิด dialog แล้วกดแชร์ใหม่
        last_err = "ไม่พบตัวเลือก 'กลุ่ม' (แชร์ไปยังกลุ่ม)"
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(1)
        share_btn = _find_first(driver, [
            (By.XPATH, '//div[@role="button"][contains(@aria-label, "ส่งลิงก์") or contains(@aria-label, "โพสต์ลงในโปรไฟล์ของคุณ")]'),
            (By.XPATH, '//div[@role="button"][contains(@aria-label, "Send this") or contains(@aria-label, "post on your profile") or contains(@aria-label, "post on your timeline")]'),
            (By.XPATH, '//div[@role="button"][contains(@aria-label, "แชร์") or contains(@aria-label, "Share")]'),
            (By.XPATH, '//div[@aria-label="แชร์โพสต์นี้"] | //div[@aria-label="Share this"]'),
        ])
        if not share_btn:
            return False, last_err
        _click(driver, share_btn)
        time.sleep(3)
    if not search:
        return False, "ไม่พบช่องค้นหากลุ่ม"

    # 4. เลือกกลุ่ม — FB 2026 หลังกด "แชร์ไปยังกลุ่ม" จะโชว์รายการกลุ่มที่เราเป็นสมาชิกแล้วทันที
    #    (text = "ชื่อกลุ่ม\nกลุ่มสาธารณะ") → กดตรง ๆ ได้เลย ไม่ต้องพิมพ์ค้นหา (เร็ว + ทนกว่า)
    caption_locators = [
        (By.XPATH, '//div[@role="dialog"]//div[@role="textbox" or @contenteditable="true"]'),
        (By.XPATH, '//div[@aria-label="เขียนข้อความ" or @aria-label="เขียนอะไรบางอย่าง"]'),
    ]
    # ปุ่มยืนยัน — ใช้ normalize-space(.) รองรับปุ่มที่มี span ซ้อน
    post_btn_locators = [
        (By.XPATH, '//div[@role="dialog"]//div[@role="button"][normalize-space(.)="โพสต์" or normalize-space(.)="Post"]'),
        (By.XPATH, '//*[@role="button"][normalize-space(.)="โพสต์" or normalize-space(.)="Post"]'),
        (By.XPATH, '//div[@role="dialog"]//div[@role="button"][normalize-space(.)="แชร์" or normalize-space(.)="Share"]'),
        (By.XPATH, '//*[@role="button"][normalize-space(.)="แชร์" or normalize-space(.)="Share"]'),
    ]

    def _find_group_item():
        return _find_first(driver, [
            (By.XPATH, f'//div[@role="dialog"]//div[@role="button"][contains(normalize-space(.), "{group_name}")]'),
            (By.XPATH, f'//div[@role="dialog"]//*[contains(normalize-space(text()), "{group_name}")]'),
            (By.XPATH, f'//div[@role="dialog"]//div[contains(normalize-space(.), "{group_name}")]'),
            (By.XPATH, f'//*[normalize-space(text())="{group_name}"]'),
        ])

    def _click_group_and_confirm():
        """คลิกกลุ่มแล้วเช็คว่าเข้าหน้าคอมโพสไหม (มีช่องแคปชั่น/ปุ่มโพสต์ = เลือกติด)."""
        it = _find_group_item()
        if not it:
            return False
        _click(driver, it)
        time.sleep(3)
        return bool(_find_first(driver, caption_locators) or _find_first(driver, post_btn_locators))

    # (a) ลองกดกลุ่มโดยตรงจากรายการที่โผล่มา — ไม่พิมพ์ค้นหา
    selected = False
    for _sel in range(3):
        if _click_group_and_confirm():
            selected = True
            break

    # (b) fallback: ยังไม่เจอ → พิมพ์ชื่อในช่องค้นหาแล้วเลือก
    if not selected:
        try:
            search.clear()
        except Exception:
            pass
        _type_like_human(search, group_name)
        time.sleep(3)
        for _sel in range(3):
            if _click_group_and_confirm():
                selected = True
                break

    if not selected:
        return False, f"เลือกกลุ่ม '{group_name}' แล้วแต่ไม่เข้าหน้าคอมโพส (บัญชีต้องเป็นสมาชิกกลุ่มนั้นด้วย)"

    # 5. ใส่แคปชั่น (ถ้ามี — โหมด direct เท่านั้น; การแชร์โพสต์ลงกลุ่มส่วนใหญ่ไม่มีช่อง)
    if message:
        box = _find_first(driver, caption_locators)
        if box:
            _type_like_human(box, message)
            time.sleep(2)
        else:
            print("[WARNING] ไม่พบช่องแคปชั่น → แชร์โดยไม่มีข้อความ")

    # 6. กดปุ่มยืนยัน
    post_btn = _find_first(driver, post_btn_locators)
    if not post_btn:
        return False, "ไม่พบปุ่มโพสต์"
    if dry_run:
        print("[DRY-RUN] พบปุ่มโพสต์แล้ว แต่ไม่กด (โหมดจำลอง)")
        return True, "dry-run"
    _click(driver, post_btn)
    # ยืนยันว่าสำเร็จจริง: dialog แชร์ต้องปิด — ถ้ายังเปิด = ล้ม/ถูกกัน
    if _share_dialog_closed(driver):
        return True, "แชร์สำเร็จ (dialog ปิด)"
    try:
        err_el = WebDriverWait(driver, 4).until(
            EC.presence_of_element_located((By.XPATH, '//*[@role="alert"]'))
        )
        return False, f"กดโพสต์แล้ว แต่เจอ error: {(err_el.text or '').strip()[:80]}"
    except Exception:
        return False, "กดโพสต์แล้ว แต่ dialog ไม่ปิด (ไม่ยืนยัน — ตรวจที่กลุ่ม)"


def _scroll_picker_list(driver) -> None:
    """เลื่อน scroller ของรายการกลุ่มใน dialog ลง (ให้ render กลุ่มที่ยังไม่โผล่)."""
    try:
        driver.execute_script(
            "var d=document.querySelector('div[role=dialog]');"
            "if(!d) return;"
            "var els=d.querySelectorAll('div');"
            "for(var i=0;i<els.length;i++){if(els[i].scrollHeight>els[i].clientHeight+80){els[i].scrollTop=els[i].scrollHeight;return;}}"
            "d.scrollTop=d.scrollHeight;"
        )
    except Exception:
        pass


def share_post_to_group_os(driver, post_url: str, group_name: str,
                           caption: Optional[str] = None,
                           dry_run: bool = False) -> Tuple[bool, str]:
    """แชร์โพสต์ลงกลุ่มเดียว — flow จริงที่พิสูจน์แล้ว (FB 2026):
    แชร์ → พิมพ์แคป → กด 'แชร์ไปยังกลุ่ม' (คลิกเมาส์จริง) → เลื่อนเลือกชื่อกลุ่ม → โพสต์.

    ใช้ pyautogui คลิกเมาส์จริงที่พิกัดจอ (img_click) เพราะ FB กัน DOM/synthetic click
    ที่ปุ่ม 'แชร์ไปยังกลุ่ม' และแถวกลุ่ม.
    """
    import img_click  # noqa: F401  (รันบนเครื่องที่มีจอ + Chrome เปิดเต็มจอ)

    print(f"[INFO] เปิดโพสต์ต้นทาง (os): {post_url}")
    try:
        driver.get(post_url)
    except Exception as e:
        print(f"[WARNING] โหลดโพสต์: {e}")
    time.sleep(5)
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(1)
    except Exception:
        pass

    # 1. กด "แชร์" (DOM click ใช้ได้)
    share_btn = _find_first(driver, [
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "ส่งลิงก์") or contains(@aria-label, "โพสต์ลงในโปรไฟล์ของคุณ")]'),
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "Send this") or contains(@aria-label, "post on your profile")]'),
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "แชร์") or contains(@aria-label, "Share")]'),
    ])
    if not share_btn:
        return False, "ไม่พบปุ่มแชร์"
    _click(driver, share_btn)
    time.sleep(3)

    # 2. พิมพ์แคปชัน (_type_like_human ตัด emoji นอก BMP ให้เอง — ChromeDriver รับเฉพาะ BMP)
    if caption:
        box = _find_first(driver, [
            (By.XPATH, '//div[@role="dialog"]//div[@role="textbox"]'),
            (By.XPATH, '//div[@role="dialog"]//*[contains(@aria-label, "บอกอะไรสักหน่อย")]'),
        ])
        if box:
            _type_like_human(box, caption)
            time.sleep(1)

    # 3. กด "กลุ่ม" (ปุ่มในแถบ "แชร์ไปยัง" — บางเวอร์ชัน aria-label="แชร์ไปยังกลุ่ม") ด้วยเมาส์จริง
    group_btn = _find_first(driver, [
        (By.XPATH, '//div[@role="dialog"]//div[@role="button"][contains(@aria-label, "แชร์ไปยังกลุ่ม") or contains(@aria-label, "Share to a group")]'),
        (By.XPATH, '//div[@role="dialog"]//*[contains(@aria-label, "แชร์ไปยังกลุ่ม") or contains(@aria-label, "Share to a group")]'),
        (By.XPATH, '//div[@role="dialog"]//div[@role="button"][normalize-space(.)="กลุ่ม"]'),
        (By.XPATH, '//div[@role="dialog"]//*[normalize-space(.)="กลุ่ม"]'),
    ])
    if not group_btn:
        return False, "ไม่พบปุ่ม 'กลุ่ม' (แชร์ไปยังกลุ่ม)"
    img_click.click_element_coord(driver, group_btn)
    time.sleep(4)

    # 4. เลื่อนรายการจนเจอชื่อกลุ่ม แล้วคลิก (เมาส์จริง)
    row = None
    for _ in range(25):
        try:
            row = driver.find_element(
                By.XPATH,
                f'//div[@role="dialog"]//div[@role="button"][contains(normalize-space(.), "{group_name}")]')
            break
        except Exception:
            _scroll_picker_list(driver)
            time.sleep(1)
    if not row:
        return False, f"ไม่พบกลุ่ม '{group_name}' ในรายการ (บัญชีต้องเป็นสมาชิกกลุ่มนั้นด้วย)"
    img_click.click_element_coord(driver, row)
    time.sleep(4)

    # 5. กดปุ่มยืนยัน ("โพสต์" / "แชร์เลย" / "แชร์") ด้วยเมาส์จริง
    post_btn = _find_first(driver, [
        (By.XPATH, '//*[@role="button"][normalize-space(.)="โพสต์" or normalize-space(.)="Post"]'),
        (By.XPATH, '//div[@role="dialog"]//*[normalize-space(text())="โพสต์" or normalize-space(text())="Post"]'),
        (By.XPATH, '//*[@role="button"][normalize-space(.)="แชร์เลย" or normalize-space(.)="Share now"]'),
        (By.XPATH, '//div[@role="dialog"]//*[normalize-space(text())="แชร์เลย" or normalize-space(text())="Share now"]'),
        (By.XPATH, '//*[@role="button"][normalize-space(.)="แชร์" or normalize-space(.)="Share"]'),
        (By.XPATH, '//div[@role="dialog"]//*[normalize-space(text())="แชร์" or normalize-space(text())="Share"]'),
    ])
    if not post_btn:
        return False, "ไม่พบปุ่มโพสต์/แชร์เลย"
    if dry_run:
        return True, f"dry-run — เลือก '{group_name}' แล้ว แต่ไม่กดโพสต์"
    img_click.click_element_coord(driver, post_btn)
    time.sleep(4)
    if _share_dialog_closed(driver, timeout=8):
        return True, "แชร์สำเร็จ (dialog ปิด)"
    return False, "กดโพสต์แล้ว แต่ dialog ไม่ปิด (ตรวจที่กลุ่ม)"


def share_post_to_groups_multi(driver, post_url: str, group_names: List[str],
                               message: Optional[Union[str, List[str]]] = None,
                               dry_run: bool = False) -> Tuple[bool, str, List[str]]:
    """แชร์โพสต์ลงหลายกลุ่ม — ใช้ flow จริงที่พิสูจน์แล้ว (แชร์ → กด 'กลุ่ม' → เลือกชื่อกลุ่ม → โพสต์)
    ด้วยเมาส์จริง (img_click) เพราะ Facebook กัน DOM/synthetic click ที่ปุ่ม 'กลุ่ม' และแถวกลุ่ม.

    แชร์ทีละ 1 กลุ่มต่อ 1 ครั้ง (flow เดียวที่พิสูจน์ว่าแชร์สำเร็จจริง) แล้วเว้นระยะสั้น ๆ
    กัน FB rate-limit.

    message: str = ใช้ข้อความเดียวทุกกลุ่ม; list[str] = หมุนแคปชั่นกันแต่ละกลุ่ม (กันข้อความซ้ำ)

    คืน (ok, note, selected_names)
    """
    if not group_names:
        return False, "ไม่มีกลุ่มเป้าหมาย", []
    selected_all: List[str] = []
    for i, name in enumerate(group_names, 1):
        if isinstance(message, (list, tuple)) and message:
            msg = message[(i - 1) % len(message)]  # หมุนแคปชั่นกันแต่ละกลุ่ม
        else:
            msg = message
        print(f"[GROUP] ({i}/{len(group_names)}) แชร์ไปยัง '{name}'")
        ok, note = share_post_to_group_os(driver, post_url, name, msg, dry_run)
        if ok:
            selected_all.append(name)
            print(f"[OK] '{name}' → {note}")
        else:
            print(f"[SKIP] '{name}' → {note}")
        if i < len(group_names):
            time.sleep(6)  # เว้นระหว่างกลุ่ม กัน FB rate-limit
    if not selected_all:
        return False, "ไม่มีกลุ่มที่แชร์สำเร็จ (บัญชีต้องเป็นสมาชิกกลุ่มนั้นด้วย)", []
    return True, f"แชร์สำเร็จ {len(selected_all)}/{len(group_names)} กลุ่ม", selected_all


# ---------------------------------------------------------------------------
# โพสต์ตรงลงกลุ่ม (Direct Post — สูตร "รูปสะอาด + ลิงก์ในคอมเมนต์" ตามคู่มือ)
# ---------------------------------------------------------------------------
def _comment_newest_post(driver, text: str) -> bool:
    """โพสต์แรกสุดในฟีด (โพสต์ที่เพิ่งสร้าง) → เปิดหน้าโพสต์ → พิมพ์คอมเมนต์ (วางลิงก์ LINE)."""
    try:
        articles = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, '//div[@role="article"]'))
        )
    except Exception:
        print("[COMMENT] ไม่พบโพสต์ในฟีด → ข้ามคอมเมนต์")
        return False
    if not articles:
        return False
    # หา link ไปหน้าโพสต์ในโพสต์แรกสุด (โพสต์ของเราเพิ่งโพสต์ → อยู่บนสุด)
    post_url = None
    for a in articles[0].find_elements(
            By.XPATH,
            './/a[contains(@href, "/posts/") or contains(@href, "permalink") '
            'or contains(@href, "story_fbid")]'):
        href = (a.get_attribute("href") or "").strip()
        if href:
            post_url = href
            break
    if not post_url:
        print("[COMMENT] หา URL โพสต์ในฟีดไม่เจอ → ข้ามคอมเมนต์")
        return False
    try:
        driver.get(post_url)
    except Exception as e:
        print(f"[WARNING] โหลดหน้าโพสต์เพื่อคอมเมนต์: {e}")
    time.sleep(5)
    box = _find_first(driver, [
        (By.XPATH, '//div[@role="textbox"][contains(@aria-label, "เขียนความคิดเห็น") '
                   'or contains(@aria-label, "Write a comment") '
                   'or contains(@aria-label, "แสดงความคิดเห็น") '
                   'or contains(@aria-label, "comment")]'),
        (By.XPATH, '//div[@role="textbox"]'),
    ])
    if not box:
        print("[COMMENT] ไม่พบกล่องคอมเมนต์ในหน้าโพสต์ → ต้องวางลิงก์เอง")
        return False
    _type_like_human(box, text)
    time.sleep(2)
    try:
        box.send_keys(Keys.ENTER)
    except Exception as e:
        print(f"[WARNING] ส่งคอมเมนต์: {e}")
    time.sleep(3)
    print("[COMMENT] วางลิงก์ในคอมเมนต์แรกสำเร็จ")
    return True


def post_to_group(driver, group_url: str, caption: str,
                  poster_path: Optional[str] = None,
                  comment: Optional[str] = None,
                  dry_run: bool = False) -> Tuple[bool, bool, str]:
    """โพสต์ตรงลงกลุ่ม (Direct Post — ปลอดภัยกว่าแชร์จากเพจ ตามคู่มือ):

    เปิดกลุ่ม → กดเริ่มโพสต์ → แนบรูปโปสเตอร์ → พิมพ์แคปชั่นสะอาด (ไม่มีลิงก์)
    → กดโพสต์ → คอมเมนต์แรกวางลิงก์ LINE (best-effort)

    คืน (posted_ok, comment_ok, note) — โพสต์สำเร็จแต่คอมเมนต์ล้ม = posted_ok=True
    comment_ok=False (ห้ามนับ fail เพราะเดี๋ยวจะโพสต์ซ้ำ)
    """
    print(f"[INFO] เปิดหน้ากลุ่ม: {group_url}")
    try:
        driver.get(group_url)
    except Exception as e:
        print(f"[WARNING] โหลดหน้ากลุ่ม: {e}")
    time.sleep(5)

    # ปิด dialog ที่อาจค้างจากกลุ่มก่อนหน้า (กัน state สับสนระหว่างกลุ่ม)
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(1)
    except Exception:
        pass

    # 1. กดช่อง "เริ่มโพสต์" (composer) — FB 2026 หน้า�กลุ่มใช้ span "เขียนอะไรสักหน่อย...."
    #    (ตัวคลิกจริงคือ ancestor ที่เป็น role=button)
    composer_trigger = _find_first(driver, [
        (By.XPATH, '//*[contains(text(), "เขียนอะไรสักหน่อย") '
                   'or contains(text(), "Write something") '
                   'or contains(text(), "เริ่มโพสต์")]'),
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "เริ่มโพสต์") '
                   'or contains(@aria-label, "Write something") '
                   'or contains(@aria-label, "สร้างโพสต์") '
                   'or contains(@aria-label, "Create post")]'),
    ])
    if not composer_trigger:
        return False, False, "ไม่พบช่องเริ่มโพสต์ (composer)"
    # span เปล่าไม่คลิกได้ → เดินขึ้นหา ancestor ที่เป็น role=button / <a>
    target = composer_trigger
    for _ in range(4):
        parent = target.find_element(By.XPATH, "..")
        if parent.get_attribute("role") == "button" or parent.tag_name == "a":
            target = parent
            break
        target = parent
    _click(driver, target)
    time.sleep(3)

    # 2. ช่องเขียนข้อความ (ใน dialog ที่เปิดขึ้น)
    box = _find_first(driver, [
        (By.XPATH, '//div[@role="dialog"]//div[@role="textbox"]'),
        (By.XPATH, '//div[@role="textbox"][@contenteditable="true"]'),
        (By.XPATH, '//div[@role="textbox"]'),
    ])
    if not box:
        return False, False, "ไม่พบช่องเขียนโพสต์ใน dialog"

    # 3. แนบรูปโปสเตอร์ (ถ้ามี)
    if poster_path:
        try:
            file_input = driver.find_element(By.XPATH, '//input[@type="file"]')
            file_input.send_keys(str(Path(poster_path).resolve()))
            print("[INFO] ส่งไฟล์ภาพให้เบราว์เซอร์แล้ว รอพรีวิวอัปโหลด...")
            time.sleep(6)
        except Exception as e:
            print(f"[WARNING] แนบภาพไม่สำเร็จ (โพสต์ข้อความล้วน): {e}")

    # 4. พิมพ์แคปชั่นสะอาด (ไม่มีลิงก์ — ลิงก์ไปอยู่ในคอมเมนต์แรก)
    if caption and not dry_run:
        _type_like_human(box, caption)
        time.sleep(2)
    elif caption and dry_run:
        print(f"[DRY-RUN] จะพิมพ์แคปชั่น:\n{caption}")

    # 5. ปุ่ม "โพสต์" — FB 2026 ใน dialog สร้างโพสต์เป็น element ข้อความ ไม่ใช่ role=button
    post_btn = _find_first(driver, [
        (By.XPATH, '//div[@role="dialog"]//*[normalize-space(text())="โพสต์" '
                   'or normalize-space(text())="Post"]'),
        (By.XPATH, '//div[@role="dialog"]//*[@role="button"]'
                   '[normalize-space(text())="โพสต์" or normalize-space(text())="Post"]'),
        (By.XPATH, '//*[@role="button"][normalize-space(text())="โพสต์" '
                   'or normalize-space(text())="Post"]'),
    ])
    if not post_btn:
        return False, False, "ไม่พบปุ่มโพสต์"
    if dry_run:
        print("[DRY-RUN] พบปุ่มโพสต์แล้ว — ไม่กด (โหมดจำลอง)")
        return True, True, "dry-run (locator ครบ: composer/กล่องข้อความ/ปุ่มโพสต์)"

    _click(driver, post_btn)

    # ยืนยันว่าสำเร็จจริง: composer dialog ปิด หรือช่องข้อความหายไป (Facebook รับโพสต์แล้ว)
    posted = False
    if _share_dialog_closed(driver):
        posted = True
    else:
        try:
            WebDriverWait(driver, 8).until(EC.staleness_of(box))
            posted = True
        except Exception:
            posted = False
    if not posted:
        return False, False, "กดโพสต์แล้ว แต่ไม่ยืนยันว่าโพสต์ขึ้น (dialog/กล่องไม่ปิด)"
    time.sleep(4)

    # 6. คอมเมนต์แรกวางลิงก์ (best-effort — ล้มไม่นับ fail เพราะโพสต์ขึ้นแล้ว)
    comment_ok = True
    if comment:
        print("[COMMENT] กำลังวางลิงก์ในคอมเมนต์แรก...")
        comment_ok = _comment_newest_post(driver, comment)
        if not comment_ok:
            print("[WARN] คอมเมนต์ลิงก์ไม่สำเร็จ — โพสต์ขึ้นแล้ว แต่ต้องวางลิงก์เองที่คอมเมนต์")

    note = "โพสต์ตรงลงกลุ่มสำเร็จ (dialog ปิด)"
    if comment and not comment_ok:
        note += " · คอมเมนต์ลิงก์ไม่สำเร็จ (วางเอง)"
    return True, comment_ok, note


def _resolve_group_name(driver, group_url: str) -> str:
    """เปิดหน้ากลุ่มแล้วอ่านชื่อจริง (ไว้ป้อนช่องค้นหากลุ่มใน dialog แชร์)."""
    print(f"[INFO] เปิดหน้ากลุ่มเพื่ออ่านชื่อ: {group_url}")
    try:
        driver.get(group_url)
    except Exception as e:
        print(f"[WARNING] โหลดหน้ากลุ่ม: {e}")
    time.sleep(4)

    title = (driver.title or "").strip()
    for suffix in (" | Facebook", "| Facebook", " - Facebook"):
        if title.lower().endswith(suffix.lower()):
            title = title[: -len(suffix)].strip()
            break
    # ตัด badge จำนวนแจ้งเตือนที่ Facebook แปะหน้าชื่อใน <title> เช่น "(20+) ชื่อกลุ่ม"
    title = re.sub(r'^\(\d+\+?\)\s*', '', title).strip()
    if title and "facebook" not in title.lower():
        return title

    # fallback: หา heading แรกของหน้า
    for by, sel in [
        (By.XPATH, "//h1[1]"),
        (By.XPATH, "//h2[1]"),
        (By.XPATH, '//*[@role="heading"][1]'),
    ]:
        try:
            el = WebDriverWait(driver, 5).until(EC.presence_of_element_located((by, sel)))
            t = (el.text or "").strip()
            if t and "facebook" not in t.lower():
                return t
        except Exception:
            continue
    return title or group_url


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="แชร์โพสต์เพจลงกลุ่ม (ปุ่มแชร์) — บันทึกชีทเท่านั้น")
    parser.add_argument("--post-url", type=str, required=True, help="URL โพสต์บนเพจที่จะแชร์")
    parser.add_argument("--group-name", type=str, default=None,
                        help="ชื่อกลุ่มเป้าหมาย (หลายกลุ่มคั่นด้วย ,)")
    parser.add_argument("--group-url", type=str, default=None,
                        help="URL กลุ่มเป้าหมาย (หลาย URL คั่นด้วย ,) — เปิดอ่านชื่อจริงเอง")
    parser.add_argument("--caption", type=str, default=None,
                        help="แคปชั่นตอนแชร์ (ถ้าไม่ระบุ → หมุน 15 แบบ spintax กันแต่ละกลุ่ม)")
    parser.add_argument("--cookies", type=str, default=None, help="พาธคุกกี้ (default fb_cookies.json)")
    parser.add_argument("--dry-run", action="store_true", help="จำลอง: ไม่แชร์ + ไม่บันทึกชีท")
    args = parser.parse_args()

    groups = [g.strip() for g in (args.group_name or "").split(",") if g.strip()]
    group_urls = [g.strip() for g in (args.group_url or "").split(",") if g.strip()]
    if not groups and not group_urls:
        parser.error("ต้องระบุ --group-name หรือ --group-url อย่างใดอย่างหนึ่ง")

    cookie_path = Path(args.cookies) if args.cookies else ROOT / "fb_cookies.json"
    captions = [args.caption] if args.caption else _share_caption_variants()

    print(f"[BROWSER] เปิดเบราว์เซอร์ + ฉีดคุกกี้ (จะแชร์ {len(groups) + len(group_urls)} กลุ่ม)")
    driver = _launch_driver()
    try:
        if not inject_cookies(driver, cookie_path):
            print("[ERROR] ตั้งค่าล็อกอิน Facebook ไม่สำเร็จ → ยกเลิก")
            return 1

        # แปลง group-url → ชื่อกลุ่มจริง (ฉีดคุกกี้เสร็จแล้วค่อยเปิดอ่านได้)
        for url in group_urls:
            name = _resolve_group_name(driver, url)
            print(f"[GROUP] {url} → '{name}'")
            groups.append(name)

        results = {"ok": 0, "fail": 0, "sheet_ok": 0}
        for i, group in enumerate(groups, 1):
            caption = captions[(i - 1) % len(captions)]
            print(f"\n👉 [{i}/{len(groups)}] แชร์โพสต์เพจ → กลุ่ม '{group}'")
            ok, note = share_post_to_group(driver, args.post_url, group, caption, args.dry_run)

            if args.dry_run:
                print(f"[DRY-RUN] {note} — ไม่บันทึกชีท (โหมดจำลอง)")
            else:
                if ok:
                    results["ok"] += 1
                else:
                    results["fail"] += 1
                if _log_to_sheet(_sheet_row(args.post_url, group, caption, ok)):
                    results["sheet_ok"] += 1

            if i < len(groups):
                time.sleep(10)

        print("\n==========================================")
        print(f"สรุป: แชร์สำเร็จ {results['ok']} | ล้ม {results['fail']} | บันทึกชีท {results['sheet_ok']}")
        return 0
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
