#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup_wizard.py — ตัวช่วยตั้งค่าระบบอัตโนมัติสำหรับผู้ซื้อ (Interactive Turnkey Setup Wizard)

ช่วยให้ผู้ซื้อตั้งค่าระบบได้ง่ายๆ ภายใน 1 นาที โดยไม่ต้องเปิดแก้ไฟล์โค้ดเอง:
1. ตั้งชื่อแบรนด์ / ร้านค้า
2. เลือกเสียงพากย์ภาษาไทย (เสียงผู้หญิง / เสียงผู้ชาย)
3. ใส่ Facebook Page ID & Access Token
4. สร้างไฟล์ .env ให้พร้อมใช้งานทันที
"""
import os
import sys
import shutil
from pathlib import Path

# บังคับ UTF-8 สำหรับ Windows Console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / "backend" / ".env"
ROOT_ENV_FILE = ROOT_DIR / ".env"
ENV_EXAMPLE = ROOT_DIR / ".env.example"

def print_header():
    print("=" * 68)
    print("🚀  ยินดีต้อนรับสู่ระบบติดตั้ง Shopee Affiliate & AI Reels Automation")
    print("     (Commercial Turnkey Edition — ตัวช่วยตั้งค่าใน 1 นาที)")
    print("=" * 68)
    print("💡 ตัวช่วยนี้จะสร้างไฟล์ตั้งค่า (.env) ให้คุณโดยอัตโนมัติ\n")


def ask_input(prompt: str, default: str = "") -> str:
    if default:
        p = f"{prompt} [กด Enter เพื่อใช้ค่าเริ่มต้น: {default}]: "
    else:
        p = f"{prompt}: "
    val = input(p).strip()
    return val if val else default


def main():
    print_header()

    # 1. ตั้งค่าชื่อแบรนด์
    print("🏷️  [ขั้นตอนที่ 1/4] ข้อมูลแบรนด์และร้านค้า")
    bot_name = ask_input("👉 ระบุชื่อแบรนด์หรือชื่อร้านของคุณ", "ป้าเข็ม ขายของ")
    brand_slogan = ask_input("👉 ระบุสโลแกนร้าน", "คัดของดี ของเด็ด Shopee แท้ 100% • รีวิวแน่น")
    brand_color = ask_input("👉 โทนสีปุ่มในการ์ดสินค้า (Hex code เช่น #EE4D2D สีส้ม, #2ECC71 สีเขียว)", "#EE4D2D")

    # 2. เลือกเสียงพากย์ภาษาไทย
    print("\n🎙️  [ขั้นตอนที่ 2/4] เลือกเสียงพากย์ภาษาไทย (Thai Neural TTS)")
    print("  [1] เสียงผู้หญิง (th-TH-PremwadeeNeural) — อบอุ่น นุ่มนวล แนะนำสินค้าดีมาก (แนะนำ)")
    print("  [2] เสียงผู้ชาย (th-TH-NiwatNeural) — มั่นใจ ชัดถ้อยชัดคำ เป็นมืออาชีพ")
    voice_choice = ask_input("👉 เลือกหมายเลขเสียง (1 หรือ 2)", "1")
    voice_name = "th-TH-PremwadeeNeural" if voice_choice == "1" else "th-TH-NiwatNeural"

    # 3. Facebook Page
    print("\n📱  [ขั้นตอนที่ 3/4] ข้อมูล Facebook Page สำหรับโพสต์ Reels")
    page_id = ask_input("👉 ระบุ Facebook Page ID", "1307380735783361")
    page_token = ask_input("👉 ระบุ Facebook Page Access Token", "")
    
    # 4. AI API Key
    print("\n🧠  [ขั้นตอนที่ 4/4] Groq AI API Key (สำหรับเขียนแคปชั่นป้ายยา)")
    groq_key = ask_input("👉 ระบุ Groq API Key (รับฟรีจาก console.groq.com)", "gsk_")

    # บันทึกไฟล์ .env
    env_content = f"""# =============================================================================
# 🛍️ Shopee Affiliate & Facebook Reels Automation — Configured via Setup Wizard
# =============================================================================

# 1. ข้อมูลแบรนด์ (White-Label Branding)
BOT_NAME="{bot_name}"
BRAND_SLOGAN="{brand_slogan}"
BRAND_COLOR="{brand_color}"
TTS_VOICE="{voice_name}"

# 2. AI Provider
LLM_PROVIDER="groq"
GROQ_API_KEY="{groq_key}"
GROQ_MODEL="openai/gpt-oss-120b"

# 3. Facebook Reels Automation
FACEBOOK_PAGE_ID="{page_id}"
FACEBOOK_PAGE_ACCESS_TOKEN="{page_token}"
POSTING_SPACING_HOURS="2.0"
MAX_REELS_PER_DAY="30"

# 4. Database (SQLite ในเครื่อง)
DATABASE_URL="sqlite:///./affiliate_db.db"
"""

    ROOT_ENV_FILE.write_text(env_content, encoding="utf-8")
    ENV_FILE.write_text(env_content, encoding="utf-8")

    print("\n" + "=" * 68)
    print("🎉 ตั้งค่าระบบเรียบร้อยสมบูรณ์ 100%!")
    print(f"📁 บันทึกไฟล์คอนฟิกไปที่: .env และ backend/.env เรียบร้อยแล้ว")
    print("🚀 คุณสามารถเริ่มต้นระบบได้ทันทีโดยดับเบิ้ลคลิกที่ไฟล์: start_system.bat")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
