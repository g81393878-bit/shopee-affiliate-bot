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
BOT_NAME = _env("BOT_NAME", "ร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้")

# ชื่อตัวละคร/มาสคอต (ใช้ใน persona prompt และน้ำเสียง AI)
PERSONA_NAME = _env("PERSONA_NAME", "ป้าเข็ม")

# สโลแกนร้าน (ใช้ท้ายคอนเทนต์/คำตอบมาตรฐานบริการ)
BOT_SLOGAN = _env("BOT_SLOGAN", "ปลาสลิดแดดเดียว ไซส์จัมโบ้ 5-7 ตัว/กก. เค็มน้อย 3% ทอดกรอบอร่อย ส่งฟรีทั่วไทย")

# LINE OA ของร้าน — โชว์ ID + ลิงก์ในท้ายโพสต์ Facebook ทุกโพสต์
LINE_OA_ID = _env("LINE_OA_ID", "@137gsref")
LINE_OA_URL = _env("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
WEB_STORE_URL = _env("WEB_STORE_URL", "https://watt29.github.io/pakhem-shop/fish.html")


def line_cta_footer(line_url: str = "") -> str:
    """ท้ายโพสต์ Facebook — ชวนแอดไลน์ร้าน + ลิงก์สั่งซื้อปลาสลิดออนไลน์."""
    url = (line_url or LINE_OA_URL).strip()
    parts = [
        f"🐟 สั่งซื้อปลาสลิดแดดเดียวคัดพิเศษ 👉 {WEB_STORE_URL}",
        f"👉 แอดไลน์{PERSONA_NAME}: {LINE_OA_ID}"
    ]
    if url:
        parts.append(f"🔗 {url}")
    return "\n".join(parts)


def promo_captions() -> list:
    """แคปชันโปรโมทร้านปลาสลิดป้าเข็ม สุพรรณบุรีแท้ 100% (หมุนเวียนกันโพสต์ให้ไม่ซ้ำ) — แหล่งความจริงเดียว."""
    url = LINE_OA_URL
    store = WEB_STORE_URL
    return [
        (f"🐟 ปลาสลิดแดดเดียว สุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ ไซส์จัมโบ้ 5-7 ตัว/กก. ✨\n"
         "🥩 เนื้อหนาฟู มันแทรก หมักเกลือสมุทรธรรมชาติ 3% ไร้กลิ่นโคลน ไม่เค็มแสบคอ\n"
         "❄️ ซีลสูญญากาศแช่แข็ง แพ็กซองฟอยล์เก็บความเย็นส่งด่วนถึงหน้าบ้าน โอนเงินส่งฟรีทุกชุด!\n"
         f"🛒 สั่งซื้อด่วน: {store}\n"
         f"👉 หรือแอดไลน์สั่งซื้อ: {url}"),
        (f"🔥 ทอดกรอบนอกนุ่มใน เนื้อปลาฟูแน่น กลิ่นหอมแดดธรรมชาติน่าทานมากๆ จ้า 🤤\n"
         "💯 ปลาสลิดป้าเข็ม สุพรรณบุรีแท้ คัดเกรดพรีเมียม สะอาด ปลอดภัย ตากโรงอบปิดไร้แมลงวัน\n"
         "📦 มีบริการเก็บเงินปลายทาง (COD) ตรวจรับของหน้าบ้านก่อนค่อยชำระเงินจ้า\n"
         f"🛒 กดสั่งซื้อที่หน้าร้าน: {store}\n"
         f"👉 หรือทักแชทคุยกับป้าเข็ม: {url}"),
        (f"🍽️ เมนูเด็ดมื้อนี้ ข้าวสวยร้อนๆ คู่น้ำปลาพริกมะนาว และปลาสลิดทอดกรอบๆ ฟินสุดๆ ค่ะ 💕\n"
         "✨ ทำปลาสดใหม่ทุกวัน ไร้สารฟอร์มาลีน ไร้สารกันบูด คนรักสุขภาพและผู้สูงอายุทานได้สบายใจ\n"
         "🚚 จัดส่งทั่วไทย แพ็กเก็บความเย็นอย่างดี การันตีความสดใหม่ 100%\n"
         f"🛒 สั่งซื้อออนไลน์: {store}\n"
         f"👉 แอดไลน์ป้าเข็ม: {url}"),
        (f"❄️ มีติดช่องฟรีซไว้ อุ่นใจทุกมื้อ! ปลาสลิดแดดเดียวสุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ 🐟\n"
         "🧊 แช่ฟรีซเก็บได้นาน 6 เดือน ทอดในกระทะหรือหม้อทอดไร้น้ำมันก็กรอบอร่อย ไร้ควัน\n"
         "🏷️ ชุด 500g (ประมาณ 3-4 ตัว 390.-) | ชุด 1kg (ประมาณ 5-7 ตัว 550.-) โอนส่งฟรีทั่วไทย!\n"
         f"🛒 กดสั่งซื้อที่นี่: {store}\n"
         f"👉 ทักแชทสั่งซื้อทาง LINE: {url}"),
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

    ใช้ในคำตอบ "ติดต่อเจ้าของร้าน" ของบอท LINE — ลูกค้าสอบถามสินค้า/พิกัดของแท้ได้ทันที.
    """
    parts = ["📞 ติดต่อป้าเข็มได้โดยตรงเลยจ๊ะ:"]
    parts.append(f"👉 LINE: {LINE_OA_ID}")
    if LINE_OA_URL:
        parts.append(f"🔗 {LINE_OA_URL}")
    parts.append("\nทักมาสอบถามสินค้าที่ตามหา หรือให้ป้าเข็มช่วยเช็คพิกัดของแท้ได้เลยนะคะ 😊")
    return "\n".join(parts)
