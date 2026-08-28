#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/run_local_bot.py — รันเซิร์ฟเวอร์บอท LINE OA + Webhook บนเครื่องตัวเองพร้อม Cloudflare Tunnel

สคริปต์นี้จะ:
1. โหลด Environment Variables และต่อฐานข้อมูลจริง (Supabase)
2. เปิดรัน FastAPI Server (Uvicorn) บน port 8000
3. เปิด Cloudflare Tunnel สร้าง URL สาธารณะ (HTTPS) อัตโนมัติสำหรับ LINE Webhook
"""
import os
import sys
import time
import subprocess
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import render_set_env

def init_env():
    print("🔄 กำลังโหลดค่าคอนฟิกและ Credential จากระบบ...")
    render_set_env.API_KEY = render_set_env.get_api_key()
    items = render_set_env.fetch_env_vars()
    for it in items:
        k, v = render_set_env.decode_env_var(it.get("envVar"))
        if k:
            os.environ[k] = v
    print("✅ โหลดการตั้งค่าเรียบร้อยแล้ว!")

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    init_env()

    # เริ่มรัน Uvicorn ใน Backend
    backend_dir = os.path.join(ROOT_DIR, "backend")
    python_exe = sys.executable

    print("\n🚀 [1/2] กำลังเริ่มรัน FastAPI Server (Uvicorn) บน port 8000...")
    uvicorn_cmd = [
        python_exe, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000"
    ]
    server_proc = subprocess.Popen(
        uvicorn_cmd,
        cwd=backend_dir,
        env=os.environ.copy()
    )

    time.sleep(3)

    print("🌐 [2/2] กำลังเปิด Cloudflare Tunnel เพื่อสร้าง HTTPS URL สาธารณะสำหรับ LINE OA...")
    cloudflared_path = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if not os.path.exists(cloudflared_path):
        cloudflared_path = "cloudflared"

    tunnel_cmd = [
        cloudflared_path, "tunnel",
        "--url", "http://127.0.0.1:8000"
    ]
    
    tunnel_proc = subprocess.Popen(
        tunnel_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    tunnel_url = ""
    print("\n⏳ กำลังค้นหา Public Tunnel URL...")
    for line in tunnel_proc.stdout:
        print(line, end="")
        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if match:
            tunnel_url = match.group(0)
            webhook_url = f"{tunnel_url}/api/webhooks/line"
            print("\n" + "="*60)
            print(f"🎉 Cloudflare Tunnel พร้อมใช้งานแล้ว!")
            print(f"👉 Public URL: {tunnel_url}")
            print(f"👉 นำ URL นี้ไปใส่ใน LINE Developers (Webhook settings):")
            print(f"   🔗 {webhook_url}")
            print("="*60 + "\n")
            break

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 กำลังปิดเซิร์ฟเวอร์...")
        server_proc.terminate()
        tunnel_proc.terminate()

if __name__ == "__main__":
    main()
