import os
import json
import re
import logging
import inspect
from typing import List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Header, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
import datetime
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (TextMessage, MessageEvent, TextSendMessage, StickerMessage,
                            StickerSendMessage, QuickReply, QuickReplyButton,
                            MessageAction, FollowEvent, FlexSendMessage)
from pydantic import BaseModel

from app.db import SessionLocal, get_db
from app import models
from app.services.product_cards import product_cards_message, link_button_message
from app.services.category import guess_category

logger = logging.getLogger(__name__)

# Fallback to dummy tokens if not set in environment (prevents crash on initialization in dev/test)
LINE_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN') or "mock_line_channel_token"
LINE_SECRET = os.getenv('LINE_CHANNEL_SECRET') or "mock_line_channel_secret"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# ชื่อร้าน/บอทที่แสดงบนข้อความตอบกลับ (ชื่อหัวแชทตั้งที่ LINE Official Account Manager)
BOT_NAME = "ป้าเข็ม ขายของ"
BOT_ICON_URL = "https://profile.line-scdn.net/0hERy_y3n3Gn1EJgY083hlKnhjFBAzCBw1PEVTE2UuR01sRAh-e0FdS2YmQEw-EF5_LBBcG2UiREg7"

# ยอดขายขั้นต่ำ (จากคอลัมน์ "ขาย" ตอน import) — สินค้าขายน้อยกว่าเกณฑ์ไม่โผล่หน้าลูกค้า
# (กันสินค้ายอดขายน้อยแทรกหน้าแนะนำ; ตั้ง env MIN_SALES ปรับได้ เช่น 5000/10000)
MIN_SALES = int(os.getenv("MIN_SALES", "2000"))

# LINE userId ของเจ้าของร้าน (คุณ) — เห็นมุมมองแอดมิน (ค่านายหน้า/คะแนน/Hook)
# ลูกค้าคนอื่นเห็นแค่การ์ดสะอาด (ราคา/ยอดขาย/ปุ่มซื้อ) ไม่รกตา
ADMIN_LINE_USER_ID = os.getenv("ADMIN_LINE_USER_ID", "Uc88eb3896b0e4bcc5fbaa9b78ac1294e")

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
    # Postgres (Supabase) คืน created_at แบบ timezone-aware, SQLite คืน naive
    # → normalize เป็น UTC ทั้งคู่ก่อนลบกัน (กัน TypeError ที่ทำให้บอทตอบ error)
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
        if float(commission or 0) > 0 and float(commission or 0) >= comm_threshold:
            b.append(BADGE_COMMISSION)
        badges[rid] = " ".join(b)
    return badges


def format_product_message(db: Session, user: models.User, products: list,
                           title: Optional[str] = None, is_owner: bool = False):
    """สร้างการ์ดสินค้า Flex — ลูกค้าเห็นเฉพาะข้อมูลซื้อ, เจ้าของเห็นข้อมูลแอดมินเพิ่ม"""
    return product_cards_message(db, user, products, title, is_owner=is_owner)


def handle_today_deals(db: Session, user: models.User, is_owner: bool = False) -> str:
    """วันนี้ขายอะไรดี — หมุนเวียนสินค้าจากกลุ่มคะแนนสูงสุด (เลื่อนวันละ 1 ตัว)
    เพื่อให้สินค้าใหม่ ๆ ได้โผล่หน้าแนะนำด้วย ไม่ใช่ซ้ำชุดเดิมทุกวัน
    นโยบายเด็ดขาด: ตอบเฉพาะสินค้าลิงก์ OK + ยอดขายถึงเกณฑ์เท่านั้น"""
    pool = (db.query(models.Product)
              .filter(models.Product.link_status == "ok",
                      models.Product.sales_count >= MIN_SALES)
              .order_by(models.Product.ai_score.desc()).limit(9).all())
    if not pool:
        return product_cards_message(db, user, [], is_owner=is_owner)
    # เลื่อนหน้าต่าง 3 ตัว ตามวันที่ (day-of-year) → วันใหม่ได้ชุดใหม่ ไม่ซ้ำ
    day_of_year = int(datetime.datetime.utcnow().strftime("%j"))
    start = day_of_year % len(pool)
    window = (pool + pool)[start:start + 3]
    return product_cards_message(db, user, window, is_owner=is_owner)


