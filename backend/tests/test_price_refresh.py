# -*- coding: utf-8 -*-
"""เทสต์ price_refresh + firecrawl_scrape — Firecrawl หลัก, requests สำรอง"""
import pytest

import app.services.price_refresh as pr  # noqa: E402
import app.services.web_search as ws  # noqa: E402


def test_extract_price_from_html():
    assert pr.extract_price_from_html('"price": 2500000, "priceMax": 3000000') == 25.0
    assert pr.extract_price_from_html("") is None
    assert pr.extract_price_from_html('"price": 500') is None  # น้อยกว่า 4 หลัก → ไม่นับ


def test_firecrawl_scrape_returns_html(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc_test_key")
    monkeypatch.setattr(ws, "_provider_allowed", lambda name: True)
    monkeypatch.setattr(ws, "_provider_success", lambda name: None)
    monkeypatch.setattr(ws, "_provider_failure", lambda name, err: None)
    monkeypatch.setattr(ws, "_post_json", lambda url, body, headers, timeout: {
        "success": True,
        "data": {"html": '<script>"price": 1990000</script>'},
    })
    assert ws.firecrawl_scrape("https://example.com/x") == '<script>"price": 1990000</script>'


def test_firecrawl_scrape_no_key(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "")
    monkeypatch.setattr(ws, "_provider_allowed", lambda name: True)
    monkeypatch.setattr(ws, "_provider_failure", lambda name, err: None)
    assert ws.firecrawl_scrape("https://example.com/x") == ""


class _FakeResp:
    status_code = 200
    content = b'{"price": 1990000}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_via_requests(monkeypatch):
    monkeypatch.setattr(pr.requests, "get", lambda *a, **k: _FakeResp())
    price, detail = pr._fetch_via_requests("https://s.shopee.co.th/x")
    assert price == 19.9
    assert detail == "ok"


def test_fetch_product_price_requests_first_no_firecrawl(monkeypatch):
    # requests ได้ราคาแล้ว → ต้องไม่เรียก Firecrawl (ประหยัด credit)
    called = {"firecrawl": False}
    monkeypatch.setattr(pr, "_fetch_via_requests", lambda url: (25.0, "ok"))
    monkeypatch.setattr(pr, "firecrawl_scrape",
                        lambda url: called.__setitem__("firecrawl", True) or "")
    price, detail = pr.fetch_product_price("https://s.shopee.co.th/x")
    assert price == 25.0
    assert detail == "ok"
    assert called["firecrawl"] is False


def test_fetch_product_price_firecrawl_when_blocked(monkeypatch):
    monkeypatch.setattr(pr, "_fetch_via_requests", lambda url: (None, "anti-bot"))
    monkeypatch.setattr(pr, "firecrawl_scrape",
                        lambda url: '<script>"price": 2500000</script>')
    price, detail = pr.fetch_product_price("https://s.shopee.co.th/x")
    assert price == 25.0
    assert detail == "ok"


def test_fetch_product_price_firecrawl_when_no_price(monkeypatch):
    monkeypatch.setattr(pr, "_fetch_via_requests", lambda url: (None, "no price found"))
    monkeypatch.setattr(pr, "firecrawl_scrape",
                        lambda url: '<script>"price": 1990000</script>')
    price, detail = pr.fetch_product_price("https://s.shopee.co.th/x")
    assert price == 19.9
    assert detail == "ok"


def test_fetch_product_price_both_fail(monkeypatch):
    monkeypatch.setattr(pr, "_fetch_via_requests", lambda url: (None, "anti-bot"))
    monkeypatch.setattr(pr, "firecrawl_scrape", lambda url: "")
    price, detail = pr.fetch_product_price("https://s.shopee.co.th/x")
    assert price is None
    assert detail == "anti-bot"
