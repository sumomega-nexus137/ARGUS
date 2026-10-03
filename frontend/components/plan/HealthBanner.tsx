"use client";

import clsx from "clsx";
import { ChevronDown, ChevronUp, HelpCircle } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { Badge, Button, StatusBadge } from "@/components/ui/primitives";
import { countdown } from "@/lib/format";
import type { PlanHealth } from "@/lib/types";

import { CausalChainView } from "./CausalChain";

export function HealthBanner({ health, fmt, siteName, planLabel, defaultOpen = false }: {
  health: PlanHealth; fmt: (m: number | null | undefined) => string; siteName: (id: string) => string; planLabel: string; defaultOpen?: boolean;
}) {
  const th = useTranslations("headline");
  const tp = useTranslations("plan");
  const tc = useTranslations("common");
  const tw = useTranslations("windows");
  const [open, setOpen] = useState(defaultOpen);
  const bad = health.status !== "PLAN_VALID";
  // when the plan turns AT RISK while the banner is on screen (e.g. BASE → HIGH escalation), show WHY at once
  const [prevBad, setPrevBad] = useState(bad);
  if (bad !== prevBad) {
    setPrevBad(bad);
    if (bad && defaultOpen) setOpen(true);
  }
  return (
    <section aria-live="polite" className={clsx("rounded-[4px] border p-3", bad ? (health.severity === "critical" ? "border-crit/60 bg-crit/10" : "border-warn/50 bg-warn/5") : "border-ok/40 bg-ok/5")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold">{planLabel}</span>
          <StatusBadge ns="health" code={health.status} className="text-xs" />
          <Badge tone="muted">{tp("basisVsCurrent", { basis: health.basis_scenario.version, current: health.scenario.version })}</Badge>
        </div>
        {health.next_critical_decision && (
          <div className="text-right">
            <span className="text-[9.5px] font-bold uppercase tracking-wider text-muted">{tw("nextDecision")} · {health.next_critical_decision.task} </span>
            <span className="tabular font-mono text-base font-extrabold text-warn">{countdown(health.next_critical_decision.minutes)}</span>
          </div>
        )}
      </div>
      {health.headline && <p className="mt-1.5 text-sm font-semibold text-crit">{th(health.headline.type, health.headline.params as Record<string, string>)}</p>}
      {health.chains.length > 0 && (
        <div className="mt-2">
          <Button size="sm" variant={open ? "default" : "danger"} icon={HelpCircle} onClick={() => setOpen((o) => !o)}>
            {tc("why")} {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </Button>
          {open && (
            <div className="mt-2 space-y-2">
              {health.chains.map((c) => (
                <div key={c.task} className="rounded-[3px] border border-line bg-panel p-2">
                  <CausalChainView chain={c} fmt={fmt} siteName={siteName} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
