"""FloodScenarioProvider — the contract between ARGUS and flood modelling pipelines.

ARGUS does NOT run hydrodynamics. It consumes *precomputed* flood surfaces (depth / relative
water level) produced by an external data/model pipeline, per ensemble member and time step.

Time is expressed in minutes relative to the scenario reference time (NOW for live scenarios).

``relative level`` = water surface − ground (metres). Positive values are flood depth.
Negative values (water below the ground surface but hydraulically connected) are optional —
providers that only know depth return ``NaN`` for dry cells.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from affine import Affine
from pyproj import Transformer


@dataclass(frozen=True)
class GridInfo:
    crs: str
    transform: Affine
    width: int
    height: int

    @property
    def res(self) -> float:
        return float(self.transform.a)

    def corners_lonlat(self) -> list[list[float]]:
        """[top-left, top-right, bottom-right, bottom-left] in lon/lat (MapLibre image source order)."""
        tr = Transformer.from_crs(self.crs, "EPSG:4326", always_xy=True)
        t = self.transform
        corners = [(0, 0), (self.width, 0), (self.width, self.height), (0, self.height)]
        pts = [(t.a * c + t.b * r + t.c, t.d * c + t.e * r + t.f) for c, r in corners]
        return [[round(float(c), 7) for c in tr.transform(x, y)] for x, y in pts]

    def rowcol(self, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        inv = ~self.transform
        x = np.asarray(xs, dtype=float)
        y = np.asarray(ys, dtype=float)
        cols = inv.a * x + inv.b * y + inv.c
        rows = inv.d * x + inv.e * y + inv.f
        cols = np.floor(cols).astype(int)
        rows = np.floor(rows).astype(int)
        inside = (cols >= 0) & (cols < self.width) & (rows >= 0) & (rows < self.height)
        return np.clip(rows, 0, self.height - 1), np.clip(cols, 0, self.width - 1), inside


@dataclass
class MemberInfo:
    id: str
    label: str
    peak_stage_cm: float | None
    peak_offset_h: float | None


class FloodScenarioProvider(ABC):
    kind: str = "abstract"
    mode_note: str = ""

    @abstractmethod
    def grid(self) -> GridInfo: ...

    @abstractmethod
    def members(self) -> list[MemberInfo]: ...

    @abstractmethod
    def time_range(self) -> tuple[float, float]:
        """Available [start, end] minutes relative to reference time."""

    @abstractmethod
    def relative_level_grid(self, member: str, t_min: float) -> np.ndarray:
        """Relative water level (m) on the provider grid; NaN where dry / unknown."""

    @abstractmethod
    def relative_level_points(self, member: str, xs: np.ndarray, ys: np.ndarray, t_mins: np.ndarray) -> np.ndarray:
        """Relative water level (m) at projected points (provider CRS) → array [n_points, n_times]."""

    @abstractmethod
    def river_level(self, member: str, t_mins: np.ndarray) -> np.ndarray:
        """Water level above bankfull (m) used for bridge clearance checks → array [n_times]."""

    @abstractmethod
    def gauge_series(self, member: str) -> list[tuple[float, float]]:
        """Simulated / forecast gauge stage (cm) at the reference hydropost: [(t_min, stage_cm)]."""

    def depth_grid(self, member: str, t_min: float) -> np.ndarray:
        lvl = self.relative_level_grid(member, t_min)
        return np.where(np.isfinite(lvl) & (lvl > 0), lvl, 0.0).astype(np.float32)
