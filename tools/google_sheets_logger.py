#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/google_sheets_logger.py
================================
โมดูลบันทึกผลการเผยแพร่วิดีโอลง Google Sheets อัตโนมัติ (24/7 Auto-Logger)
- ลำดับข้อมูล: แทรกแถวใหม่ที่ "แถว 2 (บนสุดใต้หัวตาราง)" เสมอ
- Google Sheet ID: 1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU
- URL: https://docs.google.com/spreadsheets/d/1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU/edit
- Google Drive Folder: Paa Khem Bot & Shopee Affiliate Master Workspace (ID: 1jbNqUdiKf0Zdhk218QT_2yb4q63Vk2rj)
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT_DIR / "tools"
sys.path.insert(0, str(TOOLS_DIR))

logger = logging.getLogger("GoogleSheetsLogger")
SPREADSHEET_ID = os.getenv("BROADCAST_SPREADSHEET_ID", "1cwBMSooT69IBlNrNWwn5FqRV3mi3TA27nQgyyt454dU")
ICT = timezone(timedelta(hours=7))


def log_broadcast_to_sheet(
    title: str,
    category: str,
    tiktok_url: str = "-",
    fb_reel_1: str = "-",
    fb_reel_2: str = "-",
    yt_shorts_url: str = "-",
    status: str = "✅ เผยแพร่สำเร็จ 100%"
) -> bool:
    """บันทึกผลการโพสต์ 1 รายการลง Google Sheets โดยแทรกไว้ที่แถว 2 (บนสุดเสมอ)"""
    try:
        from google_docs_logger import get_credentials
        from googleapiclient.discovery import build

        creds = get_credentials()
        sheets = build("sheets", "v4", credentials=creds)

        # 1. สร้างแถวว่างใหม่ที่ตำแหน่งแถวที่ 2 (index 1 ใน 0-based index)
        # เพื่อดันข้อมูลเก่าลงไปข้างล่าง ให้คลิปล่าสุดอยู่บนสุดเสมอ
        insert_request = {
            "insertDimension": {
                "range": {
                    "sheetId": 0,
                    "dimension": "ROWS",
                    "startIndex": 1,
                    "endIndex": 2
                },
                "inheritFromBefore": False
            }
        }
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [insert_request]}
        ).execute()

        # 2. กรอกข้อมูลคลิปล่าสุดลงในแถวที่ 2 (A2:H2)
        now_ict = datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S")
        row_values = [[
            now_ict,
            title.strip(),
            category.strip(),
            tiktok_url.strip() or "-",
            fb_reel_1.strip() or "-",
            fb_reel_2.strip() or "-",
            yt_shorts_url.strip() or "-",
            status.strip()
        ]]

        sheets.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range="A2:H2",
            valueInputOption="RAW",
            body={"values": row_values}
        ).execute()

        logger.info(f"📊 [Google Sheets] บันทึกผลสำเร็จลงแถวบนสุด: {title[:40]}")
        return True

    except Exception as e:
        logger.warning(f"⚠️ บันทึกลง Google Sheets ไม่สำเร็จ: {e}")
        return False


def log_broadcast_async(**kwargs):
    """บันทึกแบบ Daemon Thread ไม่รบกวนความเร็วของกระบวนการหลัก"""
    import threading
    t = threading.Thread(target=log_broadcast_to_sheet, kwargs=kwargs, daemon=True)
    t.start()


if __name__ == "__main__":
    print("ทดสอบบันทึกแถวใหม่ลงบนสุดของ Google Sheets...")
    ok = log_broadcast_to_sheet(
        title="[ทดสอบระบบ] การเชื่อมต่อ Google Sheets 24/7 ล่าสุดอยู่บนสุด",
        category="ระบบอัตโนมัติ (SYSTEM)",
        tiktok_url="https://www.tiktok.com/@pakhem.review99",
        fb_reel_1="https://www.facebook.com/reel/test1",
        fb_reel_2="https://www.facebook.com/reel/test2",
        yt_shorts_url="https://youtube.com/shorts/test",
        status="✅ ทดสอบสำเร็จ 100%"
    )
    print("ผลการทดสอบ:", ok)
