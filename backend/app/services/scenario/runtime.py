"""Scenario runtime: resolves a Scenario record into a FloodScenarioProvider + time model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import resolve_data_path
from app.core.errors import ArgusError, NotFound
from app.models import Scenario
from app.providers.flood.base import FloodScenarioProvider
from app.providers.flood.raster_manifest import RasterManifestProvider
from app.providers.flood.synthetic import SyntheticStageHandProvider


@lru_cache(maxsize=32)
def _provider_cached(kind: str, config_json: str, members_json: str) -> FloodScenarioProvider:
    cfg = json.loads(config_json)
    if kind == "synthetic_stage_hand":
        members = json.loads(members_json)
        return SyntheticStageHandProvider(resolve_data_path(cfg["terrain_dir"]), members, cfg["bankfull_cm"])
    if kind == "raster_manifest":
        return RasterManifestProvider(resolve_data_path(cfg["manifest_path"]))
    raise ArgusError("unknown_provider", f"Unknown flood scenario provider '{kind}'")


def provider_for(s: Scenario) -> FloodScenarioProvider:
    members_json = json.dumps(s.members if s.provider == "synthetic_stage_hand" else [], sort_keys=True)
    return _provider_cached(s.provider, json.dumps(s.provider_config, sort_keys=True), members_json)


@dataclass
class ScenarioRuntime:
    id: str
    area_id: str
    family_id: str
    version: int
    name: str
    mode: str
    reference_time: datetime
    frame_offsets: list[int]
    member: str
    members_order: list[str]
    provider: FloodScenarioProvider
    model_version: str
    selection: dict = field(default_factory=dict)

    @property
    def horizon_end(self) -> float:
        return float(self.frame_offsets[-1])

    @property
    def horizon_start(self) -> float:
        return float(self.frame_offsets[0])

    def member_shifted(self, shift: int) -> str:
        """Member ``shift`` steps above (positive = higher water) the active member, clamped."""
        i = self.members_order.index(self.member)
        return self.members_order[max(0, min(len(self.members_order) - 1, i + shift))]


def runtime_for(s: Scenario) -> ScenarioRuntime:
    order = [m["id"] for m in sorted(s.members, key=lambda m: (m.get("peak_stage_cm") or 0))]
    return ScenarioRuntime(
        id=s.id, area_id=s.area_id, family_id=s.family_id, version=s.version, name=s.name, mode=s.mode,
        reference_time=s.reference_time, frame_offsets=list(s.frame_offsets_min), member=s.active_member_id,
        members_order=order, provider=provider_for(s), model_version=s.model_version, selection=s.selection or {},
    )


def current_scenario(db: Session, area_id: str) -> Scenario:
    s = db.scalars(
        select(Scenario).where(Scenario.area_id == area_id, Scenario.is_current.is_(True)).order_by(Scenario.version.desc())
    ).first()
    if s is None:
        raise NotFound("current scenario for area", area_id)
    return s


def get_scenario(db: Session, scenario_id: str) -> Scenario:
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise NotFound("scenario", scenario_id)
    return s
