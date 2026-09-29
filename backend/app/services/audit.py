"""Audit trail + data-version bookkeeping.

Every change that can alter a computed result bumps the area's ``data_version`` and writes an
audit entry flagged ``affects_results`` — this is how ARGUS answers
"WHY DID ARGUS CHANGE ITS RESULT?".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, OperationalArea


@dataclass(frozen=True)
class Actor:
    username: str
    role: str

    @staticmethod
    def system() -> Actor:
        return Actor("argus-system", "ADMIN")


def operational_now(db: Session, area_id: str | None) -> datetime | None:
    from app.services.clock import area_now

    if not area_id:
        return None
    area = db.get(OperationalArea, area_id)
    return area_now(area) if area else None


def bump_data_version(db: Session, area_id: str) -> int:
    area = db.get(OperationalArea, area_id)
    if area is None:
        return 0
    area.data_version = (area.data_version or 0) + 1
    db.flush()
    return area.data_version


def record(
    db: Session,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: str | None,
    summary: str,
    *,
    area_id: str | None = None,
    details: dict[str, Any] | None = None,
    affects_results: bool = False,
    op_time: datetime | None = None,
) -> AuditLog:
    version = None
    if affects_results and area_id:
        version = bump_data_version(db, area_id)
    elif area_id:
        area = db.get(OperationalArea, area_id)
        version = area.data_version if area else None
    entry = AuditLog(
        username=actor.username,
        role=actor.role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        area_id=area_id,
        summary=summary,
        details=details or {},
        affects_results=affects_results,
        data_version=version,
        op_time=op_time or operational_now(db, area_id),
    )
    db.add(entry)
    db.flush()
    return entry


def changes_since(db: Session, area_id: str, data_version: int) -> list[AuditLog]:
    q = (
        select(AuditLog)
        .where(AuditLog.area_id == area_id, AuditLog.affects_results.is_(True), AuditLog.data_version > data_version)
        .order_by(AuditLog.id)
    )
    return list(db.scalars(q))
