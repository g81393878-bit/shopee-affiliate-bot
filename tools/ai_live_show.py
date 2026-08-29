"""Local AI Live Show: product clips + transparent AI-host overlay in OBS.

This is a local production/test layer. It does not log in to Shopee or bypass
any platform rules. A human should monitor the show and chat.
"""

from __future__ import annotations

import argparse
import html
import os
import time
from pathlib import Path

from obs_controller import connect_obs, ensure_source, play_file, video_files


ROOT = Path(__file__).resolve().parents[1]
AVATAR = ROOT / "assets" / "pa-khem-avatar.png"
OVERLAY = ROOT / "tools" / "live_overlay.html"
DEFAULT_DIR = ROOT / "reels_uploader" / "pending_videos"


def product_name(video: Path) -> str:
    name = video.stem.replace("_", " ").replace("-", " ")
    return " ".join(name.split())


def write_overlay(video: Path, seconds: int, index: int, total: int) -> None:
    title = html.escape(product_name(video))
    avatar = html.escape(AVATAR.as_uri()) if AVATAR.exists() else ""
    content = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=1080"><style>
*{{box-sizing:border-box}} html,body{{margin:0;padding:0;width:1080px;height:1920px;overflow:hidden;font-family:Arial,sans-serif;color:white;background:transparent}}
.badge{{position:absolute;top:46px;left:42px;background:#7c3aed;border-radius:18px;padding:14px 24px;font-size:27px;font-weight:bold}}
.host{{position:absolute;right:35px;bottom:205px;width:260px;text-align:center}}
.host img{{width:180px;height:180px;object-fit:cover;border-radius:50%;border:6px solid #fff;box-shadow:0 4px 22px #0008}}
.host p{{margin:8px 0;background:#000b;border-radius:12px;padding:9px;font-size:22px}}
.caption{{position:absolute;left:35px;right:35px;bottom:42px;background:#000c;border-radius:18px;padding:18px 24px;font-size:28px;font-weight:bold}}
.small{{font-size:18px;font-weight:normal;color:#ddd}}
</style></head><body>
<div class="badge">AI LIVE • โปรดตรวจสอบข้อมูลก่อนสั่งซื้อ</div>
<div class="host">{"<img src=\"" + avatar + "\"/>" if avatar else ""}<p>ป้าเข็ม AI Host</p></div>
<div class="caption">สินค้าในช่วงนี้: {title}<br><span class="small">ช่วงที่ {index}/{total} • สอบถามได้ในแชต • กดสินค้าที่ปักไว้</span></div>
</body></html>"""
    OVERLAY.write_text(content, encoding="utf-8")


OVERLAY_W = 1080
OVERLAY_H = 1920


def ensure_overlay(client, scene: str) -> None:
    names = {item["inputName"] for item in client.get_input_list().inputs}
    settings = {
        "is_local_file": True,
        "local_file": str(OVERLAY),
        "width": OVERLAY_W,
        "height": OVERLAY_H,
        "reroute_audio": False,
    }
    if "AI Live Overlay" not in names:
        client.create_input(scene, "AI Live Overlay", "browser_source", settings, True)
    else:
        client.set_input_settings("AI Live Overlay", settings, True)
    _reset_overlay_transform(client, scene)


def _reset_overlay_transform(client, scene: str) -> None:
    """Force the overlay browser source to fill the canvas at 100% scale."""
    try:
        item_id = client.get_scene_item_id(scene, "AI Live Overlay").scene_item_id
        client.set_scene_item_transform(scene, item_id, {
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
        print("Overlay transform reset: 0,0 @ 100%")
    except Exception as exc:
        print(f"Warning: could not reset overlay transform: {exc}")


def _reset_video_transform(client, scene: str, source_name: str) -> None:
    """Keep the vertical media source inside the 1080x1920 canvas."""
    try:
        item_id = client.get_scene_item_id(scene, source_name).scene_item_id
        client.set_scene_item_transform(scene, item_id, {
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
        print(f"{source_name} transform reset: 0,0 @ 100%")
    except Exception as exc:
        print(f"Warning: could not reset video transform: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="รัน AI Live Show แบบ Local ผ่าน OBS")
    parser.add_argument("--video-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--seconds", type=int, default=120, help="เวลาแสดงแต่ละคลิป")
    parser.add_argument("--scene", default=os.getenv("OBS_SCENE", "Live"))
    parser.add_argument("--source", default=os.getenv("OBS_SOURCE", "LiveVideo"))
    parser.add_argument("--host", default=os.getenv("OBS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OBS_PORT", "4455")))
    parser.add_argument("--password", default=os.getenv("OBS_PASSWORD", ""))
    parser.add_argument("--once", action="store_true", help="เล่นคลิปเดียวแล้วจบ")
    args = parser.parse_args()
    if args.seconds < 10:
        parser.error("--seconds ต้องไม่น้อยกว่า 10")
    files = video_files(args.video_dir)
    if not files:
        print(f"ไม่พบคลิปใน {args.video_dir}")
        return 2
    client = connect_obs(args.host, args.port, args.password)
    if client is None:
        return 2
    ensure_source(client, args.source, args.scene)
    _reset_video_transform(client, args.scene, args.source)
    ensure_overlay(client, args.scene)
    total = 1 if args.once else len(files)
    for index, video in enumerate(files[:1] if args.once else files, 1):
        write_overlay(video, args.seconds, index, total)
        client.set_input_settings("AI Live Overlay", {
            "local_file": str(OVERLAY),
            "width": OVERLAY_W,
            "height": OVERLAY_H,
        }, True)
        play_file(client, args.source, video)
        # OBS may recenter a media source when its dimensions become available.
        time.sleep(0.35)
        _reset_video_transform(client, args.scene, args.source)
        print(f"[{index}/{total}] {video.name} ({args.seconds}s)")
        if index < total:
            time.sleep(args.seconds)
    print("จบ AI Live Show")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
