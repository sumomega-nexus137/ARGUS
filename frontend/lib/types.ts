// Types for ARGUS API payloads (subset used by the UI). Times named *_min are minutes relative to the
// scenario reference time (`reference_time`); ISO strings are absolute instants.

export type Locale = "kk" | "ru" | "en";
export type Names = { kk?: string | null; ru?: string | null; en?: string | null; original?: string | null };
export type AreaStatus = "NORMAL" | "WATCH" | "WARNING" | "CRITICAL";
export type RoadState = "OPEN" | "AT_RISK" | "CLOSES_IN" | "RESTRICTED" | "CLOSED";
export type WindowStatus = "SAFE" | "WINDOW_CLOSING" | "WINDOW_MISSED" | "NO_DEADLINE" | "NO_ROUTE";
export type Role = "VIEWER" | "OPERATOR" | "PLANNER" | "COMMANDER" | "ADMIN";

export interface User {
  username: string;
  full_name: string;
  role: Role;
  permissions: string[];
  preferred_language: Locale;
}

export interface Freshness {
  id: string;
  layer: string;
  provider: string;
  source: string;
  mode: string;
  status: string;
  quality: string | null;
  last_success_at: string | null;
  age_min: number | null;
  freshness: string;
  schedule_min: number | null;
  is_external: boolean;
  message: string | null;
}

export interface Gauge {
  station_id: string;
  names: Names;
  stage_cm: number | null;
  observed_at: string | null;
  age_min: number | null;
  source: string | null;
  source_type: string | null;
  verification: string | null;
  mode: string | null;
  trend_cm_h: number | null;
  forecast_peak_cm: number | null;
  forecast_peak_at_min: number | null;
  thresholds: { bankfull: number | null; watch: number | null; warning: number | null; critical: number | null };
  open_conflict: boolean;
  scenario_station?: boolean;
  provider?: string;
}

export interface ChainNode {
  type: string;
  params: Record<string, unknown>;
  severity: "info" | "warning" | "critical";
}

export interface CausalChain {
  task: string;
  outcome: string;
  nodes: ChainNode[];
  headline: ChainNode | null;
}

export interface Issue {
  type: string;
  blocking: boolean;
  params: Record<string, unknown>;
}

export interface TaskResult {
  code: string;
  template_id: string;
  site_id: string;
  resource_ids: string[];
  status: "FEASIBLE" | "AT_RISK" | "INFEASIBLE" | "DONE" | "IN_PROGRESS";
  issues: Issue[];
  origin_node: string | null;
  departure: number | null;
  arrival: number | null;
  start: number | null;
  end: number | null;
  travel_min: number | null;
  route_segments: string[];
  route_roads: string[];
  deadline: number | null;
  deadline_reason: string;
  deadline_components: Record<string, number | null>;
  latest_departure: number | null;
  latest_route_roads: string[];
  slack_min: number | null;
  vehicle_class: string;
  crew_id: string | null;
  planned_departure: number | null;
  window_status: WindowStatus | null;
}

export interface PlanEvaluation {
  status: "FEASIBLE" | "AT_RISK" | "INFEASIBLE";
  tasks: TaskResult[];
  failed: string[];
  at_risk: string[];
  as_of: number;
  member: string;
  resource_conflicts: Record<string, unknown>[];
}

export interface PlanHealth {
  plan_version_id: string;
  status: "PLAN_VALID" | "PLAN_AT_RISK";
  severity: "ok" | "warning" | "critical";
  evaluation: PlanEvaluation;
  basis_evaluation: PlanEvaluation;
  chains: CausalChain[];
  headline: { type: string; params: Record<string, unknown> } | null;
  scenario: { id: string; version: number; member: string };
  basis_scenario: { id: string; version: number; member: string };
  as_of: number;
  reference_time: string;
  next_critical_decision: { task: string; latest_departure: number; minutes: number } | null;
  data_version: number;
}

export interface AreaOverview {
  id: string;
  names: Names;
  river_names: Names;
  archetype: string;
  center: [number, number];
  bbox: [number, number, number, number];
  is_demo: boolean;
  clock_mode: string;
  now: string;
  utc_offset_min: number;
  status: AreaStatus;
  reasons: { type: string; params: Record<string, unknown> }[];
  gauges: Gauge[];
  scenario: { id: string; version: number; member: string; mode: string; reference_time: string; model_version: string };
  plan: {
    plan_version_id: string;
    plan_name: string;
    version: number;
    status: string;
    severity: string;
    headline: { type: string; params: Record<string, unknown> } | null;
    failed: string[];
    at_risk: string[];
    next_critical_decision: { task: string; latest_departure: number; minutes: number } | null;
  } | null;
  freshness: Freshness[];
  external_offline: boolean;
  data_version: number;
}

