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
from app.services.category import guess_category, CATEGORY_KEYWORDS

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


SHOPEE_LINK_RE = re.compile(r'(?:https?://)?(?:www\.)?(?:s\.)?shopee\.co\.th/\S+', re.IGNORECASE)
ITEM_LINK_RE = re.compile(r'/product/(\d+)/(\d+)')


def extract_shopee_link(text: str) -> Optional[str]:
    """เจอลิงก์ Shopee ในข้อความ → คืนลิงก์ (ตัดเครื่องหมายท้าย), ไม่เจอ → None"""
    m = SHOPEE_LINK_RE.search(text or "")
    if not m:
        return None
    return m.group(0).rstrip('.,;!?)\"\u201d')


def handle_product_link(db: Session, user, link: str, is_owner: bool = False):
    """รับลิงก์สินค้าจากลูกค้า — ตอบด้วยข้อมูลจริงเท่านั้น (ไม่เดา/ไม่มโน):
    - ลิงก์ตรงกับสินค้าในคลัง (ลิงก์สั้น affiliate ของเรา) → ตอบการ์ดสินค้านั้น
    - ลิงก์อื่น (ยังไม่เข้าร้าน) → ตอบสุจริต ชี้ทางค้นชื่อแทน (เราตอบเฉพาะของที่ตรวจแล้ว)
    """
    link = (link or "").strip().rstrip('.,;!?)\"\u201d')
    prod = (db.query(models.Product)
              .filter(models.Product.affiliate_url == link,
                      models.Product.link_status == "ok").first())
    if prod:
        return product_cards_message(db, user, [prod],
                                     title="🔗 สินค้าจากลิงก์ของคุณ", is_owner=is_owner)
    if ITEM_LINK_RE.search(link):
        return TextSendMessage(text=(
            "🔗 ลิงก์นี้ยังไม่เข้าร้านป้าเข็มจ๊ะ\n\n"
            "ร้านเราตอบเฉพาะสินค้าที่ตรวจแล้วว่าลิงก์ใช้ได้จริง "
            "(กันลูกค้าเจอของตาย/ของปลอม)\n\n"
            "ลองพิมพ์ชื่อสินค้าค้นดูได้เลย เช่น \"หูฟัง\" \"กระติกน้ำ\" "
            "เดี๋ยวป้าเข็มหาของดีราคาคุ้มให้ค่ะ 😊"
        ))
    return TextSendMessage(text=(
        "🔗 ลิงก์นี้ยังไม่เข้าร้านป้าเข็มจ๊ะ\n\n"
        "ลองค้นชื่อสินค้าดูได้เลย เช่น \"หูฟังไม่เกิน 300\" "
        "เดี๋ยวป้าเข็มหาของดีราคาคุ้มให้ค่ะ 😊"
    ))


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
        QuickReplyButton(action=MessageAction(label="💛 ทำไมต้องป้าเข็ม", text="ทำไมต้องซื้อกับป้าเข็ม")),
    ])


def welcome_text(user_name: str) -> str:
    """ข้อความต้อนรับแรก (สั้น + คุณค่าชัด) — ลูกค้าใหม่เห็นทันทีว่าทำไมต้องอยู่กับป้าเข็ม"""
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


def welcome_quick_reply() -> QuickReply:
    """ปุ่มตอนแอดครั้งแรก — คุณค่าก่อน (ทำไมต้องป้าเข็ม) แล้วค่อยค้นหา"""
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="💛 ทำไมต้องป้าเข็ม", text="ทำไมต้องซื้อกับป้าเข็ม")),
        QuickReplyButton(action=MessageAction(label="🔍 ค้นสินค้า", text="ค้นสินค้า")),
        QuickReplyButton(action=MessageAction(label="⭐ ขายดีวันนี้", text="วันนี้ขายอะไรดี")),
        QuickReplyButton(action=MessageAction(label="🔥 อันดับขายดี", text="อันดับขายดี")),
    ])


SEARCH_GUIDE = (
    "🔍 ค้นสินค้าค่ะ! ลองพิมพ์แบบนี้:\n\n"
    "• \"หูฟัง\" — ค้นตามชื่อ\n"
    "• \"หูฟังไม่เกิน 300\" — ค้นตามงบ\n"
    "• \"กระติก 200-400\" — ค้นช่วงราคา\n\n"
    "พิมพ์มาได้เลย เดี๋ยวป้าเข็มหาให้ค่ะ 😊"
)

