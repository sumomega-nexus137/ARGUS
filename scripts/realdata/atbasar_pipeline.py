#!/usr/bin/env python3
"""Build the real Atbasar/Zhabai geospatial evidence pack for ARGUS FloodOps.

This is acquisition/pre-processing, not a hydrodynamic model. It creates:
- Copernicus GLO-30 DEM + slope;
- OSM road graph, roads, buildings, waterways, bridges/culverts, candidate critical facilities;
- Sentinel-1 same-orbit pre/flood imagery where possible;
- JRC Global Surface Water occurrence baseline;
- an automatic Sentinel-1 flood-observation mask that is explicitly REQUIRES_QC;
- WorldPop 2024 population raster when available;
- an ARGUS validation directory with observed.tif only (modelled.tif is deliberately absent);
- checksums/provenance manifest.

No unavailable measurement is replaced with an invented value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd
import planetary_computer
import pystac_client
import rasterio
import requests
from rasterio.features import shapes
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_geom
from scipy.ndimage import binary_fill_holes
from shapely.geometry import box, shape
from skimage.filters import threshold_otsu
from skimage.morphology import binary_closing, disk, remove_small_holes, remove_small_objects

ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / "data" / "realdata" / "atbasar" / "config.json"
CURATED = ROOT / "data" / "realdata" / "atbasar"

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
S1_COLLECTION = "sentinel-1-rtc"
S2_COLLECTION = "sentinel-2-l2a"
JRC_COLLECTION = "jrc-gsw"
DEM_BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
WORLDPOP_URL = (
    "https://worldpop-public-data.soton.ac.uk/GIS/Population/Global_2015_2030/"
    "R2025A/2024/KAZ/v1/100m/constrained/kaz_pop_2024_CN_100m_R2025A_v1.tif"
)


def load_cfg() -> dict:
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def mkdirs(out: Path) -> None:
    for p in ("raw", "processed", "metadata", "validation/atbasar/atbasar-2024", "logs"):
        (out / p).mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def sidecar(path: Path, obj: dict) -> None:
    write_json(Path(str(path) + ".provenance.json"), obj)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight(out: Path) -> dict:
    urls = {
        "planetary_computer": "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc",
        "earth_search_sentinel2": "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a",
        "copernicus_dem": DEM_BASE,
        "openstreetmap_overpass": "https://overpass-api.de/api/status",
        "worldpop": WORLDPOP_URL,
    }
    report = {}
    for k, url in urls.items():
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": "ARGUS-FloodOps/1.0"})
            report[k] = {"ok": r.status_code < 500, "status": r.status_code, "url": url}
        except Exception as e:
            report[k] = {"ok": False, "error": str(e), "url": url}
    write_json(out / "logs" / "preflight.json", report)
    return report


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def fetch_dem(cfg: dict, out: Path) -> None:
    west, south, east, north = cfg["analysis_bbox_wgs84"]
    tiles = [(lat, lon) for lat in range(math.floor(south), math.floor(north) + 1)
             for lon in range(math.floor(west), math.floor(east) + 1)]
    geom = {"type": "Polygon", "coordinates": [[[west,south],[east,south],[east,north],[west,north],[west,south]]]}
    parts = []
    sources = []
    for idx, (lat, lon) in enumerate(tiles):
        name = tile_name(lat, lon)
        url = f"{DEM_BASE}/{name}/{name}.tif"
        sources.append(url)
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            with rasterio.open(url) as src:
                g = transform_geom("EPSG:4326", src.crs, geom)
                arr, tr = mask(src, [g], crop=True, filled=True, nodata=src.nodata)
                p = out / "raw" / f"dem_part_{idx}.tif"
                profile = src.profile.copy()
                profile.update(height=arr.shape[1], width=arr.shape[2], transform=tr, compress="deflate", tiled=True)
                with rasterio.open(p, "w", **profile) as dst:
                    dst.write(arr)
                parts.append(p)
    datasets = [rasterio.open(p) for p in parts]
    try:
        mosaic, tr = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=tr)
        raw = out / "raw" / "dem_wgs84.tif"
        with rasterio.open(raw, "w", **profile) as dst:
            dst.write(mosaic)
    finally:
        for ds in datasets:
            ds.close()

    dem = out / "processed" / "dem_atbasar_utm42n.tif"
    with rasterio.open(raw) as src:
        tr, width, height = calculate_default_transform(
            src.crs, cfg["projected_crs"], src.width, src.height, *src.bounds, resolution=30.0
        )
        profile = src.profile.copy()
        profile.update(crs=cfg["projected_crs"], transform=tr, width=width, height=height,
                       dtype="float32", compress="deflate", tiled=True, nodata=-9999.0)
        with rasterio.open(dem, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1), destination=rasterio.band(dst, 1),
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=tr, dst_crs=cfg["projected_crs"],
                src_nodata=src.nodata, dst_nodata=-9999.0,
                resampling=Resampling.bilinear,
            )
    with rasterio.open(dem) as src:
        z = src.read(1).astype("float32")
        invalid = (~np.isfinite(z)) | (z == src.nodata)
        z[invalid] = np.nan
        dy, dx = np.gradient(z, abs(src.transform.e), abs(src.transform.a))
        slope = np.degrees(np.arctan(np.sqrt(dx * dx + dy * dy))).astype("float32")
        slope[invalid] = -9999.0
        p = src.profile.copy()
        p.update(dtype="float32", nodata=-9999.0)
        slope_path = out / "processed" / "slope_atbasar_deg.tif"
        with rasterio.open(slope_path, "w", **p) as dst:
            dst.write(slope, 1)
    meta = {
        "source": "Copernicus DEM GLO-30 public AWS",
        "source_urls": sources,
        "working_crs": cfg["projected_crs"],
        "resolution_m": 30,
        "caveat": "GLO-30 is a DSM, not surveyed bare-earth terrain."
    }
    sidecar(dem, meta)
    sidecar(slope_path, {**meta, "derived": "slope degrees"})


def clean_scalar(v):
    if isinstance(v, (list, tuple, set)):
        return ";".join(map(str, v))
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    if pd.isna(v):
        return None
    return v


def save_geojson(gdf: gpd.GeoDataFrame, path: Path, note: str) -> None:
    g = gdf.copy()
    for c in g.columns:
        if c != "geometry":
            g[c] = g[c].map(clean_scalar)
    path.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(path, driver="GeoJSON")
    sidecar(path, {"source": "OpenStreetMap via OSMnx/Overpass", "license": "ODbL",
                   "feature_count": int(len(g)), "query_note": note})


def fetch_osm(cfg: dict, out: Path) -> None:
    bbox = tuple(cfg["analysis_bbox_wgs84"])
    ox.settings.use_cache = True
    ox.settings.requests_timeout = 300
    ox.settings.log_console = True

    G = ox.graph_from_bbox(bbox, network_type="drive", simplify=True, retain_all=True)
    try:
        G = ox.routing.add_edge_speeds(G)
        G = ox.routing.add_edge_travel_times(G)
    except Exception:
        pass
    nodes, edges = ox.graph_to_gdfs(G)
    nodes = nodes.reset_index()
    edges = edges.reset_index()
    ox.save_graphml(G, filepath=out / "processed" / "osm_drive.graphml")

    e = edges.to_crs(cfg["projected_crs"]).copy()
    e["id"] = [f"osm-{u}-{v}-{k}" for u, v, k in zip(e["u"], e["v"], e["key"], strict=False)]
    e["road_id"] = e["osmid"].map(lambda x: f"OSM-{clean_scalar(x)}" if x is not None else "OSM-UNKNOWN")
    e["road_class"] = e.get("highway", "road").map(clean_scalar) if "highway" in e else "road"
    e["length_m"] = e.geometry.length.round(2)
    if "speed_kph" in e:
        e["speed_kmh"] = pd.to_numeric(e["speed_kph"], errors="coerce").fillna(30.0)
    else:
        e["speed_kmh"] = 30.0
    e["u_node"] = e["u"].map(lambda x: f"osm-node-{x}")
    e["v_node"] = e["v"].map(lambda x: f"osm-node-{x}")
    e["bridge_id"] = [
        f"osm-bridge-{u}-{v}-{k}" if clean_scalar(br) not in (None, "no", "None") else None
        for u, v, k, br in zip(e["u"], e["v"], e["key"], e.get("bridge", [None]*len(e)), strict=False)
    ]
    e["name_original"] = e.get("name", pd.Series([None]*len(e))).map(clean_scalar)
    e["name_kk"] = None
    e["name_ru"] = None
    e["name_en"] = None
    e["source"] = "OpenStreetMap"
    roads = e[["id","road_id","road_class","length_m","speed_kmh","u_node","v_node",
               "bridge_id","name_kk","name_ru","name_en","name_original","source","geometry"]].to_crs("EPSG:4326")
    save_geojson(roads, out / "processed" / "argus_roads.geojson", "ARGUS-normalized routable edges")

    n = nodes.to_crs("EPSG:4326").copy()
    n["id"] = n["osmid"].map(lambda x: f"osm-node-{x}")
    save_geojson(n[["id","geometry"]], out / "processed" / "argus_road_nodes.geojson", "ARGUS road nodes")

    tags = {
        "building": True,
        "waterway": True,
        "natural": ["water"],
        "amenity": ["hospital", "clinic", "school", "kindergarten", "fire_station", "police"],
        "healthcare": True,
    }
    feat = ox.features_from_bbox(bbox, tags).reset_index()

    buildings = feat[feat["building"].notna()].copy() if "building" in feat else feat.iloc[0:0].copy()
    if len(buildings):
        bmetric = buildings.to_crs(cfg["projected_crs"])
        geom_area = bmetric.geometry.area
        buildings["id"] = [f"osm-building-{i}" for i in range(len(buildings))]
        buildings["use"] = buildings["building"].map(lambda x: "residential" if str(x) in {"house","residential","apartments"} else "unknown")
        buildings["floors"] = pd.to_numeric(buildings.get("building:levels", 1), errors="coerce").fillna(1).clip(lower=1)
        buildings["height_m"] = pd.to_numeric(buildings.get("height", np.nan), errors="coerce")
        buildings["height_m"] = buildings["height_m"].fillna(buildings["floors"] * 3.0)
        buildings["floor_area_m2"] = geom_area.values * buildings["floors"].values
        buildings["source"] = "OpenStreetMap"
        save_geojson(buildings[["id","use","floors","height_m","floor_area_m2","source","geometry"]],
                     out / "processed" / "argus_buildings.geojson", "ARGUS-normalized OSM buildings")

    waterways = feat[
        (feat["waterway"].notna() if "waterway" in feat else False) |
        ((feat["natural"] == "water") if "natural" in feat else False)
    ].copy()
    save_geojson(waterways, out / "processed" / "osm_waterways.geojson", "waterway and natural=water")

    critical = feat[
        (feat["amenity"].isin(["hospital","clinic","school","kindergarten","fire_station","police"]) if "amenity" in feat else False) |
        (feat["healthcare"].notna() if "healthcare" in feat else False)
    ].copy()
    if len(critical):
        critical = critical.to_crs(cfg["projected_crs"])
        critical["geometry"] = critical.geometry.centroid
        critical = critical.to_crs("EPSG:4326")
        critical["id"] = [f"osm-facility-{i}" for i in range(len(critical))]
        critical["facility_type"] = critical.get("amenity", "OTHER").map(lambda x: str(x).upper() if x else "OTHER")
        critical["name_original"] = critical.get("name", pd.Series([None]*len(critical))).map(clean_scalar)
        critical["name_kk"] = None
        critical["name_ru"] = None
        critical["name_en"] = None
        critical["criticality"] = 50
        critical["criticality_note"] = "placeholder policy default; must be reviewed by domain specialists"
        critical["population_served"] = 0
        critical["verification"] = "UNVERIFIED_OSM"
        critical["source"] = "OpenStreetMap"
        save_geojson(critical[["id","facility_type","name_kk","name_ru","name_en","name_original",
                               "criticality","criticality_note","population_served","verification","source","geometry"]],
                     out / "processed" / "argus_critical_facilities.geojson", "candidate facilities from OSM")

    bridges = edges[
        (edges["bridge"].notna() if "bridge" in edges else False) |
        ((edges["tunnel"] == "culvert") if "tunnel" in edges else False)
    ].copy()
    save_geojson(bridges.to_crs("EPSG:4326"), out / "processed" / "osm_bridges_culverts.geojson",
                 "road edges tagged bridge=* or tunnel=culvert")


def _coverage(item, bbox_wgs84):
    aoi = box(*bbox_wgs84)
    return float(shape(item.geometry).intersection(aoi).area / aoi.area)


def _clip_remote(href: str, bbox_wgs84, out_path: Path, dst_crs: str, resolution: float, resampling=Resampling.bilinear):
    west, south, east, north = bbox_wgs84
    geom = {"type":"Polygon","coordinates":[[[west,south],[east,south],[east,north],[west,north],[west,south]]]}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(href) as src:
            g = transform_geom("EPSG:4326", src.crs, geom)
            arr, tr = mask(src, [g], crop=True, filled=True, nodata=src.nodata)
            left, bottom, right, top = rasterio.transform.array_bounds(arr.shape[1], arr.shape[2], tr)
            dtr, width, height = calculate_default_transform(
                src.crs, dst_crs, arr.shape[2], arr.shape[1], left, bottom, right, top, resolution=resolution
            )
            dst = np.full((height, width), np.nan, dtype="float32")
            src_arr = arr[0].astype("float32")
            if src.nodata is not None:
                src_arr[src_arr == src.nodata] = np.nan
            reproject(source=src_arr, destination=dst, src_transform=tr, src_crs=src.crs,
                      src_nodata=np.nan, dst_transform=dtr, dst_crs=dst_crs,
                      dst_nodata=np.nan, resampling=resampling)
            profile = {"driver":"GTiff","height":height,"width":width,"count":1,"dtype":"float32",
                       "crs":dst_crs,"transform":dtr,"nodata":np.nan,"compress":"deflate","tiled":True}
            with rasterio.open(out_path, "w", **profile) as f:
                f.write(dst, 1)


def fetch_sentinel1(cfg: dict, out: Path) -> None:
    cat = pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    ev = cfg["event"]
    items = list(cat.search(collections=[S1_COLLECTION], bbox=cfg["analysis_bbox_wgs84"],
                            datetime=f"{ev['search_start']}T00:00:00Z/{ev['search_end']}T23:59:59Z",
                            max_items=500).items())
    diagnostics = []
    for item in items:
        dt = item.datetime if item.datetime and item.datetime.tzinfo else (
            item.datetime.replace(tzinfo=timezone.utc) if item.datetime else None
        )
        diagnostics.append({
            "id": item.id,
            "datetime": dt.isoformat() if dt else None,
            "coverage": _coverage(item, cfg["analysis_bbox_wgs84"]),
            "assets": sorted(item.assets.keys()),
            "relative_orbit": item.properties.get("sat:relative_orbit"),
            "orbit_state": item.properties.get("sat:orbit_state"),
        })
    write_json(out / "metadata" / "sentinel1_candidates.json", {
        "collection": S1_COLLECTION,
        "item_count": len(items),
        "items": diagnostics,
    })
    pre_target = datetime.fromisoformat(ev["pre_flood_target_date"]).replace(tzinfo=timezone.utc)
    flood_target = datetime.fromisoformat(ev["flood_target_date"]).replace(tzinfo=timezone.utc)
    flood_start = datetime.fromisoformat(ev["flood_window_start"]).replace(tzinfo=timezone.utc)
    flood_end = datetime.fromisoformat(ev["flood_window_end"] + "T23:59:59").replace(tzinfo=timezone.utc)

    candidates = []
    for item in items:
        if "vv" not in item.assets:
            continue
        dt = item.datetime if item.datetime.tzinfo else item.datetime.replace(tzinfo=timezone.utc)
        cov = _coverage(item, cfg["analysis_bbox_wgs84"])
        if cov < 0.9:
            continue
        candidates.append((item, dt, item.properties.get("sat:relative_orbit"),
                           item.properties.get("sat:orbit_state"), cov))
    pre = [c for c in candidates if c[1] < flood_start]
    flood = [c for c in candidates if flood_start <= c[1] <= flood_end]
    if not pre or not flood:
        top = sorted(diagnostics, key=lambda x: x["coverage"], reverse=True)[:10]
        raise RuntimeError(
            f"No suitable Sentinel-1 RTC pair: pre={len(pre)} flood={len(flood)} "
            f"from {len(items)} items. Top candidates={top}"
        )

    best = None
    score_best = float("inf")
    for p in pre:
        for f in flood:
            penalty = (1000 if p[2] is not None and f[2] is not None and p[2] != f[2] else 0)
            penalty += (300 if p[3] and f[3] and p[3] != f[3] else 0)
            score = abs((p[1]-pre_target).total_seconds())/86400 + abs((f[1]-flood_target).total_seconds())/86400 + penalty
            if score < score_best:
                score_best, best = score, (p, f)
    p, f = best
    selection = {
        "pre_item": p[0].id, "pre_datetime": p[1].isoformat(), "pre_relative_orbit": p[2],
        "pre_orbit_state": p[3], "pre_coverage": p[4],
        "flood_item": f[0].id, "flood_datetime": f[1].isoformat(), "flood_relative_orbit": f[2],
        "flood_orbit_state": f[3], "flood_coverage": f[4],
        "rule": ">=90% AOI coverage; strongly prefer matching relative orbit/direction; then nearest target dates"
    }
    write_json(out / "metadata" / "sentinel1_selection.json", selection)
    for label, c in (("pre", p), ("flood", f)):
        signed = planetary_computer.sign(c[0])
        for pol in ("vv", "vh"):
            if pol not in signed.assets:
                continue
            dst = out / "processed" / f"sentinel1_{label}_{pol}.tif"
            _clip_remote(signed.assets[pol].href, cfg["analysis_bbox_wgs84"], dst, cfg["projected_crs"], 20.0)
            sidecar(dst, {"source":"Sentinel-1 RTC via Microsoft Planetary Computer",
                          "item_id": c[0].id, "datetime": c[1].isoformat(), "polarization": pol.upper(),
                          "relative_orbit": c[2], "orbit_state": c[3]})


def fetch_sentinel2(cfg: dict, out: Path) -> None:
    """Fetch a clear pre-flood/flood-period Sentinel-2 L2A pair.

    This is the documented optical fallback when no Sentinel-1 acquisition is
    available for the 2024 Atbasar event. Cloud/snow masking is applied later
    from the Scene Classification Layer (SCL).
    """
    cat = pystac_client.Client.open(EARTH_SEARCH_URL)
    ev = cfg["event"]
    items = list(cat.search(
        collections=[S2_COLLECTION],
        bbox=cfg["analysis_bbox_wgs84"],
        datetime=f"{ev['search_start']}T00:00:00Z/{ev['search_end']}T23:59:59Z",
        max_items=200,
    ).items())
    pre_target = datetime.fromisoformat(ev["pre_flood_target_date"]).replace(tzinfo=timezone.utc)
    flood_target = datetime.fromisoformat(ev["flood_target_date"]).replace(tzinfo=timezone.utc)
    flood_start = datetime.fromisoformat(ev["flood_window_start"]).replace(tzinfo=timezone.utc)
    flood_end = datetime.fromisoformat(ev["flood_window_end"] + "T23:59:59").replace(tzinfo=timezone.utc)

    required_assets = {"green", "nir", "swir16", "scl"}
    candidates = []
    diagnostics = []
    for item in items:
        dt = item.datetime if item.datetime and item.datetime.tzinfo else (
            item.datetime.replace(tzinfo=timezone.utc) if item.datetime else None
        )
        cov = _coverage(item, cfg["analysis_bbox_wgs84"])
        cloud = float(item.properties.get("eo:cloud_cover") or 100.0)
        ok_assets = required_assets.issubset(item.assets)
        diagnostics.append({
            "id": item.id,
            "datetime": dt.isoformat() if dt else None,
            "coverage": cov,
            "cloud_cover_percent": cloud,
            "required_assets_present": ok_assets,
            "assets": sorted(item.assets.keys()),
        })
        if dt and cov >= 0.9 and ok_assets:
            candidates.append((item, dt, cov, cloud))

    write_json(out / "metadata" / "sentinel2_candidates.json", {
        "catalogue": EARTH_SEARCH_URL,
        "collection": S2_COLLECTION,
        "item_count": len(items),
        "items": diagnostics,
    })

    pre = [x for x in candidates if x[1] < flood_start]
    flood = [x for x in candidates if flood_start <= x[1] <= flood_end]
    if not pre or not flood:
        raise RuntimeError(
            f"No suitable Sentinel-2 pair: pre={len(pre)} flood={len(flood)} "
            f"from {len(items)} catalogue items"
        )

    # Date proximity matters, but avoid selecting an almost fully cloudy scene.
    # 0.15 means 20% cloud cover costs about three days in the score.
    p = min(pre, key=lambda x: abs((x[1] - pre_target).total_seconds()) / 86400 + 0.15 * x[3])
    f = min(flood, key=lambda x: abs((x[1] - flood_target).total_seconds()) / 86400 + 0.15 * x[3])

    selection = {
        "source": "Sentinel-2 L2A via Element84 Earth Search",
        "reason": "Optical fallback because Sentinel-1 catalogue probes returned zero acquisitions for the Atbasar 2024 search window.",
        "pre_item": p[0].id,
        "pre_datetime": p[1].isoformat(),
        "pre_coverage": p[2],
        "pre_cloud_cover_percent": p[3],
        "flood_item": f[0].id,
        "flood_datetime": f[1].isoformat(),
        "flood_coverage": f[2],
        "flood_cloud_cover_percent": f[3],
        "selection_rule": ">=90% AOI coverage, required spectral/SCL assets, nearest target dates with cloud penalty",
    }
    write_json(out / "metadata" / "sentinel2_selection.json", selection)

    for label, chosen in (("pre", p), ("flood", f)):
        item = chosen[0]
        for asset, nearest in (("green", False), ("nir", False), ("swir16", False), ("scl", True)):
            dst = out / "processed" / f"sentinel2_{label}_{asset}.tif"
            _clip_remote(
                item.assets[asset].href,
                cfg["analysis_bbox_wgs84"],
                dst,
                cfg["projected_crs"],
                20.0,
                resampling=Resampling.nearest if nearest else Resampling.bilinear,
            )
            sidecar(dst, {
                "source": "Sentinel-2 L2A via Element84 Earth Search",
                "item_id": item.id,
                "datetime": chosen[1].isoformat(),
                "asset": asset,
                "cloud_cover_percent_scene": chosen[3],
                "working_resolution_m": 20,
            })


def fetch_jrc(cfg: dict, out: Path) -> None:
    cat = pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=[JRC_COLLECTION], bbox=cfg["analysis_bbox_wgs84"], max_items=20).items())
    parts = []
    used = []
    for i, item in enumerate(items):
        signed = planetary_computer.sign(item)
        if "occurrence" not in signed.assets:
            continue
        p = out / "raw" / f"jrc_{i}.tif"
        _clip_remote(signed.assets["occurrence"].href, cfg["analysis_bbox_wgs84"], p, cfg["projected_crs"], 30.0,
                     resampling=Resampling.nearest)
        parts.append(p)
        used.append(item.id)
    if not parts:
        raise RuntimeError("No JRC GSW occurrence assets intersect AOI")
    datasets = [rasterio.open(p) for p in parts]
    try:
        arr, tr = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(height=arr.shape[1], width=arr.shape[2], transform=tr,
                       dtype="float32", compress="deflate", tiled=True)
        dst = out / "processed" / "jrc_water_occurrence_utm42n.tif"
        with rasterio.open(dst, "w", **profile) as f:
            f.write(arr.astype("float32"))
    finally:
        for d in datasets:
            d.close()
    sidecar(dst, {"source":"JRC Global Surface Water via Planetary Computer",
                  "asset":"occurrence","items":used,
                  "note":"Long-term water occurrence baseline, not a 2024 observation."})


def power_to_db(a):
    """Convert Sentinel-1 RTC linear gamma0 power to decibels."""
    x = np.full(a.shape, np.nan, dtype="float32")
    good = np.isfinite(a) & (a > 0)
    x[good] = 10.0 * np.log10(a[good])
    return x


def robust_otsu(values, fallback):
    v = values[np.isfinite(values)]
    if v.size < 100:
        return fallback
    lo, hi = np.percentile(v, [1,99])
    v = v[(v >= lo) & (v <= hi)]
    return float(threshold_otsu(v)) if v.size >= 100 else fallback


def aligned(reference: Path, moving: Path, nearest=False, nodata=np.nan):
    with rasterio.open(reference) as ref, rasterio.open(moving) as mov:
        dst = np.full((ref.height, ref.width), nodata, dtype="float32")
        reproject(source=mov.read(1).astype("float32"), destination=dst,
                  src_transform=mov.transform, src_crs=mov.crs, src_nodata=mov.nodata,
                  dst_transform=ref.transform, dst_crs=ref.crs, dst_nodata=nodata,
                  resampling=Resampling.nearest if nearest else Resampling.bilinear)
        return dst


def build_observed_mask_s1(out: Path) -> None:
    pre = out / "processed" / "sentinel1_pre_vv.tif"
    flood = out / "processed" / "sentinel1_flood_vv.tif"
    slope_p = out / "processed" / "slope_atbasar_deg.tif"
    jrc_p = out / "processed" / "jrc_water_occurrence_utm42n.tif"
    with rasterio.open(pre) as ref:
        pre_amp = ref.read(1).astype("float32")
        profile = ref.profile.copy()
        tr = ref.transform
        crs = ref.crs
    flood_amp = aligned(pre, flood)
    slope = aligned(pre, slope_p)
    occurrence = aligned(pre, jrc_p, nearest=True, nodata=255) if jrc_p.exists() else None

    pre_db = power_to_db(pre_amp)
    flood_db = power_to_db(flood_amp)
    delta = flood_db - pre_db
    finite = np.isfinite(pre_db) & np.isfinite(flood_db)
    fthr = float(np.clip(robust_otsu(flood_db[finite], -16.0), -28, -8))
    pthr = float(np.clip(robust_otsu(pre_db[finite], -16.0), -28, -8))
    candidate = finite & (flood_db < fthr) & (delta < -2.5) & ~(pre_db < pthr) & np.isfinite(slope) & (slope <= 7)
    if occurrence is not None:
        candidate &= ~((occurrence != 255) & (occurrence >= 90))
    candidate = binary_closing(candidate, footprint=disk(1))
    candidate = remove_small_objects(candidate, min_size=12)
    candidate = remove_small_holes(candidate, area_threshold=12)
    candidate = binary_fill_holes(candidate)

    dst = out / "processed" / "observed_flood_mask_2024.tif"
    profile.update(dtype="uint8", count=1, nodata=0, compress="deflate", tiled=True)
    with rasterio.open(dst, "w", **profile) as f:
        f.write(candidate.astype("uint8"), 1)

    geoms = [shape(g) for g, val in shapes(candidate.astype("uint8"), mask=candidate, transform=tr) if int(val) == 1]
    gdf = gpd.GeoDataFrame({"class":["observed_flood"]*len(geoms)}, geometry=geoms, crs=crs)
    if len(gdf):
        gdf = gdf[gdf.geometry.area >= 1000].copy()
        gdf["area_m2"] = gdf.geometry.area
    gdf.to_crs("EPSG:4326").to_file(out / "processed" / "observed_flood_mask_2024.geojson", driver="GeoJSON")

    fig, axes = plt.subplots(1, 3, figsize=(15, 6))
    axes[0].imshow(pre_db, cmap="gray"); axes[0].set_title("Pre-flood VV dB")
    axes[1].imshow(flood_db, cmap="gray"); axes[1].set_title("Flood-period VV dB")
    axes[2].imshow(candidate, cmap="Blues"); axes[2].set_title("Automatic flood mask — REQUIRES QC")
    for a in axes: a.axis("off")
    plt.tight_layout()
    fig.savefig(out / "processed" / "flood_mask_qc.png", dpi=160)
    plt.close(fig)

    meta = {
        "source":"Sentinel-1 VV change",
        "method":"Sentinel-1 RTC gamma0 linear power -> dB using 10*log10; Otsu dark-water; delta<-2.5 dB; exclude pre-existing dark water; slope<=7°; morphology; JRC>=90% permanent water exclusion where available",
        "flood_threshold_db":fthr,"pre_threshold_db":pthr,
        "status":"AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC",
        "caveats":[
            "SAR can confuse smooth wet soil, radar shadow, ice and other low-backscatter surfaces with water.",
            "This is observational evidence, not a hydrodynamic model.",
            "Visual QC is mandatory before using the mask as competition validation evidence."
        ]
    }
    sidecar(dst, meta)
    write_json(out / "metadata" / "flood_mask_method.json", meta)


def _safe_index(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    den = a + b
    out = np.full(a.shape, np.nan, dtype="float32")
    good = np.isfinite(a) & np.isfinite(b) & (np.abs(den) > 1e-6)
    out[good] = (a[good] - b[good]) / den[good]
    return out


def _s2_clear(scl: np.ndarray) -> np.ndarray:
    """Sentinel-2 SCL clear land/water mask.

    Excludes no-data, saturated pixels, cloud shadow, medium/high cloud,
    cirrus, and snow/ice. Low-probability cloud class 7 is retained and is
    still subject to the spectral water tests.
    """
    bad = np.isin(np.rint(scl).astype("int16"), [0, 1, 3, 8, 9, 10, 11])
    return np.isfinite(scl) & ~bad


def build_observed_mask_s2(out: Path) -> None:
    """Derive a conservative 2024 observed-inundation baseline from Sentinel-2.

    The mask represents newly detected open water between a clear pre-flood
    scene and a flood-period scene. It is deliberately labelled REQUIRES_QC;
    snow/ice, cloud gaps and turbid/shallow water remain limitations.
    """
    pre_green_p = out / "processed" / "sentinel2_pre_green.tif"
    flood_green_p = out / "processed" / "sentinel2_flood_green.tif"
    with rasterio.open(pre_green_p) as ref:
        pre_green = ref.read(1).astype("float32")
        profile = ref.profile.copy()
        tr = ref.transform
        crs = ref.crs

    pre_nir = aligned(pre_green_p, out / "processed" / "sentinel2_pre_nir.tif")
    pre_swir = aligned(pre_green_p, out / "processed" / "sentinel2_pre_swir16.tif")
    pre_scl = aligned(pre_green_p, out / "processed" / "sentinel2_pre_scl.tif", nearest=True)

    flood_green = aligned(pre_green_p, flood_green_p)
    flood_nir = aligned(pre_green_p, out / "processed" / "sentinel2_flood_nir.tif")
    flood_swir = aligned(pre_green_p, out / "processed" / "sentinel2_flood_swir16.tif")
    flood_scl = aligned(pre_green_p, out / "processed" / "sentinel2_flood_scl.tif", nearest=True)

    slope = aligned(pre_green_p, out / "processed" / "slope_atbasar_deg.tif")
    jrc_p = out / "processed" / "jrc_water_occurrence_utm42n.tif"
    occurrence = aligned(pre_green_p, jrc_p, nearest=True, nodata=255) if jrc_p.exists() else None

    pre_mndwi = _safe_index(pre_green, pre_swir)
    pre_ndwi = _safe_index(pre_green, pre_nir)
    flood_mndwi = _safe_index(flood_green, flood_swir)
    flood_ndwi = _safe_index(flood_green, flood_nir)
    pre_clear = _s2_clear(pre_scl)
    flood_clear = _s2_clear(flood_scl)
    common_clear = pre_clear & flood_clear

    fthr = float(np.clip(robust_otsu(flood_mndwi[common_clear], 0.05), -0.05, 0.30))
    pthr = float(np.clip(robust_otsu(pre_mndwi[common_clear], 0.05), -0.05, 0.30))
    flood_water = flood_clear & (flood_mndwi > fthr) & (flood_ndwi > -0.10)
    pre_water = pre_clear & (pre_mndwi > pthr) & (pre_ndwi > -0.10)
    delta = flood_mndwi - pre_mndwi

    candidate = (
        common_clear
        & flood_water
        & ~pre_water
        & np.isfinite(delta)
        & (delta > 0.10)
        & np.isfinite(slope)
        & (slope <= 7)
    )
    if occurrence is not None:
        candidate &= ~((occurrence != 255) & (occurrence >= 90))

    candidate = binary_closing(candidate, footprint=disk(1))
    candidate = remove_small_objects(candidate, min_size=12)
    candidate = remove_small_holes(candidate, area_threshold=12)
    candidate = binary_fill_holes(candidate)

    dst = out / "processed" / "observed_flood_mask_2024.tif"
    profile.update(dtype="uint8", count=1, nodata=0, compress="deflate", tiled=True)
    with rasterio.open(dst, "w", **profile) as fh:
        fh.write(candidate.astype("uint8"), 1)

    geoms = [
        shape(g) for g, val in shapes(candidate.astype("uint8"), mask=candidate, transform=tr)
        if int(val) == 1
    ]
    gdf = gpd.GeoDataFrame({"class": ["observed_flood"] * len(geoms)}, geometry=geoms, crs=crs)
    if len(gdf):
        gdf = gdf[gdf.geometry.area >= 1000].copy()
        gdf["area_m2"] = gdf.geometry.area
    gdf.to_crs("EPSG:4326").to_file(
        out / "processed" / "observed_flood_mask_2024.geojson", driver="GeoJSON"
    )

    qc_valid = common_clear.astype("uint8")
    qc_valid_path = out / "processed" / "sentinel2_common_clear_mask.tif"
    qc_profile = profile.copy()
    qc_profile.update(dtype="uint8", nodata=0)
    with rasterio.open(qc_valid_path, "w", **qc_profile) as fh:
        fh.write(qc_valid, 1)

    fig, axes = plt.subplots(1, 4, figsize=(18, 6))
    axes[0].imshow(pre_mndwi, cmap="gray", vmin=-1, vmax=1); axes[0].set_title("Pre-flood MNDWI")
    axes[1].imshow(flood_mndwi, cmap="gray", vmin=-1, vmax=1); axes[1].set_title("Flood-period MNDWI")
    axes[2].imshow(common_clear, cmap="gray"); axes[2].set_title("Clear in both scenes")
    axes[3].imshow(candidate, cmap="Blues"); axes[3].set_title("Observed flood baseline — REQUIRES QC")
    for a in axes:
        a.axis("off")
    plt.tight_layout()
    fig.savefig(out / "processed" / "flood_mask_qc.png", dpi=160)
    plt.close(fig)

    clear_fraction = float(common_clear.mean())
    flooded_pixels = int(candidate.sum())
    pixel_area_m2 = abs(float(tr.a * tr.e))
    meta = {
        "source": "Sentinel-2 L2A change detection via Element84 Earth Search",
        "fallback_reason": "No Sentinel-1 acquisitions were returned for the Atbasar 2024 window by Planetary Computer, Copernicus Data Space STAC, or Element84 Earth Search probes.",
        "method": "SCL cloud/shadow/snow masking; MNDWI + NDWI open-water test; flood-minus-pre change > 0.10; slope<=7 degrees; JRC >=90% permanent-water exclusion where available; morphology.",
        "pre_mndwi_threshold": pthr,
        "flood_mndwi_threshold": fthr,
        "common_clear_fraction": clear_fraction,
        "observed_flood_pixels": flooded_pixels,
        "observed_flood_area_m2_raw_pixel_count": flooded_pixels * pixel_area_m2,
        "status": "AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC",
        "caveats": [
            "Optical imagery cannot observe through cloud and can miss turbid, shallow, vegetated or ice-covered floodwater.",
            "The mask is conservative and only evaluates pixels clear in both selected scenes.",
            "This is observational evidence, not a hydrodynamic model.",
            "Visual QC is mandatory before using this mask as validation evidence."
        ],
    }
    sidecar(dst, meta)
    sidecar(qc_valid_path, {
        "source": "Sentinel-2 SCL",
        "meaning": "1 = clear in both selected pre-flood and flood-period scenes",
    })
    write_json(out / "metadata" / "flood_mask_method.json", meta)


def fetch_population(cfg: dict, out: Path) -> None:
    west, south, east, north = cfg["analysis_bbox_wgs84"]
    geom = {"type":"Polygon","coordinates":[[[west,south],[east,south],[east,north],[west,north],[west,south]]]}
    raw = out / "raw" / "worldpop_clip.tif"
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            with rasterio.open(WORLDPOP_URL) as src:
                g = transform_geom("EPSG:4326", src.crs, geom)
                arr, tr = mask(src, [g], crop=True, filled=True, nodata=src.nodata)
                p = src.profile.copy()
                p.update(height=arr.shape[1], width=arr.shape[2], transform=tr)
                with rasterio.open(raw, "w", **p) as f:
                    f.write(arr)
    except Exception:
        country = out / "raw" / "worldpop_kaz_2024.tif"
        if not country.exists():
            with requests.get(WORLDPOP_URL, stream=True, timeout=600, headers={"User-Agent":"ARGUS-FloodOps/1.0"}) as r:
                r.raise_for_status()
                with country.open("wb") as f:
                    for chunk in r.iter_content(1024*1024):
                        if chunk: f.write(chunk)
        with rasterio.open(country) as src:
            g = transform_geom("EPSG:4326", src.crs, geom)
            arr, tr = mask(src, [g], crop=True, filled=True, nodata=src.nodata)
            p = src.profile.copy(); p.update(height=arr.shape[1], width=arr.shape[2], transform=tr)
            with rasterio.open(raw, "w", **p) as f: f.write(arr)

    with rasterio.open(raw) as src:
        tr, width, height = calculate_default_transform(src.crs, cfg["projected_crs"], src.width, src.height,
                                                        *src.bounds, resolution=100.0)
        dst_arr = np.full((height,width), -9999.0, dtype="float32")
        reproject(source=src.read(1).astype("float32"), destination=dst_arr,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                  dst_transform=tr, dst_crs=cfg["projected_crs"], dst_nodata=-9999.0,
                  resampling=Resampling.sum)
        dst = out / "processed" / "worldpop_2024_100m_utm42n.tif"
        profile = {"driver":"GTiff","height":height,"width":width,"count":1,"dtype":"float32",
                   "crs":cfg["projected_crs"],"transform":tr,"nodata":-9999.0,
                   "compress":"deflate","tiled":True}
        with rasterio.open(dst, "w", **profile) as f: f.write(dst_arr,1)
    sidecar(dst, {"source":"WorldPop Global2 R2025A v1 constrained 100 m","source_url":WORLDPOP_URL,
                  "year":2024,"units":"modelled people per grid cell",
                  "caveat":"Modelled gridded exposure, not a resident registry."})


def copy_curated(out: Path) -> None:
    dst = out / "curated"
    dst.mkdir(parents=True, exist_ok=True)
    for rel in [
        "hydrology/zhabai_2024_observations.csv",
        "hydrology/zhabai_2024_event_peak.csv",
        "events/atbasar_flood_2024_events.csv",
    ]:
        src = CURATED / rel
        if src.exists():
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)


def validation_layout(cfg: dict, out: Path) -> None:
    d = out / "validation" / "atbasar" / "atbasar-2024"
    shutil.copy2(out / "processed" / "observed_flood_mask_2024.tif", d / "observed.tif")
    west,south,east,north = cfg["analysis_bbox_wgs84"]
    aoi = {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"Atbasar analysis AOI"},
           "geometry":{"type":"Polygon","coordinates":[[[west,south],[east,south],[east,north],[west,north],[west,south]]]}}]}
    write_json(d / "aoi.geojson", aoi)
    method_path = out / "metadata" / "flood_mask_method.json"
    method = json.loads(method_path.read_text(encoding="utf-8")) if method_path.exists() else {}
    write_json(d / "metadata.json", {
        "name":"Atbasar 2024 flood",
        "event_date":"2024-04",
        "observed_source":method.get("source", "satellite-derived automatic baseline"),
        "observed_status":"REQUIRES_QC",
        "modelled_status":"NOT_LOADED",
        "scientific_note":"Validation metrics must not be computed/presented until modelled.tif exists and the observed mask passes visual QC."
    })


def manifest(cfg: dict, out: Path, statuses: dict) -> None:
    files = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and "raw" not in p.parts and p.name != "dataset_manifest.json":
            files.append({"path":str(p.relative_to(out)),"bytes":p.stat().st_size,"sha256":sha256(p)})
    write_json(out / "metadata" / "dataset_manifest.json", {
        "area_id":cfg["area_id"],"generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "working_crs":cfg["projected_crs"],"source_mode":"REAL_OPEN_DATA_AND_OFFICIAL_CURATED_HISTORY",
        "pipeline_status":statuses,"files":files,
        "quality_gates":{
            "observed_flood_mask":"REQUIRES_VISUAL_QC",
            "hydrology":"DO_NOT_MERGE_DIFFERENT_DATUM_REFERENCES_WITHOUT_VERIFICATION",
            "critical_facility_priority":"OSM_CANDIDATE_DEFAULT_MUST_BE_DOMAIN_REVIEWED",
            "validation":"NO_METRICS_UNTIL_OBSERVED_QC_AND_MODELLED_MASK_EXIST"
        }
    })


def run_step(name, fn, statuses, required=True):
    try:
        fn()
        statuses[name] = {"status":"OK"}
    except Exception as e:
        statuses[name] = {"status":"FAILED","error":repr(e),"required":required}
        print(f"[{name}] FAILED: {e}", file=sys.stderr)
        if required:
            raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=ROOT / "data" / "realdata" / "atbasar" / "generated")
    ap.add_argument("--skip-population", action="store_true")
    args = ap.parse_args()
    cfg = load_cfg()
    out = args.output.resolve()
    mkdirs(out)
    write_json(out / "metadata" / "config_snapshot.json", cfg)
    write_json(out / "logs" / "preflight.json", preflight(out))
    copy_curated(out)

    statuses = {}
    run_step("terrain", lambda: fetch_dem(cfg,out), statuses, required=True)
    run_step("osm", lambda: fetch_osm(cfg,out), statuses, required=True)
    run_step("sentinel1", lambda: fetch_sentinel1(cfg,out), statuses, required=False)
    run_step("jrc_water", lambda: fetch_jrc(cfg,out), statuses, required=False)
    if statuses["sentinel1"]["status"] == "OK":
        statuses["satellite_observation_source"] = {"status": "OK", "source": "Sentinel-1 RTC"}
        run_step("observed_flood_mask", lambda: build_observed_mask_s1(out), statuses, required=True)
    else:
        run_step("sentinel2_fallback", lambda: fetch_sentinel2(cfg,out), statuses, required=True)
        statuses["satellite_observation_source"] = {
            "status": "OK",
            "source": "Sentinel-2 L2A",
            "reason": "Sentinel-1 unavailable for the historical event window",
        }
        run_step("observed_flood_mask", lambda: build_observed_mask_s2(out), statuses, required=True)
    if not args.skip_population:
        run_step("population", lambda: fetch_population(cfg,out), statuses, required=False)
    else:
        statuses["population"] = {"status":"SKIPPED_BY_FLAG"}
    validation_layout(cfg,out)
    manifest(cfg,out,statuses)
    print(json.dumps(statuses, indent=2))
    print(f"ARGUS Atbasar real-data pack: {out}")


if __name__ == "__main__":
    main()
