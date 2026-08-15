# -*- coding: utf-8 -*-
"""เทสต์ facebook_local — Firecrawl ค้นร้านอร่อย/ของฝาก/ของกิน หมุน 77 จังหวัด."""
from app.services import facebook_local as fl


def test_provinces_cover_77():
    assert len(fl._PROVINCES) == 77
    assert len(set(fl._PROVINCES)) == 77  # ไม่ซ้ำ
    assert "กรุงเทพมหานคร" in fl._PROVINCES and "ภูเก็ต" in fl._PROVINCES


def test_pick_rotates_province_and_topic():
    p1, label1, _ = fl._pick(0)
    p2, label2, _ = fl._pick(1)
    p3, label3, _ = fl._pick(2)
    # 3 ตัวแรก: จังหวัดไล่ลำดับ + หัวข้อครบทั้ง 3
    assert (p1, p2, p3) == (fl._PROVINCES[0], fl._PROVINCES[1], fl._PROVINCES[2])
    assert sorted([label1, label2, label3]) == [
        "ของกินอร่อย", "ของฝากขึ้นชื่อ", "ร้านอาหารเด็ด",
    ]
    # วนกลับจังหวัดที่ 0 เมื่อเลย 77 ตัว
    assert fl._pick(77)[0] == fl._PROVINCES[0]


def test_fetch_local_items_builds_query_and_normalizes(monkeypatch):
    captured = {}

    def fake_search(query, max_results=5):
        captured["query"] = query
        captured["max_results"] = max_results
        return [
            {"title": "ร้านก๋วยเตี๋ยวเรือ", "url": "https://food.example/1",
             "content": "เด็ดจริง"},
            {"title": "", "url": "", "content": ""},  # title/url ว่าง → ตัดทิ้ง
        ]

    # fetch_local_items import firecrawl_search_results แบบ deferred → monkeypatch ที่ web_search
    from app.services import web_search
    monkeypatch.setattr(web_search, "firecrawl_search_results", fake_search)

    items = fl.fetch_local_items(0)
    assert len(items) == 1
    assert items[0]["guid"] == "https://food.example/1"
    assert items[0]["link"] == "https://food.example/1"
    assert items[0]["source"] == "firecrawl"
    assert "ของกินอร่อย" in items[0]["topic"] or "ร้านอาหารเด็ด" in items[0]["topic"] \
        or "ของฝากขึ้นชื่อ" in items[0]["topic"]
    assert "จังหวัด" in captured["query"]


def test_fetch_local_items_empty_when_firecrawl_fails(monkeypatch):
    from app.services import web_search
    monkeypatch.setattr(web_search, "firecrawl_search_results",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert fl.fetch_local_items(3) == []


def test_item_key_sha1_stable_and_short():
    item = {"guid": "https://food.example/1", "link": "https://food.example/1"}
    assert fl.item_key(item) == fl.item_key(item)
    assert len(fl.item_key(item)) == 40
    assert fl.item_key({"guid": "x"}) != fl.item_key({"guid": "y"})


def test_curate_local_caption_fallback_when_groq_down(monkeypatch):
    monkeypatch.setattr(fl, "_groq_caption", lambda item: (_ for _ in ()).throw(RuntimeError("down")))
    cap = fl.curate_local_caption(
        {"title": "ข้าวซอยเชียงใหม่", "topic": "ของกินอร่อย · จ.เชียงใหม่"},
        line_oa="https://lin.ee/test",
    )
    assert "ข้าวซอยเชียงใหม่" in cap
    assert "https://lin.ee/test" in cap  # ลิงก์ LINE OA ครบ
    assert "#ป้าเข็ม" in cap and "#เที่ยวไทย" in cap


def test_curate_local_caption_uses_groq_output(monkeypatch):
    monkeypatch.setattr(fl, "_groq_caption", lambda item: "ป้าลองแล้ว อร่อยจริง 😋")
    cap = fl.curate_local_caption({"title": "ของฝาก"}, line_oa="https://lin.ee/test")
    assert cap.startswith("ป้าลองแล้ว อร่อยจริง 😋")
    assert "https://lin.ee/test" in cap
