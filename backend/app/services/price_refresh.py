# -*- coding: utf-8 -*-
"""
Price Refresh — อัปเดตราคาปัจจุบันจากหน้า Shopee จริง
====================================================
ปัญหาที่แก้: ราคาในตารางมาจาก CSV ตอน export — ราคา Shopee เปลี่ยนบ่อย
(โปร/แฟลชเซลล์) การ์ดที่โชว์อาจไม่ตรงกับหน้าร้านจริง

วิธีแก้:
- cron refresh-prices เปิดหน้าเว็บสินค้าทุกตัว (ผ่านลิงก์สั้น affiliate
  เหมือน link_checker) แล้วอ่านราคาปัจจุบันจาก HTML → อัปเดต products.price
- ทำงานแบบ best-effort: ถ้า Shopee บล็อก/หน้าไม่สมบูรณ์ → คงราคาเดิมไว้
  ไม่พัง ไม่หลอก (การ์ดลูกค้าแสดง "ราคาเริ่มต้น" อยู่แล้ว)
- พอได้ Shopee Affiliate Open API จริง (productOfferV2 มี priceMin/priceMax)
  จะแทนที่ตัวนี้ด้วยข้อมูลทางการ เป๊ะทุกวัน
"""
import logging
import re
from typing import Optional, Tuple

import requests

from app import models
from app.services.web_search import firecrawl_scrape

logger = logging.getLogger(__name__)

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
BLOCK_MARKERS = ("เข้าสู่หน้าที่ต้องการไม่สำเร็จ", "traffic verification", "captcha",
                 "แคปต์ชา", "verify you are human", "forbidden")

# ราคาใน JSON หน้าเว็บ Shopee เป็น "centavos" (หาร 100,000 ได้บาท)
# คีย์ที่เจอบ่อย: "price", "price_min", "priceMax", "priceMin", "raw_price"
_PRICE_RE = re.compile(r'"(?:price|price_min|priceMax|priceMin|raw_price|price_before_discount)"\s*:\s*(\d{4,})')


def extract_price_from_html(html: str) -> Optional[float]:
    """อ่านราคาบาทจาก HTML หน้า product — คืน None ถ้าหาไม่เจอ/ค่าผิดปกติ"""
    if not html:
        return None
    found = [int(m) for m in _PRICE_RE.findall(html)]
    if not found:
        return None
    # เอาราคาต่ำสุด (ราคาเริ่มต้น/โปร) — centavos ควรอยู่ช่วง ฿1 - ฿1,000,000
    cand = min(found)
    if 100_000 <= cand <= 100_000_000_000:  # ฿1 - ฿1,000,000
        return round(cand / 100_000, 2)
    return None


def _fetch_via_requests(url: str) -> Tuple[Optional[float], str]:
    """requests ธรรมดา (ฟรี ไม่กิน Firecrawl credit) → (ราคา, detail)
    detail: ok / anti-bot / no price found / HTTP ... / ชื่อ exception"""
    try:
        r = requests.get(url, timeout=25, allow_redirects=True,
                         headers={"User-Agent": BROWSER_UA, "Accept-Language": "th-TH,th;q=0.9"},
                         stream=True)
        with r:
            body = (r.content[:300000] or b"").decode("utf-8", errors="ignore")
            if r.status_code != 200:
                return None, f"HTTP {r.status_code}"
            low = body.lower()
            if any(m in low for m in BLOCK_MARKERS):
                return None, "anti-bot"
            price = extract_price_from_html(body)
            if price is None:
                return None, "no price found"
            return price, "ok"
    except requests.exceptions.RequestException as e:
        return None, type(e).__name__


def fetch_product_price(url: str) -> Tuple[Optional[float], str]:
    """เปิดหน้าเว็บ (ตาม redirect ลิงก์สั้น) → (ราคาบาท, detail)

    requests ก่อน (ฟรี) → ได้ราคา ไม่ต้องจ่าย Firecrawl credit
    เฉพาะหน้าโดน anti-bot / ราคาโหลดด้วย JS (requests หาไม่เจอ) → Firecrawl scrape
    (render JS ผ่านด่าน) เป็นสำรอง — best-effort ไม่พัง
    detail: "ok" = ได้ราคา (cron นับ unchanged ด้วยค่านี้) — source อื่น = ข้าม"""
    if not url:
        return None, "NO_URL"
    price, detail = _fetch_via_requests(url)
    if price is not None:
        return price, detail
    # requests ได้หน้าแต่ไม่มีราคา (โดน anti-bot / ราคาเป็น JS) → ลอง Firecrawl
    if detail in ("anti-bot", "no price found"):
        try:
            html = firecrawl_scrape(url)
            if html:
                p = extract_price_from_html(html)
                if p is not None:
                    logger.info(f"[firecrawl] ราคา {p:,.2f} จาก {url[:45]} (requests: {detail})")
                    return p, "ok"
                return None, "no price found"
            logger.warning(f"[firecrawl] ไม่ได้หน้า ({url[:45]})")
        except Exception as e:
            logger.warning(f"firecrawl scrape ล้ม ({e})")
    return None, detail


def refresh_price(prod: models.Product) -> Tuple[bool, float, float, str]:
    """อัปเดตราคาของสินค้า 1 ตัว → (updated, old, new, detail)
    old/new เป็นราคาบาทจริง (ใช้บันทึก price_history + คำนวณ % ลด)"""
    price, detail = fetch_product_price(prod.affiliate_url)
    old = float(prod.price or 0)
    if price is None:
        return False, old, old, detail
    prod.price = price
    return (old != price), old, price, f"{old:,.2f} -> {price:,.2f}"
