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

ไม่ระบุ --caption → สร้างแคปชันโปรโมทบอทป้าเข็มให้อัตโนมัติ (เหมือน bot/post_page.py)
อ่าน env จาก backend/.env (FACEBOOK_PAGE_ACCESS_TOKEN) อัตโนมัติ

Permission ที่ page token ต้องมี: pages_manage_posts + pages_read_engagement + pages_show_list
(ถ้าขาด จะได้ error 200 "Permissions error" — ไปเพิ่ม scope ใน Meta App แล้วขอ token ใหม่)
"""
import argparse
import os
import sys

# กัน UnicodeEncodeError (emoji ✅/❌) บน console ฝั่ง Windows ที่ใช้ cp874/850 —
# บังคับ stdout เป็น UTF-8 เสมอ (ถ้า print พังกลางทางจะดูไม่รู้ว่าโพสต์สำเร็จหรือไม่)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(BACKEND, ".env"))

from app.services.facebook_poster import GRAPH_URL, PAGE_ID, configured_pages, post_video, sanitize_post_text  # noqa: E402
from app.services.bot_profile import pick_promo_caption  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="โพสต์ MP4 ลงเพจ Facebook")
    ap.add_argument("--file", help="path ไฟล์ .mp4 ในเครื่อง")
    ap.add_argument("--url", help="URL สาธารณะของไฟล์วิดีโอ (แทน --file)")
    ap.add_argument("--caption", default=None, help="แคปชันใต้คลิป (default = โปรโมทบอทป้าเข็ม)")
    ap.add_argument("--title", default="", help="ชื่อวิดีโอ (ไม่บังคับ)")
    ap.add_argument("--dry-run", action="store_true", help="ตรวจก่อน ไม่โพสต์จริง")
    args = ap.parse_args()

    if not args.file and not args.url:
        ap.error("ต้องระบุ --file หรือ --url อย่างใดอย่างหนึ่ง")

    caption = args.caption if args.caption is not None else pick_promo_caption(advance=not args.dry_run)

    if args.dry_run:
        print("[dry-run] จะโพสต์คลิปลงเพจ Facebook (PAGE_ID=%s)" % PAGE_ID)
        print("[dry-run] file: %s" % (args.file or "-"))
        print("[dry-run] url : %s" % (args.url or "-"))
        print("[dry-run] caption: %s" % caption)
        return 0

    res = post_video(
        description=caption,
        file_url=args.url or "",
        file_path=args.file or "",
        title=args.title,
    )
    ok_any = False
    if res["ok"]:
        ok_any = True
        print("✅ เพจ 1 โพสต์สำเร็จ video_id=%s" % res["video_id"])
        print("   ดูคลิปเพจ 1: https://www.facebook.com/%s/videos/%s" % (PAGE_ID, res["video_id"]))
    else:
        print("❌ เพจ 1 โพสต์ไม่สำเร็จ: %s" % res["error"])

    for p in configured_pages():
        if p["index"] > 1:
            import json
            import httpx
            from app.services.facebook_poster import _auto_post_order_comment, _ensure_top_cta_message
            desc_clean = sanitize_post_text(caption or "")
            if desc_clean:
                desc_clean = _ensure_top_cta_message(desc_clean, p["id"])
            data = {"published": "true", "call_to_action": json.dumps({"type": "MESSAGE_PAGE"})}
            if desc_clean:
                data["description"] = desc_clean
            if (args.title or "").strip():
                data["title"] = (args.title or "").strip()
            files = None
            if args.file:
                with open(args.file, "rb") as fh:
                    v_bytes = fh.read()
                files = {"source": (os.path.basename(args.file), v_bytes, "video/mp4")}
            else:
                data["file_url"] = (args.url or "").strip()
            try:
                kwargs = {"params": {"access_token": p["token"]}, "data": data, "timeout": 180}
                if files:
                    kwargs["files"] = files
                r2 = httpx.post(f"{GRAPH_URL}/{p['id']}/videos", **kwargs)
                b2 = r2.json() if r2.status_code == 200 else {}
                vid2 = b2.get("id") or b2.get("video_id")
                if vid2:
                    ok_any = True
                    _auto_post_order_comment(str(vid2), desc_clean, p["id"], p["token"])
                    print("✅ เพจ %s โพสต์สำเร็จ video_id=%s" % (p["index"], vid2))
                    print("   ดูคลิปเพจ %s: https://www.facebook.com/%s/videos/%s" % (p["index"], p["id"], vid2))
                else:
                    print("❌ เพจ %s โพสต์ไม่สำเร็จ: %s" % (p["index"], r2.text[:200]))
            except Exception as e:
                print("❌ เพจ %s โพสต์ไม่สำเร็จ: %s" % (p["index"], e))

    return 0 if ok_any else 1


if __name__ == "__main__":
    sys.exit(main())
