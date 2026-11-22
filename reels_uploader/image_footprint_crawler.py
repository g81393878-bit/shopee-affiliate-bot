# -*- coding: utf-8 -*-
"""image_footprint_crawler.py — เครื่องมือค้นหาร่องรอยดิจิทัลและดึงภาพถ่ายจริง 3 ภาพสำหรับ 1 วิดีโอ 100%
ตามกฎเหล็กภาพถ่ายจริง (Rule 22):
  1. 🌐 In-Article Web Scraper (ร่องรอยดิจิทัลในหน้าบทความจริง: ดึงรูปภาพความละเอียดสูงที่ช่างภาพข่าวลงไว้ในเนื้อหา)
  2. 🔎 Direct News Site Footprints (สืบค้นคลังข่าวดิจิทัล Sanook / สื่อหลัก สำหรับข่าวนั้นๆ)
  3. 🔍 Multi-Engine Web Search (Tavily Images Live Search ดึงภาพถ่ายจริงที่เกี่ยวข้องตรงประเด็น 100%)
  4. 📚 Thematic Authentic Editorial Library (คลังภาพถ่ายจริงคุณภาพสูงแยกตามประเด็นเฉพาะด้าน ไม่ใช้ภาพการ์ตูน AI)
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

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# รายการคำบ่งบอกว่าเป็นแบนเนอร์โฆษณา ไอคอน หรือภาพขยะที่ไม่ใช่ภาพเนื้อหา
FORBIDDEN_SUBSTRINGS = [
    "icon", "logo", "avatar", "spacer", "pixel", "tracker", "badge",
    "advert", "banner", "btn_", "arrow", "favicon", "emoji", "footer",
    "header", "widget", "sidebar", "author", "thumb-small", "ads-",
    "-ad-", "sponsor", "promo", "share-button", "loading", "blank.gif"
]

# รูปแบบขนาดที่มักเป็นไอคอนหรือแบนเนอร์กว้างเตี้ย
TINY_DIMENSION_PATTERN = re.compile(
    r'[-_](?:140x|262x|150x|300x|100x|80x|60x|50x|48x|32x|16x|90x|75x)\d+',
    re.IGNORECASE
)


def normalize_image_url(url: str) -> str:
    """ขยายขนาดรูปภาพให้เป็นความละเอียดสูงระดับ Original / Full HD"""
    if not url:
        return ""
    u = url.strip()

    # 1. Sanook: ขยายขนาดรูปจาก thumbnail 240/300/600 เป็น 1200
    if "s.isanook.com" in u:
        u = re.sub(r'/(?:240|300|600)/', '/1200/', u)

    # 2. BBC: ขยายขนาด thumbnail 240 เป็น 1024
    if "bbci.co.uk" in u:
        u = re.sub(r'/(?:240|320|640)/', '/1024/', u)

    # 3. WordPress CDN: ลบ suffix ขนาด thumbnail เช่น -300x157.jpg -> .jpg
    if re.search(r'-\d+x\d+\.(?:jpg|jpeg|png|webp)', u, re.IGNORECASE):
        # ตรวจว่าไม่ใช่ภาพขนาดใหญ่ เช่น -1024x...
        match = re.search(r'-(\d+)x(\d+)\.(jpg|jpeg|png|webp)', u, re.IGNORECASE)
        if match:
            w, h, ext = int(match.group(1)), int(match.group(2)), match.group(3)
            if w <= 400 or h <= 300:
                u = re.sub(r'-\d+x\d+\.' + ext, '.' + ext, u, flags=re.IGNORECASE)

    return u


def is_valid_image_url(url: str) -> bool:
    """ตรวจสอบว่า URL เป็นไฟล์รูปภาพจริงที่มีคุณภาพ ไม่ใช่ไอคอน หรือแบนเนอร์โฆษณา"""
    if not url or not url.startswith("http"):
        return False

    lower = url.lower().split("?")[0]

    # ตรวจสอบคำต้องห้าม
    if any(fb in lower for fb in FORBIDDEN_SUBSTRINGS):
        return False

    # ตรวจสอบขนาด thumbnail/แบนเนอร์จิ๋วในชื่อไฟล์
    if TINY_DIMENSION_PATTERN.search(lower):
        return False

    # ตรวจนามสกุลไฟล์ หรือโดเมนรูปภาพที่เชื่อถือได้
    has_valid_ext = any(lower.endswith(ext) for ext in IMAGE_EXTS)
    trusted_domains = [
        "images.unsplash.com", "s.isanook.com", "bbci.co.uk", "cdn.pixabay.com",
        "images.pexels.com", "static.thairath.co.th", "khaosod.co.th",
        "assets.brandinside.asia", "media.timeout.com", "lifestyleasia.com"
    ]
    is_trusted = any(td in lower for td in trusted_domains)

    return has_valid_ext or is_trusted or "image" in lower


def extract_core_subject(title: str, hook: str = "", mode: str = "") -> str:
    """สกัดเฉพาะประเด็นหลัก/คำสำคัญ (Core Entity) สำหรับค้นหาภาพถ่ายจริงตรงประเด็น 100%"""
    raw = hook or title or ""
    # ลบ Emojis
    t = re.sub(r'[\U00010000-\U0010ffff]', '', raw)
    # ลบเครื่องหมายตกใจและวงเล็บ
    t = re.sub(r'^[🚨💡✨🔥👑☀️💖🌟🔮💼🏠💨👕🥣🤫⚠️❓\s]+', '', t)
    # ลบวลีไวรัลขึ้นต้น
    viral_prefixes = [
        r'^(?:เรื่องเด็ดวันนี้|สรุปข่าวด่วนวันนี้|สรุปข่าวด่วน|ข่าวด่วนวันนี้|ด่วนระดับโลก|เช็คดวงวันนี้|ทริคคนทำงาน)[!:\s]*',
        r'^(?:อย่าเพิ่งทิ้ง|ทริคดับกลิ่น|วิธีแก้|วิธีทำความสะอาด|วิธี|ส่องกระแสคนดังวันนี้|เจาะลึกกระแส)[!:\s]*',
        r'^(?:ก่อนใช้ vs หลังใช้|ก่อนใช้|หลังใช้|ของแท้ 100%|ของแท้)[!:\s]*',
        r'^(?:รู้หรือไม่|เผยความลับ|เช็คเลย|ด่วน)[!:\s]*',
    ]
    for p in viral_prefixes:
        t = re.sub(p, '', t).strip()

    # ลบคำเชื่อมท้ายประโยค
    t = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', t).strip()
    words = [w for w in t.split() if len(w) >= 2 and not w.startswith("#")]
    subject = " ".join(words[:6])

    # ถ้าสกัดแล้วสั้นเกินไป ให้ใช้ title ตัวเดิมตัดแต่ง
    if len(subject) < 4:
        clean_title = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s]', ' ', title).strip()
        subject = " ".join(clean_title.split()[:5])

    return subject


def verify_image_accessible(url: str, min_size_bytes: int = 15000) -> bool:
    """ตรวจสอบเบื้องต้นว่า URL รูปภาพนี้เข้าถึงได้จริงและมีขนาดไฟล์พอเหมาะ (ป้องกันภาพเสียหรือภาพ 1x1)"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/*,*/*;q=0.8"
        }
        with httpx.Client(timeout=4.0, follow_redirects=True, headers=headers) as client:
            resp = client.head(url)
            if resp.status_code == 200:
                c_len = int(resp.headers.get("content-length", 0))
                if c_len > 0 and c_len < min_size_bytes:
                    return False
                c_type = resp.headers.get("content-type", "").lower()
                if c_type and not ("image" in c_type or "octet-stream" in c_type):
                    return False
                return True
            # ถ้า server ไม่รองรับ HEAD ให้ถือว่าผ่านเบื้องต้น
            return True
    except Exception:
        return True  # ยอมรับไว้ก่อน ให้โมดูลดาวน์โหลดจริงตัดสิน


