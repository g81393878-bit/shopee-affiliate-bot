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
import re
import threading
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse

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


# ===========================================================================
# Pre-flight ความพร้อมก่อนโพสต์ + แจ้งเจ้าของ (coordination — อย่าโพสต์เงียบ ๆ)
# ===========================================================================
# - ก่อนยิงโพสต์ทุกครั้ง ให้ตรวจว่าพร้อมไหม (token ตั้ง/ใช้ได้, page id ครบ)
#   → ไม่พร้อม = ข้ามโพสต์ + แจ้งเจ้าของร้าน (throttle กันสแปม)
# - โพสต์ล้มด้วย error รุนแรง (OAuth หมดอายุ/สิทธิ์หาย/rate-limit) → แจ้งเจ้าของด้วย
# เฉพาะ production (postgres) ถึงบังคับ/แจ้งจริง — dev/test (sqlite) lenient
# เพราะ post_feed ถูก mock อยู่แล้ว (กันเทสต์ช้า/flaky + ยิง LINE จริงโดยไม่ตั้งใจ)

_TOKEN_VERIFY_INTERVAL = 3600       # ตรวจ token จริงผ่าน Graph API อย่างมาก 1 ครั้ง/ชม.
_OWNER_ALERT_INTERVAL = 6 * 3600    # แจ้งเจ้าของซ้ำเหตุผลเดิมอย่างมาก 1 ครั้ง/6 ชม.
_token_verified_at = 0.0
_token_ok: Optional[bool] = None
_owner_alert_at: dict = {}
_OWNER_ALERT_LOCK = threading.Lock()


# error รุนแรงที่เจ้าของต้องรู้ (token/สิทธิ์/rate-limit) — อย่างอื่น (ลิงก์ไม่ valid ฯลฯ) ไม่ต้องกวน
_HARD_POST_ERROR_MARKERS = (
    "oauth", "session has expired", "#(190)", "revoke", "permissions error", "#(200)",
    "rate limit", "too many calls", "user request limit reached",
    "page access has been removed", "app not installed", "invalid token",
)


def _is_prod() -> bool:
    """Production = ต่อ Postgres จริง (Render/Supabase) — sqlite = dev/test.
    (สัญญาณเดียวกับ facebook_radar._is_production — กันเทสต์/เครื่อง dev เข้าใจผิดว่าเป็น prod)"""
    db_url = (os.getenv("DATABASE_URL") or "").strip().lower()
    return db_url.startswith("postgres") or db_url.startswith("postgresql")


def verify_page_token(force: bool = False) -> Optional[bool]:
    """ตรวจว่า page token ยังใช้ได้ (GET /{page_id}?fields=id) — cache 1 ชม.

    คืน True=ใช้ได้ / False=ใช้ไม่ได้ชัดเจน (OAuth หมดอายุ/revoke) / None=ยังไม่รู้
    (transient — ถือว่า ok อย่าไปบล็อกโพสต์เพราะเน็ตสะดุด)
    dev/test (ไม่ใช่ prod) → คืน True เสมอ ไม่ยิง Graph API จริง (กันเทสต์ช้า/flaky)
    """
    if not _is_prod():
        return True
    global _token_verified_at, _token_ok
    now = time.time()
    if not force and _token_ok is not None and now - _token_verified_at < _TOKEN_VERIFY_INTERVAL:
        return _token_ok
    token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    if not token:
        _token_ok = False
        _token_verified_at = now
        return False
    try:
        r = httpx.get(f"{GRAPH_URL}/{PAGE_ID}",
                      params={"fields": "id", "access_token": token}, timeout=10)
        if r.status_code == 200:
            _token_ok = True
        else:
            msg = ""
            try:
                msg = ((r.json() or {}).get("error") or {}).get("message", "")
            except Exception:
                pass
            low = msg.lower()
            if "oauth" in low or "session has expired" in low or "revoke" in low \
                    or r.status_code == 400:
                _token_ok = False  # หมดอายุ/ถูก revoke ชัดเจน
            else:
                _token_ok = None  # error แปลก ๆ → ไม่ตัดสิน (fail-open)
    except Exception as e:
        logger.warning(f"[fb_preflight] verify token ล้ม (transient): {e}")
        _token_ok = None  # เน็ตสะดุด → ไม่บล็อกโพสต์
    _token_verified_at = now
    return _token_ok


