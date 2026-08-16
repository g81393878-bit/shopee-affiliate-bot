"""Bot Profile (White-Label) — ตัวตนร้านต้องอ่านจาก config จุดเดียว ไม่ฝังชื่อแข็งในโค้ด"""
from app.services import bot_profile
from app.services import persona


def test_bot_profile_has_nonempty_defaults():
    # ไม่ตั้ง env ก็ต้องมีค่าตั้งต้น (กันบอทชื่อว่าง)
    assert bot_profile.BOT_NAME
    assert bot_profile.PERSONA_NAME
    assert bot_profile.BOT_SLOGAN


def test_env_helper_returns_default_when_empty():
    assert bot_profile._env("", "fallback") == "fallback"
    assert bot_profile._env("   ", "fallback") == "fallback"


def test_persona_prompt_uses_configured_names():
    # จุดสำคัญ: persona prompt ต้องสะท้อนชื่อที่ตั้งไว้ ไม่ใช่ฝัง "ป้าเข็ม" แข็ง ๆ
    assert persona.PERSONA_NAME in persona.PERSONA_PROMPT
    assert persona.BOT_NAME in persona.PERSONA_PROMPT


def test_line_bot_and_facebook_bot_share_bot_name():
    from app.api.line_bot import BOT_NAME as line_name
    from app.api.facebook_bot import BOT_NAME as fb_name
    assert line_name == bot_profile.BOT_NAME
    assert fb_name == bot_profile.BOT_NAME


def test_line_cta_footer_has_id_and_link():
    # ท้ายโพสต์ Facebook ต้องชวนแอดไลน์ครบทั้ง ID และลิงก์
    footer = bot_profile.line_cta_footer()
    assert bot_profile.LINE_OA_ID in footer
    assert bot_profile.LINE_OA_URL in footer


def test_line_cta_footer_override_url():
    footer = bot_profile.line_cta_footer("https://lin.ee/custom")
    assert "https://lin.ee/custom" in footer
    assert bot_profile.LINE_OA_ID in footer  # ID ยังติดครบทุกโพสต์
