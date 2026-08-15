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
"""

import threading

from openai import OpenAI

from app.config import settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/"

_lock = threading.Lock()
_start_index = 0


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
