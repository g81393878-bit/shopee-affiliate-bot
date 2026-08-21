"""เทสต์แจ้งเตือนเจ้าของ Reels (uploader.py notify_reels_issues) — กันโพสต์หยุดเงียบ ๆ

- คิวว่าง → แจ้ง 1 ครั้ง/วัน (state file กันสแปม)
- โพสต์ล้ม ≥ 2 ครั้งติด → แจ้ง 1 ครั้งต่อรอบ; สำเร็จ = รีเซ็ตนับ
- dry-run ไม่แจ้ง · _notify_owner best-effort (token mock/ไม่มี = ข้ามไม่ crash)
ไม่แตะ LINE จริง (mock _notify_owner / ใช้ token mock)
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UPLOADER = ROOT / "uploader.py"


def _load_uploader():
    spec = importlib.util.spec_from_file_location("uploader_under_test", UPLOADER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def up(tmp_path, monkeypatch):
    """uploader module ชี้ state/cิวไป tmp_path + mock _notify_owner (ไม่ยิง LINE จริง)"""
    mod = _load_uploader()
    monkeypatch.setattr(mod, "NOTIFY_STATE_FILE", tmp_path / ".reels_notify_state.json")
    mod.PENDING_DIR = tmp_path / "pending_videos"
    mod.PENDING_DIR.mkdir()
    sent = []
    real_notify = mod._notify_owner
    monkeypatch.setattr(mod, "_notify_owner", lambda text: sent.append(text) or True)
    mod.sent = sent
    mod.real_notify_owner = real_notify  # เทสต์ที่อยากทดสอบตัวจริงใช้ตัวนี้
    return mod


def _add_video(up, name="v.mp4"):
    (up.PENDING_DIR / name).write_bytes(b"x" * 100)


def test_empty_queue_notifies_once_per_day(up):
    """คิวว่าง → แจ้งทันที; รอบถัดไปวันเดียวกัน → ไม่แจ้งซ้ำ"""
    up.notify_reels_issues(0)
    assert len(up.sent) == 1
    assert "คิว Reels ว่าง" in up.sent[0]
    # รอบถัดไป (ชม.ถัดไป — Task Scheduler) วันเดียวกัน → ไม่แจ้งซ้ำ
    up.notify_reels_issues(0)
    assert len(up.sent) == 1
    # วันใหม่ → แจ้งได้อีก
    state = up._load_notify_state()
    state["last_empty_notified_date"] = "2000-01-01"
    up._save_notify_state(state)
    up.notify_reels_issues(0)
    assert len(up.sent) == 2


def test_failure_notifies_at_2_consecutive(up):
    """ล้ม 1 ครั้งยังไม่แจ้ง; ล้ม 2 ครั้งติด → แจ้ง; ครั้งที่ 3 (streak 3) ไม่แจ้งซ้ำ"""
    _add_video(up)
    up.notify_reels_issues(1)
    assert up.sent == []  # 1 ครั้ง ยังไม่ถึงเกณฑ์
    up.notify_reels_issues(1)
    assert len(up.sent) == 1
    assert "โพสต์ล้ม 2 ครั้งติด" in up.sent[0]
    up.notify_reels_issues(1)  # streak 3 — ไม่แจ้งซ้ำ (แจ้งแล้วในรอบนี้)
    assert len(up.sent) == 1


def test_success_resets_failure_streak(up):
    """สำเร็จ → นับล้มรีเซ็ต; ล้มอีก 2 รอบต้องแจ้งใหม่"""
    _add_video(up)
    up.notify_reels_issues(1)
    up.notify_reels_issues(1)
    assert len(up.sent) == 1
    up.notify_reels_issues(0)  # สำเร็จ
    up.notify_reels_issues(1)  # ล้มรอบแรกของรอบใหม่
    assert len(up.sent) == 1  # ยังไม่แจ้ง (streak ใหม่ = 1)
    up.notify_reels_issues(1)
    assert len(up.sent) == 2  # streak ใหม่ถึง 2 → แจ้ง


def test_dry_run_never_notifies(up):
    up.notify_reels_issues(0, dry_run=True)
    up.notify_reels_issues(1, dry_run=True)
    assert up.sent == []


def test_notify_owner_skips_without_real_token(up, monkeypatch):
    """token ไม่ตั้ง / เป็น mock → ข้าม ไม่ crash (best-effort, ไม่ยิง LINE จริง)"""
    real = up.real_notify_owner
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    assert real("test") is False
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "mock-token")
    assert real("test") is False
