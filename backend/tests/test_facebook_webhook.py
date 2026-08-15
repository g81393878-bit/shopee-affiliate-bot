# -*- coding: utf-8 -*-
"""เทสต์ Facebook webhook — GET verify (challenge) + POST signature + bypass dev.

ครอบ endpoint /api/webhooks/facebook ผ่าน HTTP จริง (TestClient) — mock ส่งเน็ต
(FACEBOOK_PAGE_ACCESS_TOKEN = "" กัน httpx ยิง Send API จริง) แยกไฟล์เพราะ
import app.main (FastAPI app เต็ม) เพิ่มน้ำหนักเฉพาะชุดนี้
"""
import hashlib
import hmac
import json

import app.api.facebook_bot as fb  # noqa: E402


def _sign(body: bytes, secret: str, algo: str = "sha256") -> str:
    digest = hmac.new(secret.encode(), body, getattr(hashlib, algo)).hexdigest()
    return f"{algo}={digest}"


def test_get_verify_returns_challenge(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_VERIFY_TOKEN", "my_token")
    client = TestClient(app)
    resp = client.get("/api/webhooks/facebook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "my_token",
        "hub.challenge": "CHALLENGE_123",
    })
    assert resp.status_code == 200
    assert resp.text == "CHALLENGE_123"  # ต้องคืน challenge เป็น plain text


def test_get_verify_rejects_bad_token(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_VERIFY_TOKEN", "my_token")
    client = TestClient(app)
    resp = client.get("/api/webhooks/facebook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "CHALLENGE_123",
    })
    assert resp.status_code == 403


def test_post_valid_signature_accepted(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    monkeypatch.setattr(fb, "FACEBOOK_PAGE_ACCESS_TOKEN", "")  # กันยิง Send API จริง
    client = TestClient(app)

    payload = {"object": "page", "entry": [{"id": "1", "messaging": []}]}
    body = json.dumps(payload).encode()
    resp = client.post("/api/webhooks/facebook", content=body, headers={
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign(body, "my_secret"),
    })
    assert resp.status_code == 200


def test_post_invalid_signature_rejected(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    client = TestClient(app)
    resp = client.post("/api/webhooks/facebook",
                       json={"object": "page", "entry": []},
                       headers={"X-Hub-Signature-256": "sha256=deadbeef"})
    assert resp.status_code == 400


def test_post_bypass_when_mock_secret(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    # secret ยัง mock (dev/test) → รับโดยไม่ตรวจลายเซ็น (เหมือน LINE bot)
    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "mock_facebook_app_secret")
    monkeypatch.setattr(fb, "FACEBOOK_PAGE_ACCESS_TOKEN", "")
    client = TestClient(app)
    resp = client.post("/api/webhooks/facebook", json={"object": "page", "entry": []})
    assert resp.status_code == 200


def test_post_message_replies_bot_intro(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "mock_facebook_app_secret")
    sent = []
    monkeypatch.setattr(fb, "_reply_to_facebook",
                        lambda rid, text: sent.append((rid, text)) or True)
    client = TestClient(app)

    payload = {"object": "page", "entry": [{"id": "1", "messaging": [
        {"sender": {"id": "1001"}, "message": {"text": "หูฟัง"}},
    ]}]}
    resp = client.post("/api/webhooks/facebook", json=payload)
    assert resp.status_code == 200
    assert len(sent) == 1 and sent[0][0] == "1001"
    # ตอบแนะนำบอทป้าเข็ม ไม่ค้นสินค้า/ไม่โพสต์สินค้า
    assert sent[0][1] == fb.BOT_INTRO
    assert "ป้าเข็ม" in sent[0][1] and "LINE" in sent[0][1]


def test_verify_signature_sha1_supported(monkeypatch):
    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    body = b"hello"
    assert fb._verify_signature(body, _sign(body, "my_secret", "sha1")) is True
    assert fb._verify_signature(body, "sha256=deadbeef") is False
    assert fb._verify_signature(body, "") is False


def test_bot_intro_includes_line_oa_url_when_set():
    intro = fb._build_intro("https://line.me/R/ti/p/@pakhem")
    assert "https://line.me/R/ti/p/@pakhem" in intro
    assert "แอดไลน์" in intro


def test_bot_intro_fallback_without_url():
    intro = fb._build_intro("")
    assert "แอดไลน์ร้าน" in intro
    assert "ป้าเข็ม ขายของ" in intro
    assert "line.me" not in intro
