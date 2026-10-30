# -*- coding: utf-8 -*-
"""
tools/sync_comments_sheet.py — ดึงคอมเมนต์และข้อความลูกค้าทั้งหมดจาก Facebook ทั้ง 2 เพจ + โฆษณา + Supabase ad_leads
มาวิเคราะห์จัดหมวดหมู่คำถาม (FAQ Clustering) พร้อมคำตอบมาตรฐานที่ถูกต้องตรงประเด็น 100%
แล้วอัปโหลดขึ้น Google Sheets อัตโนมัติ (และเซฟไฟล์ CSV สำรองที่ artifacts/pakhem_customer_comments_faq.csv)
"""

import csv
import io
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "tools"))
load_dotenv(ROOT_DIR / "backend" / ".env")

from fb_comment_responder import generate_comment_reply

ICT = timezone(timedelta(hours=7))
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://usqhvujqmnxqrdoovvnp.supabase.co").strip()
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or ""
).strip()


def classify_question_category(text: str) -> tuple[str, str]:
    """คืนค่า (หมวดหมู่คำถาม, คำอธิบายกลยุทธ์การตอบให้ตรงประเด็น) โดยดึงจากไฟล์ CSV แม่บท data/fish_faq_rules.csv ก่อน"""
    try:
        sys.path.insert(0, str(ROOT_DIR / "backend"))
        from app.services.fish_faq_engine import match_faq_rule
        m = match_faq_rule(text)
        if m and m.get("category"):
            return m["category"], m.get("strategy_note") or ""
    except Exception:
        pass
    t = (text or "").lower().strip()
    if any(k in t for k in ["บางบ่อ", "สุพรรณ", "ที่ไหน", "จังหวัดไหน", "ส่งจากไหน", "แหล่งไหน", "บ่อไหน"]):
        return (
            "📍 ถามแหล่งที่มา (บางบ่อ/สุพรรณ)",
            "ตอบตรงประเด็นในประโยคแรกว่าเป็น 'ปลาสลิดสุพรรณบุรีแท้ 100% (ไม่ใช่บางบ่อ)' เลี้ยงบ่อน้ำจืดธรรมชาติ ไร้กลิ่นโคลน เค็มน้อย 3% อร่อยไม่แพ้บางบ่อ",
        )
    if any(k in t for k in ["ปลาช่อน", "ปลาดุก", "ปลานิล", "ปลาทับทิม", "ปลาอินทรีย์", "มีแต่ปลาสลิด", "ปลาอื่น"]):
        return (
            "🐟 ถามหาปลาชนิดอื่น (เช่น ปลาช่อน)",
            "แจ้งชัดเจนว่าคัดทำเฉพาะ 'ปลาสลิดแดดเดียวสุพรรณแท้ ไซส์จัมโบ้ 5-7 ตัว/กก.' อย่างเดียว เพราะเนื้อหนาฟู ไม่มีก้างฝอย",
        )
    if any(k in t for k in ["กี่ตัว", "โลละกี่ตัว", "ตัวละ", "ตัวใหญ่ไหม", "ตัวใหญ่มั้ย", "ไซส์ไหน", "ขนาดไหน"]):
        return (
            "📏 ถามขนาด/จำนวนตัวต่อกิโล",
            "ตอบขนาดชัดเจน: คัดไซส์จัมโบ้ 5–7 ตัว/กก. (ชุด 500g ได้ 3–4 ตัว / ชุด 1 กก. ได้ 5–7 ตัว / ชุด 2 กก. ได้ 10–14 ตัว)",
        )
    if any(k in t for k in ["มีไข่ไหม", "มีไข่มั้ย", "ปลาไข่", "ไข่เต็มท้อง"]):
        return (
            "🥚 ถามว่ามีไข่ไหม",
            "ตอบตามจริงว่าคัดเฉพาะ 'ปลาสลิดเนื้อล้วน ไซส์จัมโบ้' ไม่ได้คัดแบบมีไข่ เพื่อให้ได้เนื้อปลาหนาฟูคุ้มน้ำหนักเต็มกิโล",
        )
    if any(k in t for k in ["ทอดมาให้ไหม", "ทอดให้ไหม", "แบบทอด", "พร้อมทาน", "ดิบหรือสุก"]):
        return (
            "🍳 ถามว่าทอดมาให้ไหม (ดิบ/สุก)",
            "ตอบชัดเจนว่าจำหน่ายเฉพาะ 'แบบดิบแดดเดียว (ต้องนำไปทอดเอง)' เพื่อให้ทอดสดใหม่กรอบนอกนุ่มในที่บ้าน",
        )
    if any(k in t for k in ["เค็มไหม", "เค็มมั้ย", "รสชาติ", "ส่วนประกอบ", "กันบูด", "เหม็นโคลน", "สาบโคลน"]):
        return (
            "🧂 ถามรสชาติ/ความเค็ม/กลิ่นโคลน",
            "ตอบจุดเด่น Clean Label: เนื้อปลา 97% + เกลือสมุทร 3% เค็มน้อยกลมกล่อม ไร้สารกันบูด ไร้กลิ่นสาบโคลน 100%",
        )
    if any(k in t for k in ["ปลายทาง", "เก็บเงินปลายทาง", "cod", "ส่งยังไง", "ต่างจังหวัด", "เสียไหม", "กี่วัน", "รถห้องเย็น", "ค่าส่ง"]):
        return (
            "🚚 ถามการจัดส่ง/เก็บเงินปลายทาง (COD)",
            "แยกชี้แจง 2 รูปแบบตามพื้นที่: 1-2 วันส่งแพ็กฟอยล์แช่แข็ง (รับ COD +20฿) / พื้นที่ไกล 3-4 วันหรือชุด 2 กก. ส่งรถห้องเย็น (โอนเงินล่วงหน้า)",
        )
    if any(k in t for k in ["1 กก", "1กก", "500g", "ครึ่งโล", "1 โล", "2 โล", "สนใจ", "ราคา", "เท่าไหร่", "รับชุด"]):
        return (
            "💰 สนใจสั่งซื้อ/ถามราคาแพ็กเกจ",
            "แจ้งโปรโมชั่น 3 ชุด (500g 390.- / 1kg 550.- / 2kg 1,090.-) พร้อมขอ ชื่อ-ที่อยู่-เบอร์โทร หรือส่งรูปหน้าซองจดหมาย",
        )
    if any(k in t for k in ["อร่อย", "น่ากิน", "น่าทาน", "ตาแชบ", "กำลังงาม", "ติดใจ"]):
        return (
            "⭐ ชมสินค้า/รีวิวความน่าทาน",
            "ขอบคุณลูกค้าอย่างอบอุ่น ตอกย้ำความสดใหม่เค็มน้อย 3% และชวนรับชุดโปรโมชั่นไปตุนติดตู้เย็น",
        )
    return (
        "💬 สอบถามทั่วไป",
        "ทักทายด้วยชื่อลูกค้า แจ้งจุดเด่นปลาสลิดสุพรรณแท้เค็มน้อย 3% และสรุปราคา 3 ชุดพร้อมช่องทางสั่งซื้อ",
    )


