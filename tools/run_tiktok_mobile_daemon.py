#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/run_tiktok_mobile_daemon.py — ลูปทำงาน 24/7 สำหรับ TikTok Mobile ADB Auto-Poster

คอยตรวจสอบคลัง pending_videos บน VPS/เครื่อง และโพสต์ขึ้น TikTok ผ่านสาย USB/ADB ทุก 45 นาที
"""

import os
import sys
import time
import pathlib
import subprocess

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
PYTHON_EXE = sys.executable

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [TikTok ADB Daemon] {msg}")

def main():
    log("🚀 เริ่มต้นระบบเฝ้าระวัง TikTok Mobile ADB Auto-Poster 24/7...")
    interval_seconds = 45 * 60  # โพสต์ทุก 45 นาที

    while True:
        try:
            log("🔄 กำลังตรวจสอบและโพสต์คลิป TikTok บนมือถือ Android...")
            res = subprocess.run(
                [PYTHON_EXE, str(PROJECT_ROOT / "tools" / "tiktok_adb_auto_poster.py")],
                cwd=str(PROJECT_ROOT),
                capture_output=False
            )
            log(f"✅ ทำงานเสร็จสิ้นในรอบนี้ (Exit Code: {res.returncode})")
        except Exception as e:
            log(f"⚠️ เกิดข้อผิดพลาดในลูป: {e}")

        log(f"⏳ พักรอเป็นเวลา 45 นาที ก่อนเริ่มรอบถัดไป...")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    main()
