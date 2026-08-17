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
from app.services import slip_ocr  # noqa: E402


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


def test_package_request_returns_summary(sim):
    # ถามแพ็กเกจ/ราคาบอท → สรุปย่อ + ปุ่มเลือกทีละแพ็กเกจ (ไม่ทิ้งการ์ดเต็ม 5 ใบทันที)
    r = sim.send("U_cust_1", "ค่าบริการ")
    assert r["intent"] == "manual"
    assert "5 ทางเลือก" in r["preview"], r["preview"][:80]
    assert "Lean 490" in r["preview"]
    assert "15,000–25,000" in r["preview"]
    assert "มี 4 ระดับจ๊ะ" not in r["preview"], "ยังใช้ข้อความล้วนแบบเก่า"


def test_package_summary_quick_reply_has_five_buttons():
    # สรุปย่อแนบปุ่ม 5 แพ็กเกจ → แตะส่ง "ยอด <key>" → ไปหน้าชำระเงินของตัวนั้น (ไม่ทิ้งการ์ดเต็ม)
    qr = lb.package_summary_quick_reply()
    labels = [i.action.label for i in qr.items]
    texts = [i.action.text for i in qr.items]
    assert labels == ["🟡 Lean", "🟢 Starter", "🔵 Business", "🟣 White-Label", "🟠 ขายขาด"]
    assert texts[0] == "ยอด lean"
    assert texts[-1] == "ยอด ขายขาด"


def _flex_dict(card):
    c = card.contents
    return c if isinstance(c, dict) else c.as_json_dict()


def test_package_flex_card_has_five_colored_bubbles():
    card = lb.package_flex_card()
    d = _flex_dict(card)
    assert d["type"] == "carousel"
    bubbles = d["contents"]
    assert len(bubbles) == 5
    colors = [b["header"]["backgroundColor"] for b in bubbles]
    assert len(set(colors)) == 5, f"สีแพ็กเกจต้องแยกชัดไม่ซ้ำ: {colors}"
    prices = [b["body"]["contents"][0]["text"] for b in bubbles]
    assert prices == ["490฿/เดือน", "990฿/เดือน", "1,990฿/เดือน",
                      "4,990฿/เดือน", "15,000–25,000฿"]
    # ใบสุดท้าย = ขายขาด (ซื้อครั้งเดียว ไม่ใช่รายเดือน)
    assert bubbles[-1]["header"]["contents"][0]["text"] == "🟠 ขายขาด"
    keys = ["lean", "starter", "business", "whitelabel", "ขายขาด"]
    for b, key in zip(bubbles, keys):
        btn = b["footer"]["contents"][0]
        assert btn["action"] == {"type": "message", "label": "สนใจแพ็กเกจนี้",
                                   "text": f"ยอด {key}"}


def test_is_package_request_excludes_line_oa_fee():
    # "ค่าบริการไลน์"/"ไลน์แพ็กเกจ" = ค่า LINE OA (section แยก) ต้องไม่โดนการ์ดแพ็กเกจแย่ง
    assert lb.is_package_request("ค่าบริการ") is True
    assert lb.is_package_request("แพ็กเกจราคา") is True
    assert lb.is_package_request("ค่าบริการไลน์") is False
    assert lb.is_package_request("ไลน์แพ็กเกจ") is False
    assert lb.is_package_request("บริการ") is False


def test_quick_reply_includes_bot_price_button():
    # ปุ่มลัดสากลมีปุ่ม "ราคาบอท/แพ็กเกจ" + "วิธีจ่ายเงิน" → แตะแล้วไปการ์ด/วิธีจ่าย (ขายบอทต่อ)
    # ไม่มี "คุยกับป้าเข็ม" (ซ้ำซ้อน — บอทตอบเองทุกข้อความอยู่แล้ว)
    qr = lb.quick_reply_items()
    labels = [item.action.label for item in qr.items]
    texts = [item.action.text for item in qr.items]
    assert labels == ["🔍 ค้นหาสินค้า", "💬 ฝากคำถาม", "💰 ราคาบอท/แพ็กเกจ", "💰 วิธีจ่ายเงิน"], labels
    assert texts[-2] == "ราคาบอท"
    assert texts[-1] == "วิธีจ่ายค่าบอท"
    assert "คุยกับป้าเข็ม" not in texts
    # แตะปุ่มราคาบอท → การ์ด Flex แพ็กเกจ (intent manual) ไม่ใช่ค้นสินค้า
    assert lb.is_package_request("ราคาบอท") is True
    # แตะปุ่มวิธีจ่ายเงิน → ตอบวิธีจ่าย (BOT_PAYMENT_REPLY) ไม่ใช่ค้นสินค้า
    assert lb.bot_manual_reply("วิธีจ่ายค่าบอท") == lb.payment_reply_text()


# ---------- ขายขาด / ซื้อครั้งเดียว (แม่ค้าไม่อยากผูกเดือน) ----------
PERPETUAL_PHRASES = ["ขายขาด", "ซื้อขาด", "ซื้อครั้งเดียว", "เหมาจ่าย", "จ่ายครั้งเดียว"]


