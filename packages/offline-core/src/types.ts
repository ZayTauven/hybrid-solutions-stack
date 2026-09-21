/**
 * The contract between a client and the sync endpoint.
 *
 * These types describe the wire format, so they are shared by every skin and
 * must stay free of any UI or framework concern.
 */

/** Sync metadata every synced record carries, alongside its business fields. */
export interface SyncedEntity {
  id: string;
  tenantId: string;

  /** Local version, incremented on every local edit. */
  _version: number;
  /** Last version the server confirmed. The optimistic lock compares on this. */
  _baseVersion: number;
  /** There are unpushed local changes. */
  _isDirty: boolean;
  /**
   * Tombstone. A deletion is an edit like any other and has to survive until
   * it has been pushed; removing the record outright would take the intent
   * with it and the server would never hear about it.
   */
  _isDeleted: boolean;
  _lastSyncedAt: number;
}

/** The sync-metadata fields the store fills in, not the caller. */
export type SyncMetadataKeys =
  | '_version'
  | '_baseVersion'
  | '_isDirty'
  | '_isDeleted'
  | '_lastSyncedAt';

/** What a caller supplies when creating a record. */
export type NewEntity<T extends SyncedEntity> = Omit<T, SyncMetadataKeys>;

export type SyncOperation = 'CREATE' | 'UPDATE' | 'DELETE';

/** One change pushed to the server. */
export interface SyncEventPayload {
  entityType: string;
  entityId: string;
  operation: SyncOperation;
  version: number;
  /** The version this client started from, used as the optimistic lock. */
  baseVersion: number;
  data: unknown;
}

/** One entity the server accepted. */
export interface SyncAcceptance {
  entityId: string;
  version: number;
}

/** One conflict the server refused to decide on its own. */
export interface SyncConflict {
  entityId: string;
  clientVersion: number;
  serverVersion: number;
  conflictId: string;
  resolution: string;
}

/** One change made elsewhere, as the server reports it. */
export interface RemoteSyncEvent {
  entityType: string;
  entityId: string;
  operation: SyncOperation;
  version: number;
  data: Record<string, unknown>;
}

export interface SyncResponse {
  status: string;
  uploadedCount: number;
  accepted: SyncAcceptance[];
  newEvents: RemoteSyncEvent[];
  conflicts: SyncConflict[];
  /** Server clock, in seconds, with sub-second precision. Authoritative. */
  serverTimestamp: number;
  /** True when the server truncated the batch and more changes are waiting. */
  hasMore: boolean;
}

/** A change to apply locally, normalised for a store. */
export interface RemoteChange {
  entityId: string;
  version: number;
  operation: SyncOperation;
  data: Record<string, unknown>;
}

export interface AuthUser {
  username: string;
  token: string;
  refreshToken: string;
  /** Token expiry, epoch milliseconds, read from the JWT itself. */
  expiresAt: number;
}
