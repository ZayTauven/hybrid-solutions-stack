import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { apiUrl, getConfig } from './config';
import type { AuthUser } from './types';

interface AuthStore {
  user: AuthUser | null;
  /**
   * False until the persisted session has been read back from localStorage.
   * Rendering "logged out" during that window flashes the login form at an
   * already-authenticated user on every reload.
   */
  isHydrated: boolean;
  setHydrated: () => void;
  setUser: (user: AuthUser | null) => void;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isExpired: () => boolean;
}

/**
 * Read the `exp` claim without verifying the signature.
 *
 * The client cannot verify anything -- it does not hold the signing key, and
 * the server re-validates every call regardless. This exists only so the app
 * knows when to stop trying while offline, instead of queueing work against a
 * token that expired hours ago.
 */
function readExpiry(token: string): number {
  try {
    const [, payload] = token.split('.');
    const normalised = payload.replace(/-/g, '+').replace(/_/g, '/');
    const decoded = JSON.parse(atob(normalised)) as { exp?: number };
    return decoded.exp ? decoded.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

/**
 * Authentication that survives losing the network.
 *
 * The session is persisted, so a field device that logs in while connected
 * keeps working through an outage for as long as the access token lives.
 */
export const useAuth = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      isHydrated: false,

      setHydrated: () => set({ isHydrated: true }),
      setUser: (user) => set({ user }),

      login: async (username, password) => {
        const response = await fetch(apiUrl('/api/auth/login'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        });

        if (!response.ok) {
          throw new Error(
            response.status === 401
              ? 'Invalid username or password.'
              : `Login failed: ${response.status}`,
          );
        }

        const data = (await response.json()) as { access: string; refresh: string };

        set({
          user: {
            username,
            token: data.access,
            refreshToken: data.refresh,
            expiresAt: readExpiry(data.access),
          },
        });
      },

      logout: () => set({ user: null }),

      isExpired: () => {
        const { user } = get();
        return !user || user.expiresAt <= Date.now();
      },
    }),
    {
      name: 'hybrid:auth',
      // Only the session is persisted; the actions are recreated on load.
      partialize: (state) => ({ user: state.user }),
      onRehydrateStorage: () => (state) => state?.setHydrated(),
    },
  ),
);

/**
 * Shared in-flight refresh.
 *
 * Several stores can sync at once and all notice the token is stale together.
 * Without this, each would fire its own refresh, and the losers would install
 * tokens older than the winner's.
 */
let refreshInFlight: Promise<AuthUser | null> | null = null;

async function performRefresh(): Promise<AuthUser | null> {
  const { user } = useAuth.getState();
  if (!user?.refreshToken) return null;

  try {
    const response = await fetch(apiUrl('/api/auth/refresh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: user.refreshToken }),
    });

    if (!response.ok) {
      // A refused refresh token is terminal: the session is genuinely over.
      // A network failure is not, so only clear on an actual rejection.
      if (response.status === 401 || response.status === 403) {
        useAuth.getState().logout();
      }
      return null;
    }

    const data = (await response.json()) as { access: string; refresh?: string };
    const next: AuthUser = {
      ...user,
      token: data.access,
      // The server may rotate the refresh token; keep the old one if it does not.
      refreshToken: data.refresh ?? user.refreshToken,
      expiresAt: readExpiry(data.access),
    };

    useAuth.getState().setUser(next);
    return next;
  } catch {
    // Offline. The existing token stays valid until it actually expires, which
    // is the whole point of a long-lived access token in the field.
    return null;
  }
}

export function refreshSession(): Promise<AuthUser | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/**
 * The access token to send, refreshed first if it is about to expire.
 *
 * Returns the current token when offline even if a refresh was due: it may
 * still be valid, and the alternative is refusing to work at all.
 */
export async function getAccessToken(): Promise<string | null> {
  const { user } = useAuth.getState();
  if (!user) return null;

  const expiresIn = user.expiresAt - Date.now();
  if (expiresIn > getConfig().tokenRefreshLeadMs) return user.token;

  const refreshed = await refreshSession();
  if (refreshed) return refreshed.token;

  return expiresIn > 0 ? user.token : null;
}

/**
 * `fetch` with the bearer token attached, retrying once on 401.
 *
 * The retry covers the case the lead time cannot: a token that was fine when
 * the request left and expired before it arrived, or one revoked server-side.
 */
export async function authorizedFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = await getAccessToken();
  if (!token) throw new Error('Not authenticated.');

  const send = (bearer: string) =>
    fetch(apiUrl(path), {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${bearer}` },
    });

  const response = await send(token);
  if (response.status !== 401) return response;

  const refreshed = await refreshSession();
  if (!refreshed) return response;

  return send(refreshed.token);
}
