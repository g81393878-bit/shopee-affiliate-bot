---
name: render-supabase-deploy
description: |
  Deploy a FastAPI backend to Render.com with Supabase PostgreSQL as the database.
  Use this skill when the user wants a permanent, free, always-on hosting solution
  for a Python/FastAPI backend that connects to a LINE Bot webhook or similar service.
  Covers all common technical pitfalls discovered during real deployment.
---

# Render + Supabase Deployment Skill

## Overview

This skill deploys a **FastAPI** backend to **Render.com** (free hosting) with **Supabase** (free PostgreSQL database), providing a permanent public URL suitable for LINE Bot webhooks or any webhook-based integration.

**Why this stack?**
- ✅ Permanent URL — no need for localtunnel/ngrok that changes on every restart
- ✅ No terminal needs to be kept open
- ✅ 100% free tier available
- ✅ Auto-deploy from GitHub on every push
- ✅ Existing FastAPI code works without major rewrites

---

## Required Files

### 1. `requirements.txt`
Ensure these packages are included:
```
fastapi
uvicorn[standard]
sqlmodel
sqlalchemy
psycopg2-binary
python-dotenv
line-bot-sdk
google-generativeai
httpx
```

> ⚠️ Use `psycopg2-binary` (not `psycopg2`) for Render compatibility.

### 2. `render.yaml` (place at project root)
```yaml
services:
  - type: web
    name: shopee-affiliate-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: LINE_CHANNEL_ACCESS_TOKEN
        sync: false
      - key: LINE_CHANNEL_SECRET
        sync: false
      - key: GEMINI_API_KEY
        sync: false
```

> ⚠️ `sync: false` means the value must be set manually in the Render dashboard (never commit secrets to GitHub).

### 3. `database.py` — PostgreSQL with auto-fix
```python
import os
from sqlmodel import create_engine, SQLModel, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./affiliate_db.db")

# CRITICAL: SQLAlchemy v2 rejects "postgres://" — must be "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
```

---

## Step-by-Step Deployment

### Step 1: Set Up Supabase Database
1. Go to [supabase.com](https://supabase.com) → Create new project
2. Navigate to **Settings → Database → Connection Pooling**
3. Copy the **Transaction Pooler** connection string (NOT Direct Connection)
   - URL format: `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`
4. Keep this URL — it will be set as `DATABASE_URL` in Render

### Step 2: Push Code to GitHub
1. Ensure `render.yaml` is at the repository root
2. Add `.env` to `.gitignore` to avoid leaking secrets
3. Push all code to GitHub

### Step 3: Deploy on Render
1. Go to [render.com](https://render.com) → New → Web Service
2. Connect your GitHub repository
3. Render will auto-detect `render.yaml`
4. Under **Environment Variables**, add:
   - `DATABASE_URL` = Supabase Pooler URL (from Step 1)
   - `LINE_CHANNEL_ACCESS_TOKEN` = from LINE Developers Console
   - `LINE_CHANNEL_SECRET` = from LINE Developers Console
   - `GEMINI_API_KEY` = from Google AI Studio
5. Click **Deploy**
6. Copy the permanent URL: `https://your-service-name.onrender.com`

### Step 4: Update LINE Webhook
1. Go to LINE Developers Console → Messaging API
2. Set Webhook URL to: `https://your-service-name.onrender.com/api/webhooks/line`
3. Verify the webhook

> ⚠️ Use the plural path `/api/webhooks/line` — the old walkthrough's `/api/webhook` (singular) breaks LINE webhook verification. **No Cloudflare Worker is used anymore**: the webhook points straight at Render. A worker in the middle is a silent failure point — a stale `FASTAPI_URL` (e.g. a dead `loca.lt` tunnel) drops every LINE event while still answering 200 to LINE.

---

## Common Pitfalls & Fixes

### ❌ Pitfall 1: IPv6 Blocking (Most Common)
**Error**: `OperationalError: Tenant or user not found`  
**Cause**: Supabase Direct Connection uses IPv6; Render runs on IPv4-only  
**Fix**: Always use **Connection Pooler URL** from Supabase (port 5432 or 6543), never the Direct Connection URL

### ❌ Pitfall 2: SQLAlchemy URL Format
**Error**: `Could not parse rfc1738 URL from string 'postgres://...'`  
**Cause**: SQLAlchemy v2 requires `postgresql://` not `postgres://`  
**Fix**: Add the auto-replace snippet in `database.py` (shown above)

### ❌ Pitfall 3: Hardcoded PORT
**Error**: Render returns 502 Bad Gateway immediately after deploy  
**Cause**: Hardcoded `--port 8000` conflicts with Render's dynamic port assignment  
**Fix**: Use `--port $PORT` in `startCommand` in `render.yaml`

### ❌ Pitfall 4: Cold Start (Free Tier)
**Symptom**: LINE Bot takes 30–60 seconds to respond after idle period  
**Cause**: Render Free Tier shuts down the service after 15 minutes of no traffic  
**Fix**: Use [cron-job.org](https://cron-job.org/) (free) to ping `https://your-service.onrender.com/health` every 10 minutes

Add a health endpoint in `main.py`:
```python
@app.get("/health")
def health_check():
    return {"status": "ok"}
```

---

## Architecture After Deployment

```
LINE User
    ↓
LINE Platform
    ↓
Render.com FastAPI (permanent URL, always on)
    ↓
Supabase PostgreSQL (cloud database)
    + Google Gemini AI
```

---

## Environment Variables Reference

| Variable | Where to Get |
|----------|-------------|
| `DATABASE_URL` | Supabase → Settings → Database → Connection Pooling → Transaction Pooler |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Developers → Messaging API → Channel Access Token |
| `LINE_CHANNEL_SECRET` | LINE Developers → Messaging API → Channel Secret |
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API Key |
