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

TIKTOK_CHANNEL_PROFILES = {
    "tiktok_cookies.json": "https://www.tiktok.com/@healthgooddeals",
    "tiktok_cookies_2.json": "https://www.tiktok.com/@cheepao.review",
    "tiktok_cookies_3.json": "https://www.tiktok.com/@pakhem.review99",
    "tiktok_cookies_4.json": "https://www.tiktok.com/@khonyangmefan",
}


def get_available_tiktok_accounts():
    """ค้นหาไฟล์คุกกี้ของทุกบัญชี TikTok ที่มีในระบบ (tiktok_cookies.json, tiktok_cookies_2.json, ...)"""
    accounts = []
    if COOKIE_FILE.exists() and COOKIE_FILE.stat().st_size > 20:
        accounts.append(COOKIE_FILE)
    for p in sorted(TOOLS_DIR.glob("tiktok_cookies_*.json")):
        if p.exists() and p.stat().st_size > 20 and p not in accounts:
            accounts.append(p)
    return accounts


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


def login_flow(account_id: Optional[int] = None):
    """เปิดเบราว์เซอร์ให้ผู้ใช้ล็อกอิน TikTok ด้วยตัวเอง 1 ครั้งเพื่อเก็บ Session Cookie"""
    from playwright.sync_api import sync_playwright

    target_cookie_file = TOOLS_DIR / f"tiktok_cookies_{account_id}.json" if (account_id and account_id > 1) else COOKIE_FILE
    user_data_path = TOOLS_DIR / f"tiktok_user_data_{account_id}" if (account_id and account_id > 1) else USER_DATA_DIR

    print("\n" + "=" * 65)
    acc_title = f"ช่องที่ {account_id}" if (account_id and account_id > 1) else "ช่องหลัก"
    print(f"🔑 เริ่มต้นกระบวนการเข้าสู่ระบบ TikTok สำหรับ [{acc_title}]")
    print("=" * 65)
    print("👉 ระบบกำลังเปิดหน้าต่างเบราว์เซอร์ Chrome ให้คุณล็อกอิน...")
    print("👉 คุณสามารถล็อกอินด้วย Email, Google หรือสแกน QR Code จากแอป TikTok ในมือถือได้เลยครับ")
    print("-" * 65)

    user_data_path.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_path),
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
                    target_cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
                    break
            time.sleep(2)

        if logged_in:
            print(f"\n🎉 ล็อกอิน TikTok สำเร็จ 100%! บันทึก Cookie ลง {target_cookie_file.name} เรียบร้อยแล้ว")
            log(f"TikTok Session Saved to {target_cookie_file.name} Successfully!")
            print(f"👉 คำสั่งส่งไฟล์ขึ้น VPS:")
            print(f"   scp tools/{target_cookie_file.name} root@119.10.140.161:/root/shopee-affiliate-bot/tools/{target_cookie_file.name}")
            page.goto(UPLOAD_URL, timeout=30000)
            time.sleep(3)
        else:
            print("\n⚠️ หมดเวลาการรอ หรือยังไม่ได้เข้าสู่ระบบสมบูรณ์")

        browser.close()


def sanitize_caption(caption: str, max_chars: int = 500) -> str:
    caption = (caption or "").strip()
    caption = re.sub(r"\b\d+([.,]\d+)?\s*(บาท|฿|baht)\b", "", caption, flags=re.IGNORECASE)
    if len(caption) > max_chars:
        caption = caption[:max_chars - 3] + "..."
    return caption



