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
from typing import Any, Dict, List, Optional, Tuple

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


def _default_caption() -> str:
    """แคปชั่นตอนแชร์ (โปรโมทบอทป้าเข็ม — ไม่มีลิงก์สินค้า)"""
    line_oa_url = os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    return (
        "อยากใช้บอทช่วยขายของ Shopee (บอทป้าเข็ม) ป้าจัดการระบบให้พร้อมใช้ทันทีจ้า 😊\n"
        "🛠️ ปลอดภัยรันบนบัญชี/คีย์คุณเอง แอดมินดูแลหลังบ้านให้หมด ไม่ต้องเซ็ตค่าเองให้ปวดหัวจ้า\n"
        f"💼 เริ่มต้น 490.- แอดไลน์คุยรายละเอียดแพ็กเกจกับป้าเลยจ้า 👉 {line_oa_url}"
    )


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
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


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

    # 2. กดตัวเลือก "กลุ่ม" (ใน section "แชร์ไปยัง") — FB 2026 เหลือคำว่า "กลุ่ม" เฉย ๆ
    group_opt = _find_first(driver, [
        (By.XPATH, '//div[@role="dialog"]//span[normalize-space(text())="กลุ่ม"]'),
        (By.XPATH, '//div[@role="dialog"]//*[normalize-space(text())="Groups"]'),
        (By.XPATH, '//*[normalize-space(text())="แชร์ไปยังกลุ่ม" or normalize-space(text())="แชร์ในกลุ่ม"]'),
        (By.XPATH, '//*[contains(text(), "Share to a group") or contains(text(), "Share in a group")]'),
    ])
    if not group_opt:
        return False, "ไม่พบตัวเลือก 'กลุ่ม' (แชร์ไปยังกลุ่ม)"
    _click(driver, group_opt)
    time.sleep(5)

    # 3. ค้นหากลุ่มเป้าหมาย
    search = _find_first(driver, [
        (By.XPATH, '//input[@placeholder="ค้นหากลุ่ม"] | //input[@aria-label="ค้นหากลุ่ม"]'),
        (By.XPATH, '//input[@placeholder="Search for groups"] | //input[@aria-label="Search for groups"]'),
    ])
    if not search:
        return False, "ไม่พบช่องค้นหากลุ่ม"
    try:
        search.clear()
    except Exception:
        pass
    _type_like_human(search, group_name)
    time.sleep(3)

    # 4. เลือกกลุ่มจากผลลัพธ์ (รายการเป็น div ธรรมดา ไม่มี role — ใช้ text ภายใน dialog)
    group_item = _find_first(driver, [
        (By.XPATH, f'//div[@role="dialog"]//*[contains(normalize-space(text()), "{group_name}")]'),
        (By.XPATH, f'//div[@role="dialog"]//div[contains(normalize-space(.), "{group_name}")]'),
        (By.XPATH, f'//*[normalize-space(text())="{group_name}"]'),
    ])
    if not group_item:
        return False, f"ไม่พบกลุ่ม '{group_name}' ในผลลัพธ์ (บัญชีต้องเป็นสมาชิกกลุ่มนั้นด้วย)"
    _click(driver, group_item)
    time.sleep(3)

    # 5. ใส่แคปชั่น (ถ้ามี)
    if message:
        box = _find_first(driver, [
            (By.XPATH, '//div[@role="dialog"]//div[@role="textbox" or @contenteditable="true"]'),
            (By.XPATH, '//div[@aria-label="เขียนข้อความ" or @aria-label="เขียนอะไรบางอย่าง"]'),
        ])
        if box:
            _type_like_human(box, message)
            time.sleep(2)
        else:
            print("[WARNING] ไม่พบช่องแคปชั่น → แชร์โดยไม่มีข้อความ")

    # 6. กดปุ่ม "โพสต์" (Post)
    post_btn = _find_first(driver, [
        (By.XPATH, '//div[@role="dialog"]//div[@role="button"][normalize-space(text())="โพสต์" or normalize-space(text())="Post"]'),
        (By.XPATH, '//*[@role="button"][normalize-space(text())="โพสต์" or normalize-space(text())="Post"]'),
    ])
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

    # 1. กดช่อง "เริ่มโพสต์" (composer)
    composer_trigger = _find_first(driver, [
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "เริ่มโพสต์") '
                   'or contains(@aria-label, "Write something") '
                   'or contains(@aria-label, "เขียนอะไร")]'),
        (By.XPATH, '//*[contains(text(), "เริ่มโพสต์") or contains(text(), "Write something")]'),
        (By.XPATH, '//div[@role="button"][contains(@aria-label, "สร้างโพสต์") '
                   'or contains(@aria-label, "Create post")]'),
    ])
    if not composer_trigger:
        return False, False, "ไม่พบช่องเริ่มโพสต์ (composer)"
    _click(driver, composer_trigger)
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

    # 5. ปุ่ม "โพสต์"
    post_btn = _find_first(driver, [
        (By.XPATH, '//div[@role="dialog"]//div[@role="button"]'
                   '[normalize-space(text())="โพสต์" or normalize-space(text())="Post"]'),
        (By.XPATH, '//*[@role="button"][normalize-space(text())="โพสต์" '
                   'or normalize-space(text())="Post"]'),
        (By.XPATH, '//*[normalize-space(text())="โพสต์" or normalize-space(text())="Post"]'),
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
    parser.add_argument("--caption", type=str, default=None, help="แคปชั่นตอนแชร์ (default = โปรโมทบอทป้าเข็ม)")
    parser.add_argument("--cookies", type=str, default=None, help="พาธคุกกี้ (default fb_cookies.json)")
    parser.add_argument("--dry-run", action="store_true", help="จำลอง: ไม่แชร์ + ไม่บันทึกชีท")
    args = parser.parse_args()

    groups = [g.strip() for g in (args.group_name or "").split(",") if g.strip()]
    group_urls = [g.strip() for g in (args.group_url or "").split(",") if g.strip()]
    if not groups and not group_urls:
        parser.error("ต้องระบุ --group-name หรือ --group-url อย่างใดอย่างหนึ่ง")

    cookie_path = Path(args.cookies) if args.cookies else ROOT / "fb_cookies.json"
    caption = args.caption or _default_caption()

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
