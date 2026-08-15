import json
import logging
from app.config import settings
from app.services.llm_clients import call_with_backoff
from app.schemas import ScriptGeneratorResponse
from app.services.persona import persona_system_prompt

logger = logging.getLogger(__name__)

SCRIPT_KEYS = {"hook", "problem", "solution", "cta", "caption", "hashtags", "title", "thumbnail_prompt"}


def format_hashtags_text(tags) -> str:
    """แปลง hashtags จาก model เป็นบรรทัด #tag1 #tag2 ... (รองรับทั้ง list และ string)
    - Model ส่ง string "#หูฟัง #ดี" หรือ list — ถ้า iter string ตรงๆ จะกลายเป็น
      "#ห #ู #ฟ" (ต่อทีละตัวอักษร) → normalize ก่อนเสมอ
    - บางที model ส่ง single-char tokens ("#ไ #ฟ #โ") — แท็กตัวเดียวไม่มีความหมาย
      (เป็นแฮชที่ model เกิดแยกตัวอักษร) → ตัดทิ้ง เหลือแต่แท็กยาว ≥2 ตัว
    - กำจัด # ซ้ำ/ตัวเปล่า, จำกัด 8 แท็ก"""
    raw = tags if isinstance(tags, list) else str(tags).replace(",", " ").split()
    seen, cleaned = set(), []
    for t in raw:
        t = str(t).strip().lstrip("#").strip()
        if len(t) >= 2 and t not in seen:  # ตัด single-char (แฮชที่เละ) + ซ้ำ
            seen.add(t)
            cleaned.append(t)
    if not cleaned:
        return ""
    return " ".join(f"#{t}" for t in cleaned[:8])


def _require_script_keys(data: dict) -> dict:
    """Validate the model returned the full script schema; raise so callers fall back."""
    if not isinstance(data, dict) or not SCRIPT_KEYS.issubset(data):
        raise ValueError(f"script JSON missing keys: {sorted(SCRIPT_KEYS - set(data)) if isinstance(data, dict) else 'not an object'}")
    return data


def build_template_script(product_name: str, category: str = "", price: float = 0.0,
                          style: str = "standard", tone: str = "neutral") -> dict:
    """สคริปต์คอนเทนต์แบบ template (ไม่เรียก LLM) — เสียงป้าเข็มสำเร็จรูป

    ใช้เป็น (1) fallback เมื่อ LLM ทุก provider พัง และ (2) backfill สินค้าที่ไม่มี
    คอนเทนต์โดยไม่ต้องเสีย Groq — field ครบ SCRIPT_KEYS เหมือนผลจาก LLM.
    """
    return {
        "hook": f"หยุดก่อนจ๊ะ! ป้าเพิ่งเจอ {product_name} ของดี ราคาไม่แพงแต่ใช้ดีจริง ต้องมาบอกต่อ",
        "problem": "หลายคนบ่นว่าของแบบนี้ซื้อมาแล้วพังง่าย หรือแพงเกินราคา จนบางทีก็ไม่รู้จะเชื่อใคร",
        "solution": f"ตัวนี้ป้าลองใช้เองแล้วจ๊ะ สไตล์ {style} คุณภาพดีสมราคา ใช้ประจำได้เรื่อย ๆ คุ้มมาก",
        "cta": "ใครสนใจกดลิงก์ในตะกร้า Shopee ได้เลยจ๊ะ ป้าจัดให้ ของแท้ราคาดี",
        # caption ต้องเป็นข้อความล้วน (ไม่มี inline hashtag) — consumer ทุกตัว
        # (cron analyze / _build_fb_caption / batch_generate_content) ต่อ hashtags
        # เองด้วย format_hashtags_text(hashtags) ถ้า caption มี tag อยู่แล้วจะซ้ำ
        "caption": f"ป้าใช้เองมาสักพักแล้วจ๊ะ {product_name} ดีจริง คุ้มมาก ลองดูจ๊ะ ไม่ลองไม่รู้!",
        "hashtags": ["ของดีบอกต่อ", "ป้าป้ายยา", "คุ้มมาก", style],
        "title": f"ป้าป้ายยา {product_name} สไตล์ {style}",
        "thumbnail_prompt": f"Warm friendly photo of {product_name} on a wooden shop counter with soft daylight, cozy local shop vibe",
    }


