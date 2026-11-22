"""backend/app/services/hospital_directory_service.py
ระบบค้นหาและแยกแยะโรงพยาบาล "คน" และ "สัตว์" อย่างชัดเจน 100%
รวบรวมคลังคีย์เวิร์ดที่คนไทยนิยมพิมพ์ค้นหาบนอินเทอร์เน็ต (Google/Search Engine) ทั้งหมด
- โรงพยาบาลรักษาคน (Human): 12,186 แห่ง จาก data/hospitals_thailand.csv
- สถานพยาบาลสัตว์ (Vet/Animal): 224 แห่ง จาก data/vet_hospitals_thailand.csv
"""
import csv
import logging
import re
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


HUMAN_CSV_PATH = _find_csv("hospitals_thailand.csv")
VET_CSV_PATH = _find_csv("vet_hospitals_thailand.csv")
PHARMACY_CSV_PATH = _find_csv("pharmacies_thailand.csv")

_CACHED_HUMAN: List[Dict[str, str]] = []
_CACHE_HUMAN_MTIME: float = 0.0

_CACHED_VET: List[Dict[str, str]] = []
_CACHE_VET_MTIME: float = 0.0

_CACHED_PHARMACY: List[Dict[str, str]] = []
_CACHE_PHARMACY_MTIME: float = 0.0

# ==============================================================================
# 🐾 คลังคีย์เวิร์ดฝั่ง "สัตว์ / สัตว์เลี้ยง" (อินเทอร์เน็ตเสิร์ชยอดนิยม)
# ==============================================================================
ANIMAL_FACILITY_TERMS = (
    "รพ.สัตว์", "รพ สัตว์", "โรงพยาบาลสัตว์", "คลินิกสัตว์", "คลินิกรักษาสัตว์",
    "คลีนิกสัตว์", "คลีนิกรักษาสัตว์", "สถานพยาบาลสัตว์", "ศูนย์รักษาสัตว์"
)

ANIMAL_DOCTOR_TERMS = (
    "สัตวแพทย์", "หมอสัตวแพทย์", "หมอสัตว์", "หมอหมา", "หมอแมว",
    "หมอกระต่าย", "หมอนก", "หมอ exotic", "หมอสัตว์แปลก"
)

PET_NAMES = (
    "หมา", "สุนัข", "น้องหมา", "ลูกหมา", "ไอ้ตูบ", "หมาน้อย",
    "แมว", "น้องแมว", "ลูกแมว", "เหมียว", "แมวน้อย",
    "กระต่าย", "ชูก้า", "ชูการ์", "กระรอก", "นก", "หนูแฮมเตอร์", "แฮมเตอร์",
    "เม่นแคระ", "สัตว์แปลก", "exotic pet", "สัตว์เลี้ยง"
)

VET_PROCEDURES = (
    "ทำหมันหมา", "ทำหมันแมว", "ทำหมันสุนัข", "ทำหมันสัตว์",
    "วัคซีนหมา", "วัคซีนแมว", "วัคซีนสุนัข", "วัคซีนสัตว์",
    "ฉีดวัคซีนหมา", "ฉีดวัคซีนแมว", "ฉีดวัคซีนสุนัข", "ฉีดวัคซีนสัตว์",
    "พิษสุนัขบ้า", "พยาธิหนอนหัวใจ", "หยอดเห็บ", "หยอดหมัด", "เห็บหมัด",
    "ตัดไหมหมา", "ตัดไหมแมว", "คลอดลูกหมา", "คลอดลูกแมว", "อัลตราซาวด์แมว", "อัลตราซาวด์หมา"
)

ANIMAL_SYMPTOMS = (
    "หมาป่วย", "แมวป่วย", "สัตว์ป่วย", "หมาไม่สบาย", "แมวไม่สบาย",
    "หมาซึม", "แมวซึม", "หมาอ้วก", "แมวอ้วก", "หมาไม่กินข้าว", "แมวไม่กินข้าว",
    "หมาโดนรถชน", "แมวโดนรถชน", "หมาโดนกัด", "แมวโดนกัด", "แมวฉี่ไม่ออก",
    "หมาฉี่เป็นเลือด", "หมาท้องเสีย", "แมวท้องเสีย"
)

