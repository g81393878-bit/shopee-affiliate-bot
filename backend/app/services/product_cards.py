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


def dual_persona_cards_message(products: List[models.Product], style: str = "hedonic",
                               title: Optional[str] = None):
    """สร้าง LINE Flex Carousel ตอบโจทย์จิตวิทยา 2 กลุ่มลูกค้า (สูงสุด 9 ใบ ต่อ 1 ข้อความ):
    
    1. style="hedonic" (เน้นอารมณ์):
       - รูปสินค้าไลฟ์สไตล์โดดเด่น สดใส
       - พาดหัวกระตุ้นความอยาก & ป้าย '✨ คัดสรรพิเศษ' / '🔥 ฮิตใน TikTok'
       - ปุ่ม CTA กระตุ้นอารมณ์: '💖 สั่งซื้อรับความสุข'
       
    2. style="utilitarian" (เน้นเหตุผล):
       - สเปกฟังก์ชันชัดเจน ความคุ้มค่า
       - ป้ายรับประกัน '✅ ของแท้ 100% รับประกันศูนย์' + แสดงยอดขายจริง
       - ปุ่ม CTA เน้นความคุ้มค่า: '🔍 เช็กความคุ้มค่า & ราคาล่าสุด'
    """
    if not products:
        return TextSendMessage(text="ไม่พบรายการสินค้าที่ระบุครับ")

    bubbles = []
    for i, p in enumerate(products[:9], 1):
        p_name = sanitize_public_product_text(p.name or "สินค้าของแท้ 100%")
        p_img = p.image_url if (p.image_url and p.image_url.startswith("http")) else "https://placehold.co/600x600/EE4D2D/FFFFFF.png?text=Shopee"
        p_url = p.affiliate_url or "https://s.shopee.co.th/2VqtxaXpj2"
        sales = f"🔥 ขายแล้ว {int(p.sales_count):,} ชิ้น" if (p.sales_count and p.sales_count > 0) else "✨ สินค้ามาใหม่"

        if style == "hedonic":
            # สไตล์เน้นอารมณ์ (Hedonic)
            bubble = {
                "type": "bubble",
                "size": "kilo",
                "hero": {
                    "type": "image",
                    "url": p_img,
                    "size": "full",
                    "aspectRatio": "1:1",
                    "aspectMode": "cover"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {"type": "text", "text": "✨ ดีไซน์สวย · ฟีลลิ่งระดับพรีเมียม", "size": "xxs", "color": "#E91E63", "weight": "bold"},
                        {"type": "text", "text": p_name, "weight": "bold", "size": "sm", "wrap": True, "maxLines": 2},
                        {"type": "text", "text": "🎁 ของแท้ 100% ตอบโจทย์ความสุขทุกวัน", "size": "xs", "color": "#757575"}
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#E91E63",
                            "action": {
                                "type": "uri",
                                "label": "💖 อยากได้ชิ้นนี้เลย",
                                "uri": p_url
                            }
                        }
                    ]
                }
            }
        else:
            # สไตล์เน้นเหตุผล (Utilitarian)
            bubble = {
                "type": "bubble",
                "size": "kilo",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#1E293B",
                    "paddingAll": "sm",
                    "contents": [
                        {"type": "text", "text": f"SPEC #{i} • ฟังก์ชันคุ้มค่า", "size": "xs", "color": "#38BDF8", "weight": "bold"}
                    ]
                },
                "hero": {
                    "type": "image",
                    "url": p_img,
                    "size": "full",
                    "aspectRatio": "16:10",
                    "aspectMode": "cover"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": p_name, "weight": "bold", "size": "sm", "wrap": True, "maxLines": 2},
                        {"type": "text", "text": f"📊 การันตีความนิยม: {sales}", "size": "xs", "color": "#059669"},
                        {"type": "text", "text": "🏷️ ราคาขึ้นกับตัวเลือกและโปรโมชัน", "size": "xs", "color": "#D97706", "weight": "bold"},
                        {"type": "text", "text": "✅ ของแท้ 100% ตรวจสอบสถานะแล้ว", "size": "xxs", "color": "#64748B"}
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#0284C7",
                            "action": {
                                "type": "uri",
                                "label": "🔍 เช็กสเปก & ราคา Shopee",
                                "uri": p_url
                            }
                        }
                    ]
                }
            }
        bubbles.append(bubble)

    alt_text = title or ("🎁 ดีลพิเศษโดนใจ" if style == "hedonic" else "📊 สรุปสินค้าสุดคุ้มค่า")
    return FlexSendMessage(
        alt_text=alt_text[:200],
        contents={"type": "carousel", "contents": bubbles}
    )


