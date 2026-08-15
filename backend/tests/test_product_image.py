# -*- coding: utf-8 -*-
"""เทสต์ product_image — ดึง og:image จากหน้า Shopee (requests → firecrawl fallback)."""
import requests

from app.services import product_image as pi


def test_extract_og_image_property():
    html = '<html><head><meta property="og:image" content="https://img.example.com/a.jpg"></head></html>'
    assert pi.extract_og_image(html) == "https://img.example.com/a.jpg"


def test_extract_og_image_content_before_property():
    html = '<meta content="https://img.example.com/b.png" property="og:image">'
    assert pi.extract_og_image(html) == "https://img.example.com/b.png"


def test_extract_og_image_name_attribute():
    html = '<meta name="og:image" content="https://img.example.com/c.webp">'
    assert pi.extract_og_image(html) == "https://img.example.com/c.webp"


def test_extract_og_image_missing_or_relative():
    assert pi.extract_og_image("") == ""
    assert pi.extract_og_image("<html>no meta</html>") == ""
    # protocol-relative (//...) กันเอาไปโพสต์ Facebook ไม่ได้ → ตัดทิ้ง
    assert pi.extract_og_image('<meta property="og:image" content="//img.example.com/c.jpg">') == ""


def test_fetch_product_image_requests_first(monkeypatch):
    class Resp:
        status_code = 200
        content = b'<meta property="og:image" content="https://img.example.com/x.jpg">'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    monkeypatch.setattr(pi.requests, "get", lambda *a, **k: Resp())
    assert pi.fetch_product_image("https://s.shopee.co.th/x") == "https://img.example.com/x.jpg"


def test_fetch_product_image_firecrawl_fallback(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.RequestException("down")

    monkeypatch.setattr(pi.requests, "get", boom)
    monkeypatch.setattr(pi, "firecrawl_scrape",
                        lambda url: '<meta property="og:image" content="https://img.example.com/fb.jpg">')
    assert pi.fetch_product_image("https://s.shopee.co.th/x") == "https://img.example.com/fb.jpg"


def test_fetch_product_image_empty_when_all_fail(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.RequestException("down")

    monkeypatch.setattr(pi.requests, "get", boom)
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(pi, "firecrawl_scrape", lambda url: "")
    assert pi.fetch_product_image("https://s.shopee.co.th/x") == ""


def test_facebook_og_image_returns_url(monkeypatch):
    """Facebook og scrape คืน image → ใช้ลิงก์นั้น (Shopee กัน requests แต่ยอม FB)"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    def fake_post(url, params=None, timeout=None):
        captured["params"] = params
        return type("R", (), {"json": lambda self: {
            "image": [{"url": "https://down-th.img.susercontent.com/file/promo-x"}],
        }})()

    monkeypatch.setattr(pi.requests, "post", fake_post)
    assert pi._facebook_og_image("https://s.shopee.co.th/x") == \
        "https://down-th.img.susercontent.com/file/promo-x"
    assert captured["params"]["scrape"] == "true"
    assert captured["params"]["access_token"] == "tok123"


def test_facebook_og_image_retries_on_empty_image(monkeypatch):
    """Facebook scrape ตอบ image ว่างรอบแรก (transient) → retry แล้วได้รูป"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    calls = {"n": 0}

    def fake_post(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return type("R", (), {"json": lambda self: {"image": []}})()
        return type("R", (), {"json": lambda self: {
            "image": [{"url": "https://img.example.com/retry.jpg"}],
        }})()

    monkeypatch.setattr(pi.requests, "post", fake_post)
    monkeypatch.setattr(pi.time, "sleep", lambda s: None)
    assert pi._facebook_og_image("https://s.shopee.co.th/x") == \
        "https://img.example.com/retry.jpg"
    assert calls["n"] == 2


def test_fetch_product_image_uses_facebook_scrape_before_firecrawl(monkeypatch):
    """requests หา og:image ไม่ได้ → Facebook scrape ต้องถูกใช้ (ไม่เผา firecrawl)"""
    def boom(*a, **k):
        raise requests.exceptions.RequestException("down")

    monkeypatch.setattr(pi.requests, "get", boom)
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    monkeypatch.setattr(pi, "_facebook_og_image",
                        lambda url, timeout=20: "https://img.example.com/fb-og.jpg")
    called = []
    monkeypatch.setattr(pi, "firecrawl_scrape", lambda url: called.append(url) or "")
    assert pi.fetch_product_image("https://s.shopee.co.th/x") == "https://img.example.com/fb-og.jpg"
    assert called == []  # firecrawl ไม่ถูกเรียก (facebook ได้รูปก่อน)
