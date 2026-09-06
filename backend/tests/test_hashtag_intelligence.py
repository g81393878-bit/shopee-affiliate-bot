# -*- coding: utf-8 -*-
"""backend/tests/test_hashtag_intelligence.py — ทดสอบระบบสกัดแฮชแท็กเฉพาะสื่อจากร่องรอยดิจิทัล"""
import pytest
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = ROOT_DIR / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from hashtag_intelligence import (
    sanitize_tag,
    extract_keywords_from_title,
    generate_platform_hashtags,
    DEFAULT_CATEGORY_TAGS
)


def test_sanitize_tag_removes_prices():
    """ต้องกำจัดคำเกี่ยวกับราคาและตัวเลขราคาทิ้ง 100% ตาม Strict No-Price Policy"""
    assert sanitize_tag("ราคา 199 บาท") == ""
    assert sanitize_tag("ของแท้ราคาถูก") == ""
    assert sanitize_tag("ลดราคาพิเศษ") == ""
    assert sanitize_tag("350บาท") == ""
    assert sanitize_tag("จัดพอร์ต") == "#จัดพอร์ต"
    assert sanitize_tag("#ทริคดีๆ") == "#ทริคดีๆ"


def test_extract_keywords_from_title():
    """ต้องสกัดคีย์เวิร์ดภาษาไทยที่มีความหมายได้ ไม่ติดคำเชื่อม"""
    title = "วิธีจัดพอร์ตกระจายความเสี่ยงสำหรับมือใหม่"
    kws = extract_keywords_from_title(title, limit=3)
    assert len(kws) > 0
    for kw in kws:
        assert kw.startswith("#")
        assert "ราคา" not in kw


def test_tiktok_hashtag_rule_3_to_5_tags():
    """TikTok ต้องจำกัดจำนวนแท็กไว้ระหว่าง 3 ถึง 5 แท็กเท่านั้น และต้องมี #ป้าเข็มรีวิว"""
    res = generate_platform_hashtags("จัดพอร์ตกระจายความเสี่ยง", category="WORK_PRODUCTIVITY")
    tiktok_tags = res["tiktok"].split()
    assert 3 <= len(tiktok_tags) <= 5
    assert "#ป้าเข็มรีวิว" in tiktok_tags
    assert "#TikTokUni" in tiktok_tags or "#เทรนด์วันนี้" in tiktok_tags


def test_youtube_shorts_hashtag_rule():
    """YouTube Shorts ต้องมี #Shorts นำหน้าเสมอ"""
    res = generate_platform_hashtags("จัดพอร์ตกระจายความเสี่ยง", category="WORK_PRODUCTIVITY")
    yt_tags = res["youtube"].split()
    assert yt_tags[0] == "#Shorts"
    assert len(yt_tags) >= 3


def test_facebook_reels_hashtag_rule():
    """Facebook Reels ต้องมีแท็กคอมมูนิตี้คนไทยกว้าง (#ของดีบอกต่อ, #ถ้าไม่คุ้มป้าบอกให้)"""
    res = generate_platform_hashtags("หม้อทอดไร้น้ำมัน", category="เครื่องครัว & ของกินของใช้", is_product=True)
    fb_tags = res["facebook"].split()
    assert "#ของดีบอกต่อ" in fb_tags
    assert "#ถ้าไม่คุ้มป้าบอกให้" in fb_tags
    assert len(fb_tags) >= 3


def test_all_categories_have_valid_structure():
    """ตรวจสอบว่าทุกหมวดหมู่มีโครงสร้าง fallback ครบทั้ง 3 แพลตฟอร์ม"""
    for cat, platforms in DEFAULT_CATEGORY_TAGS.items():
        assert "tiktok" in platforms
        assert "youtube" in platforms
        assert "facebook" in platforms
        assert any(t == "#Shorts" for t in platforms["youtube"])
        assert any("ป้าเข็ม" in t for t in platforms["tiktok"])
