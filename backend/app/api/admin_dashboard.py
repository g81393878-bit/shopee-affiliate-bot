# -*- coding: utf-8 -*-
"""
แดชบอร์ดแอดมิน (เว็บ) — ดู/แก้สินค้า/สถิติผ่านเบราว์เซอร์
================================================================
- หน้าเว็บ: GET /admin  (ล็อกอินด้วยรหัสผ่าน → cookie 7 วัน)
- API: /api/admin/*  (ต้องมี cookie ถึงเรียกได้)
- ข้อมูลจากตาราง Supabase เดียวกัน (products/contents/chat_logs/users) —
  ไม่มีตัวเลขมโน ตัวเลขทุกตัว query จาก DB จริง

ความปลอดภัย:
- รหัสผ่าน = env ADMIN_DASHBOARD_PASSWORD (ถ้าไม่ตั้ง ใช้ CRON_TOKEN แทน;
  ถ้าไม่ตั้งทั้งคู่ → ปิดใช้งาน แสดงข้อความชัดเจน)
- session = HMAC-signed cookie (stdlib เท่านั้น ไม่พึ่ง external dep)
"""
import datetime
import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app import models
from app.services.link_checker import check_affiliate_link
from app.services.ai_analyzer import calculate_heuristic_score

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

STATUS_VALUES = {"ok", "dead", "suspect", "unknown", "none"}
MIN_SALES = int(os.getenv("MIN_SALES", "2000"))
SESSION_TTL = 7 * 24 * 3600  # cookie อายุ 7 วัน
COOKIE_NAME = "pkh_admin"
_ADMIN_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "static", "admin.html")


def _password() -> str:
    """รหัสผ่านแดชบอร์ด — ADMIN_DASHBOARD_PASSWORD ก่อน, สำรอง CRON_TOKEN"""
    return (os.getenv("ADMIN_DASHBOARD_PASSWORD") or os.getenv("CRON_TOKEN") or "").strip()


def _sign(payload: str) -> str:
    return hmac.new(_password().encode(), payload.encode(), hashlib.sha256).hexdigest()


def _make_session() -> str:
    payload = str(int(time.time()) + SESSION_TTL)
    return f"{payload}.{_sign(payload)}"


def _check_session(cookie: str) -> bool:
    if not cookie or not _password():
        return False
    try:
        payload, sig = cookie.rsplit(".", 1)
        return hmac.compare_digest(sig, _sign(payload)) and int(payload) > time.time()
    except Exception:
        return False


def require_admin(session: str = Cookie(default="", alias=COOKIE_NAME)) -> None:
    if not _password():
        raise HTTPException(status_code=503, detail="ยังไม่ได้ตั้งรหัสผ่านแอดมิน (ADMIN_DASHBOARD_PASSWORD)")
    if not _check_session(session):
        raise HTTPException(status_code=401, detail="กรุณาล็อกอินก่อน")


def _db() -> Session:
    return SessionLocal()


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n or 0)


# ---------------------------------------------------------------------------
# หน้าเว็บ + ล็อกอิน
# ---------------------------------------------------------------------------

@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return FileResponse(_ADMIN_HTML)


@router.post("/admin/login")
def admin_login(password: str = Form(...)):
    if not _password():
        return JSONResponse({"error": "ยังไม่ได้ตั้งรหัสผ่านแอดมิน (ADMIN_DASHBOARD_PASSWORD)"}, status_code=503)
    if not hmac.compare_digest(password, _password()):
        return JSONResponse({"error": "รหัสผ่านไม่ถูกต้อง"}, status_code=401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE_NAME, _make_session(), max_age=SESSION_TTL, httponly=True,
                    samesite="lax", secure=False)
    return resp


