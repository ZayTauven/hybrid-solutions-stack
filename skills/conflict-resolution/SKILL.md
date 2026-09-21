# Skill: Conflict Detection & Resolution

**Purpose:** Decide what happens when two disconnected sites edit the same record, and make that decision auditable.

**When to use:**
- Any deployment where more than one site writes the same entity
- After `sync-engine-setup`, which detects conflicts but does not resolve them
- When users report "my change disappeared after sync"

**Outputs:**
- ✅ Versioning strategy (optimistic lock)
- ✅ Resolution policies per entity: LWW, FWW, field-merge, manual
- ✅ Conflict queue + resolution UI contract
- ✅ Audit of every resolution

**Depends on:** `sync-engine-setup`

---

## The Problem

```
t0   Site A and Site B both hold invoice INV-042, version 3
t1   Network drops
t2   Site A sets amount = 1500        (local version 4)
t3   Site B sets status = 'paid'      (local version 4)
t4   Network returns, both push version 4

Server holds version 3. Two clients claim to be version 4.
One of them is wrong -- and picking the wrong one silently loses money.
```

Detection is cheap: compare the client's `version` against the server's. Resolution
is the hard part, and it is a **business decision, not a technical one**.

---

## Strategy Selection

Pick per entity, not per application. The wrong default is "last-write-wins everywhere".

| Strategy | Rule | Fits | Never use for |
|----------|------|------|---------------|
| **LWW** (last-write-wins) | Highest timestamp survives | Comments, drafts, notes | Money, stock levels |
| **FWW** (first-write-wins) | Server state is kept, client rejected | Immutable records, closed periods | Collaborative documents |
| **Field-merge** | Merge per field when edits do not overlap | Records with independent fields | Fields with invariants between them |
| **CRDT** | Structural auto-merge, no conflict possible | Lists, task boards, rich text | Anything requiring validation |
| **Manual** | Queued, a human decides | Invoices, payments, inventory | High-volume entities |

**Rule of thumb:** if getting it wrong costs money or breaks an accounting
invariant, use `manual`. Silence is worse than friction.

---

## Clock Caveat

LWW compares timestamps across machines that have been offline for days. Client
clocks drift, get reset, or are plain wrong. **Never trust a client timestamp for
resolution.**

```python
# Wrong: the client decides who wins by lying about its clock.
winner = max(candidates, key=lambda e: e['clientTimestamp'])

# Right: the server stamps arrival order; the client timestamp is data,
# useful for display and for debugging, never for arbitration.
event.server_received_at = timezone.now()
winner = max(candidates, key=lambda e: e.server_received_at)
```

A site that has been offline for a week legitimately pushes "old" edits. Arrival
order at the server is the only clock every participant shares.

---

## Configuration

```python
# settings.py
CONFLICT_RESOLUTION = {
    'invoice':   'manual',       # money -- a human decides
    'inventory': 'manual',       # stock levels must not be guessed
    'contact':   'field-merge',  # independent fields
    'note':      'lww',          # low stakes
    'task_list': 'crdt',         # see skills/crdt-integration
    'default':   'manual',       # fail safe, not fast
}
```

---

## Implementation

