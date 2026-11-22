# -*- coding: utf-8 -*-



"""



tools/fb_comment_responder.py — ระบบบอทตรวจจับและตอบคอมเมนต์ใต้โพสต์/คลิป Facebook อัตโนมัติ 24/7



พร้อมแจ้งเตือนเข้า Telegram (@pakhem_fish_bot) ทันทีที่มีลูกค้าคอมเมนต์



"""







import json



import logging



import os



import re



import subprocess



import sys



import time



from datetime import datetime, timezone, timedelta



from pathlib import Path



import httpx



import sys as _sys



from pathlib import Path as _Path



_BACKEND_DIR = str(_Path(__file__).resolve().parent.parent / "backend")



if _BACKEND_DIR not in _sys.path:



    _sys.path.insert(0, _BACKEND_DIR)

from app.services.sales_status import closed_notice, is_sales_closed, mask_sales_text
from app.services.fb_chat_only import build_friendly_chat_reply, is_fb_chat_only_mode



from app.services.thai_address_validator import (



    build_incomplete_order_guidance,



    enrich_thai_address,



    has_complete_thai_address,



    normalize_thai_digits,



    validate_thai_phone,



)







if sys.platform == "win32":



    _orig_popen = subprocess.Popen



    class _SilentPopen(_orig_popen):



        def __init__(self, *args, **kwargs):



            kwargs.setdefault("creationflags", 0)



            kwargs["creationflags"] |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)



            super().__init__(*args, **kwargs)



    subprocess.Popen = _SilentPopen







ROOT_DIR = Path(__file__).resolve().parent.parent



if sys.stdout is None or sys.stderr is None:



    _log_path = ROOT_DIR / "artifacts" / "fb_comment_responder.log"



    _log_path.parent.mkdir(parents=True, exist_ok=True)



    _stream = open(_log_path, "a", encoding="utf-8", buffering=1)



    sys.stdout = _stream



    sys.stderr = _stream







sys.path.insert(0, str(ROOT_DIR))



sys.path.insert(0, str(ROOT_DIR / "backend"))



sys.path.insert(0, str(ROOT_DIR / "tools"))



sys.path.insert(0, str(ROOT_DIR / "reels_uploader"))







from dotenv import load_dotenv



load_dotenv(ROOT_DIR / "backend" / ".env")







from reels_uploader.uploader import configured_pages



from telegram_notifier import send_telegram_alert







logger = logging.getLogger("FBCommentResponder")



ICT = timezone(timedelta(hours=7))







WEB_STORE_URL = "https://watt29.github.io/pakhem-shop/fish.html"



MAIN_SHOP_URL = "https://watt29.github.io/pakhem-shop/"

# Anti-duplicate: เก็บ timestamp ล่าสุดที่ Inbox Poller ส่งข้อความให้แต่ละ sender
# ถ้า webhook ตอบไปแล้ว หรือ poller ตอบไปภายใน 5 นาที → ข้ามไม่ส่งซ้ำ
_INBOX_SENDER_COOLDOWN: dict[str, float] = {}
_INBOX_COOLDOWN_SECS = 5  # 5 วินาที (คุยโต้ตอบต่อเนื่องได้ มี replied_history[mid] กันตอบซ้ำอยู่แล้ว)



LINE_OA_URL = "https://lin.ee/o9Kjp1N"



HISTORY_FILE = ROOT_DIR / "artifacts" / "replied_fb_comments.json"







SUPABASE_URL = os.getenv("SUPABASE_URL", "https://usqhvujqmnxqrdoovvnp.supabase.co")



SUPABASE_KEY = (



    os.getenv("SUPABASE_SERVICE_ROLE_KEY")



    or os.getenv("SUPABASE_KEY")



    or os.getenv("SUPABASE_ANON_KEY", "")



)











THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]



THAI_MONTHS = [



    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",



    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."



]











def _fmt_thai_date(dt: datetime) -> str:



    """แปลงวันที่เป็นรูปแบบ 'วันอังคารที่ 27 ต.ค.'"""



    day_name = THAI_DAYS[dt.weekday()]



    month_name = THAI_MONTHS[dt.month]



    return f"วัน{day_name}ที่ {dt.day} {month_name}"











def calculate_delivery_schedule(now_dt: datetime | None = None) -> dict:



    """



    คำนวณรอบจัดส่ง: ทางร้านจะไปส่งที่ขนส่งภายใน 1–2 วัน (เพราะทำปลาตากแดด 1 วัน + แช่แข็งอย่างน้อย 12 ชม.)



    """



    now = now_dt or datetime.now(ICT)



    cutoff_note = "ทางร้านจะไปส่งที่ขนส่งภายใน 1–2 วัน (เพราะทำปลาสดใหม่ ตากแดด 1 วัน และแช่แข็งอย่างน้อย 12 ชม. ก่อนแพ็กส่งจ้า)"







    return {



        "now_time": now.strftime("%H:%M"),



        "ship_date_str": "ภายใน 1–2 วัน",



        "cutoff_note": cutoff_note,



        "bkk_range": "ทางร้านจะไปส่งที่ขนส่งภายใน 1–2 วัน (ทำปลาตากแดด 1 วัน + แช่แข็งอย่างน้อย 12 ชม.)",



        "upcountry_range": "ทางร้านจะไปส่งที่ขนส่งภายใน 1–2 วัน (ทำปลาตากแดด 1 วัน + แช่แข็งอย่างน้อย 12 ชม.)",



    }











def _load_replied_history() -> dict:



    if HISTORY_FILE.exists():



        try:



            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))



        except Exception:



            return {}



    return {}











def _save_replied_history(data: dict) -> None:



    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)



    HISTORY_FILE.write_text(



        json.dumps(data, ensure_ascii=False, indent=2),



        encoding="utf-8"



    )











def _get_pending_slip_from_supabase(sender_id: str) -> dict | None:



    """ดึงข้อมูลสลิปที่ลูกค้าเพิ่งส่งใน Facebook Messenger จากตาราง system_preferences (ภายใน 24 ชม.)"""



    if not sender_id or not SUPABASE_URL or not SUPABASE_KEY:



        return None



    try:



        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}



        r = httpx.get(



            f"{SUPABASE_URL}/rest/v1/system_preferences",



            params={"key": f"eq.fb_slip_{sender_id}", "select": "value"},



            headers=headers,



            timeout=6.0,



        )



        if r.status_code == 200 and r.json():



            val = json.loads(r.json()[0].get("value") or "{}")



            if (time.time() - float(val.get("ts") or 0)) < 86400:



                return val



    except Exception:



        pass



    return None











def _clear_pending_slip_in_supabase(sender_id: str) -> None:



    if not sender_id or not SUPABASE_URL or not SUPABASE_KEY:



        return



    try:



        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}



        httpx.delete(



            f"{SUPABASE_URL}/rest/v1/system_preferences",



            params={"key": f"eq.fb_slip_{sender_id}"},



            headers=headers,



            timeout=6.0,



        )



    except Exception:



        pass











def _save_comment_order_to_supabase(



    order_code: str,



    name: str,



    phone: str,



    address: str,



    pkg: str,



    price: float,



    payment_method: str = "ปิดรับออเดอร์",



    sender_id: str = "",



    extra_note: str = "",



    page_name: str = "",



) -> bool:



    """ร้านยุติการจำหน่ายแล้ว — ไม่บันทึกออเดอร์จากคอมเมนต์."""
    return False











