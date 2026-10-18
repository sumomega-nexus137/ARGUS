// Static online demo (GitHub Pages): the console runs without a server and answers every API request from a
// snapshot recorded by scripts/static_demo/record.py — real ARGUS engine outputs, never invented values.
// Changes (POST / PUT that were not recorded) are refused with a clear, localized "read-only demo" error.

export const IS_STATIC = process.env.NEXT_PUBLIC_STATIC === "1";
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || "";
const DATA_ROOT = `${BASE_PATH}/demo-data`;

interface Entry { f: string; ct: string }
export interface Manifest {
  created: string;
  user: Record<string, unknown>;
  tiles: { maxzoom: number };
  entries: Record<string, Entry>;
}

let manifest: Manifest | null = null;
let pending: Promise<Manifest> | null = null;
/** "shape" of a key with its time number replaced by # → recorded (time, key) pairs, for nearest-time lookups */
let shapes: Map<string, [number, string][]> | null = null;

const TRANSPARENT_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

function num(v: string): string {
  return /^-?\d+(\.\d+)?$/.test(v.trim()) ? String(Number(v)) : v;
}

/** Same canonical form as record.py: path + query sorted by name, numbers normalised. */
export function getKey(path: string): string {
  const u = new URL(path, "http://x");
  const q = [...u.searchParams.entries()].map(([k, v]) => [k, num(v)] as const).sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  return `GET ${u.pathname}${q.length ? `?${q.map(([k, v]) => `${k}=${v}`).join("&")}` : ""}`;
}

function stable(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stable).join(",")}]`;
  if (v && typeof v === "object") {
    return `{${Object.keys(v as object).sort().map((k) => `${JSON.stringify(k)}:${stable((v as Record<string, unknown>)[k])}`).join(",")}}`;
  }
  return JSON.stringify(v);
}

export function postKey(path: string, body: unknown): string {
  const b = { ...((body as Record<string, unknown>) || {}) };
  delete b.as_of_min;
  return `POST ${new URL(path, "http://x").pathname} ${stable(b)}`;
}

/** Key shapes that may be answered by the nearest recorded time: ?t=… and …/frames/<t>/… */
function shapeOf(key: string): [string, number] | null {
  const f = key.match(/^(.*\/frames\/)(-?\d+(?:\.\d+)?)(\/.*)$/);
  if (f) return [`${f[1]}#${f[3]}`, Number(f[2])];
  const t = key.match(/^(GET [^?]*\?(?:.*&)?t=)(-?\d+(?:\.\d+)?)(&.*)?$/);
  if (t) return [`${t[1]}#${t[3] || ""}`, Number(t[2])];
  return null;
}

export function loadManifest(): Promise<Manifest> {
  if (manifest) return Promise.resolve(manifest);
  if (!pending) {
    pending = fetch(`${DATA_ROOT}/manifest.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`manifest ${r.status}`);
        return r.json() as Promise<Manifest>;
      })
      .then((m) => {
        manifest = m;
        shapes = new Map();
        for (const key of Object.keys(m.entries)) {
          const s = shapeOf(key);
          if (!s) continue;
          const list = shapes.get(s[0]) || [];
          list.push([s[1], key]);
          shapes.set(s[0], list);
        }
        return m;
      })
      .catch((e) => {
        pending = null;
        throw e;
      });
  }
  return pending;
}

export function getManifest(): Manifest | null {
  return manifest;
}

function lookupGet(path: string): Entry | null {
  if (!manifest) return null;
  const key = getKey(path);
  const hit = manifest.entries[key];
  if (hit) return hit;
  // a time between recorded frames → nearest recorded time (the snapshot keeps hourly analyses, 10-min flood frames)
  const s = shapeOf(key);
  const list = s && shapes?.get(s[0]);
  if (s && list?.length) {
    const best = list.reduce((a, b) => (Math.abs(b[0] - s[1]) < Math.abs(a[0] - s[1]) ? b : a));
    return manifest.entries[best[1]];
  }
  // "now" requests without t: fall back to the plain path
  return null;
}

function fileUrl(e: Entry): string {
  return `${DATA_ROOT}/${e.f}`;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** fetch() replacement used by the API client in the static build. */
export async function staticFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const m = await loadManifest();
  const method = (init.method || "GET").toUpperCase();
  const url = new URL(path, "http://x").pathname;
  if (method === "POST" && url === "/api/auth/login") return json(200, { token: "static-demo", user: m.user });
  if (method === "GET" && url === "/api/auth/me") return json(200, m.user);
  let entry: Entry | null = null;
  if (method === "GET") entry = lookupGet(path);
  else if (method === "POST") {
    let body: unknown = {};
    try {
      body = typeof init.body === "string" ? JSON.parse(init.body) : {};
    } catch {
      body = {};
    }
    entry = m.entries[postKey(path, body)] || null;
  }
  if (!entry) {
    if (method === "GET") {
      console.debug("[static] not in snapshot:", getKey(path));
      return json(404, { error: { code: "static_missing", message: "Not part of the online demo snapshot" } });
    }
    return json(403, { error: { code: "static_readonly", message: "The online demo is read-only" } });
  }
  const r = await fetch(fileUrl(entry));
  if (!r.ok) return json(404, { error: { code: "static_missing", message: "Snapshot file missing" } });
  return new Response(await r.blob(), { status: 200, headers: { "content-type": entry.ct } });
}

/** Synchronous URL for MapLibre / <img> sources (manifest is loaded before the console renders). */
export function staticAssetUrl(path: string): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const tile = path.match(/^\/api\/tiles\/terrain\/([^/]+)\/(.+)$/);
  if (tile) return `${origin}${DATA_ROOT}/tiles/terrain/${tile[1]}/${tile[2]}`;
  const e = lookupGet(path);
  return e ? `${origin}${fileUrl(e)}` : TRANSPARENT_PNG;
}
