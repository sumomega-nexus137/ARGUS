from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user, require
from app.api.serialize import clean, fc, feature, names
from app.core.errors import ArgusError
from app.core.security import Permission
from app.db.session import get_db
from app.models import (
    Base_,
    Bottleneck,
    Bridge,
    Building,
    CriticalFacility,
    HydroStation,
    OperationalArea,
    PopulationZone,
    RoadNode,
    RoadSegment,
    Sector,
    TaskSite,
    User,
)
from app.schemas.common import ClockUpdate
from app.services.audit import Actor, changes_since, record
from app.services.clock import area_now
from app.services.ingest.providers import area_freshness, outage_enabled
from app.services.overview import area_overview
from app.services.scenario.runtime import current_scenario

router = APIRouter(prefix="/api/areas", tags=["areas"])
LAYERS = ("roads", "buildings", "facilities", "sectors", "population_zones", "bridges", "bottlenecks", "task_sites",
          "bases", "stations", "river", "road_nodes", "waterways")


def _bundle_file(area: OperationalArea, name: str) -> dict | None:
    import json
    from pathlib import Path

    d = (area.config or {}).get("bundle_dir")
    if not d or not (Path(d) / name).exists():
        return None
    with open(Path(d) / name, encoding="utf-8") as f:
        return json.load(f)


