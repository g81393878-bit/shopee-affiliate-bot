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
                            MessageAction, FollowEvent, FlexSendMessage, ImageSendMessage)
from pydantic import BaseModel

from app.db import SessionLocal, get_db
from app import models
from app.services.product_cards import product_cards_message, link_button_message
from app.services.line_quota import push_guard
from app.services.category import guess_category, CATEGORY_KEYWORDS, normalize_query
from app.services.web_search import web_search_answer
from app.services.hermes_brain import load_skills_safe, market_emphasis
from app.config import settings

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
    
    # Production: ต้องมีลายเซ็น LINE จริง (ปิดช่องรับ request ไม่มีลายเซ็น)
    # Dev/test: secret ยังเป็น mock → เปิด bypass ไว้ให้ลองเครื่อง
    if LINE_SECRET == "mock_line_channel_secret":
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
            
    if not x_line_signature:
        logger.warning("Webhook request rejected: missing x-line-signature")
        raise HTTPException(status_code=400, detail="chatbot handle body error: missing signature")
    try:
        handler.handle(body_str, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="chatbot handle body error.")
    return 'OK'


# ตัวเลขไทยคำ → ค่าตัวเลข ("ร้อย"=100, "สองพัน"=2000, "ยี่สิบ"=20) — คนไทย
# พิมพ์ "ไม่เกินร้อย"/"งบสองพัน" แทนตัวเลขอารบิกบ่อย (เจอจริงจากลูกค้า: "ถุงเท้าไม่เกินร้อย")
_THAI_DIGIT_WORDS = {"หนึ่ง": 1, "ยี่": 2, "สอง": 2, "สาม": 3, "สี่": 4,
                     "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9}
_THAI_UNIT_WORDS = {"สิบ": 10, "ร้อย": 100, "พัน": 1000, "หมื่น": 10000,
                    "แสน": 100000, "ล้าน": 1000000}


def _thai_word_number(text: str) -> Optional[float]:
    """แปลงตัวเลขไทยคำ → ค่า ('ร้อย'→100, 'สองพัน'→2000, 'ยี่สิบ'→20) — ไม่ใช่เลขไทยคำ → None"""
    m = re.fullmatch(r"(หนึ่ง|ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(สิบ|ร้อย|พัน|หมื่น|แสน|ล้าน)",
                     (text or "").strip())
    if not m:
        return None
    digit = _THAI_DIGIT_WORDS.get(m.group(1) or "", 1)
    return float(digit * _THAI_UNIT_WORDS[m.group(2)])


def parse_price_conditions(text: str) -> Tuple[Optional[float], Optional[float]]:
    """เข้าใจเงื่อนไขราคาแบบไทย: 'ไม่เกิน 300', '300 บาท', 'งบ 500', '300-500', 'ไม่แพงกว่า 150',
    'ไม่เกินร้อย' (100), 'งบสองพัน' (2000), 'สองร้อยบาท'"""
    t = text.replace(",", "").replace(" ", "").lower()
    # ช่วงราคา เช่น 300-500 / 300ถึง500 / 300–500
    m = re.search(r"(\d{2,})\s*(?:-|–|ถึง)\s*(\d{2,})", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    # "ไม่เกิน 300" / "งบ 300" / "ราคา 300" / "ประมาณ 300" / "ถูกกว่า 150"
    m = re.search(r"(?:ไม่เกิน|ไม่แพงกว่า|ไม่แพง|ต่ำกว่า|ถูกกว่า|งบ|ในงบ|ราคา|ประมาณ|ภายใน|ซื้อได้ใน)\s*(\d+(?:\.\d+)?)", t)
    if m:
        return None, float(m.group(1))
    # ตัวเลขไทยคำตามหลังคำบอกงบ — "ไม่เกินร้อย" / "งบสองพัน"
    m = re.search(r"(?:ไม่เกิน|ไม่แพงกว่า|ไม่แพง|ต่ำกว่า|ถูกกว่า|งบ|ในงบ|ราคา|ประมาณ|ภายใน|ซื้อได้ใน)\s*((?:หนึ่ง|ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(?:สิบ|ร้อย|พัน|หมื่น|แสน|ล้าน))", t)
    if m:
        val = _thai_word_number(m.group(1))
        if val is not None:
            return None, val
    # "300 บาท"
    m = re.search(r"(\d+(?:\.\d+)?)\s*บาท", t)
    if m:
        return None, float(m.group(1))
    # "สองร้อยบาท" / "ร้อยบาท"
    m = re.search(r"((?:หนึ่ง|ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(?:สิบ|ร้อย|พัน|หมื่น|แสน|ล้าน))\s*บาท", t)
    if m:
        val = _thai_word_number(m.group(1))
        if val is not None:
            return None, val
    return None, None


def format_product_message(db: Session, user: models.User, products: list,
                           title: Optional[str] = None, is_owner: bool = False):
    """สร้างการ์ดสินค้า Flex — ลูกค้าเห็นเฉพาะข้อมูลซื้อ, เจ้าของเห็นข้อมูลแอดมินเพิ่ม"""
    return product_cards_message(db, user, products, title, is_owner=is_owner)


def _hermes_skills(db: Session) -> dict:
    """ทักษะ hot-reload จาก Hermes AI (system_preferences) — fail-open เป็น default
    ถ้าตารางยังไม่มี (ก่อน migration) ต้องไม่ crash เส้นทางแชทหลัก"""
    return load_skills_safe(db)


def _append_market_emphasis(text: str, emphasis: str) -> str:
    """ต่อท้ายวลี market tone (Hermes) เข้าข้อความ — ไม่ซ้ำถ้ามีอยู่แล้ว"""
    if emphasis and emphasis not in (text or ""):
        return f"{text}\n\n{emphasis}"
    return text


def _trending_boost(products: list, trending) -> list:
    """เรียงสินค้าให้หมวดมาแรง (Hermes) ขึ้นก่อน — หมวดอื่นคงลำดับเดิม (ai_score desc).

    ใช้เมื่อลูกค้าไม่ได้ระบุหมวดเจาะจง (เช่น "วันนี้ขายอะไรดี"/"มีอะไรใหม่") เพื่อให้
    ป้าเข็มเชียร์หมวดที่ตลาดกำลังตามหาอยู่ก่อน (stable sort กันลำดับเดิมพัง).
    """
    trend = [c for c in (trending or []) if c]
    if not trend or not products:
        return products

    def rank(p):
        try:
            return trend.index(p.category or "")
        except ValueError:
            return len(trend)

    return sorted(products, key=rank)


def handle_today_deals(db: Session, user: models.User, is_owner: bool = False) -> str:
    """วันนี้ขายอะไรดี — หมุนเวียนสินค้าจากกลุ่มคะแนนสูงสุด (เลื่อนวันละ 1 ตัว)
    เพื่อให้สินค้าใหม่ ๆ ได้โผล่หน้าแนะนำด้วย ไม่ใช่ซ้ำชุดเดิมทุกวัน
    หมวดมาแรง (Hermes) ได้ดันขึ้นก่อน นโยบายเด็ดขาด: ตอบเฉพาะสินค้าลิงก์ OK + ยอดขายถึงเกณฑ์"""
    pool = (db.query(models.Product)
              .filter(models.Product.link_status == "ok",
                      models.Product.sales_count >= MIN_SALES)
              .order_by(models.Product.ai_score.desc()).limit(9).all())
    pool = _trending_boost(pool, _hermes_skills(db).get("trending_categories"))
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
    "มีอะไรแนะนำ", "มีอะไรแนะนำไหม", "มีอะไรน่าสนใจ",
    "ขายดีวันนี้", "ของขายดีวันนี้", "ของดีวันนี้",
)


def is_deal_query(text: str) -> bool:
    """แยก 'ขอสินค้าแนะนำ' ออกจาก 'คำค้นสินค้า' — 'หูฟังขายดี' ต้องไปค้น ไม่ใช่เมนูแนะนำ"""
    t = text.rstrip("?？ ").strip()
    return t in DEAL_PHRASES or "วันนี้ขายอะไรดี" in t


GREETING_WORDS = ("hello", "hi", "hey", "หวัดดี", "ทักทาย", "ดีจ้า", "สวัสดี",
                  "สวัสดีครับ", "สวัสดีค่ะ", "ฮัลโหล", "ไหว้")


POLITE_SUFFIXES = ("ครับผม", "ครับ", "ค่ะ", "คะ", "จ๊ะ", "จ้า", "นะคะ", "นะ")


def _strip_polite_suffix(text: str) -> str:
    """ตัดคำลงท้ายสุภาพ (ค่ะ/ครับ/คะ/จ๊ะ/นะ...) ที่ลูกค้าพิมพ์ต่อท้าย — กัน phrase หลุดจาก intent"""
    t = (text or "").strip()
    for s in POLITE_SUFFIXES:
        if t.endswith(s):
            t = t[:-len(s)].strip()
            break
    return t


def is_greeting(text: str) -> bool:
    """แยกคำทักทายล้วนๆ ออกจากคำค้น — 'สวัสดี อยากได้หูฟัง' ต้องไปค้น ไม่ใช่ทักทาย"""
    t = text.rstrip("?？!. ").strip().lower()
    if t in GREETING_WORDS:
        return True
    # "สวัสดีค่ะ ป้าเข็ม" / "สวัสดีนะคะ" → ยังเป็นทักทาย (ตัดชื่อบอท + คำสุภาพแล้วเทียบ)
    t2 = _strip_polite_suffix(t).replace("ป้าเข็ม", "").replace("แม่เข็ม", "").replace(" ", "")
    if t2 in GREETING_WORDS:
        return True
    return t.startswith("สวัสดี") and len(t) <= 12


# --- ปรับโทนภาษาให้เหมาะทุกวัย (วัยรุ่น/ผู้สูงอายุ) จากสไตล์การพิมพ์ ---
YOUTH_SIGNALS = ("555", "มั้ย", "คับ", "lol", "ป้ายยา", "ไฟลุก", "จัดให้", "แฮร่",
                 "จัดไป", "เว่อร์", "เริ่ด", "อิอิ")
ELDER_SIGNALS = ("หลาน", "ขอรบกวน", "ไม่ถนัด", "ไม่เก่ง", "ขอบพระคุณ",
                 "กราบ", "กลัวโดนหลอก", "โดนหลอก", "ครับผม", "ไม่ทราบ",
                 "ขอความกรุณา", "ลุง", "ผู้สูงอายุ", "สูงวัย", "แก่แล้ว", "ไม่ทันสมัย")

def detect_tone(text: str) -> str:
    """เดาโทนจากสไตล์ข้อความ: youth / elder / neutral (ไม่เดาเกินเหตุ)"""
    t = (text or "").lower()
    y = sum(1 for s in YOUTH_SIGNALS if s in t)
    e = sum(1 for s in ELDER_SIGNALS if s in t)
    if e > y:
        return "elder"
    if y > e:
        return "youth"
    return "neutral"


def get_tone(db: Session, line_user_id: str, text: str) -> str:
    """โทนต่อผู้ใช้ (เก็บถาวรใน user_preferences) — เดาแล้วจำไว้ใช้ข้อความถัดไป ไม่ต้องพิมพ์ซ้ำ"""
    detected = detect_tone(text)
    pref = (db.query(models.UserPreference)
              .filter(models.UserPreference.line_user_id == line_user_id).first())
    saved = pref.tone if pref and pref.tone in ("youth", "elder") else None
    if detected in ("youth", "elder") and detected != saved:
        if pref is None:
            pref = models.UserPreference(line_user_id=line_user_id,
                                         categories=[], notes=[], tone=detected)
            db.add(pref)
        else:
            pref.tone = detected
        db.commit()
        return detected
    return saved or "neutral"


SEARCH_GUIDE_YOUTH = (
    """🔍 ว่าเลย หาอะไร? พิมพ์แบบนี้:

• "หูฟัง" — ตามชื่อ
• "หูฟังไม่เกิน 300" — ตามงบ
• "กระติก 200-400" — ช่วงราคา

ส่งมา เดี๋ยวหาให้ไวๆ จ้า 😎"""
)
SEARCH_GUIDE_ELDER = (
    """🔍 ค้นของค่ะ ไม่ยากเลย

พิมพ์ชื่อของที่อยากได้ เช่น "หูฟัง"
ถ้าอยากได้ไม่แพง พิมพ์ว่า "หูฟังไม่เกิน 300"

ป้าเข็มจะหาให้ค่ะ"""
)


def search_guide(tone: str = "neutral") -> str:
    """คู่มือค้นสินค้า ปรับโทนตามวัย (neutral = ข้อความเดิม)"""
    if tone == "youth":
        return SEARCH_GUIDE_YOUTH
    if tone == "elder":
        return SEARCH_GUIDE_ELDER
    return SEARCH_GUIDE


def greeting_text_for(user_name: str, tone: str = "neutral") -> str:
    """ทักทาย + ทางเลือก ปรับโทนตามวัย (neutral = ข้อความเดิม)"""
    if tone == "youth":
        return (
            f"""โย่ว {user_name} 👋 อยากได้อะไร?

พิมพ์ชื่อของมาดิ เช่น "หูฟัง" "กระติกน้ำ"
หรือใส่เงื่อนไข "หูฟังไม่เกิน 300"

ป้าเข็มจัดให้ไวๆ จ้า 😎"""
        )
    if tone == "elder":
        return (
            f"""🤗 สวัสดีค่ะคุณ {user_name} ยินดีต้อนรับนะคะ

อยากได้อะไร บอกป้าเข็มเป็นคำสั้นๆ ได้เลยค่ะ
เช่น "หูฟัง" หรือ "กระติกน้ำ"

หรือกดปุ่มข้างล่างก็ได้นะคะ ไม่ต้องรีบค่ะ"""
        )
    return greeting_text(user_name)


def nosearch_fallback_text(user_text: str, tone: str = "neutral") -> str:
    """ยังไม่มีในร้าน — ปรับโทนตามวัย"""
    if tone == "youth":
        return (f"""🔍 ยังไม่มี "{user_text}" ในร้านตอนนี้จ้า

ลองพิมพ์สั้นๆ เช่น "หูฟัง" "กระติกน้ำ"
หรือแตะปุ่มข้างล่างเลย 👇""")
    if tone == "elder":
        return (f"""🔍 ตอนนี้ยังไม่มี "{user_text}" ในร้านนะคะ

ไม่ต้องกังวลค่ะ
ลองพิมพ์ชื่อของสั้นๆ เช่น "หูฟัง" หรือ "กระติกน้ำ"
หรือกดปุ่มข้างล่างก็ได้ค่ะ""")
    return (f"""🔍 ยังไม่มี "{user_text}" ในร้านป้าเข็มตอนนี้จ๊ะ

ลองพิมพ์ชื่อสินค้าสั้นๆ เช่น "หูฟัง" "กระติกน้ำ" หรือแตะปุ่มด้านล่างได้เลยค่ะ 👇""")


def nosearch_alt_text(user_text: str, category: str, tone: str = "neutral") -> str:
    """ยังไม่มีของที่ค้น + มีของใกล้เคียงในหมวด — ปรับโทนตามวัย"""
    if tone == "youth":
        return (f"🔍 ยังไม่มี \"{user_text}\" ในร้านตอนนี้จ้า\n\n"
                f"ลองดูของใกล้เคียงหมวด {category} ด้านล่างเลย หรือพิมพ์ชื่ออื่นก็ได้ 😎")
    if tone == "elder":
        return (f"🔍 ตอนนี้ยังไม่มี \"{user_text}\" ในร้านนะคะ\n\n"
                f"ไม่เป็นไรค่ะ ลองดูของใกล้เคียงหมวด {category} ด้านล่างก่อนได้\n"
                f"หรืออยากได้อะไร พิมพ์บอกป้าเข็มได้เลยค่ะ")
    return (f"🔍 ยังไม่มี \"{user_text}\" ในร้านป้าเข็มตอนนี้จ๊ะ\n\n"
            f"ลองดูของใกล้เคียงในหมวด {category} ด้านล่าง หรือพิมพ์ชื่ออื่นได้เลยค่ะ 😊")


def nosearch_new_text(user_text: str, category: str, tone: str = "neutral") -> str:
    """ค้นไม่เจอของขายดี แต่หมวดมีของใหม่เพิ่งเข้าคลัง (ยังไม่ถึงเกณฑ์ขาย) — ปรับโทนตามวัย"""
    if tone == "youth":
        return (f"🔍 ยังไม่มี \"{user_text}\" ที่ขายดีถึงเกณฑ์ตอนนี้จ้า\n\n"
                f"แต่มีของใหม่หมวด {category} เพิ่งเข้าคลัง ลองดูด้านล่างก่อนได้เลย 😎")
    if tone == "elder":
        return (f"🔍 ตอนนี้ยังไม่มี \"{user_text}\" ที่ขายดีถึงเกณฑ์นะคะ\n\n"
                f"แต่มีของใหม่หมวด {category} เพิ่งเข้ามา ลองดูด้านล่างก่อนได้ค่ะ\n"
                f"หรืออยากได้อะไรเพิ่ม พิมพ์บอกป้าเข็มได้เลยค่ะ")
    return (f"🔍 ยังไม่มี \"{user_text}\" ที่ขายดีถึงเกณฑ์ในตอนนี้จ๊ะ\n\n"
            f"แต่มีของใหม่หมวด {category} เพิ่งเข้าคลัง ลองดูด้านล่างก่อนได้เลยค่ะ 😊")


def quick_reply_items() -> QuickReply:
    """ปุ่มลัดแบบสากล (Quick Reply) — ลูกค้าแตะแทนพิมพ์
    3 ปุ่มพอ: 🔍 ค้นหาสินค้า · 🤖 คุยกับป้าเข็ม · 💬 ฝากคำถาม (ส่วนที่เหลือลูกค้า
    พิมพ์เองได้ หรือกดจาก Rich Menu แถบติดหน้าจอ) — ปุ่มทุกตัวส่งข้อความที่
    dispatch route ตรง intent ไม่หลุด "ค้นไม่เจอ"""
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="🔍 ค้นหาสินค้า", text="ค้นสินค้า")),
        QuickReplyButton(action=MessageAction(label="🤖 คุยกับป้าเข็ม", text="คุยกับป้าเข็ม")),
        QuickReplyButton(action=MessageAction(label="💬 ฝากคำถาม", text="ฝากคำถาม")),
    ])


def welcome_text(user_name: str, tone: str = "neutral") -> str:
    """ข้อความต้อนรับแรก (สั้น + คุณค่าชัด) — ปรับสำเนียงตามวัยที่จำไว้ (neutral = ข้อความเดิม)"""
    if tone == "youth":
        return (
            f"🤗 โย่วคุณ {user_name}! ยินดีต้อนรับเข้าร้าน{BOT_NAME} 💕\n\n"
            "ของดีราคาเท่า Shopee เป๊ะ แต่ป้าเข็มคัดให้ + จำได้ว่าคุณชอบอะไร 😎\n\n"
            "แตะปุ่มข้างล่างได้เลย 👇"
        )
    if tone == "elder":
        return (
            f"🤗 สวัสดีค่ะคุณ {user_name} ยินดีต้อนรับเข้าร้าน{BOT_NAME} 💕\n\n"
            "ที่นี่ราคาเท่ากับ Shopee เป๊ะ แต่ป้าเข็มคัดของดีให้\n"
            "และจำได้ว่าคุณชอบอะไรนะคะ 😊\n\n"
            "แตะปุ่มด้านล่างได้เลยค่ะ 👇"
        )
    return (
        f"🤗 สวัสดีค่ะคุณ {user_name}! ยินดีต้อนรับสู่ร้าน{BOT_NAME} 💕\n\n"
        "ที่นี่ราคาเท่ากับ Shopee เป๊ะ แต่ป้าเข็มคัดของดีให้"
        " + จำได้ว่าคุณชอบอะไร 😊\n\n"
        "แตะปุ่มด้านล่างได้เลยจ๊ะ 👇"
    )


