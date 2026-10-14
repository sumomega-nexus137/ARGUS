"""Synthetic terrain for DEMO areas (SIMULATION — not surveyed data).

Produces, on a regular UTM grid:

* ``hand``  – height above the bankfull water surface of the nearest river cell (m)
* ``dem``   – absolute elevation (m) = bankfull water surface + hand
* ``channel`` – river channel mask
* ``onset`` – the bankfull-relative water level at which a cell becomes hydraulically
  connected to the channel (4-connected priority flood). A cell is inundated at level h
  when ``h > onset``; depth = ``h - hand``. This is a *static stage–HAND inundation
  approximation* used only to create demonstration surfaces. It is NOT a hydrodynamic model.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass
class Grid:
    x0: float  # local x of the west edge
    y1: float  # local y of the north edge
    res: float
    nx: int
    ny: int

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        xs = self.x0 + (np.arange(self.nx) + 0.5) * self.res
        ys = self.y1 - (np.arange(self.ny) + 0.5) * self.res
        return np.meshgrid(xs, ys)


@dataclass
class Bowl:
    """Gaussian anomaly (negative = basin / depression)."""

    x: float
    y: float
    rx: float
    ry: float
    amp: float

    def eval(self, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
        return self.amp * np.exp(-(((X - self.x) / self.rx) ** 2 + ((Y - self.y) / self.ry) ** 2))


def smooth_noise(shape: tuple[int, int], sigma_cells: float, amp: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = ndimage.gaussian_filter(rng.standard_normal(shape), sigma_cells)
    n /= max(float(np.abs(n).max()), 1e-9)
    return (n * amp).astype(np.float32)


def river_distance(
    grid: Grid, river_y: Callable[[np.ndarray], np.ndarray], half_width: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Distance (m) from each cell to the river centreline, side sign and channel mask."""
    X, Y = grid.centers()
    # rasterise a densely sampled centreline
    xs = np.linspace(grid.x0, grid.x0 + grid.nx * grid.res, grid.nx * 8)
    ys = river_y(xs)
    line = np.zeros((grid.ny, grid.nx), dtype=bool)
    cols = ((xs - grid.x0) / grid.res).astype(int)
    rows = ((grid.y1 - ys) / grid.res).astype(int)
    ok = (cols >= 0) & (cols < grid.nx) & (rows >= 0) & (rows < grid.ny)
    line[rows[ok], cols[ok]] = True
    dist = ndimage.distance_transform_edt(~line) * grid.res
    side = np.sign(Y - river_y(X))
    channel = dist <= half_width
    return dist.astype(np.float32), side.astype(np.float32), channel


def priority_flood_onset(hand: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """Minimum water level at which each cell becomes connected to ``seeds`` (4-connectivity)."""
    ny, nx = hand.shape
    onset = np.full(hand.shape, np.inf, dtype=np.float64)
    h = hand.astype(np.float64)
    heap: list[tuple[float, int]] = []
    seed_idx = np.flatnonzero(seeds)
    for idx in seed_idx:
        onset.flat[idx] = h.flat[idx]
        heap.append((h.flat[idx], int(idx)))
    heapq.heapify(heap)
    done = np.zeros(hand.size, dtype=bool)
    while heap:
        level, idx = heapq.heappop(heap)
        if done[idx]:
            continue
        done[idx] = True
        r, c = divmod(idx, nx)
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= rr < ny and 0 <= cc < nx:
                j = rr * nx + cc
                if done[j]:
                    continue
                cand = max(level, h.flat[j])
                if cand < onset.flat[j]:
                    onset.flat[j] = cand
                    heapq.heappush(heap, (cand, j))
    return onset.astype(np.float32)
