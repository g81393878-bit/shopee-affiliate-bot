---
name: shopee-affiliate
description: Get real Shopee affiliate links (s.shopee.co.th/...) that earn commission, by automating the Shopee app on a USB-connected Android phone, then wire them into the Shopee Affiliate LINE bot backend. Use whenever the user needs affiliate links, wants products to earn commission, mentions Shopee Affiliate / ค่าคอม / ลิงก์ affiliate, needs to update the bot's product links, or asks why "ดึงข้อมูล Shopee ไม่ได้". Make sure to use this skill whenever Shopee affiliate links, commissions, or converting Shopee URLs come up — even if the user only says they want "links that pay commission".
---

# Shopee Affiliate Links via the Phone App

Goal: turn normal Shopee product URLs into **your own affiliate short links**
(`https://s.shopee.co.th/<code>`) that pay commission, and store them in the
Shopee Affiliate LINE bot database.

## Why this approach (read before deviating)

- **The web dashboard is blocked.** `affiliate.shopee.co.th` sits behind a
  traffic-verification wall ("เข้าสู่หน้าที่ต้องการไม่สำเร็จ") that rejects
  even a headed Chrome with valid session cookies (`is_logged_in=true` in the
  redirect URL but no captcha to solve). Do NOT burn time on the web.
- **Affiliate links cannot be scraped or guessed.** They are generated per
  account on Shopee's servers. The only sanctioned self-serve path is the
  phone app's **Convert Link (แปลงลิงก์)** feature: paste normal Shopee URLs
  (up to 5, one per line) → Convert → a popup shows your affiliate short links
  **as on-screen text**.
- **Android 10+ blocks reading the clipboard over adb** (`service call
  clipboard` returns "No items"). That is why we read the Convert Link popup
  text via uiautomator instead of tapping "คัดลอกลิงก์" and reading the
  clipboard — the popup text is far more reliable.
- A converted link is genuine when it redirects with `utm_source=an_<affiliate_id>`
  (this account: `an_15329550184`, affiliate "Anda" / boyyeerua).

## The tool

`tools/shopee_affiliate.py` in this repo automates everything:

```bash
python tools/shopee_affiliate.py convert "https://shopee.co.th/product/1/2" \
    "https://shopee.co.th/m/some-campaign/"          # up to 5 links
python tools/shopee_affiliate.py convert <url> --bot-api https://shopee-affiliate-bot-9e9n.onrender.com
python tools/shopee_affiliate.py update-bot <product_id> <affiliate_url> [--name ...] [--price ...]
python tools/shopee_affiliate.py search <ascii-keyword>
```

Flow inside `convert`: ensure phone on Convert Link screen (navigates
Me tab → scroll to โปรแกรม Affiliate → its Account tab (บัญชีผู้ใช้) →
แปลงลิงก์) → focus the big multiline field → clear (via the app's ลบทั้งหมด
button — long URLs exceed the old 200-DEL clear) → type each URL + Enter →
tap "แปลง" **while the keyboard is still open** → wait ~5 s → read the popup
links from the UI dump → dismiss popup (BACK) → print JSON. `convert` retries
up to 3 times and re-navigates on each attempt; one URL per invocation is
more reliable than batching several.

## Prerequisites

- Phone (this setup: Realme RMX3612, `HYPFZ54HRCQSBIBU`) plugged in with
  **USB debugging** enabled and authorized (`adb devices` shows `device`).
  Install adb: `winget install Google.PlatformTools` (lands in
  `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`).
- Shopee app (`com.shopee.th`) installed and logged into the Affiliate account.
- Run from Git Bash as `python tools/shopee_affiliate.py ...` — Python's
  subprocess uses arg lists, so the **MSYS path mangling never bites**.

## Hard-won lessons (each cost a debugging session)

1. **MSYS_NO_PATHCONV=1 on any native binary**: Git Bash rewrites `/foo` args
   to `C:/Program Files/Git/foo`. This broke Render's `--health-check-path /health`
   AND agent-browser's `cookies set ... --path /` ("Invalid cookie fields").
   Same class of bug — always guard path-like args.
