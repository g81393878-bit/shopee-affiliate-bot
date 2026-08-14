# -*- coding: utf-8 -*-
"""เทสต์ webhook endpoint (callback) — ครอบ dispatch + message_text ผ่าน HTTP จริง.

ใช้ LINE_SECRET แบบ mock เพื่อเข้า branch parse เอง (ไม่ต้องมีลายเซ็น) — แยกไฟล์
เพราะ import app.main (FastAPI app เต็ม) เพิ่มน้ำหนักเฉพาะชุดนี้.
"""
import pytest

import app.api.line_bot as lb  # noqa: E402


def test_webhook_mock_parse(monkeypatch, sim):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(lb, "LINE_SECRET", "mock_line_channel_secret")
    client = TestClient(app)

    payload = {
        "destination": "xxxxxxxx",
        "events": [{
            "type": "message",
            "replyToken": "rt_test",
            "message": {"type": "text", "id": "m1", "text": "หูฟัง"},
            "source": {"type": "user", "userId": "U_cust_1"},
            "timestamp": 1625682000000,
        }],
    }
    resp = client.post("/api/webhooks/line", json=payload)
    assert resp.status_code == 200
    assert len(sim.replies) == 1  # message_text ตอบการ์ดสินค้า → reply ถูก capture


def test_webhook_missing_signature_rejected(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    # secret จริง (ไม่ mock) + ไม่มี x-line-signature → 400
    monkeypatch.setattr(lb, "LINE_SECRET", "not_mock_secret")
    client = TestClient(app)
    resp = client.post("/api/webhooks/line", json={"destination": "x", "events": []})
    assert resp.status_code == 400
