# Agent: Scale to Production (500+ tenants)

**Purpose:** Scale from single server to enterprise

**Phases:**

**Phase 1: Replicated (100-500 tenants)**
- PostgreSQL with replication (Primary + Replica)
- Load balancer (Nginx)
- Multiple Django instances
- Redis cluster

**Phase 2: Sharded (500-5000 tenants)**
- Shard by tenant_id hash
- Each shard = independent DB
- Router determines shard
- Cross-shard queries limited

**Phase 3: Multi-region**
- Regional servers (Africa, Europe, Asia)
- Data residency compliance
- Sync across regions

**Skills:**
- docker-infrastructure (Kubernetes)
- postgresql-multi-tenant (advanced sharding)
- postgresql-backup (per-shard backups)
- celery-async-jobs (distributed processing)

**Time:** 3-6 months implementation

