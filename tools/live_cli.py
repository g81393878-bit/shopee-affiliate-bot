"""Composable local CLI for the AI Live/OBS test workflow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from obs_controller import DEFAULT_VIDEO_DIR, connect_obs, video_files


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = Path(__file__).resolve().parent / "obs_controller.py"
SHOW = Path(__file__).resolve().parent / "ai_live_show.py"


def emit(value, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        if isinstance(value, str):
            print(value)
        else:
            print(json.dumps(value, ensure_ascii=False, indent=2))


def doctor(as_json: bool) -> int:
    result = {
        "ok": True,
        "command": "live-cli",
        "mode": "local_obs",
        "video_dir": str(DEFAULT_VIDEO_DIR),
        "video_dir_exists": DEFAULT_VIDEO_DIR.exists(),
        "video_count": len(video_files(DEFAULT_VIDEO_DIR)),
        "obsws_python_installed": False,
        "obs_password_available": bool(os.getenv("OBS_PASSWORD")),
        "obs_connection": "not_checked",
    }
    try:
        import obsws_python  # noqa: F401
        result["obsws_python_installed"] = True
    except ImportError:
        result["ok"] = False
        result["missing"] = ["obsws-python"]
    emit(result, as_json)
    return 0 if result["ok"] else 2


def clips(as_json: bool, video_dir: Path) -> int:
    items = [{"name": item.name, "path": str(item), "extension": item.suffix.lower()} for item in video_files(video_dir)]
    emit({"ok": True, "video_dir": str(video_dir), "count": len(items), "clips": items}, as_json)
    return 0


def obs_status(as_json: bool, args: argparse.Namespace) -> int:
    client = connect_obs(args.host, args.port, args.password or os.getenv("OBS_PASSWORD", ""))
    if client is None:
        emit({"ok": False, "host": args.host, "port": args.port, "error": "obs_unreachable_or_auth_failed"}, as_json)
        return 2
    try:
        result = {"ok": True, "host": args.host, "port": args.port, "scene": args.scene}
        emit(result, as_json)
        return 0
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def forward(script: Path, extra: list[str]) -> int:
    return subprocess.call([sys.executable, str(script), *extra], cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(prog="live-cli", description="ควบคุม Local AI Live Show และ OBS")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor", help="ตรวจไฟล์ คลิป dependency และ credential แบบไม่แสดงความลับ")
    doctor_parser.add_argument("--json", action="store_true")

    clips_parser = sub.add_parser("clips", help="แสดงคลิปในคิว")
    clips_parser.add_argument("--json", action="store_true")
    clips_parser.add_argument("--video-dir", type=Path, default=DEFAULT_VIDEO_DIR)

    preview = sub.add_parser("preview", help="ดูคลิปที่จะใช้ โดยไม่เชื่อม OBS")
    preview.add_argument("--video-dir", type=Path, default=DEFAULT_VIDEO_DIR)

    play = sub.add_parser("play", help="เล่นคลิปหนึ่งไฟล์ผ่าน OBS")
    play.add_argument("--file", type=Path)
    play.add_argument("--next", action="store_true")
    play.add_argument("--dry-run", action="store_true")
    play.add_argument("--password")

    show = sub.add_parser("show", help="รัน AI Live Show และสลับคลิปอัตโนมัติ")
    show.add_argument("--seconds", type=int, default=120)
    show.add_argument("--once", action="store_true")

    status = sub.add_parser("obs-status", help="ตรวจการเชื่อมต่อ OBS")
    status.add_argument("--json", action="store_true")
    status.add_argument("--host", default=os.getenv("OBS_HOST", "127.0.0.1"))
    status.add_argument("--port", type=int, default=int(os.getenv("OBS_PORT", "4455")))
    status.add_argument("--scene", default=os.getenv("OBS_SCENE", "Live"))
    status.add_argument("--password")

    args = parser.parse_args()
    if args.command == "doctor":
        return doctor(args.json)
    if args.command == "clips":
        return clips(args.json, args.video_dir)
    if args.command == "preview":
        return forward(CONTROLLER, ["--dry-run", "--video-dir", str(args.video_dir)])
    if args.command == "play":
        extra = []
        if args.file:
            extra += ["--file", str(args.file)]
        if args.next:
            extra += ["--next"]
        if args.dry_run:
            extra += ["--dry-run"]
        return forward(CONTROLLER, extra)
    if args.command == "show":
        extra = ["--seconds", str(args.seconds)]
        if args.once:
            extra += ["--once"]
        return forward(SHOW, extra)
    if args.command == "obs-status":
        return obs_status(args.json, args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
