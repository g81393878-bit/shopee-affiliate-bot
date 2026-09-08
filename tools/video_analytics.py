# -*- coding: utf-8 -*-
"""tools/video_analytics.py — บันทึกและวิเคราะห์ข้อมูลการโพสต์แยก Category/Platform/Mode"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
ANALYTICS_FILE = ROOT_DIR / "tools" / "video_analytics.jsonl"
TZ_BKK = timezone(timedelta(hours=7))


def log_video_posted(
    product_id,
    category: str,
    platform: str,
    video_path: str,
    content_mode: str = "PRODUCT_HIGHLIGHT",
    extra: Optional[dict] = None
) -> None:
    """บันทึกการโพสต์วิดีโอ 1 รายการ — ทุกแพลตฟอร์ม append ลง JSONL"""
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"):
        return
    record = {
        "posted_at": datetime.now(TZ_BKK).isoformat(),
        "product_id": product_id,
        "category": category or "unknown",
        "platform": platform,
        "content_mode": content_mode,
        "video_file": Path(video_path).name if video_path else "",
    }
    if extra:
        record.update(extra)
    try:
        ANALYTICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ANALYTICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[video_analytics] warning: {e}", flush=True)


def get_weekly_summary(days: int = 7) -> dict:
    """สรุปจำนวนคลิปแยก Category/Platform/Mode ใน N วันล่าสุด"""
    if not ANALYTICS_FILE.exists():
        return {"period_days": days, "total_posts": 0, "by_category": {}, "by_platform": {}, "by_mode": {}}
    cutoff = datetime.now(TZ_BKK) - timedelta(days=days)
    by_category: defaultdict = defaultdict(int)
    by_platform: defaultdict = defaultdict(int)
    by_mode: defaultdict = defaultdict(int)
    total = 0
    try:
        with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    posted_at = datetime.fromisoformat(rec.get("posted_at", ""))
                    if posted_at.tzinfo is None:
                        posted_at = posted_at.replace(tzinfo=TZ_BKK)
                    if posted_at < cutoff:
                        continue
                    total += 1
                    by_category[rec.get("category", "unknown")] += 1
                    by_platform[rec.get("platform", "unknown")] += 1
                    by_mode[rec.get("content_mode", "unknown")] += 1
                except Exception:
                    continue
    except Exception as e:
        print(f"[video_analytics] read error: {e}", flush=True)
    return {
        "period_days": days,
        "total_posts": total,
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "by_platform": dict(sorted(by_platform.items(), key=lambda x: -x[1])),
        "by_mode": dict(sorted(by_mode.items(), key=lambda x: -x[1])),
    }


def print_weekly_report(days: int = 7) -> None:
    """พิมพ์รายงาน Analytics แบบสวยงาม"""
    s = get_weekly_summary(days)
    sep = "=" * 55
    print(f"\n{sep}\nVideo Analytics — {days} days\nTotal: {s['total_posts']} clips\n{sep}")
    print("By Category:")
    for cat, cnt in list(s["by_category"].items())[:10]:
        print(f"  {cat[:30]:<30} {cnt}")
    print("\nBy Platform:")
    for plat, cnt in s["by_platform"].items():
        print(f"  {plat:<22} {cnt}")
    print("\nBy Mode:")
    for mode, cnt in s["by_mode"].items():
        pct = round(cnt / max(s["total_posts"], 1) * 100)
        print(f"  {mode:<25} {cnt} clips ({pct}%)")
    print(sep)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    print_weekly_report(args.days)
