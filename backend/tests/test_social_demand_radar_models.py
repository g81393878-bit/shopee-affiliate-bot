# -*- coding: utf-8 -*-
"""Unit tests for Social Demand Radar V1 models and schemas (Milestone 1).
Verifies:
- SQLAlchemy ORM models creation, querying, foreign keys, relationships, cascading deletes.
- Pydantic v2 schema validations, serialization, and ORM conversion.
- SQL migration file integrity.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app import models, schemas


def test_facebook_demand_event_and_product_matching(db):
    """Test FacebookDemandEvent ORM and relationship with Product."""
    # Find seeded product or create one
    product = db.query(models.Product).first()
    if not product:
        product = models.Product(
            name="อาหารแมวสูตรดูแลไต 1kg",
            category="สัตว์เลี้ยง",
            price=Decimal("350.00"),
            rating=4.8,
            sales_count=1500,
            commission=Decimal("35.00"),
            affiliate_url="https://s.shopee.co.th/test-cat-food",
            link_status="ok",
            ai_score=88,
        )
        db.add(product)
        db.commit()

    lead = models.FacebookDetectedLead(
        fb_post_id="post_demand_777",
        post_url="https://facebook.com/posts/777",
        author_name="ลูกค้า แมวเหมียว",
        post_text="อยากได้อาหารแมวราคาไม่แพง มีโปรลดราคาแนะนำไหมคะ",
        status="analyzed",
    )
    db.add(lead)
    db.commit()

    demand_event = models.FacebookDemandEvent(
        lead_id=lead.id,
        intent="buy_request",
        demand_score=85,
        urgency="high",
        budget="ไม่เกิน 400 บาท",
        product_keyword="อาหารแมว",
        matched_product_id=product.id,
        suggested_reason={"sales": product.sales_count, "rating": product.rating, "commission": float(product.commission)},
        ai_comment_draft="ป้าเข็มแนะนำตัวนี้เลยจ้า อาหารแมวสูตรพรีเมียมราคาประหยัด 👉 https://shope.ee/test-cat-food",
        notification_status="sent",
        notification_sent_at=datetime.now(timezone.utc),
    )
    db.add(demand_event)
    db.commit()
    db.refresh(demand_event)

    assert demand_event.id is not None
    assert demand_event.demand_score == 85
    assert demand_event.matched_product.id == product.id
    assert demand_event.lead.id == lead.id

    # Test schema conversion
    demand_out = schemas.FacebookDemandEventOut.model_validate(demand_event)
    assert demand_out.id == demand_event.id
    assert demand_out.demand_score == 85
    assert demand_out.matched_product is not None
    assert demand_out.matched_product.name == product.name


def test_lead_action_and_data_flywheel(db):
    """Test LeadAction ORM and conversion metrics tracking."""
    lead = models.FacebookDetectedLead(
        fb_post_id="post_lead_action_1",
        post_url="https://facebook.com/posts/action1",
        post_text="ขอพิกัดหูฟังตัดเสียงรบกวนหน่อยครับ",
        status="analyzed",
    )
    db.add(lead)
    db.commit()

    event = models.FacebookDemandEvent(
        lead_id=lead.id,
        intent="buy_request",
        demand_score=90,
        urgency="high",
        product_keyword="หูฟังตัดเสียง",
    )
    db.add(event)
    db.commit()

    action = models.LeadAction(
        demand_event_id=event.id,
        lead_id=lead.id,
        action_type="reply_posted",
        admin_id="U_admin_1234",
        comment_posted="ลองดูหูฟังตัวนี้ครับ ตัดเสียงดีมาก",
        affiliate_link_used="https://shope.ee/test-headphones",
        feedback_score=5,
        click_count=12,
        order_count=2,
        commission_earned=Decimal("50.00"),
        conversion_status="converted",
        notes="คอมเมนต์ตอบแล้ว มีคนคลิกสั่งซื้อจริง 2 ออเดอร์",
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    assert action.id is not None
    assert action.click_count == 12
    assert action.order_count == 2
    assert action.commission_earned == Decimal("50.00")
    assert action.conversion_status == "converted"
    assert action.demand_event.id == event.id
    assert action.lead.id == lead.id

    # Test schema conversion
    action_out = schemas.LeadActionOut.model_validate(action)
    assert action_out.id == action.id
    assert action_out.commission_earned == Decimal("50.00")
    assert action_out.click_count == 12


def test_cascade_deletion(db):
    """Test that deleting a lead cascades to demand events and actions."""
    lead = models.FacebookDetectedLead(
        fb_post_id="post_cascade_test",
        post_url="https://facebook.com/posts/cascade",
        post_text="เทสต์การลบข้อมูล",
    )
    db.add(lead)
    db.commit()

    event = models.FacebookDemandEvent(
        lead_id=lead.id,
        intent="buy_request",
        demand_score=75,
    )
    db.add(event)
    db.commit()

    action = models.LeadAction(
        demand_event_id=event.id,
        lead_id=lead.id,
        action_type="ignored",
    )
    db.add(action)
    db.commit()

    # Verify rows exist
    assert db.query(models.FacebookDemandEvent).filter_by(lead_id=lead.id).count() == 1
    assert db.query(models.LeadAction).filter_by(lead_id=lead.id).count() == 1

    # Delete lead
    db.delete(lead)
    db.commit()

    # Verify cascade
    assert db.query(models.FacebookDemandEvent).filter_by(lead_id=lead.id).count() == 0
    assert db.query(models.LeadAction).filter_by(lead_id=lead.id).count() == 0


def test_pydantic_schemas_payloads():
    """Test Ingestion payloads and Radar stats schemas."""
    payload = schemas.LeadIngestPayload(
        leads=[
            schemas.LeadIngestItem(
                fb_post_id="post_item_01",
                post_url="https://facebook.com/post/01",
                author_name="User A",
                post_text="ต้องการซื้อเก้าอี้เพื่อสุขภาพ",
            )
        ]
    )
    assert len(payload.leads) == 1
    assert payload.leads[0].fb_post_id == "post_item_01"

    response = schemas.LeadIngestionResponse(
        total_received=1,
        processed=1,
        high_demand_count=1,
        alerts_sent=1,
        results=[
            schemas.IngestedLeadResult(
                fb_post_id="post_item_01",
                lead_id=10,
                status="analyzed",
                demand_score=92,
                intent="buy_request",
                alert_sent=True,
                matched_product_id=5,
            )
        ],
    )
    assert response.processed == 1
    assert response.results[0].demand_score == 92


def test_sql_migration_file_exists_and_valid():
    """Verify that migration SQL file exists and contains all required table definitions."""
    migration_path = Path(__file__).resolve().parent.parent.parent / "supabase" / "migrations" / "20260815194500_social_demand_radar.sql"
    assert migration_path.exists(), f"Migration file not found at {migration_path}"

    sql_content = migration_path.read_text(encoding="utf-8")
    assert "facebook_detected_leads" in sql_content
    assert "facebook_demand_events" in sql_content
    assert "lead_actions" in sql_content
    assert "idx_fb_leads_post_id" in sql_content
    assert "idx_fb_demand_lead_id" in sql_content
    assert "idx_lead_actions_demand_id" in sql_content
