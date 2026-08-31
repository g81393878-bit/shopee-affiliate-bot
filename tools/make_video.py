#!/usr/bin/env python3
"""tools/make_video.py — สร้างคลิปสั้นแบบสไลด์ (9:16) จากไฟล์คอนเทนต์ป้าเข็ม

อ่านไฟล์ CSV คอนเทนต์ (Hook/แคปชัน/ยอดขาย) → สร้างคลิป .mp4:
  - ตัวหนังสือ Hook ใหญ่ + เสียงอ่านไทย (edge-tts)
  - ยอดขาย + การ์ดท้ายชวนดูราคาล่าสุดที่ลิงก์

วิธีใช้:
  python tools/make_video.py --top 5          # สร้างคลิป 5 ตัวแรกที่ขายดีสุด
  python tools/make_video.py --id 123         # สร้างคลิปของสินค้า id นั้น
  python tools/make_video.py --csv <path> --top 3

ต้องติดตั้ง: pip install moviepy edge-tts imageio-ffmpeg pillow
"""
import argparse
import asyncio
import csv
import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

from app.services.product_price_policy import sanitize_public_product_text

CSV_DEFAULT = r"D:\คอนเทนต์ป้าเข็ม_20260812.csv"
OUT_DIR = r"D:\คลิปป้าเข็ม"
FONT = r"C:\Windows\Fonts\leelawadeeui.ttf"
FONT_BOLD = r"C:\Windows\Fonts\leelawadeeuibold.ttf"
VOICE = "th-TH-PremwadeeNeural"   # เสียงผู้หญิงไทย

W, H = 720, 1280                 # 9:16 (720p พอสำหรับ TikTok)
FPS = 20
END_CARD_SEC = 3.5               # การ์ดท้าย (วินาที)


