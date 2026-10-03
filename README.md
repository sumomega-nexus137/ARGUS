# ARGUS FloodOps — Regional Flood Decision & Response System

> **Emergency specialists know what to do. ARGUS calculates whether they can still do it in time — and what changes if the situation becomes worse.**

ARGUS FloodOps is a human-in-the-loop decision-support system for regional flood response. It does
not replace emergency specialists and never approves anything by itself. It answers, for an approved
response plan: *will it still work, where does it break, why, and what are the alternatives?*

| Module | What it computes |
|---|---|
| 1. Scenario Engine | Flood scenario model — hybrid terrain-conditioned susceptibility and stage proxy (LOW / BASE / HIGH members), calibrated against historical observations; every change is a new scenario version |
| 2. Impact Engine | Buildings, aggregated population, critical facilities, roads; exposure (floor area) — money only where an approved valuation table exists |
| 3. Access & Action Window Engine | Time-dependent road graph, road closure countdowns, sector isolation, **latest safe action time** per task |
| 4. Plan Stress Tester & Optimizer | Deterministic plan evaluation, STRESS TEST (≈30 perturbations), CP-SAT alternatives under human-set policy weights, WHY explanations, resource-gap analysis |
| 5. Operations Board | DRAFT → REVIEWED → APPROVED → ACTIVE, task status, PLAN AT RISK, RECOMPUTE → new version for approval |
| 6. Validation & After-Action | IoU / precision / recall / F1 recomputed from the observed and modelled masks (historical same-event spatial holdout), curtain comparison, after-action analysis |

Two operational areas: **Atbasar / Zhabai** (primary; historical 2024 validation slot) and
**Kokshetau / Kylshakty** (portability and bottleneck analysis). Interface languages: **Kazakh
(default)**, Russian, English — switch with **ҚАЗ | РУС | ENG** (persisted).

> **Real data.** With the real-data packs installed (one command, below) both pilots run on real
> geography and the 2024 event: Copernicus DEM, OpenStreetMap roads/buildings/facilities/waterways,
> WorldPop, JRC surface water, Sentinel-2 L2A flood evidence (no suitable Sentinel-1 acquisition was found in the probed event-window catalogues) and
> curated official reports — in **HISTORICAL** replay mode. Plans, resources and exercise injects are
> **SIMULATION** (no verified DChS/MChS inventory). Atbasar validation metrics are computed by ARGUS from
> the masks and labelled **HISTORICAL SAME-EVENT SPATIAL HOLDOUT** (not forecast accuracy). Kazhydromet
> and Tasqyn have no public API and stay **NOT CONFIGURED**. Without the packs ARGUS falls back to a
> clearly labelled synthetic DEMO. Details: [`docs/REAL_DATA_INSTALL.md`](docs/REAL_DATA_INSTALL.md),
> test record: [`docs/FINAL_SYSTEM_TEST.md`](docs/FINAL_SYSTEM_TEST.md).

---

## Quick start (local demo, no Docker)

Requirements: Python 3.11+, Node.js 20+ (22 recommended).

```bash
# 1. Backend API (SQLite demo database, auto-seeded on first start)
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.cli install-realdata        # once: download, SHA-256 verify, install both packs (~150 MB)
uvicorn app.main:app --host 127.0.0.1 --port 8000   # ARGUS_DATA_PROFILE=auto → HISTORICAL pilots
#   → http://127.0.0.1:8000/docs  (OpenAPI)

# 2. Console (new terminal)
cd frontend
npm install            # also copies the MapLibre worker into public/maplibre
npm run dev            # → http://localhost:3000  (proxies /api to :8000; set ARGUS_API_URL to change)
```

Demo accounts (password **`argus2026`**, DEMO mode only):

| User | Role | Can |
|---|---|---|
| `viewer` | VIEWER | read-only situational awareness |
| `operator` | OPERATOR | observations, road events, resource & task status |
| `planner` | PLANNER | plans, stress tests, alternatives, resource pool, recompute |
| `commander` | COMMANDER | review/approve/activate plans, resolve data conflicts |
| `admin` | ADMIN | users, providers, outage simulation, demo reset |

Reset the demo to its initial state: **Administration → Reset demo** (admin), or
`cd backend && python -m app.cli reset-demo`.

## Production-like stack (Docker, PostGIS)

```bash
cp .env.example .env          # set ARGUS_JWT_SECRET, POSTGRES_PASSWORD
docker compose up --build     # db (PostGIS 16) + backend (:8000) + frontend (:3000)
```

On first start the backend container installs the pinned real-data packs into the `packs` volume
(verified; later starts reuse them without downloading), then runs `alembic upgrade head` against
PostgreSQL. Set `ARGUS_DEMO_MODE=false` for an empty production database (no seeding, no demo accounts).

## In-app help

Every screen has a **Help** button with plain-language instructions, and the menu contains a full **User guide**
(`/help`) in Kazakh, Russian and English: quick start, badge meanings, map / 3D / timeline, every screen,
step-by-step recipes, how to add data, roles, scientific limitations and FAQ.

