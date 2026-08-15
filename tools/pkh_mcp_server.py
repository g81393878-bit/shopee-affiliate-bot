#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pkh_mcp — MCP server ที่ expose Admin API ของบอทป้าเข็ม (Shopee affiliate bot)
================================================================================
ให้ AI agent (Claude Code / Cursor / …) อ่านและจัดการข้อมูลร้านผ่าน MCP tools:
- สินค้า  (products): ค้น/กรอง/เพิ่ม/แก้/ลบ
- สถิติ   (stats / categories / radar stats)
- ประวัติโพสต์เรดาร์ (radar feed / leads / cooldown)

Auth: ต่อ production admin API ด้วย secret แอดมิน — server เรียก `POST /admin/login`
เอา cookie `pkh_admin` (HMAC, อายุ 7 วัน) แล้วแนบทุก request; 401 → re-login อัตโนมัติ.

Config (env — เรียงตามลำดับความสำคัญ):
  PKH_ADMIN_SECRET               ← secret แอดมิน (สำคัญสุด)
  ADMIN_DASHBOARD_PASSWORD / CRON_TOKEN   ← สำรอง
  backend/.env                   ← fallback อัตโนมัติ (อ่าน CRON_TOKEN / ADMIN_DASHBOARD_PASSWORD)
  PKH_API_BASE_URL               ← default https://shopee-affiliate-bot-9e9n.onrender.com

รัน (stdio — default, ต่อกับ Claude Code/Cursor เป็น MCP server แบบ local):
    cd backend && .venv/Scripts/python.exe ../tools/pkh_mcp_server.py
รัน (streamable-http — เปิดพอร์ตให้ client ระยะไกล):
    cd backend && .venv/Scripts/python.exe ../tools/pkh_mcp_server.py --transport streamable-http --port 8100

Dependencies: mcp (MCP Python SDK v2, `pip install mcp`), httpx — ติดตั้งเฉพาะ venv ท้องถิ่น
(ไม่เข้า backend/requirements.txt — ไม่ใช่ส่วนหนึ่งของ service บน Render).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import httpx
from pydantic import Field
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_API_BASE = "https://shopee-affiliate-bot-9e9n.onrender.com"
API_BASE = (os.getenv("PKH_API_BASE_URL") or DEFAULT_API_BASE).rstrip("/")


def _resolve_secrets() -> list[str]:
    """รวบรวม secret ที่เป็นไปได้ (เรียงตามความน่าจะเป็นถูก) — login จะลองทีละตัว"""
    seen: list[str] = []

    def add(v: Optional[str]) -> None:
        v = (v or "").strip()
        if v and v not in seen:
            seen.append(v)

    # _password() ฝั่ง server เลือก ADMIN_DASHBOARD_PASSWORD ก่อน CRON_TOKEN → ลองตามลำดับนี้
    add(os.getenv("PKH_ADMIN_SECRET"))
    add(os.getenv("ADMIN_DASHBOARD_PASSWORD"))
    add(os.getenv("CRON_TOKEN"))
    env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ADMIN_DASHBOARD_PASSWORD="):
                add(line.split("=", 1)[1].strip().strip('"').strip("'"))
            elif line.startswith("CRON_TOKEN="):
                add(line.split("=", 1)[1].strip().strip('"').strip("'"))
    return seen


SECRETS = _resolve_secrets()

server = MCPServer(
    name="pkh_mcp",
    title="ป้าเข็ม Admin API (Shopee affiliate bot)",
    description=(
        "อ่าน/จัดการสินค้า สถิติ และประวัติโพสต์เรดาร์ของบอทป้าเข็ม "
        "ผ่าน admin API ของบริการบน Render"
    ),
)

# Tool annotations (hints — ไม่ใช่ security guarantee)
_RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
_CREATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
_UPDATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
_DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)


