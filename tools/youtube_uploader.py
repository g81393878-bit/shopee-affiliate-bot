#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/youtube_uploader.py — อัปโหลดคลิปวิดีโอ 9:16 ขึ้น YouTube Shorts (@regency1229) อัตโนมัติ

ความสามารถ:
1. ล็อคอินและจำลองสิทธิ์ผ่าน OAuth 2.0 (บันทึก token ไว้ใน tools/youtube_token.json)
2. อัปโหลดวิดีโอ 9:16 Full HD เข้าสู่ฟีด YouTube Shorts พร้อม #Shorts ใน Title
3. ใส่คำอธิบาย (Description) พร้อมลิงก์ Shopee Affiliate + ลิงก์ LINE OA ป้าเข็ม
4. ตั้งสถานะ Public (สาธารณะ) และ Category "People & Blogs" (22)
5. ป้องกันการโพสต์ซ้ำ และส่งแจ้งเตือนเข้า LINE เจ้าของร้าน
"""
import datetime
import json
import os
import pathlib
import re
import sys
import time
from typing import Dict, Optional, Union

# บังคับ UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
TOOLS_DIR = PROJECT_ROOT / "tools"
REELS_DIR = PROJECT_ROOT / "reels_uploader"
PENDING_DIR = REELS_DIR / "pending_videos"
POSTED_DIR = REELS_DIR / "posted"
PRODUCTS_JSON = REELS_DIR / "products.json"

sys.path.insert(0, str(BACKEND_DIR))
from app.services.product_price_policy import sanitize_public_product_text  # noqa: E402

CLIENT_SECRET_FILE = TOOLS_DIR / "client_secret.json"
TOKEN_FILE = TOOLS_DIR / "youtube_token.json"
YOUTUBE_LOG_FILE = TOOLS_DIR / "youtube_uploader.log"

# `youtube.upload` alone cannot create a top-level comment.  Keep the existing
# scopes and explicitly request the write scope used by commentThreads.insert.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

def log(msg: str):
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(YOUTUBE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def notify_telegram(message: str) -> None:
    """แจ้งผล YouTube เข้า Telegram โดยไม่ส่ง token/URL credential ออกไป"""
    try:
        from telegram_notifier import send_telegram_alert
        send_telegram_alert(message[:1500])
    except Exception as e:
        log(f"[WARN] แจ้ง Telegram ไม่สำเร็จ: {type(e).__name__}")


def get_token_files() -> list:
    """ค้นหาไฟล์ YouTube OAuth Token ทั้งหมดในโฟลเดอร์ tools/"""
    tokens = []
    # 1. Token ช่องหลัก
    if TOKEN_FILE.exists():
        tokens.append({"id": 1, "name": "ช่องหลัก (@regency1229)", "path": TOKEN_FILE})
    
    # 2. Token ช่องเสริม (youtube_token_2.json, youtube_token_3.json, ...)
    for f in sorted(TOOLS_DIR.glob("youtube_token_*.json")):
        m = re.search(r'youtube_token_(\d+)\.json$', f.name)
        cid = int(m.group(1)) if m else len(tokens) + 1
        tokens.append({"id": cid, "name": f"ช่องที่ {cid}", "path": f})
    return tokens


def get_authenticated_service(token_path: Optional[pathlib.Path] = None, channel_id: int = 1):
    """สร้างหรือโหลดเซสชัน YouTube API จาก OAuth token ของช่องที่ระบุ"""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    target_token_file = token_path or (TOOLS_DIR / f"youtube_token_{channel_id}.json" if channel_id > 1 else TOKEN_FILE)
    creds = None
    if target_token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(target_token_file), SCOPES)
            granted_scopes = set(getattr(creds, "scopes", None) or [])
            if not set(SCOPES).issubset(granted_scopes):
                # อย่าบังคับเปิดเบราว์เซอร์บน VPS: token เดิมยังอัปโหลดได้
                # ส่วนคอมเมนต์จะข้าม/แจ้งเตือนจนกว่าจะ reauthorize ผ่าน CLI
                log(f"[WARN] {target_token_file.name} ขาด OAuth scope สำหรับคอมเมนต์ — อัปโหลดได้ แต่คอมเมนต์ต้องยืนยัน OAuth ใหม่")
        except Exception as e:
            log(f"[WARN] โหลด token เก่าล้มเหลว ({e}) — จะขอใหม่อีกครั้ง")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                log(f"[WARN] Refresh token ล้มเหลว ({e}) — เริ่ม Flow ล็อคอินใหม่")
                creds = None

        if not creds:
            # ช่องหลักใช้ OAuth client ชื่อ Shopee Shorts โดยตรง
            # ห้าม fallback ไปใช้ client ของช่องอื่น/โปรเจกต์อื่น เพราะจะทำให้
            # Test users และ OAuth consent ตรวจคนละโปรเจกต์
            secret_file = CLIENT_SECRET_FILE if channel_id == 1 else TOOLS_DIR / f"client_secret_{channel_id}.json"
            if not secret_file.exists():
                for sf in [TOOLS_DIR / "client_secret_3.json", TOOLS_DIR / "client_secret_2.json"]:
                    if sf.exists():
                        secret_file = sf
                        break
            if not secret_file.exists():
                raise FileNotFoundError(
                    f"ไม่พบไฟล์ OAuth Client Secret ({secret_file.name} หรือ {CLIENT_SECRET_FILE.name})\n"
                    f"กรุณาวางไฟล์ที่: {TOOLS_DIR}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), SCOPES)
            log(f"🔑 กำลังเปิดเบราว์เซอร์เพื่อขอสิทธิ์อัปโหลด YouTube Shorts ช่องที่ {channel_id}...")
            creds = flow.run_local_server(port=0, open_browser=True, prompt='consent', access_type='offline')
        
        target_token_file.write_text(creds.to_json(), encoding="utf-8")
        log(f"[OK] บันทึก YouTube OAuth Token ช่องที่ {channel_id} สำเร็จ: {target_token_file.name}")

    return build("youtube", "v3", credentials=creds)


def build_shorts_title(product_name: str) -> str:
    """สร้างชื่อคลิป YouTube Shorts พร้อม #Shorts (ความยาวไม่เกิน 85 ตัวอักษร)"""
    _HOOKS = [
        "เตือนแล้วนะ! ใครยังไม่มีติดบ้านคือพลาดมาก",
        "มีตัวนี้แล้วชีวิตง่ายขึ้น 10 เท่า!",
        "ตัวนี้คนแย่งกันซื้อถล่มทลาย รีวิวแน่นมาก!",
        "อย่าเพิ่งเลื่อนผ่าน ถ้าไม่อยากพลาดของดี!",
        "ของหลักสิบแต่ประโยชน์หลักพัน คุ้มจนต้องบอกต่อ!",
    ]
    import random
    hook = random.choice(_HOOKS)
    clean_name = re.sub(r'^prod_\d+_', '', product_name)
    clean_name = re.sub(r'[_<>]+', ' ', clean_name).strip()
    
    title = f"{hook} {clean_name} #Shorts"
    if len(title) > 80:
        title = title[:75] + "... #Shorts"
    return title


