import { create } from 'zustand';
import { persist, subscribeWithSelector } from 'zustand/middleware';

export interface Invoice {
  id: string;
  tenantId: string;
  number: string;
  status: InvoiceStatus;
  amount: number;
  dueDate: string;
  items: LineItem[];

  // Sync metadata
  /** Local version, incremented on every local edit. */
  _version: number;
  /** Last version the server confirmed. The optimistic lock compares on this. */
  _baseVersion: number;
  _isDirty: boolean;
  _lastSyncedAt: number;
}

export type InvoiceStatus = 'draft' | 'sent' | 'paid';

export interface LineItem {
  id: string;
  description: string;
  quantity: number;
  unitPrice: number;
}

/** One accepted entity, as reported by POST /api/sync. */
export interface SyncAcceptance {
  entityId: string;
  version: number;
}

/** One server-side change, as reported by POST /api/sync. */
export interface RemoteChange {
  entityId: string;
  version: number;
  data: Record<string, unknown>;
}

interface InvoiceStore {
  /**
   * Keyed by id. A Record rather than a Map: JSON-serialisable, so it works
   * with the `persist` middleware -- which offline-first needs, since state
   * has to survive a page reload.
   */
  invoices: Record<string, Invoice>;

  // Actions
  addInvoice: (invoice: Omit<Invoice, '_version' | '_baseVersion' | '_isDirty' | '_lastSyncedAt'>) => void;
  updateInvoice: (id: string, updates: Partial<Invoice>) => void;
  deleteInvoice: (id: string) => void;

  // Sync
  getDirtyInvoices: (tenantId?: string) => Invoice[];
  markSynced: (accepted: SyncAcceptance[], syncedAt?: number) => void;
  applyRemoteChanges: (changes: RemoteChange[], tenantId: string) => void;

  // Queries
  getInvoice: (id: string) => Invoice | undefined;
  getAllInvoices: () => Invoice[];
  getInvoicesByStatus: (status: InvoiceStatus) => Invoice[];
}

/**
 * Local-first invoice store.
 *
 * Every mutation returns a new `invoices` object. Mutating state in place
 * (e.g. `state.invoices.set(...)` on a Map) triggers no render at all: zustand
 * compares references, and without the `immer` middleware whatever `set`
 * returns is what becomes the next state.
 *
 * Usage note: the getters below build a new array on every call. Read them via
 * `useInvoiceStore.getState().getAllInvoices()` or inside a `useMemo`, never as
 * a direct selector -- `useInvoiceStore((s) => s.getAllInvoices())` loops
 * forever.
 */
export const useInvoiceStore = create<InvoiceStore>()(
  persist(
    subscribeWithSelector((set, get) => ({
      invoices: {},

      addInvoice: (invoice) =>
        set((state) => ({
          invoices: {
            ...state.invoices,
            [invoice.id]: {
              ...invoice,
              _version: 1,
              // A record the server has never seen starts from 0, which is
              // what tells the sync endpoint to create rather than update.
              _baseVersion: 0,
              _isDirty: true,
              _lastSyncedAt: 0,
            },
          },
        })),

      updateInvoice: (id, updates) =>
        set((state) => {
          const invoice = state.invoices[id];
          if (!invoice) return state;

          return {
            invoices: {
              ...state.invoices,
              [id]: {
                ...invoice,
                ...updates,
                // The version counter feeds the server-side optimistic lock:
                // `updates` must never be allowed to overwrite it. _baseVersion
                // deliberately does not move -- it still records the last state
                // the server confirmed.
                _version: invoice._version + 1,
                _baseVersion: invoice._baseVersion,
                _isDirty: true,
              },
            },
          };
        }),

      deleteInvoice: (id) =>
        set((state) => {
          if (!(id in state.invoices)) return state;

          const { [id]: _removed, ...rest } = state.invoices;
          return { invoices: rest };
        }),

      /**
       * Pending local changes, optionally narrowed to one tenant.
       *
       * The scoping matters: a device that has held sessions for two tenants
       * keeps both sets locally, and pushing one tenant's rows inside another
       * tenant's sync call gets them rejected by row-level security.
       */
      getDirtyInvoices: (tenantId) =>
        Object.values(get().invoices).filter(
          (inv) => inv._isDirty && (!tenantId || inv.tenantId === tenantId),
        ),

      /**
       * Only call this for invoices the server actually accepted. Marking a
       * conflicted invoice as synced discards the local edit for good.
       */
      markSynced: (accepted, syncedAt = Date.now()) =>
        set((state) => {
          const invoices = { ...state.invoices };

          for (const { entityId, version } of accepted) {
            const invoice = invoices[entityId];
            if (invoice) {
              invoices[entityId] = {
                ...invoice,
                // The server's version is authoritative from here on.
                _version: version,
                _baseVersion: version,
                _isDirty: false,
                _lastSyncedAt: syncedAt,
              };
            }
          }

          return { invoices };
        }),

      /**
       * Merge changes made by other sites.
       *
       * A locally dirty invoice is skipped: overwriting it would silently
       * discard an edit the user has not managed to push yet. It stays dirty
       * and the next sync surfaces the clash as a real conflict.
       */
      applyRemoteChanges: (changes, tenantId) =>
        set((state) => {
          const invoices = { ...state.invoices };

          for (const change of changes) {
            const existing = invoices[change.entityId];
            if (existing?._isDirty) continue;

            const incoming = change.data as Partial<Invoice>;
            invoices[change.entityId] = {
              ...(existing ?? ({} as Invoice)),
              ...incoming,
              id: change.entityId,
              // Stamped from the sync context, not from the payload: an event
              // body carries whatever the originating client sent, and an
              // untagged invoice would surface under the wrong tenant.
              tenantId,
              _version: change.version,
              _baseVersion: change.version,
              _isDirty: false,
              _lastSyncedAt: Date.now(),
            } as Invoice;
          }

          return { invoices };
        }),

      getInvoice: (id) => get().invoices[id],

      getAllInvoices: () => Object.values(get().invoices),

      getInvoicesByStatus: (status) =>
        Object.values(get().invoices).filter((inv) => inv.status === status),
    })),
    {
      name: 'hybrid:invoices',
      // Persisting the data is the point: an offline-first app must come back
      // from a reload with its unsynced work intact.
      partialize: (state) => ({ invoices: state.invoices }),
    },
  ),
);
