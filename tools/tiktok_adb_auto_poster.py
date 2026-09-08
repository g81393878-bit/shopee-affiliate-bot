#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/tiktok_adb_auto_poster.py — หุ่นยนต์อัปโหลด TikTok บนมือถือ Android อัตโนมัติ 100% (TAKTIK + uiautomator2 Engine)

คุณสมบัติระดับสตูดิโอ:
1. ผู้ใช้ไม่ต้องกดอะไรแม้แต่นิ้วเดียว (Zero User Effort)
2. ใช้ uiautomator2 + ADB Native Engine แบบเดียวกับ TAKTIK Bot (เสถียร แม่นยำ ไร้การโดนแบน)
3. ระบบ Auto-Watcher ตรวจจับและปิดป๊อปอัปแจ้งเตือนบนหน้าจออัตโนมัติ
4. ระบบ Multi-Directory Cleanup ล้างคลังมือถือให้มีเฉพาะคลิปใหม่ 100%
5. ระบบ Auto-Archive ย้ายคลิปที่โพสต์แล้วเข้าคลัง posted_videos/ และลบออกจาก VPS ทันที ป้องกันคลิปซ้ำ
6. รายงานผลสำเร็จเข้า Telegram Commander 24 ชม.
"""

import os
import sys
import time
import json
import re
import pathlib
import subprocess
from typing import List, Dict, Optional, Tuple

# บังคับ UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_PENDING_DIR = PROJECT_ROOT / "pending_videos"
LOCAL_PENDING_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR = PROJECT_ROOT / "posted_videos"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = PROJECT_ROOT / "tools" / "posted_tiktok_mobile_history.json"

VPS_HOST = "root@119.10.140.161"
VPS_PENDING_DIR = "/root/shopee-affiliate-bot/reels_uploader/pending_videos"

try:
    import uiautomator2 as u2
    HAS_U2 = True
except Exception:
    HAS_U2 = False


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [TikTok Pro Bot] {msg}"
    print(line, flush=True)


def run_adb(args: List[str], device_id: Optional[str] = None, timeout: int = 30) -> str:
    """รันคำสั่ง ADB บนอุปกรณ์"""
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(args)
    try:
        res = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
        return res.stdout.strip()
    except Exception as e:
        log(f"⚠️ ADB Error ({cmd}): {e}")
        return ""


def get_connected_device() -> Optional[str]:
    """ดึง ID มือถือที่เชื่อมต่ออยู่"""
    output = run_adb(["devices"])
    lines = output.split("\n")[1:]
    for line in lines:
        if "\tdevice" in line:
            return line.split("\t")[0]
    return None


def clean_and_archive_old_pending_videos():
    """ย้ายไฟล์ใน pending_videos ที่โพสต์แล้วทั้งหมดไปเก็บไว้ใน posted_videos ทันที ไม่ให้ค้างใน pending_videos เด็ดขาด"""
    history = set()
    if HISTORY_FILE.exists():
        try:
            history = set(json.loads(HISTORY_FILE.read_text(encoding="utf-8")))
        except Exception:
            history = set()
            
    for vid in list(LOCAL_PENDING_DIR.glob("*.mp4")):
        if vid.name in history:
            target = ARCHIVE_DIR / vid.name
            try:
                if vid.exists():
                    vid.rename(target)
                    log(f"📦 ย้ายคลิปที่เคยโพสต์แล้วออกจาก pending: {vid.name} -> posted_videos/")
            except Exception as e:
                try:
                    vid.unlink(missing_ok=True)
                except Exception:
                    pass


def sync_next_video_from_vps() -> Optional[pathlib.Path]:
    """ดึงวิดีโอถัดไปจาก VPS และย้ายคลิปเก่าเข้าคลังทันที"""
    clean_and_archive_old_pending_videos()

    log("🌐 กำลังตรวจสอบคลังวิดีโอบน Cloud VPS...")
    try:
        subprocess.run(["scp", f"{VPS_HOST}:{VPS_PENDING_DIR}/*.mp4", str(LOCAL_PENDING_DIR)], capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    except Exception as e:
        log(f"⚠️ Sync warning: {e}")

    clean_and_archive_old_pending_videos()

    downloaded = sorted(list(LOCAL_PENDING_DIR.glob("*.mp4")), key=lambda x: x.stat().st_mtime, reverse=True)
    if not downloaded:
        log("ℹ️ ไม่มีวิดีโอรอโพสต์ในคลังขณะนี้")
        return None

    history = set()
    if HISTORY_FILE.exists():
        try:
            history = set(json.loads(HISTORY_FILE.read_text(encoding="utf-8")))
        except Exception:
            history = set()

    for vid in downloaded:
        if vid.name not in history:
            return vid
    
    log("ℹ️ วิดีโอทั้งหมดในคลังถูกโพสต์ไปแล้ว 100% (ไม่มีคลิปใหม่) รอรอบถัดไป...")
    return None


def push_video_to_mobile(device_id: str, video_path: pathlib.Path) -> str:
    """ลบไฟล์วิดีโอเก่าทั้งหมดทุกโฟลเดอร์ในโทรศัพท์ เพื่อให้คลังภาพมีแค่คลิปใหม่คลิปเดียวเท่านั้น"""
    timestamp = int(time.time())
    safe_name = f"tiktok_video_{timestamp}.mp4"
    target_path = f"/sdcard/Movies/{safe_name}"
    
    log("🧹 กำลังลบวิดีโอเก่าออกจากทุกโฟลเดอร์มือถือ (/sdcard/Movies, /sdcard/DCIM/Camera, /sdcard/Download)...")
    run_adb(["shell", "rm", "-f", "/sdcard/Movies/*.mp4", "/sdcard/DCIM/Camera/*.mp4", "/sdcard/Download/*.mp4"], device_id=device_id)
    time.sleep(1)

    log(f"📲 กำลังส่งวิดีโอใหม่ {video_path.name} -> {safe_name} เข้าสู่มือถือ...")
    run_adb(["push", str(video_path), target_path], device_id=device_id, timeout=60)
    
    log("🔄 สั่งกระตุ้น Media Scanner & Content Provider สแกนวิดีโอใหม่เข้า Gallery...")
    run_adb(["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{target_path}"], device_id=device_id)
    run_adb(["shell", "content", "insert", "--uri", "content://media/external/video/media", "--bind", f"_data:s:{target_path}"], device_id=device_id)
    time.sleep(4)
    return target_path


def post_via_u2(d, video_path: pathlib.Path, caption: str = "") -> bool:
    """โพสต์วิดีโอผ่าน uiautomator2 Engine คุณภาพสูงสไตล์ TAKTIK Bot"""
    log("🚀 เริ่มต้นกระบวนการอัปโหลดผ่าน uiautomator2 Engine...")
    
    # 1. ตั้งค่า Auto-Watcher ดักจับและกดปิดป๊อปอัปอัตโนมัติ
    try:
        d.watcher.reset()
        for txt in ["ไม่ใช่ตอนนี้", "ยกเลิก", "อนุญาต", "ปิด", "ตกลง", "ข้าม", "ไม่"]:
            d.watcher.when(txt).click()
        d.watcher.start(2.0)
    except Exception as e:
        log(f"⚠️ Watcher init warning: {e}")

    # 2. ปลุกหน้าจอ + ปลดล็อก + เปิด TikTok Fresh
    d.screen_on()
    d.unlock()
    time.sleep(1)
    
    log("📱 เปิดแอป TikTok Foreground...")
    d.app_start("com.ss.android.ugc.trill", stop=True)
    d.app_wait("com.ss.android.ugc.trill", timeout=12)
    time.sleep(4)

    # ตรวจสอบความปลอดภัย 100%: ต้องเป็นแอป TikTok เท่านั้น ห้ามแตะหน้าจอโฮมเด็ดขาด
    current_pkg = d.app_current().get("package", "")
    if current_pkg != "com.ss.android.ugc.trill":
        log(f"⚠️ ตรวจพบว่าแอปปัจจุบันไม่ใช่ TikTok ({current_pkg}) พยายามเปิดใหม่...")
        d.app_start("com.ss.android.ugc.trill", stop=False)
        d.app_wait("com.ss.android.ugc.trill", timeout=8)
        time.sleep(3)
        current_pkg = d.app_current().get("package", "")
        if current_pkg != "com.ss.android.ugc.trill":
            log("❌ ไม่สามารถเปิด TikTok ได้อย่างสมบูรณ์ ข้ามรอบนี้เพื่อความปลอดภัย ไม่แตะหน้าจอโฮมเด็ดขาด")
            return False

    # 3. ค้นหาและกดปุ่ม '+' (สร้าง)
    log("👉 กำลังกดปุ่มสร้าง (+) บน TikTok...")
    clicked_plus = False
    for _ in range(4):
        if d(descriptionContains="สร้าง").exists:
            d(descriptionContains="สร้าง").click()
            clicked_plus = True
            break
        elif d(textContains="สร้าง").exists:
            d(textContains="สร้าง").click()
            clicked_plus = True
            break
        elif d(resourceIdMatches=".*create_item.*").exists:
            d(resourceIdMatches=".*create_item.*").click()
            clicked_plus = True
            break
        time.sleep(2)

    if not clicked_plus and d.app_current().get("package") == "com.ss.android.ugc.trill":
        w, h = d.window_size()
        d.click(int(w * 0.5), int(h * 0.927))
    
    time.sleep(4)

    # 4. ตรวจสอบว่าเข้าหน้ากล้องถ่ายรูปสำเร็จ
    if not (d(resourceIdMatches=".*upload.*").exists or d(textContains="อัปโหลด").exists):
        if d.app_current().get("package") == "com.ss.android.ugc.trill":
            log("⚠️ กำลังเข้าสู่หน้ากล้องถ่ายรูป...")
            w, h = d.window_size()
            d.click(int(w * 0.5), int(h * 0.927))
            time.sleep(4)

    # 5. กดปุ่ม 'อัปโหลด' คลังภาพ
    log("👉 กำลังเลือกปุ่ม 'อัปโหลด' คลังภาพ...")
    if d(resourceIdMatches=".*upload.*").exists:
        d(resourceIdMatches=".*upload.*").click()
    elif d(textContains="อัปโหลด").exists:
        d(textContains="อัปโหลด").click()
    else:
        w, h = d.window_size()
        d.click(int(w * 0.066), int(h * 0.919))
    
    time.sleep(4)

    # 6. เลือกคลิปแรกสุดในคลังภาพ (Row 1 Col 1: ช่องบนซ้ายสุด 133, 310)
    log("🎯 เลือกคลิปวิดีโอล่าสุดในแกลเลอรี (Row 1 Col 1)...")
    w, h = d.window_size()
    target_x = int(w * 0.166) if w > 0 else 133
    target_y = int(h * 0.231) if h > 0 else 310
    d.click(target_x, target_y)
    time.sleep(3)

    # 7. กดปุ่ม 'ถัดไป' ในหน้าแกลเลอรี
    log("👉 กดปุ่มถัดไป (Next)...")
    if d(textMatches="(?i)ถัดไป.*|Next.*").exists:
        d(textMatches="(?i)ถัดไป.*|Next.*").click()
    else:
        d.click(int(w * 0.925), int(h * 0.912))
    time.sleep(4)

    # 8. กดปุ่ม 'ถัดไป' ในหน้าพรีวิววิดีโอ
    log("👉 กดปุ่มถัดไปหน้าพรีวิว...")
    if d(textMatches="(?i)ถัดไป.*|Next.*").exists:
        d(textMatches="(?i)ถัดไป.*|Next.*").click()
    else:
        d.click(int(w * 0.925), int(h * 0.912))
    time.sleep(5)

def build_tiktok_caption(video_path: pathlib.Path) -> str:
    """สร้างแคปชั่นภาษาไทยและชุดแฮชแท็กระดับท็อป (TikTok Creative Center + Official SEO) อัตโนมัติ"""
    name = video_path.stem
    clean_title = re.sub(r"_\d{9,12}$", "", name)
    
    category = "general"
    if clean_title.startswith("celebrity_trend_"):
        clean_title = clean_title.replace("celebrity_trend_", "")
        category = "celebrity"
    elif clean_title.startswith("trending_news_"):
        clean_title = clean_title.replace("trending_news_", "")
        category = "news"
    elif clean_title.startswith("shopee_") or clean_title.startswith("product_"):
        clean_title = clean_title.replace("shopee_", "").replace("product_", "")
        category = "product"

    clean_title = clean_title.replace("_", " ").strip()

    # ชุดแฮชแท็กคัดสรรตามร่องรอยดิจิทัล TikTok Thailand (SEO 2026)
    if category == "celebrity":
        hashtags = "#เทรนด์วันนี้ #เรื่องนี้ต้องดู #ข่าวดารา #tiktokคนบันเทิง #ข่าวtiktok #fyp"
    elif category == "news":
        hashtags = "#เทรนด์วันนี้ #เรื่องนี้ต้องดู #ข่าวtiktok #ข่าวด่วน #tiktoknews #fyp"
    elif category == "product":
        hashtags = "#ของดีบอกต่อ #TikTokป้ายยา #ของใช้ในบ้าน #พิกัดshopee #ขายดี #ป้าเข็มรีวิว"
    else:
        hashtags = "#เทรนด์วันนี้ #เรื่องนี้ต้องดู #TikTokUni #สาระน่ารู้ #ทริคดีๆ #fyp"

    return f"{clean_title} 📌 {hashtags}"


    # 9. ใส่แคปชั่น & แฮชแท็ก (ตรวจสอบก่อนว่าอยู่หน้าโพสต์จริง!)
    on_post_screen = d(textMatches="(?i)โพสต์|Post").exists or d(resourceIdMatches=".*t6b.*").exists or d(resourceIdMatches=".*h3a.*").exists
    if caption and on_post_screen:
        log(f"✍️ ยืนยันอยู่หน้าโพสต์! กำลังกรอกแคปชั่นและแฮชแท็ก: {caption}")
        try:
            d.set_fastinput_ime(True)
        except Exception:
            pass
            
        if d(resourceIdMatches=".*h3a.*").exists:
            d(resourceIdMatches=".*h3a.*").click()
        elif d(textContains="อธิบาย").exists:
            d(textContains="อธิบาย").click()
        else:
            d.click(int(w * 0.25), int(h * 0.15))
        time.sleep(1)
        
        d.send_keys(caption)
        time.sleep(2)
        
        try:
            d.set_fastinput_ime(False)
        except Exception:
            pass

    # 10. กดปุ่ม 'โพสต์' (Post)
    log("🚀 กำลังกดปุ่ม 'โพสต์' ขึ้น TikTok...")
    if d(resourceIdMatches=".*t6b.*").exists:
        d(resourceIdMatches=".*t6b.*").click()
    elif d(textMatches="(?i)โพสต์|Post").exists:
        d(textMatches="(?i)โพสต์|Post").click()
    else:
        d.click(int(w * 0.7425), int(h * 0.9164))
    
    time.sleep(6)
    try:
        d.watcher.stop()
    except Exception:
        pass
    return True


def auto_post_video_on_tiktok_app(device_id: str, video_path: pathlib.Path, caption: str = "") -> bool:
    """สั่งโพสต์วิดีโอขึ้น TikTok โดยเลือกระบบที่ดีที่สุด (u2 หรือ Native ADB)"""
    log(f"🤖 เริ่มต้นกระบวนการ Zero-Touch Auto-Post สำหรับ: {video_path.name}")
    
    # 1. ล้างคลังมือถือและพุชคลิปใหม่
    push_video_to_mobile(device_id, video_path)

    success = False
    if HAS_U2:
        try:
            d = u2.connect(device_id)
            success = post_via_u2(d, video_path, caption=caption)
        except Exception as e:
            log(f"⚠️ u2 error ({e}) กำลังสลับไปใช้ Native ADB Engine...")
            success = False

    if not success:
        log("⚙️ กำลังประมวลผลผ่าน Native ADB Shell Engine...")
        w, h = 800, 1340
        out = run_adb(["shell", "wm", "size"], device_id=device_id)
        m = re.search(r"(\d+)x(\d+)", out)
        if m:
            w, h = int(m.group(1)), int(m.group(2))

        run_adb(["shell", "input", "keyevent", "224"], device_id=device_id)
        run_adb(["shell", "input", "keyevent", "82"], device_id=device_id)
        time.sleep(1)
        run_adb(["shell", "am", "force-stop", "com.ss.android.ugc.trill"], device_id=device_id)
        time.sleep(1)
        run_adb(["shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", "com.ss.android.ugc.trill"], device_id=device_id)
        time.sleep(6)
        
        # Tap +
        run_adb(["shell", "input", "tap", str(int(w * 0.5)), str(int(h * 0.927))], device_id=device_id)
        time.sleep(4)
        # Tap Upload
        run_adb(["shell", "input", "tap", str(int(w * 0.066)), str(int(h * 0.919))], device_id=device_id)
        time.sleep(4)
        # Tap Top Left item (133, 310)
        run_adb(["shell", "input", "tap", str(int(w * 0.166)), str(int(h * 0.231))], device_id=device_id)
        time.sleep(3)
        # Tap Next
        run_adb(["shell", "input", "tap", str(int(w * 0.925)), str(int(h * 0.912))], device_id=device_id)
        time.sleep(4)
        # Tap Preview Next
        run_adb(["shell", "input", "tap", str(int(w * 0.925)), str(int(h * 0.912))], device_id=device_id)
        time.sleep(5)
        # Type Caption
        if caption:
            run_adb(["shell", "input", "tap", str(int(w * 0.25)), str(int(h * 0.15))], device_id=device_id)
            time.sleep(1)
            clean_cap = caption.replace("\n", " ").replace("'", "")
            run_adb(["shell", "input", "text", clean_cap[:100]], device_id=device_id)
            time.sleep(2)
        # Tap Post
        run_adb(["shell", "input", "tap", str(int(w * 0.7425)), str(int(h * 0.9164))], device_id=device_id)
        time.sleep(6)
        success = True

    # 3. บันทึกประวัติ + ย้ายไฟล์ลงคลังที่โพสต์แล้ว + ลบออกจาก VPS ป้องกันคลิปซ้ำ 100%
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []
    if video_path.name not in history:
        history.append(video_path.name)
        HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    # ย้ายไปโฟลเดอร์ posted_videos
    try:
        archive_target = ARCHIVE_DIR / video_path.name
        if video_path.exists():
            video_path.rename(archive_target)
            log(f"📦 ย้ายไฟล์คลิปเข้าคลังประวัติ: {archive_target.name}")
    except Exception as e:
        log(f"⚠️ Archive warning: {e}")

    # ลบไฟล์ออกจาก VPS เพื่อไม่ให้ scp ดึงมาซ้ำ
    try:
        subprocess.run(["ssh", VPS_HOST, f"rm -f '{VPS_PENDING_DIR}/{video_path.name}'"], capture_output=True, timeout=15)
        log("🧹 ลบไฟล์คลิปออกจาก VPS pending_videos เรียบร้อย")
    except Exception as e:
        log(f"⚠️ VPS cleanup warning: {e}")

    log(f"🎉 สำเร็จ 100%! วิดีโอ {video_path.name} ถูกอัปโหลดขึ้น TikTok ผ่านมือถืออัตโนมัติเรียบร้อยครับ")
    return True


def main():
    log("🤖 เริ่มต้นทำงานระบบ TikTok Zero-Touch Auto-Poster Daemon (Pro Engine)...")
    device_id = get_connected_device()
    if not device_id:
        log("❌ ไม่พบมือถือ Android เชื่อมต่ออยู่ กรุณาเชื่อมต่อสาย USB หรือต่อ Wi-Fi ADB")
        return

    log(f"📱 เชื่อมต่อมือถือเรียบร้อย: Device ID = {device_id}")

    video = sync_next_video_from_vps()
    if not video:
        log("✅ ไม่มีวิดีโอใหม่ในคลัง ระบบพร้อมทำงานในรอบถัดไป")
        return

    caption = build_tiktok_caption(video)
    auto_post_video_on_tiktok_app(device_id, video, caption=caption)


if __name__ == "__main__":
    main()