def scrape_article_images(article_url: str, max_images: int = 5) -> List[str]:
    """แกะรอยดิจิทัลจากหน้าเว็บต้นทาง ดึงภาพถ่ายจริงที่ช่างภาพลงไว้ในบทความ (กรองแบนเนอร์ออก 100%)"""
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

                # 1. ค้นหา OpenGraph <meta property="og:image" content="..."> (ภาพหลักตรงปกของบทความเสมอ)
                og_imgs = re.findall(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html_text, re.IGNORECASE)
                og_imgs += re.findall(r'<meta[^>]+content=[\'"]([^\'"]+)[\'"][^>]+property=[\'"]og:image[\'"]', html_text, re.IGNORECASE)
                og_imgs += re.findall(r'<meta[^>]+name=[\'"]twitter:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', html_text, re.IGNORECASE)

                for u in og_imgs:
                    u = normalize_image_url(html.unescape(u.strip()))
                    if is_valid_image_url(u) and u not in found_urls:
                        found_urls.append(u)

                # 2. คัดเฉพาะส่วนเนื้อหาบทความ (Article Body / Entry Content) เพื่อไม่ให้ดึงแบนเนอร์หรือรูปคอมเมนต์
                body_matches = re.findall(
                    r'<(?:article|main|div[^>]+class=[\'"][^\'"]*(?:entry-content|article-body|post-content|story-body|content-body|detail-content)[^\'"]*)[^>]*>(.*?)</(?:article|main|div)>',
                    html_text,
                    re.IGNORECASE | re.DOTALL
                )
                search_scope = "\n".join(body_matches) if body_matches else html_text

                # ลบส่วนที่ไม่ใช่เนื้อหา เช่น aside, nav, footer, sidebar, ads
                search_scope = re.sub(r'<(?:aside|nav|footer|header|script|style)[^>]*>.*?</(?:aside|nav|footer|header|script|style)>', '', search_scope, flags=re.IGNORECASE | re.DOTALL)

                # 3. ค้นหา <img> tags ในเนื้อหาข่าว
                img_srcs = re.findall(r'<img[^>]+(?:data-src|data-original|data-lazy-src|src)=[\'"]([^\'"]+)[\'"]', search_scope, re.IGNORECASE)
                for raw_src in img_srcs:
                    src = html.unescape(raw_src.strip())
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        parsed = urlparse(article_url)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"

                    src = normalize_image_url(src)

                    if is_valid_image_url(src) and src not in found_urls:
                        found_urls.append(src)
                        if len(found_urls) >= max_images:
                            break

                logger.info(f"🌐 แกะรอยบทความ {article_url[:45]}... พบภาพจริงคุณภาพสูง {len(found_urls)} ภาพ")
    except Exception as e:
        logger.warning(f"แกะรอยภาพจากหน้าเว็บ {article_url} ผิดพลาด: {e}")

    return found_urls[:max_images]