DEAL_PHRASES = (
    "ขายอะไรดี", "ขายอะไร", "อะไรขายดี", "อะไรขาย", "มีอะไรขาย", "ขายดี",
    "สินค้าแนะนำ", "แนะนำสินค้า", "สินค้าขายดี", "ช่วยแนะนำ", "แนะนำหน่อย",
    "สินค้า", "แนะนำ", "ขาย", "เมนู",
)


def is_deal_query(text: str) -> bool:
    """แยก 'ขอสินค้าแนะนำ' ออกจาก 'คำค้นสินค้า' — 'หูฟังขายดี' ต้องไปค้น ไม่ใช่เมนูแนะนำ"""
    t = text.rstrip("?？ ").strip()
    return t in DEAL_PHRASES or "วันนี้ขายอะไรดี" in t


GREETING_WORDS = ("hello", "hi", "hey", "หวัดดี", "ทักทาย", "ดีจ้า", "สวัสดี",
                  "สวัสดีครับ", "สวัสดีค่ะ", "ฮัลโหล", "ไหว้")


def is_greeting(text: str) -> bool:
    """แยกคำทักทายล้วนๆ ออกจากคำค้น — 'สวัสดี อยากได้หูฟัง' ต้องไปค้น ไม่ใช่ทักทาย"""
    t = text.rstrip("?？!. ").strip().lower()
    if t in GREETING_WORDS:
        return True
    return t.startswith("สวัสดี") and len(t) <= 12


def quick_reply_items() -> QuickReply:
    """ปุ่มลัดแบบสากล (Quick Reply) — ลูกค้าแตะแทนพิมพ์"""
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="🔍 ค้นสินค้า", text="ค้นสินค้า")),
        QuickReplyButton(action=MessageAction(label="⭐ ขายดีวันนี้", text="วันนี้ขายอะไรดี")),
        QuickReplyButton(action=MessageAction(label="🔥 อันดับขายดี", text="อันดับขายดี")),
    ])


def greeting_text(user_name: str) -> str:
    """แนวสากล: ทักทาย + ทางเลือก — ไม่ยิงสินค้าใส่หน้าจนกว่าลูกค้าจะบอกความต้องการ"""
    return (
        f"🤗 สวัสดีค่ะคุณ {user_name}! ยินดีต้อนรับสู่ร้าน{BOT_NAME} 💕\n\n"
        "พิมพ์ชื่อสินค้าที่อยากได้ได้เลย เช่น\n"
        "\"หูฟังไม่เกิน 300\" หรือ \"กระติกน้ำ\"\n\n"
        "หรือแตะปุ่มด้านล่าง 👇"
    )


SEARCH_GUIDE = (
    "🔍 ค้นสินค้าค่ะ! ลองพิมพ์แบบนี้:\n\n"
    "• \"หูฟัง\" — ค้นตามชื่อ\n"
    "• \"หูฟังไม่เกิน 300\" — ค้นตามงบ\n"
    "• \"กระติก 200-400\" — ค้นช่วงราคา\n\n"
    "พิมพ์มาได้เลย เดี๋ยวป้าเข็มหาให้ค่ะ 😊"
)


# --- ทวงถาม/ติดตามสินค้า (WISMO — Where's My Order) ---
# เราเป็นนายหน้า — ออเดอร์/พัสดุอยู่ที่ Shopee แนวสากล (Ingrid 2025): ตอบเส้นทางตรวจเอง 24/7
WISMO_KEYWORDS = (
    "เลขพัสดุ", "tracking", "ติดตามพัสดุ", "ติดตามของ", "ตามพัสดุ", "ตามของ",
    "พัสดุอยู่ไหน", "ของอยู่ไหน", "ได้ของยัง", "ได้ของเมื่อไหร่", "ของถึงยัง",
    "ของถึงเมื่อไหร่", "ยังไม่ได้รับ", "ยังไม่ถึง", "สินค้ายังไม่มา", "รอของ",
    "สั่งแล้ว", "สั่งของแล้ว", "ทวง", "ส่งของช้า", "ที่อยู่ผิด", "ของหาย",
    "ไม่ได้รับของ", "สั่งไปแล้ว", "สินค้าอยู่ไหน",
)

