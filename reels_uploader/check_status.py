import os
import sys
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
PENDING_DIR = ROOT / "pending_videos"
POSTED_DIR = ROOT / "posted"
LAST_POST_FILE = ROOT / "last_post_time.txt"
DAILY_COUNT_FILE = ROOT / "posts_today.txt"

# Force UTF-8 encoding for printing Thai characters on Windows CMD
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

print("====================================================")
print("          ตรวจสอบสถานะระบบ Reels Uploader")
print("====================================================")

# 1. ยอดการโพสต์วันนี้
max_limit = 10
today_count = 0
if DAILY_COUNT_FILE.exists():
    try:
        date_str, count_str = DAILY_COUNT_FILE.read_text(encoding="utf-8").strip().split()
        today = datetime.now().strftime("%Y-%m-%d")
        if date_str == today:
            today_count = int(count_str)
    except Exception:
        pass
print(f"📊 โควต้าการโพสต์วันนี้: โพสต์แล้ว {today_count} / {max_limit} คลิป")

# 2. เวลาโพสต์ล่าสุด
if LAST_POST_FILE.exists():
    try:
        last_ts = float(LAST_POST_FILE.read_text(encoding="utf-8").strip())
        last_time = datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M:%S")
        print(f"🕒 โพสต์คลิปล่าสุดเมื่อ: {last_time}")
    except Exception:
        print("🕒 โพสต์คลิปล่าสุดเมื่อ: (ไม่พบข้อมูล)")
else:
    print("🕒 โพสต์คลิปล่าสุดเมื่อ: (ยังไม่มีประวัติการโพสต์)")

# 3. ลำดับคิวรอโพสต์ (Pending)
pending_clips = sorted(p for p in PENDING_DIR.glob("*.mp4") if p.is_file())
print(f"\n📥 คิวรอโพสต์ใน pending_videos/ (ทั้งหมด {len(pending_clips)} คลิป):")
if pending_clips:
    for idx, clip in enumerate(pending_clips, 1):
        status = " (คลิปถัดไปที่จะโพสต์ 🚀)" if idx == 1 else ""
        print(f"  {idx}. {clip.name}{status}")
else:
    print("  ❌ ไม่มีคลิปค้างในคิวรอโพสต์ (ระบบจะรีไซเคิลคลิปเก่ามาโพสต์อัตโนมัติหากไม่มีคลิปใหม่)")

# 4. ประวัติโพสต์เสร็จแล้ว (Posted)
posted_clips = sorted(p for p in POSTED_DIR.glob("*.mp4") if p.is_file())
print(f"\n📤 ประวัติคลิปที่โพสต์ไปแล้วใน posted/ (ทั้งหมด {len(posted_clips)} คลิป):")
if posted_clips:
    # โชว์ล่าสุด 5 คลิป
    show_clips = posted_clips[-5:]
    if len(posted_clips) > 5:
        print(f"  ... (และคลิปก่อนหน้านี้อีก {len(posted_clips) - 5} คลิป) ...")
    for idx, clip in enumerate(show_clips, 1):
        print(f"  - {clip.name}")
else:
    print("  ❌ ยังไม่มีคลิปในประวัติการโพสต์")

print("====================================================")
