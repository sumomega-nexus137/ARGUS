"""Imports, audit, admin/system, tiles."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user, require
from app.api.serialize import clean
from app.core.config import get_settings, resolve_data_path
from app.core.errors import ArgusError, Conflict, NotFound
from app.core.security import Permission
from app.db.session import get_db
from app.models import AuditLog, ImportJob, ModelVersion, OperationalArea, User
from app.providers.terrain import dem_tile
from app.schemas.common import OutageToggle
from app.services.audit import Actor, record
from app.services.ingest import imports as imp
from app.services.ingest.providers import outage_enabled, poll_once, set_outage
from app.services.operations.pipeline import run_pipeline

router = APIRouter(tags=["system"])
MAX_UPLOAD = 10 * 1024 * 1024


def _job_out(j: ImportJob, with_rows: bool = True) -> dict:
    d = {"id": j.id, "area_id": j.area_id, "import_type": j.import_type, "filename": j.filename, "file_format": j.file_format,
         "status": j.status, "created_by": j.created_by, "created_at": j.created_at, "rows_total": j.rows_total,
         "rows_valid": j.rows_valid, "rows_invalid": j.rows_invalid, "rows_warning": j.rows_warning,
         "confirmed_at": j.confirmed_at, "applied_count": j.applied_count, "message": j.message,
         "failed_on_apply": _failed(j)}
    if with_rows:
        d["preview"] = j.preview
    return d


def _failed(j: ImportJob) -> list:
    try:
        return list(json.loads(j.message).get("failed_on_apply", [])) if j.message else []
    except (ValueError, AttributeError):
        return []


@router.post("/api/areas/{area_id}/imports")
async def upload(import_type: str, file: UploadFile = File(...), area: OperationalArea = Depends(area_or_404),
                 db: Session = Depends(get_db), actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise ArgusError("file_too_large", "Maximum upload size is 10 MB")
    if not content:
        raise ArgusError("empty_file", "The uploaded file is empty")
    job = imp.create_preview(db, area, import_type, file.filename or "upload", content, actor)
    db.commit()
    return clean(_job_out(job))


@router.get("/api/areas/{area_id}/imports")
def list_imports(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                 _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(ImportJob).where(ImportJob.area_id == area.id).order_by(ImportJob.created_at.desc()).limit(30))
    return clean([_job_out(j, with_rows=False) for j in rows])


@router.get("/api/imports/{job_id}")
def get_import(job_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    j = db.get(ImportJob, job_id)
    if j is None:
        raise NotFound("import", job_id)
    return clean(_job_out(j))


@router.post("/api/imports/{job_id}/confirm")
def confirm_import(job_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    j = db.get(ImportJob, job_id)
    if j is None:
        raise NotFound("import", job_id)
    imp.confirm(db, j, actor)
    pipe = run_pipeline(db, j.area_id, f"IMPORT_{j.import_type.upper()}", j.id, actor,
                        condition=j.import_type == "observations")
    db.commit()
    pipeline = {k: v for k, v in pipe.items() if k != "health"} | {"plan_status": (pipe.get("health") or {}).get("status")}
    return clean({**_job_out(j, with_rows=False), "pipeline": pipeline})


@router.post("/api/imports/{job_id}/cancel")
def cancel_import(job_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    j = db.get(ImportJob, job_id)
    if j is None:
        raise NotFound("import", job_id)
    if j.status != "PREVIEW":
        raise Conflict("import_not_in_preview", "Only previews can be cancelled")
    j.status = "CANCELLED"
    record(db, actor, "IMPORT_CANCELLED", "import", j.id, f"Import {j.filename} cancelled", area_id=j.area_id)
    db.commit()
    return clean(_job_out(j, with_rows=False))


@router.get("/api/imports/templates/{import_type}.csv")
def template(import_type: str) -> Response:
    return Response(content=imp.template_csv(import_type), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="argus_{import_type}_template.csv"'})


@router.get("/api/audit")
def audit(area_id: str | None = None, action: str | None = None, affects_results: bool | None = None, limit: int = 200,
          db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 1000))
    if area_id:
        q = q.where(AuditLog.area_id == area_id)
    if action:
        q = q.where(AuditLog.action == action)
    if affects_results is not None:
        q = q.where(AuditLog.affects_results.is_(affects_results))
    return clean([{"id": r.id, "ts": r.ts, "op_time": r.op_time, "username": r.username, "role": r.role, "action": r.action,
                   "entity_type": r.entity_type, "entity_id": r.entity_id, "area_id": r.area_id, "summary": r.summary,
                   "details": r.details, "data_version": r.data_version, "affects_results": r.affects_results}
                  for r in db.scalars(q)])


@router.get("/api/admin/users")
def users(db: Session = Depends(get_db), _: Actor = Depends(require(Permission.USER_ADMIN))) -> list[dict]:
    return clean([{"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role, "active": u.active,
                   "created_at": u.created_at} for u in db.scalars(select(User).order_by(User.id))])


@router.get("/api/policies")
def policies(_: User = Depends(current_user)) -> dict:
    """Default weight presets and value-model assumptions. The weights actually used are always chosen by a human."""
    from app.services.optimization.value import BENEFIT_SHARE, POLICIES

    return {"policies": POLICIES, "benefit_share": BENEFIT_SHARE, "default": "BALANCED"}


@router.get("/api/admin/model-versions")
def model_versions(db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    return clean([{"id": m.id, "component": m.component, "version": m.version, "description": m.description,
                   "active": m.active, "activated_at": m.activated_at}
                  for m in db.scalars(select(ModelVersion).order_by(ModelVersion.component))])


@router.post("/api/admin/providers/outage")
def outage(body: OutageToggle, db: Session = Depends(get_db), actor: Actor = Depends(require(Permission.DATA_ADMIN))) -> dict:
    n = set_outage(db, body.enabled, actor)
    db.commit()
    return {"external_offline": outage_enabled(), "providers": n}


@router.post("/api/admin/demo/reset")
def demo_reset(actor: Actor = Depends(require(Permission.USER_ADMIN))) -> dict:
    """Restore the DEMO dataset to its initial state (demo mode only). Everything, including the audit trail, is reset."""
    from app.db.init import reset_demo

    if not get_settings().demo_mode:
        raise Conflict("not_demo", "Reset is only available in demo mode")
    ok = reset_demo()
    from app.db.session import session_scope

    with session_scope() as db:
        record(db, actor, "DEMO_RESET", "system", "demo", "DEMO dataset restored to its initial state")
    return {"reset": ok}


@router.post("/api/admin/providers/poll")
def poll(db: Session = Depends(get_db), _: Actor = Depends(require(Permission.DATA_ADMIN))) -> dict:
    res = poll_once(db)
    db.commit()
    return {"results": res}


@router.get("/api/system/health")
def health(db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unavailable",
            "dialect": "sqlite" if s.is_sqlite else "postgresql", "demo_mode": s.demo_mode,
            "external_offline": outage_enabled(), "version": "0.1.0", "app": s.app_name}


@router.get("/api/tiles/terrain/{area_id}/{z}/{x}/{y}.png")
def terrain_tile(z: int, x: int, y: int, area: OperationalArea = Depends(area_or_404)) -> Response:
    """Terrarium DEM tiles (static terrain, non-sensitive) for MapLibre 3D terrain & hillshade."""
    if not (0 <= z <= 16):
        raise ArgusError("invalid_zoom")
    cfg = area.config or {}
    path = cfg.get("dem_path")
    s = get_settings()
    dem = resolve_data_path(path) if path else (s.demo_dir / area.id / "terrain" / "dem.tif")
    if not dem.exists():
        raise NotFound("terrain", area.id)
    return Response(content=dem_tile(dem, z, x, y), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})
