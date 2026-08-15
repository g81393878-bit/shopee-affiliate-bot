# -*- coding: utf-8 -*-
"""เทสต์ Hermes AI learning loop — gather/merge/load+save + full flow (mock Groq).

ไม่แตะเน็ต: mock groq_clients ให้คืน JSON ตายตัว — ตรวจว่า analyze_market
อ่าน chat_logs/facebook_demand_events, เรียก LLM, clamp คะแนน และเขียน
system_preferences ถูกต้อง (timezone-aware ไม่ใช้ naive utcnow).
"""
import datetime
import json

import pytest

from app import models
from app.services.hermes_brain import (
    DEFAULT_SKILLS,
    HERMES_SKILLS_KEY,
    MAX_DEMAND_SCORE,
    MIN_DEMAND_SCORE,
    analyze_market,
    format_market_memory,
    gather_market_data,
    load_skills,
    merge_skills,
    save_skills,
)

UTC = datetime.timezone.utc


def _now_minus(hours: float) -> datetime.datetime:
    return datetime.datetime.now(UTC) - datetime.timedelta(hours=hours)


@pytest.fixture()
def clean_prefs(db):
    """db fixture ล้าง chat/demand แล้ว แต่ไม่ล้าง SystemPreference — ล้างเอง."""
    db.query(models.SystemPreference).delete()
    db.commit()
    yield db


def _add_chat(db, category: str, hours_ago: float = 1.0) -> None:
    db.add(models.ChatLog(
        line_user_id="U_test",
        message_text="อยากได้ของ",
        intent="search",
        category=category,
        reply_kind="text",
        created_at=_now_minus(hours_ago),
    ))
    db.commit()


def _add_demand(db, keyword: str, urgency: str = "low", hours_ago: float = 1.0) -> None:
    lead = models.FacebookDetectedLead(
        fb_post_id=f"fb_{keyword}_{hours_ago}",
        post_url=f"https://fb.com/{keyword}",
        post_text=f"หา {keyword} ครับ",
        detected_at=_now_minus(hours_ago),
    )
    db.add(lead)
    db.commit()
    db.add(models.FacebookDemandEvent(
        lead_id=lead.id,
        intent="buy_request",
        demand_score=80,
        urgency=urgency,
        product_keyword=keyword,
        created_at=_now_minus(hours_ago),
    ))
    db.commit()


class _FakeClient:
    """OpenAI-client ปลอมคืน JSON ตายตัว (ไม่แตะเน็ต)."""

    def __init__(self, content: str):
        self.api_key = "fake-key"
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


def test_gather_market_data_aggregates_recent_only(clean_prefs):
    _add_chat(clean_prefs, "หูฟัง", hours_ago=1)
    _add_chat(clean_prefs, "หูฟัง", hours_ago=2)
    _add_chat(clean_prefs, "หม้อหุงข้าว", hours_ago=72)  # เก่าเกิน 48h → ไม่นับ
    _add_demand(clean_prefs, "ชุดคลุมท้อง", urgency="high", hours_ago=3)
    _add_demand(clean_prefs, "หูฟัง", urgency="low", hours_ago=5)

    report = gather_market_data(clean_prefs, hours=48)
    assert report["chat_count"] == 2
    assert report["chat_categories_requested"] == {"หูฟัง": 2}
    assert report["facebook_demand_count"] == 2
    assert report["high_urgency_demands"] == 1
    assert report["facebook_demand_keywords"]["ชุดคลุมท้อง"] == 1


def test_merge_skills_clamps_low_score(clean_prefs):
    llm = {
        "trending_categories": ["หูฟัง", "แก้วน้ำ"],
        "radar_min_demand_score": 5,  # ต่ำกว่า MIN → clamp 50
        "pa_khem_tone": "เน้นความคุ้มค่า ของถูก",
    }
    out = merge_skills(DEFAULT_SKILLS, llm)
    assert out["trending_categories"] == ["หูฟัง", "แก้วน้ำ"]
    assert out["radar_min_demand_score"] == MIN_DEMAND_SCORE
    assert out["pa_khem_tone"] == "เน้นความคุ้มค่า ของถูก"


def test_merge_skills_clamps_high_and_keeps_defaults(clean_prefs):
    llm = {"radar_min_demand_score": 999}
    out = merge_skills(DEFAULT_SKILLS, llm)
    assert out["radar_min_demand_score"] == MAX_DEMAND_SCORE
    # ฟิลด์ที่ LLM ไม่ส่ง → คง default
    assert out["trending_categories"] == DEFAULT_SKILLS["trending_categories"]
    assert out["radar_daily_post_limit"] == DEFAULT_SKILLS["radar_daily_post_limit"]


