"""
Creative Brief Generator — สร้างชิ้นงานโฆษณา 3 มุมมองสำหรับ Meta Ads

ตามหลัก "Creative is Targeting" (ยุค AI ของ Meta):
- มุม 1: แก้ปัญหา (Problem → Solution) — สำหรับคนที่มีพฤติกรรมชอบมองหาทางแก้ปัญหา
- มุม 2: รีวิว/Social Proof — สำหรับคนชอบดูรีวิว
- มุม 3: ให้ความรู้ (Education) — สำหรับคนที่ชอบหาข้อมูลประกอบการตัดสินใจ

AI (Andromeda) จะเลือกชิ้นงานที่เหมาะสมที่สุดไปแสดงผลให้ตรงกับพฤติกรรมลูกค้าแต่ละคนเอง
"""

import json
import logging
from typing import List, Optional

from app.config import settings
from app.services.llm_clients import call_with_backoff, parse_llm_json, groq_json_schema_format
from app.services.persona import persona_system_prompt

logger = logging.getLogger(__name__)

# --- Perspective Definitions ---
PERSPECTIVES = {
    "problem_solution": {
        "name": "แก้ปัญหา",
        "description": "สำหรับคนที่มีพฤติกรรมชอบมองหาทางแก้ปัญหา — เน้น痛点 แล้วเสนอสินค้าเป็นทางออก",
        "prompt_guidance": (
            "มุม \"แก้ปัญหา\" — เน้นไปที่ปัญหา/ความเจ็บปวดที่ลูกค้าเจอจริงๆ แล้วนำเสนอสินค้าเป็นทางออกที่ชัดเจน\n"
            "- Hook: หยุดปัญหาให้เห็นชัดใน 3 วินาทีแรก (เช่น 'เบื่อมั้ยที่...')\n"
            "- Script: เล่าปัญหาให้รู้สึกว่าใช่ → โชว์สินค้าเป็นทางออก → ย้ำผลลัพธ์\n"
            "- CTA: เน้นความง่ายในการสั่งซื้อ\n"
            "- Format: วิดีโอแนวตั้ง 15-30 วินาที ถือกล้องรีวิวสดๆ"
        ),
    },
    "review": {
        "name": "รีวิว/Social Proof",
        "description": "สำหรับคนชอบดูรีวิว — เน้นความคิดเห็นจริง + โชว์สินค้าจริง",
        "prompt_guidance": (
            "มุม \"รีวิว\" — เน้น Social Proof ความคิดเห็นจริง ความประทับใจจริง\n"
            "- Hook: 'คนซื้อไปแล้วพูดว่า...' หรือ 'สิ่งที่ไม่มีใครบอก...'\n"
            "- Script: โชว์สินค้าจริง → เล่าความประทับใจ/ข้อดีข้อเสียจริง → เปรียบเทียบ\n"
            "- CTA: เน้นรีวิวจริง เชื่อถือได้\n"
            "- Format: UGC-style กล้องมือสั่นนิดๆ ดูเป็นธรรมชาติ 30-60 วินาที"
        ),
    },
    "education": {
        "name": "ให้ความรู้",
        "description": "สำหรับคนที่ชอบหาความรู้ประกอบการตัดสินใจ — เน้นเกร็ดความรู้ + แนะนำสินค้า",
        "prompt_guidance": (
            "มุม \"ให้ความรู้\" — เน้นเกร็ดความรู้ เทคนิค วิธีเลือก ข้อมูลประกอบ\n"
            "- Hook: 'รู้มั้ยว่า...' หรือ '3 เทคนิคเลือก X ให้ถูก'\n"
            "- Script: ให้ความรู้/เกร็ด → ใช้สินค้าเป็นตัวอย่าง → สรุปข้อดี\n"
            "- CTA: เน้นตัดสินใจง่ายขึ้นหลังได้ข้อมูล\n"
            "- Format: Talking head + Text overlay สั้นๆ 30-60 วินาที"
        ),
    },
}

