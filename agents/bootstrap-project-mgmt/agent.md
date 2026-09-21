# Agent: Bootstrap Project Management System

**Purpose:** Offline-first project tracking across distributed teams

**Use case:** Consultancies, NGOs tracking projects & timesheets

**Modules:**
- Projects (create, edit, status)
- Tasks (CRDT-synced for no conflicts)
- Timesheets (hours tracking)
- Teams (members, assignments)
- Reports (Gantt, burndown, exports)

**Skills Used:**
1. docker-infrastructure (local environment)
2. postgresql-multi-tenant (project data)
3. sync-engine-setup + crdt-integration (tasks auto-merge)
4. jwt-offline-auth (auth)
5. conflict-resolution (task assignment)
6. data-integrity (audit trail)
7. celery-async-jobs (PDF/CSV exports)
8. postgresql-backup (3-2-1)

**Time:** 2-3 weeks MVP

**Key Features:**
- Add tasks offline ✓
- Reorder tasks with CRDT (no conflicts) ✓
- Log hours offline ✓
- Multi-team support ✓
- Offline Gantt charts ✓

