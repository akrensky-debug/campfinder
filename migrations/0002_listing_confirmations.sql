-- 0002: owner confirmation by email.
--
-- "Here is your listing, reply if anything is wrong." Each row is one email
-- sent to an owner. The snapshot is exactly what that email showed, so a click
-- on "looks right" confirms those facts and nothing that changed since.

CREATE TABLE listing_confirmations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id         UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    email           CITEXT NOT NULL,
    token_hash      TEXT NOT NULL UNIQUE,
    snapshot        JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'sent'
                        CHECK (status IN ('sent', 'confirmed', 'removed', 'superseded')),
    sent_by         TEXT NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    responded_at    TIMESTAMPTZ
);

CREATE INDEX idx_listing_confirmations_camp ON listing_confirmations (camp_id, sent_at DESC);
