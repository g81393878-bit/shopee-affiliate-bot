"""

ระบบฐานข้อมูลรหัสไปรษณีย์ -> ตำบล/แขวง อำเภอ/เขต จังหวัด ทั้งประเทศไทย (970 รหัส 7,436 ตำบล)

และฟังก์ชันตรวจสอบความครบถ้วนของที่อยู่ + เบอร์โทรศัพท์ 10 หลัก ก่อนเปิดบิลทุกช่องทาง (100% Strict Validation)

"""

from __future__ import annotations



import json

import os

import re

from pathlib import Path

from typing import Any



_THAI_ZIP_DB: dict[str, dict[str, Any]] | None = None

_THAI_DIGIT_TRANS = str.maketrans("๐๑๒๓๔๕๖๗๘๙０１２３４５６７８９", "01234567890123456789")





def normalize_thai_digits(text: str) -> str:

    """แปลงตัวเลขไทย (๐-๙) เป็นเลขอารบิก (0-9) เพื่ออำนวยความสะดวกลูกค้าผู้สูงอายุที่แป้นพิมพ์ติดเลขไทย"""

    return str(text or "").translate(_THAI_DIGIT_TRANS)





def get_thai_zip_db() -> dict[str, dict[str, Any]]:

    global _THAI_ZIP_DB

    if _THAI_ZIP_DB:

        return _THAI_ZIP_DB



    app_dir = Path(__file__).resolve().parents[1]

    root_dir = Path(__file__).resolve().parents[3]

    candidates = [

        app_dir / "static" / "thai_zip_db.js",

        root_dir / "gas_project" / "ThaiZipMap.gs",

        Path(os.getcwd()) / "backend" / "app" / "static" / "thai_zip_db.js",

        Path(os.getcwd()) / "gas_project" / "ThaiZipMap.gs",

    ]

    for path in candidates:

        if path.exists():

            try:

                raw = path.read_text(encoding="utf-8")

                idx = raw.find("{")

                last_idx = raw.rfind("}")

                if idx != -1 and last_idx != -1:

                    _THAI_ZIP_DB = json.loads(raw[idx : last_idx + 1])

                    if _THAI_ZIP_DB:

                        return _THAI_ZIP_DB

            except Exception:

                pass



    # Fallback สำหรับ Cloud Render: ดึงฐานข้อมูลรหัสไปรษณีย์ 970 รหัสจาก Supabase Storage หรือ GitHub Pages แล้วแคชลงดิสก์ทันที

    import httpx

    remote_urls = [

        "https://usqhvujqmnxqrdoovvnp.supabase.co/storage/v1/object/public/slips/render_code/thai_zip_db.js",

        "https://watt29.github.io/pakhem-shop/thai_zip_db.js",

    ]

    for url in remote_urls:

        try:

            r = httpx.get(url, timeout=8)

            if r.status_code == 200 and "{" in r.text:

                raw = r.text

                idx = raw.find("{")

                last_idx = raw.rfind("}")

                if idx != -1 and last_idx != -1:

                    _THAI_ZIP_DB = json.loads(raw[idx : last_idx + 1])

                    if _THAI_ZIP_DB:

                        try:

                            target_cache = app_dir / "static" / "thai_zip_db.js"

                            target_cache.parent.mkdir(parents=True, exist_ok=True)

                            target_cache.write_text(raw, encoding="utf-8")

                        except Exception:

                            pass

                        return _THAI_ZIP_DB

        except Exception:

            pass



    _THAI_ZIP_DB = {}

    return _THAI_ZIP_DB





