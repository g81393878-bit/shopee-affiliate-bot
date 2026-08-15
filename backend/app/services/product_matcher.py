# -*- coding: utf-8 -*-
"""Product Matching Engine with AI Reasoning (Social Demand Radar V1 - บอทป้าเข็ม)

หน้าที่หลัก:
1. ค้นหาและจับคู่สินค้าที่ดีที่สุดในคลัง `products` ให้ตรงกับ Demand ของลูกค้า
   - กฎเหล็กตาม AGENTS.md: ค้นหาเฉพาะสินค้าที่มี `link_status == 'ok'` เท่านั้น
   - ทำความสะอาดและ Normalize ข้อความภาษาไทย (สระอำ NFC, คำพ้อง, ตัดคำนำหน้า)
2. คำนวณคะแนน Multi-Factor Match Score (0-100):
   - Relevance (ความตรงของชื่อ/หมวด): 40%
   - Rating (คะแนนรีวิวร้านค้า): 20%
   - Sales Count (ยอดขายสะสม / Social Proof): 20%
   - Commission (ผลตอบแทนค่านายหน้า): 10%
   - Budget Fit (ความคุ้มค่าและความสอดคล้องกับงบประมาณ): 10%
3. สร้าง Suggested Reasons (เหตุผลที่เลือกสินค้าชิ้นนี้) แสดงเกณฑ์เชิงประจักษ์ชัดเจน
"""
from decimal import Decimal
import logging
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy.orm import Session

from app import models
from app.services.category import CATEGORY_KEYWORDS, guess_category, normalize_query

logger = logging.getLogger(__name__)


def _nfc(s: str) -> str:
    """รวมอักขระภาษาไทยเป็นรูปแบบเดียว NFC และแปลงสระอำรูปผสมให้เป็นสระอำเดี่ยว"""
    if not s:
        return ""
    try:
        s = unicodedata.normalize("NFC", s)
    except Exception:
        pass
    return (s.replace("\u0e4d\u0e32", "\u0e33")   # นิคหิต + สระอา -> สระอำ
             .replace("\u0e4d\u0e33", "\u0e33"))  # กันรูปแบบซ้ำ


def _bigrams(s: str) -> set:
    """สกัด Bigrams อักขระสำหรับวัดความคล้ายคลึงภาษาไทยที่ไม่มีเว้นวรรค"""
    cleaned = re.sub(r"[^\u0e00-\u0e7fa-z0-9]", "", s.lower())
    if len(cleaned) < 2:
        return {cleaned} if cleaned else set()
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


def _calculate_string_similarity(query: str, target: str) -> float:
    """คำนวณความคล้ายคลึงของข้อความ (0.0 - 1.0)"""
    q = _nfc((query or "").strip().lower())
    t = _nfc((target or "").strip().lower())
    if not q or not t:
        return 0.0
    if q in t:
        return 1.0
    qb = _bigrams(q)
    tb = _bigrams(t)
    if not qb or not tb:
        return 0.0
    intersection = len(qb & tb)
    union = len(qb | tb)
    return intersection / union if union > 0 else 0.0


def calculate_product_match_score(
    product: models.Product,
    keyword: str,
    budget: Optional[float] = None,
) -> float:
    """คำนวณคะแนน Multi-factor Match Score (0 - 100) สำหรับสินค้าแต่ละชิ้น
    - Relevance (40%)
    - Rating (20%)
    - Sales Volume (20%)
    - Commission (10%)
    - Budget Fit (10%)
    """
    if not product or product.link_status != "ok":
        return 0.0

    q = _nfc(normalize_query((keyword or "").strip().lower()))
    name = _nfc(normalize_query((product.name or "").strip().lower()))
    cat = _nfc((product.category or "").strip().lower())

    # --- 1. Relevance Score (Max 40.0) ---
    relevance_score = 0.0
    if q:
        if q in name:
            pos = name.find(q) / max(len(name), 1)
            count = name.count(q)
            if pos <= 0.25 or count >= 2:
                relevance_score = 40.0
            elif pos <= 0.55:
                relevance_score = 35.0
            else:
                relevance_score = 30.0
        elif q in cat or (cat and cat in q):
            relevance_score = 25.0
        else:
            sim = _calculate_string_similarity(q, name)
            relevance_score = sim * 30.0
    else:
        relevance_score = 20.0

    relevance_score = min(max(relevance_score, 0.0), 40.0)

    # --- 2. Rating Score (Max 20.0) ---
    rating = float(product.rating or 0.0)
    rating_score = (min(rating, 5.0) / 5.0) * 20.0
    rating_score = min(max(rating_score, 0.0), 20.0)

    # --- 3. Sales Volume Score (Max 20.0) ---
    sales = max(int(product.sales_count or 0), 0)
    if sales > 0:
        sales_score = min(math.log10(max(sales, 1)) / 4.0, 1.0) * 20.0
    else:
        sales_score = 0.0
    sales_score = min(max(sales_score, 0.0), 20.0)

    # --- 4. Commission Score (Max 10.0) ---
    commission = float(product.commission or 0.0)
    comm_score = min(commission / 40.0, 1.0) * 10.0
    comm_score = min(max(comm_score, 0.0), 10.0)

    # --- 5. Budget Fit Score (Max 10.0) ---
    price = float(product.price or 0.0)
    budget_score = 0.0
    if budget is not None and budget > 0:
        if price <= budget:
            budget_score = 10.0
        elif price <= budget * 1.1:
            budget_score = 7.0
        else:
            diff_ratio = (price - budget) / budget
            budget_score = max(0.0, 10.0 - (diff_ratio * 20.0))
    else:
        # Sweet spot 100 - 1500 บาท
        if 50.0 <= price <= 1500.0:
            budget_score = 10.0
        elif price < 50.0:
            budget_score = 7.0
        else:
            budget_score = max(0.0, 10.0 - (price / 5000.0) * 5.0)

    budget_score = min(max(budget_score, 0.0), 10.0)

    total_score = relevance_score + rating_score + sales_score + comm_score + budget_score
    return round(min(max(total_score, 0.0), 100.0), 2)


