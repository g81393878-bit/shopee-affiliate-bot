# -*- coding: utf-8 -*-
"""Product Sticker Label Generator for Sun-Dried Fish Products.

Compliant with Thai Community Product Standard: มผช. 298/2549 (ปลาแดดเดียว).
Supports standard thermal sticker printers (80x50mm and 100x75mm).
"""
import datetime
from typing import Dict, Any


def render_product_sticker_label_html(product: Dict[str, Any], mfg_date: str = None, bbd_date: str = None) -> str:
    """Renders a thermal sticker label HTML compliant with มผช. 298/2549.
    
    Dimensions: 80mm x 55mm (Standard Food Grade Thermal Pouch Sticker)
    """
    now = datetime.datetime.now()
    mfg_str = mfg_date or now.strftime("%d/%m/%Y")
    # Sun-dried fish in freezer (-18C) stays fresh for 6 months
    bbd_dt = now + datetime.timedelta(days=180)
    bbd_str = bbd_date or bbd_dt.strftime("%d/%m/%Y")
    
    sku = product.get("sku", "SKU-SLID-MD-1KG")
    name = product.get("name", "ปลาสลิดแดดเดียว คัดพิเศษ")
    weight_g = product.get("weight_g", 1000)
    weight_desc = f"{weight_g / 1000:.1f} กิโลกรัม" if weight_g >= 1000 else f"{weight_g} กรัม"
    pieces_desc = product.get("pieces_desc", "7 - 8 ตัว")
    tagline = product.get("tagline", "เค็มกำลังดี เนื้อแน่นนุ่มฟู ทอดหอมฟุ้งจนต้องเติมข้าว")
    
    # Fish ingredients breakdown
    fish_name = "ปลาสลิด"
    if "ช่อน" in name:
        fish_name = "ปลาช่อน"
    elif "นิล" in name:
        fish_name = "ปลานิล"
    elif "ดุก" in name:
        fish_name = "ปลาดุก"
    elif "อินทรีย์" in name or "อินทรี" in name:
        fish_name = "ปลาอินทรี"
    elif "หมึก" in name:
        fish_name = "หมึกกล้วย/หมึกไข่"
    elif "หลด" in name:
        fish_name = "ปลาหลด"
    elif "กุเลา" in name:
        fish_name = "ปลากุเลา"
    elif "สวาย" in name:
        fish_name = "ปลาสวาย"

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<title>ฉลากสินค้า {name} - ป้าเข็ม คัดพิเศษ</title>
<style>
  @page {{
    size: 80mm 55mm;
    margin: 0;
  }}
  * {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  body {{
    margin: 0;
    padding: 2.5mm;
    width: 80mm;
    height: 55mm;
    font-family: 'Sarabun', 'Tahoma', 'Arial', sans-serif;
    color: #000;
    background: #fff;
    overflow: hidden;
  }}
  .label-container {{
    border: 1.5px solid #000;
    border-radius: 4px;
    height: 100%;
    padding: 2mm 3mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #000;
    padding-bottom: 1.5mm;
  }}
  .brand-title {{
    font-size: 11pt;
    font-weight: 900;
    letter-spacing: -0.2px;
  }}
  .standard-tag {{
    font-size: 6.5pt;
    font-weight: bold;
    border: 0.8px solid #000;
    padding: 1px 3px;
    border-radius: 2px;
  }}
  .prod-name {{
    font-size: 10.5pt;
    font-weight: 800;
    margin-top: 1.5mm;
    line-height: 1.15;
  }}
  .prod-subtitle {{
    font-size: 7pt;
    color: #333;
    margin-bottom: 1.5mm;
  }}
  .grid-info {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5mm;
    font-size: 6.5pt;
    line-height: 1.25;
    background: #f8f8f8;
    padding: 1.5mm;
    border-radius: 3px;
    border: 0.5px solid #ddd;
  }}
  .grid-info b {{
    color: #000;
  }}
  .footer-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    font-size: 6pt;
    line-height: 1.2;
    border-top: 0.8px solid #000;
    padding-top: 1.5mm;
  }}
  .dates {{
    font-size: 6.5pt;
    font-weight: bold;
  }}
  .caution {{
    font-size: 5.5pt;
    color: #222;
  }}
  @media print {{
    body {{
      width: 80mm;
      height: 55mm;
    }}
    .no-print {{
      display: none;
    }}
  }}
</style>
</head>
<body onload="if(window.location.search.indexOf('autoprint=1')!==-1)window.print()">

<div class="label-container">
  <!-- Header -->
  <div class="header">
    <div class="brand-title">🐟 ป้าเข็ม คัดพิเศษ</div>
    <div class="standard-tag">มผช. ๒๙๘/๒๕๔๙</div>
  </div>

  <!-- Product Title & Spec -->
  <div>
    <div class="prod-name">{name}</div>
    <div class="prod-subtitle">✨ {tagline}</div>
  </div>

  <!-- Compliance Grid (มผช. 298/2549) -->
  <div class="grid-info">
    <div>
      <div>• <b>ส่วนประกอบ:</b> เนื้อ{fish_name} 97%, เกลือสมุทร 3%</div>
      <div>• <b>ไม่ใส่วัตถุกันเสีย</b> / ไม่เจือสีสังเคราะห์</div>
      <div>• <b>ขนาดบรรจุ:</b> {pieces_desc}</div>
    </div>
    <div>
      <div>• <b>น้ำหนักสุทธิ:</b> <span style="font-size:8pt;font-weight:900">{weight_desc}</span></div>
      <div>• <b>วิธีเก็บ:</b> แช่ช่องฟรีซ -18°C นาน 6 เดือน</div>
      <div>• <b>คำแนะนำ:</b> ต้องทำให้สุกก่อนบริโภค</div>
    </div>
  </div>

  <!-- Dates & Contact Footer -->
  <div class="footer-row">
    <div>
      <div class="dates">ผลิต (MFG): {mfg_str} &nbsp;|&nbsp; ควรบริโภคก่อน (BBD): {bbd_str}</div>
      <div class="caution">ผลิตและจัดจำหน่ายโดย: แบรนด์ป้าเข็ม คัดพิเศษ (LINE: @137gsref)</div>
    </div>
    <div style="text-align:right">
      <span style="font-size:7pt;font-weight:bold">SKU: {sku}</span>
    </div>
  </div>
</div>

<div class="no-print" style="position:fixed;bottom:10px;right:10px;background:#1e293b;color:#fff;padding:8px 16px;border-radius:8px;font-size:13px;display:flex;gap:8px;box-shadow:0 4px 12px rgba(0,0,0,0.2)">
  <button onclick="window.print()" style="padding:6px 12px;background:#059669;color:#fff;border:none;border-radius:4px;cursor:pointer;font-weight:bold">🖨️ พิมพ์สติกเกอร์ (80x55mm)</button>
  <button onclick="window.close()" style="padding:6px 12px;background:#64748b;color:#fff;border:none;border-radius:4px;cursor:pointer">ปิด</button>
</div>

</body>
</html>
"""
    return html
