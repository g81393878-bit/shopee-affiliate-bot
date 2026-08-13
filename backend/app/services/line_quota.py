# -*- coding: utf-8 -*-
"""
LINE push quota — เช็ค + แจ้งแอดมินเมื่อเหลือน้อย
================================================
LINE ตอบแชท (reply) ไม่นับ quota แต่ push (ต้อนรับแอดเพื่อน / แจ้งราคาลง /
re-engage / แคมเปญ / รายงานประจำวัน) นับตามแผนรายเดือน (แผนฟรี ~500 ข้อความ/เดือน)

- quota_left(): จำนวน push ที่เหลือในเดือนนี้ (None = ตรวจไม่ได้:
  ไม่มี token / mock / error / แผนไม่จำกัด)
- push_guard(db): ควร push ต่อไหม?
    * เหลือ <= 0         → คืน False (บล็อก push กัน LINE error)
    * เหลือ <= warn_left → แจ้งแอดมินทาง LINE (dedupe 1 ครั้ง/24 ชม. ผ่านตาราง
                            campaign_logs — ไม่ต้องสร้างตารางใหม่) แล้วยัง push ต่อ
    * ตรวจไม่ได้         → คืน True (ไม่บล็อกชีวิตปกติตอน mock/dev)
- ตั้งค่า: env PUSH_QUOTA_WARN_LEFT (default 30) — เหลือต่ำกว่านี้แล้วแจ้งเตือน
"""
import datetime
import logging
import os

import requests

logger = logging.getLogger(__name__)

LINE_QUOTA_URL = "https://api.line.me/v2/bot/message/quota"
WARN_CATEGORY = "_quota"  # เก็บใน campaign_logs (ไม่มีตารางใหม่ ไม่ต้อง migration)


def quota_info() -> dict | None:
    """ข้อมูล quota push เดือนนี้: {limit, used, remaining} — None ถ้าตรวจไม่ได้
    (ไม่มี token / mock / error / แผนไม่จำกัด type=none)"""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token or "mock" in token.lower():
        return None
    headers = {"Authorization": "Bearer " + token}
    try:
        quota = requests.get(LINE_QUOTA_URL, headers=headers, timeout=5).json()
        consumption = requests.get(LINE_QUOTA_URL + "/consumption", headers=headers, timeout=5).json()
        if quota.get("type") != "limited":  # type == "none" = แผนไม่จำกัด
            return None
        limit, used = quota.get("value"), consumption.get("totalUsage")
        if limit is None or used is None:
            return None
        limit, used = int(limit), int(used)
        return {"limit": limit, "used": used, "remaining": limit - used}
    except Exception as e:  # LINE error / network — ปล่อยผ่าน อย่าทำให้บอทเดี้ยงเพราะเช็ค quota
        logger.warning("LINE quota check failed: %s", e)
        return None


def quota_left() -> int | None:
    """push ข้อความที่เหลือในเดือนนี้ — None ถ้าตรวจไม่ได้"""
    info = quota_info()
    return info["remaining"] if info else None


def push_guard(db, warn_left: int = 30, warn_every_hours: int = 24) -> bool:
    """ควร push ต่อไหม? (บล็อกเมื่อ quota หมด; แจ้งแอดมินเมื่อเหลือน้อย)

    warn_left ตั้งค่าได้ผ่าน env PUSH_QUOTA_WARN_LEFT (default 30 ข้อความ)
    """
    env_warn = os.getenv("PUSH_QUOTA_WARN_LEFT", "")
    if env_warn.isdigit():
        warn_left = int(env_warn)
    left = quota_left()
    if left is None:
        return True
    if left <= 0:
        logger.warning("LINE push quota หมด (%d) — ข้าม push", left)
        return False
    if left <= warn_left:
        _warn_admin(db, left, warn_every_hours)
    return True


def _warn_admin(db, left: int, every_hours: int) -> None:
    """แจ้งแอดมิน 1 ครั้ง/ทุก every_hours ชม. (dedupe ผ่าน campaign_logs category='_quota')"""
    from app import models
    from linebot import LineBotApi
    from linebot.models import TextSendMessage

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=every_hours)
    recent = (db.query(models.CampaignLog)
                 .filter(models.CampaignLog.category == WARN_CATEGORY,
                         models.CampaignLog.created_at >= cutoff)
                 .first())
    if recent:
        return  # เพิ่งเตือนไปแล้ว
    admin = os.getenv("ADMIN_LINE_USER_ID", "Uc88eb3896b0e4bcc5fbaa9b78ac1294e")
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    text = (f"⚠️ LINE push quota เหลือ {left} ข้อความในเดือนนี้\\n\\n"
            "push (ต้อนรับลูกค้าใหม่ / แจ้งราคาลง / re-engage / รายงาน) "
            "ใกล้เต็ม quota แผนฟรีแล้ว — ตรวจการใช้งานที่ LINE OA Manager "
            "หรืออัปเกรด Light Plan (~900฿/เดือน, push ฟรี 5,000) "
            "ก่อน quota หมด ไม่งั้นฟีเจอร์แจ้งเตือนจะเงียบไป")
    try:
        if token and "mock" not in token.lower():
            LineBotApi(token).push_message(admin, TextSendMessage(text=text))
        db.add(models.CampaignLog(category=WARN_CATEGORY, recipients=left, status="warn"))
        db.commit()
        logger.warning("แจ้งแอดมินแล้ว: LINE push quota เหลือ %d", left)
    except Exception as e:
        logger.warning("quota warn push failed: %s", e)