export interface AreaDetail {
  id: string;
  names: Names;
  river_names: Names;
  archetype: string;
  bbox: [number, number, number, number];
  center: [number, number];
  utc_offset_min: number;
  clock_mode: string;
  now: string;
  is_demo: boolean;
  data_version: number;
  static_version: number;
  reference_time: string;
  demo_note: string | null;
  data_profile?: "historical" | "demo";
  role?: string | null;
  assumptions?: { key: string; value: unknown; note: string; notes?: Names | null }[];
  pack?: { archive_sha256: string; run_id: number; artifact_id: number } | null;
  clock_start?: string | null;
  population_meta?: { worldpop_total_in_pack: number; allocated_to_building_cells: number; not_allocated_no_mapped_buildings: number; zones: number } | null;
  road_meta?: { segments: number; nodes: number; dropped_disconnected_segments: number; roads: number } | null;
  economic_model?: string;
  scenario_station_id?: string | null;
  attribution?: string;
}

export interface ScenarioInfo {
  id: string;
  area_id: string;
  family_id: string;
  version: number;
  name: string;
  mode: string;
  created_at: string;
  reference_time: string;
  source: string;
  provider: string;
  provider_note: string;
  frame_offsets_min: number[];
  frames: { index: number; offset_min: number; kind: "ANALYSIS" | "FORECAST" }[];
  now_min: number;
  active_member: string;
  members: { id: string; label: string; peak_stage_cm: number | null; peak_offset_h: number | null }[];
  members_order: string[];
  selection: Record<string, unknown> & {
    method?: string;
    scores?: { member: string; label: string; weighted_rmse_cm: number | null }[];
    envelope?: string[];
    open_conflicts?: string[];
  };
  uncertainty: { envelope?: string[]; description?: string };
  provenance: Record<string, unknown>;
  model_version: string;
  image_corners: [number, number][];
  parent_id: string | null;
  reason: string | null;
  parameters: Record<string, unknown>;
}

export interface RoadWindow {
  road_id: string;
  names: Names;
  road_class: string;
  state: RoadState;
  worst_segment_state: string;
  closes_at: number | null;
  closes_in_min: number | null;
  reopens_at: number | null;
  override: Record<string, unknown> | null;
  segments: { segment_id: string; state: string; closes_at: number | null; depth_m: number; override: unknown }[];
}

export interface SectorAccess {
  code: string;
  names: Names;
  population: number;
  access_lost_at: number | null;
  access_lost_in_min: number | null;
  partial_loss_at: number | null;
  isolated_now: boolean;
}

export interface FacilityAccess {
  id: string;
  type: string;
  names: Names;
  criticality: number | null;
  lon: number;
  lat: number;
  accessible_now: boolean;
  access_lost_at: number | null;
  access_lost_in_min: number | null;
  flooded_now: boolean;
  flood_at: number | null;
  flood_in_min: number | null;
}

export interface TaskWindowRow {
  code: string;
  template_id: string;
  site_id: string;
  crew: string | null;
  planned_departure: number | null;
  departure: number | null;
  latest_departure: number | null;
  deadline: number | null;
  deadline_reason: string;
  window_status: WindowStatus | null;
  slack_to_latest_min: number | null;
  plan_status: string;
  route_roads: string[];
  latest_route_roads: string[];
  end: number | null;
  issues: string[];
}

export interface AccessPayload {
  as_of: number;
  now_min: number;
  reference_time: string;
  scenario_id: string;
  member: string;
  horizon_end: number;
  roads: RoadWindow[];
  sectors: SectorAccess[];
  facilities: FacilityAccess[];
  edges: Record<string, { state: string; closes_at: number | null; depth_m: number; override: boolean }>;
  tasks: TaskWindowRow[];
  plan: { plan_version_id: string; name: string; version: number; status: string } | null;
  next_critical_decision: { task: string; latest_departure: number; minutes: number } | null;
  mode: string;
}

export interface MoneyRange {
  low: number;
  high: number;
  currency: string;
}