WISMO_REPLY = (
    '📦 เช็คสถานะสินค้าได้เลยค่ะ!\n\n'
    'เราเป็นร้านนายหน้าจัดหาสินค้าจาก Shopee — การสั่งซื้อและส่งของจัดการโดยร้านค้าบน Shopee โดยตรง จึงเช็คสถานะได้ที่:\n\n'
    '1️⃣ เปิดแอป Shopee → เมนู ฉัน → การสั่งซื้อของฉัน\n'
    '2️⃣ แตะออเดอร์นั้น → เห็นสถานะ + เลขพัสดุ\n'
    '3️⃣ มีปัญหาส่งของ → กด แชทกับร้านค้า ในหน้านั้นได้เลย\n\n'
    'ถ้ายังไม่ได้สั่งซื้อ พิมพ์ชื่อสินค้าที่อยากได้ได้เลย เดี๋ยวหาลิงก์ดีๆ ให้ค่ะ 😊'
)

# ลิงก์แยกไว้เป็นปุ่มการ์ด (กัน LINE ธง "ไม่ปลอดภัย" เวลา URL อยู่ในข้อความ)
WISMO_BUTTON = link_button_message(
    '🔗 กดปุ่มด้านล่างเพื่อตรวจสถานะออเดอร์และเลขพัสดุบน Shopee',
    'https://shopee.co.th/orders', '📦 ตรวจพัสดุ')



def is_wismo(text: str) -> bool:
    t = text.lower().replace(" ", "")
    return any(kw in t for kw in WISMO_KEYWORDS)


# --- PDPA: สิทธิ์ลบข้อมูล (erasure) + นโยบาย ---
DELETE_PHRASES = ("ลบข้อมูลฉัน", "ลบข้อมูล", "ลบข้อมูลของฉัน", "ลบประวัติ", "ลบประวัติฉัน")

DELETE_REPLY = (
    '🗑️ ลบข้อมูลของคุณเรียบร้อยแล้วค่ะ (ชื่อ + ประวัติการสนทนา)\n\n'
    'ถ้าอยากกลับมาใช้บริการ พิมพ์ สวัสดี ได้เลยนะคะ 😊'
)

PRIVACY_NOTICE = (
    '🔒 นโยบายข้อมูลส่วนบุคคล (PDPA)\n'
    'เราเก็บเฉพาะชื่อและ ID เพื่อเรียกชื่อคุณ และประวัติการสนทนา 90 วัน (เพื่อบริการที่ดีขึ้น)\n\n'
    'ดูรายละเอียดได้จากปุ่มด้านล่าง / สั่งลบข้อมูลได้ทุกเมื่อ: พิมพ์ ลบข้อมูลฉัน'
)

PRIVACY_URL = (os.getenv("RENDER_EXTERNAL_URL") or "https://shopee-affiliate-bot-9e9n.onrender.com").rstrip("/") + "/privacy"
PRIVACY_BUTTON = link_button_message('🔒 นโยบายความเป็นส่วนตัว (PDPA) ของร้าน', PRIVACY_URL, '🔒 นโยบาย PDPA')



def log_chat(db, line_user_id: str, text: str, intent: str, reply, category: Optional[str] = None):
    """บันทึกประวัติสนทนา + หมวดที่ลูกค้าสนใจ (PDPA: เก็บแค่ 90 วัน — ลบของเก่าทุกครั้งที่เขียน)
    category ต่อยอด: รู้ว่าลูกค้าสนใจหมวดอะไร → วิเคราะห์/แนะนำสินค้า/ทำการตลาด"""
    kind = 'flex' if (isinstance(reply, FlexSendMessage) or
                       (isinstance(reply, list) and any(isinstance(m, FlexSendMessage) for m in reply))) else 'text'
    db.add(models.ChatLog(line_user_id=line_user_id, message_text=text[:500],
                          intent=intent, category=category, reply_kind=kind))
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)
    db.query(models.ChatLog).filter(models.ChatLog.created_at < cutoff).delete(synchronize_session=False)
    db.commit()


