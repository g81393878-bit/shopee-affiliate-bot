import json
import logging
import math
from app.config import settings
from app.schemas import AIAnalysisResult, ScriptGeneratorResponse
from app.services.persona import persona_system_prompt

logger = logging.getLogger(__name__)

# Heuristic calculation for Product Score
def calculate_heuristic_score(sales_count: int, rating: float, commission: float, price: float) -> int:
    """
    Calculate a heuristic score from 0 to 100 based on the BRD:
    - ยอดขาย 30%
    - รีวิว 20%
    - ค่าคอม 20%
    - เทรนด์ 20% (สมมติความนิยมเป็นฟังก์ชันของยอดขายและคะแนนรีวิว)
    - ราคา 10%
    """
    # 1. ยอดขาย (30%) - ใช้ log scale รองรับหลักสิบถึงหลักหมื่น
    # ยอดขาย 0 -> 0, 10 -> 10, 100 -> 20, 1000+ -> 30
    if sales_count <= 0:
        sales_score = 0
    else:
        sales_score = min(math.log10(sales_count) / 3.0, 1.0) * 30
        
    # 2. รีวิว (20%) - เทียบอัตราส่วนจาก 5.0
    rating_val = float(rating or 0.0)
    rating_score = (rating_val / 5.0) * 20
    
    # 3. ค่าคอมมิชชัน (20%) - เทียบตามมูลค่าค่าคอม (สมมติค่าคอม 50 บาทขึ้นไปได้คะแนนเต็ม)
    comm_val = float(commission or 0.0)
    if comm_val <= 0:
        comm_score = 0
    else:
        comm_score = min(comm_val / 50.0, 1.0) * 20
        
    # 4. เทรนด์ความนิยม (20%) - คำนวณจากยอดขายร่วมกับรีวิวเพื่อคาดคะเนความนิยม
    # ถ้าของขายได้เยอะและรีวิวดี แสดงว่าเทรนด์น่าจะกำลังดี
    trend_score = min((sales_score / 30.0 + rating_score / 20.0) / 2.0, 1.0) * 20
    
    # 5. ช่วงราคา (10%) - สินค้าราคา 100 - 1500 บาท มีโอกาสตัดสินใจซื้อง่ายสุดทางออนไลน์
    price_val = float(price or 0.0)
    if 100 <= price_val <= 1500:
        price_score = 10
    elif 0 < price_val < 100:
        price_score = 7
    elif 1500 < price_val <= 5000:
        price_score = 5
    else:
        price_score = 2
        
    total_score = round(sales_score + rating_score + comm_score + trend_score + price_score)
    return max(0, min(100, total_score))


def get_mock_analysis(name: str, price: float, rating: float, sales_count: int, commission: float, score: int) -> dict:
    """Fallback mock analysis if API call fails or key is mock"""
    recommendation = "ควรทำ Content" if score >= 75 else "รอดูสถานการณ์ / ปรับปรุงกลยุทธ์"
    
    reasons = [
        f"สินค้ามียอดขายดีต่อเนื่อง ({sales_count} ชิ้น)" if sales_count > 100 else "สินค้ากลุ่มนี้มีความต้องการเฉพาะตัวสูง",
        f"คะแนนรีวิวสูงถึง {rating}/5 บ่งบอกถึงความพึงพอใจของลูกค้าและลดอัตราการคืนสินค้า",
        f"ค่าคอมมิชชัน {commission} บาท เหมาะสมกับการทำเนื้อหาแบบสั้นเพื่อกระตุ้นยอดขาย" if commission > 10 else "แม้ค่าคอมไม่สูงมากแต่เป็นสินค้าขายดีและมีอัตราการเข้าถึงง่าย",
    ]
    
    content_ideas = [
        f"คลิปสั้นรีวิวเปรียบเทียบ {name} กับรุ่นปกติ",
        f"ทำคอนเทนต์ป้ายยา บอกต่อไอเทมลับแก้ปัญหาในชีวิตประจำวัน",
        f"คลิปสั้นโชว์วิธีการใช้งานด่วน ๆ ใน 15 วินาที"
    ]
    
    script = {
        "hook": f"หยุดก่อนจ๊ะ! ป้าเพิ่งเจอ {name} ของดี ราคาไม่แพงแต่ใช้ดีจริง ต้องมาบอกต่อ",
        "problem": f"หลายคนบ่นว่าของแบบนี้ซื้อมาแล้วพังง่าย หรือแพงเกินราคา จนบางทีก็ไม่รู้จะเชื่อใคร",
        "solution": f"ตัวนี้ป้าลองใช้เองแล้วจ๊ะ ดีไซน์ตอบโจทย์ใช้จริง สะดวกขึ้นเยอะ คุ้มมาก",
        "cta": f"ใครสนใจกดลิงก์ในตะกร้า Shopee ได้เลยจ๊ะ ป้าจัดให้ ของแท้ราคาดี",
        "caption": f"ป้าใช้เองมาสักพักแล้วจ๊ะ {name} ดีจริง คุ้มมาก ลองดูจ๊ะ ไม่ลองไม่รู้! #ของดีบอกต่อ #ป้าป้ายยา #คุ้มมาก",
        "hashtags": ["ของดีบอกต่อ", "ป้าป้ายยา", "คุ้มมาก", "ShopeeAffiliate"],
        "title": f"ป้าป้ายยา {name}",
        "thumbnail_prompt": f"Warm friendly photo of {name} on a wooden shop counter with soft daylight, cozy local shop vibe"
    }
    
    return {
        "product_score": score,
        "recommendation": recommendation,
        "reasons": reasons,
        "content_ideas": content_ideas,
        "script": script
    }


