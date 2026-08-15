# -*- coding: utf-8 -*-
"""Hermes AI — สมองกลเรียนรู้ตลาด ปรับนิสัยบอทป้าเข็มแบบ Hot-Reload.

วิเคราะห์ `chat_logs` + `facebook_demand_events` ย้อนหลัง แล้วให้ Groq สรุป
ปรับ `trending_categories` / `radar_min_demand_score` / `pa_khem_tone` เก็บลง
`system_preferences` (Supabase, key="hermes_skills") ให้บอท LINE (Render) กับ
radar (local) แชร์สมองกลก้อนเดียวกัน

ใช้จาก `tools/hermes_brain.py` (CLI) หรือ cron endpoint บน Render (M2).

ฟังก์ชันแยกเป็นชั้น testable: gather (aggregation ล้วน) / merge (clamp) /
load+save (DB) / _call_llm (Groq failover) / analyze_market (orchestrate)
"""
import datetime
import json
import logging

from app import models
from app.config import settings
from app.services.llm_clients import groq_clients

logger = logging.getLogger(__name__)

HERMES_SKILLS_KEY = "hermes_skills"
DEFAULT_SKILLS = {
    "trending_categories": ["ทั่วไป"],
    "radar_min_demand_score": 70,
    "radar_daily_post_limit": 5,
    "pa_khem_tone": "ใจดี เป็นกันเอง ช่วยเหลือเต็มที่",
}
MIN_DEMAND_SCORE = 50
MAX_DEMAND_SCORE = 90


def _now() -> datetime.datetime:
    """เวลาปัจจุบันแบบ timezone-aware — ห้ามใช้ datetime.utcnow() (naive)
    เทียบกับคอลัมน์ DateTime(timezone=True) แล้วเพี้ยนบน Postgres"""
    return datetime.datetime.now(datetime.timezone.utc)


def load_skills(db) -> dict:
    """อ่าน hermes_skills จาก system_preferences — merge กับ DEFAULT (คีย์ขาดใช้ default)."""
    pref = (db.query(models.SystemPreference)
              .filter(models.SystemPreference.key == HERMES_SKILLS_KEY)
              .first())
    merged = DEFAULT_SKILLS.copy()
    if pref and isinstance(pref.value, dict):
        merged.update(pref.value)
    return merged


def save_skills(db, skills: dict) -> None:
    """upsert hermes_skills ลง system_preferences."""
    pref = (db.query(models.SystemPreference)
              .filter(models.SystemPreference.key == HERMES_SKILLS_KEY)
              .first())
    if pref:
        pref.value = skills
        pref.updated_at = _now()
    else:
        db.add(models.SystemPreference(key=HERMES_SKILLS_KEY, value=skills))
    db.commit()


def gather_market_data(db, hours: int = 48) -> dict:
    """รวมข้อมูลตลาดย้อนหลัง N ชม. → report dict (aggregation ล้วน ไม่แตะ LLM)."""
    cutoff = _now() - datetime.timedelta(hours=hours)

    chats = db.query(models.ChatLog).filter(models.ChatLog.created_at >= cutoff).all()
    chat_categories: dict = {}
    for c in chats:
        cat = (c.category or "").strip()
        if cat and cat.lower() != "unknown":
            chat_categories[cat] = chat_categories.get(cat, 0) + 1

    demands = (db.query(models.FacebookDemandEvent)
                 .filter(models.FacebookDemandEvent.created_at >= cutoff).all())
    demand_keywords: dict = {}
    high_urgency = 0
    for d in demands:
        kw = (d.product_keyword or "").strip()
        if kw:
            demand_keywords[kw] = demand_keywords.get(kw, 0) + 1
        if (d.urgency or "").lower() == "high":
            high_urgency += 1

    return {
        "chat_count": len(chats),
        "chat_categories_requested": chat_categories,
        "facebook_demand_count": len(demands),
        "facebook_demand_keywords": demand_keywords,
        "high_urgency_demands": high_urgency,
    }


