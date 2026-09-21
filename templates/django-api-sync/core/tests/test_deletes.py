"""Deletion propagation.

A deletion is an edit like any other. It has to survive until it is pushed,
reach the other sites, and lose to a conflict when someone else edited the
record in the meantime.
"""

import uuid

from django.test import override_settings

from core.models import Invoice
from core.tests.base import TenantTestCase, sync_event

MANUAL = {'invoice': 'manual', 'default': 'manual'}


def delete_event(entity_id, version, base_version):
    event = sync_event(entity_id, version=version, base_version=base_version)
    event['operation'] = 'DELETE'
    return event


class DeletePropagationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.client_mor = self.api_client(self.mor_user)
        self.entity_id = uuid.uuid4()
        self.clear_tenant()

        self.sync(
            self.client_mor,
            'MOR',
            [sync_event(self.entity_id, version=1, base_version=0, number='MOR-900')],
            origin='web',
        )

    def _delete(self, version=2, base_version=1, origin='web'):
        return self.sync(
            self.client_mor,
            'MOR',
            [delete_event(self.entity_id, version, base_version)],
            origin=origin,
        ).json()

    def test_delete_is_accepted_and_soft_deletes_the_row(self):
        body = self._delete()

        self.assertEqual(body['accepted'], [{'entityId': str(self.entity_id), 'version': 2}])
        self.assertEqual(body['conflicts'], [])

        self.set_tenant(self.mor)
        invoice = Invoice.objects.get(id=self.entity_id)
        self.assertIsNotNone(invoice.deleted_at)
        self.assertEqual(invoice.version, 2)

    def test_deleted_invoice_disappears_from_the_list(self):
        self._delete()

        response = self.client_mor.get('/api/invoices/', HTTP_X_TENANT='MOR')
        self.assertEqual(response.json(), [])

    def test_other_sites_receive_the_deletion(self):
        """Without this the record lingers forever on every other device."""
        self._delete(origin='web')

        body = self.sync(self.client_mor, 'MOR', [], origin='site_a').json()
        operations = [(e['entityId'], e['operation']) for e in body['newEvents']]

        self.assertIn((str(self.entity_id), 'DELETE'), operations)

    def test_deleting_a_record_the_server_never_had_is_accepted(self):
        """The client must be able to drop its tombstone, not retry forever."""
        unknown = uuid.uuid4()

        body = self.sync(
            self.client_mor, 'MOR', [delete_event(unknown, version=2, base_version=1)]
        ).json()

        self.assertEqual(body['conflicts'], [])
        self.assertEqual(body['accepted'], [{'entityId': str(unknown), 'version': 2}])

    def test_deleting_twice_does_not_bump_the_version_again(self):
        self._delete()

        second = self.sync(
            self.client_mor,
            'MOR',
            [delete_event(self.entity_id, version=3, base_version=2)],
            origin='site_b',
        ).json()

        self.assertEqual(second['conflicts'], [])

        self.set_tenant(self.mor)
        self.assertEqual(Invoice.objects.get(id=self.entity_id).version, 2)

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_deleting_a_record_edited_elsewhere_is_a_conflict(self):
        """Silently destroying someone's unseen edit is the worst outcome here."""
        self.sync(
            self.client_mor,
            'MOR',
            [
                sync_event(
                    self.entity_id, version=2, base_version=1,
                    number='MOR-900', status='paid',
                )
            ],
            origin='web',
        )

        body = self._delete(version=2, base_version=1, origin='site_a')

        self.assertEqual(body['accepted'], [])
        self.assertEqual(body['conflicts'][0]['resolution'], 'queued')

        self.set_tenant(self.mor)
        invoice = Invoice.objects.get(id=self.entity_id)
        self.assertIsNone(invoice.deleted_at, 'the record was destroyed despite the conflict')
        self.assertEqual(invoice.status, 'paid')

    @override_settings(CONFLICT_RESOLUTION=MANUAL)
    def test_editing_a_record_deleted_elsewhere_is_a_conflict(self):
        self._delete(origin='web')

        body = self.sync(
            self.client_mor,
            'MOR',
            [
                sync_event(
                    self.entity_id, version=2, base_version=1,
                    number='MOR-900', status='paid',
                )
            ],
            origin='site_a',
        ).json()

        self.assertEqual(body['accepted'], [])
        self.assertEqual(len(body['conflicts']), 1)
