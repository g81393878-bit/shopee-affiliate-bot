# -*- coding: utf-8 -*-
"""standalone_content_generator.py — เครื่องมือผลิตคลิปคอนเทนต์เพียวๆ 100% แยกเด็ดขาดจากสินค้า

รองรับ 5 เสาหลักคอนเทนต์เพียวๆ (ไม่ขายสินค้า / ไม่เอารูปสินค้า Shopee มาใส่):
1. 🌟 ตามรอยคนดัง & ไวรัล (20% - 4/20)
2. 📰 ข่าวด่วนจาก RSS จริง 100% (15% - 3/20)
3. 🔮 เลขเด็ด & สายมูเสริมดวง (15% - 3/20)
4. 💡 ทริคแม่บ้านแก้ปัญหาจริง (15% - 3/20)
5. 💼 ทริคคนทำงาน & มนุษย์เงินเดือน (5% - 1/20)
"""
import html
import json
import logging
import os
import random
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import httpx
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
REELS_DIR = ROOT_DIR / "reels_uploader"
TOOLS_DIR = ROOT_DIR / "tools"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REELS_DIR))

logger = logging.getLogger(__name__)

PENDING_DIR = REELS_DIR / "pending_videos"
POSTED_DIR = REELS_DIR / "posted"
TEMP_DIR = REELS_DIR / "temp_frames"
PENDING_DIR.mkdir(parents=True, exist_ok=True)
POSTED_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

import auto_product_reels
FONT_BOLD, FONT_REG = auto_product_reels._resolve_fonts()

def get_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    return auto_product_reels.get_font(font_path, size)

def get_groq_client():
    """สร้าง OpenAI client สำหรับ Groq API แบบ multi-key failover"""
    groq_keys = os.getenv("GROQ_API_KEY", "").split(",")
    for k in groq_keys:
        k = k.strip()
        if not k or "mock" in k.lower():
            continue
        try:
            from openai import OpenAI
            return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k, timeout=10.0)
        except Exception:
            continue
    return None

def clean_render_text(text: str) -> str:
    """ลบอิโมจิ, HTML tags, และอักขระพิเศษที่ทำให้ Pillow แสดงผลเป็นกล่องสี่เหลี่ยม □"""
    if not text:
        return ""
    # 1. ลบ HTML tags เช่น <img ...>, <a ...>
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    # 2. ลบ URLs ที่อาจติดมาใน description
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    # 3. ลบ Emojis และ Symbols
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned)
    cleaned = re.sub(r"[\u2600-\u27ff]", "", cleaned)
    cleaned = re.sub(r"[\u2300-\u23ff]", "", cleaned)
    cleaned = re.sub(r"[\u2b50-\u2b55]", "", cleaned)
    cleaned = re.sub(r"[\ufe0e\ufe0f]", "", cleaned)
    cleaned = cleaned.replace("🚨", "").replace("🔴", "").replace("💬", "").replace("👇", "").replace("💡", "").replace("🌟", "").replace("🔮", "").replace("💼", "").replace("🏠", "").replace("✨", "").replace("🦛", "")
    # 4. ลบ Markdown tags (#, *, _, `, ##) และเศษหัวข้อข่าวที่ติดมา
    cleaned = re.sub(r'#+\s*', '', cleaned)
    cleaned = re.sub(r'[*_~`]+', '', cleaned)
    cleaned = re.sub(r'ข่าว[อฮด]ื่น\s*ๆ.*', '', cleaned)
    cleaned = re.sub(r'##.*', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def wrap_thai_lines(text: str, max_chars_per_line: int = 24, max_lines: int = 8) -> List[str]:
    text = clean_render_text(text)
    if not text:
        return []

    # ถ้ามีเครื่องหมายวรรคตอนเด่น เช่น !, ?, •, : ให้ตัดบรรทัดตรงวรรคตอนก่อน เพื่อความสละสลวยเป็นธรรมชาติ
    for punct in ["!", "?", "•", " :", ":"]:
        if punct in text:
            parts = text.split(punct, 1)
            p1 = parts[0].strip() + (punct if punct not in ("•", " :", ":") else "")
            p2 = parts[1].strip()
            if 3 <= len(p1) <= max_chars_per_line and len(p2) >= 3:
                wrapped_p2 = wrap_thai_lines(p2, max_chars_per_line=max_chars_per_line, max_lines=max_lines - 1)
                return [p1] + wrapped_p2

    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(text, engine="newmm")
    except Exception:
        tokens = text.split(" ")

    lines, cur = [], ""
    for t in tokens:
        if len(cur) + len(t) <= max_chars_per_line:
            cur += t
        else:
            if cur:
                lines.append(cur)
            cur = t
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        return lines[:max_lines]
    return lines

def safe_thai_truncate(text: str, max_chars: int = 50) -> str:
    """ตัดข้อความตามขอบเขตคำภาษาไทยด้วย PyThaiNLP ป้องกันตัดกลางพยางค์ และตัดคำค้างคาที่ปลายประโยค"""
    text = clean_render_text(text)
    if len(text) <= max_chars:
        return re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', text).strip()

    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(text, engine="newmm")
        res = ""
        for t in tokens:
            if len(res) + len(t) <= max_chars:
                res += t
            else:
                break
        if not res:
            res = text[:max_chars]
    except Exception:
        res = text[:max_chars].rsplit(" ", 1)[0]

    # ลบอักขระ เครื่องหมายคำพูด และคำค้างคาที่ปลายข้อความ เฉพาะกรณีที่ข้อความถูกตัดทอนจริงๆ
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    res = re.sub(r'(?:เพื่อ|ที่|และ|หรือ|กับ|ว่า|คือ|จะ|ใน|ของ|จาก|สำหรับ|เมื่อ|ให้|โดย|ถึง)$', '', res).strip()
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    return res

CONTENT_HISTORY_FILE = TOOLS_DIR / "posted_content_history.json"
LAST_HACK_IDX_FILE = TOOLS_DIR / "last_life_hack_index.txt"
LAST_WORK_IDX_FILE = TOOLS_DIR / "last_work_tip_index.txt"
LAST_HORO_IDX_FILE = TOOLS_DIR / "last_horo_index.txt"

DAYS_OF_WEEK_MAP = {
    "จันทร์": "monday", "วันจันทร์": "monday",
    "อังคาร": "tuesday", "วันอังคาร": "tuesday",
    "พุธ": "wednesday", "วันพุธ": "wednesday",
    "พฤหัส": "thursday", "วันพฤหัส": "thursday", "วันพฤหัสบดี": "thursday", "พฤหัสบดี": "thursday",
    "ศุกร์": "friday", "วันศุกร์": "friday",
    "เสาร์": "saturday", "วันเสาร์": "saturday",
    "อาทิตย์": "sunday", "วันอาทิตย์": "sunday",
}

ZODIAC_SIGNS_MAP = {
    "ราศีเมษ": "aries", "เมษ": "aries",
    "ราศีพฤษภ": "taurus", "พฤษภ": "taurus",
    "ราศีเมถุน": "gemini", "เมถุน": "gemini",
    "ราศีกรกฎ": "cancer", "กรกฎ": "cancer",
    "ราศีสิงห์": "leo", "สิงห์": "leo",
    "ราศีกันย์": "virgo", "กันย์": "virgo",
    "ราศีตุลย์": "libra", "ตุลย์": "libra",
    "ราศีพิจิก": "scorpio", "พิจิก": "scorpio",
    "ราศีธนู": "sagittarius", "ธนู": "sagittarius",
    "ราศีมังกร": "capricorn", "มังกร": "capricorn",
    "ราศีกุมภ์": "aquarius", "กุมภ์": "aquarius",
    "ราศีมีน": "pisces", "มีน": "pisces",
}

def get_entity_keys(text: str) -> set:
    entities = set()
    for k, v in DAYS_OF_WEEK_MAP.items():
        if k in text:
            entities.add(f"day_{v}")
    for k, v in ZODIAC_SIGNS_MAP.items():
        if k in text:
            entities.add(f"zodiac_{v}")
    return entities

def load_content_history() -> dict:
    if CONTENT_HISTORY_FILE.exists():
        try:
            return json.loads(CONTENT_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_content_history(history: dict) -> None:
    try:
        CONTENT_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"บันทึกประวัติคอนเทนต์ล้มเหลว: {e}")

def normalize_title_for_compare(title: str) -> str:
    """ตัดเครื่องหมาย วรรค และตัวอักษรพิเศษเพื่อเปรียบเทียบข้อความจริง"""
    if not title:
        return ""
    t = re.sub(r'https?://\S+', '', title)
    t = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9]', '', t).lower()
    return t

def extract_topic_keywords(text: str) -> set:
    """สกัดคำสำคัญจากหัวข้อภาษาไทยเพื่อเปรียบเทียบประเด็นข่าว"""
    if not text:
        return set()
    cleaned = re.sub(r'https?://\S+', '', text)
    cleaned = cleaned.replace('ฯ', ' ').replace('ๆ', ' ').replace('!', ' ').replace('?', ' ')
    cleaned = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s]', ' ', cleaned)
    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(cleaned, engine="newmm")
    except Exception:
        tokens = cleaned.split()

    stop_words = {
        "และ", "หรือ", "ใน", "ที่", "ของ", "กับ", "ให้", "ได้", "จะ", "มี", "เป็น", "ไป", "มา",
        "นี้", "นั้น", "หลัง", "เปิด", "ฉาก", "กลาง", "วัน", "เวลา", "ด่วน", "เผย", "สุด", "ทำ",
        "คน", "ดูดวง", "รายวัน", "ประจำวัน", "สำหรับ", "ท่าน", "ที่เกิด", "ประจำ", "เช็ค", "เรื่อง",
        "ความ", "แบบ", "วันนี้", "สัปดาห์นี้", "ราศี", "เดือน", "ปี", "2569", "2568", "2567", "2566"
    }
    keywords = {t.strip() for t in tokens if len(t.strip()) > 2 and t.strip() not in stop_words}
    return keywords

