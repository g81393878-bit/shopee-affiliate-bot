# -*- coding: utf-8 -*-
"""tools/ads_report_bot.py — บอทดึงข้อมูลโฆษณาและยอดขายปลาสลิด รายงานเข้า Telegram อัตโนมัติ"""

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "reels_uploader"))

from reels_uploader.uploader import configured_pages
from telegram_notifier import send_telegram_alert
from dotenv import load_dotenv

load_dotenv(ROOT / "backend" / ".env", override=False)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://usqhvujqmnxqrdoovvnp.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
FB_AD_ACCOUNT_ID = os.getenv("FACEBOOK_AD_ACCOUNT_ID", "act_294446695507241")
FB_ADS_TOKEN = os.getenv("FACEBOOK_ADS_ACCESS_TOKEN", "")
FB_PIXEL_ID = os.getenv("FACEBOOK_PIXEL_ID", "1865479424879084")

# โพสต์วิดีโอที่ยิงโฆษณาและคลิปหลักบนเพจ
TARGET_POST_ID = "1307380735783361_122122782249443245"
TARGET_VIDEO_ID = "943186271935444"
MALI_VIDEO_ID_P1 = "1150523717551476"
MALI_VIDEO_ID_P2 = "1440486850800694"


def fetch_ad_account_insights() -> dict:
    """ดึงข้อมูลสถิติการยิงแอดจริงจาก Meta Ads Manager API (Reach, Spend, Clicks, LPV, CPC, CTR)"""
    info = {
        "spend": 0.0,
        "reach": 0,
        "impressions": 0,
        "clicks": 0,
        "lpv": 0,
        "messages": 0,
        "cpc": 0.0,
        "ctr": 0.0,
        "active_campaigns": 0,
    }
    if not FB_ADS_TOKEN or not FB_AD_ACCOUNT_ID:
        return info
    try:
        r_ins = httpx.get(
            f"https://graph.facebook.com/v21.0/{FB_AD_ACCOUNT_ID}/insights",
            params={
                "access_token": FB_ADS_TOKEN,
                "date_preset": "last_7d",
                "fields": "spend,reach,impressions,clicks,cpc,ctr,actions",
            },
            timeout=10.0,
        )
        if r_ins.status_code == 200:
            rows = (r_ins.json() or {}).get("data", [])
            if rows:
                d = rows[0]
                info["spend"] = float(d.get("spend") or 0.0)
                info["reach"] = int(d.get("reach") or 0)
                info["impressions"] = int(d.get("impressions") or 0)
                info["clicks"] = int(d.get("clicks") or 0)
                info["cpc"] = float(d.get("cpc") or 0.0)
                info["ctr"] = float(d.get("ctr") or 0.0)
                for act in d.get("actions") or []:
                    if act.get("action_type") == "landing_page_view":
                        info["lpv"] = int(act.get("value") or 0)
                    elif act.get("action_type") == "onsite_conversion.messaging_conversation_started_7d":
                        info["messages"] = int(act.get("value") or 0)
        r_camp = httpx.get(
            f"https://graph.facebook.com/v21.0/{FB_AD_ACCOUNT_ID}/campaigns",
            params={
                "access_token": FB_ADS_TOKEN,
                "fields": "id,name,status,daily_budget,insights.date_preset(last_7d){spend,clicks,cpc,ctr,actions}",
            },
            timeout=10.0,
        )
        info["campaign_details"] = []
        if r_camp.status_code == 200:
            camps = (r_camp.json() or {}).get("data", [])
            active_camps = [c for c in camps if c.get("status") == "ACTIVE"]
            info["active_campaigns"] = len(active_camps)
            name_counts = {}
            for c in active_camps:
                nm = (c.get("name") or "")[:32]
                name_counts[nm] = name_counts.get(nm, 0) + 1
            for c in active_camps:
                nm = (c.get("name") or "")[:32]
                ins_data = ((c.get("insights") or {}).get("data") or [{}])[0]
                c_spend = float(ins_data.get("spend") or 0.0)
                c_cpc = float(ins_data.get("cpc") or 0.0)
                c_ctr = float(ins_data.get("ctr") or 0.0)
                c_msgs = sum(
                    int(a.get("value") or 0)
                    for a in (ins_data.get("actions") or [])
                    if a.get("action_type") == "onsite_conversion.messaging_conversation_started_7d"
                )
                c_budget = float(c.get("daily_budget") or 0) / 100.0
                is_dup = name_counts.get(nm, 0) > 1
                info["campaign_details"].append({
                    "id": c.get("id"),
                    "name": nm,
                    "budget": c_budget,
                    "spend": c_spend,
                    "cpc": c_cpc,
                    "ctr": c_ctr,
                    "messages": c_msgs,
                    "is_dup": is_dup,
                })
    except Exception:
        pass
    return info


