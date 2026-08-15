#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes AI — CLI สมองกลเรียนรู้ตลาด (รันมือ/เทสต์บนเครื่อง local)

วิเคราะห์ chat_logs + facebook_demand_events ย้อนหลัง 48 ชม. → Groq ปรับ skills
→ เก็บ system_preferences (Supabase) + เขียน MARKET_MEMORY.md

Production (Render) ควรเรียกผ่าน cron endpoint แทน (M2); สคริปต์นี้ใช้ dev/local.

Usage (ตั้ง DATABASE_URL ก่อนรัน production):
    python tools/hermes_brain.py
"""
import json
import pathlib
import sys
import traceback

# เพิ่ม backend เข้า sys.path ให้ import app modules ได้ (รันจากที่ไหนก็ได้)
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.db import SessionLocal
from app.services.hermes_brain import analyze_market, format_market_memory


def main() -> int:
    db = SessionLocal()
    try:
        result = analyze_market(db)
        if result is None:
            print("[Hermes AI] ไม่สามารถเรียก LLM ได้ — ไม่ได้อัปเดต skills (คงของเดิม)")
            return 1
        print(f"[Hermes AI] อัปเดต skills สำเร็จ: "
              f"{json.dumps(result['skills'], ensure_ascii=False)}")
        print(f"[Hermes AI] เหตุผล: {result.get('reason', '')}")
        memory_path = pathlib.Path(__file__).resolve().parent.parent / "MARKET_MEMORY.md"
        memory_path.write_text(format_market_memory(result), encoding="utf-8")
        print(f"[Hermes AI] เขียนบันทึก: {memory_path}")
        return 0
    except Exception:
        print("Error:", traceback.format_exc())
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
