# Google Trends Autopilot (Local Producer)

ระบบ Local producer ดึง Google Trends Thailand RSS แล้วทำงานตามลำดับ: กรองหัวข้อเสี่ยงและซ้ำ → อ่านข่าวจาก HTTPS สาธารณะ → คัดประโยคภาษาไทยที่สมบูรณ์ด้วยกฎ Local → สร้างสคริปต์ 5 ฉากจากข้อความต้นฉบับโดยตรง → สร้างเสียง PremwadeeNeural +20% → เรนเดอร์ 1080x1920 พร้อมซับตาม WordBoundary → ตรวจ decode, AAC, ระดับเสียง และจอดำ → เขียน metadata/caption → เปลี่ยนชื่อไฟล์ `.part` เข้า `pending_videos` แบบ atomic.

คลัง Hook Local มี 33 แบบ แยกตาม 11 หมวดและเลือกแบบคงที่จาก hash ของหัวข้อ จึงหลากหลายแต่ตรวจซ้ำได้. ประโยคต้นฉบับถูกให้คะแนนจากคำในหัวข้อ หมวด ตำแหน่ง และข้อมูลตัวเลข ก่อนเลือกสามประโยคที่สำคัญที่สุด โดยยังเก็บข้อความต้นฉบับครบประโยค. แหล่งข่าวใช้ Google Trends ร่วมกับ RSS สำรองไทยจาก Beartai, Techhub, The Standard, DroidSans, Brand Inside, Marketing Oops, Mango Zero และ Kapook; feed ใดล้มจะข้ามเฉพาะ feed นั้น.

`tools/system_runner.py` เรียก producer เมื่อคิวน้อยกว่า 4 คลิป และนับผลผลิตสำเร็จแบบถาวรเพื่อรักษา 90% trend content / 10% Shopee product. รอบโพสต์ฉุกเฉินไม่ผลิตแทรก เพื่อไม่ให้ข้าม lock, QA หรือสัดส่วน. มี single-instance lock ทั้ง producer และ system runner. หัวข้อที่ไม่ผ่านจะ cooldown 30 นาที; ไม่มีหัวข้อปลอดภัยแล้วไม่ผลิตข้อมูลจำลอง.

ค่าเริ่มต้น `TREND_USE_AI=false` ไม่เรียก Groq หรือ LLM: บอทใช้ตัวกรอง, regex, anti-duplicate และ template บนเครื่องทั้งหมด และข้ามข่าวเมื่อหาประโยคไทยที่ปลอดภัยครบ 3 ประโยคไม่ได้. หากเจ้าของตั้ง `TREND_USE_AI=true` จึงอนุญาตให้ใช้ Groq เป็น fallback โดยใช้ `TREND_SCRIPT_MODEL`. ไลบรารี Local อยู่ใน `backend/requirements-video.txt`: moviepy, edge-tts 7.2.8+, imageio-ffmpeg 0.5+, Pillow, PyThaiNLP, HTTPX, BeautifulSoup, filelock, OpenAI SDK และ python-dotenv. ติดตั้งด้วย `python -m pip install -r backend/requirements-video.txt`.

ทดสอบ producer อย่างเดียวด้วย `python tools/trend_autopilot.py --once`. คำสั่งนี้อาจนำคลิปที่ผ่านทุกด่านเข้าคิวจริง แต่ไม่เรียก uploader เอง. การทำงานต่อเนื่องใช้ `python tools/system_runner.py` ตาม launcher ของระบบเดิม.

การทดสอบข้อมูลจริงวันที่ 10 กันยายน 2026: รอบ Trends สดไม่มีหัวข้อผ่านทุกด่านจึงคืน `no_eligible_topic` และไม่สร้างคลิป. Smoke test ด้วยหน้า Apple iPhone 17 ผ่าน generation → evidence mapping → factual repair/review → TTS → render → video QA; output อยู่ `artifacts/trend_autopilot/pipeline_smoke/iphone17_motion.mp4`. พบ Groq 429 ระหว่าง repair และ SDK retry สำเร็จ. ไม่ได้คัดลอก smoke test เข้าคิวและไม่ได้โพสต์.

เปิดใช้งาน Local วันที่ 10 กันยายน 2026: process เริ่มด้วย `backend/.venv/Scripts/python.exe tools/system_runner.py`; stdout/stderr อยู่ใต้ `artifacts/trend_autopilot/`. Windows Scheduled Task ชื่อ `PaKhem Trends Autopilot` เริ่มเมื่อผู้ใช้ล็อกอิน ตั้ง Hidden, IgnoreNew, restart ได้ 3 ครั้ง และไม่มี execution time limit. ตัว lock ใน Python ป้องกัน process ซ้ำอีกชั้น. Scheduled Task เป็นสถานะเครื่อง Local จึงไม่ได้อยู่ใน Git; ตรวจด้วย `Get-ScheduledTask -TaskName 'PaKhem Trends Autopilot'`.

ข้อจำกัด: ตัวผลิตนี้ใช้ typography gradient ตาม fallback ของโปรเจกต์ ยังไม่ได้ดึงภาพข่าวมาใช้. การมีข่าวใน RSS ไม่รับประกันว่าจะผลิตได้ หากหน้าอ่านไม่ได้ เนื้อหาเสี่ยง แหล่งข่าวไม่ตรงคำค้น หรือหลักฐานไม่พอ ระบบจะข้าม. Production ยังขึ้นกับ token/session ของแต่ละแพลตฟอร์มและเครื่อง Local ต้องเปิดอยู่.

รางสินค้าใช้ `PRODUCT_USE_AI=false` เป็นค่าเริ่มต้นเช่นกัน. ระบบเรียงสินค้าด้วยคะแนน Local จากยอดขาย รีวิว ค่าคอม ความพร้อมของลิงก์ Affiliate/ภาพจริง ราคาเปลี่ยนแปลง และ Demand Radar โดยไม่ใช้ `ai_score` ในการตัดสิน. เสียงขายสินค้าใช้คลังเทมเพลตตามหมวด; Groq จะทำงานเฉพาะเมื่อกำหนด `PRODUCT_USE_AI=true` เอง.

`tools/performance_learner.py` อ่านยอดจริงจาก `performance_logs` ใน Supabase ทุกชั่วโมง คำนวณ CTR, Conversion, ค่าคอมต่อคลิก และ confidence จากจำนวนวิว แล้วเขียนคะแนนแบบ atomic ที่ `artifacts/product_learning/scores.json`. โรงงานนำคะแนนนี้ไปรวมในการเลือกสินค้ารอบถัดไปสูงสุด 20 คะแนน และส่งสรุป Telegram วันละครั้งช่วง 20:00 น. หากยังไม่มี log ระบบรายงานตามจริงและใช้คะแนนคุณภาพสินค้าพื้นฐานต่อไป.
