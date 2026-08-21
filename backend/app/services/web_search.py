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
from collections import OrderedDict
import concurrent.futures
import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"

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


# --- Resilience: circuit breaker + cache + metrics (ต่อ provider) ---
# กันไม่ให้บอทเผา quota ทั้งหมดไปกับ provider ที่พัง: ล้มติดกันเกิน threshold →
# เปิดวงจร (ข้าม provider) ช่วง cooldown แล้วค่อย half-open ลองใหม่
CIRCUIT_FAIL_THRESHOLD = int(os.getenv("WEB_SEARCH_CB_THRESHOLD", "3"))
CIRCUIT_COOLDOWN = float(os.getenv("WEB_SEARCH_CB_COOLDOWN", "90"))
CACHE_TTL = float(os.getenv("WEB_SEARCH_CACHE_TTL", "600"))   # วินาที (default 10 นาที)
CACHE_MAX = int(os.getenv("WEB_SEARCH_CACHE_MAX", "200"))      # จำนวน query ที่จำ

_stats_lock = threading.Lock()
_STATS = {
    "tavily": {"success": 0, "failure": 0, "circuit_open": False,
               "fail_streak": 0, "opened_at": 0.0, "last_error": ""},
    "firecrawl": {"success": 0, "failure": 0, "circuit_open": False,
                  "fail_streak": 0, "opened_at": 0.0, "last_error": ""},
    "cache": {"hits": 0, "misses": 0},
}

_cache_lock = threading.Lock()
_cache: "OrderedDict[str, tuple]" = OrderedDict()  # key -> (expiry_ts, result)


def _provider_allowed(name: str) -> bool:
    """Circuit breaker: วงจรเปิด (ล้มติดกันเกิน threshold) → ข้าม provider ช่วง cooldown.

    หลัง cooldown หมดให้ half-open — อนุญาตลอง 1 ครั้ง ถ้าสำเร็จวงจรปิดกลับ"""
    with _stats_lock:
        st = _STATS[name]
        if not st["circuit_open"]:
            return True
        if time.time() - st["opened_at"] >= CIRCUIT_COOLDOWN:
            st["circuit_open"] = False
            st["fail_streak"] = 0
            return True
        return False


def _provider_success(name: str) -> None:
    with _stats_lock:
        st = _STATS[name]
        st["success"] += 1
        st["fail_streak"] = 0
        st["circuit_open"] = False


def _provider_failure(name: str, err: str) -> None:
    with _stats_lock:
        st = _STATS[name]
        st["failure"] += 1
        st["fail_streak"] += 1
        st["last_error"] = (err or "")[:200]
        if st["fail_streak"] >= CIRCUIT_FAIL_THRESHOLD and not st["circuit_open"]:
            st["circuit_open"] = True
            st["opened_at"] = time.time()
            logger.warning(
                f"⛔ circuit breaker เปิดสำหรับ {name} — ล้มติดกัน {st['fail_streak']} ครั้ง, พัก {CIRCUIT_COOLDOWN:.0f}s"
            )


def web_search_stats() -> dict:
    """สถิติระบบค้นเน็ต (snapshot) — ใช้โชว์ใน /health หรือ admin dashboard"""
    with _stats_lock:
        return {name: dict(v) for name, v in _STATS.items()}


def _cache_key(query: str, max_results: int, search_depth: str) -> str:
    return f"{search_depth}|{max_results}|{(query or '').strip().lower()}"


def _cache_get(key: str):
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            return None
        exp, val = item
        if time.time() >= exp:
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)  # LRU: เลื่อน key ที่ใช้ล่าสุดไปท้าย
        return val


