from django.contrib import admin

from core.models import (
    AuditLog,
    Invoice,
    SyncConflict,
    SyncEvent,
    Tenant,
    TenantMembership,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'country', 'currency', 'created_at')
    search_fields = ('code', 'name')


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'tenant', 'role')
    list_filter = ('role', 'tenant')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'tenant', 'status', 'amount', 'version', 'synced_at')
    list_filter = ('status', 'tenant')
    search_fields = ('number',)


@admin.register(SyncEvent)
class SyncEventAdmin(admin.ModelAdmin):
    list_display = (
        'entity_type', 'entity_id', 'operation', 'version',
        'origin', 'status', 'server_received_at',
    )
    list_filter = ('status', 'entity_type', 'origin')


@admin.register(SyncConflict)
class SyncConflictAdmin(admin.ModelAdmin):
    list_display = (
        'entity_type', 'entity_id', 'client_version',
        'server_version', 'status', 'created_at',
    )
    list_filter = ('status', 'entity_type')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('entity_type', 'entity_id', 'action', 'created_at')
    list_filter = ('action', 'entity_type')
    # The audit trail is evidence. Reading it through the admin is fine;
    # editing it there is not.
    readonly_fields = [field.name for field in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
