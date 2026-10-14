"""Deterministic plan evaluator.

Simulates a human response plan task-by-task on the time-dependent road graph:
resource availability and capability → departure → route (earliest arrival) → setup / execution →
action-window deadline → slack. Every failure is recorded as a typed Issue so the causality module
can explain *why* it happened. The same evaluator verifies optimizer output and powers the
stress tester and the operations health monitor (single source of truth).
"""

from __future__ import annotations

from collections import defaultdict

from app.core.config import get_settings
from app.repositories.context import AreaContext
from app.services.deadlines.windows import site_deadline, task_window
from app.services.planning.model import Constraint, EvalConfig, Issue, PlanEvaluation, TaskResult, TaskSpec
from app.services.routing.access import AccessConfig, AccessModel, build_access_model
from app.services.routing.intervals import INF, finite_or_none
from app.services.scenario.runtime import ScenarioRuntime

MOBILE_TYPES = ("CREW", "VEHICLE", "EQUIPMENT")


class ModelCache:
    """Access models per vehicle class for one evaluation configuration."""

    def __init__(self, ctx: AreaContext, rt: ScenarioRuntime, cfg: AccessConfig, now: float):
        self.ctx, self.rt, self.cfg, self.now = ctx, rt, cfg, now
        self._m: dict[str, AccessModel] = {}

    def get(self, vehicle_class: str = "STANDARD") -> AccessModel:
        if vehicle_class not in self._m:
            cfg = AccessConfig(**{**self.cfg.__dict__, "vehicle_class": vehicle_class})
            self._m[vehicle_class] = build_access_model(self.ctx, self.rt, cfg, now_min=self.now)
        return self._m[vehicle_class]


def order_tasks(tasks: list[TaskSpec], as_of: float) -> list[TaskSpec]:
    by = {t.code: t for t in tasks}
    indeg = {t.code: 0 for t in tasks}
    for t in tasks:
        for d in t.dependencies:
            if d in by:
                indeg[t.code] += 1
    ready = [t for t in tasks if indeg[t.code] == 0]
    out: list[TaskSpec] = []

    def key(t: TaskSpec) -> tuple:
        return (t.planned_departure if t.planned_departure is not None else as_of, t.sort_order, t.code)

    while ready:
        ready.sort(key=key)
        t = ready.pop(0)
        out.append(t)
        for u in tasks:
            if t.code in u.dependencies:
                indeg[u.code] -= 1
                if indeg[u.code] == 0:
                    ready.append(u)
    # cycles: append remaining in planned order
    rest = [t for t in tasks if t not in out]
    return out + sorted(rest, key=key)


def _capability_issues(ctx: AreaContext, tpl, resource_ids: list[str]) -> list[Issue]:  # type: ignore[no-untyped-def]
    res = [ctx.resources[r] for r in resource_ids if r in ctx.resources]
    req = tpl.requirements or {}
    issues = []
    crew_req = req.get("crew") or {}
    if crew_req:
        n = sum(1 for r in res if r.type == "CREW" and r.subtype in crew_req.get("types", []))
        if n < int(crew_req.get("count", 1)):
            issues.append(Issue("CAPABILITY_MISSING", True, {"kind": "CREW", "types": crew_req.get("types", []),
                                                               "required": crew_req.get("count", 1), "assigned": n}))
    veh_req = req.get("vehicle") or {}
    if veh_req:
        n = sum(1 for r in res if r.type == "VEHICLE" and r.subtype in veh_req.get("types", []))
        if n < int(veh_req.get("count", 1)):
            issues.append(Issue("CAPABILITY_MISSING", True, {"kind": "VEHICLE", "types": veh_req.get("types", []),
                                                               "required": veh_req.get("count", 1), "assigned": n}))
    pumps = int(req.get("pumps", 0) or 0)
    if pumps:
        n = sum(1 for r in res if r.type == "PUMP")
        if n < pumps:
            issues.append(Issue("CAPABILITY_MISSING", True, {"kind": "PUMP", "required": pumps, "assigned": n}))
    for sub, cnt in (req.get("equipment") or {}).items():
        n = sum(1 for r in res if r.type == "EQUIPMENT" and r.subtype == sub)
        if n < int(cnt):
            issues.append(Issue("CAPABILITY_MISSING", True, {"kind": "EQUIPMENT", "types": [sub], "required": cnt,
                                                               "assigned": n}))
    return issues


