#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/tiktok_uploader.py — อัปโหลดวิดีโอ 9:16 ขึ้น TikTok อัตโนมัติผ่าน TikTok Content Posting API (v2)

ความสามารถ:
1. ล็อกอิน OAuth 2.0 PKCE และจัดการ Token อัตโนมัติ (บันทึกใน tools/tiktok_token.json)
2. มีระบบ Auto-refresh Token อัตโนมัติก่อนหมดอายุ
3. อัปโหลดวิดีโอ 9:16 Full HD เข้าสู่ฟีด TikTok โดยตรง (Direct Post v2) แบบ Chunked Stream
4. รองรับการเรียกใช้ผ่าน CLI และเป็นโมดูลให้กับระบบ Automation (system_runner.py)
"""

import argparse
import base64
import datetime
import hashlib
import http.server
import json
import math
import os
import pathlib
import re
import secrets
import socketserver
import sys
import threading
import time
import urllib.parse
from typing import Dict, Optional, Tuple, Union

import requests

# บังคับ UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
TOOLS_DIR = PROJECT_ROOT / "tools"
REELS_DIR = PROJECT_ROOT / "reels_uploader"
TOKEN_FILE = TOOLS_DIR / "tiktok_token.json"
TIKTOK_LOG_FILE = TOOLS_DIR / "tiktok_uploader.log"

# โหลด .env
from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "aw2u4qsbt1fl8su8").strip()
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "c0VQmZrE4DjgUbmhg64T2QosUCI1l7K9").strip()
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8000/auth/tiktok/callback").strip()

AUTH_BASE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_POST_ENDPOINT = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_FETCH_ENDPOINT = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
USER_INFO_ENDPOINT = "https://open.tiktokapis.com/v2/user/info/"

SCOPES = "user.info.basic,video.publish,video.upload"


def log(msg: str):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts} UTC] [TikTok] {msg}"
    print(line)
    try:
        with open(TIKTOK_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def generate_pkce() -> Tuple[str, str]:
    """สร้าง PKCE code_verifier และ code_challenge (S256)"""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


def build_authorization_url(verifier: str, challenge: str, state: str) -> str:
    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_BASE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str, verifier: str) -> Dict:
    data = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "code_verifier": verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_ENDPOINT, data=data, headers=headers, timeout=30)
    res_json = resp.json()
    if "data" in res_json and "access_token" in res_json["data"]:
        token_data = res_json["data"]
        token_data["created_at"] = time.time()
        save_token(token_data)
        return token_data
    elif "access_token" in res_json:
        res_json["created_at"] = time.time()
        save_token(res_json)
        return res_json
    else:
        raise RuntimeError(f"Failed to exchange token: {res_json}")


def refresh_token(token_data: Dict) -> Dict:
    refresh_tok = token_data.get("refresh_token")
    if not refresh_tok:
        raise ValueError("No refresh_token found in token data")
    data = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_ENDPOINT, data=data, headers=headers, timeout=30)
    res_json = resp.json()
    if "data" in res_json and "access_token" in res_json["data"]:
        new_data = res_json["data"]
        new_data["created_at"] = time.time()
        save_token(new_data)
        return new_data
    elif "access_token" in res_json:
        res_json["created_at"] = time.time()
        save_token(res_json)
        return res_json
    else:
        raise RuntimeError(f"Failed to refresh token: {res_json}")


def save_token(token_data: Dict):
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2, ensure_ascii=False), encoding="utf-8")
    log("บันทึก TikTok Token สำเร็จ -> " + str(TOKEN_FILE))


def load_token() -> Optional[Dict]:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_valid_token() -> Optional[str]:
    tok = load_token()
    if not tok:
        log("❌ ไม่พบไฟล์ tiktok_token.json — กรุณารัน: python tools/tiktok_uploader.py --auth เพื่อล็อกอินก่อน")
        return None
    created = tok.get("created_at", 0)
    expires_in = tok.get("expires_in", 86400)
    # รีเฟรชถ้าเหลืออายุน้อยกว่า 10 นาที
    if time.time() >= (created + expires_in - 600):
        log("🔄 Access Token ใกล้หมดอายุ ทำการรีเฟรช Token อัตโนมัติ...")
        try:
            tok = refresh_token(tok)
        except Exception as e:
            log(f"⚠️ รีเฟรช Token ล้มเหลว: {e} — ต้องล็อกอินใหม่")
            return None
    return tok.get("access_token")


def run_auth_flow():
    """รันระบบล็อกอิน OAuth 2.0 PKCE ผ่าน Browser และ Local Server"""
    print("\n" + "=" * 65)
    print("🔑 TikTok Developer OAuth 2.0 PKCE Login")
    print("=" * 65)
    
    verifier, challenge = generate_pkce()
    state = secrets.token_hex(16)
    auth_url = build_authorization_url(verifier, challenge, state)

    # Local Callback Handler
    auth_code_holder = {"code": None, "state": None, "error": None}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if "code" in qs:
                auth_code_holder["code"] = qs["code"][0]
                auth_code_holder["state"] = qs.get("state", [None])[0]
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h1>✅ เข้าสู่ระบบ TikTok สำเร็จ!</h1><p>คุณสามารถปิดหน้าต่างนี้และกลับไปที่ Terminal ได้เลยครับ</p>".encode("utf-8"))
            elif "error" in qs:
                auth_code_holder["error"] = qs["error"][0]
                self.send_response(400)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>❌ ล็อกอินไม่สำเร็จ: {qs['error'][0]}</h1>".encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # ซ่อน noisy log

    server = None
    try:
        server = socketserver.TCPServer(("localhost", 8000), CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        print("🌐 กำลังรอรับ Callback ที่: http://localhost:8000/auth/tiktok/callback")
    except Exception as e:
        print(f"⚠️ ไม่สามารถเปิด Local Port 8000 ได้ ({e}) — ใช้วิธีวาง Code ด้วยตนเอง")

    print("\n👉 กรุณาเปิดลิงก์นี้ในบราวเซอร์เพื่อล็อกอินและกดยินยอมสิทธิ์ TikTok:")
    print("-" * 65)
    print(auth_url)
    print("-" * 65)

    try:
        import webbrowser
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("\n⏳ กำลังรอการยืนยันตัวตน... (หรือกด Ctrl+C หากต้องการยกเลิก)")
    wait_start = time.time()
    while time.time() - wait_start < 300:  # รอ 5 นาที
        if auth_code_holder["code"]:
            break
        if auth_code_holder["error"]:
            print(f"❌ เกิดข้อผิดพลาด: {auth_code_holder['error']}")
            if server:
                server.shutdown()
            return
        time.sleep(1)

    if server:
        server.shutdown()

    code = auth_code_holder["code"]
    if not code:
        print("\n⚠️ ไม่ได้รับ Code ผ่าน Callback อัตโนมัติ")
        code_input = input("👉 หากมี Redirect URL หรือ Code ให้วางที่นี่ (หรือกด Enter เพื่อข้าม): ").strip()
        if code_input:
            if "code=" in code_input:
                code = urllib.parse.parse_qs(urllib.parse.urlparse(code_input).query).get("code", [None])[0]
            else:
                code = code_input

    if not code:
        print("❌ ยกเลิกการล็อกอิน: ไม่ได้รับ Authorization Code")
        return

    print("🔄 กำลังแลกเปลี่ยน Authorization Code เป็น Access Token...")
    try:
        tok_data = exchange_code_for_token(code, verifier)
        print("🎉 สำเร็จ! บันทึกสิทธิ์ TikTok เรียบร้อยแล้ว พร้อมใช้งานโพสต์อัตโนมัติ")
        log(f"OAuth Login สำเร็จ, OpenID: {tok_data.get('open_id')}")
    except Exception as e:
        print(f"❌ แลก Token ล้มเหลว: {e}")
        log(f"Exchange Token Error: {e}")


def sanitize_caption(caption: str, max_chars: int = 150) -> str:
    """ตัดแต่งแคปชั่นและแฮชแท็กให้เหมาะกับกฎ TikTok"""
    caption = (caption or "").strip()
    # ห้ามแสดงตัวเลขราคาตามกฎระบบป้าเข็ม
    caption = re.sub(r"\b\d+([.,]\d+)?\s*(บาท|฿|baht)\b", "", caption, flags=re.IGNORECASE)
    # รวมแฮชแท็กหลัก
    if "#ป้าเข็ม" not in caption:
        caption += " #ป้าเข็มรีวิว"
    if "#ของดีบอกต่อ" not in caption:
        caption += " #ของดีบอกต่อ"
    if len(caption) > max_chars:
        caption = caption[:max_chars - 3] + "..."
    return caption


def upload_video_to_tiktok(
    video_path: Union[str, pathlib.Path],
    caption: str = "",
    privacy_level: str = "PUBLIC_TO_EVERYONE",
    disable_comment: bool = False,
    disable_duet: bool = False,
    disable_stitch: bool = False,
) -> Dict:
    """อัปโหลดวิดีโอ 9:16 ขึ้น TikTok ผ่าน Content Posting API v2 (Direct Post)
    
    Returns:
        Dict: {"success": bool, "publish_id": str, "status": str, "error": str}
    """
    video_file = pathlib.Path(video_path)
    if not video_file.exists():
        return {"success": False, "error": f"Video file not found: {video_file}"}

    access_token = get_valid_token()
    if not access_token:
        return {"success": False, "error": "No valid TikTok access token"}

    file_size = video_file.stat().st_size
    clean_title = sanitize_caption(caption)

    # 1. คำนวณขนาด Chunk (5MB ถึง 64MB ตามสเปก TikTok)
    CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB ต่อ Chunk
    if file_size <= 5 * 1024 * 1024:
        CHUNK_SIZE = file_size
        total_chunks = 1
    else:
        total_chunks = math.ceil(file_size / CHUNK_SIZE)

    log(f"เริ่มอัปโหลดวิดีโอ: {video_file.name} (ขนาด {file_size / (1024*1024):.2f} MB, {total_chunks} chunks)")

    # 2. Init Video Publish
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    payload = {
        "post_info": {
            "title": clean_title,
            "privacy_level": privacy_level,
            "disable_comment": disable_comment,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": CHUNK_SIZE,
            "total_chunk_count": total_chunks,
        }
    }

    try:
        resp = requests.post(INIT_POST_ENDPOINT, headers=headers, json=payload, timeout=30)
        res_json = resp.json()
    except Exception as e:
        log(f"❌ Init Video Publish API Error: {e}")
        return {"success": False, "error": str(e)}

    err = res_json.get("error", {})
    if err.get("code") != "ok" and "data" not in res_json:
        log(f"❌ Init Video Failed: {res_json}")
        return {"success": False, "error": res_json.get("error", {}).get("message", "Init Failed")}

    data = res_json.get("data", {})
    publish_id = data.get("publish_id")
    upload_url = data.get("upload_url")

    if not publish_id or not upload_url:
        return {"success": False, "error": f"Invalid Init Response: {res_json}"}

    log(f"✓ Init สำเร็จ -> publish_id: {publish_id}")

    # 3. อัปโหลด Binary Chunks
    with open(video_file, "rb") as f:
        for chunk_idx in range(total_chunks):
            start_byte = chunk_idx * CHUNK_SIZE
            chunk_data = f.read(CHUNK_SIZE)
            chunk_len = len(chunk_data)
            end_byte = start_byte + chunk_len - 1

            put_headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(chunk_len),
                "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
            }

            try:
                put_resp = requests.put(upload_url, headers=put_headers, data=chunk_data, timeout=60)
                if put_resp.status_code not in (200, 201, 204, 206):
                    log(f"⚠️ Chunk {chunk_idx + 1}/{total_chunks} Upload Warning: Status {put_resp.status_code}")
                else:
                    log(f"   ✓ ส่ง Chunk {chunk_idx + 1}/{total_chunks} สำเร็จ ({chunk_len / 1024:.1f} KB)")
            except Exception as e:
                log(f"❌ ส่ง Chunk {chunk_idx + 1} ล้มเหลว: {e}")
                return {"success": False, "error": f"Chunk upload failed: {e}", "publish_id": publish_id}

    # 4. Polling ตรวจสอบสถานะการ Publish
    log("⏳ กำลังตรวจสอบสถานะการประมวลผลบนเซิร์ฟเวอร์ TikTok...")
    status_payload = {"publish_id": publish_id}
    final_status = "UNKNOWN"
    post_id = None

    for attempt in range(12):  # รอสูงสุด 60 วินาที (ตรวจทุก 5 วินาที)
        time.sleep(5)
        try:
            st_resp = requests.post(STATUS_FETCH_ENDPOINT, headers=headers, json=status_payload, timeout=20)
            st_json = st_resp.json()
            st_data = st_json.get("data", {})
            st_status = st_data.get("status", "")
            final_status = st_status

            if st_status == "SUCCESS":
                post_ids = st_data.get("publicly_available_post_id", [])
                post_id = post_ids[0] if post_ids else None
                log(f"🎉 โพสต์วิดีโอขึ้น TikTok สำเร็จ 100%! (Post ID: {post_id or publish_id})")
                return {
                    "success": True,
                    "publish_id": publish_id,
                    "post_id": post_id,
                    "status": "SUCCESS",
                    "video_url": f"https://www.tiktok.com/@me" if not post_id else f"https://www.tiktok.com/video/{post_id}"
                }
            elif st_status == "FAILED":
                fail_reason = st_data.get("fail_reason", "Unknown fail reason")
                log(f"❌ TikTok Publish Failed: {fail_reason}")
                return {"success": False, "publish_id": publish_id, "status": "FAILED", "error": fail_reason}
            else:
                log(f"   สถานะปัจจุบัน: {st_status} (กำลังประมวลผล #{attempt + 1})...")
        except Exception as e:
            log(f"⚠️ Status check error: {e}")

    # หากยังประมวลผลไม่เสร็จ แต่ส่ง chunks ผ่าน ถือว่าอยู่ระหว่าง Render
    return {
        "success": True,
        "publish_id": publish_id,
        "status": final_status or "PROCESSING",
        "video_url": "https://www.tiktok.com/@me"
    }


def main():
    parser = argparse.ArgumentParser(description="TikTok Content Posting API (v2) Uploader")
    parser.add_argument("--auth", action="store_true", help="ล็อกอินเพื่อรับ Access Token")
    parser.add_argument("--test-upload", type=str, nargs="?", const="pending", help="ทดสอบอัปโหลดวิดีโอ (ระบุพาธหรือใช้ไฟล์ใน pending_videos)")
    parser.add_argument("--caption", type=str, default="รีวิวของใช้สุดปังจาก Shopee #ป้าเข็มรีวิว #shopee", help="แคปชั่นวิดีโอ")
    parser.add_argument("--status", type=str, help="เช็คสถานะ publish_id")
    args = parser.parse_args()

    if args.auth:
        run_auth_flow()
        return

    if args.status:
        token = get_valid_token()
        if not token:
            print("❌ ไม่พบ Token กรุณารัน --auth ก่อน")
            return
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = requests.post(STATUS_FETCH_ENDPOINT, headers=headers, json={"publish_id": args.status})
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        return

    if args.test_upload:
        target_file = None
        if args.test_upload != "pending" and os.path.exists(args.test_upload):
            target_file = pathlib.Path(args.test_upload)
        else:
            # ค้นหาไฟล์ใน pending_videos หรือ posted
            for p_dir in [PROJECT_ROOT / "reels_uploader" / "pending_videos", PROJECT_ROOT / "reels_uploader" / "posted"]:
                vids = list(p_dir.glob("*.mp4"))
                if vids:
                    target_file = vids[0]
                    break
        if not target_file or not target_file.exists():
            print("❌ ไม่พบไฟล์วิดีโอ .mp4 สำหรับทดสอบ")
            return

        print(f"🎬 กำลังทดสอบอัปโหลด: {target_file.name}")
        res = upload_video_to_tiktok(target_file, caption=args.caption)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
