# -*- coding: utf-8 -*-
"""tools/visual_hook_engine.py — ระบบดึงและจัดการภาพฮุกอารมณ์คนจริง & Before/After (Visual Hook Engine)

ยึดตามกฎเหล็กภาพถ่ายจริง 100% (Rule 22):
- คัดสรรเฉพาะภาพถ่ายคนจริง (Real Human Emotions: ตกใจ, สงสัย, เจอปัญหา)
- ภาพเปรียบเทียบ ก่อน-หลัง (Before vs After) หรือภาพปัญหาชัดเจนใน 0.5 วินาที
- รองรับ 3 แหล่งภาพ:
  1. Pexels API (ถ้ามี PEXELS_API_KEY ใน .env)
  2. Tavily Images Live Search (ดึงภาพถ่ายจริงจากข่าว/เว็บแบบสดๆ)
  3. Curated High-Impact Registry (คลังภาพความละเอียดสูง Unsplash 100% ฟรี โหลดไว 0.01 วิ)
"""
import hashlib
import json
import logging
import os
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
REELS_DIR = ROOT_DIR / "reels_uploader"
TOOLS_DIR = ROOT_DIR / "tools"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REELS_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

logger = logging.getLogger("VisualHookEngine")

# คลังภาพถ่ายจริงความละเอียดสูง (Curated High-Impact Photography Registry)
# คัดสรรช่างภาพระดับ Editorial จาก Unsplash/Stock จริง ไม่มีภาพการ์ตูน AI 100%
CURATED_HOOK_REGISTRY = {
    # 1. คนแสดงสีหน้าตกใจ อ้าปากค้าง ไม่อยากเชื่อสายตา (Shocked / Surprised Reaction)
    "SHOCKED_REACTION": [
        "https://images.unsplash.com/photo-1578496781985-452d4a934d50?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=800&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=800&auto=format&fit=crop",
    ],
    # 2. ปัญหาบ้าน/ของพัง/คราบสกปรก ก่อน-หลัง (Before & After / Problem Hook)
    "BEFORE_AFTER_PROBLEM": [
        "https://images.unsplash.com/photo-1584992236310-6edddc08acff?w=800&auto=format&fit=crop",  # กระทะไหม้ คราบดำ
        "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=800&auto=format&fit=crop",  # ท่อน้ำ กลิ่นอับ
        "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=800&auto=format&fit=crop",  # ตู้เสื้อผ้ารก
        "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=800&auto=format&fit=crop",  # กาต้มน้ำ คราบตะกรัน
        "https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?w=800&auto=format&fit=crop",  # คราบกาวเหนียว
    ],
    # 3. คนทำงานเครียด งานล้นมือ ประชุมยาว ปวดหัวกับคอมพิวเตอร์ (Work Overwhelm Hook)
    "WORK_OVERWHELM": [
        "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=800&auto=format&fit=crop",  # กุมขมับหน้าจอ
        "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800&auto=format&fit=crop",  # เอกสารกองโต
        "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&auto=format&fit=crop",  # จอคอมพิวเตอร์ Inbox
        "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=800&auto=format&fit=crop",  # ประชุมยาวเหนื่อยล้า
        "https://images.unsplash.com/photo-1507207611509-ec012433ff52?w=800&auto=format&fit=crop",  # เครียดเวลางาน
    ],
    # 4. โชคลาภ มหาสมบัติ พลังงานดวงดาว ฮวงจุ้ย (Fortune & Mystic Energy Hook)
    "FORTUNE_MYSTIC": [
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop",  # พลังงานสีทองจักรวาล
        "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop",  # ดวงดาวมงคล
        "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=800&auto=format&fit=crop",  # ธนบัตร กระเป๋าเงิน
        "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=800&auto=format&fit=crop",  # สีมงคล แฟชั่นโชคลาภ
        "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?w=800&auto=format&fit=crop",  # สีเสื้อมงคลทักษา
    ],
    # 5. ข่าวด่วนประเด็นร้อน & คนดังสปอตไลท์ (Breaking News & Celebrity Spotlight)
    "BREAKING_SPOTLIGHT": [
        "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800&auto=format&fit=crop",  # ไมโครโฟนแถลงข่าว
        "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800&auto=format&fit=crop",  # แฟชั่นคนดัง
        "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800&auto=format&fit=crop",  # สปอตไลท์เวที
        "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800&auto=format&fit=crop",  # บรรยากาศงานอีเวนต์
    ]
}


