import asyncio
import datetime
import logging
import os
from contextlib import asynccontextmanager

# default root level = WARNING ทำให้ INFO log ของ app (เช่น keep-alive ping) ถูกกลืนไม่ขึ้น Render log
logging.basicConfig(level=logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)  # กัน BEGIN/COMMIT รกทุก query
# Never emit HTTP transport URLs: Graph API query strings may contain tokens.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
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
    """นโยบายข้อมูลส่วนบุคคล (PDPA) & TikTok Privacy Policy"""
    return """<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="tiktok-developers-site-verification" content="aw2u4qsbt1fl8su8">
<title>นโยบายความเป็นส่วนตัว | Pakhem Privacy Policy</title>
<style>body{font-family:'Leelawadee UI',Tahoma,sans-serif;max-width:640px;margin:40px auto;padding:0 20px;line-height:1.7;color:#333}h1{color:#E74C3C}</style>
</head>
<body>
<h1>🔒 นโยบายความเป็นส่วนตัว (Privacy Policy & PDPA)</h1>
<p>ร้าน "ป้าเข็ม ขายของ" และแอปพลิเคชันระบบอัตโนมัติ เก็บข้อมูลส่วนบุคคลเพียงเท่าที่จำเป็น เพื่อให้บริการค้นหา แนะนำสินค้า และเผยแพร่คอนเทนต์</p>
<h2>เราเก็บอะไร</h2>
<ul>
<li>ชื่อบัญชี และ ID สำหรับการยืนยันตัวตนและการบริการ</li>
<li>ประวัติการสนทนาและบันทึกการส่งคอนเทนต์ นานสูงสุด 90 วัน</li>
</ul>
<h2>เราไม่เก็บอะไร</h2>
<ul>
<li>ไม่เก็บข้อมูลบัตร/ข้อมูลการเงินที่ละเอียดอ่อน · ไม่ขายข้อมูลให้บุคคลภายนอก</li>
</ul>
<h2>สิทธิ์ของคุณ</h2>
<ul>
<li>ลบข้อมูลได้ตลอดเวลา หรือติดต่อเจ้าหน้าที่ได้ตลอด 24 ชม.</li>
</ul>
<p>สอบถามเพิ่มเติม: ติดต่อผ่านระบบ LINE OA หรืออีเมล g81393878@gmail.com ค่ะ</p>
</body>
</html>"""


@app.get("/terms", response_class=HTMLResponse)
def terms_of_service():
    """เงื่อนไขการให้บริการ (Terms of Service) สำหรับ TikTok App Review"""
    return """<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="tiktok-developers-site-verification" content="aw2u4qsbt1fl8su8">
<title>เงื่อนไขการให้บริการ | Pakhem Terms of Service</title>
<style>body{font-family:'Leelawadee UI',Tahoma,sans-serif;max-width:640px;margin:40px auto;padding:0 20px;line-height:1.7;color:#333}h1{color:#2C3E50}</style>
</head>
<body>
<h1>📜 เงื่อนไขการให้บริการ (Terms of Service)</h1>
<p>ยินดีต้อนรับสู่บริการระบบจัดการคอนเทนต์และแนะนำสินค้า "ป้าเข็ม"</p>
<h2>1. การใช้งานบริการ</h2>
<p>ผู้ใช้บริการตกลงที่จะใช้ระบบเพื่อการบริหารจัดการคอนเทนต์ แนะนำสินค้า และรับข้อมูลข่าวสารโปรโมชั่นอย่างถูกต้องตามกฎหมายและนโยบายของแต่ละแพลตฟอร์ม</p>
<h2>2. ความรับผิดชอบในเนื้อหา</h2>
<p>เนื้อหาวิดีโอและแคปชั่นที่ผลิตขึ้นผ่านระบบเป็นไปตามมาตรฐานการตลาด ไม่ละเมิดลิขสิทธิ์ และเคารพกฎเกณฑ์ของชุมชน TikTok / Meta / YouTube</p>
<h2>3. การติดต่อ</h2>
<p>หากมีข้อสงสัยเกี่ยวกับเงื่อนไขการให้บริการ สามารถติดต่อได้ที่ g81393878@gmail.com</p>
</body>
</html>"""


@app.get("/tiktok-developers-site-verification{rest:path}", response_class=HTMLResponse)
def tiktok_verification_route(rest: str = ""):
    """TikTok Developer Site Signature Verification Handler (รองรับทุกพาธและนามสกุล)"""
    return """<!DOCTYPE html>
<html>
<head>
<meta name="tiktok-developers-site-verification" content="aw2u4qsbt1fl8su8">
</head>
<body>
tiktok-developers-site-verification=aw2u4qsbt1fl8su8
</body>
</html>"""


@app.get("/api/tarot/tts")
async def tarot_tts_endpoint(card_num: int = 1, pos_idx: int = 1):
    """🎙️ บริการสตรีมเสียงพากย์ป้าเข็มแท้ 100% (Microsoft Edge Neural TTS: th-TH-PremwadeeNeural)
    เล่นได้ทุกเครื่อง ทั้ง iOS Safari, LINE In-App Browser และ Android
    """
    import hashlib
    import tempfile
    from pathlib import Path
    from app.services.product_cards import get_tarot_card_by_number
    
    positions_info = [
        "ตัวตนและสภาวะปัจจุบัน", "อุปสรรคและแรงต้านที่ขวางทับ", "จิตสำนึกและเป้าหมายในหัว",
        "จิตใต้สำนึกและรากเหง้าของปัญหา", "อดีตที่เพิ่งผ่านพ้นมา", "อนาคตอันใกล้",
        "ทัศนคติและมุมมองของตัวคุณ", "อิทธิพลคนรอบตัวและสิ่งแวดล้อม", "ความหวังลึกๆ และความกลัวในใจ",
        "บทสรุปสูงสุดและผลลัพธ์ปลายทาง"
    ]
    p_name = positions_info[(pos_idx - 1) % len(positions_info)]
    card = get_tarot_card_by_number(card_num)
    
    text = (
        f"ตำแหน่งที่ {pos_idx} {p_name} ท่านได้ไพ่ {card.get('thai')} {card.get('name')} "
        f"{card.get('desc')} ข้อคิดคำแนะนำจากป้าเข็มคือ {card.get('advice')}"
    )
    
    # แคชไฟล์เสียงตาม hash เพื่อให้โหลดได้ทันที
    cache_dir = Path(tempfile.gettempdir()) / "tarot_tts_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    audio_path = cache_dir / f"tarot_{text_hash}.mp3"
    
    if not audio_path.exists():
        import edge_tts
        communicate = edge_tts.Communicate(text, "th-TH-PremwadeeNeural", rate="+10%")
        await communicate.save(str(audio_path))
        
    return Response(content=audio_path.read_bytes(), media_type="audio/mpeg")


