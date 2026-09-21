'use client';

import { configureOfflineCore } from '@hybrid/offline-core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

// Configured at module scope so it is in place before any store or hook reads
// it. The core has no bundler of its own and cannot read NEXT_PUBLIC_* on its
// own behalf in every skin.
configureOfflineCore({
  apiBaseUrl: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  origin: process.env.NEXT_PUBLIC_SYNC_ORIGIN ?? 'web',
});

export function OfflineProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Being offline is the expected state here, not an error worth
            // hammering the network over. The sync query drives its own
            // interval; everything else stays quiet until asked.
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 30_000,
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
