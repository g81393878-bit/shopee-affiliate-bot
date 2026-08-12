#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Product cards — สร้างการ์ดสินค้าแบบ LINE Flex Message (สะดุดตา + ปุ่มกดซื้อ)
=====================================================================
แปลงรายการสินค้าเป็น Flex Carousel — 1 การ์ด/สินค้า สูงสุด 3 ใบ:
  - หัวการ์ดสีตามคะแนน (แดง=ฮอต / ส้ม=กลาง / เขียว=ธรรมดา) พร้อมชื่อสินค้า
  - ราคาใหญ่ + ค่านายหน้า 💸 + ป้าย 🆕🔥💎 + Hook สั้น
  - ปุ่ม "🛒 ซื้อเลย" (เปิดลิงก์ affiliate) + "🔍 ค้นสินค้า" (กลับไปค้น)

ใช้ใน line_bot.py แทนข้อความยาวๆ เดิม — ไม่ต้องพึ่งรูปสินค้า (CSV ไม่มีคอลัมน์รูป)
"""

import datetime
from typing import List, Optional

from linebot.models import (
    FlexSendMessage, TextSendMessage, URIAction, MessageAction,
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


def _catalog_badges(db) -> dict:
    """id -> badge text (NEW 14 วัน / ขายดี คอมสูง อันดับ 1 ใน 5 ของคลัง)"""
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
        if float(commission or 0) > 0 and float(commission or 0) >= comm_threshold:
            b.append(BADGE_COMMISSION)
        badges[rid] = " ".join(b)
    return badges


def _fmt_price(price) -> str:
    p = float(price or 0)
    return f"{p:,.0f}" if p == int(p) else f"{p:,.2f}"


def _clamp(text: str, limit: int = 90) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _bubble(db, prod: models.Product, idx: int, badges_map: dict) -> dict:
    color = _card_color(prod.ai_score)
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

    if prod.commission and float(prod.commission) > 0:
        body.append({"type": "text", "text": f"💸 ค่านายหน้า: ฿{_fmt_price(prod.commission)}",
                     "size": "sm", "color": "#27AE60", "weight": "bold"})

    body.append({"type": "text", "text": f"📈 คะแนนขายดี: {int(prod.ai_score or 0)}/100",
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
                          title: Optional[str] = None):
    """สร้าง Flex Carousel จากสินค้า (สูงสุด 3 ใบ) — ใช้แทนข้อความยาวๆ

    products ว่าง → ตอบข้อความสั้น (TextSendMessage) แทน
    """
    if not products:
        return TextSendMessage(
            text=f"สวัสดีครับคุณ {user.name} 👋\n\n"
                 "⚠️ ยังไม่มีสินค้าในระบบชั่วคราวครับ ลองค้นชื่อสินค้าดูอีกที หรือส่ง "
                 "\"วันนี้ขายอะไรดี\" ดูสินค้าแนะนำได้ค่ะ 😊"
        )

    badges_map = _catalog_badges(db)
    bubbles = [_bubble(db, p, i, badges_map) for i, p in enumerate(products[:3], 1)]

    names = " / ".join(p.name[:20] for p in products[:3])
    alt = f"{title or '🛒 สินค้า'} {names}".strip()

    return FlexSendMessage(
        alt_text=alt[:200],
        contents={"type": "carousel", "contents": bubbles},
    )