def lookup_thai_zip(zip_code: str) -> dict[str, Any] | None:

    clean_zip = re.sub(r"\D", "", normalize_thai_digits(str(zip_code or "")))

    if len(clean_zip) != 5:

        return None

    db = get_thai_zip_db()

    entry = db.get(clean_zip)

    if not entry:

        return None

    is_bkk = clean_zip.startswith("10") or ("กรุงเทพ" in str(entry.get("p", "")))

    raw_t = entry.get("t") or []

    if isinstance(raw_t, list):

        tambons = [str(t).strip() for t in raw_t if str(t).strip()]

    else:

        tambons = [t.strip() for t in str(raw_t).split("|") if t.strip()]

    amp_name = str(entry.get("a", "")).strip()

    priority_t = [t for t in ("เสาธง", amp_name) if t in tambons]

    ordered_tambons = priority_t + [t for t in tambons if t not in priority_t]

    return {

        "zip": clean_zip,

        "amphoe": amp_name,

        "province": str(entry.get("p", "")).strip(),

        "tambons": ordered_tambons,

        "is_bkk": is_bkk,

    }





def lookup_thai_area_by_name(query: str) -> dict[str, Any] | None:

    """

    ค้นหารหัสไปรษณีย์ + อำเภอ/เขต + จังหวัด + รายชื่อตำบล จากชื่ออำเภอ/เขต หรือชื่อตำบล

    สำหรับผู้สูงอายุที่จำรหัสไปรษณีย์ 5 หลักไม่ได้ (พิมพ์แค่ชื่ออำเภอ เช่น 'บางกะปิ', 'บางปะหัน', 'ปากเกร็ด')

    """

    raw = normalize_thai_digits(str(query or "")).strip()

    if len(raw) < 2 or len(raw) > 60:

        return None

    if any(

        w in raw.lower()

        for w in [

            "โอน", "ส่งฟรี", "ปลายทาง", "ราคา", "เท่าไหร่", "ชุด", "กิโล", "กก", "กรัม",

            "500g", "1kg", "2kg", "390", "410", "550", "570", "1090", "1,090", "เลขบัญชี",

        ]

    ):

        return None

    cleaned = re.sub(r"^(?:อำเภอ|อ\.|เขต|ตำบล|ต\.|แขวง|จังหวัด|จ\.)\s*", "", raw).strip()

    if len(cleaned) < 2:

        return None

    db = get_thai_zip_db()

    # 1. Exact Amphoe match

    for zcode, entry in db.items():

        amp = re.sub(r"^เขต", "", str(entry.get("a", "")).strip()).strip()

        prov = str(entry.get("p", "")).strip()

        if cleaned == amp or cleaned == f"{amp} {prov}" or (amp and len(amp) >= 3 and amp in raw and (not prov or prov in raw or len(cleaned) <= len(amp) + 3)):

            info = lookup_thai_zip(zcode)

            if info:

                for t in info["tambons"]:

                    if t != amp and t in raw:

                        info["matched_tambon"] = t

                        break

                return info

    # 2. Exact Tambon match

    for zcode, entry in db.items():

        raw_t = entry.get("t") or []

        tambons = [str(t).strip() for t in raw_t] if isinstance(raw_t, list) else [t.strip() for t in str(raw_t).split("|")]

        for t in tambons:

            if t and (cleaned == t or f"ต.{t}" in raw or f"ตำบล{t}" in raw or f"แขวง{t}" in raw):

                info = lookup_thai_zip(zcode)

                if info:

                    info["matched_tambon"] = t

                    return info

    return None





