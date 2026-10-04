-- Camp submissions from operators. (The leads table is created in 0003, in the shape the code uses.)

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

ALTER TABLE camp_submissions ENABLE ROW LEVEL SECURITY;
