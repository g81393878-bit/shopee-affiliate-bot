# -*- coding: utf-8 -*-
"""
Web search (Tavily) — ค้นข้อมูลทั่วไป/ความรู้ในเน็ต แล้วสรุปตอบลูกค้า

ใช้ REST API ตรง (urllib) — ไม่ต้องติดตั้ง tavily-python เพิ่ม dependency
env: TAVILY_API_KEY (สมัครฟรีที่ tavily.com — ฟรี 1,000 ครั้ง/เดือน ไม่ผูกบัตร)
"""
import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

API_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 3, search_depth: str = "basic") -> dict:
    """ค้นเน็ตผ่าน Tavily → {answer, results:[{title, url, content}, ...]}"""
    key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ยังไม่ได้ตั้ง TAVILY_API_KEY")
    body = json.dumps({
        "api_key": key,
        # คำนำหน้าบังคับให้ Tavily สรุปตอบเป็นภาษาไทย (ไม่ตอบภาษาอังกฤษ)
        "query": "ตอบเป็นภาษาไทยสั้นๆ: " + query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": True,
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tavily HTTP {e.code}: {detail[:200]}") from e


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
