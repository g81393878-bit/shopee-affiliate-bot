# -*- coding: utf-8 -*-

"""

Facebook Messenger Webhook — Multi-Agent Router 4 พนักงาน AI ปลาสลิดสุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ

รองรับการรับข้อความจาก Messenger บนเพจ Facebook:

  1. น้องแพรว (ฝ่ายขายและบริการ): แนะนำเมนูฮีลใจ, รสชาติหมักเกลือ 3%, ความสะอาดโรงอบปิด

  2. น้องพิม (แผนกรับออเดอร์และการเงิน): ตรวจจับที่อยู่ เบอร์โทร ออกรหัส PKF-xxxx บันทึกลง Supabase และยิงแจ้งเตือนเข้า Telegram @pakhem_fish_bot

  3. พี่วิน (ฝ่ายจัดส่งและคลังห้องเย็น): ชี้แจงรอบจัดส่งรถเย็น Inter Express และวิธีแช่ฟรีซ 6 เดือน

  4. ป้าเข็ม (เจ้าของร้าน & VIP): ดูแลเคลมสินค้า, ขายส่ง 50 กก., โอนสายหาคนจริง (Human-in-the-Loop) ผ่าน Telegram

"""



import hashlib

import hmac

import json

import logging

import os

import re

import time

from datetime import datetime



import httpx

from fastapi import APIRouter, HTTPException, Request, Response

from app.services.sales_status import closed_notice, is_sales_closed, mask_sales_text
from app.services.fb_chat_only import build_friendly_chat_reply, is_fb_chat_only_mode

from app.services.thai_address_validator import (

    build_incomplete_order_guidance,

    calculate_shipping_route_info,

    enrich_thai_address,

    has_complete_thai_address,

    insert_tambon_into_address,

    lookup_thai_area_by_name,

    lookup_thai_zip,

    normalize_thai_digits,

    validate_thai_phone,

)



logger = logging.getLogger("FacebookBot")



# Environment configurations

FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET") or "mock_facebook_app_secret"

FACEBOOK_VERIFY_TOKEN = os.getenv("FACEBOOK_VERIFY_TOKEN") or "pakhem_fish_verify_2026"

FACEBOOK_PAGE_ACCESS_TOKEN = (

    os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

    or "REDACTED_SECRET"

)

FACEBOOK_PAGE_2_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_2_ACCESS_TOKEN") or ""



TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8939151149:AAGrVkCv0xZrlvtRPO8mzelOYsp5ah5M13U")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6734965582")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://usqhvujqmnxqrdoovvnp.supabase.co")

SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY", "")



WEB_STORE_URL = "https://watt29.github.io/pakhem-shop/fish.html"

LINE_OA_URL = "https://line.me/R/ti/p/@137gsref"



# ความจำระยะสั้นของบทสนทนา (ชื่อ/บริบทที่ลูกค้าแจ้งไว้)

_RECENT_SLIPS: dict[str, dict] = {}

_RECENT_CONTEXT: dict[str, dict] = {}

# Anti-spam debounce: เก็บ timestamp ล่าสุดที่ส่ง handoff message ให้แต่ละ sender (60 วิ cooldown)
_RECENT_HANDOFF_USERS: dict[str, float] = {}
_HANDOFF_COOLDOWN_SECONDS = 60





def _get_page_label(page_id: str = "") -> str:

    """คืนชื่อเพจภาษาไทยให้ชัดเจนว่ามาจากเพจไหน"""

    pid = str(page_id or "").strip()

    if pid == "1323469404180656":

        return "เพจ 2: ครัวแม่บ้าน ชี้เป้าของอร่อย (1323469404180656)"

    if pid == "1307380735783361":

        return "เพจ 1: ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้ (1307380735783361)"

    return f"เพจป้าเข็ม ({pid})" if pid else "เพจ 1: ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้"