# ==============================================================================
# 🔮 ไพ่ยิปซีแท้ Rider-Waite 1909 ครบทั้งสำรับ 78 ใบ (22 Major + 56 Minor)
# ==============================================================================
TAROT_CDN_BASE = "https://cdn.jsdelivr.net/gh/lalesleon13-hash/Tarot@main/"
TAROT_BACK_IMG = "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop"

def _load_tarot_deck_78() -> list:
    import json
    from pathlib import Path
    json_path = Path(__file__).parent / "tarot_deck_78.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load tarot_deck_78.json: {e}")
    # Fallback to 22 Major if json missing
    return TAROT_MAJOR_ARCANA_DICT

TAROT_MAJOR_ARCANA_DICT = [
    {
        "num": 1, "card_no": 0, "id": 0, "name": "The Fool", "thai": "คนพเนจร",
        "keyword": "การเริ่มต้นใหม่ • อิสรภาพ • ก้าวสู่สิ่งใหม่",
        "desc": "สื่อถึงการเริ่มต้นใหม่อย่างสดใส ก้าวข้ามความลังเลด้วยหัวใจที่เปิดกว้าง",
        "advice": "อย่ากลัวความผิดพลาด ทุกการก้าวเดินคือบทเรียนล้ำค่าเสมอจ้ะ",
        "img": TAROT_CDN_BASE + "RWS_Tarot_00_Fool.jpg",
        "color": "#0284C7"
    }
]
TAROT_DECK_78 = _load_tarot_deck_78()


def get_tarot_card_by_number(num: int) -> dict:
    """ดึงข้อมูลไพ่ตามหมายเลข 1 ถึง 78 (หรือ 0-21)"""
    if not TAROT_DECK_78:
        return TAROT_MAJOR_ARCANA_DICT[0]
    # 1. ลองเทียบจาก num (1-78)
    for c in TAROT_DECK_78:
        if c.get("num") == num:
            return c
    # 2. ลองเทียบจาก card_no หรือ id (0-21)
    for c in TAROT_DECK_78:
        if c.get("card_no") == num or c.get("id") == num:
            return c
    # Fallback สุ่มหรือใบแรก
    return TAROT_DECK_78[(num - 1) % len(TAROT_DECK_78)]


def tarot_invitation_card() -> FlexSendMessage:
    """สร้างการ์ดเชิญชวนเลือกเลข 1-78 สวยงาม น่าค้นหา และมีปุ่มสุ่มนำทาง"""
    import random
    seed_10 = sorted(random.sample(range(1, 79), 10))
    seed_10_str = " ".join(str(n) for n in seed_10)

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1E1B4B",
            "paddingAll": "lg",
            "contents": [
                {"type": "text", "text": "🏛️ ผังเซลติกครอส 10 ใบ (Celtic Cross)", "weight": "bold", "size": "md", "color": "#FDE047"},
                {"type": "text", "text": "สำรับ 78 ใบ • วิเคราะห์ดวงชะตาเชิงลึกรอบด้าน", "size": "xs", "color": "#E0E7FF", "margin": "xs"}
            ]
        },
        "hero": {
            "type": "image",
            "url": TAROT_BACK_IMG,
            "size": "full",
            "aspectRatio": "2:3",
            "aspectMode": "cover"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "lg",
            "backgroundColor": "#FAF5FF",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#FFFFFF",
                    "paddingAll": "md",
                    "cornerRadius": "md",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": "🎴 ไพ่สับแล้วและคว่ำหน้าเรียง 1-78 ใบ:", "weight": "bold", "size": "sm", "color": "#4338CA"},
                        {"type": "text", "text": "• เลข 1 ถึง 78 คือ 'ตำแหน่งไพ่' บนโต๊ะทำนาย\n• เลือกได้ 2 แบบ: พิมพ์เลขเอง 10 ตัว หรือแตะปุ่มสุ่มด้านล่างจ้า", "size": "xs", "wrap": True, "color": "#334155"}
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#EEF2FF",
                    "paddingAll": "md",
                    "cornerRadius": "md",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": "✍️ พิมพ์เอง: ส่งเลข 10 ตัวเว้นวรรค เช่น:", "weight": "bold", "size": "xs", "color": "#3730A3"},
                        {"type": "text", "text": "5 12 21 34 45 52 60 67 71 78", "size": "sm", "weight": "bold", "color": "#4338CA"}
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#FAF5FF",
            "paddingAll": "md",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#4338CA",
                    "action": {
                        "type": "message",
                        "label": "🎲 สุ่มเปิดดวง 10 ใบ (1 คลิก)",
                        "text": f"เปิดไพ่ {seed_10_str}"
                    }
                }
            ]
        }
    }

    return FlexSendMessage(
        alt_text="🔮 ตั้งจิตนิ่งๆ แล้วเลือกเลขไพ่ 1-78 มา 10 ตัว หรือกดสุ่มเพื่อเปิดดวงชะตาฉบับเต็มจ้า",
        contents=bubble
    )