def merge_skills(current: dict, llm_result: dict) -> dict:
    """ผสานผล LLM เข้ากับ skills ปัจจุบัน — clamp radar_min_demand_score ให้ [50, 90].

    LLM ปรับแค่ 3 ฟิลด์ (trending_categories / radar_min_demand_score /
    pa_khem_tone); radar_daily_post_limit คงค่าจาก current ไว้ (LLM ไม่แตะ).
    """
    merged = dict(current or DEFAULT_SKILLS)

    cats = llm_result.get("trending_categories")
    if isinstance(cats, list) and cats:
        merged["trending_categories"] = [str(c) for c in cats]

    if "radar_min_demand_score" in llm_result:
        try:
            score = int(llm_result["radar_min_demand_score"])
        except (TypeError, ValueError):
            score = int(merged.get("radar_min_demand_score", 70))
        merged["radar_min_demand_score"] = max(MIN_DEMAND_SCORE, min(score, MAX_DEMAND_SCORE))

    tone = llm_result.get("pa_khem_tone")
    if isinstance(tone, str) and tone.strip():
        merged["pa_khem_tone"] = tone.strip()

    return merged


def _build_prompt(report: dict, current: dict) -> dict:
    return {
        "market_data": report,
        "current_skills": current,
        "instruction": (
            "You are Hermes AI, the brain behind 'Pa Khem' (an expert Thai e-commerce "
            "affiliate bot). Analyze the market_data. Identify the top 3 trending_categories. "
            "Decide radar_min_demand_score (usually 70, lower to 60 if demand is very low, "
            "max 85 if too much spam). Decide pa_khem_tone (suggest a Thai persona/tone string "
            "based on the urgency and categories, e.g. 'เน้นความคุ้มค่า ของถูก' or "
            "'ใจดี ให้คำปรึกษา'). Return ONLY valid JSON with keys: trending_categories "
            "(list of str), radar_min_demand_score (int), pa_khem_tone (str), and reason (str)."
        ),
    }


def _call_llm(prompt: dict) -> dict | None:
    """เรียก Groq (วน key failover) → JSON dict หรือ None ถ้าล้มทุก key."""
    clients = groq_clients()
    if not clients:
        logger.warning("[Hermes] ไม่พบ GROQ_API_KEY")
        return None
    last_err = None
    for client in clients:
        try:
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a JSON-only response bot."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                timeout=60,
            )
            parsed = json.loads(response.choices[0].message.content)
            if not isinstance(parsed, dict):
                raise ValueError("LLM คืน JSON ที่ไม่ใช่ object")
            return parsed
        except Exception as e:
            last_err = e
            key = getattr(client, "api_key", "?")
            logger.warning(f"[Hermes] Groq key {str(key)[:8]}... failed: {e}")
    logger.error(f"[Hermes] Groq ล้มทุก key: {last_err}")
    return None


def analyze_market(db) -> dict | None:
    """รัน learning loop หนึ่งรอบ → {'skills', 'report', 'reason'} หรือ None (LLM ล้ม).

    LLM ล้ม → คืน None และ**ไม่เขียนทับ skills เดิม** (fail-safe).
    """
    report = gather_market_data(db)
    current = load_skills(db)
    llm_result = _call_llm(_build_prompt(report, current))
    if not llm_result:
        return None
    new_skills = merge_skills(current, llm_result)
    save_skills(db, new_skills)
    return {
        "skills": new_skills,
        "report": report,
        "reason": str(llm_result.get("reason", "")),
    }


def format_market_memory(result: dict, timestamp: datetime.datetime | None = None) -> str:
    """แปลงผล analyze_market เป็นเนื้อหา MARKET_MEMORY.md (pure function — ไม่เขียนไฟล์เอง)."""
    skills = result.get("skills", {})
    report = result.get("report", {})
    reason = result.get("reason", "")
    ts = timestamp or _now()
    top_cats = list(report.get("chat_categories_requested", {}).keys())[:5]
    return (
        "# 🧠 Shopee Market Memory (Hermes AI)\n\n"
        "บันทึกข้อเท็จจริง/แนวโน้มตลาดที่ Hermes วิเคราะห์ (Hot-Reload skills)\n\n"
        "## 📊 สถานะตลาดล่าสุด\n"
        f"* **เวลา**: {ts.isoformat()}\n"
        f"* **LINE Chats (48h)**: {report.get('chat_count', 0)} (Top: {top_cats})\n"
        f"* **Facebook Demands (48h)**: {report.get('facebook_demand_count', 0)} "
        f"(High Urgency: {report.get('high_urgency_demands', 0)})\n"
        f"* **เหตุผล LLM**: {reason or 'N/A'}\n\n"
        "## ⚙️ Active Bot Skills (Hot-Reloaded)\n"
        "```json\n" + json.dumps(skills, indent=2, ensure_ascii=False) + "\n```\n"
    )
