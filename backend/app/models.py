import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Numeric, Text, Date, DateTime, ForeignKey, Float, JSON, Boolean
from sqlalchemy.orm import relationship
from app.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String(50), default="affiliate_manager", nullable=False) # admin | affiliate_manager | caregiver_staff
    line_user_id = Column(String(100), unique=True, index=True, nullable=True)
    shopee_affiliate_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    @property
    def affiliate_id(self):
        return self.shopee_affiliate_id

    @affiliate_id.setter
    def affiliate_id(self, value):
        self.shopee_affiliate_id = value


class UserPreference(Base):
    """Account Memory (Amazon-style): สิ่งที่ลูกค้าบอกให้ป้าเข็มจำไว้
    — ตารางแยก (ไม่ใช่ users เพราะ users = auth.users ของ Supabase)
    categories: ["แมว", "หูฟัง"] หมวดที่ลูกค้าบอกว่าชอบ
    notes: ["เลี้ยงแมว 2 ตัว"] สิ่งที่ลูกค้าบอกให้จำ
    """
    __tablename__ = "user_preferences"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    line_user_id = Column(String(100), unique=True, index=True, nullable=False)
    categories = Column(JSON, nullable=True)
    notes = Column(JSON, nullable=True)
    tone = Column(String(10), nullable=True)  # youth | elder | neutral — โทนภาษาที่จำไว้ถาวร
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)


class ShopeeProduct(Base):
    """Raw products pulled from Shopee Affiliate Open API (productOfferV2) — staging table.
    Bulk-fetched catalog; curated picks get promoted into `products` for the LINE bot.
    """
    __tablename__ = "shopee_products"

    # BIGSERIAL on Postgres; INTEGER on SQLite (dev) so autoincrement works on both
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    item_id = Column(BigInteger, unique=True, index=True, nullable=False)
    shop_id = Column(BigInteger, index=True, nullable=True)
    shop_name = Column(Text, nullable=True)
    product_name = Column(Text, nullable=False)
    product_link = Column(Text, nullable=True)
    offer_link = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)
    price_min = Column(Numeric(12, 2), nullable=True)
    price_max = Column(Numeric(12, 2), nullable=True)
    price_discount_rate = Column(Float, nullable=True)
    sales = Column(Integer, nullable=True)
    rating_star = Column(Float, nullable=True)
    commission_rate = Column(Text, nullable=True)
    seller_commission_rate = Column(Text, nullable=True)
    shopee_commission_rate = Column(Text, nullable=True)
    commission = Column(Numeric(12, 2), nullable=True)
    shop_type = Column(Integer, nullable=True)
    category_id = Column(BigInteger, nullable=True)
    period_start_time = Column(BigInteger, nullable=True)
    period_end_time = Column(BigInteger, nullable=True)
    raw_json = Column(JSON, nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    price = Column(Numeric(10, 2), default=0.00, nullable=False)
    rating = Column(Float, default=0.00, nullable=True)
    sales_count = Column(Integer, default=0, nullable=True)
    commission = Column(Numeric(10, 2), default=0.00, nullable=True)
    affiliate_url = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)  # รูปสินค้า (og:image) — ใช้โพสต์ Facebook แบบแนบรูป
    link_status = Column(String(20), default="unknown", nullable=False)  # ok | dead | suspect | unknown | none
    ai_score = Column(Integer, default=0, nullable=True)
    price_checked_at = Column(DateTime(timezone=True), nullable=True)  # ครั้งสุดท้ายที่อัปเดตราคาจริง
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    @property
    def score(self) -> int:
        return self.ai_score or 0

    # Relationships
    analysis = relationship("ProductAnalysis", back_populates="product", uselist=False, cascade="all, delete-orphan")
    contents = relationship("Content", back_populates="product", cascade="all, delete-orphan")


class ProductAnalysis(Base):
    __tablename__ = "product_analysis"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, default=0, nullable=True)
    target_customer = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True) # JSON list
    analysis_date = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    # Relationships
    product = relationship("Product", back_populates="analysis")


class Content(Base):
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    style = Column(String(50), default="Standard", nullable=False) # Standard | Funny | Educational | Unboxing
    hook = Column(Text, nullable=True)
    problem = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    cta = Column(Text, nullable=True)
    caption = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    # Relationships
    product = relationship("Product", back_populates="contents")
    performance_logs = relationship("PerformanceLog", back_populates="content", cascade="all, delete-orphan")


class ChatLog(Base):
    """ประวัติการสนทนากับลูกค้า (PDPA: เก็บแค่ 90 วันแล้วลบอัตโนมัติ —
    ใช้ติดตามความสนใจสินค้า/ทวงถาม; ลูกค้าสั่ง "ลบข้อมูลฉัน" ได้ทุกเมื่อ)"""
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    line_user_id = Column(String(100), index=True, nullable=False)
    message_text = Column(Text, nullable=False)
    intent = Column(String(30), default="unknown", nullable=False)  # greeting|search|deals|top|wismo|privacy|delete|unknown
    category = Column(String(50), nullable=True)  # หมวดที่ลูกค้าสนใจ (แท็กตอนค้น — ต่อยอดวิเคราะห์/แนะนำ)
    reply_kind = Column(String(20), default="text", nullable=False)  # text|flex
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, index=True)