def greeting_text(user_name: str) -> str:
    """แนวสากล: ทักทาย + ทางเลือก — ไม่ยิงสินค้าใส่หน้าจนกว่าลูกค้าจะบอกความต้องการ"""
    return (
        f"🤗 สวัสดีค่ะคุณ {user_name}! ยินดีต้อนรับสู่ร้าน{BOT_NAME} 💕\n\n"
        "พิมพ์ชื่อสินค้าที่อยากได้ได้เลย เช่น\n"
        "\"หูฟังไม่เกิน 300\" หรือ \"กระติกน้ำ\"\n\n"
        "หรือแตะปุ่มด้านล่าง 👇"
    )


def _ensure_menu(reply):
    """ควิกรีไพลเมนูหลักติดข้อความสุดท้ายของทุกคำตอบเสมอ.

    LINE ลบ quick reply ทันทีที่บอท/ใครก็ตามส่งข้อความใหม่ในห้อง — ถ้าแนบกับ
    ข้อความแรกของชุดตอบ (บั๊กเดิมใน browse_category_message) ปุ่มจะหายก่อน
    ลูกค้าเห็น ข้อความสุดท้ายที่มี quick_reply เฉพาะอยู่แล้ว (เช่น เมนูหมวด)
    เก็บไว้ไม่ทับ"""
    msgs = reply if isinstance(reply, list) else [reply]
    last = msgs[-1]
    if getattr(last, "quick_reply", None) is None:
        try:
            last.quick_reply = quick_reply_items()
        except Exception:
            pass
    return msgs


def _web_answer_messages(query, answer=None):
    """คำตอบค้นเน็ต + รูปประกอบ (ถ้ามี) — ส่งรูปก่อน แล้วข้อความท้าย (เมนูแนบที่ข้อความ).

    answer: ผลจาก web_search_answer(query) ถ้าเรียกแล้ว จะ reuse ไม่ค้นซ้ำ"""
    if answer is None:
        answer = web_search_answer(query)
    msgs = []
    for u in (answer.get("images") or [])[:1]:
        try:
            msgs.append(ImageSendMessage(original_content_url=u, preview_image_url=u))
        except Exception:
            pass
    msgs.append(TextSendMessage(text=answer.get("text") or ""))
    return msgs


def welcome_quick_reply() -> QuickReply:
    """ปุ่มตอนแอดครั้งแรก — ใช้ชุดเดียวกับเมนูหลัก (3 ปุ่ม สากล ไม่ซ้ำ Rich Menu)"""
    return quick_reply_items()


SEARCH_GUIDE = (
    "🔍 ค้นสินค้าค่ะ! ลองพิมพ์แบบนี้:\n\n"
    "• \"หูฟัง\" — ค้นตามชื่อ\n"
    "• \"หูฟังไม่เกิน 300\" — ค้นตามงบ\n"
    "• \"กระติก 200-400\" — ค้นช่วงราคา\n\n"
    "พิมพ์มาได้เลย เดี๋ยวป้าเข็มหาให้ค่ะ 😊"
)

# --- ทำไมต้องซื้อกับป้าเข็ม (คุณค่าที่ประชาชนได้ — ข้อมูลจริง ไม่โฆษณาเกินจริง) ---
WHY_US_PHRASES = ("ทำไมต้องซื้อกับป้าเข็ม", "ทำไมต้องป้าเข็ม", "ทำไมต้องซื้อ", "เหตุผล", "ข้อดีของร้าน", "ป้าเข็มดียังไง")

# --- คู่มือ/FAQ — ตอบเรื่องบอทจากคู่มือเท่านั้น (ไม่ใช้ AI เดา — กันมโน) ---
BOT_MANUAL_PHRASES = (
    "คู่มือ", "บอททำอะไร", "บอทช่วย", "ทำอะไรได้บ้าง", "ช่วยอะไรได้",
    "วิธีใช้", "ใช้ยังไง", "ใช้ยังงัย", "ใช้งานยังไง", "สั่งยังไง",
    "ฟีเจอร์", "ฟิวเจอร์", "ฟีเจอ", "มีอะไรบ้าง", "ค้นยังไง", "เทียบยังไง", "ขายดีคืออะไร",
    "จำไว้คืออะไร", "พัสดุยังไง", "ติดตามยังไง", "สั่งซื้อยังไง",
    "ซื้อยังไง", "ซื้ออย่างไร", "ซื้อสินค้าอย่างไร", "ซื้อสินค้ายังไง", "ซื้อของอย่างไร", "ซื้อของยังไง", "วิธีซื้อ", "วิธีสั่ง", "วิธีสั่งซื้อ", "ราคายังไง", "โปรยังไง", "ลดยังไง",
    # ระบบ/ความเป็นส่วนตัว/ราคา — ประชาชนถามเรื่องความปลอดภัยของข้อมูล
    "ระบบ", "ปลอดภัย", "supabase", "ความเป็นส่วนตัว", "ข้อมูลส่วนตัว",
    "ข้อมูลของฉัน", "เก็บข้อมูล", "ทำงานยังไง", "ทำงานอย่างไร",
    "ราคาเปลี่ยน", "ราคาไม่ตรง", "อัปเดต",
    # การติดตั้ง/สิ่งที่ต้องมี — ลูกค้าไม่ต้องติดตั้งอะไร, เจ้าของร้านดูส่วนประกอบระบบ
    "ติดตั้ง", "ต้องมีอะไร", "ต้องเตรียม", "เตรียมอะไร", "ลงแอป",
    "ลงอะไร", "ตั้งค่าระบบ", "เริ่มใช้", "เริ่มต้นใช้",
    # ถามหาโค้ด/ดาวน์โหลด — เจ้าของ/นักพัฒนาอยากได้โค้ดบอท
    "โค้ดจากไหน", "โค้ดอยู่ไหน", "โค้ดหน่อย", "โค้ดของบอท", "โค้ดของป้าเข็ม",
    "ดาวน์โหลด", "github", "ซอร์สโค้ด", "ซอร์ส", "source",
    # คำถามสามัญแบบคนไม่รู้เรื่องถาม (ของแท้/คุณภาพ/จัดส่ง/ร้าน/ขอบคุณ/ราคา)
    "ขายอะไรบ้าง", "ของแท้", "ของปลอม", "คุณภาพ", "สินค้าดี", "ของดี",
    "ดีจริง", "คุณภาพดี", "ใครเป็นคนขาย", "ใครขาย", "เจ้าของร้าน", "ร้านอยู่ที่ไหน",
    "อยู่ที่ไหน", "มีหน้าร้าน", "ส่งของกี่วัน", "กี่วันถึง", "จัดส่งกี่วัน",
    "ราคาเท่าไหร่", "ราคาเท่าไร", "ขอบคุณ", "ขอบใจ",

    # FAQ ยอดนิยม (สากล: คืนเงิน/ค่าส่ง/ชำระเงิน/โปร/บอทไม่ตอบ)
    "คืนเงิน", "คืนสินค้า", "คืนของ", "เปลี่ยนสินค้า", "เปลี่ยนของ", "ชำรุด", "สินค้าเสีย", "refund",
    "ค่าส่ง", "ค่าจัดส่ง", "ส่งฟรี", "ขนส่ง",
    "ชำระเงิน", "จ่ายเงิน", "จ่ายยังไง", "โอนเงิน", "โอนจ่าย",
    "คูปอง", "โปรโมชั่น", "ส่วนลด", "ลดราคา", "มีโปร",
    "บอทไม่ตอบ", "บอทเงียบ",
    # มาตรฐานการบริการ 5 ขั้นตอน (Customer Experience) — "บริการ" ไม่ชนชื่อสินค้าในคลัง (0 ตัว)
    "บริการ", "ประสบการณ์ลูกค้า", "ห้าขั้นตอน", "5ขั้นตอน",
    # ค่าคอม/ประกัน/ปลายทาง/ถอนเงิน — คำถามเงิน + หลังซื้อ (เติมเพิ่ม)
    "ค่าคอม", "ค่าคอมมิชชั่น", "คอมมิชชั่น", "commission", "ได้ค่าคอม",
    "ปลายทาง", "cod", "เก็บปลายทาง",
    "รับประกัน", "มีประกัน", "ประกันสินค้า", "ประกันกี่วัน", "warranty",
    "ได้เงินจริง", "ถอนเงิน", "ถอนค่าคอม", "เบิกเงิน",
    # เทคนิค/ระบบ — เซิร์ฟเวอร์/คีย์/ที่เก็บข้อมูล/ไลน์ OA/โค้ด
    # (เจ้าของร้าน + คนอยากทำตาม — กันหลุดไปค้นสินค้า)
    "เซิร์ฟเวอร์", "server", "ล่ม", "เปิดคอม",
    "คีย์", "api", "groq", "gemini", "โควต้า", "โควตา",
    "ไลน์oa", "lineoa", "webhook", "richmenu", "ริชเมนู",
    "บัญชีไลน์", "ไลน์ส่วนตัว",
    "ฐานข้อมูล", "database", "ที่เก็บข้อมูล", "คลาวด์", "cloud", "สำรองข้อมูล",
    "สมัคร", "ค่าใช้จ่าย", "เสียเงิน",
    "โค้ด", "ลิขสิทธิ์", "license", "ขายต่อ", "ไวรัส",
    "เวอร์ชัน", "version", "โปรแกรมเมอร์", "คอมพิวเตอร์", "ขั้นตอน", "ตั้งค่า",
    "ขายส่ง", "รับตัวแทน", "เป็นตัวแทน", "สั่งซื้อ",
)
CONTACT_PHRASES = (
    "คุยกับป้าเข็ม", "คุยกับแม่เข็ม",
    "คุยคนจริง", "คุยกับคนจริง", "คุยกับคน", "คุยเจ้าของ",
    "ติดต่อเจ้าของร้าน", "ติดต่อร้าน", "ติดต่อแม่เข็ม", "ติดต่อป้าเข็ม",
    "แอดไลน์", "ขอไลน์", "ไลน์แม่เข็ม", "ไลน์ป้าเข็ม", "ขอไลน์แม่เข็ม", "ขอไลน์ป้าเข็ม",
    "เบอร์โทรแม่เข็ม", "เบอร์โทรป้าเข็ม", "เบอร์โทร",
    "ฝากคำถาม", "ฝากข้อความ", "อยากถาม", "มีคำถามจะถาม", "ติดต่อแม่ค้า", "ติดต่อแม่เข็ม",
    "แม่เข็มอยู่ไหม", "แม่เข็มอยู่มั้ย", "ป้าเข็มอยู่ไหม", "ป้าเข็มอยู่มั้ย",
    "แม่เข็มอยู่หรือเปล่า", "แม่เข็มอยู่เปล่า", "ป้าเข็มอยู่หรือเปล่า", "ป้าเข็มอยู่เปล่า",
)
BOT_MANUAL = (
    "🤗 ป้าเข็มคือผู้ช่วยช้อปของดีจาก Shopee ให้คุณจ๊ะ — ราคาเท่ากับในแอปเป๊ะ ไม่บวกเพิ่ม\n\n"
    "พิมพ์ชื่อสินค้าที่อยากได้ เช่น \"หูฟัง\" \"กระติกน้ำ\"\n"
    "ป้าเข็มหาให้จากของจริงในร้านได้เลยค่ะ\n\n"
    "อยากได้อะไรเป็นพิเศษ (เทียบของ / จำความชอบ / เช็คพัสดุ / โปรฯ)\n"
    "ถามป้าเข็มได้เลย หรือแตะปุ่มด้านล่างจ๊ะ 👇\n\n"
    "🛠️ อยากเอาไปเปิดร้านเอง — ถาม \"ติดตั้งยังไง\" ป้าเข็มบอกทีละขั้นให้จ๊ะ"
)
BOT_MANUAL_SECTIONS = [
    (("ค้น", "หา"), "🔍 ค้นสินค้าค่ะ — พิมพ์ชื่อ เช่น \"หูฟัง\" \"กระติกน้ำ\" หรือใส่เงื่อนไข \"หูฟังไม่เกิน 300\" \"กระติก 200-400\" ป้าเข็มหาให้จากข้อมูลจริงในร้านจ๊ะ"),
    (("เทียบ", "เปรียบเทียบ"), "⚖️ เทียบสินค้าค่ะ — พิมพ์ \"เทียบ A กับ B\" เช่น \"เทียบกระติก ESKIMO กับ YTL\" ป้าเข็มเทียบ ราคา/ยอดขาย/ขนาด ให้ดูจ๊ะ"),
    (("ขายดี", "อันดับ"), "⭐ \"วันนี้ขายอะไรดี\" = ป้าเข็มแนะนำของดี / 🔥 \"อันดับขายดี\" = เรียงยอดขายสูงสุด — แตะปุ่มด้านล่างได้เลยจ๊ะ"),
    (("จำ",), "🧠 จำไว้จ๊ะ — พิมพ์ \"จำไว้ ชอบหูฟัง\" ป้าเข็มจะจำความชอบคุณ และแจ้งของใหม่/ราคาลงในหมวดที่ชอบจ๊ะ"),
    # --- เทคนิค/ระบบ: เซิร์ฟเวอร์/คีย์ AI/ไลน์ OA/ฐานข้อมูล/โค้ด/เวอร์ชัน ---
    (("โค้ดส่วนลด", "โค้ดลด", "โค้ดโปร"),
     "🏷️ โค้ดส่วนลด/โปรโมชั่น ตามร้านค้าบน Shopee จ๊ะ — ราคาในร้านป้าเข็ม = ราคาจริงจาก Shopee "
     "(อัปเดตอัตโนมัติ) ดูโปร/คูปองในแอป Shopee ได้เลยจ๊ะ"),
    (("เซิร์ฟเวอร์", "server", "ล่ม", "เปิดคอม"),
     "🖥️ บอทป้าเข็มรันบนเซิร์ฟเวอร์คลาวด์ (Render) ฟรี — เปิดอยู่ตลอด 24 ชม. ไม่ต้องเปิดคอม/ซื้อเครื่องคุณเอง "
     "ถ้าเซิร์ฟเวอร์หลับหลังว่างนาน บอทจะตื่นเองทุก 10 นาที แล้วตอบได้ทันทีจ๊ะ"),
    (("คีย์", "api", "groq", "gemini", "โควต้า", "โควตา", "ai"),
     "🔑 คีย์ AI (Groq/Gemini) = กุญแจให้บอทสร้างคอนเทนต์ — สมัครฟรีบนเว็บผู้ให้บริการ "
     "(แผนฟรีพอใช้แน่นอน) ถ้าคีย์หมด (โควต้าประจำวัน) รอข้ามคืน เติมกลับมาเอง ไม่เสียเงิน ไม่หมดอายุจ๊ะ"),
    (("สมัครไลน์oa", "สมัครlineoa", "สมัครไลน์", "สมัครบัญชีไลน์", "เปิดไลน์oa", "lineoaสมัคร"),
     "💬 สมัคร LINE OA ฟรี: manager.line.biz → สร้างร้าน → จด Token+Secret จาก LINE Developers → ใส่ .env "
     "(ขั้นละเอียดใน docs/setup-guide.md จ๊ะ)"),
    (("ไลน์oa", "lineoa", "webhook", "richmenu", "ริชเมนู", "บัญชีไลน์", "ไลน์ส่วนตัว"),
     "💬 LINE OA = บัญชีร้านค้าบน LINE (หน้าร้าน) — สมัครฟรี เปิดจากบัญชีไลน์ที่มีอยู่แล้วได้เลย "
     "ลูกค้าแอดไลน์หน้าร้าน = คุยกับบอทได้ทันที (webhook/rich menu = ตัวเชื่อมหลังบ้าน ทำตามคู่มือจ๊ะ)"),
    (("ฐานข้อมูล", "database", "ที่เก็บข้อมูล", "คลาวด์", "cloud", "สำรองข้อมูล"),
     "🗄️ ข้อมูลร้าน (สินค้า/ลูกค้า/ประวัติ) เก็บในฐานข้อมูลคลาวด์ (Supabase) — ฟรี ปลอดภัย สำรองอัตโนมัติ "
     "ไม่ต้องซื้อฮาร์ดดิสก์ ไม่หายถ้าเครื่องคุณพัง ลูกค้าลบข้อมูลตัวเองได้ทุกเมื่อ (PDPA) จ๊ะ"),
    (("เวอร์ชัน", "version"),
     "🔁 อัปเดตเวอร์ชันใหม่ = ดึงโค้ดล่าสุด (git pull) แล้ว deploy ขึ้น Render — ระบบ build + เปิดตัวให้เอง "
     "ใน ~3 นาที วิธีละเอียดใน docs/setup-guide.md จ๊ะ"),
    (("โปรแกรมเมอร์", "คอมพิวเตอร์", "แก้โค้ด", "เขียนโค้ด"),
     "🙂 ไม่ต้องเป็นโปรแกรมเมอร์ก็ใช้ได้จ๊ะ — ทำตามคู่มือทีละขั้น ~15 นาที (มีคำสั่งก๊อป-แปะ) "
     "ติดตรงไหน ถามป้าเข็มได้เลย"),
    (("ลิขสิทธิ์", "license", "ขายต่อ", "ไวรัส", "อันตราย"),
     "✅ โค้ดป้าเข็มเป็นโอเพนซอร์ส เปิดเผยฟรีบน GitHub (ไม่มีไวรัส ตรวจสอบได้) — ใช้ส่วนตัวได้เต็มที่ "
     "อยากต่อยอด/ขายบริการ ให้ถามเจ้าของก่อนจ๊ะ"),
    (("ค่าใช้จ่าย", "เสียเงิน"),
     "💰 ใช้บอทป้าเข็ม = ฟรีทั้งหมด (LINE OA / Supabase / Render / คีย์ AI — แผนฟรีพอใช้) "
     "ลูกค้าไม่ต้องจ่ายอะไรเลย จ่ายเพิ่มก็ต่อเมื่ออยากได้สเปกสูงกว่าเท่านั้นจ๊ะ"),
    (("ค่าคอม", "ค่าคอมมิชชั่น", "คอมมิชชั่น", "commission", "ได้ค่าคอม", "ค่าคอมเท่าไหร่"),
     "💸 ค่าคอม = เงินที่ Shopee/แบรนด์จ่ายให้ร้านเมื่อลูกค้าซื้อผ่านลิงก์เรา — ลูกค้าจ่ายราคาเท่าเดิม ไม่บวกเพิ่ม "
     "(ป้าเข็มได้ส่วนต่างโดยไม่เก็บเพิ่มจากลูกค้า)"),
    (("สมัครshopee", "สมัครaffiliate", "สมัครแอฟฟิลิเอต", "สมัครนายหน้า", "affiliateสมัคร"),
     "📦 สมัคร Shopee Affiliate ฟรี: affiliate.shopee.co.th → สมัคร/รออนุมัติ → ได้ Affiliate ID "
     "ใช้ทำลิงก์ค่าคอม + export สินค้า (ขั้นละเอียดใน docs/setup-guide.md จ๊ะ)"),
    (("ได้เงินจริงไหม", "ได้เงินยังไง", "ได้เงินจริง", "ถอนเงิน", "ถอนค่าคอม", "เบิกเงิน"),
     "💰 ได้เงินจริงจ๊ะ — ค่าคอมเข้าตามรอบที่ Shopee กำหนด ดูยอด/ถอนได้ใน affiliate.shopee.co.th "
     "(ยอดขึ้นเมื่อคำสั่งซื้อ 'สำเร็จ' เท่านั้น)"),
    (("รับประกัน", "ประกันสินค้า", "มีประกัน", "ประกันกี่วัน", "warranty"),
     "🛡️ การรับประกันตามร้านค้าบน Shopee จ๊ะ — ดูเงื่อนไขในหน้าสินค้า/ติดต่อร้านค้าโดยตรง "
     "(ป้าเข็มเป็นนายหน้า ช่วยชี้ทางติดต่อร้านค้าเองจ๊ะ)"),
    (("จ่ายปลายทาง", "เก็บปลายทาง", "cod", "ปลายทาง"),
     "💵 จ่ายปลายทาง (COD) ได้หรือไม่ — ตามที่ร้านค้าบน Shopee เปิดไว้จ๊ะ ดูตัวเลือกตอนกดสั่งซื้อ "
     "(บางร้านมี/ไม่มี ขึ้นกับร้านค้านั้นๆ)"),
    (("โค้ดจากไหน", "โค้ดอยู่ไหน", "โค้ดหน่อย", "โค้ดของบอท", "โค้ด", "ดาวน์โหลด", "github", "ซอร์ส", "source"),
     "💻 โค้ดของป้าเข็มอยู่บน GitHub จ๊ะ — repo: g81393878-bit/shopee-affiliate-bot "
     "(ก๊อป/ดาวน์โหลดได้ฟรี เขียนด้วย Python) วิธีติดตั้งทีละขั้นอยู่ใน docs/setup-guide.md"),
    (("ขอบคุณ", "ขอบใจ"),
     "😊 ด้วยความยินดีจ๊ะ! ถ้าอยากได้อะไรเพิ่ม พิมพ์ชื่อสินค้า หรือแตะเมนูด้านล่างได้เลยนะคะ"),
    (("ราคาเท่าไหร่", "ราคาเท่าไร"),
     "💰 ราคาโชว์ในการ์ดสินค้าจ๊ะ — พิมพ์ชื่อที่อยากได้ เช่น \"หูฟัง\" แล้วป้าเข็มหาให้ "
     "(ราคาจริงจาก Shopee ไม่บวกเพิ่ม)"),
    (("ส่งของกี่วัน", "กี่วันถึง", "จัดส่งกี่วัน", "ส่งช้า"),
     "📦 ระยะเวลาจัดส่งตามร้านค้าบน Shopee จ๊ะ (ดูในหน้าสินค้า/ตอนสั่งซื้อ) — ปกติ 2-5 วัน "
     "ป้าเข็มเป็นนายหน้า ไม่ได้เป็นคนส่งจ๊ะ"),
    (("ของแท้", "ของปลอม", "คุณภาพ", "สินค้าดี", "ของดี", "ดีจริง", "ดีไหม"),
     "✅ ของแท้ 100% จากร้านค้าบน Shopee จ๊ะ — ป้าเข็มตรวจลิงก์สินค้าทุกตัวก่อนโชว์ "
     "(ของปลอม/ลิงก์ตายไม่ขึ้น) ดูรีวิว + ยอดขายจริงได้ในการ์ดจ๊ะ"),
    (("ใครเป็นคนขาย", "ใครขาย", "เจ้าของร้าน"),
     "🏪 ป้าเข็ม ขายของ = ร้านออนไลน์ (LINE + Shopee) แม่ค้าคัดของขายดีจาก Shopee มาแนะนำ "
     "มีคำถามอะไร ถามป้าเข็มได้เลยจ๊ะ — ป้าเข็มตอบให้เองทุกเรื่อง"),
    (("ร้านอยู่ที่ไหน", "อยู่ที่ไหน", "มีหน้าร้าน"),
     "📍 ร้านป้าเข็มเป็นร้านออนไลน์จ๊ะ — ขายผ่าน LINE + Shopee ส่งถึงบ้าน ไม่มีหน้าร้าน "
     "(เลยได้ราคาดี ไม่บวกค่าที่) สั่งจากที่ไหนก็ได้จ๊ะ"),
    (("supabaseคือ", "supabaseคืออะไร", "supabaseทำไม", "supabaseทําไม", "supabaseมีไว้ทำไม"),
     "🗄️ Supabase = ฐานข้อมูลคลาวด์ (สมุดบัญชีออนไลน์) — จำสินค้า/ลูกค้า/ประวัติ สำรองอัตโนมัติ ไม่หายถ้าเครื่องพัง "
     "(สมัครฟรี supabase.com จ๊ะ)"),
    (("ปลอดภัย", "supabase", "ระบบ", "เก็บข้อมูล", "ความเป็นส่วนตัว", "ข้อมูลส่วนตัว", "ข้อมูลของฉัน", "ทำงานยังไง", "ทำงานอย่างไร", "ความลับ"),
     "🔒 ข้อมูลคุณปลอดภัยจ๊ะ — ระบบร้านป้าเข็มรันบนคลาวด์ (Supabase) มาตรฐานเดียวกับแอปใหญ่ "
     "เก็บเฉพาะชื่อ + ข้อความที่คุย (90 วัน) เพื่อแนะนำของตรงใจ ไม่เก็บเลขบัตร/รหัสผ่าน "
     "และคุณลบได้ทุกเมื่อด้วยคำสั่ง \"ลบข้อมูลฉัน\" (ตามกฎ PDPA) จ๊ะ"),
    (("ราคาเปลี่ยน", "ราคาไม่ตรง", "อัปเดต", "ของหมด", "ลิงก์ตาย", "ของปลอม"),
     "🔄 ป้าเข็มดูแลร้านอัตโนมัติ — ตรวจลิงก์สินค้าทุกตัวว่าตาย/ปลอม (ผ่านเท่านั้นถึงโชว์) "
     "อัปเดตราคาตามจริง และแจ้งราคาลงให้คุณในหมวดที่สนใจ ถ้าของราคาเปลี่ยนป้าเข็มปรับตามจริงจ๊ะ"),
    (("สั่งซื้อ", "สั่งยังไง", "ซื้อยังไง", "ซื้ออย่างไร", "ซื้อสินค้าอย่างไร", "ซื้อสินค้ายังไง", "ซื้อของอย่างไร", "ซื้อของยังไง", "วิธีซื้อ", "วิธีสั่ง", "วิธีสั่งซื้อ", "ชำระเงิน", "จ่ายเงิน", "จ่ายยังไง", "โอนเงิน", "โอนจ่าย"),
     "🛒 สั่งซื้อผ่าน Shopee โดยตรงจ๊ะ — แตะปุ่ม \"ซื้อเลย\" ในแชท → จ่ายที่ Shopee "
     "(ปลอดภัย ไม่ต้องให้ข้อมูลบัตรกับป้าเข็ม) ป้าเข็มเป็นนายหน้า ไม่รับเงินเอง"),
    (("คืนเงิน", "คืนสินค้า", "คืนของ", "refund", "เปลี่ยนสินค้า", "เปลี่ยนของ", "ชำรุด", "สินค้าเสีย"),
     "↩️ การคืนเงิน/คืนสินค้า ตามนโยบายร้านค้าบน Shopee จ๊ะ — แอป Shopee → \"การซื้อของฉัน\" "
     "→ ขอคืนเงิน/คืนสินค้า (ป้าเข็มเป็นนายหน้า ไม่รับของ/เงินเอง)"),
    (("ค่าส่ง", "ค่าจัดส่ง", "ส่งฟรี", "ขนส่ง"),
     "📦 ค่าส่งตามที่ร้านค้าบน Shopee ตั้งไว้ (ดูในหน้าสินค้า) — ป้าเข็มไม่คิดค่าบริการเพิ่ม ราคาเท่ากับในแอปเป๊ะ"),
    (("คูปอง", "โปรโมชั่น", "โปร", "ส่วนลด", "ลดราคา", "มีโปร", "ของลดราคา"),
     "🏷️ ราคาในร้าน = ราคาจริงจาก Shopee (อัปเดตอัตโนมัติ) — ป้าเข็มแจ้งราคาลง/ของใหม่ในหมวดที่คุณชอบ "
     "ถาม \"มีอะไรใหม่\" ได้เลยจ๊ะ"),
    (("บอทไม่ตอบ", "บอทเงียบ"),
     "😅 ถ้าบอทไม่ตอบ — ลองพิมพ์ใหม่ หรือแตะปุ่มเมนูด้านล่าง ถ้ายังไม่ได้ แตะ \"ฝากคำถาม\" ป้าเข็มตอบให้เองจ๊ะ"),
    (("ขายส่ง", "รับตัวแทน", "เป็นตัวแทน"),
     "🤝 ป้าเข็มเป็นนายหน้าให้ Shopee — สั่งกี่ชิ้นก็ได้ตามร้านค้า ไม่มีค่าธรรมเนียมเพิ่ม "
     "ถ้าอยากได้ราคาส่ง ลองถามร้านค้าบน Shopee โดยตรงจ๊ะ"),
    (("พัสดุ", "สั่งแล้ว", "ของถึง"), "📦 ทวงถามพัสดุ — ป้าเข็มเป็นนายหน้า พัสดุตรวจได้ในแอป Shopee (เมนู \"การซื้อของฉัน\") พิมพ์ \"สั่งแล้ว\" ป้าเข็มบอกวิธีให้จ๊ะ"),
    (("ลบ", "ข้อมูล", "ส่วนตัว"), "🗑️ พิมพ์ \"ลบข้อมูลฉัน\" → ป้าเข็มลบประวัติ + ความจำทั้งหมดให้ทันที (สิทธิ์ตาม PDPA) จ๊ะ"),
    (("มาตรฐานการบริการ", "มาตรฐานบริการ", "บริการลูกค้า", "ประสบการณ์ลูกค้า",
      "ขั้นตอนการบริการ", "การบริการ", "บริการดี", "บริการ", "ห้าขั้นตอน", "5ขั้นตอน"),
     "💛 ป้าเข็มดูแลลูกค้าตามมาตรฐาน 5 ขั้นตอนจ๊ะ:\n\n"
     "1️⃣ การต้อนรับที่อบอุ่น — ทักทายด้วยความยินดี เป็นกันเอง สุภาพ พร้อมให้บริการเสมอ\n"
     "2️⃣ การรับฟังอย่างตั้งใจ — เข้าใจสิ่งที่อยากได้ ไม่ขัดจังหวะ ยืนยันข้อมูลให้ถูกต้อง\n"
     "3️⃣ การนำเสนอทางเลือกที่เหมาะสม — แนะนำสินค้าที่ตรงจุด ให้ข้อมูลชัดเจนครบถ้วน ตอบอย่างจริงใจ\n"
     "4️⃣ การดำเนินการที่รวดเร็วและมีประสิทธิภาพ — ลดขั้นตอนยุ่งยาก แจ้งสถานะ แก้ปัญหาให้ทันที\n"
     "5️⃣ การติดตามผลและขอบคุณ — ถามความพึงพอใจ รับฟังความคิดเห็น กล่าวขอบคุณจากใจ\n\n"
     "ความพึงพอใจของคุณคือความสำเร็จของป้าเข็มนะคะ 💕"),
]


