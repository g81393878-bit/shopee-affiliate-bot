# Facebook Reels Auto-Uploader 🤖🎬

อัปโหลดคลิปวิดีโอสั้น (Reels) ขึ้น Facebook Page "ป้าเข็ม ขายของ" อัตโนมัติ
พร้อมเขียนแคปชั่นป้ายยาภาษาไทยด้วย AI (Groq) และแปะลิงก์ Shopee Affiliate

ระบบประกอบด้วย 2 ส่วน:
- **`uploader.py`** (root) — orchestrator: คิว FIFO + **แปลงคลิป 9:16 อัตโนมัติ** + แคปชั่น + pacing + guard โควต้า/วัน
- **`backend/app/services/facebook_poster.py`** — `post_reel()` ทำ 3-step video upload session จริงผ่าน Graph API (reuse token + rate-limit logging ตัวเดียวกับ `post_feed`)

---

## โครงสร้างไฟล์

```
(project root)/
├── uploader.py                  # orchestrator (FIFO + normalize 9:16 + AI caption + pacing + daily guard)
├── products.json                # จับคู่ชื่อไฟล์วิดีโอ → ข้อมูลสินค้า Shopee
├── pending_videos/              # 📥 คลิป .mp4 รอโพสต์ (FIFO ตามชื่อไฟล์) — ใส่ .gitkeep ไว้ commit
├── posted/                      # 📤 คลิปที่โพสต์สำเร็จถูกย้ายมา (กันโพสต์ซ้ำ)
│
├── last_post_time.txt           # runtime: เวลาโพสต์สำเร็จล่าสุด (gitignored)
├── posts_today.txt              # runtime: จำนวนโพสต์วันนี้ (gitignored)
├── uploader_execution.log       # runtime: log การรัน (gitignored)
│
└── backend/
    ├── .env                     # env ทั้งหมดอยู่ที่นี่ (FACEBOOK_PAGE_ACCESS_TOKEN ฯลฯ)
    └── app/services/facebook_poster.py
                                 # post_reel() + _reels_error_hint()
```

> ไม่มี `caption_generator.py` / `reels_publisher.py` แยก — แคปชั่น AI reuse
> `app/services/llm_clients.py` (Groq multi-key failover) และอัปโหลด reuse
> `facebook_poster.py` (httpx + token + `_log_rate_limit_usage`)

---

## 3-Step Upload Session (Reels Publishing API)

`post_reel()` ทำตาม official flow ของ Meta:

1. **Init** — `POST /{page-id}/video_reels` (`upload_phase=start`) → ได้ `video_id` + `upload_url`
2. **Upload** — `POST upload_url` (`rupload.facebook.com`) ส่ง binary `.mp4` ด้วย header `Authorization: OAuth {token}`
3. **Publish** — `POST /{page-id}/video_reels` (`upload_phase=finish`, `video_state=PUBLISHED`) พร้อม `description`/`title`

ทุก step log header `X-App-Usage`/`X-Business-Use-Case` (เตือนล่วงหน้าก่อนชน rate limit)
และเมื่อ error จะต่อท้ายคำแนะนำไทยอัตโนมัติ (`_reels_error_hint`):

| Code | ความหมาย |
|---|---|
| 190 / 102 | token หมดอายุ / session สิ้นสุด — สร้าง token ใหม่ |
| 10 | สิทธิ์ไม่พอ — ต้องการ `pages_show_list`/`pages_read_engagement`/`pages_manage_posts` |
| 32 | Page rate limit ถึง — ลดความถี่หรือรอ |
| 506 | โพสต์ซ้ำติดกัน |
| 1363128 | ความยาวต้อง 3–90 วินาที |
| 1363040 | อัตราส่วนต้อง 16:9–9:16 (แนะนำ 9:16) |
| 1363127 | ความละเอียดขั้นต่ำ 540p (แนะนำ 1080p) |
| 1363129 | Frame rate 24–60 FPS |

---

## การตั้งค่า (env — ทั้งหมดใน `backend/.env`)

