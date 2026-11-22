"""
Facebook Live 24/7 Streamer CLI (FFmpeg-Powered)
รองรับการสตรีมคลิปวิดีโอวนลูปเข้า Facebook Live อัตโนมัติ มีระบบ Auto-Reconnect
"""

import os
import sys
import time
import shutil
import argparse
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# ป้องกัน UnicodeEncodeError บน Windows Command Prompt (CP874)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# โหลด .env หากมี
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / "backend" / ".env", override=False)
load_dotenv()

LIVE_DEFAULT_TITLE = "🔴 [สด] ปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม คัดพิเศษ ไซส์จัมโบ้ 4 ตัวโล! (สั่งซื้อทักแชท/พิมพ์ สนใจ)"
LIVE_DEFAULT_DESC = (
    "🐟 วันนี้มีปลาสลิดแดดเดียวเข้าใหม่สดๆ ร้อนๆ จ้า! ปลาสลิดสุพรรณแท้ ป้าเข็ม คัดพิเศษ ไซส์จัมโบ้ 4 ตัวโล เนื้อแน่นหนาฟู มันแทรก เค็มน้อยกำลังดี!\n"
    "💬 สั่งซื้อ: กดปุ่ม \"ส่งข้อความ\" ทักแชทเพจ หรือพิมพ์คำว่า \"สนใจ\" ในคอมเมนต์ไลฟ์นี้ได้เลยจ้า!\n\n"
    "✅ เนื้อปลาสลิดสุพรรณธรรมชาติแท้ 97% + เกลือสมุทรธรรมชาติ 3% (ไร้สารกันบูด 0% ไร้ผงชูรส 0%)\n"
    "✅ น้ำหนักเนื้อปลาล้วนหลังตัดหัวแล้ว (ไซส์จัมโบ้คัดพิเศษ 4 ตัว/กก. ตัวใหญ่เท่าฝ่ามือ)\n"
    "✅ ซีลสูญญากาศแช่เยือกแข็ง -18°C แพ็กซองฟอยล์เก็บความเย็นส่งตรงถึงบ้าน (เสียเคลมฟรี 100%)\n\n"
    "📦 โปรโมชั่นล็อตใหม่วันนี้ (จำหน่ายแบบดิบแดดเดียว นำไปทอดไฟกลางเหลืองกรอบหอมฟุ้ง):\n"
    "1️⃣ ชุดพอดีมื้อ 500 กรัม (2 ตัวจัมโบ้): โอนเงิน 390 บาท ส่งฟรี!\n"
    "2️⃣ 🔥 ชุดยอดฮิตสุดคุ้ม 1 กิโลกรัม (4 ตัวจัมโบ้): โอนเงิน 550 บาท ส่งฟรี! (เพิ่มแค่ 160.- ได้ปลาเพิ่มเท่าตัว!)\n"
    "3️⃣ ชุดตุนสุดคุ้ม 2 กิโลกรัม (8 ตัวจัมโบ้): โอนเงิน 1,090 บาท ส่งฟรีรถห้องเย็นควบคุมอุณหภูมิ!\n\n"
    "👇 พิมพ์คำว่า \"สนใจ\" หรือเลขชุด 1, 2, 3 ในคอมเมนต์ไลฟ์สดนี้ เดี๋ยวป้าเข็มทักแชทไปรับออเดอร์ทันทีจ้า!"
)


