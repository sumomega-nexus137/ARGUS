from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user, require
from app.api.serialize import clean
from app.core.errors import ArgusError
from app.core.security import Permission
from app.db.session import get_db
from app.models import Observation, OperationalArea, Scenario, User
from app.repositories.context import load_context
from app.schemas.common import MemberSelect
from app.services.audit import Actor
from app.services.clock import area_now, to_minutes
from app.services.ingest.authority import authority_label, authority_rank
from app.services.ingest.observations import effective_observations
from app.services.operations.pipeline import run_pipeline
from app.services.scenario.conditioning import select_member_manually
from app.services.scenario.render import depth_png, extent_geojson, frame_stats
from app.services.scenario.runtime import current_scenario, get_scenario, runtime_for

router = APIRouter(tags=["scenarios"])


def scenario_payload(s: Scenario, area: OperationalArea) -> dict:
    rt = runtime_for(s)
    now_min = to_minutes(s.reference_time, area_now(area))
    grid = rt.provider.grid()
    frames = [{"index": i, "offset_min": off, "kind": "ANALYSIS" if off <= now_min else "FORECAST"}
              for i, off in enumerate(s.frame_offsets_min)]
    members = [{"id": m.id, "label": m.label, "peak_stage_cm": m.peak_stage_cm, "peak_offset_h": m.peak_offset_h}
               for m in rt.provider.members()]
    return {
        "id": s.id, "area_id": s.area_id, "family_id": s.family_id, "version": s.version, "name": s.name, "mode": s.mode,
        "created_at": s.created_at, "reference_time": s.reference_time, "source": s.source, "provider": s.provider,
        "provider_note": rt.provider.mode_note, "frame_offsets_min": s.frame_offsets_min, "frames": frames,
        "now_min": now_min, "active_member": s.active_member_id, "members": members, "members_order": rt.members_order,
        "selection": s.selection, "uncertainty": s.uncertainty, "provenance": s.provenance,
        "model_version": s.model_version, "is_current": s.is_current, "parent_id": s.parent_id, "reason": s.reason,
        "image_corners": grid.corners_lonlat(), "parameters": s.parameters,
    }


@router.get("/api/areas/{area_id}/scenario")
def get_current(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                _: User = Depends(current_user)) -> dict:
    return clean(scenario_payload(current_scenario(db, area.id), area))


@router.get("/api/areas/{area_id}/scenarios")
def list_versions(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                  _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(Scenario).where(Scenario.area_id == area.id).order_by(Scenario.version.desc())).all()
    return clean([{"id": s.id, "version": s.version, "name": s.name, "mode": s.mode, "created_at": s.created_at,
                   "active_member": s.active_member_id, "is_current": s.is_current, "reason": s.reason,
                   "selection_method": (s.selection or {}).get("method"), "created_by": s.created_by} for s in rows])


def _member(s: Scenario, member: str | None) -> str:
    m = member or s.active_member_id
    if m not in {x["id"] for x in s.members}:
        raise ArgusError("unknown_member", f"Unknown ensemble member {m}")
    return m


@router.get("/api/scenarios/{scenario_id}/frames/{offset_min}/depth.png")
def frame_png(scenario_id: str, offset_min: float, member: str | None = None, db: Session = Depends(get_db),
              _: User = Depends(current_user)) -> Response:
    s = get_scenario(db, scenario_id)
    data = depth_png(runtime_for(s), _member(s, member), offset_min)
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, max-age=600",
                                                                   "X-Argus-Mode": s.mode})


@router.get("/api/scenarios/{scenario_id}/frames/{offset_min}/extent")
def frame_extent(scenario_id: str, offset_min: float, member: str | None = None, db: Session = Depends(get_db),
                 _: User = Depends(current_user)) -> dict:
    s = get_scenario(db, scenario_id)
    out = extent_geojson(runtime_for(s), _member(s, member), offset_min)
    return {**out, "mode": s.mode}


