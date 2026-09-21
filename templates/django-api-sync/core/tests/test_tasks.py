"""Background jobs.

A Celery task has no HTTP request, so the tenant middleware never runs for it.
That made the retention purge match zero rows -- forever, without error. These
tests exist mostly to keep that from coming back.
"""

import uuid
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from core.models import SyncEvent
from core.tasks import purge_synced_events
from core.tests.base import TenantTestCase, sync_event

MANUAL = {'invoice': 'manual', 'default': 'manual'}


class PurgeTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.client_mor = self.api_client(self.mor_user)
        self.clear_tenant()

    def _push(self, entity_id, version, base_version, origin='web', **data):
        return self.sync(
            self.client_mor,
            'MOR',
            [sync_event(entity_id, version=version, base_version=base_version, **data)],
            origin=origin,
        ).json()

    def _age_all_events(self, days=200):
        """Push every event past any sane retention window."""
        self.set_tenant(self.mor)
        SyncEvent.objects.update(
            server_received_at=timezone.now() - timedelta(days=days)
        )
        self.clear_tenant()

    def test_purge_sees_tenant_data_at_all(self):
        """Regression: without a tenant context, RLS hid everything from it."""
        self._push(uuid.uuid4(), version=1, base_version=0, number='MOR-901')
        self._age_all_events()

        deleted = purge_synced_events()

        self.assertEqual(deleted, 1, 'the task matched nothing, as it did under RLS')

    def test_purge_spares_events_inside_the_window(self):
        self._push(uuid.uuid4(), version=1, base_version=0, number='MOR-901')

        deleted = purge_synced_events()

        self.assertEqual(deleted, 0)
        self.set_tenant(self.mor)
        self.assertEqual(SyncEvent.objects.count(), 1)

    def test_purge_covers_every_tenant(self):
        self._push(uuid.uuid4(), version=1, base_version=0, number='MOR-901')

        client_mut = self.api_client(self.mut_user)
        self.sync(
            client_mut,
            'MUT',
            [sync_event(uuid.uuid4(), version=1, base_version=0, number='MUT-901')],
            origin='web',
        )

        self.set_tenant(self.mut)
        SyncEvent.objects.update(server_received_at=timezone.now() - timedelta(days=200))
        self._age_all_events()

        self.assertEqual(purge_synced_events(), 2)

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_purge_keeps_what_an_open_conflict_needs(self):
        """The event a conflict is built on, and the ancestor a merge needs.

        Purge either and a resolvable conflict becomes a coin flip.
        """
        entity_id = uuid.uuid4()

        self._push(entity_id, version=1, base_version=0, number='MOR-900')
        self._push(entity_id, version=2, base_version=1, number='MOR-900', status='sent')
        body = self._push(
            entity_id, version=2, base_version=1,
            origin='site_a', number='MOR-900', status='paid',
        )
        self.assertEqual(body['conflicts'][0]['resolution'], 'queued')

        self._age_all_events()
        purge_synced_events()

        self.set_tenant(self.mor)
        surviving = SyncEvent.objects.filter(entity_id=str(entity_id))

        # The client's own event is status='conflict', never a purge target.
        self.assertTrue(
            surviving.filter(status='conflict').exists(),
            'the conflicting push was purged; the conflict can no longer be read',
        )
        # The ancestor the merge would compare against is version 1.
        self.assertTrue(
            surviving.filter(version=1, status='synced').exists(),
            'the common ancestor was purged; field-merge degrades to guesswork',
        )
