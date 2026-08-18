# -*- coding: utf-8 -*-
"""
Cron endpoints — ให้บอทดูแลตัวเองเป็นระยะ (เรียกจาก cron-job.org วันละครั้ง)
==========================================================================
- POST /api/cron/check-links   → ตรวจลิงก์ทุกตัว + อัปเดต link_status ลงตาราง
                                   (บอทจะซ่อนตัวเสียเองอัตโนมัติ)
- POST /api/cron/analyze       → สร้าง Hook/คอนเทนต์ AI ให้สินค้าที่ยังไม่มี

ความปลอดภัย: ถ้าตั้ง env CRON_TOKEN ต้องส่ง ?token= ถึงจะรันได้ (ถ้าไม่ตั้ง = เปิด
เหมือน /health) — แนะนำตั้ง CRON_TOKEN ที่ Render dashboard แล้วใส่ใน cron-job.org

นโยบายเด็ดขาด: ตรวจอัตโนมัติจะลดสถานะเป็น dead เฉพาะเมื่อยืนยันชัด (HTTP 400/404/410
หรือหน้า "ไม่พบสินค้า") — ไม่ลดสถานะ ok → suspect/unknown (กันกรณี IP ของ Render
โดน Shopee บล็อกแล้วผลออกมาเป็น SUSPECT ทั้งคลัง)
"""
import os
import logging
import threading
import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app import models
from app.services.link_checker import check_affiliate_link, is_valid_shopee_affiliate_url
from app.services.ai_generator import format_hashtags_text, generate_script_for_product
from app.services.hermes_brain import analyze_market, market_tone
from app.services.price_refresh import refresh_price
from app.services.line_quota import push_guard
from app.services.product_cards import product_cards_message
from app.services.facebook_poster import (
    post_feed,
    log_post_async,
    fetch_page_posts,
    delete_page_post,
    is_fake_link_post,
    _normalize_shopee_link,
    preflight_ready,
    notify_owner_once,
    classify_post_error,
)
from app.services.facebook_intro import intro_posts, short_bg_posts
from app.services.facebook_curated import fetch_news_items, item_key, curate_caption
from app.services.facebook_local import fetch_local_items, item_key as local_item_key, curate_local_caption
from app.services.bot_profile import line_cta_footer
from app.services.product_image import fetch_product_image
from linebot import LineBotApi
from linebot.models import TextSendMessage

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "mock_line_channel_token")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cron", tags=["cron"])


def _authorized(token: str) -> bool:
    expected = os.getenv("CRON_TOKEN", "")
    return not expected or token == expected


def merge_status(old: Optional[str], new: str) -> str:
    """รวมผลตรวจเข้ากับสถานะเดิม — ป้องกันลดสถานะ ok โดยไม่จำเป็น"""
    if new in ("OK", "DEAD"):
        return new.lower()
    if old == "ok":
        return old  # SUSPECT/UNKNOWN (อาจเป็น IP โดนบล็อก) อย่าไปลดสถานะที่เคย ok
    return new.lower()


@router.post("/check-links")
def cron_check_links(token: str = "", limit: int = 500):
    if not _authorized(token):
        raise HTTPException(status_code=401, detail="invalid token")
    db = SessionLocal()
    try:
        prods = [p for p in db.query(models.Product).all() if p.affiliate_url][:limit]
        dead_ids, ok_count, kept = [], 0, 0
        for p in prods:
            new_status, detail = check_affiliate_link(p.affiliate_url)
            merged = merge_status(p.link_status, new_status)
            if merged == "dead" and p.link_status != "dead":
                dead_ids.append({"id": p.id, "name": p.name[:50], "detail": detail})
            elif merged == "ok" and p.link_status != "ok":
                ok_count += 1
            elif merged == p.link_status:
                kept += 1
            p.link_status = merged
        db.commit()
        return {
            "checked": len(prods),
            "newly_dead": dead_ids,
            "newly_ok": ok_count,
            "unchanged": kept,
            "policy": "bot serves link_status == 'ok' only",
        }
    finally:
        db.close()


@router.post("/analyze")
def cron_analyze(token: str = "", limit: int = 5):
    if not _authorized(token):
        raise HTTPException(status_code=401, detail="invalid token")
    db = SessionLocal()
    try:
        with_content = {c.product_id for c in db.query(models.Content).all()}
        missing = [p for p in db.query(models.Product).all() if p.id not in with_content]
        missing.sort(key=lambda p: p.ai_score or 0, reverse=True)
        tone = market_tone(db)  # Hermes hot-reload: ท่าทีตามสถานการณ์ตลาด
        done, failed = [], []
        for p in missing[:limit]:
            try:
                data = generate_script_for_product(p.name, p.category or "", float(p.price or 0), "Standard", market_tone=tone)
                caption = data.get("caption", "")
                hashtags = format_hashtags_text(data.get("hashtags"))
                if hashtags:
                    caption = (caption + "\n\n" + hashtags).strip()
                db.add(models.Content(
                    product_id=p.id, style="Standard",
                    hook=data.get("hook"), problem=data.get("problem"),
                    solution=data.get("solution"), cta=data.get("cta"), caption=caption,
                ))
                db.commit()
                done.append({"id": p.id, "name": p.name[:50]})
            except Exception as e:
                db.rollback()
                logger.error(f"analyze failed for {p.id}: {e}")
                failed.append({"id": p.id, "name": p.name[:50], "error": str(e)[:80]})
        return {"generated": done, "failed": failed, "still_missing": max(0, len(missing) - len(done))}
    finally:
        db.close()


