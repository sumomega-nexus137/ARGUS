# ARGUS FloodOps — Final System Test (real-data integration)

Run date: 3 Oct 2026 · branch `claude/festive-faraday-90f1gh` · sandbox: Linux, Python 3.11, Node 22,
Chromium (Playwright). Everything below was executed; nothing is reported from expectation.

## 1. Datasets integrated

| Pack | Archive SHA-256 (lock) | Files verified | Validator |
|---|---|---|---|
| Atbasar / Zhabai | `4c310e03…2524696a` (98.2 MB) | 81 | `validate_pack.py`: 36 PASS / 0 FAIL |
| Kokshetau / Kylshakty | `5423f470…3f181195` (53.6 MB) | 25 | `validate_pack.py`: 15 PASS / 0 FAIL |

As loaded by ARGUS:

| | Atbasar | Kokshetau |
|---|---|---|
| OSM buildings | 6,036 | 20,253 |
| Road segments / roads (largest component) | 1,470 / 394 | 2,999 / 797 |
| Critical facilities (OSM) | 33 | 115 |
| Analysis-grid sectors | 24 (1.2 km) | 39 (1.5 km) |
| WorldPop zones / population in zones | 1,400 / 16,220 | 4,390 / 148,511 |
| Bottleneck candidates | 8 | 25 |
| Scenario | HISTORICAL raster manifest LOW / BASE / HIGH | SIMULATION stage–HAND on real DEM |
| Resources | 31, SIMULATION | 31, SIMULATION |

Also: Copernicus DEM GLO-30, JRC GSW, Sentinel-2 L2A `S2A_42UVC_20240414_1_L2A` / `S2A_42UVC_20240421_0_L2A`
(no Sentinel-1 acquisition; 86.46 % usable optical coverage), curated official chronology and levels (gov.kz),
Open-Meteo GloFAS / weather event-period context.

## 2. APIs / providers

| Provider | Status in test | Notes |
|---|---|---|
| Open-Meteo GloFAS v4 / Forecast | **LIVE verified against the real public endpoints in CI**; cache fallback was then verified with outbound access disabled | GLOBAL_MODEL authority, never overrides local official/verified observations |
| Kazhydromet | NOT_CONFIGURED | no public API; manual / file import |
| Tasqyn | NOT_CONFIGURED | no public API; manual / file import |

## 3. What is real / historical / cached / simulated

* **HISTORICAL**: DEM, WorldPop, JRC, Sentinel-2 evidence, official chronology / levels, Atbasar scenario rasters, event-period GloFAS / weather.
* **CACHED**: OSM snapshot (roads, buildings, facilities, waterways); Open-Meteo responses when cached.
* **SIMULATION**: plans, resources (not DChS/MChS inventory), exercise injects, Kokshetau scenario.
* **LIVE**: Open-Meteo weather/GloFAS was verified through the actual ARGUS provider in an internet-enabled CI runner; cached/offline fallback was verified immediately afterward.

## 4. Commands and results

| Command | Result |
|---|---|
| `cd backend && ruff check app` | All checks passed |
| `pytest app/tests` (DEMO profile) | **27 passed** |
| `pytest app/tests_realdata` (historical, outbound network blocked) | **10 passed** |
| `python -m app.cli realdata-status --verify` | both installed; 81 + 25 files re-hashed OK |
| `python scripts/realdata/validate_pack.py --area atbasar|kokshetau` | 36 / 15 PASS, 0 FAIL |
| `cd frontend && npm run typecheck` | clean |
| `npx eslint .` | 0 errors, 16 warnings (pre-existing react-hooks rules) |
| `node scripts/check-i18n.mjs` | 1038 keys × 3 locales, 693 usages, 0 problems |
| `npx vitest run` | 6 passed |
| `npm run build` | success, 19 routes |
| Full Docker stack | **PASS**: PostGIS + backend + frontend built and started, API/DB/frontend health checks passed, packs installed/verified on first start, backend restart reused the same packs without re-downloading |
| Offline launch (all outbound HTTP refused, empty DB) | no download attempted; seeded historical; live context OFFLINE with message; UI usable |
| `node scripts/e2e/demo26.mjs` (fresh DB) | **26 / 26 PASS**, no server 5xx / page errors |
| ru / en screen sweep (production build) | no raw i18n keys, no Kazakh leakage |

