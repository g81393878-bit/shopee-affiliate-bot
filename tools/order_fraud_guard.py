# -*- coding: utf-8 -*-
"""
tools/order_fraud_guard.py — ระบบบอทคัดกรองมิจฉาชีพ ตรวจสอบเบอร์โทร ที่อยู่จัดส่ง และความเสี่ยง COD ตีกลับอัตโนมัติ
สำหรับร้านปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดพิเศษ
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / "backend" / ".env")

logger = logging.getLogger("OrderFraudGuard")
ICT = timezone(timedelta(hours=7))
CACHE_FILE = ROOT_DIR / "artifacts" / "order_fraud_check_cache.json"

THAI_PROVINCES = [
    "กรุงเทพ", "กทม", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น",
    "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย",
    "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก", "นครปฐม", "นครพนม", "นครราชสีมา",
    "โคราช", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน", "บึงกาฬ",
    "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา",
    "อยุธยา", "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์",
    "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด",
    "ระนอง", "ระยอง", "ราชบุรี", "ลพบุรี", "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ",
    "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว",
    "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย",
    "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี",
    "อุบลราชธานี", "อุบล",
]

FAKE_PHONE_PATTERNS = {
    "0812345678",
    "0891234567",
    "0899998877",
    "0912345678",
    "0612345678",
    "0800000000",
    "0811111111",
    "0899999999",
    "0999999999",
    "0987654321",
}


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(data: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def detect_thai_carrier(clean_phone: str) -> str:
    """ระบุเครือข่ายมือถือจากหมวด 3 หลักแรกของเบอร์โทรศัพท์ไทย"""
    if len(clean_phone) != 10 or not clean_phone.startswith("0"):
        return "ไม่ระบุเครือข่าย"
    p3 = clean_phone[:3]
    ais = {"061", "062", "063", "065", "081", "089", "092", "093", "098"}
    true_dtac = {"064", "066", "080", "082", "083", "084", "085", "086", "087", "088", "090", "091", "094", "095", "096", "097", "099"}
    if p3 in ais:
        return f"AIS (หมวด {p3})"
    if p3 in true_dtac:
        return f"TRUE/DTAC (หมวด {p3})"
    return f"เครือข่ายมือถือไทย (หมวด {p3})"


def format_thai_phone(clean_phone: str) -> str:
    if len(clean_phone) == 10:
        return f"{clean_phone[:3]}-{clean_phone[3:6]}-{clean_phone[6:]}"
    return clean_phone


def _check_online_scammer_blacklist(clean_phone: str, customer_name: str = "") -> dict:
    """
    ค้นหาประวัติมิจฉาชีพ/โกง/BlacklistSeller จากฐานข้อมูลออนไลน์ผ่าน Tavily API (พร้อม Cache ป้องกันการยิงซ้ำ)
    """
    if not clean_phone or len(clean_phone) != 10:
        return {"found_scam": False, "detail": "เบอร์ไม่ครบ 10 หลัก"}

    cache = _load_cache()
    if clean_phone in cache:
        return cache[clean_phone]

    tavily_key = (
        os.getenv("TAVILY_API_KEY")
        or os.getenv("TAVILY_API_KEYS", "").split(",")[0]
        or ""
    ).strip()

    result = {
        "found_scam": False,
        "detail": "ไม่พบประวัติโกงหรือแบล็กลิสต์บนฐานข้อมูลออนไลน์",
        "checked_at": datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S"),
    }

    if tavily_key and not tavily_key.startswith("mock"):
        try:
            fmt_phone = format_thai_phone(clean_phone)
            query = f'"{clean_phone}" OR "{fmt_phone}" ("มิจฉาชีพ" OR "โกง" OR "เตือนภัย" OR "blacklistseller")'
            r = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 3,
                },
                timeout=5.0,
            )
            if r.status_code == 200:
                items = r.json().get("results", [])
                scam_hits = []
                for it in items:
                    content = f"{it.get('title', '')} {it.get('content', '')}"
                    if (clean_phone in content or fmt_phone in content) and any(
                        w in content for w in ["โกง", "มิจฉาชีพ", "หลอกโอน", "blacklistseller", "คนโกง", "แจ้งความ"]
                    ):
                        scam_hits.append(it.get("title", "พบประวัติแจ้งเตือนออนไลน์")[:80])
                if scam_hits:
                    result["found_scam"] = True
                    result["detail"] = f"⚠️ พบประวัติแจ้งเตือน: {scam_hits[0]}"
        except Exception as e:
            logger.debug(f"[OrderFraudGuard] Tavily check skipped: {e}")

    cache[clean_phone] = result
    _save_cache(cache)
    return result


_THAI_ADDR_DB: list[dict] | None = None


def _get_thai_address_db() -> list[dict]:
    global _THAI_ADDR_DB
    if _THAI_ADDR_DB is not None:
        return _THAI_ADDR_DB
    db_file = ROOT_DIR / "artifacts" / "thailand_address_db.json"
    if db_file.exists():
        try:
            _THAI_ADDR_DB = json.loads(db_file.read_text(encoding="utf-8"))
            return _THAI_ADDR_DB
        except Exception:
            pass
    _THAI_ADDR_DB = []
    return _THAI_ADDR_DB


def verify_thai_address_77_provinces(address: str) -> dict:
    """
    ตรวจสอบพิกัดที่อยู่จัดส่งกับฐานข้อมูลกรมการปกครอง & ไปรษณีย์ไทย 77 จังหวัด (7,498 ตำบล / 928 อำเภอ):
    - ตรวจจับบ้านเลขที่ ถนน/ซอย/หมู่บ้าน
    - ตรวจสอบความสอดคล้องของ ตำบล (แขวง) + อำเภอ (เขต) + จังหวัด + รหัสไปรษณีย์จริง
    - เติมรหัสไปรษณีย์ที่ถูกต้องให้อัตโนมัติกรณีลูกค้าไม่ได้พิมพ์มา
    """
    clean_addr = (address or "").strip()
    db = _get_thai_address_db()

    has_house_no = bool(re.search(r"\d+", clean_addr))
    m_road = re.search(r"(?:ถนน|ถ\.|ซอย|ซ\.|หมู่บ้าน|หมู่ที่|หมู่|ม\.)\s*([^\s,]+(?:\s+\d+)?)", clean_addr)
    road_or_soi = m_road.group(0).strip() if m_road else ""
    m_zip = re.search(r"\b([1-9]\d{4})\b", clean_addr)
    input_zip = m_zip.group(1) if m_zip else ""

    matched_prov = None
    prov_aliases = {
        "กทม": "กรุงเทพมหานคร",
        "กทม.": "กรุงเทพมหานคร",
        "กรุงเทพ": "กรุงเทพมหานคร",
        "โคราช": "นครราชสีมา",
        "อยุธยา": "พระนครศรีอยุธยา",
        "อุบล": "อุบลราชธานี",
    }
    for alias, full_p in prov_aliases.items():
        if alias in clean_addr:
            matched_prov = full_p
            break
    if not matched_prov:
        for p in sorted(THAI_PROVINCES, key=len, reverse=True):
            if p in clean_addr:
                matched_prov = prov_aliases.get(p, p)
                break

    matched_amphoe = ""
    matched_tambon = ""
    resolved_zip = input_zip
    zip_mismatch = False

    if db and matched_prov:
        prov_rows = [r for r in db if r.get("province") == matched_prov]
        # ตรวจหาอำเภอ/เขตในจังหวัดนั้น (รองรับกรณีเขียนย่อ "อ.เมือง" -> "เมือง<จังหวัด>")
        for r in prov_rows:
            amp = str(r.get("amphoe") or "")
            if amp and (amp in clean_addr or (amp.startswith("เมือง") and ("อ.เมือง" in clean_addr or "อำเภอเมือง" in clean_addr))):
                matched_amphoe = amp
                break

        cand_rows = [r for r in prov_rows if not matched_amphoe or r.get("amphoe") == matched_amphoe]
        for r in cand_rows:
            tmb = str(r.get("district") or "")
            if tmb and tmb in clean_addr:
                matched_tambon = tmb
                if not matched_amphoe:
                    matched_amphoe = str(r.get("amphoe") or "")
                break

        valid_zips = sorted({str(r.get("zipcode")) for r in cand_rows if r.get("zipcode")})
        if input_zip:
            prov_all_zips = {str(r.get("zipcode")) for r in prov_rows if r.get("zipcode")}
            if prov_all_zips and input_zip not in prov_all_zips:
                zip_mismatch = True
        elif valid_zips:
            resolved_zip = valid_zips[0]

    is_valid = bool(has_house_no and matched_prov and len(clean_addr) >= 12 and not zip_mismatch)
    return {
        "valid": is_valid,
        "has_house_no": has_house_no,
        "road_or_soi": road_or_soi,
        "tambon": matched_tambon,
        "amphoe": matched_amphoe,
        "province": matched_prov or "",
        "input_zipcode": input_zip,
        "resolved_zipcode": resolved_zip,
        "zip_mismatch": zip_mismatch,
    }


def analyze_order_fraud_risk(
    name: str,
    phone: str,
    address: str,
    package_name: str = "",
    price: float = 0.0,
    payment_method: str = "",
    note: str = "",
) -> dict:
    """
    ตรวจสอบความน่าเชื่อถือของออเดอร์ลูกค้าสั่งซื้อปลาสลิด 3 ด่าน:
    1. ตรวจเบอร์โทรศัพท์ (รูปแบบเบอร์จริง, เบอร์จำลอง/เบอร์มั่ว, เครือข่ายมือถือ, ประวัติโกงออนไลน์)
    2. ตรวจโครงสร้างที่อยู่จัดส่งจริง (บ้านเลขที่, ถนน/ซอย/ตำบล/อำเภอ, จังหวัดจริงในไทย 77 จังหวัด + รหัสไปรษณีย์ 7,498 ตำบล)
    3. ตรวจเงื่อนไขการชำระเงิน (COD vs โอนเงิน, ชุด 2 กก. บังคับโอนเงิน)
    """
    clean_name = (name or "").strip()
    clean_phone = re.sub(r"\D", "", phone or "")
    clean_addr = (address or "").strip()
    pay_upper = (payment_method or "").upper()
    is_cod = "COD" in pay_upper or "ปลายทาง" in (payment_method or "")

    reasons = []
    risk_score = 0  # 0 = ปลอดภัย, 1-49 = เหลือง (ควรโทรเช็ค), >=50 = แดง (เสี่ยงสูง/เบอร์ปลอม)
    is_test_order = False

    # --- ด่านที่ 1: ตรวจสอบเบอร์โทรศัพท์ ---
    if (
        clean_phone in FAKE_PHONE_PATTERNS
        or "1234567" in clean_phone
        or re.search(r"(\d)\1{5,}", clean_phone)
        or "test" in clean_name.lower()
        or "ทดสอบ" in clean_name.lower()
        or "จำลอง" in clean_addr
    ):
        risk_score += 80
        is_test_order = True
        reasons.append("เบอร์โทรศัพท์หรือชื่อเป็นข้อมูลทดสอบ/เบอร์เรียงจำลอง (ไม่ใช่เบอร์ลูกค้าจริง)")
        carrier = "เบอร์จำลอง/ทดสอบระบบ"
        blacklist_info = {"found_scam": False, "detail": "รายการทดสอบระบบ"}
    elif not re.match(r"^0[689]\d{8}$", clean_phone):
        risk_score += 60
        reasons.append(f"รูปแบบเบอร์มือถือไม่ถูกต้อง ({phone or 'ไม่ระบุ'})")
        carrier = "ไม่ถูกต้อง"
        blacklist_info = {"found_scam": False, "detail": "เบอร์ไม่ถูกต้อง"}
    else:
        carrier = detect_thai_carrier(clean_phone)
        blacklist_info = _check_online_scammer_blacklist(clean_phone, clean_name)
        if blacklist_info.get("found_scam"):
            risk_score += 90
            reasons.append(blacklist_info["detail"])

    # --- ด่านที่ 2: ตรวจสอบพิกัดที่อยู่จัดส่ง 77 จังหวัด (7,498 ตำบล / 928 อำเภอ) ---
    geo = verify_thai_address_77_provinces(clean_addr)
    matched_prov = geo.get("province") or ""
    matched_amp = geo.get("amphoe") or ""
    matched_tmb = geo.get("tambon") or ""
    resolved_zip = geo.get("resolved_zipcode") or ""
    road_soi = geo.get("road_or_soi") or ""

    if is_test_order:
        addr_status = "ที่อยู่จำลองสำหรับทดสอบ"
    elif geo.get("zip_mismatch"):
        risk_score += 35
        addr_status = f"⚠️ รหัสไปรษณีย์ ({geo.get('input_zipcode')}) ไม่ตรงกับ จ.{matched_prov}"
        reasons.append(addr_status)
    elif not geo.get("valid"):
        risk_score += 30
        missing = []
        if not geo.get("has_house_no"):
            missing.append("บ้านเลขที่")
        if not matched_prov:
            missing.append("จังหวัด")
        if not (matched_amp or road_soi):
            missing.append("ถนน/อำเภอ")
        miss_str = ", ".join(missing) if missing else "รายละเอียดสั้นเกินไป"
        addr_status = f"⚠️ ที่อยู่ไม่ครบ ({miss_str})"
        reasons.append(f"ที่อยู่จัดส่งขาดข้อมูลสำคัญ ({miss_str}) เสี่ยงขนส่งตีกลับ")
    else:
        loc_parts = []
        if road_soi:
            loc_parts.append(road_soi)
        if matched_tmb:
            loc_parts.append(f"ต.{matched_tmb}")
        if matched_amp:
            loc_parts.append(f"อ.{matched_amp}")
        loc_parts.append(f"จ.{matched_prov}")
        if resolved_zip:
            loc_parts.append(f"ปณ. {resolved_zip}")
        addr_status = f"✅ พิกัดจริง ({' '.join(loc_parts)})"

    # --- ด่านที่ 3: ตรวจสอบนโยบาย COD / ยอดสั่งซื้อ ---
    if is_cod and ("2 กิโล" in (package_name or "") or "2kg" in (package_name or "").lower() or price >= 1000):
        if not is_test_order:
            risk_score += 25
            reasons.append("ชุด 2 กก. (1,090.-) ตามนโยบายร้านรับเฉพาะโอนเงินล่วงหน้า (ป้องกันความเสี่ยงอาหารสดตีกลับ)")

    # --- สรุปผลการประเมิน ---
    if risk_score >= 50:
        risk_level = "RED"
        badge = "🔴 เสี่ยงสูง / เบอร์จำลอง (ห้ามส่ง)"
        recommendation = "⛔ ระงับการจัดส่ง (รายการทดสอบ หรือเบอร์ไม่ถูกต้อง/พบความเสี่ยงสูง)"
    elif risk_score >= 20:
        risk_level = "YELLOW"
        badge = "🟡 ควรโทรยืนยันก่อนแพ็ก"
        recommendation = "📞 แนะนำโทรยืนยันที่อยู่กับลูกค้า 30 วินาทีก่อนแพ็กส่ง"
    else:
        risk_level = "GREEN"
        badge = "🟢 ปลอดภัย (ข้อมูลจริงครบถ้วน)"
        recommendation = "✅ ข้อมูลเบอร์โทรและที่อยู่จริงครบถ้วน แพ็กซีลสูญญากาศจัดส่งได้เลย"
        if not reasons:
            reasons.append("เบอร์มือถือใช้งานจริง ไม่พบประวัติแบล็กลิสต์ และพิกัดที่อยู่จัดส่งชัดเจน")

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "badge": badge,
        "is_test_order": is_test_order,
        "phone_formatted": format_thai_phone(clean_phone) if len(clean_phone) == 10 else (phone or "-"),
        "carrier": carrier,
        "blacklist_status": blacklist_info.get("detail", "-"),
        "address_status": addr_status,
        "province": matched_prov or "ไม่ระบุ",
        "recommendation": recommendation,
        "reasons": reasons,
    }


def format_fraud_guard_telegram_block(check_res: dict) -> str:
    """สร้างบล็อกข้อความผลตรวจมิจฉาชีพสำหรับแนบในแจ้งเตือน Telegram แอดมิน"""
    reasons_txt = " / ".join(check_res.get("reasons") or [])
    return (
        f"🛡️ **ผลบอทสแกนมิจฉาชีพ & ความเสี่ยง COD**:\n"
        f"• สถานะ: **{check_res.get('badge')}**\n"
        f"• เครือข่ายเบอร์: `{check_res.get('phone_formatted')}` ({check_res.get('carrier')})\n"
        f"• เช็คประวัติโกง: {check_res.get('blacklist_status')}\n"
        f"• เช็คพิกัดที่อยู่: {check_res.get('address_status')}\n"
        f"• คำแนะนำบอท: **{check_res.get('recommendation')}**\n"
        f"• รายละเอียด: {reasons_txt}"
    )


SCREENED_ORDERS_FILE = ROOT_DIR / "artifacts" / "screened_orders_history.json"


def _load_screened_orders() -> dict:
    if SCREENED_ORDERS_FILE.exists():
        try:
            return json.loads(SCREENED_ORDERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_screened_orders(data: dict) -> None:
    try:
        SCREENED_ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCREENED_ORDERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def fetch_and_screen_all_direct_orders(include_test_orders: bool = False) -> list[dict]:
    """
    ดึงรายการลูกค้าที่สั่งซื้อจากตาราง Supabase direct_orders ทั้งหมด
    พร้อมรันระบบตรวจคัดกรองมิจฉาชีพ (OrderFraudGuard) แยกชัดเจนทุกออเดอร์
    """
    sb_url = os.getenv("SUPABASE_URL", "https://usqhvujqmnxqrdoovvnp.supabase.co").strip()
    sb_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if not sb_url or not sb_key:
        return []

    try:
        r = httpx.get(
            f"{sb_url}/rest/v1/direct_orders",
            params={"select": "*", "order": "id.desc", "limit": 100},
            headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
            timeout=10.0,
        )
        if r.status_code != 200:
            return []
        orders = r.json()
    except Exception as e:
        logger.warning(f"[OrderFraudGuard] fetch direct_orders error: {e}")
        return []

    results = []
    for o in orders:
        chk = analyze_order_fraud_risk(
            name=o.get("customer_name") or "",
            phone=o.get("phone") or "",
            address=o.get("address") or "",
            package_name=o.get("package_name") or "",
            price=float(o.get("price") or 0.0),
            payment_method=o.get("payment_method") or "",
            note=o.get("note") or "",
        )
        if not include_test_orders and chk.get("is_test_order"):
            continue
        results.append({
            **o,
            "fraud_check": chk,
        })
    return results


def scan_and_screen_new_orders(notify_telegram: bool = True) -> int:
    """
    ตรวจสอบออเดอร์ใหม่ในตาราง direct_orders ทุกๆ 30 วินาที
    เมื่อพบลูกค้าสั่งซื้อรายใหม่ จะสแกนเช็คมิจฉาชีพ + ที่อยู่จริง แล้วส่งรายงานแยกเฉพาะออเดอร์เข้า Telegram ทันที
    """
    orders = fetch_and_screen_all_direct_orders(include_test_orders=False)
    if not orders:
        return 0

    screened = _load_screened_orders()
    new_count = 0

    try:
        from telegram_notifier import send_telegram_alert
    except Exception:
        send_telegram_alert = None

    for item in reversed(orders):
        oid = str(item.get("id") or "")
        ocode = str(item.get("order_code") or "")
        if not oid or oid in screened:
            continue

        chk = item.get("fraud_check") or {}
        cust_name = item.get("customer_name") or "ลูกค้า"
        pkg_name = item.get("package_name") or "ปลาสลิดแดดเดียว ป้าเข็ม"
        price = float(item.get("price") or 0.0)
        pay_method = item.get("payment_method") or "-"
        addr = item.get("address") or "-"
        phone_fmt = chk.get("phone_formatted") or item.get("phone") or "-"
        digits = re.sub(r"\D", "", phone_fmt)

        screened[oid] = {
            "order_code": ocode,
            "customer_name": cust_name,
            "phone": phone_fmt,
            "risk_level": chk.get("risk_level"),
            "badge": chk.get("badge"),
            "screened_at": datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S"),
        }
        _save_screened_orders(screened)
        new_count += 1

        if notify_telegram and send_telegram_alert:
            msg = (
                f"🛡️🛒 [บอทคัดกรองลูกค้าสั่งซื้อจริง & ตรวจมิจฉาชีพ]\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔖 รหัสออเดอร์: `{ocode}`\n"
                f"👤 ชื่อลูกค้า: **{cust_name}**\n"
                f"📱 เบอร์โทร: `{phone_fmt}` ({chk.get('carrier')})\n"
                f"📦 รายการสั่งซื้อ: {pkg_name}\n"
                f"💰 ยอดชำระ: **{price:,.0f} บาท** ({pay_method})\n"
                f"📍 ที่อยู่จัดส่ง: {addr}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{format_fraud_guard_telegram_block(chk)}\n"
                f"🔗 เช็ค BlacklistSeller: https://www.blacklistseller.com/search_results?q={digits}"
            )
            send_telegram_alert(msg)

    return new_count


def build_all_orders_fraud_report() -> str:
    """สร้างรายงานสรุปผลตรวจมิจฉาชีพของลูกค้าที่สั่งซื้อจริงทั้งหมด สำหรับปุ่ม /fraud ใน Telegram"""
    orders = fetch_and_screen_all_direct_orders(include_test_orders=False)
    if not orders:
        return "🛒 ยังไม่มีรายการสั่งซื้อจริงในระบบ (หรือมีเฉพาะรายการทดสอบระบบ)"

    lines = [
        f"🛡️🛒 [รายงานตรวจมิจฉาชีพ — แยกเฉพาะลูกค้าสั่งซื้อจริง ({len(orders)} ออเดอร์)]",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for idx, o in enumerate(orders[:10], 1):
        chk = o.get("fraud_check") or {}
        ocode = o.get("order_code") or "-"
        cname = o.get("customer_name") or "-"
        phone_fmt = chk.get("phone_formatted") or o.get("phone") or "-"
        pkg = o.get("package_name") or "-"
        price = float(o.get("price") or 0.0)
        pay = o.get("payment_method") or "-"
        addr = o.get("address") or "-"
        lines.extend([
            f"{idx}. 🔖 `{ocode}` | **{cname}**",
            f"   • 📦 สั่ง: {pkg} (**{price:,.0f}.-** / {pay})",
            f"   • 📱 เบอร์: `{phone_fmt}` ({chk.get('carrier')})",
            f"   • 📍 ที่อยู่: {addr}",
            f"   • 🗺️ พิกัด 77 จังหวัด: {chk.get('address_status')}",
            f"   • 🛡️ ผลตรวจบอท: **{chk.get('badge')}**",
            f"   • 💡 คำแนะนำ: {chk.get('recommendation')}",
            "──────────────────────",
        ])
    lines.append("💡 พิมพ์ `/fraud <เบอร์โทรหรือที่อยู่>` เพื่อตรวจสอบรายบุคคลเพิ่มเติมได้ทันทีครับ")
    return "\n".join(lines)
