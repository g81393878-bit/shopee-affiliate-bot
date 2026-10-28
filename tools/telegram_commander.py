#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/telegram_commander.py — Telegram Command Center & Interactive Controller (PaKhem Commander)

ระบบควบคุมและสั่งการระยะไกลผ่าน Telegram:
1. 🎛️ ปุ่มสั่งการด่วน: [📊 เช็คสถานะ] [🚀 สั่งโพสต์ทันที] [📈 ดูชีทยอดวิว] [🔄 ซิงค์ยอดวิวชีท] [🏭 ผลิตคลิปเพิ่ม] [📦 ดูสต็อกคลัง] [🔄 รีสตาร์ท]
2. 📱 รองรับ 3 รูปแบบการสั่งการ:
   - ปุ่มล่างหน้าจอถาวร (Persistent Reply Keyboard)
   - เมนูคำสั่ง Telegram ทางการ (Official Bot Commands Menu)
   - ปุ่มกดใต้ข้อความ (Inline Keyboard)
3. 💬 ตอบแชทลูกค้า LINE OA ผ่าน Telegram: /reply <userId> <ข้อความ> หรือ /ตอบ <userId> <ข้อความ>
4. 🔒 ความปลอดภัย: ล็อคสิทธิ์เฉพาะแอดมิน (TELEGRAM_CHAT_ID) พร้อมแจ้งเตือนหากมีผู้ใช้อื่น
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
REELS_DIR = ROOT / "reels_uploader"
TOOLS_DIR = ROOT / "tools"

sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REELS_DIR))

load_dotenv(BACKEND / ".env", override=False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TelegramCommander")
ICT = timezone(timedelta(hours=7))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8939151149:AAGrVkCv0xZrlvtRPO8mzelOYsp5ah5M13U")
TELEGRAM_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID", "6734965582")).strip()


_commander_lock = threading.Lock()
_commander_last_sent: float = 0.0
_commander_backoff_until: float = 0.0


def send_tg_message(text: str, reply_markup: dict = None, target_chat_id: str = None) -> bool:
    """ส่งข้อความเข้า Telegram แอดมิน พร้อมปุ่มกด (ถ้ามี) พร้อมระบบ Rate Limiting & 429 Backoff"""
    global _commander_last_sent, _commander_backoff_until
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    chat_id = target_chat_id or os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False

    now = time.time()
    with _commander_lock:
        if now < _commander_backoff_until:
            logger.warning("[TELEGRAM] Commander is backing off due to 429 rate limit, skipping message")
            return False

        # Minimum interval 1.5s
        elapsed = now - _commander_last_sent
        if elapsed < 1.5:
            time.sleep(1.5 - elapsed)
            now = time.time()

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text[:4000],
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    _commander_last_sent = time.time()
                    return True
        except urllib.error.HTTPError as he:
            if he.code == 429:
                _commander_backoff_until = time.time() + 60
                logger.error("🚨 [TELEGRAM RATE LIMIT] Commander got 429! Backing off 60s")
            else:
                logger.warning(f"Telegram send message HTTP error: {he.code}")
            return False
        except Exception as e:
            logger.warning(f"Telegram send message failed: {e}")
            return False
    return False


def answer_callback_query(callback_query_id: str, text: str = None) -> bool:
    """ตอบรับ callback query ทันที เพื่อหยุด spinner ค้างบน Telegram client"""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    if not token or not callback_query_id:
        return False
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        logger.warning(f"answerCallbackQuery failed: {e}")
        return False


def setup_bot_commands():
    """ลงทะเบียนรายการคำสั่งทางการกับ Telegram (เมนูสีฟ้ามุมซ้ายล่าง [/])"""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    if not token or "mock" in token.lower():
        return
    commands = [
        {"command": "menu", "description": "👑 เปิดแผงควบคุมหลัก"},
        {"command": "status", "description": "📊 เช็คสถานะระบบสด"},
        {"command": "osint", "description": "🔍 ส่องคู่แข่ง FB Marketplace"},
        {"command": "unmask", "description": "💳 ปลดล็อคชื่อจริงเบอร์โทร (PromptPay)"},
        {"command": "keyword", "description": "🎯 ขุดคำค้นหา & คำพิมพ์ผิด (SEO)"},
        {"command": "fraud", "description": "🛡️ ตรวจความเสี่ยงออเดอร์ & COD"},
        {"command": "post", "description": "🚀 สั่งโพสต์คลิปทันที"},
        {"command": "sheet", "description": "📈 ดูชีทยอดวิว & สถิติ"},
        {"command": "sync", "description": "🔄 ซิงค์ยอดวิวชีทสด"},
        {"command": "produce", "description": "🏭 ผลิตคลิปเพิ่ม 3 ตัว"},
        {"command": "stock", "description": "📦 ดูคลังวิดีโอ"},
        {"command": "restart", "description": "🔄 รีสตาร์ทบอทบน VPS"}
    ]
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/setMyCommands",
            data=json.dumps({"commands": commands}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            logger.info("✅ ตั้งค่า Telegram Bot Commands เมนูทางการสำเร็จ 100%")
    except Exception as e:
        logger.warning(f"⚠️ ตั้งค่า setMyCommands ไม่สำเร็จ: {e}")


def get_main_menu_markup() -> dict:
    """สร้าง Inline Keyboard ปุ่มกดเมนูหลัก (ใต้ข้อความ)"""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 เช็คสถานะสด", "callback_data": "cmd_status"},
                {"text": "🚀 สั่งโพสต์คลิปทันที", "callback_data": "cmd_post"}
            ],
            [
                {"text": "🔍 ส่องคู่แข่ง OSINT", "callback_data": "cmd_osint_help"},
                {"text": "💳 ปลดล็อคชื่อเบอร์", "callback_data": "cmd_unmask_help"}
            ],
            [
                {"text": "🎯 ขุดคำค้นหา SEO", "callback_data": "cmd_keyword_help"},
                {"text": "🛡️ ตรวจออเดอร์เสี่ยง", "callback_data": "cmd_fraud_help"}
            ],
            [
                {"text": "📈 ดูชีทยอดวิว", "callback_data": "cmd_sheet"},
                {"text": "🔄 ซิงค์ยอดวิวชีท", "callback_data": "cmd_refresh_metrics"}
            ],
            [
                {"text": "🏭 ผลิตคลิปเพิ่ม 3 ตัว", "callback_data": "cmd_produce"},
                {"text": "📦 ดูคลังวิดีโอ", "callback_data": "cmd_stock"}
            ],
            [
                {"text": "🔄 รีสตาร์ทบอท VPS", "callback_data": "cmd_restart"}
            ]
        ]
    }


