# -*- coding: utf-8 -*-
"""tools/tiktok_promo_presets.py — ชุดเติมแฮชแท็กสำหรับ TikTok อัตโนมัติ (TikTok Viral Hashtag Presets)

หมุนเวียนชุดแฮชแท็กยอดนิยมอัตโนมัติ:
- ดึงดูดคนดูบนหน้าฟีด For You (FYP) ด้วย #เรื่องนี้ต้องดู #เทรนด์วันนี้
- ขยายเครือข่ายผู้ติดตามด้วย #ติดตามมาติดตามกลับ (Mutual Follow Community)
- สลับหมุนเวียน 6 ชุด ป้องกันปัญหา Shadowban จากการใช้แท็กซ้ำ 100%
"""
import re
import sys
from typing import Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TIKTOK_PROMO_PRESETS: List[Dict[str, str]] = [
    {
        "id": "set_1_trend_viral",
        "name": "ชุดที่ 1: เทรนด์วันนี้ & สายแลกฟอลไวรัล",
        "promo_text": "",
        "hashtags": "#เทรนด์วันนี้ #เรื่องนี้ต้องดู #เทรนด์วันนี้tiktok #ติดตามมาติดตามกลับ #fyp",
    },
    {
        "id": "set_2_trending_now",
        "name": "ชุดที่ 2: เทรนด์วันนี้ & กระแสมาแรง",
        "promo_text": "",
        "hashtags": "#เทรนวันนี้ #เรื่องนี้ต้องดู #เทรนด์วันนี้tiktok #ติดตามมาติดตามกลับ #ไวรัล",
    },
    {
        "id": "set_3_knowledge_tips",
        "name": "ชุดที่ 3: สาระน่ารู้ & เรื่องนี้ต้องดู",
        "promo_text": "",
        "hashtags": "#สาระน่ารู้ #เรื่องนี้ต้องดู #เทรนด์วันนี้ #เทรนด์วันนี้tiktok #ติดตามมาติดตามกลับ",
    },
    {
        "id": "set_4_curated_picks",
        "name": "ชุดที่ 4: ของดีบอกต่อ & ป้ายยา",
        "promo_text": "",
        "hashtags": "#ของดีบอกต่อ #เรื่องนี้ต้องดู #เทรนด์วันนี้tiktok #ติดตามมาติดตามกลับ #ป้ายยา",
    },
    {
        "id": "set_5_daily_trends",
        "name": "ชุดที่ 5: เทรนด์ประจำวัน & ความรู้รอบตัว",
        "promo_text": "",
        "hashtags": "#เทรนด์วันนี้ #เทรนด์วันนี้tiktok #เรื่องนี้ต้องดู #ติดตามมาติดตามกลับ #ความรู้รอบตัว",
    },
    {
        "id": "set_6_share_community",
        "name": "ชุดที่ 6: ชุมชนแชร์ความรู้ & เรื่องเด็ด",
        "promo_text": "",
        "hashtags": "#เรื่องนี้ต้องดู #เทรนด์วันนี้ #ติดตามมาติดตามกลับ #เทรนด์วันนี้tiktok #แชร์ต่อ",
    },
]


def get_promo_preset(index: int = 0) -> Dict[str, str]:
    """ดึงชุด Preset ตามลำดับ index หมุนเวียน Round-Robin"""
    return TIKTOK_PROMO_PRESETS[index % len(TIKTOK_PROMO_PRESETS)]


def get_tiktok_promo_addon(index: int = 0) -> str:
    """สร้างแฮชแท็กพร้อมใช้งาน"""
    preset = get_promo_preset(index)
    if preset.get("promo_text"):
        return f"{preset['promo_text']}\n{preset['hashtags']}"
    return preset["hashtags"]


def format_tiktok_caption(base_caption: str, index: int = 0) -> str:
    """นำแคปชั่นต้นทางมาผสานเข้ากับชุดแฮชแท็ก TikTok อัตโนมัติ ป้องกันคำซ้ำ"""
    clean_base = (base_caption or "").strip()
    preset = get_promo_preset(index)
    
    # ถ้าในแคปชั่นมีแฮชแท็กหลักอยู่แล้ว จะไม่ใส่ซ้ำ
    if "#ติดตามมาติดตามกลับ" in clean_base:
        return clean_base
    
    addon = preset["hashtags"]
    if preset.get("promo_text"):
        addon = f"{preset['promo_text']}\n{preset['hashtags']}"
        
    if clean_base:
        return f"{clean_base}\n\n{addon}"
    return addon


if __name__ == "__main__":
    print("✨ รายชื่อชุดแฮชแท็ก TikTok ทั้งหมด (6 ชุดหมุนเวียน):")
    for i, p in enumerate(TIKTOK_PROMO_PRESETS, start=1):
        print(f"\n[{i}] {p['name']}")
        print(f"👉 แฮชแท็ก: {p['hashtags']}")
    
    print("\n--- ตัวอย่างแคปชั่นจริงเมื่อผสานเข้ากับคลิป ---")
    sample = format_tiktok_caption("✨ 3 วิธีจัดตู้เสื้อผ้าให้จุของเพิ่ม 3 เท่า", index=0)
    print(sample)