```python
# conflicts.py
from django.conf import settings
from django.db import transaction
from django.utils import timezone


class ConflictResolver:
    """Applies the configured strategy to a detected conflict."""

    def resolve(self, conflict):
        strategy = settings.CONFLICT_RESOLUTION.get(
            conflict.entity_type,
            settings.CONFLICT_RESOLUTION['default'],
        )
        handler = getattr(self, f'_resolve_{strategy.replace("-", "_")}')

        with transaction.atomic():
            outcome = handler(conflict)
            self._record(conflict, strategy, outcome)
        return outcome

    def _resolve_lww(self, conflict):
        # Server arrival order, never the client clock (see Clock Caveat).
        winner = (
            conflict.client_event
            if conflict.client_event.server_received_at
            > conflict.server_event.server_received_at
            else conflict.server_event
        )
        return self._apply(conflict, winner.data)

    def _resolve_fww(self, conflict):
        # Server state stands. The client must rebase and resubmit.
        return {'status': 'rejected', 'rebase_onto': conflict.server_event.data}

    def _resolve_field_merge(self, conflict):
        """Merge only where the two sides touched different fields.

        Any field both sides changed is a real conflict and is escalated --
        merging it would fabricate a state neither user ever saw.
        """
        base = conflict.base_data
        client, server = conflict.client_event.data, conflict.server_event.data

        merged, contested = dict(base), []
        for field in set(client) | set(server):
            client_changed = client.get(field) != base.get(field)
            server_changed = server.get(field) != base.get(field)

            if client_changed and server_changed:
                if client[field] != server[field]:
                    contested.append(field)
            elif client_changed:
                merged[field] = client[field]
            elif server_changed:
                merged[field] = server[field]

        if contested:
            return self._resolve_manual(conflict, contested_fields=contested)
        return self._apply(conflict, merged)

    def _resolve_manual(self, conflict, contested_fields=None):
        # Nothing is written. The record stays at the server version until a
        # human decides, and the client keeps its local edit intact.
        conflict.status = 'awaiting_review'
        conflict.contested_fields = contested_fields or []
        conflict.save(update_fields=['status', 'contested_fields'])
        return {'status': 'queued', 'conflict_id': str(conflict.id)}

    def _record(self, conflict, strategy, outcome):
        """A resolution that leaves no trace is indistinguishable from data loss."""
        AuditLog.objects.create(
            tenant=conflict.tenant,
            entity_type=conflict.entity_type,
            entity_id=conflict.entity_id,
            action='CONFLICT_RESOLVED',
            old_values={
                'client': conflict.client_event.data,
                'server': conflict.server_event.data,
            },
            new_values={'strategy': strategy, 'outcome': outcome},
        )
```

---

## Base Version Requirement

Field-merge needs the **common ancestor**, not just the two candidates. Without
it you cannot tell "B changed this field" from "B never touched it".

```python
# SyncEvent must carry the version the client started from.
base_version = models.IntegerField()   # client's version BEFORE its edit
version      = models.IntegerField()   # client's version AFTER its edit
```

Retain enough history to reconstruct `base_version`. This is the one thing the
90-day purge in `sync-engine-setup` must not delete out from under you: purge
synced events, keep the base snapshots of anything with an open conflict.

---

## Frontend Contract

```typescript
export interface ConflictResolution {
  conflictId: string;
  entityType: string;
  entityId: string;
  contestedFields: string[];
  local: Record<string, unknown>;
  remote: Record<string, unknown>;
  base: Record<string, unknown>;
}

// The UI shows all three columns. Showing only local vs remote forces the user
// to guess what they actually changed.
export async function resolveConflict(
  conflictId: string,
  choice: 'local' | 'remote' | Record<string, unknown>,
): Promise<void> {
  await fetch(`${API_BASE_URL}/api/conflicts/${conflictId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ choice }),
  });
}
```

Keep the local edit in the store, flagged `_hasConflict`, until the server
confirms resolution. Dropping it on detection is the most common way this
architecture loses user work.

---

## Testing

```python
def test_manual_strategy_writes_nothing(self):
    """A queued conflict must not mutate the record."""
    invoice = InvoiceFactory(amount=1000, version=3)

    conflict = self.make_conflict(
        entity_type='invoice',
        client_data={'amount': 1500, 'version': 4},
        server_data={'status': 'paid', 'version': 4},
    )
    outcome = ConflictResolver().resolve(conflict)

    invoice.refresh_from_db()
    self.assertEqual(outcome['status'], 'queued')
    self.assertEqual(invoice.amount, 1000)   # untouched
    self.assertEqual(invoice.version, 3)


def test_field_merge_escalates_overlapping_edits(self):
    """Two sites editing the same field is not mergeable."""
    conflict = self.make_conflict(
        entity_type='contact',
        base_data={'phone': '111', 'email': 'a@x.km'},
        client_data={'phone': '222', 'email': 'a@x.km'},
        server_data={'phone': '333', 'email': 'a@x.km'},
    )
    outcome = ConflictResolver().resolve(conflict)

    self.assertEqual(outcome['status'], 'queued')
```

---

## Operational Signals

Conflicts are a symptom. Track them:

- **Conflict rate per entity** — a spike means two sites share a workflow that assumes exclusivity
- **Time in `awaiting_review`** — a growing queue means nobody owns resolution
- **Resolutions per strategy** — heavy `manual` on a low-stakes entity means the config is too conservative

A healthy hybrid deployment has few conflicts, not a fast resolver.
