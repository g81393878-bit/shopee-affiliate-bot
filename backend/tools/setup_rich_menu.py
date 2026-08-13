"""ตั้งค่า LINE Rich Menu (แถบเมนูติดหน้าจอด้านล่าง — ไม่หายเหมือน quick reply)

- วาดรูปเมนู 2500x1686 (3x2 = 6 ปุ่ม) ด้วย Pillow + ฟอนต์ไทย (Tahoma)
- สร้าง rich menu → อัปโหลดรูป → ตั้งเป็น default ให้ทุกคน
- Idempotent: รันซ้ำได้ ไม่สร้างซ้ำ (เจอตัวชื่อเดียวกันที่ตั้ง default แล้ว = ข้าม;
  ตัวเก่าชื่อเดียวกันถูกลบหลังตั้งตัวใหม่)

รัน: cd backend && PYTHONIOENCODING=utf-8 ./.venv/Scripts/python tools/setup_rich_menu.py
รูปตัวอย่างถูกเขียนที่ D:/rich_menu.png (ดูได้ ไม่ได้ commit ขึ้น git)
"""
import os
import sys

# ให้ import app.* ได้ (db.py/models.py อยู่ app/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

try:
    from dotenv import load_dotenv
    load_dotenv()  # fallback: อ่าน backend/.env (ไม่ทับ env ที่ตั้งไว้แล้ว)
except Exception:
    pass

from PIL import Image, ImageDraw, ImageFont

from linebot import LineBotApi
from linebot.models import (RichMenu, RichMenuSize, RichMenuArea, RichMenuBounds,
                            MessageAction)

MENU_NAME = "ป้าเข็มเมนู"
CHAT_BAR_TEXT = "🛍️ เมนูป้าเข็ม"

# (label ในแถบ, ข้อความที่ส่งเมื่อแตะ, สีพื้นหลัง, สีตัวหนังสือ)
MENU = [
    ("ค้นสินค้า",     "ค้นสินค้า",              "#FFE3EC", "#B3204E"),
    ("หมวดสินค้า",   "หมวดสินค้า",            "#E3F0FF", "#1F5FA8"),
    ("ขายดีวันนี้",   "วันนี้ขายอะไรดี",        "#FFF3D6", "#B07A00"),
    ("อันดับขายดี",   "อันดับขายดี",            "#E4F7E4", "#1E7B3C"),
    ("ทำไมต้องป้าเข็ม", "ทำไมต้องซื้อกับป้าเข็ม", "#F0E8FF", "#5B3FA8"),
    ("คุยกับป้าเข็ม",  "คุยกับป้าเข็ม",           "#E0F5F5", "#0E7C7C"),
]

W, H = 2500, 1686          # ขนาด rich menu มาตรฐาน
COLS, ROWS = 3, 2
FONT_PATH = "C:/Windows/Fonts/Tahoma.ttf"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def draw_rich_menu_image(path: str):
    """วาดรูปเมนู 3x2 — พื้นขาว + 6 ช่องสีพาสเทล + ข้อความไทยกลางช่อง"""
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    cw, ch = W // COLS, H // ROWS
    f = _font(105)
    for i, (_label, _text, bg, fg) in enumerate(MENU):
        r, c = divmod(i, COLS)
        x0, y0 = c * cw, r * ch
        x1, y1 = (W if c == COLS - 1 else x0 + cw), (H if r == ROWS - 1 else y0 + ch)
        d.rounded_rectangle([x0 + 18, y0 + 18, x1 - 18, y1 - 18], radius=36, fill=bg)
        # ข้อความกลางช่อง (วัดความกว้างจริงเพื่อจัดกลางเป๊ะ)
        tb = d.textbbox((0, 0), _text, font=f)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        d.text(((x0 + x1 - tw) / 2 - tb[0], (y0 + y1 - th) / 2 - tb[1]), _text,
               font=f, fill=fg)
        # เส้นขอบบางๆ
        d.rounded_rectangle([x0 + 18, y0 + 18, x1 - 18, y1 - 18], radius=36,
                            outline="#D8D8D8", width=4)
    img.save(path, "PNG")
    return path


def main():
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token or "mock" in token.lower():
        print("❌ ไม่มี LINE_CHANNEL_ACCESS_TOKEN จริง (หรือเป็น mock) — ข้าม")
        return 1
    api = LineBotApi(token)

    existing = api.get_rich_menu_list()
    mine = [m for m in existing if m.name == MENU_NAME]
    default_id = _default_rich_menu_id(api)
    if mine and default_id and any(m.rich_menu_id == default_id for m in mine):
        print(f"✅ Rich menu '{MENU_NAME}' ตั้งเป็น default แล้ว ({default_id}) — ไม่ต้องทำซ้ำ")
        return 0

    # 1) วาดรูป
    out_png = "D:/rich_menu.png"
    draw_rich_menu_image(out_png)
    with open(out_png, "rb") as f:
        img_bytes = f.read()
    print(f"🎨 วาดรูปเมนูแล้ว: {out_png} ({len(img_bytes):,} bytes)")

    # 2) สร้าง rich menu (3x2)
    cw, ch = W // COLS, H // ROWS
    areas = []
    for i, (_label, text, _bg, _fg) in enumerate(MENU):
        r, c = divmod(i, COLS)
        areas.append(RichMenuArea(
            bounds=RichMenuBounds(x=c * cw, y=r * ch,
                                  width=(W - c * cw) if c == COLS - 1 else cw,
                                  height=(H - r * ch) if r == ROWS - 1 else ch),
            action=MessageAction(label=_label, text=text)))
    rich = RichMenu(size=RichMenuSize(width=W, height=H), selected=True,
                    name=MENU_NAME, chat_bar_text=CHAT_BAR_TEXT, areas=areas)
    rich_id = api.create_rich_menu(rich)
    print(f"📋 สร้าง rich menu แล้ว: {rich_id}")

    # 3) อัปโหลดรูป
    api.set_rich_menu_image(rich_id, "image/png", img_bytes)
    print("🖼️ อัปโหลดรูปแล้ว")

    # 4) ตั้งเป็น default ให้ทุกคน
    api.set_default_rich_menu(rich_id)
    print("👥 ตั้งเป็น default ให้ทุกคนแล้ว")

    # 5) ลบตัวเก่าชื่อเดียวกัน (ถ้ามี) — กันทิ้งขยะ
    for m in existing:
        if m.name == MENU_NAME and m.rich_menu_id != rich_id:
            try:
                api.delete_rich_menu(m.rich_menu_id)
                print(f"🗑️ ลบ rich menu เก่า: {m.rich_menu_id}")
            except Exception as e:
                print(f"⚠️ ลบตัวเก่าไม่ได้: {e}")

    print(f"\n✅ เสร็จ — default rich menu = {_default_rich_menu_id(api)}")
    return 0


def _default_rich_menu_id(api):
    """SDK ตัวนี้ get_default_rich_menu คืน ID ตรงๆ (str) — รองรับทั้ง str/object"""
    try:
        d = api.get_default_rich_menu()
        return d if isinstance(d, str) else getattr(d, "rich_menu_id", None)
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
