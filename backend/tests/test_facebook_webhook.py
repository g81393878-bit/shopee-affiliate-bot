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
    monkeypatch.setattr(
        fb,
        "_reply_to_facebook",
        lambda rid, text, *args, **kwargs: sent.append((rid, text)) or True,
    )
    client = TestClient(app)

    payload = {"object": "page", "entry": [{"id": "1", "messaging": [
        {"sender": {"id": "1001"}, "message": {"text": "สวัสดีค่ะ"}},
    ]}]}
    resp = client.post("/api/webhooks/facebook", json=payload)
    assert resp.status_code == 200
    assert len(sent) == 1 and sent[0][0] == "1001"
    assert "ปลาสลิด" in sent[0][1] and "390.-" in sent[0][1]


def test_verify_signature_sha1_supported(monkeypatch):
    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    body = b"hello"
    assert fb._verify_signature(body, _sign(body, "my_secret", "sha1")) is True
    assert fb._verify_signature(body, "sha256=deadbeef") is False
    assert fb._verify_signature(body, "") is False


def test_csv_faq_origin_and_guarantee_in_messenger(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "mock_facebook_app_secret")
    sent = []
    monkeypatch.setattr(
        fb,
        "_reply_to_facebook",
        lambda rid, text, *args, **kwargs: sent.append((rid, text)) or True,
    )
    client = TestClient(app)

    for q_text, expected_kw in [
        ("ปลาบางบ่อไหม", "ปลาสลิดสุพรรณบุรีแท้ 100%"),
        ("มีรับประกันไหม", "รับประกัน"),
        ("สั่งยังไงคะ", "พิมพ์สั่งในแชทเพจนี้ได้เลยค่ะ"),
        ("ทำไมชุด 2 กิโลไม่มีเก็บเงินปลายทาง", "รถควบคุมอุณหภูมิ"),
    ]:
        sent.clear()
        payload = {"object": "page", "entry": [{"id": "1307380735783361", "messaging": [
            {"sender": {"id": "27904143002574068"}, "message": {"text": q_text}},
        ]}]}
        resp = client.post("/api/webhooks/facebook", json=payload)
        assert resp.status_code == 200
        assert len(sent) == 1
        assert expected_kw in sent[0][1], f"Expected {expected_kw} in reply for {q_text}"


