# -*- coding: utf-8 -*-
"""Hermes AI — สมองกลเรียนรู้ตลาด & วิเคราะห์ยอดสั่งซื้อปลาสลิดป้าเข็มแบบ Hot-Reload.

วิเคราะห์:
1. `direct_orders` (ยอดสั่งซื้อปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม: แพ็กเกจขายดี, สัดส่วนโอนเงิน vs COD, ช่องทางที่ขายดี)
2. `chat_logs` + `facebook_demand_events` ย้อนหลัง
แล้วให้ Groq สรุปปรับ `trending_categories` / `radar_min_demand_score` / `pa_khem_tone` /
`fish_focus_package` / `fish_marketing_strategy` เก็บลง `system_preferences` (Supabase, key="hermes_skills")
ให้บอททุกช่องทางแชร์สมองกลก้อนเดียวกัน

ใช้จาก `tools/hermes_brain.py` (CLI) หรือ cron endpoint บน Render (M2).

ฟังก์ชันแยกเป็นชั้น testable: gather (aggregation ล้วน) / merge (clamp) /
load+save (DB) / _call_llm (Groq failover) / analyze_market (orchestrate)
"""
import datetime
import json
import logging

from app import models
from app.config import settings
from app.services.llm_clients import call_with_backoff, groq_clients

logger = logging.getLogger(__name__)

HERMES_SKILLS_KEY = "hermes_skills"
DEFAULT_SKILLS = {
    "trending_categories": ["ทั่วไป"],
    "radar_min_demand_score": 70,
    "pa_khem_tone": "ใจดี เป็นกันเอง ช่วยเหลือเต็มที่",
}
# หมายเหตุ: radar_daily_post_limit **ไม่อยู่**ใน DEFAULT — ค่ายังไม่ตั้ง → คืน None
# ให้ facebook_radar fallback ไป env RADAR_MAX_DAILY_POSTS (แอดมินเป็นเจ้าของค่าจริง)
# Hermes override ได้เฉพาะตอน save ค่าเข้ามาจริง ๆ เท่านั้น ไม่งั้นทับ env เดิม.
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


def load_skills_safe(db) -> dict:
    """load_skills แบบไม่ crash — ตาราง system_preferences ยังไม่มี (dev / ก่อนรัน
    migration) → คืน default ครบ ไม่ทำเส้นทางแชท/คอนเทนต์หลักพัง."""
    try:
        return load_skills(db)
    except Exception as e:  # noqa: BLE001 — ตาราง optional ต้อง fail-open
        logger.warning(f"[Hermes] โหลด skills ไม่ได้ ({e}) — ใช้ default")
        return dict(DEFAULT_SKILLS)


def market_tone(db) -> str:
    """อ่าน pa_khem_tone (hot-reload จาก Hermes) — คืน str สำหรับ persona prompt.

    ใช้ load_skills_safe: ไม่มีตาราง/ค่า → คืน default tone (ใจดี เป็นกันเอง) ไม่งั้น
    cron analyze / LINE บอทจะ crash ตอนระบบยังไม่ migrate.
    """
    skills = load_skills_safe(db)
    return str(skills.get("pa_khem_tone") or "").strip()


# --- แปลง pa_khem_tone → วลีสั้นต่อท้ายข้อความแชท (hot-reload) ---
# ห้ามคืน raw tone จาก LLM ตรง ๆ (กันข้อความแปลก/โฆษณาเกินจริงเข้าห้องลูกค้า) —
# จับเฉพาะหมวดที่รู้จักแล้วตอบเป็น template คงที่แทน
VALUE_SIGNALS = ("คุ้ม", "ถูก", "ประหยัด", "ราคา", "งบ")
CARING_SIGNALS = ("ใจดี", "ปรึกษา", "ละเอียด", "เป็นกันเอง", "ช่วยเหลือ", "แนะนำ", "ใส่ใจ")


