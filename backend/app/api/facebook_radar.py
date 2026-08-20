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
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db
from app.services.demand_radar_ai import (
    analyze_lead_intent_and_demand,
    generate_auntie_khem_deal_comment,
    is_high_demand,
    analyze_facebook_insights,
)
from app.services.facebook_poster import (
    log_post_async, post_feed, preflight_ready, notify_owner_once, classify_post_error,
)
from app.services.hermes_brain import load_skills_safe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/facebook-radar", tags=["facebook-radar"])

COOKIE_NAME = "pkh_admin"

# ห้ามให้ daily post limit เกินค่านี้ — กัน misconfig/Hermes ทำให้เพจล้นโพสต์
MAX_DAILY_POSTS_CAP = 25

# fb_post_id ที่ขึ้นต้นด้วยคำพวกนี้ = lead ทดสอบ/หลอก (สคริปต์เทสต์/sample) —
# ห้ามหลุดเข้า production เพราะจะสร้างแถว demand event 'posted' หลอก
# แล้วไปอุดตัน daily-limit counter (เจอจริง 15/08: fb_mock_bulk_* 100 แถวใน 7 วิ)
# หมายเหตุ: ไม่รวม "test_" เพราะ pytest ใช้ post_id แบบ test_* กับ SQLite test DB เอง
TEST_LEAD_PREFIXES = ("fb_sample_", "fb_mock_", "demo_")

# ลิงก์โปรโมตของคนอื่น/ลิงก์ปลอมใน post_text = โพสต์สแปม ไม่ใช่ buyer demand — กันไม่ให้เข้าเป็น lead
# (เจอจริง 16/08: โพสต์ AI-generated แปะลิงก์ affiliate ของรายอื่น 46 แถวใน 3 กลุ่ม ต้องล้างมือ)
# - lazada.co.th  = แพลตฟอร์มอื่น (s.lazada.co.th / S.LAZADA.CO.TH)
# - s.shopee.co.th = ลิงก์ affiliate Shopee ของรายอื่น (โปรโมตของตัวเอง ไม่ใช่คนอยากซื้อ)
# - shope.ee      = ลิงก์ปลอม (กดแล้ว 404) — ชั้นเดียวกับ DB link policy
SPAM_LINK_MARKERS = ("lazada.co.th", "s.shopee.co.th", "shope.ee")


def _looks_like_test_lead(fb_post_id: str) -> bool:
    """True เมื่อ fb_post_id เป็น lead ทดสอบ/หลอก (ไม่ใช่โพสต์จริงจากกลุ่ม FB)."""
    return (fb_post_id or "").strip().lower().startswith(TEST_LEAD_PREFIXES)


