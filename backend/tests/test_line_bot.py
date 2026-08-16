# -*- coding: utf-8 -*-
"""Regression tests สำหรับบอทป้าเข็ม — กัน intent/ตอบผิดกลับมาอีก

ครอบคลุมบั๊กที่เคยเจอจริง:
1. ลูกค้าถาม "ติดตั้ง" ต้องได้คำตอบลูกค้า ไม่ใช่ชุดเจ้าของร้าน
2. ขยะ/อิโมจิ/พิมพ์ผิด ต้องไม่ push แจ้งเจ้าของร้าน
3. ค้นสินค้า/เงื่อนไขราคา/สเปค/พิมพ์ผิด ต้องหาเจอ
"""
import datetime

import pytest

import app.api.line_bot as lb  # noqa: E402
from app import models  # noqa: E402


# ---------- ค้นสินค้าที่ควรเจอ (intent=search) ----------
SEARCH_HITS = [
    "หูฟัง", "กระติกน้ำ", "พัดลม", "หม้อหุงข้าว", "เครื่องฟอกอากาศ",
    "ของเล่นแมว", "น้ำยาย้อมผม", "เสื้อกันแดด",
    # เงื่อนไขราคา
    "หูฟังไม่เกิน 300", "หูฟัง 300-500",
    # สเปคขนาด
    "พัดลม 16 นิ้ว", "หม้อหุงข้าว 1 ลิตร",
    # พิมพ์ผิด/คำพ้อง (THAI_VARIANT_MAP)
    "หูฟง", "ฟูหัง",
]


