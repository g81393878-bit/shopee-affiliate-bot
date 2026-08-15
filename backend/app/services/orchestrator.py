# -*- coding: utf-8 -*-
"""Orchestrator — Claude (บอสใหญ่) คุมวง: รับงาน → วางแผน → สั่งทีมย่อย → ตรวจงาน

สถาปัตยกรรม "บอสสั่งการ" (แบบ NUANOSE: คน 1 คน + AI บอสคุมวง + AI ลูกน้อง):

    [เจ้าของร้าน/ผู้ใช้] ── โจทย์
            │
    [Claude = บอสใหญ่]  PLAN   แตกโจทย์เป็นขั้นตอน (JSON)
            │
            ├── worker "firecrawl" → web_search() ค้นข้อมูลเน็ต (เทรนด์/คู่แข่ง/ข้อเท็จจริง)
            ├── worker "groq"      → Groq เจนข้อความ (ถูก+เร็ว เหมาะงานร่าง)
            └── worker "claude"    → Claude คิดเหตุผลลึก/ตัดสินใจ
            │
    [Claude = บอสใหญ่]  REVIEW  รวมผลทุกขั้น → ตรวจทาน → คำตอบสุดท้าย

หลักการ:
  - บอส (Claude) = วางแผน + ตัดสินใจ + คุมคุณภาพ (งานแพงใช้ตรงนี้)
  - ลูกน้อง (Groq/Firecrawl) = งานถูก/ซ้ำ/หาข้อมูล (งานถูกใช้ตรงนี้)
  - Fallback: ถ้า Claude ไม่มี key/ล้ม → ลดขั้นเหลือ Groq ตอบตรง (บอทไม่พัง)

ผลลัพธ์ boss_orchestrate() คืน:
  {answer: str, plan: [dict], steps: [dict], boss: bool}
"""
import json
import logging
import re

from app.config import settings
from app.services.llm_clients import anthropic_clients, groq_clients

logger = logging.getLogger(__name__)

BOSS_SYSTEM = (
    "คุณคือ \"บอสใหญ่\" — หัวหน้าทีม AI ของร้าน \"ป้าเข็ม\" (แม่ค้าออนไลน์ผู้ช่วยช้อปปิ้ง) "
    "หน้าที่ของคุณคือรับโจทย์จากเจ้าของร้าน แล้วแตกเป็นแผน แบ่งให้ทีม AI ย่อยทำงาน "
    "แล้วตรวจทานผลรวมก่อนส่งมอบ"
)

# worker ที่รู้จัก — ตัวอื่นที่บอสส่งมาก็ยังรันได้ (default เป็น groq)
KNOWN_WORKERS = {"firecrawl", "groq", "claude"}

# โควตาควบคุมแผน — กันบอสวางแผนยาวเกิน/ใช้ตัวเอง(แพง+ช้า)มากไป
MAX_STEPS = 4
MAX_CLAUDE_STEPS = 1
# กัน worker ตัวไหน hang เกินงบ — Claude Opus รอบนึง ~40s, Groq/Firecrawl เร็ว
CLAUDE_TIMEOUT = 90
WORKER_TIMEOUT = 60


# ---------------------------------------------------------------------------
# เรียก worker แต่ละตัว (พร้อม failover หลาย key เหมือนที่อื่นใน repo)
# ---------------------------------------------------------------------------

def _claude_generate(prompt: str, system: str = BOSS_SYSTEM) -> str:
    """Claude (บอส) ตอบ — วน key จนกว่าจะสำเร็จ; ล้มทุก key คืน \"\" (ไม่ throw)"""
    clients = anthropic_clients()
    if not clients:
        return ""
    last_err = None
    for client in clients:
        try:
            resp = client.chat.completions.create(
                model=settings.ANTHROPIC_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                timeout=CLAUDE_TIMEOUT,
            )
            out = (resp.choices[0].message.content or "").strip()
            if out:
                return out
        except Exception as e:
            last_err = e
            logger.warning(f"[orchestrator] Claude key {client.api_key[:8]}... failed: {e}")
    logger.error(f"[orchestrator] Claude ล้มทุก key: {last_err}")
    return ""


