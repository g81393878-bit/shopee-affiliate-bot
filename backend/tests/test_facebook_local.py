# -*- coding: utf-8 -*-
"""เทสต์ facebook_local — Firecrawl ค้นหาสินค้ากระแส/ของจำเป็นต้องมี หมุน 8 หมวดหมู่."""
from app.services import facebook_local as fl


def test_product_categories_cover_8():
    assert len(fl._PRODUCT_CATEGORIES) == 8
    categories = [c["category"] for c in fl._PRODUCT_CATEGORIES]
    assert len(set(categories)) == 8  # ไม่ซ้ำ
    assert any("ของใช้ในบ้าน" in c for c in categories)
    assert any("เครื่องใช้ไฟฟ้า" in c for c in categories)


def test_pick_rotates_category_and_angle():
    cat1, tag1, angle1, q1 = fl._pick(0)
    cat2, tag2, angle2, q2 = fl._pick(1)
    cat3, tag3, angle3, q3 = fl._pick(2)
    
    assert cat1 != cat2
    assert sorted([angle1, angle2, angle3]) == [
        "ของมันต้องมี", "ยอดฮิตขายดี", "รีวิวบอกต่อ",
    ]
    # วนกลับหมวดหมู่ที่ 0 เมื่อเลย 8 ตัว
    assert fl._pick(8)[0] == fl._PRODUCT_CATEGORIES[0]["category"]


def test_fetch_local_items_builds_query_and_normalizes(monkeypatch):
    captured = {}

    def fake_search(query, max_results=5):
        captured["query"] = query
        captured["max_results"] = max_results
        return [
            {"title": "กล่องจัดระเบียบ 3D", "url": "https://item.example/1",
             "content": "ใช้ดีมาก รีวิวแน่น"},
            {"title": "", "url": "", "content": ""},  # title/url ว่าง → ตัดทิ้ง
        ]

    from app.services import web_search
    monkeypatch.setattr(web_search, "firecrawl_search_results", fake_search)

    items = fl.fetch_local_items(0)
    assert len(items) == 1
    assert items[0]["guid"] == "https://item.example/1"
    assert items[0]["link"] == "https://item.example/1"
    assert items[0]["source"] == "firecrawl"
    assert "ของใช้ในบ้าน" in items[0]["topic"]
    assert "รีวิว" in captured["query"] or "ของมันต้องมี" in captured["query"]


def test_fetch_local_items_empty_when_firecrawl_fails(monkeypatch):
    from app.services import web_search
    monkeypatch.setattr(web_search, "firecrawl_search_results",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert fl.fetch_local_items(3) == []


def test_item_key_sha1_stable_and_short():
    item = {"guid": "https://item.example/1", "link": "https://item.example/1"}
    assert fl.item_key(item) == fl.item_key(item)
    assert len(fl.item_key(item)) == 40
    assert fl.item_key({"guid": "x"}) != fl.item_key({"guid": "y"})


def test_link_ok_rejects_facebook_domains():
    """ลิงก์ facebook.com/fb.watch/messenger → Graph API โพสต์ preview ไม่ได้ → ตัด"""
    assert fl._link_ok("https://www.pantip.com/topic/12345") is True
    assert fl._link_ok("https://www.facebook.com/groups/123/posts/456") is False
    assert fl._link_ok("https://fb.watch/video123") is False
    assert fl._link_ok("https://m.facebook.com/story.php") is False
    assert fl._link_ok("") is False


def test_fetch_local_items_skips_facebook_links(monkeypatch):
    """Firecrawl มักคืนโพสต์กลุ่มเฟสเป็นผลแรก → ต้องข้ามไม่ให้คลังติดตาย"""
    from app.services import web_search
    monkeypatch.setattr(web_search, "firecrawl_search_results", lambda *a, **k: [
        {"title": "กลุ่มเฟสรวมสินค้า", "url": "https://www.facebook.com/groups/123/posts/1",
         "content": "x"},
        {"title": "รีวิวพันทิป", "url": "https://www.pantip.com/topic/12345",
         "content": "y"},
    ])
    items = fl.fetch_local_items(0)
    assert len(items) == 1
    assert items[0]["link"] == "https://www.pantip.com/topic/12345"


def test_curate_local_caption_fallback_when_groq_down(monkeypatch):
    monkeypatch.setattr(fl, "_groq_caption", lambda item: (_ for _ in ()).throw(RuntimeError("down")))
    cap = fl.curate_local_caption(
        {"title": "กล่องจัดระเบียบ", "topic": "ของใช้ในบ้าน · รีวิวบอกต่อ"},
        line_oa="https://lin.ee/test",
    )
    assert "กล่องจัดระเบียบ" in cap
    assert "https://lin.ee/test" in cap  # ลิงก์ LINE OA ครบ
    assert "#ป้าเข็มป้ายยา" in cap and "#ของมันต้องมี" in cap


def test_curate_local_caption_uses_groq_output(monkeypatch):
    monkeypatch.setattr(fl, "_groq_caption", lambda item: "ป้าแนะนำตัวนี้เลยลูก ดีจริง ✨")
    cap = fl.curate_local_caption({"title": "ไอเทมเด็ด"}, line_oa="https://lin.ee/test")
    assert cap.startswith("ป้าแนะนำตัวนี้เลยลูก ดีจริง ✨")
    assert "https://lin.ee/test" in cap