def is_topic_duplicate(title: str, history: Optional[dict] = None, url: str = "") -> bool:
    """เช็คว่าหัวข้อนี้เคยถูกนำไปสร้างคลิปหรือโพสต์ไปแล้วหรือยัง (ตรวจความคล้าย, exact match, URL, และคำสำคัญแบบ Entity-Aware)"""
    if not title and not url:
        return False

    # 0. กรองเนื้อหาต้องห้ามเด็ดขาด (การเมือง / กษัตริย์ / ม.112 / ความรุนแรง)
    try:
        from app.services.content_safety_filter import is_sensitive_forbidden_topic
        if is_sensitive_forbidden_topic(title) or is_sensitive_forbidden_topic(url):
            logger.warning(f"🚫 บล็อกเนื้อหาต้องห้าม (Sensitive Blacklist): {title[:60]}")
            return True
    except Exception:
        pass

    if history is None:
        history = load_content_history()
    
    clean_target = normalize_title_for_compare(title) if title else ""
    target_kw = extract_topic_keywords(title) if title else set()
    target_ent = get_entity_keys(title) if title else set()
    clean_url = url.strip().split("?")[0].lower() if url else ""

    # 1. เช็คจาก posted_content_history
    for item_key, record in history.items():
        # ตรวจ URL ซ้ำ 100%
        rec_details = record.get("details", {}) or {}
        rec_url = (rec_details.get("url") or rec_details.get("link") or "").strip().split("?")[0].lower()
        if clean_url and rec_url and clean_url == rec_url:
            return True

        rec_title = record.get("title", "")
        clean_rec = normalize_title_for_compare(rec_title)
        if not clean_rec:
            continue
        
        # Exact match 100%
        if clean_target and clean_target == clean_rec:
            return True

        rec_ent = get_entity_keys(rec_title)
        # ถ้ามี entity ต่างกัน (เช่น วันจันทร์ กับ วันอาทิตย์ หรือ ราศีเมษ กับ ราศีมีน) -> ไม่ถือว่าซ้ำ
        if target_ent and rec_ent and target_ent != rec_ent:
            continue

        # ตรวจความคล้ายแบบ substring
        if clean_target and (clean_target in clean_rec or clean_rec in clean_target):
            if abs(len(clean_target) - len(clean_rec)) <= 8:
                return True

        # ตรวจ keyword overlap ถ้าประเด็นข่าวเดียวกัน
        rec_kw = extract_topic_keywords(rec_title)
        if target_kw and rec_kw:
            overlap = target_kw.intersection(rec_kw)
            if len(overlap) >= 3 or (len(overlap) >= 2 and (len(overlap)/len(target_kw) >= 0.5 or len(overlap)/len(rec_kw) >= 0.5)):
                return True

    # 2. เช็คจาก products.json
    products_json_path = REELS_DIR / "products.json"
    if products_json_path.exists():
        try:
            p_meta = json.loads(products_json_path.read_text(encoding="utf-8"))
            for fn, meta in p_meta.items():
                p_name = meta.get("product_name", "")
                c_name = normalize_title_for_compare(p_name)
                if c_name and clean_target:
                    if clean_target == c_name:
                        return True
                    if clean_target in c_name or c_name in clean_target:
                        if abs(len(clean_target) - len(c_name)) <= 8:
                            return True
                p_ent = get_entity_keys(p_name)
                if target_ent and p_ent and target_ent != p_ent:
                    continue
                rec_kw = extract_topic_keywords(p_name)
                if target_kw and rec_kw:
                    overlap = target_kw.intersection(rec_kw)
                    if len(overlap) >= 3 or (len(overlap) >= 2 and (len(overlap)/len(target_kw) >= 0.5 or len(overlap)/len(rec_kw) >= 0.5)):
                        return True
        except Exception:
            pass

    # 3. เช็คจาก posted_reels_title_history.json
    titles_file = TOOLS_DIR / "posted_reels_title_history.json"
    if titles_file.exists():
        try:
            t_records = json.loads(titles_file.read_text(encoding="utf-8"))
            if isinstance(t_records, list):
                for tr in t_records:
                    pt_title = tr.get("title", "") if isinstance(tr, dict) else str(tr)
                    c_pt = normalize_title_for_compare(pt_title)
                    if c_pt and clean_target:
                        if clean_target == c_pt:
                            return True
                        if clean_target in c_pt or c_pt in clean_target:
                            if abs(len(clean_target) - len(c_pt)) <= 8:
                                return True
        except Exception:
            pass

    return False

def record_topic_used(title: str, category: str, details: Optional[dict] = None) -> None:
    history = load_content_history()
    now_iso = datetime.now(timezone.utc).isoformat()
    key = f"{category}_{int(time.time()*1000)}"
    history[key] = {
        "title": title,
        "category": category,
        "created_at": now_iso,
        "details": details or {}
    }
    # เก็บประวัติ 500 รายการล่าสุด
    if len(history) > 500:
        sorted_keys = sorted(history.keys(), key=lambda k: history[k].get("created_at", ""))
        for k in sorted_keys[:-500]:
            history.pop(k, None)
    save_content_history(history)

