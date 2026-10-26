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


def _reply_to_facebook(recipient_id: str, text: str) -> bool:
    """ส่งข้อความกลับเข้า Messenger ของผู้ใช้ผ่าน Meta Graph Send API"""
    if not FACEBOOK_PAGE_ACCESS_TOKEN:
        logger.warning("[facebook] Missing FACEBOOK_PAGE_ACCESS_TOKEN")
        return False
    try:
        r = httpx.post(
            "https://graph.facebook.com/v21.0/me/messages",
            params={"access_token": FACEBOOK_PAGE_ACCESS_TOKEN},
            json={
                "recipient": {"id": recipient_id},
                "message": {"text": text}
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
            "product_name": "ปลาสลิดแดดเดียว ไซส์จัมโบ้ 6 ตัวโล ป้าเข็ม คัดพิเศษ",
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


def _handle_event(event: dict) -> None:
    """ประมวลผลข้อความจาก Messenger ด้วยระบบ 4 พนักงาน AI"""
    sender = (event.get("sender") or {}).get("id")
    message = event.get("message") or {}
    if not sender:
        return
    text = (message.get("text") or "").strip()
    if not text:
        return

    lower_text = text.lower()
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # 1. ตรวจจับการสั่งซื้ออัตโนมัติ (Autonomous Order & Address Extractor)
    phone_match = re.search(r'(?:0[689]\d{8}|0[689]\d{1}[-\s]?\d{3}[-\s]?\d{4}|0[689]\d{2}[-\s]?\d{3}[-\s]?\d{3})', text)
    has_address = bool(re.search(r'(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|ถนน|ถ\.|ซอย|ซ\.|ม\.|หมู่ที่|หมู่|\b\d{5}\b)', text))

    if phone_match and (has_address or len(text) > 25):
        phone = re.sub(r'[-\s]', '', phone_match.group(0))
        
        # คัดกรองแพ็กเกจ
        if "500" in text or "พอดีมื้อ" in text or "ทดลอง" in text:
            pkg_name = "ชุดพอดีมื้อ ไซส์จัมโบ้ (500 กรัม / 3 ตัวใหญ่)"
            price = 390.0
        elif "2" in text or "สองโล" in text or "เหมา" in text or "2kg" in text:
            pkg_name = "ชุดสุดคุ้มตุนฟรีซ ไซส์จัมโบ้ (2 กิโลกรัม / 12 ตัวใหญ่)"
            price = 1090.0
        else:
            pkg_name = "ชุดยอดฮิต ไซส์จัมโบ้ (1 กิโลกรัม / 6 ตัวใหญ่)"
            price = 550.0

        payment_method = "โอนเงินผ่านธนาคาร 🏦" if any(k in text for k in ["โอน", "สลิป", "พร้อมเพย์"]) else "เก็บเงินปลายทาง (COD) 💵"
        order_code = f"PKF-{datetime.now().strftime('%m%d%H%M%S')}"

        # บันทึกลง Supabase
        _save_order_to_supabase(order_code, f"ลูกค้า Facebook ({sender[:6]})", phone, text, pkg_name, price, payment_method)

        # ตอบกลับลูกค้าใน Messenger ทันที
        reply_msg = (
            f"📝 [แอดมินน้องพิม - แผนกรับออเดอร์และการเงิน]\n"
            f"ขอบพระคุณสำหรับคำสั่งซื้อค่ะคุณลูกค้า 🙏💕\n"
            f"น้องพิมบันทึกออเดอร์และออกรหัสจัดส่งเรียบร้อยแล้วค่ะ ✨\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔖 รหัสคำสั่งซื้อ: {order_code}\n"
            f"📦 แพ็กเกจ: {pkg_name}\n"
            f"💰 ยอดรวม: {price:,.0f} บาท\n"
            f"💳 วิธีชำระ: {payment_method}\n"
            f"📞 เบอร์โทร: {phone}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🚚 พี่วินเตรียมลงคิวแพ็คซีลสูญญากาศและส่งรถเย็น Inter Express ให้รอบถัดไปเลยนะคะ รอรับปลาสลิดหอมกรอบที่บ้านได้เลยค่ะ 😊\n\n"
            f"🛒 ดูสถานะหรือสั่งซื้อเพิ่มได้ที่: {WEB_STORE_URL}"
        )
        _reply_to_facebook(sender, reply_msg)

        # แจ้งเตือนเข้า Telegram เจ้าของร้าน
        _send_telegram_alert(
            f"🐟 [ออเดอร์ใหม่จาก Facebook Messenger] 🔔\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔖 รหัส: {order_code}\n"
            f"👤 ผู้สั่ง: Facebook ID {sender}\n"
            f"📞 โทร: {phone}\n"
            f"📦 สินค้า: {pkg_name}\n"
            f"💰 ยอดเก็บเงิน: {price:,.0f} บาท ({payment_method})\n"
            f"📍 ข้อมูลที่อยู่:\n{text}\n"
            f"⏰ เวลา: {now_str}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 เตรียมจัดส่งรอบถัดไปได้เลยครับ"
        )
        return

    # 2. เกราะป้องกันโอนสายหาคนจริง (Human-in-the-Loop)
    human_keywords = ["ติดต่อคน", "ขอคุยกับคน", "ขอมนุษย์", "พนักงานคนจริง", "แอดมินคน", "ไม่เอาบอท", "คุยไม่รู้เรื่อง", "คนจริง", "โทรหา", "ขอเบอร์โทร", "คุยกับคน"]
    if any(k in lower_text for k in human_keywords):
        human_msg = (
            "👵 [ป้าเข็ม - เจ้าของร้านปลาสลิดสุพรรณบุรี]\n"
            "รับทราบเลยจ้ะลูก! ป้าเข็มได้ส่งสัญญาณแจ้งเตือนด่วนไปยัง [เจ้าของร้าน / แอดมินคนจริง] ให้เรียบร้อยแล้วนะจ๊ะ 🔔✨\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "แอดมินคนจริงจะรีบเข้ามาเปิดแชทนี้และพิมพ์ตอบหนูโดยเร็วที่สุดจ้ะ\n\n"
            "💡 ระหว่างนี้หนูพิมพ์ข้อความหรือเรื่องที่ต้องการสอบถามทิ้งไว้ในแชทนี้ได้เลยนะลูก ป้าเข็มและทีมงานยินดีดูแลเต็มที่จ้ะ 💕"
        )
        _reply_to_facebook(sender, human_msg)

        # ยิงสัญญาณฉุกเฉินเข้า Telegram
        _send_telegram_alert(
            f"🚨 [ด่วน: ลูกค้า Facebook Messenger ขอคุยกับคนจริง!] 🔔\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 Facebook Sender ID: {sender}\n"
            f"💬 ข้อความ: \"{text}\"\n"
            f"⏰ เวลา: {now_str}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 กรุณาเปิดแอพ Facebook Page หรือ Business Suite เข้าตอบลูกค้าได้ทันทีครับ"
        )
        return

    # 3. เจ้าของร้าน & เคส VIP / ขายส่ง / เคลมสินค้า
    owner_keywords = ["คุยกับป้าเข็ม", "ขอคุยกับป้าเข็ม", "เจ้าของร้าน", "เคลม", "ปลาเน่า", "ปลาเสีย", "ร้องเรียน", "ขายส่ง", "สั่งเยอะ", "ตัวแทน", "รับไปขาย"]
    if any(k in lower_text for k in owner_keywords):
        owner_msg = (
            "👵 [ป้าเข็ม - เจ้าของร้านปลาสลิดสุพรรณบุรี]\n"
            "สวัสดีจ้ะลูก ป้าเข็มมาดูแลด้วยตัวเองเลยจ้ะ 🙏😊\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "• หากเป็นเรื่องเคลมสินค้า: หากพบถุงซีลรั่ว หรือสินค้าเสียหายระหว่างขนส่ง ป้าเข็มรับประกันส่งชุดใหม่ให้ฟรีทันทีจ้ะ!\n"
            "• หากสนใจขายส่ง/ตัวแทน (สั่ง 20-50 กก. ขึ้นไป): แจ้งจำนวนและเบอร์โทรทิ้งไว้ได้เลยจ้ะ ป้าเข็มมีราคาพิเศษหน้าบ่อให้จ้ะ\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💬 หรือแอดไลน์คุยกับป้าเข็มโดยตรงได้ที่: {LINE_OA_URL}"
        )
        _reply_to_facebook(sender, owner_msg)
        return

    # 4. เมนูฮีลใจ & อาหารคลายเหนื่อย (น้องแพรว)
    emotion_keywords = ["เหนื่อย", "เครียด", "หมดแรง", "เบื่อ", "หิว", "กินอะไรดี", "กินไรดี", "ทอดกินกับอะไรดี", "เมนู", "แนะนำเมนู", "ฮีลใจ", "ปลอบใจ"]
    if any(k in lower_text for k in emotion_keywords):
        emotion_msg = (
            "🍲 [แอดมินน้องแพรว - ฝ่ายขายและบริการ]\n"
            "กอดๆ ส่งกำลังใจให้นะคะคุณลูกค้า 💕 วันนี้เหนื่อยมาทั้งวันแล้ว น้องแพรวขอแนะนำ 3 เมนูฮีลใจจากปลาสลิดสุพรรณมื้อนี้นะคะ ✨\n\n"
            "1️⃣ เมนูคลายเหนื่อย: 'ปลาสลิดทอดกรอบนอกนุ่มฟู คู่น้ำปลาพริกมะนาวสด' บีบมะนาวฉ่ำๆ ราดข้าวสวยร้อนๆ หอมกรอบฟินทันทีค่ะ\n"
            "2️⃣ เมนูคิดถึงบ้าน: 'ต้มยำปลาสลิดใบมะขามอ่อน' ร้อนๆ ซดคล่องคอ ชื่นใจเหมือนรสมือแม่ทำให้ทานที่บ้าน\n"
            "3️⃣ เมนูรอบดึก: 'ข้าวต้มกุ๊ยร้อนๆ แกล้มปลาสลิดทอด' กรอบ มัน เค็มกำลังดี ทานง่าย สบายท้องค่ะ\n\n"
            f"🛒 รับ [ชุดพอดีมื้อ 500g (390.- ส่งฟรี)] หรือ [ชุดยอดฮิต 1kg (550.- ส่งฟรี)] พิมพ์ชื่อที่อยู่สั่งในแชทนี้ได้เลยนะคะ หรือสั่งผ่านเว็บ: {WEB_STORE_URL}"
        )
        _reply_to_facebook(sender, emotion_msg)
        return

    # 5. แก้ข้อโต้แย้งเรื่องรสชาติ / ความเค็ม (น้องแพรว)
    if any(k in lower_text for k in ["เค็มไหม", "เค็มมั้ย", "เค็มป่าว", "รสชาติ", "หวานไหม", "ไตพัง", "เค็มมากไหม"]):
        taste_msg = (
            "🧂 [แอดมินน้องแพรว - ฝ่ายขายและบริการ]\n"
            "ไม่เค็มจัดแน่นอนค่ะคุณลูกค้า! น้องแพรวการันตีเลยค่ะ ทางร้านใช้สูตรโบราณหมักเกลือสมุทรธรรมชาติเพียง 3% ควบคุมรสชาติให้เค็มกำลังดี กลมกล่อม ไม่เค็มแสบคอและไม่เค็มไตพังค่ะ 🧂✨\n\n"
            "เนื้อปลาแดดเดียวสุพรรณบุรีแท้ เนื้อจะฟู แน่น หอมแดด ทอดแล้วหนังกรอบเนื้อนุ่ม คนรักสุขภาพและผู้สูงอายุทานได้อย่างสบายใจแน่นอนค่ะ 💕"
        )
        _reply_to_facebook(sender, taste_msg)
        return

    # 6. แก้ข้อโต้แย้งเรื่องความสะอาด / สารเคมี (น้องแพรว)
    if any(k in lower_text for k in ["สะอาดไหม", "สะอาดมั้ย", "แมลงวัน", "มีฝุ่น", "ตากยังไง", "สารเคมี", "ฟอร์มาลีน", "ยาฆ่าแมลง"]):
        clean_msg = (
            "☀️ [แอดมินน้องแพรว - ฝ่ายขายและบริการ]\n"
            "สะอาด ปลอดภัย 100% ได้มาตรฐานแน่นอนค่ะคุณลูกค้า! ☀️✨\n\n"
            "ปลาของทางร้านตากใน 'โรงอบพลังงานแสงอาทิตย์แบบปิด (Solar Greenhouse)' ปิดมิดชิด ไร้แมลงวันตอม 100% ปลอดฝุ่น PM2.5 และล้างด้วยน้ำสะอาดหลายรอบ ไร้สารฟอร์มาลีน ไร้ยาฆ่าแมลง และไม่ใส่สารกันบูดใดๆ ทั้งสิ้นค่ะ บรรจุซีลสูญญากาศมาตรฐานญี่ปุ่น ปลอดภัยสำหรับทุกคนในครอบครัวแน่นอนค่ะ 😊"
        )
        _reply_to_facebook(sender, clean_msg)
        return

    # 7. คลังสินค้า & วิธีเก็บรักษา & วิธีทอด (พี่วิน)
    if any(k in lower_text for k in ["เก็บได้นานไหม", "เก็บได้กี่วัน", "แช่ตู้เย็น", "แช่ฟรีซ", "วิธีเก็บ", "วิธีทอด", "ทอดยังไง", "อายุ", "ซีล", "สูญญากาศ"]):
        storage_msg = (
            "❄️ [พี่วิน - ฝ่ายจัดส่งและคลังสินค้าห้องเย็น]\n"
            "สวัสดีครับคุณลูกค้า! พี่วินแนะนำตามนี้เลยครับ 👨‍🍳✨\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📦 การเก็บรักษา (ถุง PA/PE ซีลสูญญากาศหนาพิเศษ):\n"
            "  • แช่ช่องฟรีซ (-18°C): เก็บรักษาความสดได้นานถึง 6 เดือน!\n"
            "  • แช่ช่องธรรมดา (0-4°C): เก็บได้นาน 7-10 วันครับ\n\n"
            "🍳 เคล็ดลับทอดให้อร่อย หนังกรอบเนื้อนุ่มฟู:\n"
            "  1. นำปลาออกจากช่องฟรีซ พักให้คลายเย็นที่อุณหภูมิห้อง\n"
            "  2. ตั้งกระทะน้ำมันท่วม ใช้ไฟกลางค่อนไปทางอ่อน\n"
            "  3. ทอดจนหนังปลาเหลืองทอง กรอบฟู แล้วตักขึ้นสะเด็ดน้ำมัน ทานร้อนๆ อร่อยมากครับ!"
        )
        _reply_to_facebook(sender, storage_msg)
        return

    # 7.5 สอบถามเลขบัญชี / โอนเงินชำระค่าสินค้า (น้องพิม)
    if any(k in lower_text for k in ["เลขบัญชี", "ขอเลขบัญชี", "โอนเงิน", "เลขที่บัญชี", "บัญชีธนาคาร", "โอนจ่าย"]):
        bank_msg = (
            "💳 [แอดมินน้องพิม - แผนกรับออเดอร์และการเงิน]\n"
            "คุณลูกค้าสามารถโอนชำระค่าสินค้าได้ที่บัญชีด้านล่างนี้เลยนะคะ 🙏✨\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🏦 ธนาคาร: ธนาคารกรุงไทย (Krungthai - ออมทรัพย์ สาขาท่าพระ)\n"
            "🔢 เลขที่บัญชี: 038-0-25363-1\n"
            "👤 ชื่อบัญชี: นายจีรวัฒน์ พลอาจ\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📸 โอนเรียบร้อยแล้ว ส่งรูปสลิปพร้อม ชื่อ-ที่อยู่-เบอร์โทร ในแชทนี้ หรือแนบสลิปหน้าเว็บได้เลยค่ะ น้องพิมจะรีบจัดส่งให้ทันทีค่ะ 😊"
        )
        _reply_to_facebook(sender, bank_msg)
        return

    # 8. รอบจัดส่ง & COD (พี่วิน)
    if any(k in lower_text for k in ["ส่งยังไง", "ส่งฟรีไหม", "ค่าส่ง", "ปลายทาง", "เก็บเงินปลายทาง", "cod", "กี่วันถึง", "ส่งวันไหน"]):
        shipping_msg = (
            "🚚 [พี่วิน - ฝ่ายจัดส่งและคลังสินค้าห้องเย็น]\n"
            "สวัสดีครับคุณลูกค้า! พี่วินแจ้งข้อมูลรอบจัดส่งและบริการเก็บเงินปลายทางครับ 💨\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📦 ราคาและโปรโมชั่น (ปลาสลิดไซส์จัมโบ้ 6 ตัวโล):\n"
            "  • ชุดพอดีมื้อ (500g / 3 ตัวใหญ่): 390 บาท (🔥 ส่งด่วนแพ็กฟอยล์เจลเก็บความเย็น ฟรีทั่วไทย!)\n"
            "  • ชุดยอดฮิต (1kg / 6 ตัวใหญ่): 550 บาท (🔥 ส่งด่วนแพ็คเจลเก็บความเย็น ฟรีทั่วไทย!)\n"
            "  • ชุดสุดคุ้มตุนฟรีซ (2kg / 12 ตัว): 1,090 บาท (❄️ ส่งฟรีรถตู้เย็นควบคุมอุณหภูมิ!)\n\n"
            "💳 มีบริการเก็บเงินปลายทาง (COD) ตรวจรับของหน้าบ้านเรียบร้อยแล้วค่อยชำระเงินกับเจ้าหน้าที่ขนส่งได้เลยครับ สะดวกและปลอดภัย 100% ครับ 😊"
        )
        _reply_to_facebook(sender, shipping_msg)
        return

    # 9. Default Catalog & Welcome
    catalog_msg = (
        "🐟 [ยินดีต้อนรับสู่ร้านปลาสลิดแดดเดียว สุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ] 💕\n"
        "แอดมินน้องแพรวยินดีให้บริการคุณลูกค้าใน Facebook Messenger นะคะ 🙏✨\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🌟 เมนูแพ็กเกจปลาสลิดคัดพิเศษ ไซส์จัมโบ้ 6 ตัวโล:\n\n"
        "1️⃣ 🐟 ชุดพอดีมื้อ (500 กรัม / 3 ตัวใหญ่) : 390.- (🔥 ส่งด่วนแพ็กฟอยล์เจลเย็น ฟรี!)\n"
        "2️⃣ ⭐ ชุดยอดฮิต (1 กิโลกรัม / 6 ตัวใหญ่) : 550.- (🔥 จัดส่งฟรีทั่วไทย - ขายดีอันดับ 1)\n"
        "3️⃣ 📦 ชุดสุดคุ้มตุนฟรีซ (2 กิโลกรัม / 12 ตัวใหญ่) : 1,090.- (❄️ ฟรีรถควบคุมความเย็น)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👉 สั่งซื้อง่ายๆ เพียงพิมพ์ 'ชื่อ-ที่อยู่-เบอร์โทร' ในแชทนี้ได้เลยนะคะ แอดมินน้องพิมจะลงคิวจัดส่งให้ทันทีค่ะ!\n\n"
        f"🛒 หรือสั่งผ่านหน้าร้านเว็บด่วนได้ที่: {WEB_STORE_URL}\n"
        f"💬 แอดไลน์ร้าน: {LINE_OA_URL}"
    )
    _reply_to_facebook(sender, catalog_msg)


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
