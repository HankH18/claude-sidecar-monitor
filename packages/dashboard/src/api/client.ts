import { getApiToken } from "./token";
import type { ApiError } from "./types";

export class ApiCallError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiCallError";
  }
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  let code = "http_error";
  let message = `${res.status} ${res.statusText}`;
  try {
    const body = (await res.json()) as ApiError & { detail?: ApiError };
    // FastAPI wraps HTTPException payloads in `detail`; unwrap for both shapes.
    const wrapped = body.detail?.error ?? body.error;
    code = wrapped?.code ?? code;
    message = wrapped?.message ?? message;
  } catch {
    /* body wasn't JSON */
  }
  throw new ApiCallError(res.status, code, message);
}

/**
 * Attach Authorization: Bearer to *every* request — GET included.
 *
 * The token lives on the same page as the dashboard JS (server-rendered
 * meta tag), so adding it to every request is harmless and removes the
 * "which calls are auth-gated?" mental overhead. The collector ignores
 * the header on unauthed routes.
 */
function withAuthHeaders(init?: HeadersInit): HeadersInit {
  const token = getApiToken();
  const base: Record<string, string> = {
    Accept: "application/json",
    ...(init as Record<string, string> | undefined),
  };
  if (token) base.Authorization = `Bearer ${token}`;
  return base;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: withAuthHeaders() });
  return jsonOrThrow<T>(res);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "PATCH",
    headers: withAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return jsonOrThrow<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: withAuthHeaders({ "Content-Type": "application/json" }),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return jsonOrThrow<T>(res);
}

export interface RetryOptions {
  retries?: number;
  baseDelayMs?: number;
}

/**
 * Retry a transient API call with exponential backoff.
 *
 * Retries network failures and 5xx responses. 4xx errors (e.g. 404) are
 * surfaced immediately so callers can short-circuit with the right UI.
 * SSE has its own retry logic in stream.ts.
 */
export async function withRetry<T>(fn: () => Promise<T>, options: RetryOptions = {}): Promise<T> {
  const { retries = 2, baseDelayMs = 300 } = options;
  let lastErr: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      // Don't retry client errors (4xx) — they won't get better.
      if (err instanceof ApiCallError && err.status >= 400 && err.status < 500) {
        throw err;
      }
      if (attempt === retries) break;
      const delay = baseDelayMs * 2 ** attempt;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  throw lastErr;
}