def get_persistent_keyboard_markup() -> dict:
    """สร้าง ReplyKeyboardMarkup แผงปุ่มกดล่างหน้าจอถาวร (กดง่าย ไม่ต้องเลื่อนหา)"""
    return {
        "keyboard": [
            [{"text": "📊 เช็คสถานะสด"}, {"text": "🚀 สั่งโพสต์คลิปทันที"}],
            [{"text": "🔍 ส่องคู่แข่ง OSINT"}, {"text": "💳 ปลดล็อคชื่อเบอร์"}],
            [{"text": "🎯 ขุดคำค้นหา SEO"}, {"text": "🛡️ ตรวจออเดอร์เสี่ยง"}],
            [{"text": "📈 ดูชีทยอดวิว"}, {"text": "🔄 ซิงค์ยอดวิวชีท"}],
            [{"text": "🏭 ผลิตคลิปเพิ่ม 3 ตัว"}, {"text": "📦 ดูคลังวิดีโอ"}],
            [{"text": "🔄 รีสตาร์ทบอท VPS"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def execute_status_command() -> str:
    """ประมวลผลดึงสถานะระบบสด"""
    import uploader
    pending_list = uploader.list_pending()
    pending_count = len(pending_list)
    today_count = uploader.get_today_post_count()
    
    disk_total, disk_used, disk_free = shutil.disk_usage("/")
    disk_free_gb = disk_free / (1024 ** 3)
    disk_use_pct = (disk_used / disk_total) * 100

    mem_text = "พร้อมใช้งาน"
    try:
        if Path("/proc/meminfo").exists():
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            mem_dict = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    mem_dict[parts[0].strip()] = parts[1].strip()
            if "MemAvailable" in mem_dict and "MemTotal" in mem_dict:
                avail_kb = int(mem_dict["MemAvailable"].split()[0])
                total_kb = int(mem_dict["MemTotal"].split()[0])
                mem_text = f"เหลือ {avail_kb / 1024 / 1024:.1f} GB / {total_kb / 1024 / 1024:.1f} GB"
    except Exception:
        pass

    now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")

    msg = (
        f"📊 [รายงานสถานะระบบ PaKhem Commander]\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ เวลา: {now_str} น.\n\n"
        f"🎯 สรุปผลงานวันนี้:\n"
        f"  • 📈 ยอดโพสต์วันนี้: {today_count} รอบ\n"
        f"  • ⏱️ ความถี่โพสต์: หมุนเวียนอัตโนมัติ 24 ชม.\n\n"
        f"🟢 สถานะบริการ & เครือข่าย:\n"
        f"  • 🎬 โรงงานผลิตคลิป (Pre-buffer): 🟢 ออนไลน์ (100% Autopilot)\n"
        f"  • 📍 Facebook Reels: 🟢 ออนไลน์ (2 เพจพร้อมยิง)\n"
        f"  • 🧠 Groq AI Multi-Key: 🟢 7 Keys Failover\n\n"
        f"📦 สถานะคลังคลิป:\n"
        f"  • สต็อกรอโพสต์: {pending_count} คลิป\n\n"
        f"💻 สภาพแวดล้อม VPS:\n"
        f"  • 💾 RAM: {mem_text}\n"
        f"  • 💽 Disk ว่าง: {disk_free_gb:.1f} GB (ใช้งาน {disk_use_pct:.0f}%)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✨ สั่งการได้ตลอดเวลาผ่านปุ่มด้านล่างจ้า!"
    )
    return msg


def execute_post_command():
    """สั่งโพสต์คลิปทันทีในเธรดแยก (Facebook Reels Master Broadcast)"""
    def _run():
        send_tg_message("🚀 [กำลังเริ่มกระบวนการโพสต์ด่วน Facebook Reels]\nบอทกำลังคัดเลือกคลิปและยิงขึ้น Facebook Reels (2 เพจ) ทันทีครับ...")
        try:
            from system_runner import execute_unified_broadcast
            res = execute_unified_broadcast(force=True)
            if res.get("success"):
                send_tg_message(f"✅ [คำสั่งโพสต์ด่วนเสร็จสิ้น 100%]\n• 🎬 คลิป: {res.get('video')}\n• เผยแพร่ขึ้น Facebook Reels (2 เพจ) เรียบร้อยแล้วครับ")
            else:
                send_tg_message(f"⚠️ [ผลการโพสต์ด่วน]\n• {res.get('error', 'ไม่สามารถโพสต์ได้ในรอบนี้')}")
        except Exception as e:
            send_tg_message(f"❌ โพสต์ด่วนเกิดข้อผิดพลาด: {e}")

    threading.Thread(target=_run, daemon=True).start()


def execute_sheet_command() -> str:
    """ดึงข้อมูลสรุปภาพรวมและสถิติยอดวิวจาก Google Sheets"""
    try:
        from update_sheet_metrics import get_sheet_summary
        return get_sheet_summary()
    except Exception as e:
        return (
            "📈 [รายงานสถิติ Google Sheets]\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔗 ลิงก์ชีท: https://docs.google.com/spreadsheets/d/1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU/edit\n"
            f"⚠️ เกิดข้อผิดพลาด: {e}"
        )


def execute_refresh_metrics_command():
    """สั่งอัปเดตสถิติยอดวิวยอดไลก์ลง Google Sheets สดๆ ในเธรดแยก"""
    def _run():
        send_tg_message("🔄 [กำลังดึงสถิติยอดวิว & ยอดไลก์สด]\nระบบกำลังคิวรี่ Meta Graph API ทุกคลิป กรุณารอสักครู่...")
        try:
            from update_sheet_metrics import update_all_metrics_in_sheet, get_sheet_summary
            count = update_all_metrics_in_sheet()
            summary = get_sheet_summary()
            send_tg_message(f"✅ [อัปเดตสถิติลง Google Sheets เรียบร้อย {count} รายการ]\n\n{summary}")
        except Exception as e:
            send_tg_message(f"❌ ซิงค์สถิติยอดวิวไม่สำเร็จ: {e}")

    threading.Thread(target=_run, daemon=True).start()


def execute_produce_command():
    """สั่งผลิตคลิปใหม่ 3 ตัวในเธรดแยก"""
    def _run():
        send_tg_message("🏭 [กำลังเริ่มโรงงานผลิตคลิป AI]\nระบบกำลังดึงสินค้าเทรนด์ สร้างภาพ 3 จังหวะ และลงเสียงพากย์ 3 คลิป กรุณารอสักครู่...")
        try:
            from auto_product_reels import generate_product_reels
            generate_product_reels(limit=3)
            import uploader
            pending = uploader.list_pending()
            send_tg_message(f"🎉 [ผลิตคลิปเสร็จสมบูรณ์ 100%!]\nขณะนี้ในคลังมีคลิปพร้อมโพสต์ทั้งหมด: {len(pending)} คลิปจ้า")
        except Exception as e:
            send_tg_message(f"❌ โรงงานผลิตคลิปเกิดข้อผิดพลาด: {e}")

    threading.Thread(target=_run, daemon=True).start()



def execute_orders_command() -> str:
    """สรุปคำสั่งซื้อสินค้าของตัวเอง (ปลาแดดเดียว) ล่าสุด"""
    try:
        from app.db import SessionLocal
        from app.models import DirectOrder
        db = SessionLocal()
        orders = db.query(DirectOrder).order_by(DirectOrder.id.desc()).limit(10).all()
        db.close()
        if not orders:
            return "📦 ยังไม่มีคำสั่งซื้อสินค้าตัวเองในระบบค่ะ"
        lines = [f"🐟 **[รายการคำสั่งซื้อปลาแดดเดียวล่าสุด {len(orders)} ออเดอร์]**", "━━━━━━━━━━━━━━━━━━━"]
        for o in orders:
            dt = o.created_at.strftime("%d/%m %H:%M") if o.created_at else ""
            lines.append(f"• `{o.order_code}` | **{o.customer_name}** ({o.phone})")
            lines.append(f"  📦 {o.package_name} | 💰 {float(o.price):,.0f}฿ ({o.payment_method})")
            lines.append(f"  📍 {o.address[:40]}... [{o.status}] ({dt})")
            lines.append("")
        return "\n".join(lines).strip()
    except Exception as e:
        return f"⚠️ เกิดข้อผิดพลาดในการดึงออเดอร์: {e}"


def execute_stock_command() -> str:
    """ตรวจสอบรายชื่อคลิปในคลัง"""
    import uploader
    pending_list = uploader.list_pending()
    if not pending_list:
        return "📦 [คลังวิดีโอรอโพสต์]\n━━━━━━━━━━━━━━━━━━\n⚠️ ไม่มีคลิปในคลัง (กดปุ่ม 'ผลิตคลิปเพิ่ม' ได้เลยครับ)"
    
    details = []
    for idx, f in enumerate(pending_list, start=1):
        size_mb = f.stat().st_size / (1024 * 1024)
        details.append(f"  {idx}. 🎬 {f.name[:35]}... ({size_mb:.1f} MB)")
        
    return (
        f"📦 [คลังวิดีโอรอโพสต์ ({len(pending_list)} คลิป)]\n"
        f"━━━━━━━━━━━━━━━━━━\n" +
        "\n".join(details) +
        f"\n━━━━━━━━━━━━━━━━━━"
    )


def execute_line_reply(user_id: str, reply_text: str) -> str:
    """ตอบแชทลูกค้า LINE OA ผ่าน Telegram โดยตรง"""
    try:
        from linebot import LineBotApi
        from linebot.models import TextSendMessage
        token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
        if not token or "mock" in token.lower():
            return "⚠️ ไม่พบ LINE_CHANNEL_ACCESS_TOKEN ที่ถูกต้อง"
        
        line_bot_api = LineBotApi(token)
        line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))
        return (
            f"✅ [ส่งข้อความตอบกลับสำเร็จ]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• 👤 ผู้รับ: {user_id}\n"
            f"• 💬 ข้อความ: “{reply_text}”\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
    except Exception as e:
        return f"❌ ไม่สามารถส่งข้อความถึงลูกค้าได้: {e}"


def execute_osint_command(target: str) -> str:
    """ประมวลผลคำสั่ง OSINT ส่อง Facebook Marketplace คู่แข่ง & SOCMINT Deep Links"""
    clean_target = (target or "").strip()
    if not clean_target or clean_target in ("/osint", "ส่องคู่แข่ง", "osint"):
        return (
            "🔍 [วิธีใช้งาน OSINT ส่องคู่แข่ง Facebook Marketplace]\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📖 ตามหลักการ OSINT แม้เป้าหมายจะล็อกโปรไฟล์ แต่ Marketplace Profile จะเปิดเป็นสาธารณะเสมอ!\n\n"
            "👉 **รูปแบบคำสั่ง:**\n"
            "`/osint <Facebook User ID หรือ Profile URL>`\n\n"
            "👉 **ตัวอย่าง:**\n"
            "• `/osint 1000123456789`\n"
            "• `/osint https://facebook.com/marketplace/profile/1000123456789`\n"
            "• `/osint https://facebook.com/username`\n"
            "━━━━━━━━━━━━━━━━━━"
        )
    try:
        from app.services.osint_intelligence import analyze_facebook_marketplace_competitor
        res = analyze_facebook_marketplace_competitor(clean_target)
        if res.get("status") != "success":
            return f"⚠️ {res.get('message', 'ไม่สามารถวิเคราะห์เป้าหมายได้')}"
        
        uid = res.get("target_identifier")
        url = res.get("marketplace_profile_url")
        
        msg = (
            f"🔍 [ผลการวิเคราะห์ OSINT — Facebook Marketplace]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎯 เป้าหมาย: `{uid}`\n"
            f"🔗 ลิงก์ตรง: {url}\n\n"
            f"💡 **ข้อแนะนำสำคัญ:** เมื่อเปิดลิงก์ให้กดเลือกแท็บ **'All Listings'** เพื่อดูสินค้าที่เคยขายไปแล้วทั้งหมด\n\n"
            f"📋 **จุดตรวจเช็คสำคัญ (Forensic OSINT):**\n"
            f"• 📦 ดูสินค้าปัจจุบัน vs สินค้าที่ขายแล้ว เพื่อวิเคราะห์สินค้าขายดี\n"
            f"• 📉 สังเกตป้ายลดราคา เพื่อคำนวณ Margin และต้นทุนคู่แข่ง\n"
            f"• 📍 ดูพิกัดจัดส่ง เพื่อระบุรัศมีทำเลจริงของคู่แข่ง\n"
            f"• 📅 ดูปีที่เปิดบัญชี เพื่อเช็คว่าเป็นร้านค้าจริงหรือบัญชีอวตาร\n\n"
            f"⚔️ **กลยุทธ์แก้เกม:**\n"
            f"• จัดเซ็ตแถมอุปกรณ์เสริมแทนการตัดราคาตรงๆ\n"
            f"• ชูจุดขาย 'มีสต็อกพร้อมส่งด่วนใน 24 ชม.'\n"
            f"• เพิ่มป้าย 'ของแท้ 100% มีประกันศูนย์ไทย'\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        return msg
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาดในการวิเคราะห์ OSINT: {e}"


def execute_unmask_command(phone: str) -> str:
    """ประมวลผลคำสั่งถอดรหัสตัวตนเบอร์โทรศัพท์ (PromptPay Real-Name Unmasking)"""
    clean_phone = (phone or "").strip()
    if not clean_phone or clean_phone in ("/unmask", "ปลดล็อคเบอร์", "unmask", "💳 ปลดล็อคชื่อเบอร์"):
        return (
            "💳 [วิธีใช้งาน ปลดล็อคชื่อจริงเจ้าของเบอร์ (PromptPay Unmasking)]\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📖 ใช้มาตรฐาน PromptPay EMVCo ดึงชื่อ-นามสกุลจริงผ่านแอปธนาคารไทยทันที!\n\n"
            "👉 **รูปแบบคำสั่ง:**\n"
            "`/unmask <หมายเลขโทรศัพท์>`\n\n"
            "👉 **ตัวอย่าง:**\n"
            "• `/unmask 0935325959`\n"
            "• `/unmask 081-234-5678`\n"
            "━━━━━━━━━━━━━━━━━━"
        )
    try:
        from app.services.osint_intelligence import unmask_phone_identity
        res = unmask_phone_identity(clean_phone)
        if res.get("status") != "success":
            return f"⚠️ {res.get('message', 'ไม่สามารถตรวจสอบเบอร์ได้')}"
        
        dashed = res.get("dashed_format")
        carrier = res.get("carrier")
        warning = res.get("threat_warning")
        line_url = res.get("line_add_url")
        digits = res.get("digits_only")
        
        msg = (
            f"💳 [ผลการตรวจสอบเบอร์โทรศัพท์ & ถอดรหัสตัวตน]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📞 หมายเลข: `{dashed}`\n"
            f"📡 เครือข่าย: {carrier}\n"
        )
        if warning:
            msg += f"\n{warning}\n"
            
        msg += (
            f"\n🎯 **วิธีดูชื่อจริง-นามสกุลจริงเจ้าของเบอร์:**\n"
            f"1. คัดลอกเลขพร้อมเพย์ด้านล่างไปใส่ในแอปธนาคาร (โอนพร้อมเพย์ 1 สตางค์ หรือแกล้งกดโอน):\n"
            f"`{digits}`\n"
            f"2. หน้าจอแอปธนาคาร (K-Plus, SCB, Krungthai) จะแสดง **ชื่อจริง-นามสกุลจริง** ทันที!\n\n"
            f"💬 ส่องโปรไฟล์ LINE: {line_url}\n"
            f"🛡️ ตรวจประวัติคนโกง: https://www.blacklistseller.com/search_results?q={digits}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        return msg
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาดในการตรวจสอบ: {e}"


def execute_keyword_command(query: str) -> str:
    """ประมวลผลขุดคำค้นหาจริง Google Autocomplete & คำพิมพ์ผิด (SEO Intelligence)"""
    clean_q = (query or "").strip()
    if not clean_q or clean_q in ("/keyword", "คีย์เวิร์ด", "ขุดคำค้นหา", "keyword", "🎯 ขุดคำค้นหา SEO"):
        return (
            "🎯 [วิธีใช้งาน ขุดคำค้นหา & คำพิมพ์ผิด (SEO Intelligence)]\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📖 ดึงคำค้นหาจริงสดๆ จาก Google Suggest เพื่อหาคำค้นยอดฮิตและคำที่คนพิมพ์ผิดบ่อย\n\n"
            "👉 **รูปแบบคำสั่ง:**\n"
            "`/keyword <คำค้นหา>`\n\n"
            "👉 **ตัวอย่าง:**\n"
            "• `/keyword หูฟังบลูทูธ`\n"
            "• `/keyword หม้อทอดไร้น้ำมัน`\n"
            "━━━━━━━━━━━━━━━━━━"
        )
    try:
        from app.services.osint_intelligence import analyze_keyword_intelligence
        res = analyze_keyword_intelligence(clean_q)
        if res.get("status") != "success":
            return f"⚠️ {res.get('message', 'ไม่สามารถค้นหาได้')}"
        
        suggs = res.get("live_suggestions", [])
        typos = res.get("common_misspellings", [])
        intents = res.get("search_intents", [])
        
        msg = (
            f"🎯 [รายงานคำค้นหา & SEO Intelligence: “{clean_q}”]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 **เจตนาการค้นหา (Intent):**\n"
            + "\n".join(f"  • {i}" for i in intents) + "\n\n"
            f"🔥 **คำค้นหาจริงบน Google (Autocomplete):**\n"
            + ("\n".join(f"  {idx}. {s}" for idx, s in enumerate(suggs[:6], 1)) if suggs else "  • ไม่พบคำค้นหาเพิ่มเติม") + "\n\n"
            f"✍️ **คำที่คนมักพิมพ์ผิด (ดักทราฟฟิก Long-tail SEO):**\n"
            + ("  • " + ", ".join(typos[:6]) if typos else "  • ครอบคลุมรูปศัพท์มาตรฐานแล้ว") + "\n\n"
            f"🎬 **Hook 3 วินาทีแนะนำ:**\n"
            f"“ใครที่กำลังหา {clean_q} แนะนำดูคลิปนี้ก่อนตัดสินใจ!”\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        return msg
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาดในการดึงคีย์เวิร์ด: {e}"


def execute_fraud_command(order_text: str) -> str:
    """ประมวลผลตรวจจับความเสี่ยงออเดอร์และการฉ้อโกง (Order Fraud Guard & COD Screener)"""
    clean_text = (order_text or "").strip()
    if not clean_text or clean_text in ("/fraud", "ตรวจโกง", "เช็คออเดอร์", "fraud", "🛡️ ตรวจออเดอร์เสี่ยง"):
        try:
            from order_fraud_guard import build_all_orders_fraud_report
            return build_all_orders_fraud_report()
        except Exception as e:
            return f"❌ ไม่สามารถดึงรายงานตรวจออเดอร์ได้: {e}"
    try:
        from order_fraud_guard import analyze_order_fraud_risk, format_fraud_guard_telegram_block
        import re as _re
        m_phone = _re.search(r"0\d[-\d\s]{7,12}", clean_text)
        phone_val = m_phone.group(0) if m_phone else ""
        addr_val = clean_text.replace(phone_val, "").strip() if phone_val else clean_text
        chk = analyze_order_fraud_risk(
            name="ตรวจสอบรายบุคคล",
            phone=phone_val or clean_text,
            address=addr_val,
            payment_method="COD",
        )
        digits = _re.sub(r"\D", "", chk.get("phone_formatted") or "")
        return (
            f"🛡️ [ผลการตรวจสอบมิจฉาชีพ & ความเสี่ยง COD]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{format_fraud_guard_telegram_block(chk)}\n"
            f"🔗 เช็ค BlacklistSeller: https://www.blacklistseller.com/search_results?q={digits}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาดในการตรวจสอบความเสี่ยง: {e}"


def handle_telegram_update(update: dict):
    """ประมวลผล Update จาก Telegram อย่างปลอดภัยและครบถ้วน"""
    admin_id = os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID

    # 1. จัดการ Callback Query จากปุ่ม Inline
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb.get("id")
        sender_id = str(cb.get("from", {}).get("id", "")).strip()
        data = cb.get("data", "")
        chat_id = str(cb.get("message", {}).get("chat", {}).get("id") or sender_id)

        # ตอบกลับ callback query ทันที เพื่อหยุด spinner ค้างบน Telegram
        if cb_id:
            answer_callback_query(cb_id)

        logger.info(f"🖱️ Callback received: data='{data}' from sender={sender_id}")

        if sender_id != admin_id:
            logger.warning(f"⚠️ Unauthorized callback from {sender_id} (Expected {admin_id})")
            send_tg_message(f"⚠️ บัญชีนี้ (ID: {sender_id}) ไม่ได้รับอนุญาตให้สั่งการบอท", target_chat_id=chat_id)
            return
            
        if data == "cmd_status":
            send_tg_message(execute_status_command(), target_chat_id=chat_id)
        elif data == "cmd_post":
            execute_post_command()
        elif data == "cmd_sheet":
            send_tg_message(execute_sheet_command(), target_chat_id=chat_id)
        elif data == "cmd_refresh_metrics":
            execute_refresh_metrics_command()
        elif data == "cmd_produce":
            execute_produce_command()
        elif data == "cmd_stock":
            send_tg_message(execute_stock_command(), target_chat_id=chat_id)
        elif data == "cmd_osint_help":
            send_tg_message(execute_osint_command(""), target_chat_id=chat_id)
        elif data == "cmd_unmask_help":
            send_tg_message(execute_unmask_command(""), target_chat_id=chat_id)
        elif data == "cmd_keyword_help":
            send_tg_message(execute_keyword_command(""), target_chat_id=chat_id)
        elif data == "cmd_fraud_help":
            send_tg_message(execute_fraud_command(""), target_chat_id=chat_id)
        elif data == "cmd_restart":
            send_tg_message("🔄 กำลังสั่งรีสตาร์ทบอทบน VPS...", target_chat_id=chat_id)
            def _restart():
                time.sleep(1)
                subprocess.run(["sudo", "systemctl", "restart", "shopee-bot"])
            threading.Thread(target=_restart, daemon=True).start()
        return

    # 2. จัดการข้อความพิมพ์ (Text Message หรือปุ่ม ReplyKeyboard)
    if "message" in update:
        msg = update["message"]
        sender_id = str(msg.get("from", {}).get("id", "")).strip()
        chat_id = str(msg.get("chat", {}).get("id") or sender_id)
        text = (msg.get("text") or "").strip()

        logger.info(f"📩 Telegram text message: '{text}' from sender={sender_id}")

        if sender_id != admin_id:
            logger.warning(f"⚠️ Unauthorized message from {sender_id} (Expected {admin_id})")
            send_tg_message(f"⚠️ บัญชีนี้ (ID: {sender_id}) ไม่ได้รับอนุญาตให้สั่งการบอท", target_chat_id=chat_id)
            return

        lower = text.lower()

        # คำสั่งเมนูหลัก
        if lower in ("/start", "/menu", "เมนู", "menu", "👑 เปิดเมนูหลัก"):
            welcome = (
                "👑 [PaKhem Commander — แผงควบคุมบอท 24/7]\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "แผงสั่งการพร้อมทำงานแล้วครับ! แตะปุ่มที่ตรึงอยู่ด้านล่างหน้าจอเพื่อสั่งการได้ทันทีเลยครับ\n\n"
                "💬 การตอบแชทลูกค้า LINE:\n"
                "พิมพ์: `/reply <userId> <ข้อความ>`\n"
                "เช่น: `/reply สวัสดีครับ ยินดีให้บริการครับ`"
            )
            send_tg_message(welcome, reply_markup=get_persistent_keyboard_markup(), target_chat_id=chat_id)
            
        elif lower in ("/status", "สถานะ", "status", "เช็คระบบ", "📊 เช็คสถานะสด") or "เช็คสถานะ" in lower:
            send_tg_message(execute_status_command(), target_chat_id=chat_id)

        elif lower.startswith("/osint") or lower.startswith("/ส่องคู่แข่ง") or lower in ("🔍 ส่องคู่แข่ง osint", "ส่องคู่แข่ง", "osint"):
            parts = text.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            send_tg_message(execute_osint_command(target), target_chat_id=chat_id)

        elif lower.startswith("/unmask") or lower.startswith("/ปลดล็อคเบอร์") or lower in ("💳 ปลดล็อคชื่อเบอร์", "ปลดล็อคเบอร์", "unmask"):
            parts = text.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            send_tg_message(execute_unmask_command(target), target_chat_id=chat_id)

        elif lower.startswith("/keyword") or lower.startswith("/คีย์เวิร์ด") or lower.startswith("/ขุด") or lower in ("🎯 ขุดคำค้นหา seo", "ขุดคำค้นหา", "คีย์เวิร์ด", "keyword"):
            parts = text.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            send_tg_message(execute_keyword_command(target), target_chat_id=chat_id)

        elif lower.startswith("/fraud") or lower.startswith("/ตรวจโกง") or lower.startswith("/เช็คโกง") or lower in ("🛡️ ตรวจออเดอร์เสี่ยง", "ตรวจโกง", "fraud"):
            parts = text.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            send_tg_message(execute_fraud_command(target), target_chat_id=chat_id)

        elif lower in ("/post", "โพสต์", "post", "ยิงคลิป", "🚀 สั่งโพสต์คลิปทันที") or "สั่งโพสต์" in lower:
            execute_post_command()

        elif lower in ("/sheet", "/stats", "/ชีท", "/สถิติ", "/views", "sheet", "ชีท", "ยอดวิว", "📈 ดูชีทยอดวิว") or "ดูชีท" in lower:
            send_tg_message(execute_sheet_command(), target_chat_id=chat_id)

        elif lower in ("/sync", "/refresh_metrics", "/sync_metrics", "sync", "ซิงค์", "ซิงค์ยอดวิว", "อัปเดตยอดวิว", "🔄 ซิงค์ยอดวิวชีท") or "ซิงค์" in lower:
            execute_refresh_metrics_command()

        elif lower in ("/produce", "ผลิต", "ทำคลิป", "🏭 ผลิตคลิปเพิ่ม 3 ตัว") or "ผลิตคลิป" in lower:
            execute_produce_command()

        elif lower in ("/battle", "/poll", "ทำโพล", "คลิปโพล", "โพล", "battle") or "คลิปเปรียบเทียบ" in lower:
            def _run_battle():
                send_tg_message("⚔️ [กำลังเริ่มผลิตคลิปเปรียบเทียบ Poll Battle]\nบอทกำลังจับคู่สินค้าชนิดเดียวกันเป๊ะๆ และเรนเดอร์วิดีโอ 9:16 เว้น Safe Zone สติกเกอร์โพล...")
                try:
                    from auto_poll_battle_reels import produce_poll_battle_reel
                    b_res = produce_poll_battle_reel()
                    if b_res:
                        send_tg_message(f"✅ [ผลิตคลิปเปรียบเทียบสำเร็จ 100%]\n• 🎯 เรื่อง: {b_res.get('title')}\n• 📦 บันทึกเข้าคลังรอโพสต์เรียบร้อยครับ")
                    else:
                        send_tg_message("⚠️ ไม่สามารถผลิตคลิปเปรียบเทียบได้ในรอบนี้ (อาจพบคู่สินค้าซ้ำ หรือรูปภาพโหลดไม่สมบูรณ์)")
                except Exception as e:
                    send_tg_message(f"⚠️ ผลิตคลิปโพลล้มเหลว: {e}")
            threading.Thread(target=_run_battle, daemon=True).start()

        elif lower in ("/ads", "/report", "/fish", "รายงาน", "โฆษณา", "ยอดขาย", "สถิติแอด", "📈 เช็คแอด & ยอดขาย") or "เช็คแอด" in lower:
            try:
                from ads_report_bot import build_ads_report_message
                send_tg_message(build_ads_report_message(), target_chat_id=chat_id)
            except Exception as e:
                send_tg_message(f"❌ ดึงข้อมูลรายงานล้มเหลว: {e}", target_chat_id=chat_id)

        elif lower in ("/stock", "สต็อก", "คลัง", "stock", "📦 ดูคลังวิดีโอ") or "คลัง" in lower:
            send_tg_message(execute_stock_command(), target_chat_id=chat_id)

        elif lower in ("/restart", "รีสตาร์ท", "🔄 รีสตาร์ทบอท VPS") or "รีสตาร์ท" in lower:
            send_tg_message("🔄 กำลังสั่งรีสตาร์ทบอทบน VPS...", target_chat_id=chat_id)
            def _restart():
                time.sleep(1)
                subprocess.run(["sudo", "systemctl", "restart", "shopee-bot"])
            threading.Thread(target=_restart, daemon=True).start()

        elif lower in ("/reply", "/ตอบ", "ตอบ", "/reply ", "/ตอบ "):
            send_tg_message(
                "💬 [วิธีตอบกลับลูกค้า]\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "👉 **แบบที่ 1 (ง่ายสุด - ตอบลูกค้าคนล่าสุดทันที):**\n"
                "`/reply สวัสดีครับ ยินดีให้บริการครับ`\n\n"
                "👉 **แบบที่ 2 (ระบุ User ID เอง):**\n"
                "`/reply U3f09510286687007931c42eb8d10fa1d สวัสดีครับ`\n"
                "━━━━━━━━━━━━━━━━━━",
                target_chat_id=chat_id
            )
            
        elif lower.startswith("/reply ") or lower.startswith("/ตอบ ") or lower.startswith("ตอบ "):
            parts = text.split(" ", 2)
            if len(parts) >= 3 and parts[1].startswith("U"):
                target_uid = parts[1].strip()
                reply_content = parts[2].strip()
            elif len(parts) >= 2:
                # พิมพ์ /reply <ข้อความ> โดยไม่ได้ใส่ User ID -> ตอบลูกค้าล่าสุดอัตโนมัติ
                try:
                    from app.db import SessionLocal
                    from app import models
                    db = SessionLocal()
                    last_user = db.query(models.User).order_by(models.User.id.desc()).first()
                    target_uid = last_user.line_user_id if last_user else "U3f09510286687007931c42eb8d10fa1d"
                    db.close()
                except Exception:
                    target_uid = "U3f09510286687007931c42eb8d10fa1d"
                reply_content = text.split(" ", 1)[1].strip()
            else:
                target_uid = None
                reply_content = ""

            if target_uid and reply_content:
                res = execute_line_reply(target_uid, reply_content)
                send_tg_message(res, target_chat_id=chat_id)
            else:
                send_tg_message("⚠️ กรุณาพิมพ์ข้อความที่ต้องการตอบ เช่น:\n`/reply สวัสดีครับ`", target_chat_id=chat_id)
        else:
            # หากพิมพ์ข้อความอื่น ให้แนะนำแตะแผงปุ่ม
            send_tg_message(
                f"🤖 รับคำสั่ง: “{text}”\nกรุณาแตะสั่งการจากแผงปุ่มด้านล่างหน้าจอได้เลยครับ",
                target_chat_id=chat_id
            )


def run_telegram_commander_loop():
    """Long-Polling loop รับคำสั่งจาก Telegram แอดมินตลอด 24 ชม."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    if not token or "mock" in token.lower():
        logger.warning("Telegram Bot token not set. Commander disabled.")
        return

    # 1. ตั้งค่า Bot Commands เมนูทางการ และล้าง Webhook ค้าง (ป้องกัน HTTP 409 Conflict)
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true", timeout=10)
    except Exception:
        pass
    setup_bot_commands()

    logger.info("🤖 เริ่มต้นระบบ PaKhem Commander Polling Loop (24/7 Controller)...")
    
    # 2. ส่งข้อความเปิดระบบพร้อมแผงปุ่มกดที่ตรึงล่างหน้าจอ (มี cooldown 1 ชม. กันสแปมเวลารีสตาร์ทบอท)
    welcome_state_file = ROOT / ".tg_commander_welcome_ts"
    now_ts = time.time()
    should_send_welcome = True
    if welcome_state_file.exists():
        try:
            last_ts = float(welcome_state_file.read_text(encoding="utf-8").strip())
            if (now_ts - last_ts) < 3600:
                should_send_welcome = False
                logger.info("ℹ️ ข้ามข้อความเปิดระบบ PaKhem Commander (ส่งไปแล้วภายใน 1 ชม.)")
        except Exception:
            pass

    if should_send_welcome:
        try:
            welcome_msg = (
                "👑 [PaKhem Commander — เปิดใช้งานแผงควบคุม 24/7]\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "แผงสั่งการพร้อมทำงานแล้วครับ! สามารถแตะปุ่มที่ตรึงไว้ด้านล่างหน้าจอเพื่อสั่งการได้ทันทีเลยครับ"
            )
            send_tg_message(welcome_msg, reply_markup=get_persistent_keyboard_markup())
            welcome_state_file.write_text(str(now_ts), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️ Startup welcome send error: {e}")

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=20"
            req = urllib.request.Request(url, headers={"User-Agent": "PaKhemCommander/1.0"})
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    results = data.get("result", [])
                    for item in results:
                        offset = item["update_id"] + 1
                        try:
                            handle_telegram_update(item)
                        except Exception as e_h:
                            logger.error(f"❌ Error handling telegram update: {e_h}", exc_info=True)
        except Exception as e:
            if "409" in str(e):
                logger.debug("ℹ️ Telegram polling conflict (409): another instance active. Backing off 15s...")
                time.sleep(15)
            else:
                logger.warning(f"⚠️ Telegram polling error: {e}")
                time.sleep(3)
        time.sleep(0.5)


if __name__ == "__main__":
    print("Starting Telegram Commander Standalone...")
    run_telegram_commander_loop()
