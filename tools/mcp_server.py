#!/usr/bin/env python3
"""
MCP server exposing the Shopee Affiliate phone automation as tools.

Run (stdio transport for local agents):
    python tools/mcp_server.py

Requires: a phone with USB debugging authorized (see shopee_affiliate.py),
Shopee app logged into the affiliate account.

Client config example (Claude Code):
    {
      "mcpServers": {
        "shopee-affiliate": {
          "command": "python",
          "args": ["D:/Shopee_Web_Scraping/tools/mcp_server.py"]
        }
      }
    }
"""

import os
import sys
import json
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shopee_affiliate as sa  # noqa: E402

try:
    from fastmcp import FastMCP
except ImportError:
    sys.exit("fastmcp not installed. Run: pip install fastmcp")

mcp = FastMCP("shopee-affiliate")

DEFAULT_BOT_API = sa.DEFAULT_BOT_API


def _phone_ok() -> tuple:
    """Return (ok, adb_bin_or_error)."""
    try:
        adb_bin = sa.adb()
    except SystemExit as e:
        return False, str(e)
    devs = sa.adb_devices(adb_bin)
    if not devs:
        return False, "No Android device attached. Connect the phone and "
        "enable USB debugging (adb devices)."
    return True, adb_bin


@mcp.tool(
    description=(
        "Check that the Android phone is connected (adb) and the LINE bot "
        "backend is healthy. Call first before convert or update tools so "
        "you can give the user an actionable error if a prerequisite is missing."
    ),
    annotations={"readOnlyHint": True},
)
def shopee_status() -> dict:
    """Check phone (adb) + bot backend health. Read-only."""
    ok, info = _phone_ok()
    result = {"phone_connected": ok}
    if not ok:
        result["phone_error"] = info
    else:
        result["adb"] = info
        result["devices"] = sa.adb_devices(info)

    # bot health
    try:
        # Render free tier cold-starts in ~30-60s, so allow a generous timeout
        with urllib.request.urlopen(f"{DEFAULT_BOT_API}/health", timeout=45) as r:
            result["bot_health"] = {"status": r.status, "body": r.read().decode()[:200]}
    except Exception as e:
        result["bot_health"] = {"error": str(e)[:200]}
    return result


@mcp.tool(
    description=(
        "Convert normal Shopee URLs (https://shopee.co.th/...) into YOUR "
        "affiliate short links (https://s.shopee.co.th/...) that pay "
        "commission. Up to 5 URLs, one per line in the app. Requires the "
        "USB-connected phone with the Shopee app logged into the affiliate "
        "account. Drives the app's built-in Convert Link (แปลงลิงก์) feature "
        "and reads the generated links from the result popup. Returns the "
        "links plus the raw popup text. Examples of valid inputs: "
        "https://shopee.co.th/product/12345/67890 or "
        "https://shopee.co.th/m/some-campaign/. A link is confirmed genuine "
        "when it redirects with utm_source=an_15329550184 (this account)."
    ),
    annotations={"openWorldHint": True},
)
def shopee_convert_links(urls: list[str]) -> dict:
    """Turn normal Shopee URLs into account-bound affiliate short links."""
    if not urls:
        return {"error": "Provide at least one Shopee URL."}
    if len(urls) > 5:
        return {"error": "The Shopee app accepts at most 5 links per convert."}
    ok, info = _phone_ok()
    if not ok:
        return {"error": info}
    try:
        return sa.convert_links(info, urls)
    except Exception as e:
        return {"error": f"convert failed: {e}"}


@mcp.tool(
    description=(
        "Verify a s.shopee.co.th short link is a real affiliate link by "
        "following its redirect and checking for the affiliate tracking "
        "parameter utm_source=an_15329550184 (this account). Returns the "
        "HTTP status, the redirect target and whether it carries this "
        "account's tracking. Read-only."
    ),
    annotations={"readOnlyHint": True},
)
def shopee_verify_link(short_url: str) -> dict:
    """Confirm a short link resolves with this account's affiliate tracking."""
    if "s.shopee.co.th" not in short_url:
        return {"error": "expected an https://s.shopee.co.th/... link, got: " + short_url}
    req = urllib.request.Request(short_url, method="GET", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            target = r.geturl()
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
        target = e.headers.get("Location", "")
    except Exception as e:
        return {"error": str(e)[:300]}
    return {
        "status": status,
        "redirect_to": target,
        "has_affiliate_tracking": "utm_source=an_15329550184" in target,
        "is_valid": status in (301, 302, 200) and "shopee.co.th" in target,
    }


@mcp.tool(
    description=(
        "Store an affiliate link (or update name/price) on a product in the "
        "Shopee Affiliate LINE bot backend via PUT /api/products/{id}. Use "
        "after shopee_convert_links so the LINE bot recommends products with "
        "real commission-earning links."
    ),
    annotations={"destructiveHint": True},
)
def shopee_update_product(
    product_id: int,
    affiliate_url: str,
    name: str | None = None,
    price: float | None = None,
    bot_api: str | None = None,
) -> dict:
    """Update a product in the bot backend with a real affiliate link."""
    api = bot_api or DEFAULT_BOT_API
    try:
        status, body = sa.update_bot(
            product_id, affiliate_url, name=name, price=price, bot_api=api
        )
    except Exception as e:
        return {"error": f"update failed: {e}"}
    return {"http_status": status, "response": body}


if __name__ == "__main__":
    mcp.run()
