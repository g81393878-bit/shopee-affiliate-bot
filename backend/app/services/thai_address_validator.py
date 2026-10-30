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


def get_thai_zip_db() -> dict[str, dict[str, Any]]:
    global _THAI_ZIP_DB
    if _THAI_ZIP_DB is not None:
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
                    return _THAI_ZIP_DB
            except Exception:
                pass
    _THAI_ZIP_DB = {}
    return _THAI_ZIP_DB


def lookup_thai_zip(zip_code: str) -> dict[str, Any] | None:
    clean_zip = re.sub(r"\D", "", str(zip_code or ""))
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
    return {
        "zip": clean_zip,
        "amphoe": str(entry.get("a", "")).strip(),
        "province": str(entry.get("p", "")).strip(),
        "tambons": tambons,
        "is_bkk": is_bkk,
    }


def validate_thai_phone(raw_phone: str) -> dict[str, Any]:
    digits = re.sub(r"\D", "", str(raw_phone or ""))
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
    has_sub = bool(re.search(r"(?:ต\.|ตำบล|แขวง)\s*[ก-๙A-Za-z]{2,}", s))
    has_dist = bool(re.search(r"(?:อ\.|อำเภอ|เขต)\s*[ก-๙A-Za-z]{2,}", s))
    has_prov = bool(re.search(r"(?:จ\.|จังหวัด)\s*[ก-๙A-Za-z]{2,}|กรุงเทพ|กทม", s))
    return has_sub and has_dist and has_prov


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
    addr = str(raw_address or "").strip()
    if not addr:
        return addr
    if has_complete_thai_address(addr):
        return addr

    zip_match = re.search(r"\b([1-9]\d{4})\b", addr)
    zip_code = zip_match.group(1) if zip_match else ""
    zip_info = lookup_thai_zip(zip_code) if zip_code else None

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
    text = str(raw_text or "").strip()
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
