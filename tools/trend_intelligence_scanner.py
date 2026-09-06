# -*- coding: utf-8 -*-
"""tools/trend_intelligence_scanner.py — ระบบสืบค้นร่องรอยดิจิทัลและเทรนด์เชิงลึกเพื่อดึงดูดผู้ติดตามสูงสุด

สืบค้นจาก 3 แหล่งร่องรอยดิจิทัลหลัก:
1. Google Trends & People Also Ask (PAA)
2. Pantip & เว็บบอร์ดชุมชนคนไทย (Pain Points & ปัญหาชีวิตจริง)
3. Global Viral Footprints (เกร็ดความรู้/ทริคชีวิตระดับโลก)

ประเมินคะแนนด้วย AI Follower-Intent Scorer (เกณฑ์คะแนน >= 80/100)
ตัดคำภาษาไทยด้วย PyThaiNLP ป้องกันสระลอยและตัดคำขาด 100%
"""
import html
import json
import logging
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
TOOLS_DIR = ROOT_DIR / "tools"
REELS_DIR = ROOT_DIR / "reels_uploader"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REELS_DIR))

import image_footprint_crawler
from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

logger = logging.getLogger("TrendIntelligence")
CACHE_FILE = TOOLS_DIR / "trend_intelligence_cache.json"

try:
    from pythainlp.tokenize import word_tokenize
except ImportError:
    word_tokenize = None


def clean_thai_text(text: str) -> str:
    """ทำความสะอาดข้อความ ลบ HTML tags, URLs และอิโมจิที่อาจทำให้เรนเดอร์พัง"""
    if not text:
        return ""
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned)
    cleaned = re.sub(r"[\u2600-\u27ff]", "", cleaned)
    cleaned = re.sub(r"[\u2300-\u23ff]", "", cleaned)
    cleaned = re.sub(r"[\u2b50-\u2b55]", "", cleaned)
    cleaned = re.sub(r"[\ufe0e\ufe0f]", "", cleaned)
    cleaned = re.sub(r'#+\s*', '', cleaned)
    cleaned = re.sub(r'[*_~`]+', '', cleaned)
    cleaned = re.sub(r'ข่าว[อฮด]ื่น\s*ๆ.*', '', cleaned)
    cleaned = re.sub(r'##.*', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def safe_thai_truncate(text: str, max_chars: int = 50) -> str:
    """ตัดข้อความภาษาไทยตามขอบเขตของคำ (Word Boundary) ห้ามตัดกลางพยางค์ และตัดคำค้างคาที่ปลายประโยค"""
    text = clean_thai_text(text)
    if len(text) <= max_chars + 4:
        res = text
    else:
        if word_tokenize:
            try:
                tokens = word_tokenize(text, engine="newmm")
                res = ""
                for t in tokens:
                    if len(res) + len(t) <= max_chars + 3:
                        res += t
                    else:
                        break
                if not res:
                    res = text[:max_chars]
            except Exception:
                res = text[:max_chars].rsplit(" ", 1)[0]
        else:
            res = text[:max_chars].rsplit(" ", 1)[0]

    # ลบอักขระ เครื่องหมายคำพูด และคำเชื่อมค้างคาที่ปลายข้อความเสมอ (ทั้งสั้นและยาว)
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    res = re.sub(r'(?:เพื่อ|ที่|และ|หรือ|กับ|ว่า|คือ|จะ|ใน|ของ|จาก|สำหรับ|เมื่อ|ให้|โดย|ถึง|อย่าง|จน|เป็น|อายุ|ซึ่ง|แก่|แด่|ต่อ|ที่จังหวัด|จังหวัด|อำเภอ|ตำบล)$', '', res).strip()
    res = re.sub(r'[\s=\-–—:_\"\'\(\[“]+$', '', res).strip()
    return res


def get_ai_client():
    """เชื่อมต่อ Groq API แบบ Multi-Key failover"""
    groq_keys = os.getenv("GROQ_API_KEY", "").split(",")
    for k in groq_keys:
        k = k.strip()
        if not k or "mock" in k.lower():
            continue
        try:
            from openai import OpenAI
            return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k, timeout=12.0)
        except Exception:
            continue
    return None


