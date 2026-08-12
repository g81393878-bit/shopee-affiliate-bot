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

# Pillow ใช้เฉพาะวาดภาพ
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / "backend" / ".env"

API_BASE = "https://api.line.me/v2/bot"
IMAGE_BASE = "https://api-data.line.me/v2/bot"  # อัปโหลดรูป rich menu ใช้ base นี้

MENU_ITEMS = [
    {"label": "ค้นสินค้า", "sub": "พิมพ์ชื่อสินค้า / งบ", "color": "#E74C3C"},
    {"label": "ขายดีวันนี้", "sub": "สินค้าแนะนำประจำวัน", "color": "#F39C12"},
    {"label": "อันดับขายดี", "sub": "3 อันดับยอดขายจริง", "color": "#2ECC71"},
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


def load_font(size: int):
    candidates = [
        r"C:\Windows\Fonts\leelawadeeui.ttf",   # ฟอนต์ไทย Windows
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if pathlib.Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_menu(path: str):
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    for i, item in enumerate(MENU_ITEMS):
        x0 = i * COL_W
        d.rounded_rectangle([x0 + 24, 24, x0 + COL_W - 24, H - 24],
                            radius=48, fill=item["color"])
        # ไอคอนวงกลมขาว
        cx = x0 + COL_W // 2
        cy = H // 2 - 150
        d.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill="#FFFFFF")
        # ตัวเลขในวงกลม
        f_num = load_font(110)
        num = str(i + 1)
        bb = d.textbbox((0, 0), num, font=f_num)
        d.text((cx - (bb[2] - bb[0]) / 2, cy - (bb[3] - bb[1]) / 2 - bb[1]),
               num, fill=item["color"], font=f_num)
        # ป้ายหลัก
        f_main = load_font(120)
        label = item["label"]
        bb = d.textbbox((0, 0), label, font=f_main)
        d.text((cx - (bb[2] - bb[0]) / 2, H // 2 + 40 - bb[1]),
               label, fill="#FFFFFF", font=f_main)
        # ป้ายรอง
        f_sub = load_font(58)
        sub = item["sub"]
        bb = d.textbbox((0, 0), sub, font=f_sub)
        d.text((cx - (bb[2] - bb[0]) / 2, H // 2 + 210 - bb[1]),
               sub, fill="#FFFFFF", font=f_sub)
    img.save(path, "PNG")


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

    # 1. ลบ rich menu เก่าทั้งหมด (ให้สภาพสะอาด)
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
            "action": {"type": "message", "text": item["label"]},
        })
    body = {
        "size": {"width": W, "height": H},
        "selected": False,
        "name": "menu-pakem",
        "chatBarText": "เมนูป้าเข็ม",
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