def _get_page_token(page_id: str = "") -> str:

    """เลือก Page Access Token ให้ตรงกับเพจที่ลูกค้าทักเข้ามา (เพจ 1 หรือ เพจ 2)"""

    if page_id == "1323469404180656" and FACEBOOK_PAGE_2_ACCESS_TOKEN:

        return FACEBOOK_PAGE_2_ACCESS_TOKEN

    raw_pages = os.getenv("FACEBOOK_PAGES_JSON", "").strip()

    if raw_pages and page_id:

        try:

            for p in json.loads(raw_pages):

                if str(p.get("id") or p.get("page_id") or "") == str(page_id) and p.get("token"):

                    return str(p["token"])

        except Exception:

            pass

    return FACEBOOK_PAGE_ACCESS_TOKEN





KRUNGTHAI_QR_IMAGE_URL = "https://watt29.github.io/pakhem-shop/krungthai_promptpay_qr.png?v=20261030"

KRUNGTHAI_ACCOUNT_DIGITS = "0380253631"





def _send_fb_plain_text(recipient_id: str, text: str, quick_replies: list | None = None, page_id: str = "") -> bool:

    """ส่งข้อความตัวอักษรล้วน (ไม่ห่อด้วย Button Template) เพื่อให้ผู้สูงอายุแตะค้างคัดลอกเลขบัญชี 0380253631 ได้ทันที"""
    text = mask_sales_text(text)

    token = _get_page_token(page_id)

    if not token:

        return False

    try:

        msg_obj: dict = {"text": text}

        if quick_replies:

            msg_obj["quick_replies"] = quick_replies

        r = httpx.post(

            "https://graph.facebook.com/v21.0/me/messages",

            params={"access_token": token},

            json={

                "recipient": {"id": recipient_id},

                "messaging_type": "RESPONSE",

                "message": msg_obj,

            },

            timeout=10,

        )

        return r.status_code == 200

    except Exception as e:

        logger.warning(f"[facebook] send plain text error: {e}")

        return False





def _send_fb_image(recipient_id: str, image_url: str, page_id: str = "") -> bool:
    """[DISABLED BY POLICY] ปิดการส่งภาพในแชท Messenger ทุกกรณีตามคำสั่งเจ้าของร้าน"""
    logger.info(f"[facebook] Chat image blocked by policy for {recipient_id}")
    return False


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
    {"content_type": "text", "title": "⭐ รับ 1 กก. (ขายดี)", "payload": "QR_PKG_1KG"},
    {"content_type": "text", "title": "📦 ลองชิม 500g", "payload": "QR_PKG_500G"},
    {"content_type": "text", "title": "❄️ ชุดตุน 2 กก.รถเย็น", "payload": "QR_PKG_2KG"},
]





