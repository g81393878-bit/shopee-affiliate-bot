# -*- coding: utf-8 -*-
"""
แคมเปญบอทป้าเข็ม — แยก 2 คำสั่งให้ขาดจากกัน (ไม่ปนกันในรันเดียว)

  post   — โพสต์ "แนะนำป้าเข็ม" ลงเพจ (แคปชั่นอัตโนมัติ + ภาพจาก assets)
           ไม่เปิด browser ไม่แตะกลุ่มเลย
  share  — แชร์ post URL ที่มีอยู่แล้วลงกลุ่มเป้าหมาย (browser + คุกกี้ + dedup + ชีท)
           ไม่โพสต์ ไม่สร้างแคปชั่น

ใช้งาน:
  # 1) โพสต์แนะนำป้าเข็มลงเพจ (ได้ post URL)
  python bot/run_campaign.py post [--caption "..." ] [--poster "D:\\...\\assets"]
  python bot/run_campaign.py post --dry-run        # โชว์แคปชั่น+ภาพ ไม่โพสต์

  # 2) แชร์โพสต์นั้นลงกลุ่ม (ใช้ post URL จากขั้น 1)
  python bot/run_campaign.py share --post-url "https://www.facebook.com/<page>/posts/<id>" \
      --groups-file groups.txt
  python bot/run_campaign.py share --post-url "..." --groups-file groups.txt --dry-run
  python bot/run_campaign.py share --post-url "..." \
      --group-url "https://www.facebook.com/groups/123/,https://www.facebook.com/groups/456/"

  # 3) ดูสถานะกลุ่ม: กลุ่มไหนเขียว (แชร์สำเร็จ) / แดง (ล้ม) / โดน blacklist
  python bot/run_campaign.py status

ประวัติกลุ่มถูกบันทึกใน state file (ledger: สำเร็จ/ล้ม/จำนวนครั้ง) — กลุ่มที่แชร์ล้ม
ติดต่อกันครบ --fail-threshold (default 2) จะถูกขึ้น blacklist อัตโนมัติ (fb_blacklist.json)
และข้ามถาวรจนกว่าจะลบออกเอง — กันเสียเวลากับกลุ่มที่แอดมินลบโพสต์ซ้ำ ๆ

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
DEFAULT_BLACKLIST_FILE = ROOT / "fb_blacklist.json"


# ===========================================================================
# องค์ประกอบโพสต์: แคปชั่น (ประกอบจากชิ้นส่วน)
# ===========================================================================
def build_caption(line_oa_url: Optional[str] = None) -> str:
    """ประกอบแคปชั่นจากองค์ประกอบย่อย ๆ — แก้จุดขาย/ราคา/CTA ได้จากที่เดียว."""
    line_oa_url = line_oa_url or os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    hook = "อยากใช้บอทช่วยขายของ Shopee (บอทป้าเข็ม) ป้าจัดการระบบให้พร้อมใช้ทันทีจ้า 😊"
    benefits = "🛠️ ปลอดภัยรันบนบัญชี/คีย์คุณเอง แอดมินดูแลหลังบ้านให้หมด ไม่ต้องเซ็ตค่าเองให้ปวดหัวจ้า"
    price_cta = f"💼 เริ่มต้น 490.- แอดไลน์คุยรายละเอียดแพ็กเกจกับป้าเลยจ้า 👉 {line_oa_url}"
    return "\n".join([hook, benefits, price_cta])


# ===========================================================================
# องค์ประกอบโพสต์: ภาพโปสเตอร์ (สุ่มหมุนเวียนจาก assets)
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
# องค์ประกอบแชร์: รายชื่อกลุ่ม + dedup (กันแชร์ซ้ำ)
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


def _load_state(path: Path) -> dict:
    """โหลด ledger กลุ่ม: key → {status, count, fails, last, note} — กันแชร์ซ้ำ + ดูประวัติ."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items()}
        if isinstance(data, list):  # รูปแบบเก่า (list ของ key ที่แชร์สำเร็จ) → แปลงเป็น ledger
            return {str(x): {"status": "ok", "count": 1, "fails": 0,
                             "last": "", "note": "imported (รูปแบบเก่า)"}
                    for x in data}
    except Exception as e:
        print(f"[STATE] อ่าน state file ล้ม (เริ่มใหม่): {e}")
    return {}


