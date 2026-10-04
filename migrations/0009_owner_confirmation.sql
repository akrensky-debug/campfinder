-- Owner confirmation: "here is your listing, reply if anything is wrong".
-- Re-runnable (IF NOT EXISTS throughout). Only the backend touches these tables.

-- Who to write to at each camp. A contact becomes verified when they answer a
-- confirmation link, because the link only reached their inbox.
CREATE TABLE IF NOT EXISTS camp_contacts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id      UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    email        TEXT NOT NULL,
    name         TEXT,
    role         TEXT,
    is_primary   BOOLEAN NOT NULL DEFAULT false,
    verified_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS camp_contacts_email_idx ON camp_contacts (camp_id, lower(email));

-- A dated record of every change to a listing and what caused it (company rule 13).
CREATE TABLE IF NOT EXISTS listing_changes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id      UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    session_id   UUID REFERENCES sessions(id) ON DELETE SET NULL,
    changed_by   TEXT NOT NULL
                     CHECK (changed_by IN ('owner_email', 'owner_web', 'team', 'ingest', 'system')),
    actor        TEXT,
    field_name   TEXT NOT NULL,
    old_value    JSONB,
    new_value    JSONB,
    raw_message  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS listing_changes_camp_idx ON listing_changes (camp_id, created_at DESC);

-- One row per confirmation email. The snapshot is exactly what the email showed, so
-- "looks right" vouches for those facts and nothing that changed since.
CREATE TABLE IF NOT EXISTS listing_confirmations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id       UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    email         TEXT NOT NULL,
    token_hash    TEXT NOT NULL UNIQUE,     -- sha256 of the link token; the token is never stored
    snapshot      JSONB NOT NULL,
    status        TEXT NOT NULL DEFAULT 'sent'
                      CHECK (status IN ('sent', 'confirmed', 'removed', 'superseded')),
    sent_by       TEXT NOT NULL,
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    responded_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS listing_confirmations_camp_idx ON listing_confirmations (camp_id, sent_at DESC);

ALTER TABLE camp_contacts          ENABLE ROW LEVEL SECURITY;
ALTER TABLE listing_changes        ENABLE ROW LEVEL SECURITY;
ALTER TABLE listing_confirmations  ENABLE ROW LEVEL SECURITY;
