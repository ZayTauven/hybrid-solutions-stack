# Skill: Celery Async Jobs

**Purpose:** Background tasks for sync processing, reports, cleanup

---

## Setup

```python
# settings.py
CELERY_BROKER_URL = 'redis://redis:6379/0'
CELERY_RESULT_BACKEND = 'redis://redis:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
```

---

## Tasks

```python
# tasks.py
from celery import shared_task
from django.utils import timezone

@shared_task
def process_sync_events(tenant_id: str):
    """Process pending sync events"""
    events = SyncEvent.objects.filter(
        tenant_id=tenant_id,
        status='pending'
    )[:100]
    
    for event in events:
        apply_event_to_entity(event)
        event.status = 'synced'
        event.save()

@shared_task
def generate_invoice_pdf(invoice_id: str):
    """Generate PDF in background"""
    invoice = Invoice.objects.get(id=invoice_id)
    pdf = generate_pdf(invoice)
    invoice.pdf_url = store_file(pdf)
    invoice.save()

@shared_task
def purge_old_synced_events(days: int = 90):
    """Cleanup synced events older than X days"""
    cutoff = timezone.now() - timedelta(days=days)
    SyncEvent.objects.filter(
        synced_at__lt=cutoff
    ).delete()

# Periodic tasks
from celery.schedules import crontab

app.conf.beat_schedule = {
    'purge-sync-daily': {
        'task': 'myapp.tasks.purge_old_synced_events',
        'schedule': crontab(hour=2, minute=0),
    },
}
```

---

## Usage

```python
# views.py
@api_view(['POST'])
def request_invoice_pdf(request, invoice_id):
    from .tasks import generate_invoice_pdf
    
    task = generate_invoice_pdf.delay(str(invoice_id))
    
    return Response({'task_id': task.id})
```

