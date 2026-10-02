"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { Badge, Button, Empty, ErrorState, Field, InlineNote, inputCls, Loading, Panel, StatusBadge, Tabs } from "@/components/ui/primitives";
import { api, post, upload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, hhmm, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { useActions, useInvalidateArea, useResources } from "@/lib/queries";
import type { Freshness } from "@/lib/types";

type Tab = "observations" | "conflicts" | "resources" | "roadEvents" | "facilities" | "imports" | "sources" | "actions";
const TABS: Tab[] = ["observations", "conflicts", "resources", "roadEvents", "facilities", "imports", "sources", "actions"];

interface Obs { id: string; station_id: string; observed_at: string; water_level_cm: number; source: string; source_type: string; verification: string; authority: string; effective: boolean; entered_by: string; mode: string }
interface Conflict { id: string; station_id: string; status: string; difference: number; resolved_by: string | null; selected_observation_id: string | null; observations: { id: string; observed_at: string; water_level_cm: number; source: string; authority: string; verification: string }[] }
interface RoadEvent { id: string; road_id: string; segment_ids: string[]; state: string; source: string; verification: string; reported_by: string; active: boolean; created_at: string; notes: string | null }

export default function DataPage() {
  const { areaId } = useAreaCtx();
  const td = useTranslations("data");
  const [tab, setTab] = useState<Tab>("observations");
  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3">
      <ScreenHeader screen="data" />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={TABS.map((t) => ({ id: t, label: td(`tabs.${t}`) }))} />
      {tab === "observations" && <Observations areaId={areaId} />}
      {tab === "conflicts" && <Conflicts areaId={areaId} />}
      {tab === "resources" && <Resources areaId={areaId} />}
      {tab === "roadEvents" && <RoadEvents areaId={areaId} />}
      {tab === "facilities" && <Facilities areaId={areaId} />}
      {tab === "imports" && <Imports areaId={areaId} />}
      {tab === "sources" && <Sources areaId={areaId} />}
      {tab === "actions" && <Actions areaId={areaId} />}
    </div>
  );
}

function useDone(areaId: string) {
  const invalidate = useInvalidateArea();
  const [msg, setMsg] = useState<string | null>(null);
  return { msg, done: (m: string) => { setMsg(m); invalidate(areaId); } };
}

