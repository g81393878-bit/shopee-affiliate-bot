"""ค้นร้านอาหาร/ร้านกินดื่มใกล้ตำแหน่งด้วย Google Places API (Nearby Search).

ใช้ endpoint ทางการ (ไม่ scrape) — ฟรีเครดิต $200/เดือนจาก Google Cloud
(เปิด Places API + billing → ได้ key GOOGLE_PLACES_API_KEY ขึ้นต้น AIza...)

ออกแบบตาม pattern เดียวกับ web_search.py:
- key อ่านจาก env (ถ้าไม่ตั้ง → คืน None ให้ line_bot ตอบขอโทษ ไม่พัง)
- คืนผลลัพธ์จัดรูปแล้ว (dict) ให้ line_bot เอาไป format ตามโทนวัยได้
"""
import os
import logging

import requests

logger = logging.getLogger(__name__)

# รองรับหลาย key คั่นด้วยคอมม่า (แบบเดียวกับ Groq/Tavily/Firecrawl) — หมุนเวียน + failover
_GOOGLE_KEYS = [k.strip() for k in (os.getenv("GOOGLE_PLACES_API_KEY") or "").split(",") if k.strip()]
_key_index = 0


def _keys():
    """คืน list key ที่ตั้งไว้ (ตัดค่าว่าง/ค่าตัวอย่างออก) — ใช้แทนอ่าน env ซ้ำทุกครั้ง"""
    return _GOOGLE_KEYS


def _rotate_start_index(n: int) -> int:
    """เริ่มยิง key ถัดไปในแต่ละครั้ง (round-robin) — กระจายโหลดหลาย key เท่าๆ กัน"""
    global _key_index
    start = _key_index
    _key_index = (_key_index + 1) % max(1, n)
    return start


def nearby_restaurants(lat: float, lng: float, keyword: str = None,
                       radius: int = 3000, limit: int = 5):
    """ค้นร้านอาหารใกล้ตำแหน่ง (lat, lng) ด้วย Places Nearby Search.

    keyword: ประเภทอาหารที่อยากได้ (เช่น "ส้มตำ", "กาแฟ") — None/ว่าง = ร้านอาหารทั่วไป
    radius: ระยะค้นเป็นเมตร (default 3 กม.)
    คืน list[dict] (name/rating/vicinity/price_level/open_now/lat/lng) หรือ None ถ้า
    ไม่มี key/ล้มทุกตัว — line_bot จะตอบขอโทษแทน ไม่ crash
    """
    keys = _keys()
    if not keys:
        logger.warning("GOOGLE_PLACES_API_KEY ยังไม่ตั้ง — ข้ามค้นร้านอาหาร")
        return None

    params_base = {
        "location": f"{lat},{lng}",
        "radius": str(radius),
        "type": "restaurant",
    }
    if keyword:
        params_base["keyword"] = keyword

    start = _rotate_start_index(len(keys))
    last_err = None
    for i in range(len(keys)):
        key = keys[(start + i) % len(keys)]
        params = dict(params_base)
        params["key"] = key
        try:
            r = requests.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params=params,
                timeout=8,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status")
            if status not in ("OK", "ZERO_RESULTS"):
                # REQUEST_DENIED (key ผิด/ไม่ได้เปิด Places API) / OVER_QUERY_LIMIT /
                # INVALID_REQUEST — key นี้ใช้ไม่ได้ → ลอง key ถัดไป
                logger.warning(f"Google Places key[{i}] status={status} msg={data.get('error_message')}")
                last_err = RuntimeError(f"places status={status}")
                continue
            results = []
            for p in data.get("results", [])[:limit]:
                geo = (p.get("geometry") or {}).get("location") or {}
                results.append({
                    "name": p.get("name"),
                    "rating": p.get("rating"),
                    "vicinity": p.get("vicinity"),
                    "price_level": p.get("price_level"),
                    "open_now": (p.get("opening_hours") or {}).get("open_now"),
                    "lat": geo.get("lat"),
                    "lng": geo.get("lng"),
                })
            return results
        except Exception as e:  # network/JSON error → key ถัดไป
            logger.warning(f"Google Places key[{i}] error: {e}")
            last_err = e
    logger.warning(f"Google Places ล้มทุก key: {last_err}")
    return None
