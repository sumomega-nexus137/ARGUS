#!/usr/bin/env python3
"""Build the real Kokshetau/Kylshakty static evidence pack for ARGUS FloodOps.

Kokshetau is the portability/bottleneck pilot. This pipeline intentionally does
not manufacture a 2024 Sentinel validation mask: Atbasar remains the primary
historical validation area. It prepares terrain, roads, buildings, waterways,
candidate facilities, population exposure, and curated official event records.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ATBASAR_PIPELINE = ROOT / "scripts" / "realdata" / "atbasar_pipeline.py"
CFG_PATH = ROOT / "data" / "realdata" / "kokshetau" / "config.json"
CURATED = ROOT / "data" / "realdata" / "kokshetau"

spec = importlib.util.spec_from_file_location("argus_atbasar_realdata_shared", ATBASAR_PIPELINE)
shared = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(shared)


def load_cfg() -> dict:
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def rename_terrain(out: Path) -> None:
    pairs = [
        ("dem_atbasar_utm42n.tif", "dem_kokshetau_utm42n.tif"),
        ("slope_atbasar_deg.tif", "slope_kokshetau_deg.tif"),
    ]
    for old, new in pairs:
        src = out / "processed" / old
        dst = out / "processed" / new
        if src.exists():
            src.replace(dst)
        old_side = Path(str(src) + ".provenance.json")
        new_side = Path(str(dst) + ".provenance.json")
        if old_side.exists():
            old_side.replace(new_side)


def copy_curated(out: Path) -> None:
    dst = out / "curated"
    for rel in [
        "hydrology/kylshakty_2024_observations.csv",
        "events/kokshetau_flood_2024_events.csv",
    ]:
        src = CURATED / rel
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def manifest(cfg: dict, out: Path, statuses: dict) -> None:
    files = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and "raw" not in p.parts and p.name != "dataset_manifest.json":
            files.append({
                "path": str(p.relative_to(out)),
                "bytes": p.stat().st_size,
                "sha256": shared.sha256(p),
            })
    shared.write_json(out / "metadata" / "dataset_manifest.json", {
        "area_id": cfg["area_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "working_crs": cfg["projected_crs"],
        "source_mode": "REAL_OPEN_DATA_AND_OFFICIAL_CURATED_HISTORY",
        "pilot_role": "PORTABILITY_AND_BOTTLENECK",
        "pipeline_status": statuses,
        "files": files,
        "quality_gates": {
            "hydrology": "PUBLIC_REPORT_VALUES_REQUIRE_DATUM_CONFIRMATION_BEFORE_MERGING_WITH_SENSOR_SERIES",
            "critical_facility_priority": "OSM_CANDIDATE_DEFAULT_MUST_BE_DOMAIN_REVIEWED",
            "population": "MODELLED_WORLDPOP_EXPOSURE_NOT_RESIDENT_REGISTRY",
            "validation": "ATBASAR_IS_PRIMARY_2024_SATELLITE_VALIDATION_AREA",
            "kopa_role": "DOWNSTREAM_RECEIVING_WATER_NOT_PRIMARY_CAUSE",
        },
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=ROOT / "data" / "realdata" / "kokshetau" / "generated")
    ap.add_argument("--skip-population", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg()
    out = args.output.resolve()
    shared.mkdirs(out)
    shared.write_json(out / "metadata" / "config_snapshot.json", cfg)
    shared.write_json(out / "logs" / "preflight.json", shared.preflight(out))
    copy_curated(out)

    statuses = {}
    shared.run_step("terrain", lambda: shared.fetch_dem(cfg, out), statuses, required=True)
    rename_terrain(out)
    shared.run_step("osm", lambda: shared.fetch_osm(cfg, out), statuses, required=True)
    if args.skip_population:
        statuses["population"] = {"status": "SKIPPED_BY_FLAG"}
    else:
        shared.run_step("population", lambda: shared.fetch_population(cfg, out), statuses, required=False)

    manifest(cfg, out, statuses)
    print(json.dumps(statuses, indent=2))
    print(f"ARGUS Kokshetau real-data pack: {out}")


if __name__ == "__main__":
    main()
