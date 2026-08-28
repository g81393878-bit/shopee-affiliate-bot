#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reels_uploader/auto_product_reels.py — สร้างคลิปวิดีโอ Reels 9:16 จากภาพสินค้าพร้อมเสียงพากย์ภาษาไทย (TTS) คุณภาพสูง

1. ดึงข้อมูลสินค้า (รูปภาพ, ชื่อ, ราคา, ลิงก์ affiliate) จากฐานข้อมูล (Supabase)
2. กรองและตัดคำซ้ำ/รหัสต่างดาว/emoji ขยะออกจากชื่อสินค้า
3. สร้างเสียงพากย์ภาษาไทย (Thai TTS) ลื่นไหล เป็นธรรมชาติ 100% ไม่พูดซ้ำ
4. สร้างภาพโปสเตอร์ 1080x1920 (9:16) ด้วย Pillow (ไม่มีตัวอักษรขยะหรือเต้าหู้)
5. รวมภาพและเสียงเป็นคลิปวิดีโอ Reels ความยาวพอดีกับเสียงพากย์ (~6-8 วิ)
"""
import asyncio
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

import edge_tts
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


def _hex_to_rgb(hex_str: str, default: tuple = (238, 77, 45)) -> tuple:
    """แปลงสี Hex เป็น RGB Tuple"""
    hex_clean = (hex_str or "").strip().lstrip("#")
    if len(hex_clean) == 6:
        try:
            return tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return default


def get_font(font_path: Path, size: int):
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()


def clean_display_text(text: str) -> str:
    """กรองข้อความสำหรับแสดงบนภาพโปสเตอร์ — ลบ emoji และอักขระต่างดาวทั้งหมด"""
    if not text:
        return ""
    # 1. ลบ tag / bracket ขยะ เช่น [ซื้อ 4 แถม 2], 【แท้ 100%】, (พร้อมส่ง)
    t = re.sub(r'\[[^\]]*\]|\([^\)]*\)|【[^】]*】', ' ', text)
    # 2. เก็บเฉพาะภาษาไทย ภาษาอังกฤษ ตัวเลข และเครื่องหมายวรรคตอนพื้นฐาน
    t = re.sub(r'[^\u0E00-\u0E7Fa-zA-Z0-9\s.,/%+\-()]', '', t)
    # 3. จัดการสระอำ
    t = t.replace('\u0e4d\u0e32', '\u0e33').replace('\u0e4d\u0e33', '\u0e33')
    # 4. ลบช่องว่างซ้ำซ้อน
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def sanitize_filename(name: str, max_len: int = 40) -> str:
    """แปลงชื่อสินค้าให้เป็นชื่อไฟล์ที่ปลอดภัย"""
    clean = clean_display_text(name)
    clean = re.sub(r'[\\/*?:"<>|]', "", clean)
    clean = re.sub(r'\s+', "_", clean)
    return clean[:max_len].strip("_")


def download_image(url: str) -> Optional[Image.Image]:
    """ดาวน์โหลดรูปภาพสินค้าจาก URL แปลงเป็น PIL Image"""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        if r.status_code == 200 and len(r.content) > 1000:
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            return img
    except Exception as e:
        logger.warning(f"ดาวน์โหลดรูปภาพล้ม ({url[:60]}): {e}")
    return None


def build_voice_script(product_name: str, price: float, category: str, seed_id: int = 0) -> str:

    """สร้างบทพูดสั้นกระชับ หลากหลายมุมมอง ไม่ซ้ำซาก สไตล์ป้าเข็ม"""
    bot_name = os.getenv("BOT_NAME", "ป้าเข็ม")
    
    # 1. กรองข้อความขยะ
    clean_name = clean_display_text(product_name)
    clean_name = re.sub(r'\b[A-Za-z0-9_-]{1,8}\b', '', clean_name)
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()

    # 2. ลบคำที่ซ้ำกัน
    words = clean_name.split()
    clean_words = []
    for w in words:
        if not clean_words or (w not in clean_words[-1] and clean_words[-1] not in w):
            clean_words.append(w)

    short_title = " ".join(clean_words[:4]).strip()
    if not short_title:
        short_title = category if category else "สินค้าคุณภาพดี"

    # 6 สไตล์บทพูดที่หลากหลาย ไม่ซ้ำกัน (ไม่พูดคำว่าราคา ตามกฎเหล็ก)
    scripts = [
        f"สวัสดีจ้า วันนี้ {bot_name} มาป้ายยา {short_title} ตัวนี้ยอดฮิต รีวิวแน่นมาก ของแท้คุณภาพดี กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะลูก",
        f"ใครกำลังมองหา {short_title} อยู่ {bot_name} แนะนำตัวนี้เลยจ้า คัดของแท้มาให้แล้ว มีโปรคุ้มๆ สั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะ",
        f"สวัสดีจ้า {bot_name} ชี้เป้า {short_title} ไอเทมเด็ดที่ต้องมีติดบ้าน การันตีของแท้ รีวิวดีมาก กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
        f"มีตัวนี้แล้วชีวิตสะดวกขึ้นเยอะเลยลูก {bot_name} แนะนำ {short_title} งานดีมีคุณภาพ ของแท้ร้านทางการ กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะลูก",
        f"ของดีบอกต่อจ้า {bot_name} คัด {short_title} ยอดขายปัง รีวิวแน่น การันตีของแท้ร้อยเปอร์เซ็นต์ ช้อปได้ที่ลิงก์ในแคปชั่นนะลูก",
        f"สวัสดีจ้า {bot_name} รวมของใช้สุดคุ้มมาให้แล้ว แนะนำ {short_title} ของแท้แน่นอน ใช้งานทนทาน กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะลูก",
    ]
    return scripts[seed_id % len(scripts)]


def clean_for_tts(text: str) -> str:
    """กรองให้เหลือเฉพาะตัวอักษรและตัวเลข เพื่อให้ TTS อ่านได้อย่างลื่นไหล ไม่ error"""
    text = re.sub(r'[\+\-\*\/\\&%#@!\?=\(\)\[\]\{\}\<\>_\|~^]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def _tts_save(text: str, output_path: str, voice: str = "th-TH-PremwadeeNeural"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_tts_audio(text: str, output_path: Path) -> bool:
    """สร้างไฟล์เสียงพากย์ผู้หญิง (ป้าเข็ม) ภาษาไทย ให้เสียงเป็นโทนเดียวกัน 100% ทุกคลิป ไม่เปลี่ยนเสียงไปมา"""
    clean_text = clean_for_tts(text)
    
    # 1. ใช้ Google Thai Female Voice เป็นโมเดลเสียงหลักประจำตัวป้าเข็ม (คงเส้นคงวา 100% ทุกคลิป)
    try:
        from gtts import gTTS
        raw_tmp = output_path.with_suffix(".raw.mp3")
        tts = gTTS(text=clean_text, lang="th")
        tts.save(str(raw_tmp))
        
        ffmpeg_exe = _ffmpeg_exe()
        # ปรับความเร็ว 1.28x และความดัง 1.3x ให้กระฉับกระเฉง สดใส เสียงเดียวกันเป๊ะทุกคลิป
        cmd = [ffmpeg_exe, "-y", "-i", str(raw_tmp), "-filter:a", "atempo=1.28,volume=1.3", str(output_path)]
        subprocess.run(cmd, check=True, capture_output=True)
        raw_tmp.unlink(missing_ok=True)
        
        if output_path.exists() and output_path.stat().st_size > 500:
            return True
    except Exception as e:
        logger.warning(f"สร้างเสียงพากย์หลักล้ม: {e}")

    # 2. สำรองกรณีฉุกเฉินด้วย Edge TTS
    try:
        asyncio.run(_tts_save(clean_text, str(output_path), voice="th-TH-PremwadeeNeural"))
        if output_path.exists() and output_path.stat().st_size > 500:
            return True
    except Exception:
        pass

    return False


def get_audio_duration(audio_path: Path) -> float:
    """วัดความยาวไฟล์เสียงจริงด้วย ffmpeg เพื่อเรนเดอร์วิดีโอให้ยาวพอดี ไม่ตัดเสียง"""
    try:
        ffmpeg_exe = _ffmpeg_exe()
        cmd = [ffmpeg_exe, "-i", str(audio_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if m:
            h, mn, s = m.groups()
            return int(h) * 3600 + int(mn) * 60 + float(s)
    except Exception:
        pass
    return 5.0


def wrap_thai_lines(text: str, max_chars_per_line: int = 25, max_lines: int = 3) -> List[str]:
    """ตัดบรรทัดชื่อสินค้าด้วย PyThaiNLP ตามหลักพจนานุกรม ไม่ตัดกลางคำหรือสระลอยเด็ดขาด 100%"""
    try:
        from pythainlp import word_tokenize
        tokens = word_tokenize(text, engine="newmm")
    except Exception:
        tokens = text.split()

    lines = []
    curr = ""
    for tok in tokens:
        if not curr:
            curr = tok
        elif len(curr) + len(tok) <= max_chars_per_line:
            curr += tok
        else:
            lines.append(curr.strip())
            curr = tok
    if curr:
        lines.append(curr.strip())
    return [l for l in lines if l][:max_lines]


def create_product_posters_multiphase(product_name: str, price: float, rating: float, sales_count: int, img: Image.Image, seed_id: int = 0) -> List[Image.Image]:
    """สร้างภาพโปสเตอร์ 3 จังหวะ พร้อมหมุนเวียน 5 ธีมสีและข้อความ ไม่ซ้ำซาก"""
    W, H = 1080, 1920
    bot_name = clean_display_text(os.getenv("BOT_NAME", "ป้าเข็ม ขายของ"))
    clean_pname = clean_display_text(product_name)

    # 1. ทำพื้นหลังแบบเบลอ (Blurred Background)
    bg_img = img.copy()
    bg_ratio = max(W / bg_img.width, H / bg_img.height)
    bg_resized = bg_img.resize((int(bg_img.width * bg_ratio), int(bg_img.height * bg_ratio)), Image.Resampling.LANCZOS)
    left = (bg_resized.width - W) // 2
    top = (bg_resized.height - H) // 2
    bg_cropped = bg_resized.crop((left, top, left + W, top + H))
    bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=35))
    dark_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 140))
    base_bg = Image.alpha_composite(bg_blurred, dark_overlay)

    # 2. กรอบรูปสินค้าตรงกลาง
    target_img_size = 760
    img_ratio = min(target_img_size / img.width, target_img_size / img.height)
    prod_w = int(img.width * img_ratio)
    prod_h = int(img.height * img_ratio)
    prod_resized = img.resize((prod_w, prod_h), Image.Resampling.LANCZOS)
    box_x = (W - prod_w) // 2
    box_y = 280 + (target_img_size - prod_h) // 2
    card_padding = 20
    card_box = [box_x - card_padding, box_y - card_padding, box_x + prod_w + card_padding, box_y + prod_h + card_padding]

    # 5 ธีมสีและข้อความไฮไลท์ หมุนเวียนสร้างความสดใหม่
    theme_idx = seed_id % 5
    themes = [
        # Theme 0: Gold & Vibrant Orange (ป้ายยาของเด็ด)
        {
            "badge": "ของแท้ 100%",
            "brand_col": (238, 77, 45),
            "p1_top_bg": (255, 215, 0), "p1_border": (238, 77, 45), "p1_text": "ป้ายยาของเด็ด • Shopee แท้ 100%!", "p1_text_col": (0, 0, 0),
            "p2_top_bg": (238, 77, 45), "p2_border": (255, 215, 0), "p2_text": f"ของแท้ คุณภาพดี รีวิวแน่น (คะแนน {rating:.1f})", "p2_text_col": (255, 255, 255),
            "p3_top_bg": (16, 185, 129), "p3_border": (255, 255, 255), "p3_text": "พิกัดของแท้ กดลิงก์ในแคปชั่นได้เลย!", "p3_text_col": (255, 255, 255),
        },
        # Theme 1: Emerald Green & Gold (ไอเทมยอดฮิต)
        {
            "badge": "ไอเทมยอดฮิต",
            "brand_col": (5, 150, 105),
            "p1_top_bg": (16, 185, 129), "p1_border": (255, 215, 0), "p1_text": "ชี้เป้าของดี • คัดมาให้แล้ว!", "p1_text_col": (255, 255, 255),
            "p2_top_bg": (255, 215, 0), "p2_border": (5, 150, 105), "p2_text": f"ยอดสั่งซื้อปัง การันตีคุณภาพ (คะแนน {rating:.1f})", "p2_text_col": (0, 0, 0),
            "p3_top_bg": (5, 150, 105), "p3_border": (255, 255, 255), "p3_text": "สั่งซื้อของแท้ กดลิงก์ในแคปชั่นเลยลูก!", "p3_text_col": (255, 255, 255),
        },
        # Theme 2: Deep Indigo & Coral (ของดีบอกต่อ)
        {
            "badge": "รีวิว 5 ดาว",
            "brand_col": (79, 70, 229),
            "p1_top_bg": (255, 237, 213), "p1_border": (79, 70, 229), "p1_text": "ของดีบอกต่อ • คุ้มค่าน่าใช้!", "p1_text_col": (79, 70, 229),
            "p2_top_bg": (79, 70, 229), "p2_border": (255, 215, 0), "p2_text": f"ของแท้ร้านทางการ รีวิวแน่น (คะแนน {rating:.1f})", "p2_text_col": (255, 255, 255),
            "p3_top_bg": (238, 77, 45), "p3_border": (255, 255, 255), "p3_text": "พิกัดของแท้ กดลิงก์ในแคปชั่นได้เลย!", "p3_text_col": (255, 255, 255),
        },
        # Theme 3: Crimson Red & White (สินค้าขายดี)
        {
            "badge": "สินค้าขายดี",
            "brand_col": (220, 38, 38),
            "p1_top_bg": (220, 38, 38), "p1_border": (255, 255, 255), "p1_text": "สินค้าขายดี • ยอดสั่งซื้อแน่น!", "p1_text_col": (255, 255, 255),
            "p2_top_bg": (254, 240, 138), "p2_border": (220, 38, 38), "p2_text": f"ของแท้ คุณภาพพรีเมียม (คะแนน {rating:.1f})", "p2_text_col": (0, 0, 0),
            "p3_top_bg": (16, 185, 129), "p3_border": (255, 255, 255), "p3_text": "สั่งซื้อของแท้ กดลิงก์ในแคปชั่นเลยลูก!", "p3_text_col": (255, 255, 255),
        },
        # Theme 4: Teal & Amber (ป้าเข็มคัดให้)
        {
            "badge": "ป้าเข็มคัดให้",
            "brand_col": (13, 148, 136),
            "p1_top_bg": (254, 215, 170), "p1_border": (13, 148, 136), "p1_text": "ป้าเข็มคัดให้ • ต้องมีติดบ้าน!", "p1_text_col": (13, 148, 136),
            "p2_top_bg": (13, 148, 136), "p2_border": (255, 215, 0), "p2_text": f"คุณภาพดี ใช้งานคุ้มค่า (คะแนน {rating:.1f})", "p2_text_col": (255, 255, 255),
            "p3_top_bg": (238, 77, 45), "p3_border": (255, 255, 255), "p3_text": "พิกัดของแท้ กดลิงก์ในแคปชั่นได้เลย!", "p3_text_col": (255, 255, 255),
        }
    ]
    thm = themes[theme_idx]

    phases = [
        # Phase 1: Hook สะดุดตา
        {
            "top_bg": thm["p1_top_bg"],
            "top_border": thm["p1_border"],
            "top_text": thm["p1_text"],
            "top_text_col": thm["p1_text_col"],
            "cta_bg": thm["brand_col"],
            "cta_text": "กดดูรายละเอียด / สั่งซื้อ ที่ลิงก์ในแคปชั่น"
        },
        # Phase 2: จุดเด่น & รีวิวแน่น
        {
            "top_bg": thm["p2_top_bg"],
            "top_border": thm["p2_border"],
            "top_text": thm["p2_text"],
            "top_text_col": thm["p2_text_col"],
            "cta_bg": thm["brand_col"],
            "cta_text": "กดดูรายละเอียด / สั่งซื้อ ที่ลิงก์ในแคปชั่น"
        },
        # Phase 3: ชวนกดซื้อทันที
        {
            "top_bg": thm["p3_top_bg"],
            "top_border": thm["p3_border"],
            "top_text": thm["p3_text"],
            "top_text_col": thm["p3_text_col"],
            "cta_bg": thm["p3_top_bg"],
            "cta_text": "สั่งซื้อของแท้ กดลิงก์ในแคปชั่นเลยลูก!"
        }
    ]

    posters = []
    for ph in phases:
        canvas = base_bg.copy()
        draw = ImageDraw.Draw(canvas)

        # แถบ Highlight ด้านบนตัวโตๆ
        draw.rounded_rectangle([40, 50, W - 40, 220], radius=32, fill=ph["top_bg"], outline=ph["top_border"], width=4)
        f_top = get_font(FONT_BOLD, 46)
        draw.text((W // 2, 135), ph["top_text"], font=f_top, fill=ph["top_text_col"], anchor="mm")

        # กรอบรูปสินค้า
        draw.rounded_rectangle(card_box, radius=32, fill=(255, 255, 255, 245), outline=(255, 215, 0, 200), width=4)
        canvas.paste(prod_resized, (box_x, box_y), prod_resized)

        # กล่องข้อมูลสินค้า
        info_top = 1120
        info_box = Image.new("RGBA", (W - 120, 520), (255, 255, 255, 250))
        draw_info = ImageDraw.Draw(info_box)
        draw_info.rounded_rectangle([0, 0, W - 120, 520], radius=32, fill=(255, 255, 255), outline=thm["brand_col"], width=4)

        f_badge = get_font(FONT_BOLD, 40)
        draw_info.text((50, 70), thm["badge"], font=f_badge, fill=thm["brand_col"], anchor="lm")
        
        f_stat = get_font(FONT_BOLD, 30)
        stat_str = f"คะแนน {rating:.1f}  |  ขายแล้ว {sales_count:,} ชิ้น"
        draw_info.text((W - 170, 70), stat_str, font=f_stat, fill=(60, 60, 60), anchor="rm")
        draw_info.line([(40, 125), (W - 160, 125)], fill=(220, 220, 220), width=2)

        f_title = get_font(FONT_BOLD, 38)
        title_lines = wrap_thai_lines(clean_pname, max_chars_per_line=24, max_lines=3)
        title_y = 175
        for l in title_lines:
            draw_info.text((50, title_y), l, font=f_title, fill=(20, 20, 20), anchor="lt")
            title_y += 52

        # ปุ่ม CTA
        cta_rect = [40, 390, W - 160, 480]
        draw_info.rounded_rectangle(cta_rect, radius=20, fill=ph["cta_bg"])
        f_cta = get_font(FONT_BOLD, 36)
        draw_info.text(((W - 120) // 2, 435), ph["cta_text"], font=f_cta, fill=(255, 255, 255), anchor="mm")

        canvas.paste(info_box, (60, info_top), info_box)

        # Footer
        f_foot = get_font(FONT_REG, 28)
        draw.text((W // 2, 1780), f"สนใจสอบถามข้อมูลสินค้า ทักแชท {bot_name} ได้ตลอด 24 ชม.", font=f_foot, fill=(200, 200, 200), anchor="mm")

        posters.append(canvas.convert("RGB"))
    return posters


def _ffmpeg_exe() -> str:

    """path ffmpeg — ใช้ binary ที่ติดมากับ imageio_ffmpeg (ใน venv) ก่อน fallback เป็น 'ffmpeg' ใน PATH"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def multiphase_posters_to_video(poster_paths: List[Path], output_video_path: Path, audio_path: Optional[Path] = None, duration: float = 7.5) -> bool:
    """แปลงภาพโปสเตอร์ 3 จังหวะพร้อมเสียงพากย์ TTS เป็นวิดีโอ 9:16 แบบมีไฮไลท์วิ่งสลับตามเวลา"""
    ffmpeg_exe = _ffmpeg_exe()
    
    p_dur = duration / len(poster_paths)
    filter_parts = []
    concat_inputs = ""
    for i in range(len(poster_paths)):
        dur_i = p_dur if i < len(poster_paths) - 1 else (duration - p_dur * (len(poster_paths) - 1))
        frames_i = int(dur_i * 30)
        filter_parts.append(
            f"[{i}:v]trim=duration={dur_i:.2f},setpts=PTS-STARTPTS,"
            f"zoompan=z='min(zoom+0.0003,1.04)':d={frames_i}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30[v{i}]"
        )
        concat_inputs += f"[v{i}]"
    
    filter_parts.append(f"{concat_inputs}concat=n={len(poster_paths)}:v=1:a=0[v]")
    filter_complex = ";".join(filter_parts)

    cmd = [ffmpeg_exe, "-y"]
    for p in poster_paths:
        cmd.extend(["-loop", "1", "-i", str(p)])

    if audio_path and audio_path.exists():
        cmd.extend([
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", f"{len(poster_paths)}:a",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_video_path)
        ])
    else:
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_video_path)
        ])

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        return output_video_path.exists() and output_video_path.stat().st_size > 1000
    except Exception as e:
        logger.error(f"สร้างวิดีโอ 3 จังหวะล้ม: {e}")
        return False



