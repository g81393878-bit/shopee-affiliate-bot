# -*- coding: utf-8 -*-
"""เทสต์ text_cleaner.sanitize_post_text — กรองอักษรต่างภาษาก่อนโพสต์เพจ."""
from app.services.text_cleaner import sanitize_post_text


def test_keeps_thai_latin_digits_and_emoji():
    text = "ป้าเข็มขายของดี ราคา ฿250 ✅ ใช้ LINE OA 👉 https://lin.ee/x 🛍️"
    assert sanitize_post_text(text) == text


def test_strips_persian_arabic_script():
    # เจอจริงจาก Groq: คำ "دیزاین" (design) หลุดปนมากับข้อความไทย
    text = "ป้าเห็นข่าวนี้แล้ว دیزاین ต้องเอามาฝากลูกหลาน 😊"
    out = sanitize_post_text(text)
    assert "دیزاین" not in out
    assert "ป้าเห็นข่าวนี้แล้ว" in out and "ต้องเอามาฝากลูกหลาน" in out and "😊" in out


def test_strips_cyrillic_and_cjk():
    text = "ของดี Привет ต้องใช้จริง 中文 จริง ๆ"
    out = sanitize_post_text(text)
    assert "Привет" not in out and "中文" not in out
    assert "ของดี" in out and "ต้องใช้จริง" in out


def test_collapses_double_spaces_after_removal():
    text = "ป้าเห็น   แล้ว  มาฝาก"
    assert sanitize_post_text(text) == "ป้าเห็น แล้ว มาฝาก"


def test_preserves_newlines_and_limits_blank_lines():
    text = "บรรทัดแรก\n\n\n\nบรรทัดสอง"
    assert sanitize_post_text(text) == "บรรทัดแรก\n\nบรรทัดสอง"


def test_keeps_currency_and_trademark_symbols():
    text = "ราคา €10 กับ £5 และแบรนด์™ ค่ะ"
    assert sanitize_post_text(text) == text


def test_empty_and_none_safe():
    assert sanitize_post_text("") == ""
    assert sanitize_post_text(None) == ""


def test_all_foreign_becomes_empty():
    assert sanitize_post_text("دیزاین 中文 Привет") == ""