def calculate_shipping_route_info(address_text: str) -> dict[str, Any]:

    """

    คำนวณระยะทางโดยประมาณ (กม.) จากจุดผลิต ต.เสาธง อ.บางปะหัน จ.พระนครศรีอยุธยา (13220)

    และประเมินจำนวนวันจัดส่ง (1–2 วัน vs 3–4 วัน) พร้อมสิทธิ์การเก็บเงินปลายทาง (COD) ตามพื้นที่

    (มาตรฐานเดียวกับ LINE OA `calculateShippingRouteInfo` ใน `tools/shopee_pakhem_bot.gs`)

    """

    raw = str(address_text or "").strip()

    dist_km = 0



    zip_match = re.search(r"\b([1-9]\d)\d{3}\b", raw)

    zip_prefix = zip_match.group(1) if zip_match else ""

    zip_dist_map = {

        "13": 20, "14": 28, "15": 60, "16": 52, "17": 95, "18": 48,

        "12": 55, "11": 72, "10": 85, "72": 68, "73": 110, "74": 115, "75": 140,

        "70": 155, "71": 155, "76": 195, "77": 290,

        "26": 95, "25": 125, "24": 125, "20": 165, "21": 220, "27": 210, "22": 290, "23": 345,

        "60": 165, "61": 135, "66": 250, "65": 300, "67": 280, "62": 270, "64": 340, "63": 360,

        "30": 215, "36": 265, "31": 355, "32": 390, "33": 495, "34": 565, "35": 490, "37": 535,

        "38": 680, "39": 465, "40": 385, "41": 500, "42": 460, "43": 555, "44": 415, "45": 450,

        "46": 460, "47": 580, "48": 670, "49": 600,

        "50": 620, "51": 595, "52": 535, "53": 395, "54": 485, "55": 600, "56": 660, "57": 750, "58": 820,

        "80": 840, "81": 860, "82": 840, "83": 900, "84": 710, "85": 650, "86": 530,

        "90": 1010, "91": 1030, "92": 890, "93": 910, "94": 1110, "95": 1140, "96": 1200,

    }

    if zip_prefix and zip_prefix in zip_dist_map:

        dist_km = zip_dist_map[zip_prefix]



    if not dist_km:

        prov_check = [

            (["อยุธยา", "บางปะหัน"], 20),

            (["อ่างทอง"], 28),

            (["สระบุรี"], 48),

            (["สิงห์บุรี"], 52),

            (["ปทุมธานี", "รังสิต", "คลองหลวง", "ธัญบุรี", "ลำลูกกา"], 55),

            (["ลพบุรี"], 60),

            (["สุพรรณบุรี"], 68),

            (["นนทบุรี", "ปากเกร็ด", "บางบัวทอง", "บางใหญ่"], 72),

            (["กรุงเทพ", "กทม", "บางนา", "ลาดพร้าว", "จตุจักร", "พระโขนง", "ดอนเมือง", "สายไหม", "บางกะปิ", "ธนบุรี", "บางแค", "พระราม"], 85),

            (["ชัยนาท", "นครนายก"], 95),

            (["สมุทรปราการ", "บางพลี", "สำโรง"], 105),

            (["นครปฐม", "ศาลายา"], 110),

            (["สมุทรสาคร", "มหาชัย", "กระทุ่มแบน"], 115),

            (["ฉะเชิงเทรา", "ปราจีนบุรี"], 125),

            (["อุทัยธานี", "สมุทรสงคราม"], 138),

            (["กาญจนบุรี", "ราชบุรี"], 155),

            (["ชลบุรี", "พัทยา", "ศรีราชา", "บางแสน", "นครสวรรค์"], 165),

            (["เพชรบุรี", "ชะอำ"], 195),

            (["สระแก้ว", "นครราชสีมา", "โคราช", "ปากช่อง"], 215),

            (["ระยอง"], 220),

            (["พิจิตร", "ชัยภูมิ"], 255),

            (["กำแพงเพชร", "เพชรบูรณ์"], 275),

            (["จันทบุรี", "ประจวบ", "หัวหิน"], 290),

            (["พิษณุโลก"], 300),

            (["สุโขทัย", "ตราด"], 340),

            (["บุรีรัมย์", "ตาก", "แม่สอด"], 360),

            (["ขอนแก่น", "สุรินทร์", "อุตรดิตถ์"], 390),

            (["มหาสารคาม", "ร้อยเอ็ด", "เลย", "กาฬสินธุ์", "หนองบัวลำภู"], 450),

            (["แพร่", "ยโสธร", "ศรีสะเกษ", "อุดรธานี"], 495),

            (["ลำปาง", "ชุมพร", "อำนาจเจริญ", "หนองคาย", "อุบลราชธานี", "สกลนคร", "ลำพูน"], 560),

            (["เชียงใหม่", "น่าน", "มุกดาหาร", "ระนอง", "พะเยา", "นครพนม", "บึงกาฬ"], 630),

            (["สุราษฎร์", "สมุย", "เชียงราย"], 730),

            (["แม่ฮ่องสอน", "นครศรีธรรมราช", "พังงา", "กระบี่", "ตรัง", "ภูเก็ต", "พัทลุง"], 870),

            (["สงขลา", "หาดใหญ่", "สตูล", "ปัตตานี", "ยะลา", "นราธิวาส"], 1050),

        ]

        for keys, d_val in prov_check:

            if any(k in raw for k in keys):

                dist_km = d_val

                break



    if not dist_km:

        dist_km = 85



    far_prefixes = {

        "31", "32", "33", "34", "35", "37", "38", "39",

        "40", "41", "42", "43", "44", "45", "46", "47", "48", "49",

        "50", "51", "52", "53", "54", "55", "56", "57", "58",

        "63",

        "80", "81", "82", "83", "84", "85", "86",

        "90", "91", "92", "93", "94", "95", "96",

    }

    is_far_3to4_days = (dist_km > 350) or (bool(zip_prefix) and zip_prefix in far_prefixes)

    est_days = "3–4 วัน" if is_far_3to4_days else "1–2 วัน"

    allow_cod = not is_far_3to4_days

    ship_method_short = "รถห้องเย็นควบคุมอุณหภูมิ" if is_far_3to4_days else "แพ็กซองฟอยล์เก็บความเย็น"

    summary_line = f"🚚 ระยะทาง ~{dist_km} กม. จากอยุธยา (จัดส่งถึงใน {est_days} • {ship_method_short})"



    return {

        "distance_km": dist_km,

        "est_days": est_days,

        "is_far_3to4_days": is_far_3to4_days,

        "allow_cod": allow_cod,

        "ship_method_short": ship_method_short,

        "summary_line": summary_line,

    }





