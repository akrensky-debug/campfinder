-- Activity API: partner keys, usage, and anonymous demand signals.

CREATE TABLE IF NOT EXISTS api_clients (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   TEXT NOT NULL,
    contact_email          TEXT,
    key_prefix             TEXT NOT NULL,          -- first characters, for support lookups
    key_hash               TEXT NOT NULL UNIQUE,   -- sha256 of the key; the key itself is never stored
    rate_limit_per_minute  INTEGER NOT NULL DEFAULT 120,
    active                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_usage (
    id          BIGSERIAL PRIMARY KEY,
    client_id   UUID NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
    endpoint    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS api_usage_client_idx ON api_usage (client_id, created_at);

-- What families asked for, reported by partners and our own agent. No personal data.
CREATE TABLE IF NOT EXISTS activity_demand (
    id                  BIGSERIAL PRIMARY KEY,
    client_id           UUID REFERENCES api_clients(id) ON DELETE SET NULL,
    location            TEXT NOT NULL,
    ages                INTEGER[] NOT NULL DEFAULT '{}',
    kinds               TEXT[] NOT NULL DEFAULT '{}',
    categories          TEXT[] NOT NULL DEFAULT '{}',
    weeks               DATE[] NOT NULL DEFAULT '{}',
    max_price_per_week  NUMERIC(10,2),
    needs               TEXT[] NOT NULL DEFAULT '{}',
    results_shown       INTEGER,
    satisfied           BOOLEAN,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS activity_demand_location_idx ON activity_demand (location, created_at);

ALTER TABLE api_clients     ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_usage       ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_demand ENABLE ROW LEVEL SECURITY;
