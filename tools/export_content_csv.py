#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_content_csv — ส่งออกคอนเทนต์ทั้งหมดเป็น CSV ไว้เปิดวางโพสต์ (TikTok/YouTube)
==================================================================================
คอลัมน์: id, สินค้า, หมวด, ราคา, ยอดขาย, คะแนน, Hook, ปัญหา, วิธีแก้, CTA,
แคปชัน (รวมแฮชท้าย), แฮชแท็ก (แยก), Title, ราคาเริ่มต้น

รัน: backend/.venv/Scripts/python tools/export_content_csv.py [--out D:\\ไฟล์.csv]
"""
import argparse
import csv
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.orm import sessionmaker

from app import models
from csv_batch_rebuild import get_engine


def main():
    ap = argparse.ArgumentParser(description="ส่งออกคอนเทนต์เป็น CSV")
    ap.add_argument("--out", default="", help="path ไฟล์ CSV (default: D:\\คอนเทนต์ป้าเข็ม_YYYYMMDD.csv)")
    args = ap.parse_args()

    db = sessionmaker(bind=get_engine())()
    try:
        rows = (db.query(models.Content, models.Product)
                  .join(models.Product, models.Content.product_id == models.Product.id)
                  .order_by(models.Product.sales_count.desc().nullslast(),
                            models.Product.ai_score.desc().nullslast())
                  .all())
        out = args.out or f"D:\\คอนเทนต์ป้าเข็ม_{datetime.now():%Y%m%d}.csv"
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "สินค้า", "หมวด", "ราคา(฿)", "ยอดขาย", "คะแนน",
                        "Hook", "ปัญหา", "วิธีแก้", "CTA", "แคปชัน", "แฮชแท็ก", "Title"])
            for c, p in rows:
                cap = c.caption or ""
                hashtags = ""
                if "\n" in cap:
                    cap_body, _, hashtags = cap.rpartition("\n")
                w.writerow([c.id, p.name, p.category or "", float(p.price or 0),
                            p.sales_count or 0, p.ai_score or 0,
                            (c.hook or "").strip(), (c.problem or "").strip(),
                            (c.solution or "").strip(), (c.cta or "").strip(),
                            cap_body.strip() or cap.strip(), hashtags.strip(),
                            (c.caption or "").strip().splitlines()[0] if c.caption else ""])
        print(f"ส่งออก {len(rows)} แถว → {out}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
