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
# 🔮 ไพ่ยิปซีแท้ Major Arcana 22 ใบ (Rider-Waite 1909 Public Domain HD)
# ==============================================================================
TAROT_CDN_BASE = "https://cdn.jsdelivr.net/gh/lalesleon13-hash/Tarot@main/"
TAROT_MAJOR_ARCANA_DICT = [
    {
        "id": 0, "name": "The Fool", "thai": "คนพเนจร",
        "keyword": "การเริ่มต้นใหม่ • อิสรภาพ • ก้าวสู่สิ่งที่ไม่รู้",
        "desc": "สื่อถึงการเริ่มต้นใหม่ ความเสี่ยง การเดินทาง หรือการทำอะไรด้วยสัญชาตญาณบริสุทธิ์โดยไม่ลังเล",
        "img": TAROT_CDN_BASE + "RWS_Tarot_00_Fool.jpg",
        "color": "#0284C7", "lucky": "กระเป๋า"
    },
    {
        "id": 1, "name": "The Magician", "thai": "จอมเวท",
        "keyword": "พรสวรรค์ • ทักษะโดดเด่น • ความเชี่ยวชาญ",
        "desc": "สื่อถึงพรสวรรค์ ทักษะความสามารถที่โดดเด่น มีเครื่องมือพร้อมสร้างความสำเร็จได้ด้วยตัวเอง",
        "img": TAROT_CDN_BASE + "RWS_Tarot_01_Magician.jpg",
        "color": "#7C3AED", "lucky": "ปากกา"
    },
    {
        "id": 2, "name": "The High Priestess", "thai": "นักบวชหญิง",
        "keyword": "ซิกซ์เซนส์ • ความลึกลับ • ลางสังหรณ์",
        "desc": "สื่อถึงซิกซ์เซนส์ เรื่องเหนือธรรมชาติ ความลึกลับ หรือสิ่งที่ซ่อนเร้น จงเชื่อในสัญชาตญาณตัวเอง",
        "img": TAROT_CDN_BASE + "RWS_Tarot_02_High_Priestess.jpg",
        "color": "#4F46E5", "lucky": "หินมงคล"
    },
    {
        "id": 3, "name": "The Empress", "thai": "จักรพรรดินี",
        "keyword": "ความเป็นแม่ • อุดมสมบูรณ์ • ความอบอุ่น",
        "desc": "สื่อถึงความเป็นแม่ การตั้งครรภ์ ความอุดมสมบูรณ์ และการเติบโตงอกงามของสิ่งดีๆ ในชีวิต",
        "img": TAROT_CDN_BASE + "RWS_Tarot_03_Empress.jpg",
        "color": "#DB2777", "lucky": "สร้อยคอ"
    },
    {
        "id": 4, "name": "The Emperor", "thai": "จักรพรรดิ",
        "keyword": "อำนาจ • ความมั่นคง • ภาวะผู้นำ",
        "desc": "สื่อถึงการมีอำนาจ ความมั่นคง การปกครอง การควบคุมสถานการณ์ และระเบียบวินัยที่เข้มแข็ง",
        "img": TAROT_CDN_BASE + "RWS_Tarot_04_Emperor.jpg",
        "color": "#DC2626", "lucky": "นาฬิกา"
    },
    {
        "id": 5, "name": "The Hierophant", "thai": "สังฆราช",
        "keyword": "คุณธรรม • ผู้ให้คำปรึกษา • ความถูกต้อง",
        "desc": "สื่อถึงความเชื่อ ศาสนา ครู อาจารย์ ผู้ใหญ่ที่เคารพ หรือการตัดสินใจบนหลักคุณธรรมและเหตุผล",
        "img": TAROT_CDN_BASE + "RWS_Tarot_05_Hierophant.jpg",
        "color": "#D97706", "lucky": "พระเครื่อง"
    },
    {
        "id": 6, "name": "The Lovers", "thai": "คู่รัก",
        "keyword": "ความโรแมนติก • พรหมลิขิต • การอยู่ร่วมกัน",
        "desc": "สื่อถึงความโรแมนติก พรหมลิขิต ความรักมั่นคง การอยู่ร่วมกัน หรือการตัดสินใจเลือกทางเดินสำคัญ",
        "img": TAROT_CDN_BASE + "RWS_Tarot_06_Lovers.jpg",
        "color": "#E11D48", "lucky": "แหวน"
    },
    {
        "id": 7, "name": "The Chariot", "thai": "นักรบรถศึก",
        "keyword": "ความก้าวหน้า • การเดินทาง • ชัยชนะ",
        "desc": "สื่อถึงความก้าวหน้า การเดินทาง ยานพาหนะ และชัยชนะที่เกิดจากความมุ่งมั่นควบคุมอย่างเด็ดขาด",
        "img": TAROT_CDN_BASE + "RWS_Tarot_07_Chariot.jpg",
        "color": "#2563EB", "lucky": "อุปกรณ์รถยนต์"
    },
    {
        "id": 8, "name": "Strength", "thai": "ความแข็งแกร่ง",
        "keyword": "พลังภายใน • ความอดทน • ชนะใจผู้อื่น",
        "desc": "สื่อถึงความแข็งแกร่ง การอดทนควบคุมอารมณ์ และการเอาชนะปัญหาหรือชนะใจผู้อื่นด้วยความอ่อนโยน",
        "img": TAROT_CDN_BASE + "RWS_Tarot_08_Strength.jpg",
        "color": "#EA580C", "lucky": "กำไล"
    },
    {
        "id": 9, "name": "The Hermit", "thai": "ฤๅษี",
        "keyword": "ความสันโดษ • ทบทวนตัวเอง • ผู้แสวงหา",
        "desc": "สื่อถึงความสันโดษ ความสงบ การอยู่ลำพังเพื่อค้นหาคำตอบในจิตใจ หรือการเป็นผู้เชี่ยวชาญเฉพาะทาง",
        "img": TAROT_CDN_BASE + "RWS_Tarot_09_Hermit.jpg",
        "color": "#475569", "lucky": "โคมไฟ"
    },
    {
        "id": 10, "name": "Wheel of Fortune", "thai": "กงล้อโชคชะตา",
        "keyword": "โชคชะตา • จุดพลิกผัน • การเปลี่ยนแปลง",
        "desc": "สื่อถึงโชคชะตา การเปลี่ยนแปลง และจุดพลิกผันของเหตุการณ์ เรื่องที่ติดขัดกำลังจะหมุนสู่ทิศทางที่ดี",
        "img": TAROT_CDN_BASE + "RWS_Tarot_10_Wheel_of_Fortune.jpg",
        "color": "#9333EA", "lucky": "พวงกุญแจ"
    },
    {
        "id": 11, "name": "Justice", "thai": "ความยุติธรรม",
        "keyword": "ความเป็นธรรม • ความถูกต้อง • ความสมดุล",
        "desc": "สื่อถึงความเป็นธรรม ศาล กฎหมาย สัญญา ความยุติธรรม และผลลัพธ์ที่เป็นไปตามเหตุและผล",
        "img": TAROT_CDN_BASE + "RWS_Tarot_11_Justice.jpg",
        "color": "#0891B2", "lucky": "สมุดโน้ต"
    },
    {
        "id": 12, "name": "The Hanged Man", "thai": "คนห้อยหัว",
        "keyword": "การรอคอย • การเสียสละ • มองมุมกลับ",
        "desc": "สื่อถึงการรอคอย สถานการณ์หยุดชะงักชั่วคราว การยอมเสียสละ หรือต้องเปลี่ยนมุมมองชีวิตใหม่",
        "img": TAROT_CDN_BASE + "RWS_Tarot_12_Hanged_Man.jpg",
        "color": "#0D9488", "lucky": "หมอน"
    },
    {
        "id": 13, "name": "Death", "thai": "การสิ้นสุด",
        "keyword": "การสิ้นสุด • จบสิ่งเก่า • เริ่มต้นใหม่",
        "desc": "สื่อถึงการสิ้นสุดของสิ่งเดิมเพื่อเริ่มต้นสิ่งใหม่ที่ดีกว่า หรือการพ้นจากเรื่องเลวร้ายในอดีต",
        "img": TAROT_CDN_BASE + "RWS_Tarot_13_Death.jpg",
        "color": "#1E293B", "lucky": "กระจก"
    },
    {
        "id": 14, "name": "Temperance", "thai": "ความสมดุล",
        "keyword": "ความสมดุล • การยั้งคิด • การปรับเปลี่ยน",
        "desc": "สื่อถึงความสมดุล การยั้งคิด การผสมผสาน และการสลับปรับเปลี่ยนอย่างเท่าเทียมและลงตัว",
        "img": TAROT_CDN_BASE + "RWS_Tarot_14_Temperance.jpg",
        "color": "#059669", "lucky": "แก้วน้ำ"
    },
    {
        "id": 15, "name": "The Devil", "thai": "ปีศาจ",
        "keyword": "กิเลสตัณหา • การยึดติด • พันธนาการ",
        "desc": "สื่อถึงกิเลสตัณหา ราคะ รสนิยม หรือการติดอยู่ในด้านมืดของจิตใจที่คุณสามารถปลดปล่อยตัวเองได้",
        "img": TAROT_CDN_BASE + "RWS_Tarot_15_Devil.jpg",
        "color": "#991B1B", "lucky": "น้ำหอม"
    },
    {
        "id": 16, "name": "The Tower", "thai": "หอคอยถล่ม",
        "keyword": "ความโกลาหล • สิ่งที่พังทลาย • ความไม่แน่นอน",
        "desc": "สื่อถึงความโกลาหล สิ่งที่คาดหวังไว้พังทลายกะทันหัน หรือการตื่นรู้เพื่อสร้างรากฐานใหม่ที่มั่นคงกว่าเดิม",
        "img": TAROT_CDN_BASE + "RWS_Tarot_16_Tower.jpg",
        "color": "#B91C1C", "lucky": "เคสโทรศัพท์"
    },
    {
        "id": 17, "name": "The Star", "thai": "ดวงดาว",
        "keyword": "ความหวัง • ความสงบ • สมปรารถนา",
        "desc": "สื่อถึงความหวัง การมองโลกในแง่ดี ความสงบทางใจ และการเดินทางสู่สิ่งที่ปรารถนาอย่างแท้จริง",
        "img": TAROT_CDN_BASE + "RWS_Tarot_17_Star.jpg",
        "color": "#0284C7", "lucky": "โคมไฟดวงดาว"
    },
    {
        "id": 18, "name": "The Moon", "thai": "พระจันทร์",
        "keyword": "ความกังวล • ความเหงา • ภาพลวงตา",
        "desc": "สื่อถึงความกังวลใจ ความเหงา เศร้าสร้อย หรืออาจพบเจอกับการหลอกลวง จงมีสติอย่าเพิ่งด่วนตัดสินใจ",
        "img": TAROT_CDN_BASE + "RWS_Tarot_18_Moon.jpg",
        "color": "#334155", "lucky": "เทียนหอม"
    },
    {
        "id": 19, "name": "The Sun", "thai": "พระอาทิตย์",
        "keyword": "ความสำเร็จ • ความสุข • ชัยชนะรุ่งโรจน์",
        "desc": "สื่อถึงความสำเร็จสูงสุด ความสุขสดใส โชคลาภ หรือโอกาสได้บุตรและข่าวดีในเร็ววัน",
        "img": TAROT_CDN_BASE + "RWS_Tarot_19_Sun.jpg",
        "color": "#D97706", "lucky": "แว่นตากันแดด"
    },
    {
        "id": 20, "name": "Judgement", "thai": "การพิพากษา",
        "keyword": "โอกาสครั้งใหม่ • การตื่นรู้ • ก้าวสู่สิ่งใหม่",
        "desc": "สื่อถึงโอกาสครั้งใหม่ การเปลี่ยนแปลงเพื่อเริ่มทำสิ่งใหม่ ละทิ้งสิ่งเก่า และรับผลดีจากการกระทำที่ผ่านมา",
        "img": TAROT_CDN_BASE + "RWS_Tarot_20_Judgement.jpg",
        "color": "#6D28D9", "lucky": "นาฬิกาปลุก"
    },
    {
        "id": 21, "name": "The World", "thai": "โลก",
        "keyword": "ความสมบูรณ์แบบ • สำเร็จเกินคาด • ชัยชนะสมบูรณ์",
        "desc": "สื่อถึงความสมบูรณ์แบบ ความสำเร็จที่เกินคาด การสิ้นสุดวงจรเดิมอย่างงดงาม และชัยชนะในทุกด้าน",
        "img": TAROT_CDN_BASE + "RWS_Tarot_21_World.jpg",
        "color": "#059669", "lucky": "กระเป๋าเดินทาง"
    },
]

