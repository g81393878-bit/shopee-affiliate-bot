# -*- coding: utf-8 -*-
"""tools/master_reel_creator.py — เครื่องมือสร้างคลิปวิดีโอ 9:16 ตามแม่แบบมาตรฐานระดับสตูดิโอ (Master Template Creator)
สร้างคลิปง่ายๆ ในคลิกเดียว หรือกรอกข้อความเอง มีระบบล็อกตัวหนังสือ พิกัด และความเร็วเสียงพากย์อัตโนมัติ 100%
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, List

# บังคับ encoding UTF-8 สำหรับ Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
REELS_DIR = ROOT_DIR / "reels_uploader"
PENDING_DIR = REELS_DIR / "pending_videos"
PENDING_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = ROOT_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(REELS_DIR) not in sys.path:
    sys.path.insert(0, str(REELS_DIR))

import auto_product_reels
import master_template_config as mtc
import video_template_engine
import standalone_content_generator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("master_reel_creator")

MODE_CHOICES = {
    "1": ("LIFE_HACK_TIP", "ทริคแม่บ้านแก้ปัญหา (สีเขียว Emerald)"),
    "2": ("WORK_PRODUCTIVITY", "ทริคคนทำงานออฟฟิศ (สีฟ้า Ocean)"),
    "3": ("TRENDING_NEWS", "ข่าวด่วนกระแสสังคม (สีแดง Crimson)"),
    "4": ("CELEBRITY_TREND", "กระแสไวรัลคนดัง (สีม่วง Purple)"),
    "5": ("LUCKY_FORTUNE", "เลขเด็ด & ดวงมงคล (สีทอง Imperial Gold)"),
    "6": ("PRODUCT_PROMO", "สินค้า Shopee ของแท้ (สีส้ม Shopee)"),
}

DEFAULT_CATEGORY_IMAGES = {
    "LIFE_HACK_TIP": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=800&auto=format&fit=crop",
    "WORK_PRODUCTIVITY": "https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=800&auto=format&fit=crop",
    "TRENDING_NEWS": "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=800&auto=format&fit=crop",
    "CELEBRITY_TREND": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800&auto=format&fit=crop",
    "LUCKY_FORTUNE": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop",
    "PRODUCT_PROMO": "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=800&auto=format&fit=crop",
}


def get_default_hero_image(mode: str) -> Optional[object]:
    """ดึงภาพถ่ายจริงความคมชัดสูงเริ่มต้นประจำหมวดหมู่"""
    url = DEFAULT_CATEGORY_IMAGES.get(mode, DEFAULT_CATEGORY_IMAGES["LIFE_HACK_TIP"])
    return standalone_content_generator.fetch_topic_image(url)


def create_master_reel_custom(
    title: str,
    hook: str,
    steps: List[str],
    mode: str = "LIFE_HACK_TIP",
    image_input: Optional[str] = None,
    output_filename: Optional[str] = None
) -> Optional[Path]:
    """สร้างคลิปวิดีโอ 9:16 ตามสเปกแม่แบบมาตรฐานสตูดิโอ จากข้อความที่กำหนดเอง"""
    # 1. ตรวจสอบความถูกต้องของข้อความตามแม่แบบ
    clean_hook = mtc.clean_master_text(hook)
    clean_steps = [mtc.format_master_step(s) for s in steps[:3]]
    while len(clean_steps) < 3:
        clean_steps.append("กดติดตามช่องไว้ ไม่พลาดเรื่องสำคัญ")

    is_valid, errors = mtc.validate_master_inputs(clean_hook, clean_steps, mode)
    if not is_valid:
        print("\n❌ ข้อความไม่ผ่านเกณฑ์แม่แบบมาตรฐาน:")
        for err in errors:
            print(f"   • {err}")
        return None

    # 2. เตรียมภาพถ่ายจริง 100%
    from PIL import Image
    hero_img = None
    if image_input:
        inp_path = Path(image_input)
        if inp_path.exists() and inp_path.is_file():
            try:
                hero_img = Image.open(inp_path).convert("RGB")
            except Exception as e:
                logger.warning(f"⚠️ ไม่สามารถเปิดไฟล์รูปภาพท้องถิ่น {inp_path}: {e}")
        elif image_input.startswith("http://") or image_input.startswith("https://"):
            hero_img = standalone_content_generator.fetch_topic_image(image_input)

    # Fallback: หากไม่ได้ระบุภาพ ให้สลับใช้ Hero Typography Card 100% ตามคู่มือ Rule 26 เพื่อให้หัวข้อตรงกันเป๊ะ ไม่แสดงภาพผิดหมวด
    if hero_img is None:
        logger.info("ℹ️ ไม่ได้ระบุภาพถ่ายเฉพาะ — สลับใช้ Hero Typography Card ตามคู่มือ Rule 26")
        hero_images = [None, None, None]
    else:
        hero_images = [hero_img, hero_img, hero_img]

    # 3. จัดทำข้อมูลหัวข้อ (Topic Data)
    topic_data = {
        "title": title or clean_hook,
        "hook": clean_hook,
        "summary": " ".join(clean_steps),
        "source": "Master Template Creator",
    }

    # 4. สร้างภาพโปสเตอร์ 3 จังหวะตามแม่แบบมาตรฐาน
    posters = video_template_engine.render_cinematic_template_posters(
        mode=mode,
        topic_data=topic_data,
        hero_images=hero_images,
        takeaways=clean_steps,
        channel_name="Anda",
        line_id="@137gsref"
    )

    if not posters or len(posters) < 3:
        print("❌ เกิดข้อผิดพลาดในการเรนเดอร์ภาพโปสเตอร์")
        return None

    # 5. สร้างเสียงพากย์ AI TTS (มาตรฐาน rate="+0%")
    # สคริปต์พูดธรรมชาติ ชัดเจน ไม่ย่อจนห้วน เล่าเรื่องราวครบถ้วน
    voice_script = topic_data.get("voiceover_script") if (topic_data.get("voiceover_script") and len(topic_data.get("voiceover_script")) >= 50) else f"{clean_hook}! เรื่องนี้เริ่มจาก {clean_steps[0]} โดยมีรายละเอียดสำคัญคือ {clean_steps[1]} และบทสรุปคือ {clean_steps[2]} ทุกคนคิดเห็นยังไง คอมเมนต์บอกกันหน่อย และอย่าลืมกดติดตามช่องไว้นะคะ"
    ts_now = int(time.time())
    audio_path = TEMP_DIR / f"master_tts_{ts_now}.mp3"
    tts_ok = auto_product_reels.generate_tts_audio(voice_script, audio_path)
    if not tts_ok or not auto_product_reels.verify_audio_file(audio_path):
        print("❌ สร้างเสียงพากย์ไม่สำเร็จ")
        if audio_path.exists():
            audio_path.unlink(missing_ok=True)
        return None

    audio_len = auto_product_reels.get_audio_duration(audio_path)
    target_duration = max(mtc.TTS_CONFIG["min_video_duration"], audio_len + mtc.TTS_CONFIG["audio_tail_buffer"])

    # 6. บันทึกภาพเฟรมชั่วคราวและเรนเดอร์เป็นวิดีโอ 1080x1920
    poster_paths = []
    for idx, p_img in enumerate(posters):
        p_path = TEMP_DIR / f"master_frame_{idx}_{ts_now}.jpg"
        p_img.save(p_path, "JPEG", quality=95)
        poster_paths.append(p_path)

    if not output_filename:
        title_tag = re.sub(r'[\\/*?:"<>|\s]+', '_', (title or clean_hook))[:32].strip(' ._-')
        safe_mode = mode.lower()
        final_filename = f"{safe_mode}_{title_tag}_{ts_now}.mp4" if title_tag else f"content_{safe_mode}_{ts_now}.mp4"
    else:
        final_filename = standalone_content_generator.sanitize_video_filename(output_filename, f"reel_{mode.lower()}")

    output_path = PENDING_DIR / final_filename

    success = auto_product_reels.multiphase_posters_to_video(
        poster_paths, output_path, audio_path=audio_path, duration=target_duration
    )

    # 7. ทำความสะอาดไฟล์ชั่วคราว
    for p in poster_paths:
        try:
            p.unlink()
        except Exception:
            pass
    if audio_path.exists():
        try:
            audio_path.unlink()
        except Exception:
            pass

    if success and output_path.exists():
        # ลงทะเบียน metadata และชื่อวิดีโอลง products.json
        products_json_path = REELS_DIR / "products.json"
        products_meta = {}
        if products_json_path.exists():
            try:
                products_meta = json.loads(products_json_path.read_text(encoding="utf-8"))
            except Exception:
                products_meta = {}

        products_meta[output_path.name] = {
            "product_name": title or clean_hook,
            "price": "",
            "category": mtc.THEME_PALETTES.get(mode, {}).get("name", "คอนเทนต์สาระความรู้"),
            "affiliate_link": "",
            "is_pure_content": True,
            "content_mode": mode,
            "topic_data": topic_data
        }
        products_json_path.write_text(json.dumps(products_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            from telegram_notifier import send_telegram_video
            caption_preview = f"🎬 [คลิปใหม่สร้างด้วย Master Creator]\n📌 {title or clean_hook}\n\n👉 ขนาด 1080x1920 (9:16 Full HD) พร้อมในคลังรอโพสต์"
            send_telegram_video(output_path, caption=caption_preview)
        except Exception:
            pass
        return output_path
    return None


def generate_sample_preview_card(output_path: Path, mode: str = "LIFE_HACK_TIP") -> Path:
    """สร้างภาพตัวอย่างการ์ดแม่แบบมาตรฐาน (1080x1920) สำหรับตรวจสอบฟอนต์และระยะห่าง"""
    thm = mtc.THEME_PALETTES.get(mode, mtc.THEME_PALETTES["LIFE_HACK_TIP"])
    topic_data = {
        "title": "วิธีแก้ปัญหาท่อน้ำตันใน 1 นาที",
        "hook": "ท่อน้ำตัน อย่าเพิ่งรื้อ! ทำตามนี้หายขาดทันที",
        "summary": "วิธีแก้ปัญหาท่อน้ำตันง่ายๆ ด้วยของในบ้าน",
    }
    takeaways = [
        "เทเบกกิ้งโซดา 1 ถ้วยลงไปในท่อ",
        "ราดน้ำส้มสายชูตาม รอฟองฟู่ 5 นาที",
        "เปิดน้ำร้อนล้างตาม ท่อโล่งทันที"
    ]
    hero_img = get_default_hero_image(mode)
    posters = video_template_engine.render_cinematic_template_posters(
        mode=mode,
        topic_data=topic_data,
        hero_images=[hero_img, hero_img, hero_img],
        takeaways=takeaways,
        channel_name="Anda",
        line_id="@137gsref"
    )
    # บันทึกภาพจังหวะที่ 1 (Active ข้อ 1)
    posters[0].save(output_path, "PNG")
    return output_path


def interactive_menu():
    """เมนูเทอร์มินัลสร้างคลิปแม่แบบมาตรฐานแบบง่าย (1-Click)"""
    while True:
        print("\n" + "=" * 65)
        print("   🎬 ระบบสร้างคลิปวิดีโอ 9:16 ตามแม่แบบมาตรฐาน (Master Creator)")
        print("=" * 65)
        print(" • ล็อกขนาดหน้าจอ: 1080 x 1920 (9:16 Full HD)")
        print(" • ล็อกพิกัด & ฟอนต์: ตาม Golden Master Template ไม่ตกขอบ 100%")
        print(" • เสียงพากย์ TTS: Microsoft Edge Neural (ความเร็วธรรมชาติ +0%)")
        print("=" * 65)
        print(" [1] 🤖 สร้างคลิปอัตโนมัติด้วย AI (1-Click AI Auto)")
        print(" [2] ✍️ กรอกข้อความเองแบบง่าย (Custom Quick Form)")
        print(" [3] 🖼️ เรนเดอร์ภาพตัวอย่างการ์ดแม่แบบ (Preview Master Card)")
        print(" [4] ⚡ เร่งผลิตคลิป AI 3 คลิปเข้าคลังรอโพสต์ (Batch 3 Reels)")
        print(" [0] 🔙 ย้อนกลับ\n")

        choice = input("กรุณาเลือกเมนู (0-4): ").strip()
        if choice == "0":
            break

        elif choice == "1":
            print("\n--- เลือกหมวดหมู่คอนเทนต์ ---")
            for k, (m, desc) in MODE_CHOICES.items():
                print(f" [{k}] {desc}")
            print(" [A] สุ่มอัตโนมัติจากกระแสไวรัล")
            m_choice = input("เลือกหมวด (1-6 หรือ A): ").strip().upper()
            target_mode = MODE_CHOICES.get(m_choice, (None, None))[0]

            print("\n🏷️ ตั้งชื่อวิดีโอ (Video Naming):")
            c_title = input(" • ตั้งชื่อวิดีโอ / หัวข้อ (กด Enter ให้ AI ตั้งให้อัตโนมัติ): ").strip() or None
            c_fname = input(" • ตั้งชื่อไฟล์วิดีโอ (.mp4 หรือกด Enter เพื่อใช้อัตโนมัติ): ").strip() or None

            print("\n⏳ กำลังใช้ AI ผลิตคลิปตามแม่แบบมาตรฐานสตูดิโอ...")
            res = standalone_content_generator.generate_standalone_reel(
                mode=target_mode,
                custom_title=c_title,
                custom_filename=c_fname
            )
            if res and res.get("video_path") and Path(res["video_path"]).exists():
                print("\n" + "=" * 60)
                print("✅ ผลิตคลิปวิดีโอสำเร็จเรียบร้อยตามแม่แบบมาตรฐาน!")
                print(f" 🏷️ ชื่อวิดีโอ: {res.get('title')}")
                print(f" 📁 ชื่อไฟล์: {res.get('filename')}")
                print(f" 📍 พาธไฟล์: {res['video_path']}")
                print(f" 🪝 พาดหัว Hook: {res.get('hook')}")
                print(f" ⏱️ ความยาว: {res.get('duration', 0):.1f} วินาที")
                print("=" * 60)
            else:
                print("❌ เกิดข้อผิดพลาดในการผลิตคลิป")
            input("\nกด Enter เพื่อดำเนินการต่อ...")

        elif choice == "2":
            print("\n--- เลือกหมวดหมู่คอนเทนต์ ---")
            for k, (m, desc) in MODE_CHOICES.items():
                print(f" [{k}] {desc}")
            m_choice = input("เลือกหมวด (1-6, ค่าเริ่มต้น 1): ").strip()
            mode = MODE_CHOICES.get(m_choice, ("LIFE_HACK_TIP", ""))[0]

            print(f"\n✍️ กรอกข้อมูลสร้างคลิป (หมวด: {mode})")
            print("💡 ข้อแนะนำ: Hook และแต่ละข้อ ไม่ควรเกิน 45 ตัวอักษร")
            title = input("• 🏷️ ชื่อวิดีโอ / หัวข้อเรื่อง (Video Title): ").strip()
            fname_in = input("• 📁 ตั้งชื่อไฟล์วิดีโอ (เช่น ทริคกระทะไหม้.mp4 หรือกด Enter เพื่อใช้ตามชื่อวิดีโอ): ").strip()
            hook = input("• 🪝 ข้อความ Hook 3 วิ (ตัวอย่าง: ท่อน้ำตัน ทำตามนี้หายขาด!): ").strip()
            s1 = input("• 1️⃣ สาระสำคัญ ข้อที่ 1: ").strip()
            s2 = input("• 2️⃣ สาระสำคัญ ข้อที่ 2: ").strip()
            s3 = input("• 3️⃣ สาระสำคัญ ข้อที่ 3: ").strip()
            img_in = input("• 📸 ลิงก์รูปภาพ หรือพาธไฟล์ในเครื่อง (กด Enter เพื่อใช้ภาพถ่ายจริงอัตโนมัติ): ").strip()

            print("\n⏳ กำลังสร้างวิดีโอ 1080x1920 และเสียงพากย์สตูดิโอ...")
            out_file = create_master_reel_custom(
                title=title,
                hook=hook,
                steps=[s1, s2, s3],
                mode=mode,
                image_input=img_in or None,
                output_filename=fname_in or None
            )
            if out_file and out_file.exists():
                print("\n" + "=" * 60)
                print("✅ สร้างคลิปวิดีโอสำเร็จเรียบร้อย 100%!")
                print(f" 🏷️ ชื่อวิดีโอ: {title or hook}")
                print(f" 📁 ชื่อไฟล์: {out_file.name}")
                print(f" 📍 พาธเต็ม: {out_file}")
                print(" 🎯 ขนาด: 1080 x 1920 (9:16 Full HD)")
                print(" 🔊 เสียงพากย์: สปีด +0% คมชัด เป็นธรรมชาติ")
                print("=" * 60)
            else:
                print("❌ การสร้างคลิปล้มเหลว โปรดตรวจสอบข้อความอีกครั้ง")
            input("\nกด Enter เพื่อดำเนินการต่อ...")

        elif choice == "3":
            print("\n⏳ กำลังเรนเดอร์ภาพตัวอย่างการ์ดแม่แบบมาตรฐาน...")
            preview_file = ROOT_DIR / "preview_master_card.png"
            generate_sample_preview_card(preview_file)
            print(f"✅ บันทึกภาพตัวอย่างแม่แบบไว้ที่: {preview_file}")
            # พยายามเปิดภาพใน Windows
            try:
                os.startfile(str(preview_file))
            except Exception:
                pass
            input("\nกด Enter เพื่อดำเนินการต่อ...")

        elif choice == "4":
            print("\n⏳ กำลังสั่งผลิตคลิปใหม่ 3 คลิปเข้าคลัง...")
            auto_product_reels.run_batch(3)
            print("✅ ผลิตครบ 3 คลิปเรียบร้อยแล้ว!")
            input("\nกด Enter เพื่อดำเนินการต่อ...")


def main():
    parser = argparse.ArgumentParser(description="Master Template Reel Creator")
    parser.add_argument("--auto", action="store_true", help="สร้างคลิปอัตโนมัติ 1 คลิปด้วย AI")
    parser.add_argument("--custom", action="store_true", help="สร้างคลิปแบบกำหนดเอง")
    parser.add_argument("--mode", type=str, default=None, help="ระบุหมวดหมู่คอนเทนต์")
    parser.add_argument("--title", type=str, default=None, help="กำหนดชื่อวิดีโอ (Video Title)")
    parser.add_argument("--hook", type=str, default=None, help="ข้อความพาดหัว Hook 3 วิ")
    parser.add_argument("--steps", type=str, default=None, help="ขั้นตอน 3 ข้อ คั่นด้วยเครื่องหมายจุลภาค (,)")
    parser.add_argument("--image", type=str, default=None, help="พาธไฟล์รูปภาพหรือ URL")
    parser.add_argument("-o", "--output-filename", type=str, default=None, help="กำหนดชื่อไฟล์วิดีโอ (.mp4)")
    parser.add_argument("--preview", action="store_true", help="เรนเดอร์ภาพตัวอย่างการ์ดแม่แบบ")
    parser.add_argument("--batch", type=int, default=0, help="ผลิตคลิปเป็นชุดตามจำนวนที่ระบุ")
    args = parser.parse_args()

    if args.preview:
        out = ROOT_DIR / "preview_master_card.png"
        generate_sample_preview_card(out, mode=args.mode or "LIFE_HACK_TIP")
        print(f"✅ บันทึกภาพตัวอย่างแม่แบบไว้ที่: {out}")
        return

    if args.custom or (args.hook and args.steps):
        steps_list = [s.strip() for s in (args.steps or "").split(",") if s.strip()]
        res_path = create_master_reel_custom(
            title=args.title or args.hook or "เรื่องน่ารู้",
            hook=args.hook or args.title or "หยุดดูก่อน!",
            steps=steps_list,
            mode=args.mode or "LIFE_HACK_TIP",
            image_input=args.image,
            output_filename=args.output_filename
        )
        if res_path and res_path.exists():
            print(f"✅ ผลิตคลิปวิดีโอ Custom สำเร็จ: {res_path}")
        else:
            print("❌ การผลิตคลิปล้มเหลว")
        return

    if args.auto:
        res = standalone_content_generator.generate_standalone_reel(
            mode=args.mode,
            custom_title=args.title,
            custom_filename=args.output_filename
        )
        v_path = (res.get("video_path") or res.get("path")) if res else None
        if v_path and Path(v_path).exists():
            print(f"\n============================================================")
            print(f"✅ ผลิตคลิปวิดีโอสำเร็จตามแม่แบบมาตรฐานสตูดิโอ 100%!")
            print(f" 🏷️ ชื่อวิดีโอ: {res.get('title')}")
            print(f" 📁 ชื่อไฟล์: {res.get('filename')}")
            print(f" 📍 พาธไฟล์: {v_path}")
            print(f" 🪝 พาดหัว Hook: {res.get('hook')}")
            print(f"============================================================")
        else:
            print("❌ การผลิตคลิปล้มเหลว")
        return

    if args.batch > 0:
        auto_product_reels.run_batch(args.batch)
        return

    interactive_menu()


if __name__ == "__main__":
    main()
