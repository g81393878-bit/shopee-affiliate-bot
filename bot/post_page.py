# -*- coding: utf-8 -*-
"""
บอทโพสต์ลงเพจป้าเข็ม (Graph API) — แยกส่วน: โพสต์อย่างเดียว ไม่แชร์ ไม่บันทึกชีท
สร้างแคปชั่นโปรโมท + แนบภาพโปสเตอร์จากโฟลเดอร์ assets (หมุนเวียนทีละภาพ)
คืน URL โพสต์ทาง stdout + เขียนลง --out-file (ให้บอทแชร์ share_group.py เอาไปใช้ต่อ)

ใช้งาน:
  python bot/post_page.py                                   # โพสต์โปรโมท default + รูปจาก assets
  python bot/post_page.py --poster "D:\\path\\poster.png"    # ระบุไฟล์ภาพเฉพาะ
  python bot/post_page.py --caption "ข้อความ" --image-url "https://.../poster.jpg"
  python bot/post_page.py --out-file post_url.txt           # เก็บ URL ไว้ต่อกับบอทแชร์
  python bot/post_page.py --dry-run                         # จำลอง ไม่โพสต์จริง
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_POSTER_DIR = r"D:\Shopee_Web_Scraping\assets"

# state จำภาพโปสเตอร์ล่าสุด (หมุนเวียนไม่ซ้ำจนกว่าจะครบทุกภาพ)
_POSTER_STATE = ROOT / "backend" / ".promo_poster_state.json"


def _load_env():
    """โหลด backend/.env เข้า os.environ — ไม่ทับค่าที่ตั้งไว้แล้ว"""
    env_path = ROOT / "backend" / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

sys.path.insert(0, str(ROOT / "backend"))
from app.services.facebook_poster import post_feed, post_photo  # noqa: E402
from app.services.bot_profile import pick_promo_caption  # noqa: E402


def _read_poster_state() -> Optional[str]:
    try:
        return json.loads(_POSTER_STATE.read_text(encoding="utf-8")).get("name")
    except Exception:
        return None


def _write_poster_state(name: str) -> None:
    try:
        _POSTER_STATE.write_text(json.dumps({"name": name}), encoding="utf-8")
    except Exception:
        pass


def resolve_poster_image(path: Optional[str], advance: bool = True) -> Optional[str]:
    """หาไฟล์ภาพโปสเตอร์: เป็นไฟล์ → ใช้เลย; เป็นโฟลเดอร์ → หมุนเวียนทีละภาพ (ข้าม avatar/icon).

    advance=True (โพสต์จริง) เลื่อนไปภาพถัดไป; advance=False (dry-run) แค่ดูภาพที่จะใช้ถัดไป.
    """
    if not path:
        return None
    p = Path(path)
    if p.is_file():
        return str(p)
    if p.is_dir():
        images = [f for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp") for f in p.glob(ext)]
        posters = sorted([f for f in images
                          if "avatar" not in f.name.lower() and "icon" not in f.name.lower()],
                         key=lambda f: f.name)
        if posters:
            state_name = _read_poster_state()
            idx = 0
            if state_name:
                for i, f in enumerate(posters):
                    if f.name == state_name:
                        idx = i
                        break
            chosen = posters[idx]
            if advance:
                _write_poster_state(posters[(idx + 1) % len(posters)].name)
            print(f"[POSTER] เจอภาพโปสเตอร์ {len(posters)} รูป → ใช้: {chosen.name}")
            return str(chosen)
        return None
    print(f"[WARN] ไม่พบพาธภาพโปสเตอร์: {path}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="โพสต์ลงเพจป้าเข็ม (Graph API) — โพสต์อย่างเดียว")
    parser.add_argument("--caption", type=str, default=None, help="เนื้อหาโพสต์ (default = โปรโมทบอทป้าเข็ม)")
    parser.add_argument("--poster", type=str, default=DEFAULT_POSTER_DIR,
                        help="พาธโฟลเดอร์/ไฟล์ภาพโปสเตอร์ (default โฟลเดอร์ assets)")
    parser.add_argument("--image-url", type=str, default=None,
                        help="URL รูปแนบ (ใช้เมื่อไม่มี --poster)")
    parser.add_argument("--out-file", type=str, default=None, help="เขียน URL โพสต์ลงไฟล์ (ให้บอทแชร์ใช้ต่อ)")
    parser.add_argument("--dry-run", action="store_true", help="จำลอง: ไม่โพสต์จริง")
    args = parser.parse_args()

    caption = args.caption or pick_promo_caption(advance=not args.dry_run)
    poster = resolve_poster_image(args.poster, advance=not args.dry_run)

    if args.dry_run:
        print("[DRY-RUN] (โหมดจำลอง — ไม่โพสต์ลงเพจจริง)")
        print(f"[DRY-RUN] caption:\n{caption}")
        print(f"[DRY-RUN] ภาพ: {poster or args.image_url or '(ไม่มี — โพสต์ข้อความล้วน)'}")
        post_url = ""
    else:
        print("[POST] กำลังโพสต์ลงเพจป้าเข็ม ...")
        if poster:
            res = post_photo(caption, file_path=poster)
        elif args.image_url:
            res = post_photo(caption, image_url=args.image_url)
        else:
            res = post_feed(caption)
        if not res.get("ok"):
            print(f"[ERROR] โพสต์ล้ม: {res.get('error')}")
            return 1
        post_url = f"https://www.facebook.com/{res['post_id']}"
        print(f"[OK] โพสต์สำเร็จ: {post_url}")

    if post_url:
        print(f"POST_URL={post_url}")
        if args.out_file:
            Path(args.out_file).write_text(post_url + "\n", encoding="utf-8")
            print(f"[OUT] เขียน URL ลง {args.out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