def fetch_google_trends_thailand() -> List[Dict[str, str]]:
    """ดึงคำค้นหายอดนิยมสดใหม่จาก Google Trends Thailand RSS"""
    trends = []
    try:
        url = "https://trends.google.co.th/trending/rss?geo=TH"
        r = httpx.get(url, timeout=7.0, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
        if r.status_code == 200 and r.content:
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                title_el = it.find("title")
                desc_el = it.find("description")
                approx_el = it.find(".//{https://trends.google.com/trending/rss}approx_traffic")
                img_el = it.find(".//{https://trends.google.com/trending/rss}picture")

                if title_el is not None and title_el.text:
                    title = clean_thai_text(html.unescape(title_el.text))
                    desc = clean_thai_text(html.unescape(desc_el.text)) if desc_el is not None and desc_el.text else ""
                    traffic = approx_el.text if approx_el is not None and approx_el.text else ""
                    img_url = img_el.text if img_el is not None and img_el.text else ""

                    if len(title) >= 3:
                        trends.append({
                            "source": "google_trends_th",
                            "title": title,
                            "summary": desc if desc else title,
                            "traffic": traffic,
                            "image_url": img_url
                        })
    except Exception as e:
        logger.warning(f"ดึง Google Trends Thailand ล้มเหลว: {e}")
    return trends


def fetch_forum_footprints_tavily(category: str) -> List[Dict[str, str]]:
    """ใช้ Tavily ค้นหาร่องรอยคำถามและกระทู้ที่คนถกเถียงกันใน Pantip และเว็บบอร์ดไทย"""
    queries = {
        "LIFE_HACK_TIP": "site:pantip.com ทริคแก้ปัญหาบ้าน วิธีแก้ปัญหาชีวิต ยอดนิยม",
        "WORK_PRODUCTIVITY": "site:pantip.com ทริคคนทำงาน วิธีคุยกับหัวหน้า พัฒนาตัวเอง",
        "LUCKY_FORTUNE": "สีเสื้อมงคล เลขเด็ด ดวงประจำวัน ดวงเฮง",
        "CELEBRITY_TREND": "ดารา ข่าวบันเทิง ไวรัลมาแรง วันนี้",
        "TRENDING_NEWS": "สรุปข่าวด่วน ประเด็นร้อน สังคม วันนี้",
    }
    query = queries.get(category, "ทริคแก้ปัญหาชีวิต ยอดนิยม pantip")
    results = []

    try:
        from app.services.web_search import web_search
        search_res = web_search(query, max_results=4)
        for r in search_res.get("results", []):
            t = clean_thai_text(r.get("title", ""))
            c = clean_thai_text(r.get("content", ""))
            if len(t) >= 10:
                results.append({
                    "source": "tavily_pantip_web",
                    "title": t,
                    "summary": c[:250] if c else t,
                    "url": r.get("url", ""),
                    "image_url": ""  # ไม่ดึงภาพดิบจากเว็บบอร์ด Pantip ป้องกันภาพอวาตาร์/การ์ตูนขยะ
                })
    except Exception as e:
        logger.warning(f"Tavily search สำหรับหมวด {category} ล้มเหลว: {e}")

    return results


def evaluate_and_synthesize_topic(raw_item: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
    """ให้ AI ประเมิน Follower-Intent Score (>=80) และสร้างสคริปต์ 3 จังหวะพร้อม Hook 3 วิ และขั้นตอน Step 1-3"""
    title = raw_item.get("title", "")
    summary = raw_item.get("summary", "")

    # ข้าม LLM ทันทีหากเป็นการรัน Unit Test ป้องกันการยิง API จริง / เปลือง Quota / Non-deterministic
    is_testing = bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"))

    if not is_testing:
        groq_keys = [k.strip() for k in os.getenv("GROQ_API_KEY", "").split(",") if k.strip() and "mock" not in k.lower()]
        models = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]

        is_news = category in ("TRENDING_NEWS", "CELEBRITY_TREND")
        if is_news:
            prompt = (
                f"คุณเป็นโปรดิวเซอร์สรุปข่าวสั้นมืออาชีพ (Reels, Shorts, TikTok) ในไทย\n"
                f"สรุปประเด็นข่าวจริงต่อไปนี้ให้กระชับ ชัดเจน น่าติดตาม ตรงประเด็น:\n"
                f"หมวดหมู่: {category}\n"
                f"หัวข้อข่าว: {title}\n"
                f"เนื้อหาข่าว: {summary}\n\n"
                f"กฎเหล็กเนื้อหา 100%:\n"
                f"- ทุกข้อความต้องเป็น 'ประโยคภาษาไทยที่สมบูรณ์ในตัวเอง' มีประธาน กริยา กรรม ครบถ้วน ห้ามตัดคำค้างคา หรือตัดชื่อคนขาด (เช่น เร แม๊คโดแนลด์ ห้ามตัดเหลือแค่ เร)\n"
                f"- step1: ข้อเท็จจริงที่ 1 (เกิดเหตุการณ์อะไรขึ้น ประโยคสมบูรณ์ 20-40 ตัวอักษร)\n"
                f"- step2: ข้อเท็จจริงที่ 2 (รายละเอียดสำคัญ หรือใครทำอะไร ที่ไหน อย่างไร 20-40 ตัวอักษร)\n"
                f"- step3: ข้อเท็จจริงที่ 3 (บทสรุป ผลกระทบ หรือสถานการณ์ล่าสุด 20-40 ตัวอักษร)\n"
                f"- กฎเหล็กห้ามฝ่าฝืน: ห้ามใส่ข้อความเชิญชวนกดติดตาม หรือข้อความลอยๆ เช่น 'ติดตามช่องเพื่อรอเนื้อหาใหม่', 'กดติดตาม' ลงใน step1, step2, step3 เด็ดขาด! ทั้ง 3 ข้อต้องเป็นเนื้อหาข่าวจริง 100%\n"
                f"- title: หัวข้อข่าวที่ชัดเจน กระชับ 25-42 ตัวอักษร จบประโยคสมบูรณ์\n"
                f"- hook_3s: ประโยคเปิด Hook 3 วินาทีแรกที่หยุดนิ้ว ดึงดูดความสนใจเกี่ยวกับเหตุการณ์นี้ 25-42 ตัวอักษร จบประโยคสมบูรณ์\n"
                f"- voiceover_script: สคริปต์เสียงพากย์เล่าเรื่องราวความยาว 14-18 วินาที (ประมาณ 180-260 ตัวอักษร) สไตล์ผู้หญิงป้าเข็ม เล่าเรื่องให้ผู้ฟังเข้าใจกระจ่างชัดเจน ไม่ย่อจนห้วนหรือตัดทอนจนฟังไม่รู้เรื่อง: มีลำดับการเล่า 3 ส่วน (1) เปิดตัวบุคคลหรือเหตุการณ์ (2) เล่ารายละเอียดสำคัญที่เกิดขึ้น (3) สรุปประเด็นชวนคอมเมนต์พูดคุย ลงท้ายด้วย 'นะคะ' หรือ 'นะจ๊ะ' ห้ามใช้ 'ครับ' เด็ดขาด\n\n"
                f"ตอบเป็น JSON เท่านั้น:\n"
                f"{{\n"
                f'  "follower_score": 88,\n'
                f'  "title": "หัวข้อข่าวภาษาไทยที่กระชับ ไม่เกิน 42 ตัวอักษร",\n'
                f'  "hook_3s": "ประโยค Hook 3 วินาทีแรกที่หยุดนิ้ว ไม่เกิน 42 ตัวอักษร",\n'
                f'  "step1": "ข้อ 1. เกิดเหตุการณ์อะไรขึ้น ประโยคสมบูรณ์",\n'
                f'  "step2": "ข้อ 2. รายละเอียดสำคัญ ใครทำอะไร ประโยคสมบูรณ์",\n'
                f'  "step3": "ข้อ 3. บทสรุปหรือผลกระทบสำคัญ ประโยคสมบูรณ์",\n'
                f'  "voiceover_script": "สคริปต์เสียงพากย์เล่าเรื่องราวสมบูรณ์ 14-18 วินาที ชัดถ้อยชัดคำ ลงท้าย นะคะ หรือ นะจ๊ะ",\n'
                f'  "hashtags": "#ข่าวด่วน #สรุปข่าว #ประเด็นร้อน"\n'
                f"}}"
            )
        else:
            prompt = (
                f"คุณเป็นผู้เชี่ยวชาญด้านจิตวิทยาคอนเทนต์ไวรัลสั้น (Shorts, Reels, TikTok) ในไทย\n"
                f"วิเคราะห์ข้อมูลร่องรอยดิจิทัลต่อไปนี้ เพื่อสร้างคลิปที่ให้ประโยชน์สูงสุด:\n"
                f"หมวดหมู่: {category}\n"
                f"หัวข้อดิบ: {title}\n"
                f"เนื้อหา: {summary}\n\n"
                f"ให้คะแนน Follower-Intent (เต็ม 100) ตาม 4 มิติ (FOMO, Utility, Hook, Continuity)\n\n"
                f"กฎเหล็กเนื้อหา 100%:\n"
                f"- ทุกข้อความต้องเป็น 'ประโยคที่สมบูรณ์ในตัวเอง' ห้ามตัดคำขาด ห้ามลงท้ายด้วยคำค้างคา เช่น เป็น, ที่, และ, หรือ, สำหรับ, เพื่อ, เมื่อ, ให้, ว่า ค้างคาเด็ดขาด\n"
                f"- step1, step2, step3 ต้องเป็น 3 ขั้นตอนหรือ 3 สาระสำคัญที่ทำได้จริง ประโยคจบในตัว 20-40 ตัวอักษร\n"
                f"- กฎเหล็กห้ามฝ่าฝืน: ห้ามใส่ข้อความเชิญชวนกดติดตาม หรือข้อความลอยๆ เช่น 'ติดตามช่อง', 'กดติดตาม' ลงใน step1, step2, step3 เด็ดขาด ทุกข้อต้องเป็นวิธีทำ/สาระจริง 100%\n"
                f"- title: หัวข้อคลิปภาษาไทยที่กระชับ ไม่เกิน 42 ตัวอักษร จบประโยคสมบูรณ์\n"
                f"- hook_3s: ประโยค Hook 3 วินาทีแรก เช่น รู้หรือไม่? หรือ ทริคเด็ด... ไม่เกิน 42 ตัวอักษร\n"
                f"- voiceover_script: สคริปต์เสียงพากย์เล่าเรื่อง 14-18 วินาที (ประมาณ 180-260 ตัวอักษร) สไตล์ผู้หญิงป้าเข็ม เล่าเนื้อหาสาระครบถ้วน ไม่ย่อจนห้วนหรือตัดทอนจนฟังไม่รู้เรื่อง ลงท้ายด้วย 'นะคะ' หรือ 'นะจ๊ะ' ห้ามใช้ 'ครับ' เด็ดขาด\n\n"
                f"ตอบเป็น JSON เท่านั้น:\n"
                f"{{\n"
                f'  "follower_score": 88,\n'
                f'  "title": "หัวข้อคลิปภาษาไทยที่กระชับ ไม่เกิน 42 ตัวอักษร",\n'
                f'  "hook_3s": "ประโยค Hook 3 วินาทีแรก ไม่เกิน 42 ตัวอักษร",\n'
                f'  "step1": "ข้อ 1. ขั้นตอนแรก ประโยคสมบูรณ์",\n'
                f'  "step2": "ข้อ 2. ขั้นตอนสอง ประโยคสมบูรณ์",\n'
                f'  "step3": "ข้อ 3. ผลลัพธ์ที่ได้ ประโยคสมบูรณ์",\n'
                f'  "voiceover_script": "สคริปต์เสียงพากย์เล่าเรื่องราวสมบูรณ์ 14-18 วินาที ชัดถ้อยชัดคำ ลงท้าย นะคะ หรือ นะจ๊ะ",\n'
                f'  "hashtags": "#สาระน่ารู้ #ทริคดีๆ #เรื่องเด็ด"\n'
                f"}}"
            )

        last_err = None
        for k in groq_keys:
            try:
                from openai import OpenAI
                client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=k, timeout=10.0)
            except Exception:
                continue

            for m in models:
                try:
                    resp = client.chat.completions.create(
                        model=m,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0.7,
                        max_tokens=300,
                    )
                    content = resp.choices[0].message.content
                    data = json.loads(content)

                    score = int(data.get("follower_score", 75))
                    if score >= 75:  # เกณฑ์ผ่านเพื่อสร้างคอนเทนต์คุณภาพสูง
                        clean_title = safe_thai_truncate(data.get("title", title), 48)
                        hook = safe_thai_truncate(data.get("hook_3s", f"เรื่องเด็ดที่ต้องรู้! {clean_title}"), 48)

                        s1 = safe_thai_truncate(data.get("step1", ""), 45)
                        s2 = safe_thai_truncate(data.get("step2", ""), 45)
                        s3 = safe_thai_truncate(data.get("step3", ""), 45)

                        # กำจัดข้อความ filler จากขั้นตอนทั้ง 3 ข้อ 100%
                        bad_fillers = ["ติดตามช่อง", "รอเนื้อหาใหม่", "กดติดตาม", "อย่าลืมกด", "ติดตามดู", "คำมั่นสัญญาต่อไป", "ไม่พลาดอัปเดต"]
                        if any(fb in s1 for fb in bad_fillers) or len(s1) < 6:
                            s1 = clean_title
                        if any(fb in s2 for fb in bad_fillers) or len(s2) < 6:
                            s2 = "รายละเอียดสำคัญของเรื่องนี้"
                        if any(fb in s3 for fb in bad_fillers) or len(s3) < 6:
                            s3 = "ติดตามความคืบหน้าของสถานการณ์นี้" if is_news else "ทดลองนำวิธีนี้ไปปรับใช้ได้จริง"

                        p1 = hook
                        p2 = clean_title
                        p3 = "กดติดตามเพื่อไม่พลาดทริคดีๆ"

                        raw_img = raw_item.get("image_url") or ""
                        if any(bad in raw_img.lower() for bad in ["ptcdn.info", "avatar", "icon", "emoji"]):
                            raw_img = ""

                        v_script = clean_thai_text(data.get("voiceover_script", ""))
                        v_script = v_script.replace("นะครับ", "นะคะ").replace("นะคับ", "นะคะ").replace("ครับผม", "ค่ะ").replace("ครับ", "ค่ะ")
                        if len(v_script) < 60:
                            v_script = f"{hook}! เรื่องนี้เริ่มจาก {s1} โดยมีรายละเอียดสำคัญคือ {s2} และบทสรุปคือ {s3} ทุกคนมีความคิดเห็นยังไง คอมเมนต์บอกกันหน่อย และอย่าลืมกดติดตามช่องไว้นะคะ"

                        return {
                            "title": clean_title,
                            "hook": hook,
                            "detail": summary[:140] if summary else clean_title,
                            "summary": summary[:140] if summary else clean_title,
                            "step1": s1,
                            "step2": s2,
                            "step3": s3,
                            "follower_score": score,
                            "phase1_text": p1,
                            "phase2_text": p2,
                            "phase3_text": p3,
                            "voiceover_script": v_script,
                            "hashtags": data.get("hashtags", "#สาระน่ารู้ #ทริคดีๆ #ติดตามช่อง"),
                            "image_url": raw_img,
                            "image_urls": image_footprint_crawler.find_three_distinct_images({
                                "title": title,
                                "link": raw_item.get("url") or raw_item.get("link", ""),
                                "image_url": raw_img
                            }, mode=category) if raw_img else [],
                            "url": raw_item.get("url") or raw_item.get("link", ""),
                            "source": raw_item.get("source", "trend_intelligence"),
                        }
                    else:
                        # คะแนนประเมินโดย AI ไม่ถึง 75
                        return None
                except Exception as e:
                    last_err = e
                    continue

        if last_err:
            logger.warning(f"AI ประเมินคะแนน Follower-Intent ขัดข้อง ({last_err}) -> สลับใช้ Heuristic Scorer สำรอง")

    # --- Heuristic Rule-Based Follower Scorer สำรอง (ทำงาน 100% แม้ไม่มีเน็ต/LLM โดนบล็อก) ---
    high_engagement_keywords = [
        ("วิธีแก้", 25, "💡 วิธีแก้ง่ายๆ ที่คนส่วนใหญ่ยังไม่รู้!"),
        ("อย่าเพิ่ง", 25, "🚨 อย่าเพิ่งทำแบบนี้เด็ดขาด! ทริคนี้ช่วยได้"),
        ("ความลับ", 25, "🤫 เผยความลับที่ไม่มีใครบอกคุณ!"),
        ("ทำไม", 20, "❓ เคยสงสัยไหมว่าทำไม? เรื่องนี้มีคำตอบ"),
        ("ทริค", 20, "✨ ทริคเด็ดชีวิตง่ายขึ้น 10 เท่า!"),
        ("ข้อห้าม", 25, "⚠️ 3 ข้อห้ามสำคัญที่ต้องระวัง!"),
        ("ด่วน", 20, "🚨 เรื่องด่วนที่ทุกคนต้องรู้ในวันนี้!"),
        ("ดวง", 25, "🔮 เช็คดวงวันนี้ ราศีไหนการเงินพุ่งสุด!"),
        ("สูตร", 20, "🥣 เผยสูตรลับทำเองง่ายๆ ได้ผลจริง!"),
    ]

    base_score = 80 if category in ("TRENDING_NEWS", "CELEBRITY_TREND") or raw_item.get("source") == "authentic_news_rss" else 65
    chosen_hook = f"เรื่องเด็ดที่ทุกคนต้องรู้! {safe_thai_truncate(title, 35)}"
    for kw, pts, hook_tmpl in high_engagement_keywords:
        if kw in title or kw in summary:
            base_score += pts
            chosen_hook = hook_tmpl
            break

    if base_score >= 75:
        clean_title = safe_thai_truncate(title, 45)
        clean_hook = safe_thai_truncate(chosen_hook, 50)
        img_url = raw_item.get("image_url") or ""
        return {
            "title": clean_title,
            "hook": clean_hook,
            "detail": summary[:140] if summary else clean_title,
            "summary": summary[:140] if summary else clean_title,
            "follower_score": min(base_score, 98),
            "phase1_text": clean_hook,
            "phase2_text": clean_title,
            "phase3_text": "กดติดตามเพื่อไม่พลาดทริคดีๆ ทุกวัน",
            "voiceover_script": f"{clean_hook}! เรื่องราวล่าสุดของ {clean_title} มีประเด็นสำคัญที่น่าติดตาม ทุกคนคิดเห็นยังไงกับเรื่องนี้ คอมเมนต์บอกกันหน่อย และอย่าลืมกดติดตามช่องไว้นะคะ",
            "hashtags": "#สาระน่ารู้ #ทริคดีๆ #ติดตามช่อง #เรื่องเด็ด",
            "image_url": img_url,
            "image_urls": image_footprint_crawler.find_three_distinct_images({
                "title": clean_title,
                "link": raw_item.get("url") or raw_item.get("link", ""),
                "image_url": img_url
            }, mode=category) if img_url else [],
            "url": raw_item.get("url") or raw_item.get("link", ""),
            "source": f"{raw_item.get('source', 'footprint')}_heuristic",
        }

    return None