ALL_ANIMAL_TRIGGERS = (
    ANIMAL_FACILITY_TERMS + ANIMAL_DOCTOR_TERMS + PET_NAMES +
    VET_PROCEDURES + ANIMAL_SYMPTOMS + ("vet", "veterinary", "pet hospital", "animal hospital")
)


# ==============================================================================
# 🚑 คลังคีย์เวิร์ดกู้ชีพฉุกเฉิน 1669 (Emergency EMS Triggers - สพฉ.)
# ==============================================================================
EMERGENCY_EMS_TRIGGERS = (
    "1669", "ขอรถพยาบาล", "เรียกรถพยาบาล", "เรียกรถฉุกเฉิน", "รถพยาบาล",
    "กู้ชีพ", "กู้ภัย", "รถกู้ชีพ", "หน่วยกู้ชีพ", "ศูนย์นเรนทร",
    "หมดสติ", "ไม่หายใจ", "หัวใจหยุดเต้น", "ปั๊มหัวใจ", "cpr", "aed",
    "แน่นหน้าอกรุนแรง", "เจ็บหน้าอกเฉียบพลัน", "ปากเบี้ยว", "แขนขาอ่อนแรง",
    "สโตรกเฉียบพลัน", "เลือดออกไม่หยุด", "ช็อก", "สำลักอาหารไม่หายใจ", "จมน้ำ"
)

# ==============================================================================
# 🏥 คลังคีย์เวิร์ดฝั่ง "คน / มนุษย์" (อินเทอร์เน็ตเสิร์ชยอดนิยม)
# ==============================================================================
HUMAN_FACILITY_TERMS = (
    "โรงพยาบาลคน", "รพ.คน", "คลินิกคน", "ศูนย์แพทย์", "ศูนย์บริการสาธารณสุข",
    "ศบส.", "รพ.สต.", "สถานีอนามัย", "อนามัย", "รพ.ศูนย์", "รพ.ทั่วไป", "รพ.ชุมชน",
    "ห้องฉุกเฉิน", "ฉุกเฉิน 1669", "กู้ชีพ 1669", "สายด่วน 1669", "1669"
)

HUMAN_DOCTOR_TERMS = (
    "หมอคน", "แพทย์", "นายแพทย์", "แพทย์หญิง", "คุณหมอคน", "หาหมอคน", "พบหมอคน"
)

HUMAN_SPECIALTIES = (
    "อายุรกรรม", "ศัลยกรรม", "สูตินรีเวช", "คลอดบุตร", "ฝากครรภ์", "ทำคลอด",
    "กุมารเวช", "แผนกเด็ก", "ออร์โธปิดิกส์", "กระดูกและข้อ", "จักษุ", "ผ่าตัดตา",
    "หูคอจมูก", "ผิวหนัง", "จิตเวช", "ไตเทียม", "ฟอกไต", "โรคหัวใจ", "โรคมะเร็ง",
    "ทันตกรรม", "หมอฟัน", "ถอนฟัน", "ผ่าฟันคุด", "ขูดหินปูน"
)

HUMAN_SYMPTOMS = (
    "คนป่วย", "ผู้ป่วย", "ไม่สบาย", "เป็นไข้", "ตัวร้อน", "เจ็บป่วย",
    "ปวดหัวข้างเดียว", "ไมเกรน", "เจ็บหน้าอก", "แน่นหน้าอก", "หายใจไม่ออก",
    "ความดันสูง", "เบาหวาน", "เส้นเลือดสมอง", "สโตรก", "stroke", "อัมพฤกษ์",
    "อุบัติเหตุคน", "คนโดนรถชน", "ตรวจสุขภาพประจำปี", "ตรวจสุขภาพ", "เช็คร่างกาย"
)

HUMAN_SCHEMES = (
    "บัตรทอง", "30บาทรักษาทุกโรค", "สปสช", "ประกันสังคม", "สิทธิบัตรทอง", "สิทธิประกันสังคม"
)

