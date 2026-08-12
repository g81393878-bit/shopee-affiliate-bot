from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import json
from app.db import get_db
from app import models, schemas
from app.services.ai_analyzer import analyze_product_with_ai, calculate_heuristic_score
from app.services.ai_generator import generate_script_for_product
from app.services.link_checker import check_affiliate_link

router = APIRouter(prefix="/products", tags=["Products"])


def verify_affiliate_link(url: str) -> str:
    """นโยบายเด็ดขาด: สินค้าทุกตัวต้องมีลิงก์ affiliate ที่ตรวจผ่านแล้ว (OK) เท่านั้น"""
    url = (url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="ต้องระบุ affiliate_url (ลิงก์สั้น s.shopee.co.th)")
    status, detail = check_affiliate_link(url)
    if status != "OK":
        raise HTTPException(
            status_code=400,
            detail=f"ลิงก์ affiliate ตรวจไม่ผ่าน ({status}: {detail}) — สินค้าที่ไม่มีค่านายหน้า/ลิงก์เสียห้ามเข้าระบบ",
        )
    return url

@router.get("/", response_model=List[schemas.ProductOut])
def list_products(
    category: Optional[str] = None,
    min_score: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Product)
    if category:
        query = query.filter(models.Product.category.ilike(f"%{category}%"))
    if min_score is not None:
        query = query.filter(models.Product.ai_score >= min_score)
    if search:
        query = query.filter(models.Product.name.ilike(f"%{search}%"))
        
    return query.order_by(models.Product.ai_score.desc()).all()


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/", response_model=schemas.ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(product_in: schemas.ProductCreate, db: Session = Depends(get_db)):
    # Calculate heuristic score
    ai_score = calculate_heuristic_score(
        sales_count=product_in.sales_count or 0,
        rating=float(product_in.rating or 0.0),
        commission=float(product_in.commission or 0.0),
        price=float(product_in.price or 0.0)
    )
    
    db_product = models.Product(
        name=product_in.name,
        category=product_in.category,
        price=product_in.price,
        rating=product_in.rating,
        sales_count=product_in.sales_count,
        commission=product_in.commission,
        affiliate_url=verify_affiliate_link(product_in.affiliate_url),
        link_status="ok",
        ai_score=ai_score
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(product_id: int, product_in: schemas.ProductUpdate, db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    update_data = product_in.model_dump(exclude_unset=True)

    # ลิงก์เปลี่ยน → ต้องตรวจใหม่ก่อนบันทึก (นโยบายเด็ดขาด)
    if "affiliate_url" in update_data:
        if not update_data["affiliate_url"]:
            raise HTTPException(status_code=400, detail="affiliate_url ห้ามว่าง — สินค้าต้องมีลิงก์ affiliate")
        if update_data["affiliate_url"] != db_product.affiliate_url:
            update_data["affiliate_url"] = verify_affiliate_link(update_data["affiliate_url"])
            update_data["link_status"] = "ok"

    # Recalculate score if needed
    if any(k in update_data for k in ["sales_count", "rating", "commission", "price"]):
        sales_count = update_data.get("sales_count", db_product.sales_count or 0)
        rating = update_data.get("rating", db_product.rating or 0.0)
        commission = update_data.get("commission", db_product.commission or 0.0)
        price = update_data.get("price", db_product.price or 0.0)
        
        update_data["ai_score"] = calculate_heuristic_score(
            sales_count=sales_count,
            rating=float(rating),
            commission=float(commission),
            price=float(price)
        )
        
    for key, value in update_data.items():
        setattr(db_product, key, value)
        
    db.commit()
    db.refresh(db_product)
    return db_product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    db.delete(db_product)
    db.commit()
    return None


def run_product_analysis(product_id: int, db: Session) -> dict:
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Analyze product using LLM or mock helper
    analysis_data = analyze_product_with_ai(
        name=db_product.name,
        category=db_product.category or "General",
        price=float(db_product.price),
        rating=float(db_product.rating or 0.0),
        sales_count=db_product.sales_count or 0,
        commission=float(db_product.commission or 0.0)
    )
    
    # Update AI score on product table
    ai_score = analysis_data.get("product_score", db_product.ai_score)
    db_product.ai_score = ai_score
    
    # Check if analysis record exists, else create
    db_analysis = db.query(models.ProductAnalysis).filter(
        models.ProductAnalysis.product_id == product_id
    ).first()
    
    target_cust = analysis_data.get("script", {}).get("title", "General Public")
    reasons_json = json.dumps(analysis_data.get("reasons", []))
    
    if not db_analysis:
        db_analysis = models.ProductAnalysis(
            product_id=product_id,
            score=ai_score,
            target_customer=target_cust,
            reason=reasons_json
        )
        db.add(db_analysis)
    else:
        db_analysis.score = ai_score
        db_analysis.target_customer = target_cust
        db_analysis.reason = reasons_json
        
    # Check if standard script content exists in Contents, else create
    script_info = analysis_data.get("script", {})
    db_content = db.query(models.Content).filter(
        models.Content.product_id == product_id,
        models.Content.style == "Standard"
    ).first()
    
    if not db_content:
        db_content = models.Content(
            product_id=product_id,
            style="Standard",
            hook=script_info.get("hook"),
            problem=script_info.get("problem"),
            solution=script_info.get("solution"),
            cta=script_info.get("cta"),
            caption=script_info.get("caption")
        )
        db.add(db_content)
    else:
        db_content.hook = script_info.get("hook")
        db_content.problem = script_info.get("problem")
        db_content.solution = script_info.get("solution")
        db_content.cta = script_info.get("cta")
        db_content.caption = script_info.get("caption")
        
    db.commit()
    db.refresh(db_product)
    db.refresh(db_content)
    
    # Return structured dict compatible with schemas.AIAnalysisResult
    return {
        "product_score": ai_score,
        "recommendation": analysis_data.get("recommendation", "ควรทำ Content"),
        "reasons": analysis_data.get("reasons", []),
        "content_ideas": analysis_data.get("content_ideas", []),
        "script": {
            "hook": db_content.hook,
            "problem": db_content.problem,
            "solution": db_content.solution,
            "cta": db_content.cta,
            "caption": db_content.caption,
            "hashtags": script_info.get("hashtags", []),
            "title": script_info.get("title", ""),
            "thumbnail_prompt": script_info.get("thumbnail_prompt", "")
        },
        "content_id": db_content.id
    }


# Support both /analyze and /analysis endpoints
@router.post("/{product_id}/analyze")
def analyze_product_v1(product_id: int, db: Session = Depends(get_db)):
    return run_product_analysis(product_id, db)

@router.post("/{product_id}/analysis")
def analyze_product_v2(product_id: int, db: Session = Depends(get_db)):
    return run_product_analysis(product_id, db)


@router.post("/{product_id}/script", response_model=schemas.ScriptGeneratorResponse)
def generate_custom_script(product_id: int, style: str = "Standard", db: Session = Depends(get_db)):
    # Standardize style casing
    style_capitalized = style.capitalize() if style else "Standard"
    
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    script_data = generate_script_for_product(
        product_name=db_product.name,
        category=db_product.category or "General",
        price=float(db_product.price),
        style=style_capitalized
    )
    
    # Store or update the script content for this specific style
    db_content = db.query(models.Content).filter(
        models.Content.product_id == product_id,
        models.Content.style == style_capitalized
    ).first()
    
    if not db_content:
        db_content = models.Content(
            product_id=product_id,
            style=style_capitalized,
            hook=script_data.get("hook"),
            problem=script_data.get("problem"),
            solution=script_data.get("solution"),
            cta=script_data.get("cta"),
            caption=script_data.get("caption")
        )
        db.add(db_content)
    else:
        db_content.hook = script_data.get("hook")
        db_content.problem = script_data.get("problem")
        db_content.solution = script_data.get("solution")
        db_content.cta = script_data.get("cta")
        db_content.caption = script_data.get("caption")
        
    db.commit()
    
    return script_data
