"use client";

// Server-state hooks (TanStack Query). Query keys include the area's data version where results depend
// on it, so every audited change triggers recomputation of dependent views.
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type {
  AccessPayload,
  AccessTimeline,
  ActionTemplate,
  AreaDetail,
  AreaOverview,
  FeatureCollection,
  ImpactFrame,
  ImpactTimeline,
  PlanHealth,
  PlanVersion,
  ResourceRow,
  ScenarioInfo,
  SiteRow,
} from "./types";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ status: string; database: string; external_offline: boolean; demo_mode: boolean }>("/api/system/health"),
    refetchInterval: 20_000,
    retry: false,
  });
}

export function useAreas() {
  return useQuery({ queryKey: ["areas"], queryFn: () => api<AreaOverview[]>("/api/areas"), refetchInterval: 60_000 });
}

export function useArea(areaId: string) {
  return useQuery({ queryKey: ["area", areaId], queryFn: () => api<AreaDetail>(`/api/areas/${areaId}`), refetchInterval: 30_000, enabled: !!areaId && areaId !== "__none__" });
}

export function useDataVersion(areaId: string): number | undefined {
  return useArea(areaId).data?.data_version;
}

export function useScenario(areaId: string) {
  const v = useDataVersion(areaId);
  return useQuery({ queryKey: ["scenario", areaId, v], queryFn: () => api<ScenarioInfo>(`/api/areas/${areaId}/scenario`), enabled: v !== undefined });
}

export function useLayer(areaId: string, layer: string, staticVersion?: number) {
  return useQuery({
    queryKey: ["layer", areaId, layer, staticVersion],
    queryFn: () => api<FeatureCollection>(`/api/areas/${areaId}/layers/${layer}`),
    staleTime: 10 * 60_000,
    enabled: staticVersion !== undefined,
  });
}

export function useAccess(areaId: string, t: number | null) {
  const v = useDataVersion(areaId);
  return useQuery({
    queryKey: ["access", areaId, v, t],
    queryFn: () => api<AccessPayload>(`/api/areas/${areaId}/access${t === null ? "" : `?t=${t}`}`),
    enabled: v !== undefined,
  });
}

export function useAccessTimeline(areaId: string) {
  const v = useDataVersion(areaId);
  return useQuery({ queryKey: ["accessTl", areaId, v], queryFn: () => api<AccessTimeline>(`/api/areas/${areaId}/access/timeline`), enabled: v !== undefined });
}

export function useImpactTimeline(areaId: string) {
  const v = useDataVersion(areaId);
  return useQuery({ queryKey: ["impactTl", areaId, v], queryFn: () => api<ImpactTimeline>(`/api/areas/${areaId}/impact/timeline`), enabled: v !== undefined });
}

export function useImpact(areaId: string, t: number | null, calc = false) {
  const v = useDataVersion(areaId);
  return useQuery({
    queryKey: ["impact", areaId, v, t, calc],
    queryFn: () => api<ImpactFrame>(`/api/areas/${areaId}/impact?${t === null ? "" : `t=${t}&`}include_calculation=${calc}`),
    enabled: v !== undefined,
  });
}

export function useOperations(areaId: string) {
  const v = useDataVersion(areaId);
  return useQuery({
    queryKey: ["ops", areaId, v],
    queryFn: () => api<{
      active_version: PlanVersion | null;
      health: PlanHealth | null;
      pending_versions: PlanVersion[];
      resources: { id: string; type: string; subtype: string; base: string | null; status: string; delay_min: number; assigned_task?: string | null; note: string | null }[];
      events: { id: number; ts: string; op_time: string | null; username: string; role: string; action: string; entity_id: string | null; summary: string }[];
      last_pipeline: { id: string; trigger: string; outcome: string; steps: { step: string; status: string; ms: number; detail: Record<string, unknown> }[]; started_at: string } | null;
      data_version: number;
    }>(`/api/areas/${areaId}/operations`),
    enabled: v !== undefined,
  });
}

export function useActions(areaId: string) {
  return useQuery({ queryKey: ["actions", areaId], queryFn: () => api<ActionTemplate[]>(`/api/actions?area_id=${areaId}`), staleTime: 5 * 60_000 });
}

export function useSites(areaId: string) {
  return useQuery({ queryKey: ["sites", areaId], queryFn: () => api<SiteRow[]>(`/api/areas/${areaId}/sites`), staleTime: 5 * 60_000 });
}

export function useResources(areaId: string) {
  const v = useDataVersion(areaId);
  return useQuery({ queryKey: ["resources", areaId, v], queryFn: () => api<ResourceRow[]>(`/api/areas/${areaId}/resources`), enabled: v !== undefined });
}

export function usePlans(areaId: string) {
  const v = useDataVersion(areaId);
  return useQuery({
    queryKey: ["plans", areaId, v],
    queryFn: () => api<{ id: string; name: string; description: string | null; versions: PlanVersion[] }[]>(`/api/areas/${areaId}/plans`),
    enabled: v !== undefined,
  });
}

export function usePlanVersion(versionId: string | null, dataVersion?: number) {
  return useQuery({
    queryKey: ["pv", versionId, dataVersion],
    queryFn: () => api<PlanVersion>(`/api/plan-versions/${versionId}`),
    enabled: !!versionId,
  });
}

export function usePlanHealth(versionId: string | null, dataVersion?: number) {
  return useQuery({
    queryKey: ["pvHealth", versionId, dataVersion],
    queryFn: () => api<PlanHealth>(`/api/plan-versions/${versionId}/health`),
    enabled: !!versionId && dataVersion !== undefined,
  });
}

/** Invalidate everything that depends on an area after a mutation (recomputation is server-side). */
export function useInvalidateArea() {
  const qc = useQueryClient();
  return (areaId: string) => {
    qc.invalidateQueries({ queryKey: ["area", areaId] });
    qc.invalidateQueries({ queryKey: ["areas"] });
    for (const k of ["scenario", "access", "accessTl", "impactTl", "impact", "ops", "resources", "plans", "hydro", "obs", "conflicts", "roadEvents", "freshness", "audit", "validation", "aar", "report"]) {
      qc.invalidateQueries({ queryKey: [k, areaId] });
    }
    qc.invalidateQueries({ queryKey: ["pv"] });
    qc.invalidateQueries({ queryKey: ["pvHealth"] });
  };
}
