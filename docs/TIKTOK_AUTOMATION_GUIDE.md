# 📱 คู่มือสถาปัตยกรรมและการทำงานของระบบ TikTok Studio Automation 24/7
## ฉบับสมบูรณ์ — บันทึกขั้นตอนทั้งหมด, สาเหตุปัญหาที่ตรวจพบจริง, การแก้ไข 100% และคู่มือบริหาร Multi-Account

---

## 📑 สารบัญ
1. [ภาพรวมสถาปัตยกรรม (Overview & Architecture)](#1-ภาพรวมสถาปัตยกรรม)
2. [ขั้นตอนการทำงานตั้งแต่เริ่มต้นจนถึงลงคลิปสำเร็จ (End-to-End Workflow)](#2-ขั้นตอนการทำงานตั้งแต่เริ่มต้นจนถึงลงคลิปสำเร็จ)
3. [ปัญหาและอุปสรรคที่ตรวจพบจริง พร้อมสาเหตุที่แท้จริง (Root Cause Analysis)](#3-ปัญหาและอุปสรรคที่ตรวจพบจริง-พร้อมสาเหตุที่แท้จริง)
4. [แนวทางแก้ไขทางวิศวกรรมที่ทำให้บอทกดผ่าน 100% (Engineering Fixes)](#4-แนวทางแก้ไขทางวิศวกรรมที่ทำให้บอทกดผ่าน-100)
5. [การจัดการหลายบัญชี (Multi-Account Rotation System)](#5-การจัดการหลายบัญชี-multi-account-rotation-system)
6. [การรันระบบอัตโนมัติบน VPS 24 ชั่วโมง (24/7 VPS Deployment)](#6-การรันระบบอัตโนมัติบน-vps-24-ชั่วโมง)

---

## 1. ภาพรวมสถาปัตยกรรม

ระบบ **TikTok Studio Automation** พัฒนาขึ้นโดยใช้ **Playwright Python (Headless Chromium Engine)** ทำหน้าที่เป็นตัวแทนผู้ใช้ (Browser Automation) ในการล็อกอิน, แนบไฟล์วิดีโอ 9:16 Full HD, ใส่แคปชั่น/แฮชแท็ก, และคลิกปุ่มโพสต์บนหน้าเว็บ **TikTok Creator Center (`https://www.tiktok.com/tiktokstudio/upload`)**

### 💎 ทำไมต้องใช้ Web Studio Automation แทน TikTok Developer API?
* **ไม่ต้องขอ App Review:** TikTok Developer Portal ต้องผ่านการตรวจสอบเอกสารธุรกิจและนโยบาย Content Posting API ที่ใช้เวลาหลายสัปดาห์
* **ไม่ต้อง Verify Domain / URL:** สามารถเปิดใช้งานกับบัญชีใดก็ได้ทันที
* **รองรับ Multi-Account:** สามารถหมุนเวียนลงคลิปได้หลายช่องพร้อมกันอย่างอิสระ

---

## 2. ขั้นตอนการทำงานตั้งแต่เริ่มต้นจนถึงลงคลิปสำเร็จ

```text
[1. สร้างบัญชี TikTok & ยืนยันตัวตนในมือถือ (Warm-up 1 คลิป)]
                                ⬇️
[2. ดึง Session Cookie จากเบราว์เซอร์ (F12 Network -> cookie:)]
                                ⬇️
[3. บันทึก Cookie เป็น JSON ใน tools/tiktok_cookies.json หรือ _2.json]
                                ⬇️
[4. บอทเปิด Headless Chromium + ฉีด Cookie เข้า Context แบบแยกอิสระ (Stateless)]
                                ⬇️
[5. นำทางสู่ https://www.tiktok.com/tiktokstudio/upload]
                                ⬇️
[6. แนบไฟล์วิดีโอ 9:16 (input[type="file"])]
                                ⬇️
[7. พิมพ์แคปชั่น + แฮชแท็ก -> กด Escape ปิด Dropdown คำแนะนำ]
                                ⬇️
[8. เคลียร์ Modal Popup (Joyride / Turn on / Got it)]
                                ⬇️
[9. คลิกปุ่ม Post (button[data-e2e="post_video_button"])]
                                ⬇️
[10. ตรวจจับ Modal ยืนยันชั้นที่ 2 -> คลิกปุ่ม "Post now" ทันที]
                                ⬇️
[11. รอระบบ Redirect เข้าสู่ https://www.tiktok.com/tiktokstudio/content]
                                ⬇️
[12. ส่งรายงานแจ้งเตือนผลสำเร็จเข้า Telegram Commander (@pakhem_commander_bot)]
```

---

## 3. ปัญหาและอุปสรรคที่ตรวจพบจริง พร้อมสาเหตุที่แท้จริง

ระหว่างการทดสอบระบบจริงกับบัญชีใหม่ **`@cheepao.review`** ได้ตรวจพบปัญหา 5 ประการ ดังนี้:

### ❌ ปัญหาที่ 1: เซสชันของช่อง 1 และช่อง 2 ชนกัน (Session Bleeding)
* **อาการ:** สั่งโพสต์คลิปเข้าช่องที่ 2 แต่คลิปกลับไปโผล่ที่ช่องที่ 1 (`@healthgooddeals`)
* **🔍 สาเหตุที่แท้จริง:** โค้ดเดิมใช้ `launch_persistent_context(user_data_dir=USER_DATA_DIR)` โฟลเดอร์เดียวกัน ทำให้แคชและ LocalStorage ของช่อง 1 เขียนทับ Cookie ของช่อง 2
* **🟢 การแก้ไข:** เปลี่ยนมาใช้ **Stateless Context (`browser.new_context()`)** และฉีด Cookie JSON ของแต่ละช่องเข้าบริบทแยกขาดจากกัน 100%

---

### ❌ ปัญหาที่ 2: บัญชีใหม่ถูกบล็อก "Something went wrong. Try again later."
* **อาการ:** บัญชีกดโพสต์ไม่ได้ ระบบ TikTok Studio ขึ้นเตือนข้อผิดพลาด
* **🔍 สาเหตุที่แท้จริง:** บัญชี `@cheepao.review` เพิ่งสร้างใหม่สด ๆ (0 วัน / 0 คลิป) ระบบ Anti-Bot ของ TikTok จะบล็อกการยิงผ่านหน้าเว็บไว้ชั่วคราว จนกว่าจะมีประวัติการใช้งานจริง
* **🟢 การแก้ไข:** ผู้ใช้ทำการ **Warm-up บัญชีด้วยการลงคลิปแรกผ่านแอป TikTok ในมือถือ 1 ครั้ง** หลังจากนั้นระบบ TikTok จะจัดสถานะเป็น **Active Creator** และปลดล็อคให้บอทโพสต์ผ่านหน้าเว็บได้ถาวร

---

### ❌ ปัญหาที่ 3: Dropdown แนะนำ Hashtag บังปุ่ม Post
* **อาการ:** Playwright แจ้งเตือน `TimeoutError: <span class="hash-tag-topic"> intercepts pointer events`
* **🔍 สาเหตุที่แท้จริง:** เมื่อพิมพ์เครื่องหมาย `#` ในช่อง Caption ระบบ TikTok จะเปิดเมนูแนะนำแฮชแท็ก (`data-floating-ui-inert`) ลอยขึ้นมาทับปุ่มควบคุมบนหน้าจอ
* **🟢 การแก้ไข:** สั่งให้บอทกดปุ่ม **`Escape` (`page.keyboard.press("Escape")`)** ทันทีที่พิมพ์แคปชั่นเสร็จ เพื่อปิดหน้าต่าง Dropdown แนะนำแฮชแท็ก

---

### ❌ ปัญหาที่ 4: Onboarding Joyride & Copyright Modal บล็อกหน้าจอ
* **อาการ:** มีหน้าต่าง `TUXModal-overlay` และ `react-joyride` ปรากฏขึ้นมาบังปุ่มกด
* **🔍 สาเหตุที่แท้จริง:** TikTok Studio จะมีป๊อปอัปแนะนำฟีเจอร์ใหม่ และป๊อปอัปถามเรื่องการตรวจสอบลิขสิทธิ์เสียง (Copyright Check)
* **🟢 การแก้ไข:** เพิ่มสคริปต์ตรวจจับและคลิกปุ่ม `Got it`, `Turn on`, `เข้าใจแล้ว` พร้อมคำสั่งลบ Overlay ที่ค้างอยู่ออกก่อนกดโพสต์

---

### ❌ ปัญหาที่ 5: ติด Modal ยืนยันชั้นที่สอง "Continue to post? -> Post now"
* **อาการ:** บอทคลิกปุ่ม Post แล้ว แต่ URL ไม่เปลี่ยนหน้า และคลิปไม่บันทึกเข้าสู่ Studio
* **🔍 สาเหตุที่แท้จริง:** สำหรับวิดีโอที่ระบบยังสแกนความปลอดภัยไม่เสร็จ TikTok จะเปิดหน้าต่างถามย้ำว่า *"Continue to post? We're still checking your video for potential issues. [Cancel] [Post now]"* ซึ่งต้องกดปุ่ม **`Post now`** ซ้ำอีกครั้งหนึ่งจึงจะบันทึกคลิป
* **🟢 การแก้ไข:** เพิ่มลูปตรวจจับป๊อปอัปหลังคลิก Post หากพบปุ่ม **`Post now`** หรือ **`โพสต์เลย`** ให้ทำการคลิกยืนยันทันที

---

## 4. แนวทางแก้ไขทางวิศวกรรมที่ทำให้บอทกดผ่าน 100%

### โค้ดส่วนสำคัญใน `tools/tiktok_studio_uploader.py`:

```python
# 1. ใช้ Stateless Browser Context แยกตาม Cookie
browser = p.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1440, "height": 900})
context.add_cookies(target_cookies)
page = context.new_page()

# 2. กรอกแคปชั่นและปิด Hashtag Dropdown
caption_box.type(clean_caption, delay=20)
page.keyboard.press("Escape")
page.wait_for_timeout(1000)

# 3. เคลียร์ Modal Popup (Got it / Turn on)
page.evaluate("""() => {
    document.querySelectorAll('button').forEach(b => {
        const t = (b.innerText || '').trim().toLowerCase();
        if (t === 'turn on' || t === 'got it' || t === 'เข้าใจแล้ว' || t === 'agree') {
            b.click();
        }
    });
}""")

# 4. คลิกปุ่ม Post ด้วย Selector ที่แม่นยำ
post_btn = page.locator('button[data-e2e="post_video_button"]').first
post_btn.click(force=True)

# 5. ตรวจจับและกดยืนยัน Modal "Post now"
for _ in range(15):
    page.wait_for_timeout(1000)
    if "content" in page.url:
        break
    confirm_btn = page.locator('button').filter(has_text=re.compile(r'^(Post now|โพสต์เลย|Confirm)$', re.I)).first
    if confirm_btn.count() > 0 and confirm_btn.is_visible():
        confirm_btn.click(force=True)
        break
```

---

## 5. การจัดการหลายบัญชี (Multi-Account Rotation System)

ระบบรองรับการเพิ่มบัญชี TikTok แบบไม่จำกัดช่อง:

| ลำดับ | ชื่อช่อง | URL | ไฟล์ Cookie | โฟลเดอร์เซสชัน |
| :--- | :--- | :--- | :--- | :--- |
| **ช่องที่ 1** | **Anda Review** | `tiktok.com/@healthgooddeals` | `tools/tiktok_cookies.json` | `tools/tiktok_user_data/` |
| **ช่องที่ 2** | **ชี้เป้าโปรคุ้ม** | `tiktok.com/@cheepao.review` | `tools/tiktok_cookies_2.json` | `tools/tiktok_user_data_tiktok_cookies_2/` |
| **ช่องที่ N** | *(ช่องถัดไป)* | `tiktok.com/@...` | `tools/tiktok_cookies_N.json` | `tools/tiktok_user_data_tiktok_cookies_N/` |

### วงรอบการโพสต์ (Cadence):
* บอทใน `tools/system_runner.py` จะรันเธรด `run_tiktok_uploader_loop()` ทุก ๆ **60 นาที**
* ในแต่ละรอบ จะหยิบคลิปใหม่จากคลัง และสลับบัญชีโพสต์แบบ **Round-Robin (ช่อง 1 ➔ ช่อง 2 ➔ ช่อง 1 ➔ ...)**

---

## 6. การรันระบบอัตโนมัติบน VPS 24 ชั่วโมง

* **เซิร์ฟเวอร์ VPS:** `157.85.111.232` (Ubuntu Linux)
* **เซอร์วิส Systemd:** `shopee-bot.service`
* **คำสั่งอัปเดตและรีสตาร์ทบอทบน VPS:**
  ```bash
  ssh root@157.85.111.232 "cd /root/shopee-affiliate-bot && git pull origin main && systemctl restart shopee-bot"
  ```
* **คำสั่งตรวจสอบ Live Logs:**
  ```bash
  ssh root@157.85.111.232 "journalctl -u shopee-bot -f"
  ```
* **ศูนย์สั่งการผ่านมือถือ:** ควบคุมระยะไกลผ่าน Telegram Commander (`@pakhem_commander_bot`) ตลอด 24 ชั่วโมง

---

## 7. สถาปัตยกรรมป้องกันคลิปซ้ำ 100% (Decoupled Thread Separation & Anti-Duplicate History)

เพื่อป้องกันปัญหาคลิปถูกโพสต์ซ้ำซ้อน ระบบได้จัดโครงสร้างการทำงานดังนี้:

1. **Decoupled Thread Separation:**
   - โมดูล `reels_uploader/uploader.py` ดูแลเฉพาะ Facebook Reels (3 เพจ) และ YouTube Shorts (5 ช่อง) ยิงทุก 30 นาที **โดยไม่แตะต้อง TikTok เด็ดขาด**
   - เธรด `run_tiktok_uploader_loop()` ใน `tools/system_runner.py` รับผิดชอบ TikTok ทุกช่องแต่เพียงผู้เดียว (ยิงทุก 60 นาที)
2. **Per-Channel JSON History Tracking (`tools/posted_tiktok_history.json`):**
   - บันทึกประวัติคลิปที่เคยโพสต์แยกตามคีย์บัญชี (เช่น `tiktok_cookies` และ `tiktok_cookies_2`)
   - ก่อนจะหยิบคลิปใหม่จากคลัง `pending_videos/` หรือ `posted/` ระบบจะนำชื่อไฟล์มาเทียบกับประวัติของช่องนั้น ๆ หากพบว่าช่องนั้นเคยโพสต์ไปแล้ว จะข้ามไปหาคลิปถัดไปทันที ทำให้ไม่เกิดคลิปซ้ำ 100%
