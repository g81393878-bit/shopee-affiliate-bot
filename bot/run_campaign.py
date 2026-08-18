# -*- coding: utf-8 -*-
"""
แคมเปญบอทป้าเข็ม — แยก 2 คำสั่งให้ขาดจากกัน (ไม่ปนกันในรันเดียว)

  post   — โพสต์ "แนะนำป้าเข็ม" ลงเพจ (แคปชั่นอัตโนมัติ + ภาพจาก assets)
           ไม่เปิด browser ไม่แตะกลุ่มเลย
  share  — โพสต์ตรงลงกลุ่ม (default, สูตรรูปสะอาด+ลิงก์ในคอมเมนต์) หรือแชร์ post URL
           (--method share) — browser + คุกกี้ + ledger/blacklist + บันทึกชีท

ใช้งาน:
  # 1) โพสต์แนะนำป้าเข็มลงเพจ (ได้ post URL)
  python bot/run_campaign.py post [--caption "..." ] [--poster "D:\\...\\assets"]
  python bot/run_campaign.py post --dry-run        # โชว์แคปชั่น+ภาพ ไม่โพสต์

  # 2) โพสต์ตรงลงกลุ่ม (default — รูปสะอาด + แคปชั่นไร้ลิงก์ + คอมเมนต์แรกวางลิงก์ LINE)
  python bot/run_campaign.py share --groups-file groups.txt
  python bot/run_campaign.py share --groups-file groups.txt --dry-run   # ตรวจ locator
  #    --comment-link ""  → ไม่คอมเมนต์ลิงก์ (ใส่ลิงก์ในแคปชั่นเองได้)
  #    --group-interval 1800 → เว้น 30 นาที/กลุ่ม (คู่มือแนะนำ 15-30 นาที)

  # 2b) แบบเดิม: แชร์ post URL ลงกลุ่ม (ใช้กับ --method share)
  python bot/run_campaign.py share --method share --post-url "https://www.facebook.com/<page>/posts/<id>" \
      --groups-file groups.txt

  # 2c) อัตโนมัติ: ดึงโพสต์เพจที่เพิ่งโพสต์จากคิว (สินค้า/แนะนำบอท/ข่าว/ร้าน) → แชร์ทีละโพสต์
  #     แล้วรายงานสถานะกลับ (ต้อง --token = CRON_TOKEN ของระบบ)
  python bot/run_campaign.py share --method share --from-queue --groups-file groups.txt \
      --token <CRON_TOKEN> [--api-base https://shopee-affiliate-bot-9e9n.onrender.com]

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

from app.services.facebook_poster import post_feed, post_photo, post_comment  # noqa: E402

import share_group  # noqa: E402  (Selenium: เปิด browser/ฉีดคุกกี้/แชร์/บันทึกชีท)

DEFAULT_POSTER_DIR = r"D:\Shopee_Web_Scraping\assets"
DEFAULT_STATE_FILE = ROOT / "fb_shared_state.json"
DEFAULT_BLACKLIST_FILE = ROOT / "fb_blacklist.json"


# ===========================================================================
# องค์ประกอบโพสต์: แคปชั่น (ประกอบจากชิ้นส่วน)
# ===========================================================================
def build_caption() -> str:
    """ประกอบแคปชั่นจากองค์ประกอบย่อย ๆ แบบไม่มีลิงก์ (กลยุทธ์โพสต์คลีนปี 2026)."""
    hook = "อยากใช้บอทช่วยขายของ Shopee (บอทป้าเข็ม) ป้าจัดการระบบให้พร้อมใช้ทันทีจ้า 😊"
    benefits = "🛠️ ปลอดภัยรันบนบัญชี/คีย์คุณเอง แอดมินดูแลหลังบ้านให้หมด ไม่ต้องเซ็ตค่าเองให้ปวดหัวจ้า"
    price_cta = "💼 เริ่มต้น 490.- ปักหมุดรายละเอียดและช่องทางคุยกับป้าไว้ที่คอมเมนต์แรกนะจ๊ะ 👇"
    return "\n".join([hook, benefits, price_cta])


def build_comment_link(line_oa_url: Optional[str] = None) -> str:
    """สร้างข้อความคอมเมนต์ที่มีลิงก์ LINE OA สำหรับปักหมุด."""
    line_oa_url = line_oa_url or os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    return f"รายละเอียดช่องทางการทักแชทคุยกับป้าเข็ม เพื่อติดตั้งระบบบอทช่วยขาย Shopee จ้า 👇\n💬 Line OA: {line_oa_url}"


# ===========================================================================
# แคปชั่นโพสต์กลุ่ม (ตามคู่มือ: ไม่มีลิงก์ + เลี่ยงคำแบล็คลิสต์แอดไลน์/ราคา/สมัคร)
# ===========================================================================
GROUP_CAPTIONS = [
    "แม่ค้าออนไลน์ที่อยากขายของใน Shopee ให้ง่ายขึ้น แวะมาคุยกับป้าเข็มได้นะคะ 😊\n"
    "ป้าช่วยจัดการระบบให้พร้อมใช้ทันที ดูแลหลังบ้านให้หมด ไม่ต้องมานั่งเซ็ตเอง\n"
    "รายละเอียดเพิ่มเติมปักหมุดไว้ที่คอมเมนต์แรกจ้า 👇",
    "ขายของออนไลน์อยู่หรือเปล่าคะ ตอบแชทลูกค้าไม่ทันบ้างไหม 😅\n"
    "ป้าเข็มมีตัวช่วยจัดการให้ สบาย ๆ คุยกันก่อนได้\n"
    "ทักไลน์มาคุยกับป้าได้เลย รายละเอียดอยู่ในคอมเมนต์แรกนะคะ",
    "แวะมาชวนแม่ค้าออนไลน์คุยหน่อยค่า 😊\n"
    "อยากให้ร้านตอบแชทลูกค้าอัตโนมัติ หาคนซื้อให้ ลองคุยกับป้าเข็มดู\n"
    "ค่าขนมป้าเบา ๆ คุยได้เลย ปักหมุดรายละเอียดไว้ที่คอมเมนต์แรกจ้า 👇",
]


def _pick_group_caption(index: int) -> str:
    """หมุนแคปชั่นกลุ่ม (spintax) — ข้อความไม่ซ้ำกันทุกกลุ่มเพราะ Facebook จำ hash
    ข้อความซ้ำ ๆ ข้ามกลุ่มได้ว่าเป็นสแปม (ตามคำแนะนำในคู่มือ)."""
    return GROUP_CAPTIONS[index % len(GROUP_CAPTIONS)]


def _default_comment_link(line_oa_url: Optional[str] = None) -> str:
    """ข้อความคอมเมนต์แรกใต้โพสต์กลุ่ม — ที่นี่แหละที่วางลิงก์ LINE OA (คู่มือข้อ 1)."""
    line_oa_url = line_oa_url or os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    return ("สนใจติดตั้งระบบบอทช่วยขาย พิกัดแอดไลน์คุยกับป้าเข็มตรงนี้ได้เลยจ้า "
            f"👉 {line_oa_url}")


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
    """อ่านไฟล์กลุ่ม: บรรทัดละ 1 กลุ่ม (ชื่อ หรือ URL) + แท็กท้ายบรรทัด
    (#promo/#product หมวด · #safe/#nosafe โพสต์ตรงได้ไหม) — ข้ามบรรทัดว่าง/คอมเมนต์.
    คืน list ของ (value, tags_set)."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"[ERROR] ไม่พบไฟล์กลุ่ม: {path}")
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        tags = {t.lstrip("#").lower() for t in parts if t.startswith("#")}
        value = " ".join(t for t in parts if not t.startswith("#"))
        if value:
            entries.append((value, tags))
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
    comment_text = build_comment_link()

    if args.dry_run:
        print("[POST][DRY-RUN] (ไม่โพสต์จริง) จะโพสต์แนะนำป้าเข็ม:")
        print(f"[POST][DRY-RUN] caption:\n{caption}")
        print(f"[POST][DRY-RUN] comment:\n{comment_text}")
        print(f"[POST][DRY-RUN] ภาพ: {poster or '(ไม่มี — ข้อความล้วน)'}")
        print("[POST][DRY-RUN] เสร็จ — ใช้ --dry-run ไม่ได้ post URL (รันจริงเพื่อโพสต์)")
        return 0

    print("[POST] กำลังโพสต์แนะนำป้าเข็มลงเพจ ...")
    res = post_photo(caption, file_path=poster) if poster else post_feed(caption)
    if not res.get("ok"):
        print(f"[ERROR] โพสต์ล้ม: {res.get('error')}")
        return 1
    post_id = res['post_id']
    post_url = f"https://www.facebook.com/{post_id}"
    print(f"[OK] โพสต์แนะนำป้าเข็มสำเร็จ: {post_url}")

    # วางลิงก์ในคอมเมนต์ทันที
    print("[POST] กำลังโพสต์คอมเมนต์แนบลิงก์...")
    c_res = post_comment(post_id, comment_text)
    if c_res.get("ok"):
        print(f"[OK] คอมเมนต์ลิงก์สำเร็จ: ID {c_res['comment_id']}")
    else:
        print(f"[WARN] คอมเมนต์ลิงก์ล้มเหลว: {c_res.get('error')}")

    print(f"[NEXT] แชร์ลงกลุ่มต่อ: python bot/run_campaign.py share --post-url \"{post_url}\" "
          f"--groups-file <ไฟล์กลุ่ม>")
    return 0


# ===========================================================================
# Subcommand: share — แชร์ post URL ที่มีอยู่แล้วลงกลุ่มอย่างเดียว (ไม่โพสต์)
# ===========================================================================
def _cmd_share(args) -> int:
    # ตรวจอาร์กิวเมนต์ตาม method
    if args.method == "share" and not args.post_url:
        print("[ERROR] --method share ต้องระบุ --post-url (URL โพสต์บนเพจที่จะแชร์)")
        return 2
    if args.method == "direct" and args.post_url:
        print(f"[INFO] โหมด direct โพสต์ตรงลงกลุ่ม (ไม่แชร์จากเพจ) — ไม่ใช้ --post-url={args.post_url}")

    # รวมรายชื่อกลุ่มจากทุกแหล่ง → (key, is_url, value, tags)
    entries = []
    for name in (args.group_name or "").split(","):
        name = name.strip()
        if name:
            entries.append((_entry_key(name), False, name, set()))
    for url in (args.group_url or "").split(","):
        url = url.strip()
        if url:
            entries.append((_entry_key(url), True, url, set()))
    if args.groups_file:
        for value, tags in _read_groups_file(args.groups_file):
            entries.append((_entry_key(value),
                            value.lower().startswith(("http://", "https://")), value, tags))
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
    skipped_unsafe = 0
    for (k, is_url, v, tags) in entries:
        if k in blacklist:
            skipped_blacklisted += 1
            print(f"[BLACKLIST] ข้าม '{v}' — {blacklist[k]}")
        elif k in ledger and ledger[k].get("status") == "ok":
            skipped_shared += 1
        elif args.method == "direct" and "nosafe" in tags and not args.allow_unsafe:
            skipped_unsafe += 1
            print(f"[SKIP] '{v}' — แท็ก #nosafe (กลุ่มสินค้า) โพสต์ตรงเสี่ยงโดนลบ → ข้าม "
                  f"(--allow-unsafe เพื่อบังคับ)")
        else:
            pending.append((k, is_url, v, tags))
    if skipped_shared:
        print(f"[STATE] ข้าม {skipped_shared} กลุ่มที่แชร์สำเร็จแล้ว (จาก ledger)")
    if not pending:
        print("[STATE] ไม่มีกลุ่มที่ต้องแชร์ (แชร์ครบแล้ว / blacklist / #nosafe) → ไม่เปิดเบราว์เซอร์")
        return 0

    # โหมด direct: เตรียมภาพโปสเตอร์ + ข้อความคอมเมนต์แรก (ลิงก์ LINE)
    poster = None
    comment = None
    if args.method == "direct":
        poster = resolve_poster_image(args.poster)
        if args.comment_link is None:
            comment = _default_comment_link()   # default = ลิงก์ LINE OA ลงคอมเมนต์แรก
        elif args.comment_link != "":
            comment = args.comment_link         # ใส่ข้อความเอง
        # ข้อความ "" = ไม่คอมเมนต์ลิงก์ (ใส่ลิงก์ในแคปชั่นเองได้)
        if comment:
            print(f"[COMMENT] จะวางลิงก์ในคอมเมนต์แรก: {comment[:70]}"
                  f"{'...' if len(comment) > 70 else ''}")
        else:
            print("[COMMENT] ปิดคอมเมนต์ลิงก์ (--comment-link \"\") — ต้องมีลิงก์ในแคปชั่นเอง")

    cookie_path = Path(args.cookies) if args.cookies else ROOT / "fb_cookies.json"
    print(f"[SHARE] เปิดเบราว์เซอร์ + ฉีดคุกกี้ (โหมด {args.method}, {len(pending)} กลุ่ม)")
    driver = share_group._launch_driver()
    try:
        if not share_group.inject_cookies(driver, cookie_path):
            print("[ERROR] ตั้งค่าล็อกอิน Facebook ไม่สำเร็จ → ยกเลิก")
            return 1

        # แปลง URL → ชื่อจริง; โหมด direct ต้องได้ URL (เปิดหน้าโพสต์เอง)
        resolved = []
        for key, is_url, value, tags in pending:
            if not is_url:
                if args.method == "direct":
                    print(f"[WARN] โหมด direct ต้องใช้ URL กลุ่ม (เปิดหน้าโพสต์เองได้) "
                          f"— ข้าม '{value}' (แก้ groups.txt เป็น URL)")
                    continue
                resolved.append((key, None, value))
            else:
                name = share_group._resolve_group_name(driver, value)
                print(f"[GROUP] {value} → '{name}'")
                resolved.append((key, value, name))
        if not resolved:
            print("[ERROR] ไม่มีกลุ่มที่รันได้ (โหมด direct ต้องการ URL กลุ่ม)")
            return 1

        results = _share_post_to_groups(
            driver, args, args.post_url, resolved, ledger, blacklist,
            state_path, blacklist_path, poster, comment,
            skipped_shared, skipped_blacklisted, skipped_unsafe)
        return 0
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _share_post_to_groups(driver, args, post_url, resolved, ledger, blacklist,
                          state_path, blacklist_path, poster=None, comment=None,
                          skipped_shared=0, skipped_blacklisted=0, skipped_unsafe=0) -> dict:
    """แชร์ 1 โพสต์ (post_url) ลงกลุ่ม resolved ทั้งหมด — วนกลุ่ม + เว้นระยะ + บันทึก ledger/blacklist/ชีท.

    คืน results dict {ok, fail, sheet_ok, skipped, blacklisted, unsafe} —
    ใช้ทั้ง flow เดิม (share --post-url) และ queue mode (แชร์ทีละโพสต์จากคิว)
    """
    interval = args.group_interval if not args.dry_run else 0
    results = {"ok": 0, "fail": 0, "sheet_ok": 0,
               "skipped": skipped_shared, "blacklisted": skipped_blacklisted,
               "unsafe": skipped_unsafe}
    for i, (key, group_url, group_name) in enumerate(resolved, 1):
        group = group_name or group_url
        comment_ok = True
        if args.method == "direct":
            caption = args.caption or _pick_group_caption(i - 1)
            print(f"\n👉 [{i}/{len(resolved)}] โพสต์ตรงลงกลุ่ม '{group}'")
            if any(u in caption for u in ("http://", "https://")):
                print("[WARN] แคปชั่นมีลิงก์! Admin Assist หลายกลุ่มลบโพสต์ที่มีลิงก์ในตัวโพสต์ "
                      "— คู่มือแนะนำให้ลิงก์อยู่ในคอมเมนต์แรก (--comment-link)")
            ok, comment_ok, note = share_group.post_to_group(
                driver, group_url, caption, poster, comment, args.dry_run)
            if ok and comment and not comment_ok:
                note += " · คอมเมนต์ลิงก์ไม่สำเร็จ (วางเอง)"
        else:  # method share (ปุ่มแชร์จากเพจ — ทางสำรอง)
            caption = args.caption or share_group._default_caption()
            print(f"\n👉 [{i}/{len(resolved)}] แชร์โพสต์เพจ → กลุ่ม '{group}'")
            ok, note = share_group.share_post_to_group(
                driver, post_url, group, caption, args.dry_run)

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
                    blacklist[key] = (f"โพสต์/แชร์ล้ม {fails} ครั้งติด "
                                      f"(≥ {args.fail_threshold}) — {note}")
                    print(f"[BLACKLIST] ขึ้นบัญชีดำ '{group}' อัตโนมัติ "
                          f"(ล้ม {fails} ครั้ง) — ครั้งหน้าไม่ลองอีก "
                          f"(ลบออกจาก {blacklist_path.name} เพื่อลองใหม่)")
            _save_state(state_path, ledger)   # กันแชร์ซ้ำแม้โปรแกรมล้มกลางทาง
            _save_blacklist(blacklist_path, blacklist)
            if share_group._log_to_sheet(
                    share_group._sheet_row(group_url or post_url, group,
                                           caption, ok)):
                results["sheet_ok"] += 1

        if i < len(resolved) and interval > 0:
            print(f"[WAIT] เว้น {interval} วินาที ({interval / 60:.0f} นาที) "
                  f"ก่อนกลุ่มถัดไป (คู่มือแนะนำ 15-30 นาที/กลุ่ม) ...")
            time.sleep(interval)

    print("\n==========================================")
    print(f"สรุป: สำเร็จ {results['ok']} | ล้ม {results['fail']} | "
          f"บันทึกชีท {results['sheet_ok']} | ข้ามแล้ว {results['skipped']} | "
          f"blacklist {results['blacklisted']} | #nosafe ข้าม {results['unsafe']}")
    print("ดูประวัติกลุ่ม: python bot/run_campaign.py status")
    print("ตรวจยืนยันด้วยตา: เปิดแต่ละกลุ่มดูโพสต์ + คอมเมนต์แรกว่ามีลิงก์ครบไหม")
    return results


# ===========================================================================
# Subcommand: share --from-queue — ดึงโพสต์เพจที่เพิ่งโพสต์จากคิว → แชร์ลงกลุ่ม → รายงาน
# ===========================================================================
def _fetch_pending_share_tasks(args) -> list:
    """GET /api/admin/group-shares/pending — คืน [{task_id, post_url, kind, post_id}]"""
    import requests
    url = f"{args.api_base.rstrip('/')}/api/admin/group-shares/pending"
    try:
        r = requests.get(url, params={"token": args.token or ""}, timeout=15)
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[ERROR] ดึงคิวแชร์ไม่สำเร็จ: {e}")
        return []


def _report_share_task(args, task_id, status, note="") -> bool:
    """POST /api/admin/group-shares/{id}/status — รายงาน shared/failed/skipped"""
    import requests
    url = f"{args.api_base.rstrip('/')}/api/admin/group-shares/{task_id}/status"
    try:
        r = requests.post(url, params={"token": args.token or "",
                                       "status": status, "note": note}, timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[WARN] รายงานสถานะงาน {task_id} ไม่สำเร็จ: {e}")
        return False


def _cmd_share_from_queue(args) -> int:
    """--from-queue: ดึงงานแชร์โพสต์เพจค้างจากคิว → แชร์ทีละโพสต์ลงกลุ่ม → รายงานสถานะกลับ.

    ต่างจาก share ปกติ: ไม่ข้ามกลุ่มที่แชร์โพสต์อื่นไปแล้ว (ทุกโพสต์ต้องถึงทุกกลุ่ม)
    """
    tasks = _fetch_pending_share_tasks(args)
    if not tasks:
        print("[QUEUE] ไม่มีงานแชร์ค้างในคิว (โพสต์เพจทั้งหมดแชร์ครบแล้ว)")
        return 0
    print(f"[QUEUE] พบงานแชร์ {len(tasks)} โพสต์: " +
          ", ".join(f"{t['kind']}#{t['task_id']}" for t in tasks))

    # รวมกลุ่มจากทุกแหล่ง (เหมือน share ปกติ) — กรอง blacklist/#nosafe แต่ไม่ข้ามกลุ่มที่แชร์แล้ว
    entries = []
    for name in (args.group_name or "").split(","):
        name = name.strip()
        if name:
            entries.append((_entry_key(name), False, name, set()))
    for url in (args.group_url or "").split(","):
        url = url.strip()
        if url:
            entries.append((_entry_key(url), True, url, set()))
    if args.groups_file:
        for value, tags in _read_groups_file(args.groups_file):
            entries.append((_entry_key(value),
                            value.lower().startswith(("http://", "https://")), value, tags))
    if not entries:
        print("[ERROR] share ต้องระบุกลุ่มผ่าน --group-name / --group-url / --groups-file")
        return 2

    state_path = Path(args.state_file)
    blacklist_path = Path(args.blacklist_file)
    ledger = _load_state(state_path)
    blacklist = _load_blacklist(blacklist_path)
    pending = []
    for (k, is_url, v, tags) in entries:
        if k in blacklist:
            print(f"[BLACKLIST] ข้าม '{v}' — {blacklist[k]}")
        elif args.method == "direct" and "nosafe" in tags and not args.allow_unsafe:
            print(f"[SKIP] '{v}' — แท็ก #nosafe โพสต์ตรงเสี่ยงโดนลบ → ข้าม (--allow-unsafe เพื่อบังคับ)")
        else:
            pending.append((k, is_url, v, tags))
    if not pending:
        print("[STATE] ไม่มีกลุ่มที่แชร์ได้ (blacklist / #nosafe หมด) → ไม่เปิดเบราว์เซอร์")
        return 0

    # โหมด direct: เตรียมภาพโปสเตอร์ + คอมเมนต์แรก (ลิงก์ LINE)
    poster = None
    comment = None
    if args.method == "direct":
        poster = resolve_poster_image(args.poster)
        if args.comment_link is None:
            comment = _default_comment_link()
        elif args.comment_link != "":
            comment = args.comment_link
        if comment:
            print(f"[COMMENT] จะวางลิงก์ในคอมเมนต์แรก: {comment[:70]}")
        else:
            print("[COMMENT] ปิดคอมเมนต์ลิงก์ (--comment-link \"\") — ต้องมีลิงก์ในแคปชั่นเอง")

    cookie_path = Path(args.cookies) if args.cookies else ROOT / "fb_cookies.json"
    print(f"[SHARE] เปิดเบราว์เซอร์ + ฉีดคุกกี้ (โหมด {args.method}, {len(pending)} กลุ่ม, {len(tasks)} โพสต์)")
    driver = share_group._launch_driver()
    try:
        if not share_group.inject_cookies(driver, cookie_path):
            print("[ERROR] ตั้งค่าล็อกอิน Facebook ไม่สำเร็จ → ยกเลิก")
            return 1

        # แปลง URL → ชื่อจริง (ทำครั้งเดียว — กลุ่มชุดเดียวกันทุกโพสต์)
        resolved = []
        for key, is_url, value, tags in pending:
            if not is_url:
                if args.method == "direct":
                    print(f"[WARN] โหมด direct ต้องใช้ URL กลุ่ม — ข้าม '{value}' (แก้ groups.txt เป็น URL)")
                    continue
                resolved.append((key, None, value))
            else:
                name = share_group._resolve_group_name(driver, value)
                print(f"[GROUP] {value} → '{name}'")
                resolved.append((key, value, name))
        if not resolved:
            print("[ERROR] ไม่มีกลุ่มที่รันได้ (โหมด direct ต้องการ URL กลุ่ม)")
            return 1

        total_ok = 0
        for idx, t in enumerate(tasks, 1):
            print(f"\n{'=' * 60}\nงาน {idx}/{len(tasks)}: kind={t.get('kind')} "
                  f"task_id={t.get('task_id')} post={t.get('post_url')}\n{'=' * 60}")
            results = _share_post_to_groups(
                driver, args, t.get("post_url") or "", resolved, ledger, blacklist,
                state_path, blacklist_path, poster, comment)
            ok = results["ok"] > 0
            if ok:
                total_ok += 1
            _report_share_task(args, t.get("task_id"),
                               "shared" if ok else "failed",
                               note=f"โพสต์ {t.get('kind')} — สำเร็จ {results['ok']} กลุ่ม / ล้ม {results['fail']} กลุ่ม")
        print(f"\n[QUEUE] แชร์สำเร็จ {total_ok}/{len(tasks)} โพสต์ (ดูรายละเอียดแต่ละโพสต์ด้านบน)")
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

    # --- share: โพสต์ตรงลงกลุ่ม (default) หรือแชร์ post URL (--method share) ---
    p_share = sub.add_parser("share", help="โพสต์ตรงลงกลุ่ม (รูปสะอาด+ลิงก์ในคอมเมนต์) หรือแชร์ post URL")
    p_share.add_argument("--method", type=str, choices=("direct", "share"), default="direct",
                         help="direct = โพสต์ตรงลงกลุ่ม (default, ตามคู่มือ) | share = แชร์ post URL จากเพจ")
    p_share.add_argument("--post-url", type=str, default=None,
                         help="URL โพสต์บนเพจ (ใช้กับ --method share เท่านั้น)")
    p_share.add_argument("--poster", type=str, default=DEFAULT_POSTER_DIR,
                         help="พาธโฟลเดอร์/ไฟล์ภาพโปสเตอร์แนบโพสต์กลุ่ม (default โฟลเดอร์ assets)")
    p_share.add_argument("--comment-link", type=str, default=None,
                         help="ข้อความคอมเมนต์แรกวางลิงก์ใต้โพสต์ (default = ลิงก์ LINE OA; "
                              "ใส่ '' = ไม่คอมเมนต์ลิงก์)")
    p_share.add_argument("--group-interval", type=int, default=900,
                         help="เว้นระยะระหว่างกลุ่ม (วินาที, default 900 = 15 นาที — "
                              "คู่มือแนะนำ 15-30 นาที; dry-run = 0 อัตโนมัติ)")
    p_share.add_argument("--allow-unsafe", action="store_true",
                         help="โพสต์ตรงลงกลุ่มที่แท็ก #nosafe ด้วย (ข้ามไปก่อนโดย default)")
    p_share.add_argument("--caption", type=str, default=None,
                         help="แคปชั่นโพสต์กลุ่ม (direct: default = หมุนอัตโนมัติ 3 แบบไร้ลิงก์; "
                              "ใส่เองได้ แต่เตือนถ้ามีลิงก์)")
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
    p_share.add_argument("--from-queue", action="store_true",
                         help="ดึงโพสต์เพจที่เพิ่งโพสต์จากคิว (/api/admin/group-shares/pending) "
                              "→ แชร์ทีละโพสต์ลงกลุ่ม แล้วรายงานสถานะกลับ (ใช้ --method share เสมอ)")
    p_share.add_argument("--api-base", type=str,
                         default="https://shopee-affiliate-bot-9e9n.onrender.com",
                         help="ฐาน URL ระบบ (ใช้กับ --from-queue)")
    p_share.add_argument("--token", type=str, default=None,
                         help="token แอดมิน = CRON_TOKEN (ใช้กับ --from-queue)")
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
    if getattr(args, "from_queue", False):
        if args.method != "share":
            print("[ERROR] --from-queue ใช้กับ --method share เท่านั้น (แชร์โพสต์เพจจากคิว)")
            return 2
        if not args.token:
            print("[ERROR] --from-queue ต้องระบุ --token (CRON_TOKEN ของระบบ)")
            return 2
        return _cmd_share_from_queue(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