def _save_comment_lead_to_supabase(



    sender_id: str,



    sender_name: str,



    phone: str,



    message: str,



    post_id: str,



    comment_id: str,



    intent: str = "comment",



    private_replied: bool = False,



) -> bool:



    """บันทึกข้อมูลผู้มีส่วนร่วมคอมเมนต์ลงตาราง public.ad_leads บน Supabase เพื่อทำ Retargeting CRM"""



    if not SUPABASE_URL or not SUPABASE_KEY:



        return False



    try:



        headers = {



            "apikey": SUPABASE_KEY,



            "Authorization": f"Bearer {SUPABASE_KEY}",



            "Content-Type": "application/json",



            "Prefer": "return=minimal",



        }



        payload = {



            "platform": "facebook_comment",



            "sender_id": sender_id or "",



            "sender_name": sender_name or "ลูกค้า Facebook",



            "phone": phone or "",



            "message": message or "",



            "post_id": post_id or "",



            "comment_id": comment_id or "",



            "intent": intent,



            "private_replied": bool(private_replied),



            "created_at": datetime.now(ICT).isoformat(),



        }



        r = httpx.post(



            f"{SUPABASE_URL}/rest/v1/ad_leads",



            headers=headers,



            json=payload,



            timeout=8.0,



        )



        return r.status_code in (200, 201)



    except Exception as e:



        logger.warning(f"[FBComment] supabase ad_leads save failed: {e}")



        return False











def generate_comment_reply(comment_text: str, commenter_name: str = "", post_message: str = "", sender_id: str = "", page_name: str = "") -> tuple[str, dict | None]:



    """ตอบคอมเมนต์แบบปิดรับออเดอร์ (ไม่มีราคา/แพ็กเกจ)."""
    return closed_notice(), None











def generate_private_offer_message(comment_text: str, commenter_name: str = "", post_message: str = "") -> str:

    """ร้านยุติการจำหน่ายแล้ว — ไม่มีข้อเสนอ/ราคาทางแชท."""
    return closed_notice()











_AD_STORY_CACHE: dict[str, tuple[float, list[str]]] = {}



_DEAD_STORY_IDS: set[str] = set()











def _fetch_ad_story_ids_for_page(page_id: str) -> list[str]:



    """ดึงรายการ effective_object_story_id / object_story_id ของแอดทั้งหมดในบัญชีโฆษณา (แคช 5 นาที)"""



    now_ts = time.time()



    cached = _AD_STORY_CACHE.get(page_id)



    if cached and (now_ts - cached[0] < 300):



        return [s for s in cached[1] if s not in _DEAD_STORY_IDS]







    ads_token = os.getenv("FACEBOOK_ADS_ACCESS_TOKEN", "").strip()



    act_id = os.getenv("FACEBOOK_AD_ACCOUNT_ID", "act_294446695507241").strip()



    if not ads_token or not act_id:



        return []







    sids: list[str] = []



    seen: set[str] = set()



    try:



        r = httpx.get(



            f"https://graph.facebook.com/v21.0/{act_id}/ads",



            params={



                "access_token": ads_token,



                "limit": 50,



                "fields": "id,status,effective_status,creative{object_story_id,effective_object_story_id}",



            },



            timeout=12.0,



        )



        if r.status_code == 200:



            for item in r.json().get("data", []):



                cr = item.get("creative") or {}



                for f in ("effective_object_story_id", "object_story_id"):



                    val = str(cr.get(f) or "").strip()



                    if val.startswith(f"{page_id}_") and val not in seen and val not in _DEAD_STORY_IDS:



                        seen.add(val)



                        sids.append(val)



    except Exception as e:



        logger.warning(f"[FBComment] fetch ads story IDs error: {e}")







    _AD_STORY_CACHE[page_id] = (now_ts, sids)



    return sids











def _unmask_commenter_from_conversations(page_id: str, token: str, recipient_id: str = "", comment_id: str = "") -> tuple[str, str]:



    """ดึงชื่อโปรไฟล์จริง (Full Name) และ PSID จาก Conversations หลังยิง Private Reply สำเร็จ"""



    if not page_id or not token:



        return "", recipient_id



    cid_suffix = comment_id.split("_")[-1] if comment_id else ""



    try:



        r = httpx.get(



            f"https://graph.facebook.com/v21.0/{page_id}/conversations",



            params={



                "access_token": token,



                "limit": 10,



                "fields": "id,participants,messages.limit(5){id,message,from}",



            },



            timeout=10.0,



        )



        if r.status_code == 200:



            for conv in r.json().get("data", []):



                parts = [p for p in (conv.get("participants") or {}).get("data", []) if str(p.get("id")) != page_id]



                if not parts:



                    continue



                p_id = str(parts[0].get("id") or "")



                p_name = (parts[0].get("name") or "").strip()



                if recipient_id and p_id == str(recipient_id) and p_name:



                    return p_name, p_id



                if cid_suffix:



                    for m in (conv.get("messages") or {}).get("data", []):



                        if f"comment_id={cid_suffix}" in (m.get("message") or ""):



                            return p_name, p_id



    except Exception:



        pass



    return "", recipient_id











def reply_to_fb_comment(



    comment_id: str,



    message: str,



    token: str,



    page_id: str = "",



    private_message: str = "",



    comment_text: str = "",



    commenter_name: str = "",



    post_message: str = "",



) -> dict:



    message = mask_sales_text(message)
    """กดถูกใจคอมเมนต์ลูกค้า + ทักแชทเสนอโปรโมชั่นทาง Inbox (Private Reply เพื่อถอดรหัสชื่อจริง) + ตอบกลับใต้คอมเมนต์"""



    # 1. กด Like ให้คอมเมนต์ลูกค้าก่อนเพื่อความใส่ใจ



    try:



        httpx.post(



            f"https://graph.facebook.com/v21.0/{comment_id}/likes",



            params={"access_token": token},



            timeout=8.0,



        )



    except Exception:



        pass







    # 2. ทักแชทส่วนตัวเข้า Messenger Inbox ลูกค้า (Private Reply API) ก่อน เพื่อถอดรหัสชื่อจริง (Profile Unmasking)



    private_ok = False



    private_data = {}



    private_error = ""



    unmasked_name = (commenter_name or "").strip()



    unmasked_id = ""



    if page_id and private_message:



        try:



            pr = httpx.post(



                f"https://graph.facebook.com/v21.0/{page_id}/messages",



                params={"access_token": token},



                json={



                    "recipient": {"comment_id": comment_id},



                    "message": {"text": private_message},



                },



                timeout=15.0,



            )



            if pr.status_code == 200:



                private_ok = True



                private_data = pr.json()



                recip_id = str(private_data.get("recipient_id") or "")



                if not unmasked_name:



                    u_name, u_id = _unmask_commenter_from_conversations(page_id, token, recip_id, comment_id)



                    if u_name:



                        unmasked_name = u_name



                    if u_id:



                        unmasked_id = u_id



                    if unmasked_name and comment_text:



                        message, _ = generate_comment_reply(



                            comment_text=comment_text,



                            commenter_name=unmasked_name,



                            post_message=post_message,



                        )



            else:



                private_error = f"HTTP {pr.status_code}: {pr.text[:200]}"



        except Exception as e:



            private_error = str(e)







    # 3. ส่งข้อความตอบกลับใต้คอมเมนต์ (Public Comment Reply)



    public_ok = False



    public_data = {}



    public_error = ""



    try:



        r = httpx.post(



            f"https://graph.facebook.com/v21.0/{comment_id}/comments",



            params={"access_token": token},



            data={"message": message},



            timeout=15.0,



        )



        if r.status_code == 200:



            public_ok = True



            public_data = r.json()



        else:



            public_error = f"HTTP {r.status_code}: {r.text}"



    except Exception as e:



        public_error = str(e)







    if public_ok:



        return {



            "ok": True,



            "data": public_data,



            "final_reply_message": message,



            "unmasked_name": unmasked_name,



            "unmasked_id": unmasked_id,



            "private_reply_ok": private_ok,



            "private_reply_data": private_data,



            "private_reply_error": private_error,



        }



    return {



        "ok": False,



        "error": public_error,



        "unmasked_name": unmasked_name,



        "unmasked_id": unmasked_id,



        "private_reply_ok": private_ok,



    }











