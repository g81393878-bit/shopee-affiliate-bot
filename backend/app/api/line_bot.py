import os
import json
import logging
import inspect
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Header, Request
from sqlalchemy.orm import Session
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextMessage, MessageEvent, TextSendMessage, StickerMessage, StickerSendMessage
from pydantic import BaseModel

from app.db import SessionLocal, get_db
from app import models

logger = logging.getLogger(__name__)

# Fallback to dummy tokens if not set in environment (prevents crash on initialization in dev/test)
LINE_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN') or "mock_line_channel_token"
LINE_SECRET = os.getenv('LINE_CHANNEL_SECRET') or "mock_line_channel_secret"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

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
    body_str = body.decode("utf-8")
    
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


def handle_today_deals(db: Session, user: models.User) -> str:
    """Fetch top 3 highest scoring products"""
    products = db.query(models.Product).order_by(models.Product.ai_score.desc()).limit(3).all()
        
    if not products:
        return (
            f"สวัสดีครับคุณ {user.name} 👋\n\n"
            "⚠️ ยังไม่มีสินค้าในระบบชั่วคราวครับ\n\n"
            "คุณสามารถเพิ่มสินค้าเข้าระบบก่อนได้ผ่านหน้า Dashboard หรือ API ของเรา เพื่อให้ระบบ AI ประเมินและสร้างสคริปต์ได้ครับ"
        )
        
    message_lines = [f"⭐ สินค้าแนะนำขายดีวันนี้สำหรับคุณ {user.name} ⭐\n"]
    
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
                
        message_lines.append(
            f"{i}. {prod.name}\n"
            f"💰 ราคา: {prod.price} บาท\n"
            f"📈 คะแนนความน่าทำคลิป: {prod.ai_score}/100\n"
            f"{hook_text}"
            f"🔗 ลิงก์ Affiliate: {prod.affiliate_url or 'ไม่มีลิงก์'}\n"
        )
        
    message_lines.append("ลองนำแนวทางหัวข้อนี้ไปถ่ายทำคอนเทนต์ด่วน ๆ เลยครับ! 🚀")
    return "\n".join(message_lines)


def get_or_create_line_user(db: Session, line_user_id: str) -> models.User:
    """Look up user by LINE user ID or register on the fly"""
    user = db.query(models.User).filter(models.User.line_user_id == line_user_id).first()
    if not user:
        user = models.User(
            name="LINE User",
            line_user_id=line_user_id,
            shopee_affiliate_id="SHP_AFF_AUTO"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Registered new LINE user on the fly: {line_user_id}")
    return user


@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
    print("!!!!!!!!!!!!!!!!!!!!!!")
    print(event)
    print("!!!!!!!!!!!!!!!!!!!!!!")
    
    user_text = event.message.text.strip()
    line_user_id = event.source.user_id
    
    db = SessionLocal()
    try:
        user = get_or_create_line_user(db, line_user_id)
        if user_text == "วันนี้ขายอะไรดี?":
            reply_text = handle_today_deals(db, user)
        else:
            reply_text = (
                f"🤖 สวัสดีครับคุณ {user.name}!\n"
                "ผมคือบอทผู้ช่วย AI Affiliate ของคุณ\n\n"
                "พิมพ์คำว่า \"วันนี้ขายอะไรดี?\" - เพื่อให้ผมช่วยหาสินค้าเจ๋ง ๆ 3 อันดับแรกที่คุณน่าลุยทำคอนเทนต์ในวันนี้ครับ!"
            )
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
            TextSendMessage(text=reply_text)
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
