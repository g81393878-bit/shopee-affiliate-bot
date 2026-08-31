# -*- coding: utf-8 -*-
"""Regression tests for truthful, non-stale prices in LINE product cards."""

import json

from app import models
from app.api.line_bot import compare_flex_message
from app.services.product_cards import product_cards_message


def _all_text(value):
    if not isinstance(value, (dict, list, tuple)):
        rendered = str(value)
        if rendered.lstrip().startswith(("{", "[")):
            try:
                return _all_text(json.loads(rendered))
            except json.JSONDecodeError:
                pass
        return rendered
    if isinstance(value, dict):
        return " | ".join(_all_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " | ".join(_all_text(item) for item in value)


def test_product_price_is_hidden_in_customer_and_owner_cards(db):
    product = db.query(models.Product).filter(models.Product.price == 250).first()
    user = models.User(line_user_id="U_price_card", name="Price Card Test")

    for is_owner in (False, True):
        message = product_cards_message(db, user, [product], is_owner=is_owner)
        text = _all_text(message.contents)

        assert "฿250" not in text
        assert "เริ่มต้น" not in text
        assert "ราคาขึ้นกับตัวเลือกและโปรโมชัน" in text
        assert "ดูราคาล่าสุดใน Shopee" in text


def test_owner_card_labels_database_timestamp_as_catalog_data(db):
    product = db.query(models.Product).first()
    product.price_checked_at = product.created_at
    user = models.User(line_user_id="U_owner_price_card", name="Owner Card Test")

    message = product_cards_message(db, user, [product], is_owner=True)
    text = _all_text(message.contents)

    assert "ข้อมูลคลังอัปเดตล่าสุด" in text
    assert "ราคาอัปเดตล่าสุด" not in text


def test_price_drop_badge_does_not_publish_percentage(db):
    product = db.query(models.Product).first()
    user = models.User(line_user_id="U_drop_card", name="Drop Card Test")
    # Call the lower-level builder path through an actual price-history row.
    history = models.PriceHistory(product_id=product.id, price_old=300, price_new=250, drop_pct=16.67)
    db.add(history)
    db.commit()
    message = product_cards_message(db, user, [product], is_owner=False)
    text = _all_text(message.contents)

    assert "16%" not in text and "17%" not in text
    assert "ตรวจพบการเปลี่ยนแปลงราคา" in text
    db.delete(history)
    db.commit()


def test_compare_card_hides_catalog_prices_for_customer_and_owner(db):
    products = db.query(models.Product).order_by(models.Product.id).limit(2).all()
    for is_owner in (False, True):
        message = compare_flex_message(products[0], products[1], [], is_owner=is_owner)
        text = _all_text(message.contents)
        assert "฿250" not in text
        assert "฿350" not in text
        assert "ดูราคาล่าสุดใน Shopee" in text
