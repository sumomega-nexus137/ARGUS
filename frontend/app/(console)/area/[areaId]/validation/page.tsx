"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { Badge, Button, Empty, ErrorState, InlineNote, Loading, Metric, Panel } from "@/components/ui/primitives";
import { api, getToken, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, num, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import type { Names } from "@/lib/types";

interface Conf { iou: number | null; precision: number | null; recall: number | null; f1: number | null; tp_cells: number; fp_cells: number; fn_cells: number; evaluated_cells: number; true_overlap_km2: number; false_positive_km2: number; false_negative_km2: number }
interface Run {
  id: string; dataset_id: string; kind: string; status: string; created_at: string; created_by: string;
  metrics: { iou: number; precision: number; recall: number; f1: number; true_overlap_km2: number; false_positive_km2: number; false_negative_km2: number; observed_km2: number; modelled_km2: number };
  result: {
    warning?: string; label?: string; headline?: string; direct_aoi?: Conf;
    protocol_metrics?: { holdout: Conf; calibration: Conf; all_usable: Conf; grid_m: number; protocol: { slope_max_deg: number; distance_max_m: number; jrc_permanent_min: number; block_m: number } };
  };
}
interface HistoricalInfo {
  label: string;
  observed_qc: { status: string; technical_visual_review: string | null; certification: string };
  satellite: { flood_item: string; flood_datetime: string; reference_item: string; reference_datetime: string; flood_cloud_cover_percent: number; reason: string } | null;
  mask_method: { common_clear_fraction: number; observed_flood_area_m2_raw_pixel_count: number; caveats: string[] } | null;
  model: { kind: string; algorithm: string; uses_raw_xy_coordinates: boolean } | null;
  limitations: string[];
  has_qc_png: boolean;
}
interface ValidationPayload {
  datasets: { id: string; name: Names; event: string; observed_source: string; status: string; path: string; kind: string }[];
  runs: Run[];
  historical: HistoricalInfo | null;
}
interface AAR {
  plan_versions: { id: string; plan: string; version: number; status: string; origin: string; approved_by: string | null }[];
  delayed_tasks: { task: string; delay_min?: number }[];
  missed_windows: { task: string; deadline: number | null; deadline_reason: string; issues: string[] }[];
  route_failures: { event_id: string; road_id: string; tasks_rerouted_or_blocked: string[] }[];
  resource_bottlenecks: { resource?: string; task?: string }[];
  unavailable_resources: { id?: string; resource?: string; status?: string }[];
  forecast_errors: { version: number; station_id: string; member: string; bias_cm: number | null; mae_cm: number | null; n: number }[];
}

function useAuthImage(url: string | null) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!url) return;
    let revoked = "";
    fetch(url, { headers: { Authorization: `Bearer ${getToken() || ""}` } })
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => { if (b) { revoked = URL.createObjectURL(b); setSrc(revoked); } });
    return () => { if (revoked) URL.revokeObjectURL(revoked); };
  }, [url]);
  return src;
}

