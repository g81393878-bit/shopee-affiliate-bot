# -*- coding: utf-8 -*-
"""backend/tests/test_master_template.py — ทดสอบความถูกต้องของแม่แบบมาตรฐานสตูดิโอ (Master Template Spec)"""
import pytest
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
REELS_DIR = ROOT_DIR / "reels_uploader"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(REELS_DIR) not in sys.path:
    sys.path.insert(0, str(REELS_DIR))

import master_template_config as mtc


def test_master_template_constants():
    assert mtc.CANVAS_W == 1080
    assert mtc.CANVAS_H == 1920
    assert mtc.BADGE_CONFIG["w"] == 440
    assert mtc.BADGE_CONFIG["h"] == 46
    assert mtc.HERO_FRAME_CONFIG["w"] == 960
    assert mtc.HERO_FRAME_CONFIG["h"] == 500
    assert mtc.CARD_CONTAINER_CONFIG["w"] == 960
    assert mtc.CARD_CONTAINER_CONFIG["h"] == 600
    assert mtc.STEP_ROW_CONFIG["w"] == 888
    assert mtc.STEP_ROW_CONFIG["h"] == 130
    assert mtc.TTS_CONFIG["rate"] == "+0%"


def test_clean_master_text_removes_glitches():
    dirty = "🚨 “ทริคเด็ด” สำหรับแม่บ้าน 📌 https://bit.ly/test <p>ล้างง่าย</p>"
    clean = mtc.clean_master_text(dirty)
    assert "🚨" not in clean
    assert "📌" not in clean
    assert "http" not in clean
    assert "<p>" not in clean
    assert "“" not in clean
    assert clean == "ทริคเด็ด สำหรับแม่บ้าน ล้างง่าย"


def test_format_master_step_budget_and_no_dangling():
    long_text = "เทเบกกิ้งโซดาผสมน้ำส้มสายชูลงไปในท่อระบายน้ำเพื่อ"
    formatted = mtc.format_master_step(long_text, max_chars=40)
    assert len(formatted) <= 40
    assert not formatted.endswith("เพื่อ")
    assert not formatted.endswith("ที่")


def test_validate_master_inputs():
    valid, errors = mtc.validate_master_inputs(
        hook="ท่อน้ำตัน อย่าเพิ่งรื้อ!",
        steps=[
            "เทเบกกิ้งโซดา 1 ถ้วยลงในท่อ",
            "ราดน้ำส้มสายชูตาม รอ 5 นาที",
            "เปิดน้ำร้อนล้างตาม ท่อโล่งทันที"
        ],
        mode="LIFE_HACK_TIP"
    )
    assert valid is True
    assert len(errors) == 0

    # ทดสอบกรณีตัวหนังสือยาวเกิน
    invalid, errors_inv = mtc.validate_master_inputs(
        hook="ข้อความ Hook นี้ยาวมากเกินกว่าที่กำหนดไว้ในแม่แบบอย่างแน่นอนที่สุดเกินกว่าโควต้า 45 ตัวอักษรอย่างชัดเจน",
        steps=["สั้น"] * 3,
        mode="LIFE_HACK_TIP"
    )
    assert invalid is False
    assert any("Hook ยาวเกินแม่แบบ" in e for e in errors_inv)


def test_sanitize_video_filename():
    import standalone_content_generator as scg
    fn1 = scg.sanitize_video_filename("ทริคกระทะไหม้:ทำตามนี้*ง่ายๆ?.mp4")
    assert ":" not in fn1
    assert "*" not in fn1
    assert "?" not in fn1
    assert fn1.endswith(".mp4")
    assert "ทริคกระทะไหม้" in fn1

    fn2 = scg.sanitize_video_filename("วิดีโอ_ไม่มีนามสกุล")
    assert fn2.endswith(".mp4")

    fn3 = scg.sanitize_video_filename("")
    assert fn3.endswith(".mp4")


def test_typography_hero_card_fallback():
    import video_template_engine as vte
    thm = vte.THEME_PALETTES["LIFE_HACK_TIP"]
    card = vte.create_typography_hero_card(
        w=960,
        h=660,
        thm=thm,
        title="AI วาดรูปฟรีตัวนี้เทพมาก ลองแล้ว",
        phase_idx=0,
        mode="LIFE_HACK_TIP"
    )
    assert card is not None
    assert card.size == (960, 660)
    assert card.mode == "RGBA"

    posters = vte.render_cinematic_template_posters(
        mode="LIFE_HACK_TIP",
        topic_data={
            "title": "AI วาดรูปฟรีตัวนี้เทพมาก ลองแล้ว",
            "hook": "หยุดดู! AI ฟรีตัวนี้วาดรูปสวยเกินคาด",
        },
        hero_images=[None, None, None],
        takeaways=[
            "เปิดแอป Dora AI เลือก โมเดล Seedance 2.0",
            "พิมพ์คำอธิบายฉาก Action ที่ต้องการให้ชัด",
            "กดสร้างและรอรับคลิปวิดีโอ คุณภาพสูง"
        ]
    )
    assert len(posters) == 3
    for p in posters:
        assert p.size == (1080, 1920)

