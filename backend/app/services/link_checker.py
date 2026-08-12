# -*- coding: utf-8 -*-
"""
Link Checker — ตรวจลิงก์ affiliate (s.shopee.co.th) ว่ายังใช้ได้หรือยัง
====================================================================
นโยบาย (เด็ดขาด): สินค้าที่เข้าระบบต้องมีลิงก์ affiliate ที่ตรวจผ่านแล้วเท่านั้น
- API สร้าง/แก้สินค้า: ตรวจลิงก์ก่อนบันทึก ถ้าไม่ผ่าน → reject (400)
- import-csv: ตรวจลิงก์ก่อน insert ถ้าไม่ผ่าน → ข้าม
- บอท LINE: ตอบเฉพาะสินค้า link_status == 'ok'
- check-links: อัปเดตสถานะลงตาราง products

สถานะ: OK / DEAD / SUSPECT / UNKNOWN
"""
import re
from typing import Tuple
from urllib.parse import urlparse

import requests

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
DEAD_MARKERS = ("item_not_found", "item not found", "ไม่พบสินค้า", "สินค้าหาย",
                "product is no longer", "product_not_found", "ไม่มีสินค้านี้")
BLOCK_MARKERS = ("เข้าสู่หน้าที่ต้องการไม่สำเร็จ", "traffic verification", "captcha",
                 "แคปต์ชา", "page unavailable", "verify you are human")
ITEM_URL_RE = re.compile(r"/product/|/opaanlp/|-[a-z0-9-]+-i\.\d+\.\d+", re.IGNORECASE)


def check_affiliate_link(url: str) -> Tuple[str, str]:
    """ตรวจลิงก์สั้น s.shopee.co.th → (status, detail)
    OK / DEAD / SUSPECT (ต้องเช็คมือ) / UNKNOWN (ยิงไม่สำเร็จ) / NO_URL
    """
    if not url or not url.strip():
        return "NO_URL", "ไม่มีลิงก์"
    url = url.strip()
    if not url.startswith(("https://s.shopee.co.th/", "http://s.shopee.co.th/")):
        return "NO_URL", "ไม่ใช่ลิงก์สั้น s.shopee.co.th"
    try:
        r = requests.get(url, timeout=20, allow_redirects=True,
                         headers={"User-Agent": BROWSER_UA, "Accept-Language": "th-TH,th;q=0.9"},
                         stream=True)
        with r:
            status = r.status_code
            final = r.url or ""
            if status != 200:
                if status in (400, 404, 410):
                    # 400 = short code ไม่ valid/หมดอายุ, 404/410 = ของหาย
                    return "DEAD", f"HTTP {status}"
                if status in (401, 403):
                    return "SUSPECT", f"HTTP {status} (ถูกบล็อก)"
                if 500 <= status < 600:
                    return "UNKNOWN", f"HTTP {status}"
                return "SUSPECT", f"HTTP {status}"
            body = (r.content[:80000] or b"").decode("utf-8", errors="ignore").lower()
            if any(m in body for m in DEAD_MARKERS):
                return "DEAD", "เจอหน้า 'ไม่พบสินค้า'"
            if any(m in body for m in BLOCK_MARKERS):
                return "SUSPECT", "โดนหน้า verify/anti-bot"
            if "shopee.co.th" in final and ITEM_URL_RE.search(urlparse(final).path):
                return "OK", final[:95]
            return "SUSPECT", f"redirect ไป {final[:75]} (ไม่ยืนยันว่ามีของ)"
    except requests.exceptions.Timeout:
        return "UNKNOWN", "timeout 20s"
    except requests.exceptions.RequestException as e:
        return "UNKNOWN", type(e).__name__
