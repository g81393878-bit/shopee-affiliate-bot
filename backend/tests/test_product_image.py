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
    monkeypatch.setattr(pi, "firecrawl_scrape", lambda url: "")
    assert pi.fetch_product_image("https://s.shopee.co.th/x") == ""
