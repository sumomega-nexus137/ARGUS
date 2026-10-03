"use client";

import clsx from "clsx";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";
import { useTranslations } from "use-intl";

import { Badge, InlineNote, Metric, Panel, StatusBadge } from "@/components/ui/primitives";
import { countdown, num } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import type { StressResult, StressScenario } from "@/lib/types";

import { CausalChainView } from "./CausalChain";

const CELL: Record<string, string> = {
  FEASIBLE: "bg-ok/25",
  AT_RISK: "bg-warn/45",
  INFEASIBLE: "bg-crit/70",
  DONE: "bg-line-2",
  IN_PROGRESS: "bg-accent/30",
};

export function useStressKindText() {
  const ts = useTranslations("stress");
  return (s: Pick<StressScenario, "kind" | "params">) => {
    const p: Record<string, string | number> = {};
    for (const k of ["member", "minutes", "road", "resource"]) {
      const v = s.params[k];
      p[k] = typeof v === "number" || typeof v === "string" ? v : "—";
    }
    const key = `kinds.${s.kind}`;
    return ts.has(key) ? ts(key, p) : s.kind;
  };
}

export function StressPanel({ result, outdated, fmt, siteName }: {
  result: StressResult; outdated: boolean; fmt: (m: number | null | undefined) => string; siteName: (id: string) => string;
}) {
  const ts = useTranslations("stress");
  const tm = useTranslations("methodology");
  const { locale } = useLocale();
  const kindText = useStressKindText();
  const [open, setOpen] = useState<string | null>(null);
  const tasks = result.task_criticality.map((c) => c.task);
  const pct = Math.round(result.robustness * 100);

  return (
    <div className="space-y-3">
      {outdated && <InlineNote tone="stale">{ts("outdated")}</InlineNote>}
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Metric big label={ts("robustness")} value={`${result.n_feasible}/${result.n_scenarios}`} tone={pct >= 80 ? "ok" : pct >= 50 ? "warn" : "crit"}
          sub={ts("robustnessValue", { feasible: result.n_feasible, total: result.n_scenarios })} />
        <Metric label={ts("baseline")} value={<StatusBadge ns="evalStatus" code={result.baseline_status} />} sub={ts("member", { member: result.member })} />
        <Metric label={ts("mostCritical")} value={result.task_criticality[0]?.failures ? result.task_criticality[0].task : "—"}
          sub={result.task_criticality[0]?.failures ? ts("failures", { n: result.task_criticality[0].failures }) : undefined} tone="crit" />
        <Metric label={ts("computed")} value={ts("duration", { n: result.n_scenarios, s: num(result.duration_s, 1, locale) })} sub={fmt(result.as_of)} />
      </div>
      <InlineNote tone="info">{ts("notProbability")}</InlineNote>

      <Panel title={ts("criticality")}>
        <div className="space-y-1">
          {result.task_criticality.map((c) => (
            <div key={c.task} className="flex items-center gap-2 text-xs">
              <span className="w-8 font-mono font-bold">{c.task}</span>
              <div className="relative h-3 flex-1 overflow-hidden rounded-[2px] bg-line/60">
                <div className="absolute inset-y-0 left-0 bg-crit/80" style={{ width: `${(c.failures / result.n_scenarios) * 100}%` }} />
                <div className="absolute inset-y-0 bg-warn/60" style={{ left: `${(c.failures / result.n_scenarios) * 100}%`, width: `${(c.at_risk / result.n_scenarios) * 100}%` }} />
              </div>
              <span className="w-40 text-right tabular text-ink-2">{ts("failures", { n: c.failures })}{c.at_risk ? ` · ${ts("atRiskN", { n: c.at_risk })}` : ""}</span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title={ts("matrix")} bodyClass="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-[11px]">
            <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-2 py-1">{ts("scenario")}</th>
                {tasks.map((t) => <th key={t} className="w-8 text-center font-mono">{t}</th>)}
                <th className="px-2 text-right">{ts("minSlack")}</th>
              </tr>
            </thead>
            <tbody>
              {result.scenarios.map((s) => (
                <FragmentRow key={s.id} s={s} tasks={tasks} open={open === s.id} onToggle={() => setOpen(open === s.id ? null : s.id)}
                  label={kindText(s)} fmt={fmt} siteName={siteName} />
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap gap-3 border-t border-line px-2 py-1.5 text-[10.5px] text-muted">
          {(["FEASIBLE", "AT_RISK", "INFEASIBLE"] as const).map((k) => (
            <span key={k} className="flex items-center gap-1"><span className={clsx("inline-block h-2.5 w-2.5 rounded-[2px]", CELL[k])} />{ts(`legend.${k}`)}</span>
          ))}
        </div>
      </Panel>

      <details className="rounded-[4px] border border-line bg-panel p-2 text-[11px] text-ink-2">
        <summary className="cursor-pointer font-semibold text-muted">{tm("title")}</summary>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          <li>{tm("stress.robustness")}</li>
          <li>{tm("stress.perturbations")}</li>
          <li>{tm("stress.limitations")}</li>
        </ul>
      </details>
    </div>
  );
}

function FragmentRow({ s, tasks, open, onToggle, label, fmt, siteName }: {
  s: StressScenario; tasks: string[]; open: boolean; onToggle: () => void; label: string;
  fmt: (m: number | null | undefined) => string; siteName: (id: string) => string;
}) {
  const ts = useTranslations("stress");
  const hasChain = s.chains.length > 0;
  return (
    <Fragment>
      <tr className={clsx("border-t border-line/60", hasChain && "cursor-pointer hover:bg-panel-2", open && "bg-panel-2")} onClick={hasChain ? onToggle : undefined}>
        <td className="px-2 py-1">
          <span className="flex items-center gap-1">
            {hasChain ? (open ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />) : <span className="w-3" />}
            <span className={clsx(s.kind === "BASELINE" && "font-bold")}>{label}</span>
          </span>
        </td>
        {tasks.map((t) => (
          <td key={t} className="px-0.5 py-0.5">
            <div title={`${t}: ${s.task_status[t] || "—"}`} className={clsx("mx-auto h-4 w-6 rounded-[2px]", CELL[s.task_status[t]] || "bg-line/40")} />
          </td>
        ))}
        <td className={clsx("px-2 text-right tabular", s.min_slack !== null && s.min_slack < 0 ? "text-crit" : "text-ink-2")}>
          {s.min_slack !== null ? (s.min_slack < 0 ? `−${countdown(-s.min_slack)}` : countdown(s.min_slack)) : "—"}
        </td>
      </tr>
      {open && (
        <tr className="bg-panel-2">
          <td colSpan={tasks.length + 2} className="space-y-1.5 px-2 pb-2">
            <div className="flex flex-wrap gap-1 pt-1">
              {s.failed_tasks.length > 0 && <Badge tone="crit">{ts("failed")}: {s.failed_tasks.join(", ")}</Badge>}
              {s.at_risk_tasks.length > 0 && <Badge tone="warn">{ts("atRisk")}: {s.at_risk_tasks.join(", ")}</Badge>}
            </div>
            {s.chains.map((c) => <CausalChainView key={c.task} chain={c} fmt={fmt} siteName={siteName} compact />)}
          </td>
        </tr>
      )}
    </Fragment>
  );
}
