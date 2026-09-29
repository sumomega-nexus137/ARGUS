"""Plan health: evaluate a plan version under CURRENT conditions and explain differences from the
conditions it was approved against (basis scenario, resource snapshot, no later field events)."""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy.orm import Session

from app.models import PlanVersion
from app.repositories.context import AreaContext, ResourceInfo
from app.services.clock import to_minutes
from app.services.planning.causality import explain_evaluation
from app.services.planning.evaluator import ModelCache, evaluate_plan
from app.services.planning.model import EvalConfig
from app.services.planning.plans import basis_runtime, constraints_of, to_specs, version_tasks
from app.services.routing.access import AccessConfig
from app.services.scenario.runtime import current_scenario, runtime_for


def context_with_snapshot(ctx: AreaContext, snapshot: dict) -> AreaContext:
    """Copy of ``ctx`` whose resource statuses are those recorded when the plan version was approved."""
    statuses = (snapshot or {}).get("statuses")
    if not statuses:
        res = {k: replace(v, status="AVAILABLE", delay_min=0, available_from=None) for k, v in ctx.resources.items()}
    else:
        res = {}
        for k, v in ctx.resources.items():
            s = statuses.get(k, {"status": "AVAILABLE", "delay_min": 0})
            res[k] = ResourceInfo(**{**v.__dict__, "status": s.get("status", "AVAILABLE"), "delay_min": s.get("delay_min", 0),
                                     "available_from": None})
    return AreaContext(static=ctx.static, data_version=ctx.data_version, resources=res, templates=ctx.templates,
                       road_events=[], now=ctx.now)


def plan_health(db: Session, ctx: AreaContext, pv: PlanVersion) -> dict:
    cur_sc = current_scenario(db, ctx.area_id)
    cur_rt = runtime_for(cur_sc)
    now = to_minutes(cur_rt.reference_time, ctx.now)
    rows = version_tasks(db, pv)
    specs = to_specs(rows, cur_rt)
    cons = constraints_of(pv)
    cur_cfg = EvalConfig(access=AccessConfig(member=cur_rt.member), as_of=now, constraints=cons, label="current")
    cur_models = ModelCache(ctx, cur_rt, cur_cfg.access, now)
    cur_ev = evaluate_plan(ctx, cur_rt, specs, cur_cfg, cur_models)

    ref_rt = basis_runtime(db, pv) or cur_rt
    ref_ctx = context_with_snapshot(ctx, pv.resource_snapshot)
    ref_cfg = EvalConfig(access=AccessConfig(member=ref_rt.member, apply_events=False), as_of=now, constraints=cons,
                         label="basis")
    ref_models = ModelCache(ref_ctx, ref_rt, ref_cfg.access, now)
    ref_ev = evaluate_plan(ref_ctx, ref_rt, specs, ref_cfg, ref_models)

    chains = explain_evaluation(ctx, cur_ev, ref_ev, cur_models.get(), ref_models.get(), cur_cfg, ref_cfg,
                                (ref_rt.id, ref_rt.version), (cur_rt.id, cur_rt.version))
    # use the matching vehicle-class model for each chain where relevant
    infeasible = [t for t in cur_ev.tasks if t.status == "INFEASIBLE"]
    at_risk = [t for t in cur_ev.tasks if t.status == "AT_RISK"]
    status = "PLAN_VALID" if not infeasible and not at_risk else "PLAN_AT_RISK"
    headline = next((c.headline for c in chains if c.headline and c.outcome == "INFEASIBLE"), None) or \
        next((c.headline for c in chains if c.headline), None)
    next_decision = None
    pend = [t for t in cur_ev.tasks if t.latest_departure is not None and t.status not in ("DONE", "IN_PROGRESS")
            and t.latest_departure >= now]
    if pend:
        t = min(pend, key=lambda t: t.latest_departure)
        next_decision = {"task": t.code, "latest_departure": t.latest_departure, "minutes": t.latest_departure - now}
    return {
        "plan_version_id": pv.id,
        "status": status,
        "severity": "critical" if infeasible else ("warning" if at_risk else "ok"),
        "evaluation": cur_ev.as_dict(),
        "basis_evaluation": ref_ev.as_dict(),
        "chains": [c.as_dict() for c in chains],
        "headline": None if headline is None else {"type": headline.type, "params": headline.params},
        "scenario": {"id": cur_rt.id, "version": cur_rt.version, "member": cur_rt.member},
        "basis_scenario": {"id": ref_rt.id, "version": ref_rt.version, "member": ref_rt.member},
        "as_of": now,
        "reference_time": cur_rt.reference_time.isoformat(),
        "next_critical_decision": next_decision,
        "data_version": ctx.data_version,
    }
