"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { relHHMM } from "@/lib/format";
import { useAccess, useAccessTimeline, useArea, useImpactTimeline, useLayer, useScenario } from "@/lib/queries";
import { useUi } from "@/lib/store";
import type { AccessPayload, AccessTimeline, AreaDetail, FeatureCollection, ImpactTimeline, ScenarioInfo } from "@/lib/types";

export interface RouteOverlay {
  id: string;
  segments: string[];
  color: string;
  dashed?: boolean;
  width?: number;
}

export interface PointOverlay {
  id: string;
  lon: number;
  lat: number;
  label: string;
  sub?: string;
  tone: "ok" | "watch" | "warn" | "crit" | "info" | "sim" | "muted";
}

export interface MapOverlays {
  routes: RouteOverlay[];
  points: PointOverlay[];
  highlightSegments: string[];
  focus?: { lon: number; lat: number; zoom?: number } | null;
}

const EMPTY: MapOverlays = { routes: [], points: [], highlightSegments: [] };

interface Ctx {
  areaId: string;
  area?: AreaDetail;
  scenario?: ScenarioInfo;
  layers: Record<string, FeatureCollection | undefined>;
  accessTl?: AccessTimeline;
  impactTl?: ImpactTimeline;
  access?: AccessPayload;
  accessLoading: boolean;
  /** effective timeline time (minutes rel. reference): cursor or NOW */
  t: number | null;
  nowMin: number | null;
  frameIndex: number;
  overlays: MapOverlays;
  setOverlays: (o: Partial<MapOverlays>) => void;
  clearOverlays: () => void;
  fmt: (m: number | null | undefined) => string;
  segmentCoords: (segmentIds: string[]) => [number, number][][];
}

const AreaCtx = createContext<Ctx | null>(null);

export function useAreaCtx(): Ctx {
  const c = useContext(AreaCtx);
  if (!c) throw new Error("useAreaCtx outside AreaProvider");
  return c;
}

const LAYERS = ["roads", "buildings", "facilities", "task_sites", "bases", "bridges", "bottlenecks", "sectors", "river", "stations"];

export function AreaProvider({ areaId, children }: { areaId: string; children: ReactNode }) {
  const area = useArea(areaId);
  const scenario = useScenario(areaId);
  const sv = area.data?.static_version;
  const layerQs = {
    roads: useLayer(areaId, "roads", sv),
    buildings: useLayer(areaId, "buildings", sv),
    facilities: useLayer(areaId, "facilities", sv),
    task_sites: useLayer(areaId, "task_sites", sv),
    bases: useLayer(areaId, "bases", sv),
    bridges: useLayer(areaId, "bridges", sv),
    bottlenecks: useLayer(areaId, "bottlenecks", sv),
    sectors: useLayer(areaId, "sectors", sv),
    river: useLayer(areaId, "river", sv),
    stations: useLayer(areaId, "stations", sv),
  } as const;
  const accessTl = useAccessTimeline(areaId);
  const impactTl = useImpactTimeline(areaId);
  const cursor = useUi((s) => s.cursor);
  const nowMin = scenario.data?.now_min ?? null;
  const t = cursor ?? nowMin;
  const access = useAccess(areaId, cursor);
  const [overlays, setOv] = useState<MapOverlays>(EMPTY);

  const layers = useMemo(() => {
    const out: Record<string, FeatureCollection | undefined> = {};
    for (const k of LAYERS) out[k] = layerQs[k as keyof typeof layerQs].data;
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [LAYERS.map((k) => layerQs[k as keyof typeof layerQs].dataUpdatedAt).join(",")]);

  const frames = scenario.data?.frame_offsets_min;
  const frameIndex = useMemo(() => {
    if (!frames || t === null) return 0;
    let best = 0;
    for (let i = 0; i < frames.length; i++) if (Math.abs(frames[i] - t) < Math.abs(frames[best] - t)) best = i;
    return best;
  }, [frames, t]);

  const segIndex = useMemo(() => {
    const m = new Map<string, [number, number][]>();
    layers.roads?.features.forEach((f) => m.set(String(f.properties.id), f.geometry.coordinates as [number, number][]));
    return m;
  }, [layers.roads]);

  const segmentCoords = useCallback((ids: string[]) => ids.map((id) => segIndex.get(id)).filter(Boolean) as [number, number][][], [segIndex]);
  const setOverlays = useCallback((o: Partial<MapOverlays>) => setOv((prev) => ({ ...prev, ...o })), []);
  const clearOverlays = useCallback(() => setOv(EMPTY), []);
  const fmt = useCallback(
    (m: number | null | undefined) => relHHMM(scenario.data?.reference_time, m, area.data?.utc_offset_min ?? 300),
    [scenario.data?.reference_time, area.data?.utc_offset_min],
  );

  const value: Ctx = {
    areaId, area: area.data, scenario: scenario.data, layers, accessTl: accessTl.data, impactTl: impactTl.data,
    access: access.data, accessLoading: access.isFetching, t, nowMin, frameIndex, overlays, setOverlays, clearOverlays, fmt,
    segmentCoords,
  };
  return <AreaCtx.Provider value={value}>{children}</AreaCtx.Provider>;
}
