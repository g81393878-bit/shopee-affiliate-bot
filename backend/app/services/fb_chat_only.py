"""
Facebook Chat-Only Mode (หยุดขายแล้ว — ตอบแบบพูดคุยทักทายอย่างเดียว)

เปิดใช้งานเป็นค่าเริ่มต้น (FB_CHAT_ONLY_MODE=true)
- ปิดการเสนอขาย ราคา แพ็กเกจ เลขบัญชี ปุ่มสั่งซื้อ และ Private Offer DM ทั้งหมด
- หากมีคนคอมเมนต์หรือทักแชททั่วไป (เช่น @ไฮไลท์, @ผู้ติดตาม, สวัสดี, สติกเกอร์) -> ตอบทักทายสุภาพแบบสุ่มหลายประโยค
- หากมีคนสอบถามสั่งซื้อ / ราคา / ปลาสลิด -> แจ้งอย่างสุภาพว่างดจำหน่าย/เลิกขายแล้ว แต่ยินดีพูดคุยทักทายเสมอ

หากต้องการกลับมาเปิดโหมดขายในอนาคต สามารถตั้งค่า env: FB_CHAT_ONLY_MODE=false
"""
from __future__ import annotations

import os
import random
import re

_PURCHASE_KEYWORDS = (
    "สั่ง",
    "ซื้อ",
    "ราคา",
    "เท่าไหร่",
    "เท่าไร",
    "กี่บาท",
    "กี่โล",
    "กิโล",
    "ครึ่งโล",
    "500g",
    "500 กรัม",
    "1 กก",
    "2 กก",
    "390",
    "550",
    "1090",
    "1,090",
    "สนใจ",
    "โอน",
    "บัญชี",
    "ปลายทาง",
    "cod",
    "ค่าส่ง",
    "ส่งฟรี",
    "ส่งไหม",
    "ส่งมั้ย",
    "รถเย็น",
    "ห้องเย็น",
    "มีของไหม",
    "ยังมีขาย",
    "ขายไหม",
    "ขายมั้ย",
    "เปิดขาย",
    "ปลาสลิด",
    "พร้อมส่ง",
    "พิกัด",
    "หน้าร้าน",
    "ที่อยู่",
    "รับ 1",
    "รับ 2",
    "เอา 1",
    "เอา 2",
)

_PHONE_RE = re.compile(r"(?:0[689]\d{8}|0[689]\d{1}[-\s]?\d{3}[-\s]?\d{4}|0[689]\d{2}[-\s]?\d{3}[-\s]?\d{3})")

_CLOSED_SHOP_REPLIES = (
    "{greeting} 🙏💕 ขอบพระคุณมากๆ เลยนะคะที่แวะมาสอบถาม ตอนนี้ป้าเข็มงดจำหน่าย/เลิกขายแล้วค่ะ แต่ยังแวะมาทักทายพูดคุยกันได้เสมอเลยนะคะ ขอให้สุขภาพแข็งแรงและมีความสุขทุกวันค่ะ 🌷",
    "{greeting} 🙏💕 ขอบคุณที่คิดถึงกันนะคะ ตอนนี้ทางเพจไม่ได้เปิดขายแล้วค่ะ แวะมาทักทายพูดคุยกันเล่นๆ ได้ตลอดเลยนะคะ ดูแลสุขภาพด้วยน้า 😊💐",
    "{greeting} 🙏💕 ขอบพระคุณที่ให้ความสนใจนะคะ ปัจจุบันป้าเข็มหยุดขายแล้วค่ะ แต่ยินดีพูดคุยทักทายกับทุกท่านเสมอนะคะ ขอให้วันนี้เป็นวันที่ดีค่ะ ✨",
)

_FRIENDLY_GREETING_REPLIES = (
    "{greeting} 🙏💕 ขอบคุณที่แวะมาทักทายกันนะคะ ขอให้วันนี้เป็นวันที่สดใสและมีความสุขมากๆ ค่ะ 🌷✨",
    "{greeting} 😊💕 ดีใจจังเลยค่ะที่แวะมาทักทายกัน ช่วงนี้สบายดีไหมคะ ดูแลสุขภาพด้วยน้า 💐",
    "{greeting} 🙏✨ ขอบคุณที่แวะเข้ามาเยี่ยมชมเพจนะคะ แวะมาคุยเล่นทักทายกันได้เสมอเลยค่ะ 💕",
    "{greeting} 🌸💕 สวัสดีวันดีๆ นะคะ ขอบคุณที่แวะมาทักทายกันค่ะ ขอให้มีแต่เรื่องดีๆ เข้ามาทั้งวันเลยน้า 😊",
    "{greeting} 🙏💐 แวะมาส่งกำลังใจให้เช่นกันนะคะ ขอให้สุขภาพแข็งแรง ยิ้มได้ทุกวันเลยค่ะ ✨",
)

