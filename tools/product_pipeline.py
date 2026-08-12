#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Product Pipeline — จัดการสินค้า Shopee Affiliate แบบครบวงจร
=============================================================
นำเข้า CSV (export จากพอร์ทัล affiliate) → คัด/ให้คะแนน/ตัดซ้ำ → วิเคราะห์+เขียนคอนเทนต์
→ เก็บใน Supabase → รายงานตรวจสอบละเอียด

Commands:
  python tools/product_pipeline.py import-csv <file.csv> [--analyze] [--top N] [--style standard|funny|educational|unboxing]
  python tools/product_pipeline.py analyze [--top N] [--style standard]
  python tools/product_pipeline.py report
  python tools/product_pipeline.py check-links [--delete]  # ตรวจลิงก์ s.shopee.co.th ตายหรือยัง (--delete = ลบตัว DEAD)
  python tools/product_pipeline.py fix-scores            # คำนวณ ai_score ใหม่ให้ทุกตัว (หลังแก้ข้อมูล)

CSV columns (จากพอร์ทัล Shopee Affiliate "สร้างลิงก์"):
  รหัสสินค้า, ชื่อสินค้า, ราคา, ขาย, ชื่อร้านค้า, อัตราค่าคอมมิชชัน, คอมมิชชัน, ลิงก์สินค้า, ลิงก์ข้อเสนอ

Notes:
  - ราคา/ยอดขาย รองรับหน่วย "พัน" "หมื่น" "ล้าน" และ "฿" (เช่น "6.9พัน" = 6,900)
  - เขียนลง Supabase production โดยตรง (อ่าน pooler-url + db-password.txt)
  - ใช้ --sqlite เพื่อทดสอบกับ local dev DB
  - ต้องรันด้วย venv ของ backend:  backend/.venv/Scripts/python tools/product_pipeline.py ...
  - นโยบายเด็ดขาด: import/API ตรวจลิงก์ก่อนเข้าระบบ (ผ่านเท่านั้น) — บอท LINE ตอบเฉพาะ link_status == 'ok'