TAROT_BACK_IMG = "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop"


def tarot_selection_carousel() -> FlexSendMessage:
    """สร้างการ์ด Carousel สำหรับเลือกไพ่ยิปซี 3 กอง (สัดส่วน 2:3 ทรงไพ่จริง)"""
    import random
    selected = random.sample(TAROT_MAJOR_ARCANA_DICT, 3)
    bubbles = []
    for idx, c in enumerate(selected):
        pile_num = idx + 1
        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": c["color"],
                "paddingAll": "md",
                "contents": [
                    {"type": "text", "text": f"🃏 ไพ่ยิปซี กองที่ {pile_num}", "weight": "bold", "size": "md", "color": "#FFFFFF"},
                    {"type": "text", "text": "ตั้งจิตสงบ นึกถึงเรื่องที่อยากรู้", "size": "xxs", "color": "#F1F5F9"}
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
                "spacing": "xs",
                "paddingAll": "md",
                "contents": [
                    {"type": "text", "text": f"✨ ไพ่ใบที่ {pile_num} แตะเปิดดูได้เลยจ้า", "weight": "bold", "size": "sm"},
                    {"type": "text", "text": "หยิบคำทำนายกำลังใจวันนี้ให้ตัวเอง 💖", "size": "xxs", "color": "#64748B"}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": c["color"],
                        "action": {
                            "type": "message",
                            "label": f"✨ แตะเปิดใบที่ {pile_num}",
                            "text": f"เปิดไพ่ใบที่ {c['id']}"
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)

    return FlexSendMessage(
        alt_text="✨ มาสุ่มเปิดไพ่ยิปซีรับพลังบวกและข้อคิดดีๆ วันนี้กันจ้า",
        contents={"type": "carousel", "contents": bubbles}
    )


def tarot_reading_card(card_id: int) -> FlexSendMessage:
    """สร้างการ์ดเฉลยคำทำนายไพ่ยิปซีใบใหญ่ ฟีลเป็นกันเอง ให้กำลังใจ ไม่ตึงเครียด"""
    card = next((c for c in TAROT_MAJOR_ARCANA_DICT if c["id"] == card_id), TAROT_MAJOR_ARCANA_DICT[19])
    theme_color = card.get("color", "#D97706")

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": theme_color,
            "paddingAll": "md",
            "contents": [
                {"type": "text", "text": f"✨ คำทำนายวันนี้: {card['name']} ({card['thai']})", "weight": "bold", "size": "md", "color": "#FFFFFF"},
                {"type": "text", "text": f"🌟 จุดเด่น: {card['keyword']}", "size": "xxs", "color": "#FEF3C7"}
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
                        "label": "🔄 สุ่มเปิดใบใหม่เล่นๆ ได้อีกนะ",
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

