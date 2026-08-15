---
name: web-search
description: >-
  Web search service (backend/app/services/web_search.py): Tavily + Firecrawl multi-key
  round-robin, circuit breaker, LRU cache, and LINE reply formatting. Use when the user
  mentions ค้นเน็ต, Tavily, Firecrawl, circuit breaker, web_search, หาข้อมูลในอินเทอร์เน็ต,
  or LINE web search answers.
---

# Web Search (Tavily + Firecrawl)

## โครงสร้าง
- `web_search(query)` → `{answer, results, images}` — เรียก Tavily + Firecrawl **ขนานกัน** (thread)
  แล้วรวมผล (ตัดซ้ำตาม URL); Tavily ล้ม → Groq สรุปจากผล Firecrawl; ล้มทั้งคู่ → throw
- `web_search_answer()` / `web_search_reply()` — ไม่ throw (คืนข้อความขอโทษ)
- `firecrawl_scrape(url)` — เปิดหน้าเว็บ render JS (ใช้กับราคา Shopee, ต้อง `formats=["rawHtml"]`
  ไม่ตัด `<script>` เพราะราคาฝังใน script); `firecrawl_search_results()` — ผลดิบ (ใช้ facebook_local)
- **หลาย key หมุนเวียน + failover** เหมือน Groq (TAVILY_API_KEY / FIRECRAWL_API_KEY คั่นคอมม่า)

## Resilience (เจอจริง กันเผา quota)
- **Circuit breaker**: provider ล้มติดกัน ≥ `WEB_SEARCH_CB_THRESHOLD` (3) → เปิดวงจรข้าม provider
  ช่วง `WEB_SEARCH_CB_COOLDOWN` (90s) แล้ว half-open ลองใหม่
- **LRU cache**: `WEB_SEARCH_CACHE_TTL` (600s) + `WEB_SEARCH_CACHE_MAX` (200) — คำถามซ้ำตอบทันที
- `web_search_stats()` เอาไปโชว์ /health

## กับดัก
1. **Tavily ต้องบังคับภาษาไทย**: query เติม "ตอบเป็นภาษาไทยสั้นๆ: " นำหน้า (ไม่งั้นตอบอังกฤษ)
2. **รูปที่ส่ง LINE ต้อง https + มีนามสกุล** (.jpg/.png/.webp/.gif) — กัน URL ที่ LINE ดึงเป็นรูปไม่ได้
   แล้ว reply ทั้งชุดพัง (เช่น TikTok api/img?itemId=...) — `_clean_image_urls` จำกัด 3 รูป
3. reply format จำกัด 1800 ตัวอักษร (LINE limit)
4. ใช้ `urllib` ตรง (ไม่มี dep เพิ่ม) — **ห้าม**เอา requests มาแทนโดยไม่จำเป็น

## ไฟล์
`backend/app/services/web_search.py`; ใช้ใน `line_bot.py` (`web_search_answer`), `price_refresh.py`,
`product_image.py`, `facebook_local.py`

## เทสต์
`backend/tests/test_line_bot.py` (mock web_search_answer ใน conftest); `test_price_refresh.py`,
`test_product_image.py` (mock firecrawl)
