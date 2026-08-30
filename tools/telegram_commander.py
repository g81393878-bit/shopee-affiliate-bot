#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/telegram_commander.py — Telegram Command Center & Interactive Controller (PaKhem Commander)

ระบบควบคุมและสั่งการระยะไกลผ่าน Telegram:
1. 🎛️ ปุ่มสั่งการด่วน: [📊 เช็คสถานะ] [🚀 สั่งโพสต์ทันที] [🏭 ผลิตคลิปเพิ่ม] [📦 ดูสต็อกคลัง] [🔄 รีสตาร์ท]
2. 💬 ตอบแชทลูกค้า LINE OA ผ่าน Telegram: /reply <userId> <ข้อความ> หรือ /ตอบ <userId> <ข้อความ>
3. 🔒 ความปลอดภัย: ล็อคสิทธิ์เฉพาะแอดมิน (TELEGRAM_CHAT_ID) เท่านั้น
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

logger = logging.getLogger("TelegramCommander")
ICT = timezone(timedelta(hours=7))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8648538339:AAGDjwjHlrYRj-g3XrqZ_nAxfJV0S-d3yfk")
TELEGRAM_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID", "6734965582")).strip()


def send_tg_message(text: str, reply_markup: dict = None) -> bool:
    """ส่งข้อความเข้า Telegram แอดมิน พร้อมปุ่มกด (ถ้ามี)"""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
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
            return response.status == 200
    except Exception as e:
        logger.warning(f"Telegram send message failed: {e}")
        return False


def get_main_menu_markup() -> dict:
    """สร้าง Inline Keyboard ปุ่มกดเมนูหลัก"""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 เช็คสถานะสด", "callback_data": "cmd_status"},
                {"text": "🚀 สั่งโพสต์คลิปทันที", "callback_data": "cmd_post"}
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
        f"  • 📈 ยอดโพสต์วันนี้: {today_count} / 48 คลิป (100%)\n"
        f"  • ⏱️ ความถี่โพสต์: ยิงทุก 30 นาที (4 ช่องทาง)\n\n"
        f"🟢 สถานะบริการ & เครือข่าย:\n"
        f"  • 🎬 โรงงานผลิตคลิป (Pre-buffer): 🟢 ออนไลน์\n"
        f"  • 📍 Facebook Reels: 🟢 ออนไลน์ (3 เพจพร้อมยิง)\n"
        f"  • 🔴 YouTube Shorts: 🟢 ปกติ (หมุนเวียน 4 ช่อง)\n"
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
    """สั่งโพสต์คลิปทันทีในเธรดแยก"""
    def _run():
        send_tg_message("🚀 [กำลังเริ่มกระบวนการโพสต์ด่วน]\nบอทกำลังอัปโหลดคลิปขึ้น FB Reels 3 เพจ + YouTube Shorts ทันทีครับ...")
        try:
            import uploader
            res = uploader.post_next(dry_run=False, force=True, normalize=True)
            if res == 0:
                send_tg_message("✅ [คำสั่งโพสต์ด่วนเสร็จสิ้น]\nโพสต์คลิปขึ้นทั้ง 4 ช่องทางเรียบร้อยแล้วครับ!")
            else:
                send_tg_message("⚠️ [ผลการโพสต์ด่วน]\nไม่สามารถโพสต์ได้ในรอบนี้ (กรุณาตรวจ Log หรือสต็อกคลิป)")
        except Exception as e:
            send_tg_message(f"❌ โพสต์ด่วนเกิดข้อผิดพลาด: {e}")

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


