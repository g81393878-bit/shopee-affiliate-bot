#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local Facebook Group Monitor — Social Demand Radar V1 (บอทป้าเข็ม)
===================================================================
Standalone Python CLI script for read-only local Facebook group monitoring.
Monitors public groups / simulated feeds, packages detected posts into
standardized payloads (`LeadIngestPayload`), and submits them to the
FastAPI Social Demand Radar endpoint:
    `POST /api/admin/facebook-radar/leads`

Key Features:
- Read-only passive monitoring adhering to safety constraints.
- Deduplication memory: Caches seen post IDs in-memory and in an optional JSON state file.
- Sample mode (`--sample` / `--mock`): Curated realistic Thai posts (High Demand, Price Inquiry, Scam Warning, Spam, General Discussion).
- Dry-run mode (`--dry-run`): Generates and validates payloads without sending network requests.
- Single-run (`--once`) or continuous interval polling (`--interval <seconds>`).
- Robust error handling: Gracefully handles network timeouts, HTTP 401/404/500 errors, and offline backends.

Usage Examples:
    # 1. Run sample posts in dry-run mode (no HTTP request)
    python tools/fb_group_monitor_local.py --sample --dry-run

    # 2. Run sample posts and submit to local backend
    python tools/fb_group_monitor_local.py --sample --once

    # 3. Monitor a specific Facebook group continuously every 5 minutes
    python tools/fb_group_monitor_local.py --group-id grp_moms_th --interval 300

    # 4. Specify custom API URL and token
    python tools/fb_group_monitor_local.py --api-url http://127.0.0.1:8000 --token my_secret_token --sample --once
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import urllib.error
import urllib.request

# Windows console encoding safeguard (force UTF-8 to display Thai & emojis cleanly)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("fb_group_monitor")

DEFAULT_API_URL = os.getenv("FASTAPI_URL") or os.getenv("BACKEND_URL") or "http://127.0.0.1:8000"
DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_STATE_FILE = ".fb_monitor_seen.json"
DEFAULT_LOCK_FILE = ".fb_monitor.lock"

# ===========================================================================
# Curated Realistic Thai Sample Posts for Testing & Demonstrations
# ===========================================================================
SAMPLE_POSTS: List[Dict[str, Any]] = [
    {
        "fb_post_id": "fb_sample_001_maternity",
        "group_id": "grp_moms_th",
        "group_name": "กลุ่มแม่และเด็ก ของใช้แม่ลูก",
        "group_url": "https://facebook.com/groups/moms_th",
        "author_name": "คุณแม่น้องบีน่า",
        "post_text": "มีแม่ๆ คนไหนแนะนำชุดคลุมท้องใส่สบายๆ ผ้าระบายอากาศดีๆ ไม่ร้อนบ้างคะ ขอแบบราคาไม่เกิน 400 บาท ขอบคุณค่ะ",
        "post_url": "https://facebook.com/groups/moms_th/posts/1001",
        "post_time": "2026-08-15T12:30:00Z",
        "raw_data": {"likes": 18, "comments": 5, "shares": 1},
    },
    {
        "fb_post_id": "fb_sample_002_earbuds",
        "group_id": "grp_tech_deals",
        "group_name": "กลุ่มคนรักหูฟังและแกดเจ็ต",
        "group_url": "https://facebook.com/groups/tech_deals",
        "author_name": "นักฟังเพลง",
        "post_text": "อยากได้หูฟังบลูทูธไร้สายตัดเสียงรบกวนดีๆ งบ 500 บาท มีตัวไหนคุ้มสุดตอนนี้บ้างครับ",
        "post_url": "https://facebook.com/groups/tech_deals/posts/1002",
        "post_time": "2026-08-15T12:35:00Z",
        "raw_data": {"likes": 12, "comments": 7, "shares": 0},
    },
    {
        "fb_post_id": "fb_sample_003_ergonomic",
        "group_id": "grp_wfh_th",
        "group_name": "กลุ่มคนทำงาน Work From Home",
        "group_url": "https://facebook.com/groups/wfh_th",
        "author_name": "พนักงานออฟฟิศปวดหลัง",
        "post_text": "ปวดหลังมาก ทำงาน WFH นั่งทั้งวัน อยากได้เบาะรองนั่งหรือเก้าอี้เพื่อสุขภาพดีๆ งบ 1000 บาท แนะนำหน่อยครับ",
        "post_url": "https://facebook.com/groups/wfh_th/posts/1003",
        "post_time": "2026-08-15T12:40:00Z",
        "raw_data": {"likes": 25, "comments": 14, "shares": 2},
    },
    {
        "fb_post_id": "fb_sample_004_scam_warning",
        "group_id": "grp_moms_th",
        "group_name": "กลุ่มแม่และเด็ก ของใช้แม่ลูก",
        "group_url": "https://facebook.com/groups/moms_th",
        "author_name": "แอดมินกลุ่มเตือนภัย",
        "post_text": "ประกาศเตือนภัยมิจฉาชีพหลอกโอนเงินค่าสินค้า ขอให้สมาชิกทุกคนระวังด้วยนะคะ โดนโกงไป 500 บาท บัญชีคนโกง blacklist",
        "post_url": "https://facebook.com/groups/moms_th/posts/1004",
        "post_time": "2026-08-15T12:45:00Z",
        "raw_data": {"likes": 64, "comments": 22, "shares": 15},
    },
    {
        "fb_post_id": "fb_sample_005_spam",
        "group_id": "grp_market_th",
        "group_name": "ตลาดนัดออนไลน์ซื้อขายของ",
        "group_url": "https://facebook.com/groups/market_th",
        "author_name": "ร้านเพิ่มยอดฟอล",
        "post_text": "ฝากร้านหน่อยจ้า รับปั๊มฟอล IG ราคาถูก สนใจทักแชทได้เลย",
        "post_url": "https://facebook.com/groups/market_th/posts/1005",
        "post_time": "2026-08-15T12:50:00Z",
        "raw_data": {"likes": 1, "comments": 0, "shares": 0},
    },
    {
        "fb_post_id": "fb_sample_006_general",
        "group_id": "grp_talk_bkk",
        "group_name": "คุยเรื่องทั่วไป กรุงเทพ",
        "group_url": "https://facebook.com/groups/talk_bkk",
        "author_name": "คนเดินทาง",
        "post_text": "วันนี้ฝนตกหนักมากแถวสยาม มีใครติดฝนเหมือนกันบ้าง รถติดสุดๆ",
        "post_url": "https://facebook.com/groups/talk_bkk/posts/1006",
        "post_time": "2026-08-15T12:55:00Z",
        "raw_data": {"likes": 9, "comments": 4, "shares": 0},
    },
]