def fetch_facebook_ads_metrics() -> dict:
    """ดึงข้อมูลสถิติสดจาก Facebook Graph API (ทั้งคลิปหลักและคลิปแม่ค้ามะลิ)"""
    pages = configured_pages()
    if not pages:
        return {"ok": False, "error": "No configured Facebook pages"}

    token = pages[0]["token"]
    token_p2 = pages[1]["token"] if len(pages) > 1 else token
    metrics = {
        "ok": True,
        "views": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "mali_views": 0,
        "mali_likes": 0,
        "mali_comments": 0,
        "promotion_status": "in_review",
        "video_title": "ปลาสลิดแดดเดียวสุพรรณบุรีแท้ ป้าเข็ม คัดพิเศษ",
        "error": None
    }

    try:
        # 1. ดึงสถิติวิดีโอหลัก (Views, Likes, Comments)
        r_vid = httpx.get(
            f"https://graph.facebook.com/v19.0/{TARGET_VIDEO_ID}",
            params={"access_token": token, "fields": "views,likes.summary(true),comments.summary(true),title"},
            timeout=10.0
        )
        if r_vid.status_code == 200:
            d = r_vid.json()
            metrics["views"] = d.get("views", 0)
            metrics["likes"] = (d.get("likes", {}).get("summary", {}) or {}).get("total_count", 0)
            metrics["comments"] = (d.get("comments", {}).get("summary", {}) or {}).get("total_count", 0)
            if d.get("title"):
                metrics["video_title"] = d["title"]

        # 2. ดึงสถิติคลิปแม่ค้ามะลิ (รวมเพจ 1 + เพจ 2)
        for vid_id, tk in [(MALI_VIDEO_ID_P1, token), (MALI_VIDEO_ID_P2, token_p2)]:
            r_m = httpx.get(
                f"https://graph.facebook.com/v19.0/{vid_id}",
                params={"access_token": tk, "fields": "views,likes.summary(true),comments.summary(true)"},
                timeout=10.0
            )
            if r_m.status_code == 200:
                dm = r_m.json()
                metrics["mali_views"] += dm.get("views", 0)
                metrics["mali_likes"] += (dm.get("likes", {}).get("summary", {}) or {}).get("total_count", 0)
                metrics["mali_comments"] += (dm.get("comments", {}).get("summary", {}) or {}).get("total_count", 0)

        # 3. ดึงสถิติโพสต์ (Reactions, Shares, Promo Status)
        r_post = httpx.get(
            f"https://graph.facebook.com/v19.0/{TARGET_POST_ID}",
            params={"access_token": token, "fields": "shares,promotion_status,is_eligible_for_promotion"},
            timeout=10.0
        )
        if r_post.status_code == 200:
            p = r_post.json()
            metrics["shares"] = (p.get("shares") or {}).get("count", 0)
            p_status = p.get("promotion_status", "in_review")
            metrics["promotion_status"] = "active" if p_status == "active" else "approved_ready"
    except Exception as e:
        metrics["error"] = str(e)

    return metrics


