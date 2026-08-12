#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_generate_content — เติมคอนเทนต์ AI ให้สินค้าที่ยังไม่มี (ทีละตัว กัน rate limit)
====================================================================================
- เรียงตาม ai_score (ของดีก่อน)
- sleep ระหว่างตัว (ค่าเริ่มต้น 1.2s) — Groq 4 keys หมุนเวียน ≈ 12 RPM/key ปลอดภัย
- retry 3 รอบด้วย backoff ถ้าล้ม / ได้ mock fallback (ทุก key โดน 429)
  — mock fallback ตรวจจับได้จาก hook ขึ้นต้น "หยุดก่อนจ๊ะ" → ไม่เขียนของปลอมเข้าร้าน
- ใช้ซ้ำได้: import สินค้าใหม่แล้วรันอีกที จะเติมเฉพาะตัวที่ยังไม่มี

รัน: backend/.venv/Scripts/python tools/batch_generate_content.py [--limit N] [--sleep S] [--style Standard]
"""
import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.orm import sessionmaker

from app import models
from app.services.ai_generator import format_hashtags_text, generate_script_for_product
from csv_batch_rebuild import get_engine

MOCK_HOOK_PREFIX = "หยุดก่อนจ๊ะ"  # signature ของ mock fallback (ทุก key ล้ม) — ต้องไม่เข้าร้าน


def gen_with_retry(product, style: str, attempts: int = 3):
    last = None
    for a in range(attempts):
        try:
            data = generate_script_for_product(product.name, product.category or "",
                                               float(product.price or 0), style)
            if (data.get("hook") or "").startswith(MOCK_HOOK_PREFIX):
                raise ValueError("ทุก Groq key ล้ม (429) — ได้ mock fallback, retry")
            return data
        except Exception as e:
            last = e
            if a < attempts - 1:
                time.sleep(20 * (a + 1))
    raise last


def main():
    ap = argparse.ArgumentParser(description="เติมคอนเทนต์ AI ให้สินค้าที่ยังไม่มี")
    ap.add_argument("--limit", type=int, default=0, help="จำกัดจำนวน (0 = หมด)")
    ap.add_argument("--sleep", type=float, default=1.2, help="วินาทีพักระหว่างตัว")
    ap.add_argument("--style", default="Standard", choices=["Standard", "Funny", "Educational", "Unboxing"])
    args = ap.parse_args()

    db = sessionmaker(bind=get_engine())()
    try:
        with_content = {c.product_id for c in db.query(models.Content).all()}
        missing = [p for p in db.query(models.Product).all() if p.id not in with_content]
        missing.sort(key=lambda p: p.ai_score or 0, reverse=True)
        if args.limit:
            missing = missing[:args.limit]
        total = len(missing)
        print(f"สินค้าที่ไม่มีคอนเทนต์: {total} ตัว (style={args.style}, sleep={args.sleep}s)", flush=True)
        done, failed = [], []
        for i, p in enumerate(missing, 1):
            try:
                data = gen_with_retry(p, args.style)
                caption = data.get("caption", "")
                hashtags = format_hashtags_text(data.get("hashtags"))
                if hashtags:
                    caption = (caption + "\n\n" + hashtags).strip()
                db.add(models.Content(product_id=p.id, style=args.style,
                                      hook=data.get("hook"), problem=data.get("problem"),
                                      solution=data.get("solution"), cta=data.get("cta"),
                                      caption=caption))
                db.commit()
                done.append(p.id)
            except Exception as e:
                db.rollback()
                failed.append((p.id, str(e)[:120]))
                print(f"  ล้ม #{p.id} {p.name[:40]}: {str(e)[:80]}", flush=True)
            if i % 10 == 0 or i == total:
                print(f"  [{i}/{total}] สำเร็จ {len(done)} · ล้ม {len(failed)}", flush=True)
            if i < total:
                time.sleep(args.sleep)
        print(f"\n=== สรุป: สำเร็จ {len(done)} · ล้ม {len(failed)} · เหลือ {total - len(done)} ===", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
