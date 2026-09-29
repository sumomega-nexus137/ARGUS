"""RESOURCE GAP — marginal resource analysis (part of Module 4).

Re-runs the optimizer (policy optimum only) with one extra unit of each resource kind and reports
the computed operational improvement, e.g. "one additional crew allows two additional high-priority
tasks to finish before their action windows close". Every statement is derived from actual runs.
"""

from __future__ import annotations

import time

from app.repositories.context import AreaContext, ResourceInfo
from app.services.optimization.alternatives import optimize
from app.services.planning.model import Constraint, TaskSpec
from app.services.scenario.runtime import ScenarioRuntime

OPTIONS = [
    ("CREW", "ENGINEERING", 1),
    ("CREW", "GENERAL", 1),
    ("CREW", "RESCUE", 1),
    ("PUMP", "MOBILE_PUMP", 1),
    ("PUMP", "MOBILE_PUMP", 2),
    ("VEHICLE", "TRUCK", 1),
    ("VEHICLE", "HIGH_CLEARANCE", 1),
    ("EQUIPMENT", "SANDBAG_FILLER", 1),
]


def _virtual(ctx: AreaContext, rtype: str, subtype: str, n: int) -> list[ResourceInfo]:
    base = next(iter(ctx.bases.values())).id if ctx.bases else None
    return [ResourceInfo(f"+{subtype[:3]}{i + 1}", rtype, subtype, base, None, None, "AVAILABLE", 0, None,
                         {"en": f"Additional {subtype.lower()} (what-if)"}, "WHAT_IF") for i in range(n)]


def resource_gap(ctx: AreaContext, rt: ScenarioRuntime, as_of: float, *, policy: str, weights: dict | None,
                 constraints: tuple[Constraint, ...], plan_specs: list[TaskSpec], extra_candidates: list[dict],
                 unavailable: set[str] | None = None, time_limit: float = 2.0) -> dict:
    t0 = time.time()
    kw = dict(policy=policy, weights=weights, constraints=constraints, plan_specs=plan_specs,
              extra_candidates=extra_candidates, unavailable=unavailable or set(), time_limit=time_limit,
              max_alternatives=1, with_stress=False, keep_human=False)
    base = optimize(ctx, rt, as_of, **kw)
    if not base["alternatives"]:
        return {"feasible": False, "options": [], "duration_s": round(time.time() - t0, 2)}
    b = base["alternatives"][0]
    b_sel = {t["code"] for t in b["tasks"]}
    values = {c["code"]: c["value"] for c in base["candidates"]}
    rows = []
    present_subtypes = {(r.type, r.subtype) for r in ctx.resources.values()}
    for rtype, sub, n in OPTIONS:
        if (rtype, sub) not in present_subtypes:
            continue
        res = optimize(ctx, rt, as_of, extra_resources=_virtual(ctx, rtype, sub, n), **kw)
        if not res["alternatives"]:
            continue
        a = res["alternatives"][0]
        sel = {t["code"] for t in a["tasks"]}
        added = sorted(sel - b_sel, key=lambda c: -values.get(c, 0))
        removed = sorted(b_sel - sel)
        hp_added = [c for c in added if values.get(c, 0) >= 50]
        slack_gain = None
        if a["metrics"]["min_slack"] is not None and b["metrics"]["min_slack"] is not None:
            slack_gain = round(a["metrics"]["min_slack"] - b["metrics"]["min_slack"], 1)
        rows.append({
            "resource_type": rtype, "subtype": sub, "count": n,
            "tasks_before": len(b_sel), "tasks_after": len(sel), "delta_tasks": len(sel) - len(b_sel),
            "value_before": b["metrics"]["value_total"], "value_after": a["metrics"]["value_total"],
            "delta_value": round(a["metrics"]["value_total"] - b["metrics"]["value_total"], 1),
            "tasks_added": added, "tasks_removed": removed, "high_priority_added": hp_added,
            "min_slack_gain_min": slack_gain,
            "statement": {"key": "gap.statement", "params": {"count": n, "type": rtype, "subtype": sub,
                                                              "n_tasks": len(sel) - len(b_sel), "n_high": len(hp_added),
                                                              "tasks": added}},
        })
    rows.sort(key=lambda r: (-r["delta_value"], -r["delta_tasks"]))
    return {"feasible": True, "policy": policy, "weights": base["weights"], "baseline": {
        "tasks": sorted(b_sel), "value_total": b["metrics"]["value_total"], "min_slack": b["metrics"]["min_slack"]},
        "options": rows, "duration_s": round(time.time() - t0, 2),
        "methodology": "Each option adds virtual resource units at the primary base and re-runs the CP-SAT policy "
                       "optimum with the same scenario, constraints and weights. Deltas are computed, not estimated."}
