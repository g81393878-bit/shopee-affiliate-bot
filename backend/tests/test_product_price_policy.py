# -*- coding: utf-8 -*-
"""Public product copy must never repeat a potentially stale Shopee price."""

from app.services.product_price_policy import (
    LATEST_PRICE_TEXT,
    sanitize_public_product_script,
    sanitize_public_product_text,
)


def test_sanitizes_common_thai_price_and_discount_formats():
    samples = (
        "ราคา 488 บาท พร้อมส่ง",
        "วันนี้เพียง ฿488 รีบซื้อ",
        "เริ่มต้น 488฿ เท่านั้น",
        "โปรโมชั่นลด 20% วันนี้",
        "Price 488 Baht",
        "product discount 20%",
    )
    for source in samples:
        cleaned = sanitize_public_product_text(source)
        assert LATEST_PRICE_TEXT in cleaned
        assert "488" not in cleaned
        assert "20%" not in cleaned


def test_preserves_non_price_product_facts():
    source = "รุ่น 16 นิ้ว คะแนน 4.8 ขายแล้ว 2,500 ชิ้น"
    assert sanitize_public_product_text(source) == source


def test_sanitizes_all_public_script_fields_but_keeps_hashtags():
    data = {
        "hook": "ของดีราคา 299 บาท",
        "caption": "โปรลด 15%",
        "cta": "ซื้อเพียง ฿299",
        "hashtags": ["ของดี", "Shopee"],
    }
    result = sanitize_public_product_script(data)
    assert all("299" not in result[key] for key in ("hook", "caption", "cta"))
    assert result["hashtags"] == data["hashtags"]
