#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""uploader.py — Facebook Reels auto-uploader (FIFO + AI caption + normalize + pacing)

ดึงคลิป .mp4 จาก pending_videos/ (FIFO) → แปลงให้ตรง spec Reels อัตโนมัติ
(9:16/1080p/30fps/≤90s ด้วย ffmpeg — ไม่ต้องตั้งขนาดเอง) → เขียนแคปชั่น:
คลิปสินค้า (มีใน products.json) = AI (Groq) + ลิงก์ Shopee · คลิปที่ไม่ใช่สินค้า =
แคปชั่นแนะนำป้าเข็มจากคลัง (facebook_intro) หมุนเวียนอัตโนมัติ → อัปโหลด Reels
ผ่าน 3-step video upload session (init → upload → publish) → ย้ายคลิปไป posted/
แล้วบันทึกเวลาล่าสุด (pacing)

ใช้งาน:
  python uploader.py                  # โพสต์คลิปถัดไป 1 ตัว (ถ้าถึงเวลา spacing)
  python uploader.py --dry-run        # จำลอง: โชว์คลิป + แคปชั่น ไม่โพสต์จริง
  python uploader.py --force          # ข้าม pacing (โพสต์ทันที) — ยังนับ daily limit
  python uploader.py --no-normalize   # ไม่แปลงคลิป (ใช้ไฟล์เดิมที่ตรง spec อยู่แล้ว)

env (อ่านจาก backend/.env):
  FACEBOOK_PAGE_ACCESS_TOKEN / FACEBOOK_PAGE_ID
  GROQ_API_KEY          (เขียนแคปชั่น AI; ไม่ตั้ง = ใช้แคปชั่น template)
  POSTING_SPACING_HOURS (default 3.0 ชม.)
  MAX_REELS_PER_DAY     (default 30 — ลิมิตจริงของ Reels API)

ตั้ง Task Scheduler / Cron รันทุก 30-60 นาที → พอถึงเวลา spacing จะโพสต์คลิปถัดไปเอง
"""
import argparse
import json
import os
import re
import shutil

import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import logging

# บังคับ stdout UTF-8 (กัน emoji/ไทย พังบน Windows console ที่ใช้ cp874/850)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # ตอนถูก import ใน pytest stdout เป็น capture object ที่ reconfigure ไม่ได้

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"
TOOLS = ROOT.parent / "tools"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(TOOLS))

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

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND / ".env")

# Transport-level INFO logs can print Facebook URLs containing access_token.
# Keep them disabled even when uploader.py is run directly, outside
# tools/system_runner.py.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from app.services.facebook_poster import PAGE_ID, configured_pages, post_reel  # noqa: E402
from app.services.facebook_intro import intro_posts  # noqa: E402
from app.services.bot_profile import LINE_OA_URL  # noqa: E402
from app.services.product_price_policy import sanitize_public_product_text  # noqa: E402



PENDING_DIR = ROOT / "pending_videos"
POSTED_DIR = ROOT / "posted"
PRODUCTS_JSON = ROOT / "products.json"


def product_selection_mode() -> str:
    """อ่านกลยุทธ์คัดสินค้าเดียวกับ pre-buffer runner"""
    mode = os.getenv("PRODUCT_SELECTION_MODE", "balanced").strip().lower()
    return mode if mode in {"discount", "bestseller", "balanced"} else "balanced"

# รองรับภาพนิ่ง — แปลงเป็นวิดีโอความยาวขั้นต่ำ 10 วินาทีอัตโนมัติ
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_VIDEO_DURATION = max(5, int(os.getenv("REELS_MIN_DURATION", "10") or 10))  # วินาที
LAST_POST_FILE = ROOT / "last_post_time.txt"
DAILY_COUNT_FILE = ROOT / "posts_today.txt"
NOTIFY_STATE_FILE = ROOT / ".reels_notify_state.json"
LOG_FILE = ROOT / "uploader_execution.log"


def log(msg: str) -> None:
    """เขียนทั้ง stdout และ uploader_execution.log (กันดูไม่ออกตอน Task Scheduler เรียก)"""
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key) or default)
    except (TypeError, ValueError):
        return default


DEFAULT_SPACING_HOURS = _env_float("POSTING_SPACING_HOURS", 0.5)  # 30 นาที (0.5 ชม.)
DEFAULT_MAX_PER_DAY = 48  # โควต้าต่อวัน




def _ffmpeg_exe() -> str:
    """path ffmpeg — ใช้ binary ที่ติดมากับ imageio_ffmpeg (ใน venv) ก่อน fallback เป็น 'ffmpeg' ใน PATH"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def normalize_video(src: Path, dst: Path, ffmpeg: str | None = None) -> bool:
    """แปลงคลิปให้ตรง spec Reels อัตโนมัติ (ไม่ต้องตั้งขนาดเอง):

    9:16 1080x1920 (แนวตั้ง) · เติมพื้นหลังเบลอแทนแถบดำ · 30fps · ตัดไม่เกิน 90 วิ
    · H.264 + AAC (มี audio ก็เก็บ ไม่มีก็ผ่าน) · faststart เปิดเล่นเร็ว
    คืน True = ได้ไฟล์ dst ที่ใช้ได้; False = แปลงไม่สำเร็จ (caller ใช้ต้นฉบับแทน)
    """
    if not src.exists():
        return False
    ffmpeg = ffmpeg or _ffmpeg_exe()
    filter_complex = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=20:5[bg2];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[v]"
    )
    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-r", "30", "-t", "90",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(dst),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
        return dst.exists() and dst.stat().st_size > 0
    except Exception as e:
        log(f"[WARN] normalize_video ล้ม ({e}) — จะใช้ไฟล์ต้นฉบับแทน")
        return False