def market_emphasis_for(tone: str) -> str:
    """pa_khem_tone → วลีเสริมท้ายข้อความ (คืน "" ถ้า default/ว่าง/ไม่รู้จัก).

    Pure function — แยกออกมาให้เทสต์ได้โดยไม่ต้องต่อ DB. Default tone คืน ""
    (ยังไม่ learning → ไม่เปลี่ยนพฤติกรรมแชทเดิม).
    """
    t = (tone or "").strip()
    if not t or t == DEFAULT_SKILLS["pa_khem_tone"]:
        return ""
    if any(k in t for k in VALUE_SIGNALS):
        return "ช่วงนี้ป้าเข็มเน้นของคุ้ม ราคาเบา ๆ เป็นพิเศษนะจ๊ะ 💰"
    if any(k in t for k in CARING_SIGNALS):
        return "ช่วงนี้ป้าเข็มจะอธิบายละเอียด ๆ ใส่ใจเป็นพิเศษจ๊ะ 🤗"
    return ""


def market_emphasis(db) -> str:
    """market_emphasis_for(market_tone(db)) — hot-reload + fail-open เป็น ""."""
    return market_emphasis_for(market_tone(db))


def gather_fish_order_stats(db, hours: int = 48) -> dict:
    """รวบรวมสถิติยอดสั่งซื้อปลาสลิดป้าเข็มจากตาราง direct_orders (ทั้งสะสมทั้งหมดและย้อนหลัง N ชม.)."""
    cutoff = _now() - datetime.timedelta(hours=hours)
    empty_stats = {
        "total_orders_all_time": 0,
        "total_revenue_all_time": 0.0,
        "recent_orders_count": 0,
        "recent_revenue": 0.0,
        "package_breakdown": {"500g": 0, "1kg": 0, "2kg": 0},
        "payment_breakdown": {"TRANSFER": 0, "COD": 0},
        "status_breakdown": {},
        "channel_breakdown": {},
        "best_selling_package": "1kg",
        "cod_ratio_pct": 0.0,
    }
    try:
        all_orders = db.query(models.DirectOrder).all()
    except Exception as e:
        logger.warning(f"[Hermes] ไม่สามารถดึงข้อมูล direct_orders ได้ ({e})")
        return empty_stats

    total_orders = 0
    total_revenue = 0.0
    recent_orders = 0
    recent_revenue = 0.0
    pkg_counts = {"500g": 0, "1kg": 0, "2kg": 0}
    pay_counts = {"TRANSFER": 0, "COD": 0}
    status_counts: dict[str, int] = {}
    channel_counts: dict[str, int] = {}

    for o in all_orders:
        st = (o.status or "PENDING").strip().upper()
        status_counts[st] = status_counts.get(st, 0) + 1
        if st == "CANCELLED":
            continue

        price_val = float(o.price or 0.0)
        total_orders += 1
        total_revenue += price_val

        # เช็คเวลา created_at (รองรับทั้ง aware และ naive จาก SQLite/Postgres)
        created = o.created_at
        if created is not None:
            if created.tzinfo is None:
                created = created.replace(tzinfo=datetime.timezone.utc)
            if created >= cutoff:
                recent_orders += 1
                recent_revenue += price_val

        # แยกตามแพ็กเกจ (500g / 1kg / 2kg)
        pcode = (o.package_code or "").strip().lower()
        pname = (o.package_name or "").strip().lower()
        if "500" in pcode or "500" in pname:
            pkg_counts["500g"] += 1
        elif "2kg" in pcode or "2 กิโล" in pname or "2โล" in pname:
            pkg_counts["2kg"] += 1
        else:
            pkg_counts["1kg"] += 1

        # แยกตามวิธีชำระเงิน (โอนเงิน vs เก็บปลายทาง COD)
        pmethod = (o.payment_method or "").upper()
        if "COD" in pmethod or "ปลายทาง" in pmethod:
            pay_counts["COD"] += 1
        else:
            pay_counts["TRANSFER"] += 1

        # แยกตามช่องทางที่สั่งซื้อจาก note
        note = o.note or ""
        if "[LINE_UID:" in note or "LINE" in note.upper():
            ch = "LINE OA"
        elif "[FB_ID:" in note or "MESSENGER" in note.upper():
            ch = "Facebook Messenger"
        elif "คอมเมนต์" in note or "COMMENT" in note.upper():
            ch = "Facebook Comment"
        else:
            ch = "Web Storefront"
        channel_counts[ch] = channel_counts.get(ch, 0) + 1

    # หาแพ็กเกจขายดีอันดับ 1 (ถ้าเท่ากันหรือยังไม่มีออเดอร์ ให้ 1kg เป็นค่าเริ่มต้น)
    best_pkg = "1kg"
    max_pkg_cnt = -1
    for k in ("1kg", "500g", "2kg"):
        if pkg_counts[k] > max_pkg_cnt and pkg_counts[k] > 0:
            max_pkg_cnt = pkg_counts[k]
            best_pkg = k

    cod_ratio = round((pay_counts["COD"] / total_orders) * 100, 1) if total_orders > 0 else 0.0

    return {
        "total_orders_all_time": total_orders,
        "total_revenue_all_time": round(total_revenue, 2),
        "recent_orders_count": recent_orders,
        "recent_revenue": round(recent_revenue, 2),
        "package_breakdown": pkg_counts,
        "payment_breakdown": pay_counts,
        "status_breakdown": status_counts,
        "channel_breakdown": channel_counts,
        "best_selling_package": best_pkg,
        "cod_ratio_pct": cod_ratio,
    }


