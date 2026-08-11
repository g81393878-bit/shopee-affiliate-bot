import json
import logging
from app.config import settings
from app.schemas import ScriptGeneratorResponse

logger = logging.getLogger(__name__)

def generate_script_for_product(product_name: str, category: str, price: float, style: str = "standard") -> dict:
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
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""
            You are a professional TikTok creator. Write a short video script (15-30s) in Thai for this product:
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
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
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
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a creative social media script writer. Respond only in JSON format with Thai texts."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"OpenAI script generation failed: {e}. Falling back to default script.")

    elif provider == "groq" and settings.GROQ_API_KEY and "mock" not in settings.GROQ_API_KEY.lower():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

            prompt = f"""
            Write a TikTok script in Thai for {product_name} ({category}) priced at {price} Baht.
            Style: {style} ({style_desc})
            Format the response exactly as JSON matching the fields: hook, problem, solution, cta, caption, hashtags, title, thumbnail_prompt.
            """
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a creative social media script writer. Respond only in JSON format with Thai texts."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Groq script generation failed: {e}. Falling back to default script.")

    # Mock script generation fallback
    return {
        "hook": f"หยุดดูคลิปนี้ก่อน! ถ้าคุณกำลังมองหา {product_name} ที่คุ้มค่าที่สุดในตอนนี้",
        "problem": f"หลายคนบ่นว่าซื้อสินค้าแบบนี้มาใช้แล้วพังง่าย หรือราคาแพงเกินไปสำหรับสไตล์นี้",
        "solution": f"แต่ตัวนี้ออกแบบมาเน้นสไตล์ {style} คุณภาพดีสมราคา ใช้งานง่ายมากครับ",
        "cta": f"พิกัดจิ้มหน้าโปรไฟล์หรือลิงก์ด้านล่างได้เลย ของแท้ราคาดีที่สุดในสัปดาห์นี้!",
        "caption": f"ตามหา {product_name} ดี ๆ อยู่ใช่ไหม? รีวิวสั้นแบบเน้น ๆ สไตล์ {style}! #TikTokป้ายยา #รีวิวของดี #ใช้ดีบอกต่อ",
        "hashtags": ["TikTokป้ายยา", "รีวิวของดี", "ใช้ดีบอกต่อ", style],
        "title": f"ป้ายยา {product_name} สไตล์ {style}",
        "thumbnail_prompt": f"Dramatic photo of {product_name} package opening with light rays coming out, studio lighting"
    }