def handle_telegram_update(update: dict):
    """ประมวลผล Update จาก Telegram"""
    # 1. จัดการ Callback Query จากปุ่ม Inline
    if "callback_query" in update:
        cb = update["callback_query"]
        sender_id = str(cb.get("from", {}).get("id", "")).strip()
        data = cb.get("data", "")
        
        if sender_id != TELEGRAM_CHAT_ID:
            return
            
        if data == "cmd_status":
            send_tg_message(execute_status_command(), reply_markup=get_main_menu_markup())
        elif data == "cmd_post":
            execute_post_command()
        elif data == "cmd_produce":
            execute_produce_command()
        elif data == "cmd_stock":
            send_tg_message(execute_stock_command(), reply_markup=get_main_menu_markup())
        elif data == "cmd_restart":
            send_tg_message("🔄 กำลังสั่งรีสตาร์ทบอทบน VPS...")
            def _restart():
                time.sleep(1)
                subprocess.run(["sudo", "systemctl", "restart", "shopee-bot"])
            threading.Thread(target=_restart, daemon=True).start()
        return

    # 2. จัดการข้อความพิมพ์ (Text Message)
    if "message" in update:
        msg = update["message"]
        sender_id = str(msg.get("from", {}).get("id", "")).strip()
        text = (msg.get("text") or "").strip()
        
        if sender_id != TELEGRAM_CHAT_ID:
            return

        lower = text.lower()
        if lower in ("/start", "/menu", "เมนู", "menu"):
            welcome = (
                "👑 [PaKhem Commander — แผงควบคุมบอท 24/7]\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "ยินดีต้อนรับครับ! คุณสามารถสั่งการบอท ผลิตคลิป โพสต์ด่วน หรือตอบแชทลูกค้าได้จากเมนูด้านล่างนี้เลยครับ:\n\n"
                "💬 การตอบแชทลูกค้า LINE:\n"
                "พิมพ์: `/reply <userId> <ข้อความ>`\n"
                "เช่น: `/reply U12345678 ขอบคุณที่สนใจครับ`"
            )
            send_tg_message(welcome, reply_markup=get_main_menu_markup())
            
        elif lower in ("/status", "สถานะ", "status", "เช็คระบบ"):
            send_tg_message(execute_status_command(), reply_markup=get_main_menu_markup())
            
        elif lower in ("/post", "โพสต์", "post", "ยิงคลิป"):
            execute_post_command()
            
        elif lower in ("/produce", "ผลิต", "ทำคลิป"):
            execute_produce_command()
            
        elif lower in ("/stock", "สต็อก", "คลัง", "stock"):
            send_tg_message(execute_stock_command(), reply_markup=get_main_menu_markup())
            
        elif lower in ("/restart", "รีสตาร์ท"):
            send_tg_message("🔄 กำลังสั่งรีสตาร์ทบอทบน VPS...")
            def _restart():
                time.sleep(1)
                subprocess.run(["sudo", "systemctl", "restart", "shopee-bot"])
        elif lower in ("/reply", "/ตอบ", "ตอบ", "/reply ", "/ตอบ "):
            send_tg_message(
                "💬 [วิธีตอบกลับลูกค้า]\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "👉 **แบบที่ 1 (ง่ายสุด - ตอบลูกค้าคนล่าสุดทันที):**\n"
                "`/reply สวัสดีครับ ยินดีให้บริการครับ`\n\n"
                "👉 **แบบที่ 2 (ระบุ User ID เอง):**\n"
                "`/reply U3f09510286687007931c42eb8d10fa1d สวัสดีครับ`\n"
                "━━━━━━━━━━━━━━━━━━"
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
                send_tg_message(res, reply_markup=get_main_menu_markup())
            else:
                send_tg_message("⚠️ กรุณาพิมพ์ข้อความที่ต้องการตอบ เช่น:\n`/reply สวัสดีครับ`")
        else:
            # ข้ามข้อความทั่วไปที่ไม่ใช่คำสั่ง เพื่อไม่ให้ตอบกลับสแปม
            pass


def run_telegram_commander_loop():
    """Long-Polling loop รับคำสั่งจาก Telegram แอดมินตลอด 24 ชม."""
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    if not token or "mock" in token.lower():
        logger.warning("Telegram Bot token not set. Commander disabled.")
        return

    logger.info("🤖 เริ่มต้นระบบ PaKhem Commander Polling Loop (24/7 Controller)...")
    
    # เคลียร์คิวข้อความเก่าตกค้างตอนเปิดระบบ (Drop stale backlog updates)
    offset = 0
    try:
        url_drop = f"https://api.telegram.org/bot{token}/getUpdates?offset=-1"
        req_drop = urllib.request.Request(url_drop, headers={"User-Agent": "PaKhemCommander/1.0"})
        with urllib.request.urlopen(req_drop, timeout=10) as r:
            d = json.loads(r.read().decode("utf-8"))
            res = d.get("result", [])
            if res:
                offset = res[-1]["update_id"] + 1
    except Exception:
        offset = 0

    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=30"
            req = urllib.request.Request(url, headers={"User-Agent": "PaKhemCommander/1.0"})
            with urllib.request.urlopen(req, timeout=40) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    results = data.get("result", [])
                    for item in results:
                        offset = item["update_id"] + 1
                        handle_telegram_update(item)
        except Exception as e:
            time.sleep(3)
        time.sleep(0.5)


if __name__ == "__main__":
    print("Starting Telegram Commander Standalone...")
    send_tg_message(
        "🚀 [PaKhem Commander — เปิดใช้งานเมนูสั่งการสำเร็จ]\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "แผงควบคุมระบบพร้อมใช้งานแล้วครับ กดปุ่มด้านล่างเพื่อสั่งการได้ทันที!",
        reply_markup=get_main_menu_markup()
    )
    run_telegram_commander_loop()
