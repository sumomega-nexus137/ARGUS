"""Time-dependent road graph (Module 3 — Access & Action Window Engine).

Each road segment receives, from the active flood scenario:
  * a depth series (max water depth on the carriageway = relative level − embankment),
  * RESTRICTED and CLOSED time intervals (depth thresholds, configurable),
  * bridge closures from river level vs deck clearance,
then field overrides are applied (verified field observations always win).

Routing primitives:
  * ``earliest_arrival``   — time-dependent Dijkstra (no waiting, FIFO)
  * ``latest_departure``   — reverse search: latest time to leave each node and still arrive by a deadline
  * ``access_loss``        — max–min (widest path) time until a node loses every open route to a base
  * ``reachable_at``       — connectivity snapshot at a time instant
"""

from __future__ import annotations

import heapq
import threading
from dataclasses import dataclass, field

import numpy as np

from app.core.config import get_settings
from app.repositories.context import AreaContext
from app.services.clock import to_minutes
from app.services.routing.intervals import (
    INF,
    Interval,
    contains,
    first_overlap,
    merge,
    next_start_after,
    subtract,
    threshold_intervals,
)
from app.services.scenario.runtime import ScenarioRuntime

SERIES_STEP_MIN = 10.0
NODE_PENALTY_MIN = 0.2
OPEN_OVERRIDE_VALIDITY_MIN = 120.0
BRIDGE_RESTRICT_MARGIN_M = 0.2


@dataclass(frozen=True)
class AccessConfig:
    member: str
    time_shift_min: float = 0.0  # > 0: the flood arrives this many minutes earlier
    road_advance_min: tuple[tuple[str, float], ...] = ()  # (road_id, minutes earlier)
    closed_roads: tuple[str, ...] = ()  # closed from ``now`` (what-if / perturbation)
    closed_segments: tuple[str, ...] = ()
    apply_events: bool = True
    vehicle_class: str = "STANDARD"  # STANDARD | HIGH_CLEARANCE


@dataclass
class EdgeState:
    seg_id: str
    road_id: str
    closed: list[Interval]
    restricted: list[Interval]
    depth: np.ndarray  # max carriageway depth per series step (m; -inf dry)
    override: dict | None = None
    model_closed: list[Interval] = field(default_factory=list)


_series_cache: dict[tuple, tuple[np.ndarray, dict[str, np.ndarray]]] = {}
_series_lock = threading.Lock()


def _depth_series(ctx: AreaContext, rt: ScenarioRuntime, member: str) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    key = (ctx.area_id, ctx.static_version, rt.family_id, id(rt.provider), member)
    with _series_lock:
        hit = _series_cache.get(key)
    if hit is not None:
        return hit
    start, end = rt.provider.time_range()
    t = np.arange(start, end + SERIES_STEP_MIN / 2, SERIES_STEP_MIN)
    segs = [s for s in ctx.segments.values() if not s.bridge_id]
    xs = np.concatenate([s.sample_x for s in segs]) if segs else np.array([])
    ys = np.concatenate([s.sample_y for s in segs]) if segs else np.array([])
    lvl = rt.provider.relative_level_points(member, xs, ys, t) if len(xs) else np.zeros((0, len(t)))
    out: dict[str, np.ndarray] = {}
    i = 0
    for s in segs:
        n = len(s.sample_x)
        block = lvl[i:i + n] - s.embankment_m
        block = np.where(np.isnan(block), -np.inf, block)
        out[s.id] = block.max(axis=0)
        i += n
    river = rt.provider.river_level(member, t)
    closed_depth = get_settings().road_closed_depth_m
    for s in ctx.segments.values():
        if s.bridge_id:
            clearance = float(ctx.bridges.get(s.bridge_id, {}).get("clearance", 99.0))
            # equivalent depth: closed at clearance, restricted from clearance - margin
            out[s.id] = river - clearance + closed_depth
    with _series_lock:
        if len(_series_cache) > 64:
            _series_cache.clear()
        _series_cache[key] = (t, out)
    return t, out


