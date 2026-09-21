# Skill: Data Integrity & Audit Trail

**Purpose:** Immutable audit logs, versioning, and data validation

---

## Audit Logging

```python
# models.py
class AuditLog(models.Model):
    tenant = FK(Tenant)
    user = FK(User)
    entity_type = models.CharField()  # 'invoice'
    entity_id = models.CharField()
    action = models.CharField()  # 'CREATE', 'UPDATE', 'DELETE'
    old_values = models.JSONField()
    new_values = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
    
    # Immutability
    signature = models.CharField(unique=True)  # HMAC signature

# Auto-audit trigger (SQL)
CREATE TRIGGER audit_invoices 
AFTER INSERT OR UPDATE OR DELETE ON invoices
FOR EACH ROW EXECUTE FUNCTION audit_trigger();
```

---

## Rollback Capability

```python
def rollback_invoice(invoice_id: str, to_version: int):
    """Rollback to previous version"""
    logs = AuditLog.objects.filter(
        entity_id=invoice_id,
        entity_type='invoice'
    ).order_by('timestamp')
    
    # Replay events up to version
    state = {}
    for log in logs:
        if log.action == 'CREATE':
            state = log.new_values
        elif log.action == 'UPDATE':
            state.update(log.new_values)
        elif log.action == 'DELETE':
            state = None
        
        if log.version == to_version:
            break
    
    # Restore
    invoice = Invoice.objects.get(id=invoice_id)
    for field, value in state.items():
        setattr(invoice, field, value)
    invoice.save()
    
    # Log rollback
    AuditLog.objects.create(
        entity_type='invoice',
        entity_id=invoice_id,
        action='ROLLBACK',
        new_values=state,
        user=request.user
    )
```

---

## Data Validation

```python
@receiver(pre_save, sender=Invoice)
def validate_invoice(sender, instance, **kwargs):
    """Validate before save"""
    if instance.amount < 0:
        raise ValidationError("Amount must be positive")
    
    if instance.due_date < instance.created_at.date():
        raise ValidationError("Due date cannot be in past")
```

---

## Checksums

```python
def compute_entity_checksum(entity):
    """Detect corruption"""
    data = str(entity.to_dict()).encode()
    return hashlib.sha256(data).hexdigest()

def verify_integrity():
    """Periodic integrity check"""
    for entity in Invoice.objects.all():
        if entity.checksum != compute_entity_checksum(entity):
            alert_admin(f"Corruption detected in {entity.id}")
```

