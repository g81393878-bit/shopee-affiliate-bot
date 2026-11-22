# -*- coding: utf-8 -*-
"""backend/app/services/shopee_image_service.py
โมดูลค้นหาและดึงรูปภาพแท้ Shopee Official CDN (down-th.img.susercontent.com)
รองรับการเรียกใช้งานจาก API, LINE Bot, และ Admin Dashboard
"""

import re
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def verify_image_url(url: str, timeout: int = 3) -> bool:
    """ตรวจสอบว่า URL รูปภาพเข้าถึงได้จริง (HTTP 200 OK)"""
    if not url or not url.startswith("http"):
        return False
    try:
        r = requests.head(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            return True
        r_get = requests.get(url, timeout=timeout, stream=True, headers={"User-Agent": USER_AGENT})
        return r_get.status_code == 200
    except Exception:
        return False


def fetch_shopee_cdn_image(product_name: str) -> Optional[str]:
    """ค้นหาและสกัดรูปภาพ Shopee Official CDN สำหรับชื่อสินค้าที่ระบุ"""
    if not product_name or not product_name.strip():
        return None

    search_query = f"{product_name.strip()} shopee"
    url = f"https://www.bing.com/images/search?q={requests.utils.quote(search_query)}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return None

        # หา murl (Media URL) ทั้งหมดในผลลัพธ์
        murls = re.findall(r'&quot;murl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)

        # 1. ให้ความสำคัญกับ Shopee CDN สูงสุด
        for u in murls:
            if "susercontent.com" in u and verify_image_url(u):
                return u

        # 2. แบรนด์หรือร้านค้าปลีก E-commerce อื่นๆ
        for u in murls:
            if any(domain in u for domain in ["lazada", "bigc", "central", "lotuss"]) and verify_image_url(u):
                return u

        # 3. ไฟล์ภาพโดยตรง
        for u in murls:
            if u.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and verify_image_url(u):
                return u

    except Exception as e:
        logger.warning(f"Error fetching image for '{product_name}': {e}")

    return None
