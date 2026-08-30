#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/render_set_env.py — Render Management API helper (env vars + deploys).

วิธีใช้ (batch — จากไฟล์ local):
  1. เติมค่าจริงลงในไฟล์ tools/render_env.local.json (gitignored — ไม่ commit ขึ้น GitHub)
     ตัวอย่าง: {"FACEBOOK_APP_SECRET": "...", "FACEBOOK_PAGE_ACCESS_TOKEN": "...", ...}
     ช่องที่เว้นว่าง "" จะถูกข้าม ไม่ set
  2. รัน:
       python tools/render_set_env.py batch            # set env ทีละตัว แล้ว trigger deploy
       python tools/render_set_env.py batch --no-deploy # set env อย่างเดียว ยังไม่ deploy

วิธีใช้ (คำสั่งเดี่ยว):
       python tools/render_set_env.py list                    # แสดง env vars ทั้งหมด (mask ค่า)
       python tools/render_set_env.py get KEY                 # แสดงค่าเต็มของตัวเดียว (ไม่ mask)
       python tools/render_set_env.py set KEY VALUE           # upsert ตัวเดียว (ยังไม่ deploy)
       python tools/render_set_env.py set KEY VALUE --deploy  # upsert แล้ว trigger deploy
       python tools/render_set_env.py unset KEY               # ลบ env var ตัวเดียว (ยังไม่ deploy)
       python tools/render_set_env.py unset KEY --deploy      # ลบ แล้ว trigger deploy
       python tools/render_set_env.py diff                    # เทียบ remote กับ VARS/render_env.local.json
       python tools/render_set_env.py deploy                  # trigger deploy (retry 503 อัตโนมัติ)

รายละเอียด:
  - อ่าน API key ตามลำดับ: env RENDER_API_KEY → ~/.bashrc (export ตัวเดียวกัน) →
    ~/.render/cli.yaml (CLI token — หมดอายุเป็นระยะ) — อ่านจาก ~/.bashrc กันกรณี
    shell ไม่ได้ inherit env var (non-login/non-interactive หรือ app เปิดค้างไว้ก่อน)
  - ค่าจาก render_env.local.json ชนะค่า default ใน VARS (ใช้กับค่าสาธารณะ เช่น APP_ID)
  - PUT /v1/services/{id}/env-vars/{key} ทีละตัว (upsert — ไม่แตะตัวอื่น ปลอดภัย)
  - DELETE /v1/services/{id}/env-vars/{key} (unset) ลบตัวเดียว — ต้อง deploy ถึงจะมีผล
  - POST /v1/services/{id}/deploys เพื่อ deploy โค้ดที่ set env ใหม่
  - GET /v1/services/{id}/env-vars: ปัจจุบันคืน envVar เป็น dict; เวอร์ชันเก่าเคย
    double-encode เป็น string แบบ python-dict ("{'key': ...}") — decode_env_var()
    รองรับทั้งสองแบบ (json.loads → แยกด้วย regex เอง) กัน ast.literal_eval พัง
  - API paginate 20 ตัว/หน้า — fetch_env_vars() ตาม cursor เก็บทุกหน้า (เดิม
    list/get/diff อ่านแค่หน้าแรก → env vars หน้า 2+ หายจากผลลัพธ์)
  - ไม่ print ค่า secret เต็ม (mask ให้ เห็นแค่หัว/ท้าย) — ยกเว้น `get KEY`
    ที่สั่งชัดว่าดูตัวเดียว → แสดงค่าเต็ม (ระวัง share หน้าจอ/terminal history)

หมายเหตุ:
  - ได้ HTTP 401 = token ใน cli.yaml หมดอายุ → รัน `renderctl whoami` (หรือ
    `renderctl login`) เพื่อ refresh แล้วรันใหม่
  - deploy ได้ HTTP 503 = incident ฝั่ง Render/Google Cloud (ชั่วคราว) — cmd_deploy
    retry อัตโนมัติ (env DEPLOY_RETRY_MAX default 12, DEPLOY_RETRY_DELAY default 300 วิ)
  - หลัง deploy รอสถานะ "live" ที่
    https://dashboard.render.com/web/srv-d9tknl2d0e5s739ebo40/deploys (~3 นาที)
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
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


