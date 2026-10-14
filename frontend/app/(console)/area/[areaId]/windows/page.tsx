"use client";

import clsx from "clsx";
import { AlarmClock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx, type PointOverlay } from "@/components/area/AreaContext";
import { WindowGantt } from "@/components/charts/WindowGantt";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { Badge, InlineNote, Loading, Panel, StatusBadge } from "@/components/ui/primitives";
import { countdown, num, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { TONE_TEXT, toneOf } from "@/lib/status";
import { useNames } from "@/lib/useNames";

function Countdown({ minutes, tone }: { minutes: number | null; tone: string }) {
  return <span className={clsx("tabular font-mono text-lg font-extrabold", TONE_TEXT[toneOf(tone)])}>{countdown(minutes)}</span>;
}

export default function WindowsPage() {
  const ctx = useAreaCtx();
  const { areaId, access, fmt, setOverlays, clearOverlays, accessTl, layers } = ctx;
  const tw = useTranslations("windows");
  const tr = useTranslations("road");
  const tf = useTranslations("facilityType");
  const { locale } = useLocale();
  const names = useNames(areaId);
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => () => clearOverlays(), [clearOverlays]);

  const sectorCentroids = useMemo(() => {
    const out: Record<string, [number, number]> = {};
    layers.sectors?.features.forEach((f) => {
      const ring = (f.geometry.coordinates as [number, number][][])[0];
      out[String(f.properties.id)] = [ring.reduce((s, c) => s + c[0], 0) / ring.length, ring.reduce((s, c) => s + c[1], 0) / ring.length];
    });
    return out;
  }, [layers.sectors]);

  // map: countdown markers for sectors losing access and for task sites; route of the selected task
  useEffect(() => {
    if (!access) return;
    const pts: PointOverlay[] = [];
    access.sectors.forEach((s) => {
      const c = sectorCentroids[s.code];
      if (!c) return;
      if (s.isolated_now) pts.push({ id: `sec-${s.code}`, lon: c[0], lat: c[1], label: tw("isolatedNow"), sub: pickName(s.names, locale), tone: "crit" });
      else if (s.access_lost_in_min !== null) pts.push({ id: `sec-${s.code}`, lon: c[0], lat: c[1], label: countdown(s.access_lost_in_min), sub: `${tw("accessLostIn")} · ${pickName(s.names, locale)}`, tone: s.access_lost_in_min < 60 ? "crit" : "warn" });
    });
    access.tasks.forEach((x) => {
      const site = names.siteObj(x.site_id);
      if (!site || x.latest_departure === null) return;
      if (sel && sel !== x.code) return;
      const late = x.planned_departure !== null && x.planned_departure > x.latest_departure;
      pts.push({ id: `task-${x.code}`, lon: site.lon, lat: site.lat, label: `${x.code} ${countdown(x.slack_to_latest_min)}`, sub: sel === x.code ? tw("latestStart") : undefined,
        tone: late ? "crit" : (toneOf(x.window_status || "SAFE") as PointOverlay["tone"]) });
    });
    const task = access.tasks.find((x) => x.code === sel);
    const routeSegs = task ? access.roads.filter((r) => task.latest_route_roads.includes(r.road_id)).flatMap((r) => r.segments.map((s) => s.segment_id)) : [];
    setOverlays({ points: pts, highlightSegments: routeSegs, routes: [] });
  }, [access, sel, names, sectorCentroids, setOverlays, tw, locale]);

  if (!access) return <div className="p-3"><ScreenHeader screen="windows" /><Loading /></div>;
  const nd = access.next_critical_decision;
  const ndTask = nd ? access.tasks.find((x) => x.code === nd.task) : undefined;
  const roads = access.roads.filter((r) => r.state !== "OPEN" && r.state !== "AT_RISK");
  return (
    <div className="space-y-3 p-3">
      <ScreenHeader screen="windows" right={<Badge tone="info">{tw("asOf", { time: fmt(access.as_of) })}</Badge>} />
      <section aria-live="polite" className={clsx("rounded-[4px] border p-4", nd && nd.minutes <= 45 ? "border-crit/60 bg-crit/10" : "border-warn/50 bg-warn/5")}>
        <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em] text-ink-2"><AlarmClock className="h-4 w-4" />{tw("nextDecision")}</div>
        {nd ? (
          <div className="mt-1 flex flex-wrap items-end justify-between gap-2">
            <div className={clsx("tabular font-mono text-5xl font-black leading-none", nd.minutes <= 45 ? "text-crit animate-pulse-soft" : "text-warn")}>{countdown(nd.minutes)}</div>
            <div className="text-right">
              <div className="text-sm font-bold">{tw("nextDecisionTask", { task: nd.task, time: fmt(nd.latest_departure) })}</div>
              {ndTask && <div className="text-xs text-ink-2">{names.action(ndTask.template_id)} · {names.site(ndTask.site_id)}{ndTask.crew ? ` · ${ndTask.crew}` : ""}</div>}
            </div>
          </div>
        ) : <div className="mt-1 text-sm text-ok">{tw("noPending")}</div>}
      </section>

      <Panel title={tw("tasks")} right={access.plan && <span className="text-[11px] text-muted">{access.plan.name} · v{access.plan.version}</span>}>
        <div className="space-y-1">
          {access.tasks.map((x) => (
            <button key={x.code} onClick={() => setSel(sel === x.code ? null : x.code)}
              className={clsx("grid w-full grid-cols-[46px_1fr_auto] items-center gap-2 rounded-[3px] border px-2 py-1.5 text-left", sel === x.code ? "border-accent/60 bg-accent/10" : "border-line bg-panel-2 hover:border-line-2")}>
              <span className="font-mono text-sm font-bold">{x.code}</span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-semibold">{names.action(x.template_id)} · {names.site(x.site_id)}</span>
                <span className="block truncate text-[11px] text-muted">
                  {x.crew ?? "—"} · {tw("planned")} {fmt(x.planned_departure)} · {tw("latest")} {fmt(x.latest_departure)} · {tw("deadline")} {fmt(x.deadline)} ({tw(`reason.${x.deadline_reason}`)})
                  {x.latest_route_roads.length > 0 && ` · ${tw("viaRoads", { roads: x.latest_route_roads.slice(0, 4).join("→") })}`}
                </span>
              </span>
              <span className="text-right">
                <span className="block text-[9.5px] font-bold uppercase tracking-wider text-muted">{tw("latestStart")}</span>
                {x.latest_departure !== null ? <Countdown minutes={x.slack_to_latest_min} tone={x.window_status || "SAFE"} /> : <span className="text-xs text-muted">—</span>}
                <span className="mt-0.5 block"><StatusBadge ns="window" code={x.window_status} /></span>
                {x.planned_departure !== null && x.latest_departure !== null && x.planned_departure > x.latest_departure && (
                  <span className="mt-0.5 block"><Badge tone="crit">{tw("plannedTooLate")}</Badge></span>
                )}
              </span>
            </button>
          ))}
        </div>
        <InlineNote tone="info" className="mt-2">{tw("formula")}</InlineNote>
      </Panel>

      <Panel title={tw("gantt")}>
        <WindowGantt tasks={access.tasks} asOf={access.as_of} horizon={access.horizon_end} closures={accessTl?.road_closures ?? {}} fmt={(m) => fmt(m)} onSelect={(c) => setSel(c)} selected={sel} />
      </Panel>

      <Panel title={tw("roads")}>
        <div className="grid grid-cols-2 gap-1.5">
          {roads.map((r) => (
            <div key={r.road_id} className={clsx("rounded-[3px] border px-2 py-1.5", r.state === "CLOSED" ? "border-crit/50 bg-crit/10" : "border-warn/40 bg-warn/5")}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-bold">{r.road_id}</span>
                <StatusBadge ns="road" code={r.state} />
              </div>
              <div className="truncate text-[10.5px] text-muted">{pickName(r.names, locale)}</div>
              {r.closes_in_min !== null && (
                <div className="mt-0.5 flex items-baseline justify-between"><span className="text-[9.5px] font-bold uppercase tracking-wider text-muted">{tw("closesIn")}</span><Countdown minutes={r.closes_in_min} tone={r.closes_in_min < 60 ? "CRITICAL" : "WARNING"} /></div>
              )}
              {r.state === "CLOSED" && r.reopens_at !== null && <div className="text-[10.5px] text-ink-2">{tr("reopensAt", { t: fmt(r.reopens_at) })}</div>}
              {r.override && <Badge tone="info" className="mt-1">{tr("override")}</Badge>}
            </div>
          ))}
        </div>
      </Panel>

      <Panel title={tw("sectors")}>
        <table className="w-full text-xs">
          <tbody>
            {access.sectors.map((s) => (
              <tr key={s.code} className="border-t border-line/60">
                <td className="py-1.5">{pickName(s.names, locale)}<div className="text-[10.5px] text-muted">{tw("population", { n: num(s.population, 0, locale) })}</div></td>
                <td className="text-right">
                  {s.isolated_now ? <Badge tone="crit">{tw("isolatedNow")}</Badge>
                    : s.access_lost_in_min !== null ? <div><div className="text-[9.5px] font-bold uppercase tracking-wider text-muted">{tw("accessLostIn")}</div><Countdown minutes={s.access_lost_in_min} tone={s.access_lost_in_min < 60 ? "CRITICAL" : "WARNING"} /></div>
                      : <span className="text-[11px] text-ok">{tw("accessible")} · {tw("notWithinHorizon")}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title={tw("facilities")}>
        <table className="w-full text-xs">
          <tbody>
            {access.facilities.map((f) => (
              <tr key={f.id} className="border-t border-line/60">
                <td className="py-1.5">{pickName(f.names, locale)}<div className="text-[10.5px] text-muted">{tf.has(f.type) ? tf(f.type) : f.type} · {f.criticality}</div></td>
                <td className="text-right">
                  {f.flooded_now ? <Badge tone="crit">{tw("flooded")}</Badge> : f.flood_in_min !== null ? <div><div className="text-[9.5px] font-bold uppercase text-muted">{tw("floodsIn")}</div><Countdown minutes={f.flood_in_min} tone="WARNING" /></div> : null}
                </td>
                <td className="w-28 text-right">
                  {!f.accessible_now ? <Badge tone="crit">{tw("isolatedNow")}</Badge> : f.access_lost_in_min !== null ? <div><div className="text-[9.5px] font-bold uppercase text-muted">{tw("accessLostIn")}</div><Countdown minutes={f.access_lost_in_min} tone="WARNING" /></div> : <span className="text-[11px] text-ok">{tw("accessible")}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
