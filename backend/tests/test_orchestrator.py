# -*- coding: utf-8 -*-
"""Regression tests สำหรับ orchestrator (Claude บอสสั่งการ → plan/dispatch/review).

mock worker ทั้ง 3 ตัว (_claude_generate/_groq_generate/_firecrawl_research) —
ไม่แตะเน็ต/API จริง ตรวจว่าโฟลว์ plan→dispatch→review + fallback ทำงานถูก
"""
import json

from app.services import orchestrator as orch

PLAN = json.dumps([
    {"worker": "firecrawl", "task": "ค้นเทรนด์สินค้า"},
    {"worker": "groq", "task": "เขียนสคริปต์ TikTok"},
    {"worker": "claude", "task": "ตรวจและเรียบเรียง"},
])


def test_extract_json_strips_fences_and_text():
    raw = 'นี่คือแผน\n```json\n[{"worker": "groq", "task": "เขียน"}]```\nหวังว่าดี'
    assert orch._extract_json(raw) == [{"worker": "groq", "task": "เขียน"}]


def test_extract_json_handles_dict_wrapper():
    raw = '{"steps": [{"worker": "groq", "task": "a"}]}'
    assert orch._extract_json(raw) == {"steps": [{"worker": "groq", "task": "a"}]}


def test_parse_plan_normalizes_and_filters():
    raw = json.dumps([
        {"worker": "firecrawl", "task": "หาเทรนด์"},
        {"worker": "บอส", "task": "worker ไม่รู้จัก → groq"},
        {"task": "ไม่มี worker → default groq"},
        {"worker": "groq", "task": ""},          # task ว่าง → ตัดทิ้ง
        "ไม่ใช่ dict",                              # item ไม่ใช่ dict → ตัดทิ้ง
    ])
    plan = orch._parse_plan(raw)
    assert plan == [
        {"worker": "firecrawl", "task": "หาเทรนด์"},
        {"worker": "groq", "task": "worker ไม่รู้จัก → groq"},
        {"worker": "groq", "task": "ไม่มี worker → default groq"},
    ]


def test_parse_plan_accepts_dict_wrapper():
    raw = '{"plan": [{"worker": "groq", "task": "x"}]}'
    assert orch._parse_plan(raw) == [{"worker": "groq", "task": "x"}]


def test_parse_plan_caps_steps_and_claude_quota():
    raw = json.dumps([
        {"worker": "claude", "task": "คิดลึก 1"},
        {"worker": "claude", "task": "คิดลึก 2"},
        {"worker": "claude", "task": "คิดลึก 3"},
        {"worker": "groq", "task": "ขั้น 4"},
        {"worker": "groq", "task": "ขั้น 5"},
        {"worker": "firecrawl", "task": "ขั้น 6"},
    ])
    plan = orch._parse_plan(raw)
    # cap 4 ขั้น + claude เหลือแค่ 1 (ที่เหลือโยนให้ groq)
    assert len(plan) == 4
    assert sum(1 for s in plan if s["worker"] == "claude") == 1


def _fake_claude(prompt, system=orch.BOSS_SYSTEM):
    if "วางแผน" in prompt:
        return PLAN
    return "คำตอบสุดท้ายจากบอส"


def test_boss_orchestrate_full_flow(monkeypatch):
    calls = {"groq": 0, "firecrawl": 0, "claude_review": 0}
    monkeypatch.setattr(orch, "_claude_generate", _fake_claude)

    def _groq(prompt):
        calls["groq"] += 1
        return "ร่าง Groq"

    def _firecrawl(q):
        calls["firecrawl"] += 1
        return "ข้อมูลรีเสิร์ช"

    monkeypatch.setattr(orch, "_groq_generate", _groq)
    monkeypatch.setattr(orch, "_firecrawl_research", _firecrawl)

    result = orch.boss_orchestrate("สร้างคอนเทนต์หูฟัง")
    assert result["boss"] is True
    assert result["answer"] == "คำตอบสุดท้ายจากบอส"
    assert [s["worker"] for s in result["steps"]] == ["firecrawl", "groq", "claude"]
    assert calls["firecrawl"] == 1 and calls["groq"] == 1


def test_boss_orchestrate_fallback_when_no_plan(monkeypatch):
    monkeypatch.setattr(orch, "_claude_generate", lambda p, s=orch.BOSS_SYSTEM: "ตอบมั่วไม่ใช่ JSON")
    monkeypatch.setattr(orch, "_groq_generate", lambda p: "Groq ตอบตรง")

    result = orch.boss_orchestrate("ถามอะไรสักอย่าง")
    assert result["boss"] is False
    assert result["answer"] == "Groq ตอบตรง"
    assert result["plan"] == [] and result["steps"] == []


def test_orchestrate_product_content_uses_boss(monkeypatch):
    monkeypatch.setattr(orch, "boss_orchestrate",
                        lambda instr: {"answer": "คอนเทนต์ชุด", "plan": [], "steps": [], "boss": True})
    r = orch.orchestrate_product_content("หูฟังไร้สาย", "หูฟัง", 250, 4.5, 5000, 10)
    assert r["answer"] == "คอนเทนต์ชุด"
    assert r["boss"] is True