2. **uiautomator dump "could not get idle state"**: the Shopee home screen has
   autoplay videos so the UI never idles. Retry the dump (it eventually lands
   on a static screen) and navigate to static pages (search results, product
   page, dialogs) before dumping. Animations also break it right after taps.
3. **adb cannot install APKs on Realme/ColorOS**: `adb install` fails with
   INSTALL_FAILED_VERIFICATION_FAILURE even via HeyTap's installer, and there
   is **no "Install via USB" toggle** in developer options. So DO NOT plan
   around ADBKeyboard — accept that Thai text can't be typed via adb
   (`input text` is ASCII-only). For Thai searches, the human types on the
   phone keyboard; URLs (the Convert Link input) are ASCII, so the tool types
   those itself.
4. **Don't fight the web anti-bot** (Shopee 403 `error 90309999`, traffic
   verification, SPA shells with no product data). The phone app is the
   supported client.
5. **Coordinates drift**: always re-dump and locate elements by text before
   tapping; bounds from an older dump go stale.
6. **The แปลง button only responds while the IME is open.** Tapping it with
   the keyboard closed (bottom of the sheet, y~2276) is silently ignored;
   tapping while the keyboard is up (y~1340) converts. Never `dump_ui`
   between typing and tapping — the dump takes 1-2 s, the IME settles, the
   layout shifts, and the tap lands on the "เพิ่ม Sub id" row instead.
7. **The "เพิ่ม Sub id" sheet is optional** (newer app build). It appears on
   the Convert Link screen ("ลิงก์จาก Shopee" + URL + "เพิ่ม Sub id" +
   "บันทึก" + info text + "แปลง"). Just ignore it and tap แปลง. If you
   accidentally open the sub-id entry ("Sub id 1", example
   `Electronics/FB/1212BigSale`), BACK out and retry — entering a sub-id is
   not required for converting.
8. **Navigation is: Me tab → โปรแกรม Affiliate (scroll — the Me page is
   long) → "บัญชีผู้ใช้" bottom tab → แปลงลิงก์.** Convert Link does NOT live
   on the main Me page. After a fresh app start a "ตั้งรหัสผ่าน" nudge popup
   may cover the Me page — dismiss it with "ไว้ทีหลัง". If the app drifts
   into an unknown screen (e.g. profile edit), `am force-stop` + relaunch
   and walk the path again.

## Finding real product URLs without scraping

Shopee's site blocks scraping, but **Google search works**: `site:shopee.co.th
<model> <keyword>` returns the product URLs directly, and each URL ends in
`-i.<shopid>.<itemid>` which you can also rewrite as
`https://shopee.co.th/product/<shopid>/<itemid>`. Feed those URLs to
`convert` — no need to browse the app for every product.

## Manual fallback (when the human prefers to tap)

App: Shopee → Me (ฉัน) → โปรแกรม Affiliate → search a product → open it →
"แชร์เพื่อสร้างรายได้" → "คัดลอกลิงก์" (copies your affiliate link). The link
starts with `s.shopee.co.th` — a long `shopee.co.th/product/...` URL means it
was copied from the regular product page, not the affiliate flow.

## MCP server (agent-callable)

`tools/mcp_server.py` wraps the tool as a FastMCP server (stdio). Install once:
`pip install -r tools/requirements-mcp.txt`. Client config:

```json
{ "mcpServers": { "shopee-affiliate": {
    "command": "python",
    "args": ["D:/Shopee_Web_Scraping/tools/mcp_server.py"] } } }
```

Tools: `shopee_status` (phone + bot health), `shopee_convert_links(urls)`,
`shopee_verify_link(short_url)` (checks `utm_source=an_15329550184`),
`shopee_update_product(product_id, affiliate_url, ...)`.

## Wiring into the LINE bot

The bot's products live in Supabase via `backend/app/api/products.py`
(PUT `/api/products/{id}` accepts `affiliate_url`). The LINE handler
`handle_today_deals` already renders `affiliate_url` in recommendations, so a
real link instantly makes the bot earn. Verify end-to-end by asking the bot
"วันนี้ขายอะไรดี" in LINE and checking the link opens with
`utm_source=an_15329550184`.
