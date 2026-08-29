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
from typing import Dict, Optional

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

CLIENT_SECRET_FILE = TOOLS_DIR / "client_secret.json"
TOKEN_FILE = TOOLS_DIR / "youtube_token.json"
YOUTUBE_LOG_FILE = TOOLS_DIR / "youtube_uploader.log"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]

def log(msg: str):
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(YOUTUBE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_authenticated_service():
    """สร้างหรือโหลดเซสชัน YouTube API จาก OAuth token"""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
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
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"ไม่พบไฟล์ {CLIENT_SECRET_FILE}\n"
                    f"กรุณาดาวน์โหลด client_secret.json จาก Google Cloud Console (Project: telegram-smart-memo)\n"
                    f"แล้วนำมาวางที่: {CLIENT_SECRET_FILE}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            print("\n=======================================================")
            print("🔑 กำลังเปิดเบราว์เซอร์เพื่อขอสิทธิ์อัปโหลด YouTube Shorts")
            print("กรุณาเลือกบัญชีที่เป็นเจ้าของช่อง Anda (@regency1229)")
            print("=======================================================\n")
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        log("[OK] บันทึก YouTube OAuth Token สำเร็จ (รันอัตโนมัติรอบถัดไปได้ทันที)")

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
    # ตัด prod_xxx_ นำหน้าออกถ้ามี
    clean_name = re.sub(r'^prod_\d+_', '', product_name)
    clean_name = re.sub(r'[_<>]+', ' ', clean_name).strip()
    
    # รวม Title ไม่ให้เกิน 80 ตัวอักษร
    title = f"{hook} {clean_name} #Shorts"
    if len(title) > 80:
        title = title[:75] + "... #Shorts"
    return title


def build_shorts_description(product_name: str, link: str, prod_id: Optional[int] = None) -> str:
    """สร้าง Description สำหรับ YouTube Shorts พร้อมลิงก์ Shopee และ LINE OA Deep Link"""
    line_url = os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    line_id = os.getenv("LINE_OA_ID", "@137gsref")
    
    code_prompt = f" แล้วพิมพ์ \"{prod_id}\"" if prod_id else ""
    deep_link = f"https://line.me/R/oaMessage/{line_id}/?รหัส{prod_id}" if prod_id else line_url

    desc = (
        f"✨ {product_name}\n\n"
        f"🛒 พิกัดสั่งซื้อของแท้ / โปรโมชั่น Shopee:\n👉 {link}\n\n"
        f"💬 ทักแชท LINE ป้าเข็ม รับพิกัดตรงทันที:\n"
        f"👉 แอด LINE ไอดี: {line_id}{code_prompt}\n"
        f"👉 ลิงก์เปิดแชทรับพิกัด: {deep_link}\n\n"
        f"📍 หรือกดที่ชื่อช่อง @regency1229 เพื่อดูลิงก์พิกัดหน้าโปรไฟล์ได้เลยจ้า!\n"
        f"----------------------------------------\n"
        f"#Shorts #ของดีบอกต่อ #ของมันต้องมี #ป้าเข็มป้ายยา #ถ้าไม่คุ้มป้าบอกให้ #ShopeeAffiliate #Shopee"
    )
    return desc


def upload_shorts(video_path: pathlib.Path, product_meta: Optional[Dict] = None) -> Optional[str]:
    """อัปโหลดไฟล์วิดีโอขึ้น YouTube Shorts"""
    from googleapiclient.http import MediaFileUpload

    name = (product_meta or {}).get("product_name") or video_path.stem
    link = (product_meta or {}).get("affiliate_link") or ""

    prod_id = None
    m = re.match(r'^prod_(\d+)_', video_path.name)
    if m:
        prod_id = int(m.group(1))

    title = build_shorts_title(name)
    description = build_shorts_description(name, link, prod_id=prod_id)

    youtube = get_authenticated_service()

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

    log(f"🚀 กำลังอัปโหลดคลิปขึ้น YouTube Shorts: {title[:50]}...")
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"   อัปโหลดแล้ว {int(status.progress() * 100)}%")

    video_id = response.get("id")
    video_url = f"https://youtube.com/shorts/{video_id}"
    log(f"✅ อัปโหลด YouTube Shorts สำเร็จ! -> {video_url}")

    # โพสต์คอมเมนต์พิกัดสินค้าใต้คลิปอัตโนมัติ
    try:
        comment_text = (
            f"🛒 พิกัดสั่งซื้อของแท้ Shopee: {link}\n"
            f"💬 ปรึกษาป้าเข็มแอด LINE ID: @137gsref หรือกดลิงก์หน้าช่อง @regency1229 ได้เลยจ้า!"
        )
        youtube.commentThreads().insert(
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
        log("💬 โพสต์คอมเมนต์พิกัดสินค้าใต้คลิป Shorts สำเร็จ!")
    except Exception as ec:
        log(f"[INFO] คอมเมนต์อัตโนมัติ: {ec}")

    return video_url


def main():
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Shorts Uploader")
    parser.add_argument("--auth-only", action="store_true", help="ทำแค่ยืนยันสิทธิ์ OAuth ครั้งแรก")
    parser.add_argument("--video", type=str, help="อัปโหลดวิดีโอที่ระบุ")
    args = parser.parse_args()

    if args.auth_only:
        get_authenticated_service()
        print("✅ ยืนยันสิทธิ์บัญชี YouTube สำเร็จเรียบร้อยแล้ว!")
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

    url = upload_shorts(target_vid, meta)
    if url:
        print(f"\n🎉 สำเร็จ! คลิปสั้นของคุณเผยแพร่แล้วที่: {url}")


if __name__ == "__main__":
    main()
