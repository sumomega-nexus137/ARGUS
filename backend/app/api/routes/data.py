"""Manual operational input & data management: observations, conflicts, resources, road events, facilities,
approved action library, task sites."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user, require
from app.api.serialize import clean, names
from app.core.errors import ArgusError, NotFound
from app.core.security import Permission
from app.db.session import get_db
from app.models import (
    ApprovedAction,
    DataConflict,
    Observation,
    OperationalArea,
    Resource,
    ResourceStatus,
    RoadEvent,
    TaskSite,
    User,
)
from app.schemas.common import (
    ActionTemplateIn,
    ConflictResolution,
    FacilityCreate,
    ObservationCreate,
    PoolCount,
    ResourceStatusUpdate,
    ResourceUpsert,
    RoadEventCreate,
    VerificationUpdate,
)
from app.services.audit import Actor, operational_now, record
from app.services.ingest.authority import authority_label, authority_rank
from app.services.ingest.observations import (
    ObservationInput,
    add_observation,
    effective_observations,
    resolve_conflict,
    verify_observation,
)
from app.services.operations.inputs import (
    add_facility,
    add_road_event,
    clear_road_event,
    set_available_count,
    set_resource_status,
    upsert_resource,
)
from app.services.operations.pipeline import run_pipeline

router = APIRouter(tags=["data"])


def _pipe(p: dict) -> dict:
    return {k: v for k, v in p.items() if k != "health"} | {"plan_status": (p.get("health") or {}).get("status")}


# ------------------------------------------------------------------ observations & conflicts
@router.get("/api/areas/{area_id}/observations")
def list_obs(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    rows = db.scalars(select(Observation).where(Observation.area_id == area.id).order_by(Observation.observed_at.desc())).all()
    eff_ids: set[str] = set()
    for sid in {r.station_id for r in rows}:
        eff, _ = effective_observations(db, sid)
        eff_ids |= {e.obs.id for e in eff}
    now = operational_now(db, area.id)
    return clean({"now": now, "observations": [
        {"id": o.id, "station_id": o.station_id, "observed_at": o.observed_at, "water_level_cm": o.water_level_cm,
         "discharge_m3s": o.discharge_m3s, "source": o.source, "source_type": o.source_type, "verification": o.verification,
         "authority": authority_label(o.source_type, o.verification), "rank": authority_rank(o.source_type, o.verification),
         "mode": o.mode, "quality": o.quality, "notes": o.notes, "entered_by": o.entered_by, "entered_at": o.entered_at,
         "effective": o.id in eff_ids, "age_min": round((now - o.observed_at).total_seconds() / 60) if now else None,
         "import_id": o.import_id} for o in rows]})


@router.post("/api/areas/{area_id}/observations")
def create_obs(body: ObservationCreate, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
               actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    inp = ObservationInput(station_id=body.station_id, observed_at=body.observed_at or operational_now(db, area.id),
                           water_level_cm=body.water_level_cm, discharge_m3s=body.discharge_m3s, source=body.source,
                           source_type=body.source_type, verification=body.verification, notes=body.notes,
                           mode="SIMULATION" if area.clock_mode == "SIMULATION" else "LIVE")
    obs, conflicts = add_observation(db, area.id, inp, actor)
    pipe = run_pipeline(db, area.id, "OBSERVATION", obs.id, actor, condition=True)
    db.commit()
    return clean({"observation_id": obs.id, "conflicts": [{"id": c.id, "difference": c.difference} for c in conflicts],
                  "pipeline": _pipe(pipe)})


@router.post("/api/observations/{obs_id}/verification")
def verify(obs_id: str, body: VerificationUpdate, db: Session = Depends(get_db),
           actor: Actor = Depends(require(Permission.DATA_ADMIN))) -> dict:
    o = db.get(Observation, obs_id)
    if o is None:
        raise NotFound("observation", obs_id)
    verify_observation(db, o, body.verification, actor, body.note)
    pipe = run_pipeline(db, o.area_id, "OBSERVATION_VERIFIED", o.id, actor, condition=True)
    db.commit()
    return clean({"id": o.id, "verification": o.verification, "pipeline": _pipe(pipe)})


@router.get("/api/areas/{area_id}/conflicts")
def conflicts(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(DataConflict).where(DataConflict.area_id == area.id).order_by(DataConflict.created_at.desc())).all()
    out = []
    for c in rows:
        obs = [db.get(Observation, i) for i in c.observation_ids]
        out.append({"id": c.id, "kind": c.kind, "station_id": c.station_id, "status": c.status, "difference": c.difference,
                    "selected_observation_id": c.selected_observation_id, "resolution_note": c.resolution_note,
                    "resolved_by": c.resolved_by, "resolved_at": c.resolved_at, "created_at": c.created_at,
                    "observations": [{"id": o.id, "observed_at": o.observed_at, "water_level_cm": o.water_level_cm,
                                      "source": o.source, "source_type": o.source_type, "verification": o.verification,
                                      "authority": authority_label(o.source_type, o.verification),
                                      "rank": authority_rank(o.source_type, o.verification)} for o in obs if o]})
    return clean(out)


@router.post("/api/conflicts/{conflict_id}/resolve")
def resolve(conflict_id: str, body: ConflictResolution, db: Session = Depends(get_db),
            actor: Actor = Depends(require(Permission.DATA_ADMIN))) -> dict:
    c = db.get(DataConflict, conflict_id)
    if c is None:
        raise NotFound("data conflict", conflict_id)
    resolve_conflict(db, c, body.selected_observation_id, body.note, actor)
    pipe = run_pipeline(db, c.area_id, "DATA_CONFLICT_RESOLVED", c.id, actor, condition=True)
    db.commit()
    return clean({"id": c.id, "status": c.status, "selected": c.selected_observation_id, "pipeline": _pipe(pipe)})


# ------------------------------------------------------------------ resources
@router.get("/api/areas/{area_id}/resources")
def list_resources(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                   _: User = Depends(current_user)) -> list[dict]:
    rows = db.execute(select(Resource, ResourceStatus).join(ResourceStatus, ResourceStatus.resource_id == Resource.id, isouter=True)
                      .where(Resource.area_id == area.id).order_by(Resource.resource_type, Resource.id)).all()
    return clean([{"id": r.id, "resource_type": r.resource_type, "subtype": r.subtype, "capacity": r.capacity,
                   "capacity_unit": r.capacity_unit, "base_id": r.base_id, "names": names(r), "source": r.source,
                   "status": s.status if s else "AVAILABLE", "delay_min": s.delay_min if s else 0,
                   "note": s.note if s else None, "updated_by": s.updated_by if s else None,
                   "updated_at": s.updated_at if s else None} for r, s in rows])


@router.post("/api/areas/{area_id}/resources")
def upsert(body: ResourceUpsert, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
           actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    r = upsert_resource(db, area.id, body.model_dump(), actor)
    pipe = run_pipeline(db, area.id, "RESOURCE_CHANGED", r.id, actor)
    db.commit()
    return clean({"id": r.id, "pipeline": _pipe(pipe)})


@router.post("/api/resources/{resource_id}/status")
def resource_status(resource_id: str, body: ResourceStatusUpdate, db: Session = Depends(get_db),
                    actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    r = db.get(Resource, resource_id)
    if r is None:
        raise NotFound("resource", resource_id)
    set_resource_status(db, r, body.status, actor, delay_min=body.delay_min, note=body.note)
    pipe = run_pipeline(db, r.area_id, "RESOURCE_CHANGED", r.id, actor)
    db.commit()
    return clean({"id": r.id, "status": body.status, "delay_min": body.delay_min, "pipeline": _pipe(pipe)})


@router.post("/api/areas/{area_id}/resources/pool")
def pool(body: PoolCount, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
         actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    res = set_available_count(db, area.id, body.resource_type, body.subtype, body.count, actor, body.note)
    pipe = run_pipeline(db, area.id, "RESOURCE_POOL_CHANGED", f"{body.resource_type}:{body.count}", actor)
    db.commit()
    return clean({**res, "pipeline": _pipe(pipe)})


# ------------------------------------------------------------------ road events
@router.get("/api/areas/{area_id}/road-events")
def road_events(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(RoadEvent).where(RoadEvent.area_id == area.id).order_by(RoadEvent.created_at.desc())).all()
    return clean([{"id": e.id, "road_id": e.road_id, "segment_ids": e.segment_ids, "state": e.state,
                   "effective_from": e.effective_from, "effective_until": e.effective_until, "source": e.source,
                   "verification": e.verification, "reported_by": e.reported_by, "notes": e.notes, "active": e.active,
                   "created_at": e.created_at} for e in rows])


@router.post("/api/areas/{area_id}/road-events")
def create_road_event(body: RoadEventCreate, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                      actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    ev = add_road_event(db, area.id, road_id=body.road_id, segment_ids=body.segment_ids, state=body.state,
                        effective_from=body.effective_from, effective_until=body.effective_until, source=body.source,
                        verification=body.verification, notes=body.notes, actor=actor)
    pipe = run_pipeline(db, area.id, f"ROAD_{body.state}", ev.id, actor)
    db.commit()
    return clean({"id": ev.id, "pipeline": _pipe(pipe), "health": pipe.get("health")})


@router.post("/api/road-events/{event_id}/clear")
def clear_event(event_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    ev = db.get(RoadEvent, event_id)
    if ev is None:
        raise NotFound("road event", event_id)
    if not ev.active:
        raise ArgusError("event_not_active", "Road event already cleared")
    clear_road_event(db, ev, actor, None)
    pipe = run_pipeline(db, ev.area_id, "ROAD_EVENT_CLEARED", ev.id, actor)
    db.commit()
    return clean({"id": ev.id, "pipeline": _pipe(pipe)})


# ------------------------------------------------------------------ facilities / sites / actions
@router.post("/api/areas/{area_id}/facilities")
def create_facility(body: FacilityCreate, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                    actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    f = add_facility(db, area.id, body.model_dump(), actor)
    pipe = run_pipeline(db, area.id, "FACILITY_ADDED", f.id, actor)
    db.commit()
    return clean({"id": f.id, "pipeline": _pipe(pipe)})


@router.get("/api/areas/{area_id}/sites")
def sites(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(TaskSite).where(TaskSite.area_id == area.id).order_by(TaskSite.id)).all()
    return clean([{"id": t.id, "kind": t.kind, "names": names(t), "sector_id": t.sector_id, "protects": t.protects,
                   "work_depth_limit_m": t.work_depth_limit_m, "lon": t.geom.x, "lat": t.geom.y} for t in rows])


@router.get("/api/actions")
def actions(area_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(ApprovedAction).order_by(ApprovedAction.id)).all()
    return clean([{"id": a.id, "area_id": a.area_id, "action_type": a.action_type, "names": names(a),
                   "description": a.description, "requirements": a.requirements, "setup_min": a.setup_min,
                   "execution_min": a.execution_min, "safety_buffer_min": a.safety_buffer_min,
                   "equipment_release": a.equipment_release, "site_kinds": a.site_kinds, "prerequisites": a.prerequisites,
                   "constraints": a.constraints, "version": a.version, "approved_by": a.approved_by, "active": a.active,
                   "notes": a.notes}
                  for a in rows if area_id is None or a.area_id in (None, area_id)])


@router.post("/api/actions")
def upsert_action(body: ActionTemplateIn, db: Session = Depends(get_db),
                  actor: Actor = Depends(require(Permission.DATA_ADMIN))) -> dict:
    a = db.get(ApprovedAction, body.id)
    created = a is None
    if a is None:
        a = ApprovedAction(id=body.id)
        db.add(a)
    else:
        a.version = (a.version or 1) + 1
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    a.approved_by = f"{actor.username} ({actor.role})"
    a.active = True
    db.flush()
    record(db, actor, "ACTION_TEMPLATE_CREATED" if created else "ACTION_TEMPLATE_UPDATED", "approved_action", a.id,
           f"Approved action {a.id} {'created' if created else f'updated to v{a.version}'}", area_id=body.area_id,
           details=body.model_dump())
    db.commit()
    return clean({"id": a.id, "version": a.version})