@pytest.mark.parametrize("text", SEARCH_HITS)
def test_search_hits(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "search", f"{text!r} → intent={r['intent']} preview={r['preview'][:80]}"


# ---------- ค้นไม่เจอ / ของไม่มีในร้าน ----------
def test_nosearch_data_gap_no_owner_push(sim):
    r = sim.send("U_cust_1", "ตู้เย็น")
    assert r["intent"] == "nosearch"
    assert r["owner_pushes"] == []  # มีของใกล้เคียงหมวดให้ → ไม่ต้องปลุกเจ้าของ


def test_legit_miss_no_owner_push(sim):
    r = sim.send("U_cust_1", "โดรนถ่ายรูป")
    assert r["intent"] == "nosearch"
    assert r["owner_pushes"] == []  # ป้าเข็มตอบเอง ไม่ปลุกเจ้าของ (NUANOSE) — gap อยู่ใน chat_logs


# ---------- บั๊ก "ติดตั้ง" (regression) ----------
def test_install_customer_gets_customer_reply(sim):
    r = sim.send("U_cust_1", "ติดตั้งยังไง")
    assert r["intent"] == "manual"
    assert "ไม่ต้องติดตั้งอะไรเลย" in r["preview"]
    assert "เตรียม 4 อย่าง" not in r["preview"]


def test_install_owner_gets_owner_reply(sim):
    r = sim.send(sim.owner_uid, "ติดตั้งยังไง")
    assert r["intent"] == "manual"
    assert "เตรียม 4 อย่าง" in r["preview"]


def test_install_no_longer_promises_free(sim):
    # โปรโมชั่นฟรีหมดแล้ว → ต้องชี้ไปแพ็กเกจ ไม่ใช่ "ฟรีทั้งหมด"
    r = sim.send(sim.owner_uid, "ติดตั้งยังไง")
    assert "แพ็กเกจ" in r["preview"]
    assert "ฟรีทั้งหมด" not in r["preview"]
    r2 = sim.send("U_cust_1", "โค้ดอยู่ไหน")
    assert "ฟรี" not in r2["preview"] or "ดาวน์โหลดได้ฟรี" not in r2["preview"]


@pytest.mark.parametrize("text", ["ต้องมีอะไรบ้าง", "ตั้งค่าระบบยังไง", "โค้ดอยู่ไหน", "github"])
def test_install_related_customer_questions(sim, text):
    r = sim.send("U_cust_1", text)
    assert "เตรียม 4 อย่าง" not in r["preview"]


# ---------- FAQ ไม่สัญญาว่ามีคน/เจ้าของมาตอบ (NUANOSE: ป้าเข็มตอบเอง) ----------
FAQ_NO_HUMAN = [
    ("บอทไม่ตอบ", "ป้าเข็มตอบให้เอง"),
    ("ใครขาย", "ป้าเข็มตอบให้เอง"),
    ("รับประกันกี่วัน", "ติดต่อร้านค้าเอง"),
]

# วลีที่เคยสัญญาว่ามีคนมาตอบ/ส่งต่อเคส — ต้องไม่เหลือในคำตอบ FAQ
HUMAN_ESCALATION_WORDS = (
    "คุยกับคนจริง", "คุยคนจริง", "แจ้งเจ้าของ", "เจ้าของร้านจะ",
    "ส่งต่อเคส", "เจ้าของตอบ", "เจ้าของร้านให้",
)


@pytest.mark.parametrize("text,expect", FAQ_NO_HUMAN)
def test_faq_does_not_promise_human_reply(sim, text, expect):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "manual", f"{text!r} → intent={r['intent']}"
    assert expect in r["preview"], f"{text!r} ตอบไม่ตรง: {r['preview'][:120]}"
    for bad in HUMAN_ESCALATION_WORDS:
        assert bad not in r["preview"], f"{text!r} ยังมี '{bad}' ในคำตอบ"


# ---------- มาตรฐานการบริการ 5 ขั้นตอน (Customer Experience) ----------
SERVICE_STANDARD_PHRASES = ["มาตรฐานการบริการ", "บริการ", "ประสบการณ์ลูกค้า", "5 ขั้นตอน"]


@pytest.mark.parametrize("text", SERVICE_STANDARD_PHRASES)
def test_service_standard_five_steps(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "manual", f"{text!r} → intent={r['intent']}"
    assert "5 ขั้นตอน" in r["preview"], f"{text!r} ไม่ได้โชว์ 5 ขั้นตอน: {r['preview'][:120]}"
    assert "ความพึงพอใจของคุณคือความสำเร็จ" in r["preview"]
    # ต้องมีข้อย่อยแบบเต็มตามอินโฟกราฟิก (ไม่ใช่แค่หัวข้อ)
    assert "ทักทายด้วยรอยยิ้ม" in r["preview"]
    assert "เข้าใจความต้องการของคุณ" in r["preview"]
    assert "ตอบข้อสงสัยอย่างจริงใจ" in r["preview"]
    assert "ลดขั้นตอนที่ยุ่งยาก" in r["preview"]
    assert "สอบถามความพึงพอใจ" in r["preview"]


def test_service_standard_does_not_shadow_product_search(sim):
    # "มาตรฐาน"/"ขั้นตอน" เป็นส่วนหนึ่งของชื่อสินค้าจริงในคลัง — ต้องไม่โดนดักเป็นคู่มือ
    r = sim.send("U_cust_1", "ผ้ามาตรฐาน")
    assert r["intent"] != "manual", "คำค้นสินค้า 'ผ้ามาตรฐาน' โดนดักเป็นคู่มือผิด"


# ---------- แพ็กเกจ/ราคาบอท (ขายต่อ) ----------
PACKAGE_PHRASES = ["ค่าบริการ", "แพ็กเกจราคา", "สมัครใช้บอท", "ซื้อบอท", "เปิดร้าน"]


@pytest.mark.parametrize("text", PACKAGE_PHRASES)
def test_package_faq(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "manual", f"{text!r} → intent={r['intent']}"
    assert "990" in r["preview"], f"{text!r} ไม่ได้โชว์ราคา 990: {r['preview'][:120]}"
    assert "4,990" in r["preview"], f"{text!r} ไม่ได้โชว์ราคา 4,990"


def test_package_faq_does_not_hijack_product_search(sim):
    # "แพ็กเกจ"/"แพ็คเกจ" เป็นส่วนหนึ่งของชื่อสินค้าจริง (3+1 ตัว) — ต้องไม่โดนดักเป็นคู่มือ
    for q in ("แพ็กเกจกล่องของขวัญ", "ชุดแพ็คเกจเซ็ต"):
        r = sim.send("U_cust_1", q)
        assert r["intent"] != "manual", f"คำค้น '{q}' โดนดักเป็นคู่มือผิด"


def test_package_faq_shows_all_four_tiers(sim):
    # เพิ่ม Lean 490/เดือน เป็นขั้นล่างสุด (ขายบอทแบบง่าย ไม่มี AI/DB)
    r = sim.send("U_cust_1", "ค่าบริการ")
    assert "Lean 490" in r["preview"], f"แพ็กเกจไม่มี Lean 490: {r['preview'][:160]}"
    assert "990" in r["preview"]
    assert "4,990" in r["preview"]


# ---------- Lean Stack / Shopee Affiliate / ไฟล์สินค้า / ฟีเจอร์เสริม / ค่าดูแล (ขายบอท) ----------
SALES_FAQ_CASES = [
    ("บอทง่าย", "Lean 490"),
    ("ตอบคีย์เวิร์ด", "Lean 490"),
    ("ลีนสแต็ค", "Lean 490"),
    ("googlesheets", "Lean 490"),
    ("แอปสคริปต์", "Lean 490"),
    ("แปลงลิงก์", "Shopee Affiliate"),
    ("ทำลิงก์ค่าคอม", "Shopee Affiliate"),
    ("แอฟฟิลิเอตคืออะไร", "Shopee Affiliate"),
    ("ใช้เฉพาะ shopee ไหม", "Shopee Affiliate"),
    ("ลาซาด้า", "Shopee Affiliate"),
    ("ไฟล์สินค้า", "ลิงก์ข้อเสนอ"),
    ("คอลัมน์ csv มีอะไรบ้าง", "ลิงก์ข้อเสนอ"),
    ("ฟีเจอร์เสริม", "เปลี่ยนแบรนด์"),
    ("addon มีอะไร", "เปลี่ยนแบรนด์"),
    ("ค่าดูแล", "ค่าดูแล"),
    ("รายปีจ่ายเท่าไหร่", "ค่าดูแล"),
    ("ค่าบริการไลน์", "555"),
    ("ไลน์แพ็กเกจ", "555"),
]


@pytest.mark.parametrize("text,expect", SALES_FAQ_CASES)
def test_sales_faq_topics(sim, text, expect):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "manual", f"{text!r} → intent={r['intent']}"
    assert expect in r["preview"], f"{text!r} ตอบไม่ตรง (หา {expect!r}): {r['preview'][:140]}"


def test_keyword_lean_does_not_shadow_ai_key_faq(sim):
    # "ตอบคีย์เวิร์ด" (Lean) ต้องไม่โดน "คีย์" (คีย์ AI) แย่งไป
    r = sim.send("U_cust_1", "ตอบคีย์เวิร์ด")
    assert "Lean" in r["preview"], f"ตอบคีย์เวิร์ดโดน section คีย์ AI: {r['preview'][:120]}"
    r2 = sim.send("U_cust_1", "คีย์ api")
    assert "Groq" in r2["preview"] or "คีย์ AI" in r2["preview"], f"คีย์ api ไม่ไป section คีย์ AI: {r2['preview'][:120]}"


def test_make_commission_link_not_shadowed_by_commission_faq(sim):
    # "ทำลิงก์ค่าคอม" (วิธีทำลิงก์) ต้องไม่โดน "ค่าคอม" (ความหมาย) แย่งไป
    r = sim.send("U_cust_1", "ทำลิงก์ค่าคอม")
    assert "Shopee Affiliate" in r["preview"], f"ทำลิงก์ค่าคอมโดน section ค่าคอม: {r['preview'][:120]}"
    r2 = sim.send("U_cust_1", "ค่าคอมคืออะไร")
    assert "ค่าคอม = เงิน" in r2["preview"], f"ค่าคอมไม่ไป section ค่าคอม: {r2['preview'][:120]}"


# ---------- ความน่าเชื่อถือ/กันมิจฉาชีพ (ลูกค้าขี้สงสัย) ----------
TRUST_PHRASES = ["เชื่อถือได้ไหม", "ไว้ใจได้ไหม", "โกงไหม", "มิจฉาชีพไหม", "หลอกลวงไหม", "เชื่อได้ไหม"]


@pytest.mark.parametrize("text", TRUST_PHRASES)
def test_trust_faq_reassures_not_scam(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "manual", f"{text!r} → intent={r['intent']}"
    assert "ไม่ใช่สแกม" in r["preview"], f"{text!r} ไม่ยืนยันว่าร้านจริง: {r['preview'][:140]}"
    for bad in HUMAN_ESCALATION_WORDS:
        assert bad not in r["preview"], f"{text!r} ยังมี '{bad}'"


def test_trust_does_not_hijack_pacifier_search(sim):
    # "หลอก" เดี่ยวชน "จุกหลอก" (จุกนมเด็ก) ในคลังจริง — ต้องใช้ "หลอกลวง" แทน
    r = sim.send("U_cust_1", "จุกหลอก")
    assert r["intent"] != "manual", "คำค้น 'จุกหลอก' โดนดักเป็น trust FAQ ผิด"



# ---------- Bulk: ทุก reply ในคู่มือต้องไม่มีวลี escalation ----------
# สแกนทุกข้อความที่ bot_manual_reply ส่งได้ (ทุก FAQ + fallback) — ไม่ใช่แค่ 3 FAQ ข้างบน
MANUAL_REPLY_SOURCES = [
    ("BOT_MANUAL_SECTIONS", [reply for _kws, reply in lb.BOT_MANUAL_SECTIONS]),
    ("BOT_MANUAL", [lb.BOT_MANUAL]),
    ("INSTALL_REPLY_CUSTOMER", [lb.INSTALL_REPLY_CUSTOMER]),
    ("INSTALL_REPLY_OWNER", [lb.INSTALL_REPLY_OWNER]),
    ("OWNER_ONLY_CUSTOMER_REPLY", [lb.OWNER_ONLY_CUSTOMER_REPLY]),
]


@pytest.mark.parametrize("source_name,replies", MANUAL_REPLY_SOURCES)
def test_all_manual_replies_no_human_escalation(source_name, replies):
    for reply in replies:
        assert isinstance(reply, str) and reply.strip(), f"{source_name} มี reply ว่าง"
        for bad in HUMAN_ESCALATION_WORDS:
            assert bad not in reply, f"{source_name} ยังมี '{bad}': {reply[:100]!r}"


# ---------- ขยะ/อิโมจิ/พิมพ์ผิด ไม่ปลุกเจ้าของ ----------
NOISE = ["zzzzzz", "asdfghjkl", "555555", "🙂", "!!!"]


@pytest.mark.parametrize("text", NOISE)
def test_noise_does_not_notify_owner(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "nosearch"
    assert r["owner_pushes"] == [], f"{text!r} ปลุกเจ้าของทั้งที่เป็นขยะ"


# ---------- routing ตาม intent ----------
ROUTING = [
    ("สวัสดี", "greeting"),
    ("วันนี้ขายอะไรดี", "deals"),
    ("อันดับขายดี", "top"),
    ("หมวดสินค้า", "browse"),
    ("คุยกับป้าเข็ม", "human"),
    ("สั่งแล้ว ของถึงยัง", "wismo"),
    ("ค้นเน็ต สภาพอากาศวันนี้", "web"),
    ("เทียบหูฟัง A กับ B", "compare"),
    ("จำไว้ ชอบหูฟัง", "remember"),
]


@pytest.mark.parametrize("text,intent", ROUTING)
def test_routing(sim, text, intent):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == intent, f"{text!r} → intent={r['intent']}"


# ---------- PDPA ลบข้อมูล ----------
def test_delete_user_erases_data(sim, db):
    r = sim.send("U_cust_1", "ลบข้อมูลฉัน")
    assert r["intent"] == "delete"
    assert db.query(models.User).filter_by(line_user_id="U_cust_1").count() == 0


# ---------- battery: ไม่ crash (intent != error) ----------
BATTERY = [
    "อยากได้หูฟัง", "มีพัดลมไหม", "ขอหม้อหุงข้าวหน่อย", "หูฟังงบ 500", "กระติก 2 ลิตร",
    "เทียบ", "เทียบราคากระติก กับ แก้ว", "ขายอะไรดี?", "สินค้าแนะนำ", "ของใหม่",
    "ทำไมต้องซื้อกับป้าเข็ม", "ลบข้อมูล", "ลบประวัติ", "ขอโทษ", "ขอบคุณนะคะ",
    "โกรธมาก", "ดีใจจัง", "วิธีลดน้ำหนัก", "ทำไมฝนตก", "🙂🙂🙂", "หูฟัง!!!!",
    "  หูฟัง  ", "powerbank", "labubu", "555", "เทส", "ok", "แอร์", "ตู้เย็น",
    "หมวด", "ดูหมวด", "ดูหมวดหูฟัง", "ค่าส่งเท่าไหร่", "ส่งฟรีไหม", "ของแท้ไหม",
]


@pytest.mark.parametrize("text", BATTERY)
def test_no_crash_battery(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] != "error", f"{text!r} ทำให้บอท crash"
    assert "ระบบขัดข้อง" not in r["preview"]


# ---------- เทียบสินค้า (compare) ----------
def test_compare_success(sim):
    r = sim.send("U_cust_1", "เทียบ หูฟังบลูทูธไร้สาย รุ่นโปร กับ หูฟังเกมมิ่ง RGB")
    assert r["intent"] == "compare"
    assert "เทียบสินค้า" in r["preview"]


def test_compare_one_missing_suggests_similar(sim):
    r = sim.send("U_cust_1", "เทียบ หูฟังบลูทูธไร้สาย รุ่นโปร กับ กีตาร์")
    assert r["intent"] == "compare"


def test_compare_none_found(sim):
    r = sim.send("U_cust_1", "เทียบ XYZ กับ ABC")
    assert r["intent"] == "compare"
    assert "ไม่เจอ" in r["preview"]


# ---------- แคมเปญ (เฉพาะเจ้าของร้าน) ----------
def test_campaign_dry_run(sim):
    sim.send("U_cust_1", "หูฟัง")
    r = sim.send(sim.owner_uid, "แคมเปญ หูฟัง")
    assert r["intent"] == "campaign"
    assert "DRY-RUN" in r["preview"]


def test_campaign_send(sim):
    sim.send("U_cust_1", "หูฟัง")
    r = sim.send(sim.owner_uid, "แคมเปญ หูฟัง ส่งเลย")
    assert r["intent"] == "campaign"
    assert "ส่งแคมเปญ" in r["preview"]
    assert len(r["owner_pushes"]) == 1  # push การ์ดให้ลูกค้า 1 คน


def test_campaign_history_empty(sim):
    r = sim.send(sim.owner_uid, "แคมเปญ ประวัติ")
    assert r["intent"] == "campaign"
    assert "ยังไม่มีแคมเปญ" in r["preview"]


def test_campaign_history_after_send(sim):
    sim.send("U_cust_1", "หูฟัง")
    sim.send(sim.owner_uid, "แคมเปญ หูฟัง ส่งเลย")
    r = sim.send(sim.owner_uid, "แคมเปญ ประวัติ")
    assert "หูฟัง" in r["preview"]


def test_campaign_no_targets(sim):
    r = sim.send(sim.owner_uid, "แคมเปญ พัดลม")
    assert r["intent"] == "campaign"
    assert "ยังไม่มีลูกค้า" in r["preview"]


def test_campaign_no_products(sim):
    r = sim.send(sim.owner_uid, "แคมเปญ โดรน")
    assert r["intent"] == "campaign"
    assert "ยังไม่มีสินค้า" in r["preview"]


def test_campaign_help(sim):
    r = sim.send(sim.owner_uid, "แคมเปญ")
    assert r["intent"] == "campaign"
    assert "วิธีใช้" in r["preview"]


# ---------- สถิติแอดมิน (เฉพาะเจ้าของร้าน) ----------
def test_admin_stats(sim):
    sim.send("U_cust_1", "หูฟัง")
    sim.send("U_cust_2", "สั่งแล้ว ของถึงยัง")
    r = sim.send(sim.owner_uid, "แอดมิน สถิติ")
    assert r["intent"] == "admin"
    assert "ลูกค้าที่ค้นสินค้า" in r["preview"]


# ---------- follow event (แอดเพื่อน) + sticker ----------
class _FollowEv:
    def __init__(self, uid):
        self.source = type("S", (), {"user_id": uid})()


def test_follow_event_welcome(sim):
    lb.follow_event(_FollowEv("U_cust_1"))
    assert len(sim.pushes) >= 1
    assert "ยินดีต้อนรับ" in sim.pushes[0]


def test_sticker_reply(sim):
    ev = type("E", (), {"reply_token": "rt_sticker"})()
    lb.sticker_text(ev)
    assert len(sim.replies) == 1


# ---------- ฝากคำถาม: ฝากรายละเอียดไว้ เจ้าของร้านตอบทีหลัง (ไม่ตอบทันที) ----------
def test_leave_message_saves_and_notifies_owner(sim):
    r1 = sim.send("U_cust_1", "ฝากคำถาม")
    assert r1["intent"] == "human"
    assert "ฝากคำถามได้เลย" in r1["preview"]  # ชวนฝากรายละเอียด
    r2 = sim.send("U_cust_1", "พัสดุของฉันอยู่ไหน")
    assert r2["intent"] == "human"  # ยังไม่ตอบ → ฝากไว้
    assert "เก็บข้อความไว้" in r2["preview"]
    assert len(r2["owner_pushes"]) == 1  # แจ้งเจ้าของให้ตอบทีหลัง


def test_chat_button_enters_ai_flow(sim):
    # "คุยกับป้าเข็ม" ต้องเข้าแชท AI (ไม่ใช่คู่มือตายตัว) — NUANOSE: AI ตอบเอง
    r1 = sim.send("U_cust_1", "คุยกับป้าเข็ม")
    assert r1["intent"] == "human"
    assert "5 ขั้นตอน" in r1["preview"]
    assert "ต้อนรับอย่างอบอุ่น" in r1["preview"]
    assert "พิมพ์ชื่อสินค้า" in r1["preview"]
    r2 = sim.send("U_cust_1", "หูฟัง")
    assert r2["intent"] == "search"


def test_chat_button_shows_clean_five_steps(sim):
    # กด "คุยกับป้าเข็ม" → ตอบชัด/ไม่อ่านรก: แค่ 5 หัวข้อ ไม่ใช่ข้อความยืดยาวหรือข้อย่อย
    r1 = sim.send("U_cust_1", "คุยกับป้าเข็ม")
    assert r1["intent"] == "human"
    assert "1️⃣ ต้อนรับอย่างอบอุ่น" in r1["preview"]
    assert "5️⃣ ติดตามผลและขอบคุณ" in r1["preview"]
    # ยังไม่ยิงข้อย่อยเต็ม (อันนั้นสำหรับพิมพ์ "บริการ"/"มาตรฐานการบริการ")
    assert "ทักทายด้วยรอยยิ้ม" not in r1["preview"]


def test_how_to_buy_uses_faq_not_web(sim):
    # "จะซื้อสินค้าอย่างไร" ต้องตอบวิธีซื้อจากคู่มือ ไม่ใช่ web search ขยะ
    r = sim.send("U_cust_1", "จะซื้อสินค้าอย่างไร")
    assert r["intent"] == "manual"
    assert "สั่งซื้อผ่าน Shopee" in r["preview"]


def test_leave_message_saves_any_question(sim):
    # ทุกคำถามหลัง "ฝากคำถาม" (แม้แต่ค้นสินค้า/FAQ/ความรู้/เทียบ/ของใหม่) ถูกฝากไว้ ไม่ตอบทันที
    for q in ("หูฟัง", "วิธีชงกาแฟให้อร่อย", "ติดตั้งยังไง", "คืนเงินได้ไหม",
              "เทียบ หูฟังบลูทูธไร้สาย รุ่นโปร กับ แก้วสแตนเลส 316 เก็บความเย็น",
              "มีของใหม่ไหม", "อืม"):
        sim.send("U_cust_1", "ฝากคำถาม")
        r2 = sim.send("U_cust_1", q)
        assert r2["intent"] == "human", f"{q!r} → {r2['intent']}"
        assert "เก็บข้อความไว้" in r2["preview"], f"{q!r} ไม่ยืนยันว่าฝากไว้แล้ว"
        assert len(r2["owner_pushes"]) == 1, f"{q!r} ต้องแจ้งเจ้าของ"


def test_leave_message_retap_shows_prompt_no_push(sim):
    # แตะ "ฝากคำถาม" ซ้ำ (ปุ่มติดมาใน prompt) → โชว์ prompt ใหม่ ไม่ push เจ้าของ
    sim.send("U_cust_1", "ฝากคำถาม")
    r2 = sim.send("U_cust_1", "ฝากคำถาม")
    assert r2["owner_pushes"] == []
    assert "ฝากคำถามได้เลย" in r2["preview"]


def test_leave_message_cancel(sim):
    sim.send("U_cust_1", "ฝากคำถาม")
    r2 = sim.send("U_cust_1", "ยกเลิก")
    assert r2["intent"] == "human"
    assert r2["owner_pushes"] == []
    assert "กลับมาเมนูปกติ" in r2["preview"]


def test_leave_message_ttl_expiry(sim):
    sim.send("U_cust_1", "ฝากคำถาม")
    lb._pending_leave["U_cust_1"] = datetime.datetime.utcnow() - datetime.timedelta(minutes=31)
    r2 = sim.send("U_cust_1", "หูฟัง")
    assert r2["intent"] == "search"  # พ้น TTL → กลับโหมดค้นสินค้าปกติ


def test_leave_message_logged_in_chat_logs(sim, db):
    sim.send("U_cust_1", "ฝากคำถาม")
    sim.send("U_cust_1", "อยากได้กระติกน้ำ 2 ลิตร")
    row = (db.query(models.ChatLog)
             .filter(models.ChatLog.line_user_id == "U_cust_1")
             .order_by(models.ChatLog.id.desc()).first())
    assert row is not None
    assert row.intent == "human"  # intent='human' = "ฝากคำถาม" ในแดชบอร์ด


def test_chat_button_still_answers_immediately(sim):
    # "คุยกับป้าเข็ม" ต่างจาก "ฝากคำถาม" — แชทกับบอทตอบทันที ไม่แจ้งเจ้าของ
    r1 = sim.send("U_cust_1", "คุยกับป้าเข็ม")
    assert r1["intent"] == "human"
    r2 = sim.send("U_cust_1", "หูฟัง")
    assert r2["intent"] == "search"
    assert r2["owner_pushes"] == []


def test_owner_reply_command(sim):
    # เจ้าของตอบลูกค้าทีหลัง: /ตอบ <userId> <ข้อความ> → push ถึงลูกค้า
    r = sim.send(sim.owner_uid, "/ตอบ U_cust_1 สวัสดีจ๊ะ มีของค่ะ")
    assert r["intent"] == "admin"
    assert "ส่งคำตอบถึง U_cust_1" in r["preview"]


def test_pending_damaged_question_manual(sim):
    """'ของชำรุด' ต้องไป FAQ คืนสินค้า ไม่ใช่ web/fallback (พิมพ์ตรง ไม่ผ่านฝากคำถาม)"""
    r = sim.send("U_cust_1", "ของชำรุด ทำไง")
    assert r["intent"] == "manual"
    assert "คืนเงิน" in r["preview"] or "คืนสินค้า" in r["preview"]


# ---------- คำสุภาพล้วน (ครับ/จ้า/ค่ะ) ต้องไม่แมตช์ทุกสินค้า ----------
@pytest.mark.parametrize("text", ["ครับ", "ครับผม", "จ้า", "ค่ะ", "คะ", "นะคะ"])
def test_polite_word_search_returns_nothing(db, text):
    """พิมพ์แค่คำลงท้ายสุภาพ → ตัดแล้วเหลือค่าว่าง อย่า "" in name แมตช์ทั้งร้าน"""
    assert lb.search_products(db, text) == []


def test_polite_word_not_all_products(sim):
    """ผ่านบอทจริง: 'ครับ' ต้องไม่คืนสินค้าทั้งร้าน (intent search)"""
    r = sim.send("U_cust_1", "ครับ")
    assert r["intent"] != "search"


# ---------- โทนวัย (youth/elder) — ครอบทุกตัวแปร tone ----------
def test_detect_tone():
    assert lb.detect_tone("จัดให้เลย 555 คับ") == "youth"
    assert lb.detect_tone("ลุงครับ ขอรบกวนครับผม") == "elder"
    assert lb.detect_tone("หูฟัง") == "neutral"


def test_get_tone_saves_and_recalls(db):
    uid = "U_cust_1"
    assert lb.get_tone(db, uid, "ลุงอยากได้หูฟังครับผม") == "elder"  # เดาแล้วจำ
    assert lb.get_tone(db, uid, "หูฟัง") == "elder"                  # จำไว้ใช้ข้อความถัดไป
    assert lb.get_tone(db, uid, "จัดให้เลย 555") == "youth"          # เดาใหม่แล้วทับ


def test_tone_variants_differ():
    # youth/elder ต้องไม่หลุดไป neutral เดิม
    assert "ว่าเลย" in lb.search_guide("youth")
    assert "ค้นของค่ะ" in lb.search_guide("elder")
    assert lb.greeting_text_for("สมชาย", "youth").startswith("โย่ว")
    assert "สวัสดีค่ะคุณ" in lb.greeting_text_for("สมชาย", "elder")
    assert "ในร้านตอนนี้จ้า" in lb.nosearch_fallback_text("xyz", "youth")
    assert "ในร้านนะคะ" in lb.nosearch_fallback_text("xyz", "elder")
    assert "😎" in lb.nosearch_alt_text("xyz", "แมว", "youth")
    assert "😎" in lb.nosearch_new_text("xyz", "แมว", "youth")
    assert lb.welcome_text("สมชาย", "youth").startswith("🤗 โย่ว")
    assert "สวัสดีค่ะคุณ" in lb.welcome_text("สมชาย", "elder")
    assert "จ้าา" in lb.why_us_text("youth")
    assert "คะ?" in lb.why_us_text("elder")
    assert lb.emotion_reply("โกรธ/ไม่พอใจ", "youth").startswith("😤")
    assert lb.emotion_reply("โกรธ/ไม่พอใจ", "elder").startswith("😔")


# ---------- web search helpers ----------
def test_web_search_helpers():
    assert lb.is_web_search_request("ค้นเน็ต ราคาทอง")
    assert lb.is_web_search_request("เสิร์ช หุ้นวันนี้")
    assert not lb.is_web_search_request("หูฟัง")
    assert lb._web_search_text("ค้นเน็ต ราคาทอง") == "ราคาทอง"
    assert lb._web_search_text("เสิร์ช หุ้นวันนี้") == "หุ้นวันนี้"
    assert lb.looks_like_question("วิธีทำอาหาร")
    assert lb.looks_like_question("คืออะไร")
    assert not lb.looks_like_question("หูฟัง")


def test_web_answer_messages_with_image(monkeypatch):
    monkeypatch.setattr(lb, "web_search_answer",
                        lambda q, *a, **k: {"text": "คำตอบ", "images": ["https://example.com/x.jpg"]})
    msgs = lb._web_answer_messages("คำถาม")  # ไม่ส่ง answer → เรียก web_search_answer เอง
    assert len(msgs) == 2  # รูป + ข้อความ


def test_web_answer_messages_reuse_answer():
    msgs = lb._web_answer_messages("คำถาม", answer={"text": "คำตอบ", "images": []})
    assert len(msgs) == 1


# ---------- Account Memory (จำไว้ / มีอะไรใหม่) ----------
def test_remember_save_and_show(sim):
    r1 = sim.send("U_cust_1", "จำไว้ ชอบหูฟัง")
    assert r1["intent"] == "remember"
    assert "จำไว้แล้ว" in r1["preview"]
    r2 = sim.send("U_cust_1", "ป้าเข็มจำได้ไหม")
    assert r2["intent"] == "remember"
    assert "หูฟัง" in r2["preview"]


def test_remember_empty_note(sim):
    r = sim.send("U_cust_1", "จำไว้")
    assert r["intent"] == "remember"


def test_remember_show_empty(sim):
    r = sim.send("U_cust_1", "ป้าเข็มจำได้ไหม")
    assert r["intent"] == "remember"
    assert "ยังไม่มีอะไร" in r["preview"]


def test_new_arrivals_matched_preference(sim):
    sim.send("U_cust_1", "จำไว้ ชอบกล่องสุ่ม")
    r = sim.send("U_cust_1", "มีอะไรใหม่")
    assert r["intent"] == "new"


def test_new_arrivals_fallback_recent(sim):
    r = sim.send("U_cust_1", "มีอะไรใหม่")
    assert r["intent"] == "new"


# ---------- compare: fact + เจ้าของร้าน + เตือนขนาด ----------
def test_compare_facts_owner(sim):
    r = sim.send(sim.owner_uid, "เทียบ หูฟังบลูทูธไร้สาย รุ่นโปร กับ ของเล่นแมว ไม้ตกแมว ขนนก")
    assert r["intent"] == "compare"


def test_compare_size_warn(sim):
    r = sim.send("U_cust_1", "เทียบ พัดลมตั้งโต๊ะ 16 นิ้ว กับ หม้อหุงข้าว 1 ลิตร อเนกประสงค์")
    assert r["intent"] == "compare"


# ---------- manual: คำถามเฉพาะเจ้าของร้าน ----------
def test_manual_owner_only_customer(sim):
    r = sim.send("U_cust_1", "สมัครไลน์โอเอ")
    assert r["intent"] == "manual"
    assert "ข้อมูลของคนอยากเปิดร้านเอง" in r["preview"]  # OWNER_ONLY_CUSTOMER_REPLY


def test_manual_owner_gets_section(sim):
    r = sim.send(sim.owner_uid, "สมัครไลน์โอเอ")
    assert r["intent"] == "manual"
    assert "LINE OA" in r["preview"]


# ---------- คีย์บอร์ด ต้องไม่โดน "คีย์" (API key) จับเป็นคู่มือ ----------
def test_keyboard_query_routes_to_search(sim, db):
    """หาคีย์บอร์ดต้องได้สินค้า ไม่ใช่คำตอบเรื่องคีย์ AI (คำ 'คีย์' ชน 'คีย์บอร์ด')"""
    db.add(models.Product(
        name="คีย์บอร์ดไร้สาย Bluetooth", category="อุปกรณ์เสริม", price=500,
        sales_count=5000, affiliate_url="https://shope.ee/test",
        link_status="ok", ai_score=70))
    db.commit()
    try:
        r = sim.send("U_cust_1", "คีย์บอร์ดไร้สาย")
        assert r["intent"] == "search", f"คีย์บอร์ดโดนจับเป็น {r['intent']}: {r['preview'][:80]}"
        assert "คีย์บอร์ด" in r["preview"]
    finally:
        db.query(models.Product).filter(models.Product.name == "คีย์บอร์ดไร้สาย Bluetooth").delete()
        db.commit()


def test_keyboard_typo_not_manual(sim):
    """'คีย์บอรด' (พิมพ์ ด แทน รด์) ก็ต้องไม่หลุดไปคู่มือคีย์ AI"""
    r = sim.send("U_cust_1", "คีย์บอรดไร้สาย")
    assert r["intent"] != "manual", f"คีย์บอรดโดนจับเป็น manual: {r['preview'][:80]}"


def test_keyboard_not_manual_request():
    assert lb.is_bot_manual_request("คีย์บอร์ดไร้สาย") is False
    assert lb.is_bot_manual_request("คีย์บอร์ด") is False
    assert lb.is_bot_manual_request("คีย์บอรด") is False


def test_key_api_query_still_manual(sim):
    """คีย์ AI/โควต้า ยังเป็นคำถามคู่มือเหมือนเดิม (ไม่หลุดไปค้นสินค้า)"""
    r = sim.send("U_cust_1", "คีย์ ai หมดแล้วทำไง")
    assert r["intent"] == "manual"
    assert "คีย์ AI" in r["preview"]


# ---------- ตัวเลขไทยคำในเงื่อนไขราคา (ลูกค้าจริง: "ถุงเท้าไม่เกินร้อย") ----------
@pytest.mark.parametrize("s,expect", [
    ("ร้อย", 100.0), ("สองร้อย", 200.0), ("พัน", 1000.0), ("สองพัน", 2000.0),
    ("ยี่สิบ", 20.0), ("หมื่น", 10000.0), ("ล้าน", 1000000.0),
    ("abc", None), ("", None),
])
def test_thai_word_number(s, expect):
    assert lb._thai_word_number(s) == expect


@pytest.mark.parametrize("text,expect", [
    # ตัวเลขไทยคำ — ก่อนแก้ regex รับแต่ตัวเลขอารบิก "ถุงเท้าไม่เกินร้อย" ค้นไม่เจอ
    ("ถุงเท้าไม่เกินร้อย", (None, 100.0)),
    ("งบสองพัน", (None, 2000.0)),
    ("สองร้อยบาท", (None, 200.0)),
    ("ไม่เกิน 300", (None, 300.0)),
    ("กระติก 200-400", (200.0, 400.0)),
    ("ถุงเท้า", (None, None)),
])
def test_parse_price_conditions(text, expect):
    assert lb.parse_price_conditions(text) == expect


def test_strip_price_phrase_thai_word():
    assert lb.strip_price_phrase("ถุงเท้าไม่เกินร้อย") == "ถุงเท้า"
    assert lb.strip_price_phrase("งบสองพัน") == ""


def test_search_thai_word_price_filters_budget(sim, db):
    """ค้น "ถุงเท้าไม่เกินร้อย" → ได้เฉพาะถุงเท้าราคา ≤100 (ไม่ใช่ของหมวดมั่วมาแทน)"""
    db.add(models.Product(
        name="ถุงเท้ากีฬาระบายอากาศ 3 คู่", category="แฟชั่น", price=89,
        sales_count=5000, affiliate_url="https://shope.ee/test",
        link_status="ok", ai_score=50))
    db.add(models.Product(
        name="ถุงเท้าแฟชั่นลายการ์ตูน 2 คู่", category="แฟชั่น", price=450,
        sales_count=5000, affiliate_url="https://shope.ee/test",
        link_status="ok", ai_score=50))
    db.commit()
    try:
        hits = lb.search_products(db, "ถุงเท้าไม่เกินร้อย")
        assert hits, "ควรเจอถุงเท้าในงบ 100"
        assert all(float(h.price or 0) <= 100 for h in hits), \
            [f"{h.name}: {h.price}" for h in hits]
        assert all("ถุงเท้า" in (h.name or "") for h in hits)
    finally:
        db.query(models.Product).filter(models.Product.name.like("ถุงเท้า%")).delete()
        db.commit()


def test_nosearch_fallback_prefers_name_similar(sim, db):
    """ค้นไม่เจอ (งบไม่มีของ) → แนะนำของที่ชื่อใกล้ (ถุงเท้า) ไม่ใช่ของหมวด ai_score สูง (นาฬิกา)
    — เดิม sort ด้วย ai_score ทำลูกค้าถามถุงเท้าได้นาฬิกา/รองเท้า"""
    db.add(models.Product(
        name="ถุงเท้ากีฬา 3 คู่", category="แฟชั่น", price=89,
        sales_count=5000, affiliate_url="https://shope.ee/test",
        link_status="ok", ai_score=50))
    db.add(models.Product(
        name="นาฬิกาอัจฉริยะ KENTO", category="แฟชั่น", price=900,
        sales_count=5000, affiliate_url="https://shope.ee/test",
        link_status="ok", ai_score=99))
    db.commit()
    try:
        r = sim.send("U_cust_1", "ถุงเท้าไม่เกิน 40")
        assert r["intent"] == "nosearch"
        assert "ถุงเท้า" in r["preview"], r["preview"][:200]
        assert "นาฬิกา" not in r["preview"], r["preview"][:200]
    finally:
        db.query(models.Product).filter(
            models.Product.name.in_(["ถุงเท้ากีฬา 3 คู่", "นาฬิกาอัจฉริยะ KENTO"])).delete()
        db.commit()
