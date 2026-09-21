import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/hooks/useAuth';
import { useInvoiceStore } from '@/lib/stores/useInvoiceStore';
import type { RemoteChange, SyncAcceptance } from '@/lib/stores/useInvoiceStore';

export interface SyncEventPayload {
  entityType: string;
  entityId: string;
  operation: 'CREATE' | 'UPDATE' | 'DELETE';
  version: number;
  /** The version this client started from, used as the optimistic lock. */
  baseVersion: number;
  data: unknown;
}

export interface SyncConflict {
  entityId: string;
  clientVersion: number;
  serverVersion: number;
  conflictId: string;
  resolution: string;
}

export interface SyncResponse {
  status: string;
  uploadedCount: number;
  accepted: SyncAcceptance[];
  newEvents: Array<{
    entityType: string;
    entityId: string;
    operation: string;
    version: number;
    data: Record<string, unknown>;
  }>;
  conflicts: SyncConflict[];
  /** Server clock, in seconds. Authoritative over the local clock. */
  serverTimestamp: number;
  /** True when the server truncated the batch and more changes are waiting. */
  hasMore: boolean;
}

/**
 * Django is served from a different origin than Next.js. A relative path
 * (`/api/sync`) would hit the Next.js server (:3000), not the API (:8000).
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const SYNC_CURSOR_STORAGE_KEY = 'hybrid:sync-cursor';

/**
 * Per-tenant sync cursor, in seconds.
 *
 * Sending `Date.now()` as `lastSyncTimestamp` tells the server "I am current as
 * of right now": it then never returns anything and the downstream flow is
 * dead. The cursor must hold the timestamp the server returned on the last
 * successful exchange, and survive a reload since the app is built to run
 * offline.
 */
function readSyncCursor(tenantId: string): number {
  if (typeof window === 'undefined') return 0;

  try {
    const raw = window.localStorage.getItem(SYNC_CURSOR_STORAGE_KEY);
    const cursors: Record<string, number> = raw ? JSON.parse(raw) : {};
    return cursors[tenantId] ?? 0;
  } catch {
    return 0;
  }
}

function writeSyncCursor(tenantId: string, timestamp: number): void {
  if (typeof window === 'undefined') return;

  try {
    const raw = window.localStorage.getItem(SYNC_CURSOR_STORAGE_KEY);
    const cursors: Record<string, number> = raw ? JSON.parse(raw) : {};
    cursors[tenantId] = timestamp;
    window.localStorage.setItem(SYNC_CURSOR_STORAGE_KEY, JSON.stringify(cursors));
  } catch {
    // Private browsing or quota exceeded: degrade without breaking sync.
  }
}

export function useSyncQuery(tenantId: string) {
  const user = useAuth((state) => state.user);
  const markSynced = useInvoiceStore((state) => state.markSynced);
  const applyRemoteChanges = useInvoiceStore((state) => state.applyRemoteChanges);

  return useQuery<SyncResponse>({
    queryKey: ['sync', tenantId],
    queryFn: async () => {
      const dirtyInvoices = useInvoiceStore.getState().getDirtyInvoices(tenantId);

      // No short-circuit when there is nothing to push: the exchange is
      // bidirectional. Skipping the call means a machine that edits nothing
      // never receives the other sites' changes.
      const response = await fetch(`${API_BASE_URL}/api/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant': tenantId,
          Authorization: `Bearer ${user?.token}`,
        },
        body: JSON.stringify({
          lastSyncTimestamp: readSyncCursor(tenantId),
          origin: 'web',
          events: dirtyInvoices.map<SyncEventPayload>((inv) => ({
            entityType: 'invoice',
            entityId: inv.id,
            operation: inv._baseVersion === 0 ? 'CREATE' : 'UPDATE',
            version: inv._version,
            baseVersion: inv._baseVersion,
            data: inv,
          })),
        }),
      });

      if (!response.ok) {
        throw new Error(`Sync failed: ${response.status} ${response.statusText}`);
      }

      const data: SyncResponse = await response.json();

      // Only the entities the server accepted are cleared. Marking everything
      // would wipe the local edits of conflict-rejected invoices, with no way
      // to replay them.
      markSynced(data.accepted, data.serverTimestamp * 1000);

      applyRemoteChanges(
        data.newEvents
          .filter((event) => event.entityType === 'invoice')
          .map<RemoteChange>((event) => ({
            entityId: event.entityId,
            version: event.version,
            data: event.data,
          })),
        tenantId,
      );

      writeSyncCursor(tenantId, data.serverTimestamp);

      return data;
    },
    // Normally every 10s. When the server says the batch was truncated, come
    // straight back for the next page instead of draining a long backlog ten
    // seconds at a time -- a site returning from a week offline would take
    // hours to catch up otherwise.
    refetchInterval: (query) => (query.state.data?.hasMore ? 250 : 10_000),
    refetchIntervalInBackground: true,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    // Offline is the normal state, not an error worth retrying into the void.
    enabled: !!user && !!tenantId,
  });
}
