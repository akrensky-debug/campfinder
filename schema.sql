-- CampFinder Database Schema
-- Run against Supabase Postgres instance

-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- CAMPS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS camps (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL,
    operator_name           TEXT,
    website_url             TEXT,
    registration_url        TEXT,
    email                   TEXT,
    phone                   TEXT,
    street_address          TEXT,
    city                    TEXT NOT NULL,
    state                   TEXT NOT NULL CHECK (char_length(state) = 2),
    zip                     TEXT NOT NULL,
    location                GEOGRAPHY(Point, 4326) NOT NULL,
    region                  TEXT,
    camp_type               TEXT NOT NULL CHECK (camp_type IN ('day', 'sleepaway', 'specialty')),
    is_day_camp             BOOLEAN DEFAULT FALSE,
    is_sleepaway            BOOLEAN DEFAULT FALSE,
    is_specialty            BOOLEAN DEFAULT FALSE,
    primary_categories      TEXT[],
    secondary_categories    TEXT[],
    gender_policy           TEXT,
    age_min                 INTEGER,
    age_max                 INTEGER,
    grade_min               INTEGER,
    grade_max               INTEGER,
    description_short       TEXT,
    description_full        TEXT,
    activities              TEXT[],
    indoor_outdoor          TEXT,
    sports_focus            BOOLEAN DEFAULT FALSE,
    arts_focus              BOOLEAN DEFAULT FALSE,
    stem_focus              BOOLEAN DEFAULT FALSE,
    nature_focus            BOOLEAN DEFAULT FALSE,
    travel_field_trips      BOOLEAN DEFAULT FALSE,
    religious_affiliation   TEXT,
    price_min               NUMERIC(10,2),
    price_max               NUMERIC(10,2),
    price_per_week          NUMERIC(10,2),
    price_per               TEXT,
    deposit_required        BOOLEAN,
    financial_aid           BOOLEAN DEFAULT FALSE,
    extended_care           BOOLEAN DEFAULT FALSE,
    transportation          BOOLEAN DEFAULT FALSE,
    meals_included          BOOLEAN DEFAULT FALSE,
    refund_policy_summary   TEXT,
    special_needs_notes     TEXT,
    medical_support_notes   TEXT,
    swim_waterfront_notes   TEXT,
    aca_accredited          BOOLEAN,
    aca_source_url          TEXT,
    verification_status     TEXT NOT NULL DEFAULT 'unverified'
                                CHECK (verification_status IN ('unverified', 'claimed', 'camp_verified', 'team_verified')),
    last_reviewed_date      TIMESTAMPTZ,
    last_updated_date       TIMESTAMPTZ DEFAULT NOW(),
    sources                 TEXT[],
    parent_review_count     INTEGER DEFAULT 0,
    parent_review_avg       NUMERIC(3,2),
    hero_image_url          TEXT,
    gallery_image_urls      TEXT[],
    faq                     JSONB,
    is_active               BOOLEAN DEFAULT TRUE,
    season_year             INTEGER,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- SESSIONS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id         UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    name            TEXT,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    length_days     INTEGER,
    length_weeks    NUMERIC(3,1),
    price           NUMERIC(10,2),
    full_season     BOOLEAN DEFAULT FALSE,
    availability    TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (availability IN ('open', 'waitlist', 'full', 'unknown')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- FIELD_SOURCES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS field_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id         UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    field_name      TEXT NOT NULL,
    source_type     TEXT NOT NULL
                        CHECK (source_type IN ('public_web', 'camp_submitted', 'camp_verified', 'team_verified', 'parent_reported')),
    source_url      TEXT,
    last_verified   TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- CLAIM_REQUESTS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS claim_requests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id             UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    email               TEXT NOT NULL,
    name                TEXT,
    role                TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'verified', 'rejected')),
    verification_token  TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    verified_at         TIMESTAMPTZ
);

-- ============================================================
-- INDEXES
-- ============================================================

-- camps indexes
CREATE INDEX IF NOT EXISTS idx_camps_location ON camps USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_camps_state ON camps (state);
CREATE INDEX IF NOT EXISTS idx_camps_camp_type ON camps (camp_type);
CREATE INDEX IF NOT EXISTS idx_camps_age_min ON camps (age_min);
CREATE INDEX IF NOT EXISTS idx_camps_age_max ON camps (age_max);
CREATE INDEX IF NOT EXISTS idx_camps_verification_status ON camps (verification_status);
CREATE INDEX IF NOT EXISTS idx_camps_is_active ON camps (is_active);
CREATE INDEX IF NOT EXISTS idx_camps_primary_categories ON camps USING GIN (primary_categories);
CREATE INDEX IF NOT EXISTS idx_camps_zip ON camps (zip);
CREATE INDEX IF NOT EXISTS idx_camps_city ON camps (city);

-- sessions indexes
CREATE INDEX IF NOT EXISTS idx_sessions_camp_id ON sessions (camp_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start_date ON sessions (start_date);
CREATE INDEX IF NOT EXISTS idx_sessions_end_date ON sessions (end_date);

-- field_sources unique index
CREATE UNIQUE INDEX IF NOT EXISTS idx_field_sources_camp_field ON field_sources (camp_id, field_name);

-- ============================================================
-- UPDATED_AT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_camps_updated_at ON camps;
CREATE TRIGGER trg_camps_updated_at
    BEFORE UPDATE ON camps
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_sessions_updated_at ON sessions;
CREATE TRIGGER trg_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