def _save_state(path: Path, ledger: dict) -> None:
    """เขียน ledger (JSON dict เรียง key) — best-effort ไม่พังแคมเปญ."""
    try:
        path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8")
    except Exception as e:
        print(f"[STATE] เขียน state file ล้ม: {e}")


def _load_blacklist(path: Path) -> dict:
    """โหลด blacklist กลุ่ม: key → เหตุผล — กลุ่มนี้จะถูกข้ามทุกครั้ง."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        if isinstance(data, list):
            return {str(x): "blacklisted" for x in data}
    except Exception as e:
        print(f"[BLACKLIST] อ่าน blacklist ล้ม (เริ่มใหม่): {e}")
    return {}


def _save_blacklist(path: Path, blacklist: dict) -> None:
    """เขียน blacklist (JSON dict) — best-effort ไม่พังแคมเปญ."""
    try:
        path.write_text(json.dumps(blacklist, ensure_ascii=False, indent=2, sort_keys=True),
                        encoding="utf-8")
    except Exception as e:
        print(f"[BLACKLIST] เขียน blacklist ล้ม: {e}")


# ===========================================================================
# Subcommand: post — โพสต์แนะนำป้าเข็มลงเพจอย่างเดียว (ไม่แตะกลุ่ม)
# ===========================================================================
def _cmd_post(args) -> int:
    caption = args.caption or build_caption()
    poster = resolve_poster_image(args.poster)

    if args.dry_run:
        print("[POST][DRY-RUN] (ไม่โพสต์จริง) จะโพสต์แนะนำป้าเข็ม:")
        print(f"[POST][DRY-RUN] caption:\n{caption}")
        print(f"[POST][DRY-RUN] ภาพ: {poster or '(ไม่มี — ข้อความล้วน)'}")
        print("[POST][DRY-RUN] เสร็จ — ใช้ --dry-run ไม่ได้ post URL (รันจริงเพื่อโพสต์)")
        return 0

    print("[POST] กำลังโพสต์แนะนำป้าเข็มลงเพจ ...")
    res = post_photo(caption, file_path=poster) if poster else post_feed(caption)
    if not res.get("ok"):
        print(f"[ERROR] โพสต์ล้ม: {res.get('error')}")
        return 1
    post_url = f"https://www.facebook.com/{res['post_id']}"
    print(f"[OK] โพสต์แนะนำป้าเข็มสำเร็จ: {post_url}")
    print(f"[NEXT] แชร์ลงกลุ่มต่อ: python bot/run_campaign.py share --post-url \"{post_url}\" "
          f"--groups-file <ไฟล์กลุ่ม>")
    return 0


# ===========================================================================
# Subcommand: share — แชร์ post URL ที่มีอยู่แล้วลงกลุ่มอย่างเดียว (ไม่โพสต์)
# ===========================================================================
def _cmd_share(args) -> int:
    if not args.post_url:
        print("[ERROR] share ต้องระบุ --post-url (URL โพสต์บนเพจที่แชร์ไปยังกลุ่ม)")
        return 2

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
        parser_error = "share ต้องระบุกลุ่มผ่าน --group-name / --group-url / --groups-file"
        print(f"[ERROR] {parser_error}")
        return 2

    # Ledger + blacklist: ข้ามกลุ่มที่แชร์สำเร็จแล้ว + กลุ่มที่โดนขึ้นบัญชีดำ
    state_path = Path(args.state_file)
    blacklist_path = Path(args.blacklist_file)
    ledger = _load_state(state_path)
    blacklist = _load_blacklist(blacklist_path)

    pending = []
    skipped_shared = 0
    skipped_blacklisted = 0
    for (k, is_url, v) in entries:
        if k in blacklist:
            skipped_blacklisted += 1
            print(f"[BLACKLIST] ข้าม '{v}' — {blacklist[k]}")
        elif k in ledger and ledger[k].get("status") == "ok":
            skipped_shared += 1
        else:
            pending.append((k, is_url, v))
    if skipped_shared:
        print(f"[STATE] ข้าม {skipped_shared} กลุ่มที่แชร์สำเร็จแล้ว (จาก ledger)")
    if not pending:
        print("[STATE] ไม่มีกลุ่มที่ต้องแชร์ (แชร์ครบแล้ว / โดน blacklist หมด) → ไม่เปิดเบราว์เซอร์")
        return 0

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

        results = {"ok": 0, "fail": 0, "sheet_ok": 0,
                   "skipped": skipped_shared, "blacklisted": skipped_blacklisted}
        for i, (key, group) in enumerate(resolved, 1):
            print(f"\n👉 [{i}/{len(resolved)}] แชร์โพสต์เพจ → กลุ่ม '{group}'")
            ok, note = share_group.share_post_to_group(
                driver, args.post_url, group, args.caption or "", args.dry_run)

            if args.dry_run:
                print(f"[DRY-RUN] {note} — ไม่บันทึกชีท ไม่เขียน ledger/blacklist (โหมดจำลอง)")
            else:
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                prev = ledger.get(key, {})
                if ok:
                    results["ok"] += 1
                    ledger[key] = {"status": "ok",
                                   "count": prev.get("count", 0) + 1,
                                   "fails": 0, "last": now, "note": note}
                    print(f"[OK] {note}")
                else:
                    results["fail"] += 1
                    fails = prev.get("fails", 0) + 1
                    ledger[key] = {"status": "fail",
                                   "count": prev.get("count", 0) + 1,
                                   "fails": fails, "last": now, "note": note}
                    print(f"[FAIL] {note}")
                    if fails >= args.fail_threshold:
                        blacklist[key] = (f"แชร์ล้ม {fails} ครั้งติด (≥ {args.fail_threshold}) — "
                                          f"{note}")
                        print(f"[BLACKLIST] ขึ้นบัญชีดำ '{group}' อัตโนมัติ "
                              f"(ล้ม {fails} ครั้ง) — ครั้งหน้าไม่ลองอีก "
                              f"(ลบออกจาก {blacklist_path.name} เพื่อลองใหม่)")
                _save_state(state_path, ledger)   # กันแชร์ซ้ำแม้โปรแกรมล้มกลางทาง
                _save_blacklist(blacklist_path, blacklist)
                if share_group._log_to_sheet(
                        share_group._sheet_row(args.post_url, group,
                                               args.caption or "", ok)):
                    results["sheet_ok"] += 1

            if i < len(resolved):
                time.sleep(10)

        print("\n==========================================")
        print(f"โพสต์เพจ: {args.post_url}")
        print(f"สรุป: แชร์สำเร็จ {results['ok']} | ล้ม {results['fail']} | "
              f"บันทึกชีท {results['sheet_ok']} | ข้ามแล้ว {results['skipped']} | "
              f"blacklist {results['blacklisted']}")
        print("ดูประวัติกลุ่ม: python bot/run_campaign.py status")
        print("ตรวจยืนยันด้วยตา: เปิด post_url บนเพจ + เปิดแต่ละกลุ่มดูโพสต์ที่แชร์")
        return 0
    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ===========================================================================
# Main — 2 subcommands แยกกันชัดเจน
# ===========================================================================
def _cmd_status(args) -> int:
    """โชว์ ledger + blacklist: กลุ่มเขียว/แดง/โดนแบน พร้อมเหตุผล."""
    ledger = _load_state(Path(args.state_file))
    blacklist = _load_blacklist(Path(args.blacklist_file))

    print("=== สถานะกลุ่ม (ledger) ===")
    if not ledger:
        print("(ยังไม่มีข้อมูล — รัน share อย่างน้อย 1 ครั้งก่อน)")
    for key in sorted(ledger):
        rec = ledger[key]
        status = rec.get("status", "?")
        mark = "🟢" if status == "ok" else "🔴"
        print(f"{mark} {key}  [{status}] ครั้ง={rec.get('count', 0)} "
              f"ล้ม={rec.get('fails', 0)} ล่าสุด={rec.get('last', '-')}")
        if rec.get("note"):
            print(f"      note: {rec['note']}")

    print("\n=== Blacklist (ข้ามถาวร — ลบ key ออกเพื่อลองกลุ่มนั้นอีกครั้ง) ===")
    if not blacklist:
        print("(ว่าง — ไม่มีกลุ่มโดนขึ้นบัญชีดำ)")
    for key in sorted(blacklist):
        print(f"⛔ {key} — {blacklist[key]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="แคมเปญบอทป้าเข็ม — แยกโพสต์แนะนำป้าเข็ม กับ แชร์กลุ่ม ออกจากกัน")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- post: โพสต์แนะนำป้าเข็มลงเพจ (ไม่แตะกลุ่ม) ---
    p_post = sub.add_parser("post", help="โพสต์แนะนำป้าเข็มลงเพจ (แคปชั่น+ภาพจาก assets)")
    p_post.add_argument("--caption", type=str, default=None,
                        help="แคปชั่นโพสต์ (default = ประกอบอัตโนมัติจาก build_caption)")
    p_post.add_argument("--poster", type=str, default=DEFAULT_POSTER_DIR,
                        help="พาธโฟลเดอร์/ไฟล์ภาพโปสเตอร์ (default โฟลเดอร์ assets)")
    p_post.add_argument("--dry-run", action="store_true",
                        help="จำลอง: โชว์แคปชั่น+ภาพ ไม่โพสต์จริง")
    p_post.set_defaults(func=_cmd_post)

    # --- share: แชร์ post URL ลงกลุ่ม (ไม่โพสต์) ---
    p_share = sub.add_parser("share", help="แชร์ post URL ที่มีอยู่แล้วลงกลุ่มเป้าหมาย")
    p_share.add_argument("--post-url", type=str, default=None,
                         help="URL โพสต์บนเพจที่ต้องการแชร์ (บังคับ)")
    p_share.add_argument("--caption", type=str, default=None,
                         help="แคปชั่นแนบตอนแชร์ (ถ้าใส่ — แชร์พร้อมข้อความ)")
    p_share.add_argument("--group-name", type=str, default=None,
                         help="ชื่อกลุ่มเป้าหมาย (หลายกลุ่มคั่น ,)")
    p_share.add_argument("--group-url", type=str, default=None,
                         help="URL กลุ่มเป้าหมาย (หลาย URL คั่น ,)")
    p_share.add_argument("--groups-file", type=str, default=None,
                         help="ไฟล์รายชื่อกลุ่ม: บรรทัดละ 1 กลุ่ม (ชื่อ หรือ URL, # = คอมเมนต์)")
    p_share.add_argument("--state-file", type=str, default=str(DEFAULT_STATE_FILE),
                         help="ledger กลุ่ม (default fb_shared_state.json)")
    p_share.add_argument("--blacklist-file", type=str, default=str(DEFAULT_BLACKLIST_FILE),
                         help="ไฟล์ blacklist กลุ่ม (default fb_blacklist.json)")
    p_share.add_argument("--fail-threshold", type=int, default=2,
                         help="ล้มติดต่อกันกี่ครั้งถึงขึ้น blacklist (default 2)")
    p_share.add_argument("--cookies", type=str, default=None,
                         help="พาธคุกกี้ (default fb_cookies.json)")
    p_share.add_argument("--dry-run", action="store_true",
                         help="จำลอง: ไม่แชร์ ไม่บันทึกชีท ไม่เขียน ledger/blacklist (ตรวจ locator)")
    p_share.set_defaults(func=_cmd_share)

    # --- status: ดูประวัติกลุ่ม + blacklist ---
    p_status = sub.add_parser("status", help="ดูสถานะกลุ่ม: เขียว/แดง/blacklist")
    p_status.add_argument("--state-file", type=str, default=str(DEFAULT_STATE_FILE),
                          help="ledger กลุ่ม (default fb_shared_state.json)")
    p_status.add_argument("--blacklist-file", type=str, default=str(DEFAULT_BLACKLIST_FILE),
                          help="ไฟล์ blacklist กลุ่ม (default fb_blacklist.json)")
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