@pytest.mark.parametrize("text", PERPETUAL_PHRASES)
def test_perpetual_faq(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "manual", f"{text!r} → intent={r['intent']}"
    assert "15,000–25,000" in r["preview"], f"{text!r} ไม่โชว์ราคาขายขาด: {r['preview'][:140]}"
    assert "จ่ายครั้งเดียว" in r["preview"], f"{text!r} ไม่บอกว่าจ่ายครั้งเดียว"


# ---------- รายเดือน (เช่าใช้) vs ขายขาด (ซื้อเป็นของตัวเอง) ----------
RENT_VS_BUYOUT_PHRASES = [
    "ขายขาดกับรายเดือนต่างกันยังไง",
    "รายเดือนกับขายขาดต่างกันยังไง",
    "เช่ากับซื้อต่างกันยังไง",
    "เช่าใช้กับซื้อขาดต่างกันยังไง",
    "ควรเช่าหรือซื้อ",
    "เช่าบอทได้ไหม",
    "รายเดือนคืออะไร",
    "ขายขาดคืออะไร",
]


@pytest.mark.parametrize("text", RENT_VS_BUYOUT_PHRASES)
def test_rent_vs_buyout_faq_explains_both(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "manual", f"{text!r} → intent={r['intent']}"
    assert "เช่าใช้" in r["preview"], f"{text!r} ไม่อธิบายว่ารายเดือน = เช่าใช้: {r['preview'][:160]}"
    assert "ซื้อเป็นของตัวเอง" in r["preview"], f"{text!r} ไม่อธิบายว่าขายขาด = ซื้อเป็นของตัวเอง: {r['preview'][:160]}"
    assert "15,000–25,000" in r["preview"], f"{text!r} ไม่โชว์ราคาขายขาด"


def test_rent_vs_buyout_does_not_hijack_rental_search(sim):
    # "เช่าชุดไทย" = ค้นสินค้า/ชุดให้เช่า → ต้องไม่โดนดักเป็น FAQ ความต่าง
    r = sim.send("U_cust_1", "เช่าชุดไทย")
    assert r["intent"] != "manual", "คำค้น 'เช่าชุดไทย' โดนดักเป็น FAQ"


# ---------- ทำไม 490฿/เดือน (แม่ค้าถามความคุ้ม/เหตุผลราคา) ----------
WHY_490_PHRASES = [
    "ทำไม490", "ทำไมต้อง 490", "ทำไมจ่าย 490", "490 ทำไมแพง",
    "490 แพงไหม", "490 คุ้มไหม", "490 ถูกไหม", "490/เดือน", "จ่าย 490",
    "ทำไมรายเดือน", "จ่ายรายเดือน", "จ่ายทุกเดือน", "ทำไมต้องจ่าย",
    "รายเดือนแพงไหม", "รายเดือนคุ้มไหม",
]


@pytest.mark.parametrize("text", WHY_490_PHRASES)
def test_why_490_monthly_faq(sim, text):
    r = sim.send("U_cust_1", text)
    assert r["intent"] == "manual", f"{text!r} → intent={r['intent']}"
    assert "490฿/เดือน" in r["preview"], f"{text!r} ไม่ตอบเรื่อง 490: {r['preview'][:140]}"
    assert "รายเดือน" in r["preview"], f"{text!r} ไม่อธิบายเหตุผลรายเดือน"


def test_why_490_does_not_hijack_price_search(sim):
    # "หูฟัง 490" = ค้นสินค้างบ 490 → ต้องไป search ไม่ใช่ FAQ "ทำไม 490"
    r = sim.send("U_cust_1", "หูฟัง 490")
    assert r["intent"] == "search", f"คำค้น 'หูฟัง 490' โดนดัก: intent={r['intent']}"
    r2 = sim.send("U_cust_1", "หูฟัง 490 บาท")
    assert r2["intent"] == "search", f"คำค้น 'หูฟัง 490 บาท' โดนดัก: intent={r2['intent']}"


# ---------- Lean Stack / Shopee Affiliate / ไฟล์สินค้า / ฟีเจอร์เสริม (ขายบอท) ----------
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
    ("ค่าบริการไลน์", "555"),
    ("ไลน์แพ็กเกจ", "555"),
    ("ใช้เวลานานแค่ไหน", "1 วัน"),
    ("กี่วันเสร็จ", "ระยะเวลาทำบอท"),
    ("ทำบอทกี่วัน", "1 วัน"),
    ("สร้างบอทใช้เวลานานไหม", "1 วัน"),
    ("เสร็จเมื่อไหร่", "ระยะเวลาทำบอท"),
    ("ส่งมอบบอท", "1 วัน"),
    ("บอทแพ็กเกจ Business ใช้เวลากี่วัน", "5 วัน"),
    ("จ่ายค่าบอท", "วิธีจ่ายเงิน"),
    ("จ่ายมัดจำ", "วิธีจ่ายเงิน"),
    ("จ่ายมัดจำยังไง", "วิธีจ่ายเงิน"),
    ("วิธีจ่ายค่าบอท", "วิธีจ่ายเงิน"),
    ("promptpay", "วิธีจ่ายเงิน"),
    ("บัตรเครดิต", "ตัดอัตโนมัติ"),
    ("โอนค่าบอท", "วิธีจ่ายเงิน"),
    # โฟกัสขายบอท (เจ้าของสั่ง): คำจ่ายเงินทั่วไปก็ตอบวิธีจ่ายค่าบอท
    ("ชำระเงิน", "วิธีจ่ายเงิน"),
    ("ชำระเงินยังไง", "วิธีจ่ายเงิน"),
    ("จ่ายเงิน", "วิธีจ่ายเงิน"),
    ("จ่ายยังไง", "วิธีจ่ายเงิน"),
    ("โอนเงิน", "วิธีจ่ายเงิน"),
    ("โอนจ่าย", "วิธีจ่ายเงิน"),
]


def test_payment_reply_precalculates_amounts():
    # รายเดือนจ่ายเต็มเดือนแรกก่อนเริ่ม (ไม่มีมัดจำ/ค่าติดตั้งแยก) · ขายขาดมัดจำ 50% จ่ายครั้งเดียว
    text = lb.payment_reply_text()
    assert "จ่าย 490 ก่อนเริ่ม" in text  # Lean (เดือนแรกเต็ม)
    assert "จ่าย 990 ก่อนเริ่ม" in text  # Starter
    assert "จ่าย 1,990 ก่อนเริ่ม" in text  # Business
    assert "จ่าย 4,990 ก่อนเริ่ม" in text  # White-Label
    assert "มัดจำ 50%" in text and "7,500–12,500" in text  # ขายขาด
    # ไม่มีมัดจำ/ค่าติดตั้งแยกสำหรับรายเดือน + บอกหลังรับบอทจ่ายรายเดือนต่อ
    assert "ไม่มีมัดจำ" in text
    assert "ไม่มีค่าติดตั้งแยก" in text
    assert "จ่ายรายเดือนต่อ" in text


def test_payment_reply_is_text_only_no_qr(sim):
    # วิธีจ่าย = ข้อความเดียว (เลขพร้อมเพย์/บัญชีในข้อความแล้ว) ไม่แนบ QR รูป
    r = sim.send("U_cust_1", "วิธีจ่ายค่าบอท")
    assert r["intent"] == "manual"
    assert "วิธีจ่ายเงิน" in r["preview"]
    assert "<ImageSendMessage>" not in r["preview"]
    msgs = lb._manual_reply_messages("วิธีจ่ายค่าบอท")
    assert not isinstance(msgs, list)
    assert msgs.text == lb.payment_reply_text()


def test_payment_reply_has_no_quick_reply_no_loop(sim):
    # หน้าเลขบัญชีตอบล้วน ไม่แนบปุ่มแพ็กเกจวนไปวนมา — เส้นทางเดียว: ดูเลขบัญชี → โอน
    msgs = lb._manual_reply_messages("วิธีจ่ายค่าบอท")
    assert not isinstance(msgs, list)
    assert msgs.quick_reply is None
    assert msgs.text == lb.payment_reply_text()


def test_tap_package_quick_reply_shows_that_package_amount(sim):
    r = sim.send("U_cust_1", "ยอด Starter")
    assert r["intent"] == "manual"
    assert "🟢 Starter 990" in r["preview"]
    assert "จ่ายเดือนแรกก่อนเริ่มทำ: 990 บาท" in r["preview"]
    assert "หลังรับบอท จ่ายรายเดือน: 990 บาท/เดือน" in r["preview"]
    assert "ชำระเงิน" in r["preview"]  # ชี้ไปปุ่มชำระเงินดูเลขบัญชี
    # แตะปุ่มขายขาด → มัดจำ 50% + ที่เหลือตอนส่งมอบ + รวมครั้งเดียว
    r2 = sim.send("U_cust_1", "ยอด ขายขาด")
    assert "มัดจำก่อนเริ่ม: 7,500–12,500 บาท" in r2["preview"]
    assert "จ่ายตอนส่งมอบ: 7,500–12,500 บาท" in r2["preview"]
    assert "รวมจ่ายครั้งเดียว: 15,000–25,000 บาท" in r2["preview"]


def test_package_card_interest_button_goes_to_payment(sim):
    # กด "สนใจแพ็กเกจนี้" ในการ์ด → ส่ง "ยอด <แพ็กเกจ>" → หน้าชำระเงินของแพ็กเกจนั้น (ไม่ใช่ติดต่อเจ้าของ)
    r = sim.send("U_cust_1", "ยอด business")
    assert r["intent"] == "manual"
    assert "🔵 Business 1,990" in r["preview"]
    assert "ชำระเงิน" in r["preview"]  # ชี้ไปปุ่มชำระเงินดูเลขบัญชี
    assert "ติดต่อเจ้าของร้าน" not in r["preview"]


def test_package_payment_reply_attaches_pay_button():
    # หน้าชำระรายแพ็กเกจแนบปุ่ม "ชำระเงิน" ปุ่มเดียว (เส้นเดียว ดูเลขบัญชี ไม่วนแพ็กเกจ)
    msgs = lb._manual_reply_messages("ยอด lean")
    assert msgs.quick_reply is not None
    labels = [i.action.label for i in msgs.quick_reply.items]
    texts = [i.action.text for i in msgs.quick_reply.items]
    assert labels == ["💳 ชำระเงิน"]
    assert texts == ["ชำระเงิน"]


def test_tap_pay_button_reopens_payment_page(sim):
    # แตะ "ชำระเงิน" → กลับมาเห็นวิธีจ่าย + เลขบัญชีอีกครั้ง (payment_reply_text)
    sim.send("U_cust_1", "ยอด lean")
    r = sim.send("U_cust_1", "ชำระเงิน")
    assert r["intent"] == "manual"
    assert "วิธีจ่ายเงินค่าบอท" in r["preview"]
    assert "โอน" in r["preview"]


# ---------- ติดตามสถานะซื้อบอท: สนใจ → จ่ายแล้ว → เจ้าของยืนยัน → ยกเลิก ----------
def _purchase(db, uid):
    return (db.query(models.BotPurchase)
              .filter(models.BotPurchase.line_user_id == uid).first())


def test_interest_tracks_bot_purchase(sim, db):
    # กด "สนใจแพ็กเกจนี้" (ส่ง "ยอด lean") → บันทึกสถานะสนใจแพ็กเกจนั้น
    r = sim.send("U_cust_1", "ยอด lean")
    assert r["intent"] == "manual"
    p = _purchase(db, "U_cust_1")
    assert p is not None
    assert p.package_key == "lean"
    assert p.status == "interested"


def test_interest_shows_queue_number(sim, db):
    # แตะ "สนใจแพ็กเกจนี้" → เห็นเลขคิวของตัวเอง (ลูกค้าแรก = คิวที่ 1, คนถัดไป = คิวที่ 2)
    r = sim.send("U_cust_1", "ยอด lean")
    assert "คิวที่ 1" in r["preview"], f"ไม่เห็นเลขคิว: {r['preview'][:160]}"
    r2 = sim.send("U_cust_2", "ยอด starter")
    assert "คิวที่ 2" in r2["preview"], f"คิวไม่เพิ่ม: {r2['preview'][:160]}"


def test_owner_queue_command_lists_pending(sim, db):
    # เจ้าของพิมพ์ /คิว → เห็นรายการงานค้างเรียงตามลำดับ (FIFO)
    sim.send("U_cust_1", "ยอด lean")
    sim.send("U_cust_2", "ยอด starter")
    r = sim.send(sim.owner_uid, "/คิว")
    assert r["intent"] == "admin"
    assert "คิวงานบอท (2 งานค้าง)" in r["preview"]
    assert "🟡 Lean 490" in r["preview"]
    assert "🟢 Starter 990" in r["preview"]


def test_owner_queue_empty(sim, db):
    # ไม่มีงานค้าง → /คิว บอกว่าไม่มีงาน
    r = sim.send(sim.owner_uid, "/คิว")
    assert r["intent"] == "admin"
    assert "ไม่มีงานค้าง" in r["preview"]


def test_customer_queue_shows_number_and_leadtime(sim, db):
    # ลูกค้าแตะสนใจแพ็กเกจ → พิมพ์ "คิวของฉัน" → เห็นเลขคิว + ระยะเวลาทำ
    sim.send("U_cust_1", "ยอด business")
    r = sim.send("U_cust_1", "คิวของฉัน")
    assert r["intent"] == "manual"
    assert "คิวที่ 1" in r["preview"], f"ไม่เห็นเลขคิว: {r['preview'][:160]}"
    assert "🔵 Business 1,990" in r["preview"]
    assert "เสร็จภายใน 5 วัน" in r["preview"]


def test_customer_queue_empty_guides_to_packages(sim, db):
    # ยังไม่สั่ง → "คิวของฉัน" บอกไม่มี + ชี้ไปถามราคาบอท
    r = sim.send("U_cust_1", "คิวของฉัน")
    assert r["intent"] == "manual"
    assert "ไม่มีคำสั่งซื้อ" in r["preview"]
    assert "ราคาบอท" in r["preview"]


def test_purchase_timestamps_recorded(sim, db):
    # จ่ายแล้ว → บันทึก paid_at; เจ้าของยืนยัน → บันทึก confirmed_at (ยึดจุดเริ่มทำ ไม่เลื่อนไปเรื่อย ๆ)
    sim.send("U_cust_1", "ยอด lean")
    p = _purchase(db, "U_cust_1")
    assert p.paid_at is None and p.confirmed_at is None
    sim.send("U_cust_1", "จ่ายแล้ว")
    db.expire_all()  # เคลียร์ identity map กัน session แคชของเก่า
    p = _purchase(db, "U_cust_1")
    assert p.paid_at is not None
    assert p.confirmed_at is None
    sim.send(sim.owner_uid, "/ยืนยัน U_cust_1")
    db.expire_all()
    p = _purchase(db, "U_cust_1")
    assert p.confirmed_at is not None


def test_customer_queue_shows_received_time(sim, db):
    # "คิวของฉัน" → เห็น "รับเรื่องเมื่อ" (เวลาที่สั่ง) ชัดเจน
    sim.send("U_cust_1", "ยอด lean")
    r = sim.send("U_cust_1", "คิวของฉัน")
    assert "รับเรื่องเมื่อ" in r["preview"]


def test_owner_queue_shows_received_time(sim, db):
    # /คิว → แต่ละงานมีเวลารับเรื่อง (ลงบันทึกดี ๆ)
    sim.send("U_cust_1", "ยอด lean")
    r = sim.send(sim.owner_uid, "/คิว")
    assert "รับเรื่อง" in r["preview"]


def test_paid_declaration_sets_pending_and_notifies_owner(sim, db):
    sim.send("U_cust_1", "ยอด lean")
    r = sim.send("U_cust_1", "จ่ายแล้ว")
    assert r["intent"] == "purchase"
    assert "รับทราบ" in r["preview"] and "แจ้งเจ้าของ" in r["preview"]
    p = _purchase(db, "U_cust_1")
    assert p.status == "paid_pending"
    assert len(r["owner_pushes"]) == 1  # แจ้งเจ้าของให้เช็คยอด + ยืนยัน


def test_owner_confirm_marks_confirmed_and_pushes_customer(sim, db):
    sim.send("U_cust_1", "ยอด lean")
    sim.send("U_cust_1", "จ่ายแล้ว")
    r = sim.send(sim.owner_uid, "/ยืนยัน U_cust_1")
    assert r["intent"] == "admin"
    assert "ยืนยันรับเงิน U_cust_1" in r["preview"]
    p = _purchase(db, "U_cust_1")
    assert p.status == "confirmed"
    assert any("ยืนยันรับเงิน" in x for x in r["owner_pushes"])  # push แจ้งลูกค้า


def test_cancel_purchase_marks_cancelled_and_notifies_owner(sim, db):
    sim.send("U_cust_1", "ยอด lean")
    r = sim.send("U_cust_1", "ยกเลิก")
    assert r["intent"] == "purchase"
    assert "ยกเลิก" in r["preview"]
    p = _purchase(db, "U_cust_1")
    assert p.status == "cancelled"
    assert len(r["owner_pushes"]) == 1  # แจ้งเจ้าของว่าลูกค้ายกเลิก


def test_paid_declaration_without_purchase_ignored(sim, db):
    # ไม่มีคำสั่งซื้อค้าง → "จ่ายแล้ว" ไม่เข้าติดตาม ไม่แจ้งเจ้าของ ไม่ crash
    r = sim.send("U_cust_1", "จ่ายแล้ว")
    assert r["intent"] != "purchase"
    assert _purchase(db, "U_cust_1") is None
    assert r["owner_pushes"] == []


# ---------- รับรูปสลิป (ImageMessage) — ดาวน์โหลดผ่าน LINE Content API ----------
class _ImageEvent:
    def __init__(self, uid, message_id="msg_slip_1"):
        self.message = type("M", (), {"id": message_id})()
        self.source = type("S", (), {"user_id": uid})()
        self.reply_token = f"rt_{uid}"


class _FakeContent:
    def __init__(self, data, content_type="image/jpeg"):
        self._data = data
        self.content_type = content_type

    def iter_content(self, chunk_size=1024):
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i:i + chunk_size]


