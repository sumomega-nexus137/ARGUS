"""Manual operational input: road events, resources, critical facilities (first-class production features).

Every update stores who / when / source / verification and writes an audit entry that bumps the
area's data version so dependent results are recomputed and the change is explainable.
"""

from __future__ import annotations

from datetime import datetime

from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ArgusError, NotFound
from app.db.base import new_id
from app.models import CriticalFacility, OperationalArea, Resource, ResourceStatus, RoadEvent, RoadSegment
from app.repositories.context import invalidate_static
from app.services.audit import Actor, operational_now, record

ROAD_STATES = ("OPEN", "RESTRICTED", "CLOSED")
RESOURCE_TYPES = ("CREW", "PUMP", "VEHICLE", "EQUIPMENT", "OTHER")
RESOURCE_STATUSES = ("AVAILABLE", "UNAVAILABLE", "FAILED")
FACILITY_TYPES = ("HOSPITAL", "CLINIC", "CARE_HOME", "SCHOOL", "SHELTER", "WATER_SUPPLY", "POWER", "HEATING",
                  "FIRE_STATION", "ADMINISTRATION", "OTHER")


def add_road_event(db: Session, area_id: str, *, road_id: str, segment_ids: list[str], state: str,
                   effective_from: datetime | None, effective_until: datetime | None, source: str, verification: str,
                   notes: str | None, actor: Actor, import_id: str | None = None) -> RoadEvent:
    if state not in ROAD_STATES:
        raise ArgusError("invalid_road_state", f"Road state must be one of {ROAD_STATES}")
    if verification not in ("VERIFIED", "UNVERIFIED"):
        raise ArgusError("invalid_verification")
    segs = list(db.scalars(select(RoadSegment.id).where(RoadSegment.area_id == area_id, RoadSegment.road_id == road_id)))
    if not segs:
        raise NotFound("road", road_id)
    bad = [s for s in segment_ids if s not in segs]
    if bad:
        raise ArgusError("unknown_segment", f"Segments not on road {road_id}: {bad}", segments=bad)
    start = effective_from or operational_now(db, area_id)
    ev = RoadEvent(id=new_id("re-"), area_id=area_id, road_id=road_id, segment_ids=segment_ids, state=state,
                   effective_from=start, effective_until=effective_until, source=source, verification=verification,
                   reported_by=actor.username, notes=notes, active=True, import_id=import_id)
    db.add(ev)
    db.flush()
    action = {"CLOSED": "ROAD_CLOSED", "RESTRICTED": "ROAD_RESTRICTED", "OPEN": "ROAD_OPENED"}[state]
    scope = f"{road_id}" + (f" [{', '.join(segment_ids)}]" if segment_ids else "")
    record(db, actor, action, "road_event", ev.id, f"{scope}: {state} ({verification}, {source})", area_id=area_id,
           affects_results=True, details={"road_id": road_id, "segment_ids": segment_ids, "state": state,
                                          "verification": verification, "source": source,
                                          "effective_from": start.isoformat(), "notes": notes})
    return ev


def clear_road_event(db: Session, ev: RoadEvent, actor: Actor, note: str | None) -> RoadEvent:
    ev.active = False
    ev.effective_until = operational_now(db, ev.area_id)
    record(db, actor, "ROAD_EVENT_CLEARED", "road_event", ev.id, f"{ev.road_id}: field override cleared",
           area_id=ev.area_id, affects_results=True, details={"note": note})
    return ev


def set_resource_status(db: Session, resource: Resource, status: str, actor: Actor, *, delay_min: int = 0,
                        note: str | None = None, source: str = "OPERATIONAL") -> ResourceStatus:
    if status not in RESOURCE_STATUSES:
        raise ArgusError("invalid_resource_status")
    st = db.get(ResourceStatus, resource.id)
    if st is None:
        st = ResourceStatus(resource_id=resource.id)
        db.add(st)
    old = (st.status, st.delay_min)
    st.status, st.delay_min, st.note, st.source = status, max(0, int(delay_min)), note, source
    st.updated_by, st.updated_at = actor.username, operational_now(db, resource.area_id)
    action = "RESOURCE_DELAYED" if status == "AVAILABLE" and delay_min else (
        "RESOURCE_FAILED" if status == "FAILED" else "RESOURCE_CHANGED")
    record(db, actor, action, "resource", resource.id,
           f"{resource.id}: {old[0]} → {status}" + (f" (delay {delay_min} min)" if delay_min else ""),
           area_id=resource.area_id, affects_results=True,
           details={"from": {"status": old[0], "delay_min": old[1]}, "to": {"status": status, "delay_min": delay_min},
                    "note": note})
    return st


