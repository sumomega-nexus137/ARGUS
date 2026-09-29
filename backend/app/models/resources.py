"""Operational resources and the expert-defined Approved Action Library."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import UTCDateTime
from app.models.area import MultilingualName


class Resource(MultilingualName, Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    resource_type: Mapped[str] = mapped_column(String(32))  # CREW | PUMP | VEHICLE | EQUIPMENT | OTHER
    subtype: Mapped[str] = mapped_column(String(64))
    capacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(255), default="DEMO")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    import_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ResourceStatus(Base):
    __tablename__ = "resource_status"

    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="AVAILABLE")  # AVAILABLE | UNAVAILABLE | FAILED
    delay_min: Mapped[int] = mapped_column(Integer, default=0)
    available_from: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="OPERATIONAL")
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ApprovedAction(MultilingualName, Base):
    """Action template defined by emergency specialists. ARGUS schedules; it never invents doctrine."""

    __tablename__ = "approved_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # None → all areas
    action_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {kk, ru, en}
    # {"crew_types": [...], "crew_count": 1, "pumps": 2, "vehicle_types": [...], "equipment": {"EXCAVATOR": 1}}
    requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    setup_min: Mapped[int] = mapped_column(Integer)
    execution_min: Mapped[int] = mapped_column(Integer)
    safety_buffer_min: Mapped[int] = mapped_column(Integer, default=20)
    equipment_release: Mapped[str] = mapped_column(String(16), default="TASK_END")  # TASK_END | HORIZON
    site_kinds: Mapped[list[str]] = mapped_column(JSON, default=list)
    prerequisites: Mapped[list[Any]] = mapped_column(JSON, default=list)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
