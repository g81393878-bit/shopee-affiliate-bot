---
name: promo-caption-rotation
description: >-
  แคปชันโปรโมทอัตโนมัติ + หมุนภาพโปสเตอร์สำหรับโพสต์ "แนะนำบอทแม่เข็ม" (ไม่ใช่สินค้า):
  bot_profile.promo_captions / pick_promo_caption (round-robin + state),
  bot/post_page.py (โพสต์รูป + หมุนภาพ), tools/post_fb_video.py (โพสต์วิดีโอ),
  tools/generate_posters.py (สร้างโปสเตอร์ Pillow).
  Use when the user mentions แคปชันอัตโนมัติ, แนะนำแม่เข็ม, โปสเตอร์, โพสต์โปรโมท,
  หมุนแคปชัน, หมุนภาพ, generate_posters, post_page, or post_fb_video.
---

# โพสต์โปรโมท + แคปชันอัตโนมัติ (แนะนำบอทแม่เข็ม)

## ภาพรวม
โพสต์โปรโมทบอทใช้ 2 องค์ประกอบที่หมุนเวียนคู่กัน (แต่ละโพสต์ได้ภาพใหม่ + แคปชันใหม่):
- **แคปชัน**: `bot_profile.promo_captions()` หลายแบบ + `pick_promo_caption()` หมุน round-robin
- **ภาพโปสเตอร์**: `bot/post_page.py resolve_poster_image()` หมุน round-robin จากโฟลเดอร์ assets

## แคปชัน (แหล่งความจริงเดียว = bot_profile.py)
- `promo_captions()` คืน list ข้อความหลายแบบ — **เพิ่ม/แก้แคปชันที่นี่ที่เดียว**
  (post_page.py + post_fb_video.py ใช้ร่วมกัน ห้าม copy ไปวางเอง)
- `pick_promo_caption(advance=True)` หยิบทีละตัว; `advance=False` = แค่ peek (dry-run ไม่กินตำแหน่ง)
- state จำตำแหน่ง: `backend/.promo_caption_state.json` (gitignored)

## วิธีคิด/ออกแบบแคปชันใหม่ (น้ำเสียงป้าเข็ม)
1. โครงสร้าง 3 ท่อน: **hook** (ปวดใจแม่ค้า) → **benefit** (ฟีเจอร์เป็นรูปธรรม) → **CTA** (ราคา + ลิงก์ LINE)
2. ลงท้าย CTA ด้วย `LINE_OA_URL` เสมอ (env, default `https://lin.ee/o9Kjp1N`)
3. ราคาเริ่มต้น 490.- (แพ็กเกจ Lean) — ตรงกับการ์ด Flex แพ็กเกจ
4. emoji ไทยใช้ได้ (😊🤖🛒📦🔍🚀) แต่ CLI ต้อง reconfig stdout UTF-8 (ดูกับดัก)
5. ห้ามพูดเกินจริง — ไม่การันตียอดขาย/ไม่รับประกัน 100% (ยึดหลักการเดียวกัน Demand Radar)

## ภาพโปสเตอร์ (tools/generate_posters.py)
- สร้างภาพ 1080×1350 (4:5 portrait) ด้วย Pillow + ฟอนต์ Tahoma (`tahomabd.ttf`/`tahoma.ttf`) — รองรับไทย
- สีตรงการ์ดแพ็กเกจ LINE: เหลือง `#F5A623` / เขียว `#2ECC71` / น้ำเงิน `#3498DB` / ม่วง `#9B59B6`
- แก้ข้อความ/สีใน `POSTERS` แล้วรัน `python tools/generate_posters.py`
- ปลายทาง default `D:\Shopee_Web_Scraping\assets`

## การหมุนภาพ (bot/post_page.py)
- `resolve_poster_image(path, advance=True)` — เรียงชื่อไฟล์ + วนทีละภาพ; ข้ามไฟล์ที่มี `avatar`/`icon`
- state: `backend/.promo_poster_state.json` (gitignored)
- เพิ่มภาพใหม่ลงโฟลเดอร์ = เข้ารอบหมุนอัตโนมัติ ไม่ต้องแก้โค้ด

## เครื่องมือโพสต์
- รูป: `python bot/post_page.py` (post_photo + แคปชันหมุน + ภาพหมุน)
- วิดีโอ: `backend/.venv/Scripts/python.exe tools/post_fb_video.py --file assets/x.mp4`
  (ไม่ระบุ `--caption` → ใช้แคปชันหมุนอัตโนมัติ)

## กับดัก
1. **console Windows cp874 เขียน emoji ไม่ได้** (✅😊) → CLI ทุกตัวต้อง
   `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` ก่อน print
2. **ห้าม copy แคปชันไปวางใน post_page/post_fb_video** — แก้ที่ bot_profile.py ที่เดียว
   (ไม่งั้น drift: แก้ที่นึง อีกที่นึงไม่เปลี่ยน)
3. dry-run ต้อง `advance=False` ทั้งแคปชันและภาพ — ดูตัวอย่างแล้ว rotation ต้องไม่เลื่อน
4. โฟลเดอร์ assets มี 2 ที่: `D:\Shopee_Web_Scraping\assets` (บอทใช้, ภายนอก repo) กับ
   `assets/` ใน repo (สำเนา) — อย่าแก้ผิดที่
5. state ไฟล์ `backend/.promo_*_state.json` ต้องอยู่ใน `.gitignore` เสมอ

## ไฟล์
- `backend/app/services/bot_profile.py` (promo_captions / pick_promo_caption)
- `bot/post_page.py` (โพสต์รูป + หมุนภาพ)
- `tools/post_fb_video.py` (โพสต์วิดีโอ + แคปชันหมุน)
- `tools/generate_posters.py` (สร้างโปสเตอร์)

## เทสต์
- `backend/tests/test_bot_profile.py` (แคปชัน/line_cta_footer/owner_contact)
- CLI tools ไม่มี unit test — ตรวจด้วย dry-run (`post_page.py --dry-run` / `post_fb_video.py --dry-run`)