@dataclass
class AccessModel:
    ctx: AreaContext
    cfg: AccessConfig
    t: np.ndarray
    edges: dict[str, EdgeState]
    now: float
    horizon_end: float
    restricted_factor: float
    closed_depth: float
    rt: ScenarioRuntime | None = None
    _point_cache: dict = field(default_factory=dict)
    _rev_cache: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ scenario-consistent point series
    def point_level_series(self, x: float, y: float) -> np.ndarray:
        """Relative water level at a projected point on ``self.t`` (perturbation time shift applied)."""
        key = (round(x, 1), round(y, 1))
        hit = self._point_cache.get(key)
        if hit is not None:
            return hit
        assert self.rt is not None
        tq = self.t + self.cfg.time_shift_min if self.cfg.time_shift_min else self.t
        lv = self.rt.provider.relative_level_points(self.cfg.member, np.array([x]), np.array([y]), tq)[0]
        self._point_cache[key] = lv
        return lv

    def first_level_exceedance(self, x: float, y: float, thr: float, t_from: float) -> float:
        s = self.point_level_series(x, y)
        s = np.where(np.isfinite(s), s, -9.0)
        iv = threshold_intervals(self.t, s, thr)
        for a, b in iv:
            if b > t_from:
                return max(a, t_from)
        return INF

    def latest_departure_cached(self, target: str, deadline: float) -> tuple[dict[str, float], dict[str, tuple[str, str]]]:
        key = (target, round(deadline, 3) if deadline != INF else INF)
        hit = self._rev_cache.get(key)
        if hit is None:
            hit = self.latest_departure({target: deadline})
            self._rev_cache[key] = hit
        return hit

    # ------------------------------------------------------------------ edge queries
    def state_at(self, seg_id: str, t: float) -> str:
        e = self.edges[seg_id]
        if contains(e.closed, t):
            return "CLOSED"
        if contains(e.restricted, t):
            return "RESTRICTED"
        return "OPEN"

    def travel_time(self, seg_id: str, t: float) -> float | None:
        e = self.edges[seg_id]
        if contains(e.closed, t):
            return None
        s = self.ctx.segments[seg_id]
        speed = s.speed_kmh * (self.restricted_factor if contains(e.restricted, t) else 1.0)
        return s.length_m / 1000.0 / max(speed, 1.0) * 60.0 + NODE_PENALTY_MIN

    def free_flow_time(self, seg_id: str) -> float:
        s = self.ctx.segments[seg_id]
        return s.length_m / 1000.0 / max(s.speed_kmh, 1.0) * 60.0 + NODE_PENALTY_MIN

    def closure_from(self, seg_id: str, t: float) -> float:
        return next_start_after(self.edges[seg_id].closed, t)

    def depth_at(self, seg_id: str, t: float) -> float:
        d = self.edges[seg_id].depth
        if d.size == 0:
            return 0.0
        v = float(np.interp(t, self.t, np.where(np.isfinite(d), d, -9.0)))
        return max(v, 0.0)

    def _traversable(self, seg_id: str, a: float, b: float) -> bool:
        return first_overlap(self.edges[seg_id].closed, a, b) is None

    # ------------------------------------------------------------------ searches
    def earliest_arrival(self, origin: str, t0: float) -> tuple[dict[str, float], dict[str, tuple[str, str]]]:
        arr: dict[str, float] = {origin: t0}
        pred: dict[str, tuple[str, str]] = {}
        heap = [(t0, origin)]
        done: set[str] = set()
        while heap:
            t, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            for seg, v in self.ctx.adjacency.get(u, []):
                tt = self.travel_time(seg, t)
                if tt is None:
                    continue
                te = t + tt
                if not self._traversable(seg, t, te):
                    continue
                if te < arr.get(v, INF):
                    arr[v] = te
                    pred[v] = (seg, u)
                    heapq.heappush(heap, (te, v))
        return arr, pred

    def _latest_entry(self, seg_id: str, arrive_by: float) -> float | None:
        e = self.edges[seg_id]
        s = self.ctx.segments[seg_id]
        fast = s.length_m / 1000.0 / max(s.speed_kmh, 1.0) * 60.0 + NODE_PENALTY_MIN
        slow = s.length_m / 1000.0 / max(s.speed_kmh * self.restricted_factor, 1.0) * 60.0 + NODE_PENALTY_MIN
        by = arrive_by
        for _ in range(8):
            if by == INF:
                ov = first_overlap(e.closed, self.now, INF)
                if ov is None:
                    return INF
                by = ov[0]
                continue
            tau = by - fast
            if contains(e.restricted, tau):
                tau = by - slow
            tt = by - tau
            ov = first_overlap(e.closed, tau, tau + tt)
            if ov is None:
                return tau
            if ov[0] <= tau:  # closed at entry time → must be before the interval
                by = ov[0]
                continue
            by = ov[0]
        return None

    def latest_departure(self, targets: dict[str, float]) -> tuple[dict[str, float], dict[str, tuple[str, str]]]:
        """Latest departure time from every node to reach any target node by its deadline."""
        L: dict[str, float] = dict(targets)
        succ: dict[str, tuple[str, str]] = {}
        heap = [(-v, k) for k, v in targets.items()]
        heapq.heapify(heap)
        done: set[str] = set()
        while heap:
            negl, v = heapq.heappop(heap)
            if v in done:
                continue
            done.add(v)
            lv = -negl
            for seg, u in self.ctx.adjacency.get(v, []):
                tau = self._latest_entry(seg, lv)
                if tau is None:
                    continue
                if tau > L.get(u, -INF):
                    L[u] = tau
                    succ[u] = (seg, v)
                    heapq.heappush(heap, (-tau, u))
        return L, succ

    def access_loss(self, sources: list[str], t0: float | None = None) -> dict[str, float]:
        """Max over paths of min closure time: after this a node has no open route to any source."""
        t0 = self.now if t0 is None else t0
        best: dict[str, float] = {s: INF for s in sources}
        heap = [(-INF, s) for s in sources]
        done: set[str] = set()
        while heap:
            negv, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            bu = -negv
            for seg, v in self.ctx.adjacency.get(u, []):
                cap = min(bu, self.closure_from(seg, t0))
                if cap > best.get(v, -INF):
                    best[v] = cap
                    heapq.heappush(heap, (-cap, v))
        return best

    def reachable_at(self, sources: list[str], t: float) -> set[str]:
        seen = set(sources)
        stack = list(sources)
        while stack:
            u = stack.pop()
            for seg, v in self.ctx.adjacency.get(u, []):
                if v in seen or contains(self.edges[seg].closed, t):
                    continue
                seen.add(v)
                stack.append(v)
        return seen

    # ------------------------------------------------------------------ path helpers
    def path_from_pred(self, pred: dict[str, tuple[str, str]], target: str) -> list[str]:
        segs: list[str] = []
        cur = target
        guard = 0
        while cur in pred and guard < 10000:
            seg, prev = pred[cur]
            segs.append(seg)
            cur = prev
            guard += 1
        return list(reversed(segs))

    def path_from_succ(self, succ: dict[str, tuple[str, str]], origin: str) -> list[str]:
        segs: list[str] = []
        cur = origin
        guard = 0
        while cur in succ and guard < 10000:
            seg, nxt = succ[cur]
            segs.append(seg)
            cur = nxt
            guard += 1
        return segs

    def route_timeline(self, origin: str, segs: list[str], t0: float) -> list[dict]:
        out = []
        t = t0
        node = origin
        for seg in segs:
            s = self.ctx.segments[seg]
            tt = self.travel_time(seg, t) or self.free_flow_time(seg)
            out.append({"segment_id": seg, "road_id": s.road_id, "enter": t, "exit": t + tt, "from": node,
                        "state_at_entry": self.state_at(seg, t)})
            node = s.v if s.u == node else s.u
            t += tt
        return out


