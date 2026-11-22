#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตั้ง Rich Menu 6 ช่องพรีเมียม (Full Grid 2500x1686) ให้บอท LINE — ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้
=============================================================================
โครงสร้าง 6 ช่อง (2 แถว x 3 คอลัมน์) โทนอาหารไทยพรีเมียม ส้มทอง-แดง-ขาว:
  [ แถวบน - ปิดการขาย ]
  1. 🐟 สั่งปลาแดดเดียว (รูปถ่ายปลาทอดจริงสีทอง) -> ส่งข้อความ "ปลาแดดเดียว"
  2. 🎁 ชุดยอดฮิต 1 กก. (ชูโปรโมชั่น 290.- ส่งฟรี) -> ส่งข้อความ "สั่งซื้อปลาแดดเดียว 1 กิโลกรัม"
  3. 🛍️ หน้าร้านออนไลน์ (เว็บ D2C สั่งซื้อตรง) -> ลิงก์ URI fish.html
  
  [ แถวล่าง - บริการ & สร้างความมั่นใจ ]
  4. 📦 เช็คสถานะพัสดุ (ส่งรถเย็น / รถด่วน) -> ส่งข้อความ "เช็คพัสดุ"
  5. ❄️ วิธีเก็บรักษา (ซีลสุญญากาศมาตรฐานญี่ปุ่น) -> ส่งข้อความ "วิธีเก็บรักษา"
  6. 💬 คุยกับป้าเข็ม (รูปป้าเข็ม AI ตอบ 24 ชม.) -> ส่งข้อความ "ถามได้ทุกเรื่อง"

รัน:
  backend/.venv/Scripts/python tools/line_rich_menu.py
