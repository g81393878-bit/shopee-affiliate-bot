# -*- coding: utf-8 -*-
"""เทสต์หน้าแอดมิน \"🎬 Reels\" — สถานะคิววิดีโอ Reels uploader

- _read_reels_status() อ่าน state จากโฟลเดอร์/ไฟล์จริง (tmp_path)
- /api/admin/reels-status ต้องมี admin cookie ถึงเรียกได้ (401 ไม่มี)
"""
import datetime
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from app.api.admin_dashboard import _read_reels_status
from app.main import app


@pytest.fixture(autouse=True)
def _admin_password(monkeypatch):
    """บังคับ password แอดมินเป็นค่าเทสต์ (กันไปชน CRON_TOKEN จริงใน .env)"""
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "test-admin-pw")
    monkeypatch.delenv("POSTING_SPACING_HOURS", raising=False)
    monkeypatch.delenv("MAX_REELS_PER_DAY", raising=False)


@pytest.fixture()
def client():
    c = TestClient(app)
    r = c.post("/admin/login", data={"password": "test-admin-pw"})
    assert r.status_code == 200, r.text
    return c


def _make_reels_state(tmp_path, with_pending=True):
    """สร้างโฟลเดอร์/ไฟล์ state ของ uploader ใน tmp_path"""
    pending = tmp_path / "pending_videos"
    pending.mkdir()
    (pending / "b_คลิปสอง.mp4").write_bytes(b"x" * 2_000_000)
    if with_pending:
        (pending / "a_คลิปหนึ่ง.mp4").write_bytes(b"y" * 3_000_000)
    posted = tmp_path / "posted"
    posted.mkdir()
    (posted / "done_คลิป.mp4").write_bytes(b"z" * 1_500_000)
    # products.json — a_คลิปหนึ่ง เป็นสินค้า
    (tmp_path / "products.json").write_text(
        '{"a_คลิปหนึ่ง.mp4": {"product_name": "สินค้า A"}}', encoding="utf-8")
    # last post = 2 ชม.ก่อน (spacing 3 ชม. → ยังไม่พร้อม)
    (tmp_path / "last_post_time.txt").write_text(
        str(time.time() - 2 * 3600), encoding="utf-8")
    (tmp_path / "posts_today.txt").write_text(
        f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')} 3",
        encoding="utf-8")
    (tmp_path / "uploader_execution.log").write_text(
        "[2026-01-01T00:00:00+00:00] line1\n[2026-01-01T00:01:00+00:00] line2\n",
        encoding="utf-8")
    return tmp_path


def test_reels_status_reads_queue_and_posted(tmp_path):
    st = _read_reels_status(_make_reels_state(tmp_path))
    # คิวเรียง FIFO (ตามชื่อ) — a ก่อน b
    assert [v["name"] for v in st["queue"]] == ["a_คลิปหนึ่ง.mp4", "b_คลิปสอง.mp4"]
    assert st["queue"][0]["is_product"] is True   # อยู่ใน products.json
    assert st["queue"][1]["is_product"] is False  # ไม่มี → แคปชั่นแนะนำป้าเข็ม
    assert st["queue"][0]["size_mb"] >= 2.0
    assert st["queue"][0]["age_min"] >= 0
    # posted เรียงใหม่สุดก่อน
    assert st["posted"][0]["name"] == "done_คลิป.mp4"
    assert st["posted"][0]["posted_at"] is not None


def test_reels_status_state_pacing_and_daily(tmp_path):
    st = _read_reels_status(_make_reels_state(tmp_path))
    s = st["state"]
    assert s["spacing_hours"] == 3.0
    assert s["max_per_day"] == 30
    assert s["posts_today"] == 3
    # last post 2 ชม.ก่อน, spacing 3 ชม. → ยังไม่พร้อม + เหลือ ~60 นาที
    assert s["pacing_ready"] is False
    assert s["last_posted_at"] is not None
    assert s["next_post_at"] is not None
    assert 0 < s["next_post_in_min"] <= 60
    assert st["log_tail"] == ["[2026-01-01T00:00:00+00:00] line1",
                              "[2026-01-01T00:01:00+00:00] line2"]
    assert st["log_file_exists"] is True


