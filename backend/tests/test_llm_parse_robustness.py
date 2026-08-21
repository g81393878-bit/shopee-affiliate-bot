# -*- coding: utf-8 -*-
"""เทสต์ robustness ของ LLM JSON handling — กัน model คืน JSON เละ/มี fence ครอบ.

- parse_llm_json(): ตัด ```json fence, กันข้อความแทรก, JSON เละ → raise ValueError
- groq_json_schema_format(): json_schema strict เฉพาะโมเดลที่รองรับ, json_object สำหรับอื่น
- generate_script_for_product: model คืน JSON มี fence/ข้อความแทรก → parse ได้ ไม่ fallback
- fallback ยังทำงานเมื่อ parse พังจริง (JSON เละจริง)
"""
import json

import pytest

from app.config import settings
from app.services.llm_clients import (
    CIRCUIT_COOLDOWN_SECONDS,
    CircuitOpenError,
    _GROQ_STRICT_JSON_MODELS,
    _circuit,
    _circuit_is_open,
    _circuit_record_failure,
    _circuit_record_success,
    call_with_backoff,
    groq_clients,
    groq_json_schema_format,
    parse_llm_json,
)
from app.services.ai_generator import SCRIPT_KEYS, generate_script_for_product


# ---------------------------------------------------------------------------
# parse_llm_json
# ---------------------------------------------------------------------------

def test_parse_llm_json_plain():
    assert parse_llm_json('{"a": 1}') == {"a": 1}


def test_parse_llm_json_with_markdown_fence():
    """โมเดลชอบครอบด้วย ```json ... ``` — ต้องตัดแล้ว parse ได้"""
    content = '```json\n{"hook": "สวัสดี", "hashtags": ["ของดี"]}\n```'
    data = parse_llm_json(content)
    assert data["hook"] == "สวัสดี"
    assert data["hashtags"] == ["ของดี"]


def test_parse_llm_json_fence_without_lang_tag():
    """fence แบบไม่มีภาษา (``` ... ```) ก็ต้องตัดได้"""
    assert parse_llm_json('```\n{"a": 2}\n```') == {"a": 2}


def test_parse_llm_json_with_surrounding_prose():
    """ข้อความแทรกหน้า/หลัง JSON (โมเดล reasoning ชอบทำ) — เอาเฉพาะบล็อก {...}"""
    content = 'ขออภัยครับ นี่คือผลลัพธ์: {"hook": "x"} ขอบคุณครับ'
    assert parse_llm_json(content) == {"hook": "x"}


def test_parse_llm_json_multiline_nested():
    """JSON ซ้อนหลายชั้น + ขึ้นบรรทัดใหม่ — ต้อง parse ได้ครบ"""
    content = '{"script": {"hook": "a", "tags": ["x", "y"]}, "n": 3}'
    data = parse_llm_json(content)
    assert data["script"]["tags"] == ["x", "y"]


def test_parse_llm_json_raises_on_garbage():
    with pytest.raises(ValueError):
        parse_llm_json("ไม่ใช่ JSON เลยแม้แต่น้อย")


def test_parse_llm_json_raises_on_empty():
    with pytest.raises(ValueError):
        parse_llm_json("   ")


def test_parse_llm_json_raises_on_non_string():
    with pytest.raises(ValueError):
        parse_llm_json({"dict": "ไม่ใช่ string"})


# ---------------------------------------------------------------------------
# groq_json_schema_format
# ---------------------------------------------------------------------------

def test_groq_json_schema_format_strict_on_supported_model():
    fmt = groq_json_schema_format({"type": "object"}, "openai/gpt-oss-120b")
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == {"type": "object"}


def test_groq_json_schema_format_falls_back_to_json_object():
    """โมเดลอื่น (ไม่รองรับ strict) ต้องได้ json_object — กัน 400 จาก Groq"""
    fmt = groq_json_schema_format({"type": "object"}, "llama-3.3-70b-versatile")
    assert fmt == {"type": "json_object"}


def test_groq_json_schema_format_empty_model_falls_back():
    assert groq_json_schema_format({"type": "object"}, "") == {"type": "json_object"}


# ---------------------------------------------------------------------------
# generate_script_for_product — โมเดลคืน JSON มี fence → ยัง parse ได้
# ---------------------------------------------------------------------------

class _FakeClient:
    """OpenAI-client ปลอมคืน content ตามที่ตั้งไว้ (ไม่แตะเน็ต)"""

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


def _full_script_json():
    return json.dumps({
        "hook": "หยุดก่อนจ๊ะ!", "problem": "พังง่าย", "solution": "ใช้ดี",
        "cta": "กดลิงก์", "caption": "ลองดูจ๊ะ", "hashtags": ["ของดี", "บอกต่อ"],
        "title": "ป้าป้ายยา", "thumbnail_prompt": "ภาพสินค้า",
    })


def test_generate_script_parses_fenced_json(monkeypatch):
    """Groq คืน JSON ครอบ ```json — ต้อง parse ได้ ไม่ fallback template"""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b")
    fenced = f"```json\n{_full_script_json()}\n```"
    fake = _FakeClient("gsk-test", fenced)
    monkeypatch.setattr("app.services.llm_clients.groq_clients", lambda: [fake])

    result = generate_script_for_product("หูฟังไร้สาย", "หูฟัง", 250, tone="neutral")
    assert result["hook"] == "หยุดก่อนจ๊ะ!"
    assert result["hashtags"] == ["ของดี", "บอกต่อ"]
    assert SCRIPT_KEYS.issubset(result)


