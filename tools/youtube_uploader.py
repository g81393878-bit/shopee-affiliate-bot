#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/youtube_uploader.py — อัปโหลดคลิปวิดีโอ 9:16 ขึ้น YouTube Shorts (@regency1229) อัตโนมัติ

ความสามารถ:
1. ล็อคอินและจำลองสิทธิ์ผ่าน OAuth 2.0 (บันทึก token ไว้ใน tools/youtube_token.json)
2. อัปโหลดวิดีโอ 9:16 Full HD เข้าสู่ฟีด YouTube Shorts พร้อม #Shorts ใน Title
3. ใส่คำอธิบาย (Description) พร้อมลิงก์ Shopee Affiliate + ลิงก์ LINE OA ป้าเข็ม
4. ตั้งสถานะ Public (สาธารณะ) และ Category "People & Blogs" (22)
5. ป้องกันการโพสต์ซ้ำ และส่งแจ้งเตือนเข้า LINE เจ้าของร้าน
"""
import datetime
import json
import os
import pathlib
import re
import sys
import time
import threading
from typing import Dict, Optional, Union

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
PENDING_DIR = REELS_DIR / "pending_videos"
POSTED_DIR = REELS_DIR / "posted"
PRODUCTS_JSON = REELS_DIR / "products.json"

sys.path.insert(0, str(BACKEND_DIR))
from app.services.product_price_policy import sanitize_public_product_text  # noqa: E402

CLIENT_SECRET_FILE = TOOLS_DIR / "client_secret.json"
TOKEN_FILE = TOOLS_DIR / "youtube_token.json"
YOUTUBE_LOG_FILE = TOOLS_DIR / "youtube_uploader.log"

# `youtube.upload` alone cannot create a top-level comment.  Keep the existing
# scopes and explicitly request the write scope used by commentThreads.insert.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

def log(msg: str):
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(YOUTUBE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def notify_telegram(message: str) -> None:
    """แจ้งผล YouTube เข้า Telegram โดยไม่ส่ง token/URL credential ออกไป"""
    try:
        from telegram_notifier import send_telegram_alert
        send_telegram_alert(message[:1500])
    except Exception as e:
        log(f"[WARN] แจ้ง Telegram ไม่สำเร็จ: {type(e).__name__}")


def get_token_files() -> list:
    """ค้นหาไฟล์ YouTube OAuth Token ทั้งหมดในโฟลเดอร์ tools/"""
    tokens = []
    # 1. Token ช่องหลัก
    if TOKEN_FILE.exists():
        tokens.append({"id": 1, "name": "ช่องหลัก (@regency1229)", "path": TOKEN_FILE})
    
    # 2. Token ช่องเสริม (youtube_token_2.json, youtube_token_3.json, ...)
    for f in sorted(TOOLS_DIR.glob("youtube_token_*.json")):
        m = re.search(r'youtube_token_(\d+)\.json$', f.name)
        cid = int(m.group(1)) if m else len(tokens) + 1
        tokens.append({"id": cid, "name": f"ช่องที่ {cid}", "path": f})
    return tokens


class ReauthorizationRequired(RuntimeError):
    """The owner must explicitly reconnect this channel."""


def atomic_write(path, text):
    import tempfile
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        pathlib.Path(name).unlink(missing_ok=True)


def get_authenticated_service(token_path=None, channel_id=1, *, interactive=False, expected_handle=None):
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError, TransportError
    from googleapiclient.discovery import build

    target = pathlib.Path(token_path) if token_path else (TOOLS_DIR / f"youtube_token_{channel_id}.json" if channel_id > 1 else TOKEN_FILE)
    creds = None
    changed = False
    if target.exists() and not interactive:
        try:
            # Preserve the granted scopes; don't request broader scopes on refresh.
            creds = Credentials.from_authorized_user_file(str(target))
        except (ValueError, KeyError) as exc:
            raise ReauthorizationRequired(f"ช่อง {channel_id}: ไฟล์ Token ไม่สมบูรณ์ ต้องเชื่อมต่อใหม่") from exc
    if creds and not creds.valid and creds.refresh_token:
        for attempt in range(3):
            try:
                creds.refresh(Request())
                changed = True
                break
            except RefreshError as exc:
                if "invalid_grant" in str(exc):
                    raise ReauthorizationRequired(f"ช่อง {channel_id}: invalid_grant — Token หมดอายุหรือถูกเพิกถอน ต้องเชื่อมต่อใหม่") from exc
                if not getattr(exc, "retryable", False) or attempt == 2:
                    raise RuntimeError("ต่ออายุ Token ไม่สำเร็จ (RefreshError)") from exc
            except TransportError as exc:
                if attempt == 2:
                    raise RuntimeError("เครือข่ายขัดข้องขณะต่ออายุ Token") from exc
            time.sleep(2 ** attempt)
    if interactive:
        secret = CLIENT_SECRET_FILE if channel_id == 1 else TOOLS_DIR / f"client_secret_{channel_id}.json"
        if not secret.exists():
            raise FileNotFoundError(f"ไม่พบ OAuth Client Secret ของช่อง {channel_id}: {secret.name}")
        flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True, prompt="consent", access_type="offline", timeout_seconds=300)
        changed = True
    if not creds or not creds.valid:
        raise ReauthorizationRequired(f"ช่อง {channel_id}: ต้องเชื่อมต่อใหม่ด้วย --add-channel {channel_id}")
    service = build("youtube", "v3", credentials=creds)
    if expected_handle:
        rows = service.channels().list(part="snippet", mine=True).execute().get("items", [])
        handles = [r["snippet"].get("customUrl", "").lower() for r in rows]
        if expected_handle.lower() not in handles:
            raise ReauthorizationRequired("บัญชีที่เลือกไม่ตรงกับช่องที่ต้องการ — ไม่เขียนทับ Token เดิม")
    if changed:
        atomic_write(target, creds.to_json())
        log(f"[OK] บันทึก Token ช่อง {channel_id} สำเร็จ")
    return service


def build_shorts_title(product_name: str, is_pure_content: bool = False, hook_override: str = "") -> str:
    """สร้างชื่อคลิป YouTube Shorts พร้อม #Shorts (ความยาวไม่เกิน 85 ตัวอักษร)"""
    clean_name = re.sub(r'^(content_|prod_\d+_|duplicate_\d+_|\d+_)', '', product_name)
    clean_name = re.sub(r'_\d+$', '', clean_name)
    clean_name = re.sub(r'[_<>]+', ' ', clean_name).strip()

    if hook_override:
        title = f"{hook_override} {clean_name} #Shorts"
    elif is_pure_content:
        _PURE_HOOKS = [
            "💡 ทริคเด็ดป้าเข็ม!",
            "✨ รู้ไว้ชีวิตง่ายขึ้น 10 เท่า!",
            "🚨 แชร์ด่วน เรื่องนี้ต้องรู้!",
            "🔥 สาระน่ารู้ประจำวัน!",
            "🎯 ป้าเข็มบอกต่อ!",
        ]
        import random
        hook = random.choice(_PURE_HOOKS)
        title = f"{hook} {clean_name} #Shorts"
    else:
        _PRODUCT_HOOKS = [
            "เตือนแล้วนะ! ใครยังไม่มีติดบ้านคือพลาดมาก",
            "มีตัวนี้แล้วชีวิตง่ายขึ้น 10 เท่า!",
            "ตัวนี้คนแย่งกันซื้อถล่มทลาย รีวิวแน่นมาก!",
            "อย่าเพิ่งเลื่อนผ่าน ถ้าไม่อยากพลาดของดี!",
            "ของหลักสิบแต่ประโยชน์หลักพัน คุ้มจนต้องบอกต่อ!",
        ]
        import random
        hook = random.choice(_PRODUCT_HOOKS)
        title = f"{hook} {clean_name} #Shorts"

    if len(title) > 80:
        title = title[:75] + "... #Shorts"
    return title