def fetch_real_live_rss(feed_url: str, default_title: str, default_summary: str, default_hook: str, default_img: str) -> Dict[str, Any]:
    """ดึงข้อมูลข่าว/กระแสสดใหม่วันนี้ 100% จาก RSS Feed สแกนหาข่าวที่ยังไม่เคยใช้เด็ดขาด"""
    try:
        r = httpx.get(feed_url, timeout=7.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.text:
            root = ET.fromstring(r.content)
            candidates = []
            for it in root.iter():
                if it.tag.split("}")[-1] == "item":
                    t_el = it.find("title")
                    d_el = it.find("description")
                    l_el = it.find("link")
                    enc_el = it.find("enclosure")
                    media_thumb = it.find(".//{http://search.yahoo.com/mrss/}thumbnail")
                    if t_el is not None and t_el.text:
                        raw_title = html.unescape(t_el.text).strip()
                        raw_desc = html.unescape(d_el.text or "").strip() if d_el is not None and d_el.text else ""
                        link = html.unescape(l_el.text).strip() if l_el is not None and l_el.text else ""
                        title = clean_render_text(raw_title)
                        desc = clean_render_text(raw_desc)
                        img_url = ""
                        if enc_el is not None and enc_el.get("url"):
                            img_url = enc_el.get("url")
                        elif media_thumb is not None and media_thumb.get("url"):
                            img_url = media_thumb.get("url").replace("/240/", "/1024/")

                        # กรองเฉพาะข่าวที่มีรูปภาพจริงเท่านั้น 100%
                        if img_url and len(title) >= 10 and not any(k in title for k in ["หวยออนไลน์", "คาสิโน"]):
                            candidates.append({
                                "title": safe_thai_truncate(title, 65),
                                "detail": safe_thai_truncate(desc, 160) if desc else title,
                                "summary": safe_thai_truncate(desc, 160) if desc else title,
                                "img_url": img_url,
                                "link": link
                            })
            if candidates:
                history = load_content_history()
                chosen = None
                for cand in candidates:
                    if not is_topic_duplicate(cand["title"], history):
                        chosen = cand
                        break
                if not chosen:
                    # หากทุกข่าวในฟีดนี้ถูกใช้ไปแล้ว ให้เลือกข่าวที่เก่าสุดในฟีดเพื่อวนรอบใหม่
                    chosen = candidates[-1] if len(candidates) > 1 else candidates[0]

                record_topic_used(chosen["title"], "RSS_LIVE", {"url": feed_url})
                chosen_img = chosen["img_url"]
                clean_hook = safe_thai_truncate(chosen['title'], 50)

                # ดึง 3 ภาพจริงที่ไม่ซ้ำกันเด็ดขาด
                import image_footprint_crawler
                three_imgs = image_footprint_crawler.find_three_distinct_images({
                    "title": chosen["title"],
                    "link": chosen.get("link", ""),
                    "image_url": chosen_img
                }, mode="TRENDING_NEWS")

                return {
                    "title": chosen["title"],
                    "detail": chosen["detail"],
                    "summary": chosen["summary"],
                    "hook": f"🚨 เรื่องเด็ดวันนี้! {clean_hook}",
                    "image_url": chosen_img,
                    "image_urls": three_imgs,
                    "link": chosen.get("link", "")
                }
    except Exception as e:
        logger.warning(f"ดึง RSS จาก {feed_url} ล้มเหลว: {e}")

    return {
        "title": default_title,
        "detail": default_summary,
        "summary": default_summary,
        "image_url": default_img,
        "image_urls": [default_img, default_img, default_img],
        "hook": default_hook
    }

def fetch_global_world_trend(category: str = "world") -> Dict[str, Any]:
    """ดึงข่าวด่วนและเทรนด์กระแสระดับโลกจาก BBC World สแกนหาข่าวที่ไม่ซ้ำ 100%"""
    feed_urls = {
        "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "entertain": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    }
    url = feed_urls.get(category, feed_urls["world"])

    try:
        r = httpx.get(url, timeout=8.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.text:
            root = ET.fromstring(r.content)
            items = []
            for it in root.iter():
                if it.tag.split("}")[-1] == "item":
                    t_el = it.find("title")
                    d_el = it.find("description")
                    media_thumb = it.find(".//{http://search.yahoo.com/mrss/}thumbnail")
                    enc_el = it.find("enclosure")
                    if t_el is not None and t_el.text:
                        title_en = html.unescape(t_el.text).strip()
                        desc_en = html.unescape(d_el.text or "").strip() if d_el is not None and d_el.text else ""
                        img_url = ""
                        if media_thumb is not None and media_thumb.get("url"):
                            img_url = media_thumb.get("url").replace("/240/", "/1024/")
                        elif enc_el is not None and enc_el.get("url"):
                            img_url = enc_el.get("url")
                        if img_url:
                            items.append((title_en, desc_en, img_url))

            if items:
                history = load_content_history()
                chosen_item = None
                for it in items:
                    if not is_topic_duplicate(it[0], history):
                        chosen_item = it
                        break
                if not chosen_item:
                    chosen_item = items[-1] if len(items) > 1 else items[0]

                chosen_en_title, chosen_en_desc, exact_img = chosen_item

                groq_keys = os.getenv("GROQ_API_KEY", "").split(",")
                for k in groq_keys:
                    k = k.strip()
                    if not k or "mock" in k:
                        continue
                    try:
                        from openai import OpenAI
                        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k, timeout=8.0)
                        prompt = (
                            f"You are a professional viral short video creator in Thailand (YouTube Shorts / TikTok / Reels).\n"
                            f"Translate and adapt this global breaking news/trend into gripping Thai:\n"
                            f"English Title: {chosen_en_title}\n"
                            f"English Detail: {chosen_en_desc}\n\n"
                            f"Respond ONLY in valid JSON with these 3 keys:\n"
                            f'{{"thai_title": "หัวข้อข่าวภาษาไทยกระชับไม่เกิน 50 ตัวอักษร", '
                            f'"hook": "ประโยค Hook 3 วินาทีแรกที่ตื่นเต้น เช่น ด่วนระดับโลก! ...", '
                            f'"summary": "สรุปเนื้อหาสำคัญ 1-2 ประโยคภาษาไทย"}}'
                        )
                        for m in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
                            try:
                                resp = client.chat.completions.create(
                                    model=m,
                                    messages=[{"role": "user", "content": prompt}],
                                    response_format={"type": "json_object"},
                                    temperature=0.6,
                                    max_tokens=250
                                )
                                data = json.loads(resp.choices[0].message.content)
                                thai_title = safe_thai_truncate(data.get("thai_title", chosen_en_title), 50)
                                record_topic_used(thai_title, "BBC_GLOBAL", {"en_title": chosen_en_title})
                                clean_hook = safe_thai_truncate(data.get("hook", f"ด่วนระดับโลก! {thai_title}"), 50)
                                import image_footprint_crawler
                                three_imgs = image_footprint_crawler.find_three_distinct_images({
                                    "title": thai_title,
                                    "link": url,
                                    "image_url": exact_img
                                }, mode="TRENDING_NEWS")
                                return {
                                    "title": thai_title,
                                    "detail": safe_thai_truncate(data.get("summary", chosen_en_desc), 140),
                                    "summary": safe_thai_truncate(data.get("summary", chosen_en_desc), 140),
                                    "hook": clean_hook,
                                    "image_url": exact_img,
                                    "image_urls": three_imgs,
                                    "link": url
                                }
                            except Exception:
                                continue
                    except Exception as e_ai:
                        logger.warning(f"Groq แปลข่าวระดับโลกผิดพลาด: {e_ai}")
                        continue
    except Exception as e:
        logger.warning(f"ดึงข่าวระดับโลก {url} ผิดพลาด: {e}")

    return fetch_real_live_rss(
        "https://rssfeeds.sanook.com/rss/feeds/sanook/news.index.xml",
        default_title="สรุปข่าวเด่นประเด็นร้อนวันนี้ เกาะติดสถานการณ์สำคัญ",
        default_summary="อัปเดตข่าวสารทันเหตุการณ์วันนี้ สรุปประเด็นสำคัญที่ทุกคนต้องรู้",
        default_hook="🚨 สรุปข่าวด่วนวันนี้! เรื่องเด่นที่ทุกคนต้องรู้",
        default_img="https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800&auto=format&fit=crop"
    )

def fetch_real_news_headline() -> Dict[str, Any]:
    """ดึงข่าวด่วนระดับโลก (BBC World) หรือข่าวด่วนจริงจาก Sanook News พร้อมภาพข่าวจริง"""
    import random
    if random.random() < 0.6:
        return fetch_global_world_trend("world")
    return fetch_real_live_rss(
        "https://rssfeeds.sanook.com/rss/feeds/sanook/news.index.xml",
        default_title="สรุปข่าวเด่นประเด็นร้อนวันนี้ เกาะติดสถานการณ์สำคัญ",
        default_summary="อัปเดตข่าวสารทันเหตุการณ์วันนี้ สรุปประเด็นสำคัญที่ทุกคนต้องรู้",
        default_hook="🚨 สรุปข่าวด่วนวันนี้! เรื่องเด่นที่ทุกคนต้องรู้",
        default_img="https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800&auto=format&fit=crop"
    )

def fetch_real_celebrity_trend() -> Dict[str, Any]:
    """ดึงข่าวดาราบันเทิงกระแสแรงจาก Sanook Entertain หรือ BBC Entertainment พร้อมภาพถ่ายศิลปินจริง"""
    import random
    if random.random() < 0.5:
        return fetch_real_live_rss(
            "https://rssfeeds.sanook.com/rss/feeds/sanook/news.entertain.xml",
            default_title="เจาะลึกกระแสคนดังไวรัล ประเด็นฮิตที่โซเชียลพูดถึง",
            default_summary="เรื่องราวคนดังและกระแสไวรัลที่กำลังเป็นที่จับตามองทั่วโลกออนไลน์",
            default_hook="🌟 ส่องกระแสคนดังวันนี้! เรื่องที่ทุกคนกำลังพูดถึง",
            default_img="https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800&auto=format&fit=crop"
        )
    return fetch_global_world_trend("entertain")

def fetch_real_horoscope_trend() -> Dict[str, Any]:
    """ดึงดวงรายวันจาก Sanook Horoscope พร้อมภาพคอลัมน์ดวงจริง"""
    return fetch_real_live_rss(
        "https://rssfeeds.sanook.com/rss/feeds/sanook/horoscope.index.xml",
        default_title="เช็คดวงวันนี้ ราศีไหนมีเกณฑ์รับทรัพย์ การเงินพุ่ง",
        default_summary="แนวทางดวงชะตาและเคล็ดลับเสริมโชคลาภประจำวัน รับพลังบวกและโชคดี",
        default_hook="🔮 เช็คดวงวันนี้! ราศีไหนมีเกณฑ์ดวงเฮงรับทรัพย์",
        default_img="https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop"
    )

def fetch_authentic_astrology_insights() -> Dict[str, Any]:
    """สืบค้นข้อมูลเชิงลึกด้านโหราศาสตร์ไทยโบราณ ทักษาปกรณ์ ฮวงจุ้ย และศาสตร์ดวงดาวจากแหล่งความรู้จริงในเน็ต (Tavily & Web Footprint)"""
    import os
    import httpx
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
    
    api_key = (os.getenv("TAVILY_API_KEY") or "").split(",")[0].strip()
    if not api_key:
        return fetch_real_horoscope_trend()

    queries = [
        "โหราศาสตร์ไทย ดวง 12 ราศี การโคจรดาวพฤหัสบดี ดาวเสาร์",
        "สีเสื้อมงคล ตำราทักษาปกรณ์ ภูมิเดช ภูมิศรี โหราศาสตร์ไทย",
        "ฮวงจุ้ยเบญจธาตุ โต๊ะทำงาน มังกรเขียว เสือขาว เสริมดวงการเงิน",
        "ศาสตร์ตัวเลขมงคล คู่ดาวศุภเคราะห์ ๒๔ ๓๖ ๕๖ โหราศาสตร์ตัวเลข",
        "เคล็ดลับเสริมดวงชะตา การเงิน โชคลาภ โหราศาสตร์โบราณ"
    ]
    import random
    query = random.choice(queries)

    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": 3},
            timeout=6.0
        )
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            if results:
                history = load_content_history()
                for res in results:
                    raw_title = res.get("title", "")
                    content_snippet = res.get("content", "")
                    if not raw_title or is_topic_duplicate(raw_title, history):
                        continue
                    
                    # ใช้ Groq AI สกัดหลักวิชาและศาสตร์แท้ที่น่าเชื่อถือ
                    client = get_groq_client()
                    if client:
                        prompt = (
                            f"คุณคือผู้เชี่ยวชาญด้านโหราศาสตร์ไทยโบราณ คัมภีร์มหาทักษาปกรณ์ และศาสตร์ฮวงจุ้ยเบญจธาตุชั้นสูง\n"
                            f"จงวิเคราะห์ข้อมูลจริงนี้ และสรุปเป็นคอนเทนต์วิดีโอสั้นที่เปี่ยมด้วยความเคารพในศาสตร์ มีหลักวิชาการ และน่าเชื่อถือสูงสุด (ห้ามทำเป็นเรื่องเล่นหรือมุกตลกเด็ดขาด):\n"
                            f"แหล่งข้อมูล: {raw_title}\n"
                            f"เนื้อหา: {content_snippet}\n\n"
                            f"ตอบกลับเป็น JSON ภาษาไทยที่มีโครงสร้างนี้เท่านั้น:\n"
                            f'{{\n'
                            f'  "thai_title": "หัวข้อตามหลักวิชาการโหราศาสตร์/ฮวงจุ้ย (ไม่เกิน 50 ตัวอักษร)",\n'
                            f'  "step1": "1. หลักวิชา & อิทธิพลดวงดาว/พลังงาน (เช่น ตามหลักทักษาปกรณ์...)",\n'
                            f'  "step2": "2. วิธีปฏิบัติหรือข้อแนะนำเสริมดวงที่ถูกต้องตามตำรา",\n'
                            f'  "step3": "3. สิ่งที่ควรระวังหรือข้อห้ามตามศาสตร์",\n'
                            f'  "hook": "ประโยค Hook 3 วินาทีแรกที่ทรงพลัง สำรวม และน่าติดตาม",\n'
                            f'  "numbers": "ตัวเลขมงคลคู่ดาว เช่น ๒ ๔ • ๕ ๖ • ๒ ๔ ๖"\n'
                            f'}}'
                        )
                        ai_data = None
                        for m in ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
                            try:
                                resp = client.chat.completions.create(
                                    model=m,
                                    messages=[{"role": "user", "content": prompt}],
                                    response_format={"type": "json_object"},
                                    temperature=0.6,
                                    max_tokens=280
                                )
                                ai_data = json.loads(resp.choices[0].message.content)
                                break
                            except Exception:
                                continue
                        if not ai_data:
                            continue
                        thai_title = safe_thai_truncate(ai_data.get("thai_title", raw_title), 50)
                        clean_hook = safe_thai_truncate(ai_data.get("hook", f"🔮 เช็คดวงตามศาสตร์แท้! {thai_title}"), 50)
                        img_url = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop"
                        topic_obj = {
                            "title": thai_title,
                            "step1": ai_data.get("step1", ""),
                            "step2": ai_data.get("step2", ""),
                            "step3": ai_data.get("step3", ""),
                            "hook": clean_hook,
                            "numbers": ai_data.get("numbers", "๒ ๔ • ๕ ๖ • ๑ ๕ ๖"),
                            "image_url": img_url,
                            "image_urls": image_footprint_crawler.find_three_distinct_images({
                                "title": thai_title,
                                "image_url": img_url
                            }, mode="LUCKY_FORTUNE")
                        }
                        record_topic_used(thai_title, "LUCKY_FORTUNE_WEB", topic_obj)
                        return topic_obj
    except Exception as e:
        logger.warning(f"ค้นหาโหราศาสตร์จากเว็บล้มเหลว: {e}")

    return fetch_real_horoscope_trend()

CACHE_IMG_DIR = REELS_DIR / "cached_topic_images"
CACHE_IMG_DIR.mkdir(parents=True, exist_ok=True)

def fetch_topic_image(image_url: str) -> Optional[Image.Image]:
    """ดาวน์โหลดและตรวจสอบรูปภาพจริงความคมชัดสูง หากโหลดภาพจริงไม่ได้ หรือเป็นภาพฟอรัมขยะ ให้ส่งคืน None ทันที เพื่อสลับใช้ Typography Card"""
    if not image_url or not image_url.startswith("http"):
        return None

    # กรองภาพขยะจากเว็บบอร์ด เช่น pantip attachment (ptcdn.info), avatar, icon
    if any(k in image_url.lower() for k in ["ptcdn.info", "avatar", "profile", "emoji", "icon"]):
        return None

    import hashlib
    img_hash = hashlib.md5(image_url.encode("utf-8")).hexdigest()
    cached_path = CACHE_IMG_DIR / f"{img_hash}.jpg"

    if cached_path.exists() and cached_path.stat().st_size > 3000:
        try:
            return Image.open(cached_path).convert("RGBA")
        except Exception:
            pass

    try:
        r = httpx.get(image_url, timeout=10.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and len(r.content) > 3000:
            import io
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            if img.width >= 300 and img.height >= 200:
                cached_path.write_bytes(r.content)
                return img
    except Exception as e:
        logger.warning(f"ดาวน์โหลดภาพจริงล้มเหลว {image_url}: {e}")

    return None

LIFE_HACK_TOPICS = [
    {
        "title": "วิธีแก้ก้นกระทะไหม้ดำ ให้เงาวับใน 1 นาที",
        "step1": "1. โรยเบกกิ้งโซดาผสมน้ำส้มสายชู",
        "step2": "2. แช่น้ำร้อนทิ้งไว้ 5-10 นาที",
        "step3": "3. ใช้ฟองน้ำขัดเบาๆ คราบหลุดหมดเกลี้ยง",
        "hook": "🚨 อย่าเพิ่งทิ้งกระทะไหม้! ทริคนี้ขัดออกง่ายเหมือนใหม่",
        "image_url": "https://images.unsplash.com/photo-1584992236310-6edddc08acff?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1584992236310-6edddc08acff?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "ดับกลิ่นท่อระบายน้ำกวนใจ ด้วยของในบ้าน",
        "step1": "1. เทเบกกิ้งโซดา 1 ถ้วยลงในท่อ",
        "step2": "2. เทน้ำส้มสายชูตามลงไป ปิดฝาไว้ 15 นาที",
        "step3": "3. ราดน้ำร้อนตาม กลิ่นเหม็นหายสนิท",
        "hook": "💡 ทริคดับกลิ่นท่อเหม็นในห้องน้ำ ทำเองง่ายๆ ใน 3 ขั้นตอน",
        "image_url": "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1585421514284-efb74c2b69ba?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "จัดตู้เสื้อผ้าแคบ ให้จุของเพิ่ม 3 เท่า",
        "step1": "1. ใช้ห่วงกระป๋องน้ำอัดลมซ้อนไม้แขวน",
        "step2": "2. ม้วนเสื้อผ้าแนวตั้งแทนการพับทับ",
        "step3": "3. แยกหมวดหมู่สี หยิบง่ายไม่รกตา",
        "hook": "🏠 ตู้เสื้อผ้าแน่นจนปิดไม่ลง? ใช้ทริคนี้ประหยัดที่ 3 เท่า!",
        "image_url": "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "วิธีล้างคราบตะกรันกาต้มน้ำ ใสวิ้งเหมือนใหม่",
        "step1": "1. เติมน้ำครึ่งกา ใส่กรดมะนาวหรือน้ำส้มสายชู 3 ช้อนโต๊ะ",
        "step2": "2. กดต้มน้ำให้เดือดแล้วแช่ทิ้งไว้ 20 นาที",
        "step3": "3. เทน้ำทิ้ง ล้างน้ำเปล่า 1 รอบ คราบหลุดเกลี้ยง",
        "hook": "✨ กาต้มน้ำคราบขาวแน่น? ต้มสูตรนี้ 5 นาที ใสปิ๊ง!",
        "image_url": "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1517256064527-09c73fc73e38?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "ทริคแก้วน้ำเหม็นอับ ล้างยังไงก็ไม่หาย",
        "step1": "1. ใส่กากกาแฟหรือเบกกิ้งโซดา 1 ช้อนลงในแก้ว",
        "step2": "2. เติมน้ำอุ่น ปิดฝาเขย่าแล้วแช่ไว้ 30 นาที",
        "step3": "3. ล้างด้วยน้ำยาล้างจานตามปกติ กลิ่นหาย 100%",
        "hook": "💡 แก้วเก็บความเย็นมีกลิ่นอับ? ใช้ของสิ่งนี้กลิ่นหายเกลี้ยง!",
        "image_url": "https://images.unsplash.com/photo-1517256064527-09c73fc73e38?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1517256064527-09c73fc73e38?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "วิธีลบคราบกาวสติกเกอร์เหนียวเหนอะหนะ",
        "step1": "1. ทาน้ำมันพืชหรือเบบี้ออยล์บนคราบกาว",
        "step2": "2. ทิ้งไว้ 3 นาทีให้น้ำมันซึมสลายกาว",
        "step3": "3. ใช้กระดาษทิชชู่เช็ดออกเบาๆ กาวหลุดทันที",
        "hook": "🚨 คราบกาวสติกเกอร์แกะไม่ออก? อย่าเพิ่งขูด ลองทริคนี้!",
        "image_url": "https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "ทริคกันมดขึ้นโต๊ะอาหาร แบบไม่ต้องใช้สารเคมี",
        "step1": "1. ใช้น้ำส้มสายชูผสมน้ำเปล่า 1:1 ฉีดพ่นทางเดินมด",
        "step2": "2. โรยแป้งเด็กหรือแป้งเย็นรอบขาโต๊ะ",
        "step3": "3. กลิ่นฉุนจะลบรอยฟีโรโมน มดไม่กล้าเดินผ่าน",
        "hook": "🐜 มดบุกครัวทุกวัน? สูตรธรรมชาติไล่มดราบคาบ ปลอดภัย 100%",
        "image_url": "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1585421514284-efb74c2b69ba?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "วิธีแก้ยางรัดผมหรือเสื้อยืด ย้วยคืนทรงเดิม",
        "step1": "1. นำยางหรือคอเสื้อแช่ในน้ำร้อนจัด 1-2 นาที",
        "step2": "2. ยกขึ้นแช่ในน้ำเย็นจัดทันที เพื่อให้เส้นใยหดตัว",
        "step3": "3. ตากในที่ร่ม ยางจะกลับมากระชับเหมือนใหม่",
        "hook": "✨ ยางย้วย เสื้อคอย้วยอย่าเพิ่งทิ้ง! แช่น้ำสูตรนี้กลับมาฟิตเปรี๊ยะ",
        "image_url": "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "วิธีทำความสะอาดพัดลมฝุ่นหนา โดยไม่ต้องถอดล้าง",
        "step1": "1. ผสมน้ำยาล้างจาน เบกกิ้งโซดา และน้ำส้มสายชูใส่ฟ็อกกี้",
        "step2": "2. ฉีดพ่นบางๆ บนตะแกรงและใบพัด",
        "step3": "3. คลุมด้วยถุงพลาสติกใบใหญ่ แล้วเปิดพัดลมเบอร์แรงสุด 3 นาที",
        "hook": "💨 ขี้เกียจล้างพัดลม? ทริคนี้สะอาดกริ๊บใน 3 นาที ฝุ่นไม่กระจาย!",
        "image_url": "https://images.unsplash.com/photo-1584992236310-6edddc08acff?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1584992236310-6edddc08acff?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "วิธีซักผ้าขาวให้โอโม่ กำจัดคราบเหลืองฝังลึก",
        "step1": "1. ผสมผงซักฟอกกับไฮโดรเจนเปอร์ออกไซด์หรือเบกกิ้งโซดา",
        "step2": "2. แช่ผ้าในน้ำอุ่นทิ้งไว้ 30 นาที",
        "step3": "3. ซักตามปกติ ผ้าจะกลับมาขาวสว่างจ้า",
        "hook": "👕 คอเสื้อเหลืองคราบเหงื่อ? แช่สูตรนี้ผ้าขาววิ้งเหมือนเพิ่งซื้อ!",
        "image_url": "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=800&auto=format&fit=crop"
        ]
    }
]

WORK_PRODUCTIVITY_TOPICS = [
    {
        "title": "3 ทริคทำงานเสร็จไว เลิกงานตรงเวลา",
        "step1": "1. เคลียร์งานยากที่สุดช่วงเช้า 9:00-11:00",
        "step2": "2. ปิดการแจ้งเตือนตอนโฟกัสงานสำคัญ",
        "step3": "3. สรุป To-Do List ของวันถัดไปก่อนกลับบ้าน",
        "hook": "💼 ทริคคนทำงาน! ทำยังไงให้เลิกงานตรงเวลา ชีวิตง่ายขึ้น 10 เท่า",
        "image_url": "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1507207611509-ec012433ff52?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "วิธีคุยกับหัวหน้า ให้ได้งานราบรื่นและได้ผล",
        "step1": "1. สรุปประเด็นหลักใน 3 ประโยคแรก",
        "step2": "2. เตรียมทางเลือก (Option A/B) พร้อมข้อดีข้อเสีย",
        "step3": "3. มุ่งเน้นทางแก้ปัญหามากกว่าการบ่นเรื่องงาน",
        "hook": "🎯 คุยกับหัวหน้ายังไงให้ผ่านฉลุย เทคนิคง่ายๆ ได้ผลจริง!",
        "image_url": "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "เทคนิคจัดลำดับความสำคัญ ด้วย Eisenhow Matrix",
        "step1": "1. ด่วนและสำคัญ: ลงมือทำทันที",
        "step2": "2. สำคัญแต่ไม่ด่วน: ล็อคเวลาทำจริงจัง",
        "step3": "3. ด่วนแต่ไม่สำคัญ: มอบหมายให้คนอื่นช่วย",
        "hook": "📊 งานล้นมือทำไม่ทัน? ใช้สูตรเมทริกซ์ 4 ช่อง งานเสร็จไวขึ้น 2 เท่า!",
        "image_url": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1507207611509-ec012433ff52?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "เทคนิคประชุมกระชับ จบใน 25 นาที ไม่ยืดเยื้อ",
        "step1": "1. แจ้งวาระและผลลัพธ์ที่ต้องการล่วงหน้า 1 วัน",
        "step2": "2. กำหนดเวลาพูดคนละไม่เกิน 3 นาที",
        "step3": "3. สรุป Action Items ผู้รับผิดชอบทันทีก่อนปิดห้อง",
        "hook": "⏰ เบื่อประชุมยาวเป็นชั่วโมง? ทริคประชุม 25 นาที ได้งานจริง 100%",
        "image_url": "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=800&auto=format&fit=crop"
        ]
    },
    {
        "title": "วิธีจัดการอีเมล Inbox Zero ไม่ให้รกตา",
        "step1": "1. ใช้กฎ 2 นาที: ถ้าตอบได้ใน 2 นาทีให้ตอบทันที",
        "step2": "2. แยกโฟลเดอร์: งานด่วน / รอติดตาม / เอกสารอ้างอิง",
        "step3": "3. กดยกเลิกรับจดหมายข่าวที่ไม่ได้อ่านสัปดาห์ละครั้ง",
        "hook": "📧 เมลดองเป็นพันฉบับ? เคลียร์ Inbox ให้เหลือ 0 ภายใน 10 นาที!",
        "image_url": "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&auto=format&fit=crop",
        "image_urls": [
            "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1507207611509-ec012433ff52?w=800&auto=format&fit=crop"
        ]
    }
]

