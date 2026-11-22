# -*- coding: utf-8 -*-



"""



backend/app/services/fish_cloud_worker.py — ระบบสายตรวจเฝ้าเพจปลาสลิดแดดเดียวป้าเข็มบน Render Cloud 24/7



แยกหน้าที่ชัดเจนจากสคริปต์ GAS (shopee_pakhem_bot.gs):



- GAS รับผิดชอบ: LINE OA Webhook, หน้าเว็บสั่งซื้อ Direct Checkout (fish.html), ตรวจสลิป AI, และ FB Messenger ด่านแรก (ทันที 1 วินาที)



- Render รับผิดชอบ (24/7 Cloud Background Loop):



  1. กวาดคอมเมนต์ใต้คลิปแอด/โพสต์ Facebook ทั้ง 2 เพจ (หากคอมที่บ้านปิดหรือเกิน 30 วินาทีแล้วยังไม่ตอบ Render ตอบเม้นต์ + ทักแชททันที)



  2. ปักหมุด First Comment + รูปโปสเตอร์เงื่อนไขการจัดส่งรับประกันความสด ใต้คลิปปลาสลิดใหม่ที่ยังไม่มีคอมเมนต์แรก



  3. ด่านสำรองตรวจแชท Inbox Facebook ที่ค้างเกิน 45 วินาที (กรณี Webhook ตกหล่น)



  4. รันสมองกล Hermes AI วิเคราะห์ยอดขายปลาสลิด (direct_orders) ทุก 6 ชั่วโมง



"""







import asyncio



import json



import logging



import os



import re



from datetime import datetime, timezone, timedelta



import httpx

from app.services.sales_status import closed_notice, is_sales_closed, mask_sales_text
from app.services.fb_chat_only import build_friendly_chat_reply, is_fb_chat_only_mode



from app.services.thai_address_validator import (



    build_incomplete_order_guidance,



    enrich_thai_address,



    has_complete_thai_address,



    normalize_thai_digits,



    validate_thai_phone,



)







logger = logging.getLogger("FishCloudWorker")



ICT = timezone(timedelta(hours=7))







WEB_STORE_URL = "https://watt29.github.io/pakhem-shop/fish.html"



MAIN_SHOP_URL = "https://watt29.github.io/pakhem-shop/"



LINE_OA_URL = "https://lin.ee/o9Kjp1N"



COLD_PACK_POSTER_URL = "https://usqhvujqmnxqrdoovvnp.supabase.co/storage/v1/object/public/slips/cold_pack_poster.png"







# In-memory cache on Render container (backed by real-time Facebook Graph API sub_comments check)



_REPLIED_CACHE: dict[str, dict] = {}











def _get_supabase_config() -> tuple[str, str]:



    url = os.getenv("SUPABASE_URL", "https://usqhvujqmnxqrdoovvnp.supabase.co").strip()



    key = (



        os.getenv("SUPABASE_SERVICE_ROLE_KEY")



        or os.getenv("SUPABASE_KEY")



        or os.getenv("SUPABASE_ANON_KEY")



        or ""



    ).strip()



    return url, key