def validate_thai_phone(raw_phone: str) -> dict[str, Any]:

    digits = re.sub(r"\D", "", normalize_thai_digits(str(raw_phone or "")))

    if not digits:

        return {"valid": False, "phone": "", "reason": "ยังไม่ได้ระบุเบอร์โทรศัพท์"}

    if len(digits) < 10:

        return {"valid": False, "phone": digits, "reason": f"เบอร์โทรศัพท์มีแค่ {len(digits)} หลัก (ต้องครบ 10 หลัก)"}

    if len(digits) > 10:

        return {"valid": False, "phone": digits, "reason": f"เบอร์โทรศัพท์เกินเป็น {len(digits)} หลัก (ต้องมี 10 หลักพอดี)"}

    if not re.match(r"^0[2689]\d{8}$", digits):

        return {"valid": False, "phone": digits, "reason": "รูปแบบเบอร์โทรไม่ถูกต้อง (ต้องขึ้นต้นด้วย 06, 08, 09 หรือ 02)"}

    fake_list = {

        "0812345678",

        "0891234567",

        "0912345678",

        "0612345678",

        "0800000000",

        "0900000000",

        "0600000000",

        "0999999999",

        "0888888888",

    }

    if digits in fake_list or re.match(r"^0\d(\d)\1{7}$", digits) or digits.endswith("1234567") or digits.endswith("12345678"):

        return {"valid": False, "phone": digits, "reason": "เป็นเบอร์ตัวอย่างหรือตัวเลขเรียงกัน กรุณาพิมพ์เบอร์โทรศัพท์จริงที่ติดต่อได้ค่ะ"}

    return {"valid": True, "phone": digits, "reason": ""}