COLD_PACK_POSTER_URL = "https://usqhvujqmnxqrdoovvnp.supabase.co/storage/v1/object/public/slips/cold_pack_poster.png"











def build_fish_first_comment() -> str:
    """First Comment ที่ปักหมุด — ร้านยุติการจำหน่ายแล้ว จึงไม่มีราคา/แพ็กเกจ."""
    return (
        "🙏 ขอขอบพระคุณที่ให้ความสนใจร้านป้าเข็มนะคะ\n"
        "ขณะนี้ทางร้านได้ยุติการจำหน่ายและปิดรับออเดอร์ทุกรายการเรียบร้อยแล้ว "
        "จึงยังไม่มีสินค้าและราคาให้เสนอในตอนนี้ค่ะ\n"
        "กราบขออภัยในความไม่สะดวก และขอบพระคุณที่ให้การสนับสนุนด้วยดีตลอดมาค่ะ ❤️"
    )














def build_fish_guarantee_comment() -> str:
    """คอมเมนต์ประกาศ — ร้านยุติการจำหน่ายแล้ว ไม่มีเงื่อนไขการขาย/ราคา."""
    return (
        "📌 ประกาศจากร้านป้าเข็ม\n\n"
        "ทางร้านได้ยุติการจำหน่ายและปิดรับออเดอร์ทุกรายการแล้วค่ะ "
        "จึงไม่มีเงื่อนไขการสั่งซื้อหรือราคาให้แจ้งในขณะนี้\n\n"
        "ขอบพระคุณทุกท่านที่ให้การสนับสนุนด้วยดีตลอดมาค่ะ 🙏"
    )














