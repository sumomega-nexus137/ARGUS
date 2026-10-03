# Architecture

```
 Browser (Next.js console, kk/ru/en)
   │  same-origin /api/* (Next rewrite → FastAPI; the browser never calls external providers)
   ▼
 FastAPI (backend/app)
   api/routes ── auth · areas · scenarios · analysis · plans · operations · data · validation · reports · misc
   services/
     ingest/        authority hierarchy, observations + DATA CONFLICT, imports (preview→validate→confirm), provider polling
     scenario/      runtime (ensemble member selection), conditioning (weighted RMSE), render (depth PNG frames), export
     impact/        buildings / aggregated population / facilities / roads / economic ranges per frame
     routing/       closure intervals per segment, time-dependent access model, bottlenecks
     deadlines/     task deadlines, latest safe departure, sector & facility access windows
     planning/      plan model, deterministic evaluator (typed Issues), causality (typed chain nodes), health
     stress_test/   perturbation set → robustness, task criticality
     optimization/  value model, CP-SAT solver, alternatives (verify loop + WHY), resource gap
     operations/    lifecycle (DRAFT→REVIEWED→APPROVED→ACTIVE), inputs, pipeline, recompute
     validation/    metrics from supplied masks, synthetic self-test, after-action
     reports/       briefing builder + print-ready HTML (kk/ru/en)
     audit.py       who/what/when; result-affecting changes bump the area data_version
   providers/       FloodScenarioProvider (synthetic DEMO | precomputed raster manifest), terrain tiles, external adapter stubs
   db / models      SQLAlchemy 2; GeometryType = PostGIS geometry (PostgreSQL) or WKT (SQLite demo)
 PostgreSQL + PostGIS (production, Alembic) │ SQLite (local demo)
```

## Key design decisions

* **One recomputation pipeline.** Any input (observation, road event, resource change, pool change,
  forecast member change, task status) runs `STORE → SCENARIO_UPDATE → ROAD_GRAPH_UPDATE →
  IMPACT_UPDATE → ACCESS_UPDATE → ACTION_WINDOWS_UPDATE → PLAN_STRESS_CHECK` and records a
  `PipelineRun` plus an audit entry. The UI shows the steps on the Operations board.
* **data_version.** Every result-affecting change increments the area's `data_version`. The frontend
  includes it in every TanStack Query key, so all screens refresh consistently; stored stress-test and
  optimizer runs carry the version they were computed on and are flagged *outdated* afterwards.
* **Simulation clock.** Each area has its own operational time (`sim_now`). In DEMO mode the clock is
  a labelled SIMULATION CLOCK that planners can advance (+30 min) or reset.
* **Deterministic core, optimizer on top.** The evaluator is the single source of truth for
  feasibility. CP-SAT proposes; every proposal is re-simulated by the evaluator; infeasible legs are
  corrected or forbidden and the model is solved again.
* **Typed explanations.** The backend emits typed issues and causal-chain nodes with parameters
  (`{type: "ROAD_CLOSES_EARLIER", params: {road, from, to}}`). All text is produced by the frontend
  translation catalogues (and by the report renderer), so explanations exist in all three languages.
* **Caches.** Static layers are cached per `static_version`; road depth series per scenario family and
  member. Admin demo reset clears them.
* **Degraded mode.** Provider adapters fail gracefully (status NOT_CONFIGURED / ERROR / STALE). The
  outage simulation (Administration) forces external providers offline; the UI shows banners and
  CACHED/STALE freshness, while computations continue on the last authoritative data.

## Frontend

* Next.js 16 (App Router, Turbopack), React 19, Tailwind v4 tokens, TanStack Query, zustand.
* `use-intl` provider; locale stored in `localStorage` and the `argus_locale` cookie (server layout reads it).
* MapLibre GL: flood depth frames as an image source with A/B cross-fade, road and building
  feature-state styling, DOM markers, backend-served Terrarium DEM tiles for 3D terrain/hillshade.
* Screens: overview (A), situation (B), impact (C), action windows (D) + bottlenecks, plan (E),
  operations (F), validation (G), report (H), plus data & input, audit, administration.
