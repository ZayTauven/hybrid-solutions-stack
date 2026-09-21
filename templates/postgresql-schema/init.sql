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
--   3. manage.py migrate  -> tables, then RLS policies and audit triggers
--                            (migration 0002)                (manual)
--
-- There is no manual SQL step after migrate any more. The policies used to
-- live in a rls-and-audit.sql applied by hand, which meant remembering it
-- after every migration that added a tenant-scoped table -- and meant the test
-- database never had them.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