def scan_and_reply_comments(limit_posts: int = 12) -> dict:



    """



    สแกนทั้งโพสต์ (published_posts) และคลิปวิดีโอ/Reels (video_reels, videos) บนเพจ Facebook ป้าเข็ม:



    0) หากเป็นคลิป/โพสต์ปลาสลิดที่ยังไม่มี 'คอมเมนต์แรกพร้อมลิงก์กดคลิกได้' จะวางคอมเมนต์แรกให้อัตโนมัติทันที



    1) หากพบคอมเมนต์ของลูกค้าที่ยังไม่ได้ตอบ จะกด Like + ตอบกลับใต้คอมเมนต์ทันที



    2) ทักแชทเสนอโปรโมชั่นเข้า Inbox ลูกค้า (Private Reply)



    3) แจ้งเตือนเข้า Telegram เจ้าของร้านทันที



    """



    pages = configured_pages()



    if not pages:



        return {"ok": False, "error": "No configured Facebook pages"}







    replied_history = _load_replied_history()



    replied_count = 0



    seen_comment_ids_in_cycle = set()



    first_comments_posted = 0



    details = []







    for page in pages:



        page_id = str(page.get("id") or page.get("page_id") or "")



        page_name = page.get("name") or (



            "เพจ 1: ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้" if page_id == "1307380735783361"



            else ("เพจ 2: ครัวแม่บ้าน ชี้เป้าของอร่อย" if page_id == "1323469404180656" else f"เพจป้าเข็ม ({page_id})")



        )



        token = page.get("token") or ""



        if not page_id or not token:



            continue







        # ดึงทั้ง video_reels, videos, published_posts และ Dark Ad Posts (ads_posts + Ads Manager Story IDs) เพื่อไม่ให้ตกหล่นแม้แต่โพสต์หรือโฆษณาเดียว



        items_to_scan = []



        seen_item_ids = set()



        _endpoints = (
            [
                ("published_posts", "message", {}),
                ("video_reels", "description", {}),
            ]
            if is_fb_chat_only_mode()
            else [
                ("live_videos", "description", {}),
                ("video_reels", "description", {}),
                ("videos", "description", {}),
                ("published_posts", "message", {}),
                ("ads_posts", "message", {"include_inline_create": "true"}),
            ]
        )

        for endpoint, msg_field, extra_params in _endpoints:



            try:



                time_field = "creation_time" if endpoint == "live_videos" else "created_time"



                req_params = {



                    "access_token": token,



                    "limit": limit_posts,



                    "fields": f"id,{msg_field},{time_field},comments.limit(50){{id,from,message,attachment,created_time,comments.limit(20){{id,from,message}}}}",



                    **extra_params,



                }



                r = httpx.get(



                    f"https://graph.facebook.com/v21.0/{page_id}/{endpoint}",



                    params=req_params,



                    timeout=15.0,



                )



                if r.status_code == 200:



                    for obj in r.json().get("data", []):



                        oid = obj.get("id", "")



                        if oid and oid not in seen_item_ids:



                            seen_item_ids.add(oid)



                            items_to_scan.append({



                                "id": oid,



                                "endpoint": endpoint,



                                "created_time": obj.get("created_time") or obj.get("creation_time") or "",



                                "message": obj.get(msg_field) or "",



                                "comments": (obj.get("comments") or {}).get("data", []),



                            })



                else:



                    logger.warning(f"[FBComment] fetch {endpoint} failed ({page_name}): {r.text[:200]}")



            except Exception as e:



                logger.warning(f"[FBComment] fetch {endpoint} exception ({page_name}): {e}")







        # สแกน Dark Ad Posts จาก Ads Manager (effective_object_story_id) ที่ไม่อยู่ใน published_posts



        ad_story_ids = [sid for sid in _fetch_ad_story_ids_for_page(page_id) if sid not in seen_item_ids]



        ad_fields = "id,message,created_time,comments.limit(50){id,from,message,attachment,created_time,comments.limit(20){id,from,message}}"



        for i in range(0, len(ad_story_ids), 20):



            batch_ids = ad_story_ids[i : i + 20]



            try:



                r_ads = httpx.get(



                    "https://graph.facebook.com/v21.0/",



                    params={"access_token": token, "ids": ",".join(batch_ids), "fields": ad_fields},



                    timeout=15.0,



                )



                if r_ads.status_code == 200:



                    for sid, obj in (r_ads.json() or {}).items():



                        if isinstance(obj, dict) and obj.get("id") and sid not in seen_item_ids:



                            seen_item_ids.add(sid)



                            items_to_scan.append({



                                "id": sid,



                                "endpoint": "ad_story",



                                "created_time": obj.get("created_time") or "",



                                "message": obj.get("message") or "",



                                "comments": (obj.get("comments") or {}).get("data", []),



                            })



                else:



                    # Fallback เช็ครายตัวเพื่อคัดกรองโพสต์แอดที่ถูกลบออก (_DEAD_STORY_IDS)



                    for sid in batch_ids:



                        if sid in seen_item_ids or sid in _DEAD_STORY_IDS:



                            continue



                        r_one = httpx.get(



                            f"https://graph.facebook.com/v21.0/{sid}",



                            params={"access_token": token, "fields": ad_fields},



                            timeout=10.0,



                        )



                        if r_one.status_code == 200:



                            obj = r_one.json() or {}



                            if obj.get("id"):



                                seen_item_ids.add(sid)



                                items_to_scan.append({



                                    "id": sid,



                                    "endpoint": "ad_story",



                                    "created_time": obj.get("created_time") or "",



                                    "message": obj.get("message") or "",



                                    "comments": (obj.get("comments") or {}).get("data", []),



                                })



                        elif r_one.status_code in (400, 404):



                            _DEAD_STORY_IDS.add(sid)



            except Exception as e:



                logger.warning(f"[FBComment] fetch ad_story batch exception ({page_name}): {e}")







        # ตรวจสอบว่าข้อความคลิปไหนมีคอมเมนต์แรกวางลิงก์ไปแล้วบ้าง (กันโพสต์ซ้ำเฉพาะกรณี Reel เดียวกันที่มีทั้ง video_id และ post_id ในเวลาเดียวกัน)



        pinned_msg_signatures = set()



        for post in items_to_scan:



            p_time_min = (post.get("created_time") or "")[:16]



            p_msg_sig = f"{page_id}:{p_time_min}:{(post.get('message') or '')[:80].strip()}"



            p_id = post.get("id", "")



            if f"first_comment_{p_id}" in replied_history:



                pinned_msg_signatures.add(p_msg_sig)



                continue



            for c in post.get("comments", []):



                c_text = c.get("message") or ""



                c_from_id = str((c.get("from") or {}).get("id") or "")



                if "watt29.github.io/pakhem-shop" in c_text:



                    pinned_msg_signatures.add(p_msg_sig)



                    replied_history[f"first_comment_{p_id}"] = {



                        "first_comment_exists": True,



                        "checked_at": datetime.now(ICT).isoformat(),



                    }



                    break







        try:



            for post in items_to_scan:



                post_id = post.get("id", "")



                post_msg = post.get("message", "")



                comments_data = post.get("comments", [])



                p_time_min = (post.get("created_time") or "")[:16]



                p_msg_sig = f"{page_id}:{p_time_min}:{post_msg[:80].strip()}"







                # 0) วางคอมเมนต์แรกพร้อมลิงก์กดคลิกได้อัตโนมัติ สำหรับคลิป/โพสต์ปลาสลิดที่ยังไม่มีคอมเมนต์แรก



                is_fish_post = any(k in post_msg for k in ("ปลาสลิด", "ปลาแดดเดียว", "fish.html"))



                if (



                    not is_fb_chat_only_mode()
                    and is_fish_post



                    and f"first_comment_{post_id}" not in replied_history



                    and p_msg_sig not in pinned_msg_signatures



                ):



                    try:



                        fc_text = build_fish_first_comment()



                        fc_res = httpx.post(



                            f"https://graph.facebook.com/v21.0/{post_id}/comments",



                            data={"message": fc_text, "access_token": token},



                            timeout=15.0,



                        )



                        if fc_res.status_code == 200:



                            fc_id = (fc_res.json() or {}).get("id", "")



                            # วางคอมเมนต์ที่ 2 แนบรูปอินโฟกราฟิกแพ็กเก็บความเย็น



                            try:



                                gc_res = httpx.post(



                                    f"https://graph.facebook.com/v21.0/{post_id}/comments",



                                    data={



                                        "message": build_fish_guarantee_comment(),



                                        "attachment_url": COLD_PACK_POSTER_URL,



                                        "access_token": token,



                                    },



                                    timeout=20.0,



                                )



                                gc_id = (gc_res.json() or {}).get("id", "") if gc_res.status_code == 200 else ""



                                if gc_id:



                                    replied_history[gc_id] = {



                                        "skipped": "own_page_comment",



                                        "checked_at": datetime.now(ICT).isoformat(),



                                    }



                            except Exception:



                                pass



                            replied_history[f"first_comment_{post_id}"] = {



                                "first_comment_id": fc_id,



                                "posted_at": datetime.now(ICT).isoformat(),



                            }



                            if fc_id:



                                replied_history[fc_id] = {



                                    "skipped": "own_page_comment",



                                    "checked_at": datetime.now(ICT).isoformat(),



                                }



                            pinned_msg_signatures.add(p_msg_sig)



                            _save_replied_history(replied_history)



                            first_comments_posted += 1



                            details.append({



                                "action": "first_comment_posted",



                                "page": page_name,



                                "post_id": post_id,



                                "first_comment_id": fc_id,



                            })



                            logger.info(f"📌 วางคอมเมนต์แรกพร้อมลิงก์ใต้คลิป {post_id} ({page_name}) สำเร็จ -> {fc_id}")



                        else:



                            logger.warning(f"⚠️ วางคอมเมนต์แรกใต้คลิป {post_id} ไม่สำเร็จ: {fc_res.text[:200]}")



                    except Exception as e:



                        logger.warning(f"⚠️ วางคอมเมนต์แรก exception ({post_id}): {e}")







                for c in comments_data:



                    cid = c.get("id", "")



                    c_msg = (c.get("message") or "").strip()



                    has_attachment = bool(c.get("attachment"))



                    c_from = c.get("from") or {}



                    from_id = str(c_from.get("id") or "")



                    from_name = (c_from.get("name") or "").strip()







                    if not cid or (not c_msg and not has_attachment):



                        continue



                    if not c_msg and has_attachment:



                        c_msg = "[ส่งสติกเกอร์/รูปภาพสนใจสินค้า]"







                    # ข้ามคอมเมนต์ที่เพจเป็นคนโพสต์เอง (เช่น คอมเมนต์ปักหมุดของร้าน)



                    if (



                        from_id == page_id



                        or "ป้าเข็ม" in from_name



                        or "มาตรฐานการแพ็กส่งด่วน" in c_msg



                        or "มั่นใจความสด 100%" in c_msg



                        or "watt29.github.io/pakhem-shop" in c_msg



                    ):



                        replied_history[cid] = {



                            "skipped": "own_page_comment",



                            "checked_at": datetime.now(ICT).isoformat(),



                        }



                        continue







                    # ข้ามถ้าเคยตอบไปแล้วในประวัติ หรือตรวจพบซ้ำในรอบการสแกนนี้ (ข้ามการตอบซ้ำจากโพสต์แอดหลาย Story ID)



                    if cid in replied_history or cid in seen_comment_ids_in_cycle:



                        continue



                    seen_comment_ids_in_cycle.add(cid)







                    # เช็คจาก sub-comments ว่าเพจเคยตอบกลับไปแล้วหรือยัง



                    sub_comments = (c.get("comments") or {}).get("data", [])



                    already_replied_on_fb = False



                    for sub in sub_comments:



                        sub_from = sub.get("from") or {}



                        sub_msg = sub.get("message") or ""



                        if (



                            str(sub_from.get("id") or "") == page_id



                            or "ป้าเข็ม" in (sub_from.get("name") or "")



                            or "watt29.github.io/pakhem-shop" in sub_msg



                        ):



                            already_replied_on_fb = True



                            break







                    if already_replied_on_fb:



                        replied_history[cid] = {



                            "replied_on_fb": True,



                            "checked_at": datetime.now(ICT).isoformat(),



                        }



                        continue







                    # สร้างคำตอบใต้คอมเมนต์ + ข้อความทักเสนอทาง Inbox และส่งทันที



                    reply_text, order_info = generate_comment_reply(



                        comment_text=c_msg,



                        commenter_name=from_name,



                        post_message=post_msg,



                        sender_id=from_id,



                        page_name=page_name,



                    )



                    private_offer_text = generate_private_offer_message(



                        comment_text=c_msg,



                        commenter_name=from_name,



                        post_message=post_msg,



                    )



                    res = reply_to_fb_comment(



                        comment_id=cid,



                        message=reply_text,



                        token=token,



                        page_id=page_id,



                        private_message=private_offer_text,



                        comment_text=c_msg,



                        commenter_name=from_name,



                        post_message=post_msg,



                    )



                    now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")







                    if res.get("ok"):



                        reply_id = (res.get("data") or {}).get("id", "")



                        priv_ok = bool(res.get("private_reply_ok"))



                        final_name = (res.get("unmasked_name") or from_name or "").strip()



                        final_id = (res.get("unmasked_id") or from_id or "").strip()



                        final_reply_text = res.get("final_reply_message") or reply_text



                        replied_history[cid] = {



                            "comment_message": c_msg,



                            "from_name": final_name or "ลูกค้า Facebook",



                            "from_id": final_id,



                            "reply_id": reply_id,



                            "private_reply_ok": priv_ok,



                            "replied_at": now_str,



                        }



                        _save_replied_history(replied_history)



                        replied_count += 1



                        _save_comment_lead_to_supabase(



                            sender_id=final_id,



                            sender_name=final_name,



                            phone=(order_info or {}).get("phone", ""),



                            message=c_msg,



                            post_id=post_id,



                            comment_id=cid,



                            intent="order" if order_info else "comment",



                            private_replied=priv_ok,



                        )



                        details.append({



                            "comment_id": cid,



                            "comment_message": c_msg,



                            "reply_id": reply_id,



                            "private_reply_ok": priv_ok,



                            "private_reply_error": res.get("private_reply_error", ""),



                            "from_name": final_name or "ลูกค้า Facebook",



                        })







                        # แจ้งเตือนเข้า Telegram เจ้าของร้านทันที



                        post_url = f"https://www.facebook.com/{post_id}"



                        inbox_status = "✅ ทักแชทเสนอโปรโมชั่นเข้า Inbox ลูกค้าสำเร็จ" if priv_ok else f"ℹ️ ตอบหน้าโพสต์สำเร็จ (Inbox: {res.get('private_reply_error') or 'ส่งเฉพาะใต้โพสต์'})"



                        tg_msg = (



                            f"💬 [บอทตอบคอมเมนต์ + ทักเสนอลูกค้า Facebook สำเร็จ!] ✅\n"



                            f"━━━━━━━━━━━━━━━━━━━━━━\n"



                            f"🏠 เพจ: {page_name}\n"



                            f"👤 ลูกค้า: {final_name or 'ผู้ใช้งาน Facebook'}\n"



                            f"❓ คอมเมนต์ลูกค้า: \"{c_msg}\"\n"



                            f"💌 สถานะทักแชท Inbox: {inbox_status}\n"



                            f"⏰ เวลาตอบ: {now_str} น.\n"



                            f"━━━━━━━━━━━━━━━━━━━━━━\n"



                            f"🤖 ข้อความที่บอทป้าเข็มตอบกลับ:\n"



                            f"{final_reply_text}\n"



                            f"━━━━━━━━━━━━━━━━━━━━━━\n"



                            f"🔗 ดูโพสต์จริง: {post_url}"



                        )



                        send_telegram_alert(tg_msg)



                        logger.info(f"✅ ตอบคอมเมนต์ {cid} ({final_name}) สำเร็จ -> reply_id={reply_id}, private_reply={priv_ok}")



                    else:



                        logger.warning(f"⚠️ ตอบคอมเมนต์ {cid} ไม่สำเร็จ: {res.get('error')}")







        except Exception as e:



            logger.warning(f"[FBComment] scan error on {page_name}: {e}")







    _save_replied_history(replied_history)



    return {



        "ok": True,



        "replied_count": replied_count,



        "first_comments_posted": first_comments_posted,



        "details": details,



    }











