import asyncio
import datetime
import logging
import os
from contextlib import asynccontextmanager

# default root level = WARNING ทำให้ INFO log ของ app (เช่น keep-alive ping) ถูกกลืนไม่ขึ้น Render log
logging.basicConfig(level=logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)  # กัน BEGIN/COMMIT รกทุก query

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx
from sqlalchemy import text

from app.db import engine, Base, is_sqlite
from app.api import users, products, performance, line_bot, cron, admin_dashboard, facebook_bot, facebook_radar, creative_brief
from app.api.cron import run_facebook_auto_post, run_facebook_product_post, run_facebook_content_post
from app.config import settings

logger = logging.getLogger(__name__)

# Create database tables on startup (especially helpful for SQLite/Supabase development)
Base.metadata.create_all(bind=engine)


def _migrate_schema():
    """Self-heal สกีมาที่ดริฟท์ — create_all สร้างแต่ตาราง ไม่ ALTER ตารางเดิม.

    เทียบคอลัมน์จริงของทุกตารางใน Base.metadata กับ model แล้ว ADD COLUMN ตัวที่ขาด
    (SQLite: PRAGMA table_info; Postgres: information_schema). เจอจริงจาก dev SQLite
    ที่ products ขาด image_url/link_status/ai_score/price_checked_at, contents ขาด
    hook/problem/solution/cta → endpoint 500 "no such column"."""
    from sqlalchemy.dialects import sqlite as sa_sqlite
    from sqlalchemy.dialects import postgresql as sa_pg

    dialect = sa_sqlite.dialect() if is_sqlite else sa_pg.dialect()

    def _default_sql(column):
        """ค่า DEFAULT สำหรับ ALTER คอลัมน์ NOT NULL ที่ไม่มีค่า (None = ปล่อย nullable)."""
        if column.server_default is not None:
            a = column.server_default.arg
            return repr(a) if isinstance(a, str) else str(a)
        if column.default is not None and not callable(column.default.arg):
            a = column.default.arg
            if isinstance(a, bool):
                return "1" if a else "0"
            return repr(a)
        return None

    try:
        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                tname = table.name
                if is_sqlite:
                    actual = {r[1] for r in conn.execute(
                        text(f'PRAGMA table_info("{tname}")')).fetchall()}
                else:
                    actual = {r[0] for r in conn.execute(
                        text("SELECT column_name FROM information_schema.columns "
                             "WHERE table_name = :t"), {"t": tname}).fetchall()}
                if not actual:
                    continue  # ตารางยังไม่มี (ไม่ควรเกิดหลัง create_all)
                for column in table.columns:
                    if column.name in actual:
                        continue
                    ddl = column.type.compile(dialect=dialect)
                    if not column.nullable:
                        d = _default_sql(column)
                        if d is not None:
                            ddl += f" NOT NULL DEFAULT {d}"
                    if is_sqlite:
                        stmt = f'ALTER TABLE "{tname}" ADD COLUMN "{column.name}" {ddl}'
                    else:
                        stmt = (f'ALTER TABLE "{tname}" ADD COLUMN IF NOT EXISTS '
                                f'"{column.name}" {ddl}')
                    conn.execute(text(stmt))
                    logger.info(f"migrate: +{tname}.{column.name} {ddl}")
    except Exception as e:
        logger.warning(f"migrate schema columns failed: {e}")


_migrate_schema()

KEEP_ALIVE_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
KEEP_ALIVE_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "600"))
# เวลาตื่น-พัก (เวลาไทย UTC+7) — ค่าเริ่มต้นตื่น 07:00 - 23:00 น. (พัก 23:00 - 07:00 น. ประหยัดโควต้า 750 ชม./เดือน)
KEEP_ALIVE_START_HOUR = int(os.getenv("KEEP_ALIVE_START_HOUR", "7") or 7)
KEEP_ALIVE_END_HOUR = int(os.getenv("KEEP_ALIVE_END_HOUR", "23") or 23)

