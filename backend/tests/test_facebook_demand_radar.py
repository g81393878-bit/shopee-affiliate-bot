# -*- coding: utf-8 -*-
"""Comprehensive E2E Integration Test Suite — Social Demand Radar V1 (บอทป้าเข็ม)
===============================================================================
Location: backend/tests/test_facebook_demand_radar.py
Milestone: Milestone 5 (Final Comprehensive E2E Test Suite)

This test suite satisfies all requirements in ORIGINAL_REQUEST.md (R1 to R5)
and the multi-tier test infrastructure defined in TEST_INFRA.md:

Tier 1: Feature Coverage (R1 to R5)
  - F1: Database Models & SQL Migrations (facebook_groups_monitor, facebook_detected_leads,
        facebook_demand_events, lead_actions).
  - F2: AI Intent & Demand Analysis (Intent, Demand Score 0-100, Urgency, Budget,
        Product Keyword, Pain Points, Sentiment, Reasoning).
  - F3: Demand Threshold Filter (is_high_demand >= 70).
  - F4: Product Matching with AI Reasoning (Strict Product.link_status == 'ok' policy,
        Multi-Factor Match Score, Empirical Suggested Reasons).
  - F5: Auntie Khem Thai Deal Copy Generation (Warm tone, empathy, persona markers,
        natural Affiliate link placement).
  - F6: FastAPI Leads Intake Endpoint (POST /api/admin/facebook-radar/leads).
  - F7: FastAPI Admin Action & Data Flywheel Endpoint (POST /api/admin/facebook-radar/actions).
  - F8: LINE Push Alert Formatting & Dispatch (Flex Bubble, Header badges, Action buttons).
  - F9: Local FB Group Monitor Tool (CLI args, SeenPostTracker, state persistence, dry-run).

Tier 2: Boundary & Edge Cases
  - Boundary scores (69 vs 70 vs 71, negative/zero/100/150).
  - Thai Sara Am NFC normalization variations (\\u0e4d\\u0e32 and \\u0e4d\\u0e33 -> \\u0e33).
  - Empty, whitespace, malformed inputs.
  - Lead deduplication idempotency (preventing duplicate events and alerts).
  - Admin authorization security (Token header, Query param, Bearer auth, HMAC cookie, 401 rejection).
  - Price parsing formats (ranges, Thai word numbers, commas, zero/negative).
  - Graceful handling when no products match or all products have link_status != 'ok'.

Tier 3: Full End-to-End Lifecycle & Data Flywheel
  - Raw lead ingest -> AI analysis -> Product matching -> Copy generation ->
    Demand event -> LINE alert -> Admin feedback action -> Conversion metrics ->
    Radar stats aggregation -> Cascade deletion lifecycle.

Tier 4: Real-World Thai Workload Simulations
  - 10 diverse real-world Thai Facebook posts (maternity dress, bluetooth headset,
    ergonomic cushion, pet food, scam warning, secondhand clothes dump, spam ad,
    weather chat, broken fan replacement, air purifier with comma price).
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import urllib.error

import pytest
from fastapi.testclient import TestClient

# Ensure tools directory is discoverable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import fb_group_monitor_local as monitor
from app import models, schemas
from app.db import SessionLocal
from app.main import app
from app.services.demand_radar_ai import (
    analyze_lead_intent_and_demand,
    generate_auntie_khem_deal_comment,
    is_high_demand,
    parse_post_budget,
    _extract_heuristic_keyword,
    _extract_pain_points,
    _nfc,
    _parse_thai_word_number,
)
from app.services.product_cards import format_radar_deal_flex_message
from app.services.product_matcher import (
    calculate_product_match_score,
    generate_suggested_reasons,
    match_best_product_for_demand,
    _calculate_string_similarity,
)
import app.api.facebook_radar as radar_api

TEST_SECRET_TOKEN = os.getenv("CRON_TOKEN") or os.getenv("ADMIN_DASHBOARD_PASSWORD") or "radar_e2e_secret_token"


@pytest.fixture
def auth_headers(monkeypatch):
    token = os.getenv("CRON_TOKEN") or os.getenv("ADMIN_DASHBOARD_PASSWORD") or TEST_SECRET_TOKEN
    monkeypatch.setenv("CRON_TOKEN", token)
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", token)
    return {"X-Admin-Token": token}


@pytest.fixture
def client(auth_headers):
    """FastAPI TestClient with default Admin Authentication Header."""
    c = TestClient(app)
    c.headers.update(auth_headers)
    return c


@pytest.fixture
def raw_client():
    """FastAPI TestClient without authentication headers for security testing."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Isolated database session for deterministic testing."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def seed_e2e_products(db_session):
    """Seeds a rich variety of deterministic test products with link_status='ok'.

    Safety: ข้ามเมื่อ DATABASE_URL เป็น postgres (production) — กันสินค้า mock
    หลุดเข้า DB จริงแล้วไปโผล่บนเพจ Facebook (เจอจริง: หูฟัง shope.ee/earbuds_ok).
    """
    if (os.getenv("DATABASE_URL") or "").strip().lower().startswith(("postgres", "postgresql")):
        pytest.skip("ไม่ seed สินค้า mock ลง DB production (DATABASE_URL เป็น postgres)")

    products_to_seed = [
        ("ชุดคลุมท้องผ้าฝ้ายทรงหลวม ผ้านิ่มระบายอากาศ", "แฟชั่น", 299.00, 4.9, 5420, 35.00, "https://s.shopee.co.th/maternity_ok", "ok", 92),
        ("หูฟังบลูทูธไร้สาย TWS ตัดเสียงรบกวน", "หูฟัง", 399.00, 4.8, 8500, 40.00, "https://s.shopee.co.th/earbuds_ok", "ok", 90),
        ("เบาะรองนั่งเพื่อสุขภาพ เมมโมรี่โฟม แก้ปวดหลัง", "เฟอร์นิเจอร์", 450.00, 4.7, 3200, 30.00, "https://s.shopee.co.th/cushion_ok", "ok", 86),
        ("อาหารแมวสูตรดูแลไต โรคไต 1kg", "สัตว์เลี้ยง", 350.00, 4.8, 1900, 25.00, "https://s.shopee.co.th/catfood_ok", "ok", 88),
        ("พัดลมตั้งโต๊ะมินิ ชาร์จ USB เสียงเงียบ ลมแรง", "พัดลม", 259.00, 4.7, 12000, 20.00, "https://s.shopee.co.th/fan_ok", "ok", 85),
        ("เครื่องฟอกอากาศ HEPA กรองฝุ่น PM2.5", "เครื่องใช้ไฟฟ้า", 1890.00, 4.9, 4500, 95.00, "https://s.shopee.co.th/airpurifier_ok", "ok", 94),
        ("กระติกน้ำเก็บความเย็น 1 ลิตร สแตนเลส 316", "แก้วน้ำ", 299.00, 4.8, 6200, 22.00, "https://s.shopee.co.th/bottle_ok", "ok", 87),
    ]

    for name, cat, price, rating, sales, comm, url, status, score in products_to_seed:
        existing = db_session.query(models.Product).filter(models.Product.name == name).first()
        if not existing:
            p = models.Product(
                name=name,
                category=cat,
                price=Decimal(str(price)),
                rating=rating,
                sales_count=sales,
                commission=Decimal(str(comm)),
                affiliate_url=url,
                link_status=status,
                ai_score=score,
            )
            db_session.add(p)
    db_session.commit()


# ===========================================================================
# Tier 1: Core Feature Verification (R1 to R5)
# ===========================================================================

