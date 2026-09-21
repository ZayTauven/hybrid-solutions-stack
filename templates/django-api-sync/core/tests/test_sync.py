"""The bidirectional sync endpoint."""

import uuid

from django.test import override_settings

from core.models import Invoice, SyncEvent
from core.tests.base import TenantTestCase, sync_event


class SyncPushTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.client_mor = self.api_client(self.mor_user)
        self.clear_tenant()

    def test_create_is_accepted_at_version_one(self):
        entity_id = uuid.uuid4()
        response = self.sync(
            self.client_mor,
            'MOR',
            [sync_event(entity_id, version=1, base_version=0, number='MOR-900')],
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['uploadedCount'], 1)
        self.assertEqual(body['accepted'], [{'entityId': str(entity_id), 'version': 1}])
        self.assertEqual(body['conflicts'], [])

        self.set_tenant(self.mor)
        invoice = Invoice.objects.get(id=entity_id)
        self.assertEqual(invoice.number, 'MOR-900')
        self.assertEqual(invoice.version, 1)
        self.assertFalse(invoice.is_dirty)

    def test_update_on_matching_base_version_is_accepted(self):
        invoice = self.make_invoice(self.mor, 'MOR-001')
        self.clear_tenant()

        response = self.sync(
            self.client_mor,
            'MOR',
            [
                sync_event(
                    invoice.id, version=2, base_version=1,
                    number='MOR-001', status='paid', amount=250,
                )
            ],
        )

        self.assertEqual(response.json()['accepted'][0]['version'], 2)

        self.set_tenant(self.mor)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'paid')
        self.assertEqual(invoice.version, 2)

    def test_replaying_the_same_push_is_idempotent(self):
        """A client that loses the response and retries must not double-log.

        The event is keyed by a content hash precisely so the retry lands on
        the same row.
        """
        entity_id = uuid.uuid4()
        event = sync_event(entity_id, version=1, base_version=0, number='MOR-900')

        self.sync(self.client_mor, 'MOR', [event])
        self.sync(self.client_mor, 'MOR', [event])

        self.set_tenant(self.mor)
        self.assertEqual(SyncEvent.objects.filter(entity_id=str(entity_id)).count(), 1)

    def test_replaying_a_push_returns_its_acceptance_not_a_conflict(self):
        """Losing a response must not cost the user a manual conflict.

        The record is one version ahead of the base version the client is
        still sending, so the optimistic lock would flag its own successful
        write as a clash.
        """
        entity_id = uuid.uuid4()
        event = sync_event(entity_id, version=1, base_version=0, number='MOR-900')

        first = self.sync(self.client_mor, 'MOR', [event]).json()
        replay = self.sync(self.client_mor, 'MOR', [event]).json()

        self.assertEqual(replay['conflicts'], [])
        self.assertEqual(replay['accepted'], first['accepted'])

    def test_replaying_an_update_returns_its_acceptance(self):
        invoice = self.make_invoice(self.mor, 'MOR-001')
        self.clear_tenant()
        event = sync_event(
            invoice.id, version=2, base_version=1, number='MOR-001', status='paid'
        )

        first = self.sync(self.client_mor, 'MOR', [event]).json()
        replay = self.sync(self.client_mor, 'MOR', [event]).json()

        self.assertEqual(replay['conflicts'], [])
        self.assertEqual(replay['accepted'], first['accepted'])

        self.set_tenant(self.mor)
        invoice.refresh_from_db()
        self.assertEqual(invoice.version, 2, 'the replay must not bump the version again')

    def test_unknown_status_is_refused(self):
        entity_id = uuid.uuid4()
        response = self.sync(
            self.client_mor,
            'MOR',
            [sync_event(entity_id, version=1, base_version=0, status='banana')],
        )
        self.assertEqual(response.status_code, 400)

    def test_base_version_must_precede_version(self):
        entity_id = uuid.uuid4()
        event = sync_event(entity_id, version=1, base_version=0)
        event['baseVersion'] = 5

        response = self.sync(self.client_mor, 'MOR', [event])
        self.assertEqual(response.status_code, 400)


class SyncPullTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.client_mor = self.api_client(self.mor_user)
        self.clear_tenant()

    def _push(self, number, origin='web'):
        entity_id = uuid.uuid4()
        self.sync(
            self.client_mor,
            'MOR',
            [sync_event(entity_id, version=1, base_version=0, number=number)],
            origin=origin,
        )
        return entity_id

    def test_pull_returns_changes_from_other_origins(self):
        self._push('MOR-901', origin='web')

        response = self.sync(self.client_mor, 'MOR', [], origin='site_a')
        numbers = [event['data']['number'] for event in response.json()['newEvents']]

        self.assertEqual(numbers, ['MOR-901'])

    def test_pull_does_not_echo_the_callers_own_writes(self):
        """Echoing them back would bump versions in a loop."""
        self._push('MOR-901', origin='web')

        response = self.sync(self.client_mor, 'MOR', [], origin='web')
        self.assertEqual(response.json()['newEvents'], [])

    def test_pull_is_scoped_to_the_tenant(self):
        self._push('MOR-901', origin='web')

        client_mut = self.api_client(self.mut_user)
        response = self.sync(client_mut, 'MUT', [], origin='site_a')

        self.assertEqual(response.json()['newEvents'], [])

    @override_settings(SYNC_BATCH_SIZE=1)
    def test_truncated_batches_resume_without_loss_or_repeat(self):
        """Regression: the cursor used to strand a client on one page forever.

        Truncated responses returned the last event's timestamp rounded to a
        whole second, so the next request's `> cutoff` matched that same event
        again. Before that, the cursor advanced to "now" over a truncated page
        and silently skipped everything that did not fit.
        """
        expected = ['MOR-901', 'MOR-902', 'MOR-903']
        for number in expected:
            self._push(number, origin='web')

        seen, cursor, calls = [], 0, 0
        while calls < 10:
            calls += 1
            body = self.sync(self.client_mor, 'MOR', [], last_sync=cursor, origin='site_a').json()
            seen.extend(event['data']['number'] for event in body['newEvents'])
            cursor = body['serverTimestamp']
            if not body['hasMore']:
                break

        self.assertFalse(body['hasMore'], 'catch-up never terminated')
        self.assertEqual(seen, expected, 'pages were skipped, repeated or reordered')
        self.assertEqual(len(seen), len(set(seen)), 'an event was delivered twice')

    def test_cursor_advances_past_delivered_events(self):
        self._push('MOR-901', origin='web')

        first = self.sync(self.client_mor, 'MOR', [], last_sync=0, origin='site_a').json()
        self.assertEqual(len(first['newEvents']), 1)

        second = self.sync(
            self.client_mor, 'MOR', [], last_sync=first['serverTimestamp'], origin='site_a'
        ).json()
        self.assertEqual(second['newEvents'], [])
