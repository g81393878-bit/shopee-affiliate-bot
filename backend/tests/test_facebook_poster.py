# -*- coding: utf-8 -*-
"""เทสต์ facebook-post cron endpoint + facebook_poster — mock ทุกเน็ต.

ไม่แตะ Groq/Facebook จริง: mock generate_script_for_product + post_feed / httpx.post
"""
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
    res = fp.post_feed("ข้อความโปรโมท", link="https://shope.ee/test")
    assert res["ok"] is True and res["post_id"] == "post_999"
    assert captured["data"]["message"] == "ข้อความโปรโมท"
    assert captured["data"]["link"] == "https://shope.ee/test"


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
    res = fp.post_feed("โปรพื้นสี", link="https://shope.ee/test",
                       image_url="https://example.com/mascot.png",
                       background_preset_id="219266485227663")
    assert res["ok"] is True
    assert "link" not in captured["data"]
    assert "url" not in captured["data"]  # ไม่ส่ง image_url (media จะทำให้พื้นสีถูก ignore)
    assert captured["data"]["text_format_preset_id"] == "219266485227663"


def test_post_feed_rejects_empty_message_and_no_image(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "tok123")
    res = fp.post_feed("")
    assert res["ok"] is False
    assert "message" in res["error"] or "image_url" in res["error"]


def test_cron_facebook_post_dedup(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(cron, "_authorized", lambda t: True)
    monkeypatch.setattr(cron, "generate_script_for_product", _fake_script)
    monkeypatch.setenv("FB_POST_PRODUCTS", "1")  # ข้าม Phase แนะนำตัว → ตรงไปขายสินค้า
    monkeypatch.setattr(cron, "intro_posts", lambda: [])  # ไม่มีโพสต์แนะนำในเทสต์นี้
    monkeypatch.setattr(cron, "short_bg_posts", lambda: [])  # ไม่มีโพสต์พื้นสีในเทสต์นี้
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

    with pytest.raises(_Stop):
        asyncio.run(main_mod.facebook_auto_post_loop())
    assert calls == [1]


def test_cron_facebook_post_intro_first(monkeypatch):
    """Phase 1 — สลับโพสต์ แนะนำตัว(มาสคอต) ↔ ข้อความสั้นพื้นสี พอครบ + ยังไม่เปิด
    FB_POST_PRODUCTS → หยุด ไม่ขายสินค้า"""
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(cron, "_authorized", lambda t: True)
    monkeypatch.delenv("FB_POST_PRODUCTS", raising=False)  # ยังไม่เปิดขายสินค้า
    monkeypatch.setattr(cron, "intro_posts", lambda: [
        {"title": "แนะนำตัว", "caption": "โพสต์แนะนำ 1"},
        {"title": "ฟีเจอร์เด่น", "caption": "โพสต์แนะนำ 2"},
    ])
    monkeypatch.setattr(cron, "short_bg_posts", lambda: [
        {"title": "สั้น1", "caption": "ข้อความสั้น 1", "preset_id": "1903718606535395"},
    ])
    posted = []
    sheet_rows = []
    monkeypatch.setattr(cron, "log_post_async", sheet_rows.append)

    def fake_post_feed(msg, link="", image_url="", background_preset_id=""):
        posted.append((msg, background_preset_id))
        return {"ok": True, "post_id": f"post_{len(posted)}", "error": None}

    monkeypatch.setattr(cron, "post_feed", fake_post_feed)
    client = TestClient(app)

    # tick 1 (คู่) → แนะนำตัวตัวที่ 0
    b1 = client.post("/api/cron/facebook-post").json()["posted"]
    assert b1[0]["kind"] == "intro" and b1[0]["index"] == 0

    # tick 2 (คี่) → ข้อความสั้นพื้นสี (มี preset_id)
    b2 = client.post("/api/cron/facebook-post").json()["posted"]
    assert b2[0]["kind"] == "bg" and b2[0]["preset_id"] == "1903718606535395"

    # tick 3 (คู่) → แนะนำตัวตัวที่ 1
    b3 = client.post("/api/cron/facebook-post").json()["posted"]
    assert b3[0]["kind"] == "intro" and b3[0]["index"] == 1

    # tick 4 (คี่) → พื้นสีครบ → fallback แนะนำตัวครบ → หยุด (ไม่โพสต์สินค้า)
    r4 = client.post("/api/cron/facebook-post")
    assert r4.json()["posted"] == []
    assert "FB_POST_PRODUCTS" in r4.json()["note"]

    assert len(posted) == 3  # intro 2 + bg 1
    assert len(sheet_rows) == 3  # ทั้ง 3 ตัวถูกบันทึกชีท
    assert [r["kind"] for r in sheet_rows] == ["intro", "bg", "intro"]
    assert sheet_rows[0]["post_id"] == "post_1"
    assert sheet_rows[0]["post_url"] == "https://www.facebook.com/post_1"
    # โพสต์พื้นสีใช้ background_preset_id ไม่มี link/image
    assert posted[1][1] == "1903718606535395"


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
    """คลังข้อความสั้นพื้นสี — ทุกตัว ≤ 130 ตัวอักษร + มี preset_id + สีหมุนเวียนไม่ซ้ำติดกัน"""
    from app.services import facebook_intro
    posts = facebook_intro.short_bg_posts()
    assert len(posts) == 8
    preset_ids = []
    for p in posts:
        assert p["title"] and p["caption"] and p["preset_id"]
        assert len(p["caption"]) <= 130  # Facebook จำกัดข้อความพื้นสี ≤ 130 ตัวอักษร
        preset_ids.append(p["preset_id"])
    # 8 สีต่างกันหมด (หมุนเวียนไม่ซ้ำ) — ไม่งั้นจะโพสต์พื้นสีเดิมซ้ำกัน
    assert len(set(preset_ids)) == 8
