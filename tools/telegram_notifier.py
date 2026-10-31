#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/telegram_notifier.py — Telegram Bot Notifier for PaKhem Commander (Free 24/7 Unlimited)"""

import json
import logging
import os
import urllib.request
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

# โหลด .env จาก backend เสมอ (override=True เพื่อป้องกัน env เก่าค้างในระบบ)
load_dotenv(BACKEND / ".env", override=True)

logger = logging.getLogger("TelegramNotifier")

DEFAULT_BOT_TOKEN = "8939151149:AAGrVkCv0xZrlvtRPO8mzelOYsp5ah5M13U"
DEFAULT_CHAT_ID = "6734965582"

_env_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
if not _env_token or _env_token.startswith("8648538339"):
    _env_token = DEFAULT_BOT_TOKEN
    os.environ["TELEGRAM_BOT_TOKEN"] = DEFAULT_BOT_TOKEN

TELEGRAM_BOT_TOKEN = _env_token
TELEGRAM_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID") or DEFAULT_CHAT_ID).strip()


import time
import threading
import hashlib
import urllib.error

# Global Thread-safe Rate Limiter & Cooldown Engine
_tg_lock = threading.Lock()
_last_sent_ts: float = 0.0
_backoff_until: float = 0.0
_dedup_cache: dict = {}  # sig -> timestamp

# Configuration: Minimum seconds between Telegram API calls
MIN_INTERVAL_SECONDS = float(os.getenv("TELEGRAM_MIN_INTERVAL_SECONDS", "3.0"))


def _clean_text_signature(text: str) -> str:
    """สร้าง signature สำหรับตรวจสอบข้อความซ้ำ โดยตัดตัวแปรเวลาออก"""
    import re
    # ตัดวันที่ เวลา timestamp ออกเพื่อจับคู่ข้อความประเภทเดียวกัน
    sig = re.sub(r'\d{1,2}/\d{1,2}/\d{4}|\d{1,2}:\d{1,2}:\d{1,2}|\b\d{10}\b', '', text[:200])
    return hashlib.md5(sig.encode("utf-8")).hexdigest()


def send_telegram_alert(
    text: str,
    parse_mode: str = None,
    throttle_key: str = None,
    cooldown_seconds: int = 0,
    force: bool = False
) -> bool:
    """ส่งข้อความแจ้งเตือนเข้า Telegram แอดมิน (พร้อม Smart Rate Limiter & Deduplication ป้องกันติดลิมิต 100%)"""
    global _last_sent_ts, _backoff_until, _dedup_cache

    # Guard 1: ห้ามส่งข้อความจาก Unit Test / Mock Data
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"):
        return True
    if "U_cust_" in text or "U_mock" in text or "test_user" in text:
        return True

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN or DEFAULT_BOT_TOKEN).strip()
    if token.startswith("8648538339"):
        token = DEFAULT_BOT_TOKEN
    chat_id = str(os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID or DEFAULT_CHAT_ID).strip()

    if not token or not chat_id or "mock" in token.lower():
        return False

    now = time.time()

    with _tg_lock:
        # Guard 2: ตรวจสอบสถานะ HTTP 429 Backoff
        if now < _backoff_until:
            wait_left = int(_backoff_until - now)
            logger.warning(f"[TELEGRAM] อยู่ในสถานะระงับชั่วคราว (Rate Limit Backoff): เหลืออีก {wait_left} วินาที — ข้ามข้อความ")
            return False

        # Guard 3: Deduplication & Cooldown Throttle
        sig = throttle_key or _clean_text_signature(text)
        eff_cooldown = cooldown_seconds if cooldown_seconds > 0 else int(os.getenv("TELEGRAM_DEDUP_COOLDOWN_SECONDS", "300"))
        
        last_time = _dedup_cache.get(sig, 0.0)
        if not force and (now - last_time) < eff_cooldown:
            logger.info(f"[TELEGRAM-THROTTLE] ข้ามข้อความซ้ำ (Cooldown เหลืออีก {int(eff_cooldown - (now - last_time))} วิ)")
            return True

        # Guard 4: Anti-Flood Interval (เว้นระยะห่างขั้นต่ำ MIN_INTERVAL_SECONDS)
        elapsed = now - _last_sent_ts
        if elapsed < MIN_INTERVAL_SECONDS:
            sleep_needed = MIN_INTERVAL_SECONDS - elapsed
            time.sleep(sleep_needed)
            now = time.time()

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload_dict = {
            "chat_id": chat_id,
            "text": text[:4000],
            "disable_web_page_preview": True
        }
        if parse_mode:
            payload_dict["parse_mode"] = parse_mode

        try:
            data = json.dumps(payload_dict).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    _last_sent_ts = time.time()
                    _dedup_cache[sig] = _last_sent_ts
                    # ทำความสะอาดแคชเก่าเกิน 1 ชั่วโมง
                    if len(_dedup_cache) > 200:
                        cutoff = _last_sent_ts - 3600
                        _dedup_cache = {k: v for k, v in _dedup_cache.items() if v > cutoff}
                    logger.info("[TELEGRAM] ส่งข้อความสำเร็จ")
                    
                    # หากเป็นข้อความเกี่ยวกับออเดอร์ หรือ สลิปเงินโอน ให้ยิงแจ้งเตือนเข้า LINE ส่วนตัวแอดมินทันที
                    is_order_event = any(k in text for k in ["ออเดอร์", "สลิป", "โอนเงิน", "ทิ้งเบอร์", "ที่อยู่จัดส่ง", "สร้างออเดอร์"])
                    if is_order_event:
                        try:
                            send_admin_line_notification(text)
                        except Exception:
                            pass

                    return True
        except urllib.error.HTTPError as he:
            if he.code == 429:
                retry_after = 60
                try:
                    err_body = json.loads(he.read().decode("utf-8"))
                    retry_after = int(err_body.get("parameters", {}).get("retry_after", 60))
                except Exception:
                    pass
                _backoff_until = time.time() + retry_after
                logger.error(f"🚨 [TELEGRAM RATE LIMIT] ติดลิมิต 429! สั่ง Backoff หยุดยิงข้อความชั่วคราว {retry_after} วินาที")
            else:
                logger.warning(f"[TELEGRAM] ส่งข้อความล้มเหลว HTTP {he.code}: {he.reason}")
            return False
        except Exception as e:
            logger.warning(f"[TELEGRAM] ส่งข้อความล้มเหลว: {e}")
            return False

    return False


