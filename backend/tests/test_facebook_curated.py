# -*- coding: utf-8 -*-
"""เทสต์ facebook_curated — RSS fetch/parse + dedup key + curate caption fallback (mock ทุกเน็ต)."""
from app.services import facebook_curated as fc


RSS2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Tech</title>
<item><title>ข่าวหูฟังรุ่นใหม่ &amp; ราคา</title><link>https://example.com/a</link>
<guid>https://example.com/a</guid><description>สรุปข่าวหูฟัง</description></item>
<item><title>ข่าวที่สอง</title><link>https://example.com/b</link>
<guid>guid-b</guid><description>desc2</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom ข่าวหนึ่ง</title>
<link href="https://example.com/atom1"/><id>urn:atom1</id><summary>สรุป atom</summary></entry>
</feed>"""


def test_default_sources_has_7_publishers():
    sources = fc._DEFAULT_SOURCES
    assert len(sources) >= 7
    names = [s["name"] for s in sources]
    assert "Beartai" in names and "The Standard" in names and "DroidSans" in names


def test_parse_rss2():
    items = fc._parse_feed(RSS2, {"name": "Test", "topic": "เทค"})
    assert len(items) == 2
    assert items[0]["title"] == "ข่าวหูฟังรุ่นใหม่ & ราคา"  # html unescape
    assert items[0]["link"] == "https://example.com/a"
    assert items[0]["summary"] == "สรุปข่าวหูฟัง"
    assert items[0]["source"] == "Test" and items[0]["topic"] == "เทค"


def test_parse_atom():
    items = fc._parse_feed(ATOM, {"name": "Test", "topic": "เทค"})
    assert len(items) == 1
    assert items[0]["title"] == "Atom ข่าวหนึ่ง"
    assert items[0]["link"] == "https://example.com/atom1"
    assert items[0]["guid"] == "urn:atom1"


def test_parse_feed_invalid_xml_returns_empty():
    assert fc._parse_feed("ไม่ใช่ xml", {"name": "Test"}) == []


def test_item_key_sha1_stable_and_short():
    item = {"guid": "https://example.com/a", "link": "https://example.com/a"}
    k1 = fc.item_key(item)
    k2 = fc.item_key(item)
    assert k1 == k2
    assert len(k1) == 40  # sha1 hex — พอดี CampaignLog.category (String 50)
    # ใช้ guid ต่าง → key ต่าง; ไม่มี guid → fallback link
    assert fc.item_key({"guid": "x"}) != fc.item_key({"guid": "y"})
    assert fc.item_key({"link": "https://example.com/a"}) == k1


def test_fetch_news_items_skips_dead_feed(monkeypatch):
    """feed ที่พัง/โดนบล็อก → ข้าม ไม่ทำให้ทั้งฟังก์ชันล้ม"""
    calls = []

    class Resp:
        status_code = 403
        text = "blocked"

    def fake_get(url, timeout=None, follow_redirects=None, headers=None):
        calls.append(url)
        return Resp()

    monkeypatch.setattr(fc.httpx, "get", fake_get)
    monkeypatch.setattr(fc, "_rss_sources", lambda: [
        {"name": "dead", "url": "https://dead.example/rss", "topic": "เทค"},
    ])
    assert fc.fetch_news_items() == []
    assert calls == ["https://dead.example/rss"]


def test_fetch_news_items_dedup_guid(monkeypatch):
    """guid ซ้ำใน feed → ตัดเหลือตัวเดียว"""
    class Resp:
        status_code = 200
        text = RSS2

    monkeypatch.setattr(fc.httpx, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(fc, "_rss_sources", lambda: [
        {"name": "Test", "url": "https://x.example/rss", "topic": "เทค"},
    ])
    items = fc.fetch_news_items()
    assert len(items) == 2
    assert items[0]["guid"] != items[1]["guid"]


def test_curate_caption_fallback_when_groq_down(monkeypatch):
    """Groq ล้ม (ไม่มี key) → fallback ใช้หัวข้อข่าว + ลิงก์ LINE + hashtags"""
    monkeypatch.setattr(fc, "_groq_caption", lambda item: (_ for _ in ()).throw(RuntimeError("down")))
    cap = fc.curate_caption({"title": "ข่าวเตือนภัยช้อปปิ้ง"}, line_oa="https://lin.ee/test")
    assert "ข่าวเตือนภัยช้อปปิ้ง" in cap
    assert "https://lin.ee/test" in cap
    assert "#ป้าเข็ม" in cap and "#ถ้าไม่คุ้มป้าบอกให้" in cap


def test_curate_caption_uses_groq_output(monkeypatch):
    """Groq สำเร็จ → ใช้คอมเมนต์ที่เขียน + ต่อท้ายลิงก์ LINE + hashtags"""
    monkeypatch.setattr(fc, "_groq_caption", lambda item: "ป้าเห็นข่าวนี้แล้วต้องเตือนลูกหลาน 😊")
    cap = fc.curate_caption({"title": "ข่าว"}, line_oa="https://lin.ee/test")
    assert cap.startswith("ป้าเห็นข่าวนี้แล้วต้องเตือนลูกหลาน 😊")
    assert "https://lin.ee/test" in cap