def scan_and_reply_inbox_messages(limit_threads: int = 10) -> int:



    """



    ระบบสำรองอัตโนมัติ (Failsafe Inbox Poller):



    สแกนแชท Inbox ของทุกเพจ Facebook (/{page_id}/conversations)



    หากพบข้อความล่าสุดเป็นของลูกค้าที่ยังไม่มีบอท Webhook ตอบกลับภายใน 20 วินาที



    จะตอบกลับเข้า Messenger + รับออเดอร์ลง Supabase + แจ้งเตือน Telegram อัตโนมัติทันที



    """



    pages = configured_pages()



    if not pages:



        return 0







    replied_history = _load_replied_history()



    inbox_replied = 0







    for page in pages:



        page_id = str(page.get("id") or page.get("page_id") or "")



        page_name = page.get("name") or (



            "เพจ 1: ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้" if page_id == "1307380735783361"



            else ("เพจ 2: ครัวแม่บ้าน ชี้เป้าของอร่อย" if page_id == "1323469404180656" else f"เพจป้าเข็ม ({page_id})")



        )



        token = page.get("token") or ""



        if not page_id or not token:



            continue







        try:



            r = httpx.get(



                f"https://graph.facebook.com/v21.0/{page_id}/conversations",



                params={



                    "access_token": token,



                    "limit": limit_threads,



                    "fields": "id,updated_time,participants,messages.limit(6){id,message,from,created_time}",



                },



                timeout=15.0,



            )



            if r.status_code != 200:



                continue







            threads = r.json().get("data", [])



            for t in threads:



                msgs = (t.get("messages") or {}).get("data", [])



                if not msgs:



                    continue



                latest = None



                for m_item in msgs:



                    cand_text = (m_item.get("message") or "").strip()



                    cand_from_id = str((m_item.get("from") or {}).get("id") or "")



                    if not cand_text:



                        # หากเพจส่งข้อความแบบ Button Template (message เป็นค่าว่าง) แปลว่าเพจตอบลูกค้าไปแล้ว ห้ามตอบซ้ำ!



                        if cand_from_id == page_id:



                            latest = m_item



                            break



                        continue



                    if cand_from_id == page_id:



                        # หากเป็นข้อความระบบ Facebook ให้ข้าม แต่ถ้าเป็นข้อความที่เพจตอบไปแล้ว ให้ถือว่าตอบแล้ว ไม่ตอบซ้ำ!



                        if 'ข้อความนี้ถูกย้ายไปยัง "สแปม"' in cand_text or "Messenger automatically created" in cand_text:



                            continue



                        latest = m_item



                        break



                    latest = m_item



                    break



                if not latest:



                    continue



                mid = str(latest.get("id") or "")



                m_text = (latest.get("message") or "").strip()



                m_from = latest.get("from") or {}



                from_id = str(m_from.get("id") or "")



                from_name = (m_from.get("name") or "").strip()



                created_str = latest.get("created_time") or ""







                # หากข้อความจริงล่าสุดเป็นของเพจเอง (รวมถึง Button Template) แปลว่าตอบไปแล้ว



                if from_id == page_id or "ป้าเข็ม" in from_name:



                    continue



                if not mid or not m_text or not from_id:



                    continue



                if mid in replied_history:



                    continue

                # Anti-dup Inbox Poller: ถ้าเพิ่งส่งให้ sender นี้ภายใน 5 นาที → ข้ามไม่ส่งซ้ำ
                if (time.time() - _INBOX_SENDER_COOLDOWN.get(from_id, 0)) < _INBOX_COOLDOWN_SECS:
                    continue







                # ให้เวลา Webhook หลักตอบก่อน 20 วินาที เพื่อป้องกันการตอบซ้ำ



                try:



                    dt_created = datetime.strptime(created_str, "%Y-%m-%dT%H:%M:%S%z")



                    age_sec = (datetime.now(timezone.utc) - dt_created).total_seconds()



                    if age_sec < 3:



                        continue



                    # ข้ามแชทเก่าเกิน 24 ชั่วโมง



                    if age_sec > 86400:



                        replied_history[mid] = {"skipped": "older_than_24h"}



                        continue



                except Exception:



                    pass







                reply_text, order_info = generate_comment_reply(



                    comment_text=m_text,



                    commenter_name=from_name,



                    post_message="ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดพิเศษ",



                    sender_id=from_id,



                    page_name=page_name,



                )



                qr_buttons = [
                    {"content_type": "text", "title": "⭐ รับ 1 กก.", "payload": "QR_PKG_1KG"},
                    {"content_type": "text", "title": "📦 ลอง 500g", "payload": "QR_PKG_500G"},
                    {"content_type": "text", "title": "❄️ ชุด 2 กก.รถเย็น", "payload": "QR_PKG_2KG"},
                ]
                msg_payload = {"text": reply_text}
                if not is_fb_chat_only_mode() and "แชทนี้บันทึกไว้ให้แล้ว" not in reply_text:
                    msg_payload["quick_replies"] = qr_buttons

                # ส่งข้อความตัวอักษรแบบกระชับ 3 บรรทัด + Quick Reply (ข้อความไม่โดนตัดบนมือถือ 100% และไม่ส่งซ้ำสองเด้ง)

                send_res = httpx.post(

                    f"https://graph.facebook.com/v21.0/{page_id}/messages",

                    params={"access_token": token},

                    json={

                        "recipient": {"id": from_id},

                        "messaging_type": "RESPONSE",

                        "message": msg_payload,

                    },

                    timeout=12.0,

                )



                if send_res.status_code != 200:



                    send_res = httpx.post(



                        f"https://graph.facebook.com/v21.0/{page_id}/messages",



                        params={"access_token": token},



                        json={"recipient": {"id": from_id}, "message": {"text": reply_text}},



                        timeout=12.0,



                    )



                if send_res.status_code == 200:



                    now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")



                    replied_history[mid] = {



                        "inbox_message": m_text,



                        "from_name": from_name,



                        "replied_at": now_str,



                    }



                    _save_replied_history(replied_history)



                    inbox_replied += 1

                    # บันทึก timestamp ส่งล่าสุด ป้องกัน duplicate
                    _INBOX_SENDER_COOLDOWN[from_id] = time.time()



                    _save_comment_lead_to_supabase(



                        sender_id=from_id,



                        sender_name=from_name,



                        phone=(order_info or {}).get("phone", ""),



                        message=m_text,



                        post_id=f"INBOX_{page_id}",



                        comment_id=mid,



                        intent="order" if order_info else "inbox",



                        private_replied=True,



                    )



                    cb_phone = (order_info or {}).get("callback_phone")



                    if cb_phone:



                        send_telegram_alert(



                            f"📞 **[ลูกค้าทิ้งเบอร์ให้โทรกลับ!]** 🔔\n"



                            f"━━━━━━━━━━━━━━━━━━━━━━\n"



                            f"🏠 เพจ: {page_name} ({page_id})\n"



                            f"👤 ลูกค้า: {from_name} (ID: {from_id})\n"



                            f"📱 เบอร์โทร: **`{cb_phone}`**\n"



                            f"💬 ข้อความลูกค้า: \"{m_text}\"\n"



                            f"⏰ เวลา: {now_str} น.\n"



                            f"━━━━━━━━━━━━━━━━━━━━━━\n"



                            f"👉 กรุณากดโทรหาลูกค้าเพื่อแนะนำสินค้าและรับออเดอร์ได้ทันทีครับ!"



                        )



                    else:



                        send_telegram_alert(



                            f"💌 [บอทตอบแชท Inbox เพจ {page_name} อัตโนมัติ!] ✅\n"



                            f"━━━━━━━━━━━━━━━━━━━━━━\n"



                            f"👤 ลูกค้า: {from_name} (ID: {from_id})\n"



                            f"💬 ข้อความลูกค้า: \"{m_text}\"\n"



                            f"⏰ เวลาตอบ: {now_str} น.\n"



                            f"━━━━━━━━━━━━━━━━━━━━━━\n"



                            f"🤖 บอทป้าเข็มตอบกลับ:\n{reply_text}"



                        )



                    logger.info(f"✅ ตอบแชท Inbox {mid} ({from_name}) บนเพจ {page_name} สำเร็จ")



        except Exception as e:



            logger.warning(f"[FBInbox] scan error on {page_name}: {e}")







    _save_replied_history(replied_history)



    return inbox_replied