# ===========================================================================
# Environment & Token Resolution
# ===========================================================================
def load_env_token(cli_token: Optional[str] = None, env_path: Optional[str] = None) -> str:
    """Resolves authentication token with precedence:
    1. CLI Argument `--token`
    2. Environment Variable `CRON_TOKEN`
    3. Environment Variable `ADMIN_DASHBOARD_PASSWORD`
    4. `backend/.env` file lookup
    """
    if cli_token and cli_token.strip():
        return cli_token.strip()

    env_val = os.getenv("CRON_TOKEN") or os.getenv("ADMIN_DASHBOARD_PASSWORD")
    if env_val and env_val.strip():
        return env_val.strip()

    # Search in backend/.env relative to script location
    if env_path is None:
        target_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
    else:
        target_path = Path(env_path)

    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                token_found = ""
                for line in f:
                    line = line.strip()
                    if line.startswith("CRON_TOKEN="):
                        token_found = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if token_found:
                            return token_found
                    elif line.startswith("ADMIN_DASHBOARD_PASSWORD=") and not token_found:
                        token_found = line.split("=", 1)[1].strip().strip('"').strip("'")
                if token_found:
                    return token_found
        except Exception as e:
            logger.debug(f"Failed to read .env at {target_path}: {e}")

    return ""


