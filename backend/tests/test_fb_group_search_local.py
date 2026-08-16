# -*- coding: utf-8 -*-
"""Unit tests for Facebook Group Discovery tool (tools/fb_group_search_local.py).

Covers the pure, browser-free helpers only:
- normalize_group_url
- parse_group_card (name / members / public)
- count_buyer_signals / count_seller_signals
- rank_candidates
- load_env_token precedence
"""
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import fb_group_search_local as discover


# ===========================================================================
# normalize_group_url
# ===========================================================================
def test_normalize_numeric_group_url():
    out = discover.normalize_group_url("https://www.facebook.com/groups/123456789/")
    assert out == {"group_id": "123456789", "url": "https://www.facebook.com/groups/123456789/"}


def test_normalize_slug_group_url():
    out = discover.normalize_group_url("https://www.facebook.com/groups/dogreviews/?locale=th_TH")
    assert out["group_id"] == "dogreviews"
    assert out["url"] == "https://www.facebook.com/groups/dogreviews/"


def test_normalize_ignores_non_group_links():
    assert discover.normalize_group_url("https://www.facebook.com/marketplace/item/123") is None
    assert discover.normalize_group_url("https://www.facebook.com/groups/") is None


def test_normalize_skips_special_segments():
    assert discover.normalize_group_url("https://www.facebook.com/groups/123/posts/456") is None
    assert discover.normalize_group_url("https://www.facebook.com/groups/123/permalink/456") is None


def test_normalize_empty():
    assert discover.normalize_group_url("") is None
    assert discover.normalize_group_url(None) is None


# ===========================================================================
# parse_group_card
# ===========================================================================
def test_parse_group_card_public_english_members():
    info = discover.parse_group_card("Cool Gadgets\n12K members\nPublic group")
    assert info["name"] == "Cool Gadgets"
    assert info["public"] is True
    assert info["members"] == 12_000


def test_parse_group_card_private_thai_members():
    info = discover.parse_group_card("กลุ่มแม่และเด็ก\nสมาชิก 5.2 หมื่น คน\nกลุ่มส่วนตัว")
    assert info["name"] == "กลุ่มแม่และเด็ก"
    assert info["public"] is False
    assert info["members"] == 52_000


def test_parse_group_card_lan_members():
    info = discover.parse_group_card("กลุ่มขายของ\nสมาชิก 1.5 ล้าน คน\nกลุ่มสาธารณะ")
    assert info["members"] == 1_500_000
    assert info["public"] is True


def test_parse_group_card_empty():
    info = discover.parse_group_card("")
    assert info["name"] == ""
    assert info["members"] is None
    assert info["public"] is None


# ===========================================================================
# buyer / seller signals
# ===========================================================================
def test_count_buyer_signals():
    text = "อยากได้หูฟังบลูทูธตัดเสียง งบ 500 แนะนำตัวไหนดีครับ"
    assert discover.count_buyer_signals(text) >= 4


def test_count_seller_signals():
    text = "ขายเสื้อผ้าแฟชั่น รับสั่ง สนใจทักแชท พร้อมส่งทั่วประเทศ"
    assert discover.count_seller_signals(text) >= 3


def test_signals_empty():
    assert discover.count_buyer_signals("") == 0
    assert discover.count_seller_signals("") == 0


# ===========================================================================
# rank_candidates
# ===========================================================================
def test_rank_candidates_buyer_first_then_public_then_members():
    cands = [
        {"name": "a", "buyer_signals": 0, "public": True, "members": 100_000},
        {"name": "b", "buyer_signals": 5, "public": False, "members": 1_000},
        {"name": "c", "buyer_signals": 5, "public": True, "members": 5_000},
        {"name": "d", "buyer_signals": 5, "public": True, "members": 50_000},
    ]
    ranked = discover.rank_candidates(cands)
    # buyer 5 มาก่อน buyer 0; กลุ่ม public มาก่อน private; สมาชิกมากก่อน
    assert [c["name"] for c in ranked] == ["d", "c", "b", "a"]


# ===========================================================================
# should_auto_add
# ===========================================================================
def test_should_auto_add_good_group():
    c = {"already_added": False, "scannable": True, "public": True,
         "buyer_signals": 3, "seller_signals": 1}
    assert discover.should_auto_add(c, min_buyer=1) is True


def test_should_auto_add_rejects_seller_group():
    c = {"already_added": False, "scannable": True, "public": True,
         "buyer_signals": 1, "seller_signals": 5}
    assert discover.should_auto_add(c, min_buyer=1) is False


def test_should_auto_add_rejects_not_scannable_or_private():
    not_scannable = {"already_added": False, "scannable": False, "public": True,
                     "buyer_signals": 3, "seller_signals": 0}
    private = {"already_added": False, "scannable": True, "public": False,
               "buyer_signals": 3, "seller_signals": 0}
    already = {"already_added": True, "scannable": True, "public": True,
               "buyer_signals": 3, "seller_signals": 0}
    assert discover.should_auto_add(not_scannable) is False
    assert discover.should_auto_add(private) is False
    assert discover.should_auto_add(already) is False


def test_should_auto_add_respects_min_buyer():
    c = {"already_added": False, "scannable": True, "public": True,
         "buyer_signals": 1, "seller_signals": 0}
    assert discover.should_auto_add(c, min_buyer=2) is False
    assert discover.should_auto_add(c, min_buyer=1) is True


# ===========================================================================
# load_env_token precedence
# ===========================================================================
def test_load_env_token_cli_precedence(monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "env_token")
    assert discover.load_env_token(cli_token="cli_token") == "cli_token"


def test_load_env_token_cron_precedence(monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "cron_val")
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "pw_val")
    assert discover.load_env_token() == "cron_val"


def test_load_env_token_from_file(monkeypatch):
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_DASHBOARD_PASSWORD", raising=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("CRON_TOKEN=file_token_123\n", encoding="utf-8")
        assert discover.load_env_token(env_path=str(env_file)) == "file_token_123"