def _send_slip(sim, monkeypatch, uid, data=b"fake-slip-image", content_type="image/jpeg"):
    """จำลองลูกค้าส่งรูปสลิป → คืน {preview, owner_pushes} เหมือน sim.send"""
    content = _FakeContent(data, content_type)
    monkeypatch.setattr(lb.line_bot_api, "get_message_content",
                        lambda mid, timeout=None: content)
    sim.replies.clear()
    sim.pushes.clear()
    lb.image_slip(_ImageEvent(uid))
    return {"preview": sim.replies[0] if sim.replies else "",
            "owner_pushes": list(sim.pushes)}


def test_slip_image_stored_and_notifies_owner(sim, db, monkeypatch):
    # ลูกค้าสั่งบอทแล้วส่งรูปสลิป → เก็บรูป + ลิงก์ + สถานะรอยืนยัน + แจ้งเจ้าของ
    # (GROQ key ว่างในเทสต์ → OCR ปิด ยอด/ref เป็น None + แจ้งอ่านยอดไม่ได้)
    monkeypatch.delenv("SLIP_VIEW_TOKEN", raising=False)
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    sim.send("U_cust_1", "ยอด lean")
    r = _send_slip(sim, monkeypatch, "U_cust_1", b"\x89PNG fake-slip", "image/png")
    assert "รับรูปสลิปแล้ว" in r["preview"]
    assert len(r["owner_pushes"]) == 1
    assert "ส่งรูปสลิปมาแล้ว" in r["owner_pushes"][0]
    assert "อ่านยอดจากสลิปไม่ได้" in r["owner_pushes"][0]
    assert "ยอดคาด: 490 บาท" in r["owner_pushes"][0]
    assert "ดูสลิป:" in r["owner_pushes"][0]
    assert "/api/slips/" in r["owner_pushes"][0]
    assert "/ยืนยัน U_cust_1" in r["owner_pushes"][0]
    p = _purchase(db, "U_cust_1")
    assert p.status == "paid_pending"
    assert p.slip_url and "/api/slips/" in p.slip_url
    assert p.amount is None  # OCR ปิดในเทสต์
    assert p.ref_no is None
    slip = db.query(models.BotPurchaseSlip).filter_by(line_user_id="U_cust_1").first()
    assert slip is not None
    assert slip.content == b"\x89PNG fake-slip"
    assert slip.content_type == "image/png"
    assert slip.size_bytes == len(b"\x89PNG fake-slip")


