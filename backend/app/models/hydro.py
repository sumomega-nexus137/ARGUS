"""Hydrology: stations, observations, forecasts, data conflicts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import GeometryType, UTCDateTime
from app.models.area import MultilingualName


class HydroStation(MultilingualName, Base):
    __tablename__ = "hydro_stations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    geom: Mapped[Any] = mapped_column(GeometryType("POINT"))
    river: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bankfull_stage_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    watch_stage_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    warning_stage_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    critical_stage_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="manual")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("hydro_stations.id", ondelete="CASCADE"), index=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    water_level_cm: Mapped[float] = mapped_column(Float)
    discharge_m3s: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(255))
    # FIELD | HYDROPOST | FORECAST | SATELLITE | GLOBAL_MODEL | SIMULATION
    source_type: Mapped[str] = mapped_column(String(32))
    verification: Mapped[str] = mapped_column(String(16), default="UNVERIFIED")  # VERIFIED | UNVERIFIED | REJECTED
    mode: Mapped[str] = mapped_column(String(16), default="SIMULATION")
    quality: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    import_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    station_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16), default="SIMULATION")
    series: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [[iso_time, stage_cm], ...]
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DataConflict(Base):
    __tablename__ = "data_conflicts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="OBSERVATION")
    station_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observation_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    difference: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # OPEN | RESOLVED
    selected_observation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
