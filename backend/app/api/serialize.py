"""Serialization helpers for API responses (JSON-safe; never NaN / Infinity)."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from shapely.geometry import mapping


def clean(obj: Any) -> Any:
    """Recursively replace NaN/±Infinity with None and datetimes with ISO strings."""
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set):
        return [clean(v) for v in obj]
    if hasattr(obj, "item") and callable(obj.item):  # numpy scalar
        try:
            return clean(obj.item())
        except (TypeError, ValueError):
            return str(obj)
    return obj


def names(o: Any) -> dict:
    return {"kk": o.name_kk, "ru": o.name_ru, "en": o.name_en, "original": o.name_original}


def feature(geom: Any, props: dict) -> dict:
    return {"type": "Feature", "geometry": mapping(geom), "properties": clean(props)}


def fc(features: list[dict], **extra: Any) -> dict:
    return {"type": "FeatureCollection", "features": features, **extra}