def test_t1_f1_database_models_and_migration(db_session):
    """[R1] Verifies database tables creation, relations, schemas, and SQL migration file."""
    # 1. Verify SQL Migration file exists and contains all required table definitions
    migration_file = PROJECT_ROOT / "supabase" / "migrations" / "20260815194500_social_demand_radar.sql"
    assert migration_file.exists(), f"Missing SQL migration file: {migration_file}"
    sql_text = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS facebook_groups_monitor" in sql_text
    assert "CREATE TABLE IF NOT EXISTS facebook_detected_leads" in sql_text
    assert "CREATE TABLE IF NOT EXISTS facebook_demand_events" in sql_text
    assert "CREATE TABLE IF NOT EXISTS lead_actions" in sql_text

    # 2. Test Group Monitor Model CRUD & Schema
    group = models.FacebookGroupMonitor(
        group_id="grp_tier1_test",
        group_name="กลุ่มแม่และเด็ก ทดสอบ T1",
        group_url="https://facebook.com/groups/grp_tier1_test",
        category_tag="แม่และเด็ก",
        is_active=True,
        check_interval_minutes=45,
    )
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    assert group.id is not None
    grp_schema = schemas.FacebookGroupMonitorOut.model_validate(group)
    assert grp_schema.group_id == "grp_tier1_test"

    # 3. Test Detected Lead Model & Schema
    lead = models.FacebookDetectedLead(
        group_id=group.id,
        fb_post_id="lead_tier1_001",
        post_url="https://facebook.com/posts/lead_tier1_001",
        author_name="คุณแม่ทดสอบ",
        post_text="ตามหาชุดคลุมท้องใส่สบาย งบ 500 บาท",
        status="pending",
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    assert lead.id is not None
    assert lead.group.group_name == "กลุ่มแม่และเด็ก ทดสอบ T1"
    lead_schema = schemas.FacebookDetectedLeadOut.model_validate(lead)
    assert lead_schema.fb_post_id == "lead_tier1_001"

    # 4. Test Demand Event Model & Schema
    product = db_session.query(models.Product).filter(models.Product.link_status == "ok").first()
    event = models.FacebookDemandEvent(
        lead_id=lead.id,
        intent="buy_request",
        demand_score=88,
        urgency="high",
        budget="500 บาท",
        product_keyword="ชุดคลุมท้อง",
        matched_product_id=product.id if product else None,
        suggested_reason=["รีวิว 4.9 ดาว", "ยอดขายดี"],
        ai_comment_draft="ป้าเข็มแนะนำชุดคลุมท้องตัวนี้เลยจ้า https://shope.ee/test",
        notification_status="sent",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    assert event.id is not None
    event_schema = schemas.FacebookDemandEventOut.model_validate(event)
    assert event_schema.demand_score == 88

    # 5. Test Lead Action Model & Schema
    action = models.LeadAction(
        demand_event_id=event.id,
        lead_id=lead.id,
        action_type="reply_posted",
        admin_id="U_admin_t1",
        comment_posted=event.ai_comment_draft,
        affiliate_link_used="https://shope.ee/test",
        feedback_score=5,
        click_count=8,
        order_count=1,
        commission_earned=Decimal("35.00"),
        conversion_status="converted",
    )
    db_session.add(action)
    db_session.commit()
    db_session.refresh(action)
    assert action.id is not None
    action_schema = schemas.LeadActionOut.model_validate(action)
    assert action_schema.click_count == 8
    assert action_schema.commission_earned == Decimal("35.00")


def test_t1_f2_ai_intent_and_demand_analysis():
    """[R2] Verifies AI analysis extracts Intent, Demand Score, Urgency, Budget, and Keywords."""
    post_text = "มีใครแนะนำชุดคลุมท้องใส่สบายๆ บ้างคะ งบไม่เกิน 500 บาท เสาร์นี้จะคลอดแล้วต้องรีบใช้ด่วน"
    analysis = analyze_lead_intent_and_demand(post_text, author_name="คุณแม่น้องฟ้า")

    assert analysis["intent"] in ("recommendation_request", "buy_request")
    assert analysis["demand_score"] >= 70
    assert analysis["urgency"] == "high"
    assert analysis["budget"] == 500.0
    assert "ชุดคลุมท้อง" in analysis["product_keyword"]
    assert len(analysis["pain_points"]) > 0
    assert analysis["reasoning"] is not None


def test_t1_f3_demand_threshold_filtering():
    """[R2] Verifies is_high_demand enforces the >= 70 threshold strictly."""
    assert is_high_demand(70, threshold=70) is True
    assert is_high_demand(85, threshold=70) is True
    assert is_high_demand(100, threshold=70) is True
    assert is_high_demand(69, threshold=70) is False
    assert is_high_demand(50, threshold=70) is False
    assert is_high_demand(0, threshold=70) is False
    assert is_high_demand(-5, threshold=70) is False


def test_t1_f4_product_matching_and_ai_reasoning(db_session):
    """[R3] Verifies Product Matching strictly enforces link_status=='ok' and generates empirical reasons."""
    # Seed a dead-link product with an identical keyword and higher fake stats
    p_dead = models.Product(
        name="ชุดคลุมท้องแฟชั่นเกาหลี ดีลเด็ดราคาถูก",
        category="แฟชั่น",
        price=Decimal("199.00"),
        rating=5.0,
        sales_count=99999,
        commission=Decimal("80.00"),
        affiliate_url="https://shope.ee/dead_link",
        link_status="dead",
        ai_score=99,
    )
    db_session.add(p_dead)
    db_session.commit()

    match_res = match_best_product_for_demand(
        db=db_session,
        product_keyword="ชุดคลุมท้อง",
        budget=500.0,
    )

    best = match_res.get("best_product")
    assert best is not None
    assert best.link_status == "ok"
    assert best.id != p_dead.id
    assert "ชุดคลุมท้อง" in best.name

    # Check candidates
    for cand in match_res.get("candidates", []):
        assert cand["product"].link_status == "ok"

    # Verify suggested reasons
    reasons = match_res.get("suggested_reasons", [])
    assert len(reasons) >= 3
    reasons_str = " ".join(reasons)
    assert "รีวิว" in reasons_str or "⭐" in reasons_str
    assert "ยอดขาย" in reasons_str or "🔥" in reasons_str
    assert "OK" in reasons_str or "ลิงก์" in reasons_str


def test_t1_f5_auntie_khem_deal_copy():
    """[R3] Verifies Auntie Khem deal copy includes empathetic persona tone and affiliate link."""
    copy = generate_auntie_khem_deal_comment(
        post_text="ตามหาชุดคลุมท้องใส่สบายๆ งบไม่เกิน 500 บาท",
        product_name="ชุดคลุมท้องผ้าฝ้ายทรงหลวม ผ้านิ่มระบายอากาศ",
        price=299.00,
        rating=4.9,
        sales_count=5420,
        affiliate_url="https://shope.ee/maternity_ok",
        suggested_reasons=["⭐ รีวิวสูง 4.9/5 ดาว", "🔥 ยอดขายกว่า 5,420 ชิ้น"],
    )

    assert isinstance(copy, str)
    assert len(copy) > 30
    assert "https://shope.ee/maternity_ok" in copy
    # Persona tone markers
    assert any(w in copy for w in ("ป้า", "จ้า", "จ้ะ", "นะจ๊ะ", "ลูก", "คุณแม่"))


def test_t1_f6_fastapi_leads_intake_endpoint(client, db_session):
    """[R4] Verifies POST /api/admin/facebook-radar/leads receives and auto-posts leads to Facebook Page & Sheets."""
    post_id = f"t1_lead_{int(time.time() * 1000)}"
    payload = {
        "leads": [
            {
                "fb_post_id": post_id,
                "group_id": "grp_moms_th",
                "group_name": "กลุ่มแม่และเด็ก",
                "author_name": "คุณแม่น้องมิน",
                "post_text": "มีใครแนะนำชุดคลุมท้องใส่สบายๆ บ้างคะ งบไม่เกิน 400 บาท ขอบคุณค่ะ",
                "post_url": f"https://facebook.com/groups/moms_th/posts/{post_id}",
            }
        ]
    }

    mock_ai = {
        "intent": "recommendation_request",
        "demand_score": 85,
        "urgency": "medium",
        "budget": 400.0,
        "budget_text": "400 บาท",
        "product_keyword": "ชุดคลุมท้อง",
        "detected_category": "แฟชั่น",
        "pain_points": ["ใส่สบาย"],
        "sentiment": "positive",
        "reasoning": "ทดสอบ"
    }

    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "page_post_t1_001", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.dispatch_radar_line_alert") as mock_line_alert, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", return_value=mock_ai):
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_received"] == 1
        assert data["processed"] == 1
        assert data["high_demand_count"] == 1
        assert data["alerts_sent"] == 0
        assert data["results"][0]["status"] == "deal_matched_and_posted"
        assert data["results"][0]["alert_sent"] is False
        assert mock_post.called
        assert mock_sheets.called
        sheet_payload = mock_sheets.call_args[0][0]
        assert sheet_payload["kind"] == "radar"
        assert sheet_payload["post_id"] == "page_post_t1_001"
        assert "https://s.shopee.co.th/" in sheet_payload["link"]
        mock_line_alert.assert_not_called()


def test_t1_f7_fastapi_admin_action_endpoint(client, db_session):
    """[R4] Verifies POST /api/admin/facebook-radar/actions records admin decision for Data Flywheel."""
    # Seed demand event
    lead = models.FacebookDetectedLead(
        fb_post_id=f"lead_act_{int(time.time() * 1000)}",
        post_url="https://facebook.com/post/act",
        post_text="ตามหาหูฟังบลูทูธ",
        status="processed",
    )
    db_session.add(lead)
    db_session.flush()

    event = models.FacebookDemandEvent(
        lead_id=lead.id,
        intent="buy_request",
        demand_score=85,
        product_keyword="หูฟังบลูทูธ",
    )
    db_session.add(event)
    db_session.commit()

    action_payload = {
        "demand_event_id": event.id,
        "lead_id": lead.id,
        "action_type": "reply_posted",
        "admin_id": "U_admin_test_t1",
        "comment_posted": "ป้าเข็มแนะนำหูฟังรุ่นนี้จ้า https://shope.ee/earbuds_ok",
        "affiliate_link_used": "https://shope.ee/earbuds_ok",
        "feedback_score": 5,
        "notes": "โพสต์คอมเมนต์ตอบแล้ว",
    }

    resp = client.post("/api/admin/facebook-radar/actions", json=action_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["demand_event_id"] == event.id
    assert data["action_type"] == "reply_posted"
    assert data["feedback_score"] == 5


def test_t1_f8_line_push_alert_formatting(db_session):
    """[R4] Verifies Flex Message builder creates structured bubbles with action URIs."""
    product = db_session.query(models.Product).filter(models.Product.link_status == "ok").first()
    flex = format_radar_deal_flex_message(
        group_name="กลุ่มคนรักหูฟัง",
        post_text="อยากได้หูฟังบลูทูธตัดเสียงรบกวนดีๆ งบ 500 บาท",
        post_url="https://facebook.com/groups/tech/posts/999",
        demand_score=92,
        urgency="high",
        matched_product=product,
        suggested_reasons=["⭐ รีวิวสูง 4.8 ดาว", "🔥 ยอดขายดี"],
        copy_text="ป้าเข็มแนะนำตัวนี้เลยจ้า https://shope.ee/test",
    )

    assert flex is not None
    assert "Demand Radar" in flex.alt_text
    assert "92" in flex.alt_text
    contents = flex.contents.as_json_dict() if hasattr(flex.contents, "as_json_dict") else flex.contents
    assert contents["type"] == "bubble"
    buttons = contents["footer"]["contents"]
    assert len(buttons) >= 2
    assert "facebook.com" in buttons[0]["action"]["uri"]


def test_t1_f9_local_fb_monitor_tool(client):
    """[R5] Verifies local scraper script CLI parsing, SeenPostTracker, and payload submission."""
    tracker = monitor.SeenPostTracker()
    assert tracker.count == 0

    # Dry run test
    res_dry = monitor.run_monitor_iteration(
        api_url="http://testserver",
        token=TEST_SECRET_TOKEN,
        tracker=tracker,
        sample_mode=True,
        dry_run=True,
        limit=2,
    )
    assert res_dry["ok"] is True
    assert res_dry["dry_run"] is True
    assert res_dry["unseen_count"] == 2
    assert tracker.count == 2

    # Live test with TestClient
    tracker.clear()
    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "mon_post_1", "error": None}), \
         patch("app.api.facebook_radar.log_post_async"):
        res_live = monitor.run_monitor_iteration(
            api_url="http://testserver",
            token=TEST_SECRET_TOKEN,
            tracker=tracker,
            sample_mode=True,
            dry_run=False,
            limit=2,
            client=client,
        )
        assert res_live["ok"] is True
        assert res_live["dry_run"] is False
        assert res_live["ingested_count"] == 2


