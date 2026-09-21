'use client';

import { useInvoiceStore, type Invoice, type InvoiceStatus } from '@/lib/stores/useInvoiceStore';

const STATUSES: InvoiceStatus[] = ['draft', 'sent', 'paid'];

export function InvoiceList({ invoices, tenantId }: { invoices: Invoice[]; tenantId: string }) {
  const addInvoice = useInvoiceStore((state) => state.addInvoice);
  const updateInvoice = useInvoiceStore((state) => state.updateInvoice);

  function handleCreate() {
    const sequence = invoices.length + 1;
    addInvoice({
      id: crypto.randomUUID(),
      tenantId,
      number: `${tenantId}-${String(900 + sequence).padStart(3, '0')}`,
      status: 'draft',
      amount: 100,
      dueDate: new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10),
      items: [],
    });
  }

  return (
    <section className="card">
      <div className="row between" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Invoices</h2>
        <button className="primary" onClick={handleCreate}>
          New invoice
        </button>
      </div>

      {invoices.length === 0 ? (
        <p className="muted">
          Nothing local yet. Create an invoice — it is written to this device
          first and pushed on the next sync.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Number</th>
              <th>Status</th>
              <th>Amount</th>
              <th>Version</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((invoice) => (
              <tr key={invoice.id}>
                <td>{invoice.number}</td>
                <td>
                  <select
                    value={invoice.status}
                    onChange={(e) =>
                      updateInvoice(invoice.id, {
                        status: e.target.value as InvoiceStatus,
                      })
                    }
                  >
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{Number(invoice.amount).toFixed(2)}</td>
                <td className="muted">
                  v{invoice._version}
                  {invoice._baseVersion !== invoice._version && (
                    <> (server v{invoice._baseVersion})</>
                  )}
                </td>
                <td>
                  {invoice._isDirty ? (
                    <span className="badge dirty">pending</span>
                  ) : (
                    <span className="badge">synced</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