# JSON Schema สำหรับ Groq json_schema (strict)
BRIEF_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "problem_solution": {
            "type": "object",
            "properties": {
                "hook": {"type": "string"},
                "script_body": {"type": "string"},
                "cta": {"type": "string"},
                "caption": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
                "target_behavior": {"type": "string"},
                "thumbnail_prompt": {"type": "string"},
                "ai_confidence": {"type": "integer"},
            },
            "required": ["hook", "script_body", "cta", "caption", "hashtags", "target_behavior", "thumbnail_prompt", "ai_confidence"],
            "additionalProperties": False,
        },
        "review": {
            "type": "object",
            "properties": {
                "hook": {"type": "string"},
                "script_body": {"type": "string"},
                "cta": {"type": "string"},
                "caption": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
                "target_behavior": {"type": "string"},
                "thumbnail_prompt": {"type": "string"},
                "ai_confidence": {"type": "integer"},
            },
            "required": ["hook", "script_body", "cta", "caption", "hashtags", "target_behavior", "thumbnail_prompt", "ai_confidence"],
            "additionalProperties": False,
        },
        "education": {
            "type": "object",
            "properties": {
                "hook": {"type": "string"},
                "script_body": {"type": "string"},
                "cta": {"type": "string"},
                "caption": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
                "target_behavior": {"type": "string"},
                "thumbnail_prompt": {"type": "string"},
                "ai_confidence": {"type": "integer"},
            },
            "required": ["hook", "script_body", "cta", "caption", "hashtags", "target_behavior", "thumbnail_prompt", "ai_confidence"],
            "additionalProperties": False,
        },
    },
    "required": ["problem_solution", "review", "education"],
    "additionalProperties": False,
}


def _build_system_prompt(tone: str = "neutral", market_tone: str = "") -> str:
    """System prompt สำหรับ Creative Brief Generator"""
    base = (
        "คุณเป็นผู้เชี่ยวชาญด้าน Creative Advertising สำหรับ Meta Ads (Facebook/Instagram Reels)\n"
        "ตามหลัก \"Creative is Targeting\" — AI ของ Meta จะเรียนรู้จากเนื้อหา รูปภาพ และวิดีโอในโฆษณา\n"
        "เพื่อนำส่งโฆษณาไปให้กลุ่มเป้าหมายที่มีแนวโน้มจะสนใจจริงๆ\n\n"
        "คุณต้องสร้างชิ้นงานโฆษณา 3 มุมมอง (perspectives) สำหรับสินค้าแต่ละตัว:\n"
        "1. แก้ปัญหา (problem_solution) — สำหรับคนที่มีพฤติกรรมชอบมองหาทางแก้ปัญหา\n"
        "2. รีวิว (review) — สำหรับคนชอบดูรีวิว\n"
        "3. ให้ความรู้ (education) — สำหรับคนที่ชอบหาข้อมูลประกอบการตัดสินใจ\n\n"
        "ข้อกำหนด:\n"
        "- ทุก field เป็นภาษาไทย\n"
        "- Hook ต้องสั้น กระชับ หยุดคนดูใน 3 วินาทีแรก\n"
        "- Script ต้องเป็นธรรมชาติ เหมือนเพื่อนเล่าให้ฟัง ไม่ใช่โฆษณาแบรนด์อย่างเป็นทางการ\n"
        "- CTA ต้องชัดเจน กดลิงก์ Shopee ง่าย\n"
        "- ห้ามใช้คำโฆษณาเกินจริง (No clickbait)\n"
        "- hashtags จำกัด 6-8 แท็ก ที่เกี่ยวข้องกับสินค้า\n"
        "- target_behavior อธิบายพฤติกรรมกลุ่มเป้าหมายที่เหมาะกับมุมมองนี้\n"
        "- ai_confidence ให้คะแนน 0-100 ว่ามั่นใจแค่ไหนว่าชิ้นงานนี้จะได้ผลดี"
    )
    return persona_system_prompt(base=base, tone=tone, market_tone=market_tone)


def _build_user_prompt(
    name: str, category: str, price: float, rating: float,
    sales_count: int, commission: float, image_url: str = "",
) -> str:
    return (
        f"สร้าง Creative Brief 3 มุมมองสำหรับสินค้านี้:\n\n"
        f"ชื่อสินค้า: {name}\n"
        f"หมวดหมู่: {category}\n"
        f"ราคา: {price} บาท\n"
        f"คะแนนรีวิว: {rating}/5\n"
        f"ยอดขาย: {sales_count} ชิ้น\n"
        f"ค่าคอมมิชชัน: {commission} บาท\n"
        + (f"รูปสินค้า: {image_url}\n" if image_url else "")
        + "\nส่งกลับเป็น JSON object ที่มี key: problem_solution, review, education\n"
        "แต่ละ key มี fields: hook, script_body, cta, caption, hashtags (array), target_behavior, thumbnail_prompt, ai_confidence (integer 0-100)"
    )