# --- ติดตั้ง/สิ่งที่ต้องมี — ลูกค้า vs เจ้าของร้าน (ตอบคนละแบบ) ---
INSTALL_KWS = ("ติดตั้ง", "ต้องมีอะไร", "ต้องเตรียม", "เตรียมอะไร", "ลงแอป", "ลงอะไร", "ตั้งค่าระบบ", "ตั้งค่า", "เริ่มใช้", "เริ่มต้นใช้")
INSTALL_REPLY_CUSTOMER = (
    "✅ ไม่ต้องติดตั้งอะไรเลยจ๊ะ — ป้าเข็มใช้ผ่าน LINE โดยตรง "
    "แค่กดแอดไลน์ร้าน แล้วพิมพ์ชื่อสินค้า/ถามได้ทันที "
    "(มือถือ คอม แท็บเล็ต ใช้ได้หมด ไม่ต้องลงแอปเพิ่ม ไม่มีค่าใช้จ่าย)\n\n"
    "ลองพิมพ์ \"ค้นสินค้า\" หรือชื่อที่อยากได้ เช่น \"หูฟังไม่เกิน 300\" ได้เลยจ๊ะ 😊\n\n"
    "💻 อยากเอาโค้ดไปเปิดร้านเอง? โค้ดอยู่บน GitHub: g81393878-bit/shopee-affiliate-bot"
)
INSTALL_REPLY_OWNER = (
    "🛠️ เอาโค้ดไปใช้เอง ไม่ยากจ๊ะ — เตรียม 4 อย่าง (ฟรีทั้งหมด):\n"
    "① บัญชี LINE ร้านค้า (LINE OA) — หน้าร้าน\n"
    "② บัญชี Shopee Affiliate — ทำลิงก์ค่าคอม + import สินค้า (สมัครฟรี)\n"
    "③ ที่เก็บข้อมูล + เซิร์ฟเวอร์ (Supabase + Render) — ฟรี\n"
    "④ คีย์ AI (Groq/Gemini) — ฟรี\n\n"
    "💻 โค้ดอยู่บน GitHub — แตะปุ่มด้านล่างเปิดได้เลยจ๊ะ"
)


GITHUB_REPO_URL = "https://github.com/g81393878-bit/shopee-affiliate-bot"
SETUP_GUIDE_URL = GITHUB_REPO_URL + "/blob/main/docs/setup-guide.md"


def _wants_code_buttons(text: str) -> bool:
    """ถามเรื่องติดตั้ง/โค้ด/ดาวน์โหลด → แนบปุ่มเปิด GitHub + คู่มือให้แตะได้ทันที (อำนวยความสะดวก)"""
    t = (text or "").strip().lower().replace(" ", "")
    return any(k in t for k in INSTALL_KWS) or \
        any(k in t for k in ("โค้ด", "github", "ดาวน์โหลด", "ซอร์ส", "source"))


def _github_button_card():
    """ปุ่ม 2 ตัว (URI action): เปิด GitHub + คู่มือติดตั้ง — แตะได้เลย ไม่ต้องก๊อปลิงก์"""
    return FlexSendMessage(
        alt_text="เปิดโค้ด GitHub",
        contents={
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "💻 โค้ดป้าเข็ม (ฟรี เปิดเผย)", "weight": "bold", "size": "sm", "wrap": True},
                ],
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "button", "style": "primary", "color": "#EE4D2D", "height": "sm",
                     "action": {"type": "uri", "label": "📦 เปิด GitHub", "uri": GITHUB_REPO_URL}},
                    {"type": "button", "style": "secondary", "color": "#334155", "height": "sm",
                     "action": {"type": "uri", "label": "📖 คู่มือติดตั้ง (ทีละขั้น)", "uri": SETUP_GUIDE_URL}},
                ],
            },
        },
    )


# หัวข้อที่ตอบละเอียดเฉพาะเจ้าของร้าน/คนอยากเปิดร้านเอง — ลูกค้าทั่วไปถาม → ตอบสั้นชี้ทางแทน
# (กันข้อมูลตั้งระบบ/รายได้ของร้านหลุดไปหาลูกค้าทั่วไป)
OWNER_ONLY_KWS = (
    "สมัครไลน์oa", "สมัครlineoa", "สมัครไลน์", "สมัครบัญชีไลน์", "เปิดไลน์oa", "lineoaสมัคร",
    "สมัครshopee", "สมัครaffiliate", "สมัครแอฟฟิลิเอต", "สมัครนายหน้า", "affiliateสมัคร",
    "ได้เงินจริง", "ได้เงินยังไง", "ถอนเงิน", "ถอนค่าคอม", "เบิกเงิน",
)
OWNER_ONLY_CUSTOMER_REPLY = (
    "💁‍♀️ เรื่องนี้เป็นข้อมูลของคนอยากเปิดร้านเองจ๊ะ — สำหรับคุณ ลองพิมพ์ชื่อสินค้า "
    "หรือแตะ 'วันนี้ขายอะไรดี' ให้ป้าเข็มหาให้เลยค่ะ 😊"
)


# กัน keyword "คีย์" (คีย์ AI/API) ไปแมตช์ซับสตริงใน "คีย์บอร์ด"/"คีย์บอรด" (keyboard)
# — ลูกค้าหาคีย์บอร์ดต้องได้สินค้า ไม่ใช่คำตอบเรื่องคีย์ AI (คลังจริงมีคีย์บอร์ด 5+6 ตัว)
KEYBOARD_VARIANTS = ("คีย์บอร์ด", "คีย์บอรด")


def _mask_keyboard(t: str) -> str:
    """'คีย์บอร์ด'/'คีย์บอรด' → 'คียบอร์ด' (ตัดสระโท) กัน keyword 'คีย์' แมตช์กลางคำ"""
    for kb in KEYBOARD_VARIANTS:
        t = t.replace(kb, "คียบอร์ด")
    return t


def bot_manual_reply(text: str, is_owner: bool = False) -> str:
    """ตอบคำถามเรื่องบอทจากคู่มือ — เจอหัวข้อตามคำสำคัญตอบเฉพาะส่วน, ไม่ตรง → คู่มือเต็ม
    หัวข้อติดตั้ง/สมัคร/รายได้ = เฉพาะเจ้าของร้าน; ลูกค้าทั่วไปได้คำตอบสั้นชี้ทาง"""
    t = _mask_keyboard((text or "").strip().lower().replace(" ", ""))
    if any(k in t for k in INSTALL_KWS) or _wants_code_buttons(t):
        return INSTALL_REPLY_OWNER if is_owner else INSTALL_REPLY_CUSTOMER
    for kws, section in BOT_MANUAL_SECTIONS:
        if any(k in t for k in kws):
            if not is_owner and any(k in t for k in OWNER_ONLY_KWS):
                return OWNER_ONLY_CUSTOMER_REPLY
            return section
    return BOT_MANUAL


# --- เทียบสินค้า A กับ B (แบบ Amazon "Compare with": ข้อมูลจริงในคลัง ไม่ AI เดา) ---
COMPARE_PREFIXES = ("เปรียบเทียบราคา", "เปรียบเทียบ", "เทียบราคา", "เทียบ")
COMPARE_SEPS = (" กับ ", " และ ", "กับ", "และ")
COMPARE_HELP = (
    "⚖️ เทียบสินค้าจ๊ะ! พิมพ์แบบนี้:\n\n"
    "• \"เทียบ GOOJODOQ กับ Jeep\"\n"
    "• \"เทียบราคากระติก ESKIMO กับ YTL\"\n"
    "• \"เปรียบเทียบหูฟัง A กับ B\"\n\n"
    "ป้าเข็มจะเทียบ ราคา/ยอดขาย/รีวิว ให้ดูจ๊ะ"
)