def _key_from_bashrc() -> str:
    """อ่าน RENDER_API_KEY จาก ~/.bashrc (บรรทัด export RENDER_API_KEY="...").

    กันกรณี shell ไม่ได้ inherit env var (non-login/non-interactive หรือ parent
    process เปิดค้างไว้ก่อนตั้งค่า) — key หลักแบบ no-expiry อยู่ตรงนี้เสมอ.
    """
    p = os.path.expanduser("~/.bashrc")
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                m = re.search(
                    r'export\s+RENDER_API_KEY\s*=\s*["\']([^"\']+)["\']', line
                )
                if m:
                    return m.group(1).strip()
    except OSError:
        pass
    return ""


def get_api_key() -> str:
    # ลำดับ: env RENDER_API_KEY → ~/.bashrc → ~/.render/cli.yaml
    # (key หลักแบบ no-expiry มาก่อน CLI token ที่หมดอายุเป็นระยะ ~6 วัน)
    env = os.environ.get("RENDER_API_KEY", "").strip()
    if env:
        return env
    bashrc = _key_from_bashrc()
    if bashrc:
        return bashrc
    p = os.path.expanduser("~/.render/cli.yaml")
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("key:"):
                    return s.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


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
        if e.code == 401:
            return e.code, ("401 Unauthorized — key/token หมดอายุหรือถูก revoke\n"
                            "   → ใช้ API key แบบ no-expiry ผ่าน RENDER_API_KEY หรือ\n"
                            "   → รัน `renderctl whoami` (หรือ `renderctl login`) "
                            "เพื่อ refresh แล้วรันใหม่")
        return e.code, e.read().decode("utf-8", "replace")[:400]


def mask(v: str) -> str:
    return (v[:4] + "…" + v[-2:]) if len(v) > 8 else "***"


def _extract_quoted_field(s: str, field: str):
    """แยก field ออกจาก python-dict-repr string เช่น "{'key': 'X', 'value': 'Y'}".

    ใช้ regex + backreference (จับคู่ quote เดิม) แทน ast.literal_eval ซึ่งพังกับ
    บางค่า (ตามที่บันทึกใน AGENTS.md) — value ที่มี quote ต่างชนิดยังผ่านได้.
    """
    pat = re.compile(
        r"(?P<oq>['\"])" + re.escape(field) + r"(?P=oq)\s*:\s*"
        r"(?P<vq>['\"])(?P<val>.*?)(?P=vq)",
        re.DOTALL,
    )
    m = pat.search(s)
    return m.group("val") if m else None


def decode_env_var(env_var):
    """Normalize envVar → (key, value).

    API ปัจจุบันคืน dict {"key": ..., "value": ...}; เวอร์ชันเก่าเคย double-encode
    เป็น string แบบ python-dict (single-quote, ไม่ใช่ JSON) ซึ่ง ast.literal_eval
    พังกับบางค่า → แยกเองด้วย _extract_quoted_field เป็น fallback.
    """
    if isinstance(env_var, dict):
        return env_var.get("key"), env_var.get("value")
    if not isinstance(env_var, str):
        return None, None
    s = env_var.strip()
    try:  # JSON แท้ (double-quoted) เผื่อ API เปลี่ยนรูปแบบกลับมา
        d = json.loads(s)
        if isinstance(d, dict):
            return d.get("key"), d.get("value")
    except (ValueError, TypeError):
        pass
    return _extract_quoted_field(s, "key"), _extract_quoted_field(s, "value")


def fetch_env_vars() -> list:
    """GET /services/{id}/env-vars ทุกหน้า (API paginate 20 ตัว/หน้า ตาม cursor)."""
    if not API_KEY:
        return []
    items = []
    cursor = None
    seen = set()
    while True:
        path = f"/services/{SERVICE_ID}/env-vars"
        if cursor:
            path += "?" + urllib.parse.urlencode({"cursor": cursor})
        status, resp = request("GET", path)
        if status != 200:
            return []
        page = resp if isinstance(resp, list) else []
        if not page:
            break
        items.extend(page)
        last = page[-1] if isinstance(page[-1], dict) else {}
        next_cursor = last.get("cursor")
        if not next_cursor or next_cursor in seen:
            break
        seen.add(next_cursor)
        cursor = next_cursor
    return items


