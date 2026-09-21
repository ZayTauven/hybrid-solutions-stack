# Skill: CRDT Integration (Yjs)

**Purpose:** Setup conflict-free collaborative editing for lists, documents, and shared state.

**Use cases:** Task lists, shared docs, real-time annotations

---

## Architecture

```
Client A (Offline)          Client B (Offline)
  ↓ Edit task              ↓ Edit task
Y.Array (Yjs)            Y.Array (Yjs)
  ↓ (Auto-merge when sync)  ↓
  └─────────┬──────────────┘
            ↓
      Both changes exist
      (No conflict!)
```

---

## Setup Yjs

```typescript
// lib/stores/useTaskStore.ts
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { useEffect, useState } from 'react';

export function useSharedTasks(projectId: string) {
  const [tasks, setTasks] = useState<Task[]>([]);
  
  useEffect(() => {
    const ydoc = new Y.Doc();
    const yTasks = ydoc.getArray<Task>('tasks');
    
    // Connect to server (if online)
    const provider = new WebsocketProvider(
      'wss://sync.example.com',
      `project-${projectId}`,
      ydoc,
      { resyncInterval: 5000, maxBackoffTime: 30000 }
    );
    
    // Listen to changes (local or remote)
    yTasks.observe((event) => {
      setTasks(yTasks.toArray());
    });
    
    return () => {
      provider.destroy();
      ydoc.destroy();
    };
  }, [projectId]);
  
  const addTask = (task: Task) => {
    const ydoc = useSharedTasks.doc;
    const yTasks = ydoc.getArray('tasks');
    yTasks.push([task]);
  };
  
  const updateTask = (taskId: string, updates: Partial<Task>) => {
    const yTasks = useSharedTasks.yTasks;
    const index = yTasks.toArray().findIndex(t => t.id === taskId);
    if (index >= 0) {
      yTasks.delete(index);
      yTasks.insert(index, [{ ...yTasks.get(index), ...updates }]);
    }
  };
  
  return { tasks, addTask, updateTask };
}
```

---

## Yjs + Django Sync

```python
# views.py
from django.http import JsonResponse
from yjs import Y

@api_view(['POST'])
def sync_yjs_doc(request):
    """Sync Yjs document state"""
    project_id = request.data.get('projectId')
    y_update = request.data.get('update')  # Base64 encoded
    
    # Reconstruct Yjs state
    ydoc = Y.Document()
    
    # Apply updates from clients
    ydoc.apply_update(base64_decode(y_update))
    
    # Get array
    y_tasks = ydoc.get_array('tasks')
    
    # Save to DB
    for i, task in enumerate(y_tasks):
        Task.objects.update_or_create(
            id=task['id'],
            defaults={
                'title': task['title'],
                'status': task['status'],
                'project_id': project_id,
                'order': i,
            }
        )
    
    return JsonResponse({'status': 'synced'})
```

---

## When to Use CRDT

✅ Use CRDT for:
- Task lists (add/remove tasks)
- Shared documents
- Collaborative annotations
- Real-time note-taking

❌ Don't use CRDT for:
- Financial amounts (need precision)
- Unique identifiers
- Single-record state (one entity)

---

## Storage (IndexedDB)

```typescript
// Persist Yjs to IndexedDB
import * as idb from 'y-indexeddb';

const ydoc = new Y.Doc();
const provider = new idb.IndexeddbPersistence(`doc-${projectId}`, ydoc);

// Auto-syncs to IndexedDB
```

