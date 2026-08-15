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


def test_cron_facebook_post_dedup(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(cron, "_authorized", lambda t: True)
    monkeypatch.setattr(cron, "generate_script_for_product", _fake_script)
    posted = []
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


def test_cron_facebook_post_requires_token(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(cron, "_authorized", lambda t: False)
    client = TestClient(app)
    r = client.post("/api/cron/facebook-post", params={"token": "wrong"})
    assert r.status_code == 401
