-- "Tell me when registration opens": a parent leaves an email on a camp's page, no account.
-- Run after 0010_booking.sql. Additive: no existing table is altered.
-- Least data: an email address and which camp (or session). No name, no child, no family.
-- Nothing is sent until the address is confirmed (double opt-in), and every email carries
-- the link that stops it. Only the backend (service key) touches these tables.

CREATE TABLE IF NOT EXISTS registration_alerts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camp_id          UUID NOT NULL REFERENCES camps(id) ON DELETE CASCADE,
    session_id       UUID REFERENCES sessions(id) ON DELETE CASCADE,   -- null: any session
    email            TEXT NOT NULL,                                     -- stored lowercased
    -- The secret in the confirm and stop links. It can only confirm or stop this one alert,
    -- and the job needs it to write the stop link into each email, so it is kept as is.
    token            TEXT NOT NULL UNIQUE,
    confirm_sent_at  TIMESTAMPTZ,
    confirmed_at     TIMESTAMPTZ,
    unsubscribed_at  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- One alert per address per camp and session.
CREATE UNIQUE INDEX IF NOT EXISTS registration_alerts_unique_idx
    ON registration_alerts (camp_id, COALESCE(session_id, '00000000-0000-0000-0000-000000000000'::uuid), email);
CREATE INDEX IF NOT EXISTS registration_alerts_email_idx ON registration_alerts (email, created_at);

-- One row per alert email sent, keyed on the opening date it was about, so a re-run never
-- sends twice and a changed date is news again.
CREATE TABLE IF NOT EXISTS registration_alert_sends (
    id          BIGSERIAL PRIMARY KEY,
    alert_id    UUID NOT NULL REFERENCES registration_alerts(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('announced', 'opens_soon', 'open_now')),
    opens_at    TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (alert_id, kind, opens_at)
);

ALTER TABLE registration_alerts      ENABLE ROW LEVEL SECURITY;
ALTER TABLE registration_alert_sends ENABLE ROW LEVEL SECURITY;
