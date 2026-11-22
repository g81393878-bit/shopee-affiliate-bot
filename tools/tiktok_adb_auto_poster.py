#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/tiktok_adb_auto_poster.py — หุ่นยนต์อัปโหลด TikTok บนมือถือ Android อัตโนมัติ 100% (TAKTIK + uiautomator2 Engine)

คุณสมบัติระดับสตูดิโอ:
1. ผู้ใช้ไม่ต้องกดอะไรแม้แต่นิ้วเดียว (Zero User Effort)
2. รองรับระบบสลับหลายบัญชีอัตโนมัติ (Multi-Account Rotation / Round-Robin)
3. ใช้ uiautomator2 + ADB Native Engine แบบเดียวกับ TAKTIK Bot (เสถียร แม่นยำ ไร้การโดนแบน)
4. ระบบ Auto-Watcher ตรวจจับและปิดป๊อปอัปแจ้งเตือนบนหน้าจออัตโนมัติ
5. ส่งคลิปเข้า Movies/PaKhemBot โดยไม่ลบวิดีโอส่วนตัว
6. ระบบ Auto-Archive ย้ายคลิปที่โพสต์แล้วเข้าคลัง posted_videos/ และลบออกจาก VPS ทันที ป้องกันคลิปซ้ำ
7. รายงานผลสำเร็จเข้า Telegram Commander 24 ชม.
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
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from android_runtime import settings as android_settings, adb as shared_adb
from tiktok_mobile_history import inspect as inspect_history, record as record_history
LOCAL_PENDING_DIR = PROJECT_ROOT / "pending_videos"
LOCAL_PENDING_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR = PROJECT_ROOT / "posted_videos"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = PROJECT_ROOT / "tools" / "posted_tiktok_mobile_history.json"
ACCOUNT_STATE_FILE = PROJECT_ROOT / "tools" / "tiktok_mobile_account_state.json"

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
    try:
        return shared_adb(args, serial=device_id, timeout=timeout)
    except Exception as exc:
        raise RuntimeError("ADB command failed; stopping this attempt") from exc



def get_connected_device() -> Optional[str]:
    """ดึง ID มือถือที่เชื่อมต่ออยู่"""
    output = run_adb(["devices"])
    lines = output.split("\n")[1:]
    devices = [parts[0] for line in lines if len(parts := line.split()) >= 2 and parts[1] == "device"]
    requested = android_settings()["serial"]
    if requested:
        if requested not in devices:
            raise RuntimeError("Configured TikTok device is not connected or authorized")
        return requested
    if len(devices) > 1:
        raise RuntimeError("Multiple Android devices; configure TIKTOK_ANDROID_SERIAL")
    return devices[0] if devices else None


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
    """Copy one clip into the bot's directory without deleting personal media."""
    video_path = pathlib.Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(video_path)
    timestamp = int(time.time())
    safe_name = f"tiktok_video_{timestamp}.mp4"
    target_path = f"/sdcard/Movies/PaKhemBot/{safe_name}"
    run_adb(["shell", "mkdir", "-p", "/sdcard/Movies/PaKhemBot"], device_id=device_id)

    log(f"📲 กำลังส่งวิดีโอใหม่ {video_path.name} -> {safe_name} เข้าสู่มือถือ...")
    run_adb(["push", str(video_path), target_path], device_id=device_id, timeout=60)
    
    log("🔄 สั่งกระตุ้น Media Scanner & Content Provider สแกนวิดีโอใหม่เข้า Gallery...")
    run_adb(["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{target_path}"], device_id=device_id)
    run_adb(["shell", "content", "insert", "--uri", "content://media/external/video/media", "--bind", f"_data:s:{target_path}"], device_id=device_id)
    time.sleep(4)
    return target_path


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