def create_auto_facebook_live(page_id: str, page_token: str, title: str = LIVE_DEFAULT_TITLE, description: str = LIVE_DEFAULT_DESC) -> dict:
    """สร้างห้องไลฟ์สดอัตโนมัติผ่าน Facebook Graph API (ไม่ต้องก๊อปปี้ Stream Key เอง)"""
    import httpx
    r = None
    for attempt in range(4):
        r = httpx.post(
            f"https://graph.facebook.com/v21.0/{page_id}/live_videos",
            data={
                "access_token": page_token,
                "status": "LIVE_NOW",
                "title": title,
                "description": description,
            },
            timeout=25.0,
        )
        if r.status_code == 200:
            break
        time.sleep(2.5)
    if r is None or r.status_code != 200:
        raise RuntimeError(f"Graph API error ({r.status_code if r else 'None'}): {r.text if r else ''}")
    data = r.json()
    live_id = data.get("id", "")
    video_id = ""
    try:
        r_info = httpx.get(
            f"https://graph.facebook.com/v21.0/{live_id}",
            params={"access_token": page_token, "fields": "id,video,permalink_url,status,stream_url,secure_stream_url,ingest_streams"},
            timeout=15.0,
        )
        if r_info.status_code == 200:
            info_json = r_info.json()
            video_id = (info_json.get("video") or {}).get("id", "")
            data["video_id"] = video_id
            data["permalink_url"] = info_json.get("permalink_url", "")
            # ดึง Stream URL รูปแบบ FB-... (ไม่มี query params & ที่ทำให้ FFmpeg GnuTLS บน Windows แท้งด้วย TLS fatal alert)
            ingest_list = info_json.get("ingest_streams") or []
            clean_stream_url = ""
            if ingest_list and isinstance(ingest_list, list):
                clean_stream_url = ingest_list[0].get("secure_stream_url") or ingest_list[0].get("stream_url") or ""
            if not clean_stream_url:
                clean_stream_url = info_json.get("stream_url") or data.get("stream_url") or data.get("secure_stream_url") or ""
            if clean_stream_url:
                data["clean_stream_url"] = clean_stream_url
    except Exception:
        pass
    # โพสต์คอมเมนต์แรกราคา + รูปจานปลาทอดใต้ไลฟ์สดอัตโนมัติ
    try:
        from app.services.facebook_poster import _auto_post_order_comment
        target_comment_id = video_id or live_id
        if target_comment_id:
            _auto_post_order_comment(str(target_comment_id), description, str(page_id), page_token)
    except Exception:
        pass
    return data


def find_ffmpeg_binary() -> str:
    """ค้นหา ffmpeg ในเครื่อง ทั้งจาก PATH และ Python imageio_ffmpeg"""
    # 1. เช็คจาก PATH ในระบบ
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    # 2. เช็คจาก imageio_ffmpeg package
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.exists(ffmpeg_exe):
            return ffmpeg_exe
    except Exception:
        pass

    # 3. เช็ค path เฉพาะเจาะจงบน Windows
    default_win = r"C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
    if os.path.exists(default_win):
        return default_win

    return ""


def find_available_videos() -> list:
    """ค้นหาไฟล์ .mp4 แนะนำในโปรเจกต์ (เรียงคลิปใหม่ล่าสุดวันนี้ไว้เป็นอันดับ 1)"""
    candidates = []
    search_dirs = [ROOT / "image", ROOT / "artifacts/videos", ROOT / "artifacts"]
    for sdir in search_dirs:
        if sdir.exists():
            for f in sdir.glob("*.mp4"):
                candidates.append(f)
    priority_names = [
        "pakhem_fresh_batch_20261031.mp4",
        "pakhem_fish_commercial_30s_clean.mp4",
        "pakhem_fried_gourami_fixed_20261029.mp4",
    ]
    candidates.sort(key=lambda p: (priority_names.index(p.name) if p.name in priority_names else 99, p.name))
    return candidates


def prompt_video_choice(candidates: list) -> str:
    """ให้ผู้ใช้เลือกไฟล์วิดีโอหรือพิมพ์/ลากไฟล์ลงมา (กด Enter เลือก [1] ทันที)"""
    print("\n🎥 พบไฟล์วิดีโอในโปรเจกต์ที่พร้อมใช้งาน:")
    for idx, v in enumerate(candidates[:6], 1):
        tag = " ⭐ (คลิปใหม่วันนี้ - แนะนำ!)" if idx == 1 else ""
        print(f"  [{idx}] {v.name}{tag}")
    print("  [0] ลากไฟล์วิดีโออื่นมาวาง หรือพิมพ์ Path เอง")

    while True:
        choice = input("\n👉 เลือกหมายเลข [1-6] (หรือกด Enter เพื่อเลือก [1] ทันที): ").strip().strip('"').strip("'")
        if not choice:
            return str(candidates[0].resolve())
        if choice.isdigit():
            c_int = int(choice)
            if 1 <= c_int <= len(candidates):
                return str(candidates[c_int - 1].resolve())
            elif c_int == 0:
                manual = input("📁 วาง Path ไฟล์วิดีโอ: ").strip().strip('"').strip("'")
                if os.path.exists(manual):
                    return str(Path(manual).resolve())
                print("❌ ไม่พบไฟล์ดังกล่าว ลองใหม่อีกครั้ง")
        else:
            if os.path.exists(choice):
                return str(Path(choice).resolve())
            print("❌ ไม่พบไฟล์ดังกล่าว ลองใหม่อีกครั้ง")


