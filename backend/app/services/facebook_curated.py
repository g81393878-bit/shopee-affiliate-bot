# -*- coding: utf-8 -*-
"""คอนเทนต์โลก (RSS curated) — ดึงข่าว/เทรนด์จาก RSS feed แล้วเขียนเป็นเสียงป้าเข็มด้วย Groq.

เหตุผล: เพจไม่ควรมีแต่โพสต์ขายของ — ข่าว/เทรนด์ในหมวดที่ลูกค้าสนใจ (เทค/ไลฟ์สไตล์)
ทำให้เพจน่าติดตาม; ทุกโพสต์จบด้วยลิงก์ LINE OA (ชวนเพิ่มเพื่อนป้าเข็ม)

ตั้งค่า:
  - RSS_SOURCES_JSON (env, JSON array) — override รายชื่อ feed ได้ (ไม่ตั้ง = ใช้ default)
  - ใช้ Groq เขียนเสียงป้าเข็ม (ถูก เร็ว ไม่เผาโควตา Claude); Groq ล้ม → fallback ข้อความตรง

กันซ้ำ: CampaignLog status='fbrss', category = sha1(guid|link) — ไม่โพสต์ข่าวเดิมซ้ำ
"""
import hashlib
import html
import json
import logging
import os
import xml.etree.ElementTree as ET

import httpx

from app.config import settings
from app.services.persona import persona_system_prompt

logger = logging.getLogger(__name__)

_LINE_PLACEHOLDER = "https://lin.ee/o9Kjp1N"

# feed ไทยยอดนิยม (ตรวจแล้วใช้ได้ 2026-08) — หมวดเทค/ไลฟ์สไตล์ เหมาะกับลูกค้าช้อปปี้
_DEFAULT_SOURCES = [
    {"name": "Beartai", "url": "https://www.beartai.com/feed", "topic": "เทค/ไลฟ์สไตล์"},
    {"name": "Techhub", "url": "https://www.techhub.in.th/feed/", "topic": "เทค"},
    {"name": "The Standard", "url": "https://thestandard.co/feed", "topic": "ข่าว/ไลฟ์สไตล์"},
]


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
                          headers={"User-Agent": "Mozilla/5.0"})
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
    """Groq เขียนโพสต์เสียงป้าเข็ม 2-3 ประโยคจากข่าว (คืนข้อความล้วน ไม่ใช่ JSON)"""
    from app.services.llm_clients import groq_clients
    clients = groq_clients()
    if not clients:
        raise RuntimeError("ไม่มี Groq key")
    prompt = (
        "เขียนโพสต์ Facebook ภาษาไทยสั้น ๆ (2-3 ประโยค) ในเสียง \"ป้าเข็ม\" แม่ค้าออนไลน์ "
        "ใจดี ที่จะมาเล่าข่าวนี้ให้ลูกหลานฟัง พร้อมคอมเมนต์ส่วนตัวที่โยงกับการช้อปปิ้ง/"
        "ความคุ้มค่า (สโลแกน \"ถ้าไม่คุ้ม ป้าบอกให้\") ใช้ emoji ได้เล็กน้อย\n\n"
        f"หัวข้อข่าว: {item['title']}\n"
        f"รายละเอียด: {(item.get('summary') or '')[:500]}\n\n"
        "ตอบเฉพาะข้อความโพสต์เท่านั้น ไม่มีคำอธิบายอื่น"
    )
    last_err = None
    for client in clients:
        try:
            resp = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system",
                     "content": persona_system_prompt("เขียนโพสต์ Facebook ภาษาไทยสั้น ๆ")},
                    {"role": "user", "content": prompt},
                ],
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
        caption = f"ป้าเห็นข่าวนี้แล้วต้องเอามาฝากลูกหลาน 😊 {item['title']}"
    parts = [caption]
    if line_oa:
        parts.append(f"👉 แอดไลน์ป้า ถามป้าก่อนซื้อ: {line_oa}")
    parts.append("#ป้าเข็ม #ถ้าไม่คุ้มป้าบอกให้")
    return "\n\n".join(parts)