def generate_script_for_product(product_name: str, category: str, price: float, style: str = "standard", tone: str = "neutral", market_tone: str = "") -> dict:
    """
    Generate a customized TikTok/Shorts video script for a product.
    Supports styles: 'standard', 'funny', 'educational', 'unboxing'.
    """
    provider = settings.LLM_PROVIDER
    
    style_prompts = {
        "standard": "เน้นการป้ายยา ปัญหาของลูกค้า และทำไมสินค้านี้ถึงช่วยแก้ปัญหาได้เป็นอย่างดี",
        "funny": "เน้นสไตล์ตลกขบขัน ฮาๆ ล้อเลียนปัญหาชีวิตประจำวันที่ต้องมีสินค้านี้มาแก้ไข",
        "educational": "เน้นให้ความรู้เกี่ยวกับวิธีใช้ เกร็ดความลับ หรือประโยชน์เชิงลึกของสินค้าตัวนี้",
        "unboxing": "เน้นรีวิวแกะกล่องความประทับใจแรก สัมผัสวัสดุ และเปิดโชว์ความคุ้มค่าทันทีที่เห็น"
    }
    
    style_desc = style_prompts.get(style.lower(), style_prompts["standard"])
    
    if provider == "gemini" and settings.GEMINI_API_KEY and "mock" not in settings.GEMINI_API_KEY.lower():
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=persona_system_prompt(tone=tone, market_tone=market_tone))
            
            prompt = f"""
            Write a short video script (15-30s) in Thai for this product:
            Product Name: {product_name}
            Category: {category}
            Price: {price} Baht
            Script Style: {style} ({style_desc})
            
            Your response must be JSON only. Return a JSON object matching this schema:
            {{
                "hook": "string (short hook, first 3 seconds, in Thai)",
                "problem": "string (pain point of target audience, in Thai)",
                "solution": "string (how this product solves it, in Thai)",
                "cta": "string (call to action pointing to affiliate link, in Thai)",
                "caption": "string (engaging post caption with emojis, in Thai)",
                "hashtags": ["tag1", "tag2", "tag3"],
                "title": "string (short catchy video title, in Thai)",
                "thumbnail_prompt": "string (detailed image prompt for generating video cover/thumbnail)"
            }}
            """
            response = call_with_backoff(
                lambda: model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
            )
            return _require_script_keys(json.loads(response.text))
        except Exception as e:
            logger.error(f"Gemini script generation failed: {e}. Falling back to default script.")
            
    elif provider == "openai" and settings.OPENAI_API_KEY and "mock" not in settings.OPENAI_API_KEY.lower():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            prompt = f"""
            Write a TikTok script in Thai for {product_name} ({category}) priced at {price} Baht.
            Style: {style} ({style_desc})
            Format the response exactly as JSON matching the fields: hook, problem, solution, cta, caption, hashtags, title, thumbnail_prompt.
            """
            response = call_with_backoff(
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": persona_system_prompt("Respond only in JSON format with Thai texts.", tone=tone, market_tone=market_tone)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
            )
            return _require_script_keys(json.loads(response.choices[0].message.content))
        except Exception as e:
            logger.error(f"OpenAI script generation failed: {e}. Falling back to default script.")

    elif provider == "groq" and settings.GROQ_API_KEY and "mock" not in settings.GROQ_API_KEY.lower():
        from app.services.llm_clients import groq_clients
        clients = groq_clients()
        prompt = f"""
        Write a TikTok script in Thai for {product_name} ({category}) priced at {price} Baht.
        Style: {style} ({style_desc})
        Format the response exactly as JSON matching the fields: hook, problem, solution, cta, caption, hashtags, title, thumbnail_prompt.
        """
        last_err = None
        for client in clients:
            try:
                response = call_with_backoff(
                    lambda: client.chat.completions.create(
                        model=settings.GROQ_MODEL,
                        messages=[
                            {"role": "system", "content": persona_system_prompt("Respond only in JSON format with Thai texts.", tone=tone, market_tone=market_tone)},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"}
                    )
                )
                return _require_script_keys(json.loads(response.choices[0].message.content))
            except Exception as e:
                last_err = e
                logger.warning(f"Groq key {client.api_key[:8]}... failed: {e} — ลอง key ถัดไป")
        logger.error(f"Groq script generation failed with all keys: {last_err}. Falling back to default script.")

    elif provider == "anthropic" and settings.ANTHROPIC_API_KEY and "mock" not in settings.ANTHROPIC_API_KEY.lower():
        from app.services.llm_clients import anthropic_clients
        clients = anthropic_clients()
        prompt = f"""
        Write a TikTok script in Thai for {product_name} ({category}) priced at {price} Baht.
        Style: {style} ({style_desc})
        Respond with ONLY the raw JSON object (no markdown fences, no extra text)
        matching the fields: hook, problem, solution, cta, caption, hashtags, title, thumbnail_prompt.
        """
        last_err = None
        for client in clients:
            try:
                # Anthropic OpenAI-compat: response_format ถูก ignore → สั่ง JSON ใน prompt เอง
                response = call_with_backoff(
                    lambda: client.chat.completions.create(
                        model=settings.ANTHROPIC_MODEL,
                        messages=[
                            {"role": "system", "content": persona_system_prompt("Respond only in JSON format with Thai texts.", tone=tone, market_tone=market_tone)},
                            {"role": "user", "content": prompt}
                        ]
                    )
                )
                return _require_script_keys(json.loads(response.choices[0].message.content))
            except Exception as e:
                last_err = e
                logger.warning(f"Anthropic key {client.api_key[:8]}... failed: {e} — ลอง key ถัดไป")
        logger.error(f"Anthropic script generation failed with all keys: {last_err}. Falling back to default script.")

    # Mock script generation fallback (เสียงป้าเข็ม) — ไม่เรียก LLM
    return build_template_script(product_name, category, price, style, tone)
