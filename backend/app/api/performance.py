from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
from app.db import get_db
from app import models, schemas

router = APIRouter(prefix="/performance", tags=["Performance & Analytics"])

def create_perf_log(content_id: int, perf_in: schemas.PerformanceLogCreate, db: Session) -> models.PerformanceLog:
    # Verify content exists
    content = db.query(models.Content).filter(models.Content.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content record not found")
        
    # Handle commission vs commission_earned mapping
    commission_val = perf_in.commission
    if perf_in.commission_earned is not None:
        commission_val = perf_in.commission_earned
        
    db_perf = models.PerformanceLog(
        content_id=content_id,
        views=perf_in.views,
        clicks=perf_in.clicks,
        orders=perf_in.orders,
        commission=commission_val
    )
    db.add(db_perf)
    db.commit()
    db.refresh(db_perf)
    return db_perf


def build_perf_out(row: models.PerformanceLog) -> schemas.PerformanceLogOut:
    views = row.views or 0
    clicks = row.clicks or 0
    orders = row.orders or 0
    commission = row.commission or Decimal("0.00")
    
    ctr = (clicks / views * 100) if views > 0 else 0.0
    conversion_rate = (orders / clicks * 100) if clicks > 0 else 0.0
    epc = float(commission / clicks) if clicks > 0 else 0.0
    
    return schemas.PerformanceLogOut(
        id=row.id,
        content_id=row.content_id,
        views=views,
        clicks=clicks,
        orders=orders,
        commission=commission,
        ctr=round(ctr, 2),
        conversion_rate=round(conversion_rate, 2),
        epc=round(epc, 2),
        created_at=row.created_at
    )


# Support both POST /performance/contents/{content_id} and POST /performance
@router.post("/contents/{content_id}", response_model=schemas.PerformanceLogOut, status_code=status.HTTP_201_CREATED)
def log_performance_v1(content_id: int, perf_in: schemas.PerformanceLogCreate, db: Session = Depends(get_db)):
    db_perf = create_perf_log(content_id, perf_in, db)
    return build_perf_out(db_perf)


@router.post("", response_model=schemas.PerformanceLogOut, status_code=status.HTTP_201_CREATED)
def log_performance_v2(perf_in: schemas.PerformanceLogCreate, db: Session = Depends(get_db)):
    db_perf = create_perf_log(perf_in.content_id, perf_in, db)
    return build_perf_out(db_perf)


@router.get("/summary", response_model=schemas.PerformanceSummaryResponse)
def get_performance_summary(db: Session = Depends(get_db)):
    query = db.query(
        func.sum(models.PerformanceLog.views).label("views"),
        func.sum(models.PerformanceLog.clicks).label("clicks"),
        func.sum(models.PerformanceLog.orders).label("orders"),
        func.sum(models.PerformanceLog.commission).label("commission")
    )
    
    result = query.first()
    
    views = result.views or 0
    clicks = result.clicks or 0
    orders = result.orders or 0
    commission = result.commission or Decimal("0.00")
    
    # Calculate rates
    ctr = (clicks / views * 100) if views > 0 else 0.0
    conversion_rate = (orders / clicks * 100) if clicks > 0 else 0.0
    epc = float(commission / clicks) if clicks > 0 else 0.0
    
    return schemas.PerformanceSummaryResponse(
        total_views=views,
        total_clicks=clicks,
        total_orders=orders,
        total_commission=commission,
        average_ctr=round(ctr, 2),
        conversion_rate=round(conversion_rate, 2),
        earnings_per_click=round(epc, 2)
    )


@router.get("/daily", response_model=List[schemas.PerformanceLogOut])
def get_daily_performance(db: Session = Depends(get_db)):
    results = db.query(models.PerformanceLog).order_by(models.PerformanceLog.created_at.asc()).all()
    return [build_perf_out(row) for row in results]
