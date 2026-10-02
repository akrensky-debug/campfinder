-- Year-round programs: classes, lessons, leagues, after-school programs and events.
-- Additive: camps and sessions are untouched. Run after schema.sql and schema_family.sql.
--
--   programs           what a provider offers ("Youth Swim Lessons"), its ages, levels, policies
--   program_offerings  one scheduled run of it: where, which term, which weekdays and times
--                      (an iCal RRULE plus exception dates), enrollment window, availability
--   program_prices     full-term, per-class, drop-in, trial, fee and membership prices
--   program_field_sources  where each fact came from and when, per program or per offering
--
-- family_events gains optional columns so the family calendar can hold recurring,
-- timed commitments (classes, practices, pickups) and enrollment reminders.
--
-- Function bodies are single-quoted (not $$) so the Supabase MCP can apply this file.

CREATE TABLE IF NOT EXISTS programs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                 TEXT NOT NULL UNIQUE,         -- stable key for importers
    kind                 TEXT NOT NULL CHECK (kind IN ('class', 'lesson', 'league', 'after_school', 'event')),
    name                 TEXT NOT NULL,
    description          TEXT,
    categories           TEXT[] NOT NULL DEFAULT '{}',
    activities           TEXT[] NOT NULL DEFAULT '{}',
    provider_name        TEXT,
    provider_website     TEXT,
    provider_phone       TEXT,
    provider_email       TEXT,
    age_min              INTEGER,
    age_max              INTEGER,
    grade_min            INTEGER,
    grade_max            INTEGER,
    skill_levels         TEXT[] NOT NULL DEFAULT '{}',
    trial_available      BOOLEAN,
    trial_notes          TEXT,
    membership_required  BOOLEAN,
    financial_aid        BOOLEAN,
    registration_url     TEXT,
    -- Default location; an offering may override it.
    location_name        TEXT,
    street_address       TEXT,
    city                 TEXT NOT NULL,
    state                TEXT NOT NULL CHECK (char_length(state) = 2),
    zip                  TEXT,
    latitude             DOUBLE PRECISION,
    longitude            DOUBLE PRECISION,
    geo_precision        TEXT CHECK (geo_precision IN ('address', 'city')),
    verification_status  TEXT NOT NULL DEFAULT 'unverified'
                             CHECK (verification_status IN ('unverified', 'claimed', 'provider_verified', 'team_verified')),
    source_dataset       TEXT,                         -- which curated import it came from
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    last_updated_date    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS programs_kind_idx       ON programs (kind) WHERE is_active;
CREATE INDEX IF NOT EXISTS programs_city_idx       ON programs (state, city);
CREATE INDEX IF NOT EXISTS programs_categories_idx ON programs USING GIN (categories);

CREATE TABLE IF NOT EXISTS program_offerings (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id         UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    external_key       TEXT NOT NULL,                  -- stable within a program, for importers
    name               TEXT,
    term_name          TEXT,                           -- 'Fall Session 1', 'Spring 2027 season'
    skill_level        TEXT,
    age_min            INTEGER,
    age_max            INTEGER,
    location_name      TEXT,
    street_address     TEXT,
    city               TEXT,
    state              TEXT CHECK (state IS NULL OR char_length(state) = 2),
    zip                TEXT,
    latitude           DOUBLE PRECISION,
    longitude          DOUBLE PRECISION,
    start_date         DATE,                           -- first meeting
    end_date           DATE,                           -- last meeting, inclusive
    start_time         TIME,                           -- local wall-clock time
    end_time           TIME,
    timezone           TEXT NOT NULL DEFAULT 'America/New_York',
    rrule              TEXT,                           -- RFC 5545, e.g. 'FREQ=WEEKLY;BYDAY=TU'
    exdates            DATE[] NOT NULL DEFAULT '{}',   -- no-class dates (holidays, breaks)
    class_count        INTEGER,
    enrollment_opens   DATE,
    enrollment_closes  DATE,
    availability       TEXT NOT NULL DEFAULT 'unknown'
                           CHECK (availability IN ('open', 'limited', 'waitlist', 'full', 'unknown')),
    drop_in_allowed    BOOLEAN,
    notes              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id, external_key),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);
