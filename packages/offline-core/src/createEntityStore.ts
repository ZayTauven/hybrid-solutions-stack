import { create, type StoreApi, type UseBoundStore } from 'zustand';
import { persist, subscribeWithSelector } from 'zustand/middleware';

import { registerSyncParticipant } from './registry';
import type {
  NewEntity,
  RemoteChange,
  SyncAcceptance,
  SyncEventPayload,
  SyncedEntity,
} from './types';

export interface EntityStoreState<T extends SyncedEntity> {
  /**
   * Keyed by id. A Record rather than a Map: JSON-serialisable, so it works
   * with the `persist` middleware -- which offline-first needs, since state
   * has to survive a page reload.
   */
  entities: Record<string, T>;

  add: (entity: NewEntity<T>) => void;
  update: (id: string, updates: Partial<NewEntity<T>>) => void;
  /** Tombstones the record, or drops it outright if the server never saw it. */
  remove: (id: string) => void;

  /** Pending changes, tombstones included. Scoped to a tenant when given. */
  getDirty: (tenantId?: string) => T[];
  markSynced: (accepted: SyncAcceptance[], syncedAt?: number) => void;
  applyRemoteChanges: (changes: RemoteChange[], tenantId: string) => void;

  get: (id: string) => T | undefined;
  /** Live records only -- tombstones are filtered out. */
  getAll: (tenantId?: string) => T[];
}

export interface CreateEntityStoreOptions {
  /** Wire identifier, e.g. `'invoice'`. Must match the server's handler. */
  entityType: string;
  /** localStorage key. Defaults to `hybrid:<entityType>`. */
  storageKey?: string;
}

/**
 * Builds a local-first store for one synced entity type.
 *
 * Every mutation returns a new `entities` object. Mutating state in place
 * (e.g. `state.entities[id].x = 1`) triggers no render at all: zustand compares
 * references, and without the `immer` middleware whatever `set` returns is what
 * becomes the next state.
 *
 * Usage note: the getters below build a new array on every call. Read them via
 * `useStore.getState().getAll()` or inside a `useMemo`, never as a direct
 * selector -- `useStore((s) => s.getAll())` loops forever.
 */
export function createEntityStore<T extends SyncedEntity>(
  options: CreateEntityStoreOptions,
): UseBoundStore<StoreApi<EntityStoreState<T>>> {
  const { entityType, storageKey = `hybrid:${entityType}` } = options;

  const useStore = create<EntityStoreState<T>>()(
    persist(
      subscribeWithSelector((set, get) => ({
        entities: {},

        add: (entity) =>
          set((state) => ({
            entities: {
              ...state.entities,
              [entity.id]: {
                ...entity,
                _version: 1,
                // A record the server has never seen starts from 0, which is
                // what tells the sync endpoint to create rather than update.
                _baseVersion: 0,
                _isDirty: true,
                _isDeleted: false,
                _lastSyncedAt: 0,
              } as unknown as T,
            },
          })),

        update: (id, updates) =>
          set((state) => {
            const entity = state.entities[id];
            if (!entity || entity._isDeleted) return state;

            return {
              entities: {
                ...state.entities,
                [id]: {
                  ...entity,
                  ...updates,
                  // The version counter feeds the server-side optimistic lock:
                  // `updates` must never overwrite it. _baseVersion stays put --
                  // it still records the last state the server confirmed.
                  _version: entity._version + 1,
                  _baseVersion: entity._baseVersion,
                  _isDirty: true,
                },
              },
            };
          }),

        remove: (id) =>
          set((state) => {
            const entity = state.entities[id];
            if (!entity) return state;

            // Never synced, so the server has nothing to forget. Keeping a
            // tombstone here would push a DELETE for a row that does not exist.
            if (entity._baseVersion === 0) {
              const { [id]: _dropped, ...rest } = state.entities;
              return { entities: rest };
            }

            return {
              entities: {
                ...state.entities,
                [id]: {
                  ...entity,
                  _version: entity._version + 1,
                  _isDirty: true,
                  _isDeleted: true,
                },
              },
            };
          }),

        /**
         * Pending local changes, optionally narrowed to one tenant.
         *
         * The scoping matters: a device that has held sessions for two tenants
         * keeps both sets locally, and pushing one tenant's rows inside another
         * tenant's sync call gets them rejected by row-level security.
         */
        getDirty: (tenantId) =>
          Object.values(get().entities).filter(
            (entity) => entity._isDirty && (!tenantId || entity.tenantId === tenantId),
          ),

        /**
         * Only call this for records the server actually accepted. Marking a
         * conflicted record as synced discards the local edit for good.
         */
        markSynced: (accepted, syncedAt = Date.now()) =>
          set((state) => {
            const entities = { ...state.entities };

            for (const { entityId, version } of accepted) {
              const entity = entities[entityId];
              if (!entity) continue;

              if (entity._isDeleted) {
                // The deletion is now the server's to remember; the event log
                // is the tombstone from here on.
                delete entities[entityId];
                continue;
              }

              entities[entityId] = {
                ...entity,
                // The server's version is authoritative from here on.
                _version: version,
                _baseVersion: version,
                _isDirty: false,
                _lastSyncedAt: syncedAt,
              };
            }

            return { entities };
          }),

        /**
         * Merge changes made by other sites.
         *
         * A locally dirty record is skipped: overwriting it would silently
         * discard an edit the user has not managed to push yet. It stays dirty
         * and the next sync surfaces the clash as a real conflict.
         */
        applyRemoteChanges: (changes, tenantId) =>
          set((state) => {
            const entities = { ...state.entities };

            for (const change of changes) {
              const existing = entities[change.entityId];
              if (existing?._isDirty) continue;

              if (change.operation === 'DELETE') {
                delete entities[change.entityId];
                continue;
              }

              entities[change.entityId] = {
                ...(existing ?? {}),
                ...change.data,
                id: change.entityId,
                // Stamped from the sync context, not from the payload: an event
                // body carries whatever the originating client sent, and an
                // untagged record would surface under the wrong tenant.
                tenantId,
                _version: change.version,
                _baseVersion: change.version,
                _isDirty: false,
                _isDeleted: false,
                _lastSyncedAt: Date.now(),
              } as unknown as T;
            }

            return { entities };
          }),

        get: (id) => get().entities[id],

        getAll: (tenantId) =>
          Object.values(get().entities).filter(
            (entity) =>
              !entity._isDeleted && (!tenantId || entity.tenantId === tenantId),
          ),
      })),
      {
        name: storageKey,
        // Persisting the data is the point: an offline-first app must come back
        // from a reload with its unsynced work intact.
        partialize: (state) => ({ entities: state.entities }),
      },
    ),
  );

  registerSyncParticipant({
    entityType,
    collectPending: (tenantId) =>
      useStore.getState().getDirty(tenantId).map<SyncEventPayload>((entity) => ({
        entityType,
        entityId: entity.id,
        operation: entity._isDeleted
          ? 'DELETE'
          : entity._baseVersion === 0
            ? 'CREATE'
            : 'UPDATE',
        version: entity._version,
        baseVersion: entity._baseVersion,
        data: entity,
      })),
    markSynced: (accepted, syncedAt) =>
      useStore.getState().markSynced(accepted, syncedAt),
    applyRemoteChanges: (changes, tenantId) =>
      useStore.getState().applyRemoteChanges(changes, tenantId),
  });

  return useStore;
}
