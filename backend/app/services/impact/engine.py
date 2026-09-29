"""Impact Engine (Module 2): what a flood frame affects — buildings, roads, facilities, population, economy."""

from __future__ import annotations

import threading

import numpy as np

from app.repositories.context import AreaContext
from app.services.impact import assumptions as A
from app.services.routing.access import AccessModel
from app.services.scenario.runtime import ScenarioRuntime

_lock = threading.Lock()
_levels_cache: dict[tuple, np.ndarray] = {}


def building_levels(ctx: AreaContext, rt: ScenarioRuntime, member: str, times: tuple[float, ...]) -> np.ndarray:
    """Relative water level at building centroids → [n_buildings, n_times] (NaN = dry)."""
    key = (ctx.area_id, ctx.static_version, rt.family_id, id(rt.provider), member, times)
    with _lock:
        hit = _levels_cache.get(key)
    if hit is not None:
        return hit
    b = ctx.buildings
    lv = rt.provider.relative_level_points(member, b.x, b.y, np.asarray(times, dtype=float)) if len(b.ids) else np.zeros((0, len(times)))
    with _lock:
        if len(_levels_cache) > 48:
            _levels_cache.clear()
        _levels_cache[key] = lv
    return lv


def point_levels(rt: ScenarioRuntime, member: str, xs: list[float], ys: list[float], times: np.ndarray) -> np.ndarray:
    if not xs:
        return np.zeros((0, len(times)))
    return rt.provider.relative_level_points(member, np.asarray(xs), np.asarray(ys), times)


def first_exceedance(times: np.ndarray, series: np.ndarray, thr: float, t_from: float) -> float | None:
    s = np.where(np.isfinite(series), series, -9.0)
    idx = np.where((s >= thr) & (times >= t_from))[0]
    if idx.size == 0:
        return None
    i = int(idx[0])
    if i == 0 or times[i - 1] < t_from:
        return float(max(times[i], t_from)) if s[i] >= thr else None
    d0, d1 = s[i - 1], s[i]
    return float(times[i - 1] + (thr - d0) / (d1 - d0) * (times[i] - times[i - 1])) if d1 != d0 else float(times[i])


def _range(lo: float, hi: float) -> dict:
    return {"low": A.round_sig(lo), "high": A.round_sig(hi), "currency": A.CURRENCY}