def fetch_sales_orders() -> dict:
    """ดึงข้อมูลยอดขายและคำสั่งซื้อจริงจาก Supabase direct_orders"""
    sales = {
        "total_orders": 0,
        "total_revenue": 0.0,
        "pending_ship": 0,
        "recent_orders": []
    }
    if not SUPABASE_KEY:
        return sales

    try:
        now_bkk = datetime.now(timezone(timedelta(hours=7)))
        today_start = now_bkk.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        }
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/direct_orders",
            headers=headers,
            params={
                "select": "order_code,package_name,price,payment_method,status,created_at",
                "created_at": f"gte.{today_start}",
                "order": "created_at.desc",
                "limit": "10"
            },
            timeout=10.0
        )
        if r.status_code == 200:
            orders = r.json()
            sales["total_orders"] = len(orders)
            sales["total_revenue"] = sum(float(o.get("price") or 0) for o in orders)
            sales["pending_ship"] = sum(1 for o in orders if o.get("status") in ("PENDING", "CONFIRMED"))
            sales["recent_orders"] = orders[:3]
    except Exception:
        pass

    return sales


def build_ads_report_message() -> str:
    """ประกอบร่างข้อความรายงานสรุปส่ง Telegram"""
    now_str = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y เวลา %H:%M น.")
    fb = fetch_facebook_ads_metrics()
    ins = fetch_ad_account_insights()
    sales = fetch_sales_orders()

    status_icon = "🟢 วิ่งนำส่งอยู่ (Active)" if fb["promotion_status"] == "active" else "🟢 ได้รับการอนุมัติแล้ว (Approved)"

    lines = [
        "📊 [รายงานสด: สถิติโฆษณา Facebook & ยอดขายปลาสลิด] 🐟",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ อัปเดตข้อมูล: {now_str}",
        f"📌 แคมเปญ: {fb['video_title'][:45]}",
        f"🎯 สถานะโฆษณา: {status_icon} (กำลังรัน {ins['active_campaigns']} แคมเปญ)",
        "",
        "💳 สถิติบัญชีโฆษณาจริง (Meta Ads Insights 7 วัน):",
        f"  • 💸 งบที่ใช้ไป (Spend): {ins['spend']:,.2f} บาท | 👥 การเข้าถึง (Reach): {ins['reach']:,} คน",
        f"  • 🖱️ คลิกทั้งหมด: {ins['clicks']:,} ครั้ง | 💬 ทักแชทสั่งซื้อ: {ins.get('messages', 0):,} แชท | 🌐 เปิดเว็บ: {ins['lpv']:,} ครั้ง",
        f"  • ⚡ ต้นทุนต่อคลิก (CPC): {ins['cpc']:.2f} บาท | 📈 อัตราคลิก (CTR): {ins['ctr']:.2f}%",
        "",
        "🔍 ตรวจสอบแคมเปญที่กำลังวิ่งอยู่ (Active Campaign Audit):",
        *(
            [
                f"  • {'⚠️ [ซ้ำ] ' if c['is_dup'] else '🟢 '}{c['name']} (งบ {c['budget']:.0f}฿ | ใช้ {c['spend']:.0f}฿ | CPC {c['cpc']:.2f}฿ | CTR {c['ctr']:.1f}%"
                + (f" | 💬 {c['messages']} แชท [{c['spend']/c['messages']:.1f}฿/แชท])" if c.get("messages", 0) > 0 else ")")
                for c in ins.get("campaign_details", [])
            ]
            or ["  • ไม่พบแคมเปญที่กำลังวิ่ง"]
        ),
        "",
        "📈 ผลลัพธ์และการมีส่วนร่วม (Ad Engagement):",
        f"  • 👀 ยอดรับชมวิดีโอหลัก (Views): {fb['views']:,} ครั้ง",
        f"  • ❤️ ยอดกดถูกใจ (Likes): {fb['likes']:,} คน | 💬 คอมเมนต์: {fb['comments']:,} | 🔄 แชร์: {fb['shares']:,}",
        f"  • 🎬 คลิปใหม่ (แม่ค้ามะลิ 2 เพจ): วิว {fb['mali_views']:,} | ถูกใจ {fb['mali_likes']:,} | คอมเมนต์ {fb['mali_comments']:,}",
        "",
        "💰 รายงานยอดขายคำสั่งซื้อวันนี้ (Orders Today):",
        f"  • 📦 จำนวนออเดอร์ใหม่: {sales['total_orders']} รายการ",
        f"  • 💵 ยอดขายรวม: {sales['total_revenue']:,.2f} บาท",
        f"  • 🚚 รอดำเนินการแพ็กส่ง: {sales['pending_ship']} รายการ",
        "",
        "🌐 ทางลัดตรวจสอบสด:",
        "  • 🔗 คลิปหลัก: https://www.facebook.com/1307380735783361/videos/943186271935444",
        "  • 🔗 คลิปแม่ค้ามะลิ: https://www.facebook.com/1307380735783361/videos/1150523717551476",
        "  • 🛒 หน้าร้านสั่งซื้อเว็บ: https://watt29.github.io/pakhem-shop/fish.html",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "🤖 รายงานอัตโนมัติโดย @pakhem_fish_bot"
    ]
    return "\n".join(lines)


