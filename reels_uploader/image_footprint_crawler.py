# -*- coding: utf-8 -*-
"""image_footprint_crawler.py — เครื่องมือค้นหาร่องรอยดิจิทัลและดึงภาพถ่ายจริง 3 ภาพสำหรับ 1 วิดีโอ 100%
ค้นหาจาก:
  1. 🌐 In-Article Web Scraper (ร่องรอยดิจิทัลในหน้าบทความจริง: ดึงรูปภาพทั้งหมดที่ช่างภาพข่าวลงไว้ในเนื้อหา)
  2. 🔎 Direct News Site Footprints (สืบค้นคลังข่าวดิจิทัล Sanook / สื่อหลัก สำหรับข่าวนั้นๆ)
  3. 🔍 Multi-Engine Web Search (Tavily / Google Digital Footprints ดึงภาพถ่ายจริงที่เกี่ยวข้องตรงประเด็น)
  4. 📚 Authentic Thematic Editorial Library (คลังภาพถ่ายจริงสำรองแยกตามหมวดหมู่ ไม่ใช้ภาพการ์ตูน AI เด็ดขาด)
"""
import html
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, quote

import httpx

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def is_valid_image_url(url: str) -> bool:
    """ตรวจสอบว่า URL เป็นไฟล์รูปภาพจริง ไม่ใช่ไอคอน หรือแบนเนอร์โฆษณา"""
    if not url or not url.startswith("http"):
        return False
    lower = url.lower().split("?")[0]
    forbidden_substrings = [
        "icon", "logo", "avatar", "spacer", "pixel", "tracker", "badge",
        "advert", "banner", "btn_", "arrow", "favicon", "emoji", "footer"
    ]
    if any(fb in lower for fb in forbidden_substrings):
        return False
    return any(lower.endswith(ext) for ext in IMAGE_EXTS) or "images.unsplash.com" in url or "s.isanook.com" in url or "bbci.co.uk" in url


def scrape_article_images(article_url: str, max_images: int = 5) -> List[str]:
    """แกะรอยดิจิทัลจากหน้าเว็บต้นทาง ดึงภาพถ่ายจริงที่ช่างภาพลงไว้ในบทความ"""
    if not article_url:
        return []
    found_urls = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "th,en-US;q=0.9,en;q=0.8",
        }
        with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(article_url)
            if resp.status_code == 200 and resp.text:
                html_text = resp.text

                # 1. ค้นหา <meta property="og:image" content="...">
                og_imgs = re.findall(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html_text, re.IGNORECASE)
                og_imgs += re.findall(r'<meta[^>]+content=[\'"]([^\'"]+)[\'"][^>]+property=[\'"]og:image[\'"]', html_text, re.IGNORECASE)
                for u in og_imgs:
                    u = html.unescape(u.strip())
                    if is_valid_image_url(u) and u not in found_urls:
                        found_urls.append(u)

                # 2. ค้นหา <img> tags ในเนื้อหาข่าว (article, entry-content, gallery, body)
                img_srcs = re.findall(r'<img[^>]+(?:data-src|data-original|src)=[\'"]([^\'"]+)[\'"]', html_text, re.IGNORECASE)
                for raw_src in img_srcs:
                    src = html.unescape(raw_src.strip())
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        parsed = urlparse(article_url)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"

                    # ปรับขนาดภาพ Sanook ให้เป็นความละเอียดสูง
                    if "s.isanook.com" in src:
                        src = re.sub(r'/(?:240|300|600)/', '/1200/', src)

                    if is_valid_image_url(src) and src not in found_urls:
                        found_urls.append(src)
                        if len(found_urls) >= max_images:
                            break

                logger.info(f"🌐 แกะรอยบทความ {article_url[:40]}... พบภาพจริง {len(found_urls)} ภาพ")
    except Exception as e:
        logger.warning(f"แกะรอยภาพจากหน้าเว็บ {article_url} ผิดพลาด: {e}")

    return found_urls[:max_images]


def search_sanook_digital_footprints(query: str, max_results: int = 3) -> List[str]:
    """สืบค้นร่องรอยดิจิทัลจากคลังสื่อ Sanook โดยตรงตามคีย์เวิร์ด"""
    if not query:
        return []
    found = []
    try:
        clean_q = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s]', ' ', query).strip()
        words = [w for w in clean_q.split() if len(w) >= 2][:4]
        term = "+".join(words)
        if not term:
            return []
        search_url = f"https://www.sanook.com/search/?q={quote(term)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        with httpx.Client(timeout=6.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(search_url)
            if resp.status_code == 200 and resp.text:
                imgs = re.findall(r'<img[^>]+(?:data-src|src)=[\'"]([^\'"]*s\.isanook\.com[^\'"]+)[\'"]', resp.text)
                for img_u in imgs:
                    img_u = html.unescape(img_u.strip())
                    img_u = re.sub(r'/(?:240|300|600)/', '/1200/', img_u)
                    if is_valid_image_url(img_u) and img_u not in found:
                        found.append(img_u)
                        if len(found) >= max_results:
                            break
    except Exception as e:
        logger.warning(f"สืบค้นคลังข่าวดิจิทัล Sanook ผิดพลาด: {e}")
    return found