def _constraint_issues(ctx: AreaContext, task: TaskSpec, constraints: tuple[Constraint, ...]) -> list[Issue]:
    site = ctx.sites.get(task.site_id)
    out = []
    for c in constraints:
        if c.kind == "FORBID_RESOURCE_SECTOR" and c.resource_id in task.resource_ids and site and site.sector == c.sector:
            out.append(Issue("CONSTRAINT_VIOLATION", True, {"constraint": c.as_dict()}))
        if c.kind == "FORBID_RESOURCE_TASK" and c.resource_id in task.resource_ids and c.task_code == task.code:
            out.append(Issue("CONSTRAINT_VIOLATION", True, {"constraint": c.as_dict()}))
        if c.kind == "EXCLUDE_TASK" and c.task_code == task.code:
            out.append(Issue("CONSTRAINT_VIOLATION", True, {"constraint": c.as_dict()}))
    return out


def evaluate_plan(ctx: AreaContext, rt: ScenarioRuntime, tasks: list[TaskSpec], cfg: EvalConfig,
                  models: ModelCache | None = None) -> PlanEvaluation:
    s = get_settings()
    models = models or ModelCache(ctx, rt, cfg.access, cfg.as_of)
    as_of = cfg.as_of
    delays = dict(cfg.delays)
    delay_used: set[str] = set()
    free_at: dict[str, float] = {}
    loc: dict[str, str | None] = {}
    for rid, r in ctx.resources.items():
        start = as_of
        if r.available_from is not None:
            start = max(start, (r.available_from - rt.reference_time).total_seconds() / 60)
        free_at[rid] = start
        base = ctx.bases.get(r.base or "")
        loc[rid] = base.node if base else None
    held_forever: dict[str, str] = {}  # resource → task code holding it until the horizon
    results: list[TaskResult] = []
    end_of: dict[str, float | None] = {}
    failed: set[str] = set()
    conflicts: list[dict] = []

    for task in order_tasks(tasks, as_of):
        tpl = ctx.templates.get(task.template_id)
        site = ctx.sites.get(task.site_id)
        tr = TaskResult(task.code, task.template_id, task.site_id, list(task.resource_ids), "FEASIBLE", [],
                        planned_departure=task.planned_departure)
        if tpl is None or site is None:
            tr.status = "INFEASIBLE"
            tr.issues.append(Issue("UNKNOWN_TEMPLATE_OR_SITE", True, {"template": task.template_id, "site": task.site_id}))
            results.append(tr)
            failed.add(task.code)
            end_of[task.code] = None
            continue
        res_objs = [ctx.resources[r] for r in task.resource_ids if r in ctx.resources]
        crew = next((r for r in res_objs if r.type == "CREW"), None)
        tr.crew_id = crew.id if crew else None
        vehicles = [r for r in res_objs if r.type == "VEHICLE"]
        tr.vehicle_class = "HIGH_CLEARANCE" if vehicles and all(v.subtype == "HIGH_CLEARANCE" for v in vehicles) else "STANDARD"
        model = models.get(tr.vehicle_class)
        holds = set((tpl.constraints or {}).get("holds", []))

        # ---- operations state: completed / in progress tasks are facts, not predictions
        if task.status == "DONE":
            tr.status = "DONE"
            tr.end = task.completed_at if task.completed_at is not None else as_of
            end_of[task.code] = tr.end
            for r in res_objs:
                if r.type in holds and tpl.equipment_release == "HORIZON":
                    held_forever[r.id] = task.code
                else:
                    free_at[r.id] = max(free_at.get(r.id, as_of), tr.end)
                    loc[r.id] = site.node
            results.append(tr)
            continue

        for rid in task.resource_ids:
            if rid not in ctx.resources:
                tr.issues.append(Issue("UNKNOWN_RESOURCE", True, {"resource": rid}))
        for r in res_objs:
            if r.status in ("UNAVAILABLE", "FAILED") or r.id in cfg.unavailable:
                tr.issues.append(Issue("RESOURCE_UNAVAILABLE", True, {"resource": r.id, "status": r.status if r.id not in cfg.unavailable else "PERTURBATION"}))
            if r.id in held_forever:
                tr.issues.append(Issue("RESOURCE_CONFLICT", True, {"resource": r.id, "held_by": held_forever[r.id]}))
                conflicts.append({"resource": r.id, "tasks": [held_forever[r.id], task.code], "kind": "DOUBLE_BOOKED"})
        tr.issues.extend(_capability_issues(ctx, tpl, task.resource_ids))
        tr.issues.extend(_constraint_issues(ctx, task, cfg.constraints))
        for d in task.dependencies:
            if d in failed:
                tr.issues.append(Issue("DEPENDENCY_FAILED", True, {"task": d}))

        # ---- departure time
        ready = as_of
        mobile = [r for r in res_objs if r.type in MOBILE_TYPES]
        for r in mobile:
            ready = max(ready, free_at.get(r.id, as_of))
        for d in task.dependencies:
            e = end_of.get(d)
            if e is not None:
                ready = max(ready, e)
        if task.status in ("EN_ROUTE", "WORKING") and task.actual_departure is not None:
            dep = task.actual_departure
        else:
            dep = task.planned_departure if task.planned_departure is not None else ready
            if dep < as_of and task.status == "PENDING":
                tr.issues.append(Issue("DEPARTURE_OVERDUE", False, {"planned": dep, "as_of": as_of}))
                dep = as_of
            if dep < ready - 0.5:
                busy = [r.id for r in mobile if free_at.get(r.id, as_of) > dep + 0.5]
                if busy:
                    tr.issues.append(Issue("RESOURCE_CONFLICT", False, {"resources": busy, "planned": dep, "free_at": ready}))
                    conflicts.append({"resource": busy[0], "tasks": [task.code], "kind": "BUSY_AT_PLANNED_TIME",
                                      "planned": dep, "free_at": ready})
                dep = ready
            if crew and crew.id in delays and crew.id not in delay_used:
                dep += delays[crew.id]
                delay_used.add(crew.id)
                tr.issues.append(Issue("CREW_DELAYED", False, {"resource": crew.id, "minutes": delays[crew.id]}))
            if crew and crew.delay_min and crew.id not in delay_used:
                dep += crew.delay_min
                delay_used.add(crew.id)
                tr.issues.append(Issue("CREW_DELAYED", False, {"resource": crew.id, "minutes": crew.delay_min,
                                                               "source": "OPERATIONAL_STATUS"}))
        tr.departure = dep
        origin = loc.get(crew.id) if crew else (loc.get(mobile[0].id) if mobile else None)
        tr.origin_node = origin

        # ---- action window (independent of the plan's own timing)
        dl = site_deadline(model, site, tpl, as_of)
        tr.deadline = finite_or_none(dl.deadline)
        tr.deadline_reason = dl.reason
        tr.deadline_components = {k: finite_or_none(v) for k, v in dl.components.items()}
        win = task_window(model, task.code, tpl, site, origin, as_of, dl)
        tr.latest_departure = win.latest_departure
        tr.latest_route_roads = win.route_roads
        tr.window_status = win.status

        blocking = any(i.blocking for i in tr.issues)
        if origin is None:
            tr.issues.append(Issue("NO_ORIGIN", True, {}))
            blocking = True
        if not blocking and task.status == "WORKING" and task.actual_start is not None:
            tr.arrival = task.actual_start - tpl.setup_min
            tr.start = task.actual_start
            tr.end = task.actual_start + tpl.execution_min
        elif not blocking:
            arr, pred = model.earliest_arrival(origin, dep)
            if site.node not in arr:
                tr.issues.append(Issue("NO_ROUTE", True, {"from": origin, "to": site.node, "departure": dep,
                                                          "blocking_segments": _blocking_segments(model, origin, site.node, dep)}))
            else:
                segs = model.path_from_pred(pred, site.node)
                tr.route_segments = segs
                tr.route_roads = _roads_of(ctx, segs)
                tr.route_timeline = model.route_timeline(origin, segs, dep)
                tr.arrival = arr[site.node] + site.access_min
                tr.travel_min = tr.arrival - dep
                tr.start = tr.arrival + tpl.setup_min
                tr.end = tr.start + tpl.execution_min
        if tr.end is not None and dl.deadline != INF:
            slack = dl.deadline - tpl.safety_buffer_min - tr.end
            tr.slack_min = slack
            if slack < 0:
                tr.issues.append(Issue("MISSED_ACTION_WINDOW", True, {
                    "completion": tr.end, "deadline": dl.deadline, "buffer": tpl.safety_buffer_min,
                    "late_by_min": -slack, "deadline_reason": dl.reason}))
            elif slack < s.task_at_risk_slack_min:
                tr.issues.append(Issue("LOW_SLACK", False, {"slack_min": slack}))

        if any(i.blocking for i in tr.issues):
            tr.status = "INFEASIBLE"
            failed.add(task.code)
            end_of[task.code] = None
        else:
            tr.status = "AT_RISK" if any(i.type in ("LOW_SLACK", "RESOURCE_CONFLICT", "DEPARTURE_OVERDUE") for i in tr.issues) else "FEASIBLE"
            if task.status in ("EN_ROUTE", "WORKING"):
                tr.status = "IN_PROGRESS" if tr.status == "FEASIBLE" else tr.status
            end_of[task.code] = tr.end
            for r in res_objs:
                if r.type in holds and tpl.equipment_release == "HORIZON" or r.type == "PUMP" and tpl.equipment_release == "HORIZON":
                    held_forever[r.id] = task.code
                else:
                    free_at[r.id] = tr.end if tr.end is not None else free_at.get(r.id, as_of)
                    loc[r.id] = site.node
        results.append(tr)

    order = {t.code: i for i, t in enumerate(sorted(tasks, key=lambda t: (t.sort_order, t.code)))}
    results.sort(key=lambda r: order.get(r.code, 999))
    if any(r.status == "INFEASIBLE" for r in results):
        status = "INFEASIBLE"
    elif any(r.status == "AT_RISK" for r in results):
        status = "AT_RISK"
    else:
        status = "FEASIBLE"
    return PlanEvaluation(status, results, cfg.label, cfg.access.member, as_of, conflicts)


