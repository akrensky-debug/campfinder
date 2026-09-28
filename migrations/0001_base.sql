-- 0001: base schema for the camps-as-the-wedge rebuild.
--
-- Replaces schema.sql, schema_leads.sql and schema_phase2.sql. Applied by
-- `python -m campfinder.migrate`. Every statement must be safe to run once,
-- inside one transaction, on an empty database.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Camps and their public listing data
-- ============================================================
CREATE TABLE camps (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                    TEXT NOT NULL UNIQUE,
    name                    TEXT NOT NULL,
    operator_name           TEXT,
    website_url             TEXT,
    registration_url        TEXT,
    email                   CITEXT,
    phone                   TEXT,
    street_address          TEXT,
    city                    TEXT NOT NULL,
    state                   TEXT NOT NULL CHECK (char_length(state) = 2),
    zip                     TEXT NOT NULL,
    location                GEOGRAPHY(Point, 4326) NOT NULL,
    region                  TEXT,
    camp_type               TEXT NOT NULL CHECK (camp_type IN ('day', 'sleepaway', 'specialty')),
    primary_categories      TEXT[] NOT NULL DEFAULT '{}',
    secondary_categories    TEXT[] NOT NULL DEFAULT '{}',
    gender_policy           TEXT,
    age_min                 INTEGER CHECK (age_min BETWEEN 0 AND 21),
    age_max                 INTEGER CHECK (age_max BETWEEN 0 AND 21),
    grade_min               INTEGER,
    grade_max               INTEGER,
    description_short       TEXT,
    description_full        TEXT,
    activities              TEXT[] NOT NULL DEFAULT '{}',
    indoor_outdoor          TEXT,
    travel_field_trips      BOOLEAN NOT NULL DEFAULT FALSE,
    religious_affiliation   TEXT,
    price_min               NUMERIC(10,2),
    price_max               NUMERIC(10,2),
    price_per_week          NUMERIC(10,2),
    deposit_required        BOOLEAN,
    financial_aid           BOOLEAN NOT NULL DEFAULT FALSE,
    extended_care           BOOLEAN NOT NULL DEFAULT FALSE,
    transportation          BOOLEAN NOT NULL DEFAULT FALSE,
    meals_included          BOOLEAN NOT NULL DEFAULT FALSE,
    refund_policy_summary   TEXT,
    special_needs_notes     TEXT,
    medical_support_notes   TEXT,
    swim_waterfront_notes   TEXT,
    aca_accredited          BOOLEAN,
    aca_source_url          TEXT,
    verification_status     TEXT NOT NULL DEFAULT 'unverified'
                                CHECK (verification_status IN ('unverified', 'claimed', 'camp_verified', 'team_verified')),
    last_reviewed_at        TIMESTAMPTZ,
    sources                 TEXT[] NOT NULL DEFAULT '{}',
    hero_image_url          TEXT,
    faq                     JSONB,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    season_year             INTEGER,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (age_min IS NULL OR age_max IS NULL OR age_min <= age_max)
);

CREATE INDEX idx_camps_location   ON camps USING GIST (location);
CREATE INDEX idx_camps_active     ON camps (is_active) WHERE is_active;
CREATE INDEX idx_camps_state_city ON camps (state, city);
CREATE INDEX idx_camps_camp_type  ON camps (camp_type);
CREATE INDEX idx_camps_categories ON camps USING GIN (primary_categories);

CREATE TRIGGER trg_camps_updated_at
    BEFORE UPDATE ON camps FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- A session is one bookable run of a camp: a week, two weeks, the season.
CREATE TABLE sessions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id                 UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    name                    TEXT,
    start_date              DATE NOT NULL,
    end_date                DATE NOT NULL,
    age_min                 INTEGER,
    age_max                 INTEGER,
    price                   NUMERIC(10,2),
    full_season             BOOLEAN NOT NULL DEFAULT FALSE,
    availability            TEXT NOT NULL DEFAULT 'unknown'
                                CHECK (availability IN ('open', 'waitlist', 'full', 'unknown')),
    spots_total             INTEGER CHECK (spots_total >= 0),
    spots_available         INTEGER CHECK (spots_available >= 0),
    registration_opens_at   TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_date >= start_date),
    CHECK (spots_available IS NULL OR spots_total IS NULL OR spots_available <= spots_total)
);

CREATE INDEX idx_sessions_camp  ON sessions (camp_id, start_date);
CREATE INDEX idx_sessions_dates ON sessions (start_date, end_date);
CREATE INDEX idx_sessions_reg_opens ON sessions (registration_opens_at) WHERE registration_opens_at IS NOT NULL;

CREATE TRIGGER trg_sessions_updated_at
    BEFORE UPDATE ON sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Where each fact on a listing came from, and when it was last checked.
CREATE TABLE field_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id         UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    field_name      TEXT NOT NULL,
    source_type     TEXT NOT NULL
                        CHECK (source_type IN ('public_web', 'camp_submitted', 'camp_verified', 'team_verified', 'parent_reported')),
    source_url      TEXT,
    last_verified   TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (camp_id, field_name)
);

-- Every change to a listing, who made it and from what message. This is the
-- audit trail behind "the owner texted 'week 3 is full' and the listing changed".
CREATE TABLE listing_changes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id         UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    session_id      UUID REFERENCES sessions(id) ON DELETE SET NULL,
    changed_by      TEXT NOT NULL
                        CHECK (changed_by IN ('owner_email', 'owner_sms', 'owner_web', 'team', 'ingest', 'system')),
    actor           TEXT,
    field_name      TEXT NOT NULL,
    old_value       JSONB,
    new_value       JSONB,
    raw_message     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_listing_changes_camp ON listing_changes (camp_id, created_at DESC);

