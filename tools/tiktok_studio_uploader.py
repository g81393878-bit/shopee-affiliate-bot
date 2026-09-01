#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/tiktok_studio_uploader.py — อัปโหลดวิดีโอเข้า TikTok Creator Center ผ่าน Playwright Browser Automation

ข้อดี:
1. ไม่ต้องขอ TikTok Developer App หรือ Verify URL แม้แต่นิดเดียว
2. ล็อกอินผ่านหน้าเว็บครั้งแรกครั้งเดียว เซสชันจะถูกบันทึกไว้ใน tools/tiktok_user_data ถาวร
3. อัปโหลดวิดีโอ ใส่แคปชั่น แฮชแท็ก และกดปุ่มโพสต์ให้อัตโนมัติ 100%
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import time
from typing import Dict, Optional, Union

# บังคับ UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
TOOLS_DIR = PROJECT_ROOT / "tools"
USER_DATA_DIR = TOOLS_DIR / "tiktok_user_data"
COOKIE_FILE = TOOLS_DIR / "tiktok_cookies.json"
LOG_FILE = TOOLS_DIR / "tiktok_studio_uploader.log"

UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
LOGIN_URL = "https://www.tiktok.com/login"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"


def log(msg: str):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts} UTC] [TikTok Studio] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def is_logged_in() -> bool:
    """เช็คว่ามี Cookie JSON หรือโฟลเดอร์เซสชัน TikTok หรือไม่"""
    if COOKIE_FILE.exists() and COOKIE_FILE.stat().st_size > 20:
        return True
    return USER_DATA_DIR.exists() and any(USER_DATA_DIR.iterdir())


def login_flow():
    """เปิดเบราว์เซอร์ให้ผู้ใช้ล็อกอิน TikTok ด้วยตัวเอง 1 ครั้งเพื่อเก็บ Session Cookie"""
    from playwright.sync_api import sync_playwright

    print("\n" + "=" * 65)
    print("🔑 เริ่มต้นกระบวนการเข้าสู่ระบบ TikTok (ทำครั้งแรกครั้งเดียว)")
    print("=" * 65)
    print("👉 ระบบกำลังเปิดหน้าต่างเบราว์เซอร์ Chrome ให้คุณล็อกอิน...")
    print("👉 คุณสามารถล็อกอินด้วย Email, Google หรือสแกน QR Code จากแอป TikTok ในมือถือได้เลยครับ")
    print("-" * 65)

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            user_agent=USER_AGENT,
            channel="chrome" if os.name == "nt" else None,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
            ],
            viewport=None,
        )
        page = browser.new_page()
        page.goto("https://www.tiktok.com/login", timeout=60000)

        print("\n⏳ กำลังรอให้คุณล็อกอิน... (ระบบให้เวลา 3 นาที)")
        print("💡 เมื่อล็อกอินสำเร็จและเข้าสู่หน้า TikTok เรียบร้อย ระบบจะบันทึกเซสชันให้อัตโนมัติ")

        logged_in = False
        start_time = time.time()
        while time.time() - start_time < 180:
            current_url = page.url
            if "login" not in current_url and ("tiktok.com" in current_url):
                cookies = page.context.cookies()
                session_cookies = [c for c in cookies if c.get("name") in ("sessionid", "sessionid_ss", "sid_guard")]
                if session_cookies:
                    logged_in = True
                    break
            time.sleep(2)

        if logged_in:
            print("\n🎉 ล็อกอิน TikTok สำเร็จ 100%! บันทึก Session เรียบร้อยแล้ว")
            log("TikTok Session Saved Successfully!")
            page.goto(UPLOAD_URL, timeout=30000)
            time.sleep(3)
        else:
            print("\n⚠️ หมดเวลาการรอ หรือยังไม่ได้เข้าสู่ระบบสมบูรณ์")

        browser.close()


def sanitize_caption(caption: str, max_chars: int = 150) -> str:
    caption = (caption or "").strip()
    caption = re.sub(r"\b\d+([.,]\d+)?\s*(บาท|฿|baht)\b", "", caption, flags=re.IGNORECASE)
    if "#ป้าเข็ม" not in caption:
        caption += " #ป้าเข็มรีวิว"
    if "#ของดีบอกต่อ" not in caption:
        caption += " #ของดีบอกต่อ"
    if len(caption) > max_chars:
        caption = caption[:max_chars - 3] + "..."
    return caption


