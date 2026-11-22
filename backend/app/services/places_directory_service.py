"""backend/app/services/places_directory_service.py
ระบบค้นหาสิ่งอำนวยความสะดวกทั่วไทยฟรี 24 ชม. (ร้านอาหาร, สถานที่ท่องเที่ยว, โรงแรม/ที่พัก)
- แยกหมวดหมู่อัตโนมัติ (restaurant / attraction / hotel)
- สกัดจังหวัดและย่านยอดนิยมทั่วไทย (77 จังหวัด + ย่านท่องเที่ยว)
- ดึงพิกัดสถานที่จริงผ่าน OpenStreetMap Nominatim (ฟรี ไม่ใช้ API Key, มีแคชในหน่วยความจำ, timeout 4 วิ)
- พร้อมลิงก์ Google Maps Search เสมอ เพื่อให้กดดูรีวิว รูปภาพ เบอร์โทร และนำทางได้ทันที
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple

import httpx

from app.services.hospital_directory_service import ALL_77_PROVINCES, PROVINCE_ALIASES, extract_location_criteria

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
    "ร้านอาหาร", "ของกิน", "ของอร่อย", "ร้านอร่อย", "ร้านเด็ด", "กินอะไรดี", "กินไรดี", "กินอะไร",
    "หิวข้าว", "หิว", "หาของกิน", "อยากกิน", "กินข้าว", "อาหารเช้า", "อาหารเย็น", "ข้าวแกง",
    "คาเฟ่", "คาเฟ", "ร้านกาแฟ", "กาแฟ", "กาเเฟ", "ก๋วยเตี๋ยว", "ก๋วยเตียว", "กวยเตี๋ยว",
    "อาหารทะเล", "ซีฟู้ด", "ซีฟูด", "ซีฟู๊ด", "ข้าวมันไก่", "ข้าวขาหมู", "ผัดไทย",
    "บุฟเฟ่ต์", "บุฟเฟต์", "บุฟเฟ่", "บุฟเฟ", "หมูกระทะ", "หมูกะทะ", "ส้มตำ", "ชาบู", "ปิ้งย่าง",
    "ตลาดกลางคืน", "ตลาดโต้รุ่ง", "สตรีทฟู้ด", "อาหารพื้นเมือง", "restaurant", "cafe",
)

ATTRACTION_TRIGGERS = (
    "สถานที่ท่องเที่ยว", "แหล่งท่องเที่ยว", "ที่เที่ยว", "ที่เทียว", "ท่องเที่ยว", "ท่องเทียว", "เที่ยวไหนดี", "เที่ยวไหน",
    "ไปไหนดี", "วันหยุดไปไหน", "เดินเล่น", "พาครอบครัวเที่ยว", "พาลูกเที่ยว",
    "จุดเช็คอิน", "จุดเช็กอิน", "จุดเชคอิน", "แลนด์มาร์ค", "แลนด์มาร์ก", "แลนมารค", "น้ำตก", "ชายหาด", "ทะเล",
    "อุทยาน", "จุดชมวิว", "ชมวิว", "ตลาดน้ำ", "ไหว้พระ", "วัดดัง", "วัดสวย", "พิพิธภัณฑ์",
    "สวนสัตว์", "สวนน้ำ", "ถนนคนเดิน", "attraction", "travel",
)

HOTEL_TRIGGERS = (
    "โรงแรม", "โรงเเรม", "ที่พัก", "รีสอร์ท", "รีสอร์ต", "รีสอรท", "รีสอรต", "รีสอท", "รีสอต",
    "โฮมสเตย์", "โฮมสเต", "พูลวิลล่า", "พูลวิลลา",
    "เกสต์เฮาส์", "เกสเฮาส", "บังกะโล", "ห้องพัก", "พักที่ไหนดี", "พักไหนดี", "นอนไหนดี",
    "หาที่นอน", "หาห้องพัก", "จองห้อง", "ค้างคืน", "อยากพัก",
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
        ("พูลวิลลา", "พูลวิลล่า"),
        ("รีสอร์ท", "รีสอร์ท"),
        ("รีสอร์ต", "รีสอร์ท"),
        ("รีสอรท", "รีสอร์ท"),
        ("รีสอรต", "รีสอร์ท"),
        ("รีสอท", "รีสอร์ท"),
        ("รีสอต", "รีสอร์ท"),
        ("โฮมสเตย์", "โฮมสเตย์"),
        ("โฮมสเต", "โฮมสเตย์"),
    ),
}

# แคชผลค้นหาจาก Nominatim (key -> (timestamp, list[dict])) อายุ 1 ชั่วโมง
_NOMINATIM_CACHE: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
_CACHE_TTL_SECS = 3600


_SHORT_FOOD = ("กิน", "ข้าว", "อาหาร")
_SHORT_HOTEL = ("นอน", "พัก", "ห้อง")
_SHORT_TRAVEL = ("เที่ยว", "วัด")


def _match_short_trigger(t: str, words: Tuple[str, ...]) -> bool:
    s = (t or "").strip().lower()
    return any(s == w or s.startswith(w + " ") or s.endswith(" " + w) or f" {w} " in s for w in words)


def detect_place_category(text: str) -> Optional[str]:
    """คืนค่า 'hotel' | 'restaurant' | 'attraction' | None"""
    t = (text or "").strip().lower()
    if not t:
        return None
    if any(k in t for k in HOTEL_TRIGGERS) or _match_short_trigger(t, _SHORT_HOTEL):
        return "hotel"
    if any(k in t for k in RESTAURANT_TRIGGERS) or _match_short_trigger(t, _SHORT_FOOD):
        return "restaurant"
    if any(k in t for k in ATTRACTION_TRIGGERS) or _match_short_trigger(t, _SHORT_TRAVEL):
        return "attraction"
    return None


def is_places_query(text: str) -> bool:
    """ตรวจว่าข้อความเป็นการค้นหาร้านอาหาร / สถานที่ท่องเที่ยว / โรงแรมหรือไม่"""
    return detect_place_category(text) is not None


_FILLER_WORDS = (
    "ใกล้ฉัน", "ใกล้ผม", "แถวนี้", "แถว", "บริเวณ", "ในเขต", "ในตัว", "ตัวเมือง",
    "แนะนำ", "อร่อยๆ", "อร่อย", "ดังๆ", "ดัง", "ดีๆ", "ราคาถูก", "ถูกๆ",
    "ช่วยหา", "ขอพิกัด", "พิกัด", "แผนที่", "ค้นหา", "อยากไป", "มีไหม", "ไหม", "มั้ย",
    "หน่อย", "ครับ", "ค่ะ", "คะ", "จ้า", "นะ", "ที", "ที่", "ใน", "ของ",
)


def extract_detailed_place_location(text: str) -> Dict[str, object]:
    """แยกพิกัดละเอียด: ตำบล/แขวง | อำเภอ/เขต | ย่าน | จังหวัด"""
    working = (text or "").strip()
    tambon = ""
    amphoe = ""
    province = ""
    area = ""

    # 1. ตำบล / ต. / แขวง
    m_tambon = re.search(r"(?:ตำบล|ต\.|แขวง)\s*([ก-๙a-zA-Z0-9]+?)(?=\s|$|อ\.|อำเภอ|เขต|จ\.|จังหวัด)", working)
    if m_tambon:
        prefix = "แขวง" if m_tambon.group(0).startswith("แขวง") else "ต."
        tambon = prefix + m_tambon.group(1).strip()
        working = working.replace(m_tambon.group(0), " ", 1)

    # 2. อำเภอ / อ. / เขต
    m_amphoe = re.search(r"(?:อำเภอ|อ\.|เขต)\s*([ก-๙a-zA-Z0-9]+?)(?=\s|$|ต\.|ตำบล|แขวง|จ\.|จังหวัด)", working)
    if m_amphoe:
        prefix = "เขต" if m_amphoe.group(0).startswith("เขต") else "อ."
        amphoe = prefix + m_amphoe.group(1).strip()
        working = working.replace(m_amphoe.group(0), " ", 1)

    # 3. จังหวัด (ทั้งแบบมี จ./จังหวัด และไม่มี)
    m_prov = re.search(r"(?:จังหวัด|จ\.)\s*([ก-๙]+)", working)
    if m_prov:
        cand = m_prov.group(1).strip()
        if cand in PROVINCE_ALIASES:
            province = PROVINCE_ALIASES[cand]
            working = working.replace(m_prov.group(0), " ", 1)
        else:
            for p in ALL_77_PROVINCES:
                if p == cand or cand in p:
                    province = p
                    working = working.replace(m_prov.group(0), " ", 1)
                    break

    if not province:
        for p in sorted(ALL_77_PROVINCES, key=len, reverse=True):
            if p in working:
                province = p
                working = working.replace(p, " ", 1)
                break

    if not province:
        for alias, std in sorted(PROVINCE_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
            if alias in working.lower():
                province = std
                working = re.sub(re.escape(alias), " ", working, count=1, flags=re.IGNORECASE)
                break

    # 4. ย่านท่องเที่ยวยอดนิยม
    for ak, (prov_val, kw_val) in sorted(EXTRA_TOURIST_AREAS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if ak in working:
            area = kw_val
            if not province:
                province = prov_val
            working = working.replace(ak, " ", 1)
            break

    if not province or not area:
        crit = extract_location_criteria(text)
        if not province and crit.get("province"):
            province = crit["province"]
        if not area and crit.get("area"):
            area = crit["area"]

    # 5. ชื่ออำเภอ/ตำบล/ย่านที่ไม่ได้พิมพ์ อ./ต. นำหน้า
    if not tambon and not amphoe and not area:
        cleaned = working.lower()
        all_kws = sorted(
            RESTAURANT_TRIGGERS + ATTRACTION_TRIGGERS + HOTEL_TRIGGERS + _FILLER_WORDS + _SHORT_FOOD + _SHORT_HOTEL + _SHORT_TRAVEL,
            key=len,
            reverse=True,
        )
        for kw in all_kws:
            cleaned = cleaned.replace(kw.lower(), " ")
        cleaned = re.sub(r"[^ก-๙a-zA-Z0-9\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if 2 <= len(cleaned) <= 35:
            area = cleaned

    # 6. ถ้ายังไม่มีจังหวัด แต่มีชื่ออำเภอ/พื้นที่ (เช่น "รีสอรท มหาราช" หรือ "กิน บางปะหัน")
    #    เติมอำเภอ + จังหวัดให้อัตโนมัติจากฐานข้อมูล 928 อำเภอทั่วไทย (ไม่หลุดไปจังหวัดอื่น!)
    if not province and (amphoe or area):
        try:
            from app.services.thai_address_validator import lookup_thai_area_by_name
            q_area = re.sub(r"^(?:อ\.|อำเภอ|เขต|ต\.|ตำบล|แขวง)", "", (amphoe or area)).strip()
            if len(q_area) >= 2:
                hit = lookup_thai_area_by_name(q_area)
                if hit and hit.get("province"):
                    province = str(hit["province"])
                    if not amphoe and hit.get("amphoe"):
                        prefix = "เขต" if hit.get("is_bkk") else "อ."
                        amphoe = prefix + str(hit["amphoe"])
                        if area == hit.get("amphoe"):
                            area = ""
        except Exception:
            pass

    display_parts: List[str] = []
    query_parts: List[str] = []
    if tambon:
        display_parts.append(tambon)
        query_parts.append(re.sub(r"^ต\.", "ตำบล", tambon))
    if amphoe:
        display_parts.append(amphoe)
        query_parts.append(re.sub(r"^อ\.", "อำเภอ", amphoe))
    if area and area not in (amphoe, tambon):
        display_parts.append(area)
        query_parts.append(area)
    if province:
        prov_label = province if province == "กรุงเทพมหานคร" else f"จ.{province}"
        display_parts.append(prov_label)
        query_parts.append(province)

    is_specific = bool(tambon or amphoe or area)
    has_explicit_location = bool(tambon or amphoe or province)
    display_label = " | ".join(display_parts) if display_parts else "ใกล้ฉัน (ไม่ได้ระบุพื้นที่)"
    map_query_loc = " ".join(query_parts) if query_parts else "ใกล้ฉัน"

    return {
        "tambon": tambon,
        "amphoe": amphoe,
        "area": area,
        "province": province or None,
        "has_explicit_location": has_explicit_location,
        "is_specific": is_specific,
        "display_label": display_label,
        "map_query_loc": map_query_loc,
    }


def format_area_bundle_reply(text: str) -> Optional[str]:
    """หากผู้ใช้พิมพ์แค่ชื่อจังหวัด/อำเภอ/ตำบล (เช่น 'สุโขทัย' หรือ 'อ.บางปะหัน อยุธยา') คืนชุดพิกัด 4 หมวดทันที"""
    loc = extract_detailed_place_location(text)
    if not loc.get("has_explicit_location"):
        return None
    q = str(loc["map_query_loc"])
    label = str(loc["display_label"])
    h_url = f"https://www.google.com/maps/search/{urllib.parse.quote('โรงพยาบาล ' + q)}"
    f_url = f"https://www.google.com/maps/search/{urllib.parse.quote('ร้านอาหารอร่อย ' + q)}"
    t_url = f"https://www.google.com/maps/search/{urllib.parse.quote('สถานที่ท่องเที่ยว ' + q)}"
    r_url = f"https://www.google.com/maps/search/{urllib.parse.quote('โรงแรม ที่พัก ' + q)}"
    return (
        f"📍 รวมพิกัดสะดวก: {label}\n"
        f"🏥 โรงพยาบาล: {h_url}\n"
        f"🍜 ร้านอาหาร: {f_url}\n"
        f"🗺️ ที่เที่ยว: {t_url}\n"
        f"🏨 โรงแรม/ที่พัก: {r_url}\n"
        f"🚑 ฉุกเฉินโทรฟรี 1669 ค่ะ"
    )


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
    """สร้างคำตอบพิกัด ร้านอาหาร / สถานที่ท่องเที่ยว / โรงแรม แบบแยก ตำบล | อำเภอ | จังหวัด ชัดเจน"""
    cat = detect_place_category(text) or "attraction"
    loc = extract_detailed_place_location(text)
    loc_display = str(loc["display_label"])
    map_query_loc = str(loc["map_query_loc"])
    prov = loc["province"]
    is_specific = bool(loc["is_specific"])
    search_kw = _pick_search_keyword(cat, text)

    maps_query = f"{search_kw} {map_query_loc}"
    maps_all = f"https://www.google.com/maps/search/{urllib.parse.quote(maps_query)}"

    live_places: List[Dict[str, str]] = []
    if prov or is_specific:
        osm_kw = {
            "restaurant": "restaurant",
            "attraction": "tourism",
            "hotel": "hotel",
        }.get(cat, search_kw)
        live_places = _fetch_nominatim_places(f"{search_kw} {map_query_loc}", cat=cat, province=prov, max_results=max_results)
        if not live_places:
            live_places = _fetch_nominatim_places(f"{osm_kw} {map_query_loc}", cat=cat, province=prov, max_results=max_results)

    if cat == "restaurant":
        header = f"🍜 {search_kw}"
        all_label = f"🗺️ ดูร้านแนะนำ + รีวิว: {maps_all}"
        sample_prefix = "ร้านอาหาร"
    elif cat == "attraction":
        header = f"🗺️ {search_kw}"
        all_label = f"🗺️ ดูที่เที่ยว + รีวิว: {maps_all}"
        sample_prefix = "ที่เที่ยว"
    else:
        header = f"🏨 {search_kw}"
        all_label = f"🗺️ ดูที่พัก + รีวิว/ราคา: {maps_all}"
        sample_prefix = "โรงแรม"

    lines = [header, f"📍 พื้นที่: {loc_display}"]
    for p in live_places[:max_results]:
        lines.append(f"• {p['name']}")
        lines.append(f"  🗺️ {p['google_maps']}")

    lines.append(all_label)
    if not is_specific:
        prov_sample = str(prov or "อยุธยา").replace("พระนครศรี", "")
        lines.append(f'🔎 ระบุเจาะจงพื้นที่ได้นะคะ เช่น "{sample_prefix} อ.เมือง {prov_sample}" หรือ "{sample_prefix} ต.เสาธง อ.บางปะหัน {prov_sample}"')
    return "\n".join(lines).strip()
