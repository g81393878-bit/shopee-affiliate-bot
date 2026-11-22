# -*- coding: utf-8 -*-
"""
ระบบบัญชีและการเงินร้านปลาสลิดป้าเข็ม (Accounting & Financial Management API)
================================================================
- GET /api/accounting/ledger      : สมุดรายวันทั่วไป (General Ledger)
- GET /api/accounting/pnl         : งบกำไรขาดทุนสรุป (Income Statement / P&L)
- GET /api/accounting/export-csv  : ดาวน์โหลดไฟล์ CSV บัญชีสำหรับเปิดใน Excel & ยื่นภาษี
- GET /api/accounting/assets      : ทะเบียนสินทรัพย์ถาวรและค่าเสื่อมราคา (Fixed Assets)
"""

import csv
import io
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/accounting", tags=["Accounting"])


@router.get("/ledger")
def get_general_ledger(
    limit: int = Query(50, ge=1, le=500),
    transaction_type: Optional[str] = Query(None, description="INCOME or EXPENSE"),
    db: Session = Depends(get_db)
):
    """ดึงข้อมูลสมุดรายวันทั่วไป (General Ledger)"""
    sql = "SELECT transaction_id, reference_no, entry_date, transaction_type, account_code, category, amount, description, created_at FROM view_general_ledger"
    params = {"limit": limit}
    if transaction_type:
        sql += " WHERE transaction_type = :tt"
        params["tt"] = transaction_type.upper()
    sql += " ORDER BY created_at DESC LIMIT :limit"

    result = db.execute(text(sql), params).mappings().all()
    return {"status": "ok", "count": len(result), "data": [dict(r) for r in result]}


@router.get("/pnl")
def get_pnl_statement(
    target_date: Optional[date] = Query(None, description="วันที่ต้องการดูงบ (ไม่ระบุ = สะสมทั้งหมดตามสมุดรายวันจริง)"),
    db: Session = Depends(get_db)
):
    """ดึงงบกำไรขาดทุนจากสมุดรายวันทั่วไป (view_general_ledger) ตามรายการที่บันทึกจริง 100%"""
    sql = "SELECT transaction_id, reference_no, entry_date, transaction_type, account_code, category, amount, description FROM view_general_ledger"
    params = {}
    if target_date:
        sql += " WHERE entry_date = :qdate"
        params["qdate"] = target_date

    rows = db.execute(text(sql), params).mappings().all()

    rev_4110 = 0.0
    rev_4120 = 0.0
    rev_4130 = 0.0
    income_count = 0

    ar_1210 = 0.0
    ar_count = 0

    cogs_5110 = 0.0
    cogs_5120 = 0.0
    cogs_5130 = 0.0

    opex_5210 = 0.0
    opex_5220 = 0.0
    opex_5230 = 0.0
    opex_5290 = 0.0

    capex_1510 = 0.0

    for r in rows:
        amt = float(r["amount"] or 0)
        code = str(r["account_code"] or "")
        cat = str(r["category"] or "").upper()
        ttype = str(r["transaction_type"] or "").upper()
        if ttype == "INCOME":
            income_count += 1
            if code == "4110":
                rev_4110 += amt
            elif code == "4130":
                rev_4130 += amt
            else:
                rev_4120 += amt
        elif ttype == "RECEIVABLE" or code == "1210" or cat == "AR_COD":
            ar_count += 1
            ar_1210 += amt
        else:
            if cat == "FISH" or code == "5110":
                cogs_5110 += amt
            elif cat == "PACKAGING" or code == "5120":
                cogs_5120 += amt
            elif cat == "SHIPPING" or code == "5130":
                cogs_5130 += amt
            elif cat == "ADS" or code == "5210":
                opex_5210 += amt
            elif cat == "TRAVEL" or code == "5220":
                opex_5220 += amt
            elif cat == "UTILITIES" or code == "5230":
                opex_5230 += amt
            elif cat == "ASSET" or code == "1510":
                capex_1510 += amt
            else:
                opex_5290 += amt

    total_revenue = rev_4110 + rev_4120 + rev_4130
    total_cogs = cogs_5110 + cogs_5120 + cogs_5130
    gross_profit = total_revenue - total_cogs
    total_opex = opex_5210 + opex_5220 + opex_5230 + opex_5290
    net_profit = gross_profit - total_opex

    return {
        "status": "ok",
        "period": target_date.isoformat() if target_date else "ALL_TIME",
        "revenue": {
            "total_revenue": total_revenue,
            "total_orders": income_count,
            "4110_sku_500g": rev_4110,
            "4120_sku_1kg": rev_4120,
            "4130_sku_2kg": rev_4130,
        },
        "accounts_receivable": {
            "1210_cod_unpaid": ar_1210,
            "unpaid_orders_count": ar_count,
        },
        "cogs": {
            "total_cogs": total_cogs,
            "5110_fish_cost": cogs_5110,
            "5120_packaging_cost": cogs_5120,
            "5130_shipping_cost": cogs_5130,
        },
        "gross_profit": gross_profit,
        "operating_expenses": {
            "total_opex": total_opex,
            "5210_facebook_ads": opex_5210,
            "5220_travel": opex_5220,
            "5230_utilities": opex_5230,
            "5290_other": opex_5290,
        },
        "net_profit": net_profit,
        "fixed_assets_capex": {
            "1510_equipment": capex_1510,
        },
    }


