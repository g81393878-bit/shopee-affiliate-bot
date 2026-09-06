# -*- coding: utf-8 -*-
"""Unit tests for TikTok-Led Unified Broadcast Architecture in tools/system_runner.py."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
import sys
sys.path.insert(0, str(ROOT_DIR / "tools"))
sys.path.insert(0, str(ROOT_DIR / "reels_uploader"))

import system_runner


def test_execute_unified_broadcast_no_accounts(monkeypatch):
    """ทดสอบกรณีไม่พบบัญชี TikTok ในระบบ"""
    monkeypatch.setattr("tiktok_studio_uploader.get_available_tiktok_accounts", lambda: [])
    res = system_runner.execute_unified_broadcast(force=False)
    assert res["success"] is False
    assert "No TikTok accounts" in res["error"]


def test_execute_unified_broadcast_daily_quota_reached(monkeypatch, tmp_path):
    """ทดสอบกรณีทุกช่องโพสต์ครบโควตา 8 คลิป/วันแล้ว"""
    mock_acc1 = tmp_path / "tiktok_cookies.json"
    mock_acc1.write_text("{}", encoding="utf-8")
    
    mock_tracker = tmp_path / "daily_tiktok_counts.json"
    today = system_runner.datetime.now(system_runner.ICT).strftime("%Y-%m-%d")
    mock_tracker.write_text(json.dumps({
        "date": today,
        "counts": {"tiktok_cookies": 8}
    }), encoding="utf-8")

    monkeypatch.setattr(system_runner, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr("tiktok_studio_uploader.get_available_tiktok_accounts", lambda: [mock_acc1])
    
    res = system_runner.execute_unified_broadcast(force=False)
    assert res["success"] is False
    assert "Daily quota reached" in res["error"]


def test_execute_unified_broadcast_sync_execution(monkeypatch, tmp_path):
    """ทดสอบการซิงค์วิดีโอตัวเดียวกันไปยัง TikTok, Facebook Reels, และ YouTube Shorts"""
    mock_acc = tmp_path / "tiktok_cookies.json"
    mock_acc.write_text("{}", encoding="utf-8")
    
    pending_dir = tmp_path / "pending_videos"
    pending_dir.mkdir(parents=True, exist_ok=True)
    cand_file = pending_dir / "test_video_123.mp4"
    cand_file.write_text("fake video content", encoding="utf-8")
    
    monkeypatch.setattr(system_runner, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr(system_runner, "REELS_DIR", tmp_path)
    monkeypatch.setattr("tiktok_studio_uploader.get_available_tiktok_accounts", lambda: [mock_acc])
    
    # Mock TikTok upload
    mock_tt_upload = MagicMock(return_value={"success": True, "title": "Test Reel"})
    monkeypatch.setattr("tiktok_studio_uploader.upload_video_via_web", mock_tt_upload)
    
    # Mock Facebook/YouTube uploader.post_next
    mock_uploader_post_next = MagicMock(return_value=0)
    monkeypatch.setattr("uploader.post_next", mock_uploader_post_next)
    monkeypatch.setattr("uploader.get_posted_titles", lambda: set())
    monkeypatch.setattr("uploader.list_pending", lambda: [])
    monkeypatch.setattr("uploader.build_caption", lambda info: "แคปชั่นทดสอบ")
    
    # Mock Telegram notify
    mock_tg = MagicMock()
    monkeypatch.setattr("telegram_notifier.send_telegram_notification", mock_tg)
    
    res = system_runner.execute_unified_broadcast(custom_video=cand_file, force=True)
    
    assert res["success"] is True
    assert res["video"] == "test_video_123.mp4"
    
    # ยืนยันว่า TikTok upload ถูกเรียกด้วย candidate video ตัวนี้
    mock_tt_upload.assert_called_once()
    assert mock_tt_upload.call_args[0][0] == cand_file
    
    # ยืนยันว่า uploader.post_next ถูกเรียกด้วย custom_video เป็น path ของ candidate video ตัวเดียวกัน 100%
    mock_uploader_post_next.assert_called_once()
    assert mock_uploader_post_next.call_args[1]["custom_video"] == str(cand_file)
    assert mock_uploader_post_next.call_args[1]["force"] is True
    
    # ยืนยันว่า Telegram แจ้งเตือนสรุปครบทุกแพลตฟอร์ม
    mock_tg.assert_called_once()
    assert "TikTok-Led Unified Broadcast สำเร็จ" in mock_tg.call_args[0][0]
