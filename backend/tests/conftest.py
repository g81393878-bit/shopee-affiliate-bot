# -*- coding: utf-8 -*-
"""pytest fixtures สำหรับเทสต์บอทป้าเข็ม (LINE bot logic) แบบ offline.

- สร้าง SQLite ชั่วคราว + seed สินค้าชุดเล็ก deterministic (ไม่แตะ production)
- mock ทุกขอบเครือข่าย: LINE reply/push/get_profile, push_guard, web_search
- fixture `sim` จำลองลูกค้าส่งข้อความ 1 ข้อความแล้วคืน intent/preview/owner_pushes
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent  # backend/
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "app"))

# ตั้ง env ก่อน import app (config.py load_dotenv ไม่ override env ที่มีอยู่แล้ว)
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = "fake_token_for_test"  # ต้องไม่มีคำว่า mock
os.environ["LINE_CHANNEL_SECRET"] = "fake_secret_for_test"
os.environ["SHEET_WEBHOOK_URL"] = ""
os.environ["ADMIN_LINE_USER_ID"] = "U_test_owner"

import pytest  # noqa: E402

from app.db import Base, engine, SessionLocal  # noqa: E402
from app import models  # noqa: E402
import app.api.line_bot as lb  # noqa: E402


# (name, category, price, sales_count, ai_score, days_ago, commission) — ชุดเล็กครอบคลุมหมวดที่เทสต์
SEED = [
    ("หูฟังบลูทูธไร้สาย รุ่นโปร", "หูฟัง", 250, 5000, 90, 60, 10),
    ("หูฟังเกมมิ่ง RGB", "หูฟัง", 350, 5000, 80, 60, 10),
    ("กระติกน้ำเก็บความเย็น 1 ลิตร", "แก้วน้ำ", 299, 5000, 85, 60, 10),
    ("แก้วสแตนเลส 316 เก็บความเย็น", "แก้วน้ำ", 150, 5000, 70, 60, 10),
    ("พัดลมตั้งโต๊ะ 16 นิ้ว", "พัดลม", 450, 5000, 75, 60, 10),
    ("หม้อหุงข้าว 1 ลิตร อเนกประสงค์", "เครื่องใช้ไฟฟ้า", 800, 5000, 78, 60, 10),
    ("เครื่องฟอกอากาศ HEPA กรองฝุ่น", "เครื่องใช้ไฟฟ้า", 2500, 5000, 88, 60, 10),
    # ยอดขาย/คอมต่างจากตัวอื่น → ใช้เทสต์ fact "ขายดีกว่า/คอมสูงกว่า" ในการ์ดเทียบ
    ("ของเล่นแมว ไม้ตกแมว ขนนก", "สัตว์เลี้ยง", 99, 12000, 65, 60, 25),
    ("น้ำยาย้อมผม STYLE FIT ครีมเปลี่ยนสีผม", "ความงาม", 120, 5000, 60, 60, 10),
    ("เสื้อกันแดด แขนยาว UPF50+", "แฟชั่น", 300, 5000, 66, 60, 10),
    # ใหม่ + ยอดขายต่ำกว่าเกณฑ์ → ใช้เทสต์ fallback "ของใหม่"
    ("กล่องสุ่มอาร์ตทอย Labubu ของสะสม", "ของสะสม", 500, 100, 40, 2, 10),
]


@pytest.fixture(scope="session", autouse=True)
def _seed_products():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        for name, cat, price, sales, score, days, commission in SEED:
            db.add(models.Product(
                name=name, category=cat, price=price, rating=4.5,
                sales_count=sales, commission=commission,
                affiliate_url="https://shope.ee/test",
                link_status="ok", ai_score=score,
                created_at=now - timedelta(days=days),
            ))
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture(autouse=True)
def db():
    """session สด + ล้างสถานะในหน่วยความจำ/ตารางลูกค้าระหว่างแต่ละเทสต์"""
    lb._last_escalate.clear()
    lb._pending_question.clear()
    s = SessionLocal()
    for m in (models.ChatLog, models.UserPreference, models.User, models.CampaignLog):
        s.query(m).delete(synchronize_session=False)
    s.commit()
    yield s
    s.close()


class _Profile:
    def __init__(self, name):
        self.display_name = name


class _Event:
    def __init__(self, uid, text):
        self.message = type("M", (), {"text": text})()
        self.source = type("S", (), {"user_id": uid})()
        self.reply_token = f"rt_{uid}"


def _preview(messages):
    msgs = messages if isinstance(messages, list) else [messages]
    parts = []
    for m in msgs:
        t = getattr(m, "text", None)
        parts.append(t if t else (getattr(m, "alt_text", "") or f"<{type(m).__name__}>"))
    return " | ".join(p for p in parts if p)


class Simulator:
    """จำลองลูกค้าส่งข้อความ → .send(uid, text) คืน {intent, preview, owner_pushes}"""
    def __init__(self, db, owner_uid):
        self.db = db
        self.owner_uid = owner_uid
        self.replies = []
        self.pushes = []

    def send(self, uid, text):
        self.replies.clear()
        self.pushes.clear()
        lb.message_text(_Event(uid, text))
        # intent อ่านจาก chat_logs (คำสั่งลบข้อมูลไม่ log → คืน 'delete')
        row = (self.db.query(models.ChatLog)
                 .filter(models.ChatLog.line_user_id == uid)
                 .order_by(models.ChatLog.id.desc()).first())
        return {
            "intent": row.intent if row else "delete",
            "preview": self.replies[0] if self.replies else "",
            "owner_pushes": list(self.pushes),
        }


@pytest.fixture()
def sim(monkeypatch, db):
    s = Simulator(db, lb.ADMIN_LINE_USER_ID)
    monkeypatch.setattr(lb.line_bot_api, "reply_message",
                        lambda token, msgs: s.replies.append(_preview(msgs)))
    monkeypatch.setattr(lb.line_bot_api, "push_message",
                        lambda uid, msgs: s.pushes.append(_preview(msgs)))
    monkeypatch.setattr(lb.line_bot_api, "get_profile",
                        lambda uid: _Profile(f"คุณ {uid[-4:]}"))
    monkeypatch.setattr(lb, "push_guard", lambda d: True)
    monkeypatch.setattr(lb, "web_search_answer",
                        lambda q, *a, **k: {"text": "🔍 ป้าเข็มหาข้อมูลมาให้แล้วจ๊ะ:\n(คำตอบจำลอง)",
                                            "images": []})
    return s
