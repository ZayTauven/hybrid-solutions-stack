-- ============================================================================
-- PostgreSQL bootstrap for the hybrid stack
-- ============================================================================
-- Run ONCE by the Docker entrypoint, before Django ever starts.
--
-- IMPORTANT: this file creates NO application tables.
-- The schema is owned by Django migrations (see DEPLOY_GUIDE.md, migrate step).
-- Creating the tables here as well made `migrate` fail with DuplicateTable on
-- invoices / sync_events / audit_logs.
--
-- Full startup order:
--   1. 01-init-roles.sh   -> non-superuser application role  (Docker entrypoint)
--   2. init.sql           -> extensions                      (Docker entrypoint)
--   3. manage.py migrate  -> application tables              (manual)
--   4. rls-and-audit.sql  -> RLS policies + audit triggers   (manual, after 3)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