FAMOUS_HUMAN_HOSPITALS = (
    "ศิริราช", "จุฬา", "จุฬาลงกรณ์", "รามา", "รามาธิบดี", "พระมงกุฎ", "ราชวิถี",
    "เลิดสิน", "วชิระ", "ธรรมศาสตร์", "ศรีนครินทร์", "มหาราชนครเชียงใหม่",
    "สมิติเวช", "บำรุงราษฎร์", "พญาไท", "กรุงเทพ", "เกษมราษฎร์", "เปาโล", "วิภาวดี",
    "ธนบุรี", "รามคำแหง", "สินแพทย์", "เจ้าพระยา", "หัวเฉียว", "มิชชั่น", "เซนต์หลุยส์"
)

HOSPITAL_NICKNAMES = {
    "สวนดอก": "มหาราชนครเชียงใหม่",
    "รพ.สวนดอก": "มหาราชนครเชียงใหม่",
    "มอ.": "สงขลานครินทร์",
    "รพ.มอ": "สงขลานครินทร์",
    "รพ.มอ.": "สงขลานครินทร์",
    "มข.": "ศรีนครินทร์",
    "รพ.มข": "ศรีนครินทร์",
    "รพ.มข.": "ศรีนครินทร์",
    "จุฬา": "จุฬาลงกรณ์",
    "รพ.จุฬา": "จุฬาลงกรณ์",
    "รามา": "รามาธิบดี",
    "รพ.รามา": "รามาธิบดี",
    "ศิริราช": "ศิริราช",
    "รพ.ศิริราช": "ศิริราช",
    "พระมงกุฎ": "พระมงกุฎเกล้า",
    "รพ.พระมงกุฎ": "พระมงกุฎเกล้า",
    "รพ.ตำรวจ": "ตำรวจ",
    "สวนปรุง": "สวนปรุง",
    "ศรีธัญญา": "ศรีธัญญา",
}

ALL_HUMAN_SPECIFIC_TRIGGERS = (
    HUMAN_FACILITY_TERMS + HUMAN_DOCTOR_TERMS + HUMAN_SPECIALTIES +
    HUMAN_SYMPTOMS + HUMAN_SCHEMES + FAMOUS_HUMAN_HOSPITALS + tuple(HOSPITAL_NICKNAMES.keys())
)

# คำกลางๆ ทั่วไป
GENERAL_HOSPITAL_TRIGGERS = (
    "โรงพยาบาล", "รพ.", "รพ ", "คลินิก", "คลีนิก", "สถานพยาบาล", "หาหมอ", "พบหมอ",
    "ฉุกเฉิน", "ห้องตรวจ", "ตรวจเลือด", "เอกซเรย์", "x-ray", "อัลตราซาวด์"
)

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


def load_human_hospitals() -> List[Dict[str, str]]:
    """โหลดข้อมูลโรงพยาบาลคน 12,186 แห่ง"""
    global _CACHED_HUMAN, _CACHE_HUMAN_MTIME
    if not HUMAN_CSV_PATH.exists():
        logger.warning(f"[hospital_service] Human CSV not found: {HUMAN_CSV_PATH}")
        return []
    try:
        mtime = HUMAN_CSV_PATH.stat().st_mtime
        if _CACHED_HUMAN and mtime == _CACHE_HUMAN_MTIME:
            return _CACHED_HUMAN
        with open(HUMAN_CSV_PATH, "r", encoding="utf-8-sig") as f:
            _CACHED_HUMAN = list(csv.DictReader(f))
        _CACHE_HUMAN_MTIME = mtime
        return _CACHED_HUMAN
    except Exception as e:
        logger.error(f"[hospital_service] Error loading human hospitals: {e}")
        return _CACHED_HUMAN or []


def load_vet_hospitals() -> List[Dict[str, str]]:
    """โหลดข้อมูลสถานพยาบาลสัตว์ 224 แห่ง"""
    global _CACHED_VET, _CACHE_VET_MTIME
    if not VET_CSV_PATH.exists():
        logger.warning(f"[hospital_service] Vet CSV not found: {VET_CSV_PATH}")
        return []
    try:
        mtime = VET_CSV_PATH.stat().st_mtime
        if _CACHED_VET and mtime == _CACHE_VET_MTIME:
            return _CACHED_VET
        with open(VET_CSV_PATH, "r", encoding="utf-8-sig") as f:
            _CACHED_VET = list(csv.DictReader(f))
        _CACHE_VET_MTIME = mtime
        return _CACHED_VET
    except Exception as e:
        logger.error(f"[hospital_service] Error loading vet hospitals: {e}")
        return _CACHED_VET or []