LUCKY_FORTUNE_TOPICS = [
    # --- หมวดที่ 1: สีเสื้อมงคล 7 วัน ตามคัมภีร์มหาทักษาปกรณ์แท้ ---
    {
        "title": "สีเสื้อมงคลวันจันทร์ ตามคัมภีร์มหาทักษาปกรณ์ เสริมโชคลาภ",
        "step1": "1. ภูมิศรี เรียกทรัพย์: สีส้ม สีเหลืองแก่ (เปิดดวงการเงิน ค้าขายกำไร)",
        "step2": "2. ภูมิมนตรี ผู้ใหญ่อุปถัมภ์: สีเขียวแก่ (ผู้บังคับบัญชาเมตตาเอ็นดู)",
        "step3": "3. ภูมิกาลกิณี ห้ามใส่เด็ดขาด: สีแดง (ขัดขวางโชคลาภ นำพาอุปสรรค)",
        "hook": "🔮 เสริมดวงวันจันทร์ตามตำราทักษาปกรณ์! สีมงคลเปิดคลังทรัพย์รับเงินล้าน",
        "numbers": "๒ ๔ • ๗ ๙ • ๒ ๔ ๗",
        "image_url": "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?w=800&auto=format&fit=crop"
    },
    {
        "title": "สีเสื้อมงคลวันอังคาร เสริมภูมิเดชและภูมิศรีมหาโชค ตามตำราโหร",
        "step1": "1. ภูมิศรี เรียกทรัพย์: สีน้ำตาล สีส้มอิฐ (เงินทองหมุนเวียนคล่องตัว)",
        "step2": "2. ภูมิเดช อำนาจบารมี: สีม่วงแก่ สีดำ (การงานก้าวหน้า ชนะศัตรูคู่แข่ง)",
        "step3": "3. ภูมิกาลกิณี ห้ามใส่เด็ดขาด: สีขาว สีครีม (สูญเสียพลังบารมี)",
        "hook": "✨ วันอังคารเปิดคลังทรัพย์ตามตำราโหร! สีมงคลหนุนดวงมหาเศรษฐี",
        "numbers": "๓ ๖ • ๕ ๑ • ๓ ๖ ๕",
        "image_url": "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=800&auto=format&fit=crop"
    },
    {
        "title": "สีเสื้อมงคลวันพุธ วาจาศักดิ์สิทธิ์ ค้าขายกำไรปัง ตามศาสตร์ทักษา",
        "step1": "1. ภูมิศรี เรียกทรัพย์: สีเทา สีควันบุหรี่ สีดำ (เจรจาค้าขายปิดดีลใหญ่)",
        "step2": "2. ภูมิเดช อำนาจวาจา: สีส้ม สีทอง (คำพูดน่าเชื่อถือ ปิดการขายง่าย)",
        "step3": "3. ภูมิกาลกิณี ห้ามใส่เด็ดขาด: สีชมพู (คำพูดคลาดเคลื่อน การเงินติดขัด)",
        "hook": "💰 ค้าขายเจรจาวันพุธต้องใส่สีนี้! ศาสตร์ทักษาปกรณ์เปิดทางรวย",
        "numbers": "๔ ๒ • ๘ ๖ • ๔ ๒ ๘",
        "image_url": "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=800&auto=format&fit=crop"
    },
    {
        "title": "สีเสื้อมงคลวันพฤหัสบดี รับพลังดาวพฤหัสบดีประธานศุภเคราะห์",
        "step1": "1. ภูมิศรี เรียกทรัพย์: สีแดง สีทอง (โชคใหญ่หล่นทับ เงินก้อนโต)",
        "step2": "2. ภูมิมนตรี บารมีหนุนนำ: สีฟ้า สีน้ำเงิน (ผู้ใหญ่และอาจารย์เมตตา)",
        "step3": "3. ภูมิกาลกิณี ห้ามใส่เด็ดขาด: สีม่วงเข้ม (พลังบาปเคราะห์เบียดเบียน)",
        "hook": "🌟 วันพฤหัสบดีวันครู! เสริมดวงรับพลังศุภเคราะห์ใหญ่ เงินงานพุ่งสุดขีด",
        "numbers": "๕ ๑ • ๙ ๓ • ๕ ๑ ๙",
        "image_url": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800&auto=format&fit=crop"
    },
    {
        "title": "สีเสื้อมงคลวันศุกร์ เสริมมหาเสน่ห์ดูดทรัพย์ ตามตำราทักษา",
        "step1": "1. ภูมิศรี เรียกทรัพย์: สีชมพู สีบานเย็น (ดึงดูดทรัพย์ เสน่ห์เมตตามหานิยม)",
        "step2": "2. ภูมิมนตรี การงานราบรื่น: สีขาว สีเหลืองอ่อน (คนรักใคร่ ช่วยเหลือ)",
        "step3": "3. ภูมิกาลกิณี ห้ามใส่เด็ดขาด: สีเทา สีดำ (ดับพลังเสน่ห์การเงิน)",
        "hook": "💖 วันศุกร์รับทรัพย์ตามตำราโบราณ! สีมงคลเปิดดวงมหาเสน่ห์ดูดทรัพย์",
        "numbers": "๖ ๓ • ๙ ๕ • ๖ ๓ ๙",
        "image_url": "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=800&auto=format&fit=crop"
    },
    {
        "title": "สีเสื้อมงคลวันเสาร์ เสริมมหาอำนาจบารมี เสี่ยงโชคเฮง",
        "step1": "1. ภูมิศรี เรียกทรัพย์: สีฟ้า สีน้ำเงินเข้ม (เสี่ยงโชคลาภก้อนใหญ่สำเร็จ)",
        "step2": "2. ภูมิเดช อำนาจยิ่งใหญ่: สีเทา สีควันบุหรี่ (บริวารยำเกรง หนุนดวงแข็ง)",
        "step3": "3. ภูมิกาลกิณี ห้ามใส่เด็ดขาด: สีเขียว (ทำให้พลังความมั่นคงลดทอน)",
        "hook": "👑 วันเสาร์เสริมมหาอำนาจมหาลาภ! ศาสตร์ทักษาปกรณ์คัดสีมงคลหนุนดวง",
        "numbers": "๗ ๘ • ๘ ๒ • ๗ ๘ ๒",
        "image_url": "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800&auto=format&fit=crop"
    },
    {
        "title": "สีเสื้อมงคลวันอาทิตย์ เสริมดวงเศรษฐี พลังสุริยเทพรับทรัพย์",
        "step1": "1. ภูมิศรี เรียกทรัพย์: สีเขียว สีมรกต (ดึงดูดความมั่งคั่ง ดวงการเงินสูงสุด)",
        "step2": "2. ภูมิเดช ชื่อเสียงบารมี: สีชมพู สีบานเย็น (เป็นที่ประจักษ์ เกียรติยศพุ่ง)",
        "step3": "3. ภูมิกาลกิณี ห้ามใส่เด็ดขาด: สีน้ำเงิน สีคราม (ดับพลังสุริยเทพ)",
        "hook": "☀️ วันอาทิตย์เปิดรับพลังสุริยเทพ! สีมงคลเสริมฐานะ ดวงเศรษฐีจับ",
        "numbers": "๑ ๕ • ๘ ๔ • ๑ ๕ ๘",
        "image_url": "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?w=800&auto=format&fit=crop"
    },
    # --- หมวดที่ 2: ศาสตร์ตัวเลขและคู่ดาวมงคลแห่งความมั่งคั่ง (Numerology) ---
    {
        "title": "ศาสตร์ตัวเลขมงคล คู่ดาว 24 พลังวาจาเรียกเงินล้าน",
        "step1": "1. พลังคู่ดาว: ดาวจันทร์ (เสน่ห์) รวมกับ ดาวพุธ (การเจรจาพารวย)",
        "step2": "2. คุณประโยชน์: เหมาะกับงานค้าขาย การตลาด เจรจาปิดการขายง่ายดาย",
        "step3": "3. เคล็ดลับใช้งาน: นำไปต่อท้ายชื่อไลน์ หรือตั้งเป็นรหัสผ่านกระเป๋าเงิน",
        "hook": "🔮 อยากวาจาพารวย? ศาสตร์คู่เลข 24 เมตตามหานิยม เงินทองไหลมาเทมา",
        "numbers": "๒ ๔ • ๔ ๒ • ๒ ๔ ๖",
        "image_url": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=800&auto=format&fit=crop"
    },
    {
        "title": "ศาสตร์ตัวเลขมงคล คู่ดาว 36 ดึงดูดทรัพย์สินเงินทองคล่องตัว",
        "step1": "1. พลังคู่ดาว: ดาวอังคาร (ความมุ่งมั่น) รวมกับ ดาวศุกร์ (ความมั่งคั่ง)",
        "step2": "2. คุณประโยชน์: หมุนเงินคล่อง การเงินไม่ติดขัด มีรายรับหลายทาง",
        "step3": "3. ข้อห้าม: ห้ามใช้คู่กับเลข 0 หรือ 7 เพราะจะทำให้ขัดแย้งพลังงาน",
        "hook": "💰 ปลดล็อคการเงินให้พุ่งกระฉูด! พลังคู่ดาว 36 ดึงดูดเงินทองเข้าไม่ขาดสาย",
        "numbers": "๓ ๖ • ๖ ๓ • ๓ ๖ ๕",
        "image_url": "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?w=800&auto=format&fit=crop"
    },
    {
        "title": "ศาสตร์ตัวเลขมงคล คู่ดาว 56 มหาเศรษฐี ทรัพย์สินมั่นคงถาวร",
        "step1": "1. พลังคู่ดาว: ศุภเคราะห์ใหญ่ทั้งคู่ สติปัญญาบวกทรัพย์สินสมบูรณ์",
        "step2": "2. คุณประโยชน์: หาเงินเก่ง เก็บเงินอยู่ กิจการมั่นคงระยะยาว",
        "step3": "3. เคล็ดลับใช้งาน: เหมาะอย่างยิ่งสำหรับผู้บริหาร เจ้าของธุรกิจ นักลงทุน",
        "hook": "🌟 เลขคู่เศรษฐีที่ดีที่สุดในตำรา! ศาสตร์คู่ดาว 56 ทรัพย์สินงอกเงยถาวร",
        "numbers": "๕ ๖ • ๖ ๕ • ๑ ๕ ๖",
        "image_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop"
    },
    {
        "title": "ศาสตร์ตัวเลขมงคล คู่ดาว 78 คู่มิตรใหญ่ เงินก้อนโตหล่นทับ",
        "step1": "1. พลังคู่ดาว: คู่มิตรมหาราหูและพระเสาร์ ดึงดูดเงินก้อนใหญ่",
        "step2": "2. คุณประโยชน์: เหมาะกับงานโครงการใหญ่ อสังหาฯ เสี่ยงโชคลาภ",
        "step3": "3. เคล็ดลับเสริม: หมั่นทำบุญปล่อยปลาเพื่อกระจายพลังบารมีให้กว้างขวาง",
        "hook": "👑 เงินก้อนใหญ่กำลังจะมา! พลังคู่ดาว 78 พลิกดวงชะตาสู่ความสำเร็จ",
        "numbers": "๗ ๘ • ๘ ๗ • ๗ ๘ ๙",
        "image_url": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop"
    },
    # --- หมวดที่ 3: ศาสตร์ฮวงจุ้ยเบญจธาตุและการจัดพลังงานชี่ (Feng Shui) ---
    {
        "title": "ศาสตร์ฮวงจุ้ยเบญจธาตุ จัดโต๊ะทำงานหนุนอำนาจและตำแหน่ง",
        "step1": "1. ตำแหน่งมังกรเขียว (ซ้ายมือ): วางของสูง คอมพิวเตอร์ หนุนบารมี",
        "step2": "2. ตำแหน่งเสือขาว (ขวามือ): วางของต่ำ สมุดจด หนุนความสงบสมาธิ",
        "step3": "3. ด้านหลังที่นั่ง: ต้องเป็นผนังทึบหรือเก้าอี้พนักสูง เสมือนมีภูเขาหนุนหลัง",
        "hook": "💼 ทำงานติดขัดผู้ใหญ่ไม่มองเห็น? ฮวงจุ้ยโต๊ะทำงาน 3 จุด งานพุ่ง เงินก้อนเข้า!",
        "numbers": "๑ ๕ • ๕ ๖ • ๑ ๕ ๖",
        "image_url": "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&auto=format&fit=crop"
    },
    {
        "title": "ศาสตร์ฮวงจุ้ยกระเป๋าสตางค์ เปิดคลังเก็บทรัพย์ส่วนบุคคล",
        "step1": "1. เรียงธนบัตรตามมูลค่า หันพระพักตร์ไปในทิศทางเดียวกันเสมอ",
        "step2": "2. เคลียร์ใบเสร็จและขยะออกทุกวัน ไม่ให้ขัดขวางกระแสพลังชี่",
        "step3": "3. ใส่ธนบัตรขวัญถุงที่มีเลขท้ายคู่มงคล 24, 56, 78 เสริมดวงดูดทรัพย์",
        "hook": "👛 เงินรั่วไหลเก็บไม่อยู่? ศาสตร์ฮวงจุ้ยกระเป๋าสตางค์ เปลี่ยนเป็นคลังดูดเงิน!",
        "numbers": "๒ ๔ • ๕ ๖ • ๘ ๘ ๘",
        "image_url": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=800&auto=format&fit=crop"
    },
    {
        "title": "ศาสตร์ฮวงจุ้ยลานหน้าบ้าน เบิกทางรับพลังปราณชี่มั่งคั่ง",
        "step1": "1. ลานหน้าประตูบ้าน (หมิงถัง) ต้องโล่ง สะอาด แสงสว่างส่องถึงตลอดวัน",
        "step2": "2. ไม่วางรองเท้าเกะกะขวางทางลม เพราะจะกักเก็บพลังงานอัปมงคล",
        "step3": "3. ห้ามติดกระจกตรงข้ามประตูบ้านเด็ดขาด เพราะจะสะท้อนโชคลาภออกไป",
        "hook": "🚪 สำรวจหน้าบ้านด่วน! 3 จุดฮวงจุ้ยหมิงถัง เปิดประตูรับทรัพย์เข้าบ้านเต็มๆ",
        "numbers": "๑ ๙ • ๙ ๘ • ๑ ๖ ๘",
        "image_url": "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=800&auto=format&fit=crop"
    },
    # --- หมวดที่ 4: ศาสตร์การโคจรของดวงดาว 4 ธาตุ (Zodiac Transits) ---
    {
        "title": "เช็คดวงกลุ่มราศีธาตุไฟ รับพลังดาวอังคารและสุริยเทพ",
        "step1": "1. อิทธิพลพลังธาตุ: พลังขับเคลื่อนสูง มีโอกาสริเริ่มโปรเจกต์ใหญ่สำเร็จ",
        "step2": "2. การเงินและโชคลาภ: รายรับก้อนโตจากการลงมือทำและความกล้าตัดสินใจ",
        "step3": "3. สิ่งที่ต้องระวัง: ความใจร้อน ควรทำบุญน้ำดื่มเพื่อปรับสมดุลธาตุ",
        "hook": "🔥 ชาวราศีธาตุไฟเช็คดวงด่วน! ดาวโคจรเปิดทางสว่าง การเงินพร้อมพุ่งทะยาน",
        "numbers": "๑ ๓ • ๓ ๖ • ๑ ๓ ๖",
        "image_url": "https://images.unsplash.com/photo-1533090161767-e6ffed986c88?w=800&auto=format&fit=crop"
    },
    {
        "title": "เช็คดวงกลุ่มราศีธาตุดิน ดาวเสาร์และพฤหัสบดีหนุนทรัพย์",
        "step1": "1. อิทธิพลพลังธาตุ: ความมั่นคง ทรัพย์สิน อสังหาริมทรัพย์ผลิดอกออกผล",
        "step2": "2. การเงินและโชคลาภ: ได้รับผลตอบแทนจากสิ่งที่สั่งสมมานาน ปลดหนี้ได้",
        "step3": "3. สิ่งที่ต้องระวัง: อย่าลังเลจนเสียโอกาส เสริมดวงด้วยการทำบุญถวายที่ดิน",
        "hook": "🌍 ชาวราศีธาตุดินหมดเคราะห์หมดโศก! ดาวศุภเคราะห์หนุนฐานะการเงินปัง",
        "numbers": "๕ ๗ • ๒ ๘ • ๕ ๗ ๒",
        "image_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop"
    },
    {
        "title": "เช็คดวงกลุ่มราศีธาตุลม ดาวพุธและพระราหูเปิดทางค้าขาย",
        "step1": "1. อิทธิพลพลังธาตุ: การเจรจา คอนเนกชัน โลกออนไลน์นำพาความมั่งคั่ง",
        "step2": "2. การเงินและโชคลาภ: เงินเข้าจากหลายทิศทาง มีรายได้เสริมงอกเงย",
        "step3": "3. สิ่งที่ต้องระวัง: ระวังคำพูดกับคนใกล้ชิด เสริมดวงด้วยการถวายหลอดไฟ",
        "hook": "💨 ชาวราศีธาตุลมเตรียมรับทรัพย์! การเจรจาพารวย ดวงเงินทองหมุนเวียนยอดเยี่ยม",
        "numbers": "๔ ๘ • ๒ ๔ • ๔ ๘ ๒",
        "image_url": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop"
    },
    {
        "title": "เช็คดวงกลุ่มราศีธาตุน้ำ สัญชาตญาณแม่นยำ รับโชคลาภลับ",
        "step1": "1. อิทธิพลพลังธาตุ: เมตตามหานิยมสูง มีลางสังหรณ์แม่นยำเรื่องการเงิน",
        "step2": "2. การเงินและโชคลาภ: มีเกณฑ์ได้รับมรดก ลาภลอย หรือเงินที่ไม่คาดฝัน",
        "step3": "3. สิ่งที่ต้องระวัง: ระวังอารมณ์อ่อนไหว เสริมดวงด้วยการปล่อยปลาหน้าเขียง",
        "hook": "🌊 ชาวราศีธาตุน้ำดวงเปิดแล้ว! เมตตามหานิยมจับ รับโชคก้อนโตไม่คาดคิด",
        "numbers": "๒ ๖ • ๘ ๙ • ๒ ๖ ๙",
        "image_url": "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=800&auto=format&fit=crop"
    }
]

