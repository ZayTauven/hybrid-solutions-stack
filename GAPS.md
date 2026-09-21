# GAPS — What exists, what does not

**Last audited:** 2026-09-21 · **Against:** `stack.yml` v1.0

The stack now runs end to end: log in, edit offline, sync, detect a conflict,
resolve it, with tenant isolation enforced by the database rather than by
application code. What follows is what is genuinely finished, what was repaired
along the way, and what is still missing.

---

## Current State

| Layer | Status |
|-------|--------|
| Skills (9) | ✅ Complete — design reference, ~2 800 lines |
| Agents (6) | ✅ Complete — orchestration guides |
| PostgreSQL + Redis | ✅ Running, tenant isolation verified against the database |
| Django API | ✅ Project, `/api/sync`, auth, conflicts, tenant middleware |
| Celery worker + beat | ✅ Running, retention purge scheduled |
| NextJS frontend | ✅ Login, invoice list, sync status, conflict display |
| Expo mobile | ❌ Not started |
| Automated tests | ❌ None |
| `docs/` guides | ❌ Three of four never written |

```bash
docker compose -f templates/docker-compose/docker-compose.yml up -d --build
```

Then follow the first-run steps in [DEPLOY_GUIDE.md](./DEPLOY_GUIDE.md):
`migrate`, then `seed_demo`.

---

## Verified Behaviour

Each of these was exercised against the running stack, not just written:

| Check | Result |
|-------|--------|
| Tenant A reads tenant B's invoices | Blocked — returns only its own rows |
| Tenant A writes a row for tenant B | `new row violates row-level security policy` |
| Query with no tenant context | 0 rows (fail-closed) |
| User requests a tenant they do not belong to | `404 Unknown tenant` |
| Request without `X-Tenant` / without a token | `400` / `401` |
| Push with a stale base version | Conflict queued, server state **not** overwritten |
| Conflict resolution | Applied, invoice versioned, decision written to the audit log |
| `DELETE FROM audit_logs` as the app role | `permission denied` |
| Catch-up over truncated sync batches | Terminates, no page replayed or skipped |
| Retention purge | Deletes expired events, keeps those backing an open conflict |
| `tsc --noEmit` and `next build` | Clean |

---

## Fixed Along the Way

Defects found by running the thing, not by reading it.

### Tenant isolation was inoperative (critical)

Django connected as `appuser` — the `POSTGRES_USER`, therefore `SUPERUSER` with
`BYPASSRLS`. Every policy was bypassed. Fixed with a dedicated `hybrid_app`
role (`NOSUPERUSER`, `NOBYPASSRLS`) plus `FORCE ROW LEVEL SECURITY`, so the
table owner is not exempt either.

### The audit trigger could not insert

`created_at` is filled by Django's `auto_now_add`, which lives in the ORM, so
the column carries no database default. Every write failed the moment the
trigger fired. The trigger now supplies it.

### The retention purge silently did nothing

Celery tasks have no HTTP request, so the tenant middleware never runs for
them and RLS matched zero rows — forever, without error. The task now iterates
tenants and sets the context itself.

### Truncated sync batches lost or replayed events

The cursor advanced to "now" even when the response was capped, skipping
everything that did not fit. Fixed to return the last sent event's timestamp —
and then, because that timestamp was truncated to whole seconds, the next
request's `> cutoff` matched the same event again and the client looped on one
page indefinitely. The cursor now carries sub-second precision, and rows
sharing the boundary timestamp are pulled in with it.

### Client-side defects in the delivered code

- The Zustand store mutated a `Map` in place inside `set()` and returned nothing, so no subscriber ever fired — the UI would have stayed frozen while data changed underneath.
- `useSyncQuery` called `/api/sync` on the NextJS origin instead of Django, sent `Date.now()` as the cursor (killing the downstream flow entirely), and cleared dirty flags on conflict-rejected invoices, discarding local edits.
- Invoice numbers were globally unique; two tenants both numbering from `INV-001` collided on first sync.

### Infrastructure

Host ports were hard-coded, so a native PostgreSQL on 5432 made the stack
unstartable. Now parameterised, and database ports bind to `127.0.0.1`.

---

## Still Missing

### Tests — the largest gap

There is no automated test suite. Every behaviour in the table above was
verified by hand, once. The skills contain worked test examples
([sync-engine-setup](skills/sync-engine-setup/SKILL.md),
[conflict-resolution](skills/conflict-resolution/SKILL.md)) that have not been
turned into runnable tests. Isolation and conflict handling in particular are
exactly the kind of behaviour that regresses silently.

- [ ] `core/tests/test_isolation.py` — cross-tenant read/write denial, fail-closed
- [ ] `core/tests/test_sync.py` — push, pull, idempotent retry, batch truncation
- [ ] `core/tests/test_conflicts.py` — each strategy, plus "manual writes nothing"
- [ ] CI pipeline

### Functional

- [ ] `DELETE` sync operation — the field is accepted and recorded but never applied; a deletion on one site does not propagate
- [ ] JWT refresh on the client — `useAuth` stores the refresh token and never uses it, so a session dies at 24h instead of renewing
- [ ] Conflict resolution UI — the queue is displayed and `POST /api/conflicts/{id}/resolve` works, but nothing in the interface calls it
- [ ] Entity types beyond `invoice` — `_apply_event` raises `NotImplementedError` by design; each new synced entity needs a handler
- [ ] CRDT integration — [the skill](skills/crdt-integration/SKILL.md) is written, no Yjs code exists
- [ ] Backup automation — [the skill](skills/postgresql-backup/SKILL.md) is written, no scripts exist

### Templates and packaging

- [ ] `templates/expo-mobile-offline/` — `stack.yml` lists `useLocalDB.ts`, `services/sync.ts`, `components/OfflineIndicator.tsx`
- [ ] `templates/docker-compose/Makefile`
- [ ] `templates/env-templates/.env.production`, `.env.staging`
- [ ] A production compose file — the current one runs `runserver`, not the `gunicorn` the Dockerfile defaults to, and ships development secrets

### Documentation

- [ ] `docs/ARCHITECTURE.md`, `docs/PERFORMANCE_TUNING.md`, `docs/TROUBLESHOOTING.md`

---

## Known Sharp Edges

Not bugs, but things that will bite someone:

- **A migration that adds a tenant-scoped table must also add its policy.** `0002_rls_and_audit.py` covers the tables that existed when it was written; a new one arrives with no policy, which means no isolation. Nothing enforces this yet.
- **Every background job must set its own tenant context.** `core/tasks.py` has a `tenant_context` helper; a job that forgets it will quietly process nothing.
- **Line items are denormalised into `Invoice.items` (JSON).** Deliberate — the invoice is the unit of sync — but it means no querying or aggregating across line items in SQL.
- **The tenant switcher in the demo UI is a demo affordance.** A real deployment is one device, one tenant; the local store keeps both tenants' data side by side and filters on display.

---

## Suggested Order

1. **Tests** — before anything else. The isolation guarantees are the product; they need a regression net.
2. **`DELETE` propagation** — the most visible functional hole.
3. **JWT refresh** — sessions currently expire hard at 24h.
4. **Conflict resolution UI** — the backend is ready and waiting.
5. **Expo, Makefile, production compose, remaining docs.**
