"""Optimization runs (persisted), adopting alternatives and RECOMPUTE of an active plan."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core.errors import ArgusError, NotFound
from app.db.base import new_id
from app.models import OptimizationRun, PlanVersion, StressTestRun
from app.repositories.context import AreaContext
from app.services.audit import Actor, record
from app.services.clock import from_minutes, to_minutes
from app.services.operations.lifecycle import new_version
from app.services.optimization.alternatives import optimize
from app.services.optimization.resource_gap import resource_gap
from app.services.planning.health import plan_health
from app.services.planning.model import Constraint
from app.services.planning.plans import constraints_of, plan_name, to_specs, version_tasks
from app.services.scenario.runtime import current_scenario, runtime_for
from app.services.stress_test.engine import run_stress_test


def run_stress(db: Session, ctx: AreaContext, pv: PlanVersion, actor: Actor) -> StressTestRun:
    rt = runtime_for(current_scenario(db, ctx.area_id))
    now = to_minutes(rt.reference_time, ctx.now)
    specs = to_specs(version_tasks(db, pv), rt)
    res = run_stress_test(ctx, rt, specs, now, constraints_of(pv))
    run = StressTestRun(id=new_id("st-"), area_id=ctx.area_id, plan_version_id=pv.id, scenario_id=rt.id,
                        created_by=actor.username, n_scenarios=res["n_scenarios"], n_feasible=res["n_feasible"],
                        robustness=res["robustness"], result={**res, "reference_time": rt.reference_time.isoformat()},
                        data_version=ctx.data_version)
    db.add(run)
    db.flush()
    record(db, actor, "PLAN_STRESS_TESTED", "stress_test_run", run.id,
           f"{plan_name(db, pv)} v{pv.version}: feasible in {res['n_feasible']}/{res['n_scenarios']} evaluated scenarios",
           area_id=ctx.area_id, details={"plan_version": pv.id, "robustness": res["robustness"]})
    return run


def run_alternatives(db: Session, ctx: AreaContext, pv: PlanVersion, *, policy: str, weights: dict | None,
                     extra_constraints: list[dict] | None, what_if_unavailable: list[str] | None, actor: Actor,
                     kind: str = "ALTERNATIVES") -> OptimizationRun:
    rt = runtime_for(current_scenario(db, ctx.area_id))
    now = to_minutes(rt.reference_time, ctx.now)
    specs = to_specs(version_tasks(db, pv), rt)
    cons = constraints_of(pv) + tuple(Constraint.from_dict(c) for c in (extra_constraints or []))
    t0 = time.time()
    res = optimize(ctx, rt, now, policy=policy, weights=weights, constraints=cons, plan_specs=specs,
                   extra_candidates=ctx.config.get("extra_candidates", []), unavailable=set(what_if_unavailable or []))
    run = OptimizationRun(id=new_id("opt-"), area_id=ctx.area_id, plan_version_id=pv.id, scenario_id=rt.id, kind=kind,
                          policy=policy, weights=res["weights"], constraints=[c.as_dict() for c in cons],
                          status="OK" if res["feasible"] else "NO_FEASIBLE_SOLUTION", duration_s=round(time.time() - t0, 2),
                          result={**res, "reference_time": rt.reference_time.isoformat(),
                                  "what_if_unavailable": what_if_unavailable or []},
                          created_by=actor.username, data_version=ctx.data_version)
    db.add(run)
    db.flush()
    record(db, actor, "ALTERNATIVES_GENERATED" if kind != "RECOMPUTE" else "OPTIMIZER_RERUN", "optimization_run", run.id,
           f"CP-SAT {policy}: {len(res['alternatives'])} alternative(s) for {plan_name(db, pv)} v{pv.version}",
           area_id=ctx.area_id, details={"plan_version": pv.id, "policy": policy, "weights": res["weights"],
                                         "alternatives": [a["id"] + ":" + a["label"] for a in res["alternatives"]]})
    return run


def run_gap(db: Session, ctx: AreaContext, pv: PlanVersion, *, policy: str, weights: dict | None, actor: Actor,
            what_if_unavailable: list[str] | None = None) -> OptimizationRun:
    rt = runtime_for(current_scenario(db, ctx.area_id))
    now = to_minutes(rt.reference_time, ctx.now)
    specs = to_specs(version_tasks(db, pv), rt)
    t0 = time.time()
    res = resource_gap(ctx, rt, now, policy=policy, weights=weights, constraints=constraints_of(pv), plan_specs=specs,
                       extra_candidates=ctx.config.get("extra_candidates", []), unavailable=set(what_if_unavailable or []),
                       time_limit=1.5)
    run = OptimizationRun(id=new_id("gap-"), area_id=ctx.area_id, plan_version_id=pv.id, scenario_id=rt.id,
                          kind="RESOURCE_GAP", policy=policy, weights=res.get("weights", {}), constraints=[],
                          status="OK" if res["feasible"] else "NO_FEASIBLE_SOLUTION", duration_s=round(time.time() - t0, 2),
                          result=res, created_by=actor.username, data_version=ctx.data_version)
    db.add(run)
    db.flush()
    record(db, actor, "RESOURCE_GAP_ANALYSED", "optimization_run", run.id, f"Marginal resource analysis ({policy})",
           area_id=ctx.area_id)
    return run


def _tasks_from_alt(alt: dict, ref_time) -> list[dict]:  # type: ignore[no-untyped-def]
    why = {t["code"]: t.get("why") for t in alt["tasks"]}
    out = []
    for i, s in enumerate(alt["specs"]):
        out.append({"code": s["code"], "template_id": s["template_id"], "site_id": s["site_id"],
                    "resource_ids": s["resource_ids"], "planned_departure": from_minutes(ref_time, s["planned_departure"]),
                    "dependencies": [], "sort_order": i, "rationale": {"why": why.get(s["code"])} if why.get(s["code"]) else {},
                    "status": s.get("status", "PENDING")})
    return out


def adopt_alternative(db: Session, run: OptimizationRun, alt_id: str, actor: Actor, origin: str = "OPTIMIZER",
                      reason: dict | None = None) -> PlanVersion:
    if not run.plan_version_id:
        raise ArgusError("run_without_plan", "Optimization run is not linked to a plan version")
    parent = db.get(PlanVersion, run.plan_version_id)
    if parent is None:
        raise NotFound("plan version", run.plan_version_id)
    alt = next((a for a in run.result.get("alternatives", []) if a["id"] == alt_id), None)
    if alt is None:
        raise NotFound("alternative", alt_id)
    from datetime import datetime

    ref = datetime.fromisoformat(run.result["reference_time"])
    tasks = _tasks_from_alt(alt, ref)
    summary = {"from_version": parent.version, "alternative": alt_id, "label": alt["label"], "diff": alt["diff_vs_human"],
               "policy": run.policy, "weights": run.weights, "optimization_run": run.id,
               "metrics": alt["metrics"], "robustness": alt.get("robustness"), **(reason or {})}
    pv = new_version(db, parent, tasks, actor, origin=origin, change_summary=summary, policy=run.policy, weights=run.weights,
                     optimization_run_id=run.id)
    return pv


def recompute(db: Session, ctx: AreaContext, pv: PlanVersion, actor: Actor, policy: str = "BALANCED",
              weights: dict | None = None) -> dict:
    health = plan_health(db, ctx, pv)
    run = run_alternatives(db, ctx, pv, policy=policy, weights=weights, extra_constraints=None, what_if_unavailable=None,
                           actor=actor, kind="RECOMPUTE")
    alts = run.result.get("alternatives", [])
    if not alts:
        raise ArgusError("no_feasible_solution", "No feasible alternative exists with current resources")

    def ok(a: dict) -> bool:
        return a["evaluation"]["status"] != "INFEASIBLE"

    chosen = next((a for a in alts if a["label"] == "MINIMAL_CHANGE" and ok(a)), None) or \
        next((a for a in alts if ok(a)), alts[0])
    reason = {"trigger": "RECOMPUTE", "health_before": health["status"], "headline": health["headline"],
              "chains": health["chains"][:5]}
    new_pv = adopt_alternative(db, run, chosen["id"], actor, origin="RECOMPUTE", reason=reason)
    return {"plan_version": new_pv, "optimization_run": run, "chosen": chosen["id"], "label": chosen["label"],
            "health_before": health["status"]}
