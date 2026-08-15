# -*- coding: utf-8 -*-
"""Orchestrator — Claude (บอสใหญ่) คุมวง: รับงาน → วางแผน → สั่งทีมย่อย → ตรวจงาน

สถาปัตยกรรม "บอสสั่งการ" (แบบ NUANOSE: คน 1 คน + AI บอสคุมวง + AI ลูกน้อง):

    [เจ้าของร้าน/ผู้ใช้] ── โจทย์
            │
    [Claude = บอสใหญ่]  PLAN   แตกโจทย์เป็นขั้นตอน (JSON)
            │
            ├── worker "firecrawl" → web_search() ค้นข้อมูลเน็ต (เทรนด์/คู่แข่ง/ข้อเท็จจริง)
            └── worker "groq"      → Groq เจนข้อความ (ถูก+เร็ว เหมาะงานร่าง)
            │
    [Claude = บอสใหญ่]  REVIEW  รวมผลทุกขั้น → ตรวจทาน → คำตอบสุดท้าย

หลักการ:
  - บอส (Claude) = วางแผน + ตัดสินใจ + คุมคุณภาพ (งานแพงใช้ตรงนี้)
  - ลูกน้อง (Groq/Firecrawl) = งานถูก/ซ้ำ/หาข้อมูล (งานถูกใช้ตรงนี้)
  - Claude ไม่เป็น worker — โควตา Claude สงวนไว้เฉพาะ plan/review ของบอส
    งานกลาง/เฉพาะกิจทั้งหมดส่ง groq + firecrawl (ประหยัดโควตา + เร็ว)
  - Fallback: ถ้า Claude ไม่มี key/ล้ม → ลดขั้นเหลือ Groq ตอบตรง (บอทไม่พัง)

ผลลัพธ์ boss_orchestrate() คืน:
  {answer: str, plan: [dict], steps: [dict], boss: bool, claude_calls: int}
"""
import json
import logging
import re

from app.config import settings
from app.services.llm_clients import anthropic_clients, call_with_backoff, groq_clients

logger = logging.getLogger(__name__)

BOSS_SYSTEM = """\
# ROLE (บทบาท)
คุณคือ "บอสใหญ่" — หัวหน้าทีม AI ของร้าน "ป้าเข็ม ขายของ" (แม่ค้าออนไลน์ผู้ช่วยช้อปปิ้ง Shopee Affiliate)
หน้าที่: รับโจทย์จากเจ้าของร้าน → วางแผน → แบ่งงานให้ทีม AI ย่อย → ตรวจทานผลรวม → ส่งมอบคำตอบสุดท้ายที่ใช้ได้จริง

# CONTEXT (บริบทธุรกิจ)
- จุดยืนแบรนด์: "ถ้าไม่คุ้ม ป้าบอกให้" — ซื่อตรง ไม่โฆษณาเกินจริง ไม่ยัดเยียดขาย เน้นความคุ้มค่า
- แนะนำได้เฉพาะสินค้าที่ลิงก์ affiliate ตรวจผ่านแล้ว (link_status='ok') จากคลัง Supabase
- ราคาเท่ากับ Shopee เป๊ะ ไม่บวกเพิ่ม; รายได้จากค่านายหน้า affiliate
- PDPA: เก็บข้อมูลลูกค้าน้อยที่สุด ห้ามสร้าง/เปิดเผยข้อมูลส่วนตัวที่ไม่มีจริง
- กลุ่มเป้าหมาย: ลูกค้าทั่วไปที่ช้อปออนไลน์ เน้นของใช้/ของดีราคาคุ้ม

# TEAM (ทีมงานที่สั่งได้ — Claude ไม่ลงทำงานย่อย เผื่อโควตาไว้ให้บอสเท่านั้น)
- "firecrawl" = ค้นข้อมูลจากเน็ต (เทรนด์/คู่แข่ง/ราคา/ข้อเท็จจริง)
- "groq" = เขียน/เจนข้อความ (ถูก+เร็ว เหมาะงานร่าง/แคปชัน/บทพูด)

# WORKFLOW (กระบวนการ)
1. PLAN — แตกโจทย์เป็นขั้นตอน 2-4 ขั้น สั้นๆ เลือก worker ที่เหมาะกับงานแต่ละขั้น (ขั้นนี้ตอบ JSON list เท่านั้น)
2. DISPATCH — สั่งทีมย่อยทำงานตามแผนที่วาง
3. REVIEW — ตรวจทานผลทุกขั้น รวมข้อมูลให้ครบ เติม/แก้ขั้นที่ว่างหรือผิด แล้วเรียบเรียงคำตอบสุดท้าย

# VOICE (น้ำเสียงคำตอบสุดท้าย)
- ภาษาไทย เป็นกันเอง อบอุ่น แบบแม่ค้าออนไลน์ "ป้าเข็ม" ใช้คำลงท้าย "จ๊ะ/จ้า/นะจ๊ะ" เรียกคนฟังว่า "ลูกหลาน/น้อง"
- ตอบสั้นกระชับ ใช้ได้จริง แบ่งเป็นหัวข้อ bullet ชัดเจน ไม่เขียนอัดแน่นก้อนเดียว
- ห้ามโฆษณาเกินจริง (no clickbait) ห้ามอ้างข้อมูลเทคนิคที่ไม่มีจริง
- ห้ามส่งลิงก์เสีย/ลิงก์ที่ไม่ใช่ affiliate ของร้าน
"""