def get_curated_fallback_topic(category: str) -> dict:
    """ฐานข้อมูลหัวข้อคัดสรรระดับพรีเมียม (Curated Fallback) สำหรับกรณีไม่มีการเชื่อมต่อภายนอก"""
    if category == "LUCKY_FORTUNE":
        return random.choice(LUCKY_FORTUNE_TOPICS)
    elif category == "WORK_PRODUCTIVITY":
        return random.choice(WORK_PRODUCTIVITY_TOPICS)
    elif category == "LIFE_HACK_TIP":
        return random.choice(LIFE_HACK_TOPICS)
    elif category in ("TRENDING_NEWS", "CELEBRITY_TREND"):
        return fetch_real_live_rss(
            "https://rssfeeds.sanook.com/rss/feeds/sanook/news.index.xml",
            default_title="สรุปข่าวเด่นประเด็นร้อนวันนี้ เกาะติดสถานการณ์สำคัญ",
            default_summary="อัปเดตข่าวสารทันเหตุการณ์วันนี้ สรุปประเด็นสำคัญที่ทุกคนต้องรู้",
            default_hook="🚨 สรุปข่าวด่วนวันนี้! เรื่องเด่นที่ทุกคนต้องรู้",
            default_img="https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800&auto=format&fit=crop"
        )
    return random.choice(LIFE_HACK_TOPICS)