# ===========================================================================
# Deduplication & Seen Post Tracker
# ===========================================================================
class SeenPostTracker:
    """Manages deduplication state for monitored posts in memory and on disk."""

    def __init__(self, state_file: Optional[str] = None, auto_load: bool = True):
        self.state_file = Path(state_file) if state_file else None
        self._seen_ids: Set[str] = set()
        if self.state_file and auto_load:
            self.load_state()

    def is_seen(self, post_id: str) -> bool:
        """Check if post_id was previously tracked."""
        if not post_id:
            return False
        return str(post_id).strip() in self._seen_ids

    def mark_seen(self, post_id: str) -> None:
        """Mark post_id as seen."""
        if post_id:
            self._seen_ids.add(str(post_id).strip())

    def mark_seen_many(self, post_ids: Iterable[str]) -> None:
        """Mark multiple post IDs as seen."""
        for pid in post_ids:
            self.mark_seen(pid)

    def filter_unseen(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filters out posts that have already been tracked."""
        unseen: List[Dict[str, Any]] = []
        for post in posts:
            pid = post.get("fb_post_id") or post.get("post_id") or ""
            if pid and not self.is_seen(pid):
                unseen.append(post)
        return unseen

    def load_state(self, path: Optional[str] = None) -> int:
        """Load seen post IDs from a JSON state file."""
        target = Path(path) if path else self.state_file
        if not target or not target.exists():
            return 0
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._seen_ids.update(str(x) for x in data if x)
                elif isinstance(data, dict) and "seen_ids" in data:
                    self._seen_ids.update(str(x) for x in data["seen_ids"] if x)
            return len(self._seen_ids)
        except Exception as e:
            logger.warning(f"Failed to load state from {target}: {e}")
            return len(self._seen_ids)

    def save_state(self, path: Optional[str] = None) -> bool:
        """Save seen post IDs to a JSON state file."""
        target = Path(path) if path else self.state_file
        if not target:
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump({
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "total_seen": len(self._seen_ids),
                    "seen_ids": sorted(list(self._seen_ids)),
                }, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.warning(f"Failed to save state to {target}: {e}")
            return False

    def clear(self) -> None:
        """Clear all in-memory seen post IDs."""
        self._seen_ids.clear()

    @property
    def count(self) -> int:
        return len(self._seen_ids)


# ===========================================================================
# Sample & Lead Payload Construction
# ===========================================================================
def get_sample_posts(
    group_id: Optional[str] = None,
    group_name: Optional[str] = None,
    group_url: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Retrieves curated sample posts with optional group overrides."""
    posts: List[Dict[str, Any]] = []
    for item in SAMPLE_POSTS:
        post_copy = dict(item)
        if group_id:
            post_copy["group_id"] = group_id
        if group_name:
            post_copy["group_name"] = group_name
        if group_url:
            post_copy["group_url"] = group_url
        posts.append(post_copy)

    if limit and limit > 0:
        return posts[:limit]
    return posts


def _kill_chrome_tree(driver: Any) -> None:
    """Close the browser and force-kill the whole chromedriver process tree.

    `driver.quit()` alone can leave orphaned `chrome.exe` / `undetected_chromedriver.exe`
    processes behind (especially after a crash or a hard kill), which is what keeps a
    "dead" monitor visibly running. On Windows we capture the driver PID *before*
    quitting, then `taskkill /T /F` the whole tree so no Chrome child survives.
    """
    # 1. Capture the driver PID while it is still alive (needed for tree-kill after quit).
    pid = None
    proc = None
    try:
        service = getattr(driver, "service", None)
        proc = getattr(service, "process", None) if service else None
        pid = getattr(proc, "pid", None) if proc else None
    except Exception:
        pid = None

    # 2. Graceful shutdown first (closes the browser window cleanly).
    try:
        driver.quit()
    except Exception:
        pass

    # 3. Then force-kill whatever survived (chromedriver + its Chrome children).
    if not pid:
        return
    try:
        if os.name == "nt":
            import subprocess
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
            )
        else:
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass
    except Exception:
        pass


def _sweep_orphan_drivers() -> int:
    """Kill leftover `undetected_chromedriver.exe` processes from a previous run.

    A hard-killed monitor (`taskkill //F`) never reaches its `finally`, so its
    chromedriver + Chrome children survive as zombies and keep "scanning" in the
    background. Sweep them at startup so every real run starts clean. Only the
    uniquely-named driver binary is targeted — never the user's own Chrome.
    """
    if os.name != "nt":
        return 0
    import subprocess
    killed = 0
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq undetected_chromedriver.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        return 0

    for line in out.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 2 or parts[0].lower() != "undetected_chromedriver.exe":
            continue
        pid = parts[1]
        if not pid.isdigit():
            continue
        try:
            subprocess.run(
                ["taskkill", "/PID", pid, "/T", "/F"],
                capture_output=True,
                timeout=10,
            )
            killed += 1
        except Exception:
            pass
    return killed


def _is_pid_alive(pid: int) -> bool:
    """True if a process with the given PID is still running (cross-platform).

    On Windows `os.kill(pid, 0)` would actually *terminate* the process, so we
    query `tasklist` instead — same technique used by `_sweep_orphan_drivers`.
    """
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import subprocess
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    return f'"{pid}"' in proc.stdout


