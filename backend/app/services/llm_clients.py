"""
LLM client helpers — รองรับ Groq หลาย API key พร้อมสลับใช้งานอัตโนมัติ.

วิธีตั้งค่า: ใส่ key หลายตัวคั่นด้วยคอมม่าใน GROQ_API_KEY
    GROQ_API_KEY=gsk_aaa...,gsk_bbb...,gsk_ccc...

การทำงาน:
  - groq_clients() หมุนเวียนลำดับ key ทุกครั้งที่เรียก (กระจายโหลด)
  - ผู้เรียกวนใช้ clients ทุกตัวตามลำดับ — ตัวไหนล้ม/โดน rate limit (429)
    ก็ข้ามไปตัวถัดไป (failover) จนกว่าจะสำเร็จ
"""

import threading

from openai import OpenAI

from app.config import settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

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


def groq_clients() -> list:
    """OpenAI clients ของทุก Groq keys เรียงแบบหมุนเวียน (call ถัดไปเริ่มที่ key ถัดไป)"""
    keys = groq_keys()
    if not keys:
        return []
    global _start_index
    with _lock:
        rot = _start_index % len(keys)
        _start_index += 1
    ordered = keys[rot:] + keys[:rot]
    return [OpenAI(api_key=k, base_url=GROQ_BASE_URL) for k in ordered]