def set_available_count(db: Session, area_id: str, resource_type: str, subtype: str | None, count: int, actor: Actor,
                        note: str | None = None) -> dict:
    """E.g. AVAILABLE PUMPS 16 → 8: the highest-numbered units beyond ``count`` become UNAVAILABLE."""
    q = select(Resource).where(Resource.area_id == area_id, Resource.resource_type == resource_type)
    if subtype:
        q = q.where(Resource.subtype == subtype)
    units = sorted(db.scalars(q), key=lambda r: r.id)
    if count < 0 or count > len(units):
        raise ArgusError("invalid_count", f"Count must be between 0 and {len(units)}", max=len(units))
    before = 0
    changed = []
    for i, r in enumerate(units):
        st = db.get(ResourceStatus, r.id)
        cur = st.status if st else "AVAILABLE"
        if cur == "AVAILABLE":
            before += 1
        target = "AVAILABLE" if i < count else "UNAVAILABLE"
        if cur in ("AVAILABLE", "UNAVAILABLE") and cur != target:
            if st is None:
                st = ResourceStatus(resource_id=r.id)
                db.add(st)
            st.status = target
            st.updated_by, st.updated_at = actor.username, operational_now(db, area_id)
            st.note = note
            changed.append(r.id)
    record(db, actor, "RESOURCE_POOL_CHANGED", "resource_pool", f"{resource_type}:{subtype or '*'}",
           f"Available {resource_type.lower()}s: {before} → {count}", area_id=area_id, affects_results=True,
           details={"type": resource_type, "subtype": subtype, "from": before, "to": count, "changed": changed, "note": note})
    return {"before": before, "after": count, "changed": changed}


def upsert_resource(db: Session, area_id: str, data: dict, actor: Actor, import_id: str | None = None) -> Resource:
    rtype = data["resource_type"]
    if rtype not in RESOURCE_TYPES:
        raise ArgusError("invalid_resource_type", f"Resource type must be one of {RESOURCE_TYPES}")
    r = db.get(Resource, data["id"])
    created = r is None
    if r is None:
        r = Resource(id=data["id"], area_id=area_id)
        db.add(r)
    elif r.area_id != area_id:
        raise ArgusError("resource_in_other_area", "Resource id already used in another area")
    r.resource_type = rtype
    r.subtype = data.get("subtype") or "GENERIC"
    r.capacity = data.get("capacity")
    r.capacity_unit = data.get("capacity_unit")
    r.base_id = data.get("base_id")
    r.name_kk, r.name_ru, r.name_en = data.get("name_kk"), data.get("name_ru"), data.get("name_en")
    r.name_original = data.get("name_original") or r.name_original
    r.attributes = data.get("attributes") or {}
    r.source = data.get("source") or "MANUAL"
    r.import_id = import_id
    db.flush()
    if db.get(ResourceStatus, r.id) is None:
        db.add(ResourceStatus(resource_id=r.id, status=data.get("status") or "AVAILABLE", updated_by=actor.username,
                              updated_at=operational_now(db, area_id)))
    record(db, actor, "RESOURCE_CREATED" if created else "RESOURCE_UPDATED", "resource", r.id,
           f"{r.id} ({rtype}/{r.subtype}) {'added' if created else 'updated'}", area_id=area_id, affects_results=True,
           details={k: v for k, v in data.items() if k != "attributes"})
    return r


def add_facility(db: Session, area_id: str, data: dict, actor: Actor, import_id: str | None = None) -> CriticalFacility:
    ftype = data["facility_type"]
    if ftype not in FACILITY_TYPES:
        raise ArgusError("invalid_facility_type", f"Facility type must be one of {FACILITY_TYPES}")
    area = db.get(OperationalArea, area_id)
    lon, lat = float(data["lon"]), float(data["lat"])
    if area and not (area.bbox[0] <= lon <= area.bbox[2] and area.bbox[1] <= lat <= area.bbox[3]):
        raise ArgusError("outside_area", "Facility location is outside the operational area")
    fid = data.get("id") or new_id("F-")
    if db.get(CriticalFacility, fid) is not None:
        raise ArgusError("duplicate_facility", f"Facility id {fid} already exists")
    f = CriticalFacility(id=fid, area_id=area_id, facility_type=ftype, geom=Point(lon, lat),
                         criticality=int(data.get("criticality", 50)), population_served=int(data.get("population_served", 0)),
                         sector_id=data.get("sector_id"), source=data.get("source") or "MANUAL",
                         verification=data.get("verification") or "UNVERIFIED", created_by=actor.username,
                         name_kk=data.get("name_kk"), name_ru=data.get("name_ru"), name_en=data.get("name_en"),
                         name_original=data.get("name_original") or data.get("name_ru") or data.get("name_kk") or data.get("name_en"),
                         import_id=import_id)
    db.add(f)
    db.flush()
    if area:
        area.config = {**(area.config or {}), "static_version": int((area.config or {}).get("static_version", 1)) + 1}
    invalidate_static(area_id)
    record(db, actor, "FACILITY_ADDED", "critical_facility", f.id, f"{f.id} ({ftype}) added", area_id=area_id,
           affects_results=True, details={k: v for k, v in data.items()})
    return f
