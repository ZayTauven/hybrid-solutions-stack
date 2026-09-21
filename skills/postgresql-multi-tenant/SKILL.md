# Skill: PostgreSQL Multi-Tenant Database Setup

**Purpose:** Configure isolated PostgreSQL databases with RLS, versioning, and audit trails.

**Outputs:**
- ✅ Multi-tenant database architecture (isolated or shared schema)
- ✅ Row-Level Security (RLS) policies
- ✅ Tenant routing middleware
- ✅ Audit tables & triggers
- ✅ Data partitioning (optional)

---

## Architecture: Isolated Databases

```sql
PostgreSQL Server (Hetzner)
├── Database: shared_meta
│   ├── tenants table
│   ├── users table
│   └── licenses table
│
├── Database: tenant_cmr_001_prod
│   ├── public.invoices
│   ├── public.projects
│   └── public.audit_logs
│
└── Database: tenant_cmr_002_prod
    ├── public.invoices
    ├── public.projects
    └── public.audit_logs
```

---

## Setup Scripts

### 1. Create Shared Metadata Database

```sql
-- shared_meta database
CREATE DATABASE shared_meta;

\c shared_meta

-- Tenants table
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,  -- 'cmr_001'
    country VARCHAR(2) DEFAULT 'KM',
    currency VARCHAR(3) DEFAULT 'KMF',
    timezone VARCHAR(50) DEFAULT 'UTC',
    db_name VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',  -- 'admin', 'user', 'viewer'
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_users_email_tenant ON users(tenant_id, email);
```

### 2. Create Tenant Database Template

```sql
-- Template for each tenant database
CREATE DATABASE tenant_cmr_001_prod;

\c tenant_cmr_001_prod

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Invoices table
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(50) NOT NULL,  -- Denormalized safety
    number VARCHAR(50) NOT NULL UNIQUE,
    status VARCHAR(20) DEFAULT 'draft',
    amount DECIMAL(12, 2) NOT NULL,
    due_date DATE,
    created_by_id UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Versioning
    version INT DEFAULT 1,
    
    -- Sync tracking
    _synced_at TIMESTAMP,
    _is_dirty BOOLEAN DEFAULT false,
    
    -- Audit
    deleted_at TIMESTAMP  -- Soft delete
);

CREATE INDEX idx_invoices_tenant_status ON invoices(tenant_id, status);
CREATE INDEX idx_invoices_created_at ON invoices(created_at DESC);

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'open',
    budget DECIMAL(12, 2),
    start_date DATE,
    end_date DATE,
    version INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Audit Logs (immutable)
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    user_id UUID,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(20) NOT NULL,  -- 'CREATE', 'UPDATE', 'DELETE'
    old_values JSONB,
    new_values JSONB,
    ip_address INET,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_tenant_entity ON audit_logs(tenant_id, entity_type, created_at);

-- Enable RLS
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
```

### 3. Row-Level Security (RLS)

```sql
-- RLS Policy: All users see only their tenant's data
CREATE POLICY tenant_isolation ON invoices
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

CREATE POLICY tenant_isolation ON projects
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::VARCHAR)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::VARCHAR);

-- Role-based policies (optional)
CREATE ROLE invoices_viewer;
CREATE ROLE invoices_editor;

CREATE POLICY view_only_policy ON invoices
    FOR SELECT
    TO invoices_viewer
    USING (true);

CREATE POLICY edit_own_invoices ON invoices
    FOR UPDATE
    TO invoices_editor
    USING (created_by_id = current_user_id())
    WITH CHECK (created_by_id = current_user_id());
```

### 4. Audit Trigger (Auto-logging)

```sql
-- Function to log changes
CREATE OR REPLACE FUNCTION audit_trigger()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_logs (
        tenant_id, user_id, entity_type, entity_id,
        action, old_values, new_values, ip_address
    ) VALUES (
        current_setting('app.current_tenant_id')::VARCHAR,
        current_setting('app.current_user_id')::UUID,
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id),
        TG_OP,
        to_jsonb(OLD),
        to_jsonb(NEW),
        current_setting('app.client_ip', TRUE)::INET
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Attach to tables
CREATE TRIGGER audit_invoices AFTER INSERT OR UPDATE OR DELETE ON invoices
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();

CREATE TRIGGER audit_projects AFTER INSERT OR UPDATE OR DELETE ON projects
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();
```

