#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes AI — CLI สมองกลเรียนรู้ตลาด & วิเคราะห์ยอดสั่งซื้อปลาสลิดป้าเข็ม (รันมือ/เทสต์บนเครื่อง local)

วิเคราะห์:
1. `direct_orders` (ยอดสั่งซื้อปลาสลิดแดดเดียวสุพรรณแท้ ป้าเข็ม: แพ็กเกจขายดี, สัดส่วนโอนเงิน vs COD, ช่องทางที่ขายดี)
2. `chat_logs` + `facebook_demand_events` ย้อนหลัง 48 ชม.
→ Groq ปรับ skills → เก็บ system_preferences (Supabase) + เขียน MARKET_MEMORY.md

Usage:
    python tools/hermes_brain.py
"""
import io
import json
import pathlib
import sys
import traceback

if sys.stdout and getattr(sys.stdout, "encoding", "").lower() != "utf-8":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass

# เพิ่ม backend เข้า sys.path ให้ import app modules ได้ (รันจากที่ไหนก็ได้)
sys.path.insert(0, str(BACKEND_DIR))

from app.db import SessionLocal
from app.services.hermes_brain import analyze_market, format_market_memory


def main() -> int:
    db = SessionLocal()
    try:
        result = analyze_market(db)
        if result is None:
            print("[Hermes AI] ไม่สามารถเรียก LLM ได้ — ไม่ได้อัปเดต skills (คงของเดิม)")
            return 1

        fish = result.get("report", {}).get("fish_orders", {})
        skills = result.get("skills", {})
        print("=" * 60)
        print("🐟 [Hermes AI — สรุปยอดสั่งซื้อปลาสลิดป้าเข็ม & วิเคราะห์ตลาด]")
        print("=" * 60)
        print(f"• ยอดสั่งซื้อสะสมทั้งหมด: {fish.get('total_orders_all_time', 0)} ออเดอร์ "
              f"({fish.get('total_revenue_all_time', 0.0):,.2f} บาท)")
        print(f"• ยอดสั่งซื้อ 48 ชม. ล่าสุด: {fish.get('recent_orders_count', 0)} ออเดอร์ "
              f"({fish.get('recent_revenue', 0.0):,.2f} บาท)")
        print(f"• แพ็กเกจขายดีอันดับ 1: {fish.get('best_selling_package', '1kg')} "
              f"{fish.get('package_breakdown', {})}")
        print(f"• สัดส่วนการชำระเงิน: {fish.get('payment_breakdown', {})} "
              f"(COD {fish.get('cod_ratio_pct', 0.0)}%)")
        print(f"• ช่องทางสั่งซื้อ: {fish.get('channel_breakdown', {})}")
        print(f"• แพ็กเกจที่ Hermes แนะนำให้โปรโมท: {skills.get('fish_focus_package', '-')}")
        print(f"• กลยุทธ์ปลาสลิดจาก AI: {skills.get('fish_marketing_strategy', '-')}")
        print(f"• เหตุผลวิเคราะห์รวม: {result.get('reason', '')}")
        print(f"• Active Skills ล่าสุด: {json.dumps(skills, ensure_ascii=False)}")

        memory_path = ROOT_DIR / "MARKET_MEMORY.md"
        memory_path.write_text(format_market_memory(result), encoding="utf-8")
        print(f"[Hermes AI] เขียนบันทึกความจำ: {memory_path}")
        return 0
    except Exception:
        print("Error:", traceback.format_exc())
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
