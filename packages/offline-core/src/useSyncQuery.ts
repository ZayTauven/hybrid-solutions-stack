import { useQuery } from '@tanstack/react-query';

import { getConfig } from './config';
import { getSyncParticipants, type SyncParticipant } from './registry';
import { authorizedFetch, useAuth } from './useAuth';
import type {
  RemoteChange,
  SyncAcceptance,
  SyncEventPayload,
  SyncResponse,
} from './types';

const SYNC_CURSOR_STORAGE_KEY = 'hybrid:sync-cursor';

/**
 * Per-tenant sync cursor, in seconds, with sub-second precision.
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

/**
 * Bidirectional sync across every registered entity store.
 *
 * One call carries every entity type, so adding an entity needs no change
 * here -- its store registers itself and is picked up on the next tick.
 */
export function useSyncQuery(tenantId: string) {
  const user = useAuth((state) => state.user);

  return useQuery<SyncResponse>({
    queryKey: ['sync', tenantId],
    queryFn: async () => {
      const participants = getSyncParticipants();

      // Remember who sent what: the server's acceptances carry no entity type,
      // and routing them by id alone would be guesswork.
      const senderById = new Map<string, SyncParticipant>();
      const events: SyncEventPayload[] = [];

      for (const participant of participants) {
        for (const event of participant.collectPending(tenantId)) {
          senderById.set(event.entityId, participant);
          events.push(event);
        }
      }

      // No short-circuit when there is nothing to push: the exchange is
      // bidirectional. Skipping the call means a machine that edits nothing
      // never receives the other sites' changes.
      const response = await authorizedFetch('/api/sync', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant': tenantId,
        },
        body: JSON.stringify({
          lastSyncTimestamp: readSyncCursor(tenantId),
          origin: getConfig().origin,
          events,
        }),
      });

      if (!response.ok) {
        throw new Error(`Sync failed: ${response.status} ${response.statusText}`);
      }

      const data: SyncResponse = await response.json();

      // Only the entities the server accepted are cleared. Marking everything
      // would wipe the local edits of conflict-rejected records, with no way
      // to replay them.
      const acceptedBySender = new Map<SyncParticipant, SyncAcceptance[]>();
      for (const acceptance of data.accepted) {
        const sender = senderById.get(acceptance.entityId);
        if (!sender) continue;
        const bucket = acceptedBySender.get(sender) ?? [];
        bucket.push(acceptance);
        acceptedBySender.set(sender, bucket);
      }

      const syncedAt = data.serverTimestamp * 1000;
      for (const [participant, accepted] of acceptedBySender) {
        participant.markSynced(accepted, syncedAt);
      }

      const changesByType = new Map<string, RemoteChange[]>();
      for (const event of data.newEvents) {
        const bucket = changesByType.get(event.entityType) ?? [];
        bucket.push({
          entityId: event.entityId,
          version: event.version,
          operation: event.operation,
          data: event.data,
        });
        changesByType.set(event.entityType, bucket);
      }

      for (const participant of participants) {
        const changes = changesByType.get(participant.entityType);
        if (changes?.length) {
          participant.applyRemoteChanges(changes, tenantId);
        }
      }

      writeSyncCursor(tenantId, data.serverTimestamp);

      return data;
    },
    // Normally on the configured interval. When the server says the batch was
    // truncated, come straight back for the next page instead of draining a
    // long backlog one interval at a time -- a site returning from a week
    // offline would take hours to catch up otherwise.
    refetchInterval: (query) =>
      query.state.data?.hasMore ? 250 : getConfig().syncIntervalMs,
    refetchIntervalInBackground: true,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    enabled: !!user && !!tenantId,
  });
}
