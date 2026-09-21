# Agent: Deploy Central Server

**Purpose:** Setup production Hetzner/LWS central server

**Steps:**
1. Provision VPS (Hetzner CPX21: €10-15/month)
2. Configure PostgreSQL (replication ready)
3. Deploy Django API (gunicorn + Nginx)
4. Setup Redis (session + task queue)
5. Configure SSL/TLS
6. Setup monitoring (Sentry, Prometheus)
7. Backup strategy (S3)
8. CI/CD pipeline (GitHub Actions)

**Skills:**
1. docker-infrastructure (Kubernetes-ready)
2. postgresql-multi-tenant (shared schema multi-tenant)
3. postgresql-backup (3-2-1 rule)
4. celery-async-jobs (sync processor)
5. data-integrity (audit trails)

**Deliverables:**
- Production docker-compose.yml
- Nginx config
- PostgreSQL replication setup
- Backup automation
- Monitoring dashboards

**Time:** 2-3 days setup

