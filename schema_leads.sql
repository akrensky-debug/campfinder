-- CampFinder Phase 2: Leads + Camp Submissions

CREATE TABLE IF NOT EXISTS leads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               TEXT NOT NULL,
    first_name          TEXT,
    search_location     TEXT,
    search_age          INTEGER,
    search_camp_type    TEXT,
    search_categories   TEXT[],
    matched_camp_ids    UUID[],
    source              TEXT DEFAULT 'search_gate',  -- search_gate, camp_detail, operator_form
    status              TEXT DEFAULT 'new'
                            CHECK (status IN ('new', 'emailed', 'contacted', 'converted')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leads_email   ON leads (email);
CREATE INDEX IF NOT EXISTS idx_leads_status  ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads (created_at DESC);

CREATE TABLE IF NOT EXISTS camp_submissions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    city                TEXT NOT NULL,
    state               TEXT NOT NULL,
    zip                 TEXT,
    camp_type           TEXT,
    website_url         TEXT,
    email               TEXT NOT NULL,
    phone               TEXT,
    contact_name        TEXT,
    contact_role        TEXT,
    age_min             INTEGER,
    age_max             INTEGER,
    description         TEXT,
    primary_categories  TEXT[],
    notes               TEXT,
    status              TEXT DEFAULT 'pending'
                            CHECK (status IN ('pending', 'reviewed', 'imported', 'rejected')),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_submissions_status ON camp_submissions (status);
CREATE INDEX IF NOT EXISTS idx_submissions_created ON camp_submissions (created_at DESC);
