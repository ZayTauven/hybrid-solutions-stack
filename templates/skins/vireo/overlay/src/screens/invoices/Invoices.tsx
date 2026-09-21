/*
 * {{PROJECT_NAME}} — Invoices (route "invoices").
 *
 * The offline-first surface, expressed in the template's own primitives. The
 * page never waits on the network: edits land locally and are pushed when a
 * connection appears, which is why every row carries its sync state.
 */
'use client';

import { useAuth, useSyncQuery } from '@hybrid/offline-core';
import { useMemo, useState } from 'react';

import { PageHead } from '../../components/shell/PageHead';
import {
  useInvoiceStore,
  type Invoice,
  type InvoiceStatus,
} from '../../offline/stores/invoices';

const TENANTS = ['MOR', 'MUT'];
const STATUSES: InvoiceStatus[] = ['draft', 'sent', 'paid'];

const ICON_PLUS = (
  <svg className="ax-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5l0 14" /><path d="M5 12l14 0" /></svg>
);

export function Invoices() {
  const user = useAuth((state) => state.user);
  const isHydrated = useAuth((state) => state.isHydrated);
  const [tenantId, setTenantId] = useState(TENANTS[0]);

  // Subscribing to the record itself, not to a getter: a getter returns a new
  // array on every call, which would re-render forever.
  const entities = useInvoiceStore((state) => state.entities);
  const add = useInvoiceStore((state) => state.add);
  const update = useInvoiceStore((state) => state.update);
  const remove = useInvoiceStore((state) => state.remove);

  const invoices = useMemo(
    () =>
      Object.values(entities).filter(
        (invoice) => invoice.tenantId === tenantId && !invoice._isDeleted,
      ),
    [entities, tenantId],
  );

  const pending = useMemo(
    () => invoices.filter((invoice) => invoice._isDirty).length,
    [invoices],
  );

  const sync = useSyncQuery(tenantId);

  function createInvoice() {
    add({
      id: crypto.randomUUID(),
      tenantId,
      number: `${tenantId}-${String(900 + invoices.length + 1).padStart(3, '0')}`,
      status: 'draft',
      amount: 100,
      dueDate: new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10),
      items: [],
    });
  }

  if (!isHydrated) {
    return <PageHead title="Invoices" subtitle="Reading local data…" />;
  }

  if (!user) {
    return (
      <PageHead
        title="Invoices"
        subtitle="Sign in to load this device's data."
      />
    );
  }

  return (
    <>
      <PageHead
        title="Invoices"
        subtitle="Written to this device first, pushed when a connection appears."
        actions={
          <>
            <select
              className="ax-input"
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
              aria-label="Tenant"
            >
              {TENANTS.map((tenant) => (
                <option key={tenant} value={tenant}>{tenant}</option>
              ))}
            </select>
            <button type="button" className="ax-btn ax-btn--primary" onClick={createInvoice}>
              {ICON_PLUS}<span className="ax-btn__label">New invoice</span>
            </button>
          </>
        }
      />

      <div className="ax-dash-grid">
        <SyncBanner
          pending={pending}
          conflicts={sync.data?.conflicts.length ?? 0}
          serverTimestamp={sync.data?.serverTimestamp}
          isFetching={sync.isFetching}
          error={sync.error as Error | null}
        />

        <section className="ax-card ax-col--12" role="region" aria-label="Invoices">
          <div className="ax-card__body">
            {invoices.length === 0 ? (
              <p style={{ margin: 0, fontSize: 'var(--ax-text-sm)', color: 'var(--ax-text-muted)' }}>
                Nothing local yet. Create an invoice — it is stored on this device
                immediately and synced when the network allows.
              </p>
            ) : (
              <table className="ax-table">
                <thead>
                  <tr>
                    <th>Number</th>
                    <th>Status</th>
                    <th>Amount</th>
                    <th>Version</th>
                    <th>State</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <InvoiceRow
                      key={invoice.id}
                      invoice={invoice}
                      onStatusChange={(status) => update(invoice.id, { status })}
                      onDelete={() => remove(invoice.id)}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

function InvoiceRow({
  invoice,
  onStatusChange,
  onDelete,
}: {
  invoice: Invoice;
  onStatusChange: (status: InvoiceStatus) => void;
  onDelete: () => void;
}) {
  return (
    <tr>
      <td>{invoice.number}</td>
      <td>
        <select
          className="ax-input"
          value={invoice.status}
          onChange={(event) => onStatusChange(event.target.value as InvoiceStatus)}
          aria-label={`Status of ${invoice.number}`}
        >
          {STATUSES.map((status) => (
            <option key={status} value={status}>{status}</option>
          ))}
        </select>
      </td>
      <td>{Number(invoice.amount).toFixed(2)}</td>
      <td style={{ color: 'var(--ax-text-muted)' }}>
        v{invoice._version}
        {invoice._baseVersion !== invoice._version && <> (server v{invoice._baseVersion})</>}
      </td>
      <td>
        <span className={`ax-badge ${invoice._isDirty ? 'ax-badge--warn' : 'ax-badge--muted'}`}>
          {invoice._isDirty ? 'pending' : 'synced'}
        </span>
      </td>
      <td>
        {/* The row goes immediately, but the deletion is kept as a tombstone
            until the server acknowledges it. */}
        <button type="button" className="ax-btn ax-btn--ghost" onClick={onDelete}>
          <span className="ax-btn__label">Delete</span>
        </button>
      </td>
    </tr>
  );
}

function SyncBanner({
  pending,
  conflicts,
  serverTimestamp,
  isFetching,
  error,
}: {
  pending: number;
  conflicts: number;
  serverTimestamp?: number;
  isFetching: boolean;
  error: Error | null;
}) {
  return (
    <section className="ax-card ax-col--12" role="status" aria-label="Sync state">
      <div
        className="ax-card__body ax-cluster"
        style={{ justifyContent: 'space-between', gap: 'var(--ax-space-3)' }}
      >
        <span style={{ fontSize: 'var(--ax-text-sm)', color: 'var(--ax-text-muted)' }}>
          {isFetching ? 'Syncing…' : error ? error.message : 'Idle'}
        </span>

        <span className="ax-cluster" style={{ gap: 'var(--ax-space-3)' }}>
          {pending > 0 && <span className="ax-badge ax-badge--warn">{pending} pending</span>}
          {conflicts > 0 && <span className="ax-badge ax-badge--danger">{conflicts} conflict(s)</span>}
          <span style={{ fontSize: 'var(--ax-text-sm)', color: 'var(--ax-text-muted)' }}>
            {serverTimestamp
              ? `last sync ${new Date(serverTimestamp * 1000).toLocaleTimeString()}`
              : 'never synced'}
          </span>
        </span>
      </div>
    </section>
  );
}
