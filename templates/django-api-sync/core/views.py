"""API endpoints: health, auth, bidirectional sync, conflicts, invoices."""

import hashlib
import json
import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.conflicts import ConflictResolver
from core.models import Invoice, SyncConflict, SyncEvent
from core.serializers import (
    InvoiceSerializer,
    SyncConflictSerializer,
    SyncRequestSerializer,
    invoice_fields_from_payload,
)

logger = logging.getLogger(__name__)

# Events returned per sync call. Bounded on purpose: a site reconnecting after
# a long outage must not be handed an unbounded response it cannot parse.
SYNC_BATCH_SIZE = getattr(settings, 'SYNC_BATCH_SIZE', 500)


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    """Liveness probe. Reports the database separately from the process.

    An API that answers 200 while its database is unreachable is worse than one
    that answers 503: it keeps clients pushing changes into a void.
    """
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:  # noqa: BLE001 - the probe must never raise
        db_ok = False

    return Response(
        {
            'status': 'ok' if db_ok else 'degraded',
            'database': 'up' if db_ok else 'down',
            'serverTimestamp': int(timezone.now().timestamp()),
        },
        status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@api_view(['POST'])
def sync(request):
    """Bidirectional sync: push client changes, pull everything else.

    The exchange is symmetric even when the client has nothing to send -- a
    site that only reads still has to receive the other sites' work.
    """
    serializer = SyncRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data

    tenant = request.tenant
    origin = payload['origin']

    accepted, conflicts = [], []

    for event in payload['events']:
        outcome = _apply_event(request, tenant, event, origin)
        if outcome['conflict']:
            conflicts.append(outcome['conflict'])
        else:
            accepted.append(outcome['accepted'])

    new_events, cursor, has_more = _events_since(
        tenant, payload['lastSyncTimestamp'], origin
    )

    return Response(
        {
            'status': 'ok',
            'uploadedCount': len(accepted),
            'accepted': accepted,
            'newEvents': new_events,
            'conflicts': conflicts,
            # When the batch was truncated this is the last event's timestamp,
            # not the current time: advancing the cursor to "now" over a
            # truncated page would skip everything that did not fit.
            'serverTimestamp': cursor,
            'hasMore': has_more,
        }
    )


def _apply_event(request, tenant, event, origin):
    """Apply one client event under an optimistic lock."""
    entity_id = event['entityId']
    client_version = event['version']
    base_version = event['baseVersion']

    if event['entityType'] != 'invoice':
        raise NotImplementedError(
            f"No handler for entity type {event['entityType']!r}. "
            'Add one here as you add synced entities.'
        )

    # Each event is its own transaction: one conflicting invoice must not roll
    # back the twenty that synced cleanly alongside it.
    with transaction.atomic():
        invoice = (
            Invoice.objects.select_for_update()
            .filter(tenant=tenant, id=entity_id)
            .first()
        )

        if invoice is None:
            return _create_invoice(request, tenant, event, origin)

        if invoice.version != base_version:
            return {
                'accepted': None,
                'conflict': _record_conflict(
                    request, tenant, event, invoice, origin
                ),
            }

        fields = invoice_fields_from_payload(event['data'])
        for name, value in fields.items():
            setattr(invoice, name, value)
        invoice.version = base_version + 1
        invoice.synced_at = timezone.now()
        invoice.is_dirty = False
        invoice.save()

        _record_event(request, tenant, event, origin, 'synced', invoice.version)

        return {
            'accepted': {'entityId': str(invoice.id), 'version': invoice.version},
            'conflict': None,
        }


def _create_invoice(request, tenant, event, origin):
    fields = invoice_fields_from_payload(event['data'])
    invoice = Invoice.objects.create(
        id=event['entityId'],
        tenant=tenant,
        version=1,
        synced_at=timezone.now(),
        is_dirty=False,
        created_by=request.user if request.user.is_authenticated else None,
        **fields,
    )
    _record_event(request, tenant, event, origin, 'synced', invoice.version)
    return {
        'accepted': {'entityId': str(invoice.id), 'version': invoice.version},
        'conflict': None,
    }


def _record_conflict(request, tenant, event, invoice, origin):
    sync_event = _record_event(
        request, tenant, event, origin, 'conflict', event['version']
    )

    conflict = SyncConflict.objects.create(
        tenant=tenant,
        entity_type=event['entityType'],
        entity_id=event['entityId'],
        client_event=sync_event,
        server_state=InvoiceSerializer(invoice).data,
        base_data=_state_at_version(tenant, event['entityId'], event['baseVersion']),
        client_version=event['version'],
        server_version=invoice.version,
    )

    outcome = ConflictResolver().resolve(conflict)
    logger.info(
        'Conflict on %s %s: client v%s vs server v%s -> %s',
        event['entityType'],
        event['entityId'],
        event['version'],
        invoice.version,
        outcome['status'],
    )

    return {
        'entityId': event['entityId'],
        'clientVersion': event['version'],
        'serverVersion': invoice.version,
        'conflictId': str(conflict.id),
        'resolution': outcome['status'],
    }


def _state_at_version(tenant, entity_id, version):
    """Reconstruct the common ancestor from the event log, when still retained.

    Returns None once the purge has removed it -- field-merge then degrades to
    a manual decision rather than merging against a state it has to guess.
    """
    event = (
        SyncEvent.objects.filter(
            tenant=tenant, entity_id=entity_id, version=version, status='synced'
        )
        .order_by('-server_received_at')
        .first()
    )
    return event.data if event else None


def _record_event(request, tenant, event, origin, event_status, version):
    """Persist the event, keyed by a content hash so retries are idempotent.

    A client that loses the response and retries must not create a second
    event: the hash makes the same push land on the same row.
    """
    digest = hashlib.sha256(
        json.dumps(
            {
                'tenant': str(tenant.id),
                'entityType': event['entityType'],
                'entityId': event['entityId'],
                'version': event['version'],
                'data': event['data'],
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()

    sync_event, _ = SyncEvent.objects.get_or_create(
        hash=digest,
        defaults={
            'tenant': tenant,
            'entity_type': event['entityType'],
            'entity_id': event['entityId'],
            'operation': event['operation'],
            'data': event['data'],
            'version': version,
            'base_version': event['baseVersion'],
            'origin': origin,
            'status': event_status,
            'synced_at': timezone.now() if event_status == 'synced' else None,
            'created_by': request.user if request.user.is_authenticated else None,
        },
    )
    return sync_event


def _events_since(tenant, last_sync_timestamp, origin):
    """Everything this origin has not seen yet.

    Excluding the caller's own origin avoids echoing a client's writes straight
    back at it, which would bump versions in a loop.

    Returns (events, cursor, has_more). A site reconnecting after weeks offline
    can be thousands of events behind, so the batch is capped -- and the cursor
    it returns must then point at the last event actually sent, or the client
    would resume past everything it never received.
    """
    cutoff = datetime.fromtimestamp(last_sync_timestamp, tz=dt_timezone.utc)

    queryset = (
        SyncEvent.objects.filter(
            tenant=tenant, status='synced', server_received_at__gt=cutoff
        )
        .exclude(origin=origin)
        .order_by('server_received_at')
    )

    # One extra row tells us whether more remain, without a second COUNT query.
    rows = list(queryset[: SYNC_BATCH_SIZE + 1])
    has_more = len(rows) > SYNC_BATCH_SIZE
    rows = rows[:SYNC_BATCH_SIZE]

    if has_more and rows:
        boundary = rows[-1].server_received_at

        # Rows sharing the boundary timestamp are pulled in even though they
        # exceed the cap. Left out, the next call would have to ask for
        # `> boundary` and would never see them, or ask for `>= boundary` and
        # replay this page forever.
        seen = {row.id for row in rows}
        rows.extend(
            row
            for row in queryset.filter(server_received_at=boundary)
            if row.id not in seen
        )

        # Full sub-second precision. Truncating to whole seconds makes the next
        # request's `> cutoff` match the very event the cursor points at, and
        # the client loops on the same page indefinitely.
        cursor = boundary.timestamp()
    else:
        cursor = timezone.now().timestamp()

    events = [
        {
            'entityType': event.entity_type,
            'entityId': event.entity_id,
            'operation': event.operation,
            'version': event.version,
            'data': event.data,
        }
        for event in rows
    ]

    return events, cursor, has_more


@api_view(['GET'])
def list_invoices(request):
    invoices = Invoice.objects.filter(tenant=request.tenant).order_by('-created_at')
    return Response(InvoiceSerializer(invoices, many=True).data)


@api_view(['GET'])
def list_conflicts(request):
    conflicts = SyncConflict.objects.filter(
        tenant=request.tenant, status='awaiting_review'
    ).select_related('client_event').order_by('-created_at')
    return Response(SyncConflictSerializer(conflicts, many=True).data)


@api_view(['POST'])
def resolve_conflict(request, conflict_id):
    """Apply a human decision to a queued conflict."""
    conflict = SyncConflict.objects.filter(
        tenant=request.tenant, id=conflict_id, status='awaiting_review'
    ).first()

    if conflict is None:
        return Response(
            {'detail': 'Conflict not found or already resolved.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    choice = request.data.get('choice')
    if choice not in ('local', 'remote') and not isinstance(choice, dict):
        return Response(
            {'detail': "choice must be 'local', 'remote', or an object of field values."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    outcome = ConflictResolver().apply_manual_choice(conflict, choice, request.user)
    return Response(outcome)