function Observations({ areaId }: { areaId: string }) {
  const td = useTranslations("data");
  const tm = useTranslations("mode");
  const tsrc = useTranslations("source");
  const tsc = useTranslations("scenario");
  const { area, scenario } = useAreaCtx();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["obs", areaId, area?.data_version], queryFn: () => api<{ observations: Obs[] }>(`/api/areas/${areaId}/observations`) });
  const stations = Array.from(new Set((q.data?.observations || []).map((o) => o.station_id)));
  const [f, setF] = useState({ station_id: "", water_level_cm: "", source: "", source_type: "FIELD", verification: "UNVERIFIED", notes: "" });
  const { msg, done } = useDone(areaId);
  const add = useMutation({
    mutationFn: () => post<{ pipeline?: { plan_status?: string } }>(`/api/areas/${areaId}/observations`, { ...f, station_id: f.station_id || stations[0], water_level_cm: Number(f.water_level_cm), notes: f.notes || null }),
    onSuccess: (r) => done(td("pipelineResult", { status: r.pipeline?.plan_status || "—" })),
  });
  const verify = useMutation({ mutationFn: ({ id, v }: { id: string; v: string }) => post(`/api/observations/${id}/verification`, { verification: v }), onSuccess: () => done(td("saved")) });
  if (!area) return <Loading />;
  return (
    <div className="space-y-3">
      <InlineNote tone="info">{td("hierarchy")}</InlineNote>
      {can("field_update") && (
        <Panel title={td("addObservation")}>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
            <Field label={td("station")}><select className={inputCls} value={f.station_id || stations[0] || ""} onChange={(e) => setF({ ...f, station_id: e.target.value })}>{stations.map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label={td("waterLevel")}><input type="number" className={inputCls} value={f.water_level_cm} onChange={(e) => setF({ ...f, water_level_cm: e.target.value })} /></Field>
            <Field label={td("source")}><input className={inputCls} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} /></Field>
            <Field label={td("sourceType")}><select className={inputCls} value={f.source_type} onChange={(e) => setF({ ...f, source_type: e.target.value })}>{["FIELD", "HYDROPOST", "FORECAST", "SATELLITE"].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label={td("verification")}><select className={inputCls} value={f.verification} onChange={(e) => setF({ ...f, verification: e.target.value })}>{["UNVERIFIED", "VERIFIED"].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label={td("notes")}><input className={inputCls} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
          </div>
          <p className="mt-1 text-[10.5px] text-muted">{td("nowDefault")} · {td("manualMeta")}</p>
          <Button className="mt-2" size="sm" variant="primary" disabled={!f.water_level_cm || !f.source} busy={add.isPending} onClick={() => add.mutate()}>{td("addObservation")}</Button>
          {add.isError && <ErrorState error={add.error} />}
          {msg && <InlineNote tone="ok" className="mt-2">{msg}</InlineNote>}
        </Panel>
      )}
      {q.isLoading ? <Loading /> : (
        <table className="w-full text-xs [&_td]:px-1.5 [&_th]:px-1.5">
          <thead className="text-left text-[10px] uppercase tracking-wider text-muted"><tr><th>{td("observedAt")}</th><th>{td("station")}</th><th>{td("waterLevel")}</th><th>{td("source")}</th><th>{td("authority")}</th><th>{td("verification")}</th><th /></tr></thead>
          <tbody>
            {(q.data?.observations || []).map((o) => (
              <tr key={o.id} className={`border-t border-line/60 ${o.effective ? "" : "opacity-60"}`}>
                <td className="py-1 tabular whitespace-nowrap">{area.is_demo ? hhmm(o.observed_at, area.utc_offset_min) : dateTime(o.observed_at, area.utc_offset_min)}
                  {area.now && o.observed_at > area.now && <span className="block text-[9.5px] text-muted">{tsc("hindsight")}</span>}</td>
                <td className="font-mono">{o.station_id}</td>
                <td className="tabular font-bold">{o.water_level_cm}</td>
                <td className="break-all">{o.source} <Badge tone={o.mode === "LIVE" ? "live" : o.mode === "HISTORICAL" ? "info" : "sim"} icon={false}>{tm.has(o.mode) ? tm(o.mode) : o.mode}</Badge></td>
                <td>{tsrc.has(o.authority) ? tsrc(o.authority) : o.authority}</td>
                <td><StatusBadge ns="verification" code={o.verification} icon={false} /> {o.effective ? <Badge tone="ok" icon={false}>{td("effective")}</Badge> : <span className="text-muted">{td("excludedLower")}</span>}</td>
                <td>{can("data_admin") && o.verification === "UNVERIFIED" && (
                  <span className="flex gap-1"><Button size="sm" onClick={() => verify.mutate({ id: o.id, v: "VERIFIED" })}>{td("verify")}</Button><Button size="sm" variant="ghost" onClick={() => verify.mutate({ id: o.id, v: "REJECTED" })}>{td("reject")}</Button></span>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {scenario && <p className="text-[10.5px] text-muted">v{scenario.version} · {scenario.active_member}</p>}
    </div>
  );
}

function Conflicts({ areaId }: { areaId: string }) {
  const td = useTranslations("data");
  const { area } = useAreaCtx();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["conflicts", areaId, area?.data_version], queryFn: () => api<Conflict[]>(`/api/areas/${areaId}/conflicts`) });
  const [note, setNote] = useState("");
  const { msg, done } = useDone(areaId);
  const resolve = useMutation({ mutationFn: ({ id, obs }: { id: string; obs: string }) => post(`/api/conflicts/${id}/resolve`, { selected_observation_id: obs, note: note || null }), onSuccess: () => done(td("saved")) });
  if (q.isLoading || !area) return <Loading />;
  if (!q.data?.length) return <Empty>{td("noConflicts")}</Empty>;
  return (
    <div className="space-y-3">
      {msg && <InlineNote tone="ok">{msg}</InlineNote>}
      {resolve.isError && <ErrorState error={resolve.error} />}
      {q.data.map((c) => (
        <div key={c.id} className={`rounded-[4px] border p-3 ${c.status === "OPEN" ? "border-warn/60 bg-warn/5" : "border-line bg-panel"}`}>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={c.status === "OPEN" ? "warn" : "ok"}>{td("conflictTitle")}</Badge>
            <span className="font-mono text-xs">{c.station_id}</span>
            <span className="text-xs font-bold">{td("difference", { d: c.difference })}</span>
            {c.resolved_by && <span className="text-xs text-muted">{td("resolved", { user: c.resolved_by })}</span>}
          </div>
          <p className="mt-1 text-[11px] text-ink-2">{td("conflictDesc")}</p>
          <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
            {c.observations.map((o) => (
              <div key={o.id} className={`rounded-[3px] border p-2 text-xs ${c.selected_observation_id === o.id ? "border-ok" : "border-line"}`}>
                <div className="text-lg font-bold tabular">{o.water_level_cm} cm</div>
                <div>{o.source}</div>
                <div className="text-muted">{o.authority} · {o.verification} · {hhmm(o.observed_at, area.utc_offset_min)}</div>
                {c.status === "OPEN" && can("data_admin") && <Button size="sm" className="mt-1" busy={resolve.isPending} onClick={() => resolve.mutate({ id: c.id, obs: o.id })}>{td("resolve")}</Button>}
              </div>
            ))}
          </div>
          {c.status === "OPEN" && (can("data_admin")
            ? <Field label={td("resolutionNote")}><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
            : <p className="mt-2 text-[10.5px] text-muted">{td("roleNeeded")}</p>)}
        </div>
      ))}
    </div>
  );
}

function Resources({ areaId }: { areaId: string }) {
  const td = useTranslations("data");
  const tt = useTranslations("resourceType");
  const tsub = useTranslations("subtype");
  const { can } = useAuth();
  const r = useResources(areaId);
  const { msg, done } = useDone(areaId);
  const set = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => post(`/api/resources/${id}/status`, { status }), onSuccess: () => done(td("saved")) });
  if (r.isLoading) return <Loading />;
  return (
    <div className="space-y-2">
      {msg && <InlineNote tone="ok">{msg}</InlineNote>}
      <table className="w-full text-xs [&_td]:px-1.5 [&_th]:px-1.5">
        <thead className="text-left text-[10px] uppercase tracking-wider text-muted"><tr><th>{td("resourceId")}</th><th>{td("resourceType")}</th><th>{td("subtype")}</th><th>{td("base")}</th><th>{td("state")}</th></tr></thead>
        <tbody>
          {(r.data || []).map((x) => (
            <tr key={x.id} className="border-t border-line/60">
              <td className="py-1 font-mono font-bold">{x.id}</td>
              <td>{tt.has(x.resource_type) ? tt(x.resource_type) : x.resource_type}</td>
              <td>{tsub.has(x.subtype) ? tsub(x.subtype) : x.subtype}</td>
              <td>{x.base_id || "—"}</td>
              <td>
                <select className={`${inputCls} w-40`} value={x.status} disabled={!can("field_update")} onChange={(e) => set.mutate({ id: x.id, status: e.target.value })}>
                  {["AVAILABLE", "UNAVAILABLE", "FAILED"].map((s) => <option key={s}>{s}</option>)}
                </select>
                {x.delay_min > 0 && <span className="ml-1 text-warn">+{x.delay_min}′</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RoadEvents({ areaId }: { areaId: string }) {
  const td = useTranslations("data");
  const { area, layers } = useAreaCtx();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["roadEvents", areaId, area?.data_version], queryFn: () => api<RoadEvent[]>(`/api/areas/${areaId}/road-events`) });
  const roads = Array.from(new Set((layers.roads?.features || []).map((f) => String(f.properties.road_id)))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  const [f, setF] = useState({ road_id: "", state: "CLOSED", verification: "VERIFIED", notes: "" });
  const { msg, done } = useDone(areaId);
  const add = useMutation({ mutationFn: () => post<{ pipeline?: { plan_status?: string } }>(`/api/areas/${areaId}/road-events`, { ...f, notes: f.notes || null }), onSuccess: (r) => done(td("pipelineResult", { status: r.pipeline?.plan_status || "—" })) });
  const clear = useMutation({ mutationFn: (id: string) => post(`/api/road-events/${id}/clear`), onSuccess: () => done(td("saved")) });
  if (!area) return <Loading />;
  return (
    <div className="space-y-3">
      {can("field_update") && (
        <Panel title={td("addRoadEvent")}>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Field label={td("road")}><select className={inputCls} value={f.road_id} onChange={(e) => setF({ ...f, road_id: e.target.value })}><option value="">—</option>{roads.map((r) => <option key={r}>{r}</option>)}</select></Field>
            <Field label={td("state")}><select className={inputCls} value={f.state} onChange={(e) => setF({ ...f, state: e.target.value })}>{["CLOSED", "RESTRICTED", "OPEN"].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label={td("verification")}><select className={inputCls} value={f.verification} onChange={(e) => setF({ ...f, verification: e.target.value })}>{["VERIFIED", "UNVERIFIED"].map((s) => <option key={s}>{s}</option>)}</select></Field>
            <Field label={td("notes")}><input className={inputCls} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
          </div>
          <Button className="mt-2" size="sm" variant="primary" disabled={!f.road_id} busy={add.isPending} onClick={() => add.mutate()}>{td("addRoadEvent")}</Button>
          {(add.error || clear.error) && <ErrorState error={add.error || clear.error} />}
          {msg && <InlineNote tone="ok" className="mt-2">{msg}</InlineNote>}
        </Panel>
      )}
      {(q.data || []).length === 0 ? <Empty /> : (q.data || []).map((e) => (
        <div key={e.id} className="flex flex-wrap items-center gap-2 border-t border-line/60 py-1 text-xs">
          <span className="font-mono font-bold">{e.road_id}</span>
          <Badge tone={e.state === "CLOSED" ? "crit" : e.state === "RESTRICTED" ? "warn" : "ok"} icon={false}>{e.state}</Badge>
          <span>{e.source} · {e.verification} · {e.reported_by} · {dateTime(e.created_at, area.utc_offset_min)}</span>
          <Badge tone={e.active ? "info" : "muted"} icon={false}>{e.active ? td("active") : td("inactive")}</Badge>
          {e.active && can("field_update") && <Button size="sm" variant="ghost" onClick={() => clear.mutate(e.id)}>{td("clear")}</Button>}
        </div>
      ))}
    </div>
  );
}

function Facilities({ areaId }: { areaId: string }) {
  const td = useTranslations("data");
  const tf = useTranslations("facilityType");
  const { layers, area } = useAreaCtx();
  const { locale } = useLocale();
  const { can } = useAuth();
  const [f, setF] = useState({ facility_type: "SHELTER", name_kk: "", name_ru: "", name_en: "", lon: "", lat: "", criticality: "50", population_served: "0" });
  const { msg, done } = useDone(areaId);
  const add = useMutation({
    mutationFn: () => post(`/api/areas/${areaId}/facilities`, { ...f, lon: Number(f.lon), lat: Number(f.lat), criticality: Number(f.criticality), population_served: Number(f.population_served), name_kk: f.name_kk || null, name_ru: f.name_ru || null, name_en: f.name_en || null }),
    onSuccess: () => done(td("saved")),
  });
  const types = ["HOSPITAL", "CLINIC", "SCHOOL", "SHELTER", "WATER", "POWER", "FIRE", "ADMIN", "CARE_HOME"].filter((x) => tf.has(x));
  return (
    <div className="space-y-3">
      {can("field_update") && (
        <Panel title={td("addFacility")}>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Field label={td("facilityType")}><select className={inputCls} value={f.facility_type} onChange={(e) => setF({ ...f, facility_type: e.target.value })}>{types.map((x) => <option key={x} value={x}>{tf(x)}</option>)}</select></Field>
            <Field label={td("nameKk")}><input className={inputCls} value={f.name_kk} onChange={(e) => setF({ ...f, name_kk: e.target.value })} /></Field>
            <Field label={td("nameRu")}><input className={inputCls} value={f.name_ru} onChange={(e) => setF({ ...f, name_ru: e.target.value })} /></Field>
            <Field label={td("nameEn")}><input className={inputCls} value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} /></Field>
            <Field label={td("lon")}><input className={inputCls} value={f.lon} placeholder={area ? String(area.center[0].toFixed(4)) : ""} onChange={(e) => setF({ ...f, lon: e.target.value })} /></Field>
            <Field label={td("lat")}><input className={inputCls} value={f.lat} placeholder={area ? String(area.center[1].toFixed(4)) : ""} onChange={(e) => setF({ ...f, lat: e.target.value })} /></Field>
            <Field label={td("criticality")}><input type="number" className={inputCls} value={f.criticality} onChange={(e) => setF({ ...f, criticality: e.target.value })} /></Field>
            <Field label={td("populationServed")}><input type="number" className={inputCls} value={f.population_served} onChange={(e) => setF({ ...f, population_served: e.target.value })} /></Field>
          </div>
          <Button className="mt-2" size="sm" variant="primary" disabled={!f.lon || !f.lat || !(f.name_kk || f.name_ru || f.name_en)} busy={add.isPending} onClick={() => add.mutate()}>{td("addFacility")}</Button>
          {add.isError && <ErrorState error={add.error} />}
          {msg && <InlineNote tone="ok" className="mt-2">{msg}</InlineNote>}
        </Panel>
      )}
      <table className="w-full text-xs [&_td]:px-1.5">
        <tbody>
          {(layers.facilities?.features || []).map((x) => (
            <tr key={String(x.properties.id)} className="border-t border-line/60">
              <td className="py-1 font-mono">{String(x.properties.id)}</td>
              <td>{pickName(x.properties.names as never, locale)}</td>
              <td>{tf.has(String(x.properties.facility_type)) ? tf(String(x.properties.facility_type)) : String(x.properties.facility_type)}</td>
              <td className="tabular">{String(x.properties.criticality)}</td>
              <td>{String(x.properties.verification)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface ImportJob { id: string; status: string; import_type: string; filename: string; rows_total: number; rows_valid: number; rows_invalid: number; rows_warning: number; applied_count: number | null; preview?: { row: number; status: string; errors: string[]; warnings: string[]; data: Record<string, unknown> }[] }

function Imports({ areaId }: { areaId: string }) {
  const ti = useTranslations("imports");
  const { can } = useAuth();
  const [type, setType] = useState("resources");
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<ImportJob | null>(null);
  const invalidate = useInvalidateArea();
  const history = useQuery({ queryKey: ["imports", areaId, job?.status], queryFn: () => api<ImportJob[]>(`/api/areas/${areaId}/imports`) });
  const up = useMutation({ mutationFn: () => upload<ImportJob>(`/api/areas/${areaId}/imports?import_type=${type}`, file!), onSuccess: setJob });
  const confirm = useMutation({ mutationFn: () => post<ImportJob>(`/api/imports/${job!.id}/confirm`), onSuccess: (j) => { setJob(j); invalidate(areaId); } });
  const cancel = useMutation({ mutationFn: () => post<ImportJob>(`/api/imports/${job!.id}/cancel`), onSuccess: () => setJob(null) });
  const step = !job ? 0 : job.status === "CONFIRMED" ? 5 : 3;
  const steps = ["upload", "preview", "validate", "errors", "confirm", "import"];
  return (
    <div className="space-y-3">
      <ol className="flex flex-wrap gap-1 text-[10.5px]">
        {steps.map((s, i) => <li key={s} className={`rounded-[3px] border px-2 py-0.5 ${i <= step ? "border-accent text-accent" : "border-line text-muted"}`}>{i + 1}. {ti(`steps.${s}`)}</li>)}
      </ol>
      <InlineNote tone="info">{ti("neverSilent")}</InlineNote>
      {can("field_update") && !job && (
        <Panel title={ti("title")}>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
            <Field label={ti("type")}><select className={inputCls} value={type} onChange={(e) => setType(e.target.value)}>{["resources", "facilities", "observations", "road_events"].map((x) => <option key={x} value={x}>{ti(`types.${x}`)}</option>)}</select></Field>
            <Field label={ti("choose")}><input type="file" accept=".csv,.xlsx,.json,.geojson" className="text-xs" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
            <div className="flex items-end gap-2">
              <Button size="sm" variant="primary" disabled={!file} busy={up.isPending} onClick={() => up.mutate()}>{ti("upload")}</Button>
              <a className="text-[11px] text-accent underline" href={`/api/imports/templates/${type}.csv`}>{ti("template")}</a>
            </div>
          </div>
          {up.isError && <ErrorState error={up.error} />}
        </Panel>
      )}
      {job && (
        <Panel title={`${job.filename} · ${job.status}`}>
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge tone="muted" icon={false}>{ti("rows")}: {job.rows_total}</Badge>
            <Badge tone="ok" icon={false}>{ti("valid")}: {job.rows_valid}</Badge>
            <Badge tone="crit" icon={false}>{ti("invalid")}: {job.rows_invalid}</Badge>
            <Badge tone="warn" icon={false}>{ti("warnings")}: {job.rows_warning}</Badge>
          </div>
          <div className="mt-2 max-h-72 overflow-auto">
            <table className="w-full text-[11px] [&_td]:px-1.5">
              <tbody>
                {(job.preview || []).map((r) => (
                  <tr key={r.row} className={`border-t border-line/60 ${r.status === "INVALID" ? "bg-crit/10" : ""}`}>
                    <td className="font-mono">{ti("row")} {r.row}</td>
                    <td>{r.status}</td>
                    <td className="font-mono text-ink-2">{JSON.stringify(r.data).slice(0, 90)}</td>
                    <td className="text-crit">{r.errors.join("; ")}</td>
                    <td className="text-warn">{r.warnings.join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {step === 3 ? (
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="primary" disabled={job.rows_valid === 0} busy={confirm.isPending} onClick={() => confirm.mutate()}>{ti("confirm", { n: job.rows_valid })}</Button>
              <Button size="sm" variant="ghost" onClick={() => cancel.mutate()}>{ti("cancel")}</Button>
            </div>
          ) : (
            <div className="mt-2 flex items-center gap-2">
              <InlineNote tone="ok">{ti("confirmed", { n: job.applied_count ?? 0, rejected: job.rows_invalid })}</InlineNote>
              <Button size="sm" onClick={() => { setJob(null); setFile(null); }}>{ti("upload")}</Button>
            </div>
          )}
          {confirm.isError && <ErrorState error={confirm.error} />}
        </Panel>
      )}
      <Panel title={ti("history")}>
        {(history.data || []).length === 0 ? <Empty /> : (history.data || []).map((j) => (
          <div key={j.id} className="border-t border-line/60 py-0.5 text-[11px] first:border-0">{j.filename} · {ti.has(`types.${j.import_type}`) ? ti(`types.${j.import_type}`) : j.import_type} · {j.status} · {j.rows_valid}/{j.rows_total}</div>
        ))}
      </Panel>
    </div>
  );
}

function Sources({ areaId }: { areaId: string }) {
  const tc = useTranslations("common");
  const { area } = useAreaCtx();
  const q = useQuery({ queryKey: ["freshness", areaId, area?.data_version], queryFn: () => api<{ sources: Freshness[] }>(`/api/areas/${areaId}/freshness`) });
  if (q.isLoading || !area) return <Loading />;
  return (
    <table className="w-full text-xs [&_td]:px-1.5 [&_th]:px-1.5">
      <thead className="text-left text-[10px] uppercase tracking-wider text-muted"><tr><th>{tc("source")}</th><th>{tc("mode")}</th><th>{tc("status")}</th><th>{tc("quality")}</th><th>{tc("age")}</th></tr></thead>
      <tbody>
        {(q.data?.sources || []).map((s) => (
          <tr key={s.id} className="border-t border-line/60">
            <td className="py-1"><div className="font-semibold">{s.source}</div><div className="text-[10.5px] text-muted">{s.layer} · {s.provider}{s.message ? ` · ${s.message}` : ""}</div></td>
            <td><StatusBadge ns="mode" code={s.mode} icon={false} /></td>
            <td><StatusBadge ns="freshness" code={s.freshness} icon={false} /></td>
            <td>{s.quality || "—"}</td>
            <td className="tabular">{s.last_success_at ? dateTime(s.last_success_at, area.utc_offset_min) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Actions({ areaId }: { areaId: string }) {
  const ta = useTranslations("admin");
  const tat = useTranslations("actionType");
  const { locale } = useLocale();
  const q = useActions(areaId);
  if (q.isLoading) return <Loading />;
  return (
    <div className="space-y-2">
      <InlineNote tone="info">{ta("libraryNote")}</InlineNote>
      <table className="w-full text-xs [&_td]:px-1.5 [&_th]:px-1.5">
        <thead className="text-left text-[10px] uppercase tracking-wider text-muted"><tr><th>ID</th><th>{ta("library")}</th><th>{ta("requirements")}</th><th>{ta("durations")}</th><th>{ta("approvedBy")}</th></tr></thead>
        <tbody>
          {(q.data || []).map((a) => (
            <tr key={a.id} className="border-t border-line/60 align-top">
              <td className="py-1 font-mono">{a.id} v{a.version}</td>
              <td><div className="font-semibold">{pickName(a.names, locale)}</div><div className="text-[10.5px] text-muted">{tat.has(a.action_type) ? tat(a.action_type) : a.action_type}</div></td>
              <td className="font-mono text-[10.5px]">{[a.requirements.crew && `crew ${a.requirements.crew.types.join("/")}×${a.requirements.crew.count}`, a.requirements.vehicle && `veh ${a.requirements.vehicle.types.join("/")}`, a.requirements.pumps && `pumps ${a.requirements.pumps}`, a.requirements.equipment && Object.entries(a.requirements.equipment).map(([k, v]) => `${k}×${v}`).join(" ")].filter(Boolean).join(" · ")}</td>
              <td className="tabular">{a.setup_min} / {a.execution_min} / {a.safety_buffer_min} min</td>
              <td>{a.approved_by || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