def frame_impact(ctx: AreaContext, rt: ScenarioRuntime, member: str, t: float, access: AccessModel | None = None,
                 include_calculation: bool = False) -> dict:
    b = ctx.buildings
    lv = building_levels(ctx, rt, member, (float(t),))[:, 0] if len(b.ids) else np.array([])
    depth = np.where(np.isfinite(lv), np.clip(lv, 0, None), 0.0)
    affected = depth >= A.AFFECTED_DEPTH_M
    lo_v, hi_v = A.unit_values(b.use)
    value_lo = b.floor_area * lo_v
    value_hi = b.floor_area * hi_v
    frac = A.damage_fraction(depth)
    exp_lo, exp_hi = float(value_lo[affected].sum()), float(value_hi[affected].sum())
    dmg_lo = float((value_lo * frac * (1 - A.DAMAGE_UNCERTAINTY))[affected].sum())
    dmg_hi = float((value_hi * frac * (1 + A.DAMAGE_UNCERTAINTY))[affected].sum())

    classes = []
    for lo, hi in A.DEPTH_CLASSES:
        m = (depth >= lo) & (depth < hi)
        classes.append({"min_m": lo, "max_m": None if hi >= 99 else hi, "buildings": int(m.sum())})
    by_use = {}
    for u in sorted(set(b.use.tolist())):
        m = affected & (b.use == u)
        by_use[u] = {"buildings": int(m.sum()), "floor_area_m2": round(float(b.floor_area[m].sum()), -1)}

    pop_total, pop_exposed, vuln_exposed = 0, 0.0, 0.0
    sector_pop: dict[str, float] = {}
    for z in ctx.zones:
        pop_total += z.population
        if z.residential_idx.size == 0:
            continue
        fa = b.floor_area[z.residential_idx]
        tot = float(fa.sum())
        if tot <= 0:
            continue
        share = float(fa[affected[z.residential_idx]].sum()) / tot
        e = z.population * share
        pop_exposed += e
        vuln_exposed += e * z.vulnerable_share
        if z.sector:
            sector_pop[z.sector] = sector_pop.get(z.sector, 0.0) + e

    sectors = {}
    sec = np.array([s or "" for s in b.sector])
    for code, info in ctx.sectors.items():
        m = affected & (sec == code)
        sectors[code] = {"names": info.names, "buildings_affected": int(m.sum()),
                         "population_exposed": int(round(sector_pop.get(code, 0.0), -1))}

    fac_ids = list(ctx.facilities.keys())
    fl = point_levels(rt, member, [ctx.facilities[f].x for f in fac_ids], [ctx.facilities[f].y for f in fac_ids],
                      np.array([t]))
    facilities = []
    for i, fid in enumerate(fac_ids):
        f = ctx.facilities[fid]
        d = float(fl[i, 0]) if fl.size and np.isfinite(fl[i, 0]) else 0.0
        d = max(d, 0.0)
        access_state = None
        facilities.append({
            "id": fid, "type": f.kind, "names": f.names, "criticality": f.attrs.get("criticality"),
            "depth_m": round(d, 2), "exposed": d >= A.FACILITY_EXPOSED_DEPTH_M, "access": access_state,
            "lon": f.lon, "lat": f.lat,
        })

    roads_km_flooded, roads_km_closed, roads_km_restricted, seg_states = 0.0, 0.0, 0.0, {}
    if access is not None:
        for sid, s in ctx.segments.items():
            st = access.state_at(sid, t)
            dep = access.depth_at(sid, t)
            seg_states[sid] = st
            if dep >= A.AFFECTED_DEPTH_M:
                roads_km_flooded += s.length_m / 1000
            if st == "CLOSED":
                roads_km_closed += s.length_m / 1000
            elif st == "RESTRICTED":
                roads_km_restricted += s.length_m / 1000

    out = {
        "t_min": t,
        "buildings": {"total": len(b.ids), "affected": int(affected.sum()), "by_depth_class": classes, "by_use": by_use},
        "population": {"total": int(pop_total), "exposed": int(round(pop_exposed, -1)),
                       "vulnerable_exposed": int(round(vuln_exposed, -1)), "aggregated": True},
        "facilities": facilities,
        "facilities_exposed": sum(1 for f in facilities if f["exposed"]),
        "roads": {"km_flooded": round(roads_km_flooded, 2), "km_closed": round(roads_km_closed, 2),
                  "km_restricted": round(roads_km_restricted, 2),
                  "segments_closed": sum(1 for v in seg_states.values() if v == "CLOSED")},
        "sectors": sectors,
        "economic": {
            "asset_exposure": _range(exp_lo, exp_hi),
            "expected_damage": _range(dmg_lo, dmg_hi),
            "status": "DEMO_ASSUMPTIONS",
        },
        "max_depth_m": round(float(depth.max()) if depth.size else 0.0, 2),
    }
    if include_calculation:
        calc_rows = []
        for u, (ulo, uhi) in A.UNIT_VALUE_KZT_M2.items():
            m = affected & (b.use == u)
            if not m.any():
                continue
            calc_rows.append({
                "use": u, "buildings": int(m.sum()), "floor_area_m2": round(float(b.floor_area[m].sum()), -1),
                "unit_value_kzt_m2": [ulo, uhi],
                "exposure": _range(float(value_lo[m].sum()), float(value_hi[m].sum())),
                "mean_damage_fraction": round(float(frac[m].mean()), 3),
                "expected_damage": _range(float((value_lo * frac * (1 - A.DAMAGE_UNCERTAINTY))[m].sum()),
                                          float((value_hi * frac * (1 + A.DAMAGE_UNCERTAINTY))[m].sum())),
            })
        out["calculation"] = {"rows": calc_rows, "assumptions": A.as_dict()}
    return out


def impact_timeline(ctx: AreaContext, rt: ScenarioRuntime, member: str, access: AccessModel | None) -> dict:
    """Per-frame summaries plus compact per-building depth arrays for map styling (no browser GIS)."""
    times = tuple(float(x) for x in rt.frame_offsets)
    lv = building_levels(ctx, rt, member, times)
    depth = np.where(np.isfinite(lv), np.clip(lv, 0, None), 0.0)
    ever = np.where(depth.max(axis=1) >= 0.05)[0] if depth.size else np.array([], dtype=int)
    frames = []
    for t in times:
        f = frame_impact(ctx, rt, member, t, access)
        frames.append({
            "t_min": t, "buildings_affected": f["buildings"]["affected"], "population_exposed": f["population"]["exposed"],
            "facilities_exposed": f["facilities_exposed"], "roads_km_closed": f["roads"]["km_closed"],
            "asset_exposure": f["economic"]["asset_exposure"], "expected_damage": f["economic"]["expected_damage"],
            "max_depth_m": f["max_depth_m"],
        })
    return {
        "frames": frames,
        "buildings": {
            "ids": [ctx.buildings.ids[i] for i in ever.tolist()],
            "depth_cm": np.round(depth[ever] * 100).astype(int).tolist(),
        },
    }
