#!/usr/bin/env python3
"""Local performance learning from verified database metrics; no LLM calls."""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv
load_dotenv(ROOT / "backend/.env")

from app import models
from app.db import SessionLocal
from sqlalchemy import func

OUTPUT = ROOT / "artifacts/product_learning/scores.json"
STATE = ROOT / "artifacts/product_learning/state.json"
ICT = timezone(timedelta(hours=7))


def metric_score(views=0, clicks=0, orders=0, commission=0.0):
    """Return a confidence weighted 0..100 score from observed outcomes."""
    views = max(0, int(views or 0)); clicks = max(0, int(clicks or 0))
    orders = max(0, int(orders or 0)); commission = max(0.0, float(commission or 0))
    ctr = clicks / views if views else 0.0
    conversion = orders / clicks if clicks else 0.0
    epc = commission / clicks if clicks else 0.0
    confidence = min(1.0, math.log10(views + 1) / 4.0)
    raw = min(35.0, ctr * 350.0) + min(35.0, conversion * 175.0) + min(30.0, epc * 3.0)
    return round(raw * confidence, 3)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def collect_scores(db=None):
    own_db = db is None
    db = db or SessionLocal()
    try:
        rows = (db.query(
                    models.Product.id, models.Product.name, models.Product.category,
                    func.coalesce(func.sum(models.PerformanceLog.views), 0),
                    func.coalesce(func.sum(models.PerformanceLog.clicks), 0),
                    func.coalesce(func.sum(models.PerformanceLog.orders), 0),
                    func.coalesce(func.sum(models.PerformanceLog.commission), 0))
                .join(models.Content, models.Content.product_id == models.Product.id)
                .join(models.PerformanceLog, models.PerformanceLog.content_id == models.Content.id)
                .group_by(models.Product.id, models.Product.name, models.Product.category).all())
        products = {}
        category_totals = {}
        for pid, name, category, views, clicks, orders, commission in rows:
            values = {"views": int(views), "clicks": int(clicks), "orders": int(orders),
                      "commission": float(commission),
                      "score": metric_score(views, clicks, orders, commission)}
            values["ctr_pct"] = round(values["clicks"] / values["views"] * 100, 3) if values["views"] else 0.0
            values["conversion_pct"] = round(values["orders"] / values["clicks"] * 100, 3) if values["clicks"] else 0.0
            values["name"] = name or ""; values["category"] = category or "อื่นๆ"
            products[str(pid)] = values
            bucket = category_totals.setdefault(values["category"], {"views": 0, "clicks": 0, "orders": 0, "commission": 0.0})
            for key in ("views", "clicks", "orders", "commission"):
                bucket[key] += values[key]
        for bucket in category_totals.values():
            bucket["score"] = metric_score(**bucket)
        result = {"generated_at": datetime.now(ICT).isoformat(), "source": "supabase_performance_logs",
                  "products": products, "categories": category_totals}
        _write_json(OUTPUT, result)
        return result
    finally:
        if own_db:
            db.close()


def build_report(data):
    products = sorted(data.get("products", {}).items(), key=lambda item: item[1].get("score", 0), reverse=True)
    totals = {key: sum(item[1].get(key, 0) for item in products)
              for key in ("views", "clicks", "orders", "commission")}
    ctr = totals["clicks"] / totals["views"] * 100 if totals["views"] else 0
    conversion = totals["orders"] / totals["clicks"] * 100 if totals["clicks"] else 0
    lines = ["📊 รายงานเรียนรู้ผลงานสินค้า", f"• ยอดดู: {totals['views']:,}",
             f"• คลิก: {totals['clicks']:,} (CTR {ctr:.2f}%)",
             f"• คำสั่งซื้อ: {totals['orders']:,} (Conversion {conversion:.2f}%)",
             f"• ค่าคอม: {totals['commission']:,.2f} บาท"]
    if products:
        lines.append("🏆 สินค้าที่ระบบจะให้น้ำหนักเพิ่ม")
        for pid, row in products[:3]:
            lines.append(f"• รหัส {pid}: {row['name'][:35]} — คะแนน {row['score']:.1f}")
    else:
        lines.append("• ยังไม่มี performance log สำหรับเรียนรู้ ระบบยังใช้คะแนนข้อมูลสินค้า")
    return "\n".join(lines)


def run_once(notify=False):
    data = collect_scores()
    if notify:
        from telegram_notifier import send_telegram_alert
        send_telegram_alert(build_report(data), throttle_key="daily_product_learning", cooldown_seconds=43200)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    result = run_once(notify=args.notify)
    print(json.dumps({"products": len(result["products"]), "categories": len(result["categories"]),
                      "output": str(OUTPUT)}, ensure_ascii=False))
