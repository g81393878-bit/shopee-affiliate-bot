# -*- coding: utf-8 -*-
"""
Facebook Messenger Webhook — Multi-Agent Router 4 พนักงาน AI ปลาสลิดสุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ
รองรับการรับข้อความจาก Messenger บนเพจ Facebook:
  1. น้องแพรว (ฝ่ายขายและบริการ): แนะนำเมนูฮีลใจ, รสชาติหมักเกลือ 3%, ความสะอาดโรงอบปิด
  2. น้องพิม (แผนกรับออเดอร์และการเงิน): ตรวจจับที่อยู่ เบอร์โทร ออกรหัส PKF-xxxx บันทึกลง Supabase และยิงแจ้งเตือนเข้า Telegram @pakhem_fish_bot
  3. พี่วิน (ฝ่ายจัดส่งและคลังห้องเย็น): ชี้แจงรอบจัดส่งรถเย็น Inter Express, มีเก็บเงินปลายทาง (COD), วิธีแช่ฟรีซ 6 เดือน
  4. ป้าเข็ม (เจ้าของร้าน & VIP): ดูแลเคลมสินค้า, ขายส่ง 50 กก., โอนสายหาคนจริง (Human-in-the-Loop) ผ่าน Telegram
"""

import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger("FacebookBot")

# Environment configurations
FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET") or "mock_facebook_app_secret"
FACEBOOK_VERIFY_TOKEN = os.getenv("FACEBOOK_VERIFY_TOKEN") or "pakhem_fish_verify_2026"
FACEBOOK_PAGE_ACCESS_TOKEN = (
    os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    or "REDACTED_SECRET"
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8939151149:AAGrVkCv0xZrlvtRPO8mzelOYsp5ah5M13U")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6734965582")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://usqhvujqmnxqrdoovvnp.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY", "")

WEB_STORE_URL = "https://watt29.github.io/pakhem-shop/fish.html"
LINE_OA_URL = "https://line.me/R/ti/p/@137gsref"

router = APIRouter(prefix="/webhooks", tags=["facebook"])


def _verify_signature(body: bytes, signature: str) -> bool:
    """ตรวจลายเซ็น X-Hub-Signature-256 (HMAC-SHA256 ด้วย App Secret)"""
    if not signature or "=" not in signature:
        return False
    algo, _, expected = signature.partition("=")
    algo = algo.strip().lower()
    if algo == "sha256":
        digest = hmac.new(FACEBOOK_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    elif algo == "sha1":
        digest = hmac.new(FACEBOOK_APP_SECRET.encode(), body, hashlib.sha1).hexdigest()
    else:
        return False
    return hmac.compare_digest(digest, expected.strip())


DEFAULT_QUICK_REPLIES = [
    {"content_type": "text", "title": "รับชุด 500g (3-4ตัว)", "payload": "QR_PKG_500G"},
    {"content_type": "text", "title": "รับชุด 1กก. (5-7ตัว)", "payload": "QR_PKG_1KG"},
    {"content_type": "text", "title": "ปลายทาง 500g (410.-)", "payload": "QR_COD_500G"},
    {"content_type": "text", "title": "ปลายทาง 1กก. (570.-)", "payload": "QR_COD_1KG"},
]


def _reply_to_facebook(recipient_id: str, text: str, quick_replies: list | None = None) -> bool:
    """ส่งข้อความพร้อมปุ่มกดเลือกด่วน (Quick Replies) กลับเข้า Messenger ของผู้ใช้ผ่าน Meta Graph Send API"""
    if not FACEBOOK_PAGE_ACCESS_TOKEN:
        logger.warning("[facebook] Missing FACEBOOK_PAGE_ACCESS_TOKEN")
        return False
    try:
        msg_obj: dict = {"text": text}
        if quick_replies:
            msg_obj["quick_replies"] = quick_replies
        r = httpx.post(
            "https://graph.facebook.com/v21.0/me/messages",
            params={"access_token": FACEBOOK_PAGE_ACCESS_TOKEN},
            json={
                "recipient": {"id": recipient_id},
                "messaging_type": "RESPONSE",
                "message": msg_obj,
            },
            timeout=10,
        )
        if r.status_code != 200 and quick_replies:
            r = httpx.post(
                "https://graph.facebook.com/v21.0/me/messages",
                params={"access_token": FACEBOOK_PAGE_ACCESS_TOKEN},
                json={
                    "recipient": {"id": recipient_id},
                    "messaging_type": "RESPONSE",
                    "message": {"text": text},
                },
                timeout=10,
            )
        if r.status_code != 200:
            logger.warning(f"[facebook] send failed ({r.status_code}): {r.text}")
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"[facebook] send error: {e}")
        return False


