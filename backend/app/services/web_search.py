# -*- coding: utf-8 -*-
"""
Web search — ค้นข้อมูลทั่วไป/ความรู้ในเน็ต แล้วสรุปตอบลูกค้า

ใช้ REST API ตรง (urllib) — ไม่ต้องติดตั้ง dependency เพิ่ม
- ตัวหลัก : TAVILY_API_KEY   (สมัครฟรีที่ tavily.com — ฟรี 1,000 ครั้ง/เดือน ไม่ผูกบัตร)
- ตัวสำรอง: FIRECRAWL_API_KEY (สมัครฟรีที่ firecrawl.dev) — ถ้า Tavily ล้ม/หมด quota จะสลับมาใช้เอง

ผลลัพธ์ถูก normalize เป็นโครงสร้างเดียวกันเสมอ:
  {answer: str, results: [{title, url, content}, ...]}
"""
import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2/search"


def _post_json(url: str, body: dict, headers: dict, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _tavily_search(query: str, max_results: int, search_depth: str) -> dict:
    key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ยังไม่ได้ตั้ง TAVILY_API_KEY")
    body = {
        "api_key": key,
        # คำนำหน้าบังคับให้ Tavily สรุปตอบเป็นภาษาไทย (ไม่ตอบภาษาอังกฤษ)
        "query": "ตอบเป็นภาษาไทยสั้นๆ: " + query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": True,
    }
    try:
        return _post_json(TAVILY_API_URL, body, {"Content-Type": "application/json"})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tavily HTTP {e.code}: {detail[:200]}") from e


def _firecrawl_search(query: str, max_results: int) -> dict:
    """ค้นผ่าน Firecrawl แล้ว normalize เป็นโครงสร้างเดียวกับ Tavily."""
    key = (os.getenv("FIRECRAWL_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ยังไม่ได้ตั้ง FIRECRAWL_API_KEY")
    body = {
        "query": query,
        "limit": max_results,
        "sources": ["web"],
    }
    headers = {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
    }
    try:
        data = _post_json(FIRECRAWL_API_URL, body, headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firecrawl HTTP {e.code}: {detail[:200]}") from e
    if not data.get("success"):
        raise RuntimeError(f"Firecrawl: {data.get('error') or 'unknown error'}")
    web = ((data.get("data") or {}).get("web") or [])[:max_results]
    results = []
    for r in web:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = (r.get("description") or "").strip()
        if not content:
            content = (r.get("markdown") or "").strip().replace("\n", " ")
        results.append({"title": title, "url": url, "content": content[:300]})
    # Firecrawl ไม่มี answer สำเร็จรูป — reply format จะใช้ title+content แทน
    return {"answer": "", "results": results}


def web_search(query: str, max_results: int = 3, search_depth: str = "basic") -> dict:
    """ค้นเน็ต → {answer, results:[{title, url, content}, ...]}

    ลำดับ: Tavily ก่อน → ถ้าล้ม (ไม่มี key / หมด quota / HTTP error) สลับ Firecrawl อัตโนมัติ
    ถ้าทั้งคู่ล้มจะ throw ให้ผู้เรียกตัดสินใจ (web_search_reply แปลงเป็นข้อความขอโทษ)"""
    try:
        return _tavily_search(query, max_results, search_depth)
    except Exception as e:
        logger.warning(f"Tavily failed ({e}) — falling back to Firecrawl")
        return _firecrawl_search(query, max_results)


def web_search_reply(query: str, max_results: int = 3) -> str:
    """ค้น + สรุปเป็นข้อความตอบลูกค้า (เนื้อหาจริง + แหล่งอ้างอิง) — ไม่ throw"""
    query = (query or "").strip()
    if not query:
        return "🙏 บอกสิ่งที่อยากให้หาหน่อยนะคะ เช่น \"ค้นเน็ต สภาพอากาศกรุงเทพวันนี้\""
    try:
        data = web_search(query, max_results)
    except Exception as e:
        logger.error(f"web_search failed: {e}")
        return "🙏 ขออภัยจ๊ะ ค้นข้อมูลเน็ตไม่สำเร็จตอนนี้ — ลองใหม่ หรือพิมพ์ใหม่สั้นๆ หน่อยนะคะ"
    answer = (data.get("answer") or "").strip()
    results = data.get("results", [])[:max_results]
    lines = ["🔍 ป้าเข็มหาข้อมูลมาให้แล้วจ๊ะ:"]
    if answer:
        lines.append(answer)
    for r in results:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = (r.get("content") or "").strip().replace("\n", " ")
        if title and content:
            lines.append(f"\n• {title}\n  {content[:180]}")
        elif title:
            lines.append(f"\n• {title}")
        if url:
            lines.append(f"  (ที่มา: {url})")
    if len(lines) == 1:
        return "🙏 ขออภัยจ๊ะ หาข้อมูลไม่เจอ — ลองเปลี่ยนคำถาม/พิมพ์ใหม่หน่อยนะคะ"
    text = "\n".join(lines)
    if len(text) > 1800:
        text = text[:1800] + "…"
    return text
