# ARGUS FloodOps — Implementation Status

> Read this first when resuming work. Single source of truth for what exists and what remains.

_Status: all six modules and all screens are implemented end-to-end on DEMO / SIMULATION data.
The real-data preparation work is now complete for the Atbasar and Kokshetau pilot packs: terrain,
roads/buildings, population/water baselines, official curated event/hydrology records, public
GloFAS/weather context, and the Atbasar 2024 satellite/validation/scenario package have all passed
their data-pipeline integrity gates. Application mounting/import/provider wiring and the full
backend/frontend/demo test pass are still pending and are the next integration step. See
`docs/REAL_DATA_FINAL_STATUS.md` and `docs/REAL_DATA_HANDOFF.md`._

## Done

| Area | State |
|---|---|
| Backend foundation | FastAPI, Pydantic settings (`ARGUS_*`), SQLAlchemy 2, SQLite demo / PostGIS prod, Alembic baseline (`backend/alembic`), JWT auth, RBAC (VIEWER/OPERATOR/PLANNER/COMMANDER/ADMIN), audit trail with `data_version` |
| Demo data | Deterministic generator for Atbasar/Zhabai and Kokshetau/Kylshakty (`python -m app.cli generate-demo`), seeded on first start; everything labelled DEMO / SIMULATION |
| Module 1 Scenario | Ensemble M1–M6, stage–HAND surrogate, observation conditioning (weighted RMSE), scenario versions, manual member selection, depth PNG frames, raster-manifest provider for real surfaces |
| Module 2 Impact | Buildings, aggregated population, facilities, roads, economic ranges, calculation transparency |
| Module 3 Access | Closure intervals, road-event overrides, earliest-arrival / latest-departure searches, sector & facility windows, bottleneck what-if + structural candidates |
| Module 4 Plan | Evaluator, causal chains, plan health, stress test (≈30 perturbations), CP-SAT alternatives (VALUE / ROBUST / MINIMAL_CHANGE) with verify loop and WHY, resource gap, human constraints, resource pool, policy presets (`/api/policies`) |
| Module 5 Operations | Lifecycle, task status, event injection, pipeline with 7 steps, recompute → new DRAFT |
| Module 6 Validation | Metrics from supplied masks only, NOT LOADED state, synthetic self-test, curtain + difference layers, after-action |
| Data & input | Observations + verification, DATA CONFLICT resolution, resources, road events, facilities, imports wizard, sources/freshness, approved action library |
| Degraded mode | Provider statuses, outage simulation, offline banners |
| Reports | Server HTML briefing in kk/ru/en (independent of UI language), print/PDF |
| Frontend | Next.js 16 console, kk default + ru + en with persisted switcher, MapLibre 2D/3D, timeline OBSERVED ━● NOW ┄ FORECAST, screens A–H + data, audit, admin |
| Ops | `docker-compose.yml` (PostGIS + backend + frontend), Dockerfiles, `.env.example`, admin demo reset |
| Quality | Backend: ruff + pytest (engines, API, RBAC, imports, full demo flow, reset). Frontend: tsc, eslint, i18n checker, vitest, production build |

## Verified demo story (computed, not scripted)

Scenario v2 (M4, conditioned on a verified field reading 613 cm vs hydropost 598 cm → OPEN conflict):
Plan A v1 → PLAN AT RISK; R7 closes ~13:55 instead of ~16:32; T8 loses egress (deadline ~14:12),
planned 14:30 → NO_ROUTE. Chain: SCENARIO_CHANGED → ROAD_CLOSES_EARLIER R7 → C3 LOSES ACCESS →
T8 MISSES WINDOW. MINIMAL_CHANGE retimes T8 to ~12:21.

## Not yet done / next steps

* Mount/import the completed real-data artifacts into the application data volume and wire the
  existing provider/import contracts. Atbasar historical evidence uses a documented Sentinel-2
  fallback because no suitable Sentinel-1 acquisition was found for the event window.
* Docker images were written but could not be built in the development sandbox (no Docker daemon);
  run `docker compose up --build` to verify.
* Wire the ready public Open-Meteo GloFAS/weather profiles into runtime providers if desired.
  Kazhydromet/Tasqyn remain NOT_CONFIGURED until authorized endpoints are supplied; do not fake LIVE data.
* Headless PDF rendering (the HTML briefing is print-ready; browser print → PDF works).
* Map-based click-to-place for new facilities (coordinates are entered manually today).
