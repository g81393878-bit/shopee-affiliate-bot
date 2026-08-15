# -*- coding: utf-8 -*-
"""ดึงรูปสินค้า (og:image) จากหน้า Shopee — ใช้โพสต์ Facebook แบบแนบรูป.

เหตุผล: โพสต์สินค้าแบบการ์ดลิงก์ (link param) ให้ Facebook crawl ลิงก์ s.shopee.co.th
เอาเอง — บางรอบ Shopee กันบอท/redirect ทำให้ได้ title แต่รูป og:image ว่าง (ช่องรูปดำ)
เลยเปลี่ยนเป็นแนบรูปจริง: ดึง og:image เอง (requests ก่อน → Firecrawl สำรอง)
แล้วโพสต์ผ่าน /photos พร้อมลิงก์ในแคปชั่น

best-effort: หาไม่เจอ/โดนบล็อก → คืน "" (ผู้เรียก fallback ไปโพสต์การ์ดลิงก์เดิม)
"""
import logging
import os
import re
import time

import requests

from app.services.web_search import firecrawl_scrape

logger = logging.getLogger(__name__)

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

# <meta> og:image — รองรับทั้ง property/name และ content อยู่ก่อน/หลัง
_OG_IMAGE_RES = [
    re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']og:image["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']og:image["\']', re.I),
]


def extract_og_image(html: str) -> str:
    """อ่าน URL รูปจาก <meta og:image> — คืน "" ถ้าไม่มี (ต้องเป็น http(s))."""
    if not html:
        return ""
    for rx in _OG_IMAGE_RES:
        m = rx.search(html)
        if m:
            url = m.group(1).strip()
            if url.startswith(("http://", "https://")):
                return url
    return ""


def _facebook_og_image(url: str, timeout: int = 20, attempts: int = 3,
                      retry_delay: float = 1.0) -> str:
    """ให้ Facebook crawl ลิงก์เอง (scrape=true) แล้วอ่าน og:image กลับ.

    เหตุผล: Shopee เป็น SPA + กันบอท — requests/firecrawl ไม่เห็น <meta og:image>
    แต่ crawler ของ Facebook (ที่มี infra ถูกต้อง) ดึงได้ → ใช้ลิงก์ที่ Facebook scrape
    มาเป็นรูปโพสต์ (ยืนยันแล้วกับลิงก์จริง: คืน down-th.img.susercontent.com/...)

    Facebook scrape ตอบ image ว่างเป็นบางรอบ (crawl ยังไม่ทัน/ติด ๆ ขัด ๆ) →
    retry อีก 2-3 รอบกัน transient หลุดจนโพสต์ตกไป fallback การ์ดลิงก์
    """
    token = (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or "").strip()
    if not token:
        return ""
    for attempt in range(1, attempts + 1):
        try:
            r = requests.post("https://graph.facebook.com/v21.0/",
                              params={"id": url, "scrape": "true", "access_token": token},
                              timeout=timeout)
            data = r.json()
            images = data.get("image") or []
            for it in images:
                u = (it.get("url") if isinstance(it, dict) else it) or ""
                if u.startswith(("http://", "https://")):
                    return u
        except Exception as e:
            logger.warning(f"[product_image] facebook og scrape ล้ม "
                           f"(attempt {attempt}/{attempts}) {url[:45]}: {e}")
        if attempt < attempts:
            time.sleep(retry_delay)
    return ""


def fetch_product_image(url: str, timeout: int = 25) -> str:
    """หาลิงก์รูปสินค้า (og:image) → คืน URL หรือ "" (best-effort ไม่ throw).

    ลำดับ: requests (ฟรี/เร็ว) → Facebook og scrape (เชื่อถือได้สำหรับ Shopee) →
    Firecrawl (สำรองสุดท้าย) — เจอตัวไหนคืนตัวนั้น
    """
    if not url:
        return ""
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, stream=True,
                         headers={"User-Agent": BROWSER_UA, "Accept-Language": "th-TH,th;q=0.9"})
        with r:
            if r.status_code == 200:
                img = extract_og_image((r.content[:300000] or b"").decode("utf-8", errors="ignore"))
                if img:
                    return img
    except requests.exceptions.RequestException as e:
        logger.debug(f"[product_image] requests ล้ม {url[:45]}: {e}")
    img = _facebook_og_image(url)
    if img:
        return img
    try:
        img = extract_og_image(firecrawl_scrape(url))
        if img:
            return img
    except Exception as e:
        logger.warning(f"[product_image] firecrawl ล้ม {url[:45]}: {e}")
    return ""