| ตัวแปร | จำเป็น | ค่า default | หมายเหตุ |
|---|---|---|---|
| `FACEBOOK_PAGE_ACCESS_TOKEN` | ✅ | — | long-lived **page token** (ต้องมี `publish_video` + `pages_manage_posts` + `pages_read_engagement`) |
| `FACEBOOK_PAGE_ID` | — | `1307380735783361` | เพจป้าเข็ม ขายของ (ตั้งชัดเจนไว้กันพึ่ง default) |
| `GROQ_API_KEY` | — | — | เขียนแคปชั่น AI; ไม่ตั้ง = ใช้แคปชั่น template |
| `GROQ_MODEL` | — | `openai/gpt-oss-120b` | โมเดลแคปชั่น |
| `POSTING_SPACING_HOURS` | — | `3.0` | ระยะห่างขั้นต่ำระหว่างโพสต์ (ชม.) |
| `MAX_REELS_PER_DAY` | — | `30` | ลิมิตจริงของ Reels API = 30 โพสต์/24 ชม. |

---

## แปลงคลิปอัตโนมัติ (normalize) — ไม่ต้องตั้งขนาดเอง

ก่อนโพสต์ `uploader.py` จะรัน ffmpeg (binary ที่ติดมากับ `imageio_ffmpeg` ใน venv)
แปลงคลิปให้ตรง spec Reels อัตโนมัติ:

- **9:16 1080×1920** (แนวตั้ง) — ถ้าคลิปเป็นแนวนอน/จัตุรัส จะเติม**พื้นหลังเบลอ**แทนแถบดำ
- **30fps**
- ตัดไม่เกิน **90 วินาที**
- H.264 + AAC (`+faststart`) — มีเสียงก็เก็บ ไม่มีก็ผ่าน

> แปลงเสร็จเป็นไฟล์ temp → โพสต์แล้วลบทิ้ง ไฟล์ต้นฉบับใน `pending_videos/` ไม่ถูกแก้

ถ้าคลิปตรง spec อยู่แล้วและอยากข้ามการแปลง (เร็วกว่า ไม่ re-encode):
```bash
python uploader.py --no-normalize
```

---

## `products.json` (จับคู่คลิป → สินค้า)

```json
{
  "keychain_demo.mp4": {
    "product_name": "ที่แขวนกุญแจไม้แม่เหล็กสไตล์มินิมอล ติดผนังไม่ต้องเจาะรู",
    "price": "159",
    "category": "ของใช้ในบ้าน",
    "affiliate_link": "https://s.shopee.co.th/xxxxxxxxxx"
  }
}
```

- key = **ชื่อไฟล์วิดีโอ** (ต้องตรงกับไฟล์ใน `pending_videos/`)
- ใส่ลิงก์ `s.shopee.co.th` จริง (ลิงก์ปลอมจะทำให้แคปชั่นเสีย)
- ไม่มี entry → ใช้แคปชั่น generic

---

## วิธีใช้งาน

```bash
# โพสต์คลิปถัดไป 1 ตัว (ถ้าถึงเวลา spacing และยังไม่ครบโควต้า/วัน)
python uploader.py

# จำลอง: โชว์คลิป + แคปชั่น ไม่โพสต์จริง
python uploader.py --dry-run

# ข้าม pacing โพสต์ทันที (ยังนับ daily limit อยู่)
python uploader.py --force

# ไม่แปลงคลิป (ใช้ไฟล์เดิม — คลิปต้องตรง spec Reels อยู่แล้ว)
python uploader.py --no-normalize
```

**Pacing:** บันทึกเวลาสำเร็จล่าสุดใน `last_post_time.txt` — ถ้ารันก่อนครบ
`POSTING_SPACING_HOURS` จะปิดตัวทันทีไม่โพสต์ (กันสแปม/ลด reach)

**Daily guard:** นับโพสต์วันนี้ใน `posts_today.txt` — ครบ `MAX_REELS_PER_DAY` (30)
จะข้ามอัตโนมัติ

**แนะนำ:** ตั้ง Windows Task Scheduler / cron รันทุก 30–60 นาที → พอถึงเวลา
spacing ระบบจะโพสต์คลิปถัดไปให้เอง

---

## ข้อกำหนดคลิป

ปกติ**ไม่ต้องทำเอง** — `normalize` แปลงให้อัตโนมัติแล้ว แต่ควรรู้ไว้ (กรณีใช้ `--no-normalize`):

- สัดส่วน **9:16** (แนวตั้ง) · ความยาว **3–90 วินาที** · ความละเอียดขั้นต่ำ **540p** (แนะนำ 1080p) · Frame rate **24–60 FPS**
- ไม่งั้นโดน error `1363xxx` (โค้ดถอดความหมายให้ใน log แล้ว)
