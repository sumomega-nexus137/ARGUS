// ARGUS backend client. All data flows through the ARGUS API (never directly to external providers).
// In the static online demo build the same calls are answered from the recorded snapshot (lib/staticDemo).

import { IS_STATIC, staticAssetUrl, staticFetch } from "./staticDemo";

export class ApiError extends Error {
  status: number;
  code: string;
  params: Record<string, unknown>;
  constructor(status: number, code: string, message: string, params: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.params = params;
  }
}

const TOKEN_KEY = "argus.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session-only */
  }
}

type Json = Record<string, unknown> | unknown[] | null;

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = IS_STATIC ? await staticFetch(path, { ...init, headers, body }) : await fetch(path, { ...init, headers, body });
  } catch {
    throw new ApiError(0, "network_unavailable", "ARGUS server unreachable");
  }
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/login")) {
    setToken(null);
    window.dispatchEvent(new Event("argus:unauthorized"));
  }
  const ct = res.headers.get("content-type") || "";
  if (!res.ok) {
    let code = "http_error";
    let message = res.statusText;
    let params: Record<string, unknown> = {};
    if (ct.includes("application/json")) {
      const j = (await res.json().catch(() => null)) as { error?: { code: string; message: string; params?: Record<string, unknown> } } | null;
      if (j?.error) {
        code = j.error.code;
        message = j.error.message;
        params = j.error.params || {};
      }
    } else if (res.status >= 500) {
      code = res.status === 502 || res.status === 504 ? "network_unavailable" : "internal_error";
    }
    throw new ApiError(res.status, code, message, params);
  }
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export const post = <T = unknown>(path: string, json?: Json | object) => api<T>(path, { method: "POST", json: json ?? {} });
export const put = <T = unknown>(path: string, json?: Json | object) => api<T>(path, { method: "PUT", json: json ?? {} });

export async function upload<T = unknown>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  return api<T>(path, { method: "POST", body: fd });
}

/** Raw (non-JSON) request to the ARGUS API with the session token — images, HTML reports, GeoJSON. */
export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (IS_STATIC) return staticFetch(path, init);
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(path, { ...init, headers });
}

/** Link target for a downloadable API file (templates). */
export function apiHref(path: string): string {
  return IS_STATIC ? staticAssetUrl(path) : path;
}

/** Adds the bearer token to MapLibre requests for ARGUS API resources (images, tiles, GeoJSON). */
export function mapTransformRequest(url: string): { url: string; headers?: Record<string, string> } {
  if (IS_STATIC) return { url };
  const token = getToken();
  if (token && (url.startsWith("/api/") || url.includes(`${typeof window !== "undefined" ? window.location.host : ""}/api/`))) {
    return { url, headers: { Authorization: `Bearer ${token}` } };
  }
  return { url };
}

/** Absolute same-origin URL. String concatenation keeps tile templates ({z}/{x}/{y}) unencoded. */
export function absUrl(path: string): string {
  if (IS_STATIC && path.startsWith("/api/")) return staticAssetUrl(path);
  if (typeof window === "undefined" || /^https?:/.test(path)) return path;
  return `${window.location.origin}${path.startsWith("/") ? "" : "/"}${path}`;
}