def _parse_brief_response(raw: str) -> dict:
    """Parse LLM response เป็น dict ที่มี 3 perspectives"""
    data = parse_llm_json(raw)
    if not isinstance(data, dict):
        raise ValueError("Response ไม่ใช่ object")
    for key in ("problem_solution", "review", "education"):
        if key not in data:
            raise ValueError(f"ขาด perspective: {key}")
        p = data[key]
        if not isinstance(p, dict):
            raise ValueError(f"{key} ไม่ใช่ object")
        for field in ("hook", "script_body", "cta", "caption"):
            if field not in p:
                raise ValueError(f"{key}.{field} ขาด")
    return data


def _fallback_brief(
    name: str, category: str, price: float, rating: float,
    sales_count: int, commission: float,
) -> dict:
    """Template fallback เมื่อ LLM ไม่พร้อม — เสียงป้าเข็ม 3 มุมมอง"""
    return {
        "problem_solution": {
            "hook": f"หยุดก่อนจ๊ะ! เบื่อมั้ยที่หา {name} ดีๆ ไม่ได้สักที",
            "script_body": (
                f"หลายคนบ่นว่า {name} แบบนี้ซื้อมาแล้วผิดหวัง แพงเกินราคา หรือไม่รู้จะเชื่อใคร\n"
                f"ตัวนี้ป้าลองใช้เองแล้วจ๊ะ คุณภาพดีสมราคา ใช้ประจำได้เรื่อยๆ คุ้มมาก\n"
                f"ราคาแค่ {price} บาท ค่าคอม {commission} บาท ไม่แพงเลย"
            ),
            "cta": "ใครสนใจกดลิงก์ในตะกร้า Shopee ได้เลยจ๊ะ ป้าจัดให้ ของแท้ราคาดี",
            "caption": f"ป้าใช้เองมาสักพักแล้วจ๊ะ {name} ดีจริง คุ้มมาก ลองดูจ๊ะ ไม่ลองไม่รู้!",
            "hashtags": ["ของดีบอกต่อ", "ป้าป้ายยา", "คุ้มมาก", category or "ShopeeAffiliate"],
            "target_behavior": "กลุ่มลูกค้าที่กำลังมีปัญหา/ความต้องการและกำลังหาทางแก้ — กำลังเสิร์ชหาสินค้า 类似",
            "thumbnail_prompt": f"Warm friendly photo of {name} on a wooden counter with soft daylight, problem-solution style",
            "ai_confidence": 60,
        },
        "review": {
            "hook": f"รีวิวจริงจากป้า! {name} ตัวนี้ดียังไง ไปดู",
            "script_body": (
                f"ป้าซื้อ {name} มาใช้สักพักแล้วจ๊ะ ต้องมาบอกต่อ\n"
                f"ข้อดี: คุณภาพดีสมราคา ใช้งานง่าย ไม่ยุ่งยาก\n"
                f"คะแนนรีวิว {rating}/5 ยอดขาย {sales_count} ชิ้น ไม่ธรรมดาเลยนะ\n"
                f"ใครลังเลอยู่ ป้ารับประกันว่าคุ้มค่าแน่นอน"
            ),
            "cta": "ดูรีวิวเพิ่มเติมแล้วกดสั่งได้เลยจ๊ะ ลิงก์ในตะกร้า Shopee",
            "caption": f"รีวิวจริงไม่จกตา! {name} ใช้ดีจริงจนต้องบอกต่อ ใครยังไม่ลองต้องลอง!",
            "hashtags": ["รีวิวจริง", "ของดีบอกต่อ", "ShopeeAffiliate", category or "รีวิวสินค้า"],
            "target_behavior": "กลุ่มลูกค้าที่ชอบอ่าน/ดูรีวิวก่อนตัดสินใจ — กำลังเปรียบเทียบสินค้า 类似",
            "thumbnail_prompt": f"UGC-style photo of {name} being held in hand, natural lighting, review style",
            "ai_confidence": 65,
        },
        "education": {
            "hook": f"รู้มั้ยว่า? เทคนิคเลือก {category or 'สินค้า'} ให้ถูกมีแค่ 3 ข้อ",
            "script_body": (
                f"วันนี้ป้ามาแชร์เกร็ดความรู้จ๊ะ ว่าเลือก {name} ยังไงให้คุ้ม\n"
                f"ข้อ 1: ดูคะแนนรีวิว (ตอนนี้ {rating}/5 ดีมาก)\n"
                f"ข้อ 2: ดูยอดขาย ({sales_count} ชิ้น แสดงว่าคนเชื่อมั่น)\n"
                f"ข้อ 3: เทียบราคาค่าคอม ({commission} บาท คุ้มค่า)\n"
                f"ถ้าผ่านทั้ง 3 ข้อ รับรองไม่ผิดหวัง"
            ),
            "cta": "รู้เทคนิคแล้ว กดสั่งได้เลยจ๊ะ ลิงก์ในตะกร้า Shopee",
            "caption": f"3 เทคนิคเลือก {category or 'สินค้า'} ให้คุ้ม! {name} ผ่านทุกเกณฑ์ แนะนำเลย",
            "hashtags": ["เทคนิคเลือกสินค้า", "เกร็ดความรู้", "ShopeeAffiliate", category or "รีวิว"],
            "target_behavior": "กลุ่มลูกค้าที่ชอบหาข้อมูล/เปรียบเทียบก่อนซื้อ — กำลัง research หาข้อมูล",
            "thumbnail_prompt": f"Educational infographic style photo of {name} with tips overlay, clean background",
            "ai_confidence": 55,
        },
    }


