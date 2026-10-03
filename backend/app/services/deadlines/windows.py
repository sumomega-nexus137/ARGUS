"""Action windows: LATEST SAFE ACTION TIME for tasks, road closure countdowns, access loss.

Task deadline D = min(site flooding at the working limit,
                      crew egress loss (no route back to a safe base) — if the action requires egress,
                      closure of a road the action protects,
                      explicit deadline).
latest completion  = D − safety buffer
latest start       = latest completion − execution
latest arrival     = latest start − setup − site access link
latest departure   = reverse time-dependent search from the site (accounts for roads closing en route)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from app.core.config import get_settings
from app.repositories.context import ActionTemplate, AreaContext, PointFeature
from app.services.clock import to_minutes
from app.services.routing.access import AccessModel, safe_base_nodes
from app.services.routing.intervals import INF, contains, finite_or_none

EXPOSED_DEPTH_M = 0.10


@dataclass
class SiteDeadline:
    deadline: float
    reason: str  # SITE_FLOODED | EGRESS_LOST | PROTECTED_ROAD_CLOSES | EXPLICIT | NONE
    components: dict[str, float | None] = field(default_factory=dict)


@dataclass
class TaskWindow:
    code: str
    template_id: str
    site_id: str
    origin_node: str | None
    deadline: float | None
    deadline_reason: str
    components: dict
    latest_completion: float | None
    latest_start: float | None
    latest_arrival: float | None
    latest_departure: float | None
    route_segments: list[str]
    route_roads: list[str]
    slack_min: float | None
    status: str  # SAFE | WINDOW_CLOSING | WINDOW_MISSED | NO_DEADLINE | NO_ROUTE

    def as_dict(self) -> dict:
        return asdict(self)


def egress_times(model: AccessModel) -> dict[str, float]:
    key = ("__egress__",)
    hit = model._rev_cache.get(key)
    if hit is None:
        bases = safe_base_nodes(model.ctx)
        L, _ = model.latest_departure({b: INF for b in bases})
        model._rev_cache[key] = (L, {})
        return L
    return hit[0]


def road_first_closure(model: AccessModel, road_id: str, t_from: float) -> float:
    segs = model.ctx.roads.get(road_id)
    if not segs:
        return INF
    return min(model.closure_from(s, t_from) for s in segs.segment_ids)


def site_deadline(model: AccessModel, site: PointFeature, template: ActionTemplate | None, t_from: float) -> SiteDeadline:
    comps: dict[str, float | None] = {}
    limit = float(site.attrs.get("work_limit", 0.25))
    flood = model.first_level_exceedance(site.x, site.y, limit, t_from)
    comps["site_flooded"] = flood
    requires_egress = template.requires_egress if template else True
    if requires_egress:
        L = egress_times(model)
        comps["egress_lost"] = L.get(site.node, -INF) - site.access_min
    else:
        # one-way actions (e.g. pre-positioning) must still ARRIVE before the site is cut off from the bases
        key = ("__access_loss__", t_from)
        loss = model._rev_cache.get(key)
        if loss is None:
            loss = model.access_loss(safe_base_nodes(model.ctx), t0=t_from)
            model._rev_cache[key] = loss
        v = loss.get(site.node, -INF)
        if v != INF:
            comps["access_lost"] = v - site.access_min
    road_ids = (site.attrs.get("protects") or {}).get("road_ids") or []
    if road_ids:
        comps["protected_road_closes"] = min(road_first_closure(model, r, t_from) for r in road_ids)
    exp = site.attrs.get("explicit_deadline")
    if exp is not None and model.rt is not None:
        comps["explicit"] = to_minutes(model.rt.reference_time, exp)
    reason_map = {"site_flooded": "SITE_FLOODED", "egress_lost": "EGRESS_LOST", "access_lost": "ACCESS_LOST",
                  "protected_road_closes": "PROTECTED_ROAD_CLOSES", "explicit": "EXPLICIT"}
    best_k, best_v = None, INF
    for k, v in comps.items():
        if v is not None and v < best_v:
            best_k, best_v = k, v
    return SiteDeadline(best_v, reason_map.get(best_k or "", "NONE") if best_v != INF else "NONE", comps)


def window_status(latest_departure: float | None, as_of: float) -> tuple[str, float | None]:
    thr = get_settings().window_closing_threshold_min
    if latest_departure is None:
        return "NO_DEADLINE", None
    if latest_departure == -INF:
        return "NO_ROUTE", None
    slack = latest_departure - as_of
    if slack < 0:
        return "WINDOW_MISSED", slack
    if slack <= thr:
        return "WINDOW_CLOSING", slack
    return "SAFE", slack


def task_window(model: AccessModel, code: str, template: ActionTemplate, site: PointFeature, origin_node: str | None,
                as_of: float, dl: SiteDeadline | None = None) -> TaskWindow:
    dl = dl or site_deadline(model, site, template, as_of)
    comps = {k: finite_or_none(v) for k, v in dl.components.items()}
    if dl.deadline == INF:
        return TaskWindow(code, template.id, site.id, origin_node, None, "NONE", comps, None, None, None, None, [], [],
                          None, "NO_DEADLINE")
    latest_completion = dl.deadline - template.safety_buffer_min
    latest_start = latest_completion - template.execution_min
    latest_arrival = latest_start - template.setup_min - site.access_min
    ld: float | None = None
    segs: list[str] = []
    if origin_node is not None:
        L, succ = model.latest_departure_cached(site.node, latest_arrival)
        v = L.get(origin_node, -INF)
        ld = v
        if v != -INF:
            segs = model.path_from_succ(succ, origin_node)
    status, slack = window_status(ld, as_of)
    roads = []
    for s in segs:
        r = model.ctx.segments[s].road_id
        if not roads or roads[-1] != r:
            roads.append(r)
    return TaskWindow(code, template.id, site.id, origin_node, dl.deadline, dl.reason, comps, latest_completion,
                      latest_start, latest_arrival, finite_or_none(ld) if ld is not None else None, segs, roads,
                      finite_or_none(slack) if slack is not None else None, status)


def road_windows(model: AccessModel, as_of: float) -> list[dict]:
    out = []
    horizon = model.horizon_end
    for rid, road in model.ctx.roads.items():
        seg_rows = []
        worst = "OPEN"
        closes_at = INF
        reopen = None
        max_future_depth = 0.0
        override = None
        for sid in road.segment_ids:
            e = model.edges[sid]
            st = model.state_at(sid, as_of)
            c = model.closure_from(sid, as_of)
            if st != "CLOSED":
                closes_at = min(closes_at, c)
            else:
                for a, b in e.closed:
                    if a <= as_of < b and b != INF:
                        reopen = b if reopen is None else min(reopen, b)
            fut = e.depth[model.t >= as_of] if e.depth.size else np.array([])
            if fut.size:
                max_future_depth = max(max_future_depth, float(np.nanmax(np.where(np.isfinite(fut), fut, -9))))
            if e.override:
                override = e.override
            rank = {"OPEN": 0, "RESTRICTED": 1, "CLOSED": 2}
            if rank[st] > rank[worst]:
                worst = st
            seg_rows.append({"segment_id": sid, "state": st, "closes_at": finite_or_none(c) if st != "CLOSED" else None,
                             "depth_m": round(model.depth_at(sid, as_of), 2), "override": e.override})
        label = worst
        if worst != "CLOSED":
            if closes_at <= horizon:
                label = worst if worst == "RESTRICTED" else "CLOSES_IN"
            elif max_future_depth > 0 or any(model.edges[s].restricted and any(b > as_of for _, b in model.edges[s].restricted)
                                             for s in road.segment_ids):
                label = "AT_RISK" if worst == "OPEN" else worst
        out.append({
            "road_id": rid, "names": road.names, "road_class": road.road_class, "state": label, "worst_segment_state": worst,
            "closes_at": finite_or_none(closes_at) if worst != "CLOSED" and closes_at <= horizon else None,
            "closes_in_min": finite_or_none(closes_at - as_of) if worst != "CLOSED" and closes_at <= horizon else None,
            "reopens_at": finite_or_none(reopen) if reopen is not None else None,
            "override": override, "segments": seg_rows,
        })
    order = {"CLOSED": 0, "RESTRICTED": 1, "CLOSES_IN": 2, "AT_RISK": 3, "OPEN": 4}
    out.sort(key=lambda r: (order[r["state"]], r["closes_at"] if r["closes_at"] is not None else 1e9, r["road_id"]))
    return out


def sector_access(model: AccessModel, as_of: float) -> tuple[list[dict], dict[str, float]]:
    ctx: AreaContext = model.ctx
    bases = safe_base_nodes(ctx)
    loss = model.access_loss(bases, t0=as_of)
    reach = model.reachable_at(bases, as_of)
    pop_by_sector: dict[str, int] = {}
    for z in ctx.zones:
        if z.sector:
            pop_by_sector[z.sector] = pop_by_sector.get(z.sector, 0) + z.population
    rows = []
    for code, s in ctx.sectors.items():
        times = [loss.get(n, -INF) for n in s.nodes]
        full = max(times) if times else -INF
        first = min(times) if times else -INF
        isolated_now = not any(n in reach for n in s.nodes)
        rows.append({
            "code": code, "names": s.names, "population": pop_by_sector.get(code, 0),
            "access_lost_at": None if isolated_now else finite_or_none(full),
            "access_lost_in_min": None if isolated_now or full == INF else finite_or_none(full - as_of),
            "partial_loss_at": finite_or_none(first) if first != full else None,
            "isolated_now": isolated_now,
        })
    rows.sort(key=lambda r: (not r["isolated_now"], r["access_lost_at"] if r["access_lost_at"] is not None else 1e9))
    return rows, loss


def facility_access(model: AccessModel, as_of: float, loss: dict[str, float]) -> list[dict]:
    ctx = model.ctx
    bases = safe_base_nodes(ctx)
    reach = model.reachable_at(bases, as_of)
    out = []
    for fid, f in ctx.facilities.items():
        lost = loss.get(f.node, -INF)
        flood = model.first_level_exceedance(f.x, f.y, EXPOSED_DEPTH_M, as_of)
        lvl_now = model.point_level_series(f.x, f.y)
        now_depth = float(np.interp(as_of, model.t, np.where(np.isfinite(lvl_now), lvl_now, -9.0)))
        out.append({
            "id": fid, "type": f.kind, "names": f.names, "criticality": f.attrs.get("criticality"),
            "lon": f.lon, "lat": f.lat,
            "accessible_now": f.node in reach,
            "access_lost_at": finite_or_none(lost) if f.node in reach else None,
            "access_lost_in_min": finite_or_none(lost - as_of) if f.node in reach and lost != INF else None,
            "flooded_now": now_depth >= EXPOSED_DEPTH_M,
            "flood_at": finite_or_none(flood) if now_depth < EXPOSED_DEPTH_M else None,
            "flood_in_min": finite_or_none(flood - as_of) if now_depth < EXPOSED_DEPTH_M and flood != INF else None,
        })
    out.sort(key=lambda r: (-(r["criticality"] or 0)))
    return out


def edge_states_payload(model: AccessModel, as_of: float) -> dict[str, dict]:
    out = {}
    for sid, e in model.edges.items():
        st = model.state_at(sid, as_of)
        c = model.closure_from(sid, as_of)
        out[sid] = {"state": st, "closes_at": finite_or_none(c) if st != "CLOSED" and c <= model.horizon_end else None,
                    "depth_m": round(model.depth_at(sid, as_of), 2), "override": e.override is not None,
                    "restricted_now": contains(e.restricted, as_of)}
    return out
