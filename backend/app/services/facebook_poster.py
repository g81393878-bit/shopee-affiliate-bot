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

from app.services.text_cleaner import sanitize_post_text

logger = logging.getLogger(__name__)

PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "1307380735783361")
GRAPH_URL = "https://graph.facebook.com/v21.0"

# เขียนโพสต์ลง Google ชีทอัตโนมัติ (ผ่าน Apps Script Web App — ดู tools/sheet_posts_apps_script.gs)
# ตั้ง env POSTS_SHEET_WEBHOOK_URL = URL web app ที่ deploy — ไม่ตั้ง = ไม่บันทึก (โค้ดทำงานปกติ)


def _push_post_to_sheet(row: dict) -> None:
    """push 1 แถวโพสต์ไป Google ชีท — fire-and-forget (background) กันไม่หน่วงการโพสต์
    Apps Script web app ตอบ 302 (redirect ไป script.googleusercontent.com/macros/echo)
    — ต้อง follow_redirects=True (httpx ปิดไว้โดยค่าเริ่มต้น ไม่งั้นแถวไม่ถึงชีท)
    (อ่าน env ตอนเรียก ไม่ใช่ตอน import — ทดสอบได้ + เปลี่ยนได้โดยไม่ต้อง restart)"""
    url = os.getenv("POSTS_SHEET_WEBHOOK_URL", "")
    if not url:
        return
    try:
        httpx.post(url, json=row, timeout=5, follow_redirects=True)
    except Exception as e:
        logger.debug(f"posts sheet push failed: {e}")


def log_post_async(row: dict) -> None:
    """บันทึกโพสต์ลง Google ชีท (daemon thread) — ตอบ/โพสต์ทันที ไม่รอ Google"""
    try:
        import threading
        threading.Thread(target=_push_post_to_sheet, args=(row,), daemon=True).start()
    except Exception:
        pass


def post_feed(message: str, link: str = "", image_url: str = "",
              background_preset_id: str = "") -> dict:
    """โพสต์ลง feed เพจ — คืน {ok, post_id, error}

    link: ถ้าระบุ Facebook จะดึง preview (รูปสินค้า + ชื่อ) จากหน้าเว็บปลายทางอัตโนมัติ
    image_url: ถ้าระบุ จะโพสต์รูปนั้น (URL สาธารณะที่ Facebook เข้าถึงได้) พร้อม message
      เป็น caption ผ่าน POST /{page-id}/photos — ใช้กับรูปมาสคอต/ภาพนิ่งที่ไม่ได้มาจาก link
      (ถ้ามี image_url จะใช้ endpoint /photos และไม่ส่ง link — Facebook เลือก media อย่างเดียว)
    background_preset_id: ถ้าระบุ จะโพสต์ข้อความล้วนบนพื้นสี (text_format_preset_id
      พารามิเตอร์ไม่เป็นทางการของ Graph API) — ใช้กับโพสต์สั้น ≤ 130 ตัวอักษร
      ข้อจำกัดของ Facebook: ห้ามมี media/link (มีแล้วพื้นสีจะถูก ignore) → ถ้าส่งค่านี้
      จะไม่แนบ link และ image_url ด้วย
    """
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or ""
    if not token:
        return {"ok": False, "post_id": None, "error": "FACEBOOK_PAGE_ACCESS_TOKEN ไม่ได้ตั้ง"}
    # กรองอักษรต่างภาษาที่ LLM หลุด (เปอร์เซีย/ซีริลลิก/CJK...) ก่อนโพสต์ขึ้นเพจ
    message = sanitize_post_text(message or "")
    image_url = (image_url or "").strip()
    background_preset_id = (background_preset_id or "").strip()
    if not message and not image_url and not background_preset_id:
        return {"ok": False, "post_id": None,
                "error": "ต้องมี message หรือ image_url อย่างใดอย่างหนึ่ง"}

    if background_preset_id:
        # พื้นสี (text-only): Facebook กำหนดให้โพสต์ข้อความล้วน (ไม่มี media/link)
        # และข้อความ ≤ 130 ตัวอักษร — เกินจะถูก 400 ปฏิเสธ
        endpoint = f"{GRAPH_URL}/{PAGE_ID}/feed"
        data = {"message": (message or "").strip(),
                "text_format_preset_id": background_preset_id}
    elif image_url:
        # โพสต์รูป: url ต้องเป็นลิงก์สาธารณะ (Facebook ดาวน์โหลดเอง); message = caption (ไม่บังคับ)
        endpoint = f"{GRAPH_URL}/{PAGE_ID}/photos"
        data = {"url": image_url}
        if (message or "").strip():
            data["message"] = (message or "").strip()
    else:
        endpoint = f"{GRAPH_URL}/{PAGE_ID}/feed"
        data = {"message": message}
        if link:
            data["link"] = link

    try:
        r = httpx.post(
            endpoint,
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
    # /photos คืนทั้ง id (รูป) และ post_id (โพสต์ feed) — ใช้ post_id เพราะลิงก์ตรงโพสต์มากกว่า
    pid = body.get("post_id") or body.get("id")
    if r.status_code == 200 and pid:
        return {"ok": True, "post_id": pid, "error": None}
    err = (body.get("error") or {}).get("message") or f"HTTP {r.status_code}"
    return {"ok": False, "post_id": None, "error": str(err)[:200]}