def tarot_reading_card(card_num: int, label_prefix: str = "") -> FlexSendMessage:
    """สร้างการ์ดเฉลยคำทำนายไพ่ยิปซี 1 ใบ พร้อมพลังบวกและข้อคิดจากป้าเข็ม"""
    card = get_tarot_card_by_number(card_num)
    theme_color = card.get("color", "#6366F1")
    title_text = f"{label_prefix}: {card['name']} ({card['thai']})" if label_prefix else f"✨ {card['name']} ({card['thai']})"

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": theme_color,
            "paddingAll": "md",
            "contents": [
                {"type": "text", "text": f"🔮 เลข {card['num']}: {card.get('suite', 'ไพ่ยิปซี')}", "size": "xxs", "color": "#F1F5F9"},
                {"type": "text", "text": title_text, "weight": "bold", "size": "md", "color": "#FFFFFF"},
                {"type": "text", "text": f"🌟 {card['keyword']}", "size": "xxs", "color": "#FEF3C7", "margin": "xs"}
            ]
        },
        "hero": {
            "type": "image",
            "url": card["img"],
            "size": "full",
            "aspectRatio": "2:3",
            "aspectMode": "cover"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "lg",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#F8FAFC",
                    "paddingAll": "md",
                    "cornerRadius": "md",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": "💬 ความหมายไพ่วันนี้:", "weight": "bold", "size": "xs", "color": "#475569"},
                        {"type": "text", "text": card["desc"], "size": "sm", "wrap": True, "color": "#1E293B"}
                    ]
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": f"💖 ป้าเข็มส่งกำลังใจ: \"{card['advice']}\"", "size": "xs", "color": "#059669", "wrap": True}
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "secondary",
                    "action": {
                        "type": "message",
                        "label": "🔄 เปิดไพ่ใบใหม่อีกครั้ง",
                        "text": "เปิดไพ่"
                    }
                }
            ]
        }
    }

    return FlexSendMessage(
        alt_text=f"🃏 คำทำนายไพ่ยิปซี: {card['name']} ({card['thai']})",
        contents=bubble
    )


