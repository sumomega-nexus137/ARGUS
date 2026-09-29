"""Exposure / infrastructure layers: buildings, roads, bridges, facilities, bottlenecks, task sites."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import GeometryType, UTCDateTime
from app.models.area import MultilingualName


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    geom: Mapped[Any] = mapped_column(GeometryType("POLYGON"))
    use: Mapped[str] = mapped_column(String(32))  # residential | commercial | public | industrial
    floors: Mapped[int] = mapped_column(Integer, default=1)
    height_m: Mapped[float] = mapped_column(Float, default=3.0)
    floor_area_m2: Mapped[float] = mapped_column(Float, default=0.0)
    sector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="DEMO")


class RoadNode(Base):
    __tablename__ = "road_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    geom: Mapped[Any] = mapped_column(GeometryType("POINT"))


class RoadSegment(MultilingualName, Base):
    """One edge of the routable road graph; ``road_id`` groups edges into a named road (e.g. R7)."""

    __tablename__ = "roads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    road_id: Mapped[str] = mapped_column(String(32), index=True)
    road_class: Mapped[str] = mapped_column(String(32))
    geom: Mapped[Any] = mapped_column(GeometryType("LINESTRING"))
    length_m: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float] = mapped_column(Float)
    u_node: Mapped[str] = mapped_column(String(64))
    v_node: Mapped[str] = mapped_column(String(64))
    bridge_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="DEMO")


class RoadEvent(Base):
    """Manual / field road state report. Verified field observations override the model."""

    __tablename__ = "road_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    road_id: Mapped[str] = mapped_column(String(32), index=True)
    segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)  # empty → whole road
    state: Mapped[str] = mapped_column(String(16))  # OPEN | RESTRICTED | CLOSED
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime)
    effective_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(255))
    verification: Mapped[str] = mapped_column(String(16), default="UNVERIFIED")
    reported_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    import_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Bridge(MultilingualName, Base):
    __tablename__ = "bridges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    geom: Mapped[Any] = mapped_column(GeometryType("POINT"))
    structure_type: Mapped[str] = mapped_column(String(32), default="BRIDGE")  # BRIDGE | CULVERT
    segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    deck_clearance_m: Mapped[float] = mapped_column(Float)  # above bankfull water level
    source: Mapped[str] = mapped_column(String(255), default="DEMO")


class Bottleneck(MultilingualName, Base):
    __tablename__ = "bottlenecks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # BRIDGE | CHANNEL_CONSTRAINT | CULVERT | LOW_ROAD
    geom: Mapped[Any] = mapped_column(GeometryType("POINT"))
    segment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    bridge_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="DEMO")


class CriticalFacility(MultilingualName, Base):
    __tablename__ = "critical_facilities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    facility_type: Mapped[str] = mapped_column(String(32))
    geom: Mapped[Any] = mapped_column(GeometryType("POINT"))
    criticality: Mapped[int] = mapped_column(Integer, default=50)  # 0–100, expert-defined
    population_served: Mapped[int] = mapped_column(Integer, default=0)
    sector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="DEMO")
    verification: Mapped[str] = mapped_column(String(16), default="UNVERIFIED")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    import_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TaskSite(MultilingualName, Base):
    """Location where an approved action may be performed (levee section, drainage point, facility…)."""

    __tablename__ = "task_sites"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    geom: Mapped[Any] = mapped_column(GeometryType("POINT"))
    sector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    protects: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {facility_ids, sector_ids}
    work_depth_limit_m: Mapped[float] = mapped_column(Float, default=0.25)
    explicit_deadline: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_candidate: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