def scan_and_notify_tracking_numbers() -> int:



    """



    ตรวจเช็คออเดอร์ใน Supabase direct_orders ที่แอดมินเพิ่งกรอกเลขพัสดุ (tracking_number)



    แล้วส่งแจ้งเลขพัสดุกลับเข้าช่องทางที่ลูกค้าสั่งซื้อโดยอัตโนมัติ:



    - หากสั่งผ่าน LINE OA ([LINE_UID:...]) -> ส่งเข้า LINE ของลูกค้า



    - หากสั่งผ่าน Facebook Messenger ([FB_ID:...]) -> ส่งเข้า Messenger ของลูกค้า



    - หากสั่งผ่านคอมเมนต์ ([COMMENT_ID:...]) -> ตอบกลับใต้คอมเมนต์/Inbox ของลูกค้า



    """



    if not SUPABASE_URL or not SUPABASE_KEY:



        return 0







    track_history_file = ROOT_DIR / "artifacts" / "notified_tracking_orders.json"



    notified = {}



    if track_history_file.exists():



        try:



            notified = json.loads(track_history_file.read_text(encoding="utf-8"))



        except Exception:



            notified = {}







    headers = {



        "apikey": SUPABASE_KEY,



        "Authorization": f"Bearer {SUPABASE_KEY}",



    }



    try:



        r = httpx.get(



            f"{SUPABASE_URL}/rest/v1/direct_orders",



            params={"select": "*", "order": "id.desc", "limit": 50},



            headers=headers,



            timeout=10.0,



        )



        if r.status_code != 200:



            return 0



        orders = r.json()



    except Exception:



        return 0







    line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")



    pages = configured_pages()



    fb_token = pages[0].get("token", "") if pages else os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")







    sent_count = 0



    for o in orders:



        oid = str(o.get("id") or "")



        order_code = str(o.get("order_code") or "")



        tracking = (o.get("tracking_number") or "").strip()



        if not oid or not tracking:



            continue



        # ข้ามถ้าเคยแจ้งเลขพัสดุตัวนี้ไปแล้ว



        if notified.get(oid) == tracking:



            continue







        cust_name = o.get("customer_name") or "คุณลูกค้า"



        pkg_name = o.get("package_name") or o.get("product_name") or "ปลาสลิดแดดเดียว ป้าเข็ม คัดพิเศษ"



        note = o.get("note") or ""







        msg = (



            f"🚚 [พี่วิน - ฝ่ายจัดส่งและคลังสินค้าห้องเย็น]\n"



            f"สวัสดีครับคุณ {cust_name} พัสดุปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดพิเศษ จัดส่งออกเดินทางเรียบร้อยแล้วครับ! 🐟❄️\n"



            f"━━━━━━━━━━━━━━━━━━\n"



            f"🔖 รหัสคำสั่งซื้อ: {order_code}\n"



            f"📦 รายการ: {pkg_name}\n"



            f"🔢 เลขพัสดุ: {tracking}\n"



            f"━━━━━━━━━━━━━━━━━━\n"



            f"🧊 แพ็กซองฟอยล์เก็บความเย็น ส่งออกให้เรียบร้อยแล้วครับ เมื่อได้รับสินค้าแล้วแนะนำให้นำเข้าช่องฟรีซ (≤ -18°C) ทันทีนะครับ ขอบพระคุณที่อุดหนุนป้าเข็มครับ 🙏✨"



        )







        m_line = re.search(r"\[LINE_UID:([^\]]+)\]", note)



        m_fb = re.search(r"\[FB_ID:([^\]]+)\]", note)



        channel_sent = None







        if m_line and line_token:



            uid = m_line.group(1).strip()



            try:



                lr = httpx.post(



                    "https://api.line.me/v2/bot/message/push",



                    headers={



                        "Authorization": f"Bearer {line_token}",



                        "Content-Type": "application/json",



                    },



                    json={"to": uid, "messages": [{"type": "text", "text": msg}]},



                    timeout=10.0,



                )



                if lr.status_code == 200:



                    channel_sent = f"LINE OA ({uid[:8]}...)"



            except Exception as e:



                logger.warning(f"[TrackNotify] LINE push failed: {e}")







        elif m_fb and fb_token:



            fb_id = m_fb.group(1).strip()



            try:



                fr = httpx.post(



                    "https://graph.facebook.com/v21.0/me/messages",



                    params={"access_token": fb_token},



                    json={"recipient": {"id": fb_id}, "message": {"text": msg}},



                    timeout=10.0,



                )



                if fr.status_code == 200:



                    channel_sent = f"Facebook Messenger ({fb_id[:8]}...)"



            except Exception as e:



                logger.warning(f"[TrackNotify] FB push failed: {e}")







        notified[oid] = tracking



        track_history_file.parent.mkdir(parents=True, exist_ok=True)



        track_history_file.write_text(json.dumps(notified, ensure_ascii=False, indent=2), encoding="utf-8")







        if channel_sent:



            sent_count += 1



            send_telegram_alert(



                f"🚚 [บอทส่งแจ้งเลขพัสดุให้ลูกค้าอัตโนมัติสำเร็จ!] ✅\n"



                f"━━━━━━━━━━━━━━━━━━\n"



                f"🔖 รหัสออเดอร์: {order_code}\n"



                f"👤 ลูกค้า: {cust_name}\n"



                f"🔢 เลขพัสดุ: {tracking}\n"



                f"📲 ช่องทางที่บอททักแจ้ง: {channel_sent}"



            )



            logger.info(f"✅ แจ้งเลขพัสดุ {tracking} ให้ {order_code} ทาง {channel_sent} สำเร็จ")







    return sent_count