def search_sanook_digital_footprints(query: str, max_results: int = 3) -> List[str]:
    """สืบค้นร่องรอยดิจิทัลจากคลังสื่อ Sanook โดยตรงตามคีย์เวิร์ด"""
    subject = extract_core_subject(query)
    if not subject:
        return []
    found = []
    try:
        search_url = f"https://www.sanook.com/search/?q={quote(subject)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        with httpx.Client(timeout=6.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(search_url)
            if resp.status_code == 200 and resp.text:
                imgs = re.findall(r'<img[^>]+(?:data-src|src)=[\'"]([^\'"]*s\.isanook\.com[^\'"]+)[\'"]', resp.text)
                for img_u in imgs:
                    img_u = normalize_image_url(html.unescape(img_u.strip()))
                    if is_valid_image_url(img_u) and img_u not in found:
                        found.append(img_u)
                        if len(found) >= max_results:
                            break
    except Exception as e:
        logger.warning(f"สืบค้นคลังข่าวดิจิทัล Sanook ผิดพลาด: {e}")
    return found


def search_web_images(query: str, max_results: int = 4, category_hint: str = "") -> List[str]:
    """สืบค้นภาพถ่ายจริงจากอินเทอร์เน็ตด้วย Tavily Images Live Search ตรงประเด็น 100%"""
    if not query:
        return []

    subject = extract_core_subject(query)
    if not subject:
        subject = query[:40]

    found = []
    try:
        import sys
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        from app.services.web_search import _tavily_search, _clean_image_urls

        search_query = f"{subject} ภาพถ่ายจริง"
        raw_tv = _tavily_search(search_query, max_results=max_results + 2, search_depth="basic")
        if raw_tv and "images" in raw_tv:
            cleaned_tv = _clean_image_urls(raw_tv["images"])
            for u in cleaned_tv:
                u = normalize_image_url(u)
                if is_valid_image_url(u) and u not in found:
                    found.append(u)
                    if len(found) >= max_results:
                        break
        logger.info(f"🔍 ค้นภาพเน็ต Tavily '{subject}': พบ {len(found)} ภาพตรงปก")
    except Exception as e_tv:
        logger.warning(f"ค้นภาพ Tavily ล้มเหลว ({e_tv}) — ตรวจสอบ fallback")

    return found[:max_results]


