-- One-time reset of the April 2026 beta schema before the first migration runs.
-- The beta held synthetic data only. Run in the Supabase SQL editor, then deploy.

DROP TABLE IF EXISTS analytics_events CASCADE;
DROP TABLE IF EXISTS camp_ownership CASCADE;
DROP TABLE IF EXISTS leads CASCADE;
DROP TABLE IF EXISTS camp_submissions CASCADE;
DROP TABLE IF EXISTS claim_requests CASCADE;
DROP TABLE IF EXISTS field_sources CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS camps CASCADE;
DROP TABLE IF EXISTS schema_migrations CASCADE;
DROP FUNCTION IF EXISTS set_updated_at() CASCADE;