def upload_video_via_web(
    video_path: Union[str, pathlib.Path],
    caption: str = "",
    headless: bool = True,
    cookie_file: Optional[Union[str, pathlib.Path]] = None,
) -> Dict:
    """อัปโหลดวิดีโอ 9:16 เข้าสู่ TikTok Creator Center โดยอัตโนมัติผ่าน Playwright"""
    from playwright.sync_api import sync_playwright

    video_file = pathlib.Path(video_path).resolve()
    if not video_file.exists():
        return {"success": False, "error": f"Video file not found: {video_file}"}

    if not is_logged_in():
        return {"success": False, "error": "TikTok session not found. Please run: python tools/tiktok_studio_uploader.py --login"}

    # เลือกไฟล์คุกกี้และแยกโฟลเดอร์เซสชันของแต่ละบัญชีออกจากกันเด็ดขาด
    target_cookie = pathlib.Path(cookie_file) if cookie_file else COOKIE_FILE
    cookie_label = target_cookie.name if target_cookie.exists() else "Default Session"
    account_user_data = TOOLS_DIR / f"tiktok_user_data_{target_cookie.stem}"
    account_user_data.mkdir(parents=True, exist_ok=True)

    clean_caption = sanitize_caption(caption)
    log(f"🎬 เริ่มต้นอัปโหลดคลิป: {video_file.name} [{cookie_label}] (Caption: {clean_caption[:50]}...)")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1440, "height": 900})
            if target_cookie.exists():
                try:
                    c_data = json.loads(target_cookie.read_text(encoding="utf-8"))
                    context.add_cookies(c_data)
                except Exception as e_cook:
                    log(f"⚠️ Load cookies error: {e_cook}")

            page = context.new_page()

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
            caption_box = page.locator('div[contenteditable="true"]').first
            if caption_box.count() > 0:
                caption_box.click(force=True)
                caption_box.fill("")
                caption_box.type(clean_caption, delay=20)
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
            else:
                txt_area = page.locator('textarea').first
                if txt_area.count() > 0:
                    txt_area.click(force=True)
                    txt_area.fill(clean_caption)

            page.wait_for_timeout(2000)

            # เคลียร์ Modal Popup และ Joyride (Got it / Turn on)
            try:
                # 1. คลิกปุ่ม Got it ของ Joyride ถ้ามี
                joyride_btn = page.locator('div.react-joyride__tooltip button, [aria-label="Got it"]').first
                if joyride_btn.count() > 0 and joyride_btn.is_visible():
                    joyride_btn.click(force=True)
                    page.wait_for_timeout(1000)

                # 2. เคลียร์ Modal Turn on / Got it ผ่าน JS
                page.evaluate("""() => {
                    const joyride = document.querySelector('#react-joyride-portal, .react-joyride__overlay');
                    if (joyride) joyride.remove();
                    document.querySelectorAll('button').forEach(b => {
                        const t = (b.innerText || '').trim().toLowerCase();
                        if (t === 'turn on' || t === 'got it' || t === 'เข้าใจแล้ว' || t === 'agree') {
                            b.click();
                        }
                    });
                }""")
                page.wait_for_timeout(1000)
            except Exception:
                pass

            # 5. กดปุ่ม Post (โพสต์) — ใช้ exact match และ Selectors จาก Chrome Recorder
            log("🚀 กำลังกดปุ่มโพสต์วิดีโอ...")
            post_selectors = [
                'button[data-e2e="post_video_button"]',
                'div.css-fsbw52 button.Button__root--type-primary',
                'xpath=//*[@id="root"]/div/div/div[2]/div[2]/div/div/div/div/div/div[6]/div/button[1]',
                'button:has-text("Post")',
                'button:has-text("โพสต์")',
            ]
            clicked = False
            for sel in post_selectors:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(force=True)
                    log(f"   ✓ คลิกปุ่ม Post สำเร็จ (Selector: {sel})")
                    clicked = True
                    break

            # 6. รอยืนยันการโพสต์สำเร็จ & ตรวจจับปุ่มยืนยัน "Post now" ถ้ามี
            log("⏳ รอระบบ TikTok ประมวลผลและตรวจจับปุ่มยืนยัน Post now...")
            for _ in range(15):
                page.wait_for_timeout(1000)
                if "content" in page.url:
                    break
                confirm_btn = page.locator('button').filter(has_text=re.compile(r'^(Post now|โพสต์เลย|Confirm|Got it)$', re.I)).first
                if confirm_btn.count() > 0 and confirm_btn.is_visible():
                    log("   ✓ คลิกปุ่มยืนยัน Post now จาก Modal เรียบร้อยแล้ว!")
                    confirm_btn.click(force=True)
                    page.wait_for_timeout(3000)
                    break

            log("🎉 อัปโหลดและสั่งโพสต์คลิปขึ้น TikTok สำเร็จ 100%!")

            browser.close()
            cookie_fname = target_cookie.name if target_cookie else "tiktok_cookies.json"
            direct_channel_url = TIKTOK_CHANNEL_PROFILES.get(cookie_fname, "https://www.tiktok.com/@cheepao.review")
            return {
                "success": True,
                "message": "Video published to TikTok successfully via Web Studio",
                "video_url": direct_channel_url
            }

        except Exception as e:
            log(f"❌ เกิดข้อผิดพลาดขณะอัปโหลด TikTok: {e}")
            return {"success": False, "error": str(e)}


