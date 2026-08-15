# pkh_mcp — MCP server ของบอทป้าเข็ม

MCP server (Python, MCP SDK v2) ที่ expose **Admin API** ของบอทป้าเข็ม (Shopee affiliate bot) ให้ AI agent (Claude Code / Cursor / …) เรียก**อ่าน/จัดการ**ผ่าน secret แอดมิน

ไฟล์: `tools/pkh_mcp_server.py` — รันแยกจาก FastAPI service ไม่แตะโค้ด backend

## Tools (10 ตัว)

| Tool | วิธี | ทำอะไร |
|---|---|---|
| `pkh_search_products` | GET | ค้น/กรองสินค้า (query/category/status/sort/page) |
| `pkh_get_stats` | GET | สถิติแดชบอร์ด (totals/today/top sellers/newest) |
| `pkh_list_categories` | GET | หมวดสินค้า + จำนวน |
| `pkh_get_radar_stats` | GET | สถิติเรดาร์ (leads/orders/commission/keywords) |
| `pkh_get_radar_feed` | GET | ประวัติโพสต์เรดาร์ + โควต้าวันนี้ (posted/ignored/failed) |
| `pkh_get_radar_cooldown` | GET | สถานะ cooldown รายหมวด |
| `pkh_list_radar_leads` | GET | โพสต์ดิบที่ตรวจพบ + ผลวิเคราะห์ |
| `pkh_create_product` | POST | เพิ่มสินค้า (ตรวจลิงก์ affiliate + eager backfill รูป) |
| `pkh_update_product` | POST | แก้สินค้าตาม id (ส่งเฉพาะฟิลด์ที่เปลี่ยน) |
| `pkh_delete_product` | DELETE | ลบสินค้า (cascade contents/analysis) |

## Auth

Server เรียก `POST /admin/login` ด้วย secret แอดมิน → ได้ cookie `pkh_admin` (อายุ 7 วัน) → แนบทุก request; 401 → re-login อัตโนมัติ

Secret เรียงลำดับที่ลอง: `PKH_ADMIN_SECRET` → `ADMIN_DASHBOARD_PASSWORD` → `CRON_TOKEN` → อ่าน `backend/.env` (ใช้ได้เลยบนเครื่องนี้)

## ติดตั้ง + รัน

```bash
# dependency (เฉพาะ venv ท้องถิ่น ไม่เข้า requirements.txt)
cd backend && .venv/Scripts/python.exe -m pip install "mcp"

# stdio (default — ต่อกับ Claude Code/Cursor)
cd backend && .venv/Scripts/python.exe ../tools/pkh_mcp_server.py

# streamable-http (เปิดพอร์ต)
cd backend && .venv/Scripts/python.exe ../tools/pkh_mcp_server.py --transport streamable-http --port 8100
```

## ต่อกับ Claude Code

```bash
claude mcp add pkh --env PKH_ADMIN_SECRET=<secret> -- backend/.venv/Scripts/python.exe tools/pkh_mcp_server.py
```

หรือ `.mcp.json` ที่ root:

```json
{
  "mcpServers": {
    "pkh": {
      "command": "backend/.venv/Scripts/python.exe",
      "args": ["tools/pkh_mcp_server.py"],
      "env": { "PKH_ADMIN_SECRET": "<secret>" }
    }
  }
}
```

## ต่อกับ Cursor

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "pkh": {
      "command": "backend/.venv/Scripts/python.exe",
      "args": ["tools/pkh_mcp_server.py"]
    }
  }
}
```

(ไม่ใส่ secret ก็ได้ — server fallback อ่าน `backend/.env` ให้เอง)