def rotate_or_switch_tiktok_account(d, target_account: Optional[str] = None) -> str:
    """ระบบตรวจจับและสลับบัญชี TikTok แบบ Multi-Account Round-Robin อัตโนมัติ 100%"""
    log("🔄 กำลังตรวจสอบและสลับบัญชี TikTok (Multi-Account Rotation)...")

    # 1. ไปที่แท็บ 'โปรไฟล์'
    if d(text="โปรไฟล์").exists:
        d(text="โปรไฟล์").click()
    elif d(descriptionContains="โปรไฟล์").exists:
        d(descriptionContains="โปรไฟล์").click()
    else:
        w, h = d.window_size()
        d.click(int(w * 0.9), int(h * 0.95))
    time.sleep(2)

    # 2. กดเปิดเมนู 'สลับบัญชี' ที่หัวข้อโปรไฟล์ด้านบน
    w, h = d.window_size()
    d.click(int(w * 0.5), int(h * 0.193))
    time.sleep(2)

    # 3. ดึงรายชื่อบัญชีทั้งหมดที่มีใน Sheet
    accounts = []
    for el in d(className="android.widget.TextView"):
        try:
            t = el.get_text()
            if t and t not in ["สลับบัญชี", "เพิ่มบัญชี", "X", "ยกเลิก"] and not t.startswith("กำลังติดตาม"):
                accounts.append(t.strip())
        except Exception:
            pass

    # กรอง duplicate
    seen = set()
    unique_accounts = []
    for a in accounts:
        if a and a not in seen and len(a) < 30:
            seen.add(a)
            unique_accounts.append(a)

    if not unique_accounts:
        log("ℹ️ ตรวจไม่พบ Sheet สลับบัญชี ใช้บัญชีปัจจุบันที่ล็อกอินอยู่")
        return "default"

    log(f"📋 พบบัญชี TikTok ในระบบทั้งหมด ({len(unique_accounts)} บัญชี): {unique_accounts}")

    # 4. คำนวณบัญชีถัดไป (Round-Robin)
    state = {"last_account": "", "account_index": 0}
    if ACCOUNT_STATE_FILE.exists():
        try:
            state = json.loads(ACCOUNT_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {"last_account": "", "account_index": 0}

    last_idx = state.get("account_index", 0)
    next_idx = (last_idx + 1) % len(unique_accounts)
    next_account = target_account if (target_account and target_account in unique_accounts) else unique_accounts[next_idx]

    # 5. สลับไปยังบัญชีเป้าหมาย
    log(f"🎯 กำลังสลับไปใช้บัญชีลำดับที่ {next_idx + 1}/{len(unique_accounts)}: @{next_account}")
    if d(text=next_account).exists:
        d(text=next_account).click()
    else:
        # Fallback กดตามตำแหน่งแถว
        row_y = int(h * (0.86 + next_idx * 0.08))
        d.click(int(w * 0.5), min(row_y, int(h * 0.95)))

    time.sleep(3)

    # บันทึก state
    state["last_account"] = next_account
    state["account_index"] = next_idx
    state["total_accounts"] = len(unique_accounts)
    ACCOUNT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"✅ สลับบัญชีสำเร็จ! บัญชีที่พร้อมโพสต์ปัจจุบันคือ: @{next_account}")
    return next_account


def post_via_u2(d, video_path: pathlib.Path, caption: str = "", remote_path: str = "") -> bool:
    """โพสต์วิดีโอผ่าน uiautomator2 Engine คุณภาพสูงสไตล์ TAKTIK Bot"""
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from app.services.video_publish_policy import publication_block_reason
    blocked = publication_block_reason(video_path, caption)
    if blocked:
        log(blocked)
        return False
    log("🚀 เริ่มต้นกระบวนการอัปโหลดผ่าน uiautomator2 Engine...")
    
    # 1. ตั้งค่า Auto-Watcher ดักจับและกดปิดป๊อปอัปอัตโนมัติ
    try:
        d.watcher.reset()
        for txt in ["ไม่ใช่ตอนนี้", "ยกเลิก", "ปิด"]:
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

    # Verify the account on its profile page before any upload navigation.
    profile = d(description="โปรไฟล์")
    if not profile.exists:
        profile = d(text="โปรไฟล์")
    if not profile.exists:
        raise RuntimeError("Profile control not found")
    profile.click()
    expected = "@" + android_settings()["account"]
    if not d(text=expected).wait(timeout=10):
        raise RuntimeError("Expected TikTok account is not visible on the profile page")

    # 4. ค้นหาและกดปุ่ม '+' (สร้าง)
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

    # 5. ตรวจสอบว่าเข้าหน้ากล้องถ่ายรูปสำเร็จ
    if not (d(resourceIdMatches=".*upload.*").exists or d(textContains="อัปโหลด").exists):
        if d.app_current().get("package") == "com.ss.android.ugc.trill":
            log("⚠️ กำลังเข้าสู่หน้ากล้องถ่ายรูป...")
            w, h = d.window_size()
            d.click(int(w * 0.5), int(h * 0.927))
            time.sleep(4)

    # 6. กดปุ่ม 'อัปโหลด' คลังภาพ
    log("👉 กำลังเลือกปุ่ม 'อัปโหลด' คลังภาพ...")
    if d(resourceIdMatches=".*upload.*").exists:
        d(resourceIdMatches=".*upload.*").click()
    elif d(textContains="อัปโหลด").exists:
        d(textContains="อัปโหลด").click()
    else:
        w, h = d.window_size()
        d.click(int(w * 0.066), int(h * 0.919))
    
    time.sleep(4)

    # 7. กดเลือกแท็บ 'วิดีโอ' เพื่อกรองเฉพาะไฟล์วิดีโอ (ตัดรูปภาพ/สกรีนช็อตออก 100%)
    if d(text="วิดีโอ").exists:
        log("🎬 กดแท็บ 'วิดีโอ' เพื่อกรองเฉพาะคลิป...")
        d(text="วิดีโอ").click()
        time.sleep(2)

    # 8. เลือกคลิปแรกสุดในคลังภาพ (Row 1 Col 1: ช่องบนซ้ายสุด 133, 220)
    log("Checking the exact uploaded filename in the gallery")
    w, h = d.window_size()
    if not remote_path:
        raise RuntimeError("Exact uploaded filename is required")
    remote_name = pathlib.PurePosixPath(remote_path).name
    target = d(text=remote_name)
    if not target.exists:
        target = d(description=remote_name)
    if not target.exists or target.count != 1:
        raise RuntimeError("Gallery does not expose the exact uploaded filename; selection needs verification")
    target.click()
    time.sleep(3)

    # 9. กดปุ่ม 'ถัดไป' ในหน้าแกลเลอรี
    log("👉 กดปุ่มถัดไป (Next)...")
    if d(textMatches="(?i)ถัดไป.*|Next.*").exists:
        d(textMatches="(?i)ถัดไป.*|Next.*").click()
    else:
        d.click(int(w * 0.925), int(h * 0.912))
    time.sleep(4)

    # 10. กดปุ่ม 'ถัดไป' ในหน้าพรีวิววิดีโอ
    log("👉 กดปุ่มถัดไปหน้าพรีวิว...")
    if d(textMatches="(?i)ถัดไป.*|Next.*").exists:
        d(textMatches="(?i)ถัดไป.*|Next.*").click()
    else:
        d.click(int(w * 0.925), int(h * 0.912))
    time.sleep(5)

    # 11. ใส่แคปชั่น & แฮชแท็ก (ตรวจสอบก่อนว่าอยู่หน้าโพสต์จริง!)
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

    # 12. กดปุ่ม 'โพสต์' (Post)
    log("🚀 กำลังกดปุ่ม 'โพสต์' ขึ้น TikTok...")
    if d(resourceIdMatches=".*t6b.*").exists:
        d(resourceIdMatches=".*t6b.*").click()
    elif d(textMatches="(?i)โพสต์|Post").exists:
        d(textMatches="(?i)โพสต์|Post").click()
    else:
        raise RuntimeError("Post button not found; no coordinate fallback allowed")
    
    time.sleep(6)
    try:
        d.watcher.stop()
    except Exception:
        pass
    return True


