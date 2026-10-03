"""Human response plans, versions and tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import UTCDateTime


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(ForeignKey("operational_areas.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PlanVersion(Base):
    __tablename__ = "plan_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    area_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    # DRAFT → REVIEWED → APPROVED → ACTIVE ; SUPERSEDED | REJECTED
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    origin: Mapped[str] = mapped_column(String(16), default="HUMAN")  # HUMAN | OPTIMIZER | RECOMPUTE
    basis_scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basis_data_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resource_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    policy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    weights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    constraints: Mapped[list[Any]] = mapped_column(JSON, default=list)
    change_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    optimization_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlanTask(Base):
    __tablename__ = "plan_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_version_id: Mapped[str] = mapped_column(ForeignKey("plan_versions.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(16))  # e.g. T8
    template_id: Mapped[str] = mapped_column(String(64))
    site_id: Mapped[str] = mapped_column(String(64))
    resource_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    planned_departure: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PENDING | EN_ROUTE | WORKING | DONE | FAILED | BLOCKED | RESOURCE_UNAVAILABLE
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    status_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status_updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual_departure: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    rationale: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