export interface ImpactFrame {
  t_min: number;
  buildings: {
    total: number;
    affected: number;
    by_depth_class: { min_m: number; max_m: number | null; buildings: number }[];
    by_use: Record<string, { buildings: number; floor_area_m2: number }>;
  };
  population: { total: number; exposed: number; vulnerable_exposed: number | null; aggregated: boolean; method?: string; zones_without_buildings_exposed?: number };
  facilities: { id: string; type: string; names: Names; criticality: number | null; depth_m: number; exposed: boolean; lon: number; lat: number }[];
  facilities_exposed: number;
  roads: { km_flooded: number; km_closed: number; km_restricted: number; segments_closed: number };
  sectors: Record<string, { names: Names; buildings_affected: number; population_exposed: number }>;
  economic: { asset_exposure: MoneyRange | null; expected_damage: MoneyRange | null; status: string; floor_area_exposed_m2?: number; damage_weighted_floor_area_m2?: number };
  max_depth_m: number;
  kind: "ANALYSIS" | "FORECAST";
  mode: string;
  calculation?: {
    rows: {
      use: string;
      buildings: number;
      floor_area_m2: number;
      unit_value_kzt_m2: [number, number];
      exposure: MoneyRange;
      mean_damage_fraction: number;
      expected_damage: MoneyRange;
    }[];
    assumptions: Record<string, unknown> & {
      methodology: Record<string, unknown> & { limitations: string[] };
      damage_curve: [number, number][];
      unit_value_kzt_m2: Record<string, [number, number]>;
    };
  };
}

export interface ImpactTimeline {
  frames: {
    t_min: number;
    buildings_affected: number;
    population_exposed: number;
    facilities_exposed: number;
    roads_km_closed: number;
    asset_exposure: MoneyRange | null;
    expected_damage: MoneyRange | null;
    floor_area_exposed_m2?: number;
    max_depth_m: number;
  }[];
  buildings: { ids: string[]; depth_cm: number[][] };
  frame_offsets_min: number[];
}

export interface AccessTimeline {
  frame_offsets_min: number[];
  states: Record<string, number[]>;
  road_closures: Record<string, number>;
  sector_access_loss: Record<string, number | null>;
  now_min: number;
}

export interface PlanTaskRow {
  id: string;
  code: string;
  template_id: string;
  site_id: string;
  resource_ids: string[];
  planned_departure: string | null;
  dependencies: string[];
  notes: string | null;
  status: string;
  status_updated_at: string | null;
  status_updated_by: string | null;
  actual_departure: string | null;
  actual_start: string | null;
  completed_at: string | null;
  sort_order: number;
  rationale: Record<string, unknown>;
}

export interface PlanVersion {
  id: string;
  plan_id: string;
  plan_name: string;
  area_id: string;
  version: number;
  status: "DRAFT" | "REVIEWED" | "APPROVED" | "ACTIVE" | "SUPERSEDED" | "REJECTED";
  origin: "HUMAN" | "OPTIMIZER" | "RECOMPUTE";
  basis_scenario_id: string | null;
  policy: string | null;
  weights: Record<string, number>;
  constraints: { kind: string; resource_id?: string | null; sector?: string | null; task_code?: string | null; note?: string | null; author?: string | null }[];
  change_summary: Record<string, unknown>;
  parent_version_id: string | null;
  created_by: string | null;
  created_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  activated_at: string | null;
  tasks?: PlanTaskRow[];
}

export interface ResourceRow {
  id: string;
  resource_type: string;
  subtype: string;
  capacity: number | null;
  capacity_unit: string | null;
  base_id: string | null;
  names: Names;
  status: string;
  delay_min: number;
  note: string | null;
  updated_by: string | null;
  updated_at: string | null;
}

export interface ActionTemplate {
  id: string;
  action_type: string;
  names: Names;
  description: Record<string, string>;
  requirements: {
    crew?: { types: string[]; count: number };
    vehicle?: { types: string[]; count: number };
    pumps?: number;
    equipment?: Record<string, number>;
  };
  setup_min: number;
  execution_min: number;
  safety_buffer_min: number;
  equipment_release: string;
  site_kinds: string[];
  constraints: Record<string, unknown>;
  approved_by: string | null;
  version: number;
}

export interface SiteRow {
  id: string;
  kind: string;
  names: Names;
  sector_id: string | null;
  protects: { sector_ids?: string[]; facility_ids?: string[]; road_ids?: string[] };
  work_depth_limit_m: number;
  lon: number;
  lat: number;
}

