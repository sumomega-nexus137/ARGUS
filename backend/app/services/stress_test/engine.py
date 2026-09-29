"""STRESS TEST MY PLAN.

The plan is re-evaluated under a documented, generated set of perturbation scenarios.
Robustness = (number of evaluated scenarios in which no task is infeasible) / (number evaluated).
No percentage is ever shown that was not computed from these evaluations.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from app.repositories.context import AreaContext
from app.services.planning.causality import explain_evaluation
from app.services.planning.evaluator import ModelCache, evaluate_plan
from app.services.planning.model import Constraint, EvalConfig, PlanEvaluation, TaskSpec
from app.services.routing.access import AccessConfig, build_access_model
from app.services.routing.intervals import INF
from app.services.scenario.runtime import ScenarioRuntime

METHODOLOGY = {
    "robustness": "feasible_scenarios / evaluated_scenarios; a scenario is feasible when no task is INFEASIBLE "
                  "(AT_RISK tasks count as feasible but are reported).",
    "perturbations": [
        "HIGHER_WATER: next higher precomputed ensemble member(s)",
        "EARLIER_PEAK: flood evolution shifted earlier by 60 / 120 min",
        "ROAD_CLOSES_EARLIER: each road on the plan's routes that closes within the horizon closes 60 min earlier",
        "ROUTE_UNAVAILABLE: the most-used roads of the plan are unavailable from now",
        "CREW_DELAYED: each assigned crew departs 30 min late",
        "VEHICLE_UNAVAILABLE / PUMP_UNAVAILABLE: each assigned vehicle / one pump per pump task unavailable",
        "COMBINED: higher water + earlier peak; higher water + delay of the most loaded crew",
    ],
    "limitations": "Perturbations are single-factor or pairwise; they are not a probabilistic ensemble. "
                   "Robustness is not a probability of success.",
}


@dataclass
class Perturbation:
    id: str
    kind: str
    params: dict
    member_shift: int = 0
    time_shift_min: float = 0.0
    road_advance: tuple[tuple[str, float], ...] = ()
    closed_roads: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    delays: tuple[tuple[str, float], ...] = ()
    tags: list[str] = field(default_factory=list)


def generate(ctx: AreaContext, rt: ScenarioRuntime, specs: list[TaskSpec], baseline: PlanEvaluation) -> list[Perturbation]:
    P = [Perturbation("baseline", "BASELINE", {})]
    for k in (1, 2):
        m = rt.member_shifted(k)
        if m != rt.member and all(p.params.get("member") != m for p in P):
            P.append(Perturbation(f"water+{k}", "HIGHER_WATER", {"member": m, "steps": k}, member_shift=k))
    for mins in (60, 120):
        P.append(Perturbation(f"peak-{mins}", "EARLIER_PEAK", {"minutes": mins}, time_shift_min=mins))
    road_use: Counter[str] = Counter()
    for t in baseline.tasks:
        for r in t.route_roads:
            road_use[r] += 1
    m0 = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=baseline.as_of)
    closing_roads = []
    for rid in road_use:
        first = min((m0.closure_from(s, baseline.as_of) for s in ctx.roads[rid].segment_ids), default=INF)
        if first <= rt.horizon_end:
            closing_roads.append((first, rid))
    for _, rid in sorted(closing_roads)[:4]:
        P.append(Perturbation(f"road-{rid}-earlier", "ROAD_CLOSES_EARLIER", {"road": rid, "minutes": 60},
                              road_advance=((rid, 60.0),)))
    main_roads = [r for r, _ in road_use.most_common() if ctx.roads[r].road_class != "highway"][:3]
    for rid in main_roads:
        P.append(Perturbation(f"route-{rid}", "ROUTE_UNAVAILABLE", {"road": rid}, closed_roads=(rid,)))
    crews = sorted({r for t in specs for r in t.resource_ids if ctx.resources.get(r) and ctx.resources[r].type == "CREW"})
    for c in crews:
        P.append(Perturbation(f"delay-{c}", "CREW_DELAYED", {"resource": c, "minutes": 30}, delays=((c, 30.0),)))
    vehicles = sorted({r for t in specs for r in t.resource_ids if ctx.resources.get(r) and ctx.resources[r].type == "VEHICLE"})
    for v in vehicles:
        P.append(Perturbation(f"veh-{v}", "VEHICLE_UNAVAILABLE", {"resource": v}, unavailable=(v,)))
    seen_p = set()
    for t in specs:
        pumps = [r for r in t.resource_ids if ctx.resources.get(r) and ctx.resources[r].type == "PUMP"]
        if pumps and pumps[-1] not in seen_p:
            seen_p.add(pumps[-1])
            P.append(Perturbation(f"pump-{pumps[-1]}", "PUMP_UNAVAILABLE", {"resource": pumps[-1], "task": t.code},
                                  unavailable=(pumps[-1],)))
    if rt.member_shifted(1) != rt.member:
        P.append(Perturbation("water+1&peak-60", "COMBINED", {"member": rt.member_shifted(1), "minutes": 60},
                              member_shift=1, time_shift_min=60))
        load: Counter[str] = Counter()
        for t in specs:
            for r in t.resource_ids:
                if r in crews:
                    load[r] += 1
        if load:
            c = load.most_common(1)[0][0]
            P.append(Perturbation(f"water+1&delay-{c}", "COMBINED", {"member": rt.member_shifted(1), "resource": c,
                                                                    "minutes": 30},
                                  member_shift=1, delays=((c, 30.0),)))
    return P


def run_stress_test(ctx: AreaContext, rt: ScenarioRuntime, specs: list[TaskSpec], as_of: float,
                    constraints: tuple[Constraint, ...] = (), perturbations: list[Perturbation] | None = None) -> dict:
    t0 = time.time()
    base_cfg = EvalConfig(access=AccessConfig(member=rt.member), as_of=as_of, constraints=constraints, label="baseline")
    base_models = ModelCache(ctx, rt, base_cfg.access, as_of)
    baseline = evaluate_plan(ctx, rt, specs, base_cfg, base_models)
    P = perturbations or generate(ctx, rt, specs, baseline)
    results = []
    task_fail: Counter[str] = Counter()
    task_risk: Counter[str] = Counter()
    feasible = 0
    for p in P:
        member = rt.member_shifted(p.member_shift) if p.member_shift else rt.member
        acc = AccessConfig(member=member, time_shift_min=p.time_shift_min, road_advance_min=p.road_advance,
                           closed_roads=p.closed_roads)
        cfg = EvalConfig(access=acc, as_of=as_of, unavailable=frozenset(p.unavailable), delays=p.delays,
                         constraints=constraints, label=p.id)
        if p.kind == "BASELINE":
            ev, models = baseline, base_models
        else:
            models = ModelCache(ctx, rt, acc, as_of)
            ev = evaluate_plan(ctx, rt, specs, cfg, models)
        ok = ev.status != "INFEASIBLE"
        feasible += 1 if ok else 0
        for t in ev.tasks:
            if t.status == "INFEASIBLE":
                task_fail[t.code] += 1
            elif t.status == "AT_RISK":
                task_risk[t.code] += 1
        chains = []
        if p.kind != "BASELINE":
            # root_nodes() already prefixes HIGHER_WATER_LEVEL / EARLIER_PEAK / ROAD_CLOSURE_ADVANCED
            chains = explain_evaluation(ctx, ev, baseline, models.get(), base_models.get(), cfg, base_cfg,
                                        None, (rt.id, rt.version), include_at_risk=False)
        else:
            chains = explain_evaluation(ctx, ev, None, models.get(), None, cfg, None, None, (rt.id, rt.version),
                                        include_at_risk=False)
        results.append({
            "id": p.id, "kind": p.kind, "params": p.params, "member": member, "feasible": ok, "status": ev.status,
            "failed_tasks": ev.failed_codes(), "at_risk_tasks": [t.code for t in ev.tasks if t.status == "AT_RISK"],
            "task_status": {t.code: t.status for t in ev.tasks},
            "chains": [c.as_dict() for c in chains],
            "min_slack": min((t.slack_min for t in ev.tasks if t.slack_min is not None), default=None),
        })
    n = len(P)
    criticality = [{"task": t.code, "failures": task_fail[t.code], "at_risk": task_risk[t.code],
                    "failure_share": task_fail[t.code] / n if n else 0.0} for t in baseline.tasks]
    criticality.sort(key=lambda x: (-x["failures"], -x["at_risk"], x["task"]))
    return {
        "n_scenarios": n,
        "n_feasible": feasible,
        "robustness": feasible / n if n else 0.0,
        "baseline_status": baseline.status,
        "baseline": baseline.as_dict(),
        "scenarios": results,
        "task_criticality": criticality,
        "methodology": METHODOLOGY,
        "duration_s": round(time.time() - t0, 3),
        "member": rt.member,
        "scenario_id": rt.id,
        "as_of": as_of,
    }
