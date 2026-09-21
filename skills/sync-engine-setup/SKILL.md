# Skill: Bidirectional Sync Engine Setup

**Purpose:** Bootstrap a complete offline-first sync system with conflict detection and resolution.

**When to use:**
- Setting up new hybrid application
- Adding sync to existing offline-first app
- Designing sync workflow for new tenant

**Outputs:**
- ✅ Django sync API endpoints (`/api/sync`, `/api/events`)
- ✅ Frontend sync manager (Zustand + TanStack Query)
- ✅ Conflict detection & resolution logic
- ✅ SyncEvent model with versioning
- ✅ Integration tests

---

## Architecture

```
Client (Zustand local state)
    ↓ (_isDirty, _version)
    ↓
Sync Manager (TanStack Query)
    ↓ POST /api/sync
    ↓
Django Sync API
    ├─ Validate events
    ├─ Check versioning (optimistic lock)
    ├─ Detect conflicts
    ├─ Apply delta to DB
    ├─ Generate audit logs
    └─ Return new events + conflicts
    ↓
Client receives & merges
    ↓
UI re-renders
```

---

## Key Components

### 1. Django Models (Backend)

```python
# models.py
from django.db import models
from django.utils import timezone

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
    
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=50)  # 'invoice', 'task', etc
    entity_id = models.CharField(max_length=100)
    operation = models.CharField(max_length=10, choices=OPERATION_CHOICES)
    
    # Data payload
    data = models.JSONField()  # Full entity or delta
    delta = models.JSONField(null=True)  # What changed
    
    # Versioning & tracking
    version = models.IntegerField(default=1)  # Optimistic lock
    origin = models.CharField(max_length=50)  # 'site_a', 'web', 'mobile'
    
    # Sync status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    synced_at = models.DateTimeField(null=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    
    # Integrity
    hash = models.CharField(max_length=64, unique=True)  # SHA256 checksum
    
    class Meta:
        db_table = 'sync_events'
        indexes = [
            models.Index(fields=['tenant', 'entity_type', 'created_at']),
            models.Index(fields=['tenant', 'synced_at']),
            models.Index(fields=['status', 'created_at']),
        ]
        ordering = ['created_at']

class SyncConflict(models.Model):
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100)
    
    client_event = models.ForeignKey(SyncEvent, on_delete=models.CASCADE, related_name='client_conflicts')
    server_event = models.ForeignKey(SyncEvent, on_delete=models.CASCADE, related_name='server_conflicts')
    
    client_version = models.IntegerField()
    server_version = models.IntegerField()
    
    resolution_strategy = models.CharField(max_length=50, default='pending')  # 'lww', 'fww', 'manual', 'crdt'
    resolved_at = models.DateTimeField(null=True)
    resolved_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    resolved_data = models.JSONField(null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
```

### 2. Sync API Endpoint

