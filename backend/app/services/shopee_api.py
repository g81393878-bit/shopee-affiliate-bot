"""
Shopee Affiliate Open API (GraphQL) client.

Authentication (official scheme):
    Authorization: SHA256 Credential={AppId}, Timestamp={Timestamp}, Signature={Signature}
    Signature = SHA256(AppId + Timestamp + Payload + Secret)
    - AppId     = partner_id ที่ Shopee ส่งให้ทางอีเมล (หลังอนุมัติ Open API)
    - Timestamp = unix seconds (ไม่ใช่ millisecond)
    - Payload   = body JSON string ที่ส่งจริง (ต้องตรงเป๊ะ)

Endpoints (GraphQL, ทั้งหมด POST ไปที่ base_url/graphql):
    productOfferV2   — ค้นสินค้าทั้งคลัง (keyword/listType/sortType/page/limit)
    generateShortLink— แปลง URL Shopee → ลิงก์สั้น affiliate (มี tracking ของเรา)
    conversionReport — รายงานออเดอร์/ค่าคอม (ใช้เช็คยอดออเดอร์เพื่อยื่นขอ API ได้)

Config (env):
    SHOPEE_AFFILIATE_PARTNER_ID  — App ID (partner_id)
    SHOPEE_AFFILIATE_SECRET      — Secret key

Usage CLI:
    python -m app.services.shopee_api search "กระติกน้ำ" --save
    python -m app.services.shopee_api short-link "https://shopee.co.th/..."
    python -m app.services.shopee_api report --days 30
"""

import argparse
import hashlib
import json
import os
import time
import urllib.request
import urllib.error
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app import models

BASE_URL = "https://open-api.affiliate.shopee.co.th/graphql"


def _signature(app_id: str, timestamp: int, payload: str, secret: str) -> str:
    """SHA256(AppId + Timestamp + Payload + Secret) — concatenated, no separators."""
    raw = f"{app_id}{timestamp}{payload}{secret}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value))