# ---------------------------------------------------------------------------
# HTTP client + session (cookie) management
# ---------------------------------------------------------------------------
_client: Optional[httpx.AsyncClient] = None
_cookie: Optional[str] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0))
    return _client


async def _login() -> str:
    global _cookie
    if not SECRETS:
        raise RuntimeError(
            "ยังไม่ได้ตั้ง secret แอดมิน — ตั้ง env PKH_ADMIN_SECRET "
            "(หรือใส่ ADMIN_DASHBOARD_PASSWORD/CRON_TOKEN ใน backend/.env)"
        )
    client = _get_client()
    last: Optional[httpx.Response] = None
    for secret in SECRETS:
        r = await client.post(f"{API_BASE}/admin/login", data={"password": secret})
        if r.status_code < 400:
            c = r.cookies.get("pkh_admin")
            if c:
                _cookie = c
                return c
        last = r
    status = getattr(last, "status_code", "?")
    body = (last.text[:200] if last else "")
    raise RuntimeError(f"login ล้มเหลวทุก secret — HTTP {status}: {body}")
    return _cookie


async def _request(method: str, path: str, *, params=None, data=None, json_body=None) -> Any:
    client = _get_client()
    if not _cookie:
        await _login()

    async def send() -> httpx.Response:
        return await client.request(
            method,
            f"{API_BASE}{path}",
            params=params,
            data=data,
            json=json_body,
            headers={"Cookie": f"pkh_admin={_cookie}"},
        )

    r = await send()
    if r.status_code == 401:  # cookie หมดอายุ → re-login แล้วลองใหม่ครั้งเดียว
        await _login()
        r = await send()
    if r.status_code >= 400:
        return {"error": f"HTTP {r.status_code}", "detail": r.text[:500]}
    try:
        return r.json()
    except Exception:
        return {"text": r.text}