```python
# views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
import hashlib

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def sync_events(request):
    """
    Bidirectional sync endpoint
    
    Request:
    {
        "lastSyncTimestamp": 1234567890,
        "events": [
            {
                "entityType": "invoice",
                "entityId": "inv_123",
                "operation": "UPDATE",
                "version": 2,
                "delta": {"status": {"old": "draft", "new": "sent"}},
                "data": {...full entity...}
            }
        ]
    }
    """
    
    tenant = request.tenant
    client_events = request.data.get('events', [])
    last_sync_ts = request.data.get('lastSyncTimestamp', 0)
    
    # 1. Ingest client events
    conflicts = []
    synced_events = []
    
    for event in client_events:
        try:
            # Checksum validation
            event_hash = compute_event_hash(event)
            
            # Check if exists
            existing = SyncEvent.objects.filter(
                tenant=tenant,
                entity_type=event['entityType'],
                entity_id=event['entityId'],
                hash=event_hash
            ).first()
            
            if existing:
                # Already synced, skip
                continue
            
            # Optimistic locking: version check
            current_version = get_current_entity_version(
                tenant, event['entityType'], event['entityId']
            )
            
            if current_version != event.get('version'):
                # CONFLICT!
                conflict = SyncConflict.objects.create(
                    tenant=tenant,
                    entity_type=event['entityType'],
                    entity_id=event['entityId'],
                    client_version=event.get('version'),
                    server_version=current_version,
                )
                conflicts.append({
                    'entityId': event['entityId'],
                    'clientVersion': event.get('version'),
                    'serverVersion': current_version,
                    'conflictId': str(conflict.id),
                })
                continue
            
            # Apply event
            sync_event = SyncEvent.objects.create(
                tenant=tenant,
                entity_type=event['entityType'],
                entity_id=event['entityId'],
                operation=event['operation'],
                version=event.get('version', 1),
                data=event.get('data'),
                delta=event.get('delta'),
                origin=request.headers.get('X-Origin', 'unknown'),
                created_by=request.user,
                hash=event_hash,
                status='pending'
            )
            
            # Apply to actual entity
            apply_event_to_entity(sync_event)
            
            sync_event.status = 'synced'
            sync_event.synced_at = timezone.now()
            sync_event.save()
            
            synced_events.append(sync_event.id)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=400)
    
    # 2. Fetch events to download
    download_events = SyncEvent.objects.filter(
        tenant=tenant,
        created_at__gt=last_sync_ts,
        status='synced'
    ).values(
        'entity_type', 'entity_id', 'operation', 'data', 'version', 'created_at'
    )
    
    return Response({
        'status': 'success',
        'uploadedCount': len(synced_events),
        'downloadCount': download_events.count(),
        'newEvents': list(download_events),
        'conflicts': conflicts,
        'serverTimestamp': timezone.now().timestamp(),
    })

def compute_event_hash(event):
    """Generate SHA256 checksum"""
    data = f"{event['entityType']}{event['entityId']}{event['operation']}".encode()
    return hashlib.sha256(data).hexdigest()

def get_current_entity_version(tenant, entity_type, entity_id):
    """Get current version of entity"""
    # Stub - implement per entity type
    pass

def apply_event_to_entity(sync_event):
    """Apply sync event to actual database entity"""
    # Route by entity_type
    # Call appropriate model's apply_delta() method
    pass
```

### 3. Frontend Sync Manager (Zustand)

```typescript
// lib/stores/useSyncStore.ts
import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

interface SyncEvent {
  entityType: string;
  entityId: string;
  operation: 'CREATE' | 'UPDATE' | 'DELETE';
  version: number;
  delta?: Record<string, any>;
  data: Record<string, any>;
}

interface SyncConflict {
  entityId: string;
  clientVersion: number;
  serverVersion: number;
  conflictId: string;
}

interface SyncStore {
  lastSyncTimestamp: number;
  pendingEvents: SyncEvent[];
  conflicts: SyncConflict[];
  isSyncing: boolean;
  
  addEvent: (event: SyncEvent) => void;
  getPendingEvents: () => SyncEvent[];
  clearPendingEvents: () => void;
  setConflicts: (conflicts: SyncConflict[]) => void;
  setLastSyncTimestamp: (ts: number) => void;
  setSyncing: (syncing: boolean) => void;
}

export const useSyncStore = create<SyncStore>(
  subscribeWithSelector((set, get) => ({
    lastSyncTimestamp: 0,
    pendingEvents: [],
    conflicts: [],
    isSyncing: false,
    
    addEvent: (event) => set((state) => ({
      pendingEvents: [...state.pendingEvents, event],
    })),
    
    getPendingEvents: () => get().pendingEvents,
    
    clearPendingEvents: () => set({ pendingEvents: [] }),
    
    setConflicts: (conflicts) => set({ conflicts }),
    
    setLastSyncTimestamp: (ts) => set({ lastSyncTimestamp: ts }),
    
    setSyncing: (syncing) => set({ isSyncing: syncing }),
  }))
);
```

### 4. TanStack Query Sync Hook

