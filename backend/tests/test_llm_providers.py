# -*- coding: utf-8 -*-
"""Regression tests สำหรับ provider Anthropic (Claude) — กัน "บอสใหญ่" พังเมื่อเพิ่ม provider ใหม่.

- anthropic_keys() / anthropic_clients(): parse/กรอง/วน key + ชี้ base_url OpenAI-compat
- generate_script_for_product / analyze_product_with_ai: เดิน anthropic branch (mock client
  คืน JSON) แล้ว parse กลับเป็น schema ที่ถูกต้อง — ไม่ fallback ไป mock script
"""
import ast
import json
from pathlib import Path

import pytest

from app.config import settings
from app.services.llm_clients import (
    ANTHROPIC_BASE_URL,
    _min_interval_seconds,
    anthropic_clients,
    anthropic_keys,
    call_with_backoff,
    throttle_llm_request,
)
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


# ---------------------------------------------------------------------------
# Rate limiting + retry (กัน HTTP 429 เมื่อเรดาร์ยิงวิเคราะห์หลายโพสต์ติดกัน)
# ---------------------------------------------------------------------------

class _FakeApiError(Exception):
    """Exception ปลอมเลียนแบบ openai/httpx error — มี status_code + response.headers"""

    def __init__(self, status_code=429, retry_after=None):
        super().__init__(f"api error {status_code}")
        self.status_code = status_code
        self.response = None
        if retry_after is not None:
            self.response = type(
                "R", (), {"headers": {"retry-after": str(retry_after)}}
            )()


def test_call_with_backoff_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "LLM_RETRY_BASE_DELAY", 1.0)
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_DELAY", 30.0)
    monkeypatch.setattr("app.services.llm_clients.time.sleep", lambda s: None)

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeApiError(429)
        return "ok"

    assert call_with_backoff(flaky) == "ok"
    assert calls["n"] == 3


def test_call_with_backoff_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr("app.services.llm_clients.time.sleep", lambda s: None)

    calls = {"n": 0}

    def always_429():
        calls["n"] += 1
        raise _FakeApiError(429)

    with pytest.raises(_FakeApiError):
        call_with_backoff(always_429)
    assert calls["n"] == 2


def test_call_with_backoff_no_retry_on_auth_error(monkeypatch):
    """401/parse error ไม่ใช่ transient → ต้อง raise ทันที ไม่เสียเวลารอ"""
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr("app.services.llm_clients.time.sleep", lambda s: None)

    calls = {"n": 0}

    def auth_fail():
        calls["n"] += 1
        raise _FakeApiError(401)

    with pytest.raises(_FakeApiError):
        call_with_backoff(auth_fail)
    assert calls["n"] == 1


def test_call_with_backoff_honors_retry_after_header(monkeypatch):
    """ถ้า server ส่ง Retry-After ต้องรอตามค่านั้น ไม่ใช่ base*2^n"""
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    monkeypatch.setattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "LLM_RETRY_BASE_DELAY", 1.0)
    slept = []
    monkeypatch.setattr("app.services.llm_clients.time.sleep", slept.append)

    calls = {"n": 0}

    def with_retry_after():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _FakeApiError(429, retry_after=7)
        return "ok"

    assert call_with_backoff(with_retry_after) == "ok"
    assert slept == [7.0]


def test_throttle_disabled_when_rpm_zero(monkeypatch):
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    slept = []
    monkeypatch.setattr("app.services.llm_clients.time.sleep", slept.append)
    throttle_llm_request()
    assert slept == []


def test_min_interval_seconds_from_rpm(monkeypatch):
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 30)
    assert _min_interval_seconds() == 2.0
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    assert _min_interval_seconds() == 0.0


# ---------------------------------------------------------------------------
# Regression: ทุก LLM call ใน services ต้องห่อ call_with_backoff
# ---------------------------------------------------------------------------

SERVICES_DIR = Path(__file__).resolve().parent.parent / "app" / "services"


def _unwrapped_llm_calls(source_path: Path):
    """คืน list[(lineno, snippet)] ของ LLM call ที่ไม่อยู่ใน call_with_backoff(...).

    ใช้ ast (ไม่ใช่ grep) → จับเฉพาะโค้ดจริง กัน false positive จาก comment/docstring.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_llm_call = False
        if isinstance(func, ast.Attribute):
            if func.attr == "generate_content":
                is_llm_call = True
            elif func.attr == "create" and isinstance(func.value, ast.Attribute) and func.value.attr == "completions":
                is_llm_call = True
        if not is_llm_call:
            continue

        # เดินขึ้น ancestor: create/generate_content → lambda → call_with_backoff(...)
        wrapped = False
        p = parent.get(node)
        while p is not None:
            if isinstance(p, ast.Lambda):
                gp = parent.get(p)
                if isinstance(gp, ast.Call) and isinstance(gp.func, ast.Name) and gp.func.id == "call_with_backoff":
                    wrapped = True
                    break
            p = parent.get(p)
        if not wrapped:
            violations.append((node.lineno, ast.unparse(node).strip()[:70]))
    return violations


def test_all_service_llm_calls_wrapped_in_call_with_backoff():
    """Regression: ห้ามมี chat.completions.create / generate_content นอก call_with_backoff.

    ถ้ามีคนเพิ่ม LLM call ใหม่โดยไม่ห่อ retry/throttle → เทสต์นี้พังทันที.
    """
    py_files = sorted(SERVICES_DIR.glob("*.py"))
    assert py_files, f"ไม่พบไฟล์ .py ใน {SERVICES_DIR}"

    problems = {}
    for path in py_files:
        bad = _unwrapped_llm_calls(path)
        if bad:
            problems[path.name] = bad

    assert not problems, (
        "พบ LLM call ที่ไม่ห่อ call_with_backoff — ห่อก่อน commit:\n"
        + "\n".join(
            f"  {name}:{line}: {snippet}"
            for name, bad in problems.items()
            for line, snippet in bad
        )
    )