def test_slip_image_without_order_guides_customer(sim, db, monkeypatch):
    # ยังไม่มีคำสั่งซื้อค้าง → ชี้ทางแตะสนใจแพ็กเกจก่อน ไม่เก็บรูป ไม่แจ้งเจ้าของ
    r = _send_slip(sim, monkeypatch, "U_cust_1", b"x")
    assert "ยังไม่เจอคำสั่งซื้อ" in r["preview"]
    assert r["owner_pushes"] == []
    assert db.query(models.BotPurchaseSlip).filter_by(line_user_id="U_cust_1").first() is None


def test_slip_download_streams_and_limits_size(monkeypatch):
    # _download_slip รวม chunks + content-type; เกิน SLIP_MAX_BYTES → _SlipTooLarge
    monkeypatch.setattr(lb.line_bot_api, "get_message_content",
                        lambda mid, timeout=None: _FakeContent(b"abcde", "image/jpeg"))
    data, ctype = lb._download_slip("msg_1")
    assert data == b"abcde"
    assert ctype == "image/jpeg"

    monkeypatch.setattr(lb.line_bot_api, "get_message_content",
                        lambda mid, timeout=None: _FakeContent(b"x" * (lb.SLIP_MAX_BYTES + 1)))
    with pytest.raises(lb._SlipTooLarge):
        lb._download_slip("msg_2")