def preflight_ready() -> tuple:
    """ตรวจความพร้อมก่อนโพสต์เพจ — คืน (ok: bool, reasons: list[str])

    ไม่พร้อม → caller ต้องข้ามโพสต์ + แจ้งเจ้าของ (notify_owner_once)
    dev/test (sqlite): ไม่มี token = ปกติ (post_feed ถูก mock) → ไม่บล็อก
    """
    reasons = []
    prod = _is_prod()
    token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    if not token:
        if prod:
            reasons.append("FACEBOOK_PAGE_ACCESS_TOKEN ไม่ได้ตั้ง — บอทจะโพสต์ไม่ได้")
    elif verify_page_token() is False:
        reasons.append("page token ใช้ไม่ได้ (หมดอายุ/ถูก revoke) — ต้อง refresh ใน Meta dashboard")
    page_id = (os.getenv("FACEBOOK_PAGE_ID") or "1307380735783361").strip()
    if not page_id:
        reasons.append("FACEBOOK_PAGE_ID ไม่ได้ตั้ง")
    return (not reasons, reasons)


def notify_owner_once(key: str, text: str) -> bool:
    """push LINE แจ้งเจ้าของร้าน (throttle: แจ้งซ้ำ key เดิมอย่างมาก 1 ครั้ง/6 ชม. กันสแปม)

    best-effort — dev/test หรือ push ล้ม ไม่พังโค้ด; คืน True ถ้าพยายามส่ง (หรือโดน throttle)
    หมายเหตุ: throttle เป็น in-memory (per-process) — Render restart จะรีเซ็ต
    """
    if not _is_prod():
        return False  # dev/test: ไม่ยิง LINE จริง
    now = time.time()
    with _OWNER_ALERT_LOCK:
        last = _owner_alert_at.get(key, 0.0)
        if now - last < _OWNER_ALERT_INTERVAL:
            return False  # เพิ่งแจ้งเหตุผลนี้ไป (throttle)
        _owner_alert_at[key] = now
    try:
        from linebot import LineBotApi
        from linebot.models import TextSendMessage
        from app.services.line_quota import push_guard
        from app.db import SessionLocal
        token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or ""
        if not token or "mock" in token.lower():
            return False
        admin_uid = (os.getenv("ADMIN_LINE_USER_ID")
                     or "Uc88eb3896b0e4bcc5fbaa9b78ac1294e").strip()
        db = SessionLocal()
        try:
            if not push_guard(db):
                logger.warning("[fb_owner_alert] ข้ามแจ้งเจ้าของ (LINE push quota หมด)")
                return False
        finally:
            db.close()
        LineBotApi(token).push_message(admin_uid, TextSendMessage(text=text[:1500]))
        return True
    except Exception as e:
        logger.warning(f"[fb_owner_alert] push ล้ม: {e}")
        return False


def classify_post_error(error: str) -> bool:
    """True = error รุนแรง (token หมดอายุ/สิทธิ์หาย/rate-limit) ควรแจ้งเจ้าของ — False = ปกติ/transient"""
    e = (error or "").lower()
    return any(m in e for m in _HARD_POST_ERROR_MARKERS)


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


def post_comment(post_id: str, message: str) -> dict:
    """โพสต์คอมเมนต์ลงโพสต์ของเพจ — POST /{post_id}/comments.
    คืนค่า {ok, comment_id, error}
    """
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or ""
    if not token:
        return {"ok": False, "comment_id": None, "error": "FACEBOOK_PAGE_ACCESS_TOKEN ไม่ได้ตั้ง"}
    if not post_id or not message:
        return {"ok": False, "comment_id": None, "error": "ต้องระบุ post_id และ message"}
    
    message = sanitize_post_text(message)
    endpoint = f"{GRAPH_URL}/{post_id}/comments"
    
    try:
        r = httpx.post(
            endpoint,
            params={"access_token": token},
            data={"message": message},
            timeout=30,
        )
    except Exception as e:
        logger.warning(f"[facebook_poster] comment failed: {e}")
        return {"ok": False, "comment_id": None, "error": str(e)[:200]}
        
    try:
        body = r.json()
    except Exception:
        body = {}
        
    cid = body.get("id")
    if r.status_code == 200 and cid:
        return {"ok": True, "comment_id": str(cid), "error": None}
    err = (body.get("error") or {}).get("message") or f"HTTP {r.status_code}"
    return {"ok": False, "comment_id": None, "error": str(err)[:200]}


