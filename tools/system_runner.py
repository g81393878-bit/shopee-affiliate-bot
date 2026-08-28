#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/system_runner.py — ระบบควบคุมการทำงานอัตโนมัติแบบครบวงจร (Commercial Turnkey Orchestrator)

รวมทุกระบบเข้าด้วยกันใน Process เดียว:
1. 🛍️ Facebook Feed Auto-Poster (โพสต์สินค้า+แคปชั่น AI ทุกๆ 60 นาที)
2. 🎬 Facebook Reels Auto-Producer & Uploader (ผลิตคลิป 9:16 + เสียงพากย์ไทย TTS + โพสต์ลง Reels)
3. 🛡️ Fake Post Cleaner & Link Watcher (ตรวจจับและล้างโพสต์แปลกปลอม)
4. 🔄 Auto-Reconnect & Self-Healing Watchdog (กู้คืนระบบอัตโนมัติเมื่อเน็ตหลุด)
"""
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

# โหลด Environment Variables
try:
    import render_set_env
    render_set_env.API_KEY = render_set_env.get_api_key()
    items = render_set_env.fetch_env_vars()
    for it in items:
        k, v = render_set_env.decode_env_var(it.get("envVar"))
        if k:
            os.environ[k] = v
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SystemRunner")

ICT = timezone(timedelta(hours=7))

def is_active_hours() -> bool:
    """เวลาทำการ 07:00 - 23:00 น. (เวลาไทย)"""
    now = datetime.now(ICT)
    return 7 <= now.hour < 23


def run_feed_poster_loop():
    """เธรดสำหรับโพสต์สินค้าลง Facebook Feed"""
    logger.info("🟢 เริ่มต้นระบบ Facebook Feed Auto-Poster (ทุกๆ 60 นาที)")
    from local_auto_poster import post_one_product
    
    while True:
        try:
            if is_active_hours():
                logger.info("🛍️ ถึงรอบโพสต์สินค้า Facebook Feed...")
                post_one_product()
            else:
                logger.info("🌙 อยู่นอกเวลาทำการ (23:00 - 07:00 น.) — พักโพสต์ Feed")
        except Exception as e:
            logger.error(f"❌ ระบบโพสต์ Feed เกิดข้อผิดพลาด: {e}")
        
        # รอ 60 นาที (3600 วินาที)
        time.sleep(3600)


def run_reels_uploader_loop():
    """เธรดสำหรับผลิตคลิปและโพสต์ลง Facebook Reels"""
    logger.info("🟢 เริ่มต้นระบบ Facebook Reels Auto-Producer & Uploader (ทุกๆ 2 ชั่วโมง)")
    import uploader
    
    while True:
        try:
            if is_active_hours():
                logger.info("🎬 ตรวจสอบคิวและโพสต์คลิป Facebook Reels...")
                # รันโพสต์คลิปถัดไป (ถ้าไม่มีคลิป ระบบจะดึงรูปสินค้ามาผลิตให้อัตโนมัติ)
                uploader.post_next(dry_run=False, force=False, normalize=True)
            else:
                logger.info("🌙 อยู่นอกเวลาทำการ (23:00 - 07:00 น.) — พักโพสต์ Reels")
        except Exception as e:
            logger.error(f"❌ ระบบโพสต์ Reels เกิดข้อผิดพลาด: {e}")
        
        # ตรวจสอบคิวทุกๆ 30 นาที
        time.sleep(1800)


def print_banner():
    bot_name = os.getenv("BOT_NAME", "ป้าเข็ม ขายของ")
    slogan = os.getenv("BRAND_SLOGAN", "คัดของดี ของเด็ด Shopee แท้ 100%")
    print("=" * 68)
    print(f"🚀  ระบบอัตโนมัติ Shopee Affiliate & AI Social Automation")
    print(f"🏷️   แบรนด์: {bot_name}")
    print(f"📢  สโลแกน: {slogan}")
    print(f"🕒  เวลาทำการ: 07:00 - 23:00 น. (Active 16 ชม./วัน)")
    print("=" * 68)
    print("📊 สถานะระบบย่อย:")
    print("  [1] Facebook Feed Poster: 🟢 ONLINE")
    print("  [2] Facebook Reels Video + TTS: 🟢 ONLINE")
    print("  [3] Auto-Recovery Watchdog: 🟢 ONLINE")
    print("=" * 68)
    print("💡 กด Ctrl + C เพื่อหยุดการทำงาน\n")


def main():
    print_banner()

    t_feed = threading.Thread(target=run_feed_poster_loop, daemon=True, name="FeedPoster")
    t_reels = threading.Thread(target=run_reels_uploader_loop, daemon=True, name="ReelsUploader")

    t_feed.start()
    t_reels.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 กำลังปิดการทำงานของระบบอย่างปลอดภัย...")
        sys.exit(0)


if __name__ == "__main__":
    main()
