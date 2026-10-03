# ARGUS FloodOps — Implementation Status

> Read this first when resuming work. Single source of truth for what exists and what remains.
> Test evidence: [`FINAL_SYSTEM_TEST.md`](FINAL_SYSTEM_TEST.md).

_Status (3 Oct 2026): all six modules and all screens run end-to-end on the **installed real-data packs**.
Atbasar is the HISTORICAL 2024 validation pilot; Kokshetau is a real-geography portability/bottleneck pilot
with a deliberately conservative SIMULATION flood envelope. Full frontend, backend, real-data, live-provider,
PostGIS migration and complete Docker-stack readiness checks pass. The synthetic DEMO profile remains only
as a fallback/unit-test profile._

## Done

| Area | State |
|---|---|
| Real-data packs | Release assets `realdata-2026-10-01` (workflow `realdata-release.yml`), pinned in `data/realdata/packs.lock.json`; `python -m app.cli install-realdata` downloads once, verifies archive SHA-256 + every file against the pack manifest, installs to `<realdata>/<area>/generated`; startup never downloads. `ARGUS_DATA_PROFILE=auto/historical/demo`. Docs: `REAL_DATA_INSTALL.md` |
| Area build | `app/realdata/build.py`: OSMnx road graph (largest component), OSM buildings / facilities / waterways / bridges, WorldPop dasymetric zones, analysis-grid sectors, bottleneck candidates (bridges, culverts / channel crossings, low roads), stations + curated official observations, exercise plans; runtime bundle rebuilt only on pack / exercise / builder change |
| Module 1 Scenario | Atbasar: raster-manifest provider, LOW / BASE / HIGH historical rasters, audited BASE → HIGH exercise escalation. Kokshetau: stage–HAND on the real DEM, bounded to a conservative 100 m Kylshakty-connected exercise corridor with LOW / BASE / HIGH = 0.10 / 0.20 / 0.40 m; SIMULATION and explicitly not spatially calibrated. A regression test prevents return to city-wide overflooding and checks the known Ertostik historical anchor. |
| Module 2 Impact | Real buildings / population / facilities / roads; exposure as floor area — no money without an approved valuation table (`NOT_AVAILABLE_NO_APPROVED_VALUATION`); vulnerable share "not available" |
| Module 3 Access | Time-dependent graph on real roads, ACCESS_LOST windows, latest safe action time; bottleneck analysis on real candidates with on-demand plan re-evaluation (tasks at risk, closed / detour roads); cached structural betweenness |
| Module 4 Plan | Plan A / Plan K-1 exercise plans, evaluator, WHY chains, stress test, CP-SAT alternatives (4 policies), resource pool, resource gap; resources labelled SIMULATION |
| Module 5 Operations | Lifecycle with commander approval, road events → pipeline → RECOMPUTE → DRAFT, task board |
| Module 6 Validation | Atbasar metrics recomputed from observed / modelled masks: holdout IoU 0.5881 · P 0.8155 · R 0.6783 · F1 0.7406, plus calibration / all-usable / direct-AOI rows; label HISTORICAL SAME-EVENT SPATIAL HOLDOUT; caveat AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC; Sentinel-2 fallback documented; after-action compares only same-datum stations |
| Providers | Open-Meteo GloFAS v4 / forecast: GLOBAL_MODEL, timeout, retry, cache, LIVE / CACHED / STALE / OFFLINE with data age; Kazhydromet / Tasqyn NOT_CONFIGURED (no endpoint invented) |
| Provenance / labels | Modes LIVE / CACHED / HISTORICAL / SIMULATION / NOT POLLED; pack layers aged on the wall clock, historical layers show data time; assumptions, limitations, chronology, bottleneck notes localized kk / ru / en (English pack text as source) |
| Frontend | Historical clock + banners, waterways, local rivers on the region map (offline), per-area attribution, history / live-context / assumptions panels, validation evidence + protocol table, bottleneck plan impact, Data screen with full date-time and post-replay flags |
| Performance | Encoded static layers cached per static version, single-builder lock for area contexts, background warm-up (`ARGUS_WARMUP`), bottleneck analysis cache |
| Ops | Docker entrypoint installs packs into the `packs` volume, `runtime` volume, `libexpat1` for rasterio, `.dockerignore`, `.env.example` with all new settings |
| Quality | Backend ruff + 27 DEMO tests + 10 real-data tests (network blocked); frontend tsc, eslint (0 errors), i18n checker (1038 keys × 3), vitest, `next build`; pack validators; `scripts/e2e/demo26.mjs` |

## Not done / limitations

* Full `docker compose up -d --build` is now verified in CI: PostGIS, backend, frontend, health checks,
  first-start pack installation and backend restart reuse all pass. The packs are not re-downloaded on restart.
* Atbasar still has a scientific limitation: documented town-interior flooding associated with local
  embankment overtopping is not fully reproduced by the ~30 m terrain model. Kokshetau is intentionally
  labelled SIMULATION: it is historically impact-bounded to avoid the former city-wide over-spread, but it
  is not an observed inundation reconstruction or a calibrated hydraulic forecast.
* Plan A now starts on its approved BASE member and is FEASIBLE at baseline. Its real evaluator stress test
  returns a mixed 9/23 feasible scenarios (robustness 0.3913); HIGH/earlier-peak/resource-loss cases fail
  naturally. CP-SAT alternatives are re-evaluated, with the best current alternative improving robustness
  to 0.4231. No pass/fail values are hardcoded.
* The optional external CARTO basemap is unreachable offline; operational layers and local rivers still render.
* Headless PDF (browser print → PDF works); map click-to-place for new facilities.
* 16 pre-existing eslint warnings (react-hooks style rules), 0 errors.