ADMIN_STATS_CMDS = ("แอดมิน สถิติ", "สถิติลูกค้า", "รายงานลูกค้า", "แอดมินรายงาน")


def admin_customer_stats(db) -> str:
    """สรุปความสนใจลูกค้าจาก chat_logs — ต่อยอดการตลาด/เลือกสินค้า/ตอบปัญหา"""
    total = db.query(models.ChatLog).count()
    searchers = (db.query(models.ChatLog.line_user_id)
                   .filter(models.ChatLog.intent == "search").distinct().count())
    wismo = db.query(models.ChatLog).filter(models.ChatLog.intent == "wismo").count()

    cat_rows = (db.query(models.ChatLog.category, func.count(models.ChatLog.id))
                  .filter(models.ChatLog.category.isnot(None))
                  .group_by(models.ChatLog.category)
                  .order_by(func.count(models.ChatLog.id).desc()).limit(6).all())
    kw_rows = (db.query(models.ChatLog.message_text, func.count(models.ChatLog.id))
                 .filter(models.ChatLog.intent == "search")
                 .group_by(models.ChatLog.message_text)
                 .order_by(func.count(models.ChatLog.id).desc()).limit(8).all())

    lines = ['📊 สถิติลูกค้า (90 วัน)', f'• ข้อความรวม: {total} ครั้ง', f'• ลูกค้าที่ค้นสินค้า: {searchers} คน',
             f'• ทวงถาม/ติดตามพัสดุ: {wismo} ครั้ง']
    if cat_rows:
        lines.append('\n🔥 หมวดที่ลูกค้าสนใจ')
        lines += [f'• {c}: {n} ครั้ง' for c, n in cat_rows]
    if kw_rows:
        lines.append('\n🔍 คำค้นยอดนิยม')
        lines += [f'• {k[:40]}: {n} ครั้ง' for k, n in kw_rows]
    lines.append('\n💡 นำไปใช้: เอาไปหาสินค้าหมวดที่ฮิต + เขียนคอนเทนต์ตามคำค้น')
    return '\n'.join(lines)


def handle_top_sellers(db: Session, user: models.User, is_owner: bool = False) -> str:
    """อันดับขายดี — 3 อันดับตามยอดขายจริง (ลิงก์ OK + ถึงเกณฑ์ขายเท่านั้น)"""
    tops = (db.query(models.Product)
              .filter(models.Product.link_status == "ok",
                      models.Product.sales_count >= MIN_SALES)
              .order_by(models.Product.sales_count.desc()).limit(3).all())
    if not tops:
        return TextSendMessage(text="ตอนนี้ยังไม่มีสินค้าขายดีค่ะ ลองค้นชื่อสินค้าดูได้นะคะ 😊")
    return product_cards_message(db, user, tops, title="🔥 อันดับสินค้าขายดีประจำร้าน", is_owner=is_owner)


# --- สินค้าใหม่ส่วนตัว (Amazon-style: จำที่ลูกค้าสนใจ ไม่ต้องเริ่มใหม่) ---
NEW_PHRASES = ("มีอะไรใหม่", "ของใหม่", "สินค้าใหม่", "อะไรใหม่", "มีของใหม่", "ของใหม่มีอะไร")


def _customer_categories(db, line_user_id: str) -> list:
    """หมวดที่ลูกค้าคนนี้เคยค้น (chat_logs) เรียงตามความถี่ — ใช้แนะนำส่วนตัว"""
    from collections import Counter
    rows = (db.query(models.ChatLog.category)
              .filter(models.ChatLog.line_user_id == line_user_id,
                      models.ChatLog.intent == "search",
                      models.ChatLog.category.isnot(None)).all())
    c = Counter(r[0] for r in rows)
    return [k for k, _ in c.most_common()]


