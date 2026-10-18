"""Open-Meteo public context providers (GloFAS v4 river discharge, weather forecast).

Authority: GLOBAL_MODEL — lower than verified field, official local hydropost, official forecast and satellite
observations. These feeds are context / forcing only and never override local observations (they are not written
as observations at all). Profiles: ``data/realdata/api_profiles.json``.

Degraded-mode contract (never fake LIVE):
* fetched now (or within the cache TTL)            → LIVE, with source timestamp and DATA AGE
* fetch failed, cached copy ≤ stale threshold       → CACHED (age shown)
* fetch failed, cached copy older than threshold    → STALE
* fetch failed, no cache                            → OFFLINE
* disabled by configuration                         → NOT_CONFIGURED
Data age is measured against the wall clock (these are current conditions, not the historical replay clock).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("argus.open_meteo")
_lock = threading.Lock()

PROFILES = {
    "glofas": {
        "endpoint": "https://flood-api.open-meteo.com/v1/flood",
        "params": {"daily": "river_discharge,river_discharge_mean,river_discharge_median,river_discharge_max,"
                            "river_discharge_min,river_discharge_p25,river_discharge_p75",
                   "forecast_days": "30", "past_days": "7", "cell_selection": "nearest"},
        "source": "Open-Meteo Flood API (GloFAS v4)", "quality": "GLOBAL_MODEL",
        "caveats": ["GloFAS/Open-Meteo resolution is about 5 km; the selected river cell may not correspond exactly to the local river.",
                    "Forecast/context only — not an official local gauge observation; local verified observations override it."],
    },
    "weather": {
        "endpoint": "https://api.open-meteo.com/v1/forecast",
        "params": {"daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum,snowfall_sum",
                   "hourly": "snow_depth,soil_moisture_0_to_7cm", "forecast_days": "7", "past_days": "3",
                   "timezone": "Asia/Almaty"},
        "source": "Open-Meteo Forecast API", "quality": "GLOBAL_MODEL",
        "caveats": ["Weather-model data are contextual forcing, not local hydropost measurements.",
                    "Snow depth and soil moisture are model-grid estimates."],
    },
}


class FetchFailed(RuntimeError):
    pass


def cache_dir() -> Path:
    d = get_settings().data_dir / "runtime" / "cache" / "open_meteo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(area_id: str, kind: str) -> Path:
    return cache_dir() / f"{area_id}_{kind}.json"


def _read_cache(area_id: str, kind: str) -> dict | None:
    p = _cache_path(area_id, kind)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _http_get_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "ARGUS-FloodOps/0.2 (decision support)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed public HTTPS endpoints)
        return json.loads(resp.read().decode("utf-8"))


def _fetch(kind: str, lat: float, lon: float) -> tuple[str, Any]:
    s = get_settings()
    prof = PROFILES[kind]
    url = f"{prof['endpoint']}?{urllib.parse.urlencode({'latitude': lat, 'longitude': lon, **prof['params']})}"
    last: Exception | None = None
    for attempt in range(max(1, s.open_meteo_retries + 1)):
        try:
            return url, _http_get_json(url, s.open_meteo_timeout_s)
        except Exception as exc:  # network / HTTP / JSON errors → retry then report
            last = exc
            if attempt < s.open_meteo_retries:
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
    raise FetchFailed(f"{type(last).__name__}: {last}")


def _normalise(kind: str, raw: dict) -> dict:
    if kind == "glofas":
        d = raw.get("daily") or {}
        keys = [k for k in d if k != "time"]
        rows = [{"date": t, **{k: d[k][i] for k in keys}} for i, t in enumerate(d.get("time") or [])]
        return {"kind": "discharge_forecast", "unit": "m3/s", "rows": rows}
    d = raw.get("daily") or {}
    keys = [k for k in d if k != "time"]
    rows = [{"date": t, **{k: d[k][i] for k in keys}} for i, t in enumerate(d.get("time") or [])]
    hourly = raw.get("hourly") or {}
    snow = [v for v in (hourly.get("snow_depth") or []) if v is not None]
    soil = [v for v in (hourly.get("soil_moisture_0_to_7cm") or []) if v is not None]
    return {"kind": "weather", "rows": rows, "snow_depth_m_latest": snow[-1] if snow else None,
            "soil_moisture_latest": soil[-1] if soil else None}


def live_context(area_id: str, lat: float, lon: float, kind: str, refresh: bool = False, offline: bool = False) -> dict:
    """Return the live context for one feed with an honest mode label. Never raises."""
    s = get_settings()
    prof = PROFILES[kind]
    base = {"kind": kind, "source": prof["source"], "quality": prof["quality"], "authority": "GLOBAL_MODEL",
            "caveats": prof["caveats"], "requested_coordinate": {"lat": lat, "lon": lon}}
    if not s.open_meteo_enabled:
        return {**base, "mode": "NOT_CONFIGURED", "status": "NOT_CONFIGURED", "data": None, "fetched_at": None, "age_min": None,
                "message": "Open-Meteo providers disabled (ARGUS_OPEN_METEO_ENABLED=false)"}
    now = datetime.now(UTC)
    with _lock:
        cached = _read_cache(area_id, kind)
    cached_at = datetime.fromisoformat(cached["fetched_at"]) if cached else None
    cached_age = (now - cached_at).total_seconds() / 60 if cached_at else None
    if cached and not refresh and not offline and cached_age is not None and cached_age <= s.open_meteo_cache_ttl_min:
        return {**base, "mode": "LIVE", "status": "OK", "data": cached["data"], "fetched_at": cached["fetched_at"],
                "age_min": round(cached_age, 1), "returned_coordinate": cached.get("returned_coordinate"),
                "message": f"Served from cache (TTL {s.open_meteo_cache_ttl_min} min)"}
    error = "outage simulation / offline mode" if offline else None
    if not offline:
        try:
            url, raw = _fetch(kind, lat, lon)
            entry = {"fetched_at": now.isoformat(), "url": url, "data": _normalise(kind, raw),
                     "returned_coordinate": {"lat": raw.get("latitude"), "lon": raw.get("longitude")}}
            with _lock:
                _cache_path(area_id, kind).write_text(json.dumps(entry), encoding="utf-8")
            return {**base, "mode": "LIVE", "status": "OK", "data": entry["data"], "fetched_at": entry["fetched_at"],
                    "age_min": 0.0, "returned_coordinate": entry["returned_coordinate"], "message": None}
        except FetchFailed as exc:
            error = str(exc)
            log.warning("open-meteo %s fetch failed for %s: %s", kind, area_id, exc)
    if cached:
        stale = cached_age is not None and cached_age > s.open_meteo_stale_after_min
        return {**base, "mode": "STALE" if stale else "CACHED", "status": "DEGRADED", "data": cached["data"],
                "fetched_at": cached["fetched_at"], "age_min": round(cached_age or 0.0, 1),
                "returned_coordinate": cached.get("returned_coordinate"), "message": f"Last fetch failed — {error}"}
    return {**base, "mode": "OFFLINE", "status": "OFFLINE", "data": None, "fetched_at": None, "age_min": None,
            "message": f"No cached data — {error}"}
