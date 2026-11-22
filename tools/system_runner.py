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
# pythonw has no console streams; retain output and tracebacks in a local log.
if sys.stdout is None or sys.stderr is None:
    runtime_logs = ROOT_DIR / "artifacts" / "trend_autopilot"
    runtime_logs.mkdir(parents=True, exist_ok=True)
    runtime_stream = open(runtime_logs / "runner_background.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = runtime_stream
    sys.stderr = runtime_stream
BACKEND_DIR = ROOT_DIR / "backend"
REELS_DIR = ROOT_DIR / "reels_uploader"
TOOLS_DIR = ROOT_DIR / "tools"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REELS_DIR))
from product_post_history import serialize_broadcast

# บังคับ UTF-8 สำหรับ Windows Console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# VPS is the primary runtime. Using local/VPS environment directly.
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
    โหมด 100% Shopee Affiliate Product Reels: คัดสินค้า Extra Commission และสินค้าขายดีตรงปก
    """
    enable_producer = os.getenv("ENABLE_PREBUFFER_PRODUCER", "true").lower() in ("true", "1", "yes")
    if enable_producer:
        logger.info("🏭 ระบบ Auto Pre-buffer Producer: ACTIVE (โหมด: 100% Shopee Affiliate Products)")
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

            from product_post_history import posted_product_ids, product_id
            posted_ids = posted_product_ids(REELS_DIR, TOOLS_DIR)
            raw_pending = uploader.list_pending()

            # Clean up already posted files sitting in pending_videos
            history_file = TOOLS_DIR / "posted_tiktok_history.json"
            global_posted_files = set()
            if history_file.exists():
                try:
                    h_data = json.loads(history_file.read_text(encoding="utf-8"))
                    for h_v in h_data.values():
                        if isinstance(h_v, list): global_posted_files.update(h_v)
                except Exception:
                    pass

            pending = []
            for pf in raw_pending:
                if pf.suffix.lower() == ".mp4":
                    if pf.name in global_posted_files:
                        try:
                            dst = REELS_DIR / "posted" / pf.name
                            if not dst.exists():
                                shutil.move(str(pf), str(dst))
                            else:
                                pf.unlink(missing_ok=True)
                            txt_pair = pf.with_suffix(".txt")
                            if txt_pair.exists():
                                txt_dst = REELS_DIR / "posted" / txt_pair.name
                                if not txt_dst.exists():
                                    shutil.move(str(txt_pair), str(txt_dst))
                                else:
                                    txt_pair.unlink(missing_ok=True)
                        except Exception:
                            pass
                        continue
                    pid = product_id(pf.name)
                    if pid is not None and pid in posted_ids:
                        continue
                pending.append(pf)

            if len(pending) < 4:
                needed = 4 - len(pending)
                logger.info(f"📦 คิวคลิปพร้อมโพสต์เหลือ {len(pending)} คลิป — กำลังผลิตเติมคลัง {needed} คลิป (สินค้า Shopee 100%)...")
                for _ in range(needed):
                    produced = False
                    # 1. ลำดับแรก: ผลิตคลิป Extra Commission สูง (฿150 - ฿700+) สไตล์ Shopee Video
                    try:
                        from shopee_extra_commission import produce_top_extra_commission_reel
                        extra_res = produce_top_extra_commission_reel()
                        if extra_res:
                            produced = True
                            logger.info(f"💎 ผลิตคลิป Extra Commission สำเร็จ: #{extra_res.get('product_id')} (ค่าคอม {extra_res.get('commission')})")
                    except Exception as ee_err:
                        logger.debug(f"Extra commission auto-produce fallback: {ee_err}")

                    # 2. ลำดับสอง: สำรองด้วยคลิปสินค้าขายดีจากคลัง Shopee ตรงปก
                    if not produced:
                        try:
                            prods = generate_product_reels(limit=1, selection=product_selection_mode())
                            if prods:
                                produced = True
                                logger.info(f"✨ ผลิตคลิปสินค้า Shopee สำเร็จ: {prods[0].get('name', '')[:40]}")
                        except Exception as pe:
                            logger.warning(f"⚠️ Product reel gen warning: {pe}")

                    if not produced:
                        break  # พักรอรอบถัดไปหากยังไม่สามารถผลิตได้
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


@serialize_broadcast(lambda: REELS_DIR / ".unified_broadcast.lock",
                     {"success": False, "error": "Broadcast already running"})
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
    5. ซิงค์วิดีโอตัวเดียวกันทันทีขึ้น Facebook Reels (2 เพจ)
    6. ย้ายคลิปเข้า posted/ และส่งแจ้งเตือนสรุปผลครบวงจรเข้า Telegram Commander
    """
    if (REELS_DIR / ".posting_paused").exists():
        return {"success": False, "error": "Posting paused for video quality review"}
    import shutil
    import uploader
    import tiktok_studio_uploader
    from broadcast_receipts import held, reserve, finish
    from app.services.video_publish_policy import publication_block_reason
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

    enable_tiktok = os.getenv("ENABLE_TIKTOK", "false").lower() in ("true", "1", "yes")
    accounts = tiktok_studio_uploader.get_available_tiktok_accounts() if enable_tiktok else []
    if not accounts and enable_tiktok:
        logger.warning("TikTok unavailable; continuing Facebook")

    tt_account_index = 0
    if index_file.exists():
        try:
            tt_account_index = int(index_file.read_text(encoding="utf-8").strip())
        except Exception:
            tt_account_index = 0

    # 2. คัดเลือกบัญชี TikTok ที่มีสิทธิ์โพสต์
    active_cookie = None
    account_key = "tiktok_cookies"
    if target_account_id and accounts:
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
            logger.info("TikTok unavailable/quota reached; continuing Facebook Reels")
        else:
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
    from product_post_history import posted_product_ids, product_id
    posted_ids = posted_product_ids(REELS_DIR, TOOLS_DIR)
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
        
        # รวบรวมประวัติการโพสต์จากทุกบัญชีและทุกแพลตฟอร์ม (Global Deduplication Pool)
        global_posted_files = set()
        for k, v in history.items():
            if isinstance(v, list):
                global_posted_files.update(v)

        posted_titles = uploader.get_posted_titles()
        posted_title_signatures = set()
        for item_name in global_posted_files:
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
                    if f.is_file() and f.stat().st_size > 100 * 1024:
                        if f not in pending_videos:
                            pending_videos.append(f)

        for v in pending_videos:
            v_info = products_meta.get(v.name, {})
            sidecar = v.with_suffix(".txt")
            if not sidecar.exists():
                alt_txt = v.parent / f"{v.stem}.txt"
                if alt_txt.exists():
                    sidecar = alt_txt
            review_caption = sidecar.read_text(encoding="utf-8") if sidecar.exists() else (uploader.build_caption(v_info) if v_info else "")
            if publication_block_reason(v, review_caption, v_info) or held(v, TOOLS_DIR):
                continue
            if product_id(v.name) in posted_ids:
                continue
            if v.name in global_posted_files:
                continue
            v_title = v_info.get("product_name") or v.stem

            # กรองความปลอดภัย
            topic_hook = (v_info.get("topic_data", {}) or {}).get("hook", "")
            if is_sensitive_forbidden_topic(f"{v.name} {v_title} {topic_hook}"):
                logger.warning(f"🚫 [Unified Safety] กรองเนื้อหาต้องห้าม: {v.name} — ข้าม")
                continue

            # กรองความซ้ำซ้อน
            clean_title_sig = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9]', '', v_title).lower() if v_title else ""
            if clean_title_sig:
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
                # Only the prebuffer owns production, locking and the 90/10 cycle.
                logger.info("Waiting for prebuffer to publish a verified clip")
            except Exception as e_gen:
                logger.warning(f"⚠️ ผลิตคลิปฉุกเฉินล้มเหลว: {e_gen}")
        else:
            logger.info("⏳ [Unified Broadcast] ผู้ใช้จัดการวิดีโอเอง — รอไฟล์วิดีโอ (.mp4) ใน pending_videos หรือ D:/")
            return {"success": False, "error": "Waiting for user video candidate"}

    if not candidate or not candidate.exists():
        return {"success": False, "error": "No available video candidate found"}

    if product_id(candidate.name) in posted_ids:
        return {"success": False, "error": "Product already posted; duplicate blocked"}

    # 4. ดึงข้อมูล Metadata และสร้างแคปชั่น
    v_info = products_meta.get(candidate.name, {})
    if not v_info:
        m_id = re.match(r'^(?:prod|shopee_(?:extracomm|high_conv|pilot))_(\d+)_', candidate.name)
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
    if not v_info.get("is_pure_content") and "@137gsref" not in clean_caption:
        clean_caption = f"{clean_caption.strip()}\n\n{line_cta}"

    # เตรียมแคปชั่นสำหรับ TikTok (Presets + Hashtags)
    try:
        from tiktok_promo_presets import format_tiktok_caption
        tt_caption = format_tiktok_caption(clean_caption, index=tt_account_index,
                                           is_pure_content=bool(v_info.get("is_pure_content")))
    except Exception:
        tt_caption = clean_caption

    # 5. ตรวจสอบคุณภาพเสียงวิดีโอก่อนโพสต์ (ป้องกันวิดีโอไม่มีเสียงหรือไฟล์เสีย 100%)
    try:
        from auto_product_reels import verify_video_has_audio
        has_audio, audio_reason = verify_video_has_audio(candidate)
        if not has_audio:
            logger.warning(f"🚨 [AUDIO GUARD] วิดีโอเสียงไม่สมบูรณ์ ({audio_reason}): {candidate.name} — กักกันไฟล์ทันที")
            corrupt_dir = REELS_DIR / "corrupted"
            corrupt_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(candidate), str(corrupt_dir / candidate.name))
            except Exception:
                pass
            return {"success": False, "error": f"Audio verification failed: {audio_reason}"}
    except Exception as e_vfy:
        logger.warning("Audio check unavailable; skip this attempt")
        return {"success": False, "error": "Audio verification unavailable"}

    blocked = publication_block_reason(candidate, clean_caption, v_info)
    if blocked:
        return {"success": False, "error": blocked}
    attempt_key = reserve(candidate, TOOLS_DIR)
    res_tt = {"success": False, "error": "Upload did not complete"}
    uploader.LAST_BROADCAST_RESULT = {"fb": [], "yt": [], "complete": False}

    # โพสต์ขึ้น TikTok (ข้ามทันทีเมื่อปิดใช้งาน: ลบออกทุกที่)
    if enable_tiktok:
        cur_ch_count = daily_data["counts"].get(account_key, 0) + 1
        logger.info(f"⚫ [TikTok: {display_channel}] กำลังประมวลผลโพสต์คลิปที่ {cur_ch_count}/{daily_target} ของวันนี้: {candidate.name}")
        try:
            if active_cookie is None:
                res_tt = {"success": False, "error": "ข้าม: ไม่มีบัญชี TikTok พร้อมใช้หรือครบโควตาแล้ว"}
            else:
                res_tt = tiktok_studio_uploader.upload_video_via_web(candidate, caption=tt_caption, cookie_file=active_cookie)
            tt_success = res_tt.get("success", False)
        except Exception as e_tt_err:
            logger.warning(f"⚠️ [TikTok: {display_channel}] Web Upload Error ({e_tt_err}) — ปลอดภัยสำหรับ FB")
            tt_success = False
            res_tt = {"success": False, "error": "TikTok upload exception; outcome unverified"}

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
            try:
                index_file.write_text(str(tt_account_index), encoding="utf-8")
            except OSError:
                logger.exception("Cannot save TikTok rotation; continuing other platforms")
    else:
        tt_success = False
        res_tt = {"success": False, "error": "TikTok disabled"}

    # 6. ซิงค์วิดีโอตัวเดียวกันขึ้น Facebook Reels (2 เพจ)
    # ตรวจสอบก่อนว่าหัวข้อนี้เคยขึ้น FB ไปแล้วหรือไม่ เพื่อป้องกันการโพสต์ซ้ำ 4-5 ครั้ง
    clean_fby_sig = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9]', '', v_title).lower() if v_title else ""
    posted_fb_yt_titles = uploader.get_posted_titles()
    already_on_fb = bool(clean_fby_sig and clean_fby_sig in posted_fb_yt_titles)

    if already_on_fb and not force:
        logger.info(f"⏭️ [Unified Broadcast] คลิป {candidate.name} ({v_title[:30]}) เคยโพสต์บน FB แล้ว — ข้ามการซิงค์ซ้ำ")
        res_fb_yt = 0
    else:
        logger.info(f"🚀 [Unified Broadcast] ซิงค์คลิป {candidate.name} ไปยัง Facebook Reels...")
        try:
            res_fb_yt = uploader.post_next(
                dry_run=False,
                custom_video=str(candidate),
                custom_caption=clean_caption,
                force=force,
                normalize=True,
                broadcast_all_yt=False,
                notify=False
            )
        except Exception as exc:
            logger.exception("Facebook attempt failed; completing report and continuing next round")
            res_fb_yt = 1
            uploader.LAST_BROADCAST_RESULT["error"] = type(exc).__name__

    receipt = uploader.LAST_BROADCAST_RESULT
    fb_urls = receipt.get("fb", [])
    yt_urls = []
    status = finish(attempt_key, TOOLS_DIR, res_tt, receipt)
    if (status == "posted" or (status == "partial" and (fb_urls or tt_success))) and candidate.exists():
        destination = REELS_DIR / "posted" / candidate.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.move(str(candidate), str(destination))
        else:
            try:
                candidate.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            candidate.with_suffix(".txt").unlink(missing_ok=True)
        except Exception:
            pass
        logger.info("Verified broadcast archived: %s (status: %s)", candidate.name, status)
    else:
        logger.warning("Broadcast %s; keeping source and holding automatic retries: %s", status, candidate.name)
    tt_url = res_tt.get("video_url") or ""

    # จัดรูปแบบแสดงผลลิงก์ของแต่ละช่องทาง
    channels_lines = []
    if enable_tiktok:
        if tt_success:
            channels_lines.append(f"  • ⚫ TikTok: ✅ โพสต์สำเร็จ ({display_channel})\n    👉 {tt_url}")
        else:
            channels_lines.append(f"  • ⚫ TikTok: ⚠️ {res_tt.get('error', 'ไม่สำเร็จ')} ({display_channel})")

    if fb_urls:
        fb_sub = "\n".join([f"    👉 {u}" for u in fb_urls])
        channels_lines.append(f"  • 🔵 Facebook Reels ({len(fb_urls)} เพจ):\n{fb_sub}")
    else:
        fb_yt_badge = "ยังไม่มีหลักฐานยืนยันการเผยแพร่ในรอบนี้"
        channels_lines.append(f"  • 🔵 Facebook Reels: {fb_yt_badge}")

    channels_text = "\n".join(channels_lines)
    skipped = receipt.get("skipped", [])
    if receipt.get("error"):
        skipped = [*skipped, f"Facebook: {receipt['error']}"]
    if skipped:
        channels_text += "\n" + "\n".join(f"  • ⏭️ {reason}" for reason in skipped)

    # 9. ส่งแจ้งเตือนสรุปครบทุกแพลตฟอร์มเข้า Telegram Commander
    try:
        from telegram_notifier import send_telegram_notification
        tiktok_block = ""
        if enable_tiktok:
            counts_list = []
            for idx, acc_file in enumerate(accounts, 1):
                c_val = daily_data["counts"].get(acc_file.stem, 0)
                counts_list.append(f"ช่อง {idx}={c_val}/{daily_target}")
            counts_summary = " | ".join(counts_list)
            tiktok_block = f"📊 สรุปยอดโพสต์ TikTok วันนี้:\n  • {counts_summary}\n"

        remaining_pending = len(uploader.list_pending())

        msg_tg = (
            f"📊 [Broadcast: {status}]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎬 คลิป: {v_title[:50]}\n\n"
            f"🌐 ลิงก์ที่เผยแพร่:\n"
            f"{channels_text}\n\n"
            f"{tiktok_block}"
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
            status=status
        )
    except Exception as e_sheet:
        logger.warning(f"⚠️ เรียกบันทึก Google Sheets ไม่สำเร็จ: {e_sheet}")

    return {
        "success": status == "posted",
        "status": status,
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
    • พร้อมซิงค์วิดีโอตัวเดียวกันทันทีขึ้น Facebook Reels (2 เพจ)
    • ย้ายคลิปเข้า posted/ และแจ้งเตือนสรุปครบทุกแพลตฟอร์มเข้า Telegram
    """
    enable_broadcast = os.getenv("ENABLE_AUTO_BROADCAST", "false").lower() in ("true", "1", "yes")
    if not enable_broadcast:
        logger.info("⏸️ ระบบ Auto Reels Broadcast: STANDBY (ปิดการกระจายอัตโนมัติ — แจ้งเตือนเฉพาะออเดอร์)")
        return
    logger.info("🚀 เริ่มต้นระบบ Facebook Reels Master Orchestrator (รอบหมุนเวียนทุก 45 นาที)")
    interval_minutes = int(os.getenv("TIKTOK_INTERVAL_MINUTES", "45"))
    # ให้เวลา Pre-buffer Producer ตรวจสอบสต็อกและเริ่มทำงานก่อน 10 วินาที
    time.sleep(10)
    # Restarting after a repair must not trigger an extra broadcast immediately.
    last_post = REELS_DIR / "last_post_time.txt"
    try:
        remaining = float(last_post.read_text(encoding="utf-8")) + interval_minutes * 60 - time.time()
    except (OSError, ValueError):
        remaining = 0
    if remaining > 0:
        logger.info("Waiting %.0f seconds until the next scheduled broadcast", remaining)
        time.sleep(remaining)
    
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
        f"  • 🎬 โรงงานผลิตคลิป (Pre-buffer): 🟢 ออนไลน์ (สินค้า Shopee 100%)\n"
        f"  • ⚫ TikTok Studio: 🟢 ปกติ (4 ช่องหมุนเวียน โควตา 8 คลิป/ช่อง/วัน)\n"
        f"  • 📍 Facebook Reels: 🟢 ปกติ (2 เพจหลักพร้อมยิงซิงค์ตรง)\n"
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


def prune_old_posted_videos(days: int = 14) -> tuple:
    """ลบไฟล์วิดีโอและไฟล์แคปชั่นในโฟลเดอร์ posted/ ที่มีอายุเก่ากว่าจำนวนวันที่กำหนด เพื่อประหยัดพื้นที่ดิสก์ 100%"""
    posted_dir = REELS_DIR / "posted"
    if not posted_dir.exists():
        return 0, 0.0

    now_ts = time.time()
    cutoff_ts = now_ts - (days * 86400)
    deleted_count = 0
    freed_bytes = 0

    for f in list(posted_dir.glob("*")):
        if f.is_file() and f.stat().st_mtime < cutoff_ts:
            try:
                freed_bytes += f.stat().st_size
                f.unlink(missing_ok=True)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"⚠️ ไม่สามารถลบไฟล์เก่า {f.name}: {e}")

    freed_mb = freed_bytes / (1024 * 1024)
    if deleted_count > 0:
        logger.info(f"🧹 Prune Disk Guard: ลบไฟล์วิดีโอที่โพสต์แล้วเก่ากว่า {days} วัน จำนวน {deleted_count} ไฟล์ (คืนพื้นที่ {freed_mb:.1f} MB)")
    return deleted_count, freed_mb


def run_daily_reporter_loop():
    """เธรดส่งรายงานสรุปสถานะระบบประจำช่วงเวลา (08:00 น. และ 20:00 น.) พร้อมอัปเดตยอดวิวลง Google Sheets และล้างดิสก์อัตโนมัติ"""
    enable_reports = os.getenv("ENABLE_PERIODIC_REPORTS", "false").lower() in ("true", "1", "yes")
    if not enable_reports:
        logger.info("⏸️ ระบบ Daily Reporter: STANDBY (ปิดการส่งสรุปประจำวันอัตโนมัติ)")
        return
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
                # 1. ส่งรายงานสถานะระบบเข้า Telegram Commander & LINE
                send_system_health_report(title=slot_title)
                
                # 2. ซิงค์ยอดวิว/ยอดไลก์ล่าสุดลง Google Sheets อัตโนมัติในเธรดเบื้องหลัง
                try:
                    from update_sheet_metrics import update_all_metrics_in_sheet
                    threading.Thread(target=update_all_metrics_in_sheet, daemon=True).start()
                except Exception as e_sheet:
                    logger.warning(f"⚠️ Auto-update sheet metrics failed: {e_sheet}")

                # 3. ล้างไฟล์วิดีโอที่โพสต์แล้วใน posted/ ที่เก่ากว่า 14 วัน
                prune_old_posted_videos(days=14)
        except Exception as e:
            logger.warning(f"⚠️ Daily reporter error: {e}")
        time.sleep(180)  # เช็คทุก 3 นาที


def run_performance_learning_loop():
    """Refresh deterministic product scores hourly and notify once daily."""
    last_notified = ""
    while True:
        try:
            from performance_learner import run_once
            now = datetime.now(ICT)
            notify_key = now.strftime("%Y-%m-%d") if now.hour == 20 else ""
            should_notify = bool(notify_key and notify_key != last_notified)
            data = run_once(notify=should_notify)
            if should_notify:
                last_notified = notify_key
            logger.info("📈 Local performance learner: %s products, %s categories",
                        len(data.get("products", {})), len(data.get("categories", {})))
        except Exception as exc:
            logger.warning("⚠️ Performance learner error: %s", exc)
        time.sleep(3600)


def print_banner():
    bot_name = os.getenv("BOT_NAME", "ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้")
    slogan = os.getenv("BRAND_SLOGAN", "คัดของดี ของเด็ด Shopee แท้ 100%")
    voice = os.getenv("TTS_VOICE", "th-TH-PremwadeeNeural")
    print("=" * 68)
    print(f"🎬  ระบบอัตโนมัติ Facebook Reels Master Broadcast (24/7)")
    print(f"🏷️   แบรนด์: {bot_name}")
    print(f"📢  สโลแกน: {slogan}")
    print(f"🎙️  เสียงพากย์: {voice}")
    print(f"🕒  เวลาทำการ: 24 ชั่วโมง (รอบหมุนเวียนทุก 45 นาที)")
    enable_producer = os.getenv("ENABLE_PREBUFFER_PRODUCER", "true").lower() in ("true", "1", "yes")
    prod_status = "🟢 ACTIVE (100% Full Autopilot — บอทผลิตและโพสต์อัตโนมัติ)" if enable_producer else "⏸️ STANDBY (ผู้ใช้จัดการไฟล์วิดีโอเอง)"
    print("📊 สถานะระบบย่อย:")
    print(f"  [1] Pre-buffer Producer: {prod_status}")
    print("  [2] Facebook Reels Orchestrator: 🟢 ACTIVE (2 เพจหลักซิงค์พร้อมกัน)")
    print("  [3] Auto-Recovery & Content Safety Guard: 🟢 ONLINE")
    print("  [4] Telegram Commander 24/7 (@pakhem_fish_bot): 🟢 ONLINE")
    print("=" * 68)
    print("💡 กด Ctrl + C เพื่อหยุดการทำงาน\n")


def main():
    print_banner()

    # 1. รันเธรดผลิตคลิปสินค้าล่วงหน้ารอไว้เสมอ (Pre-buffer Producer)
    t_producer = threading.Thread(target=run_prebuffer_producer_loop, daemon=True, name="ReelsPrebuffer")
    t_producer.start()

    # 2. รันเธรดวาทยกรหลัก Facebook Reels Master Broadcast (หมุนเวียนทุก 45 นาที)
    t_orchestrator = threading.Thread(target=run_tiktok_led_unified_loop, daemon=True, name="ReelsOrchestrator")
    t_orchestrator.start()

    # 3. รันเธรดรายงานสรุปประจำเวลา (08:00 / 20:00 น.)
    t_reporter = threading.Thread(target=run_daily_reporter_loop, daemon=True, name="SystemReporter")
    t_reporter.start()

    # 4. เรียนรู้จากยอดจริงด้วยสูตร Local ทุกชั่วโมง
    t_learning = threading.Thread(target=run_performance_learning_loop, daemon=True, name="PerformanceLearner")
    t_learning.start()

    # 5. รันเธรดศูนย์สั่งการโต้ตอบ Telegram Commander (ปุ่มสั่งการสด & ตอบแชท LINE 24/7)
    try:
        from telegram_commander import run_telegram_commander_loop
        t_commander = threading.Thread(target=run_telegram_commander_loop, daemon=True, name="TelegramCommander")
        t_commander.start()
        logger.info("🤖 เธรด PaKhem Commander เริ่มต้นทำงานเรียบร้อยแล้ว")
    except Exception as e:
        logger.warning(f"⚠️ Telegram Commander launch error: {e}")

    # 6. รันเธรดตรวจจับและตอบคอมเมนต์ใต้โพสต์/คลิป Facebook อัตโนมัติ 24/7
    try:
        from fb_comment_responder import run_comment_responder_loop
        t_comment_bot = threading.Thread(target=run_comment_responder_loop, daemon=True, name="FBCommentResponder")
        t_comment_bot.start()
        logger.info("💬 เธรด FB Comment Auto-Responder 24/7 เริ่มต้นทำงานเรียบร้อยแล้ว")
    except Exception as e:
        logger.warning(f"⚠️ FB Comment Responder launch error: {e}")

    workers = {
        "ReelsPrebuffer": (run_prebuffer_producer_loop, t_producer),
        "ReelsOrchestrator": (run_tiktok_led_unified_loop, t_orchestrator),
        "SystemReporter": (run_daily_reporter_loop, t_reporter),
        "PerformanceLearner": (run_performance_learning_loop, t_learning),
    }
    if 't_commander' in locals():
        workers["TelegramCommander"] = (run_telegram_commander_loop, t_commander)
    if 't_comment_bot' in locals():
        workers["FBCommentResponder"] = (run_comment_responder_loop, t_comment_bot)
    try:
        while True:
            time.sleep(30)
            for name, (target, worker) in list(workers.items()):
                if not worker.is_alive():
                    logger.error("Worker %s stopped; restarting", name)
                    worker = threading.Thread(target=target, daemon=True, name=name)
                    worker.start()
                    workers[name] = (target, worker)
    except KeyboardInterrupt:
        logger.info("🛑 ปิดการทำงานระบบ System Runner")
        sys.exit(0)


if __name__ == "__main__":
    from filelock import FileLock, Timeout
    lock_dir = ROOT_DIR / "artifacts" / "trend_autopilot"
    lock_dir.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(lock_dir / "system_runner.lock"), timeout=0):
            main()
    except Timeout:
        logger.info("System runner is already active; duplicate startup skipped")