@app.get("/tarot/reading/{reading_id}", response_class=HTMLResponse)
def tarot_celtic_reading_player(reading_id: str):
    """🎬 โรงภาพยนตร์คำทำนายไพ่ยิปซี 10 ใบ ป้าเข็ม (Personalized Celtic Cross Video/Audio Player)
    เปิดดูภาพไพ่ HD ขนาดใหญ่ 10 ตำแหน่ง พร้อมเสียงพากย์วิเคราะห์ชะตาชีวิตทีละใบแบบละเอียด ไม่รีบเร่ง
    """
    from app.db import SessionLocal
    from app import models
    from app.services.product_cards import get_tarot_card_by_number
    import json, re
    
    cards_data = [4, 5, 3, 2, 8, 15, 23, 21, 19, 9] # fallback
    video_url = ""
    db = SessionLocal()
    try:
        r = db.query(models.TarotReading).filter(models.TarotReading.reading_id == reading_id).first()
        if r:
            if r.cards_data:
                cards_data = r.cards_data
            if r.video_url:
                video_url = r.video_url
    except Exception as e:
        logger.warning(f"Failed to fetch reading {reading_id}: {e}")
    finally:
        db.close()

    yt_embed = ""
    if video_url:
        m = re.search(r'(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})', video_url)
        if m:
            yt_embed = f"https://www.youtube.com/embed/{m.group(1)}?rel=0"

    video_html = ""
    if yt_embed:
        video_html = f"""
  <div style="width: 100%; max-width: 460px; margin-bottom: 20px; border-radius: 18px; overflow: hidden; border: 2px solid var(--gold); box-shadow: 0 10px 30px rgba(0,0,0,0.8); background: #000;">
    <div style="position: relative; padding-bottom: 177.77%; height: 0;">
      <iframe src="{yt_embed}" style="position: absolute; top:0; left: 0; width: 100%; height: 100%;" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
    </div>
    <div style="padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; background: #171026;">
      <span style="font-size: 13px; color: var(--gold-light);">🎬 วิดีโอทำนายดวงเซลติกครอส</span>
      <a href="{video_url}" target="_blank" style="color: #FFF; background: #FF0000; padding: 6px 12px; border-radius: 16px; text-decoration: none; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 4px;">▶️ YouTube Shorts</a>
    </div>
  </div>
"""
    elif video_url and "youtube.com" in video_url:
        video_html = f"""
  <div style="margin-bottom: 15px;">
    <a href="{video_url}" target="_blank" style="color: #FFF; background: #FF0000; padding: 8px 16px; border-radius: 20px; text-decoration: none; font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;">▶️ ชมคลิปบน YouTube Shorts</a>
  </div>
"""
        
    positions_info = [
        {"title": "1. ตัวตนและสภาวะปัจจุบัน", "color": "#4338CA"},
        {"title": "2. อุปสรรคและแรงต้านที่ขวางทับ", "color": "#DC2626"},
        {"title": "3. จิตสำนึกและเป้าหมายในหัว", "color": "#D97706"},
        {"title": "4. จิตใต้สำนึกและรากเหง้าของปัญหา", "color": "#0D9488"},
        {"title": "5. อดีตที่เพิ่งผ่านพ้นมา", "color": "#475569"},
        {"title": "6. อนาคตอันใกล้ (1-3 เดือน)", "color": "#2563EB"},
        {"title": "7. ทัศนคติและมุมมองของตัวคุณ", "color": "#7C3AED"},
        {"title": "8. อิทธิพลคนรอบตัวและสิ่งแวดล้อม", "color": "#059669"},
        {"title": "9. ความหวังลึกๆ และความกลัวในใจ", "color": "#E11D48"},
        {"title": "10. บทสรุปสูงสุดและผลลัพธ์ปลายทาง", "color": "#B45309"},
    ]
    
    deck_cards = []
    for idx, num in enumerate(cards_data[:10]):
        c = get_tarot_card_by_number(num)
        pos = positions_info[idx] if idx < len(positions_info) else {"title": f"{idx+1}. ตำแหน่งทำนาย", "color": "#4338CA"}
        deck_cards.append({
            "idx": idx + 1,
            "pos": pos["title"],
            "color": pos["color"],
            "num": num,
            "name": c.get("name", "Tarot"),
            "thai": c.get("thai", "ไพ่ทาโรต์"),
            "keyword": c.get("keyword", ""),
            "desc": c.get("desc", ""),
            "advice": c.get("advice", ""),
            "img": c.get("img", "https://cdn.jsdelivr.net/gh/lalesleon13-hash/Tarot@main/RWS_Tarot_00_Fool.jpg")
        })
        
    cards_json = json.dumps(deck_cards, ensure_ascii=False)
    
    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>🎬 คำทำนายเซลติกครอส 10 ใบฉบับเต็ม | ป้าเข็ม พยากรณ์</title>