def auto_post_video_on_tiktok_app(device_id: str, video_path: pathlib.Path, caption: str = "") -> bool:
    """One attempt only; unverified results are held, never silently retried."""
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from app.services.video_publish_policy import publication_block_reason
    blocked = publication_block_reason(video_path, caption)
    if blocked:
        log(blocked)
        return False
    video_path = pathlib.Path(video_path)
    config = android_settings()
    if device_id != config["serial"]:
        raise RuntimeError("Device does not match the configured TikTok station")
    account = config["account"]
    prior = inspect_history(video_path, account)
    if prior["status"] != "pending":
        log(f"Clip held by history: {prior['status']}")
        return False
    if not HAS_U2:
        raise RuntimeError("uiautomator2 is required; coordinate-only posting is disabled")
    # Reserve before any app action; a crash cannot result in automatic duplicate posting.
    record_history(video_path, account, "in_progress")
    try:
        d = u2.connect(device_id)
        remote_path = push_video_to_mobile(device_id, video_path)
        post_via_u2(d, video_path, caption=caption, remote_path=remote_path)
    except Exception as exc:
        log(f"Mobile attempt stopped: {exc}")
    finally:
        if 'd' in locals():
            try:
                d.watcher.stop()
            except Exception:
                pass
        # The legacy UI flow has no reliable receipt. Never turn its boolean into success.
        record_history(video_path, account, "unknown", "Publication receipt not verified")
    log("Outcome requires review; clip retained and automatic retry blocked")
    return False


def main():
    log("🤖 เริ่มต้นทำงานระบบ TikTok Zero-Touch Auto-Poster Daemon (Pro Engine with Multi-Account)...")
    device_id = get_connected_device()
    if not device_id:
        log("❌ ไม่พบมือถือ Android เชื่อมต่ออยู่ กรุณาเชื่อมต่อสาย USB หรือต่อ Wi-Fi ADB")
        return

    log(f"📱 เชื่อมต่อมือถือเรียบร้อย: Device ID = {device_id}")

    config = android_settings()
    queue = PROJECT_ROOT / config["queue"]
    video = next((path for path in sorted(queue.glob("*.mp4"))
                  if inspect_history(path, config["account"])["status"] == "pending"), None)
    if not video:
        log("✅ ไม่มีวิดีโอใหม่ในคลัง ระบบพร้อมทำงานในรอบถัดไป")
        return

    caption_file = video.with_suffix(".txt")
    if not caption_file.is_file():
        raise RuntimeError("Reviewed caption sidecar is required; filenames are not captions")
    caption = caption_file.read_text(encoding="utf-8").strip()
    if not caption:
        raise RuntimeError("Caption sidecar is empty")
    if not auto_post_video_on_tiktok_app(device_id, video, caption=caption):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
