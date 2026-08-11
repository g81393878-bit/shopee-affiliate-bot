#!/usr/bin/env python3
"""Smoke-test the shopee-affiliate MCP server over stdio."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["tools/mcp_server.py"],
        cwd=r"D:\Shopee_Web_Scraping",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            r = await session.call_tool("shopee_status", {})
            print("\nSTATUS:", r.content[0].text)

            r = await session.call_tool("shopee_convert_links", {
                "urls": ["https://shopee.co.th/m/world-milk-day/"]
            })
            print("\nCONVERT:", r.content[0].text)

            data = json.loads(r.content[0].text)
            if data.get("links"):
                r = await session.call_tool("shopee_verify_link", {
                    "short_url": data["links"][0]
                })
                print("\nVERIFY:", r.content[0].text)

            r = await session.call_tool("shopee_update_product", {
                "product_id": 999999,
                "affiliate_url": "https://s.shopee.co.th/xxxxx",
            })
            print("\nUPDATE (expect 404):", r.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