def generate_suggested_reasons(
    product: models.Product,
    budget: Optional[float] = None,
) -> List[str]:
    """สร้างรายการเหตุผลที่เลือกรองรับ AI Reasoning (Suggested Reasons)
    แสดงเกณฑ์เชิงประจักษ์: รีวิวร้านค้า, ยอดขาย, ราคา/งบประมาณ, คอมมิชชั่น, ความปลอดภัยของลิงก์
    """
    reasons: List[str] = []
    if not product:
        return reasons

    price = float(product.price or 0.0)
    rating = float(product.rating or 0.0)
    sales = int(product.sales_count or 0)
    commission = float(product.commission or 0.0)

    # 1. รีวิวและความพึงพอใจ
    if rating >= 4.5:
        reasons.append(f"⭐ รีวิวสูง {rating:.1f}/5 ดาว จากผู้ใช้จริง มั่นใจได้ในคุณภาพ")
    elif rating > 0:
        reasons.append(f"⭐ คะแนนร้านค้า {rating:.1f}/5 ดาว มาตรฐานดี")

    # 2. ยอดขายและความนิยม
    if sales >= 1000:
        reasons.append(f"🔥 ยอดขายดีสะสมกว่า {sales:,} ชิ้น การันตีของดีตรงปก")
    elif sales >= 100:
        reasons.append(f"📦 ยอดขายต่อเนื่อง {sales:,} ชิ้น ในหมวด {product.category or 'สินค้าแนะนำ'}")
    elif sales > 0:
        reasons.append(f"🛍️ ยอดสั่งซื้อสะสม {sales:,} ชิ้น")

    # 3. ความคุ้มค่าด้านราคาและงบประมาณ
    if budget is not None and budget > 0 and price <= budget:
        saved = budget - price
        if saved > 0:
            reasons.append(f"💰 ราคา {price:,.2f} บาท อยู่ในงบที่ลูกค้าตั้งไว้ ({budget:,.2f} บาท) ประหยัด {saved:,.2f} บาท")
        else:
            reasons.append(f"💰 ราคา {price:,.2f} บาท พอดีกับงบประมาณที่ลูกค้ากำหนด ({budget:,.2f} บาท)")
    else:
        reasons.append(f"🏷️ ราคาสุดคุ้มเพียง {price:,.2f} บาท คุ้มค่าเมื่อเทียบกับสเปก")

    # 4. ผลตอบแทนค่านายหน้า
    if commission > 0:
        comm_pct = (commission / price * 100) if price > 0 else 0
        reasons.append(f"💸 ค่าคอมมิชชั่น {commission:,.2f} บาท ({comm_pct:.1f}%) สำหรับนายหน้า")

    # 5. ความปลอดภัยและการันตีลิงก์
    reasons.append("🛡️ ผ่านการตรวจสอบสถานะลิงก์ Affiliate (Link Status: OK) พร้อมสั่งซื้อทันที")

    return reasons


def match_best_product_for_demand(
    db: Session,
    product_keyword: Optional[str] = None,
    budget: Optional[float] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """ค้นหาและจับคู่สินค้าที่ดีที่สุดในคลัง `products`
    
    ข้อกำหนดเด็ดขาด:
    - เฉพาะ `Product.link_status == 'ok'` เท่านั้น
    - จัดอันดับตาม Multi-factor Match Score
    - คืน structured dictionary พร้อม Best product, match score, suggested reasons, และ candidates
    """
    # Query candidate products strictly with link_status == 'ok'
    candidates_query = db.query(models.Product).filter(
        models.Product.link_status == "ok"
    )
    all_ok_products = candidates_query.all()

    if not all_ok_products:
        logger.warning("No products with link_status == 'ok' found in database.")
        return {
            "best_product": None,
            "match_score": 0.0,
            "suggested_reasons": [],
            "candidates": [],
        }

    scored_candidates = []
    kw = (product_keyword or "").strip()

    for product in all_ok_products:
        score = calculate_product_match_score(product, keyword=kw, budget=budget)
        reasons = generate_suggested_reasons(product, budget=budget)
        scored_candidates.append({
            "product": product,
            "score": score,
            "reasons": reasons,
        })

    # Sort descending by score, then sales_count, then ai_score
    scored_candidates.sort(
        key=lambda x: (
            x["score"],
            int(x["product"].sales_count or 0),
            int(x["product"].ai_score or 0),
        ),
        reverse=True,
    )

    top_candidates = scored_candidates[:limit]
    best = top_candidates[0] if top_candidates else None

    return {
        "best_product": best["product"] if best else None,
        "match_score": best["score"] if best else 0.0,
        "suggested_reasons": best["reasons"] if best else [],
        "candidates": top_candidates,
    }
