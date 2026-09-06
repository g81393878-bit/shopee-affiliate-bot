#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/update_sheet_metrics.py
================================
ดึงยอดวิว, ยอดไลก์, ยอดคอมเมนต์ จาก YouTube Shorts และ Facebook Reels
กลับมาอัปเดตลงใน Google Sheets อัตโนมัติ:
- Spreadsheet ID: 1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU
- คอลัมน์ที่อัปเดต:
  Col I: ยอดวิวรวม (Total Views)
  Col J: ยอดไลก์รวม (Total Likes)
  Col K: คอมเมนต์รวม (Total Comments)
  Col L: เกรดความไวรัล (Viral Rating)
  Col M: อัปเดตสถิติล่าสุด (Last Updated)
"""

import os
import sys
import json
import re
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT_DIR / "tools"
BACKEND_DIR = ROOT_DIR / "backend"

sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

import httpx
from google_docs_logger import get_credentials
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SPREADSHEET_ID = os.getenv("BROADCAST_SPREADSHEET_ID", "1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU")
ICT = timezone(timedelta(hours=7))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SheetMetricsUpdater")


def get_youtube_service():
    """สร้าง YouTube Service จาก token ที่มีในระบบ"""
    token_files = [
        TOOLS_DIR / "youtube_token.json",
        TOOLS_DIR / "youtube_token_2.json",
        TOOLS_DIR / "youtube_token_3.json",
        TOOLS_DIR / "youtube_token_4.json",
        TOOLS_DIR / "youtube_token_5.json",
        TOOLS_DIR / "youtube_token_6.json",
    ]
    for tf in token_files:
        if tf.exists():
            try:
                t_data = json.loads(tf.read_text(encoding="utf-8"))
                creds = Credentials(
                    token=t_data.get("token"),
                    refresh_token=t_data.get("refresh_token"),
                    token_uri=t_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                    client_id=t_data.get("client_id"),
                    client_secret=t_data.get("client_secret"),
                    scopes=t_data.get("scopes")
                )
                service = build("youtube", "v3", credentials=creds)
                return service
            except Exception as e:
                logger.debug(f"Failed loading YT creds from {tf.name}: {e}")
    return None


def fetch_youtube_video_stats(video_ids: List[str]) -> Dict[str, Dict]:
    """ดึงสถิติยอดวิว, ไลก์, คอมเมนต์ จาก YouTube Data API แบบ Batch (สูงสุด 50 คลิป/รอบ)"""
    if not video_ids:
        return {}

    yt = get_youtube_service()
    if not yt:
        logger.warning("⚠️ ไม่พบ YouTube Service/Token ที่ใช้งานได้")
        return {}

    stats_map = {}
    # แบ่ง batch ละ 50 รายการตามขีดจำกัด YouTube API
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        try:
            resp = yt.videos().list(
                part="statistics",
                id=",".join(chunk)
            ).execute()

            for item in resp.get("items", []):
                vid = item["id"]
                st = item.get("statistics", {})
                stats_map[vid] = {
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0))
                }
        except Exception as e:
            logger.warning(f"⚠️ ดึงสถิติ YouTube Batch ล้มเหลว: {e}")

    return stats_map


def fetch_facebook_reel_stats(video_id: str, page_token: Optional[str] = None) -> Dict:
    """ดึงสถิติยอดวิว, ไลก์, คอมเมนต์ จาก Facebook Graph API"""
    if not video_id or not video_id.isdigit():
        return {"views": 0, "likes": 0, "comments": 0}

    token = page_token or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    if not token:
        return {"views": 0, "likes": 0, "comments": 0}

    try:
        url = f"https://graph.facebook.com/v20.0/{video_id}"
        params = {
            "fields": "views,likes.summary(true),comments.summary(true)",
            "access_token": token
        }
        res = httpx.get(url, params=params, timeout=10)
        if res.status_code == 200:
            d = res.json()
            views = int(d.get("views", 0))
            likes = int((d.get("likes", {}) or {}).get("summary", {}).get("total_count", 0))
            comments = int((d.get("comments", {}) or {}).get("summary", {}).get("total_count", 0))
            return {"views": views, "likes": likes, "comments": comments}
    except Exception as e:
        logger.debug(f"FB stats error for {video_id}: {e}")

    return {"views": 0, "likes": 0, "comments": 0}


def calculate_viral_rating(total_views: int, total_likes: int) -> str:
    """คำนวณเกรดความไวรัลพร้อม Emoji แสดงสถานะชัดเจน"""
    if total_views >= 10000:
        return "🔥 ไวรัลแตก (S+)"
    elif total_views >= 1000:
        return "🟢 ยอดนิยม (A)"
    elif total_views >= 100:
        return "🟡 กำลังมาแรง (B)"
    elif total_views > 0:
        return "⚪ กำลังสะสมวิว (C)"
    else:
        return "⏱️ เพิ่งเผยแพร่"


def update_all_metrics_in_sheet():
    """ฟังก์ชันหลัก: อ่านชีท -> ดึงสถิติสด -> คำนวณเกรด -> อัปเดตกลับลงชีท"""
    logger.info("🚀 เริ่มต้นกระบวนการดึงยอดวิว/ยอดไลก์อัตโนมัติ...")
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds)

    # 1. ตรวจสอบและอัปเดตหัวตาราง (Cols I to M)
    headers_ext = [
        ["ยอดวิวรวม (Views)", "ยอดไลก์รวม (Likes)", "คอมเมนต์รวม (Comments)", "เกรดความไวรัล (Rating)", "อัปเดตสถิติล่าสุด (ICT)"]
    ]
    sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="I1:M1",
        valueInputOption="USER_ENTERED",
        body={"values": headers_ext}
    ).execute()

    # 2. อ่านข้อมูลแถวทั้งหมดจากคอลัมน์ A ถึง H
    data_resp = sheets.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="A2:H300"
    ).execute()
    rows = data_resp.get("values", [])
    if not rows:
        logger.info("ไม่มีข้อมูลแถวให้ประมวลผล")
        return 0

    logger.info(f"📊 พบข้อมูลที่ต้องตรวจสอบสถิติทั้งหมด: {len(rows)} คลิป")

    # 3. รวบรวม YouTube Video IDs ทั้งหมด
    yt_id_to_row_idx = {}
    all_yt_ids = []
    fb_token_p1 = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    fb_token_p2 = os.getenv("PAGE_2_ACCESS_TOKEN", "")

    for idx, row in enumerate(rows):
        # Col G (index 6): YouTube Shorts Link
        yt_link = row[6] if len(row) > 6 else ""
        m_yt = re.search(r'(?:shorts/|v=)([a-zA-Z0-9_-]{11})', yt_link)
        if m_yt:
            vid = m_yt.group(1)
            all_yt_ids.append(vid)
            if vid not in yt_id_to_row_idx:
                yt_id_to_row_idx[vid] = []
            yt_id_to_row_idx[vid].append(idx)

    # ดึงสถิติจาก YouTube API
    yt_stats = fetch_youtube_video_stats(all_yt_ids)

    # 4. ประกอบค่าสถิติใหม่สำหรับแต่ละแถว (Columns I to M)
    metrics_rows = []
    now_str = datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S")

    for idx, row in enumerate(rows):
        total_views = 0
        total_likes = 0
        total_comments = 0

        # สถิติ YouTube Shorts
        yt_link = row[6] if len(row) > 6 else ""
        m_yt = re.search(r'(?:shorts/|v=)([a-zA-Z0-9_-]{11})', yt_link)
        if m_yt and m_yt.group(1) in yt_stats:
            s_yt = yt_stats[m_yt.group(1)]
            total_views += s_yt["views"]
            total_likes += s_yt["likes"]
            total_comments += s_yt["comments"]

        # สถิติ Facebook Reel เพจ 1
        p1_link = row[4] if len(row) > 4 else ""
        m_p1 = re.search(r'reel/(\d+)', p1_link)
        if m_p1:
            s_p1 = fetch_facebook_reel_stats(m_p1.group(1), fb_token_p1)
            total_views += s_p1["views"]
            total_likes += s_p1["likes"]
            total_comments += s_p1["comments"]

        # สถิติ Facebook Reel เพจ 2
        p2_link = row[5] if len(row) > 5 else ""
        m_p2 = re.search(r'reel/(\d+)', p2_link)
        if m_p2:
            s_p2 = fetch_facebook_reel_stats(m_p2.group(1), fb_token_p2)
            total_views += s_p2["views"]
            total_likes += s_p2["likes"]
            total_comments += s_p2["comments"]

        rating = calculate_viral_rating(total_views, total_likes)

        metrics_rows.append([
            total_views,
            total_likes,
            total_comments,
            rating,
            now_str
        ])

    # 5. เขียนอัปเดตสถิติทั้งหมดกลับลงช่วง I2:M... ในคำสั่งเดียว (Batch Update)
    sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"I2:M{len(metrics_rows) + 1}",
        valueInputOption="USER_ENTERED",
        body={"values": metrics_rows}
    ).execute()

    logger.info(f"✅ อัปเดตยอดวิว/ยอดไลก์ลงชีทสำเร็จครบทั้ง {len(metrics_rows)} รายการ!")
    logger.info(f"🔗 ลิงก์ชีท: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")
    return len(metrics_rows)


def get_sheet_summary() -> str:
    """ดึงข้อมูลสรุปภาพรวมและคลิปยอดนิยม Top 3 จาก Google Sheets เพื่อรายงานผ่าน Telegram"""
    try:
        creds = get_credentials()
        sheets = build("sheets", "v4", credentials=creds)
        res = sheets.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="A2:M100"
        ).execute()
        rows = res.get("values", [])
        if not rows:
            return (
                "📈 [รายงานสถิติ Google Sheets]\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ ยังไม่มีข้อมูลบันทึกในตาราง\n"
                f"🔗 ลิงก์: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
            )

        total_clips = len(rows)
        parsed = []
        total_views_all = 0
        total_likes_all = 0

        for r in rows:
            title = r[1] if len(r) > 1 else "ไม่มีชื่อ"
            yt_link = r[6] if len(r) > 6 else ""
            p1_link = r[4] if len(r) > 4 else ""
            views = int(r[8]) if len(r) > 8 and str(r[8]).isdigit() else 0
            likes = int(r[9]) if len(r) > 9 and str(r[9]).isdigit() else 0
            rating = r[11] if len(r) > 11 else "⚪ กำลังสะสมวิว (C)"
            
            total_views_all += views
            total_likes_all += likes
            link = yt_link if yt_link and yt_link != "-" else p1_link

            parsed.append({
                "title": title,
                "views": views,
                "likes": likes,
                "rating": rating,
                "link": link
            })

        # เรียงตามยอดวิวสูงสุด
        parsed.sort(key=lambda x: x["views"], reverse=True)
        top_clips = parsed[:3]

        top_lines = []
        for i, c in enumerate(top_clips, start=1):
            top_lines.append(
                f"{i}. 🎬 {c['title'][:32]}...\n"
                f"   • 👁️ {c['views']:,} วิว | ❤️ {c['likes']:,} ไลก์ | {c['rating']}\n"
                f"   • 🔗 {c['link']}"
            )

        top_text = "\n".join(top_lines) if top_lines else "ยังไม่มีสถิติวิว"

        msg = (
            "📈 [รายงานสถิติยอดวิว & สถิติ Google Sheets]\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🔗 ลิงก์ชีท: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit\n\n"
            f"📊 ผลงานสะสมในระบบ:\n"
            f"  • 🎬 คลิปที่บันทึกทั้งหมด: {total_clips} รายการ\n"
            f"  • 👁️ ยอดวิวรวมสะสม: {total_views_all:,} วิว\n"
            f"  • ❤️ ยอดไลก์รวมสะสม: {total_likes_all:,} ไลก์\n\n"
            f"🏆 3 อันดับคลิปยอดวิวสูงสุด:\n"
            f"{top_text}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✨ ข้อมูลซิงค์สดจาก YouTube Data API v3 & Meta Graph API"
        )
        return msg
    except Exception as e:
        return (
            "📈 [รายงานสถิติ Google Sheets]\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🔗 ลิงก์ชีท: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit\n"
            f"⚠️ ไม่สามารถดึงสรุปได้: {e}"
        )


if __name__ == "__main__":
    count = update_all_metrics_in_sheet()
    print(f"DONE: Updated stats for {count} videos")
    print("\n--- SUMMARY ---")
    print(get_sheet_summary())
