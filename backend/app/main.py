from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import engine, Base
from app.api import users, products, performance, line_bot
from app.config import settings

# Create database tables on startup (especially helpful for SQLite/Supabase development)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Affiliate Marketing Automation Platform API",
    description="Backend API for managing Shopee products, generating AI content scripts, and LINE bot services.",
    version="1.0.0"
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