def test_slip_download_failure_replies_error(sim, db, monkeypatch):
    # ดาวน์โหลดพัง (content หมดอายุ/เน็ตล่ม) → ตอบขอโทษ ไม่ crash ไม่เปลี่ยนสถานะ
    sim.send("U_cust_1", "ยอด lean")
    monkeypatch.setattr(lb.line_bot_api, "get_message_content",
                        lambda mid, timeout=None: (_ for _ in ()).throw(RuntimeError("expired")))
    sim.replies.clear()
    sim.pushes.clear()
    lb.image_slip(_ImageEvent("U_cust_1"))
    assert sim.replies, "ต้องตอบลูกค้าบางอย่าง"
    assert "ไม่สำเร็จ" in sim.replies[0]
    assert _purchase(db, "U_cust_1").status == "interested"  # ยังไม่เปลี่ยนเป็นรอยืนยัน
    assert sim.pushes == []


def test_slip_view_url_embeds_token(monkeypatch):
    # มี SLIP_VIEW_TOKEN → ฝัง token ในลิงก์ให้เจ้าของเปิดดูได้ทันที
    monkeypatch.setenv("SLIP_VIEW_TOKEN", "secret123")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.com")
    assert lb.slip_view_url(42) == "https://example.com/api/slips/42?token=secret123"


def test_slip_view_url_falls_back_to_cron_token(monkeypatch):
    # ไม่ตั้ง SLIP_VIEW_TOKEN → ใช้ CRON_TOKEN สำรอง
    monkeypatch.delenv("SLIP_VIEW_TOKEN", raising=False)
    monkeypatch.setenv("CRON_TOKEN", "cron_secret")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.com")
    assert lb.slip_view_url(7) == "https://example.com/api/slips/7?token=cron_secret"


def test_slip_view_url_open_without_token(monkeypatch):
    # ไม่ตั้ง token ทั้งคู่ → ลิงก์เปิด (เหมือน /health ใน dev)
    monkeypatch.delenv("SLIP_VIEW_TOKEN", raising=False)
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.com")
    assert lb.slip_view_url(9) == "https://example.com/api/slips/9"


def test_get_slip_image_serves_bytes(db, monkeypatch):
    # endpoint คืนรูปสลิปเป็น bytes + content-type ถูกต้อง (ไม่มี token = เปิด)
    slip = models.BotPurchaseSlip(line_user_id="U_cust_1", content=b"\x89PNG bytes",
                                  content_type="image/png", size_bytes=9)
    db.add(slip)
    db.commit()
    db.refresh(slip)
    monkeypatch.delenv("SLIP_VIEW_TOKEN", raising=False)
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    resp = lb.get_slip_image(slip.id, token="")
    assert resp.body == b"\x89PNG bytes"
    assert resp.media_type == "image/png"


def test_get_slip_image_requires_token(monkeypatch):
    # ตั้ง token แล้ว → ?token ผิด = 401
    monkeypatch.setenv("SLIP_VIEW_TOKEN", "secret123")
    with pytest.raises(lb.HTTPException) as exc:
        lb.get_slip_image(1, token="wrong")
    assert exc.value.status_code == 401


def test_get_slip_image_unknown_id_404(db, monkeypatch):
    # ไม่มี slip id นั้น → 404
    monkeypatch.delenv("SLIP_VIEW_TOKEN", raising=False)
    monkeypatch.delenv("CRON_TOKEN", raising=False)
    with pytest.raises(lb.HTTPException) as exc:
        lb.get_slip_image(999999, token="")
    assert exc.value.status_code == 404


