"""Bot Profile — ตัวตนร้าน (White-Label) รวมศูนย์ไว้จุดเดียว

เปลี่ยนชื่อบอท/ชื่อตัวละคร/สโลแกนได้โดยไม่แตะโค้ด:
  - ตั้งใน `backend/.env` (หรือ env บน Render):
        BOT_NAME=ร้านหนูขายของ
        PERSONA_NAME=ป้าอุ่น
        BOT_SLOGAN=ของดีราคาเบา ๆ
  - ไม่ตั้ง = ใช้ default "ป้าเข็ม" (โค้ดเดิมทำงานเหมือนเดิมทุกประการ)

Phase 1 = อ่านจาก env (ติดตั้งง่าย + แบ็คอัพง่าย = ก๊อป .env)
Phase 2 = ย้ายไปตาราง bot_profiles + หน้าแอดมิน (ดู docs/srs-white-label-bot.md)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# โหลด .env ทุกครั้งที่ import ตัวนี้ (กันกรณีถูก import ก่อน app.config)
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")


def _env(key: str, default: str) -> str:
    """env ค่าว่าง/ไม่ตั้ง → คืน default (กันบอทชื่อว่าง)"""
    return (os.getenv(key) or "").strip() or default


# ชื่อร้าน (แสดงใน welcome/ข้อความต้อนรับ)
BOT_NAME = _env("BOT_NAME", "ป้าเข็ม ขายของ")

# ชื่อตัวละคร/มาสคอต (ใช้ใน persona prompt และน้ำเสียง AI)
PERSONA_NAME = _env("PERSONA_NAME", "ป้าเข็ม")

# สโลแกนร้าน (ใช้ท้ายคอนเทนต์/คำตอบมาตรฐานบริการ)
BOT_SLOGAN = _env("BOT_SLOGAN", "ความพึงพอใจของคุณคือความสำเร็จของเรา")
