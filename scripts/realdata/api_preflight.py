#!/usr/bin/env python3
"""Probe ARGUS upstream public data/API dependencies without inventing live feeds."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]

PUBLIC = {
    "earth_search_sentinel2": "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a",
    "earth_search_landsat": "https://earth-search.aws.element84.com/v1/collections/landsat-c2-l2",
    "planetary_computer_jrc": "https://planetarycomputer.microsoft.com/api/stac/v1/collections/jrc-gsw",
    "planetary_computer_sentinel1_rtc": "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc",
    "openstreetmap_overpass": "https://overpass-api.de/api/status",
    "copernicus_dem": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N51_00_E068_00_DEM/Copernicus_DSM_COG_10_N51_00_E068_00_DEM.tif",
    "worldpop_2024": "https://worldpop-public-data.soton.ac.uk/GIS/Population/Global_2015_2030/R2025A/2024/KAZ/v1/100m/constrained/kaz_pop_2024_CN_100m_R2025A_v1.tif",
}

CONFIGURED_LATER = {
    "kazhydromet": {
        "state": "AUTHORIZED_ENDPOINT_REQUIRED",
        "reason": "ARGUS does not assume an undocumented stable public hydropost REST API.",
        "fallback": "official bulletin/report + manual/CSV/XLSX import with provenance",
        "env": "ARGUS_KAZHYDROMET_URL",
    },
    "tasqyn": {
        "state": "AUTHORIZED_ENDPOINT_REQUIRED",
        "reason": "No public ARGUS-compatible Tasqyn endpoint is assumed.",
        "fallback": "official forecast/manual import; future agency integration",
        "env": None,
    },
    "glofas": {
        "state": "CREDENTIAL_OR_PROXY_CONFIGURATION_REQUIRED",
        "reason": "Operational GloFAS access depends on the selected Copernicus CDS/EWDS delivery route.",
        "fallback": "cached forecast or omit with explicit degraded status",
        "env": "ARGUS_GLOFAS_URL",
    },
    "nasa_imerg": {
        "state": "ENDPOINT_OR_EARTHDATA_CONFIGURATION_REQUIRED",
        "reason": "IMERG delivery depends on selected NASA endpoint/product and may require Earthdata authentication.",
        "fallback": "cached precipitation context or omit with explicit degraded status",
        "env": "ARGUS_IMERG_URL",
    },
}


def probe(url: str) -> dict:
    headers = {"User-Agent": "ARGUS-FloodOps/1.0"}
    try:
        # Stream and consume only a small prefix so large rasters are not downloaded.
        with requests.get(url, stream=True, timeout=45, headers=headers) as r:
            prefix = next(r.iter_content(1024), b"")
            return {
                "ok": 200 <= r.status_code < 400,
                "status": r.status_code,
                "content_type": r.headers.get("content-type"),
                "content_length": r.headers.get("content-length"),
                "received_probe_bytes": len(prefix),
                "url": url,
            }
    except Exception as exc:
        return {"ok": False, "error": repr(exc), "url": url}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=ROOT / "data" / "realdata" / "api_readiness.json")
    args = ap.parse_args()

    public = {key: probe(url) for key, url in PUBLIC.items()}
    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "public_sources": public,
        "configured_or_authorized_sources": CONFIGURED_LATER,
        "rules": [
            "A reachable catalogue does not imply a scene exists for a specific event/AOI.",
            "Unavailable/closed providers remain NOT_CONFIGURED; no simulated value may be labelled LIVE.",
            "Historical competition datasets are cached/precomputed and are not downloaded on normal app startup.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not all(x.get("ok") for x in public.values()):
        raise SystemExit("One or more required public source probes failed.")


if __name__ == "__main__":
    main()