def handle_new_arrivals(db, user, line_user_id: str, is_owner: bool = False):
    """มีอะไรใหม่ — ดันสินค้าใหม่ในหมวดที่ลูกค้าเคยสนใจก่อน (แล้วค่อยของใหม่ทั่วไป)"""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    recent = (db.query(models.Product)
                .filter(models.Product.link_status == "ok",
                        models.Product.sales_count >= MIN_SALES,
                        models.Product.created_at >= cutoff)
                .order_by(models.Product.created_at.desc()).limit(50).all())
    cats = _customer_categories(db, line_user_id)
    if cats:
        matched = [p for p in recent if (p.category or "") in cats]
        if matched:
            return product_cards_message(db, user, matched[:3],
                                         "🆕 สินค้าใหม่ที่อาจถูกใจคุณ! (ตามหมวดที่เคยสนใจ)",
                                         is_owner=is_owner)
    if recent:
        return product_cards_message(db, user, recent[:3],
                                     "🆕 สินค้าใหม่เข้าคลังล่าสุด", is_owner=is_owner)
    return TextSendMessage(text="ตอนนี้ยังไม่มีสินค้าใหม่ค่ะ ลองค้นชื่อสินค้าดู หรือแตะ ขายดีวันนี้ ได้เลยนะคะ 😊")


# --- เอเจนต์ทำแคมเปญ (Alibaba-style: เลือกกลุ่มจากความสนใจจริง → ส่งการ์ด) ---
CAMPAIGN_LIMIT = 20  # สูงสุดต่อแคมเปญ — LINE OA จำกัด push/เดือน กันเกินโควตา


def _campaign_targets(db, category: str) -> list:
    """ลูกค้าที่เคยค้นหมวดนี้ (dedupe, ล่าสุดก่อน) — ไม่รวมเจ้าของร้าน"""
    targets = {}
    rows = (db.query(models.ChatLog.line_user_id, models.ChatLog.created_at)
              .filter(models.ChatLog.intent == "search",
                      models.ChatLog.category == category)
              .order_by(models.ChatLog.created_at.desc()).all())
    for uid, _ in rows:
        if uid not in targets and uid != ADMIN_LINE_USER_ID:
            targets[uid] = True
    return list(targets.keys())[:CAMPAIGN_LIMIT]


def _campaign_products(db, category: str, limit: int = 3) -> list:
    return (db.query(models.Product)
              .filter(models.Product.link_status == "ok",
                      models.Product.sales_count >= MIN_SALES,
                      models.Product.category == category)
              .order_by(models.Product.ai_score.desc()).limit(limit).all())


def handle_campaign(db, raw_text: str, is_owner: bool):
    """แคมเปญ <หมวด> = dry-run | แคมเปญ <หมวด> ส่งเลย = push จริง | แคมเปญ ประวัติ"""
    if not is_owner:
        return None
    parts = raw_text.split()
    if not parts or parts[0] != "แคมเปญ":
        return None
    if len(parts) >= 2 and parts[1] == "ประวัติ":
        rows = (db.query(models.CampaignLog)
                  .order_by(models.CampaignLog.id.desc()).limit(10).all())
        if not rows:
            return TextSendMessage(text="ยังไม่มีแคมเปญที่เคยส่งค่ะ")
        lines = ['📜 ประวัติแคมเปญ']
        for r in rows:
            st = '✅ ส่ง' if r.status == "sent" else '📋 dry-run'
            lines.append(f'• {r.category}: {r.recipients} คน ({st}) — {r.created_at:%d/%m %H:%M}')
        return TextSendMessage(text='\n'.join(lines))
    send_now = any(p in ("ส่งเลย", "ส่ง") for p in parts)
    cat_raw = next((p for p in parts[1:] if p not in ("ส่งเลย", "ส่ง")), "")
    if not cat_raw:
        return TextSendMessage(text="วิธีใช้: แคมเปญ <หมวด> (เช่น แคมเปญ ครีม) เพื่อดูกลุ่มเป้าหมาย\nแล้วสั่ง แคมเปญ <หมวด> ส่งเลย เพื่อส่งจริง")
    category = guess_category(cat_raw)
    products = _campaign_products(db, category)
    targets = _campaign_targets(db, category)
    if not products:
        return TextSendMessage(text=f"แคมเปญ {category}: ยังไม่มีสินค้าลิงก์ดีในหมวดนี้ (นำเข้า CSV ก่อนได้)")
    if not targets:
        return TextSendMessage(text=f"แคมเปญ {category}: ยังไม่มีลูกค้าที่สนใจหมวดนี้ (เก็บสถิติไปก่อน — ยิ่งคุยยิ่งรู้กลุ่มลูกค้า)")
    if not send_now:
        sample = ", ".join(u[:10] for u in targets[:5])
        more = "..." if len(targets) > 5 else ""
        return TextSendMessage(text=f"🎯 แคมเปญ {category} (DRY-RUN — ยังไม่ส่ง)\n"
                                     f"สินค้าที่จะส่ง: {len(products)} ตัว → ลูกค้าเป้าหมาย {len(targets)} คน\n"
                                     f"กลุ่ม: {sample}{more}\n\n"
                                     f"สั่งส่งจริง: แคมเปญ {category} ส่งเลย")
    sent, failed = 0, 0
    for uid in targets:
        u = db.query(models.User).filter(models.User.line_user_id == uid).first()
        name = u.name if u else "LINE User"
        card = product_cards_message(db, type("U", (), {"name": name})(), products,
                                     f"🎁 โปรโมชั่นหมวด {category} สำหรับคุณ!", is_owner=False)
        if "mock" in LINE_ACCESS_TOKEN.lower():
            sent += 1
            continue
        try:
            line_bot_api.push_message(uid, card)
            sent += 1
        except Exception as e:
            logger.warning(f"campaign push fail {uid}: {e}")
            failed += 1
    db.add(models.CampaignLog(category=category, recipients=sent, status="sent"))
    db.commit()
    tail = f" (ล้ม {failed})" if failed else ""
    return TextSendMessage(text=f"✅ ส่งแคมเปญ {category} แล้ว: {sent} คน{tail}\n\nดูประวัติ: แคมเปญ ประวัติ")


