# HANDOFF.md — สถานะงานค้างระหว่าง AI session

> **วิธีใช้ (อ่านก่อน):**
> - **AI ตัวใหม่ที่เข้ามาทำงาน: ต้องอ่านไฟล์นี้ + ตรวจ `git status` ก่อนเริ่มงานเสมอ**
>   (บังคับตาม AGENTS.md → Multi-Agent Handoff Protocol)
> - **AI ตัวที่กำลังทำงาน:** ถ้าจะหยุดกลางคัน (ยังไม่ commit งานให้ครบ) ให้เติมข้อมูลจริงลงใน
>   ส่วน 1–5 ด้านล่าง แล้ว commit ไฟล์นี้ทันที พร้อมกับงานที่ทำไว้
> - **เมื่องานเสร็จและ commit ครบ:** ให้ล้างเนื้อหาในส่วน 1–5 กลับเป็นสถานะว่าง แล้ว commit
>   ไฟล์นี้ — เพื่อไม่ให้ AI ตัวถัดไปเข้าใจผิดว่างานยังค้าง

## สถานะ: 🟡 โค้ด push + deploy ครบแล้ว — เหลืองาน manual ฝั่งเจ้าของ (cron-job.org + Facebook Live)

---

## 1. งานที่ทำแล้ว (ล่าสุด)

- `38e9cde` feat(facebook): post_feed รองรับ `link` param — Facebook ดึง preview รูปสินค้าจากลิงก์อัตโนมัติ
  (แยก affiliate URL ออกจากข้อความมาเป็น link param → โพสต์เป็นการ์ดมีรูป; เทสต์จริงยืนยันแล้ว)
- `a5c0c7f` feat(facebook): เพิ่ม auto-post ลงเพจ Facebook — cron `/api/cron/facebook-post`
  (ไฟล์ใหม่ `app/services/facebook_poster.py` + เลือกสินค้าที่ยังไม่โพสต์ → caption Groq/fallback → feed; 4 เทสต์)
- `ef52a63` feat(persona): ปรับแก้ตัวตนป้าเข็มเป็นแม่ค้าออนไลน์ Shopee Affiliate ด้วย RCAO Framework (`persona.py`)
- `a29aec7` feat(facebook): รองรับ `LINE_OA_URL` — ใส่ลิงก์ LINE OA ใน `BOT_INTRO` + ชุดโพสต์ (fallback บอกชื่อร้าน)
- `9b35347` docs: เพิ่มชุดโพสต์ Facebook แนะนำบอทป้าเข็ม (`docs/facebook-content.md` — 3 caption + เนื้อ + image prompt)
- `d6ab88f` docs(skills): align facebook-app-config SKILL กับตัวจริง (FACEBOOK_VERIFY_TOKEN + /api/webhooks/facebook)
- `dce3c82` feat(facebook): เปลี่ยน reply จาก ack เป็นแนะนำบอทป้าเข็ม (`BOT_INTRO`) — ไม่ค้น/ไม่โพสต์สินค้า
  (ใครทักแชทเพจ Facebook → ตอบแนะนำบอท + วิธีคุยต่อที่ LINE)
- `965bdb9` feat(facebook): เพิ่ม webhook `/api/webhooks/facebook` — GET verify (challenge) + POST ตรวจ X-Hub-Signature-256
  (ไฟล์ใหม่ `app/api/facebook_bot.py` + 7 เทสต์ใน `tests/test_facebook_webhook.py`; ทำขั้น 1–2 ของ architecture guide)
- `2bad44e` docs: เพิ่ม Facebook & Shopee Affiliate Bot Architecture Guide
  (ไฟล์ใหม่ `docs/facebook-architecture-guide.md` — แผนผัง + บทบาทส่วนประกอบ + ขั้นเชื่อมต่อ + 2 ไอเดียต่อยอด)
- `465dfc2` docs: อัปเดต HANDOFF.md — บันทึก commit orchestrator + ขั้นตอน push/deploy
- `65a8476` feat(orchestrator): เพิ่ม Claude "บอสใหญ่" คุมวง plan/dispatch/review + worker groq/firecrawl/claude + fallback Groq
  (ฟีเจอร์ใหม่ `app/services/orchestrator.py` + 8 เทสต์ mock ใน `tests/test_orchestrator.py`)