def _send_line_admin_alert(text_msg: str) -> bool:



    line_token = (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()



    admin_uid = (os.getenv("ADMIN_LINE_UID") or "Uc88eb3896b0e4bcc5fbaa9b78ac1294e").strip()



    if not line_token or not admin_uid:



        return False



    try:



        r = httpx.post(



            "https://api.line.me/v2/bot/message/push",



            headers={



                "Content-Type": "application/json",



                "Authorization": f"Bearer {line_token}",



            },



            json={



                "to": admin_uid,



                "messages": [{"type": "text", "text": text_msg[:5000]}],



            },



            timeout=10.0,



        )



        return r.status_code == 200



    except Exception as e:



        logger.warning(f"[FishCloudWorker] LINE admin alert failed: {e}")



        return False











def _send_telegram_alert(text_msg: str) -> bool:



    # แจ้งเตือนเข้า LINE แอดมินด้วยหากเป็นออเดอร์สำคัญ



    if any(k in text_msg for k in ["ออเดอร์", "สลิป", "โอนเงิน", "ทิ้งเบอร์", "ที่อยู่จัดส่ง", "สร้างออเดอร์"]):



        try:



            _send_line_admin_alert(text_msg)



        except Exception:



            pass



    bot_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()



    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "6734965582").strip()



    if not bot_token or not chat_id:



        return False



    try:



        r = httpx.post(



            f"https://api.telegram.org/bot{bot_token}/sendMessage",



            json={



                "chat_id": chat_id,



                "text": text_msg,



                "disable_web_page_preview": True,



            },



            timeout=10.0,



        )



        return r.status_code == 200



    except Exception as e:



        logger.warning(f"[FishCloudWorker] Telegram alert failed: {e}")



        return False











def _configured_fb_pages() -> list[dict]:



    pages = []



    p1_id = (os.getenv("FACEBOOK_PAGE_ID") or "1307380735783361").strip()



    p1_token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()



    if p1_id and p1_token:



        pages.append({"id": p1_id, "name": "ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้ (เพจ 1)", "token": p1_token})







    p2_id = (os.getenv("FACEBOOK_PAGE_2_ID") or "1323469404180656").strip()



    p2_token = (os.getenv("FACEBOOK_PAGE_2_ACCESS_TOKEN") or "").strip()



    if p2_id and p2_token:



        pages.append({"id": p2_id, "name": "ครัวแม่บ้าน ชี้เป้าของอร่อย (เพจ 2)", "token": p2_token})



    return pages











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