def _normalize_analysis(data: dict, score: int) -> dict:
    """Map model output (snake_case or camelCase, possibly nested) to the expected schema.
    LLMs often invent key names; this makes the response tolerant of both styles."""
    rec = data.get("recommendations") if isinstance(data.get("recommendations"), dict) else {}
    reasons = data.get("reasons") or rec.get("reasons") or []
    content_ideas = data.get("content_ideas") or rec.get("contentIdeas") or data.get("contentIdeas") or []
    script = data.get("script") or data.get("tiktokScript") or {}
    if not isinstance(script, dict):
        script = {}
    return {
        "product_score": score,
        "recommendation": data.get("recommendation") or "",
        "reasons": reasons if isinstance(reasons, list) else [],
        "content_ideas": content_ideas if isinstance(content_ideas, list) else [],
        "script": script,
    }


def analyze_product_with_ai(name: str, category: str, price: float, rating: float, sales_count: int, commission: float, tone: str = "neutral") -> dict:
    score = calculate_heuristic_score(sales_count, rating, commission, price)
    provider = settings.LLM_PROVIDER
    
    # Try calling AI if API Key is not a placeholder
    if provider == "gemini" and settings.GEMINI_API_KEY and "mock" not in settings.GEMINI_API_KEY.lower():
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=persona_system_prompt(tone=tone))
            
            prompt = f"""
            Analyze this Shopee product for affiliate marketing:
            Product Name: {name}
            Category: {category}
            Price: {price} Baht
            Rating: {rating} / 5
            Sales Count: {sales_count}
            Commission: {commission} Baht
            Product Score calculated by heuristic formula: {score}/100

            Evaluate this product's potential for TikTok/Reels marketing and respond ONLY in valid JSON format.
            Return a JSON object matching this schema (write response text in Thai language):
            {{
                "product_score": {score},
                "recommendation": "string (e.g. ควรทำ Content ทันที / ควรชะลอการทำ)",
                "reasons": ["string reason 1", "string reason 2"],
                "content_ideas": ["idea 1", "idea 2"],
                "script": {{
                    "hook": "string TikTok video hook (short and punchy, in Thai)",
                    "problem": "string the user pain point (in Thai)",
                    "solution": "string how this product solves it (in Thai)",
                    "cta": "string call to action (in Thai)",
                    "caption": "string TikTok video caption with tags (in Thai)",
                    "hashtags": ["tag1", "tag2"],
                    "title": "string video title (in Thai)",
                    "thumbnail_prompt": "string prompt for generating thumbnail image"
                }}
            }}
            """
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            data = json.loads(response.text)
            return _normalize_analysis(data, score)
        except Exception as e:
            logger.error(f"Gemini API analysis failed: {e}. Falling back to mock data.")
            
    elif provider == "openai" and settings.OPENAI_API_KEY and "mock" not in settings.OPENAI_API_KEY.lower():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)

            prompt = f"""
            Analyze this Shopee product for short-video (TikTok/Reels) affiliate marketing:
            Product Name: {name}
            Category: {category}
            Price: {price} Baht
            Rating: {rating}/5
            Sales Count: {sales_count}
            Commission: {commission} Baht
            Score: {score}/100

            Respond ONLY in valid JSON exactly matching this schema (content fields in Thai):
            {{"product_score": {score}, "recommendation": "string", "reasons": ["string"], "content_ideas": ["string"], "script": {{"hook": "string", "problem": "string", "solution": "string", "cta": "string", "caption": "string", "hashtags": ["string"], "title": "string", "thumbnail_prompt": "string"}}}}
            """

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": persona_system_prompt("You are a Shopee affiliate marketing analyst. Respond only with JSON conforming to the requested schema. Use Thai language for content fields.", tone=tone)},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            return _normalize_analysis(data, score)
        except Exception as e:
            logger.error(f"OpenAI API analysis failed: {e}. Falling back to mock data.")

    elif provider == "groq" and settings.GROQ_API_KEY and "mock" not in settings.GROQ_API_KEY.lower():
        from app.services.llm_clients import groq_clients
        clients = groq_clients()
        prompt = f"""
        Analyze this Shopee product for short-video (TikTok/Reels) affiliate marketing:
        Product Name: {name}
        Category: {category}
        Price: {price} Baht
        Rating: {rating}/5
        Sales Count: {sales_count}
        Commission: {commission} Baht
        Score: {score}/100

        Respond ONLY in valid JSON exactly matching this schema (content fields in Thai):
        {{"product_score": {score}, "recommendation": "string", "reasons": ["string"], "content_ideas": ["string"], "script": {{"hook": "string", "problem": "string", "solution": "string", "cta": "string", "caption": "string", "hashtags": ["string"], "title": "string", "thumbnail_prompt": "string"}}}}
        """
        last_err = None
        for client in clients:
            try:
                response = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": persona_system_prompt("You are a Shopee affiliate marketing analyst. Respond only with JSON conforming to the requested schema. Use Thai language for content fields.", tone=tone)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                data = json.loads(response.choices[0].message.content)
                return _normalize_analysis(data, score)
            except Exception as e:
                last_err = e
                logger.warning(f"Groq key {client.api_key[:8]}... failed: {e} — ลอง key ถัดไป")
        logger.error(f"Groq API analysis failed with all keys: {last_err}. Falling back to mock data.")

    elif provider == "anthropic" and settings.ANTHROPIC_API_KEY and "mock" not in settings.ANTHROPIC_API_KEY.lower():
        from app.services.llm_clients import anthropic_clients
        clients = anthropic_clients()
        prompt = f"""
        Analyze this Shopee product for short-video (TikTok/Reels) affiliate marketing:
        Product Name: {name}
        Category: {category}
        Price: {price} Baht
        Rating: {rating}/5
        Sales Count: {sales_count}
        Commission: {commission} Baht
        Score: {score}/100

        Respond with ONLY the raw JSON object (no markdown fences, no extra text)
        exactly matching this schema (content fields in Thai):
        {{"product_score": {score}, "recommendation": "string", "reasons": ["string"], "content_ideas": ["string"], "script": {{"hook": "string", "problem": "string", "solution": "string", "cta": "string", "caption": "string", "hashtags": ["string"], "title": "string", "thumbnail_prompt": "string"}}}}
        """
        last_err = None
        for client in clients:
            try:
                # Anthropic OpenAI-compat: response_format ถูก ignore → สั่ง JSON ใน prompt เอง
                response = client.chat.completions.create(
                    model=settings.ANTHROPIC_MODEL,
                    messages=[
                        {"role": "system", "content": persona_system_prompt("You are a Shopee affiliate marketing analyst. Respond only with JSON conforming to the requested schema. Use Thai language for content fields.", tone=tone)},
                        {"role": "user", "content": prompt}
                    ]
                )
                data = json.loads(response.choices[0].message.content)
                return _normalize_analysis(data, score)
            except Exception as e:
                last_err = e
                logger.warning(f"Anthropic key {client.api_key[:8]}... failed: {e} — ลอง key ถัดไป")
        logger.error(f"Anthropic API analysis failed with all keys: {last_err}. Falling back to mock data.")

    # Fallback to mock data if no keys configured or API calls failed
    return get_mock_analysis(name, price, rating, sales_count, commission, score)