def _compare_pair(raw_text: str) -> Optional[Tuple[str, str]]:
    """แยก \"เทียบ A กับ B\" → (A, B) — ตัดคำนำหน้า + คำต่อท้ายเล่นๆ"""
    t = raw_text.strip()
    for p in COMPARE_PREFIXES:  # เรียงคำยาวก่อน (เปรียบเทียบ > เทียบ)
        if t.startswith(p):
            t = t[len(p):]
            break
    # ลบคำต่อท้ายแบบระบุชัด (ห้าม strip ตัวอักษรไทย — "ห" ใน "หูฟัง" จะโดนกิน)
    for suf in (" หน่อย", " ให้หน่อย", " ให้ที", " ที", " ให้", " จ๊ะ", " ค่ะ", "หน่อย", "จ๊ะ", "ค่ะ"):
        if t.endswith(suf):
            t = t[: -len(suf)]
            break
    t = t.strip()
    for sep in COMPARE_SEPS:
        if sep in t:
            q1, q2 = t.split(sep, 1)
            q1, q2 = q1.strip(), q2.strip()
            if len(q1) >= 2 and len(q2) >= 2:
                return q1, q2
    return None


def _fmt_num(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


_SPEC_SIZE_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:ลิตร|แกลลอน|L\b|ML\b|มล\.?|Oz\b|ออนซ์|ฟุต|นิ้ว|ซม\.?|CM\b|เมตร|M\b|Kg\b|กก\.?|กรัม|G\b|W\b|วัตต์|ว)"
    r"|\d+(?:/\d+)+\s*ฟุต", re.IGNORECASE)
_SPEC_QTY_RE = re.compile(
    r"(?:แพ็ค|แพ็ก|พัค|กล่อง|ถุง|ชิ้น|ตัว|คู่|แผ่น|ม้วน|อัน|หลอด|ขวด)\s*\d+"
    r"|\d+\s*(?:ชิ้น|ตัว|ถุง|กล่อง|แพ็ค|แพ็ก|คู่|แผ่น|ม้วน|หลอด|ขวด|อัน|กระปุก|ก้อน)", re.IGNORECASE)


def extract_specs(name: str) -> str:
    """ดึงสเปคสำคัญจากชื่อ (ขนาด/ปริมาตร/จำนวน) — โชว์ในการ์ดเทียบ
    กันเทียบแบบไม่รู้ว่าเทียบขนาดอะไร ('2L' กับ '6-30L' ควรเห็นชัด)"""
    t = (name or "").strip()
    if not t:
        return ""
    def dedupe(items):
        """ตัดค่าซ้ำ — '2L' กับ '2 ลิตร' คือขนาดเดียวกัน เก็บแค่ตัวแรก (สั้น/อ่านง่ายกว่า)"""
        seen, seen_nums = [], []
        for s in items:
            s = s.strip()
            num = re.sub(r"[^0-9.,]", "", s).replace(",", ".")
            try:
                key = round(float(num), 2)
            except ValueError:
                key = None
            if s and s not in seen and (key is None or key not in seen_nums):
                seen.append(s)
                if key is not None:
                    seen_nums.append(key)
        return seen

    sizes = re.findall(_SPEC_SIZE_RE, t)
    qties = re.findall(_SPEC_QTY_RE, t)
    parts = []
    if sizes:
        parts.append("ขนาด " + "/".join(dedupe(sizes)[:4]))
    if qties:
        parts.append("จำนวน " + "/".join(dedupe(qties)[:3]))
    return " · ".join(parts)


def spec_size_numbers(spec: str) -> list:
    """ตัวเลขขนาดจากสเปค (สำหรับเทียบว่าขนาดต่างกันหรือไม่)"""
    if not spec:
        return []
    return [float(m.replace(",", ".")) for m in re.findall(r"\d+(?:[.,]\d+)?", spec)]


def compare_invite_message(hits: list) -> Optional[TextSendMessage]:
    """ค้นเจอ 2-3 ตัวคล้ายกัน (หมวดเดียวกัน) → ชวนเทียบ (แบบ Amazon Rufus)
    ปุ่มลัด 'เทียบ #1 กับ #2' — การ์ดสินค้าโชว์เลข 1/2/3 อยู่แล้ว ลูกค้าแตะจบไม่ต้องพิมพ์เอง
    คนละหมวด = ไม่ใช่ของใกล้กัน → ไม่ชวน (กันคำค้นกว้างๆ อย่าง 'ขวด' เด้งปุ่มรก)"""
    if len(hits) < 2:
        return None
    if (hits[0].category or "") != (hits[1].category or ""):
        return None
    buttons = []
    for i in range(1, len(hits)):
        if len(buttons) >= 2:
            break
        a, b = hits[0], hits[i]
        name_a = (a.name or "").strip()
        name_b = (b.name or "").strip()
        if not name_a or not name_b:
            continue
        buttons.append(QuickReplyButton(
            action=MessageAction(label=f"⚖️ เทียบ #1 กับ #{i + 1}",
                                 text=f"เทียบ {name_a[:25]} กับ {name_b[:25]}")))
    if not buttons:
        return None
    return TextSendMessage(
        text="👀 มี 2 ตัวใกล้กัน จะเทียบให้ดูไหม? แตะปุ่มด้านล่างจ๊ะ 👇",
        quick_reply=QuickReply(items=buttons))


def handle_compare(db, raw_text: str, user, is_owner: bool = False):
    """เทียบ A กับ B — การ์ด 2 คอลัมน์ (ลูกค้า: ราคา/ยอดขาย/รีวิว; เจ้าของ: +ค่านายหน้า/คะแนน AI) + ปุ่มซื้อทั้งคู่"""
    pair = _compare_pair(raw_text)
    if not pair:
        return TextSendMessage(text=COMPARE_HELP)
    q1, q2 = pair
    h1 = search_products(db, q1)
    h2 = search_products(db, q2)
    a = h1[0] if h1 else None
    b = h2[0] if h2 else None
    if not a and not b:
        return TextSendMessage(text=f"หาทั้ง \"{q1}\" และ \"{q2}\" ไม่เจอในร้านจ๊ะ "
                                     "ลองพิมพ์ชื่อสั้นๆ เช่น \"เทียบ GOOJODOQ กับ Jeep\" 😊")
    if not a or not b:
        found, missing = (a, q2) if a else (b, q1)
        # คู่เทียบไม่เจอ → แนะนำของใกล้เคียงหมวดเดียวกันแทน (ลูกค้าได้ทางเลือก ไม่สะดุด)
        title = f"🔎 หา \"{missing}\" ไม่เจอ"
        if found.category:
            title += f" — ลองดูของใกล้เคียงหมวด \"{found.category}\" แทนจ๊ะ"
        else:
            title += " — ลองดูของใกล้เคียงแทนจ๊ะ"
        if not found.category:
            return product_cards_message(db, user, [found], title=title, is_owner=is_owner)
        similar = (db.query(models.Product)
                     .filter(models.Product.link_status == "ok",
                             models.Product.sales_count >= MIN_SALES,
                             models.Product.category == found.category,
                             models.Product.id != found.id)
                     .order_by(models.Product.ai_score.desc()).limit(2).all())
        return product_cards_message(db, user, [found] + similar, title=title, is_owner=is_owner)

    # สเปค (ขนาด/จำนวน) จากชื่อ — โชว์ในการ์ด + ใช้เทียบว่าคนละขนาด/ชนิดหรือไม่
    spec_a, spec_b = extract_specs(a.name), extract_specs(b.name)
    nums_a, nums_b = spec_size_numbers(spec_a), spec_size_numbers(spec_b)
    facts = []
    # เตือนเมื่อขนาดต่างกันมาก (เทียบคนละประเภท เช่น กระติก 2L กับกล่องแคมป์ปิ้ง 6-30L)
    if nums_a and nums_b:
        mn, mx = min(min(nums_a), min(nums_b)), max(max(nums_a), max(nums_b))
        if mn > 0 and mx / mn >= 3:
            facts.append(f"⚠️ ขนาดต่างกันมาก ({spec_a} vs {spec_b}) — ดูขนาด/จำนวนให้ตรงกับที่ต้องการ")
    # เตือนเมื่อคนละหมวด (กันเทียบคนละชนิดโดยไม่รู้ตัว — ตัวเลขเทียบได้คร่าวๆ เท่านั้น)
    if (a.category or "") != (b.category or "") and a.category and b.category:
        facts.append(f"⚠️ {a.category} vs {b.category} — คนละหมวด ควรดูคุณสมบัติ/ขนาดประกอบ")
    if (a.sales_count or 0) != (b.sales_count or 0):
        better = a if (a.sales_count or 0) > (b.sales_count or 0) else b
        tag = "🅰️" if better is a else "🅱️"
        facts.append(f"{tag} ขายดีกว่า ({_fmt_num(better.sales_count)} ชิ้น)")
    # ค่านายหน้า = ข้อมูลฝั่งคนขาย → เฉพาะเจ้าของร้านถึงเห็น (ลูกค้าเห็นการ์ดสะอาด)
    if is_owner and (a.commission or 0) != (b.commission or 0):
        better = a if (a.commission or 0) > (b.commission or 0) else b
        tag = "🅰️" if better is a else "🅱️"
        facts.append(f"{tag} ค่านายหน้าสูงกว่า (฿{float(better.commission or 0):,.0f})")
    return compare_flex_message(a, b, facts, spec_a, spec_b, is_owner=is_owner)


def compare_flex_message(a, b, facts: list, spec_a: str = "", spec_b: str = "",
                         is_owner: bool = False) -> FlexSendMessage:
    """การ์ดเทียบ 2 คอลัมน์ใบเดียว (แบบตาราง Amazon) — ชื่อ/สเปค/ราคา/ยอดขาย + ปุ่มซื้อ
    is_owner=True (เจ้าของ): เพิ่ม 💸 คอม + 📈 คะแนน AI (ข้อมูลฝั่งคนขาย — ลูกค้าไม่เห็น)
    ลูกค้าเห็น ⭐ รีวิวแทน (ข้อมูลซื้อสาธารณะเหมือนการ์ดปกติ)
    โชว์ 📐 ขนาด/จำนวน (เช่น 2L vs 6L-30L) กันเทียบคนละขนาดโดยไม่รู้ตัว
    ชื่อไทยยาว: size xs + maxLines 3 + wrap — ไม่ล้นการ์ด"""
    def col(p, tag, spec):
        contents = [
            {"type": "text", "text": tag, "size": "xs", "align": "center", "color": "#999999"},
            {"type": "text", "text": p.name, "size": "xs", "wrap": True, "maxLines": 3, "weight": "bold"},
        ]
        if spec:
            contents.append({"type": "text", "text": f"📐 {spec}", "size": "xxs",
                             "color": "#B8860B", "align": "center", "wrap": True})
        contents += [
            {"type": "separator"},
            {"type": "text", "text": f"💰 {float(p.price or 0):,.0f}฿", "size": "sm",
             "weight": "bold", "color": "#E74C3C", "align": "center"},
            {"type": "text", "text": f"📦 ขาย {_fmt_num(p.sales_count)}", "size": "xxs",
             "color": "#666666", "align": "center", "wrap": True},
        ]
        # ข้อมูลฝั่งคนขาย (ค่านายหน้า/คะแนน AI) เฉพาะเจ้าของ — ลูกค้าเห็น ⭐ รีวิวแทน
        if is_owner:
            contents += [
                {"type": "text", "text": f"💸 คอม {float(p.commission or 0):,.0f}฿", "size": "xxs",
                 "color": "#666666", "align": "center", "wrap": True},
                {"type": "text", "text": f"📈 {p.ai_score or 0}/100", "size": "xxs",
                 "color": "#666666", "align": "center", "wrap": True},
            ]
        elif p.rating and float(p.rating) > 0:
            contents.append({"type": "text", "text": f"⭐ {float(p.rating):.1f}", "size": "xxs",
                             "color": "#666666", "align": "center", "wrap": True})
        contents.append({"type": "button", "style": "primary", "color": "#E74C3C", "height": "sm",
                         "action": {"type": "uri", "label": "🛒 ซื้อเลย", "uri": p.affiliate_url}})
        return {"type": "box", "layout": "vertical", "flex": 1, "spacing": "sm", "contents": contents}

    header = {
        "type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": "⚖️ เทียบสินค้า", "weight": "bold", "size": "md",
             "align": "center", "color": "#E74C3C"},
        ],
    }
    body = {
        "type": "box", "layout": "horizontal", "spacing": "lg",
        "contents": [col(a, "🅰️", spec_a), col(b, "🅱️", spec_b)],
    }
    contents = {"type": "bubble", "header": header, "body": body}
    if facts:
        contents["footer"] = {
            "type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": "💡 " + " · ".join(facts),
                 "size": "xxs", "color": "#999999", "wrap": True, "align": "center"},
            ],
        }
    return FlexSendMessage(alt_text="⚖️ เทียบสินค้า 2 ตัว", contents=contents)


WHY_US_YOUTH = (
    "💛 ทำไมต้องซื้อกับร้านป้าเข็ม? จ้าา\n\n"
    "1️⃣ ราคาเท่ากันเป๊ะ\n"
    "ป้าเป็นนายหน้า ค่านายหน้าจ่ายโดย Shopee/แบรนด์ ไม่บวกในราคา — จ่ายเท่าราคาปกติ\n\n"
    "2️⃣ คัดมาแล้วว่าดีจริง\n"
    "เฉพาะของที่ขายดีจริง + ลิงก์ไม่ตาย ถึงเข้าร้าน ไม่มีของกากมาให้เสียเวลา\n\n"
    "3️⃣ ข้อมูลจริง ไม่พาดหัวลวง\n"
    "ราคาบอก \"เริ่มต้น\" ตามตรง ยอดขายตัวเลขจริง กดไปเห็นโปรจริงที่หน้าร้าน\n\n"
    "4️⃣ จำได้ว่าคุณชอบอะไร\n"
    "บอก \"จำไว้ ชอบหูฟัง\" → ของใหม่/ราคาลง ป้าแจ้งก่อนใคร\n\n"
    "5️⃣ ดูแลหลังขาย 24 ชม.\n"
    "ทวงพัสดุ/สงสัยอะไร พิมพ์ถามได้ตลอด\n\n"
    "ลองพิมพ์ชื่อสินค้าดูเลยจ้า เช่น \"หูฟังไม่เกิน 300\" 😎"
)

WHY_US_ELDER = (
    "💛 ทำไมต้องซื้อกับร้านป้าเข็มคะ?\n\n"
    "1️⃣ ราคาเท่ากันเป๊ะ\n"
    "ป้าเข็มเป็นนายหน้า ค่านายหน้าจ่ายโดย Shopee/แบรนด์ ไม่ได้บวกในราคา — จ่ายเท่าราคาปกติบน Shopee\n\n"
    "2️⃣ คัดมาแล้วว่าดีจริง\n"
    "เฉพาะของที่ขายดีจริง + ลิงก์ตรวจแล้วไม่ตาย ถึงจะเข้าร้าน\n\n"
    "3️⃣ ข้อมูลจริง ไม่พาดหัวลวง\n"
    "ราคาบอก \"เริ่มต้น\" ตามตรง ยอดขายเป็นตัวเลขจริง กดลิงก์ไปเห็นราคาจริงที่หน้าร้าน\n\n"
    "4️⃣ ป้าเข็มจำได้ว่าคุณชอบอะไร\n"
    "บอก \"จำไว้ ชอบหูฟัง\" → มีของใหม่/ราคาลง ป้าเข็มจะแจ้งก่อนใคร\n\n"
    "5️⃣ ดูแลหลังขาย 24 ชม.\n"
    "ทวงถามพัสดุ/สงสัยอะไร พิมพ์ถามได้ตลอดค่ะ\n\n"
    "ลองพิมพ์ชื่อสินค้าดูได้นะคะ เช่น \"หูฟังไม่เกิน 300\" ค่ะ 😊"
)


