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

import time

from datetime import datetime



import httpx

from fastapi import APIRouter, HTTPException, Request, Response

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



# ความจำระยะสั้นสำหรับผูกสลิปโอนเงินและชุดที่ลูกค้าเพิ่งกดเลือก (ป้องกันลงเป็น COD มั่วหรือผิดขนาดชุด)

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





def _save_pending_slip(sender: str, amount_val: float, slip_url: str, ocr_text: str, receiver_ok: bool) -> None:

    """บันทึกสถานะว่าลูกค้าเพิ่งส่งรูปสลิป (ทั้งใน RAM และ Supabase system_preferences) เพื่อผูกกับที่อยู่ในข้อความถัดไป"""

    data = {

        "amount": amount_val,

        "slip_url": slip_url,

        "ocr_text": ocr_text[:300],

        "receiver_ok": receiver_ok,

        "ts": time.time(),

    }

    _RECENT_SLIPS[sender] = data

    if SUPABASE_URL and SUPABASE_KEY:

        try:

            headers = {

                "apikey": SUPABASE_KEY,

                "Authorization": f"Bearer {SUPABASE_KEY}",

                "Content-Type": "application/json",

                "Prefer": "resolution=merge-duplicates,return=minimal",

            }

            httpx.post(

                f"{SUPABASE_URL}/rest/v1/system_preferences",

                headers=headers,

                json={"key": f"fb_slip_{sender}", "value": json.dumps(data, ensure_ascii=False)},

                timeout=6,

            )

        except Exception as e:

            logger.warning(f"[facebook] save pending slip error: {e}")





def _get_pending_slip(sender: str) -> dict | None:

    """ดึงข้อมูลสลิปที่ลูกค้าเพิ่งส่งภายใน 24 ชม."""

    now = time.time()

    mem = _RECENT_SLIPS.get(sender)

    if mem and (now - float(mem.get("ts") or 0)) < 86400:

        return mem

    if SUPABASE_URL and SUPABASE_KEY:

        try:

            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

            r = httpx.get(

                f"{SUPABASE_URL}/rest/v1/system_preferences",

                params={"key": f"eq.fb_slip_{sender}", "select": "value"},

                headers=headers,

                timeout=6,

            )

            if r.status_code == 200 and r.json():

                val = json.loads(r.json()[0].get("value") or "{}")

                if (now - float(val.get("ts") or 0)) < 86400:

                    _RECENT_SLIPS[sender] = val

                    return val

        except Exception:

            pass

    return None





def _clear_pending_slip(sender: str) -> None:

    """ล้างสถานะสลิปค้างเมื่อผูกกับคำสั่งซื้อเรียบร้อยแล้ว"""

    _RECENT_SLIPS.pop(sender, None)

    if SUPABASE_URL and SUPABASE_KEY:

        try:

            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

            httpx.delete(

                f"{SUPABASE_URL}/rest/v1/system_preferences",

                params={"key": f"eq.fb_slip_{sender}"},

                headers=headers,

                timeout=6,

            )

        except Exception:

            pass





def _attach_slip_to_recent_order(sender: str, amount_val: float, slip_url: str, receiver_ok: bool) -> dict | None:

    """กรณีลูกค้าพิมพ์ชื่อ-ที่อยู่-เบอร์โทรสั่งมาก่อน แล้วค่อยส่งรูปสลิปตามมา -> อัปเดตออเดอร์ล่าสุดใน direct_orders เป็นโอนเงินทันที"""

    if not SUPABASE_URL or not SUPABASE_KEY:

        return None

    try:

        headers = {

            "apikey": SUPABASE_KEY,

            "Authorization": f"Bearer {SUPABASE_KEY}",

            "Content-Type": "application/json",

        }

        r = httpx.get(

            f"{SUPABASE_URL}/rest/v1/direct_orders",

            params={

                "note": f"ilike.*{sender[:12]}*",

                "order": "id.desc",

                "limit": 1,

                "select": "id,order_code,package_name,price,payment_method,note",

            },

            headers=headers,

            timeout=8,

        )

        if r.status_code == 200 and r.json():

            order = r.json()[0]

            oid = order.get("id")

            pkg_name = order.get("package_name") or ""

            # ปรับยอดเป็นราคาโอนส่งฟรี หรือราคาโอนส่งรถห้องเย็น (+100) ตามขนาดชุดหรือตามยอดสลิป

            if amount_val >= 1000 or "2" in pkg_name:

                new_price = 1090.0

            elif 470 <= amount_val <= 510:

                new_price = 490.0

            elif 630 <= amount_val <= 680:

                new_price = 650.0

            elif (350 <= amount_val <= 430) or "500" in pkg_name:

                new_price = 390.0

            else:

                new_price = 550.0

            check_tag = "รอแอดมินตรวจยอดเงินเข้า" if receiver_ok else "⚠️ รอแอดมินตรวจชื่อผู้รับและยอดเงิน"

            amt_label = f"{amount_val:,.0f}.-" if amount_val > 0 else "แนบสลิปแล้ว"

            new_pay = f"โอนเงิน ({amt_label} {check_tag}) 🏦"

            new_note = f"{order.get('note') or ''} [SLIP:{slip_url}]".strip()

            httpx.patch(

                f"{SUPABASE_URL}/rest/v1/direct_orders",

                params={"id": f"eq.{oid}"},

                headers=headers,

                json={"price": new_price, "payment_method": new_pay, "note": new_note},

                timeout=8,

            )

            order["price"] = new_price

            order["payment_method"] = new_pay

            return order

    except Exception as e:

        logger.warning(f"[facebook] attach slip to recent order failed: {e}")

    return None





def _switch_recent_order_to_cod(sender: str, pkg_code: str = "1kg") -> dict | None:

    """กรณีลูกค้าสั่งแบบโอนเงินไปแล้ว แต่กดปุ่มขอเปลี่ยนเป็นเก็บเงินปลายทาง (COD) ในพื้นที่ส่งถึงใน 1-2 วัน"""

    if not SUPABASE_URL or not SUPABASE_KEY:

        return None

    try:

        headers = {

            "apikey": SUPABASE_KEY,

            "Authorization": f"Bearer {SUPABASE_KEY}",

            "Content-Type": "application/json",

        }

        r = httpx.get(

            f"{SUPABASE_URL}/rest/v1/direct_orders",

            params={

                "note": f"ilike.*{sender[:12]}*",

                "order": "id.desc",

                "limit": 1,

                "select": "id,order_code,package_name,price,payment_method,note",

            },

            headers=headers,

            timeout=8,

        )

        if r.status_code == 200 and r.json():

            order = r.json()[0]

            oid = order.get("id")

            pkg_name = order.get("package_name") or ""

            new_price = 410.0 if ("500" in pkg_name or pkg_code == "500g") else 570.0

            new_pay = "เก็บเงินปลายทาง (COD) 💵"

            httpx.patch(

                f"{SUPABASE_URL}/rest/v1/direct_orders",

                params={"id": f"eq.{oid}"},

                headers=headers,

                json={"price": new_price, "payment_method": new_pay},

                timeout=8,

            )

            order["price"] = new_price

            order["payment_method"] = new_pay

            return order

    except Exception as e:

        logger.warning(f"[facebook] switch recent order to cod failed: {e}")

    return None





KRUNGTHAI_QR_IMAGE_URL = "https://watt29.github.io/pakhem-shop/krungthai_promptpay_qr.png?v=20261030"

KRUNGTHAI_ACCOUNT_DIGITS = "0380253631"





def _send_fb_plain_text(recipient_id: str, text: str, quick_replies: list | None = None, page_id: str = "") -> bool:

    """ส่งข้อความตัวอักษรล้วน (ไม่ห่อด้วย Button Template) เพื่อให้ผู้สูงอายุแตะค้างคัดลอกเลขบัญชี 0380253631 ได้ทันที"""

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





def _save_order_to_supabase(

    order_code: str,

    name: str,

    phone: str,

    address: str,

    pkg: str,

    price: float,

    payment_method: str,

    sender: str = "",

    extra_note: str = "",

    page_id: str = "",

) -> bool:

    """บันทึกออเดอร์ใหม่จาก Facebook ลง Supabase direct_orders พร้อมติดแท็ก [FB_ID:...] และชื่อเพจเพื่อแจ้งเลขพัสดุอัตโนมัติ"""

    if not SUPABASE_URL or not SUPABASE_KEY:

        return False

    address = enrich_thai_address(address)

    if not validate_thai_phone(phone)["valid"] or not has_complete_thai_address(address):

        logger.warning(f"[facebook] blocked incomplete order save: phone={phone} address={address}")

        return False

    try:

        headers = {

            "apikey": SUPABASE_KEY,

            "Authorization": f"Bearer {SUPABASE_KEY}",

            "Content-Type": "application/json",

            "Prefer": "return=minimal",

        }

        page_label = _get_page_label(page_id)

        note_str = f"สั่งซื้อผ่าน Facebook ({page_label}) [FB_ID:{sender}] {extra_note}".strip() if sender else f"สั่งซื้อผ่าน Facebook ({page_label})"

        payload = {

            "order_code": order_code,

            "product_name": "ปลาสลิดแดดเดียว ไซส์จัมโบ้ 4–6 ตัว/กก. ป้าเข็ม คัดพิเศษ",

            "package_code": "500g" if "500" in pkg else ("2kg" if "2" in pkg else "1kg"),

            "package_name": pkg,

            "price": price,

            "customer_name": name,

            "phone": phone,

            "address": address,

            "payment_method": payment_method,

            "status": "PENDING",

            "note": note_str,

            "created_at": datetime.now().isoformat(),

        }

        r = httpx.post(f"{SUPABASE_URL}/rest/v1/direct_orders", headers=headers, json=payload, timeout=8)

        return r.status_code in (200, 201)

    except Exception as e:

        logger.warning(f"[facebook] supabase insert failed: {e}")

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





def _prompt_tambon_or_house_after_zip(sender: str, recent_ctx: dict, page_id: str = "", header_prefix: str = "") -> None:

    """เมื่อทราบรหัสไปรษณีย์และเลือกวิธีชำระเงินแล้ว -> เด้งปุ่มเลือกตำบล (ถ้ามีหลายตำบล) หรือถามบ้านเลขที่ทันที"""

    zip_code = recent_ctx.get("zip_code") or ""

    zip_info = lookup_thai_zip(zip_code) if zip_code else lookup_thai_area_by_name(recent_ctx.get("saved_address") or "")

    saved_addr = recent_ctx.get("saved_address") or ""

    route = calculate_shipping_route_info(saved_addr)

    prefix_block = f"{header_prefix}\n━━━━━━━━━━━━━━━━━━\n" if header_prefix else ""



    if zip_info:

        d_prefix = "" if zip_info["amphoe"].startswith("เขต") else ("เขต" if zip_info["is_bkk"] else "อ.")

        p_prefix = "" if zip_info["is_bkk"] else "จ."

        t_prefix = "แขวง" if zip_info["is_bkk"] else "ต."

        tambons = zip_info["tambons"] or []

        has_sub_already = bool(re.search(r"(?:ต\.|ตำบล|แขวง)", saved_addr))

        if not has_sub_already and len(tambons) > 1:

            recent_ctx["waiting_tambon"] = True

            recent_ctx["addr_step"] = "WAIT_TAMBON"

            recent_ctx["ts"] = time.time()

            _RECENT_CONTEXT[sender] = recent_ctx

            tambon_qrs = [

                {

                    "content_type": "text",

                    "title": f"{t_prefix}{t}"[:20],

                    "payload": f"QR_TAMBON_{t}",

                }

                for t in tambons[:13]

            ]

            tambon_list_txt = " / ".join(f"{idx+1}.{t_prefix}{t}" for idx, t in enumerate(tambons))

            _reply_to_facebook(

                sender,

                f"{prefix_block}📍 พื้นที่: {d_prefix}{zip_info['amphoe']} {p_prefix}{zip_info['province']} {zip_info['zip']}\n"

                f"📌 มี{t_prefix}ดังนี้ค่ะ: {tambon_list_txt}\n\n"

                f"👇 กดปุ่มเลือก '{t_prefix}' ด้านล่าง (หรือพิมพ์ชื่อตำบล) ได้เลยค่ะ:",

                tambon_qrs,

                page_id=page_id,

            )

            return



    recent_ctx["waiting_tambon"] = False

    recent_ctx["addr_step"] = "WAIT_HOUSE"

    recent_ctx["ts"] = time.time()

    _RECENT_CONTEXT[sender] = recent_ctx

    _reply_to_facebook(

        sender,

        f"{prefix_block}📍 พื้นที่จัดส่ง: {saved_addr}\n"

        f"{route['summary_line']}\n"

        f"━━━━━━━━━━━━━━━━━━\n"

        f"🏠 ขั้นต่อไป (บ้านเลขที่) :\n"

        f"👉 พิมพ์ 'บ้านเลขที่ / หมู่ / ซอย / ถนน' (เช่น 99/1 หมู่ 2) ส่งมาได้เลยค่ะ:",

        [{"content_type": "text", "title": "🔄 เปลี่ยนรหัสไปรษณีย์", "payload": "QR_NEW_ADDR"}],

        page_id=page_id,

    )