def test_slip_ocr_match_notifies_owner(sim, db, monkeypatch):
    # OCR อ่านยอดได้ + ตรงยอดคาด → เก็บ amount/ref_no + แจ้งเจ้าของ ✓ ตรง
    monkeypatch.setattr(lb, "extract_slip_info",
                        lambda data, content_type="image/jpeg": {"amount": "490.00", "ref_no": "REF12345"})
    sim.send("U_cust_1", "ยอด lean")
    r = _send_slip(sim, monkeypatch, "U_cust_1", b"slip", "image/jpeg")
    assert "✓ ตรงกับยอดคาด" in r["owner_pushes"][0]
    assert "490.00 บาท" in r["owner_pushes"][0]
    assert "REF12345" in r["owner_pushes"][0]
    p = _purchase(db, "U_cust_1")
    assert p.amount == "490.00"
    assert p.ref_no == "REF12345"


def test_owner_slip_notify_has_tap_button(sim, db, monkeypatch):
    # แจ้งเจ้าของเป็น Flex การ์ด + ปุ่มแตะเปิดสลิปในแอป LINE ได้ทันที (ไม่ต้องคัดลอกลิงก์)
    captured = {}
    monkeypatch.setattr(lb.line_bot_api, "push_message",
                        lambda uid, msgs: captured.update(uid=uid, msgs=msgs))
    monkeypatch.setattr(lb, "extract_slip_info",
                        lambda data, content_type="image/jpeg": {"amount": "490.00", "ref_no": "REF1"})
    sim.send("U_cust_1", "ยอด lean")
    _send_slip(sim, monkeypatch, "U_cust_1", b"slip", "image/jpeg")
    assert captured["uid"] == lb.ADMIN_LINE_USER_ID
    msgs = captured["msgs"]
    assert len(msgs) == 2
    flex = next(m for m in msgs if isinstance(m, lb.FlexSendMessage))
    # alt_text = ข้อความสรุป (fallback/accessibility) — ข้อมูลครบเหมือนเดิม
    assert "ส่งรูปสลิปมาแล้ว" in flex.alt_text
    assert "✓ ตรงกับยอดคาด" in flex.alt_text
    footer = flex.contents.footer.contents[0]  # FlexSDK แปลง dict → typed container
    assert footer.type == "button"
    assert footer.action.type == "uri"
    assert footer.action.uri.startswith("https://") and "/api/slips/" in footer.action.uri
    # ข้อความยืนยันแยกเป็นอีกข้อความ ไม่ปนในการ์ด
    text = next(m for m in msgs if isinstance(m, lb.TextSendMessage))
    assert "/ยืนยัน U_cust_1" in text.text


def test_owner_slip_notify_flex_external_uri_scheme(sim, db, monkeypatch):
    # uri ของปุ่มต้องเป็น http(s) — LINE ปฏิเสธ uri อย่างอื่น
    captured = {}
    monkeypatch.setattr(lb.line_bot_api, "push_message",
                        lambda uid, msgs: captured.update(msgs=msgs))
    monkeypatch.setattr(lb, "extract_slip_info",
                        lambda data, content_type="image/jpeg": {"amount": None, "ref_no": None})
    sim.send("U_cust_1", "ยอด lean")
    _send_slip(sim, monkeypatch, "U_cust_1", b"slip", "image/jpeg")
    flex = next(m for m in captured["msgs"] if isinstance(m, lb.FlexSendMessage))
    uri = flex.contents.footer.contents[0].action.uri
    assert uri.startswith("https://") or uri.startswith("http://")


def test_slip_ocr_mismatch_flags_owner(sim, db, monkeypatch):
    # OCR อ่านยอดไม่ตรงยอดคาด → เตือนเจ้าของเช็คให้ดีก่อนยืนยัน
    monkeypatch.setattr(lb, "extract_slip_info",
                        lambda data, content_type="image/jpeg": {"amount": "500.00", "ref_no": None})
    sim.send("U_cust_1", "ยอด lean")
    r = _send_slip(sim, monkeypatch, "U_cust_1", b"slip", "image/jpeg")
    assert "ไม่ตรงกับยอดคาด" in r["owner_pushes"][0]
    assert "500.00 บาท" in r["owner_pushes"][0]
    p = _purchase(db, "U_cust_1")
    assert p.amount == "500.00"
    assert p.ref_no is None


def test_slip_ocr_parsing_helpers():
    assert slip_ocr.parse_amount("490.00") == 490.0
    assert slip_ocr.parse_amount("1,990 บาท") == 1990.0
    assert slip_ocr.parse_amount(None) is None
    assert slip_ocr.parse_amount("อ่านไม่ออก") is None
    assert slip_ocr.parse_amount_range("490 บาท") == (490.0, 490.0)
    assert slip_ocr.parse_amount_range("7,500–12,500 บาท") == (7500.0, 12500.0)
    assert slip_ocr.parse_amount_range("") is None


def test_slip_ocr_amount_matches():
    assert slip_ocr.amount_matches("490.00", "490 บาท") is True
    assert slip_ocr.amount_matches("1,990.00", "1,990 บาท") is True
    assert slip_ocr.amount_matches("10000", "7,500–12,500 บาท") is True
    assert slip_ocr.amount_matches("500", "490 บาท") is False
    assert slip_ocr.amount_matches(None, "490 บาท") is False


def test_extract_slip_info_no_key_returns_none(monkeypatch):
    # ไม่มี GROQ_API_KEY (conftest ปิด) → ไม่ยิง network คืน None/None
    monkeypatch.setattr(slip_ocr.settings, "GROQ_API_KEY", "")
    assert slip_ocr.extract_slip_info(b"img", "image/png") == {"amount": None, "ref_no": None}


