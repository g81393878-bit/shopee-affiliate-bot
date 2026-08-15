#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill คอนเทนต์ template (ไม่ใช้ LLM/Groq) ให้สินค้าที่ยังไม่มีแถวในตาราง contents

ต่อ production Supabase ตรง (อ่าน pw จาก ~/.supabase/db-password.txt) — เหมือน
tools/_backfill_product_images.py. ใช้ `build_template_script()` เสียงป้าเข็มสำเร็จรูป.

Usage:
    python tools/_backfill_content_template.py            # เติมทั้งหมด
    python tools/_backfill_content_template.py --limit 5  # ทดสอบก่อน
"""
import sys
import os
import pathlib
import argparse

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, ".")
sys.path.insert(0, "app")

pw = pathlib.Path(os.path.expanduser("~/.supabase/db-password.txt")).read_text().strip()
os.environ["DATABASE_URL"] = (
    f"postgresql://postgres.usqhvujqmnxqrdoovvnp:{pw}"
    f"@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
)

from app.db import SessionLocal
from app import models
from app.services.ai_generator import build_template_script


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="เติมสูงสุดกี่ตัว (default = ทั้งหมด)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        with_content = {c.product_id for c in db.query(models.Content).all()}
        missing = [p for p in db.query(models.Product).all() if p.id not in with_content]
        missing.sort(key=lambda p: p.ai_score or 0, reverse=True)
        total = len(missing)
        print(f"สินค้าที่ยังไม่มีคอนเทนต์: {total}")
        if args.limit:
            missing = missing[: args.limit]

        if not missing:
            print("ไม่มีอะไรต้องเติม")
            return

        done = 0
        batch = []
        for p in missing:
            data = build_template_script(
                p.name or "", p.category or "", float(p.price or 0), "Standard"
            )
            batch.append(models.Content(
                product_id=p.id,
                style="Standard",
                hook=data.get("hook"),
                problem=data.get("problem"),
                solution=data.get("solution"),
                cta=data.get("cta"),
                caption=(data.get("caption") or "").strip(),
            ))
            if len(batch) >= 500:
                db.add_all(batch)
                db.commit()
                done += len(batch)
                batch = []
                print(f"  inserted {done}/{len(missing)}")

        if batch:
            db.add_all(batch)
            db.commit()
            done += len(batch)

        print(f"✅ เติมคอนเทนต์ template {done} ตัว (ไม่ใช้ LLM) — จาก {total} ตัวที่ว่าง")
    finally:
        db.close()


if __name__ == "__main__":
    main()
