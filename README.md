# ARGUS FloodOps — Regional Flood Decision & Response System

> **Emergency specialists know what to do. ARGUS calculates whether they can still do it in time — and what changes if the situation becomes worse.**

ARGUS FloodOps is a human-in-the-loop decision-support system for regional flood response. It does
not replace emergency specialists and never approves anything by itself. It answers, for an approved
response plan: *will it still work, where does it break, why, and what are the alternatives?*

| Module | What it computes |
|---|---|
| 1. Scenario Engine | Ensemble flood scenarios (observed → now → forecast), conditioned on authoritative observations; every change is a new scenario version |
| 2. Impact Engine | Buildings, aggregated population, critical facilities, roads and economic ranges per time step |
| 3. Access & Action Window Engine | Time-dependent road graph, road closure countdowns, sector isolation, **latest safe action time** per task |
| 4. Plan Stress Tester & Optimizer | Deterministic plan evaluation, STRESS TEST (≈30 perturbations), CP-SAT alternatives under human-set policy weights, WHY explanations, resource-gap analysis |
| 5. Operations Board | DRAFT → REVIEWED → APPROVED → ACTIVE, task status, PLAN AT RISK, RECOMPUTE → new version for approval |
| 6. Validation & After-Action | IoU / precision / recall computed only from supplied masks, curtain comparison, after-action analysis |

Two operational areas: **Atbasar / Zhabai** (primary; historical 2024 validation slot) and
**Kokshetau / Kylshakty** (portability and bottleneck analysis). Interface languages: **Kazakh
(default)**, Russian, English — switch with **ҚАЗ | РУС | ENG** (persisted).

> ⚠️ **All bundled data is synthetic DEMO / SIMULATION data** generated deterministically for the
> two areas. It is labelled as such everywhere in the UI, API and reports. It is not a measurement,
> a hydrodynamic model or a validation result. Real datasets plug in through the contracts in
> [`docs/DATA_CONTRACTS.md`](docs/DATA_CONTRACTS.md). No real 2024 validation metric is included:
> the validation screen shows **VALIDATION DATA NOT LOADED** until real masks are supplied.

---

## Quick start (local demo, no Docker)

Requirements: Python 3.11+, Node.js 20+ (22 recommended).

```bash
# 1. Backend API (SQLite demo database, auto-seeded on first start)
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
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

The backend container runs `alembic upgrade head` against PostgreSQL before starting. Set
`ARGUS_DEMO_MODE=false` for an empty production database (no demo seeding, no demo accounts).

## The competition demo flow (≈6 minutes)

Log in as **planner**, area **Atbasar — Zhabai**.

1. **Overview / Situation** — a verified field reading (613 cm) conflicts with the hydropost (598 cm);
   ARGUS applies the authority hierarchy, marks the **DATA CONFLICT**, and the scenario moves from
   member M3 to M4 (scenario v2). Timeline: OBSERVED ━● NOW ┄ FORECAST.
2. **Plan** — *Plan A v1* shows **PLAN AT RISK**. Click **WHY?**:
   `FLOOD SCENARIO CHANGED → ROAD R7 CLOSES EARLIER → C3 LOSES ACCESS → TASK T8 MISSES ACTION WINDOW`.
3. **STRESS TEST PLAN** — robustness across ≈30 perturbations, task-criticality bars and the
   perturbation × task matrix (click a row for its causal chain).
4. **GENERATE ALTERNATIVES** — CP-SAT returns *policy optimum*, *robust (max slack)* and *minimal
   change*. Every alternative is re-simulated by the evaluator. Open a task for **WHY THIS TASK /
   RESOURCE / NOW / IF DELAYED**. Change the policy or weights (a human choice) and re-run.
5. **Available pumps 16 → 8** (Alternatives tab) → re-run: the solver drops lower-value work;
   **RESOURCE GAP** shows what one more unit of each type would buy (each row is a full re-run).
6. **Operations** — report *Road closed* (e.g. R2) → pipeline STORE → SCENARIO → ROAD GRAPH →
   IMPACT → ACCESS → ACTION WINDOWS → PLAN CHECK → **PLAN AT RISK** → **RECOMPUTE** creates a new
   DRAFT version; the commander reviews/approves/activates it. The approved plan is never replaced silently.
7. **Validation** — the 2024 dataset reports **NOT LOADED**; the clearly labelled synthetic
   self-test verifies the metric pipeline and the curtain comparison.
8. **Report** — operational briefing in any language, independent of the UI language; print/PDF.
9. **Audit trail** — *why did ARGUS change its result?* Every result-affecting change bumps the
   area's data version with who/what/when.

## Quality checks

```bash
cd backend && . .venv/bin/activate
ruff check app && pytest -q                 # engines, API, RBAC, imports, full demo flow

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
