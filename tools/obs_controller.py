"""Small, safe OBS controller for the local live-video MVP.

This script only controls a local OBS instance through obs-websocket. It does
not log in to Shopee, upload anything, or start a platform livestream.

Install the optional dependency once:
    python -m pip install obsws-python

Examples:
    python tools/obs_controller.py --dry-run
    python tools/obs_controller.py --file "path\to\clip.mp4"
    python tools/obs_controller.py --next

Before connecting, enable OBS WebSocket in Tools > WebSocket Server Settings.
The default port for OBS 28+ is 4455.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO_DIR = DEFAULT_ROOT / "reels_uploader" / "pending_videos"
DEFAULT_SOURCE = "LiveVideo"


def video_files(video_dir: Path) -> list[Path]:
    if not video_dir.exists():
        return []
    return sorted(
        (item for item in video_dir.iterdir() if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS),
        key=lambda item: item.name.casefold(),
    )


def choose_next(files: list[Path], state_file: Path) -> Path | None:
    if not files:
        return None
    previous = state_file.read_text(encoding="utf-8").strip() if state_file.exists() else ""
    for item in files:
        if str(item) == previous:
            continue
        return item
    return files[0]


def save_state(state_file: Path, selected: Path) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(str(selected), encoding="utf-8")


def dry_run(args: argparse.Namespace, selected: Path | None, files: list[Path]) -> int:
    print(f"video_dir: {args.video_dir}")
    print(f"found: {len(files)} video(s)")
    for index, item in enumerate(files, 1):
        marker = " <- selected" if selected and item == selected else ""
        print(f"{index}. {item.name}{marker}")
    if not files:
        print("ไม่พบคลิปใน pending_videos")
    return 0


def connect_obs(host: str, port: int, password: str):
    try:
        import obsws_python as obs
    except ImportError:
        print("ยังไม่มี obsws-python: python -m pip install obsws-python", file=sys.stderr)
        return None
    try:
        return obs.ReqClient(host=host, port=port, password=password, timeout=5)
    except Exception as exc:  # library exposes different exception classes by version
        print(f"เชื่อมต่อ OBS ไม่สำเร็จ: {exc}", file=sys.stderr)
        return None


def ensure_source(client, source_name: str, scene_name: str) -> None:
    inputs = client.get_input_list().inputs
    existing = {item["inputName"] for item in inputs}
    if source_name not in existing:
        client.create_input(
            scene_name,
            source_name,
            "ffmpeg_source",
            {"is_local_file": True, "local_file": "", "looping": False},
            True,
        )


def play_file(client, source_name: str, video: Path) -> None:
    client.set_input_settings(
        source_name,
        {"is_local_file": True, "local_file": str(video), "looping": False},
        True,
    )
    # OBS WebSocket 5 request exposed by obsws-python.
    client.trigger_media_input_action(source_name, "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")


def reset_source_transform(client, source_name: str, scene_name: str, delay: float = 0.35) -> None:
    """Reset a media source after OBS has loaded its dimensions."""
    time.sleep(delay)
    item_id = client.get_scene_item_id(scene_name, source_name).scene_item_id
    client.set_scene_item_transform(scene_name, item_id, {
        "positionX": 0.0,
        "positionY": 0.0,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "rotation": 0.0,
        "alignment": 5,  # OBS_ALIGN_LEFT | OBS_ALIGN_TOP
        "cropLeft": 0.0,
        "cropTop": 0.0,
        "cropRight": 0.0,
        "cropBottom": 0.0,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="ควบคุม Media Source ใน OBS สำหรับทดสอบคลิปไลฟ์")
    parser.add_argument("--video-dir", type=Path, default=DEFAULT_VIDEO_DIR)
    parser.add_argument("--file", type=Path, help="เลือกไฟล์วิดีโอโดยตรง")
    parser.add_argument("--next", action="store_true", help="เลือกคลิปถัดไปจากคิว")
    parser.add_argument("--dry-run", action="store_true", help="แสดงรายการเท่านั้น ไม่เชื่อม OBS")
    parser.add_argument("--source", default=os.getenv("OBS_SOURCE", DEFAULT_SOURCE))
    parser.add_argument("--scene", default=os.getenv("OBS_SCENE", "Live"))
    parser.add_argument("--host", default=os.getenv("OBS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OBS_PORT", "4455")))
    parser.add_argument("--password", default=os.getenv("OBS_PASSWORD", ""))
    parser.add_argument("--state-file", type=Path, default=DEFAULT_ROOT / ".obs_live_state")
    args = parser.parse_args()

    files = video_files(args.video_dir)
    selected = args.file.resolve() if args.file else choose_next(files, args.state_file) if args.next else (files[0] if files else None)
    if selected and not selected.exists():
        print(f"ไม่พบไฟล์: {selected}", file=sys.stderr)
        return 2
    if args.dry_run:
        return dry_run(args, selected, files)
    if selected is None:
        print("ไม่พบคลิป กรุณาใส่ไฟล์ไว้ใน reels_uploader/pending_videos", file=sys.stderr)
        return 2

    client = connect_obs(args.host, args.port, args.password)
    if client is None:
        return 2
    try:
        ensure_source(client, args.source, args.scene)
        play_file(client, args.source, selected)
        reset_source_transform(client, args.source, args.scene)
        save_state(args.state_file, selected)
        print(f"OBS กำลังเล่น: {selected.name}")
        return 0
    except Exception as exc:
        print(f"สั่งงาน OBS ไม่สำเร็จ: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
