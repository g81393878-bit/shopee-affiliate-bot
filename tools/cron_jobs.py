#!/usr/bin/env python3
"""สร้าง + ตรวจสอบ cron jobs ของป้าเข็มบน cron-job.org ผ่าน API (idempotent)

วิธีใช้:
    python tools/cron_jobs.py                  # อ่าน CJKEY + CRON_TOKEN จาก backend/.env
    CJKEY=<API key> python tools/cron_jobs.py  # หรือส่ง CJKEY ผ่าน env แทน
    python tools/cron_jobs.py --dry-run        # ตรวจสอบอย่างเดียว (ไม่สร้าง/แก้ job)

- อ่าน CJKEY + CRON_TOKEN จาก backend/.env (fallback เมื่อไม่มีใน os.environ)
- LIST jobs เดิมก่อน → สร้างเฉพาะตัวที่ยังไม่มี (เทียบด้วย title) → LIST อีกครั้งยืนยัน
- รันซ้ำได้ปลอดภัย (ไม่สร้างซ้ำ)
- API key เป็นความลับ — ไม่ถูกเขียนลงไฟล์/ไม่ขึ้น commit (อ่านจาก env เท่านั้น)

อ้างอิง API: https://api.cron-job.org  (PUT /jobs จำกัด 1 req/s, 5 req/min)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# Windows console มักเป็น cp874 (พิมพ์อีโมจิ/ไทยบางตัวไม่ได้) — บังคับ stdout/stderr เป็น UTF-8
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://shopee-affiliate-bot-9e9n.onrender.com"
API = "https://api.cron-job.org"

GET, POST = 0, 1  # requestMethod ตาม docs ของ cron-job.org


def _env_value(key):
    """อ่านค่า key จาก backend/.env (gitignored) — คืน None ถ้าไม่พบ"""
    env_path = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


def api_call(method, path, key, payload=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", "Bearer " + key)
    data = None
    if payload is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(payload).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def jobs(key):
    code, out = api_call("GET", "/jobs", key)
    if code != 200:
        raise SystemExit(f"GET /jobs ล้มเหลว ({code}): {out}")
    return out.get("jobs", [])


def make_job(title, url, method, schedule):
    return {
        "title": title,
        "url": url,
        "enabled": True,
        "saveResponses": False,
        "requestMethod": method,
        "requestTimeout": 300,
        "redirectSuccess": False,
        "folderId": 0,
        "schedule": {
            "timezone": "Asia/Bangkok",
            "expiresAt": 0,
            "hours": schedule["hours"],
            "mdays": [-1],
            "minutes": schedule["minutes"],
            "months": [-1],
            "wdays": [-1],
        },
    }


def main():
    key = os.environ.get("CJKEY") or _env_value("CJKEY")
    if not key:
        raise SystemExit(
            "ยังไม่มี API key — เอามาจาก cron-job.org Console → Settings → API Key\n"
            "แล้วรัน:  CJKEY=<key> python tools/cron_jobs.py\n"
            "(หรือเพิ่มบรรทัด CJKEY=... ใน backend/.env)"
        )
    token = _env_value("CRON_TOKEN")
    if not token:
        raise SystemExit("CRON_TOKEN ไม่พบใน backend/.env")

    every_10_min = {"hours": [-1], "minutes": [0, 10, 20, 30, 40, 50]}
    every_2_hours = {"hours": list(range(0, 24, 2)), "minutes": [0]}
    def daily(h):
        return {"hours": [h], "minutes": [0]}

    wanted = [
        ("ป้าเข็ม-keepalive", f"{BASE}/health", GET, every_10_min),
        ("ป้าเข็ม-ตรวจลิงก์", f"{BASE}/api/cron/check-links?token={token}", POST, daily(7)),
        ("ป้าเข็ม-คอนเทนต์", f"{BASE}/api/cron/analyze?token={token}&limit=30", POST, every_2_hours),
        ("ป้าเข็ม-ราคา", f"{BASE}/api/cron/refresh-prices?token={token}", POST, daily(5)),
        ("ป้าเข็ม-รายงานเช้า", f"{BASE}/api/cron/daily-report?token={token}", POST, daily(8)),
        ("ป้าเข็ม-ดึงลูกค้ากลับ", f"{BASE}/api/cron/re-engage?token={token}", POST, daily(9)),
    ]

    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("🔍 dry-run: จะตรวจสอบอย่างเดียว ไม่สร้าง/แก้ job ใด ๆ")

    existing = jobs(key)
    existing_titles = {j.get("title") for j in existing}
    print(f"มี job อยู่แล้ว {len(existing)} ตัวในบัญชี")

    created, skipped, would_create = 0, 0, 0
    put_times = []  # เวลาที่เรียก PUT ไปแล้ว — กันเกิน 5 req/min
    for title, url, method, schedule in wanted:
        if title in existing_titles:
            skipped += 1
            print(f"  ⏭  ข้าม (มีแล้ว): {title}")
            continue
        if dry_run:
            would_create += 1
            print(f"  🔍 (dry-run) จะสร้าง: {title}")
            continue
        # PUT /jobs จำกัด 1 req/s และ 5 req/min — พักเมื่อกำลังจะทำ request ที่ 6 ใน 60 วิ
        if len(put_times) >= 5:
            wait = put_times[-5] + 60 - time.time()
            if wait > 0:
                print(f"  ⏳ พัก {wait:.0f} วิ (PUT จำกัด 5 req/min)")
                time.sleep(wait)
        code, out = api_call("PUT", "/jobs", key, {"job": make_job(title, url, method, schedule)})
        put_times.append(time.time())
        if code == 200 and "jobId" in out:
            created += 1
            print(f"  ✅ สร้าง: {title} (jobId={out['jobId']})")
        else:
            print(f"  ❌ สร้างไม่สำเร็จ: {title} → HTTP {code}: {out}")
        time.sleep(1.2)  # PUT /jobs จำกัด 1 req/s

    if dry_run:
        print(f"\n(dry-run) จะสร้าง {would_create} ตัว, มีอยู่แล้ว {skipped} ตัว — ไม่ได้สร้างจริง")
    else:
        print(f"\nสร้างใหม่ {created} ตัว, มีอยู่แล้ว {skipped} ตัว")

    # --- สรุปสถานะทั้งหมด ---
    print("\n== สรุป job ทั้งหมดในบัญชี ==")
    for j in jobs(key):
        method = "GET" if j.get("requestMethod") == 0 else "POST"
        nxt = j.get("nextExecution")
        nxt_s = datetime.fromtimestamp(nxt).strftime("%Y-%m-%d %H:%M") if nxt else "-"
        print(f"  [{'on ' if j.get('enabled') else 'off'}] {j.get('title'):<22} "
              f"{method:<4} next={nxt_s} jobId={j.get('jobId')}")


if __name__ == "__main__":
    main()
