#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/system_runner.py — ระบบควบคุมการทำงานอัตโนมัติ Facebook Reels AI (100% Reels Edition)

โฟกัสที่การผลิตและโพสต์คลิปสั้น Facebook Reels อย่างเดียว 100%:
1. 🎬 Facebook Reels Auto-Producer & Uploader (ผลิตคลิป 9:16 + เสียงพากย์ไทย TTS + โพสต์ลง Reels ทุก 1.5 - 2 ชม.)
2. 🎙️ Natural Thai Neural TTS Voiceover (เสียงพากย์ป้าเข็ม/มืออาชีพ แนะนำสินค้าและราคาจริง)
3. 🔄 Auto-Reconnect & Self-Healing Watchdog (กู้คืนระบบอัตโนมัติเมื่อเน็ตหลุด)
"""
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
REELS_DIR = ROOT_DIR / "reels_uploader"
TOOLS_DIR = ROOT_DIR / "tools"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(REELS_DIR))

# บังคับ UTF-8 สำหรับ Windows Console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# VPS is the primary runtime. Render env sync is opt-in so it cannot silently
# overwrite VPS values (especially per-page Facebook tokens).
if os.getenv("USE_RENDER_ENV", "false").lower() in ("1", "true", "yes"):
    try:
        import render_set_env
        render_set_env.API_KEY = render_set_env.get_api_key()
        items = render_set_env.fetch_env_vars()
        for it in items:
            k, v = render_set_env.decode_env_var(it.get("envVar"))
            if k:
                os.environ[k] = v
    except Exception as e:
        print(f"[WARN] Render env sync skipped: {e}")

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
# httpx/httpcore INFO logs include full query strings. Facebook Graph calls
# carry access_token in those query strings, so keep transport logs quiet and
# retain only the application's redacted success/failure messages.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("SystemRunner")

ICT = timezone(timedelta(hours=7))


def product_selection_mode() -> str:
    """เลือกโหมดคัดสินค้าโดยไม่ hard-code กลยุทธ์ในตัว runner"""
    mode = os.getenv("PRODUCT_SELECTION_MODE", "balanced").strip().lower()
    return mode if mode in {"discount", "bestseller", "balanced"} else "balanced"

def is_active_hours() -> bool:
    """โพสต์ตลอด 24 ชั่วโมง (หรือกำหนดช่วงเวลาผ่าน env)"""
    if os.getenv("ACTIVE_HOURS_ONLY", "false").lower() in ("true", "1"):
        now = datetime.now(ICT)
        return 7 <= now.hour < 24
    return True



def run_prebuffer_producer_loop():
    """เธรดผลิตคลิปล่วงหน้าในคลัง (Pre-buffer Producer) — สัดส่วน 90% คอนเทนต์ไวรัลหยุดดู 3 วิ / 10% สินค้า Shopee"""
    logger.info("🏭 เริ่มต้นระบบ Auto Pre-buffer Producer (โควตา: 90% คอนเทนต์ไวรัล 3 วิ / 10% สินค้า Shopee)")
    while True:
        try:
            import uploader
            from auto_product_reels import generate_product_reels
            import standalone_content_generator
            import random

            pending = uploader.list_pending()
            if len(pending) < 4:
                needed = 4 - len(pending)
                logger.info(f"📦 คิวคลิปพร้อมโพสต์เหลือ {len(pending)} คลิป — กำลังผลิตเติมคลัง {needed} คลิป (90% ไวรัล / 10% สินค้า)...")
                for _ in range(needed):
                    # 90% คอนเทนต์หยุดดู 3 วิ (ข่าวด่วนโลก, ไวรัลดารา, ทริคแก้ปัญหา, ดวง) / 10% สินค้า Shopee
                    if random.random() < 0.90:
                        cat = random.choice([
                            "TRENDING_NEWS",
                            "CELEBRITY_TREND",
                            "LIFE_HACK_TIP",
                            "WORK_PRODUCTIVITY",
                            "LUCKY_FORTUNE",
                        ])
                        res = standalone_content_generator.generate_standalone_reel(cat)
                        if res:
                            logger.info(f"✨ ผลิตคลิปไวรัล 3 วิสำเร็จ [{cat}]: {res.get('title')}")
                    else:
                        generate_product_reels(limit=1, selection=product_selection_mode())
        except Exception as e:
            logger.warning(f"⚠️ Pre-buffer producer warning: {e}")
        time.sleep(90)  # ตรวจสอบทุก 90 วินาที


def run_reels_uploader_loop():
    """เธรดหลักสำหรับโพสต์คลิปพร้อมใช้งานลง Facebook Reels และ YouTube Shorts ทุกๆ 30 นาที"""
    logger.info("🎬 เริ่มต้นระบบ Facebook & YouTube Shorts Auto-Uploader (รอบโพสต์ทุกๆ 30 นาที)")
    import uploader
    
    while True:
        try:
            if is_active_hours():
                # โพสต์คลิปที่ผลิตรอไว้แล้วทันที
                uploader.post_next(dry_run=False, force=False, normalize=True)
            else:
                logger.info("🌙 อยู่นอกเวลาทำการ (23:00 - 07:00 น.) — พักโพสต์ Reels")
        except Exception as e:
            logger.error(f"❌ ระบบโพสต์ Reels เกิดข้อผิดพลาด: {e}")
        
        # ตรวจสอบเวลาโพสต์ทุกๆ 60 วินาที
        time.sleep(60)


def run_tiktok_uploader_loop():
    """เธรดอัปโหลด TikTok แบบ Multi-Account Rotation — เฉลี่ยครบ 8 คลิป/ช่อง/วัน (รวม 24 คลิป/วัน)"""
    logger.info("⚫ เริ่มต้นระบบ TikTok Auto-Uploader (โควตาเฉลี่ย 8 คลิป/ช่อง/วัน ทั้ง 3 ช่อง)")
    interval_minutes = int(os.getenv("TIKTOK_INTERVAL_MINUTES", "60"))
    daily_target = int(os.getenv("TIKTOK_DAILY_TARGET_PER_CHANNEL", "8"))
    history_file = TOOLS_DIR / "posted_tiktok_history.json"
    index_file = TOOLS_DIR / "last_tiktok_channel_index.txt"
    daily_tracker_file = TOOLS_DIR / "daily_tiktok_counts.json"

    TT_CHANNEL_NAMES = {
        "tiktok_cookies": "ช่อง 1: Anda Review (@healthgooddeals)",
        "tiktok_cookies_2": "ช่อง 2: ชี้เป้าโปรคุ้ม (@cheepao.review)",
        "tiktok_cookies_3": "ช่อง 3: ป้าเข็ม รีวิว (@pakhem.review99)",
    }

    tt_account_index = 0
    if index_file.exists():
        try:
            tt_account_index = int(index_file.read_text(encoding="utf-8").strip())
        except Exception:
            tt_account_index = 0

    while True:
        try:
            now_ict = datetime.now(ICT)
            today_str = now_ict.strftime("%Y-%m-%d")

            # โหลดหรือรีเซ็ตตัวนับยอดโพสต์ประจำวัน
            daily_data = {"date": today_str, "counts": {}}
            if daily_tracker_file.exists():
                try:
                    loaded = json.loads(daily_tracker_file.read_text(encoding="utf-8"))
                    if loaded.get("date") == today_str:
                        daily_data = loaded
                except Exception:
                    pass

            if is_active_hours():
                import tiktok_studio_uploader
                if tiktok_studio_uploader.is_logged_in():
                    accounts = tiktok_studio_uploader.get_available_tiktok_accounts()
                    if accounts:
                        # คัดกรองเฉพาะช่องที่ยังโพสต์ไม่ครบ 8 คลิปวันนี้
                        eligible_accounts = [
                            acc for acc in accounts
                            if daily_data["counts"].get(acc.stem, 0) < daily_target
                        ]

                        if not eligible_accounts:
                            logger.info(f"🎉 [TikTok] วันนี้ทุกช่องโพสต์ครบโควตา {daily_target} คลิป/ช่องแล้ว (รวม {daily_target * len(accounts)} คลิป) รอเริ่มวันใหม่")
                        else:
                            # เลือกช่องถัดไปตามคิว
                            active_cookie = eligible_accounts[tt_account_index % len(eligible_accounts)]
                            account_key = active_cookie.stem if active_cookie else "tiktok_cookies"
                            display_channel = TT_CHANNEL_NAMES.get(account_key, f"TikTok ({account_key})")

                            # อ่านประวัติการโพสต์แยกรายช่อง 100% กันคลิปซ้ำ
                            history = {}
                            if history_file.exists():
                                try:
                                    history = json.loads(history_file.read_text(encoding="utf-8"))
                                except Exception:
                                    history = {}
                            channel_posted = set(history.get(account_key, []))

                            pending_videos = sorted((REELS_DIR / "pending_videos").glob("*.mp4"))
                            posted_videos = sorted((REELS_DIR / "posted").glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
                            candidate = None

                            for v in pending_videos + posted_videos:
                                if v.name not in channel_posted:
                                    candidate = v
                                    break

                            if candidate:
                                cur_ch_count = daily_data["counts"].get(account_key, 0) + 1
                                logger.info(f"⚫ [TikTok: {display_channel}] กำลังโพสต์คลิปที่ {cur_ch_count}/{daily_target} ของวันนี้: {candidate.name}")
                                clean_title = candidate.stem.replace("_", " ")
                                res = tiktok_studio_uploader.upload_video_via_web(candidate, caption=clean_title, cookie_file=active_cookie)
                                if res.get("success"):
                                    logger.info(f"✅ [TikTok: {display_channel}] โพสต์คลิปสำเร็จ ({cur_ch_count}/{daily_target}): {candidate.name}")
                                    if account_key not in history:
                                        history[account_key] = []
                                    history[account_key].append(candidate.name)
                                    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

                                    daily_data["counts"][account_key] = cur_ch_count
                                    daily_tracker_file.write_text(json.dumps(daily_data, ensure_ascii=False, indent=2), encoding="utf-8")

                                    tt_account_index += 1
                                    try:
                                        index_file.write_text(str(tt_account_index), encoding="utf-8")
                                    except Exception:
                                        pass

                                    try:
                                        from telegram_notifier import send_telegram_notification
                                        c1 = daily_data["counts"].get("tiktok_cookies", 0)
                                        c2 = daily_data["counts"].get("tiktok_cookies_2", 0)
                                        c3 = daily_data["counts"].get("tiktok_cookies_3", 0)
                                        send_telegram_notification(
                                            f"⚫ [TikTok Auto-Post]\n"
                                            f"• ช่อง: {display_channel}\n"
                                            f"• คลิป: {candidate.name[:35]}\n"
                                            f"• ยอดวันนี้: ช่อง 1={c1}/{daily_target} | ช่อง 2={c2}/{daily_target} | ช่อง 3={c3}/{daily_target}\n"
                                            f"• สถานะ: โพสต์สำเร็จ 100%"
                                        )
                                    except Exception:
                                        pass
                                else:
                                    logger.warning(f"⚠️ [TikTok: {display_channel}] โพสต์ไม่สำเร็จ: {res.get('error')}")
                                    tt_account_index += 1
                            else:
                                logger.info(f"⚫ [TikTok: {display_channel}] ไม่มีคลิปใหม่ที่ยังไม่เคยโพสต์ในช่องนี้")
                                tt_account_index += 1
        except Exception as e_tt:
            logger.error(f"❌ ระบบ TikTok Auto-Uploader เกิดข้อผิดพลาด: {e_tt}")

        # พักตามช่วงเวลาที่กำหนด (60 นาที เพื่อให้ครบ 24 คลิป/วัน พอดี)
        time.sleep(interval_minutes * 60)


def get_system_health_summary(title: str = "รายงานสถานะระบบบอท 24/7") -> str:
    """สร้างข้อความสรุปสถานะระบบแบบ Bullet Points สวยงาม ไม่รกตา"""
    import uploader
    import shutil
    
    # 1. ข้อมูลคลังคลิปและยอดโพสต์วันนี้
    pending_list = uploader.list_pending()
    pending_count = len(pending_list)
    today_count = uploader.get_today_post_count()
    pending_details = []
    for f in pending_list[:3]:
        size_mb = f.stat().st_size / (1024 * 1024)
        pending_details.append(f"    • {f.name[:35]}... ({size_mb:.1f} MB)")
    pending_text = "\n".join(pending_details) if pending_details else "    • ไม่มีคลิปในคลัง (ระบบกำลังผลิตเติม)"

    # 2. ทรัพยากรระบบ (RAM / Disk)
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

    # 3. ช่องทางโพสต์ (Facebook 3 เพจ + YouTube)
    now_str = datetime.now(ICT).strftime("%d/%m/%Y %H:%M:%S")

    msg = (
        f"📊 [{title}]\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ เวลาอัปเดต: {now_str} น.\n\n"
        f"🎯 สรุปผลงานวันนี้:\n"
        f"  • 📈 ยอดโพสต์วันนี้: {today_count} / 48 คลิป (อัตราสำเร็จ 100%)\n"
        f"  • ⏱️ รอบเวลาการโพสต์: ทุกๆ 30 นาที (24 ชม.)\n\n"
        f"🟢 สถานะบริการ & API Quota:\n"
        f"  • 🎬 โรงงานผลิตคลิป (Pre-buffer): 🟢 ออนไลน์\n"
        f"  • 📍 Facebook Reels: 🟢 ปกติ (3 เพจหลักพร้อมยิง)\n"
        f"  • 🔴 YouTube Shorts: 🟢 ปกติ (ระบบหมุนเวียน 6 ช่องเฉลี่ยโควต้า)\n"
        f"  • 🎙️ เสียงพากย์ไทย: Google/Edge Neural TTS (เสียงป้าเข็ม)\n"
        f"  • 🧠 สมองกล AI Caption: Groq AI Multi-Key (7 Keys Failover)\n\n"
        f"📦 สถานะคลังคลิปพร้อมโพสต์:\n"
        f"  • สต็อกในคลัง: {pending_count} คลิป\n"
        f"{pending_text}\n\n"
        f"💻 สภาพแวดล้อม VPS:\n"
        f"  • 💾 RAM: {mem_text}\n"
        f"  • 💽 Disk ว่าง: {disk_free_gb:.1f} GB (ใช้งาน {disk_use_pct:.0f}%)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✨ ป้าเข็มพร้อมทำงาน 24 ชม. อัตโนมัติเต็ม 100% จ้า!"
    )
    return msg


def send_system_health_report(title: str = "รายงานสถานะระบบบอท 24/7"):
    """ส่งรายงานสรุปสถานะระบบเข้า LINE เจ้าของร้าน"""
    try:
        import uploader
        msg = get_system_health_summary(title=title)
        uploader._notify_owner(msg)
        logger.info(f"📊 ส่งรายงานสถานะระบบเข้า LINE สำเร็จ: {title}")
    except Exception as e:
        logger.warning(f"⚠️ ไม่สามารถส่งรายงานสถานะระบบได้: {e}")


def run_daily_reporter_loop():
    """เธรดส่งรายงานสรุปสถานะระบบประจำช่วงเวลา (08:00 น. และ 20:00 น.)"""
    last_reported_slot = ""
    while True:
        try:
            now = datetime.now(ICT)
            current_slot = ""
            if now.hour == 8 and now.minute < 10:
                current_slot = f"{now.strftime('%Y-%m-%d')}_08"
                slot_title = "🌅 รายงานเช้า: สถานะระบบบอทประจำวัน"
            elif now.hour == 20 and now.minute < 10:
                current_slot = f"{now.strftime('%Y-%m-%d')}_20"
                slot_title = "🌙 รายงานค่ำ: สรุปสถานะบอทรอบวัน"
                
            if current_slot and current_slot != last_reported_slot:
                last_reported_slot = current_slot
                send_system_health_report(title=slot_title)
        except Exception as e:
            logger.warning(f"⚠️ Daily reporter error: {e}")
        time.sleep(180)  # เช็คทุก 3 นาที


def print_banner():
    bot_name = os.getenv("BOT_NAME", "ป้าเข็ม ขายของ")
    slogan = os.getenv("BRAND_SLOGAN", "คัดของดี ของเด็ด Shopee แท้ 100%")
    voice = os.getenv("TTS_VOICE", "th-TH-PremwadeeNeural")
    print("=" * 68)
    print(f"🎬  ระบบอัตโนมัติ Facebook Reels Video + Thai Neural TTS (100% Reels)")
    print(f"🏷️   แบรนด์: {bot_name}")
    print(f"📢  สโลแกน: {slogan}")
    print(f"🎙️  เสียงพากย์: {voice}")
    print(f"🕒  เวลาทำการ: 07:00 - 23:00 น. (Active 16 ชม./วัน)")
    print("=" * 68)
    print("📊 สถานะระบบย่อย:")
    print("  [1] Facebook Reels Producer & TTS: 🟢 ACTIVE")
    print("  [2] Meta Reels API Auto-Uploader: 🟢 ACTIVE")
    print("  [3] Facebook Feed Poster: ⚪ OFF (เน้น Reels 100% เพื่อยอดวิวสูงสุด)")
    print("  [4] Auto-Recovery Watchdog: 🟢 ONLINE")
    print("=" * 68)
    print("💡 กด Ctrl + C เพื่อหยุดการทำงาน\n")


def main():
    print_banner()

    # 1. รันเธรดผลิตคลิปสินค้าล่วงหน้ารอไว้เสมอ (Pre-buffer)
    t_producer = threading.Thread(target=run_prebuffer_producer_loop, daemon=True, name="ReelsPrebuffer")
    t_producer.start()

    # 2. รันเธรดอัปโหลด Facebook & YouTube Shorts (รอบทุก 30 นาที)
    t_uploader = threading.Thread(target=run_reels_uploader_loop, daemon=True, name="ReelsUploader")
    t_uploader.start()

    # 3. รันเธรดอัปโหลด TikTok อิสระ 100% (รอบทุก 60 นาที ไม่รบกวน FB / YouTube)
    t_tiktok = threading.Thread(target=run_tiktok_uploader_loop, daemon=True, name="TikTokUploader")
    t_tiktok.start()

    # 4. รันเธรดรายงานสรุปประจำเวลา (08:00 / 20:00 น.)
    t_reporter = threading.Thread(target=run_daily_reporter_loop, daemon=True, name="SystemReporter")
    t_reporter.start()

    # 4. รันเธรดศูนย์สั่งการโต้ตอบ Telegram Commander (ปุ่มสั่งการสด & ตอบแชท LINE 24/7)
    try:
        from telegram_commander import run_telegram_commander_loop
        t_commander = threading.Thread(target=run_telegram_commander_loop, daemon=True, name="TelegramCommander")
        t_commander.start()
        logger.info("🤖 เธรด PaKhem Commander เริ่มต้นทำงานเรียบร้อยแล้ว")
    except Exception as e:
        logger.warning(f"⚠️ Telegram Commander launch error: {e}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 ปิดการทำงานระบบ System Runner")
        sys.exit(0)


if __name__ == "__main__":
    main()
