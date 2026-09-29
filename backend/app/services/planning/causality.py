"""Causal failure chains.

Compares a task's evaluation under a *reference* configuration (e.g. the scenario the plan was
approved against, or the unperturbed baseline) with a *current / perturbed* configuration and
explains the difference as a chain of typed, translatable nodes, e.g.::

    SCENARIO_CHANGED → ROAD_CLOSES_EARLIER(R7, 16:40→14:00) → RESOURCE_LOSES_ACCESS(C3) → TASK_MISSES_WINDOW(T8)

Node ``type`` values map to i18n keys ``causal.<TYPE>`` in the frontend.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.repositories.context import AreaContext
from app.services.planning.model import EvalConfig, PlanEvaluation, TaskResult
from app.services.routing.access import AccessModel
from app.services.routing.intervals import INF, finite_or_none

SIGNIFICANT_SHIFT_MIN = 10.0


@dataclass
class ChainNode:
    type: str
    params: dict = field(default_factory=dict)
    severity: str = "info"  # info | warning | critical


@dataclass
class CausalChain:
    task: str
    outcome: str
    nodes: list[ChainNode]
    headline: ChainNode | None = None

    def as_dict(self) -> dict:
        return {"task": self.task, "outcome": self.outcome, "nodes": [asdict(n) for n in self.nodes],
                "headline": asdict(self.headline) if self.headline else None}


def _terminal(t: TaskResult) -> ChainNode:
    types = {i.type for i in t.issues}
    if "NO_ROUTE" in types and t.deadline is not None and t.departure is not None and t.departure > (t.deadline or INF):
        return ChainNode("TASK_MISSES_WINDOW", {"task": t.code, "deadline": t.deadline, "departure": t.departure,
                                                 "latest_departure": t.latest_departure}, "critical")
    if "NO_ROUTE" in types:
        return ChainNode("TASK_NO_ROUTE", {"task": t.code, "departure": t.departure, "latest_departure": t.latest_departure,
                                            "deadline": t.deadline}, "critical")
    if "MISSED_ACTION_WINDOW" in types:
        i = next(i for i in t.issues if i.type == "MISSED_ACTION_WINDOW")
        return ChainNode("TASK_MISSES_WINDOW", {"task": t.code, "completion": i.params["completion"],
                                                 "deadline": i.params["deadline"], "late_by_min": round(i.params["late_by_min"]),
                                                 "latest_departure": t.latest_departure}, "critical")
    if "RESOURCE_UNAVAILABLE" in types or "CAPABILITY_MISSING" in types:
        return ChainNode("TASK_LACKS_RESOURCES", {"task": t.code}, "critical")
    if "DEPENDENCY_FAILED" in types:
        return ChainNode("TASK_BLOCKED_BY_DEPENDENCY", {"task": t.code}, "critical")
    if "RESOURCE_CONFLICT" in types and t.status == "INFEASIBLE":
        return ChainNode("TASK_RESOURCE_CONFLICT", {"task": t.code}, "critical")
    if "CONSTRAINT_VIOLATION" in types:
        return ChainNode("TASK_VIOLATES_CONSTRAINT", {"task": t.code}, "critical")
    if t.status == "AT_RISK":
        return ChainNode("TASK_AT_RISK", {"task": t.code, "slack_min": None if t.slack_min is None else round(t.slack_min)},
                         "warning")
    return ChainNode("TASK_FAILS", {"task": t.code}, "critical")


def _road_closure_changes(ref_m: AccessModel | None, cur_m: AccessModel, segs: list[str], t_from: float,
                          traverse: dict[str, float]) -> list[ChainNode]:
    nodes: list[ChainNode] = []
    seen: set[str] = set()
    for sid in segs:
        rid = cur_m.ctx.segments[sid].road_id
        if rid in seen:
            continue
        cur_c = cur_m.closure_from(sid, t_from)
        e = cur_m.edges[sid]
        when = traverse.get(sid, t_from)
        if e.override and e.override.get("state") == "CLOSED":
            seen.add(rid)
            nodes.append(ChainNode("ROAD_CLOSED_FIELD", {"road": rid, "segment": sid, "source": e.override.get("source"),
                                                         "verification": e.override.get("verification"),
                                                         "effective_from": e.override.get("effective_from")}, "critical"))
            continue
        if e.override and e.override.get("source") == "WHAT_IF":
            seen.add(rid)
            nodes.append(ChainNode("ROAD_UNAVAILABLE_ASSUMED", {"road": rid, "segment": sid}, "critical"))
            continue
        ref_c = ref_m.closure_from(sid, t_from) if ref_m is not None else INF
        if cur_c < ref_c - SIGNIFICANT_SHIFT_MIN and cur_c <= when + 1:
            seen.add(rid)
            nodes.append(ChainNode("ROAD_CLOSES_EARLIER", {"road": rid, "segment": sid, "from": finite_or_none(ref_c),
                                                           "to": finite_or_none(cur_c)}, "critical"))
        elif ref_m is None and cur_c <= when + 1:
            seen.add(rid)
            nodes.append(ChainNode("ROAD_CLOSED_AT", {"road": rid, "segment": sid, "at": finite_or_none(cur_c)}, "critical"))
    return nodes


def explain_task(ctx: AreaContext, cur: TaskResult, ref: TaskResult | None, cur_m: AccessModel, ref_m: AccessModel | None,
                 cur_cfg: EvalConfig, ref_cfg: EvalConfig | None, root: list[ChainNode]) -> CausalChain:
    nodes: list[ChainNode] = list(root)
    types = {i.type: i for i in cur.issues}
    t_from = cur_cfg.as_of

    # resource-level root causes
    for i in cur.issues:
        if i.type == "RESOURCE_UNAVAILABLE":
            nodes.append(ChainNode("RESOURCE_UNAVAILABLE", {"resource": i.params["resource"], "status": i.params.get("status")},
                                   "critical"))
        elif i.type == "CREW_DELAYED":
            nodes.append(ChainNode("CREW_DELAYED", {"resource": i.params["resource"], "minutes": i.params["minutes"]}, "warning"))
        elif i.type == "DEPENDENCY_FAILED":
            nodes.append(ChainNode("DEPENDENCY_FAILED", {"task": i.params["task"]}, "critical"))
        elif i.type == "CAPABILITY_MISSING":
            nodes.append(ChainNode("CAPABILITY_MISSING", i.params, "critical"))
        elif i.type == "CONSTRAINT_VIOLATION":
            nodes.append(ChainNode("CONSTRAINT_VIOLATION", i.params, "critical"))
        elif i.type == "RESOURCE_CONFLICT":
            nodes.append(ChainNode("RESOURCE_CONFLICT", i.params, "warning" if not i.blocking else "critical"))

    # route-level: which roads broke the reference route?
    ref_segs = ref.route_segments if ref and ref.route_segments else []
    traverse = {step["segment_id"]: step["enter"] for step in (ref.route_timeline if ref else [])}
    if "NO_ROUTE" in types:
        blocking = types["NO_ROUTE"].params.get("blocking_segments", [])
        segs = ref_segs or [b["segment_id"] for b in blocking]
        if not traverse:
            traverse = {b["segment_id"]: b["reach_time"] for b in blocking}
        # evaluate traversal at the *current* departure time
        shift = (cur.departure or t_from) - (ref.departure if ref and ref.departure is not None else (cur.departure or t_from))
        traverse = {k: v + shift for k, v in traverse.items()}
        nodes.extend(_road_closure_changes(ref_m, cur_m, segs, t_from, traverse))
        crew = cur.crew_id or (cur.resource_ids[0] if cur.resource_ids else None)
        nodes.append(ChainNode("RESOURCE_LOSES_ACCESS", {"resource": crew, "site": cur.site_id, "at": cur.departure}, "critical"))
    elif "MISSED_ACTION_WINDOW" in types or cur.status == "AT_RISK":
        if ref and ref.deadline is not None and cur.deadline is not None and cur.deadline < ref.deadline - SIGNIFICANT_SHIFT_MIN:
            key = {"SITE_FLOODED": "SITE_FLOODS_EARLIER", "EGRESS_LOST": "ACCESS_LOST_EARLIER",
                   "PROTECTED_ROAD_CLOSES": "PROTECTED_ROAD_CLOSES_EARLIER"}.get(cur.deadline_reason, "DEADLINE_EARLIER")
            nodes.append(ChainNode(key, {"site": cur.site_id, "from": ref.deadline, "to": cur.deadline}, "critical"))
        elif ref is None or ref.deadline is None:
            if cur.deadline is not None:
                key = {"SITE_FLOODED": "SITE_FLOODS_AT", "EGRESS_LOST": "ACCESS_LOST_AT",
                       "PROTECTED_ROAD_CLOSES": "PROTECTED_ROAD_CLOSES_AT"}.get(cur.deadline_reason, "DEADLINE_AT")
                nodes.append(ChainNode(key, {"site": cur.site_id, "at": cur.deadline}, "warning"))
        if ref and ref.arrival is not None and cur.arrival is not None and cur.arrival > ref.arrival + 5:
            changed = _road_closure_changes(ref_m, cur_m, ref_segs, t_from, traverse)
            nodes.extend(changed)
            nodes.append(ChainNode("DETOUR", {"resource": cur.crew_id, "extra_min": round(cur.arrival - ref.arrival),
                                              "roads": cur.route_roads}, "warning"))
    nodes.append(_terminal(cur))
    headline = next((n for n in nodes if n.type in ("ROAD_CLOSES_EARLIER", "ROAD_CLOSED_FIELD", "ROAD_UNAVAILABLE_ASSUMED",
                                                     "SITE_FLOODS_EARLIER", "ACCESS_LOST_EARLIER", "RESOURCE_UNAVAILABLE",
                                                     "CREW_DELAYED")), None)
    return CausalChain(cur.code, cur.status, _dedupe(nodes), headline)


def _dedupe(nodes: list[ChainNode]) -> list[ChainNode]:
    out: list[ChainNode] = []
    seen = set()
    for n in nodes:
        k = (n.type, tuple(sorted((k, str(v)) for k, v in n.params.items() if k in ("road", "resource", "task", "site"))))
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


def root_nodes(ref_cfg: EvalConfig | None, cur_cfg: EvalConfig, ref_scenario: tuple[str, int] | None,
               cur_scenario: tuple[str, int]) -> list[ChainNode]:
    """Configuration-level differences (scenario / perturbation) that start every chain."""
    nodes: list[ChainNode] = []
    if ref_cfg is not None:
        if ref_scenario and (ref_scenario != cur_scenario or ref_cfg.access.member != cur_cfg.access.member):
            nodes.append(ChainNode("SCENARIO_CHANGED", {"from_member": ref_cfg.access.member, "to_member": cur_cfg.access.member,
                                                        "from_version": ref_scenario[1], "to_version": cur_scenario[1]},
                                   "warning"))
        elif ref_cfg.access.member != cur_cfg.access.member:
            nodes.append(ChainNode("HIGHER_WATER_LEVEL", {"from_member": ref_cfg.access.member,
                                                          "to_member": cur_cfg.access.member}, "warning"))
    if cur_cfg.access.time_shift_min:
        nodes.append(ChainNode("EARLIER_PEAK", {"minutes": cur_cfg.access.time_shift_min}, "warning"))
    for rid, mins in cur_cfg.access.road_advance_min:
        nodes.append(ChainNode("ROAD_CLOSURE_ADVANCED", {"road": rid, "minutes": mins}, "warning"))
    return nodes


def explain_evaluation(ctx: AreaContext, cur: PlanEvaluation, ref: PlanEvaluation | None, cur_m: AccessModel,
                       ref_m: AccessModel | None, cur_cfg: EvalConfig, ref_cfg: EvalConfig | None,
                       ref_scenario: tuple[str, int] | None, cur_scenario: tuple[str, int],
                       include_at_risk: bool = True) -> list[CausalChain]:
    root = root_nodes(ref_cfg, cur_cfg, ref_scenario, cur_scenario)
    chains = []
    ref_by = ref.by_code if ref else {}
    for t in cur.tasks:
        if t.status == "INFEASIBLE" or (include_at_risk and t.status == "AT_RISK"):
            r = ref_by.get(t.code)
            if r is not None and r.status == t.status and t.status == "AT_RISK":
                continue  # unchanged low-slack condition is not news
            chains.append(explain_task(ctx, t, r, cur_m, ref_m, cur_cfg, ref_cfg, root))
    chains.sort(key=lambda c: (c.outcome != "INFEASIBLE", c.task))
    return chains
