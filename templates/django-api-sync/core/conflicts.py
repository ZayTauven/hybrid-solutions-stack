"""Conflict resolution strategies.

Reference and rationale: skills/conflict-resolution/SKILL.md.
The strategy per entity type is configured in settings.CONFLICT_RESOLUTION.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import AuditLog, Invoice, SyncEvent
from core.serializers import invoice_fields_from_payload

logger = logging.getLogger(__name__)


class ConflictResolver:
    def resolve(self, conflict):
        strategy = settings.CONFLICT_RESOLUTION.get(
            conflict.entity_type, settings.CONFLICT_RESOLUTION['default']
        )
        handler = getattr(self, f'_resolve_{strategy.replace("-", "_")}', None)
        if handler is None:
            logger.error(
                'Unknown conflict strategy %r for %s; falling back to manual.',
                strategy,
                conflict.entity_type,
            )
            handler = self._resolve_manual

        with transaction.atomic():
            outcome = handler(conflict)
            self._record(conflict, strategy, outcome)
        return outcome

    # -- strategies ---------------------------------------------------------

    def _resolve_lww(self, conflict):
        """Last write wins, arbitrated on server arrival order.

        Never on a client timestamp: a site offline for a week legitimately
        pushes old edits, and a drifted clock would decide the outcome.
        """
        return self._apply(conflict, conflict.client_event.data)

    def _resolve_fww(self, conflict):
        # Server state stands; the client must rebase and resubmit.
        conflict.status = 'rejected'
        conflict.resolved_at = timezone.now()
        conflict.save(update_fields=['status', 'resolved_at'])
        return {'status': 'rejected', 'rebase_onto': conflict.server_state}

    def _resolve_field_merge(self, conflict):
        """Merge only where the two sides touched different fields.

        Any field both sides changed is escalated: merging it would fabricate a
        state neither user ever saw.
        """
        base = conflict.base_data
        if base is None:
            # No common ancestor retained, so "changed" cannot be distinguished
            # from "left alone". Guessing here silently rewrites data.
            return self._resolve_manual(conflict)

        client = conflict.client_event.data
        server = self._server_snapshot(conflict)
        if server is None:
            # The server state did not come from a sync push -- a seeded row, a
            # fix through the admin -- so there is no client-shaped snapshot to
            # compare against. Declaring every field changed would escalate
            # anyway; saying so plainly is better than inferring it.
            return self._resolve_manual(conflict)

        merged, contested = dict(base), []
        for field in set(client) | set(server):
            if field.startswith('_'):
                continue  # client-side sync metadata, not business data

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

    # -- manual resolution --------------------------------------------------

    def apply_manual_choice(self, conflict, choice, user):
        """Apply a reviewer's decision to a queued conflict."""
        if choice == 'remote':
            data = conflict.server_state
        elif choice == 'local':
            data = conflict.client_event.data
        else:
            data = {**conflict.server_state, **choice}

        with transaction.atomic():
            outcome = self._apply(conflict, data)
            conflict.status = 'resolved'
            conflict.resolved_at = timezone.now()
            conflict.resolved_by = user if user.is_authenticated else None
            conflict.save(update_fields=['status', 'resolved_at', 'resolved_by'])
            self._record(conflict, f'manual:{choice if isinstance(choice, str) else "merge"}', outcome)

        return outcome

    # -- helpers ------------------------------------------------------------

    def _server_snapshot(self, conflict):
        """The server's current state, in the shape clients speak.

        `conflict.server_state` is the serializer's output, kept for display.
        It is the wrong basis for a field-by-field comparison: DRF renders a
        Decimal as the string "100.00" while the client sent the number 100, so
        every amount reads as changed on both sides and a perfectly mergeable
        conflict escalates. Comparing three client-shaped snapshots -- base,
        client, and the event that produced the server's current version --
        removes the mismatch by construction.
        """
        event = (
            SyncEvent.objects.filter(
                tenant=conflict.tenant,
                entity_type=conflict.entity_type,
                entity_id=conflict.entity_id,
                version=conflict.server_version,
                status='synced',
            )
            .order_by('-server_received_at')
            .first()
        )
        return event.data if event else None

    def _apply(self, conflict, data):
        if conflict.entity_type != 'invoice':
            raise NotImplementedError(
                f'No writer for entity type {conflict.entity_type!r}.'
            )

        invoice = Invoice.objects.select_for_update().get(
            tenant=conflict.tenant, id=conflict.entity_id
        )
        for name, value in invoice_fields_from_payload(data).items():
            setattr(invoice, name, value)

        invoice.version += 1
        invoice.synced_at = timezone.now()
        invoice.is_dirty = False
        invoice.save()

        return {
            'status': 'applied',
            'entityId': str(invoice.id),
            'version': invoice.version,
        }

    def _record(self, conflict, strategy, outcome):
        """A resolution that leaves no trace is indistinguishable from data loss."""
        # A queued conflict has decided nothing yet. Logging it as resolved
        # would make the audit trail claim an outcome that never happened.
        action = (
            'CONFLICT_DETECTED' if outcome['status'] == 'queued' else 'CONFLICT_RESOLVED'
        )

        AuditLog.objects.create(
            tenant=conflict.tenant,
            user=conflict.resolved_by,
            entity_type=conflict.entity_type,
            entity_id=conflict.entity_id,
            action=action,
            old_values={
                'client': conflict.client_event.data,
                'server': conflict.server_state,
            },
            new_values={'strategy': strategy, 'outcome': outcome},
        )