def get_pure_topic_data(mode: str) -> dict:
    # 1. ยกระดับด้วย Trend Intelligence Engine (สืบค้นร่องรอยดิจิทัล Google/Pantip/Forums + Follower Score >= 75)
    try:
        import trend_intelligence_scanner
        scanned = trend_intelligence_scanner.get_top_follower_viral_topic(mode)
        if scanned and scanned.get("title") and not is_topic_duplicate(scanned["title"]):
            record_topic_used(scanned["title"], f"INTEL_{mode}", scanned)
            return scanned
    except Exception as e_intel:
        logger.warning(f"Trend Intelligence Scanner ขัดข้องสำหรับ {mode}: {e_intel}")

    # 2. ระบบสำรองเดิมตามหมวดหมู่
    if mode == "TRENDING_NEWS":
        return fetch_real_news_headline()
    elif mode == "CELEBRITY_TREND":
        return fetch_real_celebrity_trend()
    elif mode == "LUCKY_FORTUNE":
        # 1. ลองค้นหาร่องรอยดิจิทัลด้านโหราศาสตร์สดจาก Web Search (Tavily/Google)
        import random
        if random.random() < 0.5:
            try:
                web_insight = fetch_authentic_astrology_insights()
                if web_insight and web_insight.get("title") and not is_topic_duplicate(web_insight["title"]):
                    return web_insight
            except Exception as e:
                logger.warning(f"ดึงเว็บโหราศาสตร์สดล้มเหลว: {e}")

        # 2. หมุนเวียนตามคลังตำราโหราศาสตร์แท้ (Mahathaksa / Numerology / Feng Shui / Zodiac)
        history = load_content_history()
        idx = 0
        if LAST_HORO_IDX_FILE.exists():
            try:
                idx = int(LAST_HORO_IDX_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                idx = 0
        
        chosen = None
        for step in range(len(LUCKY_FORTUNE_TOPICS)):
            cand = LUCKY_FORTUNE_TOPICS[(idx + step) % len(LUCKY_FORTUNE_TOPICS)]
            if not is_topic_duplicate(cand["title"], history):
                chosen = cand
                try:
                    LAST_HORO_IDX_FILE.write_text(str((idx + step + 1) % len(LUCKY_FORTUNE_TOPICS)), encoding="utf-8")
                except Exception:
                    pass
                break
        if not chosen:
            chosen = LUCKY_FORTUNE_TOPICS[idx % len(LUCKY_FORTUNE_TOPICS)]
            try:
                LAST_HORO_IDX_FILE.write_text(str((idx + 1) % len(LUCKY_FORTUNE_TOPICS)), encoding="utf-8")
            except Exception:
                pass
        record_topic_used(chosen["title"], "LUCKY_FORTUNE", chosen)
        return chosen
    elif mode == "LIFE_HACK_TIP":
        history = load_content_history()
        idx = 0
        if LAST_HACK_IDX_FILE.exists():
            try:
                idx = int(LAST_HACK_IDX_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                idx = 0
        
        chosen = None
        for step in range(len(LIFE_HACK_TOPICS)):
            cand = LIFE_HACK_TOPICS[(idx + step) % len(LIFE_HACK_TOPICS)]
            if not is_topic_duplicate(cand["title"], history):
                chosen = cand
                try:
                    LAST_HACK_IDX_FILE.write_text(str((idx + step + 1) % len(LIFE_HACK_TOPICS)), encoding="utf-8")
                except Exception:
                    pass
                break
        if not chosen:
            chosen = LIFE_HACK_TOPICS[idx % len(LIFE_HACK_TOPICS)]
            try:
                LAST_HACK_IDX_FILE.write_text(str((idx + 1) % len(LIFE_HACK_TOPICS)), encoding="utf-8")
            except Exception:
                pass
        record_topic_used(chosen["title"], "LIFE_HACK", chosen)
        return chosen
    elif mode == "WORK_PRODUCTIVITY":
        history = load_content_history()
        idx = 0
        if LAST_WORK_IDX_FILE.exists():
            try:
                idx = int(LAST_WORK_IDX_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                idx = 0
        
        chosen = None
        for step in range(len(WORK_PRODUCTIVITY_TOPICS)):
            cand = WORK_PRODUCTIVITY_TOPICS[(idx + step) % len(WORK_PRODUCTIVITY_TOPICS)]
            if not is_topic_duplicate(cand["title"], history):
                chosen = cand
                try:
                    LAST_WORK_IDX_FILE.write_text(str((idx + step + 1) % len(WORK_PRODUCTIVITY_TOPICS)), encoding="utf-8")
                except Exception:
                    pass
                break
        if not chosen:
            chosen = WORK_PRODUCTIVITY_TOPICS[idx % len(WORK_PRODUCTIVITY_TOPICS)]
            try:
                LAST_WORK_IDX_FILE.write_text(str((idx + 1) % len(WORK_PRODUCTIVITY_TOPICS)), encoding="utf-8")
            except Exception:
                pass
        record_topic_used(chosen["title"], "WORK_TIP", chosen)
        return chosen
    return random.choice(LIFE_HACK_TOPICS)

def build_standalone_voice_script(mode: str, topic_data: dict) -> str:
    """สร้างบทพูดเสียงพากย์ 14-18 วินาที (180-260 ตัวอักษร) เล่าเรื่องราวครบถ้วน เข้าใจง่าย ไม่ย่อจนห้วนหรือไม่รู้เรื่อง"""
    title = clean_render_text(topic_data.get("title", ""))
    hook = clean_render_text(topic_data.get("hook", title))
    summary = topic_data.get("summary", "") or topic_data.get("detail", "")
    summary = clean_render_text(re.sub(r'#+\s*', '', summary))
    summary = re.sub(r'https?://\S+', '', summary).strip()

    # 1. ถ้ามี voiceover_script จาก AI หรือ topic_data ที่สมบูรณ์ ให้ใช้ทันที (ไม่ตัดทอนให้เหลือแค่ 75-80 ตัวอักษร!)
    if topic_data.get("voiceover_script"):
        v_script = clean_render_text(topic_data["voiceover_script"])
        v_script = v_script.replace("นะครับ", "นะคะ").replace("นะคับ", "นะคะ").replace("ครับผม", "ค่ะ").replace("ครับ", "ค่ะ")
        # ตัดเฉพาะกรณีที่ยาวเกิน 320 ตัวอักษร เพื่อไม่ให้คลิปยาวเกิน 25 วินาที
        if len(v_script) > 320:
            v_script = safe_thai_truncate(v_script, 300)
        if len(v_script) >= 45:
            return v_script

    # 2. พยายามใช้ AI สร้างบทพากย์ที่เล่าเรื่องเป็นขั้นตอนอย่างลื่นไหลและเข้าใจกระจ่าง
    groq_keys = os.getenv("GROQ_API_KEY", "").split(",")
    models = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]

    prompt = (
        f"คุณคือนักพากย์หญิงวิดีโอสั้นสไตล์ป้าเข็ม น้ำเสียงอบอุ่น น่าฟัง สนุกสนาน เล่าเรื่องราวให้คนฟังเข้าใจง่าย ชัดเจน ตรงประเด็น\n"
        f"เขียนบทพูดเสียงพากย์ความยาว 14-18 วินาที (ประมาณ 180-260 ตัวอักษร) เล่าเรื่องราวให้เข้าใจกระจ่าง ไม่ย่อความจนห้วนหรือไม่รู้เรื่อง:\n"
        f"หมวดหมู่: {mode}\n"
        f"หัวข้อ: {title}\n"
        f"พาดหัว: {hook}\n"
        f"เนื้อหาเรื่องราว: {summary}\n\n"
        f"โครงสร้างบทพากย์ (3 ส่วนต่อเนื่อง):\n"
        f"1. เปิดเรื่อง: แนะนำหัวข้อและตัวละคร/เหตุการณ์ให้น่าสนใจ\n"
        f"2. เล่าเนื้อหา: เล่ารายละเอียดสำคัญ ข้อเท็จจริงที่เกิดขึ้น ให้คนฟังเข้าใจเรื่องราวทั้งหมดโดยไม่ต้องเดา\n"
        f"3. ปิดท้าย: ขมวดปม ชวนคอมเมนต์แลกเปลี่ยนความคิดเห็น และชวนกดติดตามช่อง ลงท้ายด้วย 'นะคะ' หรือ 'นะจ๊ะ' ห้ามใช้ 'ครับ' เด็ดขาด\n"
        f"ตอบเฉพาะบทพูดภาษาไทยล้วน 1 ย่อหน้าเท่านั้น ไม่มีเครื่องหมายคำพูด"
    )

    for k in groq_keys:
        k = k.strip()
        if not k or "mock" in k:
            continue
        for m in models:
            try:
                from openai import OpenAI
                client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k, timeout=8.0)
                resp = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": "คุณคือนักพากย์วิดีโอสั้นหญิง (ป้าเข็ม) น้ำเสียงอบอุ่น เล่าเรื่องราวเข้าใจง่าย ชัดถ้อยชัดคำ ลงท้าย นะคะ หรือ นะจ๊ะ ห้ามย่อความจนห้วนเด็ดขาด"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.6,
                    max_tokens=180
                )
                txt = clean_render_text((resp.choices[0].message.content or "").strip())
                txt = txt.replace('"', '').replace("'", "").replace("“", "").replace("”", "").strip()
                txt = txt.replace("นะครับ", "นะคะ").replace("นะคับ", "นะคะ").replace("ครับผม", "ค่ะ").replace("ครับ", "ค่ะ")
                if len(txt) >= 60:
                    return txt
            except Exception:
                continue

    # 3. Smart Natural Voiceover Fallback: ผสาน Hook และสาระสำคัญ 3 ข้อ ให้เป็นเรื่องราวที่สมบูรณ์
    s1 = topic_data.get("step1", "")
    s2 = topic_data.get("step2", "")
    s3 = topic_data.get("step3", "")
    steps = [re.sub(r"^\d+\.\s*", "", s).strip() for s in [s1, s2, s3] if s]

    if len(steps) >= 3:
        return f"{hook}! เรื่องนี้เริ่มจาก {steps[0]} โดยมีรายละเอียดสำคัญคือ {steps[1]} และบทสรุปคือ {steps[2]} ทุกคนมีความคิดเห็นยังไงกับเรื่องนี้ คอมเมนต์บอกกันหน่อย และอย่าลืมกดติดตามช่องไว้นะคะ"

    story = summary if summary and len(summary) > 20 else title
    story = re.split(r'ข่าว[อฮด]|##', story)[0].strip()
    return f"{hook}! เรื่องราวของ {title} ล่าสุด {story} ทุกคนคิดเห็นยังไง คอมเมนต์บอกกันหน่อย และอย่าลืมกดติดตามช่องไว้นะคะ"


