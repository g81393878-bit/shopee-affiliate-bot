# -*- coding: utf-8 -*-
"""Order API for Direct Products (e.g. ปลาแดดเดียว ป้าเข็ม คัดพิเศษ).

Handles 100% Direct Selling (D2C):
- Direct Customer Order submission (ปิดรับออเดอร์แล้ว — เก็บไว้เพื่อประวัติ)
- Supabase PostgreSQL persistence (direct_orders table)
- Instant Telegram Commander Alert
- Admin Order Management & Courier Shipping Label Export (CSV)
"""
from app.services.sales_status import closed_notice
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import datetime
import io
import csv
import sys
from pathlib import Path
from sqlalchemy.orm import Session

from app.db import get_db
from app import models
from app.services.courier_service import book_courier_shipment, render_thermal_shipping_label_html
from app.services.thai_address_validator import (
    enrich_thai_address,
    has_complete_thai_address,
    validate_thai_phone,
)

ROOT = Path(__file__).resolve().parent.parent.parent.parent
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from telegram_notifier import send_telegram_alert
except ImportError:
    def send_telegram_alert(text, **kwargs):
        print(f"[Telegram Alert] {text}")
        return True

router = APIRouter(prefix="/orders", tags=["Orders"])


class FishOrderRequest(BaseModel):
    name: str = Field(..., description="ชื่อผู้รับ")
    phone: str = Field(..., description="เบอร์โทรศัพท์")
    address: str = Field(..., description="ที่อยู่จัดส่ง")
    package: str = Field("1kg", description="แพ็กเกจที่เลือก: 500g, 1kg, 2kg")
    package_name: Optional[str] = None
    price: float = Field(0.0, description="ยอดรวม (บาท) — ร้านปิดรับออเดอร์")
    payment_method: str = Field("TRANSFER", description="ปิดรับออเดอร์ — ไม่มีบริการเก็บเงินปลายทาง")
    note: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: str = Field(..., description="PENDING | CONFIRMED | SHIPPED | DELIVERED | CANCELLED")
    tracking_number: Optional[str] = None


@router.post("/fish")
def create_fish_order(order: FishOrderRequest, db: Session = Depends(get_db)):
    """ร้านยุติการจำหน่ายแล้ว — ปิดรับออเดอร์ออนไลน์ (ไม่สร้างออเดอร์/ไม่คิดราคา)."""
    return {
        "ok": False,
        "sales_closed": True,
        "message": closed_notice(),
    }


@router.get("/fish")
def list_fish_orders(limit: int = 50, db: Session = Depends(get_db)):
    """ดูรายการคำสั่งซื้อปลาแดดเดียวทั้งหมด (สำหรับเจ้าของร้าน)"""
    orders = db.query(models.DirectOrder).order_by(models.DirectOrder.id.desc()).limit(limit).all()
    return {
        "total": len(orders),
        "orders": [
            {
                "id": o.id,
                "order_code": o.order_code,
                "customer_name": o.customer_name,
                "phone": o.phone,
                "address": o.address,
                "package_name": o.package_name,
                "price": float(o.price),
                "payment_method": o.payment_method,
                "status": o.status,
                "tracking_number": o.tracking_number,
                "note": o.note,
                "created_at": o.created_at.strftime("%d/%m/%Y %H:%M") if o.created_at else ""
            }
            for o in orders
        ]
    }


@router.patch("/fish/{order_code}")
def update_order_status(order_code: str, update: OrderStatusUpdate, db: Session = Depends(get_db)):
    """อัปเดตสถานะออเดอร์ (เช่น ส่งของแล้ว พร้อมใส่เลขพัสดุ / tracking number)"""
    order = db.query(models.DirectOrder).filter(models.DirectOrder.order_code == order_code).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order.status = update.status.upper()
    if update.tracking_number:
        order.tracking_number = update.tracking_number
    db.commit()

    # แจ้งเตือนอัปเดตสถานะเข้า Telegram
    try:
        send_telegram_alert(
            f"📦 **[อัปเดตสถานะออเดอร์]** `{order_code}`\n"
            f"👤 ลูกค้า: {order.customer_name}\n"
            f"🔄 สถานะใหม่: **{order.status}**\n"
            f"🚚 เลขพัสดุ: `{order.tracking_number or 'ยังไม่ระบุ'}`"
        )
    except Exception:
        pass

    return {"ok": True, "order_code": order_code, "status": order.status, "tracking_number": order.tracking_number}