def get_channel_info(youtube_service) -> dict:
    """ดึงชื่อช่องและแฮนเดิล (@handle) จริงจาก YouTube API"""
    try:
        res = youtube_service.channels().list(part="snippet", mine=True).execute()
        items = res.get("items", [])
        if items:
            snip = items[0].get("snippet", {})
            title = snip.get("title", "YouTube Channel")
            handle = snip.get("customUrl", "")
            if not handle and title:
                handle = f"@{title.replace(' ', '')}"
            return {"title": title, "handle": handle}
    except Exception:
        pass
    return {"title": "YouTube Shorts", "handle": ""}


def build_shorts_description(product_name: str, link: str = "", prod_id: Optional[int] = None, channel_handle: str = "", is_pure_content: bool = False, custom_caption: str = "") -> str:
    """สร้าง Description สำหรับ YouTube Shorts รองรับทั้งคลิปสินค้า Shopee และคลิปสาระความรู้เน้นยอดวิว/ยอดติดตาม"""
    if custom_caption:
        return custom_caption

    channel_ref = f" {channel_handle}" if channel_handle else ""

    yt_tags = ""
    try:
        from hashtag_intelligence import generate_platform_hashtags
        dyn = generate_platform_hashtags(product_name, is_product=not is_pure_content)
        yt_tags = dyn.get("youtube", "")
    except Exception:
        pass

    if is_pure_content or not link:
        fallback_yt = "#Shorts #สาระน่ารู้ #เรื่องเด็ด #เรื่องนี้ต้องรู้ #ไวรัล #ข่าวด่วน #ทริคดีๆ"
        lines = [
            f"✨ {product_name}\n",
            f"💬 คุณคิดเห็นยังไงกับเรื่องนี้? คอมเมนต์คุยกันได้เลยใต้คลิปนี้เลยจ้า 👇",
            f"🔔 กดติดตามช่อง{channel_ref} เพื่อรับชมเรื่องเด็ด สาระดีๆ และข่าวด่วนทุกวัน!\n",
            f"----------------------------------------",
            f"{yt_tags or fallback_yt}"
        ]
        return "\n".join(lines)

    line_url = os.getenv("LINE_OA_URL", "https://lin.ee/o9Kjp1N")
    line_id = os.getenv("LINE_OA_ID", "@137gsref")
    code_prompt = f" แล้วพิมพ์ \"{prod_id}\"" if prod_id else ""
    deep_link = f"https://line.me/R/oaMessage/{line_id}/?รหัส{prod_id}" if prod_id else line_url

    fallback_prod_yt = "#Shorts #ของดีบอกต่อ #ของมันต้องมี #ป้าเข็มป้ายยา #ถ้าไม่คุ้มป้าบอกให้ #ShopeeAffiliate #Shopee"
    lines = [
        f"✨ {product_name}\n",
        f"🛒 พิกัดสั่งซื้อของแท้ / โปรโมชั่น Shopee:\n👉 {link}\n",
        f"💬 ทักแชท LINE ป้าเข็ม รับพิกัดตรงทันที:\n",
        f"👉 แอด LINE ไอดี: {line_id}{code_prompt}\n",
        f"👉 ลิงก์เปิดแชท: {deep_link}\n\n",
        f"📍 หรือกดที่ชื่อช่อง{channel_ref} เพื่อดูรายละเอียดหน้าโปรไฟล์ได้เลยจ้า!\n",
        f"----------------------------------------",
        f"{yt_tags or fallback_prod_yt}"
    ]
    return "\n".join(lines)


