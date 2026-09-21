# Hybrid Stack Deployment Guide

Complete step-by-step instructions for deploying hybrid applications.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Deployment (Single Site)](#local-deployment)
3. [Central Server Deployment (Production)](#central-server)
4. [Scaling to Multiple Tenants](#scaling)
5. [Monitoring & Maintenance](#monitoring)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required

- Docker & Docker Compose (v19.0+)
- PostgreSQL 14+ (or use Docker)
- Redis 6+ (or use Docker)
- Node.js 18+ (for NextJS dev)
- Python 3.11+ (for Django dev)

### Optional

- AWS account (for S3 backups)
- Hetzner/LWS account (for production server)
- Git for version control
- IDE (VS Code recommended)

---

## Local Deployment

### Step 1: Clone Repository

```bash
git clone <your-repo>
cd hybrid-stack
```

### Step 2: Configure Environment

```bash
# Copy template
cp templates/env-templates/.env.example .env

# Edit with your values
nano .env
# Change:
# - DB_PASSWORD
# - SECRET_KEY
# - TENANT_MODE=local
```

### Step 3: Start Local Services

```bash
# From hybrid-stack directory
docker-compose -f templates/docker-compose/docker-compose.yml up -d

# Verify services started
docker-compose -f templates/docker-compose/docker-compose.yml ps

# Check logs
docker-compose -f templates/docker-compose/docker-compose.yml logs -f django
```

### Step 4: Initialize Database

```bash
# Run migrations
docker-compose -f templates/docker-compose/docker-compose.yml exec django python manage.py migrate

# Create superuser
docker-compose -f templates/docker-compose/docker-compose.yml exec django python manage.py createsuperuser
```

### Step 4b: Apply Tenant Isolation (REQUIRED)

Migrations create the tables; they do not create the RLS policies. Until this
script runs, every tenant can read and write every other tenant's rows.

```bash
COMPOSE="docker compose -f templates/docker-compose/docker-compose.yml"
$COMPOSE exec -T postgres psql -U appuser -d shared_meta < templates/postgresql-schema/rls-and-audit.sql
```

Verify isolation actually holds before putting real data in:

```bash
# Expect 0 rows: no tenant context set means nothing is visible (fail-closed)
$COMPOSE exec -T -e PGPASSWORD="$APP_DB_PASSWORD" postgres psql -U hybrid_app -d shared_meta -c "SELECT count(*) FROM invoices;"
```

Re-run this script after every migration that adds a tenant-scoped table.

### Step 4c: Seed demo data (optional)

```bash
$COMPOSE exec django python manage.py seed_demo
```

Creates two tenants (MOR, MUT) with one user each (`mor_user` / `mut_user`,
password `demo1234`) and a couple of invoices apiece — enough to see isolation
and conflicts behave.

### Step 5: Verify Installation

```bash
# Frontend (NextJS)
# Open http://localhost:3000
# Should show login screen

# Backend API
curl -H "X-Tenant: tenant_cmr_001" http://localhost:8000/api/health/

# Response should be:
# {"status":"ok","database":"connected","redis":"connected","timestamp":"..."}
```

### Step 6: Test Offline Mode

```bash
# In browser DevTools:
# 1. Open Network tab
# 2. Set throttling to "Offline"
# 3. Try creating an invoice
# 4. Should work locally
# 5. Restore network
# 6. Should auto-sync
```

---

## Central Server Deployment

### Prerequisites

- Hetzner Cloud account (or LWS)
- SSH key pair
- Domain name (optional but recommended)

### Step 1: Provision VPS

**Recommended Config:**
- CPU: 4 vCPU (Hetzner CPX21)
- RAM: 8 GB
- Disk: 160 GB SSD
- OS: Ubuntu 22.04 LTS
- Cost: €10-15/month

```bash
# Using Hetzner CLI (optional)
hcloud server create \
  --type cpx21 \
  --image ubuntu-22.04 \
  --name hybrid-api-central \
  --ssh-key your-key \
  --datacenter fsn1-dc14
```

### Step 2: SSH into Server

```bash
ssh root@your-server-ip

# Update system
apt update && apt upgrade -y

# Install Docker
apt install -y docker.io docker-compose
usermod -aG docker $USER
```

### Step 3: Clone Repository

```bash
git clone https://github.com/your/repo /opt/hybrid-stack
cd /opt/hybrid-stack
```

### Step 4: Configure for Production

```bash
# Copy env template
cp templates/env-templates/.env.example .env

# Edit for production
nano .env

# Critical changes:
# - DEBUG=false
# - SECRET_KEY=<generate-random>
# - DB_PASSWORD=<secure-password>
# - ALLOWED_HOSTS=your-domain.com
# - TENANT_MODE=central
```

### Step 5: Deploy with Docker

```bash
cd /opt/hybrid-stack

# Pull latest images
docker-compose -f templates/docker-compose/docker-compose.yml pull

# Start all services
docker-compose -f templates/docker-compose/docker-compose.yml up -d

# Verify
docker-compose -f templates/docker-compose/docker-compose.yml ps
```

### Step 6: Setup HTTPS (Let's Encrypt)

```bash
# Install Certbot
apt install -y certbot python3-certbot-nginx

# Generate certificate
certbot certonly --standalone -d your-domain.com

# Copy to docker volume
docker cp /etc/letsencrypt/live/your-domain.com/fullchain.pem \
  nginx:/etc/nginx/certs/

docker cp /etc/letsencrypt/live/your-domain.com/privkey.pem \
  nginx:/etc/nginx/certs/
```

### Step 7: Verify Production Setup

```bash
# Test API
curl -I https://your-domain.com/api/health/

# Should return 200 OK

# Check database
docker-compose -f templates/docker-compose/docker-compose.yml exec django \
  python manage.py dbshell

postgres=# SELECT * FROM tenants;
# Should return empty (first run) or existing tenants
```

### Step 8: Setup Automatic Backups

```bash
# Create backup script
cat > /opt/hybrid-stack/backup.sh << 'EOF'
#!/bin/bash
cd /opt/hybrid-stack
docker-compose -f templates/docker-compose/docker-compose.yml exec -T postgres \
  pg_dump shared_meta | gzip > /backups/daily/backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Upload to S3 (optional)
# aws s3 sync /backups/daily s3://backups-comores/daily/
EOF

chmod +x /opt/hybrid-stack/backup.sh

# Schedule daily at 02:00
echo "0 2 * * * /opt/hybrid-stack/backup.sh" | crontab -
```

---

## Scaling to Multiple Tenants

### Option 1: Multiple Sites (Hub & Spoke)

**Setup on each site:**

```bash
# 1. Clone repo locally
git clone https://github.com/your/repo
cd hybrid-stack

# 2. Configure as LOCAL tenant
export TENANT_MODE=local
export CURRENT_TENANT_ID=tenant_cmr_001

# 3. Start services
docker-compose -f templates/docker-compose/docker-compose.yml up -d

# 4. Configure sync to central
# Edit API_URL to point to central server
export NEXT_PUBLIC_API_URL=https://central.your-domain.com
```

**On central server:**

```bash
# Accepts sync from multiple sites automatically
# Database isolation handled by PostgreSQL

# Verify multiple tenants
docker-compose exec django python manage.py shell
>>> from models import Tenant
>>> Tenant.objects.all()
# Should show: [tenant_cmr_001, tenant_cmr_002, ...]
```

### Option 2: Replicated Central Server (HA)

```yaml
# docker-compose.yml for HA setup

postgres-primary:
  image: postgres:16-alpine
  environment:
    POSTGRES_REPLICATION_MODE: master
  volumes:
    - postgres_primary:/var/lib/postgresql/data

postgres-replica:
  image: postgres:16-alpine
  environment:
    POSTGRES_REPLICATION_MODE: slave
    PGUSER_REPLICATION: replicator
  depends_on:
    - postgres-primary
  volumes:
    - postgres_replica:/var/lib/postgresql/data
```

---

## Monitoring & Maintenance

### Health Checks

```bash
# API health
curl https://your-domain.com/api/health/

# Database
docker-compose exec django \
  python manage.py dbshell -c "SELECT NOW();"

# Redis
docker-compose exec redis redis-cli ping
# Response: PONG
```

### Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f django
docker-compose logs -f postgres
docker-compose logs -f celery
```

### Performance Monitoring

```bash
# Database size
docker-compose exec postgres \
  psql -U appuser -d shared_meta -c \
  "SELECT pg_size_pretty(pg_database_size('shared_meta'));"

# Slow queries
# Enable in postgresql.conf:
# log_min_duration_statement = 1000  # Log queries > 1s
```

### Backup Verification

```bash
# Test restore (DO NOT on production!)
# Create test database
docker-compose exec postgres createdb test_restore
docker-compose exec postgres gunzip < backup.sql.gz | psql test_restore

# Verify
docker-compose exec postgres psql -d test_restore -c "SELECT COUNT(*) FROM invoices;"

# Cleanup
docker-compose exec postgres dropdb test_restore
```

---

## Troubleshooting

### Issue: "Database connection refused"

```bash
# Check if postgres is running
docker-compose ps postgres
# Should show "postgres ... Up"

# Check database logs
docker-compose logs postgres | tail -20

# Rebuild containers
docker-compose down
docker volume rm postgres_data
docker-compose up -d
```

### Issue: "Sync not working"

```bash
# Check sync endpoint
curl -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -H "X-Tenant: tenant_cmr_001" \
  -d '{"events": []}'

# Should return 200 with events list

# Check Celery worker
docker-compose logs celery | tail -20
```

### Issue: "Out of disk space"

```bash
# Check disk usage
docker system df

# Clean up old images
docker image prune -a

# Clean up volumes
docker volume prune

# Check backups size
du -sh /backups/

# Delete old backups
find /backups/daily -mtime +7 -delete
```

### Issue: "Connection timeout on sync"

```bash
# Check network connectivity from site to central
ping central.your-domain.com

# Check firewall
# Ensure port 443 (HTTPS) is open

# Increase timeout in settings
export SYNC_REQUEST_TIMEOUT=60000  # 60 seconds
```

---

## Production Checklist

- [ ] Environment variables set correctly
- [ ] HTTPS/SSL certificate installed
- [ ] Database backups configured (3-2-1)
- [ ] Monitoring/alerting setup (Sentry, etc.)
- [ ] Admin user created
- [ ] Firewall rules configured
- [ ] Rate limiting enabled
- [ ] CORS properly configured
- [ ] Logs rotation setup
- [ ] Database maintenance scheduled

---

## Support

For issues:
1. Check TROUBLESHOOTING section above
2. Review logs: `docker-compose logs -f`
3. Check database: `psql` CLI
4. Verify connectivity: `curl` commands

