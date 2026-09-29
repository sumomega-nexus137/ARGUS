"""External data provider adapters and registry.

EXTERNAL PROVIDERS → PROVIDER ADAPTERS → NORMALIZATION → ARGUS DATA LAYER → API → FRONTEND

The frontend never talks to external providers. Each adapter implements ``fetch()`` returning normalized
records; failures never propagate — they mark the provider OFFLINE / DEGRADED and ARGUS keeps working
on cached / local data (degraded mode). Private APIs are NOT assumed: adapters without an endpoint /
credentials report NOT_CONFIGURED.
"""

from __future__ import annotations

import json
import os
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class ProviderNotConfigured(Exception):
    pass


@dataclass
class ProviderResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = ""
    mode: str = "LIVE"
    quality: str | None = None


class DataProvider(ABC):
    key: str = "abstract"
    layer: str = "abstract"
    source: str = ""
    mode: str = "LIVE"
    default_schedule_min: int = 60
    env_endpoint: str | None = None

    def endpoint(self) -> str | None:
        return os.environ.get(self.env_endpoint) if self.env_endpoint else None

    def configured(self) -> bool:
        return bool(self.endpoint())

    @abstractmethod
    def fetch(self, area: dict) -> ProviderResult: ...

    def _get_json(self, url: str, timeout: float = 15.0) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": "ARGUS-FloodOps/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (configured endpoints only)
            return json.loads(resp.read().decode("utf-8"))


class KazhydrometHydrologyProvider(DataProvider):
    """Official hydropost feed. Contract: GET {endpoint}?station=<id> → [{"time": ISO, "level_cm": n, "q": n?}]."""

    key, layer, source, default_schedule_min = "kazhydromet", "hydrology", "Kazhydromet", 15
    env_endpoint = "ARGUS_KAZHYDROMET_URL"

    def fetch(self, area: dict) -> ProviderResult:
        if not self.configured():
            raise ProviderNotConfigured(self.key)
        out = []
        for st in area.get("stations", []):
            data = self._get_json(f"{self.endpoint()}?station={st['id']}")
            for row in data:
                out.append({"station_id": st["id"], "observed_at": row["time"], "water_level_cm": float(row["level_cm"]),
                            "discharge_m3s": row.get("q"), "source": "Kazhydromet hydropost", "source_type": "HYDROPOST",
                            "verification": "VERIFIED"})
        return ProviderResult(out, source="Kazhydromet", mode="LIVE", quality="OFFICIAL")


class GloFASForecastProvider(DataProvider):
    """Copernicus GloFAS discharge forecast (via a configured CDS/EWDS proxy). Used as forecast input, not observation."""

    key, layer, source, default_schedule_min = "glofas", "glofas", "Copernicus GloFAS", 1440
    env_endpoint = "ARGUS_GLOFAS_URL"

    def fetch(self, area: dict) -> ProviderResult:
        if not self.configured():
            raise ProviderNotConfigured(self.key)
        data = self._get_json(f"{self.endpoint()}?lat={area['center'][1]}&lon={area['center'][0]}")
        return ProviderResult([{"kind": "discharge_forecast", "series": data}], source="GloFAS", mode="LIVE",
                              quality="GLOBAL_MODEL")


class Sentinel1CatalogueProvider(DataProvider):
    """Copernicus Data Space Sentinel-1 catalogue search (acquisitions intersecting the area)."""

    key, layer, source, default_schedule_min = "copernicus_s1", "sentinel1", "Copernicus Sentinel-1", 720
    env_endpoint = "ARGUS_S1_CATALOGUE_URL"

    def fetch(self, area: dict) -> ProviderResult:
        if not self.configured():
            raise ProviderNotConfigured(self.key)
        b = area["bbox"]
        data = self._get_json(f"{self.endpoint()}?bbox={b[0]},{b[1]},{b[2]},{b[3]}")
        return ProviderResult([{"kind": "s1_acquisition", **d} for d in data.get("features", [])], source="Sentinel-1",
                              mode="HISTORICAL", quality="SATELLITE")


class ImergRainfallProvider(DataProvider):
    key, layer, source, default_schedule_min = "nasa_imerg", "rainfall", "NASA IMERG", 60
    env_endpoint = "ARGUS_IMERG_URL"

    def fetch(self, area: dict) -> ProviderResult:
        if not self.configured():
            raise ProviderNotConfigured(self.key)
        data = self._get_json(f"{self.endpoint()}?lat={area['center'][1]}&lon={area['center'][0]}")
        return ProviderResult([{"kind": "rainfall", "series": data}], source="IMERG", mode="LIVE", quality="SATELLITE")


class WeatherProvider(DataProvider):
    """Generic weather endpoint (e.g. a national met-service or Open-Meteo compatible URL)."""

    key, layer, source, default_schedule_min = "weather_api", "weather", "Weather service", 30
    env_endpoint = "ARGUS_WEATHER_URL"

    def fetch(self, area: dict) -> ProviderResult:
        if not self.configured():
            raise ProviderNotConfigured(self.key)
        data = self._get_json(f"{self.endpoint()}?latitude={area['center'][1]}&longitude={area['center'][0]}")
        return ProviderResult([{"kind": "weather", "data": data}], source="Weather", mode="LIVE")


class OsmRoadsProvider(DataProvider):
    """OpenStreetMap extract loader (offline import pipeline; see scripts/import_osm_roads.py)."""

    key, layer, source, default_schedule_min = "openstreetmap", "osm", "OpenStreetMap", 10080
    env_endpoint = "ARGUS_OSM_EXTRACT"

    def fetch(self, area: dict) -> ProviderResult:
        if not self.configured():
            raise ProviderNotConfigured(self.key)
        return ProviderResult([], source="OpenStreetMap", mode="CACHED")


REGISTRY: dict[str, DataProvider] = {p.key: p for p in [
    KazhydrometHydrologyProvider(), GloFASForecastProvider(), Sentinel1CatalogueProvider(), ImergRainfallProvider(),
    WeatherProvider(), OsmRoadsProvider(),
]}