@router.get("/fish/export/shipping-csv")
def export_shipping_csv(db: Session = Depends(get_db)):
    """ส่งออกรายชื่อและที่อยู่จัดส่งเป็นไฟล์ CSV สำหรับพิมพ์ใบปะหน้าขนส่ง (Flash/J&T/Kerry/Inter Express)"""
    orders = db.query(models.DirectOrder).filter(models.DirectOrder.status.in_(["PENDING", "CONFIRMED"])).all()
    
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM สำหรับ Excel ภาษาไทย
    writer = csv.writer(output)
    writer.writerow(["รหัสสั่งซื้อ", "ชื่อผู้รับ", "เบอร์โทรศัพท์", "ที่อยู่จัดส่ง", "สินค้า", "ยอดเรียกเก็บ", "วิธีชำระเงิน", "หมายเหตุ"])

    for o in orders:
        collect_amount = f"{float(o.price):.2f}" if o.payment_method != "TRANSFER" else "0.00"
        writer.writerow([
            o.order_code,
            o.customer_name,
            o.phone,
            o.address,
            o.package_name,
            collect_amount,
            o.payment_method,
            o.note or ""
        ])

    output.seek(0)
    filename = f"shipping_labels_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/fish/{order_id}/book-courier")
def book_flash_courier_endpoint(order_id: int, db: Session = Depends(get_db)):
    """จองเลขพัสดุ Flash Express อัตโนมัติ (1-Click Courier Booking)"""
    order = db.query(models.DirectOrder).filter(models.DirectOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    res = book_courier_shipment(
        order_id=order.order_code,
        customer_name=order.customer_name,
        phone=order.phone,
        address=order.address,
        package_code=order.package_code,
        price=float(order.price),
        payment_method=order.payment_method,
        note=order.note or ""
    )

    if res.get("ok"):
        order.tracking_number = res.get("tracking_number")
        order.status = "CONFIRMED"
        db.commit()
        db.refresh(order)

        # แจ้งเตือน Telegram พร้อมลิงก์ติดตามพัสดุ
        alert = (
            f"🚚 **[จองขนส่งสำเร็จ] Flash Express**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔖 ออเดอร์: `{order.order_code}`\n"
            f"👤 ลูกค้า: {order.customer_name}\n"
            f"📦 สินค้า: {order.package_name}\n"
            f"🏷️ เลขพัสดุ: `{order.tracking_number}`\n"
            f"🔍 เช็คสถานะ: {res.get('tracking_url')}\n"
            f"💵 ยอดเรียกเก็บ: {res.get('collect_amount'):,.2f} บาท\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"👉 สามารถคลิกพิมพ์ใบปะหน้า 100x180mm ได้จากแดชบอร์ดเลยค่ะ"
        )
        try:
            send_telegram_alert(alert, parse_mode="Markdown")
        except Exception:
            pass

    return res


@router.get("/fish/{order_id}/label", response_class=HTMLResponse)
def get_order_shipping_label_html(order_id: int, db: Session = Depends(get_db)):
    """ส่งคืน HTML ใบปะหน้าพัสดุมาตรฐาน 100x180mm สำหรับเครื่องพิมพ์ความร้อน (Thermal Printer)"""
    order = db.query(models.DirectOrder).filter(models.DirectOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    html = render_thermal_shipping_label_html(order)
    return HTMLResponse(content=html)


@router.post("/fish/auto-book-all")
def auto_book_all_pending_orders(db: Session = Depends(get_db)):
    """สั่งจองขนส่ง Flash Express ให้ทุกออเดอร์ที่ค้างอยู่ (PENDING) อัตโนมัติในคลิกเดียว"""
    pending_orders = db.query(models.DirectOrder).filter(
        models.DirectOrder.status == "PENDING",
        models.DirectOrder.tracking_number.is_(None)
    ).all()

    booked = []
    for order in pending_orders:
        res = book_courier_shipment(
            order_id=order.order_code,
            customer_name=order.customer_name,
            phone=order.phone,
            address=order.address,
            package_code=order.package_code,
            price=float(order.price),
            payment_method=order.payment_method,
            note=order.note or ""
        )
        if res.get("ok"):
            order.tracking_number = res.get("tracking_number")
            order.status = "CONFIRMED"
            booked.append({
                "order_id": order.id,
                "order_code": order.order_code,
                "tracking_number": order.tracking_number
            })
    
    db.commit()

    if booked:
        summary_msg = (
            f"⚡ **[จองขนส่งอัตโนมัติสำเร็จ {len(booked)} กล่อง]**\n"
            f"━━━━━━━━━━━━━━━━━━━\n" +
            "\n".join([f"• `{b['order_code']}` ➔ `{b['tracking_number']}`" for b in booked]) +
            f"\n━━━━━━━━━━━━━━━━━━━\n"
            f"👉 พิมพ์ใบปะหน้าและติดกล่องส่งได้ทันทีค่ะ!"
        )
        try:
            send_telegram_alert(summary_msg, parse_mode="Markdown")
        except Exception:
            pass

    return {
        "ok": True,
        "booked_count": len(booked),
        "booked_orders": booked
    }


@router.get("/fish/benchmarks")
def get_fish_benchmarks(db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text("SELECT * FROM fish_market_benchmarks ORDER BY id ASC")).mappings().all()
    results = []
    for r in rows:
        d = dict(r)
        ft = d.get("fish_type", "")
        sz = d.get("size_grade", "")
        # Link to actual catalog SKU for sticker printing
        sku = "SKU-SLID-MD-1KG"
        if "หมึก" in ft:
            sku = "SKU-SQUID-EG-500G"
        elif "หลด" in ft:
            sku = "SKU-LOD-NAT-500G"
        elif "กุเลา" in ft:
            sku = "SKU-KULAO-TB-1KG"
        elif "สวาย" in ft:
            sku = "SKU-SWAI-SL-1KG"
        elif "ช่อน" in ft:
            sku = "SKU-CHON-MD-1KG"
        elif "นิล" in ft:
            sku = "SKU-NIL-FL-1KG"
        elif "ดุก" in ft:
            sku = "SKU-DUK-CT-1KG"
        elif "จัมโบ้" in sz:
            sku = "SKU-SLID-JB-1KG"
        elif "เล็ก" in sz:
            sku = "SKU-SLID-MD-500G"
        d["sku"] = sku
        results.append(d)
    return {"ok": True, "count": len(results), "data": results}


@router.get("/fish/suppliers")
def get_fish_suppliers(db: Session = Depends(get_db)):
    """Fetch verified fish supplier directories."""
    from sqlalchemy import text
    try:
        rows = db.execute(text("SELECT * FROM fish_suppliers ORDER BY id ASC")).mappings().all()
        return {"ok": True, "count": len(rows), "data": [dict(r) for r in rows]}
    except Exception as e:
        json_file = ROOT / "backend" / "app" / "data" / "fish_suppliers.json"
        if json_file.exists():
            import json
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"ok": True, "count": len(data), "data": data, "fallback": True}
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fish/sticker/{sku}", response_class=HTMLResponse)
def get_product_sticker(sku: str, db: Session = Depends(get_db)):
    """Generate a compliant 80x55mm product sticker label (มผช. 298/2549)."""
    from sqlalchemy import text
    from app.services.fish_label_service import render_product_sticker_label_html
    try:
        row = db.execute(text("SELECT * FROM fish_catalog WHERE sku = :sku LIMIT 1"), {"sku": sku}).mappings().first()
        if not row:
            # Fallback search by prefix or json
            json_file = ROOT / "backend" / "app" / "data" / "fish_catalog.json"
            if json_file.exists():
                import json
                with open(json_file, "r", encoding="utf-8") as f:
                    items = json.load(f)
                matched = [i for i in items if i.get("sku") == sku]
                if matched:
                    row = matched[0]
        if not row:
            raise HTTPException(status_code=404, detail=f"Product with SKU {sku} not found")
        
        html = render_product_sticker_label_html(dict(row))
        return HTMLResponse(content=html)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
