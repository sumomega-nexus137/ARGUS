"""Impact (Module 2) and Access & Action Windows (Module 3) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user
from app.api.serialize import clean
from app.core.errors import ArgusError
from app.db.session import get_db
from app.models import OperationalArea, User
from app.repositories.context import load_context
from app.schemas.common import WhatIfBottleneck
from app.services.clock import area_now, to_minutes
from app.services.deadlines.windows import edge_states_payload, facility_access, road_windows, sector_access
from app.services.impact.engine import frame_impact, impact_timeline
from app.services.planning.evaluator import ModelCache, evaluate_plan
from app.services.planning.model import EvalConfig
from app.services.planning.plans import active_version, constraints_of, plan_name, to_specs, version_tasks
from app.services.routing import bottlenecks as bn
from app.services.routing.access import AccessConfig, build_access_model
from app.services.routing.intervals import INF, finite_or_none
from app.services.scenario.runtime import current_scenario, runtime_for

router = APIRouter(prefix="/api/areas/{area_id}", tags=["impact", "access"])


def _t(rt, t: float | None, area: OperationalArea) -> float:  # type: ignore[no-untyped-def]
    now_min = to_minutes(rt.reference_time, area_now(area))
    if t is None:
        return now_min
    if not (rt.horizon_start - 1e-6 <= t <= rt.horizon_end + 1e-6):
        raise ArgusError("time_outside_scenario", "Requested time is outside the scenario horizon",
                         start=rt.horizon_start, end=rt.horizon_end)
    return float(t)


@router.get("/impact")
def impact(t: float | None = None, include_calculation: bool = False, area: OperationalArea = Depends(area_or_404),
           db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    ctx = load_context(db, area.id)
    rt = runtime_for(current_scenario(db, area.id))
    tt = _t(rt, t, area)
    m = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=to_minutes(rt.reference_time, ctx.now))
    out = frame_impact(ctx, rt, rt.member, tt, m, include_calculation=include_calculation)
    return clean({**out, "scenario_id": rt.id, "member": rt.member, "reference_time": rt.reference_time,
                  "mode": "SIMULATION" if rt.mode == "SIMULATION" else rt.mode,
                  "kind": "ANALYSIS" if tt <= to_minutes(rt.reference_time, ctx.now) else "FORECAST"})


@router.get("/impact/timeline")
def impact_tl(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
              _: User = Depends(current_user)) -> dict:
    ctx = load_context(db, area.id)
    rt = runtime_for(current_scenario(db, area.id))
    m = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=to_minutes(rt.reference_time, ctx.now))
    return clean({**impact_timeline(ctx, rt, rt.member, m), "scenario_id": rt.id, "member": rt.member,
                  "frame_offsets_min": rt.frame_offsets, "reference_time": rt.reference_time})


@router.get("/access")
def access(t: float | None = None, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
           _: User = Depends(current_user)) -> dict:
    ctx = load_context(db, area.id)
    rt = runtime_for(current_scenario(db, area.id))
    now_min = to_minutes(rt.reference_time, ctx.now)
    as_of = _t(rt, t, area)
    m = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=now_min)
    roads = road_windows(m, as_of)
    sectors, loss = sector_access(m, as_of)
    facilities = facility_access(m, as_of, loss)
    tasks, plan = [], None
    pv = active_version(db, area.id)
    next_decision = None
    if pv is not None:
        specs = to_specs(version_tasks(db, pv), rt)
        cfg = EvalConfig(access=AccessConfig(member=rt.member), as_of=as_of, constraints=constraints_of(pv), label="windows")
        ev = evaluate_plan(ctx, rt, specs, cfg, ModelCache(ctx, rt, cfg.access, now_min))
        plan = {"plan_version_id": pv.id, "name": plan_name(db, pv), "version": pv.version, "status": ev.status}
        for tr in ev.tasks:
            if tr.status in ("DONE",):
                continue
            tasks.append({"code": tr.code, "template_id": tr.template_id, "site_id": tr.site_id, "crew": tr.crew_id,
                          "planned_departure": tr.planned_departure, "departure": tr.departure,
                          "latest_departure": tr.latest_departure, "deadline": tr.deadline,
                          "deadline_reason": tr.deadline_reason, "window_status": tr.window_status,
                          "slack_to_latest_min": None if tr.latest_departure is None else tr.latest_departure - as_of,
                          "plan_status": tr.status, "route_roads": tr.route_roads, "latest_route_roads": tr.latest_route_roads,
                          "end": tr.end, "issues": [i.type for i in tr.issues]})
        pend = [x for x in tasks if x["latest_departure"] is not None and x["latest_departure"] >= as_of]
        if pend:
            nd = min(pend, key=lambda x: x["latest_departure"])
            next_decision = {"task": nd["code"], "latest_departure": nd["latest_departure"],
                             "minutes": nd["latest_departure"] - as_of}
    return clean({
        "as_of": as_of, "now_min": now_min, "reference_time": rt.reference_time, "scenario_id": rt.id, "member": rt.member,
        "horizon_end": rt.horizon_end, "roads": roads, "sectors": sectors, "facilities": facilities,
        "edges": edge_states_payload(m, as_of), "tasks": tasks, "plan": plan, "next_critical_decision": next_decision,
        "mode": rt.mode,
    })


@router.get("/access/timeline")
def access_timeline(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                    _: User = Depends(current_user)) -> dict:
    """Per-frame segment states (0 open, 1 restricted, 2 closed) for instant timeline scrubbing + closure markers."""
    ctx = load_context(db, area.id)
    rt = runtime_for(current_scenario(db, area.id))
    now_min = to_minutes(rt.reference_time, ctx.now)
    m = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=now_min)
    code = {"OPEN": 0, "RESTRICTED": 1, "CLOSED": 2}
    states = {sid: [code[m.state_at(sid, float(off))] for off in rt.frame_offsets] for sid in m.edges}
    closures = {}
    for rid, road in ctx.roads.items():
        first = min(m.closure_from(s, rt.horizon_start) for s in road.segment_ids)
        if first != INF and first <= rt.horizon_end:
            closures[rid] = finite_or_none(first)
    sectors, _ = sector_access(m, now_min)
    return clean({"frame_offsets_min": rt.frame_offsets, "states": states, "road_closures": closures,
                  "sector_access_loss": {s["code"]: s["access_lost_at"] for s in sectors}, "now_min": now_min,
                  "scenario_id": rt.id, "reference_time": rt.reference_time})


@router.post("/bottlenecks/analyze")
def analyze_bottlenecks(body: WhatIfBottleneck, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                        _: User = Depends(current_user)) -> dict:
    ctx = load_context(db, area.id)
    rt = runtime_for(current_scenario(db, area.id))
    as_of = _t(rt, body.as_of_min, area)
    pv = active_version(db, area.id)
    plan = None if pv is None else bn.PlanInput(pv.id, tuple(to_specs(version_tasks(db, pv), rt)), tuple(constraints_of(pv)))
    return clean({**bn.analyze(ctx, rt, as_of, body.bottleneck_ids or None, plan), "reference_time": rt.reference_time})
