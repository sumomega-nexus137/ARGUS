// Semantic status → visual tone. Every status is ALWAYS rendered with text (and usually an icon),
// never by colour alone (accessibility).

export type Tone = "ok" | "watch" | "warn" | "crit" | "info" | "sim" | "muted" | "live" | "stale" | "offline";

export const TONE_CLASS: Record<Tone, string> = {
  ok: "text-ok border-ok/40 bg-ok/10",
  watch: "text-watch border-watch/40 bg-watch/10",
  warn: "text-warn border-warn/40 bg-warn/10",
  crit: "text-crit border-crit/50 bg-crit/12",
  info: "text-accent border-accent/40 bg-accent/10",
  sim: "text-sim border-sim/40 bg-sim/10",
  muted: "text-muted border-line-2 bg-panel-2",
  live: "text-live border-live/40 bg-live/10",
  stale: "text-stale border-stale/40 bg-stale/10",
  offline: "text-offline border-offline/40 bg-offline/10",
};

export const TONE_TEXT: Record<Tone, string> = {
  ok: "text-ok", watch: "text-watch", warn: "text-warn", crit: "text-crit", info: "text-accent", sim: "text-sim",
  muted: "text-muted", live: "text-live", stale: "text-stale", offline: "text-offline",
};

export const TONE_HEX: Record<Tone, string> = {
  ok: "#34c38f", watch: "#e2c541", warn: "#f59e2b", crit: "#ef4d4d", info: "#3fb3ff", sim: "#a78bfa",
  muted: "#738396", live: "#34c38f", stale: "#e0a13a", offline: "#ef4d4d",
};

const MAP: Record<string, Tone> = {
  // area
  NORMAL: "ok", WATCH: "watch", WARNING: "warn", CRITICAL: "crit",
  // roads
  OPEN: "ok", AT_RISK: "watch", CLOSES_IN: "warn", RESTRICTED: "warn", CLOSED: "crit",
  // windows
  SAFE: "ok", WINDOW_CLOSING: "warn", WINDOW_MISSED: "crit", NO_DEADLINE: "muted", NO_ROUTE: "crit",
  // plan / eval
  PLAN_VALID: "ok", PLAN_AT_RISK: "crit", FEASIBLE: "ok", INFEASIBLE: "crit", IN_PROGRESS: "info",
  DRAFT: "muted", REVIEWED: "info", APPROVED: "ok", ACTIVE: "live", SUPERSEDED: "muted", REJECTED: "crit",
  // tasks
  PENDING: "muted", EN_ROUTE: "info", WORKING: "info", DONE: "ok", FAILED: "crit", BLOCKED: "crit",
  RESOURCE_UNAVAILABLE: "crit",
  // data modes / freshness
  LIVE: "live", CACHED: "info", HISTORICAL: "info", SIMULATION: "sim", STATIC: "muted", STALE: "stale",
  OFFLINE: "offline", NOT_CONFIGURED: "muted", NOT_POLLED: "muted", UNKNOWN: "muted", OK: "ok", DEGRADED: "warn", OPERATIONAL: "info",
  // verification
  VERIFIED: "ok", UNVERIFIED: "watch", SIMULATED: "sim",
  // resources
  AVAILABLE: "ok", UNAVAILABLE: "muted",
  // validation
  READY: "ok", PARTIAL: "watch", NOT_LOADED: "muted",
  // imports
  VALID: "ok", INVALID: "crit", PREVIEW: "info", CONFIRMED: "ok", CANCELLED: "muted",
};

export function toneOf(code: string | null | undefined): Tone {
  return (code && MAP[code]) || "muted";
}

export const ROAD_STATE_COLOR = { 0: "#3a8f6a", 1: "#f59e2b", 2: "#ef4d4d" } as const;