## 2. งานค้าง

<!-- ว่าง — ไม่มีงานโค้ดค้าง ทำงานทุกชิ้น commit ครบแล้ว -->

- โพสต์ test บนเพจ 2 อัน (ข้อความล้วน + ลิงก์การ์ด) รอเจ้าของลบเองถ้าต้องการ

## 3. ขั้นตอนต่อไป

- ✅ **push + deploy เรียบร้อย** — deploy `dep-d9vv5fjf2k7s73c4a5og` → `live` (commit `38e9cde`); endpoint cron ขึ้น production แล้ว (401 ถ้าไม่มี/ผิด token)
- ⏳ ตั้ง cron-job.org ยิง `POST https://shopee-affiliate-bot-9e9n.onrender.com/api/cron/facebook-post?token=<CRON_TOKEN>` — ช่วงทดสอบทุก 10 นาที, หลัง test ผ่านลดเป็นทุก 4 ชม.
- ✅ ตั้ง env บน Render ครบ 5 ตัว: FACEBOOK_APP_ID / APP_SECRET / VERIFY_TOKEN / PAGE_ACCESS_TOKEN + LINE_OA_URL (รวม 14 ตัว)
- ⏳ **ตั้ง Webhook บน Facebook**: Messenger → Settings → Callback URL `https://shopee-affiliate-bot-9e9n.onrender.com/api/webhooks/facebook` + Verify Token (ค่าใน `tools/render_env.local.json`) → Verify and Save → Subscribe page events
- ⏳ **เปิดแอปเป็น Live**: App Settings → Basic → ใส่ Privacy Policy URL `https://shopee-affiliate-bot-9e9n.onrender.com/privacy` → สลับโหมดเป็น Live (ตอนนี้ยัง Development → ลูกค้าทั่วไปทักเพจไม่ได้)
- ⏳ (ไม่บังคับ) ตั้ง `ANTHROPIC_API_KEY` บน Render — ตอนนี้ orchestrator บอสใหญ่ fallback เป็น Groq

## 4. ไฟล์ที่ถืออยู่ / โดนแก้

<!-- ว่าง -->

## 5. หมายเหตุ

- CI: `.github/workflows/test.yml` รัน `pytest` + coverage gate 85% ทุก push/PR
- เทสต์ทั้งชุด: 388 passed (วิธี A link preview มี 5 เทสต์ใหม่ รวมอยู่ในนี้)
- บอทจริง healthy: `/health` → 200, `llm_provider=groq`, `database_url_configured=true` (URL: `https://shopee-affiliate-bot-9e9n.onrender.com`)
- Render env vars ตอนนี้มี 14 ตัว (ครบ Facebook + LINE_OA_URL แล้ว): DATABASE_URL, CRON_TOKEN, GROQ_API_KEY, LINE_CHANNEL_ACCESS_TOKEN/SECRET, LLM_PROVIDER, TAVILY_API_KEY, FIRECRAWL_API_KEY, SHEET_WEBHOOK_URL, FACEBOOK_APP_ID/SECRET/VERIFY_TOKEN/PAGE_ACCESS_TOKEN, LINE_OA_URL
  (ยังไม่มีแค่ ANTHROPIC_API_KEY)
- ฟีเจอร์ orchestrator ยังเป็นโมดูลเดี่ยว — ยังไม่ถูกเรียกจาก `line_bot.py` (ยังไม่มีผลกับลูกค้าจริง)
- facebook webhook: หน้าที่ตอนนี้ = แนะนำบอทป้าเข็ม (แชท) — ไอเดีย A (ค้นสินค้าในแชท) ถูกพักไว้
- facebook auto-post: ไอเดีย B เริ่มแล้ว — cron `/api/cron/facebook-post` โพสต์สินค้าค่าคอมสูงลง feed (กันซ้ำด้วย CampaignLog status=fbpost)
- repo สะอาด ไม่มี untracked junk สำหรับงานใหม่