## 5. 26-step demo (recorded run)

| # | Step | Result |
|---|---|---|
| 1 | Launch | API health ok, DB ok |
| 2 | Kazakh default | `html lang=kk` |
| 3 | Atbasar | overview → situation |
| 4 | HISTORICAL 2024 | replay clock 10.04.2024 23:43 + banner |
| 5 | Map | 53 markers, OSM / Copernicus / Sentinel-2 attribution |
| 6 | Timeline | 23:43 → 00:43 → back to now |
| 7 | Impact | floor-area exposure, valuation N/A, 6,036 buildings |
| 8 | Access | next critical decision T2 at 01:18 |
| 9–10 | Plan A | approved BASE starts FEASIBLE; audited exercise escalation BASE → HIGH changes the same plan to PLAN AT RISK |
| 11 | WHY | SCENARIO CHANGED BASE→HIGH → R37 closes earlier (02:29→23:43) → C5 loses access → T1 misses window |
| 12 | Stress test from BASE | **9 / 23 feasible**, robustness **0.3913** — mixed survivals/failures produced by the evaluator |
| 13–14 | Alternatives; pumps 16 → 8 | CP-SAT alternatives are stress-tested; best current alternative robustness **0.4231** vs Plan A **0.3913**; pool 8/16 re-run works |
| 15–16 | Road R29 closed; RECOMPUTE | pipeline → PLAN_AT_RISK; DRAFT v2 |
| 17–18 | Commander review / approve / activate; board | Plan A v2 active; 5 task rows |
| 19–20 | Validation | holdout label, evidence images, metrics below |
| 21 | Provenance | assumptions panel; sources table with NOT CONFIGURED feeds |
| 22 | Kokshetau bottlenecks | KBR02 (улица Абая) → road KR161 closed, T1 FEASIBLE → INFEASIBLE (slack −82 min); top network score KBR16 10.2 |
| 23–24 | ҚАЗ → РУС → ENG | nav and banners switch |
| 25 | Report | kk / ru / en, validation section present |
| 26 | Offline | outage simulation: degraded banner, live context OFFLINE, plan still evaluated |

## 6. Metrics calculated by ARGUS (Atbasar, from `observed.tif` vs `modelled.tif`)

HISTORICAL SAME-EVENT SPATIAL HOLDOUT (headline, 30 m grid, 1.2 km checker blocks, 294,123 holdout cells):
**IoU 0.5881 · Precision 0.8155 · Recall 0.6783 · F1 0.7406.**
Calibration blocks 0.7842 / 0.8622 / 0.8966 / 0.8791; all usable 0.6762 / 0.8392 / 0.7768 / 0.8068;
direct whole-AOI at 20 m 0.5097 / 0.8321 / 0.5681 / 0.6752 (includes permanent water and far terrain).
The real-data test compares the recomputation with the pack calibration file (tolerance 0.002); values are not hardcoded.
Not forecast accuracy, not hydrodynamic validation, not certified accuracy; caveat
`AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC`.

## 7. Limitations and blockers

* Full Docker stack is now verified in CI, including PostGIS migrations and cached real-data reuse after restart.
* Atbasar: documented town-interior flooding associated with local embankment overtopping is not fully reproduced by the ~30 m terrain model.
* Kokshetau: conservative SIMULATION on real geography; 100 m river-connected corridor and low stage excesses prevent the previous city-wide over-spread. It is historically impact-bounded, not spatially calibrated and not a property-level prediction.
* Official gauges use other datums; they are shown but not silently equated with the model stage.
* Open-Meteo LIVE + cache/offline transition is now verified against the real public service.
* Optional external basemap unavailable offline (local layers still render).

## 8. Launch

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
python -m app.cli install-realdata
uvicorn app.main:app --host 127.0.0.1 --port 8000
cd ../frontend && npm install && npm run build && npx next start -p 3000   # or npm run dev
# Docker: cp .env.example .env && docker compose up --build
```

Accounts (password `argus2026`, demo mode): `viewer`, `operator`, `planner`, `commander`, `admin`.
Demo sequence: README → *The competition demo flow*; automated: `node scripts/e2e/demo26.mjs` on an empty database.