"""

import json
import pathlib
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / "backend" / ".env"

API_BASE = "https://api.line.me/v2/bot"
IMAGE_BASE = "https://api-data.line.me/v2/bot"

W, H = 2500, 1686
COL_W = W // 3       # 833 (ช่องสุดท้าย 834)
ROW_H = H // 2       # 843

FONT_DIR = PROJECT_ROOT / "tools" / "fonts"
WEB_DIR = PROJECT_ROOT / "backend" / "app" / "static"


def load_token() -> str:
    token = None
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("LINE_CHANNEL_ACCESS_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    return token or ""


def load_font(size: int, weight: str = "bold"):
    fname = "Prompt-Bold.ttf" if weight == "bold" else ("Prompt-Medium.ttf" if weight == "medium" else "Prompt-Regular.ttf")
    fpath = FONT_DIR / fname
    if fpath.exists():
        try:
            return ImageFont.truetype(str(fpath), size)
        except Exception:
            pass
    # Fallback ระบบ Windows
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
    """สร้างภาพ Gradient ไล่เฉียงพรีเมียม"""
    base = Image.new("RGBA", (width, height), start_color)
    top = Image.new("RGBA", (width, height), end_color)
    mask = Image.new("L", (width, height))
    mask_data = []
    for y in range(height):
        for x in range(width):
            p = (y / height) * 0.75 + (x / width) * 0.25
            mask_data.append(int(255 * min(max(p, 0.0), 1.0)))
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base


def make_circular_thumbnail(img_path: pathlib.Path, size: int = 240, border_color=(255, 255, 255), border_width: int = 6) -> Image.Image:
    """ตัดภาพเป็นวงกลมพร้อมเส้นขอบสวยงาม"""
    if not img_path.exists():
        im = Image.new("RGBA", (size, size), (255, 255, 255, 60))
    else:
        im = Image.open(img_path).convert("RGBA")
        w, h = im.size
        min_side = min(w, h)
        left = (w - min_side) // 2
        top = (h - min_side) // 2
        im = im.crop((left, top, left + min_side, top + min_side))
        im = im.resize((size, size), Image.Resampling.LANCZOS)

    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)

    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(im, (0, 0), mask)

    b_draw = ImageDraw.Draw(output)
    bw2 = border_width // 2
    b_draw.ellipse((bw2, bw2, size - bw2, size - bw2), outline=border_color, width=border_width)
    return output


def draw_rich_menu(output_path: str):
    # 1. Background พื้นหลังพรีเมียม Dark Warm Slate
    img = Image.new("RGBA", (W, H), (15, 18, 26, 255))

    # Glow บรรยากาศพื้นหลัง
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.ellipse([-100, -100, 1000, 900], fill=(245, 158, 11, 40))
    g_draw.ellipse([800, -100, 1700, 900], fill=(239, 68, 68, 40))
    g_draw.ellipse([1600, -100, 2600, 900], fill=(249, 115, 22, 40))
    g_draw.ellipse([-100, 800, 1000, 1800], fill=(79, 70, 229, 35))
    g_draw.ellipse([800, 800, 1700, 1800], fill=(13, 148, 136, 35))
    g_draw.ellipse([1600, 800, 2600, 1800], fill=(168, 85, 247, 35))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    fried_fish_path = WEB_DIR / "fried_fish.jpg"
    avatar_path = WEB_DIR / "pa-khem-avatar.png"
    infographic_path = WEB_DIR / "vacuum_seal_infographic.png"

    CARDS = [
        # --- แถวบน (Row 0) : เลือกสั่ง 3 แพ็กเกจชัดเจน ไม่สับสน ---
        {
            "col": 0, "row": 0,
            "badge": "• ชุดที่ 1 : ประมาณ 3–4 ตัว •",
            "title": "ชุด 500 กรัม",
            "sub": "โอน 390.- ส่งฟรี!",
            "cta": "สั่งชุด 500 กรัม  ›",
            "c_start": (245, 158, 11, 255),  # Golden Amber
            "c_end": (180, 83, 9, 255),      # Deep Burnt Gold
            "type": "deal_badge",
            "price": "390.-",
            "deal_sub": "โอนส่งฟรี!"
        },
        {
            "col": 1, "row": 0,
            "badge": "• ชุดที่ 2 : ขายดี (5–7 ตัว) •",
            "title": "ชุด 1 กิโลกรัม",
            "sub": "โอน 550.- ส่งฟรี!",
            "cta": "สั่งชุด 1 กิโลกรัม  ›",
            "c_start": (239, 68, 68, 255),   # Bright Ruby Crimson
            "c_end": (185, 28, 28, 255),     # Deep Wine Red
            "type": "deal_badge",
            "price": "550.-",
            "deal_sub": "โอนส่งฟรี!"
        },
        {
            "col": 2, "row": 0,
            "badge": "• ชุดที่ 3 : สุดคุ้ม (10–14 ตัว) •",
            "title": "ชุด 2 กิโลกรัม",
            "sub": "โอน 1,090.- ส่งฟรีรถห้องเย็น!",
            "cta": "สั่งชุด 2 กิโลกรัม  ›",
            "c_start": (249, 115, 22, 255),  # Vibrant Sunset Orange
            "c_end": (194, 65, 12, 255),     # Deep Rust Amber
            "type": "deal_badge",
            "price": "1,090.-",
            "deal_sub": "ส่งฟรีรถเย็น!"
        },

        # --- แถวล่าง (Row 1) : การจัดส่ง • วิธีเก็บ • เช็คพัสดุ ---
        {
            "col": 0, "row": 1,
            "badge": "1–2 วันซองฟอยล์ | 3–4 วันรถห้องเย็น",
            "title": "เงื่อนไขการจัดส่ง",
            "sub": "1–2 วันรับ COD • 3–4 วันโอนส่งรถเย็น",
            "cta": "ดูเงื่อนไขการส่ง  ›",
            "c_start": (79, 70, 229, 255),   # Royal Indigo
            "c_end": (55, 48, 163, 255),     # Deep Navy Indigo
            "type": "track_icon"
        },
        {
            "col": 1, "row": 1,
            "badge": "ซีลสูญญากาศ • แช่แข็ง ≤-18°C",
            "title": "วิธีเก็บรักษา",
            "sub": "เก็บช่องฟรีซนาน 6–12 เดือน",
            "cta": "ดูวิธีเก็บ & ทอด  ›",
            "c_start": (13, 148, 136, 255),  # Deep Teal / Emerald
            "c_end": (15, 118, 110, 255),    # Dark Sea Green
            "type": "image_thumb",
            "img_path": infographic_path,
            "border_color": (153, 246, 228, 255)
        },
        {
            "col": 2, "row": 1,
            "badge": "ตรวจเลขพัสดุ • เลขบัญชีร้าน",
            "title": "เช็คพัสดุ • เลขบัญชี",
            "sub": "เช็คสถานะส่ง หรือดูเลขบัญชีโอนเงิน",
            "cta": "เช็คพัสดุ / เลขบัญชี  ›",
            "c_start": (168, 85, 247, 255),  # Vivid Purple
            "c_end": (126, 34, 206, 255),    # Deep Royal Plum
            "type": "image_thumb",
            "img_path": avatar_path,
            "border_color": (253, 224, 71, 255)  # Gold Halo
        },
    ]

    for item in CARDS:
        col = item["col"]
        row = item["row"]

        x0 = col * COL_W + 18
        y0 = row * ROW_H + 18
        x1 = (col + 1) * COL_W - (18 if col < 2 else 12)
        y1 = (row + 1) * ROW_H - 18
        cw = x1 - x0
        ch = y1 - y0

        # วาด Gradient Card
        card_img = create_gradient(cw, ch, item["c_start"], item["c_end"])
        mask = Image.new("L", (cw, ch), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, cw, ch], radius=40, fill=255)

        img.paste(card_img, (x0, y0), mask)

        # ขอบ Glass Border
        d.rounded_rectangle([x0, y0, x1, y1], radius=40, outline=(255, 255, 255, 120), width=4)

        cx = x0 + cw // 2

        # 1. Badge ด้านบน
        badge_w, badge_h = 560, 62
        bx0 = cx - badge_w // 2
        by0 = y0 + 36
        d.rounded_rectangle([bx0, by0, bx0 + badge_w, by0 + badge_h],
                            radius=31, fill=(0, 0, 0, 95), outline=(255, 255, 255, 80), width=2)
        f_badge = load_font(30, "medium")
        bb = d.textbbox((0, 0), item["badge"], font=f_badge)
        d.text((cx - (bb[2] - bb[0]) / 2, by0 + (badge_h - (bb[3] - bb[1])) / 2 - bb[1] - 2),
               item["badge"], fill="#FFFFFF", font=f_badge)

        # 2. Thumbnail / Vector Icon
        icon_cy = y0 + 245

        if item["type"] == "image_thumb":
            thumb = make_circular_thumbnail(item["img_path"], size=230,
                                            border_color=item.get("border_color", (255, 255, 255)),
                                            border_width=7)
            img.paste(thumb, (cx - 115, icon_cy - 115), thumb)

        elif item["type"] == "deal_badge":
            # ตราโปรโมชั่น
            circle_r = 115
            d.ellipse([cx - circle_r, icon_cy - circle_r, cx + circle_r, icon_cy + circle_r],
                      fill=(255, 255, 255, 45), outline=(254, 240, 138, 255), width=7)
            d.ellipse([cx - circle_r + 10, icon_cy - circle_r + 10, cx + circle_r - 10, icon_cy + circle_r - 10],
                      fill=item["c_end"])
            p_size = 56 if len(item["price"]) > 5 else 72
            f_price = load_font(p_size, "bold")
            bb = d.textbbox((0, 0), item["price"], font=f_price)
            d.text((cx - (bb[2] - bb[0]) / 2, icon_cy - 44 - bb[1]), item["price"], fill="#FEF08A", font=f_price)

            f_deal = load_font(30, "bold")
            bb = d.textbbox((0, 0), item["deal_sub"], font=f_deal)
            d.text((cx - (bb[2] - bb[0]) / 2, icon_cy + 30 - bb[1]), item["deal_sub"], fill="#FFFFFF", font=f_deal)

        elif item["type"] == "shop_icon":
            # ไอคอนหน้าร้าน / ตะกร้าช้อปปิ้งพรีเมียม
            d.ellipse([cx - 108, icon_cy - 108, cx + 108, icon_cy + 108],
                      fill=(154, 52, 18, 245), outline=(254, 215, 170, 255), width=6)
            # หูหิ้วถุงช้อปปิ้ง
            d.arc([cx - 28, icon_cy - 66, cx + 28, icon_cy - 12], start=180, end=0, fill="#FFFFFF", width=9)
            # ตัวถุงช้อปปิ้ง
            d.rounded_rectangle([cx - 52, icon_cy - 22, cx + 52, icon_cy + 56], radius=14, fill="#FFFFFF")
            # รอยยิ้มบนถุง
            d.arc([cx - 24, icon_cy + 4, cx + 24, icon_cy + 34], start=0, end=180, fill=(194, 65, 12, 255), width=8)

        elif item["type"] == "track_icon":
            # ไอคอนรถส่งของด่วน / รถห้องเย็น
            d.ellipse([cx - 108, icon_cy - 108, cx + 108, icon_cy + 108],
                      fill=(49, 46, 129, 245), outline=(199, 210, 254, 255), width=6)
            # ตู้ทึบห้องเย็น + หัวรถ
            d.rounded_rectangle([cx - 58, icon_cy - 32, cx + 14, icon_cy + 30], radius=10, fill="#FFFFFF")
            d.rounded_rectangle([cx + 12, icon_cy - 12, cx + 58, icon_cy + 30], radius=8, fill="#FFFFFF")
            # หน้าต่างรถ
            d.rounded_rectangle([cx + 20, icon_cy - 5, cx + 48, icon_cy + 12], radius=4, fill=(49, 46, 129, 255))
            # สัญลักษณ์ความเย็น/ด่วนบนตู้รถ
            d.line([cx - 40, icon_cy - 10, cx - 4, icon_cy - 10], fill=(79, 70, 229, 255), width=6)
            d.line([cx - 40, icon_cy + 6, cx - 14, icon_cy + 6], fill=(56, 189, 248, 255), width=6)
            # ล้อรถ
            d.ellipse([cx - 40, icon_cy + 20, cx - 14, icon_cy + 46], fill="#1E293B", outline="#FFFFFF", width=5)
            d.ellipse([cx + 20, icon_cy + 20, cx + 46, icon_cy + 46], fill="#1E293B", outline="#FFFFFF", width=5)

        # 3. Main Title ข้อความหลัก
        f_main = load_font(74, "bold")
        bb = d.textbbox((0, 0), item["title"], font=f_main)
        d.text((cx - (bb[2] - bb[0]) / 2 + 3, y0 + 403 - bb[1]), item["title"], fill=(0, 0, 0, 110), font=f_main)
        d.text((cx - (bb[2] - bb[0]) / 2, y0 + 400 - bb[1]), item["title"], fill="#FFFFFF", font=f_main)

        # 4. Subtitle คำอธิบายย่อย
        f_sub = load_font(38, "medium")
        bb = d.textbbox((0, 0), item["sub"], font=f_sub)
        d.text((cx - (bb[2] - bb[0]) / 2, y0 + 515 - bb[1]), item["sub"], fill="#F8FAFC", font=f_sub)

        # 5. Bottom CTA Button (White Pill)
        btn_w, btn_h = 580, 96
        btn_x0 = cx - btn_w // 2
        btn_y0 = y1 - 138
        d.rounded_rectangle([btn_x0, btn_y0, btn_x0 + btn_w, btn_y0 + btn_h],
                            radius=48, fill=(255, 255, 255, 245))
        f_cta = load_font(42, "bold")
        bb = d.textbbox((0, 0), item["cta"], font=f_cta)
        d.text((cx - (bb[2] - bb[0]) / 2, btn_y0 + (btn_h - (bb[3] - bb[1])) / 2 - bb[1] - 2),
               item["cta"], fill=item["c_end"], font=f_cta)

    final_rgb = img.convert("RGB")
    final_rgb.save(output_path, "PNG", optimize=True)
    print(f"  บันทึกภาพ Rich Menu สำเร็จ: {output_path} ({pathlib.Path(output_path).stat().st_size // 1024} KB)")


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

    # 2. วาด PNG 2500x1686
    png_path = PROJECT_ROOT / "tools" / "rich_menu.png"
    draw_rich_menu(str(png_path))

    # 3. กำหนดพื้นที่ 6 ปุ่ม (2 แถว x 3 คอลัมน์)
    areas = [
        # แถวบน (Row 0) : สั่ง 3 แพ็กเกจชัดเจน (500g / 1kg / 2kg)
        {
            "bounds": {"x": 0, "y": 0, "width": COL_W, "height": ROW_H},
            "action": {"type": "message", "text": "รับชุดพอดีมื้อ 500 กรัม"}
        },
        {
            "bounds": {"x": COL_W, "y": 0, "width": COL_W, "height": ROW_H},
            "action": {"type": "message", "text": "สั่งซื้อปลาแดดเดียว 1 กิโลกรัม"}
        },
        {
            "bounds": {"x": COL_W * 2, "y": 0, "width": W - (COL_W * 2), "height": ROW_H},
            "action": {"type": "message", "text": "สั่งซื้อปลาแดดเดียว 2 กิโลกรัม"}
        },

        # แถวล่าง (Row 1) : เงื่อนไขการจัดส่ง / วิธีเก็บรักษา / เช็คพัสดุ•เลขบัญชี
        {
            "bounds": {"x": 0, "y": ROW_H, "width": COL_W, "height": H - ROW_H},
            "action": {"type": "message", "text": "เงื่อนไขการจัดส่ง"}
        },
        {
            "bounds": {"x": COL_W, "y": ROW_H, "width": COL_W, "height": H - ROW_H},
            "action": {"type": "message", "text": "วิธีเก็บรักษา"}
        },
        {
            "bounds": {"x": COL_W * 2, "y": ROW_H, "width": W - (COL_W * 2), "height": H - ROW_H},
            "action": {"type": "message", "text": "เช็คพัสดุ"}
        },
    ]

    body = {
        "size": {"width": W, "height": H},
        "selected": True,  # เปิดค้างแสดงให้เห็นชัดเจนตลอดเวลา
        "name": "menu-pakhem-6-grid-v1",
        "chatBarText": "👉 แตะเปิดเมนู 🛍️",
        "areas": areas,
    }
    st, raw = api("POST", "/richmenu", token, body=body)
    if st != 200:
        print(f"✗ สร้าง rich menu ล้ม: HTTP {st} {raw.decode()[:200]}")
        sys.exit(1)
    rid = json.loads(raw)["richMenuId"]
    print(f"  สร้าง rich menu 6 ช่องสำเร็จ: {rid}")

    # 4. อัปโหลดรูป
    st, raw = api("POST", f"/richmenu/{rid}/content", token,
                  body=png_path.read_bytes(),
                  headers={"Content-Type": "image/png"},
                  base=IMAGE_BASE)
    if st != 200:
        print(f"✗ อัปโหลดรูปล้ม: HTTP {st} {raw.decode()[:200]}")
        sys.exit(1)
    print("  อัปโหลดภาพขึ้นระบบ LINE: HTTP 200")

    # 5. ตั้งเป็นค่าเริ่มต้นให้ทุกคน
    st, raw = api("POST", f"/user/all/richmenu/{rid}", token)
    print(f"  ตั้งเป็นค่าเริ่มต้นสำหรับทุกคน: HTTP {st}")

    # 6. ลิงก์ตรงให้แอดมิน / ลูกค้าทดสอบ
    admin_uid = "Uc88eb3896b0e4bcc5fbaa9b78ac1294e"
    st_u, _ = api("POST", f"/user/{admin_uid}/richmenu/{rid}", token)
    print(f"  ผูกเมนูตรงกับแอดมิน ({admin_uid}): HTTP {st_u}")

    if st == 200:
        print("\n✅ Rich Menu 6 ช่องพรีเมียมพร้อมใช้งาน 100% — เปิดดูใน LINE ได้ทันทีครับ!")


if __name__ == "__main__":
    main()