send_telegram_notification = send_telegram_alert


def send_telegram_video(video_path: str | Path, caption: str = "") -> bool:
    """ส่งไฟล์วิดีโอ .mp4 เข้า Telegram แอดมิน (ปิดการทำงานอัตโนมัติเพื่อไม่ให้ติดลิมิต ยกเว้นเปิด TELEGRAM_SEND_VIDEO=true)"""
    send_enabled = os.getenv("TELEGRAM_SEND_VIDEO", "false").lower() in ("true", "1", "yes")
    if not send_enabled:
        logger.info("[TELEGRAM] ปิดการอัปโหลดวิดีโอ MP4 อัตโนมัติ (ประหยัดแบนด์วิดท์ & ป้องกันติดลิมิต)")
        return True

    v_p = Path(video_path)
    if not v_p.exists() or v_p.stat().st_size == 0:
        return False
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN or DEFAULT_BOT_TOKEN).strip()
    if token.startswith("8648538339"):
        token = DEFAULT_BOT_TOKEN
    chat_id = str(os.getenv("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID or DEFAULT_CHAT_ID).strip()
    if not token or not chat_id or "mock" in token.lower():
        return False
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    try:
        import httpx
        with open(v_p, "rb") as f:
            files = {"video": (v_p.name, f, "video/mp4")}
            data = {"chat_id": chat_id, "caption": caption[:1024]}
            r = httpx.post(url, data=data, files=files, timeout=60.0)
            if r.status_code == 200:
                logger.info(f"[TELEGRAM] ส่งวิดีโอสำเร็จ: {v_p.name}")
                return True
            else:
                logger.warning(f"[TELEGRAM] ส่งวิดีโอล้มเหลว HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[TELEGRAM] ส่งวิดีโอล้มเหลว: {e}")
    return False



def send_admin_line_notification(text: str) -> bool:
    """ส่งข้อความแจ้งเตือนออเดอร์เข้า LINE ส่วนตัวแอดมิน (นายจีรวัฒน์)"""
    token = (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()
    uid = (os.getenv("ADMIN_LINE_UID") or "Uc88eb3896b0e4bcc5fbaa9b78ac1294e").strip()
    if not token or not uid:
        return False
    try:
        url = "https://api.line.me/v2/bot/message/push"
        payload = {
            "to": uid,
            "messages": [{"type": "text", "text": text[:5000]}]
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info("[LINE-ADMIN-PUSH] ส่งข้อความเข้า LINE แอดมินสำเร็จ")
                return True
    except Exception as e:
        logger.warning(f"[LINE-ADMIN-PUSH] ส่งข้อความล้มเหลว: {e}")
    return False


if __name__ == "__main__":
    test_msg = (
        "🚀 [PaKhem Commander — ทดสอบระบบแจ้งเตือน]\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ เชื่อมต่อสำเร็จ 100% พร้อมรายงานผลการโพสต์ 24/7 ครับ!\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    ok = send_telegram_alert(test_msg)
    print("Telegram Notification Status:", "SUCCESS" if ok else "FAILED")
