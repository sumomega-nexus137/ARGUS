// Formatting helpers. The UI never shows undefined / NaN / Infinity: missing values render as "—".
import type { Locale, Names } from "./types";

export const DASH = "—";

export function isNum(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

/** Absolute instant from minutes relative to the scenario reference time. */
export function fromRef(referenceIso: string, minutes: number): Date {
  return new Date(new Date(referenceIso).getTime() + minutes * 60000);
}

/** HH:MM in the operational area's UTC offset (independent of the browser timezone). */
export function hhmm(d: Date | string | null | undefined, utcOffsetMin: number): string {
  if (!d) return DASH;
  const t = typeof d === "string" ? new Date(d) : d;
  if (Number.isNaN(t.getTime())) return DASH;
  const local = new Date(t.getTime() + utcOffsetMin * 60000);
  return `${String(local.getUTCHours()).padStart(2, "0")}:${String(local.getUTCMinutes()).padStart(2, "0")}`;
}

export function dateOnly(d: Date | string | null | undefined, utcOffsetMin: number): string {
  if (!d) return DASH;
  const t = typeof d === "string" ? new Date(d) : d;
  if (Number.isNaN(t.getTime())) return DASH;
  const local = new Date(t.getTime() + utcOffsetMin * 60000);
  return `${String(local.getUTCDate()).padStart(2, "0")}.${String(local.getUTCMonth() + 1).padStart(2, "0")}.${local.getUTCFullYear()}`;
}

export function dateTime(d: Date | string | null | undefined, utcOffsetMin: number): string {
  if (!d) return DASH;
  const t = typeof d === "string" ? new Date(d) : d;
  if (Number.isNaN(t.getTime())) return DASH;
  const local = new Date(t.getTime() + utcOffsetMin * 60000);
  const dd = String(local.getUTCDate()).padStart(2, "0");
  const mm = String(local.getUTCMonth() + 1).padStart(2, "0");
  return `${dd}.${mm}.${local.getUTCFullYear()} ${hhmm(t, utcOffsetMin)}`;
}

export function relHHMM(referenceIso: string | undefined, minutes: number | null | undefined, utcOffsetMin: number): string {
  if (!referenceIso || !isNum(minutes)) return DASH;
  return hhmm(fromRef(referenceIso, minutes), utcOffsetMin);
}

/** Countdown "HH:MM" (or "-HH:MM" when overdue). */
export function countdown(minutes: number | null | undefined): string {
  if (!isNum(minutes)) return DASH;
  const neg = minutes < 0;
  const m = Math.floor(Math.abs(minutes));
  const h = Math.floor(m / 60);
  return `${neg ? "−" : ""}${String(h).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function offsetLabel(minutes: number): string {
  if (!isNum(minutes)) return DASH;
  if (Math.abs(minutes) < 1) return "T";
  const sign = minutes > 0 ? "+" : "−";
  const h = Math.abs(minutes) / 60;
  return `T${sign}${Number.isInteger(h) ? h : h.toFixed(1)}h`;
}

export function num(x: number | null | undefined, digits = 0, locale: Locale = "kk"): string {
  if (!isNum(x)) return DASH;
  const loc = locale === "en" ? "en-US" : locale === "ru" ? "ru-RU" : "kk-KZ";
  return x.toLocaleString(loc, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function pct(x: number | null | undefined, digits = 0): string {
  if (!isNum(x)) return DASH;
  return `${(x * 100).toFixed(digits)}%`;
}

/** Monetary range rounded to 2 significant digits in millions — never false precision. */
export function moneyRangeM(r: { low: number; high: number } | null | undefined): string {
  if (!r || !isNum(r.low) || !isNum(r.high)) return DASH;
  const f = (v: number) => {
    const m = v / 1e6;
    if (m === 0) return "0";
    const digits = m >= 100 ? 0 : m >= 10 ? 0 : 1;
    return m.toFixed(digits);
  };
  return `${f(r.low)}–${f(r.high)}`;
}

export function pickName(n: Names | null | undefined, locale: Locale, fallback = DASH): string {
  if (!n) return fallback;
  return (n[locale] || n.kk || n.ru || n.original || n.en || fallback) as string;
}

export function ageLabel(ageMin: number | null | undefined): string {
  if (!isNum(ageMin)) return DASH;
  if (ageMin < 60) return `${Math.round(ageMin)}′`;
  if (ageMin < 48 * 60) return `${Math.floor(ageMin / 60)}h ${Math.round(ageMin % 60)}′`;
  return `${Math.round(ageMin / 1440)}d`;
}

/** "official_reported · date" → localized tokens via the obsQuality namespace (unknown tokens kept as-is). */
export function qualityLabel(q: string | null | undefined, t: { has: (k: string) => boolean; (k: string): string }): string {
  if (!q) return "";
  return q.split("·").map((x) => x.trim()).map((x) => (t.has(x) ? t(x) : x)).join(" · ");
}
