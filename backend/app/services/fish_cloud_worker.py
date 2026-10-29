# -*- coding: utf-8 -*-
"""
backend/app/services/fish_cloud_worker.py — ระบบสายตรวจเฝ้าเพจปลาสลิดแดดเดียวป้าเข็มบน Render Cloud 24/7
แยกหน้าที่ชัดเจนจากสคริปต์ GAS (shopee_pakhem_bot.gs):
- GAS รับผิดชอบ: LINE OA Webhook, หน้าเว็บสั่งซื้อ Direct Checkout (fish.html), ตรวจสลิป AI, และ FB Messenger ด่านแรก (ทันที 1 วินาที)
- Render รับผิดชอบ (24/7 Cloud Background Loop):
  1. กวาดคอมเมนต์ใต้คลิปแอด/โพสต์ Facebook ทั้ง 2 เพจ (หากคอมที่บ้านปิดหรือเกิน 30 วินาทีแล้วยังไม่ตอบ Render ตอบเม้นต์ + ทักแชททันที)
  2. ปักหมุด First Comment + รูปเจลเย็นรับประกันความสด ใต้คลิปปลาสลิดใหม่ที่ยังไม่มีคอมเมนต์แรก
  3. ด่านสำรองตรวจแชท Inbox Facebook ที่ค้างเกิน 45 วินาที (กรณี Webhook ตกหล่น)
  4. รันสมองกล Hermes AI วิเคราะห์ยอดขายปลาสลิด (direct_orders) ทุก 6 ชั่วโมง
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
import httpx

logger = logging.getLogger("FishCloudWorker")
ICT = timezone(timedelta(hours=7))

WEB_STORE_URL = "https://watt29.github.io/pakhem-shop/fish.html"
MAIN_SHOP_URL = "https://watt29.github.io/pakhem-shop/"
LINE_OA_URL = "https://lin.ee/o9Kjp1N"
COLD_PACK_POSTER_URL = "https://usqhvujqmnxqrdoovvnp.supabase.co/storage/v1/object/public/slips/cold_pack_poster.png"

# In-memory cache on Render container (backed by real-time Facebook Graph API sub_comments check)
_REPLIED_CACHE: dict[str, dict] = {}


def _get_supabase_config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "https://usqhvujqmnxqrdoovvnp.supabase.co").strip()
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()
    return url, key


def _send_telegram_alert(text_msg: str) -> bool:
    bot_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "6734965582").strip()
    if not bot_token or not chat_id:
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text_msg,
                "disable_web_page_preview": True,
            },
            timeout=10.0,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"[FishCloudWorker] Telegram alert failed: {e}")
        return False


def _configured_fb_pages() -> list[dict]:
    pages = []
    p1_id = (os.getenv("FACEBOOK_PAGE_ID") or "1307380735783361").strip()
    p1_token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    if p1_id and p1_token:
        pages.append({"id": p1_id, "name": "ป้าเข็ม ขายของ (เพจ 1)", "token": p1_token})

    p2_id = (os.getenv("FACEBOOK_PAGE_2_ID") or "1323469404180656").strip()
    p2_token = (os.getenv("FACEBOOK_PAGE_2_ACCESS_TOKEN") or "").strip()
    if p2_id and p2_token:
        pages.append({"id": p2_id, "name": "ป้าเข็ม เพจ 2", "token": p2_token})
    return pages


def build_fish_first_comment() -> str:
    return (
        f"🛒 พิมพ์คำว่า \"สนใจ\" ตอบกลับใต้เม้นต์นี้ หรือกดลิงก์สั่งได้เลยค่ะ 👇\n"
        f"👉 {WEB_STORE_URL}\n"
        f"💬 แอด LINE สั่งด่วน: {LINE_OA_URL} (ID: @137gsref)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🐟 ปลาสลิดแดดเดียว สุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ (ไซส์จัมโบ้ 5–7 ตัว/กก. เค็มน้อย 3%):\n"
        f"• ชุดพอดีมื้อ 500 กรัม (3–4 ตัว): โอน 390.- ส่งฟรี! (ปลายทาง 410.-)\n"
        f"• ชุดขายดี 1 กิโลกรัม (5–7 ตัว): โอน 550.- ส่งฟรี! (ปลายทาง 570.-) ⭐\n"
        f"• ชุดตุนสุดคุ้ม 2 กิโลกรัม (10–14 ตัว): โอน 1,090.- (ส่งฟรีรถห้องเย็น!)\n\n"
        f"📦 เงื่อนไขการจัดส่งและการชำระเงิน\n"
        f"เพื่อรักษาคุณภาพและความสดใหม่ของปลาสลิด ทางร้านเลือกวิธีจัดส่งให้เหมาะสมกับระยะเวลาขนส่งในแต่ละพื้นที่ ดังนี้ค่ะ\n"
        f"🚚 แบบที่ 1: พื้นที่จัดส่งถึงภายใน 1–2 วัน (กรุงเทพฯ ปริมณฑล และจังหวัดที่จัดส่งถึงได้ภายใน 1–2 วัน)\n"
        f"• จัดส่งสินค้าแช่แข็ง พร้อมบรรจุภัณฑ์ฟอยล์เก็บอุณหภูมิ\n"
        f"• สามารถเลือกชำระเงินปลายทางได้ในพื้นที่ที่ผู้ให้บริการรองรับ\n"
        f"❄️ แบบที่ 2: พื้นที่จัดส่งใช้เวลา 3–4 วัน (จัดส่งด้วยรถควบคุมอุณหภูมิ / รถห้องเย็น)\n"
        f"• ขอสงวนสิทธิ์จัดส่งหลังจากได้รับชำระเงินเต็มจำนวนแล้ว (ไม่สามารถใช้บริการเก็บเงินปลายทางได้)\n"
        f"💚 ก่อนยืนยันคำสั่งซื้อ ทางร้านจะแจ้งวิธีจัดส่ง ระยะเวลาโดยประมาณ และยอดชำระให้ทราบอย่างชัดเจนค่ะ 🙏"
    )


def build_fish_guarantee_comment() -> str:
    return (
        "📦 เงื่อนไขการจัดส่งและการชำระเงิน\n\n"
        "เพื่อรักษาคุณภาพและความสดใหม่ของปลาสลิด ทางร้านเลือกวิธีจัดส่งให้เหมาะสมกับระยะเวลาขนส่งในแต่ละพื้นที่ ดังนี้ค่ะ\n\n"
        "🚚 แบบที่ 1: พื้นที่จัดส่งถึงภายใน 1–2 วัน\n"
        "สำหรับกรุงเทพฯ ปริมณฑล และจังหวัดที่สามารถจัดส่งถึงได้ภายใน 1–2 วัน\n"
        "• จัดส่งสินค้าแช่แข็ง พร้อมบรรจุภัณฑ์ฟอยล์เก็บอุณหภูมิ\n"
        "• สามารถเลือกชำระเงินปลายทางได้ในพื้นที่ที่ผู้ให้บริการรองรับ\n\n"
        "❄️ แบบที่ 2: พื้นที่จัดส่งใช้เวลา 3–4 วัน\n"
        "สำหรับจังหวัดที่ใช้ระยะเวลาขนส่งนานกว่า ทางร้านจะจัดส่งด้วยรถควบคุมอุณหภูมิ (รถห้องเย็น) เพื่อช่วยรักษาคุณภาพสินค้าให้เหมาะสมตลอดการขนส่ง\n"
        "• ขอสงวนสิทธิ์จัดส่งหลังจากได้รับชำระเงินเต็มจำนวนแล้ว\n"
        "• ไม่สามารถใช้บริการเก็บเงินปลายทางได้ เนื่องจากเป็นรูปแบบการจัดส่งเฉพาะสำหรับพื้นที่ดังกล่าว\n\n"
        "💚 ทางร้านให้ความสำคัญกับคุณภาพสินค้าและความมั่นใจของลูกค้าทุกออเดอร์ ก่อนยืนยันคำสั่งซื้อ ทางร้านจะแจ้งวิธีจัดส่ง ระยะเวลาโดยประมาณ และยอดชำระให้ทราบอย่างชัดเจนค่ะ\n"
        "ขอบคุณที่ไว้วางใจเลือกซื้อปลาสลิดจากทางร้านนะคะ 🙏"
    )


def _get_pending_slip_from_supabase(sender_id: str) -> dict | None:
    if not sender_id:
        return None
    sb_url, sb_key = _get_supabase_config()
    if not sb_url or not sb_key:
        return None
    try:
        headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
        r = httpx.get(
            f"{sb_url}/rest/v1/system_preferences",
            params={"key": f"eq.fb_slip_{sender_id}", "select": "value"},
            headers=headers,
            timeout=6.0,
        )
        if r.status_code == 200 and r.json():
            val = json.loads(r.json()[0].get("value") or "{}")
            if (time.time() - float(val.get("ts") or 0)) < 86400:
                return val
    except Exception:
        pass
    return None


def _clear_pending_slip_in_supabase(sender_id: str) -> None:
    if not sender_id:
        return
    sb_url, sb_key = _get_supabase_config()
    if not sb_url or not sb_key:
        return
    try:
        headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
        httpx.delete(
            f"{sb_url}/rest/v1/system_preferences",
            params={"key": f"eq.fb_slip_{sender_id}"},
            headers=headers,
            timeout=6.0,
        )
    except Exception:
        pass


def _save_comment_order_to_supabase(
    order_code: str,
    name: str,
    phone: str,
    address: str,
    pkg: str,
    price: float,
    payment_method: str = "เก็บเงินปลายทาง (COD) 💵",
    sender_id: str = "",
    extra_note: str = "",
) -> bool:
    sb_url, sb_key = _get_supabase_config()
    if not sb_url or not sb_key:
        return False
    try:
        headers = {
            "apikey": sb_key,
            "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        note_str = f"สั่งซื้อผ่าน Facebook (Render Cloud 24/7) [FB_ID:{sender_id}] {extra_note}".strip() if sender_id else f"สั่งซื้อผ่านคอมเมนต์ Facebook (Render Cloud 24/7) {extra_note}".strip()
        payload = {
            "order_code": order_code,
            "product_name": "ปลาสลิดแดดเดียว ไซส์จัมโบ้ 5-7 ตัว/กก. ป้าเข็ม คัดพิเศษ",
            "package_code": "500g" if "500" in pkg else ("2kg" if "2" in pkg else "1kg"),
            "package_name": pkg,
            "price": price,
            "customer_name": name,
            "phone": phone,
            "address": address,
            "payment_method": payment_method,
            "status": "PENDING",
            "note": note_str,
            "created_at": datetime.now(ICT).isoformat(),
        }
        r = httpx.post(
            f"{sb_url}/rest/v1/direct_orders",
            headers=headers,
            json=payload,
            timeout=8.0,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        logger.warning(f"[FishCloudWorker] supabase order save failed: {e}")
        return False


def _save_comment_lead_to_supabase(
    sender_id: str,
    sender_name: str,
    phone: str,
    message: str,
    post_id: str,
    comment_id: str,
    intent: str = "comment",
    private_replied: bool = False,
) -> bool:
    sb_url, sb_key = _get_supabase_config()
    if not sb_url or not sb_key:
        return False
    try:
        headers = {
            "apikey": sb_key,
            "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        payload = {
            "platform": "facebook_comment",
            "sender_id": sender_id or "",
            "sender_name": sender_name or "ลูกค้า Facebook",
            "phone": phone or "",
            "message": message or "",
            "post_id": post_id or "",
            "comment_id": comment_id or "",
            "intent": intent,
            "private_replied": bool(private_replied),
            "created_at": datetime.now(ICT).isoformat(),
        }
        r = httpx.post(
            f"{sb_url}/rest/v1/ad_leads",
            headers=headers,
            json=payload,
            timeout=8.0,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        logger.warning(f"[FishCloudWorker] supabase ad_leads save failed: {e}")
        return False


def generate_comment_reply(comment_text: str, commenter_name: str = "", sender_id: str = "") -> tuple[str, dict | None]:
    text = (comment_text or "").strip()
    lower_text = text.lower()
    clean_name = (commenter_name or "").strip()
    if clean_name.startswith("คุณ"):
        greeting = f"สวัสดีค่ะ{clean_name} 🙏💕"
    elif clean_name:
        greeting = f"สวัสดีค่ะคุณ {clean_name} 🙏💕"
    else:
        greeting = "สวัสดีค่ะคุณลูกค้า 🙏💕"

    phone_match = re.search(
        r"(?:0[689]\d{8}|0[689]\d{1}[-\s]?\d{3}[-\s]?\d{4}|0[689]\d{2}[-\s]?\d{3}[-\s]?\d{3})",
        text,
    )
    has_address = bool(
        re.search(
            r"(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|ถนน|ถ\.|ซอย|ซ\.|ม\.|หมู่ที่|หมู่|\b\d{5}\b)",
            text,
        )
    )
    if phone_match and not has_address and len(text) <= 25:
        phone = re.sub(r"[-\s]", "", phone_match.group(0))
        reply = (
            f"{greeting} ป้าเข็มได้รับเบอร์โทรผู้รับพัสดุ ({phone}) เรียบร้อยแล้วค่ะ 📦✨\n"
            f"👉 รบกวนพิมพ์ **'ชุดที่รับ + ชื่อและที่อยู่จัดส่ง'** ต่อในแชทนี้ได้เลยนะคะ (หรือถ้าไม่สะดวกพิมพ์ยาว **ถ่ายรูปหน้าซองจดหมาย/นามบัตรที่อยู่** ส่งมาในแชทนี้ได้เลยค่ะ เดี๋ยวป้าเข็มพิมพ์ใบปะหน้าจัดส่งให้ค่ะ 🙏🐟)"
        )
        return reply, None

    if phone_match and (has_address or len(text) > 25):
        phone = re.sub(r"[-\s]", "", phone_match.group(0))
        pending_slip = _get_pending_slip_from_supabase(sender_id)
        slip_amt = float((pending_slip or {}).get("amount") or 0.0)
        explicit_cod = any(k in lower_text for k in ["ปลายทาง", "เก็บเงินปลายทาง", "cod"])
        wants_cold_truck = any(k in lower_text for k in ["รถห้องเย็น", "รถเย็น", "ส่งรถเย็น", "ห้องเย็น", "490", "650"]) or (470 <= slip_amt <= 510) or (630 <= slip_amt <= 680)
        is_transfer = bool(pending_slip) or wants_cold_truck or (any(k in text for k in ["โอน", "สลิป", "พร้อมเพย์", "จ่ายแล้ว"]) and not explicit_cod)

        if "500" in text or "พอดีมื้อ" in text or "ทดลอง" in text or "490" in text or (350 <= slip_amt <= 510):
            if wants_cold_truck:
                pkg_name = "ชุดพอดีมื้อ 450-500 กรัม (ประมาณ 3-4 ตัว • ❄️ ส่งรถห้องเย็น)"
                price = 490.0
                is_transfer = True
            else:
                pkg_name = "ชุดพอดีมื้อ 450-500 กรัม (ประมาณ 3-4 ตัว • 🧊 แพ็กซองฟอยล์เก็บความเย็น)"
                price = 390.0 if is_transfer else 410.0
        elif "2" in text or "สองโล" in text or "2kg" in text or (slip_amt >= 1000):
            pkg_name = "ชุดครอบครัวใหญ่ ไซส์จัมโบ้ (1.8-2.0 กิโลกรัม / ประมาณ 10-14 ตัว • ❄️ ส่งฟรีรถห้องเย็น)"
            price = 1090.0
            is_transfer = True
        else:
            if wants_cold_truck:
                pkg_name = "ชุดขายดีอันดับ 1 ไซส์จัมโบ้ (900-1,000 กรัม / ประมาณ 5-7 ตัว • ❄️ ส่งรถห้องเย็น)"
                price = 650.0
                is_transfer = True
            else:
                pkg_name = "ชุดขายดีอันดับ 1 ไซส์จัมโบ้ (900-1,000 กรัม / ประมาณ 5-7 ตัว • 🧊 แพ็กซองฟอยล์เก็บความเย็น)"
                price = 550.0 if is_transfer else 570.0

        extra_note = ""
        if pending_slip:
            s_url = pending_slip.get("slip_url") or ""
            r_ok = pending_slip.get("receiver_ok", True)
            check_str = "รอแอดมินตรวจยอดเงินเข้า" if r_ok else "⚠️ รอแอดมินตรวจชื่อผู้รับและยอดเงิน"
            amt_tag = f"{slip_amt:,.0f}.-" if slip_amt > 0 else "แนบสลิปแล้ว"
            payment_method = f"โอนเงิน ({amt_tag} {check_str}) 🏦"
            extra_note = f"[SLIP:{s_url}]"
            _clear_pending_slip_in_supabase(sender_id)
        elif is_transfer:
            payment_method = "โอนเงินผ่านธนาคาร (รอแนบสลิป/ตรวจยอด) 🏦"
        else:
            payment_method = "เก็บเงินปลายทาง (COD) 💵"

        order_code = f"PKF-{datetime.now(ICT).strftime('%m%d%H%M%S')}"
        cust_label = commenter_name or f"ลูกค้าคอมเมนต์ FB ({phone[-4:]})"
        _save_comment_order_to_supabase(
            order_code,
            cust_label,
            phone,
            text,
            pkg_name,
            price,
            payment_method=payment_method,
            sender_id=sender_id,
            extra_note=extra_note,
        )

        reply = (
            f"{greeting} แอดมินน้องพิมรับออเดอร์ให้เรียบร้อยแล้วค่ะ ✨\n"
            f"🔖 รหัสคำสั่งซื้อ: {order_code}\n"
            f"📦 รายการ: {pkg_name}\n"
            f"💰 ยอดรวม: {price:,.0f} บาท ({payment_method})\n"
            f"🚚 เตรียมจัดส่งรอบสดใหม่ให้ถึงหน้าบ้านเลยนะคะ ขอบพระคุณมากค่ะ 🙏🐟"
        )
        return reply, {
            "order_code": order_code,
            "customer_name": cust_label,
            "phone": phone,
            "pkg_name": pkg_name,
            "price": price,
            "payment_method": payment_method,
            "address": text,
        }

    # ปุ่มแอดและปุ่ม Quick Reply ใน Messenger
    is_cod_intent = any(k in lower_text for k in ["สั่งแบบเก็บเงินปลายทาง", "เก็บเงินปลายทาง", "เก็บปลายทาง", "ปลายทาง", "cod"])
    has_1kg_unit = any(k in lower_text for k in ["รับชุดขายดี", "ชุดขายดี", "1 กก", "1กก", "1kg", "1 กิโล", "1กิโล", "หนึ่งกิโล", "โลนึง", "1 โล", "1โล", "5-7 ตัว", "5-7ตัว", "570"])
    has_500g_unit = any(k in lower_text for k in ["รับชุดพอดีมื้อ", "ชุดพอดีมื้อ", "500g", "500 กรัม", "500กรัม", "ครึ่งโล", "ครึ่งกิโล", "3-4 ตัว", "3-4ตัว", "410"])
    is_1kg_intent = has_1kg_unit or (
        not has_500g_unit and (lower_text in ("2", "ชุด2", "ชุด 2", "เอาชุด2", "เอา 2", "รับชุด 2") or any(k in lower_text for k in ["ชุด 2", "ชุด2"]))
    )
    is_500g_intent = has_500g_unit or (
        not has_1kg_unit and (lower_text in ("1", "ชุด1", "ชุด 1", "เอาชุด1", "เอา 1", "รับชุด 1") or any(k in lower_text for k in ["ชุด 1", "ชุด1"]))
    )

    if is_cod_intent and is_500g_intent and not is_1kg_intent:
        reply = (
            f"{greeting} รับชุดพอดีมื้อ 500 กรัม (ประมาณ 3-4 ตัว) เก็บเงินปลายทาง 410 บาท (รวมส่งด่วนแพ็กซองฟอยล์แล้ว) 🚚❄️\n\n"
            f"👉 พิมพ์แจ้ง 'ชื่อ - ที่อยู่ - เบอร์โทรผู้รับ' (หรือถ่ายรูปหน้าซองจดหมาย + เบอร์โทร ส่งมาในแชทนี้ได้เลยค่ะ ไม่ต้องพิมพ์ยาว) 😊"
        )
        return reply, None

    if is_cod_intent and is_1kg_intent and not is_500g_intent:
        reply = (
            f"{greeting} รับชุดขายดี 1 กิโลกรัม (ประมาณ 5-7 ตัว) เก็บเงินปลายทาง 570 บาท (รวมส่งด่วนแพ็กซองฟอยล์แล้ว) ⭐🚚❄️\n\n"
            f"👉 พิมพ์แจ้ง 'ชื่อ - ที่อยู่ - เบอร์โทรผู้รับ' (หรือถ่ายรูปหน้าซองจดหมาย + เบอร์โทร ส่งมาในแชทนี้ได้เลยค่ะ ไม่ต้องพิมพ์ยาว) 😊"
        )
        return reply, None

    if any(k in lower_text for k in ["กี่ตัว", "โลละกี่ตัว", "ตัวละ", "ราคาตัวละ", "ขายเป็นตัว", "แยกตัว", "ตัวใหญ่ไหม", "ตัวใหญ่มั้ย", "ไซส์ไหน", "ขนาดไหน"]):
        reply = (
            f"{greeting} ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดไซส์ใหญ่พิเศษ ประมาณ 5-7 ตัว/กก.ค่ะ 🐟✨ (เนื้อหนาฟู เค็มน้อย 3%)\n\n"
            f"• พิมพ์ 1 : ชุด 500 กรัม (3–4 ตัว) = โอน 390.- ส่งฟรี | ปลายทาง 410.-\n"
            f"• พิมพ์ 2 : ชุดขายดี 1 กก. (5–7 ตัว) = โอน 550.- ส่งฟรี | ปลายทาง 570.- ⭐\n"
            f"• พิมพ์ 3 : ชุดคุ้ม 2 กก. (10–14 ตัว) = โอน 1,090.- ส่งฟรีรถห้องเย็น!\n\n"
            f"👉 รับชุดไหน พิมพ์เลข 1, 2 หรือ 3 พร้อม 'ชื่อ - ที่อยู่ - เบอร์โทรผู้รับ' (หรือส่งรูปหน้าซองจดหมาย) ในแชทนี้ได้เลยนะคะ 😊"
        )
        return reply, None

    if is_500g_intent:
        reply = (
            f"{greeting} รับชุดพอดีมื้อ 500 กรัม (ประมาณ 3–4 ตัว) เลือกรูปแบบการจัดส่งได้ 2 แบบค่ะ 🐟✨\n"
            f"1️⃣ 🧊 ส่งด่วนแพ็กซองฟอยล์เก็บความเย็น:\n"
            f"   • โอนเงิน: 390 บาท (ส่งฟรี!)\n"
            f"   • เก็บเงินปลายทาง (COD): 410 บาท\n"
            f"2️⃣ ❄️ ส่งรถห้องเย็นควบคุมอุณหภูมิ (+100.-):\n"
            f"   • โอนเงิน: 490 บาท (ขนส่งรถเย็นไม่มีบริการเก็บปลายทางค่ะ)\n\n"
            f"🏦 บัญชีรับโอน: ธ.กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n"
            f"👉 รับแบบไหน พิมพ์แจ้ง 'ชื่อ - ที่อยู่ - เบอร์โทรผู้รับ' (หรือถ่ายรูปหน้าซองจดหมายส่งมาในแชทนี้ได้เลยค่ะ) 😊"
        )
        return reply, None

    if is_1kg_intent:
        reply = (
            f"{greeting} รับชุดขายดี 1 กิโลกรัม (ประมาณ 5–7 ตัว) เลือกรูปแบบการจัดส่งได้ 2 แบบค่ะ ⭐🐟\n"
            f"1️⃣ 🧊 ส่งด่วนแพ็กซองฟอยล์เก็บความเย็น:\n"
            f"   • โอนเงิน: 550 บาท (ส่งฟรี!)\n"
            f"   • เก็บเงินปลายทาง (COD): 570 บาท\n"
            f"2️⃣ ❄️ ส่งรถห้องเย็นควบคุมอุณหภูมิ (+100.-):\n"
            f"   • โอนเงิน: 650 บาท (ขนส่งรถเย็นไม่มีบริการเก็บปลายทางค่ะ)\n\n"
            f"🏦 บัญชีรับโอน: ธ.กรุงไทย 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n"
            f"👉 รับแบบไหน พิมพ์แจ้ง 'ชื่อ - ที่อยู่ - เบอร์โทรผู้รับ' (หรือถ่ายรูปหน้าซองจดหมายส่งมาในแชทนี้ได้เลยค่ะ) 😊"
        )
        return reply, None

    if lower_text in ("3", "ชุด3", "ชุด 3", "เอาชุด3", "เอา 3", "รับชุด 3") or any(k in lower_text for k in ["รับชุดตุน", "ชุดตุน", "ชุดครอบครัว", "2 กก", "2กก", "2kg", "2 กิโล", "2กิโล", "สองโล", "สองกิโล", "2 โล", "2โล", "ชุด 3", "ชุด3"]):
        reply = (
            f"{greeting} รับชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 10–14 ตัว) ยอดโอน 1,090 บาท ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิค่ะ ❄️🚚 (เนื่องจากขนส่งรถห้องเย็นไม่มีบริการเก็บเงินปลายทาง ชุด 2 กก. จึงรับเฉพาะโอนเงินค่ะ)\n\n"
            f"🏦 ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n\n"
            f"👉 โอนแล้วส่งรูปสลิป พร้อมแจ้ง 'ชื่อ - ที่อยู่ - เบอร์โทรผู้รับ' ในแชทนี้ได้เลยนะคะ 😊"
        )
        return reply, None

    if any(k in lower_text for k in ["เลขบัญชี", "ขอเลขบัญชี", "โอนเงิน", "เลขที่บัญชี", "บัญชีธนาคาร", "โอนจ่าย", "จ่ายเงิน", "พร้อมเพย์", "โอนส่งฟรี"]):
        reply = (
            f"{greeting} โอนเงินล่วงหน้า จัดส่งด่วนแพ็กซองฟอยล์เก็บความเย็น ฟรีทุกชุดค่ะ 🚚❄️\n\n"
            f"🏦 ธนาคารกรุงไทย (Krungthai)\n"
            f"• เลขที่บัญชี: 038-0-25363-1\n"
            f"• ชื่อบัญชี: นายจีรวัฒน์ พลอาจ\n\n"
            f"📦 ยอดโอนตามขนาดชุด (รวมส่งฟรีแล้ว):\n"
            f"• ชุดพอดีมื้อ 500 กรัม (3–4 ตัว) = 390 บาท\n"
            f"• ชุดขายดี 1 กิโลกรัม (5–7 ตัว) = 550 บาท ⭐\n"
            f"• ชุดตุนสุดคุ้ม 2 กิโลกรัม (10–14 ตัว) = 1,090 บาท (ส่งฟรีรถห้องเย็น!)\n\n"
            f"👉 โอนเรียบร้อยแล้ว ส่งรูปสลิป + แจ้ง 'ชื่อ - ที่อยู่ - เบอร์โทรผู้รับ' ในแชทนี้ได้เลยนะคะ ขอบพระคุณค่ะ 🙏😊"
        )
        return reply, None

    if is_cod_intent:
        reply = (
            f"{greeting} สั่งแบบเก็บเงินปลายทาง (COD) รับของหน้าบ้านก่อนจ่ายเงินได้เลยค่ะ 🚚❄️\n\n"
            f"• พิมพ์ 1 : ชุดพอดีมื้อ 500 กรัม (3–4 ตัว) = 410 บาท (รวมส่งแล้ว)\n"
            f"• พิมพ์ 2 : ชุดขายดี 1 กิโลกรัม (5–7 ตัว) = 570 บาท ⭐ (รวมส่งแล้ว)\n\n"
            f"👉 สั่งง่ายๆ: พิมพ์เลข 1 หรือ 2 พร้อม 'ชื่อ - ที่อยู่ - เบอร์โทรผู้รับ' (หรือถ่ายรูปหน้าซองจดหมาย + เบอร์โทร ส่งมาในแชทนี้ได้เลยนะคะ) 😊"
        )
        return reply, None

    if any(k in lower_text for k in ["เค็มไหม", "เค็มมั้ย", "เค็มป่าว", "รสชาติ", "เค็มมาก", "อร่อยไหม", "ส่วนประกอบ", "กันบูด"]):
        reply = (
            f"{greeting} ไม่เค็มจัดแน่นอนจ้า! ป้าเข็มใช้สูตรโบราณ เนื้อปลาสลิดสุพรรณแท้ 97% หมักเกลือสมุทรธรรมชาติเพียง 3% (ไร้สารกันบูด ไร้ฟอร์มาลีน 0%) เค็มน้อยกลมกล่อมกำลังดี เนื้อหนาฟู หอมมัน ทอดแล้วกรอบนอกนุ่มในค่ะ 🐟✨\n\n"
            f"🔥 โปรโมชั่นโอนเงินรวมส่งด่วนเก็บความเย็นฟรีทุกชุด:\n"
            f"• ชุด 450-500 กรัม (ประมาณ 3-4 ตัว) = 390.- ส่งฟรี! (COD 410.-)\n"
            f"• ชุดขายดี 900-1,000 กรัม (ประมาณ 5-7 ตัว) = 550.- ส่งฟรี! (COD 570.-)\n"
            f"• ชุดครอบครัว 1.8-2.0 กิโลกรัม (ประมาณ 10-14 ตัว) = 1,090.- ส่งฟรีรถเย็น! (รับเฉพาะโอนเงิน)\n\n"
            f"🛒 สั่งซื้อด่วนที่: {WEB_STORE_URL} หรือทักแชทเพจได้เลยจ้า 💕"
        )
        return reply, None

    if any(k in lower_text for k in [
        "ต่างจังหวัด", "ตจว", "เสียไหม", "เสียมั้ย", "เน่าไหม", "บูดไหม", "ละลาย",
        "แพ็กยังไง", "แพ็คยังไง", "เก็บความเย็น", "เจลเย็น", "เจลไอซ์", "ส่งไกล", "รถห้องเย็น", "รถเย็น",
        "ส่งยังไง", "ปลายทาง", "เก็บเงินปลายทาง", "cod", "ค่าส่ง", "ส่งฟรี", "กี่วัน",
    ]):
        reply = (
            f"{greeting}\n"
            f"📦 เงื่อนไขการจัดส่งและการชำระเงิน\n\n"
            f"เพื่อรักษาคุณภาพและความสดใหม่ของปลาสลิด ทางร้านเลือกวิธีจัดส่งให้เหมาะสมกับระยะเวลาขนส่งในแต่ละพื้นที่ ดังนี้ค่ะ\n\n"
            f"🚚 แบบที่ 1: พื้นที่จัดส่งถึงภายใน 1–2 วัน\n"
            f"สำหรับกรุงเทพฯ ปริมณฑล และจังหวัดที่สามารถจัดส่งถึงได้ภายใน 1–2 วัน\n"
            f"• จัดส่งสินค้าแช่แข็ง พร้อมบรรจุภัณฑ์ฟอยล์เก็บอุณหภูมิ\n"
            f"• สามารถเลือกชำระเงินปลายทางได้ในพื้นที่ที่ผู้ให้บริการรองรับ\n\n"
            f"❄️ แบบที่ 2: พื้นที่จัดส่งใช้เวลา 3–4 วัน\n"
            f"สำหรับจังหวัดที่ใช้ระยะเวลาขนส่งนานกว่า ทางร้านจะจัดส่งด้วยรถควบคุมอุณหภูมิ (รถห้องเย็น) เพื่อช่วยรักษาคุณภาพสินค้าให้เหมาะสมตลอดการขนส่ง\n"
            f"• ขอสงวนสิทธิ์จัดส่งหลังจากได้รับชำระเงินเต็มจำนวนแล้ว\n"
            f"• ไม่สามารถใช้บริการเก็บเงินปลายทางได้ เนื่องจากเป็นรูปแบบการจัดส่งเฉพาะสำหรับพื้นที่ดังกล่าว\n\n"
            f"💚 ทางร้านให้ความสำคัญกับคุณภาพสินค้าและความมั่นใจของลูกค้าทุกออเดอร์ ก่อนยืนยันคำสั่งซื้อ ทางร้านจะแจ้งวิธีจัดส่ง ระยะเวลาโดยประมาณ และยอดชำระให้ทราบอย่างชัดเจนค่ะ\n"
            f"ขอบคุณที่ไว้วางใจเลือกซื้อปลาสลิดจากทางร้านนะคะ 🙏\n\n"
            f"• 📦 ชุดพอดีมื้อ 500 กรัม (3–4 ตัว) = โอน 390.- ส่งฟรี! (ปลายทาง 410.-)\n"
            f"• 🏆 ชุดขายดี 1 กิโลกรัม (5–7 ตัว) = โอน 550.- ส่งฟรี! (ปลายทาง 570.-)\n"
            f"• ❄️ ชุดครอบครัว 2 กิโลกรัม (10–14 ตัว) = โอน 1,090.- ส่งฟรีรถห้องเย็น!\n"
            f"🛒 กดสั่งซื้อที่: {WEB_STORE_URL} หรือทักแชทแจ้งชื่อ-ที่อยู่-เบอร์โทรได้เลยจ้า 💕"
        )
        return reply, None

    reply = (
        f"{greeting} ขอบพระคุณที่สนใจ ปลาสลิดแดดเดียว สุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ (ไซส์จัมโบ้ 5–7 ตัว/กก. เนื้อล้วนหนาฟู เค็มน้อยกลมกล่อม) นะคะ 🐟✨\n\n"
        f"🔥 โปรโมชั่นพิเศษ:\n"
        f"• 📦 ชุดพอดีมื้อ 500 กรัม (ประมาณ 3–4 ตัว) = โอน 390.- ส่งฟรี! (ปลายทาง 410.-)\n"
        f"• 🏆 ชุดขายดี 1 กิโลกรัม (ประมาณ 5–7 ตัว) = โอน 550.- ส่งฟรี! (ปลายทาง 570.-)\n"
        f"• ❄️ ชุดครอบครัว 2 กิโลกรัม (ประมาณ 10–14 ตัว) = โอน 1,090.- ส่งฟรีรถห้องเย็น!\n\n"
        f"📦 เงื่อนไขการจัดส่งและการชำระเงิน:\n"
        f"🚚 แบบที่ 1 (พื้นที่ถึงภายใน 1–2 วัน): จัดส่งสินค้าแช่แข็ง พร้อมบรรจุภัณฑ์ฟอยล์เก็บอุณหภูมิ (เลือกชำระเงินปลายทางได้)\n"
        f"❄️ แบบที่ 2 (พื้นที่ใช้เวลา 3–4 วัน): จัดส่งด้วยรถควบคุมอุณหภูมิ/รถห้องเย็น (จัดส่งหลังชำระเงินเต็มจำนวน งดเก็บเงินปลายทางค่ะ)\n"
        f"💚 ก่อนยืนยันคำสั่งซื้อ ทางร้านจะแจ้งวิธีจัดส่ง ระยะเวลาโดยประมาณ และยอดชำระให้ทราบอย่างชัดเจนค่ะ\n\n"
        f"🛒 กดสั่งซื้อผ่านหน้าเว็บได้ตลอด 24 ชม.: {WEB_STORE_URL}\n"
        f"💬 หรือทักแชทเพจ / พิมพ์ชุดที่รับพร้อม ชื่อ-ที่อยู่-เบอร์โทร ให้แอดมินรับออเดอร์ได้เลยจ้า 💕"
    )
    return reply, None


def generate_private_offer_message(comment_text: str, commenter_name: str = "") -> str:
    clean_name = (commenter_name or "").strip()
    greeting = f"สวัสดีค่ะคุณ {clean_name} 🙏💕" if clean_name else "สวัสดีค่ะคุณลูกค้า 🙏💕"
    return (
        f"{greeting} ป้าเข็มทักมาจากคอมเมนต์ \"{comment_text}\" นะคะ ขอบพระคุณมากๆ เลยจ้า 🐟💖\n\n"
        f"🔥 ป้าเข็มขออนุญาตแนะนำโปรโมชั่นพิเศษ ปลาสลิดแดดเดียวสุพรรณแท้ ไซส์จัมโบ้ 5-7 ตัว/กก. (เค็มน้อย 3% เนื้อหนาฟู ไร้กลิ่นโคลน):\n"
        f"1️⃣ ชุดพอดีมื้อ 450-450-500 กรัม (ประมาณ 3-4 ตัว): โอนเงิน 390.- ส่งฟรี! (เก็บปลายทาง COD 410.-)\n"
        f"2️⃣ ชุดยอดฮิตขายดี 900-1,000 กรัม (ประมาณ 5-7 ตัว): โอนเงิน 550.- ส่งฟรี! (เก็บปลายทาง COD 570.-)\n"
        f"3️⃣ ชุดตุนสุดคุ้ม 1.8-2.0 กิโลกรัม (ประมาณ 10-14 ตัว): โอนเงิน 1,090.- ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิ! (ชุด 2 โลรับเฉพาะโอนเงินค่ะ)\n\n"
        f"💬 คุณลูกค้าสนใจรับชุดไหน พิมพ์เลขชุด (เช่น 500g / 1 โล / 2 โล) พร้อม ชื่อ-ที่อยู่-เบอร์โทร ตอบกลับในแชทนี้ได้เลยนะคะ หรือกดสั่งที่หน้าเว็บ: {WEB_STORE_URL} ได้เลยจ้า 🙏✨"
    )


def _reply_to_fb_comment(
    comment_id: str,
    message: str,
    token: str,
    page_id: str = "",
    private_message: str = "",
) -> dict:
    try:
        httpx.post(
            f"https://graph.facebook.com/v21.0/{comment_id}/likes",
            params={"access_token": token},
            timeout=8.0,
        )
    except Exception:
        pass

    public_ok = False
    public_data = {}
    public_error = ""
    try:
        r = httpx.post(
            f"https://graph.facebook.com/v21.0/{comment_id}/comments",
            params={"access_token": token},
            data={"message": message},
            timeout=15.0,
        )
        if r.status_code == 200:
            public_ok = True
            public_data = r.json()
        else:
            public_error = f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        public_error = str(e)

    private_ok = False
    private_error = ""
    if page_id and private_message:
        try:
            pr = httpx.post(
                f"https://graph.facebook.com/v21.0/{page_id}/messages",
                params={"access_token": token},
                json={
                    "recipient": {"comment_id": comment_id},
                    "message": {"text": private_message},
                },
                timeout=15.0,
            )
            if pr.status_code == 200:
                private_ok = True
            else:
                private_error = f"HTTP {pr.status_code}: {pr.text[:200]}"
        except Exception as e:
            private_error = str(e)

    return {
        "ok": public_ok,
        "data": public_data,
        "error": public_error,
        "private_reply_ok": private_ok,
        "private_reply_error": private_error,
    }


def run_fish_cloud_scan_cycle(limit_posts: int = 10) -> dict:
    """
    รัน 1 รอบบน Render Cloud:
    - ตรวจคลิป/โพสต์ปลาสลิดที่อายุเกิน 45 วินาทีแต่ยังไม่มี First Comment -> ปักหมุดให้ทันที
    - ตรวจคอมเมนต์ลูกค้าที่อายุเกิน 30 วินาทีแต่ยังไม่มีคำตอบจากเพจ -> ตอบกลับ + ทักแชท Inbox ทันที
    - ตรวจแชท Inbox ที่อายุเกิน 45 วินาทีแต่ GAS Webhook ยังไม่ได้ตอบ -> ตอบกลับแทนทันที
    """
    pages = _configured_fb_pages()
    if not pages:
        return {"ok": False, "reason": "no_fb_pages_configured"}

    replied_comments = 0
    first_comments = 0
    inbox_replied = 0

    for page in pages:
        page_id = page["id"]
        page_name = page["name"]
        token = page["token"]

        items_to_scan = []
        seen_ids = set()
        for endpoint, msg_field in [
            ("video_reels", "description"),
            ("videos", "description"),
            ("published_posts", "message"),
        ]:
            try:
                r = httpx.get(
                    f"https://graph.facebook.com/v21.0/{page_id}/{endpoint}",
                    params={
                        "access_token": token,
                        "limit": limit_posts,
                        "fields": f"id,{msg_field},created_time,comments.limit(40){{id,from,message,attachment,created_time,comments.limit(15){{id,from,message}}}}",
                    },
                    timeout=15.0,
                )
                if r.status_code == 200:
                    for obj in r.json().get("data", []):
                        oid = obj.get("id", "")
                        if oid and oid not in seen_ids:
                            seen_ids.add(oid)
                            items_to_scan.append({
                                "id": oid,
                                "created_time": obj.get("created_time") or "",
                                "message": obj.get(msg_field) or "",
                                "comments": (obj.get("comments") or {}).get("data", []),
                            })
            except Exception as e:
                logger.warning(f"[FishCloudWorker] fetch {endpoint} failed ({page_name}): {e}")

        pinned_sigs = set()
        for post in items_to_scan:
            sig = f"{page_id}:{(post.get('message') or '')[:80].strip()}"
            pid = post.get("id", "")
            if f"fc_{pid}" in _REPLIED_CACHE:
                pinned_sigs.add(sig)
                continue
            for c in post.get("comments", []):
                ct = c.get("message") or ""
                c_from = str((c.get("from") or {}).get("id") or "")
                if "watt29.github.io/pakhem-shop" in ct or (c_from == page_id and "390.-" in ct):
                    pinned_sigs.add(sig)
                    _REPLIED_CACHE[f"fc_{pid}"] = {"exists": True}
                    break

        for post in items_to_scan:
            post_id = post.get("id", "")
            post_msg = post.get("message", "")
            comments_data = post.get("comments", [])
            sig = f"{page_id}:{post_msg[:80].strip()}"

            # 1) ปักหมุด First Comment + รูปเจลเย็น หากโพสต์อายุเกิน 45 วินาทีแล้วยังไม่มี
            is_fish_post = any(k in post_msg for k in ("ปลาสลิด", "ปลาแดดเดียว", "fish.html"))
            if is_fish_post and f"fc_{post_id}" not in _REPLIED_CACHE and sig not in pinned_sigs:
                post_age_ok = True
                try:
                    dt_p = datetime.strptime(post.get("created_time") or "", "%Y-%m-%dT%H:%M:%S%z")
                    if (datetime.now(timezone.utc) - dt_p).total_seconds() < 45:
                        post_age_ok = False
                except Exception:
                    pass
                if post_age_ok:
                    try:
                        fc_res = httpx.post(
                            f"https://graph.facebook.com/v21.0/{post_id}/comments",
                            data={"message": build_fish_first_comment(), "access_token": token},
                            timeout=15.0,
                        )
                        if fc_res.status_code == 200:
                            httpx.post(
                                f"https://graph.facebook.com/v21.0/{post_id}/comments",
                                data={
                                    "message": build_fish_guarantee_comment(),
                                    "attachment_url": COLD_PACK_POSTER_URL,
                                    "access_token": token,
                                },
                                timeout=20.0,
                            )
                            _REPLIED_CACHE[f"fc_{post_id}"] = {"posted": True}
                            pinned_sigs.add(sig)
                            first_comments += 1
                            logger.info(f"📌 [RenderCloud] ปักหมุดเม้นต์แรกใต้คลิป {post_id} สำเร็จ")
                    except Exception as e:
                        logger.warning(f"[FishCloudWorker] first comment error ({post_id}): {e}")

            # 2) ตอบคอมเมนต์ลูกค้าที่อายุเกิน 30 วินาทีและยังไม่มีคำตอบจากเพจ
            for c in comments_data:
                cid = c.get("id", "")
                c_msg = (c.get("message") or "").strip()
                has_att = bool(c.get("attachment"))
                c_from = c.get("from") or {}
                from_id = str(c_from.get("id") or "")
                from_name = (c_from.get("name") or "").strip()
                created_str = c.get("created_time") or ""

                if not cid or (not c_msg and not has_att):
                    continue
                if not c_msg and has_att:
                    c_msg = "[ส่งสติกเกอร์/รูปภาพสนใจสินค้า]"

                if (
                    from_id == page_id
                    or "ป้าเข็ม" in from_name
                    or "มาตรฐานการแพ็กส่งด่วน" in c_msg
                    or "มั่นใจความสด 100%" in c_msg
                    or "watt29.github.io/pakhem-shop" in c_msg
                ):
                    _REPLIED_CACHE[cid] = {"own": True}
                    continue

                if cid in _REPLIED_CACHE:
                    continue

                # รอ 30 วินาทีให้คอมที่บ้าน (ถ้าเปิดอยู่) ตอบก่อน เพื่อไม่ให้ชนกัน
                try:
                    dt_c = datetime.strptime(created_str, "%Y-%m-%dT%H:%M:%S%z")
                    if (datetime.now(timezone.utc) - dt_c).total_seconds() < 30:
                        continue
                except Exception:
                    pass

                sub_comments = (c.get("comments") or {}).get("data", [])
                already_replied = False
                for sub in sub_comments:
                    sub_from = sub.get("from") or {}
                    sub_msg = sub.get("message") or ""
                    if (
                        str(sub_from.get("id") or "") == page_id
                        or "ป้าเข็ม" in (sub_from.get("name") or "")
                        or "watt29.github.io/pakhem-shop" in sub_msg
                    ):
                        already_replied = True
                        break
                if already_replied:
                    _REPLIED_CACHE[cid] = {"replied_on_fb": True}
                    continue

                reply_text, order_info = generate_comment_reply(c_msg, from_name, sender_id=from_id)
                priv_text = generate_private_offer_message(c_msg, from_name)
                res = _reply_to_fb_comment(cid, reply_text, token, page_id, priv_text)
                if res.get("ok"):
                    _REPLIED_CACHE[cid] = {"replied": True}
                    replied_comments += 1
                    priv_ok = bool(res.get("private_reply_ok"))
                    _save_comment_lead_to_supabase(
                        sender_id=from_id,
                        sender_name=from_name,
                        phone=(order_info or {}).get("phone", ""),
                        message=c_msg,
                        post_id=post_id,
                        comment_id=cid,
                        intent="order" if order_info else "comment",
                        private_replied=priv_ok,
                    )
                    now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")
                    _send_telegram_alert(
                        f"☁️💬 [Render Cloud 24/7 ตอบคอมเมนต์ + ทักแชทลูกค้าสำเร็จ!] ✅\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🏠 เพจ: {page_name}\n"
                        f"👤 ลูกค้า: {from_name or 'ผู้ใช้งาน Facebook'}\n"
                        f"❓ คอมเมนต์: \"{c_msg}\"\n"
                        f"💌 ทัก Inbox: {'สำเร็จ ✅' if priv_ok else 'ตอบใต้โพสต์'}\n"
                        f"⏰ เวลา: {now_str} น."
                    )

        # 3) ด่านสำรองตรวจแชท Inbox Facebook ที่ค้างเกิน 45 วินาที (หลัง GAS Webhook)
        try:
            ir = httpx.get(
                f"https://graph.facebook.com/v21.0/{page_id}/conversations",
                params={
                    "access_token": token,
                    "limit": 8,
                    "fields": "id,updated_time,messages.limit(6){id,message,from,created_time}",
                },
                timeout=15.0,
            )
            if ir.status_code == 200:
                for t in ir.json().get("data", []):
                    msgs = (t.get("messages") or {}).get("data", [])
                    if not msgs:
                        continue
                    latest = None
                    for m_item in msgs:
                        cand_text = (m_item.get("message") or "").strip()
                        cand_from_id = str((m_item.get("from") or {}).get("id") or "")
                        if not cand_text:
                            if cand_from_id == page_id:
                                latest = m_item
                                break
                            continue
                        if cand_from_id == page_id and (
                            cand_text.endswith("ตอบกลับโฆษณา")
                            or "สนใจรับปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม ชุดไหนดีคะ" in cand_text
                            or 'ข้อความนี้ถูกย้ายไปยัง "สแปม"' in cand_text
                            or "Messenger automatically created" in cand_text
                            or "คุณกำลังตอบกลับความคิดเห็น" in cand_text
                        ):
                            continue
                        latest = m_item
                        break
                    if not latest:
                        continue
                    mid = str(latest.get("id") or "")
                    m_text = (latest.get("message") or "").strip()
                    m_from = latest.get("from") or {}
                    from_id = str(m_from.get("id") or "")
                    from_name = (m_from.get("name") or "").strip()
                    created_str = latest.get("created_time") or ""

                    if from_id == page_id or "ป้าเข็ม" in from_name:
                        continue
                    if not mid or not m_text or not from_id:
                        continue
                    if mid in _REPLIED_CACHE:
                        continue

                    try:
                        dt_m = datetime.strptime(created_str, "%Y-%m-%dT%H:%M:%S%z")
                        age_sec = (datetime.now(timezone.utc) - dt_m).total_seconds()
                        # รอ 45 วินาทีให้สคริปต์ GAS Webhook และคอมที่บ้านตอบก่อน
                        if age_sec < 45:
                            continue
                        if age_sec > 86400:
                            _REPLIED_CACHE[mid] = {"old": True}
                            continue
                    except Exception:
                        continue

                    reply_text, order_info = generate_comment_reply(m_text, from_name, sender_id=from_id)
                    qr_buttons = [
                        {"content_type": "text", "title": "รับชุด 500g (3-4ตัว)", "payload": "QR_PKG_500G"},
                        {"content_type": "text", "title": "รับชุด 1กก. (5-7ตัว)", "payload": "QR_PKG_1KG"},
                        {"content_type": "text", "title": "ปลายทาง 500g (410.-)", "payload": "QR_COD_500G"},
                        {"content_type": "text", "title": "ปลายทาง 1กก. (570.-)", "payload": "QR_COD_1KG"},
                    ]
                    tpl_buttons = [
                        {"type": "postback", "title": "📦 ปลายทาง 500g(410)", "payload": "QR_COD_500G"},
                        {"type": "postback", "title": "⭐ ปลายทาง 1กก.(570)", "payload": "QR_COD_1KG"},
                        {"type": "postback", "title": "🏦 โอนส่งฟรี (390/550)", "payload": "QR_BANK_INFO"},
                    ]
                    sr = None
                    if not order_info:
                        if len(reply_text) <= 600:
                            sr = httpx.post(
                                f"https://graph.facebook.com/v21.0/{page_id}/messages",
                                params={"access_token": token},
                                json={
                                    "recipient": {"id": from_id},
                                    "messaging_type": "RESPONSE",
                                    "message": {
                                        "attachment": {
                                            "type": "template",
                                            "payload": {
                                                "template_type": "button",
                                                "text": reply_text,
                                                "buttons": tpl_buttons,
                                            },
                                        },
                                        "quick_replies": qr_buttons,
                                    },
                                },
                                timeout=12.0,
                            )
                        else:
                            httpx.post(
                                f"https://graph.facebook.com/v21.0/{page_id}/messages",
                                params={"access_token": token},
                                json={
                                    "recipient": {"id": from_id},
                                    "messaging_type": "RESPONSE",
                                    "message": {"text": reply_text},
                                },
                                timeout=12.0,
                            )
                            sr = httpx.post(
                                f"https://graph.facebook.com/v21.0/{page_id}/messages",
                                params={"access_token": token},
                                json={
                                    "recipient": {"id": from_id},
                                    "messaging_type": "RESPONSE",
                                    "message": {
                                        "attachment": {
                                            "type": "template",
                                            "payload": {
                                                "template_type": "button",
                                                "text": "📦 เลือกชุดสั่งซื้อ (กดปุ่มในกล่องนี้ หรือพิมพ์เลข 1 หรือ 2 ได้เลยค่ะ):",
                                                "buttons": tpl_buttons,
                                            },
                                        },
                                        "quick_replies": qr_buttons,
                                    },
                                },
                                timeout=12.0,
                            )
                    if not sr or sr.status_code != 200:
                        sr = httpx.post(
                            f"https://graph.facebook.com/v21.0/{page_id}/messages",
                            params={"access_token": token},
                            json={
                                "recipient": {"id": from_id},
                                "messaging_type": "RESPONSE",
                                "message": {"text": reply_text, "quick_replies": qr_buttons},
                            },
                            timeout=12.0,
                        )
                    if sr.status_code != 200:
                        sr = httpx.post(
                            f"https://graph.facebook.com/v21.0/{page_id}/messages",
                            params={"access_token": token},
                            json={"recipient": {"id": from_id}, "message": {"text": reply_text}},
                            timeout=12.0,
                        )
                    if sr.status_code == 200:
                        _REPLIED_CACHE[mid] = {"replied": True}
                        inbox_replied += 1
                        _save_comment_lead_to_supabase(
                            sender_id=from_id,
                            sender_name=from_name,
                            phone=(order_info or {}).get("phone", ""),
                            message=m_text,
                            post_id=f"INBOX_{page_id}",
                            comment_id=mid,
                            intent="order" if order_info else "inbox",
                            private_replied=True,
                        )
                        now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")
                        _send_telegram_alert(
                            f"☁️💌 [Render Cloud 24/7 ตอบแชท Inbox สำรองเพจ {page_name}!] ✅\n"
                            f"👤 ลูกค้า: {from_name}\n"
                            f"💬 ข้อความ: \"{m_text}\"\n"
                            f"⏰ เวลา: {now_str} น."
                        )
        except Exception as e:
            logger.warning(f"[FishCloudWorker] inbox scan error ({page_name}): {e}")

    return {
        "ok": True,
        "replied_comments": replied_comments,
        "first_comments": first_comments,
        "inbox_replied": inbox_replied,
    }


async def fish_cloud_worker_loop(interval_seconds: int = 35):
    """ลูปสายตรวจเฝ้าเพจปลาสลิดแดดเดียวบน Render 24/7 (ทุก 35 วินาที)"""
    logger.info(f"🐟 [FishCloudWorker] เริ่มระบบสายตรวจเฝ้าเพจปลาสลิด 24/7 (ทุก {interval_seconds} วินาที)")
    while True:
        try:
            res = await asyncio.to_thread(run_fish_cloud_scan_cycle, 10)
            if res.get("replied_comments") or res.get("first_comments") or res.get("inbox_replied"):
                logger.info(f"🐟 [FishCloudWorker] cycle result: {res}")
        except Exception as e:
            logger.warning(f"[FishCloudWorker] loop error: {e}")
        await asyncio.sleep(interval_seconds)


async def fish_hermes_analytics_loop(interval_seconds: int = 21600):
    """ลูปสมองกล Hermes AI วิเคราะห์ยอดขายปลาสลิด (direct_orders) ทุก 6 ชั่วโมงบน Render"""
    logger.info("🧠 [FishCloudWorker] เริ่มระบบ Hermes AI วิเคราะห์ยอดขายปลาสลิดทุก 6 ชั่วโมง")
    while True:
        await asyncio.sleep(60)  # รอ 1 นาทีแรกหลังตื่นก่อนรันรอบแรก
        try:
            from app.db import SessionLocal
            from app.services.hermes_brain import run_hermes_cycle
            def _run():
                db = SessionLocal()
                try:
                    return run_hermes_cycle(db)
                finally:
                    db.close()
            res = await asyncio.to_thread(_run)
            logger.info(f"🧠 [FishCloudWorker] Hermes AI fish analytics completed: {res.get('fish_orders')}")
        except Exception as e:
            logger.warning(f"[FishCloudWorker] Hermes loop error: {e}")
        await asyncio.sleep(interval_seconds)


def run_fish_cloud_ads_guard_cycle() -> dict:
    """ตรวจเช็คงบโฆษณา Facebook Ads บน Render Cloud ทุก 4 ชั่วโมง:
    หากพบแคมเปญซ้ำซ้อน หรือแอดที่ใช้งบเกิน 150 บาทแต่ CPC แพงผิดปกติ (>15 บาท) สั่งพักแอดอัตโนมัติและแจ้ง Telegram"""
    ad_account = (os.getenv("FACEBOOK_AD_ACCOUNT_ID") or "act_294446695507241").strip()
    ads_token = (os.getenv("FACEBOOK_ADS_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    page_token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    if not ad_account or not ads_token:
        return {"ok": False, "reason": "no_ads_token"}
    try:
        r = httpx.get(
            f"https://graph.facebook.com/v21.0/{ad_account}/campaigns",
            params={
                "access_token": ads_token,
                "fields": "id,name,status,daily_budget,insights.date_preset(last_7d){spend,clicks,cpc,ctr}",
            },
            timeout=15.0,
        )
        if r.status_code != 200 and page_token and page_token != ads_token:
            ads_token = page_token
            r = httpx.get(
                f"https://graph.facebook.com/v21.0/{ad_account}/campaigns",
                params={
                    "access_token": ads_token,
                    "fields": "id,name,status,daily_budget,insights.date_preset(last_7d){spend,clicks,cpc,ctr}",
                },
                timeout=15.0,
            )
        if r.status_code != 200:
            return {"ok": False, "status_code": r.status_code}
        camps = (r.json() or {}).get("data", [])
        active = [c for c in camps if c.get("status") == "ACTIVE"]
        paused_actions = []
        seen_names = set()
        for c in active:
            cid = c.get("id")
            cname = (c.get("name") or "")[:40]
            ins = ((c.get("insights") or {}).get("data") or [{}])[0]
            spend = float(ins.get("spend") or 0.0)
            cpc = float(ins.get("cpc") or 0.0)
            reason = None
            if cname in seen_names:
                reason = "แคมเปญซ้ำซ้อน (Duplicate Active Campaign)"
            elif spend >= 150.0 and cpc > 15.0:
                reason = f"ใช้งบ {spend:.0f}฿ แต่ CPC แพงเกินเกณฑ์ ({cpc:.2f}฿/คลิก)"
            seen_names.add(cname)
            if reason and cid:
                pr = httpx.post(
                    f"https://graph.facebook.com/v21.0/{cid}",
                    params={"access_token": ads_token},
                    data={"status": "PAUSED"},
                    timeout=10.0,
                )
                if pr.status_code == 200:
                    paused_actions.append(f"• {cname} ({cid}) -> หยุดแอดเพราะ: {reason}")
        if paused_actions:
            now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")
            _send_telegram_alert(
                f"☁️🛡️ [Render Cloud 24/7 — บอทคุมงบแอดสั่งพักโฆษณาอัตโนมัติ!]\n"
                f"⏰ เวลา: {now_str} น.\n"
                + "\n".join(paused_actions)
            )
        return {"ok": True, "active_campaigns": len(active), "paused": len(paused_actions)}
    except Exception as e:
        logger.warning(f"[FishCloudWorker] ads guard error: {e}")
        return {"ok": False, "error": str(e)}


async def fish_ads_guard_loop(interval_seconds: int = 14400):
    """ลูปบอทคุมงบโฆษณา Facebook Ads ทุก 4 ชั่วโมงบน Render Cloud"""
    logger.info("🛡️ [FishCloudWorker] เริ่มระบบบอทคุมงบแอด Facebook ทุก 4 ชั่วโมง")
    while True:
        await asyncio.sleep(120)
        try:
            res = await asyncio.to_thread(run_fish_cloud_ads_guard_cycle)
            logger.info(f"🛡️ [FishCloudWorker] Ads guard result: {res}")
        except Exception as e:
            logger.warning(f"[FishCloudWorker] Ads guard loop error: {e}")
        await asyncio.sleep(interval_seconds)
