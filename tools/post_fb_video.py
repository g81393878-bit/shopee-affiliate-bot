#!/usr/bin/env python3
"""tools/post_fb_video.py — โพสต์ MP4 ลงเพจ Facebook (รันครั้งเดียวจากเครื่อง)

ใช้สำหรับคลิปแนะนำตัว/คลิปสินค้าที่เจ้าของทำไว้ในเครื่อง (เช่น assets/*.mp4)
แล้วอยากให้ขึ้นเพจป้าเข็มทันที — ไม่ต้องอัปโหลดไปโฮสต์ก่อน

วิธีใช้:
  # จากไฟล์ในเครื่อง (multipart upload ตรง ๆ)
  python tools/post_fb_video.py --file assets/202608161242.mp4 --caption "แนะนำบอทป้าเข็ม"

  # จาก URL สาธารณะ (ใช้ได้จาก Render/ที่ไหนก็ได้ — ไฟล์ไม่ต้องอยู่เครื่องนี้)
  python tools/post_fb_video.py --url "https://cdn.example.com/clip.mp4" --caption "..."

  # ตรวจก่อน ไม่โพสต์จริง (dry-run)
  python tools/post_fb_video.py --file assets/202608161242.mp4 --caption "..." --dry-run

  # ระบุชื่อวิดีโอ (ไม่บังคับ)
  python tools/post_fb_video.py --file assets/202608161242.mp4 --caption "..." --title "แนะนำบอท"

อ่าน env จาก backend/.env (FACEBOOK_PAGE_ACCESS_TOKEN) อัตโนมัติ

Permission ที่ page token ต้องมี: pages_manage_posts + pages_read_engagement + pages_show_list
(ถ้าขาด จะได้ error 200 "Permissions error" — ไปเพิ่ม scope ใน Meta App แล้วขอ token ใหม่)
"""
import argparse
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(BACKEND, ".env"))

from app.services.facebook_poster import PAGE_ID, post_video  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="โพสต์ MP4 ลงเพจ Facebook")
    ap.add_argument("--file", help="path ไฟล์ .mp4 ในเครื่อง")
    ap.add_argument("--url", help="URL สาธารณะของไฟล์วิดีโอ (แทน --file)")
    ap.add_argument("--caption", default="", help="แคปชันใต้คลิป (รองรับ emoji)")
    ap.add_argument("--title", default="", help="ชื่อวิดีโอ (ไม่บังคับ)")
    ap.add_argument("--dry-run", action="store_true", help="ตรวจก่อน ไม่โพสต์จริง")
    args = ap.parse_args()

    if not args.file and not args.url:
        ap.error("ต้องระบุ --file หรือ --url อย่างใดอย่างหนึ่ง")

    if args.dry_run:
        print("[dry-run] จะโพสต์คลิปลงเพจ Facebook (PAGE_ID=%s)" % PAGE_ID)
        print("[dry-run] file: %s" % (args.file or "-"))
        print("[dry-run] url : %s" % (args.url or "-"))
        print("[dry-run] caption: %s" % args.caption)
        return 0

    res = post_video(
        description=args.caption,
        file_url=args.url or "",
        file_path=args.file or "",
        title=args.title,
    )
    if res["ok"]:
        print("✅ โพสต์สำเร็จ video_id=%s" % res["video_id"])
        print("   ดูคลิป: https://www.facebook.com/%s/videos/%s" % (PAGE_ID, res["video_id"]))
        return 0
    print("❌ โพสต์ไม่สำเร็จ: %s" % res["error"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
