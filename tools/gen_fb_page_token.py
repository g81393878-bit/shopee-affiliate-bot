# -*- coding: utf-8 -*-
"""สร้าง long-lived Facebook page access token จาก short-lived user token

ใช้ตอนสลับ token ใหม่ — เช่น หลัง Reset App Secret ใน Meta dashboard
(การ reset secret ฆ่า token เก่าทุกตัวของ app ทันที → ต้องสร้าง token ใหม่
แล้วอัปเดต backend/.env + Render env ตามคำแนะนำท้ายสคริปต์)

ขั้นตอนที่สคริปต์ทำ:
  1. รับ short-lived user token (จาก Graph API Explorer เลือก app + scopes pages_*)
  2. exchange ผ่าน fb_exchange_token → long-lived user token (~60 วัน)
  3. GET /me/accounts → หา page access token ของเพจที่เลือก
  4. debug_token ยืนยันว่า token ใหม่ใช้ได้ + มาจาก app ไหน

ใช้งาน:
  python tools/gen_fb_page_token.py --app-id <APP_ID> --app-secret <SECRET> --short-token <TOKEN>
  python tools/gen_fb_page_token.py --app-id <APP_ID> --app-secret <SECRET> --short-token <TOKEN> --page-id 1307380735783361
  # หรือตั้ง env แทน: FACEBOOK_APP_ID, FACEBOOK_APP_SECRET, FB_SHORT_TOKEN

scopes ที่ต้องมีใน short-lived token (เหมือน token เก่า):
  pages_manage_posts, pages_read_engagement, pages_show_list, pages_manage_engagement,
  pages_read_user_content, publish_video, pages_manage_metadata, pages_manage_ads, pages_messaging

⚠️ หลังได้ token ใหม่: อัปเดต FACEBOOK_APP_SECRET + FACEBOOK_PAGE_ACCESS_TOKEN
ทั้งใน backend/.env และ Render env (ดู AGENTS.md หัวข้อ Render Management API)
แล้ว trigger deploy — ไม่งั้นบอทโพสต์/verify webhook พัง (secret เก่าถูก reset ไปแล้ว)
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = "https://graph.facebook.com/v21.0"

# Windows console encoding safeguard (force UTF-8 to print Thai & emoji cleanly)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _get(url: str) -> dict:
    """GET Graph API แล้วคืน dict (raise ถ้า error)"""
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="สร้าง long-lived Facebook page access token จาก short-lived user token")
    ap.add_argument("--app-id", default=os.getenv("FACEBOOK_APP_ID", ""),
                    help="Facebook App ID (env: FACEBOOK_APP_ID)")
    ap.add_argument("--app-secret", default=os.getenv("FACEBOOK_APP_SECRET", ""),
                    help="App Secret ใหม่หลัง Reset (env: FACEBOOK_APP_SECRET)")
    ap.add_argument("--short-token", default=os.getenv("FB_SHORT_TOKEN", ""),
                    help="short-lived user token จาก Graph API Explorer (env: FB_SHORT_TOKEN)")
    ap.add_argument("--page-id", default="",
                    help="เลือกเพจ (default: ตัวแรกในรายการ หรือตรงกับ .env)")
    args = ap.parse_args()

    if not args.app_id or not args.app_secret or not args.short_token:
        print("❌ ต้องมีครบ: --app-id, --app-secret, --short-token (หรือตั้ง env)")
        ap.print_help()
        return 1

    print("=" * 60)
    print("🔑 สร้าง long-lived Facebook page access token")
    print(f"   app_id = {args.app_id}")
    print("=" * 60)

    # 1) exchange short-lived -> long-lived user token
    print("\n[1/4] Exchange short-lived → long-lived user token ...")
    q = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": args.app_id,
        "client_secret": args.app_secret,
        "fb_exchange_token": args.short_token,
    })
    try:
        ex = _get(f"{GRAPH}/oauth/access_token?{q}")
    except Exception as e:
        print(f"❌ exchange ล้ม: {e}")
        print("   ตรวจ: secret ถูกต้องไหม (หลัง reset) / short token ยังใช้ได้ไหม")
        return 1
    long_token = ex.get("access_token", "")
    if not long_token:
        print(f"❌ ไม่ได้ access_token กลับมา: {ex}")
        return 1
    print(f"   ✅ ได้ long-lived user token (ยาว {len(long_token)} ตัว)")

    # 2) /me/accounts -> เลือกเพจ
    print("\n[2/4] ดึงรายการเพจ (/me/accounts) ...")
    try:
        accs = _get(f"{GRAPH}/me/accounts?access_token={long_token}")
    except Exception as e:
        print(f"❌ /me/accounts ล้ม: {e}")
        print("   ตรวจ: short token มี scopes pages_show_list + pages_manage_posts ไหม")
        return 1
    pages = accs.get("data", [])
    if not pages:
        print("❌ ไม่มีเพจในบัญชีนี้ — ตรวจว่า short token ได้จาก admin ของเพจจริง")
        return 1
    print(f"   เจอเพจ {len(pages)} เพจ:")
    for p in pages:
        mark = " 👈" if (args.page_id and p.get("id") == args.page_id) else ""
        print(f"     - {p.get('id')}  {p.get('name')}{mark}")

    # เลือกเพจ: ตรง --page-id หรือตรง .env หรือตัวแรก
    from dotenv import load_dotenv  # noqa: E402
    load_dotenv(ROOT / "backend" / ".env")
    env_page = ""
    env_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    try:
        d = _get(f"{GRAPH}/debug_token?input_token={env_token}&access_token={env_token}")
        env_page = (d.get("data") or {}).get("profile_id", "")
    except Exception:
        pass

    chosen = None
    for p in pages:
        if args.page_id and p.get("id") == args.page_id:
            chosen = p
            break
    if chosen is None:
        for p in pages:
            if p.get("id") == env_page:
                chosen = p
                break
    if chosen is None:
        chosen = pages[0]
    page_token = chosen.get("access_token", "")
    if not page_token:
        print("❌ เพจที่เลือกไม่มี access_token — ตรวจ scopes อีกที")
        return 1
    print(f"\n   ✅ เลือกเพจ: {chosen.get('id')}  {chosen.get('name')}")

    # 3) debug_token ยืนยัน
    print("\n[3/4] ยืนยัน token ใหม่ (debug_token) ...")
    try:
        dbg = _get(f"{GRAPH}/debug_token?input_token={page_token}&access_token={page_token}")
        d = dbg.get("data", {})
        print(f"   app_id   = {d.get('app_id')}  ({d.get('application')})")
        print(f"   is_valid = {d.get('is_valid')}")
        print(f"   type     = {d.get('type')}")
        print(f"   page_id  = {d.get('profile_id')}")
        print(f"   expires  = {d.get('expires_at')}  ({'ไม่หมดอายุ' if d.get('expires_at') == 0 else 'มีวันหมดอายุ'})")
    except Exception as e:
        print(f"   ⚠️ debug_token ล้ม: {e}")

    # 4) แสดงผล + คำแนะนำ
    print("\n" + "=" * 60)
    print("✅ FACEBOOK_PAGE_ACCESS_TOKEN ใหม่ (คัดลอกไปใช้ได้เลย):")
    print("=" * 60)
    print(page_token)
    print("=" * 60)
    print("""
ถัดไป (อัปเดต 2 ที่ + deploy — อย่าลืม secret ใหม่ด้วย เพราะ reset ไปแล้ว):
  1. backend/.env:  FACEBOOK_APP_SECRET=<secret ใหม่>  FACEBOOK_PAGE_ACCESS_TOKEN=<ข้างบน>
  2. Render env (Management API หรือ dashboard):
       PUT /services/srv-d9tknl2d0e5s739ebo40/env-vars/FACEBOOK_APP_SECRET
       PUT /services/srv-d9tknl2d0e5s739ebo40/env-vars/FACEBOOK_PAGE_ACCESS_TOKEN
  3. trigger deploy: POST /services/srv-d9tknl2d0e5s739ebo40/deploys
  4. verify: /health + webhook verify + โพสต์ทดสอบ + watcher ยัง enabled
  (FACEBOOK_APP_ID และ FACEBOOK_VERIFY_TOKEN ไม่ต้องเปลี่ยน)
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
