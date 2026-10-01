"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { Badge, Button, InlineNote, Loading, Panel } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { num } from "@/lib/format";

interface Row { [k: string]: string }
interface History {
  available: boolean;
  events: Row[];
  hydrology: Row[];
  event_peak: Row[];
  glofas: { rows: Row[]; source: string; quality: string; caveat: string; returned_coordinate?: { lat: number; lon: number } };
  weather: { rows: Row[]; source: string; quality: string };
  satellite?: { flood_item: string; flood_datetime: string; reference_item: string; reference_datetime: string; flood_cloud_cover_percent: number; reason: string };
  scenario_note?: string;
  scenario_limitations?: string[];
}

/** Tiny bar/line chart (SVG) for daily context series; values drawn as-is with their unit. */
function DailyChart({ rows, field, color, unit }: { rows: Row[]; field: string; color: string; unit: string }) {
  const tc = useTranslations("history");
  const vals = rows.map((r) => Number(r[field])).filter((v) => Number.isFinite(v));
  if (!vals.length) return null;
  const W = 380, H = 70, max = Math.max(...vals, 0.001);
  const bw = W / rows.length;
  return (
    <svg viewBox={`0 0 ${W} ${H + 12}`} className="w-full" role="img" aria-label={field}>
      {rows.map((r, i) => {
        const v = Number(r[field]);
        if (!Number.isFinite(v)) return null;
        const h = (v / max) * H;
        return <rect key={i} x={i * bw + 0.5} y={H - h} width={Math.max(1, bw - 1)} height={h} fill={color} opacity={0.75}><title>{`${r.date}: ${v} ${unit}`}</title></rect>;
      })}
      <text x={0} y={H + 10} fontSize={8} fill="#738396">{rows[0]?.date}</text>
      <text x={W} y={H + 10} fontSize={8} fill="#738396" textAnchor="end">{rows[rows.length - 1]?.date}</text>
      <text x={W} y={9} fontSize={8} fill="#738396" textAnchor="end">{tc("max")} {num(max, 2)} {unit}</text>
    </svg>
  );
}

export function HistoryPanel({ areaId }: { areaId: string }) {
  const th = useTranslations("history");
  const q = useQuery({ queryKey: ["history", areaId], queryFn: () => api<History>(`/api/areas/${areaId}/history`), staleTime: 3_600_000 });
  if (q.isLoading) return <Loading />;
  if (!q.data?.available) return null;
  const h = q.data;
  return (
    <Panel title={th("title")} right={<Badge tone="info">{th("historical")}</Badge>}>
      <div className="space-y-3 text-[11.5px]">
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{th("chronology")}</div>
          <ul className="space-y-1">
            {h.events.map((e, i) => (
              <li key={i} className="border-l-2 border-accent/40 pl-2">
                <span className="tabular font-semibold">{(e.timestamp_local || e.event_time || "").replace("T", " ").slice(0, 16)}</span>
                <span className="ml-1 text-muted">· {e.event_type}</span>
                <div className="text-ink-2">{e.description}</div>
                {e.source_url && <a className="text-[10px] text-accent underline" href={e.source_url} target="_blank" rel="noreferrer">{th("source")}</a>}
              </li>
            ))}
          </ul>
        </div>
        {h.event_peak.length > 0 && (
          <InlineNote tone="info">{h.event_peak.map((p) => `${p.event_period}: ${p.value} ${p.unit} — ${p.notes}`).join(" ")}</InlineNote>
        )}
        {h.satellite && (
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{th("satellite")}</div>
            <p>{th("satelliteText", { flood: h.satellite.flood_item, ref: h.satellite.reference_item, cloud: num(h.satellite.flood_cloud_cover_percent, 1) })}</p>
            <p className="text-[10.5px] text-muted">{th("noSentinel1")}</p>
          </div>
        )}
        {h.glofas.rows.length > 0 && (
          <div>
            <div className="mb-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-muted">
              <span>{th("glofas")}</span><Badge tone="muted">{th("globalModel")}</Badge>
            </div>
            <DailyChart rows={h.glofas.rows} field="river_discharge" color="#3fb3ff" unit="m³/s" />
            <p className="text-[10px] text-muted">{th("glofasCaveat")}</p>
          </div>
        )}
        {h.weather.rows.length > 0 && (
          <div>
            <div className="mb-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-muted">
              <span>{th("weather")}</span><Badge tone="muted">{th("reanalysis")}</Badge>
            </div>
            <DailyChart rows={h.weather.rows} field="temperature_2m_max" color="#f59e2b" unit="°C" />
            <DailyChart rows={h.weather.rows} field="precipitation_sum" color="#7aa2c7" unit="mm" />
          </div>
        )}
      </div>
    </Panel>
  );
}

