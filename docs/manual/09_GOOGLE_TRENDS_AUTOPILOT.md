# Google Trends Autopilot (Local Producer)

ระบบ Local producer ดึง Google Trends Thailand RSS แล้วทำงานตามลำดับ: กรองหัวข้อเสี่ยงและซ้ำ → อ่านข่าวจาก HTTPS สาธารณะ → สร้างสคริปต์ 5 ฉาก → ผูกข้อความข้อเท็จจริงกับ evidence block → ตรวจสคริปต์ด้วย LLM รอบสอง → สร้างเสียง PremwadeeNeural +20% → เรนเดอร์ 1080x1920 พร้อมซับตาม WordBoundary → ตรวจ decode, AAC, ระดับเสียง และจอดำ → เขียน metadata/caption → เปลี่ยนชื่อไฟล์ `.part` เข้า `pending_videos` แบบ atomic.

`tools/system_runner.py` เรียก producer เมื่อคิวน้อยกว่า 4 คลิป และนับผลผลิตสำเร็จแบบถาวรเพื่อรักษา 90% trend content / 10% Shopee product. รอบโพสต์ฉุกเฉินไม่ผลิตแทรก เพื่อไม่ให้ข้าม lock, QA หรือสัดส่วน. มี single-instance lock ทั้ง producer และ system runner. หัวข้อที่ไม่ผ่านจะ cooldown 30 นาที; ไม่มีหัวข้อปลอดภัยแล้วไม่ผลิตข้อมูลจำลอง.

ไลบรารี Local อยู่ใน `backend/requirements-video.txt`: moviepy, edge-tts 7.2.8+, imageio-ffmpeg 0.5+, Pillow, PyThaiNLP, HTTPX, BeautifulSoup, filelock, OpenAI SDK และ python-dotenv. ตั้ง `TREND_SCRIPT_MODEL=qwen/qwen3.8-27b`; ต้องมี `GROQ_API_KEY`. ติดตั้งด้วย `python -m pip install -r backend/requirements-video.txt`.

ทดสอบ producer อย่างเดียวด้วย `python tools/trend_autopilot.py --once`. คำสั่งนี้อาจนำคลิปที่ผ่านทุกด่านเข้าคิวจริง แต่ไม่เรียก uploader เอง. การทำงานต่อเนื่องใช้ `python tools/system_runner.py` ตาม launcher ของระบบเดิม.

การทดสอบข้อมูลจริงวันที่ 10 กันยายน 2026: รอบ Trends สดไม่มีหัวข้อผ่านทุกด่านจึงคืน `no_eligible_topic` และไม่สร้างคลิป. Smoke test ด้วยหน้า Apple iPhone 17 ผ่าน generation → evidence mapping → factual repair/review → TTS → render → video QA; output อยู่ `artifacts/trend_autopilot/pipeline_smoke/iphone17_motion.mp4`. พบ Groq 429 ระหว่าง repair และ SDK retry สำเร็จ. ไม่ได้คัดลอก smoke test เข้าคิวและไม่ได้โพสต์.

ข้อจำกัด: ตัวผลิตนี้ใช้ typography gradient ตาม fallback ของโปรเจกต์ ยังไม่ได้ดึงภาพข่าวมาใช้. การมีข่าวใน RSS ไม่รับประกันว่าจะผลิตได้ หากหน้าอ่านไม่ได้ เนื้อหาเสี่ยง แหล่งข่าวไม่ตรงคำค้น หรือหลักฐานไม่พอ ระบบจะข้าม. Production ยังขึ้นกับ token/session ของแต่ละแพลตฟอร์มและเครื่อง Local ต้องเปิดอยู่.
