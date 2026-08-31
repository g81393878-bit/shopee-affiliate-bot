# -*- coding: utf-8 -*-
"""คอนเทนต์โลก & เทรนด์กระแส (RSS Curated) — ดึงข่าว/เทรนด์จาก RSS feed หลากหลายสำนักข่าว
แล้วนำมาวิเคราะห์เชื่อมโยงกับ 8 หมวดหมู่สินค้าขายดีและของจำเป็นต้องมี เขียนเป็นเสียงป้าเข็มด้วย Groq.

เหตุผล: เพจไม่ควรมีแต่โพสต์ขายของตรงๆ — การนำข่าว/เทรนด์สดใหม่มาสรุปภาษาชาวบ้าน
และป้ายยาเชื่อมโยงสู่สินค้าจำเป็นที่ตอบโจทย์จากข่าวนั้น ทำให้เพจน่าติดตามและได้ยอดขาย Affiliate สูงขึ้น

ตั้งค่า:
  - RSS_SOURCES_JSON (env, JSON array) — override รายชื่อ feed ได้ (ไม่ตั้ง = ใช้ default 7 สำนักข่าว)
  - ใช้ Groq วิเคราะห์และเขียนเสียงป้าเข็ม; Groq ล้ม → fallback ข้อความตรง

กันซ้ำ: CampaignLog status='fbrss', category = sha1(guid|link) — ไม่โพสต์ข่าวเดิมซ้ำ
"""
import hashlib
import html
import re
import json
import logging
import os
import xml.etree.ElementTree as ET

import httpx

from app.config import settings
from app.services.persona import persona_system_prompt
from app.services.bot_profile import line_cta_footer

logger = logging.getLogger(__name__)

_LINE_PLACEHOLDER = "https://lin.ee/o9Kjp1N"

# สำนักข่าว & บล็อกไลฟ์สไตล์/ไอที/การตลาดชั้นนำของไทย (คัดกรอง feed ที่เสถียร 100%)
_DEFAULT_SOURCES = [
    {"name": "Beartai", "url": "https://www.beartai.com/feed", "topic": "เทคโนโลยี/นวัตกรรม/ไลฟ์สไตล์"},
    {"name": "Techhub", "url": "https://www.techhub.in.th/feed/", "topic": "ไอที/คอมพิวเตอร์/แกดเจ็ต"},
    {"name": "The Standard", "url": "https://thestandard.co/feed", "topic": "ข่าวสาร/เทรนด์ชีวิต/ไลฟ์สไตล์"},
    {"name": "DroidSans", "url": "https://droidsans.com/feed/", "topic": "มือถือ/แกดเจ็ต/สมาร์ตโฟน"},
    {"name": "Brand Inside", "url": "https://brandinside.asia/feed/", "topic": "ธุรกิจ/เทรนด์ผู้บริโภค/การใช้จ่าย"},
    {"name": "Marketing Oops", "url": "https://www.marketingoops.com/feed/", "topic": "นวัตกรรม/เทรนด์สินค้าใหม่"},
    {"name": "Mango Zero", "url": "https://www.mangozero.com/feed/", "topic": "ไลฟ์สไตล์/ไอเดียของใช้/คนรุ่นใหม่"},
    {"name": "Kapook Trend", "url": "https://hilight.kapook.com/rss", "topic": "ข่าวกระแส/สุขภาพ/ของใช้ประจำวัน"},
]

# 8 หมวดหมู่สินค้าขายดี & ของจำเป็นต้องมี สำหรับเชื่อมโยงกับข่าว
_8_PRODUCT_CATEGORIES = (
    "1. ของใช้ในบ้านและจัดระเบียบ\n"
    "2. สมาร์ตโฮมและเครื่องใช้ไฟฟ้ามินิ\n"
    "3. สุขภาพและคลายปวดเมื่อย\n"
    "4. ความงามและของใช้ส่วนตัว\n"
    "5. อุปกรณ์ไอทีและแกดเจ็ตมือถือ\n"
    "6. สินค้าสัตว์เลี้ยงสำหรับทาสแมวทาสหมา\n"
    "7. อุปกรณ์ครัวและทำอาหารง่าย\n"
    "8. อุปกรณ์ดูแลรถและการเดินทาง"
)


