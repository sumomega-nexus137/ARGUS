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
robustness from 0.391 to 0.462. Results come from the evaluator; they are not hardcoded, and the deterministic
solver budget makes them reproducible run after run.

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

## In-app user guide

Every screen has an **Анықтама / Справка / Help** button (top right of the screen header) that explains what the
screen is for, how to use it and the related step-by-step recipes. The full guide is in the menu under
**Нұсқаулық / Руководство / User guide** (`/help`): quick start, badge meanings, map and timeline, every screen,
recipes (check / stress-test / alternatives / approve / report a road closure / escalate the scenario / change
language / offline), how to add data (observations, resources, road events, facilities, file imports, real-data
packs), roles and demo accounts, what ARGUS does and does not claim, keyboard and FAQ. New users see a welcome card
on the overview once.

## Demo sequence (3 minutes)

1. **0:00** Overview in Kazakh → click **Атбасар — Жабай**. Point at the **ТАРИХИ ҚАЙТА ОЙНАТУ** badge.
2. **0:15** Press **3D**, then ⤢ (fit area). Real OSM streets, buildings and the Zhabai on the Copernicus DEM.
3. **0:30** Timeline: ⏮ then ▶ at **2×**. The flood spreads east of the river; roads turn orange/red, flooded
   buildings turn yellow-red, closure countdowns appear. Click a building or road → info card.
4. **1:00** **Жоспар**: Plan A on BASE → **ЖОСПАР ОРЫНДАЛАДЫ**. Press the BASE → HIGH exercise escalation →
   **ЖОСПАР ҚАУІПТЕ**; the **НЕГЕ?** chain opens automatically (scenario → road closes earlier → resource loses
   access → task misses window).
5. **1:30** Restore BASE → **ЖОСПАРДЫ СТРЕСС-ТЕСТІЛЕУ**: mixed robustness. **БАЛАМАЛАРДЫ ҚҰРУ**: CP-SAT
   alternatives with higher measured robustness.
6. **2:10** Operations: commander reviews → approves → activates (human approval).
7. **2:30** Validation: Sentinel-2 evidence and ARGUS-computed holdout metrics with the QC caveat.
8. **2:45** Kokshetau bottlenecks: click KBR02 → closed road, task at risk, no hydraulic claim. Switch РУС / ENG.

Full 26-step automated flow: `node scripts/e2e/demo26.mjs` (see `FINAL_SYSTEM_TEST.md`).
