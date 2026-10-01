"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { Badge, ErrorState, InlineNote, Loading, Panel } from "@/components/ui/primitives";
import { post } from "@/lib/api";
import { num, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import type { Names } from "@/lib/types";

interface BN {
  id: string;
  kind: string;
  names: Names;
  segment_ids: string[];
  lon: number;
  lat: number;
  notes: string | null;
  notes_i18n?: Names | null;
  expected_closure_at: number | null;
  affected_sectors: { code: string; names: Names; isolated: boolean; was_isolated: boolean; population: number; access_lost_at: number | null; baseline_access_lost_at: number | null; travel_increase_min: number | null }[];
  affected_facilities: { id: string; names: Names; type: string; criticality: number; accessible: boolean; single_point_of_failure: boolean; access_lost_at: number | null; baseline_access_lost_at: number | null; travel_increase_min: number | null }[];
  newly_isolated_population: number;
  single_points_of_failure: string[];
  criticality_score: number;
}

export default function BottlenecksPage() {
  const { areaId, area, t, fmt, setOverlays, clearOverlays } = useAreaCtx();
  const tb = useTranslations("bottleneck");
  const tf = useTranslations("facilityType");
  const tm = useTranslations("methodology");
  const { locale } = useLocale();
  const [sel, setSel] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["bottlenecks", areaId, area?.data_version, t],
    queryFn: () => post<{ bottlenecks: BN[]; structural_candidates: { segment_id: string; road_id: string; betweenness: number; cut_edge: boolean }[]; methodology: string }>(
      `/api/areas/${areaId}/bottlenecks/analyze`, { bottleneck_ids: [], as_of_min: t }),
    enabled: !!area && t !== null,
  });
  useEffect(() => () => clearOverlays(), [clearOverlays]);
  useEffect(() => {
    const b = q.data?.bottlenecks.find((x) => x.id === sel);
    setOverlays({
      highlightSegments: b ? b.segment_ids : [],
      points: (q.data?.bottlenecks || []).filter((x) => !sel || x.id === sel).map((x) => ({
        id: x.id, lon: x.lon, lat: x.lat, label: `${x.criticality_score}`, sub: pickName(x.names, locale), tone: x.criticality_score >= 10 ? "crit" : x.criticality_score > 0 ? "warn" : "muted",
      })),
      focus: b ? { lon: b.lon, lat: b.lat } : null,
    });
  }, [sel, q.data, setOverlays, locale]);

  return (
    <div className="space-y-3 p-3">
      <ScreenHeader screen="bottlenecks" right={<Badge tone="info">{tb("whatIf", { time: fmt(t) })}</Badge>} />
      <InlineNote tone="sim">{tb("noHydroClaim")}</InlineNote>
      {q.isLoading && <Loading />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.bottlenecks.map((b) => (
        <button key={b.id} onClick={() => setSel(sel === b.id ? null : b.id)} className={clsx("block w-full rounded-[4px] border p-3 text-left", sel === b.id ? "border-accent/60 bg-accent/5" : "border-line bg-panel hover:border-line-2")}>
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-sm font-bold">{pickName(b.names, locale)}</div>
              <div className="text-[11px] text-muted">{tb(`kind.${b.kind}`)} · {b.segment_ids.join(", ")}{b.expected_closure_at !== null ? ` · ${tb("expectedClosure")} ${fmt(b.expected_closure_at)}` : ""}</div>
            </div>
            <div className="text-right">
              <div className="text-[9.5px] font-bold uppercase tracking-wider text-muted">{tb("score")}</div>
              <div className={clsx("tabular text-xl font-extrabold", b.criticality_score >= 10 ? "text-crit" : b.criticality_score > 0 ? "text-warn" : "text-ok")}>{num(b.criticality_score, 1, locale)}</div>
            </div>
          </div>
          {b.affected_sectors.length === 0 && b.affected_facilities.length === 0 ? (
            <div className="mt-1 text-xs text-ok">{tb("noConsequence")}</div>
          ) : (
            <div className="mt-2 grid grid-cols-1 gap-2 text-xs xl:grid-cols-2">
              <div>
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">{tb("affectedSectors")}</div>
                {b.affected_sectors.map((s) => (
                  <div key={s.code} className="flex justify-between gap-2 border-t border-line/60 py-0.5">
                    <span>{pickName(s.names, locale)}</span>
                    <span className="text-right text-ink-2">
                      {s.isolated && !s.was_isolated && <Badge tone="crit">{tb("isolated")}</Badge>}
                      {s.travel_increase_min !== null && s.travel_increase_min > 0 && ` ${tb("travelIncrease", { min: num(s.travel_increase_min, 0, locale) })}`}
                    </span>
                  </div>
                ))}
                {b.newly_isolated_population > 0 && <div className="mt-1 font-semibold text-crit">{tb("newlyIsolated")}: {num(b.newly_isolated_population, 0, locale)}</div>}
              </div>
              <div>
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">{tb("affectedFacilities")}</div>
                {b.affected_facilities.map((f) => (
                  <div key={f.id} className="flex justify-between gap-2 border-t border-line/60 py-0.5">
                    <span className="min-w-0 truncate">{pickName(f.names, locale)} <span className="text-muted">· {tf.has(f.type) ? tf(f.type) : f.type}</span></span>
                    <span className="shrink-0 text-right">
                      {f.single_point_of_failure && <Badge tone="crit">{tb("spof")}</Badge>}
                      {f.travel_increase_min !== null && f.travel_increase_min > 0 && <span className="text-ink-2"> {tb("travelIncrease", { min: num(f.travel_increase_min, 0, locale) })}</span>}
                      {f.access_lost_at !== null && f.baseline_access_lost_at !== f.access_lost_at && <span className="block text-[10.5px] text-warn">{tb("accessLost", { from: fmt(f.baseline_access_lost_at), to: fmt(f.access_lost_at) })}</span>}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {b.notes && <p className="mt-1 text-[10.5px] text-muted">{b.notes_i18n ? pickName(b.notes_i18n, locale) : b.notes}</p>}
        </button>
      ))}
      {q.data && (
        <Panel title={tb("structural")}>
          <table className="w-full text-xs">
            <tbody>
              {q.data.structural_candidates.map((c) => (
                <tr key={c.segment_id} className="border-t border-line/60">
                  <td className="py-1 font-mono">{c.road_id} · {c.segment_id}</td>
                  <td className="tabular text-right">{tb("betweenness")} {num(c.betweenness, 3, locale)}</td>
                  <td className="text-right">{c.cut_edge && <Badge tone="warn">{tb("cutEdge")}</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[10.5px] leading-snug text-muted">{tm("bottleneck")}</p>
        </Panel>
      )}
    </div>
  );
}