def _run_hermes_learning_cycle() -> None:



    """รันสมองกล Hermes AI อัตโนมัติเพื่อวิเคราะห์ยอดสั่งซื้อปลาสลิดและอัปเดต MARKET_MEMORY.md"""



    try:



        sys.path.insert(0, str(ROOT_DIR / "backend"))



        from app.db import SessionLocal



        from app.services.hermes_brain import analyze_market, format_market_memory







        db = SessionLocal()



        try:



            res = analyze_market(db)



            if res:



                mem_path = ROOT_DIR / "MARKET_MEMORY.md"



                mem_path.write_text(format_market_memory(res), encoding="utf-8")



                fish = res.get("report", {}).get("fish_orders", {})



                logger.info(



                    f"🧠 [Hermes AI Auto-Learn] อัปเดตสมองกลสำเร็จ: "



                    f"orders={fish.get('total_orders_all_time', 0)}, "



                    f"focus={res.get('skills', {}).get('fish_focus_package', '1kg')}"



                )



        finally:



            db.close()



    except Exception as e:



        logger.warning(f"[Hermes AI Auto-Learn] skipped: {e}")











def run_comment_responder_loop(interval_seconds: int = 30):



    """เธรดเบื้องหลังคอยตรวจและตอบคอมเมนต์ใหม่ + แชท Inbox + แจ้งเลขพัสดุอัตโนมัติทุกๆ 30 วินาที + กระตุ้น Render ทุก 10 นาที + Automated Ads Guard ทุก 15 นาที + Telegram Commander 24 ชม."""



    logger.info(f"💬 ระบบ Auto-Reply + Private Inbox Offer + Failsafe Inbox Poller + Auto-Tracking Push + Render Keep-Alive + Automated Ads Guard + Telegram Commander 24/7: ACTIVE (ตรวจทุก {interval_seconds} วินาที)")



    # เปิดเธรดรับคำสั่ง Telegram Commander (@pakhem_fish_bot) ควบคู่ไปพร้อมกันอัตโนมัติ



    try:



        import threading



        from telegram_commander import run_telegram_commander_loop



        t_cmd = threading.Thread(target=run_telegram_commander_loop, daemon=True, name="TelegramCommanderThread")



        t_cmd.start()



        logger.info("👑 [Telegram Commander] เริ่มเธรดรับคำสั่ง @pakhem_fish_bot อัตโนมัติ 24/7 สำเร็จ")



    except Exception as tc_err:



        logger.warning(f"[Telegram Commander] thread start error: {tc_err}")







    last_hermes_run = time.time()



    hermes_interval = 6 * 3600  # วิเคราะห์ยอดขายอัตโนมัติทุก 6 ชั่วโมง



    last_render_ping = 0.0



    render_ping_interval = 600  # กระตุ้น Render (Fish Cloud Guard 24/7) ทุก 10 นาที



    last_ads_guard_run = 0.0



    ads_guard_interval = 900  # ตรวจสอบแอดซ้ำ/แอดแพงทุก 15 นาที



    last_likes_harvest_run = time.time()



    likes_harvest_interval = 1800  # กวาดรายชื่อคนกดไลค์ (Playwright) + เชิญกดติดตามเพจทุก 30 นาที



    last_ads_report_run = time.time()



    ads_report_interval = 4 * 3600  # ส่งรายงานสรุปแอดและยอดขายเข้า Telegram อัตโนมัติทุก 4 ชั่วโมง



    last_engagement_sig = ""







    def _get_live_engagement_sig() -> str:



        """เช็คยอดกดไลค์ + คอมเมนต์สดทุก 30 วินาที (รวมทั้งโพสต์หน้าเพจและ Dark Ad Posts) หากเปลี่ยนแม้แต่ +1 จะสั่งซิงค์ชีตทันทีแบบ Real-Time"""



        parts = []



        p1_tok = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")



        p2_tok = os.getenv("FACEBOOK_PAGE_2_ACCESS_TOKEN", "")



        for pid, tok in [("1307380735783361", p1_tok), ("1323469404180656", p2_tok)]:



            if not tok:



                continue



            try:



                r = httpx.get(



                    f"https://graph.facebook.com/v21.0/{pid}",



                    params={



                        "access_token": tok,



                        "fields": "followers_count,fan_count,published_posts.limit(10){id,reactions.summary(true).limit(1),comments.summary(true).limit(1)}",



                    },



                    timeout=8.0,



                )



                if r.status_code == 200:



                    data = r.json()



                    parts.append(f"FLW_{pid}:{data.get('followers_count', 0)}:{data.get('fan_count', 0)}")



                    for p in (data.get("published_posts") or {}).get("data", []):



                        rc = int(((p.get("reactions") or {}).get("summary") or {}).get("total_count") or 0)



                        cm = int(((p.get("comments") or {}).get("summary") or {}).get("total_count") or 0)



                        if rc > 0 or cm > 0:



                            parts.append(f"{p.get('id')}:{rc}:{cm}")



                ad_sids = _fetch_ad_story_ids_for_page(pid)[:20]



                if ad_sids:



                    r_ad = httpx.get(



                        "https://graph.facebook.com/v21.0/",



                        params={



                            "access_token": tok,



                            "ids": ",".join(ad_sids),



                            "fields": "id,reactions.summary(true).limit(1),comments.summary(true).limit(1)",



                        },



                        timeout=8.0,



                    )



                    if r_ad.status_code == 200:



                        for sid, p in (r_ad.json() or {}).items():



                            if isinstance(p, dict):



                                rc = int(((p.get("reactions") or {}).get("summary") or {}).get("total_count") or 0)



                                cm = int(((p.get("comments") or {}).get("summary") or {}).get("total_count") or 0)



                                if rc > 0 or cm > 0:



                                    parts.append(f"AD_{sid}:{rc}:{cm}")



            except Exception:



                pass



        return "|".join(parts)







    def _trigger_realtime_crm_sheet_sync():



        try:



            import importlib



            import crm_leads_sync



            importlib.reload(crm_leads_sync)



            res_sync = crm_leads_sync.harvest_and_sync_all_crm_data()



            try:



                import sync_comments_sheet



                importlib.reload(sync_comments_sheet)



                recs = sync_comments_sheet.collect_all_comments_and_questions()



                sync_comments_sheet.sync_to_google_drive_sheet(recs)



            except Exception as sc_e:



                logger.warning(f"[SyncCommentsSheet] error: {sc_e}")



            logger.info(



                f"⚡ [Real-Time CRM Sync] อัปเดต Google Sheets สดทันทีสำเร็จ: "



                f"total_leads={res_sync.get('total_leads_in_db')}, "



                f"new_rt_likes={res_sync.get('new_realtime_likes')}, "



                f"new_rt_followers={res_sync.get('new_realtime_followers')}, "



                f"total_followers={res_sync.get('total_page_followers')}"



            )



        except Exception as rt_e:



            logger.warning(f"[RealTimeCRMSync] error: {rt_e}")







    def _trigger_bg_likes_and_crm_sync():



        try:



            import threading



            from fb_likes_harvester import harvest_likes_safe_locked



            threading.Thread(



                target=harvest_likes_safe_locked,



                kwargs={"click_invite": True},



                daemon=True,



                name="BG_LikesHarvesterThread",



            ).start()



        except Exception as bg_e:



            logger.warning(f"[BGLikesHarvester] start error: {bg_e}")







    while True:



        try:



            if time.time() - last_render_ping >= render_ping_interval:



                try:



                    httpx.get("https://shopee-affiliate-bot-9e9n.onrender.com/health", timeout=20.0)



                except Exception:



                    pass



                last_render_ping = time.time()



            res = scan_and_reply_comments(limit_posts=12)



            if res.get("replied_count", 0) > 0:



                logger.info(f"💬 ตอบคอมเมนต์ลูกค้าใหม่สำเร็จ {res['replied_count']} รายการ")



            inbox_cnt = scan_and_reply_inbox_messages(limit_threads=10)



            if inbox_cnt > 0:



                logger.info(f"💌 ตอบแชท Inbox ลูกค้าใหม่สำเร็จ {inbox_cnt} รายการ")







            # ตรวจคัดกรองลูกค้าสั่งซื้อใหม่ใน direct_orders + สแกนมิจฉาชีพอัตโนมัติทุก 30 วินาที



            new_orders_screened = 0



            try:



                from order_fraud_guard import scan_and_screen_new_orders



                new_orders_screened = scan_and_screen_new_orders(notify_telegram=True)



            except Exception as ofg_err:



                logger.warning(f"[OrderFraudGuard] loop error: {ofg_err}")







            # ตรวจจับยอดกดถูกใจ / คอมเมนต์ที่เปลี่ยนแปลงแบบ Real-Time ทุก 30 วินาที



            curr_sig = _get_live_engagement_sig()



            sig_changed = bool(curr_sig and curr_sig != last_engagement_sig)



            if sig_changed or res.get("replied_count", 0) > 0 or inbox_cnt > 0 or new_orders_screened > 0:



                last_engagement_sig = curr_sig



                _trigger_realtime_crm_sheet_sync()



                if res.get("replied_count", 0) > 0 or inbox_cnt > 0:



                    _trigger_bg_likes_and_crm_sync()







            scan_and_notify_tracking_numbers()



            if time.time() - last_likes_harvest_run >= likes_harvest_interval:



                _trigger_bg_likes_and_crm_sync()



                last_likes_harvest_run = time.time()



            if time.time() - last_ads_guard_run >= ads_guard_interval:



                try:



                    from ads_report_bot import run_ads_guard



                    g_res = run_ads_guard()



                    logger.info(



                        f"🛡️ [Automated Ads Guard] checked={g_res.get('checked', 0)}, "



                        f"paused_dup={len(g_res.get('paused_duplicates', []))}, "



                        f"paused_stoploss={len(g_res.get('paused_stoploss', []))}"



                    )



                except Exception as ag_err:



                    logger.warning(f"[Automated Ads Guard] error: {ag_err}")



                last_ads_guard_run = time.time()



            if time.time() - last_ads_report_run >= ads_report_interval:



                try:



                    from ads_report_bot import send_ads_report



                    send_ads_report()



                    logger.info("📊 [Auto Ads Report] ส่งรายงานสรุปแอดและยอดขายอัตโนมัติสำเร็จ")



                except Exception as ar_err:



                    logger.warning(f"[Auto Ads Report] error: {ar_err}")



                last_ads_report_run = time.time()



            if time.time() - last_hermes_run >= hermes_interval:



                _run_hermes_learning_cycle()



                try:



                    from export_fb_custom_audience import export_custom_audience_csv



                    export_custom_audience_csv()



                except Exception:



                    pass



                last_hermes_run = time.time()



        except Exception as e:



            logger.warning(f"⚠️ Comment responder loop error: {e}")



        time.sleep(interval_seconds)











