"""Row-level security and the audit trail, as a migration.

This used to be a hand-applied rls-and-audit.sql. Two things were wrong with
that. It had to be remembered after every migration that added a tenant-scoped
table, and the test database Django creates never received it -- so an
isolation test would have passed against a database with no policies at all,
which is the one result worse than a failure.

Applying it here means every database that runs migrations is isolated,
including the test one.
"""

from django.db import migrations

FORWARD_SQL = r"""
-- ---------------------------------------------------------------------------
-- 1. Enable RLS
-- ---------------------------------------------------------------------------
-- ENABLE alone is NOT enough: a table's owner is exempt from its own policies,
-- and migrations create these tables under the application role, which
-- therefore owns them. FORCE removes the exemption.
ALTER TABLE invoices    ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices    FORCE  ROW LEVEL SECURITY;
ALTER TABLE sync_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_events FORCE  ROW LEVEL SECURITY;
ALTER TABLE sync_conflicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_conflicts FORCE  ROW LEVEL SECURITY;
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

DROP POLICY IF EXISTS tenant_isolation_conflicts ON sync_conflicts;
CREATE POLICY tenant_isolation_conflicts ON sync_conflicts
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID);

DROP POLICY IF EXISTS tenant_isolation_audit ON audit_logs;
CREATE POLICY tenant_isolation_audit ON audit_logs
    FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID);

-- ---------------------------------------------------------------------------
-- 3. Audit trigger
-- ---------------------------------------------------------------------------
-- created_at is supplied explicitly: Django's auto_now_add fills it in the ORM
-- layer, so the column carries no database default and a trigger-side INSERT
-- would violate its NOT NULL constraint.
CREATE OR REPLACE FUNCTION audit_trigger()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public
AS $audit$
BEGIN
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
$audit$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_invoices ON invoices;
CREATE TRIGGER audit_invoices AFTER INSERT OR UPDATE OR DELETE ON invoices
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();

-- ---------------------------------------------------------------------------
-- 4. Audit trail immutability
-- ---------------------------------------------------------------------------
-- A log the application can rewrite proves nothing. Revoked from the migrating
-- role by name rather than hardcoding one, so a generated project is free to
-- call its application role whatever it likes.
DO $revoke$
BEGIN
    EXECUTE format('REVOKE UPDATE, DELETE ON audit_logs FROM %I', current_user);
END
$revoke$;
"""

REVERSE_SQL = r"""
DO $regrant$
BEGIN
    EXECUTE format('GRANT UPDATE, DELETE ON audit_logs TO %I', current_user);
END
$regrant$;

DROP TRIGGER IF EXISTS audit_invoices ON invoices;
DROP FUNCTION IF EXISTS audit_trigger();

DROP POLICY IF EXISTS tenant_isolation_invoices ON invoices;
DROP POLICY IF EXISTS tenant_isolation_sync ON sync_events;
DROP POLICY IF EXISTS tenant_isolation_conflicts ON sync_conflicts;
DROP POLICY IF EXISTS tenant_isolation_audit ON audit_logs;

ALTER TABLE invoices       DISABLE ROW LEVEL SECURITY;
ALTER TABLE sync_events    DISABLE ROW LEVEL SECURITY;
ALTER TABLE sync_conflicts DISABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs     DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