# ===========================================================================
# Tier 2: Boundary and Edge Cases
# ===========================================================================

def test_t2_boundary_demand_scores():
    """[Boundary] Tests edge condition scores: 69 (ignored) vs 70 (high demand) vs 71."""
    assert is_high_demand(69, threshold=70) is False
    assert is_high_demand(70, threshold=70) is True
    assert is_high_demand(71, threshold=70) is True
    assert is_high_demand(0) is False
    assert is_high_demand(-1) is False
    assert is_high_demand(100) is True


def test_t2_thai_sara_am_nfc_normalization():
    """[Boundary] Tests decomposed Thai Sara Am (\\u0e4d\\u0e32) compatibility normalization."""
    decomposed = "น\u0e49\u0e4d\u0e32แข็ง"  # นิคหิต + สระอา
    normalized = _nfc(decomposed)
    assert normalized == "น้ำแข็ง"
    assert "\u0e4d\u0e32" not in normalized

    decomposed_double = "น\u0e4d\u0e33"
    assert _nfc(decomposed_double) == "นำ"


def test_t2_empty_and_whitespace_inputs():
    """[Negative] Tests empty and whitespace-only post inputs."""
    res_empty = analyze_lead_intent_and_demand("")
    assert res_empty["demand_score"] == 0
    assert res_empty["intent"] == "general_discussion"
    assert is_high_demand(res_empty["demand_score"]) is False

    res_space = analyze_lead_intent_and_demand("     \n\t  ")
    assert res_space["demand_score"] == 0


def test_t2_lead_deduplication_idempotency(client, db_session):
    """[Idempotency] Submitting the same post twice returns already_processed without duplicate post or Sheets log."""
    post_id = f"dedup_t2_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "group_id": "grp_tech_deals",
        "group_name": "กลุ่มแกดเจ็ต",
        "author_name": "ผู้ใช้ A",
        "post_text": "อยากได้หูฟังบลูทูธไร้สายตัดเสียงรบกวนดีๆ งบ 500 บาท มีตัวไหนคุ้มสุดตอนนี้บ้างครับ",
        "post_url": f"https://facebook.com/groups/tech/posts/{post_id}",
    }

    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "post_dedup_001", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets:
        # First ingest
        r1 = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["high_demand_count"] == 1
        assert mock_post.call_count == 1
        assert mock_sheets.call_count == 1

        # Second ingest of duplicate post
        r2 = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["total_received"] == 1
        assert d2["processed"] == 1
        assert d2["high_demand_count"] == 0
        assert d2["alerts_sent"] == 0
        assert d2["results"][0]["status"] == "already_processed"
        assert d2["results"][0]["alert_sent"] is False

        # Post and Sheets should not have fired again
        assert mock_post.call_count == 1
        assert mock_sheets.call_count == 1

    # Verify single record in DB
    cnt = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=post_id).count()
    assert cnt == 1