# ---------- ฟอนต์ ----------
_font_cache = {}
def font(size, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        path = FONT_BOLD if bold else FONT
        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except OSError:
            _font_cache[key] = ImageFont.truetype("C:/Windows/Fonts/tahoma.ttf", size)
    return _font_cache[key]


def wrap_thai(draw, text, font, max_w):
    """ตัดบรรทัดตามความกว้าง (กันคำไทยตกกลางบรรทัดไม่ต้องเป๊ะ แต่พอสวย)"""
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


# ---------- พื้นหลังไล่สี + องค์ประกอบ ----------
def base_bg():
    top, bottom = hex_to_rgb("FF6B6B"), hex_to_rgb("B24592")   # ชมพู→ม่วง
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        c = lerp_color(top, bottom, y / H)
        for x in range(0, W, 8):
            for xx in range(x, min(x + 8, W)):
                px[xx, y] = c
    return img


def draw_rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def fmt_num(n):
    try:
        n = int(float(n))
        if n >= 1000000:
            return f"{n/1000000:.1f} ล้าน"
        if n >= 1000:
            return f"{n/1000:.0f}K"
        return f"{n:,}"
    except (TypeError, ValueError):
        return str(n)


def render_hook_frame(product, t, dur):
    """เฟรมสไลด์ Hook — มีซูมเบาๆ เพื่อไม่ให้ภาพนิ่งจนเกินไป"""
    z = 1.0 + 0.05 * (t / max(dur, 0.01))
    img = base_bg()

    # ป้ายแบรนด์
    draw = ImageDraw.Draw(img)
    chip = (int(W * 0.10), 70, int(W * 0.90), 128)
    draw_rounded(draw, chip, 29, (255, 255, 255, 0))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(chip, radius=29, fill=(255, 255, 255, 40))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    brand = "ป้าเข็ม ขายของ 💕"
    bf = font(30, bold=True)
    draw.text((W // 2, 99), brand, font=bf, fill=(255, 255, 255), anchor="mm")

    # Hook ตัวหนังสือใหญ่
    hook = sanitize_public_product_text(product.get("Hook") or product.get("สินค้า", ""))
    hf = font(52, bold=True)
    max_w = int(W * 0.86)
    lines = wrap_thai(draw, hook, hf, max_w)
    line_h = 66
    start_y = 330 - (len(lines) - 1) * line_h // 2
    for i, ln in enumerate(lines):
        draw.text((W // 2, start_y + i * line_h), ln, font=hf,
                  fill=(255, 255, 255), anchor="mm",
                  stroke_width=4, stroke_fill=(90, 20, 60))

    # กรอบข้อมูลสินค้า — ราคาสดให้ดูใน Shopee เท่านั้น
    pf = font(34, bold=True)
    sf = font(30)
    sales = fmt_num(product.get("ยอดขาย", 0))
    panel = (int(W * 0.08), H - 430, int(W * 0.92), H - 250)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(panel, radius=26, fill=(0, 0, 0, 90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    lines1 = "🏷️ ดูราคาล่าสุดใน Shopee"
    lines2 = f"🔥 ขายแล้ว {sales} ชิ้น"
    draw.text((W // 2, H - 390), lines1, font=pf, fill=(255, 220, 120), anchor="mm")
    draw.text((W // 2, H - 325), lines2, font=sf, fill=(255, 255, 255), anchor="mm")

    # แถบความคืบ
    bar_w = int(W * 0.72)
    bx = (W - bar_w) // 2
    by = H - 170
    draw.rounded_rectangle((bx, by, bx + bar_w, by + 12), radius=6, fill=(255, 255, 255, 60))
    prog = int(bar_w * min(t / max(dur, 0.01), 1.0))
    if prog > 2:
        draw.rounded_rectangle((bx, by, bx + prog, by + 12), radius=6, fill=(255, 220, 120))
    draw.text((W // 2, by + 40), "👇 กดลิงก์ด้านล่าง มาแชทกับป้าเข็มได้เลยจ๊ะ",
              font=font(26), fill=(255, 255, 255), anchor="mm")

    # ซูมแบบ crop กลาง
    nw, nh = int(W * z), int(H * z)
    img = img.resize((nw, nh), Image.LANCZOS)
    x0, y0 = (nw - W) // 2, (nh - H) // 2
    return np.array(img.crop((x0, y0, x0 + W, y0 + H)))


def render_end_frame(product):
    img = base_bg()
    draw = ImageDraw.Draw(img)

    # สินค้า
    name = sanitize_public_product_text(product.get("สินค้า", ""))
    nf = font(34, bold=True)
    max_w = int(W * 0.84)
    lines = wrap_thai(draw, name, nf, max_w)
    y = 380
    for ln in lines:
        draw.text((W // 2, y), ln, font=nf, fill=(255, 255, 255), anchor="mm", stroke_width=3, stroke_fill=(90, 20, 60))
        y += 50

    # ราคาไม่แสดงตัวเลข เพราะเปลี่ยนตามตัวเลือก/โปรโมชัน
    pf = font(48, bold=True)
    sales = fmt_num(product.get("ยอดขาย", 0))
    draw.text((W // 2, 560), "🏷️ ดูราคาล่าสุดใน Shopee", font=pf, fill=(255, 220, 120), anchor="mm")
    draw.text((W // 2, 650), f"🔥 ขายแล้ว {sales} ชิ้น", font=font(32), fill=(255, 255, 255), anchor="mm")

    # ปุ่ม CTA
    btn = (int(W * 0.14), 820, int(W * 0.86), 940)
    draw.rounded_rectangle(btn, radius=60, fill=(255, 255, 255))
    draw.text((W // 2, 880), "สั่งซื้อผ่านลิงก์ใน BIO", font=font(38, bold=True), fill=(178, 69, 146), anchor="mm")

    draw.text((W // 2, 1030), "ป้าเข็ม ขายของ 💕", font=font(34, bold=True), fill=(255, 255, 255), anchor="mm")
    draw.text((W // 2, 1100), "ของดีคัดให้แล้ว · ราคาสุดท้ายดูใน Shopee", font=font(26), fill=(255, 240, 245), anchor="mm")
    return np.array(img)


def read_products(csv_path):
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        if not (r.get("Hook") or "").strip():
            continue
        out.append(r)
    # เรียงยอดขายจากมากไปน้อย (ของดีก่อน)
    def sales_key(r):
        try:
            return float((r.get("ยอดขาย") or "0").replace(",", ""))
        except ValueError:
            return 0.0
    out.sort(key=sales_key, reverse=True)
    return out


def find_by_id(products, pid):
    for r in products:
        if str(r.get("id", "")).strip() == str(pid).strip():
            return r
    return None


def make_voice_text(product):
    parts = [sanitize_public_product_text(product.get("Hook", ""))]
    cta = (product.get("CTA") or "").strip()
    if cta and cta not in parts[0]:
        parts.append(cta)
    parts.append("ดูราคาล่าสุดและโปรโมชันได้ในลิงก์ Shopee จ้ะ")
    return " ".join(parts)


async def tts(text, path):
    import edge_tts
    tts_obj = edge_tts.Communicate(text, VOICE, rate="-5%")
    await tts_obj.save(path)


def make_video(product, out_path, tmpdir):
    from moviepy import VideoClip, AudioFileClip, concatenate_videoclips

    old_cwd = os.getcwd()
    os.chdir(tmpdir)   # กัน moviepy สร้างไฟล์ temp เกลื่อนโฟลเดอร์โปรเจกต์
    try:
        return _make_video_inner(product, out_path, tmpdir, VideoClip, AudioFileClip, concatenate_videoclips)
    finally:
        os.chdir(old_cwd)


def _make_video_inner(product, out_path, tmpdir, VideoClip, AudioFileClip, concatenate_videoclips):

    hook = product.get("Hook", "")
    name = (product.get("สินค้า") or "")[:40]
    print(f"▶ {name}")

    # 1) เสียง
    mp3 = os.path.join(tmpdir, "voice.mp3")
    asyncio.run(tts(make_voice_text(product), mp3))
    audio = AudioFileClip(mp3)

    # 2) ความยาว
    hook_dur = audio.duration + 1.2
    total = hook_dur + END_CARD_SEC

    # 3) เฟรมสไลด์ Hook (ซูม)
    hook_clip = VideoClip(
        lambda t: render_hook_frame(product, t, hook_dur),
        duration=hook_dur,
    ).with_fps(FPS)
    end_clip = VideoClip(
        lambda t: render_end_frame(product),
        duration=END_CARD_SEC,
    ).with_fps(FPS)

    video = concatenate_videoclips([hook_clip, end_clip], method="compose")
    video = video.with_audio(audio)

    video.write_videofile(
        out_path, fps=FPS, codec="libx264", audio_codec="aac",
        preset="medium", threads=4, logger=None,
    )
    print(f"  ✓ {os.path.basename(out_path)}  ({total:.0f} วินาที)")


def main():
    ap = argparse.ArgumentParser(description="สร้างคลิปสั้นจากคอนเทนต์ป้าเข็ม")
    ap.add_argument("--csv", default=CSV_DEFAULT)
    ap.add_argument("--id", type=int, help="สร้างคลิปของสินค้า id นี้")
    ap.add_argument("--top", type=int, default=1, help="สร้าง N ตัวแรกที่ขายดีสุด")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()

    products = read_products(args.csv)
    if not products:
        print("ไม่พบสินค้าที่มี Hook ใน CSV:", args.csv)
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    targets = []
    if args.id is not None:
        p = find_by_id(products, args.id)
        if not p:
            print(f"ไม่พบสินค้า id {args.id}")
            sys.exit(1)
        targets = [p]
    else:
        targets = products[: args.top]

    print(f"สินค้าทั้งหมด {len(products)} ตัว → สร้าง {len(targets)} คลิป")

    with tempfile.TemporaryDirectory(prefix="video_") as tmp:
        for p in targets:
            pid = p.get("id", "?")
            short = (p.get("สินค้า") or "สินค้า")[:24].replace("/", "-").replace("\\", "-")
            out = os.path.join(args.out, f"คลิป_{pid}_{short}.mp4")
            try:
                make_video(p, out, tmp)
            except Exception as e:
                print(f"  ✗ {pid} ล้ม: {e}")


if __name__ == "__main__":
    main()
