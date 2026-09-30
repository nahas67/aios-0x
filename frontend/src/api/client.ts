/**
 * Central API client. Every backend call flows through here:
 * bearer token injection, request IDs, timeouts, typed errors.
 * No component may call fetch() directly.
 */

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let authToken = "";

export function setAuthToken(token: string): void {
  authToken = token.trim();
}

export function hasAuthToken(): boolean {
  return authToken.length > 0;
}

function requestId(): string {
  return `ui-${crypto.randomUUID()}`;
}

async function request<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
  timeoutMs = 15_000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = {
    "X-Request-ID": requestId(),
  };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  try {
    const res = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    if (res.status === 401) {
      throw new ApiError("Authentication required (401). Set your operator token in Settings.", 401);
    }
    if (res.status === 403) {
      const detail = await safeDetail(res);
      throw new ApiError(detail || "Not authorized for this action (403).", 403);
    }
    if (!res.ok) {
      const detail = await safeDetail(res);
      throw new ApiError(detail || `Request failed: HTTP ${res.status}`, res.status);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Request timed out — backend may be overloaded.", 0);
    }
    throw new ApiError("Backend unreachable — is the AIOS server running?", 0);
  } finally {
    clearTimeout(timer);
  }
}

async function safeDetail(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { error?: string };
    return data.error ?? "";
  } catch {
    return "";
  }
}

export const http = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown) => request<T>("POST", path, body),
};
