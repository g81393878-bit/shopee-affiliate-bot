# -*- coding: utf-8 -*-
"""
แคมเปญบอทป้าเข็ม — สคริปต์เดียวครบวงจร (เอาองค์ประกอบมารวมกัน)

โฟลว์:
  1. สร้างแคปชั่นจากองค์ประกอบ (hook / จุดขาย / ราคา / CTA + ลิงก์ LINE)
  2. สุ่มภาพโปสเตอร์จากโฟลเดอร์ assets (ข้าม avatar/icon)
  3. โพสต์ลงเพจป้าเข็มผ่าน Graph API → ได้ post_url
  4. เปิด browser + ฉีดคุกกี้ Facebook → แชร์ post_url ลงกลุ่มเป้าหมายทีละกลุ่ม
     (ยืนยันผลด้วยการเช็คว่า dialog แชร์ปิด)
  5. บันทึกผลรายกลุ่มลง Google ชีท + เขียน state กันแชร์ซ้ำ

ใช้งาน:
  # ครบวงจรจริง (โพสต์ + แชร์ + บันทึกชีท)
  python bot/run_campaign.py --groups-file groups.txt

  # อ่านกลุ่มจาก CLI (หลาย URL คั่น ,)
  python bot/run_campaign.py --group-url "https://www.facebook.com/groups/123/,https://www.facebook.com/groups/456/"

  # dry-run เฉพาะขั้นแชร์ (ใช้โพสต์ที่มีอยู่แล้ว — ตรวจ locator)
  python bot/run_campaign.py --post-url "https://www.facebook.com/<page>/posts/<id>" \
      --group-url "https://www.facebook.com/groups/123/" --dry-run

  # dry-run เฉพาะขั้นโพสต์ (โชว์แคปชั่น+ภาพ ไม่โพสต์ ไม่เปิด browser)
  python bot/run_campaign.py --groups-file groups.txt --dry-run

ต้องรันด้วย system python (มีทั้ง backend deps + selenium/undetected_chromedriver)
บนเครื่องบ้าน/IP จริง · Chrome version_main=151 · fb_cookies.json ที่ repo root
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "bot"))

from app.services.facebook_poster import post_feed, post_photo  # noqa: E402

import share_group  # noqa: E402  (Selenium: เปิด browser/ฉีดคุกกี้/แชร์/บันทึกชีท)

DEFAULT_POSTER_DIR = r"D:\Shopee_Web_Scraping\assets"
DEFAULT_STATE_FILE = ROOT / "fb_shared_state.json"


# ===========================================================================
# องค์ประกอบที่ 1: แคปชั่น (ประกอบจากชิ้นส่วน)
# ===========================================================================
def build_caption(line_oa_url: Optional[str] = None) -> str:
    """ประกอบแคปชั่นจากองค์ประกอบย่อย ๆ — แก้จุดขาย/ราคา/CTA ได้จากที่เดียว."""
    line_oa_url = line_oa_url or os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    hook = "อยากใช้บอทช่วยขายของ Shopee (บอทป้าเข็ม) ป้าจัดการระบบให้พร้อมใช้ทันทีจ้า 😊"
    benefits = "🛠️ ปลอดภัยรันบนบัญชี/คีย์คุณเอง แอดมินดูแลหลังบ้านให้หมด ไม่ต้องเซ็ตค่าเองให้ปวดหัวจ้า"
    price_cta = f"💼 เริ่มต้น 490.- แอดไลน์คุยรายละเอียดแพ็กเกจกับป้าเลยจ้า 👉 {line_oa_url}"
    return "\n".join([hook, benefits, price_cta])


# ===========================================================================
# องค์ประกอบที่ 2: ภาพโปสเตอร์ (สุ่มหมุนเวียนจาก assets)
# ===========================================================================
def resolve_poster_image(path: Optional[str]) -> Optional[str]:
    """ไฟล์ → ใช้เลย; โฟลเดอร์ → สุ่มภาพ (ข้าม avatar/icon) กันภาพเดิมซ้ำ."""
    if not path:
        return None
    p = Path(path)
    if p.is_file():
        return str(p)
    if p.is_dir():
        images = [f for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp") for f in p.glob(ext)]
        posters = [f for f in images
                   if "avatar" not in f.name.lower() and "icon" not in f.name.lower()]
        if posters:
            chosen = random.choice(posters)
            print(f"[POSTER] เจอภาพโปสเตอร์ {len(posters)} รูป → สุ่มใช้: {chosen.name}")
            return str(chosen)
        return None
    print(f"[WARN] ไม่พบพาธภาพโปสเตอร์: {path}")
    return None


# ===========================================================================
# องค์ประกอบที่ 3: รายชื่อกลุ่ม + dedup (กันแชร์ซ้ำ)
# ===========================================================================
def _entry_key(value: str) -> str:
    """คีย์ dedup: URL → normalize ตัด query/trailing slash; ชื่อ → strip + lowercase."""
    v = value.strip()
    if v.lower().startswith(("http://", "https://")):
        return v.split("?", 1)[0].rstrip("/")
    return v.lower()


def _read_groups_file(path: str) -> list:
    """อ่านไฟล์กลุ่ม: บรรทัดละ 1 กลุ่ม (ชื่อ หรือ URL), ข้ามบรรทัดว่าง + คอมเมนต์ #."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"[ERROR] ไม่พบไฟล์กลุ่ม: {path}")
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def _load_state(path: Path) -> set:
    """โหลด state (กลุ่มที่แชร์สำเร็จแล้ว) — ไฟล์ไม่มี/พัง = เริ่มใหม่."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data}
    except Exception as e:
        print(f"[STATE] อ่าน state file ล้ม (เริ่มใหม่): {e}")
    return set()


def _save_state(path: Path, keys: set) -> None:
    """เขียน state (JSON list เรียง) — best-effort ไม่พังแคมเปญ."""
    try:
        path.write_text(json.dumps(sorted(keys), ensure_ascii=False, indent=2),
                        encoding="utf-8")
    except Exception as e:
        print(f"[STATE] เขียน state file ล้ม: {e}")


# ===========================================================================
# Main
# ===========================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="แคมเปญบอทป้าเข็ม: โพสต์เพจ → แชร์กลุ่ม → บันทึกชีท")
    parser.add_argument("--caption", type=str, default=None,
                        help="แคปชั่นโพสต์ (default = ประกอบอัตโนมัติจาก build_caption)")
    parser.add_argument("--poster", type=str, default=DEFAULT_POSTER_DIR,
                        help="พาธโฟลเดอร์/ไฟล์ภาพโปสเตอร์ (default โฟลเดอร์ assets)")
    parser.add_argument("--post-url", type=str, default=None,
                        help="URL โพสต์บนเพจ (ถ้าระบุ → ข้ามขั้นโพสต์ แชร์เลย)")
    parser.add_argument("--group-name", type=str, default=None,
                        help="ชื่อกลุ่มเป้าหมาย (หลายกลุ่มคั่น ,)")
    parser.add_argument("--group-url", type=str, default=None,
                        help="URL กลุ่มเป้าหมาย (หลาย URL คั่น ,)")
    parser.add_argument("--groups-file", type=str, default=None,
                        help="ไฟล์รายชื่อกลุ่ม: บรรทัดละ 1 กลุ่ม (ชื่อ หรือ URL, # = คอมเมนต์)")
    parser.add_argument("--state-file", type=str, default=str(DEFAULT_STATE_FILE),
                        help="state file กันแชร์ซ้ำ (default fb_shared_state.json)")
    parser.add_argument("--cookies", type=str, default=None,
                        help="พาธคุกกี้ (default fb_cookies.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="จำลอง: ไม่โพสต์ ไม่แชร์ ไม่บันทึกชีท ไม่เขียน state")
    args = parser.parse_args()

    caption = args.caption or build_caption()
    state_path = Path(args.state_file)

    # รวมรายชื่อกลุ่มจากทุกแหล่ง → (key, is_url, value)
    entries = []
    for name in (args.group_name or "").split(","):
        name = name.strip()
        if name:
            entries.append((_entry_key(name), False, name))
    for url in (args.group_url or "").split(","):
        url = url.strip()
        if url:
            entries.append((_entry_key(url), True, url))
    if args.groups_file:
        for value in _read_groups_file(args.groups_file):
            entries.append((_entry_key(value),
                            value.lower().startswith(("http://", "https://")), value))
    if not entries:
        parser.error("ต้องระบุกลุ่มผ่าน --group-name / --group-url / --groups-file")

    # Dedup: ข้ามกลุ่มที่แชร์สำเร็จแล้ว
    state = _load_state(state_path)
    pending = [(k, is_url, v) for (k, is_url, v) in entries if k not in state]
    skipped = len(entries) - len(pending)
    if skipped:
        print(f"[STATE] ข้าม {skipped} กลุ่มที่แชร์สำเร็จแล้ว (จาก state file)")
    if not pending:
        print("[STATE] ไม่มีกลุ่มที่ต้องแชร์ (แชร์ครบแล้ว) → ไม่โพสต์ ไม่เปิดเบราว์เซอร์")
        return 0

    post_url = args.post_url

    # ขั้น 1: โพสต์ลงเพจ
    if not post_url:
        poster = resolve_poster_image(args.poster)
        if args.dry_run:
            print("[POST][DRY-RUN] (ไม่โพสต์จริง) จะโพสต์:")
            print(f"[POST][DRY-RUN] caption:\n{caption}")
            print(f"[POST][DRY-RUN] ภาพ: {poster or '(ไม่มี — ข้อความล้วน)'}")
            print("[POST][DRY-RUN] ไม่มี post URL จากการ dry-run → จบ"
                  " (ถ้าจะ dry-run ขั้นแชร์ ให้ส่ง --post-url มาด้วย)")
            return 0
        print("[POST] กำลังโพสต์ลงเพจป้าเข็ม ...")
        res = post_photo(caption, file_path=poster) if poster else post_feed(caption)
        if not res.get("ok"):
            print(f"[ERROR] โพสต์ล้ม: {res.get('error')}")
            return 1
        post_url = f"https://www.facebook.com/{res['post_id']}"
        print(f"[OK] โพสต์สำเร็จ: {post_url}")

    # ขั้น 2: แชร์ลงกลุ่ม
    cookie_path = Path(args.cookies) if args.cookies else ROOT / "fb_cookies.json"
    print(f"[SHARE] เปิดเบราว์เซอร์ + ฉีดคุกกี้ (แชร์ {len(pending)} กลุ่ม)")
    driver = share_group._launch_driver()
    try:
        if not share_group.inject_cookies(driver, cookie_path):
            print("[ERROR] ตั้งค่าล็อกอิน Facebook ไม่สำเร็จ → ยกเลิก")
            return 1

        # แปลง URL → ชื่อจริง (ฉีดคุกกี้เสร็จแล้วค่อยเปิดอ่านได้)
        resolved = []
        for key, is_url, value in pending:
            if is_url:
                name = share_group._resolve_group_name(driver, value)
                print(f"[GROUP] {value} → '{name}'")
            else:
                name = value
            resolved.append((key, name))

        results = {"ok": 0, "fail": 0, "sheet_ok": 0, "skipped": skipped}
        for i, (key, group) in enumerate(resolved, 1):
            print(f"\n👉 [{i}/{len(resolved)}] แชร์โพสต์เพจ → กลุ่ม '{group}'")
            ok, note = share_group.share_post_to_group(
                driver, post_url, group, caption, args.dry_run)

            if args.dry_run:
                print(f"[DRY-RUN] {note} — ไม่บันทึกชีท ไม่เขียน state (โหมดจำลอง)")
            else:
                if ok:
                    results["ok"] += 1
                    state.add(key)
                    _save_state(state_path, state)  # กันแชร์ซ้ำแม้โปรแกรมล้มกลางทาง
                    print(f"[OK] {note}")
                else:
                    results["fail"] += 1
                    print(f"[FAIL] {note}")
                if share_group._log_to_sheet(
                        share_group._sheet_row(post_url, group, caption, ok)):
                    results["sheet_ok"] += 1

            if i < len(resolved):
                time.sleep(10)

        print("\n==========================================")
        print(f"โพสต์เพจ: {post_url}")
        print(f"สรุป: แชร์สำเร็จ {results['ok']} | ล้ม {results['fail']} | "
              f"บันทึกชีท {results['sheet_ok']} | ข้ามแล้ว {results['skipped']}")
        print("ตรวจยืนยันด้วยตา: เปิด post_url บนเพจ + เปิดแต่ละกลุ่มดูโพสต์ที่แชร์")
        return 0
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
