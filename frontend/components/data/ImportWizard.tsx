"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCircle2, Download, FileSpreadsheet, FileUp, Lightbulb, Map as MapIcon, RotateCcw, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState, type DragEvent } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { Badge, Button, Empty, ErrorState, InlineNote, Panel, StatusBadge } from "@/components/ui/primitives";
import { api, post, upload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime } from "@/lib/format";
import { useInvalidateArea } from "@/lib/queries";

type Kind = "resources" | "facilities" | "observations" | "road_events";
const KINDS: Kind[] = ["observations", "road_events", "resources", "facilities"];
const MAX_BYTES = 10 * 1024 * 1024;
const EXTENSIONS = [".csv", ".txt", ".xlsx", ".json", ".geojson"];

type Ref = "stations" | "roads" | "bases" | "sectors";
interface FieldSpec { col: string; req?: boolean; values?: string[]; ns?: string; ref?: Ref }

const FIELDS: Record<Kind, FieldSpec[]> = {
  observations: [
    { col: "station_id", req: true, ref: "stations" },
    { col: "observed_at", req: true },
    { col: "utc_offset" },
    { col: "water_level_cm", req: true },
    { col: "discharge_m3s" },
    { col: "source", req: true },
    { col: "source_type", req: true, values: ["FIELD", "HYDROPOST", "FORECAST", "SATELLITE", "GLOBAL_MODEL", "SIMULATION"], ns: "source" },
    { col: "verification", values: ["UNVERIFIED", "VERIFIED", "REJECTED"], ns: "verification" },
    { col: "notes" },
  ],
  road_events: [
    { col: "road_id", req: true, ref: "roads" },
    { col: "segment_ids" },
    { col: "state", req: true, values: ["CLOSED", "RESTRICTED", "OPEN"], ns: "road" },
    { col: "effective_from" },
    { col: "effective_until" },
    { col: "utc_offset" },
    { col: "source" },
    { col: "verification", values: ["UNVERIFIED", "VERIFIED"], ns: "verification" },
    { col: "notes" },
  ],
  resources: [
    { col: "id", req: true },
    { col: "resource_type", req: true, values: ["CREW", "PUMP", "VEHICLE", "EQUIPMENT", "OTHER"], ns: "resourceType" },
    { col: "subtype", values: ["RESCUE", "ENGINEERING", "GENERAL", "MOBILE_PUMP", "TRUCK", "HIGH_CLEARANCE", "PICKUP", "EXCAVATOR", "SANDBAG_FILLER", "GENERIC"], ns: "subtype" },
    { col: "capacity" },
    { col: "capacity_unit" },
    { col: "base_id", ref: "bases" },
    { col: "name_kk" }, { col: "name_ru" }, { col: "name_en" },
    { col: "status", values: ["AVAILABLE", "UNAVAILABLE", "FAILED"], ns: "resourceStatus" },
  ],
  facilities: [
    { col: "id" },
    { col: "facility_type", req: true, values: ["HOSPITAL", "CLINIC", "CARE_HOME", "SCHOOL", "SHELTER", "WATER_SUPPLY", "POWER", "HEATING", "FIRE_STATION", "ADMINISTRATION", "OTHER"], ns: "facilityType" },
    { col: "name_kk" }, { col: "name_ru" }, { col: "name_en" },
    { col: "lon", req: true }, { col: "lat", req: true },
    { col: "criticality" },
    { col: "population_served" },
    { col: "sector_id", ref: "sectors" },
    { col: "verification", values: ["UNVERIFIED", "VERIFIED"], ns: "verification" },
    { col: "source" },
  ],
};

