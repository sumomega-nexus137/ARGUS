# ARGUS FloodOps — Competition Readiness

Date: 3 Oct 2026

## Ready state

ARGUS is launchable as the full PostGIS + FastAPI + Next.js stack. The production-style readiness workflow
passes: frontend typecheck/lint/i18n/unit/build, backend lint/tests/real-data tests, live Open-Meteo provider,
full Docker build/start/health, and pack reuse after restart. The independent PostGIS migration smoke also passes.

## What is real

- Atbasar and Kokshetau real Copernicus DEM terrain.
- Real OSM roads, buildings, waterways, bridges/crossings and facility candidates.
- WorldPop population and JRC long-term surface-water context.
- Curated official 2024 hydrology/event evidence.
- Atbasar Sentinel-2 historical flood evidence and observed/modelled validation masks.
- Public Open-Meteo weather and GloFAS context when online.

## What is modelled / simulated

- Atbasar LOW/BASE/HIGH flood surfaces are historical model outputs, not direct water sensors.
- Kokshetau is a conservative SIMULATION on real geography. It uses a 100 m Kylshakty-connected exercise
  corridor and LOW/BASE/HIGH stage excesses of 0.10/0.20/0.40 m. This replaced the former broad envelope
  that could visually over-flood the city. It is not a property-level prediction or a calibrated hydraulic model.
- Crews, vehicles, pumps, plans and exercise injects are SIMULATION because no verified DChS/MChS inventory
  was supplied.

## Kokshetau realism guard

The default Kokshetau BASE exercise is deliberately bounded to the scale of official 2024 reporting rather
than allowed to spread across low terrain city-wide. Automated tests require the BASE result to stay within
a conservative impacted-building-centroid range and to flag the documented Ertostik near-river anchor.
This is a consistency/scale guard, not spatial validation.

## Atbasar scientific evidence

Headline historical same-event spatial holdout:
- IoU 0.5881
- Precision 0.8155
- Recall 0.6783
- F1 0.7406

These are recalculated from supplied masks, not hardcoded, and are not claimed as future forecast accuracy.
The ~30 m model does not fully reproduce every documented town-interior inundation/embankment effect.

## Plan / stress-test demo

Plan A begins on the approved BASE member and is FEASIBLE.

Measured stress test:
- 23 scenarios
- 9 feasible
- robustness 0.3913

The failures are mixed and interpretable: higher water, earlier peak, selected road/resource losses and
delays can break the plan, while other perturbations remain feasible.

The CP-SAT alternatives are independently stress-tested. The best current alternative improves measured
robustness to 0.4231. Results come from the evaluator; they are not hardcoded.

For the causal demo, use the audited **EXERCISE: HIGH** control:
BASE FEASIBLE → HIGH PLAN AT RISK → WHY chain → restore BASE → stress test → generate alternatives.

## Providers

- Open-Meteo weather/GloFAS: real LIVE call verified in an internet-enabled CI runner; cached/offline fallback
  also verified.
- Kazhydromet: NOT_CONFIGURED until an authorized stable endpoint is supplied.
- Tasqyn: NOT_CONFIGURED until an authorized integration endpoint is supplied.
- No unavailable agency API is shown as LIVE.

## Production verification

Verified on CI:
- PostgreSQL/PostGIS migration: PASS.
- Full docker compose image build/start: PASS.
- API + database health: PASS.
- Frontend health: PASS.
- Real-data pack install/checksum verification: PASS.
- Restart reuses installed packs with no re-download: PASS.
- Frontend production build: PASS.
- Backend DEMO and real-data suites: PASS.
- Live provider + offline cache transition: PASS.

## Windows launch

Prerequisite: Docker Desktop is installed and running.

From the repository, double-click:

`scripts\START_ARGUS.bat`

or run PowerShell:

`powershell -ExecutionPolicy Bypass -File scripts\start-argus.ps1`

The launcher builds/starts PostGIS + backend + frontend, waits for health checks and opens:

`http://localhost:3000`

Competition login:
- planner / argus2026
- commander / argus2026

First launch downloads/verifies the pinned historical data packs. Normal restarts reuse the Docker volumes and
do not re-download the packs.

Stop with:

`scripts\STOP_ARGUS.bat`

## Demo sequence

1. Atbasar / HISTORICAL 2024.
2. Show real map, impact and action windows.
3. Open Plan A on BASE: FEASIBLE.
4. Press EXERCISE: HIGH: same plan becomes AT RISK.
5. Show WHY: scenario → road/access loss → missed action window.
6. Restore BASE.
7. Run STRESS TEST: mixed feasible/failing scenarios.
8. GENERATE ALTERNATIVES and show measured robustness comparison.
9. Close a road → recompute → DRAFT → commander review/approve/activate.
10. Validation: observed vs modelled Sentinel-2 evidence + real calculated metrics and caveats.
11. Kokshetau: show conservative SIMULATION and real bottleneck/network consequence.
12. Switch ҚАЗ / РУС / ENG and show report/offline operation.
