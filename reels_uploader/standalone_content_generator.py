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

FONT_BOLD = Path(r"C:\Windows\Fonts\tahoma.ttf")
if not FONT_BOLD.exists():
    for f_name in ["THSarabunNew Bold.ttf", "Garuda-Bold.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]:
        p = Path(f"/usr/share/fonts/truetype/{f_name}")
        if p.exists():
            FONT_BOLD = p
            break
        p_win = Path(f"C:/Windows/Fonts/{f_name}")
        if p_win.exists():
            FONT_BOLD = p_win
            break

def get_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()

def clean_render_text(text: str) -> str:
    """ลบอิโมจิและอักขระพิเศษที่ทำให้ Pillow แสดงผลเป็นกล่องสี่เหลี่ยม □"""
    if not text:
        return ""
    # Strip emojis and symbols that standard fonts cannot render
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    cleaned = re.sub(r"[\u2600-\u27ff]", "", cleaned)
    cleaned = re.sub(r"[\u2300-\u23ff]", "", cleaned)
    cleaned = re.sub(r"[\u2b50-\u2b55]", "", cleaned)
    cleaned = re.sub(r"[\ufe0e\ufe0f]", "", cleaned)
    cleaned = cleaned.replace("🚨", "").replace("🔴", "").replace("💬", "").replace("👇", "").replace("💡", "").replace("🌟", "").replace("🔮", "").replace("💼", "").replace("🏠", "").replace("✨", "").replace("🦛", "")
    return cleaned.strip()

def wrap_thai_lines(text: str, max_chars_per_line: int = 24, max_lines: int = 8) -> List[str]:
    text = clean_render_text(text)
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

def fetch_real_live_rss(feed_url: str, default_title: str, default_summary: str, default_hook: str, default_img: str) -> Dict[str, Any]:
    """ดึงข้อมูลข่าว/กระแสสดใหม่วันนี้ 100% จาก RSS Feed พร้อมรูปภาพจริง 3 ภาพจากสำนักข่าว"""
    try:
        r = httpx.get(feed_url, timeout=6.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.text:
            root = ET.fromstring(r.text)
            candidates = []
            for it in root.iter():
                if it.tag.split("}")[-1] == "item":
                    t_el = it.find("title")
                    d_el = it.find("description")
                    enc_el = it.find("enclosure")
                    if t_el is not None and t_el.text:
                        title = html.unescape(t_el.text).strip()
                        desc = html.unescape(d_el.text or "").strip() if d_el is not None and d_el.text else ""
                        img_url = enc_el.get("url") if enc_el is not None else ""
                        if len(title) >= 12 and not any(k in title for k in ["หวยออนไลน์", "คาสิโน"]):
                            candidates.append({
                                "title": title[:65],
                                "detail": desc[:160] if desc else title,
                                "summary": desc[:160] if desc else title,
                                "img_url": img_url
                            })
            if candidates:
                # เลือกข่าวด่วนล่าสุดอันดับ 1 ที่เพิ่งโพสต์สดๆ ร้อนๆ ทันที
                chosen = candidates[0]
                chosen_img = chosen.get("img_url") or default_img
                return {
                    "title": chosen["title"],
                    "detail": chosen["detail"],
                    "summary": chosen["summary"],
                    "hook": f"🚨 {chosen['title'][:45]}!",
                    "image_url": chosen_img,
                    "image_urls": [chosen_img, chosen_img, chosen_img]
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
    """ดึงข่าวด่วนและเทรนด์กระแสระดับโลกจาก BBC World / Global Media โดยล็อครูปภาพจริงตรงกับเนื้อหา 100%"""
    feed_urls = {
        "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "entertain": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    }
    url = feed_urls.get(category, feed_urls["world"])

    try:
        r = httpx.get(url, timeout=8.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.text:
            root = ET.fromstring(r.text)
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
                        items.append((title_en, desc_en, img_url))

            if items:
                # ดึงข่าวสดใหม่ล่าสุดอันดับ 1 ที่มีรูปภาพพร้อมจาก BBC
                valid_items = [it for it in items if it[2]] or items
                chosen_en_title, chosen_en_desc, chosen_img = valid_items[0]
                exact_img = chosen_img or "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800&auto=format&fit=crop"

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
                        resp = client.chat.completions.create(
                            model="qwen/qwen3.8-27b",
                            messages=[{"role": "user", "content": prompt}],
                            response_format={"type": "json_object"}
                        )
                        data = json.loads(resp.choices[0].message.content)
                        return {
                            "title": data.get("thai_title", chosen_en_title[:50]),
                            "detail": data.get("summary", chosen_en_desc[:120]),
                            "summary": data.get("summary", chosen_en_desc[:120]),
                            "hook": data.get("hook", f"ด่วนระดับโลก! {chosen_en_title[:35]}"),
                            "image_url": exact_img,
                            "image_urls": [exact_img, exact_img, exact_img]
                        }
                    except Exception as e_ai:
                        logger.warning(f"Groq แปลข่าวระดับโลกผิดพลาด: {e_ai}")
                        continue
    except Exception as e:
        logger.warning(f"ดึงข่าวระดับโลก {url} ผิดพลาด: {e}")

    return fetch_real_live_rss(
        "https://www.thairath.co.th/rss/news",
        default_title="สรุปข่าวเด่นประเด็นร้อนวันนี้ เกาะติดสถานการณ์สำคัญ",
        default_summary="อัปเดตข่าวสารทันเหตุการณ์วันนี้ สรุปประเด็นสำคัญที่ทุกคนต้องรู้",
        default_hook="🚨 สรุปข่าวด่วนวันนี้! เรื่องเด่นที่ทุกคนต้องรู้",
        default_img="https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800&auto=format&fit=crop"
    )

def fetch_real_news_headline() -> Dict[str, Any]:
    """สลับดึงข่าวด่วนระดับโลก (BBC World) และข่าวด่วนสำคัญ"""
    return fetch_global_world_trend("world")

def fetch_real_celebrity_trend() -> Dict[str, Any]:
    """สลับดึงกระแสคนดังระดับโลก (BBC Entertainment & Pop Culture) และข่าวบันเทิงกระแสแรง"""
    import random
    if random.random() < 0.6:
        return fetch_global_world_trend("entertain")
    return fetch_real_live_rss(
        "https://www.thairath.co.th/rss/entertain",
        default_title="เจาะลึกกระแสคนดังไวรัล ประเด็นฮิตที่โซเชียลพูดถึง",
        default_summary="เรื่องราวคนดังและกระแสไวรัลที่กำลังเป็นที่จับตามองทั่วโลกออนไลน์",
        default_hook="🌟 ส่องกระแสคนดังวันนี้! เรื่องที่ทุกคนกำลังพูดถึง",
        default_img="https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800&auto=format&fit=crop"
    )

def fetch_real_horoscope_trend() -> Dict[str, Any]:
    return fetch_real_live_rss(
        "https://www.thairath.co.th/rss/horoscope",
        default_title="เช็คดวงวันนี้ ราศีไหนมีเกณฑ์รับทรัพย์ การเงินพุ่ง",
        default_summary="แนวทางดวงชะตาและเคล็ดลับเสริมโชคลาภประจำวัน รับพลังบวกและโชคดี",
        default_hook="🔮 เช็คดวงวันนี้! ราศีไหนมีเกณฑ์ดวงเฮงรับทรัพย์",
        default_img="https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop"
    )

CACHE_IMG_DIR = REELS_DIR / "cached_topic_images"
CACHE_IMG_DIR.mkdir(parents=True, exist_ok=True)

def fetch_topic_image(image_url: str, title: str = "") -> Image.Image:
    """ดาวน์โหลดและ cache ภาพประกอบความคมชัดสูงสำหรับคอนเทนต์เพียว 100%"""
    if not image_url:
        return create_fallback_topic_image(title)

    import hashlib
    img_hash = hashlib.md5(image_url.encode("utf-8")).hexdigest()
    cached_path = CACHE_IMG_DIR / f"{img_hash}.jpg"

    if cached_path.exists():
        try:
            return Image.open(cached_path).convert("RGBA")
        except Exception:
            pass

    try:
        r = httpx.get(image_url, timeout=10.0, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            import io
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            cached_path.write_bytes(r.content)
            return img
    except Exception as e:
        logger.warning(f"ดาวน์โหลดภาพ {image_url} ล้มเหลว: {e}")

    return create_fallback_topic_image(title)

def create_fallback_topic_image(title: str = "") -> Image.Image:
    """สร้างภาพกราฟิกสำรองความละเอียดสูงกรณีไม่มีอินเทอร์เน็ต"""
    img = Image.new("RGBA", (800, 620), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([10, 10, 790, 610], radius=24, fill=(30, 41, 59), outline=(52, 211, 153), width=4)
    f = get_font(FONT_BOLD, 42)
    lines = wrap_thai_lines(title or "สาระน่ารู้ เรื่องเด็ดวันนี้", max_chars_per_line=18, max_lines=3)
    y = 260
    for l in lines:
        draw.text((400, y), l, font=f, fill=(255, 255, 255), anchor="mm")
        y += 55
    return img

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
]

def get_pure_topic_data(mode: str) -> dict:
    if mode == "TRENDING_NEWS":
        return fetch_real_news_headline()
    elif mode == "CELEBRITY_TREND":
        return fetch_real_celebrity_trend()
    elif mode == "LUCKY_FORTUNE":
        return fetch_real_horoscope_trend()
    elif mode == "LIFE_HACK_TIP":
        return random.choice(LIFE_HACK_TOPICS)
    elif mode == "WORK_PRODUCTIVITY":
        return random.choice(WORK_PRODUCTIVITY_TOPICS)
    return random.choice(LIFE_HACK_TOPICS)

def build_standalone_voice_script(mode: str, topic_data: dict) -> str:
    groq_keys = os.getenv("GROQ_API_KEY", "").split(",")
    models = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]

    hook = topic_data.get("hook", topic_data.get("title", ""))
    title = topic_data.get("title", "")
    detail = topic_data.get("detail", topic_data.get("summary", ""))

    prompt = (
        f"คุณคือนักเล่าเรื่องวิดีโอสั้นระดับมืออาชีพ 9:16 (Shorts / Reels / TikTok) ที่เน้นยอดวิวและยอดผู้ติดตามสูงสุด\n"
        f"จงเขียนบทพูดเสียงพากย์ความยาวเป๊ะ 7-10 วินาที (สั้นกระชับ รวม 50-80 ตัวอักษรไทย)\n"
        f"หัวข้อคอนเทนต์: {title}\n"
        f"รายละเอียด: {detail}\n"
        f"หมวดหมู่: {mode}\n\n"
        f"กฎเหล็ก:\n"
        f"1. **ห้ามขายของ ห้ามพูดเรื่องสินค้า ห้ามชวนแอดไลน์เด็ดขาด**\n"
        f"2. ประโยคที่ 1 (0-3 วิ): Hook หยุดดูอย่างตื่นเต้น น่าติดตาม เช่น '{hook}'\n"
        f"3. ประโยคที่ 2 (4-7 วิ): สรุปประเด็นสำคัญ/สาระที่น่าทึ่งให้เข้าใจทันทีใน 1 ประโยค\n"
        f"4. ประโยคที่ 3 (8-10 วิ): ชวนกดติดตามช่องหรือคอมเมนต์ เช่น 'กดติดตามช่องไว้ จะได้ไม่พลาดเรื่องเด็ดทุกวันนะ!' หรือ 'คิดเห็นยังไงคอมเมนต์มาคุยกันได้เลย!'\n"
        f"5. ห้ามมีตัวเลขราคาเด็ดขาด\n"
        f"6. ตอบเฉพาะข้อความบทพูดภาษาไทยล้วนๆ 1 ย่อหน้าเท่านั้น"
    )

    for k in groq_keys:
        k = k.strip()
        if not k or "mock" in k:
            continue
        for m in models:
            try:
                from openai import OpenAI
                client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k, timeout=10.0)
                resp = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": "คุณคือนักเขียนสคริปต์วิดีโอสั้นเน้นยอดวิวและเพิ่มผู้ติดตามช่อง 7-10 วินาที"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=140
                )
                txt = (resp.choices[0].message.content or "").strip()
                txt = txt.replace('"', '').replace("'", "").replace("“", "").replace("”", "").strip()
                if len(txt) >= 40:
                    return txt
            except Exception:
                continue

    if mode == "TRENDING_NEWS":
        return f"🚨 สรุปข่าวด่วนวันนี้! {title[:40]} กดติดตามช่องไว้ จะได้ไม่พลาดสรุปข่าวสำคัญทุกวันนะครับ"
    elif mode == "CELEBRITY_TREND":
        return f"🚨 {hook} เรื่องราวกระแสไวรัลที่คนพูดถึงกันทั้งโลก! ชอบเรื่องเด็ดๆ แบบนี้ กดติดตามช่องไว้ได้เลย"
    elif mode == "LUCKY_FORTUNE":
        return f"🔮 {hook} ขอให้ทุกคนโชคดีรับทรัพย์ปังๆ กดติดตามช่องไว้เพื่อรับพลังบวกและเลขมงคลทุกวันนะครับ"
    elif mode == "LIFE_HACK_TIP":
        return f"💡 {hook} ทริคง่ายๆ ลองเอาไปใช้กันดูนะครับ กดติดตามช่องไว้ จะได้ไม่พลาดทริคดีๆ ทุกวัน"
    else:
        return f"💼 {hook} เทคนิคง่ายๆ ช่วยให้ทำงานสบายขึ้น กดติดตามช่องไว้ จะได้ไม่พลาดเคล็ดลับดีๆ นะครับ"

def create_standalone_posters(mode: str, topic_data: dict, seed_id: int = 1) -> List[Image.Image]:
    """สร้างภาพโปสเตอร์ 1080x1920 (9:16) 3 จังหวะ พร้อม Hero Visual Image ขนาดใหญ่ตรงกลาง หยุดดูใน 3 วินาที"""
    from PIL import ImageFilter

    W, H = 1080, 1920
    themes = {
        "TRENDING_NEWS": {
            "bg": (15, 23, 42), "badge_bg": (220, 38, 38), "badge_txt": "🚨 สรุปข่าวด่วนวันนี้",
            "card_border": (239, 68, 68), "accent": (254, 202, 202), "brand_col": (220, 38, 38)
        },
        "CELEBRITY_TREND": {
            "bg": (30, 10, 60), "badge_bg": (168, 85, 247), "badge_txt": "🌟 กระแสไวรัลคนดัง",
            "card_border": (216, 180, 254), "accent": (253, 230, 138), "brand_col": (168, 85, 247)
        },
        "LUCKY_FORTUNE": {
            "bg": (67, 10, 15), "badge_bg": (234, 179, 8), "badge_txt": "🔮 เลขเด็ด & ดวงมงคล",
            "card_border": (250, 204, 21), "accent": (254, 240, 138), "brand_col": (234, 179, 8)
        },
        "LIFE_HACK_TIP": {
            "bg": (6, 78, 59), "badge_bg": (16, 185, 129), "badge_txt": "💡 ทริคแม่บ้านแก้ปัญหา",
            "card_border": (52, 211, 153), "accent": (167, 243, 208), "brand_col": (16, 185, 129)
        },
        "WORK_PRODUCTIVITY": {
            "bg": (12, 74, 96), "badge_bg": (6, 182, 212), "badge_txt": "💼 ทริคคนทำงานออฟฟิศ",
            "card_border": (34, 211, 238), "accent": (165, 243, 252), "brand_col": (6, 182, 212)
        }
    }
    thm = themes.get(mode, themes["LIFE_HACK_TIP"])
    title = topic_data.get("title", "")
    hook = topic_data.get("hook", title)
    raw_images = topic_data.get("image_urls") or ([topic_data.get("image_url")] if topic_data.get("image_url") else [])
    
    # โหลดภาพ 3 ภาพ สำหรับ 3 จังหวะของวิดีโอ (0-3 วิ, 4-7 วิ, 8-10 วิ)
    phase_raw_imgs = []
    for i in range(3):
        u = raw_images[i] if i < len(raw_images) and raw_images[i] else (raw_images[0] if raw_images else "")
        phase_raw_imgs.append(fetch_topic_image(u, title))

    hero_w, hero_h = 860, 600
    hero_y = 250
    hero_x = (W - hero_w) // 2

    phases = [
        # Phase 1: Hook 3 วินาทีแรก (ภาพข่าวที่ 1)
        {"top_text": hook, "top_badge": thm["badge_txt"], "cta_text": "👉 ดูรายละเอียดและสาระสำคัญด้านล่างได้เลย!", "img_idx": 0},
        # Phase 2: เจาะลึกเนื้อหา (ภาพข่าวที่ 2)
        {"top_text": title, "top_badge": "📌 สาระน่ารู้ประจำวัน", "cta_text": "💡 เคล็ดลับและเรื่องจริงที่ต้องรู้!", "img_idx": 1},
        # Phase 3: ชวนกดติดตาม (ภาพข่าวที่ 3)
        {"top_text": "กดติดตามช่องไว้ ไม่พลาดเรื่องเด็ด!", "top_badge": "🔔 อัปเดตเรื่องใหม่ทุกวัน", "cta_text": "คอมเมนต์แลกเปลี่ยนความคิดเห็นกันได้เลย 👇", "img_idx": 2}
    ]

    posters = []
    for ph in phases:
        curr_hero_img = phase_raw_imgs[ph["img_idx"]]

        # 1. สร้างพื้นหลังเบลอ (Blurred Background) จากภาพของจังหวะนั้นๆ
        bg_img = curr_hero_img.copy()
        bg_ratio = max(W / bg_img.width, H / bg_img.height)
        bg_resized = bg_img.resize((int(bg_img.width * bg_ratio), int(bg_img.height * bg_ratio)), Image.Resampling.LANCZOS)
        left = (bg_resized.width - W) // 2
        top = (bg_resized.height - H) // 2
        bg_cropped = bg_resized.crop((left, top, left + W, top + H))
        bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=35))
        dark_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 150))
        base_bg = Image.alpha_composite(bg_blurred, dark_overlay)

        # 2. เตรียม Hero Visual Image ตรงกลาง พร้อมซูม/จัดมุมตามจังหวะ 1, 2, 3
        zoom_factor = 1.0 if ph["img_idx"] == 0 else (1.18 if ph["img_idx"] == 1 else 1.08)
        img_ratio = max(hero_w / curr_hero_img.width, hero_h / curr_hero_img.height) * zoom_factor
        scaled_w = int(curr_hero_img.width * img_ratio)
        scaled_h = int(curr_hero_img.height * img_ratio)
        scaled_img = curr_hero_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
        crop_x = max(0, (scaled_w - hero_w) // 2)
        crop_y = max(0, (scaled_h - hero_h) // 2)
        cropped_hero = scaled_img.crop((crop_x, crop_y, crop_x + hero_w, crop_y + hero_h))

        # Mask มุมโค้งมนให้รูป Hero
        mask = Image.new("L", (hero_w, hero_h), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([0, 0, hero_w, hero_h], radius=32, fill=255)

        canvas = base_bg.copy()
        draw = ImageDraw.Draw(canvas)

        # 1. แถบ Highlight ด้านบน 0-3 วิ (เหลืองทอง/สีสดใส)
        draw.rounded_rectangle([40, 50, W - 40, 220], radius=32, fill=thm["badge_bg"], outline=(255, 255, 255), width=4)
        f_top = get_font(FONT_BOLD, 42)
        top_lines = wrap_thai_lines(ph["top_text"], max_chars_per_line=24, max_lines=2)
        if len(top_lines) == 1:
            draw.text((W // 2, 135), top_lines[0], font=f_top, fill=(255, 255, 255), anchor="mm")
        else:
            draw.text((W // 2, 105), top_lines[0], font=f_top, fill=(255, 255, 255), anchor="mm")
            draw.text((W // 2, 165), top_lines[1], font=f_top, fill=(255, 255, 255), anchor="mm")

        # 2. แปะ Hero Visual Image ตรงกลาง (ภาพตรงกับเนื้อหา 100%)
        draw.rounded_rectangle([hero_x - 6, hero_y - 6, hero_x + hero_w + 6, hero_y + hero_h + 6], radius=36, fill=(255, 255, 255), outline=thm["card_border"], width=5)
        canvas.paste(cropped_hero, (hero_x, hero_y), mask)

        # 3. กล่อง Infographic การแก้ปัญหา / สาระความรู้ ด้านล่าง
        card_y = 890
        card_h = 780
        draw.rounded_rectangle([50, card_y, W - 50, card_y + card_h], radius=36, fill=(255, 255, 255, 245), outline=thm["brand_col"], width=4)

        # หัวข้อในกล่อง
        f_card_title = get_font(FONT_BOLD, 38)
        title_lines = wrap_thai_lines(title, max_chars_per_line=24, max_lines=2)
        t_y = card_y + 55
        for tl in title_lines:
            draw.text((W // 2, t_y), tl, font=f_card_title, fill=(15, 23, 42), anchor="mm")
            t_y += 48

        draw.line([(80, t_y + 10), (W - 80, t_y + 10)], fill=(220, 220, 220), width=2)
        step_y = t_y + 40

        f_step = get_font(FONT_BOLD, 34)
        if mode in ("LIFE_HACK_TIP", "WORK_PRODUCTIVITY"):
            s1 = topic_data.get("step1", "")
            s2 = topic_data.get("step2", "")
            s3 = topic_data.get("step3", "")
            for s in [s1, s2, s3]:
                if s:
                    draw.rounded_rectangle([80, step_y, W - 80, step_y + 110], radius=20, fill=(240, 249, 255), outline=thm["badge_bg"], width=2)
                    draw.text((110, step_y + 55), s[:32], font=f_step, fill=(15, 23, 42), anchor="lm")
                    step_y += 130
        elif mode == "LUCKY_FORTUNE":
            nums = topic_data.get("numbers", "7 9 • 8 2 • 3 5 8")
            draw.rounded_rectangle([80, step_y + 20, W - 80, step_y + 260], radius=24, fill=(254, 240, 138), outline=(234, 179, 8), width=4)
            f_num = get_font(FONT_BOLD, 54)
            draw.text((W // 2, step_y + 140), nums, font=f_num, fill=(185, 28, 28), anchor="mm")
            step_y += 300
        else:
            detail_txt = topic_data.get("detail", topic_data.get("summary", ""))
            det_lines = wrap_thai_lines(detail_txt, max_chars_per_line=24, max_lines=6)
            for dl in det_lines:
                draw.text((W // 2, step_y + 25), dl, font=f_step, fill=(40, 40, 40), anchor="mm")
                step_y += 55

        # 4. แถบ Conversion Bar ด้านล่างสุด (y=1700 to 1860) — เน้นกดติดตามและมีส่วนร่วม (ไม่มีอีโมจิกล่องสี่เหลี่ยม)
        draw.rounded_rectangle([40, 1700, W - 40, 1860], radius=26, fill=(15, 23, 42), outline=(34, 197, 94), width=4)
        f_foot1 = get_font(FONT_BOLD, 33)
        f_foot2 = get_font(FONT_BOLD, 27)
        draw.text((W // 2, 1745), "กดติดตามช่องไว้ ไม่พลาดเรื่องเด็ดทุกวัน!", font=f_foot1, fill=(255, 255, 255), anchor="mm")
        draw.text((W // 2, 1805), "คอมเมนต์แลกเปลี่ยนความคิดเห็นกันได้เลย", font=f_foot2, fill=(74, 222, 128), anchor="mm")

        posters.append(canvas.convert("RGB"))
    return posters

def build_standalone_reel_video(mode: str, topic_data: dict, output_path: Path) -> bool:
    import auto_product_reels
    voice_script = build_standalone_voice_script(mode, topic_data)
    audio_path = TEMP_DIR / f"tts_{int(time.time()*1000)}.mp3"
    tts_ok = auto_product_reels.generate_tts_audio(voice_script, audio_path)
    audio_len = auto_product_reels.get_audio_duration(audio_path) if tts_ok else 5.0

    # ตั้งความยาววิดีโอให้ยาวกว่าเสียงพากย์เสมอ (+0.8 วินาที) เพื่อให้เสียงจบประโยคสมบูรณ์ ไม่ถูกตัดก่อนเด็ดขาด
    target_duration = max(7.5, audio_len + 0.8)

    posters = create_standalone_posters(mode, topic_data)
    poster_paths = []
    for idx, p_img in enumerate(posters):
        p_path = TEMP_DIR / f"frame_{idx}_{int(time.time()*1000)}.jpg"
        p_img.save(p_path, "JPEG", quality=95)
        poster_paths.append(p_path)

    success = auto_product_reels.multiphase_posters_to_video(
        poster_paths, output_path, audio_path=audio_path if audio_len > 0 else None, duration=target_duration
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

def generate_standalone_reel(mode: Optional[str] = None) -> Optional[dict]:
    """ผลิตคลิปคอนเทนต์เพียว 1 คลิป พร้อมลงทะเบียนใน products.json และบันทึกเข้า pending_videos/"""
    MODES = ["LIFE_HACK_TIP", "TRENDING_NEWS", "CELEBRITY_TREND", "LUCKY_FORTUNE", "WORK_PRODUCTIVITY"]
    selected_mode = mode if mode in MODES else random.choice(MODES)
    topic_data = get_pure_topic_data(selected_mode)

    filename = f"content_{selected_mode.lower()}_{int(time.time())}.mp4"
    target_path = PENDING_DIR / filename

    logger.info(f"🎬 กำลังผลิตคลิปคอนเทนต์เพียว ({selected_mode}): {topic_data.get('title')} -> {filename}")
    ok = build_standalone_reel_video(selected_mode, topic_data, target_path)
    if not ok or not target_path.exists():
        logger.error(f"❌ ผลิตคลิปคอนเทนต์ล้มเหลว: {filename}")
        return None

    # บันทึก metadata ลง products.json เพื่อให้ uploader โพสต์ได้ถูกต้อง
    products_json_path = REELS_DIR / "products.json"
    products_meta = {}
    if products_json_path.exists():
        try:
            products_meta = json.loads(products_json_path.read_text(encoding="utf-8"))
        except Exception:
            products_meta = {}

    products_meta[filename] = {
        "product_name": topic_data.get("title", "สาระน่ารู้ เรื่องเด็ดประจำวัน"),
        "price": "",
        "category": "สาระความรู้ & คอนเทนต์เพียว",
        "affiliate_link": "",
        "is_pure_content": True,
        "content_mode": selected_mode,
        "topic_data": topic_data
    }
    products_json_path.write_text(json.dumps(products_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"✅ ผลิตคลิปคอนเทนต์เพียวสำเร็จพร้อม Hero Visual Image -> {filename}")

    return {
        "filename": filename,
        "mode": selected_mode,
        "title": topic_data.get("title"),
        "path": target_path
    }


def build_standalone_caption(mode: str, topic_data: dict) -> str:
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

    lines = [
        f"{hook}\n",
        f"📌 {title}",
        f"{detail}\n",
        f"💬 คุณคิดเห็นยังไงกับเรื่องนี้? คอมเมนต์คุยกันได้เลย 👇",
        f"🔔 กดติดตามช่องเพื่อรับชมเรื่องเด็ด สาระดีๆ และข่าวด่วนก่อนใคร!\n",
        hashtags.get(mode, "#สาระน่ารู้ #เรื่องเด็ด #เรื่องนี้ต้องรู้")
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "LIFE_HACK_TIP"
    res = generate_standalone_reel(mode_arg)
    print("Result:", res)
