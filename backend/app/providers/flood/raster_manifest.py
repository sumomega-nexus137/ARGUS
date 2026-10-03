"""Provider for PRECOMPUTED flood surfaces delivered by the external modelling pipeline.

Manifest contract (``manifest.json``)::

    {
      "crs": "EPSG:32642",                      # optional; taken from the rasters otherwise
      "bankfull_cm": 500,                       # reference hydropost bankfull stage
      "hand_path": "hand.tif",                  # optional: enables negative relative levels
      "members": [
        {"id": "M1", "label": "P10", "gauge": [[-360, 548.0], [0, 590.0], ...],
         "frames": [{"offset_min": -360, "depth_path": "M1/f_-360.tif"}, ...]}
      ]
    }

Every raster must share the same grid (COG / GeoTIFF, depth in metres, nodata = dry).
Depth is linearly interpolated between frames. See docs/DATA_CONTRACTS.md.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio

from app.providers.flood.base import FloodScenarioProvider, GridInfo, MemberInfo


@lru_cache(maxsize=256)
def _read(path: str) -> tuple[np.ndarray, GridInfo]:
    with rasterio.open(path) as src:
        arr = src.read(1, masked=True).filled(np.nan).astype(np.float32)
        return arr, GridInfo(src.crs.to_string(), src.transform, src.width, src.height)


class RasterManifestProvider(FloodScenarioProvider):
    kind = "raster_manifest"
    mode_note = "Precomputed flood depth rasters supplied by the modelling pipeline"

    def __init__(self, manifest_path: Path):
        self.root = manifest_path.parent
        with open(manifest_path, encoding="utf-8") as f:
            self.manifest = json.load(f)
        self._members = {m["id"]: m for m in self.manifest["members"]}
        for m in self._members.values():
            m["frames"] = sorted(m["frames"], key=lambda fr: fr["offset_min"])
        self._bankfull = float(self.manifest.get("bankfull_cm", 0))
        first = next(iter(self._members.values()))["frames"][0]
        _, self._grid = _read(str(self.root / first["depth_path"]))
        self._hand = None
        if self.manifest.get("hand_path"):
            self._hand, _ = _read(str(self.root / self.manifest["hand_path"]))

    def grid(self) -> GridInfo:
        return self._grid

    def members(self) -> list[MemberInfo]:
        out = []
        for m in self._members.values():
            g = m.get("gauge") or []
            peak = max(g, key=lambda p: p[1]) if g else None
            out.append(MemberInfo(m["id"], m.get("label", m["id"]), peak[1] if peak else None,
                                  peak[0] / 60 if peak else None))
        return out

    def time_range(self) -> tuple[float, float]:
        fr = next(iter(self._members.values()))["frames"]
        return float(fr[0]["offset_min"]), float(fr[-1]["offset_min"])

    def _bracket(self, member: str, t: float) -> tuple[dict, dict, float]:
        frames = self._members[member]["frames"]
        if t <= frames[0]["offset_min"]:
            return frames[0], frames[0], 0.0
        for a, b in zip(frames[:-1], frames[1:], strict=True):
            if a["offset_min"] <= t <= b["offset_min"]:
                span = b["offset_min"] - a["offset_min"]
                return a, b, (t - a["offset_min"]) / span if span else 0.0
        return frames[-1], frames[-1], 0.0

    def _depth(self, member: str, t: float) -> np.ndarray:
        a, b, w = self._bracket(member, t)
        da, _ = _read(str(self.root / a["depth_path"]))
        if a is b:
            return da
        db, _ = _read(str(self.root / b["depth_path"]))
        return np.where(np.isnan(da) & np.isnan(db), np.nan, np.nan_to_num(da) * (1 - w) + np.nan_to_num(db) * w)

    def relative_level_grid(self, member: str, t_min: float) -> np.ndarray:
        d = self._depth(member, t_min)
        lvl = np.where(d > 0, d, np.nan)
        if self._hand is not None:
            h = float(self.river_level(member, np.array([t_min]))[0])
            below = h - self._hand
            lvl = np.where(np.isnan(lvl) & (below > -1.5) & (below <= 0), below, lvl)
        return lvl.astype(np.float32)

    def relative_level_points(self, member: str, xs: np.ndarray, ys: np.ndarray, t_mins: np.ndarray) -> np.ndarray:
        """Point queries sample only the requested cells of each native frame, then interpolate in time — identical
        to sampling ``relative_level_grid`` but O(points × frames) instead of O(grid × times)."""
        rows, cols, inside = self._grid.rowcol(xs, ys)
        frames = self._members[member]["frames"]
        fts = np.array([float(f["offset_min"]) for f in frames])
        D = np.stack([_read(str(self.root / f["depth_path"]))[0][rows, cols] for f in frames], axis=1)
        hand = self._hand[rows, cols] if self._hand is not None else None
        ts = np.asarray(t_mins, dtype=float)
        out = np.full((len(rows), len(ts)), np.nan, dtype=np.float32)
        rl = self.river_level(member, ts) if hand is not None else None
        for j, t in enumerate(ts):
            if t <= fts[0]:
                ia = ib = 0
                w = 0.0
            elif t >= fts[-1]:
                ia = ib = len(fts) - 1
                w = 0.0
            else:
                ib = int(np.searchsorted(fts, t, side="left"))
                ia = ib - 1 if fts[ib] != t else ib
                span = fts[ib] - fts[ia]
                w = float((t - fts[ia]) / span) if span else 0.0
            da, db = D[:, ia], D[:, ib]
            if ia == ib:
                d = da
            else:
                d = np.where(np.isnan(da) & np.isnan(db), np.nan,
                             np.where(np.isnan(da), 0.0, da) * (1 - w) + np.where(np.isnan(db), 0.0, db) * w)
            lvl = np.where(d > 0, d, np.nan)
            if hand is not None:
                below = float(rl[j]) - hand
                lvl = np.where(np.isnan(lvl) & (below > -1.5) & (below <= 0), below, lvl)
            out[:, j] = lvl
        out[~inside, :] = np.nan
        return out

    def river_level(self, member: str, t_mins: np.ndarray) -> np.ndarray:
        g = np.asarray(self._members[member].get("gauge") or [[0, self._bankfull]], dtype=float)
        return (np.interp(np.asarray(t_mins, dtype=float), g[:, 0], g[:, 1]) - self._bankfull) / 100.0

    def gauge_series(self, member: str) -> list[tuple[float, float]]:
        return [(float(t), float(s)) for t, s in (self._members[member].get("gauge") or [])]