## The competition demo flow (26 steps, real data)

Start from an empty database. Automated end-to-end: `node scripts/e2e/demo26.mjs` (see
[`docs/FINAL_SYSTEM_TEST.md`](docs/FINAL_SYSTEM_TEST.md) for the recorded run).

1–2. Launch; the console opens in **Kazakh**. 3–4. **Atbasar — Zhabai**, **HISTORICAL REPLAY** clock
10.04.2024 23:43 with the *2024 historical reconstruction* banner. 5–6. Real map layers; step the timeline.
7. **Impact** — 6,036 OSM buildings, WorldPop zones, exposed floor area; *monetary valuation not available*.
8. **Action windows** — latest safe action time per task (next critical decision T2).
9. **Plan A** starts on the approved **BASE** exercise member and is **PLAN VALID**.
10–11. Trigger the explicit audited **EXERCISE: BASE → HIGH** escalation → **PLAN AT RISK**; **WHY** traces
`SCENARIO CHANGED → ROAD CLOSES EARLIER → RESOURCE LOSES ACCESS → TASK MISSES ACTION WINDOW`.
12. Restore BASE and run **STRESS TEST**: the recorded real-data test gives **9/23 feasible** scenarios
(robustness 0.391), so the result is meaningfully mixed rather than all-pass/all-fail.
13. **GENERATE ALTERNATIVES** (CP-SAT): the recorded run produced an alternative with robustness **11/26 = 0.423**,
a measured improvement computed by the evaluator, not a hard-coded score.
14. Reduce pumps 16 → 8 and re-run to demonstrate resource sensitivity.
15–17. **Operations** — report *road closed* (R29) → pipeline → **RECOMPUTE** → DRAFT v2 → commander
reviews / approves / activates. 18. Operations board.
19–21. **Validation** — real Sentinel-2 evidence, ARGUS-computed holdout metrics with the QC caveat;
provenance and assumptions; sources table (Kazhydromet / Tasqyn NOT CONFIGURED).
22. **Kokshetau — Kylshakty bottlenecks** — real OSM bridges / culverts / low roads on a conservative,
historically impact-bounded **SIMULATION**. The default exercise is restricted to a 100 m river-connected
corridor with LOW/BASE/HIGH excess stages of 0.10/0.20/0.40 m, specifically to prevent the old city-wide
over-flooding behaviour. Select a bottleneck for plan impact (tasks at risk, closed and detour roads).
This is an operational exercise, not a property-level flood forecast or surveyed hydraulic model.
23–24. ҚАЗ → РУС → ENG. 25. Report in kk / ru / en. 26. External providers offline — ARGUS keeps working.

## Quality checks

```bash
cd backend && . .venv/bin/activate
ruff check app && pytest -q                 # engines, API, RBAC, imports, full demo flow (DEMO profile)
pytest -q app/tests_realdata                # real-data packs: historical areas, validation, plan, offline
python -m app.cli realdata-status --verify  # re-hash every installed pack file

cd frontend
npm run typecheck && npm run lint && npm run i18n:check && npm test && npm run build
```

`npm run i18n:check` verifies key parity across kk/ru/en, empty values, ICU placeholder parity and
that every statically used key exists.

## Repository layout

```
backend/            FastAPI app (app/), Alembic migrations, tests (app/tests)
  app/services/     scenario, impact, routing, deadlines, planning, stress_test, optimization,
                    operations, validation, reports, ingest (authority, observations, imports, providers)
  app/providers/    flood scenario providers (synthetic DEMO, precomputed raster manifest), terrain, adapters
  app/demo/         deterministic DEMO generator + seed (both areas)
frontend/           Next.js console (app/, components/, lib/, messages/{kk,ru,en}.json)
data/demo/          generated DEMO fixtures (committed, reproducible: python -m app.cli generate-demo)
data/realdata/      pack lock file, curated exercise plans / events (packs install into */generated, gitignored)
scripts/            realdata/ (pack pipelines + validator), e2e/demo26.mjs (26-step demo flow)
data/imports/       drop-in location for real data (validation masks, imports) — see README there
docs/               ARCHITECTURE, METHODOLOGY, DATA_CONTRACTS, GLOSSARY, IMPLEMENTATION_STATUS
```

## Principles enforced in code

* Human-in-the-loop: ARGUS proposes; only authorised roles approve and activate. Recompute creates a draft.
* Policy weights (life safety / critical infrastructure / economic loss) are set by people.
* Never present simulated data as live: every source carries mode (LIVE / CACHED / HISTORICAL /
  SIMULATION), provenance and freshness; the UI shows DEMO/SIMULATION badges and degraded-mode banners.
* Conflicting observations are never silently overwritten (authority hierarchy + DATA CONFLICT).
* Metrics are computed from supplied data only; nothing is hard-coded.
* Population is only handled in aggregated zones; no personal data is collected.
* Lake Kopa is **not** modelled as a flood cause for Kokshetau; that area demonstrates portability
  and road-network bottlenecks only.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).
