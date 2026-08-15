"""
LLM client helpers — รองรับ Groq + Anthropic หลาย API key พร้อมสลับใช้งานอัตโนมัติ.

วิธีตั้งค่า: ใส่ key หลายตัวคั่นด้วยคอมม่าใน GROQ_API_KEY / ANTHROPIC_API_KEY
    GROQ_API_KEY=gsk_aaa...,gsk_bbb...,gsk_ccc...
    ANTHROPIC_API_KEY=sk-ant-aaa...,sk-ant-bbb...

การทำงาน:
  - groq_clients() / anthropic_clients() หมุนเวียนลำดับ key ทุกครั้งที่เรียก (กระจายโหลด)
  - ผู้เรียกวนใช้ clients ทุกตัวตามลำดับ — ตัวไหนล้ม/โดน rate limit (429)
    ก็ข้ามไปตัวถัดไป (failover) จนกว่าจะสำเร็จ
  - Anthropic ใช้ OpenAI-compat endpoint (https://api.anthropic.com/v1/) —
    ไม่ต้องติดตั้ง anthropic SDK เพิ่ม; ข้อจำกัด: response_format ถูก ignore
    (ต้องสั่งให้ model คืน JSON ล้วนใน prompt เอง)

กัน Rate Limit 429 (เจอจริงตอนเรดาร์ยิงวิเคราะห์หลายโพสต์ติดกัน):
  - throttle_llm_request() จำกัด RPM process-wide (LLM_RATE_LIMIT_RPM)
  - call_with_backoff() retry แบบ exponential backoff + เคารพ Retry-After
"""

import logging
import threading
import time
from typing import Any, Optional

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/"

_lock = threading.Lock()
_start_index = 0

# --- Rate limiter state (process-wide — ทุก caller ที่ใช้ call_with_backoff แชร์กัน) ---
_rate_lock = threading.Lock()
_last_request_ts = 0.0

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_ERROR_NAMES = (
    "ConnectionError", "Timeout", "APITimeout",
    "RateLimitError", "InternalServerError",
    # google-generativeai transient/rate-limit errors
    "ResourceExhausted", "ServiceUnavailable", "DeadlineExceeded",
)


def groq_keys() -> list:
    """รายการ Groq keys จาก GROQ_API_KEY (รองรับหลายตัวคั่นด้วย ,) — ตัด mock/ซ้ำ"""
    raw = (settings.GROQ_API_KEY or "").strip()
    seen, keys = set(), []
    for k in raw.split(","):
        k = k.strip()
        if k and "mock" not in k.lower() and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def _rotate(keys: list) -> list:
    """เรียง keys แบบหมุนเวียน (call ถัดไปเริ่มที่ key ถัดไป — กระจายโหลด)"""
    if not keys:
        return []
    global _start_index
    with _lock:
        rot = _start_index % len(keys)
        _start_index += 1
    return keys[rot:] + keys[:rot]


def groq_clients() -> list:
    """OpenAI clients ของทุก Groq keys เรียงแบบหมุนเวียน (call ถัดไปเริ่มที่ key ถัดไป)"""
    keys = groq_keys()
    if not keys:
        return []
    return [OpenAI(api_key=k, base_url=GROQ_BASE_URL) for k in _rotate(keys)]


def anthropic_keys() -> list:
    """รายการ Anthropic keys จาก ANTHROPIC_API_KEY (รองรับหลายตัวคั่นด้วย ,) — ตัด mock/ซ้ำ"""
    raw = (settings.ANTHROPIC_API_KEY or "").strip()
    seen, keys = set(), []
    for k in raw.split(","):
        k = k.strip()
        if k and "mock" not in k.lower() and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def anthropic_clients() -> list:
    """OpenAI clients ของทุก Anthropic keys เรียงแบบหมุนเวียน (ผ่าน OpenAI-compat endpoint)"""
    keys = anthropic_keys()
    if not keys:
        return []
    return [OpenAI(api_key=k, base_url=ANTHROPIC_BASE_URL) for k in _rotate(keys)]


# ---------------------------------------------------------------------------
# Rate limiting + retry (กัน 429 เมื่อยิง LLM หลาย request ติดกัน)
# ---------------------------------------------------------------------------

def _min_interval_seconds() -> float:
    """ระยะห่างขั้นต่ำระหว่าง LLM call (วินาที) คำนวณจาก LLM_RATE_LIMIT_RPM"""
    rpm = int(getattr(settings, "LLM_RATE_LIMIT_RPM", 0) or 0)
    if rpm <= 0:
        return 0.0
    return 60.0 / rpm


def throttle_llm_request() -> None:
    """จำกัดอัตราการยิง LLM (RPM) แบบ process-wide — กัน 429 ตั้งแต่ต้นทาง.

    เรียกก่อนยิง request จริงทุกครั้ง; thread-safe และ 0 RPM = ปิด throttle.
    """
    interval = _min_interval_seconds()
    if interval <= 0:
        return
    global _last_request_ts
    with _rate_lock:
        now = time.monotonic()
        wait = _last_request_ts + interval - now
        if wait > 0:
            time.sleep(wait)
        _last_request_ts = time.monotonic()


def _is_retryable_llm_error(exc: Exception) -> bool:
    """True เมื่อ error ควร retry (429/5xx/connection/timeout)."""
    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS_CODES:
        return True
    name = type(exc).__name__
    return any(k in name for k in _RETRYABLE_ERROR_NAMES)


def _retry_after_seconds(exc: Exception) -> Optional[float]:
    """อ่าน Retry-After header จาก response (ถ้ามี) — เคารพจังหวะที่ server สั่ง"""
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) or {}
    ra = headers.get("retry-after") or headers.get("Retry-After")
    if ra is not None:
        try:
            return float(ra)
        except (TypeError, ValueError):
            return None
    return None


def call_with_backoff(
    fn,
    attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
) -> Any:
    """เรียก fn() พร้อม throttle + retry แบบ exponential backoff.

    - throttle_llm_request() ก่อนยิงทุกครั้ง (จำกัด RPM กัน 429 ตั้งแต่ต้นทาง)
    - retry เฉพาะ error ที่ retryable (429/5xx/connection/timeout) เคารพ
      Retry-After header ถ้ามี; error อื่น (401 auth/parse) raise ทันที
    """
    n = attempts if attempts is not None else int(getattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 3) or 3)
    base = base_delay if base_delay is not None else float(getattr(settings, "LLM_RETRY_BASE_DELAY", 1.0) or 1.0)
    cap = max_delay if max_delay is not None else float(getattr(settings, "LLM_RETRY_MAX_DELAY", 30.0) or 30.0)

    for attempt in range(1, n + 1):
        throttle_llm_request()
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — catch กว้างเพื่อจำแนก retryable
            retry_after = _retry_after_seconds(exc)
            if attempt < n and (retry_after is not None or _is_retryable_llm_error(exc)):
                # cap Retry-After ด้วย max_delay — กัน server สั่ง backoff นานจน request ค้าง
                delay = min(retry_after, cap) if retry_after is not None else min(base * (2 ** (attempt - 1)), cap)
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt, n, exc, delay,
                )
                time.sleep(delay)
                continue
            raise
