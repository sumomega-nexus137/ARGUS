"""Portable geometry column.

* PostgreSQL → PostGIS ``geometry(…, 4326)`` with a GiST spatial index (GeoAlchemy2).
* SQLite (demo / development) → WKT text.

Python-side values are always Shapely geometries in EPSG:4326 (lon/lat).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shapely import wkb, wkt
from shapely.geometry.base import BaseGeometry
from sqlalchemy import DateTime, Text
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Timezone-aware datetimes stored as UTC on every backend (SQLite drops tzinfo)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("UTCDateTime expects datetime")
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class GeometryType(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, geometry_type: str = "GEOMETRY", srid: int = 4326):
        super().__init__()
        self.geometry_type = geometry_type
        self.srid = srid

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from geoalchemy2 import Geometry

            return dialect.type_descriptor(Geometry(geometry_type=self.geometry_type, srid=self.srid))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, BaseGeometry):
            raise TypeError(f"GeometryType expects a shapely geometry, got {type(value)!r}")
        if dialect.name == "postgresql":
            from geoalchemy2.elements import WKTElement

            return WKTElement(value.wkt, srid=self.srid)
        return value.wkt

    def process_result_value(self, value: Any, dialect: Any) -> BaseGeometry | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            from geoalchemy2.shape import to_shape

            return to_shape(value)
        if isinstance(value, bytes | memoryview):
            return wkb.loads(bytes(value))
        return wkt.loads(value)
