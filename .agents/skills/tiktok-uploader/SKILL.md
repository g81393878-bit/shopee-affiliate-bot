---
name: tiktok-uploader
description: TikTok video automation system: Playwright Web Studio uploader (tools/tiktok_studio_uploader.py), Content Posting API v2 (tools/tiktok_uploader.py), cookie session management, and multi-platform broadcast in reels_uploader/uploader.py. Use whenever the user mentions TikTok, ติ๊กต๊อก, @healthgooddeals, tiktok_studio_uploader, or TikTok posting errors.
---

# TikTok Uploader Skill

คู่มือการทำงานกับระบบอัปโหลดวิดีโอ TikTok อัตโนมัติ

## 1. Core Modules

- **Primary Web Studio Uploader**: `tools/tiktok_studio_uploader.py`
  - Uses Playwright persistent browser context (`tools/tiktok_user_data/` and `tools/tiktok_cookies.json`).
  - Navigates to `https://www.tiktok.com/tiktokstudio/upload`.
  - Sets input files, handles joyride overlay dismissal, types sanitized caption, clicks exact Post button (`button:text-is("Post")` / regex `^(Post|โพสต์|Publish)$`).
- **Cookie Import Tool**: `tools/import_tiktok_cookies.py`
  - Ingests raw HTTP cookie strings and translates them to Playwright cookie format.
- **Direct API Uploader**: `tools/tiktok_uploader.py`
  - Uses TikTok Content Posting API v2 (OAuth 2.0 PKCE, token refresh, chunked upload).
- **Multi-Broadcast Integration**: `reels_uploader/uploader.py`
  - Calls `tiktok_uploader` (API) or `tiktok_studio_uploader` (Web Studio) automatically in `post_next()`.

## 2. Common CLI Commands

```bash
# Upload a single video via Web Studio
backend\.venv\Scripts\python tools/tiktok_studio_uploader.py --upload "reels_uploader/pending_videos/<video_name>.mp4" --caption "รีวิว #ป้าเข็มรีวิว #ของดีบอกต่อ"

# Login & save cookies
backend\.venv\Scripts\python tools/tiktok_studio_uploader.py --login

# Import cookies from raw string
backend\.venv\Scripts\python tools/import_tiktok_cookies.py
```

## 3. Important Rules & Gotchas

1. **Selector Disambiguation**:
   - Never use `page.locator('button:has-text("Post")')` because it matches the navigation link `"Posts"` on TikTok Studio!
   - Always use `page.locator('button').filter(has_text=re.compile(r'^(Post|โพสต์|Publish)$')).first` or `button:text-is("Post")`.
2. **Overlay / Joyride Dismissal**:
   - TikTok shows onboarding overlays `#react-joyride-portal, .react-joyride__overlay`. Always remove or dismiss them before clicking form elements.
3. **No-Price Compliance**:
   - All captions must pass through `sanitize_caption()`, stripping prices and appending `#ป้าเข็มรีวิว #ของดีบอกต่อ`.
4. **Git Safety**:
   - Never commit `tiktok_cookies*.json`, `tiktok_user_data/`, or `tiktok_token*.json`.
