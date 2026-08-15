# -*- coding: utf-8 -*-
"""Facebook Messenger Webhook — GET verify (challenge) + POST รับ events (ตรวจ signature).

ทำขั้นที่ 1–2 ของ docs/facebook-architecture-guide.md ให้เป็นจริง:
  1. สร้าง endpoint /api/webhooks/facebook (GET verify + POST รับ events)
  2. GET ตอบ hub.challenge กลับเมื่อ hub.verify_token ตรง (Facebook ยิงมาทดสอบ)
  POST ตรวจ X-Hub-Signature-256 (HMAC-SHA256 ด้วย App Secret) กันปลอมแปลง

หน้าทีของเพจ Facebook: แนะนำบอทป้าเข็ม (LINE bot) — ใครทักแชทมา ตอบแนะนำ
บอท + วิธีคุย (แอดไลน์) ไม่ค้นสินค้า ไม่โพสต์สินค้า (ตามที่เจ้าของร้านสั่ง)
"""
import hashlib
import hmac
import json
import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger(__name__)

# Fallback mock เมื่อ env ไม่ได้ตั้ง (dev/test เปิด app ได้ไม่ crash — เหมือน LINE bot)
FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET") or "mock_facebook_app_secret"
FACEBOOK_VERIFY_TOKEN = os.getenv("FACEBOOK_VERIFY_TOKEN") or "mock_facebook_verify_token"
FACEBOOK_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or ""

router = APIRouter(prefix="/webhooks", tags=["facebook"])

# ชื่อร้าน/บอทป้าเข็ม — ข้อความแนะนำให้ลูกค้าเพจไปคุยต่อที่ LINE
BOT_NAME = "ป้าเข็ม ขายของ"

BOT_INTRO = (
    f"🤗 สวัสดีค่ะ! ยินดีต้อนรับสู่ร้าน {BOT_NAME} 💕\n\n"
    "ป้าเข็มคือผู้ช่วยช้อปของดีจาก Shopee ให้คุณจ๊ะ:\n"
    "🔍 ค้นหาสินค้า — พิมพ์ชื่อ เช่น \"หูฟัง\" หรือ \"หูฟังไม่เกิน 300\"\n"
    "🧠 จำความชอบ — บอก \"จำไว้ ชอบหูฟัง\" ป้าเข็มจะแนะนำของตรงใจ\n"
    "📉 แจ้งราคาลง — ของที่สนใจลดราคา ป้าเข็มรีบบอก\n"
    "📦 เช็คพัสดุ — ถาม \"สั่งแล้ว\" ได้เลย\n\n"
    "💰 ราคาเท่ากับ Shopee เป๊ะ ไม่บวกเพิ่ม ตรวจลิงก์สินค้าจริงทุกตัว\n\n"
    "👉 คุยกับป้าเข็ม 24 ชม. ได้ที่ LINE แอดไลน์ร้าน \"ป้าเข็ม ขายของ\" ได้เลยนะคะ"
)


def _verify_signature(body: bytes, signature: str) -> bool:
    """ตรวจลายเซ็น X-Hub-Signature[-256] — sha256=<hex HMAC(body, app_secret)>"""
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
    """ส่งข้อความกลับแชทผ่าน Send API (ต้องตั้ง FACEBOOK_PAGE_ACCESS_TOKEN ก่อน)"""
    if not FACEBOOK_PAGE_ACCESS_TOKEN:
        return False
    try:
        r = httpx.post(
            "https://graph.facebook.com/v21.0/me/messages",
            params={"access_token": FACEBOOK_PAGE_ACCESS_TOKEN},
            json={"recipient": {"id": recipient_id}, "message": {"text": text}},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"[facebook] send failed: {e}")
        return False


def _handle_event(event: dict) -> None:
    """จัดการ 1 messaging event — ตอบแนะนำบอทป้าเข็ม (ไม่ค้น/ไม่โพสต์สินค้า)"""
    sender = (event.get("sender") or {}).get("id")
    message = event.get("message") or {}
    if not sender:
        return
    text = message.get("text") or ""
    if not text:
        return
    logger.info(f"[facebook] message from {sender}: {text[:200]}")
    _reply_to_facebook(sender, BOT_INTRO)


@router.get("/facebook")
async def verify_webhook(request: Request):
    """Facebook ตั้งค่า webhook → ยิง GET มาทดสอบ verify token → ตอบ hub.challenge กลับ"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == FACEBOOK_VERIFY_TOKEN and challenge:
        logger.info("[facebook] webhook verify OK")
        return Response(content=challenge, media_type="text/plain")
    logger.warning("[facebook] verify rejected: mode=%s token_match=%s",
                   mode, token == FACEBOOK_VERIFY_TOKEN)
    raise HTTPException(status_code=403, detail="webhook verify failed")


@router.post("/facebook")
async def receive_events(request: Request):
    """รับ events จาก Facebook — ตรวจ signature ก่อน แล้ว log/ตอบ (ตอบ 200 เร็วเสมอ)"""
    body = await request.body()

    # Production: ต้องมีลายเซ็นจริง; dev/test (secret ยัง mock) เปิด bypass ไว้ลองเครื่อง
    if FACEBOOK_APP_SECRET != "mock_facebook_app_secret":
        sig = (request.headers.get("X-Hub-Signature-256")
               or request.headers.get("X-Hub-Signature"))
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
