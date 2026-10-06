-- Listing updates by email (ROADMAP Phase 2): an owner writes "Week 3 is full", the listing
-- changes, and the owner gets back "here is what changed, reply if wrong".
--
-- One row per email received from a camp owner, with what the reader proposed and what was
-- changed. Every change it makes is also in listing_changes with the message behind it.
CREATE TABLE IF NOT EXISTS owner_messages (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id   TEXT UNIQUE,               -- the email's Message-ID: a redelivery is handled once
    from_email   TEXT NOT NULL,
    sender_verified BOOLEAN NOT NULL DEFAULT false,  -- the mail provider passed SPF/DKIM
    subject      TEXT,
    body         TEXT NOT NULL,
    camp_id      UUID REFERENCES camps(id) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT 'received'
                     CHECK (status IN ('received', 'proposed', 'applied', 'needs_person', 'rejected')),
    reason       TEXT,                      -- why a person has to look, or why it was rejected
    proposal     JSONB,                     -- what the reader proposed
    applied      JSONB,                     -- what was changed
    handled_by   TEXT,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    handled_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS owner_messages_status_idx ON owner_messages (status, received_at DESC);

ALTER TABLE owner_messages ENABLE ROW LEVEL SECURITY;
