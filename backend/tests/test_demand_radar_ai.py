# -*- coding: utf-8 -*-
"""Unit tests for AI Intent & Demand Analysis, Product Matching with AI Reasoning,
and Auntie Khem Deal Copy Generation (Milestone 2).

Verifies:
- High demand vs low demand / scam lead classification and threshold check (is_high_demand).
- Thai text normalization, price parsing, and keyword/pain point extraction.
- Product matching with strict link_status=='ok' policy and multi-factor scoring.
- Suggested reasons generation with empirical criteria.
- Auntie Khem persona comment generation with natural affiliate URL placement.
"""
from decimal import Decimal
import pytest
from unittest.mock import MagicMock

from app import models
from app.services.demand_radar_ai import (
    analyze_lead_intent_and_demand,
    generate_auntie_khem_deal_comment,
    is_high_demand,
    parse_post_budget,
    _extract_heuristic_keyword,
    _nfc,
    _strip_garbled,
    _clean_llm_data,
)
from app.services.product_matcher import (
    calculate_product_match_score,
    generate_suggested_reasons,
    match_best_product_for_demand,
)


# --- 1. Test Thai Normalization & Price Parsing ---

def test_thai_nfc_normalization():
    """Test NFC combining characters and Thai Sara Am normalization."""
    # Test decomposed Sara Am (\u0e4d\u0e32) converted to single Sara Am (\u0e33)
    decomposed = "น\u0e49\u0e4d\u0e32แข็ง"
    normalized = _nfc(decomposed)
    assert normalized == "น้ำแข็ง"
    assert "\u0e4d\u0e32" not in normalized

    decomposed2 = "น\u0e4d\u0e32"
    assert _nfc(decomposed2) == "นำ"


def test_strip_garbled_removes_surrogates_and_replacement_chars():
    """Lone surrogates (surrogateescape) + U+FFFD ต้องถูกถอดทิ้งจากคีย์เวิร์ด LLM
    (กัน mojibake ทำให้แมตช์สินค้าไม่เจอ)."""
    dirty = "แ\udc81อ\udc9bทำ\udc84ลิ\udc9b"
    cleaned = _strip_garbled(dirty)
    assert "\udc81" not in cleaned
    assert "\ufffd" not in cleaned
    # เหลือเฉพาะอักขระไทยที่สมบูรณ์ (แ อ ท ำ ล ิ)
    assert cleaned == "แอทำลิ"


def test_clean_llm_data_cleans_string_fields_keeps_numbers():
    out = _clean_llm_data({
        "product_keyword": "หูฟัง\udc9b",
        "detected_category": "อุปกรณ์เสริม\ufffd",
        "pain_points": ["ตัดเสียง\udc84", "ลมแรง"],
        "demand_score": 85,
    })
    assert out["product_keyword"] == "หูฟัง"
    assert out["detected_category"] == "อุปกรณ์เสริม"
    assert out["pain_points"] == ["ตัดเสียง", "ลมแรง"]
    assert out["demand_score"] == 85  # ตัวเลขไม่โดนแตะ


def test_parse_post_budget_formats():
    """Test parsing various Thai price and budget expressions."""
    # Standard numbers
    val1, text1 = parse_post_budget("มีใครแนะนำหูฟังบ้าง งบไม่เกิน 500 บาท")
    assert val1 == 500.0
    assert text1 == "ไม่เกิน 500 บาท"

    # Range
    val2, text2 = parse_post_budget("อยากได้กระติกน้ำ ราคา 300-500")
    assert val2 == 500.0
    assert "300-500" in text2

    # Thai word numbers
    val3, text3 = parse_post_budget("หาซื้อเก้าอี้เพื่อสุขภาพ งบสองพัน")
    assert val3 == 2000.0

    val4, text4 = parse_post_budget("ถุงเท้าวิ่ง ไม่เกินร้อย")
    assert val4 == 100.0

    # Comma formatted
    val5, text5 = parse_post_budget("มองหาเครื่องฟอกอากาศ ราคาไม่เกิน 2,500 บาท")
    assert val5 == 2500.0


# --- 2. Test Demand Analysis & Intent Extraction ---