export type Feature = { type: "Feature"; geometry: { type: string; coordinates: unknown }; properties: Record<string, unknown> };
export type FeatureCollection = { type: "FeatureCollection"; features: Feature[]; demo?: boolean };

export interface StressScenario {
  id: string;
  kind: string;
  params: Record<string, unknown>;
  member: string;
  feasible: boolean;
  status: "FEASIBLE" | "AT_RISK" | "INFEASIBLE";
  failed_tasks: string[];
  at_risk_tasks: string[];
  task_status: Record<string, string>;
  chains: CausalChain[];
  min_slack: number | null;
}

export interface TaskCriticality {
  task: string;
  failures: number;
  at_risk: number;
  failure_share: number;
}

export interface StressResult {
  id: string;
  created_at: string;
  n_scenarios: number;
  n_feasible: number;
  robustness: number;
  baseline_status: string;
  scenarios: StressScenario[];
  task_criticality: TaskCriticality[];
  duration_s: number;
  member: string;
  scenario_id: string;
  as_of: number;
  reference_time: string;
}

export interface ValueComponents {
  life: number;
  infra: number;
  economic: number;
  threatened_facilities: string[];
  protected_sectors: string[];
  exposed_population: number;
  expected_damage_mid: number;
}

export interface AltTask {
  code: string;
  template_id: string;
  site_id: string;
  crew: string | null;
  vehicle: string | null;
  pumps: string[];
  equipment: string[];
  departure: number | null;
  arrival: number | null;
  end: number | null;
  status: string;
  deadline: number | null;
  deadline_reason: string;
  latest_departure: number | null;
  route_roads: string[];
  route_segments: string[];
  prev_task: string | null;
  why?: {
    task: { value: number; rank: number; of: number; components: ValueComponents; weights: Record<string, number>; benefit_share: Record<string, number> };
    resource: {
      crew: string | null;
      qualified_types: string[];
      alternatives: { crew: string; subtype: string; earliest_arrival: number | null; assigned_to: string | null }[];
      vehicle: string | null;
      vehicle_types: string[];
      pumps: number;
    };
    now: { latest_departure: number | null; route_closures: { road: string; closes_at: number | null }[]; deadline: number | null; deadline_reason: string; slack_min: number | null };
    if_delayed: { tolerance_min: number | null; consequence: { delay_min: number; status: string; issues: string[]; other_tasks_affected: string[] } | null };
  };
}

export interface Alternative {
  id: string;
  label: string;
  tasks: AltTask[];
  evaluation: PlanEvaluation;
  metrics: { tasks_selected: number; tasks_feasible: number; value_total: number; life: number; infra: number; economic: number; high_priority_tasks: string[]; pumps_used: number; crews_used: number; min_slack: number | null };
  robustness: { n_scenarios: number; n_feasible: number; robustness: number; task_criticality: TaskCriticality[] } | null;
  excluded_candidates: { code: string; template_id: string; site_id: string; value: number; reason: string }[];
  diff_vs_human: { added: string[]; removed: string[]; reassigned: { task: string; from: string; to: string }[]; retimed: { task: string; from: number | null; to: number | null }[] };
  solver: { status: string; solve_time_s: number; objective: number };
}

export interface OptimizationResult {
  id: string;
  created_at: string;
  status: string;
  policy: string;
  weights: Record<string, number>;
  as_of: number;
  member: string;
  scenario_id: string;
  alternatives: Alternative[];
  candidates: { code: string; template_id: string; site_id: string; value: number; deadline: number | null; deadline_reason: string; origin: string }[];
  resources: Record<string, number>;
  fixed_tasks: string[];
  duration_s: number;
  feasible: boolean;
  reference_time: string;
  what_if_unavailable: string[];
}

export interface GapOption {
  resource_type: string;
  subtype: string;
  count: number;
  tasks_before: number;
  tasks_after: number;
  delta_tasks: number;
  value_before: number;
  value_after: number;
  delta_value: number;
  tasks_added: string[];
  tasks_removed: string[];
  high_priority_added: string[];
  min_slack_gain_min: number;
  statement: { key: string; params: Record<string, unknown> };
}

export interface GapResult {
  id: string;
  created_at: string;
  status: string;
  feasible: boolean;
  policy: string;
  weights: Record<string, number>;
  baseline: { tasks: string[]; value_total: number; min_slack: number | null };
  options: GapOption[];
  duration_s: number;
}
