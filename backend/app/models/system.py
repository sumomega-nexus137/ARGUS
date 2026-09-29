"""Runs (optimization, stress tests, validation, pipelines), model versions, audit, imports, providers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import UTCDateTime


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scenario_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32), default="ALTERNATIVES")  # ALTERNATIVES | RESOURCE_GAP | RECOMPUTE
    policy: Mapped[str] = mapped_column(String(32))
    weights: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    constraints: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_version: Mapped[int] = mapped_column(Integer, default=0)


class StressTestRun(Base):
    __tablename__ = "stress_test_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_version_id: Mapped[str] = mapped_column(String(64), index=True)
    scenario_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    n_scenarios: Mapped[int] = mapped_column(Integer)
    n_feasible: Mapped[int] = mapped_column(Integer)
    robustness: Mapped[float] = mapped_column(Float)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    data_version: Mapped[int] = mapped_column(Integer, default=0)


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(String(64), index=True)
    dataset_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))  # REAL | SYNTHETIC_SELF_TEST
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[str] = mapped_column(String(64))
    trigger_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    steps: Mapped[list[Any]] = mapped_column(JSON, default=list)
    outcome: Mapped[str] = mapped_column(String(32))
    data_version: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    component: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    activated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    # operational clock (simulation clock in SIMULATION mode, wall clock in LIVE mode)
    op_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    area_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    data_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affects_results: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportJob(Base):
    __tablename__ = "imports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(String(64), index=True)
    import_type: Mapped[str] = mapped_column(String(32))  # resources | facilities | observations | road_events
    filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))  # PREVIEW | CONFIRMED | CANCELLED | FAILED
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, default=0)
    rows_warning: Mapped[int] = mapped_column(Integer, default=0)
    preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    applied_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProviderStatus(Base):
    __tablename__ = "provider_status"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # f"{area_id}:{layer}"
    area_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    layer: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(16))  # LIVE | CACHED | HISTORICAL | SIMULATION | STATIC
    status: Mapped[str] = mapped_column(String(16))  # OK | DEGRADED | OFFLINE | NOT_CONFIGURED
    quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    schedule_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
