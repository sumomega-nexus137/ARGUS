"""GENERATE ALTERNATIVES — orchestration around the CP-SAT model.

1. Candidate tasks = tasks of the human plan + additional approved candidates for the area.
2. Policy-independent value components (value.py) × HUMAN-chosen policy weights.
3. CP-SAT solve → exact verification with the plan evaluator → refine travel arcs → re-solve.
4. Alternatives: policy optimum, a structurally different plan (no-good cut), and a minimal-change
   repair of the human plan. Each is stress-tested and explained (WHY task / resource / now / if delayed).
"""

from __future__ import annotations

import math
import time
from dataclasses import replace

from app.core.config import get_settings
from app.repositories.context import AreaContext, ResourceInfo
from app.services.optimization.solver import (
    OptProblem,
    Solution,
    TravelTable,
    build_candidates,
    solve,
)
from app.services.optimization.value import BENEFIT_SHARE, compute_values, normalise_weights
from app.services.planning.evaluator import ModelCache, evaluate_plan
from app.services.planning.model import Constraint, EvalConfig, PlanEvaluation, TaskSpec
from app.services.routing.access import AccessConfig, build_access_model
from app.services.routing.intervals import INF, finite_or_none
from app.services.scenario.runtime import ScenarioRuntime
from app.services.stress_test.engine import run_stress_test

MAX_REFINE = 5


