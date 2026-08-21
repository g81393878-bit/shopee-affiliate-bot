# -*- coding: utf-8 -*-
"""คลังโพสต์ท้องถิ่น (ร้านอร่อย / ของฝาก / ของกิน) — Firecrawl ค้นตามจังหวัดแล้วเขียนเสียงป้าเข็ม.

เหตุผล: เพจไม่ควรมีแต่โพสต์ขายของ — คอนเทนต์ไลฟ์สไตล์ท้องถิ่น (กิน/เที่ยว/ของฝาก)
ดึง engagement และชวนเพิ่มเพื่อน LINE OA; โครงสร้างเดียวกับ facebook_curated (RSS)
แต่แหล่งข้อมูล = Firecrawl search หมุนเวียน 77 จังหวัด × 3 หัวข้อ

ตั้งค่า:
  - ใช้ Firecrawl search (FIRECRAWL_API_KEY) หาผลดิบ → Groq เขียนเสียงป้าเข็ม
  - Firecrawl ล้ม → fallback ข้อความตรงจากหัวข้อ; Groq ล้ม → fallback ข้อความตรง

กันซ้ำ: CampaignLog status='fblocal', category = sha1(url) — ไม่โพสต์ที่เดิมซ้ำ
หมุนเวียน: index = จำนวนโพสต์ fblocal ที่สำเร็จแล้ว → จังหวัด[index%77] + หัวข้อ[index%3]
"""
import hashlib
import logging
import os
from urllib.parse import urlparse

from app.config import settings
from app.services.persona import persona_system_prompt
from app.services.bot_profile import line_cta_footer

logger = logging.getLogger(__name__)

_LINE_PLACEHOLDER = "https://lin.ee/o9Kjp1N"

# ลิงก์ที่ Facebook Graph API ใช้เป็น link preview ไม่ได้ (เจอจริง: โพสต์กลุ่ม facebook.com
# → "Permissions error" ทำให้คลังท้องถิ่นติดตายซ้ำทุก tick) → ข้ามตั้งแต่ตอน fetch
_SKIP_HOSTS = ("facebook.com", "fb.com", "fb.watch", "messenger.com", "m.me")

# 77 จังหวัดไทย — หมุนเวียนตามลำดับ (ครอบคลุมทั้งประเทศ)
_PROVINCES = [
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น",
    "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย",
    "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก", "นครปฐม", "นครพนม",
    "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน",
    "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี",
    "พระนครศรีอยุธยา", "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี",
    "เพชรบูรณ์", "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน", "ยโสธร",
    "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง", "ราชบุรี", "ลพบุรี", "ลำปาง", "ลำพูน",
    "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ", "สมุทรสงคราม",
    "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี",
    "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย", "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ",
    "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี",
]

# 3 หัวข้อหมุนเวียน (label ใช้แสดง, kw ใช้ search)
_TOPICS = [
    ("ร้านอาหารเด็ด", "ร้านอาหารเด็ด"),
    ("ของฝากขึ้นชื่อ", "ของฝากขึ้นชื่อ"),
    ("ของกินอร่อย", "ของกินอร่อย"),
]


def _pick(index: int):
    """เลือกจังหวัด + หัวข้อตาม index (หมุนครบ 77 จังหวัด แล้ววนใหม่; หัวข้อสลับทุกตัว)."""
    province = _PROVINCES[index % len(_PROVINCES)]
    label, kw = _TOPICS[index % len(_TOPICS)]
    return province, label, kw


def fetch_local_items(index: int = 0, max_items: int = 5) -> list:
    """ค้น Firecrawl ตามจังหวัด+หัวข้อที่หมุนจาก index → list ของ item dict.

    item = {guid, title, link, summary, source, topic} (โครงสร้างเดียวกับ RSS)
    Firecrawl ล้ม/ไม่มีผล → คืน [] (best-effort ไม่ทำให้ scheduler พัง)
    """
    province, label, kw = _pick(index)
    query = f"{kw} จังหวัด{province} แนะนำ"
    try:
        from app.services.web_search import firecrawl_search_results
        results = firecrawl_search_results(query, max_results=max_items)
    except Exception as e:
        logger.warning(f"[local] Firecrawl ล้ม ({province}/{label}): {e}")
        return []
    items = []
    for r in results:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        summary = (r.get("content") or "").strip()
        if not title or not url or not _link_ok(url):
            continue
        items.append({
            "guid": url,
            "title": title,
            "link": url,
            "summary": summary[:500],
            "source": "firecrawl",
            "topic": f"{label} · จ.{province}",
        })
    return items


