from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
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


# ===========================================================================
# Social Demand Radar V1 Schemas
# ===========================================================================

# --- Facebook Group Monitor Schemas ---
class FacebookGroupMonitorBase(BaseModel):
    group_id: str = Field(..., max_length=100)
    group_name: str = Field(..., max_length=255)
    group_url: str
    category_tag: Optional[str] = Field(None, max_length=100)
    is_active: bool = True
    check_interval_minutes: int = 60

class FacebookGroupMonitorCreate(FacebookGroupMonitorBase):
    pass

class FacebookGroupMonitorUpdate(BaseModel):
    group_name: Optional[str] = None
    group_url: Optional[str] = None
    category_tag: Optional[str] = None
    is_active: Optional[bool] = None
    check_interval_minutes: Optional[int] = None

class FacebookGroupMonitorOut(FacebookGroupMonitorBase):
    id: int
    last_scanned_at: Optional[datetime] = None
    post_count_detected: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Facebook Detected Lead Schemas ---
class FacebookDetectedLeadBase(BaseModel):
    fb_post_id: str = Field(..., max_length=100)
    post_url: str
    author_name: Optional[str] = Field(None, max_length=255)
    post_text: str
    post_time: Optional[datetime] = None
    group_id: Optional[int] = None
    raw_data: Optional[Dict[str, Any]] = None

class FacebookDetectedLeadCreate(FacebookDetectedLeadBase):
    pass

class FacebookDetectedLeadOut(FacebookDetectedLeadBase):
    id: int
    status: str
    detected_at: datetime

    class Config:
        from_attributes = True


# --- Facebook Demand Event Schemas ---
class FacebookDemandEventBase(BaseModel):
    lead_id: int
    intent: str = "unknown"
    demand_score: int = Field(default=0, ge=0, le=100)
    urgency: str = "low"  # high | medium | low
    budget: Optional[str] = None
    product_keyword: Optional[str] = None
    matched_product_id: Optional[int] = None
    suggested_reason: Optional[Union[Dict[str, Any], List[Any]]] = None
    ai_comment_draft: Optional[str] = None
    notification_status: str = "pending"

class FacebookDemandEventCreate(FacebookDemandEventBase):
    pass

class FacebookDemandEventOut(FacebookDemandEventBase):
    id: int
    notification_sent_at: Optional[datetime] = None
    created_at: datetime
    matched_product: Optional[ProductOut] = None

    class Config:
        from_attributes = True


# --- Lead Action & Data Flywheel Schemas ---
class LeadActionBase(BaseModel):
    demand_event_id: int
    lead_id: Optional[int] = None
    action_type: str = Field(..., max_length=50)  # reply_posted | manual_reply | ignored | product_swapped
    admin_id: Optional[str] = None
    comment_posted: Optional[str] = None
    affiliate_link_used: Optional[str] = None
    feedback_score: Optional[int] = Field(None, ge=1, le=5)
    click_count: int = 0
    order_count: int = 0
    commission_earned: Decimal = Field(default=Decimal("0.00"))
    conversion_status: str = "pending"
    notes: Optional[str] = None

class LeadActionCreate(BaseModel):
    demand_event_id: int
    action_type: str = Field(..., max_length=50)
    lead_id: Optional[int] = None
    admin_id: Optional[str] = None
    comment_posted: Optional[str] = None
    affiliate_link_used: Optional[str] = None
    feedback_score: Optional[int] = None
    notes: Optional[str] = None

class LeadActionUpdate(BaseModel):
    click_count: Optional[int] = None
    order_count: Optional[int] = None
    commission_earned: Optional[Decimal] = None
    conversion_status: Optional[str] = None
    notes: Optional[str] = None

class LeadActionOut(LeadActionBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Ingestion & Radar API Payloads ---
class LeadIngestItem(BaseModel):
    fb_post_id: str
    post_url: str
    author_name: Optional[str] = None
    post_text: str
    post_time: Optional[datetime] = None
    group_id: Optional[Union[str, int]] = None
    group_name: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

class LeadIngestPayload(BaseModel):
    leads: List[LeadIngestItem]

class IngestedLeadResult(BaseModel):
    fb_post_id: str
    lead_id: int
    status: str
    demand_score: Optional[int] = None
    intent: Optional[str] = None
    alert_sent: bool = False
    matched_product_id: Optional[int] = None

class LeadIngestionResponse(BaseModel):
    total_received: int
    processed: int
    high_demand_count: int
    alerts_sent: int
    results: List[IngestedLeadResult]

class RadarStatsResponse(BaseModel):
    total_leads_scanned: int
    high_demand_leads: int
    action_taken_count: int
    total_clicks: int
    total_orders: int
    total_commission_earned: Decimal
    top_demanded_keywords: List[Dict[str, Any]]


