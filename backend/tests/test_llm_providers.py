# -*- coding: utf-8 -*-
"""Regression tests สำหรับ provider Anthropic (Claude) — กัน "บอสใหญ่" พังเมื่อเพิ่ม provider ใหม่.

- anthropic_keys() / anthropic_clients(): parse/กรอง/วน key + ชี้ base_url OpenAI-compat
- generate_script_for_product / analyze_product_with_ai: เดิน anthropic branch (mock client
  คืน JSON) แล้ว parse กลับเป็น schema ที่ถูกต้อง — ไม่ fallback ไป mock script
"""
import json

from app.config import settings
from app.services.llm_clients import ANTHROPIC_BASE_URL, anthropic_clients, anthropic_keys
from app.services.ai_generator import generate_script_for_product
from app.services.ai_analyzer import analyze_product_with_ai

SCRIPT_JSON = json.dumps({
    "hook": "หยุดก่อนจ๊ะ!", "problem": "พังง่าย", "solution": "ใช้ดี", "cta": "กดลิงก์",
    "caption": "ลองดูจ๊ะ", "hashtags": ["ของดี", "บอกต่อ"], "title": "ป้าป้ายยา", "thumbnail_prompt": "ภาพสินค้า",
})

ANALYSIS_JSON = json.dumps({
    "product_score": 90,
    "recommendation": "ควรทำ Content ทันที",
    "reasons": ["ขายดี", "รีวิวดี"],
    "content_ideas": ["คลิปรีวิว"],
    "script": {
        "hook": "h", "problem": "p", "solution": "s", "cta": "c",
        "caption": "cap", "hashtags": ["t1"], "title": "t", "thumbnail_prompt": "tp",
    },
})


class _FakeClient:
    """OpenAI-client ปลอมคืน content JSON ตายตัว (ไม่แตะเน็ต)"""

    def __init__(self, api_key, content):
        self.api_key = api_key
        self._content = content

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        msg = type("M", (), {"content": self._content})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()


def test_anthropic_keys_parses_and_filters(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-aaa, mock_key , sk-ant-aaa, sk-ant-bbb")
    assert anthropic_keys() == ["sk-ant-aaa", "sk-ant-bbb"]


def test_anthropic_clients_uses_compat_base_url(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-aaa,sk-ant-bbb")
    clients = anthropic_clients()
    assert len(clients) == 2
    for c in clients:
        assert str(c.base_url) == ANTHROPIC_BASE_URL


def test_generate_script_uses_anthropic_branch(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(settings, "ANTHROPIC_MODEL", "claude-opus-5")
    fake = _FakeClient("sk-ant-test", SCRIPT_JSON)
    monkeypatch.setattr("app.services.llm_clients.anthropic_clients", lambda: [fake])

    result = generate_script_for_product("หูฟังไร้สาย", "หูฟัง", 250, tone="neutral")
    assert result["hook"] == "หยุดก่อนจ๊ะ!"
    assert result["hashtags"] == ["ของดี", "บอกต่อ"]


def test_analyze_product_uses_anthropic_branch(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(settings, "ANTHROPIC_MODEL", "claude-opus-5")
    fake = _FakeClient("sk-ant-test", ANALYSIS_JSON)
    monkeypatch.setattr("app.services.llm_clients.anthropic_clients", lambda: [fake])

    result = analyze_product_with_ai("หูฟังไร้สาย", "หูฟัง", 250, 4.5, 5000, 10)
    assert result["recommendation"] == "ควรทำ Content ทันที"
    assert result["reasons"] == ["ขายดี", "รีวิวดี"]


def test_analyze_product_mock_fallback_caption_has_no_inline_hashtags(monkeypatch):
    """Fallback mock (ทุก provider ไม่มี key) ต้องคืน caption ข้อความล้วน ไม่ฝัง '#' —
    กันแท็กซ้ำเหมือน build_template_script (แท็กไปอยู่ที่ช่อง script.hashtags เท่านั้น)"""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "mock-key")
    result = analyze_product_with_ai("หูฟังไร้สาย", "หูฟัง", 250, 4.5, 5000, 10)
    script = result.get("script", {})
    assert "#" not in script.get("caption", "")
    assert script.get("hashtags")  # แท็กต้องไปอยู่ที่ช่อง hashtags ไม่ใช่ใน caption
