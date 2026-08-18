# -*- coding: utf-8 -*-
"""เทสต์คิวแชร์โพสต์เพจลงกลุ่ม — /api/admin/group-shares/*

- pending: claim งาน + self-heal งานค้าง (บอทตาย)
- status: รายงาน shared/failed/skipped
- list: รายการคิวทั้งหมด
- ไม่มี cookie → 401 (list) / 401 (pending, require_admin_auth)
"""
import datetime

import pytest
from fastapi.testclient import TestClient

from app import models
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


def _seed_task(db, post_url="https://www.facebook.com/123_456", kind="product",
               status="pending"):
    t = models.GroupShareTask(post_url=post_url, kind=kind, status=status)
    db.add(t)
    db.commit()
    return t


def test_pending_claims_and_returns_tasks(client, db):
    """pending → คืนงาน + เปลี่ยนสถานะเป็น claimed (กัน poll ซ้ำ)"""
    _seed_task(db)
    r = client.get("/api/admin/group-shares/pending")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["kind"] == "product"
    assert items[0]["post_url"] == "https://www.facebook.com/123_456"
    task = db.query(models.GroupShareTask).first()
    assert task.status == "claimed"
    assert task.claimed_at is not None


def test_pending_self_heals_stale_claimed(client, db):
    """งานที่ claim ค้างเกิน 30 นาที (บอทตาย) → ปล่อยกลับเป็น pending ให้ poll ใหม่"""
    stale = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=40)
    _seed_task(db, status="claimed")
    db.query(models.GroupShareTask).update({"claimed_at": stale})
    db.commit()
    r = client.get("/api/admin/group-shares/pending")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1  # งานเก่าโดนปล่อยคืน + claim รอบใหม่
    task = db.query(models.GroupShareTask).first()
    assert task.status == "claimed"
    # SQLite คืน naive → เปรียบเทียบกับค่า naive
    assert task.claimed_at > stale.replace(tzinfo=None)


def test_report_status_shared(client, db):
    """บอท local รายงานแชร์สำเร็จ → shared + shared_at"""
    t = _seed_task(db, status="claimed")
    r = client.post(f"/api/admin/group-shares/{t.id}/status",
                    params={"status": "shared", "note": "สำเร็จ 3 กลุ่ม"})
    assert r.status_code == 200
    db.refresh(t)
    assert t.status == "shared"
    assert t.note == "สำเร็จ 3 กลุ่ม"
    assert t.shared_at is not None


def test_report_status_rejects_unknown(client, db):
    """status ไม่ใช่ shared/failed/skipped → 400"""
    t = _seed_task(db)
    r = client.post(f"/api/admin/group-shares/{t.id}/status", params={"status": "wat"})
    assert r.status_code == 400


def test_report_status_404(client, db):
    r = client.post("/api/admin/group-shares/999999/status", params={"status": "shared"})
    assert r.status_code == 404


def test_list_filters_by_status(client, db):
    _seed_task(db, post_url="https://www.facebook.com/1", kind="product", status="shared")
    _seed_task(db, post_url="https://www.facebook.com/2", kind="intro", status="pending")
    r = client.get("/api/admin/group-shares", params={"status": "pending"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["kind"] == "intro"
    assert data["items"][0]["post_url"] == "https://www.facebook.com/2"


def test_requires_admin_cookie():
    """ไม่มี cookie → 401 ทั้ง list และ pending"""
    c = TestClient(app)
    assert c.get("/api/admin/group-shares").status_code == 401
    assert c.get("/api/admin/group-shares/pending").status_code == 401
    assert c.post("/api/admin/group-shares/1/status",
                  params={"status": "shared"}).status_code == 401