-- ============================================================
-- Camp owners
-- ============================================================
CREATE TABLE camp_contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id         UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    email           CITEXT NOT NULL,
    phone           TEXT,
    name            TEXT,
    role            TEXT,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    notify_by       TEXT NOT NULL DEFAULT 'email' CHECK (notify_by IN ('email', 'sms', 'both')),
    verified_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (camp_id, email)
);

CREATE INDEX idx_camp_contacts_email ON camp_contacts (email);

-- An owner proving they speak for a camp. The token is stored hashed and
-- expires; the plain token only ever exists in the email we send.
CREATE TABLE claim_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id         UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    email           CITEXT NOT NULL,
    name            TEXT,
    role            TEXT,
    token_hash      TEXT NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'verified', 'expired', 'rejected')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at     TIMESTAMPTZ
);

CREATE INDEX idx_claim_requests_camp ON claim_requests (camp_id, created_at DESC);

-- A camp not yet listed, submitted by its owner. Reviewed by hand before import.
CREATE TABLE camp_submissions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    city                TEXT NOT NULL,
    state               TEXT NOT NULL CHECK (char_length(state) = 2),
    zip                 TEXT,
    camp_type           TEXT CHECK (camp_type IN ('day', 'sleepaway', 'specialty')),
    website_url         TEXT,
    email               CITEXT NOT NULL,
    phone               TEXT,
    contact_name        TEXT,
    contact_role        TEXT,
    age_min             INTEGER,
    age_max             INTEGER,
    description         TEXT,
    primary_categories  TEXT[] NOT NULL DEFAULT '{}',
    notes               TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'reviewed', 'imported', 'rejected')),
    imported_camp_id    UUID REFERENCES camps(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_camp_submissions_status ON camp_submissions (status, created_at DESC);

-- ============================================================
-- Families (the trust rules apply from here down)
-- ============================================================
-- Parents own this data. Every row here can be exported and deleted by the
-- parent through the API. Children never have accounts; auth_subject is the
-- parent's identity from the auth provider.
CREATE TABLE families (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_subject            TEXT NOT NULL UNIQUE,
    email                   CITEXT NOT NULL UNIQUE,
    first_name              TEXT,
    zip                     TEXT,
    home_location           GEOGRAPHY(Point, 4326),
    privacy_policy_version  TEXT,
    consented_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_families_updated_at
    BEFORE UPDATE ON families FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The minimum a camp needs: a first name, an age, and interests for matching.
CREATE TABLE children (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id       UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    first_name      TEXT NOT NULL,
    birth_year      INTEGER NOT NULL CHECK (birth_year BETWEEN 2000 AND 2030),
    birth_month     INTEGER CHECK (birth_month BETWEEN 1 AND 12),
    interests       TEXT[] NOT NULL DEFAULT '{}',
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_children_family ON children (family_id);

CREATE TRIGGER trg_children_updated_at
    BEFORE UPDATE ON children FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Kept apart from children on purpose. Read only when a camp has confirmed a
-- spot for this child, and never returned in listings, search or analytics.
CREATE TABLE child_medical (
    child_id                    UUID PRIMARY KEY REFERENCES children(id) ON DELETE CASCADE,
    allergies                   TEXT,
    medications                 TEXT,
    medical_notes               TEXT,
    emergency_contact_name      TEXT,
    emergency_contact_phone     TEXT,
    pickup_authorized           TEXT[] NOT NULL DEFAULT '{}',
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_child_medical_updated_at
    BEFORE UPDATE ON child_medical FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- The transaction: a parent asks for a spot, the camp answers
-- ============================================================
CREATE TABLE spot_requests (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id               UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    child_id                UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    camp_id                 UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    session_id              UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    status                  TEXT NOT NULL DEFAULT 'requested'
                                CHECK (status IN ('requested', 'confirmed', 'declined', 'cancelled', 'expired')),
    parent_note             TEXT,
    camp_note               TEXT,
    response_token_hash     TEXT UNIQUE,
    response_expires_at     TIMESTAMPTZ,
    responded_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (child_id, session_id)
);

CREATE INDEX idx_spot_requests_family ON spot_requests (family_id, created_at DESC);
CREATE INDEX idx_spot_requests_camp   ON spot_requests (camp_id, status, created_at DESC);

CREATE TRIGGER trg_spot_requests_updated_at
    BEFORE UPDATE ON spot_requests FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- "Tell me when registration opens." Email only; no account needed.
CREATE TABLE registration_alerts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                   CITEXT NOT NULL,
    camp_id                 UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    family_id               UUID REFERENCES families(id) ON DELETE SET NULL,
    status                  TEXT NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'sent', 'unsubscribed')),
    unsubscribe_token_hash  TEXT NOT NULL UNIQUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at                 TIMESTAMPTZ,
    UNIQUE (email, camp_id)
);

CREATE INDEX idx_registration_alerts_camp ON registration_alerts (camp_id) WHERE status = 'active';

-- ============================================================
-- Product analytics. No identifying data goes in here, by rule and by code.
-- ============================================================
CREATE TABLE analytics_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event           TEXT NOT NULL,
    session_id      TEXT,
    page            TEXT,
    properties      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analytics_events_event ON analytics_events (event, created_at DESC);
