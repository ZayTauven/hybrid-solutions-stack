# Hybrid Solutions Stack

**A factory for offline-first applications, for places where the network is not a given**

Business applications that work locally, sync when they can, and never assume
a connection. Built to be produced repeatedly, without every client ending up
with the same product wearing a different logo.

---

## 🎯 What This Is

Three things, in layers:

- **An architecture that holds.** PostgreSQL row-level security enforces tenant isolation — not application code, which can be forgotten. A bidirectional sync engine handles disconnected edits, detects conflicts and refuses to guess when guessing would cost money. 45 tests stand behind it.
- **A portable core.** `@hybrid/offline-core` — stores, sync, auth, tombstones — with no UI dependency, so it mounts on any frontend.
- **A generator.** `create-hybrid-app` assembles the backend, the core and a skin into a project, prunes the skin's demo content, and draws it a palette, a shape and a layout of its own.

Plus 9 skills and 6 orchestration agents as design reference.

```bash
node tools/create-hybrid-app --name acme-erp --skin minimal
```

**For contexts like:** Comores, rural Africa, developing economies, disaster zones, offline fieldwork

### Skins

| Skin | Stack | Source |
|------|-------|--------|
| `minimal` | Plain CSS, no design system | Ships here |
| `vireo` | Tailwind v4, three-layer tokens, 12 accents, RTL | Licensed separately |
| `cuba` | Bootstrap 5 + SCSS, i18n, 12 layout variants | Not yet adapted |

Vireo and Cuba are commercial templates. This repository holds the adapters —
what to prune, what to patch, how to wire the core — not the templates
themselves. Drop your licensed copy in `skins-src/<name>/` and the generator
picks it up; run it without one and it tells you exactly where it looked.

---

## 🚀 Quick Start

### Option 1: Generate a project

```bash
node tools/create-hybrid-app --name acme-erp --skin minimal
cd acme-erp

COMPOSE="docker compose -f docker/docker-compose.yml --env-file .env"
$COMPOSE up -d --build
$COMPOSE exec django python manage.py migrate
$COMPOSE exec django python manage.py seed_demo
$COMPOSE exec django python manage.py test
```

The generator picks host ports that are actually free, writes fresh secrets,
and draws the project a palette and a shape from its name. Its README records
the seed, so the identity is reproducible rather than accidental.

Add `--skin vireo` once `skins-src/vireo/` holds your licensed copy.

### Option 2: Run this repository itself (~5 min)

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

### Option 3: Deploy Central Server (1 day)

Use Agent: `deploy-central-server`

```bash
cd agents/deploy-central-server
# Follow guide in agent.md
```

### Option 4: Migrate Existing App (4-6 weeks)

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
├── packages/offline-core/           # The portable layer: stores, sync, auth
│
├── tools/create-hybrid-app/         # The generator
│
├── templates/
│   ├── django-api-sync/             # Backend: sync endpoint, tenant middleware,
│   │                                #   conflict strategies, Celery jobs, tests
│   ├── postgresql-schema/           # Roles and extensions (schema lives in migrations)
│   ├── docker-compose/
│   ├── env-templates/
│   └── skins/                       # Adapters, not templates
│       ├── minimal/                 #   ships here
│       ├── vireo/                   #   needs skins-src/vireo
│       └── cuba/                    #   not yet written
│
├── skills/                          # 9 reusable building blocks
├── agents/                          # 6 orchestration workflows
│
├── skins-src/                       # IGNORED — your licensed template copies
├── assets-bank/                     # IGNORED — your asset library
│
├── stack.yml                        # Stack definition
├── GAPS.md                          # What is done, what is not
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