def load_pharmacies() -> List[Dict[str, str]]:
    """โหลดข้อมูลร้านขายยา 24,888 แห่งทั่วไทย (อย.)"""
    global _CACHED_PHARMACY, _CACHE_PHARMACY_MTIME
    if not PHARMACY_CSV_PATH.exists():
        logger.warning(f"[hospital_service] Pharmacy CSV not found: {PHARMACY_CSV_PATH}")
        return []
    try:
        mtime = PHARMACY_CSV_PATH.stat().st_mtime
        if _CACHED_PHARMACY and mtime == _CACHE_PHARMACY_MTIME:
            return _CACHED_PHARMACY
        with open(PHARMACY_CSV_PATH, "r", encoding="utf-8-sig") as f:
            _CACHED_PHARMACY = list(csv.DictReader(f))
        _CACHE_PHARMACY_MTIME = mtime
        return _CACHED_PHARMACY
    except Exception as e:
        logger.error(f"[hospital_service] Error loading pharmacies: {e}")
        return _CACHED_PHARMACY or []


# ==============================================================================
# 💊 คลังคีย์เวิร์ดร้านขายยา (Pharmacy Triggers)
# ==============================================================================
PHARMACY_TRIGGERS = (
    "ร้านขายยา", "ร้านยา", "ซื้อยา", "ขายยา", "หาซื้อยา", "เภสัช", "เภสัชกร", "เภสัชกรรม",
    "ร้านขายยาสัตว์", "ยาสัตว์", "ยาหมา", "ยาแมว", "ร้านยาใกล้ฉัน", "ร้านขายยาใกล้ฉัน",
    "ยาแก้ปวด", "ยาพารา", "ยาลดไข้", "ยาแก้แพ้", "ยานอนหลับ", "ยาฆ่าเชื้อ", "ฟาร์มาซี", "โอสถ"
)


def is_pharmacy_query(text: str) -> bool:
    """ตรวจว่าข้อความถามเกี่ยวกับร้านขายยา หรือการซื้อยาหรือไม่"""
    t = (text or "").strip().lower()
    return any(k in t for k in PHARMACY_TRIGGERS)


