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

# LINE OA ของร้าน — โชว์ ID + ลิงก์ในท้ายโพสต์ Facebook ทุกโพสต์
LINE_OA_ID = _env("LINE_OA_ID", "@137gsref")
LINE_OA_URL = _env("LINE_OA_URL", "https://lin.ee/o9Kjp1N")

# เบอร์โทรเจ้าของร้าน (โชว์ในคำตอบ "ติดต่อเจ้าของร้าน" — ว่าง = ไม่โชว์บรรทัดเบอร์)
OWNER_PHONE = _env("OWNER_PHONE", "")


def line_cta_footer(line_url: str = "") -> str:
    """ท้ายโพสต์ Facebook — ชวนแอดไลน์ร้าน (LINE ID + ลิงก์กดแอดได้ทันที).

    line_url ใช้ override ลิงก์รายโพสต์ได้ (เช่น เทสต์/แคมเปญเฉพาะ); ว่าง = ใช้ LINE_OA_URL.
    """
    url = (line_url or LINE_OA_URL).strip()
    parts = [f"👉 แอดไลน์{PERSONA_NAME}: {LINE_OA_ID}"]
    if url:
        parts.append(f"🔗 {url}")
    return "\n".join(parts)


def owner_contact_text() -> str:
    """ช่องทางติดต่อเจ้าของร้านตรง ๆ — LINE ID + ลิงก์ + เบอร์โทร (ถ้าตั้ง).

    ใช้ในคำตอบ "ติดต่อเจ้าของร้าน" ของบอท LINE — ลูกค้าที่สนใจซื้อบอทติดต่อปิดดีลได้ทันที
    (ไม่ต้องฝากคำถามรอเจ้าของตอบทีหลัง).
    """
    parts = ["📞 ติดต่อเจ้าของร้านได้โดยตรงเลยจ๊ะ:"]
    parts.append(f"👉 LINE: {LINE_OA_ID}")
    if LINE_OA_URL:
        parts.append(f"🔗 {LINE_OA_URL}")
    if OWNER_PHONE:
        parts.append(f"📱 เบอร์โทร: {OWNER_PHONE}")
    parts.append("\nทักมาแจ้งแพ็กเกจที่สนใจได้เลย แล้วป้าจะดูแลต่อเองจ๊ะ 😊")
    return "\n".join(parts)
