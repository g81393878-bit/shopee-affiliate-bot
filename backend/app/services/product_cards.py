#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Product cards — การ์ดสินค้า LINE Flex Message (สะอาด ไม่รกตา)
============================================================
แปลงรายการสินค้าเป็น Flex Carousel — 1 การ์ด/สินค้า สูงสุด 3 ใบ

มุมมองลูกค้า (ค่าเริ่มต้น) — เน้นซื้อ สะอาด ไม่มีข้อมูลแอดมิน:
  - หัวการ์ดสีตามคะแนน + ชื่อสินค้า
  - ไม่แสดงราคาตายตัว เพราะราคา Shopee เปลี่ยนตามตัวเลือก/โปรโมชัน
  - ป้าย 🆕/🔥 (ยอดขายจริง) + ยอดขาย/รีวิว
  - ปุ่ม "🛒 ดูราคาล่าสุดใน Shopee" (ลิงก์ affiliate) + "🔍 ค้นสินค้า"

มุมมองเจ้าของร้าน (is_owner=True) — เพิ่มข้อมูลแอดมิน:
  - 💸 ค่านายหน้า + 📈 คะแนน AI + 💡 Hook (ไว้ทำคอนเทนต์)
  - ป้าย 💎 คอมสูง (ข้อมูลฝั่งคนขาย)