def _groq_generate(prompt: str) -> str:
    """Groq (ลูกน้อง) เจนข้อความ — วน key จนสำเร็จ; ล้มคืน \"\" (ไม่ throw)"""
    clients = groq_clients()
    if not clients:
        return ""
    for client in clients:
        try:
            resp = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "คุณคือผู้ช่วยแม่ค้าออนไลน์ป้าเข็ม ตอบภาษาไทย ตรงประเด็น"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                timeout=WORKER_TIMEOUT,
            )
            out = (resp.choices[0].message.content or "").strip()
            if out:
                return out
        except Exception as e:
            logger.warning(f"[orchestrator] Groq key {client.api_key[:8]}... failed: {e}")
    return ""


def _firecrawl_research(query: str) -> str:
    """ลูกน้องค้นเน็ต (Tavily+Firecrawl ร่วมกัน) → คืน answer + ผลค้นย่อ"""
    try:
        from app.services.web_search import web_search
        data = web_search(query, max_results=3)
    except Exception as e:
        logger.warning(f"[orchestrator] web_search failed: {e}")
        return ""
    parts = []
    if (data.get("answer") or "").strip():
        parts.append(data["answer"].strip())
    for r in (data.get("results") or [])[:3]:
        title = (r.get("title") or "").strip()
        content = (r.get("content") or "").strip().replace("\n", " ")
        if title:
            parts.append(f"- {title}: {content[:200]}")
    return "\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# แปลงผล JSON ของบอส (Claude มักห่อด้วย ```json หรือเติมข้อความหน้า/หลัง)
# ---------------------------------------------------------------------------