def gather_market_data(db, hours: int = 48) -> dict:
    """รวมข้อมูลตลาดย้อนหลัง N ชม. + ยอดสั่งซื้อปลาสลิด (direct_orders) + สถิติ Reels Insights -> report dict."""
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

    # ดึงประวัติสถิติ Reels/Post Insights ล่าสุด
    insights_history = []
    try:
        pref = db.query(models.SystemPreference).filter(models.SystemPreference.key == "facebook_insights_history").first()
        if pref and isinstance(pref.value, list):
            # เอาเฉพาะข้อมูลวิเคราะห์หลักของอันล่าสุด
            insights_history = [item.get("parsed_metrics", {}) for item in pref.value if item][:3]
    except Exception:
        pass

    fish_orders = gather_fish_order_stats(db, hours=hours)

    return {
        "chat_count": len(chats),
        "chat_categories_requested": chat_categories,
        "facebook_demand_count": len(demands),
        "facebook_demand_keywords": demand_keywords,
        "high_urgency_demands": high_urgency,
        "latest_facebook_insights": insights_history,
        "fish_orders": fish_orders,
    }


def merge_skills(current: dict, llm_result: dict) -> dict:
    """ผสานผล LLM เข้ากับ skills ปัจจุบัน — clamp radar_min_demand_score ให้ [50, 90] และเก็บกลยุทธ์ปลาสลิด."""
    merged = dict(current or DEFAULT_SKILLS)
    # radar_daily_post_limit เป็นของแอดมิน (env RADAR_MAX_DAILY_POSTS) — ห้าม persist
    # ผ่าน Hermes (เคยทำให้บอทโพสต์ระเบิด 21 ตัวในวินาทีเดียว)
    merged.pop("radar_daily_post_limit", None)

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

    fish_pkg = llm_result.get("fish_focus_package")
    if isinstance(fish_pkg, str) and fish_pkg.strip() in ("500g", "1kg", "2kg"):
        merged["fish_focus_package"] = fish_pkg.strip()

    fish_strat = llm_result.get("fish_marketing_strategy")
    if isinstance(fish_strat, str) and fish_strat.strip():
        merged["fish_marketing_strategy"] = fish_strat.strip()

    return merged


