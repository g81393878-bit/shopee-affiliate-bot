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
    load_skills_safe,
    market_emphasis,
    market_emphasis_for,
    market_tone,
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
    # radar_daily_post_limit ไม่อยู่ใน DEFAULT → ต้องหายไป (ให้ radar ใช้ env เดิม)
    assert "radar_daily_post_limit" not in out


def test_merge_skills_strips_radar_daily_post_limit_even_if_stored(clean_prefs):
    # แม้ stored skills เก่ายังมี radar_daily_post_limit (จากรุ่นก่อน) → merge ต้องถอดทิ้ง
    # ไม่งั้น Hermes จะเก็บค่าโควต้าโพสต์ไว้แล้วทับ env RADAR_MAX_DAILY_POSTS
    stored = dict(DEFAULT_SKILLS)
    stored["radar_daily_post_limit"] = 25
    out = merge_skills(stored, {"radar_min_demand_score": 70})
    assert "radar_daily_post_limit" not in out
    assert out["radar_min_demand_score"] == 70


def test_save_and_load_skills_roundtrip(clean_prefs):
    save_skills(clean_prefs, {"radar_min_demand_score": 60, "pa_khem_tone": "กระชับ"})
    loaded = load_skills(clean_prefs)
    assert loaded["radar_min_demand_score"] == 60
    assert loaded["pa_khem_tone"] == "กระชับ"
    # radar_daily_post_limit ไม่อยู่ใน DEFAULT → ไม่มีคีย์นี้ (ให้ radar ใช้ env เดิม)
    assert "radar_daily_post_limit" not in loaded
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


# --- M3: hot-reload เข้า LINE bot + cron analyze + persona ---

def test_market_tone_returns_saved_tone(clean_prefs):
    save_skills(clean_prefs, {"pa_khem_tone": "เน้นความคุ้มค่า ของถูก"})
    assert market_tone(clean_prefs) == "เน้นความคุ้มค่า ของถูก"


def test_market_tone_returns_default_when_missing(clean_prefs):
    assert market_tone(clean_prefs) == DEFAULT_SKILLS["pa_khem_tone"]


def test_default_skills_has_no_radar_daily_post_limit(clean_prefs):
    # radar_daily_post_limit ต้องไม่อยู่ใน default — ไม่งั้น Hermes จะไปทับ env
    # RADAR_MAX_DAILY_POSTS ที่แอดมินตั้งไว้โดยไม่ได้ตั้งใจ (เรดาร์ต้อง fallback env)
    assert "radar_daily_post_limit" not in DEFAULT_SKILLS
    assert "radar_daily_post_limit" not in load_skills_safe(clean_prefs)


def test_load_skills_safe_falls_back_when_table_missing(clean_prefs, monkeypatch):
    def boom(db):
        raise RuntimeError("relation 'system_preferences' does not exist")

    monkeypatch.setattr("app.services.hermes_brain.load_skills", boom)
    assert load_skills_safe(clean_prefs) == DEFAULT_SKILLS
    # market_tone ก็ต้องไม่ crash ต่อด้วย (ใช้ load_skills_safe ภายใน)
    assert market_tone(clean_prefs) == DEFAULT_SKILLS["pa_khem_tone"]


def test_trending_boost_puts_trending_first():
    import app.api.line_bot as lb

    P = type("P", (), {})
    prods = [P(), P(), P(), P()]
    prods[0].category = "หูฟัง"
    prods[1].category = "แก้วน้ำ"
    prods[2].category = "พัดลม"
    prods[3].category = "หูฟัง"
    out = lb._trending_boost(prods, ["พัดลม", "หูฟัง"])
    # หมวดมาแรงขึ้นก่อนตามลำดับใน trending; หมวดอื่น (แก้วน้ำ) คงตามหลัง
    assert [p.category for p in out] == ["พัดลม", "หูฟัง", "หูฟัง", "แก้วน้ำ"]


def test_trending_boost_noop_when_no_trending():
    import app.api.line_bot as lb

    P = type("P", (), {})
    prods = [P(), P()]
    prods[0].category = "หูฟัง"
    prods[1].category = "แก้วน้ำ"
    assert lb._trending_boost(prods, []) == prods
    assert lb._trending_boost(prods, None) == prods


def test_persona_injects_market_tone_only_when_set():
    from app.services.persona import persona_system_prompt

    with_tone = persona_system_prompt(market_tone="เน้นความคุ้มค่า ของถูก")
    assert "MARKET CONTEXT" in with_tone
    assert "เน้นความคุ้มค่า ของถูก" in with_tone
    # ไม่มี market_tone → ไม่มี section MARKET CONTEXT (พฤติกรรมเดิมไม่เปลี่ยน)
    without_tone = persona_system_prompt()
    assert "MARKET CONTEXT" not in without_tone


def test_market_emphasis_for_default_is_empty():
    assert market_emphasis_for(DEFAULT_SKILLS["pa_khem_tone"]) == ""
    assert market_emphasis_for("") == ""
    assert market_emphasis_for(None) == ""


def test_market_emphasis_for_value_tone():
    out = market_emphasis_for("เน้นความคุ้มค่า ของถูก")
    assert out != ""
    assert "คุ้ม" in out


def test_market_emphasis_for_caring_tone():
    out = market_emphasis_for("ใจดี ให้คำปรึกษา")
    assert out != ""
    assert "ละเอียด" in out


def test_market_emphasis_for_unknown_tone_is_empty():
    # LLM คืนโทนที่ไม่รู้จัก → ไม่ฉีดอะไรเข้าห้องลูกค้า (กันข้อความแปลก)
    assert market_emphasis_for("มั่ว ๆ ไม่รู้จัก xyz") == ""


def test_greeting_appends_market_emphasis_when_learned(clean_prefs, sim):
    save_skills(clean_prefs, {"pa_khem_tone": "เน้นความคุ้มค่า ของถูก"})
    r = sim.send("U_cust", "สวัสดี")
    assert r["intent"] == "greeting"
    assert "เน้นของคุ้ม" in r["preview"]


def test_greeting_has_no_emphasis_when_default(clean_prefs, sim):
    r = sim.send("U_cust", "สวัสดี")
    assert r["intent"] == "greeting"
    assert "เน้นของคุ้ม" not in r["preview"]
    assert "ใส่ใจเป็นพิเศษ" not in r["preview"]
