#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Product cards — การ์ดสินค้า LINE Flex Message (สะอาด ไม่รกตา)
============================================================
แปลงรายการสินค้าเป็น Flex Carousel — 1 การ์ด/สินค้า สูงสุด 3 ใบ

มุมมองลูกค้า (ค่าเริ่มต้น) — เน้นซื้อ สะอาด ไม่มีข้อมูลแอดมิน:
  - หัวการ์ดสีตามคะแนน + ชื่อสินค้า
  - ราคาใหญ่ + ป้าย 🆕/🔥 (ยอดขายจริง) + ยอดขาย/รีวิว
  - ปุ่ม "🛒 ซื้อเลย" (ลิงก์ affiliate) + "🔍 ค้นสินค้า"

มุมมองเจ้าของร้าน (is_owner=True) — เพิ่มข้อมูลแอดมิน:
  - 💸 ค่านายหน้า + 📈 คะแนน AI + 💡 Hook (ไว้ทำคอนเทนต์)
  - ป้าย 💎 คอมสูง (ข้อมูลฝั่งคนขาย)

ใช้ใน line_bot.py — ไม่ต้องพึ่งรูปสินค้า (CSV ไม่มีคอลัมน์รูป)
"""

import datetime
from typing import List, Optional

from linebot.models import (
    FlexSendMessage, TextSendMessage,
)

from app import models

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


def _fmt_sales(n) -> Optional[str]:
    n = int(n or 0)
    if n <= 0:
        return None
    return f"🔥 ขายแล้ว {n:,} ชิ้น"


def _clamp(text: str, limit: int = 90) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _bubble(db, prod: models.Product, idx: int, badges_map: dict, is_owner: bool) -> dict:
    color = _card_color(prod.ai_score)

    # --- ข้อมูลลูกค้า (ทุกคนเห็น) ---
    body = [
        {
            "type": "box",
            "layout": "baseline",
            "contents": [
                {"type": "text", "text": f"฿{_fmt_price(prod.price)}", "size": "xxl",
                 "weight": "bold", "color": color, "flex": 0},
                {"type": "text", "text": " บาท", "size": "sm", "color": "#8C8C8C", "flex": 0},
            ],
        },
    ]

    badge = badges_map.get(prod.id, "")
    if badge:
        body.append({"type": "text", "text": badge, "size": "xs", "color": "#B8860B", "wrap": True})

    sales_line = _fmt_sales(prod.sales_count)
    if sales_line:
        body.append({"type": "text", "text": sales_line, "size": "sm", "color": "#555555"})

    if prod.rating and float(prod.rating) > 0:
        body.append({"type": "text", "text": f"⭐ {float(prod.rating):.1f}",
                     "size": "xs", "color": "#999999"})

    # --- ข้อมูลแอดมิน (เฉพาะเจ้าของร้าน) ---
    if is_owner:
        if prod.commission and float(prod.commission) > 0:
            body.append({"type": "text", "text": f"💸 ค่านายหน้า: ฿{_fmt_price(prod.commission)}",
                         "size": "sm", "color": "#27AE60", "weight": "bold"})
        body.append({"type": "text", "text": f"📈 คะแนน AI: {int(prod.ai_score or 0)}/100",
                     "size": "xs", "color": "#999999"})
        content_hook = (db.query(models.Content)
                          .filter(models.Content.product_id == prod.id)
                          .order_by(models.Content.id.desc()).first())
        if content_hook and content_hook.hook:
            body.append({"type": "text", "text": f"💡 {_clamp(content_hook.hook)}",
                         "size": "xs", "color": "#666666", "wrap": True})

    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": color,
            "paddingAll": "sm",
            "contents": [
                {"type": "text", "text": f"{idx}. {_clamp(prod.name, 70)}",
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
                {"type": "button", "style": "primary", "color": color, "height": "sm",
                 "action": {"type": "uri", "label": "🛒 ซื้อเลย",
                            "uri": prod.affiliate_url or "https://shopee.co.th"}},
                {"type": "button", "style": "secondary", "height": "sm",
                 "action": {"type": "message", "label": "🔍 ค้นสินค้า", "text": "ค้นสินค้า"}},
            ],
        },
    }


def product_cards_message(db, user: models.User, products: List[models.Product],
                          title: Optional[str] = None, is_owner: bool = False):
    """สร้าง Flex Carousel จากสินค้า (สูงสุด 3 ใบ)

    is_owner=False (ลูกค้า): เฉพาะข้อมูลซื้อ — ราคา/ยอดขาย/ปุ่มซื้อ (สะอาด)
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
    bubbles = [_bubble(db, p, i, badges_map, is_owner) for i, p in enumerate(products[:3], 1)]

    names = " / ".join(p.name[:20] for p in products[:3])
    alt = f"{title or '🛒 สินค้า'} {names}".strip()

    return FlexSendMessage(
        alt_text=alt[:200],
        contents={"type": "carousel", "contents": bubbles},
    )
