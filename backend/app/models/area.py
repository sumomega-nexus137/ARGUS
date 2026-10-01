"""Operational areas, sectors, population zones, bases, users."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import GeometryType, UTCDateTime


class MultilingualName:
    """Mixin: multilingual display names; the original source name is never destroyed."""

    name_kk: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_ru: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_original: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def names(self) -> dict[str, str | None]:
        return {"kk": self.name_kk, "ru": self.name_ru, "en": self.name_en, "original": self.name_original}


class OperationalArea(MultilingualName, Base):
    __tablename__ = "operational_areas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    river_names: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    archetype: Mapped[str] = mapped_column(String(64))  # e.g. RIVERINE_FLOODPLAIN, URBAN_SNOWMELT_RIVER
    crs_epsg: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list[float]] = mapped_column(JSON)  # lon/lat [minx, miny, maxx, maxy]
    center: Mapped[Any] = mapped_column(GeometryType("POINT"))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Almaty")
    utc_offset_min: Mapped[int] = mapped_column(Integer, default=300)
    clock_mode: Mapped[str] = mapped_column(String(16), default="SIMULATION")  # LIVE | SIMULATION | HISTORICAL
    sim_now: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    data_version: Mapped[int] = mapped_column(Integer, default=1)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Sector(MultilingualName, Base):
    __tablename__ = "sectors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    geom: Mapped[Any] = mapped_column(GeometryType("POLYGON"))


class PopulationZone(Base):
    """Aggregated population only (no personal data)."""

    __tablename__ = "population_zones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    sector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geom: Mapped[Any] = mapped_column(GeometryType("POLYGON"))
    population: Mapped[int] = mapped_column(Integer)
    vulnerable_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16), default="SIMULATION")


class Base_(MultilingualName, Base):
    """Response base / depot (named Base_ to avoid clashing with the declarative Base)."""

    __tablename__ = "bases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    geom: Mapped[Any] = mapped_column(GeometryType("POINT"))
    safe: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_language: Mapped[str] = mapped_column(String(4), default="kk")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