def get_channel_info(youtube_service) -> dict:
    """ดึงชื่อช่องและแฮนเดิล (@handle) จริงจาก YouTube API"""
    try:
        res = youtube_service.channels().list(part="snippet", mine=True).execute()
        items = res.get("items", [])
        if items:
            snip = items[0].get("snippet", {})
            title = snip.get("title", "YouTube Channel")
            handle = snip.get("customUrl", "")
            if not handle and title:
                handle = f"@{title.replace(' ', '')}"
            return {"title": title, "handle": handle}
    except Exception:
        pass
    return {"title": "YouTube Shorts", "handle": ""}


def build_shorts_description(product_name: str, link: str, prod_id: Optional[int] = None, channel_handle: str = "") -> str:
    """สร้าง Description สำหรับ YouTube Shorts พร้อมลิงก์ Shopee และ LINE OA Deep Link"""
    line_url = os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    line_id = os.getenv("LINE_OA_ID", "@137gsref")
    
    code_prompt = f" แล้วพิมพ์ \"{prod_id}\"" if prod_id else ""
    deep_link = f"https://line.me/R/oaMessage/{line_id}/?รหัส{prod_id}" if prod_id else line_url
    channel_ref = f" {channel_handle}" if channel_handle else ""

    desc = (
        f"✨ {product_name}\n\n"
        f"🛒 พิกัดสั่งซื้อของแท้ / โปรโมชั่น Shopee:\n👉 {link}\n\n"
        f"💬 ทักแชท LINE ป้าเข็ม รับพิกัดตรงทันที:\n"
        f"👉 แอด LINE ไอดี: {line_id}{code_prompt}\n"
        f"👉 ลิงก์เปิดแชทรับพิกัด: {deep_link}\n\n"
        f"📍 หรือกดที่ชื่อช่อง{channel_ref} เพื่อดูลิงก์พิกัดหน้าโปรไฟล์ได้เลยจ้า!\n"
        f"----------------------------------------\n"
        f"#Shorts #ของดีบอกต่อ #ของมันต้องมี #ป้าเข็มป้ายยา #ถ้าไม่คุ้มป้าบอกให้ #ShopeeAffiliate #Shopee"
    )
    return desc


