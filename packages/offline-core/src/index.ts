export { configureOfflineCore, getConfig, apiUrl } from './config';
export type { OfflineCoreConfig } from './config';

export { createEntityStore } from './createEntityStore';
export type { CreateEntityStoreOptions, EntityStoreState } from './createEntityStore';

export {
  registerSyncParticipant,
  getSyncParticipants,
  getSyncParticipant,
  resetSyncParticipants,
} from './registry';
export type { SyncParticipant } from './registry';

export {
  useAuth,
  refreshSession,
  getAccessToken,
  authorizedFetch,
} from './useAuth';

export { useSyncQuery } from './useSyncQuery';

export type {
  AuthUser,
  NewEntity,
  RemoteChange,
  RemoteSyncEvent,
  SyncAcceptance,
  SyncConflict,
  SyncedEntity,
  SyncEventPayload,
  SyncMetadataKeys,
  SyncOperation,
  SyncResponse,
} from './types';
