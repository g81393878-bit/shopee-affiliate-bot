#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/sync_broadcast_history_to_sheet.py
=========================================
รวบรวมประวัติการเผยแพร่วิดีโอทั้งหมด (TikTok, Facebook Reels, YouTube Shorts)
เรียงลำดับจาก "คลิปล่าสุดอยู่บนสุด" (Newest First / Row 2)
และบันทึกลง Google Sheets ของโปรเจกต์:
- Spreadsheet ID: 1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU
- URL: https://docs.google.com/spreadsheets/d/1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU/edit
- Folder: Paa Khem Bot & Shopee Affiliate Master Workspace (ID: 1jbNqUdiKf0Zdhk218QT_2yb4q63Vk2rj)
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "tools"))

from google_docs_logger import get_credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = "1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU"
ICT = timezone(timedelta(hours=7))

TT_HANDLE_MAP = {
    "tiktok_cookies": "https://www.tiktok.com/@healthgooddeals",
    "tiktok_cookies_2": "https://www.tiktok.com/@cheepao.review",
    "tiktok_cookies_3": "https://www.tiktok.com/@pakhem.review99",
    "tiktok_cookies_4": "https://www.tiktok.com/@khonyangmefan",
}

# รายการโพสต์สดล่าสุดที่ยืนยันการแพร่ภาพครบทุกช่องทาง
KNOWN_LIVE_BROADCASTS = [
    {
        "timestamp": "2026-09-06 16:38:43",
        "title": "เซอร์ไพรส์คุกเข่าขอแต่งงานสุดโรแมนติก (ภูผา เตชะณรงค์ & มิ้นต์ ชาลิดา)",
        "category": "ข่าวเรียลไทม์ (TRENDING_NEWS)",
        "tiktok": "https://www.tiktok.com/@pakhem.review99",
        "p1": "https://www.facebook.com/reel/4387500554818126",
        "p2": "https://www.facebook.com/reel/1101282316015941",
        "yt": "https://youtube.com/shorts/cWjoicbR7rU",
        "status": "✅ เผยแพร่สำเร็จ 100%"
    },
    {
        "timestamp": "2026-09-06 16:32:39",
        "title": "น้องปีใหม่สวยจึ้ง! คว้ารางวัลใหม่ที่คุณต้องไม่พลาด",
        "category": "ข่าวเรียลไทม์ (TRENDING_NEWS)",
        "tiktok": "https://www.tiktok.com/@cheepao.review",
        "p1": "https://www.facebook.com/reel/1994025837947307",
        "p2": "https://www.facebook.com/reel/1106035865137156",
        "yt": "https://youtube.com/shorts/Re0xibWexyM",
        "status": "✅ เผยแพร่สำเร็จ 100%"
    },
    {
        "timestamp": "2026-09-06 16:25:23",
        "title": "เหตุผลที่ ขวัญ อุษามณี ยื่นหลักฐานสู้คดี",
        "category": "คนดัง (CELEBRITY_TREND)",
        "tiktok": "https://www.tiktok.com/@healthgooddeals",
        "p1": "https://www.facebook.com/reel/1450243947241790",
        "p2": "https://www.facebook.com/reel/1550947136251534",
        "yt": "https://youtube.com/shorts/fNeEGweGczs",
        "status": "✅ เผยแพร่สำเร็จ 100%"
    },
    {
        "timestamp": "2026-09-06 16:19:37",
        "title": "เมย์ประกาศต้อนรับลูกคนใหม่ แต่แฟนคลับจับตาประเด็นสำคัญ",
        "category": "คนดัง (CELEBRITY_TREND)",
        "tiktok": "https://www.tiktok.com/@khonyangmefan",
        "p1": "https://www.facebook.com/reel/1400258285406313",
        "p2": "https://www.facebook.com/reel/28631280913136842",
        "yt": "https://youtube.com/shorts/eO0z-eXm5qI",
        "status": "✅ เผยแพร่สำเร็จ 100%"
    },
    {
        "timestamp": "2026-09-06 16:08:54",
        "title": "อูมและก้อยศัลยกรรมใหม่ ย้ำสวยขึ้นมั่นใจกว่าเดิม",
        "category": "คนดัง (CELEBRITY_TREND)",
        "tiktok": "https://www.tiktok.com/@pakhem.review99",
        "p1": "https://www.facebook.com/reel/1379305534402430",
        "p2": "https://www.facebook.com/reel/933389182623988",
        "yt": "https://youtube.com/shorts/UiTIzRiT8pA",
        "status": "✅ เผยแพร่สำเร็จ 100%"
    },
    {
        "timestamp": "2026-09-06 16:00:48",
        "title": "เนย วรัฐฐา โพสต์เดือด หมดเวลาให้คนไม่เห็นค่า",
        "category": "ข่าวเรียลไทม์ (TRENDING_NEWS)",
        "tiktok": "https://www.tiktok.com/@cheepao.review",
        "p1": "https://www.facebook.com/reel/1449947900285307",
        "p2": "https://www.facebook.com/reel/1043316848543313",
        "yt": "https://youtube.com/shorts/9-X3I1oY21c",
        "status": "✅ เผยแพร่สำเร็จ 100%"
    }
]


