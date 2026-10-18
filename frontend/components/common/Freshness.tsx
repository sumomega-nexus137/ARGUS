"use client";

import { useTranslations } from "use-intl";

import { Badge } from "@/components/ui/primitives";
import { ageLabel, dateTime } from "@/lib/format";
import { toneOf } from "@/lib/status";
import type { Freshness } from "@/lib/types";

export function FreshnessTable({ rows, utcOffset, compact }: { rows: Freshness[]; utcOffset: number; compact?: boolean }) {
  const t = useTranslations("freshness");
  const tm = useTranslations("mode");
  const sorted = [...rows].sort((a, b) => Number(a.is_external) - Number(b.is_external) || a.layer.localeCompare(b.layer));
  return (
    <table className="w-full text-[11.5px]">
      <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
        <tr>
          <th className="py-1 pr-2 font-semibold">{t("layer")}</th>
          {!compact && <th className="py-1 pr-2 font-semibold">{t("source")}</th>}
          <th className="py-1 pr-2 font-semibold">{t("mode")}</th>
          <th className="py-1 pr-2 font-semibold">{t("lastSuccess")}</th>
          <th className="py-1 font-semibold">{t("age")}</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => (
          <tr key={r.id} className="border-t border-line/60 align-top">
            <td className="py-1 pr-2 text-ink">{t.has(`layers.${r.layer}`) ? t(`layers.${r.layer}`) : r.layer}</td>
            {!compact && <td className="py-1 pr-2 text-ink-2" title={r.message ?? undefined}>{r.source}</td>}
            <td className="py-1 pr-2"><Badge tone={toneOf(r.freshness)}>{tm.has(r.freshness) ? tm(r.freshness) : r.freshness}</Badge></td>
            <td className="tabular py-1 pr-2 text-ink-2">{r.freshness === "STATIC" ? "—" : dateTime(r.last_success_at, utcOffset)}</td>
            <td className="tabular py-1 text-ink-2">{r.freshness === "STATIC" || r.freshness === "NOT_CONFIGURED" ? "—" : ageLabel(r.age_min)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function FreshnessSummary({ rows }: { rows: Freshness[] }) {
  const tm = useTranslations("mode");
  const counts: Record<string, number> = {};
  rows.forEach((r) => (counts[r.freshness] = (counts[r.freshness] || 0) + 1));
  return (
    <div className="flex flex-wrap gap-1">
      {Object.entries(counts).map(([k, n]) => (
        <Badge key={k} tone={toneOf(k)}>{tm.has(k) ? tm(k) : k} · {n}</Badge>
      ))}
    </div>
  );
}
