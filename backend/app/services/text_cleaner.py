# -*- coding: utf-8 -*-
"""ตัวกรองข้อความโพสต์ — ตัดอักษรต่างภาษาที่ LLM หลุดออกมาเป็นบางครั้ง.

เจอจริง: Groq (llama) เขียนคอนเทนต์บางครั้งหลุดอักษรเปอร์เซีย/อาหรับ (เช่น
"دیزاین") ปนมากับข้อความไทย — ถ้าปล่อยขึ้นเพจ Facebook จะดูไม่เป็นมืออาชีพ
กรองที่จุดเดียว (ก่อน post_feed) ให้เหลือเฉพาะ script ที่โพสต์ไทยใช้จริง:
ไทย, Latin, ตัวเลข, เครื่องหมายวรรคตอน, สัญลักษณ์สกุลเงิน และ emoji —
script อื่น (อาหรับ/เปอร์เซีย/ซีริลลิก/จีน/ญี่ปุ่น/ฮีบรู/เทวนาครี...) ตัดทิ้ง
"""

import re

# ช่วง Unicode ที่อนุญาตในโพสต์:
# - Latin พื้นฐาน + Latin-1 Supplement + Latin Extended-A/B (รวมตัวเลข/เครื่องหมาย)
# - General Punctuation (en/em dash, ellipsis, เครื่องหมายคำพูดโค้ง, bullet ...)
# - Currency Symbols (€ £ ¥ ... — ฿ อยู่ในช่วง Thai ด้านล่าง)
# - Letterlike Symbols (™ ℠ № ... ชื่อแบรนด์ในคำอธิบายสินค้า)
# - Thai (รวม ฿ U+0E3F และตัวเลขไทย U+0E50-0E59)
# - Arrows / Misc Symbols & Dingbats / Misc Symbols & Arrows (สัญลักษณ์/emoji เก่า)
# - Emoticons + สัญลักษณ์ภาพ + Transport + Supplemental Symbols (emoji หลัก)
# - Regional Indicators (ธงชาติ)
_ALLOWED_RANGES = (
    (0x0020, 0x024F),
    (0x2000, 0x206F),
    (0x20A0, 0x20CF),
    (0x2100, 0x214F),
    (0x0E00, 0x0E7F),
    (0x2190, 0x21FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0x1F000, 0x1FAFF),
    (0x1F1E6, 0x1F1FF),
)

# อักขระเดี่ยวที่อนุญาตเพิ่ม (อยู่นอกช่วงด้านบน): ขึ้นบรรทัด + อักขระประกอบ emoji
_ALLOWED_CHARS = frozenset("\n\t\r\u200D\uFE0F\u20E3")


def _allowed(ch: str) -> bool:
    cp = ord(ch)
    for lo, hi in _ALLOWED_RANGES:
        if lo <= cp <= hi:
            return True
    return ch in _ALLOWED_CHARS


def sanitize_post_text(text: str) -> str:
    """ตัดอักษรนอกช่วงที่อนุญาตทิ้ง แล้วเก็บรูปแบบการขึ้นบรรทัดให้เรียบร้อย.

    - เก็บ: ไทย, Latin, ตัวเลข, เครื่องหมายวรรคตอน, สัญลักษณ์, emoji
    - ตัด: script ต่างภาษา (อาหรับ/ซีริลลิก/CJK...) — ตัวอย่าง "دیزاین" จะหายไป
    - ยุบช่องว่างซ้ำเป็นช่องเดียว + จำกัดบรรทัดว่างติดกันไม่เกิน 1 บรรทัด
    คืน "" ถ้าข้อความว่าง (caller ตัดสินใจ fallback ต่อเอง)
    """
    if not text:
        return ""
    kept = "".join(ch for ch in text if _allowed(ch))
    kept = re.sub(r"[ \t]{2,}", " ", kept)
    kept = re.sub(r"[ \t]*\n[ \t]*", "\n", kept)
    kept = re.sub(r"\n{3,}", "\n\n", kept)
    return kept.strip()
