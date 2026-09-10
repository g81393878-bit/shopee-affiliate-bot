"""Read-only Google Trends Thailand shortlist. No LLM, DB or posting calls."""
import argparse
import html
import json
import math
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.content_safety_filter import is_sensitive_forbidden_topic

FEED = "https://trends.google.com/trending/rss?geo=TH"
GROUPS = {
    "ของใช้ในบ้าน": ("แอร์", "เครื่องฟอก", "ฝุ่น", "เครื่องซัก", "ทำความสะอาด"),
    "สมาร์ตโฮม": ("สมาร์ตโฮม", "smart home", "กล้องวงจรปิด"),
    "สุขภาพ": ("สุขภาพ", "ออกกำลัง", "นอนหลับ"),
    "ความงาม": ("สกินแคร์", "กันแดด", "เครื่องสำอาง"),
    "ไอที": ("iphone", "ไอโฟน", "samsung", "มือถือ", "โน้ตบุ๊ก", "ipad", "apple watch", "airpods"),
    "สัตว์เลี้ยง": ("สัตว์เลี้ยง", "อาหารแมว", "อาหารสุนัข"),
    "เครื่องครัว": ("กระทะ", "หม้อ", "เครื่องครัว"),
    "อุปกรณ์ติดรถ": ("กล้องติดรถ", "อุปกรณ์รถ", "ยางรถ"),
    "ดาราและบันเทิง": ("ดารา", "นักร้อง", "ละคร", "ซีรีส์", "คอนเสิร์ต"),
    "คนทำงาน": ("ทำงาน", "ออฟฟิศ", "เงินเดือน", "excel"),
    "ความเชื่อ": ("ดูดวง", "ราศี", "สีเสื้อมงคล"),
}


def normalize(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", value).casefold())


def traffic_number(value):
    match = re.fullmatch(r"\s*([\d,.]+)\s*([KMB]?)\s*\+?\s*", value.upper())
    if not match:
        return None
    return int(float(match[1].replace(",", "")) * {"": 1, "K": 1000, "M": 1000000, "B": 1000000000}[match[2]])


def parse_feed(data):
    root = ET.fromstring(data)
    if root.tag != "rss":
        raise ValueError("Response is not an RSS feed")
    rows = []
    for item in root.findall("./channel/item"):
        def field(name):
            return next((e.text or "" for e in item.iter() if e.tag.rsplit("}", 1)[-1] == name), "")
        title = field("title").strip()
        if title:
            rows.append({"title": title, "traffic": field("approx_traffic"),
                         "published_at": field("pubDate"), "source_url": field("news_item_url"),
                         "source_title": field("news_item_title")})
    return rows


def history_titles(path):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    def walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "title" and isinstance(value, str):
                    yield value
                elif isinstance(value, (dict, list)):
                    yield from walk(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from walk(value)
    return list(walk(data))


def rank_topics(rows, history=(), now=None):
    now = now or datetime.now(timezone.utc)
    seen = set()
    previous = [normalize(t) for t in history]
    selected = []
    excluded = 0
    for row in rows:
        title = row["title"]
        key = normalize(title)
        duplicate = any(key == old or (min(len(key), len(old)) >= 18 and (key in old or old in key)) for old in previous)
        if key in seen or duplicate or is_sensitive_forbidden_topic(title + " " + row.get("source_title", "")):
            excluded += 1
            continue
        seen.add(key)
        category = next((group for group, words in GROUPS.items() if any(w in title.casefold() for w in words)), "ต้องตรวจหมวด")
        traffic = traffic_number(row.get("traffic", ""))
        try:
            published = parsedate_to_datetime(row.get("published_at", ""))
            age = (now - published).total_seconds() / 3600 if published.tzinfo else None
        except (ValueError, TypeError, OverflowError):
            age = None
        freshness = 30 * max(0, 1 - age / 48) if age is not None and age >= 0 else 0
        popularity = min(40, 8 * math.log10(max(1, traffic))) if traffic is not None else 0
        relevance = 30 if category != "ต้องตรวจหมวด" else 0
        reasons = [f"หมวด: {category}", f"ปริมาณค้นหาโดยประมาณ: {row.get('traffic') or 'ไม่ระบุ'}",
                   f"อายุรายการ {age:.1f} ชั่วโมง" if age is not None and age >= 0 else "เวลาไม่ทราบหรือผิดปกติ"]
        selected.append(dict(row, category=category, score=round(popularity + freshness + relevance, 1),
                             reasons=reasons, needs_review=True))
    selected.sort(key=lambda row: (-row["score"], row["title"]))
    return selected, excluded


def render_report(report):
    cards = []
    esc = html.escape
    for index, row in enumerate(report["topics"], 1):
        url = row.get("source_url", "")
        link = f'<a href="{esc(url, quote=True)}" rel="noreferrer">อ่านแหล่งข่าว</a>' if url.startswith("https://") else "ไม่มีลิงก์ข่าวที่ใช้ได้"
        cards.append(f'<article><b>#{index} · {row["score"]}/100</b><h2>{esc(row["title"])}</h2><p>{esc(" · ".join(row["reasons"]))}</p>{link}<p class="muted">ตรวจข้อเท็จจริงและความเกี่ยวข้องก่อนผลิต</p></article>')
    return f'''<!doctype html><html lang="th"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>หัวข้อแนะนำวันนี้</title>
<style>body{{font-family:Tahoma,sans-serif;background:#f0f4f8;color:#172b40;max-width:920px;margin:40px auto;padding:0 20px;line-height:1.7}}article{{background:white;padding:24px;margin:16px 0;border-radius:16px}}b,a{{color:#006c67}}h2{{margin:8px 0}}.muted{{color:#5c6875;font-size:14px}}</style>
<h1>หัวข้อแนะนำจาก Google Trends ประเทศไทย</h1><p>ดึงข้อมูล: {esc(report["fetched_at"])} · พบ {report["fetched_count"]} รายการ · กรองออก {report["excluded_count"]} รายการ</p>
<p>คะแนนจัดลำดับของระบบ: ปริมาณค้นหา 40 + ความสด 30 + ความเกี่ยวข้อง 30 คะแนน ไม่ใช่คะแนน Google หรือการคาดการณ์ยอดขาย</p>
<p class="muted">คำค้นมาแรงไม่ใช่อันดับคำค้นทั้งหมด · การตรวจซ้ำขั้นต้นใช้ชื่อและข้อความซ้อนกัน ต้องผ่านระบบตรวจซ้ำของโรงงานอีกครั้งก่อนผลิต</p>
{''.join(cards) or '<p>ไม่มีหัวข้อผ่านเกณฑ์ในรอบนี้</p>'}</html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "google_trends")
    parser.add_argument("--history", type=Path, default=ROOT / "tools" / "posted_content_history.json")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    request = urllib.request.Request(FEED, headers={"User-Agent": "PaKhemTrendReport/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        rows = parse_feed(response.read())
    topics, excluded = rank_topics(rows, history_titles(args.history))
    report = {"fetched_at": datetime.now(timezone.utc).isoformat(), "feed_url": FEED,
              "fetched_count": len(rows), "excluded_count": excluded, "topics": topics[:args.limit]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "latest.html").write_text(render_report(report), encoding="utf-8")
    print(json.dumps({"fetched": len(rows), "excluded": excluded, "recommended": len(report["topics"]),
                      "report": str(args.output_dir / "latest.html")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
