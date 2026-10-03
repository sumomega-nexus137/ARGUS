"""Plan lifecycle (DRAFT → REVIEWED → APPROVED → ACTIVE), versioning and task execution status.

Approved plans are never silently replaced: changes create a new version that must be approved by an
authorised human; previous versions are kept (SUPERSEDED) for comparison and after-action review.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ArgusError, Conflict, Forbidden, NotFound
from app.core.security import Permission, has_permission
from app.db.base import new_id
from app.models import Plan, PlanTask, PlanVersion, Resource, ResourceStatus
from app.services.audit import Actor, operational_now, record
from app.services.scenario.runtime import current_scenario

TRANSITIONS = {
    ("DRAFT", "REVIEWED"): Permission.PLAN_REVIEW,
    ("REVIEWED", "APPROVED"): Permission.PLAN_APPROVE,
    ("APPROVED", "ACTIVE"): Permission.PLAN_APPROVE,
    ("DRAFT", "REJECTED"): Permission.PLAN_REVIEW,
    ("REVIEWED", "REJECTED"): Permission.PLAN_APPROVE,
    ("REVIEWED", "DRAFT"): Permission.PLAN_EDIT,
}
TASK_STATUSES = ("PENDING", "EN_ROUTE", "WORKING", "DONE", "FAILED", "BLOCKED", "RESOURCE_UNAVAILABLE")


def resource_snapshot(db: Session, area_id: str) -> dict:
    rows = db.execute(select(Resource.id, ResourceStatus.status, ResourceStatus.delay_min)
                      .join(ResourceStatus, ResourceStatus.resource_id == Resource.id, isouter=True)
                      .where(Resource.area_id == area_id)).all()
    return {"statuses": {r[0]: {"status": r[1] or "AVAILABLE", "delay_min": r[2] or 0} for r in rows}}


def _next_version_no(db: Session, plan_id: str) -> int:
    return int(db.scalar(select(func.coalesce(func.max(PlanVersion.version), 0)).where(PlanVersion.plan_id == plan_id))) + 1


def _write_tasks(db: Session, pv: PlanVersion, tasks: list[dict]) -> None:
    for i, t in enumerate(tasks):
        db.add(PlanTask(
            id=new_id("pt-"), plan_version_id=pv.id, code=t["code"], template_id=t["template_id"], site_id=t["site_id"],
            resource_ids=list(t.get("resource_ids") or []), planned_departure=t.get("planned_departure"),
            dependencies=list(t.get("dependencies") or []), notes=t.get("notes"), sort_order=t.get("sort_order", i),
            rationale=t.get("rationale") or {}, status=t.get("status", "PENDING"),
            actual_departure=t.get("actual_departure"), actual_start=t.get("actual_start"),
            completed_at=t.get("completed_at"),
        ))
    db.flush()


def validate_tasks(tasks: list[dict]) -> None:
    codes = [t["code"] for t in tasks]
    if len(codes) != len(set(codes)):
        raise ArgusError("duplicate_task_code", "Task codes must be unique within a plan version")
    for t in tasks:
        for d in t.get("dependencies") or []:
            if d not in codes:
                raise ArgusError("unknown_dependency", f"Task {t['code']} depends on unknown task {d}", task=t["code"], dep=d)


def create_plan(db: Session, area_id: str, name: str, description: str | None, tasks: list[dict], actor: Actor) -> PlanVersion:
    validate_tasks(tasks)
    plan = Plan(id=new_id("plan-"), area_id=area_id, name=name, description=description, created_by=actor.username)
    db.add(plan)
    db.flush()
    sc = current_scenario(db, area_id)
    pv = PlanVersion(id=f"{plan.id}-v1", plan_id=plan.id, area_id=area_id, version=1, status="DRAFT", origin="HUMAN",
                     basis_scenario_id=sc.id, created_by=actor.username, change_summary={"note": "Initial version"})
    db.add(pv)
    db.flush()
    _write_tasks(db, pv, tasks)
    record(db, actor, "PLAN_CREATED", "plan_version", pv.id, f"{name} v1 created", area_id=area_id)
    return pv


def new_version(db: Session, parent: PlanVersion, tasks: list[dict], actor: Actor, *, origin: str, change_summary: dict,
                policy: str | None = None, weights: dict | None = None, constraints: list | None = None,
                optimization_run_id: str | None = None, notes: str | None = None) -> PlanVersion:
    validate_tasks(tasks)
    sc = current_scenario(db, parent.area_id)
    n = _next_version_no(db, parent.plan_id)
    pv = PlanVersion(
        id=f"{parent.plan_id}-v{n}", plan_id=parent.plan_id, area_id=parent.area_id, version=n, status="DRAFT",
        origin=origin, basis_scenario_id=sc.id, policy=policy, weights=weights or {},
        constraints=constraints if constraints is not None else list(parent.constraints or []),
        change_summary=change_summary, parent_version_id=parent.id, optimization_run_id=optimization_run_id,
        created_by=actor.username, notes=notes,
    )
    db.add(pv)
    db.flush()
    _write_tasks(db, pv, tasks)
    plan = db.get(Plan, parent.plan_id)
    record(db, actor, "PLAN_VERSION_CREATED", "plan_version", pv.id,
           f"{plan.name if plan else parent.plan_id} v{n} created ({origin}) from v{parent.version}", area_id=parent.area_id,
           details={"parent": parent.id, "origin": origin, "change_summary": change_summary})
    return pv


def replace_draft_tasks(db: Session, pv: PlanVersion, tasks: list[dict], actor: Actor) -> PlanVersion:
    if pv.status != "DRAFT":
        raise Conflict("version_not_editable", "Only DRAFT versions can be edited; create a new version instead")
    validate_tasks(tasks)
    for t in db.scalars(select(PlanTask).where(PlanTask.plan_version_id == pv.id)):
        db.delete(t)
    db.flush()
    _write_tasks(db, pv, tasks)
    record(db, actor, "PLAN_MODIFIED", "plan_version", pv.id, f"Draft tasks updated ({len(tasks)} tasks)", area_id=pv.area_id,
           details={"tasks": [t["code"] for t in tasks]})
    return pv


def update_constraints(db: Session, pv: PlanVersion, constraints: list[dict], actor: Actor) -> PlanVersion:
    old = list(pv.constraints or [])
    pv.constraints = [{**c, "author": c.get("author") or actor.username} for c in constraints]
    record(db, actor, "CONSTRAINT_CHANGED", "plan_version", pv.id, f"Human constraints updated ({len(constraints)})",
           area_id=pv.area_id, affects_results=True, details={"from": old, "to": pv.constraints})
    return pv


def transition(db: Session, pv: PlanVersion, target: str, actor: Actor, note: str | None = None) -> PlanVersion:
    key = (pv.status, target)
    perm = TRANSITIONS.get(key)
    if perm is None:
        raise Conflict("invalid_transition", f"Cannot move plan version from {pv.status} to {target}",
                       from_status=pv.status, to_status=target)
    if not has_permission(actor.role, perm):
        raise Forbidden(f"Role {actor.role} cannot perform {pv.status} → {target}", required=perm.value)
    now = operational_now(db, pv.area_id)
    if target == "REVIEWED":
        pv.reviewed_by, pv.reviewed_at = actor.username, now
    elif target == "APPROVED":
        pv.approved_by, pv.approved_at = actor.username, now
        pv.resource_snapshot = resource_snapshot(db, pv.area_id)
        sc = current_scenario(db, pv.area_id)
        pv.basis_scenario_id = sc.id
        from app.models import OperationalArea

        area = db.get(OperationalArea, pv.area_id)
        pv.basis_data_version = area.data_version if area else None
    elif target == "ACTIVE":
        for other in db.scalars(select(PlanVersion).where(PlanVersion.area_id == pv.area_id, PlanVersion.status == "ACTIVE",
                                                          PlanVersion.id != pv.id)):
            other.status = "SUPERSEDED"
            other.superseded_at = now
            record(db, actor, "PLAN_SUPERSEDED", "plan_version", other.id, f"{other.id} superseded by {pv.id}",
                   area_id=pv.area_id)
        pv.activated_at = now
        _carry_over_execution(db, pv)
    old = pv.status
    pv.status = target
    action = {"REVIEWED": "PLAN_REVIEWED", "APPROVED": "PLAN_APPROVED", "ACTIVE": "PLAN_ACTIVATED",
              "REJECTED": "PLAN_REJECTED", "DRAFT": "PLAN_RETURNED_TO_DRAFT"}[target]
    record(db, actor, action, "plan_version", pv.id, f"{pv.id}: {old} → {target}", area_id=pv.area_id,
           affects_results=target == "ACTIVE", details={"note": note})
    return pv


def _carry_over_execution(db: Session, pv: PlanVersion) -> None:
    """Execution facts (DONE / WORKING / EN_ROUTE) from the parent version stay true in the new version."""
    if not pv.parent_version_id:
        return
    parent_tasks = {t.code: t for t in db.scalars(select(PlanTask).where(PlanTask.plan_version_id == pv.parent_version_id))}
    for t in db.scalars(select(PlanTask).where(PlanTask.plan_version_id == pv.id)):
        p = parent_tasks.get(t.code)
        if p and p.status in ("DONE", "WORKING", "EN_ROUTE") and p.template_id == t.template_id and p.site_id == t.site_id:
            t.status = p.status
            t.actual_departure, t.actual_start, t.completed_at = p.actual_departure, p.actual_start, p.completed_at


def update_task_status(db: Session, task: PlanTask, status: str, actor: Actor, note: str | None = None,
                       at: datetime | None = None) -> PlanTask:
    if status not in TASK_STATUSES:
        raise ArgusError("invalid_task_status", f"Unknown status {status}")
    pv = db.get(PlanVersion, task.plan_version_id)
    if pv is None:
        raise NotFound("plan version", task.plan_version_id)
    if pv.status != "ACTIVE":
        raise Conflict("plan_not_active", "Task status can only be updated on the ACTIVE plan version")
    now = at or operational_now(db, pv.area_id)
    old = task.status
    task.status = status
    task.status_updated_at, task.status_updated_by = now, actor.username
    if status == "EN_ROUTE":
        task.actual_departure = now
    elif status == "WORKING":
        task.actual_start = now
        task.actual_departure = task.actual_departure or now
    elif status == "DONE":
        task.completed_at = now
    if note:
        task.notes = (task.notes + "\n" if task.notes else "") + note
    record(db, actor, "TASK_STATUS_CHANGED", "plan_task", task.id, f"{task.code}: {old} → {status}", area_id=pv.area_id,
           affects_results=True, details={"plan_version": pv.id, "from": old, "to": status, "note": note})
    return task
