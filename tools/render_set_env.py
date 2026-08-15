#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/render_set_env.py — ตั้ง env vars บน Render (Management API) + trigger deploy.

วิธีใช้:
  1. เติมค่าจริงลงใน VARS ด้านล่าง (ช่องที่เว้นว่าง '' จะถูกข้าม ไม่ set)
  2. รัน:
       python tools/render_set_env.py             # set env ทีละตัว แล้ว trigger deploy
       python tools/render_set_env.py --no-deploy # set env อย่างเดียว ยังไม่ deploy

รายละเอียด:
  - อ่าน API key จาก ~/.render/cli.yaml (บรรทัด "    key: ...")
  - PUT /v1/services/{id}/env-vars/{key} ทีละตัว (upsert — ไม่แตะตัวอื่น ปลอดภัย)
  - POST /v1/services/{id}/deploys เพื่อ deploy โค้ดที่ set env ใหม่
  - ไม่ print ค่า secret เต็ม (mask ให้ เห็นแค่หัว/ท้าย)

หมายเหตุ: หลัง deploy รอสถานะ "live" ที่
https://dashboard.render.com/web/srv-d9tknl2d0e5s739ebo40/deploys (~3 นาที)
"""
import json
import os
import sys
import urllib.error
import urllib.request

try:  # กัน Windows console ใช้ cp874 แล้ว print emoji พัง
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SERVICE_ID = "srv-d9tknl2d0e5s739ebo40"
API_BASE = "https://api.render.com/v1"

# ⬇️⬇️⬇️ เติมค่าจริงตรงนี้ (ช่องว่าง '' = ข้ามตัวนั้น) ⬇️⬇️⬇️
VARS = {
    "FACEBOOK_APP_ID": "1263958805236203",  # มีแล้วใน repo (SKILL.md) — ไม่ต้องแก้
    "FACEBOOK_APP_SECRET": "",          # App Secret (กด Show → ใส่รหัส Facebook เพื่อเปิดเผย)
    "FACEBOOK_VERIFY_TOKEN": "",        # รหัสลับตั้งเอง — ต้องตรงกับช่อง Verify Token ใน Facebook Webhook
    "FACEBOOK_PAGE_ACCESS_TOKEN": "",   # ได้จากขั้น Connect Page (Messenger → Settings)
    "LINE_OA_URL": "",                  # เช่น https://line.me/R/ti/p/@xxxxx
    # "ANTHROPIC_API_KEY": "",          # (ไม่บังคับ) เปิดใช้ Claude "บอสใหญ่" — ถ้าอยากใช้ให้ลบ # หน้า key
}
# ⬆️⬆️⬆️ จบส่วนที่ต้องกรอก ⬆️⬆️⬆️


def get_api_key() -> str:
    p = os.path.expanduser("~/.render/cli.yaml")
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("key:"):
                    return s.split(":", 1)[1].strip()
    except OSError as e:
        raise SystemExit(f"❌ อ่าน {p} ไม่ได้: {e}")
    raise SystemExit(f"❌ ไม่พบบรรทัด key: ใน {p}")


def request(method: str, path: str, payload=None):
    url = API_BASE + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


def mask(v: str) -> str:
    return (v[:4] + "…" + v[-2:]) if len(v) > 8 else "***"


def main() -> None:
    no_deploy = "--no-deploy" in sys.argv
    todo = {k: v for k, v in VARS.items() if str(v).strip()}
    if not todo:
        print("❌ ยังไม่มีการกรอกค่า — เปิด tools/render_set_env.py เติม VARS ก่อน")
        sys.exit(1)

    print(f"service: {SERVICE_ID} · กำลัง set {len(todo)} ตัว\n")
    for key, value in todo.items():
        status, resp = request("PUT", f"/services/{SERVICE_ID}/env-vars/{key}",
                               {"value": value})
        ok = status in (200, 201)
        mark = "✅" if ok else "❌"
        print(f"{mark} {key}: HTTP {status} (value={mask(value)})")
        if not ok:
            print(f"   → {resp}")

    if no_deploy:
        print("\n(ข้าม deploy — ใช้ flag --no-deploy)")
        return

    print("\nกำลัง trigger deploy…")
    status, resp = request("POST", f"/services/{SERVICE_ID}/deploys", {})
    if status in (200, 201):
        print(f"✅ trigger deploy สำเร็จ (id={resp.get('id')})")
        print("   รอสถานะ 'live' ที่ https://dashboard.render.com/web/"
              f"{SERVICE_ID}/deploys (~3 นาที)")
    else:
        print(f"❌ trigger deploy ล้ม: HTTP {status} → {resp}")


if __name__ == "__main__":
    API_KEY = get_api_key()
    main()