@router.get("/api/scenarios/{scenario_id}/stats")
def stats(scenario_id: str, member: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    s = get_scenario(db, scenario_id)
    return clean({"scenario_id": s.id, "member": _member(s, member), "frames": frame_stats(runtime_for(s), _member(s, member))})


@router.get("/api/areas/{area_id}/hydrograph")
def hydrograph(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
               _: User = Depends(current_user)) -> dict:
    s = current_scenario(db, area.id)
    rt = runtime_for(s)
    ctx = load_context(db, area.id)
    now = area_now(area)
    stations = []
    for sid, st in ctx.stations.items():
        eff, excluded = effective_observations(db, sid, until=None)
        eff_ids = {e.obs.id for e in eff}
        conflict_of = {e.obs.id: (e.conflict_id, e.conflict_status) for e in eff}
        all_obs = db.scalars(select(Observation).where(Observation.station_id == sid).order_by(Observation.observed_at)).all()
        obs = []
        for o in all_obs:
            obs.append({"id": o.id, "t_min": to_minutes(s.reference_time, o.observed_at), "observed_at": o.observed_at,
                        "stage_cm": o.water_level_cm, "source": o.source, "source_type": o.source_type,
                        "verification": o.verification, "authority": authority_label(o.source_type, o.verification),
                        "rank": authority_rank(o.source_type, o.verification), "effective": o.id in eff_ids,
                        "excluded": o.id in excluded, "conflict": conflict_of.get(o.id, (None, None))[0], "mode": o.mode,
                        "future": o.observed_at > now, "quality": o.quality, "notes": o.notes})
        is_proxy = sid == (s.parameters or {}).get("station_id")
        envelope = ((s.uncertainty or {}).get("envelope") or []) if is_proxy else []
        series = {}
        for m in (rt.members_order if is_proxy else []):
            pts = rt.provider.gauge_series(m)
            series[m] = [[t, round(v, 1)] for t, v in pts if abs(t % 30) < 1e-6]
        env_lo = env_hi = None
        if envelope:
            arr = np.array([[v for _, v in series[m]] for m in envelope])
            ts = [t for t, _ in series[envelope[0]]]
            env_lo = [[t, round(float(v), 1)] for t, v in zip(ts, arr.min(axis=0), strict=True)]
            env_hi = [[t, round(float(v), 1)] for t, v in zip(ts, arr.max(axis=0), strict=True)]
        stations.append({"station_id": sid, "names": st["names"], "thresholds": {k: st[k] for k in ("bankfull", "watch", "warning", "critical")},
                         "observations": obs, "members": series, "active_member": s.active_member_id,
                         "scenario_station": is_proxy, "provider": st.get("provider"),
                         "envelope": envelope, "envelope_low": env_lo, "envelope_high": env_hi})
    return clean({"scenario_id": s.id, "reference_time": s.reference_time, "now_min": to_minutes(s.reference_time, now),
                  "stations": stations, "mode": s.mode})


@router.post("/api/areas/{area_id}/scenario/select-member")
def select_member(body: MemberSelect, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                  actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    s = current_scenario(db, area.id)
    _member(s, body.member_id)
    if body.member_id == s.active_member_id:
        raise ArgusError("member_already_active", "This member is already active")
    new = select_member_manually(db, s, body.member_id, body.note, actor, body.lock)
    pipe = run_pipeline(db, area.id, "FORECAST_CHANGED", new.id, actor)
    db.commit()
    return clean({"scenario": scenario_payload(new, area), "pipeline": {k: v for k, v in pipe.items() if k != "health"}})


@router.post("/api/areas/{area_id}/scenario/condition")
def condition(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
              actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    pipe = run_pipeline(db, area.id, "CONDITIONING_REQUESTED", None, actor, condition=True)
    db.commit()
    return clean({k: v for k, v in pipe.items() if k != "health"})