def _get_pending_slip_from_supabase(sender_id: str) -> dict | None:



    if not sender_id:



        return None



    sb_url, sb_key = _get_supabase_config()



    if not sb_url or not sb_key:



        return None



    try:



        headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}



        r = httpx.get(



            f"{sb_url}/rest/v1/system_preferences",



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



    if not sender_id:



        return



    sb_url, sb_key = _get_supabase_config()



    if not sb_url or not sb_key:



        return



    try:



        headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}



        httpx.delete(



            f"{sb_url}/rest/v1/system_preferences",



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



    sb_url, sb_key = _get_supabase_config()



    if not sb_url or not sb_key:



        return False



    try:



        headers = {



            "apikey": sb_key,



            "Authorization": f"Bearer {sb_key}",



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



            f"{sb_url}/rest/v1/ad_leads",



            headers=headers,



            json=payload,



            timeout=8.0,



        )



        return r.status_code in (200, 201)



    except Exception as e:



        logger.warning(f"[FishCloudWorker] supabase ad_leads save failed: {e}")



        return False











def generate_comment_reply(comment_text: str, commenter_name: str = "", sender_id: str = "") -> tuple[str, dict | None]:

    """ตอบคอมเมนต์แบบปิดรับออเดอร์ (ไม่มีราคา/แพ็กเกจ)."""
    return closed_notice(), None











def generate_private_offer_message(comment_text: str, commenter_name: str = "") -> str:

    """ร้านยุติการจำหน่ายแล้ว — ไม่มีข้อเสนอ/ราคาทางแชท."""
    return closed_notice()











def _reply_to_fb_comment(



    comment_id: str,



    message: str,



    token: str,



    page_id: str = "",



    private_message: str = "",



) -> dict:



    message = mask_sales_text(message)
    try:



        httpx.post(



            f"https://graph.facebook.com/v21.0/{comment_id}/likes",



            params={"access_token": token},



            timeout=8.0,



        )



    except Exception:



        pass







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



            public_error = f"HTTP {r.status_code}: {r.text[:200]}"



    except Exception as e:



        public_error = str(e)







    private_ok = False



    private_error = ""



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



            else:



                private_error = f"HTTP {pr.status_code}: {pr.text[:200]}"



        except Exception as e:



            private_error = str(e)







    return {



        "ok": public_ok,



        "data": public_data,



        "error": public_error,



        "private_reply_ok": private_ok,



        "private_reply_error": private_error,



    }











def run_fish_cloud_scan_cycle(limit_posts: int = 10) -> dict:



    """



    รัน 1 รอบบน Render Cloud:



    - ตรวจคลิป/โพสต์ปลาสลิดที่อายุเกิน 45 วินาทีแต่ยังไม่มี First Comment -> ปักหมุดให้ทันที



    - ตรวจคอมเมนต์ลูกค้าที่อายุเกิน 30 วินาทีแต่ยังไม่มีคำตอบจากเพจ -> ตอบกลับ + ทักแชท Inbox ทันที



    - ตรวจแชท Inbox ที่อายุเกิน 45 วินาทีแต่ GAS Webhook ยังไม่ได้ตอบ -> ตอบกลับแทนทันที



    """



    pages = _configured_fb_pages()



    if not pages:



        return {"ok": False, "reason": "no_fb_pages_configured"}







    replied_comments = 0



    first_comments = 0



    inbox_replied = 0







    for page in pages:



        page_id = page["id"]



        page_name = page["name"]



        token = page["token"]







        items_to_scan = []



        seen_ids = set()



        for endpoint, msg_field in [



            ("live_videos", "description"),



            ("video_reels", "description"),



            ("videos", "description"),



            ("published_posts", "message"),



        ]:



            try:



                time_field = "creation_time" if endpoint == "live_videos" else "created_time"



                r = httpx.get(



                    f"https://graph.facebook.com/v21.0/{page_id}/{endpoint}",



                    params={



                        "access_token": token,



                        "limit": limit_posts,



                        "fields": f"id,{msg_field},{time_field},comments.limit(40){{id,from,message,attachment,created_time,comments.limit(15){{id,from,message}}}}",



                    },



                    timeout=15.0,



                )



                if r.status_code == 200:



                    for obj in r.json().get("data", []):



                        oid = obj.get("id", "")



                        if oid and oid not in seen_ids:



                            seen_ids.add(oid)



                            items_to_scan.append({



                                "id": oid,



                                "created_time": obj.get("created_time") or obj.get("creation_time") or "",



                                "message": obj.get(msg_field) or "",



                                "comments": (obj.get("comments") or {}).get("data", []),



                            })



            except Exception as e:



                logger.warning(f"[FishCloudWorker] fetch {endpoint} failed ({page_name}): {e}")







        pinned_sigs = set()



        for post in items_to_scan:



            sig = f"{page_id}:{(post.get('message') or '')[:80].strip()}"



            pid = post.get("id", "")



            if f"fc_{pid}" in _REPLIED_CACHE:



                pinned_sigs.add(sig)



                continue



            for c in post.get("comments", []):



                ct = c.get("message") or ""



                c_from = str((c.get("from") or {}).get("id") or "")



                if "watt29.github.io/pakhem-shop" in ct:



                    pinned_sigs.add(sig)



                    _REPLIED_CACHE[f"fc_{pid}"] = {"exists": True}



                    break







        for post in items_to_scan:



            post_id = post.get("id", "")



            post_msg = post.get("message", "")



            comments_data = post.get("comments", [])



            sig = f"{page_id}:{post_msg[:80].strip()}"







            # 1) ปักหมุด First Comment + รูปโปสเตอร์เงื่อนไขการจัดส่ง หากโพสต์อายุเกิน 45 วินาทีแล้วยังไม่มี



            is_fish_post = any(k in post_msg for k in ("ปลาสลิด", "ปลาแดดเดียว", "fish.html"))



            if is_fish_post and f"fc_{post_id}" not in _REPLIED_CACHE and sig not in pinned_sigs:



                post_age_ok = True



                try:



                    dt_p = datetime.strptime(post.get("created_time") or "", "%Y-%m-%dT%H:%M:%S%z")



                    if (datetime.now(timezone.utc) - dt_p).total_seconds() < 45:



                        post_age_ok = False



                except Exception:



                    pass



                if post_age_ok and not is_fb_chat_only_mode():



                    try:



                        fc_res = httpx.post(



                            f"https://graph.facebook.com/v21.0/{post_id}/comments",



                            data={"message": build_fish_first_comment(), "access_token": token},



                            timeout=15.0,



                        )



                        if fc_res.status_code == 200:



                            httpx.post(



                                f"https://graph.facebook.com/v21.0/{post_id}/comments",



                                data={



                                    "message": build_fish_guarantee_comment(),



                                    "attachment_url": COLD_PACK_POSTER_URL,



                                    "access_token": token,



                                },



                                timeout=20.0,



                            )



                            _REPLIED_CACHE[f"fc_{post_id}"] = {"posted": True}



                            pinned_sigs.add(sig)



                            first_comments += 1



                            logger.info(f"📌 [RenderCloud] ปักหมุดเม้นต์แรกใต้คลิป {post_id} สำเร็จ")



                    except Exception as e:



                        logger.warning(f"[FishCloudWorker] first comment error ({post_id}): {e}")







            # 2) ตอบคอมเมนต์ลูกค้าที่อายุเกิน 30 วินาทีและยังไม่มีคำตอบจากเพจ



            for c in comments_data:



                cid = c.get("id", "")



                c_msg = (c.get("message") or "").strip()



                has_att = bool(c.get("attachment"))



                c_from = c.get("from") or {}



                from_id = str(c_from.get("id") or "")



                from_name = (c_from.get("name") or "").strip()



                created_str = c.get("created_time") or ""







                if not cid or (not c_msg and not has_att):



                    continue



                if not c_msg and has_att:



                    c_msg = "[ส่งสติกเกอร์/รูปภาพสนใจสินค้า]"







                if (



                    from_id == page_id



                    or "ป้าเข็ม" in from_name



                    or "มาตรฐานการแพ็กส่งด่วน" in c_msg



                    or "มั่นใจความสด 100%" in c_msg



                    or "watt29.github.io/pakhem-shop" in c_msg



                ):



                    _REPLIED_CACHE[cid] = {"own": True}



                    continue







                if cid in _REPLIED_CACHE or cid in seen_comment_ids_in_cycle:



                    continue



                seen_comment_ids_in_cycle.add(cid)







                # รอ 90 วินาทีให้คอมที่บ้าน (ถ้าเปิดอยู่) ตอบและให้ Facebook CDN อัปเดตก่อน เพื่อป้องกันการตอบชนกัน 100%



                try:



                    dt_c = datetime.strptime(created_str, "%Y-%m-%dT%H:%M:%S%z")



                    if (datetime.now(timezone.utc) - dt_c).total_seconds() < 90:



                        continue



                except Exception:



                    pass







                sub_comments = (c.get("comments") or {}).get("data", [])



                already_replied = False



                for sub in sub_comments:



                    sub_from = sub.get("from") or {}



                    sub_msg = sub.get("message") or ""



                    if (



                        str(sub_from.get("id") or "") == page_id



                        or "ป้าเข็ม" in (sub_from.get("name") or "")



                        or "watt29.github.io/pakhem-shop" in sub_msg



                    ):



                        already_replied = True



                        break



                if already_replied:



                    _REPLIED_CACHE[cid] = {"replied_on_fb": True}



                    continue







                reply_text, order_info = generate_comment_reply(c_msg, from_name, sender_id=from_id)



                priv_text = generate_private_offer_message(c_msg, from_name)



                res = _reply_to_fb_comment(cid, reply_text, token, page_id, priv_text)



                if res.get("ok"):



                    _REPLIED_CACHE[cid] = {"replied": True}



                    replied_comments += 1



                    priv_ok = bool(res.get("private_reply_ok"))



                    _save_comment_lead_to_supabase(



                        sender_id=from_id,



                        sender_name=from_name,



                        phone=(order_info or {}).get("phone", ""),



                        message=c_msg,



                        post_id=post_id,



                        comment_id=cid,



                        intent="order" if order_info else "comment",



                        private_replied=priv_ok,



                    )



                    now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")



                    _send_telegram_alert(



                        f"☁️💬 [Render Cloud 24/7 ตอบคอมเมนต์ + ทักแชทลูกค้าสำเร็จ!] ✅\n"



                        f"━━━━━━━━━━━━━━━━━━━━━━\n"



                        f"🏠 เพจ: {page_name}\n"



                        f"👤 ลูกค้า: {from_name or 'ผู้ใช้งาน Facebook'}\n"



                        f"❓ คอมเมนต์: \"{c_msg}\"\n"



                        f"💌 ทัก Inbox: {'สำเร็จ ✅' if priv_ok else 'ตอบใต้โพสต์'}\n"



                        f"⏰ เวลา: {now_str} น."



                    )







        # 3) ด่านสำรองตรวจแชท Inbox Facebook ที่ค้างเกิน 45 วินาที (หลัง GAS Webhook)



        try:



            ir = httpx.get(



                f"https://graph.facebook.com/v21.0/{page_id}/conversations",



                params={



                    "access_token": token,



                    "limit": 8,



                    "fields": "id,updated_time,messages.limit(6){id,message,from,created_time}",



                },



                timeout=15.0,



            )



            if ir.status_code == 200:



                for t in ir.json().get("data", []):



                    msgs = (t.get("messages") or {}).get("data", [])



                    if not msgs:



                        continue



                    latest = None



                    for m_item in msgs:



                        cand_text = (m_item.get("message") or "").strip()



                        cand_from_id = str((m_item.get("from") or {}).get("id") or "")



                        if not cand_text:



                            if cand_from_id == page_id:



                                latest = m_item



                                break



                            continue



                        if cand_from_id == page_id and (



                            cand_text.endswith("ตอบกลับโฆษณา")



                            or "สนใจรับปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม ชุดไหนดีคะ" in cand_text



                            or 'ข้อความนี้ถูกย้ายไปยัง "สแปม"' in cand_text



                            or "Messenger automatically created" in cand_text



                            or "คุณกำลังตอบกลับความคิดเห็น" in cand_text



                        ):



                            continue



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







                    if from_id == page_id or "ป้าเข็ม" in from_name:



                        continue



                    if not mid or not m_text or not from_id:



                        continue



                    if mid in _REPLIED_CACHE:



                        continue







                    try:



                        dt_m = datetime.strptime(created_str, "%Y-%m-%dT%H:%M:%S%z")



                        age_sec = (datetime.now(timezone.utc) - dt_m).total_seconds()



                        # รอ 45 วินาทีให้สคริปต์ GAS Webhook และคอมที่บ้านตอบก่อน



                        if age_sec < 45:



                            continue



                        if age_sec > 86400:



                            _REPLIED_CACHE[mid] = {"old": True}



                            continue



                    except Exception:



                        continue







                    reply_text, order_info = generate_comment_reply(m_text, from_name, sender_id=from_id)
                    is_postpone_reply = is_fb_chat_only_mode() or ("แชทนี้บันทึกไว้ให้แล้ว" in reply_text)

                    qr_buttons = None if is_postpone_reply else [
                        {"content_type": "text", "title": "ชุด 500g", "payload": "QR_PKG_500G"},
                        {"content_type": "text", "title": "ชุด 1 กก.", "payload": "QR_PKG_1KG"},
                        {"content_type": "text", "title": "ชุด 2 กก.", "payload": "QR_PKG_2KG"},
                        {"content_type": "text", "title": "เลขบัญชีธนาคาร", "payload": "QR_BANK_INFO"},
                    ]

                    msg_payload = {"text": reply_text}
                    if qr_buttons:
                        msg_payload["quick_replies"] = qr_buttons

                    # ส่งข้อความตัวอักษรแบบกระชับ 3 บรรทัด + Quick Reply (ข้อความไม่โดนตัดบนมือถือ 100% และไม่ส่งซ้ำสองเด้ง)
                    sr = httpx.post(
                        f"https://graph.facebook.com/v21.0/{page_id}/messages",
                        params={"access_token": token},
                        json={
                            "recipient": {"id": from_id},
                            "messaging_type": "RESPONSE",
                            "message": msg_payload,
                        },
                        timeout=12.0,
                    )



                    if sr.status_code != 200:



                        sr = httpx.post(



                            f"https://graph.facebook.com/v21.0/{page_id}/messages",



                            params={"access_token": token},



                            json={"recipient": {"id": from_id}, "message": {"text": reply_text}},



                            timeout=12.0,



                        )



                    if sr.status_code == 200:



                        _REPLIED_CACHE[mid] = {"replied": True}



                        inbox_replied += 1



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



                        now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")



                        _send_telegram_alert(



                            f"☁️💌 [Render Cloud 24/7 ตอบแชท Inbox สำรองเพจ {page_name}!] ✅\n"



                            f"👤 ลูกค้า: {from_name}\n"



                            f"💬 ข้อความ: \"{m_text}\"\n"



                            f"⏰ เวลา: {now_str} น."



                        )



        except Exception as e:



            logger.warning(f"[FishCloudWorker] inbox scan error ({page_name}): {e}")







    return {



        "ok": True,



        "replied_comments": replied_comments,



        "first_comments": first_comments,



        "inbox_replied": inbox_replied,



    }











async def fish_cloud_worker_loop(interval_seconds: int = 35):



    """ลูปสายตรวจเฝ้าเพจปลาสลิดแดดเดียวบน Render 24/7 (ทุก 35 วินาที)"""



    logger.info(f"🐟 [FishCloudWorker] เริ่มระบบสายตรวจเฝ้าเพจปลาสลิด 24/7 (ทุก {interval_seconds} วินาที)")



    while True:



        try:



            res = await asyncio.to_thread(run_fish_cloud_scan_cycle, 10)



            if res.get("replied_comments") or res.get("first_comments") or res.get("inbox_replied"):



                logger.info(f"🐟 [FishCloudWorker] cycle result: {res}")



        except Exception as e:



            logger.warning(f"[FishCloudWorker] loop error: {e}")



        await asyncio.sleep(interval_seconds)











async def fish_hermes_analytics_loop(interval_seconds: int = 21600):



    """ลูปสมองกล Hermes AI วิเคราะห์ยอดขายปลาสลิด (direct_orders) ทุก 6 ชั่วโมงบน Render"""



    logger.info("🧠 [FishCloudWorker] เริ่มระบบ Hermes AI วิเคราะห์ยอดขายปลาสลิดทุก 6 ชั่วโมง")



    while True:



        await asyncio.sleep(60)  # รอ 1 นาทีแรกหลังตื่นก่อนรันรอบแรก



        try:



            from app.db import SessionLocal



            from app.services.hermes_brain import run_hermes_cycle



            def _run():



                db = SessionLocal()



                try:



                    return run_hermes_cycle(db)



                finally:



                    db.close()



            res = await asyncio.to_thread(_run)



            logger.info(f"🧠 [FishCloudWorker] Hermes AI fish analytics completed: {res.get('fish_orders')}")



        except Exception as e:



            logger.warning(f"[FishCloudWorker] Hermes loop error: {e}")



        await asyncio.sleep(interval_seconds)











def run_fish_cloud_ads_guard_cycle() -> dict:



    """ตรวจเช็คงบโฆษณา Facebook Ads บน Render Cloud ทุก 4 ชั่วโมง:



    หากพบแคมเปญซ้ำซ้อน หรือแอดที่ใช้งบเกิน 150 บาทแต่ CPC แพงผิดปกติ (>15 บาท) สั่งพักแอดอัตโนมัติและแจ้ง Telegram"""



    ad_account = (os.getenv("FACEBOOK_AD_ACCOUNT_ID") or "act_294446695507241").strip()



    ads_token = (os.getenv("FACEBOOK_ADS_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()



    page_token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()



    if not ad_account or not ads_token:



        return {"ok": False, "reason": "no_ads_token"}



    try:



        r = httpx.get(



            f"https://graph.facebook.com/v21.0/{ad_account}/campaigns",



            params={



                "access_token": ads_token,



                "fields": "id,name,status,daily_budget,insights.date_preset(last_7d){spend,clicks,cpc,ctr}",



            },



            timeout=15.0,



        )



        if r.status_code != 200 and page_token and page_token != ads_token:



            ads_token = page_token



            r = httpx.get(



                f"https://graph.facebook.com/v21.0/{ad_account}/campaigns",



                params={



                    "access_token": ads_token,



                    "fields": "id,name,status,daily_budget,insights.date_preset(last_7d){spend,clicks,cpc,ctr}",



                },



                timeout=15.0,



            )



        if r.status_code != 200:



            return {"ok": False, "status_code": r.status_code}



        camps = (r.json() or {}).get("data", [])



        active = [c for c in camps if c.get("status") == "ACTIVE"]



        paused_actions = []



        seen_names = set()



        for c in active:



            cid = c.get("id")



            cname = (c.get("name") or "")[:40]



            ins = ((c.get("insights") or {}).get("data") or [{}])[0]



            spend = float(ins.get("spend") or 0.0)



            cpc = float(ins.get("cpc") or 0.0)



            reason = None



            if cname in seen_names:



                reason = "แคมเปญซ้ำซ้อน (Duplicate Active Campaign)"



            elif spend >= 150.0 and cpc > 15.0:



                reason = f"ใช้งบ {spend:.0f}฿ แต่ CPC แพงเกินเกณฑ์ ({cpc:.2f}฿/คลิก)"



            seen_names.add(cname)



            if reason and cid:



                pr = httpx.post(



                    f"https://graph.facebook.com/v21.0/{cid}",



                    params={"access_token": ads_token},



                    data={"status": "PAUSED"},



                    timeout=10.0,



                )



                if pr.status_code == 200:



                    paused_actions.append(f"• {cname} ({cid}) -> หยุดแอดเพราะ: {reason}")



        if paused_actions:



            now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")



            _send_telegram_alert(



                f"☁️🛡️ [Render Cloud 24/7 — บอทคุมงบแอดสั่งพักโฆษณาอัตโนมัติ!]\n"



                f"⏰ เวลา: {now_str} น.\n"



                + "\n".join(paused_actions)



            )



        return {"ok": True, "active_campaigns": len(active), "paused": len(paused_actions)}



    except Exception as e:



        logger.warning(f"[FishCloudWorker] ads guard error: {e}")



        return {"ok": False, "error": str(e)}











async def fish_ads_guard_loop(interval_seconds: int = 14400):



    """ลูปบอทคุมงบโฆษณา Facebook Ads ทุก 4 ชั่วโมงบน Render Cloud"""



    logger.info("🛡️ [FishCloudWorker] เริ่มระบบบอทคุมงบแอด Facebook ทุก 4 ชั่วโมง")



    while True:



        await asyncio.sleep(120)



        try:



            res = await asyncio.to_thread(run_fish_cloud_ads_guard_cycle)



            logger.info(f"🛡️ [FishCloudWorker] Ads guard result: {res}")



        except Exception as e:



            logger.warning(f"[FishCloudWorker] Ads guard loop error: {e}")



        await asyncio.sleep(interval_seconds)



