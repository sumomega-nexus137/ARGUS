"""Server-side rendering of scenario frames for the map (no geospatial computation in the browser).

* depth PNG   — colour-ramped flood depth, georeferenced by the 4 grid corners (MapLibre image source)
* extent      — simplified flood outline polygons (GeoJSON) for crisp shorelines
* frame stats — flooded area / max depth / gauge stage per frame
"""

from __future__ import annotations

import io
import threading
from collections import OrderedDict

import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

from app.services.scenario.runtime import ScenarioRuntime

EXTENT_THRESHOLD_M = 0.05
# depth (m) → RGBA ramp (visual encoding documented in the map legend)
RAMP = [
    (0.00, (160, 225, 255, 0)),
    (0.05, (140, 215, 255, 120)),
    (0.30, (86, 180, 250, 160)),
    (0.70, (40, 130, 235, 185)),
    (1.20, (20, 90, 205, 205)),
    (2.00, (12, 55, 160, 220)),
    (3.50, (8, 30, 110, 235)),
]

_lock = threading.Lock()
_png_cache: OrderedDict = OrderedDict()
_ext_cache: OrderedDict = OrderedDict()


def _cache_get(cache: OrderedDict, key):  # type: ignore[no-untyped-def]
    with _lock:
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
    return None


def _cache_put(cache: OrderedDict, key, val, limit: int = 256) -> None:  # type: ignore[no-untyped-def]
    with _lock:
        cache[key] = val
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)


def colorize(depth: np.ndarray) -> np.ndarray:
    xs = np.array([r[0] for r in RAMP])
    out = np.zeros(depth.shape + (4,), dtype=np.uint8)
    d = np.nan_to_num(depth, nan=0.0)
    for ch in range(4):
        ys = np.array([r[1][ch] for r in RAMP], dtype=float)
        out[..., ch] = np.interp(d, xs, ys).astype(np.uint8)
    out[d < RAMP[1][0], 3] = 0
    return out


def depth_png(rt: ScenarioRuntime, member: str, t_min: float) -> bytes:
    key = (rt.family_id, id(rt.provider), member, round(t_min, 1))
    hit = _cache_get(_png_cache, key)
    if hit is not None:
        return hit
    depth = rt.provider.depth_grid(member, t_min)
    img = Image.fromarray(colorize(depth), "RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    _cache_put(_png_cache, key, data)
    return data


def extent_geojson(rt: ScenarioRuntime, member: str, t_min: float, simplify_m: float = 12.0) -> dict:
    key = (rt.family_id, id(rt.provider), member, round(t_min, 1), simplify_m)
    hit = _cache_get(_ext_cache, key)
    if hit is not None:
        return hit
    from rasterio.features import shapes

    grid = rt.provider.grid()
    depth = rt.provider.depth_grid(member, t_min)
    mask = (depth >= EXTENT_THRESHOLD_M).astype(np.uint8)
    polys = [shape(g) for g, v in shapes(mask, mask=mask.astype(bool), transform=grid.transform) if v == 1]
    feats = []
    if polys:
        merged = unary_union(polys).simplify(simplify_m, preserve_topology=True)
        tr = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
        ll = shp_transform(tr.transform, merged)
        geoms = list(ll.geoms) if hasattr(ll, "geoms") else [ll]
        for g in geoms:
            if g.is_empty:
                continue
            feats.append({"type": "Feature", "geometry": mapping(g), "properties": {}})
    out = {"type": "FeatureCollection", "features": feats,
           "properties": {"threshold_m": EXTENT_THRESHOLD_M, "member": member, "t_min": t_min}}
    _cache_put(_ext_cache, key, out, limit=128)
    return out


def frame_stats(rt: ScenarioRuntime, member: str) -> list[dict]:
    grid = rt.provider.grid()
    cell_km2 = abs(grid.transform.a * grid.transform.e) / 1e6
    gauge = rt.provider.gauge_series(member)
    ts = np.array([g[0] for g in gauge]) if gauge else np.array([0.0])
    ss = np.array([g[1] for g in gauge]) if gauge else np.array([np.nan])
    out = []
    for off in rt.frame_offsets:
        d = rt.provider.depth_grid(member, float(off))
        wet = d >= EXTENT_THRESHOLD_M
        out.append({"offset_min": off, "flooded_km2": round(float(wet.sum()) * cell_km2, 3),
                    "max_depth_m": round(float(d.max()) if d.size else 0.0, 2),
                    "gauge_stage_cm": round(float(np.interp(off, ts, ss)), 1) if gauge else None})
    return out
