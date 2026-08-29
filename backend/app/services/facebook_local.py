# -*- coding: utf-8 -*-
"""คลังโพสต์สินค้าเทรนด์ & ไอเทมยอดนิยม — Firecrawl ค้นหาสินค้ากระแส/ของจำเป็นต้องมี แล้วเขียนเสียงป้าเข็มด้วย Groq.

เหตุผล: เพจต้องการนำเสนอสินค้าที่คนกำลังชื่นชม รีวิวแน่น หรือเป็นของจำเป็นต้องใช้ในชีวิตประจำวัน
เพื่อสร้างความสนใจ ตอบโจทย์ความต้องการจริง และชวนทักแชท LINE OA / กดลิงก์ Shopee

แหล่งข้อมูล: Firecrawl search หมุนเวียน 8 หมวดหมู่สินค้าขายดี × 3 มุมมองความต้องการ
ตั้งค่า:
  - ใช้ Firecrawl search (FIRECRAWL_API_KEY) หาผลดิบ → Groq เขียนเสียงป้าเข็ม
  - Firecrawl ล้ม → fallback ข้อความตรงจากหัวข้อ; Groq ล้ม → fallback ข้อความตรง

กันซ้ำ: CampaignLog status='fblocal', category = sha1(url) — ไม่โพสต์สินค้าเดิมซ้ำ
หมุนเวียน: index = จำนวนโพสต์ fblocal ที่สำเร็จแล้ว → หมวดหมู่[index%8] + มุมมอง[index%3]
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

# ลิงก์ที่ Facebook Graph API ใช้เป็น link preview ไม่ได้
_SKIP_HOSTS = ("facebook.com", "fb.com", "fb.watch", "messenger.com", "m.me")

# 8 หมวดหมู่สินค้ากระแส / ของจำเป็นต้องใช้ ที่คนไทยค้นหาและรีวิวสูง
_PRODUCT_CATEGORIES = [
    {
        "category": "ของใช้ในบ้านและจัดระเบียบ",
        "tag": "ของใช้ในบ้าน",
        "keywords": ["ของใช้ในบ้าน ของมันต้องมี", "อุปกรณ์จัดระเบียบห้อง รีวิว", "ของแต่งบ้านมินิมอล ใช้ดี"]
    },
    {
        "category": "สมาร์ตโฮมและเครื่องใช้ไฟฟ้ามินิ",
        "tag": "เครื่องใช้ไฟฟ้า",
        "keywords": ["เครื่องใช้ไฟฟ้ามินิ ตัวช่วยชีวิต", "โคมไฟโซล่าเซลล์ อัตโนมัติ", "เครื่องฟอกอากาศ พัดลมพกพา รีวิว"]
    },
    {
        "category": "สุขภาพและคลายปวดเมื่อย",
        "tag": "สุขภาพ",
        "keywords": ["ไอเทมแก้ปวดหลัง ออฟฟิศซินโดรม", "ปืนนวด เครื่องนวดเพื่อสุขภาพ รีวิว", "อุปกรณ์ดูแลสุขภาพประจำบ้าน"]
    },
    {
        "category": "ความงามและของใช้ส่วนตัว",
        "tag": "ความงาม",
        "keywords": ["ของใช้ส่วนตัว ใช้หมดซื้อซ้ำ", "สำลี สกินแคร์ รีวิว pantip", "ครีมกันแดด เซรั่ม ใช้ดีบอกต่อ"]
    },
    {
        "category": "อุปกรณ์ไอทีและแกดเจ็ตมือถือ",
        "tag": "แกดเจ็ตไอที",
        "keywords": ["อุปกรณ์ไอที คุ้มราคา ได้มาตรฐาน", "เคสมือถือ ฟิล์มกันกระแทก ตัวท็อป", "พาวเวอร์แบงก์ สายชาร์จเร็ว มอก"]
    },
    {
        "category": "สินค้าสัตว์เลี้ยงสำหรับทาสแมวทาสหมา",
        "tag": "ของใช้สัตว์เลี้ยง",
        "keywords": ["ของใช้แมว สุนัข ทาสแมวต้องมี", "ที่ลับเล็บ ทรายแมว ผงดับกลิ่น รีวิว", "ของเล่นสัตว์เลี้ยง คุณภาพดี"]
    },
    {
        "category": "อุปกรณ์ครัวและทำอาหารง่าย",
        "tag": "เครื่องครัว",
        "keywords": ["เครื่องครัวเด็กหอ ประหยัดเวลา", "หม้อหุงข้าว กระทะ เคลือบไม่ติด", "อุปกรณ์ทำอาหารง่ายๆ สะดวก"]
    },
    {
        "category": "อุปกรณ์ดูแลรถและการเดินทาง",
        "tag": "ของใช้ติดรถ",
        "keywords": ["ของใช้ติดรถยนต์ ต้องมีติดไว้", "ที่ชาร์จในรถ ที่วางมือถือ จัดระเบียบ", "อุปกรณ์ฉุกเฉิน พกพาสะดวก"]
    },
]

# 3 มุมมองการป้ายยา (หมุนเวียนเพื่อความหลากหลายของสไตล์โพสต์)
_SEARCH_ANGLES = [
    ("รีวิวบอกต่อ", "รีวิว pantip ใช้ดีบอกต่อ"),
    ("ของมันต้องมี", "ของมันต้องมี ซื้อแล้วคุ้ม"),
    ("ยอดฮิตขายดี", "ยอดฮิต ซื้อซ้ำบ่อย แนะนำ"),
]


def _pick(index: int):
    """เลือกหมวดหมู่สินค้า + มุมมองการค้นหาตาม index."""
    cat_obj = _PRODUCT_CATEGORIES[index % len(_PRODUCT_CATEGORIES)]
    angle_label, angle_kw = _SEARCH_ANGLES[index % len(_SEARCH_ANGLES)]
    
    # เลือก keyword จากในหมวดตามมุมมอง
    kw_list = cat_obj["keywords"]
    base_kw = kw_list[index % len(kw_list)]
    
    return cat_obj["category"], cat_obj["tag"], angle_label, f"{base_kw} {angle_kw}"


def fetch_local_items(index: int = 0, max_items: int = 5) -> list:
    """ค้น Firecrawl ตามหมวดสินค้าเทรนด์และมุมมองที่หมุนจาก index → list ของ item dict.

    item = {guid, title, link, summary, source, topic}
    Firecrawl ล้ม/ไม่มีผล → คืน [] (best-effort ไม่ทำให้ scheduler พัง)
    """
    category_name, tag, angle_label, query = _pick(index)
    try:
        from app.services.web_search import firecrawl_search_results
        results = firecrawl_search_results(query, max_results=max_items)
    except Exception as e:
        logger.warning(f"[trend-hunt] Firecrawl ล้ม ({category_name}/{angle_label}): {e}")
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
            "topic": f"{tag} · {angle_label}",
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
    """Groq เขียนโพสต์เสียงป้าเข็มตามกฎ 3-Second Hook ป้ายยาชี้เป้าสินค้าเทรนด์/ของจำเป็น (ข้อความล้วน)."""
    from app.services.llm_clients import call_with_backoff, groq_clients
    clients = groq_clients()
    if not clients:
        raise RuntimeError("ไม่มี Groq key")
        
    prompt = (
        "เขียนโพสต์ Facebook ป้ายยาชี้เป้าสินค้าเทรนด์ตามกฎ 'หยุดนิ้วใน 3 วินาที' (3-Second Hook Rule) ในเสียง 'ป้าเข็ม':\n\n"
        "โครงสร้าง 3 จังหวะ:\n"
        "1. บรรทัดแรก: ประโยค Hook กระตุกความอยากรู้/ปัญหาชีวิต หยุดนิ้วคนดูใน 3 วินาที (ใช้อิโมจิเด่น เช่น 🚨 🔥 💡 😱)\n"
        "2. บรรทัดที่สอง: บอกจุดเด่นที่คุ้มค่า ทำไมคนถึงชื่นชม หรือทำไมต้องมีติดบ้าน 1-2 ประโยคสั้นกระชับ (สโลแกน 'ถ้าไม่คุ้ม ป้าบอกให้')\n"
        "3. บรรทัดสุดท้าย: CTA ชวนกดดูพิกัดของแท้ หรือทักถามป้าเข็ม\n\n"
        f"ชื่อ/หัวข้อสินค้า: {item['title']}\n"
        f"จุดเด่น/รีวิว: {(item.get('summary') or '')[:500]}\n"
        f"หมวดหมู่: {item.get('topic') or ''}\n\n"
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
                         "content": persona_system_prompt("เขียนโพสต์ Facebook สไตล์ 3-Second Hook ป้ายยาสินค้า")},
                        {"role": "user", "content": prompt},
                    ],
                ),
                circuit_key=client.api_key,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            logger.warning(f"[trend-hunt] Groq key {client.api_key[:8]}... failed: {e}")
    raise last_err or RuntimeError("Groq ล้มทุก key")


def curate_local_caption(item: dict, line_oa: str = "") -> str:
    """caption โพสต์สินค้าเทรนด์ = คอมเมนต์เสียงป้าเข็ม (Groq/fallback) + ลิงก์ LINE OA + hashtags."""
    line_oa = line_oa or (os.getenv("LINE_OA_URL") or "").strip() or _LINE_PLACEHOLDER
    try:
        caption = _groq_caption(item)
    except Exception as e:
        logger.warning(f"[trend-hunt] Groq ล้ม ใช้ fallback: {e}")
        caption = ""
    if not caption:
        caption = f"🚨 เตือนแล้วนะ! ใครยังไม่มี {item['title']} ติดบ้านคือพลาดมาก รีวิว 5 ดาวแน่น คุ้มค่าน่าใช้สุด ๆ จ้า ✨"
        
    parts = [caption]
    parts.append(line_cta_footer(line_oa))
    parts.append("#ของดีบอกต่อ #ของมันต้องมี #ป้าเข็มป้ายยา #ถ้าไม่คุ้มป้าบอกให้ #ShopeeAffiliate")
    return "\n\n".join(parts)