def search_products(db: Session, query: str) -> list:
    """ค้นสินค้า: ตรงชื่อ/หมวด + เข้าใจเงื่อนไขราคา ('หูฟังไม่เกิน 300', 'งบ 500',
    'กระติก 200-400') — จัดอันดับความตรง แล้วตอบสูงสุด 3 ตัว
    นโยบายเด็ดขาด: ตอบเฉพาะสินค้าที่ตรวจลิงก์แล้วว่า OK เท่านั้น"""
    products = (db.query(models.Product)
                  .filter(models.Product.link_status == "ok",
                          models.Product.sales_count >= MIN_SALES)
                  .all())
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
    is_owner = line_user_id == ADMIN_LINE_USER_ID
    intent = 'unknown'
    interest_cat = None
    
    db = SessionLocal()
    try:
        user = get_or_create_line_user(db, line_user_id)
        if normalized_text in DELETE_PHRASES:
            # PDPA: สิทธิ์ลบข้อมูล (erasure) — ลบชื่อ + ประวัติการสนทนาทันที
            db.query(models.ChatLog).filter(models.ChatLog.line_user_id == line_user_id).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.line_user_id == line_user_id).delete(synchronize_session=False)
            db.commit()
            reply = TextSendMessage(text=DELETE_REPLY)
            intent = 'delete'
        elif is_wismo(normalized_text):
            # ลูกค้าทวงถาม/ติดตามพัสดุ — แนะนำเส้นทางตรวจเองบน Shopee (24/7)
            # ลิงก์อยู่ในปุ่มการ์ด (ไม่ใช่ข้อความ) — กัน LINE ธง "ไม่ปลอดภัย"
            reply = [TextSendMessage(text=WISMO_REPLY), WISMO_BUTTON]
            intent = 'wismo'
        elif normalized_text in NEW_PHRASES:
            # มีอะไรใหม่ — ดันสินค้าใหม่หมวดที่เคนสนใจ (จำจาก chat_logs)
            reply = handle_new_arrivals(db, user, line_user_id, is_owner)
            intent = 'new'
        elif is_owner and normalized_text.startswith("แคมเปญ"):
            # เอเจนต์ทำแคมเปญ (เฉพาะเจ้าของ) — dry-run ก่อนส่งจริง
            reply = handle_campaign(db, normalized_text, is_owner)
            intent = 'campaign'
        elif is_greeting(normalized_text):
            # แนวสากล: ทักทาย + ปุ่มทางเลือก — ไม่ยิงสินค้าจนกว่าลูกค้าจะบอกความต้องการ
            reply = TextSendMessage(text=greeting_text(user.name),
                                    quick_reply=quick_reply_items())
            intent = 'greeting'
        elif normalized_text == "ค้นสินค้า":
            reply = TextSendMessage(text=SEARCH_GUIDE,)
            intent = 'guide'
        elif is_owner and normalized_text in ADMIN_STATS_CMDS:
            reply = TextSendMessage(text=admin_customer_stats(db))
            intent = 'admin'
        elif normalized_text == "อันดับขายดี":
            reply = handle_top_sellers(db, user, is_owner=is_owner)
            intent = 'top'
        elif is_deal_query(normalized_text):
            # สั่งถามสินค้าแนะนำ — ตอบการ์ด 3 อันดับตามคะแนน AI
            reply = handle_today_deals(db, user, is_owner=is_owner)
            intent = 'deals'
        else:
            # พิมพ์อย่างอื่น (เช่น "หูฟัง" "อยากได้กระติกน้ำ" "หูฟังไม่เกิน 300") —
            # ค้นสินค้าที่ตรง (รองรับเงื่อนไขราคา); ไม่ตรง → แนะนำวิธีใช้ ไม่ยิงสินค้าใส่หน้า
            hits = search_products(db, normalized_text)
            if hits:
                reply = format_product_message(db, user, hits,
                                               title=f"🔍 สินค้าตรงกับ \"{user_text}\" ค่ะ",
                                               is_owner=is_owner)
                intent = 'search'
                interest_cat = guess_category(normalized_text)
            else:
                reply = TextSendMessage(text=greeting_text(user.name),
                                        quick_reply=quick_reply_items())
                intent = 'greeting'
    except Exception as e:
        logger.error(f"Error processing LINE message: {e}")
        reply = TextSendMessage(text="ขออภัยด้วยค่ะ ระบบขัดข้องชั่วคราว ลองส่งใหม่อีกครั้งนะคะ 🙏",)
        intent = 'error'
    finally:
        # คำสั่งลบข้อมูลไม่ควรถูกบันทึกใหม่หลังลบ (PDPA erasure สะอาด)
        if intent != 'delete':
            try:
                log_chat(db, line_user_id, user_text, intent, reply, interest_cat)
            except Exception as e:
                logger.warning(f"log_chat failed: {e}")
        db.close()
        
    if "mock" in LINE_ACCESS_TOKEN.lower():
        logger.info(f"Mock reply sent. ReplyToken: {event.reply_token}, Message: {getattr(reply, 'text', reply)}")
    else:
        line_bot_api.reply_message(event.reply_token, reply)


