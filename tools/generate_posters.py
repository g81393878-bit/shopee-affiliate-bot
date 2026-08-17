#!/usr/bin/env python3
"""tools/generate_posters.py — สร้างภาพโปสเตอร์โปรโมทบอทป้าเข็ม (Pillow)

สร้างโปสเตอร์แบรนด์ลงโฟลเดอร์ assets (default D:\\Shopee_Web_Scraping\\assets)
แล้วบอท bot/post_page.py จะสุ่มหยิบภาพจากโฟลเดอร์นั้นไปโพสต์ (ข้าม avatar/icon)

วิธีใช้:
  python tools/generate_posters.py                          # เขียนลง D:\\Shopee_Web_Scraping\\assets
  python tools/generate_posters.py --out "D:\\path\\assets"  # ระบุโฟลเดอร์เอง

แก้ข้อความ/สีได้ที่ POSTERS ด้านล่าง (สีตรงกับการ์ดแพ็กเกจ LINE เดียวกัน)
"""
import argparse
import sys
from pathlib import Path

# กัน UnicodeEncodeError (emoji ✅) บน console ฝั่ง Windows ที่ใช้ cp874
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

# สีตามการ์ดแพ็กเกจ LINE (Lean/Starter/Business/White-Label) — แบรนด์เดียวกัน
POSTERS = [
    {
        "title": "บอทป้าเข็ม",
        "tagline": "ผู้ช่วยขายของ Shopee\nให้แม่ค้าออนไลน์",
        "cta": "เริ่มต้น 490.-",
        "color": "#F5A623",
        "file": "บอทป้าเข็ม-ผู้ช่วยขายของ.png",
    },
    {
        "title": "ตอบแชท 24 ชม.",
        "tagline": "AI เข้าใจภาษาไทย\nจำความชอบลูกค้า",
        "cta": "ไม่ต้องเฝ้าแชทเอง",
        "color": "#2ECC71",
        "file": "บอทป้าเข็ม-ตอบแชท.png",
    },
    {
        "title": "หาคนซื้อให้",
        "tagline": "ส่องโพสต์คนอยากซื้อ\nจับคู่สินค้าจากคลัง",
        "cta": "โพสต์อัตโนมัติ",
        "color": "#3498DB",
        "file": "บอทป้าเข็ม-หาคนซื้อ.png",
    },
    {
        "title": "เริ่มต้น 490.-/เดือน",
        "tagline": "มีแพ็กเกจให้เลือก\nตามขนาดร้าน",
        "cta": "แอดไลน์ @137gsref",
        "color": "#9B59B6",
        "file": "บอทป้าเข็ม-แพ็กเกจ.png",
    },
]

W, H = 1080, 1350  # 4:5 portrait — เหมาะ feed Facebook
BRAND = "ป้าเข็ม ขายของ"
FONT_DIR = Path("C:/Windows/Fonts")
FONT_BOLD = FONT_DIR / "tahomabd.ttf"
FONT_REG = FONT_DIR / "tahoma.ttf"


def _hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _shift(c, amt):
    return tuple(max(0, min(255, x + amt)) for x in c)


def _fit_font(draw, text, path, max_size, max_width):
    size = max_size
    while size > 20:
        font = ImageFont.truetype(str(path), size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4
    return ImageFont.truetype(str(path), 20)


def _center(draw, text, font):
    return (W - draw.textlength(text, font=font)) / 2


def _draw_line(draw, text, y, font, fill=(255, 255, 255), shadow=True):
    x = _center(draw, text, font)
    if shadow:
        draw.text((x + 5, y + 5), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)
    return draw.textbbox((x, y), text, font=font)[3]


def _draw_pill(draw, text, cy, font, text_fill):
    tw = draw.textlength(text, font=font)
    bb = draw.textbbox((0, 0), text, font=font)
    th = bb[3] - bb[1]
    pad_x, pad_y = 64, 26
    x0, x1 = (W - tw) / 2 - pad_x, (W + tw) / 2 + pad_x
    y0 = cy - th / 2 - pad_y
    y1 = cy + th / 2 + pad_y
    draw.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) / 2, fill=(255, 255, 255))
    draw.text(((W - tw) / 2, cy - th / 2), text, font=font, fill=text_fill)


def make_poster(spec: dict, out_dir: Path) -> Path:
    base = _hex_rgb(spec["color"])
    dark, light = _shift(base, -70), _shift(base, 50)

    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=_lerp(dark, light, y / H))

    # แบรนด์ (บน)
    f_brand = ImageFont.truetype(str(FONT_REG), 46)
    _draw_line(d, BRAND, 120, f_brand, fill=_shift(base, 160))

    # หัวข้อ (กลางบน) — auto-fit กันข้อความยาวเกิน
    f_title = _fit_font(d, spec["title"], FONT_BOLD, 150, W - 120)
    y = 500 - (150 - f_title.size) / 2
    _draw_line(d, spec["title"], y, f_title)

    # tagline (กลาง)
    f_tag = ImageFont.truetype(str(FONT_REG), 68)
    y = 690
    for line in spec["tagline"].split("\n"):
        y = _draw_line(d, line, y, f_tag, fill=(245, 245, 245), shadow=False) + 30

    # CTA (ล่าง) — ปุ่มขาว ตัวหนังสือสีแบรนด์
    f_cta = _fit_font(d, spec["cta"], FONT_BOLD, 64, W - 200)
    _draw_pill(d, spec["cta"], 1180, f_cta, base)

    out = out_dir / spec["file"]
    img.save(out, "PNG")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="สร้างภาพโปสเตอร์โปรโมทบอทป้าเข็ม (Pillow)")
    ap.add_argument("--out", default=r"D:\Shopee_Web_Scraping\assets",
                    help="โฟลเดอร์ปลายทาง (default D:\\Shopee_Web_Scraping\\assets)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for spec in POSTERS:
        out = make_poster(spec, out_dir)
        print(f"✅ {out.name}")
    print(f"สร้างครบ {len(POSTERS)} ภาพ → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