def build_access_model(ctx: AreaContext, rt: ScenarioRuntime, cfg: AccessConfig, now_min: float | None = None) -> AccessModel:
    st = get_settings()
    closed_depth = st.road_closed_depth_high_clearance_m if cfg.vehicle_class == "HIGH_CLEARANCE" else st.road_closed_depth_m
    restricted_depth = st.road_restricted_depth_m
    t, series = _depth_series(ctx, rt, cfg.member)
    now = to_minutes(rt.reference_time, ctx.now) if now_min is None else now_min
    shift = cfg.time_shift_min
    advance = dict(cfg.road_advance_min)
    edges: dict[str, EdgeState] = {}
    for sid, s in ctx.segments.items():
        d = series[sid]
        if shift:
            d = np.interp(t + shift, t, d, right=d[-1])
        if s.bridge_id:
            # bridges: clearance-based, identical for all vehicle classes
            closed = threshold_intervals(t, d, st.road_closed_depth_m)
            restricted = threshold_intervals(t, d, st.road_closed_depth_m - BRIDGE_RESTRICT_MARGIN_M)
        else:
            closed = threshold_intervals(t, d, closed_depth)
            restricted = threshold_intervals(t, d, restricted_depth)
        if s.road_id in advance:
            a = advance[s.road_id]
            closed = [(x - a if x != -INF else x, y) for x, y in closed]
        edges[sid] = EdgeState(sid, s.road_id, merge(closed), merge(restricted), d, model_closed=list(closed))

    forced = set(cfg.closed_segments)
    for rid in cfg.closed_roads:
        forced.update(ctx.roads[rid].segment_ids if rid in ctx.roads else [])
    for sid in forced:
        if sid in edges:
            edges[sid].closed = merge(edges[sid].closed + [(now, INF)])
            edges[sid].override = {"state": "CLOSED", "source": "WHAT_IF", "verification": "SIMULATED"}

    if cfg.apply_events:
        for ev in ctx.road_events:
            verified = ev.verification == "VERIFIED"
            if not verified and not (st.apply_unverified_closures and ev.state in ("CLOSED", "RESTRICTED")):
                continue
            seg_ids = ev.segment_ids or (ctx.roads[ev.road_id].segment_ids if ev.road_id in ctx.roads else [])
            a = to_minutes(rt.reference_time, ev.effective_from)
            b = to_minutes(rt.reference_time, ev.effective_until) if ev.effective_until else INF
            for sid in seg_ids:
                e = edges.get(sid)
                if e is None:
                    continue
                if ev.state == "CLOSED":
                    e.closed = merge(e.closed + [(a, b)])
                elif ev.state == "RESTRICTED":
                    e.restricted = merge(e.restricted + [(a, b)])
                elif ev.state == "OPEN" and verified:
                    bb = b if b != INF else a + OPEN_OVERRIDE_VALIDITY_MIN
                    e.closed = subtract(e.closed, (a, bb))
                    e.restricted = subtract(e.restricted, (a, bb))
                e.override = {"state": ev.state, "source": ev.source, "verification": ev.verification,
                              "event_id": ev.id, "effective_from": ev.effective_from.isoformat(),
                              "reported_by": ev.reported_by}
    return AccessModel(ctx, cfg, t, edges, now, rt.horizon_end, st.restricted_speed_factor, closed_depth, rt=rt)


def safe_base_nodes(ctx: AreaContext) -> list[str]:
    return [b.node for b in ctx.bases.values() if b.attrs.get("safe", True)]
