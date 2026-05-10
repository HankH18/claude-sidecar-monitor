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
    const body = (await res.json()) as ApiError;
    code = body.error?.code ?? code;
    message = body.error?.message ?? message;
  } catch {
    /* body wasn't JSON */
  }
  throw new ApiCallError(res.status, code, message);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  return jsonOrThrow<T>(res);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
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
