-- CampFinder Phase 2 schema additions
-- Run in Supabase SQL editor

-- ── 1. Replace leads table with full spec ──────────────────────────────────
DROP TABLE IF EXISTS leads CASCADE;

CREATE TABLE leads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_email        TEXT NOT NULL,
    parent_zip          TEXT,
    child_age_band      TEXT,               -- e.g. "6-8", "9-11", "12-14"
    weeks_needed        INTEGER,
    interests           TEXT[],
    target_camp_id      UUID REFERENCES camps(id) ON DELETE SET NULL,
    search_context      JSONB,              -- full search params snapshot
    message             TEXT,              -- optional "request info" message
    consent_flag        BOOLEAN DEFAULT FALSE,
    first_name          TEXT,
    source              TEXT DEFAULT 'search_gate',
    lead_status         TEXT DEFAULT 'new'
                            CHECK (lead_status IN ('new', 'emailed', 'contacted', 'converted')),
    billing_status      TEXT DEFAULT 'unpaid'
                            CHECK (billing_status IN ('unpaid', 'paid', 'refunded')),
    matched_camp_ids    UUID[],
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_leads_email   ON leads (parent_email);
CREATE INDEX idx_leads_status  ON leads (lead_status);
CREATE INDEX idx_leads_camp    ON leads (target_camp_id);
CREATE INDEX idx_leads_created ON leads (created_at DESC);

CREATE TRIGGER trg_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── 2. Analytics events ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event           TEXT NOT NULL,
    session_id      TEXT,
    page            TEXT,
    properties      JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_event   ON analytics_events (event);
CREATE INDEX idx_events_session ON analytics_events (session_id);
CREATE INDEX idx_events_created ON analytics_events (created_at DESC);

-- ── 3. Camp ownership (for claim flow) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS camp_ownership (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id         UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    contact_name    TEXT,
    role            TEXT,
    verified        BOOLEAN DEFAULT FALSE,
    stripe_customer_id  TEXT,
    plan            TEXT DEFAULT 'free'
                        CHECK (plan IN ('free', 'claimed', 'pro')),
    plan_started_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (camp_id)
);

CREATE INDEX idx_ownership_email ON camp_ownership (email);
CREATE INDEX idx_ownership_camp  ON camp_ownership (camp_id);
