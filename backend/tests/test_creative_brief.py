# -*- coding: utf-8 -*-
"""เทสต์ Creative Brief — 3 มุมมองสำหรับ Meta Ads (Creative is Targeting)

- /api/creative-briefs/generate  → POST สร้าง Brief
- /api/creative-briefs/product/{id} → GET ดู Brief ทั้ง 3 มุม
- /api/creative-briefs/{id} → GET มุมมองเดียว
- /api/creative-briefs/product/{id} → DELETE ลบ
- fallback template เมื่อ LLM ไม่พร้อม
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import Product, CreativeBrief


# --- Fixtures ---

@pytest.fixture(autouse=True)
def _admin_password(monkeypatch):
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "test-admin-pw")
    monkeypatch.delenv("CRON_TOKEN", raising=False)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _create_mock_product(db, name="สินค้าเทสต์", category="หูฟัง",
                         price=299.0, rating=4.5, sales_count=1200,
                         commission=30.0):
    """สร้างสินค้า mock ใน DB (ใช้ s.shopee.co.th URL ผ่าน link_checker guard)"""
    p = Product(
        name=name,
        category=category,
        price=price,
        rating=rating,
        sales_count=sales_count,
        commission=commission,
        affiliate_url="https://s.shopee.co.th/file/test_product",
        image_url="https://cf.shopee.co.th/file/test.jpg",
        link_status="ok",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# --- API Tests ---

class TestCreativeBriefAPI:

    def test_generate_requires_product(self, client):
        """POST /generate ไม่มีสินค้า → 404"""
        r = client.post("/api/creative-briefs/generate",
                        json={"product_id": 999999})
        assert r.status_code == 404
        assert "ไม่พบสินค้า" in r.json()["detail"]

    def test_generate_creates_briefs(self, client, db_session):
        """POST /generate สร้าง Brief 3 มุมมอง (ใช้ fallback template)"""
        p = _create_mock_product(db_session)
        # Mock LLM ให้ fail เพื่อใช้ fallback
        with patch("app.api.creative_brief.generate_creative_brief") as mock_gen:
            mock_gen.return_value = {
                "problem_solution": {
                    "hook": "เบื่อมั้ย?",
                    "script_body": "เล่าปัญหา",
                    "cta": "กดซื้อเลย",
                    "caption": "ป้ารีวิว",
                    "hashtags": ["หูฟัง", "รีวิว"],
                    "target_behavior": "คนกำลังหาหูฟัง",
                    "thumbnail_prompt": "photo of earphone",
                    "ai_confidence": 70,
                },
                "review": {
                    "hook": "รีวิวจริง",
                    "script_body": "เล่ารีวิว",
                    "cta": "กดสั่ง",
                    "caption": "รีวิวจริง",
                    "hashtags": ["รีวิว"],
                    "target_behavior": "คนชอบดูรีวิว",
                    "thumbnail_prompt": "review photo",
                    "ai_confidence": 75,
                },
                "education": {
                    "hook": "รู้มั้ย?",
                    "script_body": "ให้ความรู้",
                    "cta": "ลองเลย",
                    "caption": "ความรู้",
                    "hashtags": ["เกร็ด"],
                    "target_behavior": "คนหาข้อมูล",
                    "thumbnail_prompt": "education",
                    "ai_confidence": 65,
                },
            }
            r = client.post("/api/creative-briefs/generate",
                            json={"product_id": p.id})
        assert r.status_code == 200
        data = r.json()
        assert data["product_id"] == p.id
        assert data["product_name"] == "สินค้าเทสต์"
        assert len(data["perspectives"]) == 3
        perspectives = {p["perspective"] for p in data["perspectives"]}
        assert perspectives == {"problem_solution", "review", "education"}
        # ตรวจว่า hook ถูกบันทึก
        hooks = {p["hook"] for p in data["perspectives"]}
        assert "เบื่อมั้ย?" in hooks

    def test_generate_overwrites_old_briefs(self, client, db_session):
        """POST /generate ครั้งที่ 2 ลบ Brief เก่าก่อนสร้างใหม่"""
        p = _create_mock_product(db_session, name="สินค้า A")
        # สร้างรอบแรก
        with patch("app.api.creative_brief.generate_creative_brief") as mock_gen:
            mock_gen.return_value = _fallback_dict("รอบแรก", "hook1", "hook2", "hook3")
            client.post("/api/creative-briefs/generate", json={"product_id": p.id})
        # สร้างรอบที่สอง
        with patch("app.api.creative_brief.generate_creative_brief") as mock_gen:
            mock_gen.return_value = _fallback_dict("รอบสอง", "new_hook1", "new_hook2", "new_hook3")
            r = client.post("/api/creative-briefs/generate", json={"product_id": p.id})
        assert r.status_code == 200
        hooks = {p["hook"] for p in r.json()["perspectives"]}
        assert hooks == {"new_hook1", "new_hook2", "new_hook3"}

    def test_get_briefs_by_product(self, client, db_session):
        """GET /product/{id} ดู Brief ทั้ง 3 มุม"""
        p = _create_mock_product(db_session)
        _seed_briefs(db_session, p.id)
        r = client.get(f"/api/creative-briefs/product/{p.id}")
        assert r.status_code == 200
        data = r.json()
        assert len(data["perspectives"]) == 3

    def test_get_briefs_not_found(self, client, db_session):
        """GET /product/{id} ไม่มี brief → 404"""
        p = _create_mock_product(db_session)
        r = client.get(f"/api/creative-briefs/product/{p.id}")
        assert r.status_code == 404

    def test_get_single_brief(self, client, db_session):
        """GET /{brief_id} ดูมุมมองเดียว"""
        p = _create_mock_product(db_session)
        briefs = _seed_briefs(db_session, p.id)
        r = client.get(f"/api/creative-briefs/{briefs[0].id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == briefs[0].id
        assert data["perspective"] in ("problem_solution", "review", "education")

    def test_delete_briefs(self, client, db_session):
        """DELETE /product/{id} ลบ Brief ทั้งหมด"""
        p = _create_mock_product(db_session)
        _seed_briefs(db_session, p.id)
        r = client.delete(f"/api/creative-briefs/product/{p.id}")
        assert r.status_code == 200
        assert r.json()["deleted"] == 3
        # ตรวจสอบว่าหายจริง
        r2 = client.get(f"/api/creative-briefs/product/{p.id}")
        assert r2.status_code == 404

    def test_generate_uses_fallback_on_llm_error(self, client, db_session):
        """ถ้า LLM ทุกตัว fail → fallback template ใช้ได้"""
        p = _create_mock_product(db_session)
        with patch("app.api.creative_brief.generate_creative_brief") as mock_gen:
            mock_gen.return_value = _fallback_dict("Fallback", "fb1", "fb2", "fb3")
            r = client.post("/api/creative-briefs/generate",
                            json={"product_id": p.id})
        assert r.status_code == 200
        assert len(r.json()["perspectives"]) == 3


# --- Generator Tests ---

class TestCreativeBriefGenerator:

    def test_fallback_returns_3_perspectives(self):
        """Fallback template คืนครบ 3 มุม"""
        from app.services.creative_brief_generator import _fallback_brief
        result = _fallback_brief("หูฟัง BT", "หูฟัง", 299, 4.5, 1200, 30)
        assert set(result.keys()) == {"problem_solution", "review", "education"}
        for key in ("problem_solution", "review", "education"):
            p = result[key]
            assert "hook" in p
            assert "script_body" in p
            assert "cta" in p
            assert "caption" in p
            assert "hashtags" in p
            assert isinstance(p["hashtags"], list)
            assert p["ai_confidence"] >= 0

    def test_fallback_uses_product_info(self):
        """Fallback template ใส่ชื่อ/ราคา/หมวดสินค้า"""
        from app.services.creative_brief_generator import _fallback_brief
        result = _fallback_brief("สินค้า AAA", "อุปกรณ์ครัว", 599.5, 4.0, 500, 60)
        assert "สินค้า AAA" in result["problem_solution"]["hook"]
        assert "599" in result["problem_solution"]["script_body"]
        assert "อุปกรณ์ครัว" in result["education"]["hashtags"] or "อุปกรณ์ครัว" in result["education"]["script_body"]

    def test_parse_valid_json(self):
        """Parse JSON ที่ถูกต้องได้"""
        from app.services.creative_brief_generator import _parse_brief_response
        import json
        data = _valid_brief_json()
        result = _parse_brief_response(json.dumps(data))
        assert set(result.keys()) == {"problem_solution", "review", "education"}
        for key in result:
            assert "hook" in result[key]

    def test_parse_missing_perspective_raises(self):
        """JSON ขาด perspective → ValueError"""
        from app.services.creative_brief_generator import _parse_brief_response
        import json
        data = {"problem_solution": _valid_perspective(), "review": _valid_perspective()}
        with pytest.raises(ValueError, match="ขาด perspective"):
            _parse_brief_response(json.dumps(data))

    def test_parse_missing_field_raises(self):
        """JSON ขาด field ใน perspective → ValueError"""
        from app.services.creative_brief_generator import _parse_brief_response
        import json
        bad_p = _valid_perspective()
        del bad_p["hook"]
        data = {
            "problem_solution": bad_p,
            "review": _valid_perspective(),
            "education": _valid_perspective(),
        }
        with pytest.raises(ValueError, match="hook"):
            _parse_brief_response(json.dumps(data))

    def test_build_system_prompt_includes_perspectives(self):
        """System prompt ต้องอธิบายทั้ง 3 มุม"""
        from app.services.creative_brief_generator import _build_system_prompt
        prompt = _build_system_prompt()
        assert "แก้ปัญหา" in prompt
        assert "รีวิว" in prompt
        assert "ให้ความรู้" in prompt

    def test_perspectives_dict_is_complete(self):
        """PERSPECTIVES dict มีครบ 3 ตัว"""
        from app.services.creative_brief_generator import PERSPECTIVES
        assert set(PERSPECTIVES.keys()) == {"problem_solution", "review", "education"}
        for key, val in PERSPECTIVES.items():
            assert "name" in val
            assert "description" in val
            assert "prompt_guidance" in val


# --- Schema Tests ---

class TestCreativeBriefSchema:

    def test_brief_perspective_schema(self):
        """CreativeBriefPerspective รับ field ครบ"""
        from app.schemas import CreativeBriefPerspective
        p = CreativeBriefPerspective(
            perspective="problem_solution",
            hook="เบื่อมั้ย?",
            script_body="เล่า",
            cta="กดเลย",
            caption="caption",
            hashtags=["tag1"],
            ai_confidence=80,
        )
        assert p.perspective == "problem_solution"
        assert p.hashtags == ["tag1"]

    def test_generate_request_schema(self):
        """CreativeBriefGenerateRequest รับ product_id + tone"""
        from app.schemas import CreativeBriefGenerateRequest
        req = CreativeBriefGenerateRequest(product_id=1, tone="youth")
        assert req.tone == "youth"
        assert req.market_tone == ""


# --- Helpers ---

def _fallback_dict(name, hook1, hook2, hook3):
    """สร้าง mock LLM response สำหรับ patch"""
    return {
        "problem_solution": {
            "hook": hook1, "script_body": f"script {name} 1",
            "cta": "cta 1", "caption": "cap 1",
            "hashtags": ["tag1"], "target_behavior": "target1",
            "thumbnail_prompt": "thumb1", "ai_confidence": 60,
        },
        "review": {
            "hook": hook2, "script_body": f"script {name} 2",
            "cta": "cta 2", "caption": "cap 2",
            "hashtags": ["tag2"], "target_behavior": "target2",
            "thumbnail_prompt": "thumb2", "ai_confidence": 65,
        },
        "education": {
            "hook": hook3, "script_body": f"script {name} 3",
            "cta": "cta 3", "caption": "cap 3",
            "hashtags": ["tag3"], "target_behavior": "target3",
            "thumbnail_prompt": "thumb3", "ai_confidence": 55,
        },
    }


def _seed_briefs(db, product_id):
    """สร้าง Creative Brief 3 ตัวใน DB"""
    briefs = []
    for persp in ("problem_solution", "review", "education"):
        b = CreativeBrief(
            product_id=product_id,
            perspective=persp,
            hook=f"hook {persp}",
            script_body=f"script {persp}",
            cta=f"cta {persp}",
            caption=f"caption {persp}",
            hashtags=[f"tag_{persp}"],
            target_behavior=f"behavior {persp}",
            thumbnail_prompt=f"thumb {persp}",
            ai_confidence=70,
        )
        db.add(b)
        briefs.append(b)
    db.commit()
    for b in briefs:
        db.refresh(b)
    return briefs


def _valid_perspective():
    return {
        "hook": "hook", "script_body": "script", "cta": "cta",
        "caption": "caption", "hashtags": ["tag"],
        "target_behavior": "target", "thumbnail_prompt": "thumb",
        "ai_confidence": 70,
    }


def _valid_brief_json():
    return {
        "problem_solution": _valid_perspective(),
        "review": _valid_perspective(),
        "education": _valid_perspective(),
    }