def why_us_text(tone: str = "neutral") -> str:
    """ทำไมต้องซื้อกับป้าเข็ม — ปรับโทนตามวัย (neutral = ข้อความเดิม)"""
    if tone == "youth":
        return WHY_US_YOUTH
    if tone == "elder":
        return WHY_US_ELDER
    return (
        "💛 ทำไมต้องซื้อกับร้านป้าเข็ม?\n\n"
        "1️⃣ ราคาเท่ากันเป๊ะ\n"
        "ป้าเข็มเป็นนายหน้า ค่านายหน้าจ่ายโดย Shopee/แบรนด์"
        " ไม่ได้บวกขึ้นในราคา — กดซื้อจ่ายเท่าราคาปกติบน Shopee ทุกประการ\n\n"
        "2️⃣ คัดมาแล้วว่าดีจริง\n"
        "เฉพาะของที่ขายดีจริง + ลิงก์ตรวจแล้วไม่ตาย ถึงจะเข้าร้าน"
        " ของยอดขายน้อย/ลิงก์เสีย ไม่มีโผล่ให้เสียเวลา\n\n"
        "3️⃣ ข้อมูลจริง ไม่พาดหัวลวง\n"
        "ราคาบอก \"เริ่มต้น\" ตามตรง ยอดขายเป็นตัวเลขจริง"
        " กดลิงก์ไปเห็นราคาโปรโมชันจริงที่หน้าร้าน\n\n"
        "4️⃣ ป้าเข็มจำได้ว่าคุณชอบอะไร\n"
        "บอก \"จำไว้ ชอบหูฟัง\" → มีของใหม่/ราคาลง ป้าเข็มแจ้งก่อนใคร\n\n"
        "5️⃣ ดูแลหลังขาย 24 ชม.\n"
        "ทวงถามพัสดุ/สงสัยอะไร พิมพ์ถามได้ตลอด — ป้าเข็มช่วยหาคำตอบให้\n\n"
        "ลองพิมพ์ชื่อสินค้าดูเลยจ๊ะ เช่น \"หูฟังไม่เกิน 300\" 😊"
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



# เขียนลง Google ชีทอัตโนมัติ (ผ่าน Apps Script Web App — ฟรี ไม่ต้อง API key)
# ตั้ง env SHEET_WEBHOOK_URL = URL web app ที่ deploy ใน sheet_apps_script.gs
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL", "")

# intent → ภาษาไทย (ชีทให้เจ้าของอ่านง่าย — ไม่ใช่โค้ด)
INTENT_LABELS = {
    "search": "ค้นสินค้า", "greeting": "ทักทาย", "nosearch": "ค้นไม่เจอ",
    "manual": "ถามคู่มือ", "human": "ฝากคำถาม", "compare": "เทียบสินค้า",
    "deals": "ขายดี", "top": "อันดับขายดี", "why_us": "ทำไมต้องป้าเข็ม",
    "wismo": "ทวงพัสดุ", "remember": "จำความชอบ", "delete": "ลบข้อมูล",
    "new": "มีอะไรใหม่", "guide": "คู่มือค้น",
    "campaign": "แคมเปญ", "admin": "แอดมิน", "error": "ผิดพลาด",
    "emotion": "ระบายอารมณ์", "web": "ค้นเน็ต", "browse": "ดูหมวดสินค้า",
}


def _push_to_sheet(row: dict) -> None:
    """push 1 แถวไป Google ชีท — fire-and-forget (background) กันไม่หน่วงการตอบ LINE
    Apps Script web app ตอบ 302 (redirect ไป script.googleusercontent.com/macros/echo)
    — ต้อง follow_redirects=True (httpx ปิดไว้โดยค่าเริ่มต้น ไม่งั้นแถวไม่ถึงชีท)"""
    if not SHEET_WEBHOOK_URL:
        return
    try:
        import httpx
        httpx.post(SHEET_WEBHOOK_URL, json=row, timeout=5, follow_redirects=True)
    except Exception as e:
        logger.debug(f"sheet push failed: {e}")


def _reply_text(reply) -> str:
    """ดึงข้อความที่บอทตอบ (เก็บลงชีท "คำตอบ") — การ์ด Flex เก็บแค่ป้ายสั้น ไม่เก็บทั้งการ์ด"""
    if isinstance(reply, str):
        return reply[:300]
    if isinstance(reply, TextSendMessage):
        return (reply.text or "")[:300]
    if isinstance(reply, FlexSendMessage):
        alt = getattr(reply, "alt_text", "") or ""
        return (alt or "[การ์ดสินค้า]")[:300]
    if isinstance(reply, (list, tuple)):
        parts = [_reply_text(m) for m in reply]
        return " | ".join(p for p in parts if p)[:300]
    return ""


def _push_sheet_async(row: dict) -> None:
    """รัน push ชีทใน thread แยก — ตอบ LINE ทันที ไม่รอ Google"""
    try:
        import threading
        threading.Thread(target=_push_to_sheet, args=(row,), daemon=True).start()
    except Exception:
        pass


def log_chat(db, line_user_id: str, text: str, intent: str, reply, category: Optional[str] = None):
    """บันทึกประวัติสนทนา + หมวดที่ลูกค้าสนใจ (PDPA: เก็บแค่ 90 วัน — ลบของเก่าทุกครั้งที่เขียน)
    category ต่อยอด: รู้ว่าลูกค้าสนใจหมวดอะไร → วิเคราะห์/แนะนำสินค้า/ทำการตลาด
    พร้อมกันนั้น เขียนแถวลง Google ชีทอัตโนมัติ (ถ้าตั้ง SHEET_WEBHOOK_URL) —
    ชีทสำรองใช้วิเคราะห์ระยะยาว (Apps Script ลบของเก่า 90 วันให้เอง)"""
    kind = 'flex' if (isinstance(reply, FlexSendMessage) or
                       (isinstance(reply, list) and any(isinstance(m, FlexSendMessage) for m in reply))) else 'text'
    db.add(models.ChatLog(line_user_id=line_user_id, message_text=text[:500],
                          intent=intent, category=category, reply_kind=kind))
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)
    db.query(models.ChatLog).filter(models.ChatLog.created_at < cutoff).delete(synchronize_session=False)
    db.commit()
    _push_sheet_async({
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "line_user_id": line_user_id,
        "message_text": text[:500],
        "intent": intent,
        "intent_label": INTENT_LABELS.get(intent, intent),
        "category": category,
        "reply_kind": kind,
        "reply_text": _reply_text(reply),
    })


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


# --- เมนูหมวดสินค้า (เดินดูร้านเองได้ เหมือนเข้าร้านจริง — ไม่ต้องรู้ชื่อสินค้า) ---
CATEGORY_MENU_PHRASES = (
    "หมวดสินค้า", "หมวด", "เมนูสินค้า", "หมวดหมู่", "ดูหมวด",
    "ดูหมวดสินค้า", "ดูสินค้า", "เดินดูร้าน", "ดูร้าน", "หมวดอะไร", "มีหมวดอะไร",
    "มีหมวดอะไรบ้าง", "หมวดสินค้ามีอะไรบ้าง", "สินค้ามีอะไร", "สินค้ามีอะไรบ้าง",
)
CATEGORY_PICK_PREFIX = "ดูหมวด"
CATEGORY_MENU_MAX_BUTTONS = 13


def _sellable_categories(db: Session) -> list:
    """หมวด + จำนวนที่ขายได้จริง (ลิงก์ ok + ถึงเกณฑ์ขาย) เรียงมาก→น้อย, อื่นๆ ไว้ท้าย"""
    rows = (db.query(models.Product.category, func.count(models.Product.id))
              .filter(models.Product.link_status == "ok",
                      models.Product.sales_count >= MIN_SALES)
              .group_by(models.Product.category).all())
    cats = [(c or "อื่นๆ", n) for c, n in rows if c]
    real = [(c, n) for c, n in cats if c != "อื่นๆ"]
    real.sort(key=lambda r: (-r[1], r[0]))
    other = [r for r in cats if r[0] == "อื่นๆ"]
    return real + other


def _category_menu_quick_reply(db: Session) -> QuickReply:
    """ปุ่มหมวดยอดนิยม (แตะแล้วดูของขายดีหมวดนั้นทันที) — หมวดจริง 12 + อื่นๆ"""
    cats = _sellable_categories(db)
    real = [c for c in cats if c[0] != "อื่นๆ"]
    other = [c for c in cats if c[0] == "อื่นๆ"]
    picked = real[:CATEGORY_MENU_MAX_BUTTONS - 1] + other[:1]
    items = []
    for cat, _n in picked:
        label = cat if cat != "อื่นๆ" else "✨ อื่นๆ"
        items.append(QuickReplyButton(action=MessageAction(label=label, text=f"{CATEGORY_PICK_PREFIX}{cat}")))
    return QuickReply(items=items)


def category_menu_message(db: Session) -> TextSendMessage:
    """เมนูหมวดสินค้า — แตะหมวด → ของขายดีหมวดนั้น"""
    cats = _sellable_categories(db)
    if not cats:
        return TextSendMessage(text="🛍️ ยังไม่มีสินค้าในร้านตอนนี้จ๊ะ ลองใหม่พรุ่งนี้นะคะ 😊")
    total = sum(n for _c, n in cats)
    return TextSendMessage(
        text=f"🛍️ ร้านป้าเข็มมีสินค้า {total:,} ตัว — แตะหมวดที่อยากเดินดูได้เลยจ๊ะ 👇",
        quick_reply=_category_menu_quick_reply(db))


def browse_category_message(db: Session, user, cat: str, is_owner: bool = False):
    """แตะหมวด → ของขายดีในหมวดนั้น (5 ตัว) + ปุ่มหมวดให้เดินดูต่อ"""
    cat = (cat or "").strip()
    if not cat:
        return category_menu_message(db)
    prods = (db.query(models.Product)
               .filter(models.Product.link_status == "ok",
                       models.Product.sales_count >= MIN_SALES,
                       models.Product.category == cat)
               .order_by(models.Product.ai_score.desc()).limit(5).all())
    if not prods:
        return TextSendMessage(
            text=f"หมวด {cat} ยังไม่มีของขายดีในตอนนี้จ๊ะ — แตะหมวดอื่นด้านล่างได้เลย 👇",
            quick_reply=_category_menu_quick_reply(db))
    # ปุ่มหมวดต้องติดข้อความสุดท้าย (การ์ด) — LINE ลบ quick reply ทันทีที่
    # บอทส่งข้อความถัดไป (การ์ด) ไม่งั้นปุ่มหายก่อนลูกค้าเห็น
    cards = product_cards_message(db, user, prods, title=f"🛍️ หมวด {cat}", is_owner=is_owner)
    cards.quick_reply = _category_menu_quick_reply(db)
    return [
        TextSendMessage(text=f"🛍️ ของขายดีในหมวด {cat} จ๊ะ — แตะหมวดอื่นต่อได้เลย 👇"),
        cards,
    ]


# --- สินค้าใหม่ส่วนตัว (Amazon-style: จำที่ลูกค้าสนใจ ไม่ต้องเริ่มใหม่) ---
NEW_PHRASES = ("มีอะไรใหม่", "ของใหม่", "สินค้าใหม่", "อะไรใหม่", "มีของใหม่", "ของใหม่มีอะไร")


# --- Account Memory (Amazon-style): ลูกค้าบอกให้ป้าเข็มจำไว้ ---
REMEMBER_SAVE_PREFIXES = ("จำไว้", "จำไว้ว่า", "จดไว้", "จำให้หน่อย", "ช่วยจำ", "จำได้มั้ยว่า")
REMEMBER_SHOW_PHRASES = ("จำได้ไหม", "ป้าเข็มจำ", "จำอะไรไว้", "จำอะไรบ้าง")


def _saved_categories(db, line_user_id: str) -> list:
    """หมวดที่ลูกค้าบอกให้จำไว้ (user_preferences) — ข้อมูลที่ลูกค้าระบุเอง"""
    pref = (db.query(models.UserPreference)
              .filter(models.UserPreference.line_user_id == line_user_id).first())
    if pref and pref.categories:
        return [c for c in pref.categories if c]
    return []


def _saved_notes(db, line_user_id: str) -> list:
    pref = (db.query(models.UserPreference)
              .filter(models.UserPreference.line_user_id == line_user_id).first())
    if pref and pref.notes:
        return [n for n in pref.notes if n]
    return []


def _remember_categories_from_note(note: str) -> list:
    """หา "หมวด" ที่ลูกค้าพูดถึงในโน้ต (เช่น "เลี้ยงแมว 2 ตัว" → แมว) —
    ใช้ keyword เดียวกับ guess_category (แมตช์ยาวสุดก่อน) + guess_category รวม"""
    cats = []
    for kw, cat in CATEGORY_KEYWORDS:
        if kw in note and cat not in cats:
            cats.append(cat)
    fallback = guess_category(note)
    if fallback and fallback not in cats:
        cats.append(fallback)
    return cats


def handle_remember(db, raw_text: str, line_user_id: str, user) -> TextSendMessage:
    """Account Memory — "จำไว้ <อะไร>" เก็บหมวด/โน้ต; "ป้าเข็มจำได้ไหม" อ่านคืน"""
    if any(raw_text.startswith(p) for p in REMEMBER_SHOW_PHRASES):
        cats = _saved_categories(db, line_user_id)
        notes = _saved_notes(db, line_user_id)
        if not cats and not notes:
            return TextSendMessage(text=f"ยังไม่มีอะไรให้ป้าเข็มจำจ๊ะ {user.name} 😊\n\n"
                                        "ลองบอกป้าเข็มได้เลย เช่น \"จำไว้ จริงๆ ชอบหูฟังไม่เกิน 300\" "
                                        "เดี๋ยวมีของใหม่ป้าเข็มจะนึกถึงคุณก่อนเลยจ๊ะ")
        parts = []
        if cats:
            parts.append(f"• หมวดที่ชอบ: {' '.join(cats)}")
        if notes:
            parts.append(f"• ที่จำไว้: {' / '.join(notes)}")
        return TextSendMessage(text=f"ป้าเข็มจำได้จ๊ะ {user.name} 😊\n\n" + "\n".join(parts) +
                                "\n\nมีของใหม่ในหมวดนี้ป้าเข็มจะนึกถึงคุณก่อนเลยจ๊ะ 🎯")
    for p in REMEMBER_SAVE_PREFIXES:
        if raw_text.startswith(p):
            note = raw_text[len(p):].strip(" ว่า :,")
            if not note:
                return TextSendMessage(text="จะให้ป้าเข็มจำอะไรดีจ๊ะ เช่น \"จำไว้ ชอบหูฟังไม่เกิน 300\" 😊")
            cats = _remember_categories_from_note(note)
            pref = (db.query(models.UserPreference)
                      .filter(models.UserPreference.line_user_id == line_user_id).first())
            if not pref:
                pref = models.UserPreference(line_user_id=line_user_id, categories=[], notes=[])
                db.add(pref)
            merged_cats = list(dict.fromkeys(list(pref.categories or []) + cats))
            merged_notes = list(dict.fromkeys(list(pref.notes or []) + [note]))
            pref.categories = merged_cats
            pref.notes = merged_notes
            db.commit()
            line = f"จำไว้แล้วจ๊ะ {user.name} 😊\n\n📝 {note}"
            if cats:
                line += f"\n\n🛍️ ป้าเข็มจะแนะนำของหมวด {', '.join(cats)} ให้คุณก่อนเลย"
            line += "\n\nพิมพ์ \"ป้าเข็มจำได้ไหม\" เพื่อดูว่าป้าเข็มจำอะไรไว้บ้างจ๊ะ"
            return TextSendMessage(text=line)
    return None


def _customer_categories(db, line_user_id: str) -> list:
    """หมวดที่ลูกค้าคนนี้สนใจ: (1) สิ่งที่บอกให้จำไว้ก่อน (2) เคยค้น (chat_logs) ตามความถี่"""
    from collections import Counter
    saved = _saved_categories(db, line_user_id)
    rows = (db.query(models.ChatLog.category)
              .filter(models.ChatLog.line_user_id == line_user_id,
                      models.ChatLog.intent == "search",
                      models.ChatLog.category.isnot(None)).all())
    c = Counter(r[0] for r in rows)
    merged = []
    for cat in saved:
        if cat not in merged:
            merged.append(cat)
    for k, _ in c.most_common():
        if k not in merged:
            merged.append(k)
    return merged