def _prompt_payment_choice_for_area(sender: str, recent_ctx: dict, area_str: str, route: dict, page_id: str = "") -> None:

    """ขั้นที่ 2 (เหมือน LINE OA 2/5): แจ้งระยะทาง + เวลาจัดส่งตามรหัสไปรษณีย์จริง แล้วแสดงปุ่มวิธีชำระเงินตามเงื่อนไขพื้นที่:

    - พื้นที่ 1-2 วัน (<= 350 กม. allow_cod=True): เลือกได้ทั้ง โอนส่งฟรี (390/550) หรือ เก็บเงินปลายทาง COD (+20 = 410/570)

    - พื้นที่ 3-4 วัน (> 350 กม. allow_cod=False): จัดส่งด้วยรถห้องเย็น ขอสงวนสิทธิ์รับเฉพาะโอนเงินล่วงหน้า (งด COD!)

    """

    pkg_code = recent_ctx.get("pkg") or "1kg"

    allow_cod = route["allow_cod"]

    recent_ctx["addr_step"] = "WAIT_PAY_AFTER_ZIP"

    recent_ctx["ts"] = time.time()

    _RECENT_CONTEXT[sender] = recent_ctx



    if pkg_code == "500g":

        pkg_title = "ชุดทดลอง 500 กรัม (2–3 ตัวใหญ่)"

        tr_price, cod_price, cold_price = 390, 410, 490

        tr_qr, cod_qr, cold_qr = "QR_TRF_500G", "QR_COD_500G", "QR_COLD_500G"

    else:

        pkg_title = "ชุดขายดีสุดคุ้ม 1 กิโลกรัม (4–6 ตัวใหญ่) ⭐"

        tr_price, cod_price, cold_price = 550, 570, 650

        tr_qr, cod_qr, cold_qr = "QR_TRF_1KG", "QR_COD_1KG", "QR_COLD_1KG"



    saved_ph = recent_ctx.get("saved_phone") or ""

    saved_nm = recent_ctx.get("saved_name") or ""

    phone_line = f"📞 เบอร์โทรผู้รับ: {saved_ph}{f' ({saved_nm})' if saved_nm else ''}\n" if saved_ph else ""

    cta_line = (

        "👇 กดปุ่มเลือกวิธีชำระเงินด้านล่างเพื่อยืนยันออกรหัสคำสั่งซื้อทันทีค่ะ:"

        if saved_ph

        else "👇 กดปุ่มเลือกวิธีชำระเงินด้านล่างได้เลยค่ะ:"

    )



    if True:

        msg = (

            f"📍 ที่อยู่จัดส่ง: {area_str}\n"

            f"{phone_line}"

            f"{route['summary_line']}\n"

            f"✅ โอนเงินส่งฟรีด่วนพิเศษ EMS + ซองฟอยล์เก็บความเย็น (มูลค่า 82 บาท) ฟรีทุกกล่อง!\n"

            f"(เนื่องจากเป็นอาหารสดแช่แข็ง -18°C ทางร้านจึงจัดส่งหลังรับยอดโอน เพื่อการันตีปลาสดใหม่ ไม่เน่าเสียจากการตกค้างค่ะ)\n"

            f"━━━━━━━━━━━━━━━━━━\n"

            f"🐟 {pkg_title}:\n"

            f"• 🏦 ยอดโอนชำระ: {tr_price} บาท (ส่งฟรีถึงหน้าบ้าน!)\n"

            f"{cta_line}"

        )

        qrs = [

            {"content_type": "text", "title": f"🏦 ยืนยันยอดโอน {tr_price}.-", "payload": tr_qr},

            {"content_type": "text", "title": "📋 คัดลอกเลขบัญชี", "payload": "QR_COPY_ACC"},

            {"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"},

        ]

    else:

        msg = (

            f"📍 ที่อยู่จัดส่ง: {area_str}\n"

            f"{phone_line}"

            f"{route['summary_line']}\n"

            f"❄️ พื้นที่ใช้เวลาขนส่ง 3–4 วัน ทางร้านจัดส่งด้วยรถควบคุมอุณหภูมิ (รถห้องเย็น) เพื่อรักษาความสดใหม่\n"

            f"⚠️ ขอสงวนสิทธิ์จัดส่งหลังได้รับยอดโอนชำระแล้ว (งดเก็บเงินปลายทาง COD ในพื้นที่นี้ค่ะ)\n"

            f"━━━━━━━━━━━━━━━━━━\n"

            f"🐟 {pkg_title}:\n"

            f"• ❄️ โอนส่งรถห้องเย็นควบคุมอุณหภูมิ: {cold_price} บาท\n"

            f"• 🏦 โอนส่งแพ็กฟอยล์เก็บอุณหภูมิ: {tr_price} บาท (ส่งฟรี!)\n"

            f"{cta_line}"

        )

        qrs = [

            {"content_type": "text", "title": f"❄️ รถห้องเย็น {cold_price}.-", "payload": cold_qr},

            {"content_type": "text", "title": f"🏦 โอนส่งฟรี {tr_price}.-", "payload": tr_qr},

            {"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"},

        ]

    _reply_to_facebook(sender, msg, qrs, page_id=page_id)





def _prompt_address_step_1_or_saved(

    sender: str,

    pkg_code: str,

    pay_mode: str | None,

    summary_header: str,

    switch_qrs: list[dict],

    page_id: str = "",

    force_new_addr: bool = False,

) -> None:

    """เริ่มตัวนำทางที่อยู่จัดส่งแบบ LINE OA: เช็คที่อยู่เดิมก่อน ถ้าไม่มีให้เริ่มถามรหัสไปรษณีย์ 5 หลักทีละขั้น"""

    prev = None if force_new_addr else _lookup_previous_customer_address(sender)

    if prev:

        route = calculate_shipping_route_info(prev["address"])

        _RECENT_CONTEXT[sender] = {

            "pkg": pkg_code,

            "pay": pay_mode,

            "saved_name": prev["customer_name"],

            "saved_phone": prev["phone"],

            "saved_address": prev["address"],

            "house_filled": True,

            "waiting_tambon": False,

            "addr_step": "CONFIRM_SAVED",

            "ts": time.time(),

        }

        msg = (

            f"{summary_header}\n"

            f"━━━━━━━━━━━━━━━━━━\n"

            f"💚 พบที่อยู่จัดส่งเดิมของคุณลูกค้าในระบบค่ะ:\n"

            f"👤 ผู้รับ: {prev['customer_name']} ({prev['phone']})\n"

            f"🏠 ที่อยู่: {prev['address']}\n"

            f"{route['summary_line']}\n\n"

            f"👇 กดปุ่ม '✅ ใช้ที่อยู่เดิมนี้' เพื่อยืนยันสั่งซื้อได้ในคลิกเดียวเลยค่ะ:"

        )

        qrs = [

            {"content_type": "text", "title": "✅ ใช้ที่อยู่เดิมนี้", "payload": "QR_USE_SAVED_ADDR"},

            {"content_type": "text", "title": "✏️ เปลี่ยนที่อยู่ใหม่", "payload": "QR_NEW_ADDR"},

            {"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"},

        ]

        _reply_to_facebook(sender, msg, qrs, page_id=page_id)

        return



    _RECENT_CONTEXT[sender] = {

        "pkg": pkg_code,

        "pay": pay_mode,

        "addr_step": "WAIT_ZIP",

        "house_filled": False,

        "waiting_tambon": False,

        "ts": time.time(),

    }

    msg = (

        f"{summary_header}\n"

        f"━━━━━━━━━━━━━━━━━━\n"

        f"📮 แจ้งที่อยู่จัดส่งง่ายๆ (ขั้นที่ 1/3):\n"

        f"• พิมพ์ 'รหัสไปรษณีย์ 5 หลัก' (เช่น 10240) หรือพิมพ์ 'ชื่ออำเภอ/เขต' ก็ได้จ้ะ\n"

        f"• 📸 หรือถ่ายรูป 'หน้าซองจดหมาย / กล่องพัสดุ' ส่งมาให้ป้าเข็มพิมพ์ให้ได้เลยจ้า 😊"

    )

    _reply_to_facebook(sender, msg, switch_qrs, page_id=page_id)





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





def _finalize_facebook_order(

    sender: str,

    full_address: str,

    phone: str,

    recent_ctx: dict,

    page_id: str = "",

    customer_name: str = "",

    raw_hint_text: str = "",

) -> None:

    """สร้างออเดอร์ PKF-... ลง Supabase direct_orders พร้อมส่งใบเสร็จแจ้งระยะทางจัดส่ง และแจ้งเตือน Telegram"""

    addr_clean = enrich_thai_address(full_address)

    lower_hint = f"{raw_hint_text} {addr_clean}".lower()

    pending_slip = _get_pending_slip(sender)

    route_info = calculate_shipping_route_info(addr_clean)



    is_english = any(w in lower_hint for w in ["english", "hello", "please", "room", "soi", "road", "bangkok", "condo", "tel:", "phone:", "set 1", "set 2", "set 3", "how much", "how to buy"]) or (len(re.findall(r"[a-zA-Z]", lower_hint)) > len(re.findall(r"[ก-๙]", lower_hint)) and len(lower_hint) > 10)

    explicit_cod = any(k in lower_hint for k in ["ปลายทาง", "เก็บเงินปลายทาง", "cod", "cash on delivery"])

    explicit_transfer = any(k in lower_hint for k in ["โอน", "สลิป", "พร้อมเพย์", "จ่ายแล้ว", "transfer", "bank transfer", "promptpay"]) and not explicit_cod

    is_transfer = (

        bool(pending_slip)

        or explicit_transfer

        or (recent_ctx.get("pay") == "transfer" and not explicit_cod)

        or (not route_info["allow_cod"])

    )



    slip_amt = float((pending_slip or {}).get("amount") or 0.0)

    ctx_pkg = recent_ctx.get("pkg")



    if any(k in lower_hint for k in ["500", "พอดีมื้อ", "ครึ่งโล", "ครึ่งกิโล", "ชุด 1", "ชุด1", "set 1", "set1", "3 ตัว", "390", "410"]):

        pkg_code = "500g"

    elif any(k in lower_hint for k in ["2 กิโล", "2กิโล", "2 กก", "2กก", "สองโล", "2kg", "2 โล", "ชุด 3", "ชุด3", "set 3", "set3", "1090", "1,090"]):

        pkg_code = "2kg"

    elif any(k in lower_hint for k in ["1 กิโล", "1กิโล", "1 กก", "1กก", "1kg", "1 โล", "หนึ่งกิโล", "ชุด 2", "ชุด2", "set 2", "set2", "550", "570"]):

        pkg_code = "1kg"

    elif slip_amt >= 1000:

        pkg_code = "2kg"

    elif 470 <= slip_amt <= 510:

        pkg_code = "500g"

        recent_ctx["pay"] = "cold_truck"

    elif 630 <= slip_amt <= 680:

        pkg_code = "1kg"

        recent_ctx["pay"] = "cold_truck"

    elif 350 <= slip_amt <= 430:

        pkg_code = "500g"

    elif slip_amt >= 500:

        pkg_code = "1kg"

    elif ctx_pkg in ("500g", "1kg", "2kg"):

        pkg_code = ctx_pkg

    else:

        pkg_code = "1kg"



    wants_cold_truck = (recent_ctx.get("pay") == "cold_truck")

    if pkg_code == "500g":

        if wants_cold_truck:

            pkg_name = "ชุดพอดีมื้อ 450-500 กรัม (ประมาณ 2 ตัวจัมโบ้) [ส่งรถห้องเย็น]"

            price = 490.0

            is_transfer = True

        else:

            pkg_name = "ชุดพอดีมื้อ 450-500 กรัม (ประมาณ 2 ตัวจัมโบ้)"

            price = 390.0 if is_transfer else 410.0

    elif pkg_code == "2kg":

        pkg_name = "ชุดตุนสุดคุ้ม 1.8-2.0 กิโลกรัม (ประมาณ 8 ตัวจัมโบ้)"

        price = 1090.0

        is_transfer = True

    else:

        if wants_cold_truck:

            pkg_name = "ชุดยอดฮิต 900-1,000 กรัม (ประมาณ 4 ตัวจัมโบ้) [ส่งรถห้องเย็น]"

            price = 650.0

            is_transfer = True

        else:

            pkg_name = "ชุดยอดฮิต 900-1,000 กรัม (ประมาณ 4 ตัวจัมโบ้)"

            price = 550.0 if is_transfer else 570.0



    extra_note = ""

    if pending_slip:

        s_url = pending_slip.get("slip_url") or ""

        r_ok = pending_slip.get("receiver_ok", True)

        check_str = "รอแอดมินตรวจยอดเงินเข้า" if r_ok else "⚠️ รอแอดมินตรวจชื่อผู้รับและยอดเงิน"

        amt_tag = f"{slip_amt:,.0f}.-" if slip_amt > 0 else "แนบสลิปแล้ว"

        payment_method = f"โอนเงิน ({amt_tag} {check_str}) 🏦"

        extra_note = f"[SLIP:{s_url}]"

        _clear_pending_slip(sender)

    elif is_transfer:

        payment_method = "โอนเงินผ่านธนาคาร (รอแนบสลิป/ตรวจยอด) 🏦"

    else:

        payment_method = "เก็บเงินปลายทาง (COD) 💵"



    fb_prof_name = "" if (customer_name or recent_ctx.get("saved_name")) else _fetch_fb_profile_name(sender, page_id)

    final_name = (customer_name or recent_ctx.get("saved_name") or fb_prof_name or f"ลูกค้า Facebook ({sender[:6]})").strip()

    order_code = f"PKF-{datetime.now().strftime('%m%d%H%M%S')}"

    # เก็บที่อยู่และรหัสออเดอร์ล่าสุดไว้ในหน่วยความจำ เพื่อให้สั่งซ้ำหรือกดปุ่มสลับวิธีชำระเงินได้ทันที

    _RECENT_CONTEXT[sender] = {

        "saved_name": final_name,

        "saved_phone": phone,

        "saved_address": addr_clean,

        "last_order_code": order_code,

        "last_pkg": pkg_code,

        "pkg": pkg_code,

        "pay": "transfer" if is_transfer else "cod",

        "house_filled": True,

        "waiting_tambon": False,

        "addr_step": None,

        "ts": time.time(),

    }



    _save_order_to_supabase(

        order_code,

        final_name,

        phone,

        addr_clean,

        pkg_name,

        price,

        payment_method,

        sender=sender,

        extra_note=extra_note,

        page_id=page_id,

    )



    if is_english:

        pkg_name_en = {

            "500g": "Set 1: Sun-Dried Gourami Fish 500g (approx. 2-3 pcs)",

            "1kg": "Set 2: Sun-Dried Gourami Fish 1 kg (approx. 4-6 pcs • Most Popular)",

            "2kg": "Set 3: Sun-Dried Gourami Fish 2 kg (approx. 8-12 pcs • Free Cold-Chain Truck)",

        }.get(pkg_code, "Set 2: Sun-Dried Gourami Fish 1 kg (approx. 4-6 pcs)")

        pay_method_en = "Bank Transfer (Krungthai Bank)" if is_transfer else "Cash on Delivery (COD)"

        reply_msg = (

            f"Thank you for your order! 🙏🐟\n\n"

            f"📦 Order Code: {order_code}\n"

            f"🐟 Item: {pkg_name_en}\n"

            f"💰 Total: {price:,.0f} THB ({pay_method_en})\n"

            f"👤 Recipient: {final_name} ({phone})\n"

            f"📍 Delivery Address:\n{addr_clean}\n"

            f"🚚 Estimated Delivery: {route_info['est_days']} ({route_info['ship_method_short']})\n\n"

            f"We are preparing your fresh package for delivery. Thank you! 😊"

        )

        post_order_qrs = None

        if is_transfer and not pending_slip:

            reply_msg += (

                "\n\n🏦 Payment Details (Bank Transfer / PromptPay):\n"

                "• Bank: Krungthai Bank (สาขาท่าพระ)\n"

                "• Account Number: 038-0-25363-1\n"

                "• Account Name: นายจีรวัฒน์ พลอาจ (Jeerawat Phon-art)\n"

                "📸 Once transferred, please reply with your transfer slip in this chat! 😊"

            )

            post_order_qrs = [

                {"content_type": "text", "title": "📋 Copy Account No", "payload": "0380253631"},

            ]

            if route_info["allow_cod"] and pkg_code != "2kg":

                post_order_qrs.append(

                    {"content_type": "text", "title": "🚚 Switch to COD", "payload": "QR_SWITCH_TO_COD"}

                )

    else:

        reply_msg = (

            f"ขอบพระคุณสำหรับคำสั่งซื้อค่ะ 🙏\n\n"

            f"📦 รหัสคำสั่งซื้อ: {order_code}\n"

            f"🐟 รายการ: {pkg_name}\n"

            f"💰 ยอดรวม: {price:,.0f} บาท ({payment_method})\n"

            f"👤 ผู้รับ: {final_name} ({phone})\n"

            f"📍 ที่อยู่จัดส่ง:\n{addr_clean}\n"

            f"{route_info['summary_line']}\n\n"

            f"🚚 ทางร้านเตรียมแพ็กส่งรอบสดใหม่ให้ถึงหน้าบ้านเลยนะคะ ขอบพระคุณค่ะ 😊"

        )

        post_order_qrs = None

        if is_transfer and not pending_slip:

            reply_msg += (

                "\n\n🏦 ช่องทางโอนชำระเงิน:\n"

                "• ธนาคารกรุงไทย (สาขาท่าพระ)\n"

                "• เลขที่บัญชี: 038-0-25363-1\n"

                "• ชื่อบัญชี: นายจีรวัฒน์ พลอาจ\n"

                "📸 (โอนแล้วส่งรูปสลิปในแชทนี้ได้เลยจ้ะ 👇 แตะค้างที่เลขบัญชีด้านล่างเพื่อคัดลอกได้ทันทีค่ะ)"

            )

            post_order_qrs = [

                {"content_type": "text", "title": "📋 คัดลอกเลขบัญชี", "payload": "QR_COPY_ACC"},

            ]

            if route_info["allow_cod"] and pkg_code != "2kg":

                post_order_qrs.append(

                    {"content_type": "text", "title": "🚚 เปลี่ยนเป็นปลายทาง", "payload": "QR_SWITCH_TO_COD"}

                )



    page_label = _get_page_label(page_id)

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    _reply_to_facebook(sender, reply_msg, post_order_qrs, page_id=page_id)

    if is_transfer and not pending_slip:

        _send_fb_image(sender, KRUNGTHAI_QR_IMAGE_URL, page_id=page_id)

        _send_fb_plain_text(sender, KRUNGTHAI_ACCOUNT_DIGITS, post_order_qrs, page_id=page_id)

    _send_telegram_alert(

        f"🐟 [ออเดอร์ใหม่จาก Facebook!] 🔔\n"

        f"🏠 เพจ: {page_label}\n"

        f"🔖 รหัส: {order_code}\n"

        f"👤 ผู้รับ: {final_name}\n"

        f"📞 เบอร์: {phone}\n"

        f"📦 สินค้า: {pkg_name}\n"

        f"💰 ยอด: {price:,.0f} บาท ({payment_method})\n"

        f"📍 ที่อยู่:\n{addr_clean}\n"

        f"{route_info['summary_line']}\n"

        f"⏰ เวลา: {now_str}"

    )