def upload_shorts_to_channel(youtube_service, video_path: pathlib.Path, product_meta: Optional[Dict] = None, channel_name: str = "YouTube Shorts") -> Optional[str]:
    """อัปโหลดไฟล์วิดีโอขึ้น YouTube Shorts ของ 1 ช่อง"""
    from googleapiclient.http import MediaFileUpload

    ch_info = get_channel_info(youtube_service)
    display_name = f"{ch_info['title']} ({ch_info['handle']})" if ch_info['handle'] else ch_info['title']

    name = sanitize_public_product_text(
        (product_meta or {}).get("product_name") or video_path.stem
    )
    link = (product_meta or {}).get("affiliate_link") or ""

    prod_id = None
    m = re.match(r'^prod_(\d+)_', video_path.name)
    if m:
        prod_id = int(m.group(1))

    title = build_shorts_title(name)
    description = build_shorts_description(name, link, prod_id=prod_id, channel_handle=ch_info.get("handle", ""))

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["Shorts", "ของดีบอกต่อ", "รีวิว", "Shopee", "ShopeeAffiliate", "ป้าเข็ม", "ของใช้ในบ้าน", "ไอที"],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    log(f"🚀 กำลังอัปโหลดคลิปขึ้น {channel_name}: {title[:50]}...")
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)

    request = youtube_service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"   [{channel_name}] อัปโหลดแล้ว {int(status.progress() * 100)}%")

    video_id = response.get("id")
    video_url = f"https://youtube.com/shorts/{video_id}"
    log(f"✅ อัปโหลด {channel_name} สำเร็จ! -> {video_url}")
    notify_telegram(f"✅ YouTube อัปโหลดสำเร็จ\nช่อง: {channel_name}\nคลิป: {video_url}")

    # โพสต์คอมเมนต์พิกัดสินค้าใต้คลิปอัตโนมัติ
    try:
        comment_text = (
            f"🛒 พิกัดสั่งซื้อของแท้ Shopee: {link}\n"
            f"💬 ปรึกษาป้าเข็มแอด LINE ID: @137gsref ได้เลยจ้า!"
        )
        youtube_service.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
        ).execute()
        log(f"💬 [{channel_name}] โพสต์คอมเมนต์พิกัดสินค้าใต้คลิป Shorts สำเร็จ!")
        notify_telegram(f"💬 YouTube คอมเมนต์สำเร็จ\nช่อง: {channel_name}\nคลิป: {video_url}")
    except Exception as ec:
        log(f"[INFO] คอมเมนต์อัตโนมัติ ({channel_name}): {type(ec).__name__}: {str(ec)[:160]}")
        notify_telegram(f"⚠️ YouTube อัปโหลดได้ แต่คอมเมนต์ไม่สำเร็จ\nช่อง: {channel_name}\nคลิป: {video_url}\nสาเหตุ: {type(ec).__name__}")

    return video_url


LAST_CHANNEL_INDEX_FILE = TOOLS_DIR / "last_youtube_channel_index.txt"


