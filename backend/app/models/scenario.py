"""Scenario Engine persistence: scenarios, frames, cached flood extents, action window snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import GeometryType, UTCDateTime


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16))  # LIVE | CACHED | HISTORICAL | SIMULATION
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    reference_time: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(64))  # synthetic_stage_hand | raster_manifest
    provider_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    frame_offsets_min: Mapped[list[int]] = mapped_column(JSON, default=list)
    members: Mapped[list[Any]] = mapped_column(JSON, default=list)
    active_member_id: Mapped[str] = mapped_column(String(64))
    selection: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # how the member was selected
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    uncertainty: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(255))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ScenarioFrame(Base):
    __tablename__ = "scenario_frames"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    frame_index: Mapped[int] = mapped_column(Integer)
    offset_min: Mapped[int] = mapped_column(Integer)
    valid_time: Mapped[datetime] = mapped_column(UTCDateTime)
    kind: Mapped[str] = mapped_column(String(16))  # ANALYSIS | FORECAST
    gauge_stage_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FloodExtent(Base):
    """Cached vectorised flood extent (simplified) for a scenario member / frame."""

    __tablename__ = "flood_extents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[str] = mapped_column(String(64))
    frame_index: Mapped[int] = mapped_column(Integer)
    geom: Mapped[Any] = mapped_column(GeometryType("MULTIPOLYGON"), nullable=True)
    flooded_area_km2: Mapped[float] = mapped_column(Float, default=0.0)
    max_depth_m: Mapped[float] = mapped_column(Float, default=0.0)


class ActionWindowSnapshot(Base):
    __tablename__ = "action_windows"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(64))
    data_version: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
