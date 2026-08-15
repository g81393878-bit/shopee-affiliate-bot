#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/render_set_env.py — ตั้ง env vars บน Render (Management API) + trigger deploy.

วิธีใช้:
  1. เติมค่าจริงลงในไฟล์ tools/render_env.local.json (gitignored — ไม่ commit ขึ้น GitHub)
     ตัวอย่าง: {"FACEBOOK_APP_SECRET": "...", "FACEBOOK_PAGE_ACCESS_TOKEN": "...", ...}
     ช่องที่เว้นว่าง "" จะถูกข้าม ไม่ set
  2. รัน:
       python tools/render_set_env.py             # set env ทีละตัว แล้ว trigger deploy
       python tools/render_set_env.py --no-deploy # set env อย่างเดียว ยังไม่ deploy

รายละเอียด:
  - อ่าน API key จาก ~/.render/cli.yaml (บรรทัด "    key: ...")
  - ค่าจาก render_env.local.json ชนะค่า default ใน VARS (ใช้กับค่าสาธารณะ เช่น APP_ID)
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
LOCAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "render_env.local.json")

# ค่า default (สาธารณะ/placeholder — ปลอดภัยที่จะ commit) ค่าจริงใส่ใน LOCAL_FILE แทน
VARS = {
    "FACEBOOK_APP_ID": "1263958805236203",  # มีแล้วใน repo (SKILL.md) — public ไม่ใช่ secret
    "FACEBOOK_APP_SECRET": "",
    "FACEBOOK_VERIFY_TOKEN": "",
    "FACEBOOK_PAGE_ACCESS_TOKEN": "",
    "LINE_OA_URL": "",
    # "ANTHROPIC_API_KEY": "",          # (ไม่บังคับ) เปิดใช้ Claude "บอสใหญ่" — ใส่ใน LOCAL_FILE
}


def load_local_values() -> dict:
    """อ่านค่าจริงจาก tools/render_env.local.json (gitignored) — ไม่มีไฟล์คืน {}"""
    if not os.path.exists(LOCAL_FILE):
        return {}
    try:
        with open(LOCAL_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"❌ อ่าน {LOCAL_FILE} ไม่ได้: {e}")
    return {k: str(v) for k, v in data.items() if str(v).strip()}


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
    todo.update(load_local_values())  # ค่าจริงจากไฟล์ local ชนะ default
    if not todo:
        print(f"❌ ยังไม่มีการกรอกค่า — เติม {LOCAL_FILE} แล้วรันใหม่")
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