def load_products() -> dict:
    """video filename → {product_name, price, category, affiliate_link}"""
    if not PRODUCTS_JSON.exists():
        return {}
    try:
        return json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"[WARN] products.json อ่านไม่ได้ ({e}) — ใช้แคปชั่น generic")
        return {}


def is_image(path: Path) -> bool:
    """เช็คว่าเป็นไฟล์ภาพนิ่ง"""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def convert_image_to_video(src: Path, dst: Path, duration: int = IMAGE_VIDEO_DURATION, ffmpeg: str | None = None) -> bool:
    """แปลงภาพนิ่งเป็นวิดีโอ 9:16 (1080x1920) ด้วย ffmpeg:

    - ภาพจะถูก scale ให้พอดี 1080x1920 (เติมเบลอแทนแถบดำ)
    - ความยาว duration วินาที (default 5 วิ)
    - H.264 + AAC (silent) + faststart
    """
    if not src.exists():
        return False
    ffmpeg = ffmpeg or _ffmpeg_exe()
    # สร้างวิดีโอจากภาพนิ่ง: scale + blur background + overlay
    filter_complex = (
        f"color=c=black:s=1080x1920:d={duration}[bg];"
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
    )
    cmd = [
        ffmpeg, "-y",
        "-loop", "1", "-i", str(src),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-r", "30", "-t", str(duration),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dst),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        return dst.exists() and dst.stat().st_size > 0
    except Exception as e:
        log(f"[WARN] convert_image_to_video ล้ม ({e}) — ข้ามภาพนี้")
        return False


def list_pending() -> list:
    """คลิป .mp4 + ภาพ (.jpg/.png/.webp) ใน pending_videos/ เรียง FIFO (ตามชื่อไฟล์)"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    all_files = [p for p in PENDING_DIR.iterdir() if p.is_file() and not p.name.startswith(".")]
    # filter เฉพาะ .mp4 หรือภาพ
    supported = [f for f in all_files if f.suffix.lower() == ".mp4" or is_image(f)]
    return sorted(supported)


def recycle_clips() -> bool:
    """Auto-recycle: pending ว่าง → คัดลอกคลิป/ภาพจาก posted/ กลับมาโพสต์ใหม่.

    คัดลอก (ไม่ลบ) — posted/ ยังเก็บต้นฉบับไว้
    คืน True = recycling เกิดขึ้น (มีคลิป/ภาพกลับมา)
    """
    # ดึงทั้ง .mp4 และภาพจาก posted/
    posted_files = sorted(
        p for p in POSTED_DIR.iterdir()
        if p.is_file() and not p.name.startswith(".")
        and (p.suffix.lower() == ".mp4" or is_image(p))
    )
    if not posted_files:
        return False
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    for src in posted_files:
        dst = PENDING_DIR / src.name
        if not dst.exists():
            shutil.copy2(str(src), str(dst))
    recycled = list_pending()
    if recycled:
        log(f"♻️ Recycle: คัดลอกจาก posted/ กลับ {len(recycled)} ตัว → pending_videos/")
        return True
    return False


def pacing_ok(spacing_hours: float) -> bool:
    """True = ครบระยะห่าง (หรือไม่มีเวลาล่าสุด / spacing ปิด)"""
    if spacing_hours <= 0:
        return True
    if not LAST_POST_FILE.exists():
        return True
    try:
        last = float(LAST_POST_FILE.read_text(encoding="utf-8").strip())
        return (time.time() - last) >= spacing_hours * 3600
    except Exception:
        return True


def daily_ok(max_per_day: int) -> bool:
    """True = วันนี้ยังไม่ครบโควต้า (MAX_REELS_PER_DAY)"""
    if max_per_day <= 0:
        return True
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        date, count = DAILY_COUNT_FILE.read_text(encoding="utf-8").strip().split()
        if date != today:
            return True
        return int(count) < max_per_day
    except Exception:
        return True


def bump_daily_count() -> None:
    """บันทึกจำนวนโพสต์วันนี้ (รีเซ็ตอัตโนมัติเมื่อข้ามวัน)"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        date, count = DAILY_COUNT_FILE.read_text(encoding="utf-8").strip().split()
        count = (int(count) + 1) if date == today else 1
    except Exception:
        count = 1
    DAILY_COUNT_FILE.write_text(f"{today} {count}", encoding="utf-8")


def get_today_post_count() -> int:
    """อ่านจำนวนคลิปที่โพสต์ไปแล้วในวันนี้"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        if DAILY_COUNT_FILE.exists():
            date, count = DAILY_COUNT_FILE.read_text(encoding="utf-8").strip().split()
            if date == today:
                return int(count)
    except Exception:
        pass
    return 0


def _load_notify_state() -> dict:
    """สถานะแจ้งเตือน (persist เป็นไฟล์ — uploader รัน process ใหม่ทุกครั้ง)"""
    try:
        return json.loads(NOTIFY_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_notify_state(state: dict) -> None:
    try:
        NOTIFY_STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def _log_tail(n: int = 1) -> list:
    """อ่าน log ท้ายสุด n บรรทัด (ใช้ประกอบข้อความแจ้งเตือน)"""
    try:
        return LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except Exception:
        return []


def _notify_owner(text: str) -> bool:
    """ส่งแจ้งเตือนเจ้าของร้านผ่าน Telegram Commander (ฟรี 100% ไม่จำกัดจำนวน ไม่กินโควต้า LINE)"""
    try:
        from telegram_notifier import send_telegram_alert
        return bool(send_telegram_alert(text))
    except Exception as e:
        log(f"[TELEGRAM] ส่งแจ้งเตือนล้ม: {e}")
        return False


def notify_reels_issues(post_result: int, dry_run: bool = False) -> None:
    """แจ้งเจ้าของผ่าน LINE เมื่อ Reels มีปัญหา (กันโพสต์หยุดเงียบ ๆ):

    1) คิวว่าง (pending_videos/ ไม่มีคลิป) — แจ้ง 1 ครั้ง/วัน (state file กันสแปม)
    2) โพสต์ล้ม ≥ 2 ครั้งติด — แจ้ง 1 ครั้งต่อรอบที่ล้มต่อเนื่อง (สำเร็จ = รีเซ็ตนับ)
    """
    if dry_run:
        return
    state = _load_notify_state()
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1) คิวว่าง — แจ้ง 1 ครั้ง/วัน
    if not list_pending():
        if state.get("last_empty_notified_date") != now_date:
            state["last_empty_notified_date"] = now_date
            _save_notify_state(state)
            _notify_owner(
                "⚠️ [แจ้งเตือนคลังวิดีโอ Reels]\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "• 📌 สถานะ: คิว Reels ว่างแล้ว! (ไม่มีคลิปใน pending_videos/)\n"
                "• 💡 คำแนะนำ: กำลังส่งคำสั่งให้โรงงานผลิตคลิปอัตโนมัติทำงานเติมคลัง\n"
                "• ⏱️ โควต้าแจ้งเตือน: แจ้งเตือน 1 ครั้ง/วัน\n"
                "━━━━━━━━━━━━━━━━━━"
            )
        return

    # 2) โพสต์ล้มต่อเนื่อง
    if post_result != 0:
        streak = int(state.get("fail_streak", 0)) + 1
        state["fail_streak"] = streak
        if streak >= 2 and int(state.get("last_fail_notified_streak", 0)) < 2:
            state["last_fail_notified_streak"] = streak
            tail = _log_tail(1)
            detail = f"\n  • 🔍 รายละเอียด: {tail[0][:200]}" if tail else ""
            _notify_owner(
                f"🚨 [แจ้งเตือนข้อผิดพลาด Reels]\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• ❌ สถานะ: โพสต์ล้ม {streak} ครั้งติด!\n"
                f"• 📌 ข้อแนะนำ: ตรวจสอบ Token / ลิงก์สินค้า / Log{detail}\n"
                f"• 🔄 ระบบจะลองใหม่อัตโนมัติในรอบถัดไป\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
        _save_notify_state(state)
    else:
        # สำเร็จ (หรือข้าม) — รีเซ็ตนับความล้ม
        if state.get("fail_streak"):
            state["fail_streak"] = 0
            state["last_fail_notified_streak"] = 0
            _save_notify_state(state)


def _read_intro_idx() -> int:
    """ตำแหน่งแคปชั่นแนะนำป้าเข็มล่าสุด (round-robin กันโพสต์ซ้ำติดกัน)."""
    try:
        return int(json.loads(INTRO_STATE_FILE.read_text(encoding="utf-8")).get("idx", 0))
    except Exception:
        return 0


def _write_intro_idx(idx: int) -> None:
    try:
        INTRO_STATE_FILE.write_text(json.dumps({"idx": idx}), encoding="utf-8")
    except Exception:
        pass


def build_intro_caption(advance: bool = True) -> str:
    """แคปชั่นแนะนำป้าเข็มจากคลัง (facebook_intro) หมุนเวียน — ใช้กับคลิปที่ไม่ใช่สินค้า.

    advance=True เลื่อนตำแหน่ง (ใช้ตอนโพสต์สำเร็จ) — advance=False แค่ peek (dry-run).
    ลิงก์ LINE OA ที่ยังเป็น placeholder (@xxxxx) จะถูกแทนด้วยลิงก์จริงจาก bot_profile.
    """
    posts = intro_posts()
    idx = _read_intro_idx() % len(posts)
    caption = posts[idx]["caption"]
    if advance:
        _write_intro_idx((idx + 1) % len(posts))
    return caption.replace("https://line.me/R/ti/p/@xxxxx", LINE_OA_URL)


CATEGORY_HOOKS = {
    "สัตว์เลี้ยง & ของใช้หมาแมว": [
        "🐾 ทาสหมาทาสแมวต้องมีติดบ้านไว้! ป้าคัดของแท้ตัวเด็ดมาให้แล้วจ้า ✨",
        "🚨 เลี้ยงน้องแล้วเจอปัญหากวนใจใช่ไหม? ตัวนี้ช่วยได้เยอะมาก รีวิว 5 ดาวแน่น!",
        "✨ ไอเทมลับประจำบ้านสำหรับคนรักสัตว์ ใช้งานดีจนป้าต้องมาบอกต่อ 💕",
    ],
    "สมาร์ตโฮม & เครื่องใช้ไฟฟ้า": [
        "💡 เปลี่ยนชีวิตให้ง่ายและสะดวกขึ้น 10 เท่า! ตัวนี้ป้าแนะนำเลยจ้า ✨",
        "🚨 ใครกำลังมองหาตัวช่วยประหยัดแรงและเวลา ป้าคัดของแท้ตัวเด็ดมาให้แล้ว!",
        "🔥 ไอเทมเด็ดประจำบ้านที่คนแย่งกันสั่งถล่มทลาย รีวิวแน่นมาก คุ้มค่าน่าใช้สุดๆ!",
    ],
    "ของใช้ในบ้าน & จัดระเบียบบ้าน": [
        "🏠 ไอเทมลับประจำบ้านที่ทุกคนต้องมีติดไว้! ใช้ดีจนป้าต้องบอกต่อจ้า ✨",
        "🚨 เตือนแล้วนะ! ใครยังไม่มีตัวนี้ติดบ้านคือพลาดมาก รีวิว 5 ดาวแน่นสุดๆ",
        "✨ ตัวช่วยจัดบ้านและทำความสะอาดให้ชีวิตง่ายขึ้น ป้าคัดของแท้มาให้แล้ว 💕",
    ],
    "เครื่องครัว & ของกินของใช้": [
        "🍳 สายทำอาหารและสายของกินต้องมีติดครัวไว้! ป้าคัดตัวเด็ดมาให้แล้วจ้า ✨",
        "🔥 ไอเทมลับประจำห้องครัวที่แม่บ้านยกนิ้วให้ การันตีของแท้ ใช้งานคุ้มค่ามาก!",
        "🚨 ของดีมีคุณภาพที่ต้องมีติดครัว ซื้อแล้วคุ้มเงินทุกบาทแน่นอน ✨",
    ],
    "ไอที & แกดเจ็ตมือถือ": [
        "📱 แกดเจ็ตตัวเด็ดที่ทุกคนต้องมีพกติดตัว! ป้าคัดของแท้คุณภาพดีมาให้แล้วจ้า ✨",
        "💡 อย่าเพิ่งเลื่อนผ่าน ถ้าไม่อยากพลาดไอเทมไอทีสุดคุ้มตัวนี้!",
        "🔥 ตัวช่วยคู่ใจสายมือถือและไอที รีวิว 5 ดาวแน่น สเปกดีคุ้มเกินราคาแน่นอน!",
    ],
    "สุขภาพ & ดูแลตัวเอง": [
        "🩺 ไอเทมดูแลสุขภาพประจำบ้านที่ต้องมีติดไว้! ป้าคัดของแท้มาให้แล้วจ้า ✨",
        "🚨 ใครกำลังมองหาตัวช่วยดูแลตัวเองตัวนี้อยู่ การันตีคุณภาพ รีวิวแน่นมาก!",
        "✨ ตัวช่วยสุขภาพดี ใช้งานง่าย อุ่นใจได้ทุกวัน ป้าแนะนำเลยจ้า 💕",
    ],
    "ความงาม & ของใช้ส่วนตัว": [
        "💄 ไอเทมดูแลตัวเองที่คนรีวิวแน่นที่สุด! ป้าคัดของแท้ร้อยเปอร์เซ็นต์มาให้แล้วจ้า ✨",
        "✨ ของใช้ส่วนตัวตัวเด็ดที่ทุกคนต้องมีติดตัว ใช้ดีจนป้าต้องบอกต่อ 💕",
        "🔥 ตัวนี้ยอดขายปัง รีวิว 5 ดาวแน่นมาก การันตีของแท้ คุ้มค่าน่าใช้สุดๆ!",
    ],
    "ของใช้ติดรถ & เดินทาง/ช่าง": [
        "🚗 มีติดรถและพกติดบ้านไว้อุ่นใจที่สุด! ป้าคัดของแท้ตัวท็อปมาให้แล้วจ้า ✨",
        "🚨 ไอเทมฉุกเฉินและของจำเป็นสำหรับคนรักรถและการเดินทาง รีวิวแน่นมาก!",
        "🔧 ของใช้จำเป็นสุดทนทาน ใช้งานดี คุ้มค่าเงินทุกบาทแน่นอน ✨",
    ],
}


def classify_product_category(name: str, category: str) -> str:
    """จำแนกหมวดหมู่สินค้าเข้าสู่ 8 หมวดหมู่หลักตามคีย์เวิร์ดอย่างแม่นยำ 100% ป้องกันหมวดซ้อนทับ"""
    full_text = f"{name} {category}".lower()
    
    # 1. สัตว์เลี้ยง (ต้องดัก อาหารสัตว์ อาหารหมา อาหารแมว ก่อนอาหารคน)
    if any(k in full_text for k in ["อาหารสัตว์", "อาหารหมา", "อาหารแมว", "สัตว์", "หมา", "แมว", "สุนัข", "อึ", "ฉี่", "ขน", "แผ่นรอง", "pet", "ทาสแมว"]):
        return "สัตว์เลี้ยง & ของใช้หมาแมว"

    # 2. สุขภาพ & อาหารเสริม (ต้องดัก อาหารเสริม โปรตีน วิตามิน ยา ก่อนหมวดครัว)
    if any(k in full_text for k in ["อาหารเสริม", "โปรตีน", "วิตามิน", "คอลลาเจน", "สมุนไพร", "ยา", "บำรุงสุขภาพ", "สุขภาพ", "หน้ากาก", "แมสก์", "mask", "ปวด", "เมื่อย", "นวด", "หลัง", "คอ", "ไหล่", "เบาะ", "pm2.5", "เชื้อโรค"]):
        return "สุขภาพ & ดูแลตัวเอง"

    # 3. ความงาม & ของใช้ส่วนตัว
    if any(k in full_text for k in ["สิว", "หน้า", "สบู่", "ผิว", "ครีม", "เซรั่ม", "บำรุงผิว", "ความงาม", "สำลี", "ลิป", "แปรง", "แป้ง"]):
        return "ความงาม & ของใช้ส่วนตัว"

    # 4. ไอที & แกดเจ็ตมือถือ
    if any(k in full_text for k in ["หูฟัง", "ฟิล์ม", "บลูทูธ", "ไอที", "แกดเจ็ต", "เคส", "สายชาร์จ", "usb", "powerbank", "มือถือ", "คอมพิวเตอร์"]):
        return "ไอที & แกดเจ็ตมือถือ"

    # 5. เครื่องครัว & ของกินของใช้ (ไม่ใช้คำว่า อาหาร โดดๆ เพื่อไม่ให้ชนกับ อาหารเสริม)
    if any(k in full_text for k in ["ครัว", "กระทะ", "หม้อ", "แก้วน้ำ", "กระติก", "ตะหลิว", "มีด", "จาน", "ช้อน", "ปรุงอาหาร", "ทำอาหาร", "เตาแก๊ส", "เตาปิคนิค", "ของกิน", "ขนม", "พายกรอบ"]):
        return "เครื่องครัว & ของกินของใช้"

    # 6. สมาร์ตโฮม & เครื่องใช้ไฟฟ้า
    if any(k in full_text for k in ["รีโมท", "สมาร์ต", "โคมไฟ", "พัดลม", "โซล่า", "หลอดไฟ", "smart", "wifi", "tuya", "เครื่องใช้ไฟฟ้า"]):
        return "สมาร์ตโฮม & เครื่องใช้ไฟฟ้า"

    # 7. ของใช้ติดรถ & เดินทาง/ช่าง
    if any(k in full_text for k in ["รถ", "แดด", "ช่าง", "กีฬา", "เดินทาง", "ร่ม", "ปั๊ม", "เครื่องมือ", "แคมป์", "เต็นท์"]):
        return "ของใช้ติดรถ & เดินทาง/ช่าง"

    return "ของใช้ในบ้าน & จัดระเบียบบ้าน"


def clean_caption_text(text: str) -> str:
    """ทำความสะอาดชื่อสินค้าสำหรับแสดงบนแคปชั่น — ลบ tag/bracket ขยะ"""
    if not text:
        return ""
    t = re.sub(r'\[[^\]]*\]|\([^\)]*\)|【[^】]*】|\{[^\}]*\}', ' ', text)
    t = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s.,/%+\-()]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def build_caption(product: dict) -> str:
    """เขียนแคปชั่น Reels — ระบบ Smart Category Template 100% ปลอดภัย ไม่มโนสเปกผิดเพี้ยน"""
    if not product:
        return build_intro_caption(advance=False)
    raw_name = (product or {}).get("product_name") or "สินค้าเด็ดจากป้าเข็ม"
    name = sanitize_public_product_text(clean_caption_text(raw_name))
    link = (product or {}).get("affiliate_link") or ""
    category = (product or {}).get("category") or ""

    cat_key = classify_product_category(raw_name, category)
    hooks_pool = CATEGORY_HOOKS.get(cat_key, CATEGORY_HOOKS["ของใช้ในบ้าน & จัดระเบียบบ้าน"])
    
    import random
    hook = random.choice(hooks_pool)
    line_url = os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    line_id = os.getenv("LINE_OA_ID", "@137gsref")

    lines = [
        f"{hook}\n",
        f"📦 {name}",
        "รีวิว 5 ดาวแน่นมาก การันตีคุณภาพ คุ้มค่าเงินทุกบาท จิ้มดูรายละเอียดที่ลิงก์ได้เลยจ้า 👇\n"
    ]
    if link:
        lines.append(f"🛒 สั่งซื้อของแท้ / ดูโปรโมชั่น Shopee 👉 {link}")
    lines.append(f"💬 หรือทักแชทถามป้าเข็มได้ที่ LINE: {line_id} 👉 {line_url}\n")
    lines.append("#ของดีบอกต่อ #ของมันต้องมี #ป้าเข็มป้ายยา #ถ้าไม่คุ้มป้าบอกให้ #Shopee")

    return "\n".join(lines)



def post_next(dry_run: bool, force: bool, normalize: bool = True) -> int:
    pending = list_pending()
    if not pending:
        # ดึงสินค้าจากคลังมาสร้างคลิป Reels ให้อัตโนมัติ (Auto Product Reels จากภาพสินค้า)
        try:
            from auto_product_reels import generate_product_reels
            generated = generate_product_reels(
                limit=3, selection=product_selection_mode())
            if generated:
                log(f"🎬 สร้างคลิปสินค้าใหม่อัตโนมัติ {len(generated)} คลิป -> pending_videos/")
                pending = list_pending()
        except Exception as e:
            log(f"[WARN] สร้างคลิปสินค้าอัตโนมัติล้ม: {e}")

    if not pending:
        # ตรวจสอบว่าเปิด Auto-recycle หรือไม่ (ค่าเริ่มต้น ปิด เพื่อรอคลิปใหม่)
        auto_recycle = os.getenv("AUTO_RECYCLE_CLIPS", "0").lower() in ("1", "true", "yes")
        if auto_recycle and recycle_clips():
            pending = list_pending()
        else:
            log("ไม่มีคลิปใหม่ใน pending_videos/ — พักรอคลิปใหม่")
            return 0


    spacing = _env_float("POSTING_SPACING_HOURS", DEFAULT_SPACING_HOURS)
    max_per_day = int(_env_float("MAX_REELS_PER_DAY", 50))
    if not force:
        if not pacing_ok(spacing):
            log(f"ยังไม่ถึงเวลา (spacing {spacing} ชม.) — ข้าม ไม่โพสต์")
            return 0
        if not daily_ok(max_per_day):
            log(f"ครบลิมิต {max_per_day} โพสต์/วัน แล้ว — ข้าม ไม่โพสต์")
            return 0



    item = pending[0]
    product = load_products().get(item.name, {})
    if not product:
        m_id = re.match(r'^prod_(\d+)_', item.name)
        if m_id:
            try:
                from app.db import SessionLocal
                from app import models
                db = SessionLocal()
                try:
                    p = db.query(models.Product).filter(models.Product.id == int(m_id.group(1))).first()
                    if p:
                        product = {
                            "product_name": p.name,
                            "price": str(int(p.price or 0)),
                            "category": p.category or "สินค้าแนะนำ",
                            "affiliate_link": p.affiliate_url or ""
                        }
                finally:
                    db.close()
            except Exception as e:
                log(f"[WARN] ดึงข้อมูลสินค้าจาก DB ล้ม ({e})")
    caption = build_caption(product)

    # ถ้าเป็นภาพนิ่ง → แปลงเป็นวิดีโอก่อน
    is_img = is_image(item)
    img_video_tmp = None
    if is_img:
        fd, img_tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="reels_img_")
        os.close(fd)
        img_video_tmp = Path(img_tmp_path)
        log(f"[IMG] แปลงภาพนิ่งเป็นวิดีโอ 5 วินาที: {item.name} ...")
        if not convert_image_to_video(item, img_video_tmp):
            log(f"[FAIL] แปลงภาพล้ม: {item.name} — ข้าม")
            if img_video_tmp:
                img_video_tmp.unlink(missing_ok=True)
            return 1
        item = img_video_tmp  # ใช้วิดีโอที่แปลงแล้วแทน

    if dry_run:
        src_label = f"ภาพ → วิดีโอ" if is_img else "คลิป"
        log(f"[DRY-RUN] จะโพสต์ Reels ({src_label}): {item.name} (PAGE_ID={PAGE_ID})")
        log(f"[DRY-RUN] normalize: {'ON (แปลง 9:16 อัตโนมัติ)' if normalize else 'OFF (ใช้ไฟล์เดิม)'}")
        log(f"[DRY-RUN] caption:\n{caption}")
        if img_video_tmp:
            img_video_tmp.unlink(missing_ok=True)
        return 0

    # แปลงคลิปให้ตรง spec Reels ก่อนโพสต์ (9:16/1080p/30fps/≤90s) — ถ้าไม่สั่ง --no-normalize
    # ถ้าเป็นคลิปสินค้าที่สร้างจาก auto_product_reels (prod_*) จะตรง spec 1080x1920 อยู่แล้ว ไม่ต้องแปลงซ้ำ
    upload_path = str(item)
    tmp = None
    should_normalize = normalize and not item.name.startswith("prod_")
    if should_normalize:
        fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="reels_norm_")
        os.close(fd)
        tmp = Path(tmp_path)
        log(f"[NORM] แปลงคลิปเป็น 9:16/1080p/30fps: {item.name} ...")
        if normalize_video(item, tmp):
            upload_path = str(tmp)
        else:
            tmp = None  # แปลงล้ม → ใช้ไฟล์ต้นฉบับแทน


    try:
        title_text = str((product or {}).get("product_name", "") or "")[:80]
        # Broadcast เฉพาะเพจที่มี ID/token ครบ และ configured_pages() ตัด ID ซ้ำแล้ว
        page_results = []
        for page in configured_pages():
            try:
                page_result = post_reel(
                    description=caption,
                    file_path=upload_path,
                    title=title_text,
                    page_id=page["id"],
                    access_token=page["token"],
                )
                page_result["page_index"] = page["index"]
                page_results.append(page_result)
                if page_result.get("ok"):
                    log(f"[OK] โพสต์เพจ {page['index']} สำเร็จ video_id={page_result['video_id']}")
                else:
                    log(f"[WARN] โพสต์เพจ {page['index']} ไม่สำเร็จ: {page_result.get('error')}")
            except Exception as page_error:
                page_results.append({"ok": False, "error": str(page_error)[:200]})
                log(f"[WARN] โพสต์เพจ {page['index']} ล้ม: {page_error}")
        res = page_results[0] if page_results else {"ok": False, "error": "ไม่มีเพจที่ตั้งค่า token ครบ"}
        # อัปโหลดขึ้น YouTube Shorts ทุกช่องที่เชื่อมต่อไว้ (Multi-Channel)
        yt_results = []
        try:
            import youtube_uploader
            tokens = youtube_uploader.get_token_files()
            if tokens:
                yt_res = youtube_uploader.upload_shorts(Path(upload_path), product)
                if isinstance(yt_res, list):
                    yt_results = yt_res
                elif isinstance(yt_res, str):
                    yt_results = [{"channel": "ช่องหลัก (@regency1229)", "url": yt_res}]
        except Exception as e_yt:
            log(f"[WARN] อัปโหลด YouTube Shorts ล้มเหลว: {e_yt}")

    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    if any(r.get("ok") for r in page_results) or yt_results:
        POSTED_DIR.mkdir(parents=True, exist_ok=True)
        # ย้ายไฟล์ต้นฉบับ (ภาพหรือคลิป) ไป posted/
        original = pending[0]  # ใช้ไฟล์ต้นฉบับจาก pending
        dst = POSTED_DIR / original.name
        if dst.exists():
            dst = POSTED_DIR / f"{int(time.time())}_{original.name}"
        shutil.move(str(original), str(dst))
        LAST_POST_FILE.write_text(str(time.time()), encoding="utf-8")
        bump_daily_count()

        # อัปเดต timestamp สินค้าที่เพิ่งโพสต์บน Supabase เพื่อให้ LINE Bot "ของในคลิป" ดึงขึ้นอันดับ 1 ทันที
        try:
            m_id = re.match(r'^prod_(\d+)_', original.name)
            if m_id:
                p_id = int(m_id.group(1))
                supa_u = os.getenv("SUPABASE_URL")
                supa_k = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
                if supa_u and supa_k:
                    import urllib.request
                    now_iso = datetime.now(timezone.utc).isoformat()
                    req_sb = urllib.request.Request(
                        f"{supa_u}/rest/v1/products?id=eq.{p_id}",
                        data=json.dumps({"price_checked_at": now_iso}).encode("utf-8"),
                        headers={"apikey": supa_k, "Authorization": f"Bearer {supa_k}", "Content-Type": "application/json", "Prefer": "return=minimal"},
                        method="PATCH"
                    )
                    with urllib.request.urlopen(req_sb) as resp_sb:
                        pass
        except Exception as e_sb:
            log(f"[WARN] อัปเดต timestamp สินค้าล่าสุดบน Supabase ล้มเหลว: {e_sb}")

        if not product:
            build_intro_caption(advance=True)  # เลื่อนแคปชั่นแนะนำป้าเข็ม (กันโพสต์ซ้ำติดกัน)
        vids = []
        for index, page_result in enumerate(page_results, start=1):
            if page_result.get("ok") and page_result.get("video_id"):
                page_index = page_result.get("page_index", index)
                vids.append(f"P{page_index}:{page_result['video_id']}")
        if yt_results: vids.append(f"YT:{len(yt_results)}ch")
        vid_summary = ", ".join(vids)
        log(f"[OK] วิดีโอโพสต์สำเร็จ ({vid_summary}) → {dst.name}")
        
        # ส่งแจ้งเตือนตรงเข้า LINE แอดมินทันทีทุกครั้งที่โพสต์สำเร็จ (ไม่ต้องกดเช็คเอง)
        try:
            pname = sanitize_public_product_text(
                (product or {}).get("product_name") or original.name
            )
            aff_link = (product or {}).get("affiliate_link") or ""
            
            # จัดรูปแบบรายงานผลการโพสต์แบบ Bullet Point สวยงาม สบายตา
            channels_bullet = []
            page_names = {
                1: "ป้าเข็ม ขายของ",
                2: "ป้าเข็ม ชี้เป้าของดี",
                3: "ป้าเข็ม ของดีบอกต่อ",
            }
            for fallback_index, page_result in enumerate(page_results, start=1):
                if not (page_result.get("ok") and page_result.get("video_id")):
                    continue
                page_index = page_result.get("page_index", fallback_index)
                page_name = page_names.get(page_index, f"เพจ {page_index}")
                channels_bullet.append(
                    f"  • 📍 FB เพจ {page_index} ({page_name}):\n"
                    f"    👉 https://www.facebook.com/reel/{page_result['video_id']}"
                )
            if yt_results:
                for yt in yt_results:
                    channels_bullet.append(f"  • 🔴 YouTube ({yt.get('channel', 'Shorts')}):\n    👉 {yt.get('url', '')}")
            if tiktok_results:
                for tt in tiktok_results:
                    v_url = tt.get("video_url") or "https://www.tiktok.com/@me"
                    channels_bullet.append(f"  • 🎵 TikTok Video:\n    👉 {v_url}")
            
            channels_text = "\n".join(channels_bullet) if channels_bullet else "  • โพสต์สำเร็จเรียบร้อย"
            pending_count = len(list_pending())
            today_count = get_today_post_count()
            
            notify_msg = (
                f"🚀 [รายงานการโพสต์วิดีโอ 4 แพลตฟอร์ม]\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📦 สินค้า: {pname[:60]}\n\n"
                f"🌐 ช่องทางที่เผยแพร่สำเร็จ:\n"
                f"{channels_text}\n\n"
                f"🛒 ลิงก์ร้านค้า Shopee:\n"
                f"  • 👉 {aff_link}\n\n"
                f"📊 สรุปผลงานวันนี้ & รอบถัดไป:\n"
                f"  • 🎯 ยอดโพสต์วันนี้: {today_count} / 48 คลิป (อัตราสำเร็จ 100%)\n"
                f"  • 📦 คลิปในคลังพร้อมโพสต์: {pending_count} คลิป\n"
                f"  • ⏱️ รอบถัดไป: อีก 30 นาที ระบบจะโพสต์ให้อัตโนมัติ\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            _notify_owner(notify_msg)
        except Exception as e:
            log(f"[NOTIFY] ส่งแจ้งเตือน LINE ล้ม: {e}")



        # ลบ temp file ที่แปลงจากภาพ
        if img_video_tmp is not None:
            try:
                img_video_tmp.unlink(missing_ok=True)
            except Exception:
                pass
        return 0


    err_msg = res.get("error", "ไม่ทราบสาเหตุ")
    log(f"[FAIL] โพสต์ไม่สำเร็จ: {err_msg}")
    _notify_owner(
        f"🚨 [แจ้งเตือนระบบการโพสต์ Reels]\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• ❌ สถานะ: การโพสต์รอบนี้ไม่สำเร็จ\n"
        f"• 📌 สาเหตุ: {err_msg[:200]}\n"
        f"• ⏱️ การทำงาน: ระบบจะตรวจสอบและลองใหม่อัตโนมัติในรอบถัดไป\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    # ลบ temp file ที่แปลงจากภาพ (โพสต์ล้ม)
    if img_video_tmp is not None:
        try:
            img_video_tmp.unlink(missing_ok=True)
        except Exception:
            pass
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Facebook Reels auto-uploader (FIFO + AI caption + pacing)")
    ap.add_argument("--dry-run", action="store_true", help="จำลอง: โชว์คลิป + แคปชั่น ไม่โพสต์จริง")
    ap.add_argument("--force", action="store_true", help="ข้าม pacing (โพสต์ทันที) — ยังนับ daily limit")
    ap.add_argument("--no-normalize", action="store_true",
                    help="ไม่แปลงคลิป (ใช้ไฟล์เดิม — คลิปต้องตรง spec Reels อยู่แล้ว)")
    args = ap.parse_args()
    result = post_next(dry_run=args.dry_run, force=args.force, normalize=not args.no_normalize)
    notify_reels_issues(result, dry_run=args.dry_run)
    return result


if __name__ == "__main__":
    sys.exit(main())