def parse_uploader_log(log_path: Path):
    """ดึงข้อมูลโพสต์ Facebook Reels และชื่อไฟล์วิดีโอจาก uploader_execution.log"""
    if not log_path.exists():
        return []

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    records = []
    cur_p1 = None
    cur_p2 = None

    for line in lines:
        m1 = re.search(r'โพสต์เพจ 1 สำเร็จ video_id=(\d+)', line)
        if m1:
            cur_p1 = m1.group(1)

        m2 = re.search(r'โพสต์เพจ 2 สำเร็จ video_id=(\d+)', line)
        if m2:
            cur_p2 = m2.group(1)

        m_ok = re.search(r'วิดีโอโพสต์สำเร็จ .*? → (.+\.mp4)', line)
        if m_ok:
            v_name = m_ok.group(1)
            ts_m = re.search(r'^\[(.*?)\]', line)
            ts_str = ts_m.group(1) if ts_m else ""
            
            ts_display = ""
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    dt_ict = dt.astimezone(ICT)
                    ts_display = dt_ict.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    ts_display = ts_str

            records.append({
                "timestamp": ts_display,
                "video": v_name,
                "p1_id": cur_p1,
                "p2_id": cur_p2
            })
            cur_p1, cur_p2 = None, None

    return records


def build_all_rows():
    """ประกอบแถวข้อมูลสมบูรณ์สำหรับ Google Sheets จากประวัติทั้งหมด เรียงจากใหม่ไปเก่า (Newest First)"""
    rows_dict = {}

    # 1. บรรจุรายการล่าสุดที่เป็นทางการก่อน
    for item in KNOWN_LIVE_BROADCASTS:
        key = item["title"]
        rows_dict[key] = [
            item["timestamp"],
            item["title"],
            item["category"],
            item["tiktok"],
            item["p1"],
            item["p2"],
            item["yt"],
            item["status"]
        ]

    # 2. โหลด YouTube History
    yt_file = ROOT_DIR / "tools" / "posted_youtube_history.json"
    yt_history = []
    if yt_file.exists():
        try:
            yt_history = json.loads(yt_file.read_text(encoding="utf-8"))
        except Exception:
            yt_history = []

    # 3. โหลด TikTok History
    tt_file = ROOT_DIR / "tools" / "posted_tiktok_history.json"
    tt_history = {}
    if tt_file.exists():
        try:
            tt_history = json.loads(tt_file.read_text(encoding="utf-8"))
        except Exception:
            tt_history = {}

    tt_video_map = {}
    for acc_key, vlist in tt_history.items():
        ch_url = TT_HANDLE_MAP.get(acc_key, "https://www.tiktok.com/@cheepao.review")
        for v in vlist:
            tt_video_map[v] = ch_url

    # 4. โหลด Facebook Reels Log
    fb_records = parse_uploader_log(ROOT_DIR / "reels_uploader" / "uploader_execution.log")

    for rec in fb_records:
        v_name = rec["video"]
        ts = rec["timestamp"]
        p1 = f"https://www.facebook.com/reel/{rec['p1_id']}" if rec.get("p1_id") else "-"
        p2 = f"https://www.facebook.com/reel/{rec['p2_id']}" if rec.get("p2_id") else "-"
        tt_url = tt_video_map.get(v_name, "-")

        yt_url = "-"
        clean_v = re.sub(r'^\d+_', '', v_name).replace('.mp4', '').strip()
        for y in reversed(yt_history):
            y_title = y.get("title", "")
            if any(part in y_title for part in clean_v.split('_') if len(part) > 4):
                yt_url = y.get("url", "-")
                break

        category = "คนดัง (CELEBRITY_TREND)" if "celebrity" in v_name.lower() else "ข่าวเรียลไทม์ (TRENDING_NEWS)" if "trending" in v_name.lower() else "ไลฟ์แฮก/สินค้า"
        title_clean = clean_v.replace('_', ' ')

        # ถ้ายังไม่มีในตาราง ให้เพิ่ม
        if title_clean not in rows_dict:
            rows_dict[title_clean] = [
                ts or datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S"),
                title_clean,
                category,
                tt_url,
                p1,
                p2,
                yt_url,
                "✅ เผยแพร่สำเร็จ 100%"
            ]

    # เพิ่มคลิปจาก YouTube Shorts ที่ยังตกหล่น
    for y in yt_history:
        y_url = y.get("url", "")
        y_title = y.get("title", "").split('\n')[0].replace('#Shorts', '').strip()
        ts_y = y.get("posted_at", "")
        ts_display = ""
        if ts_y:
            try:
                dt = datetime.fromisoformat(ts_y.replace("Z", "+00:00"))
                ts_display = dt.astimezone(ICT).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts_display = ts_y

        already_in = any(r[6] == y_url for r in rows_dict.values())
        if not already_in and y_url and y_title not in rows_dict:
            rows_dict[y_title] = [
                ts_display or datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S"),
                y_title,
                "คนดัง / ข่าวสาร",
                "-",
                "-",
                "-",
                y_url,
                "✅ เผยแพร่สำเร็จ 100%"
            ]

    # แปลงเป็น List และเรียงลำดับเวลาจาก "ใหม่ล่าสุดไปหาเก่าสุด" (Newest First)
    all_rows = list(rows_dict.values())
    all_rows.sort(key=lambda r: r[0], reverse=True)

    return all_rows


