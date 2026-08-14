# -*- coding: utf-8 -*-
"""
Web search — ค้นข้อมูลทั่วไป/ความรู้ในเน็ต แล้วสรุปตอบลูกค้า

ใช้ REST API ตรง (urllib) — ไม่ต้องติดตั้ง dependency เพิ่ม
- TAVILY_API_KEY    (สมัครฟรีที่ tavily.com — ฟรี 1,000 ครั้ง/เดือน ไม่ผูกบัตร)
- FIRECRAWL_API_KEY (สมัครฟรีที่ firecrawl.dev)
ทั้ง 2 ตัวรองรับหลาย key คั่นคอมม่า (key_aaa,key_bbb,...) หมุนเวียน + failover เหมือน GROQ_API_KEY

ทำงานร่วมกัน (collaborate) — เรียกทั้ง 2 provider ขนานกันแล้วรวมผล:
  - answer  = สรุป AI จาก Tavily (ถ้ามี) ไม่งั้น Groq สรุปจากผล Firecrawl
  - results = รวมทั้งคู่ ตัดซ้ำตาม URL (ได้แหล่งอ้างอิงหลากหลายกว่า)
  - images  = รวมรูปทั้งคู่
  - ตัวไหนล้มไม่พัง — อีกตัวยังให้คำตอบครบ

ผลลัพธ์ normalize เป็นโครงสร้างเดียวกันเสมอ:
  {answer: str, results: [{title, url, content}, ...], images: [url, ...]}
"""
import concurrent.futures
import json
import logging
import os
import threading
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2/search"

# จำกัดเฉพาะ URL ที่มีนามสกุลรูปชัดเจน (https + .jpg/.png/...) — กันส่ง URL ที่
# LINE ดึงไม่เป็นรูปแล้ว reply ทั้งชุดพัง (เช่น TikTok api/img?itemId=... ไม่มีนามสกุล)
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# Firecrawl หลาย key หมุนเวียน + failover (pattern เดียวกับ llm_clients.groq_clients)
_fc_lock = threading.Lock()
_fc_start_index = 0


def firecrawl_keys() -> list:
    """รายการ Firecrawl keys จาก FIRECRAWL_API_KEY (รองรับหลายตัวคั่นด้วย ,) — ตัด mock/ซ้ำ"""
    raw = (os.getenv("FIRECRAWL_API_KEY") or "").strip()
    seen, keys = set(), []
    for k in raw.split(","):
        k = k.strip()
        if k and "mock" not in k.lower() and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def _rotate_firecrawl_keys() -> list:
    """Firecrawl keys เรียงแบบหมุนเวียน (call ถัดไปเริ่มที่ key ถัดไป — กระจายโหลด)"""
    keys = firecrawl_keys()
    if not keys:
        return []
    global _fc_start_index
    with _fc_lock:
        rot = _fc_start_index % len(keys)
        _fc_start_index += 1
    return keys[rot:] + keys[:rot]


# Tavily หลาย key หมุนเวียน + failover (pattern เดียวกับ Firecrawl/Groq)
_tv_lock = threading.Lock()
_tv_start_index = 0


def tavily_keys() -> list:
    """รายการ Tavily keys จาก TAVILY_API_KEY (รองรับหลายตัวคั่นด้วย ,) — ตัด mock/ซ้ำ"""
    raw = (os.getenv("TAVILY_API_KEY") or "").strip()
    seen, keys = set(), []
    for k in raw.split(","):
        k = k.strip()
        if k and "mock" not in k.lower() and k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def _rotate_tavily_keys() -> list:
    """Tavily keys เรียงแบบหมุนเวียน (call ถัดไปเริ่มที่ key ถัดไป — กระจายโหลด)"""
    keys = tavily_keys()
    if not keys:
        return []
    global _tv_start_index
    with _tv_lock:
        rot = _tv_start_index % len(keys)
        _tv_start_index += 1
    return keys[rot:] + keys[:rot]


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
    """ค้น Tavily (หลาย key หมุนเวียน+failover) — คืน dict ดิบ {answer, results, images, ...}"""
    keys = _rotate_tavily_keys()
    if not keys:
        raise RuntimeError("ยังไม่ได้ตั้ง TAVILY_API_KEY")
    body = {
        # คำนำหน้าบังคับให้ Tavily สรุปตอบเป็นภาษาไทย (ไม่ตอบภาษาอังกฤษ)
        "query": "ตอบเป็นภาษาไทยสั้นๆ: " + query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": True,
        "include_images": True,
    }
    data, last_err = None, None
    for key in keys:
        body["api_key"] = key
        try:
            data = _post_json(TAVILY_API_URL, body, {"Content-Type": "application/json"})
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"Tavily HTTP {e.code}: {detail[:200]}")
            logger.warning(f"Tavily key {key[:10]}... failed ({last_err}) — ลอง key ถัดไป")
        except Exception as e:
            last_err = e
            logger.warning(f"Tavily key {key[:10]}... failed ({e}) — ลอง key ถัดไป")
    if data is None:
        raise last_err if last_err else RuntimeError("Tavily: unknown error")
    return data


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


