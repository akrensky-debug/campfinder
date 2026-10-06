-- Phase 1 removals, the database half: we don't sell parent contacts and there is no paid
-- Pro plan (docs/ROADMAP.md Phase 1; PRODUCT trust rules 2 and 5). The code went in #17.
-- Both tables were empty on live when this was written (5 October 2026), so nothing is lost.
-- Safe to re-run.

DROP TABLE IF EXISTS leads;

-- camp_ownership keeps the claim flow ('free' until claimed, then 'claimed'); the Stripe
-- columns and the 'pro' plan go.
UPDATE camp_ownership SET plan = 'claimed' WHERE plan = 'pro';
ALTER TABLE camp_ownership DROP COLUMN IF EXISTS stripe_customer_id;
ALTER TABLE camp_ownership DROP COLUMN IF EXISTS plan_started_at;
ALTER TABLE camp_ownership DROP CONSTRAINT IF EXISTS camp_ownership_plan_check;
ALTER TABLE camp_ownership ADD CONSTRAINT camp_ownership_plan_check CHECK (plan IN ('free', 'claimed'));
