---
name: facebook-app-config
description: >-
  Instructions for retrieving Facebook App ID & App Secret, and configuring basic settings
  (App Domains, Privacy/Terms URLs) on developers.facebook.com for server integrations.
---

# Facebook App Configuration

## Overview
This skill provides instructions on how to retrieve credentials and configure the basic settings for a Meta (Facebook) App to integrate it into backend servers or bots.

## Dependencies
None.

## Quick Start
To configure Facebook credentials for your project:
1. Go to your App Dashboard on the [Meta for Developers Basic Settings page](https://developers.facebook.com/apps/1263958805236203/settings/basic/).
2. Copy the **App ID** and retrieve the **App Secret**.
3. Save them to your server environment configuration (e.g., `.env`).
4. Configure App Domains and Privacy/Terms of Service URLs to enable Live Mode.
5. Configure the Webhook (`/api/webhooks/facebook`) with a Verify Token — the endpoint is already implemented in `backend/app/api/facebook_bot.py`.

## Workflow

### 1. Retrieve App Credentials
1. Go to the [Facebook Developer Settings Basic Page](https://developers.facebook.com/apps/1263958805236203/settings/basic/).
2. **App ID (หมายเลขแอป):** Locate the **App ID** field near the top. Copy this value. This will be used as `FACEBOOK_APP_ID`.
3. **App Secret (รหัสลับแอป):** Click the **Show (แสดง)** button next to the "App Secret" field. Enter your Facebook password when prompted to reveal the secret key. Copy this value. This will be used as `FACEBOOK_APP_SECRET`.

### 2. Configure Environment Variables
Add the retrieved credentials to your project's `.env` file or hosting environment variables (e.g. Render dashboard):
```env
FACEBOOK_APP_ID=1263958805236203
FACEBOOK_APP_SECRET=your_app_secret_here
FACEBOOK_VERIFY_TOKEN=your_custom_verify_token_here
FACEBOOK_PAGE_ACCESS_TOKEN=your_page_access_token_here
```
- `FACEBOOK_VERIFY_TOKEN` is a secret you make up yourself — it must match the **Verify Token** you enter in the Facebook App Webhook settings.
- `FACEBOOK_PAGE_ACCESS_TOKEN` comes from step 3 (Connect Page); it is used to reply to Messenger chats via the Send API.

### 3. Configure Server Domains
1. In the **App Domains (โดเมนของแอป)** field, add your backend's host domain.
   - For example, if hosted on Render: `shopee-affiliate-bot-9e9n.onrender.com`
   - Do not include `https://` or path suffixes in the App Domains field.

### 4. Provide Policy URLs for Live Mode
To transition the Facebook App status from **Development** to **Live**:
1. Fill in the **Privacy Policy URL (URL นโยบายความเป็นส่วนตัว)** field with a valid HTTPS link.
2. Fill in the **Terms of Service URL (URL ข้อตกลงการใช้บริการ)** field.
3. Save changes.
4. Toggle the App Status switch at the top from **Development** to **Live**.

### 5. Webhook Verification (already implemented)
The webhook endpoint is already implemented in this repo at `backend/app/api/facebook_bot.py` — no new code needed. It handles:

- `GET /api/webhooks/facebook` — answers Meta's verification handshake: if `hub.mode=subscribe` and `hub.verify_token` matches `FACEBOOK_VERIFY_TOKEN`, it returns `hub.challenge` as plain text (otherwise 403).
- `POST /api/webhooks/facebook` — verifies the `X-Hub-Signature-256` header (HMAC-SHA256 with `FACEBOOK_APP_SECRET`), then handles incoming `messaging` events.

```python
# backend/app/api/facebook_bot.py (excerpt — for reference only)
@router.get("/facebook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == FACEBOOK_VERIFY_TOKEN and challenge:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="webhook verify failed")
```

### 6. Webhook Registration
1. Deploy the server (the endpoint must be reachable over HTTPS).
2. In your Facebook App Dashboard, navigate to **Webhooks** or **Messenger > Settings**, and configure the webhook:
   - **Callback URL:** `https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/facebook` (or `https://<your_ngrok_subdomain>.ngrok-free.app/api/webhooks/facebook` for local testing)
   - **Verify Token:** the same value you set as `FACEBOOK_VERIFY_TOKEN` in `.env`
3. Click **Verify and Save** to initiate the handshake.
4. Subscribe the webhook to your Page (Messenger → Settings → Webhooks → Subscribe to Page events), then generate a **Page Access Token** by connecting the Page.

### 7. Fix / Verify Webhook via Graph API (no browser needed)
The webhook has **two layers** — both must be present or the bot stays silent:
1. **App-level callback URL:** `POST https://graph.facebook.com/{app_id}/subscriptions` with `object=page`, `callback_url`, `verify_token`, `fields=messages,messaging_postbacks,message_reads,message_deliveries`.
2. **Page subscription (Add Subscriptions):** `POST https://graph.facebook.com/{page_id}/subscribed_apps` with `subscribed_fields=messages,...`. A correct callback URL but empty `GET /{page_id}/subscribed_apps` (`{"data":[]}`) is the usual "bot silent" cause.

- Pre-flight the verify handshake before registering: `GET https://<host>/api/webhooks/facebook?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=test` must return `test` (200, plain text).
- Delete stale subscriptions with `DELETE https://graph.facebook.com/{app_id}/subscriptions` (e.g. leftover `object=user` pointing at another app).

## Common Mistakes
* **App Secret Hidden:** Forgetting to enter the Facebook account password to reveal the App Secret.
* **Incorrect Domain Format:** Writing `https://example.com/` instead of `example.com` in the **App Domains** field.
* **Invalid Privacy Policy URL:** Meta verifies that the Privacy Policy URL returns a `200 OK` HTTP status. Using a dead link or localhost URL will prevent switching the app to Live Mode.
* **Wrong endpoint path:** Using `/webhook` instead of the repo's actual path `/api/webhooks/facebook` — the verify handshake will fail.
* **Verify token mismatch:** Setting `FACEBOOK_VERIFY_TOKEN` in `.env` but entering a different value in the Facebook Webhook settings — Meta rejects the handshake with 403.
* **Two-layer subscription:** Setting only the callback URL but not subscribing the Page (Add Subscriptions) — the page webhook never fires and the bot is silent even with a valid callback.
* **`render.com` vs `onrender.com`:** The Render host is `shopee-affiliate-bot-9e9n.onrender.com` (with `on`). Typing `...render.com` makes Meta reject the Privacy URL (404) and blocks Live.
* **Live switch has no API:** Switching Development→Live can only be done in the browser. To confirm Live, have a **non-admin** (non-tester) account message the Page — webhook only fires for non-admins when the app is Live.