ใช้ใน line_bot.py — ไม่ต้องพึ่งรูปสินค้า (CSV ไม่มีคอลัมน์รูป)
"""

import datetime
import re
from typing import List, Optional

from linebot.models import (
    FlexSendMessage, TextSendMessage,
)

from app import models
from app.services.product_price_policy import sanitize_public_product_text

# อักษรจีน/ญี่ปุ่น/เกาหลี — กัน hook ภาษาปน (เช่น "吗") โชว์ให้ลูกค้า
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")

BADGE_NEW = "🆕 ของใหม่"
BADGE_HOT = "🔥 ขายดี"
BADGE_COMMISSION = "💎 คอมสูง"


def _card_color(score: Optional[int]) -> str:
    """สีหัวการ์ดตามคะแนน — ยิ่งสูงยิ่งร้อนแรง"""
    s = int(score or 0)
    if s >= 85:
        return "#E74C3C"   # แดง — ตัวฮอต
    if s >= 65:
        return "#F39C12"   # ส้ม — ขายดี
    return "#2ECC71"       # เขียว — ธรรมดา


def _catalog_badges(db, is_owner: bool) -> dict:
    """id -> badge text (NEW 14 วัน / ขายดี อันดับ 1 ใน 5)
    💎 คอมสูง = ข้อมูลฝั่งคนขาย → เฉพาะ is_owner ถึงเห็น"""
    rows = db.query(
        models.Product.id,
        models.Product.sales_count,
        models.Product.commission,
        models.Product.created_at,
    ).all()
    if not rows:
        return {}
    sales = sorted([(r.sales_count or 0) for r in rows], reverse=True)
    comms = sorted([float(r.commission or 0) for r in rows], reverse=True)
    top_n = max(1, len(rows) // 5)
    sales_threshold = sales[top_n - 1] if sales else 0
    comm_threshold = comms[top_n - 1] if comms else 0
    now = datetime.datetime.now(datetime.timezone.utc)
    badges = {}
    for rid, sales_count, commission, created_at in rows:
        b = []
        if created_at:
            created = created_at if created_at.tzinfo else created_at.replace(tzinfo=datetime.timezone.utc)
            if (now - created).days <= 14:
                b.append(BADGE_NEW)
        if (sales_count or 0) > 0 and (sales_count or 0) >= sales_threshold:
            b.append(BADGE_HOT)
        if is_owner and float(commission or 0) > 0 and float(commission or 0) >= comm_threshold:
            b.append(BADGE_COMMISSION)
        badges[rid] = " ".join(b)
    return badges


def _fmt_price(price) -> str:
    p = float(price or 0)
    return f"{p:,.0f}" if p == int(p) else f"{p:,.2f}"


def _clean_hook(hook: str) -> Optional[str]:
    """hook ที่ปลอดภัยพอโชว์ลูกค้า (สไตล์ Rufus/A+ "ทำไมน่าสนใจ"):
    ไม่มีอักษร CJK (ภาษาปน), ความยาว 8-90 ตัวอักษร — ไม่ผ่าน = ไม่โชว์"""
    h = (hook or "").strip()
    if not h or _CJK_RE.search(h) or len(h) < 8 or len(h) > 90:
        return None
    return h


def _clamp(text: str, limit: int = 90) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _bubble(db, prod: models.Product, idx: int, badges_map: dict, is_owner: bool,
            drop_pct: Optional[float] = None) -> dict:
    color = _card_color(prod.ai_score)
    hook = (db.query(models.Content.hook)
              .filter(models.Content.product_id == prod.id)
              .order_by(models.Content.id.desc()).first())

    body = []
    # 💡 หนึ่งบรรทัด "ทำไมน่าสนใจ" (สไตล์ Amazon Rufus/A+) — เฉพาะ hook ที่ผ่านฟิลเตอร์
    clean_hook = _clean_hook(getattr(hook, "hook", None) or "")
    if not is_owner and clean_hook:
        body.append({"type": "text", "text": f"💡 {_clamp(clean_hook, 80)}",
                     "size": "xs", "color": "#8B4513", "wrap": True})

    # ราคาใน Shopee เปลี่ยนตามตัวเลือกสินค้า สต็อกโปรโมชัน และคูปอง
    # จึงไม่แสดงตัวเลขจากฐานข้อมูลทั้งมุมลูกค้าและเจ้าของร้าน
    body += [
        {
            "type": "box",
            "layout": "baseline",
            "contents": [
                {"type": "text", "text": "🏷️ ราคาขึ้นกับตัวเลือกและโปรโมชัน", "size": "md",
                 "weight": "bold", "color": "#E67E22", "flex": 0},
            ],
        },
        {"type": "text", "text": "⚡ แตะเพื่อดูราคาล่าสุดและคูปองใน Shopee", "size": "xxs",
         "color": "#888888", "wrap": True},
    ]

    # --- Trust line สากล: ⭐ รีวิว · ขายแล้ว X ชิ้น (หลักฐานสังคมชิดราคา แบบ Amazon/Alibaba) ---
    trust = []
    if prod.rating and float(prod.rating) > 0:
        trust.append(f"⭐ {float(prod.rating):.1f}")
    if (prod.sales_count or 0) > 0:
        trust.append(f"ขายแล้ว {int(prod.sales_count):,} ชิ้น")
    if trust:
        body.append({"type": "text", "text": " · ".join(trust), "size": "xs",
                     "color": "#666666", "wrap": True})

    # --- Badges: ไม่เผยตัวเลขราคา/เปอร์เซ็นต์จาก price_history ต่อสาธารณะ ---
    extras = []
    if drop_pct and drop_pct >= 1:
        extras.append("📉 ตรวจพบการเปลี่ยนแปลงราคา — เช็กล่าสุดใน Shopee")
    badge = badges_map.get(prod.id, "")
    if badge:
        extras.append(badge)
    if extras:
        body.append({"type": "text", "text": " · ".join(extras), "size": "xs",
                     "color": "#B8860B", "wrap": True})

    # --- ข้อมูลแอดมิน (เฉพาะเจ้าของร้าน) ---
    if is_owner:
        if prod.price_checked_at:
            checked = prod.price_checked_at
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=datetime.timezone.utc)
            body.append({"type": "text", "text": f"🕒 ข้อมูลคลังอัปเดตล่าสุด: {checked.strftime('%d/%m %H:%M')} UTC",
                         "size": "xxs", "color": "#BBBBBB"})
        if prod.commission and float(prod.commission) > 0:
            body.append({"type": "text", "text": f"💸 ค่านายหน้า: ฿{_fmt_price(prod.commission)}",
                         "size": "sm", "color": "#27AE60", "weight": "bold"})
        body.append({"type": "text", "text": f"📈 คะแนน AI: {int(prod.ai_score or 0)}/100",
                     "size": "xs", "color": "#999999"})
        if hook and hook.hook:
            body.append({"type": "text", "text": f"💡 {_clamp(hook.hook)}",
                         "size": "xs", "color": "#666666", "wrap": True})

    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": color,
            "paddingAll": "sm",
            "contents": [
                {"type": "text", "text": f"{idx}. {_clamp(sanitize_public_product_text(prod.name), 70)}",
                 "size": "sm", "weight": "bold", "color": "#FFFFFF", "wrap": True},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": body,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "color": "#EE4D2D", "height": "sm",
                 "action": {"type": "uri", "label": "🛒 ดูราคาล่าสุดใน Shopee",
                            "uri": prod.affiliate_url or "https://shopee.co.th"}},
                {"type": "button", "style": "secondary", "height": "sm",
                 "action": {"type": "message", "label": "🔍 ค้นสินค้า", "text": "ค้นสินค้า"}},
            ],
        },
    }


def link_button_message(text: str, uri: str, label: str = "เปิดลิงก์"):
    """การ์ดปุ่มเดียว (URI action) — ใช้แทนการแปะ URL ลงในข้อความ
    เหตุผล: LINE ธง "ข้อความนี้อาจไม่ปลอดภัย" เวลามี URL อยู่ใน text message
    (โดยเฉพาะลิงก์สั้น) แต่ปุ่ม flex ไม่โดน — ลูกค้าเห็นหน้าจอสะอาด"""
    return FlexSendMessage(
        alt_text=label,
        contents={
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "text", "text": text, "size": "sm", "wrap": True},
                ],
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "button", "style": "primary", "color": "#E74C3C", "height": "sm",
                     "action": {"type": "uri", "label": label, "uri": uri}},
                ],
            },
        },
    )


def product_cards_message(db, user: models.User, products: List[models.Product],
                          title: Optional[str] = None, is_owner: bool = False):
    """สร้าง Flex Carousel จากสินค้า (สูงสุด 3 ใบ)

    is_owner=False (ลูกค้า): เฉพาะข้อมูลซื้อ — ยอดขาย/ปุ่มดูราคาล่าสุด (สะอาด)
    is_owner=True (เจ้าของ): เพิ่ม ค่านายหน้า/คะแนน AI/Hook/ป้ายคอมสูง

    products ว่าง → ตอบข้อความสั้น (TextSendMessage) แทน
    """
    if not products:
        return TextSendMessage(
            text=f"สวัสดีครับคุณ {user.name} 👋\n\n"
                 "⚠️ ยังไม่มีสินค้าในระบบชั่วคราวครับ ลองค้นชื่อสินค้าดูอีกที หรือส่ง "
                 "\"วันนี้ขายอะไรดี\" ดูสินค้าแนะนำได้ค่ะ 😊"
        )

    badges_map = _catalog_badges(db, is_owner)
    # ราคาลงล่าสุดต่อสินค้า (จาก price_history — แสดง 📉 เฉพาะตอนมีข้อมูลจริง)
    ids = [p.id for p in products[:5]]
    drops = {}
    if ids:
        rows = (db.query(models.PriceHistory.product_id, models.PriceHistory.drop_pct)
                  .filter(models.PriceHistory.product_id.in_(ids))
                  .order_by(models.PriceHistory.created_at.desc()).all())
        for pid, drop in rows:
            if pid not in drops:
                drops[pid] = float(drop or 0)
    bubbles = [_bubble(db, p, i, badges_map, is_owner, drops.get(p.id))
               for i, p in enumerate(products[:5], 1)]

    names = " / ".join(sanitize_public_product_text(p.name)[:20] for p in products[:5])
    alt = f"{title or '🛒 สินค้า'} {names}".strip()

    return FlexSendMessage(
        alt_text=alt[:200],
        contents={"type": "carousel", "contents": bubbles},
    )
