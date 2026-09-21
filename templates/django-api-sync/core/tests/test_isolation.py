"""Multi-tenant isolation, at the database and at the API.

The isolation guarantee is the product. It is also the kind of guarantee that
breaks silently: a misconfigured role or a table added without a policy leaks
everything and nothing raises. Hence this file.
"""

import uuid

from django.db import Error as DatabaseError, connection, transaction

from core.models import Invoice
from core.tests.base import TenantTestCase


class DatabaseIsolationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.make_invoice(self.mor, 'MOR-001')
        self.make_invoice(self.mut, 'MUT-001')

    def test_tenant_reads_only_its_own_rows(self):
        self.set_tenant(self.mor)
        self.assertEqual(
            list(Invoice.objects.values_list('number', flat=True)), ['MOR-001']
        )

        self.set_tenant(self.mut)
        self.assertEqual(
            list(Invoice.objects.values_list('number', flat=True)), ['MUT-001']
        )

    def test_no_tenant_context_sees_nothing(self):
        """Fail-closed. An unset context must not mean "see everything"."""
        self.clear_tenant()
        self.assertEqual(Invoice.objects.count(), 0)

    def test_writing_for_another_tenant_is_rejected(self):
        """USING doubles as WITH CHECK, so the policy blocks writes too."""
        self.set_tenant(self.mut)

        with self.assertRaises(DatabaseError), transaction.atomic():
            Invoice.objects.create(
                tenant=self.mor,
                number='FRAUD-001',
                amount=999,
                due_date='2026-12-31',
            )

    def test_updating_another_tenants_row_matches_nothing(self):
        """An UPDATE cannot reach a row the policy hides, so it affects zero."""
        self.set_tenant(self.mut)
        updated = Invoice.objects.filter(number='MOR-001').update(amount=1)
        self.assertEqual(updated, 0)

    def test_application_role_cannot_bypass_rls(self):
        """The guarantee rests on the connecting role, so assert its shape.

        A superuser or a BYPASSRLS role turns every policy above into
        decoration, and nothing else in the suite would notice.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user'
            )
            is_superuser, bypasses_rls = cursor.fetchone()

        self.assertFalse(is_superuser, 'Tests run as a superuser: RLS is not being enforced.')
        self.assertFalse(bypasses_rls, 'Test role has BYPASSRLS: RLS is not being enforced.')

    def test_audit_trail_cannot_be_rewritten(self):
        """A log the application can edit proves nothing."""
        self.set_tenant(self.mor)
        Invoice.objects.filter(number='MOR-001').update(status='paid')

        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM audit_logs')

    def test_audit_entries_are_scoped_to_their_tenant(self):
        self.set_tenant(self.mor)
        Invoice.objects.filter(number='MOR-001').update(status='sent')

        with connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM audit_logs')
            mor_entries = cursor.fetchone()[0]

        self.set_tenant(self.mut)
        with connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM audit_logs')
            mut_entries = cursor.fetchone()[0]

        self.assertGreater(mor_entries, 0)
        self.assertEqual(mut_entries, 1, 'MUT should see only its own seeded invoice')


class ApiIsolationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.make_invoice(self.mor, 'MOR-001')
        self.make_invoice(self.mut, 'MUT-001')
        self.clear_tenant()

    def test_member_reads_its_tenant(self):
        client = self.api_client(self.mor_user)
        response = client.get('/api/invoices/', HTTP_X_TENANT='MOR')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['number'] for row in response.json()], ['MOR-001'])

    def test_non_member_tenant_is_indistinguishable_from_unknown(self):
        """Both answer 404.

        Telling a caller that a tenant exists but is not theirs leaks the
        customer list one probe at a time.
        """
        client = self.api_client(self.mor_user)

        forbidden = client.get('/api/invoices/', HTTP_X_TENANT='MUT')
        unknown = client.get('/api/invoices/', HTTP_X_TENANT='NOPE')

        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(forbidden.json(), unknown.json())

    def test_missing_tenant_header_is_rejected(self):
        client = self.api_client(self.mor_user)
        response = client.get('/api/invoices/')
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_request_is_rejected(self):
        from rest_framework.test import APIClient

        response = APIClient().get('/api/invoices/', HTTP_X_TENANT='MOR')
        self.assertEqual(response.status_code, 401)

    def test_health_needs_neither_tenant_nor_token(self):
        from rest_framework.test import APIClient

        response = APIClient().get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['database'], 'up')

    def test_sync_cannot_write_for_another_tenant(self):
        """The tenant comes from the verified header, not from the payload."""
        from core.tests.base import sync_event

        client = self.api_client(self.mor_user)
        entity_id = uuid.uuid4()

        response = self.sync(
            client, 'MOR', [sync_event(entity_id, version=1, base_version=0, number='MOR-900')]
        )
        self.assertEqual(response.status_code, 200)

        self.set_tenant(self.mut)
        self.assertFalse(Invoice.objects.filter(id=entity_id).exists())

        self.set_tenant(self.mor)
        self.assertTrue(Invoice.objects.filter(id=entity_id).exists())