def post_photo(message: str = "", file_path: str = "", image_url: str = "") -> dict:
    """โพสต์รูปภาพลงเพจ — POST /{page-id}/photos (รองรับไฟล์ในเครื่อง + URL)

    source เลือกอย่างใดอย่างหนึ่ง:
      file_path: ไฟล์รูปในเครื่อง (multipart upload source) — ใช้เฉพาะเครื่องที่มีไฟล์
      image_url: URL สาธารณะที่ Facebook ดาวน์โหลดได้เอง

    message: แคปชันใต้รูป (ไม่บังคับ) — กรองอักษรต่างภาษาก่อนส่ง
    คืน {ok, post_id, error} (ใช้ post_id เพราะลิงก์ตรงโพสต์ feed มากกว่า photo id)
    """
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or ""
    if not token:
        return {"ok": False, "post_id": None, "error": "FACEBOOK_PAGE_ACCESS_TOKEN ไม่ได้ตั้ง"}
    message = sanitize_post_text(message or "")
    file_path = (file_path or "").strip()
    image_url = (image_url or "").strip()
    if not file_path and not image_url:
        return {"ok": False, "post_id": None,
                "error": "ต้องมี file_path หรือ image_url อย่างใดอย่างหนึ่ง"}

    endpoint = f"{GRAPH_URL}/{PAGE_ID}/photos"
    data = {}
    if message:
        data["message"] = message

    files = None
    if file_path:
        if not os.path.exists(file_path):
            return {"ok": False, "post_id": None, "error": f"ไฟล์ไม่พบ: {file_path}"}
        ext = os.path.splitext(file_path)[1].lower().lstrip(".") or "png"
        mime = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
        }.get(ext, "image/png")
        with open(file_path, "rb") as fh:
            img_bytes = fh.read()
        files = {"source": (os.path.basename(file_path), img_bytes, mime)}
    else:
        data["url"] = image_url

    try:
        kwargs = {"params": {"access_token": token}, "data": data, "timeout": 60}
        if files:
            kwargs["files"] = files
        r = httpx.post(endpoint, **kwargs)
    except Exception as e:
        logger.warning(f"[facebook_poster] photo post failed: {e}")
        return {"ok": False, "post_id": None, "error": str(e)[:200]}
    try:
        body = r.json()
    except Exception:
        body = {}
    # /photos คืนทั้ง id (รูป) และ post_id (โพสต์ feed) — ใช้ post_id เพราะลิงก์ตรงโพสต์
    pid = body.get("post_id") or body.get("id")
    if r.status_code == 200 and pid:
        return {"ok": True, "post_id": str(pid), "error": None}
    err = (body.get("error") or {}).get("message") or f"HTTP {r.status_code}"
    return {"ok": False, "post_id": None, "error": str(err)[:200]}


# ===========================================================================
# กวาดลบโพสต์ลิงก์ปลอมบนเพจ (กันสคริปต์ mock โพสต์ลิงก์ปลอมขึ้นเพจ — เจอจริง 16-17/08)
# ===========================================================================

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SHOPEE_PREFIXES = ("https://s.shopee.co.th/", "http://s.shopee.co.th/")


def _decode_fb_redirect(url: str) -> str:
    """ถอดลิงก์ share preview ของ Facebook (l.facebook.com/l.php?u=...) ให้เป็น URL ปลายทางจริง
    (โพสต์ที่มีลิงก์ attachment จะเก็บ URL จริงไว้ในพารามิเตอร์ ?u= ซึ่ง URL-encode ไว้)"""
    try:
        if "l.facebook.com/l.php" in (url or ""):
            q = parse_qs(urlparse(url).query)
            if q.get("u"):
                return q["u"][0]
    except Exception:
        pass
    return url or ""


def _collect_attachment_urls(attachments) -> list:
    """เก็บทุก URL ในโครงสร้าง attachments (รวม subattachments) — กันพลาดลิงก์ที่ซ้อนลึก"""
    urls = []

    def walk(node):
        if isinstance(node, dict):
            for k in ("url", "unshimmed_url"):
                v = node.get(k)
                if isinstance(v, str) and v.startswith("http"):
                    urls.append(v)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(attachments or {})
    return urls


