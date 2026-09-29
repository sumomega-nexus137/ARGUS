"""Plan / evaluation data structures shared by the evaluator, stress tester, optimizer and operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.services.routing.access import AccessConfig


@dataclass
class TaskSpec:
    code: str
    template_id: str
    site_id: str
    resource_ids: list[str]
    planned_departure: float | None = None  # minutes relative to scenario reference
    dependencies: list[str] = field(default_factory=list)
    status: str = "PENDING"  # operations status
    actual_departure: float | None = None
    actual_start: float | None = None
    completed_at: float | None = None
    sort_order: int = 0


@dataclass(frozen=True)
class Constraint:
    """Human (commander) constraint added to plan evaluation and optimization."""

    kind: str  # FORBID_RESOURCE_SECTOR | FORBID_RESOURCE_TASK | REQUIRE_TASK | EXCLUDE_TASK | PIN_ASSIGNMENT
    resource_id: str | None = None
    sector: str | None = None
    task_code: str | None = None
    note: str | None = None
    author: str | None = None

    @staticmethod
    def from_dict(d: dict) -> Constraint:
        return Constraint(d.get("kind", ""), d.get("resource_id"), d.get("sector"), d.get("task_code"), d.get("note"),
                          d.get("author"))

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvalConfig:
    access: AccessConfig
    as_of: float
    unavailable: frozenset[str] = frozenset()
    delays: tuple[tuple[str, float], ...] = ()
    constraints: tuple[Constraint, ...] = ()
    label: str = "baseline"


@dataclass
class Issue:
    type: str
    blocking: bool
    params: dict = field(default_factory=dict)


@dataclass
class TaskResult:
    code: str
    template_id: str
    site_id: str
    resource_ids: list[str]
    status: str  # FEASIBLE | AT_RISK | INFEASIBLE | DONE | IN_PROGRESS
    issues: list[Issue]
    origin_node: str | None = None
    departure: float | None = None
    arrival: float | None = None
    start: float | None = None
    end: float | None = None
    travel_min: float | None = None
    route_segments: list[str] = field(default_factory=list)
    route_roads: list[str] = field(default_factory=list)
    route_timeline: list[dict] = field(default_factory=list)
    deadline: float | None = None
    deadline_reason: str = "NONE"
    deadline_components: dict = field(default_factory=dict)
    latest_departure: float | None = None
    latest_route_roads: list[str] = field(default_factory=list)
    slack_min: float | None = None
    vehicle_class: str = "STANDARD"
    crew_id: str | None = None
    planned_departure: float | None = None
    window_status: str | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["issues"] = [asdict(i) for i in self.issues]
        return d


@dataclass
class PlanEvaluation:
    status: str  # FEASIBLE | AT_RISK | INFEASIBLE
    tasks: list[TaskResult]
    config_label: str
    member: str
    as_of: float
    resource_conflicts: list[dict] = field(default_factory=list)

    @property
    def by_code(self) -> dict[str, TaskResult]:
        return {t.code: t for t in self.tasks}

    @property
    def feasible(self) -> bool:
        return self.status != "INFEASIBLE"

    def failed_codes(self) -> list[str]:
        return [t.code for t in self.tasks if t.status == "INFEASIBLE"]

    def as_dict(self) -> dict:
        return {"status": self.status, "config_label": self.config_label, "member": self.member, "as_of": self.as_of,
                "tasks": [t.as_dict() for t in self.tasks], "resource_conflicts": self.resource_conflicts,
                "failed": self.failed_codes(),
                "at_risk": [t.code for t in self.tasks if t.status == "AT_RISK"]}
