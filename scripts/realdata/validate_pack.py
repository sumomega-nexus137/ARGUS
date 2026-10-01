#!/usr/bin/env python3
"""Integrity/contract validation for ARGUS real-data packs.

This checks that generated files are readable, geospatially sane and internally
consistent. It does not turn an unreviewed SAR flood mask into ground truth and
does not compute model accuracy without a modelled mask.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

ROOT = Path(__file__).resolve().parents[2]


def add(report, name, ok, detail="", required=True):
    report.append({"check": name, "ok": bool(ok), "required": required, "detail": detail})
    state = "PASS" if ok else ("WARN" if not required else "FAIL")
    print(f"[{state}] {name}: {detail}")


def validate_raster(path: Path, expected_crs: str, report: list, required=True):
    if not path.exists():
        add(report, f"raster:{path.name}", False, "missing", required)
        return
    try:
        with rasterio.open(path) as src:
            arr = src.read(1, masked=True)
            valid = np.asarray(~arr.mask) if np.ndim(arr.mask) else np.ones(arr.shape, dtype=bool)
            vals = np.asarray(arr.data)[valid]
            valid_fraction = float(valid.mean()) if valid.size else 0.0
            finite_fraction = float(np.isfinite(vals).mean()) if vals.size else 0.0
            px = (abs(float(src.transform.a)), abs(float(src.transform.e)))
            ok = (
                src.width > 0 and src.height > 0 and src.crs is not None
                and src.crs.to_string() == expected_crs
                and valid_fraction > 0.001 and finite_fraction > 0.99
                and 0 < px[0] <= 500 and 0 < px[1] <= 500
            )
            detail = (
                f"{src.width}x{src.height}, crs={src.crs}, px={px}, "
                f"valid={valid_fraction:.3f}, finite={finite_fraction:.3f}"
            )
            add(report, f"raster:{path.name}", ok, detail, required)
    except Exception as exc:
        add(report, f"raster:{path.name}", False, repr(exc), required)


def validate_geojson(path: Path, report: list, required=True, allow_empty=False):
    if not path.exists():
        add(report, f"vector:{path.name}", False, "missing", required)
        return
    try:
        g = gpd.read_file(path)
        valid = bool(g.geometry.is_valid.fillna(False).all()) if len(g) else allow_empty
        nonempty = len(g) > 0 or allow_empty
        crs_ok = g.crs is not None and g.crs.to_string() in {"EPSG:4326", "OGC:CRS84"}
        add(
            report,
            f"vector:{path.name}",
            valid and nonempty and crs_ok,
            f"features={len(g)}, crs={g.crs}, geometries_valid={valid}",
            required,
        )
    except Exception as exc:
        add(report, f"vector:{path.name}", False, repr(exc), required)


def validate_csv(path: Path, required_columns: list[str], report: list, required=True):
    if not path.exists():
        add(report, f"csv:{path.name}", False, "missing", required)
        return
    try:
        df = pd.read_csv(path)
        missing = [c for c in required_columns if c not in df.columns]
        dupes = int(df.duplicated().sum())
        ok = len(df) > 0 and not missing and dupes == 0
        add(report, f"csv:{path.name}", ok, f"rows={len(df)}, missing={missing}, exact_duplicates={dupes}", required)
    except Exception as exc:
        add(report, f"csv:{path.name}", False, repr(exc), required)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", choices=["atbasar", "kokshetau"], required=True)
    ap.add_argument("--root", type=Path)
    args = ap.parse_args()

    area = args.area
    base = args.root or ROOT / "data" / "realdata" / area / "generated"
    cfg_path = ROOT / "data" / "realdata" / area / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    expected_crs = cfg["projected_crs"]
    report = []

    manifest = base / "metadata" / "dataset_manifest.json"
    add(report, "manifest", manifest.exists(), str(manifest), True)
    if manifest.exists():
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
            listed = m.get("files", [])
            missing = [x["path"] for x in listed if not (base / x["path"]).exists()]
            add(report, "manifest:file_references", not missing, f"listed={len(listed)}, missing={missing[:10]}", True)
            add(report, "manifest:area_id", m.get("area_id") == cfg["area_id"], f"{m.get('area_id')} vs {cfg['area_id']}", True)
        except Exception as exc:
            add(report, "manifest:parse", False, repr(exc), True)

    dem_name = "dem_atbasar_utm42n.tif" if area == "atbasar" else "dem_kokshetau_utm42n.tif"
    slope_name = "slope_atbasar_deg.tif" if area == "atbasar" else "slope_kokshetau_deg.tif"
    validate_raster(base / "processed" / dem_name, expected_crs, report)
    validate_raster(base / "processed" / slope_name, expected_crs, report)
    validate_geojson(base / "processed" / "argus_roads.geojson", report)
    validate_geojson(base / "processed" / "argus_road_nodes.geojson", report)
    validate_geojson(base / "processed" / "argus_buildings.geojson", report)
    validate_geojson(base / "processed" / "osm_waterways.geojson", report, required=False, allow_empty=True)
    validate_geojson(base / "processed" / "osm_bridges_culverts.geojson", report, required=False, allow_empty=True)
    validate_geojson(base / "processed" / "argus_critical_facilities.geojson", report, required=False, allow_empty=True)
    validate_raster(base / "processed" / "worldpop_2024_100m_utm42n.tif", expected_crs, report, required=False)

    if area == "atbasar":
        validate_raster(base / "processed" / "sentinel1_pre_vv.tif", expected_crs, report)
        validate_raster(base / "processed" / "sentinel1_flood_vv.tif", expected_crs, report)
        validate_raster(base / "processed" / "observed_flood_mask_2024.tif", expected_crs, report)
        selection = base / "metadata" / "sentinel1_selection.json"
        if selection.exists():
            s = json.loads(selection.read_text(encoding="utf-8"))
            same_orbit = (
                s.get("pre_relative_orbit") is None or s.get("flood_relative_orbit") is None
                or s.get("pre_relative_orbit") == s.get("flood_relative_orbit")
            )
            add(report, "sentinel1:same_relative_orbit", same_orbit, json.dumps({
                "pre": s.get("pre_relative_orbit"), "flood": s.get("flood_relative_orbit")
            }), False)
            add(report, "sentinel1:observed_mask_qc_state", True, "REQUIRES_QC is expected; this validator does not certify ground truth.", False)
        else:
            add(report, "sentinel1:selection", False, "missing selection metadata", True)
        validate_csv(
            base / "curated" / "hydrology" / "zhabai_2024_observations.csv",
            ["timestamp_local", "value", "reference_type", "source_url"],
            report,
            True,
        )
    else:
        validate_csv(
            base / "curated" / "hydrology" / "kylshakty_2024_observations.csv",
            ["observed_at", "water_level_m", "measurement_type", "source_url"],
            report,
            True,
        )
        validate_csv(
            base / "curated" / "events" / "kokshetau_flood_2024_events.csv",
            ["event_time", "event_type", "description", "source_url"],
            report,
            True,
        )

    out = base / "metadata" / "integrity_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "area": area,
        "checks": report,
        "required_failures": [x for x in report if x["required"] and not x["ok"]],
        "warnings": [x for x in report if not x["required"] and not x["ok"]],
    }, indent=2), encoding="utf-8")

    failures = [x for x in report if x["required"] and not x["ok"]]
    if failures:
        print(f"Required failures: {len(failures)}", file=sys.stderr)
        sys.exit(1)
    print("All required data integrity checks passed.")


if __name__ == "__main__":
    main()
