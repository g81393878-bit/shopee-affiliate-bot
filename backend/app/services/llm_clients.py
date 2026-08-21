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

import json
import logging
import random
import re
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

# --- Circuit breaker state (ต่อ API key — กัน key ที่ล้มซ้ำ ๆ ถูกยิงซ้ำทุก call) ---
_circuit_lock = threading.Lock()
_circuit: dict = {}  # api_key -> {"failures": int, "open_until": float}

CIRCUIT_FAIL_THRESHOLD = 2          # ล้มติดกันกี่ครั้งถึงเปิด circuit
CIRCUIT_COOLDOWN_SECONDS = 60.0     # เปิดแล้วกันนานเท่าไหร่ (วินาที)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_ERROR_NAMES = (
    "ConnectionError", "Timeout", "APITimeout",
    "RateLimitError", "InternalServerError",
    # google-generativeai transient/rate-limit errors
    "ResourceExhausted", "ServiceUnavailable", "DeadlineExceeded",
)


class CircuitOpenError(Exception):
    """Circuit ของ key นี้กำลัง open (cooldown) — caller ควรข้ามไป key ถัดไปทันที."""


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


def _circuit_is_open(api_key: str) -> bool:
    """True เมื่อ circuit ของ key นี้กำลัง open (cooldown) — ควรข้าม key นี้ไปก่อน.

    สถานะ:
      - ไม่มีใน dict / open_until = 0 → circuit ปิด (failure นับอยู่แต่ยังไม่ถึง threshold)
      - open_until > 0 และ time < open_until → circuit OPEN (กัน key นี้ชั่วคราว)
      - open_until > 0 และ time >= open_until → cooldown หมด → auto-recover (pop ออก)
    """
    if not api_key:
        return False
    with _circuit_lock:
        st = _circuit.get(api_key)
        if not st:
            return False
        # auto-recover: เปิดแล้วแต่ cooldown หมดแล้ว → ลบทิ้ง (กลับมาใช้ได้)
        if st["open_until"] > 0 and time.monotonic() >= st["open_until"]:
            _circuit.pop(api_key, None)
            return False
        return st["open_until"] > 0


def _circuit_record_failure(api_key: str) -> None:
    """นับความล้มต่อเนื่อง; ถึง threshold → เปิด circuit (กัน key นี้ชั่วคราว)."""
    if not api_key:
        return
    with _circuit_lock:
        st = _circuit.setdefault(api_key, {"failures": 0, "open_until": 0.0})
        st["failures"] += 1
        if st["failures"] >= CIRCUIT_FAIL_THRESHOLD:
            st["open_until"] = time.monotonic() + CIRCUIT_COOLDOWN_SECONDS
            logger.warning(
                "Circuit breaker: key %s... เปิด %ds (ล้มติด %d ครั้ง) — ข้าม key นี้ชั่วคราว",
                api_key[:8], CIRCUIT_COOLDOWN_SECONDS, st["failures"],
            )


def _circuit_record_success(api_key: str) -> None:
    """สำเร็จ → รีเซ็ตตัวนับ (ปิด circuit ทันที)."""
    if not api_key:
        return
    with _circuit_lock:
        _circuit.pop(api_key, None)


def groq_clients() -> list:
    """OpenAI clients ของทุก Groq keys เรียงแบบหมุนเวียน (call ถัดไปเริ่มที่ key ถัดไป) —
    กรอง key ที่ circuit เปิดทิ้ง (ล้มซ้ำ ๆ กันยิงซ้ำทุก call)."""
    keys = groq_keys()
    if not keys:
        return []
    return [
        OpenAI(api_key=k, base_url=GROQ_BASE_URL)
        for k in _rotate(keys)
        if not _circuit_is_open(k)
    ]


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
    """OpenAI clients ของทุก Anthropic keys เรียงแบบหมุนเวียน (ผ่าน OpenAI-compat endpoint) —
    กรอง key ที่ circuit เปิดทิ้งด้วย"""
    keys = anthropic_keys()
    if not keys:
        return []
    return [
        OpenAI(api_key=k, base_url=ANTHROPIC_BASE_URL)
        for k in _rotate(keys)
        if not _circuit_is_open(k)
    ]


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


