-- Migration: 20260815194500_social_demand_radar.sql
-- Description: Create tables for Social Demand Radar V1 (บอทป้าเข็ม)
-- Tables: facebook_detected_leads, facebook_demand_events, lead_actions

-- 1. Facebook Detected Leads Table
CREATE TABLE IF NOT EXISTS facebook_detected_leads (
    id              BIGSERIAL PRIMARY KEY,
    fb_post_id      VARCHAR(100) NOT NULL UNIQUE,
    post_url        TEXT NOT NULL,
    author_name     VARCHAR(255),
    post_text       TEXT NOT NULL,
    post_time       TIMESTAMPTZ,
    status          VARCHAR(30) NOT NULL DEFAULT 'pending',
    raw_data        JSONB,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fb_leads_post_id ON facebook_detected_leads(fb_post_id);
CREATE INDEX IF NOT EXISTS idx_fb_leads_status ON facebook_detected_leads(status);
CREATE INDEX IF NOT EXISTS idx_fb_leads_detected_at ON facebook_detected_leads(detected_at);


-- 3. Facebook Demand Events Table
CREATE TABLE IF NOT EXISTS facebook_demand_events (
    id                      BIGSERIAL PRIMARY KEY,
    lead_id                 BIGINT NOT NULL REFERENCES facebook_detected_leads(id) ON DELETE CASCADE,
    intent                  VARCHAR(50) NOT NULL DEFAULT 'unknown',
    demand_score            INTEGER NOT NULL DEFAULT 0,
    urgency                 VARCHAR(20) NOT NULL DEFAULT 'low',
    budget                  VARCHAR(100),
    product_keyword         VARCHAR(255),
    matched_product_id      INTEGER REFERENCES products(id) ON DELETE SET NULL,
    suggested_reason        JSONB,
    ai_comment_draft        TEXT,
    notification_status     VARCHAR(30) NOT NULL DEFAULT 'pending',
    notification_sent_at    TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fb_demand_lead_id ON facebook_demand_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_fb_demand_score ON facebook_demand_events(demand_score);
CREATE INDEX IF NOT EXISTS idx_fb_demand_matched_prod ON facebook_demand_events(matched_product_id);
CREATE INDEX IF NOT EXISTS idx_fb_demand_notif_status ON facebook_demand_events(notification_status);
CREATE INDEX IF NOT EXISTS idx_fb_demand_created_at ON facebook_demand_events(created_at);


-- 4. Lead Actions (Data Flywheel) Table
CREATE TABLE IF NOT EXISTS lead_actions (
    id                  BIGSERIAL PRIMARY KEY,
    demand_event_id     BIGINT NOT NULL REFERENCES facebook_demand_events(id) ON DELETE CASCADE,
    lead_id             BIGINT REFERENCES facebook_detected_leads(id) ON DELETE CASCADE,
    action_type         VARCHAR(50) NOT NULL,
    admin_id            VARCHAR(100),
    comment_posted      TEXT,
    affiliate_link_used TEXT,
    feedback_score      INTEGER,
    click_count         INTEGER NOT NULL DEFAULT 0,
    order_count         INTEGER NOT NULL DEFAULT 0,
    commission_earned   NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    conversion_status   VARCHAR(30) NOT NULL DEFAULT 'pending',
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lead_actions_demand_id ON lead_actions(demand_event_id);
CREATE INDEX IF NOT EXISTS idx_lead_actions_lead_id ON lead_actions(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_actions_action_type ON lead_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_lead_actions_created_at ON lead_actions(created_at);
