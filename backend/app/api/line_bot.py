import os
import json
import re
import logging
import inspect
from typing import List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Header, Request
from sqlalchemy.orm import Session
import datetime
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextMessage, MessageEvent, TextSendMessage, StickerMessage, StickerSendMessage, Sender
from pydantic import BaseModel

from app.db import SessionLocal, get_db
from app import models

logger = logging.getLogger(__name__)

# Fallback to dummy tokens if not set in environment (prevents crash on initialization in dev/test)
LINE_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN') or "mock_line_channel_token"
LINE_SECRET = os.getenv('LINE_CHANNEL_SECRET') or "mock_line_channel_secret"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# ชื่อร้าน/บอทที่แสดงบนข้อความตอบกลับ (ชื่อหัวแชทตั้งที่ LINE Official Account Manager)
BOT_NAME = "ป้าเข็ม ขายของ"
BOT_ICON_URL = "https://profile.line-scdn.net/0hERy_y3n3Gn1EJgY083hlKnhjFBAzCBw1PEVTE2UuR01sRAh-e0FdS2YmQEw-EF5_LBBcG2UiREg7"

router = APIRouter(
    prefix="/webhooks",
    tags=["chatbot"],
    responses={404: {"description": "Not found"}},
)


class Line(BaseModel):
    destination: str
    events: List[Optional[None]]


def handle_events_manually(handler: WebhookHandler, events: list, destination: str):
    """Manually dispatch LINE events to registered handlers (bypassing signature check)"""
    for event in events:
        func = None
        key = None

        if isinstance(event, MessageEvent):
            key = handler._WebhookHandler__get_handler_key(
                event.__class__, event.message.__class__)
            func = handler._handlers.get(key, None)

        if func is None:
            key = handler._WebhookHandler__get_handler_key(event.__class__)
            func = handler._handlers.get(key, None)

        if func is None:
            func = handler._default

        if func is not None:
            arg_spec = inspect.getfullargspec(func)
            args_count = len(arg_spec.args)
            has_varargs = arg_spec.varargs is not None
            if has_varargs or args_count == 2:
                func(event, destination)
            elif args_count == 1:
                func(event)
            else:
                func()


@router.post("/line")
async def callback(request: Request, x_line_signature: str = Header(None)):
    body = await request.body()
    try:
        body_str = body.decode("utf-8")
    except UnicodeDecodeError as e:
        logger.error(f"Invalid UTF-8 webhook body: {e}")
        raise HTTPException(status_code=400, detail="chatbot handle body error: invalid UTF-8")
    
    # Bypass verification for testing/mock setup if signature is missing or secret is mock
    if not x_line_signature or LINE_SECRET == "mock_line_channel_secret" or x_line_signature == "mock":
        try:
            body_json = json.loads(body_str)
            events = []
            for event in body_json.get('events', []):
                event_type = event.get('type')
                if event_type == 'message':
                    events.append(MessageEvent.new_from_json_dict(event))
            
            dest = body_json.get("destination", "")
            handle_events_manually(handler, events, dest)
            return 'OK'
        except Exception as e:
            logger.error(f"Error parsing mock event: {e}")
            raise HTTPException(status_code=400, detail=f"chatbot handle body error: {e}")
            
    try:
        handler.handle(body_str, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="chatbot handle body error.")
    return 'OK'


BADGE_NEW = "🆕 ของใหม่"
BADGE_HOT = "🔥 ขายดี"
BADGE_COMMISSION = "💎 คอมสูง"


