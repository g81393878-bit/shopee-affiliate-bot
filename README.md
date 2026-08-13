# 🤖 ป้าเข็ม ขายของ — AI Shopee Affiliate LINE Bot

An AI-powered LINE Official Account bot that searches Shopee affiliate products, generates content scripts, compares products, and re-engages customers — all through natural Thai conversation.

Built with **FastAPI**, deployed on **Render**, backed by **Supabase PostgreSQL** and **Groq/Gemini LLMs**.

---

## ✨ Features

- 🔎 **Product search & recommendation** — natural-language search with Thai price conditions ("หูฟังไม่เกิน 300", "กระติก 200-400")
- ⚖️ **Product comparison** — "เทียบ A กับ B" returns a side-by-side card (price / sales / specs) with mismatch warnings
- ⭐ **"ขายดีวันนี้"** — rotating daily picks, ranked by AI score, day-of-year rotation so it never repeats
- 🧠 **Account memory** — "จำไว้ ชอบหูฟัง" stores the customer's category preferences and tailors future alerts (Amazon-style memory)
- 🔻 **Price-drop alerts** — cron job detects price drops (≥5%) and notifies interested customers
- 🔔 **Re-engagement** — pushes new arrivals in a category to customers silent for ≥7 days (rate-limited)
- 🛡️ **Link policy enforcement** — only products with `link_status == "ok"` (verified affiliate links) ever reach a customer
- 📊 **Admin dashboard** — password-protected web UI at `/admin` + JSON API at `/api/admin/*`
- ⏰ **Cron jobs** — link checking, AI analysis, price refresh, daily report, re-engagement
- 🔒 **PDPA compliance** — 90-day chat retention, "ลบข้อมูลฉัน" deletes all user data instantly, `/privacy` policy page
- 🩺 **Always-on** — `/health` endpoint + self keep-alive loop keep Render's free tier awake

---

## 🏗 Architecture

```
LINE User
   ↓
LINE Messaging API
   ↓
Render (FastAPI)  ← /api/webhooks/line
   ↓
Supabase PostgreSQL
   ↓
Groq / Gemini LLM   (content generation)
```

Only the LINE webhook URL (`POST /api/webhooks/line`) points at Render directly — no middle proxy.

---

## 💬 LINE Commands

| Command | What it does |
|---|---|
| `หูฟัง` / `กระติกน้ำ` | Search products by name |
| `หูฟังไม่เกิน 300` | Search with a price cap |
| `กระติก 200-400` | Search with a price range |
| `เทียบ A กับ B` | Side-by-side product comparison |
| `วันนี้ขายอะไรดี` | Today's recommended picks |
| `อันดับขายดี` | Top sellers |
| `จำไว้ ชอบหูฟัง` | Remember a category preference |
| `มีอะไรใหม่` | New arrivals in your preferred category |
| `สั่งแล้ว` / `เลขพัสดุ` | How to track an order on Shopee |
| `ลบข้อมูลฉัน` | Delete all personal data (PDPA) |
| `คุยกับป้าเข็ม` | Bot manual / FAQ |

---

## 📁 Project Structure

```
backend/
  app/
    main.py            # FastAPI app, keep-alive loop, /health, /privacy
    config.py          # env settings (dotenv)
    db.py              # SQLAlchemy engine (auto-fixes postgres:// → postgresql://)
    models.py          # SQLAlchemy models
    api/               # routers: line_bot, products, users, cron, admin_dashboard, performance
    services/          # link_checker, llm_clients, product_cards, shopee_api, ai_*, category, ...
    static/admin.html  # admin dashboard (single-file vanilla JS, no build step)
  requirements.txt
tools/                 # scripts: cron_jobs, product_pipeline, export_content_csv, mcp_server, ...
dashboard/             # React/Vite admin frontend (experimental)
render.yaml            # Render deployment config
```

---

## 🚀 Getting Started (local dev)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# create backend/.env (see Environment Variables)
cp .env.example .env             # if available, or create manually

