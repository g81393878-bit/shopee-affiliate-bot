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
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# โหลด .env ทุกครั้งที่ import ตัวนี้ (กันกรณีถูก import ก่อน app.config)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_BACKEND_DIR / ".env")

# state จำตำแหน่งแคปชันโพสต์ล่าสุด (หมุนเวียนไม่ซ้ำติดกัน) — ไฟล์เดียวทั้งโพสต์รูป/วิดีโอ
_PROMO_CAPTION_STATE = _BACKEND_DIR / ".promo_caption_state.json"


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


def line_cta_footer(line_url: str = "") -> str:
    """ท้ายโพสต์ Facebook — ชวนแอดไลน์ร้าน (LINE ID + ลิงก์กดแอดได้ทันที).

    line_url ใช้ override ลิงก์รายโพสต์ได้ (เช่น เทสต์/แคมเปญเฉพาะ); ว่าง = ใช้ LINE_OA_URL.
    """
    url = (line_url or LINE_OA_URL).strip()
    parts = [f"👉 แอดไลน์{PERSONA_NAME}: {LINE_OA_ID}"]
    if url:
        parts.append(f"🔗 {url}")
    return "\n".join(parts)


def promo_captions() -> list:
    """แคปชันโปรโมทบอทหลายแบบ (หมุนเวียนกันโพสต์ให้ไม่ซ้ำ) — แหล่งความจริงเดียว."""
    url = LINE_OA_URL
    return [
        (f"อยากใช้บอทช่วยขายของ Shopee (บอทป้าเข็ม) ป้าจัดการระบบให้พร้อมใช้ทันทีจ้า 😊\n"
         "🛠️ ปลอดภัยรันบนบัญชี/คีย์คุณเอง แอดมินดูแลหลังบ้านให้หมด ไม่ต้องเซ็ตค่าเองให้ปวดหัวจ้า\n"
         f"💼 เริ่มต้น 490.- แอดไลน์คุยรายละเอียดแพ็กเกจกับป้าเลยจ้า 👉 {url}"),
        (f"เบื่อไหมตอบแชทลูกค้าเองทั้งวัน 🤖 บอทป้าเข็มช่วยได้ — ค้นสินค้า + ตอบแชท + จำความชอบลูกค้า\n"
         "📦 แปลงลิงก์ค่าคอม Shopee ให้อัตโนมัติ แม่ค้าแค่แชร์ ๆ ๆ\n"
         f"💼 เริ่มต้น 490.- แอดไลน์ป้าเข็มได้เลยจ้า 👉 {url}"),
        (f"อยากให้เพจหาคนซื้อให้แบบไม่ต้องนั่งเฝ้า 🔍 บอทป้าเข็มส่องโพสต์คนอยากซื้อ แล้วจับคู่สินค้าในคลัง\n"
         "🚀 โพสต์อัตโนมัติ + แจ้งเตือน โควตาจำกัดไม่สแปม\n"
         f"💼 เริ่มต้น 490.- คุยแพ็กเกจกับป้าได้เลยจ้า 👉 {url}"),
        (f"เปิดร้านออนไลน์แล้วยังเงียบ ๆ อยู่ไหม 🛒 บอทป้าเข็มช่วยขายของ Shopee ให้แม่ค้าไทย\n"
         "🧠 AI เข้าใจภาษาไทย ตอบเอง 24 ชม. ไม่มีวันหยุด\n"
         f"💼 เริ่มต้น 490.- แอดไลน์คุยกับป้าเข็มเลยจ้า 👉 {url}"),
    ]


def _read_promo_state() -> int:
    try:
        data = json.loads(_PROMO_CAPTION_STATE.read_text(encoding="utf-8"))
        return int(data.get("idx", 0))
    except Exception:
        return 0


def _write_promo_state(idx: int) -> None:
    try:
        _PROMO_CAPTION_STATE.write_text(json.dumps({"idx": idx}), encoding="utf-8")
    except Exception:
        pass


def pick_promo_caption(advance: bool = True) -> str:
    """หยิบแคปชันโปรโมททีละแบบ (round-robin) — advance=True เลื่อนไปตัวถัดไป (ใช้โพสต์จริง).

    advance=False = แค่ดู (dry-run) ไม่กินตำแหน่ง ไม่เลื่อน rotation.
    """
    captions = promo_captions()
    idx = _read_promo_state() % len(captions)
    if advance:
        _write_promo_state((idx + 1) % len(captions))
    return captions[idx]


def owner_contact_text() -> str:
    """ช่องทางติดต่อป้าเข็มตรง ๆ — LINE ID + ลิงก์เท่านั้น (ไม่มีเบอร์โทร).

    ใช้ในคำตอบ "ติดต่อเจ้าของร้าน" ของบอท LINE — ลูกค้าที่สนใจซื้อบอทแอดไลน์ป้าเข็มปิดดีลได้ทันที.
    """
    parts = ["📞 ติดต่อป้าเข็มได้โดยตรงเลยจ๊ะ:"]
    parts.append(f"👉 LINE: {LINE_OA_ID}")
    if LINE_OA_URL:
        parts.append(f"🔗 {LINE_OA_URL}")
    parts.append("\nทักมาแจ้งแพ็กเกจที่สนใจได้เลย แล้วป้าจะดูแลต่อเองจ๊ะ 😊")
    return "\n".join(parts)
