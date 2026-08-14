# -*- coding: utf-8 -*-
"""
Web search — ค้นข้อมูลทั่วไป/ความรู้ในเน็ต แล้วสรุปตอบลูกค้า

ใช้ REST API ตรง (urllib) — ไม่ต้องติดตั้ง dependency เพิ่ม
- ตัวหลัก : TAVILY_API_KEY   (สมัครฟรีที่ tavily.com — ฟรี 1,000 ครั้ง/เดือน ไม่ผูกบัตร)
- ตัวสำรอง: FIRECRAWL_API_KEY (สมัครฟรีที่ firecrawl.dev) — ถ้า Tavily ล้ม/หมด quota จะสลับมาใช้เอง

ผลลัพธ์ถูก normalize เป็นโครงสร้างเดียวกันเสมอ:
  {answer: str, results: [{title, url, content}, ...], images: [url, ...]}

- Tavily คืน answer (สรุปไทย) มาให้เอง
- Firecrawl ไม่มี answer → สรุปด้วย Groq แทน (LLM ที่บอทใช้อยู่แล้ว) ให้ตอบได้เทียบเท่า
- images = รูปประกอบคำตอบ (Tavily include_images / Firecrawl data.images) — ถ้าไม่มีเป็น []
"""
import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2/search"

# จำกัดเฉพาะ URL ที่มีนามสกุลรูปชัดเจน (https + .jpg/.png/...) — กันส่ง URL ที่
# LINE ดึงไม่เป็นรูปแล้ว reply ทั้งชุดพัง (เช่น TikTok api/img?itemId=... ไม่มีนามสกุล)
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _post_json(url: str, body: dict, headers: dict, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clean_image_urls(images) -> list:
    """กรองรูปที่ส่งให้ LINE ได้จริง: https + มีนามสกุลรูป — ตัดซ้ำ จำกัด 3 รูป.

    รองรับทั้ง list ของ string (Tavily) และ list ของ dict {url/imageUrl} (Firecrawl)"""
    out, seen = [], set()
    for it in (images or []):
        if isinstance(it, dict):
            u = (it.get("url") or it.get("imageUrl") or "").strip()
        else:
            u = (it or "").strip()
        if not u.startswith("https://") or u in seen:
            continue
        base = u.lower().split("?")[0]
        if base.endswith(_IMAGE_EXT):
            seen.add(u)
            out.append(u)
    return out[:3]


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
        "include_images": True,
    }
    try:
        return _post_json(TAVILY_API_URL, body, {"Content-Type": "application/json"})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tavily HTTP {e.code}: {detail[:200]}") from e


def _summarize_with_groq(query: str, results: list) -> str:
    """สรุปผลค้น Firecrawl เป็นคำตอบไทย 2-4 ประโยค (Firecrawl ไม่มี answer สำเร็จรูป).

    ใช้ Groq (LLM ตัวเดียวกับบอท) — ถ้า key หมด/ล้มทุกตัว จะคืน "" (reply format
    ตกไปใช้ title+content แทน ไม่พัง)"""
    snippets = []
    for r in results[:3]:
        t = (r.get("title") or "").strip()
        c = (r.get("content") or "").strip()
        if t or c:
            snippets.append(f"- {t}\n  {c[:300]}")
    if not snippets:
        return ""
    try:
        from app.config import settings
        from app.services.llm_clients import groq_clients
        clients = groq_clients()
        if not clients:
            return ""
        prompt = (
            "ตอบคำถามผู้ใช้เป็นภาษาไทย สั้น 2-4 ประโยค เป็นกันเองแบบแม่ค้าออนไลน์ "
            "(เรียกตัวเองว่า \"ป้า\") ตรงประเด็น จากข้อมูลอ้างอิงด้านล่าง "
            "ถ้าข้อมูลไม่พอให้ตอบตามความรู้ทั่วไป ห้ามมโนเกินข้อมูล\n\n"
            f"คำถาม: {query}\n\nข้อมูลอ้างอิง:\n" + "\n".join(snippets)
        )
        for client in clients:
            try:
                resp = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[
                        {"role": "system",
                         "content": "คุณคือป้าเข็ม แม่ค้าออนไลน์ผู้ช่วยช้อปปิ้ง ตอบสั้น ตรงประเด็น เป็นภาษาไทย"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )
                ans = (resp.choices[0].message.content or "").strip()
                if ans:
                    return ans
            except Exception as e:
                logger.warning(f"Groq summarize failed (key {client.api_key[:8]}...): {e}")
        return ""
    except Exception as e:
        logger.warning(f"Groq summarize unavailable: {e}")
        return ""


def _firecrawl_search(query: str, max_results: int) -> dict:
    """ค้นผ่าน Firecrawl + สรุปด้วย Groq → normalize เป็นโครงสร้างเดียวกับ Tavily."""
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
    d = data.get("data") or {}
    web = (d.get("web") or [])[:max_results]
    results = []
    for r in web:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = (r.get("description") or "").strip()
        if not content:
            content = (r.get("markdown") or "").strip().replace("\n", " ")
        results.append({"title": title, "url": url, "content": content[:300]})
    images = _clean_image_urls(d.get("images") or [])
    answer = _summarize_with_groq(query, results)
    return {"answer": answer, "results": results, "images": images}


def web_search(query: str, max_results: int = 3, search_depth: str = "basic") -> dict:
    """ค้นเน็ต → {answer, results:[{title, url, content}, ...], images:[url, ...]}

    ลำดับ: Tavily ก่อน → ถ้าล้ม (ไม่มี key / หมด quota / HTTP error) สลับ Firecrawl อัตโนมัติ
    ถ้าทั้งคู่ล้มจะ throw ให้ผู้เรียกตัดสินใจ (web_search_reply แปลงเป็นข้อความขอโทษ)"""
    try:
        data = _tavily_search(query, max_results, search_depth)
        return {
            "answer": (data.get("answer") or "").strip(),
            "results": data.get("results", [])[:max_results],
            "images": _clean_image_urls(data.get("images") or []),
        }
    except Exception as e:
        logger.warning(f"Tavily failed ({e}) — falling back to Firecrawl")
        return _firecrawl_search(query, max_results)


def _format_reply(data: dict, max_results: int) -> str:
    """แปลง {answer, results} เป็นข้อความตอบลูกค้า (เนื้อหาจริง + แหล่งอ้างอิง)"""
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


def web_search_answer(query: str, max_results: int = 3) -> dict:
    """ค้น + สรุป → {text: str, images: [url]} — ไม่ throw (ล้มคืนข้อความขอโทษ)"""
    query = (query or "").strip()
    if not query:
        return {"text": "🙏 บอกสิ่งที่อยากให้หาหน่อยนะคะ เช่น \"ค้นเน็ต สภาพอากาศกรุงเทพวันนี้\"",
                "images": []}
    try:
        data = web_search(query, max_results)
    except Exception as e:
        logger.error(f"web_search failed: {e}")
        return {"text": "🙏 ขออภัยจ๊ะ ค้นข้อมูลเน็ตไม่สำเร็จตอนนี้ — ลองใหม่ หรือพิมพ์ใหม่สั้นๆ หน่อยนะคะ",
                "images": []}
    return {"text": _format_reply(data, max_results), "images": data.get("images") or []}


def web_search_reply(query: str, max_results: int = 3) -> str:
    """ค้น + สรุปเป็นข้อความ (เข้ากันได้กับโค้ดเดิม) — ไม่ throw"""
    return web_search_answer(query, max_results)["text"]
