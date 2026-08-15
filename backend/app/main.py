import asyncio
import logging
import os
from contextlib import asynccontextmanager

# default root level = WARNING ทำให้ INFO log ของ app (เช่น keep-alive ping) ถูกกลืนไม่ขึ้น Render log
logging.basicConfig(level=logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)  # กัน BEGIN/COMMIT รกทุก query

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import httpx

from app.db import engine, Base
from app.api import users, products, performance, line_bot, cron, admin_dashboard, facebook_bot
from app.config import settings

logger = logging.getLogger(__name__)

# Create database tables on startup (especially helpful for SQLite/Supabase development)
Base.metadata.create_all(bind=engine)

KEEP_ALIVE_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
KEEP_ALIVE_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "600"))


async def keep_alive_loop():
    """กัน Render free tier หลับ: ping ตัวเองทุก 10 นาที
    ไม่พึ่ง cron-job.org เพียงอย่างเดียว — ถ้า external ping หยุด บอทก็ยังตื่นอยู่
    (Render ตั้ง RENDER_EXTERNAL_URL ให้อัตโนมัติ = URL สาธารณะของ service)"""
    if not KEEP_ALIVE_URL:
        logger.warning("RENDER_EXTERNAL_URL not set — keep-alive loop disabled (dev)")
        return
    while True:
        await asyncio.sleep(KEEP_ALIVE_INTERVAL)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{KEEP_ALIVE_URL}/health")
                logger.info(f"keep-alive ping {KEEP_ALIVE_URL}/health -> {r.status_code}")
        except Exception as e:
            logger.warning(f"keep-alive ping failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(keep_alive_loop())
    yield
    task.cancel()


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
app.include_router(facebook_bot.router, prefix="/api")
app.include_router(cron.router, prefix="/api")
app.include_router(admin_dashboard.router)  # แดชบอร์ดแอดมิน (/admin + /api/admin/*)

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