def _roads_of(ctx: AreaContext, segs: list[str]) -> list[str]:
    roads: list[str] = []
    for s in segs:
        r = ctx.segments[s].road_id
        if not roads or roads[-1] != r:
            roads.append(r)
    return roads


def _blocking_segments(model: AccessModel, origin: str, target: str, dep: float) -> list[dict]:
    """Segments on the free-flow shortest path that are closed when the crew would reach them."""
    import heapq

    dist = {origin: 0.0}
    pred: dict[str, tuple[str, str]] = {}
    heap = [(0.0, origin)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, INF):
            continue
        for seg, v in model.ctx.adjacency.get(u, []):
            nd = d + model.free_flow_time(seg)
            if nd < dist.get(v, INF):
                dist[v] = nd
                pred[v] = (seg, u)
                heapq.heappush(heap, (nd, v))
    if target not in dist:
        return []
    path = model.path_from_pred(pred, target)
    out = []
    t = dep
    seen_roads: set[str] = set()
    for seg in path:
        tt = model.free_flow_time(seg)
        if model.state_at(seg, t) == "CLOSED" or model.closure_from(seg, t) < t + tt:
            rid = model.ctx.segments[seg].road_id
            if rid not in seen_roads:
                seen_roads.add(rid)
                e = model.edges[seg]
                out.append({"segment_id": seg, "road_id": rid, "closed_from": finite_or_none(model.closure_from(seg, model.now)),
                            "reach_time": t, "override": e.override})
        t += tt
    return out


def resource_timeline(ev: PlanEvaluation) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for t in ev.tasks:
        for r in t.resource_ids:
            out[r].append({"task": t.code, "departure": t.departure, "end": t.end, "status": t.status})
    return dict(out)
