-- ============================================================================
-- Multi-tenant isolation (RLS) + audit trail
-- ============================================================================
-- APPLY AFTER `manage.py migrate`: this script assumes invoices, sync_events
-- and audit_logs already exist.
--
--   docker compose exec -T postgres \
--     psql -U appuser -d shared_meta < templates/postgresql-schema/rls-and-audit.sql
--
-- Session context the application must set on every connection:
--   SET app.current_tenant_id = '<uuid>';
--   SET app.client_ip        = '<ip>';     -- optional
-- Without app.current_tenant_id the policies deny everything (fail-closed).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Enable RLS
-- ---------------------------------------------------------------------------
-- ENABLE alone is NOT enough: a table's owner is exempt from its own policies.
-- Django migrations create the tables under the application role, so that role
-- owns them and would bypass isolation. FORCE removes the exemption.
ALTER TABLE invoices    ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices    FORCE  ROW LEVEL SECURITY;
ALTER TABLE sync_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_events FORCE  ROW LEVEL SECURITY;
ALTER TABLE audit_logs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs  FORCE  ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 2. Isolation policies
-- ---------------------------------------------------------------------------
-- NULLIF guards the case where the setting is '': ''::UUID raises, while
-- NULL::UUID simply makes the comparison false (no rows visible).
-- With FOR ALL and no explicit WITH CHECK, PostgreSQL applies USING to
-- inserted rows too: a session cannot write on behalf of another tenant.
DROP POLICY IF EXISTS tenant_isolation_invoices ON invoices;
CREATE POLICY tenant_isolation_invoices ON invoices
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID);

DROP POLICY IF EXISTS tenant_isolation_sync ON sync_events;
CREATE POLICY tenant_isolation_sync ON sync_events
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID);

DROP POLICY IF EXISTS tenant_isolation_audit ON audit_logs;
CREATE POLICY tenant_isolation_audit ON audit_logs
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID);

-- ---------------------------------------------------------------------------
-- 3. Audit trigger
-- ---------------------------------------------------------------------------
-- SECURITY DEFINER: the trigger must be able to write to audit_logs even when
-- the caller's own policy would block it, otherwise every legitimate write
-- would fail at logging time.
CREATE OR REPLACE FUNCTION audit_trigger()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- created_at is supplied explicitly: Django's auto_now_add fills it in the
    -- ORM layer, so the column carries no database default and a trigger-side
    -- INSERT would violate its NOT NULL constraint.
    INSERT INTO audit_logs (
        tenant_id, entity_type, entity_id, action,
        old_values, new_values, ip_address, created_at
    ) VALUES (
        COALESCE(NEW.tenant_id, OLD.tenant_id),
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id)::VARCHAR,
        TG_OP,
        CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END,
        CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END,
        NULLIF(current_setting('app.client_ip', TRUE), '')::INET,
        NOW()
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_invoices ON invoices;
CREATE TRIGGER audit_invoices AFTER INSERT OR UPDATE OR DELETE ON invoices
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();

-- ---------------------------------------------------------------------------
-- 4. Audit trail immutability
-- ---------------------------------------------------------------------------
-- A log the application can rewrite proves nothing.
REVOKE UPDATE, DELETE ON audit_logs FROM hybrid_app;