def upload_shorts_to_channel(youtube_service, video_path: pathlib.Path, product_meta: Optional[Dict] = None, channel_name: str = "YouTube Shorts") -> Optional[str]:
    """อัปโหลดไฟล์วิดีโอขึ้น YouTube Shorts ของ 1 ช่อง"""
    from googleapiclient.http import MediaFileUpload

    ch_info = get_channel_info(youtube_service)
    display_name = f"{ch_info['title']} ({ch_info['handle']})" if ch_info['handle'] else ch_info['title']

    is_pure_content = (
        bool((product_meta or {}).get("is_pure_content"))
        or (product_meta or {}).get("content_mode") not in (None, "PRODUCT_HIGHLIGHT")
        or video_path.name.startswith(("content_", "pure_", "trend_", "hack_", "news_", "lucky_", "fortune_", "work_"))
        or not (product_meta or {}).get("affiliate_link")
    )

    raw_name = (
        (product_meta or {}).get("product_name")
        or ((product_meta or {}).get("topic_data") or {}).get("title")
        or ""
    )

    if not raw_name or re.match(r'^(content_|prod_\d+_|duplicate_\d+_|\d+_)', raw_name):
        clean_stem = re.sub(r'^(content_|prod_\d+_|duplicate_\d+_|\d+_)', '', video_path.stem)
        clean_stem = re.sub(r'_\d+$', '', clean_stem)
        mode_titles = {
            "trending_news": "ข่าวด่วน ประเด็นร้อนวันนี้",
            "celebrity_trend": "เรื่องเด่น ไวรัลคนดัง",
            "lucky_fortune": "ดวงวันนี้ เลขเด็ด เสริมเฮง",
            "life_hack_tip": "ทริคดีๆ เคล็ดลับคู่บ้าน",
            "work_productivity": "ทริคคนทำงาน พัฒนาตัวเอง",
        }
        raw_name = mode_titles.get(clean_stem, "สาระน่ารู้ เรื่องเด็ดประจำวัน")

    name = sanitize_public_product_text(raw_name)
    link = "" if is_pure_content else ((product_meta or {}).get("affiliate_link") or "")

    prod_id = None
    m = re.match(r'^prod_(\d+)_', video_path.name)
    if m:
        prod_id = int(m.group(1))

    topic_data = (product_meta or {}).get("topic_data") or {}
    topic_hook = topic_data.get("hook", "")
    content_mode = (product_meta or {}).get("content_mode", "TRENDING_NEWS")

    # 3-Second Viral Hook integration for Title
    if topic_hook and is_pure_content:
        clean_hook = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff\ufe0e\ufe0f]', '', topic_hook).strip()
        title = f"{clean_hook[:60]} #Shorts"
    else:
        title = build_shorts_title(name, is_pure_content=is_pure_content)

    # 3-Second Viral Hook integration for Description
    custom_caption = ""
    if is_pure_content and topic_data:
        try:
            import standalone_content_generator
            custom_caption = standalone_content_generator.build_standalone_caption(content_mode, topic_data, platform="youtube")
        except Exception:
            custom_caption = ""

    description = build_shorts_description(
        name, link=link, prod_id=prod_id,
        channel_handle=ch_info.get("handle", ""),
        is_pure_content=is_pure_content,
        custom_caption=custom_caption
    )

    tags = (
        ["Shorts", "สาระน่ารู้", "เรื่องเด็ด", "ข่าวด่วน", "ไวรัล", "ทริคดีๆ", "ความรู้"]
        if is_pure_content
        else ["Shorts", "ของดีบอกต่อ", "รีวิว", "Shopee", "ShopeeAffiliate", "ป้าเข็ม", "ของใช้ในบ้าน", "ไอที"]
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    log(f"🚀 กำลังอัปโหลดคลิปขึ้น {channel_name}: {title[:50]}...")
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)

    request = youtube_service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"   [{channel_name}] อัปโหลดแล้ว {int(status.progress() * 100)}%")

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube response missing video ID")
    video_url = f"https://youtube.com/shorts/{video_id}"
    log(f"✅ อัปโหลด {channel_name} สำเร็จ! -> {video_url}")
    notify_telegram(f"✅ YouTube อัปโหลดสำเร็จ\nช่อง: {channel_name}\nคลิป: {video_url}")

    # บันทึกประวัติเพื่อป้องกันการอัปโหลดซ้ำ
    record_youtube_upload(title, video_url, ch_info.get("id", 1))

    return video_url