"""

import argparse
import csv
import datetime
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import models
from app.services.ai_analyzer import calculate_heuristic_score
from app.services.ai_generator import generate_script_for_product
from app.services.link_checker import check_affiliate_link

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

CATEGORY_KEYWORDS = [
    ("หูฟัง", "หูฟัง"), ("bluetooth", "หูฟัง"), ("earbud", "หูฟัง"), ("tws", "หูฟัง"),
    ("พัดลม", "พัดลม"), ("เครื่องทำความเย็น", "พัดลม"),
    ("ทิชชู่", "กระดาษทิชชู่"),
    ("แก้วน้ำ", "แก้วน้ำ"), ("tumbler", "แก้วน้ำ"), ("กระติก", "แก้วน้ำ"),
    ("โคมไฟ", "โคมไฟ"), ("หลอดไฟ", "โคมไฟ"),
    ("powerbank", "อุปกรณ์เสริม"), ("usb", "อุปกรณ์เสริม"), ("hub", "อุปกรณ์เสริม"),
    ("สายชาร์จ", "อุปกรณ์เสริม"), ("ที่ชาร์จ", "อุปกรณ์เสริม"),
    ("ขาตั้ง", "อุปกรณ์เสริม"), ("selfie", "อุปกรณ์เสริม"),
    ("กันแดด", "ความงาม"), ("ครีม", "ความงาม"), ("สกินแคร์", "ความงาม"),
    ("นาฬิกา", "แฟชั่น"), ("เสื้อ", "แฟชั่น"), ("แจ็กเก็ต", "แฟชั่น"), ("jacket", "แฟชั่น"),
    ("จักรยาน", "กีฬา"), ("แคมป์ปิ้ง", "กีฬา"), ("โต๊ะสนาม", "กีฬา"),
]


def guess_category(name: str) -> str:
    n = (name or "").lower()
    for kw, cat in CATEGORY_KEYWORDS:
        if kw in n:
            return cat
    return "อื่นๆ"


def parse_number(s: Optional[str]) -> float:
    """'6.9พัน' → 6900, '30พัน+' → 30000, '1,234' → 1234, '1.500' → 1500, '฿14.74' → 14.74"""
    s = (s or "").strip().replace("฿", "").replace(",", "").replace(" ", "")
    m = re.search(r"([\d.]+)\s*(พัน|หมื่น|แสน|ล้าน)?", s)
    if not m:
        return 0.0
    num = m.group(1)
    unit = m.group(2)
    mult = {"พัน": 1000, "หมื่น": 10000, "แสน": 100000, "ล้าน": 1000000}.get(unit, 1)
    if unit is None and re.fullmatch(r"\d{1,3}(\.\d{3})+", num):
        num = num.replace(".", "")  # จุดคั่นหลักพันแบบไทย ("1.500" = 1500)
    return float(num) * mult


def parse_thb(s: Optional[str]) -> Decimal:
    return Decimal(str(round(parse_number(s), 2)))


def get_engine(use_sqlite: bool = False):
    if use_sqlite:
        return create_engine(f"sqlite:///{PROJECT_ROOT / 'backend' / 'affiliate_db.db'}")
    url = (PROJECT_ROOT / "supabase" / ".temp" / "pooler-url").read_text(encoding="utf-8").strip()
    pw = (pathlib.Path.home() / ".supabase" / "db-password.txt").read_text(encoding="utf-8").strip()
    parts = url.split("://", 1)
    cred, rest = parts[1].split("@", 1)
    dsn = f"{parts[0]}://{cred}:{pw}@{rest}"  # pooler-url user มีพาสเวิร์ดเดียวกันกับ db-password
    return create_engine(dsn, pool_pre_ping=True, pool_recycle=300)


def read_csv(path: str) -> List[dict]:
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        for r in rd:
            name = (r.get("ชื่อสินค้า") or "").strip()
            if not name:
                continue
            rows.append({
                "name": name[:255],
                "price": parse_thb(r.get("ราคา")),
                "sales": int(parse_number(r.get("ขาย"))),
                "commission": parse_thb(r.get("คอมมิชชัน")),
                "rate": (r.get("อัตราค่าคอมมิชชัน") or "").strip(),
                "affiliate_url": (r.get("ลิงก์ข้อเสนอ") or "").strip(),
                "product_link": (r.get("ลิงก์สินค้า") or "").strip(),
                "category": guess_category(name),
            })
    return rows


def save_script(db, product: models.Product, style: str = "standard") -> Optional[models.Content]:
    try:
        data = generate_script_for_product(product.name, product.category or "", float(product.price or 0), style)
    except Exception as e:
        print(f"    ✗ AI ล้ม: {e}")
        return None
    caption = data.get("caption", "")
    tags = data.get("hashtags", [])
    if tags:
        caption = (caption + "\n\n" + " ".join(f"#{t}" for t in tags)).strip()
    content = models.Content(
        product_id=product.id, style="Standard",
        hook=data.get("hook"), problem=data.get("problem"),
        solution=data.get("solution"), cta=data.get("cta"), caption=caption,
    )
    db.add(content)
    return content


def cmd_import_csv(args):
    rows = read_csv(args.file)
    db = sessionmaker(bind=get_engine(args.sqlite))()
    existing_names = {p.name for p in db.query(models.Product).all()}
    existing_urls = {p.affiliate_url for p in db.query(models.Product).all() if p.affiliate_url}

    inserted, skipped_dupe, skipped_link = [], [], []
    fresh = []
    for r in rows:
        if r["name"] in existing_names or r["affiliate_url"] in existing_urls:
            skipped_dupe.append(r["name"])
            continue
        if not r["affiliate_url"]:
            skipped_link.append((r["name"], "ไม่มีลิงก์ข้อเสนอใน CSV"))
            continue
        fresh.append(r)

    # นโยบายเด็ดขาด: ตรวจลิงก์ก่อน insert — ผ่าน (OK) เท่านั้นถึงเข้าระบบ
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(check_affiliate_link, r["affiliate_url"]): r for r in fresh}
        for fut in as_completed(futures):
            r = futures[fut]
            status, detail = fut.result()
            if status != "OK":
                skipped_link.append((r["name"], f"{status}: {detail}"))
                continue
            score = calculate_heuristic_score(r["sales"], 0.0, float(r["commission"]), float(r["price"]))
            p = models.Product(
                name=r["name"], category=r["category"], price=r["price"], rating=0.0,
                sales_count=r["sales"], commission=r["commission"],
                affiliate_url=r["affiliate_url"], link_status="ok", ai_score=score,
            )
            db.add(p)
            db.flush()
            inserted.append(p)
            existing_names.add(r["name"])
            existing_urls.add(r["affiliate_url"])
    db.commit()
    print(f"imported {len(inserted)} / dupe {len(skipped_dupe)} / ลิงก์ไม่ผ่าน {len(skipped_link)} / จากไฟล์ {len(rows)}")
    if skipped_link:
        print("\n--- ข้าม (ลิงก์ไม่ผ่านการตรวจ) ---")
        for name, why in skipped_link:
            print(f"   ✗ {name[:50]} — {why}")

    if inserted and args.analyze:
        top = sorted(inserted, key=lambda p: p.ai_score or 0, reverse=True)[: args.top]
        print(f"\n--- AI สร้างคอนเทนต์ {len(top)} ตัว (style={args.style}) ---")
        for p in top:
            c = save_script(db, p, args.style)
            db.commit()
            print(f"  ✓ [{p.ai_score}] {p.name[:50]} -> hook: {(c.hook[:60] if c else 'N/A')}...")
    db.close()


def cmd_analyze(args):
    db = sessionmaker(bind=get_engine(args.sqlite))()
    with_content = {c.product_id for c in db.query(models.Content).all()}
    missing = [p for p in db.query(models.Product).all() if p.id not in with_content]
    missing.sort(key=lambda p: p.ai_score or 0, reverse=True)
    targets = missing[: args.top]
    print(f"สินค้าที่ยังไม่มีคอนเทนต์: {len(missing)} — จะสร้าง {len(targets)} ตัว (style={args.style})")
    for p in targets:
        c = save_script(db, p, args.style)
        db.commit()
        print(f"  ✓ [{p.ai_score}] {p.name[:50]} -> hook: {(c.hook[:60] if c else 'N/A')}...")
    db.close()


def cmd_report(args):
    db = sessionmaker(bind=get_engine(args.sqlite))()
    prods = db.query(models.Product).all()
    contents = {c.product_id for c in db.query(models.Content).all()}
    n = len(prods)
    with_link = sum(1 for p in prods if p.affiliate_url)
    no_link = [p for p in prods if not p.affiliate_url]
    no_hook = [p for p in prods if p.id not in contents]

    # หาของซ้ำตามชื่อ (ไม่รวม exact) — หาชื่อที่คล้ายกันเกิน 80%
    from difflib import SequenceMatcher
    dup_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if SequenceMatcher(None, prods[i].name, prods[j].name).ratio() > 0.8:
                dup_pairs.append((prods[i], prods[j]))

    cats = {}
    for p in prods:
        cats[p.category or "อื่นๆ"] = cats.get(p.category or "อื่นๆ", 0) + 1

    print(f"=== รายงานสินค้า ({n} ตัว) ===")
    print(f"มีลิงก์ affiliate: {with_link} | ไม่มีลิงก์: {len(no_link)}")
    print(f"มีคอนเทนต์/Hook: {n - len(no_hook)} | ยังไม่มี: {len(no_hook)}")
    print(f"คู่ที่ชื่อคล้ายกัน (ซ้ำ): {len(dup_pairs)}")
    for a, b in dup_pairs[:10]:
        print(f"   ~ [{a.ai_score}] {a.name[:40]}  vs  [{b.ai_score}] {b.name[:40]}")
    print("\n--- แยกตามหมวด ---")
    for k, v in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("\n--- คอมมิชชันสูงสุด 10 ---")
    for p in sorted(prods, key=lambda p: float(p.commission or 0), reverse=True)[:10]:
        print(f"  ฿{p.commission:>7} | {p.rate if hasattr(p, 'rate') else ''}{'':<2} | [{p.ai_score}] {p.name[:45]}")
    print("\n--- คะแนน AI สูงสุด 10 (สิ่งที่บอทแนะนำ) ---")
    for p in sorted(prods, key=lambda p: p.ai_score or 0, reverse=True)[:10]:
        print(f"  [{p.ai_score:>3}] ฿{p.price:>8} | {p.name[:45]}")
    if no_link:
        print("\n⚠️ ไม่มีลิงก์ (ต้องแก้):")
        for p in no_link:
            print(f"   - {p.name[:60]}")
    db.close()


def cmd_fix_scores(args):
    db = sessionmaker(bind=get_engine(args.sqlite))()
    for p in db.query(models.Product).all():
        p.ai_score = calculate_heuristic_score(p.sales_count or 0, float(p.rating or 0),
                                               float(p.commission or 0), float(p.price or 0))
    db.commit()
    print("recalculated ai_score ทุกตัวแล้ว")
    db.close()


def cmd_check_links(args):
    db = sessionmaker(bind=get_engine(args.sqlite))()
    prods = db.query(models.Product).all()
    with_link = [p for p in prods if p.affiliate_url]
    no_url = [p for p in prods if not p.affiliate_url]
    print(f"สินค้าทั้งหมด: {len(prods)} | มีลิงก์: {len(with_link)} | ไม่มีลิงก์: {len(no_url)}")

    groups: Dict[str, List[Tuple[models.Product, str]]] = {"OK": [], "DEAD": [], "SUSPECT": [], "UNKNOWN": [], "NO_URL": []}
    if with_link:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(check_affiliate_link, p.affiliate_url): p for p in with_link}
            for fut in as_completed(futures):
                p = futures[fut]
                status, detail = fut.result()
                groups.setdefault(status, []).append((p, detail))

    for p in no_url:
        groups["NO_URL"].append((p, "ไม่มีลิงก์"))

    # บันทึกสถานะลิงก์ลงตาราง (บอทจะตอบเฉพาะ ok)
    for st, items in groups.items():
        for p, _ in items:
            p.link_status = st.lower()
    db.commit()

    order = ["DEAD", "SUSPECT", "UNKNOWN", "NO_URL", "OK"]
    for st in order:
        items = groups.get(st, [])
        if not items:
            continue
        print(f"\n=== {st} ({len(items)}) ===")
        for p, detail in items:
            print(f"  [{st:<7}] ฿{p.price:>8} | [{p.ai_score:>3}] {p.name[:48]} — {detail}")

    n_dead = len(groups.get("DEAD", []))
    n_suspect = len(groups.get("SUSPECT", []))
    n_ok = len(groups.get("OK", []))
    print(f"\nสรุป: OK {n_ok} | DEAD {n_dead} | SUSPECT {n_suspect} | UNKNOWN {len(groups.get('UNKNOWN', []))} | NO_URL {len(groups.get('NO_URL', []))}")

    if args.delete and n_dead:
        for p, _ in groups["DEAD"]:
            db.delete(p)
        db.commit()
        print(f"🗑️ ลบสินค้า DEAD {n_dead} ตัวออกจากตารางแล้ว")
    elif args.delete and not n_dead:
        print("ไม่มีตัว DEAD — ไม่ได้ลบอะไร")
    else:
        print("(ยังไม่ลบ — ถ้าต้องการให้ลบตัว DEAD อัตโนมัติ ใช้ --delete)")
    db.close()


def main():
    ap = argparse.ArgumentParser(prog="product_pipeline", description="จัดการสินค้า Shopee Affiliate ครบวงจร")
    ap.add_argument("--sqlite", action="store_true", help="ใช้ local dev DB (SQLite) แทน Supabase")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_import = sub.add_parser("import-csv", help="นำเข้าสินค้าจาก CSV (พอร์ทัล)")
    p_import.add_argument("file")
    p_import.add_argument("--analyze", action="store_true", help="สร้างคอนเทนต์ AI ให้สินค้าใหม่ด้วย")
    p_import.add_argument("--top", type=int, default=5)
    p_import.add_argument("--style", default="standard")

    p_an = sub.add_parser("analyze", help="สร้างคอนเทนต์ AI ให้สินค้าที่ยังไม่มี")
    p_an.add_argument("--top", type=int, default=10)
    p_an.add_argument("--style", default="standard")

    sub.add_parser("report", help="รายงานตรวจสอบละเอียด")
    p_links = sub.add_parser("check-links", help="ตรวจลิงก์ affiliate ว่าตาย/redirect ผิดหรือยัง")
    p_links.add_argument("--delete", action="store_true", help="ลบสินค้าที่ตรวจว่า DEAD ออกจากตาราง")
    sub.add_parser("fix-scores", help="คำนวณคะแนนใหม่ทุกตัว")

    args = ap.parse_args()
    {"import-csv": cmd_import_csv, "analyze": cmd_analyze,
     "report": cmd_report, "check-links": cmd_check_links,
     "fix-scores": cmd_fix_scores}[args.cmd](args)


if __name__ == "__main__":
    main()
