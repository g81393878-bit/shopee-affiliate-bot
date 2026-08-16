# -*- coding: utf-8 -*-
"""FastAPI Radar API Endpoints & LINE Alerts (Social Demand Radar V1 - บอทป้าเข็ม)
================================================================================
Endpoints:
- POST /api/admin/facebook-radar/leads   → รับโพสต์ดิบ วิเคราะห์ Demand จับคู่สินค้า ส่ง LINE Push
- POST /api/admin/facebook-radar/actions → บันทึก Action แอดมินและ Conversions (Data Flywheel)
- GET  /api/admin/facebook-radar/stats   → ดึงสถิติภาพรวมเรดาร์ความต้องการ
- GET  /api/admin/facebook-radar/leads   → รายการโพสต์ที่ตรวจพบพร้อมผลการวิเคราะห์

การรักษาความปลอดภัย:
- ตรวจสอบผ่าน Session Cookie (pkh_admin), Header (X-Admin-Token / Authorization), หรือ Query (?token=)
- ในสภาพแวดล้อม Local / Testing ที่ไม่มีการตั้งค่า Token สามารถเข้าถึงได้โดยอัตโนมัติ
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
from app.services.demand_radar_ai import (
    analyze_lead_intent_and_demand,
    generate_auntie_khem_deal_comment,
    is_high_demand,
    analyze_facebook_insights,
)
from app.services.facebook_poster import log_post_async, post_feed
from app.services.line_quota import push_guard
from app.services.product_cards import format_radar_deal_flex_message
from app.services.product_matcher import match_best_product_for_demand, is_valid_shopee_affiliate_url
from app.services.hermes_brain import load_skills_safe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/facebook-radar", tags=["facebook-radar"])

COOKIE_NAME = "pkh_admin"

# ห้ามให้ daily post limit เกินค่านี้ — กัน misconfig/Hermes ทำให้เพจล้นโพสต์
MAX_DAILY_POSTS_CAP = 25

# fb_post_id ที่ขึ้นต้นด้วยคำพวกนี้ = lead ทดสอบ/หลอก (fb_group_monitor_local --sample
# หรือสคริปต์เทสต์) — ห้ามหลุดเข้า production เพราะจะสร้างแถว demand event 'posted' หลอก
# แล้วไปอุดตัน daily-limit counter (เจอจริง 15/08: fb_mock_bulk_* 100 แถวใน 7 วิ)
# หมายเหตุ: ไม่รวม "test_" เพราะ pytest ใช้ post_id แบบ test_* กับ SQLite test DB เอง
TEST_LEAD_PREFIXES = ("fb_sample_", "fb_mock_", "demo_")


def _looks_like_test_lead(fb_post_id: str) -> bool:
    """True เมื่อ fb_post_id เป็น lead ทดสอบ/หลอก (ไม่ใช่โพสต์จริงจากกลุ่ม FB)."""
    return (fb_post_id or "").strip().lower().startswith(TEST_LEAD_PREFIXES)


def _is_production() -> bool:
    """Production = ต่อ Postgres จริง (Supabase/Render) — sqlite = dev/test.

    ใช้ DATABASE_URL เป็นสัญญาณ (ไม่ใช่ secret เพราะ conftest/เครื่อง dev อาจมี
    CRON_TOKEN ใน .env แล้วทำให้เข้าใจผิดว่าเป็น production).
    """
    db_url = (os.getenv("DATABASE_URL") or "").strip().lower()
    return db_url.startswith("postgres") or db_url.startswith("postgresql")


def _safe_daily_post_limit() -> int:
    """อ่าน RADAR_MAX_DAILY_POSTS (env เท่านั้น) พร้อม clamp [1, MAX_DAILY_POSTS_CAP].

    ตั้งใจไม่ให้ Hermes / system_preferences มา override โควต้าโพสต์ —
    เพราะเคยเกิด Hermes ตั้งค่าสูงแล้วบอทโพสต์ระเบิด 21 ตัวในวินาทีเดียว.
    """
    try:
        val = int(os.getenv("RADAR_MAX_DAILY_POSTS", "5"))
    except (ValueError, TypeError):
        val = 5
    return max(1, min(val, MAX_DAILY_POSTS_CAP))


# ---------------------------------------------------------------------------
# Admin Authentication Dependency
# ---------------------------------------------------------------------------

def _get_admin_secret() -> str:
    """ดึง Secret Token สำหรับตรวจสอบสิทธิ์แอดมิน"""
    return (os.getenv("ADMIN_DASHBOARD_PASSWORD") or os.getenv("CRON_TOKEN") or "").strip()


def _check_admin_session(cookie_val: Optional[str]) -> bool:
    """ตรวจสอบ HMAC Signature ของ Session Cookie"""
    secret = _get_admin_secret()
    if not cookie_val or not secret:
        return False
    try:
        payload, sig = cookie_val.rsplit(".", 1)
        expected_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig) and int(payload) > time.time()
    except Exception:
        return False


def require_admin_auth(
    token: Optional[str] = Query(None, alias="token"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    pkh_admin: Optional[str] = Cookie(None, alias=COOKIE_NAME),
) -> bool:
    """Flexible Admin Authorization:
    1. pkh_admin Cookie
    2. X-Admin-Token Header
    3. ?token= Query Parameter
    4. Authorization: Bearer <token>
    5. Bypass in local/test if no token is configured
    """
    secret = _get_admin_secret()
    cron_token = (os.getenv("CRON_TOKEN") or "").strip()
    admin_pw = (os.getenv("ADMIN_DASHBOARD_PASSWORD") or "").strip()

    # หากไม่ได้ตั้งค่า token ใดๆ ไว้ในระบบ (เช่น local dev/test) ให้ผ่านได้
    if not secret:
        return True

    # 1. ตรวจสอบ Cookie
    if pkh_admin and _check_admin_session(pkh_admin):
        return True

    # 2. ตรวจสอบ Header X-Admin-Token
    if x_admin_token:
        xt = x_admin_token.strip()
        if (
            hmac.compare_digest(xt, secret)
            or (cron_token and hmac.compare_digest(xt, cron_token))
            or (admin_pw and hmac.compare_digest(xt, admin_pw))
        ):
            return True

    # 3. ตรวจสอบ Query Parameter ?token=
    if token:
        qt = token.strip()
        if (
            hmac.compare_digest(qt, secret)
            or (cron_token and hmac.compare_digest(qt, cron_token))
            or (admin_pw and hmac.compare_digest(qt, admin_pw))
        ):
            return True

    # 4. ตรวจสอบ Authorization: Bearer <token>
    if authorization and authorization.startswith("Bearer "):
        bt = authorization[7:].strip()
        if (
            hmac.compare_digest(bt, secret)
            or (cron_token and hmac.compare_digest(bt, cron_token))
            or (admin_pw and hmac.compare_digest(bt, admin_pw))
        ):
            return True

    raise HTTPException(status_code=401, detail="Unauthorized admin access")


# ---------------------------------------------------------------------------
# Rate Limiting & Cooldown Guards
# ---------------------------------------------------------------------------

def check_category_cooldown_allowed(
    db: Session,
    category: Optional[str],
    cooldown_hours: Optional[int] = None,
) -> bool:
    """Checks if a product category was posted via demand radar within the cooldown window.
    Returns True if allowed to post (no recent post in same category), False if in cooldown.
    """
    if not category:
        return True

    if cooldown_hours is None:
        try:
            cooldown_hours = int(os.getenv("RADAR_CATEGORY_COOLDOWN_HOURS", "24"))
        except (ValueError, TypeError):
            cooldown_hours = 24

    cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)

    # 'pending' = กำลังจะโพสต์ (commit ก่อน post_feed) — นับด้วยเพื่อกัน concurrent ซ้ำหมวด
    recent_count = (
        db.query(models.FacebookDemandEvent.id)
        .join(models.Product, models.FacebookDemandEvent.matched_product_id == models.Product.id)
        .filter(
            models.FacebookDemandEvent.notification_status.in_(["posted", "sent", "pending"]),
            models.FacebookDemandEvent.created_at >= cutoff,
            models.Product.category == category,
        )
        .count()
    )
    return recent_count == 0


def check_daily_post_limit_allowed(
    db: Session,
    max_posts: Optional[int] = None,
    window_hours: int = 24,
) -> bool:
    """Checks if total demand radar auto-posts in the sliding window is below the daily limit.
    Returns True if allowed to post, False if daily limit reached.
    """
    if max_posts is None:
        try:
            max_posts = int(os.getenv("RADAR_MAX_DAILY_POSTS", "5"))
        except (ValueError, TypeError):
            max_posts = 5

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    # 'pending' = กำลังจะโพสต์ (commit ก่อน post_feed) — นับด้วยเพื่อกัน concurrent เกินโควต้า
    total_posts = (
        db.query(models.FacebookDemandEvent.id)
        .filter(
            models.FacebookDemandEvent.notification_status.in_(["posted", "sent", "pending"]),
            models.FacebookDemandEvent.created_at >= cutoff,
        )
        .count()
    )
    return total_posts < max_posts


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def dispatch_radar_line_alert(
    db: Session,
    lead: models.FacebookDetectedLead,
    demand_event: models.FacebookDemandEvent,
    matched_product: Optional[models.Product] = None,
    group_name: Optional[str] = None,
) -> bool:
    """[DEPRECATED / DEACTIVATED] Social Demand Radar V1 uses 100% Facebook Page auto-posting.
    LINE admin alerts are deactivated to prevent alert fatigue.
    """
    logger.debug("LINE radar alerts are deactivated in favor of Facebook Page auto-posting.")
    return False


def _normalize_lead_item(raw: Any) -> Dict[str, Any]:
    """แปลง input หลากหลายรูปแบบให้อยู่ในโครงสร้างมาตรฐาน"""
    if isinstance(raw, schemas.LeadIngestItem):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        data = getattr(raw, "__dict__", {})

    post_id = data.get("fb_post_id") or data.get("post_id") or ""
    post_url = data.get("post_url") or ""
    author_name = data.get("author_name") or None
    post_text = data.get("post_text") or ""
    post_time = data.get("post_time") or data.get("posted_at") or None
    group_id = data.get("group_id")
    group_name = data.get("group_name")
    raw_data = data.get("raw_data") or data.get("raw_payload")

    if isinstance(post_time, str):
        try:
            post_time = datetime.fromisoformat(post_time.replace("Z", "+00:00"))
        except Exception:
            post_time = None

    return {
        "fb_post_id": str(post_id).strip(),
        "post_url": str(post_url).strip() or "https://facebook.com",
        "author_name": author_name,
        "post_text": str(post_text).strip(),
        "post_time": post_time,
        "group_id": group_id,
        "group_name": group_name,
        "raw_data": raw_data,
    }


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.post("/leads", response_model=schemas.LeadIngestionResponse)
def ingest_facebook_leads(
    payload: Union[schemas.LeadIngestPayload, List[schemas.LeadIngestItem], schemas.LeadIngestItem, Dict[str, Any]],
    db: Session = Depends(get_db),
    authorized: bool = Depends(require_admin_auth),
):
    """รับข้อมูลโพสต์ดิบจาก Facebook Monitor / Local Scraper
    1. Deduplicate fb_post_id ใน FacebookDetectedLead
    2. วิเคราะห์ Intent, Demand Score, Urgency, Budget, Product Keyword ด้วย AI
    3. หาก Demand Score >= 70:
       - จับคู่สินค้าในคลัง (link_status == 'ok')
       - สร้างข้อความแนะนำสไตล์ป้าเข็ม
       - ตรวจสอบ Category Cooldown (24 ชม.) และ Daily Rate Limit (3-5 โพสต์/วัน)
       - หากติด Cooldown/Rate limit: บันทึก Demand Event (notification_status='ignored') และคืน status='ignored'
       - หากผ่านเงื่อนไข: ยิงโพสต์อัตโนมัติขึ้นเพจ Facebook ทันที (post_feed) และบันทึกลง Google Sheets (log_post_async)
    4. หาก Demand Score < 70:
       - บันทึก Lead สถานะ processed โดยไม่สร้าง Demand Event
    """
    raw_items: List[Any] = []
    if isinstance(payload, schemas.LeadIngestPayload):
        raw_items = payload.leads
    elif isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict) and "leads" in payload and isinstance(payload["leads"], list):
        raw_items = payload["leads"]
    elif isinstance(payload, (schemas.LeadIngestItem, dict)):
        raw_items = [payload]
    elif hasattr(payload, "leads"):
        raw_items = payload.leads
    else:
        raw_items = [payload]

    items = [_normalize_lead_item(item) for item in raw_items if item]
    total_received = len(items)
    results: List[schemas.IngestedLeadResult] = []
    processed_count = 0
    high_demand_count = 0

    for item in items:
        fb_post_id = item["fb_post_id"]
        if not fb_post_id:
            continue

        # 0. กัน lead ทดสอบ/หลอก (fb_sample_/fb_mock_/test_...) หลุดเข้า production —
        #    เคยสร้างแถว demand event 'posted' หลอก 102 แถวแล้วอุดตัน daily-limit counter
        if _is_production() and _looks_like_test_lead(fb_post_id):
            results.append(
                schemas.IngestedLeadResult(
                    fb_post_id=fb_post_id,
                    lead_id=None,
                    status="test_lead_skipped",
                    demand_score=None,
                    intent=None,
                    alert_sent=False,
                    matched_product_id=None,
                )
            )
            continue

        # 1. ตรวจสอบ Deduplication
        existing_lead = (
            db.query(models.FacebookDetectedLead)
            .filter(models.FacebookDetectedLead.fb_post_id == fb_post_id)
            .first()
        )

        if existing_lead:
            existing_event = (
                db.query(models.FacebookDemandEvent)
                .filter(models.FacebookDemandEvent.lead_id == existing_lead.id)
                .first()
            )
            score = existing_event.demand_score if existing_event else None
            intent = existing_event.intent if existing_event else None
            matched_id = existing_event.matched_product_id if existing_event else None

            results.append(
                schemas.IngestedLeadResult(
                    fb_post_id=fb_post_id,
                    lead_id=existing_lead.id,
                    status="already_processed",
                    demand_score=score,
                    intent=intent,
                    alert_sent=False,
                    matched_product_id=matched_id,
                )
            )
            processed_count += 1
            continue

        # 2. จัดการข้อมูลกลุ่ม FacebookGroupMonitor (ถ้ามีระบุ)
        group_db_id = None
        group_identifier = item["group_id"]
        group_name = item["group_name"]
        if group_identifier:
            grp_str = str(group_identifier)
            group_obj = (
                db.query(models.FacebookGroupMonitor)
                .filter(models.FacebookGroupMonitor.group_id == grp_str)
                .first()
            )
            if not group_obj:
                group_obj = models.FacebookGroupMonitor(
                    group_id=grp_str,
                    group_name=group_name or f"Group {grp_str}",
                    group_url=f"https://facebook.com/groups/{grp_str}",
                    last_scanned_at=datetime.now(timezone.utc),
                    post_count_detected=1,
                )
                db.add(group_obj)
                db.flush()
            else:
                group_obj.post_count_detected = (group_obj.post_count_detected or 0) + 1
                group_obj.last_scanned_at = datetime.now(timezone.utc)
            group_db_id = group_obj.id

        # 3. บันทึกโพสต์ดิบ FacebookDetectedLead
        lead = models.FacebookDetectedLead(
            fb_post_id=fb_post_id,
            post_url=item["post_url"],
            author_name=item["author_name"],
            post_text=item["post_text"],
            post_time=item["post_time"] or datetime.now(timezone.utc),
            group_id=group_db_id,
            raw_data=item["raw_data"],
            status="pending",
        )
        db.add(lead)
        db.flush()

        # 4. วิเคราะห์เจตนาและความต้องการด้วย AI Engine
        analysis = analyze_lead_intent_and_demand(
            post_text=item["post_text"],
            author_name=item["author_name"],
        )
        demand_score = int(analysis.get("demand_score", 0))
        urgency = analysis.get("urgency", "low")
        budget_val = analysis.get("budget")
        budget_text = analysis.get("budget_text") or (f"{budget_val} บาท" if budget_val else None)
        product_keyword = analysis.get("product_keyword")
        intent = analysis.get("intent", "unknown")

        lead.status = "processed"

        # [Hermes AI] โหลดทักษะที่ AI เรียนรู้มาเพื่อปรับพฤติกรรมบอทแบบไดนามิก
        # (load_skills_safe = fail-open — ตาราง system_preferences ยังไม่มีก่อน
        # migration ก็ไม่ crash endpoint นี้ คืน DEFAULT ครบแทน)
        hermes_skills = load_skills_safe(db)
        radar_min_score = hermes_skills.get("radar_min_demand_score", 70)
        # Daily post limit เป็นของแอดมินเท่านั้น (env RADAR_MAX_DAILY_POSTS) —
        # Hermes เรียนปรับได้แค่ radar_min_demand_score ไม่ใช่โควต้าโพสต์
        # (เคยเจอ Hermes ตั้ง radar_daily_post_limit สูง → โพสต์ระเบิด 21 ตัวในวินาทีเดียว)
        daily_limit = _safe_daily_post_limit()

        # 5. ตรวจสอบเงื่อนไข Demand Score >= radar_min_score
        if is_high_demand(demand_score, threshold=radar_min_score):
            high_demand_count += 1
            # 5.1 จับคู่สินค้าในคลัง (link_status == 'ok')
            match_res = match_best_product_for_demand(
                db=db,
                product_keyword=product_keyword,
                budget=budget_val,
            )
            matched_product = match_res.get("best_product")
            suggested_reasons = match_res.get("suggested_reasons", [])

            # Guard: กันลิงก์ปลอม/ของ mock (https://shope.ee/...) หลุดขึ้นโพสต์ — กดแล้ว 404
            # (matcher กรองไว้ชั้นหนึ่งแล้ว แต่นี่กันซ้ำเป็นชั้นที่สอง defense-in-depth)
            if matched_product and not is_valid_shopee_affiliate_url(matched_product.affiliate_url):
                logger.warning(
                    f"Radar skip: product {matched_product.id} has non-Shopee affiliate_url "
                    f"{matched_product.affiliate_url!r} (mock/ปลอม) — treat as no-match"
                )
                matched_product = None
                suggested_reasons = []

            # 5.2 ร่างข้อความสไตล์ป้าเข็ม
            copy_text = None
            if matched_product:
                copy_text = generate_auntie_khem_deal_comment(
                    post_text=item["post_text"],
                    product_name=matched_product.name,
                    price=float(matched_product.price or 0.0),
                    rating=float(matched_product.rating or 0.0),
                    sales_count=int(matched_product.sales_count or 0),
                    affiliate_url=matched_product.affiliate_url or "https://shopee.co.th",
                    suggested_reasons=suggested_reasons,
                    lead_intent_data=analysis,
                )

            # 5.3 ตรวจสอบ Safety Guards: Category Cooldown (24h) & Daily Rate Limit
            cooldown_ok = check_category_cooldown_allowed(
                db=db,
                category=matched_product.category if matched_product else None,
            )
            daily_limit_ok = check_daily_post_limit_allowed(
                db=db,
                max_posts=daily_limit,
            )

            matched_id = matched_product.id if matched_product else None

            if not cooldown_ok or not daily_limit_ok:
                # บันทึก Demand Event สถานะ 'ignored' เมื่อติด Cooldown หรือ Daily Limit
                demand_event = models.FacebookDemandEvent(
                    lead_id=lead.id,
                    intent=intent,
                    demand_score=demand_score,
                    urgency=urgency,
                    budget=budget_text,
                    product_keyword=product_keyword,
                    matched_product_id=matched_id,
                    suggested_reason=suggested_reasons,
                    ai_comment_draft=copy_text,
                    notification_status="ignored",
                )
                db.add(demand_event)
                db.flush()

                status_str = "ignored"
                alert_sent = False
            elif matched_product and copy_text:
                # ผ่าน Safety Guards ทั้งหมด -> โพสต์ขึ้น Facebook Page ทันที
                demand_event = models.FacebookDemandEvent(
                    lead_id=lead.id,
                    intent=intent,
                    demand_score=demand_score,
                    urgency=urgency,
                    budget=budget_text,
                    product_keyword=product_keyword,
                    matched_product_id=matched_id,
                    suggested_reason=suggested_reasons,
                    ai_comment_draft=copy_text,
                    notification_status="pending",
                )
                db.add(demand_event)
                db.flush()
                # Commit ก่อน post_feed — กันบั๊ก "โพสต์ขึ้น FB แล้วแต่ record หาย"
                # (เคยเจอโพสต์ซ้ำ 4 ตัว: post_feed สำเร็จแต่ db.commit() ท้ายสุดพัง/ถูกฆ่า →
                #  lead + demand_event ถูก rollback → dedup/cooldown มองไม่เห็นโพสต์ → ยิงซ้ำได้)
                db.commit()

                image_url = (matched_product.image_url or "").strip()
                if image_url:
                    post_res = post_feed(
                        message=copy_text,
                        image_url=image_url,
                    )
                else:
                    post_res = post_feed(
                        message=copy_text,
                        link=matched_product.affiliate_url or "",
                    )

                if post_res.get("ok"):
                    demand_event.notification_status = "posted"
                    demand_event.notification_sent_at = datetime.now(timezone.utc)
                    post_id = str(post_res.get("post_id") or "")
                    post_url = f"https://www.facebook.com/{post_id}" if post_id else ""

                    # บันทึกประวัติโพสต์ลง Google Sheets ผ่าน POSTS_SHEET_WEBHOOK_URL
                    log_post_async({
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "kind": "radar",
                        "title": (matched_product.name or "")[:45],
                        "message": (copy_text or "")[:1000],
                        "link": matched_product.affiliate_url or "",
                        "post_id": post_id,
                        "post_url": post_url,
                    })
                    status_str = "deal_matched_and_posted"
                else:
                    demand_event.notification_status = "failed"
                    status_str = "deal_matched_post_failed"

                alert_sent = False
                # อัปเดตสถานะ posted/failed ให้ durable (แยกจาก commit ก่อนโพสต์)
                db.commit()
            else:
                # ไม่พบสินค้าที่ตรงกันในคลัง
                demand_event = models.FacebookDemandEvent(
                    lead_id=lead.id,
                    intent=intent,
                    demand_score=demand_score,
                    urgency=urgency,
                    budget=budget_text,
                    product_keyword=product_keyword,
                    matched_product_id=matched_id,
                    suggested_reason=suggested_reasons,
                    ai_comment_draft=copy_text,
                    notification_status="failed",
                )
                db.add(demand_event)
                db.flush()

                status_str = "deal_matched_post_failed"
                alert_sent = False
        else:
            alert_sent = False
            status_str = "low_demand_ignored"
            matched_id = None

        db.commit()

        results.append(
            schemas.IngestedLeadResult(
                fb_post_id=fb_post_id,
                lead_id=lead.id,
                status=status_str,
                demand_score=demand_score,
                intent=intent,
                alert_sent=alert_sent,
                matched_product_id=matched_id,
            )
        )
        processed_count += 1

    return schemas.LeadIngestionResponse(
        total_received=total_received,
        processed=processed_count,
        high_demand_count=high_demand_count,
        alerts_sent=0,
        results=results,
    )


@router.post("/actions", response_model=schemas.LeadActionOut)
def record_lead_action(
    payload: schemas.LeadActionCreate,
    db: Session = Depends(get_db),
    authorized: bool = Depends(require_admin_auth),
):
    """บันทึกประวัติการตัดสินใจของแอดมิน (Reply, Manual Reply, Ignore, Conversions)
    เพื่อสร้าง Data Flywheel ปรับปรุงการจับคู่สินค้าและข้อความร่าง
    """
    event = (
        db.query(models.FacebookDemandEvent)
        .filter(models.FacebookDemandEvent.id == payload.demand_event_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Demand event not found")

    lead_id = payload.lead_id or event.lead_id

    action = models.LeadAction(
        demand_event_id=event.id,
        lead_id=lead_id,
        action_type=payload.action_type,
        admin_id=payload.admin_id,
        comment_posted=payload.comment_posted,
        affiliate_link_used=payload.affiliate_link_used,
        feedback_score=payload.feedback_score,
        notes=payload.notes,
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    return action


@router.get("/stats", response_model=schemas.RadarStatsResponse)
def get_radar_stats(
    db: Session = Depends(get_db),
    authorized: bool = Depends(require_admin_auth),
):
    """ดึงสถิติภาพรวมเรดาร์ความต้องการ (Leads, Events, Actions, Conversions, Top Keywords)"""
    total_leads = db.query(func.count(models.FacebookDetectedLead.id)).scalar() or 0
    total_high_demand = db.query(func.count(models.FacebookDemandEvent.id)).scalar() or 0
    total_actions = db.query(func.count(models.LeadAction.id)).scalar() or 0
    total_clicks = db.query(func.sum(models.LeadAction.click_count)).scalar() or 0
    total_orders = db.query(func.sum(models.LeadAction.order_count)).scalar() or 0
    total_commission = db.query(func.sum(models.LeadAction.commission_earned)).scalar() or Decimal("0.00")

    # สรุป Top Demanded Keywords จาก Demand Events
    top_kw_rows = (
        db.query(
            models.FacebookDemandEvent.product_keyword,
            func.count(models.FacebookDemandEvent.id).label("count"),
        )
        .filter(models.FacebookDemandEvent.product_keyword.isnot(None))
        .group_by(models.FacebookDemandEvent.product_keyword)
        .order_by(func.count(models.FacebookDemandEvent.id).desc())
        .limit(5)
        .all()
    )

    top_keywords = [
        {"keyword": row[0], "count": int(row[1])}
        for row in top_kw_rows
        if row[0]
    ]

    return schemas.RadarStatsResponse(
        total_leads_scanned=int(total_leads),
        high_demand_leads=int(total_high_demand),
        action_taken_count=int(total_actions),
        total_clicks=int(total_clicks),
        total_orders=int(total_orders),
        total_commission_earned=Decimal(str(total_commission)),
        top_demanded_keywords=top_keywords,
    )


@router.get("/leads")
def list_radar_leads(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    authorized: bool = Depends(require_admin_auth),
):
    """เรียกดูรายการ Leads พร้อมเหตุการณ์ Demand ที่ตรวจพบ"""
    leads = (
        db.query(models.FacebookDetectedLead)
        .order_by(models.FacebookDetectedLead.detected_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    output = []
    for lead in leads:
        events = (
            db.query(models.FacebookDemandEvent)
            .filter(models.FacebookDemandEvent.lead_id == lead.id)
            .all()
        )
        event_data = []
        for ev in events:
            event_data.append({
                "id": ev.id,
                "intent": ev.intent,
                "demand_score": ev.demand_score,
                "urgency": ev.urgency,
                "budget": ev.budget,
                "product_keyword": ev.product_keyword,
                "matched_product_id": ev.matched_product_id,
                "notification_status": ev.notification_status,
                "notification_sent_at": ev.notification_sent_at,
                "ai_comment_draft": ev.ai_comment_draft,
            })

        output.append({
            "id": lead.id,
            "fb_post_id": lead.fb_post_id,
            "author_name": lead.author_name,
            "post_text": lead.post_text,
            "post_url": lead.post_url,
            "status": lead.status,
            "detected_at": lead.detected_at,
            "events": event_data,
        })

    return {
        "total": len(output),
        "leads": output,
    }


@router.get("/groups", response_model=List[schemas.FacebookGroupMonitorOut])
def list_active_groups(
    db: Session = Depends(get_db),
    authorized: bool = Depends(require_admin_auth),
):
    """ดึงรายการกลุ่ม Facebook ทั้งหมดที่มีสถานะ Active"""
    groups = (
        db.query(models.FacebookGroupMonitor)
        .filter(models.FacebookGroupMonitor.is_active == True)
        .all()
    )
    return groups


@router.post("/groups", response_model=schemas.FacebookGroupMonitorOut)
def add_new_group(
    payload: schemas.FacebookGroupMonitorCreate,
    db: Session = Depends(get_db),
    authorized: bool = Depends(require_admin_auth),
):
    """เพิ่มกลุ่ม Facebook เป้าหมายใหม่เข้าระบบเพื่อเฝ้าส่อง"""
    # Check duplicate
    existing = (
        db.query(models.FacebookGroupMonitor)
        .filter(models.FacebookGroupMonitor.group_id == payload.group_id)
        .first()
    )
    if existing:
        existing.is_active = True
        existing.group_name = payload.group_name
        existing.group_url = payload.group_url
        db.commit()
        db.refresh(existing)
        return existing

    new_group = models.FacebookGroupMonitor(
        group_id=payload.group_id,
        group_name=payload.group_name,
        group_url=payload.group_url,
        is_active=True,
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group


from pydantic import BaseModel

class InsightsPayload(BaseModel):
    insights_text: str

@router.post("/insights/analyze")
def analyze_fb_page_insights(
    payload: InsightsPayload,
    db: Session = Depends(get_db),
    authorized: bool = Depends(require_admin_auth),
):
    """วิเคราะห์ข้อความสถิติ Facebook Reels/Post Insights ดิบด้วย AI และบันทึกประวัติการพัฒนา"""
    # 1. วิเคราะห์ด้วย AI
    analysis_res = analyze_facebook_insights(payload.insights_text)
    
    # 2. บันทึกลงใน SystemPreference
    pref = db.query(models.SystemPreference).filter(models.SystemPreference.key == "facebook_insights_history").first()
    history = []
    if pref and isinstance(pref.value, list):
        history = pref.value
    
    # เพิ่มรายการใหม่
    new_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw_text": payload.insights_text,
        "parsed_metrics": analysis_res
    }
    history.insert(0, new_record)
    
    # จำกัดประวัติไว้สูงสุด 20 รายการเพื่อประหยัดพื้นที่
    history = history[:20]
    
    if pref:
        pref.value = history
        pref.updated_at = datetime.now(timezone.utc)
    else:
        db.add(models.SystemPreference(key="facebook_insights_history", value=history))
        
    db.commit()
    
    # 3. สั่งรันอัปเดตสมองกลร่วม (Hermes AI) ทันที
    try:
        from app.services.hermes_brain import analyze_market
        analyze_market(db)
    except Exception as e:
        logger.warning(f"Failed to auto-trigger Hermes AI market analysis: {e}")
        
    return {
        "status": "success",
        "parsed_metrics": analysis_res
    }


