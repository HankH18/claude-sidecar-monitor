/**
 * Reads the per-install API secret from a server-rendered meta tag on the
 * dashboard shell:
 *
 *   <meta name="csm-token" content="abc123...">
 *
 * The collector substitutes the placeholder at request time so the secret
 * never gets baked into the static bundle. In dev / test (jsdom) the meta
 * tag won't exist; in that case we return the empty string and any auth-
 * gated call will get a 401 / 503 — fine, because the dev workflow uses
 * `csm install` to bootstrap a real secret before pointing the dashboard
 * at the live collector.
 *
 * Read once at module load — the token doesn't change for the lifetime of
 * the page. Calls to `getApiToken()` are O(1).
 */

const TEMPLATE_PLACEHOLDER = "__CSM_TOKEN__";

function readMetaToken(): string {
  if (typeof document === "undefined") return "";
  const el = document.querySelector('meta[name="csm-token"]');
  if (!el) return "";
  const raw = (el.getAttribute("content") ?? "").trim();
  // The static index.html ships with the placeholder string so the build
  // can succeed before the backend substitutes it in. Treat that as empty.
  if (!raw || raw === TEMPLATE_PLACEHOLDER) return "";
  return raw;
}

let cached: string | null = null;

export function getApiToken(): string {
  if (cached === null) cached = readMetaToken();
  return cached;
}

/** Test-only escape hatch — reset the cached token after stubbing the DOM. */
export function _resetApiTokenCacheForTests(): void {
  cached = null;
}
