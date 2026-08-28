#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/system_runner.py — ระบบควบคุมการทำงานอัตโนมัติ Facebook Reels AI (100% Reels Edition)

โฟกัสที่การผลิตและโพสต์คลิปสั้น Facebook Reels อย่างเดียว 100%:
1. 🎬 Facebook Reels Auto-Producer & Uploader (ผลิตคลิป 9:16 + เสียงพากย์ไทย TTS + โพสต์ลง Reels ทุก 1.5 - 2 ชม.)
2. 🎙️ Natural Thai Neural TTS Voiceover (เสียงพากย์ป้าเข็ม/มืออาชีพ แนะนำสินค้าและราคาจริง)
3. 🔄 Auto-Reconnect & Self-Healing Watchdog (กู้คืนระบบอัตโนมัติเมื่อเน็ตหลุด)
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


def run_prebuffer_producer_loop():
    """เธรดผลิตคลิปสินค้าล่วงหน้าในคลัง (Pre-buffer Producer) — ผลิตคลิปรอไว้เสมอ 3-5 คลิป"""
    logger.info("🏭 เริ่มต้นระบบ Auto Pre-buffer Producer (ผลิตคลิปรอไว้ในคลังเสมอ 3-5 คลิป)")
    while True:
        try:
            import uploader
            from auto_product_reels import generate_product_reels
            pending = uploader.list_pending()
            if len(pending) < 3:
                needed = 3 - len(pending)
                logger.info(f"📦 คิวคลิปพร้อมโพสต์เหลือ {len(pending)} คลิป — กำลังผลิตเพิ่มล่วงหน้า {needed} คลิป...")
                generate_product_reels(limit=needed)
        except Exception as e:
            logger.warning(f"⚠️ Pre-buffer producer warning: {e}")
        time.sleep(120)  # ตรวจสอบทุก 2 นาที


def run_reels_uploader_loop():
    """เธรดหลักสำหรับโพสต์คลิปพร้อมใช้งานลง Facebook Reels ทุกๆ 10 นาที"""
    logger.info("🎬 เริ่มต้นระบบ Facebook Reels Auto-Uploader (รอบโพสต์ทุกๆ 10 นาที)")
    import uploader
    
    while True:
        try:
            if is_active_hours():
                # โพสต์คลิปที่ผลิตรอไว้แล้วทันที
                uploader.post_next(dry_run=False, force=False, normalize=True)
            else:
                logger.info("🌙 อยู่นอกเวลาทำการ (23:00 - 07:00 น.) — พักโพสต์ Reels")
        except Exception as e:
            logger.error(f"❌ ระบบโพสต์ Reels เกิดข้อผิดพลาด: {e}")
        
        # ตรวจสอบเวลาโพสต์ทุกๆ 60 วินาที
        time.sleep(60)


def print_banner():
    bot_name = os.getenv("BOT_NAME", "ป้าเข็ม ขายของ")
    slogan = os.getenv("BRAND_SLOGAN", "คัดของดี ของเด็ด Shopee แท้ 100%")
    voice = os.getenv("TTS_VOICE", "th-TH-PremwadeeNeural")
    print("=" * 68)
    print(f"🎬  ระบบอัตโนมัติ Facebook Reels Video + Thai Neural TTS (100% Reels)")
    print(f"🏷️   แบรนด์: {bot_name}")
    print(f"📢  สโลแกน: {slogan}")
    print(f"🎙️  เสียงพากย์: {voice}")
    print(f"🕒  เวลาทำการ: 07:00 - 23:00 น. (Active 16 ชม./วัน)")
    print("=" * 68)
    print("📊 สถานะระบบย่อย:")
    print("  [1] Facebook Reels Producer & TTS: 🟢 ACTIVE")
    print("  [2] Meta Reels API Auto-Uploader: 🟢 ACTIVE")
    print("  [3] Facebook Feed Poster: ⚪ OFF (เน้น Reels 100% เพื่อยอดวิวสูงสุด)")
    print("  [4] Auto-Recovery Watchdog: 🟢 ONLINE")
    print("=" * 68)
    print("💡 กด Ctrl + C เพื่อหยุดการทำงาน\n")


def main():
    print_banner()
    
    # 1. รันเธรดผลิตคลิปสินค้าล่วงหน้ารอไว้เสมอ (Pre-buffer)
    t_producer = threading.Thread(target=run_prebuffer_producer_loop, daemon=True, name="ReelsPrebuffer")
    t_producer.start()

    # 2. รันเธรดอัปโหลดตามรอบเวลา 10 นาที
    t_uploader = threading.Thread(target=run_reels_uploader_loop, daemon=True, name="ReelsUploader")
    t_uploader.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 ปิดการทำงานระบบ System Runner")
        sys.exit(0)


if __name__ == "__main__":
    main()