def detect_patient_category(text: str) -> str:
    """แยกแยะอย่างชัดเจน 100% ว่าคำค้นหาบนอินเทอร์เน็ตนี้หมายถึง "คน" หรือ "สัตว์"
    คืนค่า: 'animal' (สัตว์) | 'human' (คน) | 'ambiguous' (ไม่ระบุชัดเจน/ก้ำกึ่ง)
    """
    t = (text or "").strip().lower()

    # ระวังคำซ้ำซ้อนในชื่อสถานที่ไทย เช่น "เกาะหมาก", "แก่งหางแมว", "หัวหมาก" ไม่ใช่สัตว์
    place_exceptions = ("เกาะหมาก", "แก่งหางแมว", "หัวหมาก", "บางหมาก", "บ้านหางแมว", "ช่องแมว", "ลานหมาไน", "ห้วยสัตว์ใหญ่")
    t_clean_for_animal = t
    for ex in place_exceptions:
        t_clean_for_animal = t_clean_for_animal.replace(ex, "")

    has_animal = any(k in t_clean_for_animal for k in ALL_ANIMAL_TRIGGERS)
    # ตรวจสอบคีย์เวิร์ดคน (ต้องระวังคำว่า "แพทย์" ที่ติดอยู่ใน "สัตวแพทย์")
    t_clean_for_human = t.replace("สัตวแพทย์", "").replace("สัตวบาล", "")
    has_human = any(k in t_clean_for_human for k in ALL_HUMAN_SPECIFIC_TRIGGERS)
    has_emergency = is_emergency_ems_query(t)

    # 0. เหตุฉุกเฉินวิกฤต / รถพยาบาล 1669 (หากไม่มีคำว่าสัตว์ ถือเป็นคน 100%)
    if has_emergency and not has_animal:
        return "human"

    # 1. มีคีย์เวิร์ดสัตว์ชัดเจน และไม่มีคีย์เวิร์ดคนเฉพาะทาง
    if has_animal and not has_human:
        return "animal"

    # 2. มีคีย์เวิร์ดคนชัดเจน และไม่มีคีย์เวิร์ดสัตว์
    if has_human and not has_animal:
        return "human"

    # 3. มีทั้งคู่ในประโยคเดียวกัน (เช่น "คนหรือสัตว์", "หมอคนกับหมอหมา")
    if has_animal and has_human:
        return "ambiguous"

    # 4. มีคำเรียกโรงพยาบาล/คลินิกทั่วไป แต่ไม่มีคีย์เวิร์ดสัตว์เลย
    has_general = any(k in t for k in GENERAL_HOSPITAL_TRIGGERS)
    if has_general:
        # คำถามที่สั้นมากๆ เช่น "หาหมอ", "คลินิกใกล้ฉัน", "ตรวจเลือด" ให้ถามหรือตอบทั้ง 2 หมวด
        stripped = t.replace(" ", "").replace("ๆ", "")
        if stripped in ("หาหมอ", "หาหมอใกล้ฉัน", "คลินิกใกล้ฉัน", "คลินิก", "หมอ", "ไปหาหมอ", "ตรวจเลือด", "ตรวจสุขภาพ"):
            return "ambiguous"
        # หากมีชื่อจังหวัด หรือมีคำว่า "โรงพยาบาล" / "รพ." ลอยๆ มักหมายถึงคนตามพฤติกรรมค้นหา
        return "human"

    return "unknown"


def is_emergency_ems_query(text: str) -> bool:
    """ตรวจสอบว่าคำถามเป็นเหตุฉุกเฉินวิกฤตที่ต้องเรียกรถพยาบาล / กู้ชีพ 1669 ตามมาตรฐาน สพฉ. หรือไม่"""
    t = (text or "").strip().lower()
    return any(k in t for k in EMERGENCY_EMS_TRIGGERS)


def is_any_hospital_query(text: str) -> bool:
    """ตรวจสอบว่าข้อความถามเกี่ยวกับสถานพยาบาล หรือร้านขายยา (คน หรือ สัตว์) หรือไม่"""
    if is_emergency_ems_query(text):
        return True
    if is_pharmacy_query(text):
        return True
    cat = detect_patient_category(text)
    return cat in ("animal", "human", "ambiguous")


def extract_location_criteria(text: str):
    """สกัดจังหวัด อำเภอ และเงื่อนไขฉุกเฉิน"""
    t = (text or "").strip().lower()
    matched_province = None
    matched_area = None

    for area, (prov, kw) in POPULAR_AREAS.items():
        if area in t:
            matched_province = prov
            matched_area = kw
            break

    if not matched_province:
        for alias, standard in PROVINCE_ALIASES.items():
            if alias in t:
                matched_province = standard
                break

    if not matched_province:
        for p in sorted(ALL_77_PROVINCES, key=len, reverse=True):
            if p in t or f"จ.{p}" in t or f"จังหวัด{p}" in t:
                matched_province = p
                break

    is_24h = any(k in t for k in ("24 ชม", "24ชม", "24 ชั่วโมง", "24ชั่วโมง", "ฉุกเฉิน", "ทั้งคืน"))
    is_near_me = any(k in t for k in ("ใกล้ฉัน", "ใกล้ผม", "ใกล้ๆ", "แถวนี้", "ใกล้ที่สุด"))

    return {
        "province": matched_province,
        "area": matched_area,
        "is_24h": is_24h,
        "is_near_me": is_near_me,
        "raw_text": t
    }


