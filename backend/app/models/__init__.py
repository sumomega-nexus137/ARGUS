"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.area import Base_, OperationalArea, PopulationZone, Sector, User
from app.models.hydro import DataConflict, Forecast, HydroStation, Observation
from app.models.infrastructure import (
    Bottleneck,
    Bridge,
    Building,
    CriticalFacility,
    RoadEvent,
    RoadNode,
    RoadSegment,
    TaskSite,
)
from app.models.plans import Plan, PlanTask, PlanVersion
from app.models.resources import ApprovedAction, Resource, ResourceStatus
from app.models.scenario import ActionWindowSnapshot, FloodExtent, Scenario, ScenarioFrame
from app.models.system import (
    AuditLog,
    ImportJob,
    ModelVersion,
    OptimizationRun,
    PipelineRun,
    ProviderStatus,
    StressTestRun,
    ValidationRun,
)

ResponseBase = Base_

__all__ = [
    "ActionWindowSnapshot",
    "ApprovedAction",
    "AuditLog",
    "Base_",
    "Bottleneck",
    "Bridge",
    "Building",
    "CriticalFacility",
    "DataConflict",
    "FloodExtent",
    "Forecast",
    "HydroStation",
    "ImportJob",
    "ModelVersion",
    "Observation",
    "OperationalArea",
    "OptimizationRun",
    "PipelineRun",
    "Plan",
    "PlanTask",
    "PlanVersion",
    "PopulationZone",
    "ProviderStatus",
    "Resource",
    "ResourceStatus",
    "ResponseBase",
    "RoadEvent",
    "RoadNode",
    "RoadSegment",
    "Scenario",
    "ScenarioFrame",
    "Sector",
    "StressTestRun",
    "TaskSite",
    "User",
    "ValidationRun",
]
