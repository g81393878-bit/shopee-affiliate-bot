#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csv_batch_rebuild — ประมวลผล CSV export ทั้งหมดใน D:\\ รวมกันใหม่
=============================================================
union ทุกไฟล์ → ตัดซ้ำด้วย รหัสสินค้า (item id) → เทียบกับคลังใน Supabase
→ ตรวจลิงก์ตัวที่ยังไม่เคยตรวจ → กันราคามั่ว (ราคา <= 2฿ = suspect ซ่อน) → รายงาน

รัน: backend/.venv/Scripts/python tools/csv_batch_rebuild.py
"""
import csv
import glob
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import models
from app.services.link_checker import check_affiliate_link
from app.services.category import guess_category

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
PRICE_SUSPECT_MAX = 2  # ราคาต่ำกว่า/เท่านี้ = ข้อมูลมั่ว → ซ่อน (suspect)

CSV_PATTERNS = [
    r"D:\ลิงก์สินค้าหลายลิงก์20260812*.csv",
    r"D:\สินค้า\ลิงก์สินค้าหลายลิงก์20260812*.csv",
]


def get_engine():
    url = (PROJECT_ROOT / "supabase" / ".temp" / "pooler-url").read_text(encoding="utf-8").strip()
    pw = (pathlib.Path.home() / ".supabase" / "db-password.txt").read_text(encoding="utf-8").strip()
    parts = url.split("://", 1)
    cred, rest = parts[1].split("@", 1)
    return create_engine(f"{parts[0]}://{cred}:{pw}@{rest}", pool_pre_ping=True, pool_recycle=300)


def parse_number(s):
    s = (s or "").strip().replace("฿", "").replace(",", "").replace(" ", "")
    m = re.search(r"([\d.]+)\s*(พัน|หมื่น|แสน|ล้าน)?", s)
    if not m:
        return 0.0
    num, unit = m.group(1), m.group(2)
    mult = {"พัน": 1000, "หมื่น": 10000, "แสน": 100000, "ล้าน": 1000000}.get(unit, 1)
    if unit is None and re.fullmatch(r"\d{1,3}(\.\d{3})+", num):
        num = num.replace(".", "")
    return float(num) * mult


def read_rows(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        for r in rd:
            name = (r.get("ชื่อสินค้า") or "").strip()
            if not name:
                continue
            price = float(parse_number(r.get("ราคา")))
            sales = int(parse_number(r.get("ขาย")))
            rows.append({
                "item_id": (r.get("รหัสสินค้า") or "").strip(),
                "name": name[:255],
                "price": price,
                "sales": sales,
                "commission": float(parse_number(r.get("คอมมิชชัน"))),
                "rate": (r.get("อัตราค่าคอมมิชชัน") or "").strip(),
                "affiliate_url": (r.get("ลิงก์ข้อเสนอ") or "").strip(),
                "product_link": (r.get("ลิงก์สินค้า") or "").strip(),
                "category": guess_category(name),
                "file": pathlib.Path(path).name,
            })
    return rows


def norm(s):
    return re.sub(r"[^ก-๙a-zA-Z0-9]", "", (s or "").lower())


def main():
    files = []
    for pat in CSV_PATTERNS:
        files += sorted(glob.glob(pat))
    if not files:
        print("ไม่พบ CSV ตาม pattern:", CSV_PATTERNS)
        return
    print(f"ไฟล์ที่พบ: {len(files)} ไฟล์")
    for f in files:
        print(f"  - {pathlib.Path(f).name}")

    # --- 1) union + ตัดซ้ำด้วย item id (เก็บแถวที่ยอดขายสูงสุด = ข้อมูลล่าสุด/แม่นสุด) ---
    all_rows = []
    per_file = {}
    for f in files:
        rs = read_rows(f)
        per_file[pathlib.Path(f).name] = len(rs)
        all_rows += rs
    raw_total = len(all_rows)
    by_item = {}
    for r in all_rows:
        key = r["item_id"] or r["affiliate_url"]
        if not key:
            continue
        if key not in by_item or r["sales"] > by_item[key]["sales"]:
            by_item[key] = r
    master = sorted(by_item.values(), key=lambda r: -r["sales"])
    print(f"\n=== 1) รวมดิบ {raw_total} แถว → ตัดซ้ำตาม item id เหลือ {len(master)} สินค้า ===")
    dup_rows = raw_total - len(master)
    print(f"ตัดซ้ำ: {dup_rows} แถว (สินค้าเดิม export หลายไฟล์/หลายรอบ)")

    # --- 2) เทียบกับคลังปัจจุบัน ---
    db = sessionmaker(bind=get_engine())()
    prods = db.query(models.Product).all()
    db_by_url = {}
    db_by_name = {}
    for p in prods:
        if p.affiliate_url:
            db_by_url[p.affiliate_url] = p
        db_by_name.setdefault(norm(p.name), []).append(p)

    already, missing = [], []
    for r in master:
        if r["affiliate_url"] and r["affiliate_url"] in db_by_url:
            already.append(r)
            continue
        cands = db_by_name.get(norm(r["name"]), [])
        if any(SequenceMatcher(None, norm(r["name"]), norm(c.name)).ratio() >= 0.9 for c in cands):
            already.append(r)
            continue
        missing.append(r)
    print(f"=== 2) มีในคลังแล้ว: {len(already)} | ยังไม่เคยเข้า: {len(missing)} ===")

    # --- 3) ตรวจลิงก์เฉพาะตัวใหม่ (ผ่าน = ok) ---
    to_check = [r for r in missing if r["affiliate_url"]]
    no_link = [r for r in missing if not r["affiliate_url"]]
    print(f"=== 3) ตรวจลิงก์ {len(to_check)} ตัว (ไม่มีลิงก์ข้อเสนอ {len(no_link)}) ===")
    inserted, link_fail, price_suspect = [], [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(check_affiliate_link, r["affiliate_url"]): r for r in to_check}
        for fut in as_completed(futures):
            r = futures[fut]
            status, detail = fut.result()
            if status != "OK":
                link_fail.append((r["name"], f"{status}: {detail}"))
                continue
            p = models.Product(
                name=r["name"], category=r["category"], price=r["price"], rating=0.0,
                sales_count=r["sales"], commission=r["commission"],
                affiliate_url=r["affiliate_url"], link_status="ok",
            )
            if r["price"] <= PRICE_SUSPECT_MAX:
                # ราคามั่ว (1-2฿ จาก CSV) → เก็บไว้แต่ซ่อน ไม่โชว์หน้าลูกค้า
                p.link_status = "suspect"
                price_suspect.append(r["name"])
            db.add(p)
            inserted.append(p)
    db.commit()

    # --- 4) รายงาน ---
    tot = db.query(models.Product).count()
    ok = db.query(models.Product).filter(models.Product.link_status == "ok").count()
    susp = db.query(models.Product).filter(models.Product.link_status == "suspect").count()
    dead = db.query(models.Product).filter(models.Product.link_status == "dead").count()
    other = tot - ok - susp - dead
    print(f"\n{'='*50}")
    print(f"📦 คลังรวมตอนนี้: {tot} ตัว")
    print(f"   ✅ โชว์ลูกค้าได้ (ok): {ok}")
    print(f"   🚫 ซ่อน (suspect ราคามั่ว): {susp}")
    print(f"   💀 ลิงก์ตาย (dead): {dead}")
    print(f"   ❓ อื่นๆ: {other}")
    print(f"{'='*50}")
    print(f"แยกตามไฟล์ (แถวดิบ):")
    for name, n in per_file.items():
        print(f"   {name}: {n} แถว")
    print(f"\nใหม่ที่เพิ่มรอบนี้: {len(inserted)} (ซ่อนราคามั่ว {len(price_suspect)})")
    if link_fail:
        print(f"\n--- ลิงก์ไม่ผ่าน ไม่เข้า ({len(link_fail)}) ---")
        for name, why in link_fail[:10]:
            print(f"   ✗ {name[:50]} — {why}")
    if no_link:
        print(f"\n--- ไม่มีลิงก์ข้อเสนอใน CSV ({len(no_link)}) ---")
        for r in no_link[:10]:
            print(f"   ✗ {r['name'][:50]}")
    db.close()


if __name__ == "__main__":
    main()