def test_generate_script_parses_prose_wrapped_json(monkeypatch):
    """Groq คืน JSON มีข้อความแทรกหน้า/หลัง — ต้อง parse ได้ ไม่ fallback"""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b")
    wrapped = f"นี่คือสคริปต์จ้า: {_full_script_json()} จบครับ"
    fake = _FakeClient("gsk-test", wrapped)
    monkeypatch.setattr("app.services.llm_clients.groq_clients", lambda: [fake])

    result = generate_script_for_product("กระติกน้ำแข็ง", "แก้วน้ำ", 299, tone="neutral")
    assert result["hook"] == "หยุดก่อนจ๊ะ!"


# ---------------------------------------------------------------------------
# Circuit breaker + fail-fast (กัน key เสียถูกยิงซ้ำทุก call)
# ---------------------------------------------------------------------------

def _api_err(status_code, retry_after=None):
    exc = Exception(f"api error {status_code}")
    exc.status_code = status_code
    exc.response = None
    if retry_after is not None:
        exc.response = type("R", (), {"headers": {"retry-after": str(retry_after)}})()
    return exc


def test_circuit_opens_after_threshold_failures(monkeypatch):
    """ล้มติดกัน ≥ threshold → circuit เปิด; สำเร็จระหว่างทาง → รีเซ็ต"""
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    monkeypatch.setattr("app.services.llm_clients.time.monotonic", lambda: 1000.0)
    _circuit.clear()

    # ล้ม 1 ครั้ง (ยังไม่ถึง threshold 2) → ยังไม่เปิด
    def boom():
        raise _api_err(429)

    with pytest.raises(Exception):
        call_with_backoff(boom, attempts=1, circuit_key="key-a")
    assert not _circuit_is_open("key-a")

    # ล้มครั้งที่ 2 → เปิด circuit
    with pytest.raises(Exception):
        call_with_backoff(boom, attempts=1, circuit_key="key-a")
    assert _circuit_is_open("key-a")

    # เปิดแล้ว → raise CircuitOpenError ทันที ไม่ยิง fn
    calls = {"n": 0}

    def never_called():
        calls["n"] += 1
        return "ok"

    with pytest.raises(CircuitOpenError):
        call_with_backoff(never_called, circuit_key="key-a")
    assert calls["n"] == 0
    _circuit.clear()


def test_circuit_success_resets_failures():
    _circuit.clear()
    _circuit_record_failure("key-b")
    assert _circuit_is_open("key-b") is False  # 1 ครั้งยังไม่เปิด

    # สำเร็จ → ตัวนับรีเซ็ต
    def ok():
        return "ok"

    assert call_with_backoff(ok, circuit_key="key-b") == "ok"
    assert _circuit_is_open("key-b") is False
    _circuit.clear()


def test_circuit_auto_recovers_after_cooldown(monkeypatch):
    """cooldown หมด → circuit ปิดเอง (key กลับมาใช้ได้)"""
    _circuit.clear()
    now = [1000.0]
    monkeypatch.setattr("app.services.llm_clients.time.monotonic", lambda: now[0])

    _circuit_record_failure("key-c")
    _circuit_record_failure("key-c")
    assert _circuit_is_open("key-c")

    # ผ่าน cooldown ไปแล้ว → key กลับมา (auto-recover ลบ state ทิ้ง)
    now[0] += CIRCUIT_COOLDOWN_SECONDS + 1
    assert _circuit_is_open("key-c") is False
    assert not _circuit
    _circuit.clear()


def test_groq_clients_filters_open_circuit(monkeypatch):
    """key ที่ circuit เปิด ต้องถูกกรองออกจาก groq_clients()"""
    monkeypatch.setattr(settings, "GROQ_API_KEY", "key-1,key-2")
    _circuit.clear()
    _circuit_record_failure("key-1")
    _circuit_record_failure("key-1")
    assert _circuit_is_open("key-1")

    keys = [c.api_key for c in groq_clients()]
    assert "key-1" not in keys
    assert "key-2" in keys
    _circuit.clear()


def test_call_with_backoff_jitter_applies(monkeypatch):
    """jitter ±30% ใน exponential backoff (single-key mode) — ไม่ใช่ค่า exact"""
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "LLM_RETRY_BASE_DELAY", 2.0)
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_DELAY", 30.0)
    slept = []
    monkeypatch.setattr("app.services.llm_clients.time.sleep", slept.append)
    import random
    monkeypatch.setattr(random, "uniform", lambda lo, hi: 1.0)  # คงที่ = 2.0*1=2.0

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _api_err(500)
        return "ok"

    assert call_with_backoff(flaky) == "ok"
    assert slept == [2.0, 4.0]


def test_generate_script_validates_type_via_pydantic(monkeypatch):
    """hashtags มาเป็น string (type ผิด) → Pydantic reject → fallback template
    (เดิม _require_script_keys ตรวจแค่ key มี ไม่เห็น type ผิด → ส่ง string ต่อให้
    consumer ที่คาด list พังทีหลัง)"""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test")
    monkeypatch.setattr(settings, "GROQ_MODEL", "openai/gpt-oss-120b")
    bad = _full_script_json().replace('"hashtags": ["ของดี", "บอกต่อ"]', '"hashtags": "ของดี บอกต่อ"')
    fake = _FakeClient("gsk-test", bad)
    monkeypatch.setattr("app.services.llm_clients.groq_clients", lambda: [fake])

    result = generate_script_for_product("หูฟังไร้สาย", "หูฟัง", 250, tone="neutral")
    # fallback template — hashtags ต้องเป็น list เสมอ (ไม่ใช่ string ที่ consumer พัง)
    assert isinstance(result["hashtags"], list)
    assert SCRIPT_KEYS.issubset(result)
