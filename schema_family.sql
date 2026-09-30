-- Family layer: the household profile, its shared calendar, and agent conversations.
-- A family is identified by an unguessable UUID the browser keeps in localStorage.
-- There is no login yet, so treat the id as a bearer secret.

CREATE TABLE IF NOT EXISTS families (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Free-form household profile the agent maintains:
    -- { home_location, kids: [{name, age, interests, notes}], summer_start, summer_end,
    --   weekly_budget, needs: [..], notes }
    profile     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS family_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id   UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,          -- inclusive
    child_name  TEXT,
    camp_id     UUID REFERENCES camps(id) ON DELETE SET NULL,
    session_id  UUID REFERENCES sessions(id) ON DELETE SET NULL,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS family_events_family_idx ON family_events (family_id, start_date);

CREATE TABLE IF NOT EXISTS agent_conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id   UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    -- Full Messages API history (content blocks), appended to on every turn.
    messages    JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_conversations_family_idx ON agent_conversations (family_id);

-- Only the backend (service key) touches these tables.
ALTER TABLE families            ENABLE ROW LEVEL SECURITY;
ALTER TABLE family_events       ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;
