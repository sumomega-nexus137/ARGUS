#!/usr/bin/env python3
"""Build Atbasar terrain-conditioned flood scenario rasters for ARGUS.

This is deliberately a HAND-like / river-relative terrain proxy, not a full
hydrodynamic solver. It uses real Copernicus DEM, the OSM Zhabai river geometry
and the satellite-derived 2024 flood-observation baseline prepared by the
real-data pipeline.

Calibration is performed on alternating spatial blocks and reported separately
from a spatial holdout within the same event. These numbers are therefore
historical event-fit evidence, NOT out-of-event forecast skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize, shapes
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")



def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def refresh_dataset_manifest(pack: Path) -> None:
    manifest_path = pack / "metadata" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    files = []
    for p in sorted(pack.rglob("*")):
        if p.is_file() and "raw" not in p.parts and p != manifest_path:
            files.append({
                "path": str(p.relative_to(pack)),
                "bytes": p.stat().st_size,
                "sha256": sha256(p),
            })
    manifest["files"] = files
    manifest.setdefault("quality_gates", {})
    manifest["quality_gates"].update({
        "scenario_model": "TERRAIN_CONDITIONED_PROXY_NOT_FULL_HYDRODYNAMIC_MODEL",
        "scenario_metrics": "HISTORICAL_SAME_EVENT_SPATIAL_HOLDOUT_NOT_OUT_OF_EVENT_SKILL",
        "modelled_validation_mask": "PROVISIONAL_UNTIL_OBSERVED_SATELLITE_MASK_DOMAIN_QC",
    })
    write_json(manifest_path, manifest)

def read_raster(path: Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        arr = src.read(1, masked=True).filled(np.nan).astype("float32")
        meta = {
            "profile": src.profile.copy(),
            "transform": src.transform,
            "crs": src.crs,
            "width": src.width,
            "height": src.height,
            "nodata": src.nodata,
        }
    return arr, meta


def align_to(ref_meta: dict, path: Path, nearest: bool = False, dst_nodata=np.nan) -> np.ndarray:
    with rasterio.open(path) as src:
        out = np.full((ref_meta["height"], ref_meta["width"]), dst_nodata, dtype="float32")
        src_arr = src.read(1).astype("float32")
        reproject(
            source=src_arr,
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=ref_meta["transform"],
            dst_crs=ref_meta["crs"],
            dst_nodata=dst_nodata,
            resampling=Resampling.nearest if nearest else Resampling.bilinear,
        )
        return out


def write_float(path: Path, arr: np.ndarray, ref_meta: dict) -> None:
    p = ref_meta["profile"].copy()
    p.update(driver="GTiff", dtype="float32", count=1, nodata=-9999.0, compress="deflate", tiled=True)
    data = np.where(np.isfinite(arr), arr, -9999.0).astype("float32")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **p) as dst:
        dst.write(data, 1)


def select_zhabai(waterways: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    cols = [c for c in ("name", "name:ru", "name:kk", "name:en") if c in waterways.columns]
    mask = np.zeros(len(waterways), dtype=bool)
    for col in cols:
        s = waterways[col].fillna("").astype(str).str.lower()
        mask |= s.str.contains("жабай|zhabai", regex=True).to_numpy()
    if "waterway" in waterways.columns:
        mask &= waterways["waterway"].fillna("").astype(str).str.lower().eq("river").to_numpy()
    z = waterways.loc[mask].copy()
    z = z[z.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    if z.empty:
        raise RuntimeError("Zhabai river linework not found in OSM waterway layer")
    return z


def metrics(obs: np.ndarray, mod: np.ndarray, valid: np.ndarray) -> dict:
    o = obs & valid
    m = mod & valid
    tp = int((o & m).sum())
    fp = int((~o & m & valid).sum())
    fn = int((o & ~m & valid).sum())
    tn = int((~o & ~m & valid).sum())

    def ratio(n: int, d: int):
        return None if d == 0 else float(n / d)

    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    iou = ratio(tp, tp + fp + fn)
    f1 = None if precision is None or recall is None or precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "positives_observed": int(o.sum()),
        "positives_modelled": int(m.sum()),
        "evaluated_cells": int(valid.sum()),
        "iou": iou, "precision": precision, "recall": recall, "f1": f1,
    }


def connected_to_river(candidate: np.ndarray, river_mask: np.ndarray) -> np.ndarray:
    labels, _ = ndimage.label(candidate, structure=np.ones((3, 3), dtype="uint8"))
    touched = np.unique(labels[river_mask & candidate])
    touched = touched[touched != 0]
    if touched.size == 0:
        return np.zeros_like(candidate, dtype=bool)
    return np.isin(labels, touched)


def build_validation_aoi(common_clear_path: Path, validation_dir: Path) -> None:
    with rasterio.open(common_clear_path) as src:
        arr = src.read(1) >= 0.5
        tr = src.transform
        crs = src.crs
    geoms = [shape(g) for g, v in shapes(arr.astype("uint8"), mask=arr, transform=tr) if int(v) == 1]
    if not geoms:
        raise RuntimeError("No usable optical validation pixels")
    merged = unary_union(geoms)
    gdf = gpd.GeoDataFrame({"kind": ["SATELLITE_USABLE_AOI"]}, geometry=[merged], crs=crs).to_crs("EPSG:4326")
    validation_dir.mkdir(parents=True, exist_ok=True)
    gdf.to_file(validation_dir / "aoi.geojson", driver="GeoJSON")


def reproject_modelled_mask(model_mask: np.ndarray, dem_meta: dict, observed_path: Path, out_path: Path) -> None:
    with rasterio.open(observed_path) as obs:
        dst = np.zeros((obs.height, obs.width), dtype="uint8")
        reproject(
            source=model_mask.astype("uint8"),
            destination=dst,
            src_transform=dem_meta["transform"],
            src_crs=dem_meta["crs"],
            dst_transform=obs.transform,
            dst_crs=obs.crs,
            src_nodata=0,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
        p = obs.profile.copy()
        p.update(dtype="uint8", count=1, nodata=None, compress="deflate", tiled=True)
        with rasterio.open(out_path, "w", **p) as fh:
            fh.write(dst, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", type=Path, default=ROOT / "data" / "realdata" / "atbasar" / "generated")
    args = ap.parse_args()
    pack = args.pack.resolve()
    processed = pack / "processed"
    validation_dir = pack / "validation" / "atbasar" / "atbasar-2024"
    scenario_dir = pack / "scenarios" / "atbasar"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    dem, dm = read_raster(processed / "dem_atbasar_utm42n.tif")
    slope = align_to(dm, processed / "slope_atbasar_deg.tif")
    valid_dem = np.isfinite(dem)
    if int(valid_dem.sum()) < 10000:
        raise RuntimeError("DEM has insufficient valid coverage")

    # Suppress small DSM speckle before deriving river-relative elevation.
    fill = float(np.nanmedian(dem))
    smooth = ndimage.median_filter(np.where(valid_dem, dem, fill), size=3)

    waterways = gpd.read_file(processed / "osm_waterways.geojson")
    zhabai = select_zhabai(waterways).to_crs(dm["crs"])
    river_mask = rasterize(
        [(geom, 1) for geom in zhabai.geometry if geom is not None and not geom.is_empty],
        out_shape=(dm["height"], dm["width"]),
        transform=dm["transform"],
        fill=0,
        all_touched=True,
        dtype="uint8",
    ).astype(bool)
    river_mask = ndimage.binary_dilation(river_mask, iterations=1)
    if int(river_mask.sum()) < 20:
        raise RuntimeError("Rasterized Zhabai channel is unexpectedly small")

    yres = abs(float(dm["transform"].e))
    xres = abs(float(dm["transform"].a))
    distance_m, nearest_idx = ndimage.distance_transform_edt(
        ~river_mask,
        sampling=(yres, xres),
        return_indices=True,
    )
    channel_elev = smooth[nearest_idx[0], nearest_idx[1]]
    relative = smooth - channel_elev
    relative = np.where(valid_dem & np.isfinite(channel_elev), np.maximum(relative, 0.0), np.nan).astype("float32")
    distance_m = np.where(valid_dem, distance_m, np.nan).astype("float32")

    write_float(scenario_dir / "relative_elevation_to_zhabai.tif", relative, dm)
    write_float(scenario_dir / "distance_to_zhabai_m.tif", distance_m, dm)

    observed = align_to(dm, processed / "observed_flood_mask_2024.tif", nearest=True, dst_nodata=0) >= 0.5
    common_clear = align_to(dm, processed / "sentinel2_common_clear_mask.tif", nearest=True, dst_nodata=0) >= 0.5
    jrc_path = processed / "jrc_water_occurrence_utm42n.tif"
    if jrc_path.exists():
        jrc = align_to(dm, jrc_path, nearest=True, dst_nodata=255)
        permanent = (jrc != 255) & (jrc >= 90)
    else:
        permanent = np.zeros_like(observed, dtype=bool)

    domain = valid_dem & np.isfinite(relative) & np.isfinite(distance_m) & np.isfinite(slope) & (slope <= 7.0)
    eval_valid = domain & common_clear & ~permanent & (distance_m <= 8000)
    if int((observed & eval_valid).sum()) < 100:
        raise RuntimeError("Too few observed flood pixels inside usable calibration domain")

    rows, cols = np.indices(observed.shape)
    block_px = max(8, int(round(1200.0 / max(xres, yres))))
    checker = ((rows // block_px) + (cols // block_px)) % 2
    train = eval_valid & (checker == 0)
    holdout = eval_valid & (checker == 1)
    if int((observed & train).sum()) < 50 or int((observed & holdout).sum()) < 50:
        # Deterministic fallback to full-event fit if spatial split is too sparse.
        train = eval_valid.copy()
        holdout = eval_valid.copy()
        holdout_note = "Spatial split too sparse; holdout duplicates full usable AOI."
    else:
        holdout_note = "Alternating ~1.2 km spatial blocks withheld from parameter selection."

    # Calibrate on a 2x subsample for speed. IoU ignores true negatives, so
    # large dry areas do not artificially inflate the objective.
    sl = np.s_[::2, ::2]
    obs_s = observed[sl]
    train_s = train[sl]
    rel_s = relative[sl]
    dist_s = distance_m[sl] / 1000.0
    domain_s = domain[sl]

    stage_grid = np.round(np.linspace(0.4, 3.2, 15), 2)
    attenuation_grid = [0.0, 0.10, 0.20, 0.35, 0.50, 0.75]
    max_distance_grid = [1.5, 2.5, 3.5, 5.0, 6.5, 8.0]

    ranked = []
    for attenuation in attenuation_grid:
        eff = rel_s + attenuation * dist_s
        for max_km in max_distance_grid:
            spatial = domain_s & (dist_s <= max_km)
            for stage in stage_grid:
                cand = spatial & (eff <= stage)
                met = metrics(obs_s, cand, train_s)
                score = -1.0 if met["iou"] is None else met["iou"]
                ranked.append({
                    "stage_excess_proxy_m": float(stage),
                    "distance_attenuation_m_per_km": float(attenuation),
                    "max_floodplain_distance_km": float(max_km),
                    "train_iou_subsample": float(score),
                    "train_precision_subsample": met["precision"],
                    "train_recall_subsample": met["recall"],
                })

    ranked.sort(key=lambda x: (
        x["train_iou_subsample"],
        x["train_recall_subsample"] or -1,
        x["train_precision_subsample"] or -1,
    ), reverse=True)
    best = ranked[0]

    stage = best["stage_excess_proxy_m"]
    attenuation = best["distance_attenuation_m_per_km"]
    max_km = best["max_floodplain_distance_km"]
    eff_full = relative + attenuation * (distance_m / 1000.0)
    raw_base = domain & (distance_m <= max_km * 1000.0) & (eff_full <= stage)
    base_connected = connected_to_river(raw_base, river_mask)

    train_metrics = metrics(observed, base_connected & ~permanent, train)
    holdout_metrics = metrics(observed, base_connected & ~permanent, holdout)
    all_metrics = metrics(observed, base_connected & ~permanent, eval_valid)

    # Historical validation mask is the modelled flood expansion, excluding
    # permanent-water pixels exactly as the observed-change mask does.
    model_validation = base_connected & ~permanent
    reproject_modelled_mask(
        model_validation,
        dm,
        processed / "observed_flood_mask_2024.tif",
        validation_dir / "modelled.tif",
    )
    build_validation_aoi(processed / "sentinel2_common_clear_mask.tif", validation_dir)

    calibration = {
        "model_kind": "TERRAIN_CONDITIONED_RIVER_RELATIVE_PROXY",
        "not_a_hydrodynamic_model": True,
        "river": "Zhabai",
        "terrain_source": "Copernicus DEM GLO-30",
        "river_geometry_source": "OpenStreetMap",
        "observed_source": "Sentinel-2 L2A flood-vs-post-recession change baseline",
        "selection_objective": "maximize IoU on alternating spatial calibration blocks",
        "best_parameters": best,
        "train_metrics_full_resolution": train_metrics,
        "spatial_holdout_metrics_same_event": holdout_metrics,
        "all_usable_pixels_metrics": all_metrics,
        "holdout_note": holdout_note,
        "evaluation_excludes": [
            "pixels unusable in either selected optical scene",
            "JRC >=90% long-term permanent water",
            "terrain >8 km from rasterized Zhabai for calibration/evaluation",
        ],
        "scientific_limitations": [
            "This is a terrain-conditioned river-relative proxy, not HEC-RAS/LISFLOOD-FP or a surveyed hydraulic model.",
            "The same historical event supplies the satellite target; the spatial holdout is not out-of-event validation.",
            "DEM is a ~30 m DSM and local levees/culverts/channel bathymetry are not surveyed here.",
            "Gauge stage and the calibrated terrain proxy are related only for scenario presentation; this is not a validated stage-discharge-depth rating curve.",
            "Observed satellite mask remains subject to manual/domain QC.",
        ],
        "top_20_parameter_sets": ranked[:20],
    }
    write_json(scenario_dir / "calibration_metrics.json", calibration)

    # Produce precomputed depth frames for the existing RasterManifestProvider.
    # The base proxy is calibrated to the historical extent; LOW/HIGH are
    # sensitivity/stress-test members, not probabilistic return periods.
    offsets = [-360, -180, 0, 180, 360]
    fractions = [0.35, 0.65, 1.0, 0.75, 0.45]
    members_cfg = [
        ("LOW", "LOW sensitivity", 0.85, 550.0),
        ("BASE", "BASE calibrated", 1.00, 595.0),
        ("HIGH", "HIGH stress", 1.20, 620.0),
    ]
    bankfull_cm = 445.0
    members = []
    for member_id, label, stage_factor, peak_cm in members_cfg:
        frames = []
        gauge = []
        member_dir = scenario_dir / member_id
        member_dir.mkdir(parents=True, exist_ok=True)
        for offset, frac in zip(offsets, fractions, strict=True):
            proxy_stage = max(0.05, stage * stage_factor * frac)
            raw = domain & (distance_m <= max_km * 1000.0) & (eff_full <= proxy_stage)
            conn = connected_to_river(raw, river_mask)
            depth = np.where(conn, np.maximum(proxy_stage - eff_full, 0.0), 0.0).astype("float32")
            frame_path = member_dir / f"f_{offset}.tif"
            write_float(frame_path, depth, dm)
            frames.append({"offset_min": offset, "depth_path": str(frame_path.relative_to(scenario_dir))})
            gauge_cm = bankfull_cm + frac * (peak_cm - bankfull_cm)
            gauge.append([offset, round(float(gauge_cm), 1)])
        members.append({
            "id": member_id,
            "label": label,
            "gauge": gauge,
            "frames": frames,
        })

    manifest = {
        "crs": dm["crs"].to_string(),
        "bankfull_cm": bankfull_cm,
        "hand_path": "relative_elevation_to_zhabai.tif",
        "members": members,
        "method": "terrain-conditioned river-relative elevation + distance attenuation + river connectivity",
        "calibration_file": "calibration_metrics.json",
        "status": "HISTORICAL_CALIBRATED_PROXY_REQUIRES_DOMAIN_QC",
    }
    write_json(scenario_dir / "manifest.json", manifest)

    # Update validation metadata without pretending the result is independent forecast skill.
    meta_path = validation_dir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.update({
        "modelled_status": "LOADED_PROVISIONAL",
        "modelled_source": "ARGUS terrain-conditioned river-relative proxy",
        "evaluation_aoi": "Sentinel-2 pixels usable in both selected scenes",
        "metrics_status": "COMPUTABLE_BUT_HISTORICAL_SAME_EVENT_SPATIAL_HOLDOUT",
        "calibration_metrics_path": "scenarios/atbasar/calibration_metrics.json",
    })
    write_json(meta_path, meta)
    refresh_dataset_manifest(pack)

    print(json.dumps({
        "best_parameters": best,
        "train": train_metrics,
        "holdout": holdout_metrics,
        "all": all_metrics,
        "manifest": str(scenario_dir / "manifest.json"),
        "validation_model": str(validation_dir / "modelled.tif"),
    }, indent=2))


if __name__ == "__main__":
    main()
