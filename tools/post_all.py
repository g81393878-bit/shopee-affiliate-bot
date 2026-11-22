# -*- coding: utf-8 -*-
"""
post_all.py — ยิงโพสต์ 1 คลิปขึ้น Facebook Reels (2 เพจ)
  • 🔵 Facebook Reels (2 เพจหลัก)
"""
import argparse
import pathlib
import subprocess
import sys

# บังคับ UTF-8 บน Windows Terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
PYTHON_EXE = PROJECT_ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = pathlib.Path(sys.executable)


def resolve_video_path(video_input: str) -> pathlib.Path | None:
    if not video_input:
        return None
    raw = video_input.strip().strip('"').strip("'")
    candidates = [
        pathlib.Path(raw),
        pathlib.Path("D:/") / raw,
        PROJECT_ROOT / "reels_uploader" / "pending_videos" / raw,
        pathlib.Path("D:/คลิปป้าเข็ม") / raw,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c.resolve()

    stem_part = pathlib.Path(raw).stem[:12]
    for folder in [PROJECT_ROOT / "reels_uploader" / "pending_videos", pathlib.Path("D:/")]:
        if folder.exists():
            for f in folder.glob("*.mp4"):
                if (stem_part and stem_part in f.stem) or (f.stem and f.stem in raw) or ("จัดการรีพอ" in f.name and "จัดการรีพอ" in raw):
                    return f.resolve()
    return None


def main():
    parser = argparse.ArgumentParser(description="ยิงโพสต์ 1 คลิปขึ้นทุกแพลตฟอร์มในคำสั่งเดียว")
    parser.add_argument("--video", type=str, default=None, help="พาธหรือชื่อไฟล์วิดีโอ .mp4 ที่ต้องการโพสต์")
    parser.add_argument("--caption", type=str, default=None, help="แคปชั่นวิดีโอ (หากไม่ระบุ ระบบจะใช้ AI สร้างแคปชั่นอัตโนมัติ)")
    args = parser.parse_args()

    v_path = None
    if args.video:
        v_path = resolve_video_path(args.video)
        if not v_path:
            print(f"❌ [FAIL] ไม่พบไฟล์วิดีโอที่ระบุ: {args.video}")
            return 1
        print(f"🎬 คลิปเป้าหมาย: {v_path.name} ({v_path.stat().st_size / (1024*1024):.1f} MB)")
    else:
        pending = sorted((PROJECT_ROOT / "reels_uploader" / "pending_videos").glob("*.mp4"))
        if pending:
            v_path = pending[0]
            print(f"🎯 ดึงคลิปถัดไปจากคลังอัตโนมัติ: {v_path.name} ({v_path.stat().st_size / (1024*1024):.1f} MB)")

    target_caption = args.caption
    if not target_caption and v_path:
        sidecar_txt = v_path.with_suffix(".txt")
        if not sidecar_txt.exists():
            alt_txt = v_path.parent / f"{v_path.stem}.txt"
            if alt_txt.exists():
                sidecar_txt = alt_txt
        if sidecar_txt.exists():
            try:
                target_caption = sidecar_txt.read_text(encoding="utf-8").strip()
                print(f"📄 [Caption] พบไฟล์แคปชั่นคู่ (.txt): {sidecar_txt.name}")
            except Exception:
                pass

    print("\n" + "=" * 65)
    print(" 🚀 เริ่มต้นยิงโพสต์ขึ้น Facebook Reels (All-in-One Master Broadcast)")
    print("   • 🔵 Facebook Reels (2 เพจ)")
    if target_caption:
        preview_cap = target_caption.replace("\n", " ")[:60]
        print(f"   • 📝 แคปชั่น: \"{preview_cap}...\"")
    print("=" * 65 + "\n")

    # 1. FB Reels
    print("👉 กำลังยิงขึ้น Facebook Reels (2 เพจ)...")
    fb_cmd = [str(PYTHON_EXE), str(PROJECT_ROOT / "reels_uploader" / "uploader.py"), "--force"]
    if v_path:
        fb_cmd.extend(["--video", str(v_path)])
    if target_caption:
        fb_cmd.extend(["--caption", target_caption])
    subprocess.run(fb_cmd, cwd=str(PROJECT_ROOT))

    print("\n" + "=" * 65)
    print(" 🎉 ดำเนินการยิงโพสต์ Facebook Reels เรียบร้อยแล้ว!")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
