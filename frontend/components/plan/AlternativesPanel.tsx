"use client";

import clsx from "clsx";
import { Check, Cpu, Scale, X } from "lucide-react";
import { Fragment } from "react";
import { useTranslations } from "use-intl";

import { Badge, Button, InlineNote, inputCls, Metric, StatusBadge } from "@/components/ui/primitives";
import { countdown, num } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import type { Alternative, OptimizationResult, ResourceRow } from "@/lib/types";
import { useNames } from "@/lib/useNames";

import { WhyTask } from "./WhyTask";

export const POLICIES = ["LIFE_SAFETY", "CRITICAL_INFRASTRUCTURE", "ECONOMIC_LOSS", "BALANCED"] as const;
export type Policy = (typeof POLICIES)[number];
export type Weights = { life: number; infra: number; economic: number };

/** Policy + human-set weights + what-if unavailability. ARGUS never picks the moral priorities itself. */
export function OptimizerControls({ policy, weights, onPolicy, onWeights, whatIf, onWhatIf, resources, pool }: {
  policy: Policy; weights: Weights; onPolicy: (p: Policy) => void; onWeights: (w: Weights) => void;
  whatIf: string[]; onWhatIf: (ids: string[]) => void; resources: ResourceRow[]; pool?: React.ReactNode;
}) {
  const tp = useTranslations("plan");
  const tpol = useTranslations("policy");
  const to = useTranslations("optimizer");
  const tt = useTranslations("resourceType");
  const sum = weights.life + weights.infra + weights.economic;
  const selectable = resources.filter((r) => r.status === "AVAILABLE" && !whatIf.includes(r.id) && ["CREW", "VEHICLE", "PUMP", "EQUIPMENT"].includes(r.resource_type));
  return (
    <div className="space-y-2">
      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{tp("policy")}</div>
        <div role="radiogroup" aria-label={tp("policy")} className="flex flex-wrap gap-1">
          {POLICIES.map((p) => (
            <button key={p} role="radio" aria-checked={policy === p} onClick={() => onPolicy(p)}
              className={clsx("rounded-[3px] border px-2 py-1 text-[11px] font-semibold", policy === p ? "border-accent bg-accent/15 text-accent" : "border-line-2 text-ink-2 hover:border-accent/50")}>
              {tpol(p)}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {(["life", "infra", "economic"] as const).map((k) => (
          <label key={k} className="block text-[11px]">
            <span className="flex justify-between"><span className="text-ink-2">{tp(k)}</span><span className="tabular font-bold">{weights[k]}{sum > 0 ? ` · ${Math.round((weights[k] / sum) * 100)}%` : ""}</span></span>
            <input type="range" min={0} max={100} step={5} value={weights[k]} aria-label={tp(k)} className="w-full accent-[var(--color-accent)]"
              onChange={(e) => onWeights({ ...weights, [k]: Number(e.target.value) })} />
          </label>
        ))}
      </div>
      <p className="flex items-center gap-1 text-[10.5px] text-muted"><Scale className="h-3 w-3" />{tp("weightsNote")}</p>
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="font-semibold text-ink-2">{to("whatIfPumps")}:</span>
        {whatIf.map((id) => (
          <button key={id} onClick={() => onWhatIf(whatIf.filter((x) => x !== id))} className="inline-flex items-center gap-0.5 rounded-[3px] border border-warn/50 bg-warn/10 px-1.5 py-[1px] font-mono text-warn">
            {id}<X className="h-3 w-3" aria-label="remove" />
          </button>
        ))}
        <select className={clsx(inputCls, "w-40")} value="" aria-label={to("whatIfPumps")} onChange={(e) => e.target.value && onWhatIf([...whatIf, e.target.value])}>
          <option value="">{to("addUnavailable")}</option>
          {(["CREW", "VEHICLE", "PUMP", "EQUIPMENT"] as const).map((type) => (
            <optgroup key={type} label={tt(type)}>
              {selectable.filter((r) => r.resource_type === type).map((r) => <option key={r.id} value={r.id}>{r.id}</option>)}
            </optgroup>
          ))}
        </select>
        {pool}
      </div>
    </div>
  );
}

export function AlternativesView({ run, areaId, fmt, selected, onSelect, selectedTask, onSelectTask, onAdopt, adopting, canAdopt, outdated, facilityName, sectorName }: {
  run: OptimizationResult; areaId: string; fmt: (m: number | null | undefined) => string;
  selected: string | null; onSelect: (id: string) => void; selectedTask: string | null; onSelectTask: (c: string | null) => void;
  onAdopt: (altId: string) => void; adopting: boolean; canAdopt: boolean; outdated: boolean;
  facilityName: (id: string) => string; sectorName: (id: string) => string;
}) {
  const to = useTranslations("optimizer");
  const tpol = useTranslations("policy");
  const tp = useTranslations("plan");
  const tm = useTranslations("methodology");
  const { locale } = useLocale();
  const alt = run.alternatives.find((a) => a.id === selected) || run.alternatives[0];

  return (
    <div className="space-y-3">
      {outdated && <InlineNote tone="stale">{to("outdated")}</InlineNote>}
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-2">
        <Badge tone="info" icon={false}><Cpu className="mr-0.5 inline h-3 w-3" />CP-SAT</Badge>
        <span>{tpol(run.policy)} · {tp("life")} {run.weights.life ?? 0} / {tp("infra")} {run.weights.infra ?? 0} / {tp("economic")} {run.weights.economic ?? 0}</span>
        <span className="text-muted">· {to("computedIn", { s: num(run.duration_s, 1, locale), n: run.candidates.length })}</span>
        {run.what_if_unavailable.length > 0 && <Badge tone="warn">{to("whatIfPumps")}: {run.what_if_unavailable.join(", ")}</Badge>}
      </div>
      <InlineNote tone="info">{to("verified")}</InlineNote>
      {!run.feasible || run.alternatives.length === 0 ? (
        <InlineNote tone="crit">{to("noFeasible")}</InlineNote>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
            {run.alternatives.map((a) => (
              <AltCard key={a.id} a={a} active={alt?.id === a.id} onClick={() => onSelect(a.id)} fmt={fmt} />
            ))}
          </div>
          {alt && (
            <div className="space-y-2 rounded-[4px] border border-accent/40 bg-panel p-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-bold">{alt.id} · {to.has(`labels.${alt.label}`) ? to(`labels.${alt.label}`) : alt.label}</div>
                <div className="flex items-center gap-2">
                  <span className="text-[10.5px] text-muted">{to("solverStatus", { status: alt.solver.status, time: num(alt.solver.solve_time_s, 2, locale) })}</span>
                  {canAdopt && <Button size="sm" variant="primary" icon={Check} busy={adopting} onClick={() => onAdopt(alt.id)}>{tp("adopt")}</Button>}
                </div>
              </div>
              <AltTasks alt={alt} areaId={areaId} fmt={fmt} selectedTask={selectedTask} onSelectTask={onSelectTask} facilityName={facilityName} sectorName={sectorName} />
              {alt.excluded_candidates.length > 0 && (
                <div className="text-[11px]">
                  <span className="font-semibold text-muted">{to("excluded")}: </span>
                  {alt.excluded_candidates.map((e) => (
                    <span key={e.code} className="mr-2"><span className="font-mono font-bold">{e.code}</span> <span className="text-muted">({to.has(`excludedReason.${e.reason}`) ? to(`excludedReason.${e.reason}`) : e.reason}; {to("value")} {num(e.value, 1, locale)})</span></span>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
      <details className="rounded-[4px] border border-line bg-panel p-2 text-[11px] text-ink-2">
        <summary className="cursor-pointer font-semibold text-muted">{tm("title")}</summary>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          <li>{tm("optimizer.objective")}</li>
          <li>{tm("optimizer.value")}</li>
          <li>{tm("optimizer.verification")}</li>
          <li>{tm("optimizer.modes")}</li>
          <li>{tm("optimizer.solver")}</li>
        </ul>
      </details>
    </div>
  );
}

function AltCard({ a, active, onClick, fmt }: { a: Alternative; active: boolean; onClick: () => void; fmt: (m: number | null | undefined) => string }) {
  const to = useTranslations("optimizer");
  const { locale } = useLocale();
  const d = a.diff_vs_human;
  const rob = a.robustness;
  return (
    <button onClick={onClick} aria-pressed={active}
      className={clsx("rounded-[4px] border p-2 text-left", active ? "border-accent bg-accent/10" : "border-line bg-panel hover:border-line-2")}>
      <div className="flex items-start justify-between gap-1">
        <div>
          <div className="text-[10px] font-bold text-muted">{a.id}</div>
          <div className="text-[12.5px] font-bold leading-tight">{to.has(`labels.${a.label}`) ? to(`labels.${a.label}`) : a.label}</div>
        </div>
        <StatusBadge ns="evalStatus" code={a.evaluation.status} icon={false} />
      </div>
      <div className="mt-1.5 grid grid-cols-3 gap-1">
        <Metric label={to("tasksSelected")} value={a.metrics.tasks_selected} />
        <Metric label={to("value")} value={num(a.metrics.value_total, 0, locale)} />
        <Metric label={to("minSlack")} value={a.metrics.min_slack !== null ? countdown(a.metrics.min_slack) : "—"} tone={a.metrics.min_slack !== null && a.metrics.min_slack < 20 ? "warn" : undefined} />
        <Metric label={to("pumps")} value={a.metrics.pumps_used} />
        <Metric label={to("crews")} value={a.metrics.crews_used} />
        <Metric label={to("robustness")} value={rob ? `${rob.n_feasible}/${rob.n_scenarios}` : "—"} />
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1 text-[10.5px]">
        {d.added.map((c) => <Badge key={`a${c}`} tone="ok" icon={false}>+{c}</Badge>)}
        {d.removed.map((c) => <Badge key={`r${c}`} tone="crit" icon={false}>−{c}</Badge>)}
        {d.reassigned.map((r) => <Badge key={`s${r.task}`} tone="info" icon={false}>{r.task} {r.from}→{r.to}</Badge>)}
        {d.retimed.slice(0, 6).map((r) => <Badge key={`t${r.task}`} tone="muted" icon={false}>{r.task} {fmt(r.from)}→{fmt(r.to)}</Badge>)}
        {d.retimed.length > 6 && <Badge tone="muted" icon={false}>+{d.retimed.length - 6}</Badge>}
        {d.added.length + d.removed.length + d.reassigned.length + d.retimed.length === 0 && <span className="text-muted">{to("noChanges")}</span>}
      </div>
    </button>
  );
}

function AltTasks({ alt, areaId, fmt, selectedTask, onSelectTask, facilityName, sectorName }: {
  alt: Alternative; areaId: string; fmt: (m: number | null | undefined) => string; selectedTask: string | null; onSelectTask: (c: string | null) => void;
  facilityName: (id: string) => string; sectorName: (id: string) => string;
}) {
  const tp = useTranslations("plan");
  const to = useTranslations("optimizer");
  const names = useNames(areaId);
  const evalBy = new Map(alt.evaluation.tasks.map((t) => [t.code, t]));
  const changed = new Set([...alt.diff_vs_human.added, ...alt.diff_vs_human.reassigned.map((r) => r.task), ...alt.diff_vs_human.retimed.map((r) => r.task)]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] text-xs [&_td]:px-1.5 [&_th]:px-1.5 [&_th]:align-bottom">
        <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
          <tr><th className="py-1">{tp("task")}</th><th>{tp("template")} · {tp("site")}</th><th>{tp("resources")}</th><th>{tp("departure")}</th><th>{tp("end")}</th><th>{tp("deadline")}</th><th>{tp("slack")}</th><th>{tp("status")}</th><th /></tr>
        </thead>
        <tbody>
          {alt.tasks.map((t) => {
            const ev = evalBy.get(t.code);
            const open = selectedTask === t.code;
            return (
              <Fragment key={t.code}>
                <tr onClick={() => onSelectTask(open ? null : t.code)} className={clsx("cursor-pointer border-t border-line/60 align-top", open ? "bg-accent/10" : "hover:bg-panel-2")}>
                  <td className="py-1.5 font-mono font-bold">{t.code}{changed.has(t.code) && <span className="ml-0.5 text-accent" title={to("diff")}>•</span>}</td>
                  <td className="max-w-[210px]"><div className="truncate font-semibold">{names.action(t.template_id)}</div><div className="truncate text-[10.5px] text-muted">{names.site(t.site_id)}</div></td>
                  <td className="font-mono text-[10.5px] text-ink-2">{[t.crew, t.vehicle, ...t.pumps, ...t.equipment].filter(Boolean).join(" ")}</td>
                  <td className="tabular font-semibold">{fmt(t.departure)}</td>
                  <td className="tabular">{fmt(t.end)}</td>
                  <td className="tabular">{fmt(t.deadline)}</td>
                  <td className="tabular">{ev?.slack_min != null ? countdown(ev.slack_min) : "—"}</td>
                  <td><StatusBadge ns="evalStatus" code={ev?.status || t.status} icon={false} /></td>
                  <td className="text-[10px] font-bold text-accent">{open ? "▲" : `${tp("why")}`}</td>
                </tr>
                {open && (
                  <tr className="bg-panel-2"><td colSpan={9} className="p-2"><WhyTask task={t} fmt={fmt} facilityName={facilityName} sectorName={sectorName} /></td></tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
