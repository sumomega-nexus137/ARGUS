"""Request schemas (Pydantic). Engine outputs are returned as documented JSON objects."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ObservationCreate(BaseModel):
    station_id: str
    water_level_cm: float = Field(ge=-100, le=3000)
    discharge_m3s: float | None = Field(default=None, ge=0, le=50000)
    observed_at: datetime | None = None
    source: str = Field(min_length=1, max_length=255)
    source_type: Literal["FIELD", "HYDROPOST", "FORECAST", "SATELLITE", "GLOBAL_MODEL", "SIMULATION"] = "FIELD"
    verification: Literal["VERIFIED", "UNVERIFIED"] = "UNVERIFIED"
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("observed_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamp must include a timezone offset")
        return v


class VerificationUpdate(BaseModel):
    verification: Literal["VERIFIED", "UNVERIFIED", "REJECTED"]
    note: str | None = None


class ConflictResolution(BaseModel):
    selected_observation_id: str
    note: str | None = Field(default=None, max_length=2000)


class RoadEventCreate(BaseModel):
    road_id: str
    segment_ids: list[str] = Field(default_factory=list)
    state: Literal["OPEN", "RESTRICTED", "CLOSED"]
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    source: str = Field(default="Field report", max_length=255)
    verification: Literal["VERIFIED", "UNVERIFIED"] = "VERIFIED"
    notes: str | None = Field(default=None, max_length=2000)


class ResourceStatusUpdate(BaseModel):
    status: Literal["AVAILABLE", "UNAVAILABLE", "FAILED"]
    delay_min: int = Field(default=0, ge=0, le=24 * 60)
    note: str | None = Field(default=None, max_length=2000)


class ResourceUpsert(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-+.]+$")
    resource_type: Literal["CREW", "PUMP", "VEHICLE", "EQUIPMENT", "OTHER"]
    subtype: str = Field(default="GENERIC", max_length=64)
    capacity: float | None = None
    capacity_unit: str | None = None
    base_id: str | None = None
    name_kk: str | None = None
    name_ru: str | None = None
    name_en: str | None = None
    status: Literal["AVAILABLE", "UNAVAILABLE", "FAILED"] = "AVAILABLE"


class PoolCount(BaseModel):
    resource_type: Literal["CREW", "PUMP", "VEHICLE", "EQUIPMENT", "OTHER"]
    subtype: str | None = None
    count: int = Field(ge=0, le=1000)
    note: str | None = None


class FacilityCreate(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    facility_type: str
    name_kk: str | None = None
    name_ru: str | None = None
    name_en: str | None = None
    name_original: str | None = None
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    criticality: int = Field(default=50, ge=0, le=100)
    population_served: int = Field(default=0, ge=0)
    sector_id: str | None = None
    verification: Literal["VERIFIED", "UNVERIFIED"] = "UNVERIFIED"
    source: str | None = "Manual entry"


class TaskIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    template_id: str
    site_id: str
    resource_ids: list[str] = Field(default_factory=list)
    planned_departure: datetime | None = None
    dependencies: list[str] = Field(default_factory=list)
    notes: str | None = None


class PlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    tasks: list[TaskIn] = Field(default_factory=list)


class TasksReplace(BaseModel):
    tasks: list[TaskIn]


class NewVersionRequest(BaseModel):
    tasks: list[TaskIn] | None = None
    note: str | None = None


class TransitionRequest(BaseModel):
    target: Literal["REVIEWED", "APPROVED", "ACTIVE", "REJECTED", "DRAFT"]
    note: str | None = Field(default=None, max_length=2000)


class ConstraintIn(BaseModel):
    kind: Literal["FORBID_RESOURCE_SECTOR", "FORBID_RESOURCE_TASK", "REQUIRE_TASK", "EXCLUDE_TASK"]
    resource_id: str | None = None
    sector: str | None = None
    task_code: str | None = None
    note: str | None = None


class ConstraintsUpdate(BaseModel):
    constraints: list[ConstraintIn]


class OptimizeRequest(BaseModel):
    policy: Literal["LIFE_SAFETY", "CRITICAL_INFRASTRUCTURE", "ECONOMIC_LOSS", "BALANCED"] = "BALANCED"
    weights: dict[str, float] | None = None
    extra_constraints: list[ConstraintIn] = Field(default_factory=list)
    what_if_unavailable: list[str] = Field(default_factory=list)


class AdoptRequest(BaseModel):
    alternative_id: str


class TaskStatusUpdate(BaseModel):
    status: Literal["PENDING", "EN_ROUTE", "WORKING", "DONE", "FAILED", "BLOCKED", "RESOURCE_UNAVAILABLE"]
    note: str | None = Field(default=None, max_length=2000)


class RecomputeRequest(BaseModel):
    policy: Literal["LIFE_SAFETY", "CRITICAL_INFRASTRUCTURE", "ECONOMIC_LOSS", "BALANCED"] = "BALANCED"
    weights: dict[str, float] | None = None


class MemberSelect(BaseModel):
    member_id: str
    note: str = Field(default="", max_length=2000)
    lock: bool = False


class ClockUpdate(BaseModel):
    advance_min: int | None = Field(default=None, ge=-24 * 60, le=24 * 60)
    set_to: datetime | None = None
    reset: bool = False


class WhatIfBottleneck(BaseModel):
    bottleneck_ids: list[str] = Field(default_factory=list)
    as_of_min: float | None = None


class OutageToggle(BaseModel):
    enabled: bool


class ActionTemplateIn(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    action_type: str = Field(min_length=1, max_length=64)
    name_kk: str | None = None
    name_ru: str | None = None
    name_en: str | None = None
    description: dict[str, str] = Field(default_factory=dict)
    requirements: dict = Field(default_factory=dict)
    setup_min: int = Field(ge=0, le=24 * 60)
    execution_min: int = Field(ge=0, le=24 * 60)
    safety_buffer_min: int = Field(default=20, ge=0, le=24 * 60)
    equipment_release: Literal["TASK_END", "HORIZON"] = "TASK_END"
    site_kinds: list[str] = Field(default_factory=list)
    prerequisites: list = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    area_id: str | None = None