@router.get("")
def list_areas(db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    areas = db.scalars(select(OperationalArea).order_by(OperationalArea.sort_order)).all()
    return [clean(area_overview(db, a)) for a in areas]


@router.get("/{area_id}")
def get_area(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
             _: User = Depends(current_user)) -> dict:
    sc = current_scenario(db, area.id)
    return clean({
        "id": area.id, "names": names(area), "river_names": area.river_names, "archetype": area.archetype,
        "crs_epsg": area.crs_epsg, "bbox": area.bbox, "center": [area.center.x, area.center.y],
        "utc_offset_min": area.utc_offset_min, "timezone": area.timezone, "clock_mode": area.clock_mode,
        "now": area_now(area).isoformat(), "is_demo": area.is_demo, "data_version": area.data_version,
        "static_version": (area.config or {}).get("static_version", 1),
        "reference_time": sc.reference_time.isoformat(), "demo_note": (area.config or {}).get("demo_note"),
        "has_terrain": True, "data_profile": (area.config or {}).get("data_profile", "demo"),
        "role": (area.config or {}).get("role"), "assumptions": (area.config or {}).get("assumptions", []),
        "pack": (area.config or {}).get("pack"), "clock_start": (area.config or {}).get("clock_start"),
        "population_meta": (area.config or {}).get("population_meta"), "road_meta": (area.config or {}).get("road_meta"),
        "economic_model": (area.config or {}).get("economic_model", "demo_unit_values"),
        "scenario_station_id": (sc.parameters or {}).get("station_id"),
    })


def _layer(db: Session, area: OperationalArea, layer: str) -> dict:
    aid = area.id
    if layer == "roads":
        emb = (area.config or {}).get("embankments", {})
        return fc([feature(s.geom, {"id": s.id, "road_id": s.road_id, "road_class": s.road_class, "speed_kmh": s.speed_kmh,
                                    "length_m": s.length_m, "bridge_id": s.bridge_id, "names": names(s),
                                    "embankment_m": emb.get(s.id)})
                   for s in db.scalars(select(RoadSegment).where(RoadSegment.area_id == aid))])
    if layer == "road_nodes":
        return fc([feature(n.geom, {"id": n.id.split(":", 1)[-1]}) for n in db.scalars(select(RoadNode).where(RoadNode.area_id == aid))])
    if layer == "buildings":
        return fc([feature(b.geom, {"id": b.id, "use": b.use, "floors": b.floors, "height_m": b.height_m,
                                    "sector_id": b.sector_id})
                   for b in db.scalars(select(Building).where(Building.area_id == aid))], promote_id="id")
    if layer == "facilities":
        return fc([feature(f.geom, {"id": f.id, "facility_type": f.facility_type, "criticality": f.criticality,
                                    "population_served": f.population_served, "names": names(f), "sector_id": f.sector_id,
                                    "verification": f.verification, "source": f.source})
                   for f in db.scalars(select(CriticalFacility).where(CriticalFacility.area_id == aid))])
    if layer == "sectors":
        return fc([feature(s.geom, {"id": s.code, "names": names(s)}) for s in db.scalars(select(Sector).where(Sector.area_id == aid))])
    if layer == "population_zones":
        return fc([feature(z.geom, {"id": z.id, "sector_id": z.sector_id, "population": z.population,
                                    "vulnerable_share": z.vulnerable_share, "source": z.source, "aggregated": True})
                   for z in db.scalars(select(PopulationZone).where(PopulationZone.area_id == aid))])
    if layer == "bridges":
        return fc([feature(b.geom, {"id": b.id, "names": names(b), "structure_type": b.structure_type,
                                    "segment_ids": b.segment_ids, "deck_clearance_m": b.deck_clearance_m})
                   for b in db.scalars(select(Bridge).where(Bridge.area_id == aid))])
    if layer == "bottlenecks":
        return fc([feature(b.geom, {"id": b.id, "names": names(b), "kind": b.kind, "segment_ids": b.segment_ids,
                                    "notes": b.notes})
                   for b in db.scalars(select(Bottleneck).where(Bottleneck.area_id == aid))])
    if layer == "task_sites":
        return fc([feature(t.geom, {"id": t.id, "kind": t.kind, "names": names(t), "sector_id": t.sector_id,
                                    "protects": t.protects, "work_depth_limit_m": t.work_depth_limit_m})
                   for t in db.scalars(select(TaskSite).where(TaskSite.area_id == aid))])
    if layer == "bases":
        return fc([feature(b.geom, {"id": b.id, "names": names(b), "safe": b.safe})
                   for b in db.scalars(select(Base_).where(Base_.area_id == aid))])
    if layer == "stations":
        return fc([feature(s.geom, {"id": s.id, "names": names(s), "river": s.river, "watch": s.watch_stage_cm,
                                    "warning": s.warning_stage_cm, "critical": s.critical_stage_cm,
                                    "bankfull": s.bankfull_stage_cm})
                   for s in db.scalars(select(HydroStation).where(HydroStation.area_id == aid))])
    if layer == "river":
        lines = (area.config or {}).get("river_lines")
        if lines:
            return fc([{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": lines},
                        "properties": {"names": area.river_names, "source": "OpenStreetMap (ODbL)"}}])
        coords = (area.config or {}).get("river_centerline", [])
        return fc([{"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {"names": area.river_names}}] if coords else [])
    if layer == "waterways":
        data = _bundle_file(area, "waterways.geojson")
        return fc(data["features"] if data else [])
    raise ArgusError("unknown_layer", f"Layer must be one of {LAYERS}")


@router.get("/{area_id}/layers/{layer}")
def get_layer(layer: str, response: Response, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
              _: User = Depends(current_user)) -> dict:
    response.headers["Cache-Control"] = "private, max-age=60"
    response.headers["X-Static-Version"] = str((area.config or {}).get("static_version", 1))
    data = _layer(db, area, layer)
    data["demo"] = area.is_demo
    return data


@router.get("/{area_id}/freshness")
def freshness(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
              _: User = Depends(current_user)) -> dict:
    return clean({"now": area_now(area).isoformat(), "clock_mode": area.clock_mode, "external_offline": outage_enabled(),
                  "sources": area_freshness(db, area)})


@router.post("/{area_id}/clock")
def update_clock(body: ClockUpdate, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                 actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    if area.clock_mode == "LIVE":
        raise ArgusError("clock_is_live", "The operational clock of a LIVE area follows wall-clock time")
    old = area_now(area)
    sc = current_scenario(db, area.id)
    if body.reset:
        start = (area.config or {}).get("clock_start")
        area.sim_now = datetime.fromisoformat(start) if start else sc.reference_time
    elif body.set_to is not None:
        area.sim_now = body.set_to
    elif body.advance_min is not None:
        area.sim_now = old + timedelta(minutes=body.advance_min)
    lo = sc.reference_time + timedelta(minutes=sc.frame_offsets_min[0])
    hi = sc.reference_time + timedelta(minutes=sc.frame_offsets_min[-1])
    area.sim_now = min(max(area.sim_now, lo), hi)
    record(db, actor, "SIMULATION_CLOCK_CHANGED", "area", area.id, f"Simulation clock {old.isoformat()} → {area.sim_now.isoformat()}",
           area_id=area.id, affects_results=True, op_time=area.sim_now)
    db.commit()
    return {"now": area.sim_now.isoformat(), "previous": old.isoformat()}


@router.get("/{area_id}/changes")
def changes(since_version: int = 0, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
            _: User = Depends(current_user)) -> dict:
    rows = changes_since(db, area.id, since_version)
    return clean({"data_version": area.data_version, "since": since_version, "changes": [
        {"id": r.id, "ts": r.ts, "op_time": r.op_time, "username": r.username, "role": r.role, "action": r.action,
         "entity_type": r.entity_type, "entity_id": r.entity_id, "summary": r.summary, "data_version": r.data_version,
         "details": r.details} for r in rows]})


@router.get("/{area_id}/history")
def history(area: OperationalArea = Depends(area_or_404), _: User = Depends(current_user)) -> dict:
    """HISTORICAL context: official chronology, curated hydrology, satellite evidence and GloFAS/weather
    event-period context bundled with the real-data pack (no network access)."""
    data = _bundle_file(area, "history.json")
    if data is None:
        return {"available": False, "mode": "DEMO" if area.is_demo else None}
    return clean({"available": True, **data, "scenario_note": (_bundle_file(area, "scenario.json") or {}).get("note"),
                  "scenario_limitations": (_bundle_file(area, "scenario.json") or {}).get("limitations", [])})
