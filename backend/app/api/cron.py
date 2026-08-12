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
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app import models
from app.services.link_checker import check_affiliate_link
from app.services.ai_generator import format_hashtags_text, generate_script_for_product
from app.services.price_refresh import refresh_price
from app.services.product_cards import product_cards_message
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
        done, failed = [], []
        for p in missing[:limit]:
            try:
                data = generate_script_for_product(p.name, p.category or "", float(p.price or 0), "Standard")
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
        for prod, old, new, dp in drops[:5]:
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
        pushed, skipped = [], []
        for uid in quiet[:limit]:
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
        line_bot_api.push_message(admin_uid, TextSendMessage(text=text))
        return {"pushed": True, "recipient": admin_uid, "report": text}
    finally:
        db.close()