def _looks_like_spam_link(post_text: str) -> bool:
    """True เมื่อ post_text มีลิงก์ Lazada/Shopee-affiliate ของคนอื่น หรือลิงก์ปลอม.

    โพสต์แบบนี้คือโฆษณาโปรโมตของรายอื่น ไม่ใช่ความต้องการซื้อ — ตัดทิ้งก่อนวิเคราะห์
    เพื่อไม่ให้ไปสร้าง lead/stat หลอก และไม่เสีย LLM call.
    """
    text = (post_text or "").strip().lower()
    return any(marker in text for marker in SPAM_LINK_MARKERS)


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
    # นับได้ 2 ทาง: (ก) event เก่าที่มี matched_product → เทียบ Product.category; (ข) pivot แล้ว
    # matched_product_id เป็น None → เทียบ product_keyword ที่เก็บใน event (รองรับทั้งคู่)
    recent_count = (
        db.query(models.FacebookDemandEvent.id)
        .outerjoin(models.Product, models.FacebookDemandEvent.matched_product_id == models.Product.id)
        .filter(
            models.FacebookDemandEvent.notification_status.in_(["posted", "sent", "pending"]),
            models.FacebookDemandEvent.created_at >= cutoff,
            or_(
                models.Product.category == category,
                models.FacebookDemandEvent.product_keyword == category,
            ),
        )
        .count()
    )
    if recent_count:
        return False

    # กัน radar โพสต์หมวดที่ cron rotation เพิ่งโพสต์ (CampaignLog status=fbpost) —
    # ไม่งั้น cron โพสต์หูฟังแล้ว radar ตามโพสต์หูฟังอีกภายใน cooldown (หมวดเดียวถี่เกิน)
    # นับ 'fbpost_pending' ด้วย = cron จองหมวดก่อนยิงโพสต์ (commit ก่อน post_feed) —
    # กัน radar ยิงหมวดเดียวกันซ้ำในหน้าต่างที่ cron กำลังโพสต์ (ปิดช่องขัดกันทั้ง 2 ทาง)
    cron_ids = [int(c.category) for c in db.query(models.CampaignLog.category)
                .filter(models.CampaignLog.status.in_(["fbpost", "fbpost_pending"]),
                        models.CampaignLog.created_at >= cutoff).all()
                if str(c.category).isdigit()]
    if cron_ids:
        cron_cat_count = (
            db.query(models.Product.id)
            .filter(models.Product.id.in_(cron_ids),
                    models.Product.category == category)
            .count()
        )
        if cron_cat_count:
            return False
    return True


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

        # 0.5 กันโพสต์สแปมโปรโมตลิงก์ของคนอื่น (Lazada / Shopee affiliate ของรายอื่น) —
        #     ไม่ใช่ buyer demand อย่าให้เข้าเป็น lead/stat หลอก (เคยปน 46 แถวใน 3 กลุ่ม 16/08)
        if _looks_like_spam_link(item["post_text"]):
            results.append(
                schemas.IngestedLeadResult(
                    fb_post_id=fb_post_id,
                    lead_id=None,
                    status="spam_link_skipped",
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

        # 2. บันทึกโพสต์ดิบ FacebookDetectedLead
        lead = models.FacebookDetectedLead(
            fb_post_id=fb_post_id,
            post_url=item["post_url"],
            author_name=item["author_name"],
            post_text=item["post_text"],
            post_time=item["post_time"] or datetime.now(timezone.utc),
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
            matched_id = None
            suggested_reasons = []
            
            # ไม่เกี่ยวกับสินค้าในคลังแล้ว: ร่างข้อความแนะนำการติดตั้งบอทป้าเข็มและแพ็กเกจ (ฉบับลดคำซ้ำซ้อน)
            line_oa_url = os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
            copy_text = (
                f"อยากใช้บอทช่วยขายของ Shopee (บอทป้าเข็ม) ป้าจัดการระบบให้พร้อมใช้ทันทีจ้า 😊\n"
                f"🛠️ ปลอดภัยรันบนบัญชี/คีย์คุณเอง แอดมินดูแลหลังบ้านให้หมด ไม่ต้องเซ็ตค่าเองให้ปวดหัวจ้า\n"
                f"💼 เริ่มต้น 490.- แอดไลน์คุยรายละเอียดแพ็กเกจกับป้าเลยจ้า 👉 {line_oa_url}"
            )

            # 5.3 ทุก lead ลงเพจป้าเข็มผ่าน post_feed
            if not copy_text:
                # ไม่มีข้อความที่จะโพสต์ → บันทึก failed (เคสเดียวกับ "ไม่พบสินค้า" เดิม)
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
                # ── Flow B: เพจป้าเข็ม → cooldown + daily limit + preflight แล้ว post_feed (Graph API) ──
                cooldown_ok = check_category_cooldown_allowed(
                    db=db,
                    category=product_keyword,
                )
                daily_limit_ok = check_daily_post_limit_allowed(
                    db=db,
                    max_posts=daily_limit,
                )
                if not cooldown_ok or not daily_limit_ok:
                    # ติด cooldown/โควต้าเพจ → ไม่โพสต์ บันทึก ignored
                    demand_event = models.FacebookDemandEvent(
                        lead_id=lead.id,
                        intent=intent,
                        demand_score=demand_score,
                        urgency=urgency,
                        budget=budget_text,
                        product_keyword=product_keyword,
                        matched_product_id=None,
                        suggested_reason=[],
                        ai_comment_draft=copy_text,
                        notification_status="ignored",
                    )
                    db.add(demand_event)
                    db.flush()
                    status_str = "ignored"
                    alert_sent = False
                else:
                    preflight_ok, preflight_reasons = preflight_ready()
                    if not preflight_ok:
                        # ไม่พร้อม (token ตั้ง/ใช้ได้) → ข้ามโพสต์ + แจ้งเจ้าของ (contract เดิม)
                        notify_owner_once("fb_preflight_radar",
                                          "⚠️ ข้ามโพสต์ radar (ยังไม่พร้อม): "
                                          + "; ".join(preflight_reasons))
                        demand_event = models.FacebookDemandEvent(
                            lead_id=lead.id,
                            intent=intent,
                            demand_score=demand_score,
                            urgency=urgency,
                            budget=budget_text,
                            product_keyword=product_keyword,
                            matched_product_id=None,
                            suggested_reason=[],
                            ai_comment_draft=copy_text,
                            notification_status="failed",
                        )
                        db.add(demand_event)
                        db.flush()
                        db.commit()  # persist failed — ไม่โพสต์
                        status_str = "deal_matched_post_failed"
                        alert_sent = False
                    else:
                        # พร้อม → commit pending ก่อน post_feed (กันโพสต์แล้ว record หาย)
                        demand_event = models.FacebookDemandEvent(
                            lead_id=lead.id,
                            intent=intent,
                            demand_score=demand_score,
                            urgency=urgency,
                            budget=budget_text,
                            product_keyword=product_keyword,
                            matched_product_id=None,
                            suggested_reason=[],
                            ai_comment_draft=copy_text,
                            notification_status="pending",
                        )
                        db.add(demand_event)
                        db.flush()
                        db.commit()

                        # ยิงขึ้นเพจหลักเป็นข้อความธรรมดา (ไม่มีภาพสินค้า)
                        post_res = post_feed(
                            message=copy_text,
                        )

                        if post_res.get("ok"):
                            demand_event.notification_status = "posted"
                            demand_event.notification_sent_at = datetime.now(timezone.utc)
                            post_id = str(post_res.get("post_id") or "")
                            post_url = f"https://www.facebook.com/{post_id}" if post_id else ""

                            # บันทึกประวัติโพสต์ลง Google Sheets (pivot: ไม่มีสินค้า → title=ข้อความ, link ว่าง)
                            log_post_async({
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "kind": "radar",
                                "title": (copy_text or "")[:45],
                                "message": (copy_text or "")[:1000],
                                "link": "",
                                "post_id": post_id,
                                "post_url": post_url,
                            })
                            status_str = "deal_matched_and_posted"
                        else:
                            demand_event.notification_status = "failed"
                            status_str = "deal_matched_post_failed"
                            # error รุนแรง (token หมดอายุ/สิทธิ์หาย/rate-limit) → แจ้งเจ้าของด้วย
                            if classify_post_error(post_res.get("error") or ""):
                                notify_owner_once("fb_post_hard_error",
                                                  f"⚠️ โพสต์ radar ล้ม (error รุนแรง): "
                                                  f"{post_res.get('error') or ''}")

                        alert_sent = False
                        # อัปเดตสถานะ posted/failed ให้ durable (แยกจาก commit ก่อนโพสต์)
                        db.commit()
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