def candidate_list(plan_specs: list[TaskSpec], extra: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out = []
    for t in plan_specs:
        key = (t.template_id, t.site_id)
        if key in seen:
            continue
        seen.add(key)
        out.append({"code": t.code, "template": t.template_id, "site": t.site_id, "origin": "HUMAN_PLAN"})
    for e in extra:
        key = (e["template"], e["site"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"code": e["code"], "template": e["template"], "site": e["site"], "origin": "CANDIDATE"})
    return out


def with_resource_changes(ctx: AreaContext, unavailable: set[str], extra: list[ResourceInfo]) -> AreaContext:
    res = {}
    for k, v in ctx.resources.items():
        res[k] = replace(v, status="UNAVAILABLE") if k in unavailable else v
    for e in extra:
        res[e.id] = e
    return type(ctx)(static=ctx.static, data_version=ctx.data_version, resources=res, templates=ctx.templates,
                     road_events=ctx.road_events, now=ctx.now)


def _available(ctx: AreaContext, rtype: str, busy: set[str]) -> list[ResourceInfo]:
    return [r for r in ctx.resources.values() if r.type == rtype and r.status == "AVAILABLE" and r.id not in busy]


def _release(ctx: AreaContext, as_of: float, fixed_eval: PlanEvaluation | None) -> tuple[dict, set[str]]:
    release: dict[str, tuple[float, str | None]] = {}
    for rid, r in ctx.resources.items():
        base = ctx.bases.get(r.base or "")
        release[rid] = (as_of + (r.delay_min or 0), base.node if base else None)
    held: set[str] = set()
    if fixed_eval:
        for t in fixed_eval.tasks:
            tpl = ctx.templates.get(t.template_id)
            site = ctx.sites.get(t.site_id)
            holds = set((tpl.constraints or {}).get("holds", [])) if tpl else set()
            for rid in t.resource_ids:
                r = ctx.resources.get(rid)
                if r is None:
                    continue
                if r.type in holds or (r.type == "PUMP" and tpl and tpl.equipment_release == "HORIZON"):
                    held.add(rid)
                elif t.end is not None and site is not None:
                    release[rid] = (max(release[rid][0], t.end), site.node)
    return release, held


def _solve_verified(p: OptProblem, travel: TravelTable, ctx: AreaContext, rt: ScenarioRuntime, cfg: EvalConfig,
                    fixed_specs: list[TaskSpec], time_limit: float, nogoods: list[set[str]], models: ModelCache
                    ) -> tuple[Solution | None, PlanEvaluation | None, int]:
    forced_off: set[str] = set()
    forbidden: set[tuple[str, str | None, str]] = set()
    fail_count: dict[str, int] = {}
    for it in range(1, MAX_REFINE + 1):
        sol = solve(p, travel, time_limit, get_settings().optimizer_workers, nogoods, forced_off, forbidden)
        if sol is None:
            return None, None, it
        specs = fixed_specs + sol.to_specs()
        ev = evaluate_plan(ctx, rt, specs, cfg, models)
        bad = [t for t in ev.tasks if t.status == "INFEASIBLE" and t.code in sol.selected]
        if not bad:
            return sol, ev, it
        by = {a.code: a for a in sol.assignments}
        for t in bad:
            a = by[t.code]
            fail_count[t.code] = fail_count.get(t.code, 0) + 1
            types = {i.type for i in t.issues}
            cand = next(c for c in p.candidates if c.code == t.code)
            if fail_count[t.code] >= 3 or not ({"NO_ROUTE", "MISSED_ACTION_WINDOW"} & types):
                forced_off.add(t.code)
            elif "NO_ROUTE" in types:
                forbidden.add((a.crew, a.prev, t.code))
            elif t.travel_min is not None and a.origin_node:
                travel.override[(a.origin_node, cand.site_node)] = math.ceil(t.travel_min) + 3
                if fail_count[t.code] >= 2:
                    forbidden.add((a.crew, a.prev, t.code))
    return None, None, MAX_REFINE


def _explain(ctx: AreaContext, p: OptProblem, travel: TravelTable, ev: PlanEvaluation, sol: Solution, values: dict,
             weights: dict, cfg: EvalConfig, rt: ScenarioRuntime, fixed_specs: list[TaskSpec], models: ModelCache) -> list[dict]:
    out = []
    ranked = sorted(p.candidates, key=lambda c: -c.value)
    rank_of = {c.code: i + 1 for i, c in enumerate(ranked)}
    by_task = ev.by_code
    for a in sorted(sol.assignments, key=lambda a: (a.departure, a.code)):
        c = next(x for x in p.candidates if x.code == a.code)
        vc = values.get(a.code)
        tr = by_task.get(a.code)
        tpl = ctx.templates[c.template_id]
        # WHY THIS RESOURCE: compare with other qualified crews
        others = []
        for crew in p.crews:
            if crew.id == a.crew or crew.subtype not in c.crew_types:
                continue
            rel_t, rel_node = p.release.get(crew.id, (p.as_of, None))
            if rel_node is None:
                continue
            tt = travel.tt(rel_node, c, rel_t)
            busy_with = next((x.code for x in sol.assignments if x.crew == crew.id), None)
            others.append({"crew": crew.id, "subtype": crew.subtype, "earliest_arrival": None if tt is None else rel_t + tt,
                           "assigned_to": busy_with})
        # WHY NOW: closures on the route
        route_closures = []
        m = models.get(tr.vehicle_class if tr else "STANDARD")
        for rid in (tr.route_roads if tr else []):
            first = min(m.closure_from(s, p.as_of) for s in ctx.roads[rid].segment_ids)
            if first <= rt.horizon_end:
                route_closures.append({"road": rid, "closes_at": finite_or_none(first)})
        # WHAT IF DELAYED: re-evaluate with the crew delayed beyond the tolerance
        slack_dep = (tr.latest_departure - a.departure) if tr and tr.latest_departure is not None else None
        consequence = None
        if slack_dep is not None and slack_dep < 600:
            delay = max(5.0, slack_dep + 10)
            dcfg = EvalConfig(access=cfg.access, as_of=cfg.as_of, delays=((a.crew, delay),), constraints=cfg.constraints,
                              label="delay")
            dev = evaluate_plan(ctx, rt, fixed_specs + sol.to_specs(), dcfg, models)
            dt = dev.by_code.get(a.code)
            if dt is not None:
                consequence = {"delay_min": round(delay), "status": dt.status,
                               "issues": sorted({i.type for i in dt.issues if i.blocking}),
                               "other_tasks_affected": [t.code for t in dev.tasks if t.status == "INFEASIBLE" and t.code != a.code]}
        out.append({
            "code": a.code, "template_id": a.template_id, "site_id": a.site_id, "crew": a.crew, "vehicle": a.vehicle,
            "pumps": a.pumps, "equipment": a.equipment, "departure": a.departure, "arrival": tr.arrival if tr else a.arrival,
            "end": tr.end if tr else a.end, "status": tr.status if tr else "UNKNOWN",
            "deadline": finite_or_none(c.deadline), "deadline_reason": c.deadline_reason,
            "latest_departure": tr.latest_departure if tr else None, "route_roads": tr.route_roads if tr else [],
            "route_segments": tr.route_segments if tr else [], "prev_task": a.prev,
            "why": {
                "task": {"value": round(c.value, 1), "rank": rank_of.get(a.code), "of": len(p.candidates),
                         "components": vc.as_dict() if vc else None, "weights": weights,
                         "benefit_share": BENEFIT_SHARE.get(tpl.action_type)},
                "resource": {"crew": a.crew, "qualified_types": c.crew_types, "alternatives": others,
                             "vehicle": a.vehicle, "vehicle_types": c.vehicle_types, "pumps": len(a.pumps)},
                "now": {"latest_departure": tr.latest_departure if tr else None, "route_closures": route_closures,
                        "deadline": finite_or_none(c.deadline), "deadline_reason": c.deadline_reason,
                        "slack_min": tr.slack_min if tr else None},
                "if_delayed": {"tolerance_min": finite_or_none(slack_dep) if slack_dep is not None else None,
                               "consequence": consequence},
            },
        })
    return out


def _diff(human: list[TaskSpec], alt: list[dict]) -> dict:
    h = {t.code: t for t in human}
    a = {t["code"]: t for t in alt}
    added = sorted(set(a) - set(h))
    removed = sorted(set(h) - set(a))
    reassigned, retimed = [], []
    for code in set(a) & set(h):
        hc = next((r for r in h[code].resource_ids if r.startswith(("C", "KC"))), None)
        if hc != a[code]["crew"]:
            reassigned.append({"task": code, "from": hc, "to": a[code]["crew"]})
        hd = h[code].planned_departure
        if hd is not None and abs(hd - a[code]["departure"]) >= 10:
            retimed.append({"task": code, "from": hd, "to": a[code]["departure"]})
    return {"added": added, "removed": removed, "reassigned": sorted(reassigned, key=lambda x: x["task"]),
            "retimed": sorted(retimed, key=lambda x: x["task"])}


def optimize(ctx: AreaContext, rt: ScenarioRuntime, as_of: float, *, policy: str, weights: dict | None,
             constraints: tuple[Constraint, ...], plan_specs: list[TaskSpec], extra_candidates: list[dict],
             unavailable: set[str] | None = None, extra_resources: list[ResourceInfo] | None = None,
             fixed_codes: set[str] | None = None, time_limit: float | None = None, max_alternatives: int | None = None,
             with_stress: bool = True, keep_human: bool = True) -> dict:
    t0 = time.time()
    s = get_settings()
    time_limit = time_limit or s.optimizer_time_limit_s
    max_alternatives = s.optimizer_max_alternatives if max_alternatives is None else max_alternatives
    ctx2 = with_resource_changes(ctx, unavailable or set(), extra_resources or [])
    w = normalise_weights(weights, policy)
    fixed_codes = fixed_codes or set()
    fixed_specs = [t for t in plan_specs if t.code in fixed_codes or t.status in ("DONE", "EN_ROUTE", "WORKING")]
    fixed_set = {t.code for t in fixed_specs}
    open_specs = [t for t in plan_specs if t.code not in fixed_set]
    raw = [c for c in candidate_list(open_specs, extra_candidates) if c["code"] not in fixed_set]
    model = build_access_model(ctx2, rt, AccessConfig(member=rt.member), now_min=as_of)
    comps = compute_values(ctx2, rt, model, raw)
    values = {k: v.score(w) for k, v in comps.items()}
    cands = build_candidates(ctx2, model, raw, values, as_of)
    cfg = EvalConfig(access=AccessConfig(member=rt.member), as_of=as_of, constraints=constraints, label="optimizer")
    models = ModelCache(ctx2, rt, cfg.access, as_of)
    fixed_eval = evaluate_plan(ctx2, rt, fixed_specs, cfg, models) if fixed_specs else None
    release, held = _release(ctx2, as_of, fixed_eval)
    busy = held
    human_assign = {t.code: set(t.resource_ids) for t in open_specs}
    p = OptProblem(ctx=ctx2, rt=rt, model=model, as_of=as_of, candidates=cands,
                   crews=_available(ctx2, "CREW", busy), vehicles=_available(ctx2, "VEHICLE", busy),
                   pumps=_available(ctx2, "PUMP", busy), equipment=_available(ctx2, "EQUIPMENT", busy),
                   release=release, constraints=constraints, human_assign=human_assign, keep_bonus=40,
                   horizon=int(rt.horizon_end))
    travel = TravelTable(model, cands, as_of)
    alternatives = []
    iterations_total = 0
    sol, ev, iters = _solve_verified(p, travel, ctx2, rt, cfg, fixed_specs, time_limit, [], models)
    iterations_total += iters
    if sol is not None and ev is not None:
        alternatives.append(("POLICY_OPTIMUM", sol, ev))

    def _distinct(s2: Solution) -> bool:
        return all(set(s2.selected) != set(x[1].selected)
                   or {a.code: (a.crew, a.departure // 15) for a in s2.assignments}
                   != {a.code: (a.crew, a.departure // 15) for a in x[1].assignments} for x in alternatives)

    if max_alternatives >= 2:
        sol, ev, iters = _solve_verified(replace(p, mode="ROBUST"), travel, ctx2, rt, cfg, fixed_specs, time_limit, [],
                                         models)
        iterations_total += iters
        if sol is not None and ev is not None and _distinct(sol):
            alternatives.append(("ROBUST_SLACK", sol, ev))
    if keep_human and max_alternatives >= 3 and open_specs:
        human_dep = {}
        for t in open_specs:
            if t.planned_departure is not None:
                human_dep[t.code] = t.planned_departure + 10
        p_keep = replace(p, keep_bonus=2500, mode="MINIMAL_CHANGE", human_departure=human_dep)
        sol, ev, iters = _solve_verified(p_keep, travel, ctx2, rt, cfg, fixed_specs, time_limit, [], models)
        iterations_total += iters
        if sol is not None and ev is not None and _distinct(sol):
            alternatives.append(("MINIMAL_CHANGE", sol, ev))

    out_alts = []
    for idx, (label, sol, ev) in enumerate(alternatives, start=1):
        tasks = _explain(ctx2, p, travel, ev, sol, comps, w, cfg, rt, fixed_specs, models)
        robustness = None
        if with_stress:
            st = run_stress_test(ctx2, rt, fixed_specs + sol.to_specs(), as_of, constraints)
            robustness = {"n_scenarios": st["n_scenarios"], "n_feasible": st["n_feasible"], "robustness": st["robustness"],
                          "task_criticality": st["task_criticality"][:5]}
        sel_comps = [comps[c] for c in sol.selected if c in comps]
        excluded = []
        for c in cands:
            if c.code in sol.selected:
                continue
            if c.latest_arrival != INF and c.latest_arrival < as_of:
                reason = "WINDOW_ALREADY_MISSED"
            elif c.pumps and c.pumps > len(p.pumps) - sum(x.pumps for x in cands if x.code in sol.selected):
                reason = "INSUFFICIENT_PUMPS"
            else:
                reason = "LOWER_VALUE_OR_NO_CAPACITY"
            excluded.append({"code": c.code, "template_id": c.template_id, "site_id": c.site_id, "value": round(c.value, 1),
                             "reason": reason})
        out_alts.append({
            "id": f"ALT-{idx}", "label": label, "tasks": tasks, "evaluation": ev.as_dict(),
            "metrics": {
                "tasks_selected": len(sol.selected), "tasks_feasible": sum(1 for t in ev.tasks if t.status != "INFEASIBLE"),
                "value_total": sol.value_total,
                "life": round(sum(c.life for c in sel_comps), 1), "infra": round(sum(c.infra for c in sel_comps), 1),
                "economic": round(sum(c.economic for c in sel_comps), 1),
                "high_priority_tasks": sorted(c.code for c in cands if c.code in sol.selected and c.value >= 50),
                "pumps_used": sum(len(a.pumps) for a in sol.assignments),
                "crews_used": len({a.crew for a in sol.assignments}),
                "min_slack": min((t.slack_min for t in ev.tasks if t.slack_min is not None), default=None),
            },
            "robustness": robustness,
            "excluded_candidates": excluded,
            "diff_vs_human": _diff(open_specs, tasks),
            "solver": {"status": sol.status, "solve_time_s": sol.solve_time_s, "objective": sol.objective},
            "specs": [t.__dict__ for t in fixed_specs + sol.to_specs()],
        })
    return {
        "policy": policy, "weights": w, "as_of": as_of, "member": rt.member, "scenario_id": rt.id,
        "alternatives": out_alts,
        "candidates": [{"code": c.code, "template_id": c.template_id, "site_id": c.site_id, "value": round(c.value, 1),
                        "latest_arrival": finite_or_none(c.latest_arrival), "deadline": finite_or_none(c.deadline),
                        "deadline_reason": c.deadline_reason, "components": comps[c.code].as_dict() if c.code in comps else None,
                        "origin": next((r["origin"] for r in raw if r["code"] == c.code), "CANDIDATE")}
                       for c in sorted(cands, key=lambda c: -c.value)],
        "resources": {"crews": len(p.crews), "vehicles": len(p.vehicles), "pumps": len(p.pumps), "equipment": len(p.equipment)},
        "fixed_tasks": sorted(fixed_set),
        "refinement_iterations": iterations_total,
        "duration_s": round(time.time() - t0, 2),
        "feasible": bool(out_alts),
        "methodology": {
            "objective": "maximise Σ value(task) − Σ completion time (min) + small bonus for keeping human assignments",
            "value": "value = Σ weight_k × component_k (life / infra / economic, each normalised 0–100 across candidates)",
            "verification": "every solution is re-simulated by the time-dependent plan evaluator; infeasible arcs are "
                            "corrected or forbidden and the model re-solved",
            "solver": "Google OR-Tools CP-SAT",
        },
    }