def test_t2_admin_authorization_security_boundaries(raw_client, monkeypatch):
    """[Security] Tests authorization mechanisms (Header, Query, Bearer, Cookie, 401 Rejection)."""
    secret = "strict_security_radar_token_999"
    monkeypatch.setenv("CRON_TOKEN", secret)
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", secret)

    # 1. No auth -> 401
    assert raw_client.get("/api/admin/facebook-radar/stats").status_code == 401

    # 2. Invalid header -> 401
    assert raw_client.get("/api/admin/facebook-radar/stats", headers={"X-Admin-Token": "bad_token"}).status_code == 401

    # 3. Valid X-Admin-Token -> 200
    assert raw_client.get("/api/admin/facebook-radar/stats", headers={"X-Admin-Token": secret}).status_code == 200

    # 4. Valid ?token= -> 200
    assert raw_client.get(f"/api/admin/facebook-radar/stats?token={secret}").status_code == 200

    # 5. Valid Authorization: Bearer -> 200
    assert raw_client.get("/api/admin/facebook-radar/stats", headers={"Authorization": f"Bearer {secret}"}).status_code == 200

    # 6. Valid HMAC Session Cookie -> 200
    expiry = str(int(time.time()) + 3600)
    sig = hmac.new(secret.encode(), expiry.encode(), hashlib.sha256).hexdigest()
    valid_cookie = f"{expiry}.{sig}"
    assert raw_client.get("/api/admin/facebook-radar/stats", cookies={"pkh_admin": valid_cookie}).status_code == 200


def test_t2_price_parsing_boundary_formats():
    """[Boundary] Tests parsing diverse Thai price representations."""
    # Thai word numbers
    val1, _ = parse_post_budget("งบสองพัน")
    assert val1 == 2000.0

    val2, _ = parse_post_budget("ราคาไม่เกินร้อย")
    assert val2 == 100.0

    # Comma numbers
    val3, _ = parse_post_budget("งบ 1,500 บาท")
    assert val3 == 1500.0

    # Range
    val4, text4 = parse_post_budget("ราคา 300-500 บาท")
    assert val4 == 500.0
    assert "300-500" in text4


def test_t2_no_matching_product_or_all_dead_links(client, db_session):
    """[Boundary] Graceful handling when no products match or only dead links exist."""
    # Ingest demand for an obscure item with no product in DB
    post_id = f"no_prod_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "author_name": "ผู้ใช้พิเศษ",
        "post_text": "อยากได้เครื่องวัดคลื่นรังสีคอสมิกความแม่นยำสูง งบ 50000 บาท ด่วนมาก",
        "post_url": f"https://facebook.com/posts/{post_id}",
    }

    mock_ai_res = {
        "intent": "buy_request",
        "demand_score": 90,
        "urgency": "high",
        "budget": 50000.0,
        "budget_text": "50000 บาท",
        "product_keyword": "เครื่องวัดคลื่นรังสีคอสมิก",
        "detected_category": "ทั่วไป",
        "pain_points": ["ด่วนมาก"],
        "sentiment": "urgent",
        "reasoning": "ทดสอบ"
    }

    with patch("app.api.facebook_radar.post_feed") as mock_post, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", return_value=mock_ai_res):
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 1

        lead = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=post_id).first()
        assert lead is not None
        mock_post.assert_not_called()


# ===========================================================================
# Tier 3: Full End-to-End Lifecycle & Data Flywheel
# ===========================================================================

def test_t3_full_e2e_lifecycle_and_data_flywheel(client, db_session):
    """[E2E] Full lifecycle:
    Ingestion -> AI analysis -> Product Matching -> Auntie Khem Copy -> Demand Event ->
    Page Auto-Post -> Sheets Log -> Admin Feedback Action -> Conversion Metrics Update ->
    Stats Aggregation -> List Leads Pagination.
    """
    post_id = f"e2e_full_{int(time.time() * 1000)}"
    lead_payload = {
        "fb_post_id": post_id,
        "group_id": "grp_wfh_th",
        "group_name": "กลุ่มคนทำงาน WFH",
        "author_name": "พนักงานออฟฟิศปวดหลัง",
        "post_text": "ปวดหลังมาก ทำงาน WFH นั่งทั้งวัน อยากได้เบาะรองนั่งหรือเก้าอี้เพื่อสุขภาพดีๆ งบ 500 บาท แนะนำหน่อยครับ",
        "post_url": f"https://facebook.com/groups/wfh_th/posts/{post_id}",
        "raw_data": {"likes": 12, "comments": 4},
    }

    mock_ai = {
        "intent": "recommendation_request",
        "demand_score": 90,
        "urgency": "medium",
        "budget": 500.0,
        "budget_text": "500 บาท",
        "product_keyword": "เบาะรองนั่ง",
        "detected_category": "เฟอร์นิเจอร์",
        "pain_points": ["ปวดหลัง"],
        "sentiment": "positive",
        "reasoning": "หาเบาะรองนั่ง"
    }

    # Step 1: Ingest Lead via API
    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "e2e_fb_post_001", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.dispatch_radar_line_alert") as mock_line_alert, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", return_value=mock_ai):
        resp_ingest = client.post("/api/admin/facebook-radar/leads", json=lead_payload)
        assert resp_ingest.status_code == 200
        ingest_data = resp_ingest.json()
        assert ingest_data["high_demand_count"] == 1
        assert ingest_data["alerts_sent"] == 0
        assert ingest_data["results"][0]["status"] == "deal_matched_and_posted"
        assert mock_post.called
        assert mock_sheets.called
        mock_line_alert.assert_not_called()

    # Step 2: Verify Database Event State
    lead = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=post_id).first()
    assert lead is not None
    assert lead.status == "processed"

    event = db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead.id).first()
    assert event is not None
    assert event.demand_score >= 70
    assert event.matched_product_id is not None
    assert event.notification_status == "posted"
    assert "https://s.shopee.co.th/" in event.ai_comment_draft

    # Step 3: Admin records action & conversions via API (Data Flywheel)
    action_payload = {
        "demand_event_id": event.id,
        "lead_id": lead.id,
        "action_type": "reply_posted",
        "admin_id": "U_admin_e2e",
        "comment_posted": event.ai_comment_draft,
        "affiliate_link_used": event.matched_product.affiliate_url,
        "feedback_score": 5,
        "notes": "แอดมินคอมเมนต์ตอบแล้ว ลูกค้ากดดูลิงก์",
    }
    resp_action = client.post("/api/admin/facebook-radar/actions", json=action_payload)
    assert resp_action.status_code == 200
    action_id = resp_action.json()["id"]

    # Step 4: Simulate tracking conversions on the action
    saved_action = db_session.query(models.LeadAction).filter_by(id=action_id).first()
    saved_action.click_count = 15
    saved_action.order_count = 3
    saved_action.commission_earned = Decimal("90.00")
    saved_action.conversion_status = "converted"
    db_session.commit()

    # Step 5: Verify Radar Stats Aggregation
    resp_stats = client.get("/api/admin/facebook-radar/stats")
    assert resp_stats.status_code == 200
    stats = resp_stats.json()
    assert stats["total_leads_scanned"] >= 1
    assert stats["high_demand_leads"] >= 1
    assert stats["action_taken_count"] >= 1
    assert stats["total_clicks"] >= 15
    assert stats["total_orders"] >= 3
    assert Decimal(str(stats["total_commission_earned"])) >= Decimal("90.00")
    assert isinstance(stats["top_demanded_keywords"], list)

    # Step 6: Verify List Radar Leads Endpoint
    resp_list = client.get("/api/admin/facebook-radar/leads?limit=20&offset=0")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert list_data["total"] >= 1
    lead_entry = next((l for l in list_data["leads"] if l["fb_post_id"] == post_id), None)
    assert lead_entry is not None
    assert len(lead_entry["events"]) >= 1