def _is_own_page_or_bot_text(sender_id: str, sender_name: str, msg: str) -> bool:
    if str(sender_id) in ("1307380735783361", "1323469404180656"):
        return True
    if "ป้าเข็ม" in (sender_name or ""):
        return True
    own_markers = (
        "มาตรฐานการแพ็กส่งด่วน",
        "มั่นใจความสด 100%",
        "watt29.github.io/pakhem-shop",
        "เงื่อนไขการจัดส่งและการชำระเงิน",
        'พิมพ์คำว่า "สนใจ" ตอบกลับใต้เม้นต์นี้',
        "แอด LINE สั่งด่วน",
    )
    return any(m in (msg or "") for m in own_markers)


def collect_all_comments_and_questions() -> list[dict]:
    records = []
    seen_keys = set()
    seen_comment_ids = set()
    seen_named_msgs = set()

    def _add_record(
        created_at: str,
        channel: str,
        cust_name: str,
        msg: str,
        ref_link: str,
        sender_id: str = "",
        comment_id: str = "",
    ):
        msg_clean = (msg or "").strip()
        if not msg_clean:
            return
        if _is_own_page_or_bot_text(sender_id, cust_name, msg_clean):
            return
        cid_clean = (comment_id or "").strip()
        if cid_clean and cid_clean in seen_comment_ids:
            return
        is_generic_name = (not cust_name) or cust_name.startswith("ลูกค้า")
        msg_norm = msg_clean.lower()
        if is_generic_name and msg_norm in seen_named_msgs:
            return
        dedup_key = f"{(cust_name or sender_id or '').strip().lower()}:{msg_norm}"
        if dedup_key in seen_keys:
            return
        seen_keys.add(dedup_key)
        if cid_clean:
            seen_comment_ids.add(cid_clean)
        if not is_generic_name:
            seen_named_msgs.add(msg_norm)

        cat, strategy = classify_question_category(msg_clean)
        best_reply, _ = generate_comment_reply(msg_clean, commenter_name="" if is_generic_name else cust_name)
        records.append({
            "created_at": (created_at or datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S"))[:19].replace("T", " "),
            "channel": channel,
            "customer_name": cust_name or "ลูกค้า",
            "customer_message": msg_clean,
            "category": cat,
            "strategy": strategy,
            "recommended_reply": best_reply,
            "reference_link": ref_link or "-",
        })

    # 1. ดึงจาก Supabase ad_leads ก่อน (เพราะมีชื่อลูกค้าจริงที่ถอดรหัสจาก Private Reply แล้ว)
    if SUPABASE_URL and SUPABASE_KEY:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        try:
            r = httpx.get(
                f"{SUPABASE_URL}/rest/v1/ad_leads",
                params={"select": "*", "order": "created_at.desc", "limit": 500},
                headers=headers,
                timeout=15.0,
            )
            if r.status_code == 200:
                for row in r.json():
                    plat = row.get("platform") or ""
                    if "ผู้ติดตาม" in plat or "กดถูกใจ" in plat:
                        continue
                    sender_id = str(row.get("sender_id") or "")
                    msg = (row.get("message") or "").strip()
                    cid = str(row.get("comment_id") or "")
                    _add_record(
                        created_at=str(row.get("created_at") or ""),
                        channel="คอมเมนต์เพจ Facebook" if "comment" in plat.lower() or "คอมเมนต์" in plat else "แชท Messenger Inbox",
                        cust_name=row.get("sender_name") or "ลูกค้า Facebook",
                        msg=msg,
                        ref_link=row.get("post_id") or cid,
                        sender_id=sender_id,
                        comment_id=cid,
                    )
        except Exception as e:
            print(f"[SyncComments] Supabase ad_leads fetch error: {e}")

    # 2. ดึงจากไฟล์ประวัติคอมเมนต์ในเครื่อง data/replied_fb_comments.json
    local_hist_path = ROOT_DIR / "data" / "replied_fb_comments.json"
    if local_hist_path.exists():
        try:
            hist = json.loads(local_hist_path.read_text(encoding="utf-8"))
            for cid, info in hist.items():
                if not isinstance(info, dict):
                    continue
                msg = info.get("comment_message") or info.get("inbox_message") or ""
                if not msg:
                    continue
                _add_record(
                    created_at=info.get("replied_at") or info.get("checked_at") or "",
                    channel="คอมเมนต์เพจ Facebook" if "comment_message" in info else "แชท Messenger Inbox",
                    cust_name=info.get("from_name") or "ลูกค้า Facebook",
                    msg=msg,
                    ref_link=cid,
                    sender_id=str(info.get("from_id") or ""),
                    comment_id=str(cid),
                )
        except Exception:
            pass

    # 3. กวาดสดจาก Facebook Graph API ทั้ง 2 เพจ (Posts + Videos/Reels + Ad Posts + Messenger Inbox)
    try:
        from fb_comment_responder import configured_pages, _fetch_ad_story_ids_for_page
        pages = configured_pages()
        for page in pages:
            page_id = str(page.get("id") or page.get("page_id") or "")
            page_name = page.get("name") or f"เพจ {page_id}"
            token = page.get("token") or ""
            if not page_id or not token:
                continue

            for ep in ("published_posts", "posts", "videos"):
                try:
                    fields_str = (
                        "id,description,created_time,comments.limit(100){id,message,from,created_time}"
                        if ep == "videos"
                        else "id,message,created_time,comments.limit(100){id,message,from,created_time}"
                    )
                    r_fb = httpx.get(
                        f"https://graph.facebook.com/v21.0/{page_id}/{ep}",
                        params={"access_token": token, "limit": 50, "fields": fields_str},
                        timeout=15.0,
                    )
                    if r_fb.status_code == 200:
                        for post in r_fb.json().get("data", []):
                            pid = post.get("id") or ""
                            for c in (post.get("comments") or {}).get("data", []):
                                c_from = c.get("from") or {}
                                cid = str(c.get("id") or "")
                                _add_record(
                                    created_at=c.get("created_time") or "",
                                    channel=f"คอมเมนต์เพจ Facebook ({page_name})",
                                    cust_name=c_from.get("name") or "ลูกค้าคอมเมนต์ Facebook",
                                    msg=c.get("message") or "",
                                    ref_link=f"https://www.facebook.com/{cid or pid}",
                                    sender_id=str(c_from.get("id") or ""),
                                    comment_id=cid,
                                )
                except Exception:
                    pass

            try:
                for sid in _fetch_ad_story_ids_for_page(page_id):
                    r_ad = httpx.get(
                        f"https://graph.facebook.com/v21.0/{sid}/comments",
                        params={"access_token": token, "limit": 100, "fields": "id,message,from,created_time"},
                        timeout=12.0,
                    )
                    if r_ad.status_code == 200:
                        for c in r_ad.json().get("data", []):
                            c_from = c.get("from") or {}
                            cid = str(c.get("id") or "")
                            _add_record(
                                created_at=c.get("created_time") or "",
                                channel=f"คอมเมนต์ใต้โฆษณา Ads ({page_name})",
                                cust_name=c_from.get("name") or "ลูกค้าคอมเมนต์แอด",
                                msg=c.get("message") or "",
                                ref_link=f"https://www.facebook.com/{cid or sid}",
                                sender_id=str(c_from.get("id") or ""),
                                comment_id=cid,
                            )
            except Exception:
                pass

            try:
                r_conv = httpx.get(
                    f"https://graph.facebook.com/v21.0/{page_id}/conversations",
                    params={
                        "access_token": token,
                        "limit": 50,
                        "fields": "id,link,updated_time,participants,messages.limit(20){id,message,from,created_time}",
                    },
                    timeout=15.0,
                )
                if r_conv.status_code == 200:
                    for conv in r_conv.json().get("data", []):
                        conv_link = conv.get("link") or ""
                        ref_url = f"https://www.facebook.com{conv_link}" if conv_link.startswith("/") else conv.get("id", "")
                        for m in (conv.get("messages") or {}).get("data", []):
                            m_from = m.get("from") or {}
                            from_id = str(m_from.get("id") or "")
                            if from_id == page_id:
                                continue
                            mid = str(m.get("id") or "")
                            _add_record(
                                created_at=m.get("created_time") or "",
                                channel=f"แชท Messenger Inbox ({page_name})",
                                cust_name=m_from.get("name") or "ลูกค้า Messenger",
                                msg=m.get("message") or "",
                                ref_link=ref_url,
                                sender_id=from_id,
                                comment_id=mid,
                            )
            except Exception:
                pass
    except Exception as e:
        print(f"[SyncComments] Live FB sweep error: {e}")

    # 4. ดึงจาก Supabase chat_logs (ข้อความลูกค้าใน LINE OA @137gsref)
    if SUPABASE_URL and SUPABASE_KEY:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        try:
            r_line = httpx.get(
                f"{SUPABASE_URL}/rest/v1/chat_logs",
                params={"select": "*", "order": "created_at.desc", "limit": 200},
                headers=headers,
                timeout=12.0,
            )
            if r_line.status_code == 200:
                for row in r_line.json():
                    u_msg = (row.get("user_message") or row.get("message") or "").strip()
                    if not u_msg:
                        continue
                    _add_record(
                        created_at=str(row.get("created_at") or ""),
                        channel="แชท LINE OA (@137gsref)",
                        cust_name=f"ลูกค้า LINE ({str(row.get('line_user_id') or '')[:8]})",
                        msg=u_msg,
                        ref_link="LINE_OA",
                        sender_id=str(row.get("line_user_id") or ""),
                    )
        except Exception:
            pass

    # 5. เพิ่มชุดคำถามสำคัญที่ลูกค้าถามบ่อยจากการค้นคว้าอินเทอร์เน็ต (Pantip / กลุ่มคนรักปลาสลิด) ให้ครบทุกประเด็นในชีท
    standard_faqs = [
        ("น่าทานมากค่ะปลาสลิดของบางบ่อไหมคะ", "บุญหลาย ธานี", "คอมเมนต์เพจ Facebook"),
        ("มีแต่ปลาสลิดเหรอคะปลาช่อนไม่มีเหรอ", "ใบศรี ชนะเปรื่องวิทยา", "คอมเมนต์เพจ Facebook"),
        ("กี่ตัวโลค่ะ ตัวเล็กไหม", "ธัญยานันท์ คณาชัยวิรัตน์", "แชท Messenger Inbox"),
        ("สั่งวันนี้ส่งวันไหนคะ กี่วันได้ของ ส่งจากจังหวัดอะไร", "คำถามการจัดส่ง (Shipping FAQ)", "คำถามพบบ่อยเรื่องการส่งสินค้า"),
        ("ค่าส่งเท่าไหร่คะ ส่งฟรีไหม มีเก็บเงินปลายทางไหม", "คำถามการจัดส่ง (Shipping FAQ)", "คำถามพบบ่อยเรื่องการส่งสินค้า"),
        ("ส่งของยังไง อยู่ต่างจังหวัดไกลๆ กลัวปลาเสียระหว่างทาง มีรถห้องเย็นไหม", "Nattaseth Chalayonnawin", "แชท Messenger Inbox"),
        ("เค็มไหมคะ กลัวเค็มปี๋หรือเหม็นตุ มีสารกันบูดไหม", "คำถามยอดฮิตจาก Pantip (FAQ)", "คำถามพบบ่อยบนอินเทอร์เน็ต"),
        ("มีไข่ไหมคะ หรือเป็นปลาเนื้อล้วน", "คำถามยอดฮิตจาก Pantip (FAQ)", "คำถามพบบ่อยบนอินเทอร์เน็ต"),
        ("ขอดเกล็ด ตัดหัว ควักไส้ให้หรือยัง ชั่งน้ำหนักก่อนหรือหลังตัดหัวคะ", "คำถามยอดฮิตจาก Pantip (FAQ)", "คำถามพบบ่อยบนอินเทอร์เน็ต"),
        ("ทอดมาให้พร้อมทานไหมคะ หรือเป็นแบบดิบ", "คำถามยอดฮิตจาก Pantip (FAQ)", "คำถามพบบ่อยบนอินเทอร์เน็ต"),
        ("วิธีทอดยังไงไม่ให้ติดกระทะ ใช้หม้อทอดไร้น้ำมันไฟเท่าไหร่ กี่นาทีคะ", "คำถามยอดฮิตจาก Wongnai/Pantip (FAQ)", "คำถามพบบ่อยบนอินเทอร์เน็ต"),
        ("เก็บในตู้เย็นได้นานไหมคะ แช่ช่องฟรีซอยู่ได้กี่เดือน", "คำถามยอดฮิตจาก Pantip (FAQ)", "คำถามพบบ่อยบนอินเทอร์เน็ต"),
        ("สั่งยังไงคะ กดสั่งไม่เป็น ต้องแจ้งอะไรบ้าง", "คำถามขั้นตอนการสั่งซื้อ (Order FAQ)", "คำถามที่ลูกค้ามักไม่เข้าใจการสั่งซื้อ"),
        ("ขอเบอร์โทรร้านหน่อยค่ะ โทรสั่งได้ไหม หรือให้ร้านโทรกลับได้ไหม", "คำถามขั้นตอนการสั่งซื้อ (Order FAQ)", "คำถามที่ลูกค้ามักไม่เข้าใจการสั่งซื้อ"),
        ("ขอเลขบัญชีโอนเงินหน่อยค่ะ ชื่อบัญชีนายจีรวัฒน์ใช่ของเพจป้าเข็มไหม โอนแล้วส่งสลิปตรงไหน", "คำถามการชำระเงิน (Payment FAQ)", "คำถามที่ลูกค้ามักไม่เข้าใจการสั่งซื้อ"),
        ("ทำไมชุด 2 กิโล 1,090 บาท ถึงไม่มีเก็บเงินปลายทางคะ", "คำถามการชำระเงิน (Payment FAQ)", "คำถามที่ลูกค้ามักไม่เข้าใจการสั่งซื้อ"),
        ("มีหน้าร้านไหมคะ แวะไปซื้อเองหรือนัดรับได้ไหม ร้านอยู่ตรงไหน", "คำถามขั้นตอนการสั่งซื้อ (Order FAQ)", "คำถามที่ลูกค้ามักไม่เข้าใจการสั่งซื้อ"),
        ("สั่งไปแล้วเช็คเลขพัสดุยังไงคะ ส่งของหรือยัง ถ้าจะแก้ที่อยู่ต้องทำยังไง", "คำถามหลังการสั่งซื้อ (Tracking FAQ)", "คำถามที่ลูกค้ามักไม่เข้าใจการสั่งซื้อ"),
    ]
    for q_msg, q_name, q_chan in standard_faqs:
        if any(q_msg in r["customer_message"] for r in records):
            continue
        _add_record(
            created_at=datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S"),
            channel=q_chan,
            cust_name=q_name,
            msg=q_msg,
            ref_link="FAQ_STANDARD",
        )

    return records


def sync_to_google_drive_sheet(records: list[dict]) -> str:
    """สร้างหรืออัปเดต Google Sheet 'คลังรวมคอมเมนต์ลูกค้า & คำตอบมาตรฐาน ป้าเข็ม' และคืนค่า URL"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ""
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/system_preferences",
        params={"key": "eq.google_drive_sheet_sync", "select": "value"},
        headers=headers,
        timeout=10.0,
    )
    if r.status_code != 200 or not r.json():
        return ""
    cfg = json.loads(r.json()[0]["value"]) if isinstance(r.json()[0]["value"], str) else r.json()[0]["value"]
    token_res = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": cfg["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=10.0,
    )
    if token_res.status_code != 200:
        return ""
    access_token = token_res.json().get("access_token")
    if not access_token:
        return ""

    # เช็กว่ามี Sheet ID เก็บไว้หรือยัง
    pref_sheet = httpx.get(
        f"{SUPABASE_URL}/rest/v1/system_preferences",
        params={"key": "eq.comments_faq_sheet_id", "select": "value"},
        headers=headers,
        timeout=10.0,
    )
    sheet_id = ""
    if pref_sheet.status_code == 200 and pref_sheet.json():
        sheet_id = (pref_sheet.json()[0].get("value") or "").strip()

    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow([
        "ลำดับ",
        "วัน-เวลา",
        "ช่องทาง",
        "ชื่อลูกค้า",
        "ข้อความ/คำถามจากลูกค้า",
        "หมวดหมู่การวิเคราะห์ (Intent)",
        "แนวทางคำตอบที่ตรงประเด็น",
        "คำตอบมาตรฐานของบอทป้าเข็ม (อัปเดตล่าสุด)",
        "ลิงก์อ้างอิง",
    ])
    for idx, rec in enumerate(records, 1):
        writer.writerow([
            idx,
            rec["created_at"],
            rec["channel"],
            rec["customer_name"],
            rec["customer_message"],
            rec["category"],
            rec["strategy"],
            rec["recommended_reply"],
            rec["reference_link"],
        ])
    csv_bytes = buf.getvalue().encode("utf-8")

    # บันทึกไฟล์ CSV ลงเครื่องด้วย
    local_csv = ROOT_DIR / "artifacts" / "pakhem_customer_comments_faq.csv"
    local_csv.parent.mkdir(parents=True, exist_ok=True)
    local_csv.write_bytes(csv_bytes)

    drive_headers = {"Authorization": f"Bearer {access_token}"}
    if sheet_id:
        patch_res = httpx.patch(
            f"https://www.googleapis.com/upload/drive/v3/files/{sheet_id}?uploadType=media",
            headers={**drive_headers, "Content-Type": "text/csv; charset=utf-8"},
            content=csv_bytes,
            timeout=20.0,
        )
        if patch_res.status_code == 200:
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    # สร้าง Google Sheet ใหม่
    boundary = "pakhem_sheet_boundary_2026"
    metadata = {
        "name": "🐟 คลังรวมคอมเมนต์ลูกค้า & วิเคราะห์คำตอบตรงประเด็น (ปลาสลิดป้าเข็ม)",
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata, ensure_ascii=False)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/csv; charset=UTF-8\r\n\r\n"
    ).encode("utf-8") + csv_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    create_res = httpx.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        headers={
            **drive_headers,
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        content=body,
        timeout=20.0,
    )
    if create_res.status_code in (200, 201):
        new_id = create_res.json().get("id")
        if new_id:
            # เปิดสิทธิ์อ่านได้ทุกคนที่มีลิงก์
            httpx.post(
                f"https://www.googleapis.com/drive/v3/files/{new_id}/permissions",
                headers={**drive_headers, "Content-Type": "application/json"},
                json={"role": "reader", "type": "anyone"},
                timeout=10.0,
            )
            # บันทึก Sheet ID ลง Supabase
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/system_preferences",
                headers={
                    **headers,
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                json={"key": "comments_faq_sheet_id", "value": new_id},
                timeout=10.0,
            )
            return f"https://docs.google.com/spreadsheets/d/{new_id}/edit"
    return ""


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    recs = collect_all_comments_and_questions()
    url = sync_to_google_drive_sheet(recs)
    print(f"Synced {len(recs)} records.")
    print(f"Google Sheet URL: {url}")
