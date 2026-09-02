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
from app.services.product_price_policy import sanitize_public_product_text

logger = logging.getLogger(__name__)

PENDING_DIR = ROOT_DIR / "pending_videos"
POSTED_DIR = ROOT_DIR / "posted"
PRODUCTS_JSON = ROOT_DIR / "products.json"

def _resolve_fonts():
    """ค้นหาฟอนต์ภาษาไทยที่รองรับทั้ง Windows และ Linux VPS"""
    # 1. รายการฟอนต์หนา (Bold)
    bold_candidates = [
        Path("C:/Windows/Fonts/leelawdb.ttf"),
        Path("C:/Windows/Fonts/tahomabd.ttf"),
        Path("C:/Windows/Fonts/leelawadeeuibold.ttf"),
        Path("/usr/share/fonts/truetype/tlwg/Loma-Bold.ttf"),
        Path("/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansThai-Bold.ttf"),
        ROOT_DIR / "Prompt-Bold.ttf",
    ]
    # 2. รายการฟอนต์ปกติ (Regular)
    reg_candidates = [
        Path("C:/Windows/Fonts/leelawad.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("C:/Windows/Fonts/leelawadeeui.ttf"),
        Path("/usr/share/fonts/truetype/tlwg/Loma.ttf"),
        Path("/usr/share/fonts/truetype/tlwg/Garuda.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansThai-Regular.ttf"),
        ROOT_DIR / "Prompt-Regular.ttf",
    ]
    bold_font = next((p for p in bold_candidates if p.exists()), None)
    reg_font = next((p for p in reg_candidates if p.exists()), None)
    return bold_font, reg_font

FONT_BOLD, FONT_REG = _resolve_fonts()


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
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    try:
        # Fallback กรณีไม่มีฟอนต์เฉพาะ
        return ImageFont.truetype("DejaVuSans.ttf", size)
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


CONTENT_MODES = [
    # สัดส่วนใหม่ 90% คอนเทนต์ไวรัลหยุดดู 3 วิ / 10% สินค้า Shopee แท้
    "TRENDING_NEWS",       # 1. 🌍 ข่าวด่วนจริง (BBC/Sanook)
    "CELEBRITY_TREND",     # 2. 🌟 ตามรอยคนดัง (Sanook/BBC)
    "LIFE_HACK_TIP",       # 3. 💡 ทริคแม่บ้าน
    "TRENDING_NEWS",       # 4. 🌍 ข่าวด่วนจริง
    "CELEBRITY_TREND",     # 5. 🌟 ตามรอยคนดัง
    "LUCKY_FORTUNE",       # 6. 🔮 ดวง & เลขมงคล (Sanook)
    "WORK_PRODUCTIVITY",   # 7. 💼 ทริคคนทำงาน
    "TRENDING_NEWS",       # 8. 🌍 ข่าวด่วนจริง
    "CELEBRITY_TREND",     # 9. 🌟 ตามรอยคนดัง
    "PRODUCT_HIGHLIGHT",   # 10. 🛍️ สินค้า Shopee แท้ (10%)
    "LIFE_HACK_TIP",       # 11. 💡 ทริคแม่บ้าน
    "TRENDING_NEWS",       # 12. 🌍 ข่าวด่วนจริง
    "CELEBRITY_TREND",     # 13. 🌟 ตามรอยคนดัง
    "LUCKY_FORTUNE",       # 14. 🔮 ดวง & เลขมงคล
    "WORK_PRODUCTIVITY",   # 15. 💼 ทริคคนทำงาน
    "LIFE_HACK_TIP",       # 16. 💡 ทริคแม่บ้าน
    "TRENDING_NEWS",       # 17. 🌍 ข่าวด่วนจริง
    "CELEBRITY_TREND",     # 18. 🌟 ตามรอยคนดัง
    "LIFE_HACK_TIP",       # 19. 💡 ทริคแม่บ้าน
    "PRODUCT_HIGHLIGHT",   # 20. 🛍️ สินค้า Shopee แท้ (10%)
]


def generate_ai_voice_script(product_name: str, category: str = "", content_mode: str = "PRODUCT_HIGHLIGHT") -> Optional[str]:
    """ใช้ Groq AI Multi-Key สร้างบทพูดเสียงพากย์สั้น 7-10 วินาที ไวรัล คมชัด 100% (No Price, 3-Sec Viral Hook)
    แบ่งขาด 2 ส่วน:
    1. ขายสินค้าตรงจุด (30%): ป้ายยาและขายสินค้า Shopee
    2. คอนเทนต์เพียวๆ ไม่ขายของ (70%): คนดัง 20%, ทริคแม่บ้าน 15%, เลขเด็ด 15%, ข่าวด่วน 15%, แนะนำการทำงาน 5%
    """
    groq_keys = os.getenv("GROQ_API_KEY", "").split(",")
    models = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]
    
    clean_pname = sanitize_public_product_text(clean_display_text(product_name))
    
    # กำหนดโจทย์สไตล์และ Hook
    if content_mode == "CELEBRITY_TREND":
        mode_instruction = (
            "สไตล์: '🌟 ส่องไอเทมคนดัง & เรื่องเล่าไวรัล (คอนเทนต์เพียว 100% ไม่ขายสินค้า ไม่เอ่ยถึงการซื้อของ)'\n"
            "- ประโยคที่ 1 (0-3 วิ): Hook หยุดดูด้วยกระแสคนดัง เช่น '🚨 ส่องกระแสลิซ่า! ตัวนี้ทำไมคนถึงตามหากันทั้งเมือง?' หรือ 'ตามรอยกระแสหมูเด้งฟีเวอร์ใน 10 วิ!'\n"
            "- ประโยคที่ 2 (4-7 วิ): เล่าความปังและเหตุผลที่ไวรัลแบบสนุกสนาน\n"
            "- ประโยคที่ 3 (8-10 วิ): จบด้วยการชวนคุย เช่น 'ชอบเรื่องฮิตๆ แบบนี้ แอด LINE @137gsref มาคุยกับป้าเข็มนะจ๊ะ'"
        )
    elif content_mode == "LIFE_HACK_TIP":
        mode_instruction = (
            "สไตล์: '💡 ทริคแม่บ้าน & เกร็ดความรู้แก้ปัญหาบ้าน (คอนเทนต์เพียว 100% ไม่ขายสินค้า ไม่เอ่ยถึงการซื้อของ)'\n"
            "- ประโยคที่ 1 (0-3 วิ): Hook หยุดดูด้วยทริคหรือปัญหา เช่น '🚨 อย่าเพิ่งทิ้ง! ก้นกระทะไหม้ดำ มีวิธีแก้ใน 1 นาที' หรือ 'ทริคง่ายๆ จัดบ้านแคบให้จุของเพิ่ม 3 เท่า'\n"
            "- ประโยคที่ 2 (4-7 วิ): อธิบายวิธีแก้ปัญหา/ทริคภูมิปัญญาชาวบ้านแบบสั้นกระชับ นำไปทำตามได้ทันที\n"
            "- ประโยคที่ 3 (8-10 วิ): จบด้วยการชวนคุย เช่น 'ลองเอาทริคนี้ไปใช้ดูนะจ๊ะ แอด LINE @137gsref มาคุยกับป้าเข็มได้เลย'"
        )
    elif content_mode == "LUCKY_FORTUNE":
        mode_instruction = (
            "สไตล์: '🔮 เลขเด็ด & แนวทางโชคลาภ เสริมดวงการเงิน (คอนเทนต์เพียว 100% ไม่ขายสินค้า ไม่เอ่ยถึงการซื้อของ)'\n"
            "- ประโยคที่ 1 (0-3 วิ): Hook หยุดดูด้วยเรื่องดวง/เลขเด็ด เช่น '🔮 เลขเด็ดป้าเข็ม งวดนี้ใครอยากดวงเฮงรับทรัพย์!' หรือ 'เปิดดวงการเงินรับโชคประจำงวด!'\n"
            "- ประโยคที่ 2 (4-7 วิ): บอกแนวทางเลขมงคล/เสริมพลังบวกเพื่อความเป็นสิริมงคล\n"
            "- ประโยคที่ 3 (8-10 วิ): จบด้วยการอวยพร เช่น 'ขอให้ทุกคนเฮงๆ รวยๆ แอด LINE @137gsref มาคุยกับป้าเข็มนะจ๊ะ'"
        )
    elif content_mode == "TRENDING_NEWS":
        mode_instruction = (
            "สไตล์: '📰 สรุปข่าวด่วน & สถานการณ์สำคัญ (เช่น ข่าวเนปาล, สภาพอากาศ, ภัยพิบัติ) (คอนเทนต์เพียว 100% ไม่ขายสินค้า)'\n"
            "- ประโยคที่ 1 (0-3 วิ): Hook หยุดดูด้วยข่าวด่วน เช่น '🚨 สรุปข่าวด่วนเนปาลล่าสุด ใครมีแพลนเดินทางต้องระวัง!' หรือ 'เตือนภัยสภาพอากาศแปรปรวนหนัก!'\n"
            "- ประโยคที่ 2 (4-7 วิ): สาระสั้นๆ สรุปข้อเท็จจริงของเหตุการณ์ให้คนฟังเข้าใจใน 5 วินาที\n"
            "- ประโยคที่ 3 (8-10 วิ): จบด้วยการเตือนและชวนคุย เช่น 'ติดตามสรุปข่าวกับป้าเข็มได้ที่ LINE @137gsref จ้า'"
        )
    elif content_mode == "WORK_PRODUCTIVITY":
        mode_instruction = (
            "สไตล์: '💼 แนะนำการทำงาน & ทริคชีวิตชาวออฟฟิศ (คอนเทนต์เพียว 100% ไม่ขายสินค้า ไม่เอ่ยถึงการซื้อของ)'\n"
            "- ประโยคที่ 1 (0-3 วิ): Hook หยุดดูด้วยเรื่องงาน เช่น '💼 ทริคคนทำงาน! เลิกงานตรงเวลา ชีวิตง่ายขึ้น 10 เท่า' หรือ 'วิธีคุยกับหัวหน้าให้ราบรื่นใน 10 วิ!'\n"
            "- ประโยคที่ 2 (4-7 วิ): แนะนำเทคนิคการจัดเวลา/การทำงานให้มีประสิทธิภาพ\n"
            "- ประโยคที่ 3 (8-10 วิ): จบด้วยการให้กำลังใจ เช่น 'ลองปรับใช้ดูนะจ๊ะ ทักมาคุยกับป้าเข็มใน LINE @137gsref ได้เลย'"
        )
    else:
        # PRODUCT_HIGHLIGHT (30% ขายสินค้าตรงๆ)
        mode_instruction = (
            "สไตล์: '🛍️ รีวิวและป้ายยาของแท้ Shopee ยอดขายดี (ขายสินค้าตรงจุด)'\n"
            "- ประโยคที่ 1 (0-3 วิ): Hook หยุดดูด้วย Pain Point หรือจุดเด่นของสินค้าชิ้นนี้จริงๆ เช่น 'เตือนแล้วนะ! ใครยังไม่มีตัวนี้ติดบ้านคือพลาดมาก'\n"
            "- ประโยคที่ 2 (4-7 วิ): บอกจุดเด่น ความคุ้มค่า น่าใช้\n"
            "- ประโยคที่ 3 (8-10 วิ): จบด้วย Call-To-Action เช่น 'กดดูรายละเอียดหรือสั่งซื้อของแท้ที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ'"
        )

    prompt = (
        f"คุณคือ 'ป้าเข็ม' แม่ค้าใจดีและผู้เชี่ยวชาญด้านคอนเทนต์วิดีโอสั้น\n"
        f"จงเขียน 'บทพูดเสียงพากย์วิดีโอสั้น 9:16 (Shorts / Reels)' ความยาวเป๊ะ 7-10 วินาที (สั้น กระชับ คมกริบ)\n"
        f"หัวข้อ/สินค้า: {clean_pname}\n"
        f"หมวดหมู่: {category}\n\n"
        f"{mode_instruction}\n\n"
        f"กฎเหล็กสำคัญที่สุด:\n"
        f"1. **ความยาวสคริปต์สั้นกระชับ รวมประมาณ 50-80 ตัวอักษรไทย (อ่านจบใน 7-9 วินาทีพอดี ห้ามยาวเกินเด็ดขาด)**\n"
        f"2. **ห้ามพูดเรื่องราคา และห้ามมีตัวเลขราคาเด็ดขาด** (Strict No-Price Policy)\n"
        f"3. เขียนภาษาไทยที่เป็นธรรมชาติ สละสลวย สำหรับนำไปอ่านด้วยเสียงพากย์ TTS ทันที\n"
        f"4. **ห้ามใช้คำว่า 'ลูก', 'ลูกหลาน', 'นะลูก', 'เลยลูก', ให้เรียก 'ทุกคน', 'จ๊ะ', 'จ้า' หรือไม่ต้องระบุคำเรียกแทน**\n"
        f"5. ตอบเฉพาะข้อความบทพูดภาษาไทยล้วนๆ 1 ย่อหน้า ไม่ต้องมีคำอธิบายอื่น ไม่ต้องใส่เครื่องหมายคำพูด"
    )

    for k in groq_keys:
        k = k.strip()
        if not k or "mock" in k:
            continue
        for m in models:
            try:
                from openai import OpenAI
                client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k, timeout=12.0)
                resp = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": "คุณคือนักเขียนสคริปต์เสียงพากย์วิดีโอสั้น Viral 9:16 สไตล์ป้าเข็ม สั้นกระชับ 7-10 วินาที"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=150
                )
                script = (resp.choices[0].message.content or "").strip()
                script = script.replace('"', '').replace("'", "").replace("“", "").replace("”", "").strip()
                # กรองคำว่าราคาและตัวเลขราคาออกถ้าหลุดมา
                script = re.sub(r'(\d+[\d,]*\s*(?:บาท|.-|บ\.))', '', script)
                script = re.sub(r'(?:ราคาเพียง|ราคาแค่|ในราคา|ราคา)\s*\d+', '', script)
                script = _remove_child_address(script)
                if len(script) >= 30:
                    return script
            except Exception as e:
                logger.warning(f"Groq script error ({m}, key ...{k[-4:]}): {e}")
    return None