def _cache_put(key: str, val: dict) -> None:
    with _cache_lock:
        _cache[key] = (time.time() + CACHE_TTL, val)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)  # ไล่ของเก่าสุดออก (LRU)


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
    if not _provider_allowed("tavily"):
        raise RuntimeError("tavily circuit open (paused)")
    keys = _rotate_tavily_keys()
    if not keys:
        _provider_failure("tavily", "ยังไม่ได้ตั้ง TAVILY_API_KEY")
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
        _provider_failure("tavily", str(last_err))
        raise last_err if last_err else RuntimeError("Tavily: unknown error")
    _provider_success("tavily")
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
        from app.services.llm_clients import call_with_backoff, groq_clients
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
                resp = call_with_backoff(
                    lambda: client.chat.completions.create(
                        model=settings.GROQ_MODEL,
                        messages=[
                            {"role": "system",
                             "content": "คุณคือป้าเข็ม แม่ค้าออนไลน์ผู้ช่วยช้อปปิ้ง ตอบสั้น ตรงประเด็น เป็นภาษาไทย"},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,
                    ),
                    circuit_key=client.api_key,
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
    if not _provider_allowed("firecrawl"):
        raise RuntimeError("firecrawl circuit open (paused)")
    keys = _rotate_firecrawl_keys()
    if not keys:
        _provider_failure("firecrawl", "ยังไม่ได้ตั้ง FIRECRAWL_API_KEY")
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
        _provider_failure("firecrawl", str(last_err))
        raise last_err if last_err else RuntimeError("Firecrawl: unknown error")
    if not data.get("success"):
        _provider_failure("firecrawl", f"Firecrawl: {data.get('error') or 'unknown error'}")
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
    _provider_success("firecrawl")
    return {"results": results, "images": images}


def _firecrawl_search(query: str, max_results: int) -> dict:
    """Firecrawl เต็มรูปแบบ (ใช้เดี่ยวๆ ตอน Tavily ล้ม) → {answer, results, images}."""
    d = _firecrawl_fetch(query, max_results)
    answer = _summarize_with_groq(query, d["results"])
    return {"answer": answer, "results": d["results"], "images": d["images"]}


def firecrawl_search_results(query: str, max_results: int = 5) -> list:
    """ค้น Firecrawl อย่างเดียว → list ของ {title, url, content} (ผลดิบ ไม่สรุป).

    ใช้กับคลังโพสต์ท้องถิ่น (facebook_local) — อยากได้ลิงก์+ข้อความจริงไปให้ Groq
    เขียนโพสต์ต่อ ไม่ใช้ answer ที่สรุปแล้ว; ล้ม (ไม่มี key/วงจรเปิด/provider พัง)
    → คืน [] ให้ผู้เรียก fallback เอง (best-effort ไม่ throw)"""
    try:
        return (_firecrawl_fetch(query, max_results).get("results") or [])
    except Exception as e:
        logger.warning(f"firecrawl_search_results failed: {e}")
        return []


def firecrawl_scrape(url: str, timeout: int = 30) -> str:
    """เปิดหน้าเว็บ 1 URL ผ่าน Firecrawl (render JS กัน anti-bot) → คืน HTML ทั้งหน้า

    - ใช้กับหน้า Shopee product เพื่ออ่านราคา (ราคาฝังใน <script>) — ต้องไม่ตัด script
    - หลาย key หมุนเวียน + failover เหมือน firecrawl_keys(); ล้มทุก key/ไม่มี key →
      คืน "" ให้ผู้เรียก fallback เอง (best-effort ไม่ throw)"""
    if not _provider_allowed("firecrawl"):
        return ""
    keys = _rotate_firecrawl_keys()
    if not keys:
        _provider_failure("firecrawl", "ยังไม่ได้ตั้ง FIRECRAWL_API_KEY")
        return ""
    body = {
        "url": url,
        "formats": ["rawHtml"],      # HTML ดิบไม่ตัด <script> (ราคา Shopee ฝังใน script)
        "onlyMainContent": False,
        "waitFor": 0,
    }
    for key in keys:
        try:
            data = _post_json(FIRECRAWL_SCRAPE_URL, body,
                              {"Authorization": "Bearer " + key,
                               "Content-Type": "application/json"},
                              timeout=timeout)
        except Exception as e:
            logger.warning(f"Firecrawl scrape key {key[:8]}... failed ({e}) — ลอง key ถัดไป")
            continue
        if not data.get("success"):
            logger.warning(f"Firecrawl scrape: {data.get('error') or 'unknown error'}")
            continue
        d = data.get("data") or {}
        html = d.get("rawHtml") or d.get("html") or d.get("markdown") or ""
        if html:
            _provider_success("firecrawl")
            return html
    _provider_failure("firecrawl", "firecrawl scrape ล้มทุก key")
    return ""


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
    ตัวไหนล้มไม่พัง — อีกตัวยังให้คำตอบครบ; ถ้าล้มทั้งคู่ throw ให้ผู้เรียกตัดสินใจ
    ผลลัพธ์ถูก cache (LRU + TTL) — คำถามซ้ำในช่วง TTL ตอบทันที ไม่เรียก API ซ้ำ"""
    ckey = _cache_key(query, max_results, search_depth)
    cached = _cache_get(ckey)
    if cached is not None:
        with _stats_lock:
            _STATS["cache"]["hits"] += 1
        return cached
    with _stats_lock:
        _STATS["cache"]["misses"] += 1

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

    result = {
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
    _cache_put(ckey, result)
    return result


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