def _build_prompt(report: dict, current: dict) -> dict:
    return {
        "market_data": report,
        "current_skills": current,
        "instruction": (
            "You are Hermes AI, the master brain behind 'Pa Khem' (ร้านปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม "
            "and Thai e-commerce assistant). Analyze the market_data, especially 'fish_orders' "
            "(DirectOrders of ปลาสลิดแดดเดียว ไซส์จัมโบ้ 6 ตัวโล: 500g=390 THB transfer/410 COD, "
            "1kg=550 THB transfer/570 COD, 2kg=1,090 THB transfer free cold-chain shipping, no COD). "
            "1. Identify top 3 trending_categories. "
            "2. Decide radar_min_demand_score (50-90, default 70). "
            "3. Adjust 'pa_khem_tone' to suit customers. "
            "4. Choose 'fish_focus_package' ('500g', '1kg', or '2kg') to promote next based on fish_orders. "
            "5. Write 'fish_marketing_strategy' in Thai: actionable advice on how to boost fish sales "
            "and encourage bank transfer (free shipping) over COD based on current package_breakdown, "
            "payment_breakdown, and channel_breakdown. "
            "Return ONLY valid JSON with keys: trending_categories (list of str), "
            "radar_min_demand_score (int), pa_khem_tone (str), fish_focus_package (str), "
            "fish_marketing_strategy (str), and reason (str)."
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
            response = call_with_backoff(
                lambda: client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a JSON-only response bot."},
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    timeout=60,
                ),
                circuit_key=client.api_key,
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
    fish = report.get("fish_orders") or {}
    ts = timestamp or _now()
    top_cats = list(report.get("chat_categories_requested", {}).keys())[:5]

    fish_section = ""
    if fish:
        pkg_bd = fish.get("package_breakdown", {})
        pay_bd = fish.get("payment_breakdown", {})
        ch_bd = fish.get("channel_breakdown", {})
        fish_section = (
            "## 🐟 สถานะยอดสั่งซื้อปลาสลิดป้าเข็ม (Direct Orders)\n"
            f"* **ยอดสั่งซื้อสะสมทั้งหมด**: {fish.get('total_orders_all_time', 0)} ออเดอร์ "
            f"(รายได้รวม {fish.get('total_revenue_all_time', 0.0):,.2f} บาท)\n"
            f"* **ยอดสั่งซื้อใหม่ (48h)**: {fish.get('recent_orders_count', 0)} ออเดอร์ "
            f"(รายได้ {fish.get('recent_revenue', 0.0):,.2f} บาท)\n"
            f"* **แพ็กเกจขายดีอันดับ 1**: `{fish.get('best_selling_package', '1kg')}` "
            f"(500g: {pkg_bd.get('500g', 0)} | 1kg: {pkg_bd.get('1kg', 0)} | 2kg: {pkg_bd.get('2kg', 0)})\n"
            f"* **วิธีชำระเงิน**: โอนเงิน {pay_bd.get('TRANSFER', 0)} | เก็บปลายทาง COD {pay_bd.get('COD', 0)} "
            f"(สัดส่วน COD: {fish.get('cod_ratio_pct', 0.0)}%)\n"
            f"* **ช่องทางที่ลูกค้าสั่งซื้อ**: {json.dumps(ch_bd, ensure_ascii=False)}\n"
            f"* **แพ็กเกจที่ Hermes แนะนำให้ดันต่อ**: `{skills.get('fish_focus_package', fish.get('best_selling_package', '1kg'))}`\n"
            f"* **กลยุทธ์การตลาดปลาสลิด**: {skills.get('fish_marketing_strategy', 'เน้นโปรโอนเงินส่งฟรีทุกชุด')}\n\n"
        )

    return (
        "# 🧠 Pa Khem Market & Fish Sales Memory (Hermes AI)\n\n"
        "บันทึกข้อเท็จจริง/แนวโน้มยอดขายปลาสลิดแดดเดียวและตลาดที่ Hermes วิเคราะห์ (Hot-Reload skills)\n\n"
        f"{fish_section}"
        "## 📊 สถานะตลาดและแชทล่าสุด\n"
        f"* **เวลา**: {ts.isoformat()}\n"
        f"* **LINE Chats (48h)**: {report.get('chat_count', 0)} (Top: {top_cats})\n"
        f"* **Facebook Demands (48h)**: {report.get('facebook_demand_count', 0)} "
        f"(High Urgency: {report.get('high_urgency_demands', 0)})\n"
        f"* **เหตุผลวิเคราะห์รวม (LLM)**: {reason or 'N/A'}\n\n"
        "## ⚙️ Active Bot Skills (Hot-Reloaded)\n"
        "```json\n" + json.dumps(skills, indent=2, ensure_ascii=False) + "\n```\n"
    )