def _extract_json(text: str):
    """ดึง JSON แรกจากข้อความ — ตัด fence/ข้อความนำ — คืน parsed object หรือ None"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # fallback: หาช่วง [ ... ] หรือ { ... } แรกสุด
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        i = t.find(open_ch)
        if i == -1:
            continue
        j = t.rfind(close_ch)
        if j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


def _parse_plan(text: str) -> list:
    """แปลงแผนบอส (JSON list) → list[dict{worker,task}] — ผิดรูปแบบ/ว่าง คืน []

    คุมโควตา: ตัดเกิน MAX_STEPS ขั้น; worker=claude เกิน MAX_CLAUDE_STEPS → โยนให้ groq
    (บอสใช้ตัวเองแค่ plan/review — งานกลางควรส่งลูกน้องถูก+เร็ว)"""
    data = _extract_json(text)
    raw = []
    if isinstance(data, dict):
        data = data.get("steps") or data.get("plan") or []
    if not isinstance(data, list):
        return []
    for item in data:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or item.get("action") or "").strip()
        worker = str(item.get("worker") or "groq").strip().lower()
        if not task:
            continue
        raw.append({"worker": worker if worker in KNOWN_WORKERS else "groq", "task": task})

    steps, claude_used = [], 0
    for item in raw:
        if len(steps) >= MAX_STEPS:
            break
        worker = item["worker"]
        if worker == "claude":
            claude_used += 1
            if claude_used > MAX_CLAUDE_STEPS:
                worker = "groq"
        steps.append({"worker": worker, "task": item["task"]})
    return steps


# ---------------------------------------------------------------------------
# โฟลว์หลัก
# ---------------------------------------------------------------------------

def boss_orchestrate(instruction: str) -> dict:
    """Claude บอสใหญ่ รับโจทย์ → วางแผน → สั่งทีมย่อย → ตรวจงาน → คำตอบสุดท้าย

    Fallback: Claude ไม่พร้อม (ไม่มี key/ล้ม) → Groq ตอบตรง 1 ครั้ง (boss=False)
    """
    instruction = (instruction or "").strip()
    if not instruction:
        return {"answer": "", "plan": [], "steps": [], "boss": False}

    # 1. PLAN — บอสแตกโจทย์เป็นแผน (JSON list ของ steps)
    plan_prompt = (
        f"โจทย์จากเจ้าของร้าน: {instruction}\n\n"
        "จงวางแผนการทำงานเป็นขั้นตอน 2-4 ขั้น สั้นๆ โดยแต่ละขั้นเลือก worker ที่เหมาะสมที่สุด:\n"
        "- worker \"firecrawl\" = ค้นข้อมูลจากเน็ต (เทรนด์/คู่แข่ง/ราคา/ข้อเท็จจริง)\n"
        "- worker \"groq\" = เขียน/เจนข้อความ (ถูก+เร็ว เหมาะงานร่าง)\n"
        "- worker \"claude\" = คิดเหตุผลลึก (ใช้อย่างมาก 1 ขั้น — งานร่าง/ค้นข้อมูลให้ส่ง groq/firecrawl)\n\n"
        "ตอบเป็น JSON list เท่านั้น (ห้ามใส่ markdown fence อย่าใส่ฟิลด์อื่น):\n"
        '[{"worker": "firecrawl|groq|claude", "task": "คำสั่งงานภาษาไทยสั้นๆ"}, ...]'
    )
    plan_text = _claude_generate(plan_prompt)
    plan = _parse_plan(plan_text)

    # Claude วางแผนไม่ได้ → fallback Groq ตอบตรง
    if not plan:
        logger.warning("[orchestrator] Claude วางแผนไม่สำเร็จ — fallback Groq ตอบตรง")
        return {"answer": _groq_generate(instruction), "plan": [], "steps": [], "boss": False}

    # 2. DISPATCH — รันแต่ละขั้นด้วย worker ที่บอสสั่ง
    steps = []
    for step in plan:
        worker, task = step["worker"], step["task"]
        if worker == "firecrawl":
            out = _firecrawl_research(task)
        elif worker == "claude":
            out = _claude_generate(task)
        else:  # groq
            out = _groq_generate(task)
        steps.append({"worker": worker, "task": task, "output": out})

    # 3. REVIEW — บอสตรวจงานทุกขั้น → คำตอบสุดท้าย
    step_summary = "\n\n".join(
        f"[ขั้น {i + 1} · worker={s['worker']}]\nงาน: {s['task']}\nผล: {s['output'] or '(ว่าง/ล้ม)'}"
        for i, s in enumerate(steps)
    )
    review_prompt = (
        f"โจทย์เดิมจากเจ้าของร้าน: {instruction}\n\n"
        f"ทีมงานทำงานเสร็จแล้ว นี่คือผลแต่ละขั้น:\n{step_summary}\n\n"
        "จงตรวจทานงานทั้งหมด แล้วเรียบเรียงคำตอบสุดท้ายให้เจ้าของร้าน:\n"
        "- รวมข้อมูลจากทุกขั้นให้ครบ ตรงโจทย์\n"
        "- น้ำเสียงเป็นกันเองแบบแม่ค้าออนไลน์ (ป้าเข็ม) ภาษาไทย\n"
        "- ขั้นไหนผลว่าง/ผิด ให้แก้ไข/เติมให้ถูกเอง\n"
        "- ตอบสั้นกระชับ ใช้ได้จริง"
    )
    answer = _claude_generate(review_prompt)

    # REVIEW ล้มแต่ขั้นย่อยมีผล → ต่อ text จากขั้นย่อยเป็นคำตอบสำรอง
    if not answer:
        answer = "\n".join(s["output"] for s in steps if s["output"])

    return {"answer": answer, "plan": plan, "steps": steps, "boss": True}


def orchestrate_product_content(name: str, category: str, price: float,
                                rating: float = 0.0, sales_count: int = 0,
                                commission: float = 0.0) -> dict:
    """ตัวช่วยสำเร็จรูป: ให้บอสใหญ่ผลิตคอนเทนต์ครบชุดสำหรับสินค้า 1 ตัว

    คืนโครงเดียวกับ boss_orchestrate() — answer = คอนเทนต์ชุด (hook/caption/…)
    """
    instruction = (
        f"สร้างคอนเทนต์ครบชุดสำหรับสินค้า \"{name}\" (หมวด {category}, "
        f"ราคา {price:,.0f} บาท, ขายแล้ว {sales_count:,} ชิ้น, คะแนน {rating}/5) "
        f"เพื่อทำคลิป TikTok/Reels แนะนำสินค้า affiliate "
        f"โดยมี hook, problem, solution, cta, caption, hashtags, title, thumbnail_prompt"
    )
    return boss_orchestrate(instruction)