def _is_active_hours() -> bool:
    """ตรวจว่าตอนนี้อยู่ในช่วงเวลาทำการ (07:00 - 23:00 น. เวลาไทย UTC+7) หรือไม่"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    bkk_now = utc_now + datetime.timedelta(hours=7)
    return KEEP_ALIVE_START_HOUR <= bkk_now.hour < KEEP_ALIVE_END_HOUR

# นาทีระหว่างโพสต์ Facebook อัตโนมัติ (0/ไม่ตั้ง = ปิด) — บอทโพสต์เองในตัว ไม่พึ่ง cron-job.org
FB_AUTO_POST_INTERVAL = int(os.getenv("FB_AUTO_POST_INTERVAL", "0") or 0)
# นาทีระหว่างโพสต์คอนเทนต์ (แนะนำแม่เข็ม/ข่าว/ร้าน) — แยกกำหนดเวลาจากสินค้า (0 = ปิด)
FB_CONTENT_POST_INTERVAL = int(os.getenv("FB_CONTENT_POST_INTERVAL", "0") or 0)



FB_AUTO_POST_CHECK_SECONDS = 60  # ตรวจทุก 1 นาทีว่าถึงเวลาโพสต์หรือยัง (ไม่ sleep ยาว 4 ชม. รวดเดียว)
# วินาทีระหว่างกวาดลบโพสต์ลิงก์ปลอมอัตโนมัติ — mock poster "หูฟังลิงก์จริง" โพสต์ลิงก์ปลอม
# (shope.ee/s.shopee.co.th รหัสปลอม) ขึ้นเพจซ้ำ ๆ; cron-job.org ทุก 6 ชม. ช้าเกินไป → ตรวจเองทุกไม่กี่นาที
FB_FAKE_POST_CHECK_SECONDS = int(os.getenv("FB_FAKE_POST_CHECK_SECONDS", "300") or 300)


def _fb_fake_watcher_enabled() -> bool:
    """บอทลบโพสต์ปลอมอัตโนมัติ: เปิดเมื่อต่อ production (postgres) + มี FB token
    — dev/test (sqlite) ไม่ลบของจริงโดยไม่ได้ตั้งใจ"""
    db_url = (os.getenv("DATABASE_URL") or "").strip().lower()
    prod = db_url.startswith("postgres") or db_url.startswith("postgresql")
    token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    return prod and bool(token)


def _last_post_ts(statuses) -> "datetime.datetime | None":
    """created_at ของโพสต์สำเร็จล่าสุดใน statuses ที่กำหนด (None = ยังไม่เคยโพสต์)."""
    from app import models
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        last = (db.query(models.CampaignLog)
                  .filter(models.CampaignLog.status.in_(statuses))
                  .order_by(models.CampaignLog.created_at.desc())
                  .first())
        if last is None or last.created_at is None:
            return None
        ts = last.created_at
        if ts.tzinfo is None:  # SQLite คืน naive → เติม tz กัน TypeError ลบ aware - naive
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        return ts
    finally:
        db.close()


def _auto_post_due() -> bool:
    """(backward compat) ถึงเวลาจากโพสต์ล่าสุดทุกชนิด — ใช้โดย facebook_auto_post_loop เดิม.

    สำคัญ: นับจาก created_at ของแถวโพสต์สำเร็จล่าสุดใน CampaignLog ไม่ใช่ timer ในหน่วยความจำ —
    เพราะ Render free tier spin-down / deploy ใหม่ = process ถูก kill แล้ว sleep ที่ค้างอยู่หายไป
    → ถ้ายังนับแบบ sleep ยาว 4 ชม. ตั้งแต่ start โพสต์จะเลื่อนออกเรื่อย ๆ ทุกครั้งที่ restart
    """
    last = _last_post_ts(["fbintro", "fbbg", "fbpost", "fbrss", "fblocal"])
    if last is None:
        return True  # ยังไม่เคยโพสต์เลย → โพสต์แรกทันที
    elapsed = (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds()
    return elapsed >= FB_AUTO_POST_INTERVAL * 60


def _product_due() -> bool:
    """ถึงเวลาโพสต์สินค้าถัดไปไหม — นับจากโพสต์สินค้า (fbpost) ล่าสุดเท่านั้น."""
    last = _last_post_ts(["fbpost"])
    if last is None:
        return True  # ยังไม่เคยโพสต์สินค้า → โพสต์ทันที
    elapsed = (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds()
    return elapsed >= FB_AUTO_POST_INTERVAL * 60


def _content_due() -> bool:
    """ถึงเวลาโพสต์คอนเทนต์ (แนะนำ/ข่าว/ร้าน) ถัดไปไหม — แยก timer จากสินค้า (0 = ปิด)."""
    if FB_CONTENT_POST_INTERVAL <= 0:
        return False
    last = _last_post_ts(["fbintro", "fbbg", "fbrss", "fblocal"])
    if last is None:
        return True
    elapsed = (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds()
    return elapsed >= FB_CONTENT_POST_INTERVAL * 60


async def facebook_auto_post_loop():
    """โพสต์ลงเพจ Facebook อัตโนมัติทุก FB_AUTO_POST_INTERVAL นาที (นับจากโพสต์ล่าสุดจริง)

    ตรวจทุก 1 นาทีว่าถึงเวลาหรือยัง — หลัง deploy/รีสตาร์ทถ้าเลยกำหนดแล้วจะ catch-up
    โพสต์ทันทีแทนที่จะรอใหม่ 4 ชม. (กันตารางโพสต์เลื่อน/เงียบหาย)
    """
    if FB_AUTO_POST_INTERVAL <= 0:
        logger.info("FB_AUTO_POST_INTERVAL not set — facebook auto-post disabled")
        return
    logger.info(f"facebook auto-post enabled — ทุก {FB_AUTO_POST_INTERVAL} นาที (นับจากโพสต์ล่าสุด)")
    while True:
        try:
            if _auto_post_due():
                # run_facebook_auto_post เป็น sync + แตะ DB/เน็ต → ไป thread กันบล็อก event loop
                result = await asyncio.to_thread(run_facebook_auto_post, 1)
                posted = [r for r in result.get("posted", []) if r.get("posted")]
                if posted:
                    names = [p.get("name") or p.get("title") or p.get("id") for p in posted]
                    logger.info(f"facebook auto-post โพสต์แล้ว: {names}")
                else:
                    logger.info(f"facebook auto-post: {result.get('note') or result}")
        except Exception as e:
            logger.warning(f"facebook auto-post failed: {e}")
        await asyncio.sleep(FB_AUTO_POST_CHECK_SECONDS)


async def facebook_product_post_loop():
    """โพสต์สินค้าอัตโนมัติทุก FB_AUTO_POST_INTERVAL นาที (นับจากโพสต์สินค้าล่าสุด) — เฉพาะเวลา 07:00 - 23:00 น."""
    if FB_AUTO_POST_INTERVAL <= 0:
        logger.info("FB_AUTO_POST_INTERVAL not set — product auto-post disabled")
        return
    logger.info(f"product auto-post enabled — ทุก {FB_AUTO_POST_INTERVAL} นาที (เวลาทำการ 07:00 - 23:00 น.)")
    while True:
        try:
            if _is_active_hours() and _product_due():
                result = await asyncio.to_thread(run_facebook_product_post, 1)
                posted = [r for r in result.get("posted", []) if r.get("posted")]
                if posted:
                    names = [p.get("name") or p.get("id") for p in posted]
                    logger.info(f"product auto-post โพสต์แล้ว: {names}")
                else:
                    logger.info(f"product auto-post: {result.get('note') or result}")
        except Exception as e:
            logger.warning(f"product auto-post failed: {e}")
        await asyncio.sleep(FB_AUTO_POST_CHECK_SECONDS)


async def facebook_content_post_loop():
    """โพสต์คอนเทนต์ (แนะนำแม่เข็ม/ข่าว/ร้าน) ทุก FB_CONTENT_POST_INTERVAL นาที — เฉพาะเวลา 07:00 - 23:00 น."""
    if FB_CONTENT_POST_INTERVAL <= 0:
        logger.info("FB_CONTENT_POST_INTERVAL not set — content auto-post disabled")
        return
    logger.info(f"content auto-post enabled — ทุก {FB_CONTENT_POST_INTERVAL} นาที (เวลาทำการ 07:00 - 23:00 น.)")
    while True:
        try:
            if _is_active_hours() and _content_due():
                result = await asyncio.to_thread(run_facebook_content_post)
                posted = [r for r in result.get("posted", []) if r.get("posted")]
                if posted:
                    names = [p.get("name") or p.get("title") or p.get("id") for p in posted]
                    logger.info(f"content auto-post โพสต์แล้ว: {names}")
                else:
                    logger.info(f"content auto-post: {result.get('note') or result}")
        except Exception as e:
            logger.warning(f"content auto-post failed: {e}")
        await asyncio.sleep(FB_AUTO_POST_CHECK_SECONDS)



async def facebook_fake_post_watcher():
    """กวาดลบโพสต์ลิงก์ปลอมอัตโนมัติทุก FB_FAKE_POST_CHECK_SECONDS วิ (ทำงานเอง ไม่ต้องรอครอน)

    mock poster "หูฟังลิงก์จริง" (shope.ee / s.shopee.co.th/earbuds_ok) โพสต์ลิงก์ปลอมขึ้นเพจ
    ซ้ำ ๆ — ถ้ารอ cron-job.org ทุก 6 ชม. โพสต์ใหม่จะค้างได้เป็นชั่วโมง → ตรวจเองในตัวทุกไม่กี่นาที
    ลบทันทีที่เจอ + แจ้งเจ้าของ (throttle) ทำงานเฉพาะ production + มี FB token
    """
    if not _fb_fake_watcher_enabled():
        logger.info("facebook fake-post watcher disabled (ต้อง prod + FB token)")
        return
    logger.info(f"facebook fake-post watcher enabled — ตรวจทุก {FB_FAKE_POST_CHECK_SECONDS} วิ")
    while True:
        await asyncio.sleep(FB_FAKE_POST_CHECK_SECONDS)
        try:
            from app.api.cron import sweep_fake_posts
            from app.services.facebook_poster import notify_owner_once
            # sweep_fake_posts เป็น sync + แตะ DB/เน็ต → ไป thread กันบล็อก event loop
            result = await asyncio.to_thread(sweep_fake_posts, 100, False)
            deleted = result.get("deleted") or []
            if deleted:
                msgs = [d.get("message", "")[:40] for d in deleted]
                logger.warning(f"[fb-fake-watcher] ลบโพสต์ปลอม {len(deleted)} ตัว: {msgs}")
                # แจ้งเจ้าของ (throttle 6 ชม.) — ยังมี mock poster รันอยู่ = ต้องไปหยุดที่ต้นตอ
                notify_owner_once("fb_fake_post_deleted",
                                  f"🧹 บอทลบโพสต์ลิงก์ปลอม {len(deleted)} ตัว "
                                  f"(mock poster ยังรันอยู่?): "
                                  + "; ".join(msgs[:3]))
        except Exception as e:
            logger.warning(f"[fb-fake-watcher] ล้ม: {e}")


async def keep_alive_loop():
    """กัน Render free tier หลับ: ping ตัวเองทุก 10 นาที เฉพาะช่วงเวลาทำการ (07:00 - 23:00 น. เวลาไทย)
    ช่วงเวลาพักผ่อน (23:00 - 07:00 น.) จะหยุด ping เพื่อปล่อยให้ Render หลับอัตโนมัติ ช่วยประหยัดโควต้า 750 ชม./เดือน
    (Render ตั้ง RENDER_EXTERNAL_URL ให้อัตโนมัติ = URL สาธารณะของ service)"""
    if not KEEP_ALIVE_URL:
        logger.warning("RENDER_EXTERNAL_URL not set — keep-alive loop disabled (dev)")
        return
    while True:
        await asyncio.sleep(KEEP_ALIVE_INTERVAL)
        if not _is_active_hours():
            logger.info("keep-alive: อยู่นอกเวลาทำการ (23:00 - 07:00 น.) — ข้าม ping เพื่อปล่อยให้ Render พักผ่อน")
            continue
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{KEEP_ALIVE_URL}/health")
                logger.info(f"keep-alive ping {KEEP_ALIVE_URL}/health -> {r.status_code}")
        except Exception as e:
            logger.warning(f"keep-alive ping failed: {e}")



@asynccontextmanager
async def lifespan(app: FastAPI):
    keep_alive = asyncio.create_task(keep_alive_loop())
    product_post = asyncio.create_task(facebook_product_post_loop())
    content_post = asyncio.create_task(facebook_content_post_loop())
    fake_watcher = asyncio.create_task(facebook_fake_post_watcher())
    yield
    keep_alive.cancel()
    product_post.cancel()
    content_post.cancel()
    fake_watcher.cancel()


app = FastAPI(
    title="AI Affiliate Marketing Automation Platform API",
    description="Backend API for managing Shopee products, generating AI content scripts, and LINE bot services.",
    version="1.0.0",
    lifespan=lifespan
)

# Set up CORS middleware to allow connection from frontend (Svelte/React in future phases)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for local development, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(users.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(performance.router, prefix="/api")
app.include_router(line_bot.router, prefix="/api")
app.include_router(line_bot.slips_router, prefix="/api")  # เปิดดูรูปสลิปโอนเงิน (ลิงก์แจ้งเจ้าของ)
app.include_router(facebook_bot.router, prefix="/api")
app.include_router(facebook_radar.router, prefix="/api")
app.include_router(cron.router, prefix="/api")
app.include_router(admin_dashboard.router)  # แดชบอร์ดแอดมิน (/admin + /api/admin/*)
app.include_router(creative_brief.router, prefix="/api")

# ไฟล์ static (รูปมาสคอตป้าเข็มสำหรับโพสต์ Facebook เป็นต้น) — เสิร์ฟที่ /static/*
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": "AI Affiliate Marketing Automation Platform API",
        "version": "1.0.0",
        "llm_provider": settings.LLM_PROVIDER,
        "database_url_configured": settings.DATABASE_URL is not None
    }

@app.get("/health")
def health_check():
    """Health check endpoint for uptime monitoring (e.g. cron-job.org).
    Prevents Render free tier cold start by being pinged every 10 minutes.
    """
    return {"status": "ok"}


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    """นโยบายข้อมูลส่วนบุคคล (PDPA) — ลูกค้าดูได้จากลิงก์ใน welcome/ข้อความบอท"""
    return """<!DOCTYPE html>