def cmd_list() -> None:
    items = fetch_env_vars()
    if not items:
        print("(ไม่มี env vars)")
        return
    print(f"{len(items)} env vars:\n")
    for item in items:
        env_var = item.get("envVar") if isinstance(item, dict) else item
        key, value = decode_env_var(env_var)
        if key is None:
            print(f"⚠️  decode ไม่ได้: {item!r}")
            continue
        print(f"{key} = {mask(str(value))}")


def cmd_get(key: str) -> None:
    items = fetch_env_vars()
    for item in items:
        env_var = item.get("envVar") if isinstance(item, dict) else item
        k, value = decode_env_var(env_var)
        if k == key:
            print(f"{k} = {value}")  # get ต้องสั่งชัด → แสดงค่าเต็ม ไม่ mask
            return
    print(f"❌ ไม่พบ env var: {key}")
    sys.exit(1)


def cmd_set(key: str, value: str, deploy: bool) -> None:
    status, resp = request("PUT", f"/services/{SERVICE_ID}/env-vars/{key}",
                           {"value": value})
    if status in (200, 201):
        print(f"✅ {key}: HTTP {status} (value={mask(value)})")
    else:
        print(f"❌ {key}: HTTP {status} → {resp}")
        sys.exit(1)
    if deploy:
        cmd_deploy()
    else:
        print("(ยังไม่ deploy — ต่อท้าย --deploy หรือรัน "
              "`python tools/render_set_env.py deploy`)")


def cmd_unset(key: str, deploy: bool) -> None:
    status, resp = request("DELETE", f"/services/{SERVICE_ID}/env-vars/{key}")
    if status in (200, 202, 204):
        print(f"✅ ลบ {key} สำเร็จ (HTTP {status})")
    else:
        print(f"❌ ลบ {key} ล้ม: HTTP {status} → {resp}")
        sys.exit(1)
    if deploy:
        cmd_deploy()
    else:
        print("(ยังไม่ deploy — ต่อท้าย --deploy หรือรัน "
              "`python tools/render_set_env.py deploy`)")


def cmd_diff() -> None:
    items = fetch_env_vars()
    remote = {}
    for item in items:
        env_var = item.get("envVar") if isinstance(item, dict) else item
        k, v = decode_env_var(env_var)
        if k is not None:
            remote[k] = v

    desired = {k: v for k, v in VARS.items() if str(v).strip()}
    desired.update(load_local_values())
    if not desired:
        print(f"❌ ไม่มีค่าที่จะเทียบ — เติม {LOCAL_FILE} หรือ VARS แล้วรันใหม่")
        sys.exit(1)

    differs, missing = [], []
    for k, want in desired.items():
        if k not in remote:
            missing.append(k)
        elif str(remote[k]) != str(want):
            differs.append((k, want, remote[k]))
    extra = [k for k in remote if k not in desired]

    same = len(desired) - len(differs) - len(missing)
    print(f"ตรงกัน {same} · ต่างกัน {len(differs)} · ขาดบน Render {len(missing)} · "
          f"มีเฉพาะบน Render {len(extra)}\n")
    if differs:
        print("— ต่างกัน (local → remote):")
        for k, want, got in differs:
            print(f"  {k}: {mask(str(want))} → {mask(str(got))}")
    if missing:
        print("— ยังไม่มีบน Render:")
        for k in missing:
            print(f"  {k}")
    if extra:
        print("— มีบน Render แต่ไม่ track ในเครื่อง:")
        for k in extra:
            print(f"  {k}")
    if not differs and not missing and not extra:
        print("✅ ทุกตัวที่ track ตรงกับ Render")


