"""Build ARGUS area fixture bundles from the installed real-data packs.

Output (deterministic, rebuilt only when the pack checksum, the exercise inputs or the builder version
change): ``<data_dir>/runtime/realdata/<area>/`` with the same files the seed already consumes
(``area.json``, ``roads.geojson`` …) plus ``history.json`` (official chronology, curated hydrology,
historical GloFAS/weather context) and ``waterways.geojson``.

Provenance rules applied here:
* real layers (OSM, Copernicus DEM, WorldPop, JRC, official records, Sentinel-2 evidence) keep their
  source and caveats;
* planning sites, resources, plans and exercise injects have no real source → labelled SIMULATION;
* assumptions (speed caps, facility criticality policy, road surface level, bridge clearance) are
  recorded in ``area.json → assumptions`` and shown in the UI.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy import ndimage
from shapely.geometry import LineString, Point, shape

from app.core.config import REPO_ROOT, get_settings
from app.core.logging import get_logger
from app.demo.terrain import priority_flood_onset
from app.realdata import common as C
from app.realdata.install import pack_dir, status

log = get_logger("argus.realdata.build")
BUILDER_VERSION = 13
CURATED = REPO_ROOT / "data" / "realdata"
SIM = "SIMULATION"


def runtime_dir(area: str) -> Path:
    return get_settings().data_dir / "runtime" / "realdata" / area


def _fingerprint(area: str) -> str:
    st = status(area)
    h = hashlib.sha256(f"{BUILDER_VERSION}|{st.archive_sha256}".encode())
    ex = CURATED / area / "exercise"
    for p in sorted(ex.glob("*.json")) if ex.exists() else []:
        h.update(p.read_bytes())
    evidence = CURATED / area / "historical_evidence.json"
    if evidence.exists():
        h.update(evidence.read_bytes())
    return h.hexdigest()[:16]


def _read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _t(kk: str, ru: str, en: str) -> dict:
    return {"kk": kk, "ru": ru, "en": en, "original": ru}


def _names_props(n: dict) -> dict:
    return {"name_kk": n["kk"], "name_ru": n["ru"], "name_en": n["en"], "name_original": n.get("original") or n["ru"]}


def _seg_samples(roads: dict, proj: C.Projector, step: float = 25.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X, Y, S = [], [], []
    for f in roads["features"]:
        xy = [proj.xy(*c) for c in f["geometry"]["coordinates"]]
        ls = LineString(xy)
        n = max(2, int(ls.length / step) + 1)
        for d in np.linspace(0, ls.length, n):
            p = ls.interpolate(d)
            X.append(p.x)
            Y.append(p.y)
            S.append(f["properties"]["id"])
    return np.array(X), np.array(Y), np.array(S)


def _closure_times(level: np.ndarray, segs: np.ndarray, times: np.ndarray, thr: float = 0.30) -> dict[str, float]:
    out = {}
    lv = np.where(np.isfinite(level), level, -9.0)
    for sid in np.unique(segs):
        mx = lv[segs == sid].max(axis=0)
        idx = np.where(mx >= thr)[0]
        if idx.size:
            out[str(sid)] = float(times[idx[0]])
    return out


def _isolated_nodes(roads: dict, closed: set[str], start: str) -> set[str]:
    adj: dict[str, list[str]] = {}
    for f in roads["features"]:
        p = f["properties"]
        if p["id"] in closed:
            continue
        adj.setdefault(p["u"], []).append(p["v"])
        adj.setdefault(p["v"], []).append(p["u"])
    seen, stack = {start}, [start]
    while stack:
        n = stack.pop()
        for m in adj.get(n, []):
            if m not in seen:
                seen.add(m)
                stack.append(m)
    alln = {n["properties"]["id"] for n in roads["nodes"]}
    return alln - seen


def _node_ll(roads: dict) -> dict[str, list[float]]:
    return {n["properties"]["id"]: n["geometry"]["coordinates"] for n in roads["nodes"]}


def _cluster(points: np.ndarray, eps: float) -> list[np.ndarray]:
    """Single-linkage clusters (grid-hash, deterministic) → list of index arrays, largest first."""
    if len(points) == 0:
        return []
    from scipy.cluster.hierarchy import fcluster, linkage

    if len(points) == 1:
        return [np.array([0])]
    lab = fcluster(linkage(points, method="single"), t=eps, criterion="distance")
    groups = [np.flatnonzero(lab == k) for k in np.unique(lab)]
    return sorted(groups, key=lambda g: (-len(g), float(points[g, 0].mean())))


# ===================================================================================== ATBASAR
ATB_REF = datetime.fromisoformat("2024-04-11T04:43:00+05:00")  # official overflow record (event time)


def build_atbasar(out: Path) -> dict:
    from app.providers.flood.raster_manifest import RasterManifestProvider

    area_id = "atbasar"
    pack = pack_dir(area_id)
    cfg = C.load_json(CURATED / area_id / "config.json")
    epsg = 32642
    roads = C.build_roads(pack, epsg)
    proj: C.Projector = roads["_proj"]
    bld_raw = gpd.read_file(pack / "processed" / "argus_buildings.geojson")
    sectors = C.grid_sectors(bld_raw, epsg, 1200.0, 25, {
        "kk": "{code} талдау ұяшығы", "ru": "Аналитическая ячейка {code}", "en": "Analysis cell {code}"})
    bfeats, bgdf = C.build_buildings(pack, epsg, sectors)
    pz, pop_meta = C.population_zones(pack, bgdf, epsg)
    facilities = C.build_facilities(pack, sectors)
    bridges = C.build_bridges(pack, roads, deck_clearance_m=3.0)
    water_fc, river_lines = C.waterways_layer(pack, "жабай|zhabai")

    manifest = pack / "scenarios" / area_id / "manifest.json"
    P = RasterManifestProvider(manifest)
    times = np.arange(-360, 361, 30, dtype=float)
    X, Y, S = _seg_samples(roads, proj)
    closures = {m: _closure_times(P.relative_level_points(m, X, Y, times), S, times) for m in ("LOW", "BASE", "HIGH")}

    # ---------------------------------------------------------------- bases (fire station = real OSM location)
    fire = [f for f in facilities if f["properties"]["facility_type"] == "FIRE_STATION"]
    base_ll = fire[0]["geometry"]["coordinates"] if fire else cfg["center_wgs84"]
    # staging depot: trunk/primary node farthest from any closure, west of the river (high ground per DEM)
    nodes_ll = _node_ll(roads)
    major_nodes = sorted({f["properties"][k] for f in roads["features"] if f["properties"]["road_class"] in ("trunk", "primary")
                          for k in ("u", "v")})
    cx, cy = proj.xy(*cfg["center_wgs84"])
    depot = min(major_nodes, key=lambda n: (abs(proj.xy(*nodes_ll[n])[0] - (cx - 2500)) + abs(proj.xy(*nodes_ll[n])[1] - cy)))
    bases = [
        {"id": "BASE-FIRE", "lonlat": base_ll, "safe": True,
         "names": _t("Өрт сөндіру бөлімі (OSM орны)", "Пожарная часть (местоположение OSM)", "Fire station (OSM location)")},
        {"id": "DEPOT-W", "lonlat": nodes_ll[depot], "safe": True,
         "names": _t("Батыс жинақтау алаңы (жаттығу)", "Западная площадка сбора (учения)", "West staging depot (exercise)")},
    ]

    # ---------------------------------------------------------------- planning sites (SIMULATION objects on real geography)
    seg_props = {f["properties"]["id"]: f for f in roads["features"]}
    river = C.merged_river(pack, "жабай|zhabai", epsg)
    sites: list[dict] = []

    def add_site(sid: str, kind: str, lonlat: list[float], names: dict, sector: str | None, work_limit: float,
                 protects: dict, note: str) -> None:
        sites.append(C.point_feature(sid, [round(lonlat[0], 7), round(lonlat[1], 7)], {
            "kind": kind, "sector_id": sector, "protects": protects, "work_depth_limit_m": work_limit,
            **_names_props(names), "source": f"{SIM} planning site — {note}",
        }))

    b_x = np.array([proj.xy(*shape(f["geometry"]).centroid.coords[0])[0] for f in bfeats])
    b_y = np.array([proj.xy(*shape(f["geometry"]).centroid.coords[0])[1] for f in bfeats])
    lv_high = P.relative_level_points("HIGH", b_x, b_y, np.array([0.0, 180.0]))
    flooded = np.flatnonzero(np.nanmax(np.where(np.isfinite(lv_high), lv_high, -9), axis=1) >= 0.10)
    near = np.flatnonzero(np.nanmax(np.where(np.isfinite(lv_high), lv_high, -9), axis=1) >= -1.0)
    groups = _cluster(np.c_[b_x[near], b_y[near]], 250.0) if len(near) else []
    bsec = [f["properties"]["sector_id"] for f in bfeats]
    for k, g in enumerate(groups[:3]):
        idx = near[g]
        x, y = float(b_x[idx].mean()), float(b_y[idx].mean())
        sec = max(set(bsec[i] for i in idx), key=[bsec[i] for i in idx].count)
        add_site(f"S-PUMP-{k + 1}", "DRAINAGE_POINT", proj.ll(x, y),
                 _t(f"Сорғы нүктесі {k + 1} (жағалау маңы)", f"Точка откачки {k + 1} (прибрежная застройка)",
                    f"Pumping point {k + 1} (riverside houses)"), sec, 0.40, {"sector_ids": [sec]},
                 f"centroid of {len(idx)} riverside buildings within 1 m of the HIGH-member water level")
        # levee section: nearest point on the Zhabai, 40 m landward
        p_r = river.interpolate(river.project(Point(x, y)))
        vx, vy = x - p_r.x, y - p_r.y
        d = max(1.0, float(np.hypot(vx, vy)))
        lx, ly = p_r.x + vx / d * 40.0, p_r.y + vy / d * 40.0
        add_site(f"S-LEVEE-{k + 1}", "LEVEE", proj.ll(lx, ly),
                 _t(f"Жабай жағалау бөгетінің учаскесі {k + 1}", f"Участок береговой дамбы Жабая {k + 1}",
                    f"Zhabai embankment section {k + 1}"), sec, -0.30, {"sector_ids": [sec]},
                 "nearest Zhabai bank point to the riverside building cluster (2024: overflow at six embankment sections)")

    # road-control points on major roads that close in BASE/HIGH (earliest first)
    major = sorted(((t, sid) for sid, t in {**closures["HIGH"], **closures["BASE"]}.items()
                    if seg_props[sid]["properties"]["road_class"] in ("trunk", "primary", "secondary", "tertiary")),
                   key=lambda x: (x[0], x[1]))
    used_roads = set()
    for _t0, sid in major:
        rp = seg_props[sid]["properties"]
        if rp["road_id"] in used_roads or len(used_roads) >= 2:
            continue
        used_roads.add(rp["road_id"])
        line = LineString(seg_props[sid]["geometry"]["coordinates"])
        mid = line.interpolate(0.5, normalized=True)
        k = len(used_roads)
        add_site(f"S-ROAD-{k}", "ROAD_CLOSURE", [mid.x, mid.y],
                 _t(f"{rp['name_kk']} — жол бақылау бекеті", f"{rp['name_ru']} — пост перекрытия", f"{rp['name_en']} — road-control point"),
                 None, 0.30, {"road_ids": [rp["road_id"]]}, f"major road segment {sid} closing in the scenario")

    # staging + supply where the network becomes isolated in HIGH (union-find on open segments at peak)
    start = C.nearest_node_id(roads["nodes"], proj, *proj.xy(*base_ll))[0]
    iso_high = _isolated_nodes(roads, {s for s, t in closures["HIGH"].items() if t <= 180}, start)
    if iso_high:
        pts = np.array([proj.xy(*nodes_ll[n]) for n in sorted(iso_high)])
        g = _cluster(pts, 600.0)[0]
        x, y = float(pts[g, 0].mean()), float(pts[g, 1].mean())
        nn = min(sorted(iso_high), key=lambda n: (proj.xy(*nodes_ll[n])[0] - x) ** 2 + (proj.xy(*nodes_ll[n])[1] - y) ** 2)
        add_site("S-STAGE-1", "STAGING", nodes_ll[nn],
                 _t("Оқшауланатын аймақтағы құтқару бекеті", "Спасательный пост в изолируемой зоне", "Rescue staging in the area that becomes isolated"),
                 None, 0.50, {"sector_ids": []}, f"{len(iso_high)} road nodes lose connection to the fire station in the HIGH member")

    # facility sites: hospital + facilities nearest to modelled water (supply / protection targets)
    fx = np.array([proj.xy(*f["geometry"]["coordinates"])[0] for f in facilities])
    fy = np.array([proj.xy(*f["geometry"]["coordinates"])[1] for f in facilities])
    flv = P.relative_level_points("HIGH", fx, fy, np.array([0.0]))[:, 0]
    rank = np.argsort(np.where(np.isfinite(flv), -flv, 99.0) + np.hypot(fx - cx, fy - cy) / 1e6)
    pick = [i for i in rank[:3]]
    hosp = [i for i, f in enumerate(facilities) if f["properties"]["facility_type"] == "HOSPITAL"]
    if hosp and hosp[0] not in pick:
        pick.append(hosp[0])
    for i in pick:
        f = facilities[i]["properties"]
        add_site(f"S-{f['id']}", "FACILITY", facilities[i]["geometry"]["coordinates"],
                 {"kk": f["name_kk"], "ru": f["name_ru"], "en": f["name_en"], "original": f["name_original"] or f["name_ru"]},
                 f["sector_id"], 0.25, {"facility_ids": [f["id"]]}, "real OSM facility candidate")

    # ---------------------------------------------------------------- bottlenecks: bridges + low roads
    bottlenecks = []
    for b in bridges:
        bottlenecks.append({"type": "Feature", "geometry": b["geometry"], "properties": {
            "id": f"BN-{b['properties']['id']}", "kind": "BRIDGE", "segment_ids": b["properties"]["segment_ids"],
            "bridge_id": b["properties"]["id"], "notes": "Candidate operational bottleneck (OSM bridge); no surveyed hydraulic capacity.",
            **{k: b["properties"][k] for k in ("name_kk", "name_ru", "name_en", "name_original")}}})
    for sid, _t0 in sorted(closures["BASE"].items(), key=lambda x: x[1])[:3]:
        rp = seg_props[sid]["properties"]
        mid = LineString(seg_props[sid]["geometry"]["coordinates"]).interpolate(0.5, normalized=True)
        bottlenecks.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [mid.x, mid.y]}, "properties": {
            "id": f"BN-LOW-{sid}", "kind": "LOW_ROAD", "segment_ids": [sid], "bridge_id": None,
            "notes": "Candidate low road section: inundated in the BASE member (terrain-conditioned model).",
            "name_kk": f"Ойпаң жол учаскесі — {rp['name_kk']}", "name_ru": f"Низкий участок дороги — {rp['name_ru']}",
            "name_en": f"Low road section — {rp['name_en']}", "name_original": rp["name_original"]}})

    # ---------------------------------------------------------------- stations (scenario proxy + official local gauges)
    pr = river.interpolate(river.project(Point(cx, cy)))
    stations = [{"id": "ZHB-PROXY", "lonlat": proj.ll(pr.x, pr.y), "river": "Zhabai", "bankfull": 445, "watch": None,
                 "warning": None, "critical": 595, "provider": "scenario_stage_proxy",
                 "names": _t("Жабай — сценарийлік деңгей проксиі", "Жабай — прокси уровня сценария", "Zhabai — scenario stage proxy")}]
    obs_rows = _read_csv(pack / "curated" / "hydrology" / "zhabai_2024_observations.csv")
    station_for = {
        "Atbasar_Zhabai_local_monitoring": ("ZHB-LOCAL", _t("Жабай — Атбасар жергілікті мониторингі (ресми)",
                                                             "Жабай — местный мониторинг Атбасара (офиц.)",
                                                             "Zhabai — Atbasar local monitoring (official)")),
        "railway_bridge": ("ZHB-RAIL", _t("Жабай — темір жол көпірі бекеті (ресми)", "Жабай — пост у ж/д моста (офиц.)",
                                          "Zhabai — railway bridge gauge (official)")),
        "Almaty_Yekaterinburg_road_bridge": ("ZHB-ROAD", _t("Жабай — Алматы–Екатеринбург жол көпірі (ресми)",
                                                            "Жабай — мост трассы Алматы–Екатеринбург (офиц.)",
                                                            "Zhabai — Almaty–Yekaterinburg road bridge (official)")),
    }
    for _ref, (sid, nm) in station_for.items():
        stations.append({"id": sid, "lonlat": proj.ll(pr.x + 60, pr.y + 60), "river": "Zhabai", "bankfull": None, "watch": None,
                         "warning": None, "critical": None, "provider": "official_report", "names": nm})
    observations = []
    for r in obs_rows:
        ts = r["timestamp_local"]
        dt = datetime.fromisoformat(ts) if "T" in ts else datetime.fromisoformat(ts + "T00:00:00+05:00")
        observations.append({
            "station_id": station_for[r["location_reference"]][0], "observed_at": dt.isoformat(),
            "water_level_cm": round(float(r["value"]) * 100), "source_type": "HYDROPOST", "verification": "UNVERIFIED",
            "source": f"Official report (gov.kz) — {r['source_url']}", "mode": "HISTORICAL",
            "quality": f"{r['quality']} · {r['timestamp_precision']}"[:120],
            "notes": f"{r['reference_type']}; timestamp precision: {r['timestamp_precision']}. {r.get('notes') or ''}".strip(),
            "use_for_conditioning": False,
        })

    # ---------------------------------------------------------------- scenario (HISTORICAL raster manifest)
    m = C.load_json(manifest)
    frame_offsets = list(range(-360, 361, 60))
    members = []
    for mem in m["members"]:
        g = mem["gauge"]
        peak = max(g, key=lambda p: p[1])
        members.append({"id": mem["id"], "label": mem["label"], "peak_stage_cm": peak[1], "peak_offset_h": peak[0] / 60})
    calib = C.load_json(pack / "scenarios" / area_id / "calibration_metrics.json")
    scenario = {
        "mode": "HISTORICAL", "family_id": "atbasar-hist-2024", "issued_at": (ATB_REF - timedelta(hours=6)).isoformat(),
        "reference_time": ATB_REF.isoformat(), "frame_offsets_min": frame_offsets, "series_step_min": 10,
        "bankfull_cm": m.get("bankfull_cm", 445), "station_id": "ZHB-PROXY", "issued_member": "BASE", "members": members,
        "provider": "raster_manifest",
        "provider_config": {"manifest_path": f"<realdata>/{area_id}/generated/scenarios/{area_id}/manifest.json"},
        "model_version": "hybrid-terrain-susceptibility+stage-proxy (pack run 36886595533)",
        "name": "Atbasar 2024 — historical reconstruction (LOW / BASE / HIGH)",
        "source": "ARGUS real-data pack: Copernicus DEM + OSM Zhabai + Sentinel-2 calibrated susceptibility",
        "note": ("Hybrid terrain-conditioned susceptibility and stage proxy calibrated against the Sentinel-2 flood evidence "
                 "of 14 Apr 2024. Not a hydrodynamic model. Time profile is a stage-proxy presentation; the peak (offset 0) "
                 "is anchored to the official overflow record of 11 Apr 2024 04:43 (Zhabai 5.95 m local level). Native "
                 "frames every 180 min; intermediate frames are linear interpolations."),
        "limitations": calib.get("scientific_limitations", []) + [
            "Town-interior flooding from embankment overtopping (officially recorded on 11 Apr 2024) is not reproduced: "
            "the 30 m DSM does not resolve levees/culverts and the 14 Apr optical mask shows no detectable open water in the built-up area."],
    }
    plans = C.load_json(CURATED / area_id / "exercise" / "plans.json") if (CURATED / area_id / "exercise" / "plans.json").exists() else {"plans": [], "extra_candidates": []}
    history = _history(pack, area_id, cfg)
    area = {
        "id": area_id, "data_profile": "historical",
        "names": _t("Атбасар — Жабай", "Атбасар — Жабай", "Atbasar — Zhabai"),
        "river_names": _t("Жабай өзені", "река Жабай", "Zhabai River"), "archetype": "RIVERINE_FLOODPLAIN", "sort_order": 1,
        "crs_epsg": epsg, "center": cfg["center_wgs84"], "utc_offset_min": 300, "reference_time": ATB_REF.isoformat(),
        "clock_start": (ATB_REF - timedelta(minutes=300)).isoformat(), "clock_mode": "HISTORICAL",
        "grid": {"dem": "processed/dem_atbasar_utm42n.tif"}, "bbox": cfg["analysis_bbox_wgs84"],
        "stations": stations, "bases": bases, "river_lines": river_lines,
        "dem_path": f"<realdata>/{area_id}/generated/processed/dem_atbasar_utm42n.tif",
        "economic_model": "exposure_only", "population_method": "worldpop_dasymetric",
        "pack": {"archive_sha256": status(area_id).archive_sha256, "run_id": 36886595533, "artifact_id": 11174673127},
        "assumptions": _assumptions(bridge_clearance=3.0),
        "population_meta": pop_meta, "road_meta": roads["_meta"],
        "validation": {
            "dataset_id": "atbasar-2024", "path": f"<realdata>/{area_id}/generated/validation/{area_id}/atbasar-2024",
            "pack_root": f"<realdata>/{area_id}/generated",
            "label": "HISTORICAL_SAME_EVENT_SPATIAL_HOLDOUT",
            "protocol": {"grid": "processed/dem_atbasar_utm42n.tif", "slope": "processed/slope_atbasar_deg.tif",
                         "relative": "scenarios/atbasar/relative_elevation_to_zhabai.tif",
                         "distance": "scenarios/atbasar/distance_to_zhabai_m.tif",
                         "clear": "processed/sentinel2_common_clear_mask.tif", "jrc": "processed/jrc_water_occurrence_utm42n.tif",
                         "slope_max_deg": 7.0, "distance_max_m": 8000.0, "jrc_permanent_min": 90.0, "block_m": 1200.0,
                         "documented_in": "scenarios/atbasar/calibration_metrics.json"},
            "observed_qc": {"status": "AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC",
                            "technical_visual_review": _final_status("atbasar", "satellite", "technical_visual_review"),
                            "certification": "NOT_CERTIFIED (no hydrologist / agency certification)"},
            "satellite": history.get("satellite"), "mask_method": history.get("mask_method"),
            "model": {"kind": calib.get("model_kind"), "not_a_hydrodynamic_model": calib.get("not_a_hydrodynamic_model"),
                      "uses_raw_xy_coordinates": (calib.get("susceptibility_model") or {}).get("uses_raw_xy_coordinates"),
                      "algorithm": (calib.get("susceptibility_model") or {}).get("algorithm")},
            "limitations": calib.get("scientific_limitations", []),
            "qc_png": "processed/flood_mask_qc.png",
        },
        "role": "PRIMARY_HISTORICAL_VALIDATION_PILOT",
    }
    return _write_bundle(out, area, roads, bridges, bottlenecks, bfeats, sectors, pz, facilities, sites, _resources(bases),
                         scenario, plans, observations, history, water_fc,
                         {"closures": {k: dict(sorted(v.items(), key=lambda x: x[1])) for k, v in closures.items()},
                          "flooded_buildings_high": int(len(flooded)), "isolated_nodes_high": sorted(iso_high)})


# ===================================================================================== KOKSHETAU
KOK_TERRAIN_VERSION = 2
# Conservative exercise envelope.  The official 2024 reports describe localised impacts near the
# Kylshakty (16 private houses, 29 private yards, 12 apartment courtyards and Ertostik kindergarten),
# not city-wide inundation.  These parameters bound the uncalibrated stage-HAND exercise to the
# near-river corridor; they are NOT a surveyed hydraulic calibration.
KOK_CHANNEL_CORRIDOR_M = 100.0
KOK_STAGE_PEAKS_M = {"LOW": 0.10, "BASE": 0.20, "HIGH": 0.40}
KOK_REPORTED_IMPACT_SCALE = {
    "private_houses": 16,
    "private_yards": 29,
    "apartment_courtyards": 12,
    "kindergarten_floors": 1,
    "aggregate_reported_impact_units": 58,
    "note": "Aggregate categories are not equivalent to modelled building footprints; used only as an order-of-magnitude exercise bound.",
}

KOK_REF = datetime.fromisoformat("2024-03-29T06:00:00+05:00")


def _kokshetau_terrain(pack: Path, out: Path, river) -> dict:  # type: ignore[no-untyped-def]
    """Conservative HAND/onset surface relative to the real Kylshakty / Copernicus DEM.

    This remains a SIMULATION exercise, not a hydraulic model.  Unlike the earlier 2.5 km floodplain
    envelope, connectivity is deliberately bounded to a near-river corridor because official 2024
    reports describe localised impacts rather than city-wide inundation.  The corridor is an
    engineering exercise assumption, not an official flood boundary.
    """
    tdir = out / "terrain"
    meta_path = tdir / "terrain_model.json"
    expected = {
        "version": KOK_TERRAIN_VERSION,
        "max_channel_distance_m": KOK_CHANNEL_CORRIDOR_M,
        "method": "priority-flood onset over HAND relative to mapped Kylshakty",
    }
    if (tdir / "hand.tif").exists() and (tdir / "onset.tif").exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if all(meta.get(k) == v for k, v in expected.items()):
                with rasterio.open(tdir / "hand.tif") as s:
                    return {**expected, "crs": s.crs.to_string()}
        except (ValueError, OSError):
            pass

    with rasterio.open(pack / "processed" / "dem_kokshetau_utm42n.tif") as src:
        dem = src.read(1, masked=True).filled(np.nan).astype("float32")
        prof = src.profile.copy()
        tr = src.transform
    valid = np.isfinite(dem) & (dem > 1.0)
    fill = float(np.nanmedian(dem[valid]))
    sm = ndimage.median_filter(np.where(valid, dem, fill), size=3)
    ch = rasterize([(g, 1) for g in (river.geoms if hasattr(river, "geoms") else [river])], out_shape=dem.shape,
                   transform=tr, fill=0, all_touched=True, dtype="uint8").astype(bool)
    ch = ndimage.binary_dilation(ch, iterations=1) & valid
    _, (ri, ci) = ndimage.distance_transform_edt(~ch, return_indices=True)
    hand = np.where(valid, np.maximum(sm - sm[ri, ci], 0.0), 50.0).astype("float32")
    hand[ch] = 0.0
    dist = (ndimage.distance_transform_edt(~ch) * abs(tr.a)).astype("float32")

    # The older 2.5 km connectivity envelope caused a visually implausible city-wide spread.
    # Keep only cells hydraulically connected through the conservative near-river exercise corridor.
    work = np.where(dist <= KOK_CHANNEL_CORRIDOR_M, hand, 999.0)
    onset = priority_flood_onset(work, ch)
    onset = np.where(np.isfinite(onset) & (onset < 900), onset, 999.0).astype("float32")

    prof.update(dtype="float32", count=1, nodata=None, compress="deflate")
    tdir.mkdir(parents=True, exist_ok=True)
    for name, arr in (("hand", hand), ("onset", onset), ("distance_to_channel_m", dist)):
        with rasterio.open(tdir / f"{name}.tif", "w", **prof) as dst:
            dst.write(arr, 1)
    meta = {
        **expected,
        "source": "Copernicus DEM GLO-30 + OpenStreetMap Kylshakty centreline",
        "mode": SIM,
        "status": "HISTORICALLY_IMPACT_BOUNDED_EXERCISE",
        "caveat": (
            "The 100 m corridor is a conservative exercise envelope chosen to avoid city-wide over-spread. "
            "It is not an official flood-zone boundary, surveyed hydraulic capacity, or spatial validation."
        ),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**meta, "crs": prof["crs"].to_string()}

def build_kokshetau(out: Path) -> dict:
    from app.providers.flood.synthetic import SyntheticStageHandProvider

    area_id = "kokshetau"
    pack = pack_dir(area_id)
    cfg = C.load_json(CURATED / area_id / "config.json")
    epsg = 32642
    roads = C.build_roads(pack, epsg, prefix="K")
    proj: C.Projector = roads["_proj"]
    bld_raw = gpd.read_file(pack / "processed" / "argus_buildings.geojson")
    sectors = C.grid_sectors(bld_raw, epsg, 1500.0, 60, {
        "kk": "{code} талдау ұяшығы", "ru": "Аналитическая ячейка {code}", "en": "Analysis cell {code}"})
    bfeats, bgdf = C.build_buildings(pack, epsg, sectors, prefix="K")
    pz, pop_meta = C.population_zones(pack, bgdf, epsg, prefix="K")
    facilities = C.build_facilities(pack, sectors, prefix="K")
    bridges = C.build_bridges(pack, roads, deck_clearance_m=2.5, prefix="K")
    water_fc, river_lines = C.waterways_layer(pack, "қылшақты|кылшакты|kylshakty")
    river = C.merged_river(pack, "қылшақты|кылшакты|kylshakty", epsg)
    out.mkdir(parents=True, exist_ok=True)
    _kokshetau_terrain(pack, out, river)

    # SIMULATION exercise members: conservative water excess above the mapped Kylshakty channel.
    # The BASE envelope is historically impact-bounded against the *scale* of official 2024 reporting,
    # but there is no observed inundation polygon, so this is not spatial calibration.
    stage_peaks = KOK_STAGE_PEAKS_M
    offsets = list(range(-360, 721, 60))

    def series(peak_m: float) -> list[list[float]]:
        out_s = []
        for t in range(-360, 721, 10):
            x = (t - 360) / 300.0
            out_s.append([t, round(100.0 * peak_m * float(np.exp(-x * x)), 2)])
        return out_s

    members = [{"id": k, "label": {"LOW": "LOW (exercise)", "BASE": "BASE (exercise)", "HIGH": "HIGH (exercise)"}[k],
                "peak_stage_cm": round(v * 100), "peak_offset_h": 6.0, "stage_series": series(v), "snow_series": None}
               for k, v in stage_peaks.items()]
    P = SyntheticStageHandProvider(out / "terrain", members, 0.0)
    times = np.arange(-360, 721, 30, dtype=float)
    X, Y, S = _seg_samples(roads, proj)
    closures = {m["id"]: _closure_times(P.relative_level_points(m["id"], X, Y, times), S, times) for m in members}
    seg_props = {f["properties"]["id"]: f for f in roads["features"]}
    cx, cy = proj.xy(*cfg["center_wgs84"])
    # bases: OSM fire stations that stay dry in the HIGH member (a flooded station cannot be a safe base)
    fire = [f for f in facilities if f["properties"]["facility_type"] == "FIRE_STATION"]
    fxy = [proj.xy(*f["geometry"]["coordinates"]) for f in fire]
    flv = (P.relative_level_points("HIGH", np.array([p[0] for p in fxy]), np.array([p[1] for p in fxy]),
                                   np.arange(-360, 721, 60, dtype=float)) if fire else np.zeros((0, 1)))
    dry = [f for f, lv in zip(fire, flv, strict=True) if np.nanmax(np.where(np.isfinite(lv), lv, -9)) < -0.5]
    bases = [{"id": f"K-BASE-FIRE-{i + 1}", "lonlat": f["geometry"]["coordinates"], "safe": True,
              "names": _t(f"Өрт сөндіру бөлімі {i + 1} (OSM орны)", f"Пожарная часть {i + 1} (местоположение OSM)",
                          f"Fire station {i + 1} (OSM location)")} for i, f in enumerate(dry[:2])]
    if not bases:
        bases = [{"id": "K-BASE-1", "lonlat": cfg["center_wgs84"], "safe": True,
                  "names": _t("Жинақтау алаңы (жаттығу)", "Площадка сбора (учения)", "Staging base (exercise)")}]

    # ---------------------------------------------------------------- bottleneck candidates
    bottlenecks: list[dict] = []
    river_buf = river.buffer(60.0)
    for b in bridges:
        sid = b["properties"]["segment_ids"][0]
        seg_xy = LineString([proj.xy(*c) for c in seg_props[sid]["geometry"]["coordinates"]])
        over_river = seg_xy.intersects(river_buf)
        bottlenecks.append({"type": "Feature", "geometry": b["geometry"], "properties": {
            "id": f"KBN-{b['properties']['id']}", "kind": "BRIDGE", "segment_ids": [sid], "bridge_id": b["properties"]["id"],
            "notes": ("Candidate operational bottleneck: OSM bridge" + (" over the Kylshakty" if over_river else "")
                      + ". No surveyed hydraulic capacity."),
            **{k: b["properties"][k] for k in ("name_kk", "name_ru", "name_en", "name_original")}}})
    # culvert / channel-crossing candidates: road segments crossing mapped waterways without an OSM bridge
    wl = gpd.read_file(pack / "processed" / "osm_waterways.geojson")
    wl = wl[wl.geometry.geom_type.isin(["LineString", "MultiLineString"]) & wl.get("waterway").isin(["river", "stream", "canal", "ditch", "drain"])].to_crs(epsg)
    from shapely import STRtree
    wgeoms = list(wl.geometry)
    tree = STRtree(wgeoms)
    bridged = {s for b in bridges for s in b["properties"]["segment_ids"]}
    cands = []
    for f in roads["features"]:
        p = f["properties"]
        if p["id"] in bridged or p["road_class"] in ("residential", "living_street", "service"):
            continue
        ls = LineString([proj.xy(*c) for c in f["geometry"]["coordinates"]])
        hits = [int(i) for i in tree.query(ls, predicate="intersects")]
        if hits:
            ww = wl.iloc[hits[0]]
            pt = ls.intersection(wgeoms[hits[0]])
            pt = pt if pt.geom_type == "Point" else pt.representative_point() if not pt.is_empty else ls.interpolate(0.5, normalized=True)
            cands.append((C.CLASS_RANK.get(p["road_class"], 9), p["id"], pt, str(ww.get("waterway")), C.clean_str(ww.get("name"))))
    for _rank, sid, pt, wtype, wname in sorted(cands)[:6]:
        rp = seg_props[sid]["properties"]
        kind = "CULVERT" if wtype in ("stream", "ditch", "drain") else "CHANNEL_CONSTRAINT"
        lab = wname or wtype
        bottlenecks.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": proj.ll(pt.x, pt.y)}, "properties": {
            "id": f"KBN-X-{sid}", "kind": kind, "segment_ids": [sid], "bridge_id": None,
            "notes": f"Candidate {('culvert' if kind == 'CULVERT' else 'channel crossing')}: {rp['road_class']} road crosses mapped OSM {wtype} without a bridge tag. No surveyed dimensions.",
            "name_kk": f"Су өткізу қиылысы — {rp['name_kk']} × {lab}", "name_ru": f"Водопропускное пересечение — {rp['name_ru']} × {lab}",
            "name_en": f"Water crossing — {rp['name_en']} × {lab}", "name_original": rp["name_original"]}})
    # Candidate low-road bottlenecks should remain visible even after the conservative BASE envelope is
    # narrowed. Prefer major roads that become affected only in HIGH; if none do, fall back to the
    # closest major river-adjacent roads. A candidate is NOT a claim that the road flooded in 2024.
    low_added: set[str] = set()
    for sid, _t0 in sorted(closures["HIGH"].items(), key=lambda x: (x[1], x[0])):
        rp = seg_props[sid]["properties"]
        if rp["road_class"] in ("residential", "living_street", "service") or len(low_added) >= 4:
            continue
        mid = LineString(seg_props[sid]["geometry"]["coordinates"]).interpolate(0.5, normalized=True)
        bottlenecks.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [mid.x, mid.y]}, "properties": {
            "id": f"KBN-LOW-{sid}", "kind": "LOW_ROAD", "segment_ids": [sid], "bridge_id": None,
            "notes": "Candidate low road section on real terrain: affected in the HIGH exercise member. This is a SIMULATION candidate, not a reported 2024 road-flood observation.",
            "name_kk": f"Ойпаң жол учаскесі — {rp['name_kk']}", "name_ru": f"Низкий участок дороги — {rp['name_ru']}",
            "name_en": f"Low road section — {rp['name_en']}", "name_original": rp["name_original"]}})
        low_added.add(sid)
    if not low_added:
        near_major = []
        for sid, feat in seg_props.items():
            rp = feat["properties"]
            if sid in bridged or rp["road_class"] in ("residential", "living_street", "service"):
                continue
            ls_xy = LineString([proj.xy(*p) for p in feat["geometry"]["coordinates"]])
            d = float(ls_xy.distance(river))
            if d <= 300.0:
                near_major.append((d, sid))
        for d, sid in sorted(near_major)[:2]:
            rp = seg_props[sid]["properties"]
            mid = LineString(seg_props[sid]["geometry"]["coordinates"]).interpolate(0.5, normalized=True)
            bottlenecks.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [mid.x, mid.y]}, "properties": {
                "id": f"KBN-LOW-{sid}", "kind": "LOW_ROAD", "segment_ids": [sid], "bridge_id": None,
                "notes": f"Candidate low/river-adjacent major road ({d:.0f} m from mapped Kylshakty). Real geography; hydraulic vulnerability is NOT surveyed.",
                "name_kk": f"Өзен маңындағы жол үміткері — {rp['name_kk']}", "name_ru": f"Кандидат у реки — {rp['name_ru']}",
                "name_en": f"River-adjacent road candidate — {rp['name_en']}", "name_original": rp["name_original"]}})

    # ---------------------------------------------------------------- planning sites
    sites: list[dict] = []
    b_x = np.array([proj.xy(*shape(f["geometry"]).centroid.coords[0])[0] for f in bfeats])
    b_y = np.array([proj.xy(*shape(f["geometry"]).centroid.coords[0])[1] for f in bfeats])
    lvb = P.relative_level_points("BASE", b_x, b_y, np.array([360.0]))[:, 0]
    fl = np.flatnonzero(np.where(np.isfinite(lvb), lvb, -9) >= 0.10)
    bsec = [f["properties"]["sector_id"] for f in bfeats]
    for k, g in enumerate(_cluster(np.c_[b_x[fl], b_y[fl]], 250.0)[:3] if len(fl) else []):
        idx = fl[g]
        sec = max(set(bsec[i] for i in idx), key=[bsec[i] for i in idx].count)
        sites.append(C.point_feature(f"KS-PUMP-{k + 1}", proj.ll(float(b_x[idx].mean()), float(b_y[idx].mean())), {
            "kind": "DRAINAGE_POINT", "sector_id": sec, "protects": {"sector_ids": [sec]}, "work_depth_limit_m": 0.40,
            **_names_props(_t(f"Қылшақты бойындағы сорғы нүктесі {k + 1}", f"Точка откачки у Кылшакты {k + 1}",
                              f"Pumping point by the Kylshakty {k + 1}")),
            "source": f"{SIM} planning site — centroid of {len(idx)} buildings flooded in the BASE exercise member"}))
    for b in bottlenecks:
        if b["properties"]["kind"] in ("CULVERT", "CHANNEL_CONSTRAINT") and not any(s["properties"]["kind"] == "CULVERT" for s in sites):
            sites.append(C.point_feature("KS-CULVERT-1", b["geometry"]["coordinates"], {
                "kind": "CULVERT", "sector_id": None, "protects": {"road_ids": [seg_props[b["properties"]["segment_ids"][0]]["properties"]["road_id"]]},
                "work_depth_limit_m": 0.30, **_names_props(_t("Су өткізгішті тазарту нүктесі", "Точка прочистки водопропуска", "Culvert clearing point")),
                "source": f"{SIM} planning site at candidate {b['properties']['id']}"}))
    k = 0
    for b in bottlenecks:
        if b["properties"]["kind"] == "BRIDGE" and "Kylshakty" in b["properties"]["notes"] and k < 2:
            k += 1
            sites.append(C.point_feature(f"KS-BRIDGE-{k}", b["geometry"]["coordinates"], {
                "kind": "ROAD_CLOSURE", "sector_id": None, "protects": {"road_ids": [seg_props[b["properties"]["segment_ids"][0]]["properties"]["road_id"]]},
                "work_depth_limit_m": 0.30, **_names_props(_t(f"Көпір бақылау бекеті {k}", f"Пост контроля у моста {k}", f"Bridge control point {k}")),
                "source": f"{SIM} planning site at {b['properties']['id']}"}))
    fx = np.array([proj.xy(*f["geometry"]["coordinates"])[0] for f in facilities])
    fy = np.array([proj.xy(*f["geometry"]["coordinates"])[1] for f in facilities])
    flv = P.relative_level_points("HIGH", fx, fy, np.array([360.0]))[:, 0]
    pick = [int(i) for i in np.argsort(np.where(np.isfinite(flv), -flv, 99.0))[:2]]
    hosp = sorted((river.distance(Point(fx[i], fy[i])), i) for i, f in enumerate(facilities)
                  if f["properties"]["facility_type"] == "HOSPITAL")
    pick += [i for _, i in hosp[:2] if i not in pick]
    for i in pick:
        f = facilities[int(i)]["properties"]
        sites.append(C.point_feature(f"KS-{f['id']}", facilities[int(i)]["geometry"]["coordinates"], {
            "kind": "FACILITY", "sector_id": f["sector_id"], "protects": {"facility_ids": [f["id"]]}, "work_depth_limit_m": 0.25,
            **_names_props({"kk": f["name_kk"], "ru": f["name_ru"], "en": f["name_en"], "original": f["name_original"] or f["name_ru"]}),
            "source": f"{SIM} planning site — real OSM facility candidate"}))

    # ---------------------------------------------------------------- stations / observations (official, different datum)
    pr = river.interpolate(river.project(Point(cx, cy)))
    stations = [{"id": "KYL-PROXY", "lonlat": proj.ll(pr.x, pr.y), "river": "Kylshakty", "bankfull": 0, "watch": None, "warning": None,
                 "critical": None, "provider": "scenario_stage_proxy",
                 "names": _t("Қылшақты — жаттығу сценарийінің деңгейі (арна үстінде)", "Кылшакты — уровень учебного сценария (над руслом)",
                             "Kylshakty — exercise stage above channel")},
                {"id": "KYL-OFFICIAL", "lonlat": proj.ll(pr.x + 60, pr.y + 60), "river": "Kylshakty", "bankfull": None, "watch": None,
                 "warning": 110, "critical": 120, "provider": "official_report",
                 "threshold_note": "Operational thresholds from public reporting (1.10 safe conveyance, 1.20 critical); datum not established",
                 "names": _t("Қылшақты — ресми жедел есеп", "Кылшакты — официальная оперативная сводка", "Kylshakty — official operational report")}]
    observations = []
    for r in _read_csv(pack / "curated" / "hydrology" / "kylshakty_2024_observations.csv"):
        if r["measurement_type"] != "reported_level":
            continue
        observations.append({"station_id": "KYL-OFFICIAL", "observed_at": datetime.fromisoformat(r["observed_at"]).isoformat(),
                             "water_level_cm": round(float(r["water_level_m"]) * 100), "source_type": "HYDROPOST",
                             "verification": "UNVERIFIED", "source": f"Official report (gov.kz) — {r['source_url']}", "mode": "HISTORICAL",
                             "quality": "official_report · date", "notes": f"Datum not established; date precision. {r.get('notes') or ''}".strip(),
                             "use_for_conditioning": False})

    scenario = {
        "mode": SIM, "family_id": "kokshetau-exercise-2024", "issued_at": (KOK_REF - timedelta(hours=6)).isoformat(),
        "reference_time": KOK_REF.isoformat(), "frame_offsets_min": offsets, "series_step_min": 10, "bankfull_cm": 0,
        "station_id": "KYL-PROXY", "issued_member": "BASE", "members": members, "provider": "synthetic_stage_hand",
        "provider_config": {"terrain_dir": f"runtime/realdata/{area_id}/terrain", "has_ponding": False, "bankfull_cm": 0},
        "model_version": "conservative stage-HAND exercise on Copernicus DEM (impact-bounded, spatially uncalibrated)",
        "name": "Kokshetau — Kylshakty historically bounded operational exercise (SIMULATION)",
        "source": "ARGUS stage–HAND approximation on the real Copernicus DEM relative to the OSM Kylshakty",
        "note": (
            "SIMULATION exercise on real Kokshetau terrain. The earlier broad stage-HAND envelope was replaced by a "
            "conservative 100 m river-connected corridor and LOW/BASE/HIGH excess stages of 0.10/0.20/0.40 m. "
            "The BASE exercise is bounded only to the order of magnitude of the officially reported 2024 impacts "
            "(16 private houses, 29 private yards, 12 apartment courtyards and the first floor of Ertostik kindergarten). "
            "Those reported categories are NOT equivalent to modelled building footprints, so this is not a historical "
            "inundation reconstruction or forecast validation. Use it to exercise access/bottleneck consequences on real geography. "
            "Lake Kopa remains downstream receiving water, not the assumed flood cause."
        ),
        "limitations": [
            "Historically impact-bounded SIMULATION, not a spatially calibrated flood extent and not a prediction of which property will flood.",
            "Static stage–HAND approximation, not a hydraulic model; no surveyed culvert/bridge/channel hydraulics.",
            "The 100 m Kylshakty corridor is a conservative ARGUS exercise envelope, not an official flood-zone boundary.",
            "30 m DSM: buildings/trees bias terrain; urban drainage, frozen-ground runoff and snowmelt ponding are not explicitly resolved.",
            "Official Kylshakty levels use an unestablished gauge datum and are not used as a direct model stage."
        ],
    }
    plans = C.load_json(CURATED / area_id / "exercise" / "plans.json") if (CURATED / area_id / "exercise" / "plans.json").exists() else {"plans": [], "extra_candidates": []}
    area = {
        "id": area_id, "data_profile": "historical",
        "names": _t("Көкшетау — Қылшақты", "Кокшетау — Кылшакты", "Kokshetau — Kylshakty"),
        "river_names": _t("Қылшақты өзені", "река Кылшакты", "Kylshakty River"), "archetype": "URBAN_RIVER_BOTTLENECKS",
        "sort_order": 2, "crs_epsg": epsg, "center": cfg["center_wgs84"], "utc_offset_min": 300,
        "reference_time": KOK_REF.isoformat(), "clock_start": KOK_REF.isoformat(), "clock_mode": "HISTORICAL",
        "grid": {"dem": "processed/dem_kokshetau_utm42n.tif"}, "bbox": cfg["analysis_bbox_wgs84"],
        "stations": stations, "bases": bases, "river_lines": river_lines,
        "dem_path": f"<realdata>/{area_id}/generated/processed/dem_kokshetau_utm42n.tif",
        "economic_model": "exposure_only", "population_method": "worldpop_dasymetric",
        "pack": {"archive_sha256": status(area_id).archive_sha256, "run_id": 36886613476, "artifact_id": 11174708363},
        "assumptions": _assumptions(bridge_clearance=2.5), "population_meta": pop_meta, "road_meta": roads["_meta"],
        "role": "PORTABILITY_AND_BOTTLENECK_PILOT",
    }
    return _write_bundle(out, area, roads, bridges, bottlenecks, bfeats, sectors, pz, facilities, sites, _resources(bases, prefix="K"),
                         scenario, plans, observations, _history(pack, area_id, cfg), water_fc,
                         {"closures": {k: dict(sorted(v.items(), key=lambda x: x[1])) for k, v in closures.items()},
                          "flooded_buildings_base": int(len(fl)),
                          "flooded_buildings_base_peak": int(len(fl)),
                          "exercise_calibration": {
                              "status": "HISTORICALLY_IMPACT_BOUNDED_NOT_SPATIALLY_CALIBRATED",
                              "channel_corridor_m": KOK_CHANNEL_CORRIDOR_M,
                              "stage_peaks_m": KOK_STAGE_PEAKS_M,
                              "official_2024_reported_impact_scale": KOK_REPORTED_IMPACT_SCALE,
                              "modelled_base_building_centroids_depth_ge_0_10m": int(len(fl)),
                              "note": (
                                  "Reported houses/yards/courtyards/kindergarten are heterogeneous impact units, "
                                  "so ARGUS uses them only to reject obviously city-wide exercise spread, not as exact labels."
                              ),
                          }})


# ===================================================================================== shared
def _final_status(area: str, *keys: str):  # type: ignore[no-untyped-def]
    p = CURATED / "final_status.json"
    if not p.exists():
        return None
    d = C.load_json(p).get(area, {})
    for k in keys:
        d = d.get(k, {}) if isinstance(d, dict) else {}
    return d or None


def _assumptions(bridge_clearance: float) -> list[dict]:
    return [
        {"key": "speed_caps", "value": C.SPEED_CAP_KMH, "note": "Operational speed caps by OSM class (km/h); OSMnx-imputed speeds are capped."},
        {"key": "one_way", "value": "ignored", "note": "Emergency vehicles may use one-way streets in both directions."},
        {"key": "road_surface", "value": 0.0, "note": "Road surface assumed at DEM ground level (no embankment survey)."},
        {"key": "bridge_clearance_m", "value": bridge_clearance, "note": "Assumed deck clearance above the river proxy level (no survey)."},
        {"key": "facility_criticality", "value": C.FACILITY_CRITICALITY_POLICY, "note": "ARGUS default policy by type — requires specialist review."},
        {"key": "sectors", "value": "analysis grid", "note": "Sectors are analysis grid cells, not administrative boundaries."},
        {"key": "resources", "value": SIM, "note": "No verified agency inventory: crews, vehicles, pumps and equipment are SIMULATION."},
        {"key": "economic", "value": "exposure_only", "note": "No approved regional valuation table: exposure is reported as floor area, no money."},
    ]


def _resources(bases: list[dict], prefix: str = "") -> dict:
    b1 = bases[0]["id"]
    b2 = bases[1]["id"] if len(bases) > 1 else b1
    res = [
        ("C1", "CREW", "ENGINEERING", b1, 6, "persons"), ("C2", "CREW", "ENGINEERING", b2, 6, "persons"),
        ("C3", "CREW", "GENERAL", b1, 4, "persons"), ("C4", "CREW", "GENERAL", b1, 4, "persons"),
        ("C5", "CREW", "RESCUE", b1, 5, "persons"), ("C6", "CREW", "RESCUE", b2, 5, "persons"),
        ("V1", "VEHICLE", "TRUCK", b1, 8, "t"), ("V2", "VEHICLE", "TRUCK", b1, 8, "t"), ("V3", "VEHICLE", "TRUCK", b2, 10, "t"),
        ("V4", "VEHICLE", "HIGH_CLEARANCE", b1, 3, "t"), ("V5", "VEHICLE", "HIGH_CLEARANCE", b2, 3, "t"),
        ("V6", "VEHICLE", "PICKUP", b1, 1, "t"),
        ("EQ1", "EQUIPMENT", "EXCAVATOR", b2, None, None), ("EQ2", "EQUIPMENT", "SANDBAG_FILLER", b1, 600, "bags/h"),
        ("EQ3", "EQUIPMENT", "SANDBAG_FILLER", b2, 600, "bags/h"),
    ]
    res += [(f"P{i:02d}", "PUMP", "MOBILE_PUMP", b1 if i <= 10 else b2, 300 if i % 3 == 0 else 200, "m3/h") for i in range(1, 17)]
    return {"mode": SIM, "note": "SIMULATION resource register — not DChS/MChS inventory.",
            "resources": [{"id": f"{prefix}{i}", "type": t, "subtype": s, "base": b, "capacity": c, "unit": u}
                          for i, t, s, b, c, u in res]}


def _history(pack: Path, area_id: str, cfg: dict) -> dict:
    def rows(p: Path) -> list[dict]:
        return _read_csv(p)

    ctx = pack / "context"
    glofas = C.load_json(ctx / "glofas_event_discharge.json") if (ctx / "glofas_event_discharge.json").exists() else {}
    events_file = "atbasar_flood_2024_events.csv" if area_id == "atbasar" else "kokshetau_flood_2024_events.csv"
    hydro = rows(pack / "curated" / "hydrology" / ("zhabai_2024_observations.csv" if area_id == "atbasar" else "kylshakty_2024_observations.csv"))
    out = {
        "mode": "HISTORICAL",
        "events": rows(pack / "curated" / "events" / events_file),
        "hydrology": hydro,
        "event_peak": rows(pack / "curated" / "hydrology" / "zhabai_2024_event_peak.csv") if area_id == "atbasar" else [],
        "glofas": {"rows": rows(ctx / "glofas_event_discharge.csv"), "source": glofas.get("source"), "quality": glofas.get("quality"),
                   "requested_coordinate": glofas.get("requested_coordinate"), "returned_coordinate": glofas.get("returned_coordinate"),
                   "caveat": glofas.get("caveat")},
        "weather": {"rows": rows(ctx / "historical_weather_daily.csv"), "source": "Open-Meteo Historical Weather API",
                    "quality": "REANALYSIS_OR_HISTORICAL_MODEL"},
        "config": {k: cfg.get(k) for k in ("display_name", "event", "scientific_note", "modelling_role", "receiving_water") if k in cfg},
    }
    if area_id == "atbasar":
        out["satellite"] = C.load_json(pack / "metadata" / "sentinel2_selection.json")
        out["mask_method"] = C.load_json(pack / "metadata" / "flood_mask_method.json")
    evidence_file = CURATED / area_id / "historical_evidence.json"
    if evidence_file.exists():
        out["spatial_evidence"] = C.load_json(evidence_file)
    return out


def _write_bundle(out: Path, area: dict, roads: dict, bridges: list, bottlenecks: list, buildings: list, sectors: list,
                  pz: list, facilities: list, sites: list, resources: dict, scenario: dict, plans: dict, observations: list,
                  history: dict, waterways: dict, analysis: dict) -> dict:
    out.mkdir(parents=True, exist_ok=True)

    def fc(features: list) -> dict:
        return {"type": "FeatureCollection", "features": features}

    C.dump_json(out / "area.json", area)
    C.dump_json(out / "roads.geojson", {"type": "FeatureCollection", "nodes": roads["nodes"], "features": roads["features"]})
    for name, feats in (("bridges", bridges), ("bottlenecks", bottlenecks), ("buildings", buildings), ("sectors", sectors),
                        ("population_zones", pz), ("facilities", facilities), ("task_sites", sites)):
        C.dump_json(out / f"{name}.geojson", fc(feats))
    C.dump_json(out / "resources.json", resources)
    C.dump_json(out / "scenario.json", scenario)
    C.dump_json(out / "plans.json", plans)
    C.dump_json(out / "observations.json", {"observations": observations})
    C.dump_json(out / "history.json", history)
    C.dump_json(out / "waterways.geojson", waterways)
    C.dump_json(out / "analysis.json", analysis)
    summary = {"area": area["id"], "segments": len(roads["features"]), "nodes": len(roads["nodes"]), "buildings": len(buildings),
               "sectors": len(sectors), "population_zones": len(pz), "facilities": len(facilities), "bridges": len(bridges),
               "bottlenecks": len(bottlenecks), "task_sites": [s["properties"]["id"] for s in sites]}
    return summary


BUILDERS = {"atbasar": build_atbasar, "kokshetau": build_kokshetau}


def ensure_built(area: str, force: bool = False) -> Path:
    """Build the fixture bundle once per pack/exercise/builder fingerprint (no network)."""
    out = runtime_dir(area)
    fp = _fingerprint(area)
    marker = out / "build_info.json"
    if not force and marker.exists():
        try:
            if json.loads(marker.read_text(encoding="utf-8")).get("fingerprint") == fp:
                return out
        except ValueError:
            pass
    if not status(area).installed:
        raise RuntimeError(f"real-data pack for {area} is not installed (python -m app.cli install-realdata)")
    log.info("building %s real-data fixtures → %s", area, out)
    summary = BUILDERS[area](out)
    marker.write_text(json.dumps({"fingerprint": fp, "builder_version": BUILDER_VERSION, "summary": summary,
                                  "built_at": datetime.utcnow().isoformat() + "Z"}, indent=2), encoding="utf-8")
    return out