if __name__ == "__main__":



    _handlers = [logging.FileHandler(ROOT_DIR / "artifacts" / "fb_comment_responder.log", encoding="utf-8")]



    if sys.stdout is not None and getattr(sys.stdout, "name", "") != str(ROOT_DIR / "artifacts" / "fb_comment_responder.log"):



        _handlers.append(logging.StreamHandler(sys.stdout))







    logging.basicConfig(



        level=logging.INFO,



        format="[%(asctime)s] %(levelname)s: %(message)s",



        handlers=_handlers,



        force=True,



    )



    if "--daemon" in sys.argv:



        try:



            from filelock import FileLock, Timeout



            lock_path = ROOT_DIR / "artifacts" / "fb_comment_responder.lock"



            lock_path.parent.mkdir(parents=True, exist_ok=True)



            with FileLock(str(lock_path), timeout=0):



                run_comment_responder_loop(interval_seconds=25)



        except Timeout:



            logger.info("FB Comment Responder daemon is already active; skipping duplicate start.")



        except ImportError:



            run_comment_responder_loop(interval_seconds=25)



    else:



        result = scan_and_reply_comments(limit_posts=12)



        result["inbox_replied_count"] = scan_and_reply_inbox_messages(limit_threads=10)



        print(json.dumps(result, ensure_ascii=False, indent=2))



