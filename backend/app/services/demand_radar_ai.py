# -*- coding: utf-8 -*-
"""AI Intent & Demand Analysis Service (Social Demand Radar V1 - บอทป้าเข็ม)

หน้าที่หลัก:
1. วิเคราะห์โพสต์จากกลุ่ม Facebook ด้วย AI (Groq / Anthropic / Gemini / OpenAI)
   - สกัด Intent, Demand Score (0-100), Urgency, Budget, Product Keyword, Pain Points, Sentiment
   - มี Multi-provider failover และ Heuristic Fallback สำหรับกรณี Offline / API Error
2. ตรวจสอบเงื่อนไข Demand Score >= 70 (is_high_demand) เพื่อตัดสินใจสร้าง Demand Event
3. ร่างข้อความแนะนำสินค้าและป้ายยาสไตล์ "ป้าเข็ม" (Auntie Khem Deal Copy) พร้อมแนบลิงก์ Affiliate
"""
from decimal import Decimal
import json
import logging
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple, Union

from app.config import settings
from app.services.category import CATEGORY_KEYWORDS, guess_category, normalize_query
from app.services.llm_clients import call_with_backoff
from app.services.persona import persona_system_prompt

logger = logging.getLogger(__name__)

# --- Thai Text Normalization & Helpers ---

def _nfc(s: str) -> str:
    """รวมอักขระภาษาไทยเป็นรูปแบบเดียว NFC และแปลงสระอำรูปผสมให้เป็นสระอำเดี่ยว"""
    if not s:
        return ""
    try:
        s = unicodedata.normalize("NFC", s)
    except Exception:
        pass
    return (s.replace("\u0e4d\u0e32", "\u0e33")   # นิคหิต + สระอา -> สระอำ
             .replace("\u0e4d\u0e33", "\u0e33"))  # กันรูปแบบซ้ำ


_THAI_DIGIT_WORDS = {
    "หนึ่ง": 1, "ยี่": 2, "สอง": 2, "สาม": 3, "สี่": 4,
    "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9,
}
_THAI_UNIT_WORDS = {
    "สิบ": 10, "ร้อย": 100, "พัน": 1000, "หมื่น": 10000,
    "แสน": 100000, "ล้าน": 1000000,
}


def _parse_thai_word_number(text: str) -> Optional[float]:
    """แปลงคำบอกเลขไทย ('ร้อย' -> 100, 'สองพัน' -> 2000, 'ห้าร้อย' -> 500)"""
    t = (text or "").strip()
    m = re.fullmatch(r"(หนึ่ง|ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(สิบ|ร้อย|พัน|หมื่น|แสน|ล้าน)", t)
    if not m:
        return None
    digit = _THAI_DIGIT_WORDS.get(m.group(1) or "", 1)
    unit = _THAI_UNIT_WORDS.get(m.group(2), 1)
    return float(digit * unit)