interface PreviewRow { row: number; status: "VALID" | "INVALID" | "WARNING"; errors: string[]; warnings: string[]; data: Record<string, unknown> }
interface ImportJob {
  id: string; status: string; import_type: string; filename: string; file_format?: string; created_by?: string; created_at?: string;
  rows_total: number; rows_valid: number; rows_invalid: number; rows_warning: number; applied_count: number | null;
  failed_on_apply?: { row: number; error: string; message?: string }[];
  preview?: { rows?: PreviewRow[]; columns?: string[]; missing_columns?: string[]; unknown_columns?: string[] } | null;
  pipeline?: { plan_status?: string | null } | null;
}
type Filter = "all" | "INVALID" | "WARNING";

function fmtSize(b: number, tu: (k: string) => string) {
  return b < 1024 ? `${b} ${tu("b")}` : b < 1024 * 1024 ? `${(b / 1024).toFixed(1)} ${tu("kb")}` : `${(b / 1024 / 1024).toFixed(1)} ${tu("mb")}`;
}

function cell(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.join("; ") || "—";
  return String(v);
}

export function ImportWizard({ areaId }: { areaId: string }) {
  const ti = useTranslations("imports");
  const t = useTranslations();
  const tu = useTranslations("units");
  const { area, layers } = useAreaCtx();
  const { can } = useAuth();
  const invalidate = useInvalidateArea();
  const [kind, setKind] = useState<Kind>("observations");
  const [file, setFile] = useState<File | null>(null);
  const [clientErr, setClientErr] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const inputRef = useRef<HTMLInputElement>(null);
  const history = useQuery({ queryKey: ["imports", areaId, job?.id, job?.status], queryFn: () => api<ImportJob[]>(`/api/areas/${areaId}/imports`) });

  const refs = useMemo(() => {
    const ids = (k: string, prop = "id") => Array.from(new Set((layers[k]?.features || []).map((f) => String(f.properties[prop] ?? "")).filter(Boolean)))
      .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    return { stations: ids("stations"), roads: ids("roads", "road_id"), bases: ids("bases"), sectors: ids("sectors") } as Record<Ref, string[]>;
  }, [layers]);

  const reset = () => { setJob(null); setRows([]); setFile(null); setFilter("all"); setClientErr(null); if (inputRef.current) inputRef.current.value = ""; };

  const pick = (f: File | null | undefined) => {
    setClientErr(null);
    if (!f) return;
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (!EXTENSIONS.includes(ext)) { setFile(null); setClientErr(ti("badExtension")); return; }
    if (f.size > MAX_BYTES) { setFile(null); setClientErr(ti("tooBig")); return; }
    if (f.size === 0) { setFile(null); setClientErr(t("errors.empty_file")); return; }
    setFile(f);
  };

  const up = useMutation({
    mutationFn: () => upload<ImportJob>(`/api/areas/${areaId}/imports?import_type=${kind}`, file!),
    onSuccess: (j) => { setJob(j); setRows(j.preview?.rows || []); setFilter(j.rows_invalid ? "INVALID" : "all"); },
  });
  const confirm = useMutation({
    mutationFn: () => post<ImportJob>(`/api/imports/${job!.id}/confirm`),
    onSuccess: (j) => { setJob((prev) => ({ ...prev, ...j, preview: prev?.preview })); invalidate(areaId); },
  });
  const cancel = useMutation({ mutationFn: () => post<ImportJob>(`/api/imports/${job!.id}/cancel`), onSuccess: reset });
  const reopen = useMutation({
    mutationFn: (id: string) => api<ImportJob>(`/api/imports/${id}`),
    onSuccess: (j) => { setJob(j); setRows(j.preview?.rows || []); setFilter(j.rows_invalid ? "INVALID" : "all"); window.scrollTo({ top: 0, behavior: "smooth" }); },
  });

  const issue = (code: string) => {
    const i = code.indexOf(":");
    const key = i >= 0 ? code.slice(0, i) : code;
    const field = i >= 0 ? code.slice(i + 1) : "";
    return ti.has(`issue.${key}`) ? ti(`issue.${key}`, { field }) : code;
  };

  const step = !job ? (file ? 1 : 0) : job.status === "CONFIRMED" ? 5 : job.rows_invalid ? 3 : 4;
  const steps = ["upload", "preview", "validate", "errors", "confirm", "import"];
  const shown = rows.filter((r) => filter === "all" || r.status === filter);
  const fields = FIELDS[kind];
  // preview columns follow the job's own type; utc_offset is already folded into the timestamps
  const jobKind = (job?.import_type as Kind) || kind;
  const cols = (FIELDS[jobKind] || fields).map((f) => f.col).filter((c) => c !== "utc_offset" && (!rows.length || rows.some((r) => r.data && c in r.data)));
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); };
  const confirmed = job?.status === "CONFIRMED";

  return (
    <div className="space-y-3">
      <ol className="flex flex-wrap gap-1 text-[10.5px]" aria-label={ti("title")}>
        {steps.map((s, i) => (
          <li key={s} className={clsx("flex items-center gap-1 rounded-full border px-2.5 py-0.5", i < step ? "border-ok/50 bg-ok/10 text-ok" : i === step ? "border-accent bg-accent/15 font-bold text-accent" : "border-line text-muted")}>
            {i < step ? <CheckCircle2 className="h-3 w-3" /> : <span className="tabular">{i + 1}</span>}{ti(`steps.${s}`)}
          </li>
        ))}
      </ol>

      {!job && (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4" role="radiogroup" aria-label={ti("type")}>
            {KINDS.map((k) => (
              <button key={k} role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
                className={clsx("rounded-[5px] border p-2.5 text-left transition-colors", kind === k ? "border-accent bg-accent/10 shadow-[0_0_0_1px_rgba(63,179,255,0.35)]" : "border-line bg-panel hover:border-line-2 hover:bg-panel-2")}>
                <div className={clsx("text-xs font-bold", kind === k ? "text-accent" : "text-ink")}>{ti(`types.${k}`)}</div>
                <div className="mt-0.5 text-[11px] leading-snug text-ink-2">{ti(`typeDesc.${k}`)}</div>
                <div className="mt-1 text-[10.5px] leading-snug text-muted">{ti(`effect.${k}`)}</div>
              </button>
            ))}
          </div>

          {can("field_update") ? (
            <div
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={onDrop}
              className={clsx("rounded-[6px] border-2 border-dashed p-4 transition-colors", drag ? "border-accent bg-accent/10" : file ? "border-ok/60 bg-ok/5" : "border-line-2 bg-panel/60")}
            >
              <input ref={inputRef} id="argus-import-file" type="file" accept={EXTENSIONS.join(",")} className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
              <div className="flex flex-wrap items-center gap-3">
                <div className={clsx("grid h-11 w-11 shrink-0 place-items-center rounded-full", file ? "bg-ok/15 text-ok" : "bg-accent/15 text-accent")}>
                  {file ? <FileSpreadsheet className="h-5 w-5" /> : <FileUp className="h-5 w-5" />}
                </div>
                <div className="min-w-0 flex-1">
                  {file ? (
                    <>
                      <div className="truncate text-sm font-semibold">{file.name}</div>
                      <div className="text-[11px] text-muted">{fmtSize(file.size, tu)} · {ti(`types.${kind}`)}</div>
                    </>
                  ) : (
                    <>
                      <div className="text-sm font-semibold">{ti("drop")}</div>
                      <div className="text-[11px] text-muted">{ti("dropHint")}</div>
                    </>
                  )}
                </div>
                <label htmlFor="argus-import-file" className="cursor-pointer rounded-[3px] border border-line-2 bg-panel-2 px-3 py-1.5 text-xs font-semibold hover:border-accent">
                  {file ? ti("changeFile") : ti("browse")}
                </label>
                {file && <button aria-label={ti("removeFile")} title={ti("removeFile")} onClick={reset} className="grid h-7 w-7 place-items-center rounded text-muted hover:bg-panel-2 hover:text-ink"><X className="h-4 w-4" /></button>}
                <Button variant="primary" icon={FileUp} disabled={!file} busy={up.isPending} onClick={() => up.mutate()}>{ti("upload")}</Button>
              </div>
              {clientErr && <InlineNote tone="crit" className="mt-2">{clientErr}</InlineNote>}
              {up.isError && <div className="mt-2"><ErrorState error={up.error} /></div>}
            </div>
          ) : (
            <InlineNote tone="info">{ti("viewOnly")}</InlineNote>
          )}

          <Panel
            title={ti("guideTitle", { type: ti(`types.${kind}`) })}
            right={<a className="flex items-center gap-1 text-[11px] font-semibold text-accent hover:underline" href={`/api/imports/templates/${kind}.csv`} download>
              <Download className="h-3.5 w-3.5" />{ti("template")}</a>}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-[11.5px] [&_td]:px-2 [&_td]:py-1 [&_th]:px-2">
                <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
                  <tr><th>{ti("column")}</th><th>{ti("needed")}</th><th>{ti("meaning")}</th><th>{ti("allowed")}</th></tr>
                </thead>
                <tbody>
                  {fields.map((f) => (
                    <tr key={f.col} className="border-t border-line/60 align-top">
                      <td className="whitespace-nowrap font-mono font-semibold text-ink">{f.col}</td>
                      <td>{f.req ? <Badge tone="warn" icon={false}>{ti("required")}</Badge> : <span className="text-muted">{ti("optional")}</span>}</td>
                      <td className="text-ink-2">{ti(`col.${f.col}`)}</td>
                      <td className="text-[11px]">
                        {f.values && (
                          <div className="flex flex-wrap gap-1">
                            {f.values.map((v) => {
                              const key = `${f.ns}.${v}`;
                              return <span key={v} title={t.has(key) ? t(key) : v} className="rounded-sm border border-line-2 bg-bg px-1 font-mono text-[10.5px]">{v}{t.has(key) && <span className="ml-1 font-sans text-muted">{t(key)}</span>}</span>;
                            })}
                          </div>
                        )}
                        {f.ref && (refs[f.ref].length ? (
                          <div className="font-mono text-[10.5px] text-ink-2">
                            <span className="font-sans text-muted">{ti("inThisArea")}: </span>
                            {refs[f.ref].slice(0, 14).join(", ")}{refs[f.ref].length > 14 && <span className="font-sans text-muted"> {ti("andMore", { n: refs[f.ref].length - 14 })}</span>}
                          </div>
                        ) : <span className="text-muted">—</span>)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2 grid grid-cols-1 gap-1.5 md:grid-cols-3">
              {["tipExcel", "tipTime", "tipNumbers"].map((k) => (
                <div key={k} className="flex items-start gap-1.5 rounded-[3px] border border-line bg-bg/40 px-2 py-1.5 text-[11px] leading-snug text-ink-2">
                  <Lightbulb className="mt-[1px] h-3.5 w-3.5 shrink-0 text-watch" />{ti(k)}
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}

      {job && (
        <Panel
          title={<span className="flex items-center gap-2"><span className="normal-case tracking-normal">{job.filename}</span><StatusBadge ns="imports.jobStatus" code={job.status} icon={false} /></span>}
          right={<span className="text-[11px] text-muted">{ti(`types.${job.import_type}`)}{job.file_format ? ` · ${job.file_format}` : ""}</span>}
        >
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Tile label={ti("rows")} value={job.rows_total} />
            <Tile label={ti("valid")} value={job.rows_valid} tone="ok" />
            <Tile label={ti("invalid")} value={job.rows_invalid} tone={job.rows_invalid ? "crit" : undefined} />
            <Tile label={ti("warnings")} value={job.rows_warning} tone={job.rows_warning ? "warn" : undefined} />
          </div>

          {!!job.preview?.missing_columns?.length && (
            <InlineNote tone="crit" className="mt-2">{ti("missingColumns", { cols: job.preview.missing_columns.join(", ") })}</InlineNote>
          )}
          {!!job.preview?.unknown_columns?.length && (
            <InlineNote tone="warn" className="mt-2">{ti("unknownColumns", { cols: job.preview.unknown_columns.join(", ") })}</InlineNote>
          )}
          {job.rows_total === 0 && <InlineNote tone="warn" className="mt-2">{ti("noRows")}</InlineNote>}

          {rows.length > 0 && (
            <>
              <div className="mt-3 flex flex-wrap items-center gap-1" role="tablist">
                {(["all", "INVALID", "WARNING"] as Filter[]).map((f) => {
                  const n = f === "all" ? rows.length : rows.filter((r) => r.status === f).length;
                  return (
                    <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
                      className={clsx("rounded-full border px-2.5 py-0.5 text-[11px] font-semibold", filter === f ? "border-accent bg-accent/15 text-accent" : "border-line text-ink-2 hover:bg-panel-2")}>
                      {ti(`filter.${f}`)} <span className="tabular">{n}</span>
                    </button>
                  );
                })}
              </div>
              <div className="mt-2 max-h-[420px] overflow-auto rounded-[3px] border border-line">
                <table className="w-full text-[11px] [&_td]:px-2 [&_td]:py-1 [&_th]:px-2 [&_th]:py-1">
                  <thead className="sticky top-0 bg-panel-2 text-left text-[10px] uppercase tracking-wider text-muted">
                    <tr><th>{ti("row")}</th><th>{ti("statusCol")}</th>{cols.slice(0, 5).map((c) => <th key={c} className="font-mono normal-case">{c}</th>)}<th>{ti("issues")}</th></tr>
                  </thead>
                  <tbody>
                    {shown.slice(0, 300).map((r) => (
                      <tr key={r.row} className={clsx("border-t border-line/60 align-top", r.status === "INVALID" && "bg-crit/10", r.status === "WARNING" && "bg-warn/5")}>
                        <td className="tabular text-muted">{r.row}</td>
                        <td><StatusBadge ns="imports.rowStatus" code={r.status} icon={false} /></td>
                        {cols.slice(0, 5).map((c) => <td key={c} className="max-w-[160px] truncate font-mono" title={cell(r.data?.[c])}>{cell(r.data?.[c])}</td>)}
                        <td className="min-w-[220px]">
                          {(r.errors || []).map((e) => <div key={e} className="text-crit">• {issue(e)}</div>)}
                          {(r.warnings || []).map((w) => <div key={w} className="text-warn">• {issue(w)}</div>)}
                          {!(r.errors || []).length && !(r.warnings || []).length && <span className="text-ok">✓</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {shown.length === 0 && <div className="p-3 text-center text-[11px] text-muted">{ti("nothingHere")}</div>}
              </div>
              {shown.length > 300 && <p className="mt-1 text-[10.5px] text-muted">{ti("showingFirst", { n: 300, total: shown.length })}</p>}
            </>
          )}

          {!confirmed ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button variant="primary" icon={ShieldCheck} disabled={job.rows_valid === 0} busy={confirm.isPending} onClick={() => confirm.mutate()}>
                {ti("confirm", { n: job.rows_valid })}
              </Button>
              <Button variant="ghost" busy={cancel.isPending} onClick={() => cancel.mutate()}>{ti("cancel")}</Button>
              <span className="text-[11px] text-muted">{job.rows_invalid ? ti("invalidSkipped", { n: job.rows_invalid }) : ti("allGood")}</span>
            </div>
          ) : (
            <div className="mt-3 space-y-2 rounded-[4px] border border-ok/40 bg-ok/5 p-3">
              <div className="flex items-center gap-2 text-sm font-bold text-ok"><CheckCircle2 className="h-4 w-4" />{ti("confirmed", { n: job.applied_count ?? 0, rejected: job.rows_invalid })}</div>
              {!!job.failed_on_apply?.length && (
                <div className="text-[11px] text-warn">
                  <div className="font-semibold">{ti("failedOnApply", { n: job.failed_on_apply.length })}</div>
                  {job.failed_on_apply.slice(0, 20).map((f) => <div key={f.row}>• {ti("row")} {f.row}: {t.has(`errors.${f.error}`) ? t(`errors.${f.error}`) : t("errors.generic", { code: f.error })}</div>)}
                </div>
              )}
              {job.pipeline?.plan_status && (
                <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">{ti("planRechecked")} <StatusBadge ns="ops.outcome" code={job.pipeline.plan_status} /></div>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                <Link href={`/area/${areaId}/situation`} className="flex items-center gap-1 rounded-[3px] border border-accent/60 bg-accent/10 px-2.5 py-1 text-xs font-semibold text-accent hover:bg-accent/20"><MapIcon className="h-3.5 w-3.5" />{ti("openMap")}</Link>
                <Link href={`/area/${areaId}/plan`} className="rounded-[3px] border border-line-2 px-2.5 py-1 text-xs font-semibold hover:bg-panel-2">{ti("openPlan")}</Link>
                <Button size="sm" icon={RotateCcw} onClick={reset}>{ti("another")}</Button>
              </div>
            </div>
          )}
          {(confirm.isError || cancel.isError) && <div className="mt-2"><ErrorState error={confirm.error || cancel.error} /></div>}
        </Panel>
      )}

      {reopen.isError && <ErrorState error={reopen.error} />}
      <Panel title={ti("history")}>
        {history.isError ? <ErrorState error={history.error} onRetry={() => history.refetch()} /> : (history.data || []).length === 0 ? <Empty>{ti("historyEmpty")}</Empty> : (
          <table className="w-full text-[11px] [&_td]:px-1.5 [&_td]:py-1 [&_th]:px-1.5">
            <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
              <tr><th>{ti("when")}</th><th>{ti("file")}</th><th>{ti("type")}</th><th>{ti("statusCol")}</th><th>{ti("valid")}</th><th>{ti("by")}</th><th /></tr>
            </thead>
            <tbody>
              {(history.data || []).map((j) => (
                <tr key={j.id} className="border-t border-line/60">
                  <td className="tabular whitespace-nowrap text-muted">{j.created_at ? dateTime(j.created_at, area?.utc_offset_min ?? 300) : "—"}</td>
                  <td className="max-w-[220px] truncate" title={j.filename}>{j.filename}</td>
                  <td>{ti.has(`types.${j.import_type}`) ? ti(`types.${j.import_type}`) : j.import_type}</td>
                  <td><StatusBadge ns="imports.jobStatus" code={j.status} icon={false} /></td>
                  <td className="tabular">{j.status === "CONFIRMED" ? (j.applied_count ?? 0) : j.rows_valid}/{j.rows_total}</td>
                  <td className="font-mono">{j.created_by || "—"}</td>
                  <td className="text-right">{j.status === "PREVIEW" && can("field_update") && job?.id !== j.id && (
                    <Button size="sm" variant="accent" busy={reopen.isPending && reopen.variables === j.id} onClick={() => reopen.mutate(j.id)}>{ti("resume")}</Button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: number; tone?: "ok" | "crit" | "warn" }) {
  return (
    <div className={clsx("rounded-[4px] border px-3 py-2", tone === "ok" ? "border-ok/40 bg-ok/5" : tone === "crit" ? "border-crit/40 bg-crit/5" : tone === "warn" ? "border-warn/40 bg-warn/5" : "border-line bg-bg/40")}>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className={clsx("tabular text-xl font-bold", tone === "ok" ? "text-ok" : tone === "crit" ? "text-crit" : tone === "warn" ? "text-warn" : "text-ink")}>{value}</div>
    </div>
  );
}
