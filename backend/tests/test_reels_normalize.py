"""เทสต์ normalize_video() ใน uploader.py — แปลงคลิปเป็น 9:16/1080p/30fps อัตโนมัติ

ใช้ ffmpeg ที่ติดมากับ imageio_ffmpeg (มีใน venv แล้ว) สร้างคลิปทดสอบ landscape
แล้ว normalize → ตรวจผลเป็น 1080x1920 (9:16). ไม่แตะ Facebook API / network จริง.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UPLOADER = ROOT / "uploader.py"


def _load_uploader():
    spec = importlib.util.spec_from_file_location("uploader_under_test", UPLOADER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ffmpeg() -> str:
    # imageio_ffmpeg ติดตั้งเฉพาะ venv ท้องถิ่น (ไม่เข้า requirements.txt) —
    # บน CI ไม่มี → skip integration test แทนการ fail
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


def test_normalize_video_missing_src(tmp_path):
    """src ไม่มี → คืน False ไม่ crash (caller ใช้ต้นฉบับแทน)"""
    up = _load_uploader()
    assert up.normalize_video(tmp_path / "nope.mp4", tmp_path / "out.mp4") is False


def test_normalize_video_landscape_to_916(tmp_path):
    """คลิป landscape 640x360 → normalize → 1080x1920 (9:16)"""
    up = _load_uploader()
    ff = _ffmpeg()
    src = tmp_path / "in.mp4"
    dst = tmp_path / "out.mp4"

    # สร้างคลิปทดสอบ landscape 2 วิ (testsrc สร้างในเครื่อง ไม่ใช้ network)
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True,
    )
    assert src.exists()

    assert up.normalize_video(src, dst) is True
    assert dst.exists() and dst.stat().st_size > 0

    # ตรวจ dimension 1080x1920 (ffprobe ไม่ได้ bundle มา → อ่านจาก stderr ของ ffmpeg -i)
    probe = subprocess.run([ff, "-i", str(dst)], capture_output=True, text=True)
    assert "1080x1920" in probe.stderr
