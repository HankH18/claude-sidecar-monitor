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