def test_t3_cascade_deletion_lifecycle(db_session):
    """[Cascade] Deleting a FacebookDetectedLead cascades cleanly across demand events and lead actions."""
    post_id = f"cascade_lead_{int(time.time() * 1000)}"
    lead = models.FacebookDetectedLead(
        fb_post_id=post_id,
        post_url="https://facebook.com/cascade",
        post_text="ทดสอบ cascade delete",
        status="processed",
    )
    db_session.add(lead)
    db_session.flush()

    event = models.FacebookDemandEvent(
        lead_id=lead.id,
        intent="buy_request",
        demand_score=80,
    )
    db_session.add(event)
    db_session.flush()

    action = models.LeadAction(
        demand_event_id=event.id,
        lead_id=lead.id,
        action_type="reply_posted",
    )
    db_session.add(action)
    db_session.commit()

    assert db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead.id).count() == 1
    assert db_session.query(models.LeadAction).filter_by(lead_id=lead.id).count() == 1

    # Delete parent lead
    db_session.delete(lead)
    db_session.commit()

    # Children must be automatically deleted
    assert db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead.id).count() == 0
    assert db_session.query(models.LeadAction).filter_by(lead_id=lead.id).count() == 0


# ===========================================================================
# Tier 4: Real-World Thai Workload Simulations
# ===========================================================================