POSTED_YOUTUBE_HISTORY_FILE = TOOLS_DIR / "posted_youtube_history.json"


def record_youtube_upload(title: str, video_url: str, channel_id: int = 1):
    try:
        hist = []
        if POSTED_YOUTUBE_HISTORY_FILE.exists():
            try:
                hist = json.loads(POSTED_YOUTUBE_HISTORY_FILE.read_text(encoding="utf-8"))
                if not isinstance(hist, list):
                    hist = []
            except Exception:
                hist = []
        hist.append({
            "title": title,
            "url": video_url,
            "channel_id": channel_id,
            "posted_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        if len(hist) > 500:
            hist = hist[-500:]
        POSTED_YOUTUBE_HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"[WARN] บันทึกประวัติ YouTube ล้ม: {e}")


LAST_CHANNEL_INDEX_FILE = TOOLS_DIR / "last_youtube_channel_index.txt"
CHANNEL_STATS_FILE = TOOLS_DIR / "youtube_channel_stats.json"


def increment_channel_counter(channel_id: int, channel_name: str = ""):
    """เพิ่มตัวนับจำนวนครั้งที่โพสต์สำเร็จของแต่ละช่อง (persistent JSON)"""
    try:
        stats = {}
        if CHANNEL_STATS_FILE.exists():
            stats = json.loads(CHANNEL_STATS_FILE.read_text(encoding="utf-8"))
        key = str(channel_id)
        if key not in stats:
            stats[key] = {"name": channel_name, "count": 0, "last_post": ""}
        stats[key]["count"] = stats[key].get("count", 0) + 1
        stats[key]["name"] = channel_name or stats[key].get("name", "")
        stats[key]["last_post"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        CHANNEL_STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_channel_stats() -> dict:
    """อ่านตัวนับจำนวนครั้งที่โพสต์ของทุกช่อง"""
    try:
        if CHANNEL_STATS_FILE.exists():
            return json.loads(CHANNEL_STATS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def format_channel_stats(stats: dict, tokens: list) -> str:
    """จัดรูปแบบตัวนับเป็นข้อความสั้นๆ สำหรับ log"""
    if not stats:
        return ""
    parts = []
    for t in tokens:
        s = stats.get(str(t["id"]), {})
        count = s.get("count", 0)
        parts.append(f"Ch{t['id']}={count}")
    return " ".join(parts)


def get_next_channel_rotation(tokens: list):
    """จัดลำดับคิวช่อง YouTube แบบ Round-Robin: สลับช่องวนรอบ และต่อคิวด้วยช่องถัดไปอัตโนมัติ (Auto-Failover)"""
    if not tokens:
        return [], 0
    last_idx = -1
    if LAST_CHANNEL_INDEX_FILE.exists():
        try:
            last_idx = int(LAST_CHANNEL_INDEX_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            last_idx = -1
    
    next_idx = (last_idx + 1) % len(tokens)
    ordered = tokens[next_idx:] + tokens[:next_idx]
    return ordered, next_idx


def set_last_successful_channel(token_id: int, tokens: list):
    """บันทึกลำดับช่องที่โพสต์สำเร็จ เพื่อให้รอบถัดไปสลับไปช่องใหม่"""
    try:
        for idx, t in enumerate(tokens):
            if t["id"] == token_id:
                LAST_CHANNEL_INDEX_FILE.write_text(str(idx), encoding="utf-8")
                break
    except Exception:
        pass


HEALTH_FILE = TOOLS_DIR / "youtube_health_state.json"
_UPLOAD_LOCK = threading.Lock()


def _read_health():
    try:
        state = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def _token_version(path):
    try:
        return pathlib.Path(path).stat().st_mtime_ns
    except OSError:
        return 0


def _failure(exc):
    # Only report known categories, never raw responses containing credentials.
    raw = str(exc)
    if isinstance(exc, ReauthorizationRequired) or "invalid_grant" in raw:
        return "auth", "Token ใช้ไม่ได้ ต้องเชื่อมต่อ Google ใหม่", 6 * 3600
    if "uploadLimitExceeded" in raw:
        return "upload_limit", "ช่องถึงลิมิตอัปโหลด พัก 6 ชั่วโมงก่อนลองใหม่", 6 * 3600
    if "quotaExceeded" in raw:
        return "api_quota", "โควต้า API หมด พัก 6 ชั่วโมงก่อนลองใหม่", 6 * 3600
    return "temporary", "เชื่อมต่อหรืออัปโหลดไม่สำเร็จ พัก 5 นาที", 300


def notify_line_admin(message):
    """Compatibility alias: operational alerts go to Telegram only."""
    notify_telegram(message)


def upload_shorts(video_path, product_meta=None, broadcast_all=False):
    # Scheduled and manual calls share the same cooldown state in this process.
    with _UPLOAD_LOCK:
        return _upload_shorts_locked(video_path, product_meta, broadcast_all)


def _upload_shorts_locked(video_path, product_meta=None, broadcast_all=False):
    """Try eligible channels; retain input on failure and persist alert cooldowns."""
    video_path = pathlib.Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError("ไม่พบไฟล์วิดีโอที่ต้องการอัปโหลด")
    tokens = get_token_files()
    state = _read_health()
    now = time.time()
    results, changes = [], []
    if not tokens:
        if now >= state.get("no_tokens_alert", 0):
            changes.append("ไม่พบ Token ของช่อง YouTube")
            state["no_tokens_alert"] = now + 21600
    ordered = tokens if broadcast_all or not tokens else get_next_channel_rotation(tokens)[0]
    for t in ordered:
        key = str(t["id"])
        previous = state.get(key, {})
        version = _token_version(t["path"])
        if previous.get("version") == version and previous.get("retry_at", 0) > now:
            continue
        try:
            service = get_authenticated_service(token_path=t["path"], channel_id=t["id"])
            info = get_channel_info(service)
            display = info.get("title") or t["name"]
            url = upload_shorts_to_channel(service, video_path, product_meta, channel_name=display)
            if not url:
                raise RuntimeError("YouTube ไม่ยืนยันผลอัปโหลด")
            results.append({"channel": display, "url": url, "id": t["id"]})
            state.pop(key, None)
            atomic_write(HEALTH_FILE, json.dumps(state, ensure_ascii=False))
            if previous:
                changes.append(f"ช่อง {t['id']}: กลับมาอัปโหลดสำเร็จแล้ว")
            set_last_successful_channel(t["id"], tokens)
            increment_channel_counter(t["id"], display)
            if not broadcast_all:
                break
        except Exception as exc:
            code, reason, delay = _failure(exc)
            if previous.get("code") != code or now >= previous.get("alert_at", 0):
                changes.append(f"ช่อง {t['id']}: {reason}")
                alert_at = now + 21600
            else:
                alert_at = previous["alert_at"]
            state[key] = {"code": code, "retry_at": now + delay, "alert_at": alert_at,
                          "version": _token_version(t["path"])}
            log(f"[WARN] ช่อง {t['id']}: {reason}")
    atomic_write(HEALTH_FILE, json.dumps(state, ensure_ascii=False))
    if changes:
        outcome = "รอบนี้ YouTube อัปโหลดสำเร็จ" if results else "รอบนี้ยังไม่มีการอัปโหลด YouTube สำเร็จ"
        notify_telegram("สถานะ YouTube\n" + "\n".join(changes) + "\n" + outcome)
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Channel YouTube Shorts Uploader")
    parser.add_argument("--auth-only", action="store_true", help="ทำแค่ยืนยันสิทธิ์ OAuth ช่องหลัก")
    parser.add_argument("--add-channel", type=int, default=0, help="ล็อกอินเพิ่มช่อง YouTube ลำดับที่ระบุ (เช่น --add-channel 2)")
    parser.add_argument("--list-channels", action="store_true", help="แสดงรายการช่อง YouTube ที่เชื่อมต่อไว้")
    parser.add_argument("--video", type=str, help="อัปโหลดวิดีโอที่ระบุ")
    parser.add_argument("--broadcast-all", action="store_true", help="สั่งยิงโพสต์ขึ้นครบทุกช่อง YouTube พร้อมกันทันที")
    parser.add_argument("--expected-handle", help="ตรวจ handle ก่อนบันทึก Token ใหม่")
    args = parser.parse_args()

    if args.list_channels:
        tokens = get_token_files()
        print(f"\n📺 รายการช่อง YouTube ที่เชื่อมต่อไว้ในระบบ ({len(tokens)} ช่อง):")
        for t in tokens:
            try:
                service = get_authenticated_service(token_path=t["path"], channel_id=t["id"])
                info = get_channel_info(service)
                disp = f"{info['title']} ({info['handle']})" if info.get("handle") else info.get("title", t["name"])
                print(f"  • [{t['id']}] {disp} (ไฟล์: {t['path'].name})")
            except Exception as e:
                print(f"  • [{t['id']}] {t['name']} (ไฟล์: {t['path'].name}) - ข้อผิดพลาด: {e}")
        print("")
        return

    if args.add_channel > 0:
        get_authenticated_service(channel_id=args.add_channel, interactive=True, expected_handle=args.expected_handle)
        print(f"🎉 สำเร็จ! เชื่อมต่อช่อง YouTube ช่องที่ {args.add_channel} เรียบร้อยแล้ว!")
        return

    if args.auth_only:
        get_authenticated_service(channel_id=1, interactive=True, expected_handle=args.expected_handle)
        print("✅ ยืนยันสิทธิ์บัญชี YouTube ช่องหลักสำเร็จเรียบร้อยแล้ว!")
        return

    target_vid = None
    if args.video:
        raw_p = pathlib.Path(args.video).resolve()
        if not raw_p.exists():
            for alt in [pathlib.Path("D:/") / args.video, PENDING_DIR / args.video, pathlib.Path("D:/คลิปป้าเข็ม") / args.video]:
                if alt.exists():
                    raw_p = alt.resolve()
                    break
        if raw_p.exists():
            target_vid = raw_p

    if not target_vid:
        vids = sorted(PENDING_DIR.glob("*.mp4"), key=os.path.getmtime)
        if not vids:
            print("ℹ️ ไม่มีคลิปรอโพสต์ใน pending_videos/")
            return
        target_vid = vids[0]

    meta = {}
    if PRODUCTS_JSON.exists():
        try:
            all_meta = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
            meta = all_meta.get(target_vid.name, {})
        except Exception:
            pass

    if not meta:
        meta = {
            "product_name": target_vid.stem,
            "category": "คลิปพิเศษ",
            "is_pure_content": True,
            "content_mode": "LIFE_HACK_TIP",
            "topic_data": {"title": target_vid.stem, "hook": target_vid.stem, "detail": "คลิปพิเศษ สาระดีๆ จากป้าเข็ม"}
        }

    urls = upload_shorts(target_vid, meta, broadcast_all=args.broadcast_all)
    if urls:
        print(f"\n🎉 สำเร็จ! เผยแพร่แล้ว {len(urls)} ช่องทาง:")
        for u in urls:
            print(f"  • {u['channel']}: {u['url']}")


if __name__ == "__main__":
    main()
