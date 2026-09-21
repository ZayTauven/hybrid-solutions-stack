# Hybrid Solutions Stack

**Complete offline-first application framework for connectivity-constrained regions**

Build resilient business applications that work locally, sync across LANs, and connect to central servers — with zero forced internet dependency.

---

## 🎯 What This Is

An **offline-first application stack** with:

- ✅ **9 Reusable Skills** (database, sync, conflicts, auth, backup, etc.)
- ✅ **6 Orchestration Agents** (ERP, CRM, Project Management, Scaling)
- ✅ **Running stack** — PostgreSQL + Redis + Django API + Celery + NextJS
- 🚧 **Templates** — Expo mobile not started, see [GAPS.md](./GAPS.md)

One `docker compose up` brings up the whole thing. Tenant isolation is enforced
by PostgreSQL row-level security, not by application code, and was verified
against the running database. There is no automated test suite yet — the
largest remaining gap.

**For contexts like:** Comores, rural Africa, developing economies, disaster zones, offline fieldwork

---

## 🚀 Quick Start

### Option 1: Run it locally (~5 min)

```bash
COMPOSE="docker compose -f templates/docker-compose/docker-compose.yml"

# 1. Configure
cp templates/env-templates/.env.example templates/docker-compose/.env
# Set DB_PASSWORD and APP_DB_PASSWORD at minimum

# 2. Start everything
$COMPOSE up -d --build

# 3. Create the schema and the isolation policies
$COMPOSE exec django python manage.py migrate

# 4. Seed two tenants with users and invoices
$COMPOSE exec django python manage.py seed_demo

# 5. Optional: prove the isolation holds
$COMPOSE exec django python manage.py test
```

Migrations install the row-level security policies alongside the tables
(`core/migrations/0002_rls_and_audit.py`), so isolation cannot be forgotten —
and the test database gets it too, which is what makes the isolation tests
worth anything.

Open http://localhost:3000 and sign in as `mor_user` / `demo1234`. Switch the
tenant selector to `MUT` and the API refuses — that user is not a member.

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000/api/health/ |
| Admin | http://localhost:8000/admin/ |

If a native PostgreSQL already holds 5432, set `POSTGRES_HOST_PORT` in
`templates/docker-compose/.env` — the same applies to `DJANGO_HOST_PORT` and
`NEXTJS_HOST_PORT`.

### Option 2: Deploy Central Server (1 day)

Use Agent: `deploy-central-server`

```bash
cd agents/deploy-central-server
# Follow guide in agent.md
```

### Option 3: Migrate Existing App (4-6 weeks)

Use Agent: `migrate-existing-to-hybrid`

---

## 📚 Skills (Building Blocks)

| Skill | Purpose | Time | Use |
|-------|---------|------|-----|
| **sync-engine** | Bidirectional offline sync | 4-6h | Core to all apps |
| **postgresql-multi-tenant** | Isolated databases + RLS | 3-4h | Multi-org isolation |
| **jwt-offline-auth** | Work without server | 2-3h | Offline login |
| **conflict-resolution** | Handle simultaneous edits | 3-4h | Data consistency |
| **crdt-integration** | Conflict-free lists/docs | 3-4h | Collaborative features |
| **docker-infrastructure** | Production containers | 2-3h | Local & server deploy |
| **postgresql-backup** | 3-2-1 backup strategy | 2-3h | Data protection |
| **celery-async-jobs** | Background processing | 2-3h | PDF gen, exports, cleanup |
| **data-integrity** | Audit trails + rollback | 3-4h | Compliance & debugging |

---

## 🎬 Agents (Complete Solutions)

| Agent | Output | Time |
|-------|--------|------|
| **bootstrap-hybrid-erp** | Full ERP (invoices, inventory, GL) | 2-3 weeks |
| **bootstrap-project-mgmt** | Project tracking + timesheets | 2-3 weeks |
| **bootstrap-crm** | Sales pipeline + contacts | 2 weeks |
| **deploy-central-server** | Production server on Hetzner/LWS | 2-3 days |
| **migrate-existing-to-hybrid** | Convert existing app to offline-first | 4-6 weeks |
| **scale-to-production** | Multi-region, sharded for 5000+ users | 3-6 months |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────┐
│   FRONTEND LAYER                    │
│  ┌─────────────┐   ┌──────────────┐ │
│  │ NextJS Web  │   │  Expo Mobile │ │
│  └──────┬──────┘   └──────┬───────┘ │
└─────────┼───────────────┬─┘─────────┘
          │ (local-first) │
    ┌─────▼──────────────┼────────┐
    │  State Management       │
    │ ┌──────────────────────┐│
    │ │ Zustand + TanStack   ││
    │ │ Query (auto-sync)    ││
    │ └──────────────────────┘│
    └─────────┬──────────────┘
              │
    ┌─────────▼──────────────┐
    │  Local Persistence    │
    │ ┌─────────────────────┐│
    │ │ PostgreSQL Local    ││ (site-specific)
    │ │ IndexedDB (browser) ││
    │ └─────────────────────┘│
    └─────────┬──────────────┘
              │ POST /api/sync
              │
    ┌─────────▼──────────────────────┐
    │  Backend (Django)              │
    │ ┌─────────────────────────────┐│
    │ │ /api/sync (bidirectional)   ││
    │ │ /api/auth (JWT)             ││
    │ │ /api/resources/... (CRUD)   ││
    │ └─────────────────────────────┘│
    │ ┌─────────────────────────────┐│
    │ │ Celery (async jobs)         ││
    │ │ - Sync processing           ││
    │ │ - PDF/CSV generation        ││
    │ │ - Backups                   ││
    │ └─────────────────────────────┘│
    └─────────┬──────────────────────┘
              │
    ┌─────────▼──────────────────────┐
    │  PostgreSQL Central (Hetzner)  │
    │ - Master database              │
    │ - Versioning tables            │
    │ - Audit logs                   │
    │ - Backup automation            │
    └────────────────────────────────┘