def generate_creative_brief(
    name: str,
    category: str = "",
    price: float = 0.0,
    rating: float = 0.0,
    sales_count: int = 0,
    commission: float = 0.0,
    image_url: str = "",
    tone: str = "neutral",
    market_tone: str = "",
) -> dict:
    """
    สร้าง Creative Brief 3 มุมมองสำหรับสินค้า

    Returns: dict ที่มี problem_solution, review, education
    """
    provider = settings.LLM_PROVIDER
    system_prompt = _build_system_prompt(tone=tone, market_tone=market_tone)
    user_prompt = _build_user_prompt(name, category, price, rating, sales_count, commission, image_url)

    # --- Try LLM providers ---
    if provider == "gemini" and settings.GEMINI_API_KEY and "mock" not in settings.GEMINI_API_KEY.lower():
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=system_prompt)
            response = call_with_backoff(
                lambda: model.generate_content(
                    user_prompt,
                    generation_config={"response_mime_type": "application/json"},
                )
            )
            return _parse_brief_response(response.text)
        except Exception as e:
            logger.error(f"Gemini creative brief failed: {e}")

    elif provider == "openai" and settings.OPENAI_API_KEY and "mock" not in settings.OPENAI_API_KEY.lower():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = call_with_backoff(
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
            )
            return _parse_brief_response(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"OpenAI creative brief failed: {e}")

    elif provider == "groq" and settings.GROQ_API_KEY and "mock" not in settings.GROQ_API_KEY.lower():
        from app.services.llm_clients import groq_clients
        clients = groq_clients()
        last_err = None
        for client in clients:
            try:
                response = call_with_backoff(
                    lambda: client.chat.completions.create(
                        model=settings.GROQ_MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format=groq_json_schema_format(BRIEF_JSON_SCHEMA, settings.GROQ_MODEL),
                    ),
                    circuit_key=client.api_key,
                )
                return _parse_brief_response(response.choices[0].message.content)
            except Exception as e:
                last_err = e
                logger.warning(f"Groq key {client.api_key[:8]}... failed: {e}")
        logger.error(f"Groq creative brief failed with all keys: {last_err}")

    elif provider == "anthropic" and settings.ANTHROPIC_API_KEY and "mock" not in settings.ANTHROPIC_API_KEY.lower():
        from app.services.llm_clients import anthropic_clients
        clients = anthropic_clients()
        last_err = None
        for client in clients:
            try:
                response = call_with_backoff(
                    lambda: client.chat.completions.create(
                        model=settings.ANTHROPIC_MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    ),
                    circuit_key=client.api_key,
                )
                return _parse_brief_response(response.choices[0].message.content)
            except Exception as e:
                last_err = e
                logger.warning(f"Anthropic key {client.api_key[:8]}... failed: {e}")
        logger.error(f"Anthropic creative brief failed with all keys: {last_err}")

    # Fallback to template
    logger.info("Using template fallback for creative brief")
    return _fallback_brief(name, category, price, rating, sales_count, commission)