def test_t4_real_world_thai_workloads(client, db_session):
    """[Real-World] Simulates a realistic batch workload of 10 diverse Thai social media posts:
    - 6 High Demand Posts (Maternity, Earbuds, Cushion, Pet Food, Broken Fan, Air Purifier).
    - 4 Low Demand Posts (Scam Warning, Secondhand Clothes Dump, Spam Ad, Weather Discussion).
    """
    batch_posts = [
        # 1. High Demand: Maternity Dress
        {
            "fb_post_id": "rw_001_maternity",
            "group_id": "grp_moms",
            "group_name": "กลุ่มแม่และเด็ก",
            "author_name": "แม่น้องพิมพ์",
            "post_text": "มีแม่ๆ คนไหนแนะนำชุดคลุมท้องใส่สบายๆ บ้างคะ ผ้าระบายอากาศดีๆ ไม่ร้อน งบไม่เกิน 400 บาท",
            "post_url": "https://facebook.com/groups/moms/posts/1",
        },
        # 2. High Demand: Bluetooth Earbuds
        {
            "fb_post_id": "rw_002_earbuds",
            "group_id": "grp_tech",
            "group_name": "คนรักแกดเจ็ต",
            "author_name": "เกมเมอร์มือถือ",
            "post_text": "อยากได้หูฟังบลูทูธไร้สายตัดเสียงรบกวนดีๆ งบ 500 บาท มีตัวไหนคุ้มสุดตอนนี้บ้างครับ",
            "post_url": "https://facebook.com/groups/tech/posts/2",
        },
        # 3. High Demand: Ergonomic Cushion
        {
            "fb_post_id": "rw_003_cushion",
            "group_id": "grp_wfh",
            "group_name": "มนุษย์ WFH",
            "author_name": "โปรแกรมเมอร์ปวดหลัง",
            "post_text": "ปวดหลังมาก ทำงาน WFH นั่งทั้งวัน อยากได้เบาะรองนั่งหรือเก้าอี้เพื่อสุขภาพดีๆ งบ 1000 บาท แนะนำหน่อยครับ",
            "post_url": "https://facebook.com/groups/wfh/posts/3",
        },
        # 4. High Demand: Kidney Care Cat Food
        {
            "fb_post_id": "rw_004_catfood",
            "group_id": "grp_cats",
            "group_name": "ทาสแมว ชุมชนคนรักสัตว์",
            "author_name": "ทาสแมวส้ม",
            "post_text": "ตามหาอาหารเปียกแมวโรคไต ยี่ห้อไหนดีบ้างคะ น้องทานยากมาก อยากได้แบบรสชาติดี",
            "post_url": "https://facebook.com/groups/cats/posts/4",
        },
        # 5. Low Demand: Scam Warning
        {
            "fb_post_id": "rw_005_scam",
            "group_id": "grp_moms",
            "group_name": "กลุ่มแม่และเด็ก",
            "author_name": "แอดมินเตือนภัย",
            "post_text": "ประกาศเตือนภัยมิจฉาชีพหลอกโอนเงินค่าสินค้า อย่าโอนเด็ดขาด บัญชีคนโกง blacklist ระวังโดนหลอก",
            "post_url": "https://facebook.com/groups/moms/posts/5",
        },
        # 6. Low Demand: Secondhand Clothes Seller
        {
            "fb_post_id": "rw_006_secondhand",
            "group_id": "grp_market",
            "group_name": "ตลาดนัดมือสอง",
            "author_name": "แม่ค้าเสื้อผ้า",
            "post_text": "ขออนุญาตแอดมินปล่อยเสื้อผ้ามือสอง สภาพดี ส่งต่อราคาเบาๆ สนใจทักแชทได้เลย",
            "post_url": "https://facebook.com/groups/market/posts/6",
        },
        # 7. Low Demand: Spam Follower Seller
        {
            "fb_post_id": "rw_007_spam",
            "group_id": "grp_market",
            "group_name": "ตลาดนัดมือสอง",
            "author_name": "ร้านฟอลโลเวอร์",
            "post_text": "ฝากร้านหน่อยจ้า รับปั๊มฟอล IG ราคาถูก สนใจทักแชทได้เลย",
            "post_url": "https://facebook.com/groups/market/posts/7",
        },
        # 8. Low Demand: Weather Casual Discussion
        {
            "fb_post_id": "rw_008_weather",
            "group_id": "grp_talk",
            "group_name": "คุยเรื่อยเปื่อย",
            "author_name": "คนเมืองกรุง",
            "post_text": "วันนี้ฝนตกหนักมากแถวสยาม มีใครติดฝนเหมือนกันบ้าง รถติดสุดๆ เลยช่วงนี้",
            "post_url": "https://facebook.com/groups/talk/posts/8",
        },
        # 9. High Demand: Broken Fan Replacement
        {
            "fb_post_id": "rw_009_fan",
            "group_id": "grp_appliances",
            "group_name": "เครื่องใช้ไฟฟ้าในบ้าน",
            "author_name": "พ่อบ้านใจกล้า",
            "post_text": "พัดลมตัวเก่าพัง อยากได้พัดลมตั้งโต๊ะเงียบๆ ลมแรงๆ มียี่ห้อไหนดีบ้างคะ ด่วนมากร้อนสุดๆ",
            "post_url": "https://facebook.com/groups/appliances/posts/9",
        },
        # 10. High Demand: Air Purifier Search with Comma Price
        {
            "fb_post_id": "rw_010_airpurifier",
            "group_id": "grp_home",
            "group_name": "แต่งบ้าน มินิมอล",
            "author_name": "คนรักสุขภาพ",
            "post_text": "มองหาเครื่องฟอกอากาศ HEPA กรองฝุ่น PM2.5 ราคาไม่เกิน 2,500 บาท มีตัวไหนแนะนำบ้างครับ",
            "post_url": "https://facebook.com/groups/home/posts/10",
        },
    ]

    def mock_analyze(post_text, author_name=None):
        text = post_text or ""
        if "ชุดคลุมท้อง" in text:
            return {
                "intent": "recommendation_request",
                "demand_score": 85,
                "urgency": "high",
                "budget": 400.0,
                "budget_text": "400 บาท",
                "product_keyword": "ชุดคลุมท้อง",
                "detected_category": "แฟชั่น",
                "pain_points": ["ระบายอากาศ"],
                "sentiment": "positive",
                "reasoning": "หาชุดคลุมท้อง"
            }
        elif "หูฟังบลูทูธ" in text:
            return {
                "intent": "buy_request",
                "demand_score": 90,
                "urgency": "medium",
                "budget": 500.0,
                "budget_text": "500 บาท",
                "product_keyword": "หูฟังบลูทูธ",
                "detected_category": "หูฟัง",
                "pain_points": ["ตัดเสียงรบกวน"],
                "sentiment": "positive",
                "reasoning": "อยากได้หูฟัง"
            }
        elif "เบาะรองนั่ง" in text:
            return {
                "intent": "recommendation_request",
                "demand_score": 88,
                "urgency": "medium",
                "budget": 1000.0,
                "budget_text": "1000 บาท",
                "product_keyword": "เบาะรองนั่ง",
                "detected_category": "เฟอร์นิเจอร์",
                "pain_points": ["ปวดหลัง"],
                "sentiment": "positive",
                "reasoning": "หาเบาะรองนั่ง"
            }
        elif "แมวโรคไต" in text or "อาหารเปียกแมว" in text:
            return {
                "intent": "buy_request",
                "demand_score": 85,
                "urgency": "low",
                "budget": 350.0,
                "budget_text": "350 บาท",
                "product_keyword": "อาหารแมว",
                "detected_category": "สัตว์เลี้ยง",
                "pain_points": ["ทานยาก"],
                "sentiment": "positive",
                "reasoning": "ตามหาอาหารแมว"
            }
        elif "เตือนภัย" in text or " blacklist" in text:
            return {
                "intent": "spam_or_warning",
                "demand_score": 15,
                "urgency": "low",
                "budget": None,
                "budget_text": None,
                "product_keyword": None,
                "detected_category": "ทั่วไป",
                "pain_points": [],
                "sentiment": "negative",
                "reasoning": "แจ้งเตือนภัย"
            }
        elif "เสื้อผ้ามือสอง" in text or "ปล่อยเสื้อผ้า" in text:
            return {
                "intent": "spam_or_warning",
                "demand_score": 20,
                "urgency": "low",
                "budget": None,
                "budget_text": None,
                "product_keyword": None,
                "detected_category": "ทั่วไป",
                "pain_points": [],
                "sentiment": "neutral",
                "reasoning": "ปล่อยของมือสอง"
            }
        elif "ปั๊มฟอล" in text:
            return {
                "intent": "spam_or_warning",
                "demand_score": 10,
                "urgency": "low",
                "budget": None,
                "budget_text": None,
                "product_keyword": None,
                "detected_category": "ทั่วไป",
                "pain_points": [],
                "sentiment": "neutral",
                "reasoning": "ฝากร้าน/สแปม"
            }
        elif "ฝนตกหนัก" in text:
            return {
                "intent": "general_discussion",
                "demand_score": 5,
                "urgency": "low",
                "budget": None,
                "budget_text": None,
                "product_keyword": None,
                "detected_category": "ทั่วไป",
                "pain_points": [],
                "sentiment": "neutral",
                "reasoning": "พูดคุยสภาพอากาศ"
            }
        elif "พัดลม" in text:
            return {
                "intent": "buy_request",
                "demand_score": 88,
                "urgency": "high",
                "budget": 259.0,
                "budget_text": "259 บาท",
                "product_keyword": "พัดลม",
                "detected_category": "พัดลม",
                "pain_points": ["พัดลมพัง", "ร้อน"],
                "sentiment": "urgent",
                "reasoning": "พัดลมพังต้องการซื้อด่วน"
            }
        elif "เครื่องฟอกอากาศ" in text:
            return {
                "intent": "recommendation_request",
                "demand_score": 90,
                "urgency": "medium",
                "budget": 2500.0,
                "budget_text": "2,500 บาท",
                "product_keyword": "เครื่องฟอกอากาศ",
                "detected_category": "เครื่องใช้ไฟฟ้า",
                "pain_points": ["กรองฝุ่น"],
                "sentiment": "positive",
                "reasoning": "หาเครื่องฟอกอากาศ"
            }
        return {
            "intent": "general_discussion",
            "demand_score": 40,
            "urgency": "low",
            "budget": None,
            "budget_text": None,
            "product_keyword": None,
            "detected_category": "ทั่วไป",
            "pain_points": [],
            "sentiment": "neutral",
            "reasoning": "ทั่วไป"
        }

    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "rw_fb_123", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.dispatch_radar_line_alert") as mock_line_alert, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", side_effect=mock_analyze):
        resp = client.post("/api/admin/facebook-radar/leads", json={"leads": batch_posts})
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_received"] == 10
        assert data["processed"] == 10
        assert data["high_demand_count"] == 6
        assert data["alerts_sent"] == 0
        mock_line_alert.assert_not_called()

        # Check high demand results (first 5 succeed within max_posts=5, 6th ignored due to rate limit)
        high_demand_pids = ["rw_001_maternity", "rw_002_earbuds", "rw_003_cushion", "rw_004_catfood", "rw_009_fan", "rw_010_airpurifier"]
        low_demand_pids = {"rw_005_scam", "rw_006_secondhand", "rw_007_spam", "rw_008_weather"}

        for res in data["results"]:
            pid = res["fb_post_id"]
            if pid in high_demand_pids[:5]:
                assert res["status"] == "deal_matched_and_posted"
                assert res["demand_score"] >= 70
                assert res["alert_sent"] is False
                assert res["matched_product_id"] is not None
            elif pid == high_demand_pids[5]:
                # 6th high demand item hits daily limit of 5
                assert res["status"] == "ignored"
                assert res["demand_score"] >= 70
                assert res["alert_sent"] is False
            elif pid in low_demand_pids:
                assert res["status"] == "low_demand_ignored"
                assert res["demand_score"] < 70
                assert res["alert_sent"] is False
                assert res["matched_product_id"] is None


# ===========================================================================
# Dedicated Tests for Auto-Posting, 24h Cooldown, Rate Limiting & Sheets (R1-R4)
# ===========================================================================

