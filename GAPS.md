# GAPS — What exists, what does not

**Last audited:** 2026-09-21 · **Against:** `stack.yml` v1.0

The stack runs end to end, with a test suite behind it. What follows is what is
finished, what was repaired along the way, and what is still missing — chiefly
the factory layer that turns this from one application into a way of producing
many.

---

## Current State

| Layer | Status |
|-------|--------|
| Skills (9) | ✅ Complete — design reference, ~2 800 lines |
| Agents (6) | ✅ Complete — orchestration guides |
| PostgreSQL + Redis | ✅ Isolation enforced by the database, installed by migration |
| Django API | ✅ Sync, auth, conflicts, deletions, tenant middleware |
| Celery worker + beat | ✅ Retention purge, tenant-aware |
| `@hybrid/offline-core` | ✅ Stores, sync, auth — no UI dependency |
| Skin: `minimal` | ✅ Reference implementation, consumes the core |
| Test suite | ✅ 45 tests |
| Skin: Vireo | ❌ Adapter not started |
| Skin: Cuba | ❌ Adapter not started |
| Generator | ❌ Not started |
| Expo mobile | ❌ Not started |
| `docs/` guides | ❌ Three of four never written |

```bash
COMPOSE="docker compose -f templates/docker-compose/docker-compose.yml"
$COMPOSE up -d --build
$COMPOSE exec django python manage.py migrate
$COMPOSE exec django python manage.py seed_demo
$COMPOSE exec django python manage.py test
```

---

## Verified Behaviour

Asserted by the suite, not by hand:

| Check | Where |
|-------|-------|
| Cross-tenant read and write denied, fail-closed with no context | `test_isolation` |
| The test role is neither superuser nor BYPASSRLS | `test_isolation` |
| Non-member tenant answers exactly like an unknown one | `test_isolation` |
| Audit trail cannot be rewritten by the application | `test_isolation` |
| Push, pull, and pull not echoing the caller's own origin | `test_sync` |
| A replayed push returns its acceptance, not a conflict | `test_sync` |
| Truncated batches resume without loss, repeat or reorder | `test_sync` |
| A queued conflict writes nothing | `test_conflicts` |
| Field-merge keeps disjoint edits, escalates overlapping ones | `test_conflicts` |
| A resolution is audited with both sides | `test_conflicts` |
| Deletions propagate, and lose to a concurrent edit | `test_deletes` |
| The purge sees tenant data and spares what open conflicts need | `test_tasks` |

---

## Fixed Along the Way

Defects found by running the thing, or by writing a test for it.

### Tenant isolation was inoperative (critical)

Django connected as `appuser` — the `POSTGRES_USER`, therefore `SUPERUSER`
with `BYPASSRLS`. Every policy was bypassed. Fixed with a dedicated
`hybrid_app` role plus `FORCE ROW LEVEL SECURITY`, so the table owner is not
exempt either.

### The isolation policies never reached the test database

They lived in a hand-applied `rls-and-audit.sql`, so an isolation test would
have passed against a database with no policies at all — the one result worse
than a failure. They now ship in migration 0002.

### The audit trigger could not insert

`created_at` is filled by Django's `auto_now_add`, which lives in the ORM, so
the column carries no database default. Every write failed the moment the
trigger fired.

### The retention purge silently did nothing

Celery tasks have no HTTP request, so the tenant middleware never ran for them
and RLS matched zero rows — forever, without error.

### Truncated sync batches lost or replayed events

The cursor advanced to "now" over a capped page, skipping everything that did
not fit. Fixed to return the last sent event's timestamp — and then, because
that timestamp was truncated to whole seconds, the next request matched the
same event again and the client looped on one page indefinitely.

### A retried push was told it conflicted with itself

A client that lost the response and retried sent a base version the record had
already moved past. The push is now idempotent in outcome, not just in the
event log, so a dropped connection no longer costs the user a manual conflict.

### Field-merge escalated everything

It compared the serializer's output against raw client payloads, and DRF
renders a Decimal as `"100.00"` where the client sent `100`. Every amount read
as changed on both sides, so even perfectly disjoint edits escalated. It now
compares three client-shaped snapshots.

