"""Sync backend models.

These models are the source of truth for the schema: tables are created by
`manage.py migrate`, never by init.sql (see templates/postgresql-schema/).
RLS policies and audit triggers arrive in migration 0002, so every database
that runs migrations is isolated -- including the one `manage.py test` builds.
"""

import uuid

from django.contrib.auth.models import User
from django.db import models


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    db_name = models.CharField(max_length=100)
    country = models.CharField(max_length=2, default='KM')
    currency = models.CharField(max_length=3, default='KMF')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenants'

    def __str__(self):
        return f'{self.code} - {self.name}'


class TenantMembership(models.Model):
    """Which tenants a user may act for.

    The tenant arrives as an untrusted `X-Tenant` header. Without an explicit
    membership check, any authenticated user could set the RLS context to any
    tenant and read everything -- the database would faithfully enforce an
    isolation the application just handed away.
    """

    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('user', 'User'),
        ('viewer', 'Viewer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenant_memberships'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'tenant'],
                name='unique_membership_per_user_tenant',
            ),
        ]


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()

    # Line items travel with their invoice rather than living in a child table.
    # The invoice is the unit of synchronisation: splitting lines into rows
    # would let one site's line edit and another site's header edit conflict
    # independently, producing an invoice whose total no longer matches its
    # lines. Denormalising keeps the conflict boundary on a whole document.
    items = models.JSONField(default=list, blank=True)

    # Versioning
    version = models.IntegerField(default=1)

    # Sync tracking
    synced_at = models.DateTimeField(null=True, blank=True)
    is_dirty = models.BooleanField(default=False)

    # Audit
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoices'
        constraints = [
            # An invoice number is only unique within a tenant. Globally
            # unique, two organisations both numbering from INV-001 collide on
            # the very first sync.
            models.UniqueConstraint(
                fields=['tenant', 'number'],
                name='unique_invoice_number_per_tenant',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.number


class SyncEvent(models.Model):
    OPERATION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('conflict', 'Conflict'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100)
    operation = models.CharField(max_length=10, choices=OPERATION_CHOICES)

    # Data
    data = models.JSONField()
    delta = models.JSONField(null=True, blank=True)

    # Versioning
    version = models.IntegerField(default=1)
    # The version the client held BEFORE its edit. Field-merge resolution needs
    # the common ancestor: without it there is no way to tell "the other side
    # changed this field" from "the other side never touched it".
    base_version = models.IntegerField(default=0)
    origin = models.CharField(max_length=50)  # 'site_a', 'web', 'mobile'

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    synced_at = models.DateTimeField(null=True, blank=True)
    # Server arrival order. Conflict arbitration must never rely on a client
    # clock: a site offline for a week legitimately pushes "old" edits, and a
    # drifted clock would let it win or lose arbitrarily.
    server_received_at = models.DateTimeField(auto_now_add=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    # Integrity
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = 'sync_events'
        indexes = [
            models.Index(fields=['tenant', 'entity_type', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['server_received_at']),
        ]


class SyncConflict(models.Model):
    """A detected conflict, awaiting a resolution decision.

    Referenced by skills/sync-engine-setup and skills/conflict-resolution.
    """

    STATUS_CHOICES = [
        ('awaiting_review', 'Awaiting review'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100)

    client_event = models.ForeignKey(
        SyncEvent, on_delete=models.CASCADE, related_name='client_conflicts'
    )
    server_state = models.JSONField()
    base_data = models.JSONField(null=True, blank=True)

    client_version = models.IntegerField()
    server_version = models.IntegerField()
    contested_fields = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='awaiting_review')
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sync_conflicts'
        indexes = [
            models.Index(fields=['tenant', 'status', 'created_at']),
        ]


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100)
    action = models.CharField(max_length=20)  # 'CREATE', 'UPDATE', 'DELETE'
    old_values = models.JSONField(null=True)
    new_values = models.JSONField(null=True)
    # The SQL trigger inserts NULL when app.client_ip is not set.
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        indexes = [
            models.Index(fields=['tenant', 'entity_type', 'created_at']),
        ]