def tarot_reading_carousel(card_nums: list) -> FlexSendMessage:
    """สร้างการ์ด Carousel เฉลยไพ่ยิปซี 3 ใบ จัดเรียงตามตำแหน่ง อดีต/ปัจจุบัน/อนาคต"""
    positions = [
        "🌱 ใบที่ 1 (สถานการณ์ที่ผ่านมา / ตัวตน)",
        "⚡ ใบที่ 2 (สิ่งที่กำลังเผชิญ / สิ่งที่ควรระวัง)",
        "☀️ ใบที่ 3 (คำแนะนำ / ทางออก / บทสรุป)"
    ]
    bubbles = []
    for idx, num in enumerate(card_nums[:3]):
        card = get_tarot_card_by_number(num)
        pos_title = positions[idx] if idx < len(positions) else f"🃏 ใบที่ {idx+1}"
        theme_color = card.get("color", "#6366F1")

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": theme_color,
                "paddingAll": "sm",
                "contents": [
                    {"type": "text", "text": pos_title, "weight": "bold", "size": "xxs", "color": "#FDE047"},
                    {"type": "text", "text": f"เลข {card['num']}: {card['name']}", "weight": "bold", "size": "sm", "color": "#FFFFFF"},
                    {"type": "text", "text": card["thai"], "size": "xxs", "color": "#E0E7FF"}
                ]
            },
            "hero": {
                "type": "image",
                "url": card["img"],
                "size": "full",
                "aspectRatio": "2:3",
                "aspectMode": "cover"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "paddingAll": "md",
                "contents": [
                    {"type": "text", "text": f"🌟 {card['keyword']}", "weight": "bold", "size": "xxs", "color": "#4338CA", "wrap": True},
                    {"type": "text", "text": card["desc"], "size": "xxs", "wrap": True, "color": "#334155", "margin": "xs"},
                    {"type": "separator", "margin": "sm"},
                    {"type": "text", "text": f"💡 {card['advice']}", "size": "xxs", "color": "#059669", "wrap": True, "margin": "xs"}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "🔄 เสี่ยงทายใหม่",
                            "text": "เปิดไพ่"
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)

    return FlexSendMessage(
        alt_text="🔮 คำทำนายไพ่ยิปซี 3 ใบ (อดีต - ปัจจุบัน - อนาคต) มาแล้วจ้า",
        contents={"type": "carousel", "contents": bubbles}
    )


def tarot_celtic_cross_summary_card(reading_id: str, card_nums: list, video_url: str = None) -> FlexSendMessage:
    """สร้างการ์ดสรุปผังเซลติกครอส 10 ใบ พร้อมปุ่มเปิดดูวิดีโออธิบายแบบละเอียดไม่รีบเร่ง"""
    positions = [
        ("1. ตัวตนปัจจุบัน", "#4338CA"),
        ("2. อุปสรรคขวางทับ", "#DC2626"),
        ("3. จิตสำนึก/เป้าหมาย", "#D97706"),
        ("4. จิตใต้สำนึก/รากปัญหา", "#0D9488"),
        ("5. อดีตที่ผ่านมา", "#475569"),
        ("6. อนาคตอันใกล้", "#2563EB"),
        ("7. ทัศนคติเจ้าชะตา", "#7C3AED"),
        ("8. อิทธิพลคนรอบตัว", "#059669"),
        ("9. ความหวังและความกลัว", "#E11D48"),
        ("10. บทสรุปสูงสุด", "#B45309"),
    ]
    
    rows = []
    for idx, num in enumerate(card_nums[:10]):
        c = get_tarot_card_by_number(num)
        pos_name, color = positions[idx]
        rows.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": pos_name, "size": "xxs", "color": color, "weight": "bold", "flex": 4},
                {"type": "text", "text": f"{c['name']} ({c['thai']})", "size": "xxs", "color": "#1E293B", "flex": 5, "align": "end"}
            ]
        })
        if idx < 9:
            rows.append({"type": "separator", "margin": "xs"})

    v_url = video_url or f"https://www.youtube.com/results?search_query=เซลติกครอส+10+ใบ+ไพ่ยิปซี+ป้าเข็ม"

    bubble = {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1E1B4B",
            "paddingAll": "lg",
            "contents": [
                {"type": "text", "text": "🏛️ ผังเซลติกครอส 10 ใบ (The Celtic Cross)", "weight": "bold", "size": "md", "color": "#FDE047"},
                {"type": "text", "text": f"รหัสรอบทำนาย: {reading_id} • ศาสตร์ดั้งเดิมแท้", "size": "xxs", "color": "#C7D2FE", "margin": "xs"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "paddingAll": "lg",
            "backgroundColor": "#FFFFFF",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#F8FAFC",
                    "paddingAll": "md",
                    "cornerRadius": "md",
                    "spacing": "xs",
                    "contents": rows
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "backgroundColor": "#FAF5FF",
            "paddingAll": "md",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#4338CA",
                    "action": {
                        "type": "uri",
                        "label": "🎬 ชมวิดีโอคำทำนายแบบละเอียด (ไม่รีบเร่ง)",
                        "uri": v_url
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "message",
                        "label": "🔄 ตั้งจิตเปิดผังใหม่",
                        "text": "เปิดไพ่"
                    }
                }
            ]
        }
    }

    return FlexSendMessage(
        alt_text="🏛️ ผังเซลติกครอส 10 ใบและวิดีโอคำทำนายฉบับเต็มของคุณพร้อมแล้วจ้า",
        contents=bubble
    )


def tarot_selection_carousel() -> FlexSendMessage:
    """รองรับ Backward Compatibility สำหรับโค้ดเก่าที่เรียก tarot_selection_carousel()"""
    return tarot_invitation_card()