def test_video(ffmpeg_bin: str, video_path: str) -> bool:
    """ทดสอบอ่านและเข้ารหัสไฟล์วิดีโอ 3 วินาทีแรก เพื่อความชัวร์ 100% ก่อนไลฟ์จริง"""
    print(f"\n🔍 กำลังทดสอบตรวจสอบความสมบูรณ์ของไฟล์วิดีโอ: {os.path.basename(video_path)} ...")
    test_cmd = [
        ffmpeg_bin,
        "-t", "3",
        "-i", video_path,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-f", "null",
        "-"
    ]
    try:
        res = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=10)
        if res.returncode == 0:
            print("✅ ไฟล์วิดีโอสมบูรณ์ โคเดกภาพและเสียงพร้อมทำงาน 100%!")
            return True
        else:
            print("⚠️ คำเตือนจาก FFmpeg:")
            print(res.stderr[-300:])
            return False
    except Exception as e:
        print(f"❌ ทดสอบไม่ผ่าน: {e}")
        return False


def start_live_stream(ffmpeg_bin: str, video_path: str, stream_key: str, loop: bool = True, bitrate: str = "3500k", duration_minutes: int = 0, page_id: str = "", page_token: str = "", live_id: str = ""):
    """เริ่มยิงสตรีมเข้า Facebook Live แบบมี Auto-Reconnect และรองรับการตั้งเวลาปิดอัตโนมัติ (Timer Auto-Stop)"""
    if stream_key.startswith("rtmp://") or stream_key.startswith("rtmps://"):
        rtmps_url = stream_key
    else:
        rtmps_url = f"rtmps://live-api-s.facebook.com:443/rtmp/{stream_key}"

    # คำนวณเวลาสิ้นสุดหากมีการกำหนดระยะเวลา
    start_time = time.time()
    end_deadline = (start_time + (duration_minutes * 60)) if duration_minutes > 0 else 0

    # ประกอบคำสั่ง FFmpeg ตามมาตรฐาน Facebook Live
    cmd = [ffmpeg_bin, "-re"]

    if loop:
        cmd.extend(["-stream_loop", "-1"])

    cmd.extend([
        "-i", video_path,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", bitrate,
        "-maxrate", bitrate,
        "-bufsize", f"{int(bitrate.replace('k', '')) * 2}k",
        "-pix_fmt", "yuv420p",
        "-g", "60",
        "-keyint_min", "60",
        "-sc_threshold", "0",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-f", "flv",
        rtmps_url
    ])

    duration_desc = f"ตั้งเวลาปิดอัตโนมัติใน {duration_minutes} นาที ({duration_minutes/60:.1f} ชม.)" if duration_minutes > 0 else "เปิดวนลูปไม่รู้จบ (จนกว่าจะสั่งปิด)"

    print("\n" + "=" * 65)
    print("🚀 เริ่มต้นระบบสตรีมมิ่ง Facebook Live 24/7 (Autopilot Timer)")
    print(f"   📹 ไฟล์วิดีโอ : {video_path}")
    print(f"   🔄 การวนลูป  : {'เปิดวนลูปต่อเนื่อง' if loop else 'เล่นรอบเดียว'}")
    print(f"   ⏱️ ระยะเวลา  : {duration_desc}")
    print(f"   ⚡ บิตเรต     : {bitrate}")
    print("   🔴 สถานะ     : สัญญาณกำลังยิงขึ้นสู่เซิร์ฟเวอร์ Facebook...")
    print("   💡 คำแนะนำ  : กด [Ctrl + C] ในหน้าต่างนี้เพื่อหยุดการสตรีมก่อนกำหนดได้ตลอดเวลา")
    print("=" * 65 + "\n")

    attempt = 1
    while True:
        try:
            # ตรวจสอบว่าหมดเวลาหรือยังก่อนเริ่ม/ต่อรอบ
            if end_deadline > 0 and time.time() >= end_deadline:
                print(f"\n⏰ ครบกำหนดเวลาสตรีม {duration_minutes} นาทีแล้ว! ระบบกำลังปิดไลฟ์สดอัตโนมัติ...")
                break

            process = subprocess.Popen(cmd)

            # ลูปเฝ้าดูโปรเซสพร้อมตรวจจับเวลาหมด
            while process.poll() is None:
                if end_deadline > 0 and time.time() >= end_deadline:
                    print(f"\n\n⏰ [Autopilot Timer] ครบกำหนดเวลา {duration_minutes} นาทีแล้ว!")
                    print("🛑 กำลังสั่งปิดการสตรีมและบันทึกวิดีโอ Replay อัตโนมัติ...")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return_code = 0
                    break
                time.sleep(1)

            return_code = process.poll()

            if return_code == 0 or (end_deadline > 0 and time.time() >= end_deadline):
                print("\n🏁 การสตรีมสิ้นสุดลงเรียบร้อยแล้วอย่างสมบูรณ์")
                # แจ้งเตือนเข้า Telegram / LINE หากตั้งค่าไว้
                try:
                    from tools.telegram_notifier import send_admin_line_notification, send_telegram_sync
                    msg = f"🏁 [Facebook Live] สตรีมครบกำหนด {duration_minutes} นาที และปิดอัตโนมัติเรียบร้อยแล้วจ้า! (วิดีโอถูกบันทึกเป็น Replay บนเพจแล้ว)"
                    send_admin_line_notification(msg)
                    send_telegram_sync(msg)
                except Exception:
                    pass
                break
            else:
                print(f"\n⚠️ สัญญาณสตรีมหลุด (Exit Code: {return_code})")
                if end_deadline > 0 and time.time() >= end_deadline:
                    break
                print(f"🔄 กำลังรอ 5 วินาทีเพื่อเชื่อมต่อใหม่รอบที่ {attempt}...")
                time.sleep(5)
                attempt += 1

        except KeyboardInterrupt:
            print("\n\n🛑 ผู้ใช้สั่งหยุดการสตรีม (Ctrl + C)")
            if 'process' in locals() and process:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            print("✅ ปิดระบบสตรีมมิ่งเรียบร้อยแล้ว ปลอดภัย 100%")
            break