export default function ValidationPage() {
  const { areaId, area, fmt } = useAreaCtx();
  const tv = useTranslations("validation");
  const ti = useTranslations("issues");
  const tps = useTranslations("planStatus");
  const tor = useTranslations("origin");
  const tr = (ns: typeof ti, k: string) => (ns.has(k) ? ns(k) : k);
  const { locale } = useLocale();
  const { can } = useAuth();
  const qc = useQueryClient();
  const v = useQuery({ queryKey: ["validation", areaId, area?.data_version], queryFn: () => api<ValidationPayload>(`/api/areas/${areaId}/validation`) });
  const aar = useQuery({ queryKey: ["aar", areaId, area?.data_version], queryFn: () => api<AAR>(`/api/areas/${areaId}/after-action`) });
  const [sel, setSel] = useState<string | null>(null);
  const synth = useMutation({ mutationFn: () => post<Run>(`/api/areas/${areaId}/validation/synthetic`), onSuccess: (r) => { setSel(r.id); qc.invalidateQueries({ queryKey: ["validation", areaId] }); } });
  const real = useMutation({ mutationFn: (ds: string) => post<Run>(`/api/areas/${areaId}/validation/run`, { dataset_id: ds }), onSuccess: (r) => { setSel(r.id); qc.invalidateQueries({ queryKey: ["validation", areaId] }); } });

  if (v.isLoading || !area) return <div className="p-3"><ScreenHeader screen="validation" /><Loading /></div>;
  if (v.isError) return <div className="p-3"><ScreenHeader screen="validation" /><ErrorState error={v.error} /></div>;
  const run = v.data!.runs.find((r) => r.id === sel) || v.data!.runs[0];
  const pct = (x: number) => `${num(x * 100, 1, locale)}%`;

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3">
      <ScreenHeader screen="validation" />
      <Panel title={tv("datasets")}>
        {v.data!.datasets.map((d) => (
          <div key={d.id} className="flex flex-wrap items-center gap-2 border-t border-line/60 py-2 text-xs first:border-0">
            <span className="font-semibold">{pickName(d.name, locale)}</span>
            <Badge tone={d.status === "READY" ? "ok" : d.status === "PARTIAL" ? "warn" : "crit"}>{tv(`status.${d.status}`)}</Badge>
            <span className="text-muted">{d.observed_source}</span>
            {d.status === "READY" && can("plan_edit") && <Button size="sm" variant="primary" busy={real.isPending} onClick={() => real.mutate(d.id)}>{tv("run")}</Button>}
            {d.status !== "READY" && (
              <div className="w-full">
                <InlineNote tone="crit"><b>{tv("notLoaded")}</b> — {tv("notLoadedDesc", { path: d.path })}</InlineNote>
              </div>
            )}
          </div>
        ))}
        {can("plan_edit") && <Button size="sm" className="mt-2" busy={synth.isPending} onClick={() => synth.mutate()}>{tv("synthetic")}</Button>}
        {(synth.error || real.error) && <ErrorState error={synth.error || real.error} />}
      </Panel>

      {v.data!.historical && <HistoricalEvidence h={v.data!.historical} areaId={areaId} />}

      {run ? (
        <Panel title={`${tv("metrics")} · ${run.dataset_id} · ${dateTime(run.created_at, area.utc_offset_min)}`}>
          {run.kind === "SYNTHETIC_SELF_TEST" && <InlineNote tone="sim" className="mb-2">{tv("syntheticWarning")}</InlineNote>}
          {run.result.label === "HISTORICAL_SAME_EVENT_SPATIAL_HOLDOUT" && (
            <div className="mb-2 space-y-1">
              <div className="flex flex-wrap gap-1"><Badge tone="info">{tv("holdoutLabel")}</Badge><Badge tone="muted">{tv("historical")}</Badge></div>
              <InlineNote tone="warn">{tv("holdoutNot")}</InlineNote>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric big label={tv("iou")} value={pct(run.metrics.iou)} />
            <Metric big label={tv("precision")} value={pct(run.metrics.precision)} />
            <Metric big label={tv("recall")} value={pct(run.metrics.recall)} />
            <Metric big label={tv("f1")} value={pct(run.metrics.f1)} />
            <Metric label={tv("overlap")} value={`${num(run.metrics.true_overlap_km2, 2, locale)} ${tv("km2")}`} tone="ok" />
            <Metric label={tv("fp")} value={`${num(run.metrics.false_positive_km2, 2, locale)} ${tv("km2")}`} tone="warn" />
            <Metric label={tv("fn")} value={`${num(run.metrics.false_negative_km2, 2, locale)} ${tv("km2")}`} tone="crit" />
          </div>
          <p className="mt-2 font-mono text-[10.5px] text-muted">{tv("formula")}</p>
          {run.result.protocol_metrics && <ProtocolTable r={run.result} />}
          <Curtain runId={run.id} />
          {v.data!.runs.length > 1 && (
            <div className="mt-2 flex flex-wrap gap-1 text-[11px]">
              <span className="text-muted">{tv("runs")}:</span>
              {v.data!.runs.map((r) => <button key={r.id} onClick={() => setSel(r.id)} className={r.id === run.id ? "text-accent underline" : "text-ink-2"}>{r.id}</button>)}
            </div>
          )}
        </Panel>
      ) : <Empty>{tv("noRun")}</Empty>}

      <Panel title={tv("afterAction")}>
        {aar.data ? (
          <div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
            <AarList title={tv("missed")} items={aar.data.missed_windows.map((m) => `${m.task} · ${fmt(m.deadline)} · ${m.issues.map((i) => tr(ti, i)).join(", ")}`)} none={tv("none")} tone="crit" />
            <AarList title={tv("delayed")} items={aar.data.delayed_tasks.map((d) => `${d.task}${d.delay_min ? ` ${tv("delayMin", { n: d.delay_min })}` : ""}`)} none={tv("none")} />
            <AarList title={tv("routeFailures")} items={aar.data.route_failures.map((r) => `${r.road_id} → ${r.tasks_rerouted_or_blocked.join(", ") || "—"}`)} none={tv("none")} />
            <AarList title={tv("unavailableResources")} items={aar.data.unavailable_resources.map((r) => `${r.id || r.resource} ${r.status || ""}`)} none={tv("none")} />
            <AarList title={tv("versions")} items={aar.data.plan_versions.map((p) => `${p.plan} v${p.version} · ${tr(tps, p.status)} · ${tr(tor, p.origin)}${p.approved_by ? ` · ${p.approved_by}` : ""}`)} none={tv("none")} />
            <AarList title={tv("modelErrors")} items={aar.data.forecast_errors.map((e) => `${e.station_id} v${e.version} ${e.member}: ${tv("bias")} ${e.bias_cm ?? "—"} · ${tv("mae")} ${e.mae_cm ?? "—"} (n=${e.n})`)} none={tv("none")} />
          </div>
        ) : <Loading />}
      </Panel>
    </div>
  );
}

function ProtocolTable({ r }: { r: Run["result"] }) {
  const tv = useTranslations("validation");
  const { locale } = useLocale();
  const pm = r.protocol_metrics!;
  const rows: [string, Conf, string][] = [
    [tv("rowHoldout"), pm.holdout, "font-bold text-ink"], [tv("rowCalibration"), pm.calibration, ""], [tv("rowAllUsable"), pm.all_usable, ""],
    ...(r.direct_aoi ? [[tv("rowDirect"), r.direct_aoi, "text-muted"] as [string, Conf, string]] : []),
  ];
  const p = (x: number | null) => (x === null ? "—" : num(x, 4, locale));
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-[11px] [&_td]:px-1.5 [&_th]:px-1.5">
        <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
          <tr><th>{tv("evaluation")}</th><th>IoU</th><th>{tv("precision")}</th><th>{tv("recall")}</th><th>F1</th><th>{tv("cells")}</th></tr>
        </thead>
        <tbody>
          {rows.map(([label, c, cls]) => (
            <tr key={label} className={`border-t border-line/60 ${cls}`}>
              <td className="py-1">{label}</td><td className="tabular">{p(c.iou)}</td><td className="tabular">{p(c.precision)}</td>
              <td className="tabular">{p(c.recall)}</td><td className="tabular">{p(c.f1)}</td><td className="tabular">{num(c.evaluated_cells, 0, locale)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[10.5px] text-muted">{tv("protocolText", { grid: pm.grid_m, block: pm.protocol.block_m, slope: pm.protocol.slope_max_deg, dist: pm.protocol.distance_max_m / 1000, jrc: pm.protocol.jrc_permanent_min })}</p>
      <p className="text-[10.5px] text-muted">{tv("directExplain")}</p>
    </div>
  );
}

function HistoricalEvidence({ h, areaId }: { h: HistoricalInfo; areaId: string }) {
  const tv = useTranslations("validation");
  const { locale } = useLocale();
  const qc = useAuthImage(h.has_qc_png ? `/api/areas/${areaId}/validation/qc.png` : null);
  return (
    <Panel title={tv("evidence")} right={<Badge tone="warn">{tv("requiresQc")}</Badge>}>
      <div className="grid grid-cols-1 gap-3 text-[11.5px] md:grid-cols-2">
        <div className="space-y-1">
          {h.satellite && (
            <>
              <div className="font-semibold">{tv("sentinel2Fallback")}</div>
              <div>{tv("floodScene")}: <span className="font-mono">{h.satellite.flood_item}</span> · {h.satellite.flood_datetime.slice(0, 16).replace("T", " ")} UTC · {tv("cloud")} {num(h.satellite.flood_cloud_cover_percent, 1, locale)}%</div>
              <div>{tv("referenceScene")}: <span className="font-mono">{h.satellite.reference_item}</span> · {h.satellite.reference_datetime.slice(0, 16).replace("T", " ")} UTC</div>
              <div className="text-muted">{tv("noS1")}</div>
            </>
          )}
          {h.mask_method && <div>{tv("usableCoverage")}: {num(h.mask_method.common_clear_fraction * 100, 2, locale)}% · {tv("observedArea")}: {num(h.mask_method.observed_flood_area_m2_raw_pixel_count / 1e6, 2, locale)} {tv("km2")}</div>}
          <InlineNote tone="warn">{tv("qcState")}: {h.observed_qc.status} · {tv("visualReview")}: {h.observed_qc.technical_visual_review || "—"} · {tv("notCertified")}</InlineNote>
          {h.model && <div className="text-muted">{tv("modelKind")}: {h.model.algorithm} · {tv("noXY")}</div>}
          {h.limitations.length > 0 && (
            <details className="text-[11px]"><summary className="cursor-pointer font-semibold text-muted">{tv("limitations")}</summary>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-ink-2">{h.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></details>
          )}
        </div>
        <div>
          {qc && <img src={qc} alt={tv("qcFigure")} className="w-full rounded-[3px] border border-line" />}
          <p className="mt-1 text-[10px] text-muted">{tv("qcFigure")}</p>
        </div>
      </div>
    </Panel>
  );
}

function AarList({ title, items, none, tone }: { title: string; items: string[]; none: string; tone?: "crit" }) {
  return (
    <div>
      <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">{title}</div>
      {items.length === 0 ? <div className="text-muted">{none}</div> : items.map((x, i) => <div key={i} className={tone === "crit" ? "text-crit" : ""}>{x}</div>)}
    </div>
  );
}

/** Curtain comparison: drag to reveal OBSERVED (left) vs MODELLED (right); difference layer below. */
function Curtain({ runId }: { runId: string }) {
  const tv = useTranslations("validation");
  const [x, setX] = useState(50);
  const obs = useAuthImage(`/api/validation-runs/${runId}/layers/observed.png`);
  const mod = useAuthImage(`/api/validation-runs/${runId}/layers/modelled.png`);
  const diff = useAuthImage(`/api/validation-runs/${runId}/layers/difference.png`);
  return (
    <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{tv("curtain")}</div>
        <div className="relative aspect-[2/1] overflow-hidden rounded-[3px] border border-line bg-bg">
          {mod && <img src={mod} alt={tv("modelled")} className="absolute inset-0 h-full w-full object-fill [image-rendering:pixelated]" />}
          {obs && <img src={obs} alt={tv("observed")} className="absolute inset-0 h-full w-full object-fill [image-rendering:pixelated]" style={{ clipPath: `inset(0 ${100 - x}% 0 0)` }} />}
          <div className="absolute inset-y-0 w-0.5 bg-accent" style={{ left: `${x}%` }} />
          <span className="absolute left-1 top-1 rounded bg-bg/80 px-1 text-[10px] font-bold">{tv("observed")}</span>
          <span className="absolute right-1 top-1 rounded bg-bg/80 px-1 text-[10px] font-bold">{tv("modelled")}</span>
        </div>
        <input type="range" min={0} max={100} value={x} onChange={(e) => setX(Number(e.target.value))} aria-label={tv("curtain")} className="w-full" />
      </div>
      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{tv("difference")}</div>
        <div className="relative aspect-[2/1] overflow-hidden rounded-[3px] border border-line bg-bg">
          {diff && <img src={diff} alt={tv("difference")} className="absolute inset-0 h-full w-full object-fill [image-rendering:pixelated]" />}
        </div>
        <div className="mt-1 flex gap-3 text-[10.5px] text-muted">
          <span><span className="mr-1 inline-block h-2 w-2 bg-[#2e90fa]" />{tv("overlap")}</span>
          <span><span className="mr-1 inline-block h-2 w-2 bg-[#faa028]" />{tv("fp")}</span>
          <span><span className="mr-1 inline-block h-2 w-2 bg-[#c846dc]" />{tv("fn")}</span>
        </div>
      </div>
    </div>
  );
}
