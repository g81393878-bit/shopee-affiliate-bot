# -*- coding: utf-8 -*-
"""กวาดลบโพสต์ลิงก์ปลอมบนเพจ Facebook — รันครั้งเดียวจากเครื่อง (ไม่ได้ deploy)

ลบโพสต์ที่มี: shope.ee (ปลอมเสมอ) · lazada.co.th (แพลตฟอร์มอื่น) ·
s.shopee.co.th รหัส format ไม่ valid (มี _ / -) หรือไม่ใช่ลิงก์ในคลังสินค้า
(เช่น s.shopee.co.th/earbudsok — base62 ผ่าน format แต่ mock poster ใช้ ไม่มีใน products)

ใช้งาน:
  python tools/clean_fake_page_posts.py --dry-run   # ดูตัวอย่าง (ไม่ลบ)
  python tools/clean_fake_page_posts.py             # ลบจริง
  python tools/clean_fake_page_posts.py --limit 50  # สแกนแค่ 50 โพสต์ล่าสุด

โหลด FACEBOOK_PAGE_ACCESS_TOKEN จาก backend/.env อัตโนมัติ
การเช็ค "ลิงก์ไม่ใช่ของในคลัง" ต้องให้ DATABASE_URL ชี้ production (Supabase) —
ดู AGENTS.md หัวข้อ "เทสต์กับข้อมูลจริง (local)" (ถ้า DB มีสินค้า < 10 ตัว
จะข้ามเช็คนี้ กันลบของจริงเพราะคลัง local ว่าง)
"""
import argparse
import os
import sys
from pathlib import Path

# ให้ import app.* ได้ (backend/ + backend/app ต้องอยู่ใน sys.path)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "app"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / ".env")

from app.services.facebook_poster import (  # noqa: E402
    fetch_page_posts,
    delete_page_post,
    is_fake_link_post,
    _normalize_shopee_link,
)

# Windows console encoding safeguard (force UTF-8 to print Thai & emoji cleanly)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def load_known_links() -> set:
    """รวบ affiliate_url ในคลังสินค้า (normalize) — ใช้เช็คว่าลิงก์เป็นของจริงในคลังไหม

    กันพลาด: ถ้า DB มีสินค้า < 10 ตัว (เช่น SQLite ท้องถิ่น) → คืน set ว่าง
    (ข้ามเช็คนี้ ไม่งั้นลบของจริงเพราะคลัง local ว่าง)
    """
    try:
        from app.db import SessionLocal
        from app import models
        db = SessionLocal()
        try:
            rows = db.query(models.Product.affiliate_url) \
                     .filter(models.Product.affiliate_url.isnot(None)).all()
        finally:
            db.close()
        known = {_normalize_shopee_link(u[0]) for u in rows if u[0]}
        if len(known) < 10:
            print(f"   ⚠️ คลังสินค้าใน DB น้อยเกินไป ({len(known)} ตัว) — ข้ามเช็ค 'ไม่ใช่ลิงก์ในคลัง'")
            return set()
        return known
    except Exception as e:
        print(f"   ⚠️ อ่านคลังสินค้าไม่ได้ ({e}) — ข้ามเช็ค 'ไม่ใช่ลิงก์ในคลัง'")
        return set()


def main() -> int:
    ap = argparse.ArgumentParser(description="กวาดลบโพสต์ลิงก์ปลอมบนเพจ Facebook")
    ap.add_argument("--dry-run", action="store_true", help="ดูตัวอย่าง ไม่ลบจริง")
    ap.add_argument("--limit", type=int, default=100, help="สแกนกี่โพสต์ล่าสุด (default 100)")
    args = ap.parse_args()

    if not os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN"):
        print("❌ ไม่พบ FACEBOOK_PAGE_ACCESS_TOKEN (backend/.env) — ตรวจ .env ก่อน")
        return 1

    print("=" * 60)
    print("🧹 กวาดลบโพสต์ลิงก์ปลอมบนเพจ Facebook")
    print(f"   โหมด: {'DRY-RUN (ไม่ลบ)' if args.dry_run else 'ลบจริง'}")
    print(f"   สแกน: {args.limit} โพสต์ล่าสุด")
    print("=" * 60)

    known = load_known_links()
    print(f"   📦 ลิงก์ในคลังที่ใช้ตรวจ: {len(known)} ตัว")

    posts = fetch_page_posts(limit=args.limit)
    print(f"   📄 ดึงโพสต์ได้: {len(posts)} ตัว")

    deleted, kept = [], []
    for p in posts:
        if is_fake_link_post(p.get("message") or "", p.get("urls") or [], known_links=known):
            pid = p.get("id")
            ok = True
            if not args.dry_run:
                ok = delete_page_post(pid)
            deleted.append((pid, p.get("created_time"), (p.get("message") or "")[:55], ok))
        else:
            kept.append(p.get("id"))

    print(f"\nผลลัพธ์: เจอโพสต์ปลอม {len(deleted)} ตัว · โพสต์ปกติ {len(kept)} ตัว")
    for pid, ts, msg, ok in deleted:
        print(f"   {'🗑️ ลบแล้ว' if ok else '❌ ลบไม่สำเร็จ'} {pid.split('_')[-1]} ({ts}) | {msg}")
    if args.dry_run:
        print("\n(โหมด dry-run — ไม่ได้ลบจริง เอา --dry-run ออกเพื่อลบ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
