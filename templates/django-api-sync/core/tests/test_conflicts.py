"""Conflict detection and the resolution strategies.

The point of the conflict machinery is that it refuses to guess. Most of these
tests assert that nothing was written.
"""

import uuid

from django.test import override_settings

from core.models import AuditLog, Invoice, SyncConflict
from core.tests.base import TenantTestCase, sync_event

MANUAL = {'invoice': 'manual', 'default': 'manual'}
LWW = {'invoice': 'lww', 'default': 'manual'}
FIELD_MERGE = {'invoice': 'field-merge', 'default': 'manual'}


class ConflictDetectionTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.client_mor = self.api_client(self.mor_user)
        self.entity_id = uuid.uuid4()
        self.clear_tenant()

        # v1 from one site, then v2 from another: the server is now ahead of
        # anyone still holding v1.
        self.sync(
            self.client_mor,
            'MOR',
            [sync_event(self.entity_id, version=1, base_version=0, number='MOR-900')],
            origin='web',
        )
        self.sync(
            self.client_mor,
            'MOR',
            [
                sync_event(
                    self.entity_id, version=2, base_version=1,
                    number='MOR-900', status='sent',
                )
            ],
            origin='web',
        )

    def _stale_push(self, **data):
        """A push from a site that never saw v2."""
        return self.sync(
            self.client_mor,
            'MOR',
            [
                sync_event(
                    self.entity_id, version=2, base_version=1,
                    number='MOR-900', **data,
                )
            ],
            origin='site_a',
        ).json()

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_stale_push_is_queued_and_writes_nothing(self):
        body = self._stale_push(status='paid', amount=9999)

        self.assertEqual(body['accepted'], [])
        self.assertEqual(len(body['conflicts']), 1)
        self.assertEqual(body['conflicts'][0]['resolution'], 'queued')

        self.set_tenant(self.mor)
        invoice = Invoice.objects.get(id=self.entity_id)
        self.assertEqual(invoice.status, 'sent', 'server state was overwritten')
        self.assertEqual(invoice.amount, 100, 'server amount was overwritten')
        self.assertEqual(invoice.version, 2, 'version moved on a queued conflict')

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_queued_conflict_exposes_local_remote_and_base(self):
        """Showing only local vs remote makes the reviewer guess what changed."""
        self._stale_push(status='paid', amount=9999)

        response = self.client_mor.get('/api/conflicts/', HTTP_X_TENANT='MOR')
        conflict = response.json()[0]

        self.assertEqual(conflict['status'], 'awaiting_review')
        self.assertEqual(conflict['local']['status'], 'paid')
        self.assertEqual(conflict['remote']['status'], 'sent')
        self.assertEqual(conflict['base']['status'], 'draft')

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_manual_resolution_applies_the_chosen_side(self):
        body = self._stale_push(status='paid', amount=9999)
        conflict_id = body['conflicts'][0]['conflictId']

        response = self.client_mor.post(
            f'/api/conflicts/{conflict_id}/resolve',
            {'choice': 'local'},
            format='json',
            HTTP_X_TENANT='MOR',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'applied')

        self.set_tenant(self.mor)
        invoice = Invoice.objects.get(id=self.entity_id)
        self.assertEqual(invoice.status, 'paid')
        self.assertEqual(invoice.amount, 9999)
        self.assertEqual(invoice.version, 3)
        self.assertEqual(
            SyncConflict.objects.filter(status='awaiting_review').count(), 0
        )

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_resolving_twice_is_refused(self):
        body = self._stale_push(status='paid')
        conflict_id = body['conflicts'][0]['conflictId']
        url = f'/api/conflicts/{conflict_id}/resolve'

        self.client_mor.post(url, {'choice': 'local'}, format='json', HTTP_X_TENANT='MOR')
        second = self.client_mor.post(
            url, {'choice': 'remote'}, format='json', HTTP_X_TENANT='MOR'
        )

        self.assertEqual(second.status_code, 404)

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_a_queued_conflict_is_not_logged_as_resolved(self):
        """The audit trail must not claim an outcome that never happened."""
        self._stale_push(status='paid')

        self.set_tenant(self.mor)
        actions = set(AuditLog.objects.values_list('action', flat=True))

        self.assertIn('CONFLICT_DETECTED', actions)
        self.assertNotIn('CONFLICT_RESOLVED', actions)

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_resolution_is_audited_with_both_sides(self):
        body = self._stale_push(status='paid', amount=9999)
        conflict_id = body['conflicts'][0]['conflictId']

        self.client_mor.post(
            f'/api/conflicts/{conflict_id}/resolve',
            {'choice': 'local'},
            format='json',
            HTTP_X_TENANT='MOR',
        )

        self.set_tenant(self.mor)
        entry = AuditLog.objects.filter(action='CONFLICT_RESOLVED').first()

        self.assertIsNotNone(entry, 'a resolution that leaves no trace is data loss')
        self.assertEqual(entry.old_values['client']['status'], 'paid')
        self.assertEqual(entry.old_values['server']['status'], 'sent')
        self.assertEqual(entry.new_values['strategy'], 'manual:local')