# ---------------------------------------------------------------------------
# Robust JSON parsing + structured output (กัน model คืน JSON เละ/มี fence ครอบ)
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_llm_json(content: Any) -> Any:
    """Parse JSON จาก LLM response อย่างทนทาน (กันของจริงที่เจอบ่อย):

    - ตัด markdown fence (```json ... ``` / ``` ... ```) — โมเดลหลายตัวชอบครอบ
    - กันข้อความแทรกหน้า/หลัง — เอาเฉพาะบล็อก `{...}` แรกสุดถึงสุดท้าย
    - พยายาม json.loads บน string ที่เหลือ; ไม่ได้ → raise ValueError (caller ควร fallback)
    """
    if not isinstance(content, str):
        raise ValueError(f"LLM response ไม่ใช่ string: {type(content).__name__}")
    text = content.strip()
    if not text:
        raise ValueError("LLM response ว่างเปล่า")
    m = _JSON_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except (TypeError, ValueError) as e:
        raise ValueError(f"LLM response ไม่ใช่ JSON ที่ valid: {e}") from e


_GROQ_STRICT_JSON_MODELS = {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}


def groq_json_schema_format(schema: dict, model: str = "") -> dict:
    """response_format สำหรับ Groq — ใช้ json_schema (strict) เมื่อโมเดลรองรับ
    (การันตี output ตรง schema เป๊ะ) ตกกลับเป็น json_object สำหรับโมเดลอื่น
    (Groq คืน 400 ถ้าส่ง json_schema ไปให้โมเดลที่ไม่รองรับ strict)
    """
    if model in _GROQ_STRICT_JSON_MODELS:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": schema,
            },
        }
    return {"type": "json_object"}


def call_with_backoff(
    fn,
    attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    circuit_key: Optional[str] = None,
) -> Any:
    """เรียก fn() พร้อม throttle + retry แบบ exponential backoff.

    - throttle_llm_request() ก่อนยิงทุกครั้ง (จำกัด RPM กัน 429 ตั้งแต่ต้นทาง)
    - retry เฉพาะ error ที่ retryable (429/5xx/connection/timeout) เคารพ
      Retry-After header ถ้ามี; error อื่น (401 auth/parse) raise ทันที
    - circuit_key (เช่น api_key): เปิด circuit เมื่อ key ล้มติดกัน ≥ CIRCUIT_FAIL_THRESHOLD
      → key นั้นถูกกรองออกจาก groq_clients()/anthropic_clients() ชั่วคราว (กันยิงซ้ำ);
      สำเร็จ → รีเซ็ตตัวนับ. ยังเปิดอยู่ → raise CircuitOpenError ทันที ไม่ยิงซ้ำ
    - jitter ±30% ใน exponential backoff (ไม่ใช้กับ Retry-After) — กันหลาย thread
      retry พร้อมกัน (thundering herd)
    """
    n = attempts if attempts is not None else int(getattr(settings, "LLM_RETRY_MAX_ATTEMPTS", 3) or 3)
    base = base_delay if base_delay is not None else float(getattr(settings, "LLM_RETRY_BASE_DELAY", 1.0) or 1.0)
    cap = max_delay if max_delay is not None else float(getattr(settings, "LLM_RETRY_MAX_DELAY", 30.0) or 30.0)

    for attempt in range(1, n + 1):
        if circuit_key and _circuit_is_open(circuit_key):
            raise CircuitOpenError(f"circuit open for key {circuit_key[:8]}...")
        throttle_llm_request()
        try:
            result = fn()
            if circuit_key:
                _circuit_record_success(circuit_key)
            return result
        except Exception as exc:  # noqa: BLE001 — catch กว้างเพื่อจำแนก retryable
            retry_after = _retry_after_seconds(exc)
            retryable = retry_after is not None or _is_retryable_llm_error(exc)

            if circuit_key:
                # fail-fast: นับความล้มแล้ว raise → caller ลอง key ถัดไปทันที
                # (ไม่เผา retries บน key เดิม — key ที่ 429/5xx ย้าย key อื่นไว;
                #  circuit เปิดเมื่อล้มติดกัน ≥ threshold → key นั้นถูกกรองออกชั่วคราว)
                if retryable:
                    _circuit_record_failure(circuit_key)
                raise

            # ไม่มี circuit_key (single-key mode): พฤติกรรมเดิม — retry เดิม key
            if attempt < n and retryable:
                # cap Retry-After ด้วย max_delay — กัน server สั่ง backoff นานจน request ค้าง
                if retry_after is not None:
                    delay = min(retry_after, cap)
                else:
                    delay = min(base * (2 ** (attempt - 1)), cap)
                    delay *= random.uniform(0.7, 1.3)  # jitter ±30% กัน thundering herd
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt, n, exc, delay,
                )
                time.sleep(delay)
                continue
            raise