@router.get("/export-csv")
def export_accounting_csv(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    """ส่งออกไฟล์ CSV สมุดรายวันทั่วไป รองรับเปิดใน Excel ไทย 100% (UTF-8 with BOM)"""
    sql = """
    SELECT transaction_id, reference_no, entry_date, transaction_type, account_code, category, amount, description, created_at
    FROM view_general_ledger
    WHERE 1=1
    """
    params = {}
    if start_date:
        sql += " AND entry_date >= :sdate"
        params["sdate"] = start_date
    if end_date:
        sql += " AND entry_date <= :edate"
        params["edate"] = end_date

    sql += " ORDER BY created_at DESC"

    rows = db.execute(text(sql), params).mappings().all()

    output = io.StringIO()
    output.write('\ufeff')  # BOM for Excel
    writer = csv.writer(output)

    writer.writerow([
        "รหัสธุรกรรม (ID)",
        "เลขอ้างอิง (Ref No)",
        "วันที่ทำรายการ",
        "ประเภท (INCOME/EXPENSE)",
        "รหัสบัญชี (Account Code)",
        "หมวดหมู่ (Category)",
        "จำนวนเงิน (บาท)",
        "รายละเอียดรายการ",
        "เวลาบันทึก (Timestamp)"
    ])

    for r in rows:
        writer.writerow([
            r["transaction_id"],
            r["reference_no"],
            r["entry_date"],
            r["transaction_type"],
            r["account_code"],
            r["category"],
            f"{float(r['amount']):.2f}",
            r["description"],
            r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r["created_at"] else ""
        ])

    csv_data = output.getvalue()
    filename = f"pakhem_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/assets")
def get_fixed_assets(db: Session = Depends(get_db)):
    """ดึงข้อมูลทะเบียนสินทรัพย์ถาวร (Fixed Assets Schedule)"""
    sql = """
    SELECT id, asset_code, asset_name, purchase_price, purchase_date, useful_life_months, monthly_depreciation, daily_depreciation, status, note
    FROM accounting_fixed_assets
    ORDER BY purchase_date DESC
    """
    rows = db.execute(text(sql)).mappings().all()
    total_value = sum(float(r["purchase_price"]) for r in rows)
    total_monthly_dep = sum(float(r["monthly_depreciation"]) for r in rows)

    return {
        "status": "ok",
        "total_assets_count": len(rows),
        "total_asset_value": total_value,
        "total_monthly_depreciation": total_monthly_dep,
        "assets": [dict(r) for r in rows]
    }