CREATE INDEX IF NOT EXISTS program_offerings_program_idx ON program_offerings (program_id);
CREATE INDEX IF NOT EXISTS program_offerings_dates_idx   ON program_offerings (start_date, end_date);

CREATE TABLE IF NOT EXISTS program_prices (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id   UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    offering_id  UUID REFERENCES program_offerings(id) ON DELETE CASCADE,  -- NULL: applies to the whole program
    price_type   TEXT NOT NULL CHECK (price_type IN
                     ('full_term', 'per_class', 'drop_in', 'trial', 'registration_fee', 'membership', 'monthly')),
    amount       NUMERIC(10,2) NOT NULL CHECK (amount >= 0),
    currency     TEXT NOT NULL DEFAULT 'USD',
    audience     TEXT,                                -- 'member', 'non-member', 'resident', ...
    covers       TEXT,                                -- '8 classes', 'per month'
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS program_prices_program_idx  ON program_prices (program_id);
CREATE INDEX IF NOT EXISTS program_prices_offering_idx ON program_prices (offering_id);

CREATE TABLE IF NOT EXISTS program_field_sources (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id    UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    offering_id   UUID REFERENCES program_offerings(id) ON DELETE CASCADE,
    field_name    TEXT NOT NULL,                      -- e.g. 'start_time', 'prices.full_term.member'
    source_type   TEXT NOT NULL CHECK (source_type IN
                      ('public_web', 'provider_submitted', 'provider_verified', 'team_verified', 'parent_reported')),
    source_url    TEXT,
    retrieved_on  DATE,
    last_verified TIMESTAMPTZ,
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS program_field_sources_uniq ON program_field_sources
    (program_id, COALESCE(offering_id, '00000000-0000-0000-0000-000000000000'::uuid), field_name);

DROP TRIGGER IF EXISTS trg_programs_updated_at ON programs;
CREATE TRIGGER trg_programs_updated_at
    BEFORE UPDATE ON programs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_program_offerings_updated_at ON program_offerings;
CREATE TRIGGER trg_program_offerings_updated_at
    BEFORE UPDATE ON program_offerings FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Recurring and timed entries on the family calendar. All columns are optional, so
-- existing all-day camp events keep working unchanged. start_date/end_date remain the
-- first and last day an entry can occur.
ALTER TABLE family_events
    ADD COLUMN IF NOT EXISTS kind         TEXT CHECK (kind IS NULL OR kind IN ('camp', 'activity', 'commitment', 'reminder')),
    ADD COLUMN IF NOT EXISTS start_time   TIME,
    ADD COLUMN IF NOT EXISTS end_time     TIME,
    ADD COLUMN IF NOT EXISTS timezone     TEXT,
    ADD COLUMN IF NOT EXISTS rrule        TEXT,
    ADD COLUMN IF NOT EXISTS exdates      DATE[],
    ADD COLUMN IF NOT EXISTS location     TEXT,
    ADD COLUMN IF NOT EXISTS program_id   UUID REFERENCES programs(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS offering_id  UUID REFERENCES program_offerings(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS alarm_minutes_before INTEGER;

-- Demand signals for recurring activities: which days and hours families wanted.
ALTER TABLE activity_demand
    ADD COLUMN IF NOT EXISTS days_of_week   TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS earliest_start TEXT,
    ADD COLUMN IF NOT EXISTS latest_end     TEXT;

-- Only the backend (service key) reads and writes these tables.
ALTER TABLE programs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE program_offerings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE program_prices        ENABLE ROW LEVEL SECURITY;
ALTER TABLE program_field_sources ENABLE ROW LEVEL SECURITY;