interface LiveFeed {
  kind: string; mode: string; status: string; source: string; fetched_at: string | null; age_min: number | null; message: string | null;
  caveats: string[]; returned_coordinate?: { lat: number; lon: number } | null;
  data: { rows: Row[]; unit?: string; snow_depth_m_latest?: number | null } | null;
}

export function LiveContextPanel({ areaId }: { areaId: string }) {
  const tl = useTranslations("live");
  const tf = useTranslations("mode");
  const qc = useQueryClient();
  const [refresh, setRefresh] = useState(false);
  const q = useQuery({
    queryKey: ["liveContext", areaId, refresh],
    queryFn: () => api<{ glofas: LiveFeed; weather: LiveFeed }>(`/api/areas/${areaId}/context/live${refresh ? "?refresh=true" : ""}`),
    staleTime: 300_000,
  });
  const tone = (m: string) => (m === "LIVE" ? "live" : m === "CACHED" ? "cached" : m === "STALE" ? "stale" : m === "OFFLINE" ? "offline" : "muted") as "live";
  return (
    <Panel title={tl("title")} right={<Button size="sm" icon={RefreshCw} busy={q.isFetching} onClick={() => { setRefresh(true); qc.invalidateQueries({ queryKey: ["liveContext", areaId] }); }}>{tl("refresh")}</Button>}>
      <InlineNote tone="info">{tl("note")}</InlineNote>
      {q.isLoading && <Loading />}
      {q.data && (["glofas", "weather"] as const).map((k) => {
        const f = q.data[k];
        return (
          <div key={k} className="mt-2 rounded-[3px] border border-line p-2 text-[11px]">
            <div className="flex flex-wrap items-center justify-between gap-1">
              <span className="font-semibold">{f.source}</span>
              <span className="flex items-center gap-1">
                <Badge tone={tone(f.mode)}>{tf.has(f.mode) ? tf(f.mode) : f.mode}</Badge>
                <Badge tone="muted">{tl("globalModel")}</Badge>
              </span>
            </div>
            <div className="mt-0.5 text-muted">
              {f.fetched_at ? `${tl("dataAge")}: ${tl("minutes", { n: f.age_min !== null ? num(f.age_min, 0) : "—" })} · ${tl("fetched")} ${f.fetched_at.replace("T", " ").slice(0, 16)} UTC` : tl("noData")}
              {f.message && ` · ${f.message}`}
            </div>
            {f.data?.rows?.length ? <DailyChart rows={f.data.rows} field={k === "glofas" ? "river_discharge" : "precipitation_sum"} color={k === "glofas" ? "#3fb3ff" : "#7aa2c7"} unit={k === "glofas" ? "m³/s" : "mm"} /> : null}
          </div>
        );
      })}
    </Panel>
  );
}

export function AssumptionsPanel({ assumptions, limitations, note }: { assumptions?: { key: string; note: string }[]; limitations?: string[]; note?: string | null }) {
  const ta = useTranslations("provenance");
  if (!assumptions?.length && !limitations?.length) return null;
  return (
    <Panel title={ta("title")}>
      {note && <p className="mb-2 text-[11px] text-ink-2">{note}</p>}
      {limitations && limitations.length > 0 && (
        <>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{ta("limitations")}</div>
          <ul className="mb-2 list-disc space-y-0.5 pl-4 text-[11px] text-ink-2">{limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
        </>
      )}
      {assumptions && assumptions.length > 0 && (
        <>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{ta("assumptions")}</div>
          <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-ink-2">{assumptions.map((a) => <li key={a.key}>{a.note}</li>)}</ul>
        </>
      )}
    </Panel>
  );
}
