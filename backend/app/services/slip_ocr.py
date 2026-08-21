"""OCR รูปสลิปโอนเงิน (Groq vision) — ดึงยอดเงิน + เลขอ้างอิง แล้วเทียบกับยอดคาด

Groq รองรับภาพ (vision) ผ่าน OpenAI-compat API (base64 data URL ใน content)
ส่งรูปสลิป + prompt สั่งคืน JSON {"amount": ..., "ref_no": ...} — ถ้าไม่มี
GROQ_API_KEY / เป็น mock / อ่านล้ม คืนค่าว่าง (best-effort ไม่บล็อก flow รับสลิป)

ใช้ groq_clients() + call_with_backoff ตาม convention ของ llm_clients.py
(หมุนเวียนหลาย key + failover + retry 429/5xx)
"""

import base64
import json
import logging
import re
from typing import Optional, Tuple

from app.config import settings
from app.services.llm_clients import call_with_backoff, groq_clients

logger = logging.getLogger(__name__)

# Groq vision model — ใช้ SLIP_OCR_MODEL ถ้าตั้ง env ไว้ (override ได้)
# (llama-3.2-11b-vision-preview ถูก decommission แล้ว 16/08/26 — เหลือ qwen3.6-27b ที่รับภาพได้)
_SLIP_OCR_MODEL = "qwen/qwen3.6-27b"

_SLIP_OCR_PROMPT = (
    "อ่านรูปสลิปโอนเงินธนาคารไทยนี้ แล้วตอบเป็น JSON เท่านั้น ไม่มีข้อความอื่น:\n"
    '{"amount": "ยอดเงินที่โอน เป็นตัวเลขเช่น 490.00", "ref_no": "เลขที่อ้างอิง/Ref No (ถ้าไม่มีให้คืนค่าว่าง "")"}\n'
    "ถ้าอ่านไม่ออก ให้คืนค่าว่างทั้งสองช่อง"
)


def extract_slip_info(image_bytes: bytes, content_type: str = "image/jpeg") -> dict:
    """ดึง {"amount": str|None, "ref_no": str|None} จากรูปสลิปด้วย Groq vision.

    ไม่มี GROQ_API_KEY / เป็น mock / อ่านล้ม → {"amount": None, "ref_no": None}
    """
    result = {"amount": None, "ref_no": None}
    clients = groq_clients()  # ตัด mock key อัตโนมัติ — ว่าง = ปิด OCR
    if not image_bytes or not clients:
        return result
    try:
        data_url = "data:%s;base64,%s" % (content_type or "image/jpeg",
                                          base64.b64encode(image_bytes).decode("ascii"))
        last_err = None
        for client in clients:
            try:
                response = call_with_backoff(
                    lambda: client.chat.completions.create(
                        model=getattr(settings, "SLIP_OCR_MODEL", "") or _SLIP_OCR_MODEL,
                        messages=[
                            {"role": "user", "content": [
                                {"type": "text", "text": _SLIP_OCR_PROMPT},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ]},
                        ],
                    ),
                    circuit_key=client.api_key,
                )
                data = _parse_json(response.choices[0].message.content)
                if isinstance(data, dict):
                    result["amount"] = clean_amount(data.get("amount"))
                    result["ref_no"] = clean_ref(data.get("ref_no") or data.get("ref")
                                                 or data.get("reference_no"))
                return result
            except Exception as e:
                last_err = e
                logger.warning(f"Groq slip OCR key {client.api_key[:8]}... failed: {e} — ลอง key ถัดไป")
        logger.warning(f"slip OCR failed with all Groq keys: {last_err}")
    except Exception as e:
        logger.warning(f"slip OCR failed: {e}")
    return result


def _parse_json(text) -> Optional[dict]:
    """parse JSON จาก response — เผื่อ model คืนมาพร้อม markdown fence/ข้อความเกิน"""
    if not text:
        return None
    text = str(text).strip()
    # ตัด <think>...</think> (qwen3.6 เป็น reasoning model คืนบล็อกคิดมาด้วย — ไม่งั้นดักด้วย regex { } ไม่เจอ)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    # strip ```json ... ``` fence
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (TypeError, ValueError):
            pass
    # เก็บเฉพาะบล็อก { ... } แรก
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (TypeError, ValueError):
            pass
    return None


def clean_amount(value) -> Optional[str]:
    """'490.00' / '1,990 บาท' / '490' → '490.00'/'1990'/'490'; ไม่อ่าน → None"""
    if not value:
        return None
    text = str(value).replace(",", "").strip()
    m = re.search(r"\d+(?:\.\d+)?", text)
    return m.group() if m else None


def clean_ref(value) -> Optional[str]:
    """เลขอ้างอิง/Ref No — ตัดช่องว่าง; ว่าง → None"""
    if not value:
        return None
    text = str(value).strip()
    return text or None


def parse_amount(text) -> Optional[float]:
    """'490.00' / '490 บาท' / '1,990.00' → float; ไม่อ่าน → None"""
    cleaned = clean_amount(text)
    if cleaned is None:
        return None
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def parse_amount_range(text) -> Optional[Tuple[float, float]]:
    """'490 บาท' → (490.0, 490.0); '7,500–12,500 บาท' → (7500.0, 12500.0)"""
    if not text:
        return None
    nums = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    vals = []
    for n in nums:
        try:
            vals.append(float(n.replace(",", "")))
        except (TypeError, ValueError):
            continue
    if not vals:
        return None
    return min(vals), max(vals)


def amount_matches(ocr_text, expected_text) -> bool:
    """ยอดจากสลิปอยู่ในช่วงยอดคาดไหม (fixed = ต้องเท่ากัน, range = อยู่ในช่วง).

    อ่านยอดไม่ได้ (None) → False = ถือว่า "รอเช็ค" ไม่ใช่ "ตรง"
    """
    ocr = parse_amount(ocr_text)
    rng = parse_amount_range(expected_text)
    if ocr is None or rng is None:
        return False
    lo, hi = rng
    return lo <= ocr <= hi