@router.post("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/admin", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/api/admin/session")
def admin_session(_: None = Depends(require_admin)):
    return {"logged_in": True, "expires_in_days": SESSION_TTL // 86400}


# ---------------------------------------------------------------------------
# สถิติ
# ---------------------------------------------------------------------------

@router.get("/api/admin/stats")
def admin_stats(_: None = Depends(require_admin)):
    db = _db()
    try:
        total = db.query(models.Product).count()
        sellable = (db.query(models.Product)
                       .filter(models.Product.link_status == "ok",
                               models.Product.sales_count >= MIN_SALES).count())
        dead = db.query(models.Product).filter(models.Product.link_status == "dead").count()
        hidden = (db.query(models.Product)
                    .filter(models.Product.link_status != "ok",
                            models.Product.link_status != "dead").count())
        with_content = {c.product_id for c in db.query(models.Content).all()}
        no_content = max(0, total - len(with_content))

        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(hours=24)
        users = db.query(models.User).count()
        chats = db.query(models.ChatLog).filter(models.ChatLog.created_at >= cutoff).count()
        searches = (db.query(models.ChatLog.line_user_id)
                       .filter(models.ChatLog.created_at >= cutoff,
                               models.ChatLog.intent == "search").distinct().count())
        wismo = (db.query(models.ChatLog)
                    .filter(models.ChatLog.created_at >= cutoff,
                            models.ChatLog.intent == "wismo").count())

        by_cat = (db.query(models.Product.category, func.count(models.Product.id))
                    .group_by(models.Product.category)
                    .order_by(func.count(models.Product.id).desc()).limit(8).all())
        top_sellers = (db.query(models.Product)
                          .filter(models.Product.link_status == "ok",
                                  models.Product.sales_count >= MIN_SALES)
                          .order_by(models.Product.sales_count.desc()).limit(5).all())
        newest = (db.query(models.Product)
                     .order_by(models.Product.created_at.desc()).limit(5).all())

        return {
            "totals": {
                "total": total, "sellable": sellable, "hidden": hidden, "dead": dead,
                "no_content": no_content, "users": users,
            },
            "today": {"chats": chats, "searchers": searches, "wismo": wismo},
            "by_category": [{"category": c or "อื่นๆ", "count": n} for c, n in by_cat],
            "top_sellers": [{"id": p.id, "name": p.name, "price": float(p.price or 0),
                             "sales": p.sales_count or 0, "commission": float(p.commission or 0)}
                            for p in top_sellers],
            "newest": [{"id": p.id, "name": p.name, "category": p.category,
                        "price": float(p.price or 0),
                        "created_at": (p.created_at or now).isoformat()} for p in newest],
        }
    finally:
        db.close()


@router.get("/api/admin/quota")
def admin_quota(_: None = Depends(require_admin)):
    """LINE push quota เดือนนี้ — เพดาน/ใช้ไป/เหลือ/สถานะเตือน (แสดงในหน้าแอดมิน)"""
    from app.services.line_quota import quota_info

    info = quota_info()
    if info is None:
        return {"checked": False,
                "note": "ตรวจ quota ไม่ได้ (โหมด mock / แผนไม่จำกัด / LINE API error) — push ไม่ถูกบล็อก"}
    warn_left = int(os.getenv("PUSH_QUOTA_WARN_LEFT", "30") or 30)
    return {
        "checked": True,
        "limit": info["limit"],
        "used": info["used"],
        "remaining": info["remaining"],
        "warn_left": warn_left,
        "warning": info["remaining"] <= warn_left,
        "blocked": info["remaining"] <= 0,
    }


@router.get("/api/admin/categories")
def admin_categories(_: None = Depends(require_admin)):
    db = _db()
    try:
        rows = (db.query(models.Product.category, func.count(models.Product.id))
                  .group_by(models.Product.category)
                  .order_by(func.count(models.Product.id).desc()).all())
        return [{"category": c or "อื่นๆ", "count": n} for c, n in rows]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# สินค้า: ค้น/กรอง/หน้า
# ---------------------------------------------------------------------------

@router.get("/api/admin/products")
def admin_products(
    q: str = "",
    cat: str = "",
    status: str = "",
    sort: str = "new",
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    _: None = Depends(require_admin),
):
    db = _db()
    try:
        query = db.query(models.Product)
        qq = q.strip()
        if qq:
            like = f"%{qq}%"
            query = query.filter((models.Product.name.ilike(like)) |
                                 (models.Product.category.ilike(like)))
        if cat:
            query = query.filter(models.Product.category == cat)
        if status:
            query = query.filter(models.Product.link_status == status)
        total = query.count()
        if sort == "sales":
            query = query.order_by(models.Product.sales_count.desc().nullslast())
        elif sort == "price":
            query = query.order_by(models.Product.price.desc().nullslast())
        elif sort == "score":
            query = query.order_by(models.Product.ai_score.desc().nullslast())
        else:
            query = query.order_by(models.Product.created_at.desc().nullslast())
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
        return {
            "total": total,
            "page": page,
            "pages": max(1, (total + per_page - 1) // per_page),
            "items": [{
                "id": p.id, "name": p.name, "category": p.category or "อื่นๆ",
                "price": float(p.price or 0), "commission": float(p.commission or 0),
                "sales_count": p.sales_count or 0, "rating": float(p.rating or 0),
                "ai_score": p.ai_score or 0, "link_status": p.link_status,
                "affiliate_url": p.affiliate_url,
                "created_at": (p.created_at or datetime.datetime.now(datetime.timezone.utc)).isoformat(),
            } for p in rows],
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# สินค้า: แก้ / ลบ
# ---------------------------------------------------------------------------

@router.post("/api/admin/products")
def admin_create_product(_: None = Depends(require_admin),
                         name: str = Form(...),
                         affiliate_url: str = Form(...),
                         category: str = Form(None),
                         price: float = Form(0.0),
                         commission: float = Form(0.0),
                         sales_count: int = Form(0),
                         rating: float = Form(0.0)):
    """เพิ่มสินค้าทีละตัว — ตรวจลิงก์ affiliate ก่อนบันทึก (นโยบายเด็ดขาด)"""
    db = _db()
    try:
        name = (name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="ต้องระบุชื่อสินค้า")
        url = (affiliate_url or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="ต้องระบุ affiliate_url (ลิงก์สั้น s.shopee.co.th)")
        status, detail = check_affiliate_link(url)
        if status != "OK":
            raise HTTPException(status_code=400, detail=f"ลิงก์ตรวจไม่ผ่าน ({status}: {detail})")
        ai_score = calculate_heuristic_score(
            sales_count=sales_count or 0,
            rating=float(rating or 0.0),
            commission=float(commission or 0.0),
            price=float(price or 0.0),
        )
        p = models.Product(
            name=name,
            category=(category or "").strip() or None,
            price=price or 0.0,
            commission=commission or 0.0,
            sales_count=sales_count or 0,
            rating=rating or 0.0,
            affiliate_url=url,
            link_status="ok",
            ai_score=ai_score,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        logger.info(f"Admin created product {p.id} ({name[:40]})")
        return {"ok": True, "id": p.id}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Admin create product failed: {e}")
        raise HTTPException(status_code=400, detail=str(e)[:200])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Shopee Affiliate Open API — สถานะ + ค้นจากคลัง (credentials ยังรออนุมัติ)
# ---------------------------------------------------------------------------

def _shopee_api_ready() -> bool:
    return bool((os.getenv("SHOPEE_AFFILIATE_PARTNER_ID") or "").strip()) and \
           bool((os.getenv("SHOPEE_AFFILIATE_SECRET") or "").strip())


@router.get("/api/admin/shopee-api/status")
def admin_shopee_api_status(_: None = Depends(require_admin)):
    partner_set = bool((os.getenv("SHOPEE_AFFILIATE_PARTNER_ID") or "").strip())
    secret_set = bool((os.getenv("SHOPEE_AFFILIATE_SECRET") or "").strip())
    return {
        "configured": partner_set and secret_set,
        "partner_id_set": partner_set,
        "secret_set": secret_set,
        "message": ("✅ พร้อมใช้งาน" if (partner_set and secret_set)
                    else "ยังไม่ได้ตั้งค่า SHOPEE_AFFILIATE_PARTNER_ID / SECRET — "
                         "รอ Shopee อนุมัติ Open API (เกณฑ์ >1,000 ออเดอร์/เดือน) แล้วใส่ค่าลง Render"),
    }


@router.post("/api/admin/shopee-api/search")
def admin_shopee_api_search(_: None = Depends(require_admin),
                            keyword: str = Form(""),
                            limit: int = Form(10)):
    """ค้นสินค้าทั้งคลังจาก Shopee Affiliate Open API (อ่านอย่างเดียว ไม่เขียน DB)."""
    if not _shopee_api_ready():
        raise HTTPException(status_code=503,
                            detail="ยังไม่ได้ตั้งค่า SHOPEE_AFFILIATE_PARTNER_ID / SECRET — รออนุมัติ Open API ก่อน")
    keyword = (keyword or "").strip()
    limit = max(1, min(50, int(limit)))
    try:
        from app.services.shopee_api import ShopeeAffiliateClient
        client = ShopeeAffiliateClient()
        data = client.search_products(keyword=keyword or None, limit=limit)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)[:200])
    except Exception as e:
        logger.error(f"Shopee API search failed: {e}")
        raise HTTPException(status_code=502, detail=f"Shopee API error: {str(e)[:200]}")
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    items = [{
        "item_id": n.get("itemId"),
        "name": n.get("productName"),
        "offer_link": n.get("offerLink"),
        "product_link": n.get("productLink"),
        "image_url": n.get("imageUrl"),
        "price_min": n.get("priceMin"),
        "price_max": n.get("priceMax"),
        "commission_rate": n.get("commissionRate"),
        "sales": n.get("sales"),
        "rating": n.get("ratingStar"),
        "shop_name": n.get("shopName"),
    } for n in nodes]
    return {"total": len(items), "items": items}


@router.post("/api/admin/products/{pid}")
def admin_update_product(pid: int, _: None = Depends(require_admin),
                         name: str = Form(None), category: str = Form(None),
                         price: float = Form(None), commission: float = Form(None),
                         sales_count: int = Form(None), ai_score: int = Form(None),
                         rating: float = Form(None), link_status: str = Form(None)):
    db = _db()
    try:
        p = db.query(models.Product).filter(models.Product.id == pid).first()
        if not p:
            raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
        if name is not None:
            name = name.strip()
            if name:
                p.name = name
        if category is not None:
            p.category = category.strip() or None
        if price is not None:
            p.price = max(0, price)
        if commission is not None:
            p.commission = max(0, commission)
        if sales_count is not None:
            p.sales_count = max(0, int(sales_count))
        if ai_score is not None:
            p.ai_score = max(0, min(100, int(ai_score)))
        if rating is not None:
            p.rating = max(0, min(5, float(rating)))
        if link_status is not None:
            link_status = link_status.strip().lower()
            if link_status not in STATUS_VALUES:
                raise HTTPException(status_code=400, detail=f"link_status ต้องเป็น {sorted(STATUS_VALUES)}")
            p.link_status = link_status
        db.commit()
        db.refresh(p)
        logger.info(f"Admin updated product {pid}")
        return {"ok": True, "id": p.id, "link_status": p.link_status}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Admin update product {pid} failed: {e}")
        raise HTTPException(status_code=400, detail=str(e)[:200])
    finally:
        db.close()


@router.delete("/api/admin/products/{pid}")
def admin_delete_product(pid: int, _: None = Depends(require_admin)):
    db = _db()
    try:
        p = db.query(models.Product).filter(models.Product.id == pid).first()
        if not p:
            raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
        db.delete(p)  # cascade ลบ contents/product_analysis อัตโนมัติ
        db.commit()
        logger.info(f"Admin deleted product {pid} ({p.name[:40]})")
        return {"ok": True, "id": pid}
    finally:
        db.close()
