"""Validation & after-action (Module 6).

Metrics are ALWAYS computed from supplied masks — never hard-coded:
    IoU (CSI) = TP / (TP + FP + FN);  precision = TP / (TP + FP);  recall = TP / (TP + FN);  F1.

Dataset layout (real data, supplied later)::

    data/imports/validation/<area_id>/<dataset_id>/
        metadata.json          {"name": ..., "event_date": ..., "observed_source": "Sentinel-1 ...", ...}
        observed.tif | observed.geojson     # observed flood mask (Sentinel-1 derived)
        modelled.tif | modelled.geojson     # ARGUS modelled flood (depth or mask)
        aoi.geojson (optional)              # evaluation area of interest

If files are missing the dataset reports ``NOT_LOADED``. A clearly labelled SYNTHETIC self-test is
available to verify the metric pipeline without implying real-world skill.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from app.core.config import get_settings
from app.providers.flood.base import GridInfo

REAL_DATASETS = {
    "atbasar": [{"id": "atbasar-2024", "name": {"kk": "Атбасар, 2024 жылғы су тасқыны", "ru": "Атбасар, паводок 2024 г.",
                                              "en": "Atbasar 2024 flood"},
                 "event": "2024-04", "observed_source": "Sentinel-1 SAR flood mask (to be supplied)"}],
    "kokshetau": [],
}
MODEL_DEPTH_THRESHOLD_M = 0.05


@dataclass
class MaskPair:
    observed: np.ndarray
    modelled: np.ndarray
    aoi: np.ndarray
    grid: GridInfo


def dataset_dir(area_id: str, dataset_id: str) -> Path:
    return get_settings().imports_dir / "validation" / area_id / dataset_id


def _find(d: Path, stem: str) -> Path | None:
    for ext in (".tif", ".tiff", ".geojson", ".json"):
        p = d / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def dataset_status(area_id: str) -> list[dict]:
    out = []
    for ds in REAL_DATASETS.get(area_id, []):
        d = dataset_dir(area_id, ds["id"])
        obs, mod = _find(d, "observed"), _find(d, "modelled")
        meta = {}
        if (d / "metadata.json").exists():
            try:
                meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
            except (ValueError, OSError):
                meta = {"error": "invalid metadata.json"}
        status = "READY" if obs and mod else ("PARTIAL" if obs or mod else "NOT_LOADED")
        out.append({**ds, "status": status, "observed_file": obs.name if obs else None,
                    "modelled_file": mod.name if mod else None, "path": str(d.relative_to(get_settings().data_dir)),
                    "metadata": meta, "kind": "REAL"})
    return out


def _read_mask(path: Path, ref: GridInfo | None, is_model: bool) -> tuple[np.ndarray, GridInfo]:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import rasterize
    from rasterio.warp import reproject

    if path.suffix.lower() in (".tif", ".tiff"):
        with rasterio.open(path) as src:
            arr = src.read(1, masked=True).filled(0).astype(np.float32)
            grid = GridInfo(src.crs.to_string(), src.transform, src.width, src.height)
            if ref is not None and (grid.transform != ref.transform or grid.width != ref.width or grid.crs != ref.crs):
                out = np.zeros((ref.height, ref.width), dtype=np.float32)
                reproject(arr, out, src_transform=src.transform, src_crs=src.crs, dst_transform=ref.transform,
                          dst_crs=ref.crs, resampling=Resampling.nearest)
                arr, grid = out, ref
        mask = arr >= MODEL_DEPTH_THRESHOLD_M if is_model else arr >= 0.5
        return mask, grid
    if ref is None:
        raise ValueError("A raster reference grid is required to rasterise vector masks")
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as shp_tr

    data = json.loads(path.read_text(encoding="utf-8"))
    feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
    tr = Transformer.from_crs("EPSG:4326", ref.crs, always_xy=True)
    geoms = [shp_tr(tr.transform, shape(f["geometry"])) for f in feats if f.get("geometry")]
    mask = rasterize([(g, 1) for g in geoms], out_shape=(ref.height, ref.width), transform=ref.transform, fill=0,
                     dtype="uint8").astype(bool) if geoms else np.zeros((ref.height, ref.width), dtype=bool)
    return mask, ref


def load_pair(area_id: str, dataset_id: str) -> MaskPair:
    d = dataset_dir(area_id, dataset_id)
    obs_p, mod_p = _find(d, "observed"), _find(d, "modelled")
    if not obs_p or not mod_p:
        raise FileNotFoundError("validation data not loaded")
    ref = None
    for p in (obs_p, mod_p):
        if p.suffix.lower() in (".tif", ".tiff"):
            import rasterio

            with rasterio.open(p) as src:
                ref = GridInfo(src.crs.to_string(), src.transform, src.width, src.height)
            break
    if ref is None:
        raise ValueError("at least one of observed / modelled must be a GeoTIFF to define the evaluation grid")
    obs, _ = _read_mask(obs_p, ref, is_model=False)
    mod, _ = _read_mask(mod_p, ref, is_model=True)
    aoi_p = d / "aoi.geojson"
    aoi = _read_mask(aoi_p, ref, is_model=False)[0] if aoi_p.exists() else np.ones_like(obs, dtype=bool)
    return MaskPair(obs, mod, aoi, ref)


def metrics(pair: MaskPair) -> dict:
    o, m, a = pair.observed & pair.aoi, pair.modelled & pair.aoi, pair.aoi
    tp = int((o & m).sum())
    fp = int((~o & m & a).sum())
    fn = int((o & ~m).sum())
    tn = int((~o & ~m & a).sum())
    cell_km2 = abs(pair.grid.transform.a * pair.grid.transform.e) / 1e6

    def ratio(n: int, d: int) -> float | None:
        return round(n / d, 4) if d > 0 else None

    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision and recall else None
    return {
        "tp_cells": tp, "fp_cells": fp, "fn_cells": fn, "tn_cells": tn,
        "true_overlap_km2": round(tp * cell_km2, 3), "false_positive_km2": round(fp * cell_km2, 3),
        "false_negative_km2": round(fn * cell_km2, 3),
        "observed_km2": round(int(o.sum()) * cell_km2, 3), "modelled_km2": round(int(m.sum()) * cell_km2, 3),
        "iou": ratio(tp, tp + fp + fn), "precision": precision, "recall": recall, "f1": f1,
        "cell_size_m": abs(pair.grid.transform.a), "evaluated_cells": int(a.sum()),
    }


def synthetic_pair(area_id: str, provider, member_model: str, member_obs: str, t_min: float, seed: int = 3) -> MaskPair:  # type: ignore[no-untyped-def]
    """SYNTHETIC self-test: 'observed' = another member perturbed by morphology + speckle. NOT real skill."""
    grid = provider.grid()
    mod = provider.depth_grid(member_model, t_min) >= MODEL_DEPTH_THRESHOLD_M
    obs = provider.depth_grid(member_obs, t_min) >= MODEL_DEPTH_THRESHOLD_M
    rng = np.random.default_rng(seed)
    obs = ndimage.binary_opening(obs, iterations=1)
    noise = ndimage.gaussian_filter(rng.standard_normal(obs.shape), 2.0)
    speckle = noise > 0.08
    edge = obs & ~ndimage.binary_erosion(obs, iterations=2)
    removed = speckle & edge
    added = (noise < -0.08) & ndimage.binary_dilation(obs, iterations=3) & ~obs
    obs = (obs & ~removed) | added
    return MaskPair(obs, mod, np.ones_like(obs, dtype=bool), grid)


def comparison_png(pair: MaskPair, layer: str) -> bytes:
    h, w = pair.observed.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    o, m = pair.observed & pair.aoi, pair.modelled & pair.aoi
    if layer == "observed":
        rgba[o] = (140, 110, 255, 190)
    elif layer == "modelled":
        rgba[m] = (40, 170, 255, 190)
    else:  # difference
        rgba[o & m] = (46, 144, 250, 200)   # true overlap
        rgba[~o & m] = (250, 160, 40, 210)  # false positive (model only)
        rgba[o & ~m] = (200, 70, 220, 210)  # false negative (observed only)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