```typescript
// hooks/useSyncQuery.ts
import { useQuery } from '@tanstack/react-query';
import { useSyncStore } from '@/lib/stores/useSyncStore';

export function useSyncQuery(tenantId: string) {
  const {
    lastSyncTimestamp,
    pendingEvents,
    setSyncing,
    setLastSyncTimestamp,
    setConflicts,
    clearPendingEvents,
  } = useSyncStore();

  return useQuery({
    queryKey: ['sync', tenantId],
    queryFn: async () => {
      if (pendingEvents.length === 0) {
        return { newEvents: [], conflicts: [] };
      }

      setSyncing(true);
      
      try {
        const response = await fetch('/api/sync', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Tenant': tenantId,
            'X-Origin': 'web',
          },
          body: JSON.stringify({
            lastSyncTimestamp,
            events: pendingEvents,
          }),
        });

        if (!response.ok) throw new Error('Sync failed');

        const data = await response.json();

        // Process conflicts
        if (data.conflicts.length > 0) {
          setConflicts(data.conflicts);
        }

        // Update timestamp
        setLastSyncTimestamp(data.serverTimestamp);

        // Clear pending
        clearPendingEvents();

        return {
          newEvents: data.newEvents,
          conflicts: data.conflicts,
        };
      } finally {
        setSyncing(false);
      }
    },
    refetchInterval: 10000,  // Auto-sync every 10s
    refetchIntervalInBackground: true,
    retry: 3,
    retryDelay: (attemptIndex) =>
      Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}
```

---

## Configuration

**Environment variables:**
```
SYNC_CONFLICT_RESOLUTION_STRATEGY=last-write-wins  # or 'manual'
SYNC_AUTO_PURGE_DAYS=90
SYNC_COMPRESSION_THRESHOLD=1000  # bytes
```

**Django settings:**
```python
# settings.py
SYNC_CONFIG = {
    'CONFLICT_RESOLUTION': 'last-write-wins',
    'AUTO_PURGE_SYNCED_AFTER_DAYS': 90,
    'EVENT_COMPRESSION': True,
    'AUDIT_ENABLED': True,
}
```

---

## Usage Example

```typescript
// Component: InvoiceForm.tsx
import { useSyncStore } from '@/lib/stores/useSyncStore';

export function InvoiceForm() {
  const { addEvent } = useSyncStore();
  
  const handleSave = async (invoice) => {
    // 1. Save locally first
    invoiceStore.updateInvoice(invoice.id, invoice);
    
    // 2. Queue for sync
    addEvent({
      entityType: 'invoice',
      entityId: invoice.id,
      operation: 'UPDATE',
      version: invoice._version,
      delta: {
        status: { old: 'draft', new: 'sent' }
      },
      data: invoice,
    });
    
    // TanStack Query will auto-sync in background
  };
}
```

---

## Conflict Resolution Strategies

| Strategy | Use Case | Code |
|----------|----------|------|
| **Last-Write-Wins** | Non-critical (comments, notes) | Server overwrites client |
| **First-Write-Wins** | Financial (amounts, dates) | Client changes rejected |
| **Manual** | Critical decisions | User UI to resolve |
| **CRDT** | Lists, docs | Use Yjs auto-merge |

---

## Testing

```python
# tests/test_sync.py
from django.test import TestCase, Client
from django.contrib.auth.models import User

class SyncTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test', 'test@example.com', 'pass')
        self.tenant = Tenant.objects.create(name='Test Tenant')
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_sync_create_event(self):
        payload = {
            'lastSyncTimestamp': 0,
            'events': [
                {
                    'entityType': 'invoice',
                    'entityId': 'inv_123',
                    'operation': 'CREATE',
                    'version': 1,
                    'data': {
                        'number': 'INV-001',
                        'amount': 100,
                        'status': 'draft'
                    }
                }
            ]
        }
        
        response = self.client.post('/api/sync', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('uploadedCount', response.json())
```

---

## Performance Tuning

- **Batch events:** Send 10-50 events at once, not one-by-one
- **Compression:** Enable gzip for events > 1KB
- **Indexing:** Ensure indexes on (tenant, entity_type, created_at)
- **Archival:** Auto-purge synced events after 90 days