def _remove_child_address(text: str) -> str:
    """ตัดคำเรียกผู้ฟังที่ไม่เหมาะกับภาพลักษณ์สาธารณะของเพจ."""
    replacements = (
        ("ลูกหลาน", "ทุกคน"),
        ("ลูกรัก", "สัตว์เลี้ยงที่รัก"),
        ("นะลูก", "นะจ๊ะ"),
        ("เลยลูก", "เลยจ้า"),
        ("จ้ะลูก", "จ้ะทุกคน"),
        ("จ้าลูก", "จ้าทุกคน"),
        ("ดูแลลูก", "ดูแลทุกคน"),
        ("ให้ลูก", "ให้ทุกคน"),
        ("ช่วยลูก", "ช่วยทุกคน"),
        ("ลูกได้", "ได้"),
        ("ลูกมี", "มี"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    # catch-all: ตัด "ลูก" ที่หลุดมาเดี่ยวๆ (ไม่ใช่ "ลูกค้า")
    text = re.sub(r'(?<!ค้า)ลูก(?!ค้า)', '', text)
    return text


def build_voice_script(product_name: str, price: float, category: str, seed_id: int = 0, content_mode: str = "PRODUCT_HIGHLIGHT") -> str:
    """สร้างบทพูดสั้นกระชับ สไตล์ป้าเข็ม 7-10 วิ ด้วย AI อัจฉริยะ (พร้อมระบบ Fallback ตรงหมวด 100%)"""
    # 1. พยายามใช้ Groq AI ก่อนเสมอ เพื่อให้ได้บทพูดที่ตรงกับจุดเด่นของสินค้านั้นจริงๆ
    ai_script = generate_ai_voice_script(product_name, category, content_mode=content_mode)
    if ai_script:
        logger.info(f"🎙️ สร้างสคริปต์ [{content_mode}] ด้วย Groq AI สำเร็จ: {ai_script[:60]}...")
        return ai_script

    # 2. กรณีออฟไลน์/API ล้มเหลว -> ใช้ Smart Semantic Fallback ที่จำแนกตรงตามประเภทสินค้าจริง
    clean_name = sanitize_public_product_text(clean_display_text(product_name))
    clean_name = re.sub(r'\b[A-Za-z]{2,}\d{3,}[A-Za-z0-9]*\b', '', clean_name)
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()

    words = clean_name.split()
    clean_words = []
    for w in words:
        if not clean_words or (w not in clean_words[-1] and clean_words[-1] not in w):
            clean_words.append(w)

    short_title = " ".join(clean_words[:4]).strip()
    if not short_title:
        short_title = category if category else "สินค้าคุณภาพดี"

    full_text = f"{product_name} {category}".lower()

    if content_mode == "LIFE_HACK_TIP":
        hooks = [
            f"อย่าเพิ่งทิ้งถ้ายังไม่ลองทริคนี้! {short_title} ตัวช่วยแก้ปัญหากวนใจในบ้าน กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"ทริคง่ายๆ ช่วยประหยัดเวลาและพื้นที่! {short_title} ของแท้ใช้งานดีเว่อร์ ช้อปที่ลิงก์ในแคปชั่นนะจ๊ะ",
            f"เคล็ดลับแก้ปัญหาประจำบ้านที่แม่บ้านบอกต่อ! {short_title} ใช้ง่าย จบปัญหากริบ สั่งที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]
    elif content_mode == "TRENDING_NEWS":
        hooks = [
            f"ข่าวด่วนสภาพอากาศและภัยพิบัติล่าสุด! ใครเดินทางต้องมี {short_title} ติดกระเป๋าไว้ สั่งที่ลิงก์ในแคปชั่นนะจ๊ะ",
            f"เตือนภัยสถานการณ์ฉุกเฉิน! เตรียมพร้อมด้วย {short_title} ของแท้ปลอดภัย ช้อปที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"เกาะติดกระแสด่วน! ไอเทมรับมือเหตุฉุกเฉิน {short_title} การันตีคุณภาพ สั่งซื้อที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]
    elif content_mode == "CELEBRITY_TREND":
        hooks = [
            f"ส่องไอเทมสุดฮิตตามรอยคนดัง! {short_title} ตัวนี้ทำไมคนตามหากันทั้งเมือง กดสั่งซื้อที่ลิงก์ในแคปชั่นเลยจ้า",
            f"กระแสไวรัลที่ทุกคนต้องมี! {short_title} ของแท้ Official สวยปัง ช้อปที่ลิงก์ในแคปชั่นนะจ๊ะ",
            f"ตามรอยไอเทมยอดฮิตระดับโลก! {short_title} รีวิวแน่น การันตีของแท้ สั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ"
        ]
    elif content_mode == "LUCKY_FORTUNE":
        hooks = [
            f"งวดนี้ต้องมีติดตัวไว้! {short_title} เสริมดวงโชคลาภ การเงินปัง พลังบวกเต็มร้อย สั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ",
            f"ใครอยากดวงเฮงรับทรัพย์! {short_title} ไอเทมเสริมมงคลยอดฮิต การันตีของแท้ กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"เคล็ดลับเสริมดวงการเงินและการงาน! {short_title} เสริมพลังบวก ช้อปของแท้ที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]
    elif content_mode == "WORK_PRODUCTIVITY":
        hooks = [
            f"ทริคคนทำงานให้เหนื่อยน้อยลง! {short_title} ตัวช่วยชีวิตชาวออฟฟิศ ชีวิตง่ายขึ้น 10 เท่า สั่งที่ลิงก์ในแคปชั่นนะจ๊ะ",
            f"บอกลาอาการปวดเมื่อยจากการทำงาน! {short_title} ออกแบบตามหลักสรีระ นั่งสบาย ช้อปที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"จัดโต๊ะทำงานให้โปร่ง โฟกัสงานได้ดีขึ้น! {short_title} แข็งแรงทนทาน ของแท้ สั่งซื้อที่ลิงก์ในแคปชั่นเลยนะจ๊ะ"
        ]
    elif any(k in full_text for k in ["โปรตีน", "อาหารเสริม", "วิตามิน", "คอลลาเจน", "ข้าว", "อาหาร", "ขนม", "อร่อย", "ชา", "กาแฟ", "กิน"]):
        hooks = [
            f"อยากดูแลสุขภาพตัวเองให้ดีขึ้น แนะนำ {short_title} ตัวนี้เลย ทานง่าย มีประโยชน์ ของแท้ สั่งที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ",
            f"สายรักสุขภาพหรือชอบของอร่อยต้องลอง! {short_title} คุณภาพเน้นๆ สะอาดปลอดภัย กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"ไอเทมเด็ดเพื่อสุขภาพที่ดีขึ้นในทุกวัน! {short_title} ทานแล้วรู้สึกดี ปลอดภัย ช้อปที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]
    elif any(k in full_text for k in ["สัตว์", "หมา", "แมว", "อึ", "ฉี่", "ขน", "แผ่นรอง", "pet"]):
        hooks = [
            f"พาน้องไปเดินเล่น หรือเลี้ยงในบ้าน แล้วเจอปัญหากลิ่นกวนใจใช่ไหม? {short_title} ตัวนี้ช่วยได้เยอะมาก ของแท้ สั่งที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ",
            f"เลี้ยงหมาแมวต้องมีติดบ้านไว้! {short_title} ซับไว ลดกลิ่นกริบ รีวิวแน่นมาก กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"หยุดปัญหาเก็บอึแล้วเลอะมือหรือถุงขาด! {short_title} เหนียวทน ไม่รั่วซึม พกพาสะดวก ช้อปที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]
    elif any(k in full_text for k in ["สิว", "หน้า", "สบู่", "ผิว", "ครีม", "เซรั่ม", "บำรุง", "ความงาม", "สำลี", "ลิป", "แป้ง"]):
        hooks = [
            f"สิวผด สิวอุดตัน หรือผิวหมองคล้ำกวนใจ? {short_title} ช่วยฟื้นฟูผิว ลดรอยสิว อ่อนโยน สั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ",
            f"ไอเทมบำรุงผิวที่คนรีวิวแน่นที่สุด! {short_title} ของแท้ร้อยเปอร์เซ็นต์ ผิวกระจ่างใส กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"ล้างหน้าแล้วผิวแห้งตึง ลองเปลี่ยนมาใช้ {short_title} ผิวนุ่มชุ่มชื้น สะอาดหมดจด ช้อปที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]
    elif any(k in full_text for k in ["หูฟัง", "ฟิล์ม", "บลูทูธ", "ไอที", "แกดเจ็ต", "เคส", "สายชาร์จ", "พาวเวอร์แบงค์", "มือถือ"]):
        hooks = [
            f"ไม่อยากให้คนข้างๆ แอบมองหน้าจอ หรือหูฟังเสียงไม่ชัด? {short_title} จบปัญหากริบ ของแท้ สั่งที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ",
            f"แกดเจ็ตตัวเด็ดที่ทุกคนต้องมีพกติดตัว! {short_title} สเปกแรง คุ้มเกินราคา กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"เบื่อไหมที่สายชาร์จพังบ่อย หรือเสียงขาดๆ หายๆ? {short_title} ตัวนี้ทนทาน เสียงดี ช้อปที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]
    elif any(k in full_text for k in ["ปวด", "เมื่อย", "นวด", "หลัง", "คอ", "ไหล่", "เบาะ", "ที่นอน", "หมอน"]):
        hooks = [
            f"นั่งทำงานทั้งวัน ปวดคอบ่าไหล่จนทนไม่ไหว? {short_title} ช่วยคลายปวด ผ่อนคลายกล้ามเนื้อ สั่งซื้อที่ลิงก์ในแคปชั่นนะจ๊ะ",
            f"บอกลาอาการปวดหลัง เมื่อยสะโพก! {short_title} ออกแบบตามสรีระ นุ่มสบาย กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"ดูแลสุขภาพตัวเองง่ายๆ ได้ทุกวัน! {short_title} บรรเทาอาการเมื่อยล้า การันตีของแท้ สั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ"
        ]
    elif any(k in full_text for k in ["ครัว", "กระทะ", "หม้อ", "แก้ว", "ตะหลิว", "มีด", "จาน", "ช้อน", "คว่ำ"]):
        hooks = [
            f"ทำอาหารแล้วกระทะติด ล้างยากจนเหนื่อย? {short_title} ทนความร้อนสูง ล้างง่ายมาก สั่งซื้อที่ลิงก์ในแคปชั่นนะจ๊ะ",
            f"สายทำอาหาร สายของกินต้องมีติดครัวไว้! {short_title} ใช้ง่าย สะอาด เกรดพรีเมียม กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"ไอเทมลับประจำห้องครัวที่แม่บ้านยกนิ้วให้! {short_title} ปลอดภัย ได้มาตรฐาน สั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ"
        ]
    elif any(k in full_text for k in ["ผ้า", "เช็ด", "ไมโคร", "คราบ", "จัดระเบียบ", "ตู้", "ทิชชู่", "ทำความสะอาด", "ถูพื้น"]):
        hooks = [
            f"เช็ดคราบมัน คราบฝังลึกไม่ออกสักทีใช่ไหม? {short_title} เช็ดรอบเดียวเงาวับ ซึมซับดีมาก สั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ",
            f"บ้านรก หาของไม่เจอ ลองใช้ {short_title} จัดระเบียบได้พื้นที่เพิ่ม 3 เท่า กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"หมดปัญหาผ้าขาดง่ายหรือมีขนหลุดติดกระจก! {short_title} หนานุ่ม ซับน้ำไวเว่อร์ ช้อปที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]
    elif any(k in full_text for k in ["รถ", "แดด", "ช่าง", "กีฬา", "เดินทาง", "ร่ม", "ปั๊ม", "ยาง"]):
        hooks = [
            f"จอดรถตากแดดจนเบาะร้อน หรือกลิ่นอับในรถกวนใจ? {short_title} จบทุกปัญหา มีติดรถไว้อุ่นใจ สั่งซื้อที่ลิงก์ในแคปชั่นนะจ๊ะ",
            f"อุปกรณ์ช่างและติดรถที่ต้องมีพกไว้! {short_title} ใช้งานทนทาน แข็งแรงมาก กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"เดินทางไกลไม่ต้องกังวล! {short_title} ไอเทมฉุกเฉินคู่ใจคนรักรถ ช้อปของแท้ที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ"
        ]
    else:
        hooks = [
            f"ใครกำลังมองหาของดีมีคุณภาพ แนะนำ {short_title} ตัวนี้เลย การันตีของแท้ สั่งซื้อที่ลิงก์ในแคปชั่นได้เลยนะจ๊ะ",
            f"ของดีคุณภาพพรีเมียมที่ทุกคนแนะนำ! {short_title} ใช้งานดี รีวิวแน่นมาก กดสั่งซื้อที่ลิงก์ในแคปชั่นได้เลยจ้า",
            f"ไอเทมเด็ดที่คุ้มค่าและตอบโจทย์ชีวิต! {short_title} ของแท้ร้อยเปอร์เซ็นต์ ช้อปที่ลิงก์ในแคปชั่นนะจ๊ะ"
        ]

    return hooks[seed_id % len(hooks)]


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
    clean_pname = sanitize_public_product_text(clean_display_text(product_name))

def create_product_posters_multiphase(
    product_name: str,
    price: float,
    rating: float,
    sales_count: int,
    img: Image.Image,
    seed_id: int = 0,
    content_mode: str = "PRODUCT_HIGHLIGHT"
) -> List[Image.Image]:
    """สร้างภาพโปสเตอร์ 1080x1920 (9:16) 3 จังหวะ พร้อมหมุนเวียน 4 เสาหลักคอนเทนต์ (สินค้า/ทริค/ข่าว/คนดัง)
    และ 5 ธีมสี ไม่พูดราคา 100%
    """
    W, H = 1080, 1920
    clean_pname = sanitize_public_product_text(clean_display_text(product_name))

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
            "p3_top_bg": (5, 150, 105), "p3_border": (255, 255, 255), "p3_text": "สั่งซื้อของแท้ กดลิงก์ในแคปชั่นเลยจ้า!", "p3_text_col": (255, 255, 255),
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
            "p3_top_bg": (16, 185, 129), "p3_border": (255, 255, 255), "p3_text": "สั่งซื้อของแท้ กดลิงก์ในแคปชั่นเลยจ้า!", "p3_text_col": (255, 255, 255),
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

    # ปรับข้อความ Hook และ Badge ตาม Content Mode
    p1_hook_text = thm["p1_text"]
    badge_text = thm["badge"]
    if content_mode == "LIFE_HACK_TIP":
        p1_hook_text = "💡 ทริคแม่บ้าน • แก้ปัญหาใน 1 นาที!"
        badge_text = "💡 ทริคแก้ปัญหา"
    elif content_mode == "TRENDING_NEWS":
        p1_hook_text = "🚨 สรุปข่าวด่วน • สิ่งจำเป็นต้องรู้!"
        badge_text = "🚨 เกาะกระแสข่าวด่วน"
    elif content_mode == "CELEBRITY_TREND":
        p1_hook_text = "🌟 ส่องไอเทมคนดัง • ฮิตติดเทรนด์!"
        badge_text = "🌟 ตามรอยคนดัง"
    elif content_mode == "LUCKY_FORTUNE":
        p1_hook_text = "🔮 เสริมดวงโชคลาภ • รับทรัพย์ปังๆ!"
        badge_text = "🔮 สายมูเสริมดวง"
    elif content_mode == "WORK_PRODUCTIVITY":
        p1_hook_text = "💼 ทริคคนทำงาน • ชีวิตง่ายขึ้น 10 เท่า!"
        badge_text = "💼 ทริคคนทำงาน"

    # ปรับปุ่ม CTA ตาม Content Mode
    cta_p1_text = "กดดูรายละเอียด / สั่งซื้อ ที่ลิงก์ในแคปชั่น" if content_mode == "PRODUCT_HIGHLIGHT" else "ติดตามสาระดีๆ แอด LINE @137gsref"
    cta_p3_text = "สั่งซื้อของแท้ กดลิงก์ในแคปชั่นเลยจ้า!" if content_mode == "PRODUCT_HIGHLIGHT" else "คุยกับป้าเข็ม แอด LINE @137gsref จ้า!"

    phases = [
        # Phase 1: Hook สะดุดตา 0-3 วิ
        {
            "top_bg": thm["p1_top_bg"],
            "top_border": thm["p1_border"],
            "top_text": p1_hook_text,
            "top_text_col": thm["p1_text_col"],
            "cta_bg": thm["brand_col"],
            "cta_text": cta_p1_text
        },
        # Phase 2: จุดเด่น & รีวิวแน่น 4-7 วิ
        {
            "top_bg": thm["p2_top_bg"],
            "top_border": thm["p2_border"],
            "top_text": thm["p2_text"],
            "top_text_col": thm["p2_text_col"],
            "cta_bg": thm["brand_col"],
            "cta_text": cta_p1_text
        },
        # Phase 3: ชวนกดซื้อ/ชวนคุย 8-10 วิ
        {
            "top_bg": thm["p3_top_bg"],
            "top_border": thm["p3_border"],
            "top_text": thm["p3_text"],
            "top_text_col": thm["p3_text_col"],
            "cta_bg": thm["p3_top_bg"],
            "cta_text": cta_p3_text
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
        draw_info.text((50, 70), badge_text, font=f_badge, fill=thm["brand_col"], anchor="lm")
        
        f_stat = get_font(FONT_BOLD, 30)
        stat_str = f"คะแนน {rating:.1f}  |  ขายแล้ว {sales_count:,} ชิ้น" if content_mode == "PRODUCT_HIGHLIGHT" else "สาระน่ารู้ • อัปเดตประจำวัน"
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

        # แถบ Conversion Bar เด่นชัด ลอยด้านล่าง
        draw.rounded_rectangle([40, 1705, W - 40, 1860], radius=24, fill=(15, 23, 42, 245), outline=(34, 197, 94), width=4)
        f_foot1 = get_font(FONT_BOLD, 33)
        f_foot2 = get_font(FONT_BOLD, 27)
        if content_mode == "PRODUCT_HIGHLIGHT":
            draw.text((W // 2, 1750), f"พิกัดของแท้: แอด LINE @137gsref พิมพ์ \"{seed_id}\"", font=f_foot1, fill=(255, 255, 255), anchor="mm")
            draw.text((W // 2, 1810), f"รับลิงก์ตรงตัวทันที! (หรือกดดูที่หน้าช่อง Anda)", font=f_foot2, fill=(74, 222, 128), anchor="mm")
        else:
            draw.text((W // 2, 1750), f"ติดตามเกร็ดความรู้ & สาระดีๆ จากป้าเข็ม", font=f_foot1, fill=(255, 255, 255), anchor="mm")
            draw.text((W // 2, 1810), f"แอด LINE: @137gsref (ทักมาคุยกันได้ 24 ชม.)", font=f_foot2, fill=(74, 222, 128), anchor="mm")

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



def get_used_product_ids() -> set:
    """ดึงรหัสสินค้า (Product ID) ทั้งหมดที่เคยสร้างหรือโพสต์ไปแล้ว เพื่อไม่ให้ทำซ้ำเด็ดขาด 100%"""
    used_ids = set()
    for d in [POSTED_DIR, PENDING_DIR]:
        if d.exists():
            for f in d.glob("*"):
                m = re.search(r'prod_(\d+)_', f.name)
                if m:
                    try:
                        used_ids.add(int(m.group(1)))
                    except Exception:
                        pass
    return used_ids


def _latest_price_drop_map(db) -> dict:
    """คืนเปอร์เซ็นต์ลดราคาล่าสุดต่อสินค้า จาก price_history (อ่านอย่างเดียว)"""
    drops = {}
    try:
        rows = (db.query(models.PriceHistory)
                .order_by(models.PriceHistory.created_at.desc(),
                          models.PriceHistory.id.desc())
                .all())
        for row in rows:
            if row.product_id in drops:
                continue
            try:
                drops[row.product_id] = max(0.0, float(row.drop_pct or 0))
            except (TypeError, ValueError):
                drops[row.product_id] = 0.0
    except Exception as e:
        logger.warning(f"Price history query: {e}")
    return drops


def generate_product_reels(limit: int = 3, selection: str = "balanced",
                           dry_run: bool = False) -> List[dict]:
    """เลือกสินค้าไม่ซ้ำตามโหมด แล้วสร้างคลิปพร้อมเสียงพากย์ AI.

    selection:
      - discount: ลดราคาล่าสุดสูงสุด (ต้องมี price_history)
      - bestseller: ยอดขายสูงสุด
      - balanced: ผสม AI score, ยอดขาย และส่วนลด (ค่าเริ่มต้น)
    dry_run แสดงรายการที่เลือกโดยไม่ดาวน์โหลดรูป/เรียก AI/สร้างไฟล์
    """
    if selection not in {"discount", "bestseller", "balanced"}:
        raise ValueError("selection ต้องเป็น discount, bestseller หรือ balanced")
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_DIR.mkdir(parents=True, exist_ok=True)

    used_ids = get_used_product_ids()
    print(f"📦 ตรวจพบสินค้าที่เคยผลิต/โพสต์แล้วในระบบ: {len(used_ids)} รายการ (จะข้ามไม่ให้ซ้ำเด็ดขาด)")

    db = SessionLocal()
    generated = []
    try:
        products_meta = {}
        if PRODUCTS_JSON.exists():
            try:
                products_meta = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
            except Exception:
                products_meta = {}

        # 8 หมวดหมู่หลัก และหมวดย่อยเทรนด์ยอดฮิต (ครอบคลุมสินค้า 2,530 รายการ 100%)
        SUB_CATEGORIES_TAXONOMY = {
            "1. ไอที อุปกรณ์คอมพิวเตอร์ & มือถือ": [
                "คีย์บอร์ด", "keyboard", "เมาส์", "mouse", "hub", "usb", "โน้ตบุ๊ก", "laptop", "แผ่นรอง",
                "หูฟัง", "headset", "earphone", "ลำโพง", "speaker", "tws", "bluetooth", "ไอที", "แกดเจ็ต",
                "สายชาร์จ", "charger", "พาวเวอร์แบงค์", "eloop", "power bank", "ฟิล์ม", "เคส", "ขาตั้งกล้อง",
                "tuya", "smart remote", "เซนเซอร์", "กล้องวงจรปิด", "wifi mini"
            ],
            "2. ของใช้ในบ้าน & ช่างประจำบ้าน": [
                "คาปาซิเตอร์", "cbb61", "หลอดไฟ", "led", "สวิตช์", "เทป", "ปลั๊ก", "เต้ารับ", "เครื่องมือช่าง",
                "พัดลม", "hatari", "พัดลมพกพา", "พัดลมมือถือ", "พัดลมตั้งพื้น", "เครื่องใช้ไฟฟ้า", "โคมไฟ",
                "กระดาษทิชชู่", "ทิชชู่", "แปรง", "ไม้กวาด", "กล่องเก็บของ", "ถุงขยะ", "ปรับผ้านุ่ม", "downy", "ซักผ้า", "ของใช้บ้าน"
            ],
            "3. สุขภาพ & อาหารเสริม": [
                "dr.pong", "coq10", "วิตามิน", "vitamin", "คอลลาเจน", "โปรตีน", "นมถั่วเหลือง", "ดีน่า", "dna", "cider", "สุขภาพ",
                "วัดความดัน", "sinocare", "เครื่องวัด", "หน้ากาก", "mask", "3d mask", "welcare", "ตรวจน้ำตาล"
            ],
            "4. ความงาม & สกินแคร์": [
                "cerave", "moisturising", "โลชั่น", "lotion", "เซรั่ม", "serum", "la roche", "cicaplast", "ordinary", "สกินแคร์", "บำรุงผิว",
                "กันแดด", "uv defend", "sunscreen", "สบู่", "suk skin", "โฟมล้างหน้า", "คลีนซิ่ง", "ความงาม"
            ],
            "5. เครื่องครัว & อุปกรณ์ทำอาหาร": [
                "หม้อ", "หม้อไฟฟ้า", "กระทะ", "กระทะไฟฟ้า", "เครื่องปั่น", "หม้อทอด", "กาต้มน้ำ", "เครื่องครัว", "อาหาร",
                "กระติกน้ำ", "แก้วน้ำ", "eskimo", "civago", "สูญญากาศ", "สแตนเลส", "แก้วเก็บความเย็น", "มีด", "เขียง"
            ],
            "6. ของใช้สัตว์เลี้ยง": [
                "ทรายแมว", "kasty", "ห้องน้ำแมว", "แผ่นรองฉี่", "ดับกลิ่นทราย", "สัตว์เลี้ยง", "ทาสแมว",
                "อาหารแมว", "อาหารหมา", "ขนมแมวเลีย", "แคทนิป", "แชมพูหมา", "แชมพูแมว", "yoyopet", "ของเล่นแมว"
            ],
            "7. อุปกรณ์ติดรถยนต์ & เดินทาง": [
                "พรมปูพื้น", "carptah", "ที่วางมือถือในรถ", "ม่านบังแดด", "เบาะรอง", "ที่ชาร์จในรถ", "กล้องหน้ารถ", "ปั๊มลมพกพา", "อุปกรณ์ติดรถ", "เดินทาง"
            ],
            "8. แฟชั่น & เครื่องแต่งกาย": [
                "กางเกงวิ่ง", "yuedpao", "กางเกงขาสั้น", "เสื้อยืด", "เสื้อคลุม", "คาร์ดิแกน", "bemingtop", "แฟชั่น",
                "กางเกงใน", "บรา", "ถุงเท้า", "ผ้าเช็ดตัว", "frolina"
            ]
        }

        # 1. ให้ Demand Radar เป็นตัวตัดสินใจอันดับ 1 (Top Priority Demand Radar Decider)
        radar_prods = []
        try:
            radar_events = (db.query(models.FacebookDemandEvent)
                              .filter(models.FacebookDemandEvent.demand_score >= 70,
                                      models.FacebookDemandEvent.matched_product_id.isnot(None))
                              .order_by(models.FacebookDemandEvent.demand_score.desc(),
                                        models.FacebookDemandEvent.created_at.desc())
                              .limit(20).all())
            radar_pids = [ev.matched_product_id for ev in radar_events if ev.matched_product_id and ev.matched_product_id not in used_ids]
            if radar_pids:
                radar_prods = (db.query(models.Product)
                                 .filter(models.Product.id.in_(radar_pids),
                                         models.Product.link_status == "ok").all())
                print(f"🎯 [Demand Radar Decider] ตรวจพบสินค้ากระแสความต้องการสูงจากเรดาร์: {len(radar_prods)} รายการ (จัดคิวผลิตเป็นอันดับแรก!)")
        except Exception as e:
            logger.warning(f"Demand Radar query: {e}")

        # 2. ดึงสินค้าคุณภาพดีจาก 8 หมวดหมู่เทรนด์ครอบคลุม 100% เต็มคลัง
        query = (db.query(models.Product)
                   .filter(models.Product.link_status == "ok"))
        
        if used_ids:
            query = query.filter(~models.Product.id.in_(used_ids))

        prods = query.order_by(models.Product.ai_score.desc(),
                               models.Product.sales_count.desc()) \
                     .limit(4000).all()

        drop_map = _latest_price_drop_map(db)

        if selection == "discount":
            radar_prods = [p for p in radar_prods if drop_map.get(p.id, 0.0) > 0]
            prods = [p for p in prods if drop_map.get(p.id, 0.0) > 0]
            print(f"🔻 พบสินค้าที่มีประวัติลดราคาจริง: {len(prods)} รายการ")

        def rank_key(p):
            drop = drop_map.get(p.id, 0.0)
            sales = int(p.sales_count or 0)
            ai = int(p.ai_score or 0)
            if selection == "discount":
                return (drop, sales, ai)
            if selection == "bestseller":
                return (sales, ai, drop)
            return (ai * 2 + min(sales, 100000) / 1000 + drop * 2,
                    sales, drop)
        prods.sort(key=rank_key, reverse=True)

        print(f"✨ คัดเลือกสินค้าตรงกับ 8 หมวดหมู่เทรนด์ยอดฮิต: {len(prods)} รายการ (เต็มคลัง 100%)")

        # จัดกลุ่มสินค้าแยกตาม 8 หมวดหมู่เทรนด์ แล้วสับเปลี่ยนแบบ Round-Robin
        import random
        by_cat = {cat_name: [] for cat_name in SUB_CATEGORIES_TAXONOMY}
        for p in prods:
            p_text = f"{p.name or ''} {p.category or ''}".lower()
            matched_cat = None
            for cat_name, sub_keywords in SUB_CATEGORIES_TAXONOMY.items():
                if any(kw in p_text for kw in sub_keywords):
                    matched_cat = cat_name
                    break
            if not matched_cat:
                # Fallback to category 1 or 2
                matched_cat = "2. ของใช้ในบ้าน & ช่างประจำบ้าน"
            by_cat[matched_cat].append(p)

        if selection == "balanced":
            # balanced ยังคงกระจายหมวด เพื่อไม่ให้คลิปติดอยู่หมวดเดียว
            for trend_name in by_cat:
                by_cat[trend_name].sort(key=rank_key, reverse=True)
            interleaved_prods = list(radar_prods)
            trend_keys = list(by_cat.keys())
            random.shuffle(trend_keys)
            while any(by_cat.values()):
                for tk in trend_keys:
                    if by_cat[tk]:
                        interleaved_prods.append(by_cat[tk].pop(0))
        else:
            # discount/bestseller ต้องรักษาอันดับจริง ไม่สุ่มทิ้ง ranking
            interleaved_prods = list(radar_prods) + sorted(
                [p for values in by_cat.values() for p in values],
                key=rank_key, reverse=True)

        if dry_run:
            preview = []
            for p in interleaved_prods[:limit]:
                preview.append({
                    "id": p.id,
                    "name": clean_display_text(p.name),
                    "category": p.category or "",
                    "price": float(p.price or 0),
                    "sales_count": int(p.sales_count or 0),
                    "ai_score": int(p.ai_score or 0),
                    "latest_drop_pct": drop_map.get(p.id, 0.0),
                    "affiliate_url": p.affiliate_url or "",
                })
            print(json.dumps({"selection": selection, "products": preview},
                             ensure_ascii=False, indent=2))
            return preview

        import standalone_content_generator

        slot_idx = len(list(PENDING_DIR.glob("*.mp4")))
        prod_iter = iter(interleaved_prods)

        while len(generated) < limit:
            content_mode = CONTENT_MODES[slot_idx % len(CONTENT_MODES)]
            slot_idx += 1

            # -------------------------------------------------------------
            # รางที่ 2: 🎬 คลิปคอนเทนต์เพียวๆ 70% (ไม่ขายของ ไม่ใช้รูปสินค้า)
            # -------------------------------------------------------------
            if content_mode != "PRODUCT_HIGHLIGHT":
                topic_data = standalone_content_generator.get_pure_topic_data(content_mode)
                pure_title = topic_data.get("title", "")
                pure_filename = f"pure_{content_mode}_{int(time.time())}_{random.randint(100, 999)}.mp4"
                pure_target_path = PENDING_DIR / pure_filename

                print(f"\n🎨 [รางที่ 2: คอนเทนต์เพียว 100%] กำลังสร้างคลิป Reels [{content_mode}]: {pure_title[:45]}")
                if standalone_content_generator.build_standalone_reel_video(content_mode, topic_data, pure_target_path):
                    products_meta[pure_filename] = {
                        "product_name": pure_title,
                        "content_mode": content_mode,
                        "topic_data": topic_data,
                        "is_pure_content": True
                    }
                    generated.append({"id": None, "name": pure_title, "file": pure_filename, "content_mode": content_mode})
                    print(f"✅ สร้างคลิปคอนเทนต์เพียว 3 จังหวะสำเร็จ -> {pure_filename}")
                continue

            # -------------------------------------------------------------
            # รางที่ 1: 🛍️ คลิปสินค้า Shopee ตรงจุด 30% (รีวิวและขายสินค้าตรงๆ)
            # -------------------------------------------------------------
            p = None
            for candidate_p in prod_iter:
                if not candidate_p.affiliate_url or not candidate_p.affiliate_url.startswith("https://"):
                    continue
                if candidate_p.id in used_ids:
                    continue
                filename_check = f"prod_{candidate_p.id}_{sanitize_filename(candidate_p.name)}.mp4"
                if (PENDING_DIR / filename_check).exists() or (POSTED_DIR / filename_check).exists():
                    continue
                p = candidate_p
                break

            if not p:
                break

            filename = f"prod_{p.id}_{sanitize_filename(p.name)}.mp4"
            target_path = PENDING_DIR / filename
            posted_path = POSTED_DIR / filename

            clean_name = sanitize_public_product_text(clean_display_text(p.name))
            print(f"\n🎨 [รางที่ 1: สินค้าตรงจุด 100%] กำลังสร้างคลิป Reels: {clean_name[:40]}... (หมวด: {p.category})")

            # 1. ดึงรูปภาพสินค้าสดใหม่จากหน้าเว็บ Shopee จริงเสมอ (ป้องกันรูปเก่าที่ติดป้ายราคาเดิม)
            img_url = fetch_product_image(p.affiliate_url or "") or p.image_url
            if img_url and img_url != p.image_url:
                p.image_url = img_url
                try:
                    db.commit()
                except Exception:
                    pass

            if not img_url:
                continue

            pil_img = download_image(img_url)
            if not pil_img:
                continue

            # 2. สร้างเสียงพากย์ภาษาไทย (TTS) สั้นกระชับ 7-10 วินาที ไวรัล คมกริบ สำหรับสินค้าจริง
            voice_script = build_voice_script(p.name, float(p.price or 0), p.category or "", seed_id=p.id, content_mode="PRODUCT_HIGHLIGHT")
            print(f"🎙️ เสียงพากย์ไทย [สินค้าตรงจุด]: \"{voice_script}\"")
            
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_audio:
                tmp_audio_path = Path(tmp_audio.name)
            
            tts_ok = generate_tts_audio(voice_script, tmp_audio_path)

            # 3. สร้างภาพโปสเตอร์ 3 จังหวะ สำหรับสินค้า Shopee
            posters = create_product_posters_multiphase(
                product_name=p.name,
                price=float(p.price or 0),
                rating=float(p.rating or 4.9),
                sales_count=int(p.sales_count or 100),
                img=pil_img,
                seed_id=p.id,
                content_mode="PRODUCT_HIGHLIGHT"
            )

            tmp_poster_paths = []
            for idx, post_img in enumerate(posters):
                with tempfile.NamedTemporaryFile(suffix=f"_{idx}.png", delete=False) as tmp_p:
                    post_img.save(tmp_p.name, format="PNG")
                    tmp_poster_paths.append(Path(tmp_p.name))

            try:
                # 4. รวมภาพ 3 จังหวะและเสียงพากย์เป็นวิดีโอ Reels สั้นกระชับ 7-10 วินาทีพอดีเป๊ะ
                audio_file = tmp_audio_path if tts_ok else None
                audio_len = get_audio_duration(tmp_audio_path) if tts_ok else 5.0
                min_duration = max(5.5, float(os.getenv("REELS_MIN_DURATION", "7.5") or 7.5))
                audio_tail = max(0.5, float(os.getenv("REELS_AUDIO_TAIL_SECONDS", "0.8") or 0.8))
                target_duration = min(10.0, max(min_duration, audio_len + audio_tail))
                if multiphase_posters_to_video(tmp_poster_paths, target_path, audio_path=audio_file, duration=target_duration):

                    products_meta[filename] = {
                        "product_name": clean_name,
                        "price": str(int(p.price or 0)),
                        "category": p.category or "สินค้าแนะนำ",
                        "affiliate_link": p.affiliate_url or "",
                        "content_mode": "PRODUCT_HIGHLIGHT"
                    }
                    generated.append({"id": p.id, "name": clean_name, "file": filename, "content_mode": "PRODUCT_HIGHLIGHT"})
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
                f"สวัสดีจ้า {bot_name} เองนะจ๊ะ ป้าไม่ใช่คนขายของนะ "
                f"แต่ป้าไม่อยากเห็นทุกคนเสียเงินกับของที่ไม่คุ้ม "
                f"จะซื้ออะไรใน Shopee ไลน์มาถามป้าก่อนได้เลยนะจ๊ะ แอดไลน์คุยกันได้เลยจ้า"
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
                f"อยากได้ของดีแต่งบจำกัดใช่ไหม แค่พิมพ์บอกงบใน LINE "
                f"เช่น หูฟังไม่เกิน 300 หรือ พัดลมงบ 500 "
                f"{bot_name} จะไปคัดของดีตรงงบมาให้ทันที ไม่ต้องเสียเวลาหาเอง แอดไลน์มาลองได้เลยนะจ๊ะ"
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
                f"เห็นโปรลด 90 เปอร์เซ็นต์ อย่าเพิ่งรีบกดซื้อนะจ๊ะ ระวังโดนของปลอม "
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
                f"{bot_name} จะรีบสะกิดเตือนในไลน์ทันที ไม่พลาดของถูกแน่นอนจ้า แอดไลน์มาได้เลยนะจ๊ะ"
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
        selection = "balanced"
        dry_run = "--dry-run" in sys.argv
        positional = [a for a in sys.argv[1:] if not a.startswith("--")]
        if positional and positional[0].isdigit():
            count = int(positional[0])
        if "--mode" in sys.argv:
            try:
                selection = sys.argv[sys.argv.index("--mode") + 1].strip().lower()
            except (IndexError, ValueError):
                raise SystemExit("ใช้ --mode discount|bestseller|balanced")
        print(f"🚀 โหมด {selection}: {'ดูรายการ' if dry_run else 'สร้าง'} {count} คลิป...")
        res = generate_product_reels(count, selection=selection, dry_run=dry_run)
        if dry_run:
            print(f"\n✅ dry-run เสร็จสิ้น แสดงรายการ {len(res)} สินค้า (ยังไม่สร้าง/อัปโหลดคลิป)")
        else:
            print(f"\n🎉 สร้างสำเร็จทั้งหมด {len(res)} คลิป พร้อมสำหรับอัปโหลดลง Reels!")


