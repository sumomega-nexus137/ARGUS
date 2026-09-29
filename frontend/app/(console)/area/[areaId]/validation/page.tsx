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

interface Run {
  id: string; dataset_id: string; kind: string; status: string; created_at: string; created_by: string;
  metrics: { iou: number; precision: number; recall: number; f1: number; true_overlap_km2: number; false_positive_km2: number; false_negative_km2: number; observed_km2: number; modelled_km2: number };
  result: { warning?: string };
}
interface ValidationPayload {
  datasets: { id: string; name: Names; event: string; observed_source: string; status: string; path: string; kind: string }[];
  runs: Run[];
}
interface AAR {
  plan_versions: { id: string; plan: string; version: number; status: string; origin: string; approved_by: string | null }[];
  delayed_tasks: { task: string; delay_min?: number }[];
  missed_windows: { task: string; deadline: number | null; deadline_reason: string; issues: string[] }[];
  route_failures: { task: string }[];
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

      {run ? (
        <Panel title={`${tv("metrics")} · ${run.dataset_id} · ${dateTime(run.created_at, area.utc_offset_min)}`}>
          {run.kind === "SYNTHETIC_SELF_TEST" && <InlineNote tone="sim" className="mb-2">{tv("syntheticWarning")}</InlineNote>}
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
            <AarList title={tv("missed")} items={aar.data.missed_windows.map((m) => `${m.task} · ${fmt(m.deadline)} · ${m.issues.join(", ")}`)} none={tv("none")} tone="crit" />
            <AarList title={tv("delayed")} items={aar.data.delayed_tasks.map((d) => `${d.task}${d.delay_min ? ` ${tv("delayMin", { n: d.delay_min })}` : ""}`)} none={tv("none")} />
            <AarList title={tv("routeFailures")} items={aar.data.route_failures.map((r) => r.task)} none={tv("none")} />
            <AarList title={tv("unavailableResources")} items={aar.data.unavailable_resources.map((r) => `${r.id || r.resource} ${r.status || ""}`)} none={tv("none")} />
            <AarList title={tv("versions")} items={aar.data.plan_versions.map((p) => `${p.plan} v${p.version} · ${p.status} · ${p.origin}${p.approved_by ? ` · ${p.approved_by}` : ""}`)} none={tv("none")} />
            <AarList title={tv("modelErrors")} items={aar.data.forecast_errors.map((e) => `${e.station_id} v${e.version} ${e.member}: ${tv("bias")} ${e.bias_cm ?? "—"} · ${tv("mae")} ${e.mae_cm ?? "—"} (n=${e.n})`)} none={tv("none")} />
          </div>
        ) : <Loading />}
      </Panel>
    </div>
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
