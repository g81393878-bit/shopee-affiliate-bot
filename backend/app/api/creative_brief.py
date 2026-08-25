"""
Creative Brief API — สร้าง/ดู/จัดการชิ้นงานโฆษณา 3 มุมมองสำหรับ Meta Ads

ตามหลัก "Creative is Targeting":
- POST /api/creative-briefs/generate  → สร้าง Brief ใหม่จากข้อมูลสินค้า
- GET  /api/creative-briefs/product/{product_id}  → ดู Brief ของสินค้า
- GET  /api/creative-briefs/{brief_id}  → ดู Brief มุมมองเดียว
- DELETE /api/creative-briefs/product/{product_id}  → ลบ Brief ของสินค้า (สร้างใหม่ได้)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Product, CreativeBrief
from app.schemas import (
    CreativeBriefOut,
    CreativeBriefSingleOut,
    CreativeBriefPerspective,
    CreativeBriefGenerateRequest,
)
from app.services.creative_brief_generator import generate_creative_brief, PERSPECTIVES

logger = logging.getLogger(__name__)

router = APIRouter(tags=["creative-briefs"])


def _brief_to_perspective(brief: CreativeBrief) -> CreativeBriefPerspective:
    return CreativeBriefPerspective(
        perspective=brief.perspective,
        hook=brief.hook,
        script_body=brief.script_body,
        cta=brief.cta,
        caption=brief.caption,
        hashtags=brief.hashtags or [],
        format_type=brief.format_type,
        video_duration=brief.video_duration,
        target_behavior=brief.target_behavior,
        thumbnail_prompt=brief.thumbnail_prompt,
        ai_confidence=brief.ai_confidence or 0,
    )


@router.post("/creative-briefs/generate", response_model=CreativeBriefOut)
def create_creative_brief(
    req: CreativeBriefGenerateRequest,
    db: Session = Depends(get_db),
):
    """สร้าง Creative Brief 3 มุมมองสำหรับสินค้า"""
    product = db.query(Product).filter(Product.id == req.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")

    # ลบ Brief เก่าถ้ามี (สร้างใหม่ทับได้)
    db.query(CreativeBrief).filter(CreativeBrief.product_id == req.product_id).delete()

    # เรียก LLM สร้าง Brief
    result = generate_creative_brief(
        name=product.name,
        category=product.category or "",
        price=float(product.price or 0),
        rating=float(product.rating or 0),
        sales_count=product.sales_count or 0,
        commission=float(product.commission or 0),
        image_url=product.image_url or "",
        tone=req.tone,
        market_tone=req.market_tone,
    )

    # บันทึกลง DB
    briefs = []
    perspective_meta = {
        "problem_solution": {"format_type": "vertical_video", "video_duration": "15-30s"},
        "review": {"format_type": "vertical_video", "video_duration": "30-60s"},
        "education": {"format_type": "vertical_video", "video_duration": "30-60s"},
    }

    for perspective_key in ("problem_solution", "review", "education"):
        p_data = result.get(perspective_key, {})
        meta = perspective_meta[perspective_key]
        brief = CreativeBrief(
            product_id=req.product_id,
            perspective=perspective_key,
            hook=p_data.get("hook", ""),
            script_body=p_data.get("script_body", ""),
            cta=p_data.get("cta", ""),
            caption=p_data.get("caption", ""),
            hashtags=p_data.get("hashtags", []),
            format_type=p_data.get("format_type", meta["format_type"]),
            video_duration=p_data.get("video_duration", meta["video_duration"]),
            target_behavior=p_data.get("target_behavior", ""),
            thumbnail_prompt=p_data.get("thumbnail_prompt", ""),
            ai_confidence=p_data.get("ai_confidence", 60),
        )
        db.add(brief)
        briefs.append(brief)

    db.commit()
    for b in briefs:
        db.refresh(b)

    return CreativeBriefOut(
        product_id=req.product_id,
        product_name=product.name,
        perspectives=[_brief_to_perspective(b) for b in briefs],
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/creative-briefs/product/{product_id}", response_model=CreativeBriefOut)
def get_briefs_by_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    """ดู Creative Brief ทั้ง 3 มุมมองของสินค้า"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")

    briefs = (
        db.query(CreativeBrief)
        .filter(CreativeBrief.product_id == product_id)
        .order_by(CreativeBrief.perspective)
        .all()
    )

    if not briefs:
        raise HTTPException(status_code=404, detail="ยังไม่มี Creative Brief — ใช้ POST /creative-briefs/generate เพื่อสร้าง")

    return CreativeBriefOut(
        product_id=product_id,
        product_name=product.name,
        perspectives=[_brief_to_perspective(b) for b in briefs],
        generated_at=briefs[0].created_at,
    )


@router.get("/creative-briefs/{brief_id}", response_model=CreativeBriefSingleOut)
def get_single_brief(
    brief_id: int,
    db: Session = Depends(get_db),
):
    """ดู Creative Brief มุมมองเดียว"""
    brief = db.query(CreativeBrief).filter(CreativeBrief.id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="ไม่พบ Creative Brief")
    p = _brief_to_perspective(brief)
    return CreativeBriefSingleOut(
        id=brief.id,
        product_id=brief.product_id,
        perspective=p.perspective,
        hook=p.hook,
        script_body=p.script_body,
        cta=p.cta,
        caption=p.caption,
        hashtags=p.hashtags,
        format_type=p.format_type,
        video_duration=p.video_duration,
        target_behavior=p.target_behavior,
        thumbnail_prompt=p.thumbnail_prompt,
        ai_confidence=p.ai_confidence,
        created_at=brief.created_at,
    )


@router.delete("/creative-briefs/product/{product_id}")
def delete_briefs_by_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    """ลบ Creative Brief ทั้งหมดของสินค้า (สร้างใหม่ได้ด้วย POST /generate)"""
    count = db.query(CreativeBrief).filter(CreativeBrief.product_id == product_id).delete()
    db.commit()
    return {"deleted": count, "product_id": product_id}
