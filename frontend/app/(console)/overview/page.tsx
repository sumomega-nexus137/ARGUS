"use client";

import clsx from "clsx";
import { ArrowRight, Droplets, TrendingUp } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo } from "react";
import { useTranslations } from "use-intl";

import { FreshnessSummary } from "@/components/common/Freshness";
import { ScreenHelp } from "@/components/help/ScreenHelp";
import { WelcomeCard } from "@/components/help/WelcomeCard";
import { Badge, ErrorState, Loading, Metric, Panel, StatusBadge } from "@/components/ui/primitives";
import { ageLabel, countdown, num, pickName, relHHMM } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { useAreas } from "@/lib/queries";
import { TONE_CLASS, toneOf } from "@/lib/status";
import type { AreaOverview } from "@/lib/types";

const RegionMap = dynamic(() => import("@/components/map/RegionMap").then((m) => m.RegionMap), { ssr: false });

function AreaCard({ a }: { a: AreaOverview }) {
  const t = useTranslations("overview");
  const tq = useTranslations("questions");
  const th = useTranslations("headline");
  const ts = useTranslations("source");
  const tv = useTranslations("verification");
  const tm = useTranslations("mode");
  const tu = useTranslations("units");
  const { locale } = useLocale();
  // forecast from the scenario's stage station; latest observation from any gauge (official gauges may use other datums)
  const g = a.gauges.find((x) => x.scenario_station) || a.gauges[0];
  const obsG = [...a.gauges].filter((x) => x.stage_cm !== null).sort((x, y) => (y.observed_at || "").localeCompare(x.observed_at || ""))[0];
  const ref = a.scenario.reference_time;
  const nd = a.plan?.next_critical_decision;
  return (
    <article className={clsx("rounded-[4px] border bg-panel", a.status === "CRITICAL" ? "border-crit/60" : a.status === "WARNING" ? "border-warn/50" : "border-line")}>
      <header className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
        <div>
          <h2 className="text-base font-bold tracking-wide">{pickName(a.names, locale)}</h2>
          <p className="text-[11.5px] text-muted">{pickName(a.river_names, locale)} · {t(`archetype.${a.archetype}`)}</p>
        </div>
        <div className={clsx("rounded-[3px] border px-2.5 py-1 text-sm font-bold tracking-wider", TONE_CLASS[toneOf(a.status)])}>
          <StatusBadge ns="status" code={a.status} className="border-0 bg-transparent px-0 text-sm" />
        </div>
      </header>
      <div className="space-y-3 p-4">
        {a.reasons.length > 0 && (
          <ul className="space-y-0.5 text-[12px] text-ink-2">
            {a.reasons.map((r, i) => (
              <li key={i} className="flex items-center gap-1.5">
                <span aria-hidden className="h-1 w-1 rounded-full bg-ink-2" />
                {t(`reasons.${r.type}`, { ...r.params, stage: num(r.params.stage_cm as number, 0, locale) } as Record<string, string | number>)}
              </li>
            ))}
          </ul>
        )}
        {g && (
          <div className="grid grid-cols-3 gap-3 rounded-[3px] border border-line bg-panel-2 p-3">
            <Metric label={<span className="flex items-center gap-1"><Droplets className="h-3 w-3" />{t("stage")}</span>} value={obsG ? `${num(obsG.stage_cm, 0, locale)} ${tu("cm")}` : "—"}
              sub={obsG ? `${obsG.source_type ? ts(obsG.source_type === "FIELD" && obsG.verification === "VERIFIED" ? "VERIFIED_FIELD" : obsG.source_type) : "—"} · ${ageLabel(obsG.age_min)}` : t("noObservation")} />
            <Metric label={<span className="flex items-center gap-1"><TrendingUp className="h-3 w-3" />{t("trend")}</span>} value={<span className="whitespace-nowrap text-base">{!obsG || obsG.trend_cm_h === null ? "—" : t("trendValue", { v: num(obsG.trend_cm_h, 1, locale) })}</span>}
              tone={obsG?.trend_cm_h && obsG.trend_cm_h > 0 ? "warn" : undefined} />
            <Metric label={a.scenario.mode === "SIMULATION" ? t("scenarioPeak") : t("forecastPeak")} value={`${num(g.forecast_peak_cm, 0, locale)} ${tu("cm")}`} sub={relHHMM(ref, g.forecast_peak_at_min, a.utc_offset_min)}
              tone={g.forecast_peak_cm && g.thresholds.critical !== null && g.forecast_peak_cm >= g.thresholds.critical ? "crit" : g.forecast_peak_cm && g.thresholds.warning !== null && g.forecast_peak_cm >= g.thresholds.warning ? "warn" : undefined} />
            {obsG && obsG.station_id !== g.station_id && (
              <p className="col-span-3 text-[10.5px] leading-snug text-muted">{t("differentStations", { obs: pickName(obsG.names, locale), sc: pickName(g.names, locale) })}</p>
            )}
            <div className="col-span-3 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
              {obsG?.verification && <Badge tone={toneOf(obsG.verification)}>{tv(obsG.verification)}</Badge>}
              {obsG?.mode && <Badge tone={obsG.mode === "LIVE" ? "live" : obsG.mode === "HISTORICAL" ? "info" : "sim"}>{tm.has(obsG.mode) ? tm(obsG.mode) : obsG.mode}</Badge>}
              <Badge tone={a.scenario.mode === "HISTORICAL" ? "info" : "sim"}>{t("scenarioMode")}: {tm.has(a.scenario.mode) ? tm(a.scenario.mode) : a.scenario.mode}</Badge>
              {g.open_conflict && <Badge tone="warn">{t("conflict")}</Badge>}
            </div>
          </div>
        )}
        <div className="rounded-[3px] border border-line bg-panel-2 p-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10.5px] uppercase tracking-wider text-muted">{t("plan")}</span>
            {a.plan ? <StatusBadge ns="health" code={a.plan.status} /> : <Badge>{t("noActivePlan")}</Badge>}
          </div>
          {a.plan && (
            <>
              <div className="text-sm font-semibold">{a.plan.plan_name} · v{a.plan.version}</div>
              {a.plan.headline && <p className="mt-1 text-[12px] text-crit">{th(a.plan.headline.type, a.plan.headline.params as Record<string, string>)}</p>}
              {nd && (
                <div className="mt-2 flex items-baseline justify-between border-t border-line pt-2">
                  <span className="text-[10.5px] uppercase tracking-wider text-muted">{t("nextDecision")}</span>
                  <span className={clsx("tabular text-lg font-bold", nd.minutes <= 45 ? "text-crit" : "text-warn")}>{countdown(nd.minutes)} <span className="text-xs font-normal text-ink-2">· {nd.task}</span></span>
                </div>
              )}
            </>
          )}
        </div>
        <FreshnessSummary rows={a.freshness} />
        <Link href={`/area/${a.id}/situation`} className="flex items-center justify-between rounded-[3px] border border-accent/40 bg-accent/10 px-3 py-2 text-xs font-semibold text-accent hover:bg-accent/20">
          <span>{t("openArea")} — {tq("situation")}</span>
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </article>
  );
}

