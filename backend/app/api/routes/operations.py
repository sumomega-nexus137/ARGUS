"""Operations Board (Module 5) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user, require
from app.api.routes.plans import version_out
from app.api.serialize import clean
from app.core.errors import ArgusError, NotFound
from app.core.security import Permission
from app.db.session import get_db
from app.models import AuditLog, OperationalArea, PipelineRun, PlanTask, PlanVersion, User
from app.repositories.context import load_context
from app.schemas.common import RecomputeRequest, TaskStatusUpdate
from app.services.audit import Actor
from app.services.operations.lifecycle import update_task_status
from app.services.operations.pipeline import run_pipeline
from app.services.operations.recompute import recompute
from app.services.planning.health import plan_health
from app.services.planning.plans import active_version

router = APIRouter(tags=["operations"])

EVENT_ACTIONS = ("ROAD_CLOSED", "ROAD_RESTRICTED", "ROAD_OPENED", "RESOURCE_FAILED", "RESOURCE_DELAYED", "RESOURCE_CHANGED",
                 "RESOURCE_POOL_CHANGED", "SCENARIO_UPDATED", "OBSERVATION_ENTERED", "DATA_CONFLICT_RESOLVED",
                 "TASK_STATUS_CHANGED", "PLAN_ACTIVATED", "PLAN_VERSION_CREATED", "FACILITY_ADDED", "ROAD_EVENT_CLEARED")


@router.get("/api/areas/{area_id}/operations")
def board(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    ctx = load_context(db, area.id)
    pv = active_version(db, area.id)
    health = plan_health(db, ctx, pv) if pv else None
    pending = db.scalars(select(PlanVersion).where(PlanVersion.area_id == area.id,
                                                   PlanVersion.status.in_(("DRAFT", "REVIEWED", "APPROVED")))
                         .order_by(PlanVersion.created_at.desc())).all()
    events = db.scalars(select(AuditLog).where(AuditLog.area_id == area.id, AuditLog.action.in_(EVENT_ACTIONS))
                        .order_by(AuditLog.id.desc()).limit(25)).all()
    last_pipe = db.scalars(select(PipelineRun).where(PipelineRun.area_id == area.id)
                           .order_by(PipelineRun.started_at.desc())).first()
    resources = [{"id": r.id, "type": r.type, "subtype": r.subtype, "base": r.base, "status": r.status,
                  "delay_min": r.delay_min, "capacity": r.capacity, "unit": r.unit, "note": r.note}
                 for r in ctx.resources.values()]
    if health:
        busy = {rid: t["code"] for t in health["evaluation"]["tasks"] for rid in t["resource_ids"]
                if t["status"] not in ("DONE",)}
        for r in resources:
            r["assigned_task"] = busy.get(r["id"])
    return clean({
        "active_version": version_out(db, pv) if pv else None, "health": health,
        "pending_versions": [version_out(db, v, with_tasks=False) for v in pending],
        "resources": resources,
        "events": [{"id": e.id, "ts": e.ts, "op_time": e.op_time, "username": e.username, "role": e.role,
                    "action": e.action, "entity_id": e.entity_id, "summary": e.summary} for e in events],
        "last_pipeline": None if last_pipe is None else {"id": last_pipe.id, "trigger": last_pipe.trigger,
                                                          "outcome": last_pipe.outcome, "steps": last_pipe.steps,
                                                          "started_at": last_pipe.started_at},
        "data_version": area.data_version,
    })


@router.post("/api/plan-tasks/{task_id}/status")
def task_status(task_id: str, body: TaskStatusUpdate, db: Session = Depends(get_db),
                actor: Actor = Depends(require(Permission.FIELD_UPDATE))) -> dict:
    t = db.get(PlanTask, task_id)
    if t is None:
        raise NotFound("plan task", task_id)
    update_task_status(db, t, body.status, actor, body.note)
    pv = db.get(PlanVersion, t.plan_version_id)
    pipe = run_pipeline(db, pv.area_id, "TASK_STATUS_CHANGED", t.code, actor) if pv else None
    db.commit()
    return clean({"task_id": t.id, "code": t.code, "status": t.status,
                  "pipeline": None if pipe is None else {k: v for k, v in pipe.items() if k != "health"}})


@router.post("/api/areas/{area_id}/recompute")
def do_recompute(body: RecomputeRequest, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                 actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    pv = active_version(db, area.id)
    if pv is None:
        raise ArgusError("no_active_plan", "There is no ACTIVE plan version to recompute")
    res = recompute(db, load_context(db, area.id), pv, actor, body.policy, body.weights)
    db.commit()
    return clean({"plan_version": version_out(db, res["plan_version"]), "optimization_run_id": res["optimization_run"].id,
                  "chosen_alternative": res["chosen"], "label": res["label"], "health_before": res["health_before"]})


@router.get("/api/areas/{area_id}/pipeline-runs")
def pipelines(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
              _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(PipelineRun).where(PipelineRun.area_id == area.id).order_by(PipelineRun.started_at.desc()).limit(20))
    return clean([{"id": r.id, "trigger": r.trigger, "trigger_ref": r.trigger_ref, "outcome": r.outcome, "steps": r.steps,
                   "started_at": r.started_at, "data_version": r.data_version, "created_by": r.created_by} for r in rows])
