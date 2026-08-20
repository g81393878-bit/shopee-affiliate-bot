#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""uploader.py — Facebook Reels auto-uploader (FIFO + AI caption + pacing)

ดึงคลิป .mp4 จาก pending_videos/ (FIFO) → เขียนแคปชั่น AI (Groq) + แปะลิงก์
Shopee ตาม products.json → อัปโหลด Reels ผ่าน 3-step video upload session
(init → upload → publish) → ย้ายคลิปไป posted/ แล้วบันทึกเวลาล่าสุด (pacing)

ใช้งาน:
  python uploader.py                  # โพสต์คลิปถัดไป 1 ตัว (ถ้าถึงเวลา spacing)
  python uploader.py --dry-run        # จำลอง: โชว์คลิป + แคปชั่น ไม่โพสต์จริง
  python uploader.py --force          # ข้าม pacing (โพสต์ทันที) — ยังนับ daily limit

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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# บังคับ stdout UTF-8 (กัน emoji/ไทย พังบน Windows console ที่ใช้ cp874/850)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND / ".env")

from app.services.facebook_poster import PAGE_ID, post_reel  # noqa: E402

PENDING_DIR = ROOT / "pending_videos"
POSTED_DIR = ROOT / "posted"
PRODUCTS_JSON = ROOT / "products.json"
LAST_POST_FILE = ROOT / "last_post_time.txt"
DAILY_COUNT_FILE = ROOT / "posts_today.txt"
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


def build_caption(product: dict) -> str:
    """เขียนแคปชั่น Reels — AI (Groq) ถ้ามี key, ไม่งั้น template"""
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


def post_next(dry_run: bool, force: bool) -> int:
    pending = list_pending()
    if not pending:
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
        log(f"[DRY-RUN] caption:\n{caption}")
        return 0

    log(f"[POST] กำลังอัปโหลด Reels: {video.name} → เพจ {PAGE_ID} ...")
    res = post_reel(description=caption, file_path=str(video),
                    title=(product or {}).get("product_name", "") or "")
    if res["ok"]:
        POSTED_DIR.mkdir(parents=True, exist_ok=True)
        dst = POSTED_DIR / video.name
        if dst.exists():
            dst = POSTED_DIR / f"{int(time.time())}_{video.name}"
        shutil.move(str(video), str(dst))
        LAST_POST_FILE.write_text(str(time.time()), encoding="utf-8")
        bump_daily_count()
        log(f"[OK] Reels โพสต์สำเร็จ video_id={res['video_id']} → {dst.name}")
        return 0

    log(f"[FAIL] โพสต์ไม่สำเร็จ: {res['error']}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Facebook Reels auto-uploader (FIFO + AI caption + pacing)")
    ap.add_argument("--dry-run", action="store_true", help="จำลอง: โชว์คลิป + แคปชั่น ไม่โพสต์จริง")
    ap.add_argument("--force", action="store_true", help="ข้าม pacing (โพสต์ทันที) — ยังนับ daily limit")
    args = ap.parse_args()
    return post_next(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
