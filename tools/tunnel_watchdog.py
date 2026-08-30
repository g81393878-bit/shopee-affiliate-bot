#!/usr/bin/env python3
"""
tunnel_watchdog.py — Standalone Cloudflare Tunnel URL watchdog
รันเป็น systemd service แยกต่างหาก ตรวจทุก 15 วินาที
เมื่อ tunnel URL เปลี่ยน -> อัปเดต LINE Webhook ทันที + แจ้ง Telegram
"""
import subprocess
import re
import urllib.request
import json
import time
import os
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TunnelWatchdog")

LINE_TOKEN = "4FYHfbu8+iE7CaOo+lCEG6pBZuxiOIPXlgKQ3tQSQIxZZOpX63qY/Xp8W+1GGftkB9VXpmb88HtHVmr8BAv5qKmDYgNnaVi322Jj9Bc2g6o3ePUa/R5mX8a+u8HyE7c8g8hLAi20pgHIrnYTV9u9MgdB04t89/1O/w1cDnyilFU="
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = "6734965582"
URL_CACHE_FILE = "/tmp/tunnel_url.txt"
CHECK_INTERVAL = 15  # วินาที

_last_url = None


def get_tunnel_url():
    """ดึง URL ปัจจุบันจาก cloudflared journal — อ่านเยอะพอให้เจอ URL"""
    try:
        # อ่าน 500 บรรทัดสุดท้าย เพื่อให้แน่ใจว่าเจอ URL
        res = subprocess.run(
            ["journalctl", "-u", "cloudflared-tunnel", "-n", "500", "--no-pager", "--output=cat"],
            capture_output=True, text=True, timeout=10
        )
        urls = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", res.stdout or "")
        return urls[-1] if urls else None
    except Exception as e:
        logger.warning(f"Cannot read journal: {e}")
        return None


def update_line_webhook(url):
    """อัปเดต LINE Webhook endpoint"""
    endpoint = f"{url}/api/webhooks/line"
    try:
        payload = json.dumps({"endpoint": endpoint}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.line.me/v2/bot/channel/webhook/endpoint",
            data=payload, method="PUT",
            headers={"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"LINE Webhook update failed: {e}")
        return False


def notify_telegram(msg):
    """แจ้งเตือน Telegram"""
    if not TELEGRAM_BOT_TOKEN or "mock" in TELEGRAM_BOT_TOKEN.lower():
        return
    try:
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "disable_web_page_preview": True
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def main():
    global _last_url

    # โหลด URL เดิมจาก cache (กรณี restart watchdog)
    if os.path.exists(URL_CACHE_FILE):
        try:
            _last_url = open(URL_CACHE_FILE).read().strip()
            logger.info(f"Loaded cached tunnel URL: {_last_url}")
        except Exception:
            pass

    logger.info("🔍 Tunnel Watchdog started — checking every 15 seconds...")

    while True:
        try:
            current_url = get_tunnel_url()

            if current_url and current_url != _last_url:
                logger.info(f"🔄 Tunnel URL changed: {current_url}")

                # อัปเดต LINE Webhook
                if update_line_webhook(current_url):
                    _last_url = current_url
                    # บันทึก URL ใหม่
                    with open(URL_CACHE_FILE, "w") as f:
                        f.write(current_url)
                    logger.info(f"✅ LINE Webhook updated to: {current_url}/api/webhooks/line")
                    # แจ้ง Telegram
                    notify_telegram(
                        f"🔄 [Tunnel URL เปลี่ยนแล้ว]\n"
                        f"• URL ใหม่: {current_url}\n"
                        f"• LINE Webhook อัปเดตอัตโนมัติแล้ว ✅\n"
                        f"• บอทพร้อมรับข้อความลูกค้าแล้วครับ"
                    )
                else:
                    logger.error("❌ Failed to update LINE Webhook")

        except Exception as e:
            logger.error(f"Watchdog error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
