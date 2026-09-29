"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { HealthBanner } from "@/components/plan/HealthBanner";
import { Badge, Button, Empty, ErrorState, Field, InlineNote, inputCls, Loading, Panel, StatusBadge, Tabs } from "@/components/ui/primitives";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { hhmm } from "@/lib/format";
import { useInvalidateArea, useOperations } from "@/lib/queries";
import { useNames } from "@/lib/useNames";

const TASK_STATUSES = ["PENDING", "EN_ROUTE", "WORKING", "DONE", "FAILED", "BLOCKED", "RESOURCE_UNAVAILABLE"];
type EventType = "ROAD_CLOSED" | "PUMP_FAILED" | "CREW_DELAYED" | "FORECAST_CHANGED";

export default function OperationsPage() {
  const { areaId, area, scenario, layers, fmt, clearOverlays } = useAreaCtx();
  const to = useTranslations("ops");
  const tp = useTranslations("plan");
  const tc = useTranslations("common");
  const tts = useTranslations("taskStatus");
  const { can } = useAuth();
  const names = useNames(areaId);
  const ops = useOperations(areaId);
  const invalidate = useInvalidateArea();
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => () => clearOverlays(), [clearOverlays]);

  const statusM = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => post(`/api/plan-tasks/${id}/status`, { status }),
    onSuccess: () => invalidate(areaId),
  });
  const recomputeM = useMutation({
    mutationFn: () => post<{ plan_version: { version: number }; label: string }>(`/api/areas/${areaId}/recompute`, { policy: "BALANCED" }),
    onSuccess: (r) => { setMsg(to("recomputed", { v: r.plan_version.version, label: r.label })); invalidate(areaId); },
  });
  const transitionM = useMutation({
    mutationFn: ({ id, target }: { id: string; target: string }) => post(`/api/plan-versions/${id}/transition`, { target }),
    onSuccess: () => invalidate(areaId),
  });

  if (ops.isLoading || !area) return <div className="p-3"><ScreenHeader screen="operations" /><Loading /></div>;
  if (ops.isError) return <div className="p-3"><ScreenHeader screen="operations" /><ErrorState error={ops.error} onRetry={() => ops.refetch()} /></div>;
  const d = ops.data!;
  const pv = d.active_version;
  const evalBy = new Map((d.health?.evaluation.tasks || []).map((t) => [t.code, t]));
  const err = statusM.error || recomputeM.error || transitionM.error;

  return (
    <div className="space-y-3 p-3">
      <ScreenHeader screen="operations" />
      {err && <ErrorState error={err} />}
      {msg && <InlineNote tone="ok">{msg}</InlineNote>}
      {d.health && pv ? (
        <HealthBanner health={d.health} fmt={fmt} siteName={names.site} planLabel={`${pv.plan_name} v${pv.version}`} defaultOpen={d.health.status !== "PLAN_VALID"} />
      ) : <InlineNote tone="warn">{to("noActive")}</InlineNote>}

      {pv && can("plan_edit") && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant={d.health?.status === "PLAN_AT_RISK" ? "danger" : "default"} icon={RefreshCw} busy={recomputeM.isPending} onClick={() => recomputeM.mutate()}>
            {recomputeM.isPending ? to("recomputing") : to("recompute")}
          </Button>
          <span className="text-[11px] text-muted">{to("recomputeHint")}</span>
        </div>
      )}

      {d.pending_versions.length > 0 && (
        <Panel title={to("pendingVersions")}>
          {d.pending_versions.map((v) => (
            <div key={v.id} className="flex flex-wrap items-center gap-2 border-t border-line/60 py-1.5 text-xs first:border-0">
              <span className="font-bold">{v.plan_name} v{v.version}</span>
              <StatusBadge ns="planStatus" code={v.status} />
              <span className="text-muted">{v.created_by}</span>
              <span className="ml-auto flex gap-1">
                {v.status === "DRAFT" && can("plan_review") && <Button size="sm" onClick={() => transitionM.mutate({ id: v.id, target: "REVIEWED" })}>{tp("toReviewed")}</Button>}
                {v.status === "REVIEWED" && can("plan_approve") && <Button size="sm" variant="primary" onClick={() => transitionM.mutate({ id: v.id, target: "APPROVED" })}>{tp("toApproved")}</Button>}
                {v.status === "APPROVED" && can("plan_approve") && <Button size="sm" variant="primary" onClick={() => transitionM.mutate({ id: v.id, target: "ACTIVE" })}>{tp("toActive")}</Button>}
                <Link href={`/area/${areaId}/plan?v=${v.id}`} className="text-[11px] text-accent underline">{to("openPlan")}</Link>
              </span>
            </div>
          ))}
        </Panel>
      )}

      {pv && (
        <Panel title={to("board")}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-xs [&_td]:px-1.5 [&_th]:px-1.5">
              <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
                <tr><th>{tp("task")}</th><th>{tp("template")}</th><th>{tp("resources")}</th><th>{tp("latestDeparture")}</th><th>{to("eta")}</th><th>{tp("status")}</th><th>{to("setStatus")}</th></tr>
              </thead>
              <tbody>
                {(pv.tasks || []).map((t) => {
                  const ev = evalBy.get(t.code);
                  return (
                    <tr key={t.id} className="border-t border-line/60">
                      <td className="py-1.5 font-mono font-bold">{t.code}</td>
                      <td><div className="font-semibold">{names.action(t.template_id)}</div><div className="text-[10.5px] text-muted">{names.site(t.site_id)}</div></td>
                      <td className="font-mono text-[10.5px]">{t.resource_ids.join(" ")}</td>
                      <td className="tabular">{fmt(ev?.latest_departure)}</td>
                      <td className="tabular">{fmt(ev?.arrival)}</td>
                      <td><StatusBadge ns="evalStatus" code={ev?.status} icon={false} /></td>
                      <td>
                        <select className={`${inputCls} w-44`} value={t.status} disabled={!can("field_update") || statusM.isPending}
                          onChange={(e) => statusM.mutate({ id: t.id, status: e.target.value })} aria-label={to("setStatus")}>
                          {TASK_STATUSES.map((s) => <option key={s} value={s}>{tts(s)}</option>)}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {can("field_update") && <EventInjector areaId={areaId} roads={(layers.roads?.features || []).map((f) => String(f.properties.road_id ?? f.properties.id))}
        resources={d.resources} members={scenario?.members.map((m) => m.id) || []} canForecast={can("plan_edit")} onDone={(o) => { setMsg(to("reported", { outcome: o })); invalidate(areaId); }} />}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Panel title={to("pipeline")}>
          {d.last_pipeline ? (
            <ol className="space-y-1 text-xs">
              <li className="text-muted">{d.last_pipeline.trigger} · {hhmm(d.last_pipeline.started_at, area.utc_offset_min)} → <b>{to.has(`outcome.${d.last_pipeline.outcome}`) ? to(`outcome.${d.last_pipeline.outcome}`) : d.last_pipeline.outcome}</b></li>
              {d.last_pipeline.steps.map((s) => (
                <li key={s.step} className="flex justify-between gap-2">
                  <span><Badge tone={s.status === "OK" ? "ok" : "crit"} icon={false}>{s.status}</Badge> {to.has(`steps.${s.step}`) ? to(`steps.${s.step}`) : s.step}</span>
                  <span className="tabular text-muted">{s.ms} ms</span>
                </li>
              ))}
            </ol>
          ) : <Empty />}
        </Panel>
        <Panel title={to("resources")}>
          <div className="grid grid-cols-2 gap-1 text-[11px] sm:grid-cols-3">
            {d.resources.map((r) => (
              <div key={r.id} className="flex justify-between gap-1 rounded-[3px] border border-line px-1.5 py-0.5">
                <span className="font-mono font-bold">{r.id}</span>
                <span className={r.status === "AVAILABLE" ? "text-ink-2" : "text-crit"}>{r.status !== "AVAILABLE" ? r.status : r.assigned_task ? to("assigned", { task: r.assigned_task }) : to("free")}{r.delay_min ? ` +${r.delay_min}′` : ""}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title={to("events")}>
        {d.events.length === 0 ? <Empty /> : (
          <ul className="space-y-0.5 text-[11px]">
            {d.events.map((e) => (
              <li key={e.id} className="flex gap-2 border-t border-line/50 py-0.5 first:border-0">
                <span className="tabular text-muted">{hhmm(e.op_time || e.ts, area.utc_offset_min)}</span>
                <span className="font-mono text-accent">{e.action}</span>
                <span className="min-w-0 flex-1 truncate">{e.summary}</span>
                <span className="text-muted">{e.username}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-[10px] text-muted">{tc("source")}: audit</p>
      </Panel>
    </div>
  );
}

function EventInjector({ areaId, roads, resources, members, canForecast, onDone }: {
  areaId: string; roads: string[]; resources: { id: string; type: string }[]; members: string[]; canForecast: boolean; onDone: (outcome: string) => void;
}) {
  const to = useTranslations("ops");
  const [type, setType] = useState<EventType>("ROAD_CLOSED");
  const [road, setRoad] = useState("");
  const [res, setRes] = useState("");
  const [delay, setDelay] = useState("30");
  const [member, setMember] = useState("");
  const [note, setNote] = useState("");
  const uniqRoads = Array.from(new Set(roads)).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  const m = useMutation({
    mutationFn: async () => {
      let r: { pipeline?: { outcome?: string; plan_status?: string } };
      if (type === "ROAD_CLOSED") r = await post(`/api/areas/${areaId}/road-events`, { road_id: road, state: "CLOSED", notes: note || null, source: "Field report" });
      else if (type === "PUMP_FAILED") r = await post(`/api/resources/${res}/status`, { status: "FAILED", note: note || null });
      else if (type === "CREW_DELAYED") r = await post(`/api/resources/${res}/status`, { status: "AVAILABLE", delay_min: Number(delay) || 0, note: note || null });
      else r = await post(`/api/areas/${areaId}/scenario/select-member`, { member_id: member, note });
      return r.pipeline?.outcome || r.pipeline?.plan_status || "—";
    },
    onSuccess: onDone,
  });
  const valid = type === "ROAD_CLOSED" ? !!road : type === "FORECAST_CHANGED" ? !!member : !!res;
  const types: EventType[] = canForecast ? ["ROAD_CLOSED", "PUMP_FAILED", "CREW_DELAYED", "FORECAST_CHANGED"] : ["ROAD_CLOSED", "PUMP_FAILED", "CREW_DELAYED"];
  return (
    <Panel title={to("injectEvent")}>
      <Tabs<EventType> value={type} onChange={setType} tabs={types.map((t) => ({ id: t, label: to(`eventTypes.${t}`) }))} />
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
        {type === "ROAD_CLOSED" && (
          <Field label={to("road")}><select className={inputCls} value={road} onChange={(e) => setRoad(e.target.value)}><option value="">—</option>{uniqRoads.map((r) => <option key={r}>{r}</option>)}</select></Field>
        )}
        {(type === "PUMP_FAILED" || type === "CREW_DELAYED") && (
          <Field label={type === "PUMP_FAILED" ? to("pump") : to("crewLbl")}>
            <select className={inputCls} value={res} onChange={(e) => setRes(e.target.value)}>
              <option value="">—</option>
              {resources.filter((r) => r.type === (type === "PUMP_FAILED" ? "PUMP" : "CREW")).map((r) => <option key={r.id}>{r.id}</option>)}
            </select>
          </Field>
        )}
        {type === "CREW_DELAYED" && <Field label={to("delay")}><input type="number" min={0} className={inputCls} value={delay} onChange={(e) => setDelay(e.target.value)} /></Field>}
        {type === "FORECAST_CHANGED" && (
          <Field label={to("member")}><select className={inputCls} value={member} onChange={(e) => setMember(e.target.value)}><option value="">—</option>{members.map((x) => <option key={x}>{x}</option>)}</select></Field>
        )}
        <Field label={to("note")}><input className={inputCls} value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} /></Field>
      </div>
      <Button className="mt-2" variant="primary" size="sm" disabled={!valid} busy={m.isPending} onClick={() => m.mutate()}>{to("report")}</Button>
      {m.isError && <div className="mt-2"><ErrorState error={m.error} /></div>}
    </Panel>
  );
}
