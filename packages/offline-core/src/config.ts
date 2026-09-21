/**
 * Runtime configuration.
 *
 * The core is mounted by skins built on different frameworks, so it cannot
 * read a bundler-specific environment variable of its own. The host app calls
 * `configureOfflineCore` once at startup; `NEXT_PUBLIC_API_URL` is honoured as
 * a convenience when it happens to be defined, so a Next.js skin needs no
 * configuration at all.
 */

export interface OfflineCoreConfig {
  /**
   * Absolute origin of the API. It must be absolute: a relative path would
   * resolve against the frontend's own origin, which is not where the API is.
   */
  apiBaseUrl: string;
  /**
   * Identifies this installation in the sync log. The server uses it to avoid
   * echoing a client's own writes back at it, so two devices sharing an origin
   * will each re-receive the other's changes but not their own.
   */
  origin: string;
  /** Milliseconds between automatic sync attempts. */
  syncIntervalMs: number;
  /**
   * Refresh the access token this long before it expires. Too short and a
   * request can leave with a token that dies in flight.
   */
  tokenRefreshLeadMs: number;
}

function readEnvApiUrl(): string | undefined {
  // Guarded: `process` does not exist in every runtime a skin might use.
  try {
    return typeof process !== 'undefined'
      ? process.env?.NEXT_PUBLIC_API_URL
      : undefined;
  } catch {
    return undefined;
  }
}

const config: OfflineCoreConfig = {
  apiBaseUrl: readEnvApiUrl() ?? 'http://localhost:8000',
  origin: 'web',
  syncIntervalMs: 10_000,
  tokenRefreshLeadMs: 5 * 60_000,
};

export function configureOfflineCore(overrides: Partial<OfflineCoreConfig>): void {
  Object.assign(config, overrides);
}

export function getConfig(): Readonly<OfflineCoreConfig> {
  return config;
}

export function apiUrl(path: string): string {
  const base = config.apiBaseUrl.replace(/\/$/, '');
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}
