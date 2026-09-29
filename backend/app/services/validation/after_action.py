"""After-action analysis: model errors, missed windows, delayed tasks, route failures, bottlenecks, version history.

Everything here is derived from recorded data (observations, scenario versions, plan versions, task execution
facts, road events and optimizer runs). Nothing is estimated for display purposes.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OptimizationRun, Plan, PlanTask, PlanVersion, RoadEvent, Scenario
from app.repositories.context import load_context
from app.services.clock import to_minutes
from app.services.ingest.observations import effective_observations
from app.services.planning.plans import evaluate_version
from app.services.scenario.runtime import provider_for

DELAY_THRESHOLD_MIN = 15


def forecast_errors(db: Session, area_id: str) -> list[dict]:
    ctx = load_context(db, area_id)
    out = []
    scenarios = db.scalars(select(Scenario).where(Scenario.area_id == area_id).order_by(Scenario.version)).all()
    for sid in ctx.stations:
        eff, _ = effective_observations(db, sid)
        for s in scenarios:
            issued = s.parameters.get("issued_at")
            prov = provider_for(s)
            series = prov.gauge_series(s.active_member_id)
            ts = np.array([p[0] for p in series])
            ss = np.array([p[1] for p in series])
            res = []
            for e in eff:
                if issued and e.obs.observed_at.isoformat() < issued:
                    continue
                t = to_minutes(s.reference_time, e.obs.observed_at)
                res.append(e.obs.water_level_cm - float(np.interp(t, ts, ss)))
            if not res:
                continue
            arr = np.array(res)
            out.append({"station_id": sid, "scenario_id": s.id, "version": s.version, "member": s.active_member_id,
                        "n": len(res), "bias_cm": round(float(arr.mean()), 1), "mae_cm": round(float(np.abs(arr).mean()), 1),
                        "max_abs_cm": round(float(np.abs(arr).max()), 1)})
    return out


def after_action(db: Session, area_id: str) -> dict:
    ctx = load_context(db, area_id)
    versions = db.scalars(select(PlanVersion).where(PlanVersion.area_id == area_id).order_by(PlanVersion.plan_id, PlanVersion.version)).all()
    history = []
    for v in versions:
        plan = db.get(Plan, v.plan_id)
        tasks = db.scalars(select(PlanTask).where(PlanTask.plan_version_id == v.id)).all()
        history.append({"id": v.id, "plan": plan.name if plan else v.plan_id, "version": v.version, "status": v.status,
                        "origin": v.origin, "created_at": v.created_at, "approved_by": v.approved_by,
                        "approved_at": v.approved_at, "tasks": len(tasks), "change_summary": v.change_summary,
                        "policy": v.policy})
    delayed, failed, missed = [], [], []
    route_failures = []
    active = next((v for v in versions if v.status == "ACTIVE"), None)
    if active is not None:
        ev, rt = evaluate_version(db, ctx, active)
        by = ev.by_code
        for t in db.scalars(select(PlanTask).where(PlanTask.plan_version_id == active.id)):
            tr = by.get(t.code)
            if t.actual_departure and t.planned_departure:
                d = (t.actual_departure - t.planned_departure).total_seconds() / 60
                if d > DELAY_THRESHOLD_MIN:
                    delayed.append({"task": t.code, "delay_min": round(d), "planned": t.planned_departure,
                                    "actual": t.actual_departure})
            if t.status in ("FAILED", "BLOCKED", "RESOURCE_UNAVAILABLE"):
                failed.append({"task": t.code, "status": t.status, "updated_by": t.status_updated_by,
                               "updated_at": t.status_updated_at})
            if tr and any(i.type == "MISSED_ACTION_WINDOW" or i.type == "NO_ROUTE" for i in tr.issues):
                missed.append({"task": t.code, "deadline": tr.deadline, "deadline_reason": tr.deadline_reason,
                               "issues": [i.type for i in tr.issues if i.blocking]})
        routes = {tr.code: set(tr.route_segments) for tr in ev.tasks}
        for e in db.scalars(select(RoadEvent).where(RoadEvent.area_id == area_id, RoadEvent.state == "CLOSED")):
            segs = set(e.segment_ids or ctx.roads.get(e.road_id).segment_ids if ctx.roads.get(e.road_id) else [])
            hit = [code for code, r in routes.items() if r & segs]
            route_failures.append({"event_id": e.id, "road_id": e.road_id, "effective_from": e.effective_from,
                                   "verification": e.verification, "active": e.active, "tasks_rerouted_or_blocked": hit})
    gap = db.scalars(select(OptimizationRun).where(OptimizationRun.area_id == area_id, OptimizationRun.kind == "RESOURCE_GAP")
                     .order_by(OptimizationRun.started_at.desc())).first()
    bottlenecks = []
    if gap is not None:
        bottlenecks = [o for o in gap.result.get("options", []) if o.get("delta_value", 0) > 0][:5]
    unavailable = [{"id": r.id, "type": r.type, "subtype": r.subtype, "status": r.status}
                   for r in ctx.resources.values() if r.status != "AVAILABLE"]
    return {"plan_versions": history, "delayed_tasks": delayed, "failed_tasks": failed, "missed_windows": missed,
            "route_failures": route_failures, "resource_bottlenecks": bottlenecks, "unavailable_resources": unavailable,
            "forecast_errors": forecast_errors(db, area_id),
            "notes": "Forecast errors compare authoritative observations with each scenario version's selected member."}