def _firecrawl_fetch(query: str, max_results: int) -> dict:
    """ค้น Firecrawl (หลาย key หมุนเวียน+failover) → {results, images} — ยังไม่สรุป Groq."""
    keys = _rotate_firecrawl_keys()
    if not keys:
        raise RuntimeError("ยังไม่ได้ตั้ง FIRECRAWL_API_KEY")
    body = {
        "query": query,
        "limit": max_results,
        "sources": ["web"],
    }
    data, last_err = None, None
    for key in keys:
        headers = {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        }
        try:
            data = _post_json(FIRECRAWL_API_URL, body, headers)
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"Firecrawl HTTP {e.code}: {detail[:200]}")
            logger.warning(f"Firecrawl key {key[:8]}... failed ({last_err}) — ลอง key ถัดไป")
        except Exception as e:
            last_err = e
            logger.warning(f"Firecrawl key {key[:8]}... failed ({e}) — ลอง key ถัดไป")
    if data is None:
        raise last_err if last_err else RuntimeError("Firecrawl: unknown error")
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
    return {"results": results, "images": images}


def _firecrawl_search(query: str, max_results: int) -> dict:
    """Firecrawl เต็มรูปแบบ (ใช้เดี่ยวๆ ตอน Tavily ล้ม) → {answer, results, images}."""
    d = _firecrawl_fetch(query, max_results)
    answer = _summarize_with_groq(query, d["results"])
    return {"answer": answer, "results": d["results"], "images": d["images"]}


def _merge_results(tavily_results, fc_results, max_results: int) -> list:
    """รวมผลทั้ง 2 provider — ตัดซ้ำตาม URL (title สำรอง) จำกัดไม่เกิน 2×max_results"""
    combined = list(tavily_results or []) + list(fc_results or [])
    out, seen = [], set()
    for r in combined:
        url = (r.get("url") or "").strip()
        key = url or (r.get("title") or "").strip()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(r)
        if len(out) >= max_results * 2:
            break
    return out


def _merge_images(tavily_images, fc_images) -> list:
    """รวมรูปทั้งคู่ — _clean_image_urls ตัดซ้ำ + กรองนามสกุล + จำกัด 3 รูปให้เอง"""
    combined = list(tavily_images or []) + list(fc_images or [])
    return _clean_image_urls(combined)


def web_search(query: str, max_results: int = 3, search_depth: str = "basic") -> dict:
    """Tavily + Firecrawl ทำงานร่วมกัน → {answer, results, images}

    เรียกทั้ง 2 provider ขนานกัน (thread) แล้วรวมผล:
      - answer  = Tavily (สรุป AI); ถ้า Tavily ล้ม → Groq สรุปจากผล Firecrawl
      - results = รวมทั้งคู่ ตัดซ้ำตาม URL
      - images  = รวมทั้งคู่
    ตัวไหนล้มไม่พัง — อีกตัวยังให้คำตอบครบ; ถ้าล้มทั้งคู่ throw ให้ผู้เรียกตัดสินใจ"""
    tavily_data = firecrawl_data = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_t = ex.submit(_tavily_search, query, max_results, search_depth)
        f_f = ex.submit(_firecrawl_fetch, query, max_results)
        try:
            tavily_data = f_t.result()
        except Exception as e:
            logger.warning(f"Tavily failed ({e})")
        try:
            firecrawl_data = f_f.result()
        except Exception as e:
            logger.warning(f"Firecrawl failed ({e})")
    if tavily_data is None and firecrawl_data is None:
        raise RuntimeError("ทั้ง Tavily และ Firecrawl ล้ม")

    tavily_answer = ((tavily_data or {}).get("answer") or "").strip()
    if tavily_answer:
        answer = tavily_answer
    elif firecrawl_data is not None:
        answer = _summarize_with_groq(query, firecrawl_data.get("results") or [])
    else:
        answer = ""

    return {
        "answer": answer,
        "results": _merge_results(
            (tavily_data or {}).get("results"),
            (firecrawl_data or {}).get("results"),
            max_results,
        ),
        "images": _merge_images(
            (tavily_data or {}).get("images"),
            (firecrawl_data or {}).get("images"),
        ),
    }


def _format_reply(data: dict, max_results: int) -> str:
    """แปลง {answer, results} เป็นข้อความตอบลูกค้า (เนื้อหาจริง + แหล่งอ้างอิง)"""
    answer = (data.get("answer") or "").strip()
    # ผลรวม (ทั้ง 2 provider) แสดงได้ถึง 2×max_results — ตัว answer เป็นหัวข้อหลัก
    results = data.get("results", [])[: max_results * 2]
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