def test_extract_slip_info_parses_groq_json(monkeypatch):
    # Groq vision (OpenAI-compat) คืน JSON → parse เป็น amount/ref_no
    class _FakeClient:
        api_key = "gsk_fake123"

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    assert kwargs["model"] == slip_ocr.settings.SLIP_OCR_MODEL
                    assert kwargs["messages"][0]["content"][1]["type"] == "image_url"
                    return type("R", (), {"choices": [type("C", (), {
                        "message": type("M", (), {"content": '{"amount": "490.00", "ref_no": "REF456"}'})()
                    })()]})()

    monkeypatch.setattr(slip_ocr, "groq_clients", lambda: [_FakeClient()])
    monkeypatch.setattr(slip_ocr.settings, "GROQ_API_KEY", "real_key")
    assert slip_ocr.extract_slip_info(b"img", "image/png") == {"amount": "490.00", "ref_no": "REF456"}


def test_payment_reply_shows_account_numbers_as_text(sim, monkeypatch):
    # ตั้งเลขพร้อมเพย์ + บัญชีธนาคาร → ข้อความโชว์เลขให้ลูกค้าจดได้ (นอกเหนือจาก QR)
    monkeypatch.setattr(lb, "OWNER_PROMPTPAY", "089-999-8888")
    monkeypatch.setattr(lb, "OWNER_BANK_NAME", "กสิกรไทย")
    monkeypatch.setattr(lb, "OWNER_BANK_ACCOUNT", "123-4-56789-0")
    monkeypatch.setattr(lb, "OWNER_BANK_HOLDER", "นายสมชาย ใจดี")
    text = lb.payment_reply_text()
    assert "089-999-8888" in text
    assert "กสิกรไทย" in text
    assert "123-4-56789-0" in text
    assert "นายสมชาย ใจดี" in text
    # ผ่านบอทจริงด้วย
    r = sim.send("U_cust_1", "วิธีจ่ายค่าบอท")
    assert "089-999-8888" in r["preview"]
    assert "123-4-56789-0" in r["preview"]


def test_plain_payment_words_answer_bot_payment(sim):
    # โฟกัสขายบอท (เจ้าของสั่ง): "ชำระเงิน/จ่ายเงิน/โอนเงิน" ทั่วไป → ตอบวิธีจ่ายค่าบอท ไม่ใช่จ่ายที่ Shopee
    for q in ("ชำระเงิน", "ชำระเงินยังไง", "จ่ายเงิน", "จ่ายเงินยังไง", "โอนเงิน", "โอนจ่าย", "จ่ายยังไง"):
        r = sim.send("U_cust_1", q)
        assert r["intent"] == "manual", f"'{q}' intent={r['intent']}"
        assert "วิธีจ่ายเงินค่าบอท" in r["preview"], f"'{q}' ควรตอบวิธีจ่ายค่าบอท: {r['preview'][:120]}"
        assert "Shopee" not in r["preview"], f"'{q}' ยังตอบจ่ายที่ Shopee: {r['preview'][:120]}"


def test_shopee_order_phrases_still_answer_shopee_payment(sim):
    # "สั่งซื้อ/ซื้อยังไง/วิธีซื้อ" ยังตอบสั่งผ่าน Shopee เหมือนเดิม (แยกจากจ่ายค่าบอท)
    for q in ("สั่งซื้อยังไง", "ซื้อสินค้ายังไง", "วิธีสั่งซื้อ"):
        r = sim.send("U_cust_1", q)
        assert r["intent"] == "manual", f"'{q}' intent={r['intent']}"
        assert "Shopee" in r["preview"], f"'{q}' ควรตอบสั่งผ่าน Shopee: {r['preview'][:120]}"


def test_package_card_has_realistic_leadtime():
    # การ์ดแพ็กเกจแต่ละใบมีระยะเวลาสร้างจริง (Lean 1 วัน / Business 5 วัน) ตรงกับ FAQ
    by_name = {p["name"]: p.get("leadtime", "") for p in lb.PACKAGES}
    assert "1 วัน" in by_name["🟡 Lean"]
    assert "2-3 วัน" in by_name["🟢 Starter"]
    assert "5 วัน" in by_name["🔵 Business"]
    assert "1-2 สัปดาห์" in by_name["🟣 White-Label"]
    assert "2-3 สัปดาห์" in by_name["🟠 ขายขาด"]
    # และแสดงบนการ์ดจริง (มี element ⏱️)
    d = _flex_dict(lb.package_flex_card())
    for b in d["contents"]:
        texts = [c.get("text", "") for c in b["body"]["contents"]]
        assert any("⏱️ เสร็จภายใน" in t for t in texts), f"การ์ด {b['header']['contents'][0]['text']} ไม่มีระยะเวลา"


def test_build_time_counts_from_confirmation_and_deposit(sim):
    # บอกชัดว่าเริ่มนับวันเมื่อยืนยันสั่งทำ + จ่ายเดือนแรกครบ (ขายขาด = มัดจำ 50%)
    r = sim.send("U_cust_1", "ใช้เวลานานแค่ไหน")
    assert r["intent"] == "manual"
    assert "จ่ายเดือนแรกครบ" in r["preview"], f"ไม่แจ้งเงื่อนไขเริ่มนับวัน: {r['preview'][:180]}"
    assert "มัดจำ 50%" in r["preview"], f"ไม่แจ้งเงื่อนไขขายขาด (มัดจำ 50%): {r['preview'][:180]}"
    assert "เริ่มนับวัน" in r["preview"], f"ไม่บอกว่าเริ่มนับวันเมื่อไหร่: {r['preview'][:180]}"
    assert "นับจากวันนั้น" in r["preview"], f"ไม่ชี้แจงว่านับจากวันที่จ่ายครบ: {r['preview'][:180]}"


def test_build_time_does_not_hijack_shipping_question(sim):
    # "ส่งของกี่วัน" = ถามจัดส่งสินค้า → ตอบ shipping (section ก่อนหน้า) ไม่ใช่ระยะเวลาสร้างบอท
    r = sim.send("U_cust_1", "ส่งของกี่วัน")
    assert r["intent"] == "manual"
    assert "จัดส่ง" in r["preview"], f"ส่งของกี่วันโดน build-time แย่ง: {r['preview'][:120]}"
    assert "ระยะเวลาทำบอท" not in r["preview"]