# --- ทำไมต้องซื้อกับป้าเข็ม (คุณค่าที่ประชาชนได้ — ข้อมูลจริง ไม่โฆษณาเกินจริง) ---
WHY_US_PHRASES = ("ทำไมต้องซื้อกับป้าเข็ม", "ทำไมต้องป้าเข็ม", "ทำไมต้องซื้อ", "เหตุผล", "ข้อดีของร้าน", "ป้าเข็มดียังไง")

# --- เทียบสินค้า A กับ B (แบบ Amazon "Compare with": ข้อมูลจริงในคลัง ไม่ AI เดา) ---
COMPARE_PREFIXES = ("เปรียบเทียบราคา", "เปรียบเทียบ", "เทียบราคา", "เทียบ")
COMPARE_SEPS = (" กับ ", " และ ", "กับ", "และ")
COMPARE_HELP = (
    "⚖️ เทียบสินค้าจ๊ะ! พิมพ์แบบนี้:\n\n"
    "• \"เทียบ GOOJODOQ กับ Jeep\"\n"
    "• \"เทียบราคากระติก ESKIMO กับ YTL\"\n"
    "• \"เปรียบเทียบหูฟัง A กับ B\"\n\n"
    "ป้าเข็มจะเทียบ ราคา/ยอดขาย/ค่านายหน้า/คะแนน ให้ดูจ๊ะ"
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
    """เทียบ A กับ B — การ์ด 2 คอลัมน์ (ราคา/ยอดขาย/คอม/คะแนน) + ปุ่มซื้อทั้งคู่"""
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
    if (a.commission or 0) != (b.commission or 0):
        better = a if (a.commission or 0) > (b.commission or 0) else b
        tag = "🅰️" if better is a else "🅱️"
        facts.append(f"{tag} ค่านายหน้าสูงกว่า (฿{float(better.commission or 0):,.0f})")
    return compare_flex_message(a, b, facts, spec_a, spec_b)


def compare_flex_message(a, b, facts: list, spec_a: str = "", spec_b: str = "") -> FlexSendMessage:
    """การ์ดเทียบ 2 คอลัมน์ใบเดียว (แบบตาราง Amazon) — ชื่อ/สเปค/ราคา/ยอดขาย/คอม/คะแนน + ปุ่มซื้อ
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
            {"type": "text", "text": f"💸 คอม {float(p.commission or 0):,.0f}฿", "size": "xxs",
             "color": "#666666", "align": "center", "wrap": True},
            {"type": "text", "text": f"📈 {p.ai_score or 0}/100", "size": "xxs",
             "color": "#666666", "align": "center", "wrap": True},
            {"type": "button", "style": "primary", "color": "#E74C3C", "height": "sm",
             "action": {"type": "uri", "label": "🛒 ซื้อเลย", "uri": p.affiliate_url}},
        ]
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


def why_us_text() -> str:
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
    r"(?:ไม่เกิน|ไม่แพงกว่า|ไม่แพง|ต่ำกว่า|ถูกกว่า|งบ|ในงบ|ราคา|ประมาณ|ภายใน|ซื้อได้ใน)\s*\d+(?:\.\d+)?",
    r"\d+\s*(?:-|–|ถึง)\s*\d+",
    r"\d+(?:\.\d+)?\s*บาท",
)


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
                             "ไร้สาย", "รุ่น", "ใหม่", "ชุด", "น้ำ"})


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


# การันต์/คำพ้องที่คนไทยพิมพ์หลากหลาย → แบบมาตรฐาน (กันพิมพ์เพี้ยนแล้วหาไม่เจอ)
# ใช้เฉพาะฝั่งคำค้น — ชื่อสินค้าในคลังเขียนแบบมาตรฐานอยู่แล้ว
THAI_VARIANT_MAP = {
    "บลูธูธ": "บลูทูธ", "บลูทูท": "บลูทูธ", "บลูธูท": "บลูทูธ", "บลูทูต": "บลูทูธ",
    "ชาร์ท": "ชาร์จ", "ชารท": "ชาร์จ",
    "ไอแพท": "ไอแพด", "ไอแพ็ด": "ไอแพด",
    "iphone": "ไอโฟน", "ipad": "ไอแพด",
    "type-c": "type c", "typec": "type c",
}


def normalize_query(q: str) -> str:
    for a, b in THAI_VARIANT_MAP.items():
        q = q.replace(a, b)
    return q


def strip_price_phrase(q: str) -> str:
    """ตัดเงื่อนไขราคาออกจากคำค้น: 'หูฟังไม่เกิน 300' → 'หูฟัง', 'กระติก 200-400' → 'กระติก'"""
    t = q
    for pat in PRICE_PHRASE_RES:
        t = re.sub(pat, "", t)
    return t.strip(" -–,")


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


def search_products(db: Session, query: str) -> list:
    """ค้นสินค้า: ตรงชื่อ/หมวด + เข้าใจเงื่อนไขราคา ('หูฟังไม่เกิน 300', 'งบ 500',
    'กระติก 200-400') — จัดอันดับความตรง แล้วตอบสูงสุด 3 ตัว
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
    q = _nfc(normalize_query(q))
    min_price, max_price = parse_price_conditions(query)
    # คำหลักจริงๆ: ตัดคำนำหน้าเล่นๆ + เงื่อนไขราคา → "อยากได้หูฟังไม่เกิน 300" = "หูฟัง"
    q_core = strip_price_phrase(strip_filler_prefix(q))

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
        if after and after.isalnum() and not (0x0E00 <= ord(after) <= 0x0E7F):
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
            q_kws = [kw for kw, _c in CATEGORY_KEYWORDS
                     if len(kw) >= 4 and kw in q_core and kw != q_core]
            q_kws = [kw for kw in q_kws
                     if not any(kw in other for other in q_kws if other != kw)]
            # ต้องมีทุกคำย่อยในชื่อ (AND) — กัน "กระติกน้ำแข็ง" ไปโดนกางเกง
            # "ผ้าไหมน้ำแข็ง" (มีแค่คำว่า น้ำแข็ง คำเดียว)
            if q_kws and all(kw in name for kw in q_kws):
                w += len(q_kws)
                tier = max(tier, max(strong_tier(name, kw) for kw in q_kws))
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
            for kw, _c in CATEGORY_KEYWORDS:
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
            hits = [h for h in hits
                    if not any(m in _nfc((h[0].name or "").lower()) for m in APPLE_ONLY)]
            if not hits:
                return []  # ไม่มีที่เข้ากับ android จริง → สุจริต ไม่เอาสาย Apple มาแทน
        strong_hits = [h for h in hits if h[2] >= 1]
        if not strong_hits:
            return []  # แมตช์ท้ายชื่อ (ยัด SEO) เท่านั้น → ไม่เอาขึ้นหน้า (สุจริต)
        hits = strong_hits
        if min_price is not None or max_price is not None:
            budget_hits = [h for h in hits if in_budget(h[0])]
            if not budget_hits:
                return []  # มีชื่อตรงแต่ไม่มีตัวในงบ → ไม่เอาของมั่วมาแทน (สุจริต)
            hits = budget_hits
        hits.sort(key=lambda pw: (pw[2], pw[1], pw[0].ai_score or 0), reverse=True)
        return [p for p, _, _ in hits[:3]]

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


@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
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
            # PDPA: สิทธิ์ลบข้อมูล (erasure) — ลบชื่อ + ประวัติการสนทนา + สิ่งที่ให้จำไว้ทันที
            db.query(models.ChatLog).filter(models.ChatLog.line_user_id == line_user_id).delete(synchronize_session=False)
            db.query(models.UserPreference).filter(models.UserPreference.line_user_id == line_user_id).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.line_user_id == line_user_id).delete(synchronize_session=False)
            db.commit()
            reply = TextSendMessage(text=DELETE_REPLY)
            intent = 'delete'
        elif is_wismo(normalized_text):
            # ลูกค้าทวงถาม/ติดตามพัสดุ — แนะนำเส้นทางตรวจเองบน Shopee (24/7)
            # ลิงก์อยู่ในปุ่มการ์ด (ไม่ใช่ข้อความ) — กัน LINE ธง "ไม่ปลอดภัย"
            reply = [TextSendMessage(text=WISMO_REPLY), WISMO_BUTTON]
            intent = 'wismo'
        elif extract_shopee_link(normalized_text):
            # ลูกค้าส่งลิงก์ Shopee มา — ตอบด้วยข้อมูลจริงเท่านั้น
            # (ตรงกับคลัง = การ์ดสินค้า, ไม่ตรง = บอกสุจริตว่ายังไม่เข้าร้าน)
            reply = handle_product_link(db, user, extract_shopee_link(normalized_text), is_owner)
            intent = 'link'
        elif normalized_text in NEW_PHRASES:
            # มีอะไรใหม่ — ดันสินค้าใหม่หมวดที่เคนสนใจ (จำจาก chat_logs + ที่บอกให้จำไว้)
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
            reply = TextSendMessage(text=greeting_text(user.name),
                                    quick_reply=quick_reply_items())
            intent = 'greeting'
        elif normalized_text in WHY_US_PHRASES:
            # ทำไมต้องซื้อกับป้าเข็ม — คุณค่าที่ประชาชนได้ (ราคาเท่ากัน/ของจริง/ดูแล)
            reply = TextSendMessage(text=why_us_text())
            intent = 'why_us'
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
        elif normalized_text.startswith(COMPARE_PREFIXES):
            # เทียบสินค้า A กับ B — ตารางข้อเท็จจริงจากข้อมูลจริง (ราคา/ยอดขาย/คอม)
            reply = handle_compare(db, normalized_text, user, is_owner)
            intent = 'compare'
        else:
            # พิมพ์อย่างอื่น (เช่น "หูฟัง" "อยากได้กระติกน้ำ" "หูฟังไม่เกิน 300") —
            # ค้นสินค้าที่ตรง (รองรับเงื่อนไขราคา); ไม่ตรง → บอกตรงๆ ไม่มโน
            # + เสนอของใกล้เคียงในหมวดเดียวกัน (ข้อมูลจริงจากคลัง)
            hits = search_products(db, normalized_text)
            if hits:
                reply = format_product_message(db, user, hits,
                                               title=f"🔍 สินค้าตรงกับ \"{user_text}\" ค่ะ",
                                               is_owner=is_owner)
                # ค้นเจอ 2-3 ตัวคล้ายกัน → ชวนเทียบต่อท้าย (แบบ Rufus)
                invite = compare_invite_message(hits)
                if invite:
                    reply = [reply, invite]
                intent = 'search'
                interest_cat = guess_category(normalized_text)
            else:
                cat = guess_category(normalized_text)
                alt = []
                if cat and cat != "อื่นๆ":
                    alt = (db.query(models.Product)
                             .filter(models.Product.link_status == "ok",
                                     models.Product.sales_count >= MIN_SALES,
                                     models.Product.category == cat)
                             .order_by(models.Product.ai_score.desc()).limit(3).all())
                if alt:
                    reply = [
                        TextSendMessage(text=f"🔍 ยังไม่มี \"{user_text}\" ในร้านป้าเข็มตอนนี้จ๊ะ\n\n"
                                             f"ลองดูของใกล้เคียงในหมวด {cat} ด้านล่าง หรือพิมพ์ชื่ออื่นได้เลยค่ะ 😊"),
                        product_cards_message(db, user, alt, title=f"🛍️ ของในหมวด {cat}",
                                              is_owner=is_owner),
                    ]
                else:
                    reply = TextSendMessage(text=f"🔍 ยังไม่มี \"{user_text}\" ในร้านป้าเข็มตอนนี้จ๊ะ\n\n"
                                                 "ลองพิมพ์ชื่อสินค้าสั้นๆ เช่น \"หูฟัง\" \"กระติกน้ำ\" "
                                                 "หรือแตะปุ่มด้านล่างได้เลยค่ะ 👇",
                                            quick_reply=quick_reply_items())
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
        welcome = TextSendMessage(text=welcome_text(user.name),
                                  quick_reply=welcome_quick_reply())
        privacy = TextSendMessage(text=PRIVACY_NOTICE)
        if "mock" in LINE_ACCESS_TOKEN.lower():
            logger.info(f"Mock follow welcome -> {user.name}")
        else:
            line_bot_api.push_message(line_user_id, [welcome, privacy, PRIVACY_BUTTON])
    except Exception as e:
        logger.error(f"Follow welcome error: {e}")
    finally:
        db.close()
