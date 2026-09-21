'use client';

import { useAuth, useSyncQuery } from '@hybrid/offline-core';
import { useMemo, useState } from 'react';

import { InvoiceList } from '@/components/InvoiceList';
import { LoginForm } from '@/components/LoginForm';
import { SyncStatus } from '@/components/SyncStatus';
import { useInvoiceStore } from '@/lib/stores/invoices';

const TENANTS = ['MOR', 'MUT'];

export default function HomePage() {
  const user = useAuth((state) => state.user);
  const isHydrated = useAuth((state) => state.isHydrated);
  const logout = useAuth((state) => state.logout);

  const [tenantId, setTenantId] = useState(TENANTS[0]);

  // Subscribing to the record itself, not to a getter: a getter returns a new
  // array on every call, which would re-render forever.
  const entities = useInvoiceStore((state) => state.entities);

  // Scoped to the selected tenant, and tombstones filtered out: the device
  // keeps every tenant it has been used for, and showing them together would
  // misrepresent the isolation the server actually enforces.
  const invoices = useMemo(
    () =>
      Object.values(entities).filter(
        (invoice) => invoice.tenantId === tenantId && !invoice._isDeleted,
      ),
    [entities, tenantId],
  );

  const pendingCount = useMemo(
    () =>
      Object.values(entities).filter(
        (invoice) => invoice.tenantId === tenantId && invoice._isDirty,
      ).length,
    [entities, tenantId],
  );

  const sync = useSyncQuery(tenantId);

  if (!isHydrated) {
    return (
      <main>
        <p className="muted">Loading local data…</p>
      </main>
    );
  }

  if (!user) {
    return (
      <main>
        <h1>Hybrid ERP</h1>
        <p className="muted">Offline-first invoicing on the hybrid stack.</p>
        <LoginForm />
      </main>
    );
  }

  return (
    <main>
      <div className="row between" style={{ marginBottom: 20 }}>
        <h1>Hybrid ERP</h1>
        <div className="row">
          <select value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {TENANTS.map((tenant) => (
              <option key={tenant} value={tenant}>
                {tenant}
              </option>
            ))}
          </select>
          <span className="muted">{user.username}</span>
          <button onClick={logout}>Sign out</button>
        </div>
      </div>

      <SyncStatus
        pendingCount={pendingCount}
        conflictCount={sync.data?.conflicts.length ?? 0}
        lastResult={sync.data}
        isFetching={sync.isFetching}
        error={sync.error as Error | null}
      />

      <InvoiceList invoices={invoices} tenantId={tenantId} />

      {sync.data && sync.data.conflicts.length > 0 && (
        <section className="card">
          <h2>Conflicts</h2>
          <p className="muted">
            These records were edited elsewhere while this device held an older
            version. Nothing was overwritten — resolve them from the queue.
          </p>
          <ul>
            {sync.data.conflicts.map((conflict) => (
              <li key={conflict.conflictId}>
                <code>{conflict.entityId.slice(0, 8)}</code> — client v
                {conflict.clientVersion} vs server v{conflict.serverVersion} (
                {conflict.resolution})
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
