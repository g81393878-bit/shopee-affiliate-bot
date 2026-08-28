#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reels_uploader/auto_product_reels.py — สร้างคลิปวิดีโอ Reels 9:16 จากภาพสินค้าในคลังอัตโนมัติ

1. ดึงข้อมูลสินค้า (รูปภาพ, ชื่อ, ราคา, ลิงก์ affiliate) จากฐานข้อมูล (Supabase)
2. สร้างภาพโปสเตอร์ 1080x1920 (9:16) ด้วย Pillow (ดีไซน์สวยงาม มีพื้นหลังเบลอ, ป้ายราคา, ดาวรีวิว)
3. แปลงภาพนิ่งเป็นคลิปวิดีโอ 6 วินาทีด้วย ffmpeg (ใส่เอฟเฟกต์ซูมช้าๆ zoompan)
4. บันทึกไฟล์ลง pending_videos/ พร้อมอัปเดต products.json อัตโนมัติ
"""
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

# บังคับ stdout UTF-8 สำหรับ Windows Console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ตั้งค่า Path
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR.parent / "backend"
TOOLS_DIR = ROOT_DIR.parent / "tools"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(ROOT_DIR))

# โหลด Credential / DATABASE_URL จริงจาก Render หรือ .env
try:
    import render_set_env
    render_set_env.API_KEY = render_set_env.get_api_key()
    items = render_set_env.fetch_env_vars()
    for it in items:
        k, v = render_set_env.decode_env_var(it.get("envVar"))
        if k:
            os.environ[k] = v
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from app.db import SessionLocal
from app import models
from app.services.product_image import fetch_product_image


logger = logging.getLogger(__name__)

PENDING_DIR = ROOT_DIR / "pending_videos"
POSTED_DIR = ROOT_DIR / "posted"
PRODUCTS_JSON = ROOT_DIR / "products.json"

FONT_DIR = Path("C:/Windows/Fonts")
FONT_BOLD = FONT_DIR / "leelawdb.ttf" if (FONT_DIR / "leelawdb.ttf").exists() else FONT_DIR / "tahomabd.ttf"
FONT_REG = FONT_DIR / "leelawad.ttf" if (FONT_DIR / "leelawad.ttf").exists() else FONT_DIR / "tahoma.ttf"

def get_font(font_path: Path, size: int):
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()


def sanitize_filename(name: str) -> str:
    """แปลงชื่อให้ปลอดภัยสำหรับเป็นชื่อไฟล์"""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = clean.replace(" ", "_").strip()
    return clean[:40]


def download_image(url: str) -> Optional[Image.Image]:
    """ดาวน์โหลดรูปภาพจาก URL และแปลงเป็น PIL Image"""
    if not url:
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200 and len(r.content) > 1000:
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            return img
    except Exception as e:
        logger.warning(f"ดาวน์โหลดรูปภาพล้ม ({url[:60]}): {e}")
    return None


def create_product_poster(product_name: str, price: float, rating: float, sales_count: int, img: Image.Image) -> Image.Image:
    """สร้างภาพโปสเตอร์แนวตั้ง 1080x1920 (9:16 Full HD) พร้อมตกแต่งสวยงาม"""
    W, H = 1080, 1920
    canvas = Image.new("RGBA", (W, H), (18, 20, 24, 255))

    # 1. ทำพื้นหลังแบบเบลอ (Blurred Background)
    bg_img = img.copy()
    bg_ratio = max(W / bg_img.width, H / bg_img.height)
    bg_resized = bg_img.resize((int(bg_img.width * bg_ratio), int(bg_img.height * bg_ratio)), Image.Resampling.LANCZOS)
    left = (bg_resized.width - W) // 2
    top = (bg_resized.height - H) // 2
    bg_cropped = bg_resized.crop((left, top, left + W, top + H))
    bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=35))
    
    # Overlay เงาดำให้พื้นหลังมืดลง
    dark_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 140))
    canvas.paste(bg_blurred, (0, 0))
    canvas = Image.alpha_composite(canvas, dark_overlay)

    draw = ImageDraw.Draw(canvas)

    # 2. แถบ Header ด้านบน (ป้าเข็ม ขายของ)
    header_box = Image.new("RGBA", (W, 200), (0, 0, 0, 160))
    canvas.paste(header_box, (0, 0), header_box)
    
    f_header = get_font(FONT_BOLD, 48)
    f_sub = get_font(FONT_REG, 30)
    draw.text((W // 2, 70), "🛍️ ป้าเข็ม คัดของดี ของเด็ด Shopee", font=f_header, fill=(255, 215, 0), anchor="mm")
    draw.text((W // 2, 135), "แท้ 100% • รีวิวแน่น • คุ้มค่าเงินทุกบาท", font=f_sub, fill=(240, 240, 240), anchor="mm")

    # 3. กรอบรูปสินค้าตรงกลาง (พร้อมเงาและขอบขาว)
    target_img_size = 780
    img_ratio = min(target_img_size / img.width, target_img_size / img.height)
    prod_w = int(img.width * img_ratio)
    prod_h = int(img.height * img_ratio)
    prod_resized = img.resize((prod_w, prod_h), Image.Resampling.LANCZOS)

    box_x = (W - prod_w) // 2
    box_y = 260 + (target_img_size - prod_h) // 2

    # วาดกรอบการ์ดสีขาวรองหลัง
    card_padding = 24
    card_box = [box_x - card_padding, box_y - card_padding, box_x + prod_w + card_padding, box_y + prod_h + card_padding]
    draw.rounded_rectangle(card_box, radius=32, fill=(255, 255, 255, 245), outline=(255, 215, 0, 200), width=4)
    canvas.paste(prod_resized, (box_x, box_y), prod_resized)

    # 4. กล่องข้อมูลสินค้าด้านล่าง (ชื่อ + ราคา + ดาว)
    info_top = 1120
    info_box = Image.new("RGBA", (W - 120, 520), (255, 255, 255, 250))
    draw_info = ImageDraw.Draw(info_box)
    draw_info.rounded_rectangle([0, 0, W - 120, 520], radius=32, fill=(255, 255, 255), outline=(238, 77, 45), width=4)

    # ป้ายราคาเด่นๆ (สีส้ม Shopee #EE4D2D)
    f_price_badge = get_font(FONT_BOLD, 64)
    price_str = f"฿{price:,.0f}" if price else "ราคาพิเศษ"
    draw_info.text((50, 70), price_str, font=f_price_badge, fill=(238, 77, 45), anchor="lm")
    
    # ป้ายยอดขาย / ดาว
    f_stat = get_font(FONT_BOLD, 32)
    stat_str = f"⭐ {rating:.1f}  |  ขายแล้ว {sales_count:,} ชิ้น"
    draw_info.text((W - 170, 70), stat_str, font=f_stat, fill=(60, 60, 60), anchor="rm")

    # เส้นคั่น
    draw_info.line([(40, 125), (W - 160, 125)], fill=(220, 220, 220), width=2)

    # ชื่อสินค้า (ตัดคำไม่ให้ล้น)
    f_title = get_font(FONT_BOLD, 40)
    title_lines = []
    curr = ""
    for word in product_name:
        if len(curr) >= 28:
            title_lines.append(curr)
            curr = ""
        curr += word
    if curr:
        title_lines.append(curr)
    title_lines = title_lines[:3]  # สูงสุด 3 บรรทัด

    title_y = 175
    for l in title_lines:
        draw_info.text((50, title_y), l, font=f_title, fill=(20, 20, 20), anchor="lt")
        title_y += 55

    # 5. ปุ่ม CTA ด้านล่างของการ์ด
    cta_rect = [40, 390, W - 160, 480]
    draw_info.rounded_rectangle(cta_rect, radius=20, fill=(238, 77, 45))
    f_cta = get_font(FONT_BOLD, 36)
    draw_info.text(((W - 120) // 2, 435), "👉 ดูรายละเอียด / สั่งซื้อ ที่ลิงก์ในแคปชั่น", font=f_cta, fill=(255, 255, 255), anchor="mm")

    canvas.paste(info_box, (60, info_top), info_box)

    # 6. ท้ายคลิป (Footer)
    f_foot = get_font(FONT_REG, 28)
    draw.text((W // 2, 1780), "สงสัยของแท้ไหม? ทักปรึกษาป้าเข็มได้ที่ LINE: @137gsref", font=f_foot, fill=(200, 200, 200), anchor="mm")

    return canvas.convert("RGB")


def _ffmpeg_exe() -> str:
    """path ffmpeg — ใช้ binary ที่ติดมากับ imageio_ffmpeg (ใน venv) ก่อน fallback เป็น 'ffmpeg' ใน PATH"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def poster_to_video(poster_path: Path, output_video_path: Path, duration: int = 6) -> bool:
    """แปลงภาพนิ่ง poster เป็นวิดีโอ 9:16 พร้อมเอฟเฟกต์ซูมช้าๆ (Ken Burns effect)"""
    ffmpeg_exe = _ffmpeg_exe()
    
    # filter ซูมเข้าอย่างนุ่มนวล (1.0 -> 1.06) ที่ 30fps
    filter_complex = f"zoompan=z='min(zoom+0.0003,1.06)':d={duration*30}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
    
    cmd = [
        ffmpeg_exe, "-y",
        "-loop", "1",
        "-i", str(poster_path),
        "-vf", filter_complex,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_video_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        return output_video_path.exists() and output_video_path.stat().st_size > 1000
    except Exception as e:
        logger.error(f"สร้างวิดีโอจากภาพล้ม: {e}")
        return False



def generate_product_reels(limit: int = 3) -> List[dict]:
    """ดึงสินค้าจากฐานข้อมูลมาสร้างเป็นคลิปวิดีโอ Reels อัตโนมัติ"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    generated = []
    try:
        # อ่าน products.json เดิม
        products_meta = {}
        if PRODUCTS_JSON.exists():
            try:
                products_meta = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
            except Exception:
                products_meta = {}

        # ดึงสินค้าที่สถานะ link_status = 'ok' และมียอดขายดี
        prods = (db.query(models.Product)
                   .filter(models.Product.link_status == "ok",
                           models.Product.sales_count >= 100)
                   .order_by(models.Product.ai_score.desc(),
                             models.Product.sales_count.desc())
                   .limit(limit * 5).all())

        for p in prods:
            if len(generated) >= limit:
                break

            filename = f"prod_{p.id}_{sanitize_filename(p.name)}.mp4"
            target_path = PENDING_DIR / filename
            posted_path = POSTED_DIR / filename

            # ถ้าเคยสร้างหรือโพสต์ไปแล้ว ให้ข้าม
            if target_path.exists() or posted_path.exists():
                continue

            print(f"🎨 กำลังสร้างคลิป Reels ให้สินค้า: {p.name[:40]}...")
            
            # ดึงรูปภาพสินค้า
            img_url = p.image_url
            if not img_url:
                img_url = fetch_product_image(p.affiliate_url or "")
                if img_url:
                    p.image_url = img_url
                    db.commit()

            if not img_url:
                continue

            pil_img = download_image(img_url)
            if not pil_img:
                continue

            # สร้างภาพโปสเตอร์
            poster = create_product_poster(
                product_name=p.name,
                price=float(p.price or 0),
                rating=float(p.rating or 4.9),
                sales_count=int(p.sales_count or 100),
                img=pil_img
            )

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_poster:
                poster.save(tmp_poster.name, format="PNG")
                tmp_poster_path = Path(tmp_poster.name)

            try:
                # แปลงเป็นวิดีโอ 6 วินาที
                if poster_to_video(tmp_poster_path, target_path, duration=6):
                    # บันทึกข้อมูลลง products.json
                    products_meta[filename] = {
                        "product_name": p.name,
                        "price": str(int(p.price or 0)),
                        "category": p.category or "สินค้าแนะนำ",
                        "affiliate_link": p.affiliate_url or ""
                    }
                    generated.append({"id": p.id, "name": p.name, "file": filename})
                    print(f"✅ สร้างคลิปวิดีโอสำเร็จ -> {filename}")
            finally:
                tmp_poster_path.unlink(missing_ok=True)

        # บันทึก products.json
        if generated:
            PRODUCTS_JSON.write_text(json.dumps(products_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    finally:
        db.close()

    return generated


if __name__ == "__main__":
    count = 3
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        count = int(sys.argv[1])
    print(f"🚀 เริ่มต้นสร้างคลิปสินค้าอัตโนมัติ {count} คลิป...")
    res = generate_product_reels(count)
    print(f"🎉 สร้างสำเร็จทั้งหมด {len(res)} คลิป พร้อมสำหรับอัปโหลดลง Reels!")