def _ok(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def _err(e: Exception) -> str:
    return _ok({"error": type(e).__name__, "detail": str(e)[:500]})


# ---------------------------------------------------------------------------
# Tools — สินค้า (products)
# ---------------------------------------------------------------------------
@server.tool(name="pkh_search_products", annotations=_RO)
async def pkh_search_products(
    query: Annotated[str, Field(description="คำค้น (ตรงกับชื่อหรือหมวดสินค้า บางส่วนก็ได้ เช่น 'หูฟัง')")] = "",
    category: Annotated[str, Field(description="กรองตามหมวดสินค้าแบบตรงเป๊ะ (ว่าง = ทั้งหมด)")] = "",
    status: Annotated[str, Field(description="กรอง link_status: ok | dead | suspect | unknown | none (ว่าง = ทั้งหมด)")] = "",
    sort: Annotated[str, Field(description="เรียงลำดับ: new (ล่าสุด) | sales | price | score")] = "new",
    page: Annotated[int, Field(ge=1, description="หน้าที่ต้องการ (เริ่ม 1)")] = 1,
    per_page: Annotated[int, Field(ge=1, le=100, description="จำนวนรายการต่อหน้า (สูงสุด 100)")] = 25,
) -> str:
    """ค้น/กรองสินค้าในคลัง (อ่านอย่างเดียว)

    คืน JSON: {total, page, pages, items:[{id, name, category, price, commission,
    sales_count, rating, ai_score, link_status, affiliate_url, created_at}]}
    """
    try:
        data = await _request(
            "GET",
            "/api/admin/products",
            params={"q": query, "cat": category, "status": status,
                    "sort": sort, "page": page, "per_page": per_page},
        )
        return _ok(data)
    except Exception as e:
        return _err(e)


@server.tool(name="pkh_create_product", annotations=_CREATE)
async def pkh_create_product(
    name: Annotated[str, Field(min_length=1, description="ชื่อสินค้า")],
    affiliate_url: Annotated[str, Field(min_length=1, description="ลิงก์สั้น s.shopee.co.th (ตรวจก่อนบันทึก ถ้าไม่ผ่านจะ 400)")],
    category: Annotated[str, Field(description="หมวดสินค้า (ว่างได้)")] = "",
    price: Annotated[float, Field(ge=0, description="ราคา (บาท)")] = 0.0,
    commission: Annotated[float, Field(ge=0, description="ค่านายหน้า (บาท)")] = 0.0,
    sales_count: Annotated[int, Field(ge=0, description="ยอดขาย")] = 0,
    rating: Annotated[float, Field(ge=0, le=5, description="คะแนนรีวิว 0-5")] = 0.0,
) -> str:
    """เพิ่มสินค้าใหม่ทีละตัว (เขียน DB — ตรวจลิงก์ affiliate + eager backfill รูป)

    คืน JSON: {ok, id} หรือ {error, detail} ถ้าลิงก์ตรวจไม่ผ่าน
    """
    try:
        data = await _request(
            "POST",
            "/api/admin/products",
            data={
                "name": name,
                "affiliate_url": affiliate_url,
                "category": category or "",
                "price": price,
                "commission": commission,
                "sales_count": sales_count,
                "rating": rating,
            },
        )
        return _ok(data)
    except Exception as e:
        return _err(e)


@server.tool(name="pkh_update_product", annotations=_UPDATE)
async def pkh_update_product(
    product_id: Annotated[int, Field(ge=1, description="id สินค้า")],
    name: Annotated[Optional[str], Field(description="ชื่อใหม่ (ละไว้ = ไม่เปลี่ยน)")] = None,
    category: Annotated[Optional[str], Field(description="หมวดใหม่ (ละไว้ = ไม่เปลี่ยน)")] = None,
    price: Annotated[Optional[float], Field(ge=0, description="ราคาใหม่")] = None,
    commission: Annotated[Optional[float], Field(ge=0, description="ค่านายหน้าใหม่")] = None,
    sales_count: Annotated[Optional[int], Field(ge=0, description="ยอดขายใหม่")] = None,
    rating: Annotated[Optional[float], Field(ge=0, le=5, description="คะแนนรีวิวใหม่ 0-5")] = None,
    link_status: Annotated[Optional[str], Field(description="ok | dead | suspect | unknown | none")] = None,
) -> str:
    """แก้ไขสินค้าตาม id (เขียน DB — ส่งเฉพาะฟิลด์ที่ต้องการเปลี่ยน)

    คืน JSON: {ok, id, link_status} หรือ {error, detail}
    """
    try:
        form = {
            "name": name, "category": category, "price": price, "commission": commission,
            "sales_count": sales_count, "rating": rating, "link_status": link_status,
        }
        form = {k: v for k, v in form.items() if v is not None}
        if not form:
            return _ok({"error": "ไม่ได้ระบุฟิลด์ที่จะแก้"})
        data = await _request("POST", f"/api/admin/products/{product_id}", data=form)
        return _ok(data)
    except Exception as e:
        return _err(e)


@server.tool(name="pkh_delete_product", annotations=_DELETE)
async def pkh_delete_product(
    product_id: Annotated[int, Field(ge=1, description="id สินค้าที่จะลบ")],
) -> str:
    """ลบสินค้าตาม id (ทำลาย — cascade ลบ contents/product_analysis อัตโนมัติ)

    คืน JSON: {ok, id} หรือ {error, detail} (404 ถ้าไม่พบ)
    """
    try:
        data = await _request("DELETE", f"/api/admin/products/{product_id}")
        return _ok(data)
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tools — สถิติ (stats)
# ---------------------------------------------------------------------------
@server.tool(name="pkh_get_stats", annotations=_RO)
async def pkh_get_stats() -> str:
    """สถิติภาพรวมแดชบอร์ด (อ่านอย่างเดียว)

    คืน JSON: {totals:{total,sellable,hidden,dead,no_content,users},
    today:{chats,searchers,wismo}, by_category, top_sellers, newest}
    """
    try:
        return _ok(await _request("GET", "/api/admin/stats"))
    except Exception as e:
        return _err(e)


@server.tool(name="pkh_list_categories", annotations=_RO)
async def pkh_list_categories() -> str:
    """รายการหมวดสินค้าพร้อมจำนวน (อ่านอย่างเดียว)

    คืน JSON: [{category, count}, ...] เรียงตามจำนวนมาก→น้อย
    """
    try:
        return _ok(await _request("GET", "/api/admin/categories"))
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Tools — เรดาร์ (Social Demand Radar)
# ---------------------------------------------------------------------------
@server.tool(name="pkh_get_radar_stats", annotations=_RO)
async def pkh_get_radar_stats() -> str:
    """สถิติภาพรวมเรดาร์ความต้องการซื้อ (อ่านอย่างเดียว)

    คืน JSON: {total_leads_scanned, high_demand_leads, action_taken_count,
    total_clicks, total_orders, total_commission_earned, top_demanded_keywords}
    """
    try:
        return _ok(await _request("GET", "/api/admin/facebook-radar/stats"))
    except Exception as e:
        return _err(e)


@server.tool(name="pkh_get_radar_feed", annotations=_RO)
async def pkh_get_radar_feed(
    limit: Annotated[int, Field(ge=1, le=200, description="จำนวนรายการ")] = 50,
    offset: Annotated[int, Field(ge=0, description="เริ่มจากรายการที่")] = 0,
) -> str:
    """ประวัติโพสต์ที่เรดาร์ยิงขึ้นเพจ Facebook + โควต้าวันนี้ (อ่านอย่างเดียว)

    คืน JSON: {posted_today, daily_limit, remaining_today, total,
    feed:[{id, status(posted|ignored|failed), sent_at, demand_score,
    product_keyword, matched_product, source_lead, ai_comment_draft}]}
    """
    try:
        return _ok(await _request("GET", "/api/admin/radar/feed",
                                  params={"limit": limit, "offset": offset}))
    except Exception as e:
        return _err(e)


@server.tool(name="pkh_get_radar_cooldown", annotations=_RO)
async def pkh_get_radar_cooldown() -> str:
    """สถานะ cooldown รายหมวดของเรดาร์ (อ่านอย่างเดียว)

    คืน JSON: {cooldown_hours, categories_on_cooldown, categories_available, checked_at}
    """
    try:
        return _ok(await _request("GET", "/api/admin/radar/cooldown"))
    except Exception as e:
        return _err(e)


@server.tool(name="pkh_list_radar_leads", annotations=_RO)
async def pkh_list_radar_leads(
    limit: Annotated[int, Field(ge=1, le=200, description="จำนวนรายการ")] = 50,
    offset: Annotated[int, Field(ge=0, description="เริ่มจากรายการที่")] = 0,
) -> str:
    """รายการโพสต์ดิบที่เรดาร์ตรวจพบพร้อมผลวิเคราะห์ (อ่านอย่างเดียว)

    คืน JSON: {total, leads:[{id, fb_post_id, author_name, post_text, post_url,
    status, detected_at, events:[{demand_score, intent, product_keyword,
    matched_product_id, notification_status, ai_comment_draft}]}]}
    """
    try:
        return _ok(await _request("GET", "/api/admin/facebook-radar/leads",
                                  params={"limit": limit, "offset": offset}))
    except Exception as e:
        return _err(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    argv = sys.argv[1:]
    transport = "stdio"
    host, port = "127.0.0.1", 8000
    for flag, val in (("--transport", None), ("--host", None), ("--port", None)):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                print(f"{flag} ต้องการค่า", file=sys.stderr)
                sys.exit(2)
            val = argv[i + 1]
            if flag == "--transport":
                transport = val
            elif flag == "--host":
                host = val
            else:
                port = int(val)

    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=transport, host=host, port=port)