def handle_new_arrivals(db, user, line_user_id: str, is_owner: bool = False):
    """มีอะไรใหม่ — ดันสินค้าใหม่ในหมวดที่ลูกค้าเคยสนใจก่อน (แล้วค่อยของใหม่ทั่วไป)
    ไม่บังคับยอดขาย (ของใหม่ = เน้นความใหม่ของสินค้าในคลัง ไม่ใช่ขายดี) —
    ยังกรอง link_status == ok ตามนโยบายเด็ดขาด (เฉพาะของที่ตรวจลิงก์ผ่าน)"""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    recent = (db.query(models.Product)
                .filter(models.Product.link_status == "ok",
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
        recent = _trending_boost(recent, _hermes_skills(db).get("trending_categories"))
        return product_cards_message(db, user, recent[:3],
                                     "🆕 สินค้าใหม่เข้าคลังล่าสุด", is_owner=is_owner)
    return TextSendMessage(text="ตอนนี้ยังไม่มีสินค้าใหม่ค่ะ ลองค้นชื่อสินค้าดู หรือแตะ ขายดีวันนี้ ได้เลยนะคะ 😊")


# --- เอเจนต์ทำแคมเปญ (Alibaba-style: เลือกกลุ่มจากความสนใจจริง → ส่งการ์ด) ---
CAMPAIGN_LIMIT = 20  # สูงสุดต่อแคมเปญ — LINE OA จำกัด push/เดือน กันเกินโควตา


def _campaign_targets(db, category: str) -> list:
    """ลูกค้าเป้าหมาย: (1) บอกให้จำไว้ว่าชอบหมวดนี้ (2) เคยค้นหมวดนี้ (dedupe, ล่าสุดก่อน) — ไม่รวมเจ้าของร้าน"""
    targets = {}
    # กลุ่มที่บอกให้ป้าเข็มจำไว้ว่าชอบหมวดนี้ (กรองใน Python — ตารางเล็ก + กัน SQLite/Postgres ต่างกัน)
    for pref in db.query(models.UserPreference).all():
        if pref.categories and category in pref.categories:
            if pref.line_user_id not in targets and pref.line_user_id != ADMIN_LINE_USER_ID:
                targets[pref.line_user_id] = True
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
    if "mock" not in LINE_ACCESS_TOKEN.lower() and not push_guard(db):
        logger.warning("ข้าม campaign push (quota หมด)")
        return TextSendMessage(text="❌ ยังไม่ส่งแคมเปญ: LINE push quota หมดเดือนนี้แล้ว (ดู campaign_logs / อัปเกรดแผน)")
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


# คำนำหน้าเล่นๆ ที่คนไทยมักพิมพ์นำหน้าคำค้น ("อยากได้หูฟัง") — ตัดออกแล้ว
# เหลือคำหลักจริง ๆ เพื่อแมตช์ชื่อสินค้าได้แม่นขึ้น (กันแมตช์พลาดจากซับสตริงสั้นๆ)
FILLER_PREFIXES = ("อยากได้", "อยาก", "ขอ", "หา", "หาสินค้า", "มี", "ขาย",
                   "ซื้อ", "ช่วย", "เอา", "แนะนำ", "เห็น", "ส่ง")

PRICE_PHRASE_RES = (
    # 1) ช่วงราคา "200-400" — ตัดก่อน (กัน "งบ 500-700" เหลือเศษ)
    r"\d+\s*(?:-|–|ถึง)\s*\d+",
    # 2) "300 บาท"
    r"\d+(?:\.\d+)?\s*บาท",
    # 2b) ตัวเลขไทยคำ + บาท — "สองร้อยบาท" / "ร้อยบาท"
    r"(?:หนึ่ง|ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(?:สิบ|ร้อย|พัน|หมื่น|แสน|ล้าน)\s*บาท",
    # 3) เงื่อนไขต้องมีตัวเลขจริงตามหลัง — ห้าม \d* ว่าง เด็ดขาด กัน "งบ" กลางคำ:
    #    "หูฟังบลูทูธ" มี "ง"+"บ" ติดกัน (ขอบคำ) → ถ้ายอมไม่มีเลขจะตัด "งบ" ทิ้ง
    #    เหลือขยะ "หูฟัลูทูธ" หาไม่เจอ
    r"(?:ไม่เกิน|ไม่แพงกว่า|ไม่แพง|ต่ำกว่า|ถูกกว่า|งบ|ในงบ|ราคา|ประมาณ|ภายใน|ซื้อได้ใน)\s*\d+(?:\.\d+)?",
    # 3b) ตัวเลขไทยคำตามหลังคำบอกงบ — "ไม่เกินร้อย"/"งบสองพัน" (ลูกค้าพิมพ์จริง:
    #     "ถุงเท้าไม่เกินร้อย" — ก่อนแก้ regex รับแต่ตัวเลขอารบิก เลยหาไม่เจอ)
    r"(?:ไม่เกิน|ไม่แพงกว่า|ไม่แพง|ต่ำกว่า|ถูกกว่า|งบ|ในงบ|ราคา|ประมาณ|ภายใน|ซื้อได้ใน)\s*(?:หนึ่ง|ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(?:สิบ|ร้อย|พัน|หมื่น|แสน|ล้าน)",
    # 4) "ราคาไม่แพง/งบ 500" แบบไม่มีเลขเหลือ (ตัวเลขถูกตัดไปแล้ว) — ต้องมีเว้น
    #    วรรค/ต้นประโยคก่อนหน้า (ไม่ใช่กลางคำ)
    r"(?:\s|^)(?:งบ|ในงบ|ราคา|ประมาณ|ภายใน)\s*(?:ไม่แพง|ถูก|แพง)?",
)

# ท้ายคำถามแบบคนพิมพ์ (มีมั้ย/ได้ไหม/หน่อย...) — กันไปบังคับให้ชื่อสินค้าต้องมีคำถาม
# ระวัง "ผ้าไหม" (ไหม = ผ้าเนื้อไหม ไม่ใช่คำถาม) — เฉพาะกรณีนี้เท่านั้นที่ยกเว้น
QUESTION_SUFFIXES = ("หรือเปล่า", "หรือไม่", "หรือยัง", "มีมั้ย", "มีไหม", "ได้ไหม",
                    "ได้มั้ย", "เปล่า", "หน่อย", "เหรอ", "หรอ", "หรือ")
QUESTION_SUFFIXES_SHORT = ("ไหม", "มั้ย", "บ้าง")


def strip_question_suffix(q: str) -> str:
    for s in QUESTION_SUFFIXES:
        if q.endswith(s):
            rest = q[: -len(s)].rstrip()
            return rest if len(rest) >= 2 else q
    for s in QUESTION_SUFFIXES_SHORT:
        if q.endswith(s):
            if s == "ไหม" and q.endswith("ผ้าไหม"):
                continue  # ผ้าไหม = ผ้าเนื้อไหม ไม่ใช่คำถาม
            rest = q[: -len(s)].strip()
            if rest:
                return rest
    return q.strip()


def _starts_with_keyword(t: str) -> bool:
    return any(t.startswith(kw) for kw, _c in CATEGORY_KEYWORDS if len(kw) >= 2)


# คำประสมที่หน้าตาเหมือนคำค้นสั้นแต่คนละชนิดของ: ค้น "ที่นอน" ต้องไม่เด้ง
# "ผ้าปูที่นอน" (ผ้าปู ≠ ฟูก) — key = คำสั้นที่ user พิมพ์, value = คำประสมที่
# ถ้าเจอในชื่อให้ถือว่าไม่ตรง (user ยังค้น "ผ้าปูที่นอน" ได้ปกติ — key ไม่ตรงกับคำนั้น)
FALSE_FRIEND_COMPOUNDS = {
    "ที่นอน": ("ผ้าปูที่นอน",),
}


# คำสามัญ/คุณสมบัติ ที่เป็นคำกลางๆ ติดมากับของหลายชนิด — อย่าบังคับให้ชื่อสินค้ามี:
# - คำบ่งชี้เครื่องที่ normalize แปลงเป็นไทยแล้ว (iphone→ไอโฟน) — "สายชาร์จ iphone"
#   ต้องตอบสาย Universal ที่รองรับ iPhone ได้
# - "น้ำ" ใน "แก้วน้ำ" — แก้วกาแฟ/แก้วเยติก็เป็นแก้วน้ำ ใช้ได้ (น้ำ = 3 ตัวอักษร น+้+ำ)
REST_SKIP_WORDS = frozenset({"ไอโฟน", "แอนดรอยด์", "ซัมซุง", "บลูทูธ",
                             "ไร้สาย", "รุ่น", "ใหม่", "ชุด", "น้ำ",
                             "ไฟฟ้า", "อัตโนมัติ", "อัจฉริยะ", "ดิจิตอล", "ดิจิทัล",
                             "โทรศัพท์", "มือถือ"})


def _is_false_friend(name: str, phrase: str) -> bool:
    """กันคำค้นสั้นไปโดนคำประสมชนิดอื่น (ผ้าปูที่นอน ≠ ที่นอน)"""
    return any(word in name for word in FALSE_FRIEND_COMPOUNDS.get(phrase, ()))


def strip_filler_prefix(q: str) -> str:
    # ตัดเฉพาะเมื่อส่วนที่เหลือเป็นคำค้นจริง (ขึ้นต้นด้วย keyword ที่รู้จัก) —
    # กัน "มีด" โดนตัด "มี" เหลือ "ด" / "ของเล่นแมว" โดนตัด "ขอ" เหลือ
    # "งเล่นแมว" (ขอ เป็นแค่ส่วนของคำว่า "ของ")
    for f in FILLER_PREFIXES:
        if q.startswith(f):
            rest = q[len(f):].strip()
            if len(rest) >= 2 and _starts_with_keyword(rest):
                return rest
    return q


# (THAI_VARIANT_MAP + normalize_query ย้ายไปที่ app/services/category.py — ใช้ร่วมกันทั้งคำค้นและจัดหมวด)


def strip_price_phrase(q: str) -> str:
    """ตัดเงื่อนไขราคาออกจากคำค้น: 'หูฟังไม่เกิน 300' → 'หูฟัง', 'กระติก 200-400' → 'กระติก'"""
    t = q
    for pat in PRICE_PHRASE_RES:
        t = re.sub(pat, "", t)
    return t.strip(" -–,")


SPEC_UNITS_PAT = (r"(?:นิ้ว|เซนติเมตร|เซน|ซม\.?|มิลลิเมตร|มิล|มม\.?|เมตร|ฟุต|ลิตร|ล\."
                  r"|มิลลิลิตร|มล\.?|กิโลกรัม|กิโล|กรัม|ชิ้น|ใบ|คู่|แพ็ค|ขวด|แผ่น|ม้วน"
                  r"|[lL]|ml|cm|mm|kg|g)")


def strip_spec_phrase(q: str) -> str:
    """ตัดสเปคขนาด/ปริมาตร/จำนวนออกจากคำค้น:
    'พัดลมขนาด 16 นิ้ว' → 'พัดลม', 'กระติก 2 ลิตร' → 'กระติก'
    สเปคไม่ควรบังคับให้ชื่อสินค้าต้องมีคำว่า 'ขนาด 16 นิ้ว' (แล้วพลาดทั้งหมวด)
    (ตัวเลขขนาดถูกแยกไปกรองใน parse_size_spec แยกต่างหาก — ไม่หายไปไหน)"""
    num = r"\d+(?:\.\d+)?"
    t = q
    # "ขนาด <เลข> [หน่วย]?" — ขนาด 16 / ขนาด 16 นิ้ว / ขนาด 2 ลิตร
    t = re.sub(r"ขนาด\s*" + num + r"\s*" + SPEC_UNITS_PAT + r"?", " ", t)
    # "<เลข> <หน่วย>" — 16 นิ้ว / 2 ลิตร / 500 กรัม / 3 คู่
    t = re.sub(num + r"\s*" + SPEC_UNITS_PAT, " ", t)
    # "ขนาดใหญ่/เล็ก/กลาง" — คำคุณศัพท์ขนาด
    t = re.sub(r"ขนาด\s*(?:ใหญ่|เล็ก|กลาง|เล็กน้อย|ย่อม)", " ", t)
    return re.sub(r"\s+", " ", t).strip(" -–,")


# หน่วยขนาด → regex ที่พบในชื่อสินค้า (ทั้งแบบไทย/อังกฤษ/ย่อ)
SIZE_UNIT_PATTERNS = {
    "ลิตร": r"(?:ลิตร|ล\.|litre|liter|[lL](?![a-zA-Z]))",
    "นิ้ว": r'(?:นิ้ว|นิ้|inch|in(?![a-zA-Z])|")',
    "ฟุต": r"(?:ฟุต|ft(?![a-zA-Z])|feet)",
    "กิโลกรัม": r"(?:กิโลกรัม|กิโล|กก\.?|kg|kilo)",
    "กรัม": r"(?:กรัม|g(?![a-zA-Z])|gram)",
    "คู่": r"คู่",
}


def parse_size_spec(query: str) -> Optional[Tuple[str, str]]:
    """ดึงขนาดที่ถาม: 'หม้อหุงข้าว ขนาด 1 ลิตร' → ('1','ลิตร'), 'พัดลม 16 นิ้ว' → ('16','นิ้ว')
    คืน None ถ้าไม่มีตัวเลข+หน่วย (ราคา/เงื่อนไขอื่นไม่นับ)"""
    t = (query or "").lower()
    num = r"(\d+(?:\.\d+)?)"
    for unit, pat in SIZE_UNIT_PATTERNS.items():
        m = re.search(num + r"\s*" + pat, t)
        if m:
            return m.group(1), unit
    return None


def _name_matches_size(name: str, value: str, unit: str) -> bool:
    """ชื่อสินค้าตรงขนาดที่ถามไหม: ('1','ลิตร') ตรง '1ลิตร'/'1 ล.'/'1L'/'1.0L'
    แต่ไม่ตรง '1.4L' (ขนาดต่างกัน)"""
    pat = SIZE_UNIT_PATTERNS.get(unit)
    if not pat:
        return False
    n = (name or "").lower()
    v = re.escape(value) + r"(?:\.0)?"
    return bool(re.search(v + r"\s*" + pat, n))


MIN_SALES_FLOOR = int(os.getenv("MIN_SALES_FLOOR", "500") or 500)


def _nfc(s: str) -> str:
    """รวมอักษรไทยเป็นรูปแบบเดียว: 'น้ําแข็ง' → 'น้ำแข็ง'
    สระอำมี 3 รูปแบบในคลัง: U+0E33 เดี่ยว / U+0E4D+U+0E33 / U+0E4D+U+0E32
    (นิคหิต+สระอา) — การรวมเป็นแบบ compat NFC ไม่รวมให้ ต้องแทนที่ด้วยมือ
    กันคลังที่พิมพ์ต่างกันค้นไม่เจอ/จัดอันดับผิด"""
    try:
        import unicodedata
        s = unicodedata.normalize("NFC", s)
    except Exception:
        pass
    return (s.replace("\u0e4d\u0e32", "\u0e33")   # นิคหิต+สระอา → สระอำ
             .replace("\u0e4d\u0e33", "\u0e33"))  # กันรูปแบบซ้ำ (เผื่อ)


def _name_similarity(query: str, name: str) -> float:
    """คะแนนความใกล้ชื่อ (0-1) — ใช้จัดอันดับ "ของใกล้เคียง" ตอนค้นไม่เจอ
    (แทน sort ด้วย ai_score ซึ่งเคยแนะนำนาฬิกา/รองเท้าตอนลูกค้าถามถุงเท้า)
    1.0 = substring ตรง; นอกนั้นวัดจากคำสำคัญ (CATEGORY_KEYWORDS) ที่ซ้อนกัน
    ถ้า query ไม่มี keyword ที่รู้จัก → fallback เป็น bigram ตัวอักษรไทย"""
    q = _nfc((query or "").strip().lower())
    n = _nfc((name or "").strip().lower())
    if not q or not n:
        return 0.0
    if q in n or n in q:
        return 1.0
    # คำสำคัญใน query (คำยาวสุดก่อน กัน "หม้อ" นับก่อน "หม้อหุงข้าว") —
    # วัดว่าชื่อสินค้ามีคำสำคัญเหล่านั้นกี่ส่วน (สัดส่วนตามความยาวคำ)
    tokens, total_len, work = [], 0, q
    for kw, _c in sorted(CATEGORY_KEYWORDS, key=lambda x: -len(x[0])):
        if len(kw) < 2:
            continue
        while kw in work:
            work = work.replace(kw, " ", 1)
            tokens.append(kw)
            total_len += len(kw)
    if tokens:
        covered = sum(len(kw) for kw in tokens if kw in n)
        return covered / total_len
    # ไม่มี keyword รู้จัก — ใช้ bigram ตัวอักษร (ไทยไม่มีเว้นวรรค)
    def _bigrams(s: str):
        s = re.sub(r"[^\u0e00-\u0e7fa-z0-9]", "", s)
        if len(s) < 2:
            return {s} if s else set()
        return {s[i:i + 2] for i in range(len(s) - 1)}
    qb, nb = _bigrams(q), _bigrams(n)
    if not qb or not nb:
        return 0.0
    return len(qb & nb) / len(qb | nb)


def search_products(db: Session, query: str) -> list:
    """ค้นสินค้า: ตรงชื่อ/หมวด + เข้าใจเงื่อนไขราคา ('หูฟังไม่เกิน 300', 'งบ 500',
    'กระติก 200-400') — จัดอันดับความตรง แล้วตอบสูงสุด 5 ตัว
    นโยบายเด็ดขาด: ตอบเฉพาะสินค้าที่ตรวจลิงก์แล้วว่า OK เท่านั้น"""
    def fetch(floor: int) -> list:
        return (db.query(models.Product)
                  .filter(models.Product.link_status == "ok",
                          models.Product.sales_count >= floor)
                  .all())

    q = query.lower().strip()
    if not q:
        return []
    # คำพ้อง/การันต์ไทย (ชาร์ท=ชาร์จ, บลูธูธ=บลูทูธ, iphone=ไอโฟน, type-c=type c)
    q = strip_question_suffix(_strip_polite_suffix(_nfc(normalize_query(q))))
    if not q:
        # เหลือแต่คำลงท้ายสุภาพ ("ครับ"/"จ้า"/"ค่ะ") → ไม่มีคำค้นจริง อย่าแมตช์ทุกสินค้า
        # ("" in name = True เสมอ ไม่งั้นลูกค้าพิมพ์แค่ "ครับ" ได้สินค้าทั้งร้าน)
        return []
    min_price, max_price = parse_price_conditions(query)
    # ขนาดที่ลูกค้าถาม ("1 ลิตร"/"16 นิ้ว") — แยกไปกรองท้ายสุด ไม่ใช่ตัดทิ้ง
    size_spec = parse_size_spec(query)
    # คำหลักจริงๆ: ตัดคำนำหน้าเล่นๆ + เงื่อนไขราคา + สเปคขนาด → "อยากได้หูฟังไม่เกิน 300" = "หูฟัง"
    q_core = strip_spec_phrase(strip_price_phrase(strip_filler_prefix(q)))
    if not q_core:  # ทั้งคำค้นเป็นสเปคล้วน ("16 นิ้ว") — กันค่าว่างไปแมตช์ทุกตัว ("" in cat = True เสมอ)
        q_core = q

    def strong_tier(name: str, phrase: str) -> int:
        """ชั้นความน่าเชื่อถือของแมตช์:
        2 = คำหลักอยู่ต้นชื่อ (≤25% แรก) หรือซ้ำ ≥2 ครั้ง — เชื่อถือได้สุด
        1 = อยู่ช่วงต้นชื่อ (≤55%) — ใช้ได้
        0 = ยัดไว้ท้ายชื่อเพื่อ SEO → ไม่นับ (ตอบสุจริตดีกว่าเอาของมั่วขึ้นหน้า)"""
        pos = name.find(phrase)
        if pos < 0:
            return 0
        if name.count(phrase) >= 2 or pos <= len(name) * 0.25:
            return 2
        if pos <= len(name) * 0.55:
            return 1
        return 0

    def short_kw_tier(name: str, kw: str) -> int:
        """tier สำหรับคำไทยสั้น (เคส/หมา/จาน...): ต้องเจอที่ขอบคำ (ต้นชื่อ/หลังเว้นวรรค/
        หลังอักษรไม่ไทย) — กัน "พัดลมเคสพีซี" (เคสกลางคำ แต่ count≥2 ทำ substring_ok
        ผ่าน) หลุดเป็นเคสโทรศัพท์; 2 = ต้นชื่อหรือซ้ำ, 1 = ขอบคำอื่น"""
        m = re.search(r"(^|[^\u0E00-\u0E7F])" + re.escape(kw), name)
        if not m:
            return 0
        pos = m.end() - len(kw)
        if name.count(kw) >= 2 or pos <= len(name) * 0.25:
            return 2
        return 1

    def substring_ok(name: str, phrase: str) -> bool:
        """กันคำสั้นแมตช์ซับสตริงกลางคำยาว:
        - "หมา" ต้องไม่โดน "เหมาะ" (ตัวหน้าก่อนเป็นตัวไทย = กลางคำไทย)
        - "cap" ต้องไม่โดน "Cappuvini" (ตัวตามหลังเป็นตัวละติน = กลางคำอังกฤษ)
        - แต่ "จาน" ใน "ที่คว่ำจาน" ยังผ่านได้เพราะซ้ำ ≥2 ครั้ง
        """
        if len(phrase) >= 4:
            return True
        if name.count(phrase) >= 2:
            return True
        pos = name.find(phrase)
        if pos < 0:
            return False
        if pos > 0 and 0x0E00 <= ord(name[pos - 1]) <= 0x0E7F:
            return False  # ติดกับตัวอักษรไทย = กลางคำไทย
        after = name[pos + len(phrase):pos + len(phrase) + 1]
        if after and ('a' <= after <= 'z' or 'A' <= after <= 'Z'):
            return False  # ติดกับตัวอักษรละติน = กลางคำอังกฤษ (cap ≠ cappuvini)
        return True

    def match_weight(p) -> tuple:
        """คืน (คะแนน, tier) — tier = ชั้นความเชื่อถือ (0/1/2)
        ถ้ามีแมตช์ tier ≥1 อย่างน้อย 1 ตัว → แสดงเฉพาะชั้นนั้น (กันของยัดท้ายปน)"""
        name = _nfc((p.name or "").lower())
        cat = _nfc((p.category or "").lower())
        w = 0
        tier = 0
        # แมตช์ทั้งคำ/ทั้งประโยคในชื่อ — ไม่จับซับสตริงกลางคำ (กันคำสามัญอย่าง
        # "เครื่อง"/"ความเย็น" ไปโดนของคนละหมวด เช่น "เครื่องฟอกอากาศ" → เครื่องตัดหญ้า)
        if q in name or q_core in name:
            phrase = q_core if q_core else q
            if substring_ok(name, phrase) and not _is_false_friend(name, phrase):
                w += 3
                tier = max(tier, strong_tier(name, phrase))
        if q in cat or q_core in cat:
            w += 2
            tier = max(tier, 1)  # ตรงหมวดตรงๆ เชื่อถือได้
        # ระดับคำ (keyword ที่รู้จัก): ใช้เฉพาะ keyword ที่เฉพาะที่สุด — keyword ที่
        # เป็นซับสตริงของ keyword อื่นในคำค้นจะถูกตัด (กัน "หม้อหุงข้าว" ไปโดน
        # "หม้อทอด" / "โต๊ะสนาม" ไปโดน "พัดลมตั้งโต๊ะ") เช่น "หูฟัง bluetooth"
        # ใช้ทั้ง 2 (ไม่มีตัวไหนซ้อนกัน)
        # ถ้า q_core เป็น keyword เอง (หม้อหุงข้าว/โต๊ะสนาม/ที่นอนลม) → ใช้แค่
        # แมตช์เต็มคำ (full-phrase ข้างบน) ห้ามใช้คำย่อยมาแทน (หม้อ/โต๊ะ/ที่นอน)
        q_core_is_keyword = any(kw == q_core for kw, _c in CATEGORY_KEYWORDS)
        if not q_core_is_keyword:
            # เกณฑ์ 3 ตัวขึ้นไป (เดิม 4) — เปิดคำสั้นอย่าง "เคส" (3 ตัว) เป็นคำค้นหลัก
            # ได้: "เคส android" ต้องค้นเจอ ใช้ substring_ok กันขอบคำ (กลางคำไทย/อังกฤษ)
            q_kws = [kw for kw, _c in CATEGORY_KEYWORDS
                     if len(kw) >= 3 and kw in q_core and kw != q_core]
            q_kws = [kw for kw in q_kws
                     if not any(kw in other for other in q_kws if other != kw)]
            # ต้องมีทุกคำย่อยในชื่อ (AND) — กัน "กระติกน้ำแข็ง" ไปโดนกางเกง
            # "ผ้าไหมน้ำแข็ง" (มีแค่คำว่า น้ำแข็ง คำเดียว)
            if q_kws and all(substring_ok(name, kw) for kw in q_kws):
                kt = []
                for kw in q_kws:
                    if len(kw) < 4 and any('\u0E00' <= c <= '\u0E7F' for c in kw):
                        kt.append(short_kw_tier(name, kw))  # คำไทยสั้น: ขอบคำเท่านั้น
                    else:
                        kt.append(strong_tier(name, kw))
                if all(t > 0 for t in kt):
                    w += len(q_kws)
                    tier = max(tier, max(kt))
        # คำผสม: ถ้าคำค้นแยกเป็นหลายคำย่อยที่รู้จัก (≥2) → ต้องมีครบทุกคำในชื่อ
        # (บังคับ ไม่ใช่โบนัส) — กัน "ของเล่นแมว" ไปโดนของเล่นคลายเครียดที่ไม่มีแมว /
        # "กระติกน้ำแข็ง" ไปโดนกางเกงผ้าไหมน้ำแข็ง / "แก้วสแตนเลส" ต้องเป็นแก้วสแตนเลสจริง
        all_kws = [kw for kw, _c in CATEGORY_KEYWORDS
                   if len(kw) >= 2 and kw in q_core]
        uniq_kws = [kw for kw in all_kws
                    if not any(kw in other for other in all_kws if other != kw)]
        if len(uniq_kws) >= 2:
            if not all(kw in name for kw in uniq_kws):
                return 0, 0
            w += 2
            tier = max(tier, 1)
        # คำที่เหลือในคำค้นซึ่งไม่ใช่ keyword ที่รู้จัก (เช่น "ยางพารา" ใน
        # "ที่นอนยางพารา", "ข้าง" ใน "หมอนข้าง", "ต้ม" ใน "หม้อต้ม") —
        # ถ้าเป็นคำไทยยาวพอ (≥3 ตัว) และไม่ใช่คำบ่งชี้เครื่อง (ไอโฟน/แอนดรอยด์
        # ที่ normalize แปลงมา) ต้องมีในชื่อด้วย — กัน "ที่นอนยางพารา" ไปโดน
        # "ที่นอนลม"/"ผ้าปูที่นอน", "หมอนข้าง" ไปโดน "หมอนเด็ก" ที่มีแค่คำหลัก
        # (ไม่บังคับคำสั้นอย่าง "น้ำ" ใน "แก้วน้ำ" — แก้วกาแฟก็ตอบได้)
        if not q_core_is_keyword:
            rest = q_core
            # เรียงคำยาวก่อน — กัน "หม้อ" แทนที่ก่อน "หม้อหุงข้าว" เหลือ "หุงข้าว" ค้าง
            for kw, _c in sorted(CATEGORY_KEYWORDS, key=lambda x: -len(x[0])):
                if len(kw) >= 2 and kw in q_core:
                    rest = rest.replace(kw, " ")
            rest_words = [w for w in re.split(r"[^\u0E00-\u0E7F]+", rest)
                          if len(w) >= 3 and w not in REST_SKIP_WORDS]
            if rest_words and not all(w in name for w in rest_words):
                return 0, 0
        return w, tier

    def in_budget(p) -> bool:
        price = float(p.price or 0)
        return (min_price is None or price >= min_price) and (max_price is None or price <= max_price)

    # --- กรองตามประเภทเครื่องที่ผู้ใช้ระบุ (กัน "สายชาร์จ android" ได้สาย Lightning/Apple) ---
    ANDROID_MARKERS = ("android", "แอนดรอยด์", "ซัมซุง", "samsung", "oppo",
                       "huawei", "xiaomi", "type c", "type-c", "usb")
    APPLE_MARKERS = ("apple", "iphone", "ไอโฟน", "ios", "lightning")
    APPLE_ONLY = ("lightning", "type c to l", "type-c to l", "apple", "iphone", "ไอโฟน")
    req_android = any(m in q for m in ANDROID_MARKERS)
    req_apple = any(m in q for m in APPLE_MARKERS)

    def blocked(p) -> bool:
        """สินค้าที่คนไม่ได้ถาม: ฝาครอบ/เคส ไม่ใช่ "สายชาร์จ" ที่ต้องการ
        (คลุมทั้ง "สายชาร์จ", "สายชาร์จ apple", "สายชาร์จ android") """
        name = (p.name or "").lower()
        if "สายชาร์จ" in q_core and ("ฝาครอบ" in name or "เคส" in name):
            return True
        return False

    def finalize(hits) -> list:
        """กรอง (เครื่อง/งบ/ความเชื่อถือ) → จัดอันดับ → คืน top-3
        ว่าง = ไม่มีของที่น่าเชื่อถือ → ตอบสุจริต (ไม่เอาของมั่วขึ้นหน้า)"""
        if not hits:
            return []
        if req_android and not req_apple:
            # ไล่ชื่อที่ระบุแค่ Apple ล้วน (ไม่มีเครื่องหมาย Android เลย) — ส่วนของที่
            # ระบุทั้ง iPhone+Samsung (multi-compat) ยังตอบได้ (เคสส่วนใหญ่รองรับทั้ง 2)
            def _apple_only(name: str) -> bool:
                has_apple = any(m in name for m in APPLE_ONLY)
                if not has_apple:
                    return False
                return not any(m in name for m in ANDROID_MARKERS)
            hits = [h for h in hits
                    if not _apple_only(_nfc((h[0].name or "").lower()))]
            if not hits:
                return []  # ไม่มีที่เข้ากับ android จริง → สุจริต ไม่เอาของมั่วมาแทน
        strong_hits = [h for h in hits if h[2] >= 1]
        if not strong_hits:
            return []  # แมตช์ท้ายชื่อ (ยัด SEO) เท่านั้น → ไม่เอาขึ้นหน้า (สุจริต)
        hits = strong_hits
        if min_price is not None or max_price is not None:
            budget_hits = [h for h in hits if in_budget(h[0])]
            if not budget_hits:
                return []  # มีชื่อตรงแต่ไม่มีตัวในงบ → ไม่เอาของมั่วมาแทน (สุจริต)
            hits = budget_hits
        if size_spec:
            # กรองขนาด: "หม้อหุงข้าว 1 ลิตร" ต้องโชว์เฉพาะ 1 ลิตร ไม่ใช่ 1.4/1.8/2.2 ปน
            size_hits = [h for h in hits if _name_matches_size(h[0].name or "", size_spec[0], size_spec[1])]
            if size_hits:
                hits = size_hits
            else:
                return []  # มีสินค้าตรงชื่อแต่ไม่มีขนาดที่ถาม → สุจริต ไม่เอาขนาดอื่นมั่วมาแทน
        hits.sort(key=lambda pw: (pw[2], pw[1], pw[0].ai_score or 0), reverse=True)
        return [p for p, _, _ in hits[:5]]

    hits = []
    for p in fetch(MIN_SALES):
        if blocked(p):
            continue
        w, tier = match_weight(p)
        if w > 0:
            hits.append((p, w, tier))
    result = finalize(hits)
    if not result:
        # เกณฑ์ยืดหยุ่น: คำค้นที่ตรงหมวด (มี keyword ในคำ) แต่ไม่มีตัวขายถึงเกณฑ์
        # (เช่น "ของเล่นแมว" มีตัวเดียว ขาย 1,000) → ลองคลังขาย ≥ MIN_SALES_FLOOR
        q_has_kw = any(kw in q_core for kw, _c in CATEGORY_KEYWORDS if len(kw) >= 2)
        if q_has_kw and len(q_core) >= 4:
            hits2 = []
            for p in fetch(MIN_SALES_FLOOR):
                if blocked(p):
                    continue
                w, tier = match_weight(p)
                if w > 0:
                    hits2.append((p, w, tier))
            result = finalize(hits2)
    return result


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


# --- ฝากคำถาม 2 ขั้น: แตะปุ่ม → บอทถามคำถามจริง → ลูกค้าพิมพ์ → ป้าเข็มตอบเอง ---
# เก็บ state ในหน่วยความจำ (uvicorn 1 process พอเพียง): uid → เวลาที่แตะปุ่ม
_pending_question: dict = {}
PENDING_QUESTION_TTL_MIN = 30          # รอคำถามได้ 30 นาที แล้วคืนโหมดปกติ
ASK_QUESTION_PROMPT = (
    "🖊️ ป้าเข็มรับฟังเองจ๊ะ — พิมพ์คำถามของคุณได้เลยค่ะ\n"
    "ถามสินค้า / ความรู้ทั่วไป / เรื่องร้าน ป้าเข็มตอบให้เองทุกคำถาม\n\n"
    "ถ้าเปลี่ยนใจ พิมพ์ \"ยกเลิก\" ได้เลย 😊"
)
CANCEL_CONFIRM = "รับทราบจ๊ะ กลับมาเมนูปกติได้เลยค่ะ 😊"
# ป้าเข็มตอบเรื่องร้าน/สั่งซื้อเอง (นายหน้า ไม่มีข้อมูลสั่งซื้อ/พัสดุของลูกค้า)
STORE_QUESTION_SELF_SERVICE = (
    "🤗 เรื่องร้าน/สั่งซื้อป้าเข็มช่วยตอบได้จ๊ะ:\n\n"
    "• ราคา = เท่ากับในแอป Shopee เป๊ะ ป้าเป็นนายหน้า ไม่บวกเพิ่ม\n"
    "• สั่งซื้อ/จ่ายเงิน/คืนเงิน → ทำในแอป Shopee เองได้เลยค่ะ\n"
    "• ติดตามพัสดุ/เลขสั่งซื้อ → เปิดแอป Shopee → ฉัน → การสั่งซื้อของฉัน\n\n"
    "ถ้าอยากให้ป้าช่วยหาสินค้า พิมพ์ชื่อของมาได้เลยนะคะ 😊"
)
# คำถามที่ป้าตอบให้ตรง ๆ ไม่ได้ (คลุมเครือ/หาข้อมูลไม่เจอ) — ไม่ปลุกเจ้าของ
QUESTION_ANSWER_FALLBACK = (
    "🤗 ป้าเข็มรับคำถามไว้แล้วจ๊ะ แต่เรื่องนี้ป้าตอบให้ตรง ๆ ไม่ได้ตอนนี้ — "
    "ลองพิมพ์ชื่อสินค้าให้ป้าหาให้ก่อน หรือถามความรู้ทั่วไปดูอีกรอบนะคะ 😊"
)
# คำเฉพาะร้าน — ถ้าฝากคำถามมีคำพวกนี้ = เรื่องร้าน/สั่งซื้อ (พัสดุ/ราคา/ชำระเงิน)
# ป้าเข็มตอบวิธีจัดการเอง (นายหน้า ไม่มีข้อมูลสั่งซื้อจริง ไม่ควรตอบแทนเจ้าของ)
STORE_QUESTION_MARKERS = (
    "พัสดุ", "ส่งของ", "จะส่ง", "จัดส่ง", "ของถึง", "ได้ของ", "สต็อก", "มีของไหม",
    "มีสินค้าไหม", "ราคาเท่าไหร่", "กี่บาท", "รับประกัน", "คืนเงิน", "ชำระเงิน",
    "โอนเงิน", "จ่ายยังไง", "สั่งซื้อ", "สั่งแล้ว", "โค้ด", "ส่วนลด", "โปรโมชัน",
    "ซื้ออย่างไร", "ซื้อสินค้าอย่างไร", "ซื้อของอย่างไร", "วิธีซื้อ", "วิธีสั่ง",
    "ส่งฟรี", "ค่าส่ง",
)
# ถ้ากำลังรอคำถามอยู่แล้วลูกค้าแตะปุ่มเมนูอื่น/พิมพ์ยกเลิก → ถือว่าเปลี่ยนใจ ไม่ push
PENDING_CANCEL_IF = (
    "ค้นสินค้า", "หมวดสินค้า", "วันนี้ขายอะไรดี", "อันดับขายดี",
    "ทำไมต้องซื้อกับป้าเข็ม", "มีอะไรใหม่", "ยกเลิก", "ไม่เป็นไร", "ไม่แล้ว",
    "ช่างเถอะ", "ลืมไปเถอะ",
)


def is_bot_manual_request(text: str) -> bool:
    """ลูกค้าถามเรื่องบอท/อยากรู้วิธีใช้? (คุยกับป้าเข็ม / คู่มือ / ใช้ยังไง...) — ตอบจากคู่มือเท่านั้น"""
    t = _mask_keyboard((text or "").strip().lower().replace(" ", ""))
    return any(p in t for p in BOT_MANUAL_PHRASES)


def is_contact_request(text: str) -> bool:
    """ลูกค้าขอคุย/ฝากคำถาม? → บอทถามคำถามจริงแล้วตอบเอง (ไม่ส่งเจ้าของ)"""
    t = (text or "").strip().lower().replace(" ", "")
    return any(p in t for p in CONTACT_PHRASES)


# --- EQ: จับอารมณ์ลูกค้า แล้วตอบด้วยความเข้าใจก่อนช่วย (แม่ค้าใจดี ไม่ใช่หุ่นยนต์) ---
EMOTION_RULES = (
    (("โกรธ", "ไม่พอใจ", "โมโห", "หงุดหงิด", "รำคาญ", "เซ็ง", "หัวเสีย", "ห่วย",
      "แย่มาก", "แย่ที่สุด", "ช้ามาก", "ช้าจัง"),
     "โกรธ/ไม่พอใจ",
     "😔 ป้าเข็มเข้าใจค่ะ รอแล้วไม่ได้ของหรือบริการไม่ตรงใจ มันน่าหงุดหงิดจริงๆ — ป้าเข็มขอโทษแทนด้วยนะคะ\n"
     "ป้าเข็มช่วยได้นะคะ พิมพ์ \"สั่งแล้ว\" ให้ป้าเข็มบอกวิธีเช็คพัสดุ หรือเล่าปัญหามา ป้าเข็มหาทางช่วยให้จ๊ะ 💛"),
    (("เสียใจ", "เศร้า", "ร้องไห้", "อกหัก", "ท้อ", "หมดหวัง", "ไม่ไหว", "เหนื่อย",
      "เครียด", "กังวล", "กลัว", "กลุ้ม", "น้อยใจ", "เหงา", "แย่จัง"),
     "เสียใจ/กังวล",
     "💛 ป้าเข็มอยู่ตรงนี้นะคะ ไม่เป็นไร ค่อยๆ บอกมา — ป้าเข็มรับฟังเสมอ\n"
     "ถ้าอยากให้ใจฟูขึ้น ป้าเข็มหาของดีๆ ราคาคุ้มให้ได้นะคะ พิมพ์ชื่อสินค้า หรือ \"วันนี้ขายอะไรดี\" ก็ได้จ๊ะ"),
    (("ดีใจ", "ตื่นเต้น", "ชอบมาก", "สุดยอด", "เยี่ยม", "ประทับใจ", "ถูกใจ", "ฟิน",
      "เลิศ", "ยอดเยี่ยม"),
     "ดีใจ/พอใจ",
     "🥰 ดีใจด้วยนะคะ! ป้าเข็มยินดีที่ทำให้คุณพอใจได้ — มีอะไรให้ช่วยอีกไหมคะ พิมพ์ชื่อสินค้า "
     "หรือแตะเมนูด้านล่างได้เลยจ๊ะ 💕"),
)


def detect_emotion(text: str):
    """จับอารมณ์จากคำ → (ประเภท, คำตอบเห็นใจ) หรือ None ถ้าไม่ใช่อารมณ์"""
    t = (text or "").strip().lower().replace(" ", "")
    for kws, etype, reply in EMOTION_RULES:
        if any(k in t for k in kws):
            return etype, reply
    return None


# คำตอบเห็นใจเวอร์ชันวัยรุ่น/ผู้สูงอายุ (โทน neutral = ใช้ข้อความเดิมใน EMOTION_RULES)
EMOTION_REPLIES_YOUTH = {
    "โกรธ/ไม่พอใจ": (
        """😤 เข้าใจๆ ของมันต้องน่าหงุดหงิด! ขอโทษแทนด้วยนะ

บอกมาได้เลย มีปัญหาอะไร ป้าเข็มช่วยจัดการให้
พิมพ์ "สั่งแล้ว" ให้เช็คพัสดุ หรือเล่ามาเต็มๆ ก็ได้ 💪"""
    ),
    "เสียใจ/กังวล": (
        """💛 อยู่ตรงนี้แล้วนะ ไม่เป็นไร เล่ามาได้เลย

อยากได้อะไรให้ใจชื้นๆ บอกป้าเข็มได้
หาให้ชัวร์ รับรองฟินขึ้นแน่นอน ✨"""
    ),
    "ดีใจ/พอใจ": (
        """🎉 เย้ ถูกใจสุดๆ! ยินดีด้วยเลย

มีอะไรให้ช่วยอีกป่ะ พิมพ์มาได้เลย
เดี๋ยวจัดของดีๆ ให้อีก 555 ✨"""
    ),
}

EMOTION_REPLIES_ELDER = {
    "โกรธ/ไม่พอใจ": (
        """😔 เข้าใจนะคะ ไม่เป็นไรค่ะ
ป้าเข็มขอโทษด้วยนะคะ

บอกป้าเข็มได้ค่ะ ว่ามีปัญหาอะไร
หรือพิมพ์ "สั่งแล้ว" ป้าเข็มจะบอกวิธีเช็คพัสดุให้นะคะ"""
    ),
    "เสียใจ/กังวล": (
        """💛 ป้าเข็มอยู่ตรงนี้นะคะ
ไม่ต้องกังวลค่ะ ค่อยๆ พูดมาได้เลย

ถ้าอยากได้อะไรให้สบายใจ บอกป้าเข็มได้
ป้าเข็มจะดูแลให้เองค่ะ"""
    ),
    "ดีใจ/พอใจ": (
        """🥰 ดีใจด้วยนะคะ
ป้าเข็มยินดีมากค่ะ

อยากได้อะไรเพิ่ม บอกป้าเข็มได้เลยนะคะ"""
    ),
}


def emotion_reply(etype: str, tone: str = "neutral") -> str:
    """คำตอบเห็นใจตามโทนวัย — youth/elder มีชุดเฉพาะ, neutral → ข้อความเดิม"""
    if tone == "youth":
        return EMOTION_REPLIES_YOUTH.get(etype, "")
    if tone == "elder":
        return EMOTION_REPLIES_ELDER.get(etype, "")
    return ""


# --- ค้นข้อมูลเน็ต/ความรู้ทั่วไป (Tavily) ---
WEB_SEARCH_PREFIXES = ("ค้นเน็ต", "ถามเน็ต", "หาข้อมูล", "ค้นเว็บ", "หาในเน็ต", "เสิร์ช", "search")
QUESTION_FALLBACK_MARKERS = (
    # เดิม: คำถามความรู้
    "วิธี", "ยังไง", "ยังงัย", "คืออะไร", "ทำไม", "เมื่อไหร่", "เมื่อไร", "แปลว่า", "รู้ไหม",
    # ขยาย (สากล/ยอดนิยม — บอทค้นเน็ตให้อัตโนมัติ ไม่ต้องพิมพ์ "ค้นเน็ต" นำหน้า)
    "อะไร", "เท่าไหร่", "กี่บาท", "ที่ไหน", "ใคร", "อย่างไร", "หมายความ",
    "ความหมาย", "ขั้นตอน", "ยอดนิยม", "วันนี้",
)


def is_web_search_request(text: str) -> bool:
    """ลูกค้าสั่งค้นเน็ตตรงๆ ('ค้นเน็ต ...' / 'ถามเน็ต ...') → ค้นข้อมูลทั่วไป"""
    t = (text or "").strip().lower()
    return any(t.startswith(p) for p in WEB_SEARCH_PREFIXES)


def looks_like_question(text: str) -> bool:
    """ค้นสินค้าไม่เจอ + หน้าตาเป็นคำถามความรู้ (วิธี/ยังไง/ทำไม...) → น่าจะอยากรู้ข้อมูลทั่วไป"""
    t = (text or "").strip().lower().replace(" ", "")
    return any(m in t for m in QUESTION_FALLBACK_MARKERS)


def _web_search_text(raw: str) -> str:
    """ตัดคำนำหน้า 'ค้นเน็ต' ออก เหลือคำถามจริง"""
    t = (raw or "").strip()
    for p in WEB_SEARCH_PREFIXES:
        if t.lower().startswith(p):
            t = t[len(p):].lstrip(" :：")
            break
    return t.strip()


@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
    user_text = event.message.text.strip()
    # Accept both "วันนี้ขายอะไรดี" and "วันนี้ขายอะไรดี?" — the Thai keyboard doesn't add
    # the ?, and a bare trailing "?" from autocorrect shouldn't break the match either.
    normalized_text = user_text.rstrip("?？ ").strip()
    # ข้อความที่โชว์คืนลูกค้า — ตัดคำถามต่อท้าย ("มีไหม"/"ได้ไหม") ออก จะได้ไม่ quote คำถามเต็มๆ
    display_term = strip_question_suffix(normalized_text)
    line_user_id = event.source.user_id
    is_owner = line_user_id == ADMIN_LINE_USER_ID
    intent = 'unknown'
    interest_cat = None
    
    db = SessionLocal()
    try:
        user = get_or_create_line_user(db, line_user_id)
        tone = get_tone(db, line_user_id, normalized_text)
        emphasis = market_emphasis(db)  # Hermes hot-reload: ท่าทีตลาด ("" ถ้ายังไม่ learn)
        # --- ฝากคำถาม 2 ขั้น: ลูกค้าเพิ่งแตะ "ฝากคำถาม" → ข้อความถัดไป = คำถามจริง ---
        # (วางก่อน branch อื่น — ให้ทุกข้อความถัดไปถูกจับเป็นคำถาม ยกเว้นลบข้อมูล/ยกเลิก)
        pending_ts = _pending_question.get(line_user_id)
        if pending_ts:
            if (datetime.datetime.utcnow() - pending_ts).total_seconds() > PENDING_QUESTION_TTL_MIN * 60:
                _pending_question.pop(line_user_id, None)  # หมดเวลา → คืนโหมดปกติ
                pending_ts = None
        if pending_ts and not is_owner and normalized_text not in DELETE_PHRASES \
                and not any(p in normalized_text for p in PENDING_CANCEL_IF) and not is_contact_request(normalized_text):
            _pending_question.pop(line_user_id, None)
            # ป้าเข็มตอบเองทั้งหมด (NUANOSE: AI = พนักงาน) — mirror routing ข้อความตรงๆ:
            # ค้นสินค้า → พัสดุ → ของใหม่ → คู่มือ/FAQ → เรื่องร้าน → เทียบ → อารมณ์ →
            # ค้นเน็ต → ความรู้ทั่วไป → ถ่อมตัว ไม่ push เจ้าของ
            hits = search_products(db, normalized_text)
            if hits:
                reply = format_product_message(db, user, hits,
                                               title=f"🔍 ป้าเข็มหาให้แล้ว — สินค้าตรงกับ \"{display_term}\" ค่ะ",
                                               is_owner=is_owner)
                intent = 'search'
                interest_cat = guess_category(normalized_text)
            elif is_wismo(normalized_text):
                # พัสดุ/เลขพัสดุ/ของถึงยัง → สอนเช็คเองในแอป Shopee (ป้าเป็นนายหน้า ไม่มีเลขพัสดุ)
                reply = [TextSendMessage(text=WISMO_REPLY), WISMO_BUTTON]
                intent = 'wismo'
            elif strip_question_suffix(normalized_text) in NEW_PHRASES:
                # "มีอะไรใหม่"/"มีของใหม่ไหม" → ดันของใหม่หมวดที่เคยสนใจ (เหมือนพิมพ์ตรงๆ)
                reply = handle_new_arrivals(db, user, line_user_id, is_owner)
                intent = 'new'
            elif is_bot_manual_request(normalized_text):
                # คำถามคู่มือ (ติดตั้ง/คืนเงิน/ค่าคอม/โค้ด...) → ตอบจากคู่มือเฉพาะส่วน
                # ไม่ปล่อยไป web search (เคยตอบขยะยาวนอกเรื่องตอนถามผ่านเมนูฝากคำถาม)
                reply = TextSendMessage(text=bot_manual_reply(normalized_text, is_owner))
                intent = 'manual'
                if _wants_code_buttons(normalized_text):
                    reply = [reply, _github_button_card()]
            elif any(m in normalized_text for m in STORE_QUESTION_MARKERS):
                # เรื่องร้าน/สั่งซื้อ/ราคา/ชำระเงิน (ที่ไม่ใช่คำถามคู่มือตรงๆ) → ตอบวิธีจัดการเอง
                reply = TextSendMessage(text=STORE_QUESTION_SELF_SERVICE)
                intent = 'manual'
                interest_cat = guess_category(user_text)
            elif normalized_text.startswith(COMPARE_PREFIXES):
                # เทียบสินค้า A กับ B → ตารางข้อเท็จจริง (เหมือนพิมพ์ตรงๆ)
                reply = handle_compare(db, normalized_text, user, is_owner)
                intent = 'compare'
            elif detect_emotion(normalized_text):
                # ระบายอารมณ์ → เห็นใจก่อนตามโทนวัย (เหมือนพิมพ์ตรงๆ)
                _etype, emo_reply = detect_emotion(normalized_text)
                tone_reply = emotion_reply(_etype, tone)
                if tone_reply:
                    emo_reply = tone_reply
                reply = TextSendMessage(text=emo_reply, quick_reply=quick_reply_items())
                intent = 'emotion'
            elif is_web_search_request(normalized_text):
                # สั่งค้นเน็ตตรงๆ ("ค้นเน็ต ...") → หาข้อมูลทั่วไป
                reply = _web_answer_messages(_web_search_text(normalized_text))
                intent = 'web'
            elif looks_like_question(normalized_text):
                wanswer = web_search_answer(normalized_text)
                if wanswer["text"].startswith("🔍 ป้าเข็มหาข้อมูลมาให้แล้วจ๊ะ:"):
                    reply = _web_answer_messages(normalized_text, answer=wanswer)
                    intent = 'web'
                else:
                    # web search ไม่สำเร็จ → ถ่อมตัว + แนะนำค้นสินค้า (ไม่ปลุกเจ้าของ)
                    reply = TextSendMessage(text=QUESTION_ANSWER_FALLBACK)
                    intent = 'human'
            else:
                # คำถามไม่ชัด/ตอบไม่ได้ → ถ่อมตัว + แนะนำพิมพ์ชื่อสินค้า (ไม่ปลุกเจ้าของ)
                reply = TextSendMessage(text=QUESTION_ANSWER_FALLBACK)
                intent = 'human'
                interest_cat = guess_category(user_text)
        elif pending_ts and normalized_text in PENDING_CANCEL_IF:
            _pending_question.pop(line_user_id, None)
            reply = TextSendMessage(text=CANCEL_CONFIRM)
            intent = 'human'
        elif normalized_text in DELETE_PHRASES:
            # PDPA: สิทธิ์ลบข้อมูล (erasure) — ลบชื่อ + ประวัติการสนทนา + สิ่งที่ให้จำไว้ทันที
            # (ชีท Google ด้วย — Apps Script ลบทุกแถวของผู้ใช้นี้ออก)
            db.query(models.ChatLog).filter(models.ChatLog.line_user_id == line_user_id).delete(synchronize_session=False)
            db.query(models.UserPreference).filter(models.UserPreference.line_user_id == line_user_id).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.line_user_id == line_user_id).delete(synchronize_session=False)
            db.commit()
            _push_sheet_async({"action": "delete_user", "line_user_id": line_user_id})
            reply = TextSendMessage(text=DELETE_REPLY)
            intent = 'delete'
        elif is_wismo(normalized_text):
            # ลูกค้าทวงถาม/ติดตามพัสดุ — แนะนำเส้นทางตรวจเองบน Shopee (24/7)
            # ลิงก์อยู่ในปุ่มการ์ด (ไม่ใช่ข้อความ) — กัน LINE ธง "ไม่ปลอดภัย"
            reply = [TextSendMessage(text=WISMO_REPLY), WISMO_BUTTON]
            intent = 'wismo'
        elif strip_question_suffix(normalized_text) in NEW_PHRASES:
            # มีอะไรใหม่/มีของใหม่ไหม — ดันสินค้าใหม่หมวดที่เคยสนใจ (จำจาก chat_logs + ที่บอกให้จำไว้)
            reply = handle_new_arrivals(db, user, line_user_id, is_owner)
            intent = 'new'
        elif normalized_text.startswith(REMEMBER_SAVE_PREFIXES) or normalized_text.startswith(REMEMBER_SHOW_PHRASES):
            # Account Memory (Amazon-style): ลูกค้าบอก "จำไว้ ชอบหูฟัง" / ถาม "ป้าเข็มจำได้ไหม"
            reply = handle_remember(db, normalized_text, line_user_id, user)
            intent = 'remember'
        elif is_owner and normalized_text.startswith("แคมเปญ"):
            # เอเจนต์ทำแคมเปญ (เฉพาะเจ้าของ) — dry-run ก่อนส่งจริง
            reply = handle_campaign(db, normalized_text, is_owner)
            intent = 'campaign'
        elif is_greeting(normalized_text):
            # แนวสากล: ทักทาย + ปุ่มทางเลือก — ไม่ยิงสินค้าจนกว่าลูกค้าจะบอกความต้องการ
            reply = TextSendMessage(text=_append_market_emphasis(greeting_text_for(user.name, tone), emphasis),
                                    quick_reply=quick_reply_items())
            intent = 'greeting'
        elif normalized_text in WHY_US_PHRASES:
            # ทำไมต้องซื้อกับป้าเข็ม — คุณค่าที่ประชาชนได้ (ราคาเท่ากัน/ของจริง/ดูแล)
            reply = TextSendMessage(text=why_us_text(tone))
            intent = 'why_us'
        elif normalized_text == "ค้นสินค้า":
            reply = TextSendMessage(text=_append_market_emphasis(search_guide(tone), emphasis),)
            intent = 'guide'
        elif (normalized_text in CATEGORY_MENU_PHRASES
              or _strip_polite_suffix(normalized_text) in CATEGORY_MENU_PHRASES):
            # เดินดูร้านเอง — เมนูหมวดสินค้า (แตะหมวด → ของขายดีหมวดนั้น) แบบเข้าร้านจริง
            reply = category_menu_message(db)
            intent = 'browse'
        elif normalized_text.startswith(CATEGORY_PICK_PREFIX):
            # แตะปุ่มหมวด (เช่น "ดูหมวดหูฟัง") → ของขายดีในหมวดนั้น
            reply = browse_category_message(db, user, _strip_polite_suffix(normalized_text[len(CATEGORY_PICK_PREFIX):]), is_owner)
            intent = 'browse'
        elif is_bot_manual_request(normalized_text):
            # คำถามคู่มือ (ค้น/เทียบ/จำ/พัสดุ/ติดตั้ง...) = ตอบจากคู่มือเท่านั้น ไม่ AI เดา
            reply = TextSendMessage(text=bot_manual_reply(normalized_text, is_owner))
            intent = 'manual'
            # ถามติดตั้ง/โค้ด → แนบปุ่มเปิด GitHub + คู่มือ (แตะได้ ไม่ต้องก๊อปลิงก์)
            if _wants_code_buttons(normalized_text):
                reply = [reply, _github_button_card()]
        elif is_contact_request(normalized_text):
            # ฝากคำถาม 2 ขั้น: แตะปุ่ม → ถามคำถามจริง → ป้าเข็มตอบเอง (ไม่มีทางส่งเจ้าของ)
            _pending_question[line_user_id] = datetime.datetime.utcnow()
            reply = TextSendMessage(text=ASK_QUESTION_PROMPT,
                                    quick_reply=quick_reply_items())
            intent = 'human'
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
        elif normalized_text.startswith(COMPARE_PREFIXES):
            # เทียบสินค้า A กับ B — ตารางข้อเท็จจริงจากข้อมูลจริง (ราคา/ยอดขาย/คอม)
            reply = handle_compare(db, normalized_text, user, is_owner)
            intent = 'compare'
        elif detect_emotion(normalized_text):
            # EQ: ลูกค้าระบายอารมณ์ (โกรธ/เสียใจ/ดีใจ) → เห็นใจก่อน แล้วค่อยชี้ทางช่วย
            # ปรับโทนคำตอบตามวัยด้วย (ทุกวัยรู้สึกว่ามีคนเข้าใจ)
            _etype, emo_reply = detect_emotion(normalized_text)
            tone_reply = emotion_reply(_etype, tone)
            if tone_reply:
                emo_reply = tone_reply
            reply = TextSendMessage(text=emo_reply, quick_reply=quick_reply_items())
            intent = 'emotion'
        elif is_web_search_request(normalized_text):
            # ค้นข้อมูลเน็ต/ความรู้ทั่วไป (Tavily → Firecrawl fallback) — ลูกค้าพิมพ์ "ค้นเน็ต ..."
            reply = _web_answer_messages(_web_search_text(normalized_text))
            intent = 'web'
        else:
            # พิมพ์อย่างอื่น (เช่น "หูฟัง" "อยากได้กระติกน้ำ" "หูฟังไม่เกิน 300") —
            # ค้นสินค้าที่ตรง (รองรับเงื่อนไขราคา); ไม่ตรง → บอกตรงๆ ไม่มโน
            # + เสนอของใกล้เคียงในหมวดเดียวกัน (ข้อมูลจริงจากคลัง)
            hits = search_products(db, normalized_text)
            if hits:
                reply = format_product_message(db, user, hits,
                                               title=f"🔍 สินค้าตรงกับ \"{display_term}\" ค่ะ",
                                               is_owner=is_owner)
                # ค้นเจอ 2-3 ตัวคล้ายกัน → ชวนเทียบต่อท้าย (แบบ Rufus)
                invite = compare_invite_message(hits)
                if invite:
                    reply = [reply, invite]
                intent = 'search'
                interest_cat = guess_category(normalized_text)
            elif looks_like_question(normalized_text) and guess_category(normalized_text) == "อื่นๆ":
                # คำถามความรู้สากล/ยอดนิยม (วิธี/คืออะไร/ทำไม/เท่าไหร่/วันนี้...) →
                # ค้นเน็ตให้อัตโนมัติ ไม่ต้องพิมพ์ "ค้นเน็ต" นำหน้า
                # กันพลาด: ถ้าคำถามมีคำหมวดสินค้าแฝง ("หูฟังอะไรดี") → เสนอของในร้านแทน
                reply = _web_answer_messages(normalized_text)
                intent = 'web'
            else:
                cat = guess_category(normalized_text)
                alt = []
                if cat and cat != "อื่นๆ":
                    pool = (db.query(models.Product)
                              .filter(models.Product.link_status == "ok",
                                      models.Product.sales_count >= MIN_SALES,
                                      models.Product.category == cat)
                              .all())
                    # เรียงตามความใกล้ชื่อ (ไม่ใช่ ai_score มั่ว) — ถามถุงเท้าได้ถุงเท้า
                    # ไม่ได้นาฬิกา/รองเท้า; ถ้าไม่มีตัวไหนชื่อใกล้เลย → ใช้ ai_score เดิม
                    scored = sorted(
                        ((p, _name_similarity(normalized_text, p.name)) for p in pool),
                        key=lambda t: (t[1], t[0].ai_score or 0),
                        reverse=True,
                    )
                    sim_hits = [p for p, s in scored if s > 0][:5]
                    alt = sim_hits or [p for p, _ in scored[:5]]
                if alt:
                    reply = [
                        TextSendMessage(text=nosearch_alt_text(display_term, cat, tone)),
                        product_cards_message(db, user, alt, title=f"🛍️ ของในหมวด {cat}",
                                              is_owner=is_owner),
                    ]
                    intent = 'nosearch'
                    interest_cat = cat if cat != "อื่นๆ" else None
                else:
                    # ของใหม่ในหมวด (30 วัน, ยังไม่ถึงเกณฑ์ขาย) — เสนอแทนทางตัน
                    # เช่น "กล่องสุ่ม" ที่เพิ่ง import ยอดขายยังต่ำ แต่มีของจริงในคลัง
                    fresh = []
                    if cat and cat != "อื่นๆ":
                        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
                        fresh = (db.query(models.Product)
                                   .filter(models.Product.link_status == "ok",
                                           models.Product.created_at >= cutoff,
                                           models.Product.category == cat)
                                   .order_by(models.Product.created_at.desc()).limit(3).all())
                    if fresh:
                        reply = [
                            TextSendMessage(text=nosearch_new_text(display_term, cat, tone)),
                            product_cards_message(db, user, fresh, title=f"🆕 ของใหม่หมวด {cat}",
                                                  is_owner=is_owner),
                        ]
                        intent = 'nosearch'
                        interest_cat = cat if cat != "อื่นๆ" else None
                    else:
                        text = _append_market_emphasis(nosearch_fallback_text(user_text, tone), emphasis)
                        # NUANOSE: ป้าเข็มตอบเอง ไม่ push เจ้าของ — intent='nosearch' ถูก log
                        # ไว้ใน chat_logs แล้ว เจ้าของดู gap ของคลังได้ทีหลังใน dashboard
                        reply = TextSendMessage(text=text, quick_reply=quick_reply_items())
                        intent = 'nosearch'  # รู้ว่าลูกค้าค้นอะไรไม่เจอ → เอาไปหาสินค้ามาเติม
                        interest_cat = cat if cat != "อื่นๆ" else None
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
        line_bot_api.reply_message(event.reply_token, _ensure_menu(reply))


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
        pref = (db.query(models.UserPreference)
                  .filter(models.UserPreference.line_user_id == line_user_id).first())
        tone = pref.tone if pref and pref.tone in ("youth", "elder") else "neutral"
        welcome = TextSendMessage(text=welcome_text(user.name, tone),
                                  quick_reply=welcome_quick_reply())
        privacy = TextSendMessage(text=PRIVACY_NOTICE)
        if "mock" in LINE_ACCESS_TOKEN.lower():
            logger.info(f"Mock follow welcome -> {user.name}")
        elif not push_guard(db):
            logger.warning(f"ข้าม welcome push (quota หมด) -> {user.name}")
        else:
            # welcome (มี quick reply) ต้องเป็นข้อความสุดท้ายของชุด — ไม่งั้น
            # LINE ลบปุ่มทันทีที่ push ข้อความถัดไป (privacy/ปุ่ม PDPA) ตามมา
            line_bot_api.push_message(line_user_id, [privacy, PRIVACY_BUTTON, welcome])
    except Exception as e:
        logger.error(f"Follow welcome error: {e}")
    finally:
        db.close()
