import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface AuthUser {
  username: string;
  token: string;
  refreshToken: string;
  /** Token expiry, epoch milliseconds, read from the JWT itself. */
  expiresAt: number;
}

interface AuthStore {
  user: AuthUser | null;
  /**
   * False until the persisted session has been read back from localStorage.
   * Rendering "logged out" during that window flashes the login form at an
   * already-authenticated user on every reload.
   */
  isHydrated: boolean;
  setHydrated: () => void;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isExpired: () => boolean;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

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
 * keeps working through an outage for as long as the access token lives
 * (24h by default, see SIMPLE_JWT in myapp/settings.py).
 */
export const useAuth = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      isHydrated: false,

      setHydrated: () => set({ isHydrated: true }),

      login: async (username, password) => {
        const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
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
