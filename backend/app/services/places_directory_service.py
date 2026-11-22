"""backend/app/services/places_directory_service.py
ระบบค้นหาสิ่งอำนวยความสะดวกทั่วไทยฟรี 24 ชม. (ร้านอาหาร, สถานที่ท่องเที่ยว, โรงแรม/ที่พัก)
- แยกหมวดหมู่อัตโนมัติ (restaurant / attraction / hotel)
- สกัดจังหวัดและย่านยอดนิยมทั่วไทย (77 จังหวัด + ย่านท่องเที่ยว)
- ดึงพิกัดสถานที่จริงผ่าน OpenStreetMap Nominatim (ฟรี ไม่ใช้ API Key, มีแคชในหน่วยความจำ, timeout 4 วิ)
- พร้อมลิงก์ Google Maps Search เสมอ เพื่อให้กดดูรีวิว รูปภาพ เบอร์โทร และนำทางได้ทันที
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple

import httpx

from app.services.hospital_directory_service import extract_location_criteria

logger = logging.getLogger(__name__)

# ย่าน/แหล่งท่องเที่ยวยอดนิยมเพิ่มเติมจาก POPULAR_AREAS ของ hospital_directory_service
EXTRA_TOURIST_AREAS: Dict[str, Tuple[str, str]] = {
    "เขาใหญ่": ("นครราชสีมา", "เขาใหญ่"),
    "ปากช่อง": ("นครราชสีมา", "ปากช่อง"),
    "เขาค้อ": ("เพชรบูรณ์", "เขาค้อ"),
    "ภูทับเบิก": ("เพชรบูรณ์", "ภูทับเบิก"),
    "ปาย": ("แม่ฮ่องสอน", "ปาย"),
    "เชียงคาน": ("เลย", "เชียงคาน"),
    "อัมพวา": ("สมุทรสงคราม", "อัมพวา"),
    "ชะอำ": ("เพชรบุรี", "ชะอำ"),
    "เกาะล้าน": ("ชลบุรี", "เกาะล้าน"),
    "เกาะช้าง": ("ตราด", "เกาะช้าง"),
    "เกาะเสม็ด": ("ระยอง", "เกาะเสม็ด"),
    "เกาะพีพี": ("กระบี่", "เกาะพีพี"),
    "อ่าวนาง": ("กระบี่", "อ่าวนาง"),
    "สังขละบุรี": ("กาญจนบุรี", "สังขละบุรี"),
    "ม่อนแจ่ม": ("เชียงใหม่", "ม่อนแจ่ม"),
    "นิมมาน": ("เชียงใหม่", "นิมมาน"),
    "ดอยอินทนนท์": ("เชียงใหม่", "ดอยอินทนนท์"),
    "เยาวราช": ("กรุงเทพมหานคร", "เยาวราช"),
    "สยาม": ("กรุงเทพมหานคร", "สยาม"),
    "สีลม": ("กรุงเทพมหานคร", "สีลม"),
    "สุขุมวิท": ("กรุงเทพมหานคร", "สุขุมวิท"),
    "อารีย์": ("กรุงเทพมหานคร", "อารีย์"),
    "บางปู": ("สมุทรปราการ", "บางปู"),
}

RESTAURANT_TRIGGERS = (
    "ร้านอาหาร", "ของกิน", "ของอร่อย", "ร้านอร่อย", "ร้านเด็ด", "กินอะไรดี",
    "กินข้าว", "คาเฟ่", "ร้านกาแฟ", "ก๋วยเตี๋ยว", "อาหารทะเล", "ซีฟู้ด",
    "บุฟเฟ่ต์", "บุฟเฟต์", "หมูกระทะ", "ส้มตำ", "ชาบู", "ปิ้งย่าง",
    "ตลาดกลางคืน", "ตลาดโต้รุ่ง", "สตรีทฟู้ด", "อาหารพื้นเมือง", "restaurant", "cafe",
)

ATTRACTION_TRIGGERS = (
    "สถานที่ท่องเที่ยว", "แหล่งท่องเที่ยว", "ที่เที่ยว", "ท่องเที่ยว", "เที่ยวไหนดี",
    "จุดเช็คอิน", "จุดเช็กอิน", "แลนด์มาร์ค", "แลนด์มาร์ก", "น้ำตก", "ชายหาด",
    "อุทยาน", "จุดชมวิว", "ตลาดน้ำ", "ไหว้พระ", "วัดดัง", "พิพิธภัณฑ์",
    "สวนสัตว์", "สวนน้ำ", "ถนนคนเดิน", "attraction", "travel",
)

HOTEL_TRIGGERS = (
    "โรงแรม", "ที่พัก", "รีสอร์ท", "รีสอร์ต", "โฮมสเตย์", "พูลวิลล่า",
    "เกสต์เฮาส์", "บังกะโล", "ห้องพัก", "พักที่ไหนดี", "นอนไหนดี",
    "ที่พักใกล้", "โรงแรมใกล้", "hotel", "resort", "homestay",
)

_SUBTYPE_HINTS = {
    "restaurant": (
        ("คาเฟ่", "คาเฟ่"),
        ("ร้านกาแฟ", "คาเฟ่ ร้านกาแฟ"),
        ("อาหารทะเล", "ร้านอาหารทะเล"),
        ("ซีฟู้ด", "ร้านอาหารทะเล"),
        ("ก๋วยเตี๋ยว", "ร้านก๋วยเตี๋ยว"),
        ("หมูกระทะ", "ร้านหมูกระทะ"),
        ("บุฟเฟ่ต์", "บุฟเฟ่ต์"),
        ("บุฟเฟต์", "บุฟเฟ่ต์"),
        ("ชาบู", "ร้านชาบู"),
        ("ส้มตำ", "ร้านส้มตำ"),
        ("ตลาดโต้รุ่ง", "ตลาดโต้รุ่ง"),
        ("ตลาดกลางคืน", "ตลาดกลางคืน"),
    ),
    "attraction": (
        ("น้ำตก", "น้ำตก"),
        ("ชายหาด", "ชายหาด"),
        ("อุทยาน", "อุทยานแห่งชาติ"),
        ("จุดชมวิว", "จุดชมวิว"),
        ("ตลาดน้ำ", "ตลาดน้ำ"),
        ("ไหว้พระ", "วัดดัง"),
        ("วัดดัง", "วัดดัง"),
        ("ถนนคนเดิน", "ถนนคนเดิน"),
        ("พิพิธภัณฑ์", "พิพิธภัณฑ์"),
    ),
    "hotel": (
        ("พูลวิลล่า", "พูลวิลล่า"),
        ("รีสอร์ท", "รีสอร์ท"),
        ("รีสอร์ต", "รีสอร์ท"),
        ("โฮมสเตย์", "โฮมสเตย์"),
    ),
}

# แคชผลค้นหาจาก Nominatim (key -> (timestamp, list[dict])) อายุ 1 ชั่วโมง
_NOMINATIM_CACHE: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
_CACHE_TTL_SECS = 3600


def detect_place_category(text: str) -> Optional[str]:
    """คืนค่า 'hotel' | 'restaurant' | 'attraction' | None"""
    t = (text or "").strip().lower()
    if not t:
        return None
    if any(k in t for k in HOTEL_TRIGGERS):
        return "hotel"
    if any(k in t for k in RESTAURANT_TRIGGERS):
        return "restaurant"
    if any(k in t for k in ATTRACTION_TRIGGERS):
        return "attraction"
    return None


def is_places_query(text: str) -> bool:
    """ตรวจว่าข้อความเป็นการค้นหาร้านอาหาร / สถานที่ท่องเที่ยว / โรงแรมหรือไม่"""
    return detect_place_category(text) is not None


def _extract_place_location(text: str) -> Tuple[str, Optional[str], Optional[str]]:
    """สกัดชื่อพื้นที่/จังหวัด คืนค่า (loc_display, province, area)"""
    t = (text or "").strip().lower()
    for area, (prov, kw) in EXTRA_TOURIST_AREAS.items():
        if area in t:
            return f"{kw} {prov}", prov, kw

    crit = extract_location_criteria(text)
    prov = crit.get("province")
    area = crit.get("area")
    if area and prov:
        return f"{area} {prov}", prov, area
    if prov:
        return prov, prov, None
    return "ใกล้ฉัน", None, None


def _pick_search_keyword(cat: str, text: str) -> str:
    lower = (text or "").lower()
    for kw, label in _SUBTYPE_HINTS.get(cat, ()):
        if kw in lower:
            return label
    if cat == "restaurant":
        return "ร้านอาหารอร่อย"
    if cat == "attraction":
        return "สถานที่ท่องเที่ยว"
    return "โรงแรม ที่พัก"


_ALLOWED_OSM_TYPES = {
    "restaurant": {
        "amenity": {"restaurant", "cafe", "fast_food", "food_court", "ice_cream", "bakery"},
    },
    "hotel": {
        "tourism": {"hotel", "resort", "guest_house", "hostel", "motel", "chalet", "apartment"},
    },
    "attraction": {
        "tourism": {"attraction", "viewpoint", "museum", "theme_park", "zoo", "gallery"},
        "leisure": {"park", "nature_reserve", "water_park"},
        "historic": {"monument", "castle", "ruins", "archaeological_site", "memorial"},
        "natural": {"beach", "peak", "waterfall", "cave_entrance"},
        "amenity": {"place_of_worship"},
    },
}


def _fetch_nominatim_places(
    query: str,
    cat: str,
    province: Optional[str] = None,
    max_results: int = 3,
) -> List[Dict[str, str]]:
    """ค้นหาสถานที่จริงในประเทศไทยผ่าน OpenStreetMap Nominatim พร้อมกรองหมวดและจังหวัดอย่างเคร่งครัด"""
    cache_key = f"{cat}|{province or ''}|{query}"
    now = time.time()
    cached = _NOMINATIM_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECS:
        return cached[1][:max_results]

    allowed_map = _ALLOWED_OSM_TYPES.get(cat, {})
    results: List[Dict[str, str]] = []
    try:
        r = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "json",
                "countrycodes": "th",
                "limit": 10,
                "accept-language": "th",
            },
            headers={"User-Agent": "PaKhemCommunityHelperBot/1.0"},
            timeout=4.0,
        )
        if r.status_code == 200:
            seen = set()
            for item in r.json():
                osm_cls = (item.get("class") or "").lower()
                osm_type = (item.get("type") or "").lower()
                if osm_type not in allowed_map.get(osm_cls, set()):
                    continue
                disp = (item.get("display_name") or "").strip()
                if province and province not in disp:
                    # เช็กชื่อย่อจังหวัดบางกรณี เช่น กรุงเทพมหานคร/พระนครศรีอยุธยา
                    short_prov = province.replace("พระนครศรี", "").replace("มหานคร", "")
                    if short_prov not in disp:
                        continue
                name = (item.get("name") or disp.split(",")[0]).strip()
                lat = item.get("lat")
                lon = item.get("lon")
                if not name or not lat or not lon or name in seen or name == province:
                    continue
                seen.add(name)
                results.append(
                    {
                        "name": name,
                        "google_maps": f"https://www.google.com/maps?q={lat},{lon}",
                    }
                )
                if len(results) >= max_results:
                    break
    except Exception as exc:
        logger.debug("[places_service] Nominatim lookup skipped/failed: %s", exc)

    _NOMINATIM_CACHE[cache_key] = (now, results)
    return results[:max_results]


def format_places_directory_reply(text: str, max_results: int = 2) -> str:
    """สร้างคำตอบพิกัด ร้านอาหาร / สถานที่ท่องเที่ยว / โรงแรม แบบสั้น อ่านง่าย กดนำทางได้ทันที"""
    cat = detect_place_category(text) or "attraction"
    loc_display, prov, area = _extract_place_location(text)
    search_kw = _pick_search_keyword(cat, text)

    maps_query = f"{search_kw} {loc_display}"
    maps_all = f"https://www.google.com/maps/search/{urllib.parse.quote(maps_query)}"

    # ดึงพิกัดจริงจาก Nominatim เฉพาะกรณีที่ระบุจังหวัด/ย่านชัดเจน
    live_places: List[Dict[str, str]] = []
    if prov or area:
        osm_kw = {
            "restaurant": "restaurant",
            "attraction": "tourism",
            "hotel": "hotel",
        }.get(cat, search_kw)
        live_places = _fetch_nominatim_places(f"{search_kw} {loc_display}", cat=cat, province=prov, max_results=max_results)
        if not live_places:
            live_places = _fetch_nominatim_places(f"{osm_kw} {loc_display}", cat=cat, province=prov, max_results=max_results)

    if cat == "restaurant":
        header = f"🍜 {search_kw} ({loc_display}):"
        all_label = f"🗺️ ดูร้านแนะนำทั้งหมด + รีวิว: {maps_all}"
        tip = "💡 กดลิงก์เพื่อดูรีวิว เวลาเปิด-ปิด และกดนำทางได้เลยค่ะ"
    elif cat == "attraction":
        header = f"🗺️ {search_kw} ({loc_display}):"
        all_label = f"🗺️ ดูที่เที่ยวทั้งหมด + รีวิว: {maps_all}"
        tip = "💡 แนะนำเช็กเวลาเปิด-ปิดและสภาพอากาศก่อนเดินทางนะคะ"
    else:
        header = f"🏨 {search_kw} ({loc_display}):"
        all_label = f"🗺️ ดูที่พักทั้งหมด + รีวิว/ราคา: {maps_all}"
        tip = "💡 กดลิงก์เพื่อดูรูปห้องพัก รีวิว และเปรียบเทียบราคาได้เลยค่ะ"

    lines = [header]
    for p in live_places[:max_results]:
        lines.append(f"• {p['name']}")
        lines.append(f"  🗺️ {p['google_maps']}")

    lines.append(all_label)
    lines.append(tip)
    return "\n".join(lines).strip()