def search_pexels_hook_photo(query: str) -> Optional[str]:
    """ค้นหาภาพถ่ายคนจริงแนวตั้ง (Portrait 9:16) จาก Pexels API ฟรี"""
    api_key = os.getenv("PEXELS_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": api_key, "User-Agent": "Mozilla/5.0"}
        params = {"query": query, "orientation": "portrait", "per_page": 5}
        r = httpx.get(url, headers=headers, params=params, timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            photos = data.get("photos", [])
            if photos:
                chosen = random.choice(photos)
                src = chosen.get("src", {})
                return src.get("large2x") or src.get("large") or src.get("portrait")
    except Exception as e:
        logger.warning(f"ค้นหา Pexels API ล้มเหลว ({query}): {e}")
    return None


def search_tavily_hook_photo(query: str) -> Optional[str]:
    """ค้นหาภาพถ่ายจริงหรือ Before/After จาก Tavily Live Search"""
    api_key = (os.getenv("TAVILY_API_KEY") or "").split(",")[0].strip()
    if not api_key:
        return None
    try:
        payload = {
            "api_key": api_key,
            "query": f"{query} high resolution authentic photography",
            "include_images": True,
            "max_results": 4
        }
        r = httpx.post("https://api.tavily.com/search", json=payload, timeout=5.0)
        if r.status_code == 200:
            images = r.json().get("images", [])
            valid_imgs = [
                img for img in images
                if img.startswith("http") and not any(x in img.lower() for x in ["icon", "logo", "avatar", "advertisement", "1x1"])
            ]
            if valid_imgs:
                return random.choice(valid_imgs[:3])
    except Exception as e:
        logger.warning(f"ค้นหา Tavily Images ล้มเหลว ({query}): {e}")
    return None


def get_phase1_hook_image_url(topic_data: dict, mode: str) -> str:
    """ส่งคืน URL ภาพฮุก 3 วินาทีแรก (Phase 1) ที่หยุดนิ้วคนดูได้ดีที่สุด
    
    ลำดับความสำคัญ:
    1. ถ้าเป็นข่าวด่วนหรือคนดังที่มีภาพข่าวจริงตรงปก (BBC/Sanook/ไทยรัฐ) -> ใช้ภาพข่าวจริงตรงปก
    2. ค้นหาภาพอารมณ์คนจริง (Shocked Face) หรือ Before/After ตรงประเด็นผ่าน Pexels / Tavily
    3. Fallback สู่คลังภาพ Curated High-Impact Registry (โหลดไว 0.01 วิ คมชัดสูง)
    """
    title = topic_data.get("title", "")
    hook = topic_data.get("hook", "")
    existing_imgs = topic_data.get("image_urls") or ([topic_data.get("image_url")] if topic_data.get("image_url") else [])

    # 1. กรณีข่าวด่วน หรือคนดัง ที่มีรูปภาพข่าวจริงผูกมาแล้ว 100% -> ให้ความสำคัญกับภาพข่าวจริง
    if mode in ("TRENDING_NEWS", "CELEBRITY_TREND") and existing_imgs and existing_imgs[0]:
        img0 = existing_imgs[0]
        if not any(k in img0 for k in ["ptcdn.info", "avatar", "icon"]):
            return img0

    # 2. แปลงหัวข้อเป็นคีย์เวิร์ดภาษาอังกฤษเพื่อค้นหาภาพคนจริง/Before-After
    search_terms = []
    if "กระทะไหม้" in title or "หม้อไหม้" in title:
        search_terms = ["burnt pan dirty vs clean before after photo", "cleaning burnt cooking pot"]
    elif "ท่อ" in title or "กลิ่นอับ" in title or "มด" in title:
        search_terms = ["bathroom pipe drain cleaning photo", "disgusted person bad smell face photo"]
    elif "เสื้อ" in title or "ตู้เสื้อผ้า" in title:
        search_terms = ["messy messy clothes wardrobe before after", "surprised woman holding clothes"]
    elif "หัวหน้า" in title or "งาน" in title or "ประชุม" in title:
        search_terms = ["stressed office worker overwhelmed desk photo", "surprised corporate employee laptop"]
    elif "ดวง" in title or "สีเสื้อ" in title or "ราศี" in title:
        search_terms = ["golden wealth money luck astrology energy", "happy person winning holding money"]
    else:
        search_terms = ["shocked face reaction person photo", "amazed surprised human expression"]

    # 3. ลองค้นหาผ่าน Pexels API (ถ้ามี Key)
    for term in search_terms:
        pex_img = search_pexels_hook_photo(term)
        if pex_img:
            return pex_img

    # 4. ลองค้นหาผ่าน Tavily Live Search
    for term in search_terms[:1]:
        tav_img = search_tavily_hook_photo(term)
        if tav_img:
            return tav_img

    # 5. คัดเลือกจาก Curated High-Impact Registry ตามโหมดเนื้อหา
    if mode == "LIFE_HACK_TIP":
        # สลับระหว่างภาพปัญหา Before/After กับภาพคนทำหน้าตกใจ
        pool = CURATED_HOOK_REGISTRY["BEFORE_AFTER_PROBLEM"] + CURATED_HOOK_REGISTRY["SHOCKED_REACTION"]
    elif mode == "WORK_PRODUCTIVITY":
        pool = CURATED_HOOK_REGISTRY["WORK_OVERWHELM"] + CURATED_HOOK_REGISTRY["SHOCKED_REACTION"]
    elif mode == "LUCKY_FORTUNE":
        pool = CURATED_HOOK_REGISTRY["FORTUNE_MYSTIC"]
    elif mode == "CELEBRITY_TREND":
        pool = CURATED_HOOK_REGISTRY["BREAKING_SPOTLIGHT"] + CURATED_HOOK_REGISTRY["SHOCKED_REACTION"]
    else:
        pool = CURATED_HOOK_REGISTRY["BREAKING_SPOTLIGHT"] + CURATED_HOOK_REGISTRY["SHOCKED_REACTION"]

    # สุ่มเลือกแบบกระจายตาม hash ของชื่อเรื่อง เพื่อไม่ให้ซ้ำซากแต่คงที่สำหรับเรื่องเดียวกัน
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(pool)
    return pool[idx]
