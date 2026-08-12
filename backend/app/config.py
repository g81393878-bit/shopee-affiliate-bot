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
    # Groq model (OpenAI-compatible API): e.g. llama-3.3-70b-versatile
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    # Choose: 'gemini', 'openai', or 'groq'
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    # LINE Messaging API Keys
    LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")

    # Shopee Affiliate Open API (จากอีเมล Shopee หลังอนุมัติ)
    SHOPEE_AFFILIATE_PARTNER_ID: str = os.getenv("SHOPEE_AFFILIATE_PARTNER_ID", "")
    SHOPEE_AFFILIATE_SECRET: str = os.getenv("SHOPEE_AFFILIATE_SECRET", "")

    # Supabase REST keys (Project: usqhvujqmnxqrdoovvnp)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_PUBLISHABLE_KEY: str = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    SUPABASE_SECRET_KEY: str = os.getenv("SUPABASE_SECRET_KEY", "")

settings = Settings()
