"""Validation & After-Action (Module 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user, require
from app.api.serialize import clean
from app.core.errors import ArgusError, NotFound
from app.core.security import Permission
from app.db.base import new_id
from app.db.session import get_db
from app.models import OperationalArea, User, ValidationRun
from app.services.audit import Actor, record
from app.services.clock import area_now, to_minutes
from app.services.scenario.runtime import current_scenario, runtime_for
from app.services.validation import engine as V
from app.services.validation.after_action import after_action

router = APIRouter(tags=["validation"])


class RunValidation(BaseModel):
    dataset_id: str


def _register(area: OperationalArea) -> dict | None:
    """Point the validation engine at the installed real-data dataset for this area (if any)."""
    from app.core.config import resolve_data_path

    v = (area.config or {}).get("validation")
    if v and v.get("path"):
        V.register_dataset_dir(area.id, v["dataset_id"], resolve_data_path(v["path"]))
    return v


def _run_out(r: ValidationRun) -> dict:
    return {"id": r.id, "dataset_id": r.dataset_id, "kind": r.kind, "status": r.status, "created_at": r.created_at,
            "created_by": r.created_by, "metrics": r.metrics, "result": r.result}


@router.get("/api/areas/{area_id}/validation")
def status(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    v = _register(area)
    runs = db.scalars(select(ValidationRun).where(ValidationRun.area_id == area.id).order_by(ValidationRun.created_at.desc())).all()
    sc = current_scenario(db, area.id)
    rt = runtime_for(sc)
    info = None
    if v:
        info = {k: v.get(k) for k in ("dataset_id", "label", "observed_qc", "satellite", "mask_method", "model", "limitations")}
        info["has_qc_png"] = bool(v.get("qc_png"))
    return clean({"datasets": V.dataset_status(area.id), "runs": [_run_out(r) for r in runs],
                  "image_corners": rt.provider.grid().corners_lonlat(), "historical": info,
                  "note": "Metrics are computed only from supplied observed and modelled masks."})


def _cache_images(run_id: str, pair: V.MaskPair) -> None:
    _images[run_id] = {k: V.comparison_png(pair, k) for k in ("observed", "modelled", "difference")}
    _grids[run_id] = pair.grid.corners_lonlat()
    while len(_images) > 12:
        k = next(iter(_images))
        _images.pop(k, None)
        _grids.pop(k, None)


_images: dict[str, dict[str, bytes]] = {}
_grids: dict[str, list] = {}


@router.post("/api/areas/{area_id}/validation/run")
def run_real(body: RunValidation, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
             actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    v = _register(area)
    ds = next((d for d in V.dataset_status(area.id) if d["id"] == body.dataset_id), None)
    if ds is None:
        raise NotFound("validation dataset", body.dataset_id)
    if ds["status"] != "READY":
        raise ArgusError("validation_data_not_loaded", "Observed and modelled masks must both be supplied",
                         path=ds["path"], status=ds["status"])
    pair = V.load_pair(area.id, body.dataset_id)
    direct = V.metrics(pair)
    result = {"image_corners": pair.grid.corners_lonlat(), "dataset": ds, "direct_aoi": direct}
    m = direct
    if v and v.get("protocol") and v.get("dataset_id") == body.dataset_id:
        from app.core.config import resolve_data_path

        pm = V.protocol_metrics(V.dataset_dir(area.id, body.dataset_id), resolve_data_path(v["pack_root"]), v["protocol"])
        m = {**pm["holdout"], "cell_size_m": pm["grid_m"]}
        result.update({"label": v.get("label"), "protocol_metrics": pm, "observed_qc": v.get("observed_qc"),
                       "satellite": v.get("satellite"), "model": v.get("model"), "limitations": v.get("limitations", []),
                       "headline": "holdout"})
    run = ValidationRun(id=new_id("val-"), area_id=area.id, dataset_id=body.dataset_id, kind="REAL", status="COMPLETED",
                        metrics=m, result=result, created_by=actor.username)
    db.add(run)
    _cache_images(run.id, pair)
    record(db, actor, "VALIDATION_RUN", "validation_run", run.id, f"Validation {body.dataset_id}: IoU {m['iou']}",
           area_id=area.id, details={"metrics": m})
    db.commit()
    return clean(_run_out(run))


@router.post("/api/areas/{area_id}/validation/synthetic")
def run_synthetic(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                  actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    sc = current_scenario(db, area.id)
    rt = runtime_for(sc)
    now_min = to_minutes(rt.reference_time, area_now(area))
    t = min(rt.horizon_end, max(now_min, 0.0) + 360.0)
    obs_member = rt.member_shifted(1) if rt.member_shifted(1) != rt.member else rt.member_shifted(-1)
    pair = V.synthetic_pair(area.id, rt.provider, rt.member, obs_member, t)
    m = V.metrics(pair)
    run = ValidationRun(id=new_id("val-"), area_id=area.id, dataset_id="synthetic-self-test", kind="SYNTHETIC_SELF_TEST",
                        status="COMPLETED", metrics=m,
                        result={"image_corners": pair.grid.corners_lonlat(), "t_min": t, "model_member": rt.member,
                                "synthetic_observed_from": obs_member,
                                "warning": "SYNTHETIC SELF-TEST — verifies the metric pipeline only; not model skill."},
                        created_by=actor.username)
    db.add(run)
    _cache_images(run.id, pair)
    record(db, actor, "VALIDATION_SELF_TEST", "validation_run", run.id, "Synthetic validation self-test executed",
           area_id=area.id, details={"metrics": m})
    db.commit()
    return clean(_run_out(run))


@router.get("/api/validation-runs/{run_id}/layers/{layer}.png")
def layer_png(run_id: str, layer: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> Response:
    if layer not in ("observed", "modelled", "difference"):
        raise ArgusError("unknown_layer")
    imgs = _images.get(run_id)
    if imgs is None:
        run = db.get(ValidationRun, run_id)
        if run is None:
            raise NotFound("validation run", run_id)
        if run.kind == "REAL":
            a = db.get(OperationalArea, run.area_id)
            if a is not None:
                _register(a)
            _cache_images(run_id, V.load_pair(run.area_id, run.dataset_id))
        else:
            sc = current_scenario(db, run.area_id)
            rt = runtime_for(sc)
            _cache_images(run_id, V.synthetic_pair(run.area_id, rt.provider, run.result["model_member"],
                                                   run.result["synthetic_observed_from"], run.result["t_min"]))
        imgs = _images[run_id]
    return Response(content=imgs[layer], media_type="image/png")


@router.get("/api/areas/{area_id}/after-action")
def aar(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    return clean(after_action(db, area.id))


@router.get("/api/areas/{area_id}/validation/qc.png")
def qc_png(area: OperationalArea = Depends(area_or_404), _: User = Depends(current_user)) -> Response:
    """Satellite flood-mask QC figure shipped with the real-data pack (Sentinel-2 flood vs post-recession)."""
    from app.core.config import resolve_data_path

    v = (area.config or {}).get("validation") or {}
    if not v.get("qc_png"):
        raise NotFound("qc figure", area.id)
    p = resolve_data_path(v["pack_root"]) / v["qc_png"]
    if not p.exists():
        raise NotFound("qc figure", area.id)
    return Response(content=p.read_bytes(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