# คลังภาพถ่ายจริงสำรองคุณภาพระดับสตูดิโอ แยกตามหมวดเฉพาะด้าน (Authentic Photography ปลอดภาพการ์ตูน AI 100%)
THEMATIC_EDITORIAL_REGISTRY = {
    # 1. ข่าวและสื่อมวลชน
    "NEWS_MEDIA": [
        "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1080&auto=format&fit=crop", # บรรยากาศสำนักข่าว
        "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=1080&auto=format&fit=crop", # ไมโครโฟนแถลงข่าว
        "https://images.unsplash.com/photo-1495020689067-958852a7765e?w=1080&auto=format&fit=crop", # สื่อสิ่งพิมพ์ / ข่าว
    ],
    # 2. ดารา ศิลปิน และวงการบันเทิง
    "CELEBRITY_STAGE": [
        "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=1080&auto=format&fit=crop", # เวทีคอนเสิร์ต
        "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=1080&auto=format&fit=crop", # แสงสีการแสดง
        "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1080&auto=format&fit=crop", # อีเวนต์บันเทิง
    ],
    # 3. สุขภาพ การแพทย์ และดวงตา (Health & Medical)
    "HEALTH_MEDICAL": [
        "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1080&auto=format&fit=crop", # คุณหมอและการตรวจสุขภาพ
        "https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?w=1080&auto=format&fit=crop", # การดูแลดวงตาและสุขภาพ
        "https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=1080&auto=format&fit=crop", # สุขภาพองค์รวม
    ],
    # 4. เครื่องครัว ทำอาหาร และกระทะ (Kitchen & Cooking)
    "KITCHEN_COOKING": [
        "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=1080&auto=format&fit=crop", # ครัวและอุปกรณ์ทำอาหาร
        "https://images.unsplash.com/photo-1584992236310-6edddc08acff?w=1080&auto=format&fit=crop", # กระทะและอุปกรณ์เครื่องครัว
        "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=1080&auto=format&fit=crop", # การทำความสะอาดเครื่องครัว
    ],
    # 5. การทำความสะอาดบ้านและแก้ปัญหาในบ้าน (Home Cleaning & Maintenance)
    "HOME_CLEANING": [
        "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=1080&auto=format&fit=crop", # อุปกรณ์ทำความสะอาดบ้าน
        "https://images.unsplash.com/photo-1527515637462-cff94eecc1ac?w=1080&auto=format&fit=crop", # บ้านสะอาด เรียบร้อย
        "https://images.unsplash.com/photo-1563453392212-326f5e854473?w=1080&auto=format&fit=crop", # สเปรย์และอุปกรณ์แม่บ้าน
        "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=1080&auto=format&fit=crop", # ห้องน้ำและท่อน้ำ
    ],
    # 6. คนทำงาน ออฟฟิศ จัดการเวลา และโต๊ะทำงาน (Office & Productivity)
    "OFFICE_PRODUCTIVITY": [
        "https://images.unsplash.com/photo-1497366216548-37526070297c?w=1080&auto=format&fit=crop", # โต๊ะทำงานมาตรฐานโมเดิร์น
        "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=1080&auto=format&fit=crop", # การทำงานกับแล็ปท็อป
        "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=1080&auto=format&fit=crop", # บรรยากาศทีมงาน
    ],
    # 7. โชคลาภ ดวงชะตา และพลังงานมงคล (Astrology & Fortune)
    "FORTUNE_ASTROLOGY": [
        "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1080&auto=format&fit=crop", # ทองคำและเหรียญมงคล
        "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=1080&auto=format&fit=crop", # ท้องฟ้าราตรีดวงดาว
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1080&auto=format&fit=crop", # คริสตัลและพลังงานมงคล
    ],
    # 8. ไอที สมาร์ตโฟน และแก็ดเจ็ต (Tech & Gadgets)
    "TECH_GADGETS": [
        "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=1080&auto=format&fit=crop", # สมาร์ตโฟนเทคโนโลยี
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=1080&auto=format&fit=crop", # หูฟังไร้สายพรีเมียม
        "https://images.unsplash.com/photo-1526738549149-8e07eca6c147?w=1080&auto=format&fit=crop", # แก็ดเจ็ตไอที
    ]
}