def test_high_demand_lead_analysis():
    """Test lead with explicit buying intent, budget, and urgency."""
    post_text = "มีใครแนะนำชุดคลุมท้องใส่สบายๆ บ้างคะ งบไม่เกิน 500 บาท ด่วนมากต้องใช้เสาร์นี้"
    result = analyze_lead_intent_and_demand(post_text, author_name="คุณแม่มือใหม่")

    assert result["intent"] in ("recommendation_request", "buy_request")
    assert result["demand_score"] >= 70
    assert is_high_demand(result["demand_score"], threshold=70) is True
    assert result["urgency"] == "high"
    assert result["budget"] == 500.0
    assert "ชุดคลุมท้อง" in result["product_keyword"]
    assert len(result["pain_points"]) > 0
    assert result["reasoning"] is not None


def test_moderate_problem_seeking_lead():
    """Test lead with a problem/need seeking product recommendation."""
    post_text = "พัดลมตัวเก่าพัง อยากได้พัดลมตั้งโต๊ะเงียบๆ ลมแรงๆ มียี่ห้อไหนดีบ้างคะ"
    result = analyze_lead_intent_and_demand(post_text, author_name="สมชาย")

    assert result["demand_score"] >= 70
    assert is_high_demand(result["demand_score"]) is True
    assert "พัดลม" in result["product_keyword"]
    assert result["urgency"] in ("high", "medium")


def test_low_demand_scam_warning_lead():
    """Test post warning about scam/fraud - must have low demand score and no deal trigger."""
    post_text = "ประกาศเตือนภัยการโกงในกลุ่ม ระวังบัญชีนี้อย่าโอนเด็ดขาด โดนโกงมาแล้วหลายคน"
    result = analyze_lead_intent_and_demand(post_text, author_name="แอดมินกลุ่ม")

    assert result["intent"] == "spam_or_warning"
    assert result["demand_score"] < 40
    assert is_high_demand(result["demand_score"], threshold=70) is False
    assert result["product_keyword"] is None or result["demand_score"] < 70


def test_low_demand_secondhand_selling_post():
    """Test user promoting or selling second-hand items."""
    post_text = "ขออนุญาตแอดมินปล่อยเสื้อผ้ามือสอง สภาพดี ส่งต่อราคาเบาๆ สนใจทักแชท"
    result = analyze_lead_intent_and_demand(post_text, author_name="ผู้ขาย")

    assert result["intent"] == "spam_or_warning"
    assert result["demand_score"] < 50
    assert is_high_demand(result["demand_score"], threshold=70) is False


def test_empty_or_blank_post_analysis():
    """Test analysis on empty or whitespace text."""
    result = analyze_lead_intent_and_demand("   ")
    assert result["demand_score"] == 0
    assert is_high_demand(result["demand_score"]) is False


# --- 3. Test Product Matcher & Strict Link Policy ---

def test_product_matcher_strict_link_status_filter(db):
    """Test that ONLY products with link_status == 'ok' are matched."""
    # Clear and insert test products with different link_status
    p_ok = models.Product(
        name="ชุดคลุมท้องผ้าฝ้าย ใส่สบาย",
        category="แฟชั่น",
        price=Decimal("350.00"),
        rating=4.8,
        sales_count=2000,
        commission=Decimal("35.00"),
        affiliate_url="https://shope.ee/ok-link",
        link_status="ok",
        ai_score=85,
    )
    p_dead = models.Product(
        name="ชุดคลุมท้องแฟชั่นเกาหลี ดีลเด็ด",
        category="แฟชั่น",
        price=Decimal("299.00"),
        rating=4.9,
        sales_count=5000,
        commission=Decimal("40.00"),
        affiliate_url="https://shope.ee/dead-link",
        link_status="dead",
        ai_score=95,
    )
    p_unknown = models.Product(
        name="ชุดคลุมท้องราคาประหยัด",
        category="แฟชั่น",
        price=Decimal("250.00"),
        rating=4.7,
        sales_count=1500,
        commission=Decimal("25.00"),
        affiliate_url="https://shope.ee/unknown-link",
        link_status="unknown",
        ai_score=80,
    )
    db.add_all([p_ok, p_dead, p_unknown])
    db.commit()

    match_result = match_best_product_for_demand(db, product_keyword="ชุดคลุมท้อง", budget=500.0)

    assert match_result["best_product"] is not None
    assert match_result["best_product"].id == p_ok.id
    assert match_result["best_product"].link_status == "ok"

    # Ensure no dead/unknown products in candidates
    for cand in match_result["candidates"]:
        assert cand["product"].link_status == "ok"
        assert cand["product"].id != p_dead.id
        assert cand["product"].id != p_unknown.id