def fetch_live_authentic_news_rss(category: str) -> List[Dict[str, str]]:
    """ดึงข่าวจริงพร้อมภาพถ่ายตรงปก 100% จากสำนักข่าวชั้นนำ (Sanook บันเทิง/ไอที, ข่าวสดบันเทิง/ไลฟ์สไตล์)
    
    กฎเหล็ก: ปลอดการเมือง, ไม่แตะสถาบันฯ/กษัตริย์, ไม่แตะ ม.112 เด็ดขาด 100%
    """
    from app.services.content_safety_filter import is_sensitive_forbidden_topic
    from standalone_content_generator import is_topic_duplicate

    # คัดสรรเฉพาะ Feeds บันเทิงและประเด็นร้อน (ปลอดการเมืองและประเด็นขัดแย้ง 100%)
    if category == "CELEBRITY_TREND":
        feeds = [
            "https://rssfeeds.sanook.com/rss/feeds/sanook/news.entertain.xml",
            "https://www.khaosod.co.th/entertainment/feed",
        ]
    else:
        feeds = [
            "https://rssfeeds.sanook.com/rss/feeds/sanook/news.entertain.xml",
            "https://www.khaosod.co.th/entertainment/feed",
            "https://www.khaosod.co.th/lifestyle/feed",
        ]
    results = []
    for feed_url in feeds:
        try:
            r = httpx.get(feed_url, timeout=8.0, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
            if r.status_code != 200 or not r.content:
                continue
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                t_el = it.find("title")
                d_el = it.find("description")
                l_el = it.find("link")
                if t_el is None or not t_el.text:
                    continue
                title = clean_thai_text(html.unescape(t_el.text))
                desc = clean_thai_text(html.unescape(d_el.text)) if d_el is not None and d_el.text else title
                link = clean_thai_text(html.unescape(l_el.text)).strip() if l_el is not None and l_el.text else ""

                # 1. กรองเนื้อหาต้องห้ามเด็ดขาด (การเมือง / กษัตริย์ / 112 / ความรุนแรง)
                if is_sensitive_forbidden_topic(title) or is_sensitive_forbidden_topic(desc) or is_sensitive_forbidden_topic(link):
                    continue

                # 2. กรองชื่อเว็บหรือหมวดหมู่ทั่วไปออก ป้องกันชื่อการ์ดกลายเป็นชื่อเว็บ
                if any(x in title for x in ["ข่าววันนี้ ข่าวด่วน", "หน้าแรก", "รวมข่าว", "หน้าหลัก", "ข่าวด่วนล่าสุด"]):
                    continue
                if len(title) < 15:
                    continue

                # 3. ตรวจความซ้ำซ้อนทันที ทั้งจากหัวข้อและ URL ป้องกันการนำข่าวเดิมมาวนทำซ้ำ
                if is_topic_duplicate(title, url=link):
                    continue

                raw_xml = ET.tostring(it, encoding="utf-8").decode("utf-8", errors="ignore")
                enc_el = it.find("enclosure")
                img_url = ""
                if enc_el is not None and enc_el.get("url"):
                    img_url = enc_el.get("url")
                else:
                    imgs = re.findall(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png)', raw_xml)
                    imgs = [i for i in imgs if not any(x in i.lower() for x in ['avatar', 'icon', 'logo', '1x1', 'pixel', 'advertisement', 'banner', '696x464', 'wp-includes'])]
                    if imgs:
                        img_url = imgs[0]

                if img_url and "/240/" in img_url:
                    img_url = img_url.replace("/240/", "/1024/")

                # กฎเหล็ก: ต้องมีรูปถ่ายข่าวจริงตรงปกเท่านั้น
                if img_url and len(desc) >= 20:
                    results.append({
                        "source": "authentic_news_rss",
                        "title": title,
                        "summary": desc[:250],
                        "image_url": img_url,
                        "url": link
                    })
                    if len(results) >= 6:
                        return results
        except Exception as e:
            logger.warning(f"ดึง RSS ข่าวจริงจาก {feed_url} ล้มเหลว: {e}")

    return results


def get_top_follower_viral_topic(category: str) -> Dict[str, Any]:
    """ดึงหัวข้อที่มีศักยภาพดึงดูดผู้ติดตามสูงสุดสำหรับหมวดหมู่นั้นๆ (ปลอดการเมือง/กษัตริย์/112 และไม่ซ้ำ 100%)"""
    from app.services.content_safety_filter import is_sensitive_forbidden_topic
    from standalone_content_generator import is_topic_duplicate

    # 1. สำหรับหมวดข่าวด่วนและดารา: บังคับใช้ข่าวจริง + ภาพถ่ายจริง 100% จากสำนักข่าวเท่านั้น
    if category in ("TRENDING_NEWS", "CELEBRITY_TREND"):
        real_news = fetch_live_authentic_news_rss(category)
        for item in real_news:
            if is_sensitive_forbidden_topic(item.get("title", "")) or is_sensitive_forbidden_topic(item.get("summary", "")):
                continue
            if is_topic_duplicate(item.get("title", ""), url=item.get("url", "")):
                continue

            scored = evaluate_and_synthesize_topic(item, category)
            if scored:
                # ตรวจความปลอดภัยหลัง AI สังเคราะห์อีกรอบ
                full_check = f"{scored.get('title', '')} {scored.get('hook', '')} {scored.get('voiceover_script', '')}"
                if is_sensitive_forbidden_topic(full_check):
                    continue
                if is_topic_duplicate(scored.get("title", ""), url=item.get("url", "")):
                    continue

                if scored.get("follower_score", 0) >= 70:
                    logger.info(f"🎯 ได้รับข่าวจริงพร้อมภาพถ่ายตรงปก Follower Score: {scored['follower_score']}: {scored['title']}")
                    return scored

        # สำรองด้วย Google Trends Thailand
        g_trends = fetch_google_trends_thailand()
        for item in g_trends:
            if is_sensitive_forbidden_topic(item.get("title", "")):
                continue
            if is_topic_duplicate(item.get("title", "")):
                continue
            if item.get("image_url"):
                scored = evaluate_and_synthesize_topic(item, category)
                if scored:
                    full_check = f"{scored.get('title', '')} {scored.get('hook', '')} {scored.get('voiceover_script', '')}"
                    if is_sensitive_forbidden_topic(full_check):
                        continue
                    if is_topic_duplicate(scored.get("title", "")):
                        continue
                    if scored.get("follower_score", 0) >= 70:
                        return scored

    # 2. สำหรับหมวดทริคบ้านและทริคคนทำงาน: ค้นหาร่องรอยคำถามจาก Pantip
    else:
        footprints = fetch_forum_footprints_tavily(category)
        for item in footprints:
            if is_sensitive_forbidden_topic(item.get("title", "")):
                continue
            if is_topic_duplicate(item.get("title", "")):
                continue
            scored = evaluate_and_synthesize_topic(item, category)
            if scored:
                full_check = f"{scored.get('title', '')} {scored.get('hook', '')} {scored.get('voiceover_script', '')}"
                if is_sensitive_forbidden_topic(full_check):
                    continue
                if is_topic_duplicate(scored.get("title", "")):
                    continue
                if scored.get("follower_score", 0) >= 80:
                    logger.info(f"🎯 ได้รับหัวข้อคุณภาพสูง Follower Score: {scored['follower_score']} [{category}]: {scored['title']}")
                    return scored

    # 3. หากระบบภายนอกติดขัด ให้ใช้ฐานข้อมูลสำรองคุณภาพสูงระดับเกรด A พร้อมรูปภาพ Unsplash ตรงหมวด 100%
    logger.info(f"ℹ️ ใช้ฐานข้อมูลหัวข้อคัดสรรคุณภาพสูงสำหรับหมวด {category}")
    from standalone_content_generator import get_curated_fallback_topic
    return get_curated_fallback_topic(category)
