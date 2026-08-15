#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill products.image_url — ใช้ fetch แบบใหม่ (ฟรี/เร็ว ไม่พึ่ง FB token / Firecrawl).

fetch แบบใหม่ = ตรงจากหน้า Shopee:
  1. GET affiliate_url (follow redirect) → อ่าน <meta og:image> ตรง ๆ
  2. ถ้า redirect ไปหน้า SPA (opaanlp) ที่ไม่มีรูป → derive /product/{shop}/{item} แล้วอ่าน og:image / JSON-LD
  — ไม่แตะ Facebook og scrape (ต้อง token) และไม่แตะ Firecrawl (ช้า/เสียเครดิต)

thread-safety: fetch (network) ทำใน thread pool ส่วน session/DB เขียนทำเฉพาะ main thread
+ commit เป็น batch กัน session ข้าม thread

ใช้:  export DATABASE_URL="postgresql://postgres.usqhvujqmnxqrdoovvnp:<pw>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
     cd backend && .venv/Scripts/python.exe ../tools/_backfill_product_images.py [--dry-run] [--limit N] [--workers N]
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows console → UTF-8 (กัน UnicodeEncodeError ภาษาไทย/สัญลักษณ์)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ต้องมี backend/ และ backend/app/ ใน sys.path (db.py/models.py อยู่ app/, import แบบ app.…)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "app"))

from sqlalchemy import or_  # noqa: E402

from app.services.product_image import (  # noqa: E402
    _fetch_html,
    extract_og_image,
    derive_product_page_url,
    extract_ld_json_images,
)
from app.db import SessionLocal  # noqa: E402
from app import models  # noqa: E402


def fetch_new(url: str, timeout: int = 20) -> str:
    """fetch แบบใหม่เท่านั้น (ไม่พึ่ง FB token / Firecrawl) → URL รูป หรือ ""."""
    if not url:
        return ""
    html, final_url = _fetch_html(url, timeout)
    if html:
        img = extract_og_image(html)
        if img:
            return img
        product_url = derive_product_page_url(final_url or url)
        if product_url and product_url != url:
            html2, _ = _fetch_html(product_url, timeout)
            if html2:
                img = extract_og_image(html2) or extract_ld_json_images(html2)
                if img:
                    return img
    return ""


def _fetch_row(row) -> tuple:
    """(pid, name, img) — img = "" (ไม่ได้รูป) หรือ None (ไม่มี affiliate_url)."""
    pid, name, url = row
    if not url:
        return pid, name, None
    img = fetch_new(url)
    if not img:
        time.sleep(1.0)
        img = fetch_new(url)  # retry ครั้งเดียว (กัน transient หลุด)
    return pid, name, img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="ไม่เขียน DB — แค่นับ + ทดลอง fetch")
    ap.add_argument("--limit", type=int, default=0, help="จำกัดจำนวนตัวที่ประมวลผล (0 = ทั้งหมด)")
    ap.add_argument("--workers", type=int, default=6, help="จำนวน thread ทำงานคู่กัน")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        prods = (db.query(models.Product)
                   .filter(or_(models.Product.image_url.is_(None),
                               models.Product.image_url == ""))
                   .order_by(models.Product.id)
                   .all())
        total_empty = len(prods)
        print(f"products ที่ image_url ว่าง: {total_empty} ตัว")
        # ดึงค่าออกมาเป็น plain tuple ก่อน (session จะถูก expire หลัง commit — กันปัญหา)
        rows = [(p.id, (p.name or ""), (p.affiliate_url or "").strip()) for p in prods]
        if args.limit:
            rows = rows[:args.limit]
            print(f"(จำกัดประมวลผลแค่ {len(rows)} ตัว)")

        got = 0
        failed = 0
        skipped_no_link = 0
        pending = 0
        t0 = time.time()

        def commit_batch(force=False):
            nonlocal pending
            if pending and (force or pending >= 20):
                db.commit()
                pending = 0

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_fetch_row, r) for r in rows]
            for i, fut in enumerate(as_completed(futs), 1):
                pid, name, img = fut.result()
                if img is None:
                    skipped_no_link += 1
                    print(f"[{i}/{len(rows)}] id={pid} - ไม่มี affiliate_url -> ข้าม")
                elif img:
                    got += 1
                    if not args.dry_run:
                        db.query(models.Product).filter(models.Product.id == pid) \
                          .update({"image_url": img}, synchronize_session=False)
                        pending += 1
                        commit_batch()
                    print(f"[{i}/{len(rows)}] id={pid} OK {img[:80]}")
                else:
                    failed += 1
                    print(f"[{i}/{len(rows)}] id={pid} FAIL ({name[:40]!r})")
        if not args.dry_run:
            commit_batch(force=True)

        dt = time.time() - t0
        print("\n===== สรุป =====")
        print(f"ทั้งหมดที่ image_url ว่าง: {total_empty}")
        print(f"ได้รูป: {got}")
        print(f"ไม่ได้รูป: {failed}")
        print(f"ไม่มี affiliate_url (ข้าม): {skipped_no_link}")
        print(f"ใช้เวลา: {dt:.0f}s")
        if args.dry_run:
            print("(dry-run — ยังไม่เขียน DB)")
        else:
            print("เขียน image_url ลง DB แล้ว")
    finally:
        db.close()


if __name__ == "__main__":
    main()