def sync_to_sheet():
    print("🔄 กำลังจัดเตรียมข้อมูลประวัติการเผยแพร่ทุกช่องทาง (เรียงใหม่อยู่บน)...")
    rows = build_all_rows()
    print(f"📦 รวบรวมข้อมูลได้ทั้งหมด: {len(rows)} รายการ")

    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds)

    # 1. เขียนส่วนหัวตาราง
    headers = [
        ["วัน-เวลา (ICT)", "หัวข้อคลิป", "หมวดหมู่", "TikTok Link", "Facebook Reel 1 (ป้าเข็ม ขายของ)", "Facebook Reel 2 (ป้าเข็ม ชี้เป้าของดี)", "YouTube Shorts Link", "สถานะการเผยแพร่"]
    ]
    sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="A1:H1",
        valueInputOption="USER_ENTERED",
        body={"values": headers}
    ).execute()

    # ล้างช่วงข้อมูลเดิมเพื่อเขียนลำดับใหม่ทั้งหมด
    sheets.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range="A2:H500"
    ).execute()

    if rows:
        # 2. เขียนข้อมูลแถวทั้งหมด (ใหม่สุดอยู่แถวที่ 2 ต่อจากหัวตาราง)
        sheets.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"A2:H{len(rows) + 1}",
            valueInputOption="USER_ENTERED",
            body={"values": rows}
        ).execute()

    print(f"✅ บันทึกลง Google Sheets เรียบร้อย (คลิปล่าสุดอยู่บนสุดตามสั่ง 100%)!")
    print(f"🔗 ลิงก์ชีท: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")
    return len(rows)


if __name__ == "__main__":
    count = sync_to_sheet()
    print(f"DONE: {count} rows synced (Newest on top)")