def _send_telegram_alert(text: str) -> bool:
    """ส่งแจ้งเตือนด่วนเข้า Telegram @pakhem_fish_bot ของเจ้าของร้านทันที"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=8,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"[facebook] telegram alert failed: {e}")
        return False


def _save_order_to_supabase(order_code: str, name: str, phone: str, address: str, pkg: str, price: float, payment_method: str) -> bool:
    """บันทึกออเดอร์ใหม่จาก Facebook ลง Supabase direct_orders"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
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
            "note": "สั่งซื้อผ่าน Facebook Messenger",
            "created_at": datetime.now().isoformat()
        }
        r = httpx.post(f"{SUPABASE_URL}/rest/v1/direct_orders", headers=headers, json=payload, timeout=8)
        return r.status_code in (200, 201)
    except Exception as e:
        logger.warning(f"[facebook] supabase insert failed: {e}")
        return False


def _analyze_image_with_groq_vision(img_url: str) -> dict:
    """ใช้ Groq Vision (qwen/qwen3.8-27b) อ่านรูปภาพบน Cloud Render โดยไม่กินแรมเครื่อง"""
    res = {"category": "other", "extracted_text": "", "amount": ""}
    try:
        import base64
        from app.services.llm_clients import groq_clients
        clients = groq_clients()
        if not clients:
            return res
        img_resp = httpx.get(img_url, timeout=10)
        if img_resp.status_code != 200:
            return res
        b64 = base64.b64encode(img_resp.content).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"
        prompt = (
            "อ่านรูปภาพนี้และแยกประเภทเป็น JSON เท่านั้น:\n"
            "1. ถ้าเป็นกระดาษหรือข้อความจด ชื่อ-ที่อยู่-เบอร์โทร สำหรับส่งของ ให้ตอบ category='address' และถอดข้อความทั้งหมดลงใน extracted_text\n"
            "2. ถ้าเป็นสลิปโอนเงินธนาคารที่มีรายการโอนสำเร็จ ให้ตอบ category='slip' พร้อมระบุยอดเงินใน amount\n"
            "3. ถ้าเป็นรูปอื่นๆ ให้ตอบ category='other'\n"
            'รูปแบบ JSON: {"category": "address|slip|other", "extracted_text": "ข้อความทั้งหมดที่อ่านได้ในรูป", "amount": "ยอดเงินถ้าเป็นสลิป"}'
        )
        for c in clients:
            try:
                resp = c.chat.completions.create(
                    model="qwen/qwen3.8-27b",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }]
                )
                raw = (resp.choices[0].message.content or "").strip()
                raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict):
                        return {
                            "category": str(parsed.get("category") or "other").strip().lower(),
                            "extracted_text": str(parsed.get("extracted_text") or "").strip(),
                            "amount": str(parsed.get("amount") or "").strip()
                        }
            except Exception as e:
                logger.warning(f"[facebook] Groq vision key failed: {e}")
    except Exception as e:
        logger.warning(f"[facebook] Groq vision error: {e}")
    return res


