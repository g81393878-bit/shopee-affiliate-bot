# -*- coding: utf-8 -*-
"""Facebook Page poster — โพสต์คอนเทนต์ลง feed เพจผ่าน Graph API (ไอเดีย B).

ต้องตั้ง env:
  - FACEBOOK_PAGE_ACCESS_TOKEN (page token)
    · โพสต์ข้อความ/รูป/ลิงก์: scope pages_manage_posts
    · โพสต์วิดีโอ: scope pages_manage_posts + pages_read_engagement + pages_show_list
  - FACEBOOK_PAGE_ID (default = เพจ "ป้าเข็ม ขายของ")

Graph API:
  - POST /{page-id}/feed — โพสต์ข้อความ (message) ลงหน้าเพจ
  - POST /{page-id}/photos — โพสต์รูป (image_url + caption)
  - POST /{page-id}/videos — โพสต์วิดีโอ MP4 (file_url หรือ multipart source)
"""
import logging
import os

import httpx

from app.services.link_checker import is_valid_shopee_affiliate_url
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
    link = (link or "").strip()
    if not message and not image_url and not background_preset_id:
        return {"ok": False, "post_id": None,
                "error": "ต้องมี message หรือ image_url อย่างใดอย่างหนึ่ง"}

    # ── Guard กันลิงก์ affiliate ปลอม/ของ mock หลุดขึ้นเพจ ─────────────────────
    # (เจอจริง 16/08: สคริปต์เทสต์โพสต์ 'หูฟังลิงก์จริง' ด้วย s.shopee.co.th/earbuds_ok
    #  + shope.ee รวม 24 ตัว — กันที่ post_feed เอง แม้ถูกเรียกจากสคริปต์ไหนก็ตาม)
    # - ลิงก์ที่ดูเหมือนลิงก์สั้น Shopee (s.shopee.co.th / shope.ee) → ต้องผ่าน format
    #   จริง (base62) เท่านั้น ไม่งั้น block ไม่ให้ยิงขึ้นเพจ
    # - ลิงก์อื่น (ข่าว/ท้องถิ่น/คอนเทนต์ curated) ผ่านได้ตามเดิม
    if link and ("s.shopee.co.th" in link.lower() or "shope.ee" in link.lower()):
        if not is_valid_shopee_affiliate_url(link):
            logger.warning(f"[facebook_poster] BLOCKED fake shopee link: {link[:80]}")
            return {"ok": False, "post_id": None,
                    "error": f"ลิงก์ Shopee ไม่ valid (ลิงก์ปลอม/ของ mock): {link[:80]}"}
    # shope.ee ในข้อความ = ลิงก์ปลอมเสมอ (Shopee จริงใช้ s.shopee.co.th) — กันแปะใน message
    if "shope.ee" in (message or "").lower():
        logger.warning("[facebook_poster] BLOCKED message containing fake shope.ee link")
        return {"ok": False, "post_id": None,
                "error": "ข้อความมีลิงก์ shope.ee (ปลอม) — ไม่อนุญาต"}

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


def post_video(description: str = "", file_url: str = "", file_path: str = "",
               title: str = "") -> dict:
    """โพสต์วิดีโอ (MP4) ลงเพจ Facebook — POST /{page-id}/videos

    ต้องเลือก source อย่างใดอย่างหนึ่ง:
      file_url: URL สาธารณะที่ Facebook ดาวน์โหลดได้เอง (ใช้ได้ทุกที่ incl. Render)
      file_path: ไฟล์ .mp4 บนเครื่อง (multipart upload source) — ใช้ได้เฉพาะเครื่องที่มีไฟล์

    description: แคปชันใต้คลิป (รองรับ emoji) — กรองอักษรต่างภาษาก่อนส่ง
    title: ชื่อวิดีโอ (ไม่บังคับ)

    Permission ที่ page token ต้องมี: pages_manage_posts + pages_read_engagement
    + pages_show_list (ถ้ามีแค่ pages_manage_posts จะได้ error 200 "Permissions error")

    คืน {ok, video_id, error}
    """
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or ""
    if not token:
        return {"ok": False, "video_id": None, "error": "FACEBOOK_PAGE_ACCESS_TOKEN ไม่ได้ตั้ง"}
    description = sanitize_post_text(description or "")
    file_url = (file_url or "").strip()
    file_path = (file_path or "").strip()
    if not file_url and not file_path:
        return {"ok": False, "video_id": None,
                "error": "ต้องมี file_url หรือ file_path อย่างใดอย่างหนึ่ง"}

    endpoint = f"{GRAPH_URL}/{PAGE_ID}/videos"
    data = {"published": "true"}  # string ตัวเล็ก — Graph API ต้องการ true/false
    if description:
        data["description"] = description
    if (title or "").strip():
        data["title"] = (title or "").strip()

    files = None
    if file_path:
        if not os.path.exists(file_path):
            return {"ok": False, "video_id": None, "error": f"ไฟล์ไม่พบ: {file_path}"}
        with open(file_path, "rb") as fh:
            video_bytes = fh.read()
        files = {"source": (os.path.basename(file_path), video_bytes, "video/mp4")}
    else:
        # Facebook ดาวน์โหลดเองจาก URL สาธารณะ — ใช้ได้จาก Render/local (ไฟล์ไม่ต้องอยู่เครื่องนี้)
        data["file_url"] = file_url

    try:
        kwargs = {"params": {"access_token": token}, "data": data, "timeout": 120}
        if files:
            kwargs["files"] = files
        r = httpx.post(endpoint, **kwargs)
    except Exception as e:
        logger.warning(f"[facebook_poster] video post failed: {e}")
        return {"ok": False, "video_id": None, "error": str(e)[:200]}
    try:
        body = r.json()
    except Exception:
        body = {}
    vid = body.get("id") or body.get("video_id")
    if r.status_code == 200 and vid:
        return {"ok": True, "video_id": str(vid), "error": None}
    err = (body.get("error") or {}).get("message") or f"HTTP {r.status_code}"
    return {"ok": False, "video_id": None, "error": str(err)[:200]}
