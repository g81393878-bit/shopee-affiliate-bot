#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตั้ง Rich Menu (แถบเมนูติดด้านล่าง) ให้บอท LINE — ป้าเข็ม ขายของ
============================================================
วาด PNG 2500x843 (3 ปุ่ม) ด้วย Pillow -> อัปโหลดผ่าน LINE Messaging API
-> ตั้งเป็น rich menu เริ่มต้น (ผู้ใช้เห็นทันที ไม่ต้องพิมพ์)

รัน:
  backend/.venv/Scripts/python tools/line_rich_menu.py

ต้องมี LINE_CHANNEL_ACCESS_TOKEN ใน backend/.env (หรือ env) — admin token
"""

import json
import pathlib
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Pillow ใช้เฉพาะวาดภาพ
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / "backend" / ".env"

API_BASE = "https://api.line.me/v2/bot"
IMAGE_BASE = "https://api-data.line.me/v2/bot"  # อัปโหลดรูป rich menu ใช้ base นี้

MENU_ITEMS = [
    {"label": "ค้นหาสินค้า", "sub": "พิมพ์ชื่อหรือระบุงบ", "icon": "🔍", "color": "#EE4D2D", "send": "ค้นสินค้า"},
    {"label": "บอทรายเดือน", "sub": "เริ่มต้น 490.- / แพ็กเกจ", "icon": "💼", "color": "#F59E0B", "send": "ราคาบอท"},
    {"label": "คุยกับป้าเข็ม", "sub": "ปรึกษา & เช็คของแท้", "icon": "💬", "color": "#059669", "send": "คุยกับป้าเข็ม"},
]

W, H = 2500, 843
COL_W = W // 3  # 833


def load_token() -> str:
    token = None
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("LINE_CHANNEL_ACCESS_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    return token or ""


FONT_DIR = PROJECT_ROOT / "tools" / "fonts"

def load_font(size: int, weight: str = "bold"):
    fname = f"Prompt-Bold.ttf" if weight == "bold" else (f"Prompt-Medium.ttf" if weight == "medium" else "Prompt-Regular.ttf")
    fpath = FONT_DIR / fname
    if fpath.exists():
        try:
            return ImageFont.truetype(str(fpath), size)
        except Exception:
            pass
    # Fallback
    candidates = [
        r"C:\Windows\Fonts\leelawdb.ttf" if weight == "bold" else r"C:\Windows\Fonts\leelawadeeui.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf" if weight == "bold" else r"C:\Windows\Fonts\tahoma.ttf",
    ]
    for p in candidates:
        if pathlib.Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def create_gradient(width: int, height: int, start_color: tuple, end_color: tuple) -> Image.Image:
    """สร้างภาพ Gradient แนวตั้ง/แนวเฉียงที่เรียบเนียนระดับพรีเมียม"""
    base = Image.new("RGBA", (width, height), start_color)
    top = Image.new("RGBA", (width, height), end_color)
    mask = Image.new("L", (width, height))
    mask_data = []
    for y in range(height):
        for x in range(width):
            # ไล่เฉียงจากบนซ้ายไปล่างขวา
            p = (y / height) * 0.7 + (x / width) * 0.3
            mask_data.append(int(255 * min(max(p, 0.0), 1.0)))
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base


def draw_menu(path: str):
    # 1. Background พื้นหลัง Dark Cyber Slate ลึก พรีเมียม
    img = Image.new("RGBA", (W, H), (11, 15, 25, 255))
    d = ImageDraw.Draw(img)

    # วาด Ambient Glow เล็กน้อยด้านหลัง
    glow1 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow1)
    g_draw.ellipse([100, -100, 900, 700], fill=(255, 75, 43, 35))
    g_draw.ellipse([850, -100, 1650, 700], fill=(245, 158, 11, 35))
    g_draw.ellipse([1600, -100, 2400, 700], fill=(16, 185, 129, 35))
    img = Image.alpha_composite(img, glow1)
    d = ImageDraw.Draw(img)

    CARDS = [
        {
            "badge": "🔥 ค้นหาของแท้ & ดีลลด",
            "title": "ค้นหาสินค้า",
            "sub": "พิมพ์ชื่อของ หรือบอกงบที่ต้องการ",
            "cta": "แตะเพื่อค้นหาทันที  ›",
            "c_start": (255, 75, 43, 255),    # Coral Orange
            "c_end": (225, 29, 72, 255),      # Vivid Crimson Rose
            "icon_type": "search"
        },
        {
            "badge": "⚡️ เริ่มต้น 490.- / เดือน",
            "title": "บอทรายเดือน",
            "sub": "เช่าบอทช่วยขาย Shopee 24 ชม.",
            "cta": "ดูแพ็กเกจ & ราคาบอท  ›",
            "c_start": (245, 158, 11, 255),   # Royal Amber
            "c_end": (180, 83, 9, 255),       # Deep Gold Amber
            "icon_type": "bot"
        },
        {
            "badge": "🟢 ออนไลน์ตอบไว 24 ชม.",
            "title": "คุยกับป้าเข็ม",
            "sub": "ปรึกษา เช็คพิกัดของแท้ หรือทักทาย",
            "cta": "ทักแชทคุยกับป้าเข็ม  ›",
            "c_start": (16, 185, 129, 255),   # Emerald
            "c_end": (4, 120, 87, 255),       # Deep Teal Green
            "icon_type": "chat"
        },
    ]

    for i, item in enumerate(CARDS):
        x0 = i * COL_W + 28
        y0 = 28
        x1 = (i + 1) * COL_W - 28
        y1 = H - 28
        cw = x1 - x0
        ch = y1 - y0

        # สร้างการ์ด Gradient ขอบมน
        card_img = create_gradient(cw, ch, item["c_start"], item["c_end"])
        mask = Image.new("L", (cw, ch), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, cw, ch], radius=44, fill=255)

        # แปะการ์ดลงบนพื้นหลัง
        img.paste(card_img, (x0, y0), mask)

        # วาดเส้นขอบ Glass Border บางๆ (Inner/Outer Glow)
        d.rounded_rectangle([x0, y0, x1, y1], radius=44, outline=(255, 255, 255, 120), width=4)

        cx = x0 + cw // 2

        # 1. Badge ด้านบน (Pill Shape)
        badge_w, badge_h = 420, 68
        bx0 = cx - badge_w // 2
        by0 = y0 + 44
        d.rounded_rectangle([bx0, by0, bx0 + badge_w, by0 + badge_h],
                            radius=34, fill=(0, 0, 0, 90), outline=(255, 255, 255, 80), width=2)
        f_badge = load_font(36, "medium")
        bb = d.textbbox((0, 0), item["badge"], font=f_badge)
        d.text((cx - (bb[2] - bb[0]) / 2, by0 + (badge_h - (bb[3] - bb[1])) / 2 - bb[1] - 2),
               item["badge"], fill="#FFFFFF", font=f_badge)

        # 2. วาด Vector Icon โมเดิร์นตรงกลาง
        icon_cy = y0 + 235
        # วงกลมแก้วรอบไอคอน
        d.ellipse([cx - 85, icon_cy - 85, cx + 85, icon_cy + 85],
                  fill=(255, 255, 255, 45), outline=(255, 255, 255, 140), width=3)

        if item["icon_type"] == "search":
            # แว่นขยายทรงโมเดิร์น
            d.ellipse([cx - 45, icon_cy - 48, cx + 22, icon_cy + 19],
                      outline="#FFFFFF", width=9)
            d.line([cx + 12, icon_cy + 12, cx + 46, icon_cy + 46],
                   fill="#FFFFFF", width=12)
            # ประกายแสงวิ้ง
            d.ellipse([cx - 28, icon_cy - 34, cx - 18, icon_cy - 24], fill="#FFFFFF")

        elif item["icon_type"] == "bot":
            # ไอคอนหุ่นยนต์ / ชิปอัจฉริยะ & กระเป๋าธุรกิจ
            d.rounded_rectangle([cx - 42, icon_cy - 38, cx + 42, icon_cy + 40],
                                radius=16, fill="#FFFFFF")
            # ตาหุ่นยนต์
            d.rounded_rectangle([cx - 28, icon_cy - 18, cx - 12, icon_cy + 2], radius=6, fill=item["c_end"])
            d.rounded_rectangle([cx + 12, icon_cy - 18, cx + 28, icon_cy + 2], radius=6, fill=item["c_end"])
            # เสาอากาศ AI
            d.line([cx, icon_cy - 38, cx, icon_cy - 52], fill="#FFFFFF", width=6)
            d.ellipse([cx - 7, icon_cy - 64, cx + 7, icon_cy - 50], fill="#FFFFFF")
            # รอยยิ้ม
            d.arc([cx - 22, icon_cy + 6, cx + 22, icon_cy + 26], start=0, end=180, fill=item["c_end"], width=5)

        elif item["icon_type"] == "chat":
            # กล่องแชททรงโมเดิร์น
            d.rounded_rectangle([cx - 48, icon_cy - 42, cx + 48, icon_cy + 30],
                                radius=20, fill="#FFFFFF")
            # หางแชท
            d.polygon([(cx - 20, icon_cy + 30), (cx - 42, icon_cy + 48), (cx - 6, icon_cy + 30)], fill="#FFFFFF")
            # จุด 3 จุดในแชท
            d.ellipse([cx - 28, icon_cy - 10, cx - 18, icon_cy], fill=item["c_end"])
            d.ellipse([cx - 5, icon_cy - 10, cx + 5, icon_cy], fill=item["c_end"])
            d.ellipse([cx + 18, icon_cy - 10, cx + 28, icon_cy], fill=item["c_end"])

        # 3. Main Title ข้อความหลัก (ตัวหนาคมชัด)
        f_main = load_font(102, "bold")
        bb = d.textbbox((0, 0), item["title"], font=f_main)
        # เงาข้อความ Subtle Drop Shadow
        d.text((cx - (bb[2] - bb[0]) / 2 + 3, y0 + 363 - bb[1]),
               item["title"], fill=(0, 0, 0, 100), font=f_main)
        d.text((cx - (bb[2] - bb[0]) / 2, y0 + 360 - bb[1]),
               item["title"], fill="#FFFFFF", font=f_main)

        # 4. Subtitle คำอธิบายย่อย
        f_sub = load_font(48, "medium")
        bb = d.textbbox((0, 0), item["sub"], font=f_sub)
        d.text((cx - (bb[2] - bb[0]) / 2, y0 + 490 - bb[1]),
               item["sub"], fill="#F8FAFC", font=f_sub)

        # 5. Bottom CTA Button (Pill Button สวยหรู)
        btn_w, btn_h = 580, 100
        btn_x0 = cx - btn_w // 2
        btn_y0 = y1 - 145
        d.rounded_rectangle([btn_x0, btn_y0, btn_x0 + btn_w, btn_y0 + btn_h],
                            radius=50, fill=(255, 255, 255, 240))
        f_cta = load_font(46, "bold")
        bb = d.textbbox((0, 0), item["cta"], font=f_cta)
        d.text((cx - (bb[2] - bb[0]) / 2, btn_y0 + (btn_h - (bb[3] - bb[1])) / 2 - bb[1] - 2),
               item["cta"], fill=item["c_end"], font=f_cta)

    # บันทึกเป็น RGB PNG (LINE API รองรับ standard image/png)
    final_rgb = img.convert("RGB")
    final_rgb.save(path, "PNG", optimize=True)


def api(method: str, path: str, token: str, body=None, headers=None, raw=None, base=None):
    url = f"{(base or API_BASE)}{path}"
    h = {"Authorization": f"Bearer {token}"}
    if body is not None and not isinstance(body, (bytes, bytearray)):
        h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    data = body if isinstance(body, (bytes, bytearray)) else (
        json.dumps(body).encode("utf-8") if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    token = load_token()
    if not token or token.startswith("mock"):
        print("✗ ไม่พบ LINE_CHANNEL_ACCESS_TOKEN (จริง) ใน backend/.env")
        sys.exit(1)

    # 1. ลบ rich menu เก่าทั้งหมด
    st, raw = api("GET", "/richmenu/list", token)
    if st == 200:
        for rm in json.loads(raw).get("richmenus", []):
            rid = rm["richMenuId"]
            s2, _ = api("DELETE", f"/richmenu/{rid}", token)
            print(f"  ลบ rich menu เก่า {rid}: HTTP {s2}")

    # 2. วาด PNG
    png_path = PROJECT_ROOT / "tools" / "rich_menu.png"
    draw_menu(str(png_path))
    print(f"  วาด PNG แล้ว: {png_path} ({png_path.stat().st_size // 1024} KB)")

    # 3. สร้าง rich menu (กำหนดพื้นที่ 3 ปุ่ม)
    areas = []
    for i, item in enumerate(MENU_ITEMS):
        areas.append({
            "bounds": {"x": i * COL_W, "y": 0, "width": COL_W, "height": H},
            "action": {"type": "message", "text": item["send"]},
        })
    body = {
        "size": {"width": W, "height": H},
        "selected": False,
        "name": "menu-pakhem-3",
        "chatBarText": "🛍️ เมนูป้าเข็ม",
        "areas": areas,
    }
    st, raw = api("POST", "/richmenu", token, body=body)
    if st != 200:
        print(f"✗ สร้าง rich menu ล้ม: HTTP {st} {raw.decode()[:200]}")
        sys.exit(1)
    rid = json.loads(raw)["richMenuId"]
    print(f"  สร้าง rich menu: {rid}")

    # 4. อัปโหลดรูป
    st, raw = api("POST", f"/richmenu/{rid}/content", token,
                  body=png_path.read_bytes(),
                  headers={"Content-Type": "image/png"},
                  base=IMAGE_BASE)
    if st != 200:
        print(f"✗ อัปโหลดรูปล้ม: HTTP {st} {raw.decode()[:200]}")
        sys.exit(1)
    print("  อัปโหลดรูป: HTTP 200")

    # 5. ตั้งเป็นค่าเริ่มต้น
    st, raw = api("POST", f"/user/all/richmenu/{rid}", token)
    print(f"  ตั้งเป็นค่าเริ่มต้น: HTTP {st}")
    if st == 200:
        print("\n✅ Rich Menu พร้อมใช้ — ลูกค้าเห็นแถบเมนูด้านล่างทันที (ถ้ายังไม่เห็น ให้กดปุ่ม ▾ ที่ช่องพิมพ์)")


if __name__ == "__main__":
    main()
