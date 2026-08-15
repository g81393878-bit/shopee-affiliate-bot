---
name: llm-providers
description: >-
  Multi-provider LLM clients (backend/app/services/llm_clients.py): Groq/Anthropic
  multi-key round-robin + failover, OpenAI-compat quirks, and mock-key handling.
  Use whenever the user mentions Groq 429, Anthropic/Claude, หลาย API key, key หมด,
  LLM provider, or model switching.
---

# LLM Providers (multi-key failover)

## หลักการ
- `groq_clients()` / `anthropic_clients()` หมุนเวียน key (เรียงสลับทุก call) + ตัด key
  ที่มีคำว่า "mock" ออก — key หลายตัวคั่นคอมม่าใน `GROQ_API_KEY` / `ANTHROPIC_API_KEY`
- ผู้เรียกวนทุก client: ตัวไหนล้ม (401/429/error) → ข้ามไปตัวถัดไป; ล้มทุกตัว → fallback
- `LLM_PROVIDER` = `gemini` | `openai` | `groq` | `anthropic`; `GROQ_MODEL` / `ANTHROPIC_MODEL` override ได้

## กับดัก (เจอจริง)
1. **Groq ห้ามยิงด้วย raw urllib** — Cloudflare 1010 บล็อก; ใช้ `openai` library เสมอ
   (`base_url=https://api.groq.com/openai/v1`)
2. **Anthropic ใช้ OpenAI-compat endpoint** (`https://api.anthropic.com/v1/`) — ไม่ต้องติดตั้ง
   anthropic SDK; `response_format` ถูก **ignore** → ต้องสั่งให้ model คืน JSON ล้วนใน prompt เอง
3. **Mock key**: เงื่อนไขทุก provider ตรวจ `"mock" not in key.lower()` — ถ้า key มี "mock"
   (หรือว่าง) ข้าม provider ไป fallback ทันที (เทสต์ใช้เทคนิคนี้บังคับ fallback)
4. อย่าเขียน `llama-3.3-70b-versatile` ฮาร์ดโค้ด — ใช้ `settings.GROQ_MODEL` (เจอในของเก่าแล้วแก้)
5. Gemini package โดน deprecate (FutureWarning ในเทสต์) — ยังใช้ได้ แต่ห้ามพึ่งเป็น provider หลัก

## ไฟล์
`backend/app/services/llm_clients.py`; ผู้ใช้: `ai_generator.py`, `ai_analyzer.py`,
`demand_radar_ai.py`, `facebook_curated.py`, `facebook_local.py`, `web_search.py`, `hermes_brain.py`

## เทสต์
`backend/tests/test_llm_providers.py` (mock `_FakeClient` คืน JSON ตายตัว — เดิน anthropic branch
โดยไม่แตะเน็ต); เติมเทสต์ทุกครั้งที่เพิ่ม provider ใหม่ (กัน "บอสใหญ่" พัง)