### Client-side defects in the delivered code

- The Zustand store mutated a `Map` in place inside `set()` and returned nothing, so no subscriber ever fired — the UI would have stayed frozen while data changed underneath.
- `useSyncQuery` called the NextJS origin instead of Django, sent `Date.now()` as the cursor (killing the downstream flow entirely), and cleared dirty flags on conflict-rejected records.
- Invoice numbers were globally unique; two tenants both numbering from `INV-001` collided on first sync.

### Repository hygiene

The public repository carried the source of an Envato-licensed template and
~80 MB of webpack build cache. Both removed from tracking and from history;
licensed skins and the asset bank are now external inputs.

---

## Still Missing

### The factory — the main body of remaining work

- [ ] **Vireo adapter** (`templates/skins/vireo/`). Known blockers, all verified: `src/screens/maps/Leaflet.tsx:15` imports `leaflet/dist/leaflet.css` while `leaflet` is in neither `package.json` nor the lockfile, so **the template does not build as shipped**; `app/layout.tsx:119-122` loads three fonts from Google, which no offline-first first paint can rely on; `src/lib/manifest.ts:107` hardcodes `/` → `dashboards/sales`; `src/components/shell/Sidebar.tsx:160-165` hardcodes the template's own brand. It also has no React component primitives — 416 `.ax-*` CSS classes and two components — so the adapter must supply a thin primitives layer or every generated page is copy-pasted markup.
- [ ] **Cuba adapter** (`templates/skins/cuba/`). Start from the Starterkit: the same shell as the full template with 70 source files instead of 1752. Its code is 301 KB; the other 75 MB are demo images to prune. It declares ~110 dependencies to render one page, and pruning that manifest is the safest large win.
- [ ] **Generator** (`tools/create-hybrid-app/`). Assembles backend + skin + core, prunes demo content, rebrands, and — the part that makes it a factory rather than a `cp -r` — draws a palette, a layout variant and an asset set per project so two builds on the same skin do not look alike.
- [ ] **Asset manifest.** The bank is 123 raster files with no usable identifiers: `document-1.png` is a delivery illustration, three files have 197-character names. Nothing can be selected by intent until an `assets.manifest.json` carrying id, category, licence and source is authored. 87% of its 139 MB sits in 46 untouched camera originals that need one pass of resizing.

### Functional

- [ ] Conflict resolution UI — the queue is displayed and `POST /api/conflicts/{id}/resolve` works, but nothing in the interface calls it
- [ ] Entity types beyond `invoice` — `_apply_event` raises `NotImplementedError` by design; each new synced entity needs a handler
- [ ] CRDT integration — [the skill](skills/crdt-integration/SKILL.md) is written, no Yjs code exists
- [ ] Backup automation — [the skill](skills/postgresql-backup/SKILL.md) is written, no scripts exist
- [ ] No CI. The suite exists and nothing runs it.

### Templates and packaging

- [ ] `templates/expo-mobile-offline/`
- [ ] `templates/docker-compose/Makefile`
- [ ] `.env.production`, `.env.staging`
- [ ] A production compose file — the current one runs `runserver`, not the `gunicorn` the Dockerfile defaults to, and ships development secrets

### Documentation

- [ ] `docs/ARCHITECTURE.md`, `docs/PERFORMANCE_TUNING.md`, `docs/TROUBLESHOOTING.md`

---

## Known Sharp Edges

- **A migration that adds a tenant-scoped table must also add its policy.** `0002_rls_and_audit.py` covers the tables that existed when it was written. A new one arrives with no policy, which means no isolation, and nothing enforces this.
- **Every background job must set its own tenant context.** `core/tasks.py` has a `tenant_context` helper; a job that forgets it will quietly process nothing.
- **A soft-deleted invoice keeps its number reserved.** The `(tenant, number)` constraint does not exclude deleted rows — defensible for accounting, surprising otherwise.
- **Line items are denormalised into `Invoice.items` (JSON).** Deliberate: the invoice is the unit of sync. It does mean no SQL aggregation across line items.
- **Licensed skins and the asset bank are outside the repository.** A clone cannot generate a project until they are present locally. The generator must say so plainly rather than failing obscurely.