@handler.add(MessageEvent, message=StickerMessage)
def sticker_text(event):
    if "mock" in LINE_ACCESS_TOKEN.lower():
        logger.info(f"Mock sticker reply sent. ReplyToken: {event.reply_token}")
    else:
        line_bot_api.reply_message(
            event.reply_token,
            StickerSendMessage(package_id='6136', sticker_id='10551379')
        )


@handler.add(FollowEvent)
def follow_event(event):
    """ข้อความต้อนรับแรก (สากล): เมื่อลูกค้าแอดเพื่อน -> ส่งทักทาย + ปุ่มให้แตะทันที
    (LINE OA console ตั้ง welcome ธรรมดาได้แค่ข้อความ ไม่มีปุ่ม — ส่งจากบอทเองมีปุ่มได้)"""
    line_user_id = event.source.user_id
    db = SessionLocal()
    try:
        user = get_or_create_line_user(db, line_user_id)
        welcome = TextSendMessage(text=greeting_text(user.name),
                                  quick_reply=quick_reply_items())
        privacy = TextSendMessage(text=PRIVACY_NOTICE)
        if "mock" in LINE_ACCESS_TOKEN.lower():
            logger.info(f"Mock follow welcome -> {user.name}")
        else:
            line_bot_api.push_message(line_user_id, [welcome, privacy, PRIVACY_BUTTON])
    except Exception as e:
        logger.error(f"Follow welcome error: {e}")
    finally:
        db.close()