def generate_product_reels(limit: int = 3) -> List[dict]:
    """ดึงสินค้าจากฐานข้อมูลมาสร้างเป็นคลิปวิดีโอ Reels พร้อมเสียงพากย์ TTS ภาษาไทยธรรมชาติ"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    generated = []
    try:
        products_meta = {}
        if PRODUCTS_JSON.exists():
            try:
                products_meta = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
            except Exception:
                products_meta = {}

        prods = (db.query(models.Product)
                   .filter(models.Product.link_status == "ok",
                           models.Product.sales_count >= 100)
                   .order_by(models.Product.ai_score.desc(),
                             models.Product.sales_count.desc())
                   .limit(100).all())


        # จัดกลุ่มสินค้าตามหมวดหมู่ แล้วสลับหมวดหมู่แบบ Round-Robin เพื่อความหลากหลาย 100%
        by_cat = {}
        for p in prods:
            cat = p.category or "ของใช้ทั่วไป"
            by_cat.setdefault(cat, []).append(p)

        interleaved_prods = []
        while any(by_cat.values()):
            for cat in list(by_cat.keys()):
                if by_cat[cat]:
                    interleaved_prods.append(by_cat[cat].pop(0))

        for p in interleaved_prods:
            if len(generated) >= limit:
                break
            if not p.affiliate_url or not p.affiliate_url.startswith("https://"):
                continue

            filename = f"prod_{p.id}_{sanitize_filename(p.name)}.mp4"
            target_path = PENDING_DIR / filename
            posted_path = POSTED_DIR / filename

            if target_path.exists() or posted_path.exists():
                continue

            clean_name = clean_display_text(p.name)
            print(f"\n🎨 กำลังสร้างคลิป Reels: {clean_name[:40]}... (หมวด: {p.category})")
            
            # 1. ดึงรูปภาพสินค้า
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

            # 2. สร้างเสียงพากย์ภาษาไทย (TTS) ธรรมชาติ หลากหลายมุมมอง ไม่ซ้ำซาก
            voice_script = build_voice_script(p.name, float(p.price or 0), p.category or "", seed_id=p.id)
            print(f"🎙️ เสียงพากย์ไทย: \"{voice_script}\"")
            
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_audio:
                tmp_audio_path = Path(tmp_audio.name)
            
            tts_ok = generate_tts_audio(voice_script, tmp_audio_path)

            # 3. สร้างภาพโปสเตอร์ 3 จังหวะ พร้อมหมุนเวียน 5 ธีมสี ไม่ซ้ำแบบ
            posters = create_product_posters_multiphase(
                product_name=p.name,
                price=float(p.price or 0),
                rating=float(p.rating or 4.9),
                sales_count=int(p.sales_count or 100),
                img=pil_img,
                seed_id=p.id
            )

            tmp_poster_paths = []
            for idx, post_img in enumerate(posters):
                with tempfile.NamedTemporaryFile(suffix=f"_{idx}.png", delete=False) as tmp_p:
                    post_img.save(tmp_p.name, format="PNG")
                    tmp_poster_paths.append(Path(tmp_p.name))


            try:
                # 4. รวมภาพ 3 จังหวะและเสียงพากย์เป็นวิดีโอ Reels (ความยาวตรงกับเสียงจริง + เผื่อเวลาหายใจ 1.2 วิ)

                audio_file = tmp_audio_path if tts_ok else None
                audio_len = get_audio_duration(tmp_audio_path) if tts_ok else 5.0
                target_duration = max(5.5, audio_len + 1.2)
                if multiphase_posters_to_video(tmp_poster_paths, target_path, audio_path=audio_file, duration=target_duration):


                    products_meta[filename] = {
                        "product_name": clean_name,
                        "price": str(int(p.price or 0)),
                        "category": p.category or "สินค้าแนะนำ",
                        "affiliate_link": p.affiliate_url or ""
                    }
                    generated.append({"id": p.id, "name": clean_name, "file": filename})
                    print(f"✅ สร้างคลิปวิดีโอ 3 จังหวะพร้อมไฮไลท์ข้อความสำเร็จ -> {filename}")
            finally:
                for tp in tmp_poster_paths:
                    tp.unlink(missing_ok=True)
                tmp_audio_path.unlink(missing_ok=True)


        if generated:
            PRODUCTS_JSON.write_text(json.dumps(products_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    finally:
        db.close()

    return generated


def create_custom_topic_poster(title: str, subtitle: str, points: list, theme_bg: tuple, line_id: str = "@137gsref") -> Image.Image:
    """สร้างภาพโปสเตอร์แนวตั้ง 1080x1920 (9:16 Full HD) ตามหัวข้อเฉพาะ"""
    W, H = 1080, 1920
    bot_name = clean_display_text(os.getenv("BOT_NAME", "ป้าเข็ม ขายของ"))
    brand_color = _hex_to_rgb(os.getenv("BRAND_COLOR", "#EE4D2D"))

    canvas = Image.new("RGBA", (W, H), theme_bg)
    draw = ImageDraw.Draw(canvas)

    # 1. Header Banner
    header_box = [40, 60, W - 40, 290]
    draw.rounded_rectangle(header_box, radius=32, fill=brand_color, outline=(255, 255, 255, 200), width=3)
    f_header = get_font(FONT_BOLD, 48)
    f_sub = get_font(FONT_REG, 32)
    draw.text((W // 2, 125), title, font=f_header, fill=(255, 255, 255), anchor="mm")
    draw.text((W // 2, 210), subtitle, font=f_sub, fill=(255, 245, 220), anchor="mm")

    # 2. Body Points (3 กล่องไฮไลท์ใหญ่ๆ อ่านง่าย)
    card_y = 350
    card_h = 280
    f_p_head = get_font(FONT_BOLD, 42)
    f_p_body = get_font(FONT_REG, 32)

    for p_title, p_desc in points:
        box = [50, card_y, W - 50, card_y + card_h]
        draw.rounded_rectangle(box, radius=28, fill=(255, 255, 255, 250), outline=(255, 215, 0, 240), width=4)
        draw.text((90, card_y + 45), p_title, font=f_p_head, fill=(20, 20, 20), anchor="lt")
        
        # จัดข้อความอธิบาย
        desc_lines = wrap_thai_lines(p_desc, max_chars_per_line=26, max_lines=2)
        dy = card_y + 120
        for l in desc_lines:
            draw.text((90, dy), l, font=f_p_body, fill=(60, 60, 60), anchor="lt")
            dy += 50

        card_y += card_h + 40

    # 3. Footer / CTA Box
    cta_box = [50, H - 460, W - 50, H - 150]
    draw.rounded_rectangle(cta_box, radius=32, fill=brand_color, outline=(255, 255, 255), width=4)
    f_cta_main = get_font(FONT_BOLD, 46)
    f_cta_sub = get_font(FONT_REG, 32)
    draw.text((W // 2, H - 370), "แอดไลน์คุยกับป้าเข็มได้เลย!", font=f_cta_main, fill=(255, 255, 255), anchor="mm")
    draw.text((W // 2, H - 280), "กดลิงก์ที่หน้าโปรไฟล์ หรือ ในแคปชั่น", font=f_cta_sub, fill=(255, 240, 200), anchor="mm")
    draw.text((W // 2, H - 200), f"LINE: {line_id}", font=f_cta_main, fill=(255, 255, 0), anchor="mm")


    f_copy = get_font(FONT_REG, 26)
    draw.text((W // 2, H - 70), "ผู้ช่วยช้อปปิ้ง AI ตัวจริง • ปรึกษาฟรี 24 ชม.", font=f_copy, fill=(200, 210, 225), anchor="mm")

    return canvas.convert("RGB")


def generate_intro_series() -> List[dict]:
    """สร้างคลิป Reels ซีรีส์แนะนำตัวและฟีเจอร์เด่น 4 ตอนจบ พร้อมเสียงพากย์ไทย TTS"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_DIR.mkdir(parents=True, exist_ok=True)

    bot_name = os.getenv("BOT_NAME", "ป้าเข็ม")
    line_url = os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    
    episodes = [
        {
            "id": "ep1_who_is_pakhem",
            "filename": f"intro_ep1_who_is_{sanitize_filename(bot_name)}.mp4",
            "title": f"🛍️ รู้จักกับ {bot_name}",
            "subtitle": "ป้าไม่ใช่คนขายของ • ไม่อยากให้เสียเงินฟรี",
            "theme_bg": (15, 23, 42, 255),  # Deep Navy
            "points": [
                ("💖 ถ้าไม่คุ้ม ป้าบอกให้!", "ป้าเป็นป้าที่ชอบดูรีวิวและเทียบราคาเป็นชั่วโมงๆ แทนคุณ"),
                ("🤝 ไม่ยัดเยียดขายของ", "เลือกเฉพาะของดี คุ้มค่าเงินทุกบาท ช้อปปิ้งอย่างมั่นใจ"),
                ("📱 ถามป้าก่อนซื้อได้ 24 ชม.", "สงสัยเรื่องสินค้าชิ้นไหน ทักไลน์มาถามป้าได้ตลอดเวลา")
            ],
            "speech": (
                f"สวัสดีจ้า {bot_name} เองนะลูก ป้าไม่ใช่คนขายของนะ "
                f"แต่ป้าไม่อยากเห็นลูกหลานเสียเงินกับของที่ไม่คุ้ม "
                f"จะซื้ออะไรใน Shopee ไลน์มาถามป้าก่อนได้เลยนะลูก แอดไลน์คุยกันได้เลยจ้า"
            ),
            "caption": f"🛍️ รู้จักกับ {bot_name} ผู้ช่วยช้อปปิ้ง AI ตัวจริง! ไม่อยากเสียเงินกับของไม่คุ้ม ถามป้าก่อนซื้อได้ตลอด 24 ชม. จ้า 👉 {line_url} #ป้าเข็ม #ถ้าไม่คุ้มป้าบอกให้ #ผู้ช่วยช้อปปิ้ง"
        },
        {
            "id": "ep2_budget_search",
            "filename": "intro_ep2_budget_search.mp4",
            "title": "🔍 ฟีเจอร์เด็ด: หาสินค้าตามงบ",
            "subtitle": "พิมพ์บอกงบ ป้าคัดของเด็ดให้ทันที",
            "theme_bg": (6, 78, 59, 255),  # Emerald Green
            "points": [
                ("🎧 'หูฟังไม่เกิน 300 บาท'", "ป้าคัดตัวเสียงดี มีตัดเสียงรบกวน แบตอึด ตรงงบเป๊ะ"),
                ("🧊 'กระติกน้ำเก็บความเย็น 200-400'", "เก็บความเย็นข้ามวัน ของแท้ รีวิวแน่น ไม่ต้องเลื่อนหา"),
                ("⚡ 'พาวเวอร์แบงค์งบ 500'", "ชาร์จไว มี มอก. ปลอดภัย ได้มาตรฐาน มั่นใจได้ 100%")
            ],
            "speech": (
                f"อยากได้ของดีแต่งบจำกัดใช่ไหมลูก แค่พิมพ์บอกงบใน LINE "
                f"เช่น หูฟังไม่เกิน 300 หรือ พัดลมงบ 500 "
                f"{bot_name} จะไปคัดของดีตรงงบมาให้ทันที ไม่ต้องเสียเวลาหาเอง แอดไลน์มาลองได้เลยนะลูก"
            ),
            "caption": f"🔍 หาสินค้า Shopee ตามงบได้ง่ายๆ แค่พิมพ์บอกงบใน LINE เช่น 'หูฟังไม่เกิน 300' ป้าหาของเด็ดให้ทันที! 👉 {line_url} #หาสินค้าตามงบ #ช้อปปี้ถูกและดี #ป้าเข็ม"
        },
        {
            "id": "ep3_authentic_check",
            "filename": "intro_ep3_authentic_check.mp4",
            "title": "🛡️ เตือนภัย: คัดเฉพาะของแท้ 100%",
            "subtitle": "กรองรีวิว 4.8 ดาวขึ้นไป • ไม่โดนหลอก",
            "theme_bg": (30, 58, 138, 255),  # Royal Blue
            "points": [
                ("🚨 อย่าหลงเชื่อโปรลด 90%!", "ระวังสินค้าลดราคาเวอร์ผิดปกติ อาจได้ของปลอมไม่ตรงปก"),
                ("⭐ เช็ครีวิวและยอดขายจริง", "ป้ากรองเฉพาะร้านทางการและร้านแนะนำที่มีรีวิว 4.8 ดาวขึ้นไป"),
                ("🔒 ส่งลิงก์ให้ป้าช่วยเช็คได้ฟรี", "ไม่มั่นใจร้านไหน ส่งลิงก์มาให้ป้าช่วยตรวจสอบก่อนกดสั่งซื้อ")
            ],
            "speech": (
                f"เห็นโปรลด 90 เปอร์เซ็นต์ อย่าเพิ่งรีบกดซื้อนะลูก ระวังโดนของปลอม "
                f"{bot_name} มีระบบช่วยคัดเฉพาะร้านค้าของแท้ รีวิวแน่น ยอดขายจริง "
                f"ส่งลิงก์มาให้ป้าช่วยดูก่อนได้ตลอด 24 ชั่วโมงจ้า"
            ),
            "caption": f"🚨 เตือนภัยช้อปปิ้งออนไลน์! เห็นโปรลดเวอร์อย่าเพิ่งกดซื้อ ให้ {bot_name} ช่วยคัดร้านของแท้ รีวิวแน่นให้ก่อน ช้อปอย่างปลอดภัย 👉 {line_url} #เตือนภัยช้อปปิ้ง #ช้อปปี้ของแท้"
        },
        {
            "id": "ep4_price_drop_alerts",
            "filename": "intro_ep4_price_drop_alerts.mp4",
            "title": "🔻 จำความชอบ & แจ้งราคาลด!",
            "subtitle": "Account Memory & Price-Drop Alert",
            "theme_bg": (88, 28, 135, 255),  # Deep Purple
            "points": [
                ("🧠 พิมพ์ 'จำไว้ ชอบแก้วเก็บความเย็น'", "ป้าจะจดจำความชอบของคุณไว้ แนะนำสินค้าใหม่ได้ตรงใจ"),
                ("📉 แจ้งเตือนเมื่อราคาลดลง ≥ 5%", "ตรวจจับราคาทุกวัน วันไหนลดราคา ป้าทักเตือนในไลน์ทันที"),
                ("🎁 ไม่พลาดโค้ดลับและโปรเด็ด", "ได้รับสิทธิพิเศษและโปรโมชันลดราคาก่อนใครใน LINE OA")
            ],
            "speech": (
                f"ชอบสินค้าหมวดไหน แค่พิมพ์บอกป้า เช่น จำไว้ ชอบสกินแคร์ "
                f"วันไหนสินค้าลดราคา หรือมีโค้ดลับพิเศษ "
                f"{bot_name} จะรีบสะกิดเตือนในไลน์ทันที ไม่พลาดของถูกแน่นอนจ้า แอดไลน์มาได้เลยนะลูก"
            ),
            "caption": f"🔻 ไม่พลาดของถูก! มีระบบจำความชอบและแจ้งเตือนเมื่อสินค้าลดราคา พร้อมแจกโค้ดลับใน LINE OA 👉 {line_url} #แจ้งเตือนราคาลด #โค้ดส่วนลดช้อปปี้ #ป้าเข็ม"
        }
    ]

    products_meta = {}
    if PRODUCTS_JSON.exists():
        try:
            products_meta = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass

    results = []
    print(f"\n🎬 เริ่มต้นสร้างซีรีส์คลิปแนะนำตัวและฟีเจอร์เด่น {len(episodes)} ตอน...")

    for ep in episodes:
        target_path = PENDING_DIR / ep["filename"]
        posted_path = POSTED_DIR / ep["filename"]

        if target_path.exists() or posted_path.exists():
            print(f"⏩ มีไฟล์ {ep['filename']} อยู่แล้ว ข้าม...")
            continue

        print(f"\n🎨 กำลังสร้าง: {ep['title']} ({ep['filename']})...")
        print(f"🎙️ เสียงพากย์ไทย: \"{ep['speech']}\"")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_audio:
            tmp_audio_path = Path(tmp_audio.name)

        tts_ok = generate_tts_audio(ep["speech"], tmp_audio_path)
        poster = create_custom_topic_poster(
            title=ep["title"],
            subtitle=ep["subtitle"],
            points=ep["points"],
            theme_bg=ep["theme_bg"]
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_poster:
            poster.save(tmp_poster.name, format="PNG")
            tmp_poster_path = Path(tmp_poster.name)

        try:
            audio_file = tmp_audio_path if tts_ok else None
            if poster_to_video(tmp_poster_path, target_path, audio_path=audio_file, duration=9):
                products_meta[ep["filename"]] = {
                    "product_name": ep["title"],
                    "price": "",
                    "category": "ซีรีส์แนะนำตัวบอท",
                    "affiliate_link": line_url
                }
                results.append(ep)
                print(f"✅ ผลิตคลิปสำเร็จ -> {ep['filename']}")
        finally:
            tmp_poster_path.unlink(missing_ok=True)
            tmp_audio_path.unlink(missing_ok=True)

    if results:
        PRODUCTS_JSON.write_text(json.dumps(products_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return results


if __name__ == "__main__":
    if "--intro-series" in sys.argv:
        generate_intro_series()
    elif "--intro" in sys.argv:
        generate_intro_reel()
    else:
        count = 2
        if len(sys.argv) > 1 and sys.argv[1].isdigit():
            count = int(sys.argv[1])
        print(f"🚀 เริ่มต้นสร้างคลิปสินค้าพร้อมเสียงพากย์ไทยอัตโนมัติ {count} คลิป...")
        res = generate_product_reels(count)
        print(f"\n🎉 สร้างสำเร็จทั้งหมด {len(res)} คลิป พร้อมสำหรับอัปโหลดลง Reels!")


