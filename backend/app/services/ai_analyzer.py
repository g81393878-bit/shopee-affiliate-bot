import json
import logging
import math
from app.config import settings
from app.schemas import AIAnalysisResult, ScriptGeneratorResponse

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
        "hook": f"รู้ไหมครับว่าทำไมคนถึงหาซื้อ {name} กันเยอะขนาดนี้ในตอนนี้?",
        "problem": f"หลายคนเจอปัญหาที่ต้องใช้เวลาจัดการนาน หรือสินค้าทั่วไปใช้งานไม่ได้ดั่งใจ...",
        "solution": f"ตัวนี้ช่วยได้เลยครับ ด้วยดีไซน์และฟังก์ชันที่ตอบโจทย์ สะดวกขึ้นเยอะมาก",
        "cta": f"ใครสนใจ พิกัดลิงก์ตะกร้า Shopee ในคอมเมนต์หรือหน้าโปรไฟล์เลยครับ!",
        "caption": f"ไอเทมเด็ดที่ต้องมีติดตัว! รีวิว {name} ใช้ง่ายดีต่อใจมาก #ShopeeAffiliate #ป้ายยา #ของดีบอกต่อ",
        "hashtags": ["ShopeeAffiliate", "รีวิวของดี", "ของดีบอกต่อ", "ป้ายยา"],
        "title": f"รีวิวเจาะลึก {name}",
        "thumbnail_prompt": f"Close-up high-quality photo of {name} on a clean table with soft warm lighting, minimalist style"
    }
    
    return {
        "product_score": score,
        "recommendation": recommendation,
        "reasons": reasons,
        "content_ideas": content_ideas,
        "script": script
    }


def analyze_product_with_ai(name: str, category: str, price: float, rating: float, sales_count: int, commission: float) -> dict:
    score = calculate_heuristic_score(sales_count, rating, commission, price)
    provider = settings.LLM_PROVIDER
    
    # Try calling AI if API Key is not a placeholder
    if provider == "gemini" and settings.GEMINI_API_KEY and "mock" not in settings.GEMINI_API_KEY.lower():
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""
            You are an AI Affiliate Marketing Specialist. Analyze this Shopee product:
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
            # Ensure the score matches the calculated score
            data["product_score"] = score
            return data
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
            
            Provide recommendations, reasons, content ideas, and a TikTok script in Thai.
            """
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Respond only with JSON conforming to the requested schema. Use Thai language for content fields."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            data["product_score"] = score
            return data
        except Exception as e:
            logger.error(f"OpenAI API analysis failed: {e}. Falling back to mock data.")

    # Fallback to mock data if no keys configured or API calls failed
    return get_mock_analysis(name, price, rating, sales_count, commission, score)
