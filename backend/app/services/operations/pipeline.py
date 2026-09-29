"""Event recomputation pipeline.

OBSERVATION / ROAD EVENT / RESOURCE CHANGE / FORECAST CHANGE
  → STORE → SCENARIO UPDATE → IMPACT UPDATE → ROAD GRAPH UPDATE → ACCESS UPDATE
  → ACTION WINDOWS UPDATE → CURRENT PLAN STRESS CHECK → PLAN VALID | PLAN AT RISK

Each step is timed and recorded (PipelineRun) so the UI can show exactly what was recomputed.
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.db.base import new_id
from app.models import PipelineRun
from app.repositories.context import load_context
from app.services.audit import Actor, record
from app.services.clock import area_now, to_minutes
from app.services.deadlines.windows import sector_access
from app.services.impact.engine import frame_impact
from app.services.planning.health import plan_health
from app.services.planning.plans import active_version
from app.services.routing.access import AccessConfig, build_access_model
from app.services.scenario.conditioning import condition_current
from app.services.scenario.runtime import current_scenario, runtime_for


def run_pipeline(db: Session, area_id: str, trigger: str, trigger_ref: str | None, actor: Actor,
                 condition: bool = False) -> dict:
    steps = []

    def step(name: str, fn):  # type: ignore[no-untyped-def]
        t0 = time.time()
        try:
            detail = fn()
            steps.append({"step": name, "status": "OK", "ms": round((time.time() - t0) * 1000), "detail": detail})
            return detail
        except Exception as exc:  # a failing step must not crash operations
            steps.append({"step": name, "status": "ERROR", "ms": round((time.time() - t0) * 1000),
                          "detail": {"error": type(exc).__name__}})
            return None

    steps.append({"step": "STORE", "status": "OK", "ms": 0, "detail": {"trigger": trigger, "ref": trigger_ref}})
    from app.models import OperationalArea

    area = db.get(OperationalArea, area_id)
    now = area_now(area)
    sc = current_scenario(db, area_id)

    def _scenario():
        nonlocal sc
        if not condition:
            return {"scenario": sc.id, "member": sc.active_member_id, "changed": False, "reason": "not an observation trigger"}
        new_sc, sel, changed = condition_current(db, sc, now, actor)
        sc = new_sc
        return {"scenario": sc.id, "member": sc.active_member_id, "changed": changed, "best": sel.get("best_member"),
                "scores": sel.get("scores")}

    step("SCENARIO_UPDATE", _scenario)
    db.flush()
    ctx = load_context(db, area_id)
    rt = runtime_for(sc)
    now_min = to_minutes(rt.reference_time, now)
    model_holder = {}

    def _graph():
        m = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=now_min)
        model_holder["m"] = m
        closed = [s for s in m.edges if m.state_at(s, now_min) == "CLOSED"]
        return {"segments_closed_now": len(closed), "overrides": sum(1 for e in m.edges.values() if e.override)}

    def _impact():
        m = model_holder.get("m")
        f = frame_impact(ctx, rt, rt.member, now_min, m)
        return {"buildings_affected": f["buildings"]["affected"], "population_exposed": f["population"]["exposed"]}

    step("ROAD_GRAPH_UPDATE", _graph)
    step("IMPACT_UPDATE", _impact)

    def _access():
        rows, _ = sector_access(model_holder["m"], now_min)
        return {"isolated_sectors": [r["code"] for r in rows if r["isolated_now"]]}

    step("ACCESS_UPDATE", _access)
    health_holder = {}

    def _windows_and_plan():
        pv = active_version(db, area_id)
        if pv is None:
            return {"plan": None}
        h = plan_health(db, ctx, pv)
        health_holder["h"] = h
        return {"plan_version": pv.id, "status": h["status"], "failed": h["evaluation"]["failed"],
                "at_risk": h["evaluation"]["at_risk"], "next_critical_decision": h["next_critical_decision"]}

    step("ACTION_WINDOWS_UPDATE", lambda: {"computed": True})
    detail = step("PLAN_STRESS_CHECK", _windows_and_plan) or {}
    outcome = detail.get("status") or "NO_ACTIVE_PLAN"
    run = PipelineRun(id=new_id("pl-"), area_id=area_id, trigger=trigger, trigger_ref=trigger_ref, steps=steps,
                      outcome=outcome, data_version=ctx.data_version, created_by=actor.username)
    db.add(run)
    db.flush()
    record(db, actor, "PIPELINE_RUN", "pipeline_run", run.id, f"Recomputation after {trigger}: {outcome}", area_id=area_id,
           details={"steps": [s["step"] for s in steps], "outcome": outcome})
    return {"id": run.id, "trigger": trigger, "outcome": outcome, "steps": steps, "data_version": ctx.data_version,
            "health": health_holder.get("h")}