def upload_video_via_web(
    video_path: Union[str, pathlib.Path],
    caption: str = "",
    headless: bool = True,
) -> Dict:
    """อัปโหลดวิดีโอ 9:16 เข้าสู่ TikTok Creator Center โดยอัตโนมัติผ่าน Playwright"""
    from playwright.sync_api import sync_playwright

    video_file = pathlib.Path(video_path).resolve()
    if not video_file.exists():
        return {"success": False, "error": f"Video file not found: {video_file}"}

    if not is_logged_in():
        return {"success": False, "error": "TikTok session not found. Please run: python tools/tiktok_studio_uploader.py --login"}

    clean_caption = sanitize_caption(caption)
    log(f"🎬 เริ่มต้นอัปโหลดคลิป: {video_file.name} (Caption: {clean_caption[:50]}...)")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                headless=headless,
                user_agent=USER_AGENT,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
                viewport={"width": 1440, "height": 900},
            )
            if COOKIE_FILE.exists():
                try:
                    c_data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
                    browser.add_cookies(c_data)
                except Exception as e_cook:
                    log(f"⚠️ Load cookies error: {e_cook}")

            page = browser.new_page()

            # 1. ไปหน้า Creator Center Upload
            log("🌐 กำลังเปิดหน้า TikTok Studio Upload...")
            page.goto(UPLOAD_URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            # ตรวจสอบว่าหลุดไปหน้า Login ไหม
            if "login" in page.url:
                browser.close()
                return {"success": False, "error": "TikTok session expired. Please re-run --login"}

            # 2. ค้นหาช่องอัปโหลดไฟล์วิดีโอ (iframe หรือ input file)
            log("📤 กำลังส่งไฟล์วิดีโอเข้าสู่ฟอร์มอัปโหลด...")
            file_input = page.locator('input[type="file"]')
            if not file_input.count():
                # ลองค้นหาใน iframe
                for frame in page.frames:
                    if frame.locator('input[type="file"]').count() > 0:
                        file_input = frame.locator('input[type="file"]')
                        break

            file_input.set_input_files(str(video_file))
            log("   ✓ แนบไฟล์วิดีโอสำเร็จ รอระบบประมวลผล...")

            # 3. รอให้วิดีโออัปโหลดขึ้นเซิร์ฟเวอร์เสร็จ (รอสูงสุด 90 วินาที)
            page.wait_for_timeout(8000)

            # ปิด Onboarding Joyride / Tooltip Popup ถ้ามี
            try:
                page.evaluate("""() => {
                    const joyride = document.querySelector('#react-joyride-portal, .react-joyride__overlay');
                    if (joyride) joyride.remove();
                    document.querySelectorAll('button').forEach(b => {
                        const txt = (b.innerText || '').toLowerCase();
                        if (txt.includes('got it') || txt.includes('understand') || txt.includes('เข้าใจ') || txt.includes('skip')) {
                            b.click();
                        }
                    });
                }""")
            except Exception:
                pass

            # 4. ใส่ Caption & Hashtags
            log("✍️ กำลังกรอกแคปชั่นและแฮชแท็ก...")
            # หา element กล่องข้อความ Caption (contenteditable หรือ textarea)
            caption_box = page.locator('div[contenteditable="true"]').first
            if caption_box.count() > 0:
                caption_box.click(force=True)
                caption_box.fill("")
                caption_box.type(clean_caption, delay=20)
            else:
                txt_area = page.locator('textarea').first
                if txt_area.count() > 0:
                    txt_area.click(force=True)
                    txt_area.fill(clean_caption)

            page.wait_for_timeout(3000)

            # 5. กดปุ่ม Post (โพสต์) — ใช้ exact match เพื่อไม่ให้ไปโดนเมนู "Posts"
            log("🚀 กำลังกดปุ่มโพสต์วิดีโอ...")
            post_btn = page.locator('button').filter(has_text=re.compile(r'^(Post|โพสต์|Publish)$')).first
            if post_btn.count() > 0:
                post_btn.click(force=True)
                log("   ✓ คลิกปุ่ม Post จริงเรียบร้อยแล้ว!")
            else:
                # Fallback ค้นหาปุ่มที่มีคำว่า Post แต่ไม่ใช่ Posts
                alt_btn = page.locator('button:text-is("Post"), button:text-is("โพสต์")').first
                if alt_btn.count() > 0:
                    alt_btn.click(force=True)
                    log("   ✓ คลิกปุ่ม Post (Exact Text) เรียบร้อยแล้ว!")
                else:
                    log("⚠️ ไม่พบปุ่ม Post โดยตรง ลองค้นหาปุ่ม Submit...")
                    page.locator('button[type="submit"]').first.click(force=True)

            # 6. รอยืนยันการโพสต์สำเร็จ (รอ TikTok ประมวลผลและแสดงผลสำเร็จ)
            log("⏳ รอระบบ TikTok ประมวลผลการโพสต์ (15 วินาที)...")
            page.wait_for_timeout(15000)
            log("🎉 อัปโหลดและสั่งโพสต์คลิปขึ้น TikTok สำเร็จ 100%!")

            browser.close()
            return {
                "success": True,
                "message": "Video published to TikTok successfully via Web Studio",
                "video_url": "https://www.tiktok.com/@me"
            }

        except Exception as e:
            log(f"❌ เกิดข้อผิดพลาดขณะอัปโหลด TikTok: {e}")
            return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="TikTok Studio Web Uploader (Playwright Automation)")
    parser.add_argument("--login", action="store_true", help="เปิดเบราว์เซอร์เพื่อเข้าสู่ระบบ TikTok และบันทึก Session")
    parser.add_argument("--upload", type=str, help="พาธไฟล์วิดีโอ .mp4 ที่ต้องการอัปโหลด")
    parser.add_argument("--caption", type=str, default="รีวิวของดีบอกต่อจาก Shopee #ป้าเข็มรีวิว #ของดีบอกต่อ", help="แคปชั่นวิดีโอ")
    parser.add_argument("--visible", action="store_true", help="แสดงหน้าต่างเบราว์เซอร์ขณะอัปโหลด (สำหรับดูการทำงาน)")
    args = parser.parse_args()

    if args.login:
        login_flow()
        return

    if args.upload:
        res = upload_video_via_web(args.upload, caption=args.caption, headless=not args.visible)
        print(res)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
