# Methodology and limitations

ARGUS is a decision-support tool. Every number it shows is computed from the data it holds, with the
assumptions listed here. In the bundled demo **all inputs are synthetic (DEMO / SIMULATION)**.

## 1. Scenario Engine

* A scenario is an **ensemble** of members (demo: M1–M6, ordered by peak stage) with gauge stage series
  and flood-depth frames from `-6 h` (analysis) to the forecast horizon.
* **Demo surrogate (not hydrodynamics):** depth = stage-dependent relative water level − height above
  nearest drainage (HAND), propagated with a priority-flood *onset* grid so low areas connected to the
  river fill first. It is labelled SIMULATION everywhere. Real surfaces enter through the precomputed
  raster manifest (see DATA_CONTRACTS) produced by an external hydrodynamic pipeline.
* **Observation conditioning:** for each member, weighted RMSE between its gauge series and
  authoritative observations in the last hours; weight = authority rank × recency. The best member
  becomes active; the members within `max(3 cm, 0.75 × best)` form the uncertainty envelope. A change
  of member creates a **new scenario version** with the reason recorded.
* **Authority hierarchy:** verified field (60) > hydropost (50) > unverified field (45) > official
  forecast (40) > satellite (30) > global model (20) > simulation (10). Two observations of the same
  station within 30 min that disagree beyond tolerance create an OPEN **DATA CONFLICT**; the higher
  authority is used meanwhile, and an authorised person resolves it.

## 2. Impact Engine

Per frame: buildings with water above floor level (by depth class and use), population exposed
(**aggregated zones only**, vulnerable share), critical facilities with depth ≥ 0.05 m, km of road
flooded/restricted/closed, and economic ranges: exposure = floor area × unit value range;
expected damage = exposure × depth–damage fraction. Unit values and curves are DEMO assumptions shown
in the Impact screen's calculation panel; results are ranges, not point estimates.

## 3. Access & Action Window Engine

* Carriageway depth = water level − road embankment. Thresholds (configurable): **restricted
  0.10 m** (speed × 0.4), **closed 0.30 m** (0.60 m for high-clearance vehicles). Bridges close by
  clearance. Closure intervals are interpolated between frames.
* Road events override the model: verified field reports always win; unverified closures are applied
  conservatively (closed), unverified re-openings are not.
* Searches on the time-dependent graph: earliest arrival (Dijkstra with FIFO waiting), **reverse
  latest-departure search**, max–min access-loss time per node, reachability snapshots.
* **Task deadline** = min(site floods beyond its work limit, crew egress lost, protected road closes,
  explicit deadline). **Latest safe start** = access loss − safety buffer − execution − setup − travel,
  computed exactly by the reverse search. Status bands: SAFE / WINDOW_CLOSING (≤ 45 min) /
  WINDOW_MISSED / NO_ROUTE / NO_DEADLINE.

## 4. Plan Stress Tester & Optimizer

* **Evaluator:** simulates the plan in dependency and crew order (departure = max(planned, crew
  ready)), checks routes, windows, resource conflicts, capabilities and human constraints and emits
  typed issues; a task with < 20 min slack is AT RISK.
* **Causality:** compares the plan's basis evaluation (scenario at approval) with the current one and
  builds typed chains, e.g. SCENARIO_CHANGED → ROAD_CLOSES_EARLIER → RESOURCE_LOSES_ACCESS → TASK_MISSES_WINDOW.
* **Stress test:** higher members, peak 60/120 min earlier, each route road closing 60 min earlier,
  most-used roads unavailable, each crew 30 min late, each vehicle / one pump per pump task
  unavailable, two combined cases. **Robustness = feasible ÷ evaluated scenarios — not a probability.**
* **Value model:** per candidate task, life / infrastructure / economic components, each normalised
  0–100 across candidates, combined with **weights set by a human** (policy presets LIFE_SAFETY 70/20/10,
  CRITICAL_INFRASTRUCTURE 20/65/15, ECONOMIC_LOSS 15/20/65, BALANCED 40/35/25).
* **CP-SAT model (OR-Tools):** optional task selection; per-crew routing circuits (`AddCircuit`) with
  time-dependent travel arcs; arrival ≤ latest arrival; vehicle `NoOverlap`; pump knapsack; equipment
  cumulative; human constraints. Modes: VALUE (policy optimum), ROBUST (reward slack, 20-min margin),
  MINIMAL_CHANGE (only the human plan's tasks, deviation penalty). Loop: solve → evaluate → refine arcs.
* **WHY:** value rank and components; qualified crew and alternative crews' arrival; deadline reason,
  latest departure and route closures; tolerance and the evaluated consequence of exceeding it.
* **Resource gap:** for each resource type, add one virtual unit at the primary base and re-run the
  policy optimum. Deltas are computed, not estimated.

## 5. Operations

DRAFT → REVIEWED (planner/commander) → APPROVED → ACTIVE (commander). Approval freezes the basis
scenario and a resource snapshot. RECOMPUTE runs the optimizer on the current situation and creates a
**new DRAFT version**; the active plan changes only when an authorised person activates the new one.

## 6. Validation

IoU = TP/(TP+FP+FN), precision = TP/(TP+FP), recall = TP/(TP+FN), F1, and overlap areas, computed on
a common grid from the **supplied** observed and modelled masks (modelled depth > 0.05 m = wet).
Without files the dataset is **NOT LOADED** and no metric is shown. The synthetic self-test compares
two simulated members to verify the pipeline and is labelled as not being evidence of skill.

## Known limitations

* Demo flood surfaces are a static-inundation surrogate, not a hydraulic model; no flow velocities.
* Travel times use free-flow speeds scaled by road state; no traffic or congestion.
* Economic values and damage curves are demo assumptions to be replaced by regional tables.
* Kokshetau is a portability/bottleneck demonstration; Lake Kopa is not modelled as a flood cause.