@router.post("/hermes-learn")
def cron_hermes_learn(token: str = ""):
    """Hermes AI learning loop — วิเคราะห์ตลาด 48 ชม. แล้วให้ Groq ปรับ skills (hot-reload)

    เรียกจาก cron-job.org วันละ 1 ครั้ง (ต้องส่ง ?token=<CRON_TOKEN>). LLM ล้ม →
    คืน learned=False และไม่เขียนทับ skills เดิม (fail-safe).
    """
    if not _authorized(token):
        raise HTTPException(status_code=401, detail="invalid token")
    db = SessionLocal()
    try:
        result = analyze_market(db)
        if result is None:
            return {
                "learned": False,
                "detail": "LLM unavailable (ไม่มี GROQ_API_KEY หรือทุก key ล้ม) — skills คงเดิม",
            }
        return {
            "learned": True,
            "skills": result["skills"],
            "reason": result["reason"],
            "market": result["report"],
        }
    finally:
        db.close()


@router.post("/refresh-prices")
def cron_refresh_prices(token: str = "", limit: int = 300):
    """อัปเดตราคาปัจจุบันจากหน้าเว็บ Shopee (best-effort)
    - เปิดหน้าเว็บสินค้าทุกตัว (ลิงก์ affiliate) → อ่านราคาจาก HTML → อัปเดต
    - ราคาเปลี่ยน → บันทึก price_history + ถ้าลด ≥ PRICE_DROP_PCT (ค่าเริ่มต้น 5%)
      แจ้งเตือนราคาตกให้ลูกค้าที่สนใจหมวดนั้น (จำกัดคน/ตัว กันสแปม)
    - โดนบล็อก/หาไม่เจอ → คงราคาเดิม ไม่พัง (การ์ดลูกค้าแสดง "ราคาเริ่มต้น")
    - พอได้ Open API จะแทนที่ด้วยข้อมูลทางการ (productOfferV2 priceMin/priceMax)
    """
    if not _authorized(token):
        raise HTTPException(status_code=401, detail="invalid token")
    import datetime
    from sqlalchemy import func as _func
    db = SessionLocal()
    try:
        drop_pct_min = float(os.getenv("PRICE_DROP_PCT", "5") or 5)
        admin_uid = os.getenv("ADMIN_LINE_USER_ID", "Uc88eb3896b0e4bcc5fbaa9b78ac1294e")
        now = datetime.datetime.now(datetime.timezone.utc)
        prods = [p for p in db.query(models.Product).all()
                 if p.affiliate_url and p.link_status == "ok"][:limit]
        updated, unchanged, blocked = [], 0, 0
        drops = []  # (product, old, new, drop_pct) — ใช้แจ้งราคาตก
        for p in prods:
            changed, old, new, detail = refresh_price(p)
            if changed:
                p.price_checked_at = now
                updated.append({"id": p.id, "name": p.name[:45], "price": str(p.price), "detail": detail})
                drop_pct = round((old - new) / old * 100, 2) if old > 0 else 0.0
                db.add(models.PriceHistory(product_id=p.id, price_old=old, price_new=new,
                                           drop_pct=drop_pct if drop_pct > 0 else None))
                if drop_pct >= drop_pct_min:
                    drops.append((p, old, new, drop_pct))
            elif detail == "ok":
                p.price_checked_at = now
                unchanged += 1
            else:
                blocked += 1
        db.commit()

        # แจ้งเตือนราคาตก — เฉพาะข้อมูลจริง: ลูกค้าที่เคยค้นหมวดนี้ (90 วัน, ไม่ใช่เจ้าของ)
        alerted, alerted_detail = 0, []
        quota_ok = push_guard(db)
        if not quota_ok:
            alerted_detail = ["ข้ามแจ้งราคาลง: LINE push quota หมด"]
        for prod, old, new, dp in (drops[:5] if quota_ok else []):
            interested = (db.query(models.ChatLog.line_user_id)
                            .filter(models.ChatLog.intent == "search",
                                    models.ChatLog.category == (prod.category or ""),
                                    models.ChatLog.line_user_id != admin_uid)
                            .distinct().limit(10).all())
            uids = [u[0] for u in interested]
            if not uids:
                continue
            for uid in uids:
                u = db.query(models.User).filter(models.User.line_user_id == uid).first()
                name = u.name if u else "LINE User"
                card = product_cards_message(db, type("U", (), {"name": name})(),
                                             [prod],
                                             title=f"💰 ราคาลดลง! ฿{_fmt(old)} → ฿{_fmt(new)} (-{dp:g}%)",
                                             is_owner=False)
                if "mock" in (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").lower():
                    alerted += 1
                    continue
                try:
                    line_bot_api.push_message(uid, card)
                    alerted += 1
                except Exception as e:
                    logger.warning(f"pricedrop push fail {uid}: {e}")
            if alerted and "mock" not in (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").lower():
                db.add(models.CampaignLog(category=(prod.category or "อื่นๆ"),
                                          recipients=len(uids), status="pricedrop"))
                db.commit()
                alerted_detail.append(f"{prod.name[:35]} (-{dp:g}%) -> {len(uids)} คน")
        return {
            "checked": len(prods),
            "updated": updated,
            "unchanged": unchanged,
            "skipped_blocked": blocked,
            "price_drop_alerts": alerted_detail or (f"({alerted} ใน mock)" if alerted else []),
            "note": "ราคา = ราคาเริ่มต้นจริงในหน้าเว็บ; โดนบล็อก = คงราคาเดิม",
        }
    finally:
        db.close()


@router.post("/re-engage")
def cron_reengage(token: str = "", days_silent: int = 7, limit: int = 10):
    """ดึงดูดกลับ — ลูกค้าที่เงียบ ≥ days_silent วัน และเคยสนใจหมวด X
    ที่เพิ่งมีสินค้าใหม่ (7 วัน) → push การ์ดสินค้าใหม่หมวดนั้นให้ (ไม่สแปม:
    จำกัด limit คน/รอบ + ข้อมูลจริงจาก chat_logs เท่านั้น)
    """
    if not _authorized(token):
        raise HTTPException(status_code=401, detail="invalid token")
    import datetime
    from sqlalchemy import func as _func
    db = SessionLocal()
    try:
        admin_uid = os.getenv("ADMIN_LINE_USER_ID", "Uc88eb3896b0e4bcc5fbaa9b78ac1294e")
        min_sales = int(os.getenv("MIN_SALES", "2000") or 2000)
        now = datetime.datetime.now(datetime.timezone.utc)
        new_cutoff = now - datetime.timedelta(days=7)
        silent_cutoff = now - datetime.timedelta(days=days_silent)

        last_act = (db.query(models.ChatLog.line_user_id, _func.max(models.ChatLog.created_at))
                      .group_by(models.ChatLog.line_user_id).all())
        quiet = [uid for uid, last in last_act
                 if last is not None and last <= silent_cutoff and uid != admin_uid]
        quota_ok = push_guard(db)
        pushed, skipped = [], []
        if not quota_ok:
            logger.warning("ข้าม re-engage push (quota หมด)")
        for uid in (quiet[:limit] if quota_ok else []):
            top_cat = (db.query(models.ChatLog.category, _func.count(models.ChatLog.id))
                         .filter(models.ChatLog.line_user_id == uid,
                                 models.ChatLog.intent == "search",
                                 models.ChatLog.category.isnot(None))
                         .group_by(models.ChatLog.category)
                         .order_by(_func.count(models.ChatLog.id).desc()).first())
            if not top_cat or not top_cat[0]:
                skipped.append((uid, "ไม่มีหมวดที่สนใจ"))
                continue
            cat = top_cat[0]
            new_prods = (db.query(models.Product)
                           .filter(models.Product.category == cat,
                                   models.Product.link_status == "ok",
                                   models.Product.sales_count >= min_sales,
                                   models.Product.created_at >= new_cutoff)
                           .order_by(models.Product.created_at.desc()).limit(3).all())
            if not new_prods:
                skipped.append((uid, f"หมวด {cat} ไม่มีของใหม่"))
                continue
            u = db.query(models.User).filter(models.User.line_user_id == uid).first()
            name = u.name if u else "LINE User"
            card = product_cards_message(db, type("U", (), {"name": name})(), new_prods,
                                         f"🆕 ของใหม่หมวด {cat} มาแล้วจ๊ะ (เผื่อยังสนใจอยู่)",
                                         is_owner=False)
            if "mock" in (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").lower():
                pushed.append((uid, f"{cat} ({len(new_prods)} ตัว, mock)"))
                continue
            try:
                line_bot_api.push_message(uid, card)
                db.add(models.CampaignLog(category=cat, recipients=len(new_prods), status="reengage"))
                db.commit()
                pushed.append((uid, f"{cat} ({len(new_prods)} ตัว)"))
            except Exception as e:
                logger.warning(f"reengage push fail {uid}: {e}")
                skipped.append((uid, f"push ล้ม: {str(e)[:40]}"))
        return {"candidates": len(quiet), "pushed": pushed, "skipped": skipped}
    finally:
        db.close()


def _fmt(n: float) -> str:
    return f"{n:,.2f}".rstrip("0").rstrip(".")


def _build_fb_caption(p) -> str:
    """caption สำหรับโพสต์เพจ Facebook = caption (Groq/fallback) + แฮชแท็ก

    (ลิงก์ affiliate ส่งเป็น link param ต่างหาก — Facebook จะดึง preview รูปสินค้าให้เอง)
    """
    caption, tags = "", ""
    try:
        data = generate_script_for_product(p.name, p.category or "",
                                           float(p.price or 0), "Standard")
        caption = (data.get("caption") or "").strip()
        tags = format_hashtags_text(data.get("hashtags"))
    except Exception as e:
        logger.warning(f"[facebook-post] generate caption failed: {e}")
    if not caption:
        caption = (f"🛍️ {p.name} — ราคา {float(p.price or 0):,.0f} บาท "
                   f"ขายแล้ว {p.sales_count:,} ชิ้น ⭐ {p.rating}")
    lines = [caption]
    if tags:
        lines.append(tags)
    # ท้ายโพสต์สินค้าทุกตัว: ชวนแอดไลน์ร้าน (LINE ID + ลิงก์) — เจ้าของสั่งให้ใส่ครบ
    lines.append(line_cta_footer())
    return "\n\n".join(lines)


def _post_sheet_row(kind: str, title: str, message: str, link: str, post_id: str) -> dict:
    """แถวข้อมูลโพสต์สำหรับบันทึก Google ชีท (tools/sheet_posts_apps_script.gs)"""
    return {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kind": kind,
        "title": title,
        "message": (message or "")[:1000],
        "link": link,
        "post_id": post_id,
        "post_url": f"https://www.facebook.com/{post_id}" if post_id else "",
    }


def _post_next_intro(db) -> Optional[dict]:
    """โพสต์แนะนำตัวป้าเข็มถัดไป (Phase 1 — ให้คนรู้จักก่อน)

    กันซ้ำด้วย CampaignLog status='fbintro' (category = index โพสต์) — โพสต์ทีละตัว
    โพสต์ล้ม (รูปมาสคอตโหลดไม่ได้ ฯลฯ) → ข้ามไปตัวถัดไป อย่าให้ rotation ติดตายที่ตัวเดิม
    คืน dict result หรือ None ถ้าโพสต์แนะนำครบทุกตัวแล้ว (หรือล้มทุกตัว)
    """
    posts = intro_posts()
    posted_idx = {int(c.category) for c in db.query(models.CampaignLog)
                  .filter(models.CampaignLog.status == "fbintro").all()
                  if str(c.category).isdigit()}
    last_err = None
    for i, p in enumerate(posts):
        if i in posted_idx:
            continue
        res = post_feed(p["caption"], image_url=p.get("image_url") or "")  # แนบรูปมาสคอต (ถ้ามี)
        if res["ok"]:
            db.add(models.CampaignLog(category=str(i), recipients=1, status="fbintro"))
            db.commit()
            log_post_async(_post_sheet_row("intro", p["title"], p["caption"], "", res["post_id"]))
            return {"posted": [{"kind": "intro", "index": i, "title": p["title"],
                                "posted": True, "post_id": res["post_id"]}]}
        last_err = res["error"]
        logger.warning(f"[intro] โพสต์ล้ม index {i}: {res['error']}")
    if last_err:
        logger.warning(f"[intro] ล้มทุกตัว: {last_err}")
    return None


def _post_next_short_bg(db) -> Optional[dict]:
    """โพสต์ข้อความสั้นพื้นสีถัดไป (Phase 1 — สลับกับโพสต์แนะนำตัว)

    กันซ้ำด้วย CampaignLog status='fbbg' (category = index โพสต์) — โพสต์ทีละตัว
    ข้อความ ≤ 130 ตัวอักษร ส่งผ่าน post_feed(background_preset_id=...) ไม่มีรูป/ลิงก์
    โพสต์ล้ม → ข้ามไปตัวถัดไป อย่าให้ rotation ติดตายที่ตัวเดิม
    คืน dict result หรือ None ถ้าโพสต์พื้นสีครบทุกตัวแล้ว (หรือล้มทุกตัว)
    """
    posts = short_bg_posts()
    posted_idx = {int(c.category) for c in db.query(models.CampaignLog)
                  .filter(models.CampaignLog.status == "fbbg").all()
                  if str(c.category).isdigit()}
    last_err = None
    for i, p in enumerate(posts):
        if i in posted_idx:
            continue
        res = post_feed(p["caption"], background_preset_id=p["preset_id"])
        if res["ok"]:
            db.add(models.CampaignLog(category=str(i), recipients=1, status="fbbg"))
            db.commit()
            log_post_async(_post_sheet_row("bg", p["title"], p["caption"], "", res["post_id"]))
            return {"posted": [{"kind": "bg", "index": i, "title": p["title"],
                                "posted": True, "post_id": res["post_id"],
                                "preset_id": p["preset_id"]}]}
        last_err = res["error"]
        logger.warning(f"[bg] โพสต์ล้ม index {i}: {res['error']}")
    if last_err:
        logger.warning(f"[bg] ล้มทุกตัว: {last_err}")
    return None


def _post_next_brand(db) -> Optional[dict]:
    """แบรนด์: สลับ แนะนำตัว (มาสคอต) ↔ ข้อความสั้นพื้นสี (tick คู่/คี่ ตามจำนวนที่โพสต์แล้ว)"""
    brand_posted = (db.query(models.CampaignLog)
                      .filter(models.CampaignLog.status.in_(["fbintro", "fbbg"]))
                      .count())
    bg_turn = brand_posted % 2 == 1
    if bg_turn:
        res = _post_next_short_bg(db)
        if res is not None:
            return res
        return _post_next_intro(db)
    res = _post_next_intro(db)
    if res is not None:
        return res
    return _post_next_short_bg(db)


def _post_next_product(db, limit: int = 1) -> Optional[dict]:
    """โพสต์สินค้าถัดไป (Phase 2) — เปิดเมื่อตั้ง FB_POST_PRODUCTS=1 เท่านั้น

    คืน None ถ้ายังไม่เปิด หรือสินค้าเข้าเกณฑ์หมดแล้ว (ให้ rotation ไปลองคลังอื่น)
    """
    if os.getenv("FB_POST_PRODUCTS", "").lower() not in ("1", "true", "yes"):
        return None
    min_sales = int(os.getenv("MIN_SALES", "2000") or 2000)
    try:
        cooldown_hours = int(os.getenv("FB_POST_CATEGORY_COOLDOWN_HOURS", "24") or 24)
    except (ValueError, TypeError):
        cooldown_hours = 24
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=cooldown_hours)

    posted_ids = {int(c.category) for c in db.query(models.CampaignLog)
                  .filter(models.CampaignLog.status == "fbpost").all()
                  if str(c.category).isdigit()}

    # กันโพสต์ซ้ำ/โพสต์หมวดถี่เกิน (เช่น หูฟัง) — ดูทั้ง cron (fbpost) + radar (demand events):
    # - หมวดที่เพิ่งโพสต์ภายใน cooldown_hours → ข้าม (กันหมวดเดียวถี่ติดกัน)
    # - สินค้าที่ radar เพิ่งโพสต์ → ข้าม (cron ไม่โพสต์ซ้ำกับ radar)
    # หมายเหตุ: นับ 'pending' ของ radar ด้วย (radar commit ก่อน post_feed) — ไม่งั้น
    # ในหน้าต่างที่ radar กำลังโพสต์ cron มองไม่เห็น → ยิงหมวดเดียวกันซ้ำ (เจอจริง 16/08)
    recent_cats: set = set()
    recent_radar_ids: set = set()
    for c in db.query(models.CampaignLog).filter(
            models.CampaignLog.status == "fbpost",
            models.CampaignLog.created_at >= cutoff).all():
        if str(c.category).isdigit():
            p = db.query(models.Product).filter(models.Product.id == int(c.category)).first()
            if p and p.category:
                recent_cats.add(p.category)
    for e in db.query(models.FacebookDemandEvent).filter(
            models.FacebookDemandEvent.notification_status.in_(["posted", "sent", "pending"]),
            models.FacebookDemandEvent.created_at >= cutoff).all():
        if e.matched_product_id:
            recent_radar_ids.add(e.matched_product_id)
            p = db.query(models.Product).filter(models.Product.id == e.matched_product_id).first()
            if p and p.category:
                recent_cats.add(p.category)

    query = (db.query(models.Product)
               .filter(models.Product.link_status == "ok",
                       models.Product.sales_count >= min_sales))
    if posted_ids:
        query = query.filter(~models.Product.id.in_(posted_ids))
    if recent_radar_ids:
        query = query.filter(~models.Product.id.in_(recent_radar_ids))
    # กรองหมวดที่เพิ่งโพสต์ (cooldown) ใน SQL ก่อน limit — เดิมกรองหลังดึงแค่ 20 ตัว
    # → ถ้า 20 ตัวแรก (คอมสูง) ติด cooldown หมด จะไม่เห็นสินค้าหมวดอื่นที่พร้อม
    # (เจอจริง 18/08: โพสต์ 14 หมวด/24 ชม. หมวดคอมสูงติด cooldown หมด → เงียบทั้งที่มีของ)
    if recent_cats:
        query = query.filter(models.Product.category.is_(None)
                             | ~models.Product.category.in_(recent_cats))
    prods = []
    for p in (query.order_by(models.Product.commission.desc(),
                             models.Product.ai_score.desc())
                   .limit(max(limit * 20, 20)).all()):
        # Guard กันลิงก์ปลอม/ของ mock (เช่น s.shopee.co.th/earbuds_ok) หลุดขึ้นโพสต์:
        # ตัวที่โพสต์แนบรูปจะแปะ affiliate_url ไว้ในแคปชั่น (ไม่ใช่ link param) →
        # post_feed guard ตรวจ link param ไม่ถึง → กรองที่นี่อีกชั้น (defense-in-depth)
        if not is_valid_shopee_affiliate_url(p.affiliate_url):
            logger.warning(f"[product] ข้ามสินค้า {p.id} affiliate_url ไม่ valid: "
                           f"{str(p.affiliate_url)[:60]!r}")
            continue
        prods.append(p)
        if len(prods) >= max(limit * 5, 5):  # ลองหลายตัว เผื่อตัวแรกโพสต์ล้ม (กัน rotation ติดตาย)
            break
    if not prods:
        return None
    results = []
    for p in prods:
        # รูปสินค้า: ใช้ที่ cache ไว้ (p.image_url) ถ้ายังไม่มี → ดึง og:image ครั้งเดียวแล้วจำไว้
        image = (p.image_url or "").strip()
        if not image:
            image = fetch_product_image(p.affiliate_url or "")
            if image:
                p.image_url = image
                db.commit()
        caption = _build_fb_caption(p)  # สร้างครั้งเดียว (เดิมเรียกซ้ำ 2 รอบ → เผา Groq เปล่า)
        # จองหมวดก่อนยิงโพสต์ — กัน radar ยิงหมวดเดียวกันซ้ำระหว่างกำลังโพสต์
        # (เหมือน radar ที่ commit status='pending' ก่อน post_feed แล้วค่อยเปลี่ยน)
        # โพสต์สำเร็จ → เปลี่ยนเป็น fbpost (dedup ทำงาน) / โพสต์ล้ม → ลบการจอง
        # (ไม่ให้กันหมวดนี้ไปตลอด cooldown) — ถ้า process ตายคาการจอง จะค้างเป็น
        # fbpost_pending กัน radar 24 ชม. (self-heal เหมือน radar pending ค้าง)
        pending = models.CampaignLog(category=str(p.id), recipients=1, status="fbpost_pending")
        db.add(pending)
        db.commit()
        if image:
            # โพสต์แนบรูปจริง (ไม่พึ่ง Facebook crawl การ์ดลิงก์) — ลิงก์ affiliate ไปอยู่ในแคปชั่น
            caption = f"{caption}\n\n🛒 {p.affiliate_url or ''}".strip()
            res = post_feed(caption, image_url=image)
        else:
            # หารูปไม่ได้ → fallback การ์ดลิงก์เดิม (Facebook crawl เอาเอง)
            res = post_feed(caption, link=p.affiliate_url or "")
        if res["ok"]:
            pending.status = "fbpost"
            db.commit()
            log_post_async(_post_sheet_row("product", p.name[:45],
                                           caption, p.affiliate_url or "",
                                           res["post_id"]))
            results.append({"id": p.id, "name": p.name[:45], "posted": True,
                            "post_id": res["post_id"]})
            if len(results) >= limit:
                break
        else:
            db.delete(pending)
            db.commit()
            # โพสต์ล้ม (รูป/ลิงก์โดน Facebook ปฏิเสธ ฯลฯ) → ลองตัวถัดไป อย่าให้ rotation ติดตาย
            # error รุนแรง (token หมดอายุ/สิทธิ์หาย/rate-limit) → แจ้งเจ้าของด้วย (throttle)
            if classify_post_error(res.get("error") or ""):
                notify_owner_once("fb_post_hard_error",
                                  f"⚠️ โพสต์สินค้าล้ม (error รุนแรง): {res.get('error') or ''}")
            logger.warning(f"[product] โพสต์ล้ม {p.id} {p.name[:40]}: {res['error']}")
    return {"posted": results} if results else None


def _post_next_local(db) -> Optional[dict]:
    """โพสต์ท้องถิ่น (ร้านอร่อย/ของฝาก/ของกิน) — Firecrawl ค้นตามจังหวัด กันซ้ำ status='fblocal'.

    index = จำนวนโพสต์ fblocal ที่สำเร็จแล้ว → หมุนเวียน 77 จังหวัด × 3 หัวข้อ
    (โพสต์ล้มไม่ commit → index เดิม คราวหน้า retry จังหวัด/หัวข้อเดิม)
    """
    posted = {c.category for c in db.query(models.CampaignLog)
              .filter(models.CampaignLog.status == "fblocal").all()}
    last_err = None
    for it in fetch_local_items(len(posted)):
        key = local_item_key(it)
        if key in posted:
            continue
        caption = curate_local_caption(it)
        res = post_feed(caption, link=it["link"])
        if res["ok"]:
            db.add(models.CampaignLog(category=key, recipients=1, status="fblocal"))
            db.commit()
            log_post_async(_post_sheet_row("local", (it["title"] or "")[:45],
                                           caption, it["link"], res["post_id"]))
            return {"posted": [{"kind": "local", "title": (it["title"] or "")[:45],
                                "posted": True, "post_id": res["post_id"],
                                "source": it.get("topic", "")}]}
        # โพสต์ล้ม (ลิงก์โดน Facebook ปฏิเสธ ฯลฯ) → ลองตัวถัดไป อย่าให้คลังติดตาย
        last_err = res["error"]
        logger.warning(f"[local] โพสต์ล้ม {it['link'][:60]}: {res['error']}")
    # ล้มทุกตัว → คืน None ให้ rotation ไปลองคลังอื่น (ไม่ block scheduler)
    if last_err:
        logger.warning(f"[local] ล้มทุกตัว: {last_err}")
    return None


def _post_next_curated(db) -> Optional[dict]:
    """โพสต์คอนเทนต์โลก (RSS) — กันซ้ำด้วย status='fbrss', category=sha1(guid|link)

    โพสต์ล้ม (ลิงก์โดน Facebook ปฏิเสธ ฯลฯ) → ลองข่าวตัวถัดไป อย่าให้คลังติดตาย
    (พฤติกรรมเดียวกับ _post_next_local — เจอจริง: ลิงก์ facebook.com โพสต์ไม่ได้)
    """
    posted = {c.category for c in db.query(models.CampaignLog)
              .filter(models.CampaignLog.status == "fbrss").all()}
    last_err = None
    for it in fetch_news_items():
        key = item_key(it)
        if key in posted:
            continue
        caption = curate_caption(it)
        res = post_feed(caption, link=it["link"])
        if res["ok"]:
            db.add(models.CampaignLog(category=key, recipients=1, status="fbrss"))
            db.commit()
            log_post_async(_post_sheet_row("rss", (it["title"] or "")[:45],
                                           caption, it["link"], res["post_id"]))
            return {"posted": [{"kind": "rss", "title": (it["title"] or "")[:45],
                                "posted": True, "post_id": res["post_id"],
                                "source": it.get("source", "")}]}
        last_err = res["error"]
        logger.warning(f"[rss] โพสต์ล้ม {it['link'][:60]}: {res['error']}")
    if last_err:
        logger.warning(f"[rss] ล้มทุกตัว: {last_err}")
    return None


# กัน 2 process/thread ยิงโพสต์พร้อมกัน (scheduler ในตัว + HTTP endpoint + radar) —
# ถ้าโพสต์ก่อนหน้ายังไม่เสร็จ (slow Groq/fetch รูป > 60s) ให้ข้ามรอบนี้ กันโพสต์ซ้ำ
_AUTO_POST_LOCK = threading.Lock()


def _run_post_locked(kind: str, limit: int = 1) -> dict:
    """แกนโพสต์ร่วม: preflight + lock แล้วแยก kind='product' (สินค้า) | 'content' (แนะนำ/ข่าว/ร้าน)."""
    if not _AUTO_POST_LOCK.acquire(blocking=False):
        logger.warning("[facebook-post] มีโพสต์กำลังทำงานอยู่ — ข้ามรอบนี้ (กันโพสต์ซ้ำ)")
        return {"posted": [], "note": "โพสต์กำลังทำงานอยู่ — ข้ามรอบนี้ (กันโพสต์ซ้ำ)"}
    try:
        # ตรวจความพร้อมก่อนยิงโพสต์ (token ตั้ง/ใช้ได้, page id) — ไม่พร้อม → ข้าม + แจ้งเจ้าของ
        ok, reasons = preflight_ready()
        if not ok:
            notify_owner_once("fb_preflight_cron",
                              "⚠️ ข้ามโพสต์เพจ (ยังไม่พร้อม): " + "; ".join(reasons))
            return {"posted": [], "note": "ยังไม่พร้อมโพสต์: " + "; ".join(reasons)}
        db = SessionLocal()
        try:
            if kind == "product":
                # โหมดสินค้า: โพสต์เฉพาะสินค้า affiliate
                res = _post_next_product(db, limit)
                if res is not None:
                    return res
                return {"posted": [],
                        "note": "โพสต์สินค้าเข้าเกณฑ์ครบแล้ว (รอสินค้าใหม่/ลิงก์ตรวจผ่าน — หรือตั้ง MIN_SALES ต่ำลง)"}

            # kind == "content": แนะนำแม่เข็ม ↔ ข่าว RSS ↔ ร้านท้องถิ่น (ไม่แตะสินค้า)
            brand_n = (db.query(models.CampaignLog)
                         .filter(models.CampaignLog.status.in_(["fbintro", "fbbg"])).count())
            rss_n = (db.query(models.CampaignLog)
                         .filter(models.CampaignLog.status == "fbrss").count())
            local_n = (db.query(models.CampaignLog)
                         .filter(models.CampaignLog.status == "fblocal").count())
            slot = (brand_n + rss_n + local_n) % 3  # 0=แนะนำแม่เข็ม, 1=ข่าว, 2=ร้าน
            for s in (slot, (slot + 1) % 3, (slot + 2) % 3):
                if s == 0:
                    res = _post_next_brand(db)
                elif s == 1:
                    res = _post_next_curated(db)
                else:
                    res = _post_next_local(db)
                if res is not None:
                    return res
            return {"posted": [],
                    "note": "ไม่มีคอนเทนต์ใหม่ (แบรนด์ครบ / รอ RSS / รอ Firecrawl)"}
        finally:
            db.close()
    finally:
        _AUTO_POST_LOCK.release()


def run_facebook_product_post(limit: int = 1) -> dict:
    """โหมดสินค้า: โพสต์เฉพาะสินค้า affiliate — ใช้ scheduler แยก (FB_AUTO_POST_INTERVAL)."""
    return _run_post_locked("product", limit)


def run_facebook_content_post() -> dict:
    """โหมดคอนเทนต์: แนะนำแม่เข็ม ↔ ข่าว ↔ ร้าน — ใช้ scheduler แยก (FB_CONTENT_POST_INTERVAL)."""
    return _run_post_locked("content")


def run_facebook_auto_post(limit: int = 1) -> dict:
    """backward compat (HTTP endpoint / เทสต์เดิม): dispatch ตาม FB_POST_PRODUCTS.

    scheduler ในตัวใช้ run_facebook_product_post / run_facebook_content_post โดยตรง
    เพื่อให้สินค้ากับคอนเทนต์กำหนดเวลาแยกกัน (แยกชัดเจน)
    """
    if os.getenv("FB_POST_PRODUCTS", "").lower() in ("1", "true", "yes"):
        return run_facebook_product_post(limit)
    return run_facebook_content_post()


@router.post("/facebook-post")
def cron_facebook_post(token: str = "", limit: int = 1):
    """HTTP endpoint — โพสต์คอนเทนต์สินค้าลงเพจ Facebook (CRON_TOKEN lock เหมือน cron อื่น)

    (งานเดียวกันกับ scheduler ในตัว — เก็บ endpoint ไว้เผื่อ cron-job.org / ทดสอบ manual)
    """
    if not _authorized(token):
        raise HTTPException(status_code=401, detail="invalid token")
    return run_facebook_auto_post(limit)


def sweep_fake_posts(limit: int = 100, dry_run: bool = False) -> dict:
    """กวาดโพสต์ลิงก์ปลอมบนเพจ → ลบ (หรือ dry_run ดูตัวอย่าง)

    ลบโพสต์ที่มี: shope.ee (ปลอมเสมอ) / lazada.co.th (แพลตฟอร์มอื่น) /
    s.shopee.co.th รหัส format ไม่ valid หรือ **ไม่ใช่ลิงก์ในคลังสินค้า** (เช่น
    s.shopee.co.th/earbudsok ที่ mock poster ใช้ — base62 ผ่าน format แต่ไม่มีใน products)

    ใช้ได้ทั้ง cron endpoint (/cron/clean-fake-posts) และ watcher อัตโนมัติในตัว
    (main.py) — กัน mock poster โพสต์ลิงก์ปลอมขึ้นเพจแล้วค้างอยู่
    """
    db = SessionLocal()
    try:
        known = set()
        for (u,) in db.query(models.Product.affiliate_url)\
                     .filter(models.Product.affiliate_url.isnot(None)).all():
            if u:
                known.add(_normalize_shopee_link(u))
        posts = fetch_page_posts(limit=limit)
        deleted, kept = [], []
        for p in posts:
            if is_fake_link_post(p.get("message") or "", p.get("urls") or [],
                                 known_links=known):
                pid = p.get("id")
                ok = True
                if not dry_run:
                    ok = delete_page_post(pid)
                deleted.append({"id": pid, "created_time": p.get("created_time"),
                                "message": (p.get("message") or "")[:60],
                                "deleted": ok})
            else:
                kept.append(p.get("id"))
        return {"scanned": len(posts), "deleted": deleted,
                "kept_count": len(kept), "dry_run": dry_run}
    finally:
        db.close()


@router.post("/clean-fake-posts")
def cron_clean_fake_posts(token: str = "", limit: int = 100, dry_run: bool = False):
    """กวาดลบโพสต์ลิงก์ปลอมบนเพจ Facebook — กันสคริปต์ mock โพสต์ลิงก์ปลอมขึ้นเพจ

    เรียกจาก cron-job.org เป็นระยะ (ต้อง ?token=<CRON_TOKEN>); `dry_run=true` = ดูตัวอย่างไม่ลบ
    (งานเดียวกันกับ watcher อัตโนมัติในตัว main.py — เก็บ endpoint ไว้เผื่อ manual/ครอน)
    """
    if not _authorized(token):
        raise HTTPException(status_code=401, detail="invalid token")
    return sweep_fake_posts(limit=limit, dry_run=dry_run)


@router.post("/daily-report")
def cron_daily_report(token: str = "", hours: int = 24):
    """รายงานประจำวัน — สรุปตัวเลขจริงจาก DB แล้ว push ข้อความให้เจ้าของร้าน
    (เรียกจาก cron-job.org ทุกเช้า เช่น 08:00; ข้อมูลทั้งหมดมาจากตารางจริง ไม่มีตัวเลขมโน)
    """
    if not _authorized(token):
        raise HTTPException(status_code=401, detail="invalid token")
    import datetime
    db = SessionLocal()
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(hours=hours)
        min_sales = int(os.getenv("MIN_SALES", "2000") or 2000)
        admin_uid = os.getenv("ADMIN_LINE_USER_ID", "Uc88eb3896b0e4bcc5fbaa9b78ac1294e")

        total = db.query(models.Product).count()
        sellable = (db.query(models.Product)
                      .filter(models.Product.link_status == "ok",
                              models.Product.sales_count >= min_sales).count())
        new_prods = (db.query(models.Product)
                       .filter(models.Product.created_at >= cutoff).count())
        dead = db.query(models.Product).filter(models.Product.link_status == "dead").count()
        with_content = {c.product_id for c in db.query(models.Content).all()}
        no_content = max(0, total - len(with_content))

        msgs = db.query(models.ChatLog).filter(models.ChatLog.created_at >= cutoff).count()
        searchers = (db.query(models.ChatLog.line_user_id)
                        .filter(models.ChatLog.created_at >= cutoff,
                                models.ChatLog.intent == "search").distinct().count())
        wismo = (db.query(models.ChatLog)
                   .filter(models.ChatLog.created_at >= cutoff,
                           models.ChatLog.intent == "wismo").count())
        cat_rows = (db.query(models.ChatLog.category, func.count(models.ChatLog.id))
                      .filter(models.ChatLog.created_at >= cutoff,
                              models.ChatLog.category.isnot(None))
                      .group_by(models.ChatLog.category)
                      .order_by(func.count(models.ChatLog.id).desc()).limit(5).all())

        lines = [f"📊 รายงานร้านป้าเข็ม ({cutoff:%d/%m %H:%M} - {now:%d/%m %H:%M})", "",
                 f"🛍️ สินค้าในคลัง: {total} ตัว (ขายได้ {sellable})",
                 f"🆕 เข้าใหม่ {hours}h: {new_prods} ตัว",
                 f"💀 ลิงก์ตาย: {dead} ตัว (ซ่อนจากลูกค้าอัตโนมัติ)",
                 f"📝 ยังไม่มีคอนเทนต์: {no_content} ตัว"]
        lines += ["", f"💬 ลูกค้าคุย {msgs} ครั้ง ({searchers} คนค้นสินค้า, ทวงถาม {wismo} ครั้ง)"]
        if cat_rows:
            lines.append("🔥 หมวดที่ถูกถาม: " + ", ".join(f"{c}({n})" for c, n in cat_rows))
        lines.append("\n— สรุปจากข้อมูลจริงของร้าน 🛒")
        text = "\n".join(lines)

        if "mock" in (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").lower():
            logger.info(f"Mock daily report (ไม่ push จริง):\n{text}")
            return {"pushed": False, "report": text}
        if not push_guard(db):
            logger.warning("ข้าม daily report push (quota หมด)")
            return {"pushed": False, "report": text, "note": "ข้าม: push quota หมด"}
        line_bot_api.push_message(admin_uid, TextSendMessage(text=text))
        return {"pushed": True, "recipient": admin_uid, "report": text}
    finally:
        db.close()
