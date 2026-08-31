# -*- coding: utf-8 -*-
"""Shared policy for public Shopee product copy.

Catalog prices help with search and ranking, but are not live quotes. The final
amount can change by variant, voucher and promotion, so public copy must direct
customers to Shopee instead of repeating a potentially stale number.
"""

import re


LATEST_PRICE_TEXT = "ดูราคาล่าสุดในลิงก์ Shopee"

_PUBLIC_PRICE_PATTERNS = (
    re.compile(
        r"(?:(?:ราคา(?:ปกติ|พิเศษ|โปรโมชั่น|โปร|เริ่มต้น|เพียง|แค่)?|price)\s*[:：-]?\s*)?"
        r"(?:เพียง|แค่|เริ่มต้น)?\s*฿\s*\d[\d,.]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:(?:ราคา(?:ปกติ|พิเศษ|โปรโมชั่น|โปร|เริ่มต้น|เพียง|แค่)?|price)\s*[:：-]?\s*)?"
        r"(?:เพียง|แค่|เริ่มต้น)?\s*\d[\d,.]*\s*(?:บาท|฿|บ\.|baht)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:ราคา(?:ปกติ|พิเศษ|โปรโมชั่น|โปร|เริ่มต้น|เพียง|แค่)?|price)\s*[:：-]?\s*\d[\d,.]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:(?:โปร(?:โมชั่น)?|promotion)\s*)?(?:ลด|ส่วนลด|discount)\s*\d+(?:\.\d+)?\s*%",
        re.IGNORECASE,
    ),
)


def sanitize_public_product_text(text: str) -> str:
    """Replace exact product-price claims with a truthful Shopee CTA.

    Apply only to product promotional copy. Service/package prices and payment
    records are intentionally outside this policy.
    """
    cleaned = str(text or "")
    for pattern in _PUBLIC_PRICE_PATTERNS:
        cleaned = pattern.sub(LATEST_PRICE_TEXT, cleaned)
    cleaned = re.sub(
        rf"(?:{re.escape(LATEST_PRICE_TEXT)}[\s,·|/\-]*){{2,}}",
        LATEST_PRICE_TEXT + " ",
        cleaned,
    )
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;!?])", r"\1", cleaned)
    return cleaned.strip()


def sanitize_public_product_script(data: dict) -> dict:
    """Sanitize every public text field returned by an LLM product script."""
    result = dict(data or {})
    for key in ("hook", "problem", "solution", "cta", "caption", "title", "thumbnail_prompt"):
        if key in result:
            result[key] = sanitize_public_product_text(result[key])
    return result
