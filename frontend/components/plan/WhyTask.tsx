"use client";

import { useTranslations } from "use-intl";

import { StatusBadge } from "@/components/ui/primitives";
import { num } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import type { AltTask } from "@/lib/types";

/** WHY THIS TASK? / WHY THIS RESOURCE? / WHY NOW? / WHAT HAPPENS IF DELAYED? — built from solver facts only. */
export function WhyTask({ task, fmt, facilityName, sectorName }: {
  task: AltTask; fmt: (m: number | null | undefined) => string; facilityName: (id: string) => string; sectorName: (id: string) => string;
}) {
  const to = useTranslations("optimizer");
  const tw = useTranslations("windows");
  const tsub = useTranslations("subtype");
  const ti = useTranslations("issues");
  const { locale } = useLocale();
  const w = task.why;
  if (!w) return null;
  const c = w.task.components;
  const sub = (s: string) => (tsub.has(s) ? tsub(s) : s);
  const reason = (r: string) => (tw.has(`reason.${r}`) ? tw(`reason.${r}`) : r);

  return (
    <div className="grid grid-cols-1 gap-2 text-[11.5px] leading-snug md:grid-cols-2">
      <Section title={to("whyTask")}>
        <p>{to("valueExplain", {
          value: num(w.task.value, 1, locale), rank: w.task.rank, of: w.task.of,
          life: num(c.life, 1, locale), infra: num(c.infra, 1, locale), economic: num(c.economic, 1, locale),
          wl: w.task.weights.life ?? 0, wi: w.task.weights.infra ?? 0, we: w.task.weights.economic ?? 0,
        })}</p>
        {c.protected_sectors.length > 0 && (
          <p>{to("exposedPop", { sectors: c.protected_sectors.map(sectorName).join(", "), n: num(c.exposed_population, 0, locale) })}</p>
        )}
        {c.threatened_facilities.length > 0 && <p>{to("threatened", { list: c.threatened_facilities.map(facilityName).join(", ") })}</p>}
      </Section>

      <Section title={to("whyResource")}>
        {w.resource.crew ? (
          <p>{to("resourceExplain", { crew: w.resource.crew, types: w.resource.qualified_types.map(sub).join(", "), vehicle: w.resource.vehicle || "—" })}</p>
        ) : null}
        {w.resource.pumps > 0 && <p>{to("pumpsAssigned", { n: w.resource.pumps })}</p>}
        {w.resource.alternatives.length === 0 ? (
          <p className="text-muted">{to("noAlternative")}</p>
        ) : (
          <ul className="space-y-0.5">
            {w.resource.alternatives.map((a) => (
              <li key={a.crew} className="text-ink-2">
                {to("alternativeCrew", { crew: a.crew, subtype: sub(a.subtype), time: fmt(a.earliest_arrival) })}
                {a.assigned_to && <span className="text-muted"> · {to("busyWith", { task: a.assigned_to })}</span>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={to("whyNow")}>
        {w.now.deadline === null ? (
          <p>{to("noDeadline")}</p>
        ) : (
          <p>{to("nowExplain", { deadline: fmt(w.now.deadline), reason: reason(w.now.deadline_reason), latest: fmt(w.now.latest_departure) })}</p>
        )}
        {w.now.route_closures.filter((r) => r.closes_at !== null).length > 0 && (
          <ul className="space-y-0.5 text-ink-2">
            {w.now.route_closures.filter((r) => r.closes_at !== null).map((r) => (
              <li key={r.road}>{to("roadClosesAt", { road: r.road, time: fmt(r.closes_at) })}</li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={to("ifDelayed")}>
        {w.if_delayed.tolerance_min === null ? (
          <p>{to("noDeadline")}</p>
        ) : (
          <p>{to("toleranceExplain", { minutes: Math.max(0, Math.round(w.if_delayed.tolerance_min)) })}</p>
        )}
        {w.if_delayed.consequence && (
          <p className="flex flex-wrap items-center gap-1">
            {to("delayConsequence", { minutes: w.if_delayed.consequence.delay_min })}
            <StatusBadge ns="evalStatus" code={w.if_delayed.consequence.status} />
            {w.if_delayed.consequence.issues.map((i) => <span key={i} className="text-muted">{ti.has(i) ? ti(i) : i}</span>)}
            {w.if_delayed.consequence.other_tasks_affected.length > 0 && (
              <span className="text-warn">{to("othersAffected", { tasks: w.if_delayed.consequence.other_tasks_affected.join(", ") })}</span>
            )}
          </p>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1 rounded-[3px] border border-line bg-bg/60 p-2">
      <div className="text-[10px] font-bold tracking-wider text-accent">{title}</div>
      {children}
    </div>
  );
}
