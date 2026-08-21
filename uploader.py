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
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# บังคับ stdout UTF-8 (กัน emoji/ไทย พังบน Windows console ที่ใช้ cp874/850)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # ตอนถูก import ใน pytest stdout เป็น capture object ที่ reconfigure ไม่ได้

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND / ".env")

from app.services.facebook_poster import PAGE_ID, post_reel  # noqa: E402
from app.services.facebook_intro import intro_posts  # noqa: E402
from app.services.bot_profile import LINE_OA_URL  # noqa: E402


PENDING_DIR = ROOT / "pending_videos"
POSTED_DIR = ROOT / "posted"
PRODUCTS_JSON = ROOT / "products.json"
LAST_POST_FILE = ROOT / "last_post_time.txt"
DAILY_COUNT_FILE = ROOT / "posts_today.txt"
INTRO_STATE_FILE = ROOT / ".uploader_intro_state.json"
NOTIFY_STATE_FILE = ROOT / ".reels_notify_state.json"  # throttle การแจ้งเตือน (persist ข้าม process)
LOG_FILE = ROOT / "uploader_execution.log"

DEFAULT_SPACING_HOURS = 3.0
DEFAULT_MAX_PER_DAY = 30  # Reels API จำกัด 30 โพสต์/24 ชม.


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


