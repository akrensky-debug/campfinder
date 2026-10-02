-- Shared plan and delegation: household members, tasks, reminders and an audit log.
-- Run after schema_accounts_kit.sql. Only the backend (service key) touches these
-- tables; RLS is on with no policies, so the anon and authenticated roles see nothing.

-- People who share a family's plan. The owner gets a row too (role 'owner') so they
-- can be assigned tasks and have their own calendar feed and reminders.
-- An invited member has status 'invited' and no user_id until they accept by signing in
-- with the invited address; they can already be assigned tasks.
CREATE TABLE IF NOT EXISTS family_members (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id          UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id            UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    email              TEXT NOT NULL,
    display_name       TEXT NOT NULL,
    role               TEXT NOT NULL CHECK (role IN ('owner', 'co_parent', 'caregiver', 'viewer')),
    status             TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited', 'active')),
    -- Info kit access is off unless the owner grants it to a co-parent.
    kit_access         BOOLEAN NOT NULL DEFAULT false,
    invite_token_hash  TEXT UNIQUE,          -- sha256 of the invite token; the token is never stored
    invite_expires_at  TIMESTAMPTZ,
    invited_by         UUID REFERENCES family_members(id) ON DELETE SET NULL,
    calendar_token     TEXT NOT NULL UNIQUE DEFAULT replace(gen_random_uuid()::text, '-', ''),
    reminder_pref      TEXT NOT NULL DEFAULT 'day_before' CHECK (reminder_pref IN ('daily', 'day_before', 'off')),
    weekly_summary     BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at        TIMESTAMPTZ,
    CONSTRAINT kit_access_co_parent_only CHECK (NOT kit_access OR role IN ('owner', 'co_parent'))
);
CREATE UNIQUE INDEX IF NOT EXISTS family_members_email_idx ON family_members (family_id, lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS family_members_user_idx ON family_members (family_id, user_id);
CREATE INDEX IF NOT EXISTS family_members_user_lookup_idx ON family_members (user_id);

-- Jobs in the plan: pickups, drop-offs, forms, payments, packing lists, deadlines.
CREATE TABLE IF NOT EXISTS family_tasks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id     UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('dropoff', 'pickup', 'form', 'payment', 'packing', 'deadline', 'other')),
    title         TEXT NOT NULL,
    notes         TEXT,
    child_name    TEXT,
    due_date      DATE NOT NULL,
    due_time      TIME,                       -- local time; null means any time that day
    assignee_id   UUID REFERENCES family_members(id) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'skipped')),
    event_id      UUID REFERENCES family_events(id) ON DELETE SET NULL,
    camp_id       UUID REFERENCES camps(id) ON DELETE SET NULL,
    checklist     JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{item, done}] for packing lists
    created_by    UUID REFERENCES family_members(id) ON DELETE SET NULL,
    completed_by  UUID REFERENCES family_members(id) ON DELETE SET NULL,
    completed_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS family_tasks_family_idx ON family_tasks (family_id, due_date);
CREATE INDEX IF NOT EXISTS family_tasks_assignee_idx ON family_tasks (assignee_id, due_date);

-- Who changed or completed what. Actor name is copied in so the entry survives removal.
-- Details hold ids, titles and field names, never kit data.
CREATE TABLE IF NOT EXISTS family_audit_log (
    id           BIGSERIAL PRIMARY KEY,
    family_id    UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    actor_id     UUID REFERENCES family_members(id) ON DELETE SET NULL,
    actor_name   TEXT NOT NULL,
    via          TEXT NOT NULL DEFAULT 'app' CHECK (via IN ('app', 'assistant', 'system')),
    action       TEXT NOT NULL,
    target_type  TEXT,
    target_id    TEXT,
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS family_audit_log_family_idx ON family_audit_log (family_id, created_at DESC);

-- One row per reminder email, so a re-run of the job never sends twice.
CREATE TABLE IF NOT EXISTS reminder_sends (
    id          BIGSERIAL PRIMARY KEY,
    member_id   UUID NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('digest', 'weekly')),
    period      DATE NOT NULL,
    task_count  INTEGER NOT NULL DEFAULT 0,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (member_id, kind, period)
);

ALTER TABLE family_members   ENABLE ROW LEVEL SECURITY;
ALTER TABLE family_tasks     ENABLE ROW LEVEL SECURITY;
ALTER TABLE family_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminder_sends   ENABLE ROW LEVEL SECURITY;