def search_human_hospitals(text: str, max_results: int = 5) -> Tuple[List[Dict[str, str]], dict]:
    """ค้นหาโรงพยาบาลรักษาคน รองรับคีย์เวิร์ดอาการและแผนก"""
    hospitals = load_human_hospitals()
    crit = extract_location_criteria(text)
    if not hospitals:
        return [], crit

    prov = crit["province"]
    area = crit["area"]
    raw = crit["raw_text"]

    # ตรวจจับชื่อเล่น รพ.
    target_nickname = None
    for nick, real in HOSPITAL_NICKNAMES.items():
        if nick in raw:
            target_nickname = real
            break

    filtered = []
    for r in hospitals:
        p_th = r.get("province_th", "").replace("จังหวัด", "").strip()
        if prov and p_th != prov and r.get("province_th") != prov:
            continue

        name = r.get("name", "")
        addr = r.get("address", "")
        h_type = r.get("type", "")
        lvl = r.get("service_level", "")

        score = 0
        if target_nickname and target_nickname in name:
            score += 50

        if "โรงพยาบาลศูนย์" in h_type or "มหาวิทยาลัย" in h_type or "ระดับ A" in lvl:
            score += 15
        elif "โรงพยาบาลทั่วไป" in h_type or "โรงพยาบาลชุมชน" in h_type or "โรงพยาบาลเอกชน" in h_type:
            score += 10
        elif "รพ.สต." in h_type:
            score += 2

        if ("รพ.สต." in raw or "อนามัย" in raw) and "รพ.สต." in h_type:
            score += 25
        if "เอกชน" in raw and "เอกชน" in h_type:
            score += 30

        if area and (area in name or area in addr):
            score += 30

        for word in raw.split():
            if len(word) >= 3 and (word in name or word in addr):
                score += 10

        filtered.append((score, r))

    filtered.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in filtered[:max_results]], crit


def search_vet_hospitals(text: str, max_results: int = 5) -> Tuple[List[Dict[str, str]], dict]:
    """ค้นหาสถานพยาบาลสัตว์"""
    from app.services.vet_hospital_service import search_vet_hospitals as orig_search_vet
    return orig_search_vet(text, max_results=max_results)


def search_pharmacies(text: str, max_results: int = 2) -> Tuple[List[Dict[str, str]], dict]:
    """ค้นหาร้านขายยาแผนปัจจุบัน/โบราณ 24,888 แห่งทั่วไทย (อย.)"""
    crit = extract_location_criteria(text)
    province = crit["province"]
    area = crit["area"]
    raw = (text or "").lower()

    is_vet = any(k in raw for k in ("สัตว์", "หมา", "แมว", "ยาสัตว์", "ร้านขายยาสัตว์"))
    all_pharm = load_pharmacies()

    # กรองประเภท คน หรือ สัตว์
    if is_vet:
        pool = [p for p in all_pharm if "สัตว์" in p.get("patient_category", "")]
    else:
        pool = [p for p in all_pharm if "สัตว์" not in p.get("patient_category", "")]

    if province:
        pool = [p for p in pool if province in p.get("province", "")]

    scored = []
    for p in pool:
        name = p.get("name", "")
        addr = p.get("address", "")
        cat_lic = p.get("license_category", "")
        score = 0
        if "ร้านขายยา" in cat_lic or "ข.ย.1" in cat_lic:
            score += 25
        elif "ขายส่ง" in cat_lic:
            score -= 10
        if "บริษัท" in name:
            score -= 5

        if area and (area in name or area in addr):
            score += 30

        for w in raw.split():
            if len(w) >= 3 and (w in name or w in addr):
                score += 10
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:max_results]], crit


def format_emergency_1669_guide(province: Optional[str] = None) -> str:
    """สร้างข้อความฉุกเฉิน 1669 แบบสั้นกระชับ ตรงประเด็น"""
    prov_str = f" ({province})" if province else ""
    return (
        f"🚨 เหตุฉุกเฉินวิกฤต โทรฟรีสายด่วน 1669 (กู้ชีพ 24 ชม.){prov_str}\n"
        f"📞 กดโทรออกทันที: 1669 (โทรฟรีทุกเครือข่าย)\n"
        f"📍 แจ้งจุดสังเกตเด่น อาการผู้ป่วย และพิกัด GPS ให้เจ้าหน้าที่ฟังนะคะ"
    )