def list_pending() -> list:
    """คลิป .mp4 ใน pending_videos/ เรียง FIFO (ตามชื่อไฟล์)"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in PENDING_DIR.glob("*.mp4") if p.is_file())


def recycle_clips() -> bool:
    """Auto-recycle: pending ว่าง → คัดลอกคลิปจาก posted/ กลับมาโพสต์ใหม่.

    คัดลอก (ไม่ลบ) — posted/ ยังเก็บคลิปต้นฉบับไว้
    คืน True = recycling เกิดขึ้น (มีคลิปกลับมา)
    """
    posted_clips = sorted(p for p in POSTED_DIR.glob("*.mp4") if p.is_file())
    if not posted_clips:
        return False
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    for src in posted_clips:
        dst = PENDING_DIR / src.name
        if not dst.exists():
            import shutil
            shutil.copy2(str(src), str(dst))
    recycled = list_pending()
    if recycled:
        log(f"♻️ Recycle: คัดลอกคลิปจาก posted/ กลับ {len(recycled)} ตัว → pending_videos/")
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
    """push LINE แจ้งเจ้าของร้าน (best-effort — ล้มไม่พังโค้ด; เคารพ LINE push quota)

    ต่างจาก facebook_poster.notify_owner_once (prod-only) — ตัวนี้ใช้ได้บนเครื่อง local
    ที่รัน uploader อยู่ (ไม่มีเกต _is_prod) เพราะ Reels uploader ทำงานฝั่งเครื่อง
    """
    try:
        from linebot import LineBotApi
        from linebot.models import TextSendMessage
        from app.services.line_quota import push_guard
        from app.db import SessionLocal
        token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or ""
        if not token or "mock" in token.lower():
            log("[NOTIFY] ข้ามแจ้งเจ้าของ (ไม่มี LINE token)")
            return False
        admin_uid = (os.getenv("ADMIN_LINE_USER_ID")
                     or "Uc88eb3896b0e4bcc5fbaa9b78ac1294e").strip()
        db = SessionLocal()
        try:
            if not push_guard(db):
                log("[NOTIFY] ข้ามแจ้งเจ้าของ (LINE push quota หมด)")
                return False
        finally:
            db.close()
        LineBotApi(token).push_message(admin_uid, TextSendMessage(text=text[:1500]))
        log(f"[NOTIFY] แจ้งเจ้าของแล้ว: {text.splitlines()[0][:60]}")
        return True
    except Exception as e:
        log(f"[NOTIFY] push ล้ม: {e}")
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
                "⚠️ คิว Reels ว่างแล้ว!\n\n"
                "ไม่มีคลิปรอโพสต์ใน pending_videos/ — ใส่คลิปใหม่ให้หน่อย\n"
                "(จะไม่แจ้งซ้ำจนกว่าจะถึงพรุ่งนี้)"
            )
        return

    # 2) โพสต์ล้มต่อเนื่อง
    if post_result != 0:
        streak = int(state.get("fail_streak", 0)) + 1
        state["fail_streak"] = streak
        if streak >= 2 and int(state.get("last_fail_notified_streak", 0)) < 2:
            state["last_fail_notified_streak"] = streak
            tail = _log_tail(1)
            detail = f"\n{tail[0][:200]}" if tail else ""
            _notify_owner(
                f"❌ Reels โพสต์ล้ม {streak} ครั้งติด!\n\n"
                f"โพสต์ไม่สำเร็จต่อเนื่อง — ตรวจ uploader_execution.log / token / ลิงก์{detail}"
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


def build_caption(product: dict) -> str:
    """เขียนแคปชั่น Reels — คลิปสินค้า (มีใน products.json) ใช้ AI/template,
    คลิปที่ไม่ใช่สินค้าใช้แคปชั่นแนะนำป้าเข็มจากคลัง (หมุนเวียน)."""
    if not product:
        return build_intro_caption(advance=False)
    name = (product or {}).get("product_name") or "สินค้าเด็ดจากป้าเข็ม"
    price = (product or {}).get("price") or ""
    link = (product or {}).get("affiliate_link") or ""
    category = (product or {}).get("category") or ""

    template = f"✨ {name}" + (f" — {price} บาท" if price else "") + "\n"
    if link:
        template += f"🛒 {link}\n"
    template += "\n#ของดีบอกต่อ #ป้าป้ายยา"

    # ลอง AI (Groq) — พัง/ไม่มี key → template
    try:
        from app.services.llm_clients import groq_clients, call_with_backoff
        clients = groq_clients()
        if not clients:
            return template
        prompt = (
            "เขียนแคปชั่น Facebook Reels ภาษาไทยสั้น ๆ กระชับ มี emoji ป้ายยาสินค้า:\n"
            f"- สินค้า: {name}\n- หมวด: {category}\n- ราคา: {price} บาท\n"
            f"- ลิงก์: {link or '(ไม่มี)'}\n\n"
            "ตอบเฉพาะข้อความแคปชั่น ไม่มีคำอธิบาย ไม่มีเครื่องหมายคำพูดครอบ\n"
            "ห้ามแปะลิงก์ปลอม — ใช้ลิงก์ที่ให้เท่านั้น"
        )

        def _gen():
            last_exc = None
            for c in clients:
                try:
                    return c.chat.completions.create(
                        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.8,
                        max_tokens=300,
                    )
                except Exception as e:
                    last_exc = e
            raise (last_exc or RuntimeError("no groq client"))

        resp = call_with_backoff(_gen)
        text = (resp.choices[0].message.content or "").strip().strip('"“”').strip()
        if link and link not in text:
            text = f"{text}\n\n🛒 {link}"
        return text[:900]
    except Exception as e:
        log(f"[WARN] AI caption ล้ม ({e}) — ใช้ template")
        return template


def post_next(dry_run: bool, force: bool, normalize: bool = True) -> int:
    pending = list_pending()
    if not pending:
        # Auto-recycle: คัดลอกคลิปจาก posted/ กลับมาโพสต์ใหม่
        if recycle_clips():
            pending = list_pending()
        else:
            log("ไม่มีคลิปใน pending_videos/ — จบ")
            return 0

    spacing = _env_float("POSTING_SPACING_HOURS", DEFAULT_SPACING_HOURS)
    max_per_day = int(_env_float("MAX_REELS_PER_DAY", DEFAULT_MAX_PER_DAY))

    if not force and not pacing_ok(spacing):
        log(f"ยังไม่ถึงเวลา (spacing {spacing} ชม.) — ข้าม ไม่โพสต์")
        return 0
    if not daily_ok(max_per_day):
        log(f"ครบลิมิต {max_per_day} โพสต์/วัน แล้ว — ข้าม ไม่โพสต์")
        return 0

    video = pending[0]
    product = load_products().get(video.name, {})
    caption = build_caption(product)

    if dry_run:
        log(f"[DRY-RUN] จะโพสต์ Reels: {video.name} (PAGE_ID={PAGE_ID})")
        log(f"[DRY-RUN] normalize: {'ON (แปลง 9:16 อัตโนมัติ)' if normalize else 'OFF (ใช้ไฟล์เดิม)'}")
        log(f"[DRY-RUN] caption:\n{caption}")
        return 0

    # แปลงคลิปให้ตรง spec Reels ก่อนโพสต์ (9:16/1080p/30fps/≤90s) — ถ้าไม่สั่ง --no-normalize
    upload_path = str(video)
    tmp = None
    if normalize:
        fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="reels_norm_")
        os.close(fd)
        tmp = Path(tmp_path)
        log(f"[NORM] แปลงคลิปเป็น 9:16/1080p/30fps: {video.name} ...")
        if normalize_video(video, tmp):
            upload_path = str(tmp)
        else:
            tmp = None  # แปลงล้ม → ใช้ไฟล์ต้นฉบับแทน

    try:
        log(f"[POST] กำลังอัปโหลด Reels: {video.name} → เพจ {PAGE_ID} ...")
        res = post_reel(description=caption, file_path=upload_path,
                        title=(product or {}).get("product_name", "") or "")
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    if res["ok"]:
        POSTED_DIR.mkdir(parents=True, exist_ok=True)
        dst = POSTED_DIR / video.name
        if dst.exists():
            dst = POSTED_DIR / f"{int(time.time())}_{video.name}"
        shutil.move(str(video), str(dst))
        LAST_POST_FILE.write_text(str(time.time()), encoding="utf-8")
        bump_daily_count()
        if not product:
            build_intro_caption(advance=True)  # เลื่อนแคปชั่นแนะนำป้าเข็ม (กันโพสต์ซ้ำติดกัน)
        log(f"[OK] Reels โพสต์สำเร็จ video_id={res['video_id']} → {dst.name}")
        return 0

    log(f"[FAIL] โพสต์ไม่สำเร็จ: {res['error']}")
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
