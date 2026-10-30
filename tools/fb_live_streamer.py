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
load_dotenv()


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
    """ค้นหาไฟล์ .mp4 แนะนำในโปรเจกต์"""
    candidates = []
    search_dirs = [Path("image"), Path("artifacts/videos"), Path("artifacts")]
    for sdir in search_dirs:
        if sdir.exists():
            for f in sdir.glob("*.mp4"):
                candidates.append(f)
    return candidates


def prompt_video_choice(candidates: list) -> str:
    """ให้ผู้ใช้เลือกไฟล์วิดีโอหรือพิมพ์/ลากไฟล์ลงมา"""
    print("\n🎥 พบไฟล์วิดีโอในโปรเจกต์ที่พร้อมใช้งาน:")
    for idx, v in enumerate(candidates[:6], 1):
        print(f"  [{idx}] {v.name} ({v.parent})")
    print("  [0] ลากไฟล์วิดีโออื่นมาวาง หรือพิมพ์ Path เอง")

    while True:
        choice = input("\n👉 เลือกหมายเลข [1-6] หรือลากไฟล์มาวาง: ").strip().strip('"').strip("'")
        if not choice:
            continue
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


def start_live_stream(ffmpeg_bin: str, video_path: str, stream_key: str, loop: bool = True, bitrate: str = "3500k"):
    """เริ่มยิงสตรีมเข้า Facebook Live แบบมี Auto-Reconnect"""
    rtmps_url = f"rtmps://live-api-s.facebook.com:443/rtmp/{stream_key}"

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

    print("\n" + "=" * 65)
    print("🚀 เริ่มต้นระบบสตรีมมิ่ง Facebook Live 24/7")
    print(f"   📹 ไฟล์วิดีโอ : {video_path}")
    print(f"   🔄 การวนลูป  : {'เปิดวนลูปไม่รู้จบ (24/7 Loop)' if loop else 'เล่นรอบเดียว'}")
    print(f"   ⚡ บิตเรต     : {bitrate}")
    print("   🔴 สถานะ     : สัญญาณกำลังยิงขึ้นสู่เซิร์ฟเวอร์ Facebook...")
    print("   💡 คำแนะนำ  : กด [Ctrl + C] ในหน้าต่างนี้เพื่อหยุดการสตรีม")
    print("=" * 65 + "\n")

    attempt = 1
    while True:
        try:
            # รัน ffmpeg
            process = subprocess.Popen(cmd)
            return_code = process.wait()

            if return_code == 0:
                print("\n🏁 การสตรีมสิ้นสุดลงตามปกติ")
                break
            else:
                print(f"\n⚠️ สัญญาณสตรีมหลุด (Exit Code: {return_code})")
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
    parser.add_argument("--bitrate", "-b", type=str, default="3500k", help="Bitrate (เช่น 3500k, 4000k)")
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

    # 4. เช็ค Stream Key
    stream_key = args.key or os.getenv("FB_STREAM_KEY")
    if not stream_key:
        print("\n🔑 ไปที่ Facebook Page -> ถ่ายทอดสด (Go Live) -> ซอฟต์แวร์สตรีมมิ่ง -> คัดลอก Stream Key")
        stream_key = input("👉 วาง Facebook Stream Key ที่นี่: ").strip().strip('"').strip("'")

    if not stream_key:
        print("❌ ต้องระบุ Stream Key จึงจะสามารถสตรีมได้")
        sys.exit(1)

    # 5. ทดสอบไฟล์เบื้องต้นก่อนเริ่ม
    test_ok = test_video(ffmpeg_bin, video_path)
    if not test_ok:
        cont = input("⚠️ มีข้อความแจ้งเตือน ต้องการดำเนินการต่อหรือไม่ (y/n)? ").lower()
        if cont != "y":
            sys.exit(0)

    # 6. เริ่มการสตรีม
    start_live_stream(
        ffmpeg_bin=ffmpeg_bin,
        video_path=video_path,
        stream_key=stream_key,
        loop=not args.no_loop,
        bitrate=args.bitrate
    )


if __name__ == "__main__":
    main()