class StrategyTests(TenantTestCase):
    """Strategies other than the default, driven through real history."""

    def setUp(self):
        super().setUp()
        self.client_mor = self.api_client(self.mor_user)
        self.entity_id = uuid.uuid4()
        self.clear_tenant()

        self.sync(
            self.client_mor,
            'MOR',
            [
                sync_event(
                    self.entity_id, version=1, base_version=0,
                    number='MOR-900', status='draft', amount=100,
                )
            ],
            origin='web',
        )

    def _push_from_v1(self, origin, **data):
        """A push built on v1, from `origin`. Unnamed fields keep their v1 value."""
        payload = {'number': 'MOR-900', 'status': 'draft', 'amount': 100, **data}
        return self.sync(
            self.client_mor,
            'MOR',
            [sync_event(self.entity_id, version=2, base_version=1, **payload)],
            origin=origin,
        ).json()

    def _server_moves_to(self, **data):
        return self._push_from_v1('web', **data)

    def _stale_push(self, **data):
        """A site that never saw v2 pushing its own v2."""
        return self._push_from_v1('site_a', **data)

    @override_settings(CONFLICT_RESOLUTION=LWW)
    def test_lww_applies_the_client_state(self):
        self._server_moves_to(status='sent')
        body = self._stale_push(status='paid')

        self.assertEqual(body['conflicts'][0]['resolution'], 'applied')

        self.set_tenant(self.mor)
        invoice = Invoice.objects.get(id=self.entity_id)
        self.assertEqual(invoice.status, 'paid')

    @override_settings(CONFLICT_RESOLUTION=FIELD_MERGE)
    def test_field_merge_keeps_both_disjoint_edits(self):
        """One side moved the status, the other the amount. Both should stand."""
        self._server_moves_to(status='sent')
        body = self._stale_push(amount=250)

        self.assertEqual(body['conflicts'][0]['resolution'], 'applied')

        self.set_tenant(self.mor)
        invoice = Invoice.objects.get(id=self.entity_id)
        self.assertEqual(invoice.status, 'sent', 'the server-side edit was lost')
        self.assertEqual(invoice.amount, 250, 'the client-side edit was lost')

    @override_settings(CONFLICT_RESOLUTION=FIELD_MERGE)
    def test_field_merge_escalates_overlapping_edits(self):
        """Two sites editing the same field is not mergeable.

        Merging it would fabricate a state neither user ever saw.
        """
        self._server_moves_to(status='sent')
        body = self._stale_push(status='paid')

        self.assertEqual(body['conflicts'][0]['resolution'], 'queued')

        self.set_tenant(self.mor)
        self.assertEqual(Invoice.objects.get(id=self.entity_id).status, 'sent')