def test_build_time_answers_plain_duration_word(sim):
    # "ระยะเวลา" คำเดียว (ไม่มีคำต่อ) → ตอบระยะเวลาทำบอท ไม่หลุดไปตอบทั่วไป
    r = sim.send("U_cust_1", "ระยะเวลา")
    assert r["intent"] == "manual"
    assert "ระยะเวลาทำบอท" in r["preview"], f"'ระยะเวลา' เดี่ยว ตอบไม่ตรง: {r['preview'][:140]}"


def test_build_time_includes_buffer_note(sim):
    # หมายเหตุ buffer: ระยะเวลาอาจบวกลบ 1–2 วันตามคิวงาน (บอกตามตรง ไม่ผูกวันที่แน่นอน)
    r = sim.send("U_cust_1", "กี่วันเสร็จ")
    assert "บวกลบ 1–2 วัน" in r["preview"], f"ไม่มีหมายเหตุ buffer: {r['preview'][:200]}"
    # แตะแพ็กเกจก็เห็นหมายเหตุเดียวกัน
    assert "บวกลบ 1–2 วัน" in lb.package_payment_reply("lean")


def test_package_payment_reply_includes_leadtime_and_features():
    # แตะแพ็กเกจ → เห็นราคา + ระยะเวลาทำ + สิ่งที่ได้ + ยอดจ่าย ในที่เดียว
    r = lb.package_payment_reply("business")
    assert "🔵 Business 1,990฿/เดือน" in r
    assert "เสร็จภายใน 5 วัน" in r
    assert "สิ่งที่ได้" in r
    assert "จ่ายเดือนแรกก่อนเริ่มทำ: 1,990 บาท" in r


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


def test_greeting_opens_with_five_steps(sim):
    # ป้าเข็มต้อง 5 ขั้นตอนเมื่อเจอลูกค้า — "สวัสดี" ต้องเปิดด้วยมาตรฐาน 5 ขั้นตอน
    r = sim.send("U_cust_1", "สวัสดี")
    assert r["intent"] == "greeting"
    assert "5 ขั้นตอน" in r["preview"]
    assert "ต้อนรับอย่างอบอุ่น" in r["preview"]
    assert "ติดตามผลและขอบคุณ" in r["preview"]


def test_follow_welcome_includes_five_steps(sim):
    # แอดเพื่อนครั้งแรก (เจอลูกค้า) → welcome ต้องมีมาตรฐาน 5 ขั้นตอนด้วย
    lb.follow_event(_FollowEv("U_cust_1"))
    joined = " | ".join(sim.pushes)
    assert "5 ขั้นตอน" in joined
    assert "ต้อนรับอย่างอบอุ่น" in joined


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


def test_contact_owner_shows_direct_contact(sim):
    # "ติดต่อเจ้าของร้าน" → ตอบช่องทางติดต่อตรง (LINE ID + ลิงก์) ไม่เข้า flow ฝากคำถามแล้ว
    r = sim.send("U_cust_1", "ติดต่อเจ้าของร้าน")
    assert r["intent"] == "human"
    assert "ติดต่อป้าเข็มได้โดยตรง" in r["preview"]
    assert "👉 LINE:" in r["preview"]
    assert "🔗" in r["preview"]  # ลิงก์แอดไลน์
    assert "ฝากคำถามได้เลย" not in r["preview"]  # ไม่ชวนฝากคำถามแล้ว
    # ข้อความถัดไปตอบปกติ ไม่ถูกเก็บเป็นฝากคำถาม
    r2 = sim.send("U_cust_1", "หูฟัง")
    assert r2["intent"] == "search"


def test_ask_phone_shows_owner_contact(sim):
    # "เบอร์โทร..." → ช่องทางติดต่อตรงเหมือนกัน (ไม่ตกไป FAQ/ค้นสินค้า)
    r = sim.send("U_cust_1", "เบอร์โทรป้าเข็ม")
    assert r["intent"] == "human"
    assert "ติดต่อป้าเข็มได้โดยตรง" in r["preview"]


def test_chat_button_enters_ai_flow(sim):
    # "คุยกับป้าเข็ม" ต้องแนะนำตัวบอท + เข้าเรื่องราคา/แพ็กเกจ แล้วรอรับคำถามถัดไป
    r1 = sim.send("U_cust_1", "คุยกับป้าเข็ม")
    assert r1["intent"] == "human"
    assert "ป้าเข็มเป็นบอทไลน์" in r1["preview"]
    assert "490฿/เดือน" in r1["preview"]
    assert "ราคาบอท/แพ็กเกจ" in r1["preview"]
    assert "พิมพ์ชื่อสินค้า" in r1["preview"]
    r2 = sim.send("U_cust_1", "หูฟัง")
    assert r2["intent"] == "search"


def test_chat_button_guides_to_pricing_not_five_steps(sim):
    # กด "คุยกับป้าเข็ม" → คำแนะนำตัวบอท + ชี้ไปราคา/แพ็กเกจ (ไม่ซ้ำ 5 ขั้นตอนที่โชว์ตอนสวัสดี)
    r1 = sim.send("U_cust_1", "คุยกับป้าเข็ม")
    assert r1["intent"] == "human"
    assert "5 แพ็กเกจ" in r1["preview"]
    assert "490฿/เดือน" in r1["preview"]
    # ไม่โชว์ 5 ขั้นตอนซ้ำที่นี่ (โชว์แล้วตอน "สวัสดี"/แอดเพื่อน)
    assert "ต้อนรับอย่างอบอุ่น" not in r1["preview"]
    assert "ติดตามผลและขอบคุณ" not in r1["preview"]


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
        sales_count=5000, affiliate_url="https://s.shopee.co.th/test",
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
        sales_count=5000, affiliate_url="https://s.shopee.co.th/test",
        link_status="ok", ai_score=50))
    db.add(models.Product(
        name="ถุงเท้าแฟชั่นลายการ์ตูน 2 คู่", category="แฟชั่น", price=450,
        sales_count=5000, affiliate_url="https://s.shopee.co.th/test",
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
        sales_count=5000, affiliate_url="https://s.shopee.co.th/test",
        link_status="ok", ai_score=50))
    db.add(models.Product(
        name="นาฬิกาอัจฉริยะ KENTO", category="แฟชั่น", price=900,
        sales_count=5000, affiliate_url="https://s.shopee.co.th/test",
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