def test_product_matcher_budget_alignment(db):
    """Test that products fitting within budget get higher score than over-budget products."""
    p_in_budget = models.Product(
        name="หูฟังไร้สาย TWS ตัดเสียงรบกวน",
        category="หูฟัง",
        price=Decimal("450.00"),
        rating=4.7,
        sales_count=3000,
        commission=Decimal("30.00"),
        affiliate_url="https://shope.ee/earphone-budget",
        link_status="ok",
        ai_score=80,
    )
    p_over_budget = models.Product(
        name="หูฟังไร้สาย Hi-Res Audio รุ่นท็อป",
        category="หูฟัง",
        price=Decimal("1500.00"),
        rating=4.9,
        sales_count=3000,
        commission=Decimal("80.00"),
        affiliate_url="https://shope.ee/earphone-expensive",
        link_status="ok",
        ai_score=90,
    )
    db.add_all([p_in_budget, p_over_budget])
    db.commit()

    score_in = calculate_product_match_score(p_in_budget, keyword="หูฟังไร้สาย", budget=500.0)
    score_over = calculate_product_match_score(p_over_budget, keyword="หูฟังไร้สาย", budget=500.0)

    assert score_in > score_over


def test_suggested_reasons_generation():
    """Test generating structured empirical reasons for product recommendation."""
    product = models.Product(
        name="พัดลมตั้งโต๊ะมินิ ชาร์จ USB",
        category="พัดลม",
        price=Decimal("299.00"),
        rating=4.8,
        sales_count=15000,
        commission=Decimal("25.00"),
        affiliate_url="https://shope.ee/fan-mini",
        link_status="ok",
    )
    reasons = generate_suggested_reasons(product, budget=400.0)

    assert len(reasons) >= 4
    # Check key criteria present in reasons
    reasons_str = " ".join(reasons)
    assert "4.8" in reasons_str or "รีวิว" in reasons_str
    assert "15,000" in reasons_str or "ยอดขาย" in reasons_str
    assert "299.00" in reasons_str
    assert "ประหยัด" in reasons_str or "งบ" in reasons_str
    assert "OK" in reasons_str or "ลิงก์" in reasons_str


# --- 4. Test Auntie Khem Deal Copy Generation ---

def test_auntie_khem_deal_comment_generation():
    """Test creating Auntie Khem style comment copy with natural affiliate link placement."""
    post_text = "มีใครแนะนำชุดคลุมท้องใส่สบายๆ บ้างคะ งบไม่เกิน 500 บาท"
    product_name = "ชุดคลุมท้องผ้าฝ้ายทรงหลวม ใส่สบาย"
    price = 350.0
    rating = 4.8
    sales_count = 2500
    affiliate_url = "https://shope.ee/khem-deal-maternity"
    reasons = [
        "⭐ รีวิวสูง 4.8/5 ดาว จากผู้ใช้จริง มั่นใจได้ในคุณภาพ",
        "🔥 ยอดขายดีสะสมกว่า 2,500 ชิ้น การันตีของดีตรงปก",
        "💰 ราคา 350.00 บาท อยู่ในงบที่ลูกค้าตั้งไว้ (500.00 บาท) ประหยัด 150.00 บาท",
    ]

    comment = generate_auntie_khem_deal_comment(
        post_text=post_text,
        product_name=product_name,
        price=price,
        rating=rating,
        sales_count=sales_count,
        affiliate_url=affiliate_url,
        suggested_reasons=reasons,
    )

    assert isinstance(comment, str)
    assert len(comment) > 20
    assert affiliate_url in comment
    # Auntie Khem tone markers
    assert any(marker in comment for marker in ("จ้ะ", "จ้า", "นะจ๊ะ", "ลูก", "ป้า"))
    assert product_name in comment or "ชุดคลุมท้อง" in comment