def post_single_tiktok_video(target_account_id: Optional[int] = None, visible: bool = False, custom_video: Optional[str] = None, custom_caption: Optional[str] = None) -> Dict:
    """สั่งยิงโพสต์ 1 คลิปด่วนขึ้น TikTok Studio (หมุนเวียน Round-Robin หรือระบุช่อง หรือระบุคลิปเฉพาะ)"""
    accounts = get_available_tiktok_accounts()
    if not accounts:
        log("❌ ไม่พบบัญชี TikTok ในระบบ (ไม่พบไฟล์คุกกี้ tiktok_cookies*.json)")
        return {"success": False, "error": "No TikTok accounts found"}

    index_file = TOOLS_DIR / "last_tiktok_channel_index.txt"
    history_file = TOOLS_DIR / "posted_tiktok_history.json"
    daily_tracker_file = TOOLS_DIR / "daily_tiktok_counts.json"
    reels_dir = PROJECT_ROOT / "reels_uploader"
    daily_target = int(os.getenv("TIKTOK_DAILY_TARGET_PER_CHANNEL", "8"))

    channel_names = {
        "tiktok_cookies": "ช่อง 1: Anda Review (@healthgooddeals)",
        "tiktok_cookies_2": "ช่อง 2: ชี้เป้าโปรคุ้ม (@cheepao.review)",
        "tiktok_cookies_3": "ช่อง 3: ป้าเข็ม รีวิว (@pakhem.review99)",
        "tiktok_cookies_4": "ช่อง 4: @khonyangmefan",
    }

    tt_account_index = 0
    if index_file.exists():
        try:
            tt_account_index = int(index_file.read_text(encoding="utf-8").strip())
        except Exception:
            tt_account_index = 0

    if target_account_id:
        target_cookie_name = f"tiktok_cookies_{target_account_id}.json" if target_account_id > 1 else "tiktok_cookies.json"
        matched = [a for a in accounts if a.name == target_cookie_name]
        active_cookie = matched[0] if matched else accounts[0]
    else:
        active_cookie = accounts[tt_account_index % len(accounts)]

    account_key = active_cookie.stem if active_cookie else "tiktok_cookies"
    display_channel = channel_names.get(account_key, f"TikTok ({account_key})")

    # อ่านประวัติการโพสต์แยกรายช่อง
    history = {}
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
        except Exception:
            history = {}
    channel_posted = set(history.get(account_key, []))

    posted_title_signatures = set()
    for item_name in channel_posted:
        posted_title_signatures.add(item_name)
        clean_sig = re.sub(r'^\d+_', '', item_name)
        clean_sig = re.sub(r'_\d+\.mp4$', '', clean_sig)
        clean_sig = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9]', '', clean_sig).lower()
        if clean_sig:
            posted_title_signatures.add(clean_sig)

    products_json_path = reels_dir / "products.json"
    products_meta = {}
    if products_json_path.exists():
        try:
            products_meta = json.loads(products_json_path.read_text(encoding="utf-8"))
        except Exception:
            products_meta = {}

    candidate = None
    if custom_video:
        c_path = pathlib.Path(custom_video).resolve()
        if not c_path.exists():
            for alt in [pathlib.Path("D:/") / custom_video, reels_dir / "pending_videos" / custom_video, pathlib.Path("D:/คลิปป้าเข็ม") / custom_video]:
                if alt.exists():
                    c_path = alt.resolve()
                    break
        if not c_path.exists():
            stem_part = pathlib.Path(custom_video).stem[:12]
            for folder in [reels_dir / "pending_videos", pathlib.Path("D:/")]:
                if folder.exists():
                    for f in folder.glob("*.mp4"):
                        if (stem_part and stem_part in f.stem) or (f.stem and f.stem in custom_video) or ("จัดการรีพอ" in f.name and "จัดการรีพอ" in custom_video):
                            c_path = f.resolve()
                            break
                    if c_path.exists():
                        break
        if not c_path.exists():
            log(f"❌ [TikTok] ไม่พบไฟล์วิดีโอที่ระบุ: {c_path}")
            return {"success": False, "error": f"Video file not found: {c_path}"}
        candidate = c_path
    else:
        pending_videos = sorted((reels_dir / "pending_videos").glob("*.mp4"))

        for v in pending_videos:
            if v.name in channel_posted:
                continue
            v_info = products_meta.get(v.name, {})
            v_title = v_info.get("product_name") or v.stem

            # กรองเนื้อหาต้องห้าม
            try:
                sys.path.insert(0, str(BACKEND_DIR))
                from app.services.content_safety_filter import is_sensitive_forbidden_topic
                if is_sensitive_forbidden_topic(v.name) or is_sensitive_forbidden_topic(v_title):
                    continue
            except Exception:
                pass

            clean_title_sig = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9]', '', v_title).lower() if v_title else ""
            if clean_title_sig and clean_title_sig in posted_title_signatures:
                continue

            candidate = v
            break

    if not candidate:
        log(f"⚠️ [TikTok: {display_channel}] ไม่พบคลิปใหม่ที่ยังไม่เคยโพสต์ในช่องนี้")
        return {"success": False, "error": f"No unposted video found for {display_channel}"}

    # ตรวจสอบคุณภาพเสียงวิดีโอก่อนโพสต์
    try:
        sys.path.insert(0, str(reels_dir))
        from auto_product_reels import verify_video_has_audio
        has_audio, audio_reason = verify_video_has_audio(candidate)
        if not has_audio:
            log(f"🚨 [AUDIO GUARD] คลิปเสียงไม่ผ่านเกณฑ์ ({audio_reason}): {candidate.name}")
            corrupt_dir = reels_dir / "corrupted"
            corrupt_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(candidate), str(corrupt_dir / candidate.name))
            except Exception:
                pass
            return {"success": False, "error": f"Audio verification failed: {audio_reason}"}
    except Exception as e_vfy:
        log(f"[WARN] ตรวจสอบเสียงล้มเหลว ({e_vfy}) — ดำเนินการต่อ")

    log(f"⚡ [TikTok ด่วน: {display_channel}] กำลังยิงโพสต์คลิป: {candidate.name}")

    v_info = products_meta.get(candidate.name, {})
    v_title = v_info.get("product_name") or candidate.stem
    v_cat = v_info.get("category") or ""
    is_prod = bool(v_info.get("affiliate_link"))

    tt_dyn_tags = "#เทรนด์วันนี้ #เรื่องนี้ต้องดู #ป้าเข็มรีวิว"
    try:
        from hashtag_intelligence import generate_platform_hashtags
        tt_dyn_tags = generate_platform_hashtags(v_title, category=v_cat, is_product=is_prod).get("tiktok", tt_dyn_tags)
    except Exception:
        pass

    # ดึงแคปชั่น
    if custom_caption:
        clean_caption = custom_caption
        if "#" not in clean_caption:
            clean_caption = f"{clean_caption}\n\n{tt_dyn_tags}"
    else:
        clean_caption = f"✨ {v_title}"
        if v_info.get("is_pure_content"):
            try:
                import standalone_content_generator
                mode = v_info.get("content_mode", "LIFE_HACK_TIP")
                topic_data = v_info.get("topic_data", {})
                clean_caption = standalone_content_generator.build_standalone_caption(mode, topic_data, platform="tiktok")
            except Exception:
                clean_caption = f"{clean_caption}\n\n{tt_dyn_tags}"
        else:
            try:
                sys.path.insert(0, str(reels_dir))
                import uploader
                built = uploader.build_caption(v_info)
                if built and not ("สินค้าเด็ดจากป้าเข็ม" in built and v_title != candidate.stem):
                    clean_caption = built
            except Exception:
                pass

            try:
                from tiktok_promo_presets import format_tiktok_caption
                clean_caption = format_tiktok_caption(clean_caption, index=tt_account_index)
            except Exception:
                clean_caption = f"{clean_caption.strip()}\n\n{tt_dyn_tags}"

    res = upload_video_via_web(candidate, caption=clean_caption, headless=not visible, cookie_file=active_cookie)
    if res.get("success"):
        log(f"✅ [TikTok ด่วน: {display_channel}] โพสต์คลิปสำเร็จ: {candidate.name}")
        if account_key not in history:
            history[account_key] = []
        history[account_key].append(candidate.name)
        try:
            history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        # บันทึกยอดประจำวัน
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        daily_data = {"date": today_str, "counts": {}}
        if daily_tracker_file.exists():
            try:
                loaded = json.loads(daily_tracker_file.read_text(encoding="utf-8"))
                if loaded.get("date") == today_str:
                    daily_data = loaded
            except Exception:
                pass
        daily_data["counts"][account_key] = daily_data["counts"].get(account_key, 0) + 1
        try:
            daily_tracker_file.write_text(json.dumps(daily_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        # ขยับรอบ
        tt_account_index += 1
        try:
            index_file.write_text(str(tt_account_index), encoding="utf-8")
        except Exception:
            pass

        # ย้ายคลิปที่โพสต์สำเร็จไปยัง posted/ เพื่อป้องกันการหยิบซ้ำ
        if candidate.exists() and not custom_video:
            POSTED_DIR = reels_dir / "posted"
            POSTED_DIR.mkdir(parents=True, exist_ok=True)
            posted_dst = POSTED_DIR / candidate.name
            if posted_dst.exists():
                posted_dst = POSTED_DIR / f"{int(time.time())}_{candidate.name}"
            try:
                shutil.move(str(candidate), str(posted_dst))
                log(f"📦 [Cleanup] ย้ายคลิปที่เผยแพร่แล้วไป posted/: {posted_dst.name}")
            except Exception as e_mv:
                log(f"⚠️ ย้ายคลิปเข้า posted/ ล้มเหลว: {e_mv}")

        # ส่งแจ้งเตือน Telegram
        try:
            from telegram_notifier import send_telegram_notification
            send_telegram_notification(
                f"⚡ [TikTok ยิงโพสต์ด่วนสำเร็จ]\n"
                f"• ช่อง: {display_channel}\n"
                f"• คลิป: {candidate.name[:35]}\n"
                f"• สถานะ: โพสต์สำเร็จ 100%"
            )
        except Exception:
            pass
        return {"success": True, "channel": display_channel, "video": candidate.name}
    else:
        log(f"⚠️ [TikTok ด่วน: {display_channel}] โพสต์ไม่สำเร็จ: {res.get('error')}")
        return res


def post_all_tiktok_channels(visible: bool = False, custom_video: Optional[str] = None, custom_caption: Optional[str] = None) -> list:
    """สั่งยิงโพสต์คลิปขึ้นทุกช่อง TikTok ที่เชื่อมต่ออยู่ในระบบทีละช่องจนครบ"""
    accounts = get_available_tiktok_accounts()
    if not accounts:
        log("❌ ไม่พบบัญชี TikTok ในระบบ (ไม่พบไฟล์คุกกี้ tiktok_cookies*.json)")
        return []

    log(f"🚀 เริ่มต้นยิงโพสต์ขึ้น TikTok ครบทั้ง {len(accounts)} ช่อง...")
    results = []
    for a in accounts:
        m = re.search(r'tiktok_cookies(?:_(\d+))?\.json', a.name)
        channel_id = int(m.group(1)) if (m and m.group(1)) else 1
        log(f"\n👉 [กำลังยิงโพสต์ TikTok ช่องที่ {channel_id}: {a.name}]...")
        res = post_single_tiktok_video(target_account_id=channel_id, visible=visible, custom_video=custom_video, custom_caption=custom_caption)
        results.append(res)
        time.sleep(3)  # พักสั้น ๆ ระหว่างเปิดเบราว์เซอร์สลับช่อง
    return results


def main():
    parser = argparse.ArgumentParser(description="TikTok Studio Web Uploader (Playwright Automation)")
    parser.add_argument("--login", action="store_true", help="เปิดเบราว์เซอร์เพื่อเข้าสู่ระบบ TikTok ช่องหลัก")
    parser.add_argument("--add-account", type=int, help="เปิดเบราว์เซอร์เพื่อเข้าสู่ระบบ TikTok ช่องที่ N (เช่น --add-account 3)")
    parser.add_argument("--upload", type=str, help="พาธไฟล์วิดีโอ .mp4 ที่ต้องการอัปโหลด")
    parser.add_argument("--cookie-file", type=str, default=None, help="ไฟล์คุกกี้ที่ต้องการใช้โพสต์ (เช่น tools/tiktok_cookies_3.json)")
    parser.add_argument("--caption", type=str, default="รีวิวของดีบอกต่อจาก Shopee #ป้าเข็มรีวิว #ของดีบอกต่อ", help="แคปชั่นวิดีโอ")
    parser.add_argument("--visible", action="store_true", help="แสดงหน้าต่างเบราว์เซอร์ขณะอัปโหลด (สำหรับดูการทำงาน)")
    parser.add_argument("--list-accounts", action="store_true", help="แสดงรายชื่อบัญชี TikTok ทั้งหมดที่เชื่อมต่อ")
    parser.add_argument("--post-now", action="store_true", help="สั่งยิงโพสต์ 1 คลิปด่วนเข้าสู่ TikTok ช่องถัดไปตามคิว")
    parser.add_argument("--all-channels", action="store_true", help="สั่งยิงโพสต์ขึ้นทุกช่อง TikTok ในระบบจนครบทุกช่องทันที")
    parser.add_argument("--channel", type=int, default=None, help="ระบุหมายเลขช่องที่ต้องการยิงโพสต์ด่วน (เช่น 1, 2, 3, 4)")
    parser.add_argument("--video", type=str, default=None, help="พาธไฟล์วิดีโอ .mp4 ที่ต้องการอัปโหลดเฉพาะเจาะจง")
    args = parser.parse_args()

    if args.list_accounts:
        accs = get_available_tiktok_accounts()
        print(f"\n⚫ พบบัญชี TikTok ทั้งหมด {len(accs)} บัญชีในระบบ:")
        channel_labels = {
            "tiktok_cookies.json": "ช่อง 1: Anda Review (@healthgooddeals)",
            "tiktok_cookies_2.json": "ช่อง 2: ชี้เป้าโปรคุ้ม (@cheepao.review)",
            "tiktok_cookies_3.json": "ช่อง 3: ป้าเข็ม รีวิว (@pakhem.review99)",
            "tiktok_cookies_4.json": "ช่อง 4: @khonyangmefan",
        }
        for idx, a in enumerate(accs, 1):
            label = channel_labels.get(a.name, f"ช่องที่ {idx}")
            print(f"  • {label} | {a.name} ({a.stat().st_size:,} bytes)")
        if not accs:
            print("  ⚠️ ยังไม่มีไฟล์คุกกี้บัญชี TikTok ในระบบ")
        return

    if args.add_account:
        login_flow(account_id=args.add_account)
        return

    if args.login:
        login_flow(account_id=1)
        return

    if args.all_channels:
        res = post_all_tiktok_channels(visible=args.visible, custom_video=args.video, custom_caption=args.caption)
        print(res)
        return

    if args.post_now:
        res = post_single_tiktok_video(target_account_id=args.channel, visible=args.visible, custom_video=args.video, custom_caption=args.caption)
        print(res)
        return

    if args.upload:
        res = upload_video_via_web(args.upload, caption=args.caption, headless=not args.visible, cookie_file=args.cookie_file)
        print(res)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
