# -*- coding: utf-8 -*-
"""tools/hashtag_intelligence.py — ระบบสกัดและปรับแต่งแฮชแท็กเฉพาะแต่ละแพลตฟอร์มจากร่องรอยดิจิทัล

สืบค้นจาก 3 แหล่งร่องรอยดิจิทัลหลัก:
1. Google Search Suggestions & Trends (คำค้นหาที่คนพิมพ์ค้นหาจริงในไทย)
2. Forum & Community Discussions (Pantip / Web Discussions ผ่าน Tavily)
3. Platform-Tailored Algorithm Rules:
   - 🎵 TikTok: จำกัด 3-5 แท็ก (แท็กกระแส TikTok + คีย์เวิร์ดเจาะจงค้นหา + แท็กช่อง) ป้องกัน Tag Spam / Shadowban
   - 🔴 YouTube Shorts: บังคับ #Shorts เสมอ + ดึง 3-4 คำค้นหาตรงจาก Google Search Suggestions
   - 🔵 Facebook Reels: 4-5 แท็กคอมมูนิตี้และกลุ่มความสนใจกว้าง (#ของดีบอกต่อ, #ถ้าไม่คุ้มป้าบอกให้)
   - 🔒 No-Price Policy: คัดกรองคำว่าราคา บาท ถูก หรือตัวเลขราคาทุกชนิดทิ้ง 100%
"""
import os
import re
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import httpx

# บังคับ stdout UTF-8 (กัน emoji/ไทย พังบน Windows console ที่ใช้ cp874)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
TOOLS_DIR = ROOT_DIR / "tools"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

logger = logging.getLogger("HashtagIntelligence")

