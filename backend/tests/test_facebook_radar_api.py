# -*- coding: utf-8 -*-
"""Comprehensive tests for FastAPI Facebook Radar API Endpoints & LINE Alerts (Milestone 3).

Verifies:
1. High-demand lead ingestion (demand_score >= 70) -> lead stored, demand event created, product matched, deal copy generated, LINE alert sent.
2. Low-demand lead ingestion (demand_score < 70 e.g. scam warning) -> lead stored as processed, NO demand event created, NO LINE alert sent.
3. Lead deduplication -> submitting identical fb_post_id twice returns already_processed without duplicate events or alerts.
4. Admin action recording (Data Flywheel) -> records triage decisions, feedback, clicks, orders, commission to LeadAction.
5. Radar stats aggregation -> aggregate counts of leads, high-demand events, actions, clicks, orders, and commissions.
6. Flexible Admin Authorization -> verifies token header (X-Admin-Token), query param (?token=), Authorization Bearer, HMAC cookie (pkh_admin), and 401 rejection on invalid auth.
7. List leads endpoint -> retrieves paginated leads with associated demand events.
8. Flex message builder -> verifies rich formatting, urgency badges, and action URI buttons.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app import models
from app.services.product_cards import format_radar_deal_flex_message
from app.api.facebook_radar import _safe_daily_post_limit, _looks_like_test_lead

TEST_ADMIN_TOKEN = os.getenv("CRON_TOKEN") or os.getenv("ADMIN_DASHBOARD_PASSWORD") or "test_radar_admin_secret"


def test_safe_daily_post_limit_clamps_and_ignores_bad_values(monkeypatch):
    # default 5 เมื่อ env ไม่ได้ตั้ง
    monkeypatch.delenv("RADAR_MAX_DAILY_POSTS", raising=False)
    assert _safe_daily_post_limit() == 5
    # ค่าปกติ
    monkeypatch.setenv("RADAR_MAX_DAILY_POSTS", "10")
    assert _safe_daily_post_limit() == 10
    # ค่าที่สูงผิดปกติ (misconfig/Hermes เก่า) → clamp ที่ cap
    monkeypatch.setenv("RADAR_MAX_DAILY_POSTS", "999")
    assert _safe_daily_post_limit() == 25
    # ค่าขยะ → fallback 5
    monkeypatch.setenv("RADAR_MAX_DAILY_POSTS", "abc")
    assert _safe_daily_post_limit() == 5
    # ติดลบ/ศูนย์ → clamp เป็น 1
    monkeypatch.setenv("RADAR_MAX_DAILY_POSTS", "0")
    assert _safe_daily_post_limit() == 1


def test_looks_like_test_lead_detects_mock_prefixes():
    assert _looks_like_test_lead("fb_mock_bulk_75576777") is True
    assert _looks_like_test_lead("fb_sample_001_maternity") is True
    assert _looks_like_test_lead("demo_post_1") is True
    # โพสต์จริง (id ตัวเลขแบบ FB) และ test_* ของ pytest ไม่โดนบล็อก
    assert _looks_like_test_lead("123456789_987654321") is False
    assert _looks_like_test_lead("test_fb_high_123") is False


def test_ingest_skips_test_leads_in_production(client, db_session, monkeypatch):
    """fb_mock_* / fb_sample_* ต้องถูกข้ามใน production (Postgres) — ไม่สร้าง lead/event
    กันแถว demand event 'posted' หลอกไปอุดตัน daily-limit (เจอจริง 15/08)."""
    from app.api import facebook_radar
    monkeypatch.setattr(facebook_radar, "_is_production", lambda: True)
    payload = {
        "fb_post_id": "fb_mock_bulk_deadbeef",
        "group_id": "grp_test",
        "group_name": "Test Group",
        "author_name": "User_99",
        "post_text": "สนใจ หูฟังบลูทูธ งบ 400",
        "post_url": "https://facebook.com/groups/test/posts/1",
        "post_time": datetime.now(timezone.utc).isoformat(),
    }
    with patch("app.api.facebook_radar.post_feed") as mock_post:
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 0
    assert data["results"][0]["status"] == "test_lead_skipped"
    mock_post.assert_not_called()
    # ไม่มี lead ถูกบันทึก
    lead = (db_session.query(models.FacebookDetectedLead)
            .filter(models.FacebookDetectedLead.fb_post_id == "fb_mock_bulk_deadbeef").first())
    assert lead is None


@pytest.fixture
def auth_headers(monkeypatch):
    token = os.getenv("CRON_TOKEN") or os.getenv("ADMIN_DASHBOARD_PASSWORD")
    if not token:
        token = TEST_ADMIN_TOKEN
        monkeypatch.setenv("CRON_TOKEN", token)
    return {"X-Admin-Token": token}


@pytest.fixture
def client(auth_headers):
    # TestClient with default admin token header
    c = TestClient(app)
    c.headers.update(auth_headers)
    return c


@pytest.fixture
def raw_client():
    # TestClient without default auth headers for testing authorization mechanisms
    return TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def seed_test_radar_products(db_session):
    """Seed test products with link_status='ok' to ensure matching works deterministically."""
    existing_maternity = (
        db_session.query(models.Product)
        .filter(models.Product.name.like("%ชุดคลุมท้อง%"))
        .first()
    )
    if not existing_maternity:
        p = models.Product(
            name="ชุดคลุมท้องผ้าฝ้ายทรงหลวม ผ้านิ่มระบายอากาศ",
            category="แฟชั่น",
            price=Decimal("299.00"),
            rating=4.9,
            sales_count=5420,
            commission=Decimal("35.00"),
            affiliate_url="https://shope.ee/test_maternity_url",
            link_status="ok",
            ai_score=92,
        )
        db_session.add(p)
        db_session.commit()


@pytest.fixture(autouse=True)
def mock_radar_ai():
    """Mock AI Lead intent analysis globally for all endpoint tests to prevent Groq API 429 errors."""
    with patch("app.api.facebook_radar.analyze_lead_intent_and_demand") as mock:
        mock.return_value = {
            "intent": "buy",
            "demand_score": 85,
            "urgency": "medium",
            "budget": 400,
            "product_keyword": "ชุดคลุมท้อง",
            "product_category": "เสื้อผ้าคุณแม่",
            "reasoning": "mocked reasoning",
        }
        yield mock


# ---------------------------------------------------------------------------
# 1. Test High-Demand Lead Ingestion
# ---------------------------------------------------------------------------

def test_high_demand_lead_ingestion_creates_event_and_alert(client, db_session):
    """เมื่อส่งโพสต์ที่มีความสนใจซื้อสูง (Score >= 70):
    - ต้องบันทึก facebook_detected_leads
    - สร้าง facebook_demand_events พร้อม matched_product และ ai_comment_draft
    - ยิงโพสต์ขึ้น Facebook Page ทันที (post_feed) และบันทึกลง Google Sheets (log_post_async)
    - notification_status == 'posted' และไม่มีการส่ง LINE alert (alerts_sent == 0)
    """
    post_id = f"test_fb_high_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "group_id": "grp_moms_th",
        "group_name": "กลุ่มแม่และเด็ก ของใช้แม่ลูก",
        "author_name": "คุณแม่มือใหม่",
        "post_text": "มีใครแนะนำชุดคลุมท้องใส่สบายๆ ผ้านิ่มๆ ระบายอากาศดีบ้างคะ ขอแบบงบไม่เกิน 400 บาท ขอบคุณค่ะ",
        "post_url": f"https://facebook.com/groups/moms_th/posts/{post_id}",
        "post_time": datetime.now(timezone.utc).isoformat(),
        "raw_data": {"likes": 15, "comments": 4},
    }

    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "test_fb_page_post_123", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.dispatch_radar_line_alert") as mock_line_alert:
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_received"] == 1
        assert data["processed"] == 1
        assert data["high_demand_count"] == 1
        assert data["alerts_sent"] == 0

        result = data["results"][0]
        assert result["fb_post_id"] == post_id
        assert result["status"] == "deal_matched_and_posted"
        assert result["demand_score"] >= 70
        assert result["alert_sent"] is False
        assert result["matched_product_id"] is not None

        mock_post.assert_called_once()
        mock_sheets.assert_called_once()
        mock_line_alert.assert_not_called()


    # ตรวจสอบข้อมูลในฐานข้อมูล
    lead = (
        db_session.query(models.FacebookDetectedLead)
        .filter(models.FacebookDetectedLead.fb_post_id == post_id)
        .first()
    )
    assert lead is not None
    assert lead.status == "processed"
    assert lead.author_name == "คุณแม่มือใหม่"

    event = (
        db_session.query(models.FacebookDemandEvent)
        .filter(models.FacebookDemandEvent.lead_id == lead.id)
        .first()
    )
    assert event is not None
    assert event.demand_score >= 70
    assert event.matched_product_id is not None
    assert event.notification_status == "posted"
    assert event.ai_comment_draft is not None
    assert len(event.ai_comment_draft) > 10


# ---------------------------------------------------------------------------
# 2. Test Low-Demand Lead Ingestion (Scam Warning / General Discussion)
# ---------------------------------------------------------------------------

def test_low_demand_lead_ingestion_stores_lead_without_event_or_alert(client, db_session, mock_radar_ai):
    """เมื่อส่งโพสต์ที่ไม่มีความสนใจซื้อ (เช่น โพสต์เตือนภัยมิจฉาชีพ):
    - บันทึก facebook_detected_leads
    - ไม่มีการสร้าง facebook_demand_events
    - ไม่มีการโพสต์ Facebook Page และไม่ส่งแจ้งเตือน LINE Alert (alerts_sent == 0)
    """
    mock_radar_ai.return_value = {
        "intent": "inquire",
        "demand_score": 40,
        "urgency": "low",
        "budget": None,
        "product_keyword": None,
        "product_category": None,
        "reasoning": "low demand mocked",
    }
    post_id = f"test_fb_low_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "group_id": "grp_moms_th",
        "group_name": "กลุ่มแม่และเด็ก ของใช้แม่ลูก",
        "author_name": "แอดมินกลุ่ม",
        "post_text": "ประกาศเตือนภัยมิจฉาชีพหลอกโอนเงินค่าสินค้า อย่าโอนเด็ดขาด บัญชีคนโกง blacklist ระวังโดนหลอก",
        "post_url": f"https://facebook.com/groups/moms_th/posts/{post_id}",
        "post_time": datetime.now(timezone.utc).isoformat(),
        "raw_data": {"likes": 50, "comments": 20},
    }

    with patch("app.api.facebook_radar.post_feed") as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets, \
         patch("app.api.facebook_radar.dispatch_radar_line_alert") as mock_line_alert:
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_received"] == 1
        assert data["processed"] == 1
        assert data["high_demand_count"] == 0
        assert data["alerts_sent"] == 0

        result = data["results"][0]
        assert result["fb_post_id"] == post_id
        assert result["status"] == "low_demand_ignored"
        assert result["demand_score"] < 70
        assert result["alert_sent"] is False
        assert result["matched_product_id"] is None

        mock_post.assert_not_called()
        mock_sheets.assert_not_called()
        mock_line_alert.assert_not_called()

    # ตรวจสอบในฐานข้อมูล
    lead = (
        db_session.query(models.FacebookDetectedLead)
        .filter(models.FacebookDetectedLead.fb_post_id == post_id)
        .first()
    )
    assert lead is not None
    assert lead.status == "processed"

    # ต้องไม่มี Demand Event
    event = (
        db_session.query(models.FacebookDemandEvent)
        .filter(models.FacebookDemandEvent.lead_id == lead.id)
        .first()
    )
    assert event is None


# ---------------------------------------------------------------------------
# 3. Test Lead Deduplication
# ---------------------------------------------------------------------------

def test_lead_deduplication_idempotency(client, db_session):
    """ส่งโพสต์ซ้ำเดิมสองครั้ง:
    - ครั้งแรกสร้าง Lead + Event + โพสต์เพจ
    - ครั้งที่สองต้องคืน status='already_processed' โดยไม่สร้างแถวซ้ำและไม่โพสต์ซ้ำ
    """
    post_id = f"test_fb_dedup_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "group_id": "grp_tech_th",
        "group_name": "กลุ่มคนรักหูฟัง",
        "author_name": "นักฟังเพลง",
        "post_text": "อยากได้หูฟังบลูทูธไร้สายตัดเสียงรบกวนดีๆ งบ 500 บาท มีตัวไหนคุ้มสุดตอนนี้บ้างครับ",
        "post_url": f"https://facebook.com/groups/tech_th/posts/{post_id}",
        "post_time": datetime.now(timezone.utc).isoformat(),
    }

    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "test_dedup_pid", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets:
        # ครั้งที่ 1
        resp1 = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["high_demand_count"] == 1
        assert mock_post.call_count == 1
        assert mock_sheets.call_count == 1

        # ครั้งที่ 2 (ส่ง payload เดิมซ้ำ)
        resp2 = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp2.status_code == 200
        data2 = resp2.json()

        assert data2["total_received"] == 1
        assert data2["processed"] == 1
        assert data2["high_demand_count"] == 0
        assert data2["alerts_sent"] == 0

        result2 = data2["results"][0]
        assert result2["fb_post_id"] == post_id
        assert result2["status"] == "already_processed"
        assert result2["alert_sent"] is False

        # โพสต์ / Sheets ไม่ควรถูกเรียกเพิ่ม
        assert mock_post.call_count == 1
        assert mock_sheets.call_count == 1

    # ตรวจสอบจำนวน record ใน DB ว่าไม่มี duplicate
    lead_count = (
        db_session.query(models.FacebookDetectedLead)
        .filter(models.FacebookDetectedLead.fb_post_id == post_id)
        .count()
    )
    assert lead_count == 1


# ---------------------------------------------------------------------------
# 4. Test Admin Action Recording (Data Flywheel)
# ---------------------------------------------------------------------------

def test_admin_action_recording_flywheel(client, db_session):
    """แอดมินบันทึกการตัดสินใจ (Reply, Conversions) ลง LeadAction"""
    # 1. Ingest lead เพื่อสร้าง demand event
    post_id = f"test_fb_action_{int(time.time() * 1000)}"
    payload = {
        "fb_post_id": post_id,
        "group_id": "grp_tech_th",
        "group_name": "กลุ่มไอที",
        "author_name": "ผู้ใช้ไอที",
        "post_text": "มีใครแนะนำหูฟังบลูทูธไร้สายบ้างครับ ขอแบบราคาไม่เกิน 300 บาท",
        "post_url": f"https://facebook.com/groups/tech_th/posts/{post_id}",
    }
    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "act_pid_1", "error": None}), \
         patch("app.api.facebook_radar.log_post_async"):
        resp = client.post("/api/admin/facebook-radar/leads", json=payload)
        assert resp.status_code == 200

    lead = (
        db_session.query(models.FacebookDetectedLead)
        .filter(models.FacebookDetectedLead.fb_post_id == post_id)
        .first()
    )
    event = (
        db_session.query(models.FacebookDemandEvent)
        .filter(models.FacebookDemandEvent.lead_id == lead.id)
        .first()
    )
    assert event is not None

    # 2. แอดมินบันทึก Action ตอบคอมเมนต์
    action_payload = {
        "demand_event_id": event.id,
        "lead_id": lead.id,
        "action_type": "reply_posted",
        "admin_id": "U_admin_test",
        "comment_posted": "สวัสดีจ้า ป้าเข็มแนะนำหูฟังตัวนี้เลย https://shope.ee/test",
        "affiliate_link_used": "https://shope.ee/test",
        "feedback_score": 5,
        "notes": "โพสต์ตอบในกลุ่มแล้ว ลูกค้ากดไลก์",
    }

    action_resp = client.post("/api/admin/facebook-radar/actions", json=action_payload)
    assert action_resp.status_code == 200
    action_data = action_resp.json()

    assert action_data["demand_event_id"] == event.id
    assert action_data["action_type"] == "reply_posted"
    assert action_data["feedback_score"] == 5
    assert action_data["id"] is not None

    # ตรวจสอบใน DB
    saved_action = (
        db_session.query(models.LeadAction)
        .filter(models.LeadAction.demand_event_id == event.id)
        .first()
    )
    assert saved_action is not None
    assert saved_action.action_type == "reply_posted"
    assert saved_action.feedback_score == 5

    # 3. ทดสอบกรณี demand_event_id ไม่ถูกต้อง
    bad_resp = client.post("/api/admin/facebook-radar/actions", json={
        "demand_event_id": 999999,
        "action_type": "ignored",
    })
    assert bad_resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Test Radar Stats Aggregation
# ---------------------------------------------------------------------------

def test_radar_stats_aggregation(client, db_session):
    """ทดสอบการดึงสถิติเรดาร์ความต้องการ (Stats Endpoint)"""
    # สร้าง lead, demand event, และ lead action เพื่อทดสอบ aggregation
    post_id = f"test_stats_{int(time.time() * 1000)}"
    lead = models.FacebookDetectedLead(
        fb_post_id=post_id,
        post_url="https://facebook.com/post/stats",
        author_name="ผู้ใช้ทดสอบสถิติ",
        post_text="ตามหาชุดคลุมท้องใส่สบาย",
        status="processed",
    )
    db_session.add(lead)
    db_session.flush()

    event = models.FacebookDemandEvent(
        lead_id=lead.id,
        intent="buy_request",
        demand_score=85,
        urgency="high",
        budget="400 บาท",
        product_keyword="ชุดคลุมท้อง",
        notification_status="sent",
    )
    db_session.add(event)
    db_session.flush()

    action = models.LeadAction(
        demand_event_id=event.id,
        lead_id=lead.id,
        action_type="reply_posted",
        click_count=10,
        order_count=2,
        commission_earned=Decimal("70.00"),
    )
    db_session.add(action)
    db_session.commit()

    resp = client.get("/api/admin/facebook-radar/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert "total_leads_scanned" in data
    assert "high_demand_leads" in data
    assert "action_taken_count" in data
    assert "total_clicks" in data
    assert "total_orders" in data
    assert "total_commission_earned" in data
    assert "top_demanded_keywords" in data

    assert data["total_leads_scanned"] >= 1
    assert data["high_demand_leads"] >= 1
    assert data["action_taken_count"] >= 1
    assert data["total_clicks"] >= 10
    assert data["total_orders"] >= 2
    assert Decimal(str(data["total_commission_earned"])) >= Decimal("70.00")
    assert isinstance(data["top_demanded_keywords"], list)


# ---------------------------------------------------------------------------
# 6. Test Admin Authorization Security
# ---------------------------------------------------------------------------

def test_admin_authorization_mechanisms(raw_client, monkeypatch):
    """ทดสอบความปลอดภัยและการยืนยันตัวตนแอดมิน:
    - X-Admin-Token Header
    - ?token= Query Parameter
    - Authorization: Bearer <token>
    - pkh_admin Cookie
    - 401 เมื่อ Token ไม่ถูกต้อง
    """
    secret = "test_super_secret_radar_token_123"
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", secret)
    monkeypatch.setenv("CRON_TOKEN", secret)

    # 1. ไม่มี token/cookie -> 401
    r_unauth = raw_client.get("/api/admin/facebook-radar/stats")
    assert r_unauth.status_code == 401

    # 2. ใส่ X-Admin-Token ถูกต้อง -> 200
    r_header = raw_client.get(
        "/api/admin/facebook-radar/stats",
        headers={"X-Admin-Token": secret},
    )
    assert r_header.status_code == 200

    # 3. ใส่ ?token= ถูกต้อง -> 200
    r_query = raw_client.get(f"/api/admin/facebook-radar/stats?token={secret}")
    assert r_query.status_code == 200

    # 4. ใส่ Authorization: Bearer <token> -> 200
    r_bearer = raw_client.get(
        "/api/admin/facebook-radar/stats",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert r_bearer.status_code == 200

    # 5. Cookie pkh_admin แบบ HMAC -> 200
    payload = str(int(time.time()) + 3600)
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    valid_cookie = f"{payload}.{sig}"
    r_cookie = raw_client.get(
        "/api/admin/facebook-radar/stats",
        cookies={"pkh_admin": valid_cookie},
    )
    assert r_cookie.status_code == 200

    # 6. Token ผิด -> 401
    r_bad = raw_client.get(
        "/api/admin/facebook-radar/stats",
        headers={"X-Admin-Token": "wrong_secret"},
    )
    assert r_bad.status_code == 401


# ---------------------------------------------------------------------------
# 7. Test List Radar Leads
# ---------------------------------------------------------------------------

def test_list_radar_leads_endpoint(client, db_session):
    """ทดสอบการเรียกดูรายการ Leads และ Events"""
    # Seed lead เพื่อให้มีข้อมูลชัวร์
    post_id = f"test_list_{int(time.time() * 1000)}"
    lead = models.FacebookDetectedLead(
        fb_post_id=post_id,
        post_url="https://facebook.com/post/list",
        author_name="ผู้ใช้ลิสต์",
        post_text="ตามหาชุดคลุมท้อง",
        status="processed",
    )
    db_session.add(lead)
    db_session.commit()

    resp = client.get("/api/admin/facebook-radar/leads?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()

    assert "total" in data
    assert "leads" in data
    assert isinstance(data["leads"], list)
    assert data["total"] >= 1


# ---------------------------------------------------------------------------
# 8. Test Flex Message Builder Details
# ---------------------------------------------------------------------------

def test_radar_deal_flex_message_structure(db_session):
    """ทดสอบโครงสร้าง Flex Message แจ้งเตือนดีลเรดาร์:
    - Alt text มีชื่อสินค้าและคะแนน
    - มีปุ่มลิงก์เปิด Facebook Post
    - มีปุ่มตรวจสอบสินค้าบน Shopee
    """
    product = (
        db_session.query(models.Product)
        .filter(models.Product.link_status == "ok")
        .first()
    )

    flex = format_radar_deal_flex_message(
        group_name="กลุ่มทดสอบแม่และเด็ก",
        post_text="ตามหาชุดคลุมท้องใส่สบายๆ ผ้าระบายอากาศดีๆ งบ 400",
        post_url="https://facebook.com/groups/test/posts/1001",
        demand_score=88,
        urgency="high",
        matched_product=product,
        suggested_reasons=["ยอดขายอันดับ 1", "รีวิว 4.9 ดาว"],
        copy_text="สวัสดีจ้าคุณแม่ ป้าเข็มแนะนำรุ่นนี้เลยจ้า https://shope.ee/test",
    )

    assert flex is not None
    assert "Demand Radar" in flex.alt_text
    assert "88" in flex.alt_text

    contents_dict = flex.contents.as_json_dict() if hasattr(flex.contents, "as_json_dict") else flex.contents
    assert contents_dict["type"] == "bubble"
    assert contents_dict["header"]["backgroundColor"] == "#E74C3C"

    # ตรวจสอบปุ่มใน Footer
    footer = contents_dict["footer"]
    buttons = footer["contents"]
    assert len(buttons) == 2
    assert buttons[0]["action"]["type"] == "uri"
    assert "facebook.com" in buttons[0]["action"]["uri"]
    assert buttons[1]["action"]["type"] == "uri"
    assert buttons[1]["action"]["label"] == "🛒 ตรวจสอบสินค้าบน Shopee"


# ---------------------------------------------------------------------------
# 9. Test Category Cooldown & Daily Rate Limit Rejections
# ---------------------------------------------------------------------------

def test_high_demand_lead_category_cooldown_and_rate_limit_api(client, db_session):
    """ทดสอบการปฏิเสธโพสต์ซ้ำหมวดเดิมใน 24 ชั่วโมง:
    - ครั้งที่ 1: โพสต์สำเร็จ -> status='deal_matched_and_posted', event='posted'
    - ครั้งที่ 2 ในหมวดเดิมภายใน 24 ชม: ปฏิเสธ -> status='ignored', event='ignored'
    """
    p1 = {
        "fb_post_id": f"api_cool_1_{int(time.time() * 1000)}",
        "author_name": "ลูกค้าหมวดแฟชั่น 1",
        "post_text": "อยากได้ชุดคลุมท้องใส่สบายๆ ผ้านิ่มๆ งบ 400 บาท",
        "post_url": "https://facebook.com/post/api_cool_1",
    }
    with patch("app.api.facebook_radar.post_feed", return_value={"ok": True, "post_id": "fb_api_cool_1", "error": None}) as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets:
        resp1 = client.post("/api/admin/facebook-radar/leads", json=p1)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["results"][0]["status"] == "deal_matched_and_posted"
        assert mock_post.call_count == 1
        assert mock_sheets.call_count == 1

    # โพสต์ที่ 2 หมวดเดิมภายใน 24 ชั่วโมง
    p2 = {
        "fb_post_id": f"api_cool_2_{int(time.time() * 1000)}",
        "author_name": "ลูกค้าหมวดแฟชั่น 2",
        "post_text": "ตามหาชุดคลุมท้องผ้าฝ้ายทรงหลวม งบ 500 บาท ด่วน",
        "post_url": "https://facebook.com/post/api_cool_2",
    }
    with patch("app.api.facebook_radar.post_feed") as mock_post, \
         patch("app.api.facebook_radar.log_post_async") as mock_sheets:
        resp2 = client.post("/api/admin/facebook-radar/leads", json=p2)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["results"][0]["status"] == "ignored"
        assert data2["alerts_sent"] == 0
        mock_post.assert_not_called()
        mock_sheets.assert_not_called()

        lead2 = db_session.query(models.FacebookDetectedLead).filter_by(fb_post_id=p2["fb_post_id"]).first()
        ev2 = db_session.query(models.FacebookDemandEvent).filter_by(lead_id=lead2.id).first()
        assert ev2 is not None
        assert ev2.notification_status == "ignored"
