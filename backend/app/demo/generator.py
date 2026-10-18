"""Deterministic DEMO data generator.

``python -m app.cli generate-demo`` writes, for every demo area, into ``data/demo/<area>/``:

* ``terrain/dem.tif``, ``terrain/hand.tif``, ``terrain/onset.tif`` (+ ``ponding_cap.tif``) — SIMULATION rasters
* ``area.json``         — metadata (names, CRS, grid, stations, bases, sectors)
* ``roads.geojson``, ``bridges.geojson``, ``bottlenecks.geojson``
* ``buildings.geojson``, ``facilities.geojson``, ``sectors.geojson``, ``population_zones.geojson``
* ``task_sites.geojson``, ``resources.json``, ``plans.json``, ``observations.json``
* ``scenario.json``     — precomputed ensemble members (stage series) for the synthetic stage–HAND provider

Every output carries ``"demo": true`` / ``mode: SIMULATION`` markers.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.strtree import STRtree

from app.core.logging import get_logger
from app.demo.geo import LocalFrame
from app.demo.terrain import Bowl, Grid, priority_flood_onset, river_distance, smooth_noise

log = get_logger("argus.demo")

DEMO_NOTE = "DEMO DATA — synthetic, not surveyed or measured. For demonstration of ARGUS workflows only."
CLOSED_DEPTH_M = 0.30
FRAME_OFFSETS_MIN = list(range(-360, 1080 + 1, 60))
SERIES_STEP_MIN = 10


# ----------------------------------------------------------------------------------- terrain
def build_terrain(spec: dict) -> dict[str, Any]:
    g = spec["grid"]
    grid = Grid(g["x0"], g["y1"], g["res"], g["nx"], g["ny"])
    t = spec["terrain"]
    X, Y = grid.centers()
    dist, side, channel = river_distance(grid, spec["river_y"], t["channel_half_width"])
    slope = np.where(side >= 0, t["north_slope"], t["south_slope"])
    hand = 0.25 + slope * dist
    terr = np.clip(dist - t["terrace_start"], 0, None)
    hand = hand + t["terrace_slope"] * terr
    for b in t["bowls"]:
        hand = hand + b.eval(X, Y)
    hand = hand + smooth_noise(hand.shape, t["noise_sigma"], t["noise_amp"], t["seed"])
    hand = np.where(channel, -t["channel_depth"], np.maximum(hand, 0.05)).astype(np.float32)
    ws = t["bankfull_ws_at_x0"] - t["ws_slope"] * (X - g["x0"])
    dem = (ws + hand).astype(np.float32)
    onset = priority_flood_onset(hand, channel)
    ponding = np.zeros_like(hand)
    for p in spec.get("ponding") or []:
        ponding = np.maximum(ponding, Bowl(p["x"], p["y"], p["rx"], p["ry"], p["cap"]).eval(X, Y))
    ponding = np.where(ponding < 0.03, 0.0, ponding).astype(np.float32)
    return {"grid": grid, "hand": hand, "dem": dem, "onset": onset, "channel": channel, "ponding": ponding}


def sample_grid(arr: np.ndarray, grid: Grid, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    col = np.clip(((np.asarray(x) - grid.x0) / grid.res).astype(int), 0, grid.nx - 1)
    row = np.clip(((grid.y1 - np.asarray(y)) / grid.res).astype(int), 0, grid.ny - 1)
    return arr[row, col]


def write_raster(path: Path, arr: np.ndarray, frame: LocalFrame, grid: Grid, dtype: str = "float32",
                 nodata: float | None = None, tags: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    e0, n0 = frame.local_to_utm(grid.x0, grid.y1)
    transform = from_origin(e0, n0, grid.res, grid.res)
    profile = {
        "driver": "GTiff", "height": grid.ny, "width": grid.nx, "count": 1, "dtype": dtype,
        "crs": f"EPSG:{frame.epsg}", "transform": transform, "compress": "deflate", "tiled": True,
        "blockxsize": 256, "blockysize": 256,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)
        dst.update_tags(DEMO="true", NOTE=DEMO_NOTE, MODE="SIMULATION", **(tags or {}))


# ----------------------------------------------------------------------------------- roads
def _seg_samples(coords: list[tuple[float, float]], step: float = 20.0) -> tuple[np.ndarray, np.ndarray]:
    line = LineString(coords)
    n = max(2, int(line.length / step) + 1)
    pts = [line.interpolate(d) for d in np.linspace(0, line.length, n)]
    return np.array([p.x for p in pts]), np.array([p.y for p in pts])


def _closure_level(hand: np.ndarray, onset: np.ndarray, emb: float) -> float:
    return float(np.min(np.maximum(onset, hand + emb + CLOSED_DEPTH_M)))


def _solve_embankment(hand: np.ndarray, onset: np.ndarray, target: float) -> float:
    lo, hi = 0.0, 6.0
    if _closure_level(hand, onset, lo) >= target:
        return 0.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if _closure_level(hand, onset, mid) < target:
            lo = mid
        else:
            hi = mid
    return round(hi, 3)


def build_roads(spec: dict, terr: dict) -> tuple[dict, list[dict], list[dict]]:
    nodes = {k: (float(v[0]), float(v[1])) for k, v in spec["nodes"].items()}
    grid: Grid = terr["grid"]
    segments: list[dict] = []
    bridges: list[dict] = []
    counters: dict[str, int] = {}
    used_nodes: set[str] = set()
    seen_pairs: set[frozenset] = set()
    for road in spec["roads"]:
        seq = road["nodes"]
        for a, b in zip(seq[:-1], seq[1:], strict=True):
            if a not in nodes or b not in nodes:
                raise KeyError(f"road {road['id']} references unknown node {a} or {b}")
            pair = frozenset((a, b))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            counters[road["id"]] = counters.get(road["id"], 0) + 1
            seg_id = f"{road['id']}-{counters[road['id']]}"
            key = f"{a}>{b}"
            coords = [nodes[a], nodes[b]]
            xs, ys = _seg_samples(coords)
            hand = sample_grid(terr["hand"], grid, xs, ys)
            onset = sample_grid(terr["onset"], grid, xs, ys)
            bridge_def = (road.get("bridges") or {}).get(key)
            close_h = (road.get("segment_close_at_h") or {}).get(key, road.get("close_at_h"))
            seg_emb = (road.get("segment_embankment") or {}).get(key)
            if bridge_def:
                emb = 0.0
            elif seg_emb is not None:
                emb = float(seg_emb)
            elif close_h is not None:
                emb = _solve_embankment(hand, onset, close_h)
            else:
                emb = float(road.get("embankment", 0.3))
            length = LineString(coords).length
            seg = {
                "id": seg_id, "road_id": road["id"], "u": a, "v": b, "coords": coords, "class": road["class"],
                "speed": road["speed"], "names": road["names"], "embankment": emb, "length": round(length, 1),
                "bridge_id": bridge_def["id"] if bridge_def else None, "key": key,
            }
            segments.append(seg)
            used_nodes.update((a, b))
            if bridge_def:
                mx, my = (nodes[a][0] + nodes[b][0]) / 2, (nodes[a][1] + nodes[b][1]) / 2
                bridges.append({"id": bridge_def["id"], "names": bridge_def["names"], "xy": (mx, my),
                                "segment_ids": [seg_id], "clearance": bridge_def["clearance"]})
    nodes = {k: v for k, v in nodes.items() if k in used_nodes}
    return nodes, segments, bridges


# ----------------------------------------------------------------------------------- buildings
def build_buildings(spec: dict, terr: dict, segments: list[dict], rng: np.random.Generator) -> list[dict]:
    grid: Grid = terr["grid"]
    lines = [LineString(s["coords"]) for s in segments]
    road_tree = STRtree(lines)
    sectors = {s["id"]: Polygon(s["polygon"]) for s in spec["sectors"]}
    placed_hash: dict[tuple[int, int], list[Polygon]] = {}
    cell_size = 80.0

    def _neighbours(poly: Polygon) -> list[Polygon]:
        cx, cy = int(poly.centroid.x // cell_size), int(poly.centroid.y // cell_size)
        res: list[Polygon] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                res.extend(placed_hash.get((cx + dx, cy + dy), []))
        return res

    def _place(poly: Polygon) -> None:
        key = (int(poly.centroid.x // cell_size), int(poly.centroid.y // cell_size))
        placed_hash.setdefault(key, []).append(poly)

    out: list[dict] = []
    fac_pts = [Point(f["xy"]) for f in spec["facilities"]] + [Point(s["xy"]) for s in spec["task_sites"]]
    fac_tree = STRtree(fac_pts)
    # facility buildings first
    for f in spec["facilities"]:
        x, y = f["xy"]
        w, h = (60, 40) if f["type"] in ("HOSPITAL", "SCHOOL", "SHELTER") else (34, 26)
        poly = box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
        _place(poly)
        out.append({"id": f"BLD-{f['id']}", "poly": poly, "use": "public", "floors": 3 if f["type"] == "HOSPITAL" else 2,
                    "sector": f.get("sector")})
    counter = 0
    for zone in spec["building_zones"]:
        sector_poly = sectors[zone["sector"]]
        minx, miny, maxx, maxy = sector_poly.bounds
        s = zone["spacing"]
        core = zone.get("core")
        for gx in np.arange(minx + s / 2, maxx, s):
            for gy in np.arange(miny + s / 2, maxy, s):
                x = gx + rng.uniform(-0.3, 0.3) * s
                y = gy + rng.uniform(-0.3, 0.3) * s
                p = Point(x, y)
                if not sector_poly.contains(p):
                    continue
                hand_here = float(sample_grid(terr["hand"], grid, np.array([x]), np.array([y]))[0])
                if hand_here < 0.35:  # channel / river bank
                    continue
                nearest_line = lines[int(road_tree.nearest(p))]
                d = nearest_line.distance(p)
                if d < 16 or d > 170:
                    continue
                if fac_pts[int(fac_tree.nearest(p))].distance(p) < 45:
                    continue
                in_core = bool(core) and core[0][0] <= x <= core[1][0] and core[0][1] <= y <= core[1][1]
                floors = int(rng.choice(zone["core_floors"] if in_core else zone["floors"]))
                if floors >= 5:
                    w, h = rng.uniform(13, 16), rng.uniform(32, 48)
                else:
                    w, h = rng.uniform(8, 13), rng.uniform(9, 16)
                # orient along the nearest road
                (x1, y1), (x2, y2) = nearest_line.coords[0], nearest_line.coords[-1]
                ang = math.atan2(y2 - y1, x2 - x1)
                ca, sa = math.cos(ang), math.sin(ang)
                corners = [(-h / 2, -w / 2), (h / 2, -w / 2), (h / 2, w / 2), (-h / 2, w / 2)]
                poly = Polygon([(x + cx * ca - cy * sa, y + cx * sa + cy * ca) for cx, cy in corners])
                if any(poly.distance(q) < 4 for q in _neighbours(poly)):
                    continue
                if nearest_line.distance(poly) < 7:
                    continue
                _place(poly)
                counter += 1
                use = "residential"
                if in_core and rng.random() < 0.25 or rng.random() < 0.04:
                    use = "commercial"
                out.append({"id": f"BLD-{spec['id'][:3].upper()}-{counter:05d}", "poly": poly, "use": use,
                            "floors": floors, "sector": zone["sector"]})
    return out


# ----------------------------------------------------------------------------------- hydrology
def stage_series(hyd: dict, member: dict) -> list[tuple[int, float]]:
    common = hyd["common"]
    t_issue, s_issue = common[-1]
    base, tau = hyd["recession_base_cm"], hyd["recession_tau_h"]
    out = []
    for m in range(FRAME_OFFSETS_MIN[0], FRAME_OFFSETS_MIN[-1] + 1, SERIES_STEP_MIN):
        t = m / 60.0
        if t <= t_issue:
            ts = [c[0] for c in common]
            ss = [c[1] for c in common]
            s = float(np.interp(t, ts, ss))
        elif t <= 0:
            s = s_issue + (member["s0"] - s_issue) * (t - t_issue) / (0 - t_issue)
        elif t <= member["tp"]:
            u = t / member["tp"]
            s = member["s0"] + (member["peak"] - member["s0"]) * (1 - (1 - u) ** 2)
        else:
            s = member["peak"] - (member["peak"] - base) * (1 - math.exp(-(t - member["tp"]) / tau))
        out.append((m, round(s, 2)))
    return out


def snow_series(hyd: dict, member: dict) -> list[tuple[int, float]] | None:
    if "snowmelt_start_h" not in hyd:
        return None
    a, b = hyd["snowmelt_start_h"], hyd["snowmelt_full_h"]
    out = []
    for m in range(FRAME_OFFSETS_MIN[0], FRAME_OFFSETS_MIN[-1] + 1, SERIES_STEP_MIN):
        t = m / 60.0
        f = min(max((t - a) / (b - a), 0.0), 1.0) * member.get("snow", 1.0)
        out.append((m, round(f, 4)))
    return out


# ----------------------------------------------------------------------------------- helpers
def _fc(features: list[dict], **props: Any) -> dict:
    return {"type": "FeatureCollection", "demo": True, "note": DEMO_NOTE, **props, "features": features}


def _feat(geom, props: dict) -> dict:  # type: ignore[no-untyped-def]
    return {"type": "Feature", "geometry": mapping(geom), "properties": props}


def _names(n: dict) -> dict:
    return {"name_kk": n.get("kk"), "name_ru": n.get("ru"), "name_en": n.get("en"),
            "name_original": n.get("original") or n.get("ru")}


def local_time(spec: dict, hhmm: str) -> str:
    tz = timezone(timedelta(minutes=spec["utc_offset_min"]))
    ref = datetime.fromisoformat(spec["reference_time_local"]).replace(tzinfo=tz)
    h, m = (int(x) for x in hhmm.split(":"))
    return ref.replace(hour=h, minute=m).isoformat()


# ----------------------------------------------------------------------------------- main
def generate_area(spec: dict, out_root: Path) -> dict[str, Any]:
    out = out_root / spec["id"]
    out.mkdir(parents=True, exist_ok=True)
    frame = LocalFrame(spec["center"][0], spec["center"][1], spec["epsg"])
    rng = np.random.default_rng(abs(hash(spec["id"])) % (2**32) if False else sum(map(ord, spec["id"])))
    terr = build_terrain(spec)
    grid: Grid = terr["grid"]
    tags = {"AREA": spec["id"]}
    write_raster(out / "terrain" / "dem.tif", terr["dem"], frame, grid, tags={**tags, "LAYER": "dem"})
    write_raster(out / "terrain" / "hand.tif", terr["hand"], frame, grid, tags={**tags, "LAYER": "hand"})
    write_raster(out / "terrain" / "onset.tif", terr["onset"], frame, grid, tags={**tags, "LAYER": "onset"})
    write_raster(out / "terrain" / "channel.tif", terr["channel"].astype(np.uint8), frame, grid, dtype="uint8",
                 tags={**tags, "LAYER": "channel"})
    if spec.get("ponding"):
        write_raster(out / "terrain" / "ponding_cap.tif", terr["ponding"], frame, grid,
                     tags={**tags, "LAYER": "ponding_capacity"})

    nodes, segments, bridges = build_roads(spec, terr)
    ll = frame.local_to_ll

    # roads
    road_feats = []
    for s in segments:
        geom = LineString([ll(*c) for c in s["coords"]])
        road_feats.append(_feat(geom, {
            "id": s["id"], "road_id": s["road_id"], "road_class": s["class"], "speed_kmh": s["speed"],
            "u": s["u"], "v": s["v"], "length_m": s["length"], "bridge_id": s["bridge_id"],
            "embankment_m": s["embankment"], "key": s["key"], **_names(s["names"]), "source": "DEMO",
        }))
    node_feats = [_feat(Point(ll(*xy)), {"id": k}) for k, xy in nodes.items()]
    _dump(out / "roads.geojson", _fc(road_feats, nodes=node_feats))
    bridge_feats = [_feat(Point(ll(*b["xy"])), {"id": b["id"], **_names(b["names"]), "segment_ids": b["segment_ids"],
                                                   "deck_clearance_m": b["clearance"], "structure_type": "BRIDGE"})
                    for b in bridges]
    _dump(out / "bridges.geojson", _fc(bridge_feats))
    seg_by_key = {s["key"]: s["id"] for s in segments}
    seg_by_key.update({f"{s['v']}>{s['u']}": s["id"] for s in segments})
    bn_feats = []
    for b in spec.get("bottlenecks", []):
        seg_ids = [seg_by_key[k] for k in b["segments"]]
        coords = [nodes[k.split(">")[0]] for k in b["segments"]] + [nodes[b["segments"][-1].split(">")[1]]]
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        bn_feats.append(_feat(Point(ll(cx, cy)), {"id": b["id"], "kind": b["kind"], "segment_ids": seg_ids,
                                                   "bridge_id": b.get("bridge"), "notes": b.get("notes"),
                                                   **_names(b["names"])}))
    _dump(out / "bottlenecks.geojson", _fc(bn_feats))

    # buildings
    blds = build_buildings(spec, terr, segments, rng)
    bld_feats = []
    for b in blds:
        area = b["poly"].area
        bld_feats.append(_feat(frame.geom_local_to_ll(b["poly"]), {
            "id": b["id"], "use": b["use"], "floors": b["floors"], "height_m": round(b["floors"] * 3.1 + 1.0, 1),
            "floor_area_m2": round(area * b["floors"], 1), "sector_id": b["sector"], "source": "DEMO",
        }))
    _dump(out / "buildings.geojson", _fc(bld_feats))

    # sectors & population zones (aggregated synthetic population: floor area / 32 m² per person)
    sector_feats, zone_feats = [], []
    res_blds = [b for b in blds if b["use"] == "residential"]
    cent_tree = STRtree([b["poly"].centroid for b in res_blds])
    for s in spec["sectors"]:
        poly = Polygon(s["polygon"])
        sector_feats.append(_feat(frame.geom_local_to_ll(poly), {"id": s["id"], "code": s["id"], **_names(s["names"])}))
        minx, miny, maxx, maxy = poly.bounds
        cell = 700.0
        k = 0
        for x0 in np.arange(minx, maxx, cell):
            for y0 in np.arange(miny, maxy, cell):
                z = poly.intersection(box(x0, y0, x0 + cell, y0 + cell))
                if z.is_empty or z.area < 20000 or z.geom_type != "Polygon":
                    continue
                pop = sum(res_blds[i]["poly"].area * res_blds[i]["floors"] / 32.0
                          for i in cent_tree.query(z, predicate="contains"))
                if pop < 20:
                    continue
                k += 1
                zone_feats.append(_feat(frame.geom_local_to_ll(z), {
                    "id": f"PZ-{spec['id'][:3].upper()}-{s['id']}{k}", "sector_id": s["id"], "population": int(round(pop, -1)),
                    "vulnerable_share": round(float(rng.uniform(0.12, 0.24)), 2),
                    "source": "DEMO aggregated synthetic population (floor area / 32 m² per person)",
                }))
    _dump(out / "sectors.geojson", _fc(sector_feats))
    _dump(out / "population_zones.geojson", _fc(zone_feats))

    # facilities, bases, task sites, stations
    _dump(out / "facilities.geojson", _fc([
        _feat(Point(ll(*f["xy"])), {"id": f["id"], "facility_type": f["type"], "criticality": f["criticality"],
                                     "population_served": f["served"], "sector_id": f.get("sector"),
                                     **_names(f["names"]), "source": "DEMO", "verification": "VERIFIED"})
        for f in spec["facilities"]]))
    _dump(out / "task_sites.geojson", _fc([
        _feat(Point(ll(*t["xy"])), {"id": t["id"], "kind": t["kind"], "sector_id": t.get("sector"),
                                     "protects": t["protects"], "work_depth_limit_m": t["work_limit"],
                                     **_names(t["names"])})
        for t in spec["task_sites"]]))

    tz = timezone(timedelta(minutes=spec["utc_offset_min"]))
    ref = datetime.fromisoformat(spec["reference_time_local"]).replace(tzinfo=tz)
    hyd = spec["hydrology"]
    members = []
    for m in hyd["members"]:
        members.append({
            "id": m["id"], "label": m["label"], "peak_stage_cm": m["peak"], "peak_offset_h": m["tp"],
            "stage_series": stage_series(hyd, m), "snow_series": snow_series(hyd, m),
        })
    scenario = {
        "demo": True, "mode": "SIMULATION", "note": DEMO_NOTE,
        "family_id": f"{spec['id']}-ens-{ref:%Y%m%d}",
        "issued_at": (ref - timedelta(hours=4)).isoformat(),
        "reference_time": ref.isoformat(),
        "frame_offsets_min": FRAME_OFFSETS_MIN,
        "series_step_min": SERIES_STEP_MIN,
        "bankfull_cm": hyd["bankfull_cm"],
        "station_id": spec["stations"][0]["id"],
        "members": members,
        "issued_member": hyd["issued_member"],
        "conditioned_member": hyd["conditioned_member"],
        "provider": "synthetic_stage_hand",
        "provider_config": {"terrain_dir": f"demo/{spec['id']}/terrain", "has_ponding": bool(spec.get("ponding"))},
        "model_version": "synthetic-stage-hand-0.3 (DEMO)",
    }
    _dump(out / "scenario.json", scenario)

    obs = []
    for (h, stage, stype, verif, src) in hyd["observations"]:
        obs.append({"station_id": spec["stations"][0]["id"], "observed_at": (ref + timedelta(hours=h)).isoformat(),
                    "water_level_cm": stage, "source_type": stype, "verification": verif, "source": src,
                    "mode": "SIMULATION"})
    _dump(out / "observations.json", {"demo": True, "note": DEMO_NOTE, "observations": obs})

    area = {
        "demo": True, "note": DEMO_NOTE, "id": spec["id"], "names": spec["names"], "river_names": spec["river_names"],
        "archetype": spec["archetype"], "sort_order": spec["sort_order"], "crs_epsg": spec["epsg"],
        "center": list(spec["center"]), "utc_offset_min": spec["utc_offset_min"],
        "reference_time": ref.isoformat(),
        "grid": {"x0": grid.x0, "y1": grid.y1, "res": grid.res, "nx": grid.nx, "ny": grid.ny},
        "bbox": _bbox_ll(frame, grid),
        "stations": [{"id": s["id"], "lonlat": ll(*s["xy"]), "river": s["river"], "bankfull": s["bankfull"],
                      "watch": s["watch"], "warning": s["warning"], "critical": s["critical"], "names": s["names"]}
                     for s in spec["stations"]],
        "bases": [{"id": b["id"], "lonlat": ll(*b["xy"]), "safe": b["safe"], "names": b["names"]} for b in spec["bases"]],
        "river_centerline": [ll(float(x), float(spec["river_y"](x))) for x in
                             np.linspace(grid.x0, grid.x0 + grid.nx * grid.res, 160)],
    }
    _dump(out / "area.json", area)

    _dump(out / "resources.json", {"demo": True, "note": DEMO_NOTE, "resources": spec["resources"]})
    plans = []
    for p in spec["plans"]:
        tasks = []
        for i, t in enumerate(p["tasks"]):
            tasks.append({**t, "depart": local_time(spec, t["depart"]) if t.get("depart") else None, "sort": i})
        plans.append({**p, "tasks": tasks})
    _dump(out / "plans.json", {"demo": True, "note": DEMO_NOTE, "plans": plans,
                               "extra_candidates": spec.get("extra_candidates", [])})
    log.info("generated demo area %s: %d road segments, %d buildings", spec["id"], len(segments), len(blds))
    return {"area": spec["id"], "segments": len(segments), "buildings": len(blds), "zones": len(zone_feats)}


def _bbox_ll(frame: LocalFrame, grid: Grid) -> list[float]:
    corners = [frame.local_to_ll(grid.x0, grid.y1), frame.local_to_ll(grid.x0 + grid.nx * grid.res, grid.y1),
               frame.local_to_ll(grid.x0, grid.y1 - grid.ny * grid.res),
               frame.local_to_ll(grid.x0 + grid.nx * grid.res, grid.y1 - grid.ny * grid.res)]
    return [min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners),
            max(c[1] for c in corners)]


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def all_specs() -> list[dict]:
    from app.demo.areas import atbasar, kokshetau

    return [atbasar.SPEC, kokshetau.SPEC]


def generate_all(out_root: Path) -> list[dict]:
    return [generate_area(spec, out_root) for spec in all_specs()]
