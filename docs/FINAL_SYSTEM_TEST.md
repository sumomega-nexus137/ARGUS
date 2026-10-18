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
| 13–14 | Alternatives; pumps 16 → 8 | CP-SAT alternatives are stress-tested; best alternative robustness **0.462** vs Plan A **0.3913** (deterministic solver); pool 8/16 re-run works |
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
uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-keep-alive 75
cd ../frontend && npm install && npm run build && npx next start -p 3000   # or npm run dev
# Docker: cp .env.example .env && docker compose up --build
```

Accounts (password `argus2026`, demo mode): `viewer`, `operator`, `planner`, `commander`, `admin`.
Demo sequence: README → *The competition demo flow*; automated: `node scripts/e2e/demo26.mjs` on an empty database.


## Competition UX upgrade — test record (3 Oct 2026)

| Check | Result |
|---|---|
| `ruff check app` | clean |
| `pytest app/tests` | passed |
| `pytest app/tests_realdata` (alone) | 10 passed |
| `npm run typecheck` / `npx eslint .` | clean / 0 errors |
| `node scripts/check-i18n.mjs` (now also fails on hardcoded JSX text, attributes and Cyrillic literals) | 1250 keys × 3, 0 hardcoded strings, 0 problems |
| `npx vitest run` | 6 passed |
| `npm run build` | success, 20 routes (incl. `/help`) |
| `node scripts/e2e/demo26.mjs` on a fresh DB | **26 / 26 PASS**, no server or page errors (BASE valid → HIGH at risk with WHY → stress 9/23 → alternatives 0.391 → 0.522 (before the solver was made deterministic) → recompute → commander approval) |
| Startup name sync on an existing DB | 1403 + 29 + 1 object names refreshed, no reset |
| Browser QA | 2D / 3D, playback 0.5×–4× with growing flood, building / road info cards, layers panel, help page and drawer, welcome card, kk / ru / en language scans (remaining non-locale text = OSM proper names, plan names, station IDs, product names) |

Note: in this sandbox the headless browser renders WebGL in software, so 3D runs at about one frame per 1.7 s here;
on a laptop GPU it is interactive. 3D building heights (OSM levels × 3 m), smooth playback between frames and the
water slab are labelled as visualization.

## Final hardening pass — test record (3 Oct 2026)

Fixed: the Data → Imports screen crashed after any successful upload (the page expected a list but the API returns
`{rows, columns, …}`); replaced by a guided import wizard. Also fixed: negative bars in the weather chart (sub-zero
temperatures), a missing-parameter message after manual observations / road events, raw plan / trigger / audit /
quality codes on Operations, Audit, Data sources and Validation, facility types missing from the add form, and an
intermittent proxy `ECONNRESET` (uvicorn keep-alive now 75 s). The CP-SAT optimizer now uses a deterministic
parallel search on a fixed work budget: alternatives no longer depend on CPU load (they did — one e2e run under
load found no improvement), and the same inputs give the same plans on any machine. Added localized error boundaries (screen, area,
map/timeline widgets, global) and a localized 404 page, so a failure never shows a blank page.

| Check | Result |
|---|---|
| `ruff check app` | clean |
| `pytest app/tests` | **28 passed** (new: Excel cp1251 `;` CSV, dd.mm.yyyy + `utc_offset`, missing/unknown columns, broken XLSX/JSON/GeoJSON → 400 never 500) |
| `pytest app/tests_realdata` (alone) | **10 passed** |
| `npm run typecheck` / `npx eslint .` | clean / 0 errors |
| `node scripts/check-i18n.mjs` | 1458 keys × 3, 0 hardcoded, 0 problems |
| `npx vitest run` | 7 passed (new CSV export test) |
| `npm run build` | success |
| Browser: import wizard kk/ru/en | valid + invalid rows, cp1251 file, broken file, wrong extension, confirm, resume preview from history, export → re-import round trip (31 rows, 0 errors) |
| Browser sweep: every screen × every tab, both cities, kk / ru / en, planner / admin / viewer | no page errors, no server 5xx, no missing translations (remaining codes = Sentinel-2 product IDs and recorded system log text) |
| `node scripts/e2e/demo26.mjs` on a fresh DB | **26 / 26 PASS**, no server or page errors; alternatives 0.391 → 0.462 (identical on repeated runs) |

## Light theme + online demo on GitHub — test record (13 Oct 2026)

* **Light theme by default** (white panels, soft grey background, teal accent; blue reserved for water / flood depth),
  light "paper" map; the original dark theme stays one click away (sun / moon button, remembered per browser,
  applied before first paint). Map, markers, popups and charts follow the theme live.
* **Online demo on GitHub Pages** (`.github/workflows/pages.yml`): CI installs the packs, runs the real engines once
  (`scripts/static_demo/record.py`, deterministic CP-SAT) and publishes a read-only static console that answers from
  that snapshot. Local recording: 619 responses, 72 MB, 6 min, no failed request.
* **Full version in GitHub Codespaces** (`.devcontainer/`).

| Check | Result |
|---|---|
| `npx tsc` / `npx eslint .` / i18n check | clean / 0 errors / 1467 keys × 3, 0 problems |
| `npx vitest run` | 9 passed (new: JS ↔ Python snapshot key compatibility) |
| Static export (`ARGUS_STATIC_EXPORT=1`, base path `/ARGUS`) served like GitHub Pages | every screen × every tab, both cities: 0 missing responses, 0 page errors, 0 HTTP errors |
| Static demo buttons | stress test 9/23 and CP-SAT alternatives ALT-1…3 answered from the recorded real runs; data-changing actions show the localized read-only message |
| Server build + `node scripts/e2e/demo26.mjs` on a fresh DB | **26 / 26 PASS**, no server or page errors; alternatives 0.391 → 0.462 |

## Single "daylight blue" theme (14 Oct 2026)

One theme only (no switch): medium-blue header and navigation with white text, soft blue-grey workspace,
off-white panels, navy text; Inter bundled locally (Kazakh / Russian Cyrillic, works offline); the smallest labels
enlarged by 0.5 px. Checks: tsc / eslint clean, i18n 1465 keys × 3 with 0 problems, vitest 9 passed, every screen ×
every tab (ru) without page or server errors.

## Console restyle, "survey sheet" (18 Oct 2026)

The console itself was restyled (no separate landing page; `/` still opens the console): Onest for text and
Unbounded for screen titles (both bundled, Kazakh Cyrillic), header with faint contour lines, light navigation with
a clear active item, softer corners and depth on panels, panels rise in when a screen opens and link cards lift on
hover (both off with reduced motion), sign-in page with the valley model labelled as an illustration. Checks: tsc /
eslint (0 errors), i18n 1476 keys × 3 with 0 problems, vitest 9 passed, server and static-export builds, screenshots
of login / overview / situation / impact / plan without page errors.