def has_complete_thai_address(addr: str) -> bool:

    s = str(addr or "").strip()

    if len(s) < 12:

        return False

    has_sub = bool(re.search(r"(?:ต\.|ตำบล|แขวง|sub-?district|tambon|khwaeng)\s*[ก-๙A-Za-z]{2,}", s, re.I))

    has_dist = bool(re.search(r"(?:อ\.|อำเภอ|เขต|district|amphoe|amphur|khet)\s*[ก-๙A-Za-z]{2,}", s, re.I))

    has_prov = bool(re.search(r"(?:จ\.|จังหวัด|province)\s*[ก-๙A-Za-z]{2,}|กรุงเทพ|กทม|bangkok|bkk", s, re.I))

    if has_sub and has_dist and has_prov:

        return True

    # Foreigner address in Thailand with 5-digit zip code

    has_zip = bool(re.search(r'\b([1-9]\d{4})\b', s))

    if has_zip and (has_prov or bool(re.search(r"bangkok|bkk|phuket|chiang\s*mai|pattaya|chonburi|samui|hua\s*hin|krabi", s, re.I))):

        if len(s) >= 18:

            return True

    return False





def insert_tambon_into_address(addr: str, tambon_name: str) -> str:

    s = str(addr or "").strip()

    clean_t = re.sub(r"^(?:ต\.|ตำบล|แขวง)\s*", "", str(tambon_name or "")).strip()

    if not clean_t:

        return s

    is_bkk = bool(re.search(r"กรุงเทพ|กทม|\b10\d{3}\b", s))

    t_prefix = f"แขวง{clean_t}" if is_bkk else f"ต.{clean_t}"

    if t_prefix in s or clean_t in s:

        if not re.search(r"(?:ต\.|ตำบล|แขวง)", s):

            return s.replace(clean_t, t_prefix, 1)

        return s

    m_dist = re.search(r"(?:อ\.|อำเภอ|เขต)\s*[ก-๙A-Za-z]+", s)

    if m_dist:

        idx = m_dist.start()

        return f"{s[:idx].strip()} {t_prefix} {s[idx:].strip()}".strip()

    m_zip = re.search(r"\b([1-9]\d{4})\b", s)

    if m_zip:

        idx = m_zip.start()

        return f"{s[:idx].strip()} {t_prefix} {s[idx:].strip()}".strip()

    return f"{s} {t_prefix}".strip()





def enrich_thai_address(raw_address: str) -> str:

    addr = normalize_thai_digits(str(raw_address or "")).strip()

    if not addr:

        return addr

    if has_complete_thai_address(addr):

        return addr



    zip_match = re.search(r"\b([1-9]\d{4})\b", addr)

    zip_code = zip_match.group(1) if zip_match else ""

    zip_info = lookup_thai_zip(zip_code) if zip_code else lookup_thai_area_by_name(addr)

    if zip_info and not zip_code:

        zip_code = zip_info["zip"]



    if zip_info:

        has_sub = bool(re.search(r"(?:ต\.|ตำบล|แขวง)", addr))

        has_dist = bool(re.search(r"(?:อ\.|อำเภอ|เขต)", addr))

        has_prov = bool(re.search(r"(?:จ\.|จังหวัด|กรุงเทพ|กทม)", addr))



        matched_tambon = ""

        if not has_sub and zip_info["tambons"]:

            if len(zip_info["tambons"]) == 1:

                matched_tambon = zip_info["tambons"][0]

            else:

                sorted_t = sorted(zip_info["tambons"], key=len, reverse=True)

                for cand in sorted_t:

                    if cand in addr:

                        is_part_of_amphoe = (cand == zip_info["amphoe"]) and bool(

                            re.search(r"(?:อ\.|อำเภอ|เขต)\s*" + re.escape(cand), addr)

                        )

                        if not is_part_of_amphoe:

                            matched_tambon = cand

                            break



        add_parts: list[str] = []

        if not has_sub and matched_tambon:

            t_label = f"แขวง{matched_tambon}" if zip_info["is_bkk"] else f"ต.{matched_tambon}"

            if matched_tambon in addr:

                addr = addr.replace(matched_tambon, t_label, 1)

            else:

                add_parts.append(t_label)

        if not has_dist and zip_info["amphoe"]:

            d_label = (

                zip_info["amphoe"]

                if zip_info["amphoe"].startswith("เขต")

                else (f"เขต{zip_info['amphoe']}" if zip_info["is_bkk"] else f"อ.{zip_info['amphoe']}")

            )

            if (

                zip_info["amphoe"] != matched_tambon

                and zip_info["amphoe"] in addr

                and not zip_info["is_bkk"]

                and f"ต.{zip_info['amphoe']}" not in addr

                and f"ตำบล{zip_info['amphoe']}" not in addr

            ):

                addr = addr.replace(zip_info["amphoe"], d_label, 1)

            else:

                add_parts.append(d_label)

        if not has_prov and zip_info["province"]:

            p_label = zip_info["province"] if zip_info["is_bkk"] else f"จ.{zip_info['province']}"

            if (

                zip_info["province"] != zip_info["amphoe"]

                and zip_info["province"] != matched_tambon

                and zip_info["province"] in addr

                and not zip_info["is_bkk"]

                and f"อ.{zip_info['province']}" not in addr

                and f"ต.{zip_info['province']}" not in addr

            ):

                addr = addr.replace(zip_info["province"], p_label, 1)

            else:

                add_parts.append(p_label)



        if add_parts:

            before_zip = re.sub(r"\s*\b" + re.escape(zip_code) + r"\b\s*", " ", addr).strip()

            addr = f"{before_zip} {' '.join(add_parts)} {zip_code}".strip()



    return addr