def _analyze_image_with_groq_vision(img_url: str) -> dict:

    """ใช้ Groq Vision (qwen/qwen3.8-27b) อ่านรูปภาพบน Cloud Render โดยไม่กินแรมเครื่อง"""

    res = {"category": "other", "extracted_text": "", "amount": "", "receiver_name": ""}

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

            "2. ถ้าเป็นสลิปโอนเงินธนาคารที่มีรายการโอนสำเร็จ ให้ตอบ category='slip' พร้อมระบุตัวเลขยอดเงินใน amount และชื่อผู้รับโอนใน receiver_name\n"

            "3. ถ้าเป็นรูปอื่นๆ ให้ตอบ category='other'\n"

            'รูปแบบ JSON: {"category": "address|slip|other", "extracted_text": "ข้อความทั้งหมดที่อ่านได้ในรูป", "amount": "ตัวเลขยอดเงินถ้าเป็นสลิป เช่น 390 หรือ 550", "receiver_name": "ชื่อผู้รับโอนในสลิป"}'

        )

        for c in clients:

            try:

                resp = c.chat.completions.create(

                    model="qwen/qwen3.8-27b",

                    messages=[{

                        "role": "user",

                        "content": [

                            {"type": "text", "text": prompt},

                            {"type": "image_url", "image_url": {"url": data_url}},

                        ],

                    }],

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

                            "amount": str(parsed.get("amount") or "").strip(),

                            "receiver_name": str(parsed.get("receiver_name") or "").strip(),

                        }

            except Exception as e:

                logger.warning(f"[facebook] Groq vision key failed: {e}")

    except Exception as e:

        logger.warning(f"[facebook] Groq vision error: {e}")

    return res





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



    MENU_SHORT = (
        "สวัสดีค่ะคุณพี่ ยินดีต้อนรับสู่ร้านป้าเข็มนะคะ 🙏💕\n"
        "ปลาสลิดแดดเดียวสุพรรณแท้ ไซส์จัมโบ้ 4 ตัวโล เนื้อแน่นหนาฟู เค็มน้อย 3% 🐟✨\n"
        "(ตัดหัวควักไส้สะอาด ได้เนื้อล้วนเต็มกิโล แช่แข็ง -18°C แพ็กซองฟอยล์ส่งถึงบ้าน)\n\n"
        "• ชุด 1 กิโล (4 ตัวจัมโบ้): โอน 550.- ส่งฟรีถึงหน้าบ้าน ⭐ (ขายดีสุด)\n"
        "• ชุดทดลอง 500g (2 ตัวจัมโบ้): โอน 390.- ส่งฟรีจ้า\n"
        "• ชุดตุน 2 กิโล (8 ตัวจัมโบ้): โอน 1,090.- (ส่งฟรีรถห้องเย็น!)\n\n"
        "👉 คุณพี่รับชุด 1 กิโล หรือรับชุด 500g ไปลองชิมดูดีคะ พิมพ์บอกป้าเข็มได้เลยน้า 💕"
    )



    # 0. ตรวจจับรูปภาพด้วย Groq Vision (qwen/qwen3.8-27b) (ข้ามสติกเกอร์ยกนิ้วโป้ง 👍 ให้เข้าตัวนำทางก้าวที่ 1 ทันที)

    if not text and attachments:

        for att in attachments:

            if att.get("type") == "image":

                att_payload = att.get("payload") or {}

                if att_payload.get("sticker_id"):

                    _reply_to_facebook(sender, f"สวัสดีค่ะคุณลูกค้า 🙏💕\n\n{MENU_SHORT}", DEFAULT_QUICK_REPLIES, page_id=page_id)

                    return

                img_url = att_payload.get("url")

                if img_url:

                    v_res = _analyze_image_with_groq_vision(img_url)

                    cat = v_res.get("category", "other")

                    ocr_text = v_res.get("extracted_text", "")

                    amt = v_res.get("amount", "")

                    recv_name = v_res.get("receiver_name", "")



                    if cat == "slip":

                        amt_clean = re.sub(r"[^0-9.]", "", amt)

                        try:

                            amt_val = float(amt_clean) if amt_clean else 0.0

                        except Exception:

                            amt_val = 0.0

                        combined_ocr = f"{ocr_text} {recv_name}".lower()

                        receiver_ok = any(

                            k in combined_ocr

                            for k in ["จีรวัฒน์", "พลอาจ", "25363", "038-0-25363-1", "jeerawat", "polart"]

                        ) or not recv_name



                        # เช็คกรณีโอนต่ำกว่าราคาขั้นต่ำ (390 บาท)

                        if 0 < amt_val < 390:

                            _reply_to_facebook(

                                sender,

                                f"⚠️ ได้รับรูปสลิปยอด {amt_val:,.0f} บาท ค่ะ แต่แพ็กเกจเริ่มต้นของร้านคือ ชุดพอดีมื้อ 450–500 กรัม ราคาโอน 390 บาท (ส่งฟรี) ค่ะ 🙏\n"

                                f"เดี๋ยวแอดมินตรวจสอบยอดโอนในบัญชีกรุงไทยและติดต่อกลับนะคะ 😊",

                                page_id=page_id,

                            )

                            _send_telegram_alert(

                                f"⚠️ [สลิปยอดต่ำกว่า 390 บาท!]\n"

                                f"👤 Facebook: `{sender}`\n"

                                f"💰 ยอดในสลิป: {amt_val:,.0f} บาท\n"

                                f"🖼️ สลิป: {img_url}\n"

                                f"📝 ข้อความที่อ่านได้: {ocr_text[:150]}"

                            )

                            return



                        # กรณีลูกค้าพิมพ์ ชื่อ-ที่อยู่-เบอร์โทร สั่งมาก่อนหน้านี้แล้ว -> อัปเดตออเดอร์เดิมเป็นโอนเงินทันที

                        attached_order = _attach_slip_to_recent_order(sender, amt_val, img_url, receiver_ok)

                        if attached_order:

                            ocode = attached_order.get("order_code")

                            opkg = attached_order.get("package_name")

                            amt_disp = f"{amt_val:,.0f}" if amt_val > 0 else amt

                            _reply_to_facebook(

                                sender,

                                f"✅ ได้รับรูปสลิปโอนเงิน {amt_disp} บาท และผูกกับคำสั่งซื้อ #{ocode} เรียบร้อยค่ะ 🙏🐟\n"

                                f"📦 รายการ: {opkg}\n"

                                f"💰 สถานะ: แนบสลิปโอนเงินแล้ว (แอดมินกำลังตรวจสอบยอดเงินเข้าบัญชีกรุงไทย และเตรียมแพ็กส่งรอบสดใหม่ให้ทันทีค่ะ) 🚚❄️",

                                page_id=page_id,

                            )

                            _send_telegram_alert(

                                f"💳 [ลูกค้าส่งสลิปผูกกับออเดอร์ #{ocode} สำเร็จ!]\n"

                                f"🏠 เพจ: {_get_page_label(page_id)}\n"

                                f"👤 Facebook: `{sender}`\n"

                                f"📦 รายการ: {opkg}\n"

                                f"💰 ยอดในสลิป: {amt_disp} บาท ({'ชื่อผู้รับตรง ✅' if receiver_ok else '⚠️ โปรดตรวจชื่อผู้รับในสลิป!'})\n"

                                f"🖼️ รูปสลิป: {img_url}"

                            )

                            return



                        # กรณีลูกค้าส่งรูปสลิปมาก่อนแจ้งที่อยู่ -> บันทึกความจำสลิปและเข้าสู่ตัวนำทางที่อยู่จัดส่งทีละขั้นทันที!

                        _save_pending_slip(sender, amt_val, img_url, ocr_text, receiver_ok)

                        if amt_val >= 1000:

                            pkg_hint = "ชุดตุนสุดคุ้ม 1.8–2.0 กก."

                            slip_pkg, slip_pay = "2kg", "transfer"

                        elif 470 <= amt_val <= 510:

                            pkg_hint = "ชุดพอดีมื้อ 450–500 กรัม [ส่งรถห้องเย็น]"

                            slip_pkg, slip_pay = "500g", "cold_truck"

                        elif 630 <= amt_val <= 680:

                            pkg_hint = "ชุดขายดี 900–1,000 กรัม [ส่งรถห้องเย็น]"

                            slip_pkg, slip_pay = "1kg", "cold_truck"

                        elif 350 <= amt_val <= 430:

                            pkg_hint = "ชุดพอดีมื้อ 450–500 กรัม"

                            slip_pkg, slip_pay = "500g", "transfer"

                        elif amt_val > 0:

                            pkg_hint = "ชุดขายดี 900–1,000 กรัม"

                            slip_pkg, slip_pay = "1kg", "transfer"

                        else:

                            pkg_hint = "ปลาสลิดแดดเดียว ป้าเข็ม"

                            slip_pkg = (_RECENT_CONTEXT.get(sender) or {}).get("pkg") or "1kg"

                            slip_pay = "transfer"

                        amt_disp = f"ยอด {amt_val:,.0f} บาท " if amt_val > 0 else ""

                        slip_header = (

                            f"✅ ได้รับรูปสลิปโอนเงิน {amt_disp}({pkg_hint}) เรียบร้อยค่ะ 🙏🐟\n"

                            f"(แอดมินได้รับสลิปแล้ว กำลังตรวจสอบยอดเงินเข้าบัญชีกรุงไทยค่ะ)"

                        )

                        _prompt_address_step_1_or_saved(

                            sender,

                            pkg_code=slip_pkg,

                            pay_mode=slip_pay,

                            summary_header=slip_header,

                            switch_qrs=[{"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"}],

                            page_id=page_id,

                        )

                        amt_str_tg = f"{amt_val:,.0f}" if amt_val > 0 else amt

                        _send_telegram_alert(

                            f"💳 [ลูกค้าส่งสลิปโอนเงิน — รอแจ้งที่อยู่จัดส่ง!]\n"

                            f"🏠 เพจ: {_get_page_label(page_id)}\n"

                            f"👤 Facebook: `{sender}`\n"

                            f"💰 ยอดในสลิป: {amt_str_tg} บาท ({'ชื่อผู้รับตรง ✅' if receiver_ok else '⚠️ โปรดตรวจชื่อผู้รับในสลิป!'})\n"

                            f"🖼️ รูปสลิป: {img_url}\n"

                            f"📝 ข้อความสลิป: {ocr_text[:150]}"

                        )

                        return

                    elif cat == "address" or any(k in ocr_text for k in ["อำเภอ", "จังหวัด", "ถนน", "ตำบล", "โทร", "ปลายทาง"]):

                        text = ocr_text

                        _send_telegram_alert(f"📦 [ลูกค้าส่งรูปจดที่อยู่จัดส่ง!]\n🏠 เพจ: {_get_page_label(page_id)}\n👤 Facebook: `{sender}`\n🖼️ รูป: {img_url}\n📝 ที่อยู่ที่อ่านได้:\n{ocr_text}")

                        break

                    else:

                        _reply_to_facebook(sender, f"ได้รับรูปภาพเรียบร้อยค่ะ 🙏\n\n{MENU_SHORT}", DEFAULT_QUICK_REPLIES, page_id=page_id)

                        _send_telegram_alert(f"📸 [ลูกค้าส่งรูปภาพทั่วไป]\n🏠 เพจ: {_get_page_label(page_id)}\n👤 Facebook: `{sender}`\n🖼️ รูป: {img_url}")

                        return



    if not text:

        postback = event.get("postback") or {}

        text = (postback.get("title") or postback.get("payload") or "").strip()

        if not qr_payload:

            qr_payload = (postback.get("payload") or "").strip()

    if not text and not qr_payload:

        return



    text = normalize_thai_digits(text)

    lower_text = text.lower().strip()

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")



    # 1. ลูกค้าพิมพ์ตัวเลข หรือ กดปุ่มแอด/Quick Reply เลือกชุด (ต้องเช็คก่อนเช็คเบอร์โทร แต่ถ้ามีที่อยู่+เบอร์โทรให้ข้ามไปบันทึกออเดอร์เลย)

    recent_ctx_early = _RECENT_CONTEXT.get(sender) or {}

    if (time.time() - float(recent_ctx_early.get("ts") or 0)) > 7200:

        recent_ctx_early = {}

    if recent_ctx_early.get("saved_address") and any(

        bad_kw in str(recent_ctx_early.get("saved_address"))

        for bad_kw in ["โอนส่งฟรี", "ปลายทาง", "รับชุด", "390/550", "410", "570", "📦", "⭐", "❄️", "🏦", "🚚"]

    ):

        recent_ctx_early["saved_address"] = ""

        recent_ctx_early["addr_step"] = None

        _RECENT_CONTEXT[sender] = recent_ctx_early



    text_clean_phone = re.sub(r'[-\s]', '', text)

    phone_match = re.search(r'(?:^|[^\d])(0[2689]\d{8})(?!\d)', text_clean_phone)

    text_for_addr = re.sub(

        r'ต่างจังหวัด|(?:ตำบล|อำเภอ|จังหวัด|เขต|แขวง|ถนน|ซอย)\s*(?:ไหน|อะไร|ใด)|390/550|[45]-[67]\s*ตัว/กก|[45]-[67]\s*ตัว',

        '',

        text,

    )

    is_button_or_price_choice = bool(

        (qr_payload and not qr_payload.startswith("QR_TAMBON_"))

        or any(

            k in lower_text

            for k in [

                "โอนส่งฟรี", "ชุด 500g", "ชุด 1กก", "ชุด 2กก",

                "รับชุด", "ชุด 1:", "ชุด 2:", "ชุด 3:", "เปลี่ยนขนาด", "ขอเลขบัญชี", "เลขบัญชี",

            ]

        )

    )

    is_inquiry_sentence = any(

        q in lower_text

        for q in ["ไหม", "มั้ย", "ป่าว", "เปล่า", "เหรอ", "หรือคะ", "ทำไม", "ยังไง", "อย่างไร", "เท่าไหร่", "กี่วัน", "กี่ตัว", "ที่ไหน", "จังหวัดไหน", "อำเภอไหน", "อะไร", "?"]

    )

    has_address = (

        not is_button_or_price_choice

        and bool(

            re.search(r'(?:บ้านเลขที่|ต\.|อ\.|จ\.|ตำบล|อำเภอ|จังหวัด|แขวง|เขต|กทม|กรุงเทพ|ถนน|ถ\.|ซอย|ซ\.|ม\.|หมู่ที่|หมู่|\b[1-9]\d{4}\b|\d+/\d+|soi|road|rd|condo|room|apartment|apt|building|floor|subdistrict|district|bangkok|bkk|phuket|pattaya|chiang\s*mai)', text_for_addr, re.I)

        )

        and not (is_inquiry_sentence and not phone_match)

    )

    is_tambon_reply = bool(

        qr_payload.startswith("QR_TAMBON_")

        or (recent_ctx_early.get("saved_address") and not has_complete_thai_address(recent_ctx_early.get("saved_address", "")))

    )

    in_guided_addr_step = bool(

        qr_payload in ("QR_USE_SAVED_ADDR", "QR_NEW_ADDR")

        or qr_payload.startswith("QR_TAMBON_")

        or (

            recent_ctx_early.get("addr_step") in ("WAIT_ZIP", "WAIT_TAMBON", "WAIT_HOUSE", "WAIT_PHONE")

            and not is_inquiry_sentence

            and qr_payload

            not in (

                "QR_PKG_500G",

                "ORDER_PKG_500G",

                "QR_PKG_1KG",

                "ORDER_PKG_1KG",

                "QR_PKG_2KG",

                "ORDER_PKG_2KG",

                "QR_COD_500G",

                "QR_TRF_500G",

                "QR_COLD_500G",

                "QR_COD_1KG",

                "QR_TRF_1KG",

                "QR_COLD_1KG",

                "QR_CHANGE_PKG",

                "QR_BANK_INFO",

                "QR_COPY_ACC",

                "QR_SWITCH_TO_COD",

            )

            and lower_text not in ("เปลี่ยนขนาด", "เปลี่ยนชุด", "เลือกชุดใหม่", "1", "2", "3", "ชุด 1", "ชุด1", "ชุด 2", "ชุด2", "ชุด 3", "ชุด3")

        )

    )



    if not phone_match and not has_address and not is_tambon_reply and not in_guided_addr_step:

        # 0.9 ตรวจสอบคลังคำถาม-คำตอบอัจฉริยะ 20 หมวดจากไฟล์ CSV (data/fish_faq_rules.csv) เป็นอันดับแรกสุด!

        # (ยกเว้นกรณีลูกค้ากดปุ่มเลือกแพ็กเกจ qr_payload หรือพิมพ์เลขชุดสั้นๆ เพื่อสั่งซื้อโดยไม่มีคำถาม)

        is_short_pkg_choice = lower_text in (

            "1", "2", "3",

            "ชุด1", "ชุด 1", "เอาชุด1", "เอา 1", "รับชุด 1", "รับชุดพอดีมื้อ",

            "ชุด2", "ชุด 2", "เอาชุด2", "เอา 2", "รับชุด 2", "รับชุดขายดี",

            "ชุด3", "ชุด 3", "เอาชุด3", "เอา 3", "รับชุด 3", "รับชุดตุน",

            "ตกลง", "ยืนยัน", "ตกลงค่ะ", "ตกลงครับ", "ยืนยันค่ะ", "ยืนยันครับ", "ok", "โอเค",

        )

        has_question_word = any(

            q in lower_text

            for q in ["ไหม", "มั้ย", "ป่าว", "เปล่า", "เหรอ", "หรือ", "ทำไม", "ยังไง", "อย่างไร", "เท่าไหร่", "กี่", "ไหน", "อะไร", "ไม่มี", "ไม่ได้", "?"]

        )

        has_explicit_order_verb = any(v in lower_text for v in ["รับชุด", "เอาชุด", "สั่งชุด", "รับ 1", "เอา 1", "สั่ง 1", "รับ 500", "เอา 500", "สั่ง 500", "รับ 2", "เอา 2", "สั่ง 2", "สั่งแบบเก็บเงินปลายทาง"])

        if not qr_payload and not is_short_pkg_choice and (has_question_word or not has_explicit_order_verb):

            try:

                from app.services.fish_faq_engine import match_faq_rule

                csv_matched = match_faq_rule(text, greeting="สวัสดีค่ะคุณลูกค้า 🙏💕", web_url=WEB_STORE_URL)

                if csv_matched and csv_matched.get("comment_reply"):

                    rid = csv_matched.get("rule_id") or ""

                    if rid == "FAQ_17_BANK_ACCOUNT_TRUST":

                        _RECENT_CONTEXT[sender] = {"pkg": _RECENT_CONTEXT.get(sender, {}).get("pkg"), "pay": "transfer", "ts": time.time()}

                    qrs_to_send = None if rid == "FAQ_44_ORDER_LATER_FESTIVAL" else DEFAULT_QUICK_REPLIES
                    _reply_to_facebook(sender, csv_matched["comment_reply"], qrs_to_send, page_id=page_id)

                    return

            except Exception as e:

                logger.warning(f"[facebook] early fish_faq_engine error: {e}")



        is_cod_intent = any(k in lower_text for k in ["สั่งแบบเก็บเงินปลายทาง", "เก็บเงินปลายทาง", "เก็บปลายทาง", "ปลายทาง", "cod", "มีปลายทางไหม", "มีเก็บเงินปลายทางไหม"])

        if is_cod_intent and not has_complete_thai_address(text):

            _reply_to_facebook(

                sender,

                "กราบขออภัยด้วยนะคะคุณพี่ 🙏💕 ทางร้านจัดส่งแบบ \"โอนชำระเงินล่วงหน้า (ส่งฟรี)\" เท่านั้น งดรับเก็บเงินปลายทาง (No COD) ทุกกรณีค่ะ\n\n"

                "🧊 เนื่องจากปลาสลิดของป้าเข็มเป็น \"อาหารสดแช่แข็งเยือกแข็ง -18°C แพ็กส่งด่วนรอบต่อรอบ\" หากส่งปลายทางแล้วมีเหตุติดต่อผู้รับไม่ได้ พัสดุจะค้างโกดังจนปลาเน่าเสียทันทีค่ะ\n\n"

                "✨ ทางร้านจึงจัดส่งหลังรับยอดโอน เพื่อการันตีว่าปลาจะถึงมือคุณพี่แบบสดใหม่ เย็นเจี๊ยบ 100% มั่นใจได้เลย มีเลขพัสดุเช็กสถานะได้ตลอดเวลาจ้า 🐟\n\n"

                "⭐ ชุดขายดีสุดคุ้ม 1 กิโล (4–6 ตัวใหญ่): โอน 550.- ส่งฟรี! (เพิ่มจากครึ่งโลแค่ 160.- ได้ปลาเพิ่มเท่าตัว)\n"

                "• ชุดทดลอง 500 กรัม (2–3 ตัวใหญ่): โอน 390.- ส่งฟรี\n"

                "• ชุดตุนสุดคุ้ม 2 กิโลกรัม (8–12 ตัวใหญ่): โอน 1,090.- ส่งฟรีรถห้องเย็น\n\n"

                "🏦 บัญชีกรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n"

                "โอนแล้วแจ้งสลิปพร้อมชื่อ-ที่อยู่-เบอร์โทร ให้ป้าเข็มได้เลยนะคะ เดี๋ยวรีบแพ็กส่งรอบสดใหม่ให้เลยจ้า 💕",

                [

                    {"content_type": "text", "title": "⭐ รับ 1 กก. (550.-)", "payload": "QR_PKG_1KG"},

                    {"content_type": "text", "title": "📦 ลอง 500g (390.-)", "payload": "QR_PKG_500G"},

                    {"content_type": "text", "title": "📋 คัดลอกเลขบัญชี", "payload": "QR_COPY_ACC"},

                ],

                page_id=page_id,

            )

            return

        has_1kg_unit = any(k in lower_text for k in ["รับชุดขายดี", "ชุดขายดี", "1 กก", "1กก", "1kg", "1 กิโล", "1กิโล", "หนึ่งกิโล", "โลนึง", "1 โล", "1โล", "5-7 ตัว", "5-7ตัว", "570"])

        has_500g_unit = any(k in lower_text for k in ["รับชุดพอดีมื้อ", "ชุดพอดีมื้อ", "500g", "500 กรัม", "500กรัม", "ครึ่งโล", "ครึ่งกิโล", "3-4 ตัว", "3-4ตัว", "410"])

        is_1kg_intent = qr_payload in ("QR_PKG_1KG", "ORDER_PKG_1KG", "QR_COD_1KG") or has_1kg_unit or (

            not has_500g_unit and (lower_text in ("2", "ชุด2", "ชุด 2", "เอาชุด2", "เอา 2", "รับชุด 2") or any(k in lower_text for k in ["ชุด 2", "ชุด2"]))

        )

        is_500g_intent = qr_payload in ("QR_PKG_500G", "ORDER_PKG_500G", "QR_COD_500G") or has_500g_unit or (

            not has_1kg_unit and (lower_text in ("1", "ชุด1", "ชุด 1", "เอาชุด1", "เอา 1", "รับชุด 1") or any(k in lower_text for k in ["ชุด 1", "ชุด1"]))

        )



        # 0.92 ปุ่มคัดลอกเลขบัญชี 10 หลักล้วน (0380253631) สำหรับผู้สูงอายุแตะค้างคัดลอกเข้าแอปธนาคาร

        if qr_payload == "QR_COPY_ACC" or lower_text in ("คัดลอกเลขบัญชี", "📋 คัดลอกเลขบัญชี", "ขอเลขบัญชีคัดลอก"):

            _send_fb_plain_text(sender, KRUNGTHAI_ACCOUNT_DIGITS, page_id=page_id)

            return



        # 0.93 ปุ่มสลับจากโอนเงินเป็น "เก็บเงินปลายทาง (COD)" หลังออกบิล (เฉพาะพื้นที่ 1-2 วัน <= 350 กม.)

        if qr_payload == "QR_SWITCH_TO_COD" or any(k in lower_text for k in ["เปลี่ยนเป็นปลายทาง", "เปลี่ยนเป็นเก็บเงินปลายทาง", "ขอเปลี่ยนเป็นปลายทาง"]):

            saved_addr_sw = recent_ctx_early.get("saved_address") or ""

            pkg_sw = recent_ctx_early.get("last_pkg") or recent_ctx_early.get("pkg") or "1kg"

            if saved_addr_sw and has_complete_thai_address(saved_addr_sw):

                route_sw = calculate_shipping_route_info(saved_addr_sw)

                if not route_sw["allow_cod"]:

                    _prompt_payment_choice_for_area(sender, recent_ctx_early, saved_addr_sw, route_sw, page_id=page_id)

                    return

                if pkg_sw == "2kg":

                    _reply_to_facebook(

                        sender,

                        "⚠️ ชุดตุนสุดคุ้ม 2 กิโลกรัม (1,090.-) จัดส่งด้วยรถห้องเย็นควบคุมอุณหภูมิ จึงรับเฉพาะโอนเงินล่วงหน้าค่ะ 🙏\n"

                        "ทางร้านงดรับเก็บเงินปลายทาง (COD) ทุกชุด 100% ค่ะ รับเฉพาะโอนเงินล่วงหน้าส่งฟรีนะคะ:",

                        [

                            {"content_type": "text", "title": "ชุด 1 กก. (550.-)", "payload": "QR_PKG_1KG"},

                            {"content_type": "text", "title": "📋 คัดลอกเลขบัญชี", "payload": "QR_COPY_ACC"},

                        ],

                        page_id=page_id,

                    )

                    return

                sw_order = _switch_recent_order_to_cod(sender, pkg_sw)

                cod_p = 410 if pkg_sw == "500g" else 570

                pkg_lbl = "ชุดพอดีมื้อ 450-500 กรัม (ประมาณ 2 ตัวจัมโบ้)" if pkg_sw == "500g" else "ชุดยอดฮิต 900-1,000 กรัม (ประมาณ 4 ตัวจัมโบ้)"

                ocode_sw = (sw_order or {}).get("order_code") or recent_ctx_early.get("last_order_code") or "ล่าสุด"

                recent_ctx_early["pay"] = "cod"

                _RECENT_CONTEXT[sender] = recent_ctx_early

                _reply_to_facebook(

                    sender,

                    f"✅ เปลี่ยนวิธีชำระเงินเป็น 'เก็บเงินปลายทาง (COD)' เรียบร้อยค่ะ 🚚💵\n\n"

                    f"📦 รหัสคำสั่งซื้อ: {ocode_sw}\n"

                    f"🐟 รายการ: {pkg_lbl}\n"

                    f"💰 ยอดชำระหน้าบ้านตอนรับของ: {cod_p} บาท (รวมส่งแล้ว)\n"

                    f"📍 ที่อยู่จัดส่ง: {saved_addr_sw}\n"

                    f"{route_sw['summary_line']}\n\n"

                    f"🚚 ทางร้านเตรียมแพ็กส่งรอบสดใหม่ให้ถึงหน้าบ้าน รอรับสายขนส่งได้เลยนะคะ ขอบพระคุณค่ะ 😊",

                    page_id=page_id,

                )

                _send_telegram_alert(

                    f"🔄 [ลูกค้ากดสลับเป็นเก็บเงินปลายทาง (COD)!]\n"

                    f"🏠 เพจ: {_get_page_label(page_id)}\n"

                    f"🔖 รหัส: {ocode_sw}\n"

                    f"📦 รายการ: {pkg_lbl}\n"

                    f"💰 ยอด COD ใหม่: {cod_p} บาท\n"

                    f"📍 ที่อยู่: {saved_addr_sw}"

                )

                return



        # 0.95 ปุ่มย้อนกลับเลือกขนาดชุดใหม่ (Step 1 ของตัวนำทาง)

        if qr_payload == "QR_CHANGE_PKG" or lower_text in ("เปลี่ยนขนาด", "เปลี่ยนชุด", "เลือกชุดใหม่"):

            _reply_to_facebook(sender, MENU_SHORT, DEFAULT_QUICK_REPLIES, page_id=page_id)

            return



        # 1.0 ตัวนำทางเมื่อลูกค้ากดเลือกวิธีชำระเงิน (หลังใส่รหัสไปรษณีย์แล้ว หรือกดเลือกตรง)

        if qr_payload in ("QR_COD_500G", "QR_TRF_500G", "QR_COLD_500G", "QR_COD_1KG", "QR_TRF_1KG", "QR_COLD_1KG") or (is_cod_intent and (is_500g_intent or is_1kg_intent)):

            if qr_payload in ("QR_COD_500G", "QR_TRF_500G", "QR_COLD_500G") or (is_500g_intent and not is_1kg_intent):

                sel_pkg = "500g"

            else:

                sel_pkg = "1kg"



            if qr_payload in ("QR_COLD_500G", "QR_COLD_1KG"):

                sel_pay = "cold_truck"

            elif qr_payload in ("QR_TRF_500G", "QR_TRF_1KG"):

                sel_pay = "transfer"

            else:

                sel_pay = "cod"



            if sel_pkg == "500g":

                hdr = (

                    "❄️ สรุปรายการ: ชุดพอดีมื้อ 500 กรัม ส่งรถห้องเย็น ยอดโอน 490 บาท\n• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)"

                    if sel_pay == "cold_truck"

                    else (

                        "🏦 สรุปรายการ: ชุดพอดีมื้อ 500 กรัม (2 ตัวจัมโบ้) โอนเงิน 390 บาท (ส่งฟรี!) ❄️\n• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)"

                        if sel_pay == "transfer"

                        else "🚚 สรุปรายการ: ชุดพอดีมื้อ 500 กรัม (2 ตัวจัมโบ้) เก็บเงินปลายทาง ยอดรวม 410 บาท ❄️"

                    )

                )

            else:

                hdr = (

                    "❄️ สรุปรายการ: ชุดขายดี 1 กิโลกรัม ส่งรถห้องเย็น ยอดโอน 650 บาท ⭐\n• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)"

                    if sel_pay == "cold_truck"

                    else (

                        "🏦 สรุปรายการ: ชุดขายดี 1 กิโลกรัม (4 ตัวจัมโบ้) โอนเงิน 550 บาท (ส่งฟรี!) ⭐❄️\n• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)"

                        if sel_pay == "transfer"

                        else "🚚 สรุปรายการ: ชุดขายดี 1 กิโลกรัม (4 ตัวจัมโบ้) เก็บเงินปลายทาง ยอดรวม 570 บาท ⭐❄️"

                    )

                )



            # หากลูกค้ากรอกที่อยู่ + เบอร์โทร ครบแล้ว และกดเลือกวิธีชำระเงินในขั้นยืนยัน -> ออกบิล PKF-... ทันที!

            if (

                recent_ctx_early.get("addr_step") == "WAIT_PAY_AFTER_ZIP"

                and recent_ctx_early.get("saved_address")

                and has_complete_thai_address(recent_ctx_early["saved_address"])

                and recent_ctx_early.get("saved_phone")

                and validate_thai_phone(recent_ctx_early["saved_phone"])["valid"]

            ):

                route_chk = calculate_shipping_route_info(recent_ctx_early["saved_address"])

                if sel_pay == "cod" and not route_chk["allow_cod"]:

                    _prompt_payment_choice_for_area(sender, recent_ctx_early, recent_ctx_early["saved_address"], route_chk, page_id=page_id)

                    return

                recent_ctx_early["pkg"] = sel_pkg

                recent_ctx_early["pay"] = sel_pay

                _finalize_facebook_order(

                    sender,

                    full_address=recent_ctx_early["saved_address"],

                    phone=recent_ctx_early["saved_phone"],

                    recent_ctx=recent_ctx_early,

                    page_id=page_id,

                    customer_name=recent_ctx_early.get("saved_name") or "",

                )

                return



            # หากลูกค้าพิมพ์รหัสไปรษณีย์ไว้แล้ว (อยู่ในขั้น WAIT_PAY_AFTER_ZIP) -> ไปขั้นเลือกตำบล/บ้านเลขที่ต่อทันที!

            if recent_ctx_early.get("saved_address") and recent_ctx_early.get("addr_step") == "WAIT_PAY_AFTER_ZIP":

                route_chk = calculate_shipping_route_info(recent_ctx_early["saved_address"])

                if sel_pay == "cod" and not route_chk["allow_cod"]:

                    _prompt_payment_choice_for_area(sender, recent_ctx_early, recent_ctx_early["saved_address"], route_chk, page_id=page_id)

                    return

                recent_ctx_early["pkg"] = sel_pkg

                recent_ctx_early["pay"] = sel_pay

                _prompt_tambon_or_house_after_zip(sender, recent_ctx_early, page_id=page_id, header_prefix=hdr)

                return



            _prompt_address_step_1_or_saved(

                sender,

                pkg_code=sel_pkg,

                pay_mode=sel_pay,

                summary_header=hdr,

                switch_qrs=[{"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"}],

                page_id=page_id,

            )

            return



        # 1.1 ถามจำนวนตัว / กี่ตัวโล / ตัวละเท่าไหร่ / ไซส์ไหน

        if any(k in lower_text for k in ["กี่ตัว", "โลละกี่ตัว", "ตัวละ", "ราคาตัวละ", "ขายเป็นตัว", "แยกตัว", "ตัวใหญ่ไหม", "ตัวใหญ่มั้ย", "ไซส์ไหน", "ขนาดไหน"]):

            _reply_to_facebook(

                sender,

                "🐟 ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม (ไซส์จัมโบ้คัดพิเศษ 4–6 ตัวโล ตัวใหญ่กำลังกิน เนื้อแน่นหนาฟู ไร้กลิ่นโคลน เค็มน้อย 3%) ✨\n"

                "💡 ตัดหัวควักไส้สะอาดเรียบร้อย ได้เนื้อล้วนเต็มกิโล แช่แข็ง -18°C แพ็กซองฟอยล์สดใหม่\n\n"

                "⭐ ชุดขายดีสุดคุ้ม 1 กิโลกรัม (4–6 ตัวใหญ่): โอน 550.- ส่งฟรีถึงหน้าบ้าน! (เพิ่มจากครึ่งโลแค่ 160.- ได้ปลาเพิ่มเท่าตัว แบ่งทอดได้ 2–3 มื้อ คุ้มสุดๆ ค่ะ) ⭐\n"

                "• ชุดทดลอง 500 กรัม (2–3 ตัวใหญ่): โอน 390.- ส่งฟรี (งดรับ COD)\n"

                "• ชุดตุนสุดคุ้ม 2 กิโลกรัม (8–12 ตัว): โอน 1,090.- ส่งฟรีรถห้องเย็น\n\n"

                "👇 กดปุ่มสั่งซื้อ หรือพิมพ์ชื่อ-ที่อยู่-เบอร์โทร แจ้งป้าเข็มได้เลยนะคะ 💕",

                DEFAULT_QUICK_REPLIES,

                page_id=page_id,

            )

            return



        # 1.2 ลูกค้ากดเลือก "ชุด 1: 500g" -> ถามรหัสไปรษณีย์ 5 หลักก่อน (เหมือน LINE OA 1/5 เพื่อเช็คว่าพื้นที่อยู่ในเกณฑ์ 1-2 วันเก็บปลายทางได้ หรือ 3-4 วันส่งรถห้องเย็น)

        if qr_payload in ("QR_PKG_500G", "ORDER_PKG_500G") or is_500g_intent:

            _prompt_address_step_1_or_saved(

                sender,

                pkg_code="500g",

                pay_mode=None,

                summary_header=(

                    "✅ คุณลูกค้าเลือก ชุดพอดีมื้อ 500 กรัม (ประมาณ 2 ตัวจัมโบ้) ค่ะ 🐟✨\n"

                    "• พื้นที่ส่งถึงใน 1–2 วัน: โอน 390.- ส่งฟรี! (งดรับ COD)\n"

                    "• พื้นที่ส่ง 3–4 วัน (ตจว.ไกล): ส่งรถห้องเย็น (งดเก็บปลายทาง)"

                ),

                switch_qrs=[{"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"}],

                page_id=page_id,

            )

            return



        # 1.3 ลูกค้ากดเลือก "ชุด 2: 1กก.ขายดี" -> ถามรหัสไปรษณีย์ 5 หลักก่อน (เหมือน LINE OA 1/5 เพื่อเช็คเงื่อนไขพื้นที่ 1-2 วัน vs 3-4 วัน)

        if qr_payload in ("QR_PKG_1KG", "ORDER_PKG_1KG") or is_1kg_intent:

            _prompt_address_step_1_or_saved(

                sender,

                pkg_code="1kg",

                pay_mode=None,

                summary_header=(

                    "✅ คุณลูกค้าเลือก ชุดขายดี 1 กิโลกรัม (ประมาณ 4 ตัวจัมโบ้) ค่ะ ⭐🐟\n"

                    "• พื้นที่ส่งถึงใน 1–2 วัน: โอน 550.- ส่งฟรี! (งดรับ COD)\n"

                    "• พื้นที่ส่ง 3–4 วัน (ตจว.ไกล): ส่งรถห้องเย็น (งดเก็บปลายทาง)"

                ),

                switch_qrs=[{"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"}],

                page_id=page_id,

            )

            return



        # 1.4 ตัวนำทางก้าวที่ 2/3: เลือกชุด 3 (2kg ส่งฟรีรถห้องเย็น) -> เข้าสู่ตัวนำทางที่อยู่จัดส่งแบบ LINE OA

        if qr_payload in ("QR_PKG_2KG", "ORDER_PKG_2KG") or lower_text in ("3", "ชุด3", "ชุด 3", "เอาชุด3", "เอา 3", "รับชุด 3") or any(k in lower_text for k in ["รับชุดตุน", "ชุดตุน", "ชุดครอบครัว", "2 กก", "2กก", "2kg", "2 กิโล", "2กิโล", "สองโล", "สองกิโล", "2 โล", "2โล", "ชุด 3", "ชุด3"]):

            _prompt_address_step_1_or_saved(

                sender,

                pkg_code="2kg",

                pay_mode="transfer",

                summary_header=(

                    "✅ ชุดตุนสุดคุ้ม 2 กิโลกรัม (8 ตัวจัมโบ้) โอน 1,090 บาท (ส่งฟรีรถห้องเย็น!) ❄️🚚\n"

                    "• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)"

                ),

                switch_qrs=[{"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"}],

                page_id=page_id,

            )

            return



        # 1.5 ลูกค้าถามหาปลายทาง (COD) -> ชี้แจงงดรับ COD พร้อมเสนอชุดโอนส่งฟรี
        if is_cod_intent:
            _reply_to_facebook(
                sender,
                "🐟 ขออนุญาตเรียนแจ้งคุณลูกค้าตามตรงนะคะ ทางร้านงดรับเก็บเงินปลายทาง (COD) ทุกชุด 100% ค่ะ 🙏❄️\n"
                "เนื่องจากปลาสลิดเป็นอาหารสดแช่แข็ง ≤ -18°C ทางร้านจึงจัดส่งหลังได้รับการชำระเงินโอนเต็มจำนวนเท่านั้น เพื่อการันตีความสดและป้องกันสินค้าตกค้างเสียหายจากการตีกลับค่ะ (โอนเงินจัดส่งฟรีถึงหน้าบ้านทุกชุดเลยจ้า! 🚚)\n\n"
                "📦 โปรโมชั่นโอนเงินส่งฟรี:\n"
                "• 1️⃣ ชุดพอดีมื้อ 500g (2–3 ตัวใหญ่) = โอน 390.- ส่งฟรี!\n"
                "• 2️⃣ ชุดขายดี 1 กิโลกรัม (4–6 ตัวใหญ่) = โอน 550.- ส่งฟรี! ⭐\n"
                "• 3️⃣ ชุดตุนสุดคุ้ม 2 กิโลกรัม (8–12 ตัวใหญ่) = โอน 1,090.- (ส่งฟรีรถห้องเย็น!)\n\n"
                "🏦 ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n"
                "👉 รับชุดไหน พิมพ์เลข 1, 2 หรือ 3 ในแชทนี้ได้เลยนะคะ 😊",
                DEFAULT_QUICK_REPLIES,
                page_id=page_id,
            )
            return





        # 1.6 ลูกค้ากดปุ่ม "โอนส่งฟรี" (QR_BANK_INFO) หรือขอเลขบัญชีโอนเงิน -> แยกปุ่มเลือกชุดโอนเงินชัดเจน!

        if qr_payload == "QR_BANK_INFO" or any(k in lower_text for k in ["เลขบัญชี", "ขอเลขบัญชี", "โอนเงิน", "เลขที่บัญชี", "บัญชีธนาคาร", "โอนจ่าย", "จ่ายเงิน", "พร้อมเพย์", "โอนส่งฟรี"]):

            cur_pkg = _RECENT_CONTEXT.get(sender, {}).get("pkg")

            if cur_pkg == "500g" and qr_payload == "QR_BANK_INFO":

                _prompt_address_step_1_or_saved(

                    sender,

                    pkg_code="500g",

                    pay_mode="transfer",

                    summary_header=(

                        "🏦 สรุปรายการ: ชุดพอดีมื้อ 500 กรัม (2 ตัวจัมโบ้) โอนเงิน 390 บาท (ส่งฟรี!) ❄️\n"

                        "• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)"

                    ),

                    switch_qrs=[{"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"}],

                    page_id=page_id,

                )

                return

            if cur_pkg == "1kg" and qr_payload == "QR_BANK_INFO":

                _prompt_address_step_1_or_saved(

                    sender,

                    pkg_code="1kg",

                    pay_mode="transfer",

                    summary_header=(

                        "🏦 สรุปรายการ: ชุดขายดี 1 กิโลกรัม (4 ตัวจัมโบ้) โอนเงิน 550 บาท (ส่งฟรี!) ⭐❄️\n"

                        "• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)"

                    ),

                    switch_qrs=[{"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"}],

                    page_id=page_id,

                )

                return

            _RECENT_CONTEXT[sender] = {"pkg": cur_pkg, "pay": "transfer", "ts": time.time()}

            bank_short = (

                "🏦 โอนเงินล่วงหน้า ส่งฟรีทุกชุดค่ะ!\n"

                "• ธ.กรุงไทย: 038-0-25363-1 (นายจีรวัฒน์ พลอาจ)\n"

                "━━━━━━━━━━━━━━━━━━\n"

                "• ชุด 1 (500 กรัม / 2 ตัวจัมโบ้): โอน 390 บาท (ส่งฟรี!)\n"

                "• ชุด 2 (1 กิโลกรัม / 4 ตัวจัมโบ้): โอน 550 บาท (ส่งฟรี!) ⭐\n"

                "• ชุด 3 (2 กิโลกรัม / 8 ตัวจัมโบ้): โอน 1,090 บาท (ส่งฟรีรถห้องเย็น!)\n"

                "👇 กดปุ่มเลือกชุดที่ต้องการโอนสั่งซื้อด้านล่างได้เลยจ้า:"

            )

            bank_qrs = [

                {"content_type": "text", "title": "🏦 โอน 500g (390.-)", "payload": "QR_TRF_500G"},

                {"content_type": "text", "title": "⭐ โอน 1กก. (550.-)", "payload": "QR_TRF_1KG"},

                {"content_type": "text", "title": "❄️ โอน 2กก. (1,090.-)", "payload": "QR_PKG_2KG"},

            ]

            _reply_to_facebook(

                sender,

                bank_short,

                bank_qrs,

                page_id=page_id,

            )

            _send_fb_image(sender, KRUNGTHAI_QR_IMAGE_URL, page_id=page_id)

            _send_fb_plain_text(sender, KRUNGTHAI_ACCOUNT_DIGITS, bank_qrs, page_id=page_id)

            return



    # 2. ตัวนำทางที่อยู่จัดส่งแบบ LINE OA (ทีละขั้น: ที่อยู่เดิม -> 1.รหัสไปรษณีย์ -> 2.จิ้มเลือกตำบล -> 3.บ้านเลขที่ -> 4.เบอร์โทร 10 หลัก)

    recent_ctx = _RECENT_CONTEXT.get(sender) or {}

    if (time.time() - float(recent_ctx.get("ts") or 0)) > 7200:

        recent_ctx = {}



    # 2.01 ลูกค้ากดปุ่ม "✅ ใช้ที่อยู่เดิมนี้" (QR_USE_SAVED_ADDR) -> ออกบิลทันทีใน 1 คลิก!

    if qr_payload == "QR_USE_SAVED_ADDR" or lower_text in ("ใช้ที่อยู่เดิม", "ยืนยันใช้ที่อยู่เดิม", "✅ ใช้ที่อยู่เดิมนี้", "ใช้ที่อยู่เดิมนี้"):

        prev = _lookup_previous_customer_address(sender)

        if prev and prev.get("address") and prev.get("phone"):

            _finalize_facebook_order(

                sender,

                full_address=prev["address"],

                phone=prev["phone"],

                recent_ctx=recent_ctx,

                page_id=page_id,

                customer_name=prev.get("customer_name") or "",

            )

            return



    # 2.02 ลูกค้ากดปุ่ม "✏️ เปลี่ยนที่อยู่ใหม่" (QR_NEW_ADDR) -> เริ่มถามรหัสไปรษณีย์ 5 หลักใหม่

    if qr_payload == "QR_NEW_ADDR" or lower_text in ("เปลี่ยนที่อยู่ใหม่", "✏️ เปลี่ยนที่อยู่ใหม่", "ที่อยู่ใหม่"):

        pkg_c = recent_ctx.get("pkg") or "1kg"

        pay_m = recent_ctx.get("pay") or "cod"

        _prompt_address_step_1_or_saved(

            sender,

            pkg_code=pkg_c,

            pay_mode=pay_m,

            summary_header="✏️ เปลี่ยนที่อยู่จัดส่งใหม่ค่ะ",

            switch_qrs=[{"content_type": "text", "title": "🔄 เปลี่ยนขนาดชุด", "payload": "QR_CHANGE_PKG"}],

            page_id=page_id,

            force_new_addr=True,

        )

        return



    # 2.1 ขั้นที่ 1/3: ลูกค้าพิมพ์รหัสไปรษณีย์ 5 หลัก (เช่น "10240") หรือพิมพ์ "ชื่ออำเภอ/เขต/ตำบล" (เช่น "อำเภอ บางปะหัน")

    zip_only_m = re.match(r"^(?:รหัสไปรษณีย์|ปณ\.?)?[\s:：-]*([1-9]\d{4})[\s]*$", text.strip())

    area_by_name_info = (

        lookup_thai_area_by_name(text.strip())

        if (

            not zip_only_m

            and not phone_match

            and not is_button_or_price_choice

            and not qr_payload.startswith("QR_TAMBON_")

            and not is_inquiry_sentence

            and recent_ctx.get("addr_step") not in ("WAIT_TAMBON", "WAIT_HOUSE")

            and not re.search(r"\d+/\d+|บ้านเลขที่|หมู่", text)

        )

        else None

    )

    if (zip_only_m or area_by_name_info) and not phone_match:

        zip_code = zip_only_m.group(1) if zip_only_m else area_by_name_info["zip"]

        zip_info = lookup_thai_zip(zip_code) if zip_only_m else area_by_name_info

        if zip_info:

            d_prefix = "" if zip_info["amphoe"].startswith("เขต") else ("เขต" if zip_info["is_bkk"] else "อ.")

            p_prefix = "" if zip_info["is_bkk"] else "จ."

            t_prefix = "แขวง" if zip_info["is_bkk"] else "ต."

            area_str = f"{d_prefix}{zip_info['amphoe']} {p_prefix}{zip_info['province']} {zip_code}".strip()

            route = calculate_shipping_route_info(area_str)



            tambons = zip_info["tambons"] or []

            matched_t_direct = zip_info.get("matched_tambon") or (tambons[0] if len(tambons) == 1 else "")

            saved_house_prefix = (recent_ctx.get("saved_house_no") or "").strip()

            base_area_saved = f"{t_prefix}{matched_t_direct} {area_str}".strip() if matched_t_direct else area_str

            if saved_house_prefix and saved_house_prefix not in base_area_saved:

                base_area_saved = f"{saved_house_prefix} {base_area_saved}".strip()

                recent_ctx["house_filled"] = True

            else:

                recent_ctx["house_filled"] = False

            recent_ctx["zip_code"] = zip_code

            recent_ctx["saved_address"] = base_area_saved



            # กรณีลูกค้าพิมพ์รหัสไปรษณีย์ในโซนไกล 3-4 วัน (> 350 กม.) และยังไม่ได้เลือกวิธีจ่ายเงิน (หรือเลือก COD ไว้) -> แจ้งเงื่อนไขงด COD ก่อนทันที

            if not route["allow_cod"] and recent_ctx.get("pkg") != "2kg" and (not recent_ctx.get("pay") or recent_ctx.get("pay") == "cod"):

                _prompt_payment_choice_for_area(sender, recent_ctx, base_area_saved, route, page_id=page_id)

                return



            far_notice = "" 

            if matched_t_direct:

                full_area = f"{t_prefix}{matched_t_direct} {area_str}".strip()

                recent_ctx.update({

                    "zip_code": zip_code,

                    "saved_address": full_area,

                    "waiting_tambon": False,

                    "house_filled": False,

                    "addr_step": "WAIT_HOUSE",

                    "ts": time.time(),

                })

                _RECENT_CONTEXT[sender] = recent_ctx

                _reply_to_facebook(

                    sender,

                    f"📍 พื้นที่จัดส่ง: {full_area}\n"

                    f"{route['summary_line']}{far_notice}\n"

                    f"━━━━━━━━━━━━━━━━━━\n"

                    f"🏠 ขั้นที่ 2/3 (บ้านเลขที่) :\n"

                    f"👉 พิมพ์ 'บ้านเลขที่ / หมู่ / ซอย / ถนน' (เช่น 99/1 หมู่ 2) ส่งมาได้เลยค่ะ:",

                    [{"content_type": "text", "title": "🔄 เปลี่ยนรหัสไปรษณีย์", "payload": "QR_NEW_ADDR"}],

                    page_id=page_id,

                )

                return



            recent_ctx.update({

                "zip_code": zip_code,

                "saved_address": area_str,

                "waiting_tambon": True,

                "house_filled": False,

                "addr_step": "WAIT_TAMBON",

                "ts": time.time(),

            })

            _RECENT_CONTEXT[sender] = recent_ctx

            tambon_qrs = [

                {

                    "content_type": "text",

                    "title": f"{t_prefix}{t}"[:20],

                    "payload": f"QR_TAMBON_{t}",

                }

                for t in tambons[:13]

            ]

            tambon_list_txt = " / ".join(f"{idx+1}.{t_prefix}{t}" for idx, t in enumerate(tambons))

            _reply_to_facebook(

                sender,

                f"📍 รหัสไปรษณีย์ {zip_code} ({d_prefix}{zip_info['amphoe']} {p_prefix}{zip_info['province']})\n"

                f"{route['summary_line']}{far_notice}\n"

                f"━━━━━━━━━━━━━━━━━━\n"

                f"📌 มี{t_prefix}ดังนี้ค่ะ: {tambon_list_txt}\n\n"

                f"👇 กดปุ่มเลือก '{t_prefix}' ด้านล่าง (หรือพิมพ์ชื่อตำบล) ได้เลยค่ะ:",

                tambon_qrs,

                page_id=page_id,

            )

            return

        else:

            _reply_to_facebook(

                sender,

                f"⚠️ ไม่พบรหัสไปรษณีย์ {zip_code} ในระบบไปรษณีย์ไทยค่ะ\n"

                f"👉 รบกวนพิมพ์ 'รหัสไปรษณีย์ 5 หลัก' ที่ถูกต้องอีกครั้ง (หรือพิมพ์ ชื่อตำบล อำเภอ จังหวัด) ได้เลยนะคะ 😊",

                page_id=page_id,

            )

            return



    # 2.2 ขั้นเลือกตำบล/แขวง (ลูกค้ากดปุ่ม QR_TAMBON_... หรือพิมพ์ชื่อตำบลเมื่ออยู่ในสถานะ WAIT_TAMBON)

    if qr_payload.startswith("QR_TAMBON_") or (recent_ctx.get("addr_step") == "WAIT_TAMBON" and not phone_match):

        picked_tambon = ""

        if qr_payload.startswith("QR_TAMBON_"):

            picked_tambon = qr_payload[len("QR_TAMBON_") :].strip()

        else:

            clean_t_in = re.sub(r"^(?:เลือกตำบล|ตำบล|ต\.|แขวง)\s*[:：-]?\s*", "", text.strip()).strip()

            zip_m_ctx = re.search(r"\b([1-9]\d{4})\b", recent_ctx.get("saved_address") or "")

            z_info = lookup_thai_zip(zip_m_ctx.group(1)) if zip_m_ctx else None

            if z_info and z_info["tambons"]:

                if clean_t_in.isdigit() and 1 <= int(clean_t_in) <= len(z_info["tambons"]):

                    picked_tambon = z_info["tambons"][int(clean_t_in) - 1]

                else:

                    for ct in z_info["tambons"]:

                        if clean_t_in == ct or ct in clean_t_in:

                            picked_tambon = ct

                            break

            if not picked_tambon and 2 <= len(clean_t_in) <= 30:

                picked_tambon = clean_t_in



        if picked_tambon:

            updated_addr = enrich_thai_address(

                insert_tambon_into_address(recent_ctx.get("saved_address") or "", picked_tambon)

            )

            recent_ctx["saved_address"] = updated_addr

            recent_ctx["waiting_tambon"] = False

            recent_ctx["ts"] = time.time()



            if not recent_ctx.get("house_filled"):

                recent_ctx["addr_step"] = "WAIT_HOUSE"

                _RECENT_CONTEXT[sender] = recent_ctx

                _reply_to_facebook(

                    sender,

                    f"✅ บันทึกพื้นที่: {updated_addr} เรียบร้อยค่ะ 📍\n"

                    f"━━━━━━━━━━━━━━━━━━\n"

                    f"🏠 ขั้นที่ 2/3 (บ้านเลขที่ / หมู่ / ซอย) :\n"

                    f"👉 พิมพ์เฉพาะ 'บ้านเลขที่ / หมู่ / ซอย / ถนน' (เช่น 99/1 หมู่ 2) ส่งมาได้เลยค่ะ:",

                    [{"content_type": "text", "title": "✏️ เปลี่ยนรหัสไปรษณีย์", "payload": "QR_NEW_ADDR"}],

                    page_id=page_id,

                )

                return



            if recent_ctx.get("saved_phone") and validate_thai_phone(recent_ctx["saved_phone"])["valid"]:

                _finalize_facebook_order(

                    sender,

                    full_address=updated_addr,

                    phone=recent_ctx["saved_phone"],

                    recent_ctx=recent_ctx,

                    page_id=page_id,

                )

                return



            recent_ctx["addr_step"] = "WAIT_PHONE"

            _RECENT_CONTEXT[sender] = recent_ctx

            _reply_to_facebook(

                sender,

                f"✅ บันทึกที่อยู่จัดส่งครบถ้วนแล้วค่ะ:\n"

                f"🏠 {updated_addr}\n"

                f"━━━━━━━━━━━━━━━━━━\n"

                f"📞 ขั้นสุดท้าย (3/3 : เบอร์โทรศัพท์ผู้รับ) :\n"

                f"👉 พิมพ์เฉพาะ 'เบอร์โทรศัพท์มือถือ 10 หลัก' (เช่น 0891234567) ส่งมาได้เลยจ้ะ\n(ชื่อผู้รับป้าเข็มดึงจากชื่อเฟซบุ๊กให้เลย ไม่ต้องพิมพ์ซ้ำจ้า 😊)",

                page_id=page_id,

            )

            return



    # 2.3 ขั้นที่ 2/3: ลูกค้าพิมพ์ "บ้านเลขที่ / หมู่ / ซอย" (เมื่ออยู่ในสถานะ WAIT_HOUSE)

    if recent_ctx.get("addr_step") == "WAIT_HOUSE" and recent_ctx.get("saved_address"):

        raw_house = text.strip()

        # หากลูกค้าพิมพ์เบอร์โทรติดมาพร้อมบ้านเลขที่ในข้อความเดียวกัน

        if phone_match and validate_thai_phone(phone_match.group(1))["valid"]:

            valid_ph = validate_thai_phone(phone_match.group(1))["phone"]

            house_without_ph = re.sub(r"0[2689]\d[\d\s-]{6,12}", "", raw_house).strip()

            if house_without_ph and re.match(r"^\d", house_without_ph) and not house_without_ph.startswith("บ้านเลขที่"):

                house_without_ph = f"บ้านเลขที่ {house_without_ph}"

            full_addr = enrich_thai_address(f"{house_without_ph} {recent_ctx['saved_address']}".strip())

            _finalize_facebook_order(

                sender,

                full_address=full_addr,

                phone=valid_ph,

                recent_ctx=recent_ctx,

                page_id=page_id,

                raw_hint_text=raw_house,

            )

            return



        if re.match(r"^\d", raw_house) and not raw_house.startswith("บ้านเลขที่"):

            raw_house = f"บ้านเลขที่ {raw_house}"

        full_addr = enrich_thai_address(f"{raw_house} {recent_ctx['saved_address']}".strip())

        recent_ctx["saved_address"] = full_addr

        recent_ctx["house_filled"] = True

        recent_ctx["ts"] = time.time()



        if recent_ctx.get("saved_phone") and validate_thai_phone(recent_ctx["saved_phone"])["valid"]:

            _finalize_facebook_order(

                sender,

                full_address=full_addr,

                phone=recent_ctx["saved_phone"],

                recent_ctx=recent_ctx,

                page_id=page_id,

                raw_hint_text=raw_house,

            )

            return



        recent_ctx["addr_step"] = "WAIT_PHONE"

        _RECENT_CONTEXT[sender] = recent_ctx

        _reply_to_facebook(

            sender,

            f"✅ บันทึกที่อยู่จัดส่งครบถ้วนแล้วค่ะ:\n"

            f"🏠 {full_addr}\n"

            f"━━━━━━━━━━━━━━━━━━\n"

            f"📞 ขั้นสุดท้าย (3/3 : เบอร์โทรศัพท์ผู้รับ) :\n"

            f"👉 พิมพ์เฉพาะ 'เบอร์โทรศัพท์มือถือ 10 หลัก' (เช่น 0891234567) ส่งมาได้เลยจ้ะ\n(ชื่อผู้รับป้าเข็มดึงจากชื่อเฟซบุ๊กให้เลย ไม่ต้องพิมพ์ซ้ำจ้า 😊)",

            [{"content_type": "text", "title": "✏️ แก้ไขที่อยู่", "payload": "QR_NEW_ADDR"}],

            page_id=page_id,

        )

        return



    # 2.4 ขั้นที่ 3/3: ลูกค้าพิมพ์ "เบอร์โทรศัพท์ 10 หลัก (พร้อมชื่อผู้รับ)" เมื่อมีที่อยู่ครบแล้ว (WAIT_PHONE)

    if recent_ctx.get("addr_step") == "WAIT_PHONE" and recent_ctx.get("saved_address") and has_complete_thai_address(recent_ctx["saved_address"]):

        if phone_match and validate_thai_phone(phone_match.group(1))["valid"]:

            valid_ph = validate_thai_phone(phone_match.group(1))["phone"]

            name_part = re.sub(r"0[2689]\d[\d\s-]{6,12}", "", text).strip()

            name_part = re.sub(r"^(?:ชื่อผู้รับ|ชื่อ|คุณ|โทร|เบอร์โทร|เบอร์)\s*[:：-]?\s*", "", name_part).strip(" ,.-/()")

            recent_ctx["saved_phone"] = valid_ph

            if name_part:

                recent_ctx["saved_name"] = name_part

            route_ph = calculate_shipping_route_info(recent_ctx["saved_address"])

            if recent_ctx.get("pkg") != "2kg" and (not recent_ctx.get("pay") or (recent_ctx.get("pay") == "cod" and not route_ph["allow_cod"])):

                _prompt_payment_choice_for_area(sender, recent_ctx, recent_ctx["saved_address"], route_ph, page_id=page_id)

                return

            _finalize_facebook_order(

                sender,

                full_address=recent_ctx["saved_address"],

                phone=valid_ph,

                recent_ctx=recent_ctx,

                page_id=page_id,

                customer_name=name_part,

                raw_hint_text=text,

            )

            return

        else:

            cand_d = re.sub(r"\D", "", text)

            p_chk = validate_thai_phone(cand_d)

            _reply_to_facebook(

                sender,

                f"⚠️ {p_chk['reason']}\n"

                f"🏠 ที่อยู่ที่บันทึกไว้: {recent_ctx['saved_address']}\n\n"

                f"👉 รบกวนพิมพ์ 'เบอร์โทรศัพท์มือถือ 10 หลักที่ติดต่อได้จริง' (เช่น 089-xxx-xxxx) ส่งมาอีกครั้งนะคะ 😊",

                page_id=page_id,

            )

            return



    # 2.5 กรณีลูกค้าพิมพ์ ชื่อ-ที่อยู่-เบอร์โทร รวดเดียวในข้อความเดียว (หรือส่งรูปหน้าซองจดหมาย)

    raw_digits_all = re.sub(r"\D", "", text)

    has_invalid_phone_attempt = bool(re.search(r"0\d{6,12}", raw_digits_all)) and not (

        phone_match and validate_thai_phone(phone_match.group(1))["valid"]

    )



    if has_address or is_tambon_reply or has_invalid_phone_attempt or (phone_match and (recent_ctx.get("saved_address") or len(text) > 20)):

        guidance_reply, tambon_qrs, addr_state = build_incomplete_order_guidance(

            text,

            saved_address=recent_ctx.get("saved_address") or "",

            saved_phone=recent_ctx.get("saved_phone") or "",

            greeting="สวัสดีค่ะคุณลูกค้า 🙏💕",

        )

        merged_a = addr_state["saved_address"]

        merged_p = addr_state["saved_phone"]

        recent_ctx["saved_address"] = merged_a

        recent_ctx["saved_phone"] = merged_p

        recent_ctx["ts"] = time.time()



        # 1) หากที่อยู่ยังไม่ครบ -> แยกตัวนำทางทีละขั้น (1.รหัสไปรษณีย์/อำเภอ -> 2.ปุ่มเลือกตำบล -> 3.บ้านเลขที่)

        if not addr_state["addr_complete"]:

            zip_m_check = re.search(r"\b([1-9]\d{4})\b", merged_a)

            z_info_chk = lookup_thai_zip(zip_m_check.group(1)) if zip_m_check else lookup_thai_area_by_name(merged_a)

            if z_info_chk and z_info_chk["tambons"] and not re.search(r"(?:ต\.|ตำบล|แขวง)", merged_a):

                t_pref = "แขวง" if z_info_chk["is_bkk"] else "ต."

                d_pref = "" if z_info_chk["amphoe"].startswith("เขต") else ("เขต" if z_info_chk["is_bkk"] else "อ.")

                p_pref = "" if z_info_chk["is_bkk"] else "จ."

                has_house_in_a = bool(re.search(r"\d+/\d+|บ้านเลขที่|หมู่", merged_a))

                recent_ctx["zip_code"] = z_info_chk["zip"]

                recent_ctx["house_filled"] = has_house_in_a

                recent_ctx["waiting_tambon"] = True

                recent_ctx["addr_step"] = "WAIT_TAMBON"

                _RECENT_CONTEXT[sender] = recent_ctx

                t_qrs = [

                    {"content_type": "text", "title": f"{t_pref}{t}"[:20], "payload": f"QR_TAMBON_{t}"}

                    for t in z_info_chk["tambons"][:13]

                ]

                t_list_txt = " / ".join(f"{idx+1}.{t_pref}{t}" for idx, t in enumerate(z_info_chk["tambons"]))

                route_part = calculate_shipping_route_info(merged_a)

                _reply_to_facebook(

                    sender,

                    f"📍 พื้นที่: {d_pref}{z_info_chk['amphoe']} {p_pref}{z_info_chk['province']} {z_info_chk['zip']}\n"

                    f"{route_part['summary_line']}\n"

                    f"━━━━━━━━━━━━━━━━━━\n"

                    f"📌 ขั้นที่ 1/3 (เลือก{t_pref}) :\n"

                    f"มี{t_pref}ดังนี้ค่ะ: {t_list_txt}\n\n"

                    f"👇 กดปุ่มเลือก '{t_pref}' ด้านล่าง (หรือพิมพ์ชื่อตำบล) ได้เลยค่ะ:",

                    t_qrs,

                    page_id=page_id,

                )

                return



            # กรณีลูกค้าพิมพ์มาเฉพาะบ้านเลขที่/หมู่ แต่ยังไม่ได้ระบุ อำเภอ/จังหวัด หรือ รหัสไปรษณีย์

            recent_ctx["saved_house_no"] = merged_a

            recent_ctx["house_filled"] = True

            recent_ctx["addr_step"] = "WAIT_ZIP"

            _RECENT_CONTEXT[sender] = recent_ctx

            _reply_to_facebook(

                sender,

                f"✅ บันทึกบ้านเลขที่: {merged_a} เรียบร้อยค่ะ 🏠\n"

                f"━━━━━━━━━━━━━━━━━━\n"

                f"📮 ขั้นต่อไป (ระบุ อำเภอ/จังหวัด หรือ รหัสไปรษณีย์) :\n"

                f"👉 พิมพ์ 'รหัสไปรษณีย์ 5 หลัก' (เช่น 13220) หรือพิมพ์ 'ชื่ออำเภอ/เขต' (เช่น อำเภอบางปะหัน) ส่งมาได้เลยจ้ะ เดี๋ยวป้าเข็มขึ้นปุ่มตำบลให้กดเลือกค่ะ 😊",

                page_id=page_id,

            )

            return



        # 2) หากมี ตำบล+อำเภอ+จังหวัด ครบแล้ว แต่ยังขาด "เบอร์โทรศัพท์ผู้รับ 10 หลัก" -> เข้าตัวนำทางถามเบอร์โทร 10 หลัก!

        if not addr_state["phone_complete"]:

            recent_ctx["house_filled"] = True

            recent_ctx["addr_step"] = "WAIT_PHONE"

            _RECENT_CONTEXT[sender] = recent_ctx

            _reply_to_facebook(

                sender,

                f"✅ บันทึกที่อยู่จัดส่งครบถ้วนแล้วค่ะ:\n"

                f"🏠 {merged_a}\n"

                f"━━━━━━━━━━━━━━━━━━\n"

                f"📞 ขั้นสุดท้าย (เบอร์โทรศัพท์ผู้รับ 10 หลัก) :\n"

                f"👉 พิมพ์เฉพาะ 'เบอร์โทรศัพท์มือถือ 10 หลัก' (ตัวอย่าง: 089-xxx-xxxx) ส่งมาได้เลยจ้า 😊",

                [{"content_type": "text", "title": "✏️ แก้ไขที่อยู่", "payload": "QR_NEW_ADDR"}],

                page_id=page_id,

            )

            return



        _finalize_facebook_order(

            sender,

            full_address=merged_a,

            phone=merged_p,

            recent_ctx=recent_ctx,

            page_id=page_id,

            raw_hint_text=text,

        )

        return



    # 3. ลูกค้าทิ้งเฉพาะเบอร์โทร (จำเบอร์ไว้ในบริบท)

    if phone_match and not has_address and len(text) <= 35:

        phone = phone_match.group(1)

        recent_ctx["saved_phone"] = phone

        recent_ctx["ts"] = time.time()

        _RECENT_CONTEXT[sender] = recent_ctx

        page_label = _get_page_label(page_id)

        _reply_to_facebook(sender, f"ป้าเข็มบันทึกเบอร์โทร {phone} ไว้ให้เรียบร้อยแล้วจ้ะ 🙏🐟\n👉 รบกวนพิมพ์แจ้ง 'ชื่อผู้รับ + ที่อยู่จัดส่ง (บ้านเลขที่/ตำบล/อำเภอ/จังหวัด)' และชุดที่ต้องการ (พิมพ์ 1=500g, 2=1กก., 3=2กก.) ในแชทนี้ได้เลยนะคะ เดี๋ยวระบบออกรหัสคำสั่งซื้อจัดส่งให้ทันทีค่ะ 😊", page_id=page_id)

        _send_telegram_alert(f"📞 [ลูกค้าทิ้งเบอร์ให้โทรกลับ!]\n🏠 เพจ: {page_label}\n👤 Facebook: `{sender}`\n📱 เบอร์: **`{phone}`**\n💬 ข้อความ: \"{text}\"")

        return



    # 4. ลูกค้าพิมพ์ ยืนยัน / ตกลง

    if lower_text in ("ตกลง", "ยืนยัน", "ตกลงค่ะ", "ตกลงครับ", "ยืนยันค่ะ", "ยืนยันครับ", "ok", "โอเค"):

        page_label = _get_page_label(page_id)

        _reply_to_facebook(sender, "ขอบพระคุณค่ะ 🙏 ทางร้านล็อกคิวเตรียมจัดส่งรอบสดใหม่ให้เรียบร้อยแล้วนะคะ เมื่อพัสดุออกเดินทางจะแจ้งให้ทราบค่ะ 😊", page_id=page_id)

        _send_telegram_alert(f"✅ [ลูกค้ายืนยันออเดอร์แล้ว!]\n🏠 เพจ: {page_label}\n👤 Facebook: `{sender}`")

        return



    # 5. ขอเลขบัญชี / โอนเงิน / จ่ายเงินเลย

    if qr_payload == "QR_BANK_INFO" or any(k in lower_text for k in ["เลขบัญชี", "ขอเลขบัญชี", "โอนเงิน", "เลขที่บัญชี", "บัญชีธนาคาร", "โอนจ่าย", "จ่ายเงิน", "พร้อมเพย์", "โอนส่งฟรี"]):

        _RECENT_CONTEXT[sender] = {"pkg": _RECENT_CONTEXT.get(sender, {}).get("pkg"), "pay": "transfer", "ts": time.time()}

        bank_msg = (

            "✅ โอนเงินล่วงหน้า จัดส่งด่วนแพ็กซองฟอยล์เก็บความเย็น ฟรีทุกชุดค่ะ 🚚❄️\n\n"

            "🏦 ธนาคารกรุงไทย (Krungthai)\n"

            "• เลขที่บัญชี: 038-0-25363-1\n"

            "• ชื่อบัญชี: นายจีรวัฒน์ พลอาจ\n\n"

            "📦 ยอดโอนตามขนาดชุด (รวมส่งฟรีแล้ว):\n"

            "• ชุดพอดีมื้อ 450–500 กรัม (ประมาณ 2 ตัวจัมโบ้) = 390 บาท\n"

            "• ชุดขายดี 900–1,000 กรัม (ประมาณ 4 ตัวจัมโบ้) = 550 บาท ⭐\n"

            "• ชุดตุนสุดคุ้ม 1.8–2.0 กิโลกรัม (ประมาณ 8 ตัวจัมโบ้) = 1,090 บาท (ส่งฟรีรถห้องเย็น!)\n\n"

            "👉 โอนเรียบร้อยแล้ว ส่งรูปสลิป + พิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทรศัพท์' ในแชทนี้ได้เลยนะคะ ขอบพระคุณค่ะ 🙏😊"

        )

        _reply_to_facebook(sender, bank_msg, page_id=page_id)

        return



    # 5.5 ตรวจจับคลังคำถาม-คำตอบอัจฉริยะ 13 หมวดจากไฟล์ CSV (data/fish_faq_rules.csv)

    try:

        from app.services.fish_faq_engine import match_faq_rule

        csv_matched = match_faq_rule(text, greeting="สวัสดีค่ะคุณลูกค้า 🙏💕", web_url=WEB_STORE_URL)

        if csv_matched and csv_matched.get("comment_reply"):
            qrs_to_send = None if csv_matched.get("rule_id") == "FAQ_44_ORDER_LATER_FESTIVAL" else DEFAULT_QUICK_REPLIES
            _reply_to_facebook(sender, csv_matched["comment_reply"], qrs_to_send, page_id=page_id)

            return

    except Exception as e:

        logger.warning(f"[facebook] fish_faq_engine error: {e}")



    # 6. ถามเรื่องความเค็ม / รสชาติ

    if any(k in lower_text for k in ["เค็มไหม", "เค็มมั้ย", "รสชาติ", "เค็มมาก"]):

        _reply_to_facebook(sender, f"ไม่เค็มจัดแน่นอนค่ะ ป้าเข็มหมักเกลือสมุทรเพียง 3% กลมกล่อมกำลังดี ทอดกรอบนอกนุ่มในค่ะ 🐟\n\n{MENU_SHORT}", DEFAULT_QUICK_REPLIES, page_id=page_id)

        return



    # 7. ถามเรื่องค่าส่ง / ปลายทาง / ส่งกี่วัน

    if any(k in lower_text for k in ["ส่งยังไง", "ส่งฟรีไหม", "ค่าส่ง", "ปลายทาง", "เก็บเงินปลายทาง", "cod", "กี่วัน", "ส่งวันไหน"]):

        _reply_to_facebook(sender, f"🚚 โอนเงินส่งฟรีถึงหน้าบ้านทุกชุดค่ะ! ทางร้านงดรับเก็บเงินปลายทาง (No COD) ทุกกรณีนะคะ\nแพ็กซองฟอยล์เก็บความเย็นส่งถึงหน้าบ้านใน 1-2 วันค่ะ\n\n{MENU_SHORT}", DEFAULT_QUICK_REPLIES, page_id=page_id)

        return



    # 7.8 สั่งซื้อด่วน / ยืนยันสั่ง (เช่น ทำเลย, จัดเลย, เอาเลย, สั่งเลย, ส่งมาเลย, ตกลง, โอเค)

    is_confirm_order = any(w in lower_text for w in [

        "ทำเลย", "จัดเลย", "เอาเลย", "สั่งเลย", "ส่งเลย", "ส่งมาเลย", "ตกลง", "โอเค", "จองเลย",

        "เอาครับ", "เอาค่ะ", "จัดมา", "จัดส่งเลย", "ลุยเลย", "เอา1โล", "เอา 1 โล", "เอา1กิโล", "เอา 1 กิโล"

    ])

    if is_confirm_order:

        order_guide = (

            "รับทราบเลยจ้าคุณพี่! ยินดีจัดส่งให้เลยค่ะ 🐟✨\n\n"

            "คุณพี่เลือกรับชุดไหนดีคะ (กดปุ่มด้านล่าง หรือพิมพ์ 1, 2, 3 ได้เลยจ้า):\n"

            "• 1 = ชุด 500 กรัม (390.-)\n"

            "• 2 = ชุด 1 กิโล (550.-) ⭐ ขายดีสุด\n"

            "• 3 = ชุด 2 กิโล (1,090.-) ส่งฟรีรถเย็น\n\n"

            "แล้วพิมพ์ 'ชื่อ - ที่อยู่ - เบอร์โทร' ในแชทนี้ได้เลยนะคะ เดี๋ยวป้าเข็มรีบแพ็กส่งให้จ้า 💕"

        )

        _reply_to_facebook(sender, order_guide, DEFAULT_QUICK_REPLIES, page_id=page_id)

        return



    # 7.9 กรณีเป็นคำถามแปลกๆ นอกเหนือ 26 หมวดใน CSV -> ให้ AI ตอบตามข้อมูลจริง หรือรับเรื่องส่งต่อแอดมิน พร้อมแจ้งเตือนเข้า Telegram ทันที!

    try:

        from app.services.fish_faq_engine import answer_out_of_csv_question

        out_res = answer_out_of_csv_question(text, greeting="สวัสดีค่ะคุณลูกค้า 🙏💕", web_url=WEB_STORE_URL)

        if out_res and out_res.get("reply"):

            # Anti-spam debounce: ถ้าเพิ่งส่ง handoff ให้ sender นี้ภายใน 60 วิ ไม่ส่งซ้ำ
            _now_ts = time.time()
            _last_handoff = _RECENT_HANDOFF_USERS.get(sender, 0)
            _skip_reply = (_now_ts - _last_handoff) < _HANDOFF_COOLDOWN_SECONDS

            if not _skip_reply:
                _reply_to_facebook(sender, out_res["reply"], DEFAULT_QUICK_REPLIES, page_id=page_id)
                _RECENT_HANDOFF_USERS[sender] = _now_ts

            page_label = _get_page_label(page_id)

            mode_tag = "🤖 AI ตอบตามข้อมูลจริง" if out_res.get("mode") == "AI_GROUNDED" else "🙋‍♀️ รับเรื่องรอแอดมินตอบ"

            _send_telegram_alert(

                f"❓ [พบคำถามใหม่นอก CSV ใน Messenger!]\n"

                f"🏠 เพจ: {page_label}\n"

                f"👤 ลูกค้า: `{sender}`\n"

                f"💬 คำถาม: \"{text}\"\n"

                f"📌 สถานะ: {mode_tag}\n"

                f"⏰ เวลา: {now_str}"

            )

            return

    except Exception as e:

        logger.warning(f"[facebook] answer_out_of_csv_question error: {e}")



    # 8. ทักทายทั่วไป หรือข้อความสั้นๆ (เช่น สวัสดี / สนใจ) -> ส่งเมนูสั้น กระชับ ทันที

    _reply_to_facebook(sender, MENU_SHORT, DEFAULT_QUICK_REPLIES, page_id=page_id)







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

