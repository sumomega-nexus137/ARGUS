"""Portable geometry column.

* PostgreSQL → PostGIS ``geometry(…, 4326)`` (GeoAlchemy2). GeoAlchemy2 is imported at module
  load time so its DDL event hooks are registered before Alembic starts creating tables.
* SQLite (demo / development) → WKT text.

Python-side values are always Shapely geometries in EPSG:4326 (lon/lat).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shapely import wkb, wkt
from shapely.geometry.base import BaseGeometry
from sqlalchemy import DateTime
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import TypeDecorator, UserDefinedType


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


class GeometryType(UserDefinedType):
    """Portable Shapely geometry storage without GeoAlchemy DDL hooks.

    PostgreSQL/PostGIS compiles this type directly to geometry(TYPE, SRID).
    SQLite compiles it to TEXT/WKT. The application does not depend on
    server-side spatial operators, so this avoids GeoAlchemy table hooks.
    """

    cache_ok = True

    def __init__(self, geometry_type: str = "GEOMETRY", srid: int = 4326):
        self.geometry_type = geometry_type.upper()
        self.srid = int(srid)

    def bind_processor(self, dialect: Any):
        def process(value: Any) -> Any:
            if value is None:
                return None
            if not isinstance(value, BaseGeometry):
                raise TypeError(f"GeometryType expects a shapely geometry, got {type(value)!r}")
            if dialect.name == "postgresql":
                return f"SRID={self.srid};{value.wkt}"
            return value.wkt
        return process

    def result_processor(self, dialect: Any, coltype: Any):
        def process(value: Any) -> BaseGeometry | None:
            if value is None:
                return None
            if isinstance(value, memoryview):
                value = bytes(value)
            if isinstance(value, bytes):
                return wkb.loads(value)
            if isinstance(value, str):
                s = value.strip()
                if s.upper().startswith("SRID=") and ";" in s:
                    s = s.split(";", 1)[1]
                try:
                    if len(s) >= 10 and all(ch in "0123456789abcdefABCDEF" for ch in s):
                        return wkb.loads(s, hex=True)
                except (ValueError, TypeError):
                    pass
                return wkt.loads(s)
            raw = getattr(value, "data", None)
            if raw is not None:
                if isinstance(raw, memoryview):
                    raw = bytes(raw)
                if isinstance(raw, bytes):
                    return wkb.loads(raw)
                if isinstance(raw, str):
                    return wkb.loads(raw, hex=True)
            raise TypeError(f"Unsupported geometry result {type(value)!r}")
        return process


@compiles(GeometryType)
def _compile_geometry_default(type_: GeometryType, compiler: Any, **kw: Any) -> str:
    return "TEXT"


@compiles(GeometryType, "postgresql")
def _compile_geometry_postgresql(type_: GeometryType, compiler: Any, **kw: Any) -> str:
    return f"geometry({type_.geometry_type},{type_.srid})"
