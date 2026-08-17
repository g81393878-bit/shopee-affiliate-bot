# -*- coding: utf-8 -*-
"""เทสต์หน้าแอดมิน \"💰 สลิป\" — รายการสั่งซื้อบอท + รูปสลิป (ใช้ admin cookie)

- /api/admin/purchases ต้องคืนลูกค้า/แพ็กเกจ/ยอด OCR/สถานะ/slip_id
- /api/admin/slips/{id}/image เสิร์ฟรูปสลิปได้ (ต้อง login)
- ไม่มี cookie → 401
"""
import datetime

import pytest
from fastapi.testclient import TestClient

from app import models
from app.db import SessionLocal
from app.main import app


@pytest.fixture(autouse=True)
def _admin_password(monkeypatch):
    """บังคับ password แอดมินเป็นค่าเทสต์ (กันไปชน CRON_TOKEN จริงใน .env)"""
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "test-admin-pw")


@pytest.fixture()
def client():
    c = TestClient(app)
    r = c.post("/admin/login", data={"password": "test-admin-pw"})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture()
def seed_purchase(db):
    now = datetime.datetime.now(datetime.timezone.utc)
    u = models.User(name="ลูกค้าทดสอบ", line_user_id="U_slip_cust")
    db.add(u)
    p = models.BotPurchase(line_user_id="U_slip_cust", package_key="lean",
                           status="paid_pending", amount="490.00", ref_no="REF999",
                           paid_at=now)
    db.add(p)
    db.flush()
    slip = models.BotPurchaseSlip(line_user_id="U_slip_cust",
                                  content=b"\x89PNG fake-slip-bytes",
                                  content_type="image/png", size_bytes=18)
    db.add(slip)
    db.commit()
    return p, slip


def test_purchases_lists_slip_with_customer(client, db, seed_purchase):
    p, slip = seed_purchase
    r = client.get("/api/admin/purchases")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    row = next((x for x in data["items"] if x["id"] == p.id), None)
    assert row is not None
    assert row["customer"] == "ลูกค้าทดสอบ"
    assert row["line_user_id"] == "U_slip_cust"
    assert row["package"] == "🟡 Lean"
    assert row["status"] == "paid_pending"
    assert row["status_label"] == "รอยืนยัน"
    assert row["amount"] == "490.00"
    assert row["ref_no"] == "REF999"
    assert row["slip_id"] == slip.id
    assert row["slip_size_bytes"] == 18


def test_purchases_filter_by_status(client, db, seed_purchase):
    p, _ = seed_purchase
    r = client.get("/api/admin/purchases", params={"status": "confirmed"})
    assert all(x["status"] == "confirmed" for x in r.json()["items"])
    r2 = client.get("/api/admin/purchases", params={"status": "paid_pending"})
    assert any(x["id"] == p.id for x in r2.json()["items"])


def test_slip_image_served_after_login(client, db, seed_purchase):
    _, slip = seed_purchase
    r = client.get(f"/api/admin/slips/{slip.id}/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == b"\x89PNG fake-slip-bytes"


def test_slip_image_requires_login(db, seed_purchase):
    c = TestClient(app)
    _, slip = seed_purchase
    r = c.get(f"/api/admin/slips/{slip.id}/image")
    assert r.status_code == 401
    r2 = c.get("/api/admin/purchases")
    assert r2.status_code == 401


def test_slip_image_unknown_404(client, db):
    r = client.get("/api/admin/slips/999999/image")
    assert r.status_code == 404
