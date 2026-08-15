# -*- coding: utf-8 -*-
"""เทสต์ template script (ไม่เรียก LLM) — build_template_script + fallback เมื่อ LLM พัง.

- build_template_script ต้องคืน field ครบ SCRIPT_KEYS เหมือนผลจาก LLM (คนใช้ผลนี้
  ใน product_cards.py / cron.py / backfill) — ถ้า field ขาด จะพังต่อท้าย
- caption ต้องเป็นข้อความล้วน (ไม่มี inline hashtag) — consumer ต่อ hashtags เอง
  ด้วย format_hashtags_text ถ้า caption มี tag อยู่แล้วจะโพสต์ซ้ำ
- generate_script_for_product เมื่อ provider ไม่มี key (หรือ key เป็น mock) ต้อง
  fallback กลับมาที่ template ไม่ throw — กัน "บอสใหญ่" พังตอน Groq down
"""
from app.config import settings
from app.services.ai_generator import (
    SCRIPT_KEYS, build_template_script, format_hashtags_text, generate_script_for_product,
)


def test_build_template_script_returns_full_schema():
    data = build_template_script("หูฟังไร้สาย", "หูฟัง", 250, style="standard")
    assert SCRIPT_KEYS.issubset(data)
    assert "หูฟังไร้สาย" in data["hook"]
    assert "หูฟังไร้สาย" in data["caption"]
    # hashtags ต้องไม่เป็น string เดี่ยว ๆ (list ใช้ได้กับ format_hashtags_text)
    assert isinstance(data["hashtags"], list)


def test_template_caption_has_no_inline_hashtags():
    """caption ต้องไม่มี '#' — แฮชแท็กอยู่ที่ช่อง hashtags เท่านั้น กันโพสต์/การ์ดซ้ำแท็ก"""
    data = build_template_script("กระติกน้ำแข็ง", "แก้วน้ำ", 299, style="standard")
    assert "#" not in data["caption"]
    tags = format_hashtags_text(data["hashtags"])
    assert "#ของดีบอกต่อ" in tags
    assert "#ป้าป้ายยา" in tags
    # แท็กที่ format_hashtags_text คืนมา ต้องไม่ซ้ำกับสิ่งที่อยู่ใน caption (ไม่มีเลย)
    for t in tags.split():
        assert t not in data["caption"]


def test_generate_script_falls_back_to_template_when_no_provider_key(monkeypatch):
    # groq branch ถูก skip เพราะ key มีคำว่า mock → ไม่เรียก LLM → fallback template
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "mock-key")
    result = generate_script_for_product("กระติกน้ำแข็ง", "แก้วน้ำ", 299, tone="neutral")
    assert SCRIPT_KEYS.issubset(result)
    assert "กระติกน้ำแข็ง" in result["hook"]
    assert "#" not in result["caption"]  # fallback ก็ต้องไม่ฝังแท็กใน caption