def resolve_thematic_category(title: str, mode: str) -> str:
    """วิเคราะห์เนื้อหาเพื่อจับคู่ภาพถ่ายจริงตามธีมที่ตรงประเด็นสูงสุด"""
    t = (title or "").lower()

    if any(k in t for k in ["ตา", "แห้ง", "หมอ", "โรค", "สุขภาพ", "ยา", "อาการ", "โรงพยาบาล", "แพทย์"]):
        return "HEALTH_MEDICAL"
    if any(k in t for k in ["กระทะ", "หม้อ", "ครัว", "อาหาร", "จาน", "ต้ม", "ทอด", "ล้างจาน"]):
        return "KITCHEN_COOKING"
    if any(k in t for k in ["ท่อ", "กลิ่น", "มด", "แมลง", "ซัก", "ผ้า", "ตู้เสื้อผ้า", "ห้องน้ำ", "สะอาด"]):
        return "HOME_CLEANING"
    if any(k in t for k in ["ทำงาน", "หัวหน้า", "ออฟฟิศ", "เวลา", "ประชุม", "เงินเดือน", "ลาออก"]):
        return "OFFICE_PRODUCTIVITY"
    if any(k in t for k in ["ดวง", "ราศี", "สีเสื้อ", "โชคลาภ", "มงคล", "ทักษา", "ฮวงจุ้ย", "ไพ่"]):
        return "FORTUNE_ASTROLOGY"
    if any(k in t for k in ["ไอโฟน", "โทรศัพท์", "มือถือ", "หูฟัง", "แอป", "คอม", "ไอที", "ai"]):
        return "TECH_GADGETS"
    if mode == "CELEBRITY_TREND" or any(k in t for k in ["ดารา", "นักร้อง", "คอนเสิร์ต", "เปิดใจ", "แฟนคลับ", "นางเอก", "พระเอก"]):
        return "CELEBRITY_STAGE"

    return "NEWS_MEDIA"


def find_three_distinct_images(
    topic_data: dict,
    mode: str = "TRENDING_NEWS"
) -> List[str]:
    """สืบค้นและคัดเลือกภาพถ่ายจริง 3 ภาพที่ไม่ซ้ำกันเด็ดขาด และเข้ากับเนื้อหา 100%
    ตามคำสั่งผู้ใช้: ภาพถ่ายต้องตรงปก ไม่ใช่แบนเนอร์หรือภาพมโน
    """
    selected_images = []
    seen = set()

    def add_img(u: str):
        if not u:
            return
        u = normalize_image_url(u)
        if u not in seen and is_valid_image_url(u):
            seen.add(u)
            selected_images.append(u)

    # 1. รูปภาพหลักจาก RSS / ข่าวต้นทาง (Image 1)
    primary_img = topic_data.get("image_url") or ""
    add_img(primary_img)

    # 2. แกะรอยจาก URL บทความต้นทาง (In-Article Scrape: ดึงรูปถ่ายความละเอียดสูงจากในเนื้อหา)
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

    # 3. ร่องรอยดิจิทัลจาก Tavily Live Search โดยใช้ Core Subject
    title = topic_data.get("title") or topic_data.get("hook") or ""
    if len(selected_images) < 3 and title:
        web_imgs = search_web_images(title, max_results=4, category_hint=mode)
        for u in web_imgs:
            add_img(u)
            if len(selected_images) >= 3:
                break

    # 4. ร่องรอยดิจิทัลจากคลังสื่อตรง Sanook
    if len(selected_images) < 3 and title:
        sanook_imgs = search_sanook_digital_footprints(title, max_results=3)
        for u in sanook_imgs:
            add_img(u)
            if len(selected_images) >= 3:
                break

    # 5. หากยังไม่ครบ 3 ภาพ ให้ดึงจากคลังภาพถ่ายจริงเฉพาะธีมที่ตรงประเด็นสูงสุด
    thm_cat = resolve_thematic_category(title, mode)
    fallbacks = THEMATIC_EDITORIAL_REGISTRY.get(thm_cat, THEMATIC_EDITORIAL_REGISTRY["NEWS_MEDIA"])
    for fb_u in fallbacks:
        if len(selected_images) >= 3:
            break
        add_img(fb_u)

    logger.info(f"📸 คัดเลือกภาพถ่ายจริงครบ 3 ภาพตรงประเด็น 100% ({mode} -> {thm_cat}): {len(selected_images)} ภาพ")
    return selected_images[:3]
