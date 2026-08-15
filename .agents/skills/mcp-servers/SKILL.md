---
name: mcp-servers
description: >-
  MCP servers for the bot: tools/pkh_mcp_server.py (admin API, 10 tools) and
  tools/mcp_server.py (Shopee affiliate phone tool). Use whenever the user mentions
  MCP, pkh_mcp, tool calling, agent เรียก API, or model context protocol.
---

# MCP Servers (เครื่องมือให้ AI agent เรียก)

## pkh_mcp_server.py (admin API ของบอท)
- MCP server (Python SDK) expose 10 tools: `pkh_search_products` / `pkh_create_product` /
  `pkh_update_product` / `pkh_delete_product` / `pkh_get_stats` / `pkh_list_categories` /
  `pkh_get_radar_stats` / `pkh_get_radar_feed` / `pkh_get_radar_cooldown` / `pkh_list_radar_leads`
- **Auth**: `POST /admin/login` เอา cookie `pkh_admin` แล้วแนบทุก request —
  `require_admin` (dashboard) รับเฉพาะ cookie; `require_admin_auth` (radar) รับ token ด้วย
- **MCP SDK v2 ≠ FastMCP เก่า**: `pip install mcp` ให้ v2 — `from mcp.server.mcpserver import MCPServer`
  (ไม่มี `mcp.server.fastmcp`); single Pydantic model param ถูก wrap เป็น nested key → ใช้
  flat params `Annotated[str, Field(description=...)]` ให้ input schema สะอาด

## mcp_server.py (Shopee affiliate ผ่านโทรศัพท์)
- FastMCP stdio — wrap `tools/shopee_affiliate.py`: `shopee_status`, `shopee_convert_links`,
  `shopee_verify_link` (ตรวจ `utm_source=an_15329550184`), `shopee_update_product`
- ติดตั้งครั้งเดียว: `pip install -r tools/requirements-mcp.txt`

## กับดัก
1. dep `mcp` อยู่ใน venv ท้องถิ่นเท่านั้น (ไม่เข้า requirements.txt)
2. แก้ tool → ตรวจ schema ผ่าน `tools/test_mcp_client.py` + `tools/pkh_mcp_server.md` (docs)
3. Cookie หมดอายุ 7 วัน — ถ้า agent โดน 401 ให้ re-login

## ไฟล์
`tools/pkh_mcp_server.py`, `tools/mcp_server.py`, `tools/test_mcp_client.py`,
`tools/pkh_mcp_server.md`, `tools/requirements-mcp.txt`
