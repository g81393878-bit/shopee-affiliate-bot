#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/smart_keep_alive.py — สคริปต์กระตุ้นเซิร์ฟเวอร์ Render แบบประหยัดโควต้า

กระตุ้นเซิร์ฟเวอร์เฉพาะช่วงเวลาสำคัญ (เช่น 07:00 - 23:00 น.) ทุกๆ 10 นาที
เพื่อให้เซิร์ฟเวอร์ได้พักช่วงดึก และไม่กินชั่วโมง Render Free Tier จนหมดโควต้าปลายเดือน
"""
import os
import sys
import time
import datetime
import urllib.request

SERVICE_URL = "https://shopee-affiliate-bot-9e9n.onrender.com/health"
PING_INTERVAL_SECONDS = 600  # 10 นาที
ACTIVE_START_HOUR = 7        # เริ่มตื่น 07:00 น.
ACTIVE_END_HOUR = 23         # เริ่มพัก 23:00 น.

def ping_service():
    now = datetime.datetime.now()
    current_hour = now.hour
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # ตรวจสอบช่วงเวลาที่ควรให้เซิร์ฟเวอร์ตื่น
    if ACTIVE_START_HOUR <= current_hour < ACTIVE_END_HOUR:
        try:
            req = urllib.request.Request(
                SERVICE_URL,
                headers={"User-Agent": "SmartKeepAlive/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"[{now_str}] 🟢 Ping สำเร็จ ({SERVICE_URL}) -> Status: {resp.status}")
        except Exception as e:
            print(f"[{now_str}] 🔴 Ping ไม่สำเร็จ: {e}")
    else:
        print(f"[{now_str}] 💤 อยู่นอกช่วงเวลาทำการ ({ACTIVE_START_HOUR}:00 - {ACTIVE_END_HOUR}:00) — ปล่อยเซิร์ฟเวอร์พักเพื่อประหยัดโควต้า")

def main():
    print(f"🚀 เริ่มต้น Smart Keep-Alive สำหรับ {SERVICE_URL}")
    print(f"⏰ เวลาตื่น: {ACTIVE_START_HOUR}:00 - {ACTIVE_END_HOUR}:00 น. | Ping ทุก {PING_INTERVAL_SECONDS//60} นาที")
    print("👉 กด Ctrl + C เพื่อหยุดการทำงาน\n" + "="*50)

    while True:
        ping_service()
        time.sleep(PING_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