def format_hospital_directory_reply(text: str, max_results: int = 2) -> str:
    """ตอบกลับแบบสั้น กระชับ ตรงประเด็น (ไม่พิมพ์ยาว)"""
    is_emergency = is_emergency_ems_query(text)
    cat = detect_patient_category(text)
    crit = extract_location_criteria(text)
    province = crit["province"]
    area = crit["area"]

    loc_str = area or province or "ใกล้ฉัน"

    # 0. หมวดร้านขายยา (Pharmacy)
    if is_pharmacy_query(text):
        is_vet = any(k in text.lower() for k in ("สัตว์", "หมา", "แมว", "ยาสัตว์", "ร้านขายยาสัตว์"))
        search_kw = f"ร้านขายยาสัตว์ {loc_str}" if is_vet else f"ร้านขายยา {loc_str}"
        maps_all = f"https://www.google.com/maps/search/{urllib.parse.quote(search_kw)}"

        if is_vet:
            return (
                f"🐾 ร้านขายยาสัตว์ ({loc_str}):\n"
                f"🗺️ พิกัดและเบอร์โทร: {maps_all}\n"
                f"💡 ปรึกษาสัตวแพทย์ก่อนใช้ยานะคะ"
            )

        results, _ = search_pharmacies(text, max_results=max_results)
        lines = [f"💊 ร้านขายยา ({loc_str}):"]
        for r in results[:2]:
            name = r.get("name", "ร้านขายยา")
            maps = r.get("google_maps", "")
            lines.append(f"• {name}")
            if maps:
                lines.append(f"  🗺️ {maps}")

        lines.append(f"🗺️ ดูร้านขายยาทั้งหมด: {maps_all}")
        lines.append("💡 ปรึกษาเภสัชกรก่อนใช้ยานะคะ")
        return "\n".join(lines).strip()

    # 1. หมวดสัตว์ (Animal / Vet)
    if cat == "animal":
        maps_link = f"https://www.google.com/maps/search/{urllib.parse.quote('โรงพยาบาลสัตว์ ' + loc_str)}"
        return (
            f"🐾 สถานพยาบาลสัตว์ ({loc_str}):\n"
            f"🗺️ พิกัดและเบอร์โทร: {maps_link}\n"
            f"💡 แนะนำโทรสอบถามเวลาก่อนเดินทางนะคะ"
        )

    # 2. หมวดคน (Human Hospital)
    if cat == "human":
        prov_query = province or "ใกล้ฉัน"
        search_engine_kw = f"โรงพยาบาล {prov_query}"
        maps_all = f"https://www.google.com/maps/search/{urllib.parse.quote(search_engine_kw)}"

        if is_emergency:
            ems_guide = format_emergency_1669_guide(province)
            return (
                f"{ems_guide}\n"
                f"🗺️ แผนที่ รพ.ฉุกเฉิน: {maps_all}"
            )

        results, _ = search_human_hospitals(text, max_results=max_results)
        lines = [f"🏥 โรงพยาบาล ({loc_str}):"]
        for r in results[:2]:
            name = r.get("name", "โรงพยาบาล")
            maps = r.get("google_maps", "")
            lines.append(f"• {name}")
            if maps:
                lines.append(f"  🗺️ {maps}")

        lines.append(f"🗺️ ดูพิกัด รพ. ทั้งหมด: {maps_all}")
        lines.append("🚑 ฉุกเฉินโทรฟรี 1669 ค่ะ")
        return "\n".join(lines).strip()

    # 3. หมวดกำกวม (สั้น 4 บรรทัด)
    maps_h = f"https://www.google.com/maps/search/{urllib.parse.quote('โรงพยาบาล ' + loc_str)}"
    maps_v = f"https://www.google.com/maps/search/{urllib.parse.quote('โรงพยาบาลสัตว์ ' + loc_str)}"
    return (
        f"🏥 พิกัด รพ.คน ({loc_str}): {maps_h}\n"
        f"🐾 พิกัด รพ.สัตว์ ({loc_str}): {maps_v}\n"
        f"🚑 ฉุกเฉินทางการแพทย์ โทร 1669 (ฟรี 24 ชม.)"
    )