def _rss_sources() -> list:
    """รายชื่อ feed — override ได้ด้วย env RSS_SOURCES_JSON (JSON array ของ {name,url,topic})"""
    raw = (os.getenv("RSS_SOURCES_JSON") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                return data
        except Exception as e:  # config ผิด → ใช้ default (อย่าให้บอทพัง)
            logger.warning(f"[curated] RSS_SOURCES_JSON ใช้ไม่ได้ ({e}) — ใช้ default")
    return _DEFAULT_SOURCES


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _rss_item(el, source: dict) -> dict:
    """RSS 2.0 <item> → dict"""
    return {
        "guid": _text(el, "guid") or _text(el, "link"),
        "title": html.unescape(_text(el, "title")),
        "link": _text(el, "link"),
        "summary": html.unescape(_text(el, "description"))[:800],
        "source": source.get("name", ""),
        "topic": source.get("topic", ""),
    }


def _atom_item(el, source: dict) -> dict:
    """Atom <entry> (namespace) → dict"""
    title, link, guid, summary = "", "", "", ""
    for child in el:
        tag = child.tag.split("}")[-1]
        if tag == "title":
            title = child.text or ""
        elif tag == "link":
            link = child.get("href") or ""
        elif tag == "id":
            guid = child.text or ""
        elif tag in ("summary", "content"):
            summary = child.text or ""
    return {
        "guid": guid or link,
        "title": html.unescape(title).strip(),
        "link": link,
        "summary": html.unescape(summary)[:800],
        "source": source.get("name", ""),
        "topic": source.get("topic", ""),
    }


def _parse_feed(xml_text: str, source: dict) -> list:
    """parse XML (RSS2 / Atom) → list ของ item dict (คืน [] ถ้า parse ไม่ได้)

    ใช้ tag.split('}')[-1] เพราะ Atom มี default namespace (tag จริง = {ns}entry)
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = [_rss_item(it, source) for it in root.iter() if it.tag.split("}")[-1] == "item"]
    if not items:
        items = [_atom_item(it, source) for it in root.iter() if it.tag.split("}")[-1] == "entry"]
    return items


def fetch_news_items(max_items: int = 20) -> list:
    """ดึงข่าวจากทุก feed → list ของ {guid,title,link,summary,source,topic} (ตัด guid ซ้ำ).

    feed ไหนพัง/โดนบล็อก → ข้ามไป (log warning) ไม่ทำให้บอทล้ม
    """
    items, seen = [], set()
    for src in _rss_sources():
        url = src.get("url", "")
        if not url:
            continue
        try:
            r = httpx.get(url, timeout=15, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            if r.status_code != 200:
                logger.warning(f"[curated] feed {url} HTTP {r.status_code}")
                continue
            for it in _parse_feed(r.text, src):
                key = it["guid"] or it["link"]
                if not key or key in seen:
                    continue
                seen.add(key)
                items.append(it)
        except Exception as e:
            logger.warning(f"[curated] feed {url} failed: {e}")
    return items[:max_items]


def item_key(item: dict) -> str:
    """sha1 hex ของ guid|link (40 ตัว — พอดีคอลัมน์ CampaignLog.category 50 ตัว)"""
    return hashlib.sha1((item.get("guid") or item.get("link") or "").encode("utf-8")).hexdigest()


def _groq_caption(item: dict) -> str:
    """Groq เขียนโพสต์เสียงป้าเข็ม สรุปข่าวภาษาชาวบ้าน + วิเคราะห์เชื่อมโยงกับ 8 หมวดหมู่สินค้าจำเป็น (ข้อความล้วน)."""
    from app.services.llm_clients import call_with_backoff, groq_clients
    clients = groq_clients()
    if not clients:
        raise RuntimeError("ไม่มี Groq key")
        
    prompt = (
        "เขียนโพสต์ Facebook สรุปข่าวและป้ายยาสินค้าตามกฎ 'หยุดนิ้วใน 3 วินาที' (3-Second Hook Rule) ในเสียง 'ป้าเข็ม':\n\n"
        "โครงสร้าง 3 จังหวะ:\n"
        "1. บรรทัดแรก: ประโยค Hook สรุปประเด็นข่าวที่น่าตื่นเต้น/สะดุดตา หยุดนิ้วคนดูใน 3 วินาที (ใช้อิโมจิเด่น เช่น 🚨 🔥 💡 😱)\n"
        "2. บรรทัดที่สอง: สรุปข่าวสั้นภาษาชาวบ้าน + วิเคราะห์เชื่อมโยงว่าควรมีไอเทมสินค้าอะไรใน 8 หมวดนี้ติดบ้านไว้:\n"
        f"{_8_PRODUCT_CATEGORIES}\n"
        "3. บรรทัดสุดท้าย: ชูความคุ้มค่าตามสโลแกน 'ถ้าไม่คุ้ม ป้าบอกให้' และชวนทักแชทถามพิกัด Shopee\n\n"
        f"สำนักข่าว: {item.get('source', '')} ({item.get('topic', '')})\n"
        f"หัวข้อข่าว: {item['title']}\n"
        f"เนื้อหาข่าว: {(item.get('summary') or '')[:500]}\n\n"
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
                         "content": persona_system_prompt("เขียนโพสต์ Facebook สรุปข่าวและป้ายยาสินค้า")},
                        {"role": "user", "content": prompt},
                    ],
                ),
                circuit_key=client.api_key,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            logger.warning(f"[curated] Groq key {client.api_key[:8]}... failed: {e}")
    raise last_err or RuntimeError("Groq ล้มทุก key")


def curate_caption(item: dict, line_oa: str = "") -> str:
    """caption โพสต์คอนเทนต์โลก = คอมเมนต์เสียงป้าเข็ม (Groq/fallback) + ลิงก์ LINE OA + hashtags"""
    line_oa = line_oa or (os.getenv("LINE_OA_URL") or "").strip() or _LINE_PLACEHOLDER
    try:
        caption = _groq_caption(item)
    except Exception as e:
        logger.warning(f"[curated] Groq ล้ม ใช้ fallback: {e}")
        caption = ""
    if not caption:
        caption = f"ป้าเห็นข่าว {item['title']} แล้วต้องรีบเอามาบอกทุกคนเลยจ้า เข้ากับยุคนี้มาก 😊"
    caption = _remove_child_address(caption)
    parts = [caption]
    parts.append(line_cta_footer(line_oa))
    parts.append("#ของดีบอกต่อ #เกาะกระแส #เทรนด์วันนี้ #ป้าเข็มป้ายยา #ถ้าไม่คุ้มป้าบอกให้ #ShopeeAffiliate")
    return "\n\n".join(parts)


def _remove_child_address(text: str) -> str:
    for old, new in (
        ("ลูกหลาน", "ทุกคน"),
        ("ลูกรัก", "สัตว์เลี้ยงที่รัก"),
        ("นะลูก", "นะจ๊ะ"),
        ("เลยลูก", "เลยจ้า"),
        ("จ้ะลูก", "จ้ะทุกคน"),
        ("จ้าลูก", "จ้าทุกคน"),
        ("ดูแลลูก", "ดูแลทุกคน"),
        ("ให้ลูก", "ให้ทุกคน"),
        ("ช่วยลูก", "ช่วยทุกคน"),
        ("ลูกได้", "ได้"),
        ("ลูกมี", "มี"),
    ):
        text = text.replace(old, new)
    # catch-all: ตัด "ลูก" ที่หลุดมาเดี่ยวๆ (ไม่ใช่ "ลูกค้า")
    text = re.sub(r'(?<!ค้า)ลูก(?!ค้า)', '', text)
    return text
