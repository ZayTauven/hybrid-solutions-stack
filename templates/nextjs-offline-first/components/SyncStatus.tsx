'use client';

import { useEffect, useState } from 'react';

import type { SyncResponse } from '@/hooks/useSyncQuery';

interface SyncStatusProps {
  pendingCount: number;
  conflictCount: number;
  lastResult?: SyncResponse;
  isFetching: boolean;
  error: Error | null;
}

export function SyncStatus({
  pendingCount,
  conflictCount,
  lastResult,
  isFetching,
  error,
}: SyncStatusProps) {
  const online = useOnlineStatus();

  return (
    <div className="row between card" style={{ marginBottom: 20 }}>
      <div className="row">
        <span className={`badge ${online ? '' : 'dirty'}`}>
          {online ? 'Online' : 'Offline'}
        </span>
        {isFetching && <span className="muted">syncing…</span>}
        {error && <span className="error">{error.message}</span>}
      </div>

      <div className="row">
        {pendingCount > 0 && (
          <span className="badge dirty">{pendingCount} pending</span>
        )}
        {conflictCount > 0 && (
          <span className="badge conflict">{conflictCount} conflict(s)</span>
        )}
        <span className="muted">
          {lastResult
            ? `last sync ${new Date(lastResult.serverTimestamp * 1000).toLocaleTimeString()}`
            : 'never synced'}
        </span>
      </div>
    </div>
  );
}

/**
 * `navigator.onLine` is read after mount, never during render: it does not
 * exist on the server, and reading it while rendering would desynchronise the
 * server-rendered markup from the client's first paint.
 */
function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();

    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);

  return online;
}