def extract_post_urls(message: str = "", attachments=None) -> list:
    """รวบ URL ทั้งหมดจากข้อความ + attachments ของโพสต์ (ถอด redirect l.php ด้วย)"""
    urls = _URL_RE.findall(message or "")
    urls += _collect_attachment_urls(attachments)
    return [_decode_fb_redirect(u).rstrip(")").rstrip(".") for u in urls]


def _normalize_shopee_link(url) -> str:
    """normalize ลิงก์สั้น Shopee ให้เป็น https://s.shopee.co.th/<code> (ตัด query/trailing) —
    ใช้เทียบกับ affiliate_url ในคลังสินค้า (รหัสสั้นเป็น base62 case-sensitive → ห้าม lowercase รหัส)"""
    s = (str(url or "").strip())
    low = s.lower()
    for p in _SHOPEE_PREFIXES:
        if low.startswith(p):
            code = s[len(p):].split("/")[0].split("?")[0].split("#")[0].strip()
            return f"https://s.shopee.co.th/{code}"
    return s


def is_fake_link_post(message: str = "", urls=None, known_links=None) -> bool:
    """True = โพสต์เป็นลิงก์ปลอม/ของ mock — ใช้กวาดลบโพสต์ปลอมบนเพจ

    สัญญาณ (conservative — ลบเฉพาะที่ชัดเจน):
    - shope.ee   = ลิงก์ปลอมเสมอ (กด 404)
    - lazada.co.th = แพลตฟอร์มอื่น (โฆษณาโปรโมต)
    - s.shopee.co.th ที่รหัสสั้น format ไม่ valid (มี _ / - / อักขระพิเศษ) = mock
    - s.shopee.co.th ที่ไม่ใช่ลิงก์ในคลังสินค้า (known_links) = mock
      (เช่น s.shopee.co.th/earbudsok — base62 ผ่าน format แต่ไม่ใช่ของจริงในคลัง)
    """
    text = (message or "").lower()
    if "shope.ee" in text or "lazada.co.th" in text:
        return True
    for u in (urls or []):
        lu = u.lower()
        if "shope.ee" in lu or "lazada.co.th" in lu:
            return True
        if "s.shopee.co.th" in lu:
            if not is_valid_shopee_affiliate_url(u):
                return True
            if known_links is not None and _normalize_shopee_link(u) not in known_links:
                return True
    return False


def fetch_page_posts(limit: int = 100) -> list:
    """ดึงโพสต์ล่าสุดของเพจ (เรียงใหม่ก่อน) — คืน [{id, message, created_time, permalink_url, urls}]
    (urls = ลิงก์ที่อยู่ในข้อความ + attachment ถอด redirect แล้ว)"""
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or ""
    if not token:
        return []
    url = f"{GRAPH_URL}/{PAGE_ID}/posts"
    params = {"fields": "id,message,created_time,attachments,permalink_url",
              "limit": 100, "access_token": token}
    out = []
    while url and len(out) < limit:
        try:
            r = httpx.get(url, params=params, timeout=20)
        except Exception as e:
            logger.warning(f"[facebook_poster] fetch posts failed: {e}")
            break
        if r.status_code != 200:
            logger.warning(f"[facebook_poster] fetch posts HTTP {r.status_code}")
            break
        body = r.json()
        for p in body.get("data", []):
            p["urls"] = extract_post_urls(p.get("message") or "", p.get("attachments"))
            out.append(p)
            if len(out) >= limit:
                break
        nxt = (body.get("paging") or {}).get("next")
        url = nxt if nxt else None
        params = None  # paging.next มี access_token ใน URL อยู่แล้ว
    return out


def delete_page_post(post_id: str) -> bool:
    """ลบโพสต์ออกจากเพจผ่าน Graph API DELETE /{post_id} — คืน True เมื่อสำเร็จ"""
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or ""
    if not token or not post_id:
        return False
    try:
        r = httpx.request("DELETE", f"{GRAPH_URL}/{post_id}",
                          params={"access_token": token}, timeout=20)
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"[facebook_poster] delete post failed {post_id}: {e}")
        return False


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
