"""backend/app/api/hospitals_api.py
API ค้นหาโรงพยาบาลคนและสัตว์ 77 จังหวัด สำหรับหน้าเว็บแผนที่แบบ Interactive Map (Leaflet.js)
รองรับการกรองตามระดับบริการทางการแพทย์ (Service Level) อ้างอิง สธ. และวิกิพีเดีย
"""
from fastapi import APIRouter, Query
from typing import Optional, List, Dict
from app.services.hospital_directory_service import (
    load_human_hospitals,
    load_vet_hospitals,
    ALL_77_PROVINCES,
)

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.get("/provinces")
def get_all_provinces():
    """คืนค่ารายชื่อ 77 จังหวัดทั่วไทย"""
    return {"provinces": ALL_77_PROVINCES}


@router.get("/search")
def search_hospitals_for_map(
    patient_type: str = Query("all", description="all | human | animal"),
    province: Optional[str] = Query(None, description="ชื่อจังหวัด"),
    query: Optional[str] = Query(None, description="คำค้นชื่อ รพ. หรืออำเภอ"),
    service_level: Optional[str] = Query(None, description="center | university | general | private | all"),
    is_24h: bool = Query(False, description="เฉพาะเปิด 24 ชม."),
    limit: int = Query(400, le=3000, description="จำนวนจำกัดผลลัพธ์")
) -> Dict:
    """ค้นหารายการสถานพยาบาลสำหรับพล็อตลงบนแผนที่ Leaflet"""
    results: List[Dict] = []
    
    q_low = (query or "").strip().lower()
    p_clean = (province or "").replace("จังหวัด", "").strip() if province else ""

    # 1. โหลดข้อมูลตามประเภทที่ร้องขอ
    items_to_filter = []
    if patient_type in ("all", "human"):
        human_list = load_human_hospitals()
        items_to_filter.extend(human_list)
    if patient_type in ("all", "animal"):
        vet_list = load_vet_hospitals()
        items_to_filter.extend(vet_list)

    for r in items_to_filter:
        p_th = r.get("province_th", "").replace("จังหวัด", "").strip()
        if p_clean and p_th != p_clean and r.get("province_th") != p_clean:
            continue

        lat_str = r.get("latitude", "").strip()
        lon_str = r.get("longitude", "").strip()
        if not lat_str or not lon_str:
            continue

        try:
            lat = float(lat_str)
            lon = float(lon_str)
            if not (5.0 <= lat <= 21.0 and 96.0 <= lon <= 106.0):
                continue
        except ValueError:
            continue

        cat = r.get("patient_category", "")
        lvl = r.get("service_level", "")

        # กรอง service_level
        if service_level and service_level != "all":
            if service_level == "center" and "ระดับ A" not in lvl:
                continue
            if service_level == "university" and "มหาวิทยาลัย" not in lvl and "โรงเรียนแพทย์" not in lvl:
                continue
            if service_level == "general" and "ระดับ S/M1" not in lvl:
                continue
            if service_level == "private" and "เอกชน" not in lvl:
                continue

        # กรอง 24 ชม.
        if is_24h:
            e24 = (r.get("emergency_24h") or "").lower()
            hrs = (r.get("opening_hours") or "").lower()
            h_type = r.get("type", "")
            is_human_emergency = "คน" in cat and ("โรงพยาบาลศูนย์" in h_type or "โรงพยาบาลทั่วไป" in h_type or "โรงพยาบาลเอกชน" in h_type or "ระดับ A" in lvl)
            is_vet_emergency = "สัตว์" in cat and (e24 in ("yes", "24/7") or "24/7" in hrs or "24" in hrs)
            if not (is_human_emergency or is_vet_emergency):
                continue

        name = r.get("name", "")
        addr = r.get("address", "")
        dist = r.get("district", "")

        # กรองคีย์เวิร์ด
        if q_low:
            haystack = f"{name} {addr} {dist} {p_th} {lvl}".lower()
            if q_low not in haystack:
                continue

        results.append({
            "name": name,
            "patient_category": cat,
            "service_level": lvl,
            "type": r.get("type", "สถานพยาบาล"),
            "sector": r.get("sector", ""),
            "province": p_th,
            "address": addr,
            "phone": r.get("phone", ""),
            "opening_hours": r.get("opening_hours", ""),
            "lat": lat,
            "lon": lon,
            "google_maps": r.get("google_maps") or f"https://www.google.com/maps?q={lat},{lon}",
        })

        if len(results) >= limit:
            break

    return {
        "total": len(results),
        "patient_type": patient_type,
        "service_level": service_level,
        "province": province,
        "items": results
    }