# worker ที่รู้จัก — Claude ไม่ใช่ worker (สงวนไว้เป็นบอส plan/review เท่านั้น)
# งานกลาง/เฉพาะกิจทั้งหมดให้ groq + firecrawl — worker อื่นที่บอสส่งมา default เป็น groq
KNOWN_WORKERS = {"firecrawl", "groq"}

# โควตาควบคุมแผน — กันบอสวางแผนยาวเกินไป (Claude ใช้แค่ plan/review ไม่เผาโควตาในงานย่อย)
MAX_STEPS = 4
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
            resp = call_with_backoff(
                lambda: client.chat.completions.create(
                    model=settings.ANTHROPIC_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    timeout=CLAUDE_TIMEOUT,
                )
            )
            out = (resp.choices[0].message.content or "").strip()
            if out:
                usage = getattr(resp, "usage", None)
                pt = getattr(usage, "prompt_tokens", None)
                ct = getattr(usage, "completion_tokens", None)
                if pt is not None and ct is not None:
                    logger.info(
                        f"[orchestrator] Claude OK — tokens prompt={pt} "
                        f"completion={ct} total={pt + ct}"
                    )
                else:
                    logger.info("[orchestrator] Claude OK (ไม่ได้รับ usage tokens)")
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
            resp = call_with_backoff(
                lambda: client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": "คุณคือผู้ช่วยแม่ค้าออนไลน์ป้าเข็ม ตอบภาษาไทย ตรงประเด็น"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    timeout=WORKER_TIMEOUT,
                )
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

    คุมโควตา: ตัดเกิน MAX_STEPS ขั้น; worker="claude" → โยนให้ groq เสมอ
    (Claude สงวนเป็นบอส plan/review เท่านั้น — งานกลาง/เฉพาะกิจให้ลูกน้อง groq+firecrawl)"""
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

    steps = []
    for item in raw:
        if len(steps) >= MAX_STEPS:
            break
        steps.append({"worker": item["worker"], "task": item["task"]})
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
        return {"answer": "", "plan": [], "steps": [], "boss": False, "claude_calls": 0}

    # 1. PLAN — บอสแตกโจทย์เป็นแผน (JSON list ของ steps)
    plan_prompt = (
        f"โจทย์จากเจ้าของร้าน: {instruction}\n\n"
        "จงวางแผนการทำงานเป็นขั้นตอน 2-4 ขั้น สั้นๆ โดยแต่ละขั้นเลือก worker ที่เหมาะสมที่สุด:\n"
        "- worker \"firecrawl\" = ค้นข้อมูลจากเน็ต (เทรนด์/คู่แข่ง/ราคา/ข้อเท็จจริง)\n"
        "- worker \"groq\" = เขียน/เจนข้อความ (ถูก+เร็ว เหมาะงานร่าง)\n\n"
        "(ห้ามใช้ worker \"claude\" — Claude สงวนไว้เป็นบอส plan/review เท่านั้น)\n\n"
        "ตอบเป็น JSON list เท่านั้น (ห้ามใส่ markdown fence อย่าใส่ฟิลด์อื่น):\n"
        '[{"worker": "firecrawl|groq", "task": "คำสั่งงานภาษาไทยสั้นๆ"}, ...]'
    )
    plan_text = _claude_generate(plan_prompt)
    plan = _parse_plan(plan_text)

    # Claude วางแผนไม่ได้ → fallback Groq ตอบตรง (PLAN กิน Claude ไป 1 รอบ)
    if not plan:
        logger.warning("[orchestrator] Claude วางแผนไม่สำเร็จ — fallback Groq ตอบตรง (claude_calls=1)")
        return {"answer": _groq_generate(instruction), "plan": [], "steps": [],
                "boss": False, "claude_calls": 1}

    claude_calls = 1  # PLAN สำเร็จ — Claude ใช้ไป 1 รอบ (REVIEW จะเพิ่มอีก 1)

    # 2. DISPATCH — รันแต่ละขั้นด้วย worker ที่บอสสั่ง
    steps = []
    for i, step in enumerate(plan, 1):
        worker, task = step["worker"], step["task"]
        logger.info(f"[orchestrator] dispatch ขั้น {i}/{len(plan)}: worker={worker}, task={task[:80]}")
        if worker == "firecrawl":
            out = _firecrawl_research(task)
        else:  # groq (Claude ไม่เป็น worker — สงวนไว้เป็นบอส plan/review)
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
    claude_calls += 1  # REVIEW — Claude รอบที่ 2

    # REVIEW ล้มแต่ขั้นย่อยมีผล → ต่อ text จากขั้นย่อยเป็นคำตอบสำรอง
    if not answer:
        answer = "\n".join(s["output"] for s in steps if s["output"])

    # สรุปการใช้งานต่อคำตอบ: worker ไหนกี่ขั้น + Claude กี่รอบ (plan+review)
    worker_counts: dict = {}
    for s in steps:
        worker_counts[s["worker"]] = worker_counts.get(s["worker"], 0) + 1
    logger.info(
        f"[orchestrator] boss done — claude_calls={claude_calls} (plan+review), "
        f"steps={len(steps)}, workers={worker_counts}, answer_len={len(answer)}"
    )

    return {"answer": answer, "plan": plan, "steps": steps, "boss": True,
            "claude_calls": claude_calls}


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