def create_gradient_background(w: int, h: int, top_col: tuple, bot_col: tuple) -> Image.Image:
    """สร้างพื้นหลัง Gradient สีสดใส สวยงาม พรีเมียม เมื่อไม่มีภาพถ่ายจริง"""
    gradient_img = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(gradient_img)
    top_r, top_g, top_b = top_col[:3]
    bot_r, bot_g, bot_b = bot_col[:3]
    for y in range(h):
        ratio = y / max(1, h - 1)
        r = int(top_r + (bot_r - top_r) * ratio)
        g = int(top_g + (bot_g - top_g) * ratio)
        b = int(top_b + (bot_b - top_b) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
    return gradient_img


def create_typography_hero_card(w: int, h: int, thm: dict, top_text: str, phase_idx: int, mode: str) -> Image.Image:
    """สร้างการ์ดข้อความกราฟิกสีสันสดใสตรงกลาง (Hero Typography Card) กรณีไม่มีภาพถ่ายจริง"""
    card = Image.new("RGBA", (w, h), (255, 255, 255, 250))
    draw = ImageDraw.Draw(card)

    # กรอบการ์ด 2 ชั้น
    draw.rounded_rectangle([0, 0, w, h], radius=32, fill=(255, 255, 255, 250), outline=thm["brand_col"], width=5)
    draw.rounded_rectangle([10, 10, w - 10, h - 10], radius=24, outline=thm["card_border"], width=3)

    # แถบ Badge หัวข้อภายในการ์ด
    draw.rounded_rectangle([35, 35, w - 35, 125], radius=18, fill=thm["badge_bg"])
    f_badge = get_font(FONT_BOLD, 36)
    badge_title = thm["badge_txt"]
    draw.text((w // 2, 80), badge_title, font=f_badge, fill=(255, 255, 255), anchor="mm")

    # ข้อความไฮไลท์ตัวโตๆ ชัดเจน
    f_msg = get_font(FONT_BOLD, 42)
    lines = wrap_thai_lines(top_text, max_chars_per_line=20, max_lines=4)
    start_y = 220 if len(lines) <= 2 else 175
    for line in lines:
        draw.text((w // 2, start_y), line, font=f_msg, fill=(15, 23, 42), anchor="mm")
        start_y += 60

    # แถบจุดเด่นด้านล่างการ์ด
    f_sub = get_font(FONT_BOLD, 28)
    sub_text = "สาระน่ารู้ประจำวัน • สรุปให้ใน 1 นาที" if phase_idx < 2 else "กดติดตามช่องไว้ เพื่อรับสาระดีๆ ทุกวัน"
    draw.rounded_rectangle([35, h - 100, w - 35, h - 35], radius=16, fill=(241, 245, 249))
    draw.text((w // 2, h - 68), sub_text, font=f_sub, fill=thm["brand_col"], anchor="mm")

    return card


def extract_three_takeaways(topic_data: dict, mode: str) -> List[str]:
    """สกัดหรือสร้างสรุปสาระสำคัญ 3 ข้อสั้นกระชับ เพื่อแสดงผลบนการ์ด Infographic สำหรับคนปิดเสียงดู 100%"""
    # 1. ตรวจสอบ step1, step2, step3 ที่มีอยู่โดยตรง
    s1 = topic_data.get("step1", "").strip()
    s2 = topic_data.get("step2", "").strip()
    s3 = topic_data.get("step3", "").strip()
    direct_steps = [s for s in [s1, s2, s3] if s and len(s) >= 4]
    if len(direct_steps) >= 3:
        cleaned = []
        for s in direct_steps[:3]:
            c = re.sub(r'^\s*(?:\d+[\.\)]|•|\-)\s*', '', s).strip()
            cleaned.append(safe_thai_truncate(c, 48))
        return cleaned

    # 2. ถ้าไม่มี 3 steps แยก พยายามสกัดจาก detail หรือ summary หรือ title
    detail_txt = topic_data.get("detail") or topic_data.get("summary") or topic_data.get("title") or ""
    raw_parts = [p.strip() for p in re.split(r'[\n\r•]+|\d+\.\s*|[!?;]|\s{2,}', detail_txt) if p.strip() and len(p.strip()) >= 6]

    # หากได้ไม่ถึง 3 ส่วน ลองแยกด้วยช่องว่างเดี่ยว (คัดเฉพาะประโยค/ข้อความที่ยาวพอ >= 8 ตัวอักษร)
    if len(raw_parts) < 3 and " " in detail_txt:
        space_parts = [p.strip() for p in detail_txt.split(" ") if len(p.strip()) >= 8]
        if len(space_parts) >= 3:
            raw_parts = space_parts

    if len(raw_parts) >= 3:
        return [safe_thai_truncate(re.sub(r'^\s*(?:\d+[\.\)]|•|\-)\s*', '', p).strip(), 48) for p in raw_parts[:3]]
    elif len(raw_parts) == 2:
        p1 = safe_thai_truncate(re.sub(r'^\s*(?:\d+[\.\)]|•|\-)\s*', '', raw_parts[0]).strip(), 48)
        p2 = safe_thai_truncate(re.sub(r'^\s*(?:\d+[\.\)]|•|\-)\s*', '', raw_parts[1]).strip(), 48)
        p3 = "ติดตามความคืบหน้าของประเด็นนี้" if mode in ("TRENDING_NEWS", "CELEBRITY_TREND") else "ลองนำวิธีนี้ไปปรับใช้ดูได้ผลจริง"
        return [p1, p2, p3]

    # 3. Fallback ตามโหมดเนื้อหา ป้องกันข้อความว่างเด็ดขาด 100%
    defaults_by_mode = {
        "TRENDING_NEWS": [
            "สรุปประเด็นร้อนที่ทุกคนจับตามอง",
            "ข้อเท็จจริงสำคัญและผลกระทบ",
            "สิ่งจำเป็นที่ต้องรู้และติดตามต่อ"
        ],
        "CELEBRITY_TREND": [
            "ส่องเบื้องหลังกระแสไวรัลคนดัง",
            "ประเด็นจริงที่โซเชียลกำลังพูดถึง",
            "บทเรียนและเคล็ดลับความสำเร็จ"
        ],
        "LUCKY_FORTUNE": [
            "อิทธิพลดวงดาวและพลังงานมงคล",
            "เคล็ดลับเสริมดวงชะตารับทรัพย์",
            "สิ่งที่ควรระวังตามตำราโบราณ"
        ],
        "LIFE_HACK_TIP": [
            "เตรียมของใช้ง่ายๆ ในบ้าน",
            "ลงมือทำตามขั้นตอนใน 1 นาที",
            "คราบหลุดเกลี้ยง สะอาดเหมือนใหม่"
        ],
        "WORK_PRODUCTIVITY": [
            "เทคนิคโฟกัสงานสำคัญช่วงเช้า",
            "วิธีสื่อสารตรงเป้าได้งานรวดเร็ว",
            "เคล็ดลับเลิกงานตรงเวลาชีวิตแฮปปี้"
        ]
    }
    return defaults_by_mode.get(mode, defaults_by_mode["LIFE_HACK_TIP"])


def create_standalone_posters(mode: str, topic_data: dict, seed_id: int = 1) -> List[Image.Image]:
    """สร้างภาพโปสเตอร์ 1080x1920 (9:16) 3 จังหวะ สถาปัตยกรรม 100% Mute-First (ออกแบบเพื่อคนปิดเสียงดู)
    ใช้เทมเพลตมาตรฐานสตูดิโอ (video_template_engine) พร้อม 3 ภาพถ่ายจริงแยกกันเด็ดขาด (image_footprint_crawler)
    """
    import image_footprint_crawler
    import video_template_engine

    # 1. คัดเลือกภาพถ่ายจริง 3 ภาพที่ไม่ซ้ำกันเด็ดขาด (In-Article + Web Footprints + Editorial)
    distinct_urls = image_footprint_crawler.find_three_distinct_images(topic_data, mode)
    hero_images = []
    for u in distinct_urls:
        loaded = fetch_topic_image(u)
        hero_images.append(loaded)

    # ตรวจสอบภาพแรกต้องมีเสมอ
    if not hero_images or hero_images[0] is None:
        if topic_data.get("image_url"):
            fb = fetch_topic_image(topic_data["image_url"])
            if fb:
                hero_images = [fb, fb, fb]

    # 2. สกัดสรุปสาระสำคัญ 3 ข้อสั้นกระชับ
    takeaways = extract_three_takeaways(topic_data, mode)

    # 3. เรนเดอร์ด้วย Video Template Engine มาตรฐานสตูดิโอ
    posters = video_template_engine.render_cinematic_template_posters(
        mode=mode,
        topic_data=topic_data,
        hero_images=hero_images,
        takeaways=takeaways,
        channel_name="Anda",
        line_id="@137gsref"
    )
    return posters

def build_standalone_reel_video(mode: str, topic_data: dict, output_path: Path) -> bool:
    import auto_product_reels
    posters = create_standalone_posters(mode, topic_data)
    if not posters or len(posters) < 3:
        logger.error("❌ โปสเตอร์มีไม่ครบ 3 ภาพจริง — ยกเลิกการผลิตวิดีโอ 100% ป้องกันคลิปไม่มีรูปภาพ")
        return False
    voice_script = build_standalone_voice_script(mode, topic_data)
    audio_path = TEMP_DIR / f"tts_{int(time.time()*1000)}.mp3"
    tts_ok = auto_product_reels.generate_tts_audio(voice_script, audio_path)
    if not tts_ok or not auto_product_reels.verify_audio_file(audio_path):
        logger.error("❌ สร้างเสียงพากย์ไม่สำเร็จหรือเสียงเงียบ — ยกเลิกการผลิตวิดีโอ 100% ป้องกันคลิปไม่มีเสียง")
        if audio_path.exists():
            audio_path.unlink(missing_ok=True)
        return False

    audio_len = auto_product_reels.get_audio_duration(audio_path)
    # ตั้งความยาววิดีโอให้ยาวกว่าเสียงพากย์เล็กน้อย (+0.4 วินาที) จบประโยคสมบูรณ์ ไม่ตัดเสียง และไม่ค้างเงียบ
    target_duration = max(5.5, audio_len + 0.4)

    poster_paths = []
    for idx, p_img in enumerate(posters):
        p_path = TEMP_DIR / f"frame_{idx}_{int(time.time()*1000)}.jpg"
        p_img.save(p_path, "JPEG", quality=95)
        poster_paths.append(p_path)

    success = auto_product_reels.multiphase_posters_to_video(
        poster_paths, output_path, audio_path=audio_path, duration=target_duration
    )

    for p in poster_paths:
        try:
            p.unlink()
        except Exception:
            pass
    if audio_path.exists():
        try:
            audio_path.unlink()
        except Exception:
            pass

    return success

def sanitize_video_filename(name: str, fallback_prefix: str = "reel") -> str:
    """แปลงข้อความเป็นชื่อไฟล์วิดีโอที่ปลอดภัยบน Windows และระบบไฟล์ทั่วไป"""
    if not name:
        return f"{fallback_prefix}_{int(time.time())}.mp4"
    safe = re.sub(r'[\\/*?:"<>|\r\n\t]+', '_', name)
    safe = re.sub(r'\s+', '_', safe).strip(' ._-')
    if not safe:
        safe = f"{fallback_prefix}_{int(time.time())}"
    if not safe.lower().endswith(".mp4"):
        safe += ".mp4"
    return safe


def generate_standalone_reel(
    mode: Optional[str] = None,
    custom_title: Optional[str] = None,
    custom_filename: Optional[str] = None
) -> Optional[dict]:
    # มุ่งเน้น 100% ที่กระแสคนดังดาราและประเด็นร้อนโซเชียลเพื่อดันช่อง (ปลอดทริคแม่บ้าน)
    MODES = ["CELEBRITY_TREND", "TRENDING_NEWS"]
    selected_mode = mode if mode in MODES else random.choices(MODES, weights=[70, 30])[0]
    topic_data = get_pure_topic_data(selected_mode)

    if custom_title:
        topic_data["title"] = custom_title

    if custom_filename:
        filename = sanitize_video_filename(custom_filename, f"content_{selected_mode.lower()}")
    else:
        title_tag = re.sub(r'[\\/*?:"<>|\s]+', '_', topic_data.get('title', ''))[:32].strip(' ._-')
        filename = f"{selected_mode.lower()}_{title_tag}_{int(time.time())}.mp4" if title_tag else f"content_{selected_mode.lower()}_{int(time.time())}.mp4"

    target_path = PENDING_DIR / filename

    logger.info(f"🎬 กำลังผลิตคลิปคอนเทนต์เพียว ({selected_mode}): {topic_data.get('title')} -> {filename}")
    ok = build_standalone_reel_video(selected_mode, topic_data, target_path)
    if not ok or not target_path.exists():
        logger.error(f"❌ ผลิตคลิปคอนเทนต์ล้มเหลว: {filename}")
        return None

    # บันทึก metadata ลง products.json ทั้ง 2 จุด เพื่อให้ uploader ทุกตัวอ่านได้ตรงกัน
    products_meta = {}
    for p_path in [REELS_DIR / "products.json", ROOT_DIR / "products.json"]:
        if p_path.exists():
            try:
                loaded = json.loads(p_path.read_text(encoding="utf-8"))
                if loaded:
                    products_meta.update(loaded)
            except Exception:
                pass

    products_meta[filename] = {
        "product_name": topic_data.get("title", "สาระน่ารู้ เรื่องเด็ดประจำวัน"),
        "price": "",
        "category": "ดารา & ข่าวเรียลไทม์" if selected_mode == "CELEBRITY_TREND" else "ข่าวด่วนเรียลไทม์",
        "affiliate_link": "",
        "is_pure_content": True,
        "content_mode": selected_mode,
        "topic_data": topic_data
    }
    for p_path in [REELS_DIR / "products.json", ROOT_DIR / "products.json"]:
        try:
            p_path.write_text(json.dumps(products_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # บันทึกไฟล์แคปชั่นคู่ (.txt sidecar) เคียงข้างไฟล์วิดีโอเสมอ
    try:
        sidecar_txt = target_path.with_suffix(".txt")
        sidecar_caption = build_standalone_caption(selected_mode, topic_data, platform="facebook")
        sidecar_txt.write_text(sidecar_caption, encoding="utf-8")
        logger.info(f"📄 บันทึกไฟล์แคปชั่นคู่ (.txt sidecar) สำเร็จ: {sidecar_txt.name}")
    except Exception as e_sidecar:
        logger.warning(f"⚠️ บันทึกไฟล์แคปชั่นคู่ (.txt sidecar) ล้มเหลว: {e_sidecar}")

    logger.info(f"✅ ผลิตคลิปคอนเทนต์เพียวสำเร็จพร้อม Hero Visual Image -> {filename}")

    return {
        "filename": filename,
        "mode": selected_mode,
        "title": topic_data.get("title"),
        "hook": topic_data.get("hook"),
        "path": target_path,
        "video_path": str(target_path)
    }


def build_standalone_caption(mode: str, topic_data: dict, platform: str = "facebook") -> str:
    title = topic_data.get("title", "")
    hook = topic_data.get("hook", title)
    detail = topic_data.get("detail", topic_data.get("summary", ""))

    hashtags = {
        "TRENDING_NEWS": "#ข่าวด่วน #ข่าววันนี้ #สรุปข่าว #เกาะติดกระแส #ข่าวเด่น",
        "CELEBRITY_TREND": "#ข่าวบันเทิง #ดารา #คนดัง #ไวรัล #กระแสมาแรง #เทรนด์วันนี้",
        "LUCKY_FORTUNE": "#เลขเด็ด #ดวงวันนี้ #สายมู #เลขมงคล #ดวงเฮง #รับทรัพย์",
        "LIFE_HACK_TIP": "#ทริคดีๆ #งานบ้านที่รัก #แก้ปัญหา #ความรู้รอบตัว #แชร์ต่อ",
        "WORK_PRODUCTIVITY": "#ทริคคนทำงาน #มนุษย์เงินเดือน #ชีวิตออฟฟิศ #พัฒนาตัวเอง #ทำงานเก่ง"
    }

    tags_str = hashtags.get(mode, "#สาระน่ารู้ #เรื่องเด็ด")
    try:
        from hashtag_intelligence import generate_platform_hashtags
        dyn = generate_platform_hashtags(title or hook, category=mode, is_product=False)
        if dyn.get(platform):
            tags_str = dyn[platform]
    except Exception:
        pass

    if platform == "tiktok":
        final_tags = tags_str
    elif platform == "youtube":
        final_tags = tags_str if "#Shorts" in tags_str else f"#Shorts {tags_str}"
    else:
        final_tags = tags_str if ("#ของดีบอกต่อ" in tags_str or "#เกาะติดกระแส" in tags_str) else f"{tags_str} #เทรนด์วันนี้ #เรื่องนี้ต้องดู"

    line_cta = "👉 ทักแชทถามป้าเข็มได้ที่ LINE: @137gsref 👉 https://lin.ee/o9Kjp1N\n"
    lines = [
        f"{hook}\n",
        f"📌 {title}",
        f"{detail}\n",
        line_cta,
        f"💬 คุณคิดเห็นยังไงกับเรื่องนี้? คอมเมนต์คุยกันได้เลย 👇",
        f"🔔 กดติดตามช่องเพื่อรับชมเรื่องเด็ด สาระดีๆ และข่าวด่วนก่อนใคร!\n",
        f"{final_tags}"
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "LIFE_HACK_TIP"
    res = generate_standalone_reel(mode_arg)
    print("Result:", res)