<link href="https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;600;700&family=Cinzel:wght@700;900&display=swap" rel="stylesheet">
<style>
  :root {{
    --gold: #F59E0B;
    --gold-light: #FDE047;
    --purple-deep: #0B0813;
    --purple-surface: #171026;
    --purple-border: rgba(168, 85, 247, 0.3);
    --text-main: #F8FAFC;
    --text-sub: #94A3B8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
  body {{
    font-family: 'Kanit', sans-serif;
    background: radial-gradient(circle at 50% 15%, #23123D 0%, #0B0813 85%);
    color: var(--text-main);
    min-height: 100vh;
    padding: 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }}
  .header {{
    text-align: center;
    margin-bottom: 20px;
    max-width: 500px;
  }}
  .header h1 {{
    font-family: 'Cinzel', serif;
    font-size: 22px;
    color: var(--gold-light);
    letter-spacing: 1px;
  }}
  .header .badge {{
    display: inline-block;
    background: rgba(245, 158, 11, 0.15);
    color: var(--gold);
    border: 1px solid var(--gold);
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 11px;
    margin-top: 6px;
  }}
  .theater-container {{
    width: 100%;
    max-width: 460px;
    background: var(--purple-surface);
    border: 1px solid var(--purple-border);
    border-radius: 20px;
    padding: 20px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.6);
    display: flex;
    flex-direction: column;
    align-items: center;
  }}
  .pos-badge {{
    padding: 6px 14px;
    border-radius: 30px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 12px;
    color: #FFF;
    background: #4338CA;
    transition: all 0.3s ease;
  }}
  .card-display {{
    width: 220px;
    height: 350px;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 12px 30px rgba(0,0,0,0.8), 0 0 20px rgba(245, 158, 11, 0.3);
    border: 2px solid rgba(253, 224, 71, 0.4);
    margin-bottom: 16px;
    position: relative;
    background: #000;
  }}
  .card-display img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.4s ease;
  }}
  .card-info {{
    text-align: center;
    width: 100%;
    margin-bottom: 16px;
  }}
  .card-name {{
    font-size: 20px;
    font-weight: 700;
    color: var(--gold-light);
  }}
  .card-thai {{
    font-size: 14px;
    color: var(--text-sub);
    margin-bottom: 8px;
  }}
  .card-keyword {{
    font-size: 12px;
    color: #A78BFA;
    background: rgba(139, 92, 246, 0.15);
    padding: 4px 10px;
    border-radius: 8px;
    display: inline-block;
    margin-bottom: 12px;
  }}
  .card-desc {{
    font-size: 14px;
    line-height: 1.6;
    color: #E2E8F0;
    margin-bottom: 10px;
    text-align: left;
    background: rgba(255,255,255,0.03);
    padding: 12px;
    border-radius: 10px;
    border-left: 3px solid var(--gold);
  }}
  .card-advice {{
    font-size: 13px;
    line-height: 1.5;
    color: #CBD5E1;
    text-align: left;
    background: rgba(99, 102, 241, 0.1);
    padding: 10px;
    border-radius: 8px;
    border-left: 3px solid #6366F1;
  }}
  .controls {{
    display: flex;
    gap: 10px;
    width: 100%;
    margin-top: 10px;
  }}
  .btn {{
    flex: 1;
    padding: 12px 14px;
    border-radius: 12px;
    border: none;
    cursor: pointer;
    font-family: 'Kanit', sans-serif;
    font-weight: 600;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    transition: all 0.2s;
  }}
  .btn-prev {{
    background: rgba(255,255,255,0.1);
    color: #FFF;
  }}
  .btn-next {{
    background: linear-gradient(135deg, #F59E0B, #D97706);
    color: #000;
    font-weight: 700;
  }}
  .btn-speak {{
    width: 100%;
    margin-top: 10px;
    background: linear-gradient(135deg, #6366F1, #4338CA);
    color: #FFF;
    padding: 12px;
    border-radius: 12px;
  }}
  .grid-nav {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
    width: 100%;
    margin-top: 20px;
  }}
  .grid-btn {{
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    color: var(--text-sub);
    padding: 8px 0;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }}
  .grid-btn.active {{
    background: var(--gold);
    color: #000;
    border-color: var(--gold-light);
    font-weight: 700;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>THE CELTIC CROSS</h1>
  <div class="badge">รหัสคำทำนาย: {reading_id}</div>
  <div style="margin-top: 10px;">
    <a href="/tarot" style="color: var(--gold-light); font-size: 13px; text-decoration: none; border: 1px solid rgba(245,158,11,0.4); padding: 5px 16px; border-radius: 20px; background: rgba(245,158,11,0.12); display: inline-block;">🔮 กลับไปหน้าสุ่ม / เลือกไพ่ 10 ใบ</a>
  </div>
</div>

{video_html}

<div class="theater-container">
  <div id="pos-badge" class="pos-badge">1. ตัวตนและสภาวะปัจจุบัน</div>
  
  <div class="card-display">
    <img id="card-img" src="" alt="Tarot Card">
  </div>
  
  <div class="card-info">
    <div id="card-name" class="card-name">The Empress</div>
    <div id="card-thai" class="card-thai">(จักรพรรดินี)</div>
    <div id="card-keyword" class="card-keyword">ความอุดมสมบูรณ์ • สุขสมหวัง</div>
    <div id="card-desc" class="card-desc">...</div>
    <div id="card-advice" class="card-advice">...</div>
  </div>

  <button id="btn-speak" class="btn btn-speak" onclick="toggleVoice()">
    🔊 ฟังเสียงพากย์ป้าเข็ม (วิเคราะห์ใบนี้)
  </button>

  <div class="controls">
    <button class="btn btn-prev" onclick="changeCard(-1)">‹ ใบก่อนหน้า</button>
    <button class="btn btn-next" onclick="changeCard(1)">ใบถัดไป ›</button>
  </div>

  <div class="grid-nav" id="grid-nav"></div>
</div>

<script>
const cards = {cards_json};
let currentIndex = 0;
let audioPlayer = new Audio();
let isPlaying = false;

function renderGrid() {{
  const nav = document.getElementById('grid-nav');
  nav.innerHTML = '';
  cards.forEach((c, idx) => {{
    const b = document.createElement('button');
    b.className = 'grid-btn' + (idx === currentIndex ? ' active' : '');
    b.innerText = `ใบที่ ${{idx + 1}}`;
    b.onclick = () => selectCard(idx);
    nav.appendChild(b);
  }});
}}

function showCard(idx) {{
  if (idx < 0) idx = 0;
  if (idx >= cards.length) idx = cards.length - 1;
  currentIndex = idx;
  const c = cards[idx];
  
  document.getElementById('pos-badge').innerText = c.pos;
  document.getElementById('pos-badge').style.background = c.color;
  document.getElementById('card-img').src = c.img;
  document.getElementById('card-name').innerText = c.name;
  document.getElementById('card-thai').innerText = `(${{c.thai}})`;
  document.getElementById('card-keyword').innerText = c.keyword;
  document.getElementById('card-desc').innerText = `✨ คำทำนาย: ${{c.desc}}`;
  document.getElementById('card-advice').innerText = `💡 คำแนะนำป้าเข็ม: ${{c.advice}}`;
  
  renderGrid();
}}

function changeCard(dir) {{
  stopVoice();
  showCard(currentIndex + dir);
}}

function selectCard(idx) {{
  stopVoice();
  showCard(idx);
}}

function stopVoice() {{
  if (audioPlayer) {{
    audioPlayer.pause();
    audioPlayer.currentTime = 0;
  }}
  isPlaying = false;
  const btn = document.getElementById('btn-speak');
  if (btn) btn.innerHTML = '🔊 ฟังเสียงพากย์ป้าเข็ม (วิเคราะห์ใบนี้)';
}}

function toggleVoice() {{
  if (isPlaying) {{
    stopVoice();
    return;
  }}
  playVoice();
}}

function playVoice() {{
  const c = cards[currentIndex];
  const btn = document.getElementById('btn-speak');
  if (btn) btn.innerHTML = '⏳ ป้าเข็มกำลังตั้งจิตอ่านคำทำนาย...';
  
  const audioUrl = `/api/tarot/tts?card_num=${{c.num}}&pos_idx=${{c.idx}}`;
  audioPlayer.src = audioUrl;
  
  audioPlayer.onplay = () => {{
    isPlaying = true;
    if (btn) btn.innerHTML = '⏸️ หยุดฟังเสียงป้าเข็ม';
  }};
  
  audioPlayer.onended = () => {{
    stopVoice();
  }};
  
  audioPlayer.onerror = (e) => {{
    console.warn('Audio play error, fallback:', e);
    stopVoice();
    if (btn) btn.innerHTML = '🔊 ฟังเสียงพากย์ป้าเข็ม (วิเคราะห์ใบนี้)';
  }};
  
  audioPlayer.play().catch(err => {{
    console.warn('Playback blocked by browser:', err);
    stopVoice();
  }});
}}

// เริ่มต้นใบแรก
showCard(0);
</script>

</body>
</html>"""
    return html


@app.get("/tarot", response_class=HTMLResponse)
def tarot_web_app():
    """🔮 Web App เปิดไพ่ยิปซีจิตวิทยา 3D สไตล์สายมูโมเดิร์น (ตอบสนองไว ไม่รกตา)"""
    return """<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>🔮 ศาสตร์ไพ่ยิปซีแท้ 22 ใบ | ป้าเข็ม พยากรณ์</title>
<link href="https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;600;700&family=Cinzel:wght@600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --gold: #F59E0B;
    --gold-light: #FDE047;
    --gold-glow: rgba(245, 158, 11, 0.4);
    --purple-deep: #0B0813;
    --purple-surface: #171026;
    --purple-card: #231938;
    --purple-border: rgba(168, 85, 247, 0.3);
    --text-main: #F8FAFC;
    --text-sub: #94A3B8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  body {
    font-family: 'Kanit', sans-serif;
    background: radial-gradient(circle at 50% 10%, #2A174E 0%, #0B0813 80%);
    color: var(--text-main);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    overflow-x: hidden;
    position: relative;
  }
  .stars {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background-image: radial-gradient(2px 2px at 20px 30px, #eee, rgba(0,0,0,0)),
                      radial-gradient(2px 2px at 40px 70px, #FDE047, rgba(0,0,0,0)),
                      radial-gradient(1.5px 1.5px at 90px 40px, #fff, rgba(0,0,0,0));
    background-repeat: repeat;
    background-size: 200px 200px;
    opacity: 0.25;
    pointer-events: none;
    z-index: 0;
  }
  header {
    width: 100%;
    max-width: 480px;
    padding: 24px 20px 12px;
    text-align: center;
    position: relative;
    z-index: 10;
  }
  .badge-tag {
    display: inline-block;
    padding: 4px 14px;
    background: rgba(245, 158, 11, 0.15);
    border: 1px solid var(--gold);
    border-radius: 999px;
    color: var(--gold-light);
    font-size: 11px;
    font-weight: 600;
    margin-bottom: 8px;
    box-shadow: 0 0 15px var(--gold-glow);
  }
  h1 {
    font-size: 22px;
    font-weight: 700;
    background: linear-gradient(135deg, #FFF 20%, #FDE047 60%, #F59E0B 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .sub-title { font-size: 13px; color: var(--text-sub); margin-top: 4px; }
  .app-container {
    width: 100%;
    max-width: 480px;
    padding: 10px 16px 40px;
    display: flex;
    flex-direction: column;
    align-items: center;
    position: relative;
    z-index: 10;
  }
  #intro-stage {
    width: 100%;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px 0;
  }
  .deck-visual {
    position: relative;
    width: 140px;
    height: 220px;
    margin: 24px 0;
    cursor: pointer;
  }
  .deck-card {
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    border-radius: 12px;
    background: url("https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop") center/cover;
    border: 2px solid var(--gold);
    box-shadow: 0 10px 25px rgba(0,0,0,0.6), 0 0 20px var(--gold-glow);
    transition: transform 0.4s ease;
  }
  .deck-card:nth-child(1) { transform: rotate(-6deg) translateY(-4px); }
  .deck-card:nth-child(2) { transform: rotate(4deg) translateY(-2px); }
  .deck-card:nth-child(3) { transform: rotate(0deg); }
  .btn-primary {
    background: linear-gradient(135deg, #F59E0B 0%, #D97706 100%);
    color: #1A0C00;
    font-weight: 700;
    font-size: 16px;
    padding: 14px 36px;
    border-radius: 999px;
    border: none;
    cursor: pointer;
    box-shadow: 0 4px 20px var(--gold-glow);
    font-family: 'Kanit', sans-serif;
  }
  #pick-stage {
    display: none;
    width: 100%;
    flex-direction: column;
    align-items: center;
  }
  .instruction-box {
    font-size: 13px;
    color: var(--gold-light);
    margin-bottom: 20px;
    background: rgba(35, 25, 56, 0.7);
    padding: 8px 18px;
    border-radius: 20px;
    border: 1px solid var(--purple-border);
  }
  .cards-carousel-container {
    width: 100%;
    overflow-x: auto;
    padding: 20px 10px 40px;
    display: flex;
    gap: 14px;
    scroll-snap-type: x mandatory;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .cards-carousel-container::-webkit-scrollbar { display: none; }
  .tarot-slot {
    flex: 0 0 110px;
    height: 180px;
    border-radius: 10px;
    background: url("https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop") center/cover;
    border: 1.5px solid var(--gold);
    box-shadow: 0 8px 16px rgba(0,0,0,0.5);
    scroll-snap-align: center;
    cursor: pointer;
    transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.3s;
    position: relative;
    overflow: hidden;
  }
  .tarot-slot:active, .tarot-slot.selected {
    transform: translateY(-20px) scale(1.08);
    box-shadow: 0 12px 30px rgba(245, 158, 11, 0.6), 0 0 25px var(--gold-glow);
    border-color: #FFF;
  }
  .tarot-slot-num {
    position: absolute;
    bottom: 6px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0,0,0,0.7);
    color: var(--gold-light);
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 10px;
    font-family: 'Cinzel', serif;
  }
  #reveal-stage {
    display: none;
    width: 100%;
    flex-direction: column;
    align-items: center;
    animation: fadeIn 0.6s ease-out;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(15px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .card-3d-wrapper {
    width: 190px;
    height: 310px;
    margin: 10px 0 24px;
    perspective: 1000px;
  }
  .card-3d-inner {
    width: 100%; height: 100%;
    position: relative;
    transform-style: preserve-3d;
    transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 16px 35px rgba(0,0,0,0.7), 0 0 30px var(--gold-glow);
    border-radius: 14px;
  }
  .card-3d-inner.flipped { transform: rotateY(180deg); }
  .card-side {
    position: absolute;
    width: 100%; height: 100%;
    backface-visibility: hidden;
    border-radius: 14px;
    border: 2px solid var(--gold);
    overflow: hidden;
  }
  .card-back {
    background: url("https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop") center/cover;
  }
  .card-front { transform: rotateY(180deg); background: #111; }
  .card-front img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .reading-card-box {
    width: 100%;
    background: var(--purple-card);
    border: 1px solid var(--purple-border);
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.4);
    margin-bottom: 20px;
  }
  .card-title-header {
    text-align: center;
    padding-bottom: 14px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 14px;
  }
  .card-name-en {
    font-family: 'Cinzel', serif;
    font-size: 18px;
    font-weight: 800;
    color: var(--gold-light);
  }
  .card-name-th { font-size: 14px; color: var(--text-sub); margin-top: 2px; }
  .card-tagline {
    display: inline-block;
    font-size: 11px;
    color: #38BDF8;
    background: rgba(56, 189, 248, 0.12);
    padding: 3px 10px;
    border-radius: 6px;
    margin-top: 8px;
  }
  .section-label { font-size: 12px; font-weight: 600; color: var(--gold); margin-bottom: 4px; }
  .section-desc { font-size: 13px; line-height: 1.6; color: #E2E8F0; }
  .pakhem-advice {
    background: rgba(16, 185, 129, 0.1);
    border-left: 3px solid #10B981;
    padding: 10px 14px;
    border-radius: 0 8px 8px 0;
    font-size: 12px;
    color: #A7F3D0;
    line-height: 1.6;
    margin-top: 10px;
  }
  .lucky-item-box {
    width: 100%;
    background: linear-gradient(135deg, rgba(234, 88, 12, 0.15), rgba(245, 158, 11, 0.05));
    border: 1px solid rgba(245, 158, 11, 0.4);
    border-radius: 14px;
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 24px;
  }
  .lucky-item-img {
    width: 65px; height: 65px;
    border-radius: 10px;
    object-fit: cover;
    border: 1px solid var(--gold);
    flex-shrink: 0;
  }
  .lucky-item-info { flex: 1; min-width: 0; }
  .lucky-item-title { font-size: 13px; font-weight: 600; color: #FFF; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .lucky-item-sub { font-size: 11px; color: var(--gold-light); margin: 3px 0 8px; }
  .btn-shopee {
    display: inline-block;
    background: #EE4D2D;
    color: #FFF;
    font-size: 11px;
    font-weight: 600;
    padding: 6px 14px;
    border-radius: 999px;
    text-decoration: none;
  }
  .action-row { display: flex; gap: 10px; width: 100%; }
  .btn-action {
    flex: 1;
    padding: 12px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 600;
    border: 1px solid var(--purple-border);
    background: var(--purple-surface);
    color: var(--text-main);
    cursor: pointer;
    text-align: center;
    font-family: 'Kanit', sans-serif;
  }
</style>
</head>
<body>
<div class="stars"></div>
<header>
  <div class="badge-tag">✨ MAJOR ARCANA 22 ใบแท้</div>
  <h1>ห้องเปิดไพ่ยิปซีจิตวิทยา</h1>
  <p class="sub-title">สะท้อนพลังจิตใต้สำนึก & ชี้ทางสว่าง โดย ป้าเข็ม</p>
</header>

<div class="app-container">
  <!-- STAGE 1: เริ่มต้น -->
  <div id="intro-stage">
    <div class="deck-visual" onclick="startShuffling()">
      <div class="deck-card"></div>
      <div class="deck-card"></div>
      <div class="deck-card"></div>
    </div>
    <button class="btn-primary" onclick="startShuffling()">🔮 ตั้งจิตอธิษฐาน & สับไพ่</button>
    <p style="font-size: 12px; color: var(--text-sub); margin-top: 14px;">สูดหายใจลึกๆ นึกถึงเรื่องที่อยากรู้ในใจ 3 วินาที</p>
  </div>

  <!-- STAGE 2: คลี่ไพ่ให้เลือก 22 ใบ -->
  <div id="pick-stage">
    <div class="instruction-box">👈 เลื่อนซ้าย-ขวา แล้วแตะไพ่ใบที่ดึงดูดใจคุณที่สุด 👉</div>
    <div class="cards-carousel-container" id="carousel"></div>
  </div>

  <!-- STAGE 3: เฉลยคำทำนาย -->
  <div id="reveal-stage">
    <div class="card-3d-wrapper">
      <div class="card-3d-inner" id="card3d">
        <div class="card-side card-back"></div>
        <div class="card-side card-front">
          <img id="revealed-img" src="" alt="Tarot Card">
        </div>
      </div>
    </div>

    <div class="reading-card-box">
      <div class="card-title-header">
        <div class="card-name-en" id="r-name-en"></div>
        <div class="card-name-th" id="r-name-th"></div>
        <div class="card-tagline" id="r-keyword"></div>
      </div>
      <div class="section-block">
        <div class="section-label">🧠 สาส์นสะท้อนจากจิตใต้สำนึก:</div>
        <div class="section-desc" id="r-desc"></div>
      </div>
      <div class="pakhem-advice" id="r-advice"></div>
    </div>

    <div class="lucky-item-box">
      <img id="item-img" class="lucky-item-img" src="https://images.unsplash.com/photo-1601024445121-e28256338b0a?w=400&auto=format&fit=crop">
      <div class="lucky-item-info">
        <div class="lucky-item-title" id="item-name">ไอเทมเสริมพลังบวกประจำไพ่</div>
        <div class="lucky-item-sub" id="item-sub">เสริมสิริมงคล ของแท้ 100%</div>
        <a id="item-link" class="btn-shopee" href="#" target="_blank">🛒 ดูใน Shopee</a>
      </div>
    </div>

    <div class="action-row">
      <button class="btn-action" onclick="resetDeck()">🔄 เปิดใหม่อีกครั้ง</button>
      <button class="btn-action" style="border-color: var(--gold); color: var(--gold-light);" onclick="shareReading()">📤 แชร์คำทำนาย</button>
    </div>
  </div>
</div>

<script>
const TAROT_CDN = 'https://cdn.jsdelivr.net/gh/lalesleon13-hash/Tarot@main/';
const TAROT_DATA = [
  { id: 0, name: 'The Fool', thai: 'ใบที่ 0: คนพเนจร', keyword: 'การเริ่มต้นใหม่ • อิสรภาพ • ความกล้าเสี่ยง', desc: 'จิตใต้สำนึกของคุณพร้อมแล้วที่จะก้าวสู่บทใหม่ของชีวิต ปลดปล่อยความกลัวแล้วออกเดินทางด้วยหัวใจที่เบิกบาน', advice: 'ป้าเข็มชวนคิด: "อย่าให้ความกังวลในอดีตมาฉุดรั้งก้าวแรกของคุณ วันนี้คือวันที่ดีที่สุดในการเริ่มต้นใหม่จ้า"', img: TAROT_CDN + 'RWS_Tarot_00_Fool.jpg', item: 'กระเป๋าพกพาเสริมโชค', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 1, name: 'The Magician', thai: 'ใบที่ 1: จอมเวท', keyword: 'พรสวรรค์ • สติปัญญา • การลงมือทำ', desc: 'คุณมีทักษะและเครื่องมือครบครันอยู่ในมือ สิ่งที่คุณตั้งใจจะสร้างสามารถเกิดขึ้นได้จริง ขอเพียงมีสมาธิและลงมือทำอย่างมั่นใจ', advice: 'ป้าเข็มชวนคิด: "โอกาสมาถึงแล้ว ทักษะที่คุณสั่งสมมาจะช่วยให้คุณชนะทุกปัญหาอย่างแน่นอนลูก"', img: TAROT_CDN + 'RWS_Tarot_01_Magician.jpg', item: 'ปากกาเซ็นสัญญามงคล', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 2, name: 'The High Priestess', thai: 'ใบที่ 2: นักบวชหญิง', keyword: 'ซิกซ์เซนส์ • ความสงบนิ่ง • ลางสังหรณ์', desc: 'ฟังเสียงกระซิบในหัวใจตัวเองให้ดี คำตอบที่คุณตามหาไม่ได้อยู่ข้างนอก แต่อยู่ที่ความสงบและการสังเกตอย่างลึกซึ้ง', advice: 'ป้าเข็มชวนคิด: "บางเรื่องไม่ต้องรีบพูด ให้เวลาและสัญชาตญาณนำทาง ความจริงจะปรากฏเองจ้า"', img: TAROT_CDN + 'RWS_Tarot_02_High_Priestess.jpg', item: 'หินไหมทองนำโชคแท้', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 3, name: 'The Empress', thai: 'ใบที่ 3: จักรพรรดินี', keyword: 'ความอุดมสมบูรณ์ • ความเมตตา • การงอกงาม', desc: 'สิ่งที่ทุ่มเทหว่านเมล็ดพันธุ์ไว้กำลังจะออกดอกออกผล ความรัก การเงิน และความสุขในครอบครัวกำลังเติบโตอย่างงดงาม', advice: 'ป้าเข็มชวนคิด: "ใจดีกับตัวเองและคนรอบข้าง ความอ่อนโยนจะนำพาความมั่งคั่งมาให้คุณเองนะลูก"', img: TAROT_CDN + 'RWS_Tarot_03_Empress.jpg', item: 'สร้อยคอเสริมเสน่ห์', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 4, name: 'The Emperor', thai: 'ใบที่ 4: จักรพรรดิ', keyword: 'อำนาจ • ความมั่นคง • ภาวะผู้นำ', desc: 'ถึงเวลาตั้งหลักและวางระบบระเบียบ ความเด็ดขาดและมีวินัยจะช่วยให้คุณคุมสถานการณ์ที่ยากลำบากให้อยู่หมัด', advice: 'ป้าเข็มชวนคิด: "ความสำเร็จที่ยั่งยืนสร้างจากความมีวินัย ยืนหยัดในจุดยืนแล้วเดินหน้าต่ออย่างสง่างามจ้า"', img: TAROT_CDN + 'RWS_Tarot_04_Emperor.jpg', item: 'นาฬิกาข้อมือเสริมบารมี', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 5, name: 'The Hierophant', thai: 'ใบที่ 5: สังฆราช', keyword: 'คุณธรรม • ผู้ใหญ่ค้ำจุน • ความถูกต้อง', desc: 'หากกำลังเจอปัญหา ให้ปรึกษาผู้ใหญ่ที่มีประสบการณ์ หรือยึดมั่นในหลักศีลธรรมและความถูกต้อง แล้วผลลัพธ์จะคุ้มครองคุณ', advice: 'ป้าเข็มชวนคิด: "ทำสิ่งที่ถูกต้อง แม้ในวันที่ไม่มีใครเห็น ความดีจะคุ้มครองและเปิดทางสว่างให้เสมอจ้า"', img: TAROT_CDN + 'RWS_Tarot_05_Hierophant.jpg', item: 'จี้พระมงคลคุ้มภัย', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 6, name: 'The Lovers', thai: 'ใบที่ 6: คู่รัก', keyword: 'ความผูกพัน • พรหมลิขิต • ทางแยกที่ต้องเลือก', desc: 'ความสัมพันธ์ที่กลมเกลียวและการตัดสินใจด้วยหัวใจที่ซื่อตรง เลือกสิ่งที่คุณรักอย่างแท้จริงแล้วชีวิตจะมีความสุข', advice: 'ป้าเข็มชวนคิด: "ความรักที่ดีเริ่มต้นจากการรักตัวเอง เมื่อใจเราเต็ม เราจะดึงดูดคนที่ใช่เข้ามาเองนะลูก"', img: TAROT_CDN + 'RWS_Tarot_06_Lovers.jpg', item: 'แหวนเงินแท้เสริมรัก', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 7, name: 'The Chariot', thai: 'ใบที่ 7: นักรบรถศึก', keyword: 'ชัยชนะ • ความมุ่งมั่น • การฝ่าฟัน', desc: 'แม้เส้นทางข้างหน้าจะขรุขระ แต่พลังใจและความไม่ย่อท้อของคุณจะนำพาชัยชนะและความสำเร็จมาให้อย่างแน่นอน', advice: 'ป้าเข็มชวนคิด: "กัดฟันสู้ต่ออีกนิด โค้งสุดท้ายนี้ชัยชนะรออยู่เบื้องหน้า อย่าเพิ่งถอดใจนะลูก"', img: TAROT_CDN + 'RWS_Tarot_07_Chariot.jpg', item: 'น้ำหอมปรับอากาศในรถ', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 8, name: 'Strength', thai: 'ใบที่ 8: ความแข็งแกร่ง', keyword: 'พลังความอดทน • เมตตาสยบความโกรธ', desc: 'ความแข็งแกร่งที่แท้จริงไม่ใช่การใช้กำลัง แต่คือการควบคุมอารมณ์ตนเองและความอ่อนโยนที่สามารถชนะใจทุกคนได้', advice: 'ป้าเข็มชวนคิด: "น้ำหยดลงหินทุกวันหินยังกร่อน ความใจเย็นและเมตตาจะคลี่คลายปัญหาได้ทุกอย่างจ้า"', img: TAROT_CDN + 'RWS_Tarot_08_Strength.jpg', item: 'กำไลหินมงคลสยบเคราะห์', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 9, name: 'The Hermit', thai: 'ใบที่ 9: ฤๅษี', keyword: 'ความสงบ • การทบทวนตัวเอง • ปัญญา', desc: 'ถอยออกมาจากความวุ่นวายสักพัก ให้เวลาอยู่กับตัวเองเพื่อทบทวนทิศทางชีวิต แสงสว่างทางปัญญาจะเกิดขึ้นในความเงียบ', advice: 'ป้าเข็มชวนคิด: "บางครั้งการหยุดเพื่อคิด สำคัญกว่าการรีบวิ่งแล้วหลงทาง พักใจให้สงบแล้วค่อยลุยใหม่นะลูก"', img: TAROT_CDN + 'RWS_Tarot_09_Hermit.jpg', item: 'โคมไฟแสงอบอุ่นสร้างสมาธิ', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 10, name: 'Wheel of Fortune', thai: 'ใบที่ 10: กงล้อโชคชะตา', keyword: 'จุดพลิกผัน • โชคลาภ • จังหวะเวลาที่ดี', desc: 'กงล้อแห่งโชคชะตากำลังหมุนสู่ทิศทางบวก เรื่องที่ติดขัดกำลังจะคลี่คลาย โอกาสทองและข่าวดีกำลังเดินทางมาถึงคุณ', advice: 'ป้าเข็มชวนคิด: "ฟ้าหลังฝนย่อมสดใสเสมอ เตรียมตัวให้พร้อมรับโอกาสดีๆ ที่กำลังจะเข้ามาจ้า"', img: TAROT_CDN + 'RWS_Tarot_10_Wheel_of_Fortune.jpg', item: 'พวงกุญแจกงล้อโชคดี', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 11, name: 'Justice', thai: 'ใบที่ 11: ความยุติธรรม', keyword: 'ความถูกต้อง • ความสมดุล • ผลลัพธ์ที่เป็นธรรม', desc: 'ทุกอย่างจะเป็นไปตามความจริงและความยุติธรรม สัญญา ข้อตกลง หรือสิ่งที่รอคอยจะได้รับคำตอบที่โปร่งใสและตรงไปตรงมา', advice: 'ป้าเข็มชวนคิด: "ซื่อกินไม่หมด คดกินไม่นาน ยึดมั่นในความซื่อสัตย์แล้วผลดีจะตามมาแน่นอนจ้า"', img: TAROT_CDN + 'RWS_Tarot_11_Justice.jpg', item: 'สมุดบันทึกวางแผนงาน', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 12, name: 'The Hanged Man', thai: 'ใบที่ 12: คนห้อยหัว', keyword: 'การมองมุมกลับ • การปล่อยวาง • อดทนรอเวลา', desc: 'การหยุดนิ่งไม่ได้แปลว่าพ่ายแพ้ ลองมองปัญหาจากมุมใหม่ที่ต่างออกไป การยอมสละบางอย่างจะเปิดทางให้พบสิ่งที่มีค่ากว่า', advice: 'ป้าเข็มชวนคิด: "เมื่อเราเปลี่ยนมุมมอง ปัญหาก็จะเปลี่ยนเป็นบทเรียน ปล่อยวางเรื่องที่คุมไม่ได้นะลูก"', img: TAROT_CDN + 'RWS_Tarot_12_Hanged_Man.jpg', item: 'หมอนเพื่อสุขภาพคลายเครียด', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 13, name: 'Death', thai: 'ใบที่ 13: การสิ้นสุดเพื่อเกิดใหม่', keyword: 'การจบสิ่งเก่า • การเปลี่ยนแปลง • เริ่มต้นชีวิตใหม่', desc: 'การบอกลาสิ่งที่ไม่เหมาะกับเรา เพื่อเปิดพื้นที่ต้อนรับสิ่งที่ดีกว่าเข้ามา หมดเคราะห์หมดโศกเพื่อเริ่มต้นชีวิตใหม่อย่างสดใส', advice: 'ป้าเข็มชวนคิด: "อย่ากลัวการเปลี่ยนแปลง สิ่งเก่าจากไปเพื่อสิ่งที่ดีกว่าจะเข้ามาแทนที่เสมอลูก"', img: TAROT_CDN + 'RWS_Tarot_13_Death.jpg', item: 'กระจกแปดเหลี่ยมปรับฮวงจุ้ย', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 14, name: 'Temperance', thai: 'ใบที่ 14: การปรับสมดุล', keyword: 'ความพอดี • การประนีประนอม • การปรับตัว', desc: 'ชีวิตกำลังต้องการความสมดุล ไม่ตึงเกินไปและไม่หย่อนเกินไป ปรับจูนความคิดและการใช้ชีวิตให้กลมกลืน แล้วความราบรื่นจะกลับมา', advice: 'ป้าเข็มชวนคิด: "ทางสายกลางคือทางที่เบาสบายที่สุด ค่อยๆ ปรับ ค่อยๆ จูน แล้วทุกอย่างจะลงตัวจ้า"', img: TAROT_CDN + 'RWS_Tarot_14_Temperance.jpg', item: 'แก้วเก็บอุณหภูมิสร้างสมดุล', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 15, name: 'The Devil', thai: 'ใบที่ 15: ปีศาจ', keyword: 'กิเลส • ความยึดติด • การตื่นรู้', desc: 'ระวังกิเลสหรือสิ่งล่อใจที่ทำให้เราหลงทาง สำรวจพันธนาการในจิตใจ ความจริงคุณมีกุญแจปลดปล่อยตัวเองได้ทุกเมื่อ', advice: 'ป้าเข็มชวนคิด: "รู้ทันอารมณ์คือยอดปัญญา อะไรที่ทำให้ทุกข์ใจ วางลงได้ก็เบาได้ทันทีนะลูก"', img: TAROT_CDN + 'RWS_Tarot_15_Devil.jpg', item: 'น้ำหอมกลิ่นไม้หอมเสริมสติ', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 16, name: 'The Tower', thai: 'ใบที่ 16: หอคอยถล่ม', keyword: 'การตื่นรู้ • เรื่องกะทันหัน • สร้างฐานใหม่', desc: 'สิ่งที่พังทลายลงมาเป็นเพียงภาพลวงตา เพื่อเปิดโอกาสให้คุณสร้างรากฐานชีวิตใหม่ที่มั่นคงและแข็งแรงกว่าเดิมอย่างแท้จริง', advice: 'ป้าเข็มชวนคิด: "สิ่งที่ล้มได้ ย่อมสร้างใหม่ให้ดีกว่าเดิมได้ ขอเพียงใจเราไม่ยอมแพ้จ้า"', img: TAROT_CDN + 'RWS_Tarot_16_Tower.jpg', item: 'เคสโทรศัพท์กันกระแทกสายมู', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 17, name: 'The Star', thai: 'ใบที่ 17: ดวงดาว', keyword: 'ความหวัง • การฟื้นฟู • สมปรารถนา', desc: 'แสงสว่างแห่งความหวังกำลังส่องประกาย จิตใจที่เหนื่อยล้ากำลังได้รับการเยียวยา สิ่งที่คุณฝันและรอคอยกำลังเป็นจริง', advice: 'ป้าเข็มชวนคิด: "รักษาพลังใจให้สว่างไสวเหมือนดวงดาว สิ่งดีๆ กำลังทยอยเดินทางมาถึงคุณแล้วนะลูก"', img: TAROT_CDN + 'RWS_Tarot_17_Star.jpg', item: 'โคมไฟดวงดาวตั้งโต๊ะ', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 18, name: 'The Moon', thai: 'ใบที่ 18: พระจันทร์', keyword: 'ความกังวล • ภาพลวงตา • รอความชัดเจน', desc: 'อย่าเพิ่งด่วนตัดสินใจในวันที่หมอกลงหนา ความกังวลส่วนใหญ่มักเป็นภาพลวงตาที่จิตปรุงแต่งขึ้นมา รอให้แสงตะวันส่องสว่างแล้วค่อยก้าว', advice: 'ป้าเข็มชวนคิด: "หายใจเข้าลึกๆ ความกลัวจะหายไปเมื่อเรามองความจริงอย่างมีสติจ้า"', img: TAROT_CDN + 'RWS_Tarot_18_Moon.jpg', item: 'เทียนหอมอโรมาผ่อนคลาย', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 19, name: 'The Sun', thai: 'ใบที่ 19: พระอาทิตย์', keyword: 'ความสำเร็จสูงสุด • ชัยชนะ • พลังบวก', desc: 'ไพ่แห่งความสุขและความรุ่งโรจน์อันดับหนึ่งในชุดยิปซี! ความมืดมิดสิ้นสุดลงแล้ว มีแต่ความสำเร็จ สุขภาพแข็งแรง และโชคลาภ', advice: 'ป้าเข็มชวนคิด: "ยิ้มรับวันใหม่ด้วยความภาคภูมิใจ ความสำเร็จเป็นของคุณอย่างเต็มที่แล้วลูก!"', img: TAROT_CDN + 'RWS_Tarot_19_Sun.jpg', item: 'แว่นตากันแดดนำโชค', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 20, name: 'Judgement', thai: 'ใบที่ 20: การพิพากษา', keyword: 'โอกาสครั้งใหม่ • การตื่นรู้ • ผลลัพธ์ที่ดี', desc: 'เสียงแตรแห่งชีวิตใหม่ดังขึ้น คุณพร้อมก้าวข้ามอดีตและเกิดใหม่อีกครั้ง ผลงานและความดีที่คุณเคยสร้างไว้จะตอบแทนอย่างคุ้มค่า', advice: 'ป้าเข็มชวนคิด: "อดีตแก้ไขไม่ได้ แต่อนาคตสร้างใหม่ได้ด้วยการตัดสินใจในวันนี้ สู้เต็มที่นะลูก"', img: TAROT_CDN + 'RWS_Tarot_20_Judgement.jpg', item: 'นาฬิกาปลุกเสียงใสพลังบวก', link: 'https://s.shopee.co.th/2VqtxaXpj2' },
  { id: 21, name: 'The World', thai: 'ใบที่ 21: โลก', keyword: 'ความสมบูรณ์แบบ • ชัยชนะรอบด้าน • การบรรลุผล', desc: 'วงจรชีวิตปิดฉากลงอย่างสมบูรณ์แบบที่สุด ความสุข ความมั่งคั่ง และความสำเร็จที่คุณคู่ควรได้มาถึงแล้ว ชื่นชมกับผลงานได้เลย', advice: 'ป้าเข็มชวนคิด: "ยินดีด้วยอย่างยิ่งลูก เจ้าได้ทำหน้าที่ของตัวเองอย่างยอดเยี่ยมที่สุดแล้วจ้า"', img: TAROT_CDN + 'RWS_Tarot_21_World.jpg', item: 'กระเป๋าเดินทางมงคล', link: 'https://s.shopee.co.th/2VqtxaXpj2' }
];

function startShuffling() {
  document.getElementById('intro-stage').style.display = 'none';
  const pickStage = document.getElementById('pick-stage');
  pickStage.style.display = 'flex';
  
  const carousel = document.getElementById('carousel');
  carousel.innerHTML = '';
  const shuffled = [...TAROT_DATA].sort(() => 0.5 - Math.random());
  
  shuffled.forEach((card, idx) => {
    const slot = document.createElement('div');
    slot.className = 'tarot-slot';
    slot.innerHTML = `<span class="tarot-slot-num">${idx + 1}</span>`;
    slot.onclick = () => pickCard(card, slot);
    carousel.appendChild(slot);
  });
  
  setTimeout(() => { carousel.scrollLeft = 80; }, 100);
}

function pickCard(card, el) {
  el.classList.add('selected');
  setTimeout(() => {
    document.getElementById('pick-stage').style.display = 'none';
    const revealStage = document.getElementById('reveal-stage');
    revealStage.style.display = 'flex';
    
    document.getElementById('revealed-img').src = card.img;
    document.getElementById('r-name-en').innerText = card.name;
    document.getElementById('r-name-th').innerText = card.thai;
    document.getElementById('r-keyword').innerText = card.keyword;
    document.getElementById('r-desc').innerText = card.desc;
    document.getElementById('r-advice').innerText = card.advice;
    document.getElementById('item-name').innerText = card.item;
    document.getElementById('item-link').href = card.link;
    
    setTimeout(() => {
      document.getElementById('card3d').classList.add('flipped');
    }, 200);
  }, 400);
}

function resetDeck() {
  document.getElementById('card3d').classList.remove('flipped');
  document.getElementById('reveal-stage').style.display = 'none';
  document.getElementById('intro-stage').style.display = 'flex';
}

function shareReading() {
  if (navigator.share) {
    navigator.share({
      title: 'คำทำนายไพ่ยิปซีจิตวิทยา โดย ป้าเข็ม',
      text: `ฉันเพิ่งเปิดไพ่ยิปซีได้: ${document.getElementById('r-name-en').innerText} ✨ ลองมาเปิดดูดวงของคุณได้ที่นี่เลย!`,
      url: window.location.href
    }).catch(() => {});
  } else {
    navigator.clipboard.writeText(window.location.href);
    alert('คัดลอกลิงก์เรียบร้อย ส่งให้เพื่อนเปิดดูดวงได้เลยจ้า ✨');
  }
}
</script>
</body>
</html>"""



