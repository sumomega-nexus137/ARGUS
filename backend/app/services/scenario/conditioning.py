"""Observation conditioning of a precomputed scenario ensemble.

ARGUS does not re-run physics when an observation arrives. It selects the precomputed ensemble
member most consistent with the latest *authoritative* observations (weighted by the data
authority hierarchy and recency) and records why. A planner may also select a member manually.
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.base import new_id
from app.models import Scenario
from app.services.audit import Actor, record
from app.services.clock import to_minutes
from app.services.ingest.observations import effective_observations
from app.services.scenario.runtime import provider_for

RECENCY_TAU_MIN = 120.0


def score_members(db: Session, s: Scenario, now: datetime) -> dict:
    station_id = (s.parameters or {}).get("station_id")
    prov = provider_for(s)
    issued = datetime.fromisoformat(s.parameters["issued_at"]) if s.parameters.get("issued_at") else s.reference_time
    eff, excluded = effective_observations(db, station_id, until=now)
    used = [e for e in eff if e.obs.observed_at >= issued]
    scores = []
    for m in prov.members():
        series = prov.gauge_series(m.id)
        ts = np.array([p[0] for p in series])
        ss = np.array([p[1] for p in series])
        sse, wsum = 0.0, 0.0
        for e in used:
            t = to_minutes(s.reference_time, e.obs.observed_at)
            sim = float(np.interp(t, ts, ss))
            w = (e.rank / 10.0) * math.exp(-max(0.0, to_minutes(e.obs.observed_at, now)) / RECENCY_TAU_MIN)
            sse += w * (sim - e.obs.water_level_cm) ** 2
            wsum += w
        rmse = math.sqrt(sse / wsum) if wsum > 0 else None
        scores.append({"member": m.id, "label": m.label, "weighted_rmse_cm": None if rmse is None else round(rmse, 2)})
    valid = [x for x in scores if x["weighted_rmse_cm"] is not None]
    best = min(valid, key=lambda x: x["weighted_rmse_cm"]) if valid else None
    envelope: list[str] = []
    if best:
        tol = max(3.0, best["weighted_rmse_cm"] * 0.75)
        envelope = [x["member"] for x in valid if x["weighted_rmse_cm"] <= best["weighted_rmse_cm"] + tol]
    return {
        "method": "OBSERVATION_CONDITIONING",
        "best_member": best["member"] if best else None,
        "scores": scores,
        "observations_used": [e.obs.id for e in used],
        "observations_excluded": excluded,
        "open_conflicts": sorted({e.conflict_id for e in used if e.conflict_id and e.conflict_status == "OPEN"}),
        "envelope": envelope,
        "recency_tau_min": RECENCY_TAU_MIN,
        "computed_at_op_time": now.isoformat(),
    }


def new_version(db: Session, base: Scenario, member: str, selection: dict, reason: str, actor: Actor,
                created_at: datetime | None = None) -> Scenario:
    version = (base.version or 0) + 1
    db.execute(update(Scenario).where(Scenario.family_id == base.family_id).values(is_current=False))
    s = Scenario(
        id=f"{base.family_id}-v{version}", area_id=base.area_id, family_id=base.family_id, version=version,
        name=f"{base.name.split(' · ')[0]} · v{version}", mode=base.mode, reference_time=base.reference_time,
        source=base.source, provider=base.provider, provider_config=base.provider_config,
        frame_offsets_min=base.frame_offsets_min, members=base.members, active_member_id=member,
        selection=selection, parameters=base.parameters, uncertainty={**(base.uncertainty or {}),
                                                                       "envelope": selection.get("envelope", [])},
        provenance={**(base.provenance or {}), "derived_from": base.id}, model_version=base.model_version,
        is_current=True, parent_id=base.id, reason=reason, created_by=actor.username,
    )
    if created_at is not None:
        s.created_at = created_at
    db.add(s)
    db.flush()
    record(db, actor, "SCENARIO_UPDATED", "scenario", s.id,
           f"Scenario v{base.version} → v{version}: member {base.active_member_id} → {member} ({reason})",
           area_id=base.area_id, affects_results=True,
           details={"from": base.id, "to": s.id, "from_member": base.active_member_id, "to_member": member,
                    "selection": selection})
    return s


def condition_current(db: Session, s: Scenario, now: datetime, actor: Actor) -> tuple[Scenario, dict, bool]:
    """Re-score members against authoritative observations; version the scenario if the best member changed."""
    sel = score_members(db, s, now)
    best = sel["best_member"]
    if best and best != s.active_member_id and not (s.selection or {}).get("manual_lock"):
        return new_version(db, s, best, sel, "OBSERVATION_CONDITIONING", actor), sel, True
    return s, sel, False


def select_member_manually(db: Session, s: Scenario, member: str, note: str, actor: Actor, lock: bool) -> Scenario:
    sel = {"method": "MANUAL", "best_member": member, "note": note, "manual_lock": lock, "by": actor.username,
           "envelope": (s.selection or {}).get("envelope", [])}
    return new_version(db, s, member, sel, "MANUAL_SELECTION", actor)


def new_family_id() -> str:
    return new_id("fam-")