def cmd_deploy() -> None:
    """Trigger deploy — retry อัตโนมัติเมื่อได้ 503 (incident ฝั่ง Render/Google Cloud).

    ควบคุมด้วย env: DEPLOY_RETRY_MAX (จำนวนครั้ง, default 12) และ
    DEPLOY_RETRY_DELAY (วินาทีระหว่างครั้ง, default 300)."""
    max_attempts = int(os.getenv("DEPLOY_RETRY_MAX", "12") or 12)
    delay = int(os.getenv("DEPLOY_RETRY_DELAY", "300") or 300)
    for attempt in range(1, max_attempts + 1):
        print(f"กำลัง trigger deploy… (ครั้งที่ {attempt}/{max_attempts})")
        status, resp = request("POST", f"/services/{SERVICE_ID}/deploys", {})
        if status in (200, 201, 202):
            print(f"✅ trigger deploy สำเร็จ (id={resp.get('id') if isinstance(resp, dict) else resp})")
            print("   รอสถานะ 'live' ที่ https://dashboard.render.com/web/"
                  f"{SERVICE_ID}/deploys (~3 นาที)")
            return
        if status == 503:
            if attempt >= max_attempts:
                break
            print(f"⏳ HTTP 503 (Render ยังปิด deploy ชั่วคราว) — รอ {delay} วิ แล้วลองใหม่")
            time.sleep(delay)
            continue
        print(f"❌ trigger deploy ล้ม: HTTP {status} → {resp}")
        sys.exit(1)
    print(f"❌ retry ครบ {max_attempts} ครั้งแล้ว deploy ยังไม่ผ่าน "
          f"(Render incident ยังไม่หาย — ดู status.render.com)")
    sys.exit(1)


def _print_usage() -> None:
    print("usage: python tools/render_set_env.py <คำสั่ง> [ตัวเลือก]")
    print()
    print("คำสั่ง:")
    print("  get KEY               ดูค่า env ตัวเดียว (แสดงเต็ม)")
    print("  list                  รายการ env ทั้งหมด (mask)")
    print("  diff                  เทียบ remote กับ local (VARS + render_env.local.json)")
    print("  set KEY VALUE [--deploy]    ตั้งค่า 1 ตัว (ต้อง --deploy ถึงจะ deploy)")
    print("  unset KEY [--deploy]        ลบ 1 ตัว (ต้อง --deploy ถึงจะ deploy)")
    print("  deploy                trigger deploy")
    print("  batch [--no-deploy]   ตั้งค่าทั้งชุดจาก render_env.local.json + deploy")
    print()
    print("⚠️  ต้องระบุคำสั่งเสมอ — รันโดยไม่มีคำสั่งจะไม่ทำอะไร"
          " (กัน set+deploy เผลอ เหมือน --help ไปโดน batch)")


def main() -> None:
    args = sys.argv[1:]

    # --- คำสั่งเดี่ยว ---
    if args and args[0] == "list":
        cmd_list()
        return
    if args and args[0] == "get":
        if len(args) < 2:
            print("usage: python tools/render_set_env.py get KEY")
            sys.exit(2)
        cmd_get(args[1])
        return
    if args and args[0] == "set":
        if len(args) < 3:
            print("usage: python tools/render_set_env.py set KEY VALUE [--deploy]")
            sys.exit(2)
        cmd_set(args[1], args[2], deploy="--deploy" in args[3:])
        return
    if args and args[0] == "unset":
        if len(args) < 2:
            print("usage: python tools/render_set_env.py unset KEY [--deploy]")
            sys.exit(2)
        cmd_unset(args[1], deploy="--deploy" in args[2:])
        return
    if args and args[0] == "diff":
        cmd_diff()
        return
    if args and args[0] == "deploy":
        cmd_deploy()
        return

    # --- batch mode: ต้องสั่ง `batch` ชัดเจน (กันรันเผลอ set+deploy เหมือน --help) ---
    if args and args[0] == "batch":
        no_deploy = "--no-deploy" in args
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
        cmd_deploy()
        return

    # --- ไม่มีคำสั่ง / ไม่รู้จัก (รวม --help) → โชว์วิธีใช้ ห้ามทำอะไร ---
    _print_usage()
    sys.exit(2)


if __name__ == "__main__":
    API_KEY = get_api_key()
    main()
