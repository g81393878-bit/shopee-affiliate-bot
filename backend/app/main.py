import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.db import engine, Base
from app.api import users, products, performance, line_bot, cron
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
app.include_router(cron.router, prefix="/api")

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
