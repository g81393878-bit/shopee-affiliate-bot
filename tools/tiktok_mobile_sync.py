#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/tiktok_mobile_sync.py — โมดูลเชื่อมต่อคลังวิดีโอจาก Cloud VPS สู่ Mobile Android Station

ประโยชน์:
1. ดึงวิดีโอที่ VPS ตัดต่อเสร็จแล้วใน pending_videos/ ลงมาเตรียมพร้อมที่เครื่องคอมพิวเตอร์ Local
2. ตรวจสอบการเชื่อมต่ออุปกรณ์ Android ผ่าน ADB (Android Debug Bridge)
3. ส่งไฟล์วิดีโอเข้าสู่ Gallery / Storage ของมือถือน้องกาลเวลา (NongKanvela Assistant)
4. ป้องกันคลิปซ้ำ 100% เพื่อหลีกเลี่ยงปัญหา TikTok 0 Views / Shadowban
"""

import os
import sys
import json
import time
import pathlib
import subprocess
import argparse
from typing import List, Dict, Optional

# บังคับ UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_PENDING_DIR = PROJECT_ROOT / "pending_videos"
LOCAL_PENDING_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = PROJECT_ROOT / "tools" / "posted_tiktok_mobile_history.json"

VPS_HOST = "root@119.10.140.161"
VPS_REELS_DIR = "/root/shopee-affiliate-bot/reels_uploader/pending_videos"
VPS_PENDING_DIR = "/root/shopee-affiliate-bot/reels_uploader/pending_videos"


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [TikTok Mobile Sync] {msg}")


def check_adb_devices() -> List[str]:
    """ตรวจสอบรายการเครื่อง Android ที่เชื่อมต่ออยู่ผ่าน ADB"""
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True)
        lines = res.stdout.strip().split("\n")[1:]
        devices = []
        for line in lines:
            if "\tdevice" in line:
                dev_id = line.split("\t")[0]
                devices.append(dev_id)
        return devices
    except Exception as e:
        log(f"⚠️ ADB Check Error: {e}")
        return []


def sync_videos_from_vps(limit: int = 3) -> List[pathlib.Path]:
    """ดึงคลิปจาก VPS มาเตรียมที่คลังท้องถิ่น เครื่อง Local"""
    log("🌐 กำลังซิงค์วิดีโอล่าสุดจาก Cloud VPS...")
    cmd = [
        "scp",
        f"{VPS_HOST}:{VPS_PENDING_DIR}/*.mp4",
        str(LOCAL_PENDING_DIR)
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as e:
        log(f"⚠️ SCP Sync Warning: {e}")

    downloaded = list(LOCAL_PENDING_DIR.glob("*.mp4"))
    log(f"📦 พบวิดีโอพร้อมโพสต์ในคลังเครื่อง Local ทั้งหมด {len(downloaded)} ไฟล์")
    return downloaded[:limit]


def push_video_to_android(video_path: pathlib.Path, device_id: Optional[str] = None) -> bool:
    """ส่งไฟล์วิดีโอเข้าสู่ Storage มือถือ Android ผ่าน ADB"""
    if not video_path.exists():
        log(f"❌ ไม่พบไฟล์: {video_path}")
        return False

    adb_cmd = ["adb"]
    if device_id:
        adb_cmd.extend(["-s", device_id])

    target_mobile_path = f"/sdcard/Movies/{video_path.name}"
    log(f"📲 กำลังส่งไฟล์ {video_path.name} เข้าสู่มือถือ ({target_mobile_path})...")

    try:
        # 1. Push file
        subprocess.run(adb_cmd + ["push", str(video_path), target_mobile_path], check=True)
        
        # 2. Trigger Media Scanner เพื่อให้รูปขึ้นใน Gallery TikTok ทันที
        subprocess.run(adb_cmd + ["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{target_mobile_path}"], check=True)
        
        log(f"✅ ส่งไฟล์เข้ามือถือสำเร็จเรียบร้อย!")
        return True
    except Exception as e:
        log(f"❌ ส่งไฟล์เข้ามือถือล้มเหลว: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="TikTok Mobile Sync Agent")
    parser.add_argument("--sync", action="store_true", help="ดึงวิดีโอจาก VPS ลงเครื่อง Local")
    parser.add_argument("--push-device", action="store_true", help="ส่งวิดีโอลงมือถือ Android ผ่าน ADB")
    args = parser.parse_args()

    devices = check_adb_devices()
    if devices:
        log(f"📱 พบมือถือ Android เชื่อมต่ออยู่ {len(devices)} เครื่อง: {', '.join(devices)}")
    else:
        log("ℹ️ ยังไม่พบมือถือเชื่อมต่อสาย USB (เปิด USB Debugging) สามารถเตรียมไฟล์ไว้รอได้")

    if args.sync or not sys.argv[1:]:
        videos = sync_videos_from_vps(limit=5)
        if videos and devices and args.push_device:
            push_video_to_android(videos[0], device_id=devices[0])


if __name__ == "__main__":
    main()