export default function OverviewPage() {
  const t = useTranslations("overview");
  const tq = useTranslations("questions");
  const { locale } = useLocale();
  const router = useRouter();
  const areas = useAreas();
  const labels = useMemo(() => Object.fromEntries((areas.data || []).map((a) => [a.id, pickName(a.names, locale)])), [areas.data, locale]);
  const onSelect = useCallback((id: string) => router.push(`/area/${id}/situation`), [router]);
  return (
    <div className="flex h-full flex-col overflow-auto xl:flex-row xl:overflow-hidden">
      <div className="min-w-0 flex-1 space-y-3 overflow-y-auto p-4 xl:max-w-[760px]">
        <WelcomeCard />
        <div className="flex items-start justify-between gap-2">
          <div>
          <h1 className="text-lg font-bold tracking-wide">{t("title")}</h1>
          <p className="text-sm text-accent">{tq("overview")}</p>
          <p className="text-[11.5px] text-muted">{areas.data && areas.data.length > 0 && areas.data.every((a) => !a.is_demo) ? t("regionReal") : t("region")}</p>
          </div>
          <ScreenHelp screen="overview" />
        </div>
        {areas.isLoading && <Loading />}
        {areas.isError && <ErrorState error={areas.error} onRetry={() => areas.refetch()} />}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          {areas.data?.map((a) => <AreaCard key={a.id} a={a} />)}
        </div>
      </div>
      <div className="relative min-h-[380px] flex-1 border-l border-line">
        {areas.data && <RegionMap areas={areas.data} labels={labels} onSelect={onSelect} />}
        <div className="pointer-events-none absolute left-3 top-3">
          <Panel className="pointer-events-auto" bodyClass="p-2">
            <div className="flex flex-wrap gap-1">
              {["NORMAL", "WATCH", "WARNING", "CRITICAL"].map((s) => <StatusBadge key={s} ns="status" code={s} />)}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
