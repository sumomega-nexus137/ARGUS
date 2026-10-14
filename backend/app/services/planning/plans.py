"""Plan ⇄ engine conversions and evaluation entry points."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import Plan, PlanTask, PlanVersion, Scenario
from app.repositories.context import AreaContext
from app.services.clock import to_minutes
from app.services.planning.evaluator import evaluate_plan
from app.services.planning.model import Constraint, EvalConfig, PlanEvaluation, TaskSpec
from app.services.routing.access import AccessConfig
from app.services.scenario.runtime import ScenarioRuntime, get_scenario, runtime_for


def version_tasks(db: Session, pv: PlanVersion) -> list[PlanTask]:
    return list(db.scalars(select(PlanTask).where(PlanTask.plan_version_id == pv.id).order_by(PlanTask.sort_order, PlanTask.code)))


def to_specs(rows: list[PlanTask], rt: ScenarioRuntime) -> list[TaskSpec]:
    ref = rt.reference_time

    def m(x):  # type: ignore[no-untyped-def]
        return to_minutes(ref, x) if x is not None else None

    return [TaskSpec(code=r.code, template_id=r.template_id, site_id=r.site_id, resource_ids=list(r.resource_ids or []),
                     planned_departure=m(r.planned_departure), dependencies=list(r.dependencies or []), status=r.status,
                     actual_departure=m(r.actual_departure), actual_start=m(r.actual_start), completed_at=m(r.completed_at),
                     sort_order=r.sort_order)
            for r in rows]


def get_version(db: Session, version_id: str) -> PlanVersion:
    pv = db.get(PlanVersion, version_id)
    if pv is None:
        raise NotFound("plan version", version_id)
    return pv


def active_version(db: Session, area_id: str) -> PlanVersion | None:
    return db.scalars(select(PlanVersion).where(PlanVersion.area_id == area_id, PlanVersion.status == "ACTIVE")
                      .order_by(PlanVersion.created_at.desc())).first()


def latest_versions(db: Session, area_id: str) -> list[PlanVersion]:
    return list(db.scalars(select(PlanVersion).where(PlanVersion.area_id == area_id).order_by(PlanVersion.plan_id, PlanVersion.version)))


def constraints_of(pv: PlanVersion) -> tuple[Constraint, ...]:
    return tuple(Constraint.from_dict(c) for c in (pv.constraints or []))


def evaluate_version(db: Session, ctx: AreaContext, pv: PlanVersion, scenario: Scenario | None = None,
                     as_of_min: float | None = None, label: str = "current") -> tuple[PlanEvaluation, ScenarioRuntime]:
    from app.services.scenario.runtime import current_scenario

    sc = scenario or current_scenario(db, ctx.area_id)
    rt = runtime_for(sc)
    now = to_minutes(rt.reference_time, ctx.now) if as_of_min is None else as_of_min
    cfg = EvalConfig(access=AccessConfig(member=rt.member), as_of=now, constraints=constraints_of(pv), label=label)
    return evaluate_plan(ctx, rt, to_specs(version_tasks(db, pv), rt), cfg), rt


def basis_runtime(db: Session, pv: PlanVersion) -> ScenarioRuntime | None:
    if not pv.basis_scenario_id:
        return None
    try:
        return runtime_for(get_scenario(db, pv.basis_scenario_id))
    except NotFound:
        return None


def plan_name(db: Session, pv: PlanVersion) -> str:
    p = db.get(Plan, pv.plan_id)
    return p.name if p else pv.plan_id