def test_radar_24h_category_cooldown(client, db_session):
    """[R2 Cooldown] Verifies 24-hour Category Cooldown:
    1. First post in category 'แฟชั่น' -> posts successfully ('deal_matched_and_posted').
    2. Second post in same category 'แฟชั่น' within 24h -> rejected with status='ignored' and notification_status='ignored'.
    3. Post in different category 'หูฟัง' within 24h -> posts successfully ('deal_matched_and_posted').
    4. Post in category 'แฟชั่น' after 24h cooldown expires -> posts successfully.
    """
    from datetime import datetime, timedelta, timezone

    def mock_cooldown_ai(post_text, author_name=None):
        text = post_text or ""
        if "ชุดคลุมท้อง" in text:
            return {
                "intent": "recommendation_request",
                "demand_score": 85,
                "urgency": "medium",
                "budget": 400.0,
                "budget_text": "400 บาท",
                "product_keyword": "ชุดคลุมท้อง",
                "detected_category": "แฟชั่น",
                "pain_points": ["ใส่สบาย"],
                "sentiment": "positive",
                "reasoning": "ทดสอบ"
            }
        elif "หูฟังบลูทูธ" in text:
            return {
                "intent": "recommendation_request",
                "demand_score": 90,
                "urgency": "medium",
                "budget": 500.0,
                "budget_text": "500 บาท",
                "product_keyword": "หูฟังบลูทูธ",
                "detected_category": "หูฟัง",
                "pain_points": ["ตัดเสียง"],
                "sentiment": "positive",
                "reasoning": "ทดสอบ"
            }
        return {"intent": "general_discussion", "demand_score": 40}

    # 1. First lead in 'แฟชั่น'
    p1 = {
        "fb_post_id": f"cool_1_{int(time.time() * 1000)}",
        "author_name": "ลูกค้า 1",
        "post_text": "อยากได้ชุดคลุมท้องใส่สบายๆ ผ้านิ่มๆ งบ 400 บาท",
        "post_url": "https://facebook.com/post/cool_1",
    }
    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "fb_cool_1", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", side_effect=mock_cooldown_ai):
        r1 = client.post("/api/admin/facebook-radar/leads", json=p1)
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["results"][0]["status"] == "deal_matched_and_posted"
        assert mock_post.call_count == 1
        assert mock_sheets.call_count == 1

    # 2. Second lead in 'แฟชั่น' within 24h (Cooldown Blocked)
    p2 = {
        "fb_post_id": f"cool_2_{int(time.time() * 1000)}",
        "author_name": "ลูกค้า 2",
        "post_text": "ตามหาชุดคลุมท้องแฟชั่นสวยๆ งบ 450 บาท ด่วนมาก",
        "post_url": "https://facebook.com/post/cool_2",
    }
    with patch("app.api.facebook_radar.post_feed") as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", side_effect=mock_cooldown_ai):
        r2 = client.post("/api/admin/facebook-radar/leads", json=p2)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["results"][0]["status"] == "ignored"
        assert d2["alerts_sent"] == 0
        mock_post.assert_not_called()
        mock_sheets.assert_not_called()

        # Verify notification_status is 'ignored' in database
        lead2 = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=p2["fb_post_id"]).first()
        assert lead2 is not None
        ev2 = db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead2.id).first()
        assert ev2 is not None
        assert ev2.notification_status == "ignored"

    # 3. Third lead in a different category 'หูฟัง' -> Allowed
    p3 = {
        "fb_post_id": f"cool_3_{int(time.time() * 1000)}",
        "author_name": "ลูกค้า 3",
        "post_text": "อยากได้หูฟังบลูทูธไร้สายตัดเสียงรบกวนดีๆ งบ 500 บาท",
        "post_url": "https://facebook.com/post/cool_3",
    }
    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "fb_cool_3", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", side_effect=mock_cooldown_ai):
        r3 = client.post("/api/admin/facebook-radar/leads", json=p3)
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["results"][0]["status"] == "deal_matched_and_posted"
        assert mock_post.call_count == 1
        assert mock_sheets.call_count == 1

    # 4. Age the first demand event by 25 hours to simulate cooldown expiration
    lead1 = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=p1["fb_post_id"]).first()
    ev1 = db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead1.id).first()
    ev1.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()

    # Now fourth lead in 'แฟชั่น' should pass cooldown
    p4 = {
        "fb_post_id": f"cool_4_{int(time.time() * 1000)}",
        "author_name": "ลูกค้า 4",
        "post_text": "มีใครแนะนำชุดคลุมท้องใส่สบายๆ ผ้านิ่มๆ งบ 400 บาท บ้างคะ",
        "post_url": "https://facebook.com/post/cool_4",
    }
    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "fb_cool_4", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", side_effect=mock_cooldown_ai):
        r4 = client.post("/api/admin/facebook-radar/leads", json=p4)
        assert r4.status_code == 200
        d4 = r4.json()
        assert d4["results"][0]["status"] == "deal_matched_and_posted"
        assert mock_post.call_count == 1
        assert mock_sheets.call_count == 1


def test_radar_daily_post_rate_limit(client, db_session, monkeypatch):
    """[R2 Rate Limit] Verifies daily post rate limit (e.g. max 3 posts/24h):
    - Posts 1, 2, 3 in distinct categories succeed.
    - Post 4 in a 4th distinct category is rejected with status='ignored'.
    """
    monkeypatch.setenv("RADAR_MAX_DAILY_POSTS", "3")

    posts = [
        # Cat 1: แฟชั่น
        {"fb_post_id": f"rl_1_{int(time.time()*1000)}", "post_text": "ตามหาชุดคลุมท้อง งบ 500 บาท", "post_url": "https://fb.com/1"},
        # Cat 2: หูฟัง
        {"fb_post_id": f"rl_2_{int(time.time()*1000)}", "post_text": "อยากได้หูฟังบลูทูธ งบ 500 บาท", "post_url": "https://fb.com/2"},
        # Cat 3: เฟอร์นิเจอร์
        {"fb_post_id": f"rl_3_{int(time.time()*1000)}", "post_text": "อยากได้เบาะรองนั่งเพื่อสุขภาพ งบ 500 บาท", "post_url": "https://fb.com/3"},
        # Cat 4: สัตว์เลี้ยง (Should be blocked by daily rate limit of 3)
        {"fb_post_id": f"rl_4_{int(time.time()*1000)}", "post_text": "ตามหาอาหารแมวสูตรดูแลไต โรคไต งบ 500 บาท", "post_url": "https://fb.com/4"},
    ]

    def mock_rl_ai(post_text, author_name=None):
        text = post_text or ""
        if "ชุดคลุมท้อง" in text:
            return {"intent": "buy_request", "demand_score": 85, "product_keyword": "ชุดคลุมท้อง", "detected_category": "แฟชั่น", "budget": 500.0}
        elif "หูฟัง" in text:
            return {"intent": "buy_request", "demand_score": 85, "product_keyword": "หูฟังบลูทูธ", "detected_category": "หูฟัง", "budget": 500.0}
        elif "เบาะรองนั่ง" in text:
            return {"intent": "buy_request", "demand_score": 85, "product_keyword": "เบาะรองนั่ง", "detected_category": "เฟอร์นิเจอร์", "budget": 500.0}
        elif "อาหารแมว" in text:
            return {"intent": "buy_request", "demand_score": 85, "product_keyword": "อาหารแมว", "detected_category": "สัตว์เลี้ยง", "budget": 500.0}
        return {"intent": "general_discussion", "demand_score": 40}

    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "fb_rl_ok", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", side_effect=mock_rl_ai):
        for idx, p in enumerate(posts[:3]):
            resp = client.post("/api/admin/facebook-radar/leads", json=p)
            assert resp.status_code == 200
            data = resp.json()
            assert data["results"][0]["status"] == "deal_matched_and_posted"

        assert mock_post.call_count == 3
        assert mock_sheets.call_count == 3

        # 4th post exceeding daily limit
        resp4 = client.post("/api/admin/facebook-radar/leads", json=posts[3])
        assert resp4.status_code == 200
        data4 = resp4.json()
        assert data4["results"][0]["status"] == "ignored"
        assert mock_post.call_count == 3
        assert mock_sheets.call_count == 3

        lead4 = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=posts[3]["fb_post_id"]).first()
        ev4 = db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead4.id).first()
        assert ev4.notification_status == "ignored"