def _link_ok(url: str) -> bool:
    """ลิงก์ใช้โพสต์ Facebook ได้ไหม — ตัดโดเมน Facebook เอง (เจอ Permissions error)."""
    host = (urlparse(url or "").hostname or "").lower()
    if not host:
        return False
    return not any(host == h or host.endswith("." + h) for h in _SKIP_HOSTS)


def item_key(item: dict) -> str:
    """sha1 hex ของ guid|link (40 ตัว — พอดีคอลัมน์ CampaignLog.category 50 ตัว)."""
    return hashlib.sha1((item.get("guid") or item.get("link") or "").encode("utf-8")).hexdigest()


def _groq_caption(item: dict) -> str:
    """Groq เขียนโพสต์เสียงป้าเข็ม 2-3 ประโยคแนะนำร้าน/ของฝาก/ของกิน (ข้อความล้วน)."""
    from app.services.llm_clients import call_with_backoff, groq_clients
    clients = groq_clients()
    if not clients:
        raise RuntimeError("ไม่มี Groq key")
    prompt = (
        "เขียนโพสต์ Facebook ภาษาไทยสั้น ๆ (2-3 ประโยค) ในเสียง \"ป้าเข็ม\" แม่ค้าออนไลน์ "
        "ใจดี ที่จะมาแนะนำร้านอร่อย/ของฝาก/ของกินนี้ให้ลูกหลานฟัง แบบคนพื้นที่รู้จริง "
        "พร้อมคอมเมนต์ส่วนตัวชวนให้ไปลอง/ตามรอย (สโลแกน \"ถ้าไม่คุ้ม ป้าบอกให้\") "
        "ใช้ emoji ได้เล็กน้อย\n\n"
        f"ชื่อ/หัวข้อ: {item['title']}\n"
        f"รายละเอียด: {(item.get('summary') or '')[:500]}\n"
        f"พื้นที่/หมวด: {item.get('topic') or ''}\n\n"
        "ตอบเฉพาะข้อความโพสต์เท่านั้น ไม่มีคำอธิบายอื่น"
    )
    last_err = None
    for client in clients:
        try:
            resp = call_with_backoff(
                lambda: client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[
                        {"role": "system",
                         "content": persona_system_prompt("เขียนโพสต์ Facebook ภาษาไทยสั้น ๆ")},
                        {"role": "user", "content": prompt},
                    ],
                ),
                circuit_key=client.api_key,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            logger.warning(f"[local] Groq key {client.api_key[:8]}... failed: {e}")
    raise last_err or RuntimeError("Groq ล้มทุก key")


def curate_local_caption(item: dict, line_oa: str = "") -> str:
    """caption โพสต์ท้องถิ่น = คอมเมนต์เสียงป้าเข็ม (Groq/fallback) + ลิงก์ LINE OA + hashtags."""
    line_oa = line_oa or (os.getenv("LINE_OA_URL") or "").strip() or _LINE_PLACEHOLDER
    try:
        caption = _groq_caption(item)
    except Exception as e:
        logger.warning(f"[local] Groq ล้ม ใช้ fallback: {e}")
        caption = ""
    if not caption:
        caption = f"ป้าไปเจอ {item['title']} ที่{item.get('topic') or 'บ้านเรา'} มาฝากลูกหลาน 😋"
    parts = [caption]
    parts.append(line_cta_footer(line_oa))
    parts.append("#ป้าเข็ม #เที่ยวไทย #ของกินอร่อย #ถ้าไม่คุ้มป้าบอกให้")
    return "\n\n".join(parts)