def parse_price_conditions(text: str) -> Tuple[Optional[float], Optional[float]]:
    """เข้าใจเงื่อนไขราคาแบบไทย: 'ไม่เกิน 300', '300 บาท', 'งบ 500', '300-500', 'ไม่แพงกว่า 150'"""
    t = text.replace(",", "").replace(" ", "").lower()
    # ช่วงราคา เช่น 300-500 / 300ถึง500 / 300–500
    m = re.search(r"(\d{2,})\s*(?:-|–|ถึง)\s*(\d{2,})", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    # "ไม่เกิน 300" / "งบ 300" / "ราคา 300" / "ประมาณ 300" / "ถูกกว่า 150"
    m = re.search(r"(?:ไม่เกิน|ไม่แพงกว่า|ไม่แพง|ต่ำกว่า|ถูกกว่า|งบ|ในงบ|ราคา|ประมาณ|ภายใน|ซื้อได้ใน)\s*(\d+(?:\.\d+)?)", t)
    if m:
        return None, float(m.group(1))
    # "300 บาท"
    m = re.search(r"(\d+(?:\.\d+)?)\s*บาท", t)
    if m:
        return None, float(m.group(1))
    return None, None


def get_catalog_badges(db: Session) -> dict:
    """id -> badge text, คำนวณเทียบกับทั้งคลัง (NEW 14 วัน / ขายดี คอมสูง อันดับ 1 ใน 5)"""
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
    now = datetime.datetime.utcnow()
    badges = {}
    for rid, sales_count, commission, created_at in rows:
        b = []
        if created_at and (now - created_at).days <= 14:
            b.append(BADGE_NEW)
        if (sales_count or 0) > 0 and (sales_count or 0) >= sales_threshold:
            b.append(BADGE_HOT)
        if float(commission or 0) > 0 and float(commission or 0) >= comm_threshold:
            b.append(BADGE_COMMISSION)
        badges[rid] = " ".join(b)
    return badges


def format_product_message(db: Session, user: models.User, products: list, title: Optional[str] = None) -> str:
    """Format a product list into the reply message (พร้อมป้าย 🆕/🔥/💎)"""
    if not products:
        return (
            f"สวัสดีครับคุณ {user.name} 👋\n\n"
            "⚠️ ยังไม่มีสินค้าในระบบชั่วคราวครับ\n\n"
            "คุณสามารถเพิ่มสินค้าเข้าระบบก่อนได้ผ่านหน้า Dashboard หรือ API ของเรา เพื่อให้ระบบ AI ประเมินและสร้างสคริปต์ได้ครับ"
        )

    header = title or f"⭐ สินค้าแนะนำขายดีวันนี้สำหรับคุณ {user.name} ⭐\n"
    message_lines = [header]
    badges_map = get_catalog_badges(db)

    for i, prod in enumerate(products, 1):
        # Look for standard content script
        content = db.query(models.Content).filter(
            models.Content.product_id == prod.id,
            models.Content.style == "Standard"
        ).first()

        # Or fall back to any style if Standard not available
        if not content:
            content = db.query(models.Content).filter(models.Content.product_id == prod.id).first()

        hook_text = ""
        if content and content.hook:
            hook_text = f"💡 แนวทางคอนเทนต์ (Hook):\n\"{content.hook}\"\n"

        commission_text = ""
        if prod.commission and float(prod.commission) > 0:
            commission_text = f"💸 ค่านายหน้า: {prod.commission} บาท\n"

        badge_line = ""
        badge = badges_map.get(prod.id, "")
        if badge:
            badge_line = f"{badge}\n"

        message_lines.append(
            f"{i}. {prod.name}\n"
            f"{badge_line}"
            f"💰 ราคา: {prod.price} บาท\n"
            f"{commission_text}"
            f"📈 คะแนนความน่าทำคลิป: {prod.ai_score}/100\n"
            f"{hook_text}"
            f"🔗 ลิงก์ Affiliate: {prod.affiliate_url or 'ไม่มีลิงก์'}\n"
        )

    message_lines.append("ลองนำแนวทางหัวข้อนี้ไปถ่ายทำคอนเทนต์ด่วน ๆ เลยครับ! 🚀")
    return "\n".join(message_lines)


def handle_today_deals(db: Session, user: models.User) -> str:
    """วันนี้ขายอะไรดี — หมุนเวียนสินค้าจากกลุ่มคะแนนสูงสุด (เลื่อนวันละ 1 ตัว)
    เพื่อให้สินค้าใหม่ ๆ ได้โผล่หน้าแนะนำด้วย ไม่ใช่ซ้ำชุดเดิมทุกวัน
    นโยบายเด็ดขาด: ตอบเฉพาะสินค้าที่ตรวจลิงก์แล้วว่า OK เท่านั้น"""
    pool = (db.query(models.Product)
              .filter(models.Product.link_status == "ok")
              .order_by(models.Product.ai_score.desc()).limit(9).all())
    if not pool:
        return format_product_message(db, user, [])
    # เลื่อนหน้าต่าง 3 ตัว ตามวันที่ (day-of-year) → วันใหม่ได้ชุดใหม่ ไม่ซ้ำ
    day_of_year = int(datetime.datetime.utcnow().strftime("%j"))
    start = day_of_year % len(pool)
    window = (pool + pool)[start:start + 3]
    return format_product_message(db, user, window)


DEAL_PHRASES = (
    "ขายอะไรดี", "ขายอะไร", "อะไรขายดี", "อะไรขาย", "มีอะไรขาย", "ขายดี",
    "สินค้าแนะนำ", "แนะนำสินค้า", "สินค้าขายดี", "ช่วยแนะนำ", "แนะนำหน่อย",
    "สินค้า", "แนะนำ", "ขาย", "เมนู",
)


def is_deal_query(text: str) -> bool:
    """แยก 'ขอสินค้าแนะนำ' ออกจาก 'คำค้นสินค้า' — 'หูฟังขายดี' ต้องไปค้น ไม่ใช่เมนูแนะนำ"""
    t = text.rstrip("?？ ").strip()
    return t in DEAL_PHRASES or "วันนี้ขายอะไรดี" in t


def search_products(db: Session, query: str) -> list:
    """ค้นสินค้า: ตรงชื่อ/หมวด + เข้าใจเงื่อนไขราคา ('หูฟังไม่เกิน 300', 'งบ 500',
    'กระติก 200-400') — จัดอันดับความตรง แล้วตอบสูงสุด 3 ตัว
    นโยบายเด็ดขาด: ตอบเฉพาะสินค้าที่ตรวจลิงก์แล้วว่า OK เท่านั้น"""
    products = db.query(models.Product).filter(models.Product.link_status == "ok").all()
    q = query.lower().strip()
    if not q:
        return []
    min_price, max_price = parse_price_conditions(query)

    def match_weight(p) -> int:
        name = (p.name or "").lower()
        cat = (p.category or "").lower()
        w = 0
        if q in name:
            w += 3
        if q in cat:
            w += 2
        # 4+ char substrings (helps with Thai phrases like "อยากได้หูฟัง")
        subs = {q[i:j] for i in range(len(q)) for j in range(i + 4, len(q) + 1)}
        if any(s in name for s in subs):
            w += 1
        if any(s in cat for s in subs):
            w += 1
        return w

    def in_budget(p) -> bool:
        price = float(p.price or 0)
        return (min_price is None or price >= min_price) and (max_price is None or price <= max_price)

    hits = [(p, w) for p in products if (w := match_weight(p)) > 0]
    if min_price is not None or max_price is not None:
        budget_hits = [(p, w) for p, w in hits if in_budget(p)]
        if budget_hits:
            hits = budget_hits
        else:
            # ไม่มีตัวที่ตรงชื่อ+งบพร้อมกัน → เอาตามงบแทน (ดีกว่าไม่ตอบ)
            budget_all = sorted([p for p in products if in_budget(p)], key=lambda p: p.ai_score or 0, reverse=True)
            return budget_all[:3]

    hits.sort(key=lambda pw: (pw[1], pw[0].ai_score or 0), reverse=True)
    return [p for p, _ in hits[:3]]


def get_line_profile_name(line_user_id: str) -> Optional[str]:
    """Fetch the user's real LINE display name (works only for users who added the bot)"""
    try:
        profile = line_bot_api.get_profile(line_user_id)
        return (profile.display_name or "").strip() or None
    except Exception as e:
        logger.warning(f"Could not fetch LINE profile for {line_user_id}: {e}")
        return None


def get_or_create_line_user(db: Session, line_user_id: str) -> models.User:
    """Look up user by LINE user ID or register on the fly"""
    user = db.query(models.User).filter(models.User.line_user_id == line_user_id).first()
    if not user:
        name = get_line_profile_name(line_user_id) or "LINE User"
        user = models.User(
            name=name,
            line_user_id=line_user_id,
            shopee_affiliate_id="SHP_AFF_AUTO"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Registered new LINE user on the fly: {line_user_id}")
    elif user.name == "LINE User":
        # Upgrade the placeholder name with the real LINE display name
        name = get_line_profile_name(line_user_id)
        if name and name != user.name:
            user.name = name
            db.add(user)
            db.commit()
            db.refresh(user)
    return user


@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
    print("!!!!!!!!!!!!!!!!!!!!!!")
    print(event)
    print("!!!!!!!!!!!!!!!!!!!!!!")
    
    user_text = event.message.text.strip()
    # Accept both "วันนี้ขายอะไรดี" and "วันนี้ขายอะไรดี?" — the Thai keyboard doesn't add
    # the ?, and a bare trailing "?" from autocorrect shouldn't break the match either.
    normalized_text = user_text.rstrip("?？ ").strip()
    line_user_id = event.source.user_id
    
    db = SessionLocal()
    try:
        user = get_or_create_line_user(db, line_user_id)
        if is_deal_query(normalized_text):
            # สั่งถามสินค้าแนะนำ — ตอบ 3 อันดับตามคะแนน AI
            reply_text = handle_today_deals(db, user)
        else:
            # พิมพ์อย่างอื่น (เช่น "หูฟัง" "อยากได้กระติกน้ำ" "หูฟังไม่เกิน 300") —
            # ค้นสินค้าที่ตรง (รองรับเงื่อนไขราคา) หรือถ้าไม่ตรงให้ต้อนรับ + แสดงสินค้าแนะนำเลย
            hits = search_products(db, normalized_text)
            if hits:
                reply_text = format_product_message(
                    db, user, hits,
                    title=f"🔍 สินค้าตรงกับ \"{user_text}\" ค่ะ\n"
                )
            else:
                reply_text = (
                    f"🤖 สวัสดีครับคุณ {user.name}! ยินดีต้อนรับสู่ร้าน{BOT_NAME} 😊\n\n"
                    "นี่คือสินค้าแนะนำวันนี้ — แตะลิงก์สั่งซื้อได้เลยครับ 🛒\n\n"
                ) + handle_today_deals(db, user)
    except Exception as e:
        logger.error(f"Error processing LINE message: {e}")
        reply_text = "ขออภัยด้วยครับ ระบบเกิดข้อผิดพลาดชั่วคราว ลองส่งใหม่อีกครั้งนะครับ"
    finally:
        db.close()
        
    if "mock" in LINE_ACCESS_TOKEN.lower():
        logger.info(f"Mock reply sent. ReplyToken: {event.reply_token}, Message: {reply_text}")
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text, sender=Sender(name=BOT_NAME, icon_url=BOT_ICON_URL))
        )


@handler.add(MessageEvent, message=StickerMessage)
def sticker_text(event):
    if "mock" in LINE_ACCESS_TOKEN.lower():
        logger.info(f"Mock sticker reply sent. ReplyToken: {event.reply_token}")
    else:
        line_bot_api.reply_message(
            event.reply_token,
            StickerSendMessage(package_id='6136', sticker_id='10551379')
        )