def get_next_channel_rotation(tokens: list):
    """จัดลำดับคิวช่อง YouTube แบบ Round-Robin: สลับช่องวนรอบ และต่อคิวด้วยช่องถัดไปอัตโนมัติ (Auto-Failover)"""
    if not tokens:
        return [], 0
    last_idx = -1
    if LAST_CHANNEL_INDEX_FILE.exists():
        try:
            last_idx = int(LAST_CHANNEL_INDEX_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            last_idx = -1
    
    next_idx = (last_idx + 1) % len(tokens)
    ordered = tokens[next_idx:] + tokens[:next_idx]
    return ordered, next_idx


def set_last_successful_channel(token_id: int, tokens: list):
    """บันทึกลำดับช่องที่โพสต์สำเร็จ เพื่อให้รอบถัดไปสลับไปช่องใหม่"""
    try:
        for idx, t in enumerate(tokens):
            if t["id"] == token_id:
                LAST_CHANNEL_INDEX_FILE.write_text(str(idx), encoding="utf-8")
                break
    except Exception:
        pass


def notify_line_admin(message: str):
    """ส่งแจ้งเตือนด่วนเข้า LINE เจ้าของร้านเมื่อติดลิมิตหรือมีระบบไม่ทำงาน"""
    try:
        from linebot import LineBotApi
        from linebot.models import TextSendMessage
        token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or ""
        if not token or "mock" in token.lower():
            return
        admin_uid = (os.getenv("ADMIN_LINE_USER_ID") or "Uc88eb3896b0e4bcc5fbaa9b78ac1294e").strip()
        LineBotApi(token).push_message(admin_uid, TextSendMessage(text=message[:1500]))
        log(f"[LINE-ALERT] ส่งแจ้งเตือนปัญหาเข้า LINE แอดมินแล้ว: {message[:50]}...")
    except Exception as e:
        log(f"[LINE-ALERT] ส่งแจ้งเตือนปัญหาล้ม: {e}")


def upload_shorts(video_path: Union[pathlib.Path, str], product_meta: Optional[Dict] = None, broadcast_all: bool = False):
    """อัปโหลดขึ้น YouTube Shorts:
    - โหมดหมุนเวียน (Default): สลับช่องวนรอบ (Round-Robin) เพื่อเฉลี่ยโควต้า 24 ชม. + สลับช่องอัตโนมัติหากช่องในคิวโควต้าเต็ม (Auto-Failover)
    - โหมด Broadcast All: ยิงทุกช่องพร้อมกัน
    """
    video_path = pathlib.Path(video_path)
    tokens = get_token_files()
    if not tokens:
        log("[WARN] ไม่พบไฟล์ YouTube Token ใดๆ ใน tools/")
        notify_line_admin("⚠️ [แจ้งเตือนระบบ YouTube]\n\nไม่พบไฟล์ Token สำหรับเชื่อมต่อ YouTube ในระบบ กรุณาตรวจสอบการล็อกอินจ้า")
        return None

    if broadcast_all:
        results = []
        for t in tokens:
            try:
                yt_service = get_authenticated_service(token_path=t["path"], channel_id=t["id"])
                ch_info = get_channel_info(yt_service)
                ch_display = f"{ch_info['title']} ({ch_info['handle']})" if ch_info.get("handle") else ch_info.get("title", t["name"])
                url = upload_shorts_to_channel(yt_service, video_path, product_meta, channel_name=ch_display)
                if url:
                    results.append({"channel": ch_display, "url": url, "id": t["id"]})
            except Exception as e:
                log(f"[WARN] อัปโหลดขึ้น {t['name']} ล้มเหลว: {e}")
        return results

    # โหมด Round-Robin Rotation + Auto-Failover (เฉลี่ยโควต้าและกันสะดุด)
    ordered_tokens, target_idx = get_next_channel_rotation(tokens)
    results = []

    for t in ordered_tokens:
        try:
            yt_service = get_authenticated_service(token_path=t["path"], channel_id=t["id"])
            ch_info = get_channel_info(yt_service)
            ch_display = f"{ch_info['title']} ({ch_info['handle']})" if ch_info.get("handle") else ch_info.get("title", t["name"])
            url = upload_shorts_to_channel(yt_service, video_path, product_meta, channel_name=ch_display)
            if url:
                set_last_successful_channel(t["id"], tokens)
                results.append({"channel": ch_display, "url": url, "id": t["id"]})
                log(f"🎯 [Rotation] โพสต์ YouTube Shorts สำเร็จด้วย {ch_display} (รอบถัดไปจะสลับช่องต่อไป)")
                break  # โพสต์สำเร็จ 1 ช่องในรอบนี้เรียบร้อย (เฉลี่ยโควต้า)
        except Exception as e:
            err_str = str(e)
            if "uploadLimitExceeded" in err_str:
                reason = "ติดลิมิตการอัปโหลดรายวันของ Google (Daily Quota Exceeded)"
            elif "invalid_grant" in err_str:
                reason = "เซสชันล็อกอินหมดอายุ กรุณากดเชื่อมต่อใหม่"
            elif "quotaExceeded" in err_str:
                reason = "API Quota ประจำวันหมดชั่วคราว"
            else:
                reason = f"เกิดข้อผิดพลาด ({err_str[:80]})"

            log(f"[WARN] ช่อง {t['name']} ไม่พร้อม ({reason}) ➔ สลับไปช่องสำรองถัดไปอัตโนมัติ (Auto-Failover)...")
            notify_line_admin(
                f"⚠️ [แจ้งเตือนสถานะ YouTube]\n\n"
                f"🔴 ช่อง: {t['name']}\n"
                f"📌 สถานะ: {reason}\n\n"
                f"🔄 ระบบ Auto-Failover สลับไปโพสต์ช่องสำรองถัดไปให้อัตโนมัติเรียบร้อยจ้า"
            )

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Channel YouTube Shorts Uploader")
    parser.add_argument("--auth-only", action="store_true", help="ทำแค่ยืนยันสิทธิ์ OAuth ช่องหลัก")
    parser.add_argument("--add-channel", type=int, default=0, help="ล็อกอินเพิ่มช่อง YouTube ลำดับที่ระบุ (เช่น --add-channel 2)")
    parser.add_argument("--list-channels", action="store_true", help="แสดงรายการช่อง YouTube ที่เชื่อมต่อไว้")
    parser.add_argument("--video", type=str, help="อัปโหลดวิดีโอที่ระบุ")
    args = parser.parse_args()

    if args.list_channels:
        tokens = get_token_files()
        print(f"\n📺 รายการช่อง YouTube ที่เชื่อมต่อไว้ในระบบ ({len(tokens)} ช่อง):")
        for t in tokens:
            try:
                service = get_authenticated_service(token_path=t["path"], channel_id=t["id"])
                info = get_channel_info(service)
                disp = f"{info['title']} ({info['handle']})" if info.get("handle") else info.get("title", t["name"])
                print(f"  • [{t['id']}] {disp} (ไฟล์: {t['path'].name})")
            except Exception as e:
                print(f"  • [{t['id']}] {t['name']} (ไฟล์: {t['path'].name}) - ข้อผิดพลาด: {e}")
        print("")
        return

    if args.add_channel > 0:
        get_authenticated_service(channel_id=args.add_channel)
        print(f"🎉 สำเร็จ! เชื่อมต่อช่อง YouTube ช่องที่ {args.add_channel} เรียบร้อยแล้ว!")
        return

    if args.auth_only:
        get_authenticated_service(channel_id=1)
        print("✅ ยืนยันสิทธิ์บัญชี YouTube ช่องหลักสำเร็จเรียบร้อยแล้ว!")
        return

    vids = sorted(PENDING_DIR.glob("*.mp4"), key=os.path.getmtime)
    if not vids:
        print("ℹ️ ไม่มีคลิปรอโพสต์ใน pending_videos/")
        return

    target_vid = pathlib.Path(args.video) if args.video else vids[0]
    
    meta = {}
    if PRODUCTS_JSON.exists():
        try:
            all_meta = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
            meta = all_meta.get(target_vid.name, {})
        except Exception:
            pass

    urls = upload_shorts(target_vid, meta)
    if urls:
        print(f"\n🎉 สำเร็จ! เผยแพร่แล้ว {len(urls)} ช่องทาง:")
        for u in urls:
            print(f"  • {u['channel']}: {u['url']}")


if __name__ == "__main__":
    main()
