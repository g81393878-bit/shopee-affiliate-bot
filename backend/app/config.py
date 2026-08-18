import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class Settings:
    PORT: int = int(os.getenv("PORT", 8000))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./affiliate_db.db")
    
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    # Groq model (OpenAI-compatible API): e.g. openai/gpt-oss-120b
    # (llama-3.3-70b-versatile ถูกถอดออก 16/08/2026 — ตาม docs deprecation ของ Groq)
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    # Groq vision model สำหรับ OCR สลิป (อ่านรูป): ต้องเป็น model ที่รองรับภาพ
    SLIP_OCR_MODEL: str = os.getenv("SLIP_OCR_MODEL", "qwen/qwen3.6-27b")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    # Claude model ผ่าน OpenAI-compat endpoint (https://api.anthropic.com/v1/): e.g. claude-opus-5
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")
    
    # Choose: 'gemini', 'openai', 'groq', or 'anthropic'
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()

    # LLM rate limiting + retry (กัน HTTP 429 เมื่อยิงวิเคราะห์หลายโพสต์พร้อมกัน):
    #   LLM_RATE_LIMIT_RPM  = จำกัดจำนวน call/นาที (0 = ปิด throttle)
    #   LLM_RETRY_*        = retry แบบ exponential backoff เมื่อโดน 429/5xx/เน็ตล่ม
    LLM_RATE_LIMIT_RPM: int = int(os.getenv("LLM_RATE_LIMIT_RPM", "20"))
    LLM_RETRY_MAX_ATTEMPTS: int = int(os.getenv("LLM_RETRY_MAX_ATTEMPTS", "3"))
    LLM_RETRY_BASE_DELAY: float = float(os.getenv("LLM_RETRY_BASE_DELAY", "1.0"))
    LLM_RETRY_MAX_DELAY: float = float(os.getenv("LLM_RETRY_MAX_DELAY", "30.0"))
    
    # LINE Messaging API Keys
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")

    # Facebook Messenger (Webhook) — เพจ/แอป Facebook (docs/facebook-architecture-guide.md)
    FACEBOOK_APP_ID: str = os.getenv("FACEBOOK_APP_ID", "")
    FACEBOOK_APP_SECRET: str = os.getenv("FACEBOOK_APP_SECRET", "")
    FACEBOOK_VERIFY_TOKEN: str = os.getenv("FACEBOOK_VERIFY_TOKEN", "")
    FACEBOOK_PAGE_ACCESS_TOKEN: str = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")

    # ลิงก์ LINE OA จริง (https://line.me/R/ti/p/@xxxxx) — ใช้ในข้อความแนะนำบอท
    LINE_OA_URL: str = os.getenv("LINE_OA_URL", "")

    # Shopee Affiliate Open API (จากอีเมล Shopee หลังอนุมัติ)
    SHOPEE_AFFILIATE_PARTNER_ID: str = os.getenv("SHOPEE_AFFILIATE_PARTNER_ID", "")
    SHOPEE_AFFILIATE_SECRET: str = os.getenv("SHOPEE_AFFILIATE_SECRET", "")

    # Supabase REST keys (Project: usqhvujqmnxqrdoovvnp)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_PUBLISHABLE_KEY: str = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    SUPABASE_SECRET_KEY: str = os.getenv("SUPABASE_SECRET_KEY", "")

settings = Settings()