def _reply_to_facebook(recipient_id: str, text: str, quick_replies: list | None = None, page_id: str = "") -> bool:

    """ส่งข้อความพร้อมปุ่มกดถาวร (Button Template) และ Quick Replies กลับเข้า Messenger ของผู้ใช้ผ่าน Meta Graph Send API"""
    text = mask_sales_text(text)

    token = _get_page_token(page_id)

    if not token:

        logger.warning("[facebook] Missing Page Access Token")

        return False

    try:

        if quick_replies:

            tpl_buttons = [

                {

                    "type": "postback",

                    "title": str(b.get("title") or "")[:20],

                    "payload": str(b.get("payload") or "QR_PKG_1KG"),

                }

                for b in quick_replies[:3]

                if b.get("title") and b.get("payload")

            ]

            if tpl_buttons and len(text) <= 600:

                r_tpl = httpx.post(

                    "https://graph.facebook.com/v21.0/me/messages",

                    params={"access_token": token},

                    json={

                        "recipient": {"id": recipient_id},

                        "messaging_type": "RESPONSE",

                        "message": {

                            "attachment": {

                                "type": "template",

                                "payload": {

                                    "template_type": "button",

                                    "text": text,

                                    "buttons": tpl_buttons,

                                },

                            },

                            "quick_replies": quick_replies,

                        },

                    },

                    timeout=10,

                )

                if r_tpl.status_code == 200:

                    return True

            elif tpl_buttons and len(text) > 600:

                httpx.post(

                    "https://graph.facebook.com/v21.0/me/messages",

                    params={"access_token": token},

                    json={

                        "recipient": {"id": recipient_id},

                        "messaging_type": "RESPONSE",

                        "message": {"text": text},

                    },

                    timeout=10,

                )

                r_card = httpx.post(

                    "https://graph.facebook.com/v21.0/me/messages",

                    params={"access_token": token},

                    json={

                        "recipient": {"id": recipient_id},

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

                            "quick_replies": quick_replies,

                        },

                    },

                    timeout=10,

                )

                if r_card.status_code == 200:

                    return True



        msg_obj: dict = {"text": text}

        if quick_replies:

            msg_obj["quick_replies"] = quick_replies

        r = httpx.post(

            "https://graph.facebook.com/v21.0/me/messages",

            params={"access_token": token},

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

                params={"access_token": token},

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





def _lookup_previous_customer_address(sender: str, phone: str = "") -> dict | None:

    """ค้นหาชื่อ-เบอร์-ที่อยู่เดิมของลูกค้าจากหน่วยความจำหรือ Supabase direct_orders / ad_leads (เหมือน LINE OA lookupPreviousOrderAddress)"""

    ctx = _RECENT_CONTEXT.get(sender) or {}

    if ctx.get("saved_address") and ctx.get("saved_phone"):

        if has_complete_thai_address(ctx["saved_address"]) and validate_thai_phone(ctx["saved_phone"])["valid"]:

            return {

                "customer_name": ctx.get("saved_name") or f"ลูกค้า Facebook ({sender[:6]})",

                "phone": ctx["saved_phone"],

                "address": enrich_thai_address(ctx["saved_address"]),

            }

    if not SUPABASE_URL or not SUPABASE_KEY:

        return None

    try:

        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

        params = {

            "order": "id.desc",

            "limit": 1,

            "select": "customer_name,phone,address",

        }

        if phone and validate_thai_phone(phone)["valid"]:

            params["phone"] = f"eq.{phone}"

        elif sender:

            params["note"] = f"ilike.*{sender[:14]}*"

        else:

            return None

        r = httpx.get(f"{SUPABASE_URL}/rest/v1/direct_orders", params=params, headers=headers, timeout=5)

        if r.status_code == 200 and r.json():

            row = r.json()[0]

            addr = enrich_thai_address(str(row.get("address") or "").strip())

            ph = str(row.get("phone") or "").strip()

            if has_complete_thai_address(addr) and validate_thai_phone(ph)["valid"]:

                return {

                    "customer_name": str(row.get("customer_name") or f"ลูกค้า Facebook ({sender[:6]})").strip(),

                    "phone": validate_thai_phone(ph)["phone"],

                    "address": addr,

                }

    except Exception as e:

        logger.warning(f"[facebook] lookup previous customer address error: {e}")

    return None





def _fetch_fb_profile_name(sender: str, page_id: str = "") -> str:

    """ดึงชื่อโปรไฟล์ Facebook ของผู้สูงอายุอัตโนมัติ เพื่อไม่ต้องให้ลูกค้าพิมพ์ชื่อผู้รับซ้ำ"""

    token = _get_page_token(page_id)

    if not token or not sender or len(token) < 30:

        return ""

    try:

        r = httpx.get(

            f"https://graph.facebook.com/v21.0/{sender}",

            params={"fields": "name,first_name,last_name", "access_token": token},

            timeout=2.5,

        )

        if r.status_code == 200:

            data = r.json()

            full_n = str(data.get("name") or "").strip()

            if full_n:

                return full_n

    except Exception:

        pass

    return ""





def _handle_event(event: dict, page_id: str = "") -> None:

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

    if is_fb_chat_only_mode():
        postback = event.get("postback") or {}
        postback_title = (postback.get("title") or "").strip()
        if not text and not attachments and not postback:
            return
        profile_name = ""
        try:
            profile_name = _fetch_fb_profile_name(sender, page_id=page_id)
        except Exception:
            profile_name = ""
        reply_text = build_friendly_chat_reply(
            text or postback_title,
            sender_name=profile_name,
            channel="messenger",
        )
        _reply_to_facebook(sender, reply_text, quick_replies=None, page_id=page_id)
        return

    # โค้ดขาย/ออเดอร์/สลิปเดิมถูกลบออกทั้งก้อนแล้ว (ร้านยุติการจำหน่าย)
    return







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

        entry_page_id = str(entry.get("id") or "")

        for event in entry.get("messaging", []):

            _handle_event(event, page_id=entry_page_id)

    return "OK"

