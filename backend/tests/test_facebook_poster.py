# -*- coding: utf-8 -*-
"""เทสต์ facebook-post cron endpoint + facebook_poster — mock ทุกเน็ต.

ไม่แตะ Groq/Facebook จริง: mock generate_script_for_product + post_feed / httpx.post
"""
import os

import app.api.cron as cron  # noqa: E402
import app.services.facebook_poster as fp  # noqa: E402


def _fake_script(name, category, price, style="standard", tone="neutral"):
    return {"caption": f"ป้าป้ายยา {name} จ๊ะ", "hashtags": ["ของดีบอกต่อ", "คุ้มมาก"]}


def _prod(**kw):
    base = dict(name="หูฟังบลูทูธ", category="หูฟัง", price=250, sales_count=5000,
                rating=4.5, affiliate_url="https://shope.ee/test")
    base.update(kw)
    return type("P", (), base)()


def test_build_fb_caption_fallback(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(cron, "generate_script_for_product", boom)
    out = cron._build_fb_caption(_prod())
    assert "หูฟังบลูทูธ" in out
    assert "shope.ee" not in out  # ลิงก์แยกเป็น link param (ไม่ติดในข้อความ)


def test_build_fb_caption_with_tags(monkeypatch):
    monkeypatch.setattr(cron, "generate_script_for_product", _fake_script)
    out = cron._build_fb_caption(_prod())
    assert "ป้าป้ายยา" in out
    assert "#ของดีบอกต่อ" in out
    assert "#คุ้มมาก" in out
    assert "shope.ee" not in out


def test_push_post_to_sheet_sends_row(monkeypatch):
    """POSTS_SHEET_WEBHOOK_URL ตั้ง → push แถวโพสต์ไป Google ชีท (Apps Script)"""
    monkeypatch.setenv("POSTS_SHEET_WEBHOOK_URL", "https://script.google.com/macros/s/x/exec")
    captured = {}

    class Resp:
        status_code = 200

    def fake_post(url, json=None, timeout=None, follow_redirects=None):
        captured["url"] = url
        captured["json"] = json
        captured["follow_redirects"] = follow_redirects
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    fp._push_post_to_sheet({"kind": "intro", "title": "แนะนำตัว", "post_id": "p1"})
    assert captured["url"] == "https://script.google.com/macros/s/x/exec"
    assert captured["follow_redirects"] is True  # Apps Script ตอบ 302 — ต้องตาม redirect
    assert captured["json"]["kind"] == "intro" and captured["json"]["post_id"] == "p1"


def test_push_post_to_sheet_noop_without_url(monkeypatch):
    """ไม่ตั้ง POSTS_SHEET_WEBHOOK_URL → ไม่ push (โค้ดเดิมทำงานปกติ)"""
    monkeypatch.delenv("POSTS_SHEET_WEBHOOK_URL", raising=False)
    called = []
    monkeypatch.setattr(fp.httpx, "post", lambda *a, **k: called.append(a))
    fp._push_post_to_sheet({"kind": "product"})
    assert called == []


def test_post_feed_passes_link(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"id": "post_999"}

    def fake_post(url, params=None, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_feed("ข้อความโปรโมท", link="https://s.shopee.co.th/9pdS1rMwH8")
    assert res["ok"] is True and res["post_id"] == "post_999"
    assert captured["data"]["message"] == "ข้อความโปรโมท"
    assert captured["data"]["link"] == "https://s.shopee.co.th/9pdS1rMwH8"


def test_post_feed_image_url_uses_photos_endpoint(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            # /photos คืนทั้ง id (รูป) และ post_id (โพสต์ feed)
            return {"id": "photo_1", "post_id": "page_post_1"}

    def fake_post(url, params=None, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_feed("เปิดตัวป้าเข็ม", image_url="https://example.com/mascot.png")
    assert res["ok"] is True
    assert res["post_id"] == "page_post_1"  # ใช้ post_id (ลิงก์โพสต์) ไม่ใช่ photo id
    assert captured["url"].endswith("/photos")
    assert captured["data"]["url"] == "https://example.com/mascot.png"
    assert captured["data"]["message"] == "เปิดตัวป้าเข็ม"
    assert "link" not in captured["data"]  # โพสต์รูป → ไม่ส่ง link


def test_post_feed_image_only_without_caption(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"id": "photo_2"}

    def fake_post(url, params=None, data=None, timeout=None):
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_feed("", image_url="https://example.com/mascot.png")
    assert res["ok"] is True
    assert captured["data"]["url"] == "https://example.com/mascot.png"
    assert "message" not in captured["data"]  # ไม่มี caption


def test_post_feed_background_preset_uses_feed_endpoint(monkeypatch):
    """background_preset_id → โพสต์ข้อความล้วนบนพื้นสี (text_format_preset_id)"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"id": "bg_post_1"}

    def fake_post(url, params=None, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_feed("ขายของ ราคาเท่าช้อปปี้", background_preset_id="1903718606535395")
    assert res["ok"] is True and res["post_id"] == "bg_post_1"
    assert captured["url"].endswith("/feed")  # พื้นสี → /feed ไม่ใช่ /photos
    assert captured["data"]["message"] == "ขายของ ราคาเท่าช้อปปี้"
    assert captured["data"]["text_format_preset_id"] == "1903718606535395"


def test_post_feed_background_preset_ignores_link_and_image(monkeypatch):
    """พื้นสีห้ามมี media/link — Facebook จะ ignore preset ถ้ามี → ต้องไม่ส่ง link/image_url"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"id": "bg_post_2"}

    def fake_post(url, params=None, data=None, timeout=None):
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_feed("โปรพื้นสี", link="https://s.shopee.co.th/9pdS1rMwH8",
                       image_url="https://example.com/mascot.png",
                       background_preset_id="219266485227663")
    assert res["ok"] is True
    assert "link" not in captured["data"]
    assert "url" not in captured["data"]  # ไม่ส่ง image_url (media จะทำให้พื้นสีถูก ignore)
    assert captured["data"]["text_format_preset_id"] == "219266485227663"


def test_post_feed_blocks_fake_shopee_short_link(monkeypatch):
    """ลิงก์สั้น Shopee format ปลอม (mock อย่าง s.shopee.co.th/earbuds_ok) → block ไม่ยิงขึ้นเพจ
    (กันสคริปต์เทสต์/ของ mock ที่เคยโพสต์ 'หูฟังลิงก์จริง' 24 ตัว 16/08)"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    called = []
    monkeypatch.setattr(fp.httpx, "post", lambda *a, **k: called.append(a))
    res = fp.post_feed("โปรโมทหูฟัง", link="https://s.shopee.co.th/earbuds_ok")
    assert res["ok"] is False
    assert "ลิงก์" in res["error"]
    assert called == []  # ไม่ยิง Graph API เลย


def test_post_feed_blocks_shope_ee_link(monkeypatch):
    """shope.ee = ลิงก์ปลอม (กด 404) — block เสมอ ไม่ว่าใครเรียก"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    called = []
    monkeypatch.setattr(fp.httpx, "post", lambda *a, **k: called.append(a))
    res = fp.post_feed("โปรโมท", link="https://shope.ee/earbuds_ok")
    assert res["ok"] is False
    assert "ลิงก์" in res["error"]
    assert called == []


def test_post_feed_blocks_message_with_shope_ee(monkeypatch):
    """แปะ shope.ee ไว้ในข้อความ (ไม่ใช่ link param) → block ด้วย"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    called = []
    monkeypatch.setattr(fp.httpx, "post", lambda *a, **k: called.append(a))
    res = fp.post_feed("แนะนำสินค้าจ้า https://shope.ee/abc ดูเพิ่มเติม")
    assert res["ok"] is False
    assert "shope.ee" in res["error"]
    assert called == []


def test_post_feed_allows_non_shopee_content_link(monkeypatch):
    """ลิงก์คอนเทนต์ (ข่าว/ท้องถิ่น) ที่ไม่ใช่ Shopee → ผ่านได้ตามเดิม"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"id": "post_news"}

    def fake_post(url, params=None, data=None, timeout=None):
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_feed("ป้าเล่าข่าว", link="https://news.example/1")
    assert res["ok"] is True
    assert captured["data"]["link"] == "https://news.example/1"


def test_post_feed_rejects_empty_message_and_no_image(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    res = fp.post_feed("")
    assert res["ok"] is False
    assert "message" in res["error"] or "image_url" in res["error"]


def test_post_feed_sanitizes_foreign_chars(monkeypatch):
    """อักษรต่างภาษาที่ LLM หลุด (เปอร์เซีย) ต้องถูกกรองก่อนส่งไป Facebook"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"id": "post_sanitized"}

    def fake_post(url, params=None, data=None, timeout=None):
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_feed("ป้าเห็นข่าวนี้แล้ว دیزاین มาฝาก 😊", link="https://news.example/1")
    assert res["ok"] is True
    assert "دیزاین" not in captured["data"]["message"]
    assert "ป้าเห็นข่าวนี้แล้ว" in captured["data"]["message"]
    assert captured["data"]["link"] == "https://news.example/1"  # ลิงก์ไม่โดนกรอง


def test_cron_facebook_post_dedup(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(cron, "_authorized", lambda t: True)
    monkeypatch.setattr(cron, "generate_script_for_product", _fake_script)
    monkeypatch.setenv("FB_POST_PRODUCTS", "1")  # ข้าม Phase แนะนำตัว → ตรงไปขายสินค้า
    monkeypatch.setattr(cron, "intro_posts", lambda: [])  # ไม่มีโพสต์แนะนำในเทสต์นี้
    monkeypatch.setattr(cron, "short_bg_posts", lambda: [])  # ไม่มีโพสต์พื้นสีในเทสต์นี้
    monkeypatch.setattr(cron, "fetch_news_items", lambda max_items=20: [])  # ไม่มี RSS ในเทสต์นี้
    monkeypatch.setattr(cron, "fetch_product_image", lambda url: "")  # กันเน็ตจริงในเทสต์
    posted = []
    sheet_rows = []
    monkeypatch.setattr(cron, "log_post_async", sheet_rows.append)
    monkeypatch.setattr(cron, "post_feed",
                        lambda msg, link="": posted.append((msg, link)) or
                        {"ok": True, "post_id": f"post_{len(posted)}", "error": None})
    client = TestClient(app)

    r1 = client.post("/api/cron/facebook-post")
    assert r1.status_code == 200
    b1 = r1.json()["posted"]
    assert len(b1) == 1 and b1[0]["posted"] is True

    # เรียกซ้ำ — สินค้าตัวที่โพสต์แล้วต้องถูกกัน (status=fbpost) → ได้ตัวอื่น
    r2 = client.post("/api/cron/facebook-post")
    b2 = r2.json()["posted"]
    assert len(b2) == 1 and b2[0]["posted"] is True
    assert b1[0]["id"] != b2[0]["id"]
    assert len(posted) == 2
    assert posted[0][1]  # link affiliate ถูกส่งไปด้วย
    assert len(sheet_rows) == 2  # ทุกโพสต์ที่สำเร็จถูกบันทึกชีท
    assert all(r["kind"] == "product" for r in sheet_rows)
    assert sheet_rows[0]["post_id"] == b1[0]["post_id"]
    assert sheet_rows[0]["link"]  # ลิงก์ affiliate อยู่ในแถวชีท


def test_cron_facebook_post_requires_token(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(cron, "_authorized", lambda t: False)
    client = TestClient(app)
    r = client.post("/api/cron/facebook-post", params={"token": "wrong"})
    assert r.status_code == 401


def test_facebook_auto_post_loop_disabled_by_default(monkeypatch):
    import asyncio
    from app import main as main_mod
    monkeypatch.setattr(main_mod, "FB_AUTO_POST_INTERVAL", 0)
    # ถ้า interval = 0 ต้อง return ทันที ไม่วนลูป (กันโพสต์แบบไม่ได้ตั้งค่า)
    asyncio.run(main_mod.facebook_auto_post_loop())


def test_facebook_auto_post_loop_calls_runner(monkeypatch):
    import asyncio
    import pytest
    from app import main as main_mod

    monkeypatch.setattr(main_mod, "FB_AUTO_POST_INTERVAL", 1)  # นาที
    calls = []

    class _Stop(Exception):
        pass

    async def fake_sleep(s):
        if calls:  # รอบที่สองขึ้นไป → หยุด loop (กันวนไม่จบ)
            raise _Stop()

    async def fake_to_thread(fn, *a, **k):
        return await fn(*a, **k)

    async def fake_runner(limit):
        calls.append(limit)
        return {"posted": [], "note": "mock"}

    monkeypatch.setattr(main_mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main_mod.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(main_mod, "run_facebook_auto_post", fake_runner)
    monkeypatch.setattr(main_mod, "_auto_post_due", lambda: True)  # แยกเทสต์ catch-up ไว้ต่างหาก

    with pytest.raises(_Stop):
        asyncio.run(main_mod.facebook_auto_post_loop())
    assert calls == [1]


def test_auto_post_due_no_posts_yet(monkeypatch, db):
    """ยังไม่เคยโพสต์เลย → due=True (โพสต์แรกทันที)"""
    from app import main as main_mod
    monkeypatch.setattr(main_mod, "FB_AUTO_POST_INTERVAL", 240)
    assert main_mod._auto_post_due() is True


def test_auto_post_due_recent_post_not_due(monkeypatch, db):
    """เพิ่งโพสต์เมื่อกี้ → due=False (รอให้ครบ interval ก่อน)"""
    from app import main as main_mod
    from app import models
    monkeypatch.setattr(main_mod, "FB_AUTO_POST_INTERVAL", 240)
    db.add(models.CampaignLog(category="0", recipients=1, status="fbintro"))
    db.commit()
    assert main_mod._auto_post_due() is False


def test_auto_post_due_old_post_is_due(monkeypatch, db):
    """โพสต์ล่าสุดเลย interval ไปแล้ว → due=True (catch-up หลัง deploy/รีสตาร์ท)"""
    import datetime as dt
    from app import main as main_mod
    from app import models
    monkeypatch.setattr(main_mod, "FB_AUTO_POST_INTERVAL", 240)
    c = models.CampaignLog(category="0", recipients=1, status="fbintro")
    c.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=300)
    db.add(c)
    db.commit()
    assert main_mod._auto_post_due() is True


def test_cron_facebook_post_rotation(monkeypatch):
    """หมุนเวียน 4 คลัง: แบรนด์ → (สินค้า ยังไม่เปิด) → คอนเทนต์โลก(RSS) → ท้องถิ่น → ครบแล้วหยุด"""
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(cron, "_authorized", lambda t: True)
    monkeypatch.delenv("FB_POST_PRODUCTS", raising=False)  # ยังไม่เปิดขายสินค้า
    monkeypatch.setattr(cron, "intro_posts", lambda: [
        {"title": "แนะนำตัว", "caption": "โพสต์แนะนำ 1"},
    ])
    monkeypatch.setattr(cron, "short_bg_posts", lambda: [])
    monkeypatch.setattr(cron, "fetch_news_items", lambda max_items=20: [
        {"guid": "g1", "title": "ข่าวน่าสนใจ", "link": "https://news.example/1",
         "summary": "...", "source": "Test", "topic": "เทค"},
    ])
    monkeypatch.setattr(cron, "curate_caption",
                        lambda it, line_oa="": f"ป้าเล่าข่าว: {it['title']}\n\n👉 https://lin.ee/o9Kjp1N")
    monkeypatch.setattr(cron, "fetch_local_items", lambda index=0, max_items=5: [
        {"guid": "lg1", "title": "ร้านเด็ดเมือง", "link": "https://food.example/1",
         "summary": "...", "source": "firecrawl", "topic": "ของกิน · จ.เชียงใหม่"},
    ])
    monkeypatch.setattr(cron, "curate_local_caption",
                        lambda it, line_oa="": f"ป้าแนะนำ: {it['title']}\n\n👉 https://lin.ee/o9Kjp1N")
    posted = []
    sheet_rows = []
    monkeypatch.setattr(cron, "log_post_async", sheet_rows.append)

    def fake_post_feed(msg, link="", image_url="", background_preset_id=""):
        posted.append((msg, link))
        return {"ok": True, "post_id": f"post_{len(posted)}", "error": None}

    monkeypatch.setattr(cron, "post_feed", fake_post_feed)
    client = TestClient(app)

    # tick 1 → slot 0 (แบรนด์) → แนะนำตัว
    b1 = client.post("/api/cron/facebook-post").json()["posted"]
    assert b1[0]["kind"] == "intro" and b1[0]["index"] == 0

    # tick 2 → slot 1 (สินค้า ยังไม่เปิด → ข้าม) → slot 2 (RSS) → โพสต์ข่าว + ลิงก์ข่าว
    b2 = client.post("/api/cron/facebook-post").json()["posted"]
    assert b2[0]["kind"] == "rss" and b2[0]["title"] == "ข่าวน่าสนใจ"
    assert posted[-1][1] == "https://news.example/1"  # ลิงก์ข่าวเป็น link param (preview)

    # tick 3 → slot 2 (RSS กันซ้ำ) → slot 3 (ท้องถิ่น) → โพสต์ร้าน/ของกิน + ลิงก์
    b3 = client.post("/api/cron/facebook-post").json()["posted"]
    assert b3[0]["kind"] == "local" and b3[0]["title"] == "ร้านเด็ดเมือง"
    assert posted[-1][1] == "https://food.example/1"

    # tick 4 → ทุกคลังหมด (RSS/local กันซ้ำ + แบรนด์ครบ + สินค้ายังไม่เปิด) → หยุด
    r4 = client.post("/api/cron/facebook-post")
    assert r4.json()["posted"] == []
    assert "FB_POST_PRODUCTS" in r4.json()["note"]

    assert len(posted) == 3
    assert [r["kind"] for r in sheet_rows] == ["intro", "rss", "local"]


def test_post_next_local_skips_failed_link(monkeypatch, db):
    """โพสต์ local ตัวแรกพัง (ลิงก์โดน FB ปฏิเสธ) → ต้องลองตัวถัดไป ไม่ติดตาย"""
    from app import models
    monkeypatch.setattr(cron, "fetch_local_items", lambda index=0, max_items=5: [
        {"guid": "u1", "title": "ลิงก์เฟส", "link": "https://www.facebook.com/x",
         "summary": "x", "topic": "ของกิน · จ.กรุงเทพมหานคร"},
        {"guid": "u2", "title": "ร้านวงใน", "link": "https://www.wongnai.com/y",
         "summary": "y", "topic": "ของกิน · จ.กรุงเทพมหานคร"},
    ])
    monkeypatch.setattr(cron, "curate_local_caption",
                        lambda it, line_oa="": f"ป้า: {it['title']}\n\n👉 https://lin.ee/x")
    posts = []

    def fake_post_feed(msg, link="", image_url="", background_preset_id=""):
        posts.append(link)
        if link == "https://www.facebook.com/x":
            return {"ok": False, "post_id": None, "error": "Permissions error"}
        return {"ok": True, "post_id": "post_ok", "error": None}

    monkeypatch.setattr(cron, "post_feed", fake_post_feed)
    sheet_rows = []
    monkeypatch.setattr(cron, "log_post_async", sheet_rows.append)

    res = cron._post_next_local(db)
    assert res is not None and res["posted"][0]["posted"] is True
    assert res["posted"][0]["title"] == "ร้านวงใน"
    assert posts == ["https://www.facebook.com/x", "https://www.wongnai.com/y"]
    # dedup บันทึกเฉพาะตัวที่โพสต์สำเร็จ
    rows = db.query(models.CampaignLog).filter(models.CampaignLog.status == "fblocal").all()
    assert len(rows) == 1
    assert sheet_rows and sheet_rows[0]["kind"] == "local"


def test_post_next_local_returns_none_when_all_fail(monkeypatch, db):
    """ล้มทุกตัว → คืน None ให้ rotation ไปลองคลังอื่น (ไม่ block scheduler)"""
    monkeypatch.setattr(cron, "fetch_local_items", lambda index=0, max_items=5: [
        {"guid": "u1", "title": "ลิงก์เสีย", "link": "https://bad.example/1",
         "summary": "x", "topic": "ของกิน"},
    ])
    monkeypatch.setattr(cron, "curate_local_caption",
                        lambda it, line_oa="": f"ป้า: {it['title']}")
    monkeypatch.setattr(cron, "post_feed",
                        lambda msg, link="", **k: {"ok": False, "post_id": None,
                                                    "error": "HTTP 400"})
    assert cron._post_next_local(db) is None


def _reset_products(db):
    """ล้างเฉพาะสินค้าเทสต์ (commission ≥ 900 = marker) — ไม่แตะ seed ของ conftest
    (seed มี commission ≤ 25; ถ้าลบทั้งหมด test_line_bot ที่รันทีหลังจะพัง)"""
    from app import models
    db.query(models.Product).filter(models.Product.commission >= 900) \
        .delete(synchronize_session=False)
    db.commit()


def _add_test_product(db, **kw):
    from app import models
    base = dict(name="หูฟังบลูทูธ", category="หูฟัง", price=250, sales_count=5000,
                rating=4.5, commission=999, affiliate_url="https://s.shopee.co.th/abc",
                link_status="ok", ai_score=90)
    base.update(kw)
    p = models.Product(**base)
    db.add(p)
    db.commit()
    return p


def test_post_next_product_photo_with_image(monkeypatch, db):
    """มี image_url → โพสต์แนบรูป (photo) + ลิงก์ affiliate อยู่ในแคปชั่น"""
    monkeypatch.setenv("FB_POST_PRODUCTS", "1")
    _reset_products(db)
    _add_test_product(db, image_url="https://img.example.com/h.png")
    monkeypatch.setattr(cron, "generate_script_for_product",
                        lambda *a, **k: {"caption": "ป้าป้ายยา", "hashtags": ["ของดี"]})
    captured = {}

    def fake_post_feed(msg, link="", image_url="", background_preset_id=""):
        captured["msg"] = msg
        captured["link"] = link
        captured["image_url"] = image_url
        return {"ok": True, "post_id": "post_1", "error": None}

    monkeypatch.setattr(cron, "post_feed", fake_post_feed)
    # ไม่ควรเรียก fetch (มีรูป cache อยู่แล้ว)
    monkeypatch.setattr(cron, "fetch_product_image",
                        lambda url: (_ for _ in ()).throw(AssertionError("should not fetch")))

    res = cron._post_next_product(db)
    assert res["posted"][0]["posted"] is True
    assert captured["image_url"] == "https://img.example.com/h.png"
    assert captured["link"] == ""  # photo → ไม่ส่ง link param
    assert "s.shopee.co.th/abc" in captured["msg"]  # ลิงก์อยู่ในแคปชั่น


def test_post_next_product_link_card_when_no_image(monkeypatch, db):
    """หา og:image ไม่ได้ → fallback การ์ดลิงก์เดิม (link param แยกจากข้อความ)"""
    monkeypatch.setenv("FB_POST_PRODUCTS", "1")
    _reset_products(db)
    _add_test_product(db)  # ไม่มี image_url
    monkeypatch.setattr(cron, "generate_script_for_product",
                        lambda *a, **k: {"caption": "ป้าป้ายยา", "hashtags": ["ของดี"]})
    monkeypatch.setattr(cron, "fetch_product_image", lambda url: "")  # หาไม่ได้
    captured = {}

    def fake_post_feed(msg, link="", image_url="", background_preset_id=""):
        captured["msg"] = msg
        captured["link"] = link
        captured["image_url"] = image_url
        return {"ok": True, "post_id": "post_2", "error": None}

    monkeypatch.setattr(cron, "post_feed", fake_post_feed)
    res = cron._post_next_product(db)
    assert res["posted"][0]["posted"] is True
    assert captured["link"] == "https://s.shopee.co.th/abc"
    assert captured["image_url"] == ""
    assert "s.shopee.co.th" not in captured["msg"]  # ลิงก์แยกเป็น link param


def test_post_next_product_fetches_and_caches_image(monkeypatch, db):
    """ยังไม่มี image_url → ดึง og:image ครั้งเดียวแล้วจำไว้ใน DB"""
    monkeypatch.setenv("FB_POST_PRODUCTS", "1")
    _reset_products(db)
    p = _add_test_product(db)  # ไม่มี image_url
    calls = []
    monkeypatch.setattr(cron, "generate_script_for_product",
                        lambda *a, **k: {"caption": "ป้า", "hashtags": ["ดี"]})
    monkeypatch.setattr(cron, "fetch_product_image",
                        lambda url: calls.append(url) or "https://img.example.com/fetched.png")

    def fake_post_feed(msg, link="", image_url="", background_preset_id=""):
        return {"ok": True, "post_id": "post_3", "error": None}

    monkeypatch.setattr(cron, "post_feed", fake_post_feed)
    res = cron._post_next_product(db)
    assert res["posted"][0]["posted"] is True
    assert calls == ["https://s.shopee.co.th/abc"]
    db.refresh(p)
    assert p.image_url == "https://img.example.com/fetched.png"  # cache ลง DB


def test_intro_posts_have_badge_and_image_url(monkeypatch):
    """คลังแคปชั่น 12 ตัว — ทุกตัวต้องมีป้ายข้อความ (badge) + รูปมาสคอต image_url"""
    from app.services import facebook_intro
    monkeypatch.delenv("LINE_OA_URL", raising=False)
    monkeypatch.delenv("INTRO_IMAGE_URL", raising=False)
    posts = facebook_intro.intro_posts()
    assert len(posts) == 12
    assert posts[0]["caption"].startswith("🏷️ เรื่องป้า")
    for p in posts:
        assert p["title"] and p["caption"]
        assert p["caption"].startswith("🏷️ ")  # badge เป็นป้ายข้อความนำหน้าเสมอ
        assert p["image_url"].endswith("/static/pa-khem-avatar.png")


def test_short_bg_posts_short_text_and_rotating_presets(monkeypatch):
    """คลังข้อความสั้นพื้นสี — ทุกตัว ≤ 130 ตัวอักษร + มี preset_id + สีไม่ซ้ำ + มีลิงก์ LINE OA"""
    from app.services import facebook_intro
    monkeypatch.setenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    posts = facebook_intro.short_bg_posts()
    assert len(posts) == 8
    preset_ids = []
    for p in posts:
        assert p["title"] and p["caption"] and p["preset_id"]
        assert len(p["caption"]) <= 130  # Facebook จำกัดข้อความพื้นสี ≤ 130 ตัวอักษร
        assert "https://lin.ee/o9Kjp1N" in p["caption"]  # ทุกโพสต์ต้องชวนเพิ่มเพื่อน LINE
        preset_ids.append(p["preset_id"])
    # 8 สีต่างกันหมด (หมุนเวียนไม่ซ้ำ) — ไม่งั้นจะโพสต์พื้นสีเดิมซ้ำกัน
    assert len(set(preset_ids)) == 8


def test_post_video_file_url(monkeypatch):
    """file_url → POST /{page_id}/videos ให้ Facebook ดาวน์โหลดเอง (ใช้ได้จาก Render)"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"id": "video_123"}

    def fake_post(url, params=None, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["files"] = files
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_video(description="แนะนำบอทป้าเข็ม", file_url="https://cdn.example.com/clip.mp4")
    assert res["ok"] is True and res["video_id"] == "video_123"
    assert captured["url"].endswith("/videos")
    assert captured["data"]["file_url"] == "https://cdn.example.com/clip.mp4"
    assert captured["data"]["description"] == "แนะนำบอทป้าเข็ม"
    assert captured["data"]["published"] == "true"  # string ตัวเล็ก — Graph API ต้องการ true/false
    assert captured["files"] is None


def test_post_video_file_path_uploads_source(monkeypatch):
    """file_path → multipart upload source (ไฟล์ในเครื่อง)"""
    import tempfile
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            fh.write(b"\x00\x00\x00\x18ftypmp42" * 100)
        captured = {}

        class Resp:
            status_code = 200
            def json(self):
                return {"id": "video_456"}

        def fake_post(url, params=None, data=None, files=None, timeout=None):
            captured["url"] = url
            captured["data"] = data
            captured["files"] = files
            return Resp()

        monkeypatch.setattr(fp.httpx, "post", fake_post)
        res = fp.post_video(description="คลิป", file_path=path)
        assert res["ok"] is True and res["video_id"] == "video_456"
        assert captured["url"].endswith("/videos")
        assert "file_url" not in captured["data"]  # ใช้ source ไม่ใช่ file_url
        name, fobj, ctype = captured["files"]["source"]
        assert name == os.path.basename(path) and ctype == "video/mp4"
        assert fobj.startswith(b"\x00\x00\x00\x18ftypmp42")  # ไบต์ไฟล์ถูกส่งจริง
    finally:
        os.remove(path)


def test_post_video_requires_source(monkeypatch):
    """ไม่ระบุทั้ง file_url และ file_path → ปฏิเสธ"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    res = fp.post_video()
    assert res["ok"] is False
    assert "file_url" in res["error"] or "file_path" in res["error"]


def test_post_video_missing_file(monkeypatch):
    """ไฟล์ในเครื่องไม่มี → ปฏิเสธก่อนเรียก API"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    res = fp.post_video(file_path="C:/nonexistent/clip.mp4")
    assert res["ok"] is False
    assert "ไม่พบ" in res["error"]


def test_post_video_error_surfaces(monkeypatch):
    """Graph API ตอบ error (เช่น Permissions error) → ส่งต่อข้อความให้เห็น"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")

    class Resp:
        status_code = 400
        def json(self):
            return {"error": {"message": "Permissions error"}}

    monkeypatch.setattr(fp.httpx, "post", lambda *a, **k: Resp())
    res = fp.post_video(file_url="https://cdn.example.com/c.mp4")
    assert res["ok"] is False
    assert "Permissions error" in res["error"]


def test_post_video_sanitizes_description(monkeypatch):
    """แคปชันที่มีอักษรต่างภาษา (LLM หลุด) ต้องถูกกรองก่อนส่ง"""
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    captured = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"id": "video_san"}

    def fake_post(url, params=None, data=None, files=None, timeout=None):
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(fp.httpx, "post", fake_post)
    res = fp.post_video(description="แนะนำบอท دیزاین 😊", file_url="https://cdn.example.com/c.mp4")
    assert res["ok"] is True
    assert "دیزاین" not in captured["data"]["description"]
    assert "แนะนำบอท" in captured["data"]["description"]


def test_post_video_no_token(monkeypatch):
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    res = fp.post_video(file_url="https://cdn.example.com/c.mp4")
    assert res["ok"] is False
    assert "FACEBOOK_PAGE_ACCESS_TOKEN" in res["error"]


# ===========================================================================
# กวาดลบโพสต์ลิงก์ปลอม (clean-fake-posts)
# ===========================================================================

def test_is_fake_link_post_detects_fake_links():
    """shope.ee / lazada / s.shopee.co.th รหัสไม่ valid (มี _) = โพสต์ปลอม"""
    assert fp.is_fake_link_post("ดู https://shope.ee/abc") is True
    assert fp.is_fake_link_post("", ["https://s.lazada.co.th/x"]) is True
    assert fp.is_fake_link_post("", ["https://s.shopee.co.th/earbuds_ok"]) is True


def test_is_fake_link_post_checks_known_links():
    """รหัส base62 ที่ผ่าน format แต่ไม่ใช่ลิงก์ในคลัง (เช่น earbudsok ของ mock poster) = ปลอม"""
    known = {"https://s.shopee.co.th/9pdS1rMwH8"}
    # ไม่มีในคลัง → ปลอม
    assert fp.is_fake_link_post("", ["https://s.shopee.co.th/earbudsok"], known_links=known) is True
    # มีในคลัง (case-sensitive รหัส) → ของจริง
    assert fp.is_fake_link_post("", ["https://s.shopee.co.th/9pdS1rMwH8"], known_links=known) is False
    # ไม่ส่ง known_links → เช็คแค่ format (earbudsok base62 ผ่าน format → ไม่ปลอม)
    assert fp.is_fake_link_post("", ["https://s.shopee.co.th/earbudsok"], known_links=None) is False


def test_is_fake_link_post_allows_non_shopee_links():
    """ลิงก์คอนเทนต์ (ข่าว/ท้องถิ่น) ที่ไม่ใช่ Shopee → ไม่ปลอม"""
    assert fp.is_fake_link_post("ป้าเล่าข่าว", ["https://news.example/1"],
                                known_links=set()) is False
    assert fp.is_fake_link_post("ร้านเด็ด", ["https://www.wongnai.com/y"],
                                known_links=set()) is False


def test_extract_post_urls_decodes_fb_redirect():
    """ดึง URL จากข้อความ + attachment และถอด l.facebook.com/l.php?u= ให้เป็น URL จริง"""
    atts = {"data": [{"type": "share",
                      "url": "https://l.facebook.com/l.php?u=https%3A%2F%2Fs.shopee.co.th%2Fearbudsok%3Fcontent"}]}
    urls = fp.extract_post_urls("ดู https://s.shopee.co.th/abc", atts)
    assert "https://s.shopee.co.th/abc" in urls
    assert "https://s.shopee.co.th/earbudsok?content" in urls  # ถอด redirect แล้ว


def test_cron_clean_fake_posts_endpoint(monkeypatch, db):
    """POST /api/cron/clean-fake-posts — ลบเฉพาะโพสต์ปลอม, เก็บของจริง, dry_run ไม่ลบ

    ใช้ลิงก์ deterministic: s.shopee.co.th/test = seed ของ conftest (session-scoped คงอยู่ทุกเทสต์)
    → "ในคลัง"; zzMockFake99 = base62 ที่ไม่มีในคลังแน่นอน → "ปลอม"; shope.ee = ปลอมเสมอ.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(cron, "_authorized", lambda t: True)
    fake_posts = [
        {"id": "pg_1", "message": "ใจเย็นๆ นะลูก! 'หูฟังลิงก์จริง'",
         "created_time": "2026-08-17T02:26:21+0000",
         "urls": ["https://s.shopee.co.th/zzMockFake99"]},  # base62 แต่ไม่มีในคลัง → ปลอม
        {"id": "pg_2", "message": "ขายของจริง",
         "created_time": "2026-08-17T01:00:00+0000",
         "urls": ["https://s.shopee.co.th/test"]},          # seed ของ conftest → ในคลัง → ของจริง
        {"id": "pg_3", "message": "ดู https://shope.ee/abc",
         "created_time": "2026-08-17T00:00:00+0000",
         "urls": []},                                       # shope.ee → ปลอม
    ]
    monkeypatch.setattr(cron, "fetch_page_posts", lambda limit=100: fake_posts)
    deleted = []
    monkeypatch.setattr(cron, "delete_page_post", lambda pid: deleted.append(pid) or True)
    client = TestClient(app)

    # dry-run → ไม่ลบ
    r = client.post("/api/cron/clean-fake-posts", params={"token": "x", "dry_run": "true"})
    assert r.status_code == 200
    b = r.json()
    assert b["dry_run"] is True and b["scanned"] == 3 and b["kept_count"] == 1
    assert len(b["deleted"]) == 2  # pg_1 + pg_3 (ปลอม)
    assert deleted == []  # dry-run ไม่ลบจริง

    # ลบจริง → ลบเฉพาะ pg_1 + pg_3
    r2 = client.post("/api/cron/clean-fake-posts", params={"token": "x"})
    b2 = r2.json()
    assert b2["dry_run"] is False
    assert sorted(d["id"] for d in b2["deleted"]) == ["pg_1", "pg_3"]
    assert sorted(deleted) == ["pg_1", "pg_3"]


def test_cron_clean_fake_posts_requires_token(monkeypatch):
    """ไม่ผ่าน token → 401"""
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(cron, "_authorized", lambda t: False)
    client = TestClient(app)
    r = client.post("/api/cron/clean-fake-posts", params={"token": "wrong"})
    assert r.status_code == 401


# ===========================================================================
# กันโพสต์ซ้ำ/โพสต์หมวดถี่เกิน (cron ↔ radar cross-flow)
# ===========================================================================

def test_post_next_product_skips_recent_category(monkeypatch, db):
    """หมวดที่ cron เพิ่งโพสต์ (ภายใน cooldown) → ข้ามสินค้าหมวดนั้น (กันหูฟังถี่เกิน)"""
    from app import models
    monkeypatch.setenv("FB_POST_PRODUCTS", "1")
    monkeypatch.delenv("FB_POST_CATEGORY_COOLDOWN_HOURS", raising=False)  # default 24h
    _reset_products(db)
    _add_test_product(db, name="หูฟัง A", category="หูฟัง", commission=999)
    other = _add_test_product(db, name="ของใช้ B", category="ของใช้", commission=998)
    # เพิ่งโพสต์หูฟัง (CampaignLog fbpost) → cooldown กันหมวดหูฟัง
    earbuds = db.query(models.Product).filter(models.Product.name == "หูฟัง A").first()
    db.add(models.CampaignLog(category=str(earbuds.id), recipients=1, status="fbpost"))
    db.commit()
    monkeypatch.setattr(cron, "generate_script_for_product",
                        lambda *a, **k: {"caption": "ป้า", "hashtags": []})
    monkeypatch.setattr(cron, "fetch_product_image", lambda url: "")
    posted = {}
    monkeypatch.setattr(cron, "post_feed",
                        lambda msg, link="", **k: posted.update(name=msg) or
                        {"ok": True, "post_id": "p1", "error": None})
    res = cron._post_next_product(db)
    assert res is not None and res["posted"][0]["posted"] is True
    assert res["posted"][0]["name"] == "ของใช้ B"  # ข้ามหูฟัง (เพิ่งโพสต์) เลือกของใช้แทน


def test_post_next_product_skips_radar_posted_product(monkeypatch, db):
    """สินค้าที่ radar เพิ่งโพสต์ (demand event posted) → cron ไม่โพสต์ซ้ำ"""
    from app import models
    monkeypatch.setenv("FB_POST_PRODUCTS", "1")
    _reset_products(db)
    p = _add_test_product(db)
    # radar เพิ่งโพสต์สินค้านี้
    lead = models.FacebookDetectedLead(fb_post_id="radar_post_x", post_url="https://fb.com/x",
                                       post_text="อยากได้", status="processed")
    db.add(lead)
    db.flush()
    db.add(models.FacebookDemandEvent(lead_id=lead.id, intent="buy_request", demand_score=90,
                                      notification_status="posted", matched_product_id=p.id))
    db.commit()
    monkeypatch.setattr(cron, "generate_script_for_product",
                        lambda *a, **k: {"caption": "ป้า", "hashtags": []})
    monkeypatch.setattr(cron, "fetch_product_image", lambda url: "")
    posted = {}
    monkeypatch.setattr(cron, "post_feed",
                        lambda msg, link="", **k: posted.update(pid=p.id) or
                        {"ok": True, "post_id": "p", "error": None})
    res = cron._post_next_product(db)
    # สินค้าที่ radar โพสต์ (คอมสูงสุด 999) ต้องถูกข้าม — เลือกตัวอื่นแทน
    assert res is not None and res["posted"][0]["posted"] is True
    assert res["posted"][0]["id"] != p.id


def test_radar_category_cooldown_counts_cron_fbpost(monkeypatch, db):
    """radar กันโพสต์หมวดที่ cron เพิ่งโพสต์ (CampaignLog fbpost) — กันหมวดเดียวถี่ข้าม flow"""
    from app import models
    from app.api import facebook_radar as radar_api
    _add_test_product(db, name="หูฟัง A", category="หูฟัง")
    earbuds = db.query(models.Product).filter(models.Product.name == "หูฟัง A").first()
    db.add(models.CampaignLog(category=str(earbuds.id), recipients=1, status="fbpost"))
    db.commit()
    # cron เพิ่งโพสต์หูฟัง → radar ไม่ควรโพสต์หูฟังภายใน cooldown
    assert radar_api.check_category_cooldown_allowed(db, "หูฟัง") is False
    # หมวดอื่นยังโพสต์ได้
    assert radar_api.check_category_cooldown_allowed(db, "ของใช้") is True