def parse_post_budget(text: str) -> Tuple[Optional[float], Optional[str]]:
    """สกัดงบประมาณจากข้อความโพสต์ คืนค่า (budget_float, budget_text)
    รองรับ: 'งบไม่เกิน 500', 'งบ 500 บาท', 'ราคาไม่เกิน 1,000', '300-500', 'งบสองพัน'
    """
    if not text:
        return None, None
    raw_cleaned = text.replace(",", "")
    t = raw_cleaned.replace(" ", "").lower()

    # 1. ช่วงราคา เช่น 300-500 / 300 ถึง 500 -> นำขอบบนมาเป็นงบสูงสุด
    m_range = re.search(r"(\d{2,})\s*(?:-|–|ถึง)\s*(\d{2,})", t)
    if m_range:
        max_val = float(m_range.group(2))
        return max_val, f"{m_range.group(1)}-{m_range.group(2)} บาท"

    # 2. งบระบุชัดเจนด้วยตัวเลข: "งบไม่เกิน 500", "ไม่เกิน 500", "งบ 500", "ราคา 300"
    m_budget = re.search(
        r"(?:ไม่เกิน|ไม่แพงกว่า|ไม่เกินงบ|ต่ำกว่า|ถูกกว่า|งบประมาณ|งบ|ในงบ|ราคา|ประมาณ|ภายใน|ซื้อได้ใน)\s*(\d+(?:\.\d+)?)",
        t,
    )
    if m_budget:
        val = float(m_budget.group(1))
        return val, f"ไม่เกิน {val:g} บาท"

    # 3. ตัวเลขคำไทย: "ไม่เกินร้อย", "งบสองพัน", "งบห้าร้อย"
    m_word = re.search(
        r"(?:ไม่เกิน|ไม่แพงกว่า|ต่ำกว่า|ถูกกว่า|งบประมาณ|งบ|ในงบ|ราคา|ประมาณ)\s*((?:หนึ่ง|ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(?:สิบ|ร้อย|พัน|หมื่น|แสน|ล้าน))",
        t,
    )
    if m_word:
        val = _parse_thai_word_number(m_word.group(1))
        if val is not None:
            return val, f"ไม่เกิน {val:g} บาท"

    # 4. "<ตัวเลข> บาท"
    m_baht = re.search(r"(\d+(?:\.\d+)?)\s*บาท", t)
    if m_baht:
        val = float(m_baht.group(1))
        return val, f"{val:g} บาท"

    # 5. "<เลขไทยคำ> บาท" เช่น "สองร้อยบาท", "ห้าร้อยบาท"
    m_word_baht = re.search(
        r"((?:หนึ่ง|ยี่|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(?:สิบ|ร้อย|พัน|หมื่น|แสน|ล้าน))\s*บาท",
        t,
    )
    if m_word_baht:
        val = _parse_thai_word_number(m_word_baht.group(1))
        if val is not None:
            return val, f"{val:g} บาท"

    return None, None


# --- Keyword Banks for Demand & Intent Classification ---

SCAM_WARNING_PATTERNS = (
    "เตือนภัย", "โกง", "แบล็คลิสต์", "blacklist", "มิจฉาชีพ", "ระวังโดนหลอก",
    "อย่าโอน", "บัญชีคนโกง", "โดนโกง", "ระวังคนนี้", "ส่งต่อ", "ปล่อยต่อ",
    "ขายต่อ", "ขายเอง", "ขออนุญาตแอดมินปล่อย", "ขออนุญาตปล่อย", "ปล่อยเสื้อผ้า",
    "มือสอง", "ส่งต่องานป้าย", "รับหิ้ว", "ฝากขาย", "ปล่อยของ", "ส่งต่อสภาพดี",
)

BUYING_INTENT_STRONG_PATTERNS = (
    "มีใครแนะนำ", "ช่วยแนะนำ", "อยากได้", "ตามหา", "หาซื้อ", "ขอพิกัด", "ชี้เป้า",
    "ป้ายยาหน่อย", "ตัวไหนดี", "อันไหนดี", "รุ่นไหนดี", "ยี่ห้อไหนดี", "ซื้อที่ไหน",
    "มีแนะนำไหม", "แนะนำหน่อย", "อยากได้พิกัด", "ต้องการซื้อ", "กำลังหา", "มองหา",
    "สนใจซื้อ", "อยากลองใช้", "ใครเคยใช้", "สั่งจากไหน", "ร้านไหนดี", "แบบไหนดี",
)

URGENCY_PATTERNS = (
    "ด่วน", "ด่วนมาก", "ด่วนๆ", "วันนี้", "เสาร์นี้", "อาทิตย์นี้", "ทันที",
    "รีบใช้", "พัง", "เสีย", "จะคลอด", "ต้องใช้", "หมดแล้ว", "ขาดไม่ได้",
)

FILLER_QUERY_PREFIXES = (
    "มีใครแนะนำ", "ช่วยแนะนำหน่อยค่ะ", "ช่วยแนะนำหน่อยครับ", "ช่วยแนะนำ",
    "แนะนำหน่อยค่ะ", "แนะนำหน่อยครับ", "แนะนำหน่อย", "อยากได้", "ตามหา",
    "ขอพิกัด", "ใครมี", "รบกวนแนะนำ", "สอบถามค่ะ", "สอบถามครับ", "สอบถามหน่อยค่ะ",
    "สอบถามหน่อยครับ", "ตามหาร้าน", "ขอคำแนะนำ", "ช่วยชี้เป้า", "ชี้เป้าหน่อย",
    "อยากสอบถาม", "มีใครใช้", "กำลังตามหา", "มองหา", "ต้องการ", "รบกวนเพื่อนๆ",
    "รบกวนแม่ๆ", "แม่ๆ คนไหน", "เพื่อนๆ มี",
)

