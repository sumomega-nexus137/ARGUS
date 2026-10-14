"""Shared transforms from an installed real-data pack to ARGUS fixture contracts.

Everything here is deterministic. Real observations (OSM geometry, Copernicus DEM, WorldPop, JRC,
official records) are passed through with provenance; operational planning objects that have no real
source (resources, planning sites, exercise plans) are created elsewhere and labelled SIMULATION.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from shapely.geometry import LineString, Point, box, mapping
from shapely.ops import linemerge, unary_union

# Operational movement speeds by OSM class (km/h) for emergency vehicles in flood conditions.
# ASSUMPTION (configurable): OSMnx imputes speeds from sparse maxspeed tags (e.g. 88 km/h on
# unclassified streets), which is unrealistic for flood response; ARGUS caps them by class.
SPEED_CAP_KMH = {
    "motorway": 80, "trunk": 70, "primary": 60, "secondary": 50, "tertiary": 40, "unclassified": 35,
    "residential": 30, "living_street": 15, "service": 20,
}
# ARGUS default facility criticality POLICY (0–100) by type — an assumption requiring specialist review,
# replacing the pack's uniform placeholder 50. Exposed verbatim in the UI as an assumption.
FACILITY_CRITICALITY_POLICY = {
    "HOSPITAL": 100, "FIRE_STATION": 90, "POLICE": 80, "CLINIC": 70, "KINDERGARTEN": 65, "SCHOOL": 60,
    "DOCTORS": 50, "PHARMACY": 40, "DENTIST": 30,
}
CLASS_RANK = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3, "tertiary": 4, "unclassified": 5,
              "residential": 6, "living_street": 7, "service": 8}


def load_json(p: Path) -> Any:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dump_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def clean_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return s or None


def base_class(c: str) -> str:
    c = (c or "unclassified").split(";")[0].replace("_link", "")
    return c if c in SPEED_CAP_KMH else "unclassified"


class Projector:
    def __init__(self, epsg: int):
        self.fwd = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        self.inv = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)

    def xy(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self.fwd.transform(lon, lat)
        return float(x), float(y)

    def ll(self, x: float, y: float) -> list[float]:
        lon, lat = self.inv.transform(x, y)
        return [round(float(lon), 7), round(float(lat), 7)]


# --------------------------------------------------------------------------------------------- roads
def build_roads(pack: Path, epsg: int, prefix: str = "") -> dict:
    """OSMnx directed edges → one undirected segment per (u, v, key), largest connected component.

    Emergency movement ignores one-way restrictions (documented assumption)."""
    proj = Projector(epsg)
    g = gpd.read_file(pack / "processed" / "argus_roads.geojson")
    nodes_g = gpd.read_file(pack / "processed" / "argus_road_nodes.geojson")
    node_ll = {r.id: (float(r.geometry.x), float(r.geometry.y)) for r in nodes_g.itertuples()}
    seen: set[tuple] = set()
    segs: list[dict] = []
    for r in g.itertuples():
        u, v = str(r.u_node), str(r.v_node)
        if u == v or u not in node_ll or v not in node_ll:
            continue
        parts = str(r.id).split("-")
        key = parts[-1] if parts else "0"
        k = (min(u, v), max(u, v), key)
        if k in seen:
            continue
        seen.add(k)
        geom = r.geometry
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type == "MultiLineString":
            geom = linemerge(geom)
            if geom.geom_type != "LineString":
                geom = max(geom.geoms, key=lambda x: x.length)
        cls = base_class(str(r.road_class))
        name = clean_str(r.name_original) or clean_str(r.name_ru) or clean_str(r.name_kk) or clean_str(r.name_en)
        segs.append({
            "id": f"{prefix}S{len(segs) + 1:04d}", "osm_edge": str(r.id), "osm_way": str(r.road_id), "u": u, "v": v,
            "road_class": cls, "length_m": float(r.length_m), "geom": geom, "name": name,
            "speed_kmh": float(min(float(r.speed_kmh or SPEED_CAP_KMH[cls]), SPEED_CAP_KMH[cls])),
            "osm_bridge": clean_str(r.bridge_id),
        })
    # largest connected component (union-find)
    parent: dict[str, str] = {}

    def find(a: str) -> str:
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for s in segs:
        parent[find(s["u"])] = find(s["v"])
    comp: dict[str, int] = defaultdict(int)
    for s in segs:
        comp[find(s["u"])] += 1
    main = max(comp, key=comp.get) if comp else None
    dropped = sum(1 for s in segs if find(s["u"]) != main)
    segs = [s for s in segs if find(s["u"]) == main]
    used = {s["u"] for s in segs} | {s["v"] for s in segs}
    short = {nid: f"{prefix}N{i + 1:04d}" for i, nid in enumerate(sorted(used))}

    # group segments into named "roads" for display / closure countdowns:
    # named streets by name, unnamed ones by OSM way id.
    road_key: dict[str, str] = {}
    road_list: list[str] = []
    for s in sorted(segs, key=lambda s: (CLASS_RANK.get(s["road_class"], 9), s["name"] or "~", s["osm_way"])):
        k = f"name:{s['name']}" if s["name"] else f"way:{s['osm_way']}"
        if k not in road_key:
            road_key[k] = f"{prefix}R{len(road_list) + 1}"
            road_list.append(k)
        s["road_id"] = road_key[k]

    nodes = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(node_ll[n][0], 7), round(node_ll[n][1], 7)]},
              "properties": {"id": short[n], "osm_node": n}} for n in sorted(used)]
    feats = []
    for s in segs:
        coords = [[round(float(x), 7), round(float(y), 7)] for x, y in s["geom"].coords]
        nm = s["name"]
        # unnamed OSM ways get a factual label (road class + ARGUS road id) — never an invented street name
        cls_kk, cls_ru, cls_en = ROAD_CLASS_LABEL.get(s["road_class"], ROAD_CLASS_LABEL["other"])
        label_en = nm or f"{cls_en} · {s['road_id']}"
        label_ru = nm or f"{cls_ru} · {s['road_id']}"
        label_kk = nm or f"{cls_kk} · {s['road_id']}"
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords}, "properties": {
            "id": s["id"], "road_id": s["road_id"], "road_class": s["road_class"], "speed_kmh": round(s["speed_kmh"], 1),
            "u": short[s["u"]], "v": short[s["v"]], "length_m": round(s["length_m"], 1), "bridge_id": None,
            "embankment_m": 0.0, "osm_edge": s["osm_edge"], "osm_way": s["osm_way"],
            "name_kk": label_kk, "name_ru": label_ru, "name_en": label_en, "name_original": nm, "source": "OpenStreetMap (ODbL)",
        }})
    osm_to_seg = {}
    for s in segs:
        osm_to_seg[(s["u"], s["v"], s["osm_edge"].split("-")[-1])] = s["id"]
        osm_to_seg[(s["v"], s["u"], s["osm_edge"].split("-")[-1])] = s["id"]
    return {"type": "FeatureCollection", "nodes": nodes, "features": feats,
            "_meta": {"segments": len(feats), "nodes": len(nodes), "dropped_disconnected_segments": dropped,
                      "roads": len(road_list)},
            "_osm_to_seg": osm_to_seg, "_short": short, "_proj": proj}


# ------------------------------------------------------------------------------------------- sectors
def grid_sectors(buildings: gpd.GeoDataFrame, epsg: int, cell_m: float, min_buildings: int, names_fmt: dict) -> list[dict]:
    """Analysis-grid sectors (NOT administrative boundaries) over the built-up area."""
    b = buildings.to_crs(epsg)
    c = b.geometry.centroid
    x0, y0 = math.floor(c.x.min() / cell_m) * cell_m, math.floor(c.y.min() / cell_m) * cell_m
    x1, y1 = math.ceil(c.x.max() / cell_m) * cell_m, math.ceil(c.y.max() / cell_m) * cell_m
    ncol, nrow = int((x1 - x0) / cell_m), int((y1 - y0) / cell_m)
    col = ((c.x - x0) // cell_m).astype(int).clip(0, ncol - 1)
    row = ((y1 - c.y) // cell_m).astype(int).clip(0, nrow - 1)
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for r_, c_ in zip(row, col, strict=True):
        counts[(int(r_), int(c_))] += 1
    proj = Projector(epsg)
    out = []
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    for (r_, c_), n in sorted(counts.items()):
        if n < min_buildings:
            continue
        code = f"{letters[r_ % len(letters)]}{c_ + 1}"
        cell = box(x0 + c_ * cell_m, y1 - (r_ + 1) * cell_m, x0 + (c_ + 1) * cell_m, y1 - r_ * cell_m)
        ring = [proj.ll(x, y) for x, y in cell.exterior.coords]
        out.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {
            "id": code, "code": code, "name_kk": names_fmt["kk"].format(code=code), "name_ru": names_fmt["ru"].format(code=code),
            "name_en": names_fmt["en"].format(code=code), "name_original": names_fmt["ru"].format(code=code),
            "buildings": n, "kind": "ANALYSIS_GRID_CELL",
        }})
    return out


def sector_of(points_ll: list[tuple[float, float]], sectors: list[dict]) -> list[str | None]:
    from shapely import STRtree, points
    from shapely.geometry import shape

    polys = [shape(s["geometry"]) for s in sectors]
    codes = [s["properties"]["code"] for s in sectors]
    tree = STRtree(polys)
    pts = points([p[0] for p in points_ll], [p[1] for p in points_ll])
    res: list[str | None] = [None] * len(points_ll)
    for pi, si in zip(*tree.query(pts, predicate="within"), strict=True):
        res[int(pi)] = codes[int(si)]
    # snap outliers to the nearest sector so every building/facility belongs to one
    if any(r is None for r in res):
        cents = np.array([[p.centroid.x, p.centroid.y] for p in polys])
        for i, r in enumerate(res):
            if r is None:
                d = (cents[:, 0] - points_ll[i][0]) ** 2 + (cents[:, 1] - points_ll[i][1]) ** 2
                res[i] = codes[int(np.argmin(d))]
    return res


# ----------------------------------------------------------------------------------------- buildings
def build_buildings(pack: Path, epsg: int, sectors: list[dict], prefix: str = "") -> tuple[list[dict], gpd.GeoDataFrame]:
    g = gpd.read_file(pack / "processed" / "argus_buildings.geojson")
    g = g[g.geometry.notna() & g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gp = g.to_crs(epsg)
    area = gp.geometry.area.to_numpy()
    floors = np.clip(np.nan_to_num(g["floors"].astype(float).to_numpy(), nan=1.0), 1, 30)
    cent = gp.geometry.centroid.to_crs(4326)
    secs = sector_of(list(zip(cent.x, cent.y, strict=True)), sectors)
    feats = []
    for i, (row, a, fl, sec) in enumerate(zip(g.itertuples(), area, floors, secs, strict=True)):
        use = str(row.use) if clean_str(row.use) else "unknown"
        geom = row.geometry.simplify(0.000005, preserve_topology=True)
        feats.append({"type": "Feature", "geometry": mapping(geom), "properties": {
            "id": f"{prefix}B{i + 1:05d}", "use": use, "floors": int(fl), "height_m": round(float(fl) * 3.0, 1),
            "floor_area_m2": round(float(a * fl), 1), "footprint_m2": round(float(a), 1), "sector_id": sec,
            "source": "OpenStreetMap (ODbL); floor area = footprint × levels (default 1 level)",
        }})
    g = g.assign(argus_id=[f["properties"]["id"] for f in feats], floor_area=[f["properties"]["floor_area_m2"] for f in feats],
                 sector=secs)
    return feats, g


def population_zones(pack: Path, buildings: gpd.GeoDataFrame, epsg: int, prefix: str = "") -> tuple[list[dict], dict]:
    """WorldPop 2024 (100 m, modelled) → one zone per populated 100 m cell containing mapped buildings.

    Population is later allocated dasymetrically to the buildings inside each cell by floor area."""
    wp = pack / "processed" / "worldpop_2024_100m_utm42n.tif"
    proj = Projector(epsg)
    with rasterio.open(wp) as src:
        arr = src.read(1, masked=True).filled(0).astype(float)
        tr = src.transform
        crs = src.crs.to_epsg()
    if crs != epsg:
        raise ValueError(f"WorldPop CRS {crs} != area CRS {epsg}")
    bp = buildings.to_crs(epsg)
    cx, cy = bp.geometry.centroid.x.to_numpy(), bp.geometry.centroid.y.to_numpy()
    inv = ~tr
    cols = np.floor(inv.a * cx + inv.b * cy + inv.c).astype(int)
    rows = np.floor(inv.d * cx + inv.e * cy + inv.f).astype(int)
    h, w = arr.shape
    ok = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i in np.flatnonzero(ok):
        cells[(int(rows[i]), int(cols[i]))].append(int(i))
    total = float(arr.sum())
    allocated = 0.0
    feats = []
    for (r_, c_), idx in sorted(cells.items()):
        pop = float(arr[r_, c_])
        if pop <= 0:
            continue
        allocated += pop
        x0, y0 = tr.c + c_ * tr.a, tr.f + r_ * tr.e
        x1, y1 = x0 + tr.a, y0 + tr.e
        ring = [proj.ll(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]
        secs = buildings.iloc[idx]["sector"].tolist()
        sec = max(set(secs), key=secs.count) if secs else None
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {
            "id": f"{prefix}PZ-{r_}-{c_}", "sector_id": sec, "population": int(round(pop)), "vulnerable_share": None,
            "source": "WorldPop 2024 constrained 100 m (modelled estimate); no age-structure layer → vulnerable share not available",
        }})
    meta = {"worldpop_total_in_pack": round(total), "allocated_to_building_cells": round(allocated),
            "not_allocated_no_mapped_buildings": round(total - allocated), "zones": len(feats)}
    return feats, meta


# ---------------------------------------------------------------------------------------- facilities
ROAD_CLASS_LABEL = {  # OSM highway class → kk / ru / en label for unnamed ways
    "motorway": ("Автомагистраль", "Автомагистраль", "Motorway"),
    "trunk": ("Республикалық жол", "Магистральная дорога", "Trunk road"),
    "primary": ("Негізгі жол", "Главная дорога", "Primary road"),
    "secondary": ("Екінші деңгейлі жол", "Второстепенная дорога", "Secondary road"),
    "tertiary": ("Жергілікті жол", "Местная дорога", "Tertiary road"),
    "unclassified": ("Көше", "Улица", "Street"),
    "residential": ("Тұрғын көше", "Жилая улица", "Residential street"),
    "living_street": ("Тұрғын аймақ көшесі", "Жилая зона", "Living street"),
    "service": ("Қызметтік жол", "Служебный проезд", "Service road"),
    "other": ("Көше", "Улица", "Street"),
}


def build_facilities(pack: Path, sectors: list[dict], prefix: str = "") -> list[dict]:
    g = gpd.read_file(pack / "processed" / "argus_critical_facilities.geojson")
    g = g[g.geometry.notna()].copy()
    pts = [geom if geom.geom_type == "Point" else geom.representative_point() for geom in g.geometry]
    secs = sector_of([(p.x, p.y) for p in pts], sectors)
    type_kk = {"HOSPITAL": "Аурухана", "CLINIC": "Емхана", "SCHOOL": "Мектеп", "KINDERGARTEN": "Балабақша",
               "POLICE": "Полиция", "FIRE_STATION": "Өрт сөндіру бөлімі", "PHARMACY": "Дәріхана", "DOCTORS": "Дәрігерлік пункт",
               "DENTIST": "Стоматология"}
    type_ru = {"HOSPITAL": "Больница", "CLINIC": "Поликлиника", "SCHOOL": "Школа", "KINDERGARTEN": "Детский сад",
               "POLICE": "Полиция", "FIRE_STATION": "Пожарная часть", "PHARMACY": "Аптека", "DOCTORS": "Врачебный пункт",
               "DENTIST": "Стоматология"}
    type_en = {"HOSPITAL": "Hospital", "CLINIC": "Clinic", "SCHOOL": "School", "KINDERGARTEN": "Kindergarten",
               "POLICE": "Police", "FIRE_STATION": "Fire station", "PHARMACY": "Pharmacy", "DOCTORS": "Doctors' office",
               "DENTIST": "Dentist"}
    out = []
    for i, (row, p, sec) in enumerate(zip(g.itertuples(), pts, secs, strict=True)):
        t = str(row.facility_type)
        orig, n_kk, n_ru, n_en = (clean_str(row.name_original), clean_str(row.name_kk), clean_str(row.name_ru),
                                  clean_str(row.name_en))
        nm = orig or n_ru or n_kk or n_en
        fid = f"{prefix}F{i + 1:03d}"
        # localized OSM name priority: name:<lang> → name → other names; without any OSM name a factual
        # "type · #id" label (no invented proper name)
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(p.x, 7), round(p.y, 7)]}, "properties": {
            "id": fid, "facility_type": t, "osm_id": str(row.id),
            "criticality": FACILITY_CRITICALITY_POLICY.get(t, 40), "population_served": 0, "sector_id": sec,
            "name_kk": (n_kk or orig or n_ru or n_en) or f"{type_kk.get(t, t)} · #{fid}",
            "name_ru": (n_ru or orig or n_kk or n_en) or f"{type_ru.get(t, t)} · #{fid}",
            "name_en": (n_en or orig or n_ru or n_kk) or f"{type_en.get(t, t.replace('_', ' ').title())} · #{fid}",
            "name_original": nm, "named_in_osm": bool(nm),
            "source": "OpenStreetMap candidate (ODbL)", "verification": "UNVERIFIED",
            "criticality_note": "ARGUS default policy by facility type — assumption, requires specialist review",
        }})
    return out


def build_bridges(pack: Path, roads: dict, deck_clearance_m: float, prefix: str = "") -> list[dict]:
    g = gpd.read_file(pack / "processed" / "osm_bridges_culverts.geojson")
    o2s = roads["_osm_to_seg"]
    seg_by_id = {f["properties"]["id"]: f for f in roads["features"]}
    out, used = [], set()
    for row in g.itertuples():
        u, v, k = f"osm-node-{row.u}", f"osm-node-{row.v}", str(row.key)
        sid = o2s.get((u, v, k))
        if sid is None or sid in used:
            continue
        used.add(sid)
        seg = seg_by_id[sid]
        line = LineString(seg["geometry"]["coordinates"])
        mid = line.interpolate(0.5, normalized=True)
        nm = clean_str(row.name) or clean_str(getattr(row, "ref", None))
        bid = f"{prefix}BR{len(out) + 1:02d}"
        seg["properties"]["bridge_id"] = bid
        out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(mid.x, 7), round(mid.y, 7)]}, "properties": {
            "id": bid, "segment_ids": [sid], "deck_clearance_m": deck_clearance_m, "structure_type": "BRIDGE",
            "name_kk": f"{bid} көпірі" + (f" · {nm}" if nm else ""), "name_ru": f"Мост {bid}" + (f" · {nm}" if nm else ""),
            "name_en": f"Bridge {bid}" + (f" · {nm}" if nm else ""), "name_original": nm,
            "osm_highway": clean_str(row.highway), "clearance_note": "ASSUMED deck clearance (no survey) — configurable",
        }})
    return out


def waterways_layer(pack: Path, river_name_pattern: str) -> tuple[dict, list[list[list[float]]]]:
    """Map layer of OSM water features + the main-river centreline parts (for the river layer)."""
    import re

    g = gpd.read_file(pack / "processed" / "osm_waterways.geojson")
    keep, river_lines = [], []
    for _, row in g.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        ww = clean_str(row.get("waterway"))
        nat = clean_str(row.get("natural"))
        name = clean_str(row.get("name")) or clean_str(row.get("name:ru")) or clean_str(row.get("name:kk"))
        names = " ".join(str(row.get(c) or "") for c in ("name", "name:ru", "name:kk", "name:en")).lower()
        if geom.geom_type in ("LineString", "MultiLineString") and ww in ("river", "stream", "canal", "ditch", "drain"):
            keep.append({"type": "Feature", "geometry": mapping(geom.simplify(0.00002)), "properties": {"kind": ww, "name": name}})
            if ww == "river" and re.search(river_name_pattern, names):
                for part in (geom.geoms if geom.geom_type == "MultiLineString" else [geom]):
                    river_lines.append([[round(x, 6), round(y, 6)] for x, y in part.simplify(0.00005).coords])
        elif geom.geom_type in ("Polygon", "MultiPolygon"):
            keep.append({"type": "Feature", "geometry": mapping(geom.simplify(0.00003)),
                         "properties": {"kind": clean_str(row.get("water")) or nat or "water", "name": name}})
    return {"type": "FeatureCollection", "features": keep}, river_lines


def merged_river(pack: Path, pattern: str, epsg: int):  # type: ignore[no-untyped-def]
    g = gpd.read_file(pack / "processed" / "osm_waterways.geojson")
    cols = [c for c in ("name", "name:ru", "name:kk", "name:en") if c in g.columns]
    m = np.zeros(len(g), dtype=bool)
    for c in cols:
        m |= g[c].fillna("").astype(str).str.lower().str.contains(pattern, regex=True).to_numpy()
    if "waterway" in g.columns:
        m &= g["waterway"].fillna("").astype(str).str.lower().eq("river").to_numpy()
    r = g[m & g.geometry.geom_type.isin(["LineString", "MultiLineString"]).to_numpy()]
    if r.empty:
        raise RuntimeError(f"river /{pattern}/ not found in OSM waterways")
    return unary_union(list(r.to_crs(epsg).geometry))


def nearest_node_id(nodes: list[dict], proj: Projector, x: float, y: float) -> tuple[str, float]:
    best, bd = "", float("inf")
    for n in nodes:
        nx, ny = proj.xy(*n["geometry"]["coordinates"])
        d = (nx - x) ** 2 + (ny - y) ** 2
        if d < bd:
            best, bd = n["properties"]["id"], d
    return best, math.sqrt(bd)


def point_feature(fid: str, lonlat: list[float], props: dict) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": lonlat}, "properties": {"id": fid, **props}}


__all__ = ["Point", "build_roads", "grid_sectors", "build_buildings", "population_zones", "build_facilities",
           "build_bridges", "waterways_layer", "merged_river", "Projector", "load_json", "dump_json"]