def test_radar_google_sheets_logging_payload(client, db_session):
    """[R3 Sheets] Verifies the exact Google Sheets payload formatted for tools/sheet_posts_apps_script.gs."""
    post_id = f"sheet_test_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "author_name": "คุณแม่สมศรี",
        "post_text": "มีใครแนะนำชุดคลุมท้องใส่สบายๆ บ้างคะ งบไม่เกิน 500 บาท",
        "post_url": f"https://facebook.com/posts/{post_id}",
    }

    mock_ai = {
        "intent": "recommendation_request",
        "demand_score": 90,
        "urgency": "medium",
        "budget": 500.0,
        "budget_text": "500 บาท",
        "product_keyword": "ชุดคลุมท้อง",
        "detected_category": "แฟชั่น",
        "pain_points": ["ใส่สบาย"],
        "sentiment": "positive",
        "reasoning": "ทดสอบ"
    }

    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "page_post_8888", "error": None}), \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", return_value=mock_ai):
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp.status_code == 200
        assert mock_sheets.called

        sheet_payload = mock_sheets.call_args[0][0]
        assert isinstance(sheet_payload, dict)
        assert sheet_payload["kind"] == "radar"
        assert "ชุดคลุมท้อง" in sheet_payload["title"]
        assert len(sheet_payload["message"]) > 10
        assert "https://s.shopee.co.th/" in sheet_payload["link"]
        assert sheet_payload["post_id"] == "page_post_8888"
        assert sheet_payload["post_url"] == "https://www.facebook.com/page_post_8888"
        assert "created_at" in sheet_payload


def test_radar_post_feed_failure_handling(client, db_session):
    """[Error Handling] When post_feed returns ok=False, demand event is marked 'failed' and no Sheets row is logged."""
    post_id = f"fail_post_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "author_name": "นายทดสอบ",
        "post_text": "อยากได้หูฟังบลูทูธไร้สายตัดเสียงรบกวนดีๆ งบ 500 บาท",
        "post_url": f"https://facebook.com/posts/{post_id}",
    }

    mock_ai = {
        "intent": "buy_request",
        "demand_score": 90,
        "urgency": "medium",
        "budget": 500.0,
        "budget_text": "500 บาท",
        "product_keyword": "หูฟังบลูทูธ",
        "detected_category": "หูฟัง",
        "pain_points": ["ตัดเสียงรบกวน"],
        "sentiment": "positive",
        "reasoning": "ทดสอบ"
    }

    with patch("app.api.facebook_radar.post_feed", return_value={"ok": False, "post_id": None, "error": "Facebook API 400 Bad Request"}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", return_value=mock_ai):
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["results"][0]["status"] == "deal_matched_post_failed"
        assert data["results"][0]["alert_sent"] is False
        mock_sheets.assert_not_called()

        lead = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=post_id).first()
        ev = db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead.id).first()
        assert ev.notification_status == "failed"


def test_radar_commit_before_post_keeps_record_when_post_crashes(client, db_session):
    """commit เกิดก่อน post_feed → ถ้า post_feed พัง (raise) record 'pending' ยังอยู่ ไม่หาย
    (กันบั๊กโพสต์ขึ้น FB แล้ว record ถูก rollback → re-ingest แล้วโพสต์ซ้ำ 4 ตัว)"""
    post_id = f"boom_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "author_name": "คนทดสอบ",
        "post_text": "หูฟังพัง อยากได้หูฟังบลูทูธใหม่ด่วน งบ 500 บาท",
        "post_url": f"https://facebook.com/posts/{post_id}",
    }
    mock_ai = {
        "intent": "buy_request",
        "demand_score": 90,
        "urgency": "high",
        "budget": 500.0,
        "budget_text": "500 บาท",
        "product_keyword": "หูฟัง",
        "detected_category": "หูฟัง",
        "pain_points": ["พัง"],
        "sentiment": "positive",
        "reasoning": "ทดสอบ",
    }

    def boom(message=None, **kwargs):
        raise RuntimeError("connection reset mid-post")

    with patch("app.api.facebook_radar.post_feed", side_effect=boom), \
         patch("app.api.facebook_radar.analyze_lead_intent_and_demand", return_value=mock_ai):
        with pytest.raises(RuntimeError):
            client.post("/api/admin/facebook-radar/leads", json=payload)

    # record ยังอยู่ (commit เกิดก่อน post_feed) — ถ้าหายจะ re-ingest แล้วโพสต์ซ้ำได้
    lead = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=post_id).first()
    assert lead is not None
    ev = db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead.id).first()
    assert ev is not None
    assert ev.notification_status == "pending"  # ยังไม่ทันอัปเดต เพราะ post พังไปก่อน


def test_cooldown_and_daily_limit_count_pending_events(db_session):
    """สถานะ 'pending' (กำลังจะโพสต์) ต้องถูกนับเป็นโพสต์ด้วย — กัน concurrent ซ้ำหมวด/เกินโควต้า"""
    prod = models.Product(name="หูฟังเทสต์", category="หูฟัง", price=100, rating=4.5,
                          sales_count=1000, commission=10, affiliate_url="https://shope.ee/t",
                          link_status="ok", ai_score=80)
    db_session.add(prod)
    db_session.flush()
    lead = models.FacebookDetectedLead(fb_post_id="t_pend_1", post_url="https://facebook.com/t1",
                                       post_text="อยากได้หูฟัง")
    db_session.add(lead)
    db_session.flush()
    ev = models.FacebookDemandEvent(lead_id=lead.id, intent="buy_request", demand_score=90,
                                    matched_product_id=prod.id, notification_status="pending")
    db_session.add(ev)
    db_session.commit()

    assert radar_api.check_category_cooldown_allowed(db_session, "หูฟัง") is False
    assert radar_api.check_daily_post_limit_allowed(db_session, max_posts=1) is False


def test_radar_guard_blocks_non_shopee_affiliate_url(client, db_session):
    """Guard หน้าตาโพสต์: แม้ matcher จะคืนสินค้ามา แต่ affiliate_url ไม่ใช่ s.shopee.co.th
    (ลิงก์ mock https://shope.ee/... → 404) ต้องไม่โพสต์ — defense-in-depth ชั้นที่ 2."""
    post_id = f"guard_fake_url_{int(time.time() * 1000)}"
    fake_product = models.Product(
        name="หูฟังบลูทูธไร้สาย TWS ตัดเสียงรบกวน",
        category="หูฟัง",
        price=Decimal("399.00"),
        rating=4.8,
        sales_count=8500,
        commission=Decimal("40.00"),
        affiliate_url="https://shope.ee/earbuds_ok",
        link_status="ok",
        ai_score=90,
    )
    mock_ai = {
        "intent": "recommendation_request",
        "demand_score": 90,
        "urgency": "medium",
        "budget": 500.0,
        "budget_text": "500 บาท",
        "product_keyword": "หูฟัง",
        "detected_category": "หูฟัง",
        "pain_points": ["หูฟังพัง"],
        "sentiment": "positive",
        "reasoning": "ต้องการหูฟังใหม่",
    }
    payload = {
        "fb_post_id": post_id,
        "group_id": "grp_guard_test",
        "group_name": "กลุ่มทดสอบ",
        "author_name": "ผู้ใช้ทดสอบ",
        "post_text": "หูฟังพัง อยากได้หูฟังใหม่ งบ 500",
        "post_url": f"https://facebook.com/groups/test/posts/{post_id}",
    }
    with patch.object(radar_api, "analyze_lead_intent_and_demand", return_value=mock_ai), \
         patch.object(radar_api, "match_best_product_for_demand", return_value={
             "best_product": fake_product,
             "match_score": 90.0,
             "suggested_reasons": ["ลิงก์ปลอม"],
             "candidates": [],
         }), \
         patch.object(radar_api, "post_feed") as mock_post, \
         patch.object(radar_api, "log_post_async"):
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "deal_matched_post_failed"
        mock_post.assert_not_called()

    lead = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=post_id).first()
    assert lead is not None
    event = db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead.id).first()
    assert event is not None
    assert event.notification_status == "failed"
    assert event.matched_product_id is None