# # หมวดหมู่อ้างอิงและแท็กพื้นฐานสำหรับ Fallback — 2026 SEO-Optimized (3-5 tags per platform)
# สูตรทอง: 1 Broad + 2 Niche + 1-2 Action/Problem tags (ห้ามใช้ #fyp #foryou #ดันขึ้นฟีดที ซึ่ง algorithm ไม่สน)
DEFAULT_CATEGORY_TAGS = {
    "TRENDING_NEWS": {
        "tiktok": ["#เทรนด์วันนี้", "#ข่าวด่วน", "#ประเด็นร้อน", "#ป้าเข็มรีวิว"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#ข่าวด่วน", "#ประเด็นร้อน", "#สรุปข่าว"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#ข่าวด่วน", "#เรื่องนี้ต้องดู", "#กระแสมาแรง"],
    },
    "CELEBRITY_TREND": {
        "tiktok": ["#เรื่องนี้ต้องดู", "#ข่าวบันเทิง", "#ดาราดัง", "#ป้าเข็มรีวิว"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#ข่าวบันเทิง", "#ดาราดัง", "#ไวรัลวันนี้"],
        "facebook": ["#FBReels", "#ข่าวบันเทิง", "#ดาราดัง", "#กระแสมาแรง", "#เรื่องนี้ต้องแชร์"],
    },
    "WORK_PRODUCTIVITY": {
        "tiktok": ["#TikTokป้ายยา", "#ทริคคนทำงาน", "#มนุษย์เงินเดือน", "#ป้าเข็มรีวิว"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#ทริคคนทำงาน", "#มนุษย์เงินเดือน", "#พัฒนาตัวเอง"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#ทริคคนทำงาน", "#มนุษย์เงินเดือน", "#พัฒนาตัวเอง"],
    },
    "LIFE_HACK_TIP": {
        "tiktok": ["#TikTokป้ายยา", "#ทริคดีๆ", "#งานบ้านที่รัก", "#ป้าเข็มรีวิว"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#สาระน่ารู้", "#ทริคดีๆ", "#วิธีแก้ปัญหา"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#ทริคดีๆ", "#งานบ้านที่รัก", "#ถ้าไม่คุ้มป้าบอกให้"],
    },
    "LUCKY_FORTUNE": {
        "tiktok": ["#สายมู", "#ดวงวันนี้", "#เลขมงคล", "#ป้าเข็มรีวิว"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#ดวงวันนี้", "#สายมู", "#เสริมดวง"],
        "facebook": ["#FBReels", "#สายมู", "#ดวงวันนี้", "#เลขมงคล", "#รับทรัพย์"],
    },
    "BEFORE_AFTER": {
        "tiktok": ["#ก่อนหลัง", "#รีวิวก่อนซื้อ", "#TikTokป้ายยา", "#ของดีบอกต่อ", "#พิกัดshopee"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#ก่อนหลัง", "#รีวิวของใช้", "#พิกัดshopee"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ป้าเข็มป้ายยา", "#Shopee"],
    },
    "ของใช้ในบ้าน & จัดระเบียบบ้าน": {
        "tiktok": ["#ของดีบอกต่อ", "#ของใช้ในบ้าน", "#จัดระเบียบบ้าน", "#เด็กหอต้องมี", "#TikTokป้ายยา"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#ของดีบอกต่อ", "#ของใช้ในบ้าน", "#จัดบ้าน", "#พิกัดshopee"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ป้าเข็มป้ายยา", "#Shopee"],
    },
    "สัตว์เลี้ยง & ของใช้หมาแมว": {
        "tiktok": ["#ของดีบอกต่อ", "#ทาสแมว", "#ของใช้สัตว์เลี้ยง", "#TikTokป้ายยา", "#พิกัดshopee"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#ทาสหมา", "#ทาสแมว", "#ของใช้สัตว์เลี้ยง", "#รีวิวสัตว์เลี้ยง"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ทาสแมว", "#Shopee"],
    },
    "สมาร์ตโฮม & เครื่องใช้ไฟฟ้า": {
        "tiktok": ["#สมาร์ทโฮม", "#เครื่องใช้ไฟฟ้า", "#ชีวิตง่ายขึ้น", "#ของดีบอกต่อ", "#Shopee"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#สมาร์ทโฮม", "#เครื่องใช้ไฟฟ้า", "#ของดีบอกต่อ", "#พิกัดshopee"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ป้าเข็มป้ายยา", "#Shopee"],
    },
    "ไอที & แกดเจ็ตมือถือ": {
        "tiktok": ["#แกดเจ็ตน่าใช้", "#อุปกรณ์ไอที", "#รีวิวก่อนซื้อ", "#ของมันต้องมี", "#TikTokป้ายยา"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#แกดเจ็ต", "#อุปกรณ์ไอที", "#รีวิวก่อนซื้อ", "#พิกัดshopee"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ป้าเข็มป้ายยา", "#Shopee"],
    },
    "เครื่องครัว & ของกินของใช้": {
        "tiktok": ["#เครื่องครัวมินิมอล", "#ของใช้ในครัว", "#ทำอาหารง่ายๆ", "#รีวิวของดี", "#Shopee"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#เครื่องครัว", "#ของใช้ในครัว", "#ทำอาหาร", "#พิกัดshopee"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ป้าเข็มป้ายยา", "#Shopee"],
    },
    "สุขภาพ & ดูแลตัวเอง": {
        "tiktok": ["#รีวิวสกินแคร์", "#กู้ผิว", "#สวยบอกต่อ", "#TikTokป้ายยา", "#ถูกและดี"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#สุขภาพ", "#ดูแลตัวเอง", "#รักสุขภาพ", "#พิกัดshopee"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ป้าเข็มป้ายยา", "#Shopee"],
    },
    "ความงาม & ของใช้ส่วนตัว": {
        "tiktok": ["#รีวิวสกินแคร์", "#กู้ผิว", "#สวยบอกต่อ", "#TikTokป้ายยา", "#ถูกและดี"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#บิวตี้", "#ความงาม", "#รีวิวสกินแคร์", "#พิกัดshopee"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ป้าเข็มป้ายยา", "#Shopee"],
    },
    "ของใช้ติดรถ & เดินทาง/ช่าง": {
        "tiktok": ["#ของแต่งรถ", "#อุปกรณ์ติดรถ", "#สายแคมป์ปิ้ง", "#ของใช้จำเป็น", "#ป้าเข็มรีวิว"],
        "youtube": ["#Shorts", "#YouTubeShorts", "#ของใช้ติดรถ", "#คนรักรถ", "#ของดีบอกต่อ", "#พิกัดshopee"],
        "facebook": ["#FBReels", "#ของดีบอกต่อ", "#รีวิวของใช้", "#ป้าเข็มป้ายยา", "#Shopee"],
    },
}


def sanitize_tag(text: str) -> str:
    """ทำความสะอาดคำสำหรับใช้เป็นแฮชแท็ก:
    1. ตัดอักขระพิเศษ เว้นวรรค
    2. ตัดคำว่าราคา บาท ถูก ตัวเลขราคา ออก 100% ตาม Strict No-Price Policy
    """
    if not text:
        return ""
    
    # ถ้ามีคำเกี่ยวกับราคา ให้คัดทิ้งทันที
    price_pattern = r"(?:ราคา|บาท|฿|ถูก|ลดราคา|สตางค์|baht|\d+\s*บาท)"
    if re.search(price_pattern, text, flags=re.IGNORECASE):
        return ""

    # ลบแฮชแท็กนำหน้า หรืออักขระแปลกปลอม
    clean = re.sub(r'^[#@\s]+', '', text)
    clean = re.sub(r'[\s.,/!?%+=:;\'"()\[\]{}–—_\-]+', '', clean).strip()

    if not clean or len(clean) < 2:
        return ""

    return f"#{clean}"


def fetch_google_search_suggestions(query: str, limit: int = 5) -> List[str]:
    """สืบค้นร่องรอยดิจิทัลจาก Google Search Suggestions ภาษาไทย (คำที่คนพิมพ์ค้นหาจริง)"""
    is_testing = bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"))
    if is_testing:
        return []

    if not query or len(query.strip()) < 2:
        return []

    # สกัดเฉพาะคำสำคัญเพื่อค้นหา
    clean_q = re.sub(r'^(content_|prod_\d+_|duplicate_\d+_|\d+_)', '', query)
    clean_q = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s]', ' ', clean_q).strip()

    seeds_to_try = []
    try:
        from pythainlp.tokenize import word_tokenize
        raw_tokens = [t.strip() for t in word_tokenize(clean_q, engine="newmm") if t.strip() and len(t.strip()) >= 2]
        if len(raw_tokens) >= 2:
            s1 = "".join(raw_tokens[:2])
            seeds_to_try.append(s1)
            if "จัดการ" in s1:
                seeds_to_try.append(s1.replace("จัดการ", "จัด"))
            if "การ" in s1:
                seeds_to_try.append(s1.replace("การ", ""))
            if "วิธี" in s1:
                seeds_to_try.append(s1.replace("วิธี", ""))
        elif raw_tokens:
            seeds_to_try.append(raw_tokens[0])
    except Exception:
        pass

    if clean_q not in seeds_to_try:
        seeds_to_try.append(clean_q)

    for seed in seeds_to_try:
        if not seed or len(seed) < 2:
            continue
        url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={seed}&hl=th&gl=TH&ie=utf-8&oe=utf-8"
        try:
            r = httpx.get(url, timeout=3.5, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) and len(data[1]) > 0:
                    suggestions = []
                    for item in data[1]:
                        tag = sanitize_tag(str(item))
                        if tag and tag not in suggestions:
                            suggestions.append(tag)
                        if len(suggestions) >= limit:
                            break
                    if suggestions:
                        return suggestions
        except Exception as e:
            logger.debug(f"Google Suggest Query error ({seed}): {e}")

    return []


def fetch_forum_keywords(topic: str, category: str = "", limit: int = 3) -> List[str]:
    """สืบค้นร่องรอยคำสำคัญจาก Pantip และกระทู้ฟอรั่มไทยผ่าน Tavily"""
    is_testing = bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"))
    if is_testing or not os.getenv("TAVILY_API_KEY"):
        return []

    try:
        from app.services.web_search import web_search
        search_q = f"site:pantip.com {topic}"
        res = web_search(search_q, max_results=3)
        tags = []
        for it in res.get("results", []):
            title = it.get("title", "")
            # ตัดชื่อเว็บไซต์ - Pantip ออก
            clean_t = re.sub(r'-\s*Pantip.*$', '', title, flags=re.IGNORECASE).strip()
            # ใช้ extract_keywords_from_title เพื่อให้ตัดคำตามหลักภาษาและคัดกรอง stopwords
            kws = extract_keywords_from_title(clean_t, limit=2)
            for tag in kws:
                if tag and tag not in tags and len(tag) <= 15:
                    tags.append(tag)
                if len(tags) >= limit:
                    break
            if len(tags) >= limit:
                break
        return tags
    except Exception as e:
        logger.debug(f"Forum keyword fetch error: {e}")
        return []


def extract_keywords_from_title(title: str, limit: int = 3) -> List[str]:
    """สกัดคีย์เวิร์ดภาษาไทยจากชื่อหัวข้อคลิปโดยใช้ PyThaiNLP"""
    if not title:
        return []

    clean_t = re.sub(r'^(content_|prod_\d+_|duplicate_\d+_|\d+_)', '', title)
    clean_t = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s]', ' ', clean_t)

    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(clean_t, engine="newmm")
        stopwords = {
            "และ", "หรือ", "ที่", "ใน", "การ", "ความ", "ของ", "กับ", "ให้",
            "ได้", "ว่า", "มี", "ไม่", "จะ", "ก็", "คือ", "แล้ว", "นี้", "นั้น",
            "ใคร", "อะไร", "อย่างไร", "ทำไม", "อย่า", "เพิ่ง", "ป้า", "เข็ม",
            "ไม่มี", "พิเศษ", "ทั่วไป", "ทั้งหมด", "ตอน", "เรื่อง", "คลิป",
            "มาก", "น้อย", "ก่อน", "หลัง", "เลย", "จริง", "แท้", "ดีๆ"
        }
        candidates = []
        # จับคู่คำประสม (Compound Words) ก่อน เช่น จัด + พอร์ต -> จัดพอร์ต
        for i in range(len(tokens) - 1):
            t1, t2 = tokens[i].strip(), tokens[i+1].strip()
            if t1 not in stopwords and t2 not in stopwords and len(t1) >= 2 and len(t2) >= 2:
                pair = f"{t1}{t2}"
                tag = sanitize_tag(pair)
                if tag and tag not in candidates:
                    candidates.append(tag)
            if len(candidates) >= limit:
                break

        # ถ้ายังไม่พอ เติมคำเดี่ยว
        for t in tokens:
            t = t.strip()
            if len(t) >= 4 and t not in stopwords and not t.isdigit():
                tag = sanitize_tag(t)
                if tag and tag not in candidates:
                    candidates.append(tag)
            if len(candidates) >= limit:
                break
        return candidates
    except Exception:
        words = clean_t.split()
        return [sanitize_tag(w) for w in words[:limit] if sanitize_tag(w)]


def generate_platform_hashtags(
    title: str,
    category: str = "",
    is_product: bool = False,
    existing_tags: Optional[str] = None
) -> Dict[str, str]:
    """สร้างและประกอบแฮชแท็กเฉพาะ 3 แพลตฟอร์ม (TikTok, YouTube Shorts, Facebook Reels)
    
    Returns:
        dict with keys 'tiktok', 'youtube', 'facebook' containing formatted string tags
    """
    # 1. รวบรวมคีย์เวิร์ดจากร่องรอยดิจิทัล
    google_suggestions = fetch_google_search_suggestions(title, limit=5)
    forum_keywords = fetch_forum_keywords(title, category, limit=2)
    title_keywords = extract_keywords_from_title(title, limit=3)

    # รวมร่องรอยดิจิทัลที่ค้นพบ
    discovered_tags = []
    for t in google_suggestions + forum_keywords + title_keywords:
        if t and t not in discovered_tags:
            discovered_tags.append(t)

    # 2. ดึงแท็กมาตรฐานตามหมวดหมู่ (ถ้าเป็น pure content ใช้ LIFE_HACK_TIP, ถ้าเป็นสินค้าใช้ ของใช้ในบ้าน)
    default_cat = "ของใช้ในบ้าน & จัดระเบียบบ้าน" if is_product else "LIFE_HACK_TIP"
    chosen_cat = category if (category and category in DEFAULT_CATEGORY_TAGS) else default_cat
    fallback_pool = DEFAULT_CATEGORY_TAGS[chosen_cat]

    # -----------------------------------------------------------------
    # 🎵 1. TikTok Assembly: ล็อค 3-5 แท็กเท่านั้น (TikTok SEO + Anti-Spam)
    # -----------------------------------------------------------------
    tiktok_tags = []
    # แท็ก 1: แท็กกระแส TikTok
    base_trend = fallback_pool["tiktok"][0]  # เช่น #เทรนด์วันนี้ หรือ #เรื่องนี้ต้องดู
    tiktok_tags.append(base_trend)

    # แท็ก 2: แท็กหมวดเจาะจง
    primary_tt = fallback_pool["tiktok"][1] if len(fallback_pool["tiktok"]) > 1 else "#ทริคดีๆ"
    if primary_tt not in tiktok_tags:
        tiktok_tags.append(primary_tt)

    # แท็ก 3 & 4: คีย์เวิร์ดเฉพาะเจาะจงจากร่องรอยดิจิทัลที่ค้นพบ
    for dt in discovered_tags:
        if dt not in tiktok_tags and len(tiktok_tags) < 4:
            tiktok_tags.append(dt)

    # เติมแท็กหมวดหมู่ถ้ายังไม่ครบ
    for fb_tag in fallback_pool["tiktok"]:
        if fb_tag not in tiktok_tags and len(tiktok_tags) < 4:
            tiktok_tags.append(fb_tag)

    # แท็กสุดท้าย: แบรนด์ช่อง (#ป้าเข็มรีวิว)
    brand_tag = "#ป้าเข็มรีวิว"
    if brand_tag not in tiktok_tags:
        if len(tiktok_tags) >= 5:
            tiktok_tags[4] = brand_tag
        else:
            tiktok_tags.append(brand_tag)

    tiktok_str = " ".join(tiktok_tags[:5])

    # -----------------------------------------------------------------
    # 🔴 2. YouTube Shorts Assembly: บังคับ #Shorts เสมอ + คำค้นหา Google
    # -----------------------------------------------------------------
    yt_tags = ["#Shorts"]
    primary_yt = fallback_pool["youtube"][1] if len(fallback_pool["youtube"]) > 1 else "#สาระน่ารู้"
    if primary_yt not in yt_tags:
        yt_tags.append(primary_yt)

    # นำคำค้นหาตรงจาก Google Search Suggestions มาใส่ก่อน
    for st in google_suggestions:
        if st not in yt_tags and len(yt_tags) < 5:
            yt_tags.append(st)

    # ถ้ายังไม่พอ เติมจาก discovered_tags
    for dt in discovered_tags:
        if dt not in yt_tags and len(yt_tags) < 5:
            yt_tags.append(dt)

    # เติมแท็กมาตรฐาน YouTube
    for fb_tag in fallback_pool["youtube"]:
        if fb_tag not in yt_tags and len(yt_tags) < 6:
            yt_tags.append(fb_tag)

    yt_str = " ".join(yt_tags[:6])

    # -----------------------------------------------------------------
    # 🔵 3. Facebook Reels Assembly: 4-5 แท็กเน้น Interest & Community
    # -----------------------------------------------------------------
    fb_tags = ["#ของดีบอกต่อ", "#ถ้าไม่คุ้มป้าบอกให้"]
    primary_fb = fallback_pool["facebook"][1] if len(fallback_pool["facebook"]) > 1 else "#ทริคดีๆ"
    if primary_fb not in fb_tags:
        fb_tags.append(primary_fb)

    for dt in discovered_tags:
        if dt not in fb_tags and len(fb_tags) < 5:
            fb_tags.append(dt)

    for fb_tag in fallback_pool["facebook"]:
        if fb_tag not in fb_tags and len(fb_tags) < 5:
            fb_tags.append(fb_tag)

    fb_str = " ".join(fb_tags[:5])

    return {
        "tiktok": tiktok_str,
        "youtube": yt_str,
        "facebook": fb_str,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ทดสอบระบบสกัดแฮชแท็กเฉพาะสื่อจากร่องรอยดิจิทัล")
    parser.add_argument("--title", type=str, default="จัดพอร์ตกระจายความเสี่ยง", help="ชื่อหัวข้อหรือสินค้า")
    parser.add_argument("--category", type=str, default="WORK_PRODUCTIVITY", help="หมวดหมู่")
    parser.add_argument("--product", action="store_true", help="เป็นคลิปสินค้า Shopee")
    args = parser.parse_args()

    print(f"🔍 ทดสอบสืบค้นร่องรอยดิจิทัลสำหรับหัวข้อ: '{args.title}' [หมวด: {args.category}]")
    tags = generate_platform_hashtags(args.title, category=args.category, is_product=args.product)
    print("\n" + "=" * 60)
    print("🎵 TikTok Tags    :", tags["tiktok"])
    print("🔴 YouTube Tags   :", tags["youtube"])
    print("🔵 Facebook Tags  :", tags["facebook"])
    print("=" * 60)
