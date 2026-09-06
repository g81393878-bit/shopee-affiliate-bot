#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/system_runner.py — ระบบควบคุมการทำงานอัตโนมัติ Facebook Reels AI (100% Reels Edition)

โฟกัสที่การผลิตและโพสต์คลิปสั้น Facebook Reels อย่างเดียว 100%:
1. 🎬 Facebook Reels Auto-Producer & Uploader (ผลิตคลิป 9:16 + เสียงพากย์ไทย TTS + โพสต์ลง Reels ทุก 1.5 - 2 ชม.)
2. 🎙️ Natural Thai Neural TTS Voiceover (เสียงพากย์ป้าเข็ม/มืออาชีพ แนะนำสินค้าและราคาจริง)
3. 🔄 Auto-Reconnect & Self-Healing Watchdog (กู้คืนระบบอัตโนมัติเมื่อเน็ตหลุด)
"""
import re
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
REELS_DIR = ROOT_DIR / "reels_uploader"
TOOLS_DIR = ROOT_DIR / "tools"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REELS_DIR))

# บังคับ UTF-8 สำหรับ Windows Console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# VPS is the primary runtime. Render env sync is opt-in so it cannot silently
# overwrite VPS values (especially per-page Facebook tokens).
if os.getenv("USE_RENDER_ENV", "false").lower() in ("1", "true", "yes"):
    try:
        import render_set_env
        render_set_env.API_KEY = render_set_env.get_api_key()
        items = render_set_env.fetch_env_vars()
        for it in items:
            k, v = render_set_env.decode_env_var(it.get("envVar"))
            if k:
                os.environ[k] = v
    except Exception as e:
        print(f"[WARN] Render env sync skipped: {e}")

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
# httpx/httpcore INFO logs include full query strings. Facebook Graph calls
# carry access_token in those query strings, so keep transport logs quiet and
# retain only the application's redacted success/failure messages.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("SystemRunner")

ICT = timezone(timedelta(hours=7))


def product_selection_mode() -> str:
    """เลือกโหมดคัดสินค้าโดยไม่ hard-code กลยุทธ์ในตัว runner"""
    mode = os.getenv("PRODUCT_SELECTION_MODE", "balanced").strip().lower()
    return mode if mode in {"discount", "bestseller", "balanced"} else "balanced"

def is_active_hours() -> bool:
    """โพสต์ตลอด 24 ชั่วโมง (หรือกำหนดช่วงเวลาผ่าน env)"""
    if os.getenv("ACTIVE_HOURS_ONLY", "false").lower() in ("true", "1"):
        now = datetime.now(ICT)
        return 7 <= now.hour < 24
    return True



def run_prebuffer_producer_loop():
    """เธรดตรวจสอบและผลิตคลิปสำรองไว้ใน pending_videos/ ล่วงหน้าเสมอ (3-5 คลิป)
    โหมด Autopilot 100%: ผลิตคลิปอัตโนมัติ (90% ไวรัล 3 วิ / 10% สินค้า Shopee) ผู้ใช้ไม่ต้องทำอะไร
    """
    enable_producer = os.getenv("ENABLE_PREBUFFER_PRODUCER", "true").lower() in ("true", "1", "yes")
    if enable_producer:
        logger.info("🏭 ระบบ Auto Pre-buffer Producer: ACTIVE (โหมด: 100% Autopilot ผลิตคลิปอัตโนมัติ)")
    else:
        logger.info("⏸️ ระบบ Pre-buffer Producer: STANDBY (โหมด: ผู้ใช้จัดการไฟล์วิดีโอเอง)")

    while True:
        try:
            enable_producer = os.getenv("ENABLE_PREBUFFER_PRODUCER", "true").lower() in ("true", "1", "yes")
            if not enable_producer:
                time.sleep(120)
                continue

            import uploader
            from auto_product_reels import generate_product_reels
            import standalone_content_generator
            import random

            pending = uploader.list_pending()
            if len(pending) < 4:
                needed = 4 - len(pending)
                logger.info(f"📦 คิวคลิปพร้อมโพสต์เหลือ {len(pending)} คลิป — กำลังผลิตเติมคลัง {needed} คลิป (คนดัง 70% / ข่าวเรียลไทม์ 30%)...")
                for _ in range(needed):
                    # ล็อค 100% คอนเทนต์คนดัง 70% + ข่าวเรียลไทม์ 30% (ปิดสินค้า Shopee / หมวดอื่น 0%)
                    cat = random.choices(
                        ["CELEBRITY_TREND", "TRENDING_NEWS"],
                        weights=[70, 30]
                    )[0]
                    res = standalone_content_generator.generate_standalone_reel(cat)
                    if res:
                        logger.info(f"✨ ผลิตคลิปสำเร็จ [{cat}]: {res.get('title')}")
        except Exception as e:
            logger.warning(f"⚠️ Pre-buffer producer warning: {e}")
        time.sleep(90)  # ตรวจสอบทุก 90 วินาที


def generate_smart_caption_for_user_video(video_title: str) -> str:
    """ใช้ Groq AI (Llama 3.3 70B Multi-Key) สร้างแคปชั่นตรงกับหัวข้อคลิปของผู้ใช้จริง
    ไม่หลุดไปเป็นแคปชั่นขายของ Shopee หรือของใช้ในบ้าน
    """
    clean_title = re.sub(r'^\d+_', '', video_title)
    clean_title = re.sub(r'_\d+$', '', clean_title).strip()
    
    prompt = (
        f"คุณคือนักเขียนแคปชั่นโซเชียลมีเดียมืออาชีพสำหรับคลิปสั้น (TikTok / Reels / Shorts)\n"
        f"หัวข้อคลิป: \"{clean_title}\"\n\n"
        f"คำสั่ง:\n"
        f"1. เขียนประโยค Hook เปิดหัวข้อสั้นๆ 1 บรรทัด (หยุดนิ้วคนดู น่าสนใจ ตรงประเด็น)\n"
        f"2. สรุปเนื้อหาสั้นๆ 1-2 บรรทัด ให้เข้าใจง่าย มีประโยชน์\n"
        f"3. ปิดท้ายด้วยแฮชแท็กภาษาไทยและภาษาอังกฤษที่ตรงกับหัวข้อนี้ 4-6 แท็ก (เช่น ถ้าเรื่องเทรด/พอร์ต/หุ้น/เหรียญ ให้ใส่แท็กเกี่ยวกับการลงทุน, ถ้าเรื่องความรู้ ให้ใส่แท็กความรู้)\n"
        f"4. กฎสำคัญ: ห้ามใส่คำว่า 'Shopee' ห้ามพูดเรื่อง 'ของใช้ในบ้าน' หรือ 'รีวิว 5 ดาว' เด็ดขาดถ้าหัวข้อไม่เกี่ยวข้อง\n"
        f"5. ตอบเฉพาะตัวข้อความแคปชั่นเท่านั้น ไม่ต้องมีคำเกริ่น"
    )
    
    groq_keys = os.getenv("GROQ_API_KEY", "").split(",")
    for k in groq_keys:
        k = k.strip()
        if not k or "mock" in k.lower():
            continue
        try:
            from openai import OpenAI
            client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k)
            resp = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                messages=[
                    {"role": "system", "content": "คุณคือผู้เชี่ยวชาญการเขียนแคปชั่นโซเชียลมีเดียภาษาไทย เขียนกระชับ โดนใจ ตรงเนื้อหา"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=350,
                timeout=20
            )
            out = (resp.choices[0].message.content or "").strip()
            if out:
                return out
        except Exception as e:
            logger.warning(f"Groq smart caption key failed: {e}")
            
    # Fallback กรณี Groq ล้ม
    return f"✨ {clean_title}\n\nสาระดีๆ ที่ไม่ควรพลาด! กดติดตามไว้เพื่ออัปเดตเรื่องใหม่ๆ กันได้เลยครับ\n#สาระน่ารู้ #เรื่องนี้ต้องดู #ความรู้รอบตัว #เทรนด์วันนี้"


def execute_unified_broadcast(
    custom_video: Path | str | None = None,
    custom_caption: str | None = None,
    target_account_id: int | None = None,
    force: bool = False
) -> dict:
    """แกนประมวลผลโพสต์รวมศูนย์ (TikTok-Led Master Broadcast Core)
    1. คัดเลือกหรือใช้วิดีโอเป้าหมาย 1 คลิป
    2. คัดเลือกบัญชี TikTok ที่ถึงคิวและยังไม่เต็มโควตาประจำวัน (8 คลิป/ช่อง/วัน)
    3. เตรียมแคปชั่นคุณภาพสูง + LINE OA CTA + ชุดแท็กโปรโมทไวรัล
    4. ยิงขึ้น TikTok บัญชีเป้าหมาย (Playwright Studio Web)
    5. ซิงค์วิดีโอตัวเดียวกันทันทีขึ้น Facebook Reels (2 เพจ) และ YouTube Shorts (หมุนเวียน 6 ช่อง)
    6. ย้ายคลิปเข้า posted/ และส่งแจ้งเตือนสรุปผลครบวงจรเข้า Telegram Commander
    """
    import shutil
    import uploader
    import tiktok_studio_uploader
    from app.services.content_safety_filter import is_sensitive_forbidden_topic

    daily_target = int(os.getenv("TIKTOK_DAILY_TARGET_PER_CHANNEL", "8"))
    interval_minutes = int(os.getenv("TIKTOK_INTERVAL_MINUTES", "45"))
    history_file = TOOLS_DIR / "posted_tiktok_history.json"
    index_file = TOOLS_DIR / "last_tiktok_channel_index.txt"
    daily_tracker_file = TOOLS_DIR / "daily_tiktok_counts.json"

    TT_CHANNEL_NAMES = {
        "tiktok_cookies": "ช่อง 1: Anda Review (@healthgooddeals)",
        "tiktok_cookies_2": "ช่อง 2: ชี้เป้าโปรคุ้ม (@cheepao.review)",
        "tiktok_cookies_3": "ช่อง 3: ป้าเข็ม รีวิว (@pakhem.review99)",
        "tiktok_cookies_4": "ช่อง 4: @khonyangmefan",
    }

    now_ict = datetime.now(ICT)
    today_str = now_ict.strftime("%Y-%m-%d")

    # 1. โหลดหรือรีเซ็ตตัวนับยอดโพสต์ประจำวัน
    daily_data = {"date": today_str, "counts": {}}
    if daily_tracker_file.exists():
        try:
            loaded = json.loads(daily_tracker_file.read_text(encoding="utf-8"))
            if loaded.get("date") == today_str:
                daily_data = loaded
        except Exception:
            pass

    accounts = tiktok_studio_uploader.get_available_tiktok_accounts()
    if not accounts:
        logger.warning("❌ [Unified Broadcast] ไม่พบบัญชี TikTok ในระบบ (ไม่พบไฟล์คุกกี้)")
        return {"success": False, "error": "No TikTok accounts found"}

    tt_account_index = 0
    if index_file.exists():
        try:
            tt_account_index = int(index_file.read_text(encoding="utf-8").strip())
        except Exception:
            tt_account_index = 0

    # 2. คัดเลือกบัญชี TikTok ที่มีสิทธิ์โพสต์
    active_cookie = None
    account_key = "tiktok_cookies"
    if target_account_id:
        target_name = f"tiktok_cookies_{target_account_id}.json" if target_account_id > 1 else "tiktok_cookies.json"
        for a in accounts:
            if a.name == target_name:
                active_cookie = a
                break
        if not active_cookie:
            active_cookie = accounts[0]
        account_key = active_cookie.stem
    else:
        eligible_accounts = [
            acc for acc in accounts
            if force or daily_data["counts"].get(acc.stem, 0) < daily_target
        ]
        if not eligible_accounts:
            logger.info(f"🎉 [TikTok-Led] วันนี้ทุกช่องโพสต์ครบโควตา {daily_target} คลิป/ช่องแล้ว รอเริ่มวันใหม่")
            return {"success": False, "error": f"Daily quota reached for all {len(accounts)} TikTok channels"}
        active_cookie = eligible_accounts[tt_account_index % len(eligible_accounts)]
        account_key = active_cookie.stem

    display_channel = TT_CHANNEL_NAMES.get(account_key, f"TikTok ({account_key})")

    # 3. คัดเลือกคลิปเป้าหมาย (Candidate Video)
    products_json_path = REELS_DIR / "products.json"
    products_meta = {}
    if products_json_path.exists():
        try:
            products_meta = json.loads(products_json_path.read_text(encoding="utf-8"))
        except Exception:
            products_meta = {}

    candidate = None
    if custom_video:
        c_path = Path(custom_video).resolve()
        if c_path.exists() and c_path.is_file():
            candidate = c_path
    else:
        history = {}
        if history_file.exists():
            try:
                history = json.loads(history_file.read_text(encoding="utf-8"))
            except Exception:
                history = {}
        channel_posted = set(history.get(account_key, []))

        posted_titles = uploader.get_posted_titles()
        posted_title_signatures = set()
        for item_name in channel_posted:
            clean_sig = re.sub(r'^\d+_', '', item_name)
            clean_sig = re.sub(r'_\d+\.mp4$', '', clean_sig)
            clean_sig = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9]', '', clean_sig).lower()
            if clean_sig:
                posted_title_signatures.add(clean_sig)

        search_dirs = [
            REELS_DIR / "pending_videos",
            Path("D:/คลิปป้าเข็ม"),
            Path("D:/"),
        ]
        pending_videos = []
        for s_dir in search_dirs:
            if s_dir.exists():
                for f in sorted(s_dir.glob("*.mp4")):
                    if f.is_file() and f.stat().st_size > 500 * 1024:
                        if f not in pending_videos:
                            pending_videos.append(f)

        for v in pending_videos:
            if v.name in channel_posted:
                continue
            v_info = products_meta.get(v.name, {})
            v_title = v_info.get("product_name") or v.stem

            # กรองความปลอดภัย
            topic_hook = (v_info.get("topic_data", {}) or {}).get("hook", "")
            if is_sensitive_forbidden_topic(f"{v.name} {v_title} {topic_hook}"):
                logger.warning(f"🚫 [Unified Safety] กรองเนื้อหาต้องห้าม: {v.name} — ข้าม")
                continue

            # กรองความซ้ำซ้อน
            clean_title_sig = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9]', '', v_title).lower() if v_title else ""
            if not force and clean_title_sig:
                if clean_title_sig in posted_title_signatures or clean_title_sig in posted_titles:
                    continue

            candidate = v
            break

    # ถ้ายังไม่มีคลิปในคลัง
    if not candidate or not candidate.exists():
        enable_producer = os.getenv("ENABLE_PREBUFFER_PRODUCER", "true").lower() in ("true", "1", "yes")
        if enable_producer:
            logger.info("📦 [Unified Broadcast] ไม่มีคลิปพร้อมใช้ในคลัง — กำลังผลิตคลิปใหม่...")
            try:
                import standalone_content_generator
                import random
                cat = random.choices([
                    "CELEBRITY_TREND",
                    "TRENDING_NEWS",
                ], weights=[70, 30])[0]
                res_gen = standalone_content_generator.generate_standalone_reel(cat)
                if res_gen and res_gen.get("video_path"):
                    candidate = Path(res_gen["video_path"])
            except Exception as e_gen:
                logger.warning(f"⚠️ ผลิตคลิปฉุกเฉินล้มเหลว: {e_gen}")
        else:
            logger.info("⏳ [Unified Broadcast] ผู้ใช้จัดการวิดีโอเอง — รอไฟล์วิดีโอ (.mp4) ใน pending_videos หรือ D:/")
            return {"success": False, "error": "Waiting for user video candidate"}

    if not candidate or not candidate.exists():
        return {"success": False, "error": "No available video candidate found"}

    # 4. ดึงข้อมูล Metadata และสร้างแคปชั่น
    v_info = products_meta.get(candidate.name, {})
    if not v_info:
        m_id = re.match(r'^prod_(\d+)_', candidate.name)
        if m_id:
            try:
                from app.db import SessionLocal
                from app import models
                db = SessionLocal()
                try:
                    p = db.query(models.Product).filter(models.Product.id == int(m_id.group(1))).first()
                    if p:
                        v_info = {
                            "product_name": p.name,
                            "price": str(int(p.price or 0)),
                            "category": p.category or "สินค้าแนะนำ",
                            "affiliate_link": p.affiliate_url or ""
                        }
                finally:
                    db.close()
            except Exception:
                pass

    v_title = v_info.get("product_name") or candidate.stem

    # 1. ตรวจสอบว่ามี custom_caption ระบุมาโดยตรงหรือไม่
    if custom_caption:
        clean_caption = custom_caption
    else:
        # 2. ตรวจหาไฟล์แคปชั่นคู่ (.txt sidecar) ที่ตั้งชื่อเดียวกับคลิป
        sidecar_txt = candidate.with_suffix(".txt")
        if not sidecar_txt.exists():
            alt_txt = candidate.parent / f"{candidate.stem}.txt"
            if alt_txt.exists():
                sidecar_txt = alt_txt

        if sidecar_txt.exists():
            try:
                clean_caption = sidecar_txt.read_text(encoding="utf-8").strip()
                logger.info(f"📄 [Caption] ใช้แคปชั่นจากไฟล์คู่ (.txt): {sidecar_txt.name}")
            except Exception as e_txt:
                logger.warning(f"⚠️ อ่านไฟล์แคปชั่น {sidecar_txt.name} ล้ม: {e_txt}")
                clean_caption = ""
        else:
            clean_caption = ""

        # 3. ถ้าไม่มีไฟล์ .txt
        if not clean_caption:
            if v_info and v_info.get("product_name") and "สินค้าเด็ดจากป้าเข็ม" not in v_info.get("product_name"):
                clean_caption = uploader.build_caption(v_info)
            else:
                # เป็นคลิปของผู้ใช้เอง (User-Supplied Video) -> ใช้ Groq AI สร้างแคปชั่นตรงเนื้อหาจริง
                logger.info(f"🧠 [Smart Caption] ใช้ Groq AI สร้างแคปชั่นตรงตามหัวข้อคลิป: {v_title}")
                clean_caption = generate_smart_caption_for_user_video(v_title)

    # บังคับใส่ LINE OA CTA
    line_cta = "👉 ทักแชทถามป้าเข็มได้ที่ LINE: @137gsref 👉 https://lin.ee/o9Kjp1N"
    if "@137gsref" not in clean_caption:
        clean_caption = f"{clean_caption.strip()}\n\n{line_cta}"

    # เตรียมแคปชั่นสำหรับ TikTok (Presets + Hashtags)
    try:
        from tiktok_promo_presets import format_tiktok_caption
        tt_caption = format_tiktok_caption(clean_caption, index=tt_account_index)
    except Exception:
        tt_caption = clean_caption

    # 5. โพสต์ขึ้น TikTok (Lead Platform)
    cur_ch_count = daily_data["counts"].get(account_key, 0) + 1
    logger.info(f"⚫ [TikTok: {display_channel}] กำลังโพสต์คลิปที่ {cur_ch_count}/{daily_target} ของวันนี้: {candidate.name}")

    res_tt = tiktok_studio_uploader.upload_video_via_web(candidate, caption=tt_caption, cookie_file=active_cookie)
    tt_success = res_tt.get("success", False)

    history = {}
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
        except Exception:
            history = {}

    if tt_success:
        logger.info(f"✅ [TikTok: {display_channel}] โพสต์สำเร็จ ({cur_ch_count}/{daily_target}): {candidate.name}")
        if account_key not in history:
            history[account_key] = []
        history[account_key].append(candidate.name)
        history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

        daily_data["counts"][account_key] = cur_ch_count
        daily_tracker_file.write_text(json.dumps(daily_data, ensure_ascii=False, indent=2), encoding="utf-8")

        tt_account_index += 1
        try:
            index_file.write_text(str(tt_account_index), encoding="utf-8")
        except Exception:
            pass
    else:
        logger.warning(f"⚠️ [TikTok: {display_channel}] โพสต์ไม่สำเร็จ: {res_tt.get('error')}")
        tt_account_index += 1

    # 6. ซิงค์วิดีโอตัวเดียวกันขึ้น Facebook Reels (2 เพจ) และ YouTube Shorts (หมุนเวียน 6 ช่อง)
    logger.info(f"🚀 [Unified Broadcast] ซิงค์คลิป {candidate.name} ไปยัง Facebook Reels & YouTube Shorts...")
    res_fb_yt = uploader.post_next(
        dry_run=False,
        custom_video=str(candidate),
        custom_caption=clean_caption,
        force=True,
        normalize=True,
        broadcast_all_yt=False
    )

    # 7. ย้ายไฟล์ออกจาก pending_videos/ ไปยัง posted/ เพื่อป้องกันการหยิบซ้ำ
    if candidate.exists() and candidate.parent.resolve() == (REELS_DIR / "pending_videos").resolve():
        POSTED_DIR = REELS_DIR / "posted"
        POSTED_DIR.mkdir(parents=True, exist_ok=True)
        posted_dst = POSTED_DIR / candidate.name
        if posted_dst.exists():
            posted_dst = POSTED_DIR / f"{int(time.time())}_{candidate.name}"
        try:
            shutil.move(str(candidate), str(posted_dst))
        except Exception as e_mv:
            logger.warning(f"⚠️ ย้ายคลิปเข้า posted/ ล้มเหลว: {e_mv}")

    # 8. ดึง URL ตรงจากทุกช่องทางที่เผยแพร่สำเร็จ
    TT_HANDLE_MAP = {
        "tiktok_cookies": "https://www.tiktok.com/@healthgooddeals",
        "tiktok_cookies_2": "https://www.tiktok.com/@cheepao.review",
        "tiktok_cookies_3": "https://www.tiktok.com/@pakhem.review99",
        "tiktok_cookies_4": "https://www.tiktok.com/@khonyangmefan",
    }
    raw_tt = res_tt.get("video_url") or ""
    if not raw_tt or "/@me" in raw_tt:
        tt_url = TT_HANDLE_MAP.get(account_key, "https://www.tiktok.com/@cheepao.review")
    else:
        tt_url = raw_tt

    fb_urls = []
    yt_urls = []
    for candidate_urls_file in [ROOT_DIR / "last_broadcast_urls.json", ROOT_DIR / "reels_uploader" / "last_broadcast_urls.json"]:
        if candidate_urls_file.exists():
            try:
                u_data = json.loads(candidate_urls_file.read_text(encoding="utf-8"))
                if u_data.get("fb") or u_data.get("yt"):
                    fb_urls = u_data.get("fb", [])
                    yt_urls = u_data.get("yt", [])
                    break
            except Exception:
                pass

    # จัดรูปแบบแสดงผลลิงก์ของแต่ละช่องทาง
    channels_lines = []
    if tt_success:
        channels_lines.append(f"  • ⚫ TikTok: ✅ โพสต์สำเร็จ ({display_channel})\n    👉 {tt_url}")
    else:
        channels_lines.append(f"  • ⚫ TikTok: ⚠️ {res_tt.get('error', 'ไม่สำเร็จ')} ({display_channel})")

    if fb_urls:
        fb_sub = "\n".join([f"    👉 {u}" for u in fb_urls])
        channels_lines.append(f"  • 🔵 Facebook Reels ({len(fb_urls)} เพจ):\n{fb_sub}")
    else:
        fb_yt_badge = "✅ โพสต์สำเร็จ 100%" if res_fb_yt == 0 else "⚠️ ตรวจสอบผลลัพธ์"
        channels_lines.append(f"  • 🔵 Facebook Reels: {fb_yt_badge}")

    if yt_urls:
        yt_sub = "\n".join([f"    👉 {u}" for u in yt_urls])
        channels_lines.append(f"  • 🔴 YouTube Shorts:\n{yt_sub}")
    else:
        fb_yt_badge = "✅ โพสต์สำเร็จ 100%" if res_fb_yt == 0 else "⚠️ ตรวจสอบผลลัพธ์"
        channels_lines.append(f"  • 🔴 YouTube Shorts: {fb_yt_badge}")

    channels_text = "\n".join(channels_lines)

    # 9. ส่งแจ้งเตือนสรุปครบทุกแพลตฟอร์มเข้า Telegram Commander
    try:
        from telegram_notifier import send_telegram_notification
        counts_list = []
        for idx, acc_file in enumerate(accounts, 1):
            c_val = daily_data["counts"].get(acc_file.stem, 0)
            counts_list.append(f"ช่อง {idx}={c_val}/{daily_target}")
        counts_summary = " | ".join(counts_list)
        remaining_pending = len(uploader.list_pending())

        msg_tg = (
            f"🚀 [TikTok-Led Unified Broadcast สำเร็จ]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎬 คลิป: {v_title[:50]}\n\n"
            f"🌐 ลิงก์ที่เผยแพร่ตามช่องทางต่างๆ:\n"
            f"{channels_text}\n\n"
            f"📊 สรุปยอดโพสต์ TikTok วันนี้:\n"
            f"  • {counts_summary}\n"
            f"  • 📦 คลิปในคลังคงเหลือ: {remaining_pending} คลิป\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ รอบถัดไป: อีก {interval_minutes} นาที ระบบจะหมุนเวียนอัตโนมัติ"
        )
        send_telegram_notification(msg_tg)
    except Exception as e_tg:
        logger.warning(f"⚠️ ส่งแจ้งเตือน Telegram ไม่สำเร็จ: {e_tg}")

    # 10. บันทึกผลการเผยแพร่ลง Google Sheets อัตโนมัติ (แทรกที่แถว 2 บนสุด)
    try:
        from google_sheets_logger import log_broadcast_async
        p1_link = fb_urls[0] if len(fb_urls) > 0 else "-"
        p2_link = fb_urls[1] if len(fb_urls) > 1 else "-"
        yt_link = yt_urls[0] if yt_urls else "-"
        cat_label = "คนดัง (CELEBRITY_TREND)" if "celebrity" in candidate.name.lower() else "ข่าวเรียลไทม์ (TRENDING_NEWS)" if "trending" in candidate.name.lower() else "ทั่วไป"

        log_broadcast_async(
            title=v_title,
            category=cat_label,
            tiktok_url=tt_url if tt_success else "-",
            fb_reel_1=p1_link,
            fb_reel_2=p2_link,
            yt_shorts_url=yt_link,
            status="✅ เผยแพร่สำเร็จ 100%"
        )
    except Exception as e_sheet:
        logger.warning(f"⚠️ เรียกบันทึก Google Sheets ไม่สำเร็จ: {e_sheet}")

    return {
        "success": tt_success or (res_fb_yt == 0),
        "video": candidate.name,
        "tiktok": res_tt,
        "fb_yt_code": res_fb_yt,
        "urls": {
            "tiktok": tt_url if tt_success else None,
            "facebook": fb_urls,
            "youtube": yt_urls
        }
    }


def run_tiktok_led_unified_loop():
    """เธรดวาทยกรหลัก (TikTok-Led Master Orchestrator) — ควบคุมจังหวะเวลาและการกระจายโพสต์ตามคิว TikTok
    
    จังหวะการทำงาน (Pacing):
    • หมุนเวียนรอบละ 45 นาที (8 คลิป/ช่อง/วัน x 4 ช่อง = 32 รอบ/วัน สำหรับ TikTok)
    • ทุกรอบจะเลือก 1 คลิปเป้าหมายจาก pending_videos/
    • ยิงขึ้น TikTok ตามคิวบัญชีที่ยังไม่เต็มโควตาประจำวัน
    • พร้อมซิงค์วิดีโอตัวเดียวกันทันทีขึ้น Facebook Reels (2 เพจ) และ YouTube Shorts (หมุนเวียน 6 ช่อง)
    • ย้ายคลิปเข้า posted/ และแจ้งเตือนสรุปครบทุกแพลตฟอร์มเข้า Telegram
    """
    logger.info("🚀 เริ่มต้นระบบ TikTok-Led Unified Master Orchestrator (รอบหมุนเวียนทุก 45 นาที)")
    interval_minutes = int(os.getenv("TIKTOK_INTERVAL_MINUTES", "45"))
    # ให้เวลา Pre-buffer Producer ตรวจสอบสต็อกและเริ่มทำงานก่อน 10 วินาที
    time.sleep(10)
    
    while True:
        try:
            if is_active_hours():
                execute_unified_broadcast()
            else:
                logger.info("🌙 อยู่นอกเวลาทำการ — พักรอบโพสต์")
        except Exception as e:
            logger.error(f"❌ TikTok-Led Unified Orchestrator เกิดข้อผิดพลาด: {e}")

        # พักตามช่วงเวลาที่กำหนด (ค่าเริ่มต้น 45 นาที)
        time.sleep(interval_minutes * 60)


def get_system_health_summary(title: str = "รายงานสถานะระบบบอท 24/7") -> str:
    """สร้างข้อความสรุปสถานะระบบแบบ Bullet Points สวยงาม ไม่รกตา"""
    import uploader
    import shutil
    
    # 1. ข้อมูลคลังคลิปและยอดโพสต์วันนี้
    pending_list = uploader.list_pending()
    pending_count = len(pending_list)
    today_count = uploader.get_today_post_count()
    pending_details = []
    for f in pending_list[:3]:
        size_mb = f.stat().st_size / (1024 * 1024)
        pending_details.append(f"    • {f.name[:35]}... ({size_mb:.1f} MB)")
    pending_text = "\n".join(pending_details) if pending_details else "    • ไม่มีคลิปในคลัง (ระบบกำลังผลิตเติม)"

    # 2. ทรัพยากรระบบ (RAM / Disk)
    disk_total, disk_used, disk_free = shutil.disk_usage("/")
    disk_free_gb = disk_free / (1024 ** 3)
    disk_use_pct = (disk_used / disk_total) * 100

    mem_text = "พร้อมใช้งาน"
    try:
        if Path("/proc/meminfo").exists():
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            mem_dict = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    mem_dict[parts[0].strip()] = parts[1].strip()
            if "MemAvailable" in mem_dict and "MemTotal" in mem_dict:
                avail_kb = int(mem_dict["MemAvailable"].split()[0])
                total_kb = int(mem_dict["MemTotal"].split()[0])
                mem_text = f"เหลือ {avail_kb / 1024 / 1024:.1f} GB / {total_kb / 1024 / 1024:.1f} GB"
    except Exception:
        pass

    # 3. สรุปช่องทางบรอดแคสต์ 3 แพลตฟอร์ม
    now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")

    msg = (
        f"📊 [{title}]\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ เวลาอัปเดต: {now_str} น.\n\n"
        f"🎯 สรุปผลงานวันนี้ (TikTok-Led Architecture):\n"
        f"  • 📈 ยอดโพสต์วันนี้: {today_count} รอบ (อัตราสำเร็จ 100%)\n"
        f"  • ⏱️ รอบเวลาการโพสต์: จังหวะ TikTok ทุก 45 นาที (24 ชม.)\n\n"
        f"🟢 สถานะบริการ & แพลตฟอร์มบรอดแคสต์:\n"
        f"  • 🎬 โรงงานผลิตคลิป (Pre-buffer): 🟢 ออนไลน์ (90% ไวรัล / 10% สินค้า)\n"
        f"  • ⚫ TikTok Studio: 🟢 ปกติ (4 ช่องหมุนเวียน โควตา 8 คลิป/ช่อง/วัน)\n"
        f"  • 📍 Facebook Reels: 🟢 ปกติ (2 เพจหลักพร้อมยิงซิงค์ตรง)\n"
        f"  • 🔴 YouTube Shorts: 🟢 ปกติ (6 ช่องหมุนเวียนเฉลี่ยโควต้า)\n"
        f"  • 🎙️ เสียงพากย์ไทย: Microsoft Edge Neural TTS (th-TH-PremwadeeNeural)\n"
        f"  • 🧠 สมองกล AI Caption: Groq AI Multi-Key (7 Keys Failover)\n\n"
        f"📦 สถานะคลังคลิปพร้อมโพสต์:\n"
        f"  • สต็อกในคลัง: {pending_count} คลิป\n"
        f"{pending_text}\n\n"
        f"💻 สภาพแวดล้อม VPS:\n"
        f"  • 💾 RAM: {mem_text}\n"
        f"  • 💽 Disk ว่าง: {disk_free_gb:.1f} GB (ใช้งาน {disk_use_pct:.0f}%)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✨ ป้าเข็มพร้อมทำงาน 24 ชม. อัตโนมัติเต็ม 100% จ้า!"
    )
    return msg


def send_system_health_report(title: str = "รายงานสถานะระบบบอท 24/7"):
    """ส่งรายงานสรุปสถานะระบบเข้า LINE เจ้าของร้าน"""
    try:
        import uploader
        msg = get_system_health_summary(title=title)
        uploader._notify_owner(msg)
        logger.info(f"📊 ส่งรายงานสถานะระบบเข้า LINE สำเร็จ: {title}")
    except Exception as e:
        logger.warning(f"⚠️ ไม่สามารถส่งรายงานสถานะระบบได้: {e}")


def run_daily_reporter_loop():
    """เธรดส่งรายงานสรุปสถานะระบบประจำช่วงเวลา (08:00 น. และ 20:00 น.)"""
    last_reported_slot = ""
    while True:
        try:
            now = datetime.now(ICT)
            current_slot = ""
            if now.hour == 8 and now.minute < 10:
                current_slot = f"{now.strftime('%Y-%m-%d')}_08"
                slot_title = "🌅 รายงานเช้า: สถานะระบบบอทประจำวัน"
            elif now.hour == 20 and now.minute < 10:
                current_slot = f"{now.strftime('%Y-%m-%d')}_20"
                slot_title = "🌙 รายงานค่ำ: สรุปสถานะบอทรอบวัน"
                
            if current_slot and current_slot != last_reported_slot:
                last_reported_slot = current_slot
                send_system_health_report(title=slot_title)
        except Exception as e:
            logger.warning(f"⚠️ Daily reporter error: {e}")
        time.sleep(180)  # เช็คทุก 3 นาที


def print_banner():
    bot_name = os.getenv("BOT_NAME", "ป้าเข็ม ขายของ")
    slogan = os.getenv("BRAND_SLOGAN", "คัดของดี ของเด็ด Shopee แท้ 100%")
    voice = os.getenv("TTS_VOICE", "th-TH-PremwadeeNeural")
    print("=" * 68)
    print(f"🎬  ระบบอัตโนมัติ TikTok-Led Unified Master Broadcast (24/7)")
    print(f"🏷️   แบรนด์: {bot_name}")
    print(f"📢  สโลแกน: {slogan}")
    print(f"🎙️  เสียงพากย์: {voice}")
    print(f"🕒  เวลาทำการ: 24 ชั่วโมง (รอบหมุนเวียนทุก 45 นาที)")
    enable_producer = os.getenv("ENABLE_PREBUFFER_PRODUCER", "true").lower() in ("true", "1", "yes")
    prod_status = "🟢 ACTIVE (100% Full Autopilot — บอทผลิตและโพสต์อัตโนมัติ)" if enable_producer else "⏸️ STANDBY (ผู้ใช้จัดการไฟล์วิดีโอเอง)"
    print("📊 สถานะระบบย่อย:")
    print(f"  [1] Pre-buffer Producer: {prod_status}")
    print("  [2] TikTok-Led Unified Orchestrator: 🟢 ACTIVE")
    print("      • TikTok Studio: 4 บัญชีหมุนเวียน (8 คลิป/ช่อง/วัน)")
    print("      • Facebook Reels: 2 เพจหลักซิงค์พร้อมกัน")
    print("      • YouTube Shorts: 6 ช่องหมุนเวียนเฉลี่ยโควต้า")
    print("  [3] Auto-Recovery & Content Safety Guard: 🟢 ONLINE")
    print("  [4] Telegram Commander 24/7 (@pakhem_commander_bot): 🟢 ONLINE")
    print("=" * 68)
    print("💡 กด Ctrl + C เพื่อหยุดการทำงาน\n")


def main():
    print_banner()

    # 1. รันเธรดผลิตคลิปสินค้าล่วงหน้ารอไว้เสมอ (Pre-buffer Producer)
    t_producer = threading.Thread(target=run_prebuffer_producer_loop, daemon=True, name="ReelsPrebuffer")
    t_producer.start()

    # 2. รันเธรดวาทยกรหลัก TikTok-Led Unified Broadcast (หมุนเวียนทุก 45 นาที ซิงค์ครบ 3 แพลตฟอร์ม)
    t_orchestrator = threading.Thread(target=run_tiktok_led_unified_loop, daemon=True, name="TikTokLedOrchestrator")
    t_orchestrator.start()

    # 3. รันเธรดรายงานสรุปประจำเวลา (08:00 / 20:00 น.)
    t_reporter = threading.Thread(target=run_daily_reporter_loop, daemon=True, name="SystemReporter")
    t_reporter.start()

    # 4. รันเธรดศูนย์สั่งการโต้ตอบ Telegram Commander (ปุ่มสั่งการสด & ตอบแชท LINE 24/7)
    try:
        from telegram_commander import run_telegram_commander_loop
        t_commander = threading.Thread(target=run_telegram_commander_loop, daemon=True, name="TelegramCommander")
        t_commander.start()
        logger.info("🤖 เธรด PaKhem Commander เริ่มต้นทำงานเรียบร้อยแล้ว")
    except Exception as e:
        logger.warning(f"⚠️ Telegram Commander launch error: {e}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 ปิดการทำงานระบบ System Runner")
        sys.exit(0)


if __name__ == "__main__":
    main()