```

---

## 📊 Key Concepts

### Offline-First

```
What you build: Work ALWAYS
Where: Locally on device
Sync: When connection appears
Fallback: If server down, app still works
```

### Eventual Consistency

```
Site A edits invoice offline
Site B edits same invoice offline
Both sync to server
Server detects conflict
Resolution: Last-write-wins (configurable)
Result: Consistent state everywhere
```

### CRDT (Conflict-free)

```
Task list in Yjs
Site A adds "Task 1"
Site B adds "Task 2"
Auto-merge: Both tasks exist
No conflict!
```

---

## 🔒 Security

- **JWT**: Work offline up to 24h without server
- **RLS**: PostgreSQL row-level security by tenant
- **Audit**: Immutable logs of all changes
- **Encryption**: Data at rest (optional), TLS in transit (required)
- **RBAC**: Role-based access control

---

## 📦 Deployment Options

| Profile | Scale | Cost | Time |
|---------|-------|------|------|
| **Local Single Site** | 1-100 users | $0 | 2-4h |
| **Central Server** | 10-1000 users | $10-20/mo | 1-2 days |
| **Production Scale** | 1000+ users | $100-500/mo | 2-3 mo |

---

## 🛠️ Tech Stack

**Frontend:** NextJS + TypeScript + Zustand + TanStack Query  
**Mobile:** Expo (React Native)  
**Backend:** Django + Django REST Framework  
**Database:** PostgreSQL 16 + Redis  
**Infrastructure:** Docker + docker-compose  
**Queue:** Celery + Redis  
**Sync:** Custom bidirectional sync engine  
**Collab:** Yjs (CRDT)

---

## 📖 Documentation

- **[DEPLOY_GUIDE.md](./DEPLOY_GUIDE.md)** — Step-by-step setup
- **[INDEX.md](./INDEX.md)** — Where to find what
- **[GAPS.md](./GAPS.md)** — What is implemented, what is not, and what to build next

Not written yet: `ARCHITECTURE.md`, `PERFORMANCE_TUNING.md`, `TROUBLESHOOTING.md`.

---

## 🎓 Using This Stack

### For Consultants

```
1. Pick Agent (ERP, CRM, Project Mgmt)
2. Compose Skills
3. Customize with templates
4. Deploy to client
```

### For Developers

```
1. Study Architecture (ARCHITECTURE.md)
2. Read relevant Skill (e.g., sync-engine)
3. Copy Template code
4. Modify for your domain
5. Deploy using Agent guide
```

### For Organizations

```
1. Run bootstrap Agent
2. Customize for your business
3. Deploy locally + centrally
4. Scale when needed
```

---

## 📊 Project Structure

```
hybrid-stack/
├── skills/                          # 9 reusable building blocks
│   ├── sync-engine-setup/
│   ├── postgresql-multi-tenant/
│   ├── jwt-offline-auth/
│   ├── conflict-resolution/
│   ├── crdt-integration/
│   ├── docker-infrastructure/
│   ├── postgresql-backup/
│   ├── celery-async-jobs/
│   └── data-integrity/
│
├── agents/                          # 6 orchestration workflows
│   ├── bootstrap-hybrid-erp/
│   ├── bootstrap-project-mgmt/
│   ├── bootstrap-crm/
│   ├── deploy-central-server/
│   ├── migrate-existing-to-hybrid/
│   └── scale-to-production/
│
├── templates/                       # Code starters
│   ├── nextjs-offline-first/
│   ├── django-api-sync/
│   ├── expo-mobile-offline/
│   ├── docker-compose/
│   ├── postgresql-schema/
│   └── env-templates/
│
├── docs/                            # Guides & reference
│   ├── DEPLOY_GUIDE.md
│   ├── ARCHITECTURE.md
│   ├── PERFORMANCE_TUNING.md
│   └── TROUBLESHOOTING.md
│
├── stack.yml                        # Stack definition
└── README.md                        # This file
```

---

## 🚦 Getting Help

**Questions about:**
- **Skills**: Read the SKILL.md in each skill folder
- **Agents**: Check agent.md in each agent folder
- **Deployment**: See DEPLOY_GUIDE.md
- **Architecture**: Read ARCHITECTURE.md
- **Performance**: See PERFORMANCE_TUNING.md

---

## 📝 License

MIT License — Free for commercial and personal use

---

## 🙏 Acknowledgments

Built for and by consultants, developers, and organizations working in connectivity-constrained regions.

Special thanks to: Comores developers community

---

**Status:** Running vertical slice — see [GAPS.md](./GAPS.md) for what is not done  
**Last Updated:** 2026-09-20  
**Maintained By:** Zay
