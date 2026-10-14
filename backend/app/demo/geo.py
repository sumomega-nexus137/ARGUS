"""Local-metre ↔ UTM ↔ lon/lat helpers used by the demo generator."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform


@dataclass(frozen=True)
class LocalFrame:
    """A local Cartesian frame (metres, x east / y north) anchored at a lon/lat centre."""

    center_lon: float
    center_lat: float
    epsg: int

    @cached_property
    def _to_utm(self) -> Transformer:
        return Transformer.from_crs("EPSG:4326", f"EPSG:{self.epsg}", always_xy=True)

    @cached_property
    def _to_ll(self) -> Transformer:
        return Transformer.from_crs(f"EPSG:{self.epsg}", "EPSG:4326", always_xy=True)

    @cached_property
    def origin(self) -> tuple[float, float]:
        e, n = self._to_utm.transform(self.center_lon, self.center_lat)
        return float(e), float(n)

    def local_to_utm(self, x: float, y: float) -> tuple[float, float]:
        e0, n0 = self.origin
        return e0 + x, n0 + y

    def local_to_ll(self, x: float, y: float) -> tuple[float, float]:
        e, n = self.local_to_utm(x, y)
        lon, lat = self._to_ll.transform(e, n)
        return round(float(lon), 7), round(float(lat), 7)

    def geom_local_to_ll(self, geom: BaseGeometry) -> BaseGeometry:
        e0, n0 = self.origin
        tr = self._to_ll

        def f(xs, ys, zs=None):  # type: ignore[no-untyped-def]
            import numpy as np

            lon, lat = tr.transform(np.asarray(xs) + e0, np.asarray(ys) + n0)
            return np.round(lon, 7), np.round(lat, 7)

        return shp_transform(f, geom)