def _process_age_seconds(pid: int) -> Optional[float]:
    """Elapsed seconds since the given PID was created, or None if unknown.

    Used by `--pid-timeout` to detect hung monitors: a live lock holder that has
    been running longer than the timeout is treated as stuck and its lock is broken.
    """
    import subprocess
    if os.name != "nt":
        try:
            out = subprocess.run(
                ["ps", "-o", "etimes=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            return float(out) if out.isdigit() else None
        except Exception:
            return None

    # Windows: PowerShell CIM (wmic is deprecated). Output elapsed seconds in
    # invariant culture so a Thai/other locale can't break the number parsing.
    try:
        ps_cmd = (
            "((Get-Date) - (Get-CimInstance Win32_Process -Filter "
            "\"ProcessId={pid}\").CreationDate).TotalSeconds."
            "ToString([System.Globalization.CultureInfo]::InvariantCulture)"
        ).format(pid=pid)
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
        return float(out) if out else None
    except Exception:
        return None


def _is_monitor_process(pid: int) -> Optional[bool]:
    """Whether the given PID is actually running our monitor script.

    Returns True if the command line contains `fb_group_monitor_local.py`, False if
    the command line is readable but doesn't (PID reused by an unrelated program),
    or None if it can't be determined (treat as unknown → don't break the lock).
    """
    import subprocess
    if os.name != "nt":
        try:
            out = subprocess.run(
                ["ps", "-o", "command=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        except Exception:
            return None
        return "fb_group_monitor_local.py" in out if out.strip() else None

    try:
        ps_cmd = (
            "(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine"
        ).format(pid=pid)
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:
        return None
    return "fb_group_monitor_local.py" in out if out.strip() else None


def _acquire_monitor_lock(lock_file: Optional[str], pid_timeout_minutes: int = 0) -> Tuple[bool, str]:
    """Acquire a single-instance lock so only one monitor runs at a time.

    Returns `(acquired, message)`. If another live monitor already holds the lock,
    `acquired` is False and `message` explains why. A stale lock (dead PID) is
    overwritten; a lock we cannot write is non-fatal (we continue unlocked).

    `pid_timeout_minutes` (from `--pid-timeout`) breaks the lock when the holding
    process has been alive longer than that — a hung monitor that would otherwise
    block restarts forever.
    """
    if not lock_file:
        return True, ""
    path = Path(lock_file)

    message = ""
    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8").strip()
            old_pid = int(raw) if raw.isdigit() else None
        except Exception:
            old_pid = None
        if old_pid and _is_pid_alive(old_pid):
            # Only a process really running our monitor can hold the lock. If the PID
            # was reused by an unrelated program, the original monitor is gone → stale.
            # Unknown (can't read cmdline) → stay conservative and refuse.
            is_monitor = _is_monitor_process(old_pid)
            if is_monitor is False:
                message = (
                    f"⚠️ lock ของ PID {old_pid} ถูกใช้งานโดย process อื่น (ไม่ใช่ monitor) "
                    f"— ถือเป็น lock ค้าง เขียนทับ"
                )
            elif is_monitor is True and pid_timeout_minutes and pid_timeout_minutes > 0:
                # Hung-monitor override: break locks held by processes older than the timeout.
                age = _process_age_seconds(old_pid)
                if age is not None and age > pid_timeout_minutes * 60:
                    message = (
                        f"⏰ lock ของ PID {old_pid} อายุเกิน {pid_timeout_minutes} นาที "
                        f"(คาดว่า hung) — เขียนทับและเริ่มใหม่"
                    )
                else:
                    return False, (
                        f"❌ บอทสแกนอีกตัวกำลังรันอยู่แล้ว (PID {old_pid})\n"
                        f"   หยุดตัวนั้นก่อน หรือลบ {path} ถ้าแน่ใจว่าไม่มีตัวไหนรันจริง"
                    )
            else:
                return False, (
                    f"❌ บอทสแกนอีกตัวกำลังรันอยู่แล้ว (PID {old_pid})\n"
                    f"   หยุดตัวนั้นก่อน หรือลบ {path} ถ้าแน่ใจว่าไม่มีตัวไหนรันจริง"
                )
        # Dead PID, non-monitor PID, or timed-out hung monitor → fall through and overwrite.

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(os.getpid()), encoding="utf-8")
        return True, message
    except Exception as e:
        return True, f"⚠️ เขียน lock file ไม่ได้ ({e}) — รันต่อโดยไม่ล็อก"


def _release_monitor_lock(lock_file: Optional[str]) -> None:
    """Release the single-instance lock, but only if we still own it."""
    if not lock_file:
        return
    path = Path(lock_file)
    try:
        if path.exists():
            if path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                path.unlink()
    except Exception:
        pass


def scrape_real_facebook_posts(
    group_id: Optional[str] = None,
    group_name: Optional[str] = None,
    group_url: Optional[str] = None,
    limit: Optional[int] = 5,
) -> List[Dict[str, Any]]:
    """Scrapes recent posts from a Facebook group using undetected_chromedriver."""
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    import os
    import json
    import time
    
    posts: List[Dict[str, Any]] = []
    url = group_url or f"https://www.facebook.com/groups/{group_id}"
    
    print("   ↳ 🕵️  [Stealth] Starting Undetected Chrome Browser with advanced configurations...")
    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument('--no-first-run')
    options.add_argument('--no-service-autorun')
    options.add_argument('--password-store=basic')
    
    # Launch browser using undetected_chromedriver with version matching the host Chrome
    driver = uc.Chrome(options=options, version_main=151)
    driver.set_script_timeout(10)
    driver.set_page_load_timeout(15)
    
    try:
        # Navigate to domain first to set cookies
        print(f"   ↳ 🌐 Accessing Facebook domain to inject session cookies...")
        try:
            driver.get("https://www.facebook.com/")
        except Exception:
            pass # Ignore timeouts on initial domain load
        time.sleep(2)
        
        # Load and inject cookies
        cookie_path = os.path.join(os.path.dirname(__file__), '..', 'fb_cookies.json')
        if os.path.exists(cookie_path):
            try:
                with open(cookie_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        driver.add_cookie({
                            'name': cookie['name'],
                            'value': cookie['value'],
                            'domain': cookie.get('domain', '.facebook.com'),
                            'path': cookie.get('path', '/')
                        })
                print(f"   ↳ 🍪 Injected Facebook session cookies successfully.")
            except Exception as e:
                print(f"   ↳ ⚠️ Cookie Injection Error: {e}")
                
        # Perform refresh and Cloudflare/Captcha bypass (if present)
        driver.refresh()
        time.sleep(3)
        try:
            driver.uc_gui_click_captcha()
            time.sleep(2)
        except Exception:
            pass
            
        # Now navigate to target group URL
        print(f"   ↳ 🌐 Navigating to Group: {url}")
        driver.get(url)
        time.sleep(5)
        
        try:
            driver.uc_gui_click_captcha()
            time.sleep(2)
        except Exception:
            pass
            
        print(f"   ↳ 📄 Page Title: {driver.title}")
        
        # Wait a moment for dynamic load
        time.sleep(3)
        
        # Scroll to load posts
        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(2)
        
        # Try to find post elements. Facebook posts usually have role="article" or live in feed container
        articles = driver.find_elements(By.XPATH, '//div[@role="article"]')
        if not articles:
            articles = driver.find_elements(By.XPATH, '//div[@role="feed"]/div')
            
        print(f"   ↳ 📋 Found {len(articles)} potential posts on page")
        
        for i, el in enumerate(articles):
            if limit and len(posts) >= limit:
                break
            try:
                text_content = el.text
                if not text_content or len(text_content) < 20:
                    continue
                
                lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                if len(lines) >= 2:
                    author = lines[0]
                    # Filter out buttons and interactive elements
                    content_lines = []
                    for line in lines[1:]:
                        if line in ["Like", "Comment", "Share", "Send", "ถูกใจ", "แสดงความคิดเห็น", "แชร์", "ส่ง"]:
                            break
                        content_lines.append(line)
                    
                    post_text = " ".join(content_lines[:10])
                    
                    if len(post_text) > 10:
                        # ใช้ sha1 (deterministic) แทน hash() — hash() ของ Python ถูก salt
                        # ต่อ process (PYTHONHASHSEED) → post เดียวกันได้ id ต่างกันทุก run
                        # → dedup ข้าม run (--state-file) พัง → ส่ง post เดิมซ้ำ → โพสต์ซ้ำได้
                        _stable = hashlib.sha1(post_text[:20].encode("utf-8", "ignore")).hexdigest()[:10]
                        posts.append({
                            "fb_post_id": f"{group_id}_{i}_{_stable}",
                            "group_id": group_id,
                            "group_name": group_name or "Facebook Group",
                            "group_url": url,
                            "author_name": author,
                            "post_text": post_text,
                            "post_url": url,
                            "post_time": datetime.now(timezone.utc).isoformat(),
                            "raw_data": {"extracted_lines": len(lines)}
                        })
            except Exception:
                pass
                
    except Exception as e:
        print(f"   ↳ ❌ Error scraping Facebook: {e}")
    finally:
        _kill_chrome_tree(driver)

    return posts


def build_lead_payload(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Formats raw post dictionaries into standard `LeadIngestPayload`."""
    leads: List[Dict[str, Any]] = []
    for post in posts:
        pid = str(post.get("fb_post_id") or post.get("post_id") or "").strip()
        purl = str(post.get("post_url") or "https://facebook.com").strip()
        ptext = str(post.get("post_text") or "").strip()
        author = post.get("author_name")
        ptime = post.get("post_time") or datetime.now(timezone.utc).isoformat()
        gid = post.get("group_id")
        gname = post.get("group_name")
        raw = post.get("raw_data") or post.get("raw_payload")

        leads.append({
            "fb_post_id": pid,
            "post_url": purl,
            "author_name": author,
            "post_text": ptext,
            "post_time": ptime,
            "group_id": gid,
            "group_name": gname,
            "raw_data": raw,
        })

    return {"leads": leads}


def fetch_active_groups_from_api(api_url: str, token: str) -> List[Dict[str, Any]]:
    """Fetch active Facebook groups to monitor from the backend database."""
    clean_url = api_url.rstrip("/")
    endpoint = f"{clean_url}/api/admin/facebook-radar/groups"
    
    headers = {
        "User-Agent": "PKH-FacebookRadarMonitor/1.0",
    }
    if token:
        headers["X-Admin-Token"] = token
        
    request_url = endpoint
    if token and "?" not in request_url:
        request_url = f"{endpoint}?token={token}"
        
    import urllib.request
    req = urllib.request.Request(request_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8")
            return json.loads(resp_body) if resp_body else []
    except Exception as e:
        print(f"   ↳ ⚠️ Failed to fetch target groups from API: {e}")
        return []


# ===========================================================================
# Backend Transmission
# ===========================================================================
def submit_leads_to_api(
    api_url: str,
    token: str,
    payload: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Submits lead payload to `POST /api/admin/facebook-radar/leads`.
    Supports standard `urllib.request` or an in-process client (like FastAPI TestClient).
    """
    clean_url = api_url.rstrip("/")
    endpoint = f"{clean_url}/api/admin/facebook-radar/leads"

    # Support in-process client (e.g. FastAPI TestClient during unit tests)
    if client is not None:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Admin-Token"] = token
        try:
            resp = client.post(
                "/api/admin/facebook-radar/leads" if endpoint.startswith("http://testserver") else endpoint,
                json=payload,
                headers=headers,
                params={"token": token} if token else None,
            )
            try:
                body = resp.json()
            except Exception:
                body = {"detail": resp.text}

            return {
                "ok": resp.status_code == 200,
                "status_code": resp.status_code,
                "data": body if resp.status_code == 200 else None,
                "error": None if resp.status_code == 200 else f"HTTP {resp.status_code}",
                "detail": body if resp.status_code != 200 else None,
            }
        except Exception as e:
            return {
                "ok": False,
                "status_code": 0,
                "data": None,
                "error": type(e).__name__,
                "detail": str(e),
            }

    # Standard urllib network submission
    req_headers = {
        "Content-Type": "application/json",
        "User-Agent": "PKH-FacebookRadarMonitor/1.0",
    }
    if token:
        req_headers["X-Admin-Token"] = token

    request_url = endpoint
    if token and "?" not in request_url:
        request_url = f"{endpoint}?token={token}"

    data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(request_url, data=data_bytes, headers=req_headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            parsed_data = json.loads(resp_body) if resp_body else {}
            return {
                "ok": True,
                "status_code": resp.status,
                "data": parsed_data,
                "error": None,
                "detail": None,
            }
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        return {
            "ok": False,
            "status_code": e.code,
            "data": None,
            "error": f"HTTP {e.code}",
            "detail": err_body or str(e.reason),
        }
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "status_code": 0,
            "data": None,
            "error": "ConnectionError",
            "detail": f"Failed to connect to {api_url}: {e.reason}",
        }
    except TimeoutError as e:
        return {
            "ok": False,
            "status_code": 0,
            "data": None,
            "error": "TimeoutError",
            "detail": f"Request timed out after {timeout}s: {e}",
        }
    except Exception as e:
        return {
            "ok": False,
            "status_code": 0,
            "data": None,
            "error": type(e).__name__,
            "detail": str(e),
        }


# ===========================================================================
# Single Monitor Iteration
# ===========================================================================
def run_monitor_iteration(
    api_url: str,
    token: str,
    tracker: SeenPostTracker,
    sample_mode: bool = False,
    group_id: Optional[str] = None,
    group_name: Optional[str] = None,
    group_url: Optional[str] = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Executes a single monitoring and ingest cycle:
    1. Collects posts (from sample generator or public monitor adapter)
    2. Filters unseen posts using `tracker`
    3. Builds `LeadIngestPayload`
    4. Submits payload to Backend API (or simulates in dry-run)
    5. Updates deduplication tracker with ingested post IDs
    """
    iteration_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n[{iteration_time}] 🛰️  Scanning Facebook Target Group...")

    # 1. Collect posts
    if sample_mode:
        raw_posts = get_sample_posts(
            group_id=group_id,
            group_name=group_name,
            group_url=group_url,
            limit=limit,
        )
    else:
        # Use Real Playwright Scraper
        raw_posts = scrape_real_facebook_posts(
            group_id=group_id or "grp_public_monitor",
            group_name=group_name or "กลุ่มสาธารณะเป้าหมาย",
            group_url=group_url or "https://facebook.com/groups/public_monitor",
            limit=limit,
        )

    total_scanned = len(raw_posts)
    print(f"   ↳ 📋 Detected {total_scanned} candidate posts in feed")

    # 2. Filter unseen posts
    unseen_posts = tracker.filter_unseen(raw_posts)
    skipped_count = total_scanned - len(unseen_posts)
    if skipped_count > 0:
        print(f"   ↳ ⏭️  Deduplication: Skipped {skipped_count} already processed posts")

    if not unseen_posts:
        print("   ↳ ✅ No new unseen posts to ingest this round.")
        return {
            "ok": True,
            "total_scanned": total_scanned,
            "unseen_count": 0,
            "ingested_count": 0,
            "dry_run": dry_run,
            "response": None,
        }

    print(f"   ↳ 🚀 Packaging {len(unseen_posts)} new posts for ingestion...")
    payload = build_lead_payload(unseen_posts)

    # 3. Dry-Run Handling
    if dry_run:
        print("   ↳ 🧪 [DRY-RUN] Skipping HTTP submission. Prepared payload structure:")
        for idx, lead in enumerate(payload["leads"], 1):
            txt_preview = lead["post_text"][:60].replace("\n", " ") + ("..." if len(lead["post_text"]) > 60 else "")
            print(f"      {idx}. [{lead['fb_post_id']}] {lead['author_name'] or 'Anonymous'}: \"{txt_preview}\"")
        # In dry run, we still mark seen for memory tracking verification
        tracker.mark_seen_many(p["fb_post_id"] for p in payload["leads"])
        return {
            "ok": True,
            "total_scanned": total_scanned,
            "unseen_count": len(unseen_posts),
            "ingested_count": len(unseen_posts),
            "dry_run": True,
            "payload": payload,
            "response": None,
        }

    # 4. Submit to Backend API
    print(f"   ↳ 📡 Submitting payload to {api_url.rstrip('/')}/api/admin/facebook-radar/leads ...")
    resp = submit_leads_to_api(
        api_url=api_url,
        token=token,
        payload=payload,
        client=client,
    )

    if not resp.get("ok"):
        err_msg = resp.get("error") or "Unknown error"
        detail_msg = resp.get("detail") or ""
        print(f"   ↳ ❌ API Submission Error: {err_msg}")
        if detail_msg:
            print(f"      Detail: {detail_msg}")
        return {
            "ok": False,
            "total_scanned": total_scanned,
            "unseen_count": len(unseen_posts),
            "ingested_count": 0,
            "dry_run": False,
            "error": err_msg,
            "detail": detail_msg,
        }

    data = resp.get("data") or {}
    total_received = data.get("total_received", 0)
    processed = data.get("processed", 0)
    high_demand = data.get("high_demand_count", 0)
    alerts_sent = data.get("alerts_sent", 0)
    results = data.get("results", [])

    print(f"   ↳ ✨ Success! API Processed {processed}/{total_received} leads")
    print(f"      🔥 High Demand Deals: {high_demand} | 📲 LINE Alerts Sent: {alerts_sent}")

    for res in results:
        pid = res.get("fb_post_id", "")
        status = res.get("status", "")
        score = res.get("demand_score")
        alert_flag = "🔔 Alert Sent" if res.get("alert_sent") else "No Alert"
        if status == "deal_matched_and_alerted":
            print(f"      [✓ DEAL MATCHED] Post {pid} | Score {score} | {alert_flag}")
        elif status == "low_demand_ignored":
            print(f"      [• LOW DEMAND]   Post {pid} | Score {score} | Ignored")
        elif status == "already_processed":
            print(f"      [~ ALREADY SEEN] Post {pid} | Idempotent")
        else:
            print(f"      [? STATUS]       Post {pid} | Status: {status}")

    # Mark as seen locally
    tracker.mark_seen_many(p["fb_post_id"] for p in payload["leads"])
    if tracker.state_file:
        tracker.save_state()

    return {
        "ok": True,
        "total_scanned": total_scanned,
        "unseen_count": len(unseen_posts),
        "ingested_count": processed,
        "high_demand_count": high_demand,
        "alerts_sent": alerts_sent,
        "dry_run": False,
        "response": data,
    }


# ===========================================================================
# Argument Parser & CLI Entry Point
# ===========================================================================
def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local Facebook Group Monitor — Social Demand Radar V1 (บอทป้าเข็ม)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python tools/fb_group_monitor_local.py --sample --dry-run
  python tools/fb_group_monitor_local.py --sample --once
  python tools/fb_group_monitor_local.py --group-id grp_moms_th --interval 300
        """,
    )

    parser.add_argument(
        "--sample", "--mock",
        dest="sample",
        action="store_true",
        help="Use curated realistic Thai sample posts for testing/demonstration.",
    )
    parser.add_argument(
        "--group-id",
        type=str,
        default=None,
        help="Target Facebook group identifier (e.g. grp_moms_th).",
    )
    parser.add_argument(
        "--group-name",
        type=str,
        default=None,
        help="Target Facebook group name (e.g. 'กลุ่มแม่และเด็ก ของใช้แม่ลูก').",
    )
    parser.add_argument(
        "--group-url",
        type=str,
        default=None,
        help="Target Facebook group URL.",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=DEFAULT_API_URL,
        help=f"Base URL of FastAPI backend (default: {DEFAULT_API_URL}).",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Admin/Cron Auth Token for header X-Admin-Token or ?token= (reads from CRON_TOKEN / .env if omitted).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Polling interval in seconds (default: {DEFAULT_INTERVAL_SECONDS}s).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan iteration and exit immediately (useful for cron jobs or tests).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and generate payloads without sending HTTP requests to the backend.",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default=None,
        help=f"Path to JSON file storing seen post IDs (default: memory only, or {DEFAULT_STATE_FILE}).",
    )
    parser.add_argument(
        "--lock-file",
        type=str,
        default=DEFAULT_LOCK_FILE,
        help=f"Path to single-instance PID lock file (default: {DEFAULT_LOCK_FILE}; pass '' to disable).",
    )
    parser.add_argument(
        "--pid-timeout",
        type=int,
        default=0,
        help="Break a lock held by a process alive for more than this many minutes (0 = never; กัน monitor ค้างบล็อกการเริ่มใหม่).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of candidate posts to process per iteration.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed debug logging.",
    )

    return parser.parse_args(args)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    token = load_env_token(args.token)
    tracker = SeenPostTracker(state_file=args.state_file)

    # Single-instance lock: refuse to start if another monitor is already scanning.
    lock_ok, lock_msg = _acquire_monitor_lock(args.lock_file, pid_timeout_minutes=args.pid_timeout)
    if not lock_ok:
        print(lock_msg, file=sys.stderr)
        return 1
    if lock_msg:
        print(lock_msg)

    print("=" * 70)
    print("🎯  SOCIAL DEMAND RADAR V1 (บอทป้าเข็ม) — Facebook Group Monitor")
    print("=" * 70)
    print(f"📡 Backend API : {args.api_url.rstrip('/')}/api/admin/facebook-radar/leads")
    print(f"🔑 Auth Token  : {'[Configured]' if token else '[None / Local Bypass]'}")
    print(f"🧪 Sample Mode : {'Enabled (--sample)' if args.sample else 'Default Feed'}")
    print(f"⚡ Dry Run     : {'Yes (--dry-run)' if args.dry_run else 'No (Live HTTP)'}")
    print(f"⏱️  Run Mode    : {'Single Run (--once)' if args.once else f'Loop (every {args.interval}s)'}")
    if args.group_id:
        print(f"👥 Target Group: {args.group_id} ({args.group_name or 'No name'})")
    if args.state_file:
        print(f"💾 State File  : {args.state_file} ({tracker.count} posts tracked)")
    print("=" * 70)

    # Sweep zombie drivers from a previous hard-killed run (real scrape mode only).
    if not args.sample and not args.dry_run:
        swept = _sweep_orphan_drivers()
        if swept:
            print(f"🧹 Cleaned up {swept} orphaned monitor Chrome process(es) from a previous run.")

    # Loud warning for continuous loop mode — the #1 cause of "why is it still scanning?".
    if not args.once:
        print(f"⚠️  LOOP MODE: วิ่งวนไม่หยุดทุก {args.interval} วินาที จนกว่าจะกด Ctrl+C")
        print("   (ถ้าอยากรันครั้งเดียวแล้วจบ ให้เพิ่ม --once ด้วย)")

    try:
        while True:
            # If not in sample mode and no specific group URL was hardcoded via CLI
            if not args.sample and not args.group_url:
                print("   ↳ 📡 Fetching active groups from backend...")
                active_groups = fetch_active_groups_from_api(args.api_url, token)
                if not active_groups:
                    print("   ↳ ⚠️ No active Facebook groups found in database. Will retry next loop.")
                else:
                    print(f"   ↳ 👥 Loaded {len(active_groups)} active groups from backend.")
                    for g in active_groups:
                        run_monitor_iteration(
                            api_url=args.api_url,
                            token=token,
                            tracker=tracker,
                            sample_mode=False,
                            group_id=g.get("group_id"),
                            group_name=g.get("group_name"),
                            group_url=g.get("group_url"),
                            dry_run=args.dry_run,
                            limit=args.limit,
                        )
            else:
                # Fallback to single group CLI or sample mode
                run_monitor_iteration(
                    api_url=args.api_url,
                    token=token,
                    tracker=tracker,
                    sample_mode=args.sample,
                    group_id=args.group_id,
                    group_name=args.group_name,
                    group_url=args.group_url,
                    dry_run=args.dry_run,
                    limit=args.limit,
                )

            if args.once:
                break

            print(f"\n💤 Sleeping for {args.interval} seconds... (Press Ctrl+C to stop)")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n🛑 Monitor stopped by user (KeyboardInterrupt). Exiting cleanly.")
        if args.state_file:
            tracker.save_state()
        _release_monitor_lock(args.lock_file)
        return 0
    except Exception as e:
        print(f"\n❌ Unexpected error in monitor loop: {e}", file=sys.stderr)
        _release_monitor_lock(args.lock_file)
        return 1

    _release_monitor_lock(args.lock_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