<html lang="th">
<head><meta charset="utf-8"><title>นโยบายความเป็นส่วนตัว</title>
<style>body{font-family:'Leelawadee UI',Tahoma,sans-serif;max-width:640px;margin:40px auto;padding:0 20px;line-height:1.7;color:#333}h1{color:#E74C3C}</style>
</head>
<body>
<h1>🔒 นโยบายความเป็นส่วนตัว (PDPA)</h1>
<p>ร้าน "ป้าเข็ม ขายของ" (LINE Official Account) เก็บข้อมูลส่วนบุคคลเพียงเท่าที่จำเป็น เพื่อให้บริการค้นหาและแนะนำสินค้าให้คุณ</p>
<h2>เราเก็บอะไร</h2>
<ul>
<li>ชื่อ LINE และ ID (เพื่อเรียกชื่อคุณในการสนทนา)</li>
<li>ประวัติการสนทนา (เฉพาะข้อความที่คุณส่ง + ประเภทคำถาม) นานสูงสุด 90 วัน</li>
</ul>
<h2>เราไม่เก็บอะไร</h2>
<ul>
<li>ไม่เก็บข้อความส่วนตัวเกิน 90 วัน · ไม่เก็บข้อมูลบัตร/การเงิน · ไม่ขายข้อมูล</li>
</ul>
<h2>สิทธิ์ของคุณ</h2>
<ul>
<li>ลบข้อมูลได้ตลอด: พิมพ์ <b>ลบข้อมูลฉัน</b> ในแชท → ลบชื่อ + ประวัติทันที</li>
<li>ขอดู/แก้ไขข้อมูล: ติดต่อผ่านแชทบอทได้</li>
</ul>
<p>สอบถามเพิ่มเติม: ส่งข้อความในแชทบอทได้ตลอด 24 ชม. ค่ะ</p>
</body>
</html>"""
