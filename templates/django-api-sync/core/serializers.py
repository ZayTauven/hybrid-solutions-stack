"""Serializers bridging the TypeScript client shape and the Django models.

The frontend speaks camelCase and carries sync metadata (`_version`,
`_isDirty`) that must never be written to the database as-is.
"""

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from core.models import Invoice, SyncConflict


class InvoiceSerializer(serializers.ModelSerializer):
    """Read shape sent back to clients."""

    tenantId = serializers.CharField(source='tenant_id', read_only=True)
    dueDate = serializers.DateField(source='due_date', read_only=True)
    _version = serializers.IntegerField(source='version', read_only=True)

    class Meta:
        model = Invoice
        fields = ['id', 'tenantId', 'number', 'status', 'amount', 'dueDate', 'items', '_version']


class SyncEventInputSerializer(serializers.Serializer):
    """One change pushed by a client."""

    entityType = serializers.CharField(max_length=50)
    entityId = serializers.CharField(max_length=100)
    operation = serializers.ChoiceField(choices=['CREATE', 'UPDATE', 'DELETE'])
    version = serializers.IntegerField(min_value=1)
    # The version the client started from. Absent on older clients, in which
    # case we infer it -- but an explicit value is what makes field-merge
    # resolution possible at all.
    baseVersion = serializers.IntegerField(required=False, min_value=0)
    data = serializers.DictField()

    def validate(self, attrs):
        attrs.setdefault('baseVersion', max(attrs['version'] - 1, 0))
        if attrs['baseVersion'] >= attrs['version']:
            raise serializers.ValidationError(
                'baseVersion must be lower than version.'
            )
        return attrs


class SyncRequestSerializer(serializers.Serializer):
    # Float, not int: the cursor carries sub-second precision so that resuming
    # a truncated batch cannot replay or skip events (see core/views.py).
    lastSyncTimestamp = serializers.FloatField(min_value=0, default=0)
    origin = serializers.CharField(max_length=50, default='web')
    events = SyncEventInputSerializer(many=True, default=list)


def invoice_fields_from_payload(data):
    """Extract the writable invoice fields from a client payload.

    Anything not listed here is ignored on purpose: the client's local sync
    metadata and its idea of `version` are not inputs the server trusts.
    """
    fields = {}

    if 'number' in data:
        fields['number'] = str(data['number'])[:50]

    if 'status' in data:
        valid = {choice for choice, _ in Invoice.STATUS_CHOICES}
        if data['status'] not in valid:
            raise serializers.ValidationError(f"Invalid status: {data['status']}")
        fields['status'] = data['status']

    if 'amount' in data:
        try:
            fields['amount'] = Decimal(str(data['amount']))
        except (InvalidOperation, TypeError) as exc:
            raise serializers.ValidationError(f"Invalid amount: {data['amount']}") from exc

    if 'dueDate' in data:
        fields['due_date'] = data['dueDate']

    if 'items' in data:
        if not isinstance(data['items'], list):
            raise serializers.ValidationError('items must be a list.')
        fields['items'] = data['items']

    return fields


class SyncConflictSerializer(serializers.ModelSerializer):
    conflictId = serializers.UUIDField(source='id', read_only=True)
    entityType = serializers.CharField(source='entity_type', read_only=True)
    entityId = serializers.CharField(source='entity_id', read_only=True)
    clientVersion = serializers.IntegerField(source='client_version', read_only=True)
    serverVersion = serializers.IntegerField(source='server_version', read_only=True)
    contestedFields = serializers.JSONField(source='contested_fields', read_only=True)
    local = serializers.SerializerMethodField()
    remote = serializers.JSONField(source='server_state', read_only=True)
    base = serializers.JSONField(source='base_data', read_only=True)

    class Meta:
        model = SyncConflict
        fields = [
            'conflictId', 'entityType', 'entityId', 'clientVersion',
            'serverVersion', 'contestedFields', 'local', 'remote', 'base',
            'status', 'created_at',
        ]

    def get_local(self, obj):
        return obj.client_event.data