_THANKS_REPLIES = (
    "{greeting} 🙏💕 ยินดีมากๆ เลยค่ะ ขอให้มีความสุขและสุขภาพแข็งแรงเสมอนะคะ 🌷",
    "{greeting} 😊💐 ด้วยความยินดีเลยค่ะ แวะมาทักทายกันได้ตลอดนะคะ ✨",
)

_HOW_ARE_YOU_REPLIES = (
    "{greeting} 😊💕 ป้าเข็มสบายดีค่ะ ขอบคุณที่ถามไถ่กันนะคะ ทางโน้นสบายดีไหมคะ ดูแลสุขภาพด้วยน้า 💐",
    "{greeting} 🙏✨ สบายดีจ้า ขอบคุณที่เป็นห่วงถามไถ่กันนะคะ ขอให้แข็งแรงสดใสเช่นกันค่ะ 🌷",
)


def is_fb_chat_only_mode() -> bool:
    """คืนค่า True เมื่ออยู่ในโหมดพูดคุยทักทาย (เลิกขายแล้ว) — ค่าเริ่มต้นคือ True"""
    val = os.getenv("FB_CHAT_ONLY_MODE", "true").strip().lower()
    return val not in ("0", "false", "no", "off")


def _format_greeting(sender_name: str = "") -> str:
    clean_name = (sender_name or "").strip()
    if clean_name.startswith("คุณ"):
        return f"สวัสดีค่ะ{clean_name}"
    if clean_name:
        return f"สวัสดีค่ะคุณ {clean_name}"
    return "สวัสดีค่ะ"


def is_purchase_inquiry(text: str = "") -> bool:
    """ตรวจว่าข้อความเป็นการสอบถามสั่งซื้อ/ราคา/ที่อยู่จัดส่งหรือไม่"""
    t = (text or "").strip()
    if not t:
        return False
    lower = t.lower()
    if _PHONE_RE.search(lower):
        return True
    if re.fullmatch(r"[123]", lower):
        return True
    return any(kw in lower for kw in _PURCHASE_KEYWORDS)


def build_friendly_chat_reply(
    text: str = "",
    sender_name: str = "",
    channel: str = "comment",
) -> str:
    """สร้างข้อความตอบกลับแบบพูดคุยทักทาย (ไม่มีการเสนอขาย ราคา หรือลิงก์สั่งซื้อ)"""
    _ = channel  # reserved for future channel-specific tweaks
    greeting = _format_greeting(sender_name)
    t = (text or "").strip()
    lower = t.lower()

    # ตรวจจับคำถามค้นหาสถานพยาบาล (แยกแยะคนและสัตว์ชัดเจน 100%)
    try:
        try:
            from app.services.hospital_directory_service import is_any_hospital_query, format_hospital_directory_reply
        except ImportError:
            from backend.app.services.hospital_directory_service import is_any_hospital_query, format_hospital_directory_reply
        if is_any_hospital_query(t):
            max_res = 3 if channel == "comment" else 5
            return format_hospital_directory_reply(t, max_results=max_res)
    except Exception:
        pass

    # ตรวจจับคำถามค้นหาร้านอาหาร / สถานที่ท่องเที่ยว / โรงแรมทั่วไทย
    try:
        try:
            from app.services.places_directory_service import is_places_query, format_places_directory_reply
        except ImportError:
            from backend.app.services.places_directory_service import is_places_query, format_places_directory_reply
        if is_places_query(t):
            max_res = 2 if channel == "comment" else 3
            return format_places_directory_reply(t, max_results=max_res)
    except Exception:
        pass

    if is_purchase_inquiry(t):
        return random.choice(_CLOSED_SHOP_REPLIES).format(greeting=greeting)

    if any(k in lower for k in ("สบายดีไหม", "สบายดีมั้ย", "เป็นไงบ้าง", "เป็นยังไงบ้าง")):
        return random.choice(_HOW_ARE_YOU_REPLIES).format(greeting=greeting)

    if any(k in lower for k in ("ขอบคุณ", "ขอบใจ", "thank")):
        return random.choice(_THANKS_REPLIES).format(greeting=greeting)

    # พิมพ์แค่ชื่อจังหวัด/อำเภอ/ตำบล (เช่น "สุโขทัย", "อ.บางปะหัน อยุธยา") -> ส่งชุดพิกัด 4 หมวดทันที
    try:
        try:
            from app.services.places_directory_service import format_area_bundle_reply
        except ImportError:
            from backend.app.services.places_directory_service import format_area_bundle_reply
        bundle = format_area_bundle_reply(t)
        if bundle:
            return bundle
    except Exception:
        pass

    return random.choice(_FRIENDLY_GREETING_REPLIES).format(greeting=greeting)