class ShopeeAffiliateClient:
    """Client สำหรับ Shopee Affiliate Open API (GraphQL)."""

    def __init__(self, app_id: Optional[str] = None, secret: Optional[str] = None,
                 base_url: str = BASE_URL):
        self.app_id = app_id or os.getenv("SHOPEE_AFFILIATE_PARTNER_ID")
        self.secret = secret or os.getenv("SHOPEE_AFFILIATE_SECRET")
        self.base_url = base_url
        if not self.app_id or not self.secret:
            raise RuntimeError(
                "ยังไม่ได้ตั้งค่า SHOPEE_AFFILIATE_PARTNER_ID / SHOPEE_AFFILIATE_SECRET "
                "ใน backend/.env (ค่าจากอีเมล Shopee หลังอนุมัติ Open API)"
            )

    # ------------------------------------------------------------------ core
    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        timestamp = int(time.time())
        auth = (
            f"SHA256 Credential={self.app_id}, Timestamp={timestamp}, "
            f"Signature={_signature(self.app_id, timestamp, body.decode('utf-8'), self.secret)}"
        )
        req = urllib.request.Request(
            self.base_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": auth,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Shopee API HTTP {e.code}: {detail}") from e

    def _query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self._post({"query": query, "variables": variables or {}})
        if resp.get("errors"):
            errs = resp["errors"]
            raise RuntimeError(f"Shopee API error: {errs}")
        return resp

    # -------------------------------------------------------------- endpoints
    PRODUCT_QUERY = """query productOfferV2($keyword: String, $listType: Int, $sortType: Int, $page: Int, $limit: Int) {
      productOfferV2(keyword: $keyword, listType: $listType, sortType: $sortType, page: $page, limit: $limit) {
        nodes {
          itemId productName productLink offerLink imageUrl
          priceMin priceMax priceDiscountRate sales ratingStar
          commissionRate sellerCommissionRate shopeeCommissionRate commission
          shopId shopName shopType periodStartTime periodEndTime
        }
        pageInfo { page limit hasNextPage }
      }
    }"""

    def search_products(self, keyword: Optional[str] = None, list_type: int = 0,
                        sort_type: int = 5, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """ค้นสินค้าทั้งคลัง (listType: 0=แนะนำ 1=คอมมิชชันสูง 2=ขายดี; sortType: 1=เกี่ยวข้อง 2=ยอดขาย 5=คอมมิชชัน)."""
        variables = {
            "keyword": keyword,
            "listType": list_type,
            "sortType": sort_type,
            "page": page,
            "limit": limit,
        }
        resp = self._query(self.PRODUCT_QUERY, variables)
        return resp.get("data", {}).get("productOfferV2", {})

    SHORT_LINK_QUERY = """mutation generateShortLink($input: GenerateShortLinkInput!) {
      generateShortLink(input: $input) { shortLink }
    }"""

    def generate_short_link(self, origin_url: str, sub_ids: Optional[List[str]] = None) -> str:
        """แปลง URL สินค้า Shopee → ลิงก์สั้น affiliate (มี tracking ของเรา)."""
        variables = {"input": {"originUrl": origin_url, "subIds": sub_ids or []}}
        resp = self._query(self.SHORT_LINK_QUERY, variables)
        return resp.get("data", {}).get("generateShortLink", {}).get("shortLink", "")

    REPORT_QUERY = """query conversionReport($purchaseTimeStart: Int, $purchaseTimeEnd: Int, $orderStatus: String, $limit: Int) {
      conversionReport(purchaseTimeStart: $purchaseTimeStart, purchaseTimeEnd: $purchaseTimeEnd, orderStatus: $orderStatus, limit: $limit) {
        nodes {
          purchaseTime clickTime conversionId totalCommission sellerCommission shopeeCommissionCapped
          buyerType device utmContent
          orders { orderId orderStatus items { itemId itemName shopName itemPrice qty itemTotalCommission } }
        }
        pageInfo { limit hasNextPage scrollId }
      }
    }"""

    def conversion_report(self, start_ts: int, end_ts: int,
                          order_status: str = "COMPLETED", limit: int = 50) -> Dict[str, Any]:
        """รายงานยอดออเดอร์/ค่าคอม (ใช้เช็คยอดออเดอร์ต่อเดือนได้)."""
        variables = {
            "purchaseTimeStart": start_ts,
            "purchaseTimeEnd": end_ts,
            "orderStatus": order_status,
            "limit": limit,
        }
        resp = self._query(self.REPORT_QUERY, variables)
        return resp.get("data", {}).get("conversionReport", {})


# ---------------------------------------------------------------- persistence
def save_products(db: Session, nodes: List[Dict[str, Any]]) -> int:
    """Upsert รายการสินค้าจาก productOfferV2 ลงตาราง shopee_products (staging).

    ใช้ item_id เป็นกุญแจ: มีอยู่แล้ว → อัปเดต, ยังไม่มี → insert.
    """
    saved = 0
    for node in nodes:
        item_id = node.get("itemId")
        if not item_id:
            continue
        existing = db.query(models.ShopeeProduct).filter(
            models.ShopeeProduct.item_id == int(item_id)
        ).first()

        fields = dict(
            shop_id=_to_int(node.get("shopId")),
            shop_name=node.get("shopName"),
            product_name=node.get("productName") or f"item-{item_id}",
            product_link=node.get("productLink"),
            offer_link=node.get("offerLink"),
            image_url=node.get("imageUrl"),
            price_min=_to_decimal(node.get("priceMin")),
            price_max=_to_decimal(node.get("priceMax")),
            price_discount_rate=_to_float(node.get("priceDiscountRate")),
            sales=_to_int(node.get("sales")),
            rating_star=_to_float(node.get("ratingStar")),
            commission_rate=str(node.get("commissionRate") or ""),
            seller_commission_rate=str(node.get("sellerCommissionRate") or ""),
            shopee_commission_rate=str(node.get("shopeeCommissionRate") or ""),
            commission=_to_decimal(node.get("commission")),
            shop_type=_to_int(node.get("shopType")),
            category_id=_to_int(node.get("categoryId")),
            period_start_time=_to_int(node.get("periodStartTime")),
            period_end_time=_to_int(node.get("periodEndTime")),
            raw_json=node,
        )
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            db.add(models.ShopeeProduct(item_id=int(item_id), **fields))
        saved += 1
    db.commit()
    return saved


def _to_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------ CLI
def main() -> None:
    parser = argparse.ArgumentParser(prog="shopee_api", description="Shopee Affiliate Open API")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="ค้นสินค้า")
    p_search.add_argument("keyword", nargs="?", help="คำค้น (เว้นว่าง = ดึงสินค้าแนะนำ)")
    p_search.add_argument("--list-type", type=int, default=0)
    p_search.add_argument("--sort-type", type=int, default=5)
    p_search.add_argument("--page", type=int, default=1)
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--save", action="store_true", help="บันทึกลงตาราง shopee_products (Supabase)")

    p_short = sub.add_parser("short-link", help="แปลง URL → ลิงก์สั้น affiliate")
    p_short.add_argument("url")
    p_short.add_argument("--sub-ids", nargs="*", default=[])

    p_report = sub.add_parser("report", help="รายงานออเดอร์ (เช็คยอดออเดอร์/เดือน)")
    p_report.add_argument("--days", type=int, default=30)
    p_report.add_argument("--status", default="COMPLETED")

    args = parser.parse_args()
    client = ShopeeAffiliateClient()

    if args.cmd == "search":
        data = client.search_products(args.keyword, args.list_type, args.sort_type, args.page, args.limit)
        nodes = data.get("nodes", [])
        print(f"พบ {len(nodes)} รายการ (page {data.get('pageInfo', {}).get('page')})")
        for n in nodes:
            print(f"  [{n.get('itemId')}] {n.get('productName')} | ฿{n.get('priceMin')}-{n.get('priceMax')} | "
                  f"com {n.get('commissionRate')} | sales {n.get('sales')}")
        if args.save:
            db = SessionLocal()
            try:
                saved = save_products(db, nodes)
                print(f"💾 บันทึก {saved} รายการลง shopee_products แล้ว")
            finally:
                db.close()

    elif args.cmd == "short-link":
        link = client.generate_short_link(args.url, args.sub_ids)
        print(link or "⚠️ ไม่ได้ลิงก์กลับมา (เช็ค error/log)")

    elif args.cmd == "report":
        now = int(time.time())
        start = now - args.days * 86400
        data = client.conversion_report(start, now, args.status)
        nodes = data.get("nodes", [])
        total = sum(_to_decimal(n.get("totalCommission")) for n in nodes)
        print(f"ออเดอร์ {len(nodes)} รายการใน {args.days} วัน | ค่าคอมรวม ≈ ฿{total}")


if __name__ == "__main__":
    main()