POLITE_ENDINGS = (
    "ครับผม", "ครับ", "ค่ะ", "คะ", "จ้า", "จ๊ะ", "นะคะ", "นะค่ะ", "นะ",
    "หน่อย", "หน่อยค่ะ", "หน่อยครับ", "ด้วยค่ะ", "ด้วยครับ", "ทีค่ะ", "ทีครับ",
)


def _extract_heuristic_keyword(text: str) -> str:
    """สกัดคีย์เวิร์ดสินค้าจากข้อความโพสต์อย่างแม่นยำ"""
    t = _nfc(text)
    t = normalize_query(t)
    
    # 1. ตัดประโยคคำถาม/คำนำหน้า
    clean = t
    for prefix in FILLER_QUERY_PREFIXES:
        if prefix in clean:
            clean = clean.replace(prefix, " ")
    
    # 2. ตัดคำบอกงบและราคา
    clean = re.sub(r"(?:งบ|ราคา|ไม่เกิน|ประมาณ|บาท|\d+|[0-9]|-|–)+", " ", clean)
    
    # 3. ตัดคำบอกความเร่งด่วนและคำลงท้าย
    for u in URGENCY_PATTERNS:
        clean = clean.replace(u, " ")
    for p in POLITE_ENDINGS:
        clean = clean.replace(p, " ")

    # 4. ทำความสะอาดช่องว่างและสัญลักษณ์
    clean = re.sub(r"[!?,.:;\"'()/\\]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    # 5. เทียบกับ CATEGORY_KEYWORDS เพื่อหาคำหลักที่ตรงที่สุด
    words = clean.split()
    for w in words:
        if len(w) >= 3:
            for kw, _cat in sorted(CATEGORY_KEYWORDS, key=lambda x: -len(x[0])):
                if kw in w or w in kw:
                    return kw

    if words:
        # เลือกคำที่มีความยาวเหมาะสม (ไม่ใช่คำสั้น 1-2 ตัว)
        valid_words = [w for w in words if len(w) >= 3]
        if valid_words:
            return valid_words[0]

    return clean[:30].strip() or "สินค้าแนะนำ"


def _extract_pain_points(text: str) -> List[str]:
    """สกัด Pain Points / ความต้องการเฉพาะจากโพสต์"""
    t = _nfc(text)
    pain_points = []
    
    features = [
        ("ใส่สบาย", "ต้องการความสบายในการสวมใส่ ไม่อึดอัด"),
        ("ไม่อึดอัด", "ต้องการชุด/เสื้อผ้าที่ไม่อึดอัด"),
        ("เสียงเงียบ", "ต้องการอุปกรณ์ที่ทำงานเงียบ ไม่มีเสียงรบกวน"),
        ("ลมแรง", "ต้องการแรงลมดี ระบายอากาศได้ดี"),
        ("ตัดเสียง", "ต้องการระบบตัดเสียงรบกวน"),
        ("ของแท้", "เน้นสินค้าของแท้ มีการรับประกัน"),
        ("ส่งไว", "ต้องการการจัดส่งที่รวดเร็ว"),
        ("ราคาประหยัด", "เน้นความคุ้มค่าและราคาไม่แพง"),
        ("ทานยาก", "สำหรับสัตว์เลี้ยง/เด็กที่เลือกทานหรือทานยาก"),
        ("พัง", "ของเดิมชำรุด ต้องการตัวใหม่ทดแทนทันที"),
        ("ด่วน", "ต้องการใช้งานอย่างเร่งด่วน"),
        ("ไม่แพง", "มองหาราคาที่เหมาะสมกับงบประมาณ"),
    ]
    
    for kw, desc in features:
        if kw in t and desc not in pain_points:
            pain_points.append(desc)
            
    if not pain_points:
        pain_points.append("มองหาสินค้าคุณภาพดีที่คุ้มค่ากับราคา")
        
    return pain_points


def _heuristic_demand_analysis(post_text: str, author_name: Optional[str] = None) -> Dict[str, Any]:
    """การวิเคราะห์ความต้องการแบบ Rule-based Heuristic เมื่อไม่มีการเชื่อมต่อ LLM"""
    text_norm = _nfc(post_text or "")
    
    # 1. ตรวจสอบโพสต์เตือนภัย / สแปม / ปล่อยของมือสอง
    for pattern in SCAM_WARNING_PATTERNS:
        if pattern in text_norm:
            return {
                "intent": "spam_or_warning",
                "demand_score": 15,
                "urgency": "low",
                "budget": None,
                "budget_text": None,
                "product_keyword": None,
                "detected_category": "ทั่วไป",
                "pain_points": ["โพสต์เตือนภัยหรือปล่อยสินค้ามือสอง"],
                "sentiment": "negative" if "โกง" in pattern or "เตือน" in pattern else "neutral",
                "reasoning": f"ตรวจพบคำว่า '{pattern}' ซึ่งเป็นโพสต์แจ้งเตือนภัยหรือขายของส่วนตัว ไม่ใช่ความต้องการซื้อสินค้าใหม่",
            }

    # 2. ตรวจจับงบประมาณ
    budget_val, budget_str = parse_post_budget(text_norm)

    # 3. ตรวจจับความเร่งด่วน
    has_urgency = any(u in text_norm for u in URGENCY_PATTERNS)
    urgency = "high" if has_urgency else ("medium" if budget_val is not None else "low")

    # 4. สกัดคีย์เวิร์ดสินค้าและหมวดหมู่
    keyword = _extract_heuristic_keyword(text_norm)
    category = guess_category(keyword or text_norm)
    pain_points = _extract_pain_points(text_norm)

    # 5. ตรวจจับสัญญาณความต้องการซื้อ (Demand Signals)
    strong_intent = any(b in text_norm for b in BUYING_INTENT_STRONG_PATTERNS)
    
    # คำนวณคะแนน Demand Score (0 - 100)
    score = 45  # base score สำหรับโพสต์ทั่วไป
    if strong_intent:
        score += 30  # มีคำถามหา/อยากได้/แนะนำ (+30) -> 75
    if budget_val is not None:
        score += 10  # มีการระบุงบชัดเจน (+10)
    if has_urgency:
        score += 10  # มีความเร่งด่วน (+10)
    if len(keyword) >= 3 and keyword != "สินค้าแนะนำ":
        score += 5   # ระบุชื่อสินค้าชัดเจน (+5)

    score = min(max(score, 0), 100)

    # กำหนด Intent
    if strong_intent or score >= 70:
        intent = "recommendation_request" if "แนะนำ" in text_norm else "buy_request"
    else:
        intent = "general_discussion"

    sentiment = "urgent" if has_urgency else ("positive" if strong_intent else "neutral")

    reasoning = (
        f"ผู้โพสต์มีความต้องการสินค้า '{keyword}' ในระดับ {urgency} "
        f"พร้อมงบประมาณ {budget_str or 'ไม่ระบุ'} มีคะแนนความต้องการ {score}/100"
    )

    return {
        "intent": intent,
        "demand_score": score,
        "urgency": urgency,
        "budget": budget_val,
        "budget_text": budget_str,
        "product_keyword": keyword,
        "detected_category": category,
        "pain_points": pain_points,
        "sentiment": sentiment,
        "reasoning": reasoning,
    }


def is_high_demand(demand_score: int, threshold: int = 70) -> bool:
    """ตรวจสอบว่า Demand Score ผ่านเกณฑ์สำหรับการสร้าง Demand Event และแจ้งเตือนหรือไม่ (Default >= 70)"""
    try:
        score = int(demand_score) if demand_score is not None else 0
        return score >= threshold
    except (ValueError, TypeError):
        return False


# --- System Prompt for LLM Demand Analysis ---

DEMAND_ANALYSIS_SYSTEM_PROMPT = """\
You are an expert Social Commerce Lead & Demand Analyst specializing in Thai social media (Facebook Groups).
Your task is to analyze raw posts from Facebook groups and extract structured purchase intent, demand signals, and product keywords.

You must respond ONLY with a valid JSON object matching the exact schema below. Do not include markdown code fences (```json), explanations, or preamble.

Response Schema:
{
    "intent": "buy_request" | "recommendation_request" | "product_inquiry" | "general_discussion" | "spam_or_warning",
    "demand_score": <integer from 0 to 100>,
    "urgency": "high" | "medium" | "low",
    "budget": <float number or null if not specified>,
    "budget_text": <string describing budget or null>,
    "product_keyword": <concise Thai search keyword for the desired product, e.g. "ชุดคลุมท้อง", "หูฟังบลูทูธ">,
    "detected_category": <string category name, e.g. "แฟชั่น", "อุปกรณ์เสริม", "เครื่องใช้ไฟฟ้า", "ความงาม", "ทั่วไป">,
    "pain_points": [<list of Thai strings identifying specific needs or problems>],
    "sentiment": "urgent" | "positive" | "neutral" | "negative",
    "reasoning": <short explanation in Thai for the assigned score>
}

Scoring Rubric:
- 85-100: Explicit High Demand - Direct request to buy, asking for store links, recommendations with explicit buying intent, budget, or urgency.
- 70-84: Clear problem/need seeking product solutions, asking for best brands or comparisons.
- 40-69: General knowledge question or casual discussion without immediate intent to purchase.
- 0-39: Scam warnings, seller promotion/selling goods, second-hand dumps, off-topic memes, or news.
"""


def analyze_lead_intent_and_demand(post_text: str, author_name: Optional[str] = None) -> Dict[str, Any]:
    """วิเคราะห์เจตนาและความต้องการซื้อจากข้อความโพสต์ดิบ
    ใช้ Multi-provider LLM (Groq / Anthropic / Gemini / OpenAI) พร้อม Fallback อัตโนมัติ
    """
    if not post_text or not post_text.strip():
        return {
            "intent": "general_discussion",
            "demand_score": 0,
            "urgency": "low",
            "budget": None,
            "budget_text": None,
            "product_keyword": None,
            "detected_category": "ทั่วไป",
            "pain_points": [],
            "sentiment": "neutral",
            "reasoning": "ข้อความว่างเปล่า ไม่พบข้อมูลที่วิเคราะห์ได้",
        }

    provider = (settings.LLM_PROVIDER or "groq").lower()
    prompt = f"""
    Analyze this Facebook group post:
    Author: {author_name or "ไม่ระบุ"}
    Post Text: "{post_text}"
    """

    # 1. Try Groq
    if provider == "groq" or (settings.GROQ_API_KEY and "mock" not in settings.GROQ_API_KEY.lower()):
        try:
            from app.services.llm_clients import groq_clients
            clients = groq_clients()
            for client in clients:
                try:
                    response = call_with_backoff(
                        lambda: client.chat.completions.create(
                            model=settings.GROQ_MODEL,
                            messages=[
                                {"role": "system", "content": DEMAND_ANALYSIS_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            response_format={"type": "json_object"},
                            temperature=0.2,
                        )
                    )
                    content = response.choices[0].message.content
                    data = json.loads(content)
                    if isinstance(data, dict) and "demand_score" in data:
                        data["demand_score"] = int(data.get("demand_score", 0))
                        return data
                except Exception as ex:
                    logger.warning(f"Groq demand analysis key failed: {ex}")
        except Exception as e:
            logger.warning(f"Groq provider failed: {e}")

    # 2. Try Anthropic
    if provider == "anthropic" or (settings.ANTHROPIC_API_KEY and "mock" not in settings.ANTHROPIC_API_KEY.lower()):
        try:
            from app.services.llm_clients import anthropic_clients
            clients = anthropic_clients()
            for client in clients:
                try:
                    response = call_with_backoff(
                        lambda: client.chat.completions.create(
                            model=settings.ANTHROPIC_MODEL,
                            messages=[
                                {"role": "system", "content": DEMAND_ANALYSIS_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.2,
                        )
                    )
                    content = response.choices[0].message.content.strip()
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.endswith("```"):
                        content = content[:-3]
                    data = json.loads(content.strip())
                    if isinstance(data, dict) and "demand_score" in data:
                        data["demand_score"] = int(data.get("demand_score", 0))
                        return data
                except Exception as ex:
                    logger.warning(f"Anthropic demand analysis key failed: {ex}")
        except Exception as e:
            logger.warning(f"Anthropic provider failed: {e}")

    # 3. Try Gemini
    if settings.GEMINI_API_KEY and "mock" not in settings.GEMINI_API_KEY.lower():
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                system_instruction=DEMAND_ANALYSIS_SYSTEM_PROMPT,
            )
            response = call_with_backoff(
                lambda: model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"},
                )
            )
            data = json.loads(response.text)
            if isinstance(data, dict) and "demand_score" in data:
                data["demand_score"] = int(data.get("demand_score", 0))
                return data
        except Exception as e:
            logger.warning(f"Gemini demand analysis failed: {e}")

    # 4. Try OpenAI
    if settings.OPENAI_API_KEY and "mock" not in settings.OPENAI_API_KEY.lower():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = call_with_backoff(
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": DEMAND_ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
            )
            data = json.loads(response.choices[0].message.content)
            if isinstance(data, dict) and "demand_score" in data:
                data["demand_score"] = int(data.get("demand_score", 0))
                return data
        except Exception as e:
            logger.warning(f"OpenAI demand analysis failed: {e}")

    # Fallback to robust heuristic analyzer
    logger.info("Using heuristic demand analyzer fallback for post.")
    return _heuristic_demand_analysis(post_text, author_name)


# --- Auntie Khem Deal Copy Generator ---

AUNTIE_KHEM_COPY_SYSTEM_PROMPT = """\
คุณคือ "ป้าเข็ม" แม่ค้าออนไลน์วัย 50+ ปี เจ้าของร้าน "ป้าเข็ม ขายของ"
บุคลิก: อบอุ่น เป็นกันเอง จริงใจ เหมือนป้าข้างบ้านที่หวังดี ไม่ยัดเยียดขายของ ไม่โฆษณาเกินจริง

ภารกิจ:
เขียนข้อความสั้น (Comment Copy) ความยาวประมาณ 2-4 ประโยค เพื่อให้แอดมินนำไปคอมเมนต์แนะนำสินค้าในกลุ่ม Facebook ตอบผู้โพสต์ที่กำลังต้องการสินค้า

ข้อกำหนดการเขียน:
1. เปิดด้วยความเป็นกันเองและเห็นอกเห็นใจในปัญหาของผู้โพสต์ (ใช้คำเรียก เช่น "หนู", "น้อง", "คุณแม่", "ตัวเอง" ตามความเหมาะสม)
2. แนะนำสินค้าที่เลือกให้ พร้อมบอกจุดเด่นสั้นๆ ว่าทำไมถึงตอบโจทย์
3. ปิดท้ายด้วยการบอกพิกัดลิงก์ Affiliate ที่ระบุอย่างสุภาพและเป็นธรรมชาติ
4. ลงท้ายด้วยคำอบอุ่น เช่น "จ้ะ", "จ้า", "นะจ๊ะ", "ลองดูนะลูก"
"""


def _generate_heuristic_deal_comment(
    post_text: str,
    product_name: str,
    price: float,
    rating: float,
    sales_count: int,
    affiliate_url: str,
    suggested_reasons: Optional[List[str]] = None,
) -> str:
    """สร้างข้อความคอมเมนต์สไตล์ป้าเข็มแบบ Template Heuristic เมื่อไม่มี LLM"""
    p_text = _nfc(post_text or "")
    
    # 1. เลือกคำทักทายและ Empathy เปิดหัว
    if any(k in p_text for k in ("ชุดคลุมท้อง", "คนท้อง", "คุณแม่", "คลอด", "ตั้งครรภ์")):
        opener = "ยินดีด้วยนะจ๊ะคุณแม่! "
        empathy = "ถ้าหาชุดใส่สบายไม่อึดอัดสำหรับช่วงนี้ "
    elif any(k in p_text for k in ("แมว", "สุนัข", "หมา", "สัตว์เลี้ยง")):
        opener = "สวัสดีจ้าทาสแมว/คนรักสัตว์! "
        empathy = "เรื่องของลูกรักป้าเข้าใจดีเลยจ้ะ "
    elif any(k in p_text for k in ("พัง", "เสีย", "ด่วน", "รีบใช้")):
        opener = "ใจเย็นๆ นะลูก! "
        empathy = "ป้าเข้าใจเลยเวลาของจำเป็นพังต้องรีบใช้ด่วน "
    else:
        opener = "สวัสดีจ้ะลูกหลาน! "
        empathy = "ถ้ากำลังมองหาตัวช่วยดีๆ ที่คุ้มค่า "

    # 2. จุดเด่นสินค้า
    highlights = []
    if rating and rating >= 4.5:
        highlights.append(f"รีวิวดีมากได้ {rating:.1f}/5 ดาว")
    if sales_count and sales_count >= 1000:
        highlights.append(f"ยอดขายสะสมกว่า {sales_count:,} ชิ้น")

    highlight_str = f" ({', '.join(highlights)})" if highlights else ""
    price_str = f" ในราคาคุ้มๆ แค่ {price:,.2f} บาทเองจ้า" if price > 0 else " ราคาจับต้องได้สบายกระเป๋าจ้ะ"

    # 3. ประกอบข้อความร่าง
    body = f"ป้าแนะนำตัวนี้เลยจ้ะ '{product_name}'{highlight_str}{price_str} ของดีตรงปกแน่นอนลูก"
    cta = f"\n\n👉 ป้าปักพิกัดร้านแท้ราคาดีไว้ให้นะจ๊ะ: {affiliate_url}"
    closing = "\nลองดูนะลูก ป้าคัดมาให้แล้วจ้า 💕"

    return f"{opener}{empathy}{body}{cta}{closing}"


def generate_auntie_khem_deal_comment(
    post_text: str,
    product_name: str,
    price: float,
    rating: float,
    sales_count: int,
    affiliate_url: str,
    suggested_reasons: Optional[List[str]] = None,
    lead_intent_data: Optional[Dict[str, Any]] = None,
) -> str:
    """ร่างข้อความคอมเมนต์สไตล์ป้าเข็มสำหรับตอบผู้โพสต์ใน Facebook Group
    พร้อมสอดแทรก affiliate_url อย่างเป็นธรรมชาติ
    """
    reasons_text = "\n- ".join(suggested_reasons or ["สินค้าคุณภาพดี รีวิวสูง ยอดขายดี"])
    prompt = f"""
    ช่วยเขียนข้อความคอมเมนต์ตอบโพสต์นี้ให้หน่อยจ้ะ:
    ข้อความโพสต์ของผู้ใช้: "{post_text}"
    สินค้าที่ป้าคัดมาให้: "{product_name}"
    ราคา: {price:,.2f} บาท
    คะแนนรีวิว: {rating:.1f}/5 ดาว
    ยอดขาย: {sales_count:,} ชิ้น
    เหตุผลที่คัดเลือก:
    - {reasons_text}
    ลิงก์สินค้าที่จะให้ผู้ใช้คลิก: {affiliate_url}

    เขียนเป็นข้อความสั้น 2-4 ประโยค พร้อมแนบลิงก์ {affiliate_url} ท้ายข้อความ
    """

    provider = (settings.LLM_PROVIDER or "groq").lower()

    # 1. Try Groq
    if provider == "groq" or (settings.GROQ_API_KEY and "mock" not in settings.GROQ_API_KEY.lower()):
        try:
            from app.services.llm_clients import groq_clients
            clients = groq_clients()
            for client in clients:
                try:
                    response = call_with_backoff(
                        lambda: client.chat.completions.create(
                            model=settings.GROQ_MODEL,
                            messages=[
                                {"role": "system", "content": AUNTIE_KHEM_COPY_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.7,
                        )
                    )
                    comment = response.choices[0].message.content.strip()
                    if affiliate_url not in comment:
                        comment += f"\n\n👉 พิกัดสินค้าจ้ะ: {affiliate_url}"
                    return comment
                except Exception as ex:
                    logger.warning(f"Groq deal copy generation failed: {ex}")
        except Exception as e:
            logger.warning(f"Groq provider error: {e}")

    # 2. Try Anthropic
    if provider == "anthropic" or (settings.ANTHROPIC_API_KEY and "mock" not in settings.ANTHROPIC_API_KEY.lower()):
        try:
            from app.services.llm_clients import anthropic_clients
            clients = anthropic_clients()
            for client in clients:
                try:
                    response = call_with_backoff(
                        lambda: client.chat.completions.create(
                            model=settings.ANTHROPIC_MODEL,
                            messages=[
                                {"role": "system", "content": AUNTIE_KHEM_COPY_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.7,
                        )
                    )
                    comment = response.choices[0].message.content.strip()
                    if affiliate_url not in comment:
                        comment += f"\n\n👉 พิกัดสินค้าจ้ะ: {affiliate_url}"
                    return comment
                except Exception as ex:
                    logger.warning(f"Anthropic deal copy generation failed: {ex}")
        except Exception as e:
            logger.warning(f"Anthropic provider error: {e}")

    # 3. Fallback to Heuristic generator
    return _generate_heuristic_deal_comment(
        post_text=post_text,
        product_name=product_name,
        price=price,
        rating=rating,
        sales_count=sales_count,
        affiliate_url=affiliate_url,
        suggested_reasons=suggested_reasons,
    )


INSIGHTS_ANALYSIS_SYSTEM_PROMPT = """
You are an expert social media analyst. Your task is to analyze Facebook Reels/Post Insights text block copied by the user and extract key metrics into a structured JSON object.

Extract these keys:
- "views": integer (number of views/reach)
- "watch_time_sec": integer or null (total watch time in seconds)
- "avg_watch_time_sec": float or null (average watch time in seconds)
- "watch_percentage": float or null (average watch percentage, e.g. 37.0)
- "drop_off_seconds": float or null (the timestamp where most viewers drop off, e.g. 3.0)
- "main_age_group": string or null (e.g. "45-54" or "35-44")
- "main_gender": string or null (e.g. "female" or "male" or "unknown")
- "traffic_sources": list of dicts with {"source": string, "pct": float}
- "recommendations": list of strings (actionable suggestions for the creator to optimize next videos/posts based on dropoff and demographics in Thai language)

Return ONLY a valid JSON object.
"""

def analyze_facebook_insights(insights_text: str) -> Dict[str, Any]:
    """วิเคราะห์ข้อความรายงานสถิติ Reels/Post Insights ของ Facebook ด้วย AI"""
    if not insights_text or not insights_text.strip():
        return {
            "views": 0,
            "watch_time_sec": None,
            "avg_watch_time_sec": None,
            "watch_percentage": None,
            "drop_off_seconds": None,
            "main_age_group": None,
            "main_gender": None,
            "traffic_sources": [],
            "recommendations": ["ไม่พบข้อความวิเคราะห์"]
        }

    provider = (settings.LLM_PROVIDER or "groq").lower()
    prompt = f"Analyze these Facebook Insights metrics:\n\n{insights_text}"

    # 1. Try Groq
    if provider == "groq" or (settings.GROQ_API_KEY and "mock" not in settings.GROQ_API_KEY.lower()):
        try:
            from app.services.llm_clients import groq_clients
            clients = groq_clients()
            for client in clients:
                try:
                    response = call_with_backoff(
                        lambda: client.chat.completions.create(
                            model=settings.GROQ_MODEL,
                            messages=[
                                {"role": "system", "content": INSIGHTS_ANALYSIS_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            response_format={"type": "json_object"},
                            temperature=0.2,
                        )
                    )
                    return json.loads(response.choices[0].message.content)
                except Exception as ex:
                    logger.warning(f"Groq insights analysis failed for one key: {ex}")
        except Exception as e:
            logger.warning(f"Groq provider error in insights: {e}")

    # 2. Try Gemini
    if settings.GEMINI_API_KEY and "mock" not in settings.GEMINI_API_KEY.lower():
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                system_instruction=INSIGHTS_ANALYSIS_SYSTEM_PROMPT,
            )
            response = call_with_backoff(
                lambda: model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"},
                )
            )
            return json.loads(response.text)
        except Exception as e:
            logger.warning(f"Gemini insights analysis failed: {e}")

    # Heuristic fallback (basic dictionary)
    return {
        "views": 0,
        "watch_time_sec": None,
        "avg_watch_time_sec": None,
        "watch_percentage": None,
        "drop_off_seconds": None,
        "main_age_group": None,
        "main_gender": None,
        "traffic_sources": [],
        "recommendations": ["กรุณาตั้งค่า API Key เพื่อใช้การวิเคราะห์ขั้นสูง"]
    }

