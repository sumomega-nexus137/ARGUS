"use client";

import clsx from "clsx";
import { useTranslations } from "use-intl";

import { Badge, InlineNote, Metric } from "@/components/ui/primitives";
import { countdown, num } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import type { GapResult } from "@/lib/types";

/** RESOURCE GAP: every row is a full optimizer re-run with one extra unit — computed, never estimated. */
export function GapPanel({ result, outdated }: { result: GapResult; outdated: boolean }) {
  const tg = useTranslations("gap");
  const tsub = useTranslations("subtype");
  const tt = useTranslations("resourceType");
  const tpol = useTranslations("policy");
  const { locale } = useLocale();
  const rows = [...result.options].sort((a, b) => b.delta_value - a.delta_value || b.delta_tasks - a.delta_tasks || b.min_slack_gain_min - a.min_slack_gain_min);
  const best = rows[0];
  return (
    <div className="space-y-3">
      {outdated && <InlineNote tone="stale">{tg("outdated")}</InlineNote>}
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Metric label={tg("baseline")} value={tg("baselineValue", { n: result.baseline.tasks.length, v: num(result.baseline.value_total, 0, locale) })} sub={tpol(result.policy)} />
        <Metric label={tg("bestOption")} value={best && (best.delta_value > 0 || best.delta_tasks > 0) ? (tsub.has(best.subtype) ? tsub(best.subtype) : best.subtype) : "—"}
          sub={best && best.delta_value > 0 ? `${tg("deltaValue")} +${num(best.delta_value, 1, locale)}` : tg("noGain")} tone={best && best.delta_value > 0 ? "ok" : undefined} />
        <Metric label={tg("options")} value={rows.length} />
        <Metric label={tg("computed")} value={`${num(result.duration_s, 1, locale)} s`} />
      </div>
      <InlineNote tone="info">{tg("computedNote")}</InlineNote>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs">
          <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
            <tr><th className="py-1">{tg("option")}</th><th className="text-right">{tg("deltaTasks")}</th><th className="text-right">{tg("deltaValue")}</th><th className="text-right">{tg("slack")}</th><th className="pl-3">{tg("added")}</th></tr>
          </thead>
          <tbody>
            {rows.map((o) => {
              const sub = tsub.has(o.subtype) ? tsub(o.subtype) : o.subtype;
              const gain = o.delta_value > 0 || o.delta_tasks > 0;
              return (
                <tr key={`${o.resource_type}-${o.subtype}`} className={clsx("border-t border-line/60 align-top", gain && "bg-ok/5")}>
                  <td className="py-1.5">
                    <div className="font-semibold">+{o.count} {sub}</div>
                    <div className="text-[10.5px] text-muted">{tt.has(o.resource_type) ? tt(o.resource_type) : o.resource_type}</div>
                    <div className="mt-0.5 text-[11px] text-ink-2">{tg("statement", { count: o.count, subtype: sub, n_tasks: Math.max(0, o.delta_tasks), n_high: o.high_priority_added.length })}</div>
                  </td>
                  <td className={clsx("text-right tabular font-bold", o.delta_tasks > 0 ? "text-ok" : o.delta_tasks < 0 ? "text-crit" : "text-muted")}>{o.delta_tasks > 0 ? "+" : ""}{o.delta_tasks}</td>
                  <td className={clsx("text-right tabular font-bold", o.delta_value > 0 ? "text-ok" : "text-muted")}>{o.delta_value > 0 ? "+" : ""}{num(o.delta_value, 1, locale)}</td>
                  <td className="text-right tabular text-ink-2">{o.min_slack_gain_min > 0.5 ? `+${countdown(o.min_slack_gain_min)}` : "—"}</td>
                  <td className="pl-3">
                    <div className="flex flex-wrap gap-0.5">
                      {o.tasks_added.map((t) => <Badge key={t} tone={o.high_priority_added.includes(t) ? "crit" : "ok"} icon={false}>+{t}</Badge>)}
                      {o.tasks_removed.map((t) => <Badge key={t} tone="muted" icon={false}>−{t}</Badge>)}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
