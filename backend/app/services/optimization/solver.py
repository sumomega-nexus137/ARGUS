"""CP-SAT scheduling model (Google OR-Tools).

Decision: which approved candidate tasks to perform, with which crew / vehicle / pumps / equipment,
in which order and when — maximising the human-weighted value of tasks completed before their action
windows close.

Time-dependency is handled by (1) latest-departure bounds from the reverse time-dependent search,
(2) travel times from time-dependent earliest-arrival searches, and (3) an optimize → verify → refine
loop: every solution is re-simulated by the exact plan evaluator; violated arcs get corrected travel
times (or are forbidden) and the model is re-solved.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from app.repositories.context import AreaContext, ResourceInfo
from app.services.deadlines.windows import site_deadline
from app.services.planning.model import Constraint, TaskSpec
from app.services.routing.access import AccessModel
from app.services.routing.intervals import INF
from app.services.scenario.runtime import ScenarioRuntime

BIG = 10**6
MARGIN_MIN = 20  # schedule margin before a window closes in ROBUST / MINIMAL_CHANGE modes


@dataclass
class Candidate:
    code: str
    template_id: str
    site_id: str
    value: float  # weighted 0–100
    work: int
    setup: int
    execution: int
    buffer: int
    pumps: int
    crew_types: list[str]
    vehicle_types: list[str]
    equipment: dict[str, int]
    holds: set[str]
    release_horizon: bool
    latest_arrival: float  # minutes (INF = none)
    deadline: float
    deadline_reason: str
    site_node: str
    access_min: float
    sector: str | None


@dataclass
class OptProblem:
    ctx: AreaContext
    rt: ScenarioRuntime
    model: AccessModel
    as_of: float
    candidates: list[Candidate]
    crews: list[ResourceInfo]
    vehicles: list[ResourceInfo]
    pumps: list[ResourceInfo]
    equipment: list[ResourceInfo]
    release: dict[str, tuple[float, str | None]]  # resource → (time, node)
    constraints: tuple[Constraint, ...] = ()
    human_assign: dict[str, set[str]] = field(default_factory=dict)
    human_departure: dict[str, float] = field(default_factory=dict)
    keep_bonus: int = 0
    horizon: int = 1080
    mode: str = "VALUE"  # VALUE | ROBUST | MINIMAL_CHANGE


@dataclass
class Assignment:
    code: str
    template_id: str
    site_id: str
    crew: str
    vehicle: str | None
    pumps: list[str]
    equipment: list[str]
    arrival: int
    end: int
    departure: int
    prev: str | None  # previous task code for the crew (None → from base)
    origin_node: str | None


@dataclass
class Solution:
    status: str
    objective: float
    assignments: list[Assignment]
    selected: list[str]
    solve_time_s: float
    value_total: float

    def to_specs(self) -> list[TaskSpec]:
        out = []
        for i, a in enumerate(sorted(self.assignments, key=lambda a: (a.departure, a.code))):
            res = [a.crew] + ([a.vehicle] if a.vehicle else []) + a.pumps + a.equipment
            out.append(TaskSpec(a.code, a.template_id, a.site_id, res, float(a.departure), [], sort_order=i))
        return out


class TravelTable:
    """Travel times / latest departures between origins and candidate sites (minutes)."""

    def __init__(self, model: AccessModel, candidates: list[Candidate], as_of: float):
        self.model = model
        self.as_of = as_of
        self._arr: dict[tuple[str, float], dict[str, float]] = {}
        self.ld: dict[str, dict[str, float]] = {}
        self.override: dict[tuple[str, str], float] = {}
        for c in candidates:
            target_deadline = c.latest_arrival - c.access_min if c.latest_arrival != INF else INF
            L, _ = model.latest_departure_cached(c.site_node, target_deadline)
            self.ld[c.code] = L

    def tt(self, origin: str, cand: Candidate, depart: float) -> float | None:
        key = (origin, cand.site_node)
        if key in self.override:
            return self.override[key]
        dk = (origin, round(depart / 15.0) * 15.0)
        if dk not in self._arr:
            arr, _ = self.model.earliest_arrival(origin, dk[1])
            self._arr[dk] = arr
        arr = self._arr[dk]
        if cand.site_node not in arr:
            return None
        return arr[cand.site_node] - dk[1] + cand.access_min

    def latest_dep(self, origin: str, cand: Candidate) -> float:
        return self.ld[cand.code].get(origin, -INF)


def build_candidates(ctx: AreaContext, model: AccessModel, raw: list[dict], values: dict[str, float], as_of: float) -> list[Candidate]:
    out = []
    for r in raw:
        tpl = ctx.templates.get(r["template"])
        site = ctx.sites.get(r["site"])
        if tpl is None or site is None:
            continue
        dl = site_deadline(model, site, tpl, as_of)
        la = dl.deadline - tpl.safety_buffer_min - tpl.execution_min - tpl.setup_min if dl.deadline != INF else INF
        req = tpl.requirements or {}
        out.append(Candidate(
            code=r["code"], template_id=tpl.id, site_id=site.id, value=values.get(r["code"], 0.0),
            work=tpl.setup_min + tpl.execution_min, setup=tpl.setup_min, execution=tpl.execution_min,
            buffer=tpl.safety_buffer_min, pumps=tpl.pumps, crew_types=list((req.get("crew") or {}).get("types", [])),
            vehicle_types=list((req.get("vehicle") or {}).get("types", [])), equipment=dict(req.get("equipment") or {}),
            holds=set((tpl.constraints or {}).get("holds", [])), release_horizon=tpl.equipment_release == "HORIZON",
            latest_arrival=la, deadline=dl.deadline, deadline_reason=dl.reason, site_node=site.node,
            access_min=site.access_min, sector=site.sector,
        ))
    return out


def solve(p: OptProblem, travel: TravelTable, time_limit_s: float, workers: int = 4,
          nogoods: list[set[str]] | None = None, forced_off: set[str] | None = None,
          forbidden_arcs: set[tuple[str, str | None, str]] | None = None) -> Solution | None:
    t0 = time.time()
    m = cp_model.CpModel()
    H = int(p.horizon)
    t_now = int(math.floor(p.as_of))
    forced_off = forced_off or set()
    forbidden_arcs = forbidden_arcs or set()
    C = p.candidates
    by_code = {c.code: c for c in C}
    x = {c.code: m.NewBoolVar(f"x_{c.code}") for c in C}
    start = {c.code: m.NewIntVar(t_now, H + 2000, f"s_{c.code}") for c in C}
    end = {c.code: m.NewIntVar(t_now, H + 3000, f"e_{c.code}") for c in C}
    for c in C:
        m.Add(end[c.code] == start[c.code] + c.work)
        if c.code in forced_off:
            m.Add(x[c.code] == 0)
        if p.mode == "MINIMAL_CHANGE" and c.code not in p.human_assign:
            m.Add(x[c.code] == 0)
        if c.latest_arrival != INF:
            margin = MARGIN_MIN if p.mode in ("ROBUST", "MINIMAL_CHANGE") else 0
            la = int(math.floor(c.latest_arrival)) - margin
            if la < t_now:
                m.Add(x[c.code] == 0)
            else:
                m.Add(start[c.code] <= la).OnlyEnforceIf(x[c.code])

    # ---- commander constraints
    forbid_pairs: set[tuple[str, str]] = set()
    for k in p.constraints:
        if k.kind == "REQUIRE_TASK" and k.task_code in x:
            m.Add(x[k.task_code] == 1)
        elif k.kind == "EXCLUDE_TASK" and k.task_code in x:
            m.Add(x[k.task_code] == 0)
        elif k.kind == "FORBID_RESOURCE_SECTOR" and k.resource_id:
            for c in C:
                if c.sector == k.sector:
                    forbid_pairs.add((k.resource_id, c.code))
        elif k.kind == "FORBID_RESOURCE_TASK" and k.resource_id and k.task_code:
            forbid_pairs.add((k.resource_id, k.task_code))

    # ---- crew routing (one circuit per crew)
    a: dict[tuple[str, str], cp_model.IntVar] = {}
    arc_info: dict[tuple[str, str | None, str], cp_model.IntVar] = {}
    crew_obj_bonus = []
    for crew in p.crews:
        rel_t, rel_node = p.release.get(crew.id, (p.as_of, None))
        if rel_node is None:
            continue
        rel = int(math.ceil(rel_t))
        elig = [c for c in C if crew.subtype in c.crew_types and (crew.id, c.code) not in forbid_pairs]
        if not elig:
            continue
        arcs = []
        unused = m.NewBoolVar(f"unused_{crew.id}")
        arcs.append((0, 0, unused))
        for i, c in enumerate(elig, start=1):
            a[(c.code, crew.id)] = m.NewBoolVar(f"a_{c.code}_{crew.id}")
            arcs.append((i, i, a[(c.code, crew.id)].Not()))
            if c.code in p.human_assign and crew.id in p.human_assign[c.code]:
                crew_obj_bonus.append(a[(c.code, crew.id)])
            # depot → task
            lit = m.NewBoolVar(f"d_{crew.id}_{c.code}")
            tt = travel.tt(rel_node, c, rel_t)
            ld = travel.latest_dep(rel_node, c)
            if tt is None or ld == -INF or (crew.id, None, c.code) in forbidden_arcs:
                m.Add(lit == 0)
            else:
                tti = int(math.ceil(tt))
                m.Add(start[c.code] >= rel + tti).OnlyEnforceIf(lit)
                if ld != INF:
                    m.Add(start[c.code] - tti <= int(math.floor(ld)) + int(math.ceil(c.access_min))).OnlyEnforceIf(lit)
            arcs.append((0, i, lit))
            arc_info[(crew.id, None, c.code)] = lit
            # task → depot (end of the crew's day)
            arcs.append((i, 0, m.NewBoolVar(f"r_{crew.id}_{c.code}")))
        for i, c1 in enumerate(elig, start=1):
            if "CREW" in c1.holds:
                continue  # the crew remains at this site
            for k, c2 in enumerate(elig, start=1):
                if i == k:
                    continue
                lit = m.NewBoolVar(f"t_{crew.id}_{c1.code}_{c2.code}")
                tt = travel.tt(c1.site_node, c2, p.as_of + 60)
                ld = travel.latest_dep(c1.site_node, c2)
                if tt is None or ld == -INF or (crew.id, c1.code, c2.code) in forbidden_arcs:
                    m.Add(lit == 0)
                else:
                    tti = int(math.ceil(tt))
                    m.Add(start[c2.code] >= end[c1.code] + tti).OnlyEnforceIf(lit)
                    if ld != INF:
                        m.Add(end[c1.code] <= int(math.floor(ld))).OnlyEnforceIf(lit)
                arcs.append((i, k, lit))
                arc_info[(crew.id, c1.code, c2.code)] = lit
        m.AddCircuit(arcs)
    for c in C:
        lits = [a[(c.code, cr.id)] for cr in p.crews if (c.code, cr.id) in a]
        if lits:
            m.Add(sum(lits) == x[c.code])
        else:
            m.Add(x[c.code] == 0)

    # ---- vehicles (explicit assignment, no overlap per vehicle incl. approach travel)
    b: dict[tuple[str, str], cp_model.IntVar] = {}
    veh_intervals: dict[str, list] = {v.id: [] for v in p.vehicles}
    for c in C:
        if not c.vehicle_types:
            continue
        opts = [v for v in p.vehicles if v.subtype in c.vehicle_types and (v.id, c.code) not in forbid_pairs]
        lits = []
        for v in opts:
            lit = m.NewBoolVar(f"b_{c.code}_{v.id}")
            b[(c.code, v.id)] = lit
            lits.append(lit)
            vrel = int(math.ceil(p.release.get(v.id, (p.as_of, None))[0]))
            m.Add(start[c.code] >= vrel).OnlyEnforceIf(lit)
            s_ = m.NewIntVar(t_now - 200, H + 3000, f"vs_{c.code}_{v.id}")
            m.Add(s_ == start[c.code] - 20)
            e_ = m.NewIntVar(t_now, H + 5000, f"ve_{c.code}_{v.id}")
            if "VEHICLE" in c.holds:
                m.Add(e_ == H + 4000)
            else:
                m.Add(e_ == end[c.code])
            size = m.NewIntVar(0, H + 6000, f"vz_{c.code}_{v.id}")
            veh_intervals[v.id].append(m.NewOptionalIntervalVar(s_, size, e_, lit, f"vi_{c.code}_{v.id}"))
        if lits:
            m.Add(sum(lits) == x[c.code])
        else:
            m.Add(x[c.code] == 0)
    for ivs in veh_intervals.values():
        if len(ivs) > 1:
            m.AddNoOverlap(ivs)

    # ---- pumps (deployed until the horizon) and equipment pools
    m.Add(sum(c.pumps * x[c.code] for c in C) <= len(p.pumps))
    eq_by_sub: dict[str, list[ResourceInfo]] = {}
    for e in p.equipment:
        eq_by_sub.setdefault(e.subtype, []).append(e)
    for sub in {k for c in C for k in c.equipment}:
        cap = len(eq_by_sub.get(sub, []))
        users = [c for c in C if c.equipment.get(sub)]
        if cap == 0:
            for c in users:
                m.Add(x[c.code] == 0)
            continue
        ivs, dem = [], []
        for c in users:
            ivs.append(m.NewOptionalIntervalVar(start[c.code], c.work, end[c.code], x[c.code], f"eq_{sub}_{c.code}"))
            dem.append(int(c.equipment[sub]))
        m.AddCumulative(ivs, dem, cap)

    for ng in nogoods or []:
        m.Add(sum(1 - x[k] for k in ng if k in x) + sum(x[k] for k in x if k not in ng) >= 1)

    # ---- objective
    pen = []
    for c in C:
        pz = m.NewIntVar(0, H + 3000, f"pen_{c.code}")
        m.Add(pz >= end[c.code] - (H + 3000) * (1 - x[c.code]))
        pen.append(pz)
    obj = sum(int(round(c.value * 100)) * x[c.code] for c in C) - sum(pen) + p.keep_bonus * sum(crew_obj_bonus)
    if p.mode == "ROBUST":
        # reward schedule slack before each action window closes (capped at 120 min per task)
        for c in C:
            if c.latest_arrival == INF:
                continue
            sl = m.NewIntVar(0, 120, f"sl_{c.code}")
            m.Add(sl <= int(math.floor(c.latest_arrival)) - start[c.code]).OnlyEnforceIf(x[c.code])
            m.Add(sl == 0).OnlyEnforceIf(x[c.code].Not())
            obj = obj + 40 * sl
    if p.mode == "MINIMAL_CHANGE":
        for c in C:
            hd = p.human_departure.get(c.code)
            if hd is None:
                continue
            dev = m.NewIntVar(0, H + 4000, f"dev_{c.code}")
            m.Add(dev >= start[c.code] - int(hd)).OnlyEnforceIf(x[c.code])
            m.Add(dev >= int(hd) - start[c.code]).OnlyEnforceIf(x[c.code])
            m.Add(dev == 0).OnlyEnforceIf(x[c.code].Not())
            obj = obj - 15 * dev
    m.Maximize(obj)
    for c in C:  # symmetric-break hint: prefer human choices
        if c.code in p.human_assign:
            m.AddHint(x[c.code], 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = max(workers, 8)
    solver.parameters.random_seed = 17
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    assignments: list[Assignment] = []
    pump_pool = [pp.id for pp in sorted(p.pumps, key=lambda r: r.id)]
    eq_pool = {k: [e.id for e in sorted(v, key=lambda r: r.id)] for k, v in eq_by_sub.items()}
    eq_busy: dict[str, list[tuple[int, int]]] = {}
    chosen = [c for c in C if solver.Value(x[c.code])]
    chosen.sort(key=lambda c: solver.Value(start[c.code]))
    prev_of: dict[str, str | None] = {}
    crew_of: dict[str, str] = {}
    for (cid, frm, to), lit in arc_info.items():
        if solver.Value(lit):
            prev_of[to] = frm
            crew_of[to] = cid
    for c in chosen:
        crew = crew_of.get(c.code) or next((cr for (code, cr) in a if code == c.code and solver.Value(a[(code, cr)])), "")
        veh = next((vid for (code, vid), lit in b.items() if code == c.code and solver.Value(lit)), None)
        pumps = [pump_pool.pop(0) for _ in range(c.pumps)] if c.pumps else []
        eqs = []
        s_v, e_v = solver.Value(start[c.code]), solver.Value(end[c.code])
        for sub, cnt in c.equipment.items():
            for _ in range(int(cnt)):
                for eid in eq_pool.get(sub, []):
                    if all(e_v <= s or s_v >= e for s, e in eq_busy.get(eid, [])):
                        eq_busy.setdefault(eid, []).append((s_v, e_v))
                        eqs.append(eid)
                        break
        prev = prev_of.get(c.code)
        origin = p.release.get(crew, (0, None))[1] if prev is None else by_code[prev].site_node
        dep_base = p.release.get(crew, (p.as_of, None))[0] if prev is None else solver.Value(end[prev])
        tt = travel.tt(origin, c, dep_base) if origin else None
        departure = int(s_v - math.ceil(tt)) if tt is not None else s_v
        departure = max(departure, int(math.ceil(dep_base)))
        assignments.append(Assignment(c.code, c.template_id, c.site_id, crew, veh, pumps, eqs, s_v, e_v, departure,
                                      prev, origin))
    return Solution(
        status="OPTIMAL" if st == cp_model.OPTIMAL else "FEASIBLE",
        objective=solver.ObjectiveValue(), assignments=assignments, selected=[c.code for c in chosen],
        solve_time_s=round(time.time() - t0, 3), value_total=round(sum(c.value for c in chosen), 1),
    )