def search_web_images(query: str, max_results: int = 4) -> List[str]:
    """สืบค้นภาพถ่ายจริงจากอินเทอร์เน็ตด้วย Tavily / Web Search Engine"""
    if not query:
        return []

    clean_q = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s]', ' ', query).strip()
    words = [w for w in clean_q.split() if len(w) >= 2][:6]
    search_term = " ".join(words)
    if not search_term:
        search_term = query[:40]

    found = []
    try:
        import sys
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from app.services.web_search import _tavily_search, _clean_image_urls
        raw_tv = _tavily_search(search_term, max_results=3, search_depth="basic")
        if raw_tv and "images" in raw_tv:
            cleaned_tv = _clean_image_urls(raw_tv["images"])
            for u in cleaned_tv:
                if u not in found:
                    found.append(u)
        logger.info(f"🔍 ค้นภาพเน็ต Tavily '{search_term}': พบ {len(found)} ภาพ")
    except Exception as e_tv:
        logger.warning(f"ค้นภาพ Tavily ล้มเหลว ({e_tv}) — ดำเนินการต่อด้วย fallback")

    return found[:max_results]


# คลังภาพถ่ายจริงสำรองคุณภาพระดับสตูดิโอ (Authentic Photography ไม่ใช่การ์ตูน AI)
EDITORIAL_FALLBACK_IMAGES = {
    "TRENDING_NEWS": [
        "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1080&auto=format&fit=crop", # สำนักข่าว & สื่อ
        "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=1080&auto=format&fit=crop", # ไมโครโฟนแถลงข่าว
        "https://images.unsplash.com/photo-1495020689067-958852a7765e?w=1080&auto=format&fit=crop", # หนังสือพิมพ์ / เอกสารข่าว
    ],
    "CELEBRITY_TREND": [
        "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=1080&auto=format&fit=crop", # เวทีคอนเสิร์ต / ศิลปิน
        "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1080&auto=format&fit=crop", # อีเวนต์บันเทิง
        "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=1080&auto=format&fit=crop", # แสงสีเวทีใหญ่
    ],
    "LUCKY_FORTUNE": [
        "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1080&auto=format&fit=crop", # ทองคำ & เหรียญมงคล
        "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=1080&auto=format&fit=crop", # ท้องฟ้าราตรีดวงดาว
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1080&auto=format&fit=crop", # คริสตัลและพลังงานมงคล
    ],
    "LIFE_HACK_TIP": [
        "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=1080&auto=format&fit=crop", # อุปกรณ์ทำความสะอาดบ้าน
        "https://images.unsplash.com/photo-1527515637462-cff94eecc1ac?w=1080&auto=format&fit=crop", # บ้านสะอาด เรียบร้อย
        "https://images.unsplash.com/photo-1563453392212-326f5e854473?w=1080&auto=format&fit=crop", # สเปรย์และอุปกรณ์แม่บ้าน
    ],
    "WORK_PRODUCTIVITY": [
        "https://images.unsplash.com/photo-1497366216548-37526070297c?w=1080&auto=format&fit=crop", # ออฟฟิศและโต๊ะทำงาน
        "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=1080&auto=format&fit=crop", # โน้ตบุ๊กและกาแฟทำงาน
        "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=1080&auto=format&fit=crop", # ทีมงานประชุมสำเร็จ
    ]
}


def find_three_distinct_images(
    topic_data: dict,
    mode: str = "TRENDING_NEWS"
) -> List[str]:
    """สืบค้นและคัดเลือกภาพถ่ายจริง 3 ภาพที่ไม่ซ้ำกันเด็ดขาด (3 Unique Images in 1 Video)
    ตามคำสั่งผู้ใช้: แกะรอยดิจิทัลจากหน้าเว็บ, เอกสาร, ฟอรั่ม, และ Google Search
    """
    selected_images = []
    seen = set()

    def add_img(u: str):
        if u and u not in seen and is_valid_image_url(u):
            seen.add(u)
            selected_images.append(u)

    # 1. รูปภาพหลักจาก RSS / ข่าวต้นทาง (Image 1)
    primary_img = topic_data.get("image_url") or ""
    add_img(primary_img)

    # 2. แกะรอยจาก URL บทความต้นทาง (In-Article Scrape)
    article_link = (
        topic_data.get("link") or
        topic_data.get("url") or
        topic_data.get("article_url") or
        (topic_data.get("details", {}).get("url") if isinstance(topic_data.get("details"), dict) else "")
    )
    if article_link and len(selected_images) < 3:
        scraped = scrape_article_images(article_link, max_images=4)
        for u in scraped:
            add_img(u)
            if len(selected_images) >= 3:
                break

    # 3. ร่องรอยดิจิทัลจากคลังสื่อตรง (Direct Media Footprints)
    if len(selected_images) < 3:
        search_query = topic_data.get("title") or topic_data.get("hook") or ""
        sanook_imgs = search_sanook_digital_footprints(search_query, max_results=3)
        for u in sanook_imgs:
            add_img(u)
            if len(selected_images) >= 3:
                break

    # 4. หากยังไม่ครบ 3 ภาพ ให้สืบค้นร่องรอยดิจิทัลบนอินเทอร์เน็ต (Web & Google Search)
    if len(selected_images) < 3:
        search_query = topic_data.get("title") or topic_data.get("hook") or ""
        web_imgs = search_web_images(search_query, max_results=4)
        for u in web_imgs:
            add_img(u)
            if len(selected_images) >= 3:
                break

    # 5. หากยังไม่ครบ 3 ภาพ ให้ดึงจากคลังภาพถ่ายจริงคุณภาพสูง (Editorial Fallback)
    fallbacks = EDITORIAL_FALLBACK_IMAGES.get(mode, EDITORIAL_FALLBACK_IMAGES["TRENDING_NEWS"])
    for fb_u in fallbacks:
        if len(selected_images) >= 3:
            break
        add_img(fb_u)

    logger.info(f"📸 คัดเลือกภาพถ่ายจริงครบ 3 ภาพสำหรับวิดีโอ ({mode}): {len(selected_images)} ภาพ")
    return selected_images[:3]