def main():
    parser = argparse.ArgumentParser(description="Facebook Live 24/7 FFmpeg Streamer")
    parser.add_argument("--video", "-v", type=str, help="Path ไปยังไฟล์วิดีโอ .mp4")
    parser.add_argument("--key", "-k", type=str, help="Facebook Stream Key")
    parser.add_argument("--auto-page", "-p", type=int, choices=[1, 2], help="สร้างห้องไลฟ์สดอัตโนมัติบนเพจ 1 หรือ เพจ 2 (ไม่ต้องก๊อป Stream Key)")
    parser.add_argument("--bitrate", "-b", type=str, default="3500k", help="Bitrate (เช่น 3500k, 4000k)")
    parser.add_argument("--hours", "-H", type=float, default=0.0, help="กำหนดระยะเวลาไลฟ์สดเป็นชั่วโมง (เช่น 2 หรือ 2.5) แล้วปิดอัตโนมัติ")
    parser.add_argument("--minutes", "-m", type=int, default=0, help="กำหนดระยะเวลาไลฟ์สดเป็นนาที (เช่น 90 หรือ 120)")
    parser.add_argument("--rest-minutes", "-r", type=int, default=30, help="เวลาพักระหว่างรอบไลฟ์สด (นาที) ค่าเริ่มต้น 30 นาที")
    parser.add_argument("--auto-cycle", "-c", action="store_true", help="โหมดวนรอบอัตโนมัติ เช้า-บ่าย-เย็น-ดึก (ไลฟ์จบ พัก แล้วเปิดรอบใหม่ให้เอง)")
    parser.add_argument("--yes", "-y", action="store_true", help="โหมดอัตโนมัติ 100%% ไม่ต้องถามยืนยัน (เลือกคลิปแนะนำและเริ่มทันที)")
    parser.add_argument("--no-loop", action="store_true", help="ไม่วนลูป (เล่นรอบเดียวแล้วจบ)")
    parser.add_argument("--test", action="store_true", help="โหมดทดสอบไฟล์วิดีโออย่างเดียว (ไม่ยิงขึ้น Facebook)")
    args = parser.parse_args()

    print("=" * 65)
    print("🐟 PAKHEM FACEBOOK LIVE AUTOMATION SYSTEM (CLI ENGINE)")
    print("=" * 65)

    # 1. เช็ค FFmpeg
    ffmpeg_bin = find_ffmpeg_binary()
    if not ffmpeg_bin:
        print("❌ ไม่พบ FFmpeg ในระบบ กรุณาตรวจสอบการติดตั้ง")
        sys.exit(1)
    print(f"✅ ตรวจพบ FFmpeg: {ffmpeg_bin}")

    # 2. เช็คไฟล์วิดีโอ
    video_path = args.video
    if not video_path:
        candidates = find_available_videos()
        if candidates:
            if args.yes:
                video_path = str(candidates[0].resolve())
                print(f"🎬 [Auto-Select] เลือกคลิปวิดีโอแนะนำอัตโนมัติ: {candidates[0].name}")
            else:
                video_path = prompt_video_choice(candidates)
        else:
            video_path = input("\n📁 วาง Path ไฟล์วิดีโอ .mp4 ที่ต้องการสตรีม: ").strip().strip('"').strip("'")

    if not os.path.exists(video_path):
        print(f"❌ ไม่พบไฟล์: {video_path}")
        sys.exit(1)

    # 3. โหมดทดสอบ
    if args.test:
        test_video(ffmpeg_bin, video_path)
        sys.exit(0)

    # 4. เลือกเพจไลฟ์สดอัตโนมัติ หรือวาง Stream Key เอง
    stream_key = args.key or os.getenv("FB_STREAM_KEY")
    auto_page_choice = args.auto_page

    if not stream_key and not auto_page_choice:
        print("\n📡 เลือกช่องทางเปิดไลฟ์สด (ระบบดึง Stream Key + โพสต์แคปชั่นให้อัตโนมัติ 100%):")
        print("  [1] 🐟 เพจ 1: ป้าเข็ม ปลาสลิดแดดเดียวสุพรรณแท้ (แนะนำ - กด Enter ได้เลย!)")
        print("  [2] 🍳 เพจ 2: ครัวแม่บ้าน ชี้เป้าของอร่อย")
        print("  [3] 🔑 วาง Facebook Stream Key เองจากหน้าเว็บ")
        sel = input("\n👉 เลือก [1/2/3] (หรือกด Enter เพื่อไลฟ์ลงเพจ 1 ทันที): ").strip()
        if not sel or sel == "1":
            auto_page_choice = 1
        elif sel == "2":
            auto_page_choice = 2
        else:
            stream_key = input("👉 วาง Facebook Stream Key ที่นี่: ").strip().strip('"').strip("'")

    if auto_page_choice in (1, 2):
        sys.path.insert(0, str(ROOT / "reels_uploader"))
        from reels_uploader.uploader import configured_pages
        pages = configured_pages()
        if len(pages) < auto_page_choice:
            print("❌ ไม่พบ Token ของเพจที่เลือกในระบบ .env")
            sys.exit(1)
        target_page = pages[auto_page_choice - 1]
        print(f"\n⏳ กำลังสร้างห้องไลฟ์สดอัตโนมัติบนเพจ ID: {target_page['id']} ...")
        live_info = create_auto_facebook_live(target_page["id"], target_page["token"])
        stream_key = live_info.get("clean_stream_url") or live_info.get("stream_url") or live_info.get("secure_stream_url") or ""
        live_id = live_info.get("id", "")
        video_id = live_info.get("video_id") or live_id
        print(f"✅ สร้างห้องไลฟ์สดสำเร็จ! (Live ID: {live_id} | Video ID: {video_id})")
        print(f"🔗 ลิงก์ดูไลฟ์สดบนเพจ: https://www.facebook.com/{target_page['id']}/videos/{video_id}", flush=True)

    if not stream_key:
        print("❌ ต้องระบุ Stream Key จึงจะสามารถสตรีมได้")
        sys.exit(1)

    # 5. กำหนดระยะเวลาการไลฟ์สด (Autopilot Timer)
    duration_minutes = args.minutes or int(args.hours * 60)
    if duration_minutes <= 0 and not args.hours and not args.minutes:
        print("\n⏱️ กำหนดระยะเวลาไลฟ์สด (ระบบจะปิดอัตโนมัติเมื่อครบเวลา):")
        print("  [1] ⭐ ไลฟ์ 2 ชั่วโมง (แนะนำ! ครอบคลุมช่วงคนดูเยอะที่สุด)")
        print("  [2] ไลฟ์ 3 ชั่วโมง")
        print("  [3] ไลฟ์ 4 ชั่วโมง")
        print("  [0] เปิดวนลูปยาวๆ ไม่จำกัดเวลา (ผู้ใช้กด Ctrl+C เพื่อปิดเอง)")
        dur_choice = input("\n👉 เลือก [1/2/3/0] หรือพิมพ์จำนวนชั่วโมง (กด Enter เพื่อเลือก [1] = 2 ชม.): ").strip()
        if not dur_choice or dur_choice == "1":
            duration_minutes = 120
        elif dur_choice == "2":
            duration_minutes = 180
        elif dur_choice == "3":
            duration_minutes = 240
        elif dur_choice == "0":
            duration_minutes = 0
        else:
            try:
                duration_minutes = int(float(dur_choice) * 60)
            except ValueError:
                duration_minutes = 120

    # 6. ทดสอบไฟล์เบื้องต้นก่อนเริ่ม
    test_ok = test_video(ffmpeg_bin, video_path)
    if not test_ok and not args.yes:
        cont = input("⚠️ มีข้อความแจ้งเตือน ต้องการดำเนินการต่อหรือไม่ (y/n)? ").lower()
        if cont != "y":
            sys.exit(0)

    # 7. เริ่มการสตรีม (รองรับทั้งรอบเดียว และโหมดวนรอบอัตโนมัติ 24 ชม. เช้า-บ่าย-เย็น-ดึก)
    cycle = 1
    rest_mins = max(5, args.rest_minutes)

    while True:
        # หากอยู่ในโหมดสร้างห้องอัตโนมัติบนเพจ และไม่ใช่รอบแรก ให้ขอห้องไลฟ์สดใหม่สำหรับรอบถัดไป
        current_stream_key = stream_key
        if auto_page_choice in (1, 2) and cycle > 1:
            print(f"\n⏳ [รอบที่ {cycle}] กำลังสร้างห้องไลฟ์สดใหม่บนเพจ ID: {target_page['id']} ...")
            try:
                live_info = create_auto_facebook_live(target_page["id"], target_page["token"])
                current_stream_key = live_info.get("clean_stream_url") or live_info.get("stream_url") or live_info.get("secure_stream_url") or ""
                live_id = live_info.get("id", "")
                video_id = live_info.get("video_id") or live_id
                print(f"✅ สร้างห้องไลฟ์สดรอบที่ {cycle} สำเร็จ! (Live ID: {live_id} | Video ID: {video_id})")
                print(f"🔗 ลิงก์ดูไลฟ์สดบนเพจ: https://www.facebook.com/{target_page['id']}/videos/{video_id}", flush=True)
            except Exception as e:
                print(f"⚠️ เกิดข้อผิดพลาดในการสร้างห้องไลฟ์รอบที่ {cycle}: {e}")
                print("🔄 จะลองใหม่อีกครั้งใน 60 วินาที...")
                time.sleep(60)
                continue

        if not current_stream_key:
            print("❌ ไม่พบ Stream Key ในการสตรีมรอบนี้")
            break

        print(f"\n{'=' * 65}")
        print(f"🎬 เริ่มต้นการสตรีมรอบที่ {cycle} (ระยะเวลา {duration_minutes} นาที / {duration_minutes/60:.1f} ชม.)")
        print(f"{'=' * 65}")

        start_live_stream(
            ffmpeg_bin=ffmpeg_bin,
            video_path=video_path,
            stream_key=current_stream_key,
            loop=not args.no_loop,
            bitrate=args.bitrate,
            duration_minutes=duration_minutes
        )

        # หากไม่ได้เปิดโหมด auto-cycle หรือไม่ได้กำหนดเวลา ให้จบรอบการทำงานทันที
        if not args.auto_cycle or duration_minutes <= 0:
            break

        # แจ้งเตือนช่วงพักระบบ
        print(f"\n{'=' * 65}")
        print(f"⏸️ [รอบที่ {cycle} จบลงแล้ว] กำลังพักระบบ {rest_mins} นาทีตามนโยบายความปลอดภัย Facebook...")
        print(f"⏰ ระบบจะเริ่มไลฟ์รอบที่ {cycle + 1} ให้อัตโนมัติเมื่อครบเวลาพัก")
        print(f"{'=' * 65}")

        try:
            from tools.telegram_notifier import send_admin_line_notification, send_telegram_sync
            alert_text = f"⏸️ [Facebook Live] สตรีมรอบที่ {cycle} เสร็จสิ้นแล้วจ้า! กำลังพักระบบ {rest_mins} นาที ก่อนเริ่มสตรีมรอบที่ {cycle + 1} ให้อัตโนมัติค่ะ 🐟"
            send_admin_line_notification(alert_text)
            send_telegram_sync(alert_text)
        except Exception:
            pass

        time.sleep(rest_mins * 60)
        cycle += 1


if __name__ == "__main__":
    main()