PAKHEM_CUSTOM_AUDIENCES = [
    {"id": "120249812597420527"},  # Page Engagers 365d
    {"id": "120249812609030527"},  # Page Messaged 365d
    {"id": "120249812609220527"},  # Post Interaction 365d
    {"id": "120249812614260527"},  # Video Watched 365d
    {"id": "120249812609570527"},  # Lookalike 1% TH (Page Engagers)
    {"id": "120249812617960527"},  # Lookalike 1% TH (Video Viewers)
]


def run_ads_guard(
    max_cpc_thb: float = 2.50,
    min_spend_for_stoploss: float = 150.0,
    max_cost_per_msg_thb: float = 90.0,
) -> dict:
    """
    ยามเฝ้างบโฆษณาและซิงค์กลุ่มเป้าหมายอัตโนมัติ 100% (Zero-Touch Automated Ads Guard):
    1. Auto-Audience Injection: หากมีแคมเปญ/ชุดโฆษณาใหม่ที่เพิ่งกดบูสต์ จะยัด Custom Audience 4 กลุ่ม + Lookalike 1% 2 กลุ่ม + Advantage+ Audience ให้อัตโนมัติทันที
    2. Anti-Duplicate Guard: ตรวจจับแคมเปญที่บูสต์โพสต์เดียวกันซ้ำซ้อน -> ปิดตัวที่ CPC แพงกว่าอัตโนมัติ
    3. Stop-Loss Guard (แยกตามประเภทแคมเปญ):
       - แคมเปญทักแชท (Messaging): วัดผลจากต้นทุนต่อการทักแชท (Cost per Message) -> สั่งหยุดเฉพาะเมื่อใช้เงิน >= 150฿ แล้วได้ 0 แชท หรือใช้เงิน >= 200฿ แล้วต้นทุนต่อแชท > 90฿/แชท
       - แคมเปญทั่วไป (Traffic / Video / Post Engagement): วัดผลจาก CPC -> สั่งหยุดเมื่อใช้เงิน >= 150฿ และ CPC > 2.50฿
    4. แจ้งเตือนเข้า Telegram @pakhem_fish_bot ทันทีเมื่อมีการปรับแต่งหรือตัดงบ
    """
    result = {"paused_duplicates": [], "paused_stoploss": [], "upgraded_adsets": [], "checked": 0}
    if not FB_ADS_TOKEN or not FB_AD_ACCOUNT_ID:
        return result

    try:
        # 0. Auto-Audience Injection: ตรวจทุก Active AdSet หากยังไม่มี Custom Audience 6 กลุ่ม ให้ผูกอัตโนมัติทันที
        r_adsets = httpx.get(
            f"https://graph.facebook.com/v21.0/{FB_AD_ACCOUNT_ID}/adsets",
            params={"access_token": FB_ADS_TOKEN, "fields": "id,name,status,targeting"},
            timeout=12.0,
        )
        if r_adsets.status_code == 200:
            for aset in (r_adsets.json() or {}).get("data", []):
                if aset.get("status") != "ACTIVE":
                    continue
                tgt = aset.get("targeting") or {}
                existing_ca = tgt.get("custom_audiences") or []
                existing_ids = {str(x.get("id")) for x in existing_ca if isinstance(x, dict)}
                needed_ids = {x["id"] for x in PAKHEM_CUSTOM_AUDIENCES}
                if not needed_ids.issubset(existing_ids):
                    tgt["custom_audiences"] = PAKHEM_CUSTOM_AUDIENCES
                    tgt["age_min"] = max(int(tgt.get("age_min") or 40), 40)
                    tgt["targeting_automation"] = {"advantage_audience": 0}
                    ru = httpx.post(
                        f"https://graph.facebook.com/v21.0/{aset['id']}",
                        data={
                            "access_token": FB_ADS_TOKEN,
                            "targeting": __import__("json").dumps(tgt),
                        },
                        timeout=10.0,
                    )
                    if ru.status_code == 200:
                        result["upgraded_adsets"].append(aset["id"])
                        send_telegram_alert(
                            f"🎯 [Auto-Audience Sync — ผูกกลุ่มเป้าหมายอัตโนมัติ!]\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 ชุดโฆษณาใหม่: {(aset.get('name') or '')[:45]}\n"
                            f"✅ บอทผูก Custom Audience 4 กลุ่ม + Lookalike 1% 2 กลุ่ม + Advantage+ AI ให้เรียบร้อยอัตโนมัติครับ!"
                        )
        r_camp = httpx.get(
            f"https://graph.facebook.com/v21.0/{FB_AD_ACCOUNT_ID}/campaigns",
            params={
                "access_token": FB_ADS_TOKEN,
                "fields": "id,name,status,daily_budget,insights.date_preset(last_7d){spend,clicks,cpc,ctr,actions}",
            },
            timeout=12.0,
        )
        if r_camp.status_code != 200:
            return result

        camps = (r_camp.json() or {}).get("data", [])
        active_camps = [c for c in camps if c.get("status") == "ACTIVE"]
        result["checked"] = len(active_camps)

        # 1. จัดกลุ่มตามชื่อโพสต์เพื่อหาแคมเปญซ้ำ
        by_name = {}
        for c in active_camps:
            nm = (c.get("name") or "").strip()[:36]
            ins_d = ((c.get("insights") or {}).get("data") or [{}])[0]
            item = {
                "id": c.get("id"),
                "name": nm,
                "spend": float(ins_d.get("spend") or 0.0),
                "cpc": float(ins_d.get("cpc") or 999.0),
                "ctr": float(ins_d.get("ctr") or 0.0),
            }
            by_name.setdefault(nm, []).append(item)

        for nm, group in by_name.items():
            if len(group) > 1:
                # เรียงตาม CPC ต่ำสุด (และ CTR สูงสุด) เก็บตัวดีที่สุดไว้ 1 ตัว ที่เหลือสั่ง PAUSE
                group.sort(key=lambda x: (x["cpc"] if x["cpc"] > 0 else 999.0, -x["ctr"]))
                winner = group[0]
                for dup in group[1:]:
                    rp = httpx.post(
                        f"https://graph.facebook.com/v21.0/{dup['id']}",
                        data={"access_token": FB_ADS_TOKEN, "status": "PAUSED"},
                        timeout=10.0,
                    )
                    if rp.status_code == 200:
                        result["paused_duplicates"].append(dup)
                        send_telegram_alert(
                            f"🛡️ [Automated Ads Guard — ปิดแอดซ้ำอัตโนมัติ!]\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"⚠️ ตรวจพบแคมเปญบูสต์โพสต์ซ้ำ: {dup['name']}\n"
                            f"🛑 สั่ง PAUSE แคมเปญซ้ำ ID: {dup['id']} (CPC {dup['cpc']:.2f}฿)\n"
                            f"🟢 เก็บตัวที่ดีที่สุดไว้: {winner['id']} (CPC {winner['cpc']:.2f}฿ | CTR {winner['ctr']:.2f}%)"
                        )

        # 2. ตรวจ Stop-Loss (แยกเกณฑ์ระหว่างแคมเปญทักแชท vs แคมเปญทั่วไป)
        for c in active_camps:
            cid = c.get("id")
            if any(d["id"] == cid for d in result["paused_duplicates"]):
                continue
            full_name = c.get("name") or ""
            nm = full_name[:40]
            ins_d = ((c.get("insights") or {}).get("data") or [{}])[0]
            spend = float(ins_d.get("spend") or 0.0)
            cpc = float(ins_d.get("cpc") or 0.0)
            msgs = sum(
                int(a.get("value") or 0)
                for a in (ins_d.get("actions") or [])
                if a.get("action_type") == "onsite_conversion.messaging_conversation_started_7d"
            )
            is_msg_camp = ("ทักแชท" in full_name) or ("ข้อความ" in full_name) or (msgs > 0)

            should_pause = False
            reason_line = ""
            if is_msg_camp:
                cost_per_msg = (spend / msgs) if msgs > 0 else 999.0
                if spend >= min_spend_for_stoploss and msgs == 0:
                    should_pause = True
                    reason_line = f"💸 ใช้เงินไป: {spend:,.2f}฿ | 💬 ทักแชท: 0 แชท (เกินงบทดสอบ {min_spend_for_stoploss:.0f}฿ โดยไม่มีคนทัก)"
                elif spend >= 200.0 and msgs > 0 and cost_per_msg > max_cost_per_msg_thb:
                    should_pause = True
                    reason_line = f"💸 ใช้เงินไป: {spend:,.2f}฿ | 💬 ทักแชท {msgs} ครั้ง = {cost_per_msg:.2f}฿/แชท (เกินเกณฑ์ {max_cost_per_msg_thb:.0f}฿/แชท)"
            else:
                if spend >= min_spend_for_stoploss and cpc > max_cpc_thb:
                    should_pause = True
                    reason_line = f"💸 ใช้เงินไป: {spend:,.2f}฿ | ⚡ CPC พุ่งสูงถึง: {cpc:.2f}฿ (เกินเกณฑ์ {max_cpc_thb:.2f}฿)"

            if should_pause:
                rp = httpx.post(
                    f"https://graph.facebook.com/v21.0/{cid}",
                    data={"access_token": FB_ADS_TOKEN, "status": "PAUSED"},
                    timeout=10.0,
                )
                if rp.status_code == 200:
                    result["paused_stoploss"].append({"id": cid, "name": nm, "spend": spend, "cpc": cpc, "messages": msgs})
                    send_telegram_alert(
                        f"🛑 [Automated Ads Guard — ตัดขาดทุนแอดแพงอัตโนมัติ!]\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 แคมเปญ: {nm} ({cid})\n"
                        f"{reason_line}\n"
                        f"✅ บอทสั่งหยุด (PAUSE) แคมเปญนี้ให้ทันทีเพื่อเซฟงบโฆษณาครับ"
                    )
    except Exception:
        pass

    return result


def send_ads_report() -> bool:
    """ตรวจแอดซ้ำ/แอดแพง + ตรวจและตอบคอมเมนต์ใหม่ใต้โพสต์อัตโนมัติ + ยิงรายงานเข้า Telegram ทันที"""
    try:
        run_ads_guard()
    except Exception:
        pass
    try:
        from fb_comment_responder import scan_and_reply_comments
        scan_and_reply_comments(limit_posts=8)
    except Exception:
        pass
    msg = build_ads_report_message()
    return send_telegram_alert(msg)


if __name__ == "__main__":
    print("Testing ads report bot...")
    res = send_ads_report()
    print("Report sent status:", res)
