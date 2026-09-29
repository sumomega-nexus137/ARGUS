# ARGUS FloodOps — Implementation Status

> READ THIS FILE FIRST when resuming work. It is the single source of truth for
> what exists, how it fits together and what remains.

_Status: Phase 0 — plan written, Phase 1 in progress._

## Plan (condensed)

1. Backend foundation (FastAPI, SQLAlchemy, SQLite demo / PostGIS prod, Alembic).
2. Deterministic demo data generator (synthetic DEM, river, roads, buildings, facilities, resources,
   approved actions, human plan, scenario ensemble) — everything labelled DEMO / SIMULATION.
3. Engines: scenario → impact → time-dependent road graph → action windows →
   plan evaluator → stress tester → CP-SAT optimizer → operations → validation.
4. REST API + audit + RBAC.
5. Next.js frontend (kk default, ru, en) with MapLibre 2D/3D, timeline, eight product screens.
6. Docker Compose, README, docs.
