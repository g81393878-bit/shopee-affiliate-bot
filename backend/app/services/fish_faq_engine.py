# -*- coding: utf-8 -*-
"""
backend/app/services/fish_faq_engine.py — ระบบโหลดคลังคำถาม-คำตอบมาตรฐานจากไฟล์ CSV แม่บท (data/fish_faq_rules.csv)
รองรับการแก้ไขผ่าน Microsoft Excel ได้ทันที (UTF-8 with BOM) โดยบอทจะโหลดใหม่เองอัตโนมัติเมื่อไฟล์ถูกบันทึก
"""

import csv
import os
from pathlib import Path

from app.services.sales_status import closed_notice, is_sales_closed

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FAQ_CSV_PATH = ROOT_DIR / "data" / "fish_faq_rules.csv"
BACKEND_FAQ_CSV_PATH = BACKEND_DATA_DIR / "fish_faq_rules.csv"

# ร้านยุติการจำหน่ายแล้ว — ไม่มี seed คำตอบที่มีราคา/แพ็กเกจอีก
# (ถ้าเปิดขายอีกครั้ง ให้เติมกฎกลับเข้าที่ data/fish_faq_rules.csv)
DEFAULT_FAQ_RULES: list = []

_CACHE_MTIME: float = 0.0
_CACHED_RULES: list[dict] = []


def ensure_faq_csv_exists(csv_path: Path = FAQ_CSV_PATH, force_overwrite: bool = False) -> Path:
    """สร้างไฟล์ data/fish_faq_rules.csv อัตโนมัติหากยังไม่มี (พร้อม UTF-8 BOM สำหรับเปิดใน Excel)"""
    if not force_overwrite:
        if csv_path.exists() and csv_path.stat().st_size > 10:
            return csv_path
        if BACKEND_FAQ_CSV_PATH.exists() and BACKEND_FAQ_CSV_PATH.stat().st_size > 10:
            return BACKEND_FAQ_CSV_PATH
    fieldnames = [
        "rule_id",
        "priority",
        "category",
        "keywords",
        "exclude_keywords",
        "require_not_question",
        "strategy_note",
        "comment_reply_template",
        "inbox_prefix_template",
    ]
    for target_path in (csv_path, BACKEND_FAQ_CSV_PATH):
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in DEFAULT_FAQ_RULES:
                    writer.writerow(row)
        except Exception:
            pass
    return csv_path if csv_path.exists() else BACKEND_FAQ_CSV_PATH


def load_faq_rules(csv_path: Path = FAQ_CSV_PATH) -> list[dict]:
    """โหลดกฎคำถาม-คำตอบจากไฟล์ CSV (มีระบบ Auto-Reload เมื่อแก้ไขไฟล์ใน Excel แล้วกด Save)"""
    global _CACHE_MTIME, _CACHED_RULES
    csv_path = ensure_faq_csv_exists(csv_path)
    try:
        mtime = csv_path.stat().st_mtime
        if _CACHED_RULES and mtime == _CACHE_MTIME:
            return _CACHED_RULES
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rules = [dict(r) for r in reader if (r.get("keywords") or "").strip()]
        rules.sort(key=lambda x: int(x.get("priority") or 999))
        _CACHED_RULES = rules
        _CACHE_MTIME = mtime
        return rules
    except Exception:
        return DEFAULT_FAQ_RULES


def match_faq_rule(
    comment_text: str,
    greeting: str = "สวัสดีค่ะคุณลูกค้า 🙏💕",
    web_url: str = "https://watt29.github.io/pakhem-shop/fish.html",
) -> dict | None:
    """ร้านยุติการจำหน่ายแล้ว — ไม่มี FAQ ขายสินค้าอีก (คืน None เสมอ)."""
    return None


GREETING_OR_MENU_WORDS = {
    "สวัสดี", "สวัสดีค่ะ", "สวัสดีครับ", "สวัสดีจ้า", "ดีจ้า", "ดีค่ะ", "ดีครับ",
    "ทัก", "ทักค่ะ", "ทักครับ", "สนใจ", "สนใจค่ะ", "สนใจครับ", "สนใจจ้า",
    "สั่งปลา", "สั่งซื้อ", "สั่งของ", "ราคา", "ขอราคา", "เมนู", "แพ็กเกจ",
    "hi", "hello", "มีของไหม", "มีของมั้ย", "พร้อมส่งไหม",
    "ทำเลย", "จัดเลย", "เอาเลย", "สั่งเลย", "ส่งเลย", "ส่งมาเลย", "ตกลง", "โอเค", "จองเลย",
    "เอาครับ", "เอาค่ะ", "จัดมา", "จัดส่งเลย", "ลุยเลย", "เอา1โล", "เอา 1 โล", "เอา1กิโล", "เอา 1 กิโล",
    "เอา 2 โล", "เอา2โล", "เอา 2 กิโล", "เอา2กิโล", "เอาสองโล", "เอาสองกิโล",
    "เอา 500", "เอา500", "เอา 500g", "เอา500g", "เอา 500 กรัม", "เอา500กรัม", "เอาครึ่งโล", "เอาครึ่งกิโล",
    "เอาโลนึง", "เอา 1 โลครับ", "เอา 1 โลค่ะ", "เอา 2 โลครับ", "เอา 2 โลค่ะ",
    "เอาชุด 1", "เอาชุด1", "เอาชุด 2", "เอาชุด2", "เอาชุด 3", "เอาชุด3",
    "รับ 1 โล", "รับ 2 โล", "รับ 500", "รับ 1 ชุด", "รับชุด 1", "รับชุด 2", "รับชุด 3",
    "ส่งมาเลยครับ", "ส่งมาเลยค่ะ",
}


def is_weird_or_unmatched_question(text: str) -> bool:
    """ตรวจสอบว่าเป็นคำถามหรือข้อความเฉพาะเจาะจงที่หลุดจาก CSV (ไม่ใช่แค่คำทักทายหรือคำว่า 'สนใจ')"""
    clean = (text or "").strip().lower()
    if not clean or len(clean) < 3:
        return False
    if clean in GREETING_OR_MENU_WORDS:
        return False
    # ตรวจจับคำสั่งซื้อสั้นๆ ของลูกค้าผู้สูงอายุ
    order_words = ["เอา 1", "เอา 2", "เอา 500", "รับ 1", "รับ 2", "รับ 500", "ส่งมา", "ส่งเลย", "จัดส่ง", "สั่ง 1", "สั่ง 2", "สั่ง 3", "สั่ง 500", "เอาชุด", "รับชุด"]
    if any(ow in clean for ow in order_words):
        return False
    # ถ้าเป็นคำทักทายสั้นๆ เช่น สวัสดี + สนใจ
    stripped = clean
    for w in ("สวัสดีค่ะ", "สวัสดีครับ", "สวัสดีจ้า", "สวัสดี", "สนใจค่ะ", "สนใจครับ", "สนใจจ้า", "สนใจ", "ค่ะ", "ครับ", "จ้า", "นะ", "คะ"):
        stripped = stripped.replace(w, "").strip()
    if not stripped:
        return False
    return True


def answer_out_of_csv_question(
    text: str,
    greeting: str = "สวัสดีค่ะคุณลูกค้า 🙏💕",
    web_url: str = "https://watt29.github.io/pakhem-shop/fish.html",
) -> dict | None:
    """ตอบคำถามทั่วไปแบบปิดรับออเดอร์ (ไม่มีราคา/แพ็กเกจ)."""
    return {"mode": "SALES_CLOSED", "reply": f"{greeting} {closed_notice()}"}
