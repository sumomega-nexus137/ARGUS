"""Bottleneck analysis (Module 3): "If this bottleneck becomes constrained / unavailable, what follows?"

For every registered bottleneck (bridge, culvert, low-road section, channel constraint) the time-dependent
road graph is re-built with the bottleneck's segments unavailable from the analysis time and compared with
the baseline: sector / facility isolation, access-loss times, travel-time increases and critical
dependencies (single points of failure). Purely network consequences — no hydrodynamic claim is made.
"""

from __future__ import annotations

import networkx as nx

from app.repositories.context import AreaContext
from app.services.routing.access import AccessConfig, AccessModel, build_access_model, safe_base_nodes
from app.services.routing.intervals import INF, finite_or_none
from app.services.scenario.runtime import ScenarioRuntime


def _travel_from_bases(m: AccessModel, t: float) -> dict[str, float]:
    best: dict[str, float] = {}
    for b in safe_base_nodes(m.ctx):
        arr, _ = m.earliest_arrival(b, t)
        for n, v in arr.items():
            if v - t < best.get(n, INF):
                best[n] = v - t
    return best


def _snapshot(m: AccessModel, t: float) -> dict:
    ctx = m.ctx
    bases = safe_base_nodes(ctx)
    reach = m.reachable_at(bases, t)
    loss = m.access_loss(bases, t0=t)
    tt = _travel_from_bases(m, t)
    pop = {}
    for z in ctx.zones:
        if z.sector:
            pop[z.sector] = pop.get(z.sector, 0) + z.population
    sectors = {}
    for code, s in ctx.sectors.items():
        iso = not any(n in reach for n in s.nodes)
        sectors[code] = {"isolated": iso, "access_lost_at": max((loss.get(n, -INF) for n in s.nodes), default=-INF),
                         "travel_min": min((tt.get(n, INF) for n in s.nodes), default=INF), "population": pop.get(code, 0)}
    facilities = {}
    for fid, f in ctx.facilities.items():
        facilities[fid] = {"accessible": f.node in reach, "access_lost_at": loss.get(f.node, -INF),
                           "travel_min": tt.get(f.node, INF) + f.access_min if f.node in tt else INF,
                           "criticality": f.attrs.get("criticality", 0)}
    return {"sectors": sectors, "facilities": facilities}


def analyze(ctx: AreaContext, rt: ScenarioRuntime, as_of: float, ids: list[str] | None = None) -> dict:
    base_m = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=as_of)
    base = _snapshot(base_m, as_of)
    rows = []
    for bid, b in ctx.bottlenecks.items():
        if ids and bid not in ids:
            continue
        m = build_access_model(ctx, rt, AccessConfig(member=rt.member, closed_segments=tuple(b["segment_ids"])), now_min=as_of)
        snap = _snapshot(m, as_of)
        sectors, facilities = [], []
        newly_iso_pop = 0
        for code, s in snap["sectors"].items():
            s0 = base["sectors"][code]
            d_travel = None if s["travel_min"] == INF or s0["travel_min"] == INF else s["travel_min"] - s0["travel_min"]
            lost_earlier = s["access_lost_at"] < s0["access_lost_at"] - 1
            if s["isolated"] and not s0["isolated"]:
                newly_iso_pop += s["population"]
            if (s["isolated"] and not s0["isolated"]) or lost_earlier or (d_travel is not None and d_travel > 2):
                sectors.append({"code": code, "names": ctx.sectors[code].names, "isolated": s["isolated"],
                                "was_isolated": s0["isolated"], "population": s["population"],
                                "access_lost_at": finite_or_none(s["access_lost_at"]),
                                "baseline_access_lost_at": finite_or_none(s0["access_lost_at"]),
                                "travel_increase_min": None if d_travel is None else round(d_travel, 1)})
        spof_crit = 0
        for fid, f in snap["facilities"].items():
            f0 = base["facilities"][fid]
            d_travel = None if f["travel_min"] == INF or f0["travel_min"] == INF else f["travel_min"] - f0["travel_min"]
            newly_cut = (not f["accessible"]) and f0["accessible"]
            if newly_cut:
                spof_crit += int(f["criticality"] or 0)
            if newly_cut or f["access_lost_at"] < f0["access_lost_at"] - 1 or (d_travel is not None and d_travel > 2):
                facilities.append({"id": fid, "names": ctx.facilities[fid].names, "type": ctx.facilities[fid].kind,
                                   "criticality": f["criticality"], "accessible": f["accessible"],
                                   "single_point_of_failure": newly_cut,
                                   "access_lost_at": finite_or_none(f["access_lost_at"]),
                                   "baseline_access_lost_at": finite_or_none(f0["access_lost_at"]),
                                   "travel_increase_min": None if d_travel is None else round(d_travel, 1)})
        incr = [s["travel_increase_min"] for s in sectors if s["travel_increase_min"] is not None] + \
               [f["travel_increase_min"] for f in facilities if f["travel_increase_min"] is not None]
        score = newly_iso_pop / 100.0 + spof_crit / 10.0 + (sum(incr) / len(incr) if incr else 0.0)
        own_closure = min((base_m.closure_from(s, as_of) for s in b["segment_ids"]), default=INF)
        rows.append({
            "id": bid, "kind": b["kind"], "names": b["names"], "segment_ids": b["segment_ids"], "lon": b["lon"], "lat": b["lat"],
            "notes": b.get("notes"), "expected_closure_at": finite_or_none(own_closure) if own_closure <= rt.horizon_end else None,
            "affected_sectors": sectors, "affected_facilities": facilities, "newly_isolated_population": newly_iso_pop,
            "single_points_of_failure": [f["id"] for f in facilities if f["single_point_of_failure"]],
            "criticality_score": round(score, 1),
        })
    rows.sort(key=lambda r: -r["criticality_score"])
    return {"as_of": as_of, "scenario_id": rt.id, "member": rt.member, "bottlenecks": rows,
            "structural_candidates": structural_candidates(ctx),
            "methodology": "Each bottleneck's segments are made unavailable from the analysis time; sector / facility "
                           "reachability from safe bases, access-loss times (max–min path) and fastest travel times "
                           "are compared with the baseline scenario graph. Score = newly isolated population/100 + "
                           "Σ criticality of newly unreachable facilities/10 + mean travel-time increase (min)."}


def structural_candidates(ctx: AreaContext, top: int = 6) -> list[dict]:
    g = nx.Graph()
    for sid, s in ctx.segments.items():
        g.add_edge(s.u, s.v, key=sid, weight=s.length_m / max(s.speed_kmh, 1))
    bridges_graph = set(nx.bridges(g)) if g.number_of_edges() else set()
    eb = nx.edge_betweenness_centrality(g, weight="weight", normalized=True) if g.number_of_edges() else {}
    seg_of = {frozenset((s.u, s.v)): sid for sid, s in ctx.segments.items()}
    ranked = sorted(eb.items(), key=lambda kv: -kv[1])[:top]
    out = []
    for (u, v), val in ranked:
        sid = seg_of.get(frozenset((u, v)))
        if sid is None:
            continue
        out.append({"segment_id": sid, "road_id": ctx.segments[sid].road_id, "betweenness": round(val, 3),
                    "cut_edge": (u, v) in bridges_graph or (v, u) in bridges_graph})
    return out