class PriceHistory(Base):
    """ประวัติราคา — บันทึกราคาเก่า→ใหม่ทุกครั้งที่ refresh-prices เจอราคาเปลี่ยน
    ใช้แจ้งเตือนราคาตกให้ลูกค้าที่สนใจหมวดนั้น (ต่อยอดจาก chat_logs)"""
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    price_old = Column(Numeric(12, 2), nullable=True)
    price_new = Column(Numeric(12, 2), nullable=True)
    drop_pct = Column(Numeric(6, 2), nullable=True)  # % ที่ลดลง (ติดลบ = ขึ้นราคา)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)


class CampaignLog(Base):
    """บันทึกแคมเปญที่ส่ง — กันส่งซ้ำ + ตรวจสอบ (เฉพาะเจ้าของร้านสั่ง)"""
    __tablename__ = "campaign_logs"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False)
    recipients = Column(Integer, default=0, nullable=False)
    status = Column(String(10), default="dryrun", nullable=False)  # dryrun | sent | pricedrop | reengage
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)


class PerformanceLog(Base):
    __tablename__ = "performance_logs"

    id = Column(Integer, primary_key=True, index=True)
    content_id = Column(Integer, ForeignKey("contents.id", ondelete="CASCADE"), nullable=False)
    views = Column(Integer, default=0, nullable=True)
    clicks = Column(Integer, default=0, nullable=True)
    orders = Column(Integer, default=0, nullable=True)
    commission = Column(Numeric(10, 2), default=0.00, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    # Relationships
    content = relationship("Content", back_populates="performance_logs")


# ===========================================================================
# Social Demand Radar V1 Models
# ===========================================================================

class FacebookGroupMonitor(Base):
    """กลุ่ม Facebook เป้าหมายที่ระบบเฝ้าส่องความต้องการซื้อสินค้า"""
    __tablename__ = "facebook_groups_monitor"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    group_id = Column(String(100), unique=True, index=True, nullable=False)
    group_name = Column(String(255), nullable=False)
    group_url = Column(Text, nullable=False)
    category_tag = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    check_interval_minutes = Column(Integer, default=60, nullable=False)
    last_scanned_at = Column(DateTime(timezone=True), nullable=True)
    post_count_detected = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=True)

    # Relationships
    leads = relationship("FacebookDetectedLead", back_populates="group")


class FacebookDetectedLead(Base):
    """โพสต์ดิบที่ตรวจพบจากกลุ่ม Facebook ก่อน/หลังการวิเคราะห์ Demand"""
    __tablename__ = "facebook_detected_leads"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    group_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("facebook_groups_monitor.id", ondelete="SET NULL"), nullable=True, index=True)
    fb_post_id = Column(String(100), unique=True, index=True, nullable=False)
    post_url = Column(Text, nullable=False)
    author_name = Column(String(255), nullable=True)
    post_text = Column(Text, nullable=False)
    post_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), default="pending", nullable=False, index=True)  # pending | analyzed | ignored | error
    raw_data = Column(JSON, nullable=True)
    detected_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False, index=True)

    # Relationships
    group = relationship("FacebookGroupMonitor", back_populates="leads")
    demand_events = relationship("FacebookDemandEvent", back_populates="lead", cascade="all, delete-orphan")
    actions = relationship("LeadAction", back_populates="lead", cascade="all, delete-orphan")


class FacebookDemandEvent(Base):
    """เหตุการณ์ Demand / ดีลที่ AI วิเคราะห์ได้ พร้อมสินค้าแนะนำ เหตุผล และข้อความป้ายยา"""
    __tablename__ = "facebook_demand_events"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    lead_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("facebook_detected_leads.id", ondelete="CASCADE"), nullable=False, index=True)
    intent = Column(String(50), default="unknown", nullable=False)  # buy_request | product_inquiry | general_discussion | spam
    demand_score = Column(Integer, default=0, nullable=False, index=True)  # 0 - 100
    urgency = Column(String(20), default="low", nullable=False)  # high | medium | low
    budget = Column(String(100), nullable=True)
    product_keyword = Column(String(255), nullable=True)
    matched_product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    suggested_reason = Column(JSON, nullable=True)  # dict/list of reason criteria
    ai_comment_draft = Column(Text, nullable=True)  # ข้อความร่างสไตล์ป้าเข็ม
    notification_status = Column(String(30), default="pending", nullable=False, index=True)  # pending | sent | failed | skipped_low_score
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False, index=True)

    # Relationships
    lead = relationship("FacebookDetectedLead", back_populates="demand_events")
    matched_product = relationship("Product", foreign_keys=[matched_product_id])
    actions = relationship("LeadAction", back_populates="demand_event", cascade="all, delete-orphan")


class LeadAction(Base):
    """พฤติกรรมและการตัดสินใจของแอดมินในการจัดการดีลเพื่อสร้าง Data Flywheel"""
    __tablename__ = "lead_actions"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    demand_event_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("facebook_demand_events.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("facebook_detected_leads.id", ondelete="CASCADE"), nullable=True, index=True)
    action_type = Column(String(50), nullable=False)  # reply_posted | manual_reply | ignored | product_swapped
    admin_id = Column(String(100), nullable=True)
    comment_posted = Column(Text, nullable=True)
    affiliate_link_used = Column(Text, nullable=True)
    feedback_score = Column(Integer, nullable=True)  # 1-5 rating on AI suggestion
    click_count = Column(Integer, default=0, nullable=False)
    order_count = Column(Integer, default=0, nullable=False)
    commission_earned = Column(Numeric(10, 2), default=0.00, nullable=False)
    conversion_status = Column(String(30), default="pending", nullable=False)  # pending | clicked | converted | no_sale
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=True)

    # Relationships
    demand_event = relationship("FacebookDemandEvent", back_populates="actions")
    lead = relationship("FacebookDetectedLead", back_populates="actions")

