"""Seed two tenants with users and invoices, to exercise the sync path.

    python manage.py seed_demo

Creates the minimum needed to demonstrate isolation and conflicts: two tenants
that must not see each other, and one user per tenant.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from core.models import Invoice, Tenant, TenantMembership

DEMO_PASSWORD = 'demo1234'

TENANTS = [
    ('MOR', 'Moroni SARL', uuid.UUID('11111111-1111-1111-1111-111111111111')),
    ('MUT', 'Mutsamudu SA', uuid.UUID('22222222-2222-2222-2222-222222222222')),
]


class Command(BaseCommand):
    help = 'Create demo tenants, users and invoices.'

    @transaction.atomic
    def handle(self, *args, **options):
        for code, name, tenant_id in TENANTS:
            tenant, created = Tenant.objects.get_or_create(
                id=tenant_id,
                defaults={'code': code, 'name': name, 'db_name': f'tenant_{code.lower()}'},
            )
            self.stdout.write(
                f'{"Created" if created else "Found"} tenant {tenant.code} ({tenant.id})'
            )

            username = f'{code.lower()}_user'
            user, user_created = User.objects.get_or_create(
                username=username, defaults={'email': f'{username}@example.km'}
            )
            if user_created:
                user.set_password(DEMO_PASSWORD)
                user.save()

            TenantMembership.objects.get_or_create(
                user=user, tenant=tenant, defaults={'role': 'admin'}
            )
            self.stdout.write(f'  user {username} / {DEMO_PASSWORD}')

            self._seed_invoices(tenant, user, code)

        self.stdout.write(self.style.SUCCESS('\nSeed complete.'))
        self.stdout.write(
            'Log in with mor_user or mut_user and pass X-Tenant: MOR or MUT.'
        )

    def _seed_invoices(self, tenant, user, code):
        # Writes go through RLS like any other query, so the session needs the
        # tenant context set even from a management command.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_tenant_id', %s, false)",
                [str(tenant.id)],
            )

        for index in range(1, 3):
            number = f'{code}-{index:03d}'
            _, created = Invoice.objects.get_or_create(
                tenant=tenant,
                number=number,
                defaults={
                    'status': 'draft',
                    'amount': Decimal(100 * index),
                    'due_date': date.today() + timedelta(days=30),
                    'items': [
                        {
                            'id': str(uuid.uuid4()),
                            'description': f'Service {index}',
                            'quantity': 1,
                            'unitPrice': float(100 * index),
                        }
                    ],
                    'created_by': user,
                },
            )
            if created:
                self.stdout.write(f'  invoice {number}')