uvicorn app.main:app --reload
```

Without env vars, the app boots in mock mode (bot won't work for real) — set real credentials before deploying.

---

## 🔐 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | Supabase transaction-pooler URL (port 6543), e.g. `postgresql://...pooler.supabase.com:6543/postgres` |
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE Messaging API channel access token |
| `LINE_CHANNEL_SECRET` | ✅ | LINE channel secret |
| `GROQ_API_KEY` | ✅ | Groq API key (comma-separate multiple for round-robin failover) |
| `GROQ_MODEL` | | Model override (default `llama-3.3-70b-versatile`) |
| `LLM_PROVIDER` | | `gemini` \| `openai` \| `groq` (default `groq` in production) |
| `GEMINI_API_KEY` | | For `LLM_PROVIDER=gemini` |
| `CRON_TOKEN` | | Locks `/api/cron/*` endpoints (call with `?token=...`) |
| `ADMIN_DASHBOARD_PASSWORD` | | `/admin` password (falls back to `CRON_TOKEN`; unset both → dashboard off) |
| `ADMIN_LINE_USER_ID` | | Owner's LINE ID (sees commission/score on product cards) |
| `MIN_SALES` | | Minimum sales for a product to reach customers (default `2000`) |
| `PRICE_DROP_PCT` | | Price-drop alert threshold % (default `5`) |
| `RENDER_EXTERNAL_URL` | | Auto-set by Render; powers the self keep-alive loop |
| `KEEP_ALIVE_INTERVAL` | | Keep-alive seconds (default `600`) |
| `SHEET_WEBHOOK_URL` | | Optional Google Apps Script webhook to log chats to a sheet |

---

## ☁️ Deployment (Render + Supabase)

1. Create a **Supabase** project → Settings → Database → copy the **Transaction pooler** URL (never the Direct Connection — Render is IPv4-only).
2. Push this repo to GitHub. `render.yaml` is auto-detected by Render (note `rootDir: backend`).
3. In Render, set the `sync: false` env vars above in the dashboard (secrets are **never** committed).
4. Point the LINE webhook URL at `https://<your-service>.onrender.com/api/webhooks/line`.
5. Set up [cron-job.org](https://cron-job.org) to ping `/health` every 10 min (or rely on the built-in self keep-alive loop).

Full walkthrough: `.agents/skills/render-supabase-deploy/SKILL.md`

---

## ⏰ Cron Jobs

`POST /api/cron/*` (locked by `CRON_TOKEN`):

| Endpoint | Purpose |
|---|---|
| `check-links` | Verify affiliate links, mark dead/suspect (`--delete` removes dead) |
| `analyze` | AI-analyze new products |
| `refresh-prices` | Refresh prices, record history, alert price drops |
| `daily-report` | Daily morning report |
| `re-engage` | Notify silent customers of new arrivals |

Register them on cron-job.org automatically with `python tools/cron_jobs.py`.

---

## 🛠 Tools

| Script | Purpose |
|---|---|
| `tools/cron_jobs.py` | Idempotently register all cron jobs on cron-job.org |
| `tools/product_pipeline.py` | Import/refresh products from CSV (validates links before insert) |
| `tools/export_content_csv.py` | Export generated content |
| `tools/sheet_apps_script.gs` | Google Apps Script webhook for chat logging |
| `tools/mcp_server.py` | MCP server exposing product/catalog tools |
| `deploy_to_github.ps1` | One-click GitHub push helper |

---

## 🔒 Privacy (PDPA)

- Stores only LINE name + ID (`users`) and chat text/type (`chat_logs`, auto-pruned to 90 days).
- "ลบข้อมูลฉัน" deletes the user, logs, and preferences immediately (the command itself is not logged).
- See the live policy at `/privacy`.

---

## 📜 License

Custom license — see [LICENSE](LICENSE).

Free for personal, educational, and non-commercial use. Commercial use or resale requires prior written permission from the owner.
