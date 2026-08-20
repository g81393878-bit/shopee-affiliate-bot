# -*- coding: utf-8 -*-
"""
แคมเปญบอทป้าเข็ม — โพสต์ "แนะนำป้าเข็ม" ลงเพจ (แคปชั่นอัตโนมัติ + ภาพจาก assets)
ไม่เปิด browser ไม่แตะกลุ่ม

ใช้งาน:
  python bot/run_campaign.py post [--caption "..." ] [--poster "D:\\...\\assets"]
  python bot/run_campaign.py post --dry-run        # โชว์แคปชั่น+ภาพ ไม่โพสต์

ต้องรันด้วย system python (มี backend deps)
"""
import argparse
import os
import random
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.facebook_poster import post_feed, post_photo, post_comment  # noqa: E402

DEFAULT_POSTER_DIR = r"D:\Shopee_Web_Scraping\assets"


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

    return 0


# ===========================================================================
# Main — โพสต์ลงเพจอย่างเดียว
# ===========================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="แคมเปญบอทป้าเข็ม — โพสต์แนะนำป้าเข็มลงเพจ (ไม่แตะกลุ่ม)")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- post: โพสต์แนะนำป้าเข็มลงเพจ ---
    p_post = sub.add_parser("post", help="โพสต์แนะนำป้าเข็มลงเพจ (แคปชั่น+ภาพจาก assets)")
    p_post.add_argument("--caption", type=str, default=None,
                        help="แคปชั่นโพสต์ (default = ประกอบอัตโนมัติจาก build_caption)")
    p_post.add_argument("--poster", type=str, default=DEFAULT_POSTER_DIR,
                        help="พาธโฟลเดอร์/ไฟล์ภาพโปสเตอร์ (default โฟลเดอร์ assets)")
    p_post.add_argument("--dry-run", action="store_true",
                        help="จำลอง: โชว์แคปชั่น+ภาพ ไม่โพสต์จริง")
    p_post.set_defaults(func=_cmd_post)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