def test_save_and_load_skills_roundtrip(clean_prefs):
    save_skills(clean_prefs, {"radar_min_demand_score": 60, "pa_khem_tone": "กระชับ"})
    loaded = load_skills(clean_prefs)
    assert loaded["radar_min_demand_score"] == 60
    assert loaded["pa_khem_tone"] == "กระชับ"
    # คีย์ที่ไม่ได้บันทึก → ใช้ default
    assert loaded["radar_daily_post_limit"] == DEFAULT_SKILLS["radar_daily_post_limit"]
    # save ทับ (upsert ไม่เพิ่มแถว)
    save_skills(clean_prefs, {"radar_min_demand_score": 65})
    count = (clean_prefs.query(models.SystemPreference)
               .filter(models.SystemPreference.key == HERMES_SKILLS_KEY).count())
    assert count == 1


def test_analyze_market_full_flow(clean_prefs, monkeypatch):
    _add_chat(clean_prefs, "หูฟัง", hours_ago=1)
    _add_demand(clean_prefs, "หูฟัง", urgency="high", hours_ago=1)

    llm_json = json.dumps({
        "trending_categories": ["หูฟัง"],
        "radar_min_demand_score": 65,
        "pa_khem_tone": "เน้นความคุ้มค่า",
        "reason": "ช่วงนี้คนถามหูฟังเยอะ",
    }, ensure_ascii=False)
    monkeypatch.setattr(
        "app.services.hermes_brain.groq_clients", lambda: [_FakeClient(llm_json)])

    result = analyze_market(clean_prefs)
    assert result is not None
    assert result["skills"]["trending_categories"] == ["หูฟัง"]
    assert result["skills"]["radar_min_demand_score"] == 65
    assert result["skills"]["pa_khem_tone"] == "เน้นความคุ้มค่า"
    assert result["reason"] == "ช่วงนี้คนถามหูฟังเยอะ"

    saved = (clean_prefs.query(models.SystemPreference)
               .filter(models.SystemPreference.key == HERMES_SKILLS_KEY).first())
    assert saved is not None
    assert saved.value["trending_categories"] == ["หูฟัง"]


def test_analyze_market_returns_none_when_llm_fails(clean_prefs, monkeypatch):
    # ไม่มี Groq key → _call_llm คืน None → ไม่เขียนทับ skills เดิม
    monkeypatch.setattr("app.services.hermes_brain.groq_clients", lambda: [])
    assert analyze_market(clean_prefs) is None


def test_format_market_memory_contains_skills(clean_prefs):
    result = {
        "skills": {"radar_min_demand_score": 65, "trending_categories": ["หูฟัง"]},
        "report": {"chat_count": 3, "chat_categories_requested": {"หูฟัง": 3},
                   "facebook_demand_count": 1, "high_urgency_demands": 0},
        "reason": "test",
    }
    md = format_market_memory(result)
    assert "หูฟัง" in md
    assert '"radar_min_demand_score": 65' in md


def test_cron_hermes_learn_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.cron as cron

    fake_result = {
        "skills": {"trending_categories": ["หูฟัง"], "radar_min_demand_score": 65},
        "report": {"chat_count": 2, "facebook_demand_count": 1},
        "reason": "test",
    }
    monkeypatch.setattr(cron, "_authorized", lambda t: True)
    monkeypatch.setattr(cron, "analyze_market", lambda db: fake_result)
    client = TestClient(app)
    r = client.post("/api/cron/hermes-learn")
    assert r.status_code == 200
    body = r.json()
    assert body["learned"] is True
    assert body["skills"]["trending_categories"] == ["หูฟัง"]
    assert body["reason"] == "test"


def test_cron_hermes_learn_requires_token(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.cron as cron

    monkeypatch.setattr(cron, "_authorized", lambda t: False)
    client = TestClient(app)
    r = client.post("/api/cron/hermes-learn", params={"token": "wrong"})
    assert r.status_code == 401


def test_cron_hermes_learn_returns_learned_false_when_llm_fails(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.cron as cron

    monkeypatch.setattr(cron, "_authorized", lambda t: True)
    monkeypatch.setattr(cron, "analyze_market", lambda db: None)
    client = TestClient(app)
    r = client.post("/api/cron/hermes-learn")
    assert r.status_code == 200
    assert r.json()["learned"] is False
