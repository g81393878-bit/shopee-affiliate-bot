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
```

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

## Common Mistakes
* **App Secret Hidden:** Forgetting to enter the Facebook account password to reveal the App Secret.
* **Incorrect Domain Format:** Writing `https://example.com/` instead of `example.com` in the **App Domains** field.
* **Invalid Privacy Policy URL:** Meta verifies that the Privacy Policy URL returns a `200 OK` HTTP status. Using a dead link or localhost URL will prevent switching the app to Live Mode.
