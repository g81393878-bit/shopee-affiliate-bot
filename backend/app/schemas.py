from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

# --- User Schemas ---
class UserBase(BaseModel):
    name: str = Field(..., max_length=100)
    role: str = Field("affiliate_manager", max_length=50) # admin | affiliate_manager | caregiver_staff
    line_user_id: Optional[str] = Field(None, max_length=100)
    shopee_affiliate_id: Optional[str] = Field(None, max_length=100)
    affiliate_id: Optional[str] = Field(None, max_length=100)

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    line_user_id: Optional[str] = None
    shopee_affiliate_id: Optional[str] = None
    affiliate_id: Optional[str] = None

class UserOut(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Product Schemas ---
class ProductBase(BaseModel):
    name: str = Field(..., max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    price: Decimal = Field(default=Decimal("0.00"))
    rating: Optional[float] = Field(default=0.0)
    sales_count: Optional[int] = Field(default=0)
    commission: Optional[Decimal] = Field(default=Decimal("0.00"))
    affiliate_url: Optional[str] = Field(None)

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[Decimal] = None
    rating: Optional[float] = None
    sales_count: Optional[int] = None
    commission: Optional[Decimal] = None
    affiliate_url: Optional[str] = None
    ai_score: Optional[int] = None

class ProductOut(ProductBase):
    id: int
    ai_score: int
    score: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Product Analysis Schemas ---
class ProductAnalysisOut(BaseModel):
    id: int
    product_id: int
    score: int
    target_customer: Optional[str] = None
    reason: List[str] = [] # JSON list parsed
    analysis_date: datetime

    class Config:
        from_attributes = True


# --- Content Schemas ---
class ContentBase(BaseModel):
    product_id: int
    style: str = "Standard" # Standard | Funny | Educational | Unboxing
    hook: Optional[str] = None
    problem: Optional[str] = None
    solution: Optional[str] = None
    cta: Optional[str] = None
    caption: Optional[str] = None

class ContentCreate(ContentBase):
    pass

class ContentOut(ContentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Performance Log Schemas ---
class PerformanceLogBase(BaseModel):
    content_id: int
    views: Optional[int] = 0
    clicks: Optional[int] = 0
    orders: Optional[int] = 0
    commission: Optional[Decimal] = Decimal("0.00")

class PerformanceLogCreate(PerformanceLogBase):
    commission_earned: Optional[Decimal] = None
    date: Optional[str] = None

class PerformanceLogOut(PerformanceLogBase):
    id: int
    ctr: float
    conversion_rate: float
    epc: float
    created_at: datetime

    class Config:
        from_attributes = True


# --- Analytics / Dashboard Schemas ---
class PerformanceSummaryResponse(BaseModel):
    total_views: int
    total_clicks: int
    total_orders: int
    total_commission: Decimal
    average_ctr: float  # clicks / views * 100
    conversion_rate: float  # orders / clicks * 100
    earnings_per_click: float  # commission / clicks


# --- AI Service Response Schemas ---
class ScriptGeneratorResponse(BaseModel):
    hook: str
    problem: str
    solution: str
    cta: str
    caption: str
    hashtags: List[str]
    title: str
    thumbnail_prompt: str

class AIAnalysisResult(BaseModel):
    product_score: int
    recommendation: str
    reasons: List[str]
    content_ideas: List[str]
    script: Optional[ScriptGeneratorResponse] = None
    content_id: Optional[int] = None

