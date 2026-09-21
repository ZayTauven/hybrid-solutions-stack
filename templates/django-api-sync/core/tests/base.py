"""Shared fixtures for tests that run against real row-level security.

These tests are only meaningful because migration 0002 installs the policies
into the test database too. Run them against a database without it and they
pass while proving nothing.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Invoice, Tenant, TenantMembership

MOR_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')
MUT_ID = uuid.UUID('22222222-2222-2222-2222-222222222222')


class TenantTestCase(TestCase):
    """Two tenants, one user each, and helpers to switch the RLS context.

    Two tenants rather than one on purpose: isolation that is only ever tested
    against a single tenant is not tested at all.
    """

    def setUp(self):
        super().setUp()
        # set_config(..., false) is session-scoped, so it outlives the
        # transaction rollback between tests. Clear it explicitly or a test
        # inherits whatever context its predecessor left behind.
        self.clear_tenant()

        self.mor = Tenant.objects.create(
            id=MOR_ID, code='MOR', name='Moroni SARL', db_name='tenant_mor'
        )
        self.mut = Tenant.objects.create(
            id=MUT_ID, code='MUT', name='Mutsamudu SA', db_name='tenant_mut'
        )

        self.mor_user = User.objects.create_user('mor_user', password='demo1234')
        self.mut_user = User.objects.create_user('mut_user', password='demo1234')

        TenantMembership.objects.create(user=self.mor_user, tenant=self.mor, role='admin')
        TenantMembership.objects.create(user=self.mut_user, tenant=self.mut, role='admin')

    def tearDown(self):
        self.clear_tenant()
        super().tearDown()

    # -- RLS context --------------------------------------------------------

    def set_tenant(self, tenant):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_tenant_id', %s, false)",
                [str(tenant.id)],
            )

    def clear_tenant(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_tenant_id', '', false)")

    # -- fixtures -----------------------------------------------------------

    def make_invoice(self, tenant, number, **overrides):
        """Create an invoice under that tenant's context, then restore nothing.

        The caller is left with `tenant` as the active context, which is almost
        always what the test wants next.
        """
        self.set_tenant(tenant)
        fields = {
            'status': 'draft',
            'amount': Decimal('100.00'),
            'due_date': date.today() + timedelta(days=30),
            'items': [],
            'version': 1,
            **overrides,
        }
        return Invoice.objects.create(tenant=tenant, number=number, **fields)

    # -- API ----------------------------------------------------------------

    def api_client(self, user):
        client = APIClient()
        token = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client

    def sync(self, client, tenant_code, events=None, last_sync=0, origin='web'):
        return client.post(
            '/api/sync',
            {
                'lastSyncTimestamp': last_sync,
                'origin': origin,
                'events': events or [],
            },
            format='json',
            HTTP_X_TENANT=tenant_code,
        )


def sync_event(entity_id, version, base_version, **data):
    """One push payload, with sensible defaults for the invoice fields."""
    payload = {
        'number': 'INV-001',
        'status': 'draft',
        'amount': 100,
        'dueDate': '2026-12-31',
        'items': [],
        **data,
    }
    return {
        'entityType': 'invoice',
        'entityId': str(entity_id),
        'operation': 'CREATE' if base_version == 0 else 'UPDATE',
        'version': version,
        'baseVersion': base_version,
        'data': payload,
    }