def _handle_event(event: dict) -> None:
    """ประมวลผล Messenger: สั้น กระชับ ชัดเจน อ่านรูปลายมือและสลิปด้วย Groq Vision บน Cloud จริง"""
    sender = (event.get("sender") or {}).get("id")
    message = event.get("message") or {}
    if not sender or message.get("is_echo"):
        return
    if sender in ("1307380735783361", "1323469404180656"):
        return
    text = (message.get("text") or "").strip()
    qr_payload = ((message.get("quick_reply") or {}).get("payload") or "").strip()
    attachments = message.get("attachments") or []

    MENU_SHORT = (
        "🐟 ปลาสลิดแดดเดียว ป้าเข็ม (สุพรรณแท้ ไซส์จัมโบ้ 5-7 ตัว/กก.)\n"
        "ทอดกรอบนอกนุ่มใน เค็มน้อย 3% แพ็กซองฟอยล์+เจลเย็นทุกกล่อง\n\n"
        "📦 โปรโมชั่นพิเศษ (เลือกโอนส่งฟรี หรือ เก็บเงินปลายทาง ได้เลยค่ะ):\n"
        "1️⃣ ชุด 500 กรัม (ประมาณ 3-4 ตัว) : โอน 390.- ส่งฟรี! | ปลายทาง 410.-\n"
        "2️⃣ ชุดขายดี 1 กิโลกรัม (ประมาณ 5-7 ตัว) : โอน 550.- ส่งฟรี! | ปลายทาง 570.- ⭐\n"
        "3️⃣ ชุดคุ้ม 2 กิโลกรัม (ประมาณ 10-14 ตัว) : โอน 1,090.- ส่งฟรีรถห้องเย็น!\n\n"
        "👉 กดปุ่มเลือกชุดด้านล่าง หรือพิมพ์ 'ชื่อ-ที่อยู่-เบอร์โทร' ในแชทนี้ได้เลยนะคะ 😊"
    )

    # 0. ตรวจจับรูปภาพด้วย Groq Vision (qwen/qwen3.8-27b)
    if not text and attachments:
        for att in attachments:
            if att.get("type") == "image":
                img_url = (att.get("payload") or {}).get("url")
                if img_url:
                    v_res = _analyze_image_with_groq_vision(img_url)
                    cat = v_res.get("category", "other")
                    ocr_text = v_res.get("extracted_text", "")
                    amt = v_res.get("amount", "")

                    if cat == "slip":
                        _reply_to_facebook(sender, f"ได้รับสลิปโอนเงิน {amt} บาท เรียบร้อยค่ะ 🙏 รบกวนพิมพ์แจ้ง 'ชื่อ-ที่อยู่-เบอร์โทร' สำหรับจัดส่งไว้ได้เลยนะคะ ทางร้านจะรีบจัดส่งให้ค่ะ 😊")
                        _send_telegram_alert(f"💳 [ลูกค้าส่งสลิปโอนเงิน!]\n👤 Facebook: `{sender}`\n💰 ยอด: {amt}\n🖼️ สลิป: {img_url}\n📝 ข้อความ: {ocr_text[:120]}")
                        return
                    elif cat == "address" or any(k in ocr_text for k in ["อำเภอ", "จังหวัด", "ถนน", "ตำบล", "โทร", "ปลายทาง"]):
                        text = ocr_text
                        _send_telegram_alert(f"📦 [ลูกค้าส่งรูปจดที่อยู่จัดส่ง!]\n👤 Facebook: `{sender}`\n🖼️ รูป: {img_url}\n📝 ที่อยู่ที่อ่านได้:\n{ocr_text}")
                        break
                    else:
                        _reply_to_facebook(sender, f"ได้รับรูปภาพเรียบร้อยค่ะ 🙏\n\n{MENU_SHORT}", DEFAULT_QUICK_REPLIES)
                        _send_telegram_alert(f"📸 [ลูกค้าส่งรูปภาพทั่วไป]\n👤 Facebook: `{sender}`\n🖼️ รูป: {img_url}")
                        return

    if not text:
        postback = event.get("postback") or {}
        text = (postback.get("title") or postback.get("payload") or "").strip()
        if not qr_payload:
            qr_payload = (postback.get("payload") or "").strip()
    if not text and not qr_payload:
        return

    lower_text = text.lower().strip()
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # 1. ลูกค้าพิมพ์ตัวเลข หรือ กดปุ่มแอด/Quick Reply เลือกชุด (ต้องเช็คก่อนเช็คเบอร์โทร แต่ถ้ามีที่อยู่+เบอร์โทรให้ข้ามไปบันทึกออเดอร์เลย)
    text_clean_phone = re.sub(r'[-\s]', '', text)
    phone_match = re.search(r'0[689]\d{8}', text_clean_phone)
    has_address = any(k in text for k in ["บ้านเลขที่", "ต.", "อ.", "จ.", "ตำบล", "อำเภอ", "จังหวัด", "ถนน", "ถ.", "ซอย", "ซ.", "ม.", "หมู่"])

    if not phone_match:
        is_cod_intent = any(k in lower_text for k in ["สั่งแบบเก็บเงินปลายทาง", "เก็บเงินปลายทาง", "เก็บปลายทาง", "ปลายทาง", "cod"])
        has_1kg_unit = any(k in lower_text for k in ["รับชุดขายดี", "ชุดขายดี", "1 กก", "1กก", "1kg", "1 กิโล", "1กิโล", "หนึ่งกิโล", "โลนึง", "1 โล", "1โล", "5-7 ตัว", "5-7ตัว", "570"])
        has_500g_unit = any(k in lower_text for k in ["รับชุดพอดีมื้อ", "ชุดพอดีมื้อ", "500g", "500 กรัม", "500กรัม", "ครึ่งโล", "ครึ่งกิโล", "3-4 ตัว", "3-4ตัว", "410"])
        is_1kg_intent = qr_payload in ("QR_PKG_1KG", "ORDER_PKG_1KG", "QR_COD_1KG") or has_1kg_unit or (
            not has_500g_unit and (lower_text in ("2", "ชุด2", "ชุด 2", "เอาชุด2", "เอา 2", "รับชุด 2") or any(k in lower_text for k in ["ชุด 2", "ชุด2"]))
        )
        is_500g_intent = qr_payload in ("QR_PKG_500G", "ORDER_PKG_500G", "QR_COD_500G") or has_500g_unit or (
            not has_1kg_unit and (lower_text in ("1", "ชุด1", "ชุด 1", "เอาชุด1", "เอา 1", "รับชุด 1") or any(k in lower_text for k in ["ชุด 1", "ชุด1"]))
        )

        # 1.0 ปุ่ม Quick Reply เก็บปลายทาง ชุด 500g (410.-) หรือ พิมพ์เลือกชุด 500g + ปลายทาง
        if qr_payload == "QR_COD_500G" or (is_cod_intent and is_500g_intent and not is_1kg_intent):
            _reply_to_facebook(
                sender,
                "✅ รับชุดพอดีมื้อ 500 กรัม (ประมาณ 3-4 ตัว) แบบเก็บเงินปลายทาง (COD) ยอดรวม 410 บาท (รวมส่งแพ็กฟอยล์เจลเย็นแล้ว จ่ายเงินหน้าบ้านตอนรับของได้เลยค่ะ) 🚚❄️\n\n"
                "👉 รบกวนพิมพ์แจ้ง 'ชื่อ - ที่อยู่จัดส่ง - เบอร์โทรศัพท์' ในแชทนี้ได้เลยนะคะ เดี๋ยวทางร้านล็อกคิวแพ็กส่งรอบสดใหม่ให้ทันทีค่ะ 😊"
            )
            return

        # 1.05 ปุ่ม Quick Reply เก็บปลายทาง ชุด 1 กก. (570.-) หรือ พิมพ์เลือกชุด 1 กก. + ปลายทาง
        if qr_payload == "QR_COD_1KG" or (is_cod_intent and is_1kg_intent and not is_500g_intent):
            _reply_to_facebook(
                sender,
                "✅ รับชุดขายดี 1 กิโลกรัม (ประมาณ 5-7 ตัว) แบบเก็บเงินปลายทาง (COD) ยอดรวม 570 บาท (รวมส่งแพ็กฟอยล์เจลเย็นแล้ว จ่ายเงินหน้าบ้านตอนรับของได้เลยค่ะ) ⭐🚚❄️\n\n"
                "👉 รบกวนพิมพ์แจ้ง 'ชื่อ - ที่อยู่จัดส่ง - เบอร์โทรศัพท์' ในแชทนี้ได้เลยนะคะ เดี๋ยวทางร้านล็อกคิวแพ็กส่งรอบสดใหม่ให้ทันทีค่ะ 😊"
            )
            return

        # 1.1 ถามจำนวนตัว / กี่ตัวโล / ตัวละเท่าไหร่ / ไซส์ไหน
        if any(k in lower_text for k in ["กี่ตัว", "โลละกี่ตัว", "ตัวละ", "ราคาตัวละ", "ขายเป็นตัว", "แยกตัว", "ตัวใหญ่ไหม", "ตัวใหญ่มั้ย", "ไซส์ไหน", "ขนาดไหน"]):
            _reply_to_facebook(
                sender,
                "🐟 ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดไซส์ใหญ่พิเศษ ประมาณ 5-7 ตัว/กก.ค่ะ (จำหน่ายเป็นแพ็กซีลสูญญากาศ เนื้อหนาฟู เค็มน้อย 3%)\n\n"
                "1️⃣ ชุด 500 กรัม (ได้ประมาณ 3-4 ตัว | น้ำหนัก +/- 50g) : โอน 390.- ส่งฟรี (เฉลี่ยตัวละ ~97-130.-) | ปลายทาง 410.-\n"
                "2️⃣ ชุดขายดี 1 กิโลกรัม (ได้ประมาณ 5-7 ตัว | น้ำหนัก +/- 50g) : โอน 550.- ส่งฟรี (เฉลี่ยตัวละ ~78-110.- คุ้มมาก!) | ปลายทาง 570.- ⭐\n"
                "3️⃣ ชุดคุ้ม 2 กิโลกรัม (ได้ประมาณ 10-14 ตัว | น้ำหนัก +/- 50g) : โอน 1,090.- ส่งฟรีรถห้องเย็น (เฉลี่ยตัวละ ~77-109.-)!\n\n"
                "👉 กดปุ่มเลือกชุดด้านล่าง หรือพิมพ์ชุดที่รับ พร้อม 'ชื่อ-ที่อยู่-เบอร์โทร' ในแชทนี้ได้เลยนะคะ 😊",
                DEFAULT_QUICK_REPLIES,
            )
            return

        # 1.2 ปุ่ม "รับชุด 500g (3-4ตัว)" หรือ "รับชุดพอดีมื้อ 500g (โอน 390.- ส่งฟรี)" หรือเลือกชุด 1 (500g)
        if qr_payload in ("QR_PKG_500G", "ORDER_PKG_500G") or is_500g_intent:
            _reply_to_facebook(
                sender,
                "✅ รับชุดพอดีมื้อ 500 กรัม (ประมาณ 3-4 ตัว) ค่ะ 🐟✨\n"
                "• 💵 เก็บเงินปลายทาง (COD): 410 บาท (รวมส่งแล้ว จ่ายหน้าบ้าน)\n"
                "• 🏦 โอนเงินส่งฟรี: 390 บาท (ธ.กรุงไทย 038-0-25363-1 นายจีรวัฒน์ พลอาจ)\n\n"
                "👉 รบกวนพิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' แจ้งในแชทนี้ได้เลยนะคะ (หากโอนเงิน ส่งรูปสลิปแนบมาได้เลยค่ะ) 😊",
                [
                    {"content_type": "text", "title": "ปลายทาง 500g (410.-)", "payload": "QR_COD_500G"},
                    {"content_type": "text", "title": "รับชุด 1กก. (5-7ตัว)", "payload": "QR_PKG_1KG"},
                ],
            )
            return

        # 1.3 ปุ่ม "รับชุด 1กก. (5-7ตัว)" หรือ "รับชุดขายดี 1 กก. (โอน 550.- ส่งฟรี)" หรือเลือกชุด 2 (1kg)
        if qr_payload in ("QR_PKG_1KG", "ORDER_PKG_1KG") or is_1kg_intent:
            _reply_to_facebook(
                sender,
                "✅ รับชุดขายดี 1 กิโลกรัม (ประมาณ 5-7 ตัว) ค่ะ ⭐🐟\n"
                "• 💵 เก็บเงินปลายทาง (COD): 570 บาท (รวมส่งแล้ว จ่ายหน้าบ้าน)\n"
                "• 🏦 โอนเงินส่งฟรี: 550 บาท (ธ.กรุงไทย 038-0-25363-1 นายจีรวัฒน์ พลอาจ)\n\n"
                "👉 รบกวนพิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' แจ้งในแชทนี้ได้เลยนะคะ (หากโอนเงิน ส่งรูปสลิปแนบมาได้เลยค่ะ) 😊",
                [
                    {"content_type": "text", "title": "ปลายทาง 1กก. (570.-)", "payload": "QR_COD_1KG"},
                    {"content_type": "text", "title": "รับชุด 500g (3-4ตัว)", "payload": "QR_PKG_500G"},
                ],
            )
            return

        # 1.4 เลือกชุด 3 (2kg)
        if qr_payload in ("QR_PKG_2KG", "ORDER_PKG_2KG") or lower_text in ("3", "ชุด3", "ชุด 3", "เอาชุด3", "เอา 3", "รับชุด 3") or any(k in lower_text for k in ["รับชุดตุน", "ชุดตุน", "ชุดครอบครัว", "2 กก", "2กก", "2kg", "2 กิโล", "2กิโล", "สองโล", "สองกิโล", "2 โล", "2โล", "ชุด 3", "ชุด3"]):
            _reply_to_facebook(
                sender,
                "✅ รับชุดตุนสุดคุ้ม 2 กิโลกรัม (ประมาณ 10-14 ตัว) ยอดโอน 1,090 บาท ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิค่ะ ❄️🚚 (ชุด 2 กก. รับเฉพาะโอนเงินค่ะ)\n\n"
                "🏦 ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n\n"
                "👉 โอนแล้วส่งรูปสลิป พร้อมพิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' ในแชทนี้ได้เลยนะคะ 😊"
            )
            return

        # 1.5 ปุ่มแอด "สั่งแบบเก็บเงินปลายทาง (COD)" หรือพิมพ์ถามปลายทาง (เมื่อยังไม่ได้ระบุขนาดชุด)
        if is_cod_intent:
            _reply_to_facebook(
                sender,
                "✅ สั่งแบบเก็บเงินปลายทาง (COD) รับของหน้าบ้านก่อนจ่ายเงินได้เลยค่ะ 🚚❄️\n\n"
                "📦 เลือกชุดเก็บเงินปลายทาง (รวมค่าส่งแพ็กฟอยล์เจลเย็นแล้ว):\n"
                "1️⃣ ชุดพอดีมื้อ 500 กรัม (ประมาณ 3-4 ตัว) = 410 บาท\n"
                "2️⃣ ชุดขายดี 1 กิโลกรัม (ประมาณ 5-7 ตัว) = 570 บาท ⭐\n\n"
                "👉 กดปุ่มเลือกชุดด้านล่าง หรือพิมพ์แจ้ง 'ชุดที่รับ + ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' ในแชทนี้ได้เลยนะคะ 😊",
                [
                    {"content_type": "text", "title": "ปลายทาง 500g (410.-)", "payload": "QR_COD_500G"},
                    {"content_type": "text", "title": "ปลายทาง 1กก. (570.-)", "payload": "QR_COD_1KG"},
                ],
            )
            return

    # 2. ตรวจจับการสั่งซื้อพร้อมที่อยู่และเบอร์โทร (ทั้งจากพิมพ์ และจากรูปถ่ายที่อยู่)

    if phone_match and (has_address or len(text) > 20):
        phone = phone_match.group(0)
        is_transfer = any(k in text for k in ["โอน", "สลิป", "พร้อมเพย์"]) and "ปลายทาง" not in text
        if any(k in lower_text for k in ["500", "พอดีมื้อ", "ครึ่งโล", "ครึ่งกิโล", "ชุด 1", "ชุด1", "3 ตัว"]):
            pkg_name = "ชุดพอดีมื้อ 450-450-500 กรัม (ประมาณ 3-4 ตัว)"
            price = 390.0 if is_transfer else 410.0
        elif any(k in lower_text for k in ["2 กิโล", "2กิโล", "2 กก", "2กก", "สองโล", "2kg", "2 โล", "ชุด 3", "ชุด3", "ประมาณ 10-14 ตัว"]):
            pkg_name = "ชุดตุนสุดคุ้ม 1.8-2.0 กิโลกรัม (ประมาณ 10-14 ตัว)"
            price = 1090.0
            is_transfer = True
        else:
            pkg_name = "ชุดยอดฮิต 900-1,000 กรัม (ประมาณ 5-7 ตัว)"
            price = 550.0 if is_transfer else 570.0

        payment_method = "โอนเงินผ่านธนาคาร 🏦" if is_transfer else "เก็บเงินปลายทาง (COD) 💵"
        order_code = f"PKF-{datetime.now().strftime('%m%d%H%M%S')}"

        _save_order_to_supabase(order_code, f"ลูกค้า Facebook ({sender[:6]})", phone, text, pkg_name, price, payment_method)

        reply_msg = (
            f"ขอบพระคุณสำหรับคำสั่งซื้อค่ะ 🙏\n\n"
            f"📦 รหัสคำสั่งซื้อ: {order_code}\n"
            f"🐟 รายการ: {pkg_name}\n"
            f"💰 ยอดรวม: {price:,.0f} บาท ({payment_method})\n"
            f"📞 เบอร์โทร: {phone}\n"
            f"📍 ที่อยู่จัดส่ง:\n{text}\n\n"
            f"🚚 ทางร้านเตรียมแพ็กส่งรอบสดใหม่ให้ถึงหน้าบ้านเลยนะคะ ขอบพระคุณค่ะ 😊"
        )
        _reply_to_facebook(sender, reply_msg)
        _send_telegram_alert(
            f"🐟 [ออเดอร์ใหม่จาก Facebook!] 🔔\n"
            f"🔖 รหัส: {order_code}\n"
            f"📞 เบอร์: {phone}\n"
            f"📦 สินค้า: {pkg_name}\n"
            f"💰 ยอด: {price:,.0f} บาท ({payment_method})\n"
            f"📍 ที่อยู่:\n{text}\n"
            f"⏰ เวลา: {now_str}"
        )
        return

    # 3. ลูกค้าทิ้งเฉพาะเบอร์โทร ให้โทรกลับ
    if phone_match and not has_address and len(text) <= 35:
        phone = phone_match.group(0)
        _reply_to_facebook(sender, f"ได้รับเบอร์โทร {phone} เรียบร้อยค่ะ 🙏 เดี๋ยวเจ้าหน้าที่รีบโทรติดต่อกลับไปนะคะ\n(หรือพิมพ์ชื่อ-ที่อยู่ สั่งเก็บเงินปลายทางในแชทนี้ได้เลยค่ะ 😊)")
        _send_telegram_alert(f"📞 [ลูกค้าทิ้งเบอร์ให้โทรกลับ!]\n👤 Facebook: `{sender}`\n📱 เบอร์: **`{phone}`**\n💬 ข้อความ: \"{text}\"")
        return

    # 4. ลูกค้าพิมพ์ ยืนยัน / ตกลง
    if lower_text in ("ตกลง", "ยืนยัน", "ตกลงค่ะ", "ตกลงครับ", "ยืนยันค่ะ", "ยืนยันครับ", "ok", "โอเค"):
        _reply_to_facebook(sender, "ขอบพระคุณค่ะ 🙏 ทางร้านล็อกคิวเตรียมจัดส่งรอบสดใหม่ให้เรียบร้อยแล้วนะคะ เมื่อพัสดุออกเดินทางจะแจ้งให้ทราบค่ะ 😊")
        _send_telegram_alert(f"✅ [ลูกค้ายืนยันออเดอร์แล้ว!]\n👤 Facebook: `{sender}`")
        return

    # 5. ขอเลขบัญชี / โอนเงิน
    if any(k in lower_text for k in ["เลขบัญชี", "ขอเลขบัญชี", "โอนเงิน", "เลขที่บัญชี", "บัญชีธนาคาร", "โอนจ่าย"]):
        bank_msg = (
            "🏦 ธนาคารกรุงไทย (Krungthai)\n"
            "เลขที่บัญชี: 038-0-25363-1\n"
            "ชื่อบัญชี: นายจีรวัฒน์ พลอาจ\n\n"
            "โอนแล้วส่งรูปสลิป พร้อมแจ้ง 'ชื่อ-ที่อยู่-เบอร์โทร' ได้เลยนะคะ ขอบพระคุณค่ะ 🙏"
        )
        _reply_to_facebook(sender, bank_msg)
        return

    # 6. ถามเรื่องความเค็ม / รสชาติ
    if any(k in lower_text for k in ["เค็มไหม", "เค็มมั้ย", "รสชาติ", "เค็มมาก"]):
        _reply_to_facebook(sender, f"ไม่เค็มจัดแน่นอนค่ะ ป้าเข็มหมักเกลือสมุทรเพียง 3% กลมกล่อมกำลังดี ทอดกรอบนอกนุ่มในค่ะ 🐟\n\n{MENU_SHORT}", DEFAULT_QUICK_REPLIES)
        return

    # 7. ถามเรื่องค่าส่ง / ปลายทาง / ส่งกี่วัน
    if any(k in lower_text for k in ["ส่งยังไง", "ส่งฟรีไหม", "ค่าส่ง", "ปลายทาง", "เก็บเงินปลายทาง", "cod", "กี่วัน", "ส่งวันไหน"]):
        _reply_to_facebook(sender, f"🚚 โอนเงินส่งฟรีทุกชุดค่ะ (มีเก็บเงินปลายทาง COD +20.-)\nแพ็กเจลเย็นส่งถึงหน้าบ้านใน 1-2 วันค่ะ\n\n{MENU_SHORT}", DEFAULT_QUICK_REPLIES)
        return

    # 8. ทักทายทั่วไป หรือข้อความอื่นๆ -> ส่งเมนูสั้น กระชับ ทันที
    _reply_to_facebook(sender, MENU_SHORT, DEFAULT_QUICK_REPLIES)



@router.get("/facebook")
async def verify_webhook(request: Request):
    """Facebook ตั้งค่า Webhook → ส่ง GET มาตรวจสอบ verify token"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == FACEBOOK_VERIFY_TOKEN and challenge:
        logger.info("[facebook] webhook verify OK")
        return Response(content=challenge, media_type="text/plain")
    logger.warning("[facebook] verify rejected: mode=%s token_match=%s", mode, token == FACEBOOK_VERIFY_TOKEN)
    raise HTTPException(status_code=403, detail="webhook verify failed")


@router.post("/facebook")
async def receive_events(request: Request):
    """รับ Webhook events จาก Facebook Messenger และประมวลผลด้วย 4 พนักงาน AI"""
    body = await request.body()

    if FACEBOOK_APP_SECRET != "mock_facebook_app_secret":
        sig = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Hub-Signature")
        if not sig or not _verify_signature(body, sig):
            logger.warning("[facebook] rejected: missing/invalid signature")
            raise HTTPException(status_code=400, detail="invalid signature")

    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"invalid body: {e}")

    if data.get("object") != "page":
        return "OK"
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            _handle_event(event)
    return "OK"