---

## Django Integration

### 1. Tenant Router

```python
# django_app/routers.py
from django.conf import settings

class TenantRouter:
    """
    Route all tenant models to tenant-specific database
    """
    
    TENANT_MODELS = {
        'invoices.Invoice',
        'invoices.InvoiceLine',
        'projects.Project',
        'projects.Task',
    }
    
    def db_for_read(self, model, **hints):
        if self._is_tenant_model(model):
            return self._get_tenant_db()
        return 'default'  # shared_meta
    
    def db_for_write(self, model, **hints):
        return self.db_for_read(model, **hints)
    
    def allow_relation(self, obj1, obj2, **hints):
        return True
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in ['invoices', 'projects']:
            return db != 'default'
        return db == 'default'
    
    def _is_tenant_model(self, model):
        return f"{model._meta.app_label}.{model.__name__}" in self.TENANT_MODELS
    
    def _get_tenant_db(self):
        from django.db import connection
        tenant_id = getattr(connection, 'tenant_id', None)
        if tenant_id:
            return f"tenant_{tenant_id}"
        return 'default'
```

### 2. Middleware

```python
# django_app/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.db import connection
from rest_framework.exceptions import AuthenticationFailed

class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Get tenant from header or user
        tenant_id = request.headers.get('X-Tenant')
        if not tenant_id and request.user.is_authenticated:
            tenant_id = request.user.current_tenant_id
        
        if not tenant_id:
            raise AuthenticationFailed("Tenant not specified")
        
        # Store on connection
        connection.tenant_id = tenant_id
        
        # Set PostgreSQL context for RLS
        with connection.cursor() as cursor:
            cursor.execute(
                "SET app.current_tenant_id = %s;",
                [tenant_id]
            )
            cursor.execute(
                "SET app.current_user_id = %s;",
                [str(request.user.id) if request.user.is_authenticated else None]
            )
            cursor.execute(
                "SET app.client_ip = %s;",
                [request.META.get('REMOTE_ADDR')]
            )
```

### 3. Models

```python
# models.py
from django.db import models
from django.contrib.auth.models import User

class Tenant(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    db_name = models.CharField(max_length=100)
    country = models.CharField(max_length=2, default='KM')
    currency = models.CharField(max_length=3, default='KMF')
    
    class Meta:
        db_table = 'tenants'

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
    ]
    
    id = models.UUIDField(primary_key=True)
    tenant_id = models.CharField(max_length=50)  # Denormalized
    number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    version = models.IntegerField(default=1)
    
    class Meta:
        db_table = 'invoices'
        indexes = [
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['created_at']),
        ]
```

---

## Database Setup Command

```python
# management/commands/init_tenant_db.py
from django.core.management.base import BaseCommand
from django.db import connections

class Command(BaseCommand):
    help = 'Initialize new tenant database'
    
    def add_arguments(self, parser):
        parser.add_argument('tenant_id')
        parser.add_argument('--template', default='template_base')
    
    def handle(self, *args, **options):
        tenant_id = options['tenant_id']
        db_name = f"tenant_{tenant_id}_prod"
        
        # Create database from template
        with connections['default'].cursor() as cursor:
            cursor.execute(f"CREATE DATABASE {db_name} TEMPLATE {options['template']};")
        
        # Configure database
        with connections[db_name].cursor() as cursor:
            cursor.execute("ALTER DATABASE %s SET datestyle = 'ISO, DMY';", [db_name])
            cursor.execute("ALTER DATABASE %s SET timezone = 'UTC';", [db_name])
        
        self.stdout.write(self.style.SUCCESS(f'Created {db_name}'))
```

---

## Performance Tuning

```sql
-- Analyze queries
EXPLAIN (ANALYZE, BUFFERS) 
SELECT * FROM invoices WHERE tenant_id = 'cmr_001' AND status = 'sent';

-- Vacuum & analyze
VACUUM ANALYZE invoices;

-- Monitor table size
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

