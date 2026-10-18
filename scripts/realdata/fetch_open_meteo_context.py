#!/usr/bin/env python3
"""Fetch public global-model meteorological/hydrological context for an ARGUS pilot.

These series are contextual inputs only. They are never promoted to VERIFIED
FIELD or OFFICIAL HYDROPOST observations and never replace Kazhydromet/Tasqyn.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]


def get_json(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=90, headers={"User-Agent": "ARGUS-FloodOps/1.0"})
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data.get("reason") or str(data))
    return data


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def daily_to_csv(data: dict, path: Path, source: str, quality: str) -> None:
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    if not times:
        return
    rows = []
    for i, t in enumerate(times):
        row = {"date": t, "source": source, "quality": quality}
        for k, values in daily.items():
            if k == "time":
                continue
            row[k] = values[i] if isinstance(values, list) and i < len(values) else None
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", choices=["atbasar", "kokshetau"], required=True)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    cfg_path = ROOT / "data" / "realdata" / args.area / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    out = (args.output or ROOT / "data" / "realdata" / args.area / "generated").resolve()
    context = out / "context"
    context.mkdir(parents=True, exist_ok=True)

    lon, lat = cfg["center_wgs84"]
    ev = cfg["event"]
    start = ev["search_start"]
    end = ev["search_end"]

    status = {}

    # GloFAS v4 through Open-Meteo's public Flood API.
    try:
        flood = get_json(
            "https://flood-api.open-meteo.com/v1/flood",
            {
                "latitude": lat,
                "longitude": lon,
                "daily": "river_discharge",
                "start_date": start,
                "end_date": end,
                "cell_selection": "nearest",
            },
        )
        write_json(context / "glofas_event_discharge.json", {
            "source": "Open-Meteo Flood API / GloFAS v4",
            "quality": "GLOBAL_MODEL",
            "requested_coordinate": {"lat": lat, "lon": lon},
            "returned_coordinate": {"lat": flood.get("latitude"), "lon": flood.get("longitude")},
            "caveat": "Approx. 5 km model grid; the selected river cell may not exactly represent the local river. Never overrides local official observations.",
            "response": flood,
        })
        daily_to_csv(
            flood,
            context / "glofas_event_discharge.csv",
            "Open-Meteo / GloFAS v4",
            "GLOBAL_MODEL",
        )
        status["glofas_event"] = {"status": "OK", "rows": len((flood.get("daily") or {}).get("time") or [])}
    except Exception as exc:
        status["glofas_event"] = {"status": "FAILED_OPTIONAL", "error": repr(exc)}

    # Historical weather/reanalysis context for snowmelt and precipitation.
    try:
        weather = get_json(
            "https://archive-api.open-meteo.com/v1/archive",
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": start,
                "end_date": end,
                "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,rain_sum,snowfall_sum",
                "timezone": "Asia/Almaty",
            },
        )
        write_json(context / "historical_weather.json", {
            "source": "Open-Meteo Historical Weather API",
            "quality": "REANALYSIS_OR_HISTORICAL_MODEL",
            "requested_coordinate": {"lat": lat, "lon": lon},
            "returned_coordinate": {"lat": weather.get("latitude"), "lon": weather.get("longitude")},
            "caveat": "Model/reanalysis context for event interpretation, not an official local station record.",
            "response": weather,
        })
        daily_to_csv(
            weather,
            context / "historical_weather_daily.csv",
            "Open-Meteo Historical Weather API",
            "REANALYSIS_OR_HISTORICAL_MODEL",
        )
        status["historical_weather"] = {"status": "OK", "rows": len((weather.get("daily") or {}).get("time") or [])}
    except Exception as exc:
        status["historical_weather"] = {"status": "FAILED_OPTIONAL", "error": repr(exc)}

    write_json(context / "context_status.json", status)
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
