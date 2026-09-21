#!/bin/bash
# ============================================================================
# Create the application role Django connects with at runtime.
# ============================================================================
# Why a dedicated role: POSTGRES_USER is a SUPERUSER, and a superuser bypasses
# every RLS policy. Connecting with it makes multi-tenant isolation purely
# decorative -- each tenant reads and writes every other tenant's data.
#
# hybrid_app is NOSUPERUSER + NOBYPASSRLS. Combined with FORCE ROW LEVEL
# SECURITY (see rls-and-audit.sql), isolation holds even though this role owns
# the tables its own migrations created.
# ============================================================================
set -e

: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set to create the application role}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hybrid_app') THEN
            CREATE ROLE hybrid_app LOGIN PASSWORD '${APP_DB_PASSWORD}'
                NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO hybrid_app;
    GRANT USAGE, CREATE ON SCHEMA public TO hybrid_app;
SQL
