"""Background jobs.

Runs under the Celery worker/beat services defined in docker-compose.yml.

Every task here touches tenant-scoped tables, which means it must set the RLS
context itself. A background job has no HTTP request, so the tenant middleware
never runs for it: without an explicit context the queries match zero rows and
the job silently does nothing, forever.
"""

import logging
from contextlib import contextmanager
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.models import SyncConflict, SyncEvent, Tenant

logger = logging.getLogger(__name__)


@contextmanager
def tenant_context(tenant_id):
    """Scope the RLS context to one tenant for the duration of a transaction."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_tenant_id', %s, true)",
                [str(tenant_id)],
            )
        yield


@shared_task
def purge_synced_events():
    """Drop synced events past the retention window, tenant by tenant.

    Two exclusions matter. Events tied to an open conflict are the only record
    of what the client sent, and events matching an open conflict's base
    version are the common ancestor a field-merge needs. Purging either turns a
    resolvable conflict into a coin flip.
    """
    cutoff = timezone.now() - timedelta(days=settings.SYNC_AUTO_PURGE_SYNCED_AFTER_DAYS)
    total = 0

    # The tenants table carries no RLS policy, so it is readable without a
    # context -- which is what makes iterating them possible at all.
    for tenant_id in Tenant.objects.values_list('id', flat=True):
        with tenant_context(tenant_id):
            total += _purge_for_current_tenant(cutoff)

    logger.info('Purged %s sync events older than %s', total, cutoff.date())
    return total


def _purge_for_current_tenant(cutoff):
    open_conflicts = SyncConflict.objects.filter(status='awaiting_review')
    protected_event_ids = set(open_conflicts.values_list('client_event_id', flat=True))

    protected_ancestors = Q()
    for entity_id, base_version in open_conflicts.values_list(
        'entity_id', 'client_event__base_version'
    ):
        protected_ancestors |= Q(entity_id=entity_id, version=base_version)

    queryset = SyncEvent.objects.filter(status='synced', server_received_at__lt=cutoff)
    queryset = queryset.exclude(id__in=protected_event_ids)
    if protected_ancestors:
        queryset = queryset.exclude(protected_ancestors)

    deleted, _ = queryset.delete()
    return deleted
