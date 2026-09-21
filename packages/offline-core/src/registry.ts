/**
 * Registry of entity stores.
 *
 * One sync call carries every entity type at once, so the sync hook has to
 * reach stores it was never handed. Stores register themselves on creation and
 * the hook iterates the registry, which is what lets a skin add an entity
 * without touching the sync layer.
 */

import type { RemoteChange, SyncAcceptance, SyncEventPayload } from './types';

export interface SyncParticipant {
  /** Matches `entityType` on the wire. */
  entityType: string;
  /** Pending local changes for this tenant, as wire payloads. */
  collectPending: (tenantId: string) => SyncEventPayload[];
  /** Apply the server's acceptances. */
  markSynced: (accepted: SyncAcceptance[], syncedAt?: number) => void;
  /** Apply changes made elsewhere. */
  applyRemoteChanges: (changes: RemoteChange[], tenantId: string) => void;
}

const participants = new Map<string, SyncParticipant>();

export function registerSyncParticipant(participant: SyncParticipant): void {
  participants.set(participant.entityType, participant);
}

export function getSyncParticipants(): SyncParticipant[] {
  return Array.from(participants.values());
}

export function getSyncParticipant(entityType: string): SyncParticipant | undefined {
  return participants.get(entityType);
}

/** Test seam: drops every registration. */
export function resetSyncParticipants(): void {
  participants.clear();
}
