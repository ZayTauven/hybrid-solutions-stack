import { createEntityStore, type SyncedEntity } from '@hybrid/offline-core';

export type InvoiceStatus = 'draft' | 'sent' | 'paid';

export interface LineItem {
  id: string;
  description: string;
  quantity: number;
  unitPrice: number;
}

/**
 * Line items travel with their invoice rather than as their own entity: the
 * invoice is the unit of synchronisation, so a line edit and a header edit
 * made on two sites conflict as one document instead of diverging into an
 * invoice whose total no longer matches its lines.
 */
export interface Invoice extends SyncedEntity {
  number: string;
  status: InvoiceStatus;
  amount: number;
  dueDate: string;
  items: LineItem[];
}

/**
 * Everything offline-first about this store -- versioning, tombstones,
 * conflict-safe merging, persistence -- comes from the core. A new synced
 * entity costs exactly this much.
 */
export const useInvoiceStore = createEntityStore<Invoice>({
  entityType: 'invoice',
});
