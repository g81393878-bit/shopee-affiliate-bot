"""backend/app/services/vet_hospital_service.py
บริการค้นหาโรงพยาบาลและคลินิกรักษาสัตว์ทั่วไทยจากไฟล์ data/vet_hospitals_thailand.csv
ครอบคลุม 77 จังหวัดทั่วไทย และเชื่อมโยงแผนที่นำทาง Google Maps
"""
import csv
import logging
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def _find_csv(filename: str) -> Path:
    candidates = [
        ROOT_DIR / "data" / filename,
        Path(__file__).resolve().parent.parent / "data" / filename,
        Path(__file__).resolve().parent.parent.parent / "data" / filename,
        Path.cwd() / "app" / "data" / filename,
        Path.cwd() / "data" / filename,
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


CSV_PATH = _find_csv("vet_hospitals_thailand.csv")

_CACHED_VETS: List[Dict[str, str]] = []
_CACHE_MTIME: float = 0.0

VET_KEYWORDS = (
    "รพ.สัตว์", "รพ สัตว์", "โรงพยาบาลสัตว์", "คลินิกสัตว์", "คลินิกรักษาสัตว์",
    "คลีนิกสัตว์", "คลีนิกรักษาสัตว์", "รักษาสัตว์", "หาหมอหมา", "หาหมอแมว",
    "หมอหมา", "หมอแมว", "สัตว์เลี้ยงป่วย", "พาสัตว์ไปหาหมอ", "พาหมาไปหาหมอ",
    "พาแมวไปหาหมอ", "สัตวแพทย์", "คลินิกหมา", "คลินิกแมว", "รพ.หมา", "รพ.แมว",
    "vet", "veterinary", "หมอสัตว์"
)

# รายชื่อ 77 จังหวัดทั่วประเทศไทย
ALL_77_PROVINCES = [
    "กรุงเทพมหานคร", "สมุทรปราการ", "นนทบุรี", "ปทุมธานี", "พระนครศรีอยุธยา", "อ่างทอง", "ลพบุรี", "สิงห์บุรี", "ชัยนาท", "สระบุรี",
    "ชลบุรี", "ระยอง", "จันทบุรี", "ตราด", "ฉะเชิงเทรา", "ปราจีนบุรี", "นครนายก", "สระแก้ว",
    "นครราชสีมา", "บุรีรัมย์", "สุรินทร์", "ศรีสะเกษ", "อุบลราชธานี", "ยโสธร", "ชัยภูมิ", "อำนาจเจริญ", "บึงกาฬ", "หนองบัวลำภู",
    "ขอนแก่น", "อุดรธานี", "เลย", "หนองคาย", "มหาสารคาม", "ร้อยเอ็ด", "กาฬสินธุ์", "สกลนคร", "นครพนม", "มุกดาหาร",
    "เชียงใหม่", "ลำพูน", "ลำปาง", "อุตรดิตถ์", "แพร่", "น่าน", "พะเยา", "เชียงราย", "แม่ฮ่องสอน",
    "นครสวรรค์", "อุทัยธานี", "กำแพงเพชร", "ตาก", "สุโขทัย", "พิษณุโลก", "พิจิตร", "เพชรบูรณ์",
    "ราชบุรี", "กาญจนบุรี", "สุพรรณบุรี", "นครปฐม", "สมุทรสาคร", "สมุทรสงคราม", "เพชรบุรี", "ประจวบคีรีขันธ์",
    "นครศรีธรรมราช", "กระบี่", "พังงา", "ภูเก็ต", "สุราษฎร์ธานี", "ระนอง", "ชุมพร", "สงขลา", "สตูล", "ตรัง", "พัทลุง", "ปัตตานี", "ยะลา", "นราธิวาส"
]

PROVINCE_ALIASES = {
    "กทม": "กรุงเทพมหานคร",
    "กทม.": "กรุงเทพมหานคร",
    "กรุงเทพ": "กรุงเทพมหานคร",
    "กรุงเทพฯ": "กรุงเทพมหานคร",
    "โคราช": "นครราชสีมา",
    "อยุธยา": "พระนครศรีอยุธยา",
}

# เมือง/อำเภอสำคัญที่คนชอบพิมพ์ค้นหาโดยไม่ระบุจังหวัด
POPULAR_AREAS = {
    "พัทยา": ("ชลบุรี", "พัทยา"),
    "หาดใหญ่": ("สงขลา", "หาดใหญ่"),
    "หัวหิน": ("ประจวบคีรีขันธ์", "หัวหิน"),
    "บางแสน": ("ชลบุรี", "บางแสน"),
    "ศรีราชา": ("ชลบุรี", "ศรีราชา"),
    "รังสิต": ("ปทุมธานี", "รังสิต"),
    "บางนา": ("กรุงเทพมหานคร", "บางนา"),
    "ลาดพร้าว": ("กรุงเทพมหานคร", "ลาดพร้าว"),
    "แม่ริม": ("เชียงใหม่", "แม่ริม"),
    "ป่าตอง": ("ภูเก็ต", "ป่าตอง"),
    "เกาะสมุย": ("สุราษฎร์ธานี", "เกาะสมุย"),
    "สมุย": ("สุราษฎร์ธานี", "สมุย"),
}


def load_vet_data() -> List[Dict[str, str]]:
    """โหลดข้อมูลจาก CSV พร้อมแคชอัตโนมัติ"""
    global _CACHED_VETS, _CACHE_MTIME
    if not CSV_PATH.exists():
        logger.warning(f"[vet_service] CSV file not found: {CSV_PATH}")
        return []
    try:
        mtime = CSV_PATH.stat().st_mtime
        if _CACHED_VETS and mtime == _CACHE_MTIME:
            return _CACHED_VETS
        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            data = [dict(row) for row in reader]
        _CACHED_VETS = data
        _CACHE_MTIME = mtime
        return _CACHED_VETS
    except Exception as e:
        logger.error(f"[vet_service] Error loading vet data: {e}")
        return _CACHED_VETS or []


def is_vet_query(text: str) -> bool:
    """ตรวจสอบว่าผู้ใช้พิมพ์ถามเรื่องคลินิก/โรงพยาบาลรักษาสัตว์หรือไม่"""
    if not text:
        return False
    t = text.strip().lower()
    return any(k in t for k in VET_KEYWORDS)


def extract_search_criteria(text: str):
    """แยกเงื่อนไขการค้นหา: จังหวัด, อำเภอ, 24 ชม., ประเภท"""
    t = (text or "").strip().lower()

    matched_province = None
    matched_area = None

    # 1. ตรวจจับพื้นที่/อำเภอยอดนิยมก่อน
    for area, (prov, kw) in POPULAR_AREAS.items():
        if area in t:
            matched_province = prov
            matched_area = kw
            break

    # 2. ตรวจจับชื่อย่อจังหวัด
    if not matched_province:
        for alias, standard in PROVINCE_ALIASES.items():
            if alias in t:
                matched_province = standard
                break

    # 3. ตรวจจับ 77 จังหวัด
    if not matched_province:
        for p in sorted(ALL_77_PROVINCES, key=len, reverse=True):
            if p in t or f"จ.{p}" in t or f"จังหวัด{p}" in t:
                matched_province = p
                break

    is_24h = any(k in t for k in ("24 ชม", "24ชม", "24 ชั่วโมง", "24ชั่วโมง", "ฉุกเฉิน", "ทั้งคืน", "ตลอด 24"))
    hospital_only = "โรงพยาบาล" in t or "รพ." in t
    clinic_only = "คลินิก" in t or "คลีนิก" in t
    is_near_me = "ใกล้ฉัน" in t or "ใกล้ผม" in t or "ใกล้ๆ" in t or "แถวนี้" in t

    return {
        "province": matched_province,
        "area": matched_area,
        "is_24h": is_24h,
        "hospital_only": hospital_only,
        "clinic_only": clinic_only,
        "is_near_me": is_near_me,
        "raw_text": t
    }


def search_vet_hospitals(text: str, max_results: int = 5) -> Tuple[List[Dict[str, str]], dict]:
    """ค้นหาสถานพยาบาลสัตว์ที่ตรงกับเงื่อนไข คืนค่า (ผลลัพธ์, criteria)"""
    vets = load_vet_data()
    crit = extract_search_criteria(text)
    if not vets:
        return [], crit

    province = crit["province"]
    area = crit["area"]
    is_24h = crit["is_24h"]
    hosp_only = crit["hospital_only"]
    clinic_only = crit["clinic_only"]
    raw = crit["raw_text"]

    filtered = []
    for r in vets:
        p_th = r.get("province_th", "").replace("จังหวัด", "").strip()
        # กรองจังหวัดถ้าผู้ใช้ระบุชัดเจน
        if province and p_th != province and r.get("province_th") != province:
            continue

        # กรอง 24 ชม.
        if is_24h:
            e24 = (r.get("emergency_24h") or "").lower()
            hrs = (r.get("opening_hours") or "").lower()
            if not (e24 in ("yes", "24/7") or "24/7" in hrs or "24" in hrs):
                continue

        name = r.get("name", "")
        addr = r.get("address", "")
        dist = r.get("district", "")
        t_type = r.get("type", "")

        score = 0
        if name:
            score += 10
        if r.get("phone"):
            score += 5
        if r.get("google_maps"):
            score += 3
        if r.get("opening_hours"):
            score += 2

        # เพิ่มคะแนนตรงประเภท
        if hosp_only and "โรงพยาบาล" in t_type:
            score += 4
        if clinic_only and "คลินิก" in t_type:
            score += 4

        # ตรวจจับชื่ออำเภอ/พื้นที่
        if area and (area in name or area in addr or area in dist):
            score += 20

        # ตรวจคำค้นทั่วไป
        for word in raw.split():
            if len(word) >= 3 and (word in name.lower() or word in addr.lower() or word in dist.lower()):
                score += 8

        filtered.append((score, r))

    filtered.sort(key=lambda x: x[0], reverse=True)
    results = [item[1] for item in filtered[:max_results]]
    return results, crit


def format_vet_reply(text: str, max_results: int = 5) -> str:
    """จัดรูปแบบข้อความตอบกลับภาษาไทยอย่างเป็นกันเอง รองรับทุกที่ทั่วประเทศ"""
    results, crit = search_vet_hospitals(text, max_results=max_results)
    province = crit["province"]
    area = crit["area"]
    is_24h = crit["is_24h"]
    is_near_me = crit["is_near_me"]

    # 1. กรณีระบุจังหวัด/พื้นที่ แต่ใน CSV ไม่มีข้อมูล
    if not results and province:
        loc_str = f"{area} " if area else ""
        loc_str += f"จังหวัด{province}" if province != "กรุงเทพมหานคร" else "กรุงเทพมหานคร"
        search_kw = f"โรงพยาบาลสัตว์ {loc_str}"
        if is_24h:
            search_kw += " 24 ชั่วโมง"
        encoded = urllib.parse.quote(search_kw)
        maps_link = f"https://www.google.com/maps/search/{encoded}"

        return (
            f"🐾 ป้าเข็มช่วยค้นหาข้อมูลสถานพยาบาลสัตว์ใน {loc_str} ให้แล้วนะคะ 🙏\n\n"
            f"เนื่องจากในฐานข้อมูลเปิดยังไม่มีรายชื่อของพื้นที่นี้ ป้าเข็มได้สร้างลิงก์ค้นหาพิกัด รพ./คลินิกสัตว์ใน {loc_str} บน Google Maps ให้คุณกดนำทางได้ทันทีค่ะ:\n"
            f"🗺️ แผนที่นำทาง: {maps_link}\n\n"
            f"💡 หากต้องการให้ค้นหาจังหวัดใกล้เคียง หรือพื้นที่อื่นๆ พิมพ์บอกป้าเข็มได้เลยนะคะ 😊🐶🐱"
        )

    # 2. กรณีผู้ใช้พิมพ์ "ใกล้ฉัน" โดยไม่ระบุพื้นที่
    if is_near_me and not province and not area:
        search_kw = "โรงพยาบาลสัตว์ ใกล้ฉัน"
        if is_24h:
            search_kw += " 24 ชั่วโมง"
        maps_link = f"https://www.google.com/maps/search/{urllib.parse.quote(search_kw)}"

        lines = [
            "🐾 ป้าเข็มแนะนำสถานพยาบาลสัตว์ยอดนิยมให้ก่อนนะคะ:",
            f"📍 แตะเพื่อดูคลินิก/รพ.สัตว์ที่อยู่ใกล้คุณที่สุดบนแผนที่: {maps_link}",
            ""
        ]
        for idx, r in enumerate(results[:3], 1):
            name = r.get("name") or "สถานพยาบาลสัตว์"
            phone = r.get("phone") or "ไม่ระบุเบอร์โทร"
            maps = r.get("google_maps") or ""
            lines.append(f"{idx}. 🏥 {name} (📞 {phone})")
            if maps:
                lines.append(f"   🗺️ นำทาง: {maps}")
        lines.append("")
        lines.append("💡 เพื่อให้ตรงตำแหน่งของคุณที่สุด คุณสามารถพิมพ์ระบุชื่อจังหวัดหรืออำเภอได้เลยนะคะ เช่น 'รพ.สัตว์ นนทบุรี', 'คลินิกสัตว์ พัทยา 24 ชม.' ค่ะ 😊")
        return "\n".join(lines).strip()

    # 3. กรณีพบผลลัพธ์ในฐานข้อมูล
    header_loc = ""
    if area:
        header_loc = f" ({area})"
    elif province:
        header_loc = f" (จังหวัด{province})" if province != "กรุงเทพมหานคร" else " (กรุงเทพมหานคร)"

    header_title = f"🐾 รายชื่อสถานพยาบาลสัตว์{header_loc} ที่ป้าเข็มหาให้ค่ะ:"
    if is_24h:
        header_title += "\n(🚑 เปิดบริการ 24 ชม. / ฉุกเฉิน)"

    lines = [header_title, ""]

    for idx, r in enumerate(results, 1):
        name = r.get("name") or "สถานพยาบาลสัตว์ (ตามพิกัด)"
        v_type = r.get("type") or "สถานพยาบาลสัตว์"
        phone = r.get("phone") or "ไม่ระบุเบอร์โทร"
        hours = r.get("opening_hours")
        maps = r.get("google_maps")
        addr = r.get("address") or r.get("district") or r.get("province_th") or ""

        block = [f"{idx}. 🏥 {name}"]
        if v_type and v_type != name:
            block.append(f"   • ประเภท: {v_type}")
        if addr:
            block.append(f"   • ที่อยู่: {addr}")
        block.append(f"   • 📞 โทร: {phone}")
        if hours:
            block.append(f"   • ⏰ เวลาเปิด: {hours}")
        if maps:
            block.append(f"   • 🗺️ นำทาง: {maps}")
        lines.append("\n".join(block))
        lines.append("")

    # เพิ่มลิงก์ดูเพิ่มเติมบน Google Maps สำหรับพื้นที่นั้น
    query_prov = province or "ใกล้ฉัน"
    maps_more = f"https://www.google.com/maps/search/{urllib.parse.quote('โรงพยาบาลสัตว์ ' + query_prov)}"
    lines.append(f"🗺️ ดูสถานพยาบาลสัตว์ทั้งหมดในพื้นที่นี้บน Google Maps: {maps_more}")
    lines.append("💡 หากต้องการค้นหาจังหวัดอื่น หรือเปิด 24 ชม. พิมพ์บอกป้าเข็มได้เลยนะคะ เช่น 'รพ.สัตว์ ชลบุรี 24 ชม.' ค่ะ 😊🐶🐱")

    return "\n".join(lines).strip()
