# -*- coding: utf-8 -*-
"""Facebook Page poster — โพสต์คอนเทนต์ลง feed เพจผ่าน Graph API (ไอเดีย B).

ต้องตั้ง env:
  - FACEBOOK_PAGE_ACCESS_TOKEN (page token — ต้องมี scope pages_manage_posts)
  - FACEBOOK_PAGE_ID (default = เพจ "ป้าเข็ม ขายของ")

Graph API: POST /{page-id}/feed — โพสต์ข้อความ (message) ลงหน้าเพจ
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "1307380735783361")
GRAPH_URL = "https://graph.facebook.com/v21.0"


def post_feed(message: str, link: str = "") -> dict:
    """โพสต์ลง feed เพจ — คืน {ok, post_id, error}

    link: ถ้าระบุ Facebook จะดึง preview (รูปสินค้า + ชื่อ) จากหน้าเว็บปลายทางอัตโนมัติ
    """
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or ""
    if not token:
        return {"ok": False, "post_id": None, "error": "FACEBOOK_PAGE_ACCESS_TOKEN ไม่ได้ตั้ง"}
    if not (message or "").strip():
        return {"ok": False, "post_id": None, "error": "message ว่าง"}
    data = {"message": message}
    if link:
        data["link"] = link
    try:
        r = httpx.post(
            f"{GRAPH_URL}/{PAGE_ID}/feed",
            params={"access_token": token},
            data=data,
            timeout=20,
        )
    except Exception as e:
        logger.warning(f"[facebook_poster] post failed: {e}")
        return {"ok": False, "post_id": None, "error": str(e)[:200]}
    try:
        body = r.json()
    except Exception:
        body = {}
    if r.status_code == 200 and body.get("id"):
        return {"ok": True, "post_id": body["id"], "error": None}
    err = (body.get("error") or {}).get("message") or f"HTTP {r.status_code}"
    return {"ok": False, "post_id": None, "error": str(err)[:200]}
