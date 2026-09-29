"""TerrainProvider: serves Terrarium-encoded DEM tiles (MapLibre raster-dem) from a local GeoTIFF / COG.

Demo areas use the synthetic DEM (STATIC · DEMO). A real DEM (e.g. Copernicus GLO-30 clipped to the
area) is used automatically when ``area.config.dem_path`` points to it. Tiles are cached in memory; for
national-scale deployment pre-render tiles or serve a COG through a tile server (docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import io
import math
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer

TILE = 256
_lock = threading.Lock()
_tiles: OrderedDict = OrderedDict()


@lru_cache(maxsize=8)
def _load_dem(path: str) -> tuple[np.ndarray, tuple, str]:
    import rasterio

    with rasterio.open(path) as src:
        arr = src.read(1, masked=True).filled(np.nan).astype(np.float32)
        return arr, tuple(src.transform)[:6], src.crs.to_string()


def _tile_lonlat(z: int, x: int, y: int) -> tuple[np.ndarray, np.ndarray]:
    n = 2.0 ** z
    px = (np.arange(TILE) + 0.5) / TILE
    xs = (x + px) / n * 360.0 - 180.0
    ys_merc = math.pi * (1 - 2 * (y + px) / n)
    lats = np.degrees(np.arctan(np.sinh(ys_merc)))
    return np.meshgrid(xs, lats)


def terrarium_encode(elev: np.ndarray) -> np.ndarray:
    v = np.clip(elev + 32768.0, 0, 65535.99)
    r = np.floor(v / 256.0)
    g = np.floor(v - r * 256.0)
    b = np.floor((v - np.floor(v)) * 256.0)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def dem_tile(dem_path: Path, z: int, x: int, y: int) -> bytes:
    key = (str(dem_path), z, x, y)
    with _lock:
        if key in _tiles:
            _tiles.move_to_end(key)
            return _tiles[key]
    arr, t, crs = _load_dem(str(dem_path))
    lon, lat = _tile_lonlat(z, x, y)
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    ex, ny = tr.transform(lon, lat)
    a, b, c, d, e, f = t
    cols = (ex - c) / a
    rows = (ny - f) / e
    h, w = arr.shape
    ci = np.clip(np.round(cols).astype(int), 0, w - 1)
    ri = np.clip(np.round(rows).astype(int), 0, h - 1)
    elev = arr[ri, ci]
    fill = float(np.nanmedian(arr))
    elev = np.where(np.isfinite(elev), elev, fill)
    img = Image.fromarray(terrarium_encode(elev), "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    with _lock:
        _tiles[key] = data
        while len(_tiles) > 2048:
            _tiles.popitem(last=False)
    return data
