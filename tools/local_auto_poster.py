#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/local_auto_poster.py — สคริปต์โพสต์ Facebook อัตโนมัติจากเครื่อง Local

ใช้รันเมื่อเซิร์ฟเวอร์หลัก (Render) อยู่ระหว่างปรับปรุงหรือหมดโควต้า
จะดึงค่าคอนฟิกและฐานข้อมูลจริงมาทำงาน และวนลูปโพสต์ตามช่วงเวลาที่กำหนด
"""
import os
import sys
import time
import datetime

# เพิ่ม path ให้หาโมดูลใน backend และ tools เจอ
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import render_set_env

INTERVAL_MINUTES = 60  # โพสต์ทุกๆ กี่นาที (ค่าเริ่มต้น 60 นาที)

def init_environment():
    print("🔄 กำลังโหลดการตั้งค่าและ Credential จากระบบ...")
    render_set_env.API_KEY = render_set_env.get_api_key()
    items = render_set_env.fetch_env_vars()
    for it in items:
        k, v = render_set_env.decode_env_var(it.get("envVar"))
        if k:
            os.environ[k] = v
    os.environ["FB_POST_PRODUCTS"] = "1"
    print("✅ โหลดการตั้งค่าเรียบร้อยแล้ว!")

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    init_environment()
    from app.api.cron import run_facebook_product_post

    print(f"\n🚀 เริ่มต้นระบบโพสต์ Facebook อัตโนมัติ (ทุก {INTERVAL_MINUTES} นาที)")
    print("👉 กด Ctrl + C เพื่อหยุดการทำงาน\n" + "="*50)

    while True:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{now_str}] 📢 กำลังเตรียมโพสต์สินค้าลงเพจ...")
        try:
            result = run_facebook_product_post(1)
            posted = [r for r in result.get("posted", []) if r.get("posted")]
            if posted:
                for p in posted:
                    print(f"🎉 โพสต์สำเร็จ: {p.get('name') or p.get('id')} (Post ID: {p.get('post_id')})")
            else:
                print(f"ℹ️ บันทึก: {result.get('note') or result}")
        except Exception as e:
            print(f"⚠️ เกิดข้อผิดพลาดในการโพสต์: {e}")

        print(f"⏳ รออีก {INTERVAL_MINUTES} นาทีสำหรับการโพสต์รอบถัดไป...")
        time.sleep(INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