def test_reels_status_ready_when_no_last_post(tmp_path):
    """ไม่มี last_post_time.txt → พร้อมโพสต์ทันที (pacing_ready=True)"""
    root = _make_reels_state(tmp_path)
    (root / "last_post_time.txt").unlink()
    s = _read_reels_status(root)["state"]
    assert s["pacing_ready"] is True
    assert s["last_posted_at"] is None
    assert s["next_post_at"] is None


def test_reels_status_empty_dirs(tmp_path):
    """โฟลเดอร์ว่าง/ไม่มีไฟล์ → คิวว่าง ไม่ crash"""
    s = _read_reels_status(tmp_path)["state"]
    assert _read_reels_status(tmp_path)["queue"] == []
    assert _read_reels_status(tmp_path)["posted"] == []
    assert s["pacing_ready"] is True


def test_reels_status_requires_login():
    c = TestClient(app)
    r = c.get("/api/admin/reels-status")
    assert r.status_code == 401


def test_reels_status_endpoint_ok(client):
    r = client.get("/api/admin/reels-status")
    assert r.status_code == 200
    data = r.json()
    for key in ("queue", "posted", "state", "log_tail", "manual_post"):
        assert key in data
    assert "spacing_hours" in data["state"]
    assert "running" in data["manual_post"]


def test_reels_post_now_requires_login():
    c = TestClient(app)
    assert c.post("/api/admin/reels/post-now").status_code == 401


def test_reels_post_now_no_pending(monkeypatch, tmp_path, client):
    """คิวว่าง → started=False ไม่ spawn uploader (ปลอดภัย ไม่โพสต์จริง)"""
    from app.api import admin_dashboard
    monkeypatch.setattr(admin_dashboard, "_repo_root", lambda: tmp_path)
    r = client.post("/api/admin/reels/post-now")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["started"] is False


def test_reels_post_now_409_when_already_running(monkeypatch, tmp_path, client):
    """กำลังโพสต์อยู่ → 409 (กันกดซ้ำ)"""
    from app.api import admin_dashboard
    (tmp_path / "pending_videos").mkdir()
    (tmp_path / "pending_videos" / "v.mp4").write_bytes(b"x")
    monkeypatch.setattr(admin_dashboard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(admin_dashboard, "_reels_post_running", True)
    r = client.post("/api/admin/reels/post-now")
    assert r.status_code == 409


def test_reels_post_now_starts_thread(monkeypatch, tmp_path, client):
    """มีคลิป + ไม่กำลังโพสต์ → started=True และ spawn thread รัน uploader --force
    (mock subprocess.run กันโพสต์ Facebook จริง)"""
    from app.api import admin_dashboard
    (tmp_path / "pending_videos").mkdir()
    (tmp_path / "pending_videos" / "v.mp4").write_bytes(b"x")
    (tmp_path / "uploader.py").write_text("print('fake uploader')", encoding="utf-8")
    monkeypatch.setattr(admin_dashboard, "_repo_root", lambda: tmp_path)
    calls = {}

    def _fake_run(cmd, **kw):
        calls["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="[OK] posted", stderr="")

    monkeypatch.setattr(admin_dashboard.subprocess, "run", _fake_run)
    r = client.post("/api/admin/reels/post-now")
    assert r.status_code == 200
    assert r.json()["started"] is True
    # รอ thread จบ (สั้นมาก เพราะ mock)
    import time as _t
    for _ in range(50):
        if not admin_dashboard._reels_post_running:
            break
        _t.sleep(0.05)
    assert admin_dashboard._reels_post_running is False
    assert "--force" in calls["cmd"]
    assert any(x.endswith("uploader.py") for x in calls["cmd"])
    assert admin_dashboard._reels_manual_result["exit_code"] == 0
