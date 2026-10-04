-- Parent accounts, private calendar links, and the encrypted family info kit.
-- Requires Supabase Auth (auth.users).

ALTER TABLE families
    ADD COLUMN IF NOT EXISTS owner_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS calendar_token TEXT UNIQUE
        DEFAULT replace(gen_random_uuid()::text, '-', '');
UPDATE families SET calendar_token = replace(gen_random_uuid()::text, '-', '') WHERE calendar_token IS NULL;

-- One encrypted blob per family (AES-GCM, family id bound as associated data).
-- The server holds the key (KIT_ENCRYPTION_KEY); the database never sees plaintext.
CREATE TABLE IF NOT EXISTS family_kits (
    family_id   UUID PRIMARY KEY REFERENCES families(id) ON DELETE CASCADE,
    ciphertext  TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A package shared from the kit: chosen fields, chosen kids, an expiring link.
CREATE TABLE IF NOT EXISTS kit_shares (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id         UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    recipient         TEXT NOT NULL,
    camp_id           UUID REFERENCES camps(id) ON DELETE SET NULL,
    children          TEXT[] NOT NULL DEFAULT '{}',
    household_fields  TEXT[] NOT NULL DEFAULT '{}',
    child_fields      TEXT[] NOT NULL DEFAULT '{}',
    token_hash        TEXT NOT NULL UNIQUE,   -- sha256 of the link token; the token is never stored
    expires_at        TIMESTAMPTZ NOT NULL,
    revoked_at        TIMESTAMPTZ,
    open_count        INTEGER NOT NULL DEFAULT 0,
    last_opened_at    TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kit_shares_family_idx ON kit_shares (family_id, created_at);

CREATE TABLE IF NOT EXISTS kit_share_events (
    id          BIGSERIAL PRIMARY KEY,
    share_id    UUID NOT NULL REFERENCES kit_shares(id) ON DELETE CASCADE,
    event       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE family_kits      ENABLE ROW LEVEL SECURITY;
ALTER TABLE kit_shares       ENABLE ROW LEVEL SECURITY;
ALTER TABLE kit_share_events ENABLE ROW LEVEL SECURITY;
