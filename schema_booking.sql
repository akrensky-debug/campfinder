-- Registration day: when registration opens, what each camp's form asks for, what the
-- family has registered for (and paid), reminder settings, and the sandbox booking log.
-- Run after schema_accounts_kit.sql. Additive: no existing table is altered.
-- Only the backend (service key) touches these tables; RLS is on with no policies,
-- so the anon and authenticated keys can read or write nothing.

-- When registration opens (and closes) for a camp, or for one session of it.
-- Public facts about the camp, entered by our team, the camp, or an import.
CREATE TABLE IF NOT EXISTS registration_windows (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id      UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    session_id   UUID REFERENCES sessions(id) ON DELETE CASCADE,   -- null: the whole camp
    opens_at     TIMESTAMPTZ NOT NULL,
    closes_at    TIMESTAMPTZ,
    source_url   TEXT,
    verified     BOOLEAN NOT NULL DEFAULT false,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS registration_windows_camp_idx ON registration_windows (camp_id, opens_at);

-- What a camp's registration form asks for, mapped to info kit fields.
-- fields: [{"question": "Camper date of birth", "kit_field": "child.date_of_birth", "required": true}, ...]
-- kit_field is null for questions the kit can't answer (e.g. "How did you hear about us?").
CREATE TABLE IF NOT EXISTS registration_forms (
    camp_id      UUID PRIMARY KEY REFERENCES camps(id) ON DELETE CASCADE,
    fields       JSONB NOT NULL DEFAULT '[]'::jsonb,
    form_url     TEXT,
    platform     TEXT,                  -- e.g. campminder, ultracamp, pike13, custom, sandbox
    provider_refs JSONB NOT NULL DEFAULT '{}'::jsonb,  -- our session id -> the platform's id (booking prototype)
    source       TEXT NOT NULL DEFAULT 'team' CHECK (source IN ('team', 'camp', 'import')),
    verified_at  TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A camp or session the family is watching or has registered for.
-- The parent records what happened; CampFinder never registers or pays on its own.
CREATE TABLE IF NOT EXISTS family_registrations (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id            UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    camp_id              UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    session_id           UUID REFERENCES sessions(id) ON DELETE SET NULL,
    child_name           TEXT,
    status               TEXT NOT NULL DEFAULT 'watching'
                             CHECK (status IN ('watching', 'registered', 'waitlisted', 'cancelled')),
    payment_status       TEXT NOT NULL DEFAULT 'unpaid'
                             CHECK (payment_status IN ('unpaid', 'deposit', 'paid', 'refunded')),
    amount_paid          NUMERIC(10,2),
    paid_on              DATE,
    balance_due          NUMERIC(10,2),
    payment_due_date     DATE,
    forms_due_date       DATE,
    opens_at             TIMESTAMPTZ,       -- the family's own date when we don't have one
    confirmation_number  TEXT,
    notes                TEXT,
    remind               BOOLEAN NOT NULL DEFAULT true,
    event_ids            JSONB NOT NULL DEFAULT '{}'::jsonb,  -- family_events rows this created, by kind
    registered_at        TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS family_registrations_family_idx ON family_registrations (family_id, created_at);

-- How and when a family wants registration reminders. Email goes only to this address.
CREATE TABLE IF NOT EXISTS registration_reminder_prefs (
    family_id     UUID PRIMARY KEY REFERENCES families(id) ON DELETE CASCADE,
    email         TEXT,
    enabled       BOOLEAN NOT NULL DEFAULT true,
    opens_days    INTEGER[] NOT NULL DEFAULT '{7,1,0}',   -- days before registration opens
    deadline_days INTEGER[] NOT NULL DEFAULT '{3,0}',     -- days before payment and form deadlines
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per reminder sent, so a re-run never sends twice.
CREATE TABLE IF NOT EXISTS registration_reminder_sends (
    id               BIGSERIAL PRIMARY KEY,
    registration_id  UUID NOT NULL REFERENCES family_registrations(id) ON DELETE CASCADE,
    kind             TEXT NOT NULL,            -- opens | payment_due | forms_due
    due_on           DATE NOT NULL,
    days_before      INTEGER NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (registration_id, kind, due_on, days_before)
);

-- Sandbox booking prototype (feature flag BOOKING_PROVIDERS, test credentials only).
-- A quote carries no personal data; the consent record is what the parent saw and agreed to.
CREATE TABLE IF NOT EXISTS booking_attempts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id        UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    registration_id  UUID REFERENCES family_registrations(id) ON DELETE SET NULL,
    provider         TEXT NOT NULL,
    environment      TEXT NOT NULL DEFAULT 'sandbox' CHECK (environment = 'sandbox'),
    status           TEXT NOT NULL DEFAULT 'quoted'
                         CHECK (status IN ('quoted', 'confirmed', 'failed', 'expired', 'cancelled')),
    quote            JSONB NOT NULL,
    consent          JSONB,          -- {confirmed_by, confirmed_at, summary_shown, fields_shared}
    provider_ref     TEXT,
    error            TEXT,
    expires_at       TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS booking_attempts_family_idx ON booking_attempts (family_id, created_at);

ALTER TABLE registration_windows        ENABLE ROW LEVEL SECURITY;
ALTER TABLE registration_forms          ENABLE ROW LEVEL SECURITY;
ALTER TABLE family_registrations        ENABLE ROW LEVEL SECURITY;
ALTER TABLE registration_reminder_prefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE registration_reminder_sends ENABLE ROW LEVEL SECURITY;
ALTER TABLE booking_attempts            ENABLE ROW LEVEL SECURITY;