def build_incomplete_order_guidance(

    raw_text: str,

    saved_address: str = "",

    saved_phone: str = "",

    greeting: str = "สวัสดีค่ะคุณลูกค้า 🙏💕",

) -> tuple[str, list[dict[str, str]], dict[str, Any]]:

    """

    ตรวจสอบข้อความสั่งซื้อ/ที่อยู่ว่าขาดอะไรบ้าง (ตำบล/แขวง, อำเภอ/เขต, จังหวัด, เบอร์โทร 10 หลัก)

    คืนค่า (reply_text, quick_replies_for_fb, updated_state)

    """

    text = normalize_thai_digits(str(raw_text or "")).strip()

    phone_cand_m = re.search(r"0[2689]\d[\d\s-]{5,12}", text)

    cand_digits = re.sub(r"\D", "", phone_cand_m.group(0)) if phone_cand_m else ""

    phone_check = validate_thai_phone(cand_digits) if cand_digits else validate_thai_phone(saved_phone)

    valid_phone = phone_check["phone"] if phone_check["valid"] else (saved_phone if validate_thai_phone(saved_phone)["valid"] else "")



    text_no_phone = text.replace(phone_cand_m.group(0), "").strip() if phone_cand_m else text

    merged_addr = saved_address or ""



    # Check if the user just replied with a Tambon name for saved_address

    if merged_addr and not has_complete_thai_address(merged_addr):

        zip_m = re.search(r"\b([1-9]\d{4})\b", merged_addr)

        zip_info = lookup_thai_zip(zip_m.group(1)) if zip_m else None

        picked_t = ""

        t_pref_m = re.match(r"^(?:ต\.|ตำบล|แขวง)\s*([ก-๙A-Za-z0-9]+)", text_no_phone)

        if t_pref_m:

            picked_t = t_pref_m.group(1).strip()

        elif zip_info and zip_info["tambons"]:

            for ct in zip_info["tambons"]:

                if text_no_phone == ct or ct in text_no_phone:

                    picked_t = ct

                    break

        if picked_t:

            merged_addr = enrich_thai_address(insert_tambon_into_address(merged_addr, picked_t))

        elif len(text_no_phone) >= 6:

            merged_addr = enrich_thai_address(f"{merged_addr} {text_no_phone}".strip())

    elif len(text_no_phone) >= 4:

        merged_addr = enrich_thai_address(text_no_phone)



    addr_complete = has_complete_thai_address(merged_addr)

    phone_complete = bool(valid_phone and validate_thai_phone(valid_phone)["valid"])



    is_en_customer = any(w in text.lower() for w in ["hello", "please", "room", "soi", "road", "bangkok", "condo", "tel:", "phone:", "english", "order", "deliver", "set 1", "set 2", "set 3"]) or (len(re.findall(r"[a-zA-Z]", text)) > len(re.findall(r"[ก-๙]", text)) and len(text) > 8)



    missing_lines: list[str] = []

    quick_replies: list[dict[str, str]] = []



    if not addr_complete:

        zip_m = re.search(r"\b([1-9]\d{4})\b", merged_addr)

        zip_info = lookup_thai_zip(zip_m.group(1)) if zip_m else None

        if zip_info and zip_info["tambons"] and not re.search(r"(?:ต\.|ตำบล|แขวง)", merged_addr):

            t_prefix = "แขวง" if zip_info["is_bkk"] else "ต."

            d_prefix = "เขต" if zip_info["is_bkk"] else "อ."

            t_list_str = ", ".join(f"{t_prefix}{t}" for t in zip_info["tambons"])

            missing_lines.append(

                f"📌 ขาด **ตำบล/แขวง** (รหัส {zip_info['zip']} {d_prefix}{zip_info['amphoe']} จ.{zip_info['province']} มีตำบลดังนี้ค่ะ: {t_list_str})"

            )

            for t in zip_info["tambons"][:10]:

                label = f"{t_prefix}{t}"[:20]

                quick_replies.append({"content_type": "text", "title": label, "payload": label})

        else:

            missing_lines.append("📌 ขาด **ตำบล/แขวง + อำเภอ/เขต + จังหวัด** (หรือพิมพ์รหัสไปรษณีย์ 5 หลักเพิ่มได้เลยค่ะ)")



    if not phone_complete:

        reason = phone_check["reason"] if cand_digits else "ยังไม่ได้ระบุเบอร์โทรศัพท์ผู้รับ 10 หลัก"

        missing_lines.append(f"📞 เบอร์โทรศัพท์: **{reason}** (ตัวอย่าง: 089-xxx-xxxx)")



    if is_en_customer:

        missing_lines_en: list[str] = []

        if not addr_complete:

            missing_lines_en.append("📌 Delivery Address: Please provide Sub-district / District / Province / 5-digit Postal Code (e.g. Sukhumvit Rd, Khlong Toei, Bangkok 10110)")

        if not phone_complete:

            missing_lines_en.append("📞 Phone Number: Please provide a valid 10-digit Thailand mobile phone number (e.g. 081-xxx-xxxx)")

        reply = (

            "Hello! Thank you for ordering Pa Khem Sun-Dried Gourami Fish 🙏🐟\n"

            "📋 We have recorded your information:\n"

            + (f"🏠 Address: {merged_addr}\n" if merged_addr else "")

            + (f"📞 Phone: {valid_phone}\n" if valid_phone else "")

            + "━━━━━━━━━━━━━━━━━━\n"

            + "⚠️ To ensure accurate courier delivery, please provide the following missing details:\n"

            + "\n".join(missing_lines_en)

            + "\n\n👉 Please reply with the missing details in this chat! 😊"

        )

    else:

        reply = (

            f"{greeting}\n"

            f"📋 ป้าเข็มบันทึกข้อมูลเบื้องต้นไว้ให้แล้วจ้ะ:\n"

            + (f"🏠 ที่อยู่: {merged_addr}\n" if merged_addr else "")

            + (f"📞 เบอร์โทร: {valid_phone}\n" if valid_phone else "")

            + "━━━━━━━━━━━━━━━━━━\n"

            + "⚠️ เพื่อให้ขนส่งจัดส่งถึงหน้าบ้านไม่ตีกลับ รบกวนแจ้งเพิ่มอีกนิดเดียวนะจ๊ะ:\n"

            + "\n".join(missing_lines)

            + "\n\n"

            + ("👇 กดเลือกปุ่มตำบลด้านล่าง หรือพิมพ์แจ้งในแชทได้เลยจ้า 😊" if quick_replies else "👇 พิมพ์ข้อมูลที่ขาดส่งมาในแชทนี้ได้เลยจ้า 😊")

        )



    state = {

        "saved_address": merged_addr,

        "saved_phone": valid_phone,

        "addr_complete": addr_complete,

        "phone_complete": phone_complete,

    }

    return reply, quick_replies, state