def test_get_verify_rejects_wrong_mode(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_VERIFY_TOKEN", "my_token")
    client = TestClient(app)
    resp = client.get("/api/webhooks/facebook", params={
        "hub.mode": "unsubscribe",
        "hub.verify_token": "my_token",
        "hub.challenge": "CHALLENGE_123",
    })
    assert resp.status_code == 403


def test_get_verify_rejects_missing_challenge(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_VERIFY_TOKEN", "my_token")
    client = TestClient(app)
    resp = client.get("/api/webhooks/facebook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "my_token",
        # ไม่ส่ง hub.challenge — Facebook ต้องมีเสมอ
    })
    assert resp.status_code == 403


def test_get_verify_rejects_missing_token(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_VERIFY_TOKEN", "my_token")
    client = TestClient(app)
    resp = client.get("/api/webhooks/facebook", params={
        "hub.mode": "subscribe",
        "hub.challenge": "CHALLENGE_123",
        # ไม่ส่ง hub.verify_token
    })
    assert resp.status_code == 403


def test_post_rejects_missing_signature_header(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    # secret จริง (ไม่ mock) แต่ไม่ส่ง header ลายเซ็น → ต้อง reject
    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    monkeypatch.setattr(fb, "FACEBOOK_PAGE_ACCESS_TOKEN", "")
    client = TestClient(app)
    resp = client.post("/api/webhooks/facebook",
                       json={"object": "page", "entry": []})
    assert resp.status_code == 400


def test_post_accepts_sha1_fallback_header(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    monkeypatch.setattr(fb, "FACEBOOK_PAGE_ACCESS_TOKEN", "")
    client = TestClient(app)

    payload = {"object": "page", "entry": []}
    body = json.dumps(payload).encode()
    # header เก่าแบบ sha1 (ไม่ใช่ -256) — code รองรับ fallback
    resp = client.post("/api/webhooks/facebook", content=body, headers={
        "Content-Type": "application/json",
        "X-Hub-Signature": _sign(body, "my_secret", "sha1"),
    })
    assert resp.status_code == 200


def test_post_rejects_unknown_algo(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    monkeypatch.setattr(fb, "FACEBOOK_PAGE_ACCESS_TOKEN", "")
    client = TestClient(app)
    resp = client.post("/api/webhooks/facebook",
                       json={"object": "page", "entry": []},
                       headers={"X-Hub-Signature-256": "sha512=deadbeef"})
    assert resp.status_code == 400


def test_post_rejects_malformed_signature(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    monkeypatch.setattr(fb, "FACEBOOK_PAGE_ACCESS_TOKEN", "")
    client = TestClient(app)
    # ไม่มี "=" → _verify_signature คืน False → reject
    resp = client.post("/api/webhooks/facebook",
                       json={"object": "page", "entry": []},
                       headers={"X-Hub-Signature-256": "noequalsmark"})
    assert resp.status_code == 400


def test_verify_signature_edge_cases(monkeypatch):
    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "my_secret")
    body = b"payload"
    # ไม่มีตัวคั่น "="
    assert fb._verify_signature(body, "noseparator") is False
    # algorithm ที่ไม่รู้จัก (รองรับแค่ sha256 / sha1)
    assert fb._verify_signature(body, "sha512=" + "0" * 40) is False
    # signature ว่าง
    assert fb._verify_signature(body, "") is False
    # whitespace หน้าหลัง → strip แล้วยังตรงกันได้
    good = _sign(body, "my_secret", "sha256")
    assert fb._verify_signature(body, "  " + good + "  ") is True


def test_post_message_cold_pack_upcountry_spoilage(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "mock_facebook_app_secret")
    sent_text = []
    monkeypatch.setattr(
        fb,
        "_reply_to_facebook",
        lambda rid, text, *args, **kwargs: sent_text.append((rid, text)) or True,
    )
    client = TestClient(app)

    payload = {"object": "page", "entry": [{"id": "1", "messaging": [
        {"sender": {"id": "2002"}, "message": {"text": "ส่งต่างจังหวัดปลาจะเสียไหม?"}},
    ]}]}
    resp = client.post("/api/webhooks/facebook", json=payload)
    assert resp.status_code == 200
    assert len(sent_text) == 1 and sent_text[0][0] == "2002"
    assert "ไม่เสีย" in sent_text[0][1]
    assert "ซองฟอยล์เก็บอุณหภูมิ" in sent_text[0][1]
    assert "รับประกันความสด 100%" in sent_text[0][1]


def test_edge_faqs_and_out_of_csv_weird_question(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(fb, "FACEBOOK_APP_SECRET", "mock_facebook_app_secret")
    sent_text = []
    tg_alerts = []
    monkeypatch.setattr(
        fb,
        "_reply_to_facebook",
        lambda rid, text, *args, **kwargs: sent_text.append((rid, text)) or True,
    )
    monkeypatch.setattr(
        fb,
        "_send_telegram_alert",
        lambda text: tg_alerts.append(text) or True,
    )
    client = TestClient(app)

    # 1. FAQ_23 (ต่อราคา), FAQ_24 (ฮาลาล), FAQ_25 (ผู้สูงอายุ/ก้าง), FAQ_26 (ส่งต่างประเทศ)
    for q, expected_kw in [
        ("ลดอีกได้ไหมคะ", "โปรโมชั่นลดพิเศษ"),
        ("อิสลามทานได้ไหมคะ", "ฮาลาล"),
        ("ผู้สูงอายุทานได้ไหม ก้างเยอะไหม", "เค็มน้อย 3%"),
        ("ส่งต่างประเทศไหมคะ", "77 จังหวัด"),
    ]:
        sent_text.clear()
        resp = client.post("/api/webhooks/facebook", json={
            "object": "page",
            "entry": [{"id": "1307380735783361", "messaging": [{"sender": {"id": "3001"}, "message": {"text": q}}]}],
        })
        assert resp.status_code == 200
        assert len(sent_text) == 1
        assert expected_kw in sent_text[0][1]

    # 2. คำถามแปลกนอก CSV -> ต้องตอบรับเรื่องอย่างสุภาพ (ไม่ส่ง MENU_SHORT เดิมๆ) และแจ้งเตือนเข้า Telegram
    sent_text.clear()
    tg_alerts.clear()
    resp = client.post("/api/webhooks/facebook", json={
        "object": "page",
        "entry": [{"id": "1307380735783361", "messaging": [{"sender": {"id": "3002"}, "message": {"text": "ขอแลกกับข้าวสารหอมมะลิ 2 ถุงได้ไหมครับ"}}]}],
    })
    assert resp.status_code == 200
    assert len(sent_text) == 1
    assert len(tg_alerts) == 1
    assert "พบคำถามใหม่นอก CSV" in tg_alerts[0]
