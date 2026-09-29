"""Hydrological observations: validation, duplicates, conflicts, effective (authoritative) series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ArgusError, Conflict
from app.db.base import new_id
from app.models import DataConflict, HydroStation, Observation
from app.services.audit import Actor, record
from app.services.ingest.authority import SOURCE_TYPES, authority_rank

VERIFICATIONS = ("VERIFIED", "UNVERIFIED", "REJECTED")


@dataclass
class ObservationInput:
    station_id: str
    observed_at: datetime
    water_level_cm: float
    discharge_m3s: float | None
    source: str
    source_type: str
    verification: str
    notes: str | None = None
    mode: str = "LIVE"
    import_id: str | None = None


def validate_observation(db: Session, area_id: str, inp: ObservationInput) -> list[str]:
    errors: list[str] = []
    st = db.get(HydroStation, inp.station_id)
    if st is None or st.area_id != area_id:
        errors.append("unknown_station")
    if inp.source_type not in SOURCE_TYPES:
        errors.append("invalid_source_type")
    if inp.verification not in VERIFICATIONS:
        errors.append("invalid_verification")
    if not (-100 <= inp.water_level_cm <= 3000):
        errors.append("water_level_out_of_range")
    if inp.discharge_m3s is not None and not (0 <= inp.discharge_m3s <= 50000):
        errors.append("discharge_out_of_range")
    if inp.observed_at.tzinfo is None:
        errors.append("timestamp_without_timezone")
    if not inp.source.strip():
        errors.append("missing_source")
    return errors


def is_duplicate(db: Session, inp: ObservationInput) -> bool:
    q = select(Observation).where(
        Observation.station_id == inp.station_id,
        Observation.observed_at >= inp.observed_at - timedelta(minutes=1),
        Observation.observed_at <= inp.observed_at + timedelta(minutes=1),
        Observation.source == inp.source,
    )
    return any(abs(o.water_level_cm - inp.water_level_cm) < 0.5 for o in db.scalars(q))


def detect_conflicts(db: Session, obs: Observation) -> list[DataConflict]:
    s = get_settings()
    window = timedelta(minutes=s.observation_conflict_window_min)
    q = select(Observation).where(
        Observation.station_id == obs.station_id,
        Observation.id != obs.id,
        Observation.observed_at >= obs.observed_at - window,
        Observation.observed_at <= obs.observed_at + window,
        Observation.verification != "REJECTED",
    )
    created = []
    for other in db.scalars(q):
        if other.source == obs.source and other.source_type == obs.source_type:
            continue
        # compare at similar times only (rising limb): tolerance scales with the time gap
        gap_h = abs((other.observed_at - obs.observed_at).total_seconds()) / 3600
        diff = abs(other.water_level_cm - obs.water_level_cm)
        if diff <= s.observation_conflict_tolerance_cm + 12.0 * gap_h:
            continue
        existing = db.scalars(
            select(DataConflict).where(DataConflict.station_id == obs.station_id, DataConflict.status == "OPEN")
        ).all()
        if any({obs.id, other.id} <= set(c.observation_ids) for c in existing):
            continue
        c = DataConflict(
            id=new_id("cf-"), area_id=obs.area_id, kind="OBSERVATION", station_id=obs.station_id,
            observation_ids=[other.id, obs.id], difference=round(diff, 2), status="OPEN",
        )
        db.add(c)
        created.append(c)
    db.flush()
    return created


def add_observation(db: Session, area_id: str, inp: ObservationInput, actor: Actor) -> tuple[Observation, list[DataConflict]]:
    errors = validate_observation(db, area_id, inp)
    if errors:
        raise ArgusError("invalid_observation", "; ".join(errors), errors=errors)
    if is_duplicate(db, inp):
        raise Conflict("duplicate_observation", "An identical observation from this source already exists")
    obs = Observation(
        id=new_id("ob-"), area_id=area_id, station_id=inp.station_id, observed_at=inp.observed_at,
        water_level_cm=inp.water_level_cm, discharge_m3s=inp.discharge_m3s, source=inp.source,
        source_type=inp.source_type, verification=inp.verification, notes=inp.notes, mode=inp.mode,
        entered_by=actor.username, import_id=inp.import_id,
    )
    db.add(obs)
    db.flush()
    conflicts = detect_conflicts(db, obs)
    record(db, actor, "OBSERVATION_ENTERED", "observation", obs.id,
           f"{inp.station_id}: {inp.water_level_cm:.0f} cm ({inp.source_type}, {inp.verification})",
           area_id=area_id, affects_results=True,
           details={"station_id": inp.station_id, "water_level_cm": inp.water_level_cm, "source": inp.source,
                    "source_type": inp.source_type, "verification": inp.verification,
                    "observed_at": inp.observed_at.isoformat(), "conflicts": [c.id for c in conflicts]})
    for c in conflicts:
        record(db, actor, "DATA_CONFLICT_DETECTED", "data_conflict", c.id,
               f"{inp.station_id}: Δ {c.difference:.0f} cm between sources", area_id=area_id,
               details={"observation_ids": c.observation_ids})
    return obs, conflicts


def verify_observation(db: Session, obs: Observation, verification: str, actor: Actor, note: str | None) -> Observation:
    if verification not in VERIFICATIONS:
        raise ArgusError("invalid_verification")
    old = obs.verification
    obs.verification = verification
    record(db, actor, "OBSERVATION_VERIFIED", "observation", obs.id,
           f"{obs.station_id}: {old} → {verification}", area_id=obs.area_id, affects_results=True,
           details={"from": old, "to": verification, "note": note})
    return obs


def resolve_conflict(db: Session, conflict: DataConflict, selected_id: str, note: str | None, actor: Actor) -> DataConflict:
    if selected_id not in conflict.observation_ids:
        raise ArgusError("invalid_selection", "Selected observation is not part of this conflict")
    if conflict.status != "OPEN":
        raise Conflict("conflict_already_resolved", "Conflict already resolved")
    conflict.status = "RESOLVED"
    conflict.selected_observation_id = selected_id
    conflict.resolution_note = note
    conflict.resolved_by = actor.username
    from app.services.audit import operational_now

    conflict.resolved_at = operational_now(db, conflict.area_id)
    conflict.version += 1
    record(db, actor, "DATA_CONFLICT_RESOLVED", "data_conflict", conflict.id,
           f"Authoritative observation selected: {selected_id}", area_id=conflict.area_id, affects_results=True,
           details={"selected": selected_id, "note": note, "observation_ids": conflict.observation_ids})
    return conflict


@dataclass
class EffectiveObservation:
    obs: Observation
    rank: int
    conflict_id: str | None
    conflict_status: str | None


def effective_observations(db: Session, station_id: str, until: datetime | None = None) -> tuple[list[EffectiveObservation], list[str]]:
    """Authoritative observation series. Returns (effective, excluded_ids)."""
    q = select(Observation).where(Observation.station_id == station_id, Observation.verification != "REJECTED")
    if until is not None:
        q = q.where(Observation.observed_at <= until)
    obs = list(db.scalars(q.order_by(Observation.observed_at)))
    conflicts = list(db.scalars(select(DataConflict).where(DataConflict.station_id == station_id)))
    excluded: set[str] = set()
    conflict_of: dict[str, DataConflict] = {}
    by_id = {o.id: o for o in obs}
    for c in conflicts:
        members = [by_id[i] for i in c.observation_ids if i in by_id]
        for m in members:
            conflict_of[m.id] = c
        if c.status == "RESOLVED" and c.selected_observation_id:
            excluded.update(m.id for m in members if m.id != c.selected_observation_id)
        elif members:
            best = max(members, key=lambda o: (authority_rank(o.source_type, o.verification), o.observed_at))
            excluded.update(m.id for m in members if m.id != best.id)
    out = [
        EffectiveObservation(o, authority_rank(o.source_type, o.verification),
                             conflict_of[o.id].id if o.id in conflict_of else None,
                             conflict_of[o.id].status if o.id in conflict_of else None)
        for o in obs if o.id not in excluded
    ]
    return out, sorted(excluded)
