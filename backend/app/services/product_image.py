# -*- coding: utf-8 -*-
"""ดึงรูปสินค้า (og:image) จากหน้า Shopee — ใช้โพสต์ Facebook แบบแนบรูป.

เหตุผล: โพสต์สินค้าแบบการ์ดลิงก์ (link param) ให้ Facebook crawl ลิงก์ s.shopee.co.th
เอาเอง — บางรอบ Shopee กันบอท/redirect ทำให้ได้ title แต่รูป og:image ว่าง (ช่องรูปดำ)
เลยเปลี่ยนเป็นแนบรูปจริง: ดึงรูปเองหลายชั้น แล้วโพสต์ผ่าน /photos พร้อมลิงก์ในแคปชั่น

ลำดับหา: หน้าเว็บตรง (og:image) → หน้า product ปกติที่ derive จาก redirect ของลิงก์
affiliate (s.shopee.co.th → หน้า SPA `opaanlp/{shop}/{item}` ไม่มีรูป แต่
`/product/{shop}/{item}` มี og:image) → JSON-LD → Facebook og scrape → Firecrawl

best-effort: หาไม่เจอ/โดนบล็อก → คืน "" (ผู้เรียก fallback ไปโพสต์การ์ดลิงก์เดิม)
"""
import json
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


def _fetch_html(url: str, timeout: int) -> tuple:
    """GET หน้าเว็บ (follow redirect) → (html, final_url) — คืน ("", "") ถ้าไม่ 200/ล้ม."""
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, stream=True,
                         headers={"User-Agent": BROWSER_UA, "Accept-Language": "th-TH,th;q=0.9"})
        with r:
            if r.status_code != 200:
                return "", ""
            html = (r.content[:300000] or b"").decode("utf-8", errors="ignore")
            return html, (getattr(r, "url", "") or "")
    except requests.exceptions.RequestException as e:
        logger.debug(f"[product_image] requests ล้ม {url[:45]}: {e}")
        return "", ""


def derive_product_page_url(final_url: str) -> str:
    """แปลง redirect target ของลิงก์ affiliate Shopee เป็น URL หน้า product ปกติ.

    s.shopee.co.th → redirect ไปหน้า SPA `opaanlp/{shopid}/{itemid}` (ไม่มี og:image)
    แต่หน้า `/product/{shopid}/{itemid}` มี og:image (เทสต์จริงแล้ว) → ใช้ URL นี้แทน
    คืน "" ถ้ารูปแบบไม่เข้า (ไม่ใช่หน้า Shopee product)
    """
    if not final_url:
        return ""
    m = re.search(r'/(?:opaanlp|product|item)/(\d+)/(\d+)', final_url)
    if not m:
        return ""
    base = re.match(r'(https?://[^/]+)', final_url)
    host = base.group(1) if base else "https://shopee.co.th"
    return f"{host}/product/{m.group(1)}/{m.group(2)}"


def extract_ld_json_images(html: str) -> str:
    """อ่าน URL รูปจาก <script type="application/ld+json"> — คืน "" ถ้าไม่มี.

    รองรับ image = string | array | {"@type":"ImageObject","contentUrl":...}
    (ค้นเฉพาะ key image/contentUrl/thumbnailUrl แบบ recursive — ไม่ร่อนทั้ง JSON
    กันไปติดรูป noise อย่างโลโก้/avatar ของเว็บอื่น)
    """
    if not html:
        return ""
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
                            html, re.I | re.S):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        img = _ld_json_image(data)
        if img:
            return img
    return ""


def _ld_json_image(node) -> str:
    """หา URL รูปแรกในโครงสร้าง JSON-LD (string | list | dict) — คืน "" ถ้าไม่มี."""
    if isinstance(node, str):
        return node if node.startswith(("http://", "https://")) else ""
    if isinstance(node, list):
        for item in node:
            img = _ld_json_image(item)
            if img:
                return img
        return ""
    if isinstance(node, dict):
        for key in ("image", "contentUrl", "thumbnailUrl"):
            if key in node:
                img = _ld_json_image(node[key])
                if img:
                    return img
        return ""
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
    """หาลิงก์รูปสินค้า → คืน URL หรือ "" (best-effort ไม่ throw).

    ลำดับ: หน้าเว็บตรง (og:image) → derive หน้า product ปกติจาก redirect ของลิงก์
    affiliate (opaanlp→product; มี og:image/JSON-LD) → Facebook og scrape → Firecrawl
    — เจอตัวไหนคืนตัวนั้น
    """
    if not url:
        return ""
    html, final_url = _fetch_html(url, timeout)
    if html:
        img = extract_og_image(html)
        if img:
            return img
        # ลิงก์ affiliate redirect ไปหน้า SPA (opaanlp) ไม่มีรูป → ลองหน้า product ปกติ
        product_url = derive_product_page_url(final_url or url)
        if product_url and product_url != url:
            html2, _ = _fetch_html(product_url, timeout)
            if html2:
                img = extract_og_image(html2) or extract_ld_json_images(html2)
                if img:
                    return img
    img = _facebook_og_image(url)
    if img:
        return img
    try:
        fhtml = firecrawl_scrape(url)
        img = extract_og_image(fhtml) or extract_ld_json_images(fhtml)
        if img:
            return img
    except Exception as e:
        logger.warning(f"[product_image] firecrawl ล้ม {url[:45]}: {e}")
    return ""
