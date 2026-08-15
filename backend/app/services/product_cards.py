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
import re
from typing import List, Optional

from linebot.models import (
    FlexSendMessage, TextSendMessage,
)

from app import models

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

    # --- ราคาใหญ่ + เริ่มต้น (ราคาจริงตามโปรฯ ในลิงก์ — ไม่การันตีราคาคงที่) ---
    body += [
        {
            "type": "box",
            "layout": "baseline",
            "contents": [
                {"type": "text", "text": f"฿{_fmt_price(prod.price)}", "size": "xxl",
                 "weight": "bold", "color": color, "flex": 0},
                {"type": "text", "text": " เริ่มต้น", "size": "xs", "color": "#8C8C8C", "flex": 0},
            ],
        },
        {"type": "text", "text": "ราคาจริงตามโปรโมชันในลิงก์", "size": "xxs",
         "color": "#AAAAAA", "wrap": True},
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

    # --- Badges: 🆕 / 🔥 ขายดี / 📉 ราคาลง X% (anchor ราคาแบบ Amazon Deal) ---
    extras = []
    if drop_pct and drop_pct >= 1:
        extras.append(f"📉 ราคาลง {drop_pct:.0f}%")
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
            body.append({"type": "text", "text": f"🕒 ราคาอัปเดตล่าสุด: {checked.strftime('%d/%m %H:%M')} UTC",
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

    names = " / ".join(p.name[:20] for p in products[:5])
    alt = f"{title or '🛒 สินค้า'} {names}".strip()

    return FlexSendMessage(
        alt_text=alt[:200],
        contents={"type": "carousel", "contents": bubbles},
    )


def format_radar_deal_flex_message(
    group_name: str,
    post_text: str,
    post_url: str,
    demand_score: int,
    urgency: str,
    matched_product: Optional[models.Product] = None,
    suggested_reasons: Optional[List[str]] = None,
    copy_text: Optional[str] = None,
) -> FlexSendMessage:
    """สร้าง Flex Message แจ้งเตือนดีลเรดาร์ความต้องการ (Social Demand Radar V1) สำหรับแอดมิน"""
    score = int(demand_score or 0)
    header_color = "#E74C3C" if score >= 85 else ("#E67E22" if score >= 70 else "#3498DB")
    urgency_text = "⚡ ด่วนมาก (High)" if (urgency or "").lower() == "high" else (
        "⏱️ ปานกลาง (Medium)" if (urgency or "").lower() == "medium" else "⏳ ทั่วไป (Low)"
    )

    body_contents: List[dict] = [
        {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F8F9FA",
            "cornerRadius": "md",
            "paddingAll": "sm",
            "contents": [
                {"type": "text", "text": "📝 ข้อความในกลุ่ม:", "size": "xxs", "color": "#888888", "weight": "bold"},
                {"type": "text", "text": f'"{_clamp(post_text or "", 150)}"', "size": "xs", "color": "#333333", "wrap": True},
            ],
        },
    ]

    # Product section
    if matched_product:
        p_price = _fmt_price(matched_product.price)
        p_comm = _fmt_price(matched_product.commission)
        p_rating = float(matched_product.rating or 0)
        p_sales = int(matched_product.sales_count or 0)
        reason_text = " · ".join(suggested_reasons[:2]) if suggested_reasons else "สินค้าขายดี ตรงตามคำค้นหา"

        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#EBF5FB",
            "cornerRadius": "md",
            "paddingAll": "sm",
            "contents": [
                {"type": "text", "text": "🏷️ สินค้าแนะนำในคลัง:", "size": "xxs", "color": "#2980B9", "weight": "bold"},
                {"type": "text", "text": _clamp(matched_product.name, 80), "size": "sm", "weight": "bold", "color": "#2C3E50", "wrap": True},
                {
                    "type": "box",
                    "layout": "baseline",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": f"฿{p_price}", "size": "md", "weight": "bold", "color": "#E74C3C", "flex": 0},
                        {"type": "text", "text": f" · 💸 คอม ฿{p_comm} · ⭐ {p_rating:.1f} ({p_sales:,} ชิ้น)", "size": "xxs", "color": "#27AE60", "flex": 0},
                    ],
                },
                {"type": "text", "text": f"💡 เหตุผล: {_clamp(reason_text, 100)}", "size": "xxs", "color": "#7F8C8D", "wrap": True, "margin": "xs"},
            ],
        })
    else:
        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F2F4F4",
            "cornerRadius": "md",
            "paddingAll": "sm",
            "contents": [
                {"type": "text", "text": "🏷️ สินค้าแนะนำ:", "size": "xxs", "color": "#7F8C8D", "weight": "bold"},
                {"type": "text", "text": "ไม่พบสินค้าในคลังที่ตรงกับคำค้นหา", "size": "xs", "color": "#95A5A6"},
            ],
        })

    # Deal copy section
    body_contents.append({
        "type": "box",
        "layout": "vertical",
        "backgroundColor": "#FEF9E7",
        "cornerRadius": "md",
        "paddingAll": "sm",
        "contents": [
            {"type": "text", "text": "💬 ร่างข้อความสไตล์ป้าเข็ม (พร้อมคอมเมนต์):", "size": "xxs", "color": "#D35400", "weight": "bold"},
            {"type": "text", "text": _clamp(copy_text or "ไม่มีข้อความร่าง", 250), "size": "xs", "color": "#7D6608", "wrap": True},
        ],
    })

    safe_post_url = post_url.strip() if post_url and post_url.startswith("http") else "https://facebook.com"
    safe_shopee_url = (
        matched_product.affiliate_url.strip()
        if (matched_product and matched_product.affiliate_url and matched_product.affiliate_url.startswith("http"))
        else "https://shopee.co.th"
    )

    footer_buttons = [
        {
            "type": "button",
            "style": "primary",
            "color": "#1877F2",
            "height": "sm",
            "action": {
                "type": "uri",
                "label": "🔗 เปิดโพสต์ Facebook ทันที",
                "uri": safe_post_url,
            },
        },
        {
            "type": "button",
            "style": "secondary",
            "height": "sm",
            "action": {
                "type": "uri",
                "label": "🛒 ตรวจสอบสินค้าบน Shopee",
                "uri": safe_shopee_url,
            },
        },
    ]

    prod_name_label = matched_product.name if matched_product else "พบความต้องการใหม่"
    alt_text = f"🎯 [Demand Radar] ดีลแนะนำ: {_clamp(prod_name_label, 40)} (Score {score}/100)"

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": header_color,
            "paddingAll": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "🎯 SOCIAL DEMAND RADAR", "weight": "bold", "color": "#FFFFFF", "size": "sm", "flex": 1},
                        {"type": "text", "text": f"🔥 Score {score}/100", "weight": "bold", "color": "#FFF200", "size": "xs", "align": "end"},
                    ],
                },
                {
                    "type": "text",
                    "text": f"{urgency_text} · {_clamp(group_name or 'กลุ่ม Facebook', 40)}",
                    "color": "#FFFFFFCC",
                    "size": "xxs",
                    "margin": "xs",
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": body_contents,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": footer_buttons,
        },
    }

    return FlexSendMessage(alt_text=alt_text[:200], contents=bubble)

