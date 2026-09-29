"""SIMULATION provider: static stage–HAND inundation approximation over a synthetic DEMO terrain.

For each ensemble member a gauge stage series defines the water level above bankfull ``h(t)``.
A cell is wet when ``h(t)`` exceeds its connection ("onset") level; its relative water level is
``h(t) − HAND``. Optional snowmelt ponding adds ``capacity × snowmelt_index(t)`` in urban
depressions. This is a transparent demonstration surrogate, NOT a hydrodynamic model, and is
labelled SIMULATION everywhere it is displayed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio

from app.providers.flood.base import FloodScenarioProvider, GridInfo, MemberInfo


@lru_cache(maxsize=16)
def _load_terrain(terrain_dir: str) -> dict:
    d = Path(terrain_dir)
    out: dict = {}
    for name in ("hand", "onset", "ponding_cap"):
        p = d / f"{name}.tif"
        if p.exists():
            with rasterio.open(p) as src:
                out[name] = src.read(1).astype(np.float32)
                out["grid"] = GridInfo(src.crs.to_string(), src.transform, src.width, src.height)
    if "hand" not in out:
        raise FileNotFoundError(f"synthetic terrain not found in {terrain_dir}")
    return out


class SyntheticStageHandProvider(FloodScenarioProvider):
    kind = "synthetic_stage_hand"
    mode_note = "SIMULATION — static stage–HAND approximation on synthetic DEMO terrain"

    def __init__(self, terrain_dir: Path, members: list[dict], bankfull_cm: float):
        self._t = _load_terrain(str(terrain_dir))
        self._members = {m["id"]: m for m in members}
        self._bankfull = float(bankfull_cm)
        self._series: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._snow: dict[str, tuple[np.ndarray, np.ndarray] | None] = {}
        for m in members:
            arr = np.asarray(m["stage_series"], dtype=float)
            self._series[m["id"]] = (arr[:, 0], arr[:, 1])
            if m.get("snow_series"):
                s = np.asarray(m["snow_series"], dtype=float)
                self._snow[m["id"]] = (s[:, 0], s[:, 1])
            else:
                self._snow[m["id"]] = None

    # ------------------------------------------------------------------ metadata
    def grid(self) -> GridInfo:
        return self._t["grid"]

    def members(self) -> list[MemberInfo]:
        return [MemberInfo(m["id"], m.get("label", m["id"]), m.get("peak_stage_cm"), m.get("peak_offset_h"))
                for m in self._members.values()]

    def time_range(self) -> tuple[float, float]:
        t = next(iter(self._series.values()))[0]
        return float(t[0]), float(t[-1])

    # ------------------------------------------------------------------ hydraulics surrogate
    def _h(self, member: str, t_mins: np.ndarray) -> np.ndarray:
        ts, ss = self._series[member]
        return (np.interp(t_mins, ts, ss) - self._bankfull) / 100.0

    def _snow_index(self, member: str, t_mins: np.ndarray) -> np.ndarray:
        s = self._snow.get(member)
        if s is None:
            return np.zeros_like(np.asarray(t_mins, dtype=float))
        return np.interp(t_mins, s[0], s[1])

    def relative_level_grid(self, member: str, t_min: float) -> np.ndarray:
        h = float(self._h(member, np.array([t_min]))[0])
        hand, onset = self._t["hand"], self._t["onset"]
        lvl = np.where(h > onset, h - hand, np.nan).astype(np.float32)
        cap = self._t.get("ponding_cap")
        if cap is not None:
            pond = cap * float(self._snow_index(member, np.array([t_min]))[0])
            pond = np.where(pond > 0.02, pond, np.nan)
            lvl = np.fmax(lvl, pond).astype(np.float32)
        return lvl

    def relative_level_points(self, member: str, xs: np.ndarray, ys: np.ndarray, t_mins: np.ndarray) -> np.ndarray:
        g = self.grid()
        rows, cols, inside = g.rowcol(xs, ys)
        hand = self._t["hand"][rows, cols][:, None]
        onset = self._t["onset"][rows, cols][:, None]
        h = self._h(member, np.asarray(t_mins, dtype=float))[None, :]
        lvl = np.where(h > onset, h - hand, np.nan)
        cap = self._t.get("ponding_cap")
        if cap is not None:
            c = cap[rows, cols][:, None]
            pond = c * self._snow_index(member, np.asarray(t_mins, dtype=float))[None, :]
            pond = np.where(pond > 0.02, pond, np.nan)
            lvl = np.fmax(lvl, pond)
        lvl[~inside, :] = np.nan
        return lvl

    def river_level(self, member: str, t_mins: np.ndarray) -> np.ndarray:
        return self._h(member, np.asarray(t_mins, dtype=float))

    def gauge_series(self, member: str) -> list[tuple[float, float]]:
        ts, ss = self._series[member]
        return [(float(t), float(s)) for t, s in zip(ts, ss, strict=True)]
