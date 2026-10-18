"""Plans (Module 4 human plan builder, stress tester, optimizer) and lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user, require
from app.api.serialize import clean
from app.core.errors import ArgusError, NotFound
from app.core.security import Permission
from app.db.session import get_db
from app.models import OperationalArea, OptimizationRun, Plan, PlanTask, PlanVersion, StressTestRun, User
from app.repositories.context import load_context
from app.schemas.common import (
    AdoptRequest,
    ConstraintsUpdate,
    NewVersionRequest,
    OptimizeRequest,
    PlanCreate,
    TaskIn,
    TasksReplace,
    TransitionRequest,
)
from app.services.audit import Actor
from app.services.operations.lifecycle import (
    create_plan,
    new_version,
    replace_draft_tasks,
    transition,
    update_constraints,
)
from app.services.operations.recompute import adopt_alternative, run_alternatives, run_gap, run_stress
from app.services.planning.health import plan_health
from app.services.planning.plans import evaluate_version, get_version, version_tasks

router = APIRouter(tags=["plans"])


def task_out(t: PlanTask) -> dict:
    return {"id": t.id, "code": t.code, "template_id": t.template_id, "site_id": t.site_id, "resource_ids": t.resource_ids,
            "planned_departure": t.planned_departure, "dependencies": t.dependencies, "notes": t.notes, "status": t.status,
            "status_updated_at": t.status_updated_at, "status_updated_by": t.status_updated_by,
            "actual_departure": t.actual_departure, "actual_start": t.actual_start, "completed_at": t.completed_at,
            "sort_order": t.sort_order, "rationale": t.rationale}


def version_out(db: Session, pv: PlanVersion, with_tasks: bool = True) -> dict:
    plan = db.get(Plan, pv.plan_id)
    d = {"id": pv.id, "plan_id": pv.plan_id, "plan_name": plan.name if plan else pv.plan_id, "area_id": pv.area_id,
         "version": pv.version, "status": pv.status, "origin": pv.origin, "basis_scenario_id": pv.basis_scenario_id,
         "basis_data_version": pv.basis_data_version, "policy": pv.policy, "weights": pv.weights,
         "constraints": pv.constraints, "change_summary": pv.change_summary, "parent_version_id": pv.parent_version_id,
         "optimization_run_id": pv.optimization_run_id, "created_by": pv.created_by, "created_at": pv.created_at,
         "reviewed_by": pv.reviewed_by, "reviewed_at": pv.reviewed_at, "approved_by": pv.approved_by,
         "approved_at": pv.approved_at, "activated_at": pv.activated_at, "superseded_at": pv.superseded_at, "notes": pv.notes}
    if with_tasks:
        d["tasks"] = [task_out(t) for t in version_tasks(db, pv)]
    return d


def _tasks_in(tasks: list[TaskIn]) -> list[dict]:
    return [{**t.model_dump(), "sort_order": i} for i, t in enumerate(tasks)]


@router.get("/api/areas/{area_id}/plans")
def list_plans(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
               _: User = Depends(current_user)) -> list[dict]:
    plans = db.scalars(select(Plan).where(Plan.area_id == area.id).order_by(Plan.created_at)).all()
    out = []
    for p in plans:
        versions = db.scalars(select(PlanVersion).where(PlanVersion.plan_id == p.id).order_by(PlanVersion.version)).all()
        out.append({"id": p.id, "name": p.name, "description": p.description, "created_by": p.created_by,
                    "versions": [version_out(db, v, with_tasks=False) for v in versions]})
    return clean(out)


@router.post("/api/areas/{area_id}/plans")
def create(body: PlanCreate, area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
           actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    pv = create_plan(db, area.id, body.name, body.description, _tasks_in(body.tasks), actor)
    db.commit()
    return clean(version_out(db, pv))


@router.get("/api/plan-versions/{version_id}")
def get_pv(version_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    return clean(version_out(db, get_version(db, version_id)))


@router.put("/api/plan-versions/{version_id}/tasks")
def put_tasks(version_id: str, body: TasksReplace, db: Session = Depends(get_db),
              actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    pv = replace_draft_tasks(db, get_version(db, version_id), _tasks_in(body.tasks), actor)
    db.commit()
    return clean(version_out(db, pv))


@router.post("/api/plan-versions/{version_id}/versions")
def fork(version_id: str, body: NewVersionRequest, db: Session = Depends(get_db),
         actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    parent = get_version(db, version_id)
    if body.tasks is not None:
        tasks = _tasks_in(body.tasks)
    else:
        tasks = [{**task_out(t), "status": "PENDING"} for t in version_tasks(db, parent)]
    pv = new_version(db, parent, tasks, actor, origin="HUMAN",
                     change_summary={"from_version": parent.version, "note": body.note or "Manual revision"})
    db.commit()
    return clean(version_out(db, pv))


@router.post("/api/plan-versions/{version_id}/transition")
def do_transition(version_id: str, body: TransitionRequest, db: Session = Depends(get_db),
                  user: User = Depends(current_user)) -> dict:
    pv = transition(db, get_version(db, version_id), body.target, Actor(user.username, user.role), body.note)
    db.commit()
    return clean(version_out(db, pv))


@router.put("/api/plan-versions/{version_id}/constraints")
def put_constraints(version_id: str, body: ConstraintsUpdate, db: Session = Depends(get_db),
                    actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    pv = update_constraints(db, get_version(db, version_id), [c.model_dump() for c in body.constraints], actor)
    db.commit()
    return clean(version_out(db, pv))


@router.get("/api/plan-versions/{version_id}/evaluate")
def evaluate(version_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    pv = get_version(db, version_id)
    ctx = load_context(db, pv.area_id)
    ev, rt = evaluate_version(db, ctx, pv)
    return clean({**ev.as_dict(), "reference_time": rt.reference_time, "scenario_id": rt.id})


@router.get("/api/plan-versions/{version_id}/health")
def health(version_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    pv = get_version(db, version_id)
    return clean(plan_health(db, load_context(db, pv.area_id), pv))


@router.post("/api/plan-versions/{version_id}/stress-test")
def stress(version_id: str, db: Session = Depends(get_db), actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    pv = get_version(db, version_id)
    run = run_stress(db, load_context(db, pv.area_id), pv, actor)
    db.commit()
    return clean({"id": run.id, "created_at": run.created_at, "data_version": run.data_version, **run.result})


@router.get("/api/plan-versions/{version_id}/stress-tests")
def stress_list(version_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(StressTestRun).where(StressTestRun.plan_version_id == version_id)
                      .order_by(StressTestRun.created_at.desc())).all()
    return clean([{"id": r.id, "created_at": r.created_at, "created_by": r.created_by, "n_scenarios": r.n_scenarios,
                   "n_feasible": r.n_feasible, "robustness": r.robustness, "scenario_id": r.scenario_id,
                   "data_version": r.data_version} for r in rows])


@router.get("/api/stress-tests/{run_id}")
def stress_get(run_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    r = db.get(StressTestRun, run_id)
    if r is None:
        raise NotFound("stress test", run_id)
    return clean({"id": r.id, "created_at": r.created_at, "data_version": r.data_version, **r.result})


@router.post("/api/plan-versions/{version_id}/alternatives")
def alternatives(version_id: str, body: OptimizeRequest, db: Session = Depends(get_db),
                 actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    pv = get_version(db, version_id)
    run = run_alternatives(db, load_context(db, pv.area_id), pv, policy=body.policy, weights=body.weights,
                           extra_constraints=[c.model_dump() for c in body.extra_constraints],
                           what_if_unavailable=body.what_if_unavailable, actor=actor)
    db.commit()
    return clean({"id": run.id, "created_at": run.started_at, "status": run.status, "data_version": run.data_version,
                  **run.result})


@router.post("/api/plan-versions/{version_id}/resource-gap")
def gap(version_id: str, body: OptimizeRequest, db: Session = Depends(get_db),
        actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    pv = get_version(db, version_id)
    run = run_gap(db, load_context(db, pv.area_id), pv, policy=body.policy, weights=body.weights, actor=actor,
                  what_if_unavailable=body.what_if_unavailable)
    db.commit()
    return clean({"id": run.id, "created_at": run.started_at, "status": run.status, "data_version": run.data_version,
                  **run.result})


@router.get("/api/optimization-runs/{run_id}")
def opt_get(run_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    r = db.get(OptimizationRun, run_id)
    if r is None:
        raise NotFound("optimization run", run_id)
    return clean({"id": r.id, "kind": r.kind, "created_at": r.started_at, "status": r.status, "policy": r.policy,
                  "plan_version_id": r.plan_version_id, "scenario_id": r.scenario_id, "data_version": r.data_version,
                  **r.result})


@router.get("/api/areas/{area_id}/optimization-runs")
def opt_list(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
             _: User = Depends(current_user)) -> list[dict]:
    rows = db.scalars(select(OptimizationRun).where(OptimizationRun.area_id == area.id)
                      .order_by(OptimizationRun.started_at.desc()).limit(30)).all()
    return clean([{"id": r.id, "kind": r.kind, "created_at": r.started_at, "status": r.status, "policy": r.policy,
                   "plan_version_id": r.plan_version_id, "created_by": r.created_by, "duration_s": r.duration_s,
                   "data_version": r.data_version,
                   "alternatives": len(r.result.get("alternatives", [])) if r.kind != "RESOURCE_GAP" else None}
                  for r in rows])


@router.post("/api/optimization-runs/{run_id}/adopt")
def adopt(run_id: str, body: AdoptRequest, db: Session = Depends(get_db),
          actor: Actor = Depends(require(Permission.PLAN_EDIT))) -> dict:
    r = db.get(OptimizationRun, run_id)
    if r is None:
        raise NotFound("optimization run", run_id)
    if r.kind == "RESOURCE_GAP":
        raise ArgusError("not_adoptable", "Resource-gap runs cannot be adopted as plans")
    pv = adopt_alternative(db, r, body.alternative_id, actor)
    db.commit()
    return clean(version_out(db, pv))


@router.get("/api/plans/{plan_id}/compare")
def compare(plan_id: str, a: str, b: str, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    va, vb = get_version(db, a), get_version(db, b)
    if va.plan_id != plan_id or vb.plan_id != plan_id:
        raise ArgusError("version_plan_mismatch", "Both versions must belong to the plan")
    ta = {t.code: t for t in version_tasks(db, va)}
    tb = {t.code: t for t in version_tasks(db, vb)}
    rows = []
    for code in sorted(set(ta) | set(tb)):
        x, y = ta.get(code), tb.get(code)
        change = "ADDED" if x is None else "REMOVED" if y is None else "UNCHANGED"
        if x is not None and y is not None:
            if set(x.resource_ids) != set(y.resource_ids):
                change = "REASSIGNED"
            elif (x.planned_departure or 0) != (y.planned_departure or 0):
                change = "RETIMED"
        rows.append({"code": code, "change": change, "a": task_out(x) if x else None, "b": task_out(y) if y else None})
    return clean({"a": version_out(db, va, with_tasks=False), "b": version_out(db, vb, with_tasks=False), "tasks": rows})